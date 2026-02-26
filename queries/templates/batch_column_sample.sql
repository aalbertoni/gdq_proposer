-- batch_column_sample.sql
-- Profiling batch de multiplas colunas em uma unica query.
-- Reduz N scans para 1, usando APPROX_DISTINCT para cardinalidade.
-- Parametros: table_ref, string_cols, numeric_cols, date_expression,
--             date_lookback_expr, partition_filter, base_filter
SELECT
  COUNT(*) as total_count
{% for col in string_cols %}
  , COUNT("{{ col.name }}") as "{{ col.name }}__non_null"
  , {{ col.approx_distinct_expr }} as "{{ col.name }}__distinct"
  , SUM(CASE WHEN TRY_CAST("{{ col.name }}" AS DOUBLE) IS NOT NULL THEN 1 ELSE 0 END) as "{{ col.name }}__castable"
{% endfor %}
{% for col in numeric_cols %}
  , COUNT("{{ col.name }}") as "{{ col.name }}__non_null"
  , {{ col.approx_distinct_expr }} as "{{ col.name }}__distinct"
{% endfor %}
FROM {{ table_ref }}
WHERE {{ date_expression }} >= {{ date_lookback_expr }}
{% if partition_filter %}
  AND {{ partition_filter }}
{% endif %}
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
