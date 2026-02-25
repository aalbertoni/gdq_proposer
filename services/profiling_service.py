"""
Camada B: Column Classification.

Executa profiling de colunas via Athena (ou DuckDB mock) e
usa o column_classifier para inferir o tipo semântico.

Definido conforme docs/technical_spec_v1.md seção 4.2.
"""

from core.column_classifier import classify_column
from core.models.column_profile import ColumnProfile
from core.models.dataset_config import DatasetConfig
from core.models.enums import SemanticType
from infra.athena_client import AthenaClient
from infra.query_builder import QueryBuilder
from infra.query_safety import validate_identifier, sanitize_filter


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
                sample_periods=sample_periods,
            )
            profiles.append(profile)

        return profiles

    def _profile_single_column(
        self,
        config: DatasetConfig,
        col_name: str,
        athena_type: str,
        temporal_col: str,
        base_filter: str,
        sample_periods: int,
    ) -> ColumnProfile:
        """Faz profiling de uma coluna individual.

        Para tipos nativos numéricos/data, classifica direto sem query.
        Para strings, executa query de amostragem para obter métricas.
        """
        from core.column_classifier import (
            ATHENA_DATE_TYPES,
            ATHENA_NUMERIC_TYPES,
            _normalize_athena_type,
        )

        normalized = _normalize_athena_type(athena_type)

        # Camada 1: tipo nativo não precisa de query
        if normalized in ATHENA_NUMERIC_TYPES or normalized in ATHENA_DATE_TYPES:
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

        # Camada 2+3: strings precisam de query para métricas
        return self._profile_string_column(
            config=config,
            col_name=col_name,
            athena_type=athena_type,
            temporal_col=temporal_col,
            base_filter=base_filter,
            sample_periods=sample_periods,
        )

    def _profile_string_column(
        self,
        config: DatasetConfig,
        col_name: str,
        athena_type: str,
        temporal_col: str,
        base_filter: str,
        sample_periods: int,
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

    def apply_user_overrides(
        self,
        profiles: list[ColumnProfile],
        overrides: dict[str, SemanticType],
    ) -> list[ColumnProfile]:
        """Aplica overrides manuais do usuário.

        Args:
            profiles: Lista de ColumnProfile existentes.
            overrides: Dict de {column_name: SemanticType} com overrides.

        Returns:
            Lista de ColumnProfile com overrides aplicados.
        """
        for profile in profiles:
            if profile.column_name in overrides:
                profile.user_override_type = overrides[profile.column_name]
        return profiles
