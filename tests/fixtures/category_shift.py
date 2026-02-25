"""Fixtures categoricas: distribuicoes com shift, estaveis, raras e emergentes.

Gera dados para testar:
- compute_frequency_band (por categoria individual)
- backtest_frequency_band (serie temporal de % de uma categoria)
- Deteccao de shift, categorias raras e emergentes
"""

import random


def _build_result(n: int, dates: list[str], distributions: list[dict]) -> dict:
    """Constroi dict padrao a partir de distribuicoes por periodo."""
    all_cats = set()
    for d in distributions:
        all_cats.update(d.keys())
    domain = sorted(all_cats)

    series = {}
    for cat in domain:
        series[cat] = [d.get(cat, 0.0) for d in distributions]

    distinct_counts = [len([c for c in domain if d.get(c, 0.0) > 0]) for d in distributions]

    return {
        "dates": dates,
        "distributions": distributions,
        "series": series,
        "domain": domain,
        "distinct_counts": distinct_counts,
    }


def make_category_shift(n: int = 30, seed: int = 42) -> dict:
    """Distribuicao categorica com shift no meio.

    Primeira metade: A=70%, B=20%, C=10%
    Segunda metade: A=30%, B=50%, C=20%

    Returns:
        dict com dates, distributions, series, domain, distinct_counts
    """
    rng = random.Random(seed)
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    distributions = []

    mid = n // 2
    for i in range(n):
        if i < mid:
            a = max(0, 70.0 + rng.gauss(0, 2))
            b = max(0, 20.0 + rng.gauss(0, 1.5))
        else:
            a = max(0, 30.0 + rng.gauss(0, 2))
            b = max(0, 50.0 + rng.gauss(0, 2))
        c = max(0, 100.0 - a - b)
        total = a + b + c
        distributions.append({
            "A": round(a / total * 100, 2),
            "B": round(b / total * 100, 2),
            "C": round(c / total * 100, 2),
        })

    return _build_result(n, dates, distributions)


def make_stable_categories(n: int = 30, seed: int = 42) -> dict:
    """Distribuicao categorica estavel com 4 categorias.

    A=50%, B=30%, C=15%, D=5% com ruido pequeno (~1pp).
    """
    rng = random.Random(seed)
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    distributions = []

    for _ in range(n):
        a = max(0, 50.0 + rng.gauss(0, 1))
        b = max(0, 30.0 + rng.gauss(0, 1))
        c = max(0, 15.0 + rng.gauss(0, 0.8))
        d = max(0, 5.0 + rng.gauss(0, 0.5))
        total = a + b + c + d
        distributions.append({
            "A": round(a / total * 100, 2),
            "B": round(b / total * 100, 2),
            "C": round(c / total * 100, 2),
            "D": round(d / total * 100, 2),
        })

    return _build_result(n, dates, distributions)


def make_rare_category(n: int = 30, seed: int = 42) -> dict:
    """Uma categoria dominante (95%), uma rara (2%), uma media (3%).

    Testa clamping inferior da banda em -0.01.
    """
    rng = random.Random(seed)
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    distributions = []

    for _ in range(n):
        a = max(0, 95.0 + rng.gauss(0, 0.5))
        b = max(0, 2.0 + rng.gauss(0, 0.3))
        c = max(0, 100.0 - a - b)
        total = a + b + c
        distributions.append({
            "DOM": round(a / total * 100, 2),
            "RARE": round(b / total * 100, 2),
            "MED": round(c / total * 100, 2),
        })

    return _build_result(n, dates, distributions)


def make_emerging_category(n: int = 30, seed: int = 42) -> dict:
    """Categoria D aparece nos ultimos 1/3 dos periodos.

    Primeiros 2/3: A=60%, B=30%, C=10%
    Ultimo 1/3: A=45%, B=25%, C=10%, D=20%
    """
    rng = random.Random(seed)
    dates = [f"2026-01-{i + 1:02d}" for i in range(n)]
    distributions = []

    cutoff = n * 2 // 3
    for i in range(n):
        if i < cutoff:
            a = max(0, 60.0 + rng.gauss(0, 2))
            b = max(0, 30.0 + rng.gauss(0, 1.5))
            c = max(0, 100.0 - a - b)
            total = a + b + c
            distributions.append({
                "A": round(a / total * 100, 2),
                "B": round(b / total * 100, 2),
                "C": round(c / total * 100, 2),
            })
        else:
            a = max(0, 45.0 + rng.gauss(0, 2))
            b = max(0, 25.0 + rng.gauss(0, 1.5))
            c = max(0, 10.0 + rng.gauss(0, 1))
            d = max(0, 20.0 + rng.gauss(0, 1.5))
            total = a + b + c + d
            distributions.append({
                "A": round(a / total * 100, 2),
                "B": round(b / total * 100, 2),
                "C": round(c / total * 100, 2),
                "D": round(d / total * 100, 2),
            })

    return _build_result(n, dates, distributions)
