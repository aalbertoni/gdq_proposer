"""
Estrategia de RowCount: Protocol + implementacao GenericBand.

O Protocol permite que clientes enterprise pluguem estrategias customizadas.
A GenericBandRowCountStrategy e o default: dual guard (sigma OR margem%).

Definido conforme docs/technical_spec_v1.md Sprint B1.
"""

import uuid
from typing import Protocol, runtime_checkable

from core.backtest import backtest_band
from core.gdq_rule_generator import GDQRuleGenerator
from core.models.baseline import BaselineStrategy
from core.models.enums import BaselineMethod, RuleType
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import UserOverride
from core.rule_scoring import score_proposal
from core.statistical_engine import compute_dynamic_band, compute_margin_band


@runtime_checkable
class RowCountStrategy(Protocol):
    """Protocol para estrategias de geracao de regras RowCount.

    Permite que clientes enterprise implementem estrategias customizadas
    enquanto o GenericBand permanece como default.
    """

    def propose(
        self,
        row_counts: list[float],
        dates: list[str],
        table: str,
        baseline: BaselineStrategy,
    ) -> RuleProposal | None:
        """Gera proposta de RowCount a partir de contagens historicas.

        Args:
            row_counts: Valores de row count por periodo.
            dates: Datas correspondentes.
            table: Nome da tabela alvo.
            baseline: Parametros de baseline.

        Returns:
            RuleProposal com ROW_COUNT_DUAL_GUARD, ou None se dados insuficientes.
        """
        ...

    def recalculate(
        self,
        proposal: RuleProposal,
        new_baseline: BaselineStrategy,
    ) -> RuleProposal:
        """Recalcula proposta com novos parametros de baseline."""
        ...


class GenericBandRowCountStrategy:
    """Estrategia default: dual guard (sigma OR margem%) para RowCount."""

    def __init__(self):
        self.generator = GDQRuleGenerator()

    def propose(
        self,
        row_counts: list[float],
        dates: list[str],
        table: str,
        baseline: BaselineStrategy,
    ) -> RuleProposal | None:
        """Gera proposta RowCount com backtest, score e sintaxe GDQ."""
        # Limpar valores
        clean = []
        for v in row_counts:
            if v is None:
                clean.append(float("nan"))
            elif isinstance(v, (int, float)):
                clean.append(float(v))
            else:
                clean.append(float("nan"))

        try:
            sigma_band = compute_dynamic_band(
                clean, baseline.n_periods, baseline.n_sigma,
            )
            margin_band = compute_margin_band(
                clean, baseline.n_periods, baseline.margin_pct,
            )
        except ValueError:
            return None

        proposal = RuleProposal(
            id=str(uuid.uuid4()),
            target_column=None,
            target_table=table,
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            metric_name="row_count",
            suggested_lower=min(sigma_band["lower"], margin_band["lower"]),
            suggested_upper=max(sigma_band["upper"], margin_band["upper"]),
            baseline_method=baseline.method,
            baseline_window=baseline.n_periods,
            baseline_n_sigma=baseline.n_sigma,
            baseline_margin_pct=baseline.margin_pct,
            history_dates=dates,
            history_values=clean,
        )

        # Backtest
        proposal.backtest = backtest_band(
            values=clean,
            dates=dates,
            n_periods=baseline.n_periods,
            n_sigma=baseline.n_sigma,
            margin_pct=baseline.margin_pct,
            min_history=baseline.min_history_points,
        )

        # Score
        score = score_proposal(proposal, clean)
        proposal.confidence = score.confidence
        proposal.warnings = score.warnings

        # Sintaxe GDQ
        proposal.gdq_syntax_preview = self.generator.generate(proposal)

        return proposal

    def recalculate(
        self,
        proposal: RuleProposal,
        new_baseline: BaselineStrategy,
    ) -> RuleProposal:
        """Recalcula proposta RowCount com novos parametros."""
        values = proposal.history_values
        dates = proposal.history_dates

        if not values:
            return proposal

        try:
            sigma_band = compute_dynamic_band(
                values, new_baseline.n_periods, new_baseline.n_sigma,
            )
            margin_band = compute_margin_band(
                values, new_baseline.n_periods, new_baseline.margin_pct,
            )
        except ValueError:
            return proposal

        proposal.suggested_lower = min(sigma_band["lower"], margin_band["lower"])
        proposal.suggested_upper = max(sigma_band["upper"], margin_band["upper"])
        proposal.baseline_window = new_baseline.n_periods
        proposal.baseline_n_sigma = new_baseline.n_sigma
        proposal.baseline_method = new_baseline.method

        # Recalcular backtest
        proposal.backtest = backtest_band(
            values=values,
            dates=dates,
            n_periods=new_baseline.n_periods,
            n_sigma=new_baseline.n_sigma,
            margin_pct=new_baseline.margin_pct,
            min_history=new_baseline.min_history_points,
        )

        # Recalcular score
        score = score_proposal(proposal, values)
        proposal.confidence = score.confidence
        proposal.warnings = score.warnings

        proposal.baseline_margin_pct = new_baseline.margin_pct

        # Regenerar sintaxe
        overrides = UserOverride(
            custom_n_periods=new_baseline.n_periods,
            custom_n_sigma=new_baseline.n_sigma,
            custom_margin_pct=new_baseline.margin_pct,
        )
        proposal.gdq_syntax_preview = self.generator.generate(proposal, overrides)

        return proposal
