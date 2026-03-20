"""Resumo executivo da analise.

Agrega indicadores de profiles, proposals, carrinho e regimes
em um dataclass imutavel para renderizacao na UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models.enums import (
    ConfidenceLevel,
    ProposalCategory,
    RecommendationTier,
    SemanticType,
    SeriesRegime,
)
from core.models.rule_proposal import RuleProposal
from core.rule_recommender import ColumnExclusion


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_LOW_COVERAGE_THRESHOLD = 80.0

# Regimes que merecem destaque no resumo executivo
_PROBLEMATIC_REGIMES = {
    SeriesRegime.STRUCTURAL_BREAK,
    SeriesRegime.SPARSE,
    SeriesRegime.VOLATILE,
    SeriesRegime.ZERO_INFLATED,
}

# Mapa de confianca → score numerico para media
_CONFIDENCE_SCORE = {
    ConfidenceLevel.HIGH: 1.0,
    ConfidenceLevel.MEDIUM: 0.5,
    ConfidenceLevel.LOW: 0.0,
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnalysisSummary:
    """Indicadores consolidados da analise para exibicao executiva."""

    # Contagens
    total_columns: int = 0
    columns_with_proposals: int = 0
    columns_in_cart: int = 0
    total_proposals: int = 0
    rules_in_cart: int = 0

    # Distribuicoes
    by_semantic_type: dict[str, int] = field(default_factory=dict)
    by_proposal_category: dict[str, int] = field(default_factory=dict)

    # Alertas
    excluded_columns: list[ColumnExclusion] = field(default_factory=list)
    experimental_in_cart: int = 0
    low_coverage_rules: int = 0
    problematic_regimes: dict[str, list[str]] = field(default_factory=dict)

    # Health
    avg_coverage: float = 0.0
    avg_confidence_score: float = 0.0


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_analysis_summary(
    profiles: list,
    all_proposals: list[RuleProposal],
    cart: list,
    col_health: dict[str, dict] | None = None,
    series_profiles: dict | None = None,
    exclusions: list[ColumnExclusion] | None = None,
) -> AnalysisSummary:
    """Constroi resumo executivo a partir dos dados disponiveis.

    Args:
        profiles: Lista de ColumnProfile selecionados.
        all_proposals: Todas as propostas geradas (flat list).
        cart: Lista de RuleSelection no carrinho.
        col_health: Dict {column: {rule_key: ConfidenceLevel}}.
        series_profiles: Dict {key: SeriesProfile} do session_state.
        exclusions: Exclusoes pre-calculadas (opcional, senao gera internamente).

    Returns:
        AnalysisSummary imutavel.
    """
    if col_health is None:
        col_health = {}
    if series_profiles is None:
        series_profiles = {}

    # --- Exclusoes ---
    if exclusions is None:
        from core.rule_recommender import explain_column_exclusions
        exclusions = explain_column_exclusions(profiles)

    # --- Contagens ---
    total_columns = len(profiles)

    # Colunas com pelo menos 1 proposta RECOMMENDED ou POSSIBLE
    cols_with_proposals = {
        p.target_column for p in all_proposals
        if p.recommendation_tier in (
            RecommendationTier.RECOMMENDED,
            RecommendationTier.POSSIBLE,
        ) and p.target_column is not None
    }
    # Incluir propostas de tabela (target_column=None) se existirem
    has_table_proposals = any(
        p.target_column is None
        and p.recommendation_tier in (
            RecommendationTier.RECOMMENDED,
            RecommendationTier.POSSIBLE,
        )
        for p in all_proposals
    )

    # Colunas no carrinho
    cart_columns = {
        sel.proposal.target_column
        for sel in cart
        if sel.proposal.target_column is not None
    }

    # --- Distribuicao por tipo semantico ---
    by_type: dict[str, int] = {}
    for p in profiles:
        key = p.effective_type.value
        by_type[key] = by_type.get(key, 0) + 1

    # --- Distribuicao por categoria de proposta ---
    by_cat: dict[str, int] = {}
    for p in all_proposals:
        key = p.proposal_category.value
        by_cat[key] = by_cat.get(key, 0) + 1

    # --- Experimentais no carrinho ---
    experimental_count = sum(
        1 for sel in cart
        if sel.proposal.proposal_category == ProposalCategory.EXPERIMENTAL
    )

    # --- Regras com coverage baixa ---
    low_coverage = _count_low_coverage(all_proposals)

    # --- Regimes problematicos ---
    problematic: dict[str, list[str]] = {}
    for key, sp in series_profiles.items():
        if not hasattr(sp, "regime"):
            continue
        if sp.regime in _PROBLEMATIC_REGIMES:
            regime_name = sp.regime.value
            # Extrair nome da coluna do key (format: series_profile_{col}_{lookback})
            col_name = _extract_column_from_key(key)
            if col_name:
                problematic.setdefault(regime_name, []).append(col_name)

    # --- Health medias ---
    coverages = []
    for p in all_proposals:
        if p.backtest is not None and p.recommendation_tier != RecommendationTier.NOT_RECOMMENDED:
            coverages.append(p.backtest.coverage_pct)
    avg_cov = sum(coverages) / len(coverages) if coverages else 0.0

    confidence_scores = []
    for sel in cart:
        score = _CONFIDENCE_SCORE.get(sel.proposal.confidence, 0.5)
        confidence_scores.append(score)
    avg_conf = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

    return AnalysisSummary(
        total_columns=total_columns,
        columns_with_proposals=len(cols_with_proposals) + (1 if has_table_proposals else 0),
        columns_in_cart=len(cart_columns),
        total_proposals=len(all_proposals),
        rules_in_cart=len(cart),
        by_semantic_type=by_type,
        by_proposal_category=by_cat,
        excluded_columns=list(exclusions),
        experimental_in_cart=experimental_count,
        low_coverage_rules=low_coverage,
        problematic_regimes=problematic,
        avg_coverage=round(avg_cov, 1),
        avg_confidence_score=round(avg_conf, 2),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_low_coverage(proposals: list[RuleProposal]) -> int:
    """Conta propostas com coverage abaixo do threshold (exclui NOT_RECOMMENDED)."""
    count = 0
    for p in proposals:
        if p.backtest is None:
            continue
        if p.recommendation_tier == RecommendationTier.NOT_RECOMMENDED:
            continue
        if p.backtest.coverage_pct < _LOW_COVERAGE_THRESHOLD:
            count += 1
    return count


def _extract_column_from_key(key: str) -> str | None:
    """Extrai nome da coluna de uma chave series_profile_{col}_{lookback}."""
    prefix = "series_profile_"
    if not key.startswith(prefix):
        return None
    rest = key[len(prefix):]
    # O lookback é o último segmento após o último _
    parts = rest.rsplit("_", 1)
    if len(parts) == 2:
        col, _ = parts
        return col
    return rest
