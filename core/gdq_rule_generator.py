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

        target = proposal.target_column or ""

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
        return f"Completeness {proposal.target_column} >= {threshold:.2f}"

    def _generate_allowed_values(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        values = proposal.suggested_values or []
        if overrides and overrides.custom_values is not None:
            values = overrides.custom_values
        values_str = ", ".join(str(v) for v in values)
        return f"ColumnValues {proposal.target_column} in [{values_str}]"

    def _generate_distinct_count(
        self,
        proposal: RuleProposal,
        overrides: UserOverride | None,
    ) -> str:
        count = int(proposal.suggested_lower) if proposal.suggested_lower else 0
        if overrides and overrides.custom_lower is not None:
            count = int(overrides.custom_lower)
        return f"DistinctValuesCount {proposal.target_column} = {count}"

    def _generate_primary_key(self, proposal: RuleProposal) -> str:
        cols = proposal.suggested_values or []
        return f"IsPrimaryKey {' '.join(cols)}"

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
        sql_inner = (
            f"select cast(sum(case when {col} = '{value}' "
            f"then 1 else 0 end) as double) * 100.0 / count(*) from primary"
        )
        return f'CustomSql "{sql_inner}" between {lower:.2f} and {upper:.2f}'

    def _build_custom_sql_expression(self, col: str, value: str) -> str:
        """Constrói a expressão SQL interna do CustomSql frequency."""
        return (
            f"select cast(sum(case when {col} = '{value}' "
            f"then 1 else 0 end) as double) * 100.0 / count(*) from primary"
        )

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

        sql_expr = self._build_custom_sql_expression(col, value)

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

        sql_expr = self._build_custom_sql_expression(col, value)

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
        col = proposal.target_column
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
