"""
Gerador de regras GDQ a partir de RuleProposal.

Nível mais alto que o renderer: decide qual tipo de regra gerar
e delega a formatação para DualGuardRenderer.

Definido conforme docs/technical_spec_v1.md seção 8.
"""

from core.gdq_renderer import DualGuardRenderer
from core.models.dual_guard import DualGuardSpec
from core.models.enums import MetricRef, RuleType
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
        margin_pct = 0.10

        if overrides:
            if overrides.custom_n_periods is not None:
                n_periods = overrides.custom_n_periods
            if overrides.custom_n_sigma is not None:
                n_sigma = overrides.custom_n_sigma

        target = proposal.target_column or ""

        spec = DualGuardSpec(
            metric=metric,
            target=target,
            n_periods=n_periods,
            n_sigma=n_sigma,
            margin_pct=margin_pct,
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
