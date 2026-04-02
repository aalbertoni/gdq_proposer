"""Testes para core/gdq_filtered_rule_generator.py."""

import pytest

from core.gdq_filtered_rule_generator import generate_filtered_rule
from core.models.enums import RuleType
from core.models.rule_proposal import RuleProposal


DATE_FILTER = "ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')"


def _make_proposal(**kwargs) -> RuleProposal:
    """Helper para criar proposta com defaults."""
    defaults = {
        "id": "test-001",
        "target_table": "schema.table",
        "metric_name": "mean",
        "target_column": "VLR_CNTR_LIQO_OPCR",
        "rule_type": RuleType.MEAN_DUAL_GUARD,
        "baseline_window": 30,
        "baseline_n_sigma": 2.0,
        "baseline_margin_pct": 0.10,
        "margin_enabled": True,
    }
    defaults.update(kwargs)
    return RuleProposal(**defaults)


class TestMeanDualGuard:
    def test_generates_customsql_with_where(self):
        proposal = _make_proposal()
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert 'from primary where ANO_MES_RFRC_CRED' in result
        assert 'avg(cast(VLR_CNTR_LIQO_OPCR as double))' in result

    def test_contains_avg_last_in_between(self):
        proposal = _make_proposal()
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert "avg(last(30))" in result
        assert "std(last(30))" in result

    def test_contains_dual_guard_or(self):
        proposal = _make_proposal(margin_enabled=True)
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert " OR " in result

    def test_sigma_only_no_or(self):
        proposal = _make_proposal(margin_enabled=False)
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert " OR " not in result


class TestStdDevDualGuard:
    def test_generates_stddev_with_where(self):
        proposal = _make_proposal(rule_type=RuleType.STDDEV_DUAL_GUARD)
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert "stddev" in result.lower()
        assert "from primary where" in result


class TestRowCountDualGuard:
    def test_generates_count_with_where(self):
        proposal = _make_proposal(
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            target_column="",
        )
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert "count(*)" in result.lower()
        assert "from primary where" in result

    def test_no_buffer(self):
        proposal = _make_proposal(
            rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
            target_column="",
            margin_enabled=False,
        )
        result = generate_filtered_rule(proposal, DATE_FILTER)
        # RowCount should not have 0.01 buffer
        assert "- 0.01" not in result


class TestCompleteness:
    def test_generates_ratio_with_where(self):
        proposal = _make_proposal(
            rule_type=RuleType.COMPLETENESS,
            suggested_lower=0.95,
        )
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert 'count(VLR_CNTR_LIQO_OPCR)' in result
        assert "nullif(count(*), 0)" in result
        assert ">= 0.95" in result
        assert "from primary where" in result


class TestAllowedValues:
    def test_generates_not_in_count_with_where(self):
        proposal = _make_proposal(
            rule_type=RuleType.ALLOWED_VALUES,
            target_column="COD_TIPO",
            suggested_values=["A", "B", "C"],
        )
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert "not in" in result
        assert "= 0" in result
        assert "from primary where" in result

    def test_numeric_values_no_quotes(self):
        proposal = _make_proposal(
            rule_type=RuleType.ALLOWED_VALUES,
            target_column="COD_SITU",
            suggested_values=["1", "2", "3"],
        )
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert "1, 2, 3" in result


class TestDistinctCount:
    def test_exact_with_where(self):
        proposal = _make_proposal(
            rule_type=RuleType.DISTINCT_COUNT_EXACT,
            target_column="UF",
            suggested_lower=27,
        )
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert 'count(distinct UF)' in result
        assert "= 27" in result

    def test_range_with_where(self):
        proposal = _make_proposal(
            rule_type=RuleType.DISTINCT_COUNT_RANGE,
            target_column="CIDADE",
            suggested_lower=200,
            suggested_upper=350,
        )
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert ">= 200" in result
        assert "<= 350" in result


class TestCategoryFrequency:
    def test_static_with_where(self):
        proposal = _make_proposal(
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            target_column="COD_TIPO",
            category_value="A",
            suggested_lower=30.0,
            suggested_upper=50.0,
        )
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert "'A'" in result
        assert "100.0" in result
        assert "from primary where" in result

    def test_dynamic_with_where(self):
        proposal = _make_proposal(
            rule_type=RuleType.CATEGORY_FREQUENCY_DYNAMIC,
            target_column="COD_TIPO",
            category_value="A",
        )
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert "avg(last(30))" in result
        assert "from primary where" in result


class TestIsPrimaryKey:
    def test_returns_none(self):
        proposal = _make_proposal(
            rule_type=RuleType.IS_PRIMARY_KEY,
            suggested_values=["COL1", "COL2"],
        )
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is None


class TestMaxValueStrategy:
    def test_max_value_in_where(self):
        max_filter = "ANO_MES_RFRC_CRED = (select max(ANO_MES_RFRC_CRED) from primary)"
        proposal = _make_proposal()
        result = generate_filtered_rule(proposal, max_filter)
        assert result is not None
        assert "select max(ANO_MES_RFRC_CRED)" in result


class TestLagStrategy:
    def test_lag_in_where(self):
        lag_filter = "ANO_MES_RFRC_CRED = date_format(add_months(current_date(), -1), 'yyyyMM')"
        proposal = _make_proposal()
        result = generate_filtered_rule(proposal, lag_filter)
        assert result is not None
        assert "add_months" in result


class TestColumnSanitization:
    """Testes de sanitizacao de nomes de coluna via validate_identifier."""

    def test_rejects_sql_injection_in_column(self):
        proposal = _make_proposal(target_column="x); DROP TABLE t--")
        with pytest.raises(ValueError, match="Identificador"):
            generate_filtered_rule(proposal, DATE_FILTER)

    def test_rejects_column_with_spaces(self):
        proposal = _make_proposal(target_column="col name")
        with pytest.raises(ValueError, match="Identificador"):
            generate_filtered_rule(proposal, DATE_FILTER)

    def test_rejects_column_with_semicolon(self):
        proposal = _make_proposal(target_column="col;drop")
        with pytest.raises(ValueError, match="Identificador"):
            generate_filtered_rule(proposal, DATE_FILTER)

    def test_rejects_column_with_quotes(self):
        proposal = _make_proposal(target_column='col"name')
        with pytest.raises(ValueError, match="Identificador"):
            generate_filtered_rule(proposal, DATE_FILTER)

    def test_rejects_column_with_parentheses(self):
        proposal = _make_proposal(target_column="col()")
        with pytest.raises(ValueError, match="Identificador"):
            generate_filtered_rule(proposal, DATE_FILTER)

    def test_valid_column_with_underscores(self):
        proposal = _make_proposal(target_column="VLR_SALD_AVNC_OPCR")
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert "VLR_SALD_AVNC_OPCR" in result

    def test_lowercase_column_uppercased(self):
        proposal = _make_proposal(target_column="vlr_saldo")
        result = generate_filtered_rule(proposal, DATE_FILTER)
        assert result is not None
        assert "VLR_SALDO" in result
        assert "vlr_saldo" not in result

    def test_completeness_rejects_injection(self):
        proposal = _make_proposal(
            rule_type=RuleType.COMPLETENESS,
            target_column="x union select 1--",
            suggested_lower=1.0,
        )
        with pytest.raises(ValueError, match="Identificador"):
            generate_filtered_rule(proposal, DATE_FILTER)

    def test_distinct_count_rejects_injection(self):
        proposal = _make_proposal(
            rule_type=RuleType.DISTINCT_COUNT_EXACT,
            target_column="col; DROP TABLE",
            suggested_lower=5,
        )
        with pytest.raises(ValueError, match="Identificador"):
            generate_filtered_rule(proposal, DATE_FILTER)

    def test_category_frequency_rejects_injection(self):
        proposal = _make_proposal(
            rule_type=RuleType.CATEGORY_FREQUENCY_STATIC,
            target_column="x' OR 1=1--",
            category_value="A",
            suggested_lower=10.0,
            suggested_upper=90.0,
        )
        with pytest.raises(ValueError, match="Identificador"):
            generate_filtered_rule(proposal, DATE_FILTER)
