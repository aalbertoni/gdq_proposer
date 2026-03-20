"""
Gerador de regras GDQ a partir de RuleProposal.

Nível mais alto que o renderer: decide qual tipo de regra gerar
e delega a formatação para DualGuardRenderer.

Definido conforme docs/technical_spec_v1.md seção 8.
"""

from core.gdq_renderer import DualGuardRenderer
from core.models.dual_guard import DualGuardSpec
from core.models.enums import MetricRef, RuleType
from typing import Optional
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import UserOverride


_RULE_TYPE_TO_METRIC = {
    RuleType.MEAN_DUAL_GUARD: MetricRef.MEAN,
    RuleType.STDDEV_DUAL_GUARD: MetricRef.STANDARD_DEVIATION,
    RuleType.ROW_COUNT_DUAL_GUARD: MetricRef.ROW_COUNT,
}


class GDQRuleGenerator:
    """Gera string GDQ a partir de RuleProposal + overrides opcionais."""

    def __init__(self):
        self.renderer = DualGuardRenderer()

    def generate(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None = None,
    ) -> str:
        """Gera sintaxe GDQ para a proposta.

        Args:
            proposal: Proposta de regra com parâmetros.
            overrides: Ajustes manuais do usuário (opcionais).

        Returns:
            String GDQ válida.
        """
        if proposal.rule_type in _RULE_TYPE_TO_METRIC:
            return self._generate_dual_guard(proposal, overrides)
        elif proposal.rule_type == RuleType.COMPLETENESS:
            return self._generate_completeness(proposal, overrides)
        elif proposal.rule_type == RuleType.ALLOWED_VALUES:
            return self._generate_allowed_values(proposal, overrides)
        elif proposal.rule_type == RuleType.DISTINCT_COUNT_EXACT:
            return self._generate_distinct_count(proposal, overrides)
        elif proposal.rule_type == RuleType.IS_PRIMARY_KEY:
            return self._generate_primary_key(proposal)
        elif proposal.rule_type == RuleType.CATEGORY_FREQUENCY_STATIC:
            return self._generate_category_frequency_static(proposal, overrides)
        elif proposal.rule_type == RuleType.CATEGORY_FREQUENCY_DYNAMIC:
            return self._generate_category_frequency_dynamic(proposal, overrides)
        elif proposal.rule_type == RuleType.CATEGORY_FREQUENCY_HYBRID:
            return self._generate_category_frequency_hybrid(proposal, overrides)
        elif proposal.rule_type == RuleType.DISTINCT_COUNT_RANGE:
            return self._generate_distinct_count_range(proposal, overrides)
        elif proposal.rule_type == RuleType.NUMERIC_PERCENTILE_BAND:
            return self._generate_percentile_custom_sql(proposal, overrides)
        elif proposal.rule_type == RuleType.UNIQUENESS_CUSTOM_SQL:
            return self._generate_uniqueness_custom_sql(proposal)
        else:
            raise ValueError(f"Tipo de regra não suportado: {proposal.rule_type}")

    def _generate_dual_guard(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        metric = _RULE_TYPE_TO_METRIC[proposal.rule_type]

        n_periods = proposal.baseline_window or 30
        n_sigma = proposal.baseline_n_sigma or 2.0
        margin_pct = proposal.baseline_margin_pct or 0.10
        margin_enabled = proposal.margin_enabled

        if overrides:
            if overrides.custom_n_periods is not None:
                n_periods = overrides.custom_n_periods
            if overrides.custom_n_sigma is not None:
                n_sigma = overrides.custom_n_sigma
            if overrides.custom_margin_pct is not None:
                margin_pct = overrides.custom_margin_pct
            if overrides.margin_enabled is not None:
                margin_enabled = overrides.margin_enabled

        target = proposal.target_column.upper() if proposal.target_column else ""

        spec = DualGuardSpec(
            metric=metric,
            target=target,
            n_periods=n_periods,
            n_sigma=n_sigma,
            margin_pct=margin_pct,
            margin_enabled=margin_enabled,
        )
        return self.renderer.render(spec)

    def _generate_completeness(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        threshold = proposal.suggested_lower or 1.0
        if overrides and overrides.custom_lower is not None:
            threshold = overrides.custom_lower
        col = proposal.target_column.upper() if proposal.target_column else ""
        return f"Completeness {col} >= {threshold:.2f}"

    def _generate_allowed_values(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        values = proposal.suggested_values or []
        if overrides and overrides.custom_values is not None:
            values = overrides.custom_values
        values_str = ", ".join(self._format_column_value(v) for v in values)
        col = proposal.target_column.upper() if proposal.target_column else ""
        return f"ColumnValues {col} in [{values_str}]"

    @staticmethod
    def _format_column_value(value: str) -> str:
        """Formata valor para ColumnValues: numerico sem aspas, string com aspas, NULL sem aspas."""
        s = str(value)
        if s.upper() == "NULL":
            return "NULL"
        try:
            # Tenta interpretar como numero
            float(s)
            return s
        except (ValueError, TypeError):
            return f"'{s}'"

    def _generate_distinct_count(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        count = int(proposal.suggested_lower) if proposal.suggested_lower else 0
        if overrides and overrides.custom_lower is not None:
            count = int(overrides.custom_lower)
        col = proposal.target_column.upper() if proposal.target_column else ""
        return f"DistinctValuesCount {col} = {count}"

    def _generate_primary_key(self, proposal: RuleProposal) -> str:
        cols = proposal.suggested_values or []
        return f"IsPrimaryKey {' '.join(c.upper() for c in cols)}"

    def _generate_category_frequency_static(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        """CustomSql static frequency for a single category value."""
        col = proposal.target_column
        value = proposal.category_value or ""
        lower = proposal.suggested_lower or 0.0
        upper = proposal.suggested_upper or 100.0
        if overrides:
            if overrides.custom_lower is not None:
                lower = overrides.custom_lower
            if overrides.custom_upper is not None:
                upper = overrides.custom_upper
        athena_type = proposal.target_column_type or "string"
        sql_inner = self._build_custom_sql_expression(col, value, athena_type)
        return f'CustomSql "{sql_inner}" between {lower:.2f} and {upper:.2f}'

    def _build_custom_sql_expression(
        self, col: str, value: str, athena_type: str = "string",
    ) -> str:
        """Constrói a expressão SQL interna do CustomSql frequency.

        Nomes de coluna em MAIUSCULO sem aspas (convencao GDQ).
        Valores: numerico sem aspas, string com aspas simples.
        """
        col_upper = col.upper()
        value_literal = self._format_sql_value(value, athena_type)
        return (
            f"select cast(sum(case when {col_upper} = {value_literal} "
            f"then 1 else 0 end) as double) * 100.0 / count(*) from primary"
        )

    @staticmethod
    def _format_sql_value(value: str, athena_type: str) -> str:
        """Formata valor para SQL: numerico sem aspas, string com aspas simples."""
        from core.column_classifier import ATHENA_NUMERIC_TYPES, _normalize_athena_type
        base_type = _normalize_athena_type(athena_type)
        if base_type in ATHENA_NUMERIC_TYPES:
            return str(value)
        safe_value = value.replace("'", "''")
        return f"'{safe_value}'"

    def _generate_category_frequency_dynamic(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        """CustomSql dynamic frequency com dual guard."""
        col = proposal.target_column
        value = proposal.category_value or ""
        n_periods = proposal.baseline_window or 30
        n_sigma = proposal.baseline_n_sigma or 2.0
        margin_pct = proposal.baseline_margin_pct or 0.10
        margin_enabled = proposal.margin_enabled

        if overrides:
            if overrides.custom_n_periods is not None:
                n_periods = overrides.custom_n_periods
            if overrides.custom_n_sigma is not None:
                n_sigma = overrides.custom_n_sigma
            if overrides.custom_margin_pct is not None:
                margin_pct = overrides.custom_margin_pct
            if overrides.margin_enabled is not None:
                margin_enabled = overrides.margin_enabled

        athena_type = proposal.target_column_type or "string"
        sql_expr = self._build_custom_sql_expression(col, value, athena_type)

        spec = DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            custom_sql_expression=sql_expr,
            n_periods=n_periods,
            n_sigma=n_sigma,
            margin_pct=margin_pct,
            margin_enabled=margin_enabled,
        )
        return self.renderer.render(spec)

    def _generate_category_frequency_hybrid(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        """CustomSql hybrid frequency: dynamic dual guard + absolute floor/ceiling."""
        col = proposal.target_column
        value = proposal.category_value or ""
        n_periods = proposal.baseline_window or 30
        n_sigma = proposal.baseline_n_sigma or 2.0
        margin_pct = proposal.baseline_margin_pct or 0.10
        margin_enabled = proposal.margin_enabled
        floor_pct = proposal.floor_pct if proposal.floor_pct is not None else 0.0
        ceiling_pct = proposal.ceiling_pct if proposal.ceiling_pct is not None else 100.0

        if overrides:
            if overrides.custom_n_periods is not None:
                n_periods = overrides.custom_n_periods
            if overrides.custom_n_sigma is not None:
                n_sigma = overrides.custom_n_sigma
            if overrides.custom_margin_pct is not None:
                margin_pct = overrides.custom_margin_pct
            if overrides.margin_enabled is not None:
                margin_enabled = overrides.margin_enabled
            if overrides.custom_floor_pct is not None:
                floor_pct = overrides.custom_floor_pct
            if overrides.custom_ceiling_pct is not None:
                ceiling_pct = overrides.custom_ceiling_pct

        athena_type = proposal.target_column_type or "string"
        sql_expr = self._build_custom_sql_expression(col, value, athena_type)

        spec = DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            custom_sql_expression=sql_expr,
            n_periods=n_periods,
            n_sigma=n_sigma,
            margin_pct=margin_pct,
            margin_enabled=margin_enabled,
            floor_pct=floor_pct,
            ceiling_pct=ceiling_pct,
        )
        return self.renderer.render(spec)

    def _generate_distinct_count_range(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        """(DistinctValuesCount COL >= X) AND (DistinctValuesCount COL <= Y)."""
        col = proposal.target_column.upper() if proposal.target_column else ""
        lower = int(proposal.suggested_lower) if proposal.suggested_lower else 0
        upper = int(proposal.suggested_upper) if proposal.suggested_upper else 0
        if overrides:
            if overrides.custom_lower is not None:
                lower = int(overrides.custom_lower)
            if overrides.custom_upper is not None:
                upper = int(overrides.custom_upper)
        return (
            f"(DistinctValuesCount {col} >= {lower}) AND "
            f"(DistinctValuesCount {col} <= {upper})"
        )

    def _generate_uniqueness_custom_sql(
        self,
        proposal: RuleProposal,
    ) -> str:
        """CustomSql uniqueness check: COUNT(DISTINCT ...) / COUNT(*) >= 100%.

        Para coluna unica, gera:
            CustomSql "select cast(count(distinct cast(\"COL\" as varchar))
            as double) * 100.0 / count(*) from primary" >= 100.0

        Para chave composta, usa concat com separador '||':
            CustomSql "select cast(count(distinct concat(cast(\"COL1\" as varchar),
            '||', cast(\"COL2\" as varchar))) as double) * 100.0 / count(*)
            from primary" >= 100.0
        """
        cols = proposal.suggested_values or []
        if not cols:
            raise ValueError("UNIQUENESS_CUSTOM_SQL requires suggested_values with column names")

        if len(cols) == 1:
            distinct_expr = f'cast({cols[0].upper()} as varchar)'
        else:
            # concat(cast(COL1 as varchar), '||', cast(COL2 as varchar), ...)
            parts = []
            for col in cols:
                parts.append(f'cast({col.upper()} as varchar)')
            distinct_expr = "concat(" + ", '||', ".join(parts) + ")"

        sql_expr = (
            f'select cast(count(distinct {distinct_expr}) '
            f'as double) * 100.0 / count(*) from primary'
        )
        return f'CustomSql "{sql_expr}" >= 100.0'

    def _generate_percentile_custom_sql(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        """CustomSql dynamic percentile com dual guard."""
        col = proposal.target_column
        pct_value = proposal.suggested_values[0] if proposal.suggested_values else "0.50"
        n_periods = proposal.baseline_window or 30
        n_sigma = proposal.baseline_n_sigma or 2.0
        margin_pct = proposal.baseline_margin_pct or 0.10
        margin_enabled = proposal.margin_enabled

        if overrides:
            if overrides.custom_n_periods is not None:
                n_periods = overrides.custom_n_periods
            if overrides.custom_n_sigma is not None:
                n_sigma = overrides.custom_n_sigma
            if overrides.custom_margin_pct is not None:
                margin_pct = overrides.custom_margin_pct
            if overrides.margin_enabled is not None:
                margin_enabled = overrides.margin_enabled

        col_upper = col.upper() if col else ""
        sql_expr = (
            f'select approx_percentile(cast({col_upper} as double), {pct_value}) from primary'
        )

        spec = DualGuardSpec(
            metric=MetricRef.CUSTOM_SQL,
            custom_sql_expression=sql_expr,
            n_periods=n_periods,
            n_sigma=n_sigma,
            margin_pct=margin_pct,
            margin_enabled=margin_enabled,
        )
        return self.renderer.render(spec)
