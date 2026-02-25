# ADR-003: DuckDB como Backend Mock Local

- **Status:** Aceito
- **Data:** 2026-01-10
- **Decisores:** Equipe GDQ Rule Proposer

---

## Contexto

O GDQ Rule Proposer executa queries SQL contra o Amazon Athena
(Presto/Trino) para analisar historico de dados. Durante o
desenvolvimento, precisamos:

- Iterar rapidamente sem depender de conectividade AWS
- Executar testes unitarios e de integracao sem custo Athena
- Rodar CI/CD pipelines sem credenciais AWS
- Demonstrar a ferramenta sem infraestrutura cloud

O Athena cobra por volume de dados escaneados (US$ 5/TB). Executar
dezenas de queries de desenvolvimento por dia pode gerar custos
significativos, especialmente com tabelas grandes.

Precisamos de um backend local que execute o mesmo SQL (ou muito
proximo) do Athena, com dados sinteticos.

---

## Decisao

Usar **DuckDB** como backend mock local, com um modulo de adaptacao
de dialeto (`infra/sql_dialect.py`) para as poucas diferencas de
sintaxe entre Athena (Presto/Trino) e DuckDB.

### Componentes

- **`infra/mock_athena.py`** — `MockAthenaBackend` que encapsula DuckDB.
  Carrega parquet/CSV como tabelas in-memory.
- **`infra/sql_dialect.py`** — Enum `SQLDialect` (ATHENA/DUCKDB) e
  dicionario `DIALECT_FUNCTIONS` com templates para as funcoes que diferem.
- **`infra/athena_client.py`** — `AthenaClient` unificado que detecta
  o modo (MOCK/REAL) e roteia para o backend correto.
- **`infra/query_builder.py`** — `QueryBuilder` que injeta funcoes
  adaptadas ao dialeto nos templates Jinja2.

### Funcoes adaptadas

- `APPROX_PERCENTILE(col, ARRAY[...])` -> `QUANTILE_CONT(col, [...])`
- `STDDEV(expr)` -> `STDDEV_SAMP(expr)`
- `DATE_ADD('day', -N, CURRENT_DATE)` -> `CURRENT_DATE - INTERVAL 'N' DAY`
- `"schema"."table"` -> `"table"` (DuckDB nao usa schema separado)

### Dados sinteticos

Diretorio `mock_data/` contem arquivos parquet com dados sinteticos
gerados por `scripts/generate_mock_data.py`. Os dados simulam:
- 45+ periodos diarios
- Colunas numericas com diferentes distribuicoes
- Colunas categoricas com diferentes cardinalidades
- Colunas de data como VARCHAR (simula formato Athena)

---

## Alternativas Consideradas

### 1. SQLite

- **Pros:** Mais popular, zero dependencias
- **Contras:** SQL muito diferente do Presto/Trino. Nao suporta
  `APPROX_PERCENTILE`, arrays, `TRY_CAST`, nem muitas funcoes
  analiticas. Seria necessario reescrever quase todas as queries.

### 2. Presto/Trino local (Docker)

- **Pros:** SQL identico ao Athena, sem adaptacao
- **Contras:** Pesado (JVM, 2GB+ RAM), lento para iniciar, complexo
  de configurar catalogo Hive. Nao e viavel para CI rapido ou para
  desenvolvedores com maquinas Windows sem Docker nativo.

### 3. LocalStack (Athena mock)

- **Pros:** Simula servicos AWS completos
- **Contras:** Athena no LocalStack tem suporte limitado. Precisa
  de Docker. Ainda cobra (versao Pro) ou tem funcionalidade incompleta.

### 4. Mocks em Python puro (DataFrames)

- **Pros:** Total controle, sem dependencias
- **Contras:** Nao executa SQL real. Testes nao validam queries SQL.
  Qualquer erro de sintaxe SQL so seria detectado em producao.

### 5. Apache DataFusion

- **Pros:** Motor SQL rapido, API Python via datafusion
- **Contras:** Ecossistema menor, menos funcoes agregadas, menos
  suporte da comunidade. DuckDB e mais maduro e tem melhor
  compatibilidade com Presto.

---

## Consequencias

### Positivas

- **Desenvolvimento rapido:** DuckDB e in-process, inicia em milissegundos,
  nao precisa de servidor. Um `pytest` completo roda em < 5 segundos.
- **SQL real:** As queries sao executadas de verdade contra um motor SQL
  completo. Erros de sintaxe, tipos incorretos e logica quebrada sao
  detectados nos testes.
- **Zero custo AWS:** Nenhuma query Athena e executada durante desenvolvimento.
  Custo mensal de desenvolvimento = US$ 0.
- **CI sem credenciais:** Pipelines de CI/CD rodam sem precisar de
  AWS_PROFILE ou IAM roles. Basta instalar duckdb via pip.
- **Compatibilidade alta:** DuckDB suporta a maioria do SQL ANSI e tem
  boa sobreposicao com Presto. As 4 funcoes que diferem sao poucas e
  bem mapeadas.

### Negativas

- **Manutencao do dialeto:** Cada nova funcao SQL que difere entre Athena
  e DuckDB precisa ser adicionada ao `DIALECT_FUNCTIONS`. Se uma query
  usa funcao nao mapeada, vai falhar no mock mas funcionar no Athena
  (ou vice-versa).
- **Diferencas sutis de comportamento:** DuckDB e Athena podem divergir
  em edge cases (arredondamento de floats, tratamento de NaN/NULL,
  cast implicito de tipos). Esses bugs sao dificeis de detectar
  e exigem testes de integracao periodicos contra Athena real.
- **Dados sinteticos != dados reais:** Distribuicoes sinteticas nao
  capturam todas as anomalias de dados reais (encoding, caracteres
  especiais, valores extremos, particoes vazias). Testes de integracao
  com Athena real sao obrigatorios a cada sprint.
- **DuckDB nao simula particoes:** O conceito de particionamento
  fisico S3/Glue nao existe no DuckDB. Queries que dependem de
  `SHOW PARTITIONS` precisam de tratamento especial no mock.

---

## Mitigacoes

Para as consequencias negativas, as seguintes mitigacoes estao em vigor:

- **Testes de integracao com Athena real:** Obrigatorios ao final de
  cada sprint (hook `integration-qa`). Comparam resultados DuckDB vs
  Athena para detectar divergencias.
- **sql_dialect.py centralizado:** Todas as diferencas ficam em um unico
  arquivo. Quando uma nova divergencia e descoberta, basta adicionar
  uma entrada ao dicionario.
- **resolve_date_expression():** Metodo no `QueryBuilder` que trata
  automaticamente a diferenca de cast de datas entre backends.
- **Mock data realista:** Os dados sinteticos simulam padroes reais
  (drift, sazonalidade, outliers, nulls) para cobrir mais cenarios.
