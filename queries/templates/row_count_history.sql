-- row_count_history.sql
-- Row count por periodo para analise de regra RowCount.
-- Parametros: table_ref, date_expression, date_lookback_expr, base_filter, partition_filter
SELECT
  {{ date_expression }} as processing_period,
  COUNT(*) as row_count
FROM {{ table_ref }}
WHERE {{ date_expression }} >= {{ date_lookback_expr }}
{% if partition_filter %}
  AND {{ partition_filter }}
{% endif %}
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
GROUP BY {{ date_expression }}
ORDER BY processing_period
