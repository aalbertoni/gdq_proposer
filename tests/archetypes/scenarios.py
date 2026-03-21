"""Cenarios adversos concretos (starter pack).

Cada funcao arch_*() retorna um Archetype pronto para teste.
Para adicionar novo cenario: criar funcao e incluir em ALL_ARCHETYPES.
"""

import random

import pandas as pd

from core.models.dataset_config import DatasetConfig
from core.models.enums import GrainType, PartitionMethod, SemanticType
from tests.archetypes import AdversarialBehavior, Archetype
from tests.archetypes.helpers import make_date_range, make_int_dates, repeat_for_rows


# ---------------------------------------------------------------------------
# 1. partition_int_yyyymmdd — partição inteira formato YYYYMMDD
# ---------------------------------------------------------------------------

def arch_partition_int_yyyymmdd() -> Archetype:
    """Tabela com particao inteira no formato 20260101.

    Cenario real comum em ambientes corporativos onde a particao
    S3 e armazenada como bigint. O sistema deve gerar predicado
    de pruning sem aspas: "dt_ref" >= 20260101.
    """
    n_periods = 30
    rows_per_period = 100
    dates_int = make_int_dates(n_periods)
    dates_str = make_date_range(n_periods)

    rng = random.Random(42)
    df = pd.DataFrame({
        "dt_ref": repeat_for_rows(dates_int, rows_per_period),
        "dt_ref_str": repeat_for_rows(dates_str, rows_per_period),
        "VLR_SALDO": [100.0 + rng.gauss(0, 5) for _ in range(n_periods * rows_per_period)],
        "COD_PRODUTO": [rng.choice(["A", "B", "C"]) for _ in range(n_periods * rows_per_period)],
    })

    config = DatasetConfig(
        schema="test_db",
        table="tb_partition_int",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        partition_format="%Y%m%d",
        partition_is_integer=True,
        grain_type=GrainType.DAILY,
        lookback_value=30,
        reference_date="2026-01-30",
        # Para profiling: usar a coluna string como eixo temporal,
        # pois DuckDB precisa de date-like para date arithmetic
        temporal_axis_column="dt_ref_str",
        date_expression=None,
        selected_columns=["VLR_SALDO", "COD_PRODUTO"],
    )

    return Archetype(
        name="partition_int_yyyymmdd",
        description="Particao inteira YYYYMMDD — pruning deve gerar literal sem aspas",
        category="partitioning",
        behavior=AdversarialBehavior.SUPPORTED,
        df=df,
        config=config,
        expected_types={
            "VLR_SALDO": SemanticType.NUMERIC,
            "COD_PRODUTO": SemanticType.CATEGORICAL_LOW_CARDINALITY,
        },
        notes=(
            "Valida que partition_is_integer=True gera predicado correto. "
            "Em producao, o Athena aceita comparacao int >= 20260101 sem aspas."
        ),
    )


# ---------------------------------------------------------------------------
# 2. schema_all_varchar — todas as colunas sao varchar
# ---------------------------------------------------------------------------

def arch_schema_all_varchar() -> Archetype:
    """Tabela legacy onde todas as colunas sao varchar.

    Cenario real: migracoes de mainframe/CSV onde tudo vira string.
    A classificacao depende 100% da Camada 2 (cast) e Camada 3 (cardinalidade).
    Risco: colunas numericas nao castadas viram CATEGORICAL_HIGH.
    """
    n_periods = 30
    rows_per_period = 200
    dates = make_date_range(n_periods)

    rng = random.Random(42)
    n_rows = n_periods * rows_per_period

    df = pd.DataFrame({
        "dt_ref": repeat_for_rows(dates, rows_per_period),
        # Numerica como string — 100% castavel
        "VLR_SALDO": [f"{100.0 + rng.gauss(0, 5):.2f}" for _ in range(n_rows)],
        # Codigo — 3 valores, castavel
        "COD_TIPO": [rng.choice(["1", "2", "3"]) for _ in range(n_rows)],
        # Categoria textual — nao castavel
        "UF": [rng.choice(["SP", "RJ", "MG", "RS", "BA"]) for _ in range(n_rows)],
        # Alta cardinalidade textual
        "NOME_CLIENTE": [f"Cliente {i}" for i in range(n_rows)],
    })

    config = DatasetConfig(
        schema="test_db",
        table="tb_all_varchar",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        partition_format="%Y-%m-%d",  # dt_ref e string, nao date nativa
        grain_type=GrainType.DAILY,
        lookback_value=30,
        reference_date="2026-01-30",
        selected_columns=["VLR_SALDO", "COD_TIPO", "UF", "NOME_CLIENTE"],
    )

    return Archetype(
        name="schema_all_varchar",
        description="Tabela 100% varchar — classificacao depende de cast + cardinalidade",
        category="schema",
        behavior=AdversarialBehavior.WARNING,
        df=df,
        config=config,
        expected_types={
            "VLR_SALDO": SemanticType.NUMERIC,          # cast ratio >= 0.95, mid cardinality
            "COD_TIPO": SemanticType.CATEGORICAL_LOW_CARDINALITY,  # cast >= 0.95, <= 20 distinct
            "UF": SemanticType.CATEGORICAL_LOW_CARDINALITY,        # 5 distinct, < 0.005 ratio
            "NOME_CLIENTE": SemanticType.CATEGORICAL_HIGH_CARDINALITY,  # alta cardinalidade
        },
        notes=(
            "Valida que Camada 2 (cast heuristic) funciona para tabelas all-varchar. "
            "COD_TIPO (castavel, 3 distinct) deve virar CATEGORICAL_LOW via threshold <= 20. "
            "VLR_SALDO (castavel, alta cardinality) deve virar NUMERIC."
        ),
    )


# ---------------------------------------------------------------------------
# 3. quality_all_nulls — colunas 100% NULL
# ---------------------------------------------------------------------------

def arch_quality_all_nulls() -> Archetype:
    """Tabela com colunas de dados 100% NULL.

    Cenario real: tabela criada mas nunca populada, ou colunas
    deprecated que ficaram no schema. O profiling deve retornar
    UNKNOWN e nao tentar gerar regras.
    """
    n_periods = 15
    rows_per_period = 50
    dates = make_date_range(n_periods)
    n_rows = n_periods * rows_per_period

    df = pd.DataFrame({
        "dt_ref": repeat_for_rows(dates, rows_per_period),
        # Usar pandas nullable types para que DuckDB infira VARCHAR/DOUBLE
        "VLR_SALDO": pd.array([None] * n_rows, dtype="Float64"),
        "COD_TIPO": pd.array([None] * n_rows, dtype="string"),
        "QTD_PARCELAS": pd.array([None] * n_rows, dtype="Int64"),
    })

    config = DatasetConfig(
        schema="test_db",
        table="tb_all_nulls",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        partition_format="%Y-%m-%d",  # dt_ref e string
        grain_type=GrainType.DAILY,
        lookback_value=30,
        reference_date="2026-01-15",
        selected_columns=["VLR_SALDO", "COD_TIPO", "QTD_PARCELAS"],
    )

    return Archetype(
        name="quality_all_nulls",
        description="Colunas 100% NULL — profiling deve retornar UNKNOWN",
        category="quality",
        behavior=AdversarialBehavior.WARNING,
        df=df,
        config=config,
        expected_types={},  # all UNKNOWN — validated per-column in test
        expected_profiling_succeeds=True,  # should not crash
        expected_warnings_contain=["null"],
        notes=(
            "Cenario critico: colunas 100% NULL nao devem gerar regras. "
            "classify_column com non_null_count=0 retorna UNKNOWN. "
            "O profiling deve completar sem crash e emitir warnings."
        ),
    )


# ---------------------------------------------------------------------------
# 4. quality_leading_zeros — codigos com zeros a esquerda
# ---------------------------------------------------------------------------

def arch_quality_leading_zeros() -> Archetype:
    """Colunas com codigos que tem leading zeros (ex: "001", "002").

    Cenario real: codigos de agencia, produto, ou status que sao
    armazenados como varchar com padding. TRY_CAST("001" AS DOUBLE)
    retorna 1.0 — o sistema classifica como NUMERIC, mas sao codigos.

    Esta e uma limitacao conhecida do classificador: sem analise de
    padrao textual, codigos castaveis sao indistinguiveis de numeros.
    """
    n_periods = 30
    rows_per_period = 200
    dates = make_date_range(n_periods)
    n_rows = n_periods * rows_per_period

    rng = random.Random(42)

    # Codigos com leading zeros — 100% castaveis para numero
    codigos_agencia = [f"{i:04d}" for i in range(1, 51)]     # "0001" a "0050"
    codigos_produto = [f"{i:03d}" for i in range(1, 4)]       # "001", "002", "003"

    df = pd.DataFrame({
        "dt_ref": repeat_for_rows(dates, rows_per_period),
        "COD_AGENCIA": [rng.choice(codigos_agencia) for _ in range(n_rows)],
        "COD_PRODUTO": [rng.choice(codigos_produto) for _ in range(n_rows)],
        "VLR_REAL": [f"{rng.uniform(100, 500):.2f}" for _ in range(n_rows)],
    })

    config = DatasetConfig(
        schema="test_db",
        table="tb_leading_zeros",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        partition_format="%Y-%m-%d",  # dt_ref e string
        grain_type=GrainType.DAILY,
        lookback_value=30,
        reference_date="2026-01-30",
        selected_columns=["COD_AGENCIA", "COD_PRODUTO", "VLR_REAL"],
    )

    return Archetype(
        name="quality_leading_zeros",
        description="Codigos com leading zeros castados como NUMERIC — limitacao conhecida",
        category="quality",
        behavior=AdversarialBehavior.KNOWN_LIMITATION,
        df=df,
        config=config,
        expected_types={
            # COD_AGENCIA: 50 distinct, 100% castavel → NUMERIC (errado, deveria ser codigo)
            # Mas pelo classificador atual: cast >= 95%, distinct entre 21-9999 → NUMERIC
            "COD_AGENCIA": SemanticType.NUMERIC,
            # COD_PRODUTO: 3 distinct, 100% castavel → CATEGORICAL_LOW (correto!)
            # cast >= 95%, distinct <= 20 → CATEGORICAL_LOW
            "COD_PRODUTO": SemanticType.CATEGORICAL_LOW_CARDINALITY,
            # VLR_REAL: alta cardinalidade, 100% castavel → NUMERIC (correto)
            "VLR_REAL": SemanticType.NUMERIC,
        },
        notes=(
            "KNOWN_LIMITATION: COD_AGENCIA com 50 distinct e 100% cast ratio "
            "e classificado como NUMERIC pelo classificador atual. "
            "Sem analise de padrao textual (leading zeros, comprimento fixo), "
            "nao ha como distinguir de um numero real. "
            "COD_PRODUTO (3 distinct) escapa via guardrail <= 20."
        ),
    )


# ---------------------------------------------------------------------------
# 5. volume_defasagem_90d — ultima particao ha 90 dias
# ---------------------------------------------------------------------------

def arch_volume_defasagem_90d() -> Archetype:
    """Tabela cuja ultima particao e de 90 dias atras.

    Cenario real: tabela com carga descontinuada, mas ainda no catalogo.
    Se reference_date=None, lookback usa today() e a janela pega dados
    muito antigos. Se reference_date e setado corretamente para max_date,
    funciona. O risco e quando o usuario nao seta reference_date.

    Aqui testamos COM reference_date setado (comportamento correto).
    O cenario SEM reference_date e uma limitacao de UX, nao de backend.
    """
    n_periods = 30
    rows_per_period = 100
    # Dados de 90 dias atras
    dates = make_date_range(n_periods, start="2025-10-01")
    n_rows = n_periods * rows_per_period

    rng = random.Random(42)

    df = pd.DataFrame({
        "dt_ref": repeat_for_rows(dates, rows_per_period),
        "VLR_SALDO": [100.0 + rng.gauss(0, 5) for _ in range(n_rows)],
        "COD_TIPO": [rng.choice(["A", "B"]) for _ in range(n_rows)],
    })

    config = DatasetConfig(
        schema="test_db",
        table="tb_defasagem",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        partition_format="%Y-%m-%d",  # dt_ref e string
        grain_type=GrainType.DAILY,
        lookback_value=30,
        # reference_date setado para max_date dos dados
        reference_date="2025-10-30",
        selected_columns=["VLR_SALDO", "COD_TIPO"],
    )

    return Archetype(
        name="volume_defasagem_90d",
        description="Dados de 90 dias atras — reference_date deve apontar para max_date",
        category="volume",
        behavior=AdversarialBehavior.WARNING,
        df=df,
        config=config,
        expected_types={
            "VLR_SALDO": SemanticType.NUMERIC,
            "COD_TIPO": SemanticType.CATEGORICAL_LOW_CARDINALITY,
        },
        notes=(
            "WARNING: se reference_date nao for setado, lookback usa today() "
            "e a janela cai no vazio (dados de out/2025, lookback de jan/2026). "
            "O teste valida que COM reference_date correto, tudo funciona. "
            "A limitacao de UX (nao avisar o usuario) e separada."
        ),
    )


# ---------------------------------------------------------------------------
# 6. quality_single_value_column — coluna numerica com valor unico
# ---------------------------------------------------------------------------

def arch_quality_single_value_column() -> Archetype:
    """Coluna numerica onde todos os valores sao iguais (ex: taxa fixa).

    Cenario real: coluna de taxa de juros fixa (0.05), flag binario
    que nunca varia, ou coluna default. stddev=0, banda sigma tem
    largura zero. O dual guard salva via margem (+-10%), mas:
    - band_width_ratio = 0.0 (potencialmente enganoso na UI)
    - stability_score = 1.0 (falsa confianca)
    - qualquer variacao futura viola a sigma band

    O backtest passa 100% mas o resultado mascara fragilidade.
    """
    n_periods = 30
    rows_per_period = 100
    dates = make_date_range(n_periods)
    n_rows = n_periods * rows_per_period

    rng = random.Random(42)

    df = pd.DataFrame({
        "dt_ref": repeat_for_rows(dates, rows_per_period),
        # Coluna constante — mesma taxa em todos os periodos
        "TAXA_JUROS": [0.05] * n_rows,
        # Coluna com variacao normal para contraste
        "VLR_SALDO": [100.0 + rng.gauss(0, 5) for _ in range(n_rows)],
        # Categorica normal
        "COD_TIPO": [rng.choice(["A", "B"]) for _ in range(n_rows)],
    })

    config = DatasetConfig(
        schema="test_db",
        table="tb_single_value",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        partition_format="%Y-%m-%d",
        grain_type=GrainType.DAILY,
        lookback_value=30,
        reference_date="2026-01-30",
        selected_columns=["TAXA_JUROS", "VLR_SALDO", "COD_TIPO"],
    )

    return Archetype(
        name="quality_single_value_column",
        description="Coluna constante (stddev=0) — banda degenerada, dual guard salva via margem",
        category="quality",
        behavior=AdversarialBehavior.WARNING,
        df=df,
        config=config,
        expected_types={
            # TAXA_JUROS: double com 1 distinct → guardrail reclassifica para
            # CATEGORICAL_LOW (distinct <= 20). Comportamento correto do guardrail,
            # mas surpreendente: coluna genuinamente numerica (taxa fixa) vira
            # categorica por ter cardinalidade baixa.
            "TAXA_JUROS": SemanticType.CATEGORICAL_LOW_CARDINALITY,
            "VLR_SALDO": SemanticType.NUMERIC,
            "COD_TIPO": SemanticType.CATEGORICAL_LOW_CARDINALITY,
        },
        notes=(
            "WARNING: coluna constante gera sigma band com width=0. "
            "O dual guard (OR margem +-10%) evita FP, mas band_width_ratio=0 "
            "e stability_score=1.0 mascaram fragilidade. Qualquer variacao "
            "futura viola a sigma band imediatamente."
        ),
    )


# ---------------------------------------------------------------------------
# 7. combo_codes_as_integers — int com poucos valores distintos
# ---------------------------------------------------------------------------

def arch_combo_codes_as_integers() -> Archetype:
    """Coluna int/bigint com poucos valores distintos (ex: COD_STATUS).

    Cenario real: colunas de codigo/flag que sao armazenadas como
    inteiro por conveniencia, mas semanticamente sao categoricas.
    O guardrail suggest_reclassification deve reclassificar para
    CATEGORICAL_LOW quando distinct <= 20.

    Testa o pipeline completo: DuckDB reporta tipo INTEGER,
    ProfilingService executa cardinalidade, suggest_reclassification
    propoe reclassificacao, profiling aplica automaticamente.
    """
    n_periods = 30
    rows_per_period = 200
    dates = make_date_range(n_periods)
    n_rows = n_periods * rows_per_period

    rng = random.Random(42)

    df = pd.DataFrame({
        "dt_ref": repeat_for_rows(dates, rows_per_period),
        # Int com 5 valores — deve ser reclassificado para CATEGORICAL_LOW
        "COD_STATUS": [rng.choice([1, 2, 3, 4, 5]) for _ in range(n_rows)],
        # Int com 3 valores — idem
        "IND_ATIVO": [rng.choice([0, 1, 2]) for _ in range(n_rows)],
        # Double com alta cardinalidade — deve permanecer NUMERIC
        "VLR_SALDO": [100.0 + rng.gauss(0, 10) for _ in range(n_rows)],
        # Bigint com alta cardinalidade e alta unicidade — IDENTIFIER
        "NUM_CONTRATO": list(range(n_rows)),
    })

    config = DatasetConfig(
        schema="test_db",
        table="tb_codes_int",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        partition_format="%Y-%m-%d",
        grain_type=GrainType.DAILY,
        lookback_value=30,
        reference_date="2026-01-30",
        selected_columns=["COD_STATUS", "IND_ATIVO", "VLR_SALDO", "NUM_CONTRATO"],
    )

    return Archetype(
        name="combo_codes_as_integers",
        description="Int com poucos distintos — guardrail deve reclassificar para CATEGORICAL_LOW",
        category="combo",
        behavior=AdversarialBehavior.SUPPORTED,
        df=df,
        config=config,
        expected_types={
            # Guardrail: int com <= 20 distinct → reclassificado para CATEGORICAL_LOW
            "COD_STATUS": SemanticType.CATEGORICAL_LOW_CARDINALITY,
            "IND_ATIVO": SemanticType.CATEGORICAL_LOW_CARDINALITY,
            # Double com alta cardinality → permanece NUMERIC
            "VLR_SALDO": SemanticType.NUMERIC,
            # Bigint sequencial: 6000 valores totais, mas profiling amostra
            # apenas 10 periodos (sample_periods default) = ~2000 distinct.
            # Guardrail IDENTIFIER exige >= 10000 distinct → fica NUMERIC.
            # Em producao com mais dados, seria IDENTIFIER.
            "NUM_CONTRATO": SemanticType.NUMERIC,
        },
        notes=(
            "Valida o pipeline completo de reclassificacao: "
            "DuckDB reporta tipo INTEGER/BIGINT, classify_column retorna NUMERIC, "
            "suggest_reclassification detecta baixa cardinalidade e sugere "
            "CATEGORICAL_LOW, ProfilingService aplica a sugestao automaticamente. "
            "NUM_CONTRATO fica NUMERIC (nao IDENTIFIER) porque amostra de 10 periodos "
            "tem ~2000 distinct, abaixo do threshold 10000."
        ),
    )


# ---------------------------------------------------------------------------
# 8. volume_tiny_5_periods — tabela com apenas 5 periodos
# ---------------------------------------------------------------------------

def arch_volume_tiny_5_periods() -> Archetype:
    """Tabela com apenas 5 periodos de dados.

    Cenario real: tabela nova, recem-criada, com poucas cargas.
    O profiling funciona (classifica colunas), mas o backtest
    nao tem pontos suficientes (min_history=7 por default).

    backtest_band retorna total_periods=0, coverage_pct=0.0.
    Regras sao propostas sem evidencia de backtest — confianca LOW.
    """
    n_periods = 5
    rows_per_period = 100
    dates = make_date_range(n_periods)
    n_rows = n_periods * rows_per_period

    rng = random.Random(42)

    df = pd.DataFrame({
        "dt_ref": repeat_for_rows(dates, rows_per_period),
        "VLR_SALDO": [100.0 + rng.gauss(0, 5) for _ in range(n_rows)],
        "COD_TIPO": [rng.choice(["A", "B", "C"]) for _ in range(n_rows)],
    })

    config = DatasetConfig(
        schema="test_db",
        table="tb_tiny",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        partition_format="%Y-%m-%d",
        grain_type=GrainType.DAILY,
        lookback_value=30,
        reference_date="2026-01-05",
        selected_columns=["VLR_SALDO", "COD_TIPO"],
    )

    return Archetype(
        name="volume_tiny_5_periods",
        description="Apenas 5 periodos — backtest impossivel com min_history=7",
        category="volume",
        behavior=AdversarialBehavior.WARNING,
        df=df,
        config=config,
        expected_types={
            "VLR_SALDO": SemanticType.NUMERIC,
            # COD_TIPO: 3 distinct / 500 rows = ratio 0.006.
            # Threshold LOW_CARDINALITY_MAX_RATIO = 0.005, ratio > threshold
            # → CATEGORICAL_MID (nao LOW). Volume pequeno eleva o ratio.
            "COD_TIPO": SemanticType.CATEGORICAL_MID_CARDINALITY,
        },
        notes=(
            "WARNING: profiling funciona mas backtest retorna total_periods=0. "
            "Regras propostas sem evidencia de backtest recebem confianca LOW. "
            "O sistema nao impede a proposta — o usuario decide se aceita. "
            "COD_TIPO com 3 distinct vira CATEGORICAL_MID (nao LOW) porque "
            "ratio 0.006 > threshold 0.005 — efeito de amostra pequena."
        ),
    )


# ---------------------------------------------------------------------------
# 9. partition_string_yyyymm — particao mensal como string
# ---------------------------------------------------------------------------

def arch_partition_string_yyyymm() -> Archetype:
    """Tabela com particao mensal no formato '202601'.

    Cenario real: tabelas com carga mensal onde a particao e
    o mes no formato YYYYMM. Pruning deve gerar comparacao
    de string: "dt_ref" >= '202512'.

    Requer grain_type=MONTHLY para que o lookback e a analise
    funcionem corretamente (periodos = meses, nao dias).
    """
    n_periods = 12
    rows_per_period = 500
    # 12 meses de dados
    months = pd.date_range("2025-01-01", periods=n_periods, freq="MS")
    month_strs = [d.strftime("%Y%m") for d in months]
    # Datas reais (1o dia de cada mes) para uso como eixo temporal
    # DuckDB precisa de date-like strings para date arithmetic no profiling
    month_dates = [d.strftime("%Y-%m-%d") for d in months]

    rng = random.Random(42)
    n_rows = n_periods * rows_per_period

    df = pd.DataFrame({
        "dt_ref": repeat_for_rows(month_strs, rows_per_period),
        "dt_ref_date": repeat_for_rows(month_dates, rows_per_period),
        "VLR_SALDO": [100.0 + rng.gauss(0, 8) for _ in range(n_rows)],
        "COD_PRODUTO": [rng.choice(["A", "B", "C", "D"]) for _ in range(n_rows)],
    })

    config = DatasetConfig(
        schema="test_db",
        table="tb_monthly",
        partition_method=PartitionMethod.INCREMENTAL,
        partition_column="dt_ref",
        date_column="dt_ref",
        partition_format="%Y%m",
        grain_type=GrainType.MONTHLY,
        lookback_value=400,  # dias (nao meses) — 400 dias cobre 12+ meses
        reference_date="2025-12-15",
        # temporal_axis_column com datas reais para date arithmetic no DuckDB
        temporal_axis_column="dt_ref_date",
        selected_columns=["VLR_SALDO", "COD_PRODUTO"],
    )

    return Archetype(
        name="partition_string_yyyymm",
        description="Particao mensal YYYYMM — pruning com formato truncado",
        category="partitioning",
        behavior=AdversarialBehavior.SUPPORTED,
        df=df,
        config=config,
        expected_types={
            "VLR_SALDO": SemanticType.NUMERIC,
            "COD_PRODUTO": SemanticType.CATEGORICAL_LOW_CARDINALITY,
        },
        # Profiling usa date_lookback de sample_periods DIAS.
        # Com dados mensais, default=10 dias so captura 1 mes.
        # 400 dias cobre os 12 meses de dados.
        sample_periods=400,
        notes=(
            "Valida que partition_format='%Y%m' gera pruning correto "
            "e grain_type=MONTHLY com 12 periodos funciona. "
            "Pruning: \"dt_ref\" >= '202501' (string comparison). "
            "Requer temporal_axis_column com datas reais (dt_ref_date) porque "
            "DuckDB nao consegue fazer date arithmetic com strings YYYYMM. "
            "lookback_value=400 (dias) para cobrir 12+ meses."
        ),
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_ARCHETYPES: list[Archetype] = [
    arch_partition_int_yyyymmdd(),
    arch_schema_all_varchar(),
    arch_quality_all_nulls(),
    arch_quality_leading_zeros(),
    arch_volume_defasagem_90d(),
    arch_quality_single_value_column(),
    arch_combo_codes_as_integers(),
    arch_volume_tiny_5_periods(),
    arch_partition_string_yyyymm(),
]

ARCHETYPES_BY_NAME: dict[str, Archetype] = {a.name: a for a in ALL_ARCHETYPES}
