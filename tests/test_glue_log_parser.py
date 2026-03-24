"""Testes para core/glue_log_parser.py."""

import pytest

from core.glue_log_parser import parse_glue_log, _extract_rule_label


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
