Voce e um reviewer tecnico independente do plano de implementacao.

Sua tarefa:
- revisar o plano proposto pelo Claude Code antes da implementacao
- criticar riscos tecnicos, lacunas, regressao operacional, seguranca e UX/jornada
- retornar somente um objeto JSON no formato:
  {
    "status": "APROVADO" | "ATENCAO" | "BLOQUEADO",
    "blockers": ["..."],
    "warnings": ["..."],
    "summary": "..."
  }

Regras:
- use BLOQUEADO para plano tecnicamente inseguro, incompleto para release, ou com risco concreto de quebrar deploy, dados, seguranca ou jornada principal
- use ATENCAO para riscos moderados, lacunas de validacao, falta de rollback ou ambiguidade operacional
- use APROVADO quando o plano estiver coerente, executavel, validavel e reversivel
- critique o plano, nao implemente nada
- nao inclua markdown, comentarios extras nem texto fora do JSON

Rubrica de plano:
# Homelab Plan Review Rubric

Use this rubric to critique an implementation plan before coding begins.

## 1. Goal and Scope

Check:
- the objective is concrete
- scope is bounded
- out-of-scope is explicit

Warn if the plan is vague.
Block if the plan can expand into unrelated areas without control.

## 2. Technical Coherence

Check:
- the proposed approach matches the actual architecture
- responsibilities stay in the correct layer
- migrations, wrappers, secrets, deploy, and runtime concerns are placed correctly

Block if the plan is built on a false technical assumption.

## 3. Safety and Reversibility

Check:
- validation steps are explicit
- rollback is explicit
- release/deploy risk is acknowledged

Block if the plan changes runtime-critical paths without validation or rollback.

## 4. Security

Check:
- secrets remain server-side
- privileged actions go through wrappers
- payment, webhook, auth, and admin surfaces are reviewed explicitly when relevant

Block if the plan weakens security boundaries or omits obvious payment/webhook risk.

## 5. UX and Journey

Check:
- affected user journeys are identified
- edge states are called out
- failures or degraded states still have a clear next step

Warn or block if the plan can leave broken CTA chains, dead ends, or misleading completion states.

## 6. Testing and Diagnostics

Check:
- unit/integration/manual checks are identified
- health/smoke coverage is appropriate
- logs or diagnostics are sufficient to debug likely failure modes

Warn if validation is thin.
Block if the plan touches critical flows without a realistic validation strategy.

## 7. Verdict Mapping

Use `BLOQUEADO` for plans that are unsafe, incomplete for critical flows, or structurally wrong.
Use `ATENCAO` for usable but under-specified plans with moderate operational or UX risk.
Use `APROVADO` only when the plan is actionable, bounded, testable, and reversible.

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

Contexto de git status:
 M requirements.txt
?? .coverage
?? .dockerignore
?? Dockerfile
?? Taskfile.yml
?? app.yaml
?? reviews/
?? scripts/healthcheck.sh
?? scripts/smoke.sh

Contexto de diff stat:
 requirements.txt | 1 +
 1 file changed, 1 insertion(+)

Plano para revisar:
# Objective
- Colocar o repositorio `gdq-proposer` no formato de governanca do homelab, com `app.yaml`, `Taskfile.yml`, `Dockerfile`, scripts de health/smoke e deploy separado do source via imagem Docker.
- Preservar a logica funcional atual do app Streamlit e validar que staging e producao executam a imagem da release, sem bind mount do source.
- Garantir que o runtime containerizado continue funcional para a jornada principal do produto: diagnostico de ambiente, autenticacao AWS, leitura Athena e navegacao basica do fluxo Setup -> Explore -> Review -> Teste -> Diagnostico.

# Scope
- Ajustar `app.yaml`, `Taskfile.yml`, `Dockerfile`, `.dockerignore`, `scripts/healthcheck.sh` e `scripts/smoke.sh`.
- Ajustar o manifesto para declarar explicitamente os file-secrets de runtime AWS usados no deploy path, em vez de depender do `.env` do source.
- Gerar e manter as stacks `gdq-proposer` e `gdq-proposer-staging` no homelab, sincronizando `app.yaml` e `CLAUDE.md` pela via canonica.
- Validar `gate1`, `snapshot`, `review-agents-consensus`, `release-build`, deploy em staging e smoke funcional minimo antes de qualquer deploy em producao.
- Fora de escopo: mudar regras de negocio do app, adicionar banco, alterar Athena/Glue, criar URL publica, ou introduzir rotas HTTP novas so para smoke funcional.

# Assumptions
- O source oficial fica em `/home/claude-deploy/projects/gdq-proposer` e o workspace em `/home/claude-deploy/workspaces/gdq-proposer`.
- O deploy fica em `/home/aalbertoni/.config/homelab/stacks/gdq-proposer` e staging em `/home/aalbertoni/.config/homelab/stacks/gdq-proposer-staging`.
- O app nao usa banco nem migracoes.
- O runtime nao dependera do `.env` do source. Configuracoes de deploy ficam no path da stack.
- As credenciais e artefatos sensiveis AWS serao tratados como file-secrets no deploy path:
  - `/home/aalbertoni/.config/secrets/gdq-proposer/aws_credentials`
  - `/home/aalbertoni/.config/secrets/gdq-proposer/aws_config`
  - `/home/aalbertoni/.config/secrets/gdq-proposer/aws_ca_bundle` quando necessario
- Variaveis nao secretas de runtime ficam no `.env` da stack, por exemplo:
  - `GDQ_AWS_PROFILE`
  - `GDQ_ATHENA_REGION`
  - `GDQ_ATHENA_WORKGROUP`
  - `GDQ_ATHENA_S3_OUTPUT`
  - `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`
  - `AWS_SHARED_CREDENTIALS_FILE=/run/secrets/aws_credentials`
  - `AWS_CONFIG_FILE=/run/secrets/aws_config`
  - `AWS_CA_BUNDLE=/run/secrets/aws_ca_bundle` quando aplicavel
- Operacoes privilegiadas continuarao apenas por wrappers root-owned do homelab executados manualmente no host, nao por `sudo` direto a partir do `Taskfile.yml` do source.

# Affected Files
- `app.yaml`
- `Taskfile.yml`
- `Dockerfile`
- `.dockerignore`
- `requirements.txt`
- `scripts/healthcheck.sh`
- `scripts/smoke.sh`
- `reviews/latest/plan.md`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer/.env`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer/docker-compose.yml`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer/app.yaml`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer/source.CLAUDE.md`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer-staging/.env`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer-staging/docker-compose.yml`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer-staging/app.yaml`
- `/home/aalbertoni/.config/homelab/stacks/gdq-proposer-staging/source.CLAUDE.md`

# Strategy
- Materializar o source no path final e garantir permissao minima de leitura para `sync-source-to-stack`, sem abrir escrita no path do `claude-deploy`.
- Ajustar `app.yaml` para declarar os file-secrets AWS necessarios ao runtime containerizado, em vez de manter `secrets: []`.
- Sincronizar `app.yaml` e `CLAUDE.md` do source para staging e producao pela via canonica `scripts/sync-source-to-stack`.
- Ajustar `Taskfile.yml` para manter apenas tasks nao privilegiadas no source:
  - `plan-*`
  - `gate1`
  - `snapshot`
  - `review-agents*`
- Remover do `Taskfile.yml` qualquer dependencia de `sudo` direto para `release-build`, `deploy-staging`, `deploy-prod`, `stack-status`, `stack-health`, `stack-logs` ou `stack-rollback`.
- Executar `release-build`, `deploy-staging`, `deploy-prod` e rollback apenas como comandos manuais de host, fora do `Taskfile`, usando os wrappers canonicos do homelab.
- Construir a imagem da release com tag deterministica por data+SHA e subir staging pela stack `gdq-proposer-staging`.
- Validar staging em dois niveis:
  - readiness tecnico: `stack-status`, `stack-health`, `stack-logs` e `curl http://localhost:18501/_stcore/health`
  - smoke funcional minimo e reproduzivel:
    - abrir a UI de staging
    - entrar em `Diagnostico`
    - confirmar que as checagens de AWS/proxy/CA nao estao em erro bloqueante
    - em `Setup`, validar uma tabela canario conhecida de baixo custo no Athena e carregar colunas/metadata sem exception
    - confirmar que a navegacao para `Explore` e `Review` continua disponivel sem falha fatal de sessao
- Promover para producao apenas se staging passar nos dois niveis de validacao.
- Confirmar ausencia de bind mount do source por revisao do `docker-compose.yml` gerado da stack, que deve usar apenas imagem de release e volumes de runtime previstos.

# Risks
- Se os file-secrets AWS nao forem montados corretamente, staging/producao podem subir tecnicamente e falhar exatamente na jornada principal.
- Se o `Taskfile.yml` continuar chamando `sudo` direto, o projeto fica acoplado ao host e fora da disciplina de wrappers do homelab.
- `/_stcore/health` mede readiness do processo, nao funcionalidade Athena/Glue.
- Sem tabela canario definida e barata, o smoke funcional pode virar validacao manual vaga demais.
- Se `.env` ou `docker-compose.yml` da stack forem alterados sem backup previo, o rollback operacional fica fragil.

# Validation
- `sudo -u claude-deploy bash -lc "cd /home/claude-deploy/projects/gdq-proposer && task plan-consensus"`
- `sudo -u claude-deploy bash -lc "cd /home/claude-deploy/projects/gdq-proposer && task gate1"`
- `sudo -u claude-deploy bash -lc "cd /home/claude-deploy/projects/gdq-proposer && task snapshot"`
- `sudo -u claude-deploy bash -lc "cd /home/claude-deploy/projects/gdq-proposer && task review-agents-consensus"`
- `sudo /home/aalbertoni/.config/homelab/scripts/release-build /home/claude-deploy/projects/gdq-proposer`
- `sudo /home/aalbertoni/.config/homelab/scripts/deploy-staging gdq-proposer`
- `sudo /home/aalbertoni/.config/homelab/scripts/stack-status gdq-proposer-staging`
- `sudo /home/aalbertoni/.config/homelab/scripts/stack-health gdq-proposer-staging 60`
- `sudo /home/aalbertoni/.config/homelab/scripts/stack-logs gdq-proposer-staging 50`
- `curl -fsS http://localhost:18501/_stcore/health`
- Validacao funcional em staging:
  - abrir `Diagnostico`
  - confirmar ausencia de erro bloqueante de autenticacao AWS, proxy e CA
  - validar tabela canario conhecida e carregar metadata/colunas no `Setup`
  - confirmar navegacao minima para `Explore` e `Review` sem exception fatal
- Revisar `docker-compose.yml` das stacks para confirmar runtime por imagem e ausencia de mount do source.

# Rollback
- Antes de alterar `.env` ou `docker-compose.yml` da stack, criar backup:
  - `.env.bak.<datahora>`
  - `docker-compose.yml.bak.<datahora>`
- Se o plano for abandonado antes do deploy, reverter artefatos no source via `git revert` ou descartar o snapshot local.
- Se staging falhar, usar `sudo /home/aalbertoni/.config/homelab/scripts/stack-rollback gdq-proposer-staging`.
- Se producao falhar, usar `sudo /home/aalbertoni/.config/homelab/scripts/stack-rollback gdq-proposer`.
- Se o problema estiver na configuracao operacional, restaurar o backup do `.env` e do compose da stack antes do redeploy da release anterior.

Contexto do projeto:
# Project Context

- Project: `gdq-proposer`
- Generated at: `2026-03-21T02:10:09Z`
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
 M requirements.txt
?? .coverage
?? .dockerignore
?? Dockerfile
?? Taskfile.yml
?? app.yaml
?? reviews/
?? scripts/healthcheck.sh
?? scripts/smoke.sh

```

## Diff Stat vs HEAD

```text
 requirements.txt | 1 +
 1 file changed, 1 insertion(+)

```
