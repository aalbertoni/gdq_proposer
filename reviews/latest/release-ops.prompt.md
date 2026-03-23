Voce e um revisor de release e operacoes.

Analise o diff abaixo e responda SOMENTE em JSON com o formato padrao.

Verifique obrigatoriamente:
1. O app continua implantavel pelo compose?
2. O health check e valido e suficiente para a mudanca?
3. Ha smoke test compativel com o que mudou?
4. Existe plano de rollback por artefato?
5. Se houver migracao, o deploy continua seguro?
6. Ha logging e sinais minimos para diagnostico pos-deploy?
7. Alguma alteracao exige aprovacao humana antes de prod?

Formato esperado:
{
  "status": "APROVADO|ATENCAO|BLOQUEADO",
  "blockers": [],
  "warnings": [],
  "summary": "Resumo em uma linha."
}

Diff:
diff --git a/.coverage b/.coverage
index ac5d0e1..81d8dfb 100644
Binary files a/.coverage and b/.coverage differ
diff --git a/core/calibration_advisor.py b/core/calibration_advisor.py
new file mode 100644
index 0000000..2f4110a
--- /dev/null
+++ b/core/calibration_advisor.py
@@ -0,0 +1,762 @@
+"""
+Assistente de Calibracao: substituicao explicavel do auto-tune grid search.
+
+Logica sequencial em 5 etapas, onde cada decisao e justificada:
+1. Escolher N (janela) baseado no grao e dados disponiveis
+2. Testar sigma sozinho — se >=98% cobertura normal, nao usar margem
+3. Adicionar margem somente se sigma insuficiente
+4. Validar com backtest e ajustar se FPs recentes
+5. Gerar relatorio de justificativa
+
+Funcoes puras — sem I/O, sem Athena, sem UI.
+
+Dependencias: core/backtest, core/statistical_engine, core/series_regime.
+"""
+
+import math
+from dataclasses import dataclass, field
+from typing import Optional
+
+from core.backtest import backtest_band, backtest_frequency_dual_guard
+from core.models.enums import ConfidenceLevel, GrainType, SeriesRegime
+from core.models.series_profile import SeriesProfile
+from core.series_regime import classify_series
+from core.statistical_engine import _filter_valid, detect_change_points
+
+
+# ---------------------------------------------------------------------------
+# Resultado da calibracao
+# ---------------------------------------------------------------------------
+
+@dataclass
+class CalibrationStep:
+    """Uma etapa do processo de calibracao com sua justificativa."""
+
+    step: int
+    name: str
+    decision: str
+    justification: str
+    data: dict = field(default_factory=dict)
+
+
+@dataclass
+class CalibrationResult:
+    """Resultado completo da calibracao com parametros e justificativas.
+
+    Attrs:
+        n_periods: Janela escolhida.
+        n_sigma: Multiplicador de sigma escolhido.
+        margin_pct: Margem percentual (0 se nao necessaria).
+        margin_enabled: Se a margem esta ativa.
+        coverage_pct: Cobertura do backtest final.
+        weighted_coverage_pct: Cobertura ponderada por recencia.
+        false_positives: FPs estimados do backtest final.
+        confidence: Nivel de confianca final.
+        viable: Se a calibracao encontrou parametros aceitaveis.
+        steps: Lista de etapas com justificativas.
+        recommendation: Texto final de recomendacao.
+        profile: Perfil de regime da serie (se disponivel).
+    """
+
+    n_periods: int
+    n_sigma: float
+    margin_pct: float
+    margin_enabled: bool
+    coverage_pct: float
+    weighted_coverage_pct: float
+    false_positives: int
+    stability: float
+    confidence: ConfidenceLevel
+    viable: bool
+    steps: list[CalibrationStep] = field(default_factory=list)
+    recommendation: str = ""
+    profile: Optional[SeriesProfile] = None
+
+
+# ---------------------------------------------------------------------------
+# Thresholds
+# ---------------------------------------------------------------------------
+
+# Cobertura minima de pontos normais para aceitar sigma sozinho
+SIGMA_SUFFICIENT_THRESHOLD = 0.98
+
+# Cobertura minima com margem para aceitar
+MARGIN_SUFFICIENT_THRESHOLD = 0.98
+
+# Sigmas testados em ordem de preferencia (menor = mais restritivo)
+SIGMA_CANDIDATES = [2.0, 2.5, 3.0, 3.5]
+
+# Margens testadas em ordem de preferencia (menor = mais restritivo)
+MARGIN_CANDIDATES = [0.05, 0.10, 0.15, 0.20]
+
+# N defaults por grao
+N_DEFAULTS = {
+    GrainType.DAILY: 30,
+    GrainType.MONTHLY: 12,
+}
+
+# Minimo de pontos avaliados para considerar valido
+MIN_EVALUATED_POINTS = 5
+
+# FP maximo nos ultimos 7 periodos antes de relaxar
+MAX_RECENT_FP = 0
+
+
+# ---------------------------------------------------------------------------
+# Funcoes auxiliares
+# ---------------------------------------------------------------------------
+
+def _compute_outlier_mask(values: list[float]) -> set[int]:
+    """Detecta outliers via IQR 2.5x e retorna indices."""
+    valid = [(i, v) for i, v in enumerate(values)
+             if v is not None and not (isinstance(v, float) and math.isnan(v))]
+    if len(valid) < 4:
+        return set()
+
+    sorted_vals = sorted(v for _, v in valid)
+    q1_idx = len(sorted_vals) // 4
+    q3_idx = 3 * len(sorted_vals) // 4
+    q1 = sorted_vals[q1_idx]
+    q3 = sorted_vals[q3_idx]
+    iqr = q3 - q1
+    fence_lower = q1 - 2.5 * iqr
+    fence_upper = q3 + 2.5 * iqr
+
+    return {i for i, v in valid if v < fence_lower or v > fence_upper}
+
+
+def _normal_coverage(backtest_result, outlier_indices: set[int]) -> float:
+    """Calcula cobertura de pontos normais (excluindo outliers)."""
+    normal_pass = 0
+    normal_total = 0
+    for pr in backtest_result.point_results:
+        if pr["index"] not in outlier_indices:
+            normal_total += 1
+            if pr["passed"]:
+                normal_pass += 1
+    if normal_total == 0:
+        return backtest_result.coverage_pct / 100.0
+    return normal_pass / normal_total
+
+
+def _recent_fps(backtest_result, n_recent: int = 7) -> int:
+    """Conta falsos positivos nos ultimos N periodos."""
+    results = backtest_result.point_results
+    if not results:
+        return 0
+    recent = results[-n_recent:]
+    return sum(1 for r in recent if not r["passed"])
+
+
+# ---------------------------------------------------------------------------
+# Etapa 1: Escolher N
+# ---------------------------------------------------------------------------
+
+def choose_n(
+    values: list[float],
+    dates: list[str],
+    grain: GrainType = GrainType.DAILY,
+    profile: Optional[SeriesProfile] = None,
+) -> CalibrationStep:
+    """Escolhe a janela N baseada no grao e dados disponiveis.
+
+    Regras:
+    - Default: 30 (daily), 12 (monthly)
+    - Se structural_break: usar apenas dados pos-mudanca
+    - Se serie curta (< 2*N_default): reduzir proporcionalmente
+    - Seasonal: preferir multiplo de 7 (daily)
+    """
+    valid = _filter_valid(values)
+    n_valid = len(valid)
+    n_default = N_DEFAULTS.get(grain, 30)
+    reasons: list[str] = []
+
+    n_chosen = n_default
+    reasons.append(f"default para grao {grain.value}: N={n_default}")
+
+    # Structural break: limitar N aos dados pos-mudanca
+    post_change_len = None
+    if profile and profile.has_structural_break:
+        change_result = detect_change_points(values, dates)
+        if change_result.get("has_change_point"):
+            post_change_len = len(change_result.get("post_change_values", []))
+            if post_change_len >= 5:
+                n_chosen = min(n_chosen, max(post_change_len - 2, 5))
+                reasons.append(
+                    f"mudanca de regime em {profile.change_point_date}: "
+                    f"limitado a {post_change_len} pontos pos-mudanca → N={n_chosen}"
+                )
+
+    # Serie curta: reduzir proporcionalmente
+    if n_valid < 2 * n_chosen:
+        n_chosen = max(n_valid // 2, 5)
+        reasons.append(f"serie curta ({n_valid} pontos): reduzido para N={n_chosen}")
+
+    # Seasonal (daily): preferir multiplo de 7
+    if profile and profile.is_seasonal and grain == GrainType.DAILY:
+        # Encontrar o multiplo de 7 mais proximo de n_chosen
+        candidates_7 = [7, 14, 21, 28, 35, 42]
+        best_7 = min(candidates_7, key=lambda x: abs(x - n_chosen))
+        if best_7 <= n_valid // 2:
+            n_chosen = best_7
+            reasons.append(
+                f"sazonalidade semanal detectada: ajustado para multiplo de 7 → N={n_chosen}"
+            )
+
+    justification = ". ".join(reasons) + "."
+
+    return CalibrationStep(
+        step=1,
+        name="Escolha de N (janela)",
+        decision=f"N = {n_chosen}",
+        justification=f"N={n_chosen} porque {justification}",
+        data={"n_periods": n_chosen, "n_valid": n_valid, "post_change_len": post_change_len},
+    )
+
+
+# ---------------------------------------------------------------------------
+# Etapa 2: Testar sigma sozinho
+# ---------------------------------------------------------------------------
+
+def find_best_sigma(
+    values: list[float],
+    dates: list[str],
+    n_periods: int,
+    outlier_indices: set[int],
+    metric_kind: str = "numeric",
+) -> CalibrationStep:
+    """Testa sigmas em ordem crescente sem margem.
+
+    Se algum sigma atinge >= 98% cobertura normal, retorna-o.
+    Sempre retorna o melhor sigma encontrado.
+    """
+    best_sigma = SIGMA_CANDIDATES[0]
+    best_coverage = 0.0
+    sigma_sufficient = False
+    results_by_sigma: dict[float, float] = {}
+
+    for sigma in SIGMA_CANDIDATES:
+        try:
+            if metric_kind == "frequency":
+                bt = backtest_frequency_dual_guard(
+                    pct_series=values, dates=dates,
+                    n_periods=n_periods, n_sigma=sigma,
+                    margin_pct=0.0, buffer=0.01,
+                    margin_enabled=False,
+                )
+            else:
+                bt = backtest_band(
+                    values=values, dates=dates,
+                    n_periods=n_periods, n_sigma=sigma,
+                    margin_pct=0.0, margin_enabled=False,
+                )
+        except Exception:
+            continue
+
+        if bt.total_periods < MIN_EVALUATED_POINTS:
+            continue
+
+        cov = _normal_coverage(bt, outlier_indices)
+        results_by_sigma[sigma] = cov
+
+        if cov > best_coverage:
+            best_coverage = cov
+            best_sigma = sigma
+
+        if cov >= SIGMA_SUFFICIENT_THRESHOLD and not sigma_sufficient:
+            sigma_sufficient = True
+            best_sigma = sigma
+            best_coverage = cov
+            break  # Menor sigma que atinge threshold — parar
+
+    if sigma_sufficient:
+        decision = f"sigma = {best_sigma} (suficiente sem margem)"
+        justification = (
+            f"sigma={best_sigma} cobre {best_coverage:.1%} dos pontos normais "
+            f"(>= {SIGMA_SUFFICIENT_THRESHOLD:.0%}). Margem desnecessaria."
+        )
+    else:
+        decision = f"sigma = {best_sigma} (melhor disponivel, margem necessaria)"
+        justification = (
+            f"Nenhum sigma atinge {SIGMA_SUFFICIENT_THRESHOLD:.0%} de cobertura normal. "
+            f"Melhor: sigma={best_sigma} com {best_coverage:.1%}. Margem sera adicionada."
+        )
+
+    return CalibrationStep(
+        step=2,
+        name="Teste de sigma (sem margem)",
+        decision=decision,
+        justification=justification,
+        data={
+            "sigma": best_sigma,
+            "coverage": best_coverage,
+            "sigma_sufficient": sigma_sufficient,
+            "results_by_sigma": results_by_sigma,
+        },
+    )
+
+
+# ---------------------------------------------------------------------------
+# Etapa 3: Adicionar margem se necessario
+# ---------------------------------------------------------------------------
+
+def add_margin_if_needed(
+    values: list[float],
+    dates: list[str],
+    n_periods: int,
+    sigma: float,
+    sigma_sufficient: bool,
+    outlier_indices: set[int],
+    metric_kind: str = "numeric",
+) -> CalibrationStep:
+    """Adiciona margem somente se sigma nao foi suficiente.
+
+    Testa margens em ordem crescente e escolhe a menor que atinge
+    >= 98% cobertura normal com o sigma escolhido.
+    """
+    if sigma_sufficient:
+        return CalibrationStep(
+            step=3,
+            name="Margem percentual",
+            decision="margem desativada",
+            justification="Sigma sozinho ja atinge cobertura suficiente. Margem nao necessaria.",
+            data={"margin_pct": 0.0, "margin_enabled": False},
+        )
+
+    best_margin = MARGIN_CANDIDATES[0]
+    best_coverage = 0.0
+    margin_found = False
+    results_by_margin: dict[float, float] = {}
+
+    for margin in MARGIN_CANDIDATES:
+        try:
+            if metric_kind == "frequency":
+                bt = backtest_frequency_dual_guard(
+                    pct_series=values, dates=dates,
+                    n_periods=n_periods, n_sigma=sigma,
+                    margin_pct=margin, buffer=0.01,
+                    margin_enabled=True,
+                )
+            else:
+                bt = backtest_band(
+                    values=values, dates=dates,
+                    n_periods=n_periods, n_sigma=sigma,
+                    margin_pct=margin, margin_enabled=True,
+                )
+        except Exception:
+            continue
+
+        if bt.total_periods < MIN_EVALUATED_POINTS:
+            continue
+
+        cov = _normal_coverage(bt, outlier_indices)
+        results_by_margin[margin] = cov
+
+        if cov > best_coverage:
+            best_coverage = cov
+            best_margin = margin
+
+        if cov >= MARGIN_SUFFICIENT_THRESHOLD and not margin_found:
+            margin_found = True
+            best_margin = margin
+            best_coverage = cov
+            break
+
+    if margin_found:
+        justification = (
+            f"Sigma={sigma} sozinho insuficiente. "
+            f"Com margem {best_margin:.0%}, cobertura normal atinge {best_coverage:.1%}."
+        )
+    else:
+        justification = (
+            f"Sigma={sigma} sozinho insuficiente. "
+            f"Melhor margem testada: {best_margin:.0%} com cobertura {best_coverage:.1%}. "
+            f"A serie pode ser muito volatil para regra automatica."
+        )
+
+    return CalibrationStep(
+        step=3,
+        name="Margem percentual",
+        decision=f"margem = {best_margin*100:.0f}% ({'ativada' if True else 'desativada'})",
+        justification=justification,
+        data={
+            "margin_pct": best_margin,
+            "margin_enabled": True,
+            "coverage_with_margin": best_coverage,
+            "results_by_margin": results_by_margin,
+        },
+    )
+
+
+# ---------------------------------------------------------------------------
+# Etapa 4: Validar com backtest
+# ---------------------------------------------------------------------------
+
+def validate_with_backtest(
+    values: list[float],
+    dates: list[str],
+    n_periods: int,
+    sigma: float,
+    margin_pct: float,
+    margin_enabled: bool,
+    outlier_indices: set[int],
+    metric_kind: str = "numeric",
+) -> CalibrationStep:
+    """Executa backtest final e verifica FPs recentes.
+
+    Se ha FPs nos ultimos 7 periodos, tenta relaxar:
+    1. Se margem desativada, ativa com menor margem viavel
+    2. Se margem ativa, incrementa sigma em 0.5
+    """
+    try:
+        if metric_kind == "frequency":
+            bt = backtest_frequency_dual_guard(
+                pct_series=values, dates=dates,
+                n_periods=n_periods, n_sigma=sigma,
+                margin_pct=margin_pct, buffer=0.01,
+                margin_enabled=margin_enabled,
+            )
+        else:
+            bt = backtest_band(
+                values=values, dates=dates,
+                n_periods=n_periods, n_sigma=sigma,
+                margin_pct=margin_pct, margin_enabled=margin_enabled,
+            )
+    except Exception as e:
+        return CalibrationStep(
+            step=4,
+            name="Validacao por backtest",
+            decision="falha no backtest",
+            justification=f"Backtest falhou: {e}. Dados insuficientes ou invalidos.",
+            data={
+                "backtest": None,
+                "adjusted": False,
+                "final_sigma": sigma,
+                "final_margin_pct": margin_pct,
+                "final_margin_enabled": margin_enabled,
+            },
+        )
+
+    recent_fp = _recent_fps(bt, n_recent=7)
+    adjusted = False
+    adjust_reason = ""
+
+    # Tentar relaxar se FPs recentes
+    if recent_fp > MAX_RECENT_FP:
+        if not margin_enabled:
+            # Tentar ativar margem minima
+            for try_margin in MARGIN_CANDIDATES:
+                try:
+                    if metric_kind == "frequency":
+                        bt2 = backtest_frequency_dual_guard(
+                            pct_series=values, dates=dates,
+                            n_periods=n_periods, n_sigma=sigma,
+                            margin_pct=try_margin, buffer=0.01,
+                            margin_enabled=True,
+                        )
+                    else:
+                        bt2 = backtest_band(
+                            values=values, dates=dates,
+                            n_periods=n_periods, n_sigma=sigma,
+                            margin_pct=try_margin, margin_enabled=True,
+                        )
+                    if _recent_fps(bt2, 7) == 0:
+                        bt = bt2
+                        margin_pct = try_margin
+                        margin_enabled = True
+                        adjusted = True
+                        adjust_reason = (
+                            f"FP recente detectado: ativada margem {try_margin:.0%} para eliminar."
+                        )
+                        break
+                except Exception:
+                    continue
+        else:
+            # Tentar aumentar sigma
+            for try_sigma in [sigma + 0.5, sigma + 1.0]:
+                if try_sigma > 4.0:
+                    break
+                try:
+                    if metric_kind == "frequency":
+                        bt2 = backtest_frequency_dual_guard(
+                            pct_series=values, dates=dates,
+                            n_periods=n_periods, n_sigma=try_sigma,
+                            margin_pct=margin_pct, buffer=0.01,
+                            margin_enabled=True,
+                        )
+                    else:
+                        bt2 = backtest_band(
+                            values=values, dates=dates,
+                            n_periods=n_periods, n_sigma=try_sigma,
+                            margin_pct=margin_pct, margin_enabled=True,
+                        )
+                    if _recent_fps(bt2, 7) == 0:
+                        bt = bt2
+                        sigma = try_sigma
+                        adjusted = True
+                        adjust_reason = (
+                            f"FP recente detectado: sigma aumentado para {try_sigma} para eliminar."
+                        )
+                        break
+                except Exception:
+                    continue
+
+    normal_cov = _normal_coverage(bt, outlier_indices)
+
+    if adjusted:
+        justification = (
+            f"Backtest: {bt.coverage_pct:.1f}% cobertura geral, "
+            f"{bt.false_positive_proxy} FP(s). {adjust_reason}"
+        )
+    elif recent_fp > 0:
+        justification = (
+            f"Backtest: {bt.coverage_pct:.1f}% cobertura geral, "
+            f"{bt.false_positive_proxy} FP(s). "
+            f"{recent_fp} FP(s) nos ultimos 7 periodos — nao foi possivel eliminar completamente."
+        )
+    else:
+        justification = (
+            f"Backtest: {bt.coverage_pct:.1f}% cobertura geral, "
+            f"0 FPs nos ultimos 7 periodos. Parametros validados."
+        )
+
+    return CalibrationStep(
+        step=4,
+        name="Validacao por backtest",
+        decision=f"cobertura {bt.coverage_pct:.1f}%, {bt.false_positive_proxy} FP(s)",
+        justification=justification,
+        data={
+            "backtest": bt,
+            "adjusted": adjusted,
+            "final_sigma": sigma,
+            "final_margin_pct": margin_pct,
+            "final_margin_enabled": margin_enabled,
+            "normal_coverage": normal_cov,
+            "recent_fps": _recent_fps(bt, 7),
+        },
+    )
+
+
+# ---------------------------------------------------------------------------
+# Etapa 5: Gerar relatorio
+# ---------------------------------------------------------------------------
+
+def generate_report(
+    steps: list[CalibrationStep],
+    profile: Optional[SeriesProfile] = None,
+) -> CalibrationStep:
+    """Gera relatorio consolidado da calibracao."""
+    parts: list[str] = []
+
+    if profile:
+        parts.append(f"Regime: {profile.regime_summary}")
+        if profile.has_structural_break and profile.change_point_date:
+            parts.append(f"Mudanca de regime em {profile.change_point_date}")
+        if profile.is_seasonal:
+            parts.append(f"Sazonalidade detectada (eta²={profile.seasonality_strength:.2f})")
+        if profile.is_volatile:
+            parts.append(f"Serie volatil (CV={profile.cv:.2f})")
+        if profile.is_asymmetric:
+            parts.append(f"Distribuicao assimetrica (skew={profile.skewness:.2f})")
+
+    for step in steps:
+        parts.append(f"Etapa {step.step} ({step.name}): {step.decision}")
+
+    return CalibrationStep(
+        step=5,
+        name="Relatorio",
+        decision="calibracao concluida",
+        justification="\n".join(parts),
+        data={"summary_parts": parts},
+    )
+
+
+# ---------------------------------------------------------------------------
+# Orquestrador principal
+# ---------------------------------------------------------------------------
+
+def calibrate(
+    values: list[float],
+    dates: list[str],
+    grain: GrainType = GrainType.DAILY,
+    metric_kind: str = "numeric",
+    seasonality_enabled: bool = True,
+    profile: Optional[SeriesProfile] = None,
+) -> CalibrationResult:
+    """Executa calibracao completa em 5 etapas sequenciais.
+
+    Args:
+        values: Serie temporal de valores.
+        dates: Datas correspondentes.
+        grain: Granularidade temporal (daily, monthly).
+        metric_kind: "numeric" ou "frequency".
+        seasonality_enabled: Se deve considerar sazonalidade semanal.
+        profile: Perfil de regime pre-computado (opcional, sera calculado se None).
+
+    Returns:
+        CalibrationResult com parametros, justificativas e backtest.
+    """
+    valid = _filter_valid(values)
+    if len(valid) < 5:
+        return CalibrationResult(
+            n_periods=N_DEFAULTS.get(grain, 30),
+            n_sigma=2.0,
+            margin_pct=0.0,
+            margin_enabled=False,
+            coverage_pct=0.0,
+            weighted_coverage_pct=0.0,
+            false_positives=0,
+            stability=0.0,
+            confidence=ConfidenceLevel.LOW,
+            viable=False,
+            recommendation="Dados insuficientes para calibracao (minimo 5 pontos validos).",
+        )
+
+    # Classificar regime se nao fornecido
+    if profile is None:
+        profile = classify_series(values, dates, seasonality_enabled=seasonality_enabled)
+
+    # Mascara de outliers (calculada uma vez)
+    outlier_indices = _compute_outlier_mask(values)
+
+    steps: list[CalibrationStep] = []
+
+    # Etapa 1: Escolher N
+    step1 = choose_n(values, dates, grain=grain, profile=profile)
+    steps.append(step1)
+    n_periods = step1.data["n_periods"]
+
+    # Etapa 2: Testar sigma sozinho
+    step2 = find_best_sigma(
+        values, dates, n_periods, outlier_indices, metric_kind=metric_kind,
+    )
+    steps.append(step2)
+    sigma = step2.data["sigma"]
+    sigma_sufficient = step2.data["sigma_sufficient"]
+
+    # Etapa 3: Margem se necessario
+    step3 = add_margin_if_needed(
+        values, dates, n_periods, sigma, sigma_sufficient, outlier_indices,
+        metric_kind=metric_kind,
+    )
+    steps.append(step3)
+    margin_pct = step3.data["margin_pct"]
+    margin_enabled = step3.data["margin_enabled"]
+
+    # Etapa 4: Validar com backtest
+    step4 = validate_with_backtest(
+        values, dates, n_periods, sigma, margin_pct, margin_enabled,
+        outlier_indices, metric_kind=metric_kind,
+    )
+    steps.append(step4)
+
+    # Parametros finais (podem ter sido ajustados na etapa 4)
+    final_sigma = step4.data.get("final_sigma", sigma)
+    final_margin_pct = step4.data.get("final_margin_pct", margin_pct)
+    final_margin_enabled = step4.data.get("final_margin_enabled", margin_enabled)
+    bt = step4.data.get("backtest")
+
+    # Etapa 5: Relatorio
+    step5 = generate_report(steps, profile=profile)
+    steps.append(step5)
+
+    # Extrair metricas do backtest final
+    coverage_pct = bt.coverage_pct if bt else 0.0
+    weighted_coverage_pct = bt.weighted_coverage_pct if bt else 0.0
+    false_positives = bt.false_positive_proxy if bt else 0
+    stability = bt.stability_score if bt else 0.0
+
+    # Determinar confianca
+    if coverage_pct >= 90.0 and false_positives == 0:
+        confidence = ConfidenceLevel.HIGH
+    elif coverage_pct >= 70.0:
+        confidence = ConfidenceLevel.MEDIUM
+    else:
+        confidence = ConfidenceLevel.LOW
+
+    viable = coverage_pct >= 70.0
+
+    # Construir recomendacao
+    recommendation = _build_recommendation(
+        n_periods, final_sigma, final_margin_pct, final_margin_enabled,
+        coverage_pct, false_positives, confidence, profile, steps,
+    )
+
+    return CalibrationResult(
+        n_periods=n_periods,
+        n_sigma=final_sigma,
+        margin_pct=final_margin_pct,
+        margin_enabled=final_margin_enabled,
+        coverage_pct=coverage_pct,
+        weighted_coverage_pct=weighted_coverage_pct,
+        false_positives=false_positives,
+        stability=stability,
+        confidence=confidence,
+        viable=viable,
+        steps=steps,
+        recommendation=recommendation,
+        profile=profile,
+    )
+
+
+def _build_recommendation(
+    n_periods: int,
+    sigma: float,
+    margin_pct: float,
+    margin_enabled: bool,
+    coverage_pct: float,
+    false_positives: int,
+    confidence: ConfidenceLevel,
+    profile: Optional[SeriesProfile],
+    steps: list[CalibrationStep],
+) -> str:
+    """Constroi texto de recomendacao consolidado."""
+    parts: list[str] = []
+
+    # Parametros escolhidos
+    sigma_str = str(int(sigma)) if sigma == int(sigma) else f"{sigma:.1f}"
+    if margin_enabled:
+        params = (
+            f"N={n_periods}, sigma={sigma_str}, margem={margin_pct*100:.0f}%"
+        )
+    else:
+        params = f"N={n_periods}, sigma={sigma_str} (sem margem)"
+
+    # Veredicto principal
+    if confidence == ConfidenceLevel.HIGH:
+        parts.append(f"Recomendado: {params}. Cobertura {coverage_pct:.1f}%, 0 falsos positivos.")
+    elif confidence == ConfidenceLevel.MEDIUM:
+        fp_text = f", {false_positives} FP(s)" if false_positives > 0 else ""
+        parts.append(f"Aceitavel: {params}. Cobertura {coverage_pct:.1f}%{fp_text}. Revise os parametros.")
+    else:
+        parts.append(
+            f"Nao recomendado: {params}. Cobertura {coverage_pct:.1f}% com {false_positives} FP(s). "
+            f"A metrica pode ser instavel para regra automatica."
+        )
+
+    # Justificativa do sigma/margem
+    if not margin_enabled:
+        parts.append(
+            f"Sigma {sigma_str} suficiente sozinho — distribuicao bem comportada."
+        )
+    else:
+        parts.append(
+            f"Margem {margin_pct*100:.0f}% necessaria — sigma sozinho nao cobria pontos normais suficientes."
+        )
+
+    # Contexto de regime
+    if profile and profile.regime != SeriesRegime.STABLE:
+        regime_texts = {
+            SeriesRegime.STRUCTURAL_BREAK: "Mudanca de regime detectada — N limitado a dados pos-mudanca.",
+            SeriesRegime.TRENDING: "Tendencia detectada — N reduzido para acompanhar.",
+            SeriesRegime.SEASONAL: "Sazonalidade detectada — N ajustado para multiplo de 7.",
+            SeriesRegime.VOLATILE: "Serie volatil — parametros podem precisar de revisao periodica.",
+            SeriesRegime.ZERO_INFLATED: "Serie com muitos zeros — considere regra alternativa.",
+            SeriesRegime.ASYMMETRIC: "Distribuicao assimetrica — margem complementa sigma.",
+            SeriesRegime.SPARSE: "Serie esparsa — poucos dados reduzem confianca.",
+        }
+        regime_text = regime_texts.get(profile.regime)
+        if regime_text:
+            parts.append(regime_text)
+
+    return " ".join(parts)
diff --git a/core/calibration_explainer.py b/core/calibration_explainer.py
new file mode 100644
index 0000000..3b17314
--- /dev/null
+++ b/core/calibration_explainer.py
@@ -0,0 +1,136 @@
+"""
+Gerador de explicacoes para o Assistente de Calibracao.
+
+Converte CalibrationResult em texto legivel em pt-BR,
+detalhando cada etapa e decisao do processo de calibracao.
+
+Funcoes puras — sem I/O, sem Athena, sem UI.
+"""
+
+from core.calibration_advisor import CalibrationResult, CalibrationStep
+from core.models.enums import ConfidenceLevel, SeriesRegime
+
+
+def explain_calibration(result: CalibrationResult) -> str:
+    """Gera texto explicativo completo da calibracao em pt-BR.
+
+    Args:
+        result: Resultado da calibracao com etapas.
+
+    Returns:
+        Markdown com explicacao passo a passo.
+    """
+    parts: list[str] = []
+
+    parts.append("### Assistente de Calibracao")
+    parts.append("")
+
+    # Resumo do regime
+    if result.profile:
+        profile = result.profile
+        if profile.regime == SeriesRegime.STABLE:
+            parts.append("**Regime:** Estavel — serie sem anomalias detectadas.")
+        else:
+            parts.append(f"**Regime:** {profile.regime_summary}")
+            _append_regime_detail(parts, profile)
+        parts.append("")
+
+    # Etapas
+    for step in result.steps:
+        if step.step == 5:
+            continue  # Relatorio nao precisa ser repetido
+        parts.append(f"**Etapa {step.step}: {step.name}**")
+        parts.append(f"- Decisao: {step.decision}")
+        parts.append(f"- Justificativa: {step.justification}")
+        parts.append("")
+
+    # Veredicto final
+    parts.append("---")
+    parts.append(f"**Resultado:** {result.recommendation}")
+
+    return "\n".join(parts)
+
+
+def explain_calibration_short(result: CalibrationResult) -> str:
+    """Gera resumo curto (1-2 linhas) da calibracao.
+
+    Args:
+        result: Resultado da calibracao.
+
+    Returns:
+        Texto curto com parametros e justificativa principal.
+    """
+    sigma_str = _fmt_sigma(result.n_sigma)
+
+    if result.margin_enabled:
+        params = f"N={result.n_periods}, σ={sigma_str}, margem={result.margin_pct*100:.0f}%"
+    else:
+        params = f"N={result.n_periods}, σ={sigma_str} (sem margem)"
+
+    if not result.margin_enabled:
+        reason = "sigma suficiente"
+    else:
+        reason = "margem complementar necessaria"
+
+    return f"{params} — {reason}, cobertura {result.coverage_pct:.0f}%"
+
+
+def explain_step_detail(step: CalibrationStep) -> str:
+    """Gera explicacao detalhada de uma etapa individual.
+
+    Args:
+        step: Etapa da calibracao.
+
+    Returns:
+        Texto em pt-BR com detalhes da etapa.
+    """
+    parts = [f"**{step.name}**", f"Decisao: {step.decision}", f"Justificativa: {step.justification}"]
+
+    # Dados extras por tipo de etapa
+    if step.step == 2 and "results_by_sigma" in step.data:
+        results = step.data["results_by_sigma"]
+        if results:
+            parts.append("Cobertura por sigma:")
+            for sigma, cov in sorted(results.items()):
+                parts.append(f"  - σ={sigma}: {cov:.1%}")
+
+    if step.step == 3 and "results_by_margin" in step.data:
+        results = step.data["results_by_margin"]
+        if results:
+            parts.append("Cobertura por margem:")
+            for margin, cov in sorted(results.items()):
+                parts.append(f"  - margem={margin:.0%}: {cov:.1%}")
+
+    return "\n".join(parts)
+
+
+def _append_regime_detail(parts: list[str], profile) -> None:
+    """Adiciona detalhes do regime ao texto."""
+    if profile.has_structural_break and profile.change_point_date:
+        parts.append(
+            f"  - Mudanca de patamar em {profile.change_point_date} "
+            f"(magnitude: {profile.change_point_magnitude:.2f})"
+        )
+    if profile.is_seasonal:
+        parts.append(
+            f"  - Sazonalidade (eta²={profile.seasonality_strength:.2f}, "
+            f"amplitude={profile.seasonality_amplitude_ratio:.1%})"
+        )
+    if profile.is_volatile:
+        parts.append(f"  - Volatil (CV={profile.cv:.2f})")
+    if profile.has_trend:
+        parts.append(
+            f"  - Tendencia (slope={profile.drift_slope:.4f}, "
+            f"R²={profile.drift_r_squared:.2f})"
+        )
+    if profile.is_asymmetric:
+        parts.append(f"  - Assimetrica (skew={profile.skewness:.2f})")
+    if profile.is_zero_inflated:
+        parts.append(f"  - Zero-inflated ({profile.zero_pct:.0f}% zeros)")
+    if profile.is_sparse:
+        parts.append(f"  - Esparsa ({profile.null_pct:.0f}% nulos)")
+
+
+def _fmt_sigma(sigma: float) -> str:
+    """Formata sigma como inteiro quando possivel."""
+    return str(int(sigma)) if sigma == int(sigma) else f"{sigma:.1f}"
diff --git a/pages/02_explore.py b/pages/02_explore.py
index 6f6f9e3..d022894 100644
--- a/pages/02_explore.py
+++ b/pages/02_explore.py
@@ -19,6 +19,8 @@ from core.models.enums import BaselineMethod, ConfidenceLevel, RuleType, Semanti
 from core.models.rule_selection import RuleSelection
 from core.backtest_analysis import analyze_backtest, summarize_backtest_analysis
 from core.gdq_capability import capability_warning
+from core.calibration_advisor import calibrate, CalibrationResult
+from core.calibration_explainer import explain_calibration, explain_calibration_short, explain_step_detail
 from core.rule_explainer import explain_rule, explain_rule_detail, explain_regime_context, explain_trade_offs
 from core.rule_scoring import evaluate_proposal
 from core.series_regime import classify_series
@@ -568,99 +570,70 @@ def _render_diagnostics_panel(proposal):
                 )
 
 
-def _render_auto_tune(proposal_svc, values, dates, rule_key, metric_kind="numeric"):
-    """Renderiza botao de auto-tuning, exibe resultado com justificativa e aplica parametros.
+def _render_calibration(proposal_svc, values, dates, rule_key, metric_kind="numeric",
+                        grain=None, series_profile=None):
+    """Renderiza botao de calibracao explicavel, exibe resultado com justificativa e aplica parametros.
 
-    Alem de mostrar os parametros recomendados, exibe um breakdown detalhado
-    do score composto e uma comparacao antes/depois quando possivel.
+    Substitui o antigo auto-tune (grid search) por logica sequencial em 5 etapas:
+    1. Escolher N pelo grao
+    2. Testar sigma sozinho — se suficiente, sem margem
+    3. Adicionar margem somente se necessario
+    4. Validar com backtest
+    5. Gerar justificativa
+
+    Cada decisao e explicada ao usuario.
     """
+    from core.models.enums import GrainType
     cache_key = f"autotune_{rule_key}"
 
-    # Captura parametros atuais dos sliders para comparacao antes/depois
-    current_n = st.session_state.get(f"n_{rule_key}")
-    current_k = st.session_state.get(f"k_{rule_key}")
-    current_margin_pct_int = st.session_state.get(f"margin_{rule_key}")
-    current_margin_on = st.session_state.get(f"margin_on_{rule_key}")
+    if grain is None:
+        grain = GrainType.DAILY
 
     if st.button(
-        "Sugerir melhor combinacao",
+        "Calibrar parametros",
         key=f"btn_autotune_{rule_key}",
-        help="Testa diversas combinacoes de N, sigma e margem para encontrar "
-             "a que maximiza cobertura com menos falsos positivos.",
+        help="Analisa a serie e sugere a melhor combinacao de N, sigma e margem, "
+             "explicando cada decisao.",
     ):
-        with st.spinner("Avaliando combinacoes..."):
-            result = proposal_svc.find_best_params(
-                values=values, dates=dates, metric_kind=metric_kind,
+        with st.spinner("Calibrando..."):
+            result = calibrate(
+                values=values, dates=dates,
+                grain=grain, metric_kind=metric_kind,
+                profile=series_profile,
             )
-            # Captura tambem o backtest com parametros atuais para comparacao
-            current_snapshot = None
-            if current_n is not None and current_k is not None:
-                try:
-                    current_margin = (current_margin_pct_int or 10) / 100.0
-                    current_margin_enabled = current_margin_on if current_margin_on is not None else True
-                    current_snapshot = proposal_svc.find_best_params(
-                        values=values, dates=dates, metric_kind=metric_kind,
-                        n_range=[current_n],
-                        sigma_range=[current_k],
-                        margin_range=[current_margin],
-                    )
-                except Exception:
-                    current_snapshot = None
             st.session_state[cache_key] = result
-            st.session_state[f"{cache_key}_before"] = current_snapshot
 
     if cache_key in st.session_state:
         result = st.session_state[cache_key]
-        before = st.session_state.get(f"{cache_key}_before")
-        confidence = result["confidence"]
+        if not isinstance(result, CalibrationResult):
+            # Legado: se cache contem AutoTuneResult dict antigo, limpar e recalibrar
+            del st.session_state[cache_key]
+            return
+
+        confidence = result.confidence
         badge = _confidence_badge(confidence)
 
-        if result["viable"]:
-            st.success(
-                f"{badge} {result['recommendation']}"
-            )
+        if result.viable:
+            st.success(f"{badge} {result.recommendation}")
         else:
-            st.error(
-                f"{badge} {result['recommendation']}"
-            )
+            st.error(f"{badge} {result.recommendation}")
 
         # -- Metricas-chave em colunas --
-        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
+        m_c1, m_c2, m_c3 = st.columns(3)
         with m_c1:
-            cov_delta = None
-            if before and before.get("coverage_pct", 0) > 0:
-                cov_delta = f"{result['coverage_pct'] - before['coverage_pct']:+.1f}%"
             st.metric(
                 "Cobertura",
-                f"{result['coverage_pct']:.1f}%",
-                delta=cov_delta,
-                help="Porcentagem de periodos historicos que passariam na regra com os parametros sugeridos.",
+                f"{result.coverage_pct:.1f}%",
+                help="Porcentagem de periodos historicos que passariam na regra.",
             )
         with m_c2:
-            fp_delta = None
-            if before and "false_positives" in before:
-                fp_diff = result["false_positives"] - before["false_positives"]
-                if fp_diff != 0:
-                    fp_delta = f"{fp_diff:+d}"
             st.metric(
                 "Falsos Positivos",
-                f"~{result['false_positives']}",
-                delta=fp_delta,
+                f"~{result.false_positives}",
                 delta_color="inverse",
-                help="Estimativa de periodos normais que seriam reprovados indevidamente.",
+                help="Periodos normais que seriam reprovados indevidamente.",
             )
         with m_c3:
-            score_delta = None
-            if before and before.get("score_total", 0) > 0:
-                score_delta = f"{result['score_total'] - before['score_total']:+.4f}"
-            st.metric(
-                "Score Total",
-                f"{result['score_total']:.4f}",
-                delta=score_delta,
-                help="Score composto do grid search. Maior = melhor. "
-                     "Combina cobertura, FP, estabilidade, largura da banda e drift.",
-            )
-        with m_c4:
             st.metric(
                 "Confianca",
                 badge,
@@ -670,146 +643,62 @@ def _render_auto_tune(proposal_svc, values, dates, rule_key, metric_kind="numeri
         # -- Parametros recomendados --
         p_c1, p_c2, p_c3, p_c4 = st.columns(4)
         with p_c1:
-            st.caption(f"**N:** {result['n_periods']} periodos")
+            st.caption(f"**N:** {result.n_periods} periodos")
         with p_c2:
-            st.caption(f"**Sigma:** {result['n_sigma']}")
+            sigma_str = str(int(result.n_sigma)) if result.n_sigma == int(result.n_sigma) else f"{result.n_sigma:.1f}"
+            st.caption(f"**Sigma:** {sigma_str}")
         with p_c3:
-            st.caption(f"**Margem:** {result['margin_pct']*100:.0f}%")
+            st.caption(f"**Margem:** {result.margin_pct*100:.0f}%")
         with p_c4:
-            st.caption(f"**Margem:** {'ativada' if result['margin_enabled'] else 'desativada'}")
-
-        # -- Expander com detalhes do score e comparacao --
-        with st.expander("Detalhes do auto-tune", expanded=False):
-            # Score breakdown table
-            st.markdown("**Decomposicao do Score**")
-            st.caption(
-                "O score total e a soma dos componentes abaixo. "
-                "Valores positivos contribuem, negativos penalizam."
-            )
-
-            breakdown_items = [
-                ("Cobertura normal", result.get("normal_coverage", 0), "+", "pontos normais cobertos / total normais"),
-                ("Penalidade outliers", result.get("outlier_penalty", 0), "-", "outliers cobertos * 0.15"),
-                ("Penalidade FP", result.get("fp_penalty", 0), "-", "FP * 0.05"),
-                ("Bonus estabilidade", result.get("stability_bonus", 0), "+", "stability * 0.10"),
-                ("Penalidade largura", result.get("width_penalty", 0), "-", "(width_ratio - 0.20)^2 * 0.5"),
-                ("Bonus/penalidade drift", result.get("drift_bonus", 0), "+/-", "+0.05 sem drift, -0.05 com drift"),
-                ("Penalidade N curto", result.get("n_penalty", 0), "-", "0.05 se N < 15"),
-                ("Preferencia sigma", result.get("sigma_preference", 0), "-", "sigma * 0.02"),
-                ("Preferencia margem", result.get("margin_preference", 0), "-", "margem * 0.10"),
-                ("Bonus recencia", result.get("recency_bonus", 0), "+", "(weighted_cov - flat_cov)/100 * 0.10"),
-            ]
-
-            # Build markdown table
-            md_rows = ["| Componente | Valor | Sinal | Formula |", "|---|---|---|---|"]
-            for name, value, sign, formula in breakdown_items:
-                if sign == "-" and value > 0:
-                    md_rows.append(f"| {name} | :red[-{value:.4f}] | {sign} | `{formula}` |")
-                elif sign == "+/-":
-                    if value >= 0:
-                        md_rows.append(f"| {name} | :green[+{value:.4f}] | {sign} | `{formula}` |")
-                    else:
-                        md_rows.append(f"| {name} | :red[{value:.4f}] | {sign} | `{formula}` |")
-                else:
-                    md_rows.append(f"| {name} | :green[+{value:.4f}] | {sign} | `{formula}` |")
-            md_rows.append(f"| **Score Total** | **{result['score_total']:.4f}** | = | soma |")
-            st.markdown("\n".join(md_rows))
-
-            # Largura da banda
-            bwr = result.get("band_width_ratio", 0)
-            if bwr > 0:
-                st.caption(
-                    f"Largura relativa da banda: {bwr:.4f} "
-                    f"({'estreita' if bwr < 0.2 else 'moderada' if bwr < 0.5 else 'larga'}). "
-                    f"Penalidade quadratica quando > 0.20."
-                )
-            n_outliers = result.get("outliers_detected", 0)
-            if n_outliers > 0:
-                n_covered = result.get("outliers_covered", 0)
-                st.caption(
-                    f"Outliers detectados (IQR 2.5x): {n_outliers}, "
-                    f"excluidos da banda: {n_outliers - n_covered}."
-                )
+            st.caption(f"**Margem:** {'ativada' if result.margin_enabled else 'desativada'}")
+
+        # -- Expander com justificativas passo a passo --
+        with st.expander("Justificativa da calibracao", expanded=False):
+            for step in result.steps:
+                if step.step == 5:
+                    continue  # Relatorio consolidado nao precisa ser repetido
+                st.markdown(f"**Etapa {step.step}: {step.name}**")
+                st.caption(f"Decisao: {step.decision}")
+                st.caption(f"Justificativa: {step.justification}")
+
+                # Detalhes extras por etapa
+                if step.step == 2 and step.data.get("results_by_sigma"):
+                    results = step.data["results_by_sigma"]
+                    items = [f"sigma={s}: {c:.1%}" for s, c in sorted(results.items())]
+                    st.caption(f"Cobertura por sigma: {' | '.join(items)}")
+
+                if step.step == 3 and step.data.get("results_by_margin"):
+                    results = step.data["results_by_margin"]
+                    items = [f"margem={m:.0%}: {c:.1%}" for m, c in sorted(results.items())]
+                    st.caption(f"Cobertura por margem: {' | '.join(items)}")
+
+                st.caption("")  # spacer
 
             # Weighted coverage insight
-            weighted_cov = result.get("weighted_coverage_pct", 0)
-            flat_cov = result.get("coverage_pct", 0)
-            if abs(weighted_cov - flat_cov) > 1.0:
-                if weighted_cov > flat_cov:
+            if abs(result.weighted_coverage_pct - result.coverage_pct) > 1.0:
+                if result.weighted_coverage_pct > result.coverage_pct:
                     st.caption(
-                        f":green[Cobertura recente ({weighted_cov:.1f}%) e melhor que historica ({flat_cov:.1f}%).] "
-                        f"Os periodos mais recentes estao mais estaveis."
+                        f":green[Cobertura recente ({result.weighted_coverage_pct:.1f}%) melhor que historica ({result.coverage_pct:.1f}%).] "
+                        f"Periodos mais recentes estao mais estaveis."
                     )
                 else:
                     st.caption(
-                        f":orange[Cobertura recente ({weighted_cov:.1f}%) e pior que historica ({flat_cov:.1f}%).] "
-                        f"Os periodos mais recentes estao mais instaveis."
+                        f":orange[Cobertura recente ({result.weighted_coverage_pct:.1f}%) pior que historica ({result.coverage_pct:.1f}%).] "
+                        f"Periodos mais recentes estao mais instaveis."
                     )
 
-            # Comparacao antes vs depois
-            if before and before.get("score_total", 0) > 0:
-                st.divider()
-                st.markdown("**Comparacao: parametros atuais vs sugeridos**")
-
-                cmp_c1, cmp_c2 = st.columns(2)
-                with cmp_c1:
-                    st.markdown("**Antes** (parametros atuais)")
-                    st.caption(
-                        f"N={before['n_periods']}, "
-                        f"sigma={before['n_sigma']}, "
-                        f"margem={before['margin_pct']*100:.0f}%"
-                        f"{' (ativada)' if before['margin_enabled'] else ' (desativada)'}"
-                    )
-                    st.caption(
-                        f"Cobertura: {before['coverage_pct']:.1f}% | "
-                        f"FP: ~{before['false_positives']} | "
-                        f"Score: {before['score_total']:.4f}"
-                    )
-                with cmp_c2:
-                    st.markdown("**Depois** (parametros sugeridos)")
-                    st.caption(
-                        f"N={result['n_periods']}, "
-                        f"sigma={result['n_sigma']}, "
-                        f"margem={result['margin_pct']*100:.0f}%"
-                        f"{' (ativada)' if result['margin_enabled'] else ' (desativada)'}"
-                    )
-                    st.caption(
-                        f"Cobertura: {result['coverage_pct']:.1f}% | "
-                        f"FP: ~{result['false_positives']} | "
-                        f"Score: {result['score_total']:.4f}"
-                    )
-
-                # Highlight improvements
-                improvements = []
-                cov_diff = result["coverage_pct"] - before["coverage_pct"]
-                fp_diff = result["false_positives"] - before["false_positives"]
-                score_diff = result["score_total"] - before["score_total"]
-
-                if cov_diff > 0:
-                    improvements.append(f"cobertura +{cov_diff:.1f}pp")
-                if fp_diff < 0:
-                    improvements.append(f"FP {fp_diff:+d}")
-                if score_diff > 0:
-                    improvements.append(f"score +{score_diff:.4f}")
-
-                if improvements:
-                    st.caption(f"Ganhos: {', '.join(improvements)}")
-                elif score_diff == 0 and cov_diff == 0:
-                    st.caption("Os parametros atuais ja sao otimos para esta metrica.")
-
         # Botao para aplicar parametros sugeridos nos sliders.
-        # Armazena em _pending_autotune para aplicar ANTES dos widgets no proximo rerun.
-        if result["viable"] and st.button(
+        if result.viable and st.button(
             "Aplicar parametros sugeridos",
             key=f"apply_autotune_{rule_key}",
             help="Atualiza os sliders com os parametros recomendados.",
         ):
             st.session_state["_pending_autotune"] = {
                 "rule_key": rule_key,
-                "n_periods": result["n_periods"],
-                "n_sigma": result["n_sigma"],
-                "margin_pct": int(result["margin_pct"] * 100),
-                "margin_enabled": result["margin_enabled"],
+                "n_periods": result.n_periods,
+                "n_sigma": result.n_sigma,
+                "margin_pct": int(result.margin_pct * 100),
+                "margin_enabled": result.margin_enabled,
             }
             st.rerun()
 
@@ -979,6 +868,7 @@ proposal_svc = _get_proposal_service()
 proposal_svc.set_grain_policy(dataset_config.grain_policy)
 
 _grain_policy = dataset_config.grain_policy
+_grain_type = dataset_config.grain_type
 
 config_dict = {
     "schema": dataset_config.schema,
@@ -1274,9 +1164,9 @@ if _has_details:
 # ---------------------------------------------------------------------------
 
 if numeric_profiles:
-    with st.expander("Calibracao em lote (auto-tune)", expanded=False):
+    with st.expander("Calibracao em lote", expanded=False):
         st.caption(
-            "Executa auto-tune em todas as colunas numericas e adiciona "
+            "Calibra todas as colunas numericas e adiciona "
             "regras de alta confianca ao carrinho automaticamente."
         )
 
@@ -1288,7 +1178,7 @@ if numeric_profiles:
             help="HIGH: apenas regras muito confiaveis. MEDIUM: inclui regras que precisam revisao.",
         )
 
-        if st.button("Auto-calibrar todas", key="btn_batch_calibrate_top", type="primary"):
+        if st.button("Calibrar todas", key="btn_batch_calibrate_top", type="primary"):
             _batch_cols = [p.column_name for p in numeric_profiles]
             if not _batch_cols:
                 st.warning("Nenhuma coluna numerica encontrada.")
@@ -1299,7 +1189,7 @@ if numeric_profiles:
                 for _bi, _bc in enumerate(_batch_cols):
                     _batch_progress.progress(
                         (_bi + 1) / len(_batch_cols),
-                        text=f"Analisando {_bc} ({_bi + 1}/{len(_batch_cols)})...",
+                        text=f"Calibrando {_bc} ({_bi + 1}/{len(_batch_cols)})...",
                     )
                     try:
                         _bh = fetch_numeric_history(config_dict, _bc)
@@ -1309,24 +1199,22 @@ if numeric_profiles:
 
                         _bvals = _bh["mean"].tolist()
                         _bdates = _bh["period"].astype(str).tolist()
-                        _b_n_range = [n for n in _grain_policy.n_range if n <= len(_bvals) - _grain_policy.min_history]
-                        _bbest = proposal_svc.find_best_params(
+                        _bbest = calibrate(
                             values=_bvals, dates=_bdates,
-                            n_range=_b_n_range or [_grain_policy.slider_n_min],
+                            grain=_grain_type,
                             seasonality_enabled=_grain_policy.seasonality_enabled,
-                            n_penalty_threshold=_grain_policy.n_penalty_threshold,
                         )
 
-                        if _bbest["confidence"].value == "LOW":
+                        if _bbest.confidence == ConfidenceLevel.LOW:
                             _batch_results.append({"column": _bc, "status": "skip", "reason": "confianca LOW"})
                             continue
-                        if _batch_min == "HIGH" and _bbest["confidence"] != ConfidenceLevel.HIGH:
-                            _batch_results.append({"column": _bc, "status": "skip", "reason": f"confianca {_bbest['confidence'].value}"})
+                        if _batch_min == "HIGH" and _bbest.confidence != ConfidenceLevel.HIGH:
+                            _batch_results.append({"column": _bc, "status": "skip", "reason": f"confianca {_bbest.confidence.value}"})
                             continue
 
                         _bbl = BaselineStrategy(
-                            n_periods=_bbest["n_periods"], n_sigma=_bbest["n_sigma"],
-                            margin_pct=_bbest["margin_pct"], margin_enabled=_bbest["margin_enabled"],
+                            n_periods=_bbest.n_periods, n_sigma=_bbest.n_sigma,
+                            margin_pct=_bbest.margin_pct, margin_enabled=_bbest.margin_enabled,
                             min_history_points=_grain_policy.min_history,
                         )
                         _bprops = proposal_svc.propose_numeric_rules(
@@ -1350,9 +1238,9 @@ if numeric_profiles:
                         st.session_state["rule_cart"] = _bcart
                         _batch_results.append({
                             "column": _bc, "status": "added" if _badded > 0 else "exists",
-                            "confidence": _bbest["confidence"].value,
-                            "coverage": _bbest["coverage_pct"],
-                            "n": _bbest["n_periods"], "sigma": _bbest["n_sigma"],
+                            "confidence": _bbest.confidence.value,
+                            "coverage": _bbest.coverage_pct,
+                            "n": _bbest.n_periods, "sigma": _bbest.n_sigma,
                             "added": _badded,
                         })
                     except Exception as e:
@@ -1439,41 +1327,37 @@ with tab_numericas:
             # Show regime badge
             _render_regime_panel(series_profile)
 
-            # Auto-tune automatico na primeira visita a coluna
+            # Calibracao automatica na primeira visita a coluna
             _at_key = f"autotune_{_fp}_mean_{selected_col}"
             _at_min = _grain_policy.min_history + 1  # precisa de min_history + pelo menos 1 ponto
             if _at_key not in st.session_state and _mean_vals and len(_mean_vals) >= _at_min:
-                _at_n_range = [n for n in _grain_policy.n_range if n <= len(_mean_vals) - _grain_policy.min_history]
-                with st.spinner(f"Auto-tune {selected_col}..."):
-                    _at_result = proposal_svc.find_best_params(
+                with st.spinner(f"Calibrando {selected_col}..."):
+                    _at_result = calibrate(
                         values=_mean_vals, dates=_mean_dates,
-                        n_range=_at_n_range or [_grain_policy.slider_n_min],
+                        grain=_grain_type,
                         seasonality_enabled=_grain_policy.seasonality_enabled,
-                        n_penalty_threshold=_grain_policy.n_penalty_threshold,
+                        profile=series_profile,
                     )
                     st.session_state[_at_key] = _at_result
-                    if _at_result["viable"]:
+                    if _at_result.viable:
                         _rk = f"{_fp}_mean_{selected_col}"
-                        st.session_state[f"n_{_rk}"] = _at_result["n_periods"]
-                        st.session_state[f"k_{_rk}"] = _at_result["n_sigma"]
-                        st.session_state[f"margin_{_rk}"] = int(_at_result["margin_pct"] * 100)
-                        st.session_state[f"margin_on_{_rk}"] = _at_result["margin_enabled"]
+                        st.session_state[f"n_{_rk}"] = _at_result.n_periods
+                        st.session_state[f"k_{_rk}"] = _at_result.n_sigma
+                        st.session_state[f"margin_{_rk}"] = int(_at_result.margin_pct * 100)
+                        st.session_state[f"margin_on_{_rk}"] = _at_result.margin_enabled
                         # Tambem aplicar ao StdDev
                         _rk_std = f"{_fp}_stddev_{selected_col}"
-                        st.session_state[f"n_{_rk_std}"] = _at_result["n_periods"]
-                        st.session_state[f"k_{_rk_std}"] = _at_result["n_sigma"]
-                        st.session_state[f"margin_{_rk_std}"] = int(_at_result["margin_pct"] * 100)
-                        st.session_state[f"margin_on_{_rk_std}"] = _at_result["margin_enabled"]
+                        st.session_state[f"n_{_rk_std}"] = _at_result.n_periods
+                        st.session_state[f"k_{_rk_std}"] = _at_result.n_sigma
+                        st.session_state[f"margin_{_rk_std}"] = int(_at_result.margin_pct * 100)
+                        st.session_state[f"margin_on_{_rk_std}"] = _at_result.margin_enabled
                     st.rerun()
 
             _at_cached = st.session_state.get(_at_key)
-            if _at_cached and _at_cached.get("viable"):
+            if _at_cached and isinstance(_at_cached, CalibrationResult) and _at_cached.viable:
                 st.caption(
-                    f"Parametros sugeridos pelo auto-tune: "
-                    f"N={_at_cached['n_periods']}, sigma={_at_cached['n_sigma']}, "
-                    f"margem={_at_cached['margin_pct']*100:.0f}% — "
-                    f"cobertura {_at_cached['coverage_pct']:.0f}%, "
-                    f"{_confidence_badge(_at_cached['confidence'])}"
+                    f"Calibracao automatica: {explain_calibration_short(_at_cached)} — "
+                    f"{_confidence_badge(_at_cached.confidence)}"
                 )
 
             # ---- Mean ----
@@ -1531,12 +1415,13 @@ with tab_numericas:
                     # Diagnostics panel (seasonality, change-point, outliers, recency)
                     _render_diagnostics_panel(proposal)
 
-                    _render_auto_tune(
+                    _render_calibration(
                         proposal_svc, values, dates,
                         f"{_fp}_mean_{selected_col}", metric_kind="numeric",
+                        grain=_grain_type, series_profile=series_profile,
                     )
 
-                # Metricas do backtest (ocultar se auto-tune ja exibe metricas)
+                # Metricas do backtest (ocultar se calibracao ja exibe metricas)
                 if f"autotune_{_fp}_mean_{selected_col}" not in st.session_state:
                     _render_backtest_metrics(proposal)
                 _render_add_to_cart(
@@ -1591,9 +1476,10 @@ with tab_numericas:
                     # Diagnostics panel (outliers, recency — seasonality/change-point already shown in Mean)
                     _render_diagnostics_panel(proposal)
 
-                    _render_auto_tune(
+                    _render_calibration(
                         proposal_svc, values, dates,
                         f"{_fp}_stddev_{selected_col}", metric_kind="numeric",
+                        grain=_grain_type, series_profile=series_profile,
                     )
 
                 if f"autotune_{_fp}_stddev_{selected_col}" not in st.session_state:
@@ -2259,33 +2145,29 @@ with tab_tabela:
         _rc_vals = rc_history_df["row_count"].tolist() if "row_count" in rc_history_df.columns else []
         _rc_dates = rc_history_df["period"].astype(str).tolist() if "period" in rc_history_df.columns else []
 
-        # Auto-tune automatico para RowCount
+        # Calibracao automatica para RowCount
         _at_rc_key = f"autotune_{_fp}_rowcount"
         _at_rc_min = _grain_policy.min_history + 1
         if _at_rc_key not in st.session_state and _rc_vals and len(_rc_vals) >= _at_rc_min:
-            _at_rc_n_range = [n for n in _grain_policy.n_range if n <= len(_rc_vals) - _grain_policy.min_history]
-            with st.spinner("Auto-tune RowCount..."):
-                _at_rc = proposal_svc.find_best_params(
+            with st.spinner("Calibrando RowCount..."):
+                _at_rc = calibrate(
                     values=_rc_vals, dates=_rc_dates,
-                    n_range=_at_rc_n_range or [_grain_policy.slider_n_min],
+                    grain=_grain_type,
                     seasonality_enabled=_grain_policy.seasonality_enabled,
-                    n_penalty_threshold=_grain_policy.n_penalty_threshold,
                 )
                 st.session_state[_at_rc_key] = _at_rc
-                if _at_rc["viable"]:
-                    st.session_state[f"n_{_fp}_rowcount"] = _at_rc["n_periods"]
-                    st.session_state[f"k_{_fp}_rowcount"] = _at_rc["n_sigma"]
-                    st.session_state[f"margin_{_fp}_rowcount"] = int(_at_rc["margin_pct"] * 100)
-                    st.session_state[f"margin_on_{_fp}_rowcount"] = _at_rc["margin_enabled"]
+                if _at_rc.viable:
+                    st.session_state[f"n_{_fp}_rowcount"] = _at_rc.n_periods
+                    st.session_state[f"k_{_fp}_rowcount"] = _at_rc.n_sigma
+                    st.session_state[f"margin_{_fp}_rowcount"] = int(_at_rc.margin_pct * 100)
+                    st.session_state[f"margin_on_{_fp}_rowcount"] = _at_rc.margin_enabled
                 st.rerun()
 
         _at_rc_cached = st.session_state.get(_at_rc_key)
-        if _at_rc_cached and _at_rc_cached.get("viable"):
+        if _at_rc_cached and isinstance(_at_rc_cached, CalibrationResult) and _at_rc_cached.viable:
             st.caption(
-                f"Auto-tune: N={_at_rc_cached['n_periods']}, sigma={_at_rc_cached['n_sigma']}, "
-                f"margem={_at_rc_cached['margin_pct']*100:.0f}% — "
-                f"cobertura {_at_rc_cached['coverage_pct']:.0f}%, "
-                f"{_confidence_badge(_at_rc_cached['confidence'])}"
+                f"Calibracao automatica: {explain_calibration_short(_at_rc_cached)} — "
+                f"{_confidence_badge(_at_rc_cached.confidence)}"
             )
         rc_n, rc_k, rc_margin, rc_buffer, rc_margin_on = _render_rule_params(
             f"{_fp}_rowcount",
@@ -2328,9 +2210,10 @@ with tab_tabela:
                     values, dates, rc_n, rc_k, rc_margin, "Row Count",
                     margin_enabled=rc_margin_on,
                 )
-                _render_auto_tune(
+                _render_calibration(
                     proposal_svc, values, dates,
                     f"{_fp}_rowcount", metric_kind="numeric",
+                    grain=_grain_type, series_profile=rc_series_profile,
                 )
 
             if "autotune_rowcount" not in st.session_state:
diff --git a/services/proposal_service.py b/services/proposal_service.py
index 7ef05b1..c83193b 100644
--- a/services/proposal_service.py
+++ b/services/proposal_service.py
@@ -1373,6 +1373,50 @@ class ProposalService:
         best["recommendation"] = recommendation
         return best
 
+    def calibrate_params(
+        self,
+        values: list[float],
+        dates: list[str],
+        metric_kind: str = "numeric",
+        grain: "GrainType | None" = None,
+        seasonality_enabled: bool = True,
+        profile: "SeriesProfile | None" = None,
+    ) -> "CalibrationResult":
+        """Calibracao explicavel de parametros (substitui find_best_params).
+
+        Executa logica sequencial em 5 etapas:
+        1. Escolher N baseado no grao e dados disponiveis
+        2. Testar sigma sozinho — se suficiente, sem margem
+        3. Adicionar margem somente se necessario
+        4. Validar com backtest e ajustar FPs recentes
+        5. Gerar relatorio de justificativa
+
+        Args:
+            values: Serie temporal de valores.
+            dates: Datas correspondentes.
+            metric_kind: "numeric" ou "frequency".
+            grain: Granularidade (daily/monthly). Default: daily.
+            seasonality_enabled: Se deve considerar sazonalidade.
+            profile: Perfil de regime pre-computado (opcional).
+
+        Returns:
+            CalibrationResult com parametros, justificativas e backtest.
+        """
+        from core.calibration_advisor import calibrate
+        from core.models.enums import GrainType
+
+        if grain is None:
+            grain = GrainType.DAILY
+
+        return calibrate(
+            values=values,
+            dates=dates,
+            grain=grain,
+            metric_kind=metric_kind,
+            seasonality_enabled=seasonality_enabled,
+            profile=profile,
+        )
+
     def _build_completeness_proposal(
         self,
         history: pd.DataFrame,
diff --git a/tests/test_calibration_advisor.py b/tests/test_calibration_advisor.py
new file mode 100644
index 0000000..e27f6c5
--- /dev/null
+++ b/tests/test_calibration_advisor.py
@@ -0,0 +1,560 @@
+"""
+Testes do Assistente de Calibracao (core/calibration_advisor.py).
+
+Cobre as 5 etapas, o orquestrador calibrate(), e o explainer.
+"""
+
+import math
+
+import pytest
+
+from core.calibration_advisor import (
+    MARGIN_CANDIDATES,
+    SIGMA_CANDIDATES,
+    SIGMA_SUFFICIENT_THRESHOLD,
+    CalibrationResult,
+    CalibrationStep,
+    _compute_outlier_mask,
+    _normal_coverage,
+    _recent_fps,
+    add_margin_if_needed,
+    calibrate,
+    choose_n,
+    generate_report,
+    find_best_sigma,
+    validate_with_backtest,
+)
+from core.calibration_explainer import (
+    explain_calibration,
+    explain_calibration_short,
+    explain_step_detail,
+)
+from core.models.enums import ConfidenceLevel, GrainType, SeriesRegime
+from core.models.series_profile import SeriesProfile
+
+
+# ---------------------------------------------------------------------------
+# Fixtures
+# ---------------------------------------------------------------------------
+
+def _stable_series(n: int = 60, mean: float = 100.0, std: float = 5.0) -> tuple[list[float], list[str]]:
+    """Gera serie estavel (baixa variacao, sem outliers)."""
+    import random
+    random.seed(42)
+    values = [mean + random.gauss(0, std) for _ in range(n)]
+    dates = [f"2026-01-{i+1:02d}" for i in range(n)]
+    return values, dates
+
+
+def _volatile_series(n: int = 60) -> tuple[list[float], list[str]]:
+    """Gera serie volatil (CV > 30%)."""
+    import random
+    random.seed(42)
+    values = [100 + random.gauss(0, 50) for _ in range(n)]
+    dates = [f"2026-01-{i+1:02d}" for i in range(n)]
+    return values, dates
+
+
+def _series_with_outliers(n: int = 60) -> tuple[list[float], list[str]]:
+    """Gera serie estavel com 3 outliers."""
+    values, dates = _stable_series(n)
+    values[10] = 300.0  # outlier alto
+    values[25] = -100.0  # outlier baixo
+    values[40] = 250.0  # outlier alto
+    return values, dates
+
+
+def _short_series() -> tuple[list[float], list[str]]:
+    """Gera serie curta (10 pontos)."""
+    return _stable_series(n=10)
+
+
+def _series_with_structural_break(n: int = 60) -> tuple[list[float], list[str]]:
+    """Gera serie com mudanca de patamar no meio."""
+    import random
+    random.seed(42)
+    # Primeira metade: media 100
+    values1 = [100 + random.gauss(0, 3) for _ in range(n // 2)]
+    # Segunda metade: media 200
+    values2 = [200 + random.gauss(0, 3) for _ in range(n // 2)]
+    values = values1 + values2
+    dates = [f"2026-01-{i+1:02d}" for i in range(n)]
+    return values, dates
+
+
+def _asymmetric_series(n: int = 60) -> tuple[list[float], list[str]]:
+    """Gera serie assimetrica (muitos valores baixos, poucos altos)."""
+    import random
+    random.seed(42)
+    # Distribuicao log-normal (assimetrica para direita)
+    values = [math.exp(random.gauss(4.0, 0.5)) for _ in range(n)]
+    dates = [f"2026-01-{i+1:02d}" for i in range(n)]
+    return values, dates
+
+
+def _insufficient_series() -> tuple[list[float], list[str]]:
+    """Gera serie com menos de 5 pontos."""
+    return [1.0, 2.0, 3.0], ["2026-01-01", "2026-01-02", "2026-01-03"]
+
+
+# ---------------------------------------------------------------------------
+# Test CalibrationStep / CalibrationResult dataclasses
+# ---------------------------------------------------------------------------
+
+class TestDataclasses:
+    def test_calibration_step_fields(self):
+        step = CalibrationStep(
+            step=1, name="test", decision="N=30", justification="default",
+        )
+        assert step.step == 1
+        assert step.data == {}
+
+    def test_calibration_result_fields(self):
+        result = CalibrationResult(
+            n_periods=30, n_sigma=2.5, margin_pct=0.0, margin_enabled=False,
+            coverage_pct=95.0, weighted_coverage_pct=96.0,
+            false_positives=0, stability=0.9,
+            confidence=ConfidenceLevel.HIGH, viable=True,
+        )
+        assert result.n_periods == 30
+        assert result.n_sigma == 2.5
+        assert result.margin_enabled is False
+        assert result.steps == []
+        assert result.profile is None
+
+
+# ---------------------------------------------------------------------------
+# Test Etapa 1: choose_n
+# ---------------------------------------------------------------------------
+
+class TestChooseN:
+    def test_daily_default_n_30(self):
+        values, dates = _stable_series(90)
+        step = choose_n(values, dates, grain=GrainType.DAILY)
+        assert step.data["n_periods"] == 30
+        assert step.step == 1
+
+    def test_monthly_default_n_12(self):
+        values, dates = _stable_series(36)
+        step = choose_n(values, dates, grain=GrainType.MONTHLY)
+        assert step.data["n_periods"] == 12
+
+    def test_short_series_reduces_n(self):
+        values, dates = _stable_series(20)
+        step = choose_n(values, dates, grain=GrainType.DAILY)
+        # 20 pontos < 2*30, deveria reduzir
+        assert step.data["n_periods"] == 10  # 20 // 2
+        assert "serie curta" in step.justification
+
+    def test_very_short_series_n_minimum_5(self):
+        values, dates = _stable_series(8)
+        step = choose_n(values, dates, grain=GrainType.DAILY)
+        assert step.data["n_periods"] == 5  # min(8//2, ...) mas floor é 5
+
+    def test_seasonal_prefers_multiple_of_7(self):
+        values, dates = _stable_series(90)
+        profile = SeriesProfile(
+            regime=SeriesRegime.SEASONAL,
+            is_seasonal=True,
+            seasonality_strength=0.25,
+            n_points=90, n_valid=90,
+        )
+        step = choose_n(values, dates, grain=GrainType.DAILY, profile=profile)
+        assert step.data["n_periods"] % 7 == 0
+        assert "multiplo de 7" in step.justification
+
+    def test_structural_break_limits_n(self):
+        values, dates = _series_with_structural_break(60)
+        profile = SeriesProfile(
+            regime=SeriesRegime.STRUCTURAL_BREAK,
+            has_structural_break=True,
+            change_point_date="2026-01-31",
+            n_points=60, n_valid=60,
+        )
+        step = choose_n(values, dates, grain=GrainType.DAILY, profile=profile)
+        # N deve ser limitado aos dados pos-mudanca
+        assert step.data["n_periods"] <= 30
+
+    def test_returns_calibration_step(self):
+        values, dates = _stable_series()
+        step = choose_n(values, dates)
+        assert isinstance(step, CalibrationStep)
+        assert step.name == "Escolha de N (janela)"
+        assert "n_periods" in step.data
+
+
+# ---------------------------------------------------------------------------
+# Test Etapa 2: find_best_sigma
+# ---------------------------------------------------------------------------
+
+class TestSigmaAlone:
+    def test_stable_series_sigma_sufficient(self):
+        values, dates = _stable_series(90)
+        outliers = _compute_outlier_mask(values)
+        step = find_best_sigma(values, dates, n_periods=30, outlier_indices=outliers)
+        assert step.data["sigma_sufficient"] is True
+        assert step.data["coverage"] >= SIGMA_SUFFICIENT_THRESHOLD
+        assert "suficiente sem margem" in step.decision
+
+    def test_prefers_smaller_sigma(self):
+        """Quando sigma_sufficient, deve escolher o menor sigma que atinge threshold."""
+        values, dates = _stable_series(90, std=2.0)
+        outliers = _compute_outlier_mask(values)
+        step = find_best_sigma(values, dates, n_periods=30, outlier_indices=outliers)
+        # Se encontrou sigma suficiente, deve ser o menor possivel
+        if step.data["sigma_sufficient"]:
+            results = step.data["results_by_sigma"]
+            for sigma in sorted(results.keys()):
+                if results[sigma] >= SIGMA_SUFFICIENT_THRESHOLD:
+                    assert step.data["sigma"] == sigma
+                    break
+
+    def test_volatile_series_sigma_insufficient(self):
+        values, dates = _volatile_series(90)
+        outliers = _compute_outlier_mask(values)
+        step = find_best_sigma(values, dates, n_periods=30, outlier_indices=outliers)
+        # Volatil pode nao atingir threshold
+        assert "results_by_sigma" in step.data
+        assert step.step == 2
+
+    def test_returns_results_by_sigma(self):
+        values, dates = _stable_series(90)
+        outliers = _compute_outlier_mask(values)
+        step = find_best_sigma(values, dates, n_periods=30, outlier_indices=outliers)
+        results = step.data["results_by_sigma"]
+        assert len(results) >= 1
+        # Cobertura deve crescer com sigma
+        sigmas = sorted(results.keys())
+        if len(sigmas) >= 2:
+            assert results[sigmas[-1]] >= results[sigmas[0]]
+
+    def test_frequency_metric_kind(self):
+        # Percentages 0-100
+        import random
+        random.seed(42)
+        values = [30 + random.gauss(0, 2) for _ in range(90)]
+        dates = [f"2026-01-{i+1:02d}" for i in range(90)]
+        outliers = _compute_outlier_mask(values)
+        step = find_best_sigma(
+            values, dates, n_periods=30, outlier_indices=outliers,
+            metric_kind="frequency",
+        )
+        assert step.data["sigma"] in SIGMA_CANDIDATES
+
+
+# ---------------------------------------------------------------------------
+# Test Etapa 3: add_margin_if_needed
+# ---------------------------------------------------------------------------
+
+class TestMargin:
+    def test_sigma_sufficient_skips_margin(self):
+        values, dates = _stable_series(90)
+        outliers = _compute_outlier_mask(values)
+        step = add_margin_if_needed(
+            values, dates, n_periods=30, sigma=2.5,
+            sigma_sufficient=True, outlier_indices=outliers,
+        )
+        assert step.data["margin_enabled"] is False
+        assert step.data["margin_pct"] == 0.0
+        assert "desativada" in step.decision
+
+    def test_sigma_insufficient_adds_margin(self):
+        values, dates = _volatile_series(90)
+        outliers = _compute_outlier_mask(values)
+        step = add_margin_if_needed(
+            values, dates, n_periods=30, sigma=2.0,
+            sigma_sufficient=False, outlier_indices=outliers,
+        )
+        assert step.data["margin_enabled"] is True
+        assert step.data["margin_pct"] > 0
+        assert step.data["margin_pct"] in MARGIN_CANDIDATES
+
+    def test_prefers_smaller_margin(self):
+        """Escolhe a menor margem que atinge cobertura suficiente."""
+        values, dates = _stable_series(90)
+        outliers = _compute_outlier_mask(values)
+        step = add_margin_if_needed(
+            values, dates, n_periods=30, sigma=2.0,
+            sigma_sufficient=False, outlier_indices=outliers,
+        )
+        if step.data.get("results_by_margin"):
+            # Se 5% basta, nao deve escolher 10%
+            for margin, cov in sorted(step.data["results_by_margin"].items()):
+                if cov >= SIGMA_SUFFICIENT_THRESHOLD:
+                    assert step.data["margin_pct"] <= margin
+                    break
+
+
+# ---------------------------------------------------------------------------
+# Test Etapa 4: validate_with_backtest
+# ---------------------------------------------------------------------------
+
+class TestValidation:
+    def test_stable_series_validates(self):
+        values, dates = _stable_series(90)
+        outliers = _compute_outlier_mask(values)
+        step = validate_with_backtest(
+            values, dates, n_periods=30, sigma=2.5,
+            margin_pct=0.0, margin_enabled=False,
+            outlier_indices=outliers,
+        )
+        bt = step.data["backtest"]
+        assert bt is not None
+        assert bt.coverage_pct > 0
+        assert "Parametros validados" in step.justification or "FP" in step.justification
+
+    def test_adjusts_when_recent_fps(self):
+        """Se ha FPs recentes, tenta relaxar parametros."""
+        # Serie com mudanca recente que causa FP
+        import random
+        random.seed(42)
+        values = [100 + random.gauss(0, 3) for _ in range(85)]
+        # Ultimos 5 pontos: ligeiramente fora da banda estreita
+        values.extend([100 + 15 * ((-1)**i) for i in range(5)])
+        dates = [f"2026-01-{i+1:02d}" for i in range(90)]
+
+        outliers = _compute_outlier_mask(values)
+        step = validate_with_backtest(
+            values, dates, n_periods=30, sigma=2.0,
+            margin_pct=0.0, margin_enabled=False,
+            outlier_indices=outliers,
+        )
+        # Pode ter sido ajustado ou nao, mas deve ter tentado
+        assert step.step == 4
+        assert "backtest" in step.data
+
+    def test_backtest_failure_handled(self):
+        """Backtest com dados invalidos nao quebra."""
+        step = validate_with_backtest(
+            values=[], dates=[], n_periods=30, sigma=2.5,
+            margin_pct=0.0, margin_enabled=False,
+            outlier_indices=set(),
+        )
+        assert "falha" in step.decision or step.data.get("backtest") is not None
+
+
+# ---------------------------------------------------------------------------
+# Test Etapa 5: generate_report
+# ---------------------------------------------------------------------------
+
+class TestReport:
+    def test_report_includes_steps(self):
+        steps = [
+            CalibrationStep(step=1, name="N", decision="N=30", justification="default"),
+            CalibrationStep(step=2, name="Sigma", decision="sigma=2.5", justification="suficiente"),
+        ]
+        report = generate_report(steps)
+        assert "N=30" in report.justification
+        assert "sigma=2.5" in report.justification
+
+    def test_report_includes_regime(self):
+        profile = SeriesProfile(
+            regime=SeriesRegime.VOLATILE,
+            is_volatile=True, cv=0.45,
+            n_points=60, n_valid=60,
+        )
+        report = generate_report([], profile=profile)
+        assert "volatile" in report.justification.lower()
+
+
+# ---------------------------------------------------------------------------
+# Test Orquestrador: calibrate()
+# ---------------------------------------------------------------------------
+
+class TestCalibrate:
+    def test_stable_series_high_confidence(self):
+        values, dates = _stable_series(90)
+        result = calibrate(values, dates, grain=GrainType.DAILY)
+        assert isinstance(result, CalibrationResult)
+        assert result.viable is True
+        assert result.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
+        assert result.coverage_pct >= 70.0
+        assert len(result.steps) == 5
+
+    def test_stable_series_no_margin(self):
+        """Serie estavel deve usar sigma sem margem."""
+        values, dates = _stable_series(90, std=3.0)
+        result = calibrate(values, dates, grain=GrainType.DAILY)
+        assert result.margin_enabled is False
+        assert result.margin_pct == 0.0
+        assert "sem margem" in result.recommendation or "suficiente" in result.recommendation
+
+    def test_insufficient_data_returns_not_viable(self):
+        values, dates = _insufficient_series()
+        result = calibrate(values, dates)
+        assert result.viable is False
+        assert result.confidence == ConfidenceLevel.LOW
+        assert "insuficientes" in result.recommendation.lower()
+
+    def test_monthly_grain_uses_n_12(self):
+        values, dates = _stable_series(36)
+        result = calibrate(values, dates, grain=GrainType.MONTHLY, seasonality_enabled=False)
+        assert result.n_periods <= 12
+
+    def test_result_has_all_fields(self):
+        values, dates = _stable_series(90)
+        result = calibrate(values, dates)
+        assert result.n_periods > 0
+        assert result.n_sigma > 0
+        assert result.coverage_pct >= 0
+        assert result.weighted_coverage_pct >= 0
+        assert result.false_positives >= 0
+        assert result.stability >= 0
+        assert isinstance(result.confidence, ConfidenceLevel)
+        assert isinstance(result.viable, bool)
+        assert len(result.recommendation) > 0
+
+    def test_result_has_profile(self):
+        values, dates = _stable_series(90)
+        result = calibrate(values, dates)
+        assert result.profile is not None
+        assert isinstance(result.profile, SeriesProfile)
+
+    def test_preexisting_profile_reused(self):
+        values, dates = _stable_series(90)
+        profile = SeriesProfile(
+            regime=SeriesRegime.STABLE, n_points=90, n_valid=90,
+        )
+        result = calibrate(values, dates, profile=profile)
+        assert result.profile is profile
+
+    def test_frequency_metric_kind(self):
+        import random
+        random.seed(42)
+        values = [30 + random.gauss(0, 2) for _ in range(90)]
+        dates = [f"2026-01-{i+1:02d}" for i in range(90)]
+        result = calibrate(values, dates, metric_kind="frequency")
+        assert result.viable is True
+        assert result.coverage_pct > 0
+
+    def test_volatile_series_may_add_margin(self):
+        values, dates = _volatile_series(90)
+        result = calibrate(values, dates)
+        # Volatil pode ou nao precisar de margem, mas deve completar
+        assert result.n_periods > 0
+        assert result.n_sigma > 0
+        assert len(result.steps) == 5
+
+    def test_steps_sequential(self):
+        values, dates = _stable_series(90)
+        result = calibrate(values, dates)
+        step_numbers = [s.step for s in result.steps]
+        assert step_numbers == [1, 2, 3, 4, 5]
+
+    def test_each_step_has_justification(self):
+        values, dates = _stable_series(90)
+        result = calibrate(values, dates)
+        for step in result.steps:
+            assert len(step.justification) > 0
+            assert len(step.decision) > 0
+            assert len(step.name) > 0
+
+
+# ---------------------------------------------------------------------------
+# Test Helpers
+# ---------------------------------------------------------------------------
+
+class TestHelpers:
+    def test_compute_outlier_mask_empty(self):
+        assert _compute_outlier_mask([]) == set()
+
+    def test_compute_outlier_mask_no_outliers(self):
+        values, _ = _stable_series(60)
+        mask = _compute_outlier_mask(values)
+        # Stable series should have very few outliers
+        assert len(mask) <= 3
+
+    def test_compute_outlier_mask_finds_outliers(self):
+        values, _ = _series_with_outliers(60)
+        mask = _compute_outlier_mask(values)
+        # Should detect the injected outliers at indices 10, 25, 40
+        assert 10 in mask or 25 in mask or 40 in mask
+
+    def test_compute_outlier_mask_handles_nans(self):
+        values = [1.0, 2.0, None, float('nan'), 3.0, 4.0, 5.0, 6.0]
+        mask = _compute_outlier_mask(values)
+        assert isinstance(mask, set)
+
+    def test_compute_outlier_mask_short_list(self):
+        mask = _compute_outlier_mask([1.0, 2.0, 3.0])
+        assert mask == set()
+
+
+# ---------------------------------------------------------------------------
+# Test Explainer
+# ---------------------------------------------------------------------------
+
+class TestExplainer:
+    def test_explain_calibration_full(self):
+        values, dates = _stable_series(90)
+        result = calibrate(values, dates)
+        text = explain_calibration(result)
+        assert "Assistente de Calibracao" in text
+        assert "Etapa 1" in text
+        assert "Etapa 2" in text
+        assert "Etapa 3" in text
+        assert "Etapa 4" in text
+        assert "Resultado:" in text
+
+    def test_explain_calibration_includes_regime(self):
+        values, dates = _volatile_series(90)
+        result = calibrate(values, dates)
+        text = explain_calibration(result)
+        assert "Regime" in text
+
+    def test_explain_calibration_short(self):
+        values, dates = _stable_series(90)
+        result = calibrate(values, dates)
+        text = explain_calibration_short(result)
+        assert "N=" in text
+        assert "σ=" in text
+        assert "cobertura" in text
+        assert len(text) < 200  # deve ser curto
+
+    def test_explain_step_detail_sigma(self):
+        values, dates = _stable_series(90)
+        outliers = _compute_outlier_mask(values)
+        step = find_best_sigma(values, dates, n_periods=30, outlier_indices=outliers)
+        text = explain_step_detail(step)
+        assert "sigma" in text.lower()
+
+    def test_explain_step_detail_margin(self):
+        values, dates = _stable_series(90)
+        outliers = _compute_outlier_mask(values)
+        step = add_margin_if_needed(
+            values, dates, n_periods=30, sigma=2.0,
+            sigma_sufficient=False, outlier_indices=outliers,
+        )
+        text = explain_step_detail(step)
+        assert "margem" in text.lower()
+
+
+# ---------------------------------------------------------------------------
+# Test ProposalService.calibrate_params integration
+# ---------------------------------------------------------------------------
+
+class TestProposalServiceIntegration:
+    def test_calibrate_params_returns_calibration_result(self):
+        from services.proposal_service import ProposalService
+        svc = ProposalService()
+        values, dates = _stable_series(90)
+        result = svc.calibrate_params(values, dates)
+        assert isinstance(result, CalibrationResult)
+        assert result.viable is True
+
+    def test_calibrate_params_with_grain(self):
+        from services.proposal_service import ProposalService
+        svc = ProposalService()
+        values, dates = _stable_series(36)
+        result = svc.calibrate_params(
+            values, dates, grain=GrainType.MONTHLY, seasonality_enabled=False,
+        )
+        assert result.n_periods <= 12
+
+    def test_calibrate_params_with_profile(self):
+        from services.proposal_service import ProposalService
+        svc = ProposalService()
+        values, dates = _stable_series(90)
+        profile = SeriesProfile(regime=SeriesRegime.STABLE, n_points=90, n_valid=90)
+        result = svc.calibrate_params(values, dates, profile=profile)
+        assert result.profile is profile

