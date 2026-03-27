-- categorical_distribution.sql
-- Distribuicao de valores categoricos por periodo.
-- Usado pelo AnalysisService para alimentar frequency_band e backtest categorico.
-- Parametros: table_ref, col, date_expression, date_lookback_expr, base_filter, partition_filter
SELECT
  {{ date_expression }} as processing_period,
  CAST("{{ col }}" AS VARCHAR) as category_value,
  COUNT(*) as value_count,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY {{ date_expression }}) as value_pct
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
GROUP BY {{ date_expression }}, CAST("{{ col }}" AS VARCHAR)
ORDER BY processing_period, value_count DESC
