"""
Configuração da tabela alvo para análise.

Definido conforme docs/technical_spec_v1.md seção 3.1.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional

from core.models.enums import GrainType, LookbackMode, PartitionMethod

logger = logging.getLogger(__name__)

# Maximum lookback value allowed (in periods or days).
# Higher values cause expensive Athena queries (full-table scans over long ranges).
MAX_LOOKBACK_VALUE = 730


@dataclass
class DatasetConfig:
    """Configuração da tabela alvo para análise.

    Conceitos-chave:
    - partition_columns: lista de colunas fisicas de particao no S3/Glue
    - partition_column: atalho legacy para partition_columns[0] (backward compat)
    - partition_method: como os dados são organizados na partição
    - date_column: coluna que define o eixo temporal para análise/GDQ
    - Quando method=INCREMENTAL: partition_column == date_column (geralmente)
    - Quando method=FULL_SNAPSHOT: partition_column != date_column

    Multi-partition: partition_columns pode ter N colunas (ex: ano, mes, dia).
    Cada coluna tem seu formato em partition_formats e tipo em partition_is_integer_map.
    Os campos legacy (partition_column, partition_format, partition_is_integer) sao
    mantidos para backward compat e retornam o valor da primeira coluna.
    """

    # === Identificação da tabela ===
    schema: str
    table: str

    # === Particionamento ===
    partition_method: PartitionMethod = PartitionMethod.INCREMENTAL

    # --- Legacy fields (backward compat — usados por callers existentes) ---
    # Quando fornecidos, sao migrados para partition_columns no __post_init__.
    partition_column: Optional[str] = None
    partition_format: Optional[str] = None
    partition_is_integer: bool = False

    # --- Canonical multi-partition fields (source of truth) ---
    partition_columns: list[str] = field(default_factory=list)
    partition_formats: dict[str, Optional[str]] = field(default_factory=dict)
    partition_is_integer_map: dict[str, bool] = field(default_factory=dict)

    # === Eixo temporal (para análise e regras GDQ) ===
    date_column: str = ""
    # Coluna que define o "processamento" para fins de regras.

    temporal_axis_column: Optional[str] = None
    # Coluna usada como eixo temporal no GROUP BY das queries de histórico.

    grain_type: GrainType = GrainType.DAILY
    date_expression: Optional[str] = None
    # Expressão SQL para normalizar a coluna de data.

    # === Lookback ===
    lookback_mode: LookbackMode = LookbackMode.LAST_N_PERIODS
    lookback_value: int = 30

    # === Filtros ===
    base_filter_sql: Optional[str] = None

    # === Data ancora ===
    reference_date: Optional[str] = None

    # === Colunas selecionadas ===
    selected_columns: list[str] = field(default_factory=list)
    unique_key_columns: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate, cap lookback, and migrate legacy partition fields."""
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

        # --- Migration: legacy single → canonical list ---
        if self.partition_column and not self.partition_columns:
            self.partition_columns = [self.partition_column]
            if self.partition_column not in self.partition_formats:
                self.partition_formats[self.partition_column] = self.partition_format
            if self.partition_column not in self.partition_is_integer_map:
                self.partition_is_integer_map[self.partition_column] = self.partition_is_integer

        # --- Sync: canonical list → legacy fields (keep in sync) ---
        if self.partition_columns:
            first = self.partition_columns[0]
            self.partition_column = first
            self.partition_format = self.partition_formats.get(first)
            self.partition_is_integer = self.partition_is_integer_map.get(first, False)
        else:
            # NON_PARTITIONED or no partition info
            self.partition_column = None
            self.partition_format = None
            self.partition_is_integer = False

    @property
    def partition_is_temporal(self) -> bool:
        """True se a partição contém dados temporais e pruning é aplicável.

        Heurística:
        - partition_format explícito → caller confirmou que é temporal
        - Sem formato: temporal apenas se partition_column == date_column
          (cobre native date onde ambos coincidem)
        - Sem partition_column → False
        """
        if not self.partition_column:
            return False
        if self.partition_format is not None:
            return True
        return self.partition_column == self.date_column

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
    def is_multi_partition(self) -> bool:
        """True se a tabela tem mais de uma coluna de particao."""
        return len(self.partition_columns) > 1

    @property
    def grain_policy(self):
        """Policy de thresholds adaptativos para a granularidade configurada."""
        from core.models.grain_policy import get_grain_policy
        return get_grain_policy(self.grain_type)

    def analysis_fingerprint(self) -> str:
        """Hash determinisico dos campos que afetam resultados de analise.

        Qualquer mudanca em schema, tabela, eixo temporal, lookback,
        filtros ou colunas selecionadas gera um fingerprint diferente.
        Usado para invalidacao de estado analitico no session_state.
        """
        # Partition columns (canonical) — sorted for determinism
        pcols = ",".join(sorted(self.partition_columns))
        pfmts = ",".join(
            f"{k}={v or ''}" for k, v in sorted(self.partition_formats.items())
        )
        pints = ",".join(
            f"{k}={v}" for k, v in sorted(self.partition_is_integer_map.items())
        )

        parts = [
            self.schema,
            self.table,
            self.partition_method.value,
            pcols,
            pfmts,
            pints,
            self.date_column,
            self.temporal_axis_column or "",
            self.grain_type.value,
            self.date_expression or "",
            self.lookback_mode.value,
            str(self.lookback_value),
            self.base_filter_sql or "",
            self.reference_date or "",
            ",".join(sorted(self.selected_columns or [])),
            ",".join(sorted(self.unique_key_columns or [])),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
