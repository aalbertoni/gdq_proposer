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
diff --git a/core/rule_explainer.py b/core/rule_explainer.py
index c2648e4..7025016 100644
--- a/core/rule_explainer.py
+++ b/core/rule_explainer.py
@@ -92,46 +92,67 @@ def _explain_mean(p: RuleProposal) -> str:
     col = p.target_column
     n = p.baseline_window or 30
     k = p.baseline_n_sigma or 2.0
-    margin = (p.baseline_margin_pct or 0.10) * 100
 
-    return (
+    base = (
         f"Verifica se a **media** da coluna `{col}` esta dentro do esperado. "
         f"A regra calcula a media dos ultimos **{n} periodos** e aceita o valor se estiver "
-        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica, "
-        f"**ou** dentro de **{margin:.0f}%** da media historica. "
-        f"Se qualquer uma das duas bandas for atendida, a regra passa."
+        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica"
     )
 
+    if p.margin_enabled:
+        margin = (p.baseline_margin_pct or 0.10) * 100
+        return (
+            f"{base}, "
+            f"**ou** dentro de **{margin:.0f}%** da media historica. "
+            f"Se qualquer uma das duas bandas for atendida, a regra passa."
+        )
+
+    return f"{base}."
+
 
 def _explain_stddev(p: RuleProposal) -> str:
     col = p.target_column
     n = p.baseline_window or 30
     k = p.baseline_n_sigma or 2.0
-    margin = (p.baseline_margin_pct or 0.10) * 100
 
-    return (
+    base = (
         f"Verifica se o **desvio padrao** da coluna `{col}` esta dentro do esperado. "
         f"A regra calcula o desvio padrao medio dos ultimos **{n} periodos** e aceita se estiver "
-        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica, "
-        f"**ou** dentro de **{margin:.0f}%** da media historica. "
-        f"Detecta se a dispersao dos dados mudou significativamente."
+        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica"
     )
 
+    if p.margin_enabled:
+        margin = (p.baseline_margin_pct or 0.10) * 100
+        return (
+            f"{base}, "
+            f"**ou** dentro de **{margin:.0f}%** da media historica. "
+            f"Detecta se a dispersao dos dados mudou significativamente."
+        )
+
+    return f"{base}. Detecta se a dispersao dos dados mudou significativamente."
+
 
 def _explain_rowcount(p: RuleProposal) -> str:
     table = p.target_table
     n = p.baseline_window or 30
     k = p.baseline_n_sigma or 2.0
-    margin = (p.baseline_margin_pct or 0.10) * 100
 
-    return (
+    base = (
         f"Verifica se o **volume de linhas** da tabela `{table}` esta dentro do esperado. "
         f"A regra calcula a quantidade media de linhas dos ultimos **{n} periodos** e aceita se estiver "
-        f"dentro de **{_fmt_k(k)} desvios padrao** do volume historico, "
-        f"**ou** dentro de **{margin:.0f}%** do volume historico. "
-        f"Detecta cargas com volume anomalo (muito acima ou abaixo)."
+        f"dentro de **{_fmt_k(k)} desvios padrao** do volume historico"
     )
 
+    if p.margin_enabled:
+        margin = (p.baseline_margin_pct or 0.10) * 100
+        return (
+            f"{base}, "
+            f"**ou** dentro de **{margin:.0f}%** do volume historico. "
+            f"Detecta cargas com volume anomalo (muito acima ou abaixo)."
+        )
+
+    return f"{base}. Detecta cargas com volume anomalo (muito acima ou abaixo)."
+
 
 def _explain_completeness(p: RuleProposal) -> str:
     col = p.target_column
@@ -207,16 +228,23 @@ def _explain_percentile(p: RuleProposal) -> str:
     pct_label = p.metric_name.upper() if p.metric_name else "P50"
     n = p.baseline_window or 30
     k = p.baseline_n_sigma or 2.0
-    margin = (p.baseline_margin_pct or 0.10) * 100
 
-    return (
+    base = (
         f"Verifica se o **{pct_label}** da coluna `{col}` esta dentro do esperado. "
         f"A regra calcula o percentil historico dos ultimos **{n} periodos** e aceita se estiver "
-        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica, "
-        f"**ou** dentro de **{margin:.0f}%** da media historica. "
-        f"Detecta mudancas na distribuicao dos dados (caudas)."
+        f"dentro de **{_fmt_k(k)} desvios padrao** da media historica"
     )
 
+    if p.margin_enabled:
+        margin = (p.baseline_margin_pct or 0.10) * 100
+        return (
+            f"{base}, "
+            f"**ou** dentro de **{margin:.0f}%** da media historica. "
+            f"Detecta mudancas na distribuicao dos dados (caudas)."
+        )
+
+    return f"{base}. Detecta mudancas na distribuicao dos dados (caudas)."
+
 
 def _explain_category_frequency(p: RuleProposal) -> str:
     col = p.target_column
diff --git a/pages/02_explore.py b/pages/02_explore.py
index d022894..160d270 100644
--- a/pages/02_explore.py
+++ b/pages/02_explore.py
@@ -303,23 +303,31 @@ def _render_add_to_cart(proposal, label, stable_key, show_syntax=True, profile=N
         st.caption(f"Motivo: {'; '.join(reasons)}")
 
     if show_syntax:
-        with st.expander("Sintaxe GDQ e detalhes", expanded=False):
-            st.code(proposal.gdq_syntax_preview)
-            st.info(explain_rule(proposal))
-            detail = explain_rule_detail(proposal)
-            if detail.strip():
-                st.markdown(detail)
-
-            # Regime context and trade-offs
-            if profile is not None:
-                regime_ctx = explain_regime_context(proposal, profile)
-                if regime_ctx:
+        st.code(proposal.gdq_syntax_preview)
+        st.info(explain_rule(proposal))
+
+        detail = explain_rule_detail(proposal)
+        has_detail = bool(detail and detail.strip())
+        has_regime = False
+        has_trade_off = False
+
+        if profile is not None:
+            regime_ctx = explain_regime_context(proposal, profile)
+            has_regime = bool(regime_ctx)
+            ev = evaluate_proposal(proposal, profile=profile)
+            trade_off_text = explain_trade_offs(proposal, ev)
+            has_trade_off = bool(trade_off_text)
+
+        if has_detail or has_regime or has_trade_off:
+            with st.expander("Detalhes", expanded=False):
+                if has_detail:
+                    st.markdown(detail)
+
+                if has_regime:
                     st.markdown("---")
                     st.markdown(regime_ctx)
 
-                ev = evaluate_proposal(proposal, profile=profile)
-                trade_off_text = explain_trade_offs(proposal, ev)
-                if trade_off_text:
+                if has_trade_off:
                     st.markdown("---")
                     st.markdown(trade_off_text)
 
@@ -364,212 +372,6 @@ def _update_col_health(column: str, rule_key: str, confidence: ConfidenceLevel)
     st.session_state[health_key][column][rule_key] = confidence
 
 
-def _render_diagnostics_panel(proposal):
-    """Painel consolidado de ferramentas de apoio a calibragem.
-
-    Agrupa sazonalidade, change-point, IQR/MAD e cobertura ponderada
-    em um unico expander com explicacoes claras sobre o que cada item
-    faz e se impacta ou nao a regra gerada.
-    """
-    if not proposal:
-        return
-
-    # Collect diagnostics
-    has_seasonality = (
-        proposal.seasonality_info
-        and proposal.seasonality_info.get("has_seasonality")
-    )
-    has_change_point = (
-        proposal.change_point_info
-        and proposal.change_point_info.get("has_change_point")
-    )
-    has_outliers = (
-        proposal.robust_info
-        and proposal.robust_info.get("outliers", {}).get("n_outliers", 0) > 0
-    )
-    has_weighted_cov = (
-        proposal.backtest
-        and hasattr(proposal.backtest, "weighted_coverage_pct")
-        and abs(proposal.backtest.weighted_coverage_pct - proposal.backtest.coverage_pct) > 1.0
-    )
-
-    n_findings = sum([
-        bool(has_seasonality),
-        bool(has_change_point),
-        bool(has_outliers),
-        bool(has_weighted_cov),
-    ])
-
-    if n_findings == 0:
-        return
-
-    # Build label
-    tags = []
-    if has_change_point:
-        tags.append("change-point")
-    if has_seasonality:
-        tags.append("sazonalidade")
-    if has_outliers:
-        tags.append("outliers")
-    if has_weighted_cov:
-        tags.append("recencia")
-    label = f"Diagnosticos de apoio a calibragem ({n_findings}): {', '.join(tags)}"
-
-    with st.expander(label, expanded=n_findings >= 2):
-        st.caption(
-            "Estas ferramentas analisam o comportamento dos dados para ajudar "
-            "na escolha dos parametros. Apenas o **Change-Point** altera o "
-            "calculo da regra. Os demais sao **informativos**."
-        )
-
-        # ------ 1. Change-Point (IMPACTA a regra) ------
-        if has_change_point:
-            cp = proposal.change_point_info
-            st.markdown("---")
-            st.markdown("**Change-Point (Mudanca de Regime)** — :red[IMPACTA A REGRA]")
-            st.caption(
-                "Detecta mudancas bruscas de patamar na serie (ex: migracao de sistema). "
-                "Usa o algoritmo CUSUM bilateral com threshold de 4 sigma."
-            )
-            n_post = len(cp.get("post_change_values", []))
-            st.warning(
-                f"Mudanca detectada em **{cp.get('change_date', '?')}**. "
-                f"{cp.get('message', '')} "
-                f"Os limites da regra foram calculados usando apenas os "
-                f"**{n_post} periodos pos-mudanca** (dados do regime atual)."
-            )
-            st.caption(
-                "Gabarito: a regra deve usar N <= periodos pos-mudanca. "
-                f"Neste caso, N <= {n_post}."
-            )
-
-        # ------ 2. Sazonalidade (NAO impacta) ------
-        if has_seasonality:
-            info = proposal.seasonality_info
-            st.markdown("---")
-            st.markdown("**Sazonalidade Semanal** — :green[NAO IMPACTA A REGRA]")
-            st.caption(
-                "Detecta padroes repetitivos por dia da semana usando eta-squared "
-                "(variancia entre grupos / variancia total). "
-                "Positivo quando eta-squared > 15% e amplitude > 10% da media."
-            )
-            st.info(
-                f"Forca: **{info['seasonality_strength']:.0%}** · "
-                f"Amplitude: **{info['amplitude_ratio']:.0%}** da media. "
-                f"{info['message']}"
-            )
-            st.caption(
-                "Gabarito: use N multiplo de 7 (14, 21, 28, 35) para alinhar a "
-                "janela com semanas completas e evitar vies. "
-                "O auto-tune ja prioriza isso automaticamente (+0.02 no score)."
-            )
-
-        # ------ 3. Outliers / IQR / MAD (NAO impacta) ------
-        if has_outliers:
-            robust = proposal.robust_info
-            outlier_info = robust.get("outliers", {})
-            comparison = robust.get("iqr_vs_sigma", {})
-            iqr_b = robust.get("iqr_band", {})
-            mad_b = robust.get("mad_band", {})
-
-            st.markdown("---")
-            st.markdown("**Analise de Outliers (IQR/MAD)** — :green[NAO IMPACTA A REGRA]")
-            st.caption(
-                "Compara a banda classica (sigma) com bandas robustas (IQR de Tukey "
-                "e MAD). Se a banda sigma for muito mais larga, outliers podem estar "
-                "distorcendo o desvio padrao."
-            )
-
-            # Key metrics side by side
-            oc1, oc2, oc3 = st.columns(3)
-            with oc1:
-                st.metric(
-                    "Outliers",
-                    f"{outlier_info['n_outliers']} ({outlier_info['pct_outliers']:.0%})",
-                    help="Periodos com valores fora de [Q1 - 1.5*IQR, Q3 + 1.5*IQR].",
-                )
-            with oc2:
-                sigma_w = comparison.get("sigma_width", 0)
-                iqr_w = comparison.get("iqr_width", 0)
-                ratio = sigma_w / iqr_w if iqr_w > 0 else 0
-                st.metric(
-                    "Sigma / IQR",
-                    f"{ratio:.1f}x",
-                    help="Razao entre largura da banda sigma e largura da banda IQR. "
-                         "Acima de 2x indica distorcao por outliers.",
-                )
-            with oc3:
-                rec = comparison.get("recommendation", "classical")
-                rec_labels = {
-                    "classical": "Classica (OK)",
-                    "robust_iqr": "Considerar IQR",
-                    "robust_mad": "Considerar MAD",
-                }
-                st.metric(
-                    "Recomendacao",
-                    rec_labels.get(rec, rec),
-                    help="'Classica (OK)' = banda sigma adequada. "
-                         "'Considerar IQR' = sigma inflada, aumentar K ou margem. "
-                         "'Considerar MAD' = distorcao severa.",
-                )
-
-            if iqr_b and mad_b:
-                st.caption(
-                    f"Banda IQR: [{iqr_b['lower']:.2f}, {iqr_b['upper']:.2f}] · "
-                    f"Banda MAD: [{mad_b['lower']:.2f}, {mad_b['upper']:.2f}]"
-                )
-
-            if rec != "classical":
-                st.caption(
-                    "Gabarito: aumente sigma (K) de 2 para 2.5 ou 3, ou aumente "
-                    "a margem % para compensar a distorcao causada pelos outliers."
-                )
-            else:
-                st.caption(
-                    "Gabarito: banda classica (sigma) esta adequada. "
-                    "Os outliers nao distorcem significativamente os limites."
-                )
-
-        # ------ 4. Cobertura Ponderada (NAO impacta) ------
-        if has_weighted_cov:
-            bt = proposal.backtest
-            st.markdown("---")
-            st.markdown("**Cobertura Ponderada (Recencia)** — :green[NAO IMPACTA A REGRA]")
-            st.caption(
-                "Atribui mais peso aos periodos recentes no backtest "
-                "(meia-vida ~14 periodos, decaimento exponencial). "
-                "Compara com a cobertura classica para indicar tendencia."
-            )
-            wc1, wc2 = st.columns(2)
-            with wc1:
-                st.metric(
-                    "Cobertura classica",
-                    f"{bt.coverage_pct:.1f}%",
-                    help="Todos os periodos com peso igual.",
-                )
-            with wc2:
-                delta = bt.weighted_coverage_pct - bt.coverage_pct
-                st.metric(
-                    "Cobertura recente",
-                    f"{bt.weighted_coverage_pct:.1f}%",
-                    delta=f"{delta:+.1f}pp",
-                    delta_color="normal",
-                    help="Periodos recentes pesam mais. "
-                         "Delta positivo = regra funciona melhor recentemente.",
-                )
-            if bt.weighted_coverage_pct > bt.coverage_pct:
-                st.caption(
-                    "Gabarito: periodos recentes mais estaveis — bom sinal "
-                    "para producao. A regra tende a funcionar bem daqui pra frente."
-                )
-            else:
-                st.caption(
-                    "Gabarito: periodos recentes menos estaveis — sinal de "
-                    "atencao. Considere reduzir N para focar em dados mais recentes "
-                    "ou investigar o que mudou."
-                )
-
-
 def _render_calibration(proposal_svc, values, dates, rule_key, metric_kind="numeric",
                         grain=None, series_profile=None):
     """Renderiza botao de calibracao explicavel, exibe resultado com justificativa e aplica parametros.
@@ -589,12 +391,30 @@ def _render_calibration(proposal_svc, values, dates, rule_key, metric_kind="nume
     if grain is None:
         grain = GrainType.DAILY
 
-    if st.button(
-        "Calibrar parametros",
-        key=f"btn_autotune_{rule_key}",
-        help="Analisa a serie e sugere a melhor combinacao de N, sigma e margem, "
-             "explicando cada decisao.",
-    ):
+    has_result = (
+        cache_key in st.session_state
+        and isinstance(st.session_state.get(cache_key), CalibrationResult)
+    )
+
+    # Buttons side by side: Calibrar + Aplicar
+    btn_c1, btn_c2 = st.columns(2)
+    with btn_c1:
+        calibrate_clicked = st.button(
+            "Calibrar parametros",
+            key=f"btn_autotune_{rule_key}",
+            help="Analisa a serie e sugere a melhor combinacao de N, sigma e margem.",
+        )
+    with btn_c2:
+        apply_enabled = has_result and st.session_state[cache_key].viable
+        apply_clicked = st.button(
+            "Aplicar parametros sugeridos",
+            key=f"apply_autotune_{rule_key}",
+            disabled=not apply_enabled,
+            help="Atualiza os sliders com os parametros recomendados."
+                 if apply_enabled else "Execute a calibracao primeiro.",
+        )
+
+    if calibrate_clicked:
         with st.spinner("Calibrando..."):
             result = calibrate(
                 values=values, dates=dates,
@@ -602,11 +422,22 @@ def _render_calibration(proposal_svc, values, dates, rule_key, metric_kind="nume
                 profile=series_profile,
             )
             st.session_state[cache_key] = result
+            has_result = True
+
+    if apply_clicked and apply_enabled:
+        result = st.session_state[cache_key]
+        st.session_state["_pending_autotune"] = {
+            "rule_key": rule_key,
+            "n_periods": result.n_periods,
+            "n_sigma": result.n_sigma,
+            "margin_pct": int(result.margin_pct * 100),
+            "margin_enabled": result.margin_enabled,
+        }
+        st.rerun()
 
-    if cache_key in st.session_state:
+    if has_result:
         result = st.session_state[cache_key]
         if not isinstance(result, CalibrationResult):
-            # Legado: se cache contem AutoTuneResult dict antigo, limpar e recalibrar
             del st.session_state[cache_key]
             return
 
@@ -687,21 +518,6 @@ def _render_calibration(proposal_svc, values, dates, rule_key, metric_kind="nume
                         f"Periodos mais recentes estao mais instaveis."
                     )
 
-        # Botao para aplicar parametros sugeridos nos sliders.
-        if result.viable and st.button(
-            "Aplicar parametros sugeridos",
-            key=f"apply_autotune_{rule_key}",
-            help="Atualiza os sliders com os parametros recomendados.",
-        ):
-            st.session_state["_pending_autotune"] = {
-                "rule_key": rule_key,
-                "n_periods": result.n_periods,
-                "n_sigma": result.n_sigma,
-                "margin_pct": int(result.margin_pct * 100),
-                "margin_enabled": result.margin_enabled,
-            }
-            st.rerun()
-
 
 # ---------------------------------------------------------------------------
 # Page config
@@ -1363,17 +1179,6 @@ with tab_numericas:
             # ---- Mean ----
             st.subheader(f"Mean -- {selected_col}")
 
-            with st.expander("O que e o dual guard?", expanded=False):
-                st.markdown(
-                    "O **dual guard** combina duas bandas de validacao com OR:\n\n"
-                    "1. **Banda sigma:** media +/- K desvios padrao — captura a variabilidade normal dos dados\n"
-                    "2. **Banda margem:** media +/- X% — captura variacao proporcional\n\n"
-                    "A regra passa se o valor estiver dentro de **qualquer uma** das bandas. "
-                    "Isso evita falsos positivos quando o dado e muito estavel (sigma proximo de 0).\n\n"
-                    "O grafico mostra ambas as bandas: azul (sigma) e verde (margem). "
-                    "Ajuste os parametros abaixo e observe como as bandas mudam."
-                )
-
             mean_n, mean_k, mean_margin, mean_buffer, mean_margin_on = _render_rule_params(
                 f"{_fp}_mean_{selected_col}",
                 n_min=_grain_policy.slider_n_min, n_max=_grain_policy.slider_n_max,
@@ -1412,9 +1217,6 @@ with tab_numericas:
                         margin_enabled=mean_margin_on,
                     )
 
-                    # Diagnostics panel (seasonality, change-point, outliers, recency)
-                    _render_diagnostics_panel(proposal)
-
                     _render_calibration(
                         proposal_svc, values, dates,
                         f"{_fp}_mean_{selected_col}", metric_kind="numeric",
@@ -1473,9 +1275,6 @@ with tab_numericas:
                         margin_enabled=std_margin_on,
                     )
 
-                    # Diagnostics panel (outliers, recency — seasonality/change-point already shown in Mean)
-                    _render_diagnostics_panel(proposal)
-
                     _render_calibration(
                         proposal_svc, values, dates,
                         f"{_fp}_stddev_{selected_col}", metric_kind="numeric",
diff --git a/tests/test_rule_explainer.py b/tests/test_rule_explainer.py
index c2e376c..84e9d13 100644
--- a/tests/test_rule_explainer.py
+++ b/tests/test_rule_explainer.py
@@ -152,6 +152,30 @@ class TestExplainRule:
         text = explain_rule(p)
         assert "20%" in text
 
+    def test_mean_margin_disabled_no_margin_text(self):
+        p = _make_proposal(RuleType.MEAN_DUAL_GUARD)
+        p.margin_enabled = False
+        text = explain_rule(p)
+        assert "**ou**" not in text
+        assert "% da media" not in text
+        assert "duas bandas" not in text
+
+    def test_stddev_margin_disabled_no_margin_text(self):
+        p = _make_proposal(RuleType.STDDEV_DUAL_GUARD)
+        p.margin_enabled = False
+        text = explain_rule(p)
+        assert "**ou**" not in text
+        assert "% da media" not in text
+        assert "duas bandas" not in text
+
+    def test_rowcount_margin_disabled_no_margin_text(self):
+        p = _make_proposal(RuleType.ROW_COUNT_DUAL_GUARD, column=None, table="tb_ops")
+        p.margin_enabled = False
+        text = explain_rule(p)
+        assert "**ou**" not in text
+        assert "% do volume" not in text
+        assert "duas bandas" not in text
+
 
 # ---------------------------------------------------------------------------
 # Tests: explain_rule_detail

