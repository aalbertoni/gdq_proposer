"""Testes para core/glue_log_parser.py."""

import pytest

from core.glue_log_parser import (
    parse_glue_log, _extract_rule_label,
    _extract_rule_category_and_column, _extract_compiled_range,
    _extract_balanced_list, _strip_log_prefix, _is_balanced,
    _dict_to_rule_result, _extract_limits_from_evaluated_rule,
    explain_result, explain_compiled_rule, fmt_number,
)
from core.models.glue_test import GlueRuleResult


class TestParseGlueLog:
    def test_empty_log(self):
        assert parse_glue_log("") == []

    def test_no_results(self):
        log = "INFO:root:Criando Tabela Temporária\nINFO:root:Done"
        assert parse_glue_log(log) == []

    def test_resultados_gdq_inline(self):
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Completeness col1 >= 0.95', "
            "'outcome': 'Passed', 'evaluatedmetrics': {'Dataset.*.Completeness': 0.98}, "
            "'failurereason': ''}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].rule_syntax == "Completeness col1 >= 0.95"
        assert results[0].evaluated_metrics["Dataset.*.Completeness"] == 0.98

    def test_failed_rule(self):
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Mean vlr_saldo >= 100', "
            "'outcome': 'Failed', 'evaluatedmetrics': {'Dataset.*.Mean': 85.0}, "
            "'failurereason': 'Value below threshold'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].failure_reason == "Value below threshold"

    def test_multiple_rules(self):
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'R1', 'outcome': 'Passed', "
            "'evaluatedmetrics': {}, 'failurereason': ''}, "
            "{'rule': 'R2', 'outcome': 'Failed', "
            "'evaluatedmetrics': {}, 'failurereason': 'err'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

    def test_book_qualidades_pattern(self):
        log = (
            "INFO:BookQualidades:Salvando {'Rule': 'Completeness col1 >= 0.95', "
            "'Outcome': 'Passed', 'FailureReason': '', "
            "'EvaluatedMetrics': {'Dataset.*.Completeness': 0.98}} more text"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].rule_syntax == "Completeness col1 >= 0.95"

    def test_deduplication(self):
        """Same rule from both sources should not be duplicated."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Completeness col1 >= 0.95', "
            "'outcome': 'Passed', 'evaluatedmetrics': {}, 'failurereason': ''}]\n"
            "INFO:BookQualidades:Salvando {'Rule': 'Completeness col1 >= 0.95', "
            "'Outcome': 'Passed', 'FailureReason': '', 'EvaluatedMetrics': {}} end"
        )
        results = parse_glue_log(log)
        assert len(results) == 1

    def test_dedup_pattern2_replaces_pattern1_with_evaluated_rule(self):
        """Pattern 2 (BookQualidades) with EvaluatedRule replaces Pattern 1 without it."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Mean vlr_saldo >= 100', "
            "'outcome': 'Passed', 'evaluatedmetrics': {'Dataset.*.Mean': 150.0}, "
            "'failurereason': ''}]\n"
            "INFO:BookQualidades:Salvando {'Rule': 'Mean vlr_saldo >= 100', "
            "'Outcome': 'Passed', 'FailureReason': '', "
            "'EvaluatedMetrics': {'Dataset.*.Mean': 150.0}, "
            "'EvaluatedRule': 'Mean vlr_saldo >= 120.5'} end"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].evaluated_rule == "Mean vlr_saldo >= 120.5"

    def test_dedup_pattern1_kept_when_both_have_evaluated_rule(self):
        """When both patterns have evaluated_rule, Pattern 1 is kept (no replacement)."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Mean vlr_saldo >= 100', "
            "'outcome': 'Passed', 'evaluatedmetrics': {'Dataset.*.Mean': 150.0}, "
            "'failurereason': '', 'evaluatedrule': 'Mean vlr_saldo >= 110.0'}]\n"
            "INFO:BookQualidades:Salvando {'Rule': 'Mean vlr_saldo >= 100', "
            "'Outcome': 'Passed', 'FailureReason': '', "
            "'EvaluatedMetrics': {'Dataset.*.Mean': 150.0}, "
            "'EvaluatedRule': 'Mean vlr_saldo >= 120.5'} end"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].evaluated_rule == "Mean vlr_saldo >= 110.0"

    def test_dedup_pattern2_only_with_evaluated_rule(self):
        """Pattern 2 alone (no Pattern 1) correctly captures EvaluatedRule."""
        log = (
            "INFO:BookQualidades:Salvando {'Rule': 'Completeness col1 >= 0.95', "
            "'Outcome': 'Passed', 'FailureReason': '', "
            "'EvaluatedMetrics': {'Dataset.*.Completeness': 0.98}, "
            "'EvaluatedRule': 'Completeness col1 >= 0.95'} end"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].evaluated_rule == "Completeness col1 >= 0.95"

    def test_failure_reason_newline_cleanup(self):
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'R1', 'outcome': 'Failed', "
            "'evaluatedmetrics': {}, 'failurereason': 'reason1\\nreason2'}]"
        )
        results = parse_glue_log(log)
        assert "|" in results[0].failure_reason

    def test_customsql_rule(self):
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': '(CustomSql \"select approx_percentile("
            "cast(vlr_limi_excs as double), 0.99) from primary\" between "
            "(avg(last(30)) - (3 * std(last(30))) - 0.01) and "
            "(avg(last(30)) + (3 * std(last(30))) + 0.01)) OR "
            "(CustomSql \"select approx_percentile(cast(vlr_limi_excs as double), 0.99) "
            "from primary\" between (avg(last(30)) * 0.97 - 0.01) and "
            "(avg(last(30)) * 1.03 + 0.01))', "
            "'outcome': 'Failed', 'evaluatedmetrics': "
            "{'Dataset.*.CustomSQL': 492.73}, "
            "'failurereason': 'Custom SQL response failed to satisfy the threshold'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].evaluated_metrics["Dataset.*.CustomSQL"] == 492.73

    def test_rule_label_enrichment(self):
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Completeness vlr_saldo >= 0.95', "
            "'outcome': 'Passed', 'evaluatedmetrics': {}, 'failurereason': ''}]"
        )
        results = parse_glue_log(log)
        assert results[0].rule_label == "Completeness vlr_saldo"


class TestExtractRuleLabel:
    def test_completeness(self):
        assert _extract_rule_label("Completeness vlr_saldo >= 0.95") == "Completeness vlr_saldo"

    def test_mean_dual_guard(self):
        label = _extract_rule_label("((Mean vlr_saldo >= ...) AND ...)")
        assert "Mean" in label
        assert "vlr_saldo" in label

    def test_customsql(self):
        label = _extract_rule_label(
            '(CustomSql "select avg(cast(vlr as double)) from primary" between 1 and 10)'
        )
        assert "CustomSql" in label
        assert "avg" in label

    def test_column_values(self):
        assert _extract_rule_label("ColumnValues status in [1, 2, 3]") == "ColumnValues status"

    def test_short_syntax(self):
        assert _extract_rule_label("RowCount >= 100") == "RowCount"


class TestExtractRuleCategoryAndColumn:
    def test_completeness(self):
        cat, col = _extract_rule_category_and_column("Completeness vlr_saldo >= 0.95")
        assert cat == "Completeness"
        assert col == "vlr_saldo"

    def test_mean_dual_guard(self):
        cat, col = _extract_rule_category_and_column(
            "((Mean VLR_SALDO >= (avg(last(30)) - ...)) AND ...)"
        )
        assert cat == "Mean"
        assert col == "VLR_SALDO"

    def test_customsql_percentile(self):
        cat, col = _extract_rule_category_and_column(
            '(CustomSql "select approx_percentile(cast(vlr_limi as double), 0.99) from primary" between 1 and 10)'
        )
        assert cat == "Percentil"
        assert col == "vlr_limi"

    def test_customsql_frequency(self):
        cat, col = _extract_rule_category_and_column(
            '(CustomSql "select cast(sum(case when COD_SITU = \'1\' then 1 else 0 end) as double) * 100.0 / count(*) from primary" >= 85)'
        )
        assert cat == "Frequencia"
        assert col == "COD_SITU"

    def test_column_values(self):
        cat, col = _extract_rule_category_and_column("ColumnValues status in [1, 2, 3]")
        assert cat == "ColumnValues"
        assert col == "status"

    def test_isprimarykey(self):
        cat, col = _extract_rule_category_and_column("IsPrimaryKey COL_A COL_B")
        assert cat == "IsPrimaryKey"
        assert "COL_A" in col
        assert "COL_B" in col

    def test_rowcount(self):
        cat, col = _extract_rule_category_and_column("RowCount >= 100")
        assert cat == "RowCount"
        assert col == ""


class TestExtractCompiledRange:
    def test_expected_range_pattern(self):
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult(failure_reason="Value: 85 does not meet constraint! ExpectedRange: [80.5, 120.3]")
        _extract_compiled_range(r)
        assert r.compiled_lower == 80.5
        assert r.compiled_upper == 120.3

    def test_between_pattern(self):
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult(failure_reason="Expected between 100.00 and 200.00 but got 250")
        _extract_compiled_range(r)
        assert r.compiled_lower == 100.0
        assert r.compiled_upper == 200.0

    def test_threshold_pattern(self):
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult(failure_reason="Value 0.85 does not satisfy >= 0.95")
        _extract_compiled_range(r)
        assert r.compiled_lower == 0.95
        assert r.compiled_upper is None

    def test_no_failure_reason(self):
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult(failure_reason="")
        _extract_compiled_range(r)
        assert r.compiled_lower is None
        assert r.compiled_upper is None

    def test_enrichment_via_parse(self):
        """Full integration: parse_glue_log enriches category and column."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Completeness vlr_saldo >= 0.95', "
            "'outcome': 'Passed', 'evaluatedmetrics': {'Dataset.*.Completeness': 0.98}, "
            "'failurereason': ''}]"
        )
        results = parse_glue_log(log)
        assert results[0].rule_category == "Completeness"
        assert results[0].target_column == "vlr_saldo"

    def test_limits_from_evaluated_rule(self):
        """Compiled limits extracted from evaluated_rule field."""
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult(
            evaluated_rule="Mean VLR_SALDO between 1234.56 and 5678.90",
        )
        _extract_compiled_range(r)
        assert r.compiled_lower == 1234.56
        assert r.compiled_upper == 5678.90

    def test_limits_from_evaluated_rule_gte_lte(self):
        """Compiled limits from >= and <= in evaluated_rule."""
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult(
            evaluated_rule="(Mean VLR >= 100.5) AND (Mean VLR <= 500.3)",
        )
        _extract_compiled_range(r)
        assert r.compiled_lower == 100.5
        assert r.compiled_upper == 500.3

    def test_evaluated_rule_takes_priority_over_failure_reason(self):
        """evaluated_rule is preferred over failure_reason for limits."""
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult(
            failure_reason="ExpectedRange: [10.0, 20.0]",
            evaluated_rule="Mean COL between 100.0 and 200.0",
        )
        _extract_compiled_range(r)
        # Should use evaluated_rule limits (100, 200) not failure_reason (10, 20)
        assert r.compiled_lower == 100.0
        assert r.compiled_upper == 200.0

    def test_no_limits_falls_back_to_failure_reason(self):
        """If evaluated_rule has no limits, falls back to failure_reason."""
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult(
            failure_reason="ExpectedRange: [80.5, 120.3]",
            evaluated_rule="Mean COL something without numbers",
        )
        _extract_compiled_range(r)
        assert r.compiled_lower == 80.5
        assert r.compiled_upper == 120.3


class TestTypeMismatchError:
    """Tests for type mismatch errors (column type rejected by GDQ)."""

    def test_type_mismatch_failure_preserved(self):
        """Type mismatch error message is preserved in failure_reason."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Mean VLR_CNTR_OPCR >= 100', "
            "'outcome': 'Failed', "
            "'evaluatedmetrics': {}, "
            "'failurereason': 'expected type of column VLR_CNTR_OPCR to be one of "
            "(longtype,integertype,doubletype,decimaltype) but found string instead', "
            "'evaluatedrule': ''}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].passed is False
        assert "expected type" in results[0].failure_reason
        assert "string instead" in results[0].failure_reason
        # No metrics when type mismatch (rule didn't execute)
        assert results[0].metric_value is None

    def test_type_mismatch_no_compiled_limits(self):
        """Type mismatch errors have no compiled limits."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': "
            "'((Mean VLR_CNTR_OPCR >= (avg(last(30)) - (3 * std(last(30))) - 0.01)) "
            "AND (Mean VLR_CNTR_OPCR <= (avg(last(30)) + (3 * std(last(30))) + 0.01)))', "
            "'outcome': 'Failed', "
            "'evaluatedmetrics': {}, "
            "'failurereason': 'expected type of column VLR_CNTR_OPCR to be one of "
            "(longtype,integertype,doubletype,decimaltype) but found string instead', "
            "'evaluatedrule': ''}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].compiled_lower is None
        assert results[0].compiled_upper is None

    def test_multiple_rules_with_type_mismatch(self):
        """Mix of type mismatch and normal results."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:["
            "{'rule': 'Mean VLR_CNTR_OPCR >= 100', "
            "'outcome': 'Failed', "
            "'evaluatedmetrics': {}, "
            "'failurereason': 'expected type of column VLR_CNTR_OPCR to be one of "
            "(longtype,integertype,doubletype,decimaltype) but found string instead', "
            "'evaluatedrule': ''}, "
            "{'rule': 'Completeness VLR_SALDO >= 0.95', "
            "'outcome': 'Passed', "
            "'evaluatedmetrics': {'Dataset.*.Completeness': 0.99}, "
            "'failurereason': '', "
            "'evaluatedrule': 'Completeness VLR_SALDO >= 0.95'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 2
        # First: type mismatch
        assert results[0].passed is False
        assert "expected type" in results[0].failure_reason
        assert results[0].metric_value is None
        # Second: normal pass
        assert results[1].passed is True
        assert results[1].metric_value == 0.99


class TestEvaluatedRuleExtraction:
    """Tests for evaluatedrule field parsing and limit extraction."""

    def test_evaluatedrule_extracted(self):
        """evaluatedrule field is extracted from log dict."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': "
            "'(CustomSql \"select approx_percentile(cast(vlr_limi as double), 0.99) "
            "from primary\" between (avg(last(30)) - (3 * std(last(30))) - 0.01) and "
            "(avg(last(30)) + (3 * std(last(30))) + 0.01))', "
            "'outcome': 'Passed', "
            "'evaluatedmetrics': {'Dataset.*.CustomSQL': 492.73}, "
            "'failurereason': '', "
            "'evaluatedrule': '(CustomSql \"select approx_percentile(cast(vlr_limi as double), "
            "0.99) from primary\" between 350.12 and 600.45)'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].evaluated_rule != ""
        assert "between 350.12 and 600.45" in results[0].evaluated_rule
        # Compiled limits from evaluated_rule
        assert results[0].compiled_lower == 350.12
        assert results[0].compiled_upper == 600.45

    def test_evaluatedrule_empty_string(self):
        """Empty evaluatedrule is handled gracefully."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Mean COL >= 100', "
            "'outcome': 'Failed', "
            "'evaluatedmetrics': {}, "
            "'failurereason': 'type error', "
            "'evaluatedrule': ''}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].evaluated_rule == ""

    def test_evaluatedrule_with_expanded_dual_guard(self):
        """evaluatedrule shows expanded avg/std values."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': "
            "'((Mean VLR_SALDO >= (avg(last(30)) - (3 * std(last(30))) - 0.01)) "
            "AND (Mean VLR_SALDO <= (avg(last(30)) + (3 * std(last(30))) + 0.01)))', "
            "'outcome': 'Passed', "
            "'evaluatedmetrics': {'Dataset.*.Mean': 1500.0}, "
            "'failurereason': '', "
            "'evaluatedrule': '((Mean VLR_SALDO >= 1200.50) AND (Mean VLR_SALDO <= 1800.30))'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].compiled_lower == 1200.50
        assert results[0].compiled_upper == 1800.30

    def test_dict_to_rule_result_evaluatedrule(self):
        """_dict_to_rule_result extracts evaluatedrule key."""
        d = {
            "rule": "Mean COL between 1 and 2",
            "outcome": "Passed",
            "evaluatedmetrics": {},
            "failurereason": "",
            "evaluatedrule": "Mean COL between 100.5 and 200.3",
        }
        result = _dict_to_rule_result(d)
        assert result.evaluated_rule == "Mean COL between 100.5 and 200.3"

    def test_dict_to_rule_result_evaluated_rule_underscore(self):
        """_dict_to_rule_result also handles evaluated_rule (underscore variant)."""
        d = {
            "rule": "Mean COL between 1 and 2",
            "outcome": "Passed",
            "evaluatedmetrics": {},
            "failurereason": "",
            "evaluated_rule": "Mean COL between 100.5 and 200.3",
        }
        result = _dict_to_rule_result(d)
        assert result.evaluated_rule == "Mean COL between 100.5 and 200.3"


class TestExtractLimitsFromEvaluatedRule:
    """Tests for _extract_limits_from_evaluated_rule."""

    def test_between_pattern(self):
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult()
        _extract_limits_from_evaluated_rule(r, "CustomSql ... between 350.12 and 600.45")
        assert r.compiled_lower == 350.12
        assert r.compiled_upper == 600.45

    def test_gte_and_lte_separate(self):
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult()
        _extract_limits_from_evaluated_rule(
            r, "((Mean VLR >= 1200.50) AND (Mean VLR <= 1800.30))"
        )
        assert r.compiled_lower == 1200.50
        assert r.compiled_upper == 1800.30

    def test_only_gte(self):
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult()
        _extract_limits_from_evaluated_rule(r, "Completeness COL >= 0.95")
        assert r.compiled_lower == 0.95
        assert r.compiled_upper is None

    def test_scientific_notation(self):
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult()
        _extract_limits_from_evaluated_rule(r, "Mean COL between 1.5e+03 and 2.0e+03")
        assert r.compiled_lower == 1500.0
        assert r.compiled_upper == 2000.0

    def test_no_numbers(self):
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult()
        _extract_limits_from_evaluated_rule(r, "Mean COL something without numbers")
        assert r.compiled_lower is None
        assert r.compiled_upper is None

    def test_negative_numbers(self):
        from core.models.glue_test import GlueRuleResult
        r = GlueRuleResult()
        _extract_limits_from_evaluated_rule(r, "Mean COL between -100.5 and 200.3")
        assert r.compiled_lower == -100.5
        assert r.compiled_upper == 200.3


class TestBalancedListExtraction:
    """Tests for bracket-balanced extraction logic."""

    def test_simple_list(self):
        text = "some prefix [{'a': 1}]"
        result = _extract_balanced_list(text, 12)  # after "some prefix "
        assert result == "[{'a': 1}]"

    def test_nested_brackets_in_strings(self):
        text = "[{'rule': 'ColumnValues col in [1, 2, 3]', 'outcome': 'Passed'}]"
        result = _extract_balanced_list(text, 0)
        assert result == text

    def test_skips_log_prefix(self):
        text = "Resultados GDQ:\nINFO:DistribuicaoDeDados:[{'rule': 'R1'}]"
        result = _extract_balanced_list(text, len("Resultados GDQ:"))
        assert result is not None
        assert "'rule': 'R1'" in result

    def test_skips_whitespace_and_newlines(self):
        text = "marker:  \n  \n  [{'r': 1}]"
        result = _extract_balanced_list(text, 7)  # after "marker:"
        assert result == "[{'r': 1}]"

    def test_returns_none_if_no_bracket(self):
        text = "no brackets here at all just text"
        result = _extract_balanced_list(text, 0)
        assert result is None

    def test_returns_none_if_unbalanced(self):
        text = "[{'rule': 'R1', 'outcome': 'Passed'"
        result = _extract_balanced_list(text, 0)
        assert result is None

    def test_handles_escaped_quotes(self):
        text = r"""[{'rule': 'CustomSql "select avg(col) from primary"', 'outcome': 'Passed'}]"""
        result = _extract_balanced_list(text, 0)
        assert result is not None
        assert "CustomSql" in result


class TestStripLogPrefix:
    """Tests for _strip_log_prefix."""

    def test_info_prefix(self):
        assert _strip_log_prefix("INFO:DistribuicaoDeDados:something") == "something"

    def test_timestamp_prefix(self):
        result = _strip_log_prefix("2026-03-24T12:00:00.000Z some text")
        assert result == "some text"

    def test_both_timestamp_and_info(self):
        result = _strip_log_prefix("2026-03-24T12:00:00.000Z INFO:Module:data")
        assert result == "data"

    def test_no_prefix(self):
        assert _strip_log_prefix("[{'rule': 'R1'}]") == "[{'rule': 'R1'}]"

    def test_warning_prefix(self):
        assert _strip_log_prefix("WARNING:SomeModule:message") == "message"

    def test_empty(self):
        assert _strip_log_prefix("") == ""


class TestIsBalanced:
    """Tests for bracket balancing check."""

    def test_balanced(self):
        assert _is_balanced("[1, 2, 3]", "[", "]") is True

    def test_unbalanced(self):
        assert _is_balanced("[1, 2, [3", "[", "]") is False

    def test_nested(self):
        assert _is_balanced("[[1, 2], [3, 4]]", "[", "]") is True

    def test_brackets_in_strings(self):
        assert _is_balanced("['a[b]c']", "[", "]") is True

    def test_empty(self):
        assert _is_balanced("", "[", "]") is True


class TestRealWorldLogFormats:
    """Tests simulating real-world Glue log output patterns."""

    def test_distribuicao_inline_single_line(self):
        """Single line with INFO:DistribuicaoDeDados: prefix."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:"
            "[{'rule': 'Completeness VLR_SALDO >= 1.00', "
            "'outcome': 'Passed', "
            "'evaluatedmetrics': {'Dataset.*.Completeness': 1.0}, "
            "'failurereason': '', "
            "'evaluatedrule': 'Completeness VLR_SALDO >= 1.00'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].evaluated_rule == "Completeness VLR_SALDO >= 1.00"

    def test_distribuicao_next_line(self):
        """List on next line after Resultados GDQ marker."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Mean VLR >= 100', "
            "'outcome': 'Passed', "
            "'evaluatedmetrics': {'Dataset.*.Mean': 150.0}, "
            "'failurereason': '', "
            "'evaluatedrule': 'Mean VLR >= 100'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].passed is True

    def test_three_rules_mixed_results(self):
        """Real scenario: 3 rules — 2 type errors + 1 percentile pass."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:["
            "{'rule': '((Mean VLR_CNTR_OPCR >= (avg(last(30)) - (3 * std(last(30))) - 0.01)) "
            "AND (Mean VLR_CNTR_OPCR <= (avg(last(30)) + (3 * std(last(30))) + 0.01)))', "
            "'outcome': 'Failed', "
            "'evaluatedmetrics': {}, "
            "'failurereason': 'expected type of column VLR_CNTR_OPCR to be one of "
            "(longtype,integertype,doubletype,decimaltype) but found string instead', "
            "'evaluatedrule': ''}, "
            "{'rule': '((StandardDeviation VLR_CNTR_OPCR >= (avg(last(30)) - (3 * std(last(30))) - 0.01)) "
            "AND (StandardDeviation VLR_CNTR_OPCR <= (avg(last(30)) + (3 * std(last(30))) + 0.01)))', "
            "'outcome': 'Failed', "
            "'evaluatedmetrics': {}, "
            "'failurereason': 'expected type of column VLR_CNTR_OPCR to be one of "
            "(longtype,integertype,doubletype,decimaltype) but found string instead', "
            "'evaluatedrule': ''}, "
            "{'rule': '(CustomSql \"select approx_percentile(cast(VLR_CNTR_OPCR as double), 0.99) "
            "from primary\" between (avg(last(30)) - (3 * std(last(30))) - 0.01) and "
            "(avg(last(30)) + (3 * std(last(30))) + 0.01))', "
            "'outcome': 'Passed', "
            "'evaluatedmetrics': {'Dataset.*.CustomSQL': 492.73}, "
            "'failurereason': '', "
            "'evaluatedrule': '(CustomSql \"select approx_percentile(cast(VLR_CNTR_OPCR as double), "
            "0.99) from primary\" between 350.12 and 600.45)'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 3

        # Rule 1: Mean type mismatch
        r1 = results[0]
        assert r1.passed is False
        assert "expected type" in r1.failure_reason
        assert r1.metric_value is None
        assert r1.evaluated_rule == ""
        assert r1.compiled_lower is None
        assert r1.compiled_upper is None
        assert r1.rule_category == "Mean"
        assert r1.target_column == "VLR_CNTR_OPCR"

        # Rule 2: StdDev type mismatch
        r2 = results[1]
        assert r2.passed is False
        assert "expected type" in r2.failure_reason
        assert r2.rule_category == "StandardDeviation"
        assert r2.target_column == "VLR_CNTR_OPCR"

        # Rule 3: Percentile passed with evaluated limits
        r3 = results[2]
        assert r3.passed is True
        assert r3.metric_value == 492.73
        assert r3.evaluated_rule != ""
        assert r3.compiled_lower == 350.12
        assert r3.compiled_upper == 600.45
        assert r3.rule_category == "Percentil"
        assert r3.target_column == "VLR_CNTR_OPCR"

    def test_multiline_list_with_log_prefixes(self):
        """List split across multiple lines, each with INFO prefix."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Completeness COL >= 0.95',\n"
            "INFO:DistribuicaoDeDados: 'outcome': 'Passed',\n"
            "INFO:DistribuicaoDeDados: 'evaluatedmetrics': {'Dataset.*.Completeness': 0.99},\n"
            "INFO:DistribuicaoDeDados: 'failurereason': '',\n"
            "INFO:DistribuicaoDeDados: 'evaluatedrule': 'Completeness COL >= 0.95'}]"
        )
        results = parse_glue_log(log)
        # The balanced list extraction should handle this since it operates
        # on the full text (not line-by-line)
        assert len(results) == 1
        assert results[0].passed is True

    def test_passed_percentile_with_metrics(self):
        """Percentile rule that passed — metrics should be present."""
        log = (
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': "
            "'(CustomSql \"select approx_percentile(cast(VLR as double), 0.99) "
            "from primary\" between (avg(last(30)) - (3 * std(last(30))) - 0.01) "
            "and (avg(last(30)) + (3 * std(last(30))) + 0.01))', "
            "'outcome': 'Passed', "
            "'evaluatedmetrics': {'Dataset.*.CustomSQL': 1234.56}, "
            "'failurereason': '', "
            "'evaluatedrule': '(CustomSql \"select approx_percentile(cast(VLR as double), "
            "0.99) from primary\" between 1000.00 and 1500.00)'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].passed is True
        assert results[0].metric_value == 1234.56
        assert results[0].compiled_lower == 1000.0
        assert results[0].compiled_upper == 1500.0

    def test_log_with_extra_noise(self):
        """Log with irrelevant lines before and after results."""
        log = (
            "INFO:root:Criando Tabela Temporaria\n"
            "INFO:root:Tabela criada com sucesso\n"
            "INFO:DistribuicaoDeDados:Processando regras...\n"
            "INFO:DistribuicaoDeDados:Resultados GDQ:\n"
            "INFO:DistribuicaoDeDados:[{'rule': 'Mean VLR >= 100', "
            "'outcome': 'Passed', 'evaluatedmetrics': {'Dataset.*.Mean': 150.0}, "
            "'failurereason': '', 'evaluatedrule': 'Mean VLR >= 100'}]\n"
            "INFO:root:Finalizando processamento\n"
            "INFO:root:Job concluido"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].passed is True

    def test_empty_evaluatedmetrics_dict(self):
        """Empty evaluatedmetrics dict (type error — rule not executed)."""
        d = {
            "rule": "Mean COL >= 100",
            "outcome": "Failed",
            "evaluatedmetrics": {},
            "failurereason": "type error",
            "evaluatedrule": "",
        }
        result = _dict_to_rule_result(d)
        assert result.evaluated_metrics == {}
        assert result.metric_value is None

    def test_evaluatedmetrics_string_value(self):
        """evaluatedmetrics as unparseable string yields empty metrics."""
        d = {
            "rule": "Mean COL >= 100",
            "outcome": "Failed",
            "evaluatedmetrics": "N/A",
            "failurereason": "error",
            "evaluatedrule": "",
        }
        result = _dict_to_rule_result(d)
        assert result.evaluated_metrics == {}

    def test_evaluatedmetrics_json_string(self):
        """evaluatedmetrics as JSON string is parsed correctly."""
        d = {
            "rule": "Mean COL >= 100",
            "outcome": "Passed",
            "evaluatedmetrics": '{"Column.COL.Mean": 42.5}',
            "failurereason": "None",
        }
        result = _dict_to_rule_result(d)
        assert result.evaluated_metrics == {"Column.COL.Mean": 42.5}


class TestInfoPrefixLogFormat:
    """Test parsing of INFO:ModuleName:[...] log format."""

    def test_info_distribuicao_format(self):
        log = (
            "INFO:DistribuicaoDeDados:[{'rule': 'Completeness COL >= 1.00', "
            "'outcome': 'Passed', "
            "'evaluatedmetrics': '{\"Column.COL.Completeness\": 1.0}', "
            "'failurereason': 'None'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].outcome == "Passed"
        assert results[0].rule_category == "Completeness"
        assert results[0].target_column == "COL"
        assert results[0].evaluated_metrics == {"Column.COL.Completeness": 1.0}

    def test_info_format_with_rowcount(self):
        log = (
            "INFO:DistribuicaoDeDados:[{'rule': "
            "'((RowCount >= (avg(last(30)) * 1.0 - (3.0 * std(last(30)))))', "
            "'outcome': 'Passed', "
            "'evaluatedmetrics': '{\"Dataset.*.RowCount\": 1395227.0}', "
            "'failurereason': 'None'}]"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        assert results[0].rule_category == "RowCount"
        assert results[0].evaluated_metrics == {"Dataset.*.RowCount": 1395227.0}


class TestBookQualidadesNestedDict:
    """Tests for BookQualidades with nested dicts (EvaluatedMetrics + EvaluatedRule)."""

    def test_nested_metrics_and_evaluated_rule(self):
        """Real-world log: nested EvaluatedMetrics dict + EvaluatedRule field."""
        log = (
            "INFO:BookQualidades:Salvando {'Rule': "
            "'(Mean VLR_CNTR_OPCR >= (avg(last(30)) - (2.5 * std(last(30))) - 0.01)) "
            "AND (Mean VLR_CNTR_OPCR <= (avg(last(30)) + (2.5 * std(last(30))) + 0.01))', "
            "'Outcome': 'Passed', 'FailureReason': None, "
            "'EvaluatedMetrics': {'Column.VLR_CNTR_OPCR.Mean': 61646.02100276873}, "
            "'EvaluatedRule': '(Mean VLR_CNTR_OPCR >= 61636.17) AND "
            "(Mean VLR_CNTR_OPCR <= 61653.81)'}\n"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        r = results[0]
        assert r.passed is True
        assert r.evaluated_metrics == {"Column.VLR_CNTR_OPCR.Mean": 61646.02100276873}
        assert r.evaluated_rule == (
            "(Mean VLR_CNTR_OPCR >= 61636.17) AND (Mean VLR_CNTR_OPCR <= 61653.81)"
        )
        assert r.compiled_lower == 61636.17
        assert r.compiled_upper == 61653.81
        assert r.rule_category == "Mean"
        assert r.target_column == "VLR_CNTR_OPCR"

    def test_stddev_with_nested_dict(self):
        """StandardDeviation with nested EvaluatedMetrics and EvaluatedRule."""
        log = (
            "INFO:BookQualidades:Salvando {'Rule': "
            "'((StandardDeviation VLR >= (avg(last(30)) - (2.5 * std(last(30)))) - 0.01)) "
            "AND (StandardDeviation VLR <= (avg(last(30)) + (2.5 * std(last(30))) + 0.01))', "
            "'Outcome': 'Passed', 'FailureReason': None, "
            "'EvaluatedMetrics': {'Column.VLR.StandardDeviation': 136179.47}, "
            "'EvaluatedRule': '(StandardDeviation VLR >= 136162.41) AND "
            "(StandardDeviation VLR <= 136209.97)'}\n"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        r = results[0]
        assert r.evaluated_rule != ""
        assert r.compiled_lower == 136162.41
        assert r.compiled_upper == 136209.97

    def test_customsql_dual_guard_with_nested_dict(self):
        """CustomSql percentile dual guard — complex nested structure."""
        log = (
            "INFO:BookQualidades:Salvando {'Rule': "
            "'((CustomSql \"select approx_percentile(cast(VLR as double), 0.99) "
            "from primary\" >= (avg(last(20)) - (2 * std(last(20))) - 0.01)))', "
            "'Outcome': 'Passed', 'FailureReason': 'Custom SQL response failed.', "
            "'EvaluatedMetrics': {'Dataset.*.CustomSQL': 547258.05, "
            "'Dataset.abc123.CustomSQL': 547258.05}, "
            "'EvaluatedRule': '(((CustomSql \"select approx_percentile(cast(VLR as double), 0.99) "
            "from primary\" >= 338092.54) AND (CustomSql \"select approx_percentile(cast(VLR "
            "as double), 0.99) from primary\" <= 650811.43)))'}\n"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        r = results[0]
        assert r.compiled_lower == 338092.54
        assert r.compiled_upper == 650811.43
        # Two metrics with same value — deduplication happens in UI, not parser
        assert len(r.evaluated_metrics) == 2

    def test_completeness_simple_dict(self):
        """Completeness — no nested EvaluatedMetrics (single level)."""
        log = (
            "INFO:BookQualidades:Salvando {'Rule': 'Completeness VLR >= 1.00', "
            "'Outcome': 'Passed', 'FailureReason': None, "
            "'EvaluatedMetrics': {'Column.VLR.Completeness': 1.0}, "
            "'EvaluatedRule': 'completeness VLR >= 1.00'}\n"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        r = results[0]
        assert r.passed is True
        assert r.evaluated_rule == "completeness VLR >= 1.00"
        assert r.compiled_lower == 1.0

    def test_multiple_book_qualidades_entries(self):
        """Multiple BookQualidades entries, each with nested dicts."""
        log = (
            "INFO:BookQualidades:Salvando {'Rule': 'Mean A >= 1', 'Outcome': 'Passed', "
            "'FailureReason': None, 'EvaluatedMetrics': {'Column.A.Mean': 10.0}, "
            "'EvaluatedRule': '(Mean A >= 5) AND (Mean A <= 15)'}\n"
            "INFO:BookQualidades:Salvando {'Rule': 'Mean B >= 1', 'Outcome': 'Failed', "
            "'FailureReason': 'out of bounds', 'EvaluatedMetrics': {'Column.B.Mean': 100.0}, "
            "'EvaluatedRule': '(Mean B >= 5) AND (Mean B <= 15)'}\n"
        )
        results = parse_glue_log(log)
        assert len(results) == 2
        assert results[0].passed is True
        assert results[0].compiled_lower == 5.0
        assert results[1].passed is False
        assert results[1].compiled_upper == 15.0

    def test_failure_reason_none_handled(self):
        """FailureReason: None (Python None, not string) is handled."""
        log = (
            "INFO:BookQualidades:Salvando {'Rule': 'Mean A >= 1', 'Outcome': 'Passed', "
            "'FailureReason': None, 'EvaluatedMetrics': {'Column.A.Mean': 10.0}, "
            "'EvaluatedRule': '(Mean A >= 5) AND (Mean A <= 15)'}\n"
        )
        results = parse_glue_log(log)
        assert len(results) == 1
        # None should not cause crash
        assert results[0].failure_reason == "" or results[0].failure_reason == "None"


class TestExtractBalancedBraces:
    """Tests for _extract_balanced_braces."""

    def test_simple_dict(self):
        from core.glue_log_parser import _extract_balanced_braces
        text = "{'a': 1, 'b': 2} rest"
        assert _extract_balanced_braces(text, 0) == "{'a': 1, 'b': 2}"

    def test_nested_dict(self):
        from core.glue_log_parser import _extract_balanced_braces
        text = "{'a': {'inner': 1}, 'b': 2} rest"
        assert _extract_balanced_braces(text, 0) == "{'a': {'inner': 1}, 'b': 2}"

    def test_braces_in_strings_ignored(self):
        from core.glue_log_parser import _extract_balanced_braces
        text = "{'a': 'has } brace', 'b': 2} rest"
        assert _extract_balanced_braces(text, 0) == "{'a': 'has } brace', 'b': 2}"

    def test_not_starting_with_brace(self):
        from core.glue_log_parser import _extract_balanced_braces
        assert _extract_balanced_braces("no brace", 0) is None

    def test_unbalanced(self):
        from core.glue_log_parser import _extract_balanced_braces
        assert _extract_balanced_braces("{'a': 1", 0) is None


class TestExplainResult:
    """Tests for explain_result()."""

    def test_mean(self):
        r = GlueRuleResult(rule_category="Mean", target_column="VLR_SALDO")
        assert "media" in explain_result(r).lower()
        assert "VLR_SALDO" in explain_result(r)

    def test_completeness(self):
        r = GlueRuleResult(rule_category="Completeness", target_column="COL")
        assert "nulos" in explain_result(r).lower()

    def test_rowcount(self):
        r = GlueRuleResult(rule_category="RowCount", target_column="")
        assert "linhas" in explain_result(r).lower()

    def test_isprimarykey(self):
        r = GlueRuleResult(rule_category="IsPrimaryKey", target_column="A B C")
        text = explain_result(r)
        assert "chave primaria" in text.lower()
        assert "A B C" in text

    def test_unknown_category_with_label(self):
        r = GlueRuleResult(rule_category="", rule_label="SomeRule COL")
        assert "SomeRule COL" in explain_result(r)

    def test_unknown_category_no_label(self):
        r = GlueRuleResult(rule_category="", rule_label="")
        assert "customizada" in explain_result(r).lower()


class TestExplainCompiledRule:
    """Tests for explain_compiled_rule()."""

    def test_metric_only(self):
        r = GlueRuleResult(
            rule_category="Mean", target_column="COL",
            evaluated_metrics={"Column.COL.Mean": 42.5},
        )
        text = explain_compiled_rule(r)
        assert "42.50" in text
        assert "Media medida" in text

    def test_metric_and_band(self):
        r = GlueRuleResult(
            rule_category="Mean", target_column="COL",
            evaluated_metrics={"Column.COL.Mean": 50.0},
            compiled_lower=40.0, compiled_upper=60.0,
        )
        text = explain_compiled_rule(r)
        assert "40.00" in text
        assert "60.00" in text
        assert "dentro da faixa" in text.lower()

    def test_metric_outside_band(self):
        r = GlueRuleResult(
            rule_category="Mean", target_column="COL",
            evaluated_metrics={"Column.COL.Mean": 100.0},
            compiled_lower=40.0, compiled_upper=60.0,
        )
        text = explain_compiled_rule(r)
        assert "fora da faixa" in text.lower()

    def test_no_metrics(self):
        r = GlueRuleResult(rule_category="Mean", target_column="COL")
        assert explain_compiled_rule(r) == ""

    def test_single_sided_lower(self):
        r = GlueRuleResult(
            rule_category="Completeness", target_column="COL",
            evaluated_metrics={"Column.COL.Completeness": 1.0},
            compiled_lower=0.95,
        )
        text = explain_compiled_rule(r)
        assert "0.95" in text
        assert "minimo" in text.lower()


class TestFmtNumber:
    """Tests for fmt_number()."""

    def test_large_number(self):
        assert fmt_number(1395227.0) == "1,395,227.00"

    def test_small_number(self):
        assert "0.000931" in fmt_number(0.000931748)

    def test_one(self):
        assert fmt_number(1.0) == "1.00"

    def test_negative(self):
        assert fmt_number(-42.5) == "-42.50"


class TestExtractCategoryColumnEdgeCases:
    """Tests for new branches in _extract_rule_category_and_column."""

    def test_single_paren_wrapper(self):
        syntax = "(Mean COL >= 100) AND (Mean COL <= 200)"
        cat, col = _extract_rule_category_and_column(syntax)
        assert cat == "Mean"
        assert col == "COL"

    def test_deep_search_fallback(self):
        # Weird format that doesn't match standard patterns
        syntax = "some_prefix Completeness MY_COL >= 0.95"
        cat, col = _extract_rule_category_and_column(syntax)
        # Standard match picks up "some_prefix" and "Completeness"
        assert cat == "some_prefix"

    def test_deep_search_when_no_standard_match(self):
        # No standard match at all — deep search kicks in
        syntax = "--- Mean VLR >= 100 ---"
        cat, col = _extract_rule_category_and_column(syntax)
        assert cat == "Mean"
        assert col == "VLR"
