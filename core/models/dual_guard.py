"""
Representacao intermediaria do padrao dual guard.

Definido conforme docs/technical_spec_v1.md secao 3.4.

Nunca gerar string GDQ diretamente -- sempre montar DualGuardSpec
e passar pelo DualGuardRenderer.
"""

from dataclasses import dataclass

from core.models.enums import MetricRef


@dataclass
class FormattingProfile:
    """Diferencas de formatacao por tipo de regra.

    Mean/StdDev: K inteiro, buffer 0.01, margem como 'avg * factor'
    RowCount: K float (2.0), sem buffer, margem como 'avg - (avg * pct)', avg * 1.0
    CustomSql: SQL entre aspas duplas, valores entre aspas simples, from primary
    """

    k_as_float: bool = False  # True para RowCount (2.0), False para Mean/StdDev (2)
    include_buffer: bool = True  # True para Mean/StdDev, False para RowCount
    avg_multiply_one: bool = False  # True para RowCount (avg * 1.0)
    margin_format: str = "factor"  # "factor" -> avg * 0.9/1.1; "delta" -> avg - (avg * 0.1)


# Profiles pre-definidos
MEAN_PROFILE = FormattingProfile()
STDDEV_PROFILE = FormattingProfile()
ROWCOUNT_PROFILE = FormattingProfile(
    k_as_float=True,
    include_buffer=False,
    avg_multiply_one=True,
    margin_format="delta",
)


@dataclass
class DualGuardSpec:
    """Representacao intermediaria do padrao dual guard.

    A representacao e:
      (banda_sigma) OR (banda_margem)    [quando margin_enabled=True]
      (banda_sigma)                       [quando margin_enabled=False]

    Onde:
      banda_sigma: metric >= avg(last(N)) - K*std(last(N)) [-buffer]
                   AND metric <= avg(last(N)) + K*std(last(N)) [+buffer]
      banda_margem: metric >= avg(last(N)) * lo_margin [-buffer]
                    AND metric <= avg(last(N)) * hi_margin [+buffer]
    """

    metric: MetricRef
    target: str = ""  # nome da coluna (vazio para RowCount)
    n_periods: int = 30
    n_sigma: float = 2  # int para Mean/StdDev, float para RowCount
    margin_pct: float = 0.10
    buffer: float = 0.01  # 0 para RowCount
    margin_enabled: bool = True  # Se False, gera apenas banda sigma (sem OR margem)
    profile: FormattingProfile = None  # type: ignore[assignment]
    # Se None, inferido automaticamente do metric type
    custom_sql_expression: str = ""  # Apenas para MetricRef.CUSTOM_SQL

    def __post_init__(self):
        if self.profile is None:
            if self.metric == MetricRef.MEAN:
                self.profile = MEAN_PROFILE
            elif self.metric == MetricRef.STANDARD_DEVIATION:
                self.profile = STDDEV_PROFILE
            elif self.metric == MetricRef.ROW_COUNT:
                self.profile = ROWCOUNT_PROFILE
                self.buffer = 0
                self.n_sigma = float(self.n_sigma)
