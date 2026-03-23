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
deleted file mode 100644
index 81d8dfb..0000000
Binary files a/.coverage and /dev/null differ
diff --git a/.gitignore b/.gitignore
index 343ab3c..9026de7 100644
--- a/.gitignore
+++ b/.gitignore
@@ -3,6 +3,7 @@
 __pycache__/
 *.pyc
 .pytest_cache/
+.coverage
 
 # Ambiente
 .env

