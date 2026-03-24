"""Parser de logs do Thundera/GDQ para extrair resultados por regra.

Processa o output do Glue job Thundera, identificando a linha
'Resultados GDQ:' seguida de um array Python-like de dicts com:
  - rule: sintaxe GDQ completa
  - outcome: Passed|Failed
  - evaluatedmetrics: dict de metricas avaliadas
  - failurereason: motivo da falha

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

    # Enrich with labels, category, column, and compiled range
    for r in results:
        r.rule_label = _extract_rule_label(r.rule_syntax)
        r.rule_category, r.target_column = _extract_rule_category_and_column(r.rule_syntax)
        _extract_compiled_range(r)

    return results


def _parse_resultados_gdq_block(log_text: str) -> list[GlueRuleResult]:
    """Parse 'Resultados GDQ:' block containing Python list of dicts."""
    results = []

    # Find all occurrences of the result list pattern
    # The list may appear on the same line or the next line after "Resultados GDQ:"
    pattern = re.compile(
        r"Resultados GDQ:\s*\n?\s*(?:INFO:\w+:)?\s*(\[.*?\])",
        re.DOTALL,
    )

    for match in pattern.finditer(log_text):
        raw = match.group(1)
        parsed = _safe_eval_list(raw)
        if parsed:
            for item in parsed:
                results.append(_dict_to_rule_result(item))

    # Also try: line starting with INFO:...:[ after "Resultados GDQ"
    if not results:
        lines = log_text.split("\n")
        for i, line in enumerate(lines):
            if "Resultados GDQ" in line:
                # Check same line after the colon
                after = line.split("Resultados GDQ:")[-1].strip() if "Resultados GDQ:" in line else ""
                if after.startswith("["):
                    parsed = _safe_eval_list(after)
                    if parsed:
                        for item in parsed:
                            results.append(_dict_to_rule_result(item))
                # Check next lines for the list
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    # Strip log prefix (e.g. "INFO:DistribuicaoDeDados:")
                    candidate = re.sub(r"^[\d\-T:.Z]+\s*", "", candidate)
                    candidate = re.sub(r"^INFO:\w+:", "", candidate).strip()
                    if candidate.startswith("["):
                        parsed = _safe_eval_list(candidate)
                        if parsed:
                            for item in parsed:
                                results.append(_dict_to_rule_result(item))
                            break

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
    """Convert a raw dict to GlueRuleResult."""
    rule = d.get("rule", d.get("regragdq", ""))
    outcome = d.get("outcome", "")
    metrics_raw = d.get("evaluatedmetrics", d.get("evaluated_metrics", {}))
    failure = d.get("failurereason", d.get("failure_reason", ""))

    # Normalize metrics: ensure values are floats
    metrics: dict[str, float] = {}
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

    # Dual guard: (((Mean COL >= ...) AND ...)) OR ...)
    if s.startswith("(("):
        m = re.match(r'\(\((\w+)\s+(\w+)', s)
        if m:
            return m.group(1), m.group(2)

    # RowCount dual guard: (((RowCount >= ...) AND ...))
    if s.startswith("(((RowCount"):
        return "RowCount", ""

    # RowCount standalone (no column)
    if re.match(r'RowCount\b', s):
        return "RowCount", ""

    # IsPrimaryKey: all remaining tokens are columns
    if s.startswith("IsPrimaryKey"):
        cols = s.replace("IsPrimaryKey", "").strip()
        return "IsPrimaryKey", cols

    # Standard: RuleName column ...
    m = re.match(r'(\w+)\s+(\w+)', s)
    if m:
        return m.group(1), m.group(2)

    return "", ""


def _extract_compiled_range(r) -> None:
    """Extract compiled band limits from failure_reason.

    GDQ failure reasons often contain patterns like:
    - 'ExpectedRange: [80.5, 120.3]'
    - 'Expected: between 80.5 and 120.3'
    - 'Threshold: >= 0.95'
    """
    if not r.failure_reason:
        return

    # Pattern: ExpectedRange: [lower, upper]
    m = re.search(r'ExpectedRange:\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]', r.failure_reason)
    if m:
        try:
            r.compiled_lower = float(m.group(1))
            r.compiled_upper = float(m.group(2))
        except ValueError:
            pass
        return

    # Pattern: Expected ... between X and Y
    m = re.search(r'between\s+([-\d.]+)\s+and\s+([-\d.]+)', r.failure_reason, re.IGNORECASE)
    if m:
        try:
            r.compiled_lower = float(m.group(1))
            r.compiled_upper = float(m.group(2))
        except ValueError:
            pass
        return

    # Pattern: >= threshold (single-sided like Completeness)
    m = re.search(r'>=\s*([-\d.]+)', r.failure_reason)
    if m:
        try:
            r.compiled_lower = float(m.group(1))
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
