"""
Interactive script to automate AWS environment setup for GDQ Rule Proposer.

Wraps all manual steps from docs/aws_test_setup.md (steps 1-6) into an
interactive CLI with confirmations, state persistence, idempotency, and cleanup.

Usage:
    python scripts/aws_setup.py              # full setup (interactive)
    python scripts/aws_setup.py --cleanup    # tear down in reverse order
    python scripts/aws_setup.py --status     # show what's been done
    python scripts/aws_setup.py --region us-east-2  # override region
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_DIR = Path("aws_test_data")
STATE_FILE = STATE_DIR / ".aws_setup_state.json"
LOCAL_DATA_DIR = "aws_test_data"

DATABASE_NAME = "gdq_test_db"
TABLE_INCREMENTAL = "tb_operacoes_incremental"
TABLE_FULL = "tb_cadastro_full"
IAM_USER = "gdq-readonly"
IAM_POLICY_NAME = "GDQReadOnlyPolicy"
WORKGROUP_NAME = "gdq-test"
PROFILE_NAME = "gdq-test"
DEFAULT_REGION = "us-east-1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_aws(
    args: list[str],
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run an AWS CLI command, printing it first for transparency."""
    cmd = ["aws"] + args
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        raise RuntimeError(f"AWS command failed (rc={result.returncode}): {stderr}")
    return result


def run_aws_quiet(args: list[str]) -> subprocess.CompletedProcess:
    """Run AWS CLI without printing or raising on failure."""
    return subprocess.run(
        ["aws"] + args,
        capture_output=True,
        text=True,
    )


def confirm(msg: str) -> bool:
    """Ask user for y/n confirmation. Returns True on 'y'."""
    while True:
        answer = input(f"\n{msg} [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please answer y or n.")


def load_state() -> dict[str, Any]:
    """Load persisted state from JSON file."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"completed_steps": []}


def save_state(state: dict[str, Any]) -> None:
    """Save state to JSON file."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_step_done(state: dict[str, Any], step_id: str) -> bool:
    return step_id in state.get("completed_steps", [])


def mark_done(state: dict[str, Any], step_id: str) -> None:
    if step_id not in state.get("completed_steps", []):
        state.setdefault("completed_steps", []).append(step_id)
    save_state(state)


def write_temp_json(data: dict, filename: str) -> Path:
    """Write a dict as JSON to a temp file in aws_test_data/."""
    path = STATE_DIR / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def remove_temp_file(filename: str) -> None:
    path = STATE_DIR / filename
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Table definitions (Glue)
# ---------------------------------------------------------------------------


def get_incremental_table_input(bucket_name: str) -> dict:
    return {
        "Name": TABLE_INCREMENTAL,
        "Description": "Operacoes de credito - incremental por dia",
        "StorageDescriptor": {
            "Columns": [
                {"Name": "NUM_CTRT_OPCR", "Type": "string"},
                {"Name": "VLR_SALD_AVNC_OPCR", "Type": "double"},
                {"Name": "VLR_PARC_OPCR", "Type": "double"},
                {"Name": "VLR_CNTR_OPCR", "Type": "double"},
                {"Name": "VLR_SALD_DEVE_CTBL", "Type": "double"},
                {"Name": "COD_SITU_OPCR", "Type": "string"},
            ],
            "Location": f"s3://{bucket_name}/data/incremental/",
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
            },
        },
        "PartitionKeys": [{"Name": "dt_ref", "Type": "string"}],
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": "parquet",
            "projection.enabled": "true",
            "projection.dt_ref.type": "date",
            "projection.dt_ref.format": "yyyy-MM-dd",
            "projection.dt_ref.range": "2025-01-01,NOW",
            "projection.dt_ref.interval": "1",
            "projection.dt_ref.interval.unit": "DAYS",
            "storage.location.template": f"s3://{bucket_name}/data/incremental/dt_ref=${{dt_ref}}/",
        },
    }


def get_full_table_input(bucket_name: str) -> dict:
    return {
        "Name": TABLE_FULL,
        "Description": "Cadastro de clientes - full snapshot por carga",
        "StorageDescriptor": {
            "Columns": [
                {"Name": "ID_CLIENTE", "Type": "string"},
                {"Name": "DT_ABERTURA", "Type": "string"},
                {"Name": "VLR_LIMITE", "Type": "double"},
                {"Name": "VLR_SALDO", "Type": "double"},
                {"Name": "COD_SEGMENTO", "Type": "string"},
                {"Name": "IND_ATIVO", "Type": "int"},
                {"Name": "QTD_PRODUTOS", "Type": "int"},
            ],
            "Location": f"s3://{bucket_name}/data/full_snapshot/",
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
            },
        },
        "PartitionKeys": [{"Name": "dt_carga", "Type": "string"}],
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": "parquet",
            "projection.enabled": "true",
            "projection.dt_carga.type": "date",
            "projection.dt_carga.format": "yyyy-MM-dd",
            "projection.dt_carga.range": "2025-01-01,NOW",
            "projection.dt_carga.interval": "1",
            "projection.dt_carga.interval.unit": "DAYS",
            "storage.location.template": f"s3://{bucket_name}/data/full_snapshot/dt_carga=${{dt_carga}}/",
        },
    }


# ---------------------------------------------------------------------------
# IAM policy document
# ---------------------------------------------------------------------------


def get_iam_policy_document(bucket_name: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AthenaQueryOnly",
                "Effect": "Allow",
                "Action": [
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:StopQueryExecution",
                    "athena:ListWorkGroups",
                    "athena:GetWorkGroup",
                ],
                "Resource": "*",
            },
            {
                "Sid": "GlueCatalogReadOnly",
                "Effect": "Allow",
                "Action": [
                    "glue:GetDatabase",
                    "glue:GetDatabases",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartition",
                    "glue:GetPartitions",
                ],
                "Resource": "*",
            },
            {
                "Sid": "S3ReadData",
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:GetBucketLocation",
                ],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*",
                ],
            },
            {
                "Sid": "S3WriteAthenaResults",
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:AbortMultipartUpload",
                ],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}/athena-results/*",
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Setup steps
# ---------------------------------------------------------------------------


def step_detect_account(state: dict[str, Any], region: str) -> None:
    """(a) Detect AWS account ID from current credentials."""
    step_id = "detect_account"
    if is_step_done(state, step_id):
        print(f"  [skip] Already done. Account: {state.get('account_id', '?')}")
        return

    print("\nStep 1/14: Detect AWS account ID")
    print("  This calls 'aws sts get-caller-identity' to find your account ID.")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    result = run_aws(
        ["sts", "get-caller-identity", "--query", "Account", "--output", "text"]
    )
    account_id = result.stdout.strip()
    if not account_id or not account_id.isdigit():
        raise RuntimeError(f"Could not detect account ID. Got: {account_id!r}")

    state["account_id"] = account_id
    state["region"] = region
    state["bucket_name"] = f"gdq-test-data-{account_id[-4:]}"

    mark_done(state, step_id)
    print(f"  Account ID: {account_id}")
    print(f"  Bucket name will be: {state['bucket_name']}")
    print(f"  Region: {region}")


def step_create_bucket(state: dict[str, Any]) -> None:
    """(b) Create S3 bucket."""
    step_id = "create_bucket"
    bucket = state["bucket_name"]
    region = state["region"]

    if is_step_done(state, step_id):
        print(f"  [skip] Bucket {bucket} already created.")
        return

    print(f"\nStep 2/14: Create S3 bucket '{bucket}'")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    try:
        run_aws(["s3", "mb", f"s3://{bucket}", "--region", region])
    except RuntimeError as e:
        if "BucketAlreadyOwnedByYou" in str(e):
            print("  Bucket already exists (owned by you). Continuing.")
        else:
            raise

    # Create folder structure
    for key in ["data/incremental/", "data/full_snapshot/", "athena-results/"]:
        run_aws(["s3api", "put-object", "--bucket", bucket, "--key", key])

    mark_done(state, step_id)
    print(f"  Bucket {bucket} created with folder structure.")


def step_upload_data(state: dict[str, Any]) -> None:
    """(c) Generate test data locally and upload to S3."""
    step_id = "upload_data"
    bucket = state["bucket_name"]

    if is_step_done(state, step_id):
        print("  [skip] Data already uploaded.")
        return

    print("\nStep 3/14: Generate test data and upload to S3")
    print(f"  Will run: scripts/generate_aws_test_data.py --bucket {bucket} --upload")
    print(f"  Local data dir: {LOCAL_DATA_DIR}/")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    # Run the existing generation script
    result = subprocess.run(
        [
            sys.executable,
            "scripts/generate_aws_test_data.py",
            "--bucket", bucket,
            "--local-dir", LOCAL_DATA_DIR,
            "--upload",
        ],
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Data generation/upload failed.")

    mark_done(state, step_id)
    print("  Data uploaded to S3.")


def step_create_glue_db(state: dict[str, Any]) -> None:
    """(d) Create Glue database."""
    step_id = "create_glue_db"
    region = state["region"]

    if is_step_done(state, step_id):
        print(f"  [skip] Database {DATABASE_NAME} already created.")
        return

    print(f"\nStep 4/14: Create Glue database '{DATABASE_NAME}'")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    db_input = json.dumps({
        "Name": DATABASE_NAME,
        "Description": "GDQ Rule Proposer test database",
    })

    try:
        run_aws([
            "glue", "create-database",
            "--database-input", db_input,
            "--region", region,
        ])
    except RuntimeError as e:
        if "AlreadyExistsException" in str(e):
            print(f"  Database {DATABASE_NAME} already exists. Continuing.")
        else:
            raise

    mark_done(state, step_id)
    print(f"  Database {DATABASE_NAME} created.")


def step_create_table_incremental(state: dict[str, Any]) -> None:
    """(e) Create Glue table: tb_operacoes_incremental."""
    step_id = "create_table_incremental"
    region = state["region"]
    bucket = state["bucket_name"]

    if is_step_done(state, step_id):
        print(f"  [skip] Table {TABLE_INCREMENTAL} already created.")
        return

    print(f"\nStep 5/14: Create Glue table '{TABLE_INCREMENTAL}'")
    print("  Columns: NUM_CTRT_OPCR, VLR_SALD_AVNC_OPCR, VLR_PARC_OPCR,")
    print("           VLR_CNTR_OPCR, VLR_SALD_DEVE_CTBL, COD_SITU_OPCR")
    print("  Partition key: dt_ref (string, date projection)")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    table_input = get_incremental_table_input(bucket)
    tmp_file = ".tmp_table_incremental.json"
    tmp_path = write_temp_json(table_input, tmp_file)

    try:
        run_aws([
            "glue", "create-table",
            "--region", region,
            "--database-name", DATABASE_NAME,
            "--table-input", f"file://{tmp_path.as_posix()}",
        ])
    except RuntimeError as e:
        if "AlreadyExistsException" in str(e):
            print(f"  Table {TABLE_INCREMENTAL} already exists. Continuing.")
        else:
            raise
    finally:
        remove_temp_file(tmp_file)

    mark_done(state, step_id)
    print(f"  Table {TABLE_INCREMENTAL} created.")


def step_create_table_full(state: dict[str, Any]) -> None:
    """(f) Create Glue table: tb_cadastro_full."""
    step_id = "create_table_full"
    region = state["region"]
    bucket = state["bucket_name"]

    if is_step_done(state, step_id):
        print(f"  [skip] Table {TABLE_FULL} already created.")
        return

    print(f"\nStep 6/14: Create Glue table '{TABLE_FULL}'")
    print("  Columns: ID_CLIENTE, DT_ABERTURA, VLR_LIMITE, VLR_SALDO,")
    print("           COD_SEGMENTO, IND_ATIVO, QTD_PRODUTOS")
    print("  Partition key: dt_carga (string, date projection)")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    table_input = get_full_table_input(bucket)
    tmp_file = ".tmp_table_full.json"
    tmp_path = write_temp_json(table_input, tmp_file)

    try:
        run_aws([
            "glue", "create-table",
            "--region", region,
            "--database-name", DATABASE_NAME,
            "--table-input", f"file://{tmp_path.as_posix()}",
        ])
    except RuntimeError as e:
        if "AlreadyExistsException" in str(e):
            print(f"  Table {TABLE_FULL} already exists. Continuing.")
        else:
            raise
    finally:
        remove_temp_file(tmp_file)

    mark_done(state, step_id)
    print(f"  Table {TABLE_FULL} created.")


def step_create_workgroup(state: dict[str, Any]) -> None:
    """(g) Create Athena workgroup with cost limit."""
    step_id = "create_workgroup"
    region = state["region"]
    bucket = state["bucket_name"]

    if is_step_done(state, step_id):
        print(f"  [skip] Workgroup {WORKGROUP_NAME} already created.")
        return

    print(f"\nStep 7/14: Create Athena workgroup '{WORKGROUP_NAME}'")
    print(f"  Output: s3://{bucket}/athena-results/")
    print("  Cost limit: 100MB per query")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    config = (
        f"ResultConfiguration={{OutputLocation=s3://{bucket}/athena-results/}},"
        f"EnforceWorkGroupConfiguration=true,"
        f"BytesScannedCutoffPerQuery=100000000"
    )

    try:
        run_aws([
            "athena", "create-work-group",
            "--name", WORKGROUP_NAME,
            "--configuration", config,
            "--region", region,
        ])
    except RuntimeError as e:
        # Athena doesn't have a standard "already exists" exception name,
        # but the error message contains "already exists"
        if "already exists" in str(e).lower():
            print(f"  Workgroup {WORKGROUP_NAME} already exists. Continuing.")
        else:
            raise

    mark_done(state, step_id)
    print(f"  Workgroup {WORKGROUP_NAME} created.")


def step_create_iam_policy(state: dict[str, Any]) -> None:
    """(h) Create IAM policy for readonly access."""
    step_id = "create_iam_policy"
    bucket = state["bucket_name"]

    if is_step_done(state, step_id):
        print(f"  [skip] Policy {IAM_POLICY_NAME} already created.")
        return

    print(f"\nStep 8/14: Create IAM policy '{IAM_POLICY_NAME}'")
    print("  Permissions: Athena query, S3 read, Glue catalog read,")
    print(f"               S3 write to {bucket}/athena-results/")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    policy_doc = get_iam_policy_document(bucket)
    tmp_file = ".tmp_iam_policy.json"
    tmp_path = write_temp_json(policy_doc, tmp_file)

    try:
        result = run_aws([
            "iam", "create-policy",
            "--policy-name", IAM_POLICY_NAME,
            "--policy-document", f"file://{tmp_path.as_posix()}",
            "--output", "json",
        ])
        resp = json.loads(result.stdout)
        policy_arn = resp["Policy"]["Arn"]
    except RuntimeError as e:
        if "EntityAlreadyExists" in str(e):
            print(f"  Policy {IAM_POLICY_NAME} already exists. Fetching ARN...")
            result = run_aws([
                "iam", "list-policies",
                "--query", f"Policies[?PolicyName=='{IAM_POLICY_NAME}'].Arn",
                "--output", "text",
            ])
            policy_arn = result.stdout.strip()
        else:
            raise
    finally:
        remove_temp_file(tmp_file)

    state["policy_arn"] = policy_arn
    mark_done(state, step_id)
    print(f"  Policy ARN: {policy_arn}")


def step_create_iam_user(state: dict[str, Any]) -> None:
    """(i) Create IAM user."""
    step_id = "create_iam_user"

    if is_step_done(state, step_id):
        print(f"  [skip] User {IAM_USER} already created.")
        return

    print(f"\nStep 9/14: Create IAM user '{IAM_USER}'")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    try:
        run_aws(["iam", "create-user", "--user-name", IAM_USER])
    except RuntimeError as e:
        if "EntityAlreadyExists" in str(e):
            print(f"  User {IAM_USER} already exists. Continuing.")
        else:
            raise

    mark_done(state, step_id)
    print(f"  User {IAM_USER} created.")


def step_attach_policy(state: dict[str, Any]) -> None:
    """(j) Attach policy to user."""
    step_id = "attach_policy"
    policy_arn = state.get("policy_arn", "")

    if is_step_done(state, step_id):
        print("  [skip] Policy already attached.")
        return

    if not policy_arn:
        print("  [error] No policy_arn in state. Run create_iam_policy first.")
        return

    print(f"\nStep 10/14: Attach policy to user '{IAM_USER}'")
    print(f"  Policy: {policy_arn}")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    run_aws([
        "iam", "attach-user-policy",
        "--user-name", IAM_USER,
        "--policy-arn", policy_arn,
    ])

    mark_done(state, step_id)
    print("  Policy attached.")


def step_create_access_key(state: dict[str, Any]) -> None:
    """(k) Create access key for the IAM user."""
    step_id = "create_access_key"

    if is_step_done(state, step_id):
        print(f"  [skip] Access key already created: {state.get('access_key_id', '?')}")
        return

    print(f"\nStep 11/14: Create access key for '{IAM_USER}'")
    print("  WARNING: The secret key will only be shown ONCE.")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    result = run_aws([
        "iam", "create-access-key",
        "--user-name", IAM_USER,
        "--output", "json",
    ])
    resp = json.loads(result.stdout)
    access_key_id = resp["AccessKey"]["AccessKeyId"]
    secret_key = resp["AccessKey"]["SecretAccessKey"]

    state["access_key_id"] = access_key_id
    # Do NOT persist the secret key -- it's shown once only
    mark_done(state, step_id)

    print("")
    print("  =========================================")
    print(f"  ACCESS KEY ID:     {access_key_id}")
    print(f"  SECRET ACCESS KEY: {secret_key}")
    print("  =========================================")
    print("  SAVE THESE NOW! The secret key cannot be retrieved again.")
    print("")

    # Store secret temporarily in memory for the configure_profile step
    state["_secret_key_tmp"] = secret_key


def step_configure_profile(state: dict[str, Any]) -> None:
    """(l) Configure AWS CLI profile 'gdq-test'."""
    step_id = "configure_profile"
    region = state["region"]
    access_key_id = state.get("access_key_id", "")
    # The secret might be in memory from the previous step, or user enters it
    secret_key = state.pop("_secret_key_tmp", "")

    if is_step_done(state, step_id):
        print(f"  [skip] Profile {PROFILE_NAME} already configured.")
        return

    print(f"\nStep 12/14: Configure AWS CLI profile '{PROFILE_NAME}'")

    if not access_key_id:
        access_key_id = input("  Enter Access Key ID: ").strip()
    if not secret_key:
        secret_key = input("  Enter Secret Access Key: ").strip()

    if not access_key_id or not secret_key:
        print("  [error] Access key ID and secret key are required.")
        return

    print(f"  Will set profile '{PROFILE_NAME}' with:")
    print(f"    access_key_id = {access_key_id}")
    print(f"    region        = {region}")
    print(f"    output        = json")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    run_aws(["configure", "set", f"profile.{PROFILE_NAME}.aws_access_key_id", access_key_id])
    run_aws(["configure", "set", f"profile.{PROFILE_NAME}.aws_secret_access_key", secret_key])
    run_aws(["configure", "set", f"profile.{PROFILE_NAME}.region", region])
    run_aws(["configure", "set", f"profile.{PROFILE_NAME}.output", "json"])

    mark_done(state, step_id)
    print(f"  Profile {PROFILE_NAME} configured.")


def step_test_athena_query(state: dict[str, Any]) -> None:
    """(m) Run a test query on Athena to verify everything works."""
    step_id = "test_athena_query"
    region = state["region"]

    if is_step_done(state, step_id):
        print("  [skip] Test query already passed.")
        return

    query = (
        f"SELECT COUNT(*) as cnt FROM {DATABASE_NAME}.{TABLE_INCREMENTAL} "
        f"LIMIT 10"
    )

    print("\nStep 13/14: Test Athena query")
    print(f"  Query: {query}")
    print(f"  Profile: {PROFILE_NAME}")

    if not confirm("Execute?"):
        print("  Skipped.")
        return

    # Start query execution
    result = run_aws([
        "athena", "start-query-execution",
        "--query-string", query,
        "--work-group", WORKGROUP_NAME,
        "--profile", PROFILE_NAME,
        "--region", region,
        "--output", "json",
    ])
    resp = json.loads(result.stdout)
    execution_id = resp["QueryExecutionId"]
    print(f"  Query started: {execution_id}")

    # Poll for completion
    print("  Waiting for query to complete", end="", flush=True)
    for _ in range(30):
        time.sleep(2)
        print(".", end="", flush=True)
        poll = run_aws([
            "athena", "get-query-execution",
            "--query-execution-id", execution_id,
            "--profile", PROFILE_NAME,
            "--region", region,
            "--output", "json",
        ])
        poll_resp = json.loads(poll.stdout)
        query_state = poll_resp["QueryExecution"]["Status"]["State"]
        if query_state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
    print()

    if query_state != "SUCCEEDED":
        reason = poll_resp["QueryExecution"]["Status"].get(
            "StateChangeReason", "unknown"
        )
        print(f"  Query {query_state}: {reason}")
        print("  Test NOT passed. Fix issues and re-run this step.")
        return

    # Get results
    results = run_aws([
        "athena", "get-query-results",
        "--query-execution-id", execution_id,
        "--profile", PROFILE_NAME,
        "--region", region,
        "--output", "json",
    ])
    results_resp = json.loads(results.stdout)
    rows = results_resp.get("ResultSet", {}).get("Rows", [])
    if len(rows) >= 2:
        count_val = rows[1]["Data"][0].get("VarCharValue", "?")
        print(f"  Result: COUNT(*) = {count_val}")
    else:
        print(f"  Result rows: {rows}")

    mark_done(state, step_id)
    print("  Athena test query PASSED.")


def step_generate_env_dev(state: dict[str, Any]) -> None:
    """(n) Generate .env.dev file."""
    step_id = "generate_env_dev"
    region = state["region"]
    bucket = state["bucket_name"]

    if is_step_done(state, step_id):
        print("  [skip] .env.dev already generated.")
        return

    env_content = (
        f"GDQ_ENV=dev\n"
        f"GDQ_ATHENA_REGION={region}\n"
        f"GDQ_ATHENA_WORKGROUP={WORKGROUP_NAME}\n"
        f"GDQ_ATHENA_S3_OUTPUT=s3://{bucket}/athena-results/\n"
        f"GDQ_AWS_PROFILE={PROFILE_NAME}\n"
    )

    print("\nStep 14/14: Generate .env.dev")
    print("  Contents:")
    for line in env_content.strip().split("\n"):
        print(f"    {line}")

    if not confirm("Write .env.dev?"):
        print("  Skipped.")
        return

    env_path = Path(".env.dev")
    env_path.write_text(env_content, encoding="utf-8")

    mark_done(state, step_id)
    print("  .env.dev written.")


# ---------------------------------------------------------------------------
# Cleanup steps (reverse order)
# ---------------------------------------------------------------------------


def cleanup_access_key(state: dict[str, Any]) -> None:
    """Delete IAM access key."""
    access_key_id = state.get("access_key_id")
    if not access_key_id:
        print("  [skip] No access_key_id in state.")
        return
    print(f"  Deleting access key {access_key_id} for user {IAM_USER}...")
    run_aws_quiet([
        "iam", "delete-access-key",
        "--user-name", IAM_USER,
        "--access-key-id", access_key_id,
    ])


def cleanup_detach_policy(state: dict[str, Any]) -> None:
    """Detach policy from user."""
    policy_arn = state.get("policy_arn")
    if not policy_arn:
        print("  [skip] No policy_arn in state.")
        return
    print(f"  Detaching policy from {IAM_USER}...")
    run_aws_quiet([
        "iam", "detach-user-policy",
        "--user-name", IAM_USER,
        "--policy-arn", policy_arn,
    ])


def cleanup_iam_user(state: dict[str, Any]) -> None:
    """Delete IAM user."""
    print(f"  Deleting user {IAM_USER}...")
    run_aws_quiet(["iam", "delete-user", "--user-name", IAM_USER])


def cleanup_iam_policy(state: dict[str, Any]) -> None:
    """Delete IAM policy."""
    policy_arn = state.get("policy_arn")
    if not policy_arn:
        print("  [skip] No policy_arn in state.")
        return
    print(f"  Deleting policy {policy_arn}...")
    run_aws_quiet(["iam", "delete-policy", "--policy-arn", policy_arn])


def cleanup_workgroup(state: dict[str, Any]) -> None:
    """Delete Athena workgroup."""
    region = state.get("region", DEFAULT_REGION)
    print(f"  Deleting workgroup {WORKGROUP_NAME}...")
    run_aws_quiet([
        "athena", "delete-work-group",
        "--work-group", WORKGROUP_NAME,
        "--recursive-delete-option",
        "--region", region,
    ])


def cleanup_tables(state: dict[str, Any]) -> None:
    """Delete Glue tables."""
    region = state.get("region", DEFAULT_REGION)
    for table in [TABLE_INCREMENTAL, TABLE_FULL]:
        print(f"  Deleting table {table}...")
        run_aws_quiet([
            "glue", "delete-table",
            "--database-name", DATABASE_NAME,
            "--name", table,
            "--region", region,
        ])


def cleanup_glue_db(state: dict[str, Any]) -> None:
    """Delete Glue database."""
    region = state.get("region", DEFAULT_REGION)
    print(f"  Deleting database {DATABASE_NAME}...")
    run_aws_quiet([
        "glue", "delete-database",
        "--name", DATABASE_NAME,
        "--region", region,
    ])


def cleanup_bucket(state: dict[str, Any]) -> None:
    """Empty and delete S3 bucket."""
    bucket = state.get("bucket_name")
    if not bucket:
        print("  [skip] No bucket_name in state.")
        return
    print(f"  Emptying bucket {bucket}...")
    run_aws_quiet(["s3", "rm", f"s3://{bucket}", "--recursive"])
    print(f"  Deleting bucket {bucket}...")
    run_aws_quiet(["s3", "rb", f"s3://{bucket}"])


def do_cleanup(state: dict[str, Any]) -> None:
    """Run all cleanup steps in reverse order."""
    print("\n=== CLEANUP ===")
    print("This will delete ALL AWS resources created by this script.")
    print("Resources to remove:")
    print(f"  - IAM access key: {state.get('access_key_id', 'N/A')}")
    print(f"  - IAM user: {IAM_USER}")
    print(f"  - IAM policy: {state.get('policy_arn', 'N/A')}")
    print(f"  - Athena workgroup: {WORKGROUP_NAME}")
    print(f"  - Glue tables: {TABLE_INCREMENTAL}, {TABLE_FULL}")
    print(f"  - Glue database: {DATABASE_NAME}")
    print(f"  - S3 bucket: {state.get('bucket_name', 'N/A')}")

    if not confirm("Proceed with cleanup?"):
        print("Cleanup cancelled.")
        return

    # Order matters: detach before delete, tables before db, empty before remove
    cleanup_steps = [
        ("Detach policy", cleanup_detach_policy),
        ("Delete access key", cleanup_access_key),
        ("Delete IAM user", cleanup_iam_user),
        ("Delete IAM policy", cleanup_iam_policy),
        ("Delete workgroup", cleanup_workgroup),
        ("Delete Glue tables", cleanup_tables),
        ("Delete Glue database", cleanup_glue_db),
        ("Empty and delete S3 bucket", cleanup_bucket),
    ]

    for name, fn in cleanup_steps:
        print(f"\n-- {name} --")
        try:
            fn(state)
            print("  Done.")
        except Exception as e:
            print(f"  Warning: {e}")

    # Reset state
    state["completed_steps"] = []
    save_state(state)
    print("\nCleanup complete. State file reset.")
    print(f"Note: AWS CLI profile '{PROFILE_NAME}' was NOT removed.")
    print("  To remove it manually: edit ~/.aws/credentials and ~/.aws/config")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def do_status(state: dict[str, Any]) -> None:
    """Print current setup status."""
    completed = state.get("completed_steps", [])

    all_steps = [
        ("detect_account", "Detect AWS account"),
        ("create_bucket", "Create S3 bucket"),
        ("upload_data", "Upload test data"),
        ("create_glue_db", "Create Glue database"),
        ("create_table_incremental", f"Create table {TABLE_INCREMENTAL}"),
        ("create_table_full", f"Create table {TABLE_FULL}"),
        ("create_workgroup", "Create Athena workgroup"),
        ("create_iam_policy", "Create IAM policy"),
        ("create_iam_user", "Create IAM user"),
        ("attach_policy", "Attach policy to user"),
        ("create_access_key", "Create access key"),
        ("configure_profile", "Configure AWS CLI profile"),
        ("test_athena_query", "Test Athena query"),
        ("generate_env_dev", "Generate .env.dev"),
    ]

    print("\n=== AWS Setup Status ===\n")

    if not completed:
        print("No setup steps completed yet.")
        print(f"Run: python scripts/aws_setup.py")
        return

    print(f"Account ID:  {state.get('account_id', 'N/A')}")
    print(f"Region:      {state.get('region', 'N/A')}")
    print(f"Bucket:      {state.get('bucket_name', 'N/A')}")
    print(f"Policy ARN:  {state.get('policy_arn', 'N/A')}")
    print(f"Access Key:  {state.get('access_key_id', 'N/A')}")
    print()

    for step_id, desc in all_steps:
        marker = "[x]" if step_id in completed else "[ ]"
        print(f"  {marker} {desc}")

    done = len(completed)
    total = len(all_steps)
    print(f"\n{done}/{total} steps completed.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def do_setup(region: str) -> None:
    """Run all setup steps interactively."""
    state = load_state()

    print("=== GDQ Rule Proposer - AWS Environment Setup ===")
    print(f"Region: {region}")
    print("This script will walk you through each step with confirmation.")
    print("Progress is saved -- you can stop and resume at any time.\n")

    setup_steps = [
        lambda s: step_detect_account(s, region),
        step_create_bucket,
        step_upload_data,
        step_create_glue_db,
        step_create_table_incremental,
        step_create_table_full,
        step_create_workgroup,
        step_create_iam_policy,
        step_create_iam_user,
        step_attach_policy,
        step_create_access_key,
        step_configure_profile,
        step_test_athena_query,
        step_generate_env_dev,
    ]

    for step_fn in setup_steps:
        try:
            step_fn(state)
        except RuntimeError as e:
            print(f"\n  ERROR: {e}")
            print("  Fix the issue and re-run the script. Progress is saved.")
            return
        except KeyboardInterrupt:
            print("\n\nInterrupted. Progress saved. Re-run to continue.")
            return

    print("\n=== Setup Complete ===")
    print(f"  Bucket:     {state.get('bucket_name')}")
    print(f"  Database:   {DATABASE_NAME}")
    print(f"  Tables:     {TABLE_INCREMENTAL}, {TABLE_FULL}")
    print(f"  Workgroup:  {WORKGROUP_NAME}")
    print(f"  Profile:    {PROFILE_NAME}")
    print(f"  .env.dev:   written")
    print(f"\nTo verify: python scripts/aws_setup.py --status")
    print(f"To tear down: python scripts/aws_setup.py --cleanup")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automate AWS environment setup for GDQ Rule Proposer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/aws_setup.py              # full setup\n"
            "  python scripts/aws_setup.py --status     # show progress\n"
            "  python scripts/aws_setup.py --cleanup    # tear down\n"
            "  python scripts/aws_setup.py --region us-east-2\n"
        ),
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Tear down all AWS resources in reverse order",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current setup status",
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help=f"AWS region (default: {DEFAULT_REGION})",
    )
    args = parser.parse_args()

    if args.status:
        do_status(load_state())
    elif args.cleanup:
        do_cleanup(load_state())
    else:
        do_setup(args.region)


if __name__ == "__main__":
    main()
