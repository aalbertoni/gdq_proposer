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
- `infra/athena_client.py` — Client PyAthena com timeout, logging e cache
- `infra/query_builder.py` — Templates Jinja2 com dialeto SQL via `sql_dialect.py`
- `infra/sql_dialect.py` — Adapta funcoes SQL entre Athena e DuckDB (usado nos testes)
- `infra/glue_client.py` — Wrapper boto3 para Glue jobs (integracao Thundera)
- `services/` — Camada de servico: dataset, profiling, analysis, proposal, export, glue_test
- `core/` — Logica pura: statistical_engine, backtest, rule_scoring, gdq_renderer, gdq_rule_generator
- `pages/` — 5 paginas Streamlit: Setup, Explore, Review, Teste, Ajuda
- `tests/conftest.py` — `DuckDBTestClient` para testes sem Athena real

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
7. **Athena retorna arrays de percentil como string** — parse necessario no `analysis_service`
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
