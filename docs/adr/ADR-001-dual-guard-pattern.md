# ADR-001: Padrao Dual Guard (Sigma OR Margem)

- **Status:** Aceito
- **Data:** 2026-01-15
- **Decisores:** Equipe GDQ Rule Proposer

---

## Contexto

O AWS Glue Data Quality (GDQ) suporta regras dinamicas que usam funcoes
como `avg(last(N))` e `std(last(N))` para calcular thresholds a partir
do historico. Ha duas abordagens comuns para definir bandas de aceite:

- **Banda sigma:** `avg +/- K * std` — boa para series com variabilidade
  consistente, mas falha quando o desvio padrao e muito baixo
- **Banda margem:** `avg * (1 +/- pct)` — boa como fallback, mas pode
  ser larga demais para series com alta variabilidade

O problema central: series com variabilidade muito baixa (ex: coluna
quase constante) produzem `std -> 0`, fazendo com que a banda sigma
tenha largura proxima de zero. Qualquer variacao minima faz a regra
falhar, gerando falsos positivos.

Exemplo concreto:
- Coluna `VLR_TAXA` com media 1.5% e std 0.001
- Banda sigma com K=2: aceita apenas [1.498, 1.502]
- Um valor perfeitamente normal de 1.51 falharia

---

## Decisao

Usar o padrao **dual guard** com logica **OR** como padrao para todas
as regras dinamicas (Mean, StandardDeviation, RowCount):

```
(banda_sigma) OR (banda_margem)
```

A regra passa se o valor estiver dentro de **qualquer uma** das duas bandas.

### Formato concreto para Mean/StdDev

```
(((Mean COL >= (avg(last(N)) - (K * std(last(N))) - 0.01))
  AND (Mean COL <= (avg(last(N)) + (K * std(last(N))) + 0.01)))
 OR
 ((Mean COL >= (avg(last(N)) * 0.9) - 0.01)
  AND (Mean COL <= (avg(last(N)) * 1.1) + 0.01)))
```

### Formato concreto para RowCount

```
(((RowCount >= (avg(last(N)) * 1.0 - (K * std(last(N)))))
  AND (RowCount <= (avg(last(N)) * 1.0 + (K * std(last(N))))))
 OR
 ((RowCount >= (avg(last(N)) - (avg(last(N)) * 0.1)))
  AND (RowCount <= (avg(last(N)) + (avg(last(N)) * 0.1)))))
```

### Parametros default

- **N (janela):** 30 periodos
- **K (sigma):** 2 desvios padrao
- **Margem:** 10%
- **Buffer:** 0.01 para Mean/StdDev, 0 para RowCount

---

## Alternativas Consideradas

### 1. Apenas banda sigma

- **Pros:** Mais simples, menos parenteses, mais matematicamente "pura"
- **Contras:** Falha com series de baixa variabilidade (std -> 0).
  Gera muitos falsos positivos em colunas quase constantes.

### 2. Apenas banda margem

- **Pros:** Simples, intuitiva para usuarios de negocio
- **Contras:** Nao se adapta a series de alta variabilidade. Uma margem
  de 10% pode ser insuficiente se a serie tem picos sazonais legitimos.

### 3. Dual guard com AND

- **Pros:** Mais restritivo, menos falsos negativos
- **Contras:** Muito restritivo na pratica. A intersecao das bandas e
  sempre menor que cada banda individual, gerando mais falsos positivos.

### 4. Selecao automatica de uma unica banda

- **Pros:** Mais simples de entender
- **Contras:** Requer heuristica para decidir qual banda usar. A
  decisao pode ser fragil e dificil de explicar ao usuario.

---

## Consequencias

### Positivas

- **Cobertura robusta:** A banda sigma captura variacao estatistica real,
  enquanto a banda margem garante um minimo de tolerancia
- **Funciona com qualquer distribuicao:** Series com alta ou baixa
  variabilidade produzem regras razoaveis
- **Calibravel:** O usuario pode ajustar K e margem independentemente
  e ver o impacto em tempo real no backtest
- **Backtest com OR:** O backtest simula exatamente a mesma logica OR,
  dando metricas realistas de coverage e falsos positivos

### Negativas

- **Complexidade de parenteses:** A string GDQ gerada tem muitos niveis
  de parenteses aninhados, dificultando leitura manual. Mitigado pela
  representacao intermediaria `DualGuardSpec` e pelo `DualGuardRenderer`
  que garante parenteses balanceados.
- **Dois conjuntos de parametros:** O usuario precisa entender K (sigma)
  e margem (%). Mitigado pela UI de calibracao com sliders e preview
  de impacto lado a lado.
- **Mais permissiva que sigma puro:** Em series com alta variabilidade,
  a banda margem pode ser mais estreita que a banda sigma, efetivamente
  nao adicionando nada. Isso e aceitavel — o OR nunca piora a cobertura.

---

## Notas de Implementacao

- A representacao intermediaria `DualGuardSpec` (em `core/models/dual_guard.py`)
  separa parametros de formatacao via `FormattingProfile`
- O `DualGuardRenderer` (em `core/gdq_renderer.py`) garante formatacao
  correta e parenteses balanceados
- Nunca gerar string GDQ diretamente — sempre passar pelo spec + renderer
- Mean e StdDev usam buffer de 0.01 para evitar rejeicao por arredondamento
- RowCount usa formato de margem diferente: `avg - (avg * pct)` vs `avg * factor`
