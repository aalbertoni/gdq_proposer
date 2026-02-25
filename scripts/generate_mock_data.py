"""
Gera dados sintéticos para desenvolvimento local.

Tabela 1 — tb_operacoes_credito (incremental):
  - Colunas numéricas: VLR_SALD_AVNC_OPCR, VLR_PARC_OPCR, VLR_CNTR_OPCR, VLR_SALD_DEVE_CTBL
  - Coluna categórica: COD_SITU_OPCR (3 valores: '1', '2', '3')
  - Coluna de data: DT_REF (diária, últimos 60 dias)
  - Coluna de chave: NUM_CTRT_OPCR

Tabela 2 — tb_cadastro_full (full snapshot):
  - Colunas numéricas: VLR_LIMITE, VLR_SALDO, QTD_PRODUTOS
  - Coluna categórica: COD_SEGMENTO, IND_ATIVO
  - Eixo temporal: DT_CARGA (data do snapshot)
  - Coluna de data interna: DT_ABERTURA (fixa por cliente)
  - Coluna de chave: ID_CLIENTE
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta
from pathlib import Path


def generate_operacoes_credito(
    n_days: int = 60,
    rows_per_day: int = 10000,
    seed: int = 42,
    output_dir: str = "mock_data",
) -> pd.DataFrame:
    """Gera dataset sintético de operações de crédito (incremental)."""
    rng = np.random.default_rng(seed)
    Path(output_dir).mkdir(exist_ok=True)

    all_rows = []
    base_date = date.today() - timedelta(days=n_days)

    for day_offset in range(n_days):
        current_date = base_date + timedelta(days=day_offset)
        n_rows = rows_per_day + rng.integers(-500, 500)

        # Drift leve no saldo (cresce ~0.1% por dia)
        drift_factor = 1 + (day_offset * 0.001)

        # Outlier no dia 45 (+35%)
        outlier_factor = 1.35 if day_offset == 45 else 1.0

        # Regime change no dia 50+ (+200 absoluto)
        regime_shift = 200 if day_offset >= 50 else 0

        # === Colunas numéricas ===

        # VLR_SALD_AVNC_OPCR: saldo médio ~5000, std ~1500
        vlr_sald_avnc = rng.normal(
            loc=5000 * drift_factor * outlier_factor + regime_shift,
            scale=1500,
            size=n_rows,
        ).clip(0)

        # VLR_PARC_OPCR: parcela ~500, std ~150
        vlr_parc = rng.normal(
            loc=500 * drift_factor,
            scale=150,
            size=n_rows,
        ).clip(0)

        # VLR_CNTR_OPCR: valor contrato ~20000, std ~8000
        vlr_cntr = rng.normal(
            loc=20000,
            scale=8000,
            size=n_rows,
        ).clip(0)

        # VLR_SALD_DEVE_CTBL: muitos zeros (zero-inflated, 70% zeros)
        vlr_deve = np.where(
            rng.random(n_rows) < 0.7,
            0.0,
            rng.exponential(scale=1000, size=n_rows),
        )

        # === Coluna categórica: COD_SITU_OPCR ===
        # Distribuição base: '1' ~90%, '2' ~7%, '3' ~3%
        # Shift categórico nos dias 30-35: '2' sobe para 12%
        if 30 <= day_offset <= 35:
            cat_probs = [0.85, 0.12, 0.03]
        else:
            cat_probs = [0.90, 0.07, 0.03]

        cod_situ = rng.choice(
            ["1", "2", "3"],
            size=n_rows,
            p=cat_probs,
        )

        # === Chave primária ===
        num_ctrt = [f"CTRT{day_offset:03d}{i:06d}" for i in range(n_rows)]

        # === Montar DataFrame do dia ===
        day_df = pd.DataFrame({
            "DT_REF": current_date.isoformat(),
            "NUM_CTRT_OPCR": num_ctrt,
            "VLR_SALD_AVNC_OPCR": vlr_sald_avnc.round(2),
            "VLR_PARC_OPCR": vlr_parc.round(2),
            "VLR_CNTR_OPCR": vlr_cntr.round(2),
            "VLR_SALD_DEVE_CTBL": vlr_deve.round(2),
            "COD_SITU_OPCR": cod_situ,
        })

        all_rows.append(day_df)

    df = pd.concat(all_rows, ignore_index=True)

    # Introduzir nulls esparsos em VLR_PARC_OPCR (~2%)
    null_mask = rng.random(len(df)) < 0.02
    df.loc[null_mask, "VLR_PARC_OPCR"] = None

    # Salvar como parquet
    output_path = Path(output_dir) / "tb_operacoes_credito.parquet"
    df.to_parquet(output_path, index=False)
    print(f"tb_operacoes_credito: {output_path}")
    print(f"  {len(df)} rows, {n_days} dias")
    print(f"  Colunas: {list(df.columns)}")

    return df


def generate_cadastro_full(
    n_snapshots: int = 45,
    n_records: int = 2000,
    seed: int = 123,
    output_dir: str = "mock_data",
) -> pd.DataFrame:
    """Gera dataset sintético de cadastro de clientes (full snapshot)."""
    rng = np.random.default_rng(seed)
    Path(output_dir).mkdir(exist_ok=True)

    # Base fixa de clientes
    client_ids = [f"CLI{i:06d}" for i in range(n_records)]

    # DT_ABERTURA é fixa por cliente (não muda entre snapshots)
    dt_abertura = [
        (date(2020, 1, 1) + timedelta(days=int(rng.integers(0, 2000)))).isoformat()
        for _ in range(n_records)
    ]

    all_snapshots = []
    base_date = date.today() - timedelta(days=n_snapshots)

    for snap_offset in range(n_snapshots):
        current_date = base_date + timedelta(days=snap_offset)

        # Drift leve em VLR_LIMITE (+0.05%/dia)
        drift = 1 + (snap_offset * 0.0005)

        df = pd.DataFrame({
            "DT_CARGA": current_date.isoformat(),
            "ID_CLIENTE": client_ids,
            "DT_ABERTURA": dt_abertura,
            "VLR_LIMITE": rng.normal(10000 * drift, 3000, n_records).clip(0).round(2),
            "VLR_SALDO": rng.normal(4000, 2000, n_records).clip(0).round(2),
            "COD_SEGMENTO": rng.choice(
                ["VAREJO", "ALTA_RENDA", "PRIVATE", "MICRO"],
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

        # A cada 10 dias, 2 clientes novos aparecem
        if snap_offset % 10 == 0 and snap_offset > 0:
            new_clients = pd.DataFrame({
                "DT_CARGA": [current_date.isoformat()] * 2,
                "ID_CLIENTE": [f"CLINEW{snap_offset:03d}{i}" for i in range(2)],
                "DT_ABERTURA": [current_date.isoformat()] * 2,
                "VLR_LIMITE": [5000.0, 8000.0],
                "VLR_SALDO": [0.0, 0.0],
                "COD_SEGMENTO": ["VAREJO", "ALTA_RENDA"],
                "IND_ATIVO": [1, 1],
                "QTD_PRODUTOS": [1, 2],
            })
            df = pd.concat([df, new_clients], ignore_index=True)

        all_snapshots.append(df)

    full_df = pd.concat(all_snapshots, ignore_index=True)

    # Salvar como parquet
    output_path = Path(output_dir) / "tb_cadastro_full.parquet"
    full_df.to_parquet(output_path, index=False)
    print(f"tb_cadastro_full: {output_path}")
    print(f"  {len(full_df)} rows, {n_snapshots} snapshots")
    print(f"  Colunas: {list(full_df.columns)}")

    return full_df


if __name__ == "__main__":
    print("=== Gerando mock data ===\n")
    generate_operacoes_credito()
    print()
    generate_cadastro_full()
    print("\nDone.")
