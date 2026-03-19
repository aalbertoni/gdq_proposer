"""
Mapeamento de status de validacao por tipo de regra GDQ.

Define quais tipos de regra sao validated, experimental ou unknown
no runtime real do AWS Glue Data Quality.

Referencia: docs/gdq_capability_matrix.md

Dependencias: core/models/enums.py.
"""

from core.models.enums import GDQCapabilityStatus, RuleType

# Mapeamento RuleType → GDQCapabilityStatus
RULE_CAPABILITY: dict[RuleType, GDQCapabilityStatus] = {
    # Built-in (validated)
    RuleType.MEAN_DUAL_GUARD: GDQCapabilityStatus.VALIDATED,
    RuleType.STDDEV_DUAL_GUARD: GDQCapabilityStatus.VALIDATED,
    RuleType.ROW_COUNT_DUAL_GUARD: GDQCapabilityStatus.VALIDATED,
    RuleType.COMPLETENESS: GDQCapabilityStatus.VALIDATED,
    RuleType.ALLOWED_VALUES: GDQCapabilityStatus.VALIDATED,
    RuleType.DISTINCT_COUNT_EXACT: GDQCapabilityStatus.VALIDATED,
    RuleType.DISTINCT_COUNT_RANGE: GDQCapabilityStatus.VALIDATED,
    RuleType.IS_PRIMARY_KEY: GDQCapabilityStatus.VALIDATED,
    # CustomSql static (validated)
    RuleType.CATEGORY_FREQUENCY_STATIC: GDQCapabilityStatus.VALIDATED,
    RuleType.UNIQUENESS_CUSTOM_SQL: GDQCapabilityStatus.VALIDATED,
    # CustomSql dynamic (experimental — avg/std no between)
    RuleType.CATEGORY_FREQUENCY_DYNAMIC: GDQCapabilityStatus.EXPERIMENTAL,
    RuleType.CATEGORY_FREQUENCY_HYBRID: GDQCapabilityStatus.EXPERIMENTAL,
    RuleType.NUMERIC_PERCENTILE_BAND: GDQCapabilityStatus.EXPERIMENTAL,
    # Generic
    RuleType.CUSTOM_SQL: GDQCapabilityStatus.EXPERIMENTAL,
}


def get_capability_status(rule_type: RuleType) -> GDQCapabilityStatus:
    """Retorna status de validacao para o tipo de regra.

    Args:
        rule_type: Tipo de regra GDQ.

    Returns:
        GDQCapabilityStatus (validated, experimental, unknown).
    """
    return RULE_CAPABILITY.get(rule_type, GDQCapabilityStatus.UNKNOWN)


def is_experimental(rule_type: RuleType) -> bool:
    """Verifica se o tipo de regra e experimental."""
    return get_capability_status(rule_type) == GDQCapabilityStatus.EXPERIMENTAL


def capability_badge(rule_type: RuleType) -> str:
    """Retorna badge textual do status de validacao.

    Returns:
        String formatada para exibicao na UI.
    """
    status = get_capability_status(rule_type)
    if status == GDQCapabilityStatus.VALIDATED:
        return ""  # No badge needed for validated
    elif status == GDQCapabilityStatus.EXPERIMENTAL:
        return "⚠️ experimental"
    else:
        return "❓ unknown"


def capability_warning(rule_type: RuleType) -> str:
    """Retorna texto de aviso para regras experimentais.

    Returns:
        String com aviso, ou vazio se validated.
    """
    status = get_capability_status(rule_type)
    if status == GDQCapabilityStatus.EXPERIMENTAL:
        return (
            "Esta regra usa sintaxe experimental (CustomSql com avg/std no between). "
            "Funciona em testes, mas nao foi confirmada em producao. "
            "Valide via Thundera (pagina Teste) antes de promover."
        )
    elif status == GDQCapabilityStatus.UNKNOWN:
        return (
            "Status de validacao desconhecido para este tipo de regra. "
            "Teste manualmente antes de usar em producao."
        )
    return ""
