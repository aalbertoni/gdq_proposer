"""
Configuração da tabela alvo para análise.

Definido conforme docs/technical_spec_v1.md seção 3.1.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.models.enums import GrainType, LookbackMode, PartitionMethod

logger = logging.getLogger(__name__)

# Maximum lookback value allowed (in periods or days).
# Higher values cause expensive Athena queries (full-table scans over long ranges).
MAX_LOOKBACK_VALUE = 365


@dataclass
class DatasetConfig:
    """Configuração da tabela alvo para análise.

    Conceitos-chave:
    - partition_column: coluna física de partição no S3/Glue (pode ser None)
    - partition_method: como os dados são organizados na partição
    - date_column: coluna que define o eixo temporal para análise/GDQ
    - Quando method=INCREMENTAL: partition_column == date_column (geralmente)
    - Quando method=FULL_SNAPSHOT: partition_column != date_column
    """

    # === Identificação da tabela ===
    schema: str
    table: str

    # === Particionamento ===
    partition_method: PartitionMethod = PartitionMethod.INCREMENTAL
    partition_column: Optional[str] = None
    # Nome da coluna de partição (ex: "dt_ref", "dt_carga")
    # None se non_partitioned

    # === Eixo temporal (para análise e regras GDQ) ===
    date_column: str = ""
    # Coluna que define o "processamento" para fins de regras.
    # Em INCREMENTAL: geralmente = partition_column (ex: "dt_ref")
    # Em FULL_SNAPSHOT: = partition_column (dt_carga) para eixo temporal
    # OU = coluna interna (DT_ABERTURA) para análise de conteúdo

    temporal_axis_column: Optional[str] = None
    # Coluna usada como eixo temporal no GROUP BY das queries de histórico.
    # Se None, usa partition_column (INCREMENTAL) ou date_column.
    # Em FULL_SNAPSHOT: normalmente = partition_column (cada snapshot = 1 ponto)
    # Isso garante que cada "período" no histórico = 1 execução do GDQ.

    grain_type: GrainType = GrainType.DAILY
    date_expression: Optional[str] = None
    # Expressão SQL para normalizar a coluna de data.
    # Ex.: "date_parse(dt_ref, '%Y.%m.%d')"
    # Ex.: "date_trunc('month', dt_evento)"
    # Se None, usa a coluna diretamente.

    # === Lookback ===
    lookback_mode: LookbackMode = LookbackMode.LAST_N_PERIODS
    lookback_value: int = 30

    # === Filtros ===
    base_filter_sql: Optional[str] = None
    # Filtro WHERE aplicado em TODAS as queries.
    # Ex.: "IND_ATIVO = 1"
    # Ex.: "COD_SEGMENTO != 'TESTE'"
    # Muito usado em FULL_SNAPSHOT para filtrar registros relevantes.

    # === Colunas selecionadas ===
    selected_columns: list[str] = field(default_factory=list)
    unique_key_columns: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate and cap lookback_value at MAX_LOOKBACK_VALUE.

        If the user provides a lookback_value exceeding the maximum, it is
        silently capped and a warning is logged.  This prevents runaway
        Athena queries that scan excessive time ranges.
        """
        if self.lookback_value > MAX_LOOKBACK_VALUE:
            logger.warning(
                "lookback_value %d exceeds maximum %d — capping to %d",
                self.lookback_value,
                MAX_LOOKBACK_VALUE,
                MAX_LOOKBACK_VALUE,
            )
            self.lookback_value = MAX_LOOKBACK_VALUE

        if self.lookback_value < 1:
            logger.warning(
                "lookback_value %d is below minimum 1 — setting to 1",
                self.lookback_value,
            )
            self.lookback_value = 1

    @property
    def effective_temporal_axis(self) -> str:
        """Coluna usada como eixo temporal nas queries de histórico.

        Lógica:
        1. Se temporal_axis_column foi definido explicitamente, usar
        2. Se INCREMENTAL, usar partition_column (= date_column)
        3. Se FULL_SNAPSHOT, usar partition_column (cada snapshot = 1 ponto)
        4. Se NON_PARTITIONED, usar date_column
        """
        if self.temporal_axis_column:
            return self.temporal_axis_column
        if self.partition_method == PartitionMethod.INCREMENTAL:
            return self.partition_column or self.date_column
        if self.partition_method == PartitionMethod.FULL_SNAPSHOT:
            return self.partition_column or self.date_column
        return self.date_column

    @property
    def effective_partition_filter(self) -> Optional[str]:
        """Gera filtro de partição para otimizar queries (partition pruning).

        Se a tabela é particionada, gerar WHERE partition_col >= ...
        para que o Athena faça partition pruning (reduz custo).
        """
        if not self.partition_column:
            return None
        if self.date_expression:
            return (
                f"{self.date_expression} >= "
                f"DATE_ADD('day', -{self.lookback_value}, CURRENT_DATE)"
            )
        return (
            f'"{self.partition_column}" >= '
            f"CAST(DATE_ADD('day', -{self.lookback_value}, CURRENT_DATE) AS VARCHAR)"
        )
