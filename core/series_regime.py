"""
Classificacao de regime estatistico de series temporais.

Combina os detectores do statistical_engine (drift, seasonality,
change-points, outliers) com metricas descritivas (CV, skewness,
zero%, null%) para produzir um SeriesProfile completo.

Funcoes puras — sem I/O, sem Athena, sem UI.

Dependencias: core/statistical_engine, core/models/series_profile.
"""

import math

from core.models.enums import SeriesRegime
from core.models.series_profile import SeriesProfile
from core.statistical_engine import (
    _filter_valid,
    detect_change_points,
    detect_drift,
    detect_outliers,
    detect_seasonality,
)

# Thresholds de classificacao
CV_VOLATILE_THRESHOLD = 0.30       # CV > 30% → volatil
SKEWNESS_THRESHOLD = 1.0           # |skew| > 1.0 → assimetrica
ZERO_INFLATED_THRESHOLD = 30.0     # >= 30% zeros → zero-inflated
SPARSE_THRESHOLD = 30.0            # >= 30% nulos → esparsa
SEASONALITY_MIN_POINTS = 14        # minimo para detectar sazonalidade


def classify_series(
    values: list[float],
    dates: list[str],
) -> SeriesProfile:
    """Classifica serie temporal em regime estatistico.

    Executa deteccao de drift, sazonalidade, change-points e outliers,
    calcula metricas descritivas, e determina o regime principal.

    Args:
        values: Serie temporal de valores (pode conter NaN/None).
        dates: Datas correspondentes (mesmo length).

    Returns:
        SeriesProfile com regime principal, flags e metricas.
    """
    n_points = len(values)
    valid = _filter_valid(values)
    n_valid = len(valid)

    if n_valid < 3:
        return SeriesProfile(
            regime=SeriesRegime.STABLE,
            n_points=n_points,
            n_valid=n_valid,
            null_pct=_null_pct(n_points, n_valid),
            is_sparse=_null_pct(n_points, n_valid) >= SPARSE_THRESHOLD,
        )

    # Metricas descritivas basicas
    mean = sum(valid) / n_valid
    variance = sum((v - mean) ** 2 for v in valid) / max(n_valid - 1, 1)
    std = math.sqrt(variance)
    cv = std / abs(mean) if abs(mean) > 1e-10 else 0.0
    skewness = _compute_skewness(valid, mean, std)
    zero_count = sum(1 for v in valid if abs(v) < 1e-10)
    zero_pct = (zero_count / n_valid) * 100 if n_valid > 0 else 0.0
    null_pct = _null_pct(n_points, n_valid)

    # Deteccao de outliers (IQR)
    outlier_result = detect_outliers(valid, method="iqr", n_periods=n_valid)
    n_outliers_iqr = outlier_result.get("n_outliers", 0)

    # Deteccao de drift
    drift_result = detect_drift(values)
    has_trend = drift_result.get("has_drift", False)
    drift_slope = drift_result.get("slope", 0.0)
    drift_r_squared = drift_result.get("r_squared", 0.0)

    # Deteccao de sazonalidade
    is_seasonal = False
    seasonality_strength = 0.0
    seasonality_amplitude_ratio = 0.0
    if n_valid >= SEASONALITY_MIN_POINTS:
        season_result = detect_seasonality(values, dates)
        is_seasonal = season_result.get("has_seasonality", False)
        seasonality_strength = season_result.get("seasonality_strength", 0.0)
        seasonality_amplitude_ratio = season_result.get("amplitude_ratio", 0.0)

    # Deteccao de change-point
    change_result = detect_change_points(values, dates)
    has_structural_break = (
        change_result.get("has_change_point", False)
        and len(change_result.get("post_change_values", [])) >= 5
    )
    change_point_date = change_result.get("change_date") if has_structural_break else None
    change_point_magnitude = 0.0
    if has_structural_break:
        segments = change_result.get("segments", [])
        if len(segments) >= 2:
            change_point_magnitude = abs(segments[-1]["mean"] - segments[0]["mean"])

    # Flags booleanos
    is_volatile = cv > CV_VOLATILE_THRESHOLD
    is_asymmetric = abs(skewness) > SKEWNESS_THRESHOLD
    is_zero_inflated = zero_pct >= ZERO_INFLATED_THRESHOLD
    is_sparse = null_pct >= SPARSE_THRESHOLD

    # Determinar regime principal + secundarios
    regime, secondary = _determine_regime(
        has_structural_break=has_structural_break,
        has_trend=has_trend,
        is_seasonal=is_seasonal,
        is_volatile=is_volatile,
        is_zero_inflated=is_zero_inflated,
        is_asymmetric=is_asymmetric,
        is_sparse=is_sparse,
    )

    return SeriesProfile(
        regime=regime,
        secondary_regimes=tuple(secondary),
        is_volatile=is_volatile,
        has_trend=has_trend,
        is_seasonal=is_seasonal,
        has_structural_break=has_structural_break,
        is_zero_inflated=is_zero_inflated,
        is_asymmetric=is_asymmetric,
        is_sparse=is_sparse,
        n_points=n_points,
        n_valid=n_valid,
        cv=round(cv, 4),
        skewness=round(skewness, 4),
        zero_pct=round(zero_pct, 2),
        null_pct=round(null_pct, 2),
        n_outliers_iqr=n_outliers_iqr,
        drift_slope=round(drift_slope, 6),
        drift_r_squared=round(drift_r_squared, 4),
        seasonality_strength=round(seasonality_strength, 4),
        seasonality_amplitude_ratio=round(seasonality_amplitude_ratio, 4),
        change_point_date=change_point_date,
        change_point_magnitude=round(change_point_magnitude, 4),
    )


def _determine_regime(
    *,
    has_structural_break: bool,
    has_trend: bool,
    is_seasonal: bool,
    is_volatile: bool,
    is_zero_inflated: bool,
    is_asymmetric: bool,
    is_sparse: bool,
) -> tuple[SeriesRegime, list[SeriesRegime]]:
    """Determina regime principal e secundarios por prioridade.

    Prioridade (do mais impactante para recomendacao ao menos):
    1. STRUCTURAL_BREAK — muda completamente a baseline efetiva
    2. TRENDING — baseline movel, regra precisa acompanhar
    3. SEASONAL — ciclos afetam banda, N deve ser multiplo
    4. ZERO_INFLATED — distribuicao degenerada
    5. SPARSE — dados insuficientes afetam confiabilidade
    6. VOLATILE — banda larga, risco de FP
    7. ASYMMETRIC — bandas simetricas podem nao ser ideais
    8. STABLE — nenhuma anomalia detectada

    Returns:
        (regime_principal, [regimes_secundarios])
    """
    candidates: list[SeriesRegime] = []

    if has_structural_break:
        candidates.append(SeriesRegime.STRUCTURAL_BREAK)
    if has_trend:
        candidates.append(SeriesRegime.TRENDING)
    if is_seasonal:
        candidates.append(SeriesRegime.SEASONAL)
    if is_zero_inflated:
        candidates.append(SeriesRegime.ZERO_INFLATED)
    if is_sparse:
        candidates.append(SeriesRegime.SPARSE)
    if is_volatile:
        candidates.append(SeriesRegime.VOLATILE)
    if is_asymmetric:
        candidates.append(SeriesRegime.ASYMMETRIC)

    if not candidates:
        return SeriesRegime.STABLE, []

    return candidates[0], candidates[1:]


def _compute_skewness(values: list[float], mean: float, std: float) -> float:
    """Calcula skewness (assimetria) da distribuicao.

    Usa formula de Fisher (terceiro momento padronizado).
    Retorna 0.0 se std e zero ou menos de 3 pontos.
    """
    n = len(values)
    if n < 3 or std < 1e-10:
        return 0.0
    m3 = sum((v - mean) ** 3 for v in values) / n
    return m3 / (std ** 3)


def _null_pct(n_total: int, n_valid: int) -> float:
    """Calcula percentual de nulos."""
    if n_total == 0:
        return 0.0
    return ((n_total - n_valid) / n_total) * 100
