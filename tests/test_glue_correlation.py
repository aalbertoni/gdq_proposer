"""Tests for Glue test result correlation and write-back to cart."""
import pytest

from core.models.enums import RuleType
from core.models.glue_test import GlueRuleResult
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import RuleSelection, _syntax_hash
from services.glue_test_service import (
    CorrelationReport,
    GlueTestService,
    normalize_syntax,
)


# --- Fixtures ---

class MockGlueClient:
    def start_job_run(self, job_name, arguments):
        return "jr_test"
    def get_job_run(self, job_name, run_id):
        return {"JobRunState": "SUCCEEDED"}
    def stop_job_run(self, job_name, run_id):
        pass
    def get_job_logs(self, job_name, run_id):
        return ""


class MockConfig:
    class glue_test:
        glue_job_name = "test-job"
        region = "us-east-1"
        poll_interval_seconds = 1
        poll_timeout_seconds = 5
        default_squad = ""
        default_comunidade = ""
        default_racf = ""
        default_periodicidade = "D"
        default_tipo_qualidade = "POUSADO"
        default_conta = ""
        default_timeout = "30"
        default_workers = "10"


def _make_selection(
    proposal_id: str,
    rule_type: RuleType,
    target_column: str,
    syntax: str,
    enabled: bool = True,
) -> RuleSelection:
    proposal = RuleProposal(
        id=proposal_id,
        target_column=target_column,
        target_table="test_table",
        rule_type=rule_type,
        metric_name="test",
    )
    return RuleSelection(
        proposal_id=proposal_id,
        proposal=proposal,
        enabled=enabled,
        final_gdq_syntax=syntax,
    )


def _make_glue_result(
    syntax: str,
    outcome: str = "Passed",
    category: str = "",
    target_column: str = "",
    metrics: dict | None = None,
    failure_reason: str = "",
) -> GlueRuleResult:
    return GlueRuleResult(
        rule_syntax=syntax,
        outcome=outcome,
        evaluated_metrics=metrics or {},
        failure_reason=failure_reason,
        rule_category=category,
        target_column=target_column,
    )


def _make_svc() -> GlueTestService:
    return GlueTestService(MockGlueClient(), MockConfig())


# --- normalize_syntax ---

class TestNormalizeSyntax:
    def test_collapses_whitespace(self):
        assert normalize_syntax("Mean  VLR_SALDO  >= 100") == "Mean VLR_SALDO >= 100"

    def test_strips_leading_trailing(self):
        assert normalize_syntax("  Mean VLR >= 1  ") == "Mean VLR >= 1"

    def test_tabs_and_newlines(self):
        assert normalize_syntax("Mean\tVLR\n>= 1") == "Mean VLR >= 1"

    def test_preserves_case(self):
        assert normalize_syntax("Mean VLR_SALDO") == "Mean VLR_SALDO"

    def test_empty_string(self):
        assert normalize_syntax("") == ""


# --- _syntax_hash ---

class TestSyntaxHash:
    def test_same_content_same_hash(self):
        assert _syntax_hash("Mean VLR >= 1") == _syntax_hash("Mean VLR >= 1")

    def test_whitespace_normalized(self):
        assert _syntax_hash("Mean  VLR  >= 1") == _syntax_hash("Mean VLR >= 1")

    def test_different_content_different_hash(self):
        assert _syntax_hash("Mean VLR >= 1") != _syntax_hash("Mean VLR >= 2")

    def test_returns_16_char_hex(self):
        h = _syntax_hash("test")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


# --- RuleSelection properties ---

class TestRuleSelectionTestProperties:
    def test_has_test_result_false_by_default(self):
        sel = _make_selection("p1", RuleType.COMPLETENESS, "col", "rule1")
        assert sel.has_test_result is False

    def test_has_test_result_true_when_populated(self):
        sel = _make_selection("p1", RuleType.COMPLETENESS, "col", "rule1")
        sel.glue_test_result = GlueRuleResult(outcome="Passed")
        assert sel.has_test_result is True

    def test_is_test_stale_false_when_no_result(self):
        sel = _make_selection("p1", RuleType.COMPLETENESS, "col", "rule1")
        assert sel.is_test_stale is False

    def test_is_test_stale_false_when_syntax_unchanged(self):
        sel = _make_selection("p1", RuleType.COMPLETENESS, "col", "Mean VLR >= 1")
        sel.glue_test_result = GlueRuleResult(outcome="Passed")
        sel.glue_tested_syntax_hash = _syntax_hash("Mean VLR >= 1")
        assert sel.is_test_stale is False

    def test_is_test_stale_true_when_syntax_changed(self):
        sel = _make_selection("p1", RuleType.COMPLETENESS, "col", "Mean VLR >= 2")
        sel.glue_test_result = GlueRuleResult(outcome="Passed")
        sel.glue_tested_syntax_hash = _syntax_hash("Mean VLR >= 1")
        assert sel.is_test_stale is True

    def test_is_test_stale_false_when_whitespace_only_change(self):
        sel = _make_selection("p1", RuleType.COMPLETENESS, "col", "Mean  VLR  >= 1")
        sel.glue_test_result = GlueRuleResult(outcome="Passed")
        sel.glue_tested_syntax_hash = _syntax_hash("Mean VLR >= 1")
        assert sel.is_test_stale is False

    def test_backward_compatible_defaults(self):
        """New fields don't break existing code that creates RuleSelection."""
        sel = RuleSelection(
            proposal_id="p1",
            proposal=RuleProposal(
                id="p1", target_column="col",
                target_table="tbl", rule_type=RuleType.COMPLETENESS,
                metric_name="test",
            ),
        )
        assert sel.glue_test_result is None
        assert sel.glue_tested_at is None
        assert sel.glue_tested_syntax_hash is None
        assert sel.has_test_result is False
        assert sel.is_test_stale is False


# --- correlate_results ---

class TestCorrelateResults:
    def test_exact_syntax_match(self):
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.COMPLETENESS, "col_a", "Completeness col_a >= 0.95"),
        ]
        results = [
            _make_glue_result("Completeness col_a >= 0.95", "Passed"),
        ]
        corr_map, report = svc.correlate_results(cart, results)
        assert report.matched == 1
        assert report.orphaned == 0
        assert report.unmatched == 0
        assert "p1" in corr_map

    def test_syntax_match_with_whitespace_differences(self):
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.COMPLETENESS, "col_a", "Completeness col_a >= 0.95"),
        ]
        results = [
            _make_glue_result("Completeness  col_a  >=  0.95", "Passed"),
        ]
        corr_map, report = svc.correlate_results(cart, results)
        assert report.matched == 1

    def test_fallback_by_category_column(self):
        """When syntax doesn't match, fallback to category+column."""
        svc = _make_svc()
        cart = [
            _make_selection(
                "p1", RuleType.MEAN_DUAL_GUARD, "vlr_saldo",
                "Mean VLR_SALDO >= (avg(last(30)) - 2 * std(last(30)))",
            ),
        ]
        # Glue may log a reformatted version of the syntax
        results = [
            _make_glue_result(
                "Mean VLR_SALDO >= (avg(last(30))-2*std(last(30)))",
                "Passed",
                category="Mean",
                target_column="vlr_saldo",
            ),
        ]
        corr_map, report = svc.correlate_results(cart, results)
        assert report.matched == 1
        assert "p1" in corr_map

    def test_fallback_skipped_when_ambiguous(self):
        """When multiple cart items match same category+column, fallback is skipped."""
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.COMPLETENESS, "col_a", "syntax1"),
            _make_selection("p2", RuleType.COMPLETENESS, "col_a", "syntax2"),
        ]
        results = [
            _make_glue_result(
                "different_syntax",
                "Passed",
                category="Completeness",
                target_column="col_a",
            ),
        ]
        corr_map, report = svc.correlate_results(cart, results)
        assert report.matched == 0
        assert report.orphaned == 1

    def test_orphaned_results(self):
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.COMPLETENESS, "col_a", "rule1"),
        ]
        results = [
            _make_glue_result("completely_different_rule", "Passed"),
        ]
        corr_map, report = svc.correlate_results(cart, results)
        assert report.matched == 0
        assert report.orphaned == 1
        assert len(report.orphaned_results) == 1

    def test_unmatched_cart_items(self):
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.COMPLETENESS, "col_a", "rule1"),
            _make_selection("p2", RuleType.COMPLETENESS, "col_b", "rule2"),
        ]
        results = [
            _make_glue_result("rule1", "Passed"),
        ]
        corr_map, report = svc.correlate_results(cart, results)
        assert report.matched == 1
        assert report.unmatched == 1

    def test_disabled_items_excluded(self):
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.COMPLETENESS, "col_a", "rule1", enabled=False),
        ]
        results = [
            _make_glue_result("rule1", "Passed"),
        ]
        corr_map, report = svc.correlate_results(cart, results)
        assert report.matched == 0
        assert report.orphaned == 1

    def test_empty_cart(self):
        svc = _make_svc()
        results = [_make_glue_result("rule1", "Passed")]
        corr_map, report = svc.correlate_results([], results)
        assert report.matched == 0
        assert report.orphaned == 1

    def test_empty_results(self):
        svc = _make_svc()
        cart = [_make_selection("p1", RuleType.COMPLETENESS, "col_a", "rule1")]
        corr_map, report = svc.correlate_results(cart, [])
        assert report.matched == 0
        assert report.unmatched == 1
        assert report.orphaned == 0

    def test_multiple_rules_mixed(self):
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.MEAN_DUAL_GUARD, "col_a", "Mean col_a rule"),
            _make_selection("p2", RuleType.COMPLETENESS, "col_a", "Completeness col_a >= 0.95"),
            _make_selection("p3", RuleType.STDDEV_DUAL_GUARD, "col_b", "StdDev col_b rule"),
        ]
        results = [
            _make_glue_result("Mean col_a rule", "Passed"),
            _make_glue_result("Completeness col_a >= 0.95", "Failed", failure_reason="too low"),
            _make_glue_result("orphan_rule", "Passed"),
        ]
        corr_map, report = svc.correlate_results(cart, results)
        assert report.matched == 2
        assert report.unmatched == 1  # p3 unmatched
        assert report.orphaned == 1  # orphan_rule

    def test_does_not_double_match(self):
        """Each cart item can only be matched once."""
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.COMPLETENESS, "col_a", "rule1"),
        ]
        # Two results with same syntax — second should be orphaned
        results = [
            _make_glue_result("rule1", "Passed"),
            _make_glue_result("rule1", "Failed"),
        ]
        corr_map, report = svc.correlate_results(cart, results)
        assert report.matched == 1
        assert report.orphaned == 1


# --- apply_results_to_cart ---

class TestApplyResultsToCart:
    def test_applies_matched_results(self):
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.COMPLETENESS, "col_a", "rule1"),
            _make_selection("p2", RuleType.COMPLETENESS, "col_b", "rule2"),
        ]
        glue_result = GlueRuleResult(
            rule_syntax="rule1", outcome="Passed",
            evaluated_metrics={"Dataset.*.Completeness": 0.98},
        )
        corr_map = {"p1": glue_result}

        applied, skipped = svc.apply_results_to_cart(cart, corr_map)

        assert applied == 1
        assert skipped == 1
        assert cart[0].has_test_result is True
        assert cart[0].glue_test_result.passed is True
        assert cart[0].glue_tested_at is not None
        assert cart[0].glue_tested_syntax_hash is not None
        assert cart[1].has_test_result is False

    def test_overwrites_previous_result(self):
        svc = _make_svc()
        sel = _make_selection("p1", RuleType.COMPLETENESS, "col_a", "rule1")
        sel.glue_test_result = GlueRuleResult(outcome="Failed")
        sel.glue_tested_at = "2026-01-01T00:00:00"
        sel.glue_tested_syntax_hash = "old_hash"

        new_result = GlueRuleResult(outcome="Passed")
        applied, skipped = svc.apply_results_to_cart([sel], {"p1": new_result})

        assert applied == 1
        assert sel.glue_test_result.passed is True
        assert sel.glue_tested_at != "2026-01-01T00:00:00"

    def test_empty_correlation_map(self):
        svc = _make_svc()
        cart = [_make_selection("p1", RuleType.COMPLETENESS, "col_a", "rule1")]
        applied, skipped = svc.apply_results_to_cart(cart, {})
        assert applied == 0
        assert skipped == 1
        assert cart[0].has_test_result is False

    def test_empty_cart(self):
        svc = _make_svc()
        applied, skipped = svc.apply_results_to_cart([], {"p1": GlueRuleResult()})
        assert applied == 0
        assert skipped == 0

    def test_stale_detection_after_apply(self):
        """After apply, stale is False. After syntax change, stale is True."""
        svc = _make_svc()
        sel = _make_selection("p1", RuleType.COMPLETENESS, "col_a", "rule1")
        svc.apply_results_to_cart([sel], {"p1": GlueRuleResult(outcome="Passed")})

        assert sel.is_test_stale is False

        # Simulate syntax change
        sel.final_gdq_syntax = "rule1_modified"
        assert sel.is_test_stale is True


# --- End-to-end: correlate + apply ---

class TestCorrelateAndApplyEndToEnd:
    def test_full_flow(self):
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.MEAN_DUAL_GUARD, "vlr_saldo", "Mean VLR_SALDO rule"),
            _make_selection("p2", RuleType.COMPLETENESS, "vlr_saldo", "Completeness vlr_saldo >= 0.95"),
        ]
        glue_results = [
            _make_glue_result(
                "Mean VLR_SALDO rule", "Passed",
                metrics={"Dataset.*.Mean": 1234.56},
            ),
            _make_glue_result(
                "Completeness vlr_saldo >= 0.95", "Failed",
                metrics={"Dataset.*.Completeness": 0.89},
                failure_reason="Expected >= 0.95, got 0.89",
            ),
        ]

        corr_map, report = svc.correlate_results(cart, glue_results)
        assert report.matched == 2
        assert report.orphaned == 0

        applied, skipped = svc.apply_results_to_cart(cart, corr_map)
        assert applied == 2
        assert skipped == 0

        # p1: passed
        assert cart[0].has_test_result is True
        assert cart[0].glue_test_result.passed is True
        assert cart[0].glue_test_result.metric_value == 1234.56

        # p2: failed
        assert cart[1].has_test_result is True
        assert cart[1].glue_test_result.passed is False
        assert "0.89" in cart[1].glue_test_result.failure_reason

    def test_cart_item_removed_between_test_and_apply(self):
        """If cart item was removed, apply just skips it gracefully."""
        svc = _make_svc()
        cart = [
            _make_selection("p2", RuleType.COMPLETENESS, "col_b", "rule2"),
        ]
        # p1 was in the cart during test but removed before apply
        corr_map = {
            "p1": GlueRuleResult(outcome="Passed"),
            "p2": GlueRuleResult(outcome="Failed"),
        }
        applied, skipped = svc.apply_results_to_cart(cart, corr_map)
        assert applied == 1  # p2 matched
        assert skipped == 0  # p2 was the only cart item

    def test_no_results_no_write_back(self):
        """When Glue returns no parseable results, nothing happens."""
        svc = _make_svc()
        cart = [
            _make_selection("p1", RuleType.COMPLETENESS, "col_a", "rule1"),
        ]
        corr_map, report = svc.correlate_results(cart, [])
        applied, _ = svc.apply_results_to_cart(cart, corr_map)
        assert applied == 0
        assert cart[0].has_test_result is False
