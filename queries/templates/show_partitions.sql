-- show_partitions.sql
-- Lista valores distintos da coluna de partição.
-- ATENCAO: SELECT DISTINCT faz full scan. Em producao no Athena real,
-- substituir por SHOW PARTITIONS "schema"."table" (zero bytes scanned).
-- Este template existe como fallback para DuckDB nos testes.
-- Fora do caminho critico atual (nenhuma pagina chama get_partitions).
-- Parâmetros: table_ref, partition_col
SELECT DISTINCT "{{ partition_col }}" as partition_value
FROM {{ table_ref }}
ORDER BY partition_value
