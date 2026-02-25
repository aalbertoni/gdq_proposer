"""Série com ~40% de NaN intercalados."""

import random
import math


def make_sparse_numeric_series(n: int = 30, seed: int = 42) -> dict:
    """Gera série com ~40% dos valores como NaN.

    Returns:
        {"values": list[float], "dates": list[str]}
    """
    rng = random.Random(seed)
    values = []
    for i in range(n):
        if rng.random() < 0.4:
            values.append(float("nan"))
        else:
            values.append(100.0 + rng.gauss(0, 5))
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    return {"values": values, "dates": dates}
