"""
Backtest: simula a regra dual guard no histórico.

Percorre a série com janela rolante, calcula banda a cada ponto
e conta pass/fail. Retorna BacktestSummary.

Definido conforme docs/technical_spec_v1.md seção 5.
"""

import math

from core.models.rule_proposal import BacktestSummary
from core.statistical_engine import (
    compute_dynamic_band,
    compute_margin_band,
    detect_drift,
    _filter_valid,
)


def backtest_band(
    values: list[float],
    dates: list[str],
    n_periods: int,
    n_sigma: float = 2.0,
    margin_pct: float = 0.10,
    min_history: int = 7,
) -> BacktestSummary:
    """Executa backtest da regra dual guard no histórico.

    Para cada ponto i, usa os valores anteriores [i-n_periods:i] como baseline.
    O ponto "passa" se estiver dentro da banda sigma OU da banda de margem.

    Args:
        values: Série de valores agregados (pode conter NaN).
        dates: Datas correspondentes (mesmo length de values).
        n_periods: Janela de lookback para baseline.
        n_sigma: Multiplicador de desvio padrão.
        margin_pct: Margem percentual alternativa.
        min_history: Mínimo de pontos no baseline para avaliar.

    Returns:
        BacktestSummary com métricas de cobertura e estabilidade.
    """
    n = len(values)
    if n == 0:
        return BacktestSummary(
            total_periods=0, periods_pass=0, periods_fail=0,
            coverage_pct=0.0, false_positive_proxy=0,
            band_width_ratio=0.0, stability_score=0.0,
            has_drift=False, outlier_periods=[],
        )

    valid_values = _filter_valid(values)
    if len(valid_values) < min_history:
        return BacktestSummary(
            total_periods=0, periods_pass=0, periods_fail=0,
            coverage_pct=0.0, false_positive_proxy=0,
            band_width_ratio=0.0, stability_score=0.0,
            has_drift=False, outlier_periods=[],
        )

    periods_pass = 0
    periods_fail = 0
    outlier_periods = []
    false_positive_proxy = 0
    evaluated = 0
    last_sigma_band = None
    last_margin_band = None

    # Estatísticas globais para estimativa de FP
    global_mean = sum(valid_values) / len(valid_values)
    global_std = math.sqrt(
        sum((v - global_mean) ** 2 for v in valid_values) / max(len(valid_values) - 1, 1)
    )

    for i in range(n):
        current = values[i]
        if current is None or (isinstance(current, float) and math.isnan(current)):
            continue

        # Baseline: valores anteriores (excluindo o ponto atual)
        baseline = _filter_valid(values[max(0, i - n_periods):i])
        if len(baseline) < min_history:
            continue

        evaluated += 1

        try:
            sigma_band = compute_dynamic_band(baseline, n_periods, n_sigma)
            margin_band = compute_margin_band(baseline, n_periods, margin_pct)
        except ValueError:
            continue

        last_sigma_band = sigma_band
        last_margin_band = margin_band

        in_sigma = sigma_band["lower"] <= current <= sigma_band["upper"]
        in_margin = margin_band["lower"] <= current <= margin_band["upper"]

        if in_sigma or in_margin:
            periods_pass += 1
        else:
            periods_fail += 1
            if i < len(dates):
                outlier_periods.append(dates[i])
            # FP proxy: se o valor está dentro de 4σ global, provavelmente é normal
            if global_std > 0 and abs(current - global_mean) < 4 * global_std:
                false_positive_proxy += 1

    total_periods = periods_pass + periods_fail
    coverage_pct = (periods_pass / total_periods * 100) if total_periods > 0 else 0.0

    # Band width ratio usando última banda calculada
    band_width_ratio = 0.0
    if last_sigma_band and last_sigma_band["center"] != 0:
        band_width_ratio = (
            (last_sigma_band["upper"] - last_sigma_band["lower"])
            / abs(last_sigma_band["center"])
        )

    # Stability: recalcular banda com n_periods ± 2 e verificar estabilidade
    stability_score = _compute_stability(
        values, n_periods, n_sigma, margin_pct, min_history,
    )

    # Drift detection
    drift_result = detect_drift(values)

    return BacktestSummary(
        total_periods=total_periods,
        periods_pass=periods_pass,
        periods_fail=periods_fail,
        coverage_pct=coverage_pct,
        false_positive_proxy=false_positive_proxy,
        band_width_ratio=band_width_ratio,
        stability_score=stability_score,
        has_drift=drift_result["has_drift"],
        outlier_periods=outlier_periods,
    )


def _compute_stability(
    values: list[float],
    n_periods: int,
    n_sigma: float,
    margin_pct: float,
    min_history: int,
) -> float:
    """Calcula score de estabilidade comparando bandas com n±2.

    Estável = banda muda pouco quando variamos n.
    Returns: 0.0 a 1.0 (1.0 = muito estável).
    """
    valid = _filter_valid(values)
    if len(valid) < min_history + 4:
        return 0.5  # insuficiente para avaliar

    try:
        band_base = compute_dynamic_band(valid, n_periods, n_sigma)
    except ValueError:
        return 0.5

    variations = []
    for delta in [-2, 2]:
        n_test = max(min_history, n_periods + delta)
        try:
            band_test = compute_dynamic_band(valid, n_test, n_sigma)
            if band_base["center"] != 0:
                center_change = abs(band_test["center"] - band_base["center"]) / abs(band_base["center"])
            else:
                center_change = abs(band_test["center"] - band_base["center"])
            width_base = band_base["upper"] - band_base["lower"]
            width_test = band_test["upper"] - band_test["lower"]
            if width_base > 0:
                width_change = abs(width_test - width_base) / width_base
            else:
                width_change = 0.0
            variations.append(max(center_change, width_change))
        except ValueError:
            variations.append(0.5)

    max_variation = max(variations) if variations else 0.0

    if max_variation < 0.05:
        return 1.0
    elif max_variation < 0.10:
        return 0.8
    elif max_variation < 0.20:
        return 0.6
    elif max_variation < 0.30:
        return 0.4
    else:
        return 0.2
