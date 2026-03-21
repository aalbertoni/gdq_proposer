Voce e um revisor de arquitetura senior.

Analise o diff abaixo e responda SOMENTE em JSON com o formato padrao.

Verifique obrigatoriamente:
1. A separacao entre source, deploy, runtime e secrets foi mantida?
2. Ha tentativa de modificar runtime ou secrets diretamente?
3. Ha acoplamento excessivo entre modulos?
4. Ha logica operacional fora dos pontos previstos pelo playbook?
5. Ha violacao de padroes de caminhos, ownership ou wrappers?
6. O diff introduz complexidade desnecessaria ou dependencia nao justificada?

Formato esperado:
{
  "status": "APROVADO|ATENCAO|BLOQUEADO",
  "blockers": [],
  "warnings": [],
  "summary": "Resumo em uma linha."
}

Diff:
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

