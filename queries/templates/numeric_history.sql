-- numeric_history.sql
-- Análise histórica de coluna numérica: agregações por período.
-- Usado pelo AnalysisService para alimentar statistical_engine e backtest.
-- Parâmetros: table_ref, col, date_expression, stddev_func,
--             approx_percentile_expr, date_lookback_expr, base_filter,
--             partition_filter
SELECT
  {{ date_expression }} as processing_period,
  COUNT(*) as total_count,
  COUNT("{{ col }}") as non_null_count,
  COUNT(*) - COUNT("{{ col }}") as null_count,
  AVG(CAST("{{ col }}" AS DOUBLE)) as col_mean,
  {{ stddev_func }}(CAST("{{ col }}" AS DOUBLE)) as col_stddev,
  MIN(CAST("{{ col }}" AS DOUBLE)) as col_min,
  MAX(CAST("{{ col }}" AS DOUBLE)) as col_max,
  {{ approx_percentile_expr }} as col_percentiles
FROM {{ table_ref }}{% if tablesample_clause %} {{ tablesample_clause }}{% endif %}

WHERE {{ date_expression }} >= {{ date_lookback_expr }}
{% if partition_filter %}
  AND {{ partition_filter }}
{% endif %}
{% if date_filter %}
  AND {{ date_filter }}
{% endif %}
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
GROUP BY {{ date_expression }}
ORDER BY processing_period
