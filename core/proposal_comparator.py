"""
Comparador de propostas de regras.

Permite comparacao lado a lado entre duas propostas para a mesma
coluna/tabela, destacando diferencas em cobertura, estabilidade,
risco e adequacao ao regime.

Funcoes puras — sem I/O, sem UI.

Dependencias: core/models/rule_proposal, core/rule_scoring, core/models/series_profile.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.models.enums import RuleType, SeriesRegime
from core.models.rule_evaluation import RuleEvaluation
from core.models.rule_proposal import RuleProposal
from core.models.series_profile import SeriesProfile
from core.rule_scoring import evaluate_proposal


@dataclass
class ComparisonResult:
    """Resultado da comparacao entre duas propostas.

    Attrs:
        proposal_a_id: ID da proposta A.
        proposal_b_id: ID da proposta B.
        winner: "A", "B", ou "tie".
        score_a: Score total da proposta A.
        score_b: Score total da proposta B.
        advantages_a: Dimensoes onde A supera B.
        advantages_b: Dimensoes onde B supera A.
        summary: Texto resumo da comparacao.
    """

    proposal_a_id: str
    proposal_b_id: str
    winner: str  # "A", "B", "tie"
    score_a: float
    score_b: float
    advantages_a: list[str] = field(default_factory=list)
    advantages_b: list[str] = field(default_factory=list)
    summary: str = ""


# Threshold para considerar uma vantagem significativa
_SIGNIFICANT_DIFF = 0.05

# Labels das dimensoes
_DIMENSION_LABELS = {
    "coverage": "Cobertura",
    "stability": "Estabilidade",
    "interpretability": "Interpretabilidade",
    "cost_efficiency": "Eficiencia",
    "regime_fit": "Adequacao ao regime",
    "robustness": "Robustez dos dados",
    "fp_risk": "Risco de FP",
}


def compare_proposals(
    proposal_a: RuleProposal,
    proposal_b: RuleProposal,
    profile: Optional[SeriesProfile] = None,
) -> ComparisonResult:
    """Compara duas propostas e determina qual e melhor.

    Args:
        proposal_a: Primeira proposta.
        proposal_b: Segunda proposta.
        profile: Perfil de regime da serie (opcional).

    Returns:
        ComparisonResult com vencedor, vantagens e resumo.
    """
    eval_a = evaluate_proposal(proposal_a, profile=profile)
    eval_b = evaluate_proposal(proposal_b, profile=profile)

    advantages_a, advantages_b = _find_advantages(eval_a, eval_b)

    score_diff = eval_a.score_total - eval_b.score_total
    if abs(score_diff) < 0.02:
        winner = "tie"
    elif score_diff > 0:
        winner = "A"
    else:
        winner = "B"

    summary = _build_summary(
        proposal_a, proposal_b,
        eval_a, eval_b,
        winner, advantages_a, advantages_b,
    )

    return ComparisonResult(
        proposal_a_id=proposal_a.id,
        proposal_b_id=proposal_b.id,
        winner=winner,
        score_a=eval_a.score_total,
        score_b=eval_b.score_total,
        advantages_a=advantages_a,
        advantages_b=advantages_b,
        summary=summary,
    )


def _find_advantages(
    eval_a: RuleEvaluation,
    eval_b: RuleEvaluation,
) -> tuple[list[str], list[str]]:
    """Identifica dimensoes onde cada proposta supera a outra."""
    adv_a: list[str] = []
    adv_b: list[str] = []

    # Higher is better
    for dim in ("coverage", "stability", "interpretability",
                "cost_efficiency", "regime_fit", "robustness"):
        val_a = getattr(eval_a, dim)
        val_b = getattr(eval_b, dim)
        label = _DIMENSION_LABELS[dim]
        if val_a - val_b >= _SIGNIFICANT_DIFF:
            adv_a.append(f"{label} ({val_a:.0%} vs {val_b:.0%})")
        elif val_b - val_a >= _SIGNIFICANT_DIFF:
            adv_b.append(f"{label} ({val_b:.0%} vs {val_a:.0%})")

    # Lower is better for fp_risk
    if eval_b.fp_risk - eval_a.fp_risk >= _SIGNIFICANT_DIFF:
        adv_a.append(
            f"Risco de FP ({eval_a.fp_risk:.0%} vs {eval_b.fp_risk:.0%})"
        )
    elif eval_a.fp_risk - eval_b.fp_risk >= _SIGNIFICANT_DIFF:
        adv_b.append(
            f"Risco de FP ({eval_b.fp_risk:.0%} vs {eval_a.fp_risk:.0%})"
        )

    return adv_a, adv_b


def _build_summary(
    prop_a: RuleProposal,
    prop_b: RuleProposal,
    eval_a: RuleEvaluation,
    eval_b: RuleEvaluation,
    winner: str,
    adv_a: list[str],
    adv_b: list[str],
) -> str:
    """Gera texto resumo da comparacao."""
    from core.models.enums import get_rule_label

    label_a = get_rule_label(prop_a.rule_type)
    label_b = get_rule_label(prop_b.rule_type)

    parts: list[str] = []

    if winner == "tie":
        parts.append(
            f"**{label_a}** e **{label_b}** tem desempenho equivalente "
            f"(score {eval_a.score_total:.2f} vs {eval_b.score_total:.2f})."
        )
    elif winner == "A":
        parts.append(
            f"**{label_a}** supera **{label_b}** "
            f"(score {eval_a.score_total:.2f} vs {eval_b.score_total:.2f})."
        )
    else:
        parts.append(
            f"**{label_b}** supera **{label_a}** "
            f"(score {eval_b.score_total:.2f} vs {eval_a.score_total:.2f})."
        )

    if adv_a:
        parts.append(f"Vantagens de {label_a}: {', '.join(adv_a)}.")
    if adv_b:
        parts.append(f"Vantagens de {label_b}: {', '.join(adv_b)}.")

    return " ".join(parts)
