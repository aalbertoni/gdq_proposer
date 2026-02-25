"""Série com variação por dia da semana (mais alta Mon/Tue)."""

import random
import math


def make_seasonal_series(n: int = 30, seed: int = 42) -> dict:
    """Gera série com padrão semanal.

    Returns:
        {"values": list[float], "dates": list[str]}
    """
    rng = random.Random(seed)
    values = []
    for i in range(n):
        day_of_week = i % 7
        seasonal = 10.0 * math.sin(2 * math.pi * day_of_week / 7)
        values.append(100.0 + seasonal + rng.gauss(0, 3))
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    return {"values": values, "dates": dates}
