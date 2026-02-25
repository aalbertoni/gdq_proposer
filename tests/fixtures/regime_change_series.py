"""Série com mudança brusca de patamar (ex: migração de sistema)."""

import random


def make_regime_change_series(n: int = 30, seed: int = 42) -> dict:
    """Gera série com dois regimes: primeiros 50% em ~50, últimos 50% em ~200.

    Returns:
        {"values": list[float], "dates": list[str]}
    """
    rng = random.Random(seed)
    mid = n // 2
    values = []
    for i in range(n):
        if i < mid:
            values.append(50.0 + rng.gauss(0, 5))
        else:
            values.append(200.0 + rng.gauss(0, 5))
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    return {"values": values, "dates": dates}
