"""Série com ~60% zeros (ex: colunas monetárias com muitas ops zeradas)."""

import random


def make_zero_inflated_series(n: int = 30, seed: int = 42) -> dict:
    """Gera série onde ~60% dos valores são 0.0.

    Returns:
        {"values": list[float], "dates": list[str]}
    """
    rng = random.Random(seed)
    values = []
    for i in range(n):
        if rng.random() < 0.6:
            values.append(0.0)
        else:
            values.append(abs(rng.gauss(50, 20)))
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    return {"values": values, "dates": dates}
