"""Sprint D.1c: CustomSql frequency guardrail (max_frequency_rules).

Tests that propose_categorical_rules() respects the max_frequency_rules
parameter to limit the number of frequency rules generated per column,
prioritizing the most frequent domain values.
"""

import random

import pandas as pd
import pytest
from datetime import date, timedelta

from core.models.baseline import BaselineStrategy
from core.models.column_profile import ColumnProfile
from core.models.enums import BaselineMethod, RuleType, SemanticType
from services.proposal_service import ProposalService


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FREQ_RULE_TYPES = {
    RuleType.CATEGORY_FREQUENCY_STATIC,
    RuleType.CATEGORY_FREQUENCY_DYNAMIC,
    RuleType.CATEGORY_FREQUENCY_HYBRID,
}

NON_FREQ_TYPES = {
    RuleType.ALLOWED_VALUES,
    RuleType.DISTINCT_COUNT_EXACT,
    RuleType.DISTINCT_COUNT_RANGE,
    RuleType.COMPLETENESS,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
    return ProposalService()


@pytest.fixture
def baseline():
    return BaselineStrategy(
        method=BaselineMethod.LAST_N_PERIODS,
        n_periods=20,
        n_sigma=2.0,
        margin_pct=0.10,
    )


@pytest.fixture
def low_profile():
    """Low-cardinality column profile (5 distinct values)."""
    return ColumnProfile(
        column_name="COD_PRODUTO",
        athena_type="string",
        inferred_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY,
        total_count=1000,
        non_null_count=1000,
        distinct_count=5,
        null_ratio=0.0,
    )


@pytest.fixture
def mid_profile():
    """Mid-cardinality column profile (100 distinct values)."""
    return ColumnProfile(
        column_name="COD_MUNI",
        athena_type="string",
        inferred_semantic_type=SemanticType.CATEGORICAL_MID_CARDINALITY,
        total_count=10000,
        non_null_count=10000,
        distinct_count=100,
        null_ratio=0.0,
    )


@pytest.fixture
def domain_10():
    """Domain DataFrame with 10 values sorted by frequency (descending)."""
    return pd.DataFrame({
        "category_value": [f"VAL_{i}" for i in range(10)],
        "value_count": [1000 - i * 100 for i in range(10)],
        "value_pct": [20, 15, 13, 12, 10, 8, 7, 6, 5, 4],
    })


@pytest.fixture
def distribution_10():
    """Distribution DataFrame: 30 periods x 10 category values."""
    random.seed(42)
    today = date.today()
    rows = []
    for i in range(30):
        dt = (today - timedelta(days=i)).isoformat()
        for j in range(10):
            rows.append({
                "period": dt,
                "category_value": f"VAL_{j}",
                "value_count": 100 - j * 10,
                "value_pct": 20 - j * 1.5 + random.uniform(-1, 1),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_freq_rules(proposals):
    """Count frequency rules in a list of proposals."""
    return [p for p in proposals if p.rule_type in FREQ_RULE_TYPES]


def _count_non_freq_rules(proposals):
    """Count non-frequency rules in a list of proposals."""
    return [p for p in proposals if p.rule_type in NON_FREQ_TYPES]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDefaultGuardrail:
    """Default max_frequency_rules=5 limits frequency rules to at most 5."""

    def test_default_max_5_with_10_domain_values(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
        )
        freq_rules = _count_freq_rules(proposals)
        assert len(freq_rules) <= 5, (
            f"Default guardrail should limit frequency rules to 5, got {len(freq_rules)}"
        )
        # With 10 domain values and default=5, we expect exactly 5
        assert len(freq_rules) == 5


class TestCustomGuardrailMax3:
    """max_frequency_rules=3 limits frequency rules to at most 3."""

    def test_max_3(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            max_frequency_rules=3,
        )
        freq_rules = _count_freq_rules(proposals)
        assert len(freq_rules) <= 3, (
            f"Guardrail max=3 should limit frequency rules to 3, got {len(freq_rules)}"
        )
        assert len(freq_rules) == 3


class TestCustomGuardrailMax10:
    """max_frequency_rules=10 with exactly 10 domain values."""

    def test_max_10_all_values(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            max_frequency_rules=10,
        )
        freq_rules = _count_freq_rules(proposals)
        assert len(freq_rules) <= 10, (
            f"Guardrail max=10 should allow up to 10 frequency rules, got {len(freq_rules)}"
        )
        # All 10 domain values have enough history (30 periods), so we expect 10
        assert len(freq_rules) == 10


class TestPriorityOrder:
    """Frequency rules should be for the first N values in domain (most frequent)."""

    def test_top_5_values_selected(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            max_frequency_rules=5,
        )
        freq_rules = _count_freq_rules(proposals)
        freq_values = {p.category_value for p in freq_rules}

        # The domain is sorted by value_count DESC, so top-5 are VAL_0..VAL_4
        expected_values = {f"VAL_{i}" for i in range(5)}
        assert freq_values == expected_values, (
            f"Expected frequency rules for {expected_values}, got {freq_values}"
        )

    def test_top_3_values_selected(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            max_frequency_rules=3,
        )
        freq_rules = _count_freq_rules(proposals)
        freq_values = {p.category_value for p in freq_rules}

        expected_values = {f"VAL_{i}" for i in range(3)}
        assert freq_values == expected_values, (
            f"Expected frequency rules for {expected_values}, got {freq_values}"
        )


class TestNonFrequencyRulesNotAffected:
    """AllowedValues, DistinctCount, Completeness still generated regardless of guardrail."""

    def test_non_freq_rules_present_with_guardrail_3(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            max_frequency_rules=3,
        )
        rule_types = {p.rule_type for p in proposals}

        # Low-cardinality should still produce AllowedValues + DistinctCountExact + Completeness
        assert RuleType.ALLOWED_VALUES in rule_types, "AllowedValues should not be affected by guardrail"
        assert RuleType.DISTINCT_COUNT_EXACT in rule_types, "DistinctCountExact should not be affected"
        assert RuleType.COMPLETENESS in rule_types, "Completeness should not be affected"

    def test_non_freq_count_same_regardless_of_guardrail(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals_3 = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            max_frequency_rules=3,
        )
        proposals_10 = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            max_frequency_rules=10,
        )

        non_freq_3 = _count_non_freq_rules(proposals_3)
        non_freq_10 = _count_non_freq_rules(proposals_10)

        assert len(non_freq_3) == len(non_freq_10), (
            f"Non-frequency rule count should be the same: "
            f"guardrail=3 produced {len(non_freq_3)}, guardrail=10 produced {len(non_freq_10)}"
        )


class TestFreqModeOverrides:
    """Per-value freq_mode overrides work with the guardrail."""

    def test_override_val0_to_dynamic(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            freq_mode="static",
            freq_mode_overrides={"VAL_0": "dynamic"},
            max_frequency_rules=5,
        )
        freq_rules = _count_freq_rules(proposals)

        val0_rules = [p for p in freq_rules if p.category_value == "VAL_0"]
        other_rules = [p for p in freq_rules if p.category_value != "VAL_0"]

        assert len(val0_rules) == 1, "VAL_0 should have exactly 1 frequency rule"
        assert val0_rules[0].rule_type == RuleType.CATEGORY_FREQUENCY_DYNAMIC, (
            f"VAL_0 should be dynamic, got {val0_rules[0].rule_type}"
        )
        for p in other_rules:
            assert p.rule_type == RuleType.CATEGORY_FREQUENCY_STATIC, (
                f"{p.category_value} should be static, got {p.rule_type}"
            )

    def test_override_multiple_values(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            freq_mode="static",
            freq_mode_overrides={"VAL_0": "dynamic", "VAL_2": "hybrid"},
            floor_pct=1.0,
            ceiling_pct=90.0,
            max_frequency_rules=5,
        )
        freq_rules = _count_freq_rules(proposals)

        types_by_value = {p.category_value: p.rule_type for p in freq_rules}
        assert types_by_value.get("VAL_0") == RuleType.CATEGORY_FREQUENCY_DYNAMIC
        assert types_by_value.get("VAL_2") == RuleType.CATEGORY_FREQUENCY_HYBRID
        assert types_by_value.get("VAL_1") == RuleType.CATEGORY_FREQUENCY_STATIC

    def test_override_for_value_outside_guardrail_ignored(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        """Override for VAL_9 should be ignored when guardrail=3 (only VAL_0..2 included)."""
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            freq_mode="static",
            freq_mode_overrides={"VAL_9": "dynamic"},
            max_frequency_rules=3,
        )
        freq_rules = _count_freq_rules(proposals)
        freq_values = {p.category_value for p in freq_rules}

        assert "VAL_9" not in freq_values, (
            "VAL_9 should not appear when guardrail=3 (only top 3 domain values)"
        )
        assert len(freq_rules) == 3


class TestMidCardinalityWithGuardrail:
    """Mid-cardinality column also respects the max_frequency_rules guardrail."""

    def test_mid_cardinality_guardrail_5(
        self, service, distribution_10, domain_10, mid_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_MUNI", "tb_test", mid_profile, baseline,
            max_frequency_rules=5,
        )
        freq_rules = _count_freq_rules(proposals)
        assert len(freq_rules) <= 5, (
            f"Mid-cardinality guardrail=5 should limit to 5, got {len(freq_rules)}"
        )
        assert len(freq_rules) == 5

    def test_mid_cardinality_guardrail_2(
        self, service, distribution_10, domain_10, mid_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_MUNI", "tb_test", mid_profile, baseline,
            max_frequency_rules=2,
        )
        freq_rules = _count_freq_rules(proposals)
        assert len(freq_rules) <= 2, (
            f"Mid-cardinality guardrail=2 should limit to 2, got {len(freq_rules)}"
        )
        assert len(freq_rules) == 2

    def test_mid_has_distinct_count_range_not_exact(
        self, service, distribution_10, domain_10, mid_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_MUNI", "tb_test", mid_profile, baseline,
            max_frequency_rules=3,
        )
        rule_types = {p.rule_type for p in proposals}

        assert RuleType.DISTINCT_COUNT_RANGE in rule_types
        assert RuleType.DISTINCT_COUNT_EXACT not in rule_types
        assert RuleType.ALLOWED_VALUES not in rule_types


class TestMaxFrequencyRulesZero:
    """max_frequency_rules=0 means no frequency rules, but other rules still present."""

    def test_no_frequency_rules_generated(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            max_frequency_rules=0,
        )
        freq_rules = _count_freq_rules(proposals)
        assert len(freq_rules) == 0, (
            f"max_frequency_rules=0 should produce 0 frequency rules, got {len(freq_rules)}"
        )

    def test_other_rules_still_present(
        self, service, distribution_10, domain_10, low_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_PRODUTO", "tb_test", low_profile, baseline,
            max_frequency_rules=0,
        )
        rule_types = {p.rule_type for p in proposals}

        assert RuleType.ALLOWED_VALUES in rule_types, "AllowedValues should still be generated"
        assert RuleType.DISTINCT_COUNT_EXACT in rule_types, "DistinctCountExact should still be generated"
        assert RuleType.COMPLETENESS in rule_types, "Completeness should still be generated"

    def test_mid_cardinality_zero_guardrail(
        self, service, distribution_10, domain_10, mid_profile, baseline,
    ):
        proposals = service.propose_categorical_rules(
            distribution_10, domain_10,
            "COD_MUNI", "tb_test", mid_profile, baseline,
            max_frequency_rules=0,
        )
        freq_rules = _count_freq_rules(proposals)
        non_freq_rules = _count_non_freq_rules(proposals)

        assert len(freq_rules) == 0
        assert len(non_freq_rules) > 0, "Non-frequency rules should still be present"
