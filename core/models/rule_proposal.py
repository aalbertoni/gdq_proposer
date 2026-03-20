"""
Proposta de regra com evidencia e scoring.

Definido conforme docs/technical_spec_v1.md secao 3.5.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.models.enums import BaselineMethod, ConfidenceLevel, RuleType


@dataclass
class BacktestSummary:
    """Resultado do backtest da regra no historico."""

    total_periods: int
    periods_pass: int
    periods_fail: int
    coverage_pct: float  # % dentro da banda
    false_positive_proxy: int  # historicos "normais" reprovados
    band_width_ratio: float  # largura da banda / centro (sensibilidade)
    stability_score: float  # 0-1; banda muda pouco com variacao de n?
    has_drift: bool  # tendencia detectada
    outlier_periods: list[str] = field(default_factory=list)  # datas dos outliers
    weighted_coverage_pct: float = 0.0  # Coverage with recency bias (recent periods weighted more)
    point_results: list[dict] = field(default_factory=list)  # Per-point {index, value, passed}


@dataclass
class RuleProposal:
    """Uma proposta de regra com evidencia e scoring."""

    id: str  # uuid
    target_column: Optional[str]  # None para regras de tabela
    target_table: str
    rule_type: RuleType
    metric_name: str  # ex: "mean", "stddev", "allowed_values"

    # Thresholds sugeridos
    suggested_lower: Optional[float] = None
    suggested_upper: Optional[float] = None
    suggested_values: Optional[list[str]] = None  # para allowed_values
    category_value: Optional[str] = None  # para regras de frequencia: qual valor monitorar
    target_column_type: Optional[str] = None  # tipo Athena da coluna (ex: "string", "int")

    # Baseline
    baseline_method: Optional[BaselineMethod] = None
    baseline_window: Optional[int] = None
    baseline_n_sigma: Optional[float] = None
    baseline_margin_pct: Optional[float] = None
    margin_enabled: bool = True  # Se False, regra usa apenas banda sigma
    floor_pct: Optional[float] = None  # Modo hibrido: limite inferior absoluto (0-100)
    ceiling_pct: Optional[float] = None  # Modo hibrido: limite superior absoluto (0-100)

    # Avaliacao
    backtest: Optional[BacktestSummary] = None
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    warnings: list[str] = field(default_factory=list)

    # Sintaxe
    gdq_syntax_preview: str = ""

    # Sazonalidade (informacional, nao altera sintaxe GDQ)
    seasonality_info: Optional[dict] = None

    # Mudanca de regime (informacional — pode afetar baseline efetivo)
    change_point_info: Optional[dict] = None

    # Estatisticas robustas (informacional, nao altera sintaxe GDQ)
    robust_info: Optional[dict] = None  # IQR/MAD analysis results

    # Historico para grafico (dados agregados, nao raw)
    history_dates: list[str] = field(default_factory=list)
    history_values: list[float] = field(default_factory=list)
