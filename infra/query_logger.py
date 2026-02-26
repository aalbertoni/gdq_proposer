"""
Logging estruturado para queries Athena/DuckDB.

Cada query executada gera uma entrada com métricas.
Útil para debug, otimização de custo e identificação de queries lentas.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class QueryLogEntry:
    """Entrada de log estruturada para cada query executada."""

    query_name: str            # ex: "numeric_history", "categorical_distribution"
    dataset: str               # schema.table
    column: Optional[str]      # coluna analisada (None para tabela)
    elapsed_ms: int
    cache_hit: bool
    rows_returned: int
    bytes_scanned: Optional[int] = None  # se disponível do Athena
    exception_type: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class QueryLogger:
    """Logger estruturado para queries Athena.

    Cada query executada gera uma entrada com métricas.
    Útil para debug ("a tela travou"), otimização de custo,
    e identificação de queries lentas.
    """

    def __init__(self):
        self.logger = logging.getLogger("gdq_proposer.queries")
        self.entries: list[QueryLogEntry] = []

    def log_query(self, entry: QueryLogEntry):
        """Registra uma query executada."""
        self.entries.append(entry)
        level = logging.WARNING if entry.exception_type else logging.INFO
        self.logger.log(
            level,
            "[%s] %s.%s → %d rows, %dms, cache=%s%s",
            entry.query_name,
            entry.dataset,
            entry.column or "*",
            entry.rows_returned,
            entry.elapsed_ms,
            "HIT" if entry.cache_hit else "MISS",
            f", ERROR={entry.exception_type}" if entry.exception_type else "",
        )

    def get_session_summary(self) -> dict:
        """Resumo da sessão: total queries, tempo total, cache hits, custo estimado."""
        total = len(self.entries)
        if total == 0:
            return {
                "total_queries": 0,
                "total_elapsed_ms": 0,
                "cache_hits": 0,
                "cache_hit_rate": 0.0,
                "total_rows": 0,
                "errors": 0,
                "total_bytes_scanned": 0,
                "estimated_cost_usd": 0.0,
            }

        total_ms = sum(e.elapsed_ms for e in self.entries)
        cache_hits = sum(1 for e in self.entries if e.cache_hit)
        total_rows = sum(e.rows_returned for e in self.entries)
        errors = sum(1 for e in self.entries if e.exception_type)
        total_bytes = sum(e.bytes_scanned or 0 for e in self.entries)
        # Athena pricing: $5.00 per TB scanned (minimum 10MB per query)
        estimated_cost = (total_bytes / (1024 ** 4)) * 5.0

        return {
            "total_queries": total,
            "total_elapsed_ms": total_ms,
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hits / total, 2),
            "total_rows": total_rows,
            "errors": errors,
            "total_bytes_scanned": total_bytes,
            "estimated_cost_usd": round(estimated_cost, 4),
        }

    def export_json(self) -> str:
        """Exporta log da sessao como JSON (summary + entries)."""
        return json.dumps(
            {
                "summary": self.get_session_summary(),
                "entries": [asdict(e) for e in self.entries],
            },
            indent=2,
            ensure_ascii=False,
        )
