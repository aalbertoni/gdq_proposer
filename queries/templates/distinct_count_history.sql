-- distinct_count_history.sql
-- Distinct count of a categorical column per period.
-- Used by AnalysisService to chart distinct value trends and backtest DistinctCount rules.
-- Parameters: table_ref, col, date_expression, date_lookback_expr, base_filter
SELECT
  {{ date_expression }} as processing_period,
  COUNT(DISTINCT CAST("{{ col }}" AS VARCHAR)) as distinct_count,
  COUNT(*) as total_count,
  COUNT("{{ col }}") as non_null_count
FROM {{ table_ref }}
WHERE {{ date_expression }} >= {{ date_lookback_expr }}
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
GROUP BY {{ date_expression }}
ORDER BY processing_period
