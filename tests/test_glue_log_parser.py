"""Testes para core/glue_log_parser.py."""

import pytest

from core.glue_log_parser import (
    parse_glue_log, _extract_rule_label,
    _extract_rule_category_and_column, _extract_compiled_range,
)


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
        assert _extract_rule_label("RowCount >= 100") == "RowCount >="


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
