"""
Motor estatístico: bandas dinâmicas, margem percentual, detecção de drift.

Funções puras — sem I/O, sem Athena, sem UI.
Recebem dados agregados (listas de float) e retornam dicts com thresholds.

Definido conforme docs/technical_spec_v1.md seção 5.
"""

import math
from typing import Optional


def _filter_valid(values: list[float]) -> list[float]:
    """Remove NaN e None de uma lista de floats."""
    return [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]


def _last_n(values: list[float], n: int) -> list[float]:
    """Retorna os últimos N valores válidos (após filtrar NaN)."""
    valid = _filter_valid(values)
    if n >= len(valid):
        return valid
    return valid[-n:]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _stddev(values: list[float]) -> float:
    """Desvio padrão amostral (ddof=1)."""
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def compute_dynamic_band(
    values: list[float],
    n_periods: int,
    n_sigma: float = 2.0,
) -> dict:
    """Calcula banda baseada em desvio padrão (avg ± K×std).

    Args:
        values: Série histórica de valores agregados.
        n_periods: Número de períodos recentes a considerar.
        n_sigma: Multiplicador de desvio padrão (K).

    Returns:
        {"lower": float, "upper": float, "center": float,
         "std": float, "n_sigma": float, "n_periods_used": int}

    Raises:
        ValueError: Se menos de 3 valores válidos disponíveis.
    """
    subset = _last_n(values, n_periods)
    if len(subset) < 3:
        raise ValueError(
            f"Insuficiente: {len(subset)} valores válidos, mínimo 3"
        )

    center = _mean(subset)
    std = _stddev(subset)
    lower = center - n_sigma * std
    upper = center + n_sigma * std

    return {
        "lower": lower,
        "upper": upper,
        "center": center,
        "std": std,
        "n_sigma": n_sigma,
        "n_periods_used": len(subset),
    }


def compute_margin_band(
    values: list[float],
    n_periods: int,
    margin_pct: float = 0.10,
) -> dict:
    """Calcula banda baseada em margem percentual (avg × (1±margin)).

    Args:
        values: Série histórica de valores agregados.
        n_periods: Número de períodos recentes a considerar.
        margin_pct: Margem percentual (0.10 = 10%).

    Returns:
        {"lower": float, "upper": float, "center": float,
         "margin_pct": float, "n_periods_used": int}

    Raises:
        ValueError: Se menos de 3 valores válidos disponíveis.
    """
    subset = _last_n(values, n_periods)
    if len(subset) < 3:
        raise ValueError(
            f"Insuficiente: {len(subset)} valores válidos, mínimo 3"
        )

    center = _mean(subset)
    lower = center * (1 - margin_pct)
    upper = center * (1 + margin_pct)

    return {
        "lower": lower,
        "upper": upper,
        "center": center,
        "margin_pct": margin_pct,
        "n_periods_used": len(subset),
    }


def compute_percentile_band(
    p_lower_series: list[float],
    p_upper_series: list[float],
    n_periods: int,
) -> dict:
    """Calcula banda baseada em percentis históricos.

    Args:
        p_lower_series: Série dos percentis inferiores (ex: P05).
        p_upper_series: Série dos percentis superiores (ex: P95).
        n_periods: Número de períodos recentes.

    Returns:
        {"lower": float, "upper": float, "n_periods_used": int}
    """
    p_lower = _last_n(p_lower_series, n_periods)
    p_upper = _last_n(p_upper_series, n_periods)
    n_used = min(len(p_lower), len(p_upper))
    if n_used < 3:
        raise ValueError(
            f"Insuficiente: {n_used} pontos de percentil válidos, mínimo 3"
        )

    lower = _mean(p_lower[-n_used:])
    upper = _mean(p_upper[-n_used:])

    return {
        "lower": lower,
        "upper": upper,
        "n_periods_used": n_used,
    }


def compute_frequency_band(
    pct_series: list[float],
    n_periods: int,
    margin_pct: float = 0.05,
    n_sigma: float = 2.0,
) -> dict:
    """Calcula banda para frequência percentual de categoria.

    Args:
        pct_series: Série de proporções (0-100) da categoria.
        n_periods: Número de períodos recentes.
        margin_pct: Margem absoluta em pontos percentuais.
        n_sigma: Multiplicador de desvio padrão.

    Returns:
        {"lower": float, "upper": float, "center": float, "std": float,
         "n_sigma": float, "margin_pct": float, "n_periods_used": int}
    """
    subset = _last_n(pct_series, n_periods)
    if len(subset) < 3:
        raise ValueError(
            f"Insuficiente: {len(subset)} valores válidos, mínimo 3"
        )

    center = _mean(subset)
    std = _stddev(subset)
    lower = max(center - n_sigma * std - margin_pct, -0.01)
    upper = min(center + n_sigma * std + margin_pct, 100.01)

    return {
        "lower": lower,
        "upper": upper,
        "center": center,
        "std": std,
        "n_sigma": n_sigma,
        "margin_pct": margin_pct,
        "n_periods_used": len(subset),
    }


def compute_rolling_bands(
    values: list[float],
    n_periods: int,
    n_sigma: float = 2.0,
    margin_pct: float = 0.10,
    min_history: int = 7,
) -> dict:
    """Calcula bandas rolantes sigma e margem para cada ponto.

    Para cada ponto i, usa values[max(0,i-n_periods):i] como baseline
    (excluindo o ponto atual, igual ao backtest).

    Returns:
        {"sigma_upper": list, "sigma_lower": list,
         "margin_upper": list, "margin_lower": list,
         "center": list}
        Cada lista tem mesmo tamanho que values. None onde historico insuficiente.
    """
    n = len(values)
    sigma_upper: list[float | None] = [None] * n
    sigma_lower: list[float | None] = [None] * n
    margin_upper: list[float | None] = [None] * n
    margin_lower: list[float | None] = [None] * n
    center: list[float | None] = [None] * n

    for i in range(n):
        baseline = _filter_valid(values[max(0, i - n_periods):i])
        if len(baseline) < min_history:
            continue
        try:
            sb = compute_dynamic_band(baseline, n_periods, n_sigma)
            mb = compute_margin_band(baseline, n_periods, margin_pct)
            sigma_upper[i] = sb["upper"]
            sigma_lower[i] = sb["lower"]
            margin_upper[i] = mb["upper"]
            margin_lower[i] = mb["lower"]
            center[i] = sb["center"]
        except ValueError:
            continue

    return {
        "sigma_upper": sigma_upper,
        "sigma_lower": sigma_lower,
        "margin_upper": margin_upper,
        "margin_lower": margin_lower,
        "center": center,
    }


def detect_drift(
    values: list[float],
    window: Optional[int] = None,
) -> dict:
    """Detecta tendência linear na série via regressão simples.

    Args:
        values: Série de valores.
        window: Se fornecido, usa apenas os últimos N pontos.

    Returns:
        {"has_drift": bool, "slope": float, "r_squared": float,
         "n_points": int}
    """
    valid = _filter_valid(values)
    if window and window < len(valid):
        valid = valid[-window:]

    n = len(valid)
    if n < 5:
        return {"has_drift": False, "slope": 0.0, "r_squared": 0.0, "n_points": n}

    # Regressão linear simples: y = a + b*x
    x = list(range(n))
    x_mean = _mean(x)
    y_mean = _mean(valid)

    ss_xy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, valid))
    ss_xx = sum((xi - x_mean) ** 2 for xi in x)
    ss_yy = sum((yi - y_mean) ** 2 for yi in valid)

    if ss_xx == 0 or ss_yy == 0:
        return {"has_drift": False, "slope": 0.0, "r_squared": 0.0, "n_points": n}

    slope = ss_xy / ss_xx
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy)

    # Drift se R² > 0.5 e slope significativo relativo à escala
    has_drift = r_squared > 0.5 and abs(slope) > 0.01 * abs(y_mean) if y_mean != 0 else r_squared > 0.5

    return {
        "has_drift": has_drift,
        "slope": slope,
        "r_squared": r_squared,
        "n_points": n,
    }
