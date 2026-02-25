-- show_partitions.sql
-- Lista valores distintos da coluna de partição.
-- No Athena real: substituir por SHOW PARTITIONS.
-- No mock (DuckDB): usa SELECT DISTINCT.
-- Parâmetros: table_ref, partition_col
SELECT DISTINCT "{{ partition_col }}" as partition_value
FROM {{ table_ref }}
ORDER BY partition_value
