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
diff --git a/core/gdq_renderer.py b/core/gdq_renderer.py
index 37175fd..8fc8962 100644
--- a/core/gdq_renderer.py
+++ b/core/gdq_renderer.py
@@ -71,20 +71,28 @@ class DualGuardRenderer:
         lo_margin = round(1 - margin, 2)
         hi_margin = round(1 + margin, 2)
 
-        sigma_part = (
-            f'(CustomSql "{sql_expr}" between '
-            f"(avg(last({n})) - ({k} * std(last({n}))) - {buffer}) "
-            f"and (avg(last({n})) + ({k} * std(last({n}))) + {buffer}))"
+        sigma_lower = (
+            f'(CustomSql "{sql_expr}" >= '
+            f"(avg(last({n})) - ({k} * std(last({n}))) - {buffer}))"
         )
+        sigma_upper = (
+            f'(CustomSql "{sql_expr}" <= '
+            f"(avg(last({n})) + ({k} * std(last({n}))) + {buffer}))"
+        )
+        sigma_part = f"({sigma_lower} AND {sigma_upper})"
 
         if not spec.margin_enabled:
             return sigma_part
 
-        margin_part = (
-            f'(CustomSql "{sql_expr}" between '
-            f"(avg(last({n})) * {lo_margin} - {buffer}) "
-            f"and (avg(last({n})) * {hi_margin} + {buffer}))"
+        margin_lower = (
+            f'(CustomSql "{sql_expr}" >= '
+            f"(avg(last({n})) * {lo_margin} - {buffer}))"
+        )
+        margin_upper = (
+            f'(CustomSql "{sql_expr}" <= '
+            f"(avg(last({n})) * {hi_margin} + {buffer}))"
         )
+        margin_part = f"({margin_lower} AND {margin_upper})"
 
         dual_guard = f"({sigma_part} OR {margin_part})"
 
@@ -92,10 +100,12 @@ class DualGuardRenderer:
         is_hybrid = spec.floor_pct > 0.0 or spec.ceiling_pct < 100.0
         if is_hybrid:
             floor_ceil = (
-                f'(CustomSql "{sql_expr}" between '
-                f"{spec.floor_pct} and {spec.ceiling_pct})"
+                f'(CustomSql "{sql_expr}" >= '
+                f"{spec.floor_pct:.4f}) AND "
+                f'(CustomSql "{sql_expr}" <= '
+                f"{spec.ceiling_pct:.4f})"
             )
-            return f"({dual_guard} AND {floor_ceil})"
+            return f"({dual_guard} AND ({floor_ceil}))"
 
         return dual_guard
 
diff --git a/core/gdq_rule_generator.py b/core/gdq_rule_generator.py
index 0009a4c..05425b6 100644
--- a/core/gdq_rule_generator.py
+++ b/core/gdq_rule_generator.py
@@ -169,7 +169,11 @@ class GDQRuleGenerator:
                 upper = overrides.custom_upper
         athena_type = proposal.target_column_type or "string"
         sql_inner = self._build_custom_sql_expression(col, value, athena_type)
-        return f'CustomSql "{sql_inner}" between {lower:.2f} and {upper:.2f}'
+        return (
+            f'(CustomSql "{sql_inner}" >= {lower:.4f})'
+            f' AND '
+            f'(CustomSql "{sql_inner}" <= {upper:.4f})'
+        )
 
     def _build_custom_sql_expression(
         self, col: str, value: str, athena_type: str = "string",
diff --git a/docs/gdq_syntax_reference.md b/docs/gdq_syntax_reference.md
index 6154542..163f1ea 100644
--- a/docs/gdq_syntax_reference.md
+++ b/docs/gdq_syntax_reference.md
@@ -141,7 +141,7 @@ Verificar que a **proporção de uma categoria específica** em uma coluna está
 ### Sintaxe
 
 ```
-CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between {LOWER} and {UPPER}
+(CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" >= {LOWER}) AND (CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as double) * 100.0 / count(*) from primary" <= {UPPER})
 ```
 
 ### Parâmetros
@@ -150,16 +150,16 @@ CustomSql "select cast(sum(case when {COL} = '{VALUE}' then 1 else 0 end) as dou
 |-----------|-----------|
 | `{COL}` | Nome da coluna (sem aspas, uppercase) — dentro do SQL |
 | `{VALUE}` | Valor da categoria (com aspas simples dentro do SQL) |
-| `{LOWER}` | Percentual mínimo esperado (pode ser negativo como buffer) |
-| `{UPPER}` | Percentual máximo esperado |
+| `{LOWER}` | Percentual mínimo esperado (4 casas decimais, pode ser negativo como buffer) |
+| `{UPPER}` | Percentual máximo esperado (4 casas decimais) |
 | `"from primary"` | Referência à tabela sendo avaliada (sempre `primary`) |
 
 ### Exemplos Reais
 
 ```
-CustomSql "select cast(sum(case when COD_SITU_OPCR = '1' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between 85.61 and 97.66
-CustomSql "select cast(sum(case when COD_SITU_OPCR = '2' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between 2.31 and 14.35
-CustomSql "select cast(sum(case when COD_SITU_OPCR = '3' then 1 else 0 end) as double) * 100.0 / count(*) from primary" between -0.01 and 5.04
+(CustomSql "select cast(sum(case when COD_SITU_OPCR = '1' then 1 else 0 end) as double) * 100.0 / count(*) from primary" >= 85.6100) AND (CustomSql "select cast(sum(case when COD_SITU_OPCR = '1' then 1 else 0 end) as double) * 100.0 / count(*) from primary" <= 97.6600)
+(CustomSql "select cast(sum(case when COD_SITU_OPCR = '2' then 1 else 0 end) as double) * 100.0 / count(*) from primary" >= 2.3100) AND (CustomSql "select cast(sum(case when COD_SITU_OPCR = '2' then 1 else 0 end) as double) * 100.0 / count(*) from primary" <= 14.3500)
+(CustomSql "select cast(sum(case when COD_SITU_OPCR = '3' then 1 else 0 end) as double) * 100.0 / count(*) from primary" >= -0.0100) AND (CustomSql "select cast(sum(case when COD_SITU_OPCR = '3' then 1 else 0 end) as double) * 100.0 / count(*) from primary" <= 5.0400)
 ```
 
 ### Notas Importantes
@@ -167,10 +167,11 @@ CustomSql "select cast(sum(case when COD_SITU_OPCR = '3' then 1 else 0 end) as d
 - O SQL inteiro fica entre **aspas duplas**
 - Valores de string dentro do SQL usam **aspas simples**: `= '1'`
 - O resultado é em **percentual (0-100)**, não proporção (0-1)
-- `LOWER` pode ser negativo (ex: `-0.01`) como buffer para categorias muito raras
+- `LOWER` pode ser negativo (ex: `-0.0100`) como buffer para categorias muito raras
 - `from primary` é a referência fixa à tabela sendo avaliada
 - O `cast(... as double)` é obrigatório para evitar divisão inteira
-- Valores de LOWER/UPPER são **estáticos** (calculados pela ferramenta), não dinâmicos
+- Valores de LOWER/UPPER são **estáticos** (calculados pela ferramenta) com **4 casas decimais**
+- Usa `>=` e `<=` (não `between`)
 
 ---
 
@@ -210,15 +211,15 @@ A regra passa se: (dentro da banda dinamica) **AND** (entre floor e ceiling).
 ### Sintaxe
 
 ```
-((DUAL_GUARD_EXPRESSION) AND (CustomSql "..." between {FLOOR} and {CEILING}))
+((DUAL_GUARD_EXPRESSION) AND ((CustomSql "..." >= {FLOOR}) AND (CustomSql "..." <= {CEILING})))
 ```
 
 Onde `DUAL_GUARD_EXPRESSION` e a mesma expressao da secao 4b (sigma OR margem).
 
 ### Parametros adicionais
 
-- `{FLOOR}`: Limite inferior absoluto (percentual 0-100). Ex: `5.0`
-- `{CEILING}`: Limite superior absoluto (percentual 0-100). Ex: `50.0`
+- `{FLOOR}`: Limite inferior absoluto (percentual 0-100, 4 casas decimais). Ex: `5.0000`
+- `{CEILING}`: Limite superior absoluto (percentual 0-100, 4 casas decimais). Ex: `50.0000`
 
 ### Quando usar
 
diff --git a/pages/05_help.py b/pages/05_help.py
index 6d641f0..7492a98 100644
--- a/pages/05_help.py
+++ b/pages/05_help.py
@@ -1050,8 +1050,8 @@ def _render_faq_glossario():
         ("Falso positivo", "Estimativa (~) de periodos normais que seriam reprovados pela regra. Criterio: viola a regra mas esta dentro de 4 sigma da media global. Ideal: 0."),
         ("Floor", "Limite inferior absoluto (%) usado no modo hibrido. A frequencia nunca pode ficar abaixo deste valor, independente do dual guard."),
         ("Frequencia dinamica", "Regra CustomSql de frequencia que usa avg(last(N)) e std(last(N)) para auto-ajustar os limites a cada execucao do GDQ."),
-        ("Frequencia estatica", "Regra CustomSql de frequencia com limites fixos (between X and Y). Calculada pela ferramenta com base no historico, mas nao se auto-ajusta."),
-        ("Frequencia hibrida", "Regra dinamica com floor/ceiling absolutos. Combina auto-ajuste com limites de negocio fixos. Logica: dual guard AND between floor and ceiling."),
+        ("Frequencia estatica", "Regra CustomSql de frequencia com limites fixos (>= lower AND <= upper, 4 casas decimais). Calculada pela ferramenta com base no historico, mas nao se auto-ajusta."),
+        ("Frequencia hibrida", "Regra dinamica com floor/ceiling absolutos. Combina auto-ajuste com limites de negocio fixos. Logica: dual guard AND (>= floor AND <= ceiling)."),
         ("GDQ", "AWS Glue Data Quality. Servico da AWS para definir e executar regras de qualidade de dados em pipelines Glue."),
         ("Granularidade", "Frequencia dos periodos de analise: diario (1 periodo por dia), mensal (1 periodo por mes)."),
         ("IsPrimaryKey", "Regra GDQ que valida unicidade de uma combinacao de colunas. Colunas separadas por espaco, sem aspas."),
diff --git a/tests/test_categorical.py b/tests/test_categorical.py
index 1f0940d..7e30d13 100644
--- a/tests/test_categorical.py
+++ b/tests/test_categorical.py
@@ -210,7 +210,8 @@ class TestGDQGeneratorCategorical:
         assert 'CustomSql' in syntax
         assert 'STATUS' in syntax and "'A'" in syntax
         assert '"STATUS"' not in syntax  # sem aspas no nome da coluna
-        assert 'between 25.00 and 35.00' in syntax
+        assert '>= 25.0000' in syntax
+        assert '<= 35.0000' in syntax
         assert 'from primary' in syntax
 
     def test_distinct_count_range(self):
diff --git a/tests/test_sprint_c2.py b/tests/test_sprint_c2.py
index 28ad262..1f2f5d3 100644
--- a/tests/test_sprint_c2.py
+++ b/tests/test_sprint_c2.py
@@ -136,13 +136,15 @@ class TestRendererCustomSqlHybrid:
         spec = self._make_spec(floor_pct=0.0, ceiling_pct=5.0)
         result = self.renderer.render(spec)
         assert 'AND' in result
-        assert 'between 0.0 and 5.0' in result
+        assert '>= 0.0000' in result
+        assert '<= 5.0000' in result
 
     def test_hybrid_has_dual_guard_and_absolute(self):
         spec = self._make_spec(floor_pct=1.0, ceiling_pct=10.0)
         result = self.renderer.render(spec)
         assert 'OR' in result  # dual guard
-        assert 'between 1.0 and 10.0' in result  # absolute
+        assert '>= 1.0000' in result  # absolute lower
+        assert '<= 10.0000' in result  # absolute upper
 
     def test_hybrid_balanced_parentheses(self):
         spec = self._make_spec()
@@ -153,18 +155,20 @@ class TestRendererCustomSqlHybrid:
         """floor=0 and ceiling=100 means no effective constraint — pure dynamic."""
         spec = self._make_spec(floor_pct=0.0, ceiling_pct=100.0)
         result = self.renderer.render(spec)
-        # Should be pure dynamic (no AND with between 0.0 and 100.0)
-        assert 'between 0.0 and 100.0' not in result
+        # Should be pure dynamic (no >= 0.0000 AND <= 100.0000 absolute clause)
+        assert '>= 0.0000) AND' not in result or '<= 100.0000)' not in result
 
     def test_hybrid_floor_only(self):
         spec = self._make_spec(floor_pct=1.0, ceiling_pct=100.0)
         result = self.renderer.render(spec)
-        assert 'between 1.0 and 100.0' in result
+        assert '>= 1.0000' in result
+        assert '<= 100.0000' in result
 
     def test_hybrid_ceiling_only(self):
         spec = self._make_spec(floor_pct=0.0, ceiling_pct=50.0)
         result = self.renderer.render(spec)
-        assert 'between 0.0 and 50.0' in result
+        assert '>= 0.0000' in result
+        assert '<= 50.0000' in result
 
 
 # ---------------------------------------------------------------------------
@@ -233,7 +237,8 @@ class TestGeneratorDynamic:
             floor_pct=0.0, ceiling_pct=5.0,
         )
         syntax = self.gen.generate(p)
-        assert 'between 0.0 and 5.0' in syntax
+        assert '>= 0.0000' in syntax
+        assert '<= 5.0000' in syntax
         assert 'avg(last(30))' in syntax
         assert 'OR' in syntax
 
@@ -247,7 +252,8 @@ class TestGeneratorDynamic:
         )
         overrides = UserOverride(custom_floor_pct=1.0, custom_ceiling_pct=10.0)
         syntax = self.gen.generate(p, overrides)
-        assert 'between 1.0 and 10.0' in syntax
+        assert '>= 1.0000' in syntax
+        assert '<= 10.0000' in syntax
 
 
 # ---------------------------------------------------------------------------
@@ -436,7 +442,8 @@ class TestProposalServiceFreqMode:
         freq_proposals = [p for p in proposals if p.rule_type == RuleType.CATEGORY_FREQUENCY_HYBRID]
         assert len(freq_proposals) > 0
         for p in freq_proposals:
-            assert 'between 0.0 and 80.0' in p.gdq_syntax_preview
+            assert '>= 0.0000' in p.gdq_syntax_preview
+            assert '<= 80.0000' in p.gdq_syntax_preview
             assert p.floor_pct == 0.0
             assert p.ceiling_pct == 80.0
 

