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


# Athena pricing per TB scanned by region (USD).
# Source: AWS Pricing API (pricing.us-east-1.amazonaws.com), fetched 2026-03-22.
# Regions not listed fall back to the us-east-1 price ($5.00).
ATHENA_PRICE_PER_TB: dict[str, float] = {
    "us-east-1": 5.00,
    "us-east-2": 5.00,
    "us-west-1": 6.75,
    "us-west-2": 5.00,
    "eu-west-1": 5.00,
    "eu-central-1": 5.00,
    "ap-southeast-1": 5.00,
    "ap-northeast-1": 5.00,
    "sa-east-1": 9.00,
}

DEFAULT_ATHENA_PRICE_PER_TB = 5.00


def get_athena_price_per_tb(region: str) -> float:
    """Retorna o preco por TB para a regiao Athena."""
    return ATHENA_PRICE_PER_TB.get(region, DEFAULT_ATHENA_PRICE_PER_TB)


@dataclass
class QueryLogEntry:
    """Entrada de log estruturada para cada query executada."""

    query_name: str            # ex: "numeric_history", "categorical_distribution"
    dataset: str               # schema.table
    column: Optional[str]      # coluna analisada (None para tabela)
    elapsed_ms: int
    cache_hit: bool
    rows_returned: int
    sql: str = ""              # SQL executado (para debug)
    bytes_scanned: Optional[int] = None  # se disponível do Athena
    exception_type: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    _price_per_tb: float = field(default=DEFAULT_ATHENA_PRICE_PER_TB, repr=False)

    @property
    def estimated_cost_usd(self) -> float:
        """Custo estimado desta query baseado na regiao.

        Athena has a 10MB minimum charge per query.
        """
        if self.bytes_scanned is None or self.bytes_scanned == 0:
            return 0.0
        ATHENA_MIN_BYTES = 10 * 1024 * 1024  # 10MB minimum per query
        billable = max(self.bytes_scanned, ATHENA_MIN_BYTES)
        return (billable / (1024 ** 4)) * self._price_per_tb


class QueryLogger:
    """Logger estruturado para queries Athena.

    Cada query executada gera uma entrada com métricas.
    Útil para debug ("a tela travou"), otimização de custo,
    e identificação de queries lentas.
    """

    def __init__(self, region: str = "sa-east-1"):
        self.logger = logging.getLogger("gdq_proposer.queries")
        self.entries: list[QueryLogEntry] = []
        self.region = region
        self.price_per_tb = get_athena_price_per_tb(region)

    def log_query(self, entry: QueryLogEntry):
        """Registra uma query executada."""
        entry._price_per_tb = self.price_per_tb
        self.entries.append(entry)
        level = logging.WARNING if entry.exception_type else logging.INFO

        # Build optional suffixes
        suffixes = []
        if entry.bytes_scanned is not None and entry.bytes_scanned > 0:
            mb = entry.bytes_scanned / (1024 ** 2)
            suffixes.append(f"scanned={mb:.2f}MB")
            suffixes.append(f"cost=${entry.estimated_cost_usd:.6f}")
        if entry.exception_type:
            suffixes.append(f"ERROR={entry.exception_type}")
        suffix_str = (", " + ", ".join(suffixes)) if suffixes else ""

        self.logger.log(
            level,
            "[%s] %s.%s -> %d rows, %dms, cache=%s%s",
            entry.query_name,
            entry.dataset,
            entry.column or "*",
            entry.rows_returned,
            entry.elapsed_ms,
            "HIT" if entry.cache_hit else "MISS",
            suffix_str,
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
        # Sum per-query costs (each already applies 10MB minimum billing).
        # This is more accurate than recomputing from total bytes, which
        # would undercount sessions with many small queries.
        estimated_cost = sum(e.estimated_cost_usd for e in self.entries)

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
        """Exporta log da sessao como JSON (summary + entries).

        Each entry includes ``estimated_cost_usd`` computed from bytes_scanned.
        """
        entries = []
        for e in self.entries:
            d = asdict(e)
            d.pop("_price_per_tb", None)
            d["estimated_cost_usd"] = e.estimated_cost_usd
            entries.append(d)
        return json.dumps(
            {
                "summary": self.get_session_summary(),
                "entries": entries,
            },
            indent=2,
            ensure_ascii=False,
        )
