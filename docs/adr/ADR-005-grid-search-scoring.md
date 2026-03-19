# ADR-005: Formula de Scoring do Grid Search (Auto-Tune)

- **Status:** Aceito (v2 — outlier-aware)
- **Data:** 2026-02-26 (atualizado 2026-03-17)
- **Decisores:** Equipe GDQ Rule Proposer

---

## Contexto

O auto-tune (`ProposalService.find_best_params`) testa 200 combinacoes de parametros
(5 valores de N x 5 de sigma x 4 de margem x 2 de margin_on) para encontrar a melhor
configuracao de uma regra dual guard.

Cada combinacao gera um backtest com metricas (coverage, FP, stability, band_width_ratio).
Precisamos de um score composto que balanceie essas metricas para selecionar a melhor combinacao.

### Problema da v1

A formula v1 maximizava cobertura total sem distinguir pontos normais de outliers.
Isso levava a bandas largas que cobriam tudo (incluindo outliers obvios), resultando
em parametros "absurdos" (margens muito grandes, sigma alto) que nao refletiam o que
um analista escolheria manualmente.

---

## Decisao (v2 — outlier-aware)

Score composto com 10 componentes, centrado em **cobertura de pontos normais**:

```python
combo_score = (
    normal_coverage      # pontos normais cobertos / total normais (0-1)
    - outlier_penalty    # (outliers cobertos / total outliers) * 0.15
    - fp_penalty         # false_positives * 0.05
    + stability_bonus    # stability_score * 0.10
    - width_penalty      # max(0, (bwr - 0.20))^2 * 0.5 (quadratico)
    + drift_bonus        # +0.05 sem drift, -0.05 com drift
    - n_penalty          # 0.05 se N < 15
    - sigma_preference   # sigma * 0.02 (prefere sigma apertado)
    - margin_preference  # margin * 0.10 (prefere margem apertada)
    + recency_bonus      # (weighted_cov - flat_cov) / 100 * 0.10
)
```

### Deteccao de outliers

Antes do grid search, outliers sao detectados via IQR com fator 2.5:
- Q1, Q3 calculados sobre valores validos
- Fences: Q1 - 2.5*IQR, Q3 + 2.5*IQR
- Fator 2.5 (vs 1.5 padrao) para ser conservador — so marca outliers extremos

### Justificativa de cada componente

- **normal_coverage (peso dominante, ~1.0):** Cobertura de pontos NAO-outlier.
  Maximiza quantos periodos normais passam na regra, ignorando outliers.

- **outlier_penalty (0.15 max):** Penaliza bandas que cobrem outliers.
  Se todos os outliers passam na regra, a banda e larga demais.

- **fp_penalty (0.05 por FP):** Cada falso positivo custa investigacao manual.
  Peso moderado: 2 FPs reduzem score em 0.10.

- **stability_bonus (0.10 max):** Banda estavel e mais previsivel.

- **width_penalty (quadratico, threshold 0.20):** Banda > 20% da media recebe
  penalidade quadratica. Muito mais forte que v1 (linear, threshold 0.30).
  Ex: bwr=0.40 → 0.020, bwr=0.60 → 0.080, bwr=1.0 → 0.320.

- **drift_bonus (+/-0.05):** Series com drift sao menos confiaveis.

- **n_penalty (0.05 se N<15):** Janelas curtas geram bandas volateis.

- **sigma_preference (sigma * 0.02):** Quando cobertura e igual, prefere
  sigma menor (banda mais apertada = mais util). Ex: sigma 1.5 → 0.03.

- **margin_preference (margin * 0.10):** Quando cobertura e igual, prefere
  margem menor. Ex: margem 5% → 0.005, margem 20% → 0.020.

- **recency_bonus:** Recompensa combos com cobertura recente melhor que geral.

### Classificacao de confianca

Apos o grid search:
- **HIGH:** coverage >= 90% E 0 FPs
- **MEDIUM:** coverage >= min_coverage (default 70%)
- **LOW:** coverage < min_coverage

### Informacoes de outlier no resultado

O resultado inclui `outliers_detected` e `outliers_covered` para transparencia.
A recomendacao textual informa quantos outliers foram excluidos da banda.

---

## Historico

### v1 (2026-02-26) — Formula original

```python
combo_score = (
    coverage_norm - fp_penalty + stability_bonus
    - width_penalty + drift_bonus - n_penalty
)
```

Problemas: cobertura cega a outliers, width penalty linear e fraco,
nao diferencia sigma/margem quando cobertura e igual.

### v2 (2026-03-17) — Outlier-aware

Adiciona: IQR outlier detection, normal_coverage, outlier_penalty,
sigma/margin preference, width penalty quadratico.

---

## Alternativas Consideradas

### A) Pareto front multi-objetivo

Rejeitado: complexidade excessiva. O usuario precisa de UMA recomendacao.

### B) Coverage puro (max coverage)

Rejeitado: ignora FPs e estabilidade. Banda enorme = 100% coverage mas inutil.

### C) Pesos configuraveis pelo usuario

Adiado: pode ser extensao futura.

### D) MAD para deteccao de outliers (v2)

Considerado mas rejeitado em favor de IQR: IQR e mais simples, mais conhecido,
e com fator 2.5 atinge sensibilidade similar ao MAD com fator 3.5.

---

## Consequencias

**Positivas:**
- Auto-tune produz parametros mais proximos do que analista escolheria manualmente
- Outliers obvios sao excluidos da banda
- Preferencia por parametros mais apertados evita "bandas absurdas"
- Width penalty quadratico e mais eficaz contra degeneracao

**Negativas:**
- IQR com fator 2.5 pode nao detectar todos os outliers em distribuicoes assimatricas
- Grid search de 200 combinacoes pode ser lento para series muito longas
- BacktestSummary.point_results aumenta memoria (lista de dicts por ponto)

---

## Referencias

- `services/proposal_service.py` — `find_best_params()`
- `core/backtest.py` — `backtest_band()`, `BacktestSummary.point_results`
- `core/statistical_engine.py` — `detect_drift()`, `detect_seasonality()`
- `ADR-001` — Padrao dual guard (sigma OR margem)
