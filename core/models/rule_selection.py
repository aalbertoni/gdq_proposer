"""
Regra selecionada pelo usuario para exportacao (carrinho).

Definido conforme docs/technical_spec_v1.md secao 3.5.
"""

from dataclasses import dataclass
from typing import Optional

from core.models.rule_proposal import RuleProposal


@dataclass
class UserOverride:
    """Ajustes manuais do usuario sobre a proposta."""

    custom_lower: Optional[float] = None
    custom_upper: Optional[float] = None
    custom_values: Optional[list[str]] = None
    custom_n_periods: Optional[int] = None
    custom_n_sigma: Optional[float] = None
    custom_margin_pct: Optional[float] = None
    notes: str = ""


@dataclass
class RuleSelection:
    """Regra selecionada pelo usuario para exportacao."""

    proposal_id: str
    proposal: RuleProposal
    enabled: bool = True
    user_overrides: Optional[UserOverride] = None
    final_gdq_syntax: str = ""
    # Gerada com base em proposal + overrides
