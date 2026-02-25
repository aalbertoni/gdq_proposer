"""
Pagina 01 — Setup: Configuracao da tabela alvo.

Fluxo simplificado:
- Carregar preset existente OU configurar nova tabela
- Setup da tabela + eixo temporal + profiling em um fluxo continuo
- Resultado do profiling com selecao de colunas inline
- Salva config no session_state para uso imediato na pagina Explore

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
    if "client" not in st.session_state:
        config = load_config()
        st.session_state["config"] = config
        st.session_state["client"] = AthenaClient(config)
    return st.session_state["client"]


def get_services(client: AthenaClient):
    if "dataset_service" not in st.session_state:
        builder = QueryBuilder(dialect=client.dialect)
        st.session_state["dataset_service"] = DatasetService(client, builder)
        st.session_state["profiling_service"] = ProfilingService(client, builder)
    return (
        st.session_state["dataset_service"],
        st.session_state["profiling_service"],
    )


def _semantic_type_label(st_type: SemanticType) -> str:
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


def _load_preset(path: Path, profiling_svc, dataset_svc) -> bool:
    """Carrega preset e popula session_state. Retorna True se sucesso."""
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        st.error(f"Erro ao ler preset: {e}")
        return False

    schema = data["schema"]
    table = data["table"]

    # Validar tabela
    try:
        exists = dataset_svc.validate_table(schema, table)
    except ValueError:
        exists = False

    if not exists:
        st.error(f"Tabela `{schema}.{table}` nao encontrada no backend atual.")
        return False

    columns = dataset_svc.get_columns(schema, table)

    config = DatasetConfig(
        schema=schema,
        table=table,
        partition_method=PartitionMethod(data.get("partition_method", "incremental")),
        partition_column=data.get("partition_column"),
        date_column=data.get("date_column", ""),
        grain_type=GrainType(data.get("grain_type", "daily")),
        lookback_mode=LookbackMode(data.get("lookback_mode", "last_n_periods")),
        lookback_value=data.get("lookback_value", 30),
        date_expression=data.get("date_expression"),
        base_filter_sql=data.get("base_filter_sql"),
        selected_columns=data.get("selected_columns", []),
    )

    st.session_state["setup_validated"] = True
    st.session_state["setup_schema"] = schema
    st.session_state["setup_table"] = table
    st.session_state["setup_columns"] = columns
    st.session_state["setup_config"] = config
    st.session_state["setup_date_range"] = data.get("date_range", {})

    return True


def _activate_config():
    """Salva config ativa no session_state para uso nas paginas Explore/Review."""
    config = st.session_state.get("setup_config")
    profiles = st.session_state.get("setup_profiles")
    if config and profiles:
        st.session_state["dataset_config"] = config
        st.session_state["column_profiles"] = profiles


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Setup - GDQ Rule Proposer", page_icon=":gear:")

st.title("Setup da Tabela")

try:
    client = get_client()
except Exception as e:
    st.error(f"Falha na conexao: {e}")
    st.stop()

app_config = st.session_state["config"]
is_mock = app_config.athena.mode == AthenaMode.MOCK
dataset_svc, profiling_svc = get_services(client)


# ===================================================================
# Presets existentes
# ===================================================================

preset_dir = Path(app_config.preset_dir)
preset_files = sorted(preset_dir.glob("*.json")) if preset_dir.exists() else []

if preset_files:
    st.subheader("Carregar Configuracao Existente")
    preset_names = ["(nova configuracao)"] + [p.stem for p in preset_files]

    chosen_preset = st.selectbox(
        "Preset:",
        preset_names,
        key="setup_preset_choice",
        help="Selecione um preset salvo ou crie uma nova configuracao.",
    )

    if chosen_preset != "(nova configuracao)":
        preset_path = preset_dir / f"{chosen_preset}.json"
        if st.button("Carregar Preset", type="primary"):
            with st.spinner("Validando preset..."):
                ok = _load_preset(preset_path, profiling_svc, dataset_svc)
            if ok:
                st.success(f"Preset **{chosen_preset}** carregado.")
                # Precisa rodar profiling se nao tem profiles no state
                if "setup_profiles" not in st.session_state:
                    st.info("Execute o profiling abaixo para ativar a configuracao.")
                st.rerun()

        # Mostrar preview do preset
        with st.expander("Preview do preset", expanded=False):
            data = json.loads(preset_path.read_text())
            st.json(data)

    st.divider()


# ===================================================================
# STEP 1: Selecionar e validar tabela
# ===================================================================

st.header("1. Tabela")

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

columns = st.session_state["setup_columns"]
schema = st.session_state["setup_schema"]
table = st.session_state["setup_table"]

with st.expander(f"Colunas de `{schema}.{table}` ({len(columns)})", expanded=True):
    for col_info in columns:
        st.text(f"  {str(col_info['name']):30s}  {col_info['type']}")


# ===================================================================
# STEP 2: Eixo temporal
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
# STEP 4: Validar range temporal
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

    # Quick summary by semantic type
    type_counts: dict[str, int] = {}
    for p in profiles:
        label = _semantic_type_label(p.effective_type)
        type_counts[label] = type_counts.get(label, 0) + 1
    summary_items = [f"**{v}** {k}" for k, v in sorted(type_counts.items(), key=lambda x: -x[1])]
    st.info("Resumo: " + " · ".join(summary_items))

    st.rerun()

profiles = st.session_state.get("setup_profiles")
if not profiles:
    st.info("Clique em **Executar Profiling** para classificar as colunas.")
    st.stop()


# ===================================================================
# STEP 6: Classificacao + selecao de colunas
# ===================================================================

st.header("6. Selecao de Colunas")

st.caption(
    "Revise a classificacao inferida e selecione as colunas para analise. "
    "Use o dropdown para alterar o tipo manualmente."
)

semantic_options = [s.value for s in SemanticType]
semantic_labels = {s.value: _semantic_type_label(s) for s in SemanticType}
semantic_label_to_value = {v: k for k, v in semantic_labels.items()}

# Carregar selecoes anteriores se existirem (do preset ou sessao anterior)
prev_selected = set(dataset_config.selected_columns or [])

# --- Quick select/deselect buttons ---
qs_col1, qs_col2, qs_col3 = st.columns(3)
with qs_col1:
    if st.button("Selecionar todas"):
        for p in profiles:
            st.session_state[f"sel_{p.column_name}"] = True
        st.rerun()
with qs_col2:
    if st.button("Desmarcar todas"):
        for p in profiles:
            st.session_state[f"sel_{p.column_name}"] = False
        st.rerun()
with qs_col3:
    if st.button("Somente numericas"):
        for p in profiles:
            st.session_state[f"sel_{p.column_name}"] = (p.effective_type == SemanticType.NUMERIC)
        st.rerun()

overrides = {}
selected_cols = []

# Header row
hdr1, hdr2, hdr3, hdr4, hdr5 = st.columns([0.5, 2.5, 1.5, 2.5, 1])
hdr1.markdown("**Sel**")
hdr2.markdown("**Coluna**")
hdr3.markdown("**Tipo Athena**")
hdr4.markdown("**Tipo Semantico**")
hdr5.markdown("**Null %**")

for profile in profiles:
    col_d, col_a, col_b, col_c, col_e = st.columns([0.5, 2.5, 1.5, 2.5, 1])

    with col_d:
        default_sel = profile.column_name in prev_selected if prev_selected else True
        is_selected = st.checkbox(
            "Sel",
            value=default_sel,
            key=f"sel_{profile.column_name}",
            label_visibility="collapsed",
        )
        if is_selected:
            selected_cols.append(profile.column_name)

    with col_a:
        st.code(profile.column_name, language=None)

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

    with col_e:
        null_pct = profile.null_ratio * 100
        if null_pct > 50:
            st.markdown(f":red[{null_pct:.0f}%]")
        elif null_pct > 10:
            st.markdown(f":orange[{null_pct:.0f}%]")
        else:
            st.caption(f"{null_pct:.0f}%")

    if profile.warnings:
        for w in profile.warnings:
            st.caption(f"  {w}")

# Aplicar overrides
if overrides:
    profiling_svc.apply_user_overrides(profiles, overrides)

# Resumo por tipo
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
# STEP 7: Ativar configuracao (e opcionalmente salvar preset)
# ===================================================================

st.header("7. Ativar Configuracao")

dataset_config.selected_columns = selected_cols

col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    if st.button(
        "Ativar e ir para Explore",
        type="primary",
        disabled=not selected_cols,
    ):
        st.session_state["setup_config"] = dataset_config
        st.session_state["dataset_config"] = dataset_config
        st.session_state["column_profiles"] = profiles
        st.switch_page("pages/02_explore.py")

with col_btn2:
    save_preset = st.checkbox("Salvar como preset", value=False)

if save_preset:
    preset_name = st.text_input(
        "Nome do preset:",
        value=f"{schema}_{table}",
        help="Sera salvo em presets/<nome>.json",
    )

    if st.button("Salvar Preset", disabled=not selected_cols):
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

        pdir = Path(app_config.preset_dir)
        pdir.mkdir(exist_ok=True)
        preset_path = pdir / f"{preset_name}.json"
        preset_path.write_text(json.dumps(preset, indent=2, ensure_ascii=False))
        st.success(f"Preset salvo em `{preset_path}`")


# Status bar: mostrar se config esta ativa
if "dataset_config" in st.session_state:
    cfg = st.session_state["dataset_config"]
    n_sel = len(cfg.selected_columns) if cfg.selected_columns else 0
    st.sidebar.success(
        f"Config ativa: `{cfg.schema}.{cfg.table}` ({n_sel} colunas)"
    )
else:
    st.sidebar.info("Nenhuma config ativa.")
