# CLAUDE.md — GDQ Rule Proposer

> Instruções para desenvolvimento assistido por IA com Claude Code.

---

## Projeto

**GDQ Rule Proposer** — Ferramenta Streamlit que analisa histórico de dados via Athena e propõe regras de qualidade para AWS Glue Data Quality (GDQ).

Especificação técnica completa: `docs/technical_spec_v1.md`
Setup de ambiente: `docs/sprint0_setup.md`

### Ambiente de desenvolvimento

- **Local (mock):** DuckDB carrega CSVs de `mock_data/` e emula Athena SQL
- **Local (Athena):** AWS CLI profile aponta para Athena real
- **Enterprise:** IAM role, sem credenciais explícitas

O código usa `QueryExecutor` protocol — nunca acessa Athena diretamente.
Sempre usar `create_executor(config)` para obter o executor correto.

**Compatibilidade SQL Athena ↔ DuckDB:**
- A maioria do SQL é idêntica
- Diferenças tratadas em `infra/sql_adapter.py` (SQLDialect)
- `APPROX_PERCENTILE` → `QUANTILE_CONT` no DuckDB
- `DATE_ADD('day', -N, CURRENT_DATE)` → `CURRENT_DATE - INTERVAL 'N' DAY` no DuckDB
- `DESCRIBE` → `PRAGMA table_info` no DuckDB

---

## Princípios de Desenvolvimento

### 1. Fatias verticais pequenas

Nunca implemente um sprint inteiro de uma vez. Trabalhe em fatias:

- 1 query template
- 1 serviço (com interface definida antes)
- 1 componente de UI
- 1 conjunto de testes
- 1 integração curta

### 2. Contrato antes de implementação

Sempre defina a interface (dataclass, type hints, docstring) ANTES de escrever o corpo. Consulte `docs/technical_spec_v1.md` para os contratos aprovados.

### 3. Testes junto com implementação

Módulos do `core/` DEVEM ter testes unitários. Use as fixtures em `tests/fixtures/` para dados sintéticos.

Módulos que exigem testes:

- `core/statistical_engine.py`
- `core/rule_scoring.py`
- `core/column_classifier.py`
- `core/gdq_rule_generator.py`
- `core/gdq_renderer.py` — testes contra exemplos de produção reais
- `core/backtest.py`
- `infra/query_safety.py`

### 4. Athena-first

- TODA computação estatística é feita via SQL no Athena
- O servidor Streamlit recebe APENAS dados agregados
- NUNCA puxe raw rows para o app
- Use `APPROX_PERCENTILE` ao invés de `PERCENTILE` exato
- Use partitions quando disponíveis para otimizar custo

### 5. SQL Dialect: Athena ↔ DuckDB

- Em LOCAL: queries rodam contra DuckDB (mock) com dados sintéticos
- Em DEV/PROD: mesmas queries rodam contra Athena real
- A ÚNICA coisa que muda é o backend — as queries SQL são conceptualmente idênticas
- Usar `infra/sql_dialect.py` para adaptar funções que diferem (APPROX_PERCENTILE, STDDEV, DATE_ADD)
- Templates Jinja2 recebem as funções corretas do query_builder baseado no dialeto

### 6. SQL Safety

- NUNCA interpole strings diretamente em SQL
- Use templates Jinja2 em `queries/templates/`
- Valide TODOS os identificadores com `infra/query_safety.py`
- O `base_filter_sql` do usuário deve passar por sanitização básica

---

## Modos de Operação (Agentes)

Ao iniciar uma tarefa, identifique qual modo é mais adequado:

### 🏗️ architect

**Quando:** início de sprint, decisões de design, novos componentes

**Foco:**
- Definir interfaces e contratos (type hints, dataclasses)
- Trade-offs de design
- Dependências entre componentes
- Nunca escreve implementação completa

**Output:** interfaces + assinaturas + docstrings + decisão documentada

**Exemplo de pedido:**
> "Defina a interface do ProposalService incluindo os métodos para numéricas e categóricas, com tipos de entrada e saída."

---

### 🗄️ athena-sql

**Quando:** criar ou otimizar queries Athena

**Foco:**
- SQL Presto/Trino compatível com Athena
- Templates Jinja2 parametrizados
- Otimização: partições, pushdown, aproximações
- Custo e performance
- NUNCA use sintaxe MySQL/PostgreSQL
- Manter compatibilidade DuckDB via `sql_dialect.py` (ver diferenças abaixo)

**Output:** template `.sql` + documentação de parâmetros + notas de performance

**Referência de dialeto:**
- Funções: `APPROX_PERCENTILE`, `TRY_CAST`, `DATE_ADD`, `DATE_TRUNC`
- Strings: aspas simples para valores, aspas duplas para identificadores
- Sem variáveis, sem UPDATE/DELETE, sem procedures
- CTEs são preferíveis a subqueries aninhadas

**Diferenças Athena ↔ DuckDB (tratadas pelo sql_dialect.py):**

| Athena | DuckDB | Adaptação |
|--------|--------|-----------|
| `APPROX_PERCENTILE(col, ARRAY[...])` | `QUANTILE_CONT(col, [...])` | Via template var |
| `STDDEV(col)` | `STDDEV_SAMP(col)` | Via template var |
| `DATE_ADD('day', -N, CURRENT_DATE)` | `CURRENT_DATE - INTERVAL 'N' DAY` | Via template var |
| `"schema"."table"` | `"table"` (sem schema) | Via TABLE_REF |

**Exemplo de pedido:**
> "Crie o template SQL para análise histórica de coluna numérica, com agregações por período, usando os parâmetros do DatasetConfig. Garanta compatibilidade com DuckDB via variáveis de dialeto."

---

### 📊 stats-engine

**Quando:** lógica estatística e backtest

**Foco:**
- Funções puras (sem I/O, sem Athena, sem UI)
- Recebe dados agregados (listas/DataFrames)
- Bandas dinâmicas (sigma, margem, percentil)
- Scoring de regras (coverage, false positives, stability)
- Edge cases: poucos pontos, zeros, nulls, drift
- Sempre com testes unitários

**Output:** funções tipadas + testes usando fixtures

**Fixtures disponíveis (`tests/fixtures/`):**
- `stable_series.py` — série estável sem anomalias
- `drift_series.py` — série com tendência crescente
- `seasonal_series.py` — variação por dia da semana
- `outlier_series.py` — série com 2-3 outliers extremos
- `category_shift.py` — distribuição categórica que muda
- `sparse_numeric_series.py` — muitos nulls intercalados
- `zero_inflated_series.py` — muitos zeros (ex: colunas monetárias)
- `regime_change_series.py` — mudança brusca de patamar (ex: migração de sistema)

**Exemplo de pedido:**
> "Implemente `compute_dynamic_band` e `score_proposal` com testes para séries estável, com drift e com outliers."

---

### 🎨 frontend

**Quando:** componentes Streamlit e Plotly

**Foco:**
- Streamlit multi-page app com `st.session_state`
- Gráficos Plotly interativos com bandas de confiança
- Formulários com validação
- UX de calibração (sliders → recalcula → atualiza gráfico)
- Carrinho de regras no session_state
- Preview de impacto ao alterar parâmetros (coverage/FP/score lado a lado)

**Output:** páginas Streamlit completas e funcionalidades

**Padrões Streamlit:**
- Use `st.session_state` para persistência entre reruns
- Use `st.cache_data(ttl=...)` para queries Athena
- Use `st.columns()` para layout
- Use `st.plotly_chart(fig, use_container_width=True)`
- Callbacks com `on_change` para interatividade

**Exemplo de pedido:**
> "Crie a página 02_explore.py com o gráfico de calibração para colunas numéricas, incluindo sliders para N e σ."

---

### 📝 gdq-syntax

**Quando:** gerar, validar ou debugar sintaxe GDQ

**Foco:**
- Sintaxe GDQ real (SEMPRE consultar `docs/gdq_syntax_reference.md` antes)
- Casing correto (coluna sem aspas, CamelCase em regras, lowercase em avg/std/last)
- Parênteses balanceados no dual guard
- Diferenças de formato por regra:
  - Mean/StdDev: K inteiro, buffer 0.01, margem como `avg * factor`
  - RowCount: K float (2.0), sem buffer, margem como `avg - (avg * pct)`
  - CustomSql: `from primary`, escala 0-100, aspas simples em valores
- Validação de output contra exemplos de produção
- Representação intermediária DualGuardSpec antes de renderizar string

**Output:** sintaxe GDQ validada + testes com exemplos reais

**Regra de ouro:** NUNCA gerar string GDQ diretamente — sempre passar pela representação intermediária e pelo renderer.

**Exemplo de pedido:**
> "Implemente o DualGuardRenderer que recebe DualGuardSpec e gera a string GDQ correta para Mean, StdDev e RowCount, com testes contra os exemplos de produção em gdq_syntax_reference.md."

---

### 🧪 integration-qa

**Quando:** validar fluxo end-to-end

**Foco:**
- Setup → análise → proposta → export
- Consistência da sintaxe GDQ gerada
- Smoke tests
- Validação de erros e edge cases

**Output:** checklists, testes de integração, scripts de validação

---

### 🎨 ux-ui (HOOK — planejamento + avaliação)

**Quando:** SEMPRE no início e final de cada sprint

**Foco:**
- Redução de fricção em cada interação do usuário
- Visibilidade do estado do sistema (config ativa, carrinho, progresso)
- Consistência visual e de navegação entre páginas
- Padrões Streamlit: layout, componentes, session_state, responsividade
- Checklist completa: navegação, informação, interação, consistência, performance

**Spec completa:** `docs/agents/ux_ui_agent.md`

**Output:** Avaliação com achados classificados: `[BLOQUEANTE]`, `[MELHORIA]`, `[SUGESTÃO]`

---

### 📓 tech-writer-user (HOOK — planejamento + avaliação)

**Quando:** SEMPRE no início e final de cada sprint

**Foco:**
- Documentação contextual no app Streamlit (help texts, tooltips, captions)
- Linguagem clara para analista/engenheiro de dados (não dev)
- Progressive disclosure: label → help → caption → expander
- Consistência de termos entre páginas
- Mensagens de erro acionáveis (dizem o que fazer)

**Spec completa:** `docs/agents/tech_writer_user_agent.md`

**Output:** Avaliação com achados classificados: `[TEXTO_FALTANDO]`, `[TEXTO_CONFUSO]`, `[TEXTO_INCONSISTENTE]`

---

### 📄 tech-writer-code (HOOK — planejamento + avaliação)

**Quando:** SEMPRE no início e final de cada sprint

**Foco:**
- Docstrings Google Style para funções/classes públicas
- Docstrings de módulo (propósito, dependências, referência à spec)
- ADRs para decisões de design não óbvias (`docs/adr/`)
- Documentação de templates SQL (parâmetros, output, notas)
- Sincronização docs ↔ código

**Spec completa:** `docs/agents/tech_writer_code_agent.md`

**Output:** Avaliação com achados classificados: `[DOCSTRING_FALTANDO]`, `[DOCSTRING_DESATUALIZADA]`, `[ADR_NECESSÁRIO]`

---

## Convenções de Código

### Python

```python
# Type hints obrigatórios
def compute_band(values: list[float], n: int) -> dict[str, float]:
    ...

# Dataclasses para modelos (não dicts soltos)
@dataclass
class RuleProposal:
    ...

# Docstrings para funções públicas
def score_proposal(proposal: RuleProposal) -> RuleScore:
    """Avalia qualidade da regra proposta.

    Args:
        proposal: Proposta com thresholds e histórico.

    Returns:
        Score com coverage, confidence e warnings.

    Raises:
        ValueError: Se histórico tem menos de 3 pontos.
    """
    ...
```

### SQL Templates (Jinja2)

```sql
-- queries/templates/numeric_history.sql
-- Parâmetros: schema, table, col, date_col, date_expression, lookback_value, base_filter
SELECT
  {{ date_expression or '"' ~ date_col ~ '"' }} as processing_period,
  COUNT(*) as total_count,
  COUNT("{{ col }}") as non_null_count,
  AVG(CAST("{{ col }}" AS DOUBLE)) as col_mean,
  STDDEV(CAST("{{ col }}" AS DOUBLE)) as col_stddev,
  MIN(CAST("{{ col }}" AS DOUBLE)) as col_min,
  MAX(CAST("{{ col }}" AS DOUBLE)) as col_max,
  APPROX_PERCENTILE(CAST("{{ col }}" AS DOUBLE),
    ARRAY[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]) as col_percentiles
FROM "{{ schema }}"."{{ table }}"
WHERE {{ date_expression or '"' ~ date_col ~ '"' }} >= DATE_ADD('day', -{{ lookback_value }}, CURRENT_DATE)
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
GROUP BY {{ date_expression or '"' ~ date_col ~ '"' }}
ORDER BY processing_period
```

### Nomes de arquivos

- snake_case para todos os arquivos Python
- Templates SQL: `<propósito>_<contexto>.sql` (ex: `numeric_history.sql`)
- Testes: `test_<módulo>.py`

---

## Dependências

```
# requirements.txt
streamlit>=1.30
plotly>=5.18
pyathena>=3.0
boto3>=1.34
pandas>=2.1
numpy>=1.26
jinja2>=3.1
duckdb>=1.0       # mock Athena local (desenvolvimento)
pyarrow>=14.0     # leitura de parquet
pytest>=8.0
```

---

## Workflow de Desenvolvimento

### Sprint 0 — Setup de Ambiente (manual + Claude Code)

Guia completo: `docs/sprint0_setup_guide.md`

```
1. Setup Windows: Python 3.11+, Node.js, Claude Code, venv
2. Criar estrutura de pastas
3. config.py multi-ambiente (local/dev/prod)
4. infra/sql_dialect.py (adaptação Athena↔DuckDB)
5. infra/mock_athena.py (DuckDB como backend local)
6. infra/athena_client.py (unificado: mock + real)
7. infra/query_logger.py
8. scripts/generate_mock_data.py (dados sintéticos)
9. scripts/validate_setup.py
10. app.py mínimo (smoke test)
```

Critério de sucesso: `validate_setup.py` passa, DuckDB executa queries mock,
Streamlit abre sem erro.

### Sprint A1 — Fundação técnica mínima

```
1. infra/query_safety.py + tests
2. infra/athena_client.py (wrapper com retry/timeout/cache)
3. infra/query_builder.py + queries/templates/metadata_discovery.sql
4. core/models/ (todos os dataclasses incluindo DualGuardSpec)
5. services/dataset_service.py + template SQL
6. core/column_classifier.py + tests
7. services/profiling_service.py + template SQL
8. pages/01_setup.py (UI wizard com validação progressiva)
```

Critério de sucesso: valida tabela, lista colunas, classifica, salva preset.

### Sprint A2 — Numéricas + Backtest + Score + Export

```
9.  queries/templates/numeric_history.sql
10. core/statistical_engine.py + tests (com 8 fixtures)
11. core/backtest.py + tests
12. core/rule_scoring.py + tests (score composto)
13. services/analysis_service.py (numéricas)
14. services/proposal_service.py (numéricas)
15. core/gdq_renderer.py + tests (DualGuardSpec → string GDQ)
16. core/gdq_rule_generator.py + tests (Mean/StdDev dual guard)
17. pages/02_explore.py (calibração numérica + preview de impacto)
18. services/export_service.py (básico: copiar + .txt)
19. pages/03_review.py (carrinho + export básico)
```

Critério de sucesso: calibra e exporta regras Mean/StdDev válidas com score.

### Sprint B1 — RowCount + Plugin

```
20. strategies/row_count_strategy.py (Protocol + GenericBand)
21. RowCount dual guard no gdq_renderer.py + tests
22. Integração no explore/review
```

### Sprint B2 — Categóricas MVP

```
23. queries/templates/categorical_*.sql
24. Classificação low/mid/high no profiling
25. ColumnValues, DistinctValuesCount, Completeness, CustomSql (estático)
26. IsPrimaryKey
27. Integração no explore/review
```

### Sprint C1 — Review + Validação de Sintaxe

```
28. validate_syntax() no export_service
29. Relatório analítico markdown
30. Carrinho com evidência + racional por regra
```

### Sprint C2 — CustomSql Dinâmico

```
31. category_frequency_dynamic() + modo híbrido (floor/ceiling)
32. Toggle estático/dinâmico/híbrido na UI
33. Backtest adaptado para dinâmica
```

### Sprint D — Polish + IA

```
34. Cache TTL por tipo + cost guardrails + logging estruturado
35. Presets reutilizáveis (por família de tabela)
36. AI provider protocol + adapters + insights panel
```

### Padrão de execução por fatia

```
1. architect   → define contrato/interface
2. athena-sql  → cria template SQL
3. stats-engine / gdq-syntax → implementa lógica core
4. frontend    → pluga no fluxo Streamlit
5. integration-qa → testa e2e
```

### Hooks obrigatórios por sprint

Os hooks abaixo DEVEM ser acionados automaticamente nos momentos indicados.

#### HOOK: Início de sprint (planejamento)

Ao iniciar qualquer sprint, ANTES de escrever código, rodar **6 agentes** em paralelo:

**Grupo técnico:**
```
[architect]       → Revisar contratos/interfaces das fatias, validar dependências, identificar trade-offs
[athena-sql]      → Revisar templates SQL necessários, planejar compatibilidade Athena↔DuckDB, estimar custo
[stats-engine]    → Revisar abordagem estatística, identificar edge cases, planejar fixtures necessárias
```

**Grupo qualidade:**
```
[ux-ui]           → Revisar fatias planejadas, propor wireframes textuais, definir fluxo do usuário
[tech-writer-user]→ Identificar novos conceitos, rascunhar textos de help/caption/info
[tech-writer-code]→ Rascunhar docstrings para novas interfaces, verificar se ADRs são necessários
```

O output dos 6 agentes DEVE ser considerado antes de começar a implementação.
Se qualquer agente identificar `[BLOQUEANTE]`, a implementação NÃO deve prosseguir até resolver.

#### HOOK: Final de sprint (avaliação)

Ao finalizar qualquer sprint, DEPOIS de código pronto e testes unitários passando, executar **3 etapas sequenciais**:

**Etapa 1 — Teste com Athena real (obrigatório):**

```
[integration-qa]  → Executar fluxo completo contra Athena real (não mock)
```

- Usar tabela `gdq_test_db.tb_operacoes_incremental` (ou tabela relevante ao sprint)
- Configurar `AWS_PROFILE=gdq-test` e `GDQ_ATHENA_MODE=real`
- Validar: queries executam sem erro, dados retornados fazem sentido, regras GDQ geradas são válidas
- Comparar resultados Athena vs DuckDB mock para detectar divergências de dialeto
- Documentar: número de períodos, coverage, regras geradas, qualquer diferença vs mock
- Se houver divergência Athena↔DuckDB: é `[BLOQUEANTE]`, deve ser corrigida antes de prosseguir

**Etapa 2 — Avaliação técnica (em paralelo):**

```
[architect]       → Revisar código implementado: contratos respeitados, sem acoplamento indevido, extensibilidade
[athena-sql]      → Validar templates SQL: compatibilidade Athena↔DuckDB, uso de partições, custo
[stats-engine]    → Validar lógica estatística: edge cases cobertos, fixtures adequadas, robustez numérica
```

**Etapa 3 — Avaliação de qualidade (em paralelo):**

```
[ux-ui]           → Checklist UX completa, testar fluxo do usuário, listar achados
[tech-writer-user]→ Verificar textos em todas as páginas modificadas, executar checklist
[tech-writer-code]→ Verificar docstrings, sincronização docs↔código, executar checklist
```

#### Critérios de aprovação

Cada agente DEVE:
- Ser **crítico e específico** — apontar arquivos e linhas de código
- Classificar achados por severidade
- Propor solução concreta para cada achado
- Dar status final: APROVADO / APROVADO COM RESSALVAS / REPROVADO

O sprint só está completo quando:
1. Testes unitários passam (`pytest tests/ -v`)
2. Teste com Athena real passa sem divergências
3. Todos os 6 agentes de avaliação aprovam (com ou sem ressalvas)

Achados `[BLOQUEANTE]` devem ser resolvidos antes de fechar o sprint.
Achados `[MELHORIA]` e `[SUGESTÃO]` podem ser diferidos para sprints futuros.

### Como pedir tarefas

**Bom (fatia clara com contrato):**
> "Implemente `core/column_classifier.py` seguindo o contrato em `docs/technical_spec_v1.md` seção 7. Inclua testes para: coluna int (→ NUMERIC), coluna string com 95% castável (→ NUMERIC), coluna string com 20 valores distintos (→ CAT_LOW), coluna string com 300 distintos (→ CAT_MID), coluna string com 10k distintos (→ CAT_HIGH)."

**Ruim (escopo vago):**
> "Faz a parte de classificação de colunas"

---

## Referência Rápida: Modelos

| Modelo | Arquivo | Uso |
|--------|---------|-----|
| `DatasetConfig` | `core/models/dataset_config.py` | Config da tabela alvo |
| `ColumnProfile` | `core/models/column_profile.py` | Resultado da classificação |
| `BaselineStrategy` | `core/models/baseline.py` | Como calcular baseline |
| `DualGuardSpec` | `core/models/dual_guard.py` | Representação intermediária do dual guard |
| `RuleProposal` | `core/models/rule_proposal.py` | Proposta com evidência |
| `RuleSelection` | `core/models/rule_selection.py` | Regra no carrinho |
| `BacktestSummary` | `core/models/rule_proposal.py` | Resultado do backtest |
| `RuleScore` | `core/rule_scoring.py` | Avaliação composta da regra |
| `SemanticType` | `core/models/enums.py` | Tipos de coluna |
| `RuleType` | `core/models/enums.py` | Tipos de regra |

---

## Referência Rápida: Sintaxe GDQ

> **Referência completa:** `docs/gdq_syntax_reference.md`

**REGRAS CRÍTICAS DE SINTAXE:**
- Nomes de coluna **SEM aspas**: `Mean VLR_SALDO` (não `Mean "VLR_SALDO"`)
- Nomes de regra em **CamelCase**: `Mean`, `StandardDeviation`, `RowCount`, `CustomSql`
- Funções dinâmicas em **lowercase**: `avg(last(30))`, `std(last(30))`

### Regras Dinâmicas — Padrão "Dual Guard" (σ OR margem%)

```
# Mean (coluna numérica) — com buffer 0.01, K inteiro
(((Mean {COL} >= (avg(last({N})) - ({K} * std(last({N}))) - 0.01)) AND (Mean {COL} <= (avg(last({N})) + ({K} * std(last({N}))) + 0.01))) OR ((Mean {COL} >= (avg(last({N})) * 0.9) - 0.01) AND (Mean {COL} <= (avg(last({N})) * 1.1) + 0.01)))

# StandardDeviation (coluna numérica) — mesmo padrão do Mean
(((StandardDeviation {COL} >= (avg(last({N})) - ({K} * std(last({N}))) - 0.01)) AND (StandardDeviation {COL} <= (avg(last({N})) + ({K} * std(last({N}))) + 0.01))) OR ((StandardDeviation {COL} >= (avg(last({N})) * 0.9) - 0.01) AND (StandardDeviation {COL} <= (avg(last({N})) * 1.1) + 0.01)))

# RowCount (tabela) — SEM buffer, K como float (2.0), formato de margem diferente
(((RowCount >= (avg(last({N})) * 1.0 - ({K} * std(last({N}))))) AND (RowCount <= (avg(last({N})) * 1.0 + ({K} * std(last({N})))))) OR ((RowCount >= (avg(last({N})) - (avg(last({N})) * 0.1))) AND (RowCount <= (avg(last({N})) + (avg(last({N})) * 0.1)))))
```

### Regras Estáticas

```
# Frequência de categoria (CustomSql) — valores fixos, resultado em % (0-100)
CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between {LOWER} and {UPPER}

# Valores permitidos (numéricos sem aspas)
ColumnValues {COL} in [2, 1, 3]

# Distintos (exato)
DistinctValuesCount {COL} = 3

# Completude (usa >=, não between)
Completeness {COL} >= 1.00

# Chave primária (colunas separadas por espaço, não vírgula)
IsPrimaryKey COL1 COL2 COL3
```

---

## Configuração Local

```bash
# Clone e setup
git clone <repo>
cd gdq-proposer

# Instalar dependências
pip install -r requirements.txt

# Configurar AWS
export AWS_PROFILE=<your-profile>
# ou configurar em .env

# Rodar
streamlit run app.py

# Testes
pytest tests/ -v
```

---

## Notas Importantes

1. **Referência de sintaxe GDQ real:** `docs/gdq_syntax_reference.md` — SEMPRE consultar antes de gerar sintaxe
2. **Nomes de coluna sem aspas na sintaxe GDQ** — diferente do SQL Athena onde usamos aspas duplas
3. **CustomSql usa `from primary`** — keyword GDQ que referencia a tabela sendo avaliada
4. **Frequência em percentual 0-100** (não 0-1) nas regras CustomSql
5. **Todas as regras dinâmicas usam padrão dual guard (σ OR margem %)** — nunca gerar só uma parte
6. **Mean e StandardDeviation SÃO regras built-in do GDQ** — suportam `avg(last(N))` e `std(last(N))`
7. **CustomSql também suporta `avg(last(N))` no between** — regras categóricas podem ser dinâmicas (ver `docs/evolution_dynamic_sql_and_ai.md`)
8. **Athena retorna arrays de percentil como string** — parse necessário no `analysis_service`
9. **`APPROX_PERCENTILE` com array** retorna array na mesma ordem — mapear por índice
10. **Coluna de data pode ser string** — sempre usar `date_expression` do config para normalizar
11. **`COUNT(DISTINCT ...)` é caro** — usar apenas quando necessário, com limit de lookback
12. **Streamlit reruns inteiros** a cada interação — usar `st.session_state` para preservar estado
13. **Plotly `add_hrect`** é ideal para desenhar bandas de confiança no gráfico
14. **IA é aditiva, nunca bloqueante** — ferramenta funciona 100% sem IA; insights são opcionais
15. **AIProvider usa protocol** — facilita trocar entre Bedrock, StackSpot, Mock sem mudar lógica
16. **Partition method muda a lógica das queries:**
    - INCREMENTAL: GROUP BY partition_column → cada partição = 1 processamento
    - FULL_SNAPSHOT: GROUP BY partition_column, mas cada partição contém foto completa
    - Sempre usar `effective_temporal_axis` do DatasetConfig como eixo de GROUP BY
    - Sempre usar `effective_partition_filter` para partition pruning (reduz custo Athena)

## Documentação de Referência

| Documento | Localização | Conteúdo |
|-----------|-------------|----------|
| Spec Técnica v1 | `docs/technical_spec_v1.md` | Arquitetura, modelos, contratos, critérios de aceite |
| Referência de Sintaxe GDQ | `docs/gdq_syntax_reference.md` | Sintaxe exata de cada regra, com exemplos de produção |
| Evolução: CustomSql + IA | `docs/evolution_dynamic_sql_and_ai.md` | CustomSql dinâmico, integração IA, roadmap pós-MVP |
| Setup de Ambiente | `docs/sprint0_setup_guide.md` | Windows + Claude Code + mock Athena + multi-ambiente |
| Setup AWS Teste | `docs/aws_test_setup.md` | IAM readonly + tabelas fake S3/Glue/Athena |
| Playbook Claude Code | `docs/playbook_claude_code.md` | Etapas sequenciais para Claude Code executar |
| Agente UX/UI | `docs/agents/ux_ui_agent.md` | Princípios, padrões Streamlit, checklist de avaliação |
| Agente Tech Writer (User) | `docs/agents/tech_writer_user_agent.md` | Documentação in-app, progressive disclosure, checklist |
| Agente Tech Writer (Code) | `docs/agents/tech_writer_code_agent.md` | Docstrings, ADRs, documentação de módulo, checklist |
