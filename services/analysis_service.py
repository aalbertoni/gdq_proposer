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

        date_expr = config.date_expression or f'"{config.effective_temporal_axis}"'

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
