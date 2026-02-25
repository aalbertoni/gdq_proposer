# Referencia de Modulos — GDQ Rule Proposer

Indice rapido de todos os modulos do projeto, organizados por camada.
Para cada modulo: caminho, proposito, classes/funcoes publicas,
dependencias e arquivo de teste.

---

## Configuracao

### config.py

- **Proposito:** Configuracao multi-ambiente (local/dev/prod) carregada de variaveis de ambiente e .env files.
- **Classes e funcoes publicas:**
    - `Environment` — Enum: LOCAL, DEV, PROD
    - `AthenaMode` — Enum: MOCK, REAL
    - `AthenaConfig` — Dataclass com parametros de conexao Athena (mode, region, workgroup, s3_output, aws_profile, mock_data_dir, timeouts, cache TTLs)
    - `AppConfig` — Dataclass raiz com environment, athena config, log_dir, preset_dir
    - `load_config()` — Carrega config do ambiente com hierarquia: env vars > .env file > defaults
- **Dependencias:** `os`, `dataclasses`, `enum`, `pathlib`
- **Testes:** Sem arquivo de teste dedicado (coberto por testes de integracao)

---

## Camada de Dominio (core/)

### core/statistical_engine.py

- **Proposito:** Motor estatistico com funcoes puras para calculo de bandas dinamicas, margem percentual, percentis, frequencia, bandas rolantes e deteccao de drift. Sem I/O, sem Athena, sem UI.
- **Funcoes publicas:**
    - `compute_dynamic_band(values, n_periods, n_sigma)` — Banda sigma: avg +/- K*std. Retorna dict com lower, upper, center, std, n_sigma, n_periods_used.
    - `compute_margin_band(values, n_periods, margin_pct)` — Banda margem: avg * (1 +/- margin). Retorna dict com lower, upper, center, margin_pct, n_periods_used.
    - `compute_percentile_band(p_lower_series, p_upper_series, n_periods)` — Banda baseada em percentis historicos (ex: P05/P95).
    - `compute_frequency_band(pct_series, n_periods, margin_pct)` — Banda para frequencia percentual de categorias (0-100).
    - `compute_rolling_bands(values, n_periods, n_sigma, margin_pct, min_history)` — Bandas rolantes sigma e margem para cada ponto da serie. Retorna listas alinhadas.
    - `detect_drift(values, window)` — Detecta tendencia linear via regressao simples. Retorna has_drift, slope, r_squared.
- **Dependencias:** `math`, `typing`
- **Testes:** `tests/test_statistical_engine.py`

### core/backtest.py

- **Proposito:** Simulacao historica da regra dual guard com janela rolante. Para cada ponto, calcula banda a partir dos valores anteriores e verifica pass/fail com logica OR (sigma OR margem).
- **Funcoes publicas:**
    - `backtest_band(values, dates, n_periods, n_sigma, margin_pct, min_history)` — Executa backtest completo. Retorna `BacktestSummary` com total_periods, periods_pass, periods_fail, coverage_pct, false_positive_proxy, band_width_ratio, stability_score, has_drift, outlier_periods.
- **Dependencias:** `math`, `core.models.rule_proposal.BacktestSummary`, `core.statistical_engine`
- **Testes:** `tests/test_backtest.py`

### core/rule_scoring.py

- **Proposito:** Score composto que avalia qualidade de uma proposta de regra baseado em backtest, tipo de regra e historico.
- **Classes e funcoes publicas:**
    - `RuleScore` — Dataclass com coverage (0-1), stability (0-1), interpretability (0-1), cost_efficiency (0-1), false_positive_count, sensitivity, score_total, confidence (HIGH/MEDIUM/LOW), recommendation, warnings.
    - `score_proposal(proposal, history_values)` — Avalia proposta e retorna RuleScore.
    - Constantes de peso: `WEIGHT_COVERAGE=0.35`, `WEIGHT_STABILITY=0.25`, `WEIGHT_INTERPRETABILITY=0.20`, `WEIGHT_COST_EFFICIENCY=0.20`
- **Dependencias:** `dataclasses`, `core.models.enums`, `core.models.rule_proposal`, `core.statistical_engine`
- **Testes:** `tests/test_rule_scoring.py`

### core/gdq_renderer.py

- **Proposito:** Renderiza `DualGuardSpec` como string GDQ valida. Aplica `FormattingProfile` para diferenciar formato entre Mean/StdDev e RowCount. Nunca gerar string GDQ sem passar por este renderer.
- **Classes publicas:**
    - `DualGuardRenderer` — Classe com metodo `render(spec: DualGuardSpec) -> str` que gera string GDQ formatada para producao.
- **Dependencias:** `core.models.dual_guard`, `core.models.enums`
- **Testes:** `tests/test_gdq_renderer.py`

### core/gdq_rule_generator.py

- **Proposito:** Gerador de alto nivel que recebe `RuleProposal` + overrides opcionais e delega ao renderer ou gera strings simples para regras nao-dual-guard.
- **Classes publicas:**
    - `GDQRuleGenerator` — Metodo `generate(proposal, overrides)` que despacha por tipo de regra: dual guard (Mean/StdDev/RowCount), Completeness, AllowedValues, DistinctCount, IsPrimaryKey.
- **Dependencias:** `core.gdq_renderer`, `core.models.dual_guard`, `core.models.enums`, `core.models.rule_proposal`, `core.models.rule_selection`
- **Testes:** `tests/test_gdq_rule_generator.py`

### core/rule_explainer.py

- **Proposito:** Gera explicacoes em linguagem natural (pt-BR) para regras GDQ, tornando-as comprehensiveis para analistas e engenheiros de dados sem conhecimento de sintaxe GDQ.
- **Funcoes publicas:**
    - `explain_rule(proposal)` — Explicacao curta em linguagem natural.
    - `explain_rule_detail(proposal)` — Explicacao detalhada incluindo parametros e evidencia do backtest.
- **Dependencias:** `core.models.enums`, `core.models.rule_proposal`
- **Testes:** `tests/test_rule_explainer.py`

### core/column_classifier.py

- **Proposito:** Classificacao semantica de colunas em 3 camadas: tipo fisico Athena, heuristica de conteudo e cardinalidade.
- **Funcoes publicas:**
    - `classify_column(athena_type, distinct_count, total_count, non_null_count, numeric_cast_count)` — Retorna `SemanticType` inferido.
- **Constantes publicas:**
    - `NUMERIC_CAST_THRESHOLD = 0.95` — Limiar de castabilidade para considerar string como numerica
    - `LOW_CARDINALITY_MAX_DISTINCT = 50` — Maximo de distintos para low cardinality
    - `MID_CARDINALITY_MAX_DISTINCT = 500` — Maximo de distintos para mid cardinality
    - `ATHENA_NUMERIC_TYPES` — Set de tipos numericos Athena reconhecidos
    - `ATHENA_DATE_TYPES` — Set de tipos de data Athena reconhecidos
- **Dependencias:** `core.models.enums`
- **Testes:** `tests/test_column_classifier.py`

---

## Modelos (core/models/)

### core/models/enums.py

- **Proposito:** Enums compartilhados do dominio que definem vocabulario de tipos, regras, niveis de confianca e modos de operacao.
- **Enums publicos:**
    - `LookbackMode` — LAST_N_PERIODS, LAST_X_DAYS
    - `GrainType` — DAILY, MONTHLY, TIMESTAMP, CUSTOM
    - `PartitionMethod` — INCREMENTAL, FULL_SNAPSHOT, NON_PARTITIONED
    - `SemanticType` — NUMERIC, CATEGORICAL_LOW/MID/HIGH, DATETIME, IDENTIFIER, FREE_TEXT, UNKNOWN
    - `RuleType` — MEAN_DUAL_GUARD, STDDEV_DUAL_GUARD, ROW_COUNT_DUAL_GUARD, COMPLETENESS, ALLOWED_VALUES, CATEGORY_FREQUENCY_STATIC/DYNAMIC/HYBRID, DISTINCT_COUNT_EXACT/RANGE, IS_PRIMARY_KEY, CUSTOM_SQL, NUMERIC_PERCENTILE_BAND
    - `ConfidenceLevel` — HIGH, MEDIUM, LOW
    - `MetricRef` — MEAN, STANDARD_DEVIATION, ROW_COUNT, CUSTOM_SQL
    - `BaselineMethod` — LAST_N_PERIODS, LAST_X_DAYS, ROLLING_WINDOW_EXCLUDE_CURRENT, SAME_WEEKDAY, SAME_DAY_OF_MONTH
    - `ExportOutputMode` — GDQ_RUNTIME, ANALYTICAL
- **Dependencias:** `enum`
- **Testes:** `tests/test_models.py`

### core/models/dataset_config.py

- **Proposito:** Configuracao da tabela alvo para analise, encapsulando schema, tabela, particao, eixo temporal, lookback e filtros.
- **Classes publicas:**
    - `DatasetConfig` — Dataclass com properties `effective_temporal_axis` (resolve coluna temporal baseado no metodo de particao) e `effective_partition_filter` (gera WHERE para partition pruning).
- **Dependencias:** `dataclasses`, `typing`, `core.models.enums`
- **Testes:** `tests/test_dataset_config.py`

### core/models/column_profile.py

- **Proposito:** Perfil de uma coluna apos classificacao, com tipo fisico, tipo semantico inferido, metricas de profiling e override manual.
- **Classes publicas:**
    - `ColumnProfile` — Dataclass com properties `effective_type` (override > inferido), `is_numeric`, `is_categorical`.
- **Dependencias:** `dataclasses`, `typing`, `core.models.enums`
- **Testes:** `tests/test_models.py`

### core/models/dual_guard.py

- **Proposito:** Representacao intermediaria do padrao dual guard. Nunca gerar string GDQ diretamente — sempre montar DualGuardSpec e passar pelo renderer.
- **Classes publicas:**
    - `FormattingProfile` — Diferencas de formatacao por tipo de regra (k_as_float, include_buffer, avg_multiply_one, margin_format).
    - `DualGuardSpec` — Especificacao com metric, target, n_periods, n_sigma, margin_pct, buffer, profile. `__post_init__` infere profile automaticamente baseado na metrica.
- **Constantes publicas:**
    - `MEAN_PROFILE` — Profile default para Mean/StdDev
    - `STDDEV_PROFILE` — Profile default para StdDev (identico a Mean)
    - `ROWCOUNT_PROFILE` — Profile para RowCount (K float, sem buffer, avg*1.0, margem delta)
- **Dependencias:** `dataclasses`, `core.models.enums`
- **Testes:** `tests/test_models.py`, `tests/test_gdq_renderer.py`

### core/models/rule_proposal.py

- **Proposito:** Proposta de regra com evidencia completa (thresholds, backtest, confianca, historico para graficos).
- **Classes publicas:**
    - `BacktestSummary` — Resultado do backtest: total_periods, periods_pass/fail, coverage_pct, false_positive_proxy, band_width_ratio, stability_score, has_drift, outlier_periods.
    - `RuleProposal` — Proposta completa com id, target, rule_type, thresholds sugeridos, parametros de baseline, backtest, confianca, warnings, preview GDQ e historico.
- **Dependencias:** `dataclasses`, `typing`, `core.models.enums`
- **Testes:** `tests/test_models.py`, `tests/test_proposal_service.py`

### core/models/rule_selection.py

- **Proposito:** Regra selecionada pelo usuario para o carrinho de exportacao, com overrides opcionais.
- **Classes publicas:**
    - `UserOverride` — Ajustes manuais: custom_lower, custom_upper, custom_values, custom_n_periods, custom_n_sigma, custom_margin_pct, notes.
    - `RuleSelection` — Referencia a proposal com enabled, user_overrides e final_gdq_syntax.
- **Dependencias:** `dataclasses`, `typing`, `core.models.rule_proposal`
- **Testes:** `tests/test_models.py`, `tests/test_export_service.py`

### core/models/baseline.py

- **Proposito:** Estrategia de baseline para calculo de thresholds. Configura janela, sigma, margem e minimos.
- **Classes publicas:**
    - `BaselineStrategy` — Dataclass com method, n_periods (default 20), n_sigma (default 2.0), margin_pct (default 0.10), percentile_lower/upper, min_history_points (default 7).
- **Dependencias:** `dataclasses`, `core.models.enums`
- **Testes:** `tests/test_models.py`

---

## Camada de Servicos (services/)

### services/dataset_service.py

- **Proposito:** Metadata discovery — validacao de tabela, descoberta de colunas, deteccao de particoes, range temporal e volume por periodo.
- **Classes publicas:**
    - `DatasetService` — Construtor recebe `AthenaClient` e `QueryBuilder`.
        - `validate_table(schema, table)` — Verifica existencia da tabela.
        - `get_columns(schema, table)` — Retorna lista de {name, type}.
        - `get_columns_with_partitions(schema, table)` — Retorna (columns, partition_columns).
        - `get_partitions(schema, table)` — Lista valores de particao.
        - `get_date_range(config)` — Min/max temporal e contagem de periodos.
        - `get_volume_by_period(config, limit)` — Row count por periodo.
- **Dependencias:** `core.models.dataset_config`, `infra.athena_client`, `infra.query_builder`, `infra.query_safety`
- **Testes:** `tests/test_dataset_service.py`

### services/profiling_service.py

- **Proposito:** Classificacao semantica de colunas via profiling SQL. Camada 1 classifica por tipo nativo sem query. Camada 2+3 executa query de amostragem para strings.
- **Classes publicas:**
    - `ProfilingService` — Construtor recebe `AthenaClient` e `QueryBuilder`.
        - `profile_columns(config, columns, sample_periods)` — Classifica todas as colunas e retorna lista de `ColumnProfile`.
        - `apply_user_overrides(profiles, overrides)` — Aplica overrides manuais de SemanticType.
- **Dependencias:** `core.column_classifier`, `core.models.column_profile`, `core.models.dataset_config`, `core.models.enums`, `infra.athena_client`, `infra.query_builder`, `infra.query_safety`
- **Testes:** `tests/test_profiling_service.py`

### services/analysis_service.py

- **Proposito:** Analise historica de colunas numericas e row count via SQL. Normaliza DataFrames e parseia arrays de percentis.
- **Classes publicas:**
    - `AnalysisService` — Construtor recebe `AthenaClient` e `QueryBuilder`.
        - `get_numeric_history(config, column)` — DataFrame com period, mean, stddev, min, max, p01..p99, non_null_count, null_count, total_count.
        - `get_row_count_history(config)` — DataFrame com period, row_count.
- **Dependencias:** `json`, `math`, `pandas`, `core.models.dataset_config`, `infra.athena_client`, `infra.query_builder`, `infra.query_safety`
- **Testes:** `tests/test_analysis_service.py`

### services/proposal_service.py

- **Proposito:** Orquestra statistical_engine + backtest + rule_scoring + gdq_rule_generator para gerar propostas completas com evidencia.
- **Classes publicas:**
    - `ProposalService` — Sem dependencias de infraestrutura no construtor.
        - `propose_numeric_rules(history, column, table, baseline)` — Gera Mean + StdDev + Completeness proposals.
        - `propose_table_rules(row_count_history, table, baseline, strategy)` — Gera RowCount proposals via Strategy.
        - `recalculate_proposal(proposal, new_baseline)` — Recalcula com novos parametros (para calibracao na UI).
- **Dependencias:** `uuid`, `pandas`, `core.backtest`, `core.gdq_rule_generator`, `core.models.baseline`, `core.models.enums`, `core.models.rule_proposal`, `core.models.rule_selection`, `core.rule_scoring`, `core.statistical_engine`
- **Testes:** `tests/test_proposal_service.py`

### services/export_service.py

- **Proposito:** Exportacao de regras GDQ selecionadas. Concatena sintaxe, valida parenteses e gera output final.
- **Classes publicas:**
    - `ExportResult` — Dataclass com rules_text, rules_count, warnings.
    - `ExportService` — Sem dependencias de infraestrutura.
        - `generate_syntax(selections)` — Concatena regras habilitadas com newline.
        - `validate_syntax(syntax)` — Validacao basica (parenteses, linhas vazias).
        - `export(selections, mode)` — Gera `ExportResult` completo.
- **Dependencias:** `dataclasses`, `core.models.enums`, `core.models.rule_selection`
- **Testes:** `tests/test_export_service.py`

---

## Camada de Infraestrutura (infra/)

### infra/athena_client.py

- **Proposito:** Client unificado que funciona com DuckDB (mock local) ou Athena real (dev/prod). Mesma interface independente do backend.
- **Classes publicas:**
    - `AthenaClient` — Construtor recebe `AppConfig` e `QueryLogger` opcional.
        - `execute_df(sql, query_name, dataset, column)` — Executa query e retorna DataFrame. Loga metricas automaticamente.
        - `execute(sql)` — Executa query e retorna lista de dicts.
        - `table_exists(schema, table)` — Verifica existencia de tabela.
        - `get_columns(schema, table)` — Retorna colunas sem info de particao.
        - `get_columns_with_partitions(schema, table)` — Retorna (columns, partition_columns).
    - Atributo `dialect` — `SQLDialect.DUCKDB` ou `SQLDialect.ATHENA` conforme o modo.
- **Dependencias:** `os`, `time`, `typing`, `pandas`, `config`, `infra.mock_athena`, `infra.query_logger`, `infra.sql_dialect`. Condicionalmente: `pyathena`, `boto3`.
- **Testes:** Coberto por testes de servicos e integracao

### infra/mock_athena.py

- **Proposito:** Backend DuckDB que simula Athena localmente. Carrega parquet/CSV como tabelas in-memory.
- **Classes publicas:**
    - `MockAthenaBackend` — Construtor aceita database (default `:memory:`).
        - `load_table(schema, table, data_path)` — Carrega arquivo como tabela DuckDB.
        - `execute(sql)` — Retorna lista de dicts.
        - `execute_df(sql)` — Retorna DataFrame.
        - `get_columns(table)` — Retorna [{name, type}] via information_schema.
        - `table_exists(table)` — Verifica existencia.
        - `close()` — Fecha conexao DuckDB.
- **Dependencias:** `duckdb`, `pandas`, `pathlib`
- **Testes:** Coberto indiretamente por todos os testes que usam mock

### infra/query_builder.py

- **Proposito:** Montagem de queries SQL a partir de templates Jinja2, com injecao de funcoes adaptadas ao dialeto.
- **Classes publicas:**
    - `QueryBuilder` — Construtor recebe `SQLDialect` e diretorio de templates.
        - `build_metadata_discovery(schema, table)` — Template `metadata_discovery.sql`
        - `build_date_range(schema, table, temporal_col, date_expression, base_filter)` — Template `date_range.sql`
        - `build_volume_by_period(schema, table, temporal_col, date_expression, base_filter, limit)` — Template `volume_by_period.sql`
        - `build_show_partitions(schema, table, partition_col)` — Template `show_partitions.sql`
        - `build_column_sample(schema, table, col, temporal_col, date_expression, sample_periods, base_filter)` — Template `column_sample.sql`
        - `build_row_count_history(schema, table, date_expression, lookback_value, base_filter)` — Template `row_count_history.sql`
        - `build_numeric_history(schema, table, col, date_expression, lookback_value, base_filter)` — Template `numeric_history.sql`
        - `resolve_date_expression(temporal_col, date_expression)` — Resolve expressao de data com TRY_CAST para DuckDB.
- **Dependencias:** `pathlib`, `jinja2`, `infra.sql_dialect`
- **Testes:** Coberto por testes de servicos

### infra/sql_dialect.py

- **Proposito:** Adaptador de funcoes SQL entre Athena (Presto/Trino) e DuckDB. Trata as poucas funcoes que diferem entre backends.
- **Classes e funcoes publicas:**
    - `SQLDialect` — Enum: ATHENA, DUCKDB
    - `DIALECT_FUNCTIONS` — Dicionario com templates para: APPROX_PERCENTILE, STDDEV, DATE_SUBTRACT_DAYS, TABLE_REF
    - `adapt_function(func_name, dialect, **kwargs)` — Retorna expressao SQL formatada para o dialeto.
- **Dependencias:** `enum`
- **Testes:** `tests/test_sql_dialect.py`

### infra/query_safety.py

- **Proposito:** Validacao de seguranca para queries SQL. Previne SQL injection via validacao de identificadores e sanitizacao de filtros.
- **Funcoes publicas:**
    - `validate_identifier(name)` — Valida nome de schema/tabela/coluna contra regex `^[a-zA-Z_][a-zA-Z0-9_]*$`.
    - `validate_lookback(value, mode)` — Garante lookback dentro dos limites (365 dias ou 100 periodos).
    - `sanitize_filter(sql_fragment)` — Bloqueia tokens perigosos (`;`, `--`, `/*`) e keywords destrutivas (DROP, DELETE, INSERT, etc).
- **Constantes publicas:**
    - `IDENTIFIER_PATTERN` — Regex compilada para identificadores validos
    - `MAX_LOOKBACK_DAYS = 365`
    - `MAX_LOOKBACK_PERIODS = 100`
- **Dependencias:** `re`, `enum`
- **Testes:** `tests/test_query_safety.py`

### infra/query_logger.py

- **Proposito:** Logging estruturado para queries. Cada query gera entrada com metricas para debug e otimizacao de custo.
- **Classes publicas:**
    - `QueryLogEntry` — Dataclass com query_name, dataset, column, elapsed_ms, cache_hit, rows_returned, bytes_scanned, exception_type, timestamp.
    - `QueryLogger` — Acumula entries e gera log.
        - `log_query(entry)` — Registra query executada.
        - `get_session_summary()` — Retorna metricas agregadas (total queries, tempo, cache hits, erros).
- **Dependencias:** `logging`, `dataclasses`, `datetime`, `typing`
- **Testes:** Coberto por testes de integracao

---

## Strategies (strategies/)

### strategies/row_count_strategy.py

- **Proposito:** Protocol extensivel para estrategias de geracao de regras RowCount. Permite plugins enterprise com logica customizada.
- **Classes publicas:**
    - `RowCountStrategy` — `@runtime_checkable Protocol` com metodos `propose(row_counts, dates, table, baseline)` e `recalculate(proposal, new_baseline)`.
    - `GenericBandRowCountStrategy` — Implementacao default com dual guard (sigma OR margem). Reutiliza toda a pipeline do core.
- **Dependencias:** `uuid`, `typing`, `core.backtest`, `core.gdq_rule_generator`, `core.models.baseline`, `core.models.enums`, `core.models.rule_proposal`, `core.models.rule_selection`, `core.rule_scoring`, `core.statistical_engine`
- **Testes:** `tests/test_row_count_strategy.py`

---

## Paginas Streamlit (pages/)

### app.py

- **Proposito:** Entry point Streamlit. Pagina inicial com status de conexao, tabelas disponiveis, preview de colunas e navegacao.
- **Funcoes publicas:**
    - `get_client()` — Cria ou recupera `AthenaClient` do `session_state`.
    - `get_available_tables(client)` — Lista tabelas do backend ativo.
    - `get_table_columns(client, table)` — Retorna colunas de uma tabela.
    - `render_sidebar()` — Renderiza sidebar com seletor de ambiente, modo ativo e config ativa.
    - `main()` — Ponto de entrada principal da pagina.
- **Dependencias:** `os`, `streamlit`, `config`, `infra.athena_client`

### pages/01_setup.py

- **Proposito:** Wizard de configuracao da tabela alvo. Validacao progressiva: tabela existe -> colunas listadas -> coluna temporal definida -> colunas classificadas -> config salva.
- **Dependencias:** `streamlit`, `config`, `infra.athena_client`, `infra.query_builder`, `services.dataset_service`, `services.profiling_service`, `core.models.dataset_config`, `core.models.enums`

### pages/02_explore.py

- **Proposito:** Pagina de exploracao e calibracao com abas "Numericas" e "Tabela". Graficos Plotly com bandas, sliders para ajuste de parametros e preview de impacto (score, coverage, FP).
- **Dependencias:** `streamlit`, `plotly`, `pandas`, `services.analysis_service`, `services.proposal_service`, `core.models.baseline`, `core.models.enums`, `core.rule_explainer`

### pages/03_review.py

- **Proposito:** Pagina de revisao do carrinho de regras e exportacao. Lista regras selecionadas, permite habilitar/desabilitar e exporta sintaxe GDQ como texto.
- **Dependencias:** `streamlit`, `services.export_service`, `core.models.rule_selection`, `core.gdq_rule_generator`

---

## Templates SQL (queries/templates/)

### metadata_discovery.sql

- **Proposito:** Obtem schema da tabela via `SELECT * LIMIT 0`
- **Parametros:** `table`, `table_ref`

### date_range.sql

- **Proposito:** MIN/MAX da coluna temporal e COUNT DISTINCT de periodos
- **Parametros:** `table_ref`, `temporal_col`, `date_expression`, `base_filter`

### volume_by_period.sql

- **Proposito:** Row count por periodo (ultimos N periodos, ordem DESC com LIMIT)
- **Parametros:** `table_ref`, `temporal_col`, `date_expression`, `base_filter`, `limit`

### show_partitions.sql

- **Proposito:** Lista valores distintos da coluna de particao
- **Parametros:** `table_ref`, `partition_col`

### column_sample.sql

- **Proposito:** Profiling de coluna: total, non_null, distinct, numeric_cast_count
- **Parametros:** `table_ref`, `col`, `temporal_col`, `date_expression`, `date_lookback_expr`, `base_filter`

### numeric_history.sql

- **Proposito:** Analise historica de coluna numerica: media, stddev, min, max, percentis por periodo
- **Parametros:** `col`, `date_expression`, `table_ref`, `stddev_func`, `approx_percentile_expr`, `date_lookback_expr`, `base_filter`

### row_count_history.sql

- **Proposito:** Row count por periodo para analise RowCount (com lookback, ordem ASC)
- **Parametros:** `table_ref`, `date_expression`, `date_lookback_expr`, `base_filter`

---

## Testes e Fixtures (tests/)

### Arquivos de teste

- `tests/test_statistical_engine.py` — Testes do motor estatistico com 8 tipos de serie
- `tests/test_backtest.py` — Testes do backtest com diferentes cenarios
- `tests/test_rule_scoring.py` — Testes do score composto
- `tests/test_gdq_renderer.py` — Testes do renderer contra exemplos de producao
- `tests/test_gdq_rule_generator.py` — Testes do gerador de alto nivel
- `tests/test_rule_explainer.py` — Testes das explicacoes em linguagem natural
- `tests/test_column_classifier.py` — Testes da classificacao semantica
- `tests/test_models.py` — Testes das dataclasses e enums
- `tests/test_dataset_config.py` — Testes do DatasetConfig e properties
- `tests/test_dataset_service.py` — Testes do servico de metadata
- `tests/test_profiling_service.py` — Testes do servico de profiling
- `tests/test_analysis_service.py` — Testes do servico de analise
- `tests/test_proposal_service.py` — Testes do servico de propostas
- `tests/test_export_service.py` — Testes do servico de exportacao
- `tests/test_row_count_strategy.py` — Testes da estrategia RowCount
- `tests/test_query_safety.py` — Testes de validacao de seguranca SQL
- `tests/test_sql_dialect.py` — Testes da adaptacao de dialeto

### Fixtures (tests/fixtures/)

- `stable_series.py` — Serie estavel sem anomalias
- `drift_series.py` — Serie com tendencia crescente
- `seasonal_series.py` — Variacao por dia da semana
- `outlier_series.py` — Serie com 2-3 outliers extremos
- `category_shift.py` — Distribuicao categorica que muda
- `sparse_numeric_series.py` — Muitos nulls intercalados
- `zero_inflated_series.py` — Muitos zeros (ex: colunas monetarias)
- `regime_change_series.py` — Mudanca brusca de patamar (ex: migracao de sistema)

---

## Scripts (scripts/)

- `scripts/generate_mock_data.py` — Gera dados sinteticos em parquet para mock_data/
- `scripts/validate_setup.py` — Valida ambiente de desenvolvimento (config, DuckDB, queries)
- `scripts/test_athena_integration.py` — Teste de integracao com Athena real
- `scripts/test_full_flow.py` — Teste do fluxo completo end-to-end
- `scripts/generate_aws_test_data.py` — Gera dados de teste para ambiente AWS
- `scripts/aws_setup.py` — Setup de recursos AWS para teste
- `scripts/test_aws_connection.py` — Testa conectividade AWS
