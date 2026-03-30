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
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from pages.components.breadcrumb import render_breadcrumb
from pages.components.theme import inject_global_css

from config import load_config
from core.models.dataset_config import DatasetConfig
from core.models.enums import (
    DateFilterGranularity,
    DateReferenceStrategy,
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


# ---------------------------------------------------------------------------
# Cached metadata fetchers
# TTL matches config defaults: metadata=3600s, profiling=1800s
# Cache is keyed by _client_id which changes on reconnect
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_validate_table(_client_id, schema, table):
    """Cached table validation. _client_id forces cache bust on reconnect."""
    svc = st.session_state["dataset_service"]
    return svc.validate_table(schema, table)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_get_columns_with_partitions(_client_id, schema, table):
    """Cached column discovery. _client_id forces cache bust on reconnect."""
    svc = st.session_state["dataset_service"]
    return svc.get_columns_with_partitions(schema, table)


@st.cache_data(ttl=3600, show_spinner="Consultando range temporal...")
def _cached_get_date_range(_client_id, config_dict):
    """Cached date range query. _client_id forces cache bust on reconnect."""
    svc = st.session_state["dataset_service"]
    config = _build_config_from_dict(config_dict)
    return svc.get_date_range(config)


@st.cache_resource(ttl=1800, show_spinner=False)
def _cached_profile_column(_client_id, config_dict, col_name, col_type, sample_periods):
    """Cached single-column profiling."""
    svc = st.session_state["profiling_service"]
    config = _build_config_from_dict(config_dict)
    col_info = {"name": col_name, "type": col_type}
    return svc.profile_columns(config, [col_info], sample_periods=sample_periods)


@st.cache_resource(ttl=1800, show_spinner=False)
def _cached_batch_profile(_client_id, config_dict, _col_names_frozen, _col_types_frozen, sample_periods):
    """Cached batch profiling. 1 query para todas as colunas."""
    svc = st.session_state["profiling_service"]
    config = _build_config_from_dict(config_dict)
    columns = [
        {"name": n, "type": t}
        for n, t in zip(_col_names_frozen, _col_types_frozen)
    ]
    return svc.profile_columns(config, columns, sample_periods=sample_periods)


def _build_config_from_dict(config_dict):
    return DatasetConfig(
        schema=config_dict["schema"],
        table=config_dict["table"],
        partition_method=PartitionMethod(config_dict["partition_method"]),
        partition_column=config_dict.get("partition_column"),
        partition_format=config_dict.get("partition_format"),
        partition_is_integer=config_dict.get("partition_is_integer", False),
        date_column=config_dict["date_column"],
        date_expression=config_dict.get("date_expression"),
        lookback_value=config_dict["lookback_value"],
        grain_type=GrainType(config_dict.get("grain_type", "daily")),
        lookback_mode=LookbackMode(config_dict.get("lookback_mode", "last_n_periods")),
        base_filter_sql=config_dict.get("base_filter_sql"),
        reference_date=config_dict.get("reference_date"),
    )


def _get_client_id() -> str:
    """Unique ID for the current client connection. Used to bust cache on reconnect."""
    return id(st.session_state.get("client", None))


def _semantic_type_label(st_type: SemanticType) -> str:
    from core.models.enums import get_semantic_label
    return get_semantic_label(st_type)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_sample_column_values(_client_id, schema, table, column, limit=5):
    """Fetch a small sample of distinct non-null values from a column.

    Uses LIMIT to minimize cost (typically a single partition scan).
    Returns list of string representations.
    """
    from infra.query_safety import validate_identifier
    _schema = validate_identifier(schema)
    _table = validate_identifier(table)
    _col = validate_identifier(column)
    sql = (
        f'SELECT DISTINCT "{_col}" FROM "{_schema}"."{_table}" '
        f'WHERE "{_col}" IS NOT NULL LIMIT {int(limit)}'
    )
    client = st.session_state["client"]
    rows = client.execute(sql, query_name="sample_column_values", dataset=f"{schema}.{table}", column=column)
    return [str(r[column]) for r in rows if r.get(column) is not None]


    # _detect_date_format imported from core.date_format_detector


def _load_preset(path: Path, profiling_svc, dataset_svc) -> bool:
    """Carrega preset e popula session_state. Retorna True se sucesso."""
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        st.error(f"Erro ao ler preset: {e}")
        return False

    schema = data["schema"]
    table = data["table"]

    # Validar tabela (cached)
    client_id = _get_client_id()
    try:
        exists = _cached_validate_table(client_id, schema, table)
    except ConnectionError as e:
        st.error(str(e))
        return False
    except ValueError:
        exists = False

    if not exists:
        st.error(f"Tabela `{schema}.{table}` nao encontrada no backend atual.")
        return False

    columns, partition_cols = _cached_get_columns_with_partitions(client_id, schema, table)
    st.session_state["setup_partition_cols"] = partition_cols

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
        unique_key_columns=data.get("unique_key_columns", []),
    )

    # Preencher reference_date a partir do date_range do preset
    _preset_date_range = data.get("date_range", {})
    _preset_max = _preset_date_range.get("max_date")
    if _preset_max:
        config.reference_date = str(_preset_max)[:10]

    st.session_state["setup_validated"] = True
    st.session_state["setup_schema"] = schema
    st.session_state["setup_table"] = table
    st.session_state["setup_columns"] = columns
    st.session_state["setup_config"] = config
    st.session_state["setup_date_range"] = _preset_date_range
    st.session_state["setup_pk_columns"] = data.get("unique_key_columns", [])

    # Clear stale sel_* keys so checkbox defaults from preset take effect
    _stale_sel_keys = [k for k in st.session_state if isinstance(k, str) and k.startswith("sel_")]
    for k in _stale_sel_keys:
        del st.session_state[k]

    # Restore cached profiles if available
    _cached_profiles_raw = data.get("column_profiles", [])
    _profiles_cached_at = data.get("profiles_cached_at", "")
    if _cached_profiles_raw:
        st.session_state["_preset_cached_profiles"] = _cached_profiles_raw
        st.session_state["_preset_profiles_cached_at"] = _profiles_cached_at

    return True


def _clear_analysis_state():
    """Limpa estado analitico do session_state ao trocar configuracao.

    Remove carrinho, proposals, series profiles, auto-tune e col_health.
    Nao remove chaves de infraestrutura (client, services, setup_*).
    """
    _ANALYSIS_PREFIXES = (
        "proposal_mean_", "proposal_stddev_", "proposal_comp_",
        "proposal_pct_", "proposal_rc_", "proposal_pk_",
        "cat_proposals_",
        "series_profile_",
        "autotune_",
    )
    # Chaves exatas
    for key in ["rule_cart", "col_health"]:
        st.session_state.pop(key, None)
    # Chaves por prefixo
    keys_to_remove = [
        k for k in list(st.session_state.keys())
        if isinstance(k, str) and any(k.startswith(p) for p in _ANALYSIS_PREFIXES)
    ]
    for key in keys_to_remove:
        del st.session_state[key]


def _activate_config():
    """Salva config ativa no session_state para uso nas paginas Explore/Review.

    Compara fingerprint de analise com a configuracao anterior.
    Se houve mudanca, limpa todo o estado analitico para evitar
    contaminacao cruzada entre configuracoes diferentes.
    """
    config = st.session_state.get("setup_config")
    profiles = st.session_state.get("setup_profiles")
    if not config or not profiles:
        return

    old_fp = st.session_state.get("_analysis_fingerprint", "")
    new_fp = config.analysis_fingerprint()

    if old_fp != new_fp:
        _clear_analysis_state()
        st.session_state["_analysis_fingerprint"] = new_fp

    st.session_state["dataset_config"] = config
    st.session_state["column_profiles"] = profiles


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Setup - GDQ Rule Proposer", page_icon=":gear:")
inject_global_css()

st.title("Setup da Tabela")
render_breadcrumb("Setup")
st.caption(
    "Configure a tabela alvo, eixo temporal e colunas para analise. "
    "Ao final, ative a configuracao para ir para a calibracao de regras."
)


# ===================================================================
# Inicializacao
# ===================================================================

try:
    client = get_client()
except Exception as e:
    st.error(f"Falha na conexao: {e}")
    st.stop()

app_config = st.session_state["config"]
dataset_svc, profiling_svc = get_services(client)


# ===================================================================
# Presets existentes
# ===================================================================

preset_dir = Path(app_config.preset_dir)
preset_dir.mkdir(exist_ok=True)
preset_files = sorted(preset_dir.glob("*.json"))

st.subheader("Presets")

if preset_files:
    preset_names = ["(nova configuracao)"] + [p.stem for p in preset_files]

    chosen_preset = st.selectbox(
        "Preset:",
        preset_names,
        key="setup_preset_choice",
        help="Selecione um preset salvo ou crie uma nova configuracao.",
    )

    if chosen_preset != "(nova configuracao)":
        from services.preset_manager import PresetManager

        preset_path = preset_dir / f"{chosen_preset}.json"
        _preset_col1, _preset_col2 = st.columns(2)

        with _preset_col1:
            if st.button("Carregar Preset", type="primary"):
                mgr = PresetManager(app_config.preset_dir)
                mgr.mark_used(chosen_preset)
                with st.spinner("Validando preset..."):
                    ok = _load_preset(preset_path, profiling_svc, dataset_svc)
                if ok:
                    st.success(f"Preset **{chosen_preset}** carregado.")
                    st.rerun()

        # After load: offer instant activation if cached profiles exist
        _has_cached = "_preset_cached_profiles" in st.session_state
        _cached_at = st.session_state.get("_preset_profiles_cached_at", "")
        if _has_cached and st.session_state.get("setup_config"):
            _cached_date = _cached_at[:10] if _cached_at else "data desconhecida"
            _n_profiles = len(st.session_state["_preset_cached_profiles"])
            st.divider()
            st.markdown(
                f"**Dados de profiling em cache** — {_n_profiles} colunas "
                f"perfiladas em {_cached_date}"
            )
            _cache_col1, _cache_col2 = st.columns(2)
            with _cache_col1:
                if st.button(
                    f"Usar cache de {_cached_date} (instantaneo)",
                    type="primary",
                    help="Restaura profiling salvo no preset sem executar nenhuma query. "
                         "Use quando a estrutura da tabela nao mudou.",
                ):
                    from services.preset_manager import deserialize_profiles
                    _profiles = deserialize_profiles(
                        st.session_state["_preset_cached_profiles"]
                    )
                    st.session_state["setup_profiles"] = _profiles
                    st.session_state.pop("_preset_cached_profiles", None)
                    st.session_state.pop("_preset_profiles_cached_at", None)
                    _activate_config()
                    st.success("Configuracao ativada com dados em cache.")
                    st.switch_page("pages/02_explore.py")
            with _cache_col2:
                if st.button(
                    "Executar profiling novamente",
                    help="Ignora o cache e executa profiling fresco via Athena. "
                         "Use se a tabela mudou desde o ultimo profiling.",
                ):
                    st.session_state.pop("_preset_cached_profiles", None)
                    st.session_state.pop("_preset_profiles_cached_at", None)
                    st.info("Configure o profiling abaixo para executar novamente.")
                    st.rerun()

        with _preset_col2:
            if len(preset_names) > 2:
                if st.button("Comparar presets"):
                    st.session_state["show_compare_ui"] = True

        # Mostrar preview com metadados
        with st.expander("Preview do preset", expanded=False):
            data = json.loads(preset_path.read_text())
            meta = data.get("metadata", {})
            if meta.get("notes"):
                st.caption(f"Notas: {meta['notes']}")
            if meta.get("last_used_at"):
                st.caption(f"Ultimo uso: {meta['last_used_at'][:10]}")
            st.json(data)

        # Comparar presets UI
        if st.session_state.get("show_compare_ui") and len(preset_names) > 2:
            real_presets = [n for n in preset_names if n != "(nova configuracao)"]
            cmp_col1, cmp_col2 = st.columns(2)
            with cmp_col1:
                cmp_a = st.selectbox("Preset A:", real_presets, key="cmp_a")
            with cmp_col2:
                others = [n for n in real_presets if n != cmp_a]
                cmp_b = st.selectbox("Preset B:", others, key="cmp_b") if others else None

            if cmp_b:
                mgr = PresetManager(app_config.preset_dir)
                diffs = mgr.compare(cmp_a, cmp_b)
                if diffs:
                    for d in diffs:
                        st.text(f"  {d['field']:25s}  {str(d['value_a']):30s}  {str(d['value_b'])}")
                else:
                    st.caption("Presets identicos (mesma configuracao).")
else:
    st.info(
        "Nenhum preset salvo. Configure a tabela abaixo e no passo 7 "
        "marque **\"Salvar como preset\"** para reutilizar esta configuracao."
    )

st.divider()


# ===================================================================
# STEP 1: Selecionar e validar tabela
# ===================================================================

st.header("1. Tabela")

col1, col2 = st.columns(2)
with col1:
    schema = st.text_input(
        "Schema (Glue database):",
        value="gdq_test_db",
        placeholder="ex: datalake_trusted",
        help="Nome do banco no Glue Catalog. Ex: gdq_test_db, datalake_raw.",
    )

with col2:
    table = st.text_input(
        "Tabela:",
        placeholder="ex: tb_operacoes_credito",
        help="Nome da tabela a ser analisada. Deve existir no schema informado.",
    )

if st.button("Validar Tabela", disabled=not table, type="primary"):
    client_id = _get_client_id()
    with st.spinner("Verificando tabela..."):
        try:
            exists = _cached_validate_table(client_id, schema, table)
        except ConnectionError as e:
            st.error(str(e))
            st.stop()
        except ValueError as e:
            st.error(
                f"Nome invalido: {e}. "
                "Use apenas letras, numeros e underscore."
            )
            st.stop()

    if exists:
        columns, partition_cols = _cached_get_columns_with_partitions(client_id, schema, table)
        st.session_state["setup_validated"] = True
        st.session_state["setup_schema"] = schema
        st.session_state["setup_table"] = table
        st.session_state["setup_columns"] = columns
        st.session_state["setup_partition_cols"] = partition_cols
        for key in ["setup_config", "setup_profiles", "setup_date_range"]:
            st.session_state.pop(key, None)
        part_info = f", particao: {', '.join(partition_cols)}" if partition_cols else ", sem particao detectada"
        st.success(f"Tabela `{schema}.{table}` encontrada — {len(columns)} colunas{part_info}")
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
col_type_map = {c["name"]: c["type"].strip().lower() for c in columns}
detected_partition_cols = st.session_state.get("setup_partition_cols", [])

# Types that can serve as temporal axis
_TEMPORAL_BASE_TYPES = {
    "date", "timestamp", "timestamp with time zone",
    "string", "varchar", "char",
    "bigint", "int", "integer", "smallint", "tinyint",
}


def _base_type(t: str) -> str:
    """Strip parenthesized params: 'varchar(100)' -> 'varchar'."""
    t = t.strip().lower()
    paren = t.find("(")
    return t[:paren] if paren != -1 else t


temporal_candidates = []
for c in columns:
    base = _base_type(c["type"])
    is_partition = c["name"] in detected_partition_cols
    if base in _TEMPORAL_BASE_TYPES or is_partition:
        temporal_candidates.append(c["name"])

if not temporal_candidates:
    st.warning(
        "Nenhuma coluna de tipo date, timestamp ou string encontrada. "
        "Todas as colunas serao listadas como fallback."
    )
    temporal_candidates = col_names

# --- Partition info (auto-detected) ---
if detected_partition_cols:
    st.text_input(
        "Colunas de particao (detectadas automaticamente):",
        value=", ".join(detected_partition_cols),
        disabled=True,
        help="Colunas de particao detectadas no catalogo Glue. Nao editavel.",
    )
    partition_col = detected_partition_cols[0]  # Primary partition column

    partition_method = st.selectbox(
        "Metodo de particao:",
        options=[PartitionMethod.INCREMENTAL.value, PartitionMethod.FULL_SNAPSHOT.value],
        format_func=lambda x: {
            "incremental": "Incremental (cada particao = dados novos)",
            "full_snapshot": "Full Snapshot (cada particao = foto completa)",
        }.get(x, x),
        help="Incremental: cada particao contem dados novos. Full Snapshot: cada particao contem foto completa.",
    )
else:
    st.info("Nenhuma coluna de particao detectada. Tabela sera tratada como nao-particionada.")
    partition_method = PartitionMethod.NON_PARTITIONED.value
    partition_col = None

date_col = st.selectbox(
    "Coluna de data (eixo temporal):",
    temporal_candidates,
    index=temporal_candidates.index(partition_col) if partition_col and partition_col in temporal_candidates else 0,
    help="Somente colunas de tipo date, timestamp ou string sao listadas. "
         "Colunas numericas (int, double, etc.) nao podem ser usadas como eixo temporal.",
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
        help="Frequencia dos periodos de analise. "
             "Diario = 1 periodo por dia. Mensal = 1 periodo por mes.",
    )

if grain_type == "monthly":
    st.info(
        "Granularidade **mensal** detectada. Os parametros de analise "
        "(janela de lookback, auto-tune, thresholds de confianca) serao "
        "adaptados automaticamente para series mais curtas."
    )

with col_t2:
    lookback_mode = st.selectbox(
        "Modo de lookback:",
        options=[lm.value for lm in LookbackMode],
        format_func=lambda x: {
            "last_n_periods": "Ultimos N periodos",
            "last_x_days": "Ultimos X dias",
        }.get(x, x),
        help="Quantos periodos recentes considerar na analise.",
    )

lookback_value = st.slider(
    "Valor de lookback:",
    min_value=5,
    max_value=730,
    value=30,
    help=(
        "Quantidade de periodos recentes a considerar (relativo a hoje). "
        "Valores entre 20 e 60 costumam funcionar bem. "
        "Se os dados da tabela sao historicos (nao recentes), aumente o valor "
        "para cobrir o range temporal real dos dados."
    ),
)

# Auto-suggest date_expression if selected date col is string type
selected_col_base_type = _base_type(col_type_map.get(date_col, ""))
_STRING_TYPES = {"string", "varchar", "char"}
_INTEGER_TYPES = {"bigint", "int", "integer", "smallint", "tinyint"}
needs_date_expression = selected_col_base_type in (_STRING_TYPES | _INTEGER_TYPES)
is_integer_temporal = selected_col_base_type in _INTEGER_TYPES

if needs_date_expression:
    # SQL expressions: (label, athena_expr, partition_format_for_pruning)
    # partition_format: strftime format for raw partition column comparison
    # None = no safe pruning (epoch, custom, non-lexicographic)
    if is_integer_temporal:
        _DATE_PATTERNS = [
            (
                "yyyyMMdd como inteiro (ex: 20240115)",
                'DATE_PARSE(CAST("{col}" AS VARCHAR), \'%Y%m%d\')',
                "%Y%m%d",
            ),
            (
                "yyyyMM como inteiro (ex: 202401)",
                'DATE_PARSE(CAST("{col}" AS VARCHAR), \'%Y%m\')',
                "%Y%m",
            ),
            (
                "Epoch segundos (ex: 1705276800)",
                'CAST(FROM_UNIXTIME("{col}") AS DATE)',
                None,  # Epoch nao suporta pruning lexicografico
            ),
            (
                "Epoch milissegundos (ex: 1705276800000)",
                'CAST(FROM_UNIXTIME("{col}" / 1000) AS DATE)',
                None,
            ),
            (
                "Customizado (digitar manualmente)",
                "",
                None,
            ),
        ]
    else:
        _DATE_PATTERNS = [
            (
                "yyyy-MM-dd (ex: 2024-01-15)",
                'CAST("{col}" AS DATE)',
                "%Y-%m-%d",
            ),
            (
                "yyyyMMdd (ex: 20240115)",
                'DATE_PARSE("{col}", \'%Y%m%d\')',
                "%Y%m%d",
            ),
            (
                "yyyyMM (ex: 202401)",
                'DATE_PARSE("{col}", \'%Y%m\')',
                "%Y%m",
            ),
            (
                "dd/MM/yyyy (ex: 15/01/2024)",
                'DATE_PARSE("{col}", \'%d/%m/%Y\')',
                None,  # Nao lexicografico — pruning inseguro
            ),
            (
                "yyyy-MM-dd HH:mm:ss (ex: 2024-01-15 10:30:00)",
                'CAST("{col}" AS TIMESTAMP)',
                "%Y-%m-%d",
            ),
            (
                "Customizado (digitar manualmente)",
                "",
                None,
            ),
        ]

    pattern_labels = [p[0] for p in _DATE_PATTERNS]

    # --- Smart detection: sample real values to suggest the right format ---
    _suggested_idx = 0
    _sample_values = []
    try:
        _client_id = _get_client_id()
        _sample_values = _cached_sample_column_values(_client_id, schema, table, date_col, limit=5)
        if _sample_values:
            from core.date_format_detector import detect_date_format
            _suggested_idx, _sample_values = detect_date_format(_sample_values, is_integer_temporal)
    except Exception:
        pass  # Fallback to default index 0 if sample fails

    _detection_help = (
        "Selecione o formato que corresponde aos valores da coluna. "
        "A expressao SQL sera gerada automaticamente para o backend ativo."
    )
    if _sample_values:
        _sample_display = ", ".join(_sample_values[:3])
        _detected_label = pattern_labels[_suggested_idx].split(" (")[0]  # "yyyyMMdd como inteiro"
        st.caption(f"Formato detectado: **{_detected_label}** (amostra: `{_sample_display}`)")
        _detection_help = (
            f"Detectado automaticamente a partir de valores reais da coluna "
            f"(ex: {_sample_display}). Altere se a sugestao nao estiver correta."
        )

    chosen_pattern = st.selectbox(
        "Formato da coluna de data:",
        pattern_labels,
        index=_suggested_idx,
        key="date_format_pattern",
        help=_detection_help,
    )

    chosen_idx = pattern_labels.index(chosen_pattern)
    is_custom = chosen_idx == len(_DATE_PATTERNS) - 1

    if is_custom:
        date_expression = st.text_input(
            "Expressao SQL customizada (obrigatoria):",
            value="",
            placeholder=f'ex: DATE_PARSE("{date_col}", \'%Y%m%d\')',
            help="Informe a expressao SQL que converte a coluna string para date/timestamp.",
        )
        _partition_format = None  # Custom — sem pruning seguro
    else:
        _, athena_expr, _partition_format = _DATE_PATTERNS[chosen_idx]
        date_expression = athena_expr.format(col=date_col)

        st.code(date_expression, language="sql")
        st.caption("Expressao SQL gerada automaticamente para o Athena.")

    # Feedback de pruning
    if _partition_format and partition_col and partition_col == date_col:
        from datetime import date as _d
        _preview_cutoff = _d.today().strftime(_partition_format)
        st.caption(f"Partition pruning: `\"{partition_col}\" >= '{_preview_cutoff}'`")
    elif partition_col and partition_col != date_col:
        st.caption(
            "Particao sem formato de data — "
            "pruning de custo nao sera aplicado nesta coluna."
        )
    elif partition_col:
        st.warning(
            "Este formato nao permite partition pruning otimizado. "
            "As queries podem escanear mais dados do que o necessario."
        )

    if not date_expression.strip():
        st.error(
            f"A coluna `{date_col}` e do tipo **{col_type_map.get(date_col, '?')}** "
            f"e precisa de uma expressao de normalizacao para ser usada como eixo temporal."
        )
        st.stop()

else:
    # date/timestamp columns: tipo nativo — pruning direto com DATE literal
    _partition_format = None
    date_expression = st.text_input(
        "Expressao de normalizacao (opcional):",
        value="",
        placeholder='ex: date_trunc(\'month\', "dt_evento")',
        help="Para colunas de tipo date/timestamp, normalmente nao e necessario. "
             "Use apenas se precisar de truncamento (ex: agrupar por mes).",
    )


# ===================================================================
# STEP 3: Filtro de data para regras GDQ (quando partition ≠ date)
# ===================================================================

# Defaults
_date_filter_granularity = DateFilterGranularity.NONE
_date_reference_strategy = DateReferenceStrategy.CURRENT
_date_reference_lag = 0
_gdq_date_filter_expr = None
_gdq_date_filter_format = None

_show_date_filter = (
    partition_col
    and partition_col != date_col
    and partition_col is not None
)

if _show_date_filter:
    st.header("3. Filtro de Data nas Regras GDQ")

    st.info(
        "A coluna de data de negocio (`{}`) e diferente da particao (`{}`). "
        "Voce pode configurar um filtro para que as regras GDQ avaliem "
        "apenas os registros de um periodo especifico, em vez do snapshot inteiro.".format(
            date_col, partition_col
        ),
        icon="📅",
    )

    # --- Granularity selector ---
    from core.gdq_date_filter import (
        GRANULARITY_LABELS,
        STRATEGY_LABELS,
        build_gdq_date_filter_expr,
        explain_date_filter,
        explain_execution_frequency_warning,
    )

    _gran_options = list(DateFilterGranularity)
    _gran_labels = [GRANULARITY_LABELS[g] for g in _gran_options]

    _chosen_gran_label = st.selectbox(
        "Granularidade do filtro de data:",
        _gran_labels,
        index=0,
        key="date_filter_granularity_select",
        help=(
            "Define a granularidade do filtro WHERE nas regras GDQ geradas. "
            "Escolha 'Sem filtro' para avaliar o snapshot inteiro (comportamento padrao)."
        ),
    )
    _date_filter_granularity = _gran_options[_gran_labels.index(_chosen_gran_label)]

    if _date_filter_granularity != DateFilterGranularity.NONE:
        # --- Reference strategy selector ---
        col_df1, col_df2 = st.columns(2)

        with col_df1:
            _strat_options = list(DateReferenceStrategy)
            _strat_labels = [STRATEGY_LABELS[s] for s in _strat_options]

            _chosen_strat_label = st.selectbox(
                "Estrategia de referencia temporal:",
                _strat_labels,
                index=0,
                key="date_reference_strategy_select",
                help=(
                    "Como identificar qual periodo avaliar a cada execucao do GDQ.\n\n"
                    "- **Periodo corrente:** Usa current_date() formatado. "
                    "Ideal quando o GDQ roda no mesmo dia/mes que os dados.\n"
                    "- **Defasagem fixa:** Usa N periodos atras. "
                    "Ideal para fechamentos mensais (ex: avaliar mes anterior).\n"
                    "- **Ultimo valor disponivel:** Usa max(coluna). "
                    "Ideal quando o delay de atualizacao e variavel."
                ),
            )
            _date_reference_strategy = _strat_options[_strat_labels.index(_chosen_strat_label)]

        with col_df2:
            if _date_reference_strategy == DateReferenceStrategy.LAG_N:
                _lag_label = {
                    DateFilterGranularity.DAY: "dias",
                    DateFilterGranularity.MONTH: "meses",
                    DateFilterGranularity.YEAR: "anos",
                }.get(_date_filter_granularity, "periodos")

                _date_reference_lag = st.number_input(
                    f"Defasagem ({_lag_label}):",
                    min_value=1,
                    max_value=365,
                    value=1,
                    key="date_reference_lag_input",
                    help=f"Quantos {_lag_label} atras do periodo corrente.",
                )
            else:
                _date_reference_lag = 0
                st.empty()

        # --- Detect column type for integer flag ---
        _date_col_base_type = _base_type(col_type_map.get(date_col, ""))
        _date_col_is_integer = _date_col_base_type in _INTEGER_TYPES

        # --- Build expression ---
        _gdq_date_filter_expr = build_gdq_date_filter_expr(
            column=date_col,
            granularity=_date_filter_granularity,
            strategy=_date_reference_strategy,
            lag=_date_reference_lag,
            column_is_integer=_date_col_is_integer,
        )

        # --- Preview ---
        if _gdq_date_filter_expr:
            st.markdown("**Filtro WHERE gerado para as regras GDQ (Spark SQL):**")
            st.code(f"WHERE {_gdq_date_filter_expr}", language="sql")

            # Explanation
            _explanation = explain_date_filter(
                date_col, _date_filter_granularity,
                _date_reference_strategy, _date_reference_lag,
            )
            st.caption(_explanation)

            # Execution frequency warning
            _freq_warning = explain_execution_frequency_warning(_date_filter_granularity)
            if _freq_warning:
                with st.expander("Sobre frequencia de execucao e last(N)", expanded=False):
                    st.markdown(_freq_warning)

        # Store spark format for later use
        _SPARK_DATE_FORMATS = {
            DateFilterGranularity.DAY: "yyyyMMdd",
            DateFilterGranularity.MONTH: "yyyyMM",
            DateFilterGranularity.YEAR: "yyyy",
        }
        _gdq_date_filter_format = _SPARK_DATE_FORMATS.get(_date_filter_granularity)

    st.divider()

_STEP_OFFSET = 1 if _show_date_filter else 0

# ===================================================================
# STEP 3/4: Filtro base
# ===================================================================

st.header(f"{3 + _STEP_OFFSET}. Filtro Base (opcional)")

base_filter = st.text_input(
    "Filtro WHERE aplicado em todas as queries:",
    placeholder="ex: IND_ATIVO = 1 AND COD_SEGMENTO != 'TESTE'",
    help=(
        "Filtro WHERE aplicado em todas as queries de analise. "
        "Util para excluir registros de teste ou segmentos irrelevantes. "
        "Nao inclua a palavra WHERE. Ex: IND_ATIVO = 1"
    ),
)


# ===================================================================
# STEP 4: Validar range temporal
# ===================================================================

st.header(f"{4 + _STEP_OFFSET}. Validar Configuracao")

dataset_config = DatasetConfig(
    schema=schema,
    table=table,
    partition_method=PartitionMethod(partition_method),
    partition_column=partition_col,
    partition_format=_partition_format if (partition_col and partition_col == date_col) else None,
    partition_is_integer=(
        partition_col is not None
        and _base_type(col_type_map.get(partition_col, "")) in _INTEGER_TYPES
    ),
    date_column=date_col,
    temporal_axis_column=date_col if (partition_col and partition_col != date_col) else None,
    grain_type=GrainType(grain_type),
    lookback_mode=LookbackMode(lookback_mode),
    lookback_value=lookback_value,
    date_expression=date_expression or None,
    date_filter_granularity=_date_filter_granularity,
    date_reference_strategy=_date_reference_strategy,
    date_reference_lag=_date_reference_lag,
    gdq_date_filter_expr=_gdq_date_filter_expr,
    gdq_date_filter_format=_gdq_date_filter_format,
    base_filter_sql=base_filter or None,
)

if st.button("Validar Eixo Temporal", type="primary"):
    client_id = _get_client_id()
    config_dict = {
        "schema": dataset_config.schema,
        "table": dataset_config.table,
        "partition_method": dataset_config.partition_method.value,
        "partition_column": dataset_config.partition_column,
        "partition_format": dataset_config.partition_format,
        "partition_is_integer": dataset_config.partition_is_integer,
        "date_column": dataset_config.date_column,
        "temporal_axis_column": dataset_config.temporal_axis_column,
        "date_expression": dataset_config.date_expression,
        "lookback_value": dataset_config.lookback_value,
        "grain_type": dataset_config.grain_type.value,
        "lookback_mode": dataset_config.lookback_mode.value,
        "base_filter_sql": dataset_config.base_filter_sql,
        "reference_date": dataset_config.reference_date,
        "date_filter_granularity": dataset_config.date_filter_granularity.value,
        "date_reference_strategy": dataset_config.date_reference_strategy.value,
        "date_reference_lag": dataset_config.date_reference_lag,
        "gdq_date_filter_expr": dataset_config.gdq_date_filter_expr,
        "gdq_date_filter_format": dataset_config.gdq_date_filter_format,
    }
    try:
        date_range = _cached_get_date_range(client_id, config_dict)
        st.session_state["setup_date_range"] = date_range
        st.session_state["setup_config"] = dataset_config
    except Exception as e:
        from infra.cost_guard import PartitionMetadataError, CostGuardrailTriggered
        if isinstance(e, PartitionMetadataError):
            st.error(
                f"Erro ao descobrir particoes: {e}\n\n"
                "Verifique:\n"
                "- Se a coluna de particao e formato estao corretos\n"
                "- Se voce tem permissao `glue:GetPartitions` no AWS\n"
                "- Se a tabela esta registrada no Glue Catalog"
            )
        elif isinstance(e, CostGuardrailTriggered):
            st.error(f"Custo excedido: {e}")
        else:
            st.error(f"Erro ao consultar range temporal: {e}")
        st.stop()

    if date_range["n_periods"] == 0:
        st.warning("Nenhum periodo encontrado. Verifique a coluna temporal e o filtro base.")
    else:
        # Preencher reference_date com max_date da tabela
        _max = date_range.get("max_date")
        if _max:
            dataset_config.reference_date = str(_max)[:10]
            st.session_state["setup_config"] = dataset_config

        # Estimar volume e adaptar timeout para tabelas grandes
        svc = st.session_state["dataset_service"]
        estimated_rows = svc.estimate_volume_and_adapt_timeout(dataset_config)
        st.session_state["estimated_rows"] = estimated_rows

        st.success(
            f"Range: **{date_range['min_date']}** a **{date_range['max_date']}** "
            f"— **{date_range['n_periods']}** periodos distintos"
        )
        if estimated_rows > 10_000_000:
            st.info(
                f"Tabela grande: ~**{estimated_rows:,}** linhas no lookback. "
                f"Timeout adaptado automaticamente."
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

# --- Alerta de dados desatualizados ---
_max_date_str = date_range.get("max_date")
if _max_date_str:
    from datetime import date as _date_type, datetime as _datetime_type
    try:
        _max_date = _datetime_type.strptime(str(_max_date_str)[:10], "%Y-%m-%d").date()
        _days_ago = (_date_type.today() - _max_date).days
        if _days_ago > 7:
            st.info(
                f"A safra mais recente e de **{_max_date_str}** ({_days_ago} dias atras). "
                f"As queries usarao essa data como referencia para o lookback."
            )
        if _days_ago > 30:
            st.warning(
                f"A tabela nao recebe dados novos ha **{_days_ago} dias**. "
                f"Verifique se o pipeline de carga esta ativo."
            )
    except (ValueError, TypeError):
        pass  # max_date em formato nao-parseable, prosseguir normalmente

_n_periods = date_range.get("n_periods", 0)
if _n_periods > 0 and _n_periods < 7:
    st.caption(
        f"Serie curta: **{_n_periods} periodos** disponiveis. "
        f"Regras serao geradas com confianca reduzida. "
        f"Recomendamos recalibrar apos acumular mais historico."
    )


# ===================================================================
# STEP 5: Selecao de colunas para profiling
# ===================================================================

st.header("5. Colunas para Profiling")

dataset_config = st.session_state.get("setup_config", dataset_config)

# Excluir coluna temporal do profiling (ja usada como eixo)
all_col_names = [c["name"] for c in columns if c["name"] != date_col]

st.caption(
    "Desmarque colunas que nao precisam de regras de qualidade "
    "(IDs internos, timestamps de auditoria, etc). "
    "Menos colunas = profiling mais rapido e mais barato."
)

# Quick select/deselect
pf_c1, pf_c2, pf_c3 = st.columns(3)
with pf_c1:
    if st.button("Marcar todas", key="prof_sel_all"):
        for cn in all_col_names:
            st.session_state[f"prof_{cn}"] = True
        st.rerun()
with pf_c2:
    if st.button("Desmarcar todas", key="prof_desel_all"):
        for cn in all_col_names:
            st.session_state[f"prof_{cn}"] = False
        st.rerun()
with pf_c3:
    st.caption(f"{len(all_col_names)} colunas disponiveis")

# Column checkboxes
profiling_cols_selected = []
for col_info in columns:
    cname = col_info["name"]
    if cname == date_col:
        continue
    default = st.session_state.get(f"prof_{cname}", True)
    checked = st.checkbox(
        f"`{cname}` ({col_info['type']})",
        value=default,
        key=f"prof_{cname}",
    )
    if checked:
        profiling_cols_selected.append(col_info)

n_profiling = len(profiling_cols_selected)

# Cost guardrail
if n_profiling > 20:
    st.info(
        f"O profiling executara queries para **{n_profiling} colunas** "
        f"contra o Athena. Desmarque colunas desnecessarias para reduzir custo.",
        icon="💰",
    )

if n_profiling == 0:
    st.warning("Selecione pelo menos uma coluna para executar o profiling.")
    st.stop()

st.caption(f"**{n_profiling}** coluna(s) selecionada(s) para profiling.")

if st.button("Executar Profiling", type="primary"):
    client_id = _get_client_id()
    config_dict = {
        "schema": dataset_config.schema,
        "table": dataset_config.table,
        "partition_method": dataset_config.partition_method.value,
        "partition_column": dataset_config.partition_column,
        "partition_format": dataset_config.partition_format,
        "partition_is_integer": dataset_config.partition_is_integer,
        "date_column": dataset_config.date_column,
        "temporal_axis_column": dataset_config.temporal_axis_column,
        "date_expression": dataset_config.date_expression,
        "lookback_value": dataset_config.lookback_value,
        "grain_type": dataset_config.grain_type.value,
        "lookback_mode": dataset_config.lookback_mode.value,
        "base_filter_sql": dataset_config.base_filter_sql,
        "reference_date": dataset_config.reference_date,
        "date_filter_granularity": dataset_config.date_filter_granularity.value,
        "date_reference_strategy": dataset_config.date_reference_strategy.value,
        "date_reference_lag": dataset_config.date_reference_lag,
        "gdq_date_filter_expr": dataset_config.gdq_date_filter_expr,
        "gdq_date_filter_format": dataset_config.gdq_date_filter_format,
    }

    _BATCH_THRESHOLD = 20
    _MAX_PROFILING_SAMPLE = 30
    _profiling_sample = min(lookback_value, _MAX_PROFILING_SAMPLE)

    try:
        if n_profiling <= _BATCH_THRESHOLD:
            # Batch: 1 query para todas as colunas
            with st.spinner(f"Profiling {n_profiling} colunas (batch)..."):
                _col_names = tuple(c["name"] for c in profiling_cols_selected)
                _col_types = tuple(c["type"] for c in profiling_cols_selected)
                profiles = _cached_batch_profile(
                    client_id, config_dict,
                    _col_names, _col_types,
                    _profiling_sample,
                )
        else:
            # Per-column: progress bar individual (tabelas grandes)
            profiles = []
            progress = st.progress(0, text="Classificando colunas...")
            for i, col_info in enumerate(profiling_cols_selected):
                progress.progress(
                    (i + 1) / n_profiling,
                    text=f"Classificando {col_info['name']}...",
                )
                profile_list = _cached_profile_column(
                    client_id, config_dict,
                    col_info["name"], col_info["type"],
                    _profiling_sample,
                )
                profiles.extend(profile_list)
            progress.empty()
    except Exception as e:
        from infra.cost_guard import CostGuardrailTriggered
        if isinstance(e, CostGuardrailTriggered):
            st.error(f"Custo excedido: {e}")
        else:
            st.error(
                f"Erro no profiling: {e}\n\n"
                "O profiling falhou. Verifique a configuracao da tabela, "
                "eixo temporal e permissoes no Athena."
            )
        st.stop()

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

st.header("6. Classificacao e Selecao Final")

st.caption(
    "Revise a classificacao inferida e selecione as colunas para analise. "
    "Use o dropdown para alterar o tipo semantico se a inferencia estiver incorreta."
)

with st.expander("Como funciona a classificacao?", expanded=False):
    st.markdown(
        "O profiling analisa o tipo Athena e amostra de valores para inferir o tipo semantico:\n\n"
        "- **Numerico:** colunas int/double/float, ou strings com >95% dos valores castaveis para numero. "
        "Geram regras **Mean** e **StdDev**.\n"
        "- **Categorico (low):** ate ~50 valores distintos — dominio fixo (ex: UF, tipo_operacao). "
        "Geram regras **ColumnValues** e **CustomSql**.\n"
        "- **Categorico (mid/high):** muitos distintos — tipicamente IDs ou texto livre.\n"
        "- **Data/hora:** colunas date/timestamp — usadas como eixo temporal.\n\n"
        "Desmarque colunas que nao precisam de regras (IDs, timestamps internos, etc.). "
        "Voce pode alterar o tipo manualmente usando o dropdown."
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
            st.warning(w)

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
# STEP 6b: Chave Primaria (opcional)
# ===================================================================

st.subheader("Chave Primaria (opcional)")
st.caption(
    "Selecione as colunas que formam a chave primaria ou chave unica da tabela. "
    "A ferramenta analisara unicidade e completude historica dessas colunas."
)

# Options: all column names from the validated table (not just profiled ones)
_pk_all_col_names = [c["name"] for c in columns]

pk_columns = st.multiselect(
    "Colunas da chave primaria:",
    options=_pk_all_col_names,
    default=st.session_state.get("setup_pk_columns", []),
    key="pk_columns_select",
    help=(
        "Colunas que juntas identificam unicamente cada registro. "
        "Deixe vazio se nao aplicavel. "
        "Gera regra IsPrimaryKey na analise."
    ),
)
st.session_state["setup_pk_columns"] = pk_columns


# ===================================================================
# STEP 7: Ativar configuracao (e opcionalmente salvar preset)
# ===================================================================

st.header("7. Ativar Configuracao")
st.caption(
    "Ao ativar, a configuracao sera salva na sessao e voce podera "
    "calibrar regras na pagina Explore."
)

dataset_config.selected_columns = selected_cols
dataset_config.unique_key_columns = st.session_state.get("setup_pk_columns", [])

col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    if st.button(
        "Ativar e ir para Explore",
        type="primary",
        disabled=not selected_cols,
    ):
        st.session_state["setup_config"] = dataset_config
        _activate_config()
        st.switch_page("pages/02_explore.py")

with col_btn2:
    save_preset = st.checkbox("Salvar como preset", value=False)

if save_preset:
    from services.preset_manager import PresetManager, Preset, PresetMetadata, serialize_profiles

    preset_name = st.text_input(
        "Nome do preset:",
        value=f"{schema}_{table}",
        help="Sera salvo em presets/<nome>.json",
    )
    preset_notes = st.text_input(
        "Notas (opcional):",
        placeholder="Ex: config para validacao mensal",
        help="Anotacoes livres sobre este preset.",
    )

    _save_col1, _save_col2 = st.columns(2)

    with _save_col1:
        if st.button("Salvar Preset", disabled=not selected_cols):
            mgr = PresetManager(app_config.preset_dir)
            preset_obj = Preset(
                name=preset_name,
                schema=dataset_config.schema,
                table=dataset_config.table,
                partition_method=dataset_config.partition_method.value,
                partition_column=dataset_config.partition_column,
                partition_format=dataset_config.partition_format,
                partition_is_integer=dataset_config.partition_is_integer,
                temporal_axis_column=dataset_config.temporal_axis_column,
                partition_columns=dataset_config.partition_columns,
                partition_formats=dataset_config.partition_formats,
                partition_is_integer_map=dataset_config.partition_is_integer_map,
                date_column=dataset_config.date_column,
                grain_type=dataset_config.grain_type.value,
                lookback_mode=dataset_config.lookback_mode.value,
                lookback_value=dataset_config.lookback_value,
                date_expression=dataset_config.date_expression,
                date_filter_granularity=dataset_config.date_filter_granularity.value,
                date_reference_strategy=dataset_config.date_reference_strategy.value,
                date_reference_lag=dataset_config.date_reference_lag,
                gdq_date_filter_expr=dataset_config.gdq_date_filter_expr,
                gdq_date_filter_format=dataset_config.gdq_date_filter_format,
                base_filter_sql=dataset_config.base_filter_sql,
                selected_columns=dataset_config.selected_columns,
                unique_key_columns=dataset_config.unique_key_columns,
                overrides={k: v.value for k, v in overrides.items()},
                date_range=date_range,
                column_profiles=serialize_profiles(
                    st.session_state.get("setup_profiles", [])
                ),
                profiles_cached_at=datetime.now(timezone.utc).isoformat()[:19],
                metadata=PresetMetadata(notes=preset_notes),
            )
            preset_path = mgr.save(preset_obj)
            st.success(f"Preset salvo em `{preset_path}`")

    with _save_col2:
        if preset_files and st.button("Clonar de existente", disabled=not selected_cols):
            st.session_state["show_clone_ui"] = True

    if st.session_state.get("show_clone_ui") and preset_files:
        clone_source = st.selectbox(
            "Clonar de:", [p.stem for p in preset_files], key="clone_source"
        )
        if st.button("Clonar", key="clone_confirm"):
            mgr = PresetManager(app_config.preset_dir)
            mgr.clone(clone_source, preset_name, notes=preset_notes)
            st.success(f"Preset **{preset_name}** clonado de **{clone_source}**")
            st.session_state.pop("show_clone_ui", None)
            st.rerun()


# Status bar: mostrar se config esta ativa
if "dataset_config" in st.session_state:
    cfg = st.session_state["dataset_config"]
    n_sel = len(cfg.selected_columns) if cfg.selected_columns else 0
    st.sidebar.success(
        f"Config ativa: `{cfg.schema}.{cfg.table}` ({n_sel} colunas)"
    )
else:
    st.sidebar.info("Nenhuma config ativa.")

# Query log no sidebar (se client disponivel)
if "client" in st.session_state:
    _client = st.session_state["client"]
    _entries = _client.logger.entries
    if _entries:
        with st.sidebar.expander(f"Queries executadas ({len(_entries)})"):
            for _e in reversed(_entries[-10:]):
                _status = ":red[ERRO]" if _e.exception_type else ":green[OK]"
                _col_label = f".{_e.column}" if _e.column else ""
                st.caption(
                    f"{_status} **{_e.query_name}**{_col_label} "
                    f"— {_e.rows_returned} rows, {_e.elapsed_ms}ms"
                )
                if _e.sql:
                    st.code(_e.sql, language="sql")
