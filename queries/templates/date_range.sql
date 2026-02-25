-- date_range.sql
-- Retorna min/max da coluna temporal e contagem de períodos distintos.
-- Parâmetros: table_ref, temporal_col, date_expression, base_filter
SELECT
  MIN({{ date_expression or '"' ~ temporal_col ~ '"' }}) as min_date,
  MAX({{ date_expression or '"' ~ temporal_col ~ '"' }}) as max_date,
  COUNT(DISTINCT {{ date_expression or '"' ~ temporal_col ~ '"' }}) as n_periods
FROM {{ table_ref }}
{% if base_filter %}
WHERE {{ base_filter }}
{% endif %}
