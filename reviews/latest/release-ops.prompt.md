Voce e um revisor de release e operacoes.

Analise o diff abaixo e responda SOMENTE em JSON com o formato padrao.

Verifique obrigatoriamente:
1. O app continua implantavel pelo compose?
2. O health check e valido e suficiente para a mudanca?
3. Ha smoke test compativel com o que mudou?
4. Existe plano de rollback por artefato?
5. Se houver migracao, o deploy continua seguro?
6. Ha logging e sinais minimos para diagnostico pos-deploy?
7. Alguma alteracao exige aprovacao humana antes de prod?

Formato esperado:
{
  "status": "APROVADO|ATENCAO|BLOQUEADO",
  "blockers": [],
  "warnings": [],
  "summary": "Resumo em uma linha."
}

Diff:
diff --git a/core/gdq_rule_generator.py b/core/gdq_rule_generator.py
index d22895b..0009a4c 100644
--- a/core/gdq_rule_generator.py
+++ b/core/gdq_rule_generator.py
@@ -126,7 +126,7 @@ class GDQRuleGenerator:
 
     @staticmethod
     def _format_column_value(value: str) -> str:
-        """Formata valor para ColumnValues: numerico sem aspas, string com aspas, NULL sem aspas."""
+        """Formata valor para ColumnValues: numerico sem aspas, string com aspas duplas, NULL sem aspas."""
         s = str(value)
         if s.upper() == "NULL":
             return "NULL"
@@ -135,7 +135,7 @@ class GDQRuleGenerator:
             float(s)
             return s
         except (ValueError, TypeError):
-            return f"'{s}'"
+            return f'"{s}"'
 
     def _generate_distinct_count(
         self,
diff --git a/docs/gdq_syntax_reference.md b/docs/gdq_syntax_reference.md
index 667d783..6154542 100644
--- a/docs/gdq_syntax_reference.md
+++ b/docs/gdq_syntax_reference.md
@@ -13,7 +13,7 @@
 | Nomes de regra | **CamelCase**: `Mean`, `StandardDeviation`, `RowCount`, `CustomSql` |
 | Funções dinâmicas | `avg(last(N))`, `std(last(N))` — sempre em **lowercase** |
 | Valores string em CustomSql | Com aspas simples: `'1'`, `'2'` |
-| Valores em ColumnValues | Numéricos sem aspas: `in [2, 1, 3]`; strings com aspas simples: `in ['SP', 'RJ']`; `NULL` nunca tem aspas |
+| Valores em ColumnValues | Numéricos sem aspas: `in [2, 1, 3]`; strings com aspas duplas: `in ["SP", "RJ"]`; `NULL` nunca tem aspas |
 | Buffer numérico | `0.01` adicionado/subtraído para evitar falso positivo em zero |
 | Operadores | `>=`, `<=`, `=`, `in`, `between ... and` |
 
@@ -245,15 +245,15 @@ ColumnValues {COL} in [{VALUE1}, {VALUE2}, {VALUE3}]
 
 ```
 ColumnValues COD_SITU_OPCR in [2, 1, 3]
-ColumnValues UF_EMPR in ['SP', 'RJ', 'MG']
-ColumnValues STATUS in ['ATIVO', NULL, 'INATIVO']
+ColumnValues UF_EMPR in ["SP", "RJ", "MG"]
+ColumnValues STATUS in ["ATIVO", NULL, "INATIVO"]
 ```
 
 ### Notas
 
 - Valores numéricos: **sem aspas** — `in [2, 1, 3]`
-- Valores string: **com aspas simples** — `in ['SP', 'RJ', 'MG']`
-- `NULL` **nunca** tem aspas — `in ['ATIVO', NULL]`
+- Valores string: **com aspas duplas** — `in ["SP", "RJ", "MG"]`
+- `NULL` **nunca** tem aspas — `in ["ATIVO", NULL]`
 - Sem aspas no nome da coluna (sempre UPPERCASE)
 - Ordem dos valores não importa semanticamente
 
diff --git a/pages/05_help.py b/pages/05_help.py
index e399db1..6d641f0 100644
--- a/pages/05_help.py
+++ b/pages/05_help.py
@@ -729,8 +729,8 @@ def _render_sintaxe_gdq():
         )
         st.code(
             "ColumnValues COD_SITU_OPCR in [2, 1, 3]\n"
-            "ColumnValues UF_EMPR in ['SP', 'RJ', 'MG']\n"
-            "ColumnValues STATUS in ['ATIVO', NULL, 'INATIVO']",
+            'ColumnValues UF_EMPR in ["SP", "RJ", "MG"]\n'
+            'ColumnValues STATUS in ["ATIVO", NULL, "INATIVO"]',
             language=None,
         )
 
@@ -1029,7 +1029,7 @@ def _render_faq_glossario():
     )
 
     glossary = [
-        ("AllowedValues", "Regra GDQ estatica que verifica se todos os valores de uma coluna pertencem a uma lista fixa. Sintaxe: ColumnValues COL in [...]. Valores numericos sem aspas, strings com aspas simples, NULL sem aspas."),
+        ("AllowedValues", "Regra GDQ estatica que verifica se todos os valores de uma coluna pertencem a uma lista fixa. Sintaxe: ColumnValues COL in [...]. Valores numericos sem aspas, strings com aspas duplas, NULL sem aspas."),
         ("Athena", "Servico da AWS para consultar dados no data lake via SQL. A ferramenta usa Athena para analisar historico de tabelas."),
         ("Auto-tuning", "Busca automatica da melhor combinacao de N/sigma/margem via grid search. Testa multiplas combinacoes e retorna a que maximiza cobertura com menos falsos positivos."),
         ("Backtest", "Simulacao da regra no historico passado para medir cobertura, falsos positivos e estabilidade. Usa janela rolante para simular o comportamento real da regra em producao."),
diff --git a/tests/test_categorical.py b/tests/test_categorical.py
index 28d69b1..1f0940d 100644
--- a/tests/test_categorical.py
+++ b/tests/test_categorical.py
@@ -253,7 +253,7 @@ class TestGDQGeneratorCategorical:
             suggested_values=["SP", "RJ", "MG"],
         )
         syntax = self.gen.generate(p)
-        assert "ColumnValues UF in ['SP', 'RJ', 'MG']" == syntax
+        assert 'ColumnValues UF in ["SP", "RJ", "MG"]' == syntax
 
     def test_frequency_static_numeric_column(self):
         """Coluna numerica: valor no case when sem aspas."""

