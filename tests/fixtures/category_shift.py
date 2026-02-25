"""Distribuição categórica que muda ao longo do tempo (Sprint B2 scope)."""


def make_category_shift(n: int = 30) -> dict:
    """Stub — será implementada no Sprint B2 para categorias.

    Returns:
        {"categories": list[dict], "dates": list[str]}
    """
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    categories = [{"A": 0.7, "B": 0.2, "C": 0.1}] * (n // 2) + \
                 [{"A": 0.3, "B": 0.5, "C": 0.2}] * (n - n // 2)
    return {"categories": categories, "dates": dates}
