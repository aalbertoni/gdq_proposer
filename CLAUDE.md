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
ColumnValues {COL} in [2, 1, 3]
DistinctValuesCount {COL} = 3
Completeness {COL} >= 1.00
IsPrimaryKey COL1 COL2 COL3
```

---

## Notas Importantes

1. **Referencia de sintaxe GDQ real:** `docs/gdq_syntax_reference.md` — SEMPRE consultar antes de gerar sintaxe
2. **Nomes de coluna sem aspas na sintaxe GDQ** — diferente do SQL Athena onde usamos aspas duplas
3. **CustomSql usa `from primary`** — keyword GDQ que referencia a tabela sendo avaliada
4. **Frequencia em percentual 0-100** (nao 0-1) nas regras CustomSql
5. **Todas as regras dinamicas usam padrao dual guard (sigma OR margem %)** — nunca gerar so uma parte
6. **CustomSql tambem suporta `avg(last(N))` no between** — regras categoricas podem ser dinamicas
7. **Athena retorna arrays de percentil como lista (DictCursor) ou string (PandasCursor)** — `_parse_percentile_array` trata ambos
8. **Coluna de data pode ser string** — sempre usar `date_expression` do config para normalizar
9. **Streamlit reruns inteiros** a cada interacao — usar `st.session_state` para preservar estado
10. **Plotly `add_hrect`** e ideal para desenhar bandas de confianca no grafico
11. **Partition method muda a logica das queries:**
    - INCREMENTAL: GROUP BY partition_column, cada particao = 1 processamento
    - FULL_SNAPSHOT: GROUP BY partition_column, cada particao contem foto completa
    - Sempre usar `effective_temporal_axis` do DatasetConfig como eixo de GROUP BY
    - Sempre usar `effective_partition_filter` para partition pruning (reduz custo Athena)
12. **Thundera** e o pipeline generico de qualidade de dados via Glue job
    - Payload JSON com campos UPPER_CASE (SQUAD, COD_TABE, VARIAVEIS.GDQ)
    - Argumento do Glue job: `--objson` (nao `--payload`)
    - CustomSql rules com escaping automatico de aspas via json.dumps
13. **DuckDB e dependencia de teste apenas** — nunca importar em codigo de producao
    - Testes usam `DuckDBTestClient` de `tests/conftest.py`
    - `QueryBuilder(dialect=SQLDialect.DUCKDB)` nos testes para SQL compativel
14. **PyAthena usa DictCursor** (nao PandasCursor) — busca resultados via API GetQueryResults, sem acessar S3
    - `execute_df()` faz `pd.DataFrame(cursor.fetchall())`, nao `cursor.as_pandas()`
    - `execute()` retorna `list[dict]` direto do DictCursor
    - `s3_staging_dir=""` quando workgroup configurado — desabilita referencia ao S3
    - NULLs do Athena chegam como Python `None` (nao `float('nan')`)
15. **information_schema para metadados** — `get_columns_with_partitions()` usa
    `information_schema.columns` (SQL padrao) em vez de `DESCRIBE` (formato varia entre cursors)
    - Colunas retornadas: `column_name`, `data_type`, `extra_info` (contem "partition key")
16. **Timeout adaptativo** — `AthenaClient.adapt_timeout(estimated_rows)` ajusta timeout
    baseado na volumetria: >500M=10min, >100M=6min, >10M=4min, default=2min
    - `DatasetService.estimate_volume_and_adapt_timeout()` roda COUNT(*) com partition pruning
17. **Partition pruning em TODAS as queries de analise** — todos os templates de analise
    aceitam `partition_filter` opcional via Jinja2 `{% if partition_filter %}`
    - Templates: numeric_history, row_count_history, distinct_count_history,
      categorical_distribution, categorical_domain, uniqueness_check
    - `AnalysisService._resolve_partition_filter()` gera filtro via `QueryBuilder.resolve_partition_filter()`
18. **Proxy corporativo** — `.env` configura HTTP_PROXY/HTTPS_PROXY/NO_PROXY
    - `infra/aws_session.py` forca S3 path-style e propaga CA bundle
    - `preflight_check.py` valida proxy, CA bundle, conectividade
    - `pages/06_diagnostico.py` mostra SSL tests, proxy detection, environment fingerprint

## Classificacao Semantica de Colunas (column_classifier)

Modulo: `core/column_classifier.py`. Servico: `services/profiling_service.py`.

### Inputs (coletados via SQL — `batch_column_sample.sql` / `column_sample.sql`)

| Metrica | SQL | Descricao |
|---------|-----|-----------|
| `athena_type` | `information_schema.columns` | Tipo fisico (varchar, bigint, double, date...) |
| `total_count` | `COUNT(*)` | Linhas na amostra (ultimos `sample_periods` dias, default 10) |
| `non_null_count` | `COUNT("col")` | Linhas nao-nulas |
| `distinct_count` | `APPROX_DISTINCT("col")` | Valores distintos (aproximado) |
| `numeric_cast_count` | `SUM(CASE WHEN TRY_CAST("col" AS DOUBLE) IS NOT NULL ...)` | So para strings: quantos valores sao castaveis para numero |

Metricas derivadas: `null_ratio`, `distinct_ratio`, `numeric_cast_ratio`.

### Camada 1 — Tipo Fisico Athena (sem query)

| Tipo normalizado | Resultado |
|-----------------|-----------|
| `tinyint, smallint, int, integer, bigint, float, double, decimal, real` | **NUMERIC** (com guardrails de cardinalidade) |
| `date, timestamp, timestamp with time zone` | **DATETIME** |
| `string, varchar, char, binary, varbinary` | vai para Camada 2 |

Normalizacao: `varchar(255)` → `varchar`, `decimal(10,2)` → `decimal`, `BIGINT` → `bigint`.

### Camada 1b — Guardrails de Numericas Nativas (`suggest_reclassification`)

| Condicao | Resultado | Exemplo |
|----------|-----------|---------|
| `distinct <= 20` | **CATEGORICAL_LOW** | COD_SITU (int com valores 1,2,3) |
| `distinct >= 10000 AND ratio >= 50% AND tipo inteiro` | **IDENTIFIER** | NUM_CONTRATO (bigint) |
| `tipo double/decimal com alta cardinalidade` | mantém **NUMERIC** | VLR_SALDO |

### Camada 2 — Heuristica de Conteudo (strings castaveis)

| Condicao | Resultado | Exemplo |
|----------|-----------|---------|
| `cast_ratio >= 0.95 AND distinct >= 10000 AND ratio >= 50%` | **IDENTIFIER** | CPF (varchar "12345678901") |
| `cast_ratio >= 0.95 AND distinct <= 20` | **CATEGORICAL_LOW** | COD_TIPO (varchar "1","2","3") |
| `cast_ratio >= 0.95 AND 21 <= distinct <= 9999` | **NUMERIC** | VLR_PARCELA (varchar com valores monetarios) |
| `cast_ratio < 0.95` | vai para Camada 3 | |

### Camada 3 — Cardinalidade (strings nao-numericas)

| Condicao | Resultado | Exemplo |
|----------|-----------|---------|
| `non_null == 0` | **UNKNOWN** | Coluna 100% nula |
| `distinct <= 50 AND ratio < 0.005` | **CATEGORICAL_LOW** | UF (27 estados) |
| `distinct <= 500 AND ratio < 0.05` | **CATEGORICAL_MID** | CIDADE (300 cidades) |
| Senao | **CATEGORICAL_HIGH** | NOME_CLIENTE |

### Thresholds (configuraveis em `column_classifier.py`)

| Constante | Valor | Uso |
|-----------|-------|-----|
| `NUMERIC_CAST_THRESHOLD` | 0.95 | Min ratio cast para classificar string como NUMERIC |
| `LOW_CARDINALITY_MAX_DISTINCT` | 50 | Max distinct para CATEGORICAL_LOW |
| `LOW_CARDINALITY_MAX_RATIO` | 0.005 | Max ratio para CATEGORICAL_LOW |
| `MID_CARDINALITY_MAX_DISTINCT` | 500 | Max distinct para CATEGORICAL_MID |
| `MID_CARDINALITY_MAX_RATIO` | 0.05 | Max ratio para CATEGORICAL_MID |
| `NUMERIC_LOW_CARD_MAX_DISTINCT` | 20 | Guardrail: numerico nativo com <= 20 distintos → categorica |
| `NUMERIC_HIGH_CARD_MIN_DISTINCT` | 10000 | Guardrail: inteiro com >= 10k distintos → identificador |
| `NUMERIC_HIGH_CARD_MIN_RATIO` | 0.50 | Guardrail: + ratio >= 50% → confirma identificador |

### SemanticType → Regras GDQ

| SemanticType | Regras geradas |
|-------------|----------------|
| NUMERIC | Mean, StandardDeviation, Completeness |
| CATEGORICAL_LOW | AllowedValues, DistinctCountExact, Frequency, Completeness |
| CATEGORICAL_MID | DistinctCountRange, Top-20 Frequency, Completeness |
| CATEGORICAL_HIGH | Completeness only |
| DATETIME | Nenhuma (eixo temporal) |
| IDENTIFIER | IsPrimaryKey (se chave), Completeness |
| UNKNOWN | Nenhuma |

### Limitacoes conhecidas

1. Gap entre 20-9999 distintos na Camada 2: strings castaveis com ~200 distintos sao NUMERIC, mas podem ser codigos
2. Sem analise de padrao textual (comprimento fixo, leading zeros, formato misto)
3. APPROX_DISTINCT pode variar entre execucoes, cruzando boundaries
4. Amostra de 10 periodos pode nao representar colunas com sazonalidade
5. Sem distincao entre CATEGORICAL_HIGH e FREE_TEXT
6. `suggest_reclassification` nao reclassifica double/decimal para IDENTIFIER (intencional: saldos tem alta cardinalidade)

---

## Diagnosticos Estatisticos (Painel de Calibracao)

Ferramentas de apoio exibidas na pagina Explore para auxiliar na calibracao:

| Ferramenta | Algoritmo | Metrica Gabarito | Impacta Regra? |
|------------|-----------|------------------|----------------|
| Change-Point Detection | CUSUM bilateral + filtro de magnitude (>1.5x std, >5% relativo) | Periodo e magnitude da mudanca | NAO |
| Sazonalidade Semanal | Eta-squared (variancia entre grupos / total) | Eta² > 15% + amplitude > 10% | NAO |
| IQR (Tukey Fences) | Q1 - 1.5*IQR, Q3 + 1.5*IQR | Limites e outliers detectados | NAO |
| MAD (Median Absolute Deviation) | Mediana ± 3 * MAD * 1.4826 | Limites e outliers detectados | NAO |
| Weighted Coverage | Cobertura com decaimento exponencial (lambda=0.05) | % cobertura ponderada recente | NAO |

## Auto-Tune (find_best_params)

Grid search de 200 combinacoes (N x sigma x margem x margin_on) com scoring **outlier-aware**.
Detalhes completos em `docs/adr/ADR-005-grid-search-scoring.md`.

**Principio:** maximizar cobertura de pontos normais, excluindo outliers da banda.

**Outlier detection:** IQR com fator 2.5 (conservador — so marca extremos).

**Scoring (10 componentes):**

| Componente | Peso | Descricao |
|------------|------|-----------|
| normal_coverage | ~1.0 (dominante) | Cobertura de pontos nao-outlier |
| outlier_penalty | -0.15 max | Penaliza cobrir outliers |
| fp_penalty | -0.05/FP | Falsos positivos |
| stability_bonus | +0.10 max | Estabilidade da banda |
| width_penalty | quadratico (thresh 0.20) | Banda larga |
| sigma_preference | -sigma*0.02 | Prefere sigma menor |
| margin_preference | -margin*0.10 | Prefere margem menor |
| drift_bonus | +/-0.05 | Drift detectado |
| n_penalty | -0.05 se N<15 | Janela curta |
| recency_bonus | variavel | Cobertura recente melhor que geral |

**BacktestSummary.point_results:** Lista de `{index, value, passed}` por ponto avaliado.
Usado pelo auto-tune para cruzar com mascara de outliers.

## Score Composto Enriquecido (score_proposal / evaluate_proposal)

Scoring de regras com 6 dimensoes ponderadas + penalidade de FP risk.
Modulo: `core/rule_scoring.py`, modelo enriquecido: `core/models/rule_evaluation.py`.

**Pesos:**

| Dimensao | Peso | Fonte |
|----------|------|-------|
| coverage | 0.30 | Backtest coverage_pct / 100 |
| stability | 0.20 | Backtest stability_score |
| interpretability | 0.10 | Hardcoded por RuleType |
| cost_efficiency | 0.10 | Hardcoded por RuleType (built-in=1.0, CustomSql=0.7) |
| regime_fit | 0.15 | Adequacao regra vs regime da serie |
| robustness | 0.15 | Qualidade dos dados (n_valid, null%, outliers) |
| fp_risk | -0.10 * risk | Penalidade: CV alto, assimetria, FPs no backtest |

**regime_fit**: Lookup (regime, rule_type) com overrides especificos.
Ex: Mean em STRUCTURAL_BREAK = 0.3, Completeness em SPARSE = 0.9.
Regimes secundarios aplicam 30% do impacto como penalidade adicional.

**evaluate_proposal()**: Retorna `RuleEvaluation` com todas 7 dimensoes + `regime_warnings` contextuais.
**score_proposal()**: Backward-compatible, aceita `profile` opcional.

**UI integration:** `classify_series()` chamado uma vez por coluna no 02_explore.py (cacheado em session_state).
Profile passado para `_render_add_to_cart(profile=)` que exibe `explain_regime_context()` e `explain_trade_offs()` dentro do expander de sintaxe.
Regime badge exibido no topo de cada coluna numerica e no tab Tabela.

---

## Regime Estatistico (SeriesProfile)

Classificacao pragmatica de series temporais para orientar propostas e calibracao.
Modulo: `core/series_regime.py`, modelo: `core/models/series_profile.py`.

| Regime | Condicao | Impacto na Regra |
|--------|----------|------------------|
| STABLE | Nenhum flag ativo | Regras padroes funcionam bem |
| VOLATILE | CV > 30% | Banda larga, risco de FP, considerar margem maior |
| TRENDING | Drift detectado (R² > 0.5) | Baseline movel, N menor pode ser melhor |
| SEASONAL | Eta² > 15% + amplitude > 10% | N multiplo de 7 suaviza efeito semanal |
| STRUCTURAL_BREAK | Change-point com magnitude significativa | Baseline deve usar apenas pos-mudanca |
| ZERO_INFLATED | >= 30% zeros | Distribuicao degenerada, banda simetrica inadequada |
| ASYMMETRIC | \|skewness\| > 1.0 | Bandas simetricas podem gerar FP assimetricos |
| SPARSE | >= 30% nulos | Dados insuficientes, confiabilidade reduzida |

O regime principal e o mais impactante (prioridade: structural_break > trending > seasonal > ...).
Regimes secundarios sao detectados mas nao dominam a classificacao.

## Backtest Enriquecido (BacktestAnalysis)

Analise aprofundada dos resultados de backtest para detectar padroes de falha.
Modulo: `core/backtest_analysis.py`.

| Metrica | Descricao | Alerta |
|---------|-----------|--------|
| max_fail_streak | Maior sequencia de falhas consecutivas | >= 3 → sinal de mudanca de regime |
| violation_rate | Taxa de violacao geral (falhas / total) | Referencia historica |
| recent_violation_rate | Taxa nos ultimos 7 periodos | > 1.5x historica → degradacao recente |
| tail_risk | Taxa de falha nos ultimos 20% dos dados | > 30% → risco de cauda |

**UI:** Expander "Analise do backtest" no painel de metricas da pagina Explore.
`summarize_backtest_analysis()` gera texto em pt-BR com insights automaticos.

## Explicabilidade (rule_explainer)

Funcoes de explicacao em linguagem natural em `core/rule_explainer.py`:

| Funcao | Entrada | Saida |
|--------|---------|-------|
| `explain_rule(proposal)` | RuleProposal | Frase curta (1 linha) |
| `explain_rule_detail(proposal)` | RuleProposal | Markdown com parametros e evidencia |
| `explain_regime_context(proposal, profile)` | RuleProposal + SeriesProfile | Texto sobre impacto do regime na regra |
| `explain_trade_offs(proposal, evaluation)` | RuleProposal + RuleEvaluation | Texto sobre regime_fit, FP risk, robustez |

**UI:** `explain_regime_context` e `explain_trade_offs` exibidos dentro do expander de sintaxe
quando ha SeriesProfile disponivel. Vazio para regime STABLE.

## GDQ Capability Matrix

Status de validacao por tipo de regra: `docs/gdq_capability_matrix.md`.

| Status | Significado |
|--------|-------------|
| validated | Testado e confirmado em producao |
| experimental | Funciona em testes, nao confirmado em producao |
| unknown | Sem evidencia |

Regras built-in (Mean, StdDev, RowCount, Completeness, etc): **validated**.
CustomSql dinamico (avg/std no between): **experimental**.

## Documentacao de Referencia

| Documento | Localizacao | Conteudo |
|-----------|-------------|----------|
| Spec Tecnica v1 | `docs/technical_spec_v1.md` | Arquitetura, modelos, contratos |
| Referencia de Sintaxe GDQ | `docs/gdq_syntax_reference.md` | Sintaxe exata de cada regra |
| Evolucao: CustomSql + IA | `docs/evolution_dynamic_sql_and_ai.md` | CustomSql dinamico, integracao IA |
| Setup AWS Teste | `docs/aws_test_setup.md` | IAM readonly + tabelas fake S3/Glue/Athena |
| Agente UX/UI | `docs/agents/ux_ui_agent.md` | Principios, padroes Streamlit, checklist |
| Agente Tech Writer (User) | `docs/agents/tech_writer_user_agent.md` | Documentacao in-app, progressive disclosure |
| Agente Tech Writer (Code) | `docs/agents/tech_writer_code_agent.md` | Docstrings, ADRs, documentacao de modulo |
| GDQ Capability Matrix | `docs/gdq_capability_matrix.md` | Status validated/experimental por tipo de regra |
