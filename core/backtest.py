"""
Backtest: simula a regra dual guard no histórico.

Percorre a série com janela rolante, calcula banda a cada ponto
e conta pass/fail. Retorna BacktestSummary.

Inclui backtests para regras numéricas (dual guard), frequência categórica,
contagem de distintos, valores permitidos e chave primária.

Definido conforme docs/technical_spec_v1.md seção 5.
"""

import math
from typing import Optional

from core.models.rule_proposal import BacktestSummary
from core.statistical_engine import (
    compute_dynamic_band,
    compute_frequency_band,
    compute_margin_band,
    detect_drift,
    _filter_valid,
)


# Half-life ~14 periods: ln(2)/0.05 ~ 13.9
_RECENCY_LAMBDA = 0.05


def _compute_weighted_coverage(results: list[dict]) -> float:
    """Compute coverage with exponential recency bias.

    Recent periods get higher weight: w_i = exp(-lambda * (n - 1 - i)).
    Lambda = 0.05 gives ~14-period half-life.

    Args:
        results: List of dicts with 'passed' bool, in chronological order.

    Returns:
        Weighted coverage percentage (0-100).
    """
    if not results:
        return 0.0
    n = len(results)
    weights = [math.exp(-_RECENCY_LAMBDA * (n - 1 - i)) for i in range(n)]
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    weighted_passes = sum(
        w * (1.0 if r["passed"] else 0.0) for w, r in zip(weights, results)
    )
    return round(weighted_passes / total_weight * 100, 2)


def backtest_band(
    values: list[float],
    dates: list[str],
    n_periods: int,
    n_sigma: float = 2.0,
    margin_pct: float = 0.10,
    min_history: int = 7,
    margin_enabled: bool = True,
) -> BacktestSummary:
    """Executa backtest da regra dual guard no histórico.

    Para cada ponto i, usa os valores anteriores [i-n_periods:i] como baseline.
    O ponto "passa" se estiver dentro da banda sigma OU da banda de margem
    (quando margin_enabled=True). Se margin_enabled=False, avalia apenas sigma.

    Args:
        values: Série de valores agregados (pode conter NaN).
        dates: Datas correspondentes (mesmo length de values).
        n_periods: Janela de lookback para baseline.
        n_sigma: Multiplicador de desvio padrão.
        margin_pct: Margem percentual alternativa.
        min_history: Mínimo de pontos no baseline para avaliar.
        margin_enabled: Se False, avalia apenas banda sigma (sem OR margem).

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
    eval_results: list[dict] = []  # for weighted coverage

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
            if margin_enabled:
                margin_band = compute_margin_band(baseline, n_periods, margin_pct)
        except ValueError:
            continue

        last_sigma_band = sigma_band
        if margin_enabled:
            last_margin_band = margin_band

        in_sigma = sigma_band["lower"] <= current <= sigma_band["upper"]
        in_margin = (
            margin_band["lower"] <= current <= margin_band["upper"]
            if margin_enabled
            else False
        )

        passed = in_sigma or in_margin
        eval_results.append({"index": i, "value": current, "passed": passed})

        if passed:
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
    weighted_coverage_pct = _compute_weighted_coverage(eval_results)

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
        weighted_coverage_pct=weighted_coverage_pct,
        point_results=eval_results,
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


def backtest_frequency_band(
    pct_series: list[float],
    dates: list[str],
    n_periods: int,
    margin_pct: float = 5.0,
    n_sigma: float = 2.0,
    min_history: int = 7,
) -> BacktestSummary:
    """Executa backtest de banda de frequencia no historico.

    Para cada ponto i, usa pct_series[max(0,i-n_periods):i] como baseline.
    Calcula banda via compute_frequency_band e verifica se o ponto esta dentro.

    Args:
        pct_series: Serie de porcentagens (0-100) da categoria por periodo.
        dates: Datas correspondentes (mesmo length).
        n_periods: Janela de lookback para baseline.
        margin_pct: Margem absoluta em pontos percentuais.
        n_sigma: Multiplicador de desvio padrao.
        min_history: Minimo de pontos na baseline para avaliar.

    Returns:
        BacktestSummary com metricas de cobertura e estabilidade.
    """
    n = len(pct_series)
    if n == 0:
        return BacktestSummary(
            total_periods=0, periods_pass=0, periods_fail=0,
            coverage_pct=0.0, false_positive_proxy=0,
            band_width_ratio=0.0, stability_score=0.0,
            has_drift=False, outlier_periods=[],
        )

    valid_values = _filter_valid(pct_series)
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
    last_band = None
    eval_results: list[dict] = []  # for weighted coverage

    # Global stats for FP proxy
    global_mean = sum(valid_values) / len(valid_values)
    global_std = math.sqrt(
        sum((v - global_mean) ** 2 for v in valid_values) / max(len(valid_values) - 1, 1)
    )

    for i in range(n):
        current = pct_series[i]
        if current is None or (isinstance(current, float) and math.isnan(current)):
            continue

        baseline = _filter_valid(pct_series[max(0, i - n_periods):i])
        if len(baseline) < min_history:
            continue

        try:
            band = compute_frequency_band(baseline, n_periods, margin_pct, n_sigma)
        except ValueError:
            continue

        last_band = band

        passed = band["lower"] <= current <= band["upper"]
        eval_results.append({"index": i, "value": current, "passed": passed})

        if passed:
            periods_pass += 1
        else:
            periods_fail += 1
            if i < len(dates):
                outlier_periods.append(dates[i])
            if global_std > 0 and abs(current - global_mean) < 4 * global_std:
                false_positive_proxy += 1

    total_periods = periods_pass + periods_fail
    coverage_pct = (periods_pass / total_periods * 100) if total_periods > 0 else 0.0
    weighted_coverage_pct = _compute_weighted_coverage(eval_results)

    band_width_ratio = 0.0
    if last_band:
        width = last_band["upper"] - last_band["lower"]
        if last_band["center"] > 1.0:
            band_width_ratio = width / last_band["center"]
        else:
            band_width_ratio = width / 100.0

    stability_score = _compute_frequency_stability(
        pct_series, n_periods, margin_pct, n_sigma, min_history,
    )

    drift_result = detect_drift(pct_series)

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
        weighted_coverage_pct=weighted_coverage_pct,
        point_results=eval_results,
    )


def backtest_frequency_dual_guard(
    pct_series: list[float],
    dates: list[str],
    n_periods: int,
    n_sigma: float = 2.0,
    margin_pct: float = 0.10,
    buffer: float = 0.01,
    min_history: int = 7,
    margin_enabled: bool = True,
    floor_pct: float | None = None,
    ceiling_pct: float | None = None,
) -> BacktestSummary:
    """Executa backtest de frequencia dinamica com dual guard (sigma OR margem).

    Para cada ponto i, calcula sigma band e margin band separadamente
    e avalia com logica OR (como a regra GDQ faz em runtime).

    Para modo hibrido: o resultado do dual guard e AND com floor/ceiling.

    Args:
        pct_series: Serie de porcentagens (0-100) da categoria.
        dates: Datas correspondentes.
        n_periods: Janela de lookback.
        n_sigma: Multiplicador sigma.
        margin_pct: Margem como fracao (0.10 = 10%).
        buffer: Buffer absoluto em pontos percentuais.
        min_history: Minimo de pontos para avaliar.
        margin_enabled: Se False, avalia apenas sigma.
        floor_pct: Limite inferior absoluto (modo hibrido).
        ceiling_pct: Limite superior absoluto (modo hibrido).

    Returns:
        BacktestSummary.
    """
    n = len(pct_series)
    if n == 0:
        return BacktestSummary(
            total_periods=0, periods_pass=0, periods_fail=0,
            coverage_pct=0.0, false_positive_proxy=0,
            band_width_ratio=0.0, stability_score=0.0,
            has_drift=False, outlier_periods=[],
        )

    valid_values = _filter_valid(pct_series)
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
    last_sigma_band = None
    eval_results: list[dict] = []  # for weighted coverage

    global_mean = sum(valid_values) / len(valid_values)
    global_std = math.sqrt(
        sum((v - global_mean) ** 2 for v in valid_values) / max(len(valid_values) - 1, 1)
    )

    is_hybrid = floor_pct is not None or ceiling_pct is not None
    effective_floor = floor_pct if floor_pct is not None else 0.0
    effective_ceiling = ceiling_pct if ceiling_pct is not None else 100.0

    for i in range(n):
        current = pct_series[i]
        if current is None or (isinstance(current, float) and math.isnan(current)):
            continue

        baseline = _filter_valid(pct_series[max(0, i - n_periods):i])
        if len(baseline) < min_history:
            continue

        if len(baseline) < 3:
            continue

        bl_mean = sum(baseline) / len(baseline)
        bl_std = math.sqrt(
            sum((v - bl_mean) ** 2 for v in baseline) / max(len(baseline) - 1, 1)
        )

        # Sigma band
        sigma_lower = bl_mean - n_sigma * bl_std - buffer
        sigma_upper = bl_mean + n_sigma * bl_std + buffer
        in_sigma = sigma_lower <= current <= sigma_upper

        last_sigma_band = {"lower": sigma_lower, "upper": sigma_upper, "center": bl_mean}

        # Margin band
        in_margin = False
        if margin_enabled:
            lo_factor = 1 - margin_pct
            hi_factor = 1 + margin_pct
            margin_lower = bl_mean * lo_factor - buffer
            margin_upper = bl_mean * hi_factor + buffer
            in_margin = margin_lower <= current <= margin_upper

        passes_dual_guard = in_sigma or in_margin

        # Hybrid: AND with floor/ceiling
        if is_hybrid:
            in_absolute = effective_floor <= current <= effective_ceiling
            passes = passes_dual_guard and in_absolute
        else:
            passes = passes_dual_guard

        eval_results.append({"index": i, "value": current, "passed": passes})

        if passes:
            periods_pass += 1
        else:
            periods_fail += 1
            if i < len(dates):
                outlier_periods.append(dates[i])
            if global_std > 0 and abs(current - global_mean) < 4 * global_std:
                false_positive_proxy += 1

    total_periods = periods_pass + periods_fail
    coverage_pct = (periods_pass / total_periods * 100) if total_periods > 0 else 0.0
    weighted_coverage_pct = _compute_weighted_coverage(eval_results)

    band_width_ratio = 0.0
    if last_sigma_band:
        width = last_sigma_band["upper"] - last_sigma_band["lower"]
        if last_sigma_band["center"] > 1.0:
            band_width_ratio = width / last_sigma_band["center"]
        else:
            band_width_ratio = width / 100.0

    stability_score = _compute_frequency_stability(
        pct_series, n_periods, margin_pct * 100, n_sigma, min_history,
    )

    drift_result = detect_drift(pct_series)

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
        weighted_coverage_pct=weighted_coverage_pct,
        point_results=eval_results,
    )


def _compute_frequency_stability(
    pct_series: list[float],
    n_periods: int,
    margin_pct: float,
    n_sigma: float,
    min_history: int,
) -> float:
    """Calcula score de estabilidade para banda de frequencia."""
    valid = _filter_valid(pct_series)
    if len(valid) < min_history + 4:
        return 0.5

    try:
        band_base = compute_frequency_band(valid, n_periods, margin_pct, n_sigma)
    except ValueError:
        return 0.5

    variations = []
    for delta in [-2, 2]:
        n_test = max(min_history, n_periods + delta)
        try:
            band_test = compute_frequency_band(valid, n_test, margin_pct, n_sigma)
            if band_base["center"] > 1.0:
                center_change = abs(band_test["center"] - band_base["center"]) / band_base["center"]
            else:
                center_change = abs(band_test["center"] - band_base["center"]) / 100.0
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


# ---------------------------------------------------------------------------
# Backtest: DistinctCount exact
# ---------------------------------------------------------------------------

def backtest_distinct_count_exact(
    distinct_counts: list[float],
    dates: list[str],
    expected_count: int,
) -> BacktestSummary:
    """Executa backtest de DistinctValuesCount = N (contagem exata).

    Para cada periodo, verifica se distinct_count == expected_count.

    Args:
        distinct_counts: Serie de contagens de valores distintos por periodo.
        dates: Datas correspondentes (mesmo length).
        expected_count: Contagem esperada de valores distintos.

    Returns:
        BacktestSummary com metricas de cobertura e estabilidade.
    """
    n = len(distinct_counts)
    if n == 0:
        return BacktestSummary(
            total_periods=0, periods_pass=0, periods_fail=0,
            coverage_pct=0.0, false_positive_proxy=0,
            band_width_ratio=0.0, stability_score=0.0,
            has_drift=False, outlier_periods=[],
        )

    periods_pass = 0
    periods_fail = 0
    outlier_periods: list[str] = []
    false_positive_proxy = 0

    for i in range(n):
        val = distinct_counts[i]
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue

        count = int(round(val))
        if count == expected_count:
            periods_pass += 1
        else:
            periods_fail += 1
            if i < len(dates):
                outlier_periods.append(dates[i])
            # FP proxy: periods where count differs by exactly 1 (borderline)
            if abs(count - expected_count) == 1:
                false_positive_proxy += 1

    total_periods = periods_pass + periods_fail
    coverage_pct = (periods_pass / total_periods * 100) if total_periods > 0 else 0.0

    # Stability: 1.0 if all match, else ratio that match
    stability_score = coverage_pct / 100.0 if total_periods > 0 else 0.0

    # Drift: monotonic increase or decrease in distinct count
    valid_counts = _filter_valid(distinct_counts)
    has_drift = _detect_monotonic_trend(valid_counts)

    return BacktestSummary(
        total_periods=total_periods,
        periods_pass=periods_pass,
        periods_fail=periods_fail,
        coverage_pct=coverage_pct,
        false_positive_proxy=false_positive_proxy,
        band_width_ratio=0.0,  # exact match, no band
        stability_score=stability_score,
        has_drift=has_drift,
        outlier_periods=outlier_periods,
    )


# ---------------------------------------------------------------------------
# Backtest: DistinctCount range
# ---------------------------------------------------------------------------

def backtest_distinct_count_range(
    distinct_counts: list[float],
    dates: list[str],
    lower: int,
    upper: int,
) -> BacktestSummary:
    """Executa backtest de DistinctValuesCount entre lower e upper (faixa).

    Para cada periodo, verifica se lower <= distinct_count <= upper.

    Args:
        distinct_counts: Serie de contagens de valores distintos por periodo.
        dates: Datas correspondentes (mesmo length).
        lower: Limite inferior da faixa.
        upper: Limite superior da faixa.

    Returns:
        BacktestSummary com metricas de cobertura e estabilidade.
    """
    n = len(distinct_counts)
    if n == 0:
        return BacktestSummary(
            total_periods=0, periods_pass=0, periods_fail=0,
            coverage_pct=0.0, false_positive_proxy=0,
            band_width_ratio=0.0, stability_score=0.0,
            has_drift=False, outlier_periods=[],
        )

    periods_pass = 0
    periods_fail = 0
    outlier_periods: list[str] = []
    false_positive_proxy = 0

    for i in range(n):
        val = distinct_counts[i]
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue

        count = int(round(val))
        if lower <= count <= upper:
            periods_pass += 1
        else:
            periods_fail += 1
            if i < len(dates):
                outlier_periods.append(dates[i])
            # FP proxy: just outside by 1
            if count == lower - 1 or count == upper + 1:
                false_positive_proxy += 1

    total_periods = periods_pass + periods_fail
    coverage_pct = (periods_pass / total_periods * 100) if total_periods > 0 else 0.0

    # Stability: ratio of periods that pass
    stability_score = coverage_pct / 100.0 if total_periods > 0 else 0.0

    # Band width ratio: (upper - lower) / center
    center = (upper + lower) / 2.0
    band_width_ratio = (upper - lower) / center if center > 0 else 0.0

    # Drift
    valid_counts = _filter_valid(distinct_counts)
    has_drift = _detect_monotonic_trend(valid_counts)

    return BacktestSummary(
        total_periods=total_periods,
        periods_pass=periods_pass,
        periods_fail=periods_fail,
        coverage_pct=coverage_pct,
        false_positive_proxy=false_positive_proxy,
        band_width_ratio=band_width_ratio,
        stability_score=stability_score,
        has_drift=has_drift,
        outlier_periods=outlier_periods,
    )


# ---------------------------------------------------------------------------
# Backtest: AllowedValues
# ---------------------------------------------------------------------------

def backtest_allowed_values(
    period_values_map: dict[str, set[str]],
    allowed_set: set[str],
) -> BacktestSummary:
    """Executa backtest de ColumnValues ... in [...] (valores permitidos).

    Para cada periodo, verifica se todos os valores observados estao no
    conjunto de valores permitidos.

    Args:
        period_values_map: Mapa de data -> conjunto de valores observados no periodo.
        allowed_set: Conjunto de valores permitidos.

    Returns:
        BacktestSummary com metricas de cobertura e estabilidade.
    """
    if not period_values_map:
        return BacktestSummary(
            total_periods=0, periods_pass=0, periods_fail=0,
            coverage_pct=0.0, false_positive_proxy=0,
            band_width_ratio=0.0, stability_score=0.0,
            has_drift=False, outlier_periods=[],
        )

    # Sort dates for consistent ordering
    sorted_dates = sorted(period_values_map.keys())

    periods_pass = 0
    periods_fail = 0
    outlier_periods: list[str] = []
    false_positive_proxy = 0
    unexpected_counts: list[int] = []  # track unexpected value counts for drift

    for date in sorted_dates:
        observed = period_values_map[date]
        unexpected = observed - allowed_set

        if not unexpected:
            periods_pass += 1
            unexpected_counts.append(0)
        else:
            periods_fail += 1
            outlier_periods.append(date)
            unexpected_counts.append(len(unexpected))
            # FP proxy: only 1 unexpected value (borderline)
            if len(unexpected) == 1:
                false_positive_proxy += 1

    total_periods = periods_pass + periods_fail
    coverage_pct = (periods_pass / total_periods * 100) if total_periods > 0 else 0.0

    # Stability: same as coverage ratio
    stability_score = coverage_pct / 100.0 if total_periods > 0 else 0.0

    # Drift: check if number of unexpected values is increasing over time
    has_drift = _detect_monotonic_trend(
        [float(c) for c in unexpected_counts]
    )

    return BacktestSummary(
        total_periods=total_periods,
        periods_pass=periods_pass,
        periods_fail=periods_fail,
        coverage_pct=coverage_pct,
        false_positive_proxy=false_positive_proxy,
        band_width_ratio=0.0,  # binary check, no band
        stability_score=stability_score,
        has_drift=has_drift,
        outlier_periods=outlier_periods,
    )


# ---------------------------------------------------------------------------
# Backtest: IsPrimaryKey
# ---------------------------------------------------------------------------

def backtest_primary_key(
    total_rows: list[int],
    distinct_keys: list[int],
    null_counts_per_col: dict[str, list[int]],
    dates: list[str],
) -> BacktestSummary:
    """Executa backtest de IsPrimaryKey (unicidade + completude).

    Para cada periodo, verifica se:
    - Nao ha duplicatas: total_rows == distinct_keys
    - Todas as colunas PK tem zero nulls

    Args:
        total_rows: Total de linhas por periodo.
        distinct_keys: Contagem de chaves distintas por periodo.
        null_counts_per_col: Mapa de coluna -> lista de contagem de nulls por periodo.
        dates: Datas correspondentes.

    Returns:
        BacktestSummary com metricas de cobertura e estabilidade.
    """
    n = len(total_rows)
    if n == 0:
        return BacktestSummary(
            total_periods=0, periods_pass=0, periods_fail=0,
            coverage_pct=0.0, false_positive_proxy=0,
            band_width_ratio=0.0, stability_score=0.0,
            has_drift=False, outlier_periods=[],
        )

    periods_pass = 0
    periods_fail = 0
    outlier_periods: list[str] = []
    false_positive_proxy = 0
    duplicate_counts: list[int] = []

    for i in range(n):
        rows = total_rows[i]
        keys = distinct_keys[i]
        duplicates = rows - keys
        duplicate_counts.append(duplicates)

        # Check nulls across all PK columns
        has_nulls = False
        for col_name, null_list in null_counts_per_col.items():
            if i < len(null_list) and null_list[i] > 0:
                has_nulls = True
                break

        if duplicates == 0 and not has_nulls:
            periods_pass += 1
        else:
            periods_fail += 1
            if i < len(dates):
                outlier_periods.append(dates[i])
            # FP proxy: very few duplicates or nulls (borderline)
            total_nulls = sum(
                nl[i] for nl in null_counts_per_col.values()
                if i < len(nl)
            )
            if duplicates <= 1 and total_nulls <= 1:
                false_positive_proxy += 1

    total_periods = periods_pass + periods_fail
    coverage_pct = (periods_pass / total_periods * 100) if total_periods > 0 else 0.0

    # Stability: ratio of periods that pass
    stability_score = coverage_pct / 100.0 if total_periods > 0 else 0.0

    # Drift: increasing duplicate trend
    has_drift = _detect_monotonic_trend([float(d) for d in duplicate_counts])

    return BacktestSummary(
        total_periods=total_periods,
        periods_pass=periods_pass,
        periods_fail=periods_fail,
        coverage_pct=coverage_pct,
        false_positive_proxy=false_positive_proxy,
        band_width_ratio=0.0,  # binary check, no band
        stability_score=stability_score,
        has_drift=has_drift,
        outlier_periods=outlier_periods,
    )


# ---------------------------------------------------------------------------
# Helper: monotonic trend detection
# ---------------------------------------------------------------------------

def _detect_monotonic_trend(values: list[float], threshold: float = 0.7) -> bool:
    """Detecta tendencia monotonica (crescente ou decrescente) na serie.

    Usa a proporcao de diferencas consecutivas com mesmo sinal.
    Se mais de `threshold` (70%) das diferencas sao positivas ou negativas,
    considera que ha tendencia.

    Args:
        values: Serie de valores numericos.
        threshold: Proporcao minima de diferencas no mesmo sentido (default 0.7).

    Returns:
        True se ha tendencia monotonica.
    """
    valid = _filter_valid(values)
    if len(valid) < 5:
        return False

    diffs = [valid[i] - valid[i - 1] for i in range(1, len(valid))]
    if not diffs:
        return False

    positive = sum(1 for d in diffs if d > 0)
    negative = sum(1 for d in diffs if d < 0)
    total = len(diffs)

    return (positive / total) >= threshold or (negative / total) >= threshold
