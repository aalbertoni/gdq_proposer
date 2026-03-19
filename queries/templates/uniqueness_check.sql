-- uniqueness_check.sql
-- Uniqueness and completeness of key columns per period.
-- Used by AnalysisService to evaluate IsPrimaryKey rule historically.
-- Parameters: table_ref, key_expr, key_cols, date_expression, date_lookback_expr, base_filter, partition_filter
SELECT
  {{ date_expression }} as processing_period,
  COUNT(*) as total_rows,
  COUNT(DISTINCT {{ key_expr }}) as distinct_keys,
  COUNT(*) - COUNT(DISTINCT {{ key_expr }}) as duplicate_count
  {%- for col in key_cols %},
  COUNT("{{ col }}") as "non_null_{{ col }}"
  {%- endfor %}
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
