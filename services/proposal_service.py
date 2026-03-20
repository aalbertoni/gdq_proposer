"""
Camada D: Geração e recalibração de propostas de regras.

Orquestra statistical_engine + backtest + rule_scoring + gdq_rule_generator
para gerar propostas completas com evidência.

Definido conforme docs/technical_spec_v1.md seção 4.4.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, TypedDict

if TYPE_CHECKING:
    from strategies.row_count_strategy import RowCountStrategy

import pandas as pd

from core.backtest import (
    backtest_allowed_values,
    backtest_band,
    backtest_distinct_count_exact,
    backtest_distinct_count_range,
    backtest_frequency_band,
    backtest_frequency_dual_guard,
    backtest_primary_key,
)
from core.gdq_rule_generator import GDQRuleGenerator
from core.models.baseline import BaselineStrategy
from core.models.enums import (
    BaselineMethod,
    ConfidenceLevel,
    RuleType,
    SemanticType,
)
from core.models.column_profile import ColumnProfile
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import UserOverride
from core.rule_recommender import recommend_tier
from core.rule_scoring import score_proposal
from core.statistical_engine import (
    compute_dynamic_band,
    compute_frequency_band,
    compute_iqr_band,
    compute_mad_band,
    compute_margin_band,
    detect_change_points,
    detect_drift,
    detect_outliers,
    detect_seasonality,
)


class AutoTuneResult(TypedDict, total=False):
    """Resultado do grid search de auto-tune (find_best_params).

    Campos sempre presentes: n_periods, n_sigma, margin_pct, margin_enabled,
    coverage_pct, weighted_coverage_pct, false_positives, stability, score_total.

    Campos de breakdown do score (sempre presentes quando score_total > 0):
    normal_coverage, outlier_penalty, fp_penalty, stability_bonus, width_penalty,
    drift_bonus, n_penalty, sigma_preference, margin_preference, recency_bonus.

    Outlier-aware scoring: o auto-tune detecta outliers via IQR (2.5x) e
    maximiza cobertura de pontos normais enquanto penaliza cobrir outliers.

    Campos adicionados apos avaliacao: confidence, viable, recommendation.
    """

    n_periods: int
    n_sigma: float
    margin_pct: float
    margin_enabled: bool
    coverage_pct: float
    weighted_coverage_pct: float
    false_positives: int
    stability: float
    score_total: float
    # Score breakdown components
    normal_coverage: float
    outlier_penalty: float
    fp_penalty: float
    stability_bonus: float
    width_penalty: float
    drift_bonus: float
    n_penalty: float
    sigma_preference: float
    margin_preference: float
    recency_bonus: float
    band_width_ratio: float
    outliers_detected: int
    outliers_covered: int
    confidence: "ConfidenceLevel"
    viable: bool
    recommendation: str


class ProposalService:
    """Geração e recalibração de propostas de regras numéricas e de tabela."""

    def __init__(self):
        self.generator = GDQRuleGenerator()

    @staticmethod
    def _apply_recommendations(
        proposals: list[RuleProposal],
        profile: "SeriesProfile | None" = None,
    ) -> list[RuleProposal]:
        """Aplica recommend_tier a todas as propostas."""
        for p in proposals:
            tier, reasons = recommend_tier(p, profile)
            p.recommendation_tier = tier
            p.recommendation_reasons = reasons
        return proposals

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

        return self._apply_recommendations(proposals)

    def propose_table_rules(
        self,
        row_count_history: pd.DataFrame,
        table: str,
        baseline: BaselineStrategy,
        strategy: Optional["RowCountStrategy"] = None,
    ) -> list[RuleProposal]:
        """Gera propostas de regra de tabela (RowCount)."""
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

        return self._apply_recommendations([proposal])

    def propose_categorical_rules(
        self,
        distribution: pd.DataFrame,
        domain: pd.DataFrame,
        column: str,
        table: str,
        profile: ColumnProfile,
        baseline: BaselineStrategy,
        freq_mode: str = "static",
        freq_mode_overrides: dict[str, str] | None = None,
        floor_pct: float | None = None,
        ceiling_pct: float | None = None,
        max_frequency_rules: int = 5,
        distinct_count_history: pd.DataFrame | None = None,
    ) -> list[RuleProposal]:
        """Gera propostas de regra para coluna categorica.

        Args:
            distribution: DataFrame [period, category_value, value_count, value_pct]
            domain: DataFrame [category_value, value_count, value_pct]
            column: Nome da coluna.
            table: Nome da tabela.
            profile: ColumnProfile com effective_type.
            baseline: Estrategia de baseline.
            freq_mode: "static", "dynamic" ou "hybrid" (default global).
            freq_mode_overrides: Mapa {valor: modo} para overrides individuais.
            floor_pct: Limite inferior absoluto (modo hibrido, 0-100).
            ceiling_pct: Limite superior absoluto (modo hibrido, 0-100).
            max_frequency_rules: Máximo de regras de frequência por coluna (default 5).
            distinct_count_history: DataFrame [period, distinct_count, total_count,
                non_null_count] para backtest de AllowedValues/DistinctCount/Completeness.
                Quando fornecido, as propostas recebem backtest e scoring.
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
                target_column_type=profile.athena_type,
            )
            # Backtest: check if all observed values per period are in allowed set
            if distinct_count_history is not None and not distribution.empty:
                period_values_map = self._build_period_values_map(distribution)
                allowed_set = set(str(v) for v in domain_values)
                av_proposal.backtest = backtest_allowed_values(
                    period_values_map, allowed_set,
                )
                sorted_periods = sorted(period_values_map.keys())
                av_proposal.history_dates = sorted_periods
                av_proposal.history_values = [
                    1.0 if not (period_values_map[p] - allowed_set) else 0.0
                    for p in sorted_periods
                ]
                av_score = score_proposal(av_proposal, av_proposal.history_values)
                av_proposal.confidence = av_score.confidence
                av_proposal.warnings = av_score.warnings
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
            # Backtest: check if distinct_count == expected in each period
            if distinct_count_history is not None and not distinct_count_history.empty:
                dc_counts = distinct_count_history["distinct_count"].tolist()
                dc_dates = [str(d) for d in distinct_count_history["period"].tolist()]
                dc_proposal.backtest = backtest_distinct_count_exact(
                    dc_counts, dc_dates, n_distinct,
                )
                dc_proposal.history_dates = dc_dates
                dc_proposal.history_values = [float(c) for c in dc_counts]
                dc_score = score_proposal(dc_proposal, dc_proposal.history_values)
                dc_proposal.confidence = dc_score.confidence
                dc_proposal.warnings = dc_score.warnings
            dc_proposal.gdq_syntax_preview = self.generator.generate(dc_proposal)
            proposals.append(dc_proposal)
        elif is_mid:
            # Range: +/- 10% or at least +/- 2
            margin = max(int(n_distinct * 0.10), 2)
            lower_bound = max(1, n_distinct - margin)
            upper_bound = n_distinct + margin
            dc_proposal = RuleProposal(
                id=str(uuid.uuid4()),
                target_column=column,
                target_table=table,
                rule_type=RuleType.DISTINCT_COUNT_RANGE,
                metric_name="distinct_count_range",
                suggested_lower=float(lower_bound),
                suggested_upper=float(upper_bound),
            )
            # Backtest: check if distinct_count in [lower, upper] each period
            if distinct_count_history is not None and not distinct_count_history.empty:
                dc_counts = distinct_count_history["distinct_count"].tolist()
                dc_dates = [str(d) for d in distinct_count_history["period"].tolist()]
                dc_proposal.backtest = backtest_distinct_count_range(
                    dc_counts, dc_dates, lower_bound, upper_bound,
                )
                dc_proposal.history_dates = dc_dates
                dc_proposal.history_values = [float(c) for c in dc_counts]
                dc_score = score_proposal(dc_proposal, dc_proposal.history_values)
                dc_proposal.confidence = dc_score.confidence
                dc_proposal.warnings = dc_score.warnings
            dc_proposal.gdq_syntax_preview = self.generator.generate(dc_proposal)
            proposals.append(dc_proposal)

        # --- Category Frequency (static / dynamic / hybrid) ---
        # Guardrail: limita ao max_frequency_rules, priorizando por frequência
        if (is_low or is_mid) and not distribution.empty:
            values_to_monitor = domain_values[:max_frequency_rules]
            for cat_value in values_to_monitor:
                # Per-value mode override
                effective_mode = freq_mode
                if freq_mode_overrides and cat_value in freq_mode_overrides:
                    effective_mode = freq_mode_overrides[cat_value]

                freq_proposal = self._build_frequency_proposal(
                    distribution=distribution,
                    column=column,
                    table=table,
                    cat_value=cat_value,
                    baseline=baseline,
                    freq_mode=effective_mode,
                    floor_pct=floor_pct,
                    ceiling_pct=ceiling_pct,
                    athena_type=profile.athena_type,
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
            # Add history from distinct_count_history if available
            if distinct_count_history is not None and not distinct_count_history.empty:
                comp_dates = [str(d) for d in distinct_count_history["period"].tolist()]
                comp_total = distinct_count_history["total_count"].tolist()
                comp_non_null = distinct_count_history["non_null_count"].tolist()
                comp_values = []
                for nn, tot in zip(comp_non_null, comp_total):
                    if tot and tot > 0:
                        comp_values.append(round(float(nn) / float(tot) * 100, 2))
                    else:
                        comp_values.append(0.0)
                comp_proposal.history_dates = comp_dates
                comp_proposal.history_values = comp_values
            comp_proposal.gdq_syntax_preview = self.generator.generate(comp_proposal)
            proposals.append(comp_proposal)

        return self._apply_recommendations(proposals)

    def propose_percentile_rules(
        self,
        history: pd.DataFrame,
        column: str,
        table: str,
        baseline: BaselineStrategy,
        percentile_levels: list[str] | None = None,
    ) -> list[RuleProposal]:
        """Gera propostas de regra de percentil via CustomSql dual guard.

        Args:
            history: DataFrame do get_numeric_history (com colunas p01..p99).
            column: Nome da coluna.
            table: Nome da tabela.
            baseline: Estratégia de baseline.
            percentile_levels: Lista de colunas de percentil (ex: ["p10", "p90"]).

        Returns:
            Lista de RuleProposal com tipo NUMERIC_PERCENTILE_BAND.
        """
        if percentile_levels is None:
            percentile_levels = ["p10", "p90"]

        proposals = []
        if history.empty:
            return proposals

        pct_map = {
            "p01": 0.01, "p05": 0.05, "p10": 0.10, "p25": 0.25,
            "p50": 0.50, "p75": 0.75, "p90": 0.90, "p95": 0.95, "p99": 0.99,
        }

        for pct_col in percentile_levels:
            if pct_col not in history.columns:
                continue
            pct_value = pct_map.get(pct_col)
            if pct_value is None:
                continue

            pct_series = history[pct_col].tolist()
            dates = history["period"].tolist()

            proposal = self._build_percentile_proposal(
                series=pct_series,
                dates=dates,
                column=column,
                table=table,
                pct_col=pct_col,
                pct_value=pct_value,
                baseline=baseline,
            )
            if proposal:
                proposals.append(proposal)

        return self._apply_recommendations(proposals)

    def _build_percentile_proposal(
        self,
        series: list,
        dates: list[str],
        column: str,
        table: str,
        pct_col: str,
        pct_value: float,
        baseline: BaselineStrategy,
    ) -> RuleProposal | None:
        """Constrói proposta de percentil via CustomSql dual guard."""
        # Filtrar NaN
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
                margin_band = sigma_band
        except ValueError:
            return None

        pct_label = pct_col.upper()  # "p10" -> "P10"

        proposal = RuleProposal(
            id=str(uuid.uuid4()),
            target_column=column,
            target_table=table,
            rule_type=RuleType.NUMERIC_PERCENTILE_BAND,
            metric_name=pct_col,
            suggested_lower=min(sigma_band["lower"], margin_band["lower"]),
            suggested_upper=max(sigma_band["upper"], margin_band["upper"]),
            suggested_values=[str(pct_value)],  # percentile fraction for inner SQL
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

    def propose_primary_key_rules(
        self,
        uniqueness_history: pd.DataFrame,
        key_columns: list[str],
        table: str,
    ) -> list[RuleProposal]:
        """Gera propostas de regra de chave primaria (IsPrimaryKey / UNIQUENESS_CUSTOM_SQL).

        Analisa o historico de unicidade para determinar se as colunas candidatas
        formam uma chave primaria valida. Gera IsPrimaryKey quando nao ha duplicatas
        nem nulls, UNIQUENESS_CUSTOM_SQL quando ha nulls mas nao duplicatas,
        ou um alerta LOW quando ha duplicatas.

        Args:
            uniqueness_history: DataFrame com colunas [period, total_rows,
                distinct_keys, duplicate_count, non_null_{col}...].
            key_columns: Lista de colunas candidatas a chave primaria.
            table: Nome da tabela.

        Returns:
            Lista de RuleProposal (IsPrimaryKey e/ou UNIQUENESS_CUSTOM_SQL
            e/ou Completeness para colunas com nulls).
        """
        if uniqueness_history is None or uniqueness_history.empty or not key_columns:
            return []

        proposals: list[RuleProposal] = []

        # Extract arrays from DataFrame
        total_rows = uniqueness_history["total_rows"].tolist()
        distinct_keys = uniqueness_history["distinct_keys"].tolist()
        duplicate_counts = uniqueness_history["duplicate_count"].tolist()
        dates = [str(d) for d in uniqueness_history["period"].tolist()]

        # Build null_counts_per_col
        null_counts_per_col: dict[str, list[int]] = {}
        for col in key_columns:
            non_null_col = f"non_null_{col}"
            if non_null_col in uniqueness_history.columns:
                non_null_vals = uniqueness_history[non_null_col].tolist()
                null_counts_per_col[col] = [
                    int(tr) - int(nn)
                    for tr, nn in zip(total_rows, non_null_vals)
                ]
            else:
                # Assume no nulls if column not in history
                null_counts_per_col[col] = [0] * len(total_rows)

        # Backtest
        bt_total_rows = [int(r) for r in total_rows]
        bt_distinct_keys = [int(k) for k in distinct_keys]
        backtest_result = backtest_primary_key(
            bt_total_rows, bt_distinct_keys, null_counts_per_col, dates,
        )

        # Determine recommendation
        has_duplicates = any(int(d) > 0 for d in duplicate_counts)
        has_nulls = any(
            any(nc > 0 for nc in null_list)
            for null_list in null_counts_per_col.values()
        )

        # History values: duplicate counts per period (for visualization)
        history_values_dup = [float(d) for d in duplicate_counts]

        if not has_duplicates and not has_nulls:
            # Recommend IsPrimaryKey
            pk_proposal = RuleProposal(
                id=str(uuid.uuid4()),
                target_column=None,
                target_table=table,
                rule_type=RuleType.IS_PRIMARY_KEY,
                metric_name="is_primary_key",
                suggested_values=key_columns,
                history_dates=dates,
                history_values=history_values_dup,
                backtest=backtest_result,
            )
            pk_proposal.gdq_syntax_preview = self.generator.generate(pk_proposal)
            pk_score = score_proposal(pk_proposal, history_values_dup)
            pk_proposal.confidence = pk_score.confidence
            pk_proposal.warnings = pk_score.warnings
            proposals.append(pk_proposal)

        elif not has_duplicates and has_nulls:
            # Recommend UNIQUENESS_CUSTOM_SQL (no duplicates but nulls prevent IsPrimaryKey)
            uq_proposal = RuleProposal(
                id=str(uuid.uuid4()),
                target_column=None,
                target_table=table,
                rule_type=RuleType.UNIQUENESS_CUSTOM_SQL,
                metric_name="uniqueness_custom_sql",
                suggested_values=key_columns,
                history_dates=dates,
                history_values=history_values_dup,
                backtest=backtest_result,
            )
            uq_proposal.gdq_syntax_preview = self.generator.generate(uq_proposal)
            uq_score = score_proposal(uq_proposal, history_values_dup)
            uq_proposal.confidence = uq_score.confidence
            uq_proposal.warnings = uq_score.warnings
            uq_proposal.warnings.append(
                "Colunas PK contêm nulls — IsPrimaryKey não aplicável, "
                "usando CustomSql COUNT(DISTINCT) como alternativa"
            )
            proposals.append(uq_proposal)

            # Also create Completeness proposals for columns with nulls
            for col in key_columns:
                col_null_counts = null_counts_per_col.get(col, [])
                col_has_nulls = any(nc > 0 for nc in col_null_counts)
                if col_has_nulls:
                    # Compute overall completeness for this column
                    total_all = sum(int(r) for r in total_rows)
                    null_all = sum(col_null_counts)
                    if total_all > 0:
                        comp_ratio = (total_all - null_all) / total_all
                        comp_proposal = RuleProposal(
                            id=str(uuid.uuid4()),
                            target_column=col,
                            target_table=table,
                            rule_type=RuleType.COMPLETENESS,
                            metric_name="completeness",
                            suggested_lower=round(comp_ratio, 2),
                            history_dates=dates,
                            history_values=[
                                round((float(tr) - float(nc)) / float(tr) * 100, 2)
                                if float(tr) > 0 else 0.0
                                for tr, nc in zip(total_rows, col_null_counts)
                            ],
                        )
                        comp_proposal.gdq_syntax_preview = self.generator.generate(
                            comp_proposal
                        )
                        comp_proposal.warnings.append(
                            f"Coluna PK '{col}' contém nulls — considere corrigir os dados"
                        )
                        proposals.append(comp_proposal)

        else:
            # has_duplicates: warning-only proposal with LOW confidence
            warn_proposal = RuleProposal(
                id=str(uuid.uuid4()),
                target_column=None,
                target_table=table,
                rule_type=RuleType.IS_PRIMARY_KEY,
                metric_name="is_primary_key",
                suggested_values=key_columns,
                confidence=ConfidenceLevel.LOW,
                history_dates=dates,
                history_values=history_values_dup,
                backtest=backtest_result,
            )
            # Generate syntax for reference, even though not recommended
            warn_proposal.gdq_syntax_preview = self.generator.generate(warn_proposal)
            max_dup = max(int(d) for d in duplicate_counts)
            dup_periods = sum(1 for d in duplicate_counts if int(d) > 0)
            warn_proposal.warnings = [
                f"Duplicatas detectadas em {dup_periods}/{len(duplicate_counts)} períodos "
                f"(máx {max_dup} duplicatas) — IsPrimaryKey não recomendado",
                "Verifique se as colunas selecionadas realmente formam a chave primária",
            ]
            proposals.append(warn_proposal)

        return self._apply_recommendations(proposals)

    def _build_period_values_map(
        self,
        distribution: pd.DataFrame,
    ) -> dict[str, set[str]]:
        """Constroi mapa de periodo -> conjunto de valores observados.

        Args:
            distribution: DataFrame [period, category_value, value_count, value_pct].

        Returns:
            Dict mapeando cada periodo para o set de valores categoricos observados.
        """
        period_values_map: dict[str, set[str]] = {}
        for _, row in distribution.iterrows():
            period = str(row["period"])
            value = str(row["category_value"])
            if period not in period_values_map:
                period_values_map[period] = set()
            period_values_map[period].add(value)
        return period_values_map

    def _build_frequency_proposal(
        self,
        distribution: pd.DataFrame,
        column: str,
        table: str,
        cat_value: str,
        baseline: BaselineStrategy,
        freq_mode: str = "static",
        floor_pct: float | None = None,
        ceiling_pct: float | None = None,
        athena_type: str = "string",
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

        # Determine rule type based on mode
        if freq_mode == "dynamic":
            rule_type = RuleType.CATEGORY_FREQUENCY_DYNAMIC
        elif freq_mode == "hybrid":
            rule_type = RuleType.CATEGORY_FREQUENCY_HYBRID
        else:
            rule_type = RuleType.CATEGORY_FREQUENCY_STATIC

        proposal = RuleProposal(
            id=str(uuid.uuid4()),
            target_column=column,
            target_table=table,
            rule_type=rule_type,
            metric_name=f"cat_freq_{cat_value}",
            category_value=cat_value,
            target_column_type=athena_type,
            suggested_lower=round(band["lower"], 2),
            suggested_upper=round(band["upper"], 2),
            baseline_method=baseline.method,
            baseline_window=baseline.n_periods,
            baseline_n_sigma=baseline.n_sigma,
            baseline_margin_pct=baseline.margin_pct,
            margin_enabled=baseline.margin_enabled,
            history_dates=dates,
            history_values=pct_series,
        )

        if rule_type == RuleType.CATEGORY_FREQUENCY_HYBRID:
            proposal.floor_pct = floor_pct if floor_pct is not None else 0.0
            proposal.ceiling_pct = ceiling_pct if ceiling_pct is not None else 100.0

        # Backtest
        if freq_mode == "static":
            proposal.backtest = backtest_frequency_band(
                pct_series=pct_series,
                dates=dates,
                n_periods=baseline.n_periods,
                margin_pct=baseline.margin_pct * 100,
                n_sigma=baseline.n_sigma,
                min_history=baseline.min_history_points,
            )
        else:
            proposal.backtest = backtest_frequency_dual_guard(
                pct_series=pct_series,
                dates=dates,
                n_periods=baseline.n_periods,
                n_sigma=baseline.n_sigma,
                margin_pct=baseline.margin_pct,
                buffer=0.01,
                min_history=baseline.min_history_points,
                margin_enabled=baseline.margin_enabled,
                floor_pct=floor_pct if freq_mode == "hybrid" else None,
                ceiling_pct=ceiling_pct if freq_mode == "hybrid" else None,
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

        Suporta todos os tipos de regra: numeric dual guard, percentile,
        frequency (static/dynamic/hybrid). Static frequency não recalcula
        (valores são fixos).
        """
        values = proposal.history_values
        dates = proposal.history_dates

        if not values:
            return proposal

        margin_enabled = new_baseline.margin_enabled

        # Frequency modes
        if proposal.rule_type in (
            RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            RuleType.CATEGORY_FREQUENCY_HYBRID,
        ):
            return self._recalculate_frequency(proposal, new_baseline)
        elif proposal.rule_type == RuleType.CATEGORY_FREQUENCY_STATIC:
            # Static: valores fixos, não recalcula
            return proposal

        # Numeric / percentile / row count dual guard
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

    def _recalculate_frequency(
        self,
        proposal: RuleProposal,
        new_baseline: BaselineStrategy,
    ) -> RuleProposal:
        """Recalcula proposta de frequência (dynamic/hybrid)."""
        pct_series = proposal.history_values
        dates = proposal.history_dates
        margin_enabled = new_baseline.margin_enabled

        try:
            band = compute_frequency_band(
                pct_series,
                new_baseline.n_periods,
                margin_pct=new_baseline.margin_pct * 100,
                n_sigma=new_baseline.n_sigma,
            )
        except ValueError:
            return proposal

        proposal.suggested_lower = round(band["lower"], 2)
        proposal.suggested_upper = round(band["upper"], 2)
        proposal.baseline_window = new_baseline.n_periods
        proposal.baseline_n_sigma = new_baseline.n_sigma
        proposal.baseline_method = new_baseline.method
        proposal.baseline_margin_pct = new_baseline.margin_pct
        proposal.margin_enabled = margin_enabled

        # Backtest
        proposal.backtest = backtest_frequency_dual_guard(
            pct_series=pct_series,
            dates=dates,
            n_periods=new_baseline.n_periods,
            n_sigma=new_baseline.n_sigma,
            margin_pct=new_baseline.margin_pct,
            buffer=0.01,
            min_history=new_baseline.min_history_points,
            margin_enabled=margin_enabled,
            floor_pct=proposal.floor_pct if proposal.rule_type == RuleType.CATEGORY_FREQUENCY_HYBRID else None,
            ceiling_pct=proposal.ceiling_pct if proposal.rule_type == RuleType.CATEGORY_FREQUENCY_HYBRID else None,
        )

        # Score
        score = score_proposal(proposal, pct_series)
        proposal.confidence = score.confidence
        proposal.warnings = score.warnings

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

        # Detect seasonality (uses full series)
        seasonality = detect_seasonality(clean, dates)

        # Detect change points (uses full series)
        change_info = detect_change_points(clean, dates)

        # If change point detected, use only post-change values for band computation
        effective_values = clean
        effective_dates = dates
        effective_n = baseline.n_periods
        if change_info["has_change_point"] and len(change_info["post_change_values"]) >= 5:
            effective_values = change_info["post_change_values"]
            effective_dates = change_info["post_change_dates"]
            # Adjust n_periods to not exceed available data
            effective_n = min(baseline.n_periods, len(effective_values))

        try:
            sigma_band = compute_dynamic_band(
                effective_values, effective_n, baseline.n_sigma,
            )
            if margin_enabled:
                margin_band = compute_margin_band(
                    effective_values, effective_n, baseline.margin_pct,
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

        # Backtest (uses full series for complete evaluation)
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

        # Store seasonality and change-point info
        proposal.seasonality_info = seasonality
        proposal.change_point_info = change_info

        # Robust analysis (informational — does not change bands)
        n_periods = baseline.n_periods
        iqr_band = compute_iqr_band(clean, n_periods)
        mad_band = compute_mad_band(clean, n_periods)
        outliers = detect_outliers(clean, method="iqr", n_periods=n_periods)
        robust_info = {
            "iqr_band": iqr_band,
            "mad_band": mad_band,
            "outliers": outliers,
            "iqr_vs_sigma": {
                "sigma_width": sigma_band["upper"] - sigma_band["lower"],
                "iqr_width": iqr_band["upper"] - iqr_band["lower"],
                "mad_width": mad_band["upper"] - mad_band["lower"],
                "recommendation": "classical",
            },
        }
        # Recommend robust method if outliers distort classical band significantly
        sigma_width = sigma_band["upper"] - sigma_band["lower"]
        iqr_width = iqr_band["upper"] - iqr_band["lower"]
        if sigma_width > 0 and iqr_width > 0:
            width_ratio = sigma_width / iqr_width
            if width_ratio > 2.0 and outliers["n_outliers"] >= 2:
                robust_info["iqr_vs_sigma"]["recommendation"] = "robust_iqr"
            elif width_ratio > 3.0:
                robust_info["iqr_vs_sigma"]["recommendation"] = "robust_mad"
        proposal.robust_info = robust_info

        # Sintaxe GDQ
        proposal.gdq_syntax_preview = self.generator.generate(proposal)

        return proposal

    def find_best_params(
        self,
        values: list[float],
        dates: list[str],
        metric_kind: str = "numeric",
        n_range: list[int] | None = None,
        sigma_range: list[float] | None = None,
        margin_range: list[float] | None = None,
        min_coverage: float = 70.0,
    ) -> AutoTuneResult:
        """Busca a melhor combinacao de N/sigma/margem via grid search.

        Avalia 5×5×4×2 = 200 combinacoes de (N, sigma, margem, margin_on).
        Scoring composto: coverage - FP_penalty + stability_bonus
        - width_penalty + drift_bonus - n_penalty.
        Veja ADR-005 para detalhes da formula de scoring.

        Args:
            values: Serie temporal de valores.
            dates: Datas correspondentes.
            metric_kind: "numeric" ou "frequency".
            n_range: Valores de N a testar.
            sigma_range: Valores de sigma a testar.
            margin_range: Valores de margem a testar.
            min_coverage: Cobertura minima para considerar viavel.

        Returns:
            AutoTuneResult com melhor combinacao, confianca e recomendacao.
        """
        if n_range is None:
            n_range = [10, 15, 20, 30, 45]
        if sigma_range is None:
            sigma_range = [1.0, 1.5, 2.0, 2.5, 3.0]
        if margin_range is None:
            margin_range = [0.05, 0.10, 0.15, 0.20]

        # Detectar drift uma vez (não depende de N/sigma/margin)
        drift_result = detect_drift(values)
        drift_bonus = 0.05 if not drift_result["has_drift"] else -0.05

        # Detectar sazonalidade uma vez
        seasonality_result = detect_seasonality(values, dates)
        has_strong_seasonality = (
            seasonality_result["has_seasonality"]
            and seasonality_result["amplitude_ratio"] > 0.10
        )

        # Detectar mudanca de regime uma vez
        change_result = detect_change_points(values, dates)
        has_change_point = (
            change_result["has_change_point"]
            and len(change_result["post_change_values"]) >= 5
        )
        post_change_len = len(change_result["post_change_values"]) if has_change_point else 0

        # Detectar outliers via IQR para scoring inteligente
        valid_values = [v for v in values if v is not None and not (isinstance(v, float) and v != v)]
        outlier_indices = set()
        if len(valid_values) >= 4:
            sorted_vals = sorted(valid_values)
            q1_idx = len(sorted_vals) // 4
            q3_idx = 3 * len(sorted_vals) // 4
            q1 = sorted_vals[q1_idx]
            q3 = sorted_vals[q3_idx]
            iqr = q3 - q1
            fence_lower = q1 - 2.5 * iqr
            fence_upper = q3 + 2.5 * iqr
            for idx, v in enumerate(values):
                if v is not None and not (isinstance(v, float) and v != v):
                    if v < fence_lower or v > fence_upper:
                        outlier_indices.add(idx)

        best = None
        best_score = -1.0

        for n in n_range:
            for sigma in sigma_range:
                for margin in margin_range:
                    for margin_on in [True, False]:
                        try:
                            if metric_kind == "frequency":
                                bt = backtest_frequency_dual_guard(
                                    pct_series=values, dates=dates,
                                    n_periods=n, n_sigma=sigma,
                                    margin_pct=margin, buffer=0.01,
                                    margin_enabled=margin_on,
                                )
                            else:
                                bt = backtest_band(
                                    values=values, dates=dates,
                                    n_periods=n, n_sigma=sigma,
                                    margin_pct=margin,
                                    margin_enabled=margin_on,
                                )
                        except Exception:
                            continue

                        if bt.total_periods == 0:
                            continue

                        # Outlier-aware coverage: separate normal vs outlier points
                        normal_pass = 0
                        normal_total = 0
                        outlier_pass = 0
                        outlier_total = 0
                        for pr in bt.point_results:
                            if pr["index"] in outlier_indices:
                                outlier_total += 1
                                if pr["passed"]:
                                    outlier_pass += 1
                            else:
                                normal_total += 1
                                if pr["passed"]:
                                    normal_pass += 1

                        # Primary metric: coverage of non-outlier points
                        normal_coverage = (
                            normal_pass / normal_total if normal_total > 0
                            else bt.coverage_pct / 100.0
                        )

                        # Penalty for covering outliers (band too wide)
                        outlier_penalty = (
                            (outlier_pass / outlier_total) * 0.15
                            if outlier_total > 0 else 0.0
                        )

                        fp_penalty = bt.false_positive_proxy * 0.05
                        stability_bonus = bt.stability_score * 0.10

                        # Quadratic width penalty — stronger than before
                        width_penalty = max(0, (bt.band_width_ratio - 0.20)) ** 2 * 0.5

                        n_penalty = 0.05 if n < 15 else 0.0

                        # Prefer tighter parameters when coverage is equal
                        sigma_preference = sigma * 0.02
                        margin_preference = margin * 0.10

                        # Bonus for N multiple of 7 when seasonality detected
                        seasonality_bonus = (
                            0.02 if has_strong_seasonality and n % 7 == 0 else 0.0
                        )

                        # Bonus for N <= post-change data when regime shift detected
                        change_point_bonus = (
                            0.03 if has_change_point and n <= post_change_len else 0.0
                        )

                        # Recency bonus: reward when recent coverage is better than overall
                        weighted_cov = bt.weighted_coverage_pct
                        if weighted_cov > bt.coverage_pct:
                            recency_bonus = (weighted_cov - bt.coverage_pct) / 100 * 0.10
                        else:
                            recency_bonus = 0.0

                        combo_score = (
                            normal_coverage
                            - outlier_penalty
                            - fp_penalty
                            + stability_bonus
                            - width_penalty
                            + drift_bonus
                            - n_penalty
                            - sigma_preference
                            - margin_preference
                            + seasonality_bonus
                            + change_point_bonus
                            + recency_bonus
                        )

                        if combo_score > best_score:
                            best_score = combo_score
                            best = {
                                "n_periods": n,
                                "n_sigma": sigma,
                                "margin_pct": margin,
                                "margin_enabled": margin_on,
                                "coverage_pct": bt.coverage_pct,
                                "weighted_coverage_pct": bt.weighted_coverage_pct,
                                "false_positives": bt.false_positive_proxy,
                                "stability": bt.stability_score,
                                "score_total": round(combo_score, 4),
                                # Score breakdown components
                                "normal_coverage": round(normal_coverage, 4),
                                "outlier_penalty": round(outlier_penalty, 4),
                                "fp_penalty": round(fp_penalty, 4),
                                "stability_bonus": round(stability_bonus, 4),
                                "width_penalty": round(width_penalty, 4),
                                "drift_bonus": round(drift_bonus, 4),
                                "n_penalty": round(n_penalty, 4),
                                "sigma_preference": round(sigma_preference, 4),
                                "margin_preference": round(margin_preference, 4),
                                "recency_bonus": round(recency_bonus, 4),
                                "band_width_ratio": round(bt.band_width_ratio, 4),
                                "outliers_detected": len(outlier_indices),
                                "outliers_covered": outlier_pass,
                            }

        if best is None:
            return {
                "n_periods": 20, "n_sigma": 2.0, "margin_pct": 0.10,
                "margin_enabled": True,
                "coverage_pct": 0.0, "weighted_coverage_pct": 0.0,
                "false_positives": 0,
                "stability": 0.0, "score_total": 0.0,
                "normal_coverage": 0.0, "outlier_penalty": 0.0,
                "fp_penalty": 0.0,
                "stability_bonus": 0.0, "width_penalty": 0.0,
                "drift_bonus": 0.0, "n_penalty": 0.0,
                "sigma_preference": 0.0, "margin_preference": 0.0,
                "recency_bonus": 0.0,
                "band_width_ratio": 0.0,
                "outliers_detected": 0, "outliers_covered": 0,
                "confidence": ConfidenceLevel.LOW,
                "viable": False,
                "recommendation": "Dados insuficientes para avaliar — nao recomendado.",
            }

        coverage = best["coverage_pct"]
        fp = best["false_positives"]
        n_outliers = best.get("outliers_detected", 0)
        n_outliers_covered = best.get("outliers_covered", 0)

        if coverage >= 90.0 and fp == 0:
            confidence = ConfidenceLevel.HIGH
            recommendation = (
                f"Recomendado: N={best['n_periods']}, sigma={best['n_sigma']}, "
                f"margem={best['margin_pct']*100:.0f}%"
                f"{'' if best['margin_enabled'] else ' (sem margem)'}. "
                f"Cobertura {coverage:.1f}%, 0 falsos positivos."
            )
        elif coverage >= min_coverage:
            confidence = ConfidenceLevel.MEDIUM
            fp_text = f", {fp} possivel(is) falso(s) positivo(s)" if fp > 0 else ""
            recommendation = (
                f"Aceitavel: N={best['n_periods']}, sigma={best['n_sigma']}, "
                f"margem={best['margin_pct']*100:.0f}%"
                f"{'' if best['margin_enabled'] else ' (sem margem)'}. "
                f"Cobertura {coverage:.1f}%{fp_text}. Revise os parametros."
            )
        else:
            confidence = ConfidenceLevel.LOW
            recommendation = (
                f"Nao recomendado: a melhor combinacao atinge apenas {coverage:.1f}% de cobertura"
                f" com {fp} falso(s) positivo(s). "
                f"Esta metrica pode ser instavel demais para uma regra automatica."
            )

        # Append outlier info if detected
        if n_outliers > 0:
            excluded = n_outliers - n_outliers_covered
            recommendation += (
                f" {n_outliers} outlier(s) detectado(s) via IQR"
                f" ({excluded} excluido(s) da banda)."
            )

        # Append seasonality warning if detected
        if has_strong_seasonality:
            amp_ratio = seasonality_result["amplitude_ratio"]
            recommendation += (
                f" Sazonalidade detectada (amplitude {amp_ratio:.0%})."
                f" Considere usar N multiplo de 7 para suavizar efeito semanal."
            )

        # Append change-point note if detected
        if has_change_point:
            cp_date = change_result.get("change_date", "periodo desconhecido")
            recommendation += (
                f" Mudanca de regime detectada em {cp_date}."
                f" Apenas os {post_change_len} periodos pos-mudanca foram priorizados."
            )

        best["confidence"] = confidence
        best["viable"] = coverage >= min_coverage
        best["recommendation"] = recommendation
        return best

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
