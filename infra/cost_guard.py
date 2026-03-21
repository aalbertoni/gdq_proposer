"""Excepcoes de dominio e guardrails de custo para queries Athena.

Politica fail-closed: se o caminho barato falha, a execucao para
com erro explicito em vez de cair silenciosamente para caminho caro.
"""


class PartitionMetadataError(Exception):
    """SHOW PARTITIONS ou metadata de particao falhou.

    Levantada quando a descoberta de particoes falha e nao ha
    caminho seguro para descobrir o range temporal sem full scan.
    """


class ExpensiveFallbackBlocked(Exception):
    """Fallback para caminho mais caro bloqueado pela politica fail-closed.

    Levantada quando batch profiling falha e o sistema tentaria
    cair para N queries individuais, multiplicando custo.
    """


class CostGuardrailTriggered(Exception):
    """Custo estimado ultrapassou o limiar. Novas queries bloqueadas.

    O usuario deve confirmar explicitamente para continuar.
    """

    def __init__(self, cost_usd: float, threshold_usd: float, query_name: str = ""):
        self.cost_usd = cost_usd
        self.threshold_usd = threshold_usd
        self.query_name = query_name
        super().__init__(
            f"Custo acumulado ${cost_usd:.4f} excedeu limiar ${threshold_usd:.2f}"
            f"{f' (ultima query: {query_name})' if query_name else ''}"
        )
