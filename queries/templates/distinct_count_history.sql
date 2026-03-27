-- distinct_count_history.sql
-- Distinct count of a categorical column per period.
-- Used by AnalysisService to chart distinct value trends and backtest DistinctCount rules.
-- Uses APPROX_DISTINCT for lower cost (approx_distinct_expr adapts per dialect).
-- Parameters: table_ref, col, date_expression, date_lookback_expr,
--             approx_distinct_expr, base_filter, partition_filter
SELECT
  {{ date_expression }} as processing_period,
  {{ approx_distinct_expr }} as distinct_count,
  COUNT(*) as total_count,
  COUNT("{{ col }}") as non_null_count
FROM {{ table_ref }}
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
