"""
Pagina 04 — Teste: Execucao de regras via Thundera (Glue DQ).

Constroi o payload JSON para o Glue job Thundera, permite edicao
dos campos classificatorios e dispara o teste das regras exportadas.
Inclui parsing de logs para exibir resultados por regra.
"""

import json

import streamlit as st

from core.models.enums import get_rule_label


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Teste - GDQ Rule Proposer", page_icon=":test_tube:")

st.title("Teste via Thundera")
st.caption(
    "Execute as regras do carrinho em um Glue job de teste (Thundera) "
    "para validar o comportamento antes de implantar em producao."
)

# Config summary
if "dataset_config" in st.session_state:
    cfg = st.session_state["dataset_config"]
    st.caption(
        f"Tabela: `{cfg.schema}.{cfg.table}` · "
        f"Lookback: {cfg.lookback_value}p"
    )

# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

if "dataset_config" not in st.session_state:
    st.info(
        "Configure uma tabela na pagina **Setup** antes de testar."
    )
    if st.button("Ir para Setup"):
        st.switch_page("pages/01_setup.py")
    st.stop()

if "rule_cart" not in st.session_state or not st.session_state["rule_cart"]:
    st.info(
        "Carrinho vazio. Adicione regras na pagina **Explore** "
        "e revise na pagina **Review** antes de testar."
    )
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        if st.button("Ir para Explore"):
            st.switch_page("pages/02_explore.py")
    with col_g2:
        if st.button("Ir para Review"):
            st.switch_page("pages/03_review.py")
    st.stop()

dataset_config = st.session_state["dataset_config"]
cart = st.session_state["rule_cart"]
enabled_rules = [s for s in cart if s.enabled and s.final_gdq_syntax.strip()]

if not enabled_rules:
    st.warning(
        "Nenhuma regra habilitada no carrinho. "
        "Habilite ao menos uma regra na pagina **Review**."
    )
    if st.button("Ir para Review "):
        st.switch_page("pages/03_review.py")
    st.stop()


# ---------------------------------------------------------------------------
# Dynamic rules warning
# ---------------------------------------------------------------------------

_has_dynamic = any("last(" in s.final_gdq_syntax.lower() for s in enabled_rules)
if _has_dynamic:
    st.info(
        "Regras dinamicas (com `last(N)`) dependem de historico interno do GDQ. "
        "Na **primeira execucao**, essas regras geralmente falham porque o GDQ "
        "ainda nao tem dados acumulados. Execute pelo menos **2 vezes** para "
        "validar o comportamento real.",
        icon="ℹ️",
    )


# ---------------------------------------------------------------------------
# 1. Resumo das regras
# ---------------------------------------------------------------------------

st.header("1. Regras para teste")

# Extract unique columns
columns_set: set[str] = set()
for sel in enabled_rules:
    p = sel.proposal
    if p.target_column:
        from core.models.enums import RuleType
        if p.rule_type == RuleType.IS_PRIMARY_KEY:
            columns_set.update(p.target_column.split())
        else:
            columns_set.add(p.target_column)

columns_sorted = sorted(columns_set)

m1, m2, m3 = st.columns(3)
with m1:
    st.metric("Regras habilitadas", len(enabled_rules))
with m2:
    st.metric("Colunas referenciadas", len(columns_sorted))
with m3:
    st.metric("Tabela", f"{dataset_config.schema}.{dataset_config.table}")

with st.expander(f"Regras ({len(enabled_rules)})", expanded=False):
    for sel in enabled_rules:
        p = sel.proposal
        label = get_rule_label(p.rule_type)
        target = p.target_column or "(tabela)"
        st.markdown(f"- **{label}** — `{target}`")
        st.caption(f"  `{sel.final_gdq_syntax[:120]}{'...' if len(sel.final_gdq_syntax) > 120 else ''}`")


# ---------------------------------------------------------------------------
# 2. Campos classificatorios
# ---------------------------------------------------------------------------

st.header("2. Campos classificatorios")
st.caption(
    "Preencha os campos classificatorios do payload Thundera. "
    "Valores default podem ser configurados via variaveis de ambiente "
    "(GDQ_SQUAD, GDQ_RACF, GDQ_COMUNIDADE)."
)

# Load defaults from config
app_config = st.session_state.get("config")
if app_config:
    glue_cfg = app_config.glue_test
else:
    from config import load_config
    app_config = load_config()
    glue_cfg = app_config.glue_test

col_c1, col_c2 = st.columns(2)

with col_c1:
    squad = st.text_input(
        "Squad",
        value=st.session_state.get("thundera_squad", glue_cfg.default_squad),
        key="thundera_squad_input",
        help="Nome do squad responsavel pela tabela.",
    )
    comunidade = st.text_input(
        "Comunidade",
        value=st.session_state.get("thundera_comunidade", glue_cfg.default_comunidade),
        key="thundera_comunidade_input",
        help="Nome da comunidade de dados.",
    )
    racf = st.text_input(
        "RACF",
        value=st.session_state.get("thundera_racf", glue_cfg.default_racf),
        key="thundera_racf_input",
        help="Identificador do usuario (login corporativo).",
    )
    cod_regr = st.text_input(
        "Codigo do Evento/Regra",
        value=st.session_state.get("thundera_cod_regr", ""),
        key="thundera_cod_regr_input",
        help="Codigo identificador unico do evento de credito (COD_REGR_EVEN_CRED).",
    )

with col_c2:
    periodicidade = st.selectbox(
        "Periodicidade",
        options=["D", "S", "M"],
        index=["D", "S", "M"].index(
            st.session_state.get("thundera_periodicidade", glue_cfg.default_periodicidade)
        ),
        key="thundera_periodicidade_input",
        help="D=Diario, S=Semanal, M=Mensal.",
    )
    tipo_qualidade = st.selectbox(
        "Tipo de Qualidade",
        options=["POUSADO", "STREAMING"],
        index=0,
        key="thundera_tipo_qualidade_input",
        help="POUSADO (batch) ou STREAMING (tempo real).",
    )
    status_regra = st.selectbox(
        "Status da Regra",
        options=["ATIVA", "INATIVA"],
        index=0,
        key="thundera_status_regra_input",
        help="Status da regra no pipeline.",
    )
    nome_orig = st.selectbox(
        "Origem da Tabela",
        options=["AWS", "ON_PREM", "CLOUD"],
        index=0,
        key="thundera_nome_orig_input",
        help="Origem da tabela (NOME_ORIG_TABLEA).",
    )


# ---------------------------------------------------------------------------
# 3. Processamento
# ---------------------------------------------------------------------------

st.header("3. Processamento")

col_p1, col_p2 = st.columns(2)

with col_p1:
    nome_glue_job = st.text_input(
        "Nome do Glue Job",
        value=st.session_state.get("thundera_job_name", glue_cfg.glue_job_name),
        key="thundera_job_name_input",
        help="Nome do Glue job Thundera na conta AWS.",
    )
    conta = st.text_input(
        "Conta",
        value=st.session_state.get("thundera_conta", glue_cfg.default_conta),
        key="thundera_conta_input",
        help="Conta de processamento (PROCESSAMENTO.CONTA).",
    )

with col_p2:
    timeout = st.text_input(
        "Timeout (minutos)",
        value=st.session_state.get("thundera_timeout", glue_cfg.default_timeout),
        key="thundera_timeout_input",
        help="Timeout do job em minutos.",
    )
    workers = st.text_input(
        "Workers",
        value=st.session_state.get("thundera_workers", glue_cfg.default_workers),
        key="thundera_workers_input",
        help="Numero de workers do Glue job.",
    )


# ---------------------------------------------------------------------------
# 4. Opcoes avancadas
# ---------------------------------------------------------------------------

with st.expander("Opcoes avancadas", expanded=False):
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        infer_schema = st.checkbox(
            "Inferir schema",
            value=False,
            key="thundera_infer_schema",
            help="Se marcado, o Thundera infere o schema automaticamente.",
        )
        iceberg = st.checkbox(
            "Tabela Iceberg",
            value=False,
            key="thundera_iceberg",
            help="Marque se a tabela usa formato Apache Iceberg.",
        )
    with col_a2:
        delay_processamento = st.number_input(
            "Delay (minutos)",
            min_value=0,
            max_value=1440,
            value=0,
            key="thundera_delay",
            help="Delay em minutos antes do processamento.",
        )
        release_train = st.text_input(
            "Release Train",
            value="",
            key="thundera_release_train",
            help="Release train (opcional).",
        )

    # Partition columns
    default_partitions = []
    if dataset_config.partition_column:
        default_partitions = [dataset_config.partition_column]

    particao_str = st.text_input(
        "Colunas de particao (separadas por virgula)",
        value=", ".join(default_partitions),
        key="thundera_particao",
        help="Colunas de particao da tabela. Pre-preenchido a partir do Setup.",
    )
    particoes_evento = st.text_input(
        "Particoes de evento",
        value="",
        key="thundera_particoes_evento",
        help="Filtro adicional de particoes de evento (opcional).",
    )


# ---------------------------------------------------------------------------
# 5. Build payload + JSON preview
# ---------------------------------------------------------------------------

st.header("4. Payload JSON")

# Build classificatory dict from form
classificatory = {
    "squad": squad,
    "comunidade": comunidade,
    "racf": racf,
    "periodicidade": periodicidade,
    "tipo_qualidade": tipo_qualidade,
    "status_regra": status_regra,
    "nome_orig_tablea": nome_orig,
    "cod_regr_even_cred": cod_regr,
    "release_train": release_train,
    "nome_glue_job": nome_glue_job,
    "conta": conta,
    "timeout": timeout,
    "workers": workers,
    "infer_schema": infer_schema,
    "iceberg": iceberg,
    "delay_processamento": delay_processamento,
    "particoes_evento": particoes_evento,
}

# Parse partition columns
partition_columns = []
if particao_str.strip():
    partition_columns = [p.strip() for p in particao_str.split(",") if p.strip()]

# Build payload using service
from services.glue_test_service import GlueTestService
from infra.glue_client import GlueClient

glue_client = GlueClient(app_config)
glue_svc = GlueTestService(glue_client, app_config)

payload = glue_svc.build_payload(
    dataset_config=dataset_config,
    selections=enabled_rules,
    classificatory=classificatory,
    partition_columns=partition_columns if partition_columns else None,
)

# Show JSON
json_str = payload.to_json(indent=2)

st.code(json_str, language="json")
st.caption(f"{len(enabled_rules)} regras · {len(columns_sorted)} colunas · {len(json_str)} caracteres")

col_d1, col_d2 = st.columns(2)
with col_d1:
    st.download_button(
        label="Baixar payload.json",
        data=json_str,
        file_name="thundera_payload.json",
        mime="application/json",
        type="primary",
    )
with col_d2:
    st.caption(
        "Voce tambem pode copiar o JSON acima usando o icone de copia "
        "no canto superior direito do bloco de codigo."
    )


# ---------------------------------------------------------------------------
# 6. Executar teste
# ---------------------------------------------------------------------------

st.header("5. Executar teste")

st.caption(
    "Dispara o Glue job com o payload acima e acompanha o status "
    "ate a conclusao. Requer permissoes `glue:StartJobRun` e `glue:GetJobRun` "
    "no perfil AWS ativo."
)

# Validation
validation_errors = []
if not nome_glue_job.strip():
    validation_errors.append("Nome do Glue job e obrigatorio.")
if not payload.regras_gdq:
    validation_errors.append("Nenhuma regra GDQ no payload.")

if validation_errors:
    for err in validation_errors:
        st.error(err)

run_disabled = bool(validation_errors)

# Execution lock: prevent double-run and persist across page navigation
_run_state = st.session_state.get("glue_run_state", "idle")  # idle | running | done
_run_result = st.session_state.get("glue_run_result")

if _run_state == "running":
    st.warning(
        "Uma execucao esta em andamento. Aguarde a conclusao antes de disparar outra.",
        icon="⏳",
    )
    run_disabled = True

if _run_state != "running" and st.button(
    "Executar teste",
    type="primary",
    disabled=run_disabled,
    help="Dispara o Glue job Thundera com o payload configurado.",
):
    st.session_state["glue_run_state"] = "running"
    st.session_state["glue_run_result"] = None

    with st.status("Executando teste...", expanded=True) as status:
        def on_status(state, msg):
            st.write(msg)

        try:
            result = glue_svc.run_test(payload, on_status=on_status)

            st.session_state["glue_run_state"] = "done"
            st.session_state["glue_run_result"] = result
            st.session_state["glue_run_execution_num"] = st.session_state.get("glue_run_execution_num", 0) + 1

            if result.status == "SUCCEEDED":
                status.update(label="Teste concluido com sucesso!", state="complete")
            elif result.status == "TIMEOUT":
                status.update(label="Teste excedeu timeout", state="error")
            else:
                status.update(label=f"Teste finalizado: {result.status}", state="error")

        except Exception as e:
            st.session_state["glue_run_state"] = "done"
            status.update(label="Erro na execucao", state="error")
            st.error(f"Erro ao executar teste: {e}")

    st.rerun()

# Reset button
if _run_state == "done":
    if st.button("Nova execucao", help="Libera para uma nova execucao do teste."):
        st.session_state["glue_run_state"] = "idle"
        st.session_state["glue_run_result"] = None
        st.rerun()

# Show persisted result
if _run_state == "done" and _run_result:
    result = _run_result
    exec_num = st.session_state.get("glue_run_execution_num", 1)

    if result.status == "SUCCEEDED":
        st.success(f"Execucao #{exec_num} concluida com sucesso ({result.duration_seconds}s)")
    elif result.status == "TIMEOUT":
        st.error(f"Execucao #{exec_num}: timeout ({result.error_message})")
    else:
        st.error(f"Execucao #{exec_num}: {result.status} — {result.error_message or 'Sem detalhes'}")

    with st.expander("Detalhes da execucao", expanded=False):
        st.markdown(f"- **Run ID:** `{result.run_id}`")
        st.markdown(f"- **Job:** `{result.job_name}`")
        st.markdown(f"- **Status:** `{result.status}`")
        st.markdown(f"- **Inicio:** `{result.started_at}`")
        st.markdown(f"- **Fim:** `{result.completed_at}`")
        st.markdown(f"- **Duracao:** {result.duration_seconds}s")
        if result.error_message:
            st.markdown(f"- **Erro:** {result.error_message}")


# ---------------------------------------------------------------------------
# 7. Resultados por regra (parsed de logs)
# ---------------------------------------------------------------------------

st.header("6. Resultados por regra")

st.caption(
    "Cole o log do Glue job abaixo para visualizar o resultado individual "
    "de cada regra. O parser extrai automaticamente os resultados GDQ "
    "do output do Thundera."
)

log_input = st.text_area(
    "Log do Glue job",
    height=200,
    key="glue_log_input",
    placeholder="Cole aqui o log completo do Glue job (CloudWatch ou console)...",
    help="Copie o log do CloudWatch Logs do Glue job e cole aqui. "
         "O parser identifica os blocos 'Resultados GDQ' e 'BookQualidades'.",
)

if log_input.strip():
    from core.glue_log_parser import parse_glue_log

    rule_results = parse_glue_log(log_input)

    if not rule_results:
        st.warning(
            "Nenhum resultado de regra encontrado no log. "
            "Verifique se o log contem a linha 'Resultados GDQ:' ou 'BookQualidades:Salvando'."
        )
    else:
        # Summary metrics
        n_total = len(rule_results)
        n_passed = sum(1 for r in rule_results if r.passed)
        n_failed = n_total - n_passed

        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.metric("Total de regras", n_total)
        with mc2:
            st.metric("Aprovadas", n_passed)
        with mc3:
            st.metric("Reprovadas", n_failed)

        if n_failed > 0 and _has_dynamic:
            _exec_num = st.session_state.get("glue_run_execution_num", 1)
            if _exec_num <= 1:
                st.info(
                    f"{n_failed} regra(s) reprovada(s). Se esta e a **primeira execucao**, "
                    "regras dinamicas (`last(N)`) falham por falta de historico interno. "
                    "Execute novamente para validar.",
                    icon="ℹ️",
                )

        st.divider()

        # Results table — failed first, then passed
        sorted_results = sorted(rule_results, key=lambda r: (r.passed, r.rule_label))

        for r in sorted_results:
            status_icon = "✅" if r.passed else "❌"
            outcome_label = "Aprovada" if r.passed else "Reprovada"

            with st.container(border=True):
                col_status, col_label = st.columns([1, 11])
                with col_status:
                    st.markdown(f"### {status_icon}")
                with col_label:
                    st.markdown(f"**{r.rule_label}** — {outcome_label}")

                    # Metrics
                    if r.evaluated_metrics:
                        metrics_parts = []
                        for k, v in r.evaluated_metrics.items():
                            # Clean metric key: remove Dataset.*.hash prefix
                            clean_key = k.split(".")[-1] if "." in k else k
                            metrics_parts.append(f"`{clean_key}` = **{v:g}**")
                        st.caption("Metricas: " + " · ".join(metrics_parts))

                    # Failure reason
                    if r.failure_reason:
                        st.caption(f"Motivo: {r.failure_reason}")

                    # Full syntax (collapsible)
                    with st.expander("Sintaxe completa", expanded=False):
                        st.code(r.rule_syntax, language=None)

        # Cross-reference with cart
        st.divider()
        if n_failed > 0:
            st.markdown("**Proximos passos:**")
            st.markdown(
                "- Revise as regras reprovadas e ajuste parametros na pagina **Explore**\n"
                "- Desabilite regras problematicas na pagina **Review**\n"
                "- Re-execute o teste apos ajustes"
            )
            col_nav1, col_nav2 = st.columns(2)
            with col_nav1:
                if st.button("Ir para Explore", key="nav_explore_results"):
                    st.switch_page("pages/02_explore.py")
            with col_nav2:
                if st.button("Ir para Review", key="nav_review_results"):
                    st.switch_page("pages/03_review.py")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption(
    "O Thundera e um pipeline generico de qualidade de dados via Glue job. "
    "As regras GDQ do carrinho sao passadas no campo VARIAVEIS.GDQ do payload JSON."
)
