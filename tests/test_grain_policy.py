"""Testes para core/models/grain_policy.py — policies por granularidade."""

import pytest

from core.models.enums import GrainType
from core.models.grain_policy import GrainPolicy, get_grain_policy


class TestGetGrainPolicy:
    def test_daily_returns_daily_policy(self):
        p = get_grain_policy(GrainType.DAILY)
        assert p.min_history == 7
        assert p.seasonality_enabled is True
        assert 10 in p.n_range
        assert 45 in p.n_range

    def test_monthly_returns_monthly_policy(self):
        p = get_grain_policy(GrainType.MONTHLY)
        assert p.min_history == 3
        assert p.seasonality_enabled is False
        assert 3 in p.n_range
        assert 12 in p.n_range
        assert 45 not in p.n_range

    def test_unknown_grain_returns_daily(self):
        p = get_grain_policy(GrainType.TIMESTAMP)
        assert p.min_history == 7  # daily default

    def test_custom_grain_returns_daily(self):
        p = get_grain_policy(GrainType.CUSTOM)
        assert p.min_history == 7


class TestDailyPolicyPreservesExistingDefaults:
    """Garante que a policy daily reproduz exatamente os valores hardcoded anteriores."""

    def test_min_history(self):
        p = get_grain_policy(GrainType.DAILY)
        assert p.min_history == 7

    def test_n_range(self):
        p = get_grain_policy(GrainType.DAILY)
        assert list(p.n_range) == [10, 15, 20, 30, 45]

    def test_n_penalty_threshold(self):
        p = get_grain_policy(GrainType.DAILY)
        assert p.n_penalty_threshold == 15

    def test_robustness_tiers(self):
        p = get_grain_policy(GrainType.DAILY)
        assert p.robustness_tiers == ((7, -0.30), (15, -0.15), (30, -0.05))

    def test_min_valid_periods_dynamic(self):
        p = get_grain_policy(GrainType.DAILY)
        assert p.min_valid_periods_dynamic == 10

    def test_slider_defaults(self):
        p = get_grain_policy(GrainType.DAILY)
        assert p.slider_n_min == 5
        assert p.slider_n_max == 90
        assert p.slider_n_default == 20


class TestMonthlyPolicyAdaptations:
    def test_min_history_reduced(self):
        p = get_grain_policy(GrainType.MONTHLY)
        assert p.min_history == 3

    def test_n_range_includes_small_values(self):
        p = get_grain_policy(GrainType.MONTHLY)
        assert p.n_range[0] == 3
        assert all(n <= 12 for n in p.n_range)

    def test_robustness_tiers_adapted(self):
        p = get_grain_policy(GrainType.MONTHLY)
        # Menor threshold = 3 (nao 7)
        thresholds = [t for t, _ in p.robustness_tiers]
        assert min(thresholds) == 3

    def test_min_valid_periods_dynamic(self):
        p = get_grain_policy(GrainType.MONTHLY)
        assert p.min_valid_periods_dynamic == 3

    def test_min_valid_periods_possible(self):
        p = get_grain_policy(GrainType.MONTHLY)
        assert p.min_valid_periods_possible == 2

    def test_slider_n_min(self):
        p = get_grain_policy(GrainType.MONTHLY)
        assert p.slider_n_min == 3

    def test_slider_n_max(self):
        p = get_grain_policy(GrainType.MONTHLY)
        assert p.slider_n_max == 24

    def test_batch_min_periods(self):
        p = get_grain_policy(GrainType.MONTHLY)
        assert p.batch_min_periods == 3


class TestGrainPolicyFrozen:
    def test_immutable(self):
        p = get_grain_policy(GrainType.DAILY)
        with pytest.raises(AttributeError):
            p.min_history = 99


class TestDatasetConfigGrainPolicy:
    def test_config_returns_daily_policy(self):
        from core.models.dataset_config import DatasetConfig
        cfg = DatasetConfig(schema="db", table="tb", grain_type=GrainType.DAILY)
        assert cfg.grain_policy.min_history == 7

    def test_config_returns_monthly_policy(self):
        from core.models.dataset_config import DatasetConfig
        cfg = DatasetConfig(schema="db", table="tb", grain_type=GrainType.MONTHLY)
        assert cfg.grain_policy.min_history == 3
        assert cfg.grain_policy.seasonality_enabled is False


class TestSetGrainPolicyIntegration:
    def test_set_grain_policy_monthly(self):
        from services.proposal_service import ProposalService
        svc = ProposalService()
        policy = get_grain_policy(GrainType.MONTHLY)
        svc.set_grain_policy(policy)
        assert svc._min_periods_dynamic == 3
        assert svc._min_periods_possible == 2

    def test_set_grain_policy_daily(self):
        from services.proposal_service import ProposalService
        svc = ProposalService()
        policy = get_grain_policy(GrainType.DAILY)
        svc.set_grain_policy(policy)
        assert svc._min_periods_dynamic == 10
        assert svc._min_periods_possible == 5
