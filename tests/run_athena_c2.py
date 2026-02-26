"""Sprint C2 - Athena Integration Test Script."""
import os
import sys

os.environ["GDQ_ENV"] = "dev"
os.environ["AWS_PROFILE"] = "gdq-test"

print("=" * 60)
print("SPRINT C2 - ATHENA INTEGRATION TEST")
print("=" * 60)

# --- Setup ---
from config import get_config
config = get_config()
print(f"Config env: {config.env}")
print(f"Athena mode: {config.athena.mode}")

from infra.athena_client import create_executor
executor = create_executor(config)
print(f"Executor type: {type(executor).__name__}")

# --- Config ---
TABLE = "tb_operacoes_incremental"
SCHEMA = "gdq_test_db"
DATE_COL = "dt_ref"
DATE_EXPR = "CAST(\"dt_ref\" AS DATE)"
LOOKBACK = 60
NUMERIC_COL = "vlr_sald_avnc_opcr"
CAT_COL = "cod_situ_opcr"
