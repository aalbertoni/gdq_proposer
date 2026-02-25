"""
Camada C: Análise histórica de colunas numéricas.

Executa queries de histórico via Athena (ou DuckDB mock) e
retorna DataFrames com agregações por período.

Definido conforme docs/technical_spec_v1.md seção 4.3.
"""

import json
import math

import pandas as pd

from core.models.dataset_config import DatasetConfig
from infra.athena_client import AthenaClient
from infra.query_builder import QueryBuilder
from infra.query_safety import validate_identifier, sanitize_filter


class AnalysisService:
    """Análise histórica de colunas numéricas."""

    def __init__(self, client: AthenaClient, builder: QueryBuilder):
        self.client = client
        self.builder = builder

    def get_numeric_history(
        self,
        config: DatasetConfig,
        column: str,
    ) -> pd.DataFrame:
        """Executa query de histórico numérico e retorna DataFrame normalizado.

        Args:
            config: Configuração da tabela alvo.
            column: Nome da coluna numérica.

        Returns:
            DataFrame com colunas: [period, mean, stddev, min, max,
            p01, p05, p25, p50, p75, p95, p99,
            non_null_count, null_count, total_count]
        """
        validate_identifier(config.schema)
        validate_identifier(config.table)
        validate_identifier(column)

        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, config.date_expression or "",
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        sql = self.builder.build_numeric_history(
            schema=config.schema,
            table=config.table,
            col=column,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
        )

        df = self.client.execute_df(
            sql,
            query_name="numeric_history",
            dataset=f"{config.schema}.{config.table}",
            column=column,
        )

        if df.empty:
            return pd.DataFrame(columns=[
                "period", "mean", "stddev", "min", "max",
                "p01", "p05", "p25", "p50", "p75", "p95", "p99",
                "non_null_count", "null_count", "total_count",
            ])

        return self._normalize_df(df)

    def get_row_count_history(
        self,
        config: DatasetConfig,
    ) -> pd.DataFrame:
        """Row count por periodo para analise de regra RowCount.

        Args:
            config: Configuracao da tabela alvo.

        Returns:
            DataFrame com colunas: [period, row_count]
        """
        validate_identifier(config.schema)
        validate_identifier(config.table)

        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, config.date_expression or "",
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        sql = self.builder.build_row_count_history(
            schema=config.schema,
            table=config.table,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
        )

        df = self.client.execute_df(
            sql,
            query_name="row_count_history",
            dataset=f"{config.schema}.{config.table}",
        )

        if df.empty:
            return pd.DataFrame(columns=["period", "row_count"])

        result = pd.DataFrame()
        result["period"] = df["processing_period"].astype(str)
        result["row_count"] = pd.to_numeric(df["row_count"], errors="coerce").fillna(0).astype(float)

        return result.sort_values("period").reset_index(drop=True)

    def get_categorical_distribution(
        self,
        config: DatasetConfig,
        column: str,
    ) -> pd.DataFrame:
        """Distribuicao de valores categoricos por periodo.

        Args:
            config: Configuracao da tabela alvo.
            column: Coluna categorica.

        Returns:
            DataFrame [period, category_value, value_count, value_pct]
        """
        validate_identifier(config.schema)
        validate_identifier(config.table)
        validate_identifier(column)

        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, config.date_expression or "",
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        sql = self.builder.build_categorical_distribution(
            schema=config.schema,
            table=config.table,
            col=column,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
        )

        df = self.client.execute_df(
            sql,
            query_name="categorical_distribution",
            dataset=f"{config.schema}.{config.table}",
            column=column,
        )

        if df.empty:
            return pd.DataFrame(columns=[
                "period", "category_value", "value_count", "value_pct",
            ])

        result = pd.DataFrame()
        result["period"] = df["processing_period"].astype(str)
        result["category_value"] = df["category_value"].astype(str)
        result["value_count"] = pd.to_numeric(df["value_count"], errors="coerce").fillna(0).astype(int)
        result["value_pct"] = pd.to_numeric(df["value_pct"], errors="coerce").fillna(0.0)

        return result.sort_values(["period", "value_pct"], ascending=[True, False]).reset_index(drop=True)

    def get_categorical_domain(
        self,
        config: DatasetConfig,
        column: str,
        limit: int = 0,
    ) -> pd.DataFrame:
        """Valores distintos e frequencia global.

        Args:
            config: Configuracao da tabela alvo.
            column: Coluna categorica.
            limit: Max categorias (0 = all).

        Returns:
            DataFrame [category_value, value_count, value_pct]
        """
        validate_identifier(config.schema)
        validate_identifier(config.table)
        validate_identifier(column)

        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, config.date_expression or "",
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        sql = self.builder.build_categorical_domain(
            schema=config.schema,
            table=config.table,
            col=column,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
            limit=limit,
        )

        df = self.client.execute_df(
            sql,
            query_name="categorical_domain",
            dataset=f"{config.schema}.{config.table}",
            column=column,
        )

        if df.empty:
            return pd.DataFrame(columns=[
                "category_value", "value_count", "value_pct",
            ])

        result = pd.DataFrame()
        result["category_value"] = df["category_value"].astype(str)
        result["value_count"] = pd.to_numeric(df["value_count"], errors="coerce").fillna(0).astype(int)
        result["value_pct"] = pd.to_numeric(df["value_pct"], errors="coerce").fillna(0.0)

        return result.sort_values("value_count", ascending=False).reset_index(drop=True)

    def _normalize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normaliza o DataFrame: renomeia colunas e expande percentis."""
        result = pd.DataFrame()
        result["period"] = df["processing_period"].astype(str)
        result["mean"] = pd.to_numeric(df["col_mean"], errors="coerce")
        result["stddev"] = pd.to_numeric(df["col_stddev"], errors="coerce")
        result["min"] = pd.to_numeric(df["col_min"], errors="coerce")
        result["max"] = pd.to_numeric(df["col_max"], errors="coerce")
        result["non_null_count"] = pd.to_numeric(df["non_null_count"], errors="coerce").fillna(0).astype(int)
        result["null_count"] = pd.to_numeric(df["null_count"], errors="coerce").fillna(0).astype(int)
        result["total_count"] = pd.to_numeric(df["total_count"], errors="coerce").fillna(0).astype(int)

        # Expandir percentis do array
        percentile_cols = ["p01", "p05", "p25", "p50", "p75", "p95", "p99"]
        percentile_data = df["col_percentiles"].apply(self._parse_percentile_array)
        for i, col_name in enumerate(percentile_cols):
            result[col_name] = percentile_data.apply(
                lambda arr, idx=i: arr[idx] if arr is not None and idx < len(arr) else None
            )

        return result.sort_values("period").reset_index(drop=True)

    @staticmethod
    def _parse_percentile_array(value) -> list[float] | None:
        """Parse array de percentis (compatível Athena e DuckDB).

        Athena pode retornar string como "[1.0, 2.0, ...]".
        DuckDB retorna lista nativa.
        """
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return [float(v) if v is not None else float("nan") for v in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [float(v) for v in parsed]
            except (json.JSONDecodeError, ValueError):
                pass
            # Athena pode retornar formato diferente
            try:
                import ast
                parsed = ast.literal_eval(value)
                if isinstance(parsed, (list, tuple)):
                    return [float(v) for v in parsed]
            except (ValueError, SyntaxError):
                pass
        # numpy array
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return None
