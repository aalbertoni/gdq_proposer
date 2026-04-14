-- column_sample.sql
-- Profiling de uma coluna: contagens, cardinalidade e cast numérico.
-- Usado pelo ProfilingService para classificação semântica.
-- Parâmetros: table_ref, col, temporal_col, date_expression,
--             sample_periods, date_lookback_expr, approx_distinct_expr,
--             partition_filter, base_filter
SELECT
  COUNT(*) as total_count,
  COUNT("{{ col }}") as non_null_count,
  {{ approx_distinct_expr }} as distinct_count,
  SUM(CASE WHEN TRY_CAST("{{ col }}" AS DOUBLE) IS NOT NULL THEN 1 ELSE 0 END) as numeric_cast_count
FROM {{ table_ref }}{% if tablesample_clause %} {{ tablesample_clause }}{% endif %}

WHERE {{ date_expression or '"' ~ temporal_col ~ '"' }} >= {{ date_lookback_expr }}
{% if partition_filter %}
  AND {{ partition_filter }}
{% endif %}
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
