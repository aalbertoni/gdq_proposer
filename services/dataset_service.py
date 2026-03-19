"""
Camada A: Metadata Discovery.

Valida tabelas, lista colunas, descobre partições e
calcula range temporal + volume por período.

Definido conforme docs/technical_spec_v1.md seção 4.1.
"""

from typing import Optional

from core.models.dataset_config import DatasetConfig
from infra.athena_client import AthenaClient
from infra.query_builder import QueryBuilder
from infra.query_safety import validate_identifier, sanitize_filter


class DatasetService:
    """Metadata discovery e validação de tabelas."""

    def __init__(self, client: AthenaClient, builder: QueryBuilder):
        self.client = client
        self.builder = builder

    def validate_table(self, schema: str, table: str) -> bool:
        """Verifica se schema.table existe no catálogo Athena.

        Args:
            schema: Nome do schema/database.
            table: Nome da tabela.

        Returns:
            True se a tabela existe e é acessível.
        """
        validate_identifier(schema)
        validate_identifier(table)
        return self.client.table_exists(schema, table)

    def get_columns(self, schema: str, table: str) -> list[dict]:
        """Retorna colunas com nome e tipo Athena.

        Args:
            schema: Nome do schema/database.
            table: Nome da tabela.

        Returns:
            Lista de {"name": "col1", "type": "string", ...}

        Raises:
            ValueError: Se identificadores são inválidos.
        """
        validate_identifier(schema)
        validate_identifier(table)
        return self.client.get_columns(schema, table)

    def get_columns_with_partitions(
        self, schema: str, table: str,
    ) -> tuple[list[dict], list[str]]:
        """Retorna colunas e nomes das colunas de particao.

        Args:
            schema: Nome do schema/database.
            table: Nome da tabela.

        Returns:
            Tuple (columns, partition_columns):
            - columns: [{"name": str, "type": str}, ...]
            - partition_columns: ["dt_ref", ...] (vazia se nao particionada)
        """
        validate_identifier(schema)
        validate_identifier(table)
        return self.client.get_columns_with_partitions(schema, table)

    def get_partitions(self, schema: str, table: str) -> list[str]:
        """Retorna partições disponíveis (se particionada).

        No mock, retorna valores distintos da coluna de partição
        via metadata. No Athena real, usa SHOW PARTITIONS.

        Args:
            schema: Nome do schema/database.
            table: Nome da tabela.

        Returns:
            Lista de strings com valores de partição.
        """
        validate_identifier(schema)
        validate_identifier(table)
        # Para MVP, delega ao client; expansível para SHOW PARTITIONS
        try:
            sql = self.builder.build_show_partitions(schema, table)
            df = self.client.execute_df(
                sql,
                query_name="show_partitions",
                dataset=f"{schema}.{table}",
            )
            if df.empty:
                return []
            return df.iloc[:, 0].astype(str).tolist()
        except Exception:
            return []

    def get_date_range(self, config: DatasetConfig) -> dict:
        """Retorna min/max da coluna temporal e contagem de períodos.

        Args:
            config: Configuração da tabela alvo.

        Returns:
            {"min_date": str, "max_date": str, "n_periods": int}
        """
        validate_identifier(config.schema)
        validate_identifier(config.table)

        temporal_col = config.effective_temporal_axis
        validate_identifier(temporal_col)

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        sql = self.builder.build_date_range(
            schema=config.schema,
            table=config.table,
            temporal_col=temporal_col,
            date_expression=config.date_expression,
            base_filter=base_filter,
        )
        df = self.client.execute_df(
            sql,
            query_name="date_range",
            dataset=f"{config.schema}.{config.table}",
        )

        if df.empty:
            return {"min_date": None, "max_date": None, "n_periods": 0}

        row = df.iloc[0]
        return {
            "min_date": str(row["min_date"]) if row["min_date"] is not None else None,
            "max_date": str(row["max_date"]) if row["max_date"] is not None else None,
            "n_periods": int(row["n_periods"]) if row["n_periods"] is not None else 0,
        }

    def estimate_volume_and_adapt_timeout(self, config: DatasetConfig) -> int:
        """Estima volume da tabela no lookback window e adapta o timeout.

        Usa COUNT(*) com partition pruning para ser rapido mesmo em
        tabelas grandes. Adapta o timeout do AthenaClient automaticamente.

        Args:
            config: Configuracao da tabela alvo.

        Returns:
            Numero estimado de linhas no lookback window.
        """
        validate_identifier(config.schema)
        validate_identifier(config.table)

        partition_filter = self.builder.resolve_partition_filter(
            partition_column=config.partition_column,
            date_expression=config.date_expression,
            lookback_value=config.lookback_value,
        )

        from infra.sql_dialect import adapt_function
        table_ref = adapt_function(
            "TABLE_REF", self.builder.dialect,
            schema=config.schema, table=config.table,
        )

        where_clause = "WHERE 1=1"
        if partition_filter:
            where_clause += f" AND {partition_filter}"

        sql = f"SELECT COUNT(*) as total FROM {table_ref} {where_clause}"

        try:
            rows = self.client.execute(
                sql,
                query_name="estimate_volume",
                dataset=f"{config.schema}.{config.table}",
            )
            estimated = int(rows[0]["total"]) if rows else 0
        except Exception:
            estimated = 0

        if estimated > 0:
            self.client.adapt_timeout(estimated)

        return estimated

    def get_volume_by_period(
        self, config: DatasetConfig, limit: int = 50
    ) -> list[dict]:
        """Row count por período (para validar grão e volume).

        Args:
            config: Configuração da tabela alvo.
            limit: Número máximo de períodos a retornar.

        Returns:
            [{"period": "2026-01-15", "row_count": 50000}, ...]
        """
        validate_identifier(config.schema)
        validate_identifier(config.table)

        temporal_col = config.effective_temporal_axis
        validate_identifier(temporal_col)

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        sql = self.builder.build_volume_by_period(
            schema=config.schema,
            table=config.table,
            temporal_col=temporal_col,
            date_expression=config.date_expression,
            base_filter=base_filter,
            limit=limit,
        )
        df = self.client.execute_df(
            sql,
            query_name="volume_by_period",
            dataset=f"{config.schema}.{config.table}",
        )

        if df.empty:
            return []

        return [
            {
                "period": str(row["processing_period"]),
                "row_count": int(row["row_count"]),
            }
            for _, row in df.iterrows()
        ]
