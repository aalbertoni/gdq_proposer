# ADR-005: Formula de Scoring do Grid Search (Auto-Tune)

- **Status:** Aceito
- **Data:** 2026-02-26
- **Decisores:** Equipe GDQ Rule Proposer

---

## Contexto

O auto-tune (`ProposalService.find_best_params`) testa 200 combinacoes de parametros
(5 valores de N x 5 de sigma x 4 de margem x 2 de margin_on) para encontrar a melhor
configuracao de uma regra dual guard.

Cada combinacao gera um backtest com metricas (coverage, FP, stability, band_width_ratio).
Precisamos de um score composto que balanceie essas metricas para selecionar a melhor combinacao.

---

## Decisao

Score composto com 6 componentes:

```python
combo_score = (
    coverage_norm        # coverage / 100 (0.0 a 1.0)
    - fp_penalty         # false_positives * 0.05
    + stability_bonus    # stability_score * 0.10
    - width_penalty      # max(0, (band_width_ratio - 0.3)) * 0.15
    + drift_bonus        # +0.05 se sem drift, -0.05 se com drift
    - n_penalty          # 0.05 se N < 15, else 0.0
)
```

### Justificativa de cada componente

- **coverage_norm (peso dominante, ~1.0):** Cobertura e o objetivo principal.
  Uma regra que reprova muitos periodos normais nao e util.

- **fp_penalty (0.05 por FP):** Cada falso positivo custa investigacao manual.
  Peso moderado: 2 FPs reduzem score em 0.10.

- **stability_bonus (0.10 max):** Banda estavel e mais previsivel. Bonus maximo
  de 0.10 evita que domine a cobertura.

- **width_penalty (0.15 multiplier):** Banda muito larga (>30% da media) perde
  utilidade pratica. Penaliza progressivamente.

- **drift_bonus (+/-0.05):** Series com drift sao menos confiaveis para regras
  automaticas. Bonus simetrico (+0.05 sem drift, -0.05 com drift).

- **n_penalty (0.05 se N<15):** Janelas muito curtas geram bandas volateis.
  Penaliza levemente para preferir janelas mais estaveis.

### Classificacao de confianca

Apos o grid search:
- **HIGH:** coverage >= 90% E 0 FPs
- **MEDIUM:** coverage >= min_coverage (default 70%)
- **LOW:** coverage < min_coverage

---

## Alternativas Consideradas

### A) Pareto front multi-objetivo

Rejeitado: complexidade excessiva para o caso de uso. O usuario precisa de
UMA recomendacao, nao de um conjunto de solucoes.

### B) Coverage puro (max coverage)

Rejeitado: ignora FPs e estabilidade. Uma banda enorme tem 100% coverage
mas e inutil.

### C) Pesos configuraveis pelo usuario

Adiado: pode ser implementado futuramente como extensao. A formula atual
funciona bem empiricamente para Mean, StdDev, RowCount e Percentil.

---

## Consequencias

**Positivas:**
- Formula deterministica e reprodutivel
- Penalidades previnem degeneration (bandas gigantes)
- Drift detection integrada ao scoring

**Negativas:**
- Pesos escolhidos empiricamente, sem prova formal de otimalidade
- Grid search de 200 combinacoes pode ser lento para series muito longas
- Formula unica para todos os tipos de metrica (pode nao ser ideal para frequency)

---

## Referencias

- `services/proposal_service.py` — `find_best_params()`
- `core/backtest.py` — `backtest_band()`, `backtest_frequency_dual_guard()`
- `core/statistical_engine.py` — `detect_drift()`
- `ADR-001` — Padrao dual guard (sigma OR margem)
