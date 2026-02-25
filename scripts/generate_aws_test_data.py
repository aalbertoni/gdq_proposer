"""
Gera dados fake e faz upload para S3 em formato particionado.

Cria 2 tabelas:
  1. tb_operacoes_incremental -- particao = coluna de data (incremental)
     aws_test_data/data/incremental/dt_ref=YYYY-MM-DD/data.parquet
     45 dias, ~5000 rows/dia

  2. tb_cadastro_full -- particao = data de carga, coluna de data e interna
     aws_test_data/data/full_snapshot/dt_carga=YYYY-MM-DD/data.parquet
     45 dias, ~2000 rows/snapshot

Uso:
  python scripts/generate_aws_test_data.py --bucket meu-bucket
  python scripts/generate_aws_test_data.py --bucket meu-bucket --upload

Conforme docs/aws_test_setup.md secao 2.1.
"""

import sys
from pathlib import Path

# Garantir que o diretorio raiz do projeto esta no sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import subprocess
from datetime import date, timedelta

import numpy as np
import pandas as pd


def generate_incremental_table(
    output_dir: str,
    n_days: int = 45,
    rows_per_day: int = 5000,
    seed: int = 42,
) -> None:
    """Tabela incremental: particao por dt_ref, dados novos a cada dia.

    Cenario: operacoes de credito diarias.
    Particao = coluna de data = dt_ref
    Cada particao tem APENAS os dados daquele dia.
    """
    rng = np.random.default_rng(seed)
    base_date = date.today() - timedelta(days=n_days)
    base_dir = Path(output_dir) / "data" / "incremental"
    base_dir.mkdir(parents=True, exist_ok=True)

    total_rows = 0

    for day_offset in range(n_days):
        current_date = base_date + timedelta(days=day_offset)
        dt_str = current_date.isoformat()
        n_rows = rows_per_day + int(rng.integers(-300, 300))

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
        total_rows += n_rows

    print(f"[OK] Incremental: {n_days} particoes, ~{total_rows} rows em {base_dir}")


def generate_full_snapshot_table(
    output_dir: str,
    n_snapshots: int = 45,
    n_records: int = 2000,
    seed: int = 123,
) -> None:
    """Tabela full snapshot: particao por dt_carga, coluna de data e DT_ABERTURA.

    Cenario: cadastro de clientes, foto completa a cada dia.
    Particao = dt_carga (data do processamento/carga)
    Coluna de data para analise = DT_ABERTURA (data de abertura da conta)
    Cada particao tem a foto COMPLETA do cadastro.
    """
    rng = np.random.default_rng(seed)
    base_date = date.today() - timedelta(days=n_snapshots)
    base_dir = Path(output_dir) / "data" / "full_snapshot"
    base_dir.mkdir(parents=True, exist_ok=True)

    # Base fixa de clientes
    client_ids = [f"CLI{i:06d}" for i in range(n_records)]

    # DT_ABERTURA e fixa por cliente (nao muda entre snapshots)
    dt_abertura = [
        (date(2020, 1, 1) + timedelta(days=int(rng.integers(0, 2000)))).isoformat()
        for _ in range(n_records)
    ]

    total_rows = 0

    for snap_offset in range(n_snapshots):
        current_date = base_date + timedelta(days=snap_offset)
        dt_str = current_date.isoformat()

        # Alguns campos mudam entre snapshots (simula atualizacao)
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
        total_rows += len(df)

    print(f"[OK] Full snapshot: {n_snapshots} particoes, ~{total_rows} rows em {base_dir}")


def upload_to_s3(local_dir: str, bucket: str) -> None:
    """Upload recursivo para S3."""
    data_dir = str(Path(local_dir) / "data")
    s3_target = f"s3://{bucket}/data/"
    print(f"\nUploading {data_dir} -> {s3_target}")
    result = subprocess.run(
        ["aws", "s3", "sync", data_dir, s3_target,
         "--exclude", "*.csv", "--exclude", "*.py", "--exclude", ".gitkeep"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[FAIL] Upload falhou: {result.stderr}")
        sys.exit(1)
    print("[OK] Upload concluido")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Gera dados fake particionados para teste com Athena."
    )
    parser.add_argument("--bucket", required=True, help="Nome do bucket S3")
    parser.add_argument("--local-dir", default="aws_test_data", help="Dir local (default: aws_test_data)")
    parser.add_argument("--upload", action="store_true", help="Fazer upload para S3 apos gerar")
    args = parser.parse_args()

    print("Gerando dados fake particionados...\n")
    generate_incremental_table(args.local_dir)
    generate_full_snapshot_table(args.local_dir)

    if args.upload:
        upload_to_s3(args.local_dir, args.bucket)
    else:
        print(f"\nDados gerados em: {args.local_dir}/")
        print(f"Para upload: python {sys.argv[0]} --bucket {args.bucket} --upload")
