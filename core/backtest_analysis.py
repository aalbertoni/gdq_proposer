"""
Analise enriquecida de resultados de backtest.

Computa metricas derivadas a partir de BacktestSummary:
streaks de falha consecutivas, taxa de violacao,
e analise de sensibilidade.

Funcoes puras — sem I/O, sem UI.

Dependencias: core/models/rule_proposal.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.models.rule_proposal import BacktestSummary


@dataclass
class BacktestAnalysis:
    """Analise enriquecida dos resultados de backtest.

    Attrs:
        max_fail_streak: Maior sequencia consecutiva de falhas.
        max_pass_streak: Maior sequencia consecutiva de passes.
        current_streak_type: "pass" ou "fail" (mais recente).
        current_streak_length: Comprimento da streak atual.
        violation_rate: Falhas por periodo avaliado (0-1).
        recent_violation_rate: Falhas nos ultimos 7 periodos avaliados.
        tail_risk: Percentual de falhas nos ultimos 20% dos dados.
        first_fail_index: Indice do primeiro ponto que falhou.
        last_fail_index: Indice do ultimo ponto que falhou.
    """

    max_fail_streak: int = 0
    max_pass_streak: int = 0
    current_streak_type: str = "pass"
    current_streak_length: int = 0
    violation_rate: float = 0.0
    recent_violation_rate: float = 0.0
    tail_risk: float = 0.0
    first_fail_index: Optional[int] = None
    last_fail_index: Optional[int] = None


def analyze_backtest(bt: BacktestSummary) -> BacktestAnalysis:
    """Analisa resultados de backtest para metricas enriquecidas.

    Args:
        bt: BacktestSummary com point_results.

    Returns:
        BacktestAnalysis com streaks, violation rate e tail risk.
    """
    results = bt.point_results
    if not results:
        return BacktestAnalysis()

    # Streaks
    max_fail = 0
    max_pass = 0
    cur_fail = 0
    cur_pass = 0
    first_fail = None
    last_fail = None

    for r in results:
        if r["passed"]:
            cur_pass += 1
            cur_fail = 0
        else:
            cur_fail += 1
            cur_pass = 0
            if first_fail is None:
                first_fail = r["index"]
            last_fail = r["index"]
        max_fail = max(max_fail, cur_fail)
        max_pass = max(max_pass, cur_pass)

    # Current streak (from last result)
    cur_type = "pass" if results[-1]["passed"] else "fail"
    cur_length = 0
    for r in reversed(results):
        if (cur_type == "pass" and r["passed"]) or (cur_type == "fail" and not r["passed"]):
            cur_length += 1
        else:
            break

    # Violation rate
    n_total = len(results)
    n_fails = sum(1 for r in results if not r["passed"])
    violation_rate = n_fails / n_total if n_total > 0 else 0.0

    # Recent violation rate (last 7 evaluated)
    recent = results[-7:] if len(results) >= 7 else results
    n_recent_fails = sum(1 for r in recent if not r["passed"])
    recent_violation_rate = n_recent_fails / len(recent) if recent else 0.0

    # Tail risk (last 20% of data)
    tail_size = max(1, n_total // 5)
    tail = results[-tail_size:]
    n_tail_fails = sum(1 for r in tail if not r["passed"])
    tail_risk = n_tail_fails / len(tail) if tail else 0.0

    return BacktestAnalysis(
        max_fail_streak=max_fail,
        max_pass_streak=max_pass,
        current_streak_type=cur_type,
        current_streak_length=cur_length,
        violation_rate=round(violation_rate, 4),
        recent_violation_rate=round(recent_violation_rate, 4),
        tail_risk=round(tail_risk, 4),
        first_fail_index=first_fail,
        last_fail_index=last_fail,
    )


def summarize_backtest_analysis(analysis: BacktestAnalysis) -> str:
    """Gera texto resumo da analise de backtest.

    Args:
        analysis: Resultado de analyze_backtest().

    Returns:
        Texto em pt-BR com insights sobre o comportamento da regra.
    """
    parts: list[str] = []

    if analysis.max_fail_streak >= 3:
        parts.append(
            f"**Sequencia de falhas:** ate {analysis.max_fail_streak} "
            f"periodos consecutivos falharam — pode indicar mudanca de regime."
        )

    if analysis.recent_violation_rate > analysis.violation_rate * 1.5 and analysis.recent_violation_rate > 0.1:
        parts.append(
            f"**Degradacao recente:** taxa de violacao recente "
            f"({analysis.recent_violation_rate:.0%}) esta acima da historica "
            f"({analysis.violation_rate:.0%}) — parametros podem estar defasados."
        )

    if analysis.tail_risk > 0.30:
        parts.append(
            f"**Risco na cauda:** {analysis.tail_risk:.0%} dos pontos mais "
            f"recentes falharam — a regra pode estar se tornando inadequada."
        )

    if analysis.violation_rate == 0.0 and analysis.max_pass_streak > 0:
        parts.append(
            f"**Cobertura perfeita:** todos os {analysis.max_pass_streak} "
            f"periodos avaliados passaram."
        )

    if not parts:
        return ""

    return "\n".join(parts)
