"""
Avaliacao enriquecida de regra proposta.

Combina o RuleScore existente com dimensoes adicionais:
regime_fit, fp_risk, robustness, e warnings contextuais.

Usado pela UI para fornecer orientacao mais detalhada ao usuario.

Dependencias: core/models/enums.py, core/rule_scoring.py.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.models.enums import ConfidenceLevel, SeriesRegime


@dataclass
class RuleEvaluation:
    """Avaliacao enriquecida com contexto de regime.

    Attrs:
        coverage: Cobertura do backtest (0-1).
        stability: Estabilidade da banda (0-1).
        interpretability: Legibilidade da regra (0-1).
        cost_efficiency: Eficiencia computacional (0-1).
        regime_fit: Adequacao da regra ao regime da serie (0-1).
        fp_risk: Risco de falsos positivos (0-1, 0=baixo risco).
        robustness: Qualidade e confiabilidade dos dados (0-1).
        false_positive_count: Estimativa de FPs no backtest.
        sensitivity: Razao largura da banda / centro.
        score_total: Score composto ponderado.
        confidence: Nivel de confianca final.
        recommendation: Texto de recomendacao.
        regime_summary: Resumo do regime detectado (se disponivel).
        regime_warnings: Alertas especificos do regime.
        warnings: Alertas gerais.
    """

    # Dimensoes classicas (backward-compatible)
    coverage: float
    stability: float
    interpretability: float
    cost_efficiency: float

    # Novas dimensoes
    regime_fit: float = 1.0
    fp_risk: float = 0.0
    robustness: float = 1.0

    # Metricas
    false_positive_count: int = 0
    sensitivity: float = 0.0
    score_total: float = 0.0
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    recommendation: str = ""

    # Contexto de regime
    regime_summary: Optional[str] = None
    regime_warnings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
