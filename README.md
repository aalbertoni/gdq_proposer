# GDQ Rule Proposer

Ferramenta Streamlit que analisa o historico de dados de uma tabela via AWS Athena e propoe regras de qualidade para [AWS Glue Data Quality (GDQ)](https://docs.aws.amazon.com/glue/latest/dg/data-quality.html).

## Contexto

O AWS Glue Data Quality permite definir regras declarativas para monitorar a qualidade dos dados em tabelas do Data Lake. Porem, criar essas regras manualmente e trabalhoso: exige analisar o historico da tabela, entender distribuicoes, calibrar thresholds e validar a sintaxe GDQ.

O GDQ Rule Proposer automatiza esse processo. Ele se conecta ao Athena, analisa o historico de cada coluna (media, desvio padrao, distribuicao, volume), propoe regras com bandas dinamicas calibradas por backtest, e exporta a sintaxe GDQ pronta para uso.

## Funcionalidades

- **Classificacao automatica** de colunas (numerico, categorico low/mid/high, identificador, data)
- **Regras com dual guard** — banda sigma OR banda margem, reduzindo falsos positivos
- **Calibracao interativa** com graficos de bandas em tempo real
- **Backtest historico** com metricas de cobertura, estabilidade e falsos positivos
- **Validacao de sintaxe GDQ** e checagem de consistencia entre regras
- **Relatorio analitico** exportavel em markdown com evidencia e racional por regra

## Regras suportadas

- **Mean / StandardDeviation** — dual guard dinamico com `avg(last(N))` e `std(last(N))`
- **RowCount** — volume de linhas com dual guard
- **Completeness** — porcentagem de valores nao-nulos
- **AllowedValues** — dominio fixo de valores permitidos
- **DistinctValuesCount** — contagem exata ou faixa de valores distintos
- **CategoryFrequency** — frequencia percentual via CustomSql
- **IsPrimaryKey** — validacao de chave primaria

## Arquitetura

```
app.py                  # Pagina inicial + sidebar
pages/
  01_setup.py           # Config da tabela + profiling
  02_explore.py         # Calibracao de regras + graficos
  03_review.py          # Carrinho + export + relatorio
  04_help.py            # Documentacao in-app

core/                   # Logica de negocio (sem I/O)
  statistical_engine.py # Bandas dinamicas, media movel
  backtest.py           # Avaliacao historica das regras
  rule_scoring.py       # Score composto (coverage, stability, etc.)
  gdq_renderer.py       # DualGuardSpec -> string GDQ
  gdq_rule_generator.py # Gerador de regras com dual guard
  column_classifier.py  # Classificacao semantica de colunas
  rule_explainer.py     # Explicacoes em linguagem natural
  models/               # Dataclasses do dominio

services/               # Orquestracao (com I/O)
  dataset_service.py    # Metadados da tabela
  profiling_service.py  # Classificacao de colunas
  analysis_service.py   # Queries de historico
  proposal_service.py   # Geracao de propostas
  export_service.py     # Validacao + export + relatorio

infra/                  # Infraestrutura
  athena_client.py      # Cliente unificado (mock + real)
  mock_athena.py        # Backend DuckDB para dev local
  query_builder.py      # Templates Jinja2
  sql_dialect.py        # Adaptacao Athena <-> DuckDB
  query_safety.py       # Sanitizacao de identificadores

strategies/             # Plugins extensiveis
  row_count_strategy.py # Protocol + implementacao generica
```

## Setup local

### Requisitos

- Python 3.11+
- Git

### Instalacao

```bash
git clone https://github.com/aalbertoni/gdq_proposer.git
cd gdq_proposer
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### Rodar com dados mock (sem AWS)

O modo local usa DuckDB com dados sinteticos — nao precisa de conta AWS.

```bash
# Gerar dados mock (se necessario)
python scripts/generate_mock_data.py

# Iniciar o app
streamlit run app.py
```

### Rodar com Athena real

Para conectar ao Athena, configure um arquivo `.env.dev`:

```
GDQ_ENV=dev
GDQ_ATHENA_REGION=us-east-1
GDQ_ATHENA_WORKGROUP=primary
GDQ_ATHENA_S3_OUTPUT=s3://seu-bucket/athena-results/
GDQ_AWS_PROFILE=seu-profile
```

```bash
GDQ_ENV=dev streamlit run app.py
```

A configuracao tambem pode ser feita pela UI do app em Setup > Configuracao de Ambiente.

### Variaveis de ambiente

- **GDQ_ENV** — `local` (default), `dev` ou `prod`
- **GDQ_ATHENA_REGION** — Regiao AWS (default: `us-east-1`)
- **GDQ_ATHENA_WORKGROUP** — Workgroup do Athena (default: `primary`)
- **GDQ_ATHENA_S3_OUTPUT** — Bucket S3 para resultados
- **GDQ_AWS_PROFILE** — Named profile do AWS CLI
- **GDQ_MOCK_DATA_DIR** — Diretorio de dados mock (default: `mock_data`)

## Testes

```bash
pytest tests/ -v
```

## Documentacao

- `docs/technical_spec_v1.md` — Especificacao tecnica completa
- `docs/gdq_syntax_reference.md` — Referencia de sintaxe GDQ com exemplos reais
- `docs/sprint0_setup_guide.md` — Guia de setup do ambiente
- `docs/evolution_dynamic_sql_and_ai.md` — Roadmap: CustomSql dinamico + IA
