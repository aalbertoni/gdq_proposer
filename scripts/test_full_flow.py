"""
Full flow test: simulates Setup -> Profiling -> Explore -> Review -> Export.

Tests the entire pipeline end-to-end with all service layers.
Run with: python scripts/test_full_flow.py          (mock mode)
          GDQ_ENV=dev python scripts/test_full_flow.py  (real Athena)
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Default to mock if not specified
if "GDQ_ENV" not in os.environ:
    os.environ["GDQ_ENV"] = "local"

from config import load_config
from core.models.baseline import BaselineStrategy
from core.models.dataset_config import DatasetConfig
from core.models.enums import BaselineMethod, PartitionMethod, SemanticType
from core.models.rule_selection import RuleSelection
from infra.athena_client import AthenaClient
from infra.query_builder import QueryBuilder
from services.analysis_service import AnalysisService
from services.dataset_service import DatasetService
from services.export_service import ExportService
from services.profiling_service import ProfilingService
from services.proposal_service import ProposalService


def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def main():
    config = load_config()
    is_mock = config.athena.mode.value == "mock"
    env_label = "MOCK (DuckDB)" if is_mock else f"REAL Athena ({config.athena.region})"

    separator(f"Full Flow Test — {env_label}")

    # Determine table based on environment
    if is_mock:
        schema = "mock_db"
        table = "tb_operacoes_credito"
    else:
        schema = "gdq_test_db"
        table = "tb_operacoes_incremental"

    errors = []
    warnings = []

    # ===================================================================
    # STEP 1: Setup — Initialize services
    # ===================================================================
    separator("STEP 1: Setup & Connection")
    try:
        client = AthenaClient(config)
        builder = QueryBuilder(dialect=client.dialect)
        dataset_svc = DatasetService(client, builder)
        profiling_svc = ProfilingService(client, builder)
        analysis_svc = AnalysisService(client, builder)
        proposal_svc = ProposalService()
        export_svc = ExportService()
        print(f"  OK: All services initialized")
        print(f"  Dialect: {client.dialect.value}")
    except Exception as e:
        errors.append(f"STEP 1 FAIL: {e}")
        traceback.print_exc()
        _print_summary(errors, warnings)
        return

    # ===================================================================
    # STEP 2: Validate table
    # ===================================================================
    separator("STEP 2: Validate Table")
    try:
        exists = dataset_svc.validate_table(schema, table)
        print(f"  Table {schema}.{table} exists: {exists}")
        if not exists:
            errors.append(f"STEP 2 FAIL: Table {schema}.{table} not found")
            _print_summary(errors, warnings)
            return
    except Exception as e:
        errors.append(f"STEP 2 FAIL: validate_table error: {e}")
        traceback.print_exc()
        _print_summary(errors, warnings)
        return

    # ===================================================================
    # STEP 3: Get columns
    # ===================================================================
    separator("STEP 3: Get Columns")
    try:
        columns = dataset_svc.get_columns(schema, table)
        # Clean up whitespace (Athena gotcha)
        columns = [
            c for c in columns
            if isinstance(c.get("name"), str) and isinstance(c.get("type"), str)
        ]
        for c in columns:
            c["name"] = str(c["name"]).strip()
            c["type"] = str(c["type"]).strip()

        print(f"  Columns found: {len(columns)}")
        for c in columns:
            print(f"    {c['name']:30s}  {c['type']}")

        if not columns:
            errors.append("STEP 3 FAIL: No columns returned")
            _print_summary(errors, warnings)
            return
    except Exception as e:
        errors.append(f"STEP 3 FAIL: get_columns error: {e}")
        traceback.print_exc()
        _print_summary(errors, warnings)
        return

    # ===================================================================
    # STEP 4: Build DatasetConfig & Validate Date Range
    # ===================================================================
    separator("STEP 4: DatasetConfig & Date Range")
    try:
        dataset_config = DatasetConfig(
            schema=schema,
            table=table,
            partition_method=PartitionMethod.INCREMENTAL,
            partition_column="dt_ref",
            date_column="dt_ref",
            date_expression='CAST("dt_ref" AS DATE)',
            lookback_value=60,
        )

        date_range = dataset_svc.get_date_range(dataset_config)
        print(f"  Min date: {date_range['min_date']}")
        print(f"  Max date: {date_range['max_date']}")
        print(f"  Periods:  {date_range['n_periods']}")

        if date_range["n_periods"] == 0:
            errors.append("STEP 4 FAIL: No periods found")
            _print_summary(errors, warnings)
            return
    except Exception as e:
        errors.append(f"STEP 4 FAIL: get_date_range error: {e}")
        traceback.print_exc()
        _print_summary(errors, warnings)
        return

    # ===================================================================
    # STEP 5: Profiling
    # ===================================================================
    separator("STEP 5: Profiling")
    try:
        profiles = profiling_svc.profile_columns(
            dataset_config,
            columns,
            sample_periods=60,
        )
        print(f"  Profiles generated: {len(profiles)}")
        for p in profiles:
            print(f"    {p.column_name:30s}  {p.effective_type.value:25s}  null={p.null_ratio:.1%}  dist={p.distinct_count}")

        numeric_profiles = [p for p in profiles if p.effective_type == SemanticType.NUMERIC]
        cat_profiles = [p for p in profiles if p.is_categorical]
        print(f"\n  Numeric: {len(numeric_profiles)}, Categorical: {len(cat_profiles)}")

        if not numeric_profiles:
            warnings.append("STEP 5 WARN: No numeric columns found")
    except Exception as e:
        errors.append(f"STEP 5 FAIL: profiling error: {e}")
        traceback.print_exc()
        _print_summary(errors, warnings)
        return

    # ===================================================================
    # STEP 6: Numeric History + Proposals
    # ===================================================================
    separator("STEP 6: Numeric History & Proposals")
    all_proposals = []
    baseline = BaselineStrategy(
        method=BaselineMethod.LAST_N_PERIODS,
        n_periods=20,
        n_sigma=2.0,
        margin_pct=0.10,
    )

    for np_profile in numeric_profiles:
        col_name = np_profile.column_name
        print(f"\n  --- Column: {col_name} ---")

        try:
            history_df = analysis_svc.get_numeric_history(dataset_config, col_name)
            print(f"  History rows: {len(history_df)}")
            if not history_df.empty:
                print(f"  Period range: {history_df['period'].iloc[0]} to {history_df['period'].iloc[-1]}")
                print(f"  Mean range: {history_df['mean'].min():.4f} to {history_df['mean'].max():.4f}")
                print(f"  StdDev range: {history_df['stddev'].min():.4f} to {history_df['stddev'].max():.4f}")
            else:
                warnings.append(f"STEP 6 WARN: Empty history for {col_name}")
                continue
        except Exception as e:
            errors.append(f"STEP 6 FAIL: get_numeric_history({col_name}): {e}")
            traceback.print_exc()
            continue

        try:
            proposals = proposal_svc.propose_numeric_rules(
                history_df, col_name, table, baseline,
            )
            print(f"  Proposals: {len(proposals)}")
            for p in proposals:
                conf = p.confidence.value
                cov = f"{p.backtest.coverage_pct:.1f}%" if p.backtest else "N/A"
                drift = p.backtest.has_drift if p.backtest else False
                print(f"    {p.rule_type.value:25s}  conf={conf:6s}  cov={cov:7s}  drift={drift}")
                print(f"    syntax: {p.gdq_syntax_preview[:100]}...")
            all_proposals.extend(proposals)
        except Exception as e:
            errors.append(f"STEP 6 FAIL: propose_numeric_rules({col_name}): {e}")
            traceback.print_exc()

    # ===================================================================
    # STEP 7: RowCount History + Proposals
    # ===================================================================
    separator("STEP 7: RowCount History & Proposals")
    try:
        rc_history_df = analysis_svc.get_row_count_history(dataset_config)
        print(f"  RowCount history rows: {len(rc_history_df)}")
        if not rc_history_df.empty:
            print(f"  Period range: {rc_history_df['period'].iloc[0]} to {rc_history_df['period'].iloc[-1]}")
            print(f"  Row count range: {rc_history_df['row_count'].min():.0f} to {rc_history_df['row_count'].max():.0f}")

            rc_proposals = proposal_svc.propose_table_rules(
                rc_history_df, table, baseline,
            )
            print(f"  RowCount proposals: {len(rc_proposals)}")
            for p in rc_proposals:
                conf = p.confidence.value
                cov = f"{p.backtest.coverage_pct:.1f}%" if p.backtest else "N/A"
                print(f"    {p.rule_type.value:25s}  conf={conf:6s}  cov={cov}")
                print(f"    syntax: {p.gdq_syntax_preview[:100]}...")
            all_proposals.extend(rc_proposals)
        else:
            warnings.append("STEP 7 WARN: Empty row count history")
    except Exception as e:
        errors.append(f"STEP 7 FAIL: row count: {e}")
        traceback.print_exc()

    # ===================================================================
    # STEP 8: Review (simulate cart)
    # ===================================================================
    separator("STEP 8: Review — Cart Simulation")
    print(f"  Total proposals to cart: {len(all_proposals)}")

    selections = []
    for p in all_proposals:
        sel = RuleSelection(
            proposal_id=p.id,
            proposal=p,
            final_gdq_syntax=p.gdq_syntax_preview,
        )
        selections.append(sel)
        target = p.target_column or "(tabela)"
        print(f"    [{p.rule_type.value}] {target} — {p.confidence.value}")

    # ===================================================================
    # STEP 9: Export
    # ===================================================================
    separator("STEP 9: Export")
    try:
        result = export_svc.export(selections)
        print(f"  Rules count: {result.rules_count}")
        print(f"  Warnings: {result.warnings}")
        print(f"\n  === Generated GDQ Syntax ===")
        for line in result.rules_text.split("\n"):
            print(f"  {line}")

        if result.warnings:
            for w in result.warnings:
                warnings.append(f"STEP 9 WARN: Export warning: {w}")
    except Exception as e:
        errors.append(f"STEP 9 FAIL: export: {e}")
        traceback.print_exc()

    # ===================================================================
    # Summary
    # ===================================================================
    _print_summary(errors, warnings)


def _print_summary(errors, warnings):
    separator("SUMMARY")
    if warnings:
        print(f"  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"    - {w}")
        print()

    if errors:
        print(f"  ERRORS ({len(errors)}):")
        for e in errors:
            print(f"    - {e}")
        print(f"\n  RESULT: FAIL")
    else:
        print(f"  RESULT: ALL STEPS PASSED")


if __name__ == "__main__":
    main()
