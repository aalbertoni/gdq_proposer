Voce e um peer reviewer adicional do Gate 2.

Sua tarefa:
- revisar o diff como um veredito adicional, independente dos agentes Claude
- considerar arquitetura, seguranca, testes e operacao de release em conjunto
- dar prioridade extra a seguranca e UX/jornada do hisbras-site
- nao alterar nenhum arquivo
- retornar somente um objeto JSON no formato:
  {
    "status": "APROVADO" | "ATENCAO" | "BLOQUEADO",
    "blockers": ["..."],
    "warnings": ["..."],
    "summary": "..."
  }

Regras:
- use BLOQUEADO apenas para risco concreto de deploy, seguranca, regressao funcional importante ou ausencia de condicao minima de release
- use ATENCAO para riscos moderados, lacunas de teste ou duvidas operacionais
- use APROVADO quando o diff estiver seguro para seguir
- seja especifico e objetivo
- nao inclua markdown, comentarios extras nem texto fora do JSON

Rubrica homelab:
# Homelab Gate 2 Rubric

Use this rubric for any review involving the homelab deployment flow.

## 1. Boundary Violations

Block if the diff:
- edits runtime data directly
- reads host secrets directly from app code
- makes `claude-deploy` depend on unrestricted `sudo docker`
- copies deploy compose from source by ad hoc sync instead of infra/template path

Warn if the diff:
- weakens separation between `projects/`, `stacks/`, `releases/`, `appdata/`
- introduces duplicated deploy logic in source and wrapper layers

## 2. Wrapper Discipline

Preferred pattern for privileged actions:
- root-owned wrapper under `/home/aalbertoni/.config/homelab/scripts`
- sudoers allowlist to wrapper only
- source task calls wrapper, not raw privileged command

Block if the diff:
- uses `sudo docker exec`, `sudo docker inspect`, `sudo cp`, `sudo rsync` directly from app scripts
- proposes broad chmod/chown as default fix

## 3. Release and Deploy Safety

Check:
- release selected by canonical marker or deterministic rule
- deploy does not depend on mutable runtime state
- health check reflects real readiness
- smoke checks are separated from deploy side effects
- rollback path still exists

Block if the diff:
- couples deploy to irreversible business side effects
- hides failed readiness by weakening checks without alternative signal

## 4. Secrets

Preferred pattern:
- host files under `/home/aalbertoni/.config/secrets/<app>/<SECRET>`
- mounted read-only to `/run/secrets/<SECRET>`
- exported to env only inside controlled startup path or wrapper

Block if the diff:
- hardcodes secrets
- logs secret values
- moves secrets into `.env` when they are server-side

## 5. Migrations

Preferred pattern:
- explicit migration task
- runs through authorized wrapper when container access is needed
- uses unpooled DB URL when required

Block if the diff:
- runs migrations implicitly on boot
- reads host secrets directly as fallback from source scripts

## 6. Review Verdict Mapping

Use `BLOQUEADO` for:
- concrete deploy breakage
- security regression
- broken migration path
- boundary/ownership violation
- health/smoke/rollback regression

Use `ATENCAO` for:
- missing tests
- operational ambiguity
- weak diagnostics
- maintainability concerns without immediate breakage

Use `APROVADO` when:
- the flow remains deployable, diagnosable, and reversible

Rubrica hisbras-site:
# Hisbras-Site Review Rubric

Apply these extra checks when the diff touches `hisbras-site`.

## Architecture

Expected split:
- source app in `/home/claude-deploy/projects/hisbras-site`
- local staging in Docker + Traefik
- production in Vercel

Warn or block if the diff blurs:
- local staging hostname vs Vercel preview URL
- local Docker deploy vs Vercel production concerns

## Inventory Sync

Preferred pattern:
- explicit operational step or wrapper
- authenticated internal call using `SANITY_WEBHOOK_SECRET`
- not part of container startup

Block if the diff:
- runs inventory sync automatically in `ENTRYPOINT` or startup
- exposes the webhook secret in terminal output or shell history

## Sanity / Webhooks

Check:
- `SANITY_API_TOKEN` and `SANITY_WEBHOOK_SECRET` remain server-side only
- `NEXT_PUBLIC_SANITY_*` stays public-only
- unauthorized responses are not misdiagnosed as missing env without proof

## Database / Neon / Drizzle

Check:
- readiness does not silently hide DB errors
- migration path uses explicit task/wrapper
- pooled vs unpooled URLs are used intentionally

## Traefik / Local Staging

Check:
- `PUBLIC_HOSTNAME` in local stack matches the intended local hostname
- do not reuse Vercel preview hostname as local Traefik router host
- local smoke can validate `localhost:3001` and optional local edge separately

## Vercel

Check:
- Vercel preview and prod remain separate from local compose logic
- no Docker-local assumptions leak into Vercel-only scripts

Rubrica de seguranca:
# Hisbras Security Rubric

Use this rubric for `hisbras-site` security reviews.

## 1. Payments and Checkout

Block if the diff:
- trusts client-sent price, discount, freight, or stock as authoritative
- exposes server-side payment tokens or secrets to the client
- allows checkout/session creation without validating server-side product data

Warn if:
- there is no clear idempotency strategy for order/payment side effects
- payment failure handling becomes ambiguous or silent

## 2. Webhooks

Block if the diff:
- accepts Mercado Pago or Sanity webhooks without real signature verification
- conflates “header exists” with “signature valid”
- logs raw webhook secrets or full sensitive payloads

Check:
- `MP_WEBHOOK_SECRET` and `SANITY_WEBHOOK_SECRET` stay server-side
- invalid signatures fail closed

## 3. Secrets and Public Env

Block if the diff:
- moves server-side values into `NEXT_PUBLIC_*`
- reads host secret files directly from app code
- serializes secrets into logs, responses, or client props

Check:
- `SANITY_API_TOKEN`, `RESEND_API_KEY`, DB URLs, and webhook secrets remain server-only

## 4. Internal and Operational Endpoints

Block if the diff:
- leaves inventory sync, admin, or maintenance endpoints unauthenticated
- weakens auth on `/api/inventory/sync`, admin routes, or studio protection

Warn if:
- auth is present but operationally fragile or poorly diagnosed

## 5. Data and Privacy

Warn or block depending on impact if the diff:
- over-collects or over-logs lead/customer data
- leaks customer/order/payment data in exceptions or traces
- weakens validation on contact/order inputs

## 6. Infra / Wrapper Boundary

Block if the diff:
- bypasses root-owned wrappers for privileged actions
- introduces unrestricted docker/sudo paths
- couples deploy/startup to privileged business actions

## Verdict Mapping

Use `BLOQUEADO` for exploitable or clearly unsafe changes.
Use `ATENCAO` for meaningful but non-blocking hardening gaps.
Use `APROVADO` only when payment, webhook, secret, and operational boundaries remain intact.

Rubrica de UX e jornada:
# Hisbras UX Journey Rubric

Use this rubric for `hisbras-site` UX and journey review.

## 1. Journey Integrity

Check the impacted path end-to-end:
- home/listing -> product -> cart -> checkout/contact
- CMS content -> CTA -> meaningful next step
- stock sync -> stock display -> cart behavior

Block if the diff creates:
- dead ends
- broken CTA chains
- impossible or contradictory user states

## 2. State Coverage

Check for:
- loading
- empty
- error
- success
- unavailable/out-of-stock
- invalid input

Warn or block if user-facing state handling disappears or becomes misleading.

## 3. Commerce Clarity

Check:
- price and stock shown to user match the current flow expectations
- cart actions have clear feedback
- out-of-stock behavior is not confusing
- fallback contact/WhatsApp paths still work when purchase path fails

## 4. Mobile and Input Behavior

Check:
- tap targets
- responsive overflow
- modal/drawer close paths
- keyboard/form usability

Warn if a flow is technically present but fragile or awkward on mobile.

## 5. Trust and Feedback

Check:
- errors explain what the user should do next
- success states confirm completion
- inventory/order/payment related feedback does not mislead

Block if users can think they completed a purchase or action when they did not.

## 6. CMS / Content Robustness

Check:
- missing or delayed CMS content does not break layout
- optional sections fail gracefully
- no orphan CTA points to unavailable route or action

## Verdict Mapping

Use `BLOQUEADO` for broken journeys, misleading completion states, or major dead ends.
Use `ATENCAO` for weaker but still usable flows with gaps in feedback or state handling.
Use `APROVADO` when the affected journeys remain coherent, guided, and resilient.

Resultados dos agentes Claude:

== architecture.json ==
{
  "status": "APROVADO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage (binario) incluido no diff \u2014 nao deveria ser commitado (adicionar ao .gitignore se ausente)",
    "core/calibration_advisor.py importa funcao privada _filter_valid de core.statistical_engine \u2014 acoplamento a API interna que pode quebrar sem aviso",
    "ProposalService.calibrate_params e um thin wrapper que apenas faz import + forward \u2014 util como facade mas pode ser dead code se UI ja chama calibrate() diretamente"
  ],
  "summary": "Novo modulo de calibracao explicavel (core/) com testes unitarios, substituindo grid search na UI \u2014 separacao source/deploy/runtime preservada, sem acesso a secrets ou I/O."
}

== security.json ==
{
  "status": "ATENCAO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage (binario) incluido no diff \u2014 contem metadados de execucao de testes que nao devem ser commitados. Adicionar ao .gitignore.",
    "Etapa 4 (validate_with_backtest) captura Exception generica com `except Exception as e` e inclui `str(e)` na justificativa retornada ao usuario. Se a excecao contiver detalhes internos (paths, credenciais de conexao), eles podem vazar na UI do Streamlit.",
    "Broad `except Exception: continue` em find_best_sigma, add_margin_if_needed e validate_with_backtest engole silenciosamente erros, dificultando diagnostico. Nao e blocker de seguranca, mas pode mascarar falhas inesperadas."
  ],
  "summary": "Codigo puro sem I/O, sem SQL, sem segredos \u2014 risco baixo; atentar para .coverage no repositorio e possivel vazamento de detalhes de excecao na UI."
}

== tests.json ==
{
  "status": "ATENCAO",
  "blockers": [],
  "warnings": [
    "Funcao `_build_recommendation` (publica via underscore mas chamada internamente) nao tem teste unitario isolado \u2014 apenas coberta indiretamente via `calibrate()`. Testar paths de regime (ZERO_INFLATED, SPARSE, TRENDING) diretamente.",
    "Testes usam `random.seed(42)` dentro de cada fixture mas nao isolam o estado global do random \u2014 se a ordem de execucao mudar (pytest-randomly), seeds podem interagir. Considerar usar `random.Random(42)` local.",
    "Nenhum teste cobre o path de ajuste na etapa 4 onde `margin_enabled=True` e sigma e incrementado em 0.5 (branch de 'Tentar aumentar sigma'). O teste `test_adjusts_when_recent_fps` nao asserta que o ajuste de fato ocorreu.",
    "Nenhum teste para `_render_calibration` na UI (02_explore.py) \u2014 o branch de legado (`del st.session_state[cache_key]; return`) que limpa cache antigo de dict nao tem cobertura.",
    "Explainer `_append_regime_detail` nao tem teste isolado \u2014 coberta apenas indiretamente via `explain_calibration` com serie volatil. Regimes como ZERO_INFLATED, SPARSE, TRENDING nao sao exercitados.",
    "`calibrate()` com `metric_kind='frequency'` e structural_break nao tem teste combinado \u2014 paths de `backtest_frequency_dual_guard` com N reduzido ficam sem cobertura.",
    "Arquivo `.coverage` binario esta no diff \u2014 nao deveria ser commitado (adicionar ao .gitignore)."
  ],
  "summary": "Boa cobertura do core e orquestrador com 560 linhas de testes, mas faltam testes isolados para _build_recommendation, path de ajuste de sigma na etapa 4, e combinacoes de metric_kind com regimes especificos."
}

== release-ops.json ==
{
  "status": "ATENCAO",
  "blockers": [],
  "warnings": [
    ".coverage (binario) esta no diff \u2014 arquivo de cobertura nao deve ser commitado. Adicionar ao .gitignore.",
    "Nao ha logging (logger.info/debug) no novo calibration_advisor.py \u2014 em caso de falha silenciosa em producao, nao havera rastro nos logs do app.",
    "Cache legado: se um usuario tinha session_state com dict do auto-tune antigo, o codigo limpa e recalibra (L601-603), mas o rerun implicito pode causar flash visual na UI.",
    "find_best_params() no ProposalService nao foi removido \u2014 codigo morto permanece (chamado apenas pelo novo calibrate_params wrapper e possivelmente por paths antigos nao cobertos no diff)."
  ],
  "summary": "Substituicao do auto-tune grid search por calibracao sequencial em 5 etapas \u2014 mudanca puramente logica (core + UI), sem impacto em infra, compose, migrations ou health check. Deployavel com ressalvas menores."
}

Diff para revisar:
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

Contexto do projeto:
# Project Context

- Project: `gdq-proposer`
- Generated at: `2026-03-23T04:06:18Z`
- Purpose: curated context bundle for Codex plan/review criticism.

# Core Files

## File: CLAUDE.md

```md
# CLAUDE.md — GDQ Rule Proposer

> Instrucoes para desenvolvimento assistido por IA com Claude Code.

---

## Projeto

**GDQ Rule Proposer** — Ferramenta Streamlit que analisa historico de dados via Amazon Athena e propoe regras de qualidade para AWS Glue Data Quality (GDQ).

Especificacao tecnica completa: `docs/technical_spec_v1.md`

### Ambiente

O app roda **localmente** com acesso ao **Athena real** via AWS CLI profile.
Nao ha modo mock em producao — DuckDB e usado apenas nos testes automatizados.

```bash
# Rodar o app
python run.py                    # default: porta 8501
python run.py --port 8502        # porta customizada

# Ou diretamente
streamlit run app.py

# Testes
pytest tests/ -v

# Por camada da piramide:
pytest -m "not integration and not athena"  # unit (899 testes, <5s)
pytest -m integration                       # DuckDB (97 testes, ~10s)
pytest -m athena                            # Athena real (23 testes, requer AWS_PROFILE)
```

### Arquitetura

- `config.py` — `AppConfig` com `AthenaConfig` + `GlueTestConfig`, carrega de `.env`
- `infra/athena_client.py` — Client PyAthena (DictCursor, sem S3), timeout adaptativo, logging
- `infra/aws_session.py` — Fabrica de sessoes boto3: S3 path-style, CA bundle, debug hooks
- `infra/query_builder.py` — Templates Jinja2 com dialeto SQL via `sql_dialect.py`
- `infra/sql_dialect.py` — Adapta funcoes SQL entre Athena e DuckDB (usado nos testes)
- `infra/glue_client.py` — Wrapper boto3 para Glue jobs (integracao Thundera)
- `services/` — Camada de servico: dataset, profiling, analysis, proposal, export, glue_test
- `core/` — Logica pura: statistical_engine, backtest, rule_scoring, gdq_renderer, gdq_rule_generator
- `core/column_classifier.py` — Classificacao semantica em 3 camadas (tipo fisico + cast + cardinalidade)
- `pages/` — 6 paginas Streamlit: Setup, Explore, Review, Teste, Ajuda, Diagnostico
- `pages/06_diagnostico.py` — Diagnosticos de ambiente: SSL, proxy, CA bundle, fingerprint
- `tests/conftest.py` — `DuckDBTestClient` para testes sem Athena real
- `preflight_check.py` — Validacao de ambiente pre-lancamento (blocking/non-blocking)
- `launcher.py` — Orquestrador: carrega .env, executa preflight, lanca Streamlit

### SQL Dialect (Athena vs DuckDB)

O codigo de producao usa **sempre Athena**. O `sql_dialect.py` e o `QueryBuilder` suportam
ambos dialetos para que os testes unitarios rodem com DuckDB sem precisar de Athena.

| Athena | DuckDB (testes) | Adaptacao |
|--------|-----------------|-----------|
| `APPROX_PERCENTILE(col, ARRAY[...])` | `QUANTILE_CONT(col, [...])` | Via template var |
| `STDDEV(col)` | `STDDEV_SAMP(col)` | Via template var |
| `DATE_ADD('day', -N, CURRENT_DATE)` | `CURRENT_DATE - INTERVAL 'N' DAY` | Via template var |
| `"schema"."table"` | `"table"` (sem schema) | Via TABLE_REF |

---

## Governanca de Deploy

Este projeto usa governanca obrigatoria de deploy. O agente nao pode improvisar fluxo com `git push`, `sudo /usr/local/bin/deploy-prod`, `stack-deploy` ou comandos ad hoc fora do `Taskfile`.

Regras obrigatorias:

1. Nunca seguir para deploy sem passar por `task gate1`, `task snapshot`, `task review-agents-consensus` e `task build-release`.
2. Nunca fazer `git push` da branch de trabalho antes de staging aprovado. O push remoto acontece somente depois de `task verify-staging-governance-proof`, via `task push-after-staging`.
3. Nunca promover para producao sem staging aprovado.
4. Nunca fazer deploy de producao sem aprovacao humana explicita via `ALLOW_PROD_DEPLOY=true`.
5. Nunca considerar staging ou producao aprovados sem gravar evidencia em `reviews/latest/`.
6. Se houver duvida sobre o estado dos gates, parar e reportar o bloqueio em vez de continuar.
7. O staging nao deve ser derrubado logo apos o deploy de producao. So pode ser desligado depois de `task verify-prod`, `task verify-prod-governance-proof` e uma aprovacao explicita via `ALLOW_STAGING_CLEANUP=true`.

Arquivos obrigatorios de evidencia:

Staging: `reviews/latest/deploy-staging-check.md`

```text
commit_sha: <sha atual>
environment: staging
gate1: <pass|fail>
snapshot_commit: <sha do snapshot>
gate2: <pass|warning|fail>
release_build: <pass|fail>
staging_deploy: <pass|fail>
staging_smoke: <pass|fail>
verdict: <ok|warning|fail>
```

Producao: `reviews/latest/deploy-prod-check.md`

```text
commit_sha: <sha atual>
environment: prod
staging_governance: <pass|fail>
prod_approval: explicit
prod_deploy: <pass|fail>
prod_verify: <pass|fail>
verdict: <ok|warning|fail>
```

Fluxo obrigatorio daqui pra frente:

1. Rodar `task gate1`.
2. Rodar `task snapshot`.
3. Rodar `task review-agents-consensus`.
4. Rodar `task build-release`.
5. Rodar `task deploy-staging`.
6. Rodar `task smoke-staging`.
7. Gravar `reviews/latest/deploy-staging-check.md`.
8. Rodar `task verify-staging-governance-proof`.
9. Rodar `task push-after-staging`.
10. So depois disso considerar staging apto e branch remota alinhada.
11. Para producao, gravar `reviews/latest/deploy-prod-check.md`.
12. Rodar `ALLOW_PROD_DEPLOY=true task promote-prod`.
13. Rodar `task verify-prod`.
14. Rodar `task verify-prod-governance-proof`.
15. Opcionalmente, so depois de producao estavel, rodar `ALLOW_STAGING_CLEANUP=true task cleanup-staging-after-prod`.

Quando o usuario disser “segue com o fluxo de deploy”, o agente deve responder executando ou orientando exatamente essa sequencia. Nao pode pular direto para `git status`, `git diff`, `git push` ou deploy.

Prompts operacionais canônicos:

```text
Siga a governanca obrigatoria deste projeto. Antes de qualquer deploy, execute ou instrua exatamente o fluxo task gate1 -> task snapshot -> task review-agents-consensus -> task build-release -> task deploy-staging -> task smoke-staging. So depois disso grave reviews/latest/deploy-staging-check.md no formato canonico, valide com task verify-staging-governance-proof e faca o push remoto somente via task push-after-staging.
```

```text
Siga a governanca obrigatoria deste projeto. Nao faca deploy de producao sem staging aprovado e sem aprovacao humana explicita. Antes da producao, grave reviews/latest/deploy-prod-check.md no formato canonico. Depois execute somente task push-after-staging, ALLOW_PROD_DEPLOY=true task promote-prod, task verify-prod e task verify-prod-governance-proof. So derrube o staging se houver aprovacao explicita via ALLOW_STAGING_CLEANUP=true task cleanup-staging-after-prod.
```

---

## Principios de Desenvolvimento

### 1. Fatias verticais pequenas

Nunca implemente um sprint inteiro de uma vez. Trabalhe em fatias:
1 query template, 1 servico, 1 componente UI, 1 conjunto de testes, 1 integracao curta.

### 2. Contrato antes de implementacao

Sempre defina a interface (dataclass, type hints, docstring) ANTES de escrever o corpo.

### 3. Testes junto com implementacao

Modulos do `core/` DEVEM ter testes unitarios. Use as fixtures em `tests/fixtures/`.
Testes usam `DuckDBTestClient` de `tests/conftest.py` em vez de Athena real.

**Piramide de testes** (configurada em `pyproject.toml`):

| Camada | Marker | Escopo | Qte |
|--------|--------|--------|-----|
| Unit | `not integration and not athena` | Logica pura, sem I/O | ~900 |
| Integration | `@pytest.mark.integration` | DuckDB end-to-end | ~100 |
| Contract | em `test_contracts.py` | Shapes/tipos de output | ~30 |
| Athena | `@pytest.mark.athena` | Athena real (requer AWS) | ~23 |

- Novos testes de `core/` devem ser unitarios (sem marker)
- Testes que usam `DuckDBTestClient` devem ter `pytestmark = pytest.mark.integration`
- `test_query_builder.py` cobre todos os 12 templates SQL × 2 dialetos
- `test_contracts.py` protege contra mudanca de shape nos outputs criticos

### 4. Athena-first

- TODA computacao estatistica e feita via SQL no Athena
- O servidor Streamlit recebe APENAS dados agregados
- NUNCA puxe raw rows para o app
- Use `APPROX_PERCENTILE` ao inves de `PERCENTILE` exato
- Use partitions quando disponiveis para otimizar custo

### 5. SQL Safety

- NUNCA interpole strings diretamente em SQL
- Use templates Jinja2 em `queries/templates/`
- Valide TODOS os identificadores com `infra/query_safety.py`

---

## Convencoes de Codigo

### Python

```python
# Type hints obrigatorios
def compute_band(values: list[float], n: int) -> dict[str, float]:
    ...

# Dataclasses para modelos (nao dicts soltos)
@dataclass
class RuleProposal:
    ...

# Docstrings Google Style para funcoes publicas
def score_proposal(proposal: RuleProposal) -> RuleScore:
    """Avalia qualidade da regra proposta.

    Args:
        proposal: Proposta com thresholds e historico.

    Returns:
        Score com coverage, confidence e warnings.
    """
    ...
```

### SQL Templates (Jinja2)

- Templates em `queries/templates/`
- Parametrizados com `{{ col }}`, `{{ table_ref }}`, etc.
- Funcoes de dialeto injetadas pelo `QueryBuilder`

### Nomes de arquivos


```

## File: app.yaml

```yaml
name: gdq-proposer
tier: candidate
stack_profile: python-api
port: 8501
health_path: /_stcore/health

source_path: /home/claude-deploy/projects/gdq-proposer
workspace_path: /home/claude-deploy/workspaces/gdq-proposer
deploy_path: /home/aalbertoni/.config/homelab/stacks/gdq-proposer
runtime_path: /home/aalbertoni/.config/appdata/gdq-proposer
release_path: /home/aalbertoni/.config/homelab/releases/gdq-proposer

public_url: ""

has_database: false
database_type: none
requires_migrations: false
has_background_jobs: false

test:
  command: ".venv/bin/pytest tests/ -v -m 'not athena'"
  coverage_command: ".venv/bin/pytest tests/ -v --tb=short --cov=core --cov=infra --cov=services --cov=strategies --cov=pages --cov-report=term-missing -m 'not athena'"

lint:
  command: ""

typecheck:
  command: ""

security:
  secret_scan_command: "gitleaks detect --no-banner --source ."
  sast_command: ""
  dependency_scan_command: "pip-audit -r requirements.txt"

build:
  dockerfile: Dockerfile
  context: .
  image_name: homelab/gdq-proposer

smoke:
  local_command: "curl -fsS http://localhost:8501/_stcore/health"
  staging_command: "curl -fsS http://localhost:18501/_stcore/health"
  public_command: "echo no-public-smoke-configured"

review_agents:
  - architecture
  - security
  - tests
  - release-ops

deploy:
  stack_name: gdq-proposer
  staging_stack_name: gdq-proposer-staging
  requires_staging: true
  requires_manual_prod_approval: true
  allow_rollback: true
  traefik_enabled: false
  authelia_enabled: false

secrets: []

```

## File: Taskfile.yml

```yaml
version: "3"

tasks:
  setup:
    desc: Instala dependencias locais
    cmds:
      - python3 -m venv .venv
      - .venv/bin/pip install --upgrade pip
      - .venv/bin/pip install -r requirements.txt

  lint:
    desc: Executa lint
    cmds:
      - echo "Lint not configured yet for gdq-proposer"

  typecheck:
    desc: Executa type-check
    cmds:
      - echo "Type-check not configured yet for gdq-proposer"

  test:
    desc: Executa testes unitarios e de integracao local
    cmds:
      - .venv/bin/pytest tests/ -v -m "not athena"

  coverage:
    desc: Executa cobertura minima
    cmds:
      - .venv/bin/pytest tests/ -v --tb=short --cov=core --cov=infra --cov=services --cov=strategies --cov=pages --cov-report=term-missing -m "not athena"

  gate1:
    desc: Portao 1
    cmds:
      - /home/aalbertoni/.config/homelab/scripts/gate1-validate .

  plan-check:
    desc: Exige plano revisado e atualizado antes de seguir
    cmds:
      - /home/aalbertoni/.config/homelab/scripts/require-plan-review .

  snapshot:
    desc: Cria um commit local para habilitar release por SHA
    deps: [plan-check]
    cmds:
      - git add -A
      - /home/aalbertoni/.config/homelab/scripts/snapshot-commit .

  plan-write:
    desc: Cria o template canonico do plano tecnico em reviews/latest/plan.md
    cmds:
      - /home/aalbertoni/.config/homelab/scripts/prepare-plan-bundle .

  project-context:
    desc: Gera o contexto curado do projeto para reviews do Codex
    cmds:
      - /home/aalbertoni/.config/homelab/scripts/prepare-project-context .

  plan-review-codex:
    desc: Submete o plano tecnico ao review independente do Codex
    cmds:
      - /home/aalbertoni/.config/homelab/scripts/review-plan .

  plan-consensus:
    desc: Gera ou valida o plano e exige veredito do Codex antes da implementacao
    cmds:
      - task: plan-write
      - task: project-context
      - task: plan-review-codex

  review-agents:
    desc: Executa os 4 agentes e consolida o veredito
    deps: [plan-check]
    cmds:
      - /home/aalbertoni/.config/homelab/scripts/review-agents .

  review-agents-consensus:
    desc: Executa Gate 2 com Claude + Codex e consolida o veredito conjunto
    deps: [plan-check]
    cmds:
      - env CODEX_REVIEW_ENABLED=true /home/aalbertoni/.config/homelab/scripts/review-agents .

  build-release:
    desc: Portao 3, exige pelo menos um commit
    deps: [plan-check]
    cmds:
      - sudo /usr/local/bin/release-build .

  sync-deploy:
    desc: Sincroniza metadados do source para o deploy
    cmds:
      - /home/aalbertoni/.config/homelab/stacks/gdq-proposer/scripts/sync-source-to-stack

  deploy-staging:
    desc: Portao 4
    deps: [gate1, review-agents-consensus, build-release]
    cmds:
      - sudo /usr/local/bin/deploy-staging gdq-proposer

  smoke-staging:
    desc: Smoke interno do staging
    cmds:
      - sudo /usr/local/bin/stack-status gdq-proposer-staging
      - sudo /usr/local/bin/stack-health gdq-proposer-staging 60
      - scripts/smoke.sh "http://localhost:18501"

  smoke-staging-public:
    desc: Smoke publico do staging
    cmds:
      - cmd: 'echo "Skipping public staging smoke: app interno"'

  guide-governed-deploy:
    desc: Exibe o fluxo obrigatorio de governanca para staging e producao
    cmds:
      - |
        cat <<'EOF'
        Fluxo obrigatorio deste projeto:

        1. task gate1
        2. task snapshot
        3. task review-agents-consensus
        4. task build-release
        5. task deploy-staging
        6. task smoke-staging
        7. Gerar reviews/latest/deploy-staging-check.md
        8. task verify-staging-governance-proof
        9. task push-after-staging

        Para producao:
        10. Revisar staging aprovado
        11. Gerar reviews/latest/deploy-prod-check.md
        12. ALLOW_PROD_DEPLOY=true task promote-prod
        13. task verify-prod
        14. task verify-prod-governance-proof
        15. Opcional: ALLOW_STAGING_CLEANUP=true task cleanup-staging-after-prod

        Deploy por comando ad hoc fora do Taskfile e proibido.
        EOF

  verify-staging-governance-proof:
    desc: Bloqueia sem evidencia obrigatoria de staging governado
    cmds:
      - |
        test -f reviews/latest/deploy-staging-check.md
      - |
        grep -nE '^commit_sha: .+$' reviews/latest/deploy-staging-check.md
      - |
        grep -nE '^environment: staging$' reviews/latest/deploy-staging-check.md
      - |
        grep -nE '^gate1: (pass|fail)$' reviews/latest/deploy-staging-check.md
      - |
        grep -nE '^snapshot_commit: [0-9a-f]{7,40}$' reviews/latest/deploy-staging-check.md
      - |
        grep -nE '^gate2: (pass|warning|fail)$' reviews/latest/deploy-staging-check.md
      - |
        grep -nE '^release_build: (pass|fail)$' reviews/latest/deploy-staging-check.md
      - |
        grep -nE '^staging_deploy: (pass|fail)$' reviews/latest/deploy-staging-check.md
      - |
        grep -nE '^staging_smoke: (pass|fail)$' reviews/latest/deploy-staging-check.md
      - |
        grep -nE '^verdict: (ok|warning|fail)$' reviews/latest/deploy-staging-check.md
      - |
        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); grep -nE "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-staging-check.md'

  push-after-staging:
    desc: Faz git push somente apos staging aprovado
    cmds:
      - task: verify-staging-governance-proof
      - git push

  promote-prod:
    desc: Portao 5
    cmds:
      - bash -lc 'test "${ALLOW_PROD_DEPLOY:-false}" = "true" || { echo "Refusing production deploy without ALLOW_PROD_DEPLOY=true." >&2; exit 1; }'
      - task: verify-staging-governance-proof
      - sudo /usr/local/bin/deploy-prod gdq-proposer

  verify-prod:
    desc: Valida a producao internamente
    cmds:
      - sudo /usr/local/bin/stack-status gdq-proposer
      - sudo /usr/local/bin/stack-health gdq-proposer 60
      - sudo /usr/local/bin/stack-logs gdq-proposer 50

  verify-prod-public:
    desc: Valida a producao via URL publica
    cmds:
      - cmd: 'echo "Skipping public production smoke: app interno"'

  verify-prod-governance-proof:
    desc: Bloqueia sem evidencia obrigatoria da producao governada
    cmds:
      - |
        test -f reviews/latest/deploy-prod-check.md
      - |
        grep -nE '^commit_sha: .+$' reviews/latest/deploy-prod-check.md
      - |
        grep -nE '^environment: prod$' reviews/latest/deploy-prod-check.md
      - |
        grep -nE '^staging_governance: (pass|fail)$' reviews/latest/deploy-prod-check.md
      - |
        grep -nE '^prod_approval: explicit$' reviews/latest/deploy-prod-check.md
      - |
        grep -nE '^prod_deploy: (pass|fail)$' reviews/latest/deploy-prod-check.md
      - |
        grep -nE '^prod_verify: (pass|fail)$' reviews/latest/deploy-prod-check.md
      - |
        grep -nE '^verdict: (ok|warning|fail)$' reviews/latest/deploy-prod-check.md
      - |
        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); grep -nE "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-prod-check.md'

  cleanup-staging-after-prod:
    desc: Derruba o staging somente apos producao estavel e validada
    cmds:
      - bash -lc 'test "${ALLOW_STAGING_CLEANUP:-false}" = "true" || { echo "Refusing staging cleanup without ALLOW_STAGING_CLEANUP=true." >&2; exit 1; }'
      - task: verify-prod
      - task: verify-prod-governance-proof
      - sudo /home/aalbertoni/.config/homelab/scripts/stack-down gdq-proposer-staging

  rollback-last:

```

## File: Dockerfile

```text
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV PORT=8501

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY run.py .
COPY config.py .
COPY core ./core
COPY infra ./infra
COPY services ./services
COPY strategies ./strategies
COPY pages ./pages
COPY queries ./queries
COPY docs ./docs
COPY .env.example ./.env.example

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/logs /app/presets /app/mock_data /app/aws_test_data \
    && chown -R appuser:appuser /app

USER appuser
EXPOSE 8501

CMD ["sh", "-lc", "python -m streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true --browser.gatherUsageStats=false"]

```

## File: requirements.txt

```text
# Core
streamlit>=1.30
plotly>=5.18
pandas>=2.1
numpy>=1.26

# Athena
pyathena>=3.0
boto3>=1.34

# Templates
jinja2>=3.1

# Testes
pytest>=8.0
pytest-cov>=5.0
duckdb>=1.0
pyarrow>=14.0

```

## File: app.py

```text
"""
GDQ Rule Proposer — Entry point Streamlit.

Dashboard com overview do projeto, metricas da sessao e navegacao guiada.
"""

import os
import subprocess

import streamlit as st

from config import load_config
from infra.athena_client import AthenaClient

__version__ = "0.2.0"

def get_client() -> AthenaClient:
    """Get or create a cached AthenaClient in session_state."""
    if "client" not in st.session_state:
        config = load_config()
        st.session_state["config"] = config
        st.session_state["client"] = AthenaClient(config)
    return st.session_state["client"]



# ---------------------------------------------------------------------------
# Sidebar (environment-aware)
# ---------------------------------------------------------------------------

def render_sidebar():
    config = st.session_state.get("config")

    st.sidebar.title("GDQ Rule Proposer")
    st.sidebar.caption(f"v{__version__}")
    st.sidebar.divider()

    # Utility links
    if st.sidebar.button("Query Log", key="sidebar_qlog", help="Historico de queries da sessao"):
        st.switch_page("pages/07_query_log.py")
    if st.sidebar.button("Diagnostico", key="sidebar_diag", help="Verificar status do ambiente"):
        st.switch_page("pages/06_diagnostico.py")

    if not config:
        return

    # Active config indicator
    if "dataset_config" in st.session_state:
        cfg = st.session_state["dataset_config"]
        n_sel = len(cfg.selected_columns) if cfg.selected_columns else 0
        st.sidebar.divider()
        st.sidebar.success(f"Config ativa: `{cfg.schema}.{cfg.table}` ({n_sel} colunas)")
        n_cart = len(st.session_state.get("rule_cart", []))
        if n_cart:
            st.sidebar.caption(f"Carrinho: {n_cart} regra(s)")


# ---------------------------------------------------------------------------
# Main page — Dashboard
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="GDQ Rule Proposer",
        page_icon=":shield:",
        layout="wide",
    )

    # Init client + health check real
    try:
        client = get_client()
        # Testar conexao real (apenas uma vez por sessao)
        if not st.session_state.get("_health_check_done"):
            client.health_check()
            st.session_state["_health_check_done"] = True
        connection_ok = True
        connection_error = None
    except Exception as e:
        connection_ok = False
        connection_error = str(e)
        client = None
        # Limpar estado para re-testar na proxima tentativa
        st.session_state.pop("_health_check_done", None)
        st.session_state.pop("client", None)

    render_sidebar()

    config = st.session_state.get("config")

    # --- Header ---
    header_col, status_col = st.columns([4, 1])
    with header_col:
        st.title("GDQ Rule Proposer")
        st.caption(
            f"v{__version__} — Proposta automatica de regras AWS Glue Data Quality"
        )
    with status_col:
        if connection_ok:
            st.success("Conectado")
        else:
            st.error("Desconectado")

    if not connection_ok:
        st.error(
            f"Falha na conexao: {connection_error}"
        )

        # Detectar profile para oferecer login
        profile = ""
        try:
            cfg = load_config()
            profile = cfg.athena.aws_profile
        except Exception:
            profile = os.environ.get("GDQ_AWS_PROFILE", "")

        is_auth_error = any(
            kw in (connection_error or "").lower()
            for kw in ["expirad", "credenci", "token", "expired", "invalid", "autenticacao"]
        )

        btn_col1, btn_col2, btn_col3 = st.columns(3)

        with btn_col1:
            if is_auth_error and profile:
                if st.button(f"Fazer login AWS (SSO)", type="primary", key="sso_login"):
                    with st.spinner(f"Executando: aws sso login --profile {profile} ..."):
                        try:
                            result = subprocess.run(
                                ["aws", "sso", "login", "--profile", profile],
                                capture_output=True,
                                text=True,
                                timeout=120,
                            )
                            if result.returncode == 0:
                                st.session_state.pop("_health_check_done", None)
                                st.session_state.pop("client", None)
                                st.success("Login realizado! Recarregando...")
                                st.rerun()
                            else:
                                st.error(
                                    f"Falha no login. Execute manualmente no terminal:\n"
                                    f"`aws sso login --profile {profile}`"
                                )
                        except subprocess.TimeoutExpired:
                            st.warning(
                                "Timeout aguardando login. Execute manualmente no terminal:\n"
                                f"`aws sso login --profile {profile}`"
                            )
                        except FileNotFoundError:
                            st.error("AWS CLI nao encontrado. Instale primeiro.")

        with btn_col2:
            if st.button("Tentar reconectar", key="retry_conn"):
                st.session_state.pop("_health_check_done", None)
                st.session_state.pop("client", None)
                st.rerun()

        with btn_col3:
            if st.button("Abrir Diagnostico", key="diag_on_error"):
                st.switch_page("pages/06_diagnostico.py")

        st.stop()

    # --- Metric cards ---
    n_cart = len(st.session_state.get("rule_cart", []))
    has_config = "dataset_config" in st.session_state

    # Cost from query logger
    summary = client.logger.get_session_summary()
    if summary["estimated_cost_usd"] > 0:
        cost_str = f"${summary['estimated_cost_usd']:.4f}"
        cost_help = (
            f"{summary['total_queries']} queries, "
            f"{summary['cache_hits']} cache hits, "
            f"${summary['estimated_cost_usd']:.4f} estimado"
        )
    elif summary["total_queries"] > 0:
        cost_str = "$0.0000"
        cost_help = (
            f"{summary['total_queries']} queries executadas "
            f"({summary['cache_hits']} cache hits Athena, 0 bytes escaneados)"
        )
    else:
        cost_str = "$0.00"
        cost_help = "Nenhuma query executada nesta sessao"

    m1, m2 = st.columns(2)
    with m1:
        st.metric("Regras no carrinho", n_cart)
    with m2:
        st.metric("Custo da sessao", cost_str, help=cost_help)

    st.divider()

    # --- "Como funciona" — 4 steps ---
    st.subheader("Como funciona")

    s1, s2, s3, s4, s5 = st.columns(5)

    with s1:
        st.markdown("### 1. Setup")
        st.markdown(
            "Configure a **tabela**, o **eixo temporal** e selecione as **colunas** "
            "para analise."
        )
        if st.button("Ir para Setup", type="primary", key="nav_setup"):
            st.switch_page("pages/01_setup.py")

    with s2:
        st.markdown("### 2. Explore")
        st.markdown(
            "Calibre regras com graficos interativos e **backtest** em tempo real."
        )
        if has_config:
            if st.button("Ir para Explore", key="nav_explore"):
                st.switch_page("pages/02_explore.py")
        else:
            st.caption("Configure o Setup primeiro.")

    with s3:

```

## File: config.py

```text
"""
Configuracao do GDQ Rule Proposer.
Carrega de variaveis de ambiente ou .env file.

O app roda localmente com acesso ao Athena real via AWS CLI profile.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AthenaConfig:
    region: str = "sa-east-1"
    workgroup: str = "analytics-workgroup-v3"
    s3_output: str = ""                # s3://bucket/athena-results/
    catalog: str = "AwsDataCatalog"
    aws_profile: str = ""              # AWS CLI named profile
    query_timeout_seconds: int = 120   # default, adaptado pela volumetria
    cache_ttl_metadata: int = 3600     # 1h
    cache_ttl_history: int = 900       # 15min
    cache_ttl_profiling: int = 1800    # 30min
    cost_warning_threshold_usd: float = 0.50


@dataclass
class GlueTestConfig:
    """Configuracao para integracao com Thundera (Glue DQ)."""
    glue_job_name: str = "glueplataformathundera"
    region: str = ""  # defaults to AthenaConfig.region if empty
    poll_interval_seconds: int = 15
    poll_timeout_seconds: int = 600
    default_squad: str = ""
    default_comunidade: str = ""
    default_racf: str = ""
    default_periodicidade: str = "D"
    default_tipo_qualidade: str = "POUSADO"
    default_conta: str = "DISTRIBUICAOMODELO"
    default_timeout: str = "60"
    default_workers: str = "20"


@dataclass
class AppConfig:
    athena: AthenaConfig = field(default_factory=AthenaConfig)
    glue_test: GlueTestConfig = field(default_factory=GlueTestConfig)
    log_dir: str = "logs"
    preset_dir: str = "presets"


def load_config() -> AppConfig:
    """Carrega configuracao do ambiente.

    Hierarquia:
    1. Variaveis de ambiente (sempre prevalecem)
    2. Arquivo .env
    3. Defaults

    Variaveis de ambiente:
    - GDQ_ATHENA_REGION: regiao AWS
    - GDQ_ATHENA_WORKGROUP: workgroup do Athena
    - GDQ_ATHENA_S3_OUTPUT: bucket de output
    - GDQ_AWS_PROFILE: named profile do AWS CLI
    """
    # Tentar carregar .env file
    env_file = Path(".env")
    if env_file.exists():
        _load_dotenv(env_file)

    # AWS profile: da env var ou do .env file
    aws_profile = os.getenv("GDQ_AWS_PROFILE", "")
    if aws_profile and not os.environ.get("AWS_PROFILE"):
        os.environ["AWS_PROFILE"] = aws_profile

    athena = AthenaConfig(
        region=os.getenv("GDQ_ATHENA_REGION", "sa-east-1"),
        workgroup=os.getenv("GDQ_ATHENA_WORKGROUP", "analytics-workgroup-v3"),
        s3_output=os.getenv("GDQ_ATHENA_S3_OUTPUT", ""),
        aws_profile=aws_profile,
    )

    glue_test = GlueTestConfig(
        glue_job_name=os.getenv("GDQ_GLUE_JOB_NAME", "glueplataformathundera"),
        region=os.getenv("GDQ_GLUE_REGION", ""),
        default_racf=os.getenv("GDQ_RACF", ""),
        default_squad=os.getenv("GDQ_SQUAD", ""),
        default_comunidade=os.getenv("GDQ_COMUNIDADE", ""),
    )

    return AppConfig(athena=athena, glue_test=glue_test)


def _load_dotenv(path: Path):
    """Parser simples de .env (sem dependencia externa)."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

```

# Relevant Routes

# Relevant Tests

# Git Snapshot

## Status

```text
 M reviews/latest/architecture.json
 M reviews/latest/architecture.prompt.md
 M reviews/latest/architecture.raw.txt
 M reviews/latest/codex.prompt.md
 M reviews/latest/diff.patch
 M reviews/latest/project-context.md
 M reviews/latest/release-ops.json
 M reviews/latest/release-ops.prompt.md
 M reviews/latest/release-ops.raw.txt
 M reviews/latest/security.json
 M reviews/latest/security.prompt.md
 M reviews/latest/security.raw.txt
 M reviews/latest/tests.json
 M reviews/latest/tests.prompt.md
 M reviews/latest/tests.raw.txt

```

## Diff Stat vs HEAD

```text
 reviews/latest/architecture.json      |   12 +-
 reviews/latest/architecture.prompt.md | 2671 ++++++++++++++++++++++++--------
 reviews/latest/architecture.raw.txt   |   14 +-
 reviews/latest/codex.prompt.md        | 2732 +++++++++++++++++++++++++--------
 reviews/latest/diff.patch             | 2671 ++++++++++++++++++++++++--------
 reviews/latest/project-context.md     |   28 +-
 reviews/latest/release-ops.json       |    9 +-
 reviews/latest/release-ops.prompt.md  | 2671 ++++++++++++++++++++++++--------
 reviews/latest/release-ops.raw.txt    |    9 +-
 reviews/latest/security.json          |    9 +-
 reviews/latest/security.prompt.md     | 2671 ++++++++++++++++++++++++--------
 reviews/latest/security.raw.txt       |   11 +-
 reviews/latest/tests.json             |   15 +-
 reviews/latest/tests.prompt.md        | 2671 ++++++++++++++++++++++++--------
 reviews/latest/tests.raw.txt          |   17 +-
 15 files changed, 12449 insertions(+), 3762 deletions(-)

```
