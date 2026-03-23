Voce e um revisor de arquitetura senior.

Analise o diff abaixo e responda SOMENTE em JSON com o formato padrao.

Verifique obrigatoriamente:
1. A separacao entre source, deploy, runtime e secrets foi mantida?
2. Ha tentativa de modificar runtime ou secrets diretamente?
3. Ha acoplamento excessivo entre modulos?
4. Ha logica operacional fora dos pontos previstos pelo playbook?
5. Ha violacao de padroes de caminhos, ownership ou wrappers?
6. O diff introduz complexidade desnecessaria ou dependencia nao justificada?

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

