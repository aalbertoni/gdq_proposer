"""Parser de logs do Thundera/GDQ para extrair resultados por regra.

Processa o output do Glue job Thundera, identificando a linha
'Resultados GDQ:' seguida de um array Python-like de dicts com:
  - rule: sintaxe GDQ completa
  - outcome: Passed|Failed
  - evaluatedmetrics: dict de metricas avaliadas
  - failurereason: motivo da falha
  - evaluatedrule: regra compilada pelo GDQ (limites expandidos)

Tambem extrai resultados do formato BookQualidades (Salvando {...}).
"""

import ast
import json
import re
from typing import Optional

from core.models.glue_test import GlueRuleResult


def parse_glue_log(log_text: str) -> list[GlueRuleResult]:
    """Extrai resultados de regras GDQ do log do Thundera.

    Busca padroes conhecidos nos logs:
    1. 'Resultados GDQ:' seguido de lista Python (DistribuicaoDeDados)
    2. 'Salvando {' dicts individuais (BookQualidades)

    Args:
        log_text: Texto completo do log do Glue job.

    Returns:
        Lista de GlueRuleResult, um por regra encontrada.
    """
    results: list[GlueRuleResult] = []
    seen_rules: set[str] = set()

    # Pattern 1: "Resultados GDQ:" followed by a Python list of dicts
    results_from_block = _parse_resultados_gdq_block(log_text)
    for r in results_from_block:
        key = r.rule_syntax[:100]
        if key not in seen_rules:
            seen_rules.add(key)
            results.append(r)

    # Pattern 2: "Salvando {" individual dicts from BookQualidades
    results_from_book = _parse_book_qualidades(log_text)
    for r in results_from_book:
        key = r.rule_syntax[:100]
        if key not in seen_rules:
            seen_rules.add(key)
            results.append(r)

    # Pattern 3: "INFO:ModuleName:[{...}]" — direct list after log prefix
    if not results:
        results_from_info = _parse_info_prefix_list(log_text)
        for r in results_from_info:
            key = r.rule_syntax[:100]
            if key not in seen_rules:
                seen_rules.add(key)
                results.append(r)

    # Enrich with labels, category, column, and compiled range
    for r in results:
        r.rule_label = _extract_rule_label(r.rule_syntax)
        r.rule_category, r.target_column = _extract_rule_category_and_column(r.rule_syntax)
        _extract_compiled_range(r)

    return results


def _parse_resultados_gdq_block(log_text: str) -> list[GlueRuleResult]:
    """Parse 'Resultados GDQ:' block containing Python list of dicts.

    Strategy: find the marker, then locate the opening '[' and use bracket
    balancing to extract the full list (handles nested brackets in strings).
    Falls back to line-by-line search with log prefix stripping.
    """
    results = []

    # Strategy 1: Find all text after "Resultados GDQ:" and extract balanced list
    for marker_match in re.finditer(r"Resultados GDQ:", log_text):
        start_pos = marker_match.end()
        list_str = _extract_balanced_list(log_text, start_pos)
        if list_str:
            parsed = _safe_eval_list(list_str)
            if parsed:
                for item in parsed:
                    results.append(_dict_to_rule_result(item))

    # Strategy 2: line-by-line search (handles log prefix on next line)
    if not results:
        lines = log_text.split("\n")
        for i, line in enumerate(lines):
            if "Resultados GDQ" not in line:
                continue

            # Check same line after the colon
            if "Resultados GDQ:" in line:
                after = line.split("Resultados GDQ:")[-1].strip()
                # Strip optional log prefix on same line
                after = _strip_log_prefix(after)
                if after.startswith("["):
                    parsed = _safe_eval_list(after)
                    if parsed:
                        for item in parsed:
                            results.append(_dict_to_rule_result(item))
                        continue

            # Check next lines for the list (may be on separate line with prefix)
            for j in range(i + 1, min(i + 10, len(lines))):
                candidate = _strip_log_prefix(lines[j].strip())
                if candidate.startswith("["):
                    # Collect remaining lines in case list spans multiple lines
                    full_text = candidate
                    if not _is_balanced(full_text, "[", "]"):
                        for k in range(j + 1, min(j + 50, len(lines))):
                            full_text += " " + _strip_log_prefix(lines[k].strip())
                            if _is_balanced(full_text, "[", "]"):
                                break
                    parsed = _safe_eval_list(full_text)
                    if parsed:
                        for item in parsed:
                            results.append(_dict_to_rule_result(item))
                        break
                elif candidate:
                    # Non-empty non-list line — stop looking
                    break

    return results


def _extract_balanced_list(text: str, start_pos: int) -> Optional[str]:
    """Extract a balanced [...] expression from text starting at start_pos.

    Skips whitespace, log prefixes, and newlines to find the opening bracket.
    Then uses bracket counting (ignoring brackets inside strings) to find the end.
    """
    # Skip whitespace, newlines, and log prefixes to find '['
    pos = start_pos
    while pos < len(text):
        ch = text[pos]
        if ch == '[':
            break
        if ch in ' \t\r\n':
            pos += 1
            continue
        # Skip log prefix pattern: "INFO:SomeName:"
        if text[pos:pos + 5] == 'INFO:':
            colon_pos = text.find(':', pos + 5)
            if colon_pos != -1 and colon_pos < pos + 50:
                pos = colon_pos + 1
                continue
        # Not a bracket or known prefix — stop looking
        if pos > start_pos + 200:
            return None
        pos += 1
    else:
        return None

    # Balance brackets (tracking whether we're inside a string)
    depth = 0
    in_single_quote = False
    in_double_quote = False
    i = pos
    while i < len(text):
        ch = text[i]

        # Handle escape sequences
        if ch == '\\' and (in_single_quote or in_double_quote):
            i += 2
            continue

        if ch == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif not in_single_quote and not in_double_quote:
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    return text[pos:i + 1]

        i += 1

    return None


def _is_balanced(text: str, open_ch: str, close_ch: str) -> bool:
    """Check if brackets are balanced (ignoring brackets inside strings)."""
    depth = 0
    in_single = False
    in_double = False
    for i, ch in enumerate(text):
        if ch == '\\' and (in_single or in_double):
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
    return depth == 0


def _strip_log_prefix(line: str) -> str:
    """Strip common log prefixes from a line.

    Handles: timestamps, INFO:ModuleName:, etc.
    """
    s = line.strip()
    # Strip timestamp prefix (e.g. "2026-03-24T12:00:00.000Z ")
    s = re.sub(r"^[\d\-T:.Z]+\s+", "", s)
    # Strip INFO:Module: prefix (possibly chained)
    s = re.sub(r"^(?:INFO|WARNING|ERROR|DEBUG):\w+:", "", s).strip()
    return s


def _parse_info_prefix_list(log_text: str) -> list[GlueRuleResult]:
    """Parse 'INFO:ModuleName:[{...}]' lines containing a Python list of dicts.

    Handles logs like: INFO:DistribuicaoDeDados:[{'rule': ...}, ...]
    """
    results = []
    # Match INFO:AnyModule: followed by a list
    for m in re.finditer(r"(?:INFO|WARNING):\w+:\s*(\[)", log_text):
        start_pos = m.start(1)
        list_str = _extract_balanced_list(log_text, start_pos)
        if list_str:
            parsed = _safe_eval_list(list_str)
            if parsed:
                for item in parsed:
                    results.append(_dict_to_rule_result(item))
    return results


def _parse_book_qualidades(log_text: str) -> list[GlueRuleResult]:
    """Parse individual 'Salvando {...}' dicts from BookQualidades lines."""
    results = []
    pattern = re.compile(r"BookQualidades:Salvando\s+(\{.*?\})\s", re.DOTALL)

    for match in pattern.finditer(log_text):
        raw = match.group(1)
        parsed = _safe_eval_dict(raw)
        if parsed:
            # BookQualidades uses Title Case keys: Rule, Outcome, FailureReason, EvaluatedMetrics
            normalized = {k.lower(): v for k, v in parsed.items()}
            results.append(_dict_to_rule_result(normalized))

    return results


def _dict_to_rule_result(d: dict) -> GlueRuleResult:
    """Convert a raw dict to GlueRuleResult.

    Handles keys: rule, outcome, evaluatedmetrics, failurereason, evaluatedrule.
    """
    rule = d.get("rule", d.get("regragdq", ""))
    outcome = d.get("outcome", "")
    metrics_raw = d.get("evaluatedmetrics", d.get("evaluated_metrics", {}))
    failure = d.get("failurereason", d.get("failure_reason", ""))
    evaluated_rule = d.get("evaluatedrule", d.get("evaluated_rule", ""))

    # Normalize metrics: ensure values are floats
    metrics: dict[str, float] = {}
    if isinstance(metrics_raw, str) and metrics_raw.strip():
        # evaluatedmetrics often comes as a JSON string — parse it first
        try:
            metrics_raw = json.loads(metrics_raw)
        except (json.JSONDecodeError, ValueError):
            pass
    if isinstance(metrics_raw, dict):
        for k, v in metrics_raw.items():
            try:
                metrics[k] = float(v)
            except (ValueError, TypeError):
                metrics[k] = 0.0

    # Clean up failure reason (may have \n separators)
    if isinstance(failure, str):
        failure = failure.replace("\n", " | ").strip()

    return GlueRuleResult(
        rule_syntax=rule,
        outcome=outcome,
        evaluated_metrics=metrics,
        failure_reason=failure,
        evaluated_rule=evaluated_rule,
    )


def _extract_rule_label(syntax: str) -> str:
    """Extract a human-readable label from GDQ rule syntax.

    Examples:
        'Completeness vlr_saldo >= 0.95' -> 'Completeness vlr_saldo'
        'Mean vlr_saldo ...' -> 'Mean vlr_saldo'
        '(CustomSql "select avg(...) from primary" ...)' -> 'CustomSql avg(...)'
        'ColumnValues status in [...]' -> 'ColumnValues status'
    """
    s = syntax.strip()

    # CustomSql: extract the select expression
    m = re.match(r'\(?CustomSql\s+"select\s+(.*?)\s+from\s+primary"', s, re.IGNORECASE)
    if m:
        expr = m.group(1)
        # Shorten long expressions
        if len(expr) > 50:
            expr = expr[:47] + "..."
        return f"CustomSql {expr}"

    # Dual guard wrapped in ((...) OR (...))
    if s.startswith("(("):
        inner = re.match(r'\(\((\w+)\s+(\S+)', s)
        if inner:
            return f"{inner.group(1)} {inner.group(2)}"

    # Standard: RuleName column_or_args
    m = re.match(r'(\w+)\s+(\S+)', s)
    if m:
        return f"{m.group(1)} {m.group(2)}"

    # Fallback: first 40 chars
    return s[:40] if len(s) > 40 else s


def _safe_eval_list(raw: str) -> Optional[list[dict]]:
    """Safely evaluate a Python list literal from log output."""
    try:
        # Try ast.literal_eval first (safest)
        result = ast.literal_eval(raw)
        if isinstance(result, list):
            return result
    except (ValueError, SyntaxError):
        pass

    # Try json.loads with single->double quote replacement
    try:
        cleaned = raw.replace("'", '"')
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    return None


def _extract_rule_category_and_column(syntax: str) -> tuple[str, str]:
    """Extract rule category and target column from GDQ syntax.

    Returns:
        Tuple of (category, column). Category is user-friendly name.
    """
    s = syntax.strip()

    # CustomSql percentile: extract percentile + column
    m = re.search(
        r'CustomSql\s+"select\s+approx_percentile\(\s*cast\((\w+)',
        s, re.IGNORECASE,
    )
    if m:
        return "Percentil", m.group(1)

    # CustomSql frequency: extract column and value from case when
    m = re.search(
        r'CustomSql\s+"select\s+cast\(sum\(case\s+when\s+(\w+)',
        s, re.IGNORECASE,
    )
    if m:
        return "Frequencia", m.group(1)

    # CustomSql generic
    if "CustomSql" in s or "customsql" in s.lower():
        m = re.search(r'select\s+\w+\(.*?(\w+).*?from\s+primary', s, re.IGNORECASE)
        col = m.group(1) if m else ""
        return "CustomSql", col

    # RowCount dual guard: ((RowCount >= ...) or (((RowCount ...))
    if re.search(r'\({2,3}RowCount\b', s):
        return "RowCount", ""

    # RowCount standalone (no column)
    if re.match(r'RowCount\b', s):
        return "RowCount", ""

    # Dual guard: ((Mean COL >= ...) AND ...) OR ...)
    if s.startswith("(("):
        m = re.match(r'\(\((\w+)\s+(\w+)', s)
        if m:
            return m.group(1), m.group(2)

    # IsPrimaryKey: all remaining tokens are columns
    if s.startswith("IsPrimaryKey"):
        cols = s.replace("IsPrimaryKey", "").strip()
        return "IsPrimaryKey", cols

    # Standard: RuleName column ...
    m = re.match(r'(\w+)\s+(\w+)', s)
    if m:
        return m.group(1), m.group(2)

    return "", ""


def _extract_compiled_range(r: GlueRuleResult) -> None:
    """Extract compiled band limits from failure_reason or evaluatedrule.

    GDQ failure reasons often contain patterns like:
    - 'ExpectedRange: [80.5, 120.3]'
    - 'Expected: between 80.5 and 120.3'
    - 'Threshold: >= 0.95'
    - 'Value: 85 does not meet ... type to be one of ...' (type mismatch error)

    The evaluatedrule (compiled rule) may contain actual expanded limits.
    """
    # Try from evaluated_rule first (most reliable for compiled limits)
    evaluated_rule = r.evaluated_rule or ""
    if evaluated_rule:
        _extract_limits_from_evaluated_rule(r, evaluated_rule)
        # If we got limits from evaluatedrule, we're done
        if r.compiled_lower is not None or r.compiled_upper is not None:
            return

    if not r.failure_reason:
        return

    # Pattern: ExpectedRange: [lower, upper]
    m = re.search(r'ExpectedRange:\s*\[\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*\]', r.failure_reason)
    if m:
        try:
            r.compiled_lower = float(m.group(1))
            r.compiled_upper = float(m.group(2))
        except ValueError:
            pass
        return

    # Pattern: Expected ... between X and Y
    m = re.search(r'between\s+([-\d.eE+]+)\s+and\s+([-\d.eE+]+)', r.failure_reason, re.IGNORECASE)
    if m:
        try:
            r.compiled_lower = float(m.group(1))
            r.compiled_upper = float(m.group(2))
        except ValueError:
            pass
        return

    # Pattern: >= threshold (single-sided like Completeness)
    m = re.search(r'>=\s*([-\d.eE+]+)', r.failure_reason)
    if m:
        try:
            r.compiled_lower = float(m.group(1))
        except ValueError:
            pass


def _extract_limits_from_evaluated_rule(r: GlueRuleResult, evaluated_rule: str) -> None:
    """Extract compiled limits from the evaluatedrule (expanded by GDQ).

    The evaluated rule contains the actual numeric limits after GDQ
    expanded dynamic expressions like avg(last(30)).
    """
    # Pattern: between X and Y
    m = re.search(r'between\s+([-\d.eE+]+)\s+and\s+([-\d.eE+]+)', evaluated_rule, re.IGNORECASE)
    if m:
        try:
            r.compiled_lower = float(m.group(1))
            r.compiled_upper = float(m.group(2))
        except ValueError:
            pass
        return

    # Pattern: >= X and <= Y (separate)
    lower_m = re.search(r'>=\s*([-\d.eE+]+)', evaluated_rule)
    upper_m = re.search(r'<=\s*([-\d.eE+]+)', evaluated_rule)
    if lower_m:
        try:
            r.compiled_lower = float(lower_m.group(1))
        except ValueError:
            pass
    if upper_m:
        try:
            r.compiled_upper = float(upper_m.group(1))
        except ValueError:
            pass


def _safe_eval_dict(raw: str) -> Optional[dict]:
    """Safely evaluate a Python dict literal from log output."""
    try:
        result = ast.literal_eval(raw)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass

    return None
