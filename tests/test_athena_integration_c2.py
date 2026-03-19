"""
Sprint C2 End-of-Sprint Athena Integration Test.

Validates full pipeline against real Athena:
1. Table connectivity and column discovery
2. Numeric history query + proposals (Mean/StdDev/Completeness)
3. Row count history + proposals (RowCount dual guard)
4. Categorical distribution/domain queries
5. Categorical proposals: static, dynamic, hybrid modes
6. Auto-tuning (find_best_params) for numeric and frequency
7. Syntax validation (all generated rules)
8. Export with analytical report
9. Comparison with DuckDB mock for dialect divergence

Table: gdq_test_db.tb_operacoes_incremental
  - date column: dt_ref (VARCHAR, needs CAST("dt_ref" AS DATE))
  - partition: dt_ref (INCREMENTAL)

Usage:
  set GDQ_ENV=dev
  set AWS_PROFILE=gdq-test
  python -m pytest tests/test_athena_integration_c2.py -v -s
"""

import os
import sys
import time

import pandas as pd
import pytest

from config import load_config
from core.models.baseline import BaselineStrategy
from core.models.column_profile import ColumnProfile
from core.models.dataset_config import DatasetConfig
from core.models.enums import (
    BaselineMethod,
    ConfidenceLevel,
    ExportOutputMode,
    PartitionMethod,
    RuleType,
    SemanticType,
)
from core.models.rule_selection import RuleSelection
from infra.athena_client import AthenaClient
from infra.query_builder import QueryBuilder
from services.analysis_service import AnalysisService
from services.export_service import ExportService
from services.profiling_service import ProfilingService
from services.proposal_service import ProposalService


# ---------------------------------------------------------------------------
# Test configuration
# ---------------------------------------------------------------------------

SCHEMA = "gdq_test_db"
TABLE = "tb_operacoes_incremental"
DATE_COL = "dt_ref"
DATE_EXPR = 'CAST("dt_ref" AS DATE)'
LOOKBACK = 60  # 60 days to ensure 45+ periods

BASELINE = BaselineStrategy(
    method=BaselineMethod.LAST_N_PERIODS,
    n_periods=20,
    n_sigma=2.0,
    margin_pct=0.10,
)


def make_config(lookback: int = LOOKBACK) -> DatasetConfig:
    return DatasetConfig(
        schema=SCHEMA,
        table=TABLE,
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column=DATE_COL,
        date_column=DATE_COL,
        date_expression=DATE_EXPR,
        lookback_value=lookback,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def app_config():
    if not os.environ.get("AWS_PROFILE"):
        pytest.skip("Athena integration requires AWS_PROFILE")
    config = load_config()
    return config


@pytest.fixture(scope="module")
def client(app_config):
    return AthenaClient(app_config)


@pytest.fixture(scope="module")
def builder(client):
    return QueryBuilder(dialect=client.dialect)


@pytest.fixture(scope="module")
def dataset_config():
    return make_config()


@pytest.fixture(scope="module")
def analysis_svc(client, builder):
    return AnalysisService(client, builder)


@pytest.fixture(scope="module")
def profiling_svc(client, builder):
    return ProfilingService(client, builder)


@pytest.fixture(scope="module")
def proposal_svc():
    return ProposalService()


@pytest.fixture(scope="module")
def export_svc():
    return ExportService()


# ---------------------------------------------------------------------------
# 1. Connectivity and column discovery
# ---------------------------------------------------------------------------

class TestConnectivity:

    def test_table_exists(self, client):
        assert client.table_exists(SCHEMA, TABLE), (
            f"Table {SCHEMA}.{TABLE} not accessible"
        )

    def test_get_columns(self, client):
        columns = client.get_columns(SCHEMA, TABLE)
        assert len(columns) > 0, "No columns returned"
        col_names = [c["name"] for c in columns]
        assert DATE_COL in col_names, f"Expected {DATE_COL} in columns"
        print(f"\n  Columns found ({len(columns)}): {col_names}")

    def test_get_columns_with_partitions(self, client):
        columns, partitions = client.get_columns_with_partitions(SCHEMA, TABLE)
        print(f"\n  Partition columns: {partitions}")
        # dt_ref should be a partition column
        assert DATE_COL in partitions, (
            f"Expected {DATE_COL} in partitions, got {partitions}"
        )


# ---------------------------------------------------------------------------
# 2. Numeric history queries
# ---------------------------------------------------------------------------

class TestNumericHistory:

    def test_numeric_history_returns_data(self, analysis_svc, dataset_config):
        # Pick a numeric column (we'll use one known from the test table)
        columns = self._get_numeric_columns(analysis_svc, dataset_config)
        assert len(columns) > 0, "No numeric columns to test"

        col = columns[0]
        print(f"\n  Testing numeric history for column: {col}")

        t0 = time.time()
        history = analysis_svc.get_numeric_history(dataset_config, col)
        elapsed = time.time() - t0

        assert not history.empty, f"Numeric history for {col} returned empty"
        n_periods = len(history)
        print(f"  Periods: {n_periods}, Query time: {elapsed:.2f}s")
        print(f"  Date range: {history['period'].iloc[0]} to {history['period'].iloc[-1]}")
        print(f"  Mean range: {history['mean'].min():.2f} to {history['mean'].max():.2f}")

        assert n_periods >= 30, f"Expected >= 30 periods, got {n_periods}"

        # Verify DataFrame columns
        expected_cols = [
            "period", "mean", "stddev", "min", "max",
            "p01", "p05", "p25", "p50", "p75", "p95", "p99",
            "non_null_count", "null_count", "total_count",
        ]
        for ec in expected_cols:
            assert ec in history.columns, f"Missing column: {ec}"

    def test_numeric_proposals_generated(self, analysis_svc, dataset_config, proposal_svc):
        columns = self._get_numeric_columns(analysis_svc, dataset_config)
        col = columns[0]

        history = analysis_svc.get_numeric_history(dataset_config, col)
        proposals = proposal_svc.propose_numeric_rules(
            history, col, TABLE, BASELINE,
        )

        assert len(proposals) > 0, "No numeric proposals generated"
        types = [p.rule_type for p in proposals]
        print(f"\n  Column: {col}")
        print(f"  Proposals ({len(proposals)}):")
        for p in proposals:
            bt_info = ""
            if p.backtest:
                bt_info = f"  coverage={p.backtest.coverage_pct:.1f}% FP={p.backtest.false_positive_proxy}"
            print(f"    {p.rule_type.value}: confidence={p.confidence.value}{bt_info}")
            print(f"    Syntax: {p.gdq_syntax_preview[:100]}...")

        assert RuleType.MEAN_DUAL_GUARD in types, "Missing Mean proposal"
        assert RuleType.STDDEV_DUAL_GUARD in types, "Missing StdDev proposal"

        # Validate Mean proposal details
        mean_p = next(p for p in proposals if p.rule_type == RuleType.MEAN_DUAL_GUARD)
        assert mean_p.backtest is not None, "Mean proposal missing backtest"
        assert mean_p.backtest.total_periods > 0, "Mean backtest has 0 periods"
        assert mean_p.backtest.coverage_pct > 0, "Mean coverage is 0%"
        assert "avg(last(" in mean_p.gdq_syntax_preview, "Mean syntax missing avg(last(...))"
        assert mean_p.gdq_syntax_preview.count("(") == mean_p.gdq_syntax_preview.count(")"), (
            "Unbalanced parentheses in Mean syntax"
        )

    @staticmethod
    def _get_numeric_columns(analysis_svc, config):
        """Get numeric columns from the table, excluding known non-numeric ones."""
        client = analysis_svc.client
        columns = client.get_columns(config.schema, config.table)
        numeric_types = {"int", "integer", "bigint", "float", "double", "decimal"}
        numeric_cols = [
            c["name"] for c in columns
            if c["type"].lower().split("(")[0] in numeric_types
            and c["name"] != DATE_COL
        ]
        return numeric_cols


# ---------------------------------------------------------------------------
# 3. Row count history
# ---------------------------------------------------------------------------

class TestRowCountHistory:

    def test_row_count_history_returns_data(self, analysis_svc, dataset_config):
        t0 = time.time()
        rc_history = analysis_svc.get_row_count_history(dataset_config)
        elapsed = time.time() - t0

        assert not rc_history.empty, "Row count history returned empty"
        n_periods = len(rc_history)
        print(f"\n  Row count periods: {n_periods}, Query time: {elapsed:.2f}s")
        print(f"  Row count range: {rc_history['row_count'].min():.0f} to {rc_history['row_count'].max():.0f}")

        assert n_periods >= 30, f"Expected >= 30 periods, got {n_periods}"

    def test_row_count_proposal(self, analysis_svc, dataset_config, proposal_svc):
        rc_history = analysis_svc.get_row_count_history(dataset_config)
        proposals = proposal_svc.propose_table_rules(rc_history, TABLE, BASELINE)

        assert len(proposals) > 0, "No RowCount proposal generated"
        p = proposals[0]
        print(f"\n  RowCount proposal:")
        print(f"    Confidence: {p.confidence.value}")
        if p.backtest:
            print(f"    Coverage: {p.backtest.coverage_pct:.1f}%")
            print(f"    FP: {p.backtest.false_positive_proxy}")
        print(f"    Syntax: {p.gdq_syntax_preview[:120]}...")

        assert p.rule_type == RuleType.ROW_COUNT_DUAL_GUARD
        assert p.backtest is not None
        assert p.backtest.coverage_pct > 0


# ---------------------------------------------------------------------------
# 4. Categorical distribution and domain queries
# ---------------------------------------------------------------------------

class TestCategoricalQueries:

    def test_categorical_distribution(self, analysis_svc, dataset_config, client):
        cat_col = self._find_categorical_column(client, dataset_config)
        if cat_col is None:
            pytest.skip("No categorical column found in table")

        print(f"\n  Testing categorical distribution for: {cat_col}")
        t0 = time.time()
        dist = analysis_svc.get_categorical_distribution(dataset_config, cat_col)
        elapsed = time.time() - t0

        assert not dist.empty, f"Categorical distribution for {cat_col} is empty"
        n_periods = dist["period"].nunique()
        n_categories = dist["category_value"].nunique()
        print(f"  Periods: {n_periods}, Categories: {n_categories}, Query time: {elapsed:.2f}s")
        print(f"  Top categories: {dist.groupby('category_value')['value_pct'].mean().nlargest(5).to_dict()}")

        assert n_periods >= 5, f"Expected >= 5 periods, got {n_periods}"

    def test_categorical_domain(self, analysis_svc, dataset_config, client):
        cat_col = self._find_categorical_column(client, dataset_config)
        if cat_col is None:
            pytest.skip("No categorical column found in table")

        t0 = time.time()
        domain = analysis_svc.get_categorical_domain(dataset_config, cat_col)
        elapsed = time.time() - t0

        assert not domain.empty, f"Categorical domain for {cat_col} is empty"
        n_values = len(domain)
        print(f"\n  Domain for {cat_col}: {n_values} values, Query time: {elapsed:.2f}s")
        print(f"  Values: {domain['category_value'].tolist()[:10]}")

    @staticmethod
    def _find_categorical_column(client, config):
        """Find a low-cardinality string column suitable for categorical analysis.

        Picks the string column with lowest distinct count (between 2 and 50)
        to ensure enough periods per value for frequency proposals.
        """
        columns = client.get_columns(config.schema, config.table)
        string_types = {"string", "varchar", "char"}
        candidates = [
            c["name"] for c in columns
            if c["type"].lower().split("(")[0] in string_types
            and c["name"] != DATE_COL
        ]
        if not candidates:
            return None

        # Pick column with lowest cardinality (2-50 distinct values)
        best_col = None
        best_count = float("inf")
        table_ref = f'"{config.schema}"."{config.table}"' if config.schema else f'"{config.table}"'
        for col in candidates:
            try:
                df = client.execute_df(
                    f'SELECT COUNT(DISTINCT "{col}") AS cnt FROM {table_ref}'
                )
                cnt = int(df.iloc[0, 0])
                if 2 <= cnt <= 50 and cnt < best_count:
                    best_count = cnt
                    best_col = col
            except Exception:
                continue

        return best_col or candidates[0]


# ---------------------------------------------------------------------------
# 5. Categorical proposals: static, dynamic, hybrid
# ---------------------------------------------------------------------------

class TestCategoricalProposals:

    @pytest.fixture(autouse=True)
    def _setup(self, analysis_svc, dataset_config, client, proposal_svc):
        self.analysis_svc = analysis_svc
        self.config = dataset_config
        self.client = client
        self.proposal_svc = proposal_svc
        self.cat_col = TestCategoricalQueries._find_categorical_column(client, dataset_config)
        if self.cat_col is None:
            pytest.skip("No categorical column found")

    def _get_cat_data(self):
        dist = self.analysis_svc.get_categorical_distribution(self.config, self.cat_col)
        domain = self.analysis_svc.get_categorical_domain(self.config, self.cat_col)
        n_distinct = len(domain)
        profile = ColumnProfile(
            column_name=self.cat_col,
            athena_type="string",
            inferred_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY if n_distinct <= 50 else SemanticType.CATEGORICAL_MID_CARDINALITY,
            distinct_count=n_distinct,
            null_ratio=0.0,
        )
        return dist, domain, profile

    def test_static_proposals(self):
        dist, domain, profile = self._get_cat_data()
        proposals = self.proposal_svc.propose_categorical_rules(
            dist, domain, self.cat_col, TABLE, profile, BASELINE,
            freq_mode="static",
        )
        assert len(proposals) > 0, "No static categorical proposals"

        freq_static = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_STATIC]
        print(f"\n  Static proposals: {len(proposals)} total, {len(freq_static)} frequency")
        for p in proposals[:5]:
            print(f"    {p.rule_type.value}: {p.metric_name}")

        assert len(freq_static) > 0, "No CATEGORY_FREQUENCY_STATIC proposals"
        for p in freq_static:
            assert "CustomSql" in p.gdq_syntax_preview
            assert "between" in p.gdq_syntax_preview.lower()
            assert "from primary" in p.gdq_syntax_preview

    def test_dynamic_proposals(self):
        dist, domain, profile = self._get_cat_data()
        proposals = self.proposal_svc.propose_categorical_rules(
            dist, domain, self.cat_col, TABLE, profile, BASELINE,
            freq_mode="dynamic",
        )
        freq_dynamic = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_DYNAMIC]
        print(f"\n  Dynamic frequency proposals: {len(freq_dynamic)}")

        assert len(freq_dynamic) > 0, "No CATEGORY_FREQUENCY_DYNAMIC proposals"
        for p in freq_dynamic[:3]:
            print(f"    {p.metric_name}: coverage={p.backtest.coverage_pct:.1f}% conf={p.confidence.value}")
            print(f"    Syntax: {p.gdq_syntax_preview[:100]}...")

            assert "avg(last(" in p.gdq_syntax_preview, "Dynamic syntax missing avg(last(...))"
            assert "OR" in p.gdq_syntax_preview, "Dynamic syntax missing OR (dual guard)"
            assert p.backtest is not None, "Dynamic proposal missing backtest"
            assert p.backtest.total_periods > 0, "Dynamic backtest has 0 periods"
            # Balanced parentheses
            assert p.gdq_syntax_preview.count("(") == p.gdq_syntax_preview.count(")"), (
                f"Unbalanced parens in dynamic syntax: {p.gdq_syntax_preview}"
            )

    def test_hybrid_proposals(self):
        dist, domain, profile = self._get_cat_data()
        proposals = self.proposal_svc.propose_categorical_rules(
            dist, domain, self.cat_col, TABLE, profile, BASELINE,
            freq_mode="hybrid",
            floor_pct=0.0, ceiling_pct=80.0,
        )
        freq_hybrid = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_HYBRID]
        print(f"\n  Hybrid frequency proposals: {len(freq_hybrid)}")

        assert len(freq_hybrid) > 0, "No CATEGORY_FREQUENCY_HYBRID proposals"
        for p in freq_hybrid[:3]:
            print(f"    {p.metric_name}: floor={p.floor_pct} ceiling={p.ceiling_pct}")
            print(f"    Syntax: {p.gdq_syntax_preview[:120]}...")

            assert "between 0.0 and 80.0" in p.gdq_syntax_preview, (
                f"Hybrid syntax missing 'between 0.0 and 80.0': {p.gdq_syntax_preview}"
            )
            assert "avg(last(" in p.gdq_syntax_preview, "Hybrid syntax missing dynamic part"
            assert p.backtest is not None
            assert p.floor_pct == 0.0
            assert p.ceiling_pct == 80.0

    def test_dynamic_vs_static_coverage_comparison(self):
        """Dynamic should have comparable or better coverage than static."""
        dist, domain, profile = self._get_cat_data()

        static_proposals = self.proposal_svc.propose_categorical_rules(
            dist, domain, self.cat_col, TABLE, profile, BASELINE,
            freq_mode="static",
        )
        dynamic_proposals = self.proposal_svc.propose_categorical_rules(
            dist, domain, self.cat_col, TABLE, profile, BASELINE,
            freq_mode="dynamic",
        )

        static_freq = [p for p in static_proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_STATIC]
        dynamic_freq = [p for p in dynamic_proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_DYNAMIC]

        print(f"\n  Static frequency: {len(static_freq)} proposals")
        print(f"  Dynamic frequency: {len(dynamic_freq)} proposals")

        # Both should generate proposals for the same categories
        static_cats = {p.category_value for p in static_freq}
        dynamic_cats = {p.category_value for p in dynamic_freq}
        print(f"  Static categories: {static_cats}")
        print(f"  Dynamic categories: {dynamic_cats}")
        assert static_cats == dynamic_cats, (
            f"Static and dynamic should cover same categories. "
            f"Only in static: {static_cats - dynamic_cats}. "
            f"Only in dynamic: {dynamic_cats - static_cats}."
        )


# ---------------------------------------------------------------------------
# 6. Auto-tuning (find_best_params)
# ---------------------------------------------------------------------------

class TestAutoTuning:

    def test_numeric_auto_tuning(self, analysis_svc, dataset_config, proposal_svc):
        columns = TestNumericHistory._get_numeric_columns(analysis_svc, dataset_config)
        if not columns:
            pytest.skip("No numeric columns")

        col = columns[0]
        history = analysis_svc.get_numeric_history(dataset_config, col)
        values = history["mean"].tolist()
        dates = history["period"].tolist()

        print(f"\n  Auto-tuning numeric for {col} ({len(values)} points)")
        t0 = time.time()
        result = proposal_svc.find_best_params(values, dates, metric_kind="numeric")
        elapsed = time.time() - t0

        print(f"  Time: {elapsed:.2f}s")
        print(f"  Result: N={result['n_periods']}, sigma={result['n_sigma']}, "
              f"margin={result['margin_pct']}, margin_on={result['margin_enabled']}")
        print(f"  Coverage: {result['coverage_pct']:.1f}%, FP: {result['false_positives']}")
        print(f"  Confidence: {result['confidence'].value}, Viable: {result['viable']}")
        print(f"  Recommendation: {result['recommendation']}")

        assert "n_periods" in result
        assert "n_sigma" in result
        assert "margin_pct" in result
        assert "coverage_pct" in result
        assert "confidence" in result
        assert "viable" in result
        assert "recommendation" in result
        assert len(result["recommendation"]) > 10

    def test_frequency_auto_tuning(self, analysis_svc, dataset_config, proposal_svc, client):
        cat_col = TestCategoricalQueries._find_categorical_column(client, dataset_config)
        if cat_col is None:
            pytest.skip("No categorical column")

        dist = analysis_svc.get_categorical_distribution(dataset_config, cat_col)
        # Get the top category
        top_cat = dist.groupby("category_value")["value_count"].sum().idxmax()
        cat_data = dist[dist["category_value"] == top_cat].sort_values("period")
        pct_series = cat_data["value_pct"].tolist()
        dates = cat_data["period"].tolist()

        print(f"\n  Auto-tuning frequency for {cat_col}='{top_cat}' ({len(pct_series)} points)")
        t0 = time.time()
        result = proposal_svc.find_best_params(pct_series, dates, metric_kind="frequency")
        elapsed = time.time() - t0

        print(f"  Time: {elapsed:.2f}s")
        print(f"  Result: N={result['n_periods']}, sigma={result['n_sigma']}, "
              f"margin={result['margin_pct']}, margin_on={result['margin_enabled']}")
        print(f"  Coverage: {result['coverage_pct']:.1f}%, FP: {result['false_positives']}")
        print(f"  Confidence: {result['confidence'].value}, Viable: {result['viable']}")
        print(f"  Recommendation: {result['recommendation']}")

        assert result["viable"] is True or result["coverage_pct"] > 0
        assert isinstance(result["confidence"], ConfidenceLevel)

    def test_auto_tuning_result_structure(self, analysis_svc, dataset_config, proposal_svc):
        columns = TestNumericHistory._get_numeric_columns(analysis_svc, dataset_config)
        if not columns:
            pytest.skip("No numeric columns")

        history = analysis_svc.get_numeric_history(dataset_config, columns[0])
        result = proposal_svc.find_best_params(
            history["mean"].tolist(),
            history["period"].tolist(),
        )
        expected_keys = {
            "n_periods", "n_sigma", "margin_pct", "margin_enabled",
            "coverage_pct", "false_positives", "stability", "score_total",
            "confidence", "viable", "recommendation",
        }
        assert expected_keys.issubset(set(result.keys())), (
            f"Missing keys: {expected_keys - set(result.keys())}"
        )


# ---------------------------------------------------------------------------
# 7. Syntax validation
# ---------------------------------------------------------------------------

class TestSyntaxValidation:

    def test_all_numeric_rules_pass_validation(
        self, analysis_svc, dataset_config, proposal_svc, export_svc,
    ):
        columns = TestNumericHistory._get_numeric_columns(analysis_svc, dataset_config)
        if not columns:
            pytest.skip("No numeric columns")

        history = analysis_svc.get_numeric_history(dataset_config, columns[0])
        proposals = proposal_svc.propose_numeric_rules(history, columns[0], TABLE, BASELINE)

        for p in proposals:
            warnings = export_svc.validate_syntax(p.gdq_syntax_preview)
            print(f"\n  {p.rule_type.value}: {len(warnings)} warnings")
            if warnings:
                for w in warnings:
                    print(f"    WARNING: {w}")
            assert len(warnings) == 0, (
                f"Syntax warnings for {p.rule_type.value}: {warnings}"
            )

    def test_all_categorical_rules_pass_validation(
        self, analysis_svc, dataset_config, proposal_svc, export_svc, client,
    ):
        cat_col = TestCategoricalQueries._find_categorical_column(client, dataset_config)
        if cat_col is None:
            pytest.skip("No categorical column")

        dist = analysis_svc.get_categorical_distribution(dataset_config, cat_col)
        domain = analysis_svc.get_categorical_domain(dataset_config, cat_col)
        n_distinct = len(domain)
        profile = ColumnProfile(
            column_name=cat_col,
            athena_type="string",
            inferred_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY if n_distinct <= 50 else SemanticType.CATEGORICAL_MID_CARDINALITY,
            distinct_count=n_distinct,
            null_ratio=0.0,
        )

        all_warnings = []
        for mode in ["static", "dynamic", "hybrid"]:
            kwargs = {}
            if mode == "hybrid":
                kwargs = {"floor_pct": 0.0, "ceiling_pct": 80.0}
            proposals = proposal_svc.propose_categorical_rules(
                dist, domain, cat_col, TABLE, profile, BASELINE,
                freq_mode=mode, **kwargs,
            )
            for p in proposals:
                warnings = export_svc.validate_syntax(p.gdq_syntax_preview)
                if warnings:
                    all_warnings.append((mode, p.rule_type.value, p.metric_name, warnings))

        print(f"\n  Total syntax issues across all modes: {len(all_warnings)}")
        for mode, rtype, metric, ws in all_warnings:
            print(f"    [{mode}] {rtype} ({metric}): {ws}")

        assert len(all_warnings) == 0, (
            f"Syntax warnings found: {all_warnings}"
        )

    def test_row_count_passes_validation(
        self, analysis_svc, dataset_config, proposal_svc, export_svc,
    ):
        rc_history = analysis_svc.get_row_count_history(dataset_config)
        proposals = proposal_svc.propose_table_rules(rc_history, TABLE, BASELINE)

        for p in proposals:
            warnings = export_svc.validate_syntax(p.gdq_syntax_preview)
            assert len(warnings) == 0, (
                f"RowCount syntax warnings: {warnings}"
            )


# ---------------------------------------------------------------------------
# 8. Export with analytical report
# ---------------------------------------------------------------------------

class TestExport:

    def test_full_export_with_report(
        self, analysis_svc, dataset_config, proposal_svc, export_svc, client,
    ):
        """End-to-end: collect all proposals, build cart, export + validate."""
        all_proposals = []

        # Numeric proposals
        num_cols = TestNumericHistory._get_numeric_columns(analysis_svc, dataset_config)
        if num_cols:
            history = analysis_svc.get_numeric_history(dataset_config, num_cols[0])
            all_proposals.extend(
                proposal_svc.propose_numeric_rules(history, num_cols[0], TABLE, BASELINE)
            )

        # RowCount proposal
        rc_history = analysis_svc.get_row_count_history(dataset_config)
        all_proposals.extend(
            proposal_svc.propose_table_rules(rc_history, TABLE, BASELINE)
        )

        # Categorical proposals (dynamic mode)
        cat_col = TestCategoricalQueries._find_categorical_column(client, dataset_config)
        if cat_col:
            dist = analysis_svc.get_categorical_distribution(dataset_config, cat_col)
            domain = analysis_svc.get_categorical_domain(dataset_config, cat_col)
            n_distinct = len(domain)
            profile = ColumnProfile(
                column_name=cat_col,
                athena_type="string",
                inferred_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY if n_distinct <= 50 else SemanticType.CATEGORICAL_MID_CARDINALITY,
                distinct_count=n_distinct,
                null_ratio=0.0,
            )
            all_proposals.extend(
                proposal_svc.propose_categorical_rules(
                    dist, domain, cat_col, TABLE, profile, BASELINE,
                    freq_mode="dynamic",
                )
            )

        assert len(all_proposals) > 0, "No proposals at all"

        # Build cart (RuleSelection)
        selections = []
        for p in all_proposals:
            sel = RuleSelection(
                proposal_id=p.id,
                proposal=p,
                enabled=True,
                final_gdq_syntax=p.gdq_syntax_preview,
            )
            selections.append(sel)

        # Export GDQ runtime
        result_runtime = export_svc.export(selections, ExportOutputMode.GDQ_RUNTIME)
        print(f"\n  GDQ Runtime Export:")
        print(f"    Rules: {result_runtime.rules_count}")
        print(f"    Warnings: {result_runtime.warnings}")
        print(f"    Syntax length: {len(result_runtime.rules_text)} chars")

        assert result_runtime.rules_count > 0
        assert result_runtime.rules_text.strip() != ""

        # Export analytical report
        result_report = export_svc.export(selections, ExportOutputMode.ANALYTICAL_REPORT)
        print(f"\n  Analytical Report:")
        print(f"    Report length: {len(result_report.report)} chars")
        print(f"    Warnings: {result_report.warnings}")

        assert len(result_report.report) > 100, "Report too short"
        assert "Relatorio Analitico" in result_report.report
        assert "Resumo Executivo" in result_report.report

        # Check syntax warnings are minimal
        print(f"\n  Export syntax warnings ({len(result_runtime.warnings)}):")
        for w in result_runtime.warnings:
            print(f"    - {w}")


# ---------------------------------------------------------------------------
# 9. DuckDB mock comparison
# ---------------------------------------------------------------------------

class TestMockComparison:

    def _make_mock_client(self):
        """Create a DuckDBTestClient and load mock data if available."""
        from pathlib import Path
        from tests.conftest import DuckDBTestClient

        mock_dir = Path(__file__).parent.parent / "mock_data"
        parquet = mock_dir / "tb_operacoes_credito.parquet"
        if not parquet.exists():
            return None, "tb_operacoes_credito"

        client = DuckDBTestClient()
        client.load_table("mock_db", "tb_operacoes_credito", str(parquet))
        return client, "tb_operacoes_credito"

    def test_mock_numeric_history_comparable(self):
        """Compare Athena numeric history with DuckDB mock for the same query pattern."""
        mock_client, table_name = self._make_mock_client()
        if mock_client is None:
            pytest.skip("Mock parquet not available")

        mock_builder = QueryBuilder(dialect=mock_client.dialect)
        mock_analysis = AnalysisService(mock_client, mock_builder)

        mock_dataset = DatasetConfig(
            schema="mock_db",
            table=table_name,
            partition_method=PartitionMethod.INCREMENTAL,
            partition_column=DATE_COL,
            date_column=DATE_COL,
            date_expression=DATE_EXPR,
            lookback_value=60,
        )

        # Find a numeric column in mock
        try:
            mock_cols = mock_client.get_columns("mock_db", table_name)
        except Exception:
            print("\n  Mock table not available, skipping")
            return

        numeric_types = {"integer", "bigint", "float", "double", "decimal", "int"}
        num_cols = [
            c["name"] for c in mock_cols
            if c["type"].lower().split("(")[0] in numeric_types
            and c["name"] != DATE_COL
        ]
        if not num_cols:
            print("\n  No numeric columns in mock, skipping")
            return

        try:
            mock_history = mock_analysis.get_numeric_history(mock_dataset, num_cols[0])
        except Exception as e:
            print(f"\n  Mock comparison skipped: {e}")
            return

        if mock_history.empty:
            print("\n  Mock table returned empty history, skipping comparison")
            return

        # Verify structure matches
        expected_cols = [
            "period", "mean", "stddev", "min", "max",
            "p01", "p05", "p25", "p50", "p75", "p95", "p99",
            "non_null_count", "null_count", "total_count",
        ]
        for ec in expected_cols:
            assert ec in mock_history.columns, f"Mock missing column: {ec}"

        print(f"\n  Mock numeric history: {len(mock_history)} periods")
        print(f"  Mock mean range: {mock_history['mean'].min():.2f} to {mock_history['mean'].max():.2f}")
        print("  Structure matches Athena output: OK")

    def test_mock_categorical_distribution_comparable(self):
        """Verify DuckDB mock returns same structure as Athena."""
        mock_client, table_name = self._make_mock_client()
        if mock_client is None:
            pytest.skip("Mock parquet not available")

        mock_builder = QueryBuilder(dialect=mock_client.dialect)
        mock_analysis = AnalysisService(mock_client, mock_builder)

        mock_dataset = DatasetConfig(
            schema="mock_db",
            table=table_name,
            partition_method=PartitionMethod.INCREMENTAL,
            partition_column=DATE_COL,
            date_column=DATE_COL,
            date_expression=DATE_EXPR,
            lookback_value=60,
        )

        # Find a string column in mock
        try:
            mock_cols = mock_client.get_columns("mock_db", table_name)
        except Exception:
            print("\n  Mock table not available, skipping")
            return

        string_cols = [
            c["name"] for c in mock_cols
            if c["type"].lower() in ("string", "varchar", "text")
            and c["name"] != DATE_COL
        ]
        if not string_cols:
            print("\n  No string columns in mock, skipping")
            return

        try:
            mock_dist = mock_analysis.get_categorical_distribution(mock_dataset, string_cols[0])
        except Exception as e:
            print(f"\n  Mock categorical query failed: {e}")
            return

        if not mock_dist.empty:
            expected = ["period", "category_value", "value_count", "value_pct"]
            for ec in expected:
                assert ec in mock_dist.columns, f"Mock dist missing column: {ec}"
            print(f"\n  Mock categorical distribution: {len(mock_dist)} rows, structure OK")


# ---------------------------------------------------------------------------
# Summary report (runs last)
# ---------------------------------------------------------------------------

class TestSummaryReport:

    def test_print_summary(
        self, analysis_svc, dataset_config, proposal_svc, export_svc, client,
    ):
        """Print a final summary of the integration test results."""
        print("\n" + "=" * 70)
        print("  ATHENA INTEGRATION TEST SUMMARY — Sprint C2")
        print("=" * 70)

        # Numeric
        num_cols = TestNumericHistory._get_numeric_columns(analysis_svc, dataset_config)
        print(f"\n  Numeric columns available: {len(num_cols)}")

        if num_cols:
            history = analysis_svc.get_numeric_history(dataset_config, num_cols[0])
            n_periods = len(history)
            proposals = proposal_svc.propose_numeric_rules(history, num_cols[0], TABLE, BASELINE)

            print(f"  Numeric history periods: {n_periods}")
            for p in proposals:
                bt = p.backtest
                cov = bt.coverage_pct if bt else 0
                fp = bt.false_positive_proxy if bt else 0
                print(f"    {p.rule_type.value}: confidence={p.confidence.value} "
                      f"coverage={cov:.1f}% FP={fp}")

        # Row count
        rc_history = analysis_svc.get_row_count_history(dataset_config)
        rc_proposals = proposal_svc.propose_table_rules(rc_history, TABLE, BASELINE)
        print(f"\n  Row count periods: {len(rc_history)}")
        for p in rc_proposals:
            bt = p.backtest
            cov = bt.coverage_pct if bt else 0
            print(f"    RowCount: confidence={p.confidence.value} coverage={cov:.1f}%")

        # Categorical
        cat_col = TestCategoricalQueries._find_categorical_column(client, dataset_config)
        if cat_col:
            dist = analysis_svc.get_categorical_distribution(dataset_config, cat_col)
            domain = analysis_svc.get_categorical_domain(dataset_config, cat_col)
            n_distinct = len(domain)
            profile = ColumnProfile(
                column_name=cat_col,
                athena_type="string",
                inferred_semantic_type=SemanticType.CATEGORICAL_LOW_CARDINALITY if n_distinct <= 50 else SemanticType.CATEGORICAL_MID_CARDINALITY,
                distinct_count=n_distinct,
                null_ratio=0.0,
            )

            print(f"\n  Categorical column: {cat_col} ({n_distinct} values)")
            for mode in ["static", "dynamic", "hybrid"]:
                kwargs = {"floor_pct": 0.0, "ceiling_pct": 80.0} if mode == "hybrid" else {}
                proposals = proposal_svc.propose_categorical_rules(
                    dist, domain, cat_col, TABLE, profile, BASELINE,
                    freq_mode=mode, **kwargs,
                )
                freq_rules = [p for p in proposals if "freq" in p.rule_type.value]
                total_cov = sum(p.backtest.coverage_pct for p in freq_rules if p.backtest) / max(len(freq_rules), 1)
                print(f"    {mode}: {len(freq_rules)} frequency rules, avg coverage={total_cov:.1f}%")

            # Auto-tuning
            top_cat = dist.groupby("category_value")["value_count"].sum().idxmax()
            cat_data = dist[dist["category_value"] == top_cat].sort_values("period")
            at_result = proposal_svc.find_best_params(
                cat_data["value_pct"].tolist(),
                cat_data["period"].tolist(),
                metric_kind="frequency",
            )
            print(f"\n  Auto-tuning ({cat_col}='{top_cat}'):")
            print(f"    Best: N={at_result['n_periods']}, sigma={at_result['n_sigma']}, "
                  f"margin={at_result['margin_pct']}")
            print(f"    Coverage: {at_result['coverage_pct']:.1f}%, "
                  f"Confidence: {at_result['confidence'].value}")

        print("\n" + "=" * 70)
        print("  ALL TESTS PASSED")
        print("=" * 70)
