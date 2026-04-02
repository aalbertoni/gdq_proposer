"""Servico de teste de regras GDQ via Thundera (Glue job).

Orquestra: construcao do payload JSON, execucao do Glue job,
polling de status e coleta de resultados.
Inclui correlacao de resultados com o carrinho (write-back).
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable

from core.models.enums import RuleType
from core.models.rule_selection import _syntax_hash

logger = logging.getLogger(__name__)

# Pattern para extrair nome de coluna de filtro de igualdade: "COL = ..."
_FILTER_COL_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _extract_column_from_filter(filter_expr: str) -> str | None:
    """Extrai nome de coluna de um filtro de igualdade simples.

    Aceita: 'COL = valor', 'COL = 123', etc.
    Retorna None se não conseguir extrair.
    """
    m = _FILTER_COL_PATTERN.match(filter_expr.strip())
    return m.group(1) if m else None


def normalize_syntax(syntax: str) -> str:
    """Normalize GDQ syntax for matching: collapse whitespace, strip."""
    return " ".join(syntax.split())


@dataclass
class CorrelationReport:
    """Result of correlating Glue test results with cart items."""
    matched: int = 0
    unmatched: int = 0
    orphaned: int = 0
    orphaned_results: list = field(default_factory=list)


class GlueTestService:
    """Orquestra teste de regras GDQ via Thundera Glue job.

    Responsabilidades:
    1. Construir payload JSON a partir do carrinho de regras
    2. Disparar execucao do Glue job
    3. Fazer polling de status ate conclusao
    4. Retornar resultado estruturado

    Usage:
        svc = GlueTestService(glue_client, config)
        payload = svc.build_payload(dataset_config, selections, classificatory)
        result = svc.run_test(payload)
    """

    def __init__(self, glue_client, config):
        """Inicializa o servico.

        Args:
            glue_client: GlueClient para operacoes boto3.
            config: AppConfig com GlueTestConfig.
        """
        self._client = glue_client
        self._config = config

    def build_payload(
        self,
        dataset_config,
        selections: list,
        classificatory: dict[str, str],
        partition_columns: list[str] | None = None,
    ):
        """Constroi ThunderaPayload a partir do carrinho e config.

        Args:
            dataset_config: DatasetConfig ativo.
            selections: Lista de RuleSelection habilitadas.
            classificatory: Campos classificatorios editados pelo usuario.
            partition_columns: Colunas de particao (None = usa dataset_config).

        Returns:
            ThunderaPayload pronto para serializacao.
        """
        from core.models.glue_test import ThunderaPayload, ThunderaProcessamento

        # Extract unique column names from rules
        columns = self._extract_columns(selections)

        # Extract GDQ syntax strings
        regras = []
        for sel in selections:
            if sel.enabled and sel.final_gdq_syntax and sel.final_gdq_syntax.strip():
                regras.append(sel.final_gdq_syntax.strip())

        # Build partition list
        if partition_columns:
            particao = partition_columns
        elif dataset_config.partition_column:
            particao = [dataset_config.partition_column]
        else:
            particao = []

        # COD_TABE = schema.table
        cod_tabe = f"{dataset_config.schema}.{dataset_config.table}"

        glue_cfg = self._config.glue_test

        return ThunderaPayload(
            squad=classificatory.get("squad", glue_cfg.default_squad),
            comunidade=classificatory.get("comunidade", glue_cfg.default_comunidade),
            racf=classificatory.get("racf", glue_cfg.default_racf),
            periodicidade=classificatory.get("periodicidade", glue_cfg.default_periodicidade),
            tipo_qualidade=classificatory.get("tipo_qualidade", glue_cfg.default_tipo_qualidade),
            status_regra=classificatory.get("status_regra", "ATIVA"),
            nome_orig_tablea=classificatory.get("nome_orig_tablea", "AWS"),
            cod_regr_even_cred=classificatory.get("cod_regr_even_cred", ""),
            release_train=classificatory.get("release_train", ""),
            cod_tabe=cod_tabe,
            processamento=ThunderaProcessamento(
                conta=classificatory.get("conta", glue_cfg.default_conta),
                timeout=classificatory.get("timeout", glue_cfg.default_timeout),
                workers=classificatory.get("workers", glue_cfg.default_workers),
            ),
            nome_glue_job=classificatory.get("nome_glue_job", glue_cfg.glue_job_name),
            infer_schema=classificatory.get("infer_schema", False),
            iceberg=classificatory.get("iceberg", False),
            particao=particao,
            particoes_evento=classificatory.get("particoes_evento", ""),
            delay_processamento=int(classificatory.get("delay_processamento", 0)),
            columns_name=columns,
            regras_gdq=regras,
        )

    def _extract_columns(self, selections: list) -> list[str]:
        """Extrai nomes unicos de colunas referenciadas nas regras.

        Inclui: target_column, colunas de IsPrimaryKey, e colunas
        usadas em filtros de subpopulacao (necessarias no COLUMNS_NAME
        para o Thundera conseguir executar queries com WHERE).

        Formato Thundera: UPPERCASE sem aspas (ex: 'VLR_SALDO').

        Args:
            selections: Lista de RuleSelection.

        Returns:
            Lista ordenada de nomes de colunas em UPPERCASE.
        """
        columns: set[str] = set()
        for sel in selections:
            if not sel.enabled:
                continue
            p = sel.proposal
            if p.rule_type == RuleType.IS_PRIMARY_KEY:
                if p.suggested_values:
                    columns.update(p.suggested_values)
            elif p.target_column:
                columns.add(p.target_column)
            # Coluna de subpopulacao (usada no WHERE do CustomSql)
            subpop_filter = getattr(p, "subpopulation_filter", None)
            if subpop_filter:
                subpop_col = _extract_column_from_filter(subpop_filter)
                if subpop_col:
                    columns.add(subpop_col)
        return sorted(c.upper() for c in columns)

    def run_test(
        self,
        payload,
        on_status: Callable[[str, str], None] | None = None,
    ):
        """Executa teste: dispara job, faz polling, retorna resultado.

        Args:
            payload: ThunderaPayload construido por build_payload().
            on_status: Callback(status, message) para atualizacao de UI.

        Returns:
            GlueTestResult com status final.

        Raises:
            GlueTestError: Em caso de falha do job ou timeout.
        """
        from core.models.glue_test import GlueTestResult
        from infra.glue_client import GlueTestError

        cfg = self._config.glue_test
        job_name = payload.nome_glue_job
        json_str = payload.to_json()

        # Trigger
        if on_status:
            on_status("STARTING", "Disparando Glue job...")
        run_id = self._client.start_job_run(
            job_name=job_name,
            arguments={"--objson": json_str},
        )

        # Poll
        elapsed = 0
        interval = cfg.poll_interval_seconds
        timeout = cfg.poll_timeout_seconds

        while elapsed < timeout:
            time.sleep(interval)
            elapsed += interval

            try:
                status_info = self._client.get_job_run(job_name, run_id)
            except GlueTestError:
                # Transient error, retry
                continue

            state = status_info["JobRunState"]
            if on_status:
                on_status(state, f"Job {state}... ({elapsed}s)")

            if state in ("SUCCEEDED", "FAILED", "STOPPED", "ERROR", "TIMEOUT"):
                result = GlueTestResult(
                    run_id=run_id,
                    job_name=job_name,
                    status=state,
                    started_at=status_info.get("StartedOn", ""),
                    completed_at=status_info.get("CompletedOn", ""),
                    duration_seconds=status_info.get("ExecutionTime", 0),
                    error_message=status_info.get("ErrorMessage", ""),
                )
                self._fetch_and_parse_logs(result, on_status)
                return result

        # Timeout — try to cancel
        self._client.stop_job_run(job_name, run_id)
        return GlueTestResult(
            run_id=run_id,
            job_name=job_name,
            status="TIMEOUT",
            duration_seconds=elapsed,
            error_message=f"Job excedeu timeout de {timeout}s. Cancelamento solicitado.",
        )

    def _fetch_and_parse_logs(self, result, on_status=None):
        """Busca logs do CloudWatch e faz parse dos resultados por regra.

        Args:
            result: GlueTestResult a ser enriquecido com logs e rule_results.
            on_status: Callback opcional para atualizacao de UI.
        """
        from core.glue_log_parser import parse_glue_log

        if on_status:
            on_status("FETCHING_LOGS", "Buscando logs do CloudWatch...")

        try:
            log_text = self._client.get_job_logs(result.job_name, result.run_id)
        except Exception as e:
            logger.warning("Falha ao buscar logs: %s", e)
            if on_status:
                on_status("NO_LOGS", "Falha ao buscar logs do CloudWatch.")
            return

        result.execution_log = log_text

        if log_text:
            if on_status:
                on_status("PARSING_LOGS", "Analisando resultados por regra...")
            result.rule_results = parse_glue_log(log_text)
        else:
            if on_status:
                on_status("NO_LOGS", "Logs nao disponiveis no CloudWatch.")

    # --- Correlation & Write-back ---

    def correlate_results(
        self,
        cart: list,
        glue_results: list,
    ) -> tuple[dict[str, "GlueRuleResult"], CorrelationReport]:
        """Correlate GlueRuleResults with cart RuleSelections.

        Uses cascading match strategy:
        1. Exact normalized syntax match
        2. Fallback: rule_category + target_column (if unique in cart)
        3. Orphaned: result without match

        Args:
            cart: list[RuleSelection] from session_state.
            glue_results: list[GlueRuleResult] from test execution.

        Returns:
            Tuple of (correlation_map, report).
            correlation_map: {proposal_id: GlueRuleResult}
        """
        from core.models.glue_test import GlueRuleResult

        report = CorrelationReport()
        correlation_map: dict[str, GlueRuleResult] = {}

        # Build lookup index: normalized syntax -> RuleSelection
        syntax_index: dict[str, list] = {}
        for sel in cart:
            if sel.enabled and sel.final_gdq_syntax.strip():
                norm = normalize_syntax(sel.final_gdq_syntax)
                syntax_index.setdefault(norm, []).append(sel)

        # Build category+column index for fallback
        cat_col_index: dict[str, list] = {}
        for sel in cart:
            if sel.enabled and sel.final_gdq_syntax.strip():
                p = sel.proposal
                key = f"{p.rule_type.value}|{(p.target_column or '').lower()}"
                cat_col_index.setdefault(key, []).append(sel)

        matched_ids: set[str] = set()

        for gr in glue_results:
            matched = False

            # Strategy 1: exact syntax match
            norm_result = normalize_syntax(gr.rule_syntax)
            candidates = syntax_index.get(norm_result, [])
            for sel in candidates:
                if sel.proposal_id not in matched_ids:
                    correlation_map[sel.proposal_id] = gr
                    matched_ids.add(sel.proposal_id)
                    report.matched += 1
                    matched = True
                    break

            if matched:
                continue

            # Strategy 2: category + column fallback (only if unique)
            cat_key = f"{gr.rule_category.lower()}|{(gr.target_column or '').lower()}"
            # Normalize rule_category to match RuleType values
            cat_candidates = self._find_by_category_column(
                cat_col_index, gr, matched_ids,
            )
            if cat_candidates:
                sel = cat_candidates[0]
                correlation_map[sel.proposal_id] = gr
                matched_ids.add(sel.proposal_id)
                report.matched += 1
                logger.info(
                    "Fallback match: %s -> %s (by category+column)",
                    gr.rule_label, sel.proposal_id,
                )
                continue

            # No match — orphaned
            report.orphaned += 1
            report.orphaned_results.append(gr)

        # Count unmatched cart items (enabled, with syntax, not matched)
        for sel in cart:
            if sel.enabled and sel.final_gdq_syntax.strip():
                if sel.proposal_id not in matched_ids:
                    report.unmatched += 1

        return correlation_map, report

    def _find_by_category_column(
        self, cat_col_index: dict, gr, matched_ids: set,
    ) -> list:
        """Find cart items by rule category + target column.

        Maps GlueRuleResult.rule_category to RuleType values for lookup.
        Only returns candidates that are unique for the category+column
        combination (avoids ambiguous assignment).
        """
        # Map common Glue log categories to RuleType enum values
        category_map = {
            "mean": "mean_dual_guard",
            "standarddeviation": "stddev_dual_guard",
            "rowcount": "row_count_dual_guard",
            "completeness": "completeness",
            "columnvalues": "allowed_values",
            "distinctvaluescount": "distinct_count_exact",
            "isprimarykey": "is_primary_key",
            "customsql": "custom_sql",
        }

        glue_cat = (gr.rule_category or "").lower().replace(" ", "")
        mapped_cat = category_map.get(glue_cat, glue_cat)
        target = (gr.target_column or "").lower()

        key = f"{mapped_cat}|{target}"
        candidates = cat_col_index.get(key, [])

        # Filter out already matched
        available = [s for s in candidates if s.proposal_id not in matched_ids]

        # Only return if unique (avoid ambiguous assignment)
        if len(available) == 1:
            return available
        return []

    def apply_results_to_cart(
        self,
        cart: list,
        correlation_map: dict[str, "GlueRuleResult"],
    ) -> tuple[int, int]:
        """Write Glue test results back to cart RuleSelections.

        Args:
            cart: list[RuleSelection] (mutated in-place).
            correlation_map: {proposal_id: GlueRuleResult} from correlate_results.

        Returns:
            Tuple of (applied, skipped) counts.
        """
        applied = 0
        skipped = 0
        now = datetime.now(timezone.utc).isoformat()

        for sel in cart:
            if sel.proposal_id in correlation_map:
                sel.glue_test_result = correlation_map[sel.proposal_id]
                sel.glue_tested_at = now
                sel.glue_tested_syntax_hash = _syntax_hash(sel.final_gdq_syntax)
                applied += 1
            else:
                skipped += 1

        return applied, skipped
