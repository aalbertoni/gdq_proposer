-- date_range.sql
-- Retorna min/max da coluna temporal e contagem de períodos distintos.
-- Usa partition_filter quando disponível para evitar full scan.
-- Parâmetros: table_ref, temporal_col, date_expression, base_filter, partition_filter
SELECT
  MIN({{ date_expression or '"' ~ temporal_col ~ '"' }}) as min_date,
  MAX({{ date_expression or '"' ~ temporal_col ~ '"' }}) as max_date,
  COUNT(DISTINCT {{ date_expression or '"' ~ temporal_col ~ '"' }}) as n_periods
FROM {{ table_ref }}
WHERE 1=1
{% if partition_filter %}
  AND {{ partition_filter }}
{% endif %}
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
