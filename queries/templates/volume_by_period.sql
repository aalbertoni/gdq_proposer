-- volume_by_period.sql
-- Row count por período para validar grão e volume.
-- Parâmetros: table_ref, temporal_col, date_expression, base_filter, partition_filter, limit
SELECT
  {{ date_expression or '"' ~ temporal_col ~ '"' }} as processing_period,
  COUNT(*) as row_count
FROM {{ table_ref }}
WHERE 1=1
{% if partition_filter %}
  AND {{ partition_filter }}
{% endif %}
{% if base_filter %}
  AND {{ base_filter }}
{% endif %}
GROUP BY {{ date_expression or '"' ~ temporal_col ~ '"' }}
ORDER BY processing_period DESC
LIMIT {{ limit }}
