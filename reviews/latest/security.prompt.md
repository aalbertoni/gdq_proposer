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

