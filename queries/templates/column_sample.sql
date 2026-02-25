-- column_sample.sql
-- Profiling de uma coluna: contagens, cardinalidade e cast numérico.
-- Usado pelo ProfilingService para classificação semântica.
-- Parâmetros: table_ref, col, temporal_col, date_expression,
--             sample_periods, date_lookback_expr, base_filter
SELECT
  COUNT(*) as total_count,
  COUNT("{{ col }}") as non_null_count,
  COUNT(DISTINCT "{{ col }}") as distinct_count,
  SUM(CASE WHEN TRY_CAST("{{ col }}" AS DOUBLE) IS NOT NULL THEN 1 ELSE 0 END) as numeric_cast_count
FROM {{ table_ref }}
WHERE {{ date_expression or '"' ~ temporal_col ~ '"' }} >= {{ date_lookback_expr }}
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
