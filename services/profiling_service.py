"""
Camada B: Column Classification.

Executa profiling de colunas via Athena (ou DuckDB mock) e
usa o column_classifier para inferir o tipo semântico.

Definido conforme docs/technical_spec_v1.md seção 4.2.
"""

import logging

from core.column_classifier import classify_column
from core.models.column_profile import ColumnProfile
from core.models.dataset_config import DatasetConfig
from core.models.enums import SemanticType
from infra.athena_client import AthenaClient
from infra.query_builder import QueryBuilder
from infra.query_safety import validate_identifier, sanitize_filter

logger = logging.getLogger(__name__)


class ProfilingService:
    """Classificação semântica de colunas via profiling."""

    def __init__(self, client: AthenaClient, builder: QueryBuilder):
        self.client = client
        self.builder = builder

    def profile_columns(
        self,
        config: DatasetConfig,
        columns: list[dict],
        sample_periods: int = 10,
    ) -> list[ColumnProfile]:
        """Classifica colunas usando estratégia em camadas.

        Camada 1: tipo físico Athena (int/double → NUMERIC, date → DATETIME)
        Camada 2: heurística de conteúdo (amostra limitada para strings)
        Camada 3: cardinalidade para subclassificar categóricas

        Usa batch profiling (1 query para todas as colunas) quando possível,
        com APPROX_DISTINCT e partition pruning para performance.

        Args:
            config: Configuração da tabela alvo.
            columns: Lista de {"name": str, "type": str} do get_columns().
            sample_periods: Número de períodos para amostragem de strings.

        Returns:
            Lista de ColumnProfile com tipo semântico inferido.
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

        # Batch profiling: 1 query para todas as colunas.
        # Fail-closed: se batch falha, NAO cair para N queries individuais.
        return self._batch_profile_columns(
            config=config,
            columns=columns,
            temporal_col=temporal_col,
            base_filter=base_filter,
            partition_filter=partition_filter,
            sample_periods=sample_periods,
        )

    def _profile_columns_per_column(
        self,
        config: DatasetConfig,
        columns: list[dict],
        temporal_col: str,
        base_filter: str,
        partition_filter: str,
        sample_periods: int,
    ) -> list[ColumnProfile]:
        """Profiling por coluna individual. Usado apenas para tabelas > BATCH_THRESHOLD."""
        profiles = []
        for col_info in columns:
            col_name = col_info["name"]
            athena_type = col_info["type"]

            profile = self._profile_single_column(
                config=config,
                col_name=col_name,
                athena_type=athena_type,
                temporal_col=temporal_col,
                base_filter=base_filter,
                partition_filter=partition_filter,
                sample_periods=sample_periods,
            )
            profiles.append(profile)

        return profiles

    def _batch_profile_columns(
        self,
        config: DatasetConfig,
        columns: list[dict],
        temporal_col: str,
        base_filter: str,
        partition_filter: str,
        sample_periods: int,
    ) -> list[ColumnProfile]:
        """Batch profiling: 1 query para todas as colunas."""
        from core.column_classifier import (
            ATHENA_DATE_TYPES,
            ATHENA_NUMERIC_TYPES,
            _normalize_athena_type,
            suggest_reclassification,
        )

        # Separar por tipo: date (sem query), numeric (só counts), string (full)
        date_cols = []
        numeric_cols = []
        string_cols = []

        for col_info in columns:
            col_name = col_info["name"]
            athena_type = col_info["type"]
            normalized = _normalize_athena_type(athena_type)

            validate_identifier(col_name)

            if normalized in ATHENA_DATE_TYPES:
                date_cols.append(col_info)
            elif normalized in ATHENA_NUMERIC_TYPES:
                numeric_cols.append(col_info)
            else:
                string_cols.append(col_info)

        # Profiles de date: sem query
        profiles_map = {}
        for col_info in date_cols:
            semantic_type = classify_column(
                athena_type=col_info["type"],
                distinct_count=0, total_count=0, non_null_count=0,
            )
            profiles_map[col_info["name"]] = ColumnProfile(
                column_name=col_info["name"],
                athena_type=col_info["type"],
                inferred_semantic_type=semantic_type,
            )

        # Batch query para numeric + string juntos
        str_names = [c["name"] for c in string_cols]
        num_names = [c["name"] for c in numeric_cols]

        if str_names or num_names:
            sql = self.builder.build_batch_column_sample(
                schema=config.schema,
                table=config.table,
                string_cols=str_names,
                numeric_cols=num_names,
                temporal_col=temporal_col,
                date_expression=config.date_expression or "",
                sample_periods=sample_periods,
                base_filter=base_filter,
                partition_filter=partition_filter,
                reference_date=config.reference_date or "",
            )

            df = self.client.execute_df(
                sql,
                query_name="batch_column_sample",
                dataset=f"{config.schema}.{config.table}",
            )

            if df.empty:
                raise ValueError("Batch profiling returned empty result")

            row = df.iloc[0]
            total_count = int(row["total_count"] or 0)

            # Parse string columns
            for col_info in string_cols:
                col_name = col_info["name"]
                athena_type = col_info["type"]
                non_null = int(row.get(f"{col_name}__non_null", 0) or 0)
                distinct = int(row.get(f"{col_name}__distinct", 0) or 0)
                raw_cast = row.get(f"{col_name}__castable", 0)
                castable = 0 if (raw_cast is None or raw_cast != raw_cast) else int(raw_cast)

                semantic_type = classify_column(
                    athena_type=athena_type,
                    distinct_count=distinct,
                    total_count=total_count,
                    non_null_count=non_null,
                    numeric_cast_count=castable,
                )

                null_ratio = (total_count - non_null) / total_count if total_count > 0 else 0.0
                distinct_ratio = distinct / non_null if non_null > 0 else 0.0
                numeric_cast_ratio = castable / non_null if non_null > 0 else 0.0

                warnings = []
                if null_ratio > 0.5:
                    warnings.append(f"Alta taxa de nulls: {null_ratio:.1%}")
                if total_count < 100:
                    warnings.append(f"Amostra pequena: {total_count} linhas")

                profiles_map[col_name] = ColumnProfile(
                    column_name=col_name,
                    athena_type=athena_type,
                    inferred_semantic_type=semantic_type,
                    total_count=total_count,
                    non_null_count=non_null,
                    distinct_count=distinct,
                    null_ratio=null_ratio,
                    distinct_ratio=distinct_ratio,
                    numeric_cast_ratio=numeric_cast_ratio,
                    warnings=warnings,
                )

            # Parse numeric columns
            for col_info in numeric_cols:
                col_name = col_info["name"]
                athena_type = col_info["type"]
                non_null = int(row.get(f"{col_name}__non_null", 0) or 0)
                distinct = int(row.get(f"{col_name}__distinct", 0) or 0)

                semantic_type = SemanticType.NUMERIC
                warnings = []

                suggested, warning_msg = suggest_reclassification(
                    athena_type=athena_type,
                    distinct_count=distinct,
                    total_count=total_count,
                    non_null_count=non_null,
                )
                if suggested is not None:
                    semantic_type = suggested
                    warnings.append(
                        f"Reclassificado automaticamente: {warning_msg} "
                        f"Tipo alterado para **{semantic_type.value}**. "
                        f"Altere manualmente se necessario."
                    )

                null_ratio = (total_count - non_null) / total_count if total_count > 0 else 0.0
                distinct_ratio = distinct / non_null if non_null > 0 else 0.0

                profiles_map[col_name] = ColumnProfile(
                    column_name=col_name,
                    athena_type=athena_type,
                    inferred_semantic_type=semantic_type,
                    total_count=total_count,
                    non_null_count=non_null,
                    distinct_count=distinct,
                    null_ratio=null_ratio,
                    distinct_ratio=distinct_ratio,
                    warnings=warnings,
                )

        # Retornar na ordem original
        return [profiles_map[c["name"]] for c in columns]

    def _profile_single_column(
        self,
        config: DatasetConfig,
        col_name: str,
        athena_type: str,
        temporal_col: str,
        base_filter: str,
        partition_filter: str = "",
        sample_periods: int = 10,
    ) -> ColumnProfile:
        """Faz profiling de uma coluna individual (fallback)."""
        from core.column_classifier import (
            ATHENA_DATE_TYPES,
            ATHENA_NUMERIC_TYPES,
            _normalize_athena_type,
            suggest_reclassification,
        )

        normalized = _normalize_athena_type(athena_type)

        # Camada 1a: date/timestamp → DATETIME direto, sem query
        if normalized in ATHENA_DATE_TYPES:
            semantic_type = classify_column(
                athena_type=athena_type,
                distinct_count=0,
                total_count=0,
                non_null_count=0,
            )
            return ColumnProfile(
                column_name=col_name,
                athena_type=athena_type,
                inferred_semantic_type=semantic_type,
            )

        # Camada 1b: numérico nativo → classificar como NUMERIC,
        # mas executar query leve de cardinalidade para guardrails
        if normalized in ATHENA_NUMERIC_TYPES:
            semantic_type = SemanticType.NUMERIC
            warnings = []
            total_count = 0
            non_null_count = 0
            distinct_count = 0

            try:
                card_df = self._query_cardinality(
                    config=config,
                    col_name=col_name,
                    temporal_col=temporal_col,
                    base_filter=base_filter,
                    partition_filter=partition_filter,
                    sample_periods=sample_periods,
                )
                if not card_df.empty:
                    row = card_df.iloc[0]
                    total_count = int(row["total_count"] or 0)
                    non_null_count = int(row["non_null_count"] or 0)
                    distinct_count = int(row["distinct_count"] or 0)

                    suggested, warning_msg = suggest_reclassification(
                        athena_type=athena_type,
                        distinct_count=distinct_count,
                        total_count=total_count,
                        non_null_count=non_null_count,
                    )
                    if suggested is not None:
                        semantic_type = suggested
                        warnings.append(
                            f"Reclassificado automaticamente: {warning_msg} "
                            f"Tipo alterado para **{semantic_type.value}**. "
                            f"Altere manualmente se necessario."
                        )
            except Exception:
                pass  # fallback: classificar como NUMERIC sem guardrail

            null_ratio = (
                (total_count - non_null_count) / total_count
                if total_count > 0 else 0.0
            )
            distinct_ratio = (
                distinct_count / non_null_count
                if non_null_count > 0 else 0.0
            )

            return ColumnProfile(
                column_name=col_name,
                athena_type=athena_type,
                inferred_semantic_type=semantic_type,
                total_count=total_count,
                non_null_count=non_null_count,
                distinct_count=distinct_count,
                null_ratio=null_ratio,
                distinct_ratio=distinct_ratio,
                warnings=warnings,
            )

        # Camada 2+3: strings precisam de query para métricas
        return self._profile_string_column(
            config=config,
            col_name=col_name,
            athena_type=athena_type,
            temporal_col=temporal_col,
            base_filter=base_filter,
            partition_filter=partition_filter,
            sample_periods=sample_periods,
        )

    def _profile_string_column(
        self,
        config: DatasetConfig,
        col_name: str,
        athena_type: str,
        temporal_col: str,
        base_filter: str,
        partition_filter: str = "",
        sample_periods: int = 10,
    ) -> ColumnProfile:
        """Executa query de profiling para coluna string."""
        validate_identifier(col_name)

        sql = self.builder.build_column_sample(
            schema=config.schema,
            table=config.table,
            col=col_name,
            temporal_col=temporal_col,
            date_expression=config.date_expression or "",
            sample_periods=sample_periods,
            base_filter=base_filter,
            partition_filter=partition_filter,
            reference_date=config.reference_date or "",
        )

        df = self.client.execute_df(
            sql,
            query_name="column_sample",
            dataset=f"{config.schema}.{config.table}",
            column=col_name,
        )

        if df.empty:
            return ColumnProfile(
                column_name=col_name,
                athena_type=athena_type,
                inferred_semantic_type=SemanticType.UNKNOWN,
                warnings=["Profiling retornou 0 linhas"],
            )

        row = df.iloc[0]
        total_count = int(row["total_count"] or 0)
        non_null_count = int(row["non_null_count"] or 0)
        distinct_count = int(row["distinct_count"] or 0)
        raw_cast = row["numeric_cast_count"]
        numeric_cast_count = 0 if (raw_cast is None or raw_cast != raw_cast) else int(raw_cast)

        semantic_type = classify_column(
            athena_type=athena_type,
            distinct_count=distinct_count,
            total_count=total_count,
            non_null_count=non_null_count,
            numeric_cast_count=numeric_cast_count,
        )

        null_ratio = (
            (total_count - non_null_count) / total_count
            if total_count > 0
            else 0.0
        )
        distinct_ratio = (
            distinct_count / non_null_count
            if non_null_count > 0
            else 0.0
        )
        numeric_cast_ratio = (
            numeric_cast_count / non_null_count
            if non_null_count > 0
            else 0.0
        )

        warnings = []
        if null_ratio > 0.5:
            warnings.append(f"Alta taxa de nulls: {null_ratio:.1%}")
        if total_count < 100:
            warnings.append(f"Amostra pequena: {total_count} linhas")

        return ColumnProfile(
            column_name=col_name,
            athena_type=athena_type,
            inferred_semantic_type=semantic_type,
            total_count=total_count,
            non_null_count=non_null_count,
            distinct_count=distinct_count,
            null_ratio=null_ratio,
            distinct_ratio=distinct_ratio,
            numeric_cast_ratio=numeric_cast_ratio,
            warnings=warnings,
        )

    def _query_cardinality(
        self,
        config: DatasetConfig,
        col_name: str,
        temporal_col: str,
        base_filter: str,
        partition_filter: str = "",
        sample_periods: int = 10,
    ):
        """Query leve de cardinalidade para colunas numéricas nativas."""
        validate_identifier(col_name)
        sql = self.builder.build_column_sample(
            schema=config.schema,
            table=config.table,
            col=col_name,
            temporal_col=temporal_col,
            date_expression=config.date_expression or "",
            sample_periods=sample_periods,
            base_filter=base_filter,
            partition_filter=partition_filter,
            reference_date=config.reference_date or "",
        )
        return self.client.execute_df(
            sql,
            query_name="column_cardinality",
            dataset=f"{config.schema}.{config.table}",
            column=col_name,
        )

    def apply_user_overrides(
        self,
        profiles: list[ColumnProfile],
        overrides: dict[str, SemanticType],
    ) -> list[ColumnProfile]:
        """Aplica overrides manuais do usuário."""
        for profile in profiles:
            if profile.column_name in overrides:
                profile.user_override_type = overrides[profile.column_name]
        return profiles
