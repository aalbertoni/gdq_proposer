-- categorical_domain.sql
-- Valores distintos e frequencia global de uma coluna categorica.
-- Usado pelo AnalysisService para ColumnValues, DistinctValuesCount, e filtragem top-K.
-- Parametros: table_ref, col, date_expression, date_lookback_expr, base_filter, limit
SELECT
  CAST("{{ col }}" AS VARCHAR) as category_value,
  COUNT(*) as value_count,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as value_pct
FROM {{ table_ref }}
WHERE {{ date_expression }} >= {{ date_lookback_expr }}
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
GROUP BY CAST("{{ col }}" AS VARCHAR)
ORDER BY value_count DESC
{% if limit %}
LIMIT {{ limit }}
{% endif %}
