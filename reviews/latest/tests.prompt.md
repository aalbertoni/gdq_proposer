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

