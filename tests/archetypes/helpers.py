"""Helpers minimos para geracao de dados sinteticos em archetypes."""

import pandas as pd


def make_date_range(
    n_periods: int = 30,
    start: str = "2026-01-01",
    freq: str = "D",
) -> list[str]:
    """Gera lista de datas como strings ISO."""
    return (
        pd.date_range(start, periods=n_periods, freq=freq)
        .strftime("%Y-%m-%d")
        .tolist()
    )


def make_int_dates(
    n_periods: int = 30,
    start: str = "2026-01-01",
    fmt: str = "%Y%m%d",
) -> list[int]:
    """Gera lista de datas como inteiros (ex: 20260101)."""
    return [
        int(d.strftime(fmt))
        for d in pd.date_range(start, periods=n_periods)
    ]


def repeat_for_rows(values: list, rows_per_period: int) -> list:
    """Repete cada valor N vezes para simular rows por periodo."""
    result = []
    for v in values:
        result.extend([v] * rows_per_period)
    return result
