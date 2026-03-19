"""Tests for core/gdq_capability.py."""

import pytest

from core.models.enums import GDQCapabilityStatus, RuleType
from core.gdq_capability import (
    get_capability_status,
    is_experimental,
    capability_badge,
    capability_warning,
    RULE_CAPABILITY,
)


class TestGetCapabilityStatus:

    def test_mean_validated(self):
        assert get_capability_status(RuleType.MEAN_DUAL_GUARD) == GDQCapabilityStatus.VALIDATED

    def test_stddev_validated(self):
        assert get_capability_status(RuleType.STDDEV_DUAL_GUARD) == GDQCapabilityStatus.VALIDATED

    def test_rowcount_validated(self):
        assert get_capability_status(RuleType.ROW_COUNT_DUAL_GUARD) == GDQCapabilityStatus.VALIDATED

    def test_completeness_validated(self):
        assert get_capability_status(RuleType.COMPLETENESS) == GDQCapabilityStatus.VALIDATED

    def test_freq_static_validated(self):
        assert get_capability_status(RuleType.CATEGORY_FREQUENCY_STATIC) == GDQCapabilityStatus.VALIDATED

    def test_freq_dynamic_experimental(self):
        assert get_capability_status(RuleType.CATEGORY_FREQUENCY_DYNAMIC) == GDQCapabilityStatus.EXPERIMENTAL

    def test_freq_hybrid_experimental(self):
        assert get_capability_status(RuleType.CATEGORY_FREQUENCY_HYBRID) == GDQCapabilityStatus.EXPERIMENTAL

    def test_percentile_experimental(self):
        assert get_capability_status(RuleType.NUMERIC_PERCENTILE_BAND) == GDQCapabilityStatus.EXPERIMENTAL

    def test_all_rule_types_mapped(self):
        for rt in RuleType:
            status = get_capability_status(rt)
            assert status in list(GDQCapabilityStatus)


class TestIsExperimental:

    def test_dynamic_is_experimental(self):
        assert is_experimental(RuleType.CATEGORY_FREQUENCY_DYNAMIC) is True

    def test_mean_not_experimental(self):
        assert is_experimental(RuleType.MEAN_DUAL_GUARD) is False


class TestCapabilityBadge:

    def test_validated_empty(self):
        assert capability_badge(RuleType.MEAN_DUAL_GUARD) == ""

    def test_experimental_has_badge(self):
        badge = capability_badge(RuleType.CATEGORY_FREQUENCY_DYNAMIC)
        assert "experimental" in badge

    def test_badge_is_string(self):
        for rt in RuleType:
            assert isinstance(capability_badge(rt), str)


class TestCapabilityWarning:

    def test_validated_no_warning(self):
        assert capability_warning(RuleType.MEAN_DUAL_GUARD) == ""

    def test_experimental_has_warning(self):
        warning = capability_warning(RuleType.CATEGORY_FREQUENCY_DYNAMIC)
        assert "experimental" in warning.lower()
        assert "thundera" in warning.lower()

    def test_warning_is_string(self):
        for rt in RuleType:
            assert isinstance(capability_warning(rt), str)
