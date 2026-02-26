"""Testes para core/gdq_rule_generator.py."""

import pytest

from core.gdq_rule_generator import GDQRuleGenerator
from core.models.enums import RuleType
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import UserOverride


@pytest.fixture
def generator():
    return GDQRuleGenerator()


def _make_proposal(
    rule_type: RuleType = RuleType.MEAN_DUAL_GUARD,
    target_column: str = "VLR_SALDO",
    **kwargs,
) -> RuleProposal:
    return RuleProposal(
        id="test-001",
        target_column=target_column,
        target_table="tb_test",
        rule_type=rule_type,
        metric_name=rule_type.value,
        baseline_window=30,
        baseline_n_sigma=2.0,
        **kwargs,
    )


class TestDualGuardGeneration:
    def test_mean_generates_valid_syntax(self, generator):
        proposal = _make_proposal(RuleType.MEAN_DUAL_GUARD)
        result = generator.generate(proposal)
        assert "Mean VLR_SALDO" in result
        assert "avg(last(30))" in result
        assert "std(last(30))" in result

    def test_stddev_generates_valid_syntax(self, generator):
        proposal = _make_proposal(RuleType.STDDEV_DUAL_GUARD)
        result = generator.generate(proposal)
        assert "StandardDeviation VLR_SALDO" in result

    def test_rowcount_generates_valid_syntax(self, generator):
        proposal = _make_proposal(
            RuleType.ROW_COUNT_DUAL_GUARD,
            target_column=None,
        )
        result = generator.generate(proposal)
        assert "RowCount" in result
        assert "2.0 *" in result

    def test_override_n_periods(self, generator):
        proposal = _make_proposal()
        overrides = UserOverride(custom_n_periods=20)
        result = generator.generate(proposal, overrides)
        assert "last(20)" in result

    def test_override_n_sigma(self, generator):
        proposal = _make_proposal()
        overrides = UserOverride(custom_n_sigma=3.0)
        result = generator.generate(proposal, overrides)
        assert "3 *" in result


class TestStaticRuleGeneration:
    def test_completeness(self, generator):
        proposal = _make_proposal(
            RuleType.COMPLETENESS,
            suggested_lower=0.95,
        )
        result = generator.generate(proposal)
        assert result == "Completeness VLR_SALDO >= 0.95"

    def test_completeness_override(self, generator):
        proposal = _make_proposal(
            RuleType.COMPLETENESS,
            suggested_lower=1.0,
        )
        overrides = UserOverride(custom_lower=0.90)
        result = generator.generate(proposal, overrides)
        assert result == "Completeness VLR_SALDO >= 0.90"

    def test_allowed_values(self, generator):
        proposal = _make_proposal(
            RuleType.ALLOWED_VALUES,
            target_column="COD_SITU",
            suggested_values=["1", "2", "3"],
        )
        result = generator.generate(proposal)
        assert result == "ColumnValues COD_SITU in [1, 2, 3]"

    def test_distinct_count(self, generator):
        proposal = _make_proposal(
            RuleType.DISTINCT_COUNT_EXACT,
            target_column="COD_SITU",
            suggested_lower=3.0,
        )
        result = generator.generate(proposal)
        assert result == "DistinctValuesCount COD_SITU = 3"

    def test_primary_key(self, generator):
        proposal = _make_proposal(
            RuleType.IS_PRIMARY_KEY,
            target_column="PK_COL",
            suggested_values=["COL1", "COL2", "COL3"],
        )
        result = generator.generate(proposal)
        assert result == "IsPrimaryKey COL1 COL2 COL3"

    def test_unsupported_type_raises(self, generator):
        proposal = _make_proposal(RuleType.NUMERIC_PERCENTILE_BAND)
        with pytest.raises(ValueError, match="não suportado"):
            generator.generate(proposal)
