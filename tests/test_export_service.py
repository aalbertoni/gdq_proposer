"""Testes para services/export_service.py."""

import pytest

from core.models.enums import RuleType
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import RuleSelection
from services.export_service import ExportService


@pytest.fixture
def service():
    return ExportService()


def _make_selection(syntax: str, enabled: bool = True) -> RuleSelection:
    proposal = RuleProposal(
        id="test", target_column="COL", target_table="TBL",
        rule_type=RuleType.MEAN_DUAL_GUARD, metric_name="mean",
    )
    return RuleSelection(
        proposal_id="test",
        proposal=proposal,
        enabled=enabled,
        final_gdq_syntax=syntax,
    )


class TestGenerateSyntax:
    def test_single_rule(self, service):
        selections = [_make_selection("Mean COL >= 0.9")]
        result = service.generate_syntax(selections)
        assert result == "Mean COL >= 0.9"

    def test_multiple_rules(self, service):
        selections = [
            _make_selection("Mean COL >= 0.9"),
            _make_selection("Completeness COL >= 1.00"),
        ]
        result = service.generate_syntax(selections)
        assert "Mean COL >= 0.9" in result
        assert "Completeness COL >= 1.00" in result
        assert result.count("\n") == 1

    def test_disabled_rules_excluded(self, service):
        selections = [
            _make_selection("Mean COL >= 0.9", enabled=True),
            _make_selection("StdDev COL >= 0.5", enabled=False),
        ]
        result = service.generate_syntax(selections)
        assert "Mean" in result
        assert "StdDev" not in result

    def test_empty_selections(self, service):
        result = service.generate_syntax([])
        assert result == ""


class TestValidateSyntax:
    def test_valid_syntax(self, service):
        warnings = service.validate_syntax("Mean COL >= 0.9")
        assert warnings == []

    def test_empty_syntax(self, service):
        warnings = service.validate_syntax("")
        assert any("vazia" in w.lower() for w in warnings)

    def test_unbalanced_parens(self, service):
        warnings = service.validate_syntax("((Mean COL >= 0.9)")
        assert any("parenteses" in w.lower() for w in warnings)


class TestExport:
    def test_export_returns_result(self, service):
        selections = [_make_selection("Mean COL >= 0.9")]
        result = service.export(selections)
        assert result.rules_text == "Mean COL >= 0.9"
        assert result.rules_count == 1
        assert result.warnings == []

    def test_export_counts_enabled_only(self, service):
        selections = [
            _make_selection("R1", enabled=True),
            _make_selection("R2", enabled=False),
            _make_selection("R3", enabled=True),
        ]
        result = service.export(selections)
        assert result.rules_count == 2
