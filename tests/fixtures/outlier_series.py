"""Série estável com 2-3 outliers extremos."""

import random


def make_outlier_series(n: int = 30, seed: int = 42) -> dict:
    """Gera série com outliers em posições fixas (índices 10, 20, 27).

    Returns:
        {"values": list[float], "dates": list[str]}
    """
    rng = random.Random(seed)
    values = [100.0 + rng.gauss(0, 5) for _ in range(n)]
    # Injetar outliers extremos (5x+ do desvio padrão)
    outlier_indices = [10, 20]
    if n > 27:
        outlier_indices.append(27)
    for idx in outlier_indices:
        if idx < n:
            values[idx] = 100.0 + rng.choice([-1, 1]) * 50.0
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    return {"values": values, "dates": dates}
