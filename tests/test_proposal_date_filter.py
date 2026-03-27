"""Testes para integração ProposalService + date filter.

Valida que o fluxo completo (config → ProposalService → syntax)
gera CustomSql com WHERE quando has_date_filter=True.
"""

import pandas as pd
import pytest

from core.models.baseline import BaselineStrategy
from core.models.enums import BaselineMethod
from services.proposal_service import ProposalService


DATE_FILTER_WHERE = "ANO_MES_RFRC_CRED = date_format(current_date(), 'yyyyMM')"
TABLE = "schema.tb_test"
BASELINE = BaselineStrategy(method=BaselineMethod.LAST_N_PERIODS, n_periods=30)


@pytest.fixture
def svc_with_filter():
    svc = ProposalService()
    svc.set_date_filter(DATE_FILTER_WHERE)
    return svc


@pytest.fixture
def svc_without_filter():
    svc = ProposalService()
    svc.set_date_filter(None)
    return svc


@pytest.fixture
def numeric_history():
    return pd.DataFrame({
        "period": pd.date_range("2026-01-01", periods=30, freq="D"),
        "mean": [100 + i * 0.5 for i in range(30)],
        "stddev": [10.0] * 30,
        "min": [80.0] * 30,
        "max": [120.0] * 30,
        "p01": [82.0] * 30,
        "p05": [85.0] * 30,
        "p10": [87.0] * 30,
        "p25": [92.0] * 30,
        "p50": [100.0] * 30,
        "p75": [108.0] * 30,
        "p90": [113.0] * 30,
        "p95": [115.0] * 30,
        "p99": [118.0] * 30,
        "non_null_count": [1000] * 30,
        "null_count": [0] * 30,
        "total_count": [1000] * 30,
    })


class TestNumericRulesWithDateFilter:
    def test_mean_rule_has_where(self, svc_with_filter, numeric_history):
        proposals = svc_with_filter.propose_numeric_rules(
            numeric_history, "VLR_CNTR_LIQO_OPCR", TABLE, BASELINE,
        )
        mean_proposals = [p for p in proposals if "mean" in p.rule_type.value.lower()]
        assert len(mean_proposals) > 0
        for p in mean_proposals:
            assert "from primary where" in p.gdq_syntax_preview
            assert "ANO_MES_RFRC_CRED" in p.gdq_syntax_preview

    def test_mean_rule_without_filter_is_builtin(self, svc_without_filter, numeric_history):
        proposals = svc_without_filter.propose_numeric_rules(
            numeric_history, "VLR_CNTR_LIQO_OPCR", TABLE, BASELINE,
        )
        mean_proposals = [p for p in proposals if "mean" in p.rule_type.value.lower()]
        assert len(mean_proposals) > 0
        for p in mean_proposals:
            assert "from primary where" not in p.gdq_syntax_preview

    def test_completeness_rule_has_where(self, svc_with_filter, numeric_history):
        proposals = svc_with_filter.propose_numeric_rules(
            numeric_history, "VLR_CNTR_LIQO_OPCR", TABLE, BASELINE,
        )
        comp_proposals = [p for p in proposals if "completeness" in p.rule_type.value.lower()]
        assert len(comp_proposals) > 0
        for p in comp_proposals:
            assert "from primary where" in p.gdq_syntax_preview

    def test_stddev_rule_has_where(self, svc_with_filter, numeric_history):
        proposals = svc_with_filter.propose_numeric_rules(
            numeric_history, "VLR_CNTR_LIQO_OPCR", TABLE, BASELINE,
        )
        std_proposals = [p for p in proposals if "stddev" in p.rule_type.value.lower()]
        assert len(std_proposals) > 0
        for p in std_proposals:
            assert "stddev" in p.gdq_syntax_preview.lower()
            assert "from primary where" in p.gdq_syntax_preview


class TestTableRulesWithDateFilter:
    def test_row_count_has_where(self, svc_with_filter):
        row_history = pd.DataFrame({
            "period": pd.date_range("2026-01-01", periods=30, freq="D"),
            "row_count": [10000 + i * 10 for i in range(30)],
        })
        proposals = svc_with_filter.propose_table_rules(row_history, TABLE, BASELINE)
        rc_proposals = [p for p in proposals if "row_count" in p.rule_type.value.lower()]
        assert len(rc_proposals) > 0
        for p in rc_proposals:
            assert "count(*)" in p.gdq_syntax_preview.lower()
            assert "from primary where" in p.gdq_syntax_preview


class TestCategoricalRulesWithDateFilter:
    def test_allowed_values_has_where(self, svc_with_filter):
        from core.models.column_profile import ColumnProfile
        from core.models.enums import SemanticType

        profile = ColumnProfile(
            column_name="COD_TIPO",
            athena_type="varchar",
            inferred_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY,
            total_count=1000,
            non_null_count=1000,
            distinct_count=3,
        )
        distribution = pd.DataFrame({
            "period": pd.date_range("2026-01-01", periods=30, freq="D").repeat(3),
            "category_value": ["A", "B", "C"] * 30,
            "value_count": [400, 350, 250] * 30,
            "value_pct": [40.0, 35.0, 25.0] * 30,
        })
        domain = pd.DataFrame({
            "category_value": ["A", "B", "C"],
            "value_count": [12000, 10500, 7500],
            "value_pct": [40.0, 35.0, 25.0],
        })
        proposals = svc_with_filter.propose_categorical_rules(
            distribution, domain, "COD_TIPO", TABLE, profile, BASELINE,
        )
        # At least AllowedValues or frequency rules should have WHERE
        filtered = [p for p in proposals if "from primary where" in p.gdq_syntax_preview]
        assert len(filtered) > 0

    def test_categorical_without_filter_is_builtin(self, svc_without_filter):
        from core.models.column_profile import ColumnProfile
        from core.models.enums import SemanticType

        profile = ColumnProfile(
            column_name="COD_TIPO",
            athena_type="varchar",
            inferred_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY,
            total_count=1000,
            non_null_count=1000,
            distinct_count=3,
        )
        distribution = pd.DataFrame({
            "period": pd.date_range("2026-01-01", periods=30, freq="D").repeat(3),
            "category_value": ["A", "B", "C"] * 30,
            "value_count": [400, 350, 250] * 30,
            "value_pct": [40.0, 35.0, 25.0] * 30,
        })
        domain = pd.DataFrame({
            "category_value": ["A", "B", "C"],
            "value_count": [12000, 10500, 7500],
            "value_pct": [40.0, 35.0, 25.0],
        })
        proposals = svc_without_filter.propose_categorical_rules(
            distribution, domain, "COD_TIPO", TABLE, profile, BASELINE,
        )
        for p in proposals:
            assert "from primary where ANO_MES_RFRC_CRED" not in p.gdq_syntax_preview


class TestEdgeCases:
    def test_empty_string_filter_treated_as_no_filter(self, numeric_history):
        """Empty string is falsy — should behave like None."""
        svc = ProposalService()
        svc.set_date_filter("")
        proposals = svc.propose_numeric_rules(
            numeric_history, "VLR", TABLE, BASELINE,
        )
        mean_proposals = [p for p in proposals if "mean" in p.rule_type.value.lower()]
        assert len(mean_proposals) > 0
        for p in mean_proposals:
            assert "from primary where" not in p.gdq_syntax_preview


class TestSetDateFilter:
    def test_set_none_disables(self):
        svc = ProposalService()
        svc.set_date_filter(DATE_FILTER_WHERE)
        assert svc._date_filter_where == DATE_FILTER_WHERE
        svc.set_date_filter(None)
        assert svc._date_filter_where is None

    def test_max_value_strategy(self, numeric_history):
        svc = ProposalService()
        svc.set_date_filter(
            "ANO_MES_RFRC_CRED = (select max(ANO_MES_RFRC_CRED) from primary)"
        )
        proposals = svc.propose_numeric_rules(
            numeric_history, "VLR", TABLE, BASELINE,
        )
        mean_proposals = [p for p in proposals if "mean" in p.rule_type.value.lower()]
        assert len(mean_proposals) > 0
        for p in mean_proposals:
            assert "select max(ANO_MES_RFRC_CRED)" in p.gdq_syntax_preview
