"""Série estável: média ~100, stddev ~5, sem drift, sem outliers."""

import random


def make_stable_series(n: int = 30, seed: int = 42) -> dict:
    """Gera série numérica estável.

    Returns:
        {"values": list[float], "dates": list[str]}
    """
    rng = random.Random(seed)
    values = [100.0 + rng.gauss(0, 5) for _ in range(n)]
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    return {"values": values, "dates": dates}
