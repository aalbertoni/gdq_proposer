-- metadata_discovery.sql
-- Retorna colunas e tipos de uma tabela.
-- Parâmetros: table_ref (via sql_dialect TABLE_REF)
SELECT
  column_name,
  data_type
FROM information_schema.columns
WHERE table_name = '{{ table }}'
ORDER BY ordinal_position
