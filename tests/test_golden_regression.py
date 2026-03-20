"""Testes de regressao funcional com golden dataset.

Regua fixa: se algum destes testes quebrar, significa que o comportamento
do motor mudou. A mudanca deve ser revisada conscientemente e o golden
atualizado explicitamente — nunca silenciosamente.

Cobre 4 dimensoes:
1. Classificacao semantica (classify_column + suggest_reclassification)
2. Regime estatistico (classify_series)
3. Elegibilidade de regras (quais RuleTypes sao gerados)
4. Qualidade das propostas (confianca, cobertura, sintaxe)
"""

import random
import math

import pandas as pd
import pytest

from core.column_classifier import classify_column, suggest_reclassification
from core.models.enums import (
    ConfidenceLevel,
    RecommendationTier,
    RuleType,
    SemanticType,
    SeriesRegime,
)
from core.series_regime import classify_series
from core.models.baseline import BaselineStrategy
from core.models.rule_proposal import RuleProposal
from services.proposal_service import ProposalService

from tests.fixtures import (
    make_stable_series,
    make_drift_series,
    make_seasonal_series,
    make_outlier_series,
    make_sparse_numeric_series,
    make_zero_inflated_series,
    make_regime_change_series,
)
from tests.fixtures.golden_dataset import (
    GOLDEN_SCENARIOS,
    GOLDEN_BY_NAME,
    GoldenScenario,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _baseline(n: int = 30) -> BaselineStrategy:
    return BaselineStrategy(n_periods=n, n_sigma=2.0, margin_pct=0.10)


def _make_numeric_history(series: dict, col: str = "VLR_SALDO") -> pd.DataFrame:
    """Converte fixture de serie em DataFrame similar ao numeric_history."""
    values = series["values"]
    dates = series["dates"]
    rows = []
    for d, v in zip(dates, values):
        rows.append({
            "period": d,
            "row_count": 1000,
            "total_count": 1000,
            "non_null_count": 1000,
            "mean": v,
            "stddev": abs(v * 0.05),
            "min_val": v * 0.9,
            "max_val": v * 1.1,
            "p01": v * 0.92, "p05": v * 0.95, "p10": v * 0.96,
            "p25": v * 0.98, "p50": v, "p75": v * 1.02,
            "p90": v * 1.04, "p95": v * 1.05, "p99": v * 1.08,
        })
    return pd.DataFrame(rows)


def _make_volatile_series(n: int = 45, seed: int = 99) -> dict:
    """Serie com CV > 30%."""
    rng = random.Random(seed)
    values = [100.0 + rng.gauss(0, 50) for _ in range(n)]
    dates = [f"2026-01-{i+1:02d}" if i < 28 else f"2026-02-{i-27:02d}" for i in range(n)]
    return {"values": values, "dates": dates}


# ===========================================================================
# DIMENSAO 1: Classificacao semantica
# ===========================================================================

class TestGoldenClassification:
    """Validacao de classificacao semantica contra golden dataset."""

    @pytest.mark.parametrize(
        "scenario",
        [s for s in GOLDEN_SCENARIOS],
        ids=[s.name for s in GOLDEN_SCENARIOS],
    )
    def test_classify_column_matches_golden(self, scenario: GoldenScenario):
        """classify_column retorna o SemanticType esperado."""
        result = classify_column(
            athena_type=scenario.athena_type,
            distinct_count=scenario.distinct_count,
            total_count=scenario.total_count,
            non_null_count=scenario.non_null_count,
            numeric_cast_count=scenario.numeric_cast_count,
        )
        assert result == scenario.expected_semantic_type, (
            f"[{scenario.name}] Expected {scenario.expected_semantic_type.name}, "
            f"got {result.name}"
        )

    @pytest.mark.parametrize(
        "scenario",
        [s for s in GOLDEN_SCENARIOS if s.expected_reclassification is not None],
        ids=[s.name for s in GOLDEN_SCENARIOS if s.expected_reclassification is not None],
    )
    def test_reclassification_suggestion(self, scenario: GoldenScenario):
        """suggest_reclassification retorna sugestao esperada."""
        suggested, reason = suggest_reclassification(
            athena_type=scenario.athena_type,
            distinct_count=scenario.distinct_count,
            total_count=scenario.total_count,
            non_null_count=scenario.non_null_count,
        )
        assert suggested == scenario.expected_reclassification, (
            f"[{scenario.name}] Expected reclassification to "
            f"{scenario.expected_reclassification.name}, got {suggested}"
        )

    def test_no_reclassification_for_real_numeric(self):
        """Coluna double com cardinalidade normal nao deve ser reclassificada."""
        s = GOLDEN_BY_NAME["numeric_stable"]
        suggested, _ = suggest_reclassification(
            s.athena_type, s.distinct_count, s.total_count, s.non_null_count,
        )
        assert suggested is None

    def test_varchar_date_not_numeric(self):
        """Varchar com datas nao deve ser classificada como NUMERIC."""
        s = GOLDEN_BY_NAME["datetime_as_string"]
        result = classify_column(
            s.athena_type, s.distinct_count, s.total_count,
            s.non_null_count, s.numeric_cast_count,
        )
        assert result != SemanticType.NUMERIC
        assert result != SemanticType.IDENTIFIER

    def test_string_castable_as_numeric(self):
        """Varchar com 95%+ cast numerico e cardinalidade media → NUMERIC."""
        result = classify_column(
            athena_type="varchar",
            distinct_count=500,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=96000,  # 96% cast
        )
        assert result == SemanticType.NUMERIC

    def test_string_castable_low_card_as_categorical(self):
        """Varchar castavel com <= 20 distintos → CATEGORICAL_LOW."""
        result = classify_column(
            athena_type="varchar",
            distinct_count=5,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=96000,
        )
        assert result == SemanticType.CATEGORICAL_LOW_CARDINALITY

    def test_string_castable_high_card_as_identifier(self):
        """Varchar castavel com >= 10k distintos e ratio >= 50% → IDENTIFIER."""
        result = classify_column(
            athena_type="varchar",
            distinct_count=60000,
            total_count=100000,
            non_null_count=100000,
            numeric_cast_count=96000,
        )
        assert result == SemanticType.IDENTIFIER


# ===========================================================================
# DIMENSAO 2: Regime estatistico
# ===========================================================================

class TestGoldenRegime:
    """Validacao de regime estatistico contra series de referencia."""

    def test_stable_regime(self):
        s = make_stable_series(n=45)
        profile = classify_series(s["values"], s["dates"])
        assert profile.regime == SeriesRegime.STABLE
        assert not profile.is_volatile
        assert not profile.has_trend

    def test_volatile_regime(self):
        s = _make_volatile_series()
        profile = classify_series(s["values"], s["dates"])
        assert profile.is_volatile
        assert profile.cv > 0.30

    def test_seasonal_regime(self):
        s = make_seasonal_series(n=56)  # 8 semanas
        profile = classify_series(s["values"], s["dates"])
        assert profile.regime == SeriesRegime.SEASONAL or profile.is_seasonal

    def test_structural_break_regime(self):
        s = make_regime_change_series(n=60)
        profile = classify_series(s["values"], s["dates"])
        # Mudanca brusca 50→200 pode ser detectada como break ou trending
        assert profile.has_structural_break or profile.has_trend

    def test_sparse_regime(self):
        s = make_sparse_numeric_series(n=45)
        profile = classify_series(s["values"], s["dates"])
        assert profile.is_sparse
        assert profile.null_pct >= 0.25

    def test_zero_inflated_regime(self):
        s = make_zero_inflated_series(n=45)
        profile = classify_series(s["values"], s["dates"])
        assert profile.is_zero_inflated
        assert profile.zero_pct >= 0.25

    def test_drift_detected(self):
        s = make_drift_series(n=45)
        profile = classify_series(s["values"], s["dates"])
        assert profile.has_trend or profile.regime == SeriesRegime.TRENDING


# ===========================================================================
# DIMENSAO 3: Elegibilidade de regras
# ===========================================================================

class TestGoldenRuleEligibility:
    """Valida quais tipos de regra sao gerados para cada cenario."""

    def test_numeric_generates_mean_stddev_completeness(self):
        """Coluna numerica estavel gera Mean + StdDev + Completeness."""
        s = make_stable_series(n=45)
        history = _make_numeric_history(s)
        svc = ProposalService()
        proposals = svc.propose_numeric_rules(
            history, "VLR_SALDO", "tb_test", _baseline(),
        )
        rule_types = {p.rule_type for p in proposals}
        assert RuleType.MEAN_DUAL_GUARD in rule_types
        assert RuleType.STDDEV_DUAL_GUARD in rule_types
        assert RuleType.COMPLETENESS in rule_types

    def test_numeric_at_least_3_proposals(self):
        """Coluna numerica deve gerar ao menos 3 propostas."""
        s = make_stable_series(n=45)
        history = _make_numeric_history(s)
        svc = ProposalService()
        proposals = svc.propose_numeric_rules(
            history, "VLR_SALDO", "tb_test", _baseline(),
        )
        assert len(proposals) >= 3

    def test_volatile_still_generates_proposals(self):
        """Coluna volatil nao deve bloquear geracao de propostas."""
        s = _make_volatile_series()
        history = _make_numeric_history(s)
        svc = ProposalService()
        proposals = svc.propose_numeric_rules(
            history, "VLR_VOLATIL", "tb_test", _baseline(),
        )
        assert len(proposals) >= 1

    def test_empty_history_generates_nothing(self):
        """Historico vazio nao deve gerar propostas."""
        svc = ProposalService()
        proposals = svc.propose_numeric_rules(
            pd.DataFrame(), "VLR_SALDO", "tb_test", _baseline(),
        )
        assert len(proposals) == 0


# ===========================================================================
# DIMENSAO 4: Qualidade das propostas
# ===========================================================================

class TestGoldenProposalQuality:
    """Valida qualidade das propostas: confianca, cobertura, sintaxe."""

    def _propose_stable(self) -> list[RuleProposal]:
        s = make_stable_series(n=45)
        history = _make_numeric_history(s)
        svc = ProposalService()
        return svc.propose_numeric_rules(
            history, "VLR_SALDO", "tb_test", _baseline(),
        )

    def test_stable_mean_high_confidence(self):
        """Mean em serie estavel deve ter confianca HIGH."""
        proposals = self._propose_stable()
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert mean_p.confidence == ConfidenceLevel.HIGH

    def test_stable_mean_high_coverage(self):
        """Mean em serie estavel deve ter coverage >= 90%."""
        proposals = self._propose_stable()
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert mean_p.backtest is not None
        assert mean_p.backtest.coverage_pct >= 90.0

    def test_stable_mean_low_fp(self):
        """Mean em serie estavel deve ter poucos falsos positivos."""
        proposals = self._propose_stable()
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert mean_p.backtest.false_positive_proxy <= 2

    def test_syntax_preview_populated(self):
        """Toda proposta deve ter gdq_syntax_preview preenchido."""
        proposals = self._propose_stable()
        for p in proposals:
            assert p.gdq_syntax_preview, f"{p.rule_type.name} sem syntax preview"
            assert len(p.gdq_syntax_preview) > 10

    def test_syntax_column_uppercase(self):
        """Nome da coluna na sintaxe deve estar em UPPERCASE."""
        proposals = self._propose_stable()
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert "VLR_SALDO" in mean_p.gdq_syntax_preview
        assert "vlr_saldo" not in mean_p.gdq_syntax_preview

    def test_mean_syntax_has_dual_guard(self):
        """Mean deve ter padrao dual guard (OR) na sintaxe."""
        proposals = self._propose_stable()
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert "OR" in mean_p.gdq_syntax_preview
        assert "avg(last(" in mean_p.gdq_syntax_preview
        assert "std(last(" in mean_p.gdq_syntax_preview

    def test_completeness_syntax_uses_gte(self):
        """Completeness deve usar >= (nao between)."""
        proposals = self._propose_stable()
        comp_p = next(p for p in proposals if p.rule_type == RuleType.COMPLETENESS)
        assert ">=" in comp_p.gdq_syntax_preview
        assert "between" not in comp_p.gdq_syntax_preview.lower()

    def test_volatile_lower_confidence(self):
        """Serie volatil pode ter confianca menor que serie estavel."""
        s = _make_volatile_series()
        history = _make_numeric_history(s)
        svc = ProposalService()
        proposals = svc.propose_numeric_rules(
            history, "VLR_VOLATIL", "tb_test", _baseline(),
        )
        mean_p = next(
            (p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD),
            None,
        )
        if mean_p and mean_p.backtest:
            # Volatil pode ter cobertura menor — aceitavel
            assert mean_p.backtest.coverage_pct >= 50.0

    def test_history_dates_and_values_populated(self):
        """Propostas devem ter historico para grafico."""
        proposals = self._propose_stable()
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert len(mean_p.history_dates) > 0
        assert len(mean_p.history_values) > 0
        assert len(mean_p.history_dates) == len(mean_p.history_values)


# ===========================================================================
# DIMENSAO 5: Recommendation tier
# ===========================================================================

class TestGoldenRecommendationTier:
    """Valida que tiers de recomendacao sao atribuidos corretamente."""

    def test_stable_mean_recommended(self):
        """Mean em serie estavel = RECOMMENDED."""
        s = make_stable_series(n=45)
        history = _make_numeric_history(s)
        svc = ProposalService()
        proposals = svc.propose_numeric_rules(
            history, "VLR_SALDO", "tb_test", _baseline(),
        )
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert mean_p.recommendation_tier == RecommendationTier.RECOMMENDED

    def test_stable_completeness_trivial(self):
        """Completeness 1.0 com 100% coverage em serie estavel = NOT_RECOMMENDED (trivial)."""
        s = make_stable_series(n=45)
        history = _make_numeric_history(s)
        svc = ProposalService()
        proposals = svc.propose_numeric_rules(
            history, "VLR_SALDO", "tb_test", _baseline(),
        )
        comp_p = next(p for p in proposals if p.rule_type == RuleType.COMPLETENESS)
        # Completeness com threshold 1.0 e 100% coverage = trivial
        if comp_p.backtest and comp_p.backtest.coverage_pct >= 100.0:
            assert comp_p.recommendation_tier == RecommendationTier.NOT_RECOMMENDED
            assert any("trivial" in r.lower() for r in comp_p.recommendation_reasons)

    def test_all_proposals_have_tier(self):
        """Todas as propostas devem ter tier atribuido."""
        s = make_stable_series(n=45)
        history = _make_numeric_history(s)
        svc = ProposalService()
        proposals = svc.propose_numeric_rules(
            history, "VLR_SALDO", "tb_test", _baseline(),
        )
        for p in proposals:
            assert hasattr(p, "recommendation_tier")
            assert isinstance(p.recommendation_tier, RecommendationTier)
            assert isinstance(p.recommendation_reasons, list)

    def test_volatile_mean_not_recommended_highest(self):
        """Mean em serie volatil nao deve ser RECOMMENDED."""
        s = _make_volatile_series()
        history = _make_numeric_history(s)
        svc = ProposalService()
        proposals = svc.propose_numeric_rules(
            history, "VLR_VOLATIL", "tb_test", _baseline(),
        )
        mean_p = next(
            (p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD),
            None,
        )
        if mean_p:
            # Volatil pode ser POSSIBLE ou NOT_RECOMMENDED, nunca RECOMMENDED
            assert mean_p.recommendation_tier != RecommendationTier.RECOMMENDED
