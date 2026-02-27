"""Testes para services/export_service.py."""

import pytest

from core.models.enums import (
    ConfidenceLevel,
    ExportOutputMode,
    RuleType,
)
from core.models.rule_proposal import BacktestSummary, RuleProposal
from core.models.rule_selection import RuleSelection
from services.export_service import ExportService


@pytest.fixture
def service():
    return ExportService()


def _make_selection(
    syntax: str,
    enabled: bool = True,
    rule_type: RuleType = RuleType.MEAN_DUAL_GUARD,
    column: str = "COL",
    table: str = "TBL",
    metric: str = "mean",
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    backtest: BacktestSummary | None = None,
    warnings: list[str] | None = None,
    baseline_window: int | None = None,
    baseline_n_sigma: float | None = None,
    baseline_margin_pct: float | None = None,
    category_value: str | None = None,
    suggested_upper: float | None = None,
    suggested_lower: float | None = None,
) -> RuleSelection:
    proposal = RuleProposal(
        id="test",
        target_column=column,
        target_table=table,
        rule_type=rule_type,
        metric_name=metric,
        confidence=confidence,
        backtest=backtest,
        warnings=warnings or [],
        baseline_window=baseline_window,
        baseline_n_sigma=baseline_n_sigma,
        baseline_margin_pct=baseline_margin_pct,
        category_value=category_value,
        suggested_upper=suggested_upper,
        suggested_lower=suggested_lower,
    )
    return RuleSelection(
        proposal_id="test",
        proposal=proposal,
        enabled=enabled,
        final_gdq_syntax=syntax,
    )


def _make_backtest(**kwargs) -> BacktestSummary:
    defaults = dict(
        total_periods=30,
        periods_pass=28,
        periods_fail=2,
        coverage_pct=93.3,
        false_positive_proxy=1,
        band_width_ratio=0.25,
        stability_score=0.90,
        has_drift=False,
    )
    defaults.update(kwargs)
    return BacktestSummary(**defaults)


# ============================================================================
# generate_syntax
# ============================================================================

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


# ============================================================================
# validate_syntax — basic checks
# ============================================================================

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


# ============================================================================
# validate_syntax — GDQ-specific checks
# ============================================================================

class TestValidateSyntaxGDQ:
    """Validações específicas de sintaxe GDQ."""

    def test_column_with_quotes_warns(self, service):
        """Coluna com aspas em regra built-in deve gerar warning."""
        syntax = 'Mean "COL_NAME" >= 0.9'
        warnings = service.validate_syntax(syntax)
        assert any("aspas" in w.lower() for w in warnings)

    def test_column_without_quotes_ok(self, service):
        """Coluna sem aspas nao gera warning."""
        syntax = "Mean COL_NAME >= 0.9"
        warnings = service.validate_syntax(syntax)
        assert not any("aspas" in w.lower() for w in warnings)

    def test_dynamic_functions_uppercase_warns(self, service):
        """Funcoes dinamicas em UPPERCASE devem gerar warning."""
        syntax = "Mean COL >= AVG(LAST(30))"
        warnings = service.validate_syntax(syntax)
        assert any("lowercase" in w.lower() for w in warnings)

    def test_dynamic_functions_lowercase_ok(self, service):
        """Funcoes dinamicas em lowercase nao geram warning."""
        syntax = "(Mean COL >= (avg(last(30)) - 0.01))"
        warnings = service.validate_syntax(syntax)
        assert not any("lowercase" in w.lower() for w in warnings)

    def test_customsql_unbalanced_quotes_warns(self, service):
        """CustomSql com aspas desbalanceadas."""
        syntax = 'CustomSql "select 1 from primary between 0 and 100'
        warnings = service.validate_syntax(syntax)
        assert any("aspas" in w.lower() for w in warnings)

    def test_customsql_no_from_primary_warns(self, service):
        """CustomSql sem 'from primary'."""
        syntax = 'CustomSql "select 1 from mytable" between 0 and 100'
        warnings = service.validate_syntax(syntax)
        assert any("from primary" in w.lower() for w in warnings)

    def test_customsql_valid_ok(self, service):
        """CustomSql valido nao gera warnings."""
        syntax = (
            'CustomSql "select cast(sum(case when COL = \'A\' then 1 else 0 end) '
            'as double) * 100.0 / count(*) from primary" between 10.0 and 30.0'
        )
        warnings = service.validate_syntax(syntax)
        assert not any("CustomSql" in w for w in warnings)

    def test_completeness_with_between_warns(self, service):
        """Completeness com between deve usar >= ao inves."""
        syntax = "Completeness COL between 0.9 and 1.0"
        warnings = service.validate_syntax(syntax)
        assert any("Completeness" in w and ">=" in w for w in warnings)

    def test_completeness_with_gte_ok(self, service):
        """Completeness com >= nao gera warning."""
        syntax = "Completeness COL >= 1.00"
        warnings = service.validate_syntax(syntax)
        assert not any("Completeness" in w for w in warnings)

    def test_isprimarykey_with_comma_warns(self, service):
        """IsPrimaryKey com virgula deve usar espaco."""
        syntax = "IsPrimaryKey COL1, COL2, COL3"
        warnings = service.validate_syntax(syntax)
        assert any("IsPrimaryKey" in w and "espaco" in w for w in warnings)

    def test_isprimarykey_with_spaces_ok(self, service):
        """IsPrimaryKey com espacos nao gera warning."""
        syntax = "IsPrimaryKey COL1 COL2 COL3"
        warnings = service.validate_syntax(syntax)
        assert not any("IsPrimaryKey" in w for w in warnings)

    def test_valid_dual_guard_syntax(self, service):
        """Dual guard valido nao gera warnings."""
        syntax = (
            "(((Mean VLR_SALDO >= (avg(last(30)) - (2 * std(last(30))) - 0.01)) "
            "AND (Mean VLR_SALDO <= (avg(last(30)) + (2 * std(last(30))) + 0.01))) "
            "OR ((Mean VLR_SALDO >= (avg(last(30)) * 0.9) - 0.01) "
            "AND (Mean VLR_SALDO <= (avg(last(30)) * 1.1) + 0.01)))"
        )
        warnings = service.validate_syntax(syntax)
        assert warnings == []


# ============================================================================
# check_consistency
# ============================================================================

class TestCheckConsistency:
    """Testes de verificacao de consistencia entre regras."""

    def test_no_duplicates_ok(self, service):
        selections = [
            _make_selection("Mean COL >= 0.9", rule_type=RuleType.MEAN_DUAL_GUARD),
            _make_selection(
                "Completeness COL >= 1.00",
                rule_type=RuleType.COMPLETENESS,
            ),
        ]
        warnings = service.check_consistency(selections)
        assert warnings == []

    def test_duplicate_rule_warns(self, service):
        """Mesma coluna + mesmo tipo = duplicata."""
        selections = [
            _make_selection("Mean COL >= 0.9", rule_type=RuleType.MEAN_DUAL_GUARD),
            _make_selection("Mean COL >= 0.8", rule_type=RuleType.MEAN_DUAL_GUARD),
        ]
        warnings = service.check_consistency(selections)
        assert any("duplicada" in w.lower() for w in warnings)

    def test_different_columns_not_duplicate(self, service):
        """Mesmo tipo mas colunas diferentes nao e duplicata."""
        s1 = _make_selection("Mean A >= 0.9", column="A")
        s2 = _make_selection("Mean B >= 0.9", column="B")
        warnings = service.check_consistency([s1, s2])
        assert not any("duplicada" in w.lower() for w in warnings)

    def test_mean_stddev_different_n_warns(self, service):
        """Mean e StdDev com N diferentes geram warning."""
        s1 = _make_selection(
            "Mean COL >= 0.9",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            baseline_window=30,
        )
        s2 = _make_selection(
            "StdDev COL >= 0.5",
            rule_type=RuleType.STDDEV_DUAL_GUARD,
            baseline_window=20,
        )
        warnings = service.check_consistency([s1, s2])
        assert any("N diferentes" in w for w in warnings)

    def test_mean_stddev_same_n_ok(self, service):
        """Mean e StdDev com mesmo N nao geram warning."""
        s1 = _make_selection(
            "Mean COL >= 0.9",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            baseline_window=30,
        )
        s2 = _make_selection(
            "StdDev COL >= 0.5",
            rule_type=RuleType.STDDEV_DUAL_GUARD,
            baseline_window=30,
        )
        warnings = service.check_consistency([s1, s2])
        assert not any("N diferentes" in w for w in warnings)

    def test_disabled_rules_excluded(self, service):
        """Regras desabilitadas nao entram na checagem."""
        selections = [
            _make_selection("Mean COL >= 0.9", enabled=True),
            _make_selection("Mean COL >= 0.8", enabled=False),
        ]
        warnings = service.check_consistency(selections)
        assert not any("duplicada" in w.lower() for w in warnings)

    def test_frequency_different_values_not_duplicate(self, service):
        """Frequencia para valores diferentes nao e duplicata."""
        s1 = _make_selection(
            "CustomSql 1",
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            category_value="A",
        )
        s2 = _make_selection(
            "CustomSql 2",
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            category_value="B",
        )
        warnings = service.check_consistency([s1, s2])
        assert not any("duplicada" in w.lower() for w in warnings)


# ============================================================================
# check_consistency — frequency sum > 100%
# ============================================================================

class TestFrequencySumConflict:
    """Testes para deteccao de soma de frequencias > 100%."""

    def test_frequency_sum_over_100(self, service):
        """Duas regras de frequencia estatica com soma de upper > 100% geram conflito."""
        s1 = _make_selection(
            'CustomSql "..." between 40 and 60',
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            column="STATUS",
            category_value="A",
            suggested_lower=40.0,
            suggested_upper=60.0,
        )
        s2 = _make_selection(
            'CustomSql "..." between 50 and 70',
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            column="STATUS",
            category_value="B",
            suggested_lower=50.0,
            suggested_upper=70.0,
        )
        warnings = service.check_consistency([s1, s2])
        assert any("conflito" in w.lower() and "100%" in w for w in warnings)

    def test_frequency_sum_under_100(self, service):
        """Duas regras de frequencia estatica com soma de upper <= 100% nao geram conflito."""
        s1 = _make_selection(
            'CustomSql "..." between 20 and 40',
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            column="STATUS",
            category_value="A",
            suggested_lower=20.0,
            suggested_upper=40.0,
        )
        s2 = _make_selection(
            'CustomSql "..." between 30 and 50',
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            column="STATUS",
            category_value="B",
            suggested_lower=30.0,
            suggested_upper=50.0,
        )
        warnings = service.check_consistency([s1, s2])
        assert not any("conflito" in w.lower() for w in warnings)

    def test_frequency_sum_exactly_100(self, service):
        """Soma exatamente 100% nao gera conflito (limite inclusivo)."""
        s1 = _make_selection(
            'CustomSql "..." between 20 and 50',
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            column="STATUS",
            category_value="A",
            suggested_lower=20.0,
            suggested_upper=50.0,
        )
        s2 = _make_selection(
            'CustomSql "..." between 30 and 50',
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            column="STATUS",
            category_value="B",
            suggested_lower=30.0,
            suggested_upper=50.0,
        )
        warnings = service.check_consistency([s1, s2])
        assert not any("conflito" in w.lower() for w in warnings)

    def test_frequency_single_rule_no_conflict(self, service):
        """Uma unica regra de frequencia nao gera conflito de soma."""
        s1 = _make_selection(
            'CustomSql "..." between 80 and 95',
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            column="STATUS",
            category_value="A",
            suggested_lower=80.0,
            suggested_upper=95.0,
        )
        warnings = service.check_consistency([s1])
        assert not any("conflito" in w.lower() for w in warnings)

    def test_frequency_dynamic_rules_not_checked(self, service):
        """Regras dinamicas nao entram na soma (sao avaliadas em runtime)."""
        s1 = _make_selection(
            'CustomSql "..." between avg(last(30))*0.9 and avg(last(30))*1.1',
            rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            column="STATUS",
            category_value="A",
            suggested_lower=40.0,
            suggested_upper=60.0,
        )
        s2 = _make_selection(
            'CustomSql "..." between avg(last(30))*0.9 and avg(last(30))*1.1',
            rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            column="STATUS",
            category_value="B",
            suggested_lower=50.0,
            suggested_upper=70.0,
        )
        warnings = service.check_consistency([s1, s2])
        assert not any("conflito" in w.lower() and "100%" in w for w in warnings)


# ============================================================================
# check_consistency — IsPrimaryKey + Completeness redundancy
# ============================================================================

class TestPKCompletenessRedundancy:
    """Testes para deteccao de redundancia IsPrimaryKey + Completeness."""

    def test_pk_completeness_redundancy(self, service):
        """IsPrimaryKey + Completeness na mesma coluna gera aviso de redundancia."""
        pk = _make_selection(
            "IsPrimaryKey COL_A COL_B",
            rule_type=RuleType.IS_PRIMARY_KEY,
            column="COL_A COL_B",
            metric="is_primary_key",
        )
        comp = _make_selection(
            "Completeness COL_A >= 1.00",
            rule_type=RuleType.COMPLETENESS,
            column="COL_A",
            metric="completeness",
        )
        warnings = service.check_consistency([pk, comp])
        assert any("redundancia" in w.lower() and "IsPrimaryKey" in w for w in warnings)

    def test_pk_completeness_different_column_ok(self, service):
        """IsPrimaryKey e Completeness em colunas diferentes nao geram redundancia."""
        pk = _make_selection(
            "IsPrimaryKey COL_A COL_B",
            rule_type=RuleType.IS_PRIMARY_KEY,
            column="COL_A COL_B",
            metric="is_primary_key",
        )
        comp = _make_selection(
            "Completeness COL_C >= 1.00",
            rule_type=RuleType.COMPLETENESS,
            column="COL_C",
            metric="completeness",
        )
        warnings = service.check_consistency([pk, comp])
        assert not any("redundancia" in w.lower() for w in warnings)

    def test_completeness_without_pk_ok(self, service):
        """Completeness sem IsPrimaryKey nao gera redundancia."""
        comp = _make_selection(
            "Completeness COL_A >= 1.00",
            rule_type=RuleType.COMPLETENESS,
            column="COL_A",
            metric="completeness",
        )
        warnings = service.check_consistency([comp])
        assert not any("redundancia" in w.lower() for w in warnings)


# ============================================================================
# check_consistency — RowCount + Mean with very different N
# ============================================================================

class TestRowCountMeanDifferentN:
    """Testes para deteccao de RowCount e Mean com N muito diferentes."""

    def test_rowcount_mean_different_n(self, service):
        """RowCount N=30 e Mean N=10 (diferenca > 15) gera aviso."""
        rc = _make_selection(
            "RowCount >= ...",
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            column=None,
            metric="row_count",
            baseline_window=30,
        )
        mean = _make_selection(
            "Mean COL >= ...",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            column="VLR_SALDO",
            metric="mean",
            baseline_window=10,
        )
        warnings = service.check_consistency([rc, mean])
        assert any(
            "RowCount" in w and "Mean" in w and "N=" in w
            for w in warnings
        )

    def test_rowcount_mean_similar_n_ok(self, service):
        """RowCount N=30 e Mean N=25 (diferenca <= 15) nao gera aviso."""
        rc = _make_selection(
            "RowCount >= ...",
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            column=None,
            metric="row_count",
            baseline_window=30,
        )
        mean = _make_selection(
            "Mean COL >= ...",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            column="VLR_SALDO",
            metric="mean",
            baseline_window=25,
        )
        warnings = service.check_consistency([rc, mean])
        assert not any(
            "RowCount" in w and "Mean" in w
            for w in warnings
        )

    def test_rowcount_mean_same_n_ok(self, service):
        """RowCount e Mean com mesmo N nao gera aviso."""
        rc = _make_selection(
            "RowCount >= ...",
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            column=None,
            metric="row_count",
            baseline_window=30,
        )
        mean = _make_selection(
            "Mean COL >= ...",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            column="VLR_SALDO",
            metric="mean",
            baseline_window=30,
        )
        warnings = service.check_consistency([rc, mean])
        assert not any(
            "RowCount" in w and "Mean" in w
            for w in warnings
        )

    def test_rowcount_without_mean_ok(self, service):
        """RowCount sem Mean nao gera aviso."""
        rc = _make_selection(
            "RowCount >= ...",
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            column=None,
            metric="row_count",
            baseline_window=30,
        )
        warnings = service.check_consistency([rc])
        assert not any("RowCount" in w and "Mean" in w for w in warnings)

    def test_rowcount_mean_warns_only_once(self, service):
        """Com multiplas colunas Mean com N diferente, avisa apenas uma vez."""
        rc = _make_selection(
            "RowCount >= ...",
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            column=None,
            metric="row_count",
            baseline_window=30,
        )
        mean1 = _make_selection(
            "Mean COL1 >= ...",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            column="COL1",
            metric="mean",
            baseline_window=10,
        )
        mean2 = _make_selection(
            "Mean COL2 >= ...",
            rule_type=RuleType.MEAN_DUAL_GUARD,
            column="COL2",
            metric="mean",
            baseline_window=5,
        )
        warnings = service.check_consistency([rc, mean1, mean2])
        rowcount_mean_warnings = [
            w for w in warnings
            if "RowCount" in w and "Mean" in w
        ]
        assert len(rowcount_mean_warnings) == 1


# ============================================================================
# export — integration
# ============================================================================

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

    def test_export_includes_consistency_warnings(self, service):
        """Export integra warnings de sintaxe + consistencia."""
        selections = [
            _make_selection("Mean COL >= 0.9"),
            _make_selection("Mean COL >= 0.8"),
        ]
        result = service.export(selections)
        assert any("duplicada" in w.lower() for w in result.warnings)

    def test_export_analytical_mode_includes_report(self, service):
        """Modo ANALYTICAL_REPORT preenche campo report."""
        bt = _make_backtest()
        selections = [
            _make_selection(
                "Mean COL >= 0.9",
                confidence=ConfidenceLevel.HIGH,
                backtest=bt,
                baseline_window=30,
                baseline_n_sigma=2.0,
            ),
        ]
        result = service.export(selections, mode=ExportOutputMode.ANALYTICAL_REPORT)
        assert result.report  # nao vazio
        assert "Relatorio Analitico" in result.report

    def test_export_gdq_mode_no_report(self, service):
        """Modo GDQ_RUNTIME nao gera report."""
        selections = [_make_selection("Mean COL >= 0.9")]
        result = service.export(selections, mode=ExportOutputMode.GDQ_RUNTIME)
        assert result.report == ""


# ============================================================================
# export_analytical_report
# ============================================================================

class TestAnalyticalReport:
    """Testes para geração de relatório analítico."""

    def test_empty_cart(self, service):
        report = service.export_analytical_report([])
        assert "vazio" in report.lower()

    def test_report_has_header(self, service):
        selections = [_make_selection("Mean COL >= 0.9")]
        report = service.export_analytical_report(selections, table_name="schema.table")
        assert "Relatorio Analitico" in report
        assert "schema.table" in report

    def test_report_has_summary(self, service):
        bt = _make_backtest()
        selections = [
            _make_selection(
                "Mean COL >= 0.9",
                confidence=ConfidenceLevel.HIGH,
                backtest=bt,
            ),
            _make_selection(
                "Completeness COL >= 1.0",
                rule_type=RuleType.COMPLETENESS,
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ]
        report = service.export_analytical_report(selections)
        assert "Total de regras:** 2" in report
        assert "Alta confianca:** 1" in report
        assert "Media confianca:** 1" in report

    def test_report_per_rule_sections(self, service):
        bt = _make_backtest()
        selections = [
            _make_selection(
                "Mean VLR >= 0.9",
                column="VLR",
                confidence=ConfidenceLevel.HIGH,
                backtest=bt,
                baseline_window=30,
                baseline_n_sigma=2.0,
            ),
        ]
        report = service.export_analytical_report(selections)
        # Racional
        assert "Racional" in report
        # Evidencia (from explain_rule_detail)
        assert "Cobertura" in report
        # Sintaxe
        assert "Mean VLR >= 0.9" in report
        assert "```" in report

    def test_report_shows_warnings(self, service):
        selections = [
            _make_selection(
                "Mean COL >= 0.9",
                warnings=["Drift detectado"],
            ),
        ]
        report = service.export_analytical_report(selections)
        assert "Drift detectado" in report

    def test_report_recommendations(self, service):
        selections = [_make_selection("Mean COL >= 0.9")]
        report = service.export_analytical_report(selections)
        assert "Recomendacoes" in report
        assert "alta confianca" in report.lower()

    def test_report_infers_table_name(self, service):
        """Sem table_name explicito, infere do proposal."""
        selections = [_make_selection("Mean COL >= 0.9", table="my_db.my_table")]
        report = service.export_analytical_report(selections)
        assert "my_db.my_table" in report

    def test_report_consistency_section(self, service):
        """Duplicatas aparecem na seção de consistencia."""
        selections = [
            _make_selection("Mean COL >= 0.9"),
            _make_selection("Mean COL >= 0.8"),
        ]
        report = service.export_analytical_report(selections)
        assert "Consistencia" in report
        assert "duplicada" in report.lower()

    def test_report_with_backtest_detail(self, service):
        """Report inclui detalhes do backtest via explain_rule_detail."""
        bt = _make_backtest(coverage_pct=96.7, stability_score=0.92, has_drift=True)
        selections = [
            _make_selection(
                "Mean COL >= 0.9",
                backtest=bt,
                baseline_window=30,
                baseline_n_sigma=2.0,
                baseline_margin_pct=0.10,
            ),
        ]
        report = service.export_analytical_report(selections)
        assert "96.7%" in report
        assert "0.92" in report
        assert "drift" in report.lower()

    def test_report_disabled_excluded(self, service):
        """Regras desabilitadas nao aparecem no report."""
        selections = [
            _make_selection("Mean COL >= 0.9", enabled=True),
            _make_selection("StdDev COL >= 0.5", enabled=False),
        ]
        report = service.export_analytical_report(selections)
        assert "Mean" in report
        assert "StdDev" not in report.split("Recomendacoes")[0]
