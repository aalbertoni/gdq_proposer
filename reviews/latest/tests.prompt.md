Voce e um revisor de qualidade e testes.

Analise o diff abaixo e responda SOMENTE em JSON com o formato padrao.

Verifique obrigatoriamente:
1. Toda funcao publica nova tem teste unitario?
2. Casos de borda relevantes foram cobertos?
3. Bug corrigido ganhou teste de regressao?
4. Os testes sao deterministicos?
5. Mocks foram usados corretamente?
6. Existe risco de flaky tests?
7. Cobertura critica ficou insuficiente?

Formato esperado:
{
  "status": "APROVADO|ATENCAO|BLOQUEADO",
  "blockers": [],
  "warnings": [],
  "summary": "Resumo em uma linha."
}

Diff:
diff --git a/.coverage b/.coverage
index 3f6d8aa..6baef5f 100644
Binary files a/.coverage and b/.coverage differ
diff --git a/CLAUDE.md b/CLAUDE.md
index f825d8e..5bae87b 100644
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -63,6 +63,76 @@ ambos dialetos para que os testes unitarios rodem com DuckDB sem precisar de Ath
 
 ---
 
+## Governanca de Deploy
+
+Este projeto usa governanca obrigatoria de deploy. O agente nao pode improvisar fluxo com `git push`, `sudo /usr/local/bin/deploy-prod`, `stack-deploy` ou comandos ad hoc fora do `Taskfile`.
+
+Regras obrigatorias:
+
+1. Nunca seguir para deploy sem passar por `task gate1`, `task snapshot`, `task review-agents-consensus` e `task build-release`.
+2. Nunca promover para producao sem staging aprovado.
+3. Nunca fazer deploy de producao sem aprovacao humana explicita via `ALLOW_PROD_DEPLOY=true`.
+4. Nunca considerar staging ou producao aprovados sem gravar evidencia em `reviews/latest/`.
+5. Se houver duvida sobre o estado dos gates, parar e reportar o bloqueio em vez de continuar.
+
+Arquivos obrigatorios de evidencia:
+
+Staging: `reviews/latest/deploy-staging-check.md`
+
+```text
+commit_sha: <sha atual>
+environment: staging
+gate1: <pass|fail>
+snapshot_commit: <sha do snapshot>
+gate2: <pass|warning|fail>
+release_build: <pass|fail>
+staging_deploy: <pass|fail>
+staging_smoke: <pass|fail>
+verdict: <ok|warning|fail>
+```
+
+Producao: `reviews/latest/deploy-prod-check.md`
+
+```text
+commit_sha: <sha atual>
+environment: prod
+staging_governance: <pass|fail>
+prod_approval: explicit
+prod_deploy: <pass|fail>
+prod_verify: <pass|fail>
+verdict: <ok|warning|fail>
+```
+
+Fluxo obrigatorio daqui pra frente:
+
+1. Rodar `task gate1`.
+2. Rodar `task snapshot`.
+3. Rodar `task review-agents-consensus`.
+4. Rodar `task build-release`.
+5. Rodar `task deploy-staging`.
+6. Rodar `task smoke-staging`.
+7. Gravar `reviews/latest/deploy-staging-check.md`.
+8. Rodar `task verify-staging-governance-proof`.
+9. So depois disso considerar staging apto.
+10. Para producao, gravar `reviews/latest/deploy-prod-check.md`.
+11. Rodar `ALLOW_PROD_DEPLOY=true task promote-prod`.
+12. Rodar `task verify-prod`.
+13. Rodar `task verify-prod-governance-proof`.
+
+Quando o usuario disser “segue com o fluxo de deploy”, o agente deve responder executando ou orientando exatamente essa sequencia. Nao pode pular direto para `git status`, `git diff`, `git push` ou deploy.
+
+Prompts operacionais canônicos:
+
+```text
+Siga a governanca obrigatoria deste projeto. Antes de qualquer deploy, execute ou instrua exatamente o fluxo task gate1 -> task snapshot -> task review-agents-consensus -> task build-release -> task deploy-staging -> task smoke-staging. So depois disso grave reviews/latest/deploy-staging-check.md no formato canonico e valide com task verify-staging-governance-proof.
+```
+
+```text
+Siga a governanca obrigatoria deste projeto. Nao faca deploy de producao sem staging aprovado e sem aprovacao humana explicita. Antes da producao, grave reviews/latest/deploy-prod-check.md no formato canonico. Depois execute somente ALLOW_PROD_DEPLOY=true task promote-prod, task verify-prod e task verify-prod-governance-proof.
+```
+
+---
+
 ## Principios de Desenvolvimento
 
 ### 1. Fatias verticais pequenas
diff --git a/Taskfile.yml b/Taskfile.yml
index 341cd74..307dafd 100644
--- a/Taskfile.yml
+++ b/Taskfile.yml
@@ -108,9 +108,63 @@ tasks:
     cmds:
       - cmd: 'echo "Skipping public staging smoke: app interno"'
 
+  guide-governed-deploy:
+    desc: Exibe o fluxo obrigatorio de governanca para staging e producao
+    cmds:
+      - |
+        cat <<'EOF'
+        Fluxo obrigatorio deste projeto:
+
+        1. task gate1
+        2. task snapshot
+        3. task review-agents-consensus
+        4. task build-release
+        5. task deploy-staging
+        6. task smoke-staging
+        7. Gerar reviews/latest/deploy-staging-check.md
+        8. task verify-staging-governance-proof
+
+        Para producao:
+        9. Revisar staging aprovado
+        10. Gerar reviews/latest/deploy-prod-check.md
+        11. ALLOW_PROD_DEPLOY=true task promote-prod
+        12. task verify-prod
+        13. task verify-prod-governance-proof
+
+        Deploy por comando ad hoc fora do Taskfile e proibido.
+        EOF
+
+  verify-staging-governance-proof:
+    desc: Bloqueia sem evidencia obrigatoria de staging governado
+    cmds:
+      - |
+        test -f reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^commit_sha: .+$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^environment: staging$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^gate1: (pass|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^snapshot_commit: [0-9a-f]{7,40}$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^gate2: (pass|warning|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^release_build: (pass|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^staging_deploy: (pass|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^staging_smoke: (pass|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        rg -n '^verdict: (ok|warning|fail)$' reviews/latest/deploy-staging-check.md
+      - |
+        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); rg -n "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-staging-check.md'
+
   promote-prod:
     desc: Portao 5
     cmds:
+      - bash -lc 'test "${ALLOW_PROD_DEPLOY:-false}" = "true" || { echo "Refusing production deploy without ALLOW_PROD_DEPLOY=true." >&2; exit 1; }'
+      - task: verify-staging-governance-proof
       - sudo /usr/local/bin/deploy-prod gdq-proposer
 
   verify-prod:
@@ -125,6 +179,28 @@ tasks:
     cmds:
       - cmd: 'echo "Skipping public production smoke: app interno"'
 
+  verify-prod-governance-proof:
+    desc: Bloqueia sem evidencia obrigatoria da producao governada
+    cmds:
+      - |
+        test -f reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^commit_sha: .+$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^environment: prod$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^staging_governance: (pass|fail)$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^prod_approval: explicit$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^prod_deploy: (pass|fail)$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^prod_verify: (pass|fail)$' reviews/latest/deploy-prod-check.md
+      - |
+        rg -n '^verdict: (ok|warning|fail)$' reviews/latest/deploy-prod-check.md
+      - |
+        bash -lc 'sha_short=$(git rev-parse --short HEAD); sha_full=$(git rev-parse HEAD); rg -n "^commit_sha: (${sha_short}|${sha_full})$" reviews/latest/deploy-prod-check.md'
+
   rollback-last:
     desc: Faz rollback para a ultima release saudavel
     cmds:
@@ -139,6 +215,7 @@ tasks:
       - task: build-release
       - task: deploy-staging
       - task: smoke-staging
+      - task: verify-staging-governance-proof
 
   pipeline-prod:
     desc: Executa gates, staging e verificacao interna de producao
@@ -146,3 +223,4 @@ tasks:
       - task: pipeline-staging
       - task: promote-prod
       - task: verify-prod
+      - task: verify-prod-governance-proof

