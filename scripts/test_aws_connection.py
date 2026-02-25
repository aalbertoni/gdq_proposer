"""
Test AWS connection by running 4 queries against Athena via AthenaClient (REAL mode).

Loads config from .env.dev, connects via PyAthena, and runs:
  a) DESCRIBE tb_operacoes_incremental
  b) SELECT dt_ref, COUNT(*) ... LIMIT 5
  c) DESCRIBE tb_cadastro_full
  d) SELECT dt_carga, COUNT(*) ... LIMIT 5

Usage:
    python scripts/test_aws_connection.py
"""

from __future__ import annotations

import os
import sys

# Force dev mode so load_config reads .env.dev and uses AthenaMode.REAL
os.environ["GDQ_ENV"] = "dev"

# Add project root to path so imports work when running from scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import load_config
from infra.athena_client import AthenaClient

DATABASE = "gdq_test_db"
TABLE_INC = "tb_operacoes_incremental"
TABLE_FULL = "tb_cadastro_full"

QUERIES = [
    {
        "name": f"DESCRIBE {TABLE_INC}",
        "sql": f'DESCRIBE "{DATABASE}"."{TABLE_INC}"',
        "description": "Colunas da tabela incremental",
    },
    {
        "name": f"Row counts por dt_ref ({TABLE_INC})",
        "sql": (
            f"SELECT dt_ref, COUNT(*) as row_count "
            f'FROM "{DATABASE}"."{TABLE_INC}" '
            f"GROUP BY dt_ref ORDER BY dt_ref LIMIT 5"
        ),
        "description": "Primeiras 5 particoes incrementais",
    },
    {
        "name": f"DESCRIBE {TABLE_FULL}",
        "sql": f'DESCRIBE "{DATABASE}"."{TABLE_FULL}"',
        "description": "Colunas da tabela full snapshot",
    },
    {
        "name": f"Row counts por dt_carga ({TABLE_FULL})",
        "sql": (
            f"SELECT dt_carga, COUNT(*) as row_count "
            f'FROM "{DATABASE}"."{TABLE_FULL}" '
            f"GROUP BY dt_carga ORDER BY dt_carga LIMIT 5"
        ),
        "description": "Primeiras 5 particoes full snapshot",
    },
]


def print_dataframe(df) -> None:
    """Print a DataFrame as a formatted table (ASCII-safe)."""
    if df.empty:
        print("    (empty)")
        return

    # Build column widths
    cols = list(df.columns)
    widths = {c: max(len(str(c)), df[c].astype(str).str.len().max()) for c in cols}

    # Header
    header = "  ".join(str(c).ljust(widths[c]) for c in cols)
    print(f"    {header}")
    print(f"    {'  '.join('-' * widths[c] for c in cols)}")

    # Rows
    for _, row in df.iterrows():
        line = "  ".join(str(row[c]).ljust(widths[c]) for c in cols)
        print(f"    {line}")


def main() -> None:
    config = load_config()

    print("=== GDQ Rule Proposer - AWS Connection Test ===\n")
    print(f"  Environment: {config.environment.value}")
    print(f"  Athena mode: {config.athena.mode.value}")
    print(f"  Region:      {config.athena.region}")
    print(f"  Workgroup:   {config.athena.workgroup}")
    print(f"  S3 output:   {config.athena.s3_output}")
    print(f"  AWS profile: {config.athena.aws_profile or '(none - IAM role)'}")
    print()

    if config.athena.mode.value != "real":
        print("ERROR: Expected REAL mode but got MOCK.")
        print("  Check that .env.dev exists with GDQ_ENV=dev")
        sys.exit(1)

    try:
        client = AthenaClient(config)
    except Exception as e:
        print(f"ERROR: Failed to create AthenaClient: {e}")
        sys.exit(1)

    passed = 0
    failed = 0

    for i, q in enumerate(QUERIES, 1):
        print(f"--- Query {i}/4: {q['name']} ---")
        print(f"  {q['description']}")
        print(f"  SQL: {q['sql']}")
        print()

        try:
            df = client.execute_df(q["sql"], query_name=q["name"])
            print_dataframe(df)
            print(f"  Rows returned: {len(df)}")
            print()
            passed += 1
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            print()
            failed += 1

    # Summary
    print("=" * 50)
    if failed == 0:
        print(f"\n\u2705 Conexao AWS OK! ({passed}/{passed + failed} queries passed)")
    else:
        print(f"\n\u274c {failed} query(ies) failed, {passed} passed.")
        print("  Check your AWS setup (run: python scripts/aws_setup.py --status)")
        sys.exit(1)


if __name__ == "__main__":
    main()
