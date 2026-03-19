"""
Perfil estatistico completo de uma serie temporal.

Agrupa regime + flags + metricas de suporte em estrutura coesa.
Usado pelo rule_scoring e rule_explainer para decisoes informadas
sobre a adequacao de cada tipo de regra.

Dependencias: apenas core/models/enums.py.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.models.enums import SeriesRegime


@dataclass(frozen=True)
class SeriesProfile:
    """Perfil estatistico de uma serie temporal.

    Classificacao pragmatica que combina deteccao de regime,
    flags secundarios e metricas de suporte para orientar
    propostas e calibracao de regras DQ.

    Attrs:
        regime: Regime principal (mais dominante).
        secondary_regimes: Regimes adicionais detectados.

        is_volatile: CV > 30%.
        has_trend: Tendencia monotonica (drift).
        is_seasonal: Padrao ciclico (semanal/mensal).
        has_structural_break: Mudanca abrupta de patamar.
        is_zero_inflated: >= 30% zeros.
        is_asymmetric: |skewness| > 1.0.
        is_sparse: >= 30% nulos.

        n_points: Total de pontos na serie.
        n_valid: Pontos nao-nulos.
        cv: Coeficiente de variacao (std/mean).
        skewness: Assimetria da distribuicao.
        zero_pct: Percentual de zeros (0-100).
        null_pct: Percentual de nulos (0-100).
        n_outliers_iqr: Outliers detectados via IQR.
        drift_slope: Inclinacao da tendencia (se detectada).
        drift_r_squared: R-quadrado da tendencia.
        seasonality_strength: Eta-squared (0-1).
        seasonality_amplitude_ratio: Amplitude/media (0-1).
        change_point_date: Data da mudanca de regime (se detectada).
        change_point_magnitude: Magnitude da mudanca (diferenca de medias).
    """

    # Regime principal e secundarios
    regime: SeriesRegime
    secondary_regimes: tuple[SeriesRegime, ...] = ()

    # Flags booleanos
    is_volatile: bool = False
    has_trend: bool = False
    is_seasonal: bool = False
    has_structural_break: bool = False
    is_zero_inflated: bool = False
    is_asymmetric: bool = False
    is_sparse: bool = False

    # Metricas de suporte
    n_points: int = 0
    n_valid: int = 0
    cv: float = 0.0
    skewness: float = 0.0
    zero_pct: float = 0.0
    null_pct: float = 0.0
    n_outliers_iqr: int = 0
    drift_slope: float = 0.0
    drift_r_squared: float = 0.0
    seasonality_strength: float = 0.0
    seasonality_amplitude_ratio: float = 0.0
    change_point_date: Optional[str] = None
    change_point_magnitude: float = 0.0

    @property
    def is_stable(self) -> bool:
        """Serie e estavel (sem nenhum flag ativo)."""
        return self.regime == SeriesRegime.STABLE

    @property
    def regime_count(self) -> int:
        """Numero total de regimes detectados (principal + secundarios)."""
        return 1 + len(self.secondary_regimes)

    @property
    def regime_summary(self) -> str:
        """Resumo textual dos regimes detectados."""
        parts = [self.regime.value]
        for r in self.secondary_regimes:
            parts.append(r.value)
        return " + ".join(parts)
