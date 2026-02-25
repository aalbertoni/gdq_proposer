"""
Valida que o ambiente esta configurado corretamente.
Roda como primeiro teste apos setup.
"""

import sys
from pathlib import Path

# Garantir que o diretorio raiz do projeto esta no sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def validate():
    errors = []
    warnings = []

    # 1. Python version
    print(f"Python {sys.version}")
    if sys.version_info < (3, 11):
        errors.append("Python >= 3.11 necessario (atual: {})".format(sys.version))

    # 2. Imports essenciais
    try:
        import streamlit
        print("[OK] streamlit {}".format(streamlit.__version__))
    except ImportError:
        errors.append("[FAIL] streamlit nao instalado")

    try:
        import plotly
        print("[OK] plotly {}".format(plotly.__version__))
    except ImportError:
        errors.append("[FAIL] plotly nao instalado")

    try:
        import duckdb
        print("[OK] duckdb {}".format(duckdb.__version__))
    except ImportError:
        errors.append("[FAIL] duckdb nao instalado")

    try:
        import pandas
        print("[OK] pandas {}".format(pandas.__version__))
    except ImportError:
        errors.append("[FAIL] pandas nao instalado")

    try:
        import numpy
        print("[OK] numpy {}".format(numpy.__version__))
    except ImportError:
        errors.append("[FAIL] numpy nao instalado")

    try:
        import jinja2
        print("[OK] jinja2 {}".format(jinja2.__version__))
    except ImportError:
        errors.append("[FAIL] jinja2 nao instalado")

    try:
        import pyarrow
        print("[OK] pyarrow {}".format(pyarrow.__version__))
    except ImportError:
        errors.append("[FAIL] pyarrow nao instalado")

    try:
        import pyathena
        print("[OK] pyathena {}".format(pyathena.__version__))
    except ImportError:
        warnings.append("[WARN] pyathena nao instalado (necessario apenas para Athena real)")

    try:
        import pytest
        print("[OK] pytest {}".format(pytest.__version__))
    except ImportError:
        errors.append("[FAIL] pytest nao instalado")

    # 3. Config
    try:
        from config import load_config
        config = load_config()
        print("[OK] Config carregada: env={}, mode={}".format(
            config.environment.value, config.athena.mode.value,
        ))
    except Exception as e:
        errors.append("[FAIL] Erro ao carregar config: {}".format(e))

    # 4. Mock data
    from pathlib import Path
    mock_dir = Path("mock_data")
    if mock_dir.exists():
        files = list(mock_dir.glob("*.parquet")) + list(mock_dir.glob("*.csv"))
        if files:
            print("[OK] Mock data: {} arquivo(s) em {}".format(len(files), mock_dir))
        else:
            warnings.append(
                "[WARN] Diretorio {} existe mas sem dados. "
                "Rode: python scripts/generate_mock_data.py".format(mock_dir)
            )
    else:
        warnings.append(
            "[WARN] Diretorio {} nao existe. "
            "Rode: python scripts/generate_mock_data.py".format(mock_dir)
        )

    # 5. DuckDB query test
    try:
        import duckdb
        conn = duckdb.connect(":memory:")
        result = conn.execute("SELECT 1 + 1 as test").fetchone()
        assert result[0] == 2
        print("[OK] DuckDB query engine OK")
        conn.close()
    except Exception as e:
        errors.append("[FAIL] DuckDB query test falhou: {}".format(e))

    # 6. Mock Athena integration test
    if mock_dir.exists() and list(mock_dir.glob("*.parquet")):
        try:
            from config import load_config
            from infra.athena_client import AthenaClient
            config = load_config()
            client = AthenaClient(config)
            result = client.execute(
                "SELECT COUNT(*) as cnt FROM tb_operacoes_credito"
            )
            count = result[0]["cnt"]
            print("[OK] Mock Athena query OK ({} rows)".format(count))
        except Exception as e:
            errors.append("[FAIL] Mock Athena query falhou: {}".format(e))

    # Resultado
    print("\n" + "=" * 50)
    if errors:
        print("SETUP INCOMPLETO:")
        for e in errors:
            print("   {}".format(e))
    else:
        print("SETUP OK -- pronto para desenvolver!")

    if warnings:
        print("\nAvisos:")
        for w in warnings:
            print("   {}".format(w))

    return len(errors) == 0


if __name__ == "__main__":
    success = validate()
    sys.exit(0 if success else 1)
