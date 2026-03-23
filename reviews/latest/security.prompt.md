Voce e um revisor de seguranca.

Analise o diff abaixo e responda SOMENTE em JSON com o formato padrao.

Verifique obrigatoriamente:
1. Segredos hardcoded ou expostos no codigo?
2. Inputs sem validacao ou sanitizacao?
3. Logs contendo dados sensiveis?
4. Risco de injecao SQL, XSS, SSRF, CSRF, path traversal?
5. Permissoes de container, compose ou filesystem excessivas?
6. Dependencias ou bibliotecas com risco conhecido?
7. Endpoints sem autenticacao adequada?

Formato esperado:
{
  "status": "APROVADO|ATENCAO|BLOQUEADO",
  "blockers": [],
  "warnings": [],
  "summary": "Resumo em uma linha."
}

Diff:
diff --git a/.coverage b/.coverage
index 6baef5f..6e69e8a 100644
Binary files a/.coverage and b/.coverage differ
diff --git a/CLAUDE.md b/CLAUDE.md
index 5bae87b..7a07250 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -70,10 +70,12 @@ Este projeto usa governanca obrigatoria de deploy. O agente nao pode improvisar
 Regras obrigatorias:
 
 1. Nunca seguir para deploy sem passar por `task gate1`, `task snapshot`, `task review-agents-consensus` e `task build-release`.
-2. Nunca promover para producao sem staging aprovado.
-3. Nunca fazer deploy de producao sem aprovacao humana explicita via `ALLOW_PROD_DEPLOY=true`.
-4. Nunca considerar staging ou producao aprovados sem gravar evidencia em `reviews/latest/`.
-5. Se houver duvida sobre o estado dos gates, parar e reportar o bloqueio em vez de continuar.
+2. Nunca fazer `git push` da branch de trabalho antes de staging aprovado. O push remoto acontece somente depois de `task verify-staging-governance-proof`, via `task push-after-staging`.
+3. Nunca promover para producao sem staging aprovado.
+4. Nunca fazer deploy de producao sem aprovacao humana explicita via `ALLOW_PROD_DEPLOY=true`.
+5. Nunca considerar staging ou producao aprovados sem gravar evidencia em `reviews/latest/`.
+6. Se houver duvida sobre o estado dos gates, parar e reportar o bloqueio em vez de continuar.
+7. O staging nao deve ser derrubado logo apos o deploy de producao. So pode ser desligado depois de `task verify-prod`, `task verify-prod-governance-proof` e uma aprovacao explicita via `ALLOW_STAGING_CLEANUP=true`.
 
 Arquivos obrigatorios de evidencia:
 
@@ -113,22 +115,24 @@ Fluxo obrigatorio daqui pra frente:
 6. Rodar `task smoke-staging`.
 7. Gravar `reviews/latest/deploy-staging-check.md`.
 8. Rodar `task verify-staging-governance-proof`.
-9. So depois disso considerar staging apto.
-10. Para producao, gravar `reviews/latest/deploy-prod-check.md`.
-11. Rodar `ALLOW_PROD_DEPLOY=true task promote-prod`.
-12. Rodar `task verify-prod`.
-13. Rodar `task verify-prod-governance-proof`.
+9. Rodar `task push-after-staging`.
+10. So depois disso considerar staging apto e branch remota alinhada.
+11. Para producao, gravar `reviews/latest/deploy-prod-check.md`.
+12. Rodar `ALLOW_PROD_DEPLOY=true task promote-prod`.
+13. Rodar `task verify-prod`.
+14. Rodar `task verify-prod-governance-proof`.
+15. Opcionalmente, so depois de producao estavel, rodar `ALLOW_STAGING_CLEANUP=true task cleanup-staging-after-prod`.
 
 Quando o usuario disser “segue com o fluxo de deploy”, o agente deve responder executando ou orientando exatamente essa sequencia. Nao pode pular direto para `git status`, `git diff`, `git push` ou deploy.
 
 Prompts operacionais canônicos:
 
 ```text
-Siga a governanca obrigatoria deste projeto. Antes de qualquer deploy, execute ou instrua exatamente o fluxo task gate1 -> task snapshot -> task review-agents-consensus -> task build-release -> task deploy-staging -> task smoke-staging. So depois disso grave reviews/latest/deploy-staging-check.md no formato canonico e valide com task verify-staging-governance-proof.
+Siga a governanca obrigatoria deste projeto. Antes de qualquer deploy, execute ou instrua exatamente o fluxo task gate1 -> task snapshot -> task review-agents-consensus -> task build-release -> task deploy-staging -> task smoke-staging. So depois disso grave reviews/latest/deploy-staging-check.md no formato canonico, valide com task verify-staging-governance-proof e faca o push remoto somente via task push-after-staging.
 ```
 
 ```text
-Siga a governanca obrigatoria deste projeto. Nao faca deploy de producao sem staging aprovado e sem aprovacao humana explicita. Antes da producao, grave reviews/latest/deploy-prod-check.md no formato canonico. Depois execute somente ALLOW_PROD_DEPLOY=true task promote-prod, task verify-prod e task verify-prod-governance-proof.
+Siga a governanca obrigatoria deste projeto. Nao faca deploy de producao sem staging aprovado e sem aprovacao humana explicita. Antes da producao, grave reviews/latest/deploy-prod-check.md no formato canonico. Depois execute somente task push-after-staging, ALLOW_PROD_DEPLOY=true task promote-prod, task verify-prod e task verify-prod-governance-proof. So derrube o staging se houver aprovacao explicita via ALLOW_STAGING_CLEANUP=true task cleanup-staging-after-prod.
 ```
 
 ---
diff --git a/Taskfile.yml b/Taskfile.yml
index 307dafd..c08903e 100644
--- a/Taskfile.yml
+++ b/Taskfile.yml
@@ -123,13 +123,15 @@ tasks:
         6. task smoke-staging
         7. Gerar reviews/latest/deploy-staging-check.md
         8. task verify-staging-governance-proof
+        9. task push-after-staging
 
         Para producao:
-        9. Revisar staging aprovado
-        10. Gerar reviews/latest/deploy-prod-check.md
-        11. ALLOW_PROD_DEPLOY=true task promote-prod
-        12. task verify-prod
-        13. task verify-prod-governance-proof
+        10. Revisar staging aprovado
+        11. Gerar reviews/latest/deploy-prod-check.md
+        12. ALLOW_PROD_DEPLOY=true task promote-prod
+        13. task verify-prod
+        14. task verify-prod-governance-proof
+        15. Opcional: ALLOW_STAGING_CLEANUP=true task cleanup-staging-after-prod
 
         Deploy por comando ad hoc fora do Taskfile e proibido.
         EOF
@@ -140,25 +142,31 @@ tasks:
       - |
         test -f reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^commit_sha: .+$' reviews/latest/deploy-staging-check.md
+        grep -nE '^commit_sha: .+$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^environment: staging$' reviews/latest/deploy-staging-check.md
+        grep -nE '^environment: staging$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^gate1: (pass|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^gate1: (pass|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^snapshot_commit: [0-9a-f]{7,40}$' reviews/latest/deploy-staging-check.md
+        grep -nE '^snapshot_commit: [0-9a-f]{7,40}$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^gate2: (pass|warning|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^gate2: (pass|warning|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^release_build: (pass|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^release_build: (pass|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^staging_deploy: (pass|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^staging_deploy: (pass|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^staging_smoke: (pass|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^staging_smoke: (pass|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        rg -n '^verdict: (ok|warning|fail)$' reviews/latest/deploy-staging-check.md
+        grep -nE '^verdict: (ok|warning|fail)$' reviews/latest/deploy-staging-check.md
       - |
-        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); rg -n "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-staging-check.md'
+        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); grep -nE "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-staging-check.md'
+
+  push-after-staging:
+    desc: Faz git push somente apos staging aprovado
+    cmds:
+      - task: verify-staging-governance-proof
+      - git push
 
   promote-prod:
     desc: Portao 5
@@ -185,21 +193,29 @@ tasks:
       - |
         test -f reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^commit_sha: .+$' reviews/latest/deploy-prod-check.md
+        grep -nE '^commit_sha: .+$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^environment: prod$' reviews/latest/deploy-prod-check.md
+        grep -nE '^environment: prod$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^staging_governance: (pass|fail)$' reviews/latest/deploy-prod-check.md
+        grep -nE '^staging_governance: (pass|fail)$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^prod_approval: explicit$' reviews/latest/deploy-prod-check.md
+        grep -nE '^prod_approval: explicit$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^prod_deploy: (pass|fail)$' reviews/latest/deploy-prod-check.md
+        grep -nE '^prod_deploy: (pass|fail)$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^prod_verify: (pass|fail)$' reviews/latest/deploy-prod-check.md
+        grep -nE '^prod_verify: (pass|fail)$' reviews/latest/deploy-prod-check.md
       - |
-        rg -n '^verdict: (ok|warning|fail)$' reviews/latest/deploy-prod-check.md
+        grep -nE '^verdict: (ok|warning|fail)$' reviews/latest/deploy-prod-check.md
       - |
-        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); rg -n "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-prod-check.md'
+        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); grep -nE "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-prod-check.md'
+
+  cleanup-staging-after-prod:
+    desc: Derruba o staging somente apos producao estavel e validada
+    cmds:
+      - bash -lc 'test "${ALLOW_STAGING_CLEANUP:-false}" = "true" || { echo "Refusing staging cleanup without ALLOW_STAGING_CLEANUP=true." >&2; exit 1; }'
+      - task: verify-prod
+      - task: verify-prod-governance-proof
+      - sudo /home/aalbertoni/.config/homelab/scripts/stack-down gdq-proposer-staging
 
   rollback-last:
     desc: Faz rollback para a ultima release saudavel
@@ -221,6 +237,7 @@ tasks:
     desc: Executa gates, staging e verificacao interna de producao
     cmds:
       - task: pipeline-staging
+      - task: push-after-staging
       - task: promote-prod
       - task: verify-prod
       - task: verify-prod-governance-proof
diff --git a/app.py b/app.py
index 6a4652a..0ee46ae 100644
--- a/app.py
+++ b/app.py
@@ -35,7 +35,9 @@ def render_sidebar():
     st.sidebar.caption(f"v{__version__}")
     st.sidebar.divider()
 
-    # Diagnostic link
+    # Utility links
+    if st.sidebar.button("Query Log", key="sidebar_qlog", help="Historico de queries da sessao"):
+        st.switch_page("pages/07_query_log.py")
     if st.sidebar.button("Diagnostico", key="sidebar_diag", help="Verificar status do ambiente"):
         st.switch_page("pages/06_diagnostico.py")
 
diff --git a/pages/07_query_log.py b/pages/07_query_log.py
new file mode 100644
index 0000000..bbf6671
--- /dev/null
+++ b/pages/07_query_log.py
@@ -0,0 +1,218 @@
+"""
+Query Log — Historico completo de queries da sessao.
+
+Exibe todas as queries executadas com status, custo, tempo,
+motivo, detalhes de erro e SQL completo.
+"""
+
+import streamlit as st
+
+st.set_page_config(
+    page_title="Query Log — GDQ",
+    page_icon=":memo:",
+    layout="wide",
+)
+
+st.title("Query Log")
+st.caption("Historico completo de queries executadas nesta sessao.")
+
+# ---------------------------------------------------------------------------
+# Guard: precisa de client ativo
+# ---------------------------------------------------------------------------
+if "client" not in st.session_state:
+    st.info("Nenhuma sessao ativa. Volte ao Dashboard para conectar.")
+    if st.button("Ir para Dashboard", key="ql_go_dash"):
+        st.switch_page("app.py")
+    st.stop()
+
+client = st.session_state["client"]
+entries = client.logger.entries
+
+if not entries:
+    st.info("Nenhuma query executada nesta sessao.")
+    if st.button("Ir para Setup", key="ql_go_setup"):
+        st.switch_page("pages/01_setup.py")
+    st.stop()
+
+# ---------------------------------------------------------------------------
+# Summary metrics
+# ---------------------------------------------------------------------------
+summary = client.logger.get_session_summary()
+time_s = summary["total_elapsed_ms"] / 1000
+cost = summary["estimated_cost_usd"]
+
+m1, m2, m3, m4, m5 = st.columns(5)
+m1.metric("Total de queries", summary["total_queries"])
+m2.metric("Tempo total", f"{time_s:.1f}s")
+m3.metric("Cache hits", f"{summary['cache_hits']}/{summary['total_queries']}")
+m4.metric("Custo estimado", f"${cost:.4f}")
+m5.metric("Erros", summary["errors"])
+
+# Cost guardrail
+app_cfg = st.session_state.get("config")
+threshold = app_cfg.athena.cost_warning_threshold_usd if app_cfg else 0.50
+if cost > threshold:
+    st.warning(f"Custo da sessao (${cost:.4f}) excedeu o limite de ${threshold:.2f}.")
+
+st.divider()
+
+# ---------------------------------------------------------------------------
+# Filters
+# ---------------------------------------------------------------------------
+col_f1, col_f2, col_f3 = st.columns(3)
+
+# Status filter
+status_options = ["Todas", "OK", "Erro", "Cache Hit"]
+with col_f1:
+    status_filter = st.selectbox("Status", status_options, key="ql_status_filter")
+
+# Query name filter
+query_names = sorted({e.query_name for e in entries})
+with col_f2:
+    name_filter = st.selectbox(
+        "Tipo de query", ["Todas"] + query_names, key="ql_name_filter"
+    )
+
+# Column filter
+columns_used = sorted({e.column for e in entries if e.column})
+with col_f3:
+    column_filter = st.selectbox(
+        "Coluna", ["Todas"] + columns_used, key="ql_col_filter"
+    )
+
+# Apply filters
+filtered = list(entries)
+if status_filter == "OK":
+    filtered = [e for e in filtered if not e.exception_type and not e.cache_hit]
+elif status_filter == "Erro":
+    filtered = [e for e in filtered if e.exception_type]
+elif status_filter == "Cache Hit":
+    filtered = [e for e in filtered if e.cache_hit]
+
+if name_filter != "Todas":
+    filtered = [e for e in filtered if e.query_name == name_filter]
+
+if column_filter != "Todas":
+    filtered = [e for e in filtered if e.column == column_filter]
+
+st.caption(f"Exibindo {len(filtered)} de {len(entries)} queries.")
+
+
+# ---------------------------------------------------------------------------
+# Helper: query purpose descriptions
+# ---------------------------------------------------------------------------
+
+def _describe_query_purpose(query_name: str) -> str:
+    """Retorna descricao do proposito de cada tipo de query."""
+    purposes = {
+        "health_check": "Verificacao de conectividade com o Athena.",
+        "table_exists": "Validacao de existencia da tabela no catalogo.",
+        "get_columns": "Leitura de metadados (colunas e tipos) via information_schema.",
+        "get_columns_with_partitions": "Leitura de colunas com deteccao de partition keys.",
+        "count_rows": "Contagem de linhas para estimativa de volume e timeout adaptativo.",
+        "estimate_volume": "Estimativa de volumetria para ajustar timeout da sessao.",
+        "column_sample": "Amostragem de coluna para classificacao semantica (tipo, cardinalidade, cast ratio).",
+        "batch_column_sample": "Amostragem em lote de varias colunas para classificacao semantica.",
+        "numeric_history": "Historico temporal de metricas numericas (mean, stddev, percentis) para calibracao de regras.",
+        "row_count_history": "Historico de contagem de linhas por periodo para regra de RowCount.",
+        "distinct_count_history": "Historico de contagem de valores distintos por periodo.",
+        "categorical_distribution": "Distribuicao de frequencia de valores categoricos.",
+        "categorical_domain": "Dominio de valores (valores unicos) de coluna categorica.",
+        "uniqueness_check": "Verificacao de unicidade para deteccao de chaves primarias.",
+        "completeness_check": "Verificacao de completude (nulls) da coluna.",
+        "partition_values": "Listagem de valores de particao disponiveis.",
+        "partition_range": "Range de particoes (min/max) para definir lookback.",
+    }
+    return purposes.get(query_name, f"Query do tipo `{query_name}`.")
+
+
+# ---------------------------------------------------------------------------
+# Query list (most recent first)
+# ---------------------------------------------------------------------------
+for i, entry in enumerate(reversed(filtered)):
+    # Status badge
+    if entry.exception_type:
+        status_icon = ":red_circle:"
+        status_text = "ERRO"
+    elif entry.cache_hit:
+        status_icon = ":large_blue_circle:"
+        status_text = "CACHE"
+    else:
+        status_icon = ":green_circle:"
+        status_text = "OK"
+
+    # Cost per query
+    entry_cost = entry.estimated_cost_usd
+    cost_label = f"${entry_cost:.6f}" if entry_cost > 0 else "—"
+
+    # Bytes scanned
+    if entry.bytes_scanned and entry.bytes_scanned > 0:
+        mb = entry.bytes_scanned / (1024 ** 2)
+        if mb >= 1024:
+            scan_label = f"{mb / 1024:.2f} GB"
+        else:
+            scan_label = f"{mb:.2f} MB"
+    else:
+        scan_label = "—"
+
+    # Column label
+    col_label = f" → `{entry.column}`" if entry.column else ""
+
+    # Header line
+    header = (
+        f"{status_icon} **{entry.query_name}**{col_label} — "
+        f"{status_text} · {entry.elapsed_ms}ms · {entry.rows_returned} rows · "
+        f"custo {cost_label}"
+    )
+
+    with st.expander(header, expanded=False):
+        # Detail grid
+        d1, d2, d3 = st.columns(3)
+
+        with d1:
+            st.markdown("**Detalhes da execucao**")
+            st.markdown(f"- **Query:** {entry.query_name}")
+            st.markdown(f"- **Dataset:** {entry.dataset}")
+            st.markdown(f"- **Coluna:** {entry.column or '(tabela inteira)'}")
+            st.markdown(f"- **Timestamp:** {entry.timestamp}")
+
+        with d2:
+            st.markdown("**Metricas**")
+            st.markdown(f"- **Tempo:** {entry.elapsed_ms}ms")
+            st.markdown(f"- **Rows retornadas:** {entry.rows_returned}")
+            st.markdown(f"- **Bytes escaneados:** {scan_label}")
+            st.markdown(f"- **Custo:** {cost_label}")
+            st.markdown(f"- **Cache hit:** {'Sim' if entry.cache_hit else 'Nao'}")
+
+        with d3:
+            st.markdown("**Motivo da query**")
+            st.markdown(f"{_describe_query_purpose(entry.query_name)}")
+
+            if entry.exception_type:
+                st.markdown("**Erro**")
+                st.error(f"Tipo: `{entry.exception_type}`")
+
+        # SQL
+        if entry.sql:
+            st.markdown("**SQL executado:**")
+            st.code(entry.sql, language="sql")
+        else:
+            st.caption("SQL nao disponivel para esta query.")
+
+st.divider()
+
+# ---------------------------------------------------------------------------
+# Export
+# ---------------------------------------------------------------------------
+exp1, exp2 = st.columns(2)
+with exp1:
+    st.download_button(
+        label="Exportar log completo (JSON)",
+        data=client.logger.export_json(),
+        file_name="gdq_query_log.json",
+        mime="application/json",
+        key="ql_export_json",
+    )
+with exp2:
+    if st.button("Voltar ao Dashboard", key="ql_back_dash"):
+        st.switch_page("app.py")

