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
        """Retorna min/max da coluna temporal e contagem de periodos.

        Estrategia metadata-first:
        1. Para tabelas particionadas: descobre range via lista de particoes
           (SHOW PARTITIONS no Athena, SELECT DISTINCT no DuckDB).
           Zero bytes scanned no Athena. Deriva reference_date do max.
        2. Se base_filter_sql configurado: valida com query SQL leve pruneada.
        3. Fallback: query SQL sem pruning (tabelas nao particionadas ou erro).

        Args:
            config: Configuracao da tabela alvo.

        Returns:
            {"min_date": str, "max_date": str, "n_periods": int}
        """
        validate_identifier(config.schema)
        validate_identifier(config.table)

        # --- Caminho A: metadata de particoes (zero scan no Athena) ---
        if config.partition_column:
            try:
                result = self._get_date_range_from_partitions(config)
                if result and result["n_periods"] > 0:
                    return result
            except Exception:
                pass  # fallback para SQL

        # --- Caminho C: SQL sem pruning (fallback) ---
        return self._get_date_range_sql(config)

    def _get_date_range_from_partitions(self, config: DatasetConfig) -> dict | None:
        """Descobre range via lista de particoes (metadata-first).

        Usa SHOW PARTITIONS no Athena (zero scan) ou SELECT DISTINCT no DuckDB.
        Faz parsing dos valores de particao e deriva min/max/count em Python.
        """
        from datetime import datetime

        partition_col = config.partition_column
        validate_identifier(partition_col)

        # Obter lista de particoes
        if self.builder.dialect.value == "duckdb":
            # DuckDB: SELECT DISTINCT (teste-only)
            raw_values = self.get_partitions(config.schema, config.table)
        else:
            # Athena: SHOW PARTITIONS (zero scan)
            try:
                sql = f'SHOW PARTITIONS "{config.schema}"."{config.table}"'
                rows = self.client.execute(
                    sql,
                    query_name="show_partitions_metadata",
                    dataset=f"{config.schema}.{config.table}",
                )
                # SHOW PARTITIONS retorna rows como {"partition": "col=value"}
                raw_values = []
                for row in rows:
                    val = list(row.values())[0]  # primeiro campo
                    # Parse "col=value" ou valor direto
                    if "=" in str(val):
                        val = str(val).split("=", 1)[1]
                    raw_values.append(str(val))
            except Exception:
                # Fallback para SELECT DISTINCT
                raw_values = self.get_partitions(config.schema, config.table)

        if not raw_values:
            return None

        # Parse para datas usando partition_format
        fmt = config.partition_format
        dates = []
        for v in raw_values:
            v = v.strip()
            if not v:
                continue
            try:
                if fmt:
                    dt = datetime.strptime(v, fmt).date()
                else:
                    # Tipo nativo — tentar ISO parse
                    dt = datetime.fromisoformat(v.split(" ")[0]).date()
                dates.append(dt)
            except (ValueError, TypeError):
                continue

        if not dates:
            return None

        min_date = min(dates)
        max_date = max(dates)
        n_periods = len(set(dates))

        return {
            "min_date": str(min_date),
            "max_date": str(max_date),
            "n_periods": n_periods,
        }

    def _get_date_range_sql(self, config: DatasetConfig) -> dict:
        """Fallback: query SQL sem pruning para descobrir range."""
        temporal_col = config.effective_temporal_axis
        validate_identifier(temporal_col)

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        # SEM partition_filter — esta query descobre o range global
        sql = self.builder.build_date_range(
            schema=config.schema,
            table=config.table,
            temporal_col=temporal_col,
            date_expression=config.date_expression,
            base_filter=base_filter,
            partition_filter="",
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
            partition_format=config.partition_format,
            lookback_value=config.lookback_value,
            reference_date=config.reference_date or "",
            partition_is_integer=config.partition_is_integer,
        )

        from infra.sql_dialect import adapt_function
        table_ref = adapt_function(
            "TABLE_REF", self.builder.dialect,
            schema=config.schema, table=config.table,
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        where_clause = "WHERE 1=1"
        if partition_filter:
            where_clause += f" AND {partition_filter}"
        if base_filter:
            where_clause += f" AND {base_filter}"

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

        partition_filter = self.builder.resolve_partition_filter(
            partition_column=config.partition_column,
            partition_format=config.partition_format,
            lookback_value=config.lookback_value,
            reference_date=config.reference_date or "",
            partition_is_integer=config.partition_is_integer,
        )

        sql = self.builder.build_volume_by_period(
            schema=config.schema,
            table=config.table,
            temporal_col=temporal_col,
            date_expression=config.date_expression,
            base_filter=base_filter,
            partition_filter=partition_filter,
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
