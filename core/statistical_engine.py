"""
Motor estatístico: bandas dinâmicas, margem percentual, detecção de drift.

Funções puras — sem I/O, sem Athena, sem UI.
Recebem dados agregados (listas de float) e retornam dicts com thresholds.

Definido conforme docs/technical_spec_v1.md seção 5.
"""

import math
from datetime import datetime
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
    lower = center - abs(center) * margin_pct
    upper = center + abs(center) * margin_pct

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


def _median(values: list[float]) -> float:
    """Mediana de uma lista de floats."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
    return sorted_vals[mid]


def _percentile(values: list[float], p: float) -> float:
    """Percentil p (0-100) de uma lista de floats usando interpolacao linear."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    k = (p / 100.0) * (n - 1)
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_vals[-1]
    d = k - f
    return sorted_vals[f] + d * (sorted_vals[c] - sorted_vals[f])


def compute_iqr_band(
    values: list[float],
    n_periods: int,
    n_iqr: float = 1.5,
) -> dict[str, float]:
    """Banda robusta baseada no IQR (Interquartile Range).

    Usa Q1/Q3 ao inves de mean/std — resistente a outliers.
    A banda e [Q1 - n_iqr*IQR, Q3 + n_iqr*IQR].

    Args:
        values: Lista completa de valores historicos.
        n_periods: Usar os ultimos N periodos.
        n_iqr: Multiplicador do IQR (1.5 = padrao Tukey, 3.0 = muito permissivo).

    Returns:
        Dict com: lower, upper, center (median), q1, q3, iqr,
        n_iqr, n_periods_used.
    """
    subset = _last_n(_filter_valid(values), n_periods)
    if len(subset) < 3:
        center = _mean(subset) if subset else 0.0
        return {
            "lower": center, "upper": center, "center": center,
            "q1": center, "q3": center, "iqr": 0.0,
            "n_iqr": n_iqr, "n_periods_used": len(subset),
        }
    q1 = _percentile(subset, 25.0)
    q3 = _percentile(subset, 75.0)
    iqr = q3 - q1
    center = _median(subset)
    return {
        "lower": q1 - n_iqr * iqr,
        "upper": q3 + n_iqr * iqr,
        "center": center,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "n_iqr": n_iqr,
        "n_periods_used": len(subset),
    }


def compute_mad_band(
    values: list[float],
    n_periods: int,
    n_mad: float = 3.0,
) -> dict[str, float]:
    """Banda robusta baseada no MAD (Median Absolute Deviation).

    Usa mediana +/- K*MAD ao inves de mean +/- K*sigma.
    Extremamente resistente a outliers (breakdown point 50%).

    Fator de escala 1.4826 converte MAD em estimador consistente de sigma
    para distribuicoes normais.

    Args:
        values: Lista completa de valores historicos.
        n_periods: Usar os ultimos N periodos.
        n_mad: Multiplicador do MAD escalado (3.0 ~ 99.7% para normal).

    Returns:
        Dict com: lower, upper, center (median), mad_raw, mad_scaled,
        n_mad, n_periods_used.
    """
    MAD_SCALE = 1.4826  # consistency factor for normal distribution
    subset = _last_n(_filter_valid(values), n_periods)
    if len(subset) < 3:
        center = _mean(subset) if subset else 0.0
        return {
            "lower": center, "upper": center, "center": center,
            "mad_raw": 0.0, "mad_scaled": 0.0,
            "n_mad": n_mad, "n_periods_used": len(subset),
        }
    center = _median(subset)
    deviations = [abs(v - center) for v in subset]
    mad_raw = _median(deviations)
    mad_scaled = mad_raw * MAD_SCALE
    return {
        "lower": center - n_mad * mad_scaled,
        "upper": center + n_mad * mad_scaled,
        "center": center,
        "mad_raw": mad_raw,
        "mad_scaled": mad_scaled,
        "n_mad": n_mad,
        "n_periods_used": len(subset),
    }


def detect_outliers(
    values: list[float],
    method: str = "iqr",
    n_periods: int | None = None,
    threshold: float = 1.5,
) -> dict:
    """Detecta outliers usando IQR ou MAD.

    Args:
        values: Lista de valores.
        method: "iqr" ou "mad".
        n_periods: Usar ultimos N periodos (None = todos).
        threshold: Multiplicador (1.5 para IQR, 3.0 para MAD).

    Returns:
        Dict com: outlier_indices (list[int]), outlier_values (list[float]),
        n_outliers (int), pct_outliers (float), band_used (dict).
    """
    clean = _filter_valid(values)

    if method == "iqr":
        band = compute_iqr_band(values, n_periods or len(clean), threshold)
    else:
        band = compute_mad_band(values, n_periods or len(clean), threshold)

    outlier_indices = []
    outlier_values = []
    for i, v in enumerate(values):
        if v is None or (isinstance(v, float) and v != v):
            continue
        if v < band["lower"] or v > band["upper"]:
            outlier_indices.append(i)
            outlier_values.append(v)

    total_valid = len(clean)
    return {
        "outlier_indices": outlier_indices,
        "outlier_values": outlier_values,
        "n_outliers": len(outlier_indices),
        "pct_outliers": len(outlier_indices) / total_valid if total_valid > 0 else 0.0,
        "band_used": band,
        "method": method,
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
    if y_mean != 0:
        has_drift = r_squared > 0.5 and abs(slope) > 0.01 * abs(y_mean)
    else:
        has_drift = r_squared > 0.5

    return {
        "has_drift": has_drift,
        "slope": slope,
        "r_squared": r_squared,
        "n_points": n,
    }


def detect_seasonality(
    values: list[float],
    dates: list[str],
    min_periods: int = 14,
) -> dict:
    """Detecta padroes sazonais (semanal) na serie temporal.

    Analisa se ha variacao significativa por dia da semana.

    Args:
        values: Serie de valores numericos (um por periodo).
        dates: Lista de datas no formato YYYY-MM-DD correspondente a values.
        min_periods: Minimo de periodos necessarios para deteccao confiavel.

    Returns:
        Dict com chaves:
        - has_seasonality (bool): True se padrao semanal detectado
        - seasonality_strength (float): 0.0-1.0 (fracao da variancia explicada)
        - day_of_week_means (dict[int, float]): Media por dia da semana (0=Mon..6=Sun)
        - amplitude (float): Diferenca entre max e min das medias diarias
        - amplitude_ratio (float): amplitude / mean geral (0.0 se mean == 0)
        - message (str): Descricao legivel do resultado
    """
    _DAY_NAMES = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"]

    _empty_result = {
        "has_seasonality": False,
        "seasonality_strength": 0.0,
        "day_of_week_means": {},
        "amplitude": 0.0,
        "amplitude_ratio": 0.0,
        "message": "",
    }

    if not values or not dates or len(values) != len(dates):
        return {**_empty_result, "message": "Dados insuficientes para deteccao de sazonalidade."}

    # 1. Filter valid (non-None, non-NaN) value-date pairs
    valid_pairs: list[tuple[float, str]] = []
    for v, d in zip(values, dates):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        valid_pairs.append((v, d))

    # 2. Insufficient data check
    if len(valid_pairs) < min_periods:
        return {**_empty_result, "message": "Dados insuficientes para deteccao de sazonalidade."}

    # 3. Parse dates to day_of_week
    groups: dict[int, list[float]] = {}
    for v, d in valid_pairs:
        try:
            dow = datetime.strptime(d, "%Y-%m-%d").weekday()  # 0=Monday
        except (ValueError, TypeError):
            continue
        if dow not in groups:
            groups[dow] = []
        groups[dow].append(v)

    if not groups:
        return {**_empty_result, "message": "Dados insuficientes para deteccao de sazonalidade."}

    # 4. Compute mean per day of week
    day_means: dict[int, float] = {}
    for dow, vals in groups.items():
        day_means[dow] = sum(vals) / len(vals)

    # 5. Overall mean and total variance
    all_values = [v for v, _ in valid_pairs]
    total_n = len(all_values)
    overall_mean = sum(all_values) / total_n
    total_variance = sum((v - overall_mean) ** 2 for v in all_values) / total_n

    # 6. Between-group variance
    between_variance = 0.0
    for dow, vals in groups.items():
        n_group = len(vals)
        group_mean = day_means[dow]
        between_variance += n_group * (group_mean - overall_mean) ** 2
    between_variance /= total_n

    # 7. Seasonality strength (eta-squared)
    if total_variance == 0:
        seasonality_strength = 0.0
    else:
        seasonality_strength = max(0.0, min(1.0, between_variance / total_variance))

    # 8. Amplitude
    if day_means:
        amplitude = max(day_means.values()) - min(day_means.values())
    else:
        amplitude = 0.0

    # 9. Amplitude ratio
    if abs(overall_mean) > 0:
        amplitude_ratio = amplitude / abs(overall_mean)
    else:
        amplitude_ratio = 0.0

    # 10. Detection threshold
    # amplitude_ratio > 0.10 avoids false positives from random noise in small samples
    has_seasonality = seasonality_strength > 0.15 and amplitude_ratio > 0.10

    # 11. Build message
    if has_seasonality:
        peak_dow = max(day_means, key=day_means.get)  # type: ignore[arg-type]
        valley_dow = min(day_means, key=day_means.get)  # type: ignore[arg-type]
        peak_name = _DAY_NAMES[peak_dow]
        valley_name = _DAY_NAMES[valley_dow]
        message = (
            f"Pico em {peak_name} (media {day_means[peak_dow]:.2f}), "
            f"vale em {valley_name} (media {day_means[valley_dow]:.2f})."
        )
    else:
        message = "Nenhum padrao semanal significativo detectado."

    return {
        "has_seasonality": has_seasonality,
        "seasonality_strength": seasonality_strength,
        "day_of_week_means": day_means,
        "amplitude": amplitude,
        "amplitude_ratio": amplitude_ratio,
        "message": message,
    }


def detect_change_points(
    values: list[float],
    dates: list[str] | None = None,
    threshold: float = 4.0,
    min_segment: int = 5,
) -> dict:
    """Detecta pontos de mudanca de regime usando CUSUM (Cumulative Sum).

    Identifica quando a serie muda de patamar (ex: migracao de sistema,
    mudanca de regra de negocio). Usa o algoritmo CUSUM bilateral que
    acumula desvios da media e detecta quando o acumulo ultrapassa
    um threshold.

    Args:
        values: Serie de valores numericos.
        dates: Datas correspondentes (opcional, para enriquecer output).
        threshold: Multiplicador do desvio padrao para trigger (4.0 = conservador).
        min_segment: Minimo de pontos em cada segmento para considerar valido.

    Returns:
        Dict com:
        - has_change_point (bool): True se mudanca detectada
        - change_index (int | None): Indice do ponto de mudanca mais recente
        - change_date (str | None): Data do ponto de mudanca (se dates fornecido)
        - n_change_points (int): Total de pontos de mudanca detectados
        - segments (list[dict]): Lista de segmentos com mean/std/start/end
        - post_change_values (list[float]): Valores apos a ultima mudanca
        - post_change_dates (list[str]): Datas apos a ultima mudanca
        - message (str): Descricao legivel do resultado
    """
    _empty_result: dict = {
        "has_change_point": False,
        "change_index": None,
        "change_date": None,
        "n_change_points": 0,
        "segments": [],
        "post_change_values": [],
        "post_change_dates": [],
        "message": "",
    }

    # 1. Filter valid values, tracking original indices
    valid_indices: list[int] = []
    valid_values: list[float] = []
    for i, v in enumerate(values):
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            valid_indices.append(i)
            valid_values.append(v)

    # 2. Need at least 2*min_segment valid values
    if len(valid_values) < 2 * min_segment:
        return {**_empty_result, "message": "Dados insuficientes para deteccao de mudanca de regime."}

    # 3. Compute overall mean and std
    mean = _mean(valid_values)
    std = _stddev(valid_values)

    # 4. If std == 0, no change possible
    if std == 0:
        return {**_empty_result, "message": "Desvio padrao zero — nenhuma mudanca detectada."}

    # 5-6. CUSUM bilateral
    cusum_pos = 0.0
    cusum_neg = 0.0
    slack = 0.5
    raw_change_points: list[int] = []  # indices into valid_values

    for i, v in enumerate(valid_values):
        normalized = (v - mean) / std
        cusum_pos = max(0.0, cusum_pos + normalized - slack)
        cusum_neg = max(0.0, cusum_neg - normalized - slack)

        if cusum_pos > threshold or cusum_neg > threshold:
            raw_change_points.append(i)
            cusum_pos = 0.0
            cusum_neg = 0.0

    # 7. Filter: remove change points that create segments smaller than min_segment
    filtered_cps: list[int] = []
    prev = 0
    for cp in raw_change_points:
        if cp - prev >= min_segment:
            filtered_cps.append(cp)
            prev = cp

    # Also check that the last segment has at least min_segment points
    while filtered_cps and (len(valid_values) - filtered_cps[-1]) < min_segment:
        filtered_cps.pop()

    # 8. No valid change points
    if not filtered_cps:
        # Build single segment covering all data
        segments = [{
            "start": 0,
            "end": len(valid_values),
            "mean": mean,
            "std": std,
        }]
        return {
            **_empty_result,
            "segments": segments,
            "message": "Nenhuma mudanca de regime detectada.",
        }

    # 8. Keep the LAST valid change point as most relevant
    last_cp = filtered_cps[-1]
    last_cp_original_index = valid_indices[last_cp]

    # 9. Build segments
    segments: list[dict] = []
    boundaries = [0] + filtered_cps + [len(valid_values)]
    for j in range(len(boundaries) - 1):
        seg_start = boundaries[j]
        seg_end = boundaries[j + 1]
        seg_values = valid_values[seg_start:seg_end]
        seg_mean = _mean(seg_values) if seg_values else 0.0
        seg_std = _stddev(seg_values) if len(seg_values) >= 2 else 0.0
        segments.append({
            "start": seg_start,
            "end": seg_end,
            "mean": seg_mean,
            "std": seg_std,
        })

    # 10. Post-change values (from original arrays, using the original index)
    post_change_values = values[last_cp_original_index:]
    post_change_dates: list[str] = []
    if dates:
        post_change_dates = dates[last_cp_original_index:]

    # 11. Build message
    change_date = None
    if dates and last_cp_original_index < len(dates):
        change_date = dates[last_cp_original_index]

    # Pre-change segment is second-to-last, post-change is last
    pre_seg = segments[-2] if len(segments) >= 2 else segments[0]
    post_seg = segments[-1]

    if change_date:
        message = (
            f"Mudanca de patamar detectada em {change_date}: "
            f"media mudou de {pre_seg['mean']:.2f} para {post_seg['mean']:.2f}"
        )
    else:
        message = (
            f"Mudanca de patamar detectada no indice {last_cp_original_index}: "
            f"media mudou de {pre_seg['mean']:.2f} para {post_seg['mean']:.2f}"
        )

    return {
        "has_change_point": True,
        "change_index": last_cp_original_index,
        "change_date": change_date,
        "n_change_points": len(filtered_cps),
        "segments": segments,
        "post_change_values": post_change_values,
        "post_change_dates": post_change_dates,
        "message": message,
    }
