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
    "Arquivo binario .coverage incluido no diff \u2014 nao deveria ser commitado (adicionar ao .gitignore)",
    "verify-staging-governance-proof e verify-prod-governance-proof usam 'bash -lc' com login shell \u2014 pode carregar estado inesperado do ambiente; preferir 'bash -c' simples",
    "promote-prod executa verify-staging-governance-proof inline antes do deploy, mas tambem e chamado em pipeline-prod apos pipeline-staging que ja verifica \u2014 dupla execucao redundante (nao e bloqueio, apenas ruido)"
  ],
  "summary": "Governanca de deploy bem estruturada: separacao source/deploy/runtime preservada, sem acesso a secrets, sem acoplamento excessivo; apenas .coverage binario e detalhes menores de shell merecem atencao."
}

== security.json ==
{
  "status": "APROVADO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage (binario) incluido no diff \u2014 normalmente deve estar no .gitignore para evitar vazamento de paths locais ou metricas internas.",
    "promote-prod usa 'sudo /usr/local/bin/deploy-prod' \u2014 garantir que o script destino valida inputs e que sudoers restringe apenas esse comando."
  ],
  "summary": "Diff adiciona governanca de deploy com gates obrigatorios, evidencia auditavel e bloqueio de producao sem aprovacao explicita \u2014 sem segredos, injecao ou permissoes excessivas."
}

== tests.json ==
{
  "status": "APROVADO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage binario incluido no diff \u2014 nao deveria ser commitado (adicionar ao .gitignore)",
    "Tasks de governanca (verify-staging-governance-proof, verify-prod-governance-proof) dependem de `rg` estar instalado no ambiente de deploy \u2014 sem fallback se ausente",
    "Nenhum teste automatizado valida os novos tasks do Taskfile (ex: testar que promote-prod falha sem ALLOW_PROD_DEPLOY=true)"
  ],
  "summary": "Mudancas de governanca de deploy via Taskfile e CLAUDE.md \u2014 sem codigo Python novo, sem funcoes publicas adicionadas, sem risco de regressao funcional."
}

== release-ops.json ==
{
  "status": "APROVADO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage (binario) incluido no diff \u2014 nao deveria ser commitado; adicionar ao .gitignore.",
    "Tasks de verificacao (verify-staging-governance-proof, verify-prod-governance-proof) dependem de `rg` (ripgrep) estar instalado no ambiente de deploy \u2014 confirmar presenca na imagem Docker/compose.",
    "promote-prod agora exige ALLOW_PROD_DEPLOY=true e evidencia de staging antes de executar \u2014 operadores existentes precisam ser informados da mudanca de fluxo."
  ],
  "summary": "Diff adiciona governanca obrigatoria de deploy (gates, evidencia, aprovacao humana) sem alterar codigo de aplicacao \u2014 implantabilidade e health check nao sao afetados; rollback continua disponivel via task rollback-last."
}

Diff para revisar:
diff --git a/.coverage b/.coverage
index 3f6d8aa..6baef5f 100644
Binary files a/.coverage and b/.coverage differ
diff --git a/CLAUDE.md b/CLAUDE.md
index f825d8e..5bae87b 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -63,6 +63,76 @@ ambos dialetos para que os testes unitarios rodem com DuckDB sem precisar de Ath
 
 ---
 
+## Governanca de Deploy
+
+Este projeto usa governanca obrigatoria de deploy. O agente nao pode improvisar fluxo com `git push`, `sudo /usr/local/bin/deploy-prod`, `stack-deploy` ou comandos ad hoc fora do `Taskfile`.
+
+Regras obrigatorias:
+
+1. Nunca seguir para deploy sem passar por `task gate1`, `task snapshot`, `task review-agents-consensus` e `task build-release`.
+2. Nunca promover para producao sem staging aprovado.
+3. Nunca fazer deploy de producao sem aprovacao humana explicita via `ALLOW_PROD_DEPLOY=true`.
+4. Nunca considerar staging ou producao aprovados sem gravar evidencia em `reviews/latest/`.
+5. Se houver duvida sobre o estado dos gates, parar e reportar o bloqueio em vez de continuar.
+
+Arquivos obrigatorios de evidencia:
+
+Staging: `reviews/latest/deploy-staging-check.md`
+
+```text
+commit_sha: <sha atual>
+environment: staging
+gate1: <pass|fail>
+snapshot_commit: <sha do snapshot>
+gate2: <pass|warning|fail>
+release_build: <pass|fail>
+staging_deploy: <pass|fail>
+staging_smoke: <pass|fail>
+verdict: <ok|warning|fail>
+```
+
+Producao: `reviews/latest/deploy-prod-check.md`
+
+```text
+commit_sha: <sha atual>
+environment: prod
+staging_governance: <pass|fail>
+prod_approval: explicit
+prod_deploy: <pass|fail>
+prod_verify: <pass|fail>
+verdict: <ok|warning|fail>
+```
+
+Fluxo obrigatorio daqui pra frente:
+
+1. Rodar `task gate1`.
+2. Rodar `task snapshot`.
+3. Rodar `task review-agents-consensus`.
+4. Rodar `task build-release`.
+5. Rodar `task deploy-staging`.
+6. Rodar `task smoke-staging`.
+7. Gravar `reviews/latest/deploy-staging-check.md`.
+8. Rodar `task verify-staging-governance-proof`.
+9. So depois disso considerar staging apto.
+10. Para producao, gravar `reviews/latest/deploy-prod-check.md`.
+11. Rodar `ALLOW_PROD_DEPLOY=true task promote-prod`.
+12. Rodar `task verify-prod`.
+13. Rodar `task verify-prod-governance-proof`.
+
+Quando o usuario disser “segue com o fluxo de deploy”, o agente deve responder executando ou orientando exatamente essa sequencia. Nao pode pular direto para `git status`, `git diff`, `git push` ou deploy.
+
+Prompts operacionais canônicos:
+
+```text
+Siga a governanca obrigatoria deste projeto. Antes de qualquer deploy, execute ou instrua exatamente o fluxo task gate1 -> task snapshot -> task review-agents-consensus -> task build-release -> task deploy-staging -> task smoke-staging. So depois disso grave reviews/latest/deploy-staging-check.md no formato canonico e valide com task verify-staging-governance-proof.
+```
+
+```text
+Siga a governanca obrigatoria deste projeto. Nao faca deploy de producao sem staging aprovado e sem aprovacao humana explicita. Antes da producao, grave reviews/latest/deploy-prod-check.md no formato canonico. Depois execute somente ALLOW_PROD_DEPLOY=true task promote-prod, task verify-prod e task verify-prod-governance-proof.
+```
+
+---
+
 ## Principios de Desenvolvimento
 
 ### 1. Fatias verticais pequenas
diff --git a/Taskfile.yml b/Taskfile.yml
index 341cd74..307dafd 100644
--- a/Taskfile.yml
+++ b/Taskfile.yml
@@ -108,9 +108,63 @@ tasks:
     cmds:
       - cmd: 'echo "Skipping public staging smoke: app interno"'
 
+  guide-governed-deploy:
+    desc: Exibe o fluxo obrigatorio de governanca para staging e producao
+    cmds:
+      - |
+        cat <<'EOF'
+        Fluxo obrigatorio deste projeto:
+
+        1. task gate1
+        2. task snapshot
+        3. task review-agents-consensus
+        4. task build-release
+        5. task deploy-staging
+        6. task smoke-staging
+        7. Gerar reviews/latest/deploy-staging-check.md
+        8. task verify-staging-governance-proof
+
+        Para producao:
+        9. Revisar staging aprovado
+        10. Gerar reviews/latest/deploy-prod-check.md
+        11. ALLOW_PROD_DEPLOY=true task promote-prod
+        12. task verify-prod
+        13. task verify-prod-governance-proof
+
+        Deploy por comando ad hoc fora do Taskfile e proibido.
+        EOF
+
+  verify-staging-governance-proof:
+    desc: Bloqueia sem evidencia obrigatoria de staging governado
+    cmds:
+      - |
+        test -f reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^commit_sha: .+$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^environment: staging$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^gate1: (pass|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^snapshot_commit: [0-9a-f]{7,40}$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^gate2: (pass|warning|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^release_build: (pass|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^staging_deploy: (pass|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^staging_smoke: (pass|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^verdict: (ok|warning|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); rg -n "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-staging-check.md'
+
   promote-prod:
     desc: Portao 5
     cmds:
+      - bash -lc 'test "${ALLOW_PROD_DEPLOY:-false}" = "true" || { echo "Refusing production deploy without ALLOW_PROD_DEPLOY=true." >&2; exit 1; }'
+      - task: verify-staging-governance-proof
       - sudo /usr/local/bin/deploy-prod gdq-proposer
 
   verify-prod:
@@ -125,6 +179,28 @@ tasks:
     cmds:
       - cmd: 'echo "Skipping public production smoke: app interno"'
 
+  verify-prod-governance-proof:
+    desc: Bloqueia sem evidencia obrigatoria da producao governada
+    cmds:
+      - |
+        test -f reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^commit_sha: .+$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^environment: prod$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^staging_governance: (pass|fail)$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^prod_approval: explicit$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^prod_deploy: (pass|fail)$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^prod_verify: (pass|fail)$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^verdict: (ok|warning|fail)$' reviews/latest/deploy-prod-check.md
+      - |
+        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); rg -n "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-prod-check.md'
+
   rollback-last:
     desc: Faz rollback para a ultima release saudavel
     cmds:
@@ -139,6 +215,7 @@ tasks:
       - task: build-release
       - task: deploy-staging
       - task: smoke-staging
+      - task: verify-staging-governance-proof
 
   pipeline-prod:
     desc: Executa gates, staging e verificacao interna de producao
@@ -146,3 +223,4 @@ tasks:
       - task: pipeline-staging
       - task: promote-prod
       - task: verify-prod
+      - task: verify-prod-governance-proof

Contexto do projeto:
# Project Context

- Project: `gdq-proposer`
- Generated at: `2026-03-21T22:28:26Z`
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
2. Nunca promover para producao sem staging aprovado.
3. Nunca fazer deploy de producao sem aprovacao humana explicita via `ALLOW_PROD_DEPLOY=true`.
4. Nunca considerar staging ou producao aprovados sem gravar evidencia em `reviews/latest/`.
5. Se houver duvida sobre o estado dos gates, parar e reportar o bloqueio em vez de continuar.

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
9. So depois disso considerar staging apto.
10. Para producao, gravar `reviews/latest/deploy-prod-check.md`.
11. Rodar `ALLOW_PROD_DEPLOY=true task promote-prod`.
12. Rodar `task verify-prod`.
13. Rodar `task verify-prod-governance-proof`.

Quando o usuario disser “segue com o fluxo de deploy”, o agente deve responder executando ou orientando exatamente essa sequencia. Nao pode pular direto para `git status`, `git diff`, `git push` ou deploy.

Prompts operacionais canônicos:

```text
Siga a governanca obrigatoria deste projeto. Antes de qualquer deploy, execute ou instrua exatamente o fluxo task gate1 -> task snapshot -> task review-agents-consensus -> task build-release -> task deploy-staging -> task smoke-staging. So depois disso grave reviews/latest/deploy-staging-check.md no formato canonico e valide com task verify-staging-governance-proof.
```

```text
Siga a governanca obrigatoria deste projeto. Nao faca deploy de producao sem staging aprovado e sem aprovacao humana explicita. Antes da producao, grave reviews/latest/deploy-prod-check.md no formato canonico. Depois execute somente ALLOW_PROD_DEPLOY=true task promote-prod, task verify-prod e task verify-prod-governance-proof.
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

- snake_case para todos os arquivos Python
- Templates SQL: `<proposito>_<contexto>.sql` (ex: `numeric_history.sql`)
- Testes: `test_<modulo>.py`


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

        Para producao:
        9. Revisar staging aprovado
        10. Gerar reviews/latest/deploy-prod-check.md
        11. ALLOW_PROD_DEPLOY=true task promote-prod
        12. task verify-prod
        13. task verify-prod-governance-proof

        Deploy por comando ad hoc fora do Taskfile e proibido.
        EOF

  verify-staging-governance-proof:
    desc: Bloqueia sem evidencia obrigatoria de staging governado
    cmds:
      - |
        test -f reviews/latest/deploy-staging-check.md
      - |
        rg -n '^commit_sha: .+$' reviews/latest/deploy-staging-check.md
      - |
        rg -n '^environment: staging$' reviews/latest/deploy-staging-check.md
      - |
        rg -n '^gate1: (pass|fail)$' reviews/latest/deploy-staging-check.md
      - |
        rg -n '^snapshot_commit: [0-9a-f]{7,40}$' reviews/latest/deploy-staging-check.md
      - |
        rg -n '^gate2: (pass|warning|fail)$' reviews/latest/deploy-staging-check.md
      - |
        rg -n '^release_build: (pass|fail)$' reviews/latest/deploy-staging-check.md
      - |
        rg -n '^staging_deploy: (pass|fail)$' reviews/latest/deploy-staging-check.md
      - |
        rg -n '^staging_smoke: (pass|fail)$' reviews/latest/deploy-staging-check.md
      - |
        rg -n '^verdict: (ok|warning|fail)$' reviews/latest/deploy-staging-check.md
      - |
        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); rg -n "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-staging-check.md'

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
        rg -n '^commit_sha: .+$' reviews/latest/deploy-prod-check.md
      - |
        rg -n '^environment: prod$' reviews/latest/deploy-prod-check.md
      - |
        rg -n '^staging_governance: (pass|fail)$' reviews/latest/deploy-prod-check.md
      - |
        rg -n '^prod_approval: explicit$' reviews/latest/deploy-prod-check.md
      - |
        rg -n '^prod_deploy: (pass|fail)$' reviews/latest/deploy-prod-check.md
      - |
        rg -n '^prod_verify: (pass|fail)$' reviews/latest/deploy-prod-check.md
      - |
        rg -n '^verdict: (ok|warning|fail)$' reviews/latest/deploy-prod-check.md
      - |
        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); rg -n "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-prod-check.md'

  rollback-last:
    desc: Faz rollback para a ultima release saudavel
    cmds:
      - sudo /usr/local/bin/stack-rollback gdq-proposer

  pipeline-staging:
    desc: Executa gates ate staging interno
    cmds:
      - task: gate1
      - task: snapshot
      - task: review-agents-consensus
      - task: build-release
      - task: deploy-staging
      - task: smoke-staging
      - task: verify-staging-governance-proof

  pipeline-prod:

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
 reviews/latest/architecture.json      |  13 +-
 reviews/latest/architecture.prompt.md | 522 +++++++++--------------
 reviews/latest/architecture.raw.txt   |  13 +-
 reviews/latest/codex.json             |  19 +-
 reviews/latest/codex.prompt.md        | 771 +++++++++++++++-------------------
 reviews/latest/codex.raw.txt          |   2 +-
 reviews/latest/diff.patch             | 522 +++++++++--------------
 reviews/latest/project-context.md     | 251 +++++++----
 reviews/latest/release-ops.json       |  15 +-
 reviews/latest/release-ops.prompt.md  | 522 +++++++++--------------
 reviews/latest/release-ops.raw.txt    |  15 +-
 reviews/latest/security.json          |  11 +-
 reviews/latest/security.prompt.md     | 522 +++++++++--------------
 reviews/latest/security.raw.txt       |  11 +-
 reviews/latest/summary.json           |  72 ++--
 reviews/latest/tests.json             |  12 +-
 reviews/latest/tests.prompt.md        | 522 +++++++++--------------
 reviews/latest/tests.raw.txt          |  12 +-
 18 files changed, 1540 insertions(+), 2287 deletions(-)

```
