"""Série com tendência crescente clara (slope ~2 por período)."""

import random


def make_drift_series(n: int = 30, seed: int = 42) -> dict:
    """Gera série com drift linear ascendente.

    Returns:
        {"values": list[float], "dates": list[str]}
    """
    rng = random.Random(seed)
    values = [50.0 + 2.0 * i + rng.gauss(0, 2) for i in range(n)]
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    return {"values": values, "dates": dates}
