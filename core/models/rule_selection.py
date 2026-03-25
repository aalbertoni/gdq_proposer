"""
Regra selecionada pelo usuario para exportacao (carrinho).

Definido conforme docs/technical_spec_v1.md secao 3.5.
"""

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from core.models.rule_proposal import RuleProposal

if TYPE_CHECKING:
    from core.models.glue_test import GlueRuleResult


@dataclass
class UserOverride:
    """Ajustes manuais do usuario sobre a proposta."""

    custom_lower: Optional[float] = None
    custom_upper: Optional[float] = None
    custom_values: Optional[list[str]] = None
    custom_n_periods: Optional[int] = None
    custom_n_sigma: Optional[float] = None
    custom_margin_pct: Optional[float] = None
    margin_enabled: Optional[bool] = None
    custom_floor_pct: Optional[float] = None
    custom_ceiling_pct: Optional[float] = None
    notes: str = ""


def _syntax_hash(syntax: str) -> str:
    """Compute hash of normalized GDQ syntax for stale detection."""
    normalized = " ".join(syntax.split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


@dataclass
class RuleSelection:
    """Regra selecionada pelo usuario para exportacao."""

    proposal_id: str
    proposal: RuleProposal
    enabled: bool = True
    user_overrides: Optional[UserOverride] = None
    final_gdq_syntax: str = ""
    # Gerada com base em proposal + overrides

    # Glue test result (populated by write-back after test execution)
    glue_test_result: Optional["GlueRuleResult"] = None
    glue_tested_at: Optional[str] = None
    glue_tested_syntax_hash: Optional[str] = None

    @property
    def has_test_result(self) -> bool:
        """True if this rule has been tested via Glue."""
        return self.glue_test_result is not None

    @property
    def is_test_stale(self) -> bool:
        """True if syntax changed after the test was run."""
        if not self.has_test_result or not self.glue_tested_syntax_hash:
            return False
        return _syntax_hash(self.final_gdq_syntax) != self.glue_tested_syntax_hash
