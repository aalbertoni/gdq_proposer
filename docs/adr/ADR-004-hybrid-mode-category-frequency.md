# ADR-004: Modo Hibrido para Frequencia Categorica

- **Status:** Aceito
- **Data:** 2026-02-20
- **Decisores:** Equipe GDQ Rule Proposer

---

## Contexto

Regras de frequencia categorica (CustomSql com `sum(case when col = 'val' ...) / count(*)`)
podem ser geradas em tres modos:

1. **Estatico:** Thresholds fixos calculados a partir do historico (ex: `between 15.0 and 25.0`).
   Simples e interpretavel, mas quebra quando a distribuicao evolui naturalmente.

2. **Dinamico:** Thresholds adaptativos usando `avg(last(N))` e `std(last(N))` via padrao
   dual guard (sigma OR margem). Acompanha tendencias, mas pode aceitar qualquer valor
   se a variabilidade historica for alta.

3. **Hibrido:** Dinamico com limites absolutos (floor/ceiling). Combina adaptabilidade
   do dinamico com guardrails do estatico.

O problema: em cenarios reais, distribuicoes categoricas podem ter drift lento
(ex: migracoes de sistema) onde o modo estatico gera falsos positivos, mas tambem
ha limites de negocio que nao devem ser violados (ex: "categoria X nunca deve
passar de 50% do total").

---

## Decisao

Implementar os tres modos como opcao do usuario na UI, com o seguinte comportamento:

- **Estatico:** `CustomSql "..." between {lower} and {upper}` (valores fixos)
- **Dinamico:** `CustomSql "..." between ...` usando padrao dual guard com
  `avg(last(N))`, `std(last(N))`, sigma e margem
- **Hibrido:** Dinamico com clausula adicional: o resultado final e
  `(sigma_band OR margin_band) AND (value between floor and ceiling)`

### Representacao no DualGuardSpec

Adicionados dois campos ao `DualGuardSpec`:
- `floor_pct: float = 0.0` — limite inferior absoluto (0-100, percentual)
- `ceiling_pct: float = 100.0` — limite superior absoluto (0-100, percentual)

Modo hibrido e ativado quando `floor_pct > 0` ou `ceiling_pct < 100`.

### Validacao

- `floor_pct` deve ser < `ceiling_pct` (validado em `DualGuardSpec.__post_init__`
  e na UI antes de gerar proposta)
- Valores default (0, 100) desativam os guardrails (equivale a modo dinamico)

---

## Alternativas Consideradas

### A) Dois campos separados no renderer (min_absolute, max_absolute)

Rejeitado: duplicaria logica que ja existe no DualGuardSpec. Melhor reusar
a representacao intermediaria.

### B) Modo hibrido como composicao de duas regras separadas

Rejeitado: GDQ avalia regras independentemente. Duas regras separadas
aplicariam AND implicito, mas sem a logica OR do dual guard na parte
dinamica. A regra unica preserva a semantica correta.

### C) Apenas dinamico (sem floor/ceiling)

Insuficiente: ha cenarios de negocio onde limites absolutos sao necessarios
independente do historico.

---

## Consequencias

**Positivas:**
- Usuario escolhe o modo mais adequado ao seu cenario
- Floor/ceiling previnem alertas por variacao dentro do aceitavel
- Backtest adaptado avalia cobertura considerando os tres modos

**Negativas:**
- Complexidade adicional na UI (radio button + inputs condicionais)
- Tres caminhos de rendering no `DualGuardRenderer`
- Necessidade de explicar ao usuario quando usar cada modo

---

## Referencias

- `core/models/dual_guard.py` — DualGuardSpec com floor_pct/ceiling_pct
- `core/gdq_renderer.py` — `_render_custom_sql()` com logica hibrida
- `core/gdq_rule_generator.py` — `_generate_category_frequency_dynamic/hybrid()`
- `core/backtest.py` — `backtest_frequency_dual_guard()`
- `ADR-001` — Padrao dual guard original (sigma OR margem)
