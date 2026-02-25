"""
Camada D: Geração e recalibração de propostas de regras.

Orquestra statistical_engine + backtest + rule_scoring + gdq_rule_generator
para gerar propostas completas com evidência.

Definido conforme docs/technical_spec_v1.md seção 4.4.
"""

import uuid

import pandas as pd

from core.backtest import backtest_band, backtest_frequency_band
from core.gdq_rule_generator import GDQRuleGenerator
from core.models.baseline import BaselineStrategy
from core.models.enums import (
    BaselineMethod,
    RuleType,
    SemanticType,
)
from core.models.column_profile import ColumnProfile
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import UserOverride
from core.rule_scoring import score_proposal
from core.statistical_engine import (
    compute_dynamic_band,
    compute_frequency_band,
    compute_margin_band,
)


class ProposalService:
    """Geração e recalibração de propostas de regras numéricas e de tabela."""

    def __init__(self):
        self.generator = GDQRuleGenerator()

    def propose_numeric_rules(
        self,
        history: pd.DataFrame,
        column: str,
        table: str,
        baseline: BaselineStrategy,
    ) -> list[RuleProposal]:
        """Gera propostas de regra para coluna numérica.

        Args:
            history: DataFrame do get_numeric_history (com colunas mean, stddev, etc.)
            column: Nome da coluna.
            table: Nome da tabela.
            baseline: Estratégia de baseline.

        Returns:
            Lista de RuleProposal (Mean + StdDev + Completeness).
        """
        proposals = []

        if history.empty:
            return proposals

        # --- Mean Dual Guard ---
        mean_proposal = self._build_dual_guard_proposal(
            series=history["mean"].tolist(),
            dates=history["period"].tolist(),
            column=column,
            table=table,
            rule_type=RuleType.MEAN_DUAL_GUARD,
            metric_name="mean",
            baseline=baseline,
        )
        if mean_proposal:
            proposals.append(mean_proposal)

        # --- StdDev Dual Guard ---
        stddev_values = history["stddev"].tolist()
        # Filtrar NaN de stddev (DuckDB retorna None para grupos com 1 row)
        has_valid_stddev = any(
            v is not None and not (isinstance(v, float) and v != v)
            for v in stddev_values
        )
        if has_valid_stddev:
            stddev_proposal = self._build_dual_guard_proposal(
                series=stddev_values,
                dates=history["period"].tolist(),
                column=column,
                table=table,
                rule_type=RuleType.STDDEV_DUAL_GUARD,
                metric_name="stddev",
                baseline=baseline,
            )
            if stddev_proposal:
                proposals.append(stddev_proposal)

        # --- Completeness ---
        completeness_proposal = self._build_completeness_proposal(
            history=history,
            column=column,
            table=table,
        )
        if completeness_proposal:
            proposals.append(completeness_proposal)

        return proposals

    def propose_table_rules(
        self,
        row_count_history: pd.DataFrame,
        table: str,
        baseline: BaselineStrategy,
        strategy=None,
    ) -> list[RuleProposal]:
        """Gera propostas de regra de tabela (RowCount).

        Args:
            row_count_history: DataFrame de get_row_count_history [period, row_count].
            table: Nome da tabela.
            baseline: Estrategia de baseline.
            strategy: Estrategia customizada (plugin). Default: GenericBandRowCountStrategy.

        Returns:
            Lista de RuleProposal (tipicamente 1 RowCount dual guard).
        """
        if row_count_history.empty:
            return []

        if strategy is None:
            from strategies.row_count_strategy import GenericBandRowCountStrategy
            strategy = GenericBandRowCountStrategy()

        row_counts = row_count_history["row_count"].tolist()
        dates = row_count_history["period"].tolist()

        proposal = strategy.propose(row_counts, dates, table, baseline)
        if proposal is None:
            return []

        return [proposal]

    def propose_categorical_rules(
        self,
        distribution: pd.DataFrame,
        domain: pd.DataFrame,
        column: str,
        table: str,
        profile: ColumnProfile,
        baseline: BaselineStrategy,
    ) -> list[RuleProposal]:
        """Gera propostas de regra para coluna categorica.

        Args:
            distribution: DataFrame [period, category_value, value_count, value_pct]
            domain: DataFrame [category_value, value_count, value_pct]
            column: Nome da coluna.
            table: Nome da tabela.
            profile: ColumnProfile com effective_type.
            baseline: Estrategia de baseline.

        Returns:
            Lista de RuleProposal.
        """
        proposals = []
        if domain.empty:
            return proposals

        effective = profile.effective_type
        domain_values = domain["category_value"].tolist()
        n_distinct = len(domain_values)

        is_low = effective == SemanticType.CATEGORICAL_LOW_CARDINALITY
        is_mid = effective == SemanticType.CATEGORICAL_MID_CARDINALITY

        # --- AllowedValues (CAT_LOW only) ---
        if is_low:
            av_proposal = RuleProposal(
                id=str(uuid.uuid4()),
                target_column=column,
                target_table=table,
                rule_type=RuleType.ALLOWED_VALUES,
                metric_name="allowed_values",
                suggested_values=domain_values,
            )
            av_proposal.gdq_syntax_preview = self.generator.generate(av_proposal)
            proposals.append(av_proposal)

        # --- DistinctValuesCount ---
        if is_low:
            dc_proposal = RuleProposal(
                id=str(uuid.uuid4()),
                target_column=column,
                target_table=table,
                rule_type=RuleType.DISTINCT_COUNT_EXACT,
                metric_name="distinct_count",
                suggested_lower=float(n_distinct),
            )
            dc_proposal.gdq_syntax_preview = self.generator.generate(dc_proposal)
            proposals.append(dc_proposal)
        elif is_mid:
            # Range: +/- 10% or at least +/- 2
            margin = max(int(n_distinct * 0.10), 2)
            dc_proposal = RuleProposal(
                id=str(uuid.uuid4()),
                target_column=column,
                target_table=table,
                rule_type=RuleType.DISTINCT_COUNT_RANGE,
                metric_name="distinct_count_range",
                suggested_lower=float(max(1, n_distinct - margin)),
                suggested_upper=float(n_distinct + margin),
            )
            dc_proposal.gdq_syntax_preview = self.generator.generate(dc_proposal)
            proposals.append(dc_proposal)

        # --- Category Frequency Static (CAT_LOW: all, CAT_MID: top-K) ---
        if (is_low or is_mid) and not distribution.empty:
            values_to_monitor = domain_values if is_low else domain_values[:20]
            for cat_value in values_to_monitor:
                freq_proposal = self._build_frequency_proposal(
                    distribution=distribution,
                    column=column,
                    table=table,
                    cat_value=cat_value,
                    baseline=baseline,
                )
                if freq_proposal:
                    proposals.append(freq_proposal)

        # --- Completeness ---
        if profile.null_ratio <= 0.10:
            completeness = 1.0 - profile.null_ratio
            threshold = round(completeness, 2)
            comp_proposal = RuleProposal(
                id=str(uuid.uuid4()),
                target_column=column,
                target_table=table,
                rule_type=RuleType.COMPLETENESS,
                metric_name="completeness",
                suggested_lower=threshold,
            )
            comp_proposal.gdq_syntax_preview = self.generator.generate(comp_proposal)
            proposals.append(comp_proposal)

        return proposals

    def _build_frequency_proposal(
        self,
        distribution: pd.DataFrame,
        column: str,
        table: str,
        cat_value: str,
        baseline: BaselineStrategy,
    ) -> RuleProposal | None:
        """Constroi proposta de frequencia para um valor categorico."""
        mask = distribution["category_value"] == cat_value
        value_df = distribution[mask].sort_values("period")

        if value_df.empty:
            return None

        pct_series = value_df["value_pct"].tolist()
        dates = value_df["period"].tolist()

        if len(pct_series) < 3:
            return None

        try:
            band = compute_frequency_band(
                pct_series,
                baseline.n_periods,
                margin_pct=baseline.margin_pct * 100,  # convert 0.10 -> 10pp
                n_sigma=baseline.n_sigma,
            )
        except ValueError:
            return None

        proposal = RuleProposal(
            id=str(uuid.uuid4()),
            target_column=column,
            target_table=table,
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            metric_name=f"cat_freq_{cat_value}",
            category_value=cat_value,
            suggested_lower=round(band["lower"], 2),
            suggested_upper=round(band["upper"], 2),
            baseline_method=baseline.method,
            baseline_window=baseline.n_periods,
            baseline_n_sigma=baseline.n_sigma,
            baseline_margin_pct=baseline.margin_pct,
            history_dates=dates,
            history_values=pct_series,
        )

        # Backtest
        proposal.backtest = backtest_frequency_band(
            pct_series=pct_series,
            dates=dates,
            n_periods=baseline.n_periods,
            margin_pct=baseline.margin_pct * 100,
            n_sigma=baseline.n_sigma,
            min_history=baseline.min_history_points,
        )

        # Score
        score = score_proposal(proposal, pct_series)
        proposal.confidence = score.confidence
        proposal.warnings = score.warnings

        # Syntax
        proposal.gdq_syntax_preview = self.generator.generate(proposal)

        return proposal

    def recalculate_proposal(
        self,
        proposal: RuleProposal,
        new_baseline: BaselineStrategy,
    ) -> RuleProposal:
        """Recalcula uma proposta com novos parâmetros de baseline.

        Usado quando o usuário ajusta sliders na UI.
        """
        values = proposal.history_values
        dates = proposal.history_dates

        if not values:
            return proposal

        margin_enabled = new_baseline.margin_enabled

        # Recalcular banda
        try:
            sigma_band = compute_dynamic_band(
                values, new_baseline.n_periods, new_baseline.n_sigma,
            )
            if margin_enabled:
                margin_band = compute_margin_band(
                    values, new_baseline.n_periods, new_baseline.margin_pct,
                )
            else:
                margin_band = sigma_band
        except ValueError:
            return proposal

        proposal.suggested_lower = min(sigma_band["lower"], margin_band["lower"])
        proposal.suggested_upper = max(sigma_band["upper"], margin_band["upper"])
        proposal.baseline_window = new_baseline.n_periods
        proposal.baseline_n_sigma = new_baseline.n_sigma
        proposal.baseline_method = new_baseline.method
        proposal.margin_enabled = margin_enabled

        # Recalcular backtest
        proposal.backtest = backtest_band(
            values=values,
            dates=dates,
            n_periods=new_baseline.n_periods,
            n_sigma=new_baseline.n_sigma,
            margin_pct=new_baseline.margin_pct,
            min_history=new_baseline.min_history_points,
            margin_enabled=margin_enabled,
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
            margin_enabled=margin_enabled,
        )
        proposal.gdq_syntax_preview = self.generator.generate(proposal, overrides)

        return proposal

    def _build_dual_guard_proposal(
        self,
        series: list,
        dates: list[str],
        column: str,
        table: str,
        rule_type: RuleType,
        metric_name: str,
        baseline: BaselineStrategy,
    ) -> RuleProposal | None:
        """Constrói uma proposta dual guard completa com backtest e score."""
        # Filtrar valores válidos (float, não NaN/None)
        clean = []
        for v in series:
            if v is None:
                clean.append(float("nan"))
            elif isinstance(v, (int, float)):
                clean.append(float(v))
            else:
                clean.append(float("nan"))

        margin_enabled = baseline.margin_enabled

        try:
            sigma_band = compute_dynamic_band(
                clean, baseline.n_periods, baseline.n_sigma,
            )
            if margin_enabled:
                margin_band = compute_margin_band(
                    clean, baseline.n_periods, baseline.margin_pct,
                )
            else:
                margin_band = sigma_band  # fallback: same as sigma
        except ValueError:
            return None

        proposal = RuleProposal(
            id=str(uuid.uuid4()),
            target_column=column,
            target_table=table,
            rule_type=rule_type,
            metric_name=metric_name,
            suggested_lower=min(sigma_band["lower"], margin_band["lower"]),
            suggested_upper=max(sigma_band["upper"], margin_band["upper"]),
            baseline_method=baseline.method,
            baseline_window=baseline.n_periods,
            baseline_n_sigma=baseline.n_sigma,
            baseline_margin_pct=baseline.margin_pct,
            margin_enabled=margin_enabled,
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
            margin_enabled=margin_enabled,
        )

        # Score
        score = score_proposal(proposal, clean)
        proposal.confidence = score.confidence
        proposal.warnings = score.warnings

        # Sintaxe GDQ
        proposal.gdq_syntax_preview = self.generator.generate(proposal)

        return proposal

    def _build_completeness_proposal(
        self,
        history: pd.DataFrame,
        column: str,
        table: str,
    ) -> RuleProposal | None:
        """Constrói proposta de Completeness baseada no histórico."""
        total = history["total_count"].sum()
        non_null = history["non_null_count"].sum()
        if total == 0:
            return None

        completeness = non_null / total
        # Só sugerir se completeness >= 0.90
        if completeness < 0.90:
            return None

        threshold = round(completeness, 2)
        proposal = RuleProposal(
            id=str(uuid.uuid4()),
            target_column=column,
            target_table=table,
            rule_type=RuleType.COMPLETENESS,
            metric_name="completeness",
            suggested_lower=threshold,
        )
        proposal.gdq_syntax_preview = self.generator.generate(proposal)
        return proposal
