# Setup AWS — Conta Pessoal para Testes com Athena

> **Objetivo:** Criar ambiente mínimo na AWS pessoal para testar queries Athena
> com tabelas fake, usando IAM com permissões restritas (somente leitura).
> **Tempo estimado:** 20-30 minutos
> **Custo estimado:** < $1/mês (Athena cobra por dados escaneados, ~$5/TB)

---

## Visão Geral

```
┌─────────────────────────────────────────────┐
│  Seu Windows (Claude Code)                   │
│  └─ AWS CLI com profile "gdq-test"          │
│      └─ IAM User: gdq-readonly              │
│          └─ Permissões mínimas:             │
│              Athena: query only              │
│              S3: read output bucket          │
│              Glue: read catalog              │
├─────────────────────────────────────────────┤
│  AWS Account                                 │
│  ├─ S3: s3://gdq-test-data-{id}/           │
│  │   ├─ data/incremental/                   │
│  │   │   ├─ dt_ref=2026-01-01/             │
│  │   │   ├─ dt_ref=2026-01-02/             │
│  │   │   └─ ...                             │
│  │   ├─ data/full_snapshot/                 │
│  │   │   ├─ dt_carga=2026-01-01/           │
│  │   │   └─ ...                             │
│  │   └─ athena-results/                     │
│  ├─ Glue Catalog:                           │
│  │   └─ Database: gdq_test_db              │
│  │       ├─ tb_operacoes_incremental        │
│  │       └─ tb_cadastro_full                │
│  └─ Athena: workgroup "gdq-test"           │
└─────────────────────────────────────────────┘
```

---

## Passo 1: Criar Bucket S3

```bash
# Defina um sufixo único (ex: últimos 4 dígitos do seu account ID)
# Buckets S3 precisam de nomes globalmente únicos
BUCKET_NAME="gdq-test-data-$(aws sts get-caller-identity --query Account --output text | tail -c 5)"
REGION="us-east-1"

echo "Bucket: $BUCKET_NAME"

# Criar bucket
aws s3 mb s3://$BUCKET_NAME --region $REGION

# Criar estrutura de pastas
aws s3api put-object --bucket $BUCKET_NAME --key data/incremental/
aws s3api put-object --bucket $BUCKET_NAME --key data/full_snapshot/
aws s3api put-object --bucket $BUCKET_NAME --key athena-results/
```

**No PowerShell (Windows):**

```powershell
$ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$BUCKET_NAME = "gdq-test-data-$($ACCOUNT_ID.Substring($ACCOUNT_ID.Length - 4))"
$REGION = "us-east-1"

Write-Host "Bucket: $BUCKET_NAME"

aws s3 mb "s3://$BUCKET_NAME" --region $REGION
```

---

## Passo 2: Gerar e Subir Dados Fake

### 2.1 Script Python (rodar local, depois upload)

```python
# scripts/generate_aws_test_data.py
"""
Gera dados fake e faz upload para S3 em formato particionado.
Cria 2 tabelas:
  1. tb_operacoes_incremental — partição = coluna de data (incremental)
  2. tb_cadastro_full — partição = data de carga, coluna de data é interna
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, timedelta
import subprocess
import sys


def generate_incremental_table(
    output_dir: str,
    n_days: int = 45,
    rows_per_day: int = 5000,
    seed: int = 42,
):
    """Tabela incremental: partição por dt_ref, dados novos a cada dia.

    Cenário: operações de crédito diárias.
    Partição = coluna de data = dt_ref
    Cada partição tem APENAS os dados daquele dia.
    """
    rng = np.random.default_rng(seed)
    base_date = date.today() - timedelta(days=n_days)
    base_dir = Path(output_dir) / "data" / "incremental"
    base_dir.mkdir(parents=True, exist_ok=True)

    for day_offset in range(n_days):
        current_date = base_date + timedelta(days=day_offset)
        dt_str = current_date.isoformat()
        n_rows = rows_per_day + rng.integers(-300, 300)

        # Drift leve no saldo (+0.1%/dia)
        drift = 1 + (day_offset * 0.001)

        # Outlier no dia 35
        spike = 1.3 if day_offset == 35 else 1.0

        df = pd.DataFrame({
            "NUM_CTRT_OPCR": [f"CTRT{day_offset:03d}{i:06d}" for i in range(n_rows)],
            "VLR_SALD_AVNC_OPCR": rng.normal(5000 * drift * spike, 1500, n_rows).clip(0).round(2),
            "VLR_PARC_OPCR": rng.normal(500, 150, n_rows).clip(0).round(2),
            "VLR_CNTR_OPCR": rng.normal(20000, 8000, n_rows).clip(0).round(2),
            "VLR_SALD_DEVE_CTBL": np.where(
                rng.random(n_rows) < 0.7, 0.0,
                rng.exponential(1000, n_rows)
            ).round(2),
            "COD_SITU_OPCR": rng.choice(
                ['1', '2', '3'],
                size=n_rows,
                p=[0.88, 0.08, 0.04] if 28 <= day_offset <= 33 else [0.91, 0.06, 0.03],
            ),
        })

        # Nulls esparsos em VLR_PARC_OPCR (~2%)
        null_mask = rng.random(n_rows) < 0.02
        df.loc[null_mask, "VLR_PARC_OPCR"] = None

        # Salvar particionado: dt_ref=YYYY-MM-DD/data.parquet
        partition_dir = base_dir / f"dt_ref={dt_str}"
        partition_dir.mkdir(exist_ok=True)
        df.to_parquet(partition_dir / "data.parquet", index=False)

    print(f"✅ Incremental: {n_days} partições em {base_dir}")


def generate_full_snapshot_table(
    output_dir: str,
    n_snapshots: int = 45,
    n_records: int = 2000,
    seed: int = 123,
):
    """Tabela full snapshot: partição por dt_carga, coluna de data é DT_ABERTURA.

    Cenário: cadastro de clientes, foto completa a cada dia.
    Partição = dt_carga (data do processamento/carga)
    Coluna de data para análise = DT_ABERTURA (data de abertura da conta)
    Cada partição tem a foto COMPLETA do cadastro.
    """
    rng = np.random.default_rng(seed)
    base_date = date.today() - timedelta(days=n_snapshots)
    base_dir = Path(output_dir) / "data" / "full_snapshot"
    base_dir.mkdir(parents=True, exist_ok=True)

    # Base fixa de clientes
    client_ids = [f"CLI{i:06d}" for i in range(n_records)]

    # DT_ABERTURA é fixa por cliente (não muda entre snapshots)
    dt_abertura = [
        (date(2020, 1, 1) + timedelta(days=rng.integers(0, 2000))).isoformat()
        for _ in range(n_records)
    ]

    for snap_offset in range(n_snapshots):
        current_date = base_date + timedelta(days=snap_offset)
        dt_str = current_date.isoformat()

        # Alguns campos mudam entre snapshots (simula atualização)
        drift = 1 + (snap_offset * 0.0005)

        df = pd.DataFrame({
            "ID_CLIENTE": client_ids,
            "DT_ABERTURA": dt_abertura,
            "VLR_LIMITE": rng.normal(10000 * drift, 3000, n_records).clip(0).round(2),
            "VLR_SALDO": rng.normal(4000, 2000, n_records).clip(0).round(2),
            "COD_SEGMENTO": rng.choice(
                ['VAREJO', 'ALTA_RENDA', 'PRIVATE', 'MICRO'],
                size=n_records,
                p=[0.60, 0.25, 0.05, 0.10],
            ),
            "IND_ATIVO": rng.choice(
                [1, 0],
                size=n_records,
                p=[0.92, 0.08],
            ),
            "QTD_PRODUTOS": rng.poisson(3, n_records).clip(0, 15),
        })

        # A cada 10 dias, 1-2 clientes novos aparecem
        if snap_offset % 10 == 0 and snap_offset > 0:
            new_clients = pd.DataFrame({
                "ID_CLIENTE": [f"CLINEW{snap_offset:03d}{i}" for i in range(2)],
                "DT_ABERTURA": [current_date.isoformat()] * 2,
                "VLR_LIMITE": [5000.0, 8000.0],
                "VLR_SALDO": [0.0, 0.0],
                "COD_SEGMENTO": ["VAREJO", "ALTA_RENDA"],
                "IND_ATIVO": [1, 1],
                "QTD_PRODUTOS": [1, 2],
            })
            df = pd.concat([df, new_clients], ignore_index=True)

        partition_dir = base_dir / f"dt_carga={dt_str}"
        partition_dir.mkdir(exist_ok=True)
        df.to_parquet(partition_dir / "data.parquet", index=False)

    print(f"✅ Full snapshot: {n_snapshots} partições em {base_dir}")


def upload_to_s3(local_dir: str, bucket: str):
    """Upload recursivo para S3."""
    print(f"\n📤 Uploading {local_dir} → s3://{bucket}/")
    result = subprocess.run(
        ["aws", "s3", "sync", local_dir, f"s3://{bucket}/",
         "--exclude", "*.csv", "--exclude", "*.py"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"❌ Upload falhou: {result.stderr}")
        sys.exit(1)
    print(f"✅ Upload concluído")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True, help="Nome do bucket S3")
    parser.add_argument("--local-dir", default="aws_test_data", help="Dir local temp")
    parser.add_argument("--upload", action="store_true", help="Fazer upload para S3")
    args = parser.parse_args()

    print("🔧 Gerando dados fake...")
    generate_incremental_table(args.local_dir)
    generate_full_snapshot_table(args.local_dir)

    if args.upload:
        upload_to_s3(args.local_dir, args.bucket)
    else:
        print(f"\nDados gerados em: {args.local_dir}/")
        print(f"Para upload: python {sys.argv[0]} --bucket {args.bucket} --upload")
```

### 2.2 Executar

```powershell
# Gerar localmente e subir para S3
python scripts/generate_aws_test_data.py --bucket $BUCKET_NAME --upload
```

---

## Passo 3: Criar Database e Tabelas no Glue Catalog

### 3.1 Criar database

```bash
aws glue create-database \
  --database-input '{"Name": "gdq_test_db", "Description": "GDQ Rule Proposer test database"}' \
  --region $REGION
```

**PowerShell:**

```powershell
aws glue create-database `
  --database-input '{\"Name\": \"gdq_test_db\", \"Description\": \"GDQ Rule Proposer test database\"}' `
  --region $REGION
```

### 3.2 Criar tabela incremental (partição = coluna de data)

```bash
aws glue create-table --region $REGION --database-name gdq_test_db --table-input '{
  "Name": "tb_operacoes_incremental",
  "Description": "Operacoes de credito - incremental por dia",
  "StorageDescriptor": {
    "Columns": [
      {"Name": "NUM_CTRT_OPCR", "Type": "string"},
      {"Name": "VLR_SALD_AVNC_OPCR", "Type": "double"},
      {"Name": "VLR_PARC_OPCR", "Type": "double"},
      {"Name": "VLR_CNTR_OPCR", "Type": "double"},
      {"Name": "VLR_SALD_DEVE_CTBL", "Type": "double"},
      {"Name": "COD_SITU_OPCR", "Type": "string"}
    ],
    "Location": "s3://'"$BUCKET_NAME"'/data/incremental/",
    "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
    "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
    "SerdeInfo": {
      "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }
  },
  "PartitionKeys": [
    {"Name": "dt_ref", "Type": "string"}
  ],
  "TableType": "EXTERNAL_TABLE",
  "Parameters": {
    "classification": "parquet",
    "projection.enabled": "true",
    "projection.dt_ref.type": "date",
    "projection.dt_ref.format": "yyyy-MM-dd",
    "projection.dt_ref.range": "2025-01-01,NOW",
    "projection.dt_ref.interval": "1",
    "projection.dt_ref.interval.unit": "DAYS",
    "storage.location.template": "s3://'"$BUCKET_NAME"'/data/incremental/dt_ref=${dt_ref}/"
  }
}'
```

**PowerShell (salvar como JSON primeiro — mais fácil):**

```powershell
# Salvar o JSON em arquivo temporário
$tableInput = @"
{
  "Name": "tb_operacoes_incremental",
  "Description": "Operacoes de credito - incremental por dia",
  "StorageDescriptor": {
    "Columns": [
      {"Name": "NUM_CTRT_OPCR", "Type": "string"},
      {"Name": "VLR_SALD_AVNC_OPCR", "Type": "double"},
      {"Name": "VLR_PARC_OPCR", "Type": "double"},
      {"Name": "VLR_CNTR_OPCR", "Type": "double"},
      {"Name": "VLR_SALD_DEVE_CTBL", "Type": "double"},
      {"Name": "COD_SITU_OPCR", "Type": "string"}
    ],
    "Location": "s3://$BUCKET_NAME/data/incremental/",
    "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
    "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
    "SerdeInfo": {
      "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }
  },
  "PartitionKeys": [
    {"Name": "dt_ref", "Type": "string"}
  ],
  "TableType": "EXTERNAL_TABLE",
  "Parameters": {
    "classification": "parquet",
    "projection.enabled": "true",
    "projection.dt_ref.type": "date",
    "projection.dt_ref.format": "yyyy-MM-dd",
    "projection.dt_ref.range": "2025-01-01,NOW",
    "projection.dt_ref.interval": "1",
    "projection.dt_ref.interval.unit": "DAYS",
    "storage.location.template": "s3://$BUCKET_NAME/data/incremental/dt_ref=${'$'}{dt_ref}/"
  }
}
"@

# Substituir variável do bucket
$tableInput = $tableInput.Replace('$BUCKET_NAME', $BUCKET_NAME)
$tableInput | Out-File -Encoding utf8 temp_table_incremental.json

aws glue create-table --region $REGION --database-name gdq_test_db `
  --table-input file://temp_table_incremental.json

Remove-Item temp_table_incremental.json
```

### 3.3 Criar tabela full snapshot (partição ≠ coluna de data)

```powershell
$tableInput2 = @"
{
  "Name": "tb_cadastro_full",
  "Description": "Cadastro de clientes - full snapshot por carga",
  "StorageDescriptor": {
    "Columns": [
      {"Name": "ID_CLIENTE", "Type": "string"},
      {"Name": "DT_ABERTURA", "Type": "string"},
      {"Name": "VLR_LIMITE", "Type": "double"},
      {"Name": "VLR_SALDO", "Type": "double"},
      {"Name": "COD_SEGMENTO", "Type": "string"},
      {"Name": "IND_ATIVO", "Type": "int"},
      {"Name": "QTD_PRODUTOS", "Type": "int"}
    ],
    "Location": "s3://$BUCKET_NAME/data/full_snapshot/",
    "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
    "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
    "SerdeInfo": {
      "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }
  },
  "PartitionKeys": [
    {"Name": "dt_carga", "Type": "string"}
  ],
  "TableType": "EXTERNAL_TABLE",
  "Parameters": {
    "classification": "parquet",
    "projection.enabled": "true",
    "projection.dt_carga.type": "date",
    "projection.dt_carga.format": "yyyy-MM-dd",
    "projection.dt_carga.range": "2025-01-01,NOW",
    "projection.dt_carga.interval": "1",
    "projection.dt_carga.interval.unit": "DAYS",
    "storage.location.template": "s3://$BUCKET_NAME/data/full_snapshot/dt_carga=${'$'}{dt_carga}/"
  }
}
"@

$tableInput2 = $tableInput2.Replace('$BUCKET_NAME', $BUCKET_NAME)
$tableInput2 | Out-File -Encoding utf8 temp_table_full.json

aws glue create-table --region $REGION --database-name gdq_test_db `
  --table-input file://temp_table_full.json

Remove-Item temp_table_full.json
```

---

## Passo 4: Criar IAM User com Permissões Mínimas

### 4.1 Policy JSON (somente leitura Athena + S3 + Glue)

```powershell
$policy = @"
{
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
        "athena:GetWorkGroup"
      ],
      "Resource": "*"
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
        "glue:GetPartitions"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3ReadData",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::$BUCKET_NAME",
        "arn:aws:s3:::$BUCKET_NAME/*"
      ]
    },
    {
      "Sid": "S3WriteAthenaResults",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:AbortMultipartUpload"
      ],
      "Resource": [
        "arn:aws:s3:::$BUCKET_NAME/athena-results/*"
      ]
    }
  ]
}
"@

$policy = $policy.Replace('$BUCKET_NAME', $BUCKET_NAME)
$policy | Out-File -Encoding utf8 gdq-readonly-policy.json
```

### 4.2 Criar policy, user, e access key

```powershell
# Criar policy
aws iam create-policy `
  --policy-name GDQReadOnlyPolicy `
  --policy-document file://gdq-readonly-policy.json

# Pegar o ARN da policy criada
$POLICY_ARN = (aws iam list-policies --query "Policies[?PolicyName=='GDQReadOnlyPolicy'].Arn" --output text)

# Criar user
aws iam create-user --user-name gdq-readonly

# Anexar policy
aws iam attach-user-policy `
  --user-name gdq-readonly `
  --policy-arn $POLICY_ARN

# Criar access key
$keys = (aws iam create-access-key --user-name gdq-readonly --output json) | ConvertFrom-Json
$ACCESS_KEY = $keys.AccessKey.AccessKeyId
$SECRET_KEY = $keys.AccessKey.SecretAccessKey

Write-Host "`n========================================="
Write-Host "ACCESS KEY: $ACCESS_KEY"
Write-Host "SECRET KEY: $SECRET_KEY"
Write-Host "========================================="
Write-Host "ANOTE AGORA! O secret key nao aparece novamente."

# Limpar arquivos temp
Remove-Item gdq-readonly-policy.json
```

### 4.3 Configurar profile no AWS CLI

```powershell
aws configure --profile gdq-test
# AWS Access Key ID: [colar ACCESS_KEY]
# AWS Secret Access Key: [colar SECRET_KEY]
# Default region name: us-east-1
# Default output format: json
```

### 4.4 Criar Athena Workgroup (opcional mas recomendado)

```powershell
aws athena create-work-group `
  --name gdq-test `
  --configuration "ResultConfiguration={OutputLocation=s3://$BUCKET_NAME/athena-results/},EnforceWorkGroupConfiguration=true,BytesScannedCutoffPerQuery=100000000" `
  --region $REGION

# O BytesScannedCutoffPerQuery = 100MB limita custo por query
```

---

## Passo 5: Testar

### 5.1 Query de teste no Athena

```powershell
# Testar com o profile readonly
aws athena start-query-execution `
  --query-string "SELECT COUNT(*) FROM gdq_test_db.tb_operacoes_incremental WHERE dt_ref = '2026-02-01'" `
  --work-group gdq-test `
  --profile gdq-test `
  --region $REGION

# Pegar o query execution ID do output e checar resultado
# aws athena get-query-results --query-execution-id <ID> --profile gdq-test
```

### 5.2 Teste rápido via Python

```python
# scripts/test_aws_connection.py
from pyathena import connect

conn = connect(
    region_name="us-east-1",
    work_group="gdq-test",
    s3_staging_dir="s3://SEU-BUCKET/athena-results/",
    profile_name="gdq-test",
)

# Tabela incremental
cursor = conn.cursor()
cursor.execute("""
    SELECT dt_ref, COUNT(*) as row_count
    FROM gdq_test_db.tb_operacoes_incremental
    WHERE dt_ref >= '2026-02-01'
    GROUP BY dt_ref
    ORDER BY dt_ref
    LIMIT 5
""")
print("=== tb_operacoes_incremental ===")
for row in cursor:
    print(row)

# Tabela full snapshot
cursor.execute("""
    SELECT dt_carga, COUNT(*) as row_count, COUNT(DISTINCT ID_CLIENTE) as distinct_clients
    FROM gdq_test_db.tb_cadastro_full
    WHERE dt_carga >= '2026-02-01'
    GROUP BY dt_carga
    ORDER BY dt_carga
    LIMIT 5
""")
print("\n=== tb_cadastro_full ===")
for row in cursor:
    print(row)

print("\n✅ Conexão AWS OK!")
```

### 5.3 .env.dev atualizado

```bash
GDQ_ENV=dev
GDQ_ATHENA_REGION=us-east-1
GDQ_ATHENA_WORKGROUP=gdq-test
GDQ_ATHENA_S3_OUTPUT=s3://SEU-BUCKET/athena-results/
GDQ_AWS_PROFILE=gdq-test
```

---

## Passo 6: Limpeza (quando não precisar mais)

```powershell
# Remover dados do S3
aws s3 rm s3://$BUCKET_NAME --recursive
aws s3 rb s3://$BUCKET_NAME

# Remover tabelas e database
aws glue delete-table --database-name gdq_test_db --name tb_operacoes_incremental
aws glue delete-table --database-name gdq_test_db --name tb_cadastro_full
aws glue delete-database --name gdq_test_db

# Remover workgroup
aws athena delete-work-group --work-group gdq-test --recursive-delete-option

# Remover IAM
aws iam detach-user-policy --user-name gdq-readonly --policy-arn $POLICY_ARN
aws iam delete-access-key --user-name gdq-readonly --access-key-id $ACCESS_KEY
aws iam delete-user --user-name gdq-readonly
aws iam delete-policy --policy-arn $POLICY_ARN
```

---

## Resumo: o que você criou

| Recurso | Nome | Propósito |
|---------|------|-----------|
| S3 Bucket | `gdq-test-data-XXXX` | Dados + resultados Athena |
| Glue Database | `gdq_test_db` | Catálogo |
| Tabela 1 | `tb_operacoes_incremental` | Partição = data, incremental |
| Tabela 2 | `tb_cadastro_full` | Partição ≠ data, full snapshot |
| IAM User | `gdq-readonly` | Acesso mínimo (read only) |
| IAM Policy | `GDQReadOnlyPolicy` | Athena query + S3 read + Glue read |
| Workgroup | `gdq-test` | Limite de 100MB/query |
| AWS CLI Profile | `gdq-test` | Credenciais locais |

### As duas tabelas representam os dois cenários reais

| Aspecto | tb_operacoes_incremental | tb_cadastro_full |
|---------|------------------------|------------------|
| Partição | `dt_ref` (date string) | `dt_carga` (date string) |
| Coluna de data | `dt_ref` (= partição) | `DT_ABERTURA` (coluna interna) |
| Eixo temporal para GDQ | `dt_ref` | `dt_carga` |
| Conteúdo por partição | Dados novos do dia | Foto completa do cadastro |
| Volume por partição | ~5000 rows | ~2000 rows |
| Filtro base | Nenhum | `IND_ATIVO = 1` (opcional) |
