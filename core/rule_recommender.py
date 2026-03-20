"""Motor de recomendacao de regras.

Decide se uma regra proposta merece ser RECOMMENDED, POSSIBLE ou NOT_RECOMMENDED
com base no score, backtest, regime estatistico e contexto da coluna.

Tambem gera explicacoes para colunas excluidas (sem regras propostas).

Principio: nenhuma regra e descartada — o tier apenas orienta a apresentacao.
O usuario sempre pode sobrescrever a recomendacao.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models.enums import (
    ProposalCategory,
    RecommendationTier,
    RuleType,
    SemanticType,
    SeriesRegime,
)
from core.models.rule_proposal import RuleProposal
from core.models.series_profile import SeriesProfile


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Score minimo para RECOMMENDED
SCORE_RECOMMENDED = 0.70
# Score minimo para POSSIBLE
SCORE_POSSIBLE = 0.45
# Coverage minima para RECOMMENDED
COVERAGE_RECOMMENDED = 80.0
# Coverage minima para POSSIBLE
COVERAGE_POSSIBLE = 50.0
# FP maximo para RECOMMENDED
FP_MAX_RECOMMENDED = 2
# FP maximo para POSSIBLE
FP_MAX_POSSIBLE = 5
# Historico minimo para regras dinamicas
MIN_VALID_PERIODS_DYNAMIC = 10

# Tipos de regra dinamica (usam avg(last(N))/std(last(N)))
_DYNAMIC_RULE_TYPES = {
    RuleType.MEAN_DUAL_GUARD,
    RuleType.STDDEV_DUAL_GUARD,
    RuleType.ROW_COUNT_DUAL_GUARD,
    RuleType.CATEGORY_FREQUENCY_DYNAMIC,
    RuleType.CATEGORY_FREQUENCY_HYBRID,
    RuleType.NUMERIC_PERCENTILE_BAND,
}

# Regimes que tornam Mean/StdDev nao recomendados
_HOSTILE_REGIMES_FOR_MEAN = {
    SeriesRegime.STRUCTURAL_BREAK,
}

# Regimes que rebaixam Mean/StdDev para POSSIBLE
_CAUTIOUS_REGIMES_FOR_MEAN = {
    SeriesRegime.SPARSE,
    SeriesRegime.ZERO_INFLATED,
    SeriesRegime.VOLATILE,
}


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def recommend_tier(
    proposal: RuleProposal,
    profile: SeriesProfile | None = None,
    min_periods_dynamic: int = MIN_VALID_PERIODS_DYNAMIC,
    min_periods_possible: int = 5,
) -> tuple[RecommendationTier, list[str]]:
    """Decide tier de recomendacao + justificativas textuais.

    Args:
        proposal: Proposta com backtest e score ja calculados.
        profile: Perfil de regime da serie (opcional).
        min_periods_dynamic: Minimo de periodos para RECOMMENDED (da GrainPolicy).
        min_periods_possible: Minimo de periodos para POSSIBLE (da GrainPolicy).

    Returns:
        Tupla (tier, reasons) onde reasons e lista de strings explicativas.
    """
    reasons: list[str] = []

    # --- Regras de contexto (override por regime) ---
    context_tier = _check_context_rules(proposal, profile, reasons)
    if context_tier == RecommendationTier.NOT_RECOMMENDED:
        return context_tier, reasons

    # --- Sem backtest → nao pode ser RECOMMENDED ---
    bt = proposal.backtest
    if bt is None:
        reasons.append("Sem backtest disponivel")
        return RecommendationTier.NOT_RECOMMENDED, reasons

    # --- Historico insuficiente para regras dinamicas ---
    if proposal.rule_type in _DYNAMIC_RULE_TYPES:
        n_periods = bt.total_periods
        if n_periods < min_periods_possible:
            reasons.append(
                f"Historico insuficiente para regra dinamica "
                f"({n_periods} periodos, minimo {min_periods_possible})"
            )
            return RecommendationTier.NOT_RECOMMENDED, reasons
        if n_periods < min_periods_dynamic:
            reasons.append(
                f"Historico limitado ({n_periods} periodos, "
                f"recomendado {min_periods_dynamic})"
            )
            # Nao retorna — marca como possible mais abaixo

    # --- Metricas do backtest ---
    coverage = bt.coverage_pct
    fp_count = bt.false_positive_proxy
    score = proposal.confidence.value  # fallback

    # Calcular score efetivo a partir do backtest
    score_total = _estimate_score(bt, proposal.rule_type)

    # --- NOT_RECOMMENDED: falhas graves ---
    if coverage < COVERAGE_POSSIBLE:
        reasons.append(f"Cobertura insuficiente ({coverage:.0f}%, minimo {COVERAGE_POSSIBLE:.0f}%)")
        return RecommendationTier.NOT_RECOMMENDED, reasons

    if fp_count > FP_MAX_POSSIBLE:
        reasons.append(f"Alto risco de falso positivo ({fp_count} FPs, maximo {FP_MAX_POSSIBLE})")
        return RecommendationTier.NOT_RECOMMENDED, reasons

    if score_total < SCORE_POSSIBLE:
        reasons.append(f"Score muito baixo ({score_total:.2f}, minimo {SCORE_POSSIBLE:.2f})")
        return RecommendationTier.NOT_RECOMMENDED, reasons

    # --- POSSIBLE: limites intermediarios ---
    is_possible = False

    # Historico limitado (entre min_possible e min_dynamic) → POSSIBLE no maximo
    if (proposal.rule_type in _DYNAMIC_RULE_TYPES
            and bt.total_periods < min_periods_dynamic):
        is_possible = True

    if coverage < COVERAGE_RECOMMENDED:
        reasons.append(f"Cobertura moderada ({coverage:.0f}%)")
        is_possible = True

    if fp_count > FP_MAX_RECOMMENDED:
        reasons.append(f"Risco moderado de falso positivo ({fp_count} FPs)")
        is_possible = True

    if score_total < SCORE_RECOMMENDED:
        reasons.append(f"Score moderado ({score_total:.2f})")
        is_possible = True

    # Context rules podem rebaixar para POSSIBLE
    if context_tier == RecommendationTier.POSSIBLE:
        is_possible = True

    if is_possible:
        return RecommendationTier.POSSIBLE, reasons

    # --- RECOMMENDED ---
    return RecommendationTier.RECOMMENDED, reasons


# ---------------------------------------------------------------------------
# Regras de contexto (regime × rule_type)
# ---------------------------------------------------------------------------

def _check_context_rules(
    proposal: RuleProposal,
    profile: SeriesProfile | None,
    reasons: list[str],
) -> RecommendationTier | None:
    """Aplica regras de contexto baseadas em regime e tipo de regra.

    Returns:
        NOT_RECOMMENDED ou POSSIBLE se regra de contexto dispara, None se nao.
    """
    # Completeness trivial (null_ratio = 0, threshold = 1.0)
    if proposal.rule_type == RuleType.COMPLETENESS:
        threshold = proposal.suggested_lower or 1.0
        if threshold >= 1.0 and _completeness_is_trivial(proposal):
            reasons.append("Completeness trivial: coluna sem nulos no historico")
            return RecommendationTier.NOT_RECOMMENDED

    if profile is None:
        return None

    rule_type = proposal.rule_type
    regime = profile.regime

    # Mean/StdDev em regime hostil
    if rule_type in (RuleType.MEAN_DUAL_GUARD, RuleType.STDDEV_DUAL_GUARD):
        if regime in _HOSTILE_REGIMES_FOR_MEAN:
            reasons.append(
                f"Regime {regime.value}: baseline desalinhado para {_rule_label(rule_type)}"
            )
            return RecommendationTier.NOT_RECOMMENDED

        if regime in _CAUTIOUS_REGIMES_FOR_MEAN:
            reasons.append(
                f"Regime {regime.value}: cautela com {_rule_label(rule_type)}"
            )
            return RecommendationTier.POSSIBLE

        # Secondary regimes also checked
        for sec in profile.secondary_regimes:
            if sec in _HOSTILE_REGIMES_FOR_MEAN:
                reasons.append(
                    f"Regime secundario {sec.value}: risco para {_rule_label(rule_type)}"
                )
                return RecommendationTier.POSSIBLE

    return None


def _completeness_is_trivial(proposal: RuleProposal) -> bool:
    """Verifica se Completeness e trivial: historico com 100% coverage."""
    bt = proposal.backtest
    if bt is None:
        return False
    return bt.coverage_pct >= 100.0 and bt.false_positive_proxy == 0


def _estimate_score(bt, rule_type: RuleType) -> float:
    """Estima score composto a partir do backtest (sem profile)."""
    from core.rule_scoring import (
        WEIGHT_COVERAGE, WEIGHT_STABILITY,
        WEIGHT_INTERPRETABILITY, WEIGHT_COST_EFFICIENCY,
        _INTERPRETABILITY, _COST_EFFICIENCY,
    )
    coverage = bt.coverage_pct / 100.0
    stability = bt.stability_score
    interpretability = _INTERPRETABILITY.get(rule_type, 0.5)
    cost_efficiency = _COST_EFFICIENCY.get(rule_type, 0.5)
    # regime_fit and robustness default to 1.0 without profile
    regime_fit = 1.0
    robustness = 1.0

    score = (
        WEIGHT_COVERAGE * coverage
        + WEIGHT_STABILITY * stability
        + WEIGHT_INTERPRETABILITY * interpretability
        + WEIGHT_COST_EFFICIENCY * cost_efficiency
        + 0.15 * regime_fit
        + 0.15 * robustness
    )
    return max(0.0, min(1.0, score))


def detect_redundancies(proposals: list[RuleProposal]) -> list[RuleProposal]:
    """Detecta regras redundantes e rebaixa para NOT_RECOMMENDED.

    Opera no conjunto de propostas (tipicamente de uma coluna) e aplica
    4 padroes de redundancia. Regras rebaixadas recebem motivo explicativo.
    Nenhuma proposta e removida — apenas o tier e a categoria sao ajustados.

    Padroes:
    R1. AllowedValues + DistinctCountExact → rebaixa DistinctCountExact
    R2. IsPrimaryKey + Completeness (threshold=1.0) → rebaixa Completeness
    R3. Mean + Percentil P50 → rebaixa P50
    """
    if len(proposals) < 2:
        return proposals

    # Indexar por (coluna, tipo) para lookup rapido
    by_col_type: dict[tuple, RuleProposal] = {}
    for p in proposals:
        key = (p.target_column, p.rule_type)
        by_col_type[key] = p

    # Colunas com AllowedValues
    av_cols = {
        p.target_column for p in proposals
        if p.rule_type == RuleType.ALLOWED_VALUES
    }
    # Colunas com IsPrimaryKey (target_column=None para PK de tabela)
    pk_cols: set[str] = set()
    for p in proposals:
        if p.rule_type == RuleType.IS_PRIMARY_KEY and p.suggested_values:
            pk_cols.update(p.suggested_values)
    # Colunas com Mean
    mean_cols = {
        p.target_column for p in proposals
        if p.rule_type == RuleType.MEAN_DUAL_GUARD
    }

    for p in proposals:
        # R1: DistinctCountExact redundante com AllowedValues
        if (p.rule_type == RuleType.DISTINCT_COUNT_EXACT
                and p.target_column in av_cols):
            _mark_redundant(p, "AllowedValues")

        # R2: Completeness redundante com IsPrimaryKey
        if (p.rule_type == RuleType.COMPLETENESS
                and p.target_column in pk_cols
                and (p.suggested_lower or 1.0) >= 1.0):
            _mark_redundant(p, "IsPrimaryKey")

        # R3: Percentil P50 redundante com Mean
        if (p.rule_type == RuleType.NUMERIC_PERCENTILE_BAND
                and p.target_column in mean_cols
                and _is_p50(p)):
            _mark_redundant(p, "Mean")

    return proposals


def _mark_redundant(proposal: RuleProposal, covered_by: str) -> None:
    """Rebaixa proposta para NOT_RECOMMENDED com motivo de redundancia."""
    proposal.recommendation_tier = RecommendationTier.NOT_RECOMMENDED
    proposal.recommendation_reasons.append(
        f"Redundante com {covered_by} na mesma coluna"
    )
    proposal.proposal_category = ProposalCategory.NOT_RECOMMENDED


def _is_p50(proposal: RuleProposal) -> bool:
    """Verifica se proposta de percentil e P50 (mediana)."""
    if proposal.suggested_values and len(proposal.suggested_values) > 0:
        try:
            val = float(proposal.suggested_values[0])
            return abs(val - 0.50) < 0.01
        except (ValueError, TypeError):
            pass
    return "p50" in proposal.metric_name.lower()


# ---------------------------------------------------------------------------
# Modo minimo: subconjunto essencial de alta confianca
# ---------------------------------------------------------------------------

# Tipos de regra elegiveis no modo minimo
_MINIMAL_RULE_TYPES = {
    RuleType.ROW_COUNT_DUAL_GUARD,
    RuleType.IS_PRIMARY_KEY,
    RuleType.COMPLETENESS,
    RuleType.ALLOWED_VALUES,
    RuleType.MEAN_DUAL_GUARD,
}

# Categorias aceitas no modo minimo
_MINIMAL_CATEGORIES = {
    ProposalCategory.STRONG,
    ProposalCategory.CONSERVATIVE,
}


def select_minimal_set(proposals: list[RuleProposal]) -> list[RuleProposal]:
    """Filtra propostas para o conjunto minimo de alta confianca.

    Criterios de inclusao:
    - Tipo de regra elegivel (RowCount, IsPrimaryKey, Completeness, AllowedValues, Mean)
    - Categoria STRONG ou CONSERVATIVE
    - Tier RECOMMENDED
    - Completeness nao trivial (NOT_RECOMMENDED excluida)
    - StdDev excluido (redundante com Mean no modo minimo)
    - Percentis, Frequency, DistinctCount excluidos

    Returns:
        Subconjunto filtrado (nova lista).
    """
    result = []
    # Track quais colunas ja tem Mean para evitar duplicar Mean
    for p in proposals:
        # Tipo elegivel?
        if p.rule_type not in _MINIMAL_RULE_TYPES:
            continue

        # Tier deve ser RECOMMENDED
        if p.recommendation_tier != RecommendationTier.RECOMMENDED:
            continue

        # Categoria deve ser STRONG ou CONSERVATIVE
        if p.proposal_category not in _MINIMAL_CATEGORIES:
            continue

        result.append(p)

    return result


def prioritize_proposals(proposals: list[RuleProposal]) -> list[RuleProposal]:
    """Ordena propostas por relevancia (maior prioridade primeiro).

    Sort key composta:
    1. Tier: RECOMMENDED > POSSIBLE > NOT_RECOMMENDED
    2. Priority score (maior primeiro)
    3. Coverage (maior primeiro)
    4. Falsos positivos (menor primeiro)

    Returns:
        Lista ordenada (novo objeto, nao muta a original).
    """
    return sorted(proposals, key=_sort_key)


_TIER_RANK = {
    RecommendationTier.RECOMMENDED: 2,
    RecommendationTier.POSSIBLE: 1,
    RecommendationTier.NOT_RECOMMENDED: 0,
}


def _sort_key(proposal: RuleProposal) -> tuple:
    """Chave de ordenacao composta (negada para desc onde maior = melhor)."""
    tier_rank = _TIER_RANK.get(proposal.recommendation_tier, 0)
    score = proposal.priority_score
    bt = proposal.backtest
    coverage = bt.coverage_pct if bt else 0.0
    fp = bt.false_positive_proxy if bt else 999

    return (-tier_rank, -score, -coverage, fp)


def compute_priority_score(proposal: RuleProposal) -> float:
    """Calcula priority_score para ordenacao.

    Combina score estimado do backtest com bonus/penalidades de tier.
    Resultado em [0, 1].
    """
    bt = proposal.backtest
    if bt is None:
        return 0.0

    base_score = _estimate_score(bt, proposal.rule_type)

    # Bonus por cobertura ponderada (recencia)
    if bt.weighted_coverage_pct > 0:
        recency_bonus = min(0.05, (bt.weighted_coverage_pct - bt.coverage_pct) / 100.0 * 0.5)
        base_score += max(0.0, recency_bonus)

    # Penalidade por FP
    if bt.false_positive_proxy > 0:
        fp_penalty = min(0.10, bt.false_positive_proxy * 0.02)
        base_score -= fp_penalty

    return max(0.0, min(1.0, round(base_score, 4)))


# ---------------------------------------------------------------------------
# Categorias de proposta (sintese tier × capability × rule_type)
# ---------------------------------------------------------------------------

# Regras simples/built-in (alta interpretabilidade, baixo custo)
_SIMPLE_RULE_TYPES = {
    RuleType.COMPLETENESS,
    RuleType.ALLOWED_VALUES,
    RuleType.DISTINCT_COUNT_EXACT,
    RuleType.DISTINCT_COUNT_RANGE,
    RuleType.IS_PRIMARY_KEY,
}

CATEGORY_LABELS: dict[ProposalCategory, str] = {
    ProposalCategory.STRONG: "Forte",
    ProposalCategory.CONSERVATIVE: "Conservadora",
    ProposalCategory.EXPERIMENTAL: "Experimental",
    ProposalCategory.NEEDS_REVIEW: "Revisar",
    ProposalCategory.NOT_RECOMMENDED: "Nao recomendada",
}

CATEGORY_BADGES: dict[ProposalCategory, str] = {
    ProposalCategory.STRONG: ":green[Forte]",
    ProposalCategory.CONSERVATIVE: ":blue[Conservadora]",
    ProposalCategory.EXPERIMENTAL: ":orange[Experimental]",
    ProposalCategory.NEEDS_REVIEW: ":orange[Revisar]",
    ProposalCategory.NOT_RECOMMENDED: ":red[Nao recomendada]",
}


def classify_proposal(proposal: RuleProposal) -> ProposalCategory:
    """Classifica proposta em categoria operacional unificada.

    Sintese de:
    - RecommendationTier (qualidade da evidencia)
    - GDQCapabilityStatus (maturidade da sintaxe)
    - RuleType (simplicidade da regra)

    Returns:
        ProposalCategory com 1 dos 5 valores.
    """
    from core.gdq_capability import is_experimental

    tier = proposal.recommendation_tier

    # NOT_RECOMMENDED domina tudo
    if tier == RecommendationTier.NOT_RECOMMENDED:
        return ProposalCategory.NOT_RECOMMENDED

    # Experimental capability domina RECOMMENDED e POSSIBLE
    if is_experimental(proposal.rule_type):
        return ProposalCategory.EXPERIMENTAL

    # POSSIBLE + VALIDATED = precisa revisao
    if tier == RecommendationTier.POSSIBLE:
        return ProposalCategory.NEEDS_REVIEW

    # RECOMMENDED + VALIDATED: distinguir forte vs conservadora
    if proposal.rule_type in _SIMPLE_RULE_TYPES:
        return ProposalCategory.CONSERVATIVE

    return ProposalCategory.STRONG


def category_badge(proposal: RuleProposal) -> str:
    """Retorna badge formatado para Streamlit."""
    cat = getattr(proposal, "proposal_category", classify_proposal(proposal))
    return CATEGORY_BADGES.get(cat, cat.value)


# ---------------------------------------------------------------------------
# Explicacao de exclusoes de colunas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColumnExclusion:
    """Justificativa de por que uma coluna nao recebeu regras (ou recebeu poucas)."""
    column_name: str
    semantic_type: SemanticType
    reason: str


# Motivos por tipo semantico
_TYPE_EXCLUSION_REASONS: dict[SemanticType, str] = {
    SemanticType.DATETIME: (
        "Coluna temporal: usada como eixo de analise, nao gera regras de qualidade"
    ),
    SemanticType.IDENTIFIER: (
        "Coluna identificadora: cardinalidade muito alta para regras estatisticas. "
        "Considere IsPrimaryKey se for chave unica"
    ),
    SemanticType.UNKNOWN: (
        "Coluna desconhecida: 100% nula no periodo amostrado"
    ),
    SemanticType.FREE_TEXT: (
        "Texto livre: cardinalidade alta demais para regras de dominio"
    ),
    SemanticType.CATEGORICAL_HIGH_CARDINALITY: (
        "Alta cardinalidade: apenas Completeness aplicavel. "
        "Regras de dominio e frequencia nao sao viaveis"
    ),
}

# Threshold de nulidade para gerar nota
_HIGH_NULL_THRESHOLD = 0.10


def explain_column_exclusions(
    profiles: "list",
) -> list[ColumnExclusion]:
    """Gera explicacoes para colunas que nao recebem regras ou recebem poucas.

    Args:
        profiles: Lista de ColumnProfile selecionados pelo usuario.

    Returns:
        Lista de ColumnExclusion com motivos em pt-BR.
    """
    exclusions: list[ColumnExclusion] = []

    for p in profiles:
        etype = p.effective_type

        # Tipo semantico sem regras completas
        if etype in _TYPE_EXCLUSION_REASONS:
            exclusions.append(ColumnExclusion(
                column_name=p.column_name,
                semantic_type=etype,
                reason=_TYPE_EXCLUSION_REASONS[etype],
            ))
            continue

        # Nulidade alta impede Completeness
        if p.null_ratio > _HIGH_NULL_THRESHOLD:
            exclusions.append(ColumnExclusion(
                column_name=p.column_name,
                semantic_type=etype,
                reason=(
                    f"Nulidade alta ({p.null_ratio:.0%}): "
                    f"Completeness nao aplicavel com threshold padrao"
                ),
            ))

    return exclusions


def _rule_label(rule_type: RuleType) -> str:
    """Label curto para mensagens."""
    from core.models.enums import get_rule_label
    return get_rule_label(rule_type)
