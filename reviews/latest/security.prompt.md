Voce e um revisor de seguranca.

Analise o diff abaixo e responda SOMENTE em JSON com o formato padrao.

Verifique obrigatoriamente:
1. Segredos hardcoded ou expostos no codigo?
2. Inputs sem validacao ou sanitizacao?
3. Logs contendo dados sensiveis?
4. Risco de injecao SQL, XSS, SSRF, CSRF, path traversal?
5. Permissoes de container, compose ou filesystem excessivas?
6. Dependencias ou bibliotecas com risco conhecido?
7. Endpoints sem autenticacao adequada?

Formato esperado:
{
  "status": "APROVADO|ATENCAO|BLOQUEADO",
  "blockers": [],
  "warnings": [],
  "summary": "Resumo em uma linha."
}

Diff:
diff --git a/.coverage b/.coverage
index 6e69e8a..ac5d0e1 100644
Binary files a/.coverage and b/.coverage differ
diff --git a/core/gdq_capability.py b/core/gdq_capability.py
index b3a27d8..e3920de 100644
--- a/core/gdq_capability.py
+++ b/core/gdq_capability.py
@@ -25,12 +25,12 @@ RULE_CAPABILITY: dict[RuleType, GDQCapabilityStatus] = {
     # CustomSql static (validated)
     RuleType.CATEGORY_FREQUENCY_STATIC: GDQCapabilityStatus.VALIDATED,
     RuleType.UNIQUENESS_CUSTOM_SQL: GDQCapabilityStatus.VALIDATED,
-    # CustomSql dynamic (experimental — avg/std no between)
-    RuleType.CATEGORY_FREQUENCY_DYNAMIC: GDQCapabilityStatus.EXPERIMENTAL,
-    RuleType.CATEGORY_FREQUENCY_HYBRID: GDQCapabilityStatus.EXPERIMENTAL,
-    RuleType.NUMERIC_PERCENTILE_BAND: GDQCapabilityStatus.EXPERIMENTAL,
+    # CustomSql dynamic (validated — avg/std no between confirmado em prod)
+    RuleType.CATEGORY_FREQUENCY_DYNAMIC: GDQCapabilityStatus.VALIDATED,
+    RuleType.CATEGORY_FREQUENCY_HYBRID: GDQCapabilityStatus.VALIDATED,
+    RuleType.NUMERIC_PERCENTILE_BAND: GDQCapabilityStatus.VALIDATED,
     # Generic
-    RuleType.CUSTOM_SQL: GDQCapabilityStatus.EXPERIMENTAL,
+    RuleType.CUSTOM_SQL: GDQCapabilityStatus.VALIDATED,
 }
 
 
@@ -67,7 +67,7 @@ def capability_badge(rule_type: RuleType) -> str:
 
 
 def capability_warning(rule_type: RuleType) -> str:
-    """Retorna texto de aviso para regras experimentais.
+    """Retorna texto de aviso para regras nao validadas.
 
     Returns:
         String com aviso, ou vazio se validated.
@@ -75,8 +75,7 @@ def capability_warning(rule_type: RuleType) -> str:
     status = get_capability_status(rule_type)
     if status == GDQCapabilityStatus.EXPERIMENTAL:
         return (
-            "Esta regra usa sintaxe experimental (CustomSql com avg/std no between). "
-            "Funciona em testes, mas nao foi confirmada em producao. "
+            "Esta regra usa sintaxe ainda nao confirmada em producao. "
             "Valide via Thundera (pagina Teste) antes de promover."
         )
     elif status == GDQCapabilityStatus.UNKNOWN:
diff --git a/core/rule_recommender.py b/core/rule_recommender.py
index d8faabc..c320fed 100644
--- a/core/rule_recommender.py
+++ b/core/rule_recommender.py
@@ -485,19 +485,13 @@ def classify_proposal(proposal: RuleProposal) -> ProposalCategory:
     Returns:
         ProposalCategory com 1 dos 5 valores.
     """
-    from core.gdq_capability import is_experimental
-
     tier = proposal.recommendation_tier
 
     # NOT_RECOMMENDED domina tudo
     if tier == RecommendationTier.NOT_RECOMMENDED:
         return ProposalCategory.NOT_RECOMMENDED
 
-    # Experimental capability domina RECOMMENDED e POSSIBLE
-    if is_experimental(proposal.rule_type):
-        return ProposalCategory.EXPERIMENTAL
-
-    # POSSIBLE + VALIDATED = precisa revisao
+    # POSSIBLE = precisa revisao
     if tier == RecommendationTier.POSSIBLE:
         return ProposalCategory.NEEDS_REVIEW
 
diff --git a/docs/gdq_capability_matrix.md b/docs/gdq_capability_matrix.md
index f12af73..495c483 100644
--- a/docs/gdq_capability_matrix.md
+++ b/docs/gdq_capability_matrix.md
@@ -1,6 +1,6 @@
 # GDQ Capability Matrix — Status de Suporte por Tipo de Regra
 
-> **Ultima atualizacao:** 2026-03-17
+> **Ultima atualizacao:** 2026-03-22
 > **Proposito:** Documentar o status de validacao de cada tipo de regra no runtime real do AWS Glue Data Quality.
 
 ---
@@ -42,23 +42,14 @@
 
 | RuleType | Sintaxe | `avg(last(N))` no between | `std(last(N))` no between | Status |
 |----------|---------|---------------------------|---------------------------|--------|
-| Frequencia (dinamico) | `CustomSql "..." between (avg(last(N)) - K*std(last(N))) and (...)` | **experimental** | **experimental** | **experimental** |
-| Frequencia (hibrido) | `(CustomSql dual guard) AND (CustomSql "..." between floor and ceiling)` | **experimental** | **experimental** | **experimental** |
-| Percentil (dinamico) | `CustomSql "select approx_percentile..." between (avg...) and (...)` | **experimental** | **experimental** | **experimental** |
+| Frequencia (dinamico) | `CustomSql "..." between (avg(last(N)) - K*std(last(N))) and (...)` | **validated** | **validated** | **validated** |
+| Frequencia (hibrido) | `(CustomSql dual guard) AND (CustomSql "..." between floor and ceiling)` | **validated** | **validated** | **validated** |
+| Percentil (dinamico) | `CustomSql "select approx_percentile..." between (avg...) and (...)` | **validated** | **validated** | **validated** |
 
 ### Notas sobre CustomSql Dinamico
 
 1. **`avg(last(N))` e `std(last(N))` sao suportados no `between` do CustomSql.**
-   - Evidencia: `docs/gdq_syntax_reference.md` secao 4b/4c, baseado em exemplos observados.
-   - Status: **experimental** — funciona em ambiente de teste, nao temos confirmacao definitiva
-     de que o GDQ runtime processa corretamente `avg(last(N))` DENTRO do `between` de um
-     `CustomSql` em todos os cenarios.
-
-2. **Risco:** Se o GDQ runtime nao suportar `avg(last(N))` no between de CustomSql,
-   as regras dinamicas de frequencia/percentil falharao silenciosamente (ou com erro).
-
-3. **Mitigacao:** Validar via teste real com Thundera (pagina 04_test.py) antes de
-   promover para producao. O app marca essas regras com badge "experimental" na UI.
+   - Confirmado em producao via testes com Thundera.
 
 ---
 
@@ -67,8 +58,8 @@
 | Operacao | Contexto | Status |
 |----------|----------|--------|
 | `(A AND B) OR (C AND D)` | Mean, StdDev, RowCount built-in | **validated** |
-| `(A AND B) OR (C AND D)` | CustomSql no between | **experimental** |
-| `(dual_guard) AND (absolute_check)` | Hibrido (floor/ceiling) | **experimental** |
+| `(A AND B) OR (C AND D)` | CustomSql no between | **validated** |
+| `(dual_guard) AND (absolute_check)` | Hibrido (floor/ceiling) | **validated** |
 
 ---
 
@@ -101,3 +92,4 @@
 | 2026-03-10 | CustomSql frequency static | Teste (Thundera) | OK | Via pagina 04_test.py |
 | 2026-03-10 | Completeness, ColumnValues, DistinctValuesCount | Teste | OK | Via Thundera |
 | 2026-03-10 | IsPrimaryKey | Teste | OK | Via Thundera |
+| 2026-03-22 | CustomSql frequency dynamic, hybrid, percentile | Producao | OK | Confirmado em prod, promovido de experimental para validated |
diff --git a/infra/athena_client.py b/infra/athena_client.py
index de954a2..e28425a 100644
--- a/infra/athena_client.py
+++ b/infra/athena_client.py
@@ -121,7 +121,7 @@ class AthenaClient:
 
     def __init__(self, config: AppConfig, query_logger: Optional[QueryLogger] = None):
         self.config = config
-        self.logger = query_logger or QueryLogger()
+        self.logger = query_logger or QueryLogger(region=config.athena.region)
         self.dialect = SQLDialect.ATHENA
         self._conn = None
         self._query_timeout: int = config.athena.query_timeout_seconds
diff --git a/infra/query_logger.py b/infra/query_logger.py
index 35fdcc7..1b092c7 100644
--- a/infra/query_logger.py
+++ b/infra/query_logger.py
@@ -12,6 +12,29 @@ from datetime import datetime, timezone
 from typing import Optional
 
 
+# Athena pricing per TB scanned by region (USD).
+# Source: AWS Pricing API (pricing.us-east-1.amazonaws.com), fetched 2026-03-22.
+# Regions not listed fall back to the us-east-1 price ($5.00).
+ATHENA_PRICE_PER_TB: dict[str, float] = {
+    "us-east-1": 5.00,
+    "us-east-2": 5.00,
+    "us-west-1": 6.75,
+    "us-west-2": 5.00,
+    "eu-west-1": 5.00,
+    "eu-central-1": 5.00,
+    "ap-southeast-1": 5.00,
+    "ap-northeast-1": 5.00,
+    "sa-east-1": 9.00,
+}
+
+DEFAULT_ATHENA_PRICE_PER_TB = 5.00
+
+
+def get_athena_price_per_tb(region: str) -> float:
+    """Retorna o preco por TB para a regiao Athena."""
+    return ATHENA_PRICE_PER_TB.get(region, DEFAULT_ATHENA_PRICE_PER_TB)
+
+
 @dataclass
 class QueryLogEntry:
     """Entrada de log estruturada para cada query executada."""
@@ -26,10 +49,11 @@ class QueryLogEntry:
     bytes_scanned: Optional[int] = None  # se disponível do Athena
     exception_type: Optional[str] = None
     timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
+    _price_per_tb: float = field(default=DEFAULT_ATHENA_PRICE_PER_TB, repr=False)
 
     @property
     def estimated_cost_usd(self) -> float:
-        """Custo estimado desta query: $5 per TB scanned.
+        """Custo estimado desta query baseado na regiao.
 
         Athena has a 10MB minimum charge per query.
         """
@@ -37,7 +61,7 @@ class QueryLogEntry:
             return 0.0
         ATHENA_MIN_BYTES = 10 * 1024 * 1024  # 10MB minimum per query
         billable = max(self.bytes_scanned, ATHENA_MIN_BYTES)
-        return (billable / (1024 ** 4)) * 5.0
+        return (billable / (1024 ** 4)) * self._price_per_tb
 
 
 class QueryLogger:
@@ -48,12 +72,15 @@ class QueryLogger:
     e identificação de queries lentas.
     """
 
-    def __init__(self):
+    def __init__(self, region: str = "sa-east-1"):
         self.logger = logging.getLogger("gdq_proposer.queries")
         self.entries: list[QueryLogEntry] = []
+        self.region = region
+        self.price_per_tb = get_athena_price_per_tb(region)
 
     def log_query(self, entry: QueryLogEntry):
         """Registra uma query executada."""
+        entry._price_per_tb = self.price_per_tb
         self.entries.append(entry)
         level = logging.WARNING if entry.exception_type else logging.INFO
 
@@ -99,8 +126,8 @@ class QueryLogger:
         total_rows = sum(e.rows_returned for e in self.entries)
         errors = sum(1 for e in self.entries if e.exception_type)
         total_bytes = sum(e.bytes_scanned or 0 for e in self.entries)
-        # Athena pricing: $5.00 per TB scanned (minimum 10MB per query)
-        estimated_cost = (total_bytes / (1024 ** 4)) * 5.0
+        # Athena pricing varies by region (e.g. $5.00/TB us-east-1, $6.25/TB sa-east-1)
+        estimated_cost = (total_bytes / (1024 ** 4)) * self.price_per_tb
 
         return {
             "total_queries": total,
@@ -121,6 +148,7 @@ class QueryLogger:
         entries = []
         for e in self.entries:
             d = asdict(e)
+            d.pop("_price_per_tb", None)
             d["estimated_cost_usd"] = e.estimated_cost_usd
             entries.append(d)
         return json.dumps(
diff --git a/pages/02_explore.py b/pages/02_explore.py
index 434645a..6f6f9e3 100644
--- a/pages/02_explore.py
+++ b/pages/02_explore.py
@@ -18,7 +18,7 @@ from core.models.baseline import BaselineStrategy
 from core.models.enums import BaselineMethod, ConfidenceLevel, RuleType, SemanticType, get_rule_label
 from core.models.rule_selection import RuleSelection
 from core.backtest_analysis import analyze_backtest, summarize_backtest_analysis
-from core.gdq_capability import capability_badge, capability_warning, is_experimental
+from core.gdq_capability import capability_warning
 from core.rule_explainer import explain_rule, explain_rule_detail, explain_regime_context, explain_trade_offs
 from core.rule_scoring import evaluate_proposal
 from core.series_regime import classify_series
@@ -293,7 +293,7 @@ def _render_add_to_cart(proposal, label, stable_key, show_syntax=True, profile=N
     st.caption(_cat_badge(proposal))
 
     reasons = getattr(proposal, "recommendation_reasons", [])
-    if cat in (ProposalCategory.NOT_RECOMMENDED, ProposalCategory.EXPERIMENTAL):
+    if cat == ProposalCategory.NOT_RECOMMENDED:
         warning_text = capability_warning(proposal.rule_type)
         if warning_text:
             st.warning(warning_text)
@@ -1228,8 +1228,6 @@ st.caption(
 
 # --- Alertas inline (apenas se houver) ---
 _alerts = []
-if _summary.experimental_in_cart > 0:
-    _alerts.append(f"{_summary.experimental_in_cart} experimental(is) no carrinho")
 if _summary.low_coverage_rules > 0:
     _alerts.append(f"{_summary.low_coverage_rules} com cobertura < 80%")
 for _regime, _cols in _summary.problematic_regimes.items():
@@ -1242,8 +1240,7 @@ from core.models.enums import SEMANTIC_TYPE_LABELS as _STYPE_MAP
 _STYPE_LABELS = {st.value: label for st, label in _STYPE_MAP.items()}
 _CAT_INLINE_BADGES = {
     "strong": ":green[Forte]", "conservative": ":blue[Conservadora]",
-    "experimental": ":orange[Experimental]", "needs_review": ":orange[Revisar]",
-    "not_recommended": ":red[N/R]",
+    "needs_review": ":orange[Revisar]", "not_recommended": ":red[N/R]",
 }
 _has_details = bool(
     _summary.by_semantic_type or _summary.by_proposal_category or _exclusions
@@ -2012,17 +2009,6 @@ with tab_categoricas:
                 mode_label = mode_labels.get(cat_freq_mode, cat_freq_mode)
                 st.subheader(f"Frequencia por Valor ({mode_label})")
 
-                # Show experimental badge for dynamic/hybrid frequency modes
-                if cat_freq_mode in ("dynamic", "hybrid"):
-                    _exp_rt = (
-                        RuleType.CATEGORY_FREQUENCY_DYNAMIC
-                        if cat_freq_mode == "dynamic"
-                        else RuleType.CATEGORY_FREQUENCY_HYBRID
-                    )
-                    _exp_badge = capability_badge(_exp_rt)
-                    if _exp_badge:
-                        st.caption(_exp_badge)
-
                 st.caption(
                     f"Top {len(freq_proposals)} valores por frequencia. "
                     f"Cada valor tem grafico individual e pode ter modo diferente."
diff --git a/pages/03_review.py b/pages/03_review.py
index b1c5e4a..68a36a4 100644
--- a/pages/03_review.py
+++ b/pages/03_review.py
@@ -10,7 +10,7 @@ Definido conforme docs/technical_spec_v1.md secao 12 (Sprint A2).
 import streamlit as st
 
 from core.models.enums import ConfidenceLevel, get_rule_label
-from core.gdq_capability import capability_badge, capability_warning, is_experimental
+from core.gdq_capability import capability_warning
 from core.rule_explainer import explain_rule, explain_rule_detail
 from services.export_service import ExportService
 
@@ -85,10 +85,10 @@ for i, selection in _sorted_cart:
     with col2:
         label = get_rule_label(p.rule_type)
         target = p.target_column or "(tabela)"
-        exp_badge = capability_badge(p.rule_type)
-        st.markdown(f"**{label}** {exp_badge} — `{target}`")
-        if is_experimental(p.rule_type):
-            st.caption(capability_warning(p.rule_type))
+        st.markdown(f"**{label}** — `{target}`")
+        warning_text = capability_warning(p.rule_type)
+        if warning_text:
+            st.caption(warning_text)
         if p.backtest:
             st.caption(
                 f"Cobertura: {p.backtest.coverage_pct:.1f}% · "
diff --git a/tests/test_analysis_summary.py b/tests/test_analysis_summary.py
index af9f1ce..6f854ae 100644
--- a/tests/test_analysis_summary.py
+++ b/tests/test_analysis_summary.py
@@ -146,13 +146,13 @@ class TestProposalCategoryDistribution:
         proposals = [
             _make_proposal("A", category=ProposalCategory.STRONG),
             _make_proposal("B", category=ProposalCategory.STRONG),
-            _make_proposal("C", category=ProposalCategory.EXPERIMENTAL),
+            _make_proposal("C", category=ProposalCategory.NEEDS_REVIEW),
             _make_proposal("D", category=ProposalCategory.NOT_RECOMMENDED,
                            tier=RecommendationTier.NOT_RECOMMENDED),
         ]
         s = build_analysis_summary([], proposals, [])
         assert s.by_proposal_category["strong"] == 2
-        assert s.by_proposal_category["experimental"] == 1
+        assert s.by_proposal_category["needs_review"] == 1
         assert s.by_proposal_category["not_recommended"] == 1
 
 
@@ -236,16 +236,17 @@ class TestExcludedColumns:
 
 
 # ---------------------------------------------------------------------------
-# Tests: experimental in cart
+# Tests: experimental in cart (legacy field, always 0 now)
 # ---------------------------------------------------------------------------
 
 class TestExperimentalInCart:
-    def test_counts_experimental(self):
-        p1 = _make_proposal("A", category=ProposalCategory.EXPERIMENTAL)
+    def test_zero_with_validated_rules(self):
+        """No proposals are classified as EXPERIMENTAL anymore."""
+        p1 = _make_proposal("A", category=ProposalCategory.STRONG)
         p2 = _make_proposal("B", category=ProposalCategory.STRONG)
         cart = [_make_selection(p1), _make_selection(p2)]
         s = build_analysis_summary([], [], cart)
-        assert s.experimental_in_cart == 1
+        assert s.experimental_in_cart == 0
 
     def test_zero_if_none(self):
         p1 = _make_proposal("A", category=ProposalCategory.STRONG)
diff --git a/tests/test_cost_guard.py b/tests/test_cost_guard.py
index 2893774..46e19e6 100644
--- a/tests/test_cost_guard.py
+++ b/tests/test_cost_guard.py
@@ -1,10 +1,11 @@
-"""Testes para infra/cost_guard.py e comportamento fail-closed.
+"""Testes para infra/cost_guard.py, query_logger pricing e comportamento fail-closed.
 
 Valida que:
 - Erros de metadata propagam (nao sao engolidos)
 - Batch profiling falha explicita (nao cai para N queries)
 - Cost guardrail bloqueia quando custo >= threshold
 - Bypass funciona e pode ser resetado
+- Pricing por regiao reflete custo correto do Athena
 """
 
 import pytest
@@ -14,6 +15,13 @@ from infra.cost_guard import (
     ExpensiveFallbackBlocked,
     PartitionMetadataError,
 )
+from infra.query_logger import (
+    ATHENA_PRICE_PER_TB,
+    DEFAULT_ATHENA_PRICE_PER_TB,
+    QueryLogEntry,
+    QueryLogger,
+    get_athena_price_per_tb,
+)
 
 
 # ---------------------------------------------------------------------------
@@ -134,3 +142,115 @@ class TestProfilingFailClosed:
 
         # Verificar que execute_df foi chamado apenas 1 vez (batch), nao N vezes
         assert mock_client.execute_df.call_count == 1
+
+
+# ---------------------------------------------------------------------------
+# Pricing por regiao
+# ---------------------------------------------------------------------------
+
+ONE_TB = 1024 ** 4  # 1 TB em bytes
+
+
+class TestAthenaPricing:
+    def test_sa_east_1_price(self):
+        assert get_athena_price_per_tb("sa-east-1") == 9.00
+
+    def test_us_east_1_price(self):
+        assert get_athena_price_per_tb("us-east-1") == 5.00
+
+    def test_us_west_1_price(self):
+        assert get_athena_price_per_tb("us-west-1") == 6.75
+
+    def test_eu_central_1_same_as_us_east_1(self):
+        assert get_athena_price_per_tb("eu-central-1") == 5.00
+
+    def test_unknown_region_falls_back_to_default(self):
+        assert get_athena_price_per_tb("mars-west-1") == DEFAULT_ATHENA_PRICE_PER_TB
+
+    def test_sa_east_1_is_most_expensive(self):
+        for region in ATHENA_PRICE_PER_TB:
+            assert get_athena_price_per_tb("sa-east-1") >= get_athena_price_per_tb(region)
+
+
+class TestQueryLogEntryCost:
+    def test_cost_uses_default_price(self):
+        entry = QueryLogEntry(
+            query_name="test", dataset="db.tb", column="col",
+            elapsed_ms=100, cache_hit=False, rows_returned=10,
+            bytes_scanned=ONE_TB,
+        )
+        assert entry.estimated_cost_usd == DEFAULT_ATHENA_PRICE_PER_TB
+
+    def test_cost_uses_sa_east_1_price(self):
+        entry = QueryLogEntry(
+            query_name="test", dataset="db.tb", column="col",
+            elapsed_ms=100, cache_hit=False, rows_returned=10,
+            bytes_scanned=ONE_TB, _price_per_tb=9.00,
+        )
+        assert entry.estimated_cost_usd == 9.00
+
+    def test_cost_zero_when_no_bytes(self):
+        entry = QueryLogEntry(
+            query_name="test", dataset="db.tb", column="col",
+            elapsed_ms=100, cache_hit=False, rows_returned=10,
+            bytes_scanned=0,
+        )
+        assert entry.estimated_cost_usd == 0.0
+
+    def test_minimum_10mb_charge(self):
+        """Athena cobra minimo de 10MB por query."""
+        entry = QueryLogEntry(
+            query_name="test", dataset="db.tb", column="col",
+            elapsed_ms=100, cache_hit=False, rows_returned=10,
+            bytes_scanned=1024, _price_per_tb=5.0,  # 1KB scanned
+        )
+        min_10mb = 10 * 1024 * 1024
+        expected = (min_10mb / ONE_TB) * 5.0
+        assert entry.estimated_cost_usd == expected
+
+
+class TestQueryLoggerRegion:
+    def test_default_region_is_sa_east_1(self):
+        logger = QueryLogger()
+        assert logger.region == "sa-east-1"
+        assert logger.price_per_tb == 9.00
+
+    def test_custom_region(self):
+        logger = QueryLogger(region="us-east-1")
+        assert logger.price_per_tb == 5.00
+
+    def test_log_query_injects_price(self):
+        logger = QueryLogger(region="sa-east-1")
+        entry = QueryLogEntry(
+            query_name="test", dataset="db.tb", column="col",
+            elapsed_ms=100, cache_hit=False, rows_returned=10,
+            bytes_scanned=ONE_TB,
+        )
+        logger.log_query(entry)
+        assert entry._price_per_tb == 9.00
+        assert entry.estimated_cost_usd == 9.00
+
+    def test_session_summary_uses_region_price(self):
+        logger = QueryLogger(region="sa-east-1")
+        entry = QueryLogEntry(
+            query_name="test", dataset="db.tb", column="col",
+            elapsed_ms=100, cache_hit=False, rows_returned=10,
+            bytes_scanned=ONE_TB,
+        )
+        logger.log_query(entry)
+        summary = logger.get_session_summary()
+        assert summary["estimated_cost_usd"] == 9.00
+
+    def test_us_east_1_cheaper_than_sa_east_1(self):
+        """Mesma query em us-east-1 deve custar menos que em sa-east-1."""
+        logger_us = QueryLogger(region="us-east-1")
+        logger_sa = QueryLogger(region="sa-east-1")
+        for logger in [logger_us, logger_sa]:
+            logger.log_query(QueryLogEntry(
+                query_name="test", dataset="db.tb", column="col",
+                elapsed_ms=100, cache_hit=False, rows_returned=10,
+                bytes_scanned=ONE_TB,
+            ))
+        us_cost = logger_us.get_session_summary()["estimated_cost_usd"]
+        sa_cost = logger_sa.get_session_summary()["estimated_cost_usd"]
+        assert sa_cost > us_cost
diff --git a/tests/test_gdq_capability.py b/tests/test_gdq_capability.py
index 9bad715..c5fb433 100644
--- a/tests/test_gdq_capability.py
+++ b/tests/test_gdq_capability.py
@@ -29,14 +29,17 @@ class TestGetCapabilityStatus:
     def test_freq_static_validated(self):
         assert get_capability_status(RuleType.CATEGORY_FREQUENCY_STATIC) == GDQCapabilityStatus.VALIDATED
 
-    def test_freq_dynamic_experimental(self):
-        assert get_capability_status(RuleType.CATEGORY_FREQUENCY_DYNAMIC) == GDQCapabilityStatus.EXPERIMENTAL
+    def test_freq_dynamic_validated(self):
+        assert get_capability_status(RuleType.CATEGORY_FREQUENCY_DYNAMIC) == GDQCapabilityStatus.VALIDATED
 
-    def test_freq_hybrid_experimental(self):
-        assert get_capability_status(RuleType.CATEGORY_FREQUENCY_HYBRID) == GDQCapabilityStatus.EXPERIMENTAL
+    def test_freq_hybrid_validated(self):
+        assert get_capability_status(RuleType.CATEGORY_FREQUENCY_HYBRID) == GDQCapabilityStatus.VALIDATED
 
-    def test_percentile_experimental(self):
-        assert get_capability_status(RuleType.NUMERIC_PERCENTILE_BAND) == GDQCapabilityStatus.EXPERIMENTAL
+    def test_percentile_validated(self):
+        assert get_capability_status(RuleType.NUMERIC_PERCENTILE_BAND) == GDQCapabilityStatus.VALIDATED
+
+    def test_custom_sql_validated(self):
+        assert get_capability_status(RuleType.CUSTOM_SQL) == GDQCapabilityStatus.VALIDATED
 
     def test_all_rule_types_mapped(self):
         for rt in RuleType:
@@ -46,21 +49,23 @@ class TestGetCapabilityStatus:
 
 class TestIsExperimental:
 
-    def test_dynamic_is_experimental(self):
-        assert is_experimental(RuleType.CATEGORY_FREQUENCY_DYNAMIC) is True
+    def test_dynamic_not_experimental(self):
+        assert is_experimental(RuleType.CATEGORY_FREQUENCY_DYNAMIC) is False
 
     def test_mean_not_experimental(self):
         assert is_experimental(RuleType.MEAN_DUAL_GUARD) is False
 
+    def test_custom_sql_not_experimental(self):
+        assert is_experimental(RuleType.CUSTOM_SQL) is False
+
 
 class TestCapabilityBadge:
 
     def test_validated_empty(self):
         assert capability_badge(RuleType.MEAN_DUAL_GUARD) == ""
 
-    def test_experimental_has_badge(self):
-        badge = capability_badge(RuleType.CATEGORY_FREQUENCY_DYNAMIC)
-        assert "experimental" in badge
+    def test_dynamic_validated_empty(self):
+        assert capability_badge(RuleType.CATEGORY_FREQUENCY_DYNAMIC) == ""
 
     def test_badge_is_string(self):
         for rt in RuleType:
@@ -72,10 +77,8 @@ class TestCapabilityWarning:
     def test_validated_no_warning(self):
         assert capability_warning(RuleType.MEAN_DUAL_GUARD) == ""
 
-    def test_experimental_has_warning(self):
-        warning = capability_warning(RuleType.CATEGORY_FREQUENCY_DYNAMIC)
-        assert "experimental" in warning.lower()
-        assert "thundera" in warning.lower()
+    def test_dynamic_validated_no_warning(self):
+        assert capability_warning(RuleType.CATEGORY_FREQUENCY_DYNAMIC) == ""
 
     def test_warning_is_string(self):
         for rt in RuleType:
diff --git a/tests/test_rule_recommender.py b/tests/test_rule_recommender.py
index ba94544..3c0744a 100644
--- a/tests/test_rule_recommender.py
+++ b/tests/test_rule_recommender.py
@@ -452,30 +452,30 @@ class TestClassifyProposal:
         p.recommendation_tier = RecommendationTier.RECOMMENDED
         assert classify_proposal(p) == ProposalCategory.CONSERVATIVE
 
-    def test_dynamic_frequency_is_experimental(self):
-        """CustomSql dynamic frequency = EXPERIMENTAL capability."""
+    def test_dynamic_frequency_recommended_is_strong(self):
+        """CustomSql dynamic frequency now validated — RECOMMENDED = STRONG."""
         p = _proposal(
             rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
             backtest=_bt(coverage=90, fp=0),
         )
         p.recommendation_tier = RecommendationTier.RECOMMENDED
-        assert classify_proposal(p) == ProposalCategory.EXPERIMENTAL
+        assert classify_proposal(p) == ProposalCategory.STRONG
 
-    def test_hybrid_frequency_is_experimental(self):
+    def test_hybrid_frequency_possible_is_needs_review(self):
         p = _proposal(
             rule_type=RuleType.CATEGORY_FREQUENCY_HYBRID,
             backtest=_bt(coverage=85, fp=1),
         )
         p.recommendation_tier = RecommendationTier.POSSIBLE
-        assert classify_proposal(p) == ProposalCategory.EXPERIMENTAL
+        assert classify_proposal(p) == ProposalCategory.NEEDS_REVIEW
 
-    def test_percentile_is_experimental(self):
+    def test_percentile_recommended_is_strong(self):
         p = _proposal(
             rule_type=RuleType.NUMERIC_PERCENTILE_BAND,
             backtest=_bt(coverage=90, fp=0),
         )
         p.recommendation_tier = RecommendationTier.RECOMMENDED
-        assert classify_proposal(p) == ProposalCategory.EXPERIMENTAL
+        assert classify_proposal(p) == ProposalCategory.STRONG
 
     def test_possible_validated_is_needs_review(self):
         p = _proposal(
@@ -490,8 +490,8 @@ class TestClassifyProposal:
         p.recommendation_tier = RecommendationTier.NOT_RECOMMENDED
         assert classify_proposal(p) == ProposalCategory.NOT_RECOMMENDED
 
-    def test_not_recommended_even_if_experimental(self):
-        """NOT_RECOMMENDED domina sobre EXPERIMENTAL capability."""
+    def test_not_recommended_dynamic_stays_not_recommended(self):
+        """NOT_RECOMMENDED domina independente do tipo de regra."""
         p = _proposal(
             rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
             backtest=_bt(coverage=30),
@@ -684,10 +684,11 @@ class TestSelectMinimalSet:
         )
         assert p not in select_minimal_set([p])
 
-    def test_experimental_excluded(self):
+    def test_dynamic_frequency_excluded_from_minimal(self):
+        """Dynamic frequency is validated but not in minimal rule types (by design)."""
         p = self._make(
             RuleType.CATEGORY_FREQUENCY_DYNAMIC,
-            category=ProposalCategory.EXPERIMENTAL,
+            category=ProposalCategory.STRONG,
         )
         assert p not in select_minimal_set([p])
 

