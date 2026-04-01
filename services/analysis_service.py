"""
Camada C: Análise histórica de colunas numéricas.

Executa queries de histórico via Athena (ou DuckDB mock) e
retorna DataFrames com agregações por período.

Definido conforme docs/technical_spec_v1.md seção 4.3.
"""

import json
import logging
import math

import pandas as pd

from core.models.dataset_config import DatasetConfig
from core.models.enums import GrainType
from core.models.grain_policy import get_grain_policy
from infra.athena_client import AthenaClient
from infra.query_builder import QueryBuilder
from infra.query_safety import validate_identifier, sanitize_filter, sanitize_expression

logger = logging.getLogger(__name__)


def diagnose_history_gap(
    n_periods_returned: int,
    config: DatasetConfig,
    profiling_total_count: int | None = None,
) -> list[str]:
    """Diagnostica gap entre profiling (encontrou dados) e histórico (vazio/curto).

    Retorna lista de warnings contextuais e acionáveis.
    Lista vazia = sem problemas detectados.

    Args:
        n_periods_returned: Períodos retornados pelo histórico (0 = vazio).
        config: DatasetConfig usada na análise.
        profiling_total_count: total_count do profiling (se disponível).
            Quando > 0 e n_periods == 0, sinaliza gap profiling→histórico.
    """
    warnings: list[str] = []
    policy = get_grain_policy(config.grain_type)

    if n_periods_returned == 0:
        # Gap: histórico vazio
        if profiling_total_count is not None and profiling_total_count > 0:
            warnings.append(
                "Profiling encontrou dados, mas historico retornou 0 periodos. "
                "Possivel causa: lookback_value ou reference_date incompativeis "
                "com a janela de analise historica."
            )
        else:
            warnings.append(
                "Historico retornou 0 periodos. "
                "Verifique reference_date, lookback_value e granularidade."
            )

        if config.grain_type == GrainType.MONTHLY:
            warnings.append(
                f"Granularidade MONTHLY com lookback_value={config.lookback_value} dias. "
                f"Para capturar N meses, lookback_value deve ser >= N*31 dias."
            )

        if not config.reference_date:
            warnings.append(
                "reference_date nao definido — lookback usa data atual. "
                "Se a tabela tem dados historicos, defina reference_date "
                "para a data do ultimo processamento."
            )

    elif n_periods_returned < policy.min_history:
        # Poucos períodos: backtest não vai funcionar
        warnings.append(
            f"Historico com {n_periods_returned} periodos, "
            f"abaixo do minimo para backtest ({policy.min_history}). "
            f"Regras serao propostas sem evidencia de backtest — confianca reduzida."
        )
        if config.grain_type == GrainType.MONTHLY and config.lookback_value < 365:
            warnings.append(
                f"lookback_value={config.lookback_value} dias pode ser insuficiente "
                f"para acumular {policy.min_history}+ periodos mensais. "
                f"Considere aumentar para {policy.min_history * 31}+ dias."
            )

    return warnings


class AnalysisService:
    """Análise histórica de colunas numéricas."""

    def __init__(self, client: AthenaClient, builder: QueryBuilder):
        self.client = client
        self.builder = builder

    def _resolve_date_filter(self, config: DatasetConfig) -> str:
        """Resolve filtro de data de negocio para queries de analise.

        Gera predicado WHERE adicional quando a coluna de data de negocio
        e diferente da particao E diferente do eixo temporal do GROUP BY.
        Evita analisar dados de todos os periodos de negocio quando so
        queremos o subset relevante dentro de cada particao.

        Returns:
            Predicado SQL (sem WHERE), ou string vazia se nao aplicavel.
        """
        if not config.has_date_filter:
            return ""
        if not config.date_column or config.date_column == config.effective_temporal_axis:
            return ""
        # A coluna de data esta no GROUP BY via date_expression, que ja filtra
        # pelo lookback. O date_filter adicional so e necessario quando
        # effective_temporal_axis != date_column (ex: partition como eixo + date col separada).
        # Neste caso, a filtragem pela coluna de data deve ser adicionada.
        validate_identifier(config.date_column)
        date_expr = config.date_expression
        if date_expr:
            date_expr = sanitize_expression(date_expr)
        else:
            date_expr = f'"{config.date_column}"'
        lookback_expr = self.builder.date_lookback_expr(
            config.lookback_value, config.reference_date or "",
        )
        return f"{date_expr} >= {lookback_expr}"

    def _resolve_partition_filter(self, config: DatasetConfig) -> str:
        """Resolve filtro de particao para partition pruning nas queries de analise.

        Retorna string vazia quando a partição não é temporal (ex: flag "s"/"n"),
        evitando predicados absurdos como '"flag_ativo" >= "2026-02-18"'.
        """
        if not config.partition_is_temporal:
            return ""
        if config.partition_columns:
            return self.builder.resolve_partition_filter(
                partition_columns=config.partition_columns,
                partition_formats=config.partition_formats,
                partition_is_integer_map=config.partition_is_integer_map,
                lookback_value=config.lookback_value,
                reference_date=config.reference_date or "",
            )
        return self.builder.resolve_partition_filter(
            partition_column=config.partition_column,
            partition_format=config.partition_format,
            lookback_value=config.lookback_value,
            reference_date=config.reference_date or "",
            partition_is_integer=config.partition_is_integer,
        )

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

        raw_date_expr = config.date_expression or ""
        if raw_date_expr:
            raw_date_expr = sanitize_expression(raw_date_expr)
        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, raw_date_expr,
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        partition_filter = self._resolve_partition_filter(config)
        date_filter = self._resolve_date_filter(config)

        sql = self.builder.build_numeric_history(
            schema=config.schema,
            table=config.table,
            col=column,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
            partition_filter=partition_filter,
            reference_date=config.reference_date or "",
            date_filter=date_filter,
        )

        df = self.client.execute_df(
            sql,
            query_name="numeric_history",
            dataset=f"{config.schema}.{config.table}",
            column=column,
        )

        n_periods = len(df) if not df.empty else 0
        diag = diagnose_history_gap(n_periods, config)
        for w in diag:
            logger.warning("[numeric_history %s.%s.%s] %s",
                           config.schema, config.table, column, w)

        if df.empty:
            return pd.DataFrame(columns=[
                "period", "mean", "stddev", "min", "max",
                "p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99",
                "non_null_count", "null_count", "total_count",
            ])

        return self._normalize_df(df)

    def get_numeric_history_filtered(
        self,
        config: DatasetConfig,
        column: str,
        subpopulation_filter: str,
    ) -> pd.DataFrame:
        """Executa query de historico numerico filtrado por subpopulacao.

        Reutiliza o template numeric_history.sql, compondo o filtro de
        subpopulacao com o base_filter existente.

        Args:
            config: Configuracao da tabela alvo.
            column: Nome da coluna numerica.
            subpopulation_filter: Expressao WHERE (sem keyword WHERE).
                Ex: "TIPO_PRODUTO = 'CONSIGNADO'"

        Returns:
            DataFrame com mesmas colunas de get_numeric_history.
        """
        validate_identifier(config.schema)
        validate_identifier(config.table)
        validate_identifier(column)

        raw_date_expr = config.date_expression or ""
        if raw_date_expr:
            raw_date_expr = sanitize_expression(raw_date_expr)
        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, raw_date_expr,
        )

        # Compose base_filter with subpopulation_filter
        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)
        subpop_sanitized = sanitize_filter(subpopulation_filter)
        if base_filter:
            base_filter = f"({base_filter}) AND ({subpop_sanitized})"
        else:
            base_filter = subpop_sanitized

        partition_filter = self._resolve_partition_filter(config)
        date_filter = self._resolve_date_filter(config)

        sql = self.builder.build_numeric_history(
            schema=config.schema,
            table=config.table,
            col=column,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
            partition_filter=partition_filter,
            reference_date=config.reference_date or "",
            date_filter=date_filter,
        )

        df = self.client.execute_df(
            sql,
            query_name="numeric_history_subpop",
            dataset=f"{config.schema}.{config.table}",
            column=column,
        )

        if df.empty:
            return pd.DataFrame(columns=[
                "period", "mean", "stddev", "min", "max",
                "p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99",
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

        raw_date_expr = config.date_expression or ""
        if raw_date_expr:
            raw_date_expr = sanitize_expression(raw_date_expr)
        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, raw_date_expr,
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        partition_filter = self._resolve_partition_filter(config)
        date_filter = self._resolve_date_filter(config)

        sql = self.builder.build_row_count_history(
            schema=config.schema,
            table=config.table,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
            partition_filter=partition_filter,
            reference_date=config.reference_date or "",
            date_filter=date_filter,
        )

        df = self.client.execute_df(
            sql,
            query_name="row_count_history",
            dataset=f"{config.schema}.{config.table}",
        )

        n_periods = len(df) if not df.empty else 0
        diag = diagnose_history_gap(n_periods, config)
        for w in diag:
            logger.warning("[row_count_history %s.%s] %s",
                           config.schema, config.table, w)

        if df.empty:
            return pd.DataFrame(columns=["period", "row_count"])

        result = pd.DataFrame()
        result["period"] = df["processing_period"].astype(str)
        result["row_count"] = pd.to_numeric(df["row_count"], errors="coerce").fillna(0).astype(float)

        return result.sort_values("period").reset_index(drop=True)

    def get_distinct_count_history(
        self,
        config: DatasetConfig,
        column: str,
    ) -> pd.DataFrame:
        """Contagem de valores distintos por periodo para uma coluna categorica.

        Args:
            config: Configuracao da tabela alvo.
            column: Coluna categorica.

        Returns:
            DataFrame com colunas: [period, distinct_count, total_count, non_null_count]
        """
        validate_identifier(config.schema)
        validate_identifier(config.table)
        validate_identifier(column)

        raw_date_expr = config.date_expression or ""
        if raw_date_expr:
            raw_date_expr = sanitize_expression(raw_date_expr)
        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, raw_date_expr,
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        partition_filter = self._resolve_partition_filter(config)
        date_filter = self._resolve_date_filter(config)

        sql = self.builder.build_distinct_count_history(
            schema=config.schema,
            table=config.table,
            col=column,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
            partition_filter=partition_filter,
            reference_date=config.reference_date or "",
            date_filter=date_filter,
        )

        df = self.client.execute_df(
            sql,
            query_name="distinct_count_history",
            dataset=f"{config.schema}.{config.table}",
            column=column,
        )

        if df.empty:
            return pd.DataFrame(columns=[
                "period", "distinct_count", "total_count", "non_null_count",
            ])

        result = pd.DataFrame()
        result["period"] = df["processing_period"].astype(str)
        result["distinct_count"] = pd.to_numeric(df["distinct_count"], errors="coerce").fillna(0).astype(int)
        result["total_count"] = pd.to_numeric(df["total_count"], errors="coerce").fillna(0).astype(int)
        result["non_null_count"] = pd.to_numeric(df["non_null_count"], errors="coerce").fillna(0).astype(int)

        return result.sort_values("period").reset_index(drop=True)

    def get_uniqueness_history(
        self,
        config: DatasetConfig,
        key_columns: list[str],
    ) -> pd.DataFrame:
        """Unicidade e completude de colunas-chave por periodo.

        Verifica se a combinacao de key_columns forma uma chave primaria
        valida em cada periodo historico, contando duplicatas e nulls.

        Args:
            config: Configuracao da tabela alvo.
            key_columns: Lista de colunas que compoe a chave primaria.

        Returns:
            DataFrame com colunas: [period, total_rows, distinct_keys,
            duplicate_count, non_null_{col1}, non_null_{col2}, ...]

        Raises:
            ValueError: Se key_columns esta vazio ou contem identificador invalido.
        """
        if not key_columns:
            raise ValueError("key_columns nao pode ser vazio")

        validate_identifier(config.schema)
        validate_identifier(config.table)
        for col in key_columns:
            validate_identifier(col)

        raw_date_expr = config.date_expression or ""
        if raw_date_expr:
            raw_date_expr = sanitize_expression(raw_date_expr)
        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, raw_date_expr,
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        partition_filter = self._resolve_partition_filter(config)
        date_filter = self._resolve_date_filter(config)

        sql = self.builder.build_uniqueness_check(
            schema=config.schema,
            table=config.table,
            key_columns=key_columns,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
            partition_filter=partition_filter,
            reference_date=config.reference_date or "",
            date_filter=date_filter,
        )

        df = self.client.execute_df(
            sql,
            query_name="uniqueness_check",
            dataset=f"{config.schema}.{config.table}",
        )

        # Build expected column list
        expected_cols = ["period", "total_rows", "distinct_keys", "duplicate_count"]
        for col in key_columns:
            expected_cols.append(f"non_null_{col}")

        if df.empty:
            return pd.DataFrame(columns=expected_cols)

        result = pd.DataFrame()
        result["period"] = df["processing_period"].astype(str)
        result["total_rows"] = pd.to_numeric(df["total_rows"], errors="coerce").fillna(0).astype(int)
        result["distinct_keys"] = pd.to_numeric(df["distinct_keys"], errors="coerce").fillna(0).astype(int)
        result["duplicate_count"] = pd.to_numeric(df["duplicate_count"], errors="coerce").fillna(0).astype(int)

        for col in key_columns:
            src_col = f"non_null_{col}"
            if src_col in df.columns:
                result[src_col] = pd.to_numeric(df[src_col], errors="coerce").fillna(0).astype(int)
            else:
                result[src_col] = 0

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

        raw_date_expr = config.date_expression or ""
        if raw_date_expr:
            raw_date_expr = sanitize_expression(raw_date_expr)
        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, raw_date_expr,
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        partition_filter = self._resolve_partition_filter(config)
        date_filter = self._resolve_date_filter(config)

        sql = self.builder.build_categorical_distribution(
            schema=config.schema,
            table=config.table,
            col=column,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
            partition_filter=partition_filter,
            reference_date=config.reference_date or "",
            date_filter=date_filter,
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

        raw_date_expr = config.date_expression or ""
        if raw_date_expr:
            raw_date_expr = sanitize_expression(raw_date_expr)
        date_expr = self.builder.resolve_date_expression(
            config.effective_temporal_axis, raw_date_expr,
        )

        base_filter = ""
        if config.base_filter_sql:
            base_filter = sanitize_filter(config.base_filter_sql)

        partition_filter = self._resolve_partition_filter(config)
        date_filter = self._resolve_date_filter(config)

        sql = self.builder.build_categorical_domain(
            schema=config.schema,
            table=config.table,
            col=column,
            date_expression=date_expr,
            lookback_value=config.lookback_value,
            base_filter=base_filter,
            partition_filter=partition_filter,
            limit=limit,
            reference_date=config.reference_date or "",
            date_filter=date_filter,
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

        # Expandir percentis do array (9 elementos: p01..p99)
        percentile_cols = ["p01", "p05", "p10", "p25", "p50", "p75", "p90", "p95", "p99"]
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
