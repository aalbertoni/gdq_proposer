"""Deteccao inteligente de formato de data a partir de valores de amostra.

Usado pela setup page para sugerir automaticamente o formato correto
da coluna de data (string ou inteiro) com base em valores reais.
"""

import re


def detect_date_format(
    sample_values: list[str],
    is_integer: bool,
) -> tuple[int, list[str]]:
    """Detect the most likely date format from sample values.

    Args:
        sample_values: Sample values as strings (max 5).
        is_integer: True if column is integer type.

    Returns:
        (best_index, sample_display) where best_index maps to the
        position in the _DATE_PATTERNS list defined in the setup page.
        Integer patterns: 0=yyyyMMdd, 1=yyyyMM, 2=epoch_s, 3=epoch_ms
        String patterns: 0=yyyy-MM-dd, 1=yyyyMMdd, 2=yyyyMM, 3=dd/MM/yyyy, 4=timestamp
    """
    if not sample_values:
        return 0, []

    samples = sample_values[:5]

    if is_integer:
        return _detect_integer_format(samples)
    else:
        return _detect_string_format(samples)


def _detect_integer_format(samples: list[str]) -> tuple[int, list[str]]:
    """Detect format for integer temporal columns."""
    lengths = []
    for v in samples:
        clean = v.strip().replace(".0", "")  # float repr "202401.0" -> "202401"
        if clean.lstrip("-").isdigit():
            lengths.append(len(clean))

    if not lengths:
        return 0, samples

    most_common_len = max(set(lengths), key=lengths.count)

    if most_common_len == 8:
        return 0, samples  # yyyyMMdd
    elif most_common_len == 6:
        return 1, samples  # yyyyMM
    elif most_common_len >= 13:
        return 3, samples  # Epoch milliseconds (check before seconds)
    elif most_common_len >= 10:
        return 2, samples  # Epoch seconds
    else:
        return 0, samples  # Default yyyyMMdd


def _detect_string_format(samples: list[str]) -> tuple[int, list[str]]:
    """Detect format for string temporal columns."""
    patterns = [
        (r'^\d{4}-\d{2}-\d{2}$', 0),                 # yyyy-MM-dd
        (r'^\d{8}$', 1),                               # yyyyMMdd
        (r'^\d{6}$', 2),                               # yyyyMM
        (r'^\d{2}/\d{2}/\d{4}$', 3),                  # dd/MM/yyyy
        (r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}', 4),    # yyyy-MM-dd HH:mm:ss
    ]

    scores = [0] * len(patterns)
    for v in samples:
        v_clean = v.strip()
        for i, (pat, _) in enumerate(patterns):
            if re.match(pat, v_clean):
                scores[i] += 1
                break

    best = max(range(len(scores)), key=lambda i: scores[i])
    if scores[best] > 0:
        return patterns[best][1], samples

    return 0, samples
