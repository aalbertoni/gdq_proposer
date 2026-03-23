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
  "status": "ATENCAO",
  "blockers": [],
  "warnings": [
    "Arquivo binario .coverage incluido no diff \u2014 nao deveria ser commitado (adicionar ao .gitignore).",
    "cleanup-staging-after-prod executa `sudo /home/aalbertoni/.config/homelab/scripts/stack-down` \u2014 path hardcoded com usuario especifico e uso de sudo; considerar wrapper no Taskfile ou variavel de ambiente.",
    "push-after-staging faz `git push` sem especificar remote/branch \u2014 pode empurrar para branch errada se tracking nao estiver configurado.",
    "pages/07_query_log.py acessa `client.logger.entries` e `client.logger.export_json()` \u2014 contrato do logger nao visivel no diff; se logger ainda nao expoe esses atributos, vai quebrar em runtime."
  ],
  "summary": "Mudancas de governanca (push-after-staging, cleanup-staging) e nova pagina query_log sao coerentes com a arquitetura; nenhum bloqueio, mas .coverage no diff e path hardcoded com sudo merecem atencao."
}

== security.json ==
{
  "status": "ATENCAO",
  "blockers": [],
  "warnings": [
    "O arquivo .coverage (binario) esta no diff e nao deveria ser commitado \u2014 adicionar ao .gitignore se ainda nao estiver.",
    "pages/07_query_log.py exibe SQL completo via st.code(entry.sql) \u2014 verificar que o SQL nao contem credenciais ou tokens inline antes de exibir ao usuario.",
    "Taskfile.yml cleanup-staging-after-prod executa sudo com path hardcoded (/home/aalbertoni/.config/homelab/scripts/stack-down) \u2014 path especifico de usuario pode ser um risco de path traversal se o script for modificavel por outros usuarios."
  ],
  "summary": "Mudancas de governanca e query log sem bloqueadores criticos; atentar ao .coverage no versionamento e ao SQL exibido no log."
}

== tests.json ==
{
  "status": "ATENCAO",
  "blockers": [],
  "warnings": [
    "Nova pagina pages/07_query_log.py (218 linhas) nao possui nenhum teste unitario. Funcao publica _describe_query_purpose() deveria ter teste cobrindo query_names conhecidos e fallback para nomes desconhecidos.",
    "Pagina depende de client.logger.entries e client.logger.get_session_summary() \u2014 nao ha teste de contrato validando shape desses retornos contra o que a UI espera (campos: total_queries, total_elapsed_ms, estimated_cost_usd, cache_hits, errors; entry fields: query_name, column, exception_type, cache_hit, elapsed_ms, rows_returned, estimated_cost_usd, bytes_scanned, dataset, timestamp, sql).",
    "Nova task push-after-staging no Taskfile.yml executa git push incondicional \u2014 nao ha teste ou validacao de que remote esta configurado. Falha silenciosa possivel se remote nao existir.",
    "Nova task cleanup-staging-after-prod usa sudo com path hardcoded (/home/aalbertoni/.config/homelab/scripts/stack-down) \u2014 acoplamento a usuario especifico, pode falhar em outro ambiente.",
    "Troca de rg por grep -nE no Taskfile.yml e funcional mas nao ha teste automatizado das tasks de governanca (verify-staging-governance-proof, verify-prod-governance-proof). Regressao possivel se regex divergir.",
    "Arquivo .coverage binario incluido no diff \u2014 nao deveria ser versionado."
  ],
  "summary": "Mudancas de governanca (Taskfile/CLAUDE.md) sao documentacao/infra sem risco funcional, mas a nova pagina Query Log carece de testes unitarios e de contrato para as dependencias de logger."
}

== release-ops.json ==
{
  "status": "APROVADO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage binario incluido no diff \u2014 nao deve ser commitado (adicionar ao .gitignore se ausente).",
    "Nova pagina 07_query_log.py depende de client.logger.entries e client.logger.get_session_summary() \u2014 confirmar que esses atributos existem no AthenaClient atual.",
    "Taskfile troca rg por grep -nE nas validacoes de governance proof \u2014 funcionalmente equivalente, mas confirmar que grep esta disponivel no ambiente de deploy (containers Alpine podem precisar de pacote extra).",
    "Task cleanup-staging-after-prod referencia path hardcoded /home/aalbertoni/.config/homelab/scripts/stack-down \u2014 verificar se path existe no ambiente de deploy."
  ],
  "summary": "Mudancas de governanca (push-after-staging, cleanup-staging-after-prod), migracao rg->grep no Taskfile e nova pagina Query Log \u2014 sem bloqueios, apenas verificacoes menores recomendadas."
}

Diff para revisar:
diff --git a/.coverage b/.coverage
index 6baef5f..6e69e8a 100644
Binary files a/.coverage and b/.coverage differ
diff --git a/CLAUDE.md b/CLAUDE.md
index 5bae87b..7a07250 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -70,10 +70,12 @@ Este projeto usa governanca obrigatoria de deploy. O agente nao pode improvisar
 Regras obrigatorias:
 
 1. Nunca seguir para deploy sem passar por `task gate1`, `task snapshot`, `task review-agents-consensus` e `task build-release`.
-2. Nunca promover para producao sem staging aprovado.
-3. Nunca fazer deploy de producao sem aprovacao humana explicita via `ALLOW_PROD_DEPLOY=true`.
-4. Nunca considerar staging ou producao aprovados sem gravar evidencia em `reviews/latest/`.
-5. Se houver duvida sobre o estado dos gates, parar e reportar o bloqueio em vez de continuar.
+2. Nunca fazer `git push` da branch de trabalho antes de staging aprovado. O push remoto acontece somente depois de `task verify-staging-governance-proof`, via `task push-after-staging`.
+3. Nunca promover para producao sem staging aprovado.
+4. Nunca fazer deploy de producao sem aprovacao humana explicita via `ALLOW_PROD_DEPLOY=true`.
+5. Nunca considerar staging ou producao aprovados sem gravar evidencia em `reviews/latest/`.
+6. Se houver duvida sobre o estado dos gates, parar e reportar o bloqueio em vez de continuar.
+7. O staging nao deve ser derrubado logo apos o deploy de producao. So pode ser desligado depois de `task verify-prod`, `task verify-prod-governance-proof` e uma aprovacao explicita via `ALLOW_STAGING_CLEANUP=true`.
 
 Arquivos obrigatorios de evidencia:
 
@@ -113,22 +115,24 @@ Fluxo obrigatorio daqui pra frente:
 6. Rodar `task smoke-staging`.
 7. Gravar `reviews/latest/deploy-staging-check.md`.
 8. Rodar `task verify-staging-governance-proof`.
-9. So depois disso considerar staging apto.
-10. Para producao, gravar `reviews/latest/deploy-prod-check.md`.
-11. Rodar `ALLOW_PROD_DEPLOY=true task promote-prod`.
-12. Rodar `task verify-prod`.
-13. Rodar `task verify-prod-governance-proof`.
+9. Rodar `task push-after-staging`.
+10. So depois disso considerar staging apto e branch remota alinhada.
+11. Para producao, gravar `reviews/latest/deploy-prod-check.md`.
+12. Rodar `ALLOW_PROD_DEPLOY=true task promote-prod`.
+13. Rodar `task verify-prod`.
+14. Rodar `task verify-prod-governance-proof`.
+15. Opcionalmente, so depois de producao estavel, rodar `ALLOW_STAGING_CLEANUP=true task cleanup-staging-after-prod`.
 
 Quando o usuario disser “segue com o fluxo de deploy”, o agente deve responder executando ou orientando exatamente essa sequencia. Nao pode pular direto para `git status`, `git diff`, `git push` ou deploy.
 
 Prompts operacionais canônicos:
 
 ```text
-Siga a governanca obrigatoria deste projeto. Antes de qualquer deploy, execute ou instrua exatamente o fluxo task gate1 -> task snapshot -> task review-agents-consensus -> task build-release -> task deploy-staging -> task smoke-staging. So depois disso grave reviews/latest/deploy-staging-check.md no formato canonico e valide com task verify-staging-governance-proof.
+Siga a governanca obrigatoria deste projeto. Antes de qualquer deploy, execute ou instrua exatamente o fluxo task gate1 -> task snapshot -> task review-agents-consensus -> task build-release -> task deploy-staging -> task smoke-staging. So depois disso grave reviews/latest/deploy-staging-check.md no formato canonico, valide com task verify-staging-governance-proof e faca o push remoto somente via task push-after-staging.
 ```
 
 ```text
-Siga a governanca obrigatoria deste projeto. Nao faca deploy de producao sem staging aprovado e sem aprovacao humana explicita. Antes da producao, grave reviews/latest/deploy-prod-check.md no formato canonico. Depois execute somente ALLOW_PROD_DEPLOY=true task promote-prod, task verify-prod e task verify-prod-governance-proof.
+Siga a governanca obrigatoria deste projeto. Nao faca deploy de producao sem staging aprovado e sem aprovacao humana explicita. Antes da producao, grave reviews/latest/deploy-prod-check.md no formato canonico. Depois execute somente task push-after-staging, ALLOW_PROD_DEPLOY=true task promote-prod, task verify-prod e task verify-prod-governance-proof. So derrube o staging se houver aprovacao explicita via ALLOW_STAGING_CLEANUP=true task cleanup-staging-after-prod.
 ```
 
 ---
diff --git a/Taskfile.yml b/Taskfile.yml
index 307dafd..c08903e 100644
--- a/Taskfile.yml
+++ b/Taskfile.yml
@@ -123,13 +123,15 @@ tasks:
         6. task smoke-staging
         7. Gerar reviews/latest/deploy-staging-check.md
         8. task verify-staging-governance-proof
+        9. task push-after-staging
 
         Para producao:
-        9. Revisar staging aprovado
-        10. Gerar reviews/latest/deploy-prod-check.md
-        11. ALLOW_PROD_DEPLOY=true task promote-prod
-        12. task verify-prod
-        13. task verify-prod-governance-proof
+        10. Revisar staging aprovado
+        11. Gerar reviews/latest/deploy-prod-check.md
+        12. ALLOW_PROD_DEPLOY=true task promote-prod
+        13. task verify-prod
+        14. task verify-prod-governance-proof
+        15. Opcional: ALLOW_STAGING_CLEANUP=true task cleanup-staging-after-prod
 
         Deploy por comando ad hoc fora do Taskfile e proibido.
         EOF
@@ -140,25 +142,31 @@ tasks:
       - |
         test -f reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^commit_sha: .+$' reviews/latest/deploy-staging-check.md
+        grep -nE '^commit_sha: .+$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^environment: staging$' reviews/latest/deploy-staging-check.md
+        grep -nE '^environment: staging$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^gate1: (pass|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^gate1: (pass|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^snapshot_commit: [0-9a-f]{7,40}$' reviews/latest/deploy-staging-check.md
+        grep -nE '^snapshot_commit: [0-9a-f]{7,40}$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^gate2: (pass|warning|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^gate2: (pass|warning|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^release_build: (pass|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^release_build: (pass|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^staging_deploy: (pass|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^staging_deploy: (pass|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^staging_smoke: (pass|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^staging_smoke: (pass|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^verdict: (ok|warning|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^verdict: (ok|warning|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); rg -n "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-staging-check.md'
+        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); grep -nE "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-staging-check.md'
+
+  push-after-staging:
+    desc: Faz git push somente apos staging aprovado
+    cmds:
+      - task: verify-staging-governance-proof
+      - git push
 
   promote-prod:
     desc: Portao 5
@@ -185,21 +193,29 @@ tasks:
       - |
         test -f reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^commit_sha: .+$' reviews/latest/deploy-prod-check.md
+        grep -nE '^commit_sha: .+$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^environment: prod$' reviews/latest/deploy-prod-check.md
+        grep -nE '^environment: prod$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^staging_governance: (pass|fail)$' reviews/latest/deploy-prod-check.md
+        grep -nE '^staging_governance: (pass|fail)$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^prod_approval: explicit$' reviews/latest/deploy-prod-check.md
+        grep -nE '^prod_approval: explicit$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^prod_deploy: (pass|fail)$' reviews/latest/deploy-prod-check.md
+        grep -nE '^prod_deploy: (pass|fail)$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^prod_verify: (pass|fail)$' reviews/latest/deploy-prod-check.md
+        grep -nE '^prod_verify: (pass|fail)$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^verdict: (ok|warning|fail)$' reviews/latest/deploy-prod-check.md
+        grep -nE '^verdict: (ok|warning|fail)$' reviews/latest/deploy-prod-check.md
       - |
-        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); rg -n "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-prod-check.md'
+        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); grep -nE "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-prod-check.md'
+
+  cleanup-staging-after-prod:
+    desc: Derruba o staging somente apos producao estavel e validada
+    cmds:
+      - bash -lc 'test "${ALLOW_STAGING_CLEANUP:-false}" = "true" || { echo "Refusing staging cleanup without ALLOW_STAGING_CLEANUP=true." >&2; exit 1; }'
+      - task: verify-prod
+      - task: verify-prod-governance-proof
+      - sudo /home/aalbertoni/.config/homelab/scripts/stack-down gdq-proposer-staging
 
   rollback-last:
     desc: Faz rollback para a ultima release saudavel
@@ -221,6 +237,7 @@ tasks:
     desc: Executa gates, staging e verificacao interna de producao
     cmds:
       - task: pipeline-staging
+      - task: push-after-staging
       - task: promote-prod
       - task: verify-prod
       - task: verify-prod-governance-proof
diff --git a/app.py b/app.py
index 6a4652a..0ee46ae 100644
--- a/app.py
+++ b/app.py
@@ -35,7 +35,9 @@ def render_sidebar():
     st.sidebar.caption(f"v{__version__}")
     st.sidebar.divider()
 
-    # Diagnostic link
+    # Utility links
+    if st.sidebar.button("Query Log", key="sidebar_qlog", help="Historico de queries da sessao"):
+        st.switch_page("pages/07_query_log.py")
     if st.sidebar.button("Diagnostico", key="sidebar_diag", help="Verificar status do ambiente"):
         st.switch_page("pages/06_diagnostico.py")
 
diff --git a/pages/07_query_log.py b/pages/07_query_log.py
new file mode 100644
index 0000000..bbf6671
--- /dev/null
+++ b/pages/07_query_log.py
@@ -0,0 +1,218 @@
+"""
+Query Log — Historico completo de queries da sessao.
+
+Exibe todas as queries executadas com status, custo, tempo,
+motivo, detalhes de erro e SQL completo.
+"""
+
+import streamlit as st
+
+st.set_page_config(
+    page_title="Query Log — GDQ",
+    page_icon=":memo:",
+    layout="wide",
+)
+
+st.title("Query Log")
+st.caption("Historico completo de queries executadas nesta sessao.")
+
+# ---------------------------------------------------------------------------
+# Guard: precisa de client ativo
+# ---------------------------------------------------------------------------
+if "client" not in st.session_state:
+    st.info("Nenhuma sessao ativa. Volte ao Dashboard para conectar.")
+    if st.button("Ir para Dashboard", key="ql_go_dash"):
+        st.switch_page("app.py")
+    st.stop()
+
+client = st.session_state["client"]
+entries = client.logger.entries
+
+if not entries:
+    st.info("Nenhuma query executada nesta sessao.")
+    if st.button("Ir para Setup", key="ql_go_setup"):
+        st.switch_page("pages/01_setup.py")
+    st.stop()
+
+# ---------------------------------------------------------------------------
+# Summary metrics
+# ---------------------------------------------------------------------------
+summary = client.logger.get_session_summary()
+time_s = summary["total_elapsed_ms"] / 1000
+cost = summary["estimated_cost_usd"]
+
+m1, m2, m3, m4, m5 = st.columns(5)
+m1.metric("Total de queries", summary["total_queries"])
+m2.metric("Tempo total", f"{time_s:.1f}s")
+m3.metric("Cache hits", f"{summary['cache_hits']}/{summary['total_queries']}")
+m4.metric("Custo estimado", f"${cost:.4f}")
+m5.metric("Erros", summary["errors"])
+
+# Cost guardrail
+app_cfg = st.session_state.get("config")
+threshold = app_cfg.athena.cost_warning_threshold_usd if app_cfg else 0.50
+if cost > threshold:
+    st.warning(f"Custo da sessao (${cost:.4f}) excedeu o limite de ${threshold:.2f}.")
+
+st.divider()
+
+# ---------------------------------------------------------------------------
+# Filters
+# ---------------------------------------------------------------------------
+col_f1, col_f2, col_f3 = st.columns(3)
+
+# Status filter
+status_options = ["Todas", "OK", "Erro", "Cache Hit"]
+with col_f1:
+    status_filter = st.selectbox("Status", status_options, key="ql_status_filter")
+
+# Query name filter
+query_names = sorted({e.query_name for e in entries})
+with col_f2:
+    name_filter = st.selectbox(
+        "Tipo de query", ["Todas"] + query_names, key="ql_name_filter"
+    )
+
+# Column filter
+columns_used = sorted({e.column for e in entries if e.column})
+with col_f3:
+    column_filter = st.selectbox(
+        "Coluna", ["Todas"] + columns_used, key="ql_col_filter"
+    )
+
+# Apply filters
+filtered = list(entries)
+if status_filter == "OK":
+    filtered = [e for e in filtered if not e.exception_type and not e.cache_hit]
+elif status_filter == "Erro":
+    filtered = [e for e in filtered if e.exception_type]
+elif status_filter == "Cache Hit":
+    filtered = [e for e in filtered if e.cache_hit]
+
+if name_filter != "Todas":
+    filtered = [e for e in filtered if e.query_name == name_filter]
+
+if column_filter != "Todas":
+    filtered = [e for e in filtered if e.column == column_filter]
+
+st.caption(f"Exibindo {len(filtered)} de {len(entries)} queries.")
+
+
+# ---------------------------------------------------------------------------
+# Helper: query purpose descriptions
+# ---------------------------------------------------------------------------
+
+def _describe_query_purpose(query_name: str) -> str:
+    """Retorna descricao do proposito de cada tipo de query."""
+    purposes = {
+        "health_check": "Verificacao de conectividade com o Athena.",
+        "table_exists": "Validacao de existencia da tabela no catalogo.",
+        "get_columns": "Leitura de metadados (colunas e tipos) via information_schema.",
+        "get_columns_with_partitions": "Leitura de colunas com deteccao de partition keys.",
+        "count_rows": "Contagem de linhas para estimativa de volume e timeout adaptativo.",
+        "estimate_volume": "Estimativa de volumetria para ajustar timeout da sessao.",
+        "column_sample": "Amostragem de coluna para classificacao semantica (tipo, cardinalidade, cast ratio).",
+        "batch_column_sample": "Amostragem em lote de varias colunas para classificacao semantica.",
+        "numeric_history": "Historico temporal de metricas numericas (mean, stddev, percentis) para calibracao de regras.",
+        "row_count_history": "Historico de contagem de linhas por periodo para regra de RowCount.",
+        "distinct_count_history": "Historico de contagem de valores distintos por periodo.",
+        "categorical_distribution": "Distribuicao de frequencia de valores categoricos.",
+        "categorical_domain": "Dominio de valores (valores unicos) de coluna categorica.",
+        "uniqueness_check": "Verificacao de unicidade para deteccao de chaves primarias.",
+        "completeness_check": "Verificacao de completude (nulls) da coluna.",
+        "partition_values": "Listagem de valores de particao disponiveis.",
+        "partition_range": "Range de particoes (min/max) para definir lookback.",
+    }
+    return purposes.get(query_name, f"Query do tipo `{query_name}`.")
+
+
+# ---------------------------------------------------------------------------
+# Query list (most recent first)
+# ---------------------------------------------------------------------------
+for i, entry in enumerate(reversed(filtered)):
+    # Status badge
+    if entry.exception_type:
+        status_icon = ":red_circle:"
+        status_text = "ERRO"
+    elif entry.cache_hit:
+        status_icon = ":large_blue_circle:"
+        status_text = "CACHE"
+    else:
+        status_icon = ":green_circle:"
+        status_text = "OK"
+
+    # Cost per query
+    entry_cost = entry.estimated_cost_usd
+    cost_label = f"${entry_cost:.6f}" if entry_cost > 0 else "—"
+
+    # Bytes scanned
+    if entry.bytes_scanned and entry.bytes_scanned > 0:
+        mb = entry.bytes_scanned / (1024 ** 2)
+        if mb >= 1024:
+            scan_label = f"{mb / 1024:.2f} GB"
+        else:
+            scan_label = f"{mb:.2f} MB"
+    else:
+        scan_label = "—"
+
+    # Column label
+    col_label = f" → `{entry.column}`" if entry.column else ""
+
+    # Header line
+    header = (
+        f"{status_icon} **{entry.query_name}**{col_label} — "
+        f"{status_text} · {entry.elapsed_ms}ms · {entry.rows_returned} rows · "
+        f"custo {cost_label}"
+    )
+
+    with st.expander(header, expanded=False):
+        # Detail grid
+        d1, d2, d3 = st.columns(3)
+
+        with d1:
+            st.markdown("**Detalhes da execucao**")
+            st.markdown(f"- **Query:** {entry.query_name}")
+            st.markdown(f"- **Dataset:** {entry.dataset}")
+            st.markdown(f"- **Coluna:** {entry.column or '(tabela inteira)'}")
+            st.markdown(f"- **Timestamp:** {entry.timestamp}")
+
+        with d2:
+            st.markdown("**Metricas**")
+            st.markdown(f"- **Tempo:** {entry.elapsed_ms}ms")
+            st.markdown(f"- **Rows retornadas:** {entry.rows_returned}")
+            st.markdown(f"- **Bytes escaneados:** {scan_label}")
+            st.markdown(f"- **Custo:** {cost_label}")
+            st.markdown(f"- **Cache hit:** {'Sim' if entry.cache_hit else 'Nao'}")
+
+        with d3:
+            st.markdown("**Motivo da query**")
+            st.markdown(f"{_describe_query_purpose(entry.query_name)}")
+
+            if entry.exception_type:
+                st.markdown("**Erro**")
+                st.error(f"Tipo: `{entry.exception_type}`")
+
+        # SQL
+        if entry.sql:
+            st.markdown("**SQL executado:**")
+            st.code(entry.sql, language="sql")
+        else:
+            st.caption("SQL nao disponivel para esta query.")
+
+st.divider()
+
+# ---------------------------------------------------------------------------
+# Export
+# ---------------------------------------------------------------------------
+exp1, exp2 = st.columns(2)
+with exp1:
+    st.download_button(
+        label="Exportar log completo (JSON)",
+        data=client.logger.export_json(),
+        file_name="gdq_query_log.json",
+        mime="application/json",
+        key="ql_export_json",
+    )
+with exp2:
+    if st.button("Voltar ao Dashboard", key="ql_back_dash"):
+        st.switch_page("app.py")

Contexto do projeto:
# Project Context

- Project: `gdq-proposer`
- Generated at: `2026-03-23T01:24:30Z`
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
 reviews/latest/architecture.json      |    9 +-
 reviews/latest/architecture.prompt.md |  558 +++++++++++-----
 reviews/latest/architecture.raw.txt   |    9 +-
 reviews/latest/codex.json             |   18 +-
 reviews/latest/codex.prompt.md        | 1130 +++++++++++++++++++++++++--------
 reviews/latest/codex.raw.txt          |    2 +-
 reviews/latest/diff.patch             |  558 +++++++++++-----
 reviews/latest/project-context.md     |  529 ++++++++++++---
 reviews/latest/release-ops.json       |   12 +-
 reviews/latest/release-ops.prompt.md  |  558 +++++++++++-----
 reviews/latest/release-ops.raw.txt    |   12 +-
 reviews/latest/security.json          |    9 +-
 reviews/latest/security.prompt.md     |  558 +++++++++++-----
 reviews/latest/security.raw.txt       |    9 +-
 reviews/latest/summary.json           |   62 +-
 reviews/latest/tests.json             |   12 +-
 reviews/latest/tests.prompt.md        |  558 +++++++++++-----
 reviews/latest/tests.raw.txt          |   12 +-
 18 files changed, 3339 insertions(+), 1276 deletions(-)

```
