"""
GDQ Rule Proposer — Entry point Streamlit.

Dashboard com overview do projeto, metricas da sessao e navegacao guiada.
"""

import os
import subprocess

import streamlit as st

from config import load_config
from infra.athena_client import AthenaClient
from pages.components.breadcrumb import render_breadcrumb
from pages.components.theme import inject_global_css

__version__ = "1.0.0"

def get_client() -> AthenaClient:
    """Get or create a cached AthenaClient in session_state."""
    if "client" not in st.session_state:
        config = load_config()
        st.session_state["config"] = config
        st.session_state["client"] = AthenaClient(config)
    return st.session_state["client"]



# ---------------------------------------------------------------------------
# Sidebar (environment-aware)
# ---------------------------------------------------------------------------

def render_sidebar():
    config = st.session_state.get("config")

    st.sidebar.title("GDQ Rule Proposer")
    st.sidebar.caption(f"v{__version__}")
    st.sidebar.divider()

    # Utility links
    if st.sidebar.button("Query Log", key="sidebar_qlog", help="Historico de queries da sessao"):
        st.switch_page("pages/07_query_log.py")
    if st.sidebar.button("Diagnostico", key="sidebar_diag", help="Verificar status do ambiente"):
        st.switch_page("pages/06_diagnostico.py")

    if not config:
        return

    # Active config indicator
    if "dataset_config" in st.session_state:
        cfg = st.session_state["dataset_config"]
        n_sel = len(cfg.selected_columns) if cfg.selected_columns else 0
        st.sidebar.divider()
        st.sidebar.success(f"Config ativa: `{cfg.schema}.{cfg.table}` ({n_sel} colunas)")
        n_cart = len(st.session_state.get("rule_cart", []))
        if n_cart:
            st.sidebar.caption(f"Carrinho: {n_cart} regra(s)")


# ---------------------------------------------------------------------------
# Main page — Dashboard
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="GDQ Rule Proposer",
        page_icon=":shield:",
        layout="wide",
    )
    inject_global_css()

    # Init client + health check real
    try:
        client = get_client()
        # Testar conexao real (apenas uma vez por sessao)
        if not st.session_state.get("_health_check_done"):
            client.health_check()
            st.session_state["_health_check_done"] = True
        connection_ok = True
        connection_error = None
    except Exception as e:
        connection_ok = False
        connection_error = str(e)
        client = None
        # Limpar estado para re-testar na proxima tentativa
        st.session_state.pop("_health_check_done", None)
        st.session_state.pop("client", None)
        # Limpar services que cacheiam referencia ao client antigo
        for _svc_key in ("dataset_service", "profiling_service", "analysis_service"):
            st.session_state.pop(_svc_key, None)

    render_sidebar()

    config = st.session_state.get("config")

    # --- Header ---
    header_col, status_col = st.columns([4, 1])
    with header_col:
        st.title("GDQ Rule Proposer")
        render_breadcrumb("Dashboard")
        st.caption(
            f"v{__version__} — Proposta automatica de regras AWS Glue Data Quality"
        )
    with status_col:
        if connection_ok:
            st.success("Conectado")
        else:
            st.error("Desconectado")

    if not connection_ok:
        st.error(
            f"Falha na conexao: {connection_error}"
        )

        # Detectar profile e região para diagnóstico
        profile = ""
        region = ""
        try:
            cfg = load_config()
            profile = cfg.athena.aws_profile
            region = cfg.athena.region
        except Exception:
            profile = os.environ.get("GDQ_AWS_PROFILE", "")
            region = os.environ.get("AWS_DEFAULT_REGION", "")

        is_auth_error = any(
            kw in (connection_error or "").lower()
            for kw in ["expirad", "credenci", "token", "expired", "invalid", "autenticacao"]
        )

        # --- Diagnóstico automático ---
        with st.expander("Diagnostico de conexao", expanded=True):
            diag_col1, diag_col2 = st.columns(2)

            with diag_col1:
                st.markdown("**Configuracao do app**")
                st.markdown(f"- Profile: `{profile or '(nao configurado)'}`")
                st.markdown(f"- Regiao: `{region or '(nao configurada)'}`")

                # Verificar .env
                _env_path = os.path.join(os.path.dirname(__file__), ".env")
                _env_exists = os.path.exists(_env_path)
                st.markdown(f"- Arquivo .env: {'encontrado' if _env_exists else ':red[nao encontrado]'}")

            with diag_col2:
                st.markdown("**Verificacao de credenciais**")

                # Testar aws sts get-caller-identity
                _sts_ok = False
                _sts_msg = ""
                try:
                    _sts_cmd = ["aws", "sts", "get-caller-identity"]
                    if profile:
                        _sts_cmd += ["--profile", profile]
                    _sts_result = subprocess.run(
                        _sts_cmd, capture_output=True, text=True, timeout=15,
                    )
                    if _sts_result.returncode == 0:
                        _sts_ok = True
                        import json as _json
                        try:
                            _sts_data = _json.loads(_sts_result.stdout)
                            _sts_msg = f"ARN: `{_sts_data.get('Arn', '?')}`"
                        except Exception:
                            _sts_msg = "OK (identidade confirmada)"
                    else:
                        _sts_msg = f"Falhou: {_sts_result.stderr.strip()[:100]}"
                except FileNotFoundError:
                    _sts_msg = "AWS CLI nao encontrado"
                except subprocess.TimeoutExpired:
                    _sts_msg = "Timeout (possivel problema de rede)"
                except Exception as _e:
                    _sts_msg = f"Erro: {_e}"

                if _sts_ok:
                    st.markdown(f"- `aws sts get-caller-identity`: :green[OK]")
                    st.markdown(f"  {_sts_msg}")
                else:
                    st.markdown(f"- `aws sts get-caller-identity`: :red[FALHOU]")
                    st.markdown(f"  {_sts_msg}")

                # Verificar região do profile
                try:
                    _region_cmd = ["aws", "configure", "get", "region"]
                    if profile:
                        _region_cmd += ["--profile", profile]
                    _region_result = subprocess.run(
                        _region_cmd, capture_output=True, text=True, timeout=5,
                    )
                    _profile_region = _region_result.stdout.strip()
                    if _profile_region:
                        _region_match = _profile_region == region
                        _icon = ":green[OK]" if _region_match else ":red[DIFERENTE]"
                        st.markdown(f"- Regiao do profile: `{_profile_region}` {_icon}")
                        if not _region_match:
                            st.markdown(f"  App usa `{region}`, profile usa `{_profile_region}`")
                    else:
                        st.markdown("- Regiao do profile: :orange[nao configurada]")
                except Exception:
                    pass

            # Diagnóstico contextual
            if _sts_ok and is_auth_error:
                st.warning(
                    "As credenciais AWS estao validas no terminal, mas o app falhou. "
                    "Isso geralmente acontece porque o app cacheou uma conexao antiga. "
                    "Clique **Tentar reconectar** abaixo."
                )
            elif not _sts_ok:
                st.info(
                    f"Execute no terminal: `aws sso login --profile {profile}`\n\n"
                    f"Depois clique **Tentar reconectar**."
                )

        btn_col1, btn_col2, btn_col3 = st.columns(3)

        with btn_col1:
            if is_auth_error and profile:
                if st.button(f"Fazer login AWS (SSO)", type="primary", key="sso_login"):
                    with st.spinner(f"Executando: aws sso login --profile {profile} ..."):
                        try:
                            result = subprocess.run(
                                ["aws", "sso", "login", "--profile", profile],
                                capture_output=True,
                                text=True,
                                timeout=120,
                            )
                            if result.returncode == 0:
                                st.session_state.pop("_health_check_done", None)
                                st.session_state.pop("client", None)
                                for _k in ("dataset_service", "profiling_service", "analysis_service"):
                                    st.session_state.pop(_k, None)
                                st.success("Login realizado! Recarregando...")
                                st.rerun()
                            else:
                                st.error(
                                    f"Falha no login. Execute manualmente no terminal:\n"
                                    f"`aws sso login --profile {profile}`"
                                )
                        except subprocess.TimeoutExpired:
                            st.warning(
                                "Timeout aguardando login. Execute manualmente no terminal:\n"
                                f"`aws sso login --profile {profile}`"
                            )
                        except FileNotFoundError:
                            st.error("AWS CLI nao encontrado. Instale primeiro.")

        with btn_col2:
            if st.button("Tentar reconectar", type="primary" if not is_auth_error else "secondary", key="retry_conn"):
                st.session_state.pop("_health_check_done", None)
                st.session_state.pop("client", None)
                for _k in ("dataset_service", "profiling_service", "analysis_service"):
                    st.session_state.pop(_k, None)
                st.rerun()

        with btn_col3:
            if st.button("Abrir Diagnostico", key="diag_on_error"):
                st.switch_page("pages/06_diagnostico.py")

        st.stop()

    # --- Metric cards ---
    n_cart = len(st.session_state.get("rule_cart", []))
    has_config = "dataset_config" in st.session_state

    # Cost from query logger
    summary = client.logger.get_session_summary()
    if summary["estimated_cost_usd"] > 0:
        cost_str = f"${summary['estimated_cost_usd']:.4f}"
        cost_help = (
            f"{summary['total_queries']} queries, "
            f"{summary['cache_hits']} cache hits, "
            f"${summary['estimated_cost_usd']:.4f} estimado"
        )
    elif summary["total_queries"] > 0:
        cost_str = "$0.0000"
        cost_help = (
            f"{summary['total_queries']} queries executadas "
            f"({summary['cache_hits']} cache hits Athena, 0 bytes escaneados)"
        )
    else:
        cost_str = "$0.00"
        cost_help = "Nenhuma query executada nesta sessao"

    m1, m2 = st.columns(2)
    with m1:
        st.metric("Regras no carrinho", n_cart)
    with m2:
        st.metric("Custo da sessao", cost_str, help=cost_help)

    st.divider()

    # --- "Como funciona" — 4 steps ---
    st.subheader("Como funciona")

    s1, s2, s3, s4, s5 = st.columns(5)

    with s1:
        st.markdown("### 1. Setup")
        st.markdown(
            "Configure a **tabela**, o **eixo temporal** e selecione as **colunas** "
            "para analise."
        )
        if st.button("Ir para Setup", type="primary", key="nav_setup"):
            st.switch_page("pages/01_setup.py")

    with s2:
        st.markdown("### 2. Explore")
        st.markdown(
            "Calibre regras com graficos interativos e **backtest** em tempo real."
        )
        if has_config:
            if st.button("Ir para Explore", key="nav_explore"):
                st.switch_page("pages/02_explore.py")
        else:
            st.caption("Configure o Setup primeiro.")

    with s3:
        st.markdown("### 3. Review")
        st.markdown(
            "Revise as regras, valide a **sintaxe GDQ** e **exporte** para arquivo."
        )
        if n_cart > 0:
            if st.button("Ir para Review", key="nav_review"):
                st.switch_page("pages/03_review.py")
        else:
            st.caption("Adicione regras no Explore primeiro.")

    with s4:
        st.markdown("### 4. Teste")
        st.markdown(
            "Teste as regras via **Glue job Thundera** antes de implantar."
        )
        if n_cart > 0:
            if st.button("Ir para Teste", key="nav_test"):
                st.switch_page("pages/04_test.py")
        else:
            st.caption("Adicione regras no Explore primeiro.")

    with s5:
        st.markdown("### 5. Ajuda")
        st.markdown(
            "Documentacao completa, conceitos e **glossario**."
        )
        if st.button("Ver Ajuda", key="nav_help"):
            st.switch_page("pages/05_help.py")

    st.divider()

    # --- Active config section OR quick start ---
    if has_config:
        cfg = st.session_state["dataset_config"]
        profiles = st.session_state.get("column_profiles", [])

        st.subheader("Configuracao ativa")

        from core.models.enums import SemanticType

        n_sel = len(cfg.selected_columns) if cfg.selected_columns else 0
        n_num = sum(
            1 for p in profiles
            if p.effective_type == SemanticType.NUMERIC
            and p.column_name in set(cfg.selected_columns or [])
        )
        n_cat = sum(
            1 for p in profiles
            if p.is_categorical
            and p.column_name in set(cfg.selected_columns or [])
        )

        info_c1, info_c2, info_c3, info_c4 = st.columns(4)
        info_c1.markdown(f"**Tabela:** `{cfg.schema}.{cfg.table}`")
        info_c2.markdown(f"**Colunas:** {n_sel} ({n_num} num, {n_cat} cat)")
        info_c3.markdown(f"**Lookback:** {cfg.lookback_value} periodos")
        info_c4.markdown(f"**Particao:** {cfg.partition_method.value}")

        if cfg.base_filter_sql:
            st.caption(f"Filtro: `{cfg.base_filter_sql}`")

        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("Continuar analise", type="primary", key="continue_explore"):
                st.switch_page("pages/02_explore.py")
        with btn_c2:
            if n_cart > 0:
                if st.button(f"Revisar {n_cart} regra(s)", key="continue_review"):
                    st.switch_page("pages/03_review.py")

    else:
        st.subheader("Inicio rapido")

        st.markdown(
            "Bem-vindo ao **GDQ Rule Proposer**. Esta ferramenta analisa o historico "
            "de dados de uma tabela e propoe regras de qualidade prontas para o "
            "AWS Glue Data Quality."
        )

        st.markdown(
            "- Conecta ao **Amazon Athena** para consultar dados agregados (sem trazer dados brutos)\n"
            "- Propoe regras dinamicas (**Mean**, **StdDev**, **RowCount**, **Percentil**) "
            "e estaticas (**AllowedValues**, **DistinctCount**, **Frequencia**)\n"
            "- Todas as regras passam por **backtest** no historico antes de serem sugeridas\n"
            "- A sintaxe GDQ gerada e validada e pode ser exportada diretamente"
        )

        if st.button("Comecar configuracao", type="primary", key="quick_start"):
            st.switch_page("pages/01_setup.py")


if __name__ == "__main__":
    main()
