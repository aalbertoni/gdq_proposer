# Arquitetura — GDQ Rule Proposer

## Visao Geral

O GDQ Rule Proposer e uma ferramenta Streamlit que analisa o historico de dados
de tabelas via Amazon Athena e propoe regras de qualidade para o AWS Glue Data
Quality (GDQ). A ferramenta funciona com backend real (Athena/Presto) ou mock
local (DuckDB), usando o mesmo codigo SQL em ambos os cenarios.

O sistema segue uma arquitetura em camadas com separacao clara entre UI,
servicos de aplicacao, dominio/core e infraestrutura.

---

## Diagrama de Camadas

```
+---------------------------------------------------------------+
|                     Streamlit UI (pages/)                      |
|  app.py | 01_setup.py | 02_explore.py | 03_review.py         |
|  - Formularios, sliders, graficos Plotly                      |
|  - st.session_state para persistencia entre reruns            |
+---------------------------+-----------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|              Application Services (services/)                  |
|  DatasetService | ProfilingService | AnalysisService          |
|  ProposalService | ExportService                              |
|  - Orquestra queries + logica de dominio                      |
|  - Recebe/retorna dataclasses tipados                         |
+---------------------------+-----------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|                   Domain / Core (core/)                        |
|  statistical_engine | backtest | rule_scoring                 |
|  gdq_renderer | gdq_rule_generator | column_classifier        |
|  rule_explainer | models/*                                    |
|  - Funcoes puras (sem I/O, sem Athena, sem UI)                |
|  - Recebe dados agregados, retorna resultados tipados         |
+---------------------------+-----------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|                  Infrastructure (infra/)                       |
|  AthenaClient | MockAthenaBackend | QueryBuilder              |
|  SQLDialect | QuerySafety | QueryLogger                      |
|  - Comunicacao com backends (PyAthena / DuckDB)               |
|  - Templates SQL Jinja2                                       |
|  - Validacao de seguranca e logging                           |
+---------------------------+-----------------------------------+
                            |
                            v
+---------------------------------------------------------------+
|                  Strategies (strategies/)                      |
|  RowCountStrategy (Protocol) | GenericBandRowCountStrategy    |
|  - Extensibilidade via Protocol para plugins enterprise       |
+---------------------------------------------------------------+
```

---

## Fluxo de Dados: Setup ate Export

O fluxo completo percorre 5 etapas sequenciais:

### 1. Setup (01_setup.py -> DatasetService + ProfilingService)

O usuario configura a tabela alvo:

```
Usuario -> 01_setup.py
  -> DatasetService.validate_table()       -- tabela existe?
  -> DatasetService.get_columns()          -- quais colunas?
  -> DatasetService.get_date_range()       -- qual intervalo temporal?
  -> ProfilingService.profile_columns()    -- classificacao semantica
  -> DatasetConfig + ColumnProfile[]       -- salvo em session_state
```

- **Entrada:** schema, tabela, coluna de data, filtros
- **Saida:** `DatasetConfig` e lista de `ColumnProfile` no `session_state`

### 2. Analise (02_explore.py -> AnalysisService)

A ferramenta busca historico agregado via SQL:

```
02_explore.py
  -> AnalysisService.get_numeric_history()  -- media/stddev/percentis por periodo
  -> AnalysisService.get_row_count_history() -- contagem de linhas por periodo
  -> DataFrame normalizado                   -- dados para ProposalService
```

- **Entrada:** `DatasetConfig` + coluna selecionada
- **Saida:** `DataFrame` com series temporais agregadas

### 3. Propostas (02_explore.py -> ProposalService)

O servico orquestra motor estatistico, backtest, scoring e gerador:

```
ProposalService.propose_numeric_rules()
  -> statistical_engine.compute_dynamic_band()  -- banda sigma
  -> statistical_engine.compute_margin_band()   -- banda margem
  -> backtest.backtest_band()                   -- simulacao historica
  -> rule_scoring.score_proposal()              -- score composto
  -> gdq_rule_generator.generate()              -- sintaxe GDQ
  -> RuleProposal[]                             -- com evidencia completa

ProposalService.propose_table_rules()
  -> GenericBandRowCountStrategy.propose()      -- mesma pipeline para RowCount
```

- **Entrada:** `DataFrame` de historico + `BaselineStrategy`
- **Saida:** lista de `RuleProposal` com backtest, score e sintaxe

### 4. Calibracao (02_explore.py)

O usuario ajusta parametros via sliders e ve o impacto em tempo real:

```
Usuario ajusta N/sigma/margin
  -> ProposalService.recalculate_proposal()  -- recalcula tudo
  -> Grafico Plotly atualiza                 -- bandas + pontos historicos
  -> Score/coverage/FP atualizam             -- metricas lado a lado
```

### 5. Revisao e Export (03_review.py -> ExportService)

O usuario revisa o carrinho de regras e exporta:

```
03_review.py
  -> ExportService.generate_syntax()    -- concatena regras habilitadas
  -> ExportService.validate_syntax()    -- parenteses balanceados, etc
  -> ExportService.export()             -- gera .txt para download
```

- **Entrada:** lista de `RuleSelection` (carrinho)
- **Saida:** texto GDQ pronto para cadastro no AWS Glue

---

## Decisoes de Design Fundamentais

### Athena-first

Toda computacao estatistica pesada e feita via SQL no Athena. O servidor
Streamlit recebe apenas dados agregados (medias, desvios, percentis por
periodo). Nunca se puxam linhas brutas (raw rows) para o app.

Isso garante:
- **Custo controlado:** Athena cobra por volume de dados escaneados
- **Escalabilidade:** funciona com tabelas de bilhoes de linhas
- **Seguranca:** nenhum dado sensivel trafega para o servidor

### QueryExecutor Protocol

O codigo nunca acessa Athena diretamente. O `AthenaClient` encapsula
tanto o backend real (PyAthena) quanto o mock (DuckDB). Quem consome
ve a mesma interface `execute_df(sql)` independente do backend.

### DualGuardSpec — Representacao Intermediaria

A sintaxe GDQ nunca e gerada como string diretamente. O fluxo e:

```
RuleProposal -> DualGuardSpec -> DualGuardRenderer -> string GDQ
```

O `DualGuardSpec` carrega os parametros (metrica, N, K, margem, buffer)
e o `FormattingProfile` dita as diferencas de formato por tipo de regra
(Mean vs StdDev vs RowCount). Isso evita erros de formatacao e garante
consistencia.

### SQL Dialect Adaptation (Athena <-> DuckDB)

A maioria do SQL e identica entre Athena e DuckDB. As poucas diferencas
sao tratadas no `infra/sql_dialect.py`:

- **APPROX_PERCENTILE:** Athena usa `APPROX_PERCENTILE(col, ARRAY[...])`,
  DuckDB usa `QUANTILE_CONT(col, [...])`
- **STDDEV:** Athena usa `STDDEV(...)`, DuckDB usa `STDDEV_SAMP(...)`
- **DATE_ADD:** Athena usa `DATE_ADD('day', -N, CURRENT_DATE)`,
  DuckDB usa `CURRENT_DATE - INTERVAL 'N' DAY`
- **TABLE_REF:** Athena usa `"schema"."table"`, DuckDB usa `"table"` (sem schema)

Os templates SQL Jinja2 recebem as funcoes adaptadas via `QueryBuilder`,
que injeta a versao correta com base no dialeto ativo.

### Strategy Protocol para RowCount

O `RowCountStrategy` e um `@runtime_checkable Protocol` que permite
equipes enterprise plugarem logica customizada (sazonalidade, calendario
de negocios) sem alterar o core. A implementacao default
`GenericBandRowCountStrategy` usa a mesma pipeline de banda sigma + margem.

---

## Grafo de Dependencias entre Modulos

```
config.py
  |
  v
infra/sql_dialect.py --------+
  |                          |
  v                          v
infra/query_safety.py    infra/query_builder.py
  |                          |
  v                          v
infra/mock_athena.py     infra/query_logger.py
  |                          |
  +-------+------------------+
          |
          v
  infra/athena_client.py
          |
          v
  services/dataset_service.py ------> core/column_classifier.py
          |                                     |
          v                                     v
  services/profiling_service.py -----> core/models/column_profile.py
          |
          v
  services/analysis_service.py
          |
          v
  services/proposal_service.py
     |         |         |
     v         v         v
  core/       core/     core/
  statistical backtest  rule_scoring
  _engine.py  .py       .py
     |
     v
  core/gdq_rule_generator.py
     |
     v
  core/gdq_renderer.py -------> core/models/dual_guard.py
                                     |
                                     v
                              core/models/enums.py
```

Servicos dependem de `AthenaClient` e `QueryBuilder` (infraestrutura).
Servicos chamam modulos `core/` (dominio) para logica pura.
Modulos `core/` nunca dependem de infraestrutura ou UI.
O `strategies/` depende de `core/` e implementa o Protocol.

---

## Modulos Principais

### Camada de Dominio (core/)

**core/statistical_engine.py** — Motor estatistico com funcoes puras.
Calcula bandas dinamicas (sigma, margem, percentil, frequencia), bandas
rolantes e deteccao de drift via regressao linear. Nao faz I/O.

**core/backtest.py** — Simulacao historica com janela rolante. Para cada
ponto da serie, calcula a banda usando valores anteriores e verifica se
o ponto passa na regra dual guard (sigma OR margem). Retorna
`BacktestSummary` com coverage, falsos positivos, estabilidade e drift.

**core/rule_scoring.py** — Score composto que avalia qualidade de uma
proposta. Pesos: coverage 0.35, stability 0.25, interpretability 0.20,
cost_efficiency 0.20. Interpretability e cost_efficiency sao hardcoded
por tipo de regra (built-in = 1.0, CustomSql = 0.6). Classifica
confianca como HIGH (>=0.80), MEDIUM (>=0.55) ou LOW.

**core/gdq_renderer.py** — Converte `DualGuardSpec` em string GDQ. Usa
`FormattingProfile` para diferenciar formatacao entre Mean/StdDev
(K inteiro, buffer 0.01, margem como `avg * factor`) e RowCount
(K float, sem buffer, margem como `avg - (avg * pct)`).

**core/gdq_rule_generator.py** — Nivel mais alto do que o renderer.
Recebe `RuleProposal` + `UserOverride` opcionais, decide qual tipo de
regra gerar (dual guard, completeness, allowed values, etc) e delega
ao `DualGuardRenderer` ou gera strings simples.

**core/rule_explainer.py** — Gera explicacoes em linguagem natural a
partir de `RuleProposal`. Produz texto legivel para analistas que nao
conhecem sintaxe GDQ, incluindo descricao da regra, parametros e
evidencia do backtest.

**core/column_classifier.py** — Classificacao semantica em 3 camadas.
Camada 1: tipo fisico Athena (int/double -> NUMERIC, date -> DATETIME).
Camada 2: heuristica de conteudo (string castavel -> NUMERIC se > 95%).
Camada 3: cardinalidade para categoricas (low <= 50, mid <= 500, high).

### Modelos (core/models/)

**core/models/enums.py** — Enums do dominio: `SemanticType`,
`RuleType`, `ConfidenceLevel`, `MetricRef`, `PartitionMethod`,
`LookbackMode`, `GrainType`, `BaselineMethod`, `ExportOutputMode`.

**core/models/dataset_config.py** — Configuracao da tabela alvo.
Encapsula schema, tabela, metodo de particao, coluna temporal,
expressao de data, lookback, filtros e colunas selecionadas. Tem
properties para `effective_temporal_axis` e `effective_partition_filter`.

**core/models/column_profile.py** — Perfil de uma coluna apos
classificacao. Inclui tipo fisico Athena, tipo semantico inferido,
metricas de profiling (total, null ratio, distinct ratio) e override
manual do usuario.

**core/models/dual_guard.py** — Representacao intermediaria do padrao
dual guard. `DualGuardSpec` carrega metrica, target, N, K, margem,
buffer e `FormattingProfile`. Profiles pre-definidos: `MEAN_PROFILE`,
`STDDEV_PROFILE`, `ROWCOUNT_PROFILE`.

**core/models/rule_proposal.py** — Proposta de regra com evidencia.
`RuleProposal` tem thresholds sugeridos, parametros de baseline,
`BacktestSummary`, confianca, warnings, preview da sintaxe GDQ e
historico para graficos. `BacktestSummary` tem coverage, falsos
positivos, estabilidade, drift e outliers.

**core/models/rule_selection.py** — Regra no carrinho do usuario.
`RuleSelection` referencia um `RuleProposal` com `UserOverride`
opcionais e a sintaxe GDQ final. `UserOverride` permite ajustar
N, sigma, margem, lower, upper e valores.

**core/models/baseline.py** — Estrategia de baseline para calcular
thresholds. Configura metodo, n_periods, n_sigma, margin_pct,
percentis e minimo de pontos historicos.

### Camada de Servicos (services/)

**services/dataset_service.py** — Validacao de tabela, descoberta de
colunas, deteccao de particoes, range temporal e volume por periodo.
Usa `QueryBuilder` para montar SQL e `AthenaClient` para executar.

**services/profiling_service.py** — Profiling de colunas com
classificacao semantica. Camada 1 (tipos nativos) nao precisa de query.
Camada 2+3 (strings) executa query de amostragem para obter contagens,
distintos e castabilidade numerica. Delega classificacao ao
`column_classifier`.

**services/analysis_service.py** — Analise historica via SQL. Executa
queries de historico numerico (media, stddev, percentis por periodo) e
historico de row count. Normaliza DataFrames e parseia arrays de
percentis compativel com Athena e DuckDB.

**services/proposal_service.py** — Orquestra toda a pipeline de
propostas. Para numericas: gera Mean + StdDev + Completeness. Para
tabela: gera RowCount via Strategy. Suporta recalibracao (recalcula
banda, backtest, score e sintaxe com novos parametros).

**services/export_service.py** — Concatena sintaxe GDQ de regras
habilitadas, valida (parenteses balanceados) e exporta como texto.
Formato principal: `GDQ_RUNTIME` (sintaxe pura para cadastro).

### Camada de Infraestrutura (infra/)

**infra/athena_client.py** — Client unificado PyAthena + DuckDB.
Detecta modo (MOCK/REAL) via config e inicializa o backend correto.
Interface identica: `execute_df()`, `execute()`, `table_exists()`,
`get_columns()`, `get_columns_with_partitions()`. Loga metricas via
`QueryLogger`.

**infra/mock_athena.py** — Backend DuckDB que simula Athena. Carrega
parquet/CSV como tabelas in-memory. Suporta `execute()`, `execute_df()`,
`get_columns()`, `table_exists()`.

**infra/query_builder.py** — Montagem de queries SQL a partir de
templates Jinja2. Injeta funcoes adaptadas ao dialeto via
`sql_dialect.adapt_function()`. Metodos para cada tipo de query:
metadata, date range, volume, column sample, numeric history,
row count history.

**infra/sql_dialect.py** — Adaptador de funcoes SQL entre Athena e
DuckDB. Mapeia 4 funcoes: `APPROX_PERCENTILE`, `STDDEV`,
`DATE_SUBTRACT_DAYS`, `TABLE_REF`. Funcao `adapt_function()` interpola
parametros no template correto.

**infra/query_safety.py** — Validacao de seguranca para SQL.
`validate_identifier()` garante que nomes de schema/tabela/coluna
usam apenas caracteres permitidos. `validate_lookback()` limita janelas.
`sanitize_filter()` bloqueia tokens perigosos (`;`, `--`, `/*`) e
keywords destrutivas (DROP, DELETE, INSERT, etc).

**infra/query_logger.py** — Logging estruturado. Cada query gera um
`QueryLogEntry` com nome, dataset, coluna, tempo, rows, cache hit e
erros. `get_session_summary()` retorna metricas agregadas da sessao.

### Strategies (strategies/)

**strategies/row_count_strategy.py** — Protocol `RowCountStrategy` com
`@runtime_checkable` para extensibilidade enterprise. Implementacao
default `GenericBandRowCountStrategy` reutiliza a mesma pipeline do
core (statistical_engine + backtest + scoring + generator) para gerar
propostas RowCount dual guard.

### Templates SQL (queries/templates/)

- **metadata_discovery.sql** — `SELECT *` com `LIMIT 0` para obter schema
- **date_range.sql** — MIN/MAX da coluna temporal + COUNT DISTINCT periodos
- **volume_by_period.sql** — COUNT(*) GROUP BY periodo (ultimos N periodos)
- **show_partitions.sql** — SELECT DISTINCT na coluna de particao
- **column_sample.sql** — Profiling: total, non_null, distinct, numeric_cast
- **numeric_history.sql** — Media, stddev, min, max, percentis por periodo
- **row_count_history.sql** — COUNT(*) por periodo com lookback e ORDER ASC

---

## Configuracao Multi-Ambiente

O sistema suporta 3 ambientes via `config.py`:

- **LOCAL (mock):** DuckDB carrega CSVs/parquets de `mock_data/`.
  Nenhuma credencial AWS necessaria. Ideal para desenvolvimento.
- **DEV (Athena real):** PyAthena conecta via AWS CLI profile.
  Precisa de `AWS_PROFILE` configurado.
- **PROD (Athena + IAM):** PyAthena usa IAM role automaticamente.
  Sem credenciais explicitas.

Variaveis de ambiente:
- `GDQ_ENV` — `local`, `dev`, `prod`
- `GDQ_ATHENA_REGION` — regiao AWS
- `GDQ_ATHENA_WORKGROUP` — workgroup do Athena
- `GDQ_ATHENA_S3_OUTPUT` — bucket de output
- `GDQ_AWS_PROFILE` — named profile AWS CLI
- `GDQ_MOCK_DATA_DIR` — diretorio dos dados mock

---

## Padrao Dual Guard: Sigma OR Margem

Todas as regras dinamicas do GDQ Rule Proposer usam o padrao "dual guard":

```
(banda_sigma) OR (banda_margem)
```

Onde:
- **Banda sigma:** `metric >= avg(last(N)) - K*std(last(N))` AND `metric <= avg(last(N)) + K*std(last(N))`
- **Banda margem:** `metric >= avg(last(N)) * (1 - margin)` AND `metric <= avg(last(N)) * (1 + margin)`

O OR garante que series com baixa variabilidade (std -> 0) nao produzam
bandas impossivelmente estreitas. A banda de margem funciona como fallback.

Mais detalhes em `docs/adr/ADR-001-dual-guard-pattern.md`.

---

## Extensibilidade

O sistema foi desenhado para extensao sem modificacao do core:

- **Novos tipos de regra:** adicionar `RuleType` em enums, handler no
  `GDQRuleGenerator`, e logica de proposta no `ProposalService`
- **Novas estrategias RowCount:** implementar o Protocol `RowCountStrategy`
  e passar como parametro em `propose_table_rules(strategy=...)`
- **Novos backends SQL:** implementar a mesma interface do `AthenaClient`
- **Novos formatos de export:** adicionar `ExportOutputMode` e handler
  no `ExportService`
