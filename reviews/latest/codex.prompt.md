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
    "Arquivo binario .coverage incluido no diff \u2014 nao deveria ser commitado (adicionar ao .gitignore se ausente)",
    "Tabela ATHENA_PRICE_PER_TB hardcoded em query_logger.py \u2014 se precos mudarem, requer deploy para atualizar"
  ],
  "summary": "Promocao de regras CustomSql de experimental para validated com pricing regional no query_logger \u2014 separacao source/deploy/runtime preservada, sem acoplamento excessivo."
}

== security.json ==
{
  "status": "APROVADO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage (binario) incluido no diff \u2014 deve estar no .gitignore para evitar vazamento de paths locais ou metricas de cobertura.",
    "Precos hardcoded em ATHENA_PRICE_PER_TB podem ficar desatualizados \u2014 considerar validacao periodica contra AWS Pricing API."
  ],
  "summary": "Diff seguro: promove regras de experimental para validated, adiciona pricing por regiao sem segredos ou inputs inseguros."
}

== tests.json ==
{
  "status": "APROVADO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage binario incluido no diff \u2014 nao deveria ser commitado (adicionar ao .gitignore se ausente)",
    "QueryLogEntry._price_per_tb com valor default DEFAULT_ATHENA_PRICE_PER_TB (5.00) diverge do default do QueryLogger (sa-east-1 = 9.00) \u2014 entries criadas fora do logger terao preco incorreto ate log_query() injetar o valor",
    "Tabela ATHENA_PRICE_PER_TB hardcoded \u2014 se precos AWS mudarem, requer deploy para atualizar",
    "Teste test_dynamic_frequency_excluded_from_minimal valida que STRONG e excluido do minimal set, mas o motivo (by design) merece comentario no codigo de producao (select_minimal_set) alem do teste"
  ],
  "summary": "Mudancas consistentes: promocao experimental\u2192validated com testes atualizados, pricing regional bem coberto com 12 novos testes deterministicos."
}

== release-ops.json ==
{
  "status": "APROVADO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage binario incluido no diff \u2014 nao deve ser commitado (adicionar ao .gitignore se ausente)",
    "QueryLogger default region mudou para sa-east-1 ($9/TB) \u2014 confirmar que testes existentes nao assumiam $5/TB em assercoes fora deste diff",
    "Pricing hardcoded no codigo (ATHENA_PRICE_PER_TB) \u2014 se precos AWS mudarem, requer novo deploy para atualizar"
  ],
  "summary": "Promocao de regras CustomSql de experimental para validated, pricing Athena por regiao no query_logger, e limpeza de UI \u2014 mudancas seguras, sem migracao, sem impacto em deploy/compose/healthcheck."
}

Diff para revisar:
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
 

Contexto do projeto:
# Project Context

- Project: `gdq-proposer`
- Generated at: `2026-03-23T02:33:39Z`
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
 M infra/query_logger.py
 M reviews/latest/architecture.json
 M reviews/latest/architecture.prompt.md
 M reviews/latest/architecture.raw.txt
 M reviews/latest/codex.json
 M reviews/latest/codex.prompt.md
 M reviews/latest/codex.raw.txt
 M reviews/latest/diff.patch
 M reviews/latest/project-context.md
 M reviews/latest/release-ops.json
 M reviews/latest/release-ops.prompt.md
 M reviews/latest/release-ops.raw.txt
 M reviews/latest/security.json
 M reviews/latest/security.prompt.md
 M reviews/latest/security.raw.txt
 M reviews/latest/summary.json
 M reviews/latest/tests.json
 M reviews/latest/tests.prompt.md
 M reviews/latest/tests.raw.txt

```

## Diff Stat vs HEAD

```text
 infra/query_logger.py                 |    2 +-
 reviews/latest/architecture.json      |   10 +-
 reviews/latest/architecture.prompt.md | 1027 ++++++++++++++++++++------------
 reviews/latest/architecture.raw.txt   |   10 +-
 reviews/latest/codex.json             |   11 +-
 reviews/latest/codex.prompt.md        | 1060 ++++++++++++++++++++-------------
 reviews/latest/codex.raw.txt          |    2 +-
 reviews/latest/diff.patch             | 1027 ++++++++++++++++++++------------
 reviews/latest/project-context.md     |   24 +-
 reviews/latest/release-ops.json       |    7 +-
 reviews/latest/release-ops.prompt.md  | 1027 ++++++++++++++++++++------------
 reviews/latest/release-ops.raw.txt    |    7 +-
 reviews/latest/security.json          |    9 +-
 reviews/latest/security.prompt.md     | 1027 ++++++++++++++++++++------------
 reviews/latest/security.raw.txt       |    9 +-
 reviews/latest/summary.json           |   57 +-
 reviews/latest/tests.json             |   13 +-
 reviews/latest/tests.prompt.md        | 1027 ++++++++++++++++++++------------
 reviews/latest/tests.raw.txt          |   13 +-
 19 files changed, 3852 insertions(+), 2517 deletions(-)

```
