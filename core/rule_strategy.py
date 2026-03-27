"""Seleção de estratégia de regras por regime estatístico.

Retorna um RuleBundle advisory com regras recomendadas e explicações.
Puramente informativo — não gera SQL, não altera pipeline de propostas.

Bundles v1 consensuados por 3 agentes (Claude estatístico + Codex
pragmático + Claude arquiteto). Máximo 4 regras por coluna.
"""

import logging
from core.models.enums import RuleType, SeriesRegime
from core.models.rule_bundle import BundledRuleConfig, RuleBundle
from core.models.series_profile import SeriesProfile

logger = logging.getLogger(__name__)

# Regras universais presentes em todos os bundles
_ROWCOUNT = BundledRuleConfig(
    rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
    note="Monitora volume — detecta falhas de pipeline independente da distribuicao",
)
_COMPLETENESS = BundledRuleConfig(
    rule_type=RuleType.COMPLETENESS,
    note="Monitora preenchimento de dados",
)


def select_strategy(profile: SeriesProfile) -> RuleBundle:
    """Seleciona bundle de regras recomendadas baseado no regime.

    Args:
        profile: Perfil estatístico da série (de classify_series).

    Returns:
        RuleBundle advisory com regras, explicação e substituições.
    """
    try:
        regime = profile.regime
        builder = _STRATEGY_MAP.get(regime, _strategy_stable)
        return builder(profile)
    except Exception:
        logger.warning(
            "select_strategy failed for profile %s, falling back to STABLE",
            getattr(profile, "primary_regime", "unknown"),
            exc_info=True,
        )
        return _strategy_stable(profile)


def _strategy_stable(profile: SeriesProfile) -> RuleBundle:
    return RuleBundle(
        regime=SeriesRegime.STABLE,
        rule_configs=(
            BundledRuleConfig(
                rule_type=RuleType.MEAN_DUAL_GUARD,
                suggested_n=30, suggested_sigma=2.0,
                note="Padrao — serie estavel, Mean com sigma=2 funciona bem",
            ),
            BundledRuleConfig(
                rule_type=RuleType.STDDEV_DUAL_GUARD,
                suggested_n=30, suggested_sigma=2.0,
                note="Monitora dispersao — complementar ao Mean",
            ),
            _ROWCOUNT,
            _COMPLETENESS,
        ),
        explanation=(
            "Serie estavel (baixa volatilidade, sem tendencia, sem sazonalidade). "
            "Regras padrao de Mean + StdDev funcionam bem neste regime."
        ),
        substitutions=(),
    )


def _strategy_volatile(profile: SeriesProfile) -> RuleBundle:
    return RuleBundle(
        regime=SeriesRegime.VOLATILE,
        rule_configs=(
            BundledRuleConfig(
                rule_type=RuleType.MEAN_DUAL_GUARD,
                suggested_n=30, suggested_sigma=3.0,
                note="Sigma=3 reduz falsos positivos em serie volatil (CV={:.0f}%)".format(
                    (profile.cv or 0) * 100
                ),
            ),
            BundledRuleConfig(
                rule_type=RuleType.NUMERIC_PERCENTILE_BAND,
                note="P05/P95 monitora expansao das caudas — robusto a outliers",
            ),
            _ROWCOUNT,
            _COMPLETENESS,
        ),
        explanation=(
            "Serie volatil (CV={:.0f}%). Mean com sigma=2 geraria muitos falsos positivos. "
            "Sigma=3 + percentis P05/P95 oferecem protecao sem excesso de alertas.".format(
                (profile.cv or 0) * 100
            )
        ),
        substitutions=(
            "Mean: sigma 2 -> 3 (CV alto causa FP com sigma=2)",
            "StdDev omitido (instavel em series volateis — substituido por P05/P95)",
        ),
    )


def _strategy_asymmetric(profile: SeriesProfile) -> RuleBundle:
    skew = profile.skewness or 0
    return RuleBundle(
        regime=SeriesRegime.ASYMMETRIC,
        rule_configs=(
            BundledRuleConfig(
                rule_type=RuleType.NUMERIC_PERCENTILE_BAND,
                note="P10/P90 se adapta a assimetria (skewness={:.2f})".format(skew),
            ),
            _ROWCOUNT,
            _COMPLETENESS,
        ),
        explanation=(
            "Serie assimetrica (skewness={:.2f}). Bandas simetricas (Mean ± K*std) "
            "geram falsos positivos no lado curto da distribuicao. "
            "Percentis P10/P90 se ajustam naturalmente a assimetria.".format(skew)
        ),
        substitutions=(
            "Mean omitido (banda simetrica inadequada para distribuicao assimetrica)",
            "StdDev omitido (mesmo motivo)",
            "+P10/P90 substitui Mean+StdDev com bandas assimetricas",
        ),
    )


def _strategy_trending(profile: SeriesProfile) -> RuleBundle:
    # N adaptivo: se drift forte (R²>0.7), N mais curto
    r2 = profile.drift_r_squared or 0
    suggested_n = 10 if r2 > 0.7 else 15
    return RuleBundle(
        regime=SeriesRegime.TRENDING,
        rule_configs=(
            BundledRuleConfig(
                rule_type=RuleType.MEAN_DUAL_GUARD,
                suggested_n=suggested_n, suggested_sigma=2.0,
                note="N={} acompanha a tendencia (R²={:.2f})".format(suggested_n, r2),
            ),
            _ROWCOUNT,
            _COMPLETENESS,
        ),
        explanation=(
            "Serie com tendencia detectada (R²={:.2f}). "
            "N=30 (padrao) inclui baseline desatualizado e gera falsos positivos. "
            "N={} acompanha a tendencia mantendo baseline recente.".format(r2, suggested_n)
        ),
        substitutions=(
            "Mean: N 30 -> {} (baseline precisa acompanhar tendencia)".format(suggested_n),
            "StdDev omitido (desvio padrao inflado pela tendencia)",
        ),
    )


def _strategy_seasonal(profile: SeriesProfile) -> RuleBundle:
    return RuleBundle(
        regime=SeriesRegime.SEASONAL,
        rule_configs=(
            BundledRuleConfig(
                rule_type=RuleType.MEAN_DUAL_GUARD,
                suggested_n=28, suggested_sigma=2.5,
                note="N=28 (4 semanas) suaviza efeito dia-da-semana; sigma=2.5 compensa variancia residual",
            ),
            BundledRuleConfig(
                rule_type=RuleType.ROW_COUNT_DUAL_GUARD,
                suggested_n=14,
                note="N=14 (2 semanas) para RowCount — volume tambem tem padrao semanal",
            ),
            _COMPLETENESS,
        ),
        explanation=(
            "Serie com sazonalidade semanal detectada (eta²={:.0f}%). "
            "N multiplo de 7 suaviza o efeito dia-da-semana no baseline. "
            "Sigma=2.5 compensa a variancia residual sazonal.".format(
                (profile.seasonality_strength or 0) * 100
            )
        ),
        substitutions=(
            "Mean: N 30 -> 28, sigma 2.0 -> 2.5 (suavizar sazonalidade + compensar variancia)",
            "RowCount: N 30 -> 14 (volume sazonal precisa de multiplo de 7)",
        ),
    )


def _strategy_structural_break(profile: SeriesProfile) -> RuleBundle:
    # Estimate post-change points. SeriesProfile doesn't store exact count,
    # so we use n_valid/3 as heuristic (change points typically in last third).
    # If n_valid is 0, fallback conservatively.
    post_count = max(profile.n_valid // 3, 0) if profile.n_valid > 0 else 0
    if post_count < 5:
        # Poucos pontos pós-mudança — fallback com warning
        return RuleBundle(
            regime=SeriesRegime.STRUCTURAL_BREAK,
            rule_configs=(
                _ROWCOUNT,
                _COMPLETENESS,
            ),
            explanation=(
                "Mudanca estrutural detectada, mas apenas {} pontos apos a mudanca. "
                "Insuficiente para calibrar regras de valor (Mean/StdDev). "
                "Recomendado aguardar mais dados ou usar apenas RowCount + Completeness.".format(
                    post_count
                )
            ),
            substitutions=(
                "Mean omitido (apenas {} pontos pos-mudanca — baseline nao confiavel)".format(post_count),
                "StdDev omitido (mesmo motivo)",
            ),
        )

    suggested_n = max(post_count, 10)
    return RuleBundle(
        regime=SeriesRegime.STRUCTURAL_BREAK,
        rule_configs=(
            BundledRuleConfig(
                rule_type=RuleType.MEAN_DUAL_GUARD,
                suggested_n=suggested_n, suggested_sigma=2.0,
                note="N={} limitado ao periodo pos-mudanca".format(suggested_n),
            ),
            BundledRuleConfig(
                rule_type=RuleType.STDDEV_DUAL_GUARD,
                suggested_n=suggested_n, suggested_sigma=2.0,
                note="Monitora se variancia pos-mudanca estabilizou",
            ),
            _ROWCOUNT,
            _COMPLETENESS,
        ),
        explanation=(
            "Mudanca estrutural detectada. Baseline deve usar apenas os {} pontos "
            "pos-mudanca para evitar contaminacao do regime anterior. "
            "StdDev monitora se o novo regime esta estabilizado.".format(post_count)
        ),
        substitutions=(
            "Mean: N 30 -> {} (somente dados pos-mudanca)".format(suggested_n),
            "+StdDev pos-mudanca (verifica estabilidade do novo regime)",
        ),
    )


def _strategy_zero_inflated(profile: SeriesProfile) -> RuleBundle:
    zero_pct = profile.zero_pct or 0
    return RuleBundle(
        regime=SeriesRegime.ZERO_INFLATED,
        rule_configs=(
            _COMPLETENESS,
            _ROWCOUNT,
        ),
        explanation=(
            "Serie com {:.0f}% de zeros. Mean convencional e distorcida pelos zeros "
            "e nao representa o comportamento real dos dados nao-zero. "
            "Recomendado monitorar Completeness + RowCount. "
            "Para analise de valor, considere filtrar zeros manualmente.".format(zero_pct)
        ),
        substitutions=(
            "Mean omitido (distorcida por {:.0f}% de zeros)".format(zero_pct),
            "StdDev omitido (inflado pela distribuicao bimodal zero/nao-zero)",
        ),
    )


def _strategy_sparse(profile: SeriesProfile) -> RuleBundle:
    null_pct = profile.null_pct or 0
    return RuleBundle(
        regime=SeriesRegime.SPARSE,
        rule_configs=(
            _COMPLETENESS,
            _ROWCOUNT,
        ),
        explanation=(
            "Serie com {:.0f}% de nulos. Regras de valor (Mean, StdDev) sao "
            "calculadas sobre amostra reduzida e nao sao confiaveis. "
            "Monitorar preenchimento (Completeness) e volume (RowCount).".format(null_pct)
        ),
        substitutions=(
            "Mean omitido (amostra efetiva muito pequena — {:.0f}% nulos)".format(null_pct),
            "StdDev omitido (mesmo motivo)",
        ),
    )


_STRATEGY_MAP: dict[SeriesRegime, callable] = {
    SeriesRegime.STABLE: _strategy_stable,
    SeriesRegime.VOLATILE: _strategy_volatile,
    SeriesRegime.ASYMMETRIC: _strategy_asymmetric,
    SeriesRegime.TRENDING: _strategy_trending,
    SeriesRegime.SEASONAL: _strategy_seasonal,
    SeriesRegime.STRUCTURAL_BREAK: _strategy_structural_break,
    SeriesRegime.ZERO_INFLATED: _strategy_zero_inflated,
    SeriesRegime.SPARSE: _strategy_sparse,
}
