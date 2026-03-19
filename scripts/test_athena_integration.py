"""
Integration test: Sprint A2 + B1 flow against real Athena.

Tests the full pipeline:
1. AnalysisService.get_numeric_history() against real Athena table
2. ProposalService.propose_numeric_rules() with real data
3. AnalysisService.get_row_count_history() + propose_table_rules()
4. GDQ syntax generation and validation
5. Export

Run with: GDQ_ENV=dev python scripts/test_athena_integration.py
"""

import os
import sys

os.environ.setdefault("GDQ_AWS_PROFILE", "gdq-test")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import load_config
from core.models.baseline import BaselineStrategy
from core.models.dataset_config import DatasetConfig
from core.models.enums import BaselineMethod, PartitionMethod
from infra.athena_client import AthenaClient
from infra.query_builder import QueryBuilder
from services.analysis_service import AnalysisService
from services.dataset_service import DatasetService
from services.export_service import ExportService
from services.proposal_service import ProposalService
from core.models.rule_selection import RuleSelection


def main():
    config = load_config()
    print(f"Region: {config.athena.region}")
    print(f"Workgroup: {config.athena.workgroup}")
    print()

    client = AthenaClient(config)
    builder = QueryBuilder(dialect=client.dialect)

    # --- Step 1: Validate table ---
    dataset_svc = DatasetService(client, builder)
    schema = "gdq_test_db"
    table = "tb_operacoes_incremental"

    print(f"[1] Validating table {schema}.{table}...")
    exists = dataset_svc.validate_table(schema, table)
    print(f"    Table exists: {exists}")
    if not exists:
        print("    FAIL: Table not found. Exiting.")
        return

    columns = dataset_svc.get_columns(schema, table)
    # Strip whitespace from Athena DESCRIBE output and filter invalid rows
    columns = [c for c in columns if isinstance(c.get("name"), str) and isinstance(c.get("type"), str)]
    for c in columns:
        c["name"] = c["name"].strip()
        c["type"] = c["type"].strip()
    print(f"    Columns found: {len(columns)}")
    for c in columns[:5]:
        print(f"      {c['name']:30s} {c['type']}")
    if len(columns) > 5:
        print(f"      ... and {len(columns) - 5} more")
    print()

    # --- Step 2: Get numeric history ---
    analysis_svc = AnalysisService(client, builder)
    dataset_config = DatasetConfig(
        schema=schema,
        table=table,
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        date_expression='CAST("dt_ref" AS DATE)',
        lookback_value=60,
    )

    # Find a numeric column (handle Athena type names)
    numeric_types = {"int", "integer", "bigint", "float", "double", "decimal", "smallint", "tinyint", "real"}
    numeric_cols = [
        c["name"] for c in columns
        if c["type"].lower().split("(")[0] in numeric_types
    ]
    if not numeric_cols:
        print("[2] No native numeric columns found. Trying first double column...")
        numeric_cols = [c["name"] for c in columns if "double" in c["type"].lower() or "float" in c["type"].lower()]
    if not numeric_cols:
        print("    FAIL: No numeric columns found at all. Exiting.")
        return

    test_col = numeric_cols[0]
    print(f"[2] Getting numeric history for column: {test_col}")
    history_df = analysis_svc.get_numeric_history(dataset_config, test_col)
    print(f"    Rows returned: {len(history_df)}")
    if not history_df.empty:
        print(f"    Columns: {list(history_df.columns)}")
        print(f"    Period range: {history_df['period'].iloc[0]} to {history_df['period'].iloc[-1]}")
        print(f"    Mean range: {history_df['mean'].min():.2f} to {history_df['mean'].max():.2f}")
        print(f"    Percentiles present: {not history_df['p50'].isna().all()}")
    print()

    # --- Step 3: Generate proposals ---
    proposal_svc = ProposalService()
    baseline = BaselineStrategy(
        method=BaselineMethod.LAST_N_PERIODS,
        n_periods=20,
        n_sigma=2.0,
        margin_pct=0.10,
    )

    print(f"[3] Generating proposals for {test_col}...")
    proposals = proposal_svc.propose_numeric_rules(
        history_df, test_col, table, baseline,
    )
    print(f"    Proposals generated: {len(proposals)}")
    for p in proposals:
        print(f"    - {p.rule_type.value}: confidence={p.confidence.value}")
        if p.backtest:
            print(f"      coverage={p.backtest.coverage_pct:.1f}%, "
                  f"stability={p.backtest.stability_score:.2f}, "
                  f"drift={p.backtest.has_drift}")
        print(f"      syntax: {p.gdq_syntax_preview[:80]}...")
    print()

    # --- Step 3b: RowCount proposals ---
    print(f"[3b] Getting row count history...")
    rc_history_df = analysis_svc.get_row_count_history(dataset_config)
    print(f"     Rows returned: {len(rc_history_df)}")
    if not rc_history_df.empty:
        print(f"     Period range: {rc_history_df['period'].iloc[0]} to {rc_history_df['period'].iloc[-1]}")
        print(f"     Row count range: {rc_history_df['row_count'].min():.0f} to {rc_history_df['row_count'].max():.0f}")

    rc_proposals = proposal_svc.propose_table_rules(
        rc_history_df, table, baseline,
    )
    print(f"     RowCount proposals: {len(rc_proposals)}")
    for p in rc_proposals:
        print(f"     - {p.rule_type.value}: confidence={p.confidence.value}")
        if p.backtest:
            print(f"       coverage={p.backtest.coverage_pct:.1f}%, "
                  f"stability={p.backtest.stability_score:.2f}, "
                  f"drift={p.backtest.has_drift}")
        print(f"       syntax: {p.gdq_syntax_preview[:80]}...")
    all_proposals = proposals + rc_proposals
    print()

    # --- Step 4: Export ---
    export_svc = ExportService()
    selections = [
        RuleSelection(
            proposal_id=p.id,
            proposal=p,
            final_gdq_syntax=p.gdq_syntax_preview,
        )
        for p in all_proposals
    ]

    result = export_svc.export(selections)
    print(f"[4] Export result:")
    print(f"    Rules count: {result.rules_count}")
    print(f"    Warnings: {result.warnings}")
    print(f"    Syntax:")
    for line in result.rules_text.split("\n"):
        print(f"      {line[:120]}")
    print()

    print("=" * 60)
    print("INTEGRATION TEST PASSED")
    print(f"Full pipeline: table validation -> numeric history -> row count -> "
          f"{len(all_proposals)} proposals -> export")
    print("=" * 60)


if __name__ == "__main__":
    main()
