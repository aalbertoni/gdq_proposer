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
  "blockers": [
    ".coverage (arquivo binario de cobertura) commitado no repositorio \u2014 deve ser adicionado ao .gitignore e removido do tracking"
  ],
  "warnings": [
    "Taskfile.yml referencia caminhos absolutos do usuario (/home/aalbertoni/.config/homelab/scripts/*) \u2014 acoplamento com ambiente local, dificulta portabilidade",
    "app.yaml expoe caminhos absolutos de source_path, workspace_path, deploy_path, runtime_path e release_path \u2014 considerar parametrizacao via variaveis de ambiente",
    "Dockerfile faz COPY de .env.example mas .dockerignore exclui .env* \u2014 verificar se .env.example nao e filtrado pelo glob (nao e, pois .dockerignore lista .env, .env.local, .env.dev, .env.prod explicitamente, entao .env.example passa \u2014 OK)",
    "pytest-cov adicionado em requirements.txt junto com dependencias de producao \u2014 considerar separar em requirements-dev.txt para nao incluir no container"
  ],
  "summary": "Infraestrutura de deploy bem estruturada com separacao clara source/deploy/runtime, mas .coverage binario deve ser bloqueado e caminhos absolutos no Taskfile merecem atencao."
}

== security.json ==
{
  "status": "ATENCAO",
  "blockers": [],
  "warnings": [
    "`.coverage` binary file committed \u2014 should be in `.gitignore`",
    "`Taskfile.yml` references hardcoded user home paths (`/home/aalbertoni/...`) \u2014 leaks username and internal directory structure",
    "`app.yaml` exposes absolute filesystem paths (`source_path`, `deploy_path`, `runtime_path`, `release_path`) with username",
    "`smoke.sh` uses `curl -k` which disables TLS certificate verification \u2014 acceptable for internal staging but risky if reused against external endpoints",
    "`Dockerfile` CMD uses shell expansion (`${PORT:-8501}`) via `sh -lc` \u2014 login shell (`-l`) loads profile files which is unnecessary and could introduce unexpected behavior",
    "`app.yaml` shows `authelia_enabled: false` and `traefik_enabled: false` \u2014 confirm the app is truly internal-only with no external exposure"
  ],
  "summary": "No secrets or injection risks found; minor hygiene issues with committed `.coverage`, hardcoded paths leaking usernames, and `curl -k` in smoke test."
}

== tests.json ==
{
  "status": "ATENCAO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage binario incluido no diff \u2014 deve ser adicionado ao .gitignore, nao commitado",
    "Dockerfile CMD usa sh -lc com interpolacao de variavel sem aspas internas no PORT \u2014 risco baixo pois ENV ja define default",
    "Taskfile.yml referencia paths absolutos de usuario (/home/aalbertoni/) \u2014 nao portavel entre ambientes",
    "Nenhum teste novo foi adicionado neste diff \u2014 aceitavel pois as mudancas sao infra/deploy (Dockerfile, Taskfile, scripts) sem logica de negocio",
    "scripts/smoke.sh e scripts/healthcheck.sh nao tem testes automatizados \u2014 considerar smoke test no CI para validar scripts"
  ],
  "summary": "Diff de infraestrutura (Docker, CI pipeline, scripts) sem codigo de negocio \u2014 nao requer testes unitarios, mas .coverage nao deve ser commitado."
}

== release-ops.json ==
{
  "status": "ATENCAO",
  "blockers": [],
  "warnings": [
    "Arquivo .coverage (binario) incluido no diff \u2014 deve ser adicionado ao .gitignore para nao ser commitado",
    "Dockerfile usa COPY seletivo mas nao copia preflight_check.py \u2014 se o app depende dele no startup, falhara em runtime",
    "Dockerfile nao copia scripts/ para dentro da imagem \u2014 healthcheck.sh so funciona se montado externamente ou via compose",
    "Nao ha docker-compose.yml no diff \u2014 deploy via compose depende de artefato externo nao visivel aqui",
    "Taskfile.yml referencia paths absolutos do usuario (/home/aalbertoni/.config/...) \u2014 quebra em outro host sem esses scripts",
    "smoke.sh usa apenas health endpoint (_stcore/health) \u2014 nao valida funcionalidade do app (ex: pagina principal carrega)",
    "Nao ha logging estruturado adicionado \u2014 diagnostico pos-deploy depende apenas dos logs nativos do Streamlit",
    "pytest-cov adicionado em requirements.txt principal (nao separado em requirements-dev.txt) \u2014 sera instalado na imagem de producao"
  ],
  "summary": "Containerizacao inicial solida com health check valido e rollback previsto, mas .coverage commitado, paths absolutos no Taskfile e ausencia de compose.yml no diff requerem atencao antes de prod."
}

Diff para revisar:
diff --git a/.coverage b/.coverage
new file mode 100644
index 0000000..3f6d8aa
Binary files /dev/null and b/.coverage differ
diff --git a/.dockerignore b/.dockerignore
new file mode 100644
index 0000000..806e3a2
--- /dev/null
+++ b/.dockerignore
@@ -0,0 +1,22 @@
+.git
+.gitignore
+.venv
+.pytest_cache
+__pycache__
+*.pyc
+*.pyo
+*.pyd
+.env
+.env.local
+.env.dev
+.env.prod
+.vscode
+.idea
+tests
+aws_test_data
+mock_data
+logs
+presets
+run_app.bat
+run_app.sh
+launcher.py
diff --git a/Dockerfile b/Dockerfile
new file mode 100644
index 0000000..b75fb77
--- /dev/null
+++ b/Dockerfile
@@ -0,0 +1,38 @@
+FROM python:3.12-slim
+
+ENV PYTHONDONTWRITEBYTECODE=1
+ENV PYTHONUNBUFFERED=1
+ENV PIP_NO_CACHE_DIR=1
+ENV STREAMLIT_SERVER_HEADLESS=true
+ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
+ENV PORT=8501
+
+WORKDIR /app
+
+RUN apt-get update \
+    && apt-get install -y --no-install-recommends curl \
+    && rm -rf /var/lib/apt/lists/*
+
+COPY requirements.txt .
+RUN pip install --no-cache-dir -r requirements.txt
+
+COPY app.py .
+COPY run.py .
+COPY config.py .
+COPY core ./core
+COPY infra ./infra
+COPY services ./services
+COPY strategies ./strategies
+COPY pages ./pages
+COPY queries ./queries
+COPY docs ./docs
+COPY .env.example ./.env.example
+
+RUN useradd --create-home --uid 1000 appuser \
+    && mkdir -p /app/logs /app/presets /app/mock_data /app/aws_test_data \
+    && chown -R appuser:appuser /app
+
+USER appuser
+EXPOSE 8501
+
+CMD ["sh", "-lc", "python -m streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true --browser.gatherUsageStats=false"]
diff --git a/Taskfile.yml b/Taskfile.yml
new file mode 100644
index 0000000..341cd74
--- /dev/null
+++ b/Taskfile.yml
@@ -0,0 +1,148 @@
+version: "3"
+
+tasks:
+  setup:
+    desc: Instala dependencias locais
+    cmds:
+      - python3 -m venv .venv
+      - .venv/bin/pip install --upgrade pip
+      - .venv/bin/pip install -r requirements.txt
+
+  lint:
+    desc: Executa lint
+    cmds:
+      - echo "Lint not configured yet for gdq-proposer"
+
+  typecheck:
+    desc: Executa type-check
+    cmds:
+      - echo "Type-check not configured yet for gdq-proposer"
+
+  test:
+    desc: Executa testes unitarios e de integracao local
+    cmds:
+      - .venv/bin/pytest tests/ -v -m "not athena"
+
+  coverage:
+    desc: Executa cobertura minima
+    cmds:
+      - .venv/bin/pytest tests/ -v --tb=short --cov=core --cov=infra --cov=services --cov=strategies --cov=pages --cov-report=term-missing -m "not athena"
+
+  gate1:
+    desc: Portao 1
+    cmds:
+      - /home/aalbertoni/.config/homelab/scripts/gate1-validate .
+
+  plan-check:
+    desc: Exige plano revisado e atualizado antes de seguir
+    cmds:
+      - /home/aalbertoni/.config/homelab/scripts/require-plan-review .
+
+  snapshot:
+    desc: Cria um commit local para habilitar release por SHA
+    deps: [plan-check]
+    cmds:
+      - git add -A
+      - /home/aalbertoni/.config/homelab/scripts/snapshot-commit .
+
+  plan-write:
+    desc: Cria o template canonico do plano tecnico em reviews/latest/plan.md
+    cmds:
+      - /home/aalbertoni/.config/homelab/scripts/prepare-plan-bundle .
+
+  project-context:
+    desc: Gera o contexto curado do projeto para reviews do Codex
+    cmds:
+      - /home/aalbertoni/.config/homelab/scripts/prepare-project-context .
+
+  plan-review-codex:
+    desc: Submete o plano tecnico ao review independente do Codex
+    cmds:
+      - /home/aalbertoni/.config/homelab/scripts/review-plan .
+
+  plan-consensus:
+    desc: Gera ou valida o plano e exige veredito do Codex antes da implementacao
+    cmds:
+      - task: plan-write
+      - task: project-context
+      - task: plan-review-codex
+
+  review-agents:
+    desc: Executa os 4 agentes e consolida o veredito
+    deps: [plan-check]
+    cmds:
+      - /home/aalbertoni/.config/homelab/scripts/review-agents .
+
+  review-agents-consensus:
+    desc: Executa Gate 2 com Claude + Codex e consolida o veredito conjunto
+    deps: [plan-check]
+    cmds:
+      - env CODEX_REVIEW_ENABLED=true /home/aalbertoni/.config/homelab/scripts/review-agents .
+
+  build-release:
+    desc: Portao 3, exige pelo menos um commit
+    deps: [plan-check]
+    cmds:
+      - sudo /usr/local/bin/release-build .
+
+  sync-deploy:
+    desc: Sincroniza metadados do source para o deploy
+    cmds:
+      - /home/aalbertoni/.config/homelab/stacks/gdq-proposer/scripts/sync-source-to-stack
+
+  deploy-staging:
+    desc: Portao 4
+    deps: [gate1, review-agents-consensus, build-release]
+    cmds:
+      - sudo /usr/local/bin/deploy-staging gdq-proposer
+
+  smoke-staging:
+    desc: Smoke interno do staging
+    cmds:
+      - sudo /usr/local/bin/stack-status gdq-proposer-staging
+      - sudo /usr/local/bin/stack-health gdq-proposer-staging 60
+      - scripts/smoke.sh "http://localhost:18501"
+
+  smoke-staging-public:
+    desc: Smoke publico do staging
+    cmds:
+      - cmd: 'echo "Skipping public staging smoke: app interno"'
+
+  promote-prod:
+    desc: Portao 5
+    cmds:
+      - sudo /usr/local/bin/deploy-prod gdq-proposer
+
+  verify-prod:
+    desc: Valida a producao internamente
+    cmds:
+      - sudo /usr/local/bin/stack-status gdq-proposer
+      - sudo /usr/local/bin/stack-health gdq-proposer 60
+      - sudo /usr/local/bin/stack-logs gdq-proposer 50
+
+  verify-prod-public:
+    desc: Valida a producao via URL publica
+    cmds:
+      - cmd: 'echo "Skipping public production smoke: app interno"'
+
+  rollback-last:
+    desc: Faz rollback para a ultima release saudavel
+    cmds:
+      - sudo /usr/local/bin/stack-rollback gdq-proposer
+
+  pipeline-staging:
+    desc: Executa gates ate staging interno
+    cmds:
+      - task: gate1
+      - task: snapshot
+      - task: review-agents-consensus
+      - task: build-release
+      - task: deploy-staging
+      - task: smoke-staging
+
+  pipeline-prod:
+    desc: Executa gates, staging e verificacao interna de producao
+    cmds:
+      - task: pipeline-staging
+      - task: promote-prod
+      - task: verify-prod
diff --git a/app.yaml b/app.yaml
new file mode 100644
index 0000000..0dbcd82
--- /dev/null
+++ b/app.yaml
@@ -0,0 +1,60 @@
+name: gdq-proposer
+tier: candidate
+stack_profile: python-api
+port: 8501
+health_path: /_stcore/health
+
+source_path: /home/claude-deploy/projects/gdq-proposer
+workspace_path: /home/claude-deploy/workspaces/gdq-proposer
+deploy_path: /home/aalbertoni/.config/homelab/stacks/gdq-proposer
+runtime_path: /home/aalbertoni/.config/appdata/gdq-proposer
+release_path: /home/aalbertoni/.config/homelab/releases/gdq-proposer
+
+public_url: ""
+
+has_database: false
+database_type: none
+requires_migrations: false
+has_background_jobs: false
+
+test:
+  command: ".venv/bin/pytest tests/ -v -m 'not athena'"
+  coverage_command: ".venv/bin/pytest tests/ -v --tb=short --cov=core --cov=infra --cov=services --cov=strategies --cov=pages --cov-report=term-missing -m 'not athena'"
+
+lint:
+  command: ""
+
+typecheck:
+  command: ""
+
+security:
+  secret_scan_command: "gitleaks detect --no-banner --source ."
+  sast_command: ""
+  dependency_scan_command: "pip-audit -r requirements.txt"
+
+build:
+  dockerfile: Dockerfile
+  context: .
+  image_name: homelab/gdq-proposer
+
+smoke:
+  local_command: "curl -fsS http://localhost:8501/_stcore/health"
+  staging_command: "curl -fsS http://localhost:18501/_stcore/health"
+  public_command: "echo no-public-smoke-configured"
+
+review_agents:
+  - architecture
+  - security
+  - tests
+  - release-ops
+
+deploy:
+  stack_name: gdq-proposer
+  staging_stack_name: gdq-proposer-staging
+  requires_staging: true
+  requires_manual_prod_approval: true
+  allow_rollback: true
+  traefik_enabled: false
+  authelia_enabled: false
+
+secrets: []
diff --git a/requirements.txt b/requirements.txt
index ce9b541..f595483 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -13,5 +13,6 @@ jinja2>=3.1
 
 # Testes
 pytest>=8.0
+pytest-cov>=5.0
 duckdb>=1.0
 pyarrow>=14.0
diff --git a/scripts/healthcheck.sh b/scripts/healthcheck.sh
new file mode 100755
index 0000000..ab52ef0
--- /dev/null
+++ b/scripts/healthcheck.sh
@@ -0,0 +1,6 @@
+#!/usr/bin/env bash
+set -euo pipefail
+
+PORT="${PORT:-8501}"
+
+curl -fsS "http://localhost:${PORT}/_stcore/health"
diff --git a/scripts/smoke.sh b/scripts/smoke.sh
new file mode 100755
index 0000000..1f163e0
--- /dev/null
+++ b/scripts/smoke.sh
@@ -0,0 +1,11 @@
+#!/usr/bin/env bash
+set -euo pipefail
+
+TARGET="${1:-http://localhost:${PORT:-8501}}"
+
+if [[ -z "$TARGET" || "$TARGET" == '""' ]]; then
+  echo "Skipping smoke: no target configured"
+  exit 0
+fi
+
+curl -kfsS "${TARGET%/}/_stcore/health"

Contexto do projeto:
# Project Context

- Project: `gdq-proposer`
- Generated at: `2026-03-21T02:11:55Z`
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

---

## Dependencias

```
# requirements.txt
streamlit>=1.30       # UI
plotly>=5.18          # graficos
pyathena>=3.0         # Athena
boto3>=1.34           # AWS SDK
pandas>=2.1           # dados
numpy>=1.26           # estatistica
jinja2>=3.1           # templates SQL

# Testes
pytest>=8.0
duckdb>=1.0           # backend de teste (substitui Athena nos testes)
pyarrow>=14.0         # leitura de parquet nos testes
```

---

## Referencia Rapida: Modelos

| Modelo | Arquivo | Uso |
|--------|---------|-----|
| `DatasetConfig` | `core/models/dataset_config.py` | Config da tabela alvo |
| `ColumnProfile` | `core/models/column_profile.py` | Resultado da classificacao |
| `BaselineStrategy` | `core/models/baseline.py` | Como calcular baseline |
| `DualGuardSpec` | `core/models/dual_guard.py` | Representacao intermediaria do dual guard |
| `RuleProposal` | `core/models/rule_proposal.py` | Proposta com evidencia |
| `RuleSelection` | `core/models/rule_selection.py` | Regra no carrinho |
| `BacktestSummary` | `core/models/rule_proposal.py` | Resultado do backtest |
| `RuleScore` | `core/rule_scoring.py` | Avaliacao composta da regra |
| `RuleEvaluation` | `core/models/rule_evaluation.py` | Avaliacao enriquecida com regime (7 dimensoes) |
| `ComparisonResult` | `core/proposal_comparator.py` | Resultado de comparacao entre 2 propostas |
| `BacktestAnalysis` | `core/backtest_analysis.py` | Streaks, violation rate, tail risk do backtest |
| `SemanticType` | `core/models/enums.py` | Tipos de coluna |
| `RuleType` | `core/models/enums.py` | Tipos de regra |
| `ThunderaPayload` | `core/models/glue_test.py` | Payload JSON para Glue job Thundera |
| `GlueTestResult` | `core/models/glue_test.py` | Resultado da execucao do teste |
| `SeriesProfile` | `core/models/series_profile.py` | Perfil estatistico (regime + flags + metricas) |
| `SeriesRegime` | `core/models/enums.py` | Regime estatistico da serie |
| `GDQCapabilityStatus` | `core/models/enums.py` | Status validated/experimental/unknown |

---

## Referencia Rapida: Sintaxe GDQ

> **Referencia completa:** `docs/gdq_syntax_reference.md`

**REGRAS CRITICAS DE SINTAXE:**
- Nomes de coluna **SEM aspas**: `Mean VLR_SALDO` (nao `Mean "VLR_SALDO"`)
- Nomes de regra em **CamelCase**: `Mean`, `StandardDeviation`, `RowCount`, `CustomSql`
- Funcoes dinamicas em **lowercase**: `avg(last(30))`, `std(last(30))`

### Regras Dinamicas — Padrao "Dual Guard" (sigma OR margem%)

```
# Mean (coluna numerica) — com buffer 0.01, K inteiro
(((Mean {COL} >= (avg(last({N})) - ({K} * std(last({N}))) - 0.01)) AND (Mean {COL} <= (avg(last({N})) + ({K} * std(last({N}))) + 0.01))) OR ((Mean {COL} >= (avg(last({N})) * 0.9) - 0.01) AND (Mean {COL} <= (avg(last({N})) * 1.1) + 0.01)))

# StandardDeviation — mesmo padrao do Mean
# RowCount — SEM buffer, K como float (2.0), formato de margem diferente
```

### Regras Estaticas

```
CustomSql "select ... from primary" between {LOWER} and {UPPER}

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

  promote-prod:
    desc: Portao 5
    cmds:
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

  pipeline-prod:
    desc: Executa gates, staging e verificacao interna de producao
    cmds:
      - task: pipeline-staging
      - task: promote-prod
      - task: verify-prod

```

# Relevant Routes

# Relevant Tests

# Git Snapshot

## Status

```text
 M reviews/latest/project-context.md
?? reviews/latest/README.md
?? reviews/latest/architecture.prompt.md
?? reviews/latest/diff.patch
?? reviews/latest/release-ops.prompt.md
?? reviews/latest/security.prompt.md
?? reviews/latest/tests.prompt.md

```

## Diff Stat vs HEAD

```text
 reviews/latest/project-context.md | 22 ++++++++--------------
 1 file changed, 8 insertions(+), 14 deletions(-)

```
