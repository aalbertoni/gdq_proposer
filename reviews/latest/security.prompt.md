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
diff --git a/tests/test_rule_explainer.py b/tests/test_rule_explainer.py
index 84e9d13..02f809b 100644
--- a/tests/test_rule_explainer.py
+++ b/tests/test_rule_explainer.py
@@ -176,6 +176,13 @@ class TestExplainRule:
         assert "% do volume" not in text
         assert "duas bandas" not in text
 
+    def test_percentile_margin_disabled_no_margin_text(self):
+        p = _make_proposal(RuleType.NUMERIC_PERCENTILE_BAND)
+        p.margin_enabled = False
+        text = explain_rule(p)
+        assert "**ou**" not in text
+        assert "% da media" not in text
+
 
 # ---------------------------------------------------------------------------
 # Tests: explain_rule_detail

