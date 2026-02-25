"""
Pagina 01 — Setup Wizard.

Wizard com validacao progressiva para configurar a tabela alvo:
1. Selecionar schema/tabela e validar existencia
2. Configurar eixo temporal (coluna de data, grain, partition method)
3. Filtro base opcional
4. Profiling de colunas (classificacao semantica)
5. Override manual de tipos + selecao de colunas
6. Salvar preset

Definido conforme docs/technical_spec_v1.md secao 12 (Sprint A1).
"""

import json
from pathlib import Path

import streamlit as st

from config import load_config, AthenaMode
from core.models.dataset_config import DatasetConfig
from core.models.enums import (
    GrainType,
    LookbackMode,
    PartitionMethod,
    SemanticType,
)
from infra.athena_client import AthenaClient
from infra.query_builder import QueryBuilder
from services.dataset_service import DatasetService
from services.profiling_service import ProfilingService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_client() -> AthenaClient:
    """Get or create a cached AthenaClient in session_state."""
    if "client" not in st.session_state:
        config = load_config()
        st.session_state["config"] = config
        st.session_state["client"] = AthenaClient(config)
    return st.session_state["client"]


def get_services(client: AthenaClient):
    """Get or create cached services."""
    if "dataset_service" not in st.session_state:
        builder = QueryBuilder(dialect=client.dialect)
        st.session_state["dataset_service"] = DatasetService(client, builder)
        st.session_state["profiling_service"] = ProfilingService(client, builder)
    return (
        st.session_state["dataset_service"],
        st.session_state["profiling_service"],
    )


def _semantic_type_label(st_type: SemanticType) -> str:
    """Label legivel para tipo semantico."""
    labels = {
        SemanticType.NUMERIC: "Numerico",
        SemanticType.CATEGORICAL_LOW_CARDINALITY: "Categorico (low)",
        SemanticType.CATEGORICAL_MID_CARDINALITY: "Categorico (mid)",
        SemanticType.CATEGORICAL_HIGH_CARDINALITY: "Categorico (high)",
        SemanticType.DATETIME: "Data/hora",
        SemanticType.IDENTIFIER: "Identificador",
        SemanticType.FREE_TEXT: "Texto livre",
        SemanticType.UNKNOWN: "Desconhecido",
    }
    return labels.get(st_type, st_type.value)


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Setup - GDQ Rule Proposer", page_icon=":gear:")

st.title("Setup da Tabela")
st.caption("Configure a tabela alvo, eixo temporal e colunas para analise.")

try:
    client = get_client()
except Exception as e:
    st.error(f"Falha na conexao: {e}")
    st.stop()

app_config = st.session_state["config"]
is_mock = app_config.athena.mode == AthenaMode.MOCK
dataset_svc, profiling_svc = get_services(client)


# ===================================================================
# STEP 1: Selecionar e validar tabela
# ===================================================================

st.header("1. Selecionar Tabela")

col1, col2 = st.columns(2)
with col1:
    if is_mock:
        schema = st.text_input("Schema:", value="mock_db", disabled=True)
    else:
        schema = st.text_input("Schema (Glue database):", value="gdq_test_db")

with col2:
    table = st.text_input("Tabela:", placeholder="ex: tb_operacoes_credito")

if st.button("Validar Tabela", disabled=not table, type="primary"):
    with st.spinner("Verificando tabela..."):
        try:
            exists = dataset_svc.validate_table(schema, table)
        except ValueError as e:
            st.error(f"Nome invalido: {e}")
            st.stop()

    if exists:
        columns = dataset_svc.get_columns(schema, table)
        st.session_state["setup_validated"] = True
        st.session_state["setup_schema"] = schema
        st.session_state["setup_table"] = table
        st.session_state["setup_columns"] = columns
        # Limpar estado de etapas posteriores quando tabela muda
        for key in ["setup_config", "setup_profiles", "setup_date_range"]:
            st.session_state.pop(key, None)
        st.success(f"Tabela `{schema}.{table}` encontrada — {len(columns)} colunas")
        st.rerun()
    else:
        st.session_state["setup_validated"] = False
        st.error(f"Tabela `{schema}.{table}` nao encontrada.")
        st.stop()

if not st.session_state.get("setup_validated"):
    st.info("Informe schema e tabela e clique em **Validar Tabela** para continuar.")
    st.stop()

# Mostrar colunas encontradas
columns = st.session_state["setup_columns"]
schema = st.session_state["setup_schema"]
table = st.session_state["setup_table"]

with st.expander(f"Colunas de `{schema}.{table}` ({len(columns)})", expanded=False):
    for col_info in columns:
        st.text(f"  {col_info['name']:30s}  {col_info['type']}")


# ===================================================================
# STEP 2: Configurar eixo temporal
# ===================================================================

st.header("2. Eixo Temporal")

col_names = [c["name"] for c in columns]

partition_method = st.selectbox(
    "Metodo de particao:",
    options=[pm.value for pm in PartitionMethod],
    format_func=lambda x: {
        "incremental": "Incremental (cada particao = dados novos)",
        "full_snapshot": "Full Snapshot (cada particao = foto completa)",
        "non_partitioned": "Sem particao",
    }.get(x, x),
)

partition_col = None
if partition_method != PartitionMethod.NON_PARTITIONED.value:
    partition_col = st.selectbox("Coluna de particao:", col_names)

date_col = st.selectbox(
    "Coluna de data (eixo temporal):",
    col_names,
    index=col_names.index(partition_col) if partition_col and partition_col in col_names else 0,
)

col_t1, col_t2 = st.columns(2)
with col_t1:
    grain_type = st.selectbox(
        "Granularidade:",
        options=[g.value for g in GrainType],
        format_func=lambda x: {
            "daily": "Diario",
            "monthly": "Mensal",
            "timestamp": "Timestamp",
            "custom": "Custom",
        }.get(x, x),
    )

with col_t2:
    lookback_mode = st.selectbox(
        "Modo de lookback:",
        options=[lm.value for lm in LookbackMode],
        format_func=lambda x: {
            "last_n_periods": "Ultimos N periodos",
            "last_x_days": "Ultimos X dias",
        }.get(x, x),
    )

lookback_value = st.slider("Valor de lookback:", min_value=5, max_value=365, value=30)

date_expression = st.text_input(
    "Expressao de normalizacao (opcional):",
    placeholder='ex: CAST("dt_ref" AS DATE) ou date_trunc(\'month\', dt_evento)',
    help="Se a coluna de data e string ou precisa de transformacao, informe a expressao SQL.",
)


# ===================================================================
# STEP 3: Filtro base
# ===================================================================

st.header("3. Filtro Base (opcional)")

base_filter = st.text_input(
    "Filtro WHERE aplicado em todas as queries:",
    placeholder="ex: IND_ATIVO = 1 AND COD_SEGMENTO != 'TESTE'",
    help="Expressao SQL valida. Nao inclua WHERE.",
)


# ===================================================================
# STEP 4: Montar config e validar range temporal
# ===================================================================

st.header("4. Validar Configuracao")

dataset_config = DatasetConfig(
    schema=schema,
    table=table,
    partition_method=PartitionMethod(partition_method),
    partition_column=partition_col,
    date_column=date_col,
    grain_type=GrainType(grain_type),
    lookback_mode=LookbackMode(lookback_mode),
    lookback_value=lookback_value,
    date_expression=date_expression or None,
    base_filter_sql=base_filter or None,
)

if st.button("Validar Eixo Temporal", type="primary"):
    with st.spinner("Consultando range temporal..."):
        try:
            date_range = dataset_svc.get_date_range(dataset_config)
            st.session_state["setup_date_range"] = date_range
            st.session_state["setup_config"] = dataset_config
        except Exception as e:
            st.error(f"Erro ao consultar range temporal: {e}")
            st.stop()

    if date_range["n_periods"] == 0:
        st.warning("Nenhum periodo encontrado. Verifique a coluna temporal e o filtro base.")
    else:
        st.success(
            f"Range: **{date_range['min_date']}** a **{date_range['max_date']}** "
            f"— **{date_range['n_periods']}** periodos distintos"
        )
        st.rerun()

date_range = st.session_state.get("setup_date_range")
if not date_range or date_range.get("n_periods", 0) == 0:
    st.info("Clique em **Validar Eixo Temporal** para continuar.")
    st.stop()

st.success(
    f"Range: **{date_range['min_date']}** a **{date_range['max_date']}** "
    f"— **{date_range['n_periods']}** periodos distintos"
)


# ===================================================================
# STEP 5: Profiling de colunas
# ===================================================================

st.header("5. Profiling de Colunas")

dataset_config = st.session_state.get("setup_config", dataset_config)

st.warning(
    f"O profiling vai executar **{len(columns)}** queries de amostragem. "
    f"Em Athena real, isso gera custo proporcional ao volume de dados."
)

if st.button("Executar Profiling", type="primary"):
    profiles = []
    progress = st.progress(0, text="Classificando colunas...")

    for i, col_info in enumerate(columns):
        progress.progress(
            (i + 1) / len(columns),
            text=f"Classificando {col_info['name']}...",
        )
        profile_list = profiling_svc.profile_columns(
            dataset_config,
            [col_info],
            sample_periods=lookback_value,
        )
        profiles.extend(profile_list)

    progress.empty()
    st.session_state["setup_profiles"] = profiles
    st.success(f"Profiling concluido — {len(profiles)} colunas classificadas")
    st.rerun()

profiles = st.session_state.get("setup_profiles")
if not profiles:
    st.info("Clique em **Executar Profiling** para classificar as colunas.")
    st.stop()


# ===================================================================
# STEP 6: Resultado do profiling + override manual
# ===================================================================

st.header("6. Classificacao de Colunas")

st.caption("Revise a classificacao inferida. Use o dropdown para alterar manualmente.")

semantic_options = [s.value for s in SemanticType]
semantic_labels = {s.value: _semantic_type_label(s) for s in SemanticType}

overrides = {}
selected_cols = []

for profile in profiles:
    col_a, col_b, col_c, col_d = st.columns([3, 2, 3, 1])

    with col_a:
        st.text(profile.column_name)

    with col_b:
        st.caption(profile.athena_type)

    with col_c:
        current = profile.effective_type.value
        new_type = st.selectbox(
            "Tipo",
            options=semantic_options,
            index=semantic_options.index(current),
            format_func=lambda x: semantic_labels.get(x, x),
            key=f"type_{profile.column_name}",
            label_visibility="collapsed",
        )
        if new_type != profile.inferred_semantic_type.value:
            overrides[profile.column_name] = SemanticType(new_type)

    with col_d:
        is_selected = st.checkbox(
            "Sel",
            value=True,
            key=f"sel_{profile.column_name}",
            label_visibility="collapsed",
        )
        if is_selected:
            selected_cols.append(profile.column_name)

    # Mostrar warnings se houver
    if profile.warnings:
        for w in profile.warnings:
            st.caption(f"  {w}")

# Aplicar overrides
if overrides:
    profiling_svc.apply_user_overrides(profiles, overrides)

# Resumo
n_numeric = sum(
    1 for p in profiles
    if p.column_name in selected_cols and p.effective_type == SemanticType.NUMERIC
)
n_cat = sum(
    1 for p in profiles
    if p.column_name in selected_cols and p.effective_type in (
        SemanticType.CATEGORICAL_LOW_CARDINALITY,
        SemanticType.CATEGORICAL_MID_CARDINALITY,
        SemanticType.CATEGORICAL_HIGH_CARDINALITY,
    )
)

st.divider()
st.markdown(
    f"**Selecionadas:** {len(selected_cols)} colunas "
    f"({n_numeric} numericas, {n_cat} categoricas)"
)


# ===================================================================
# STEP 7: Salvar preset
# ===================================================================

st.header("7. Salvar Configuracao")

dataset_config.selected_columns = selected_cols

preset_name = st.text_input(
    "Nome do preset:",
    value=f"{schema}_{table}",
    help="Sera salvo em presets/<nome>.json",
)

if st.button("Salvar Preset", type="primary", disabled=not selected_cols):
    # Montar preset
    preset = {
        "schema": dataset_config.schema,
        "table": dataset_config.table,
        "partition_method": dataset_config.partition_method.value,
        "partition_column": dataset_config.partition_column,
        "date_column": dataset_config.date_column,
        "grain_type": dataset_config.grain_type.value,
        "lookback_mode": dataset_config.lookback_mode.value,
        "lookback_value": dataset_config.lookback_value,
        "date_expression": dataset_config.date_expression,
        "base_filter_sql": dataset_config.base_filter_sql,
        "selected_columns": dataset_config.selected_columns,
        "overrides": {k: v.value for k, v in overrides.items()},
        "date_range": date_range,
    }

    preset_dir = Path(app_config.preset_dir)
    preset_dir.mkdir(exist_ok=True)
    preset_path = preset_dir / f"{preset_name}.json"
    preset_path.write_text(json.dumps(preset, indent=2, ensure_ascii=False))

    st.success(f"Preset salvo em `{preset_path}`")

    # Salvar config no session_state para proximas paginas
    st.session_state["dataset_config"] = dataset_config
    st.session_state["column_profiles"] = profiles

    st.info("Configuracao pronta! Va para a pagina **Explore** para analisar colunas.")
