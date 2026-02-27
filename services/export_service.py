"""
Camada E: Exportação de regras GDQ.

Gera sintaxe final, valida e exporta em diferentes formatos.
Inclui relatório analítico markdown com evidência e racional por regra.

Definido conforme docs/technical_spec_v1.md seção 4.5.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from core.models.enums import ConfidenceLevel, ExportOutputMode, RuleType, get_rule_label
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import RuleSelection
from core.rule_explainer import explain_rule, explain_rule_detail


@dataclass
class ExportResult:
    """Resultado da exportacao de regras GDQ.

    Attributes:
        rules_text: Texto concatenado das regras GDQ (uma por linha).
        rules_count: Quantidade de regras exportadas (apenas habilitadas).
        warnings: Avisos de sintaxe/consistencia detectados na validacao.
        report: Relatorio analitico em markdown. Populado automaticamente
            quando export() e chamado com mode=ExportOutputMode.ANALYTICAL_REPORT.
    """

    rules_text: str = ""
    rules_count: int = 0
    warnings: list[str] = field(default_factory=list)
    report: str = ""


class ExportService:
    """Exportação de regras GDQ selecionadas."""

    def generate_syntax(self, selections: list[RuleSelection]) -> str:
        """Concatena sintaxe GDQ de regras habilitadas.

        Args:
            selections: Lista de RuleSelection do carrinho.

        Returns:
            String com regras separadas por newline.
        """
        enabled = [s for s in selections if s.enabled]
        lines = []
        for s in enabled:
            syntax = s.final_gdq_syntax.strip()
            if syntax:
                lines.append(syntax)
        return "\n".join(lines)

    def validate_syntax(self, syntax: str) -> list[str]:
        """Validação da sintaxe GDQ com checks específicos.

        Verifica estrutura, casing, aspas, operadores e padrões GDQ.

        Returns:
            Lista de warnings (vazia = OK).
        """
        warnings: list[str] = []
        if not syntax.strip():
            warnings.append("Sintaxe vazia")
            return warnings

        # Parenteses balanceados
        if syntax.count("(") != syntax.count(")"):
            warnings.append(
                f"Parenteses desbalanceados: {syntax.count('(')} abre, {syntax.count(')')} fecha"
            )

        for i, line in enumerate(syntax.strip().split("\n"), 1):
            stripped = line.strip()
            if not stripped:
                warnings.append(f"Linha {i} vazia")
                continue

            # Coluna com aspas em regras built-in (deve ser sem)
            match_quoted = re.search(
                r'(Mean|StandardDeviation|Completeness|ColumnValues|DistinctValuesCount|RowCount)\s+"(\w+)"',
                stripped,
            )
            if match_quoted:
                rule_name = match_quoted.group(1)
                col_name = match_quoted.group(2)
                warnings.append(
                    f'Linha {i}: coluna com aspas em {rule_name} — GDQ usa nomes sem aspas '
                    f'para regras built-in. '
                    f'Correto: `{rule_name} {col_name}` (sem aspas duplas)'
                )

            # Funcoes dinamicas devem ser lowercase
            upper_match = re.search(r'(AVG|STD|LAST)\(', stripped)
            if upper_match:
                wrong = upper_match.group(1)
                warnings.append(
                    f"Linha {i}: funcao '{wrong}' deve ser lowercase — GDQ exige casing minusculo "
                    f"para funcoes dinamicas. "
                    f"Correto: `{wrong.lower()}(last(N))`. "
                    f"Exemplo: `avg(last(30))`, `std(last(30))`"
                )

            # CustomSql checks
            if "CustomSql" in stripped:
                # Aspas duplas balanceadas
                if stripped.count('"') % 2 != 0:
                    warnings.append(
                        f"Linha {i}: CustomSql com aspas duplas desbalanceadas — "
                        f"verifique se abriu e fechou todas as aspas no SQL. "
                        f'Exemplo correto: CustomSql "select ... from primary" between X and Y'
                    )
                # 'from primary' presente
                if "from primary" not in stripped.lower():
                    warnings.append(
                        f"Linha {i}: CustomSql sem 'from primary' — "
                        f"toda regra CustomSql deve referenciar a tabela como 'primary'. "
                        f"Exemplo correto: "
                        f'CustomSql "select cast(sum(case when COL = \'VAL\' '
                        f"then 1 else 0 end) as double) * 100.0 / count(*) "
                        f'from primary" between X and Y'
                    )

            # Completeness com between (deve usar >=)
            if "Completeness" in stripped and "between" in stripped.lower():
                comp_match = re.search(r'Completeness\s+(\S+)', stripped)
                col_ref = comp_match.group(1) if comp_match else "COL"
                warnings.append(
                    f"Linha {i}: Completeness deve usar >=, nao between — "
                    f"a regra define um limite minimo de preenchimento. "
                    f"Correto: `Completeness {col_ref} >= 1.00`"
                )

            # IsPrimaryKey com virgula (deve ser espaco)
            if "IsPrimaryKey" in stripped and "," in stripped:
                cols_part = stripped.split("IsPrimaryKey", 1)[1].strip()
                fixed_cols = " ".join(c.strip() for c in cols_part.split(","))
                warnings.append(
                    f"Linha {i}: IsPrimaryKey — colunas devem ser separadas por espaco, nao virgula. "
                    f"Correto: `IsPrimaryKey {fixed_cols}`"
                )

        return warnings

    def check_consistency(self, selections: list[RuleSelection]) -> list[str]:
        """Verifica consistência entre regras antes do export.

        Detecta duplicatas, conflitos e redundâncias.

        Returns:
            Lista de warnings de consistência.
        """
        warnings: list[str] = []
        enabled = [s for s in selections if s.enabled and s.final_gdq_syntax.strip()]
        if not enabled:
            return warnings

        # Detectar duplicatas (mesma coluna + mesmo tipo)
        seen: dict[str, int] = {}
        for s in enabled:
            p = s.proposal
            key = f"{p.rule_type.value}|{p.target_column or '(tabela)'}|{p.category_value or ''}"
            if key in seen:
                target = p.target_column or "(tabela)"
                label = get_rule_label(p.rule_type)
                suffix = f" ({p.category_value})" if p.category_value else ""
                warnings.append(
                    f"Regra duplicada: {label} — {target}{suffix} aparece mais de uma vez"
                )
            seen[key] = seen.get(key, 0) + 1

        # Mean e StdDev com N diferente para mesma coluna
        dual_guard_params: dict[str, list[tuple[str, int]]] = {}
        for s in enabled:
            p = s.proposal
            if p.rule_type in (
                RuleType.MEAN_DUAL_GUARD,
                RuleType.STDDEV_DUAL_GUARD,
            ) and p.target_column:
                col = p.target_column
                n = p.baseline_window or 30
                label = "Mean" if p.rule_type == RuleType.MEAN_DUAL_GUARD else "StdDev"
                dual_guard_params.setdefault(col, []).append((label, n))

        for col, entries in dual_guard_params.items():
            if len(entries) > 1:
                n_values = {n for _, n in entries}
                if len(n_values) > 1:
                    labels = ", ".join(f"{lbl}(N={n})" for lbl, n in entries)
                    warnings.append(
                        f"Coluna {col}: Mean e StdDev com N diferentes ({labels}) "
                        f"— considere usar o mesmo N para consistencia"
                    )

        # Check 3: Frequency upper bounds sum > 100%
        freq_rules = [
            s for s in enabled
            if s.proposal.rule_type in (
                RuleType.CATEGORY_FREQUENCY_STATIC,
                RuleType.CATEGORY_FREQUENCY_DYNAMIC,
                RuleType.CATEGORY_FREQUENCY_HYBRID,
            )
        ]
        freq_by_col: dict[str, list[RuleSelection]] = {}
        for s in freq_rules:
            col = s.proposal.target_column or "(tabela)"
            freq_by_col.setdefault(col, []).append(s)

        for col, col_sels in freq_by_col.items():
            static_sels = [
                s for s in col_sels
                if s.proposal.rule_type == RuleType.CATEGORY_FREQUENCY_STATIC
            ]
            if len(static_sels) >= 2:
                upper_sum = sum(
                    s.proposal.suggested_upper
                    for s in static_sels
                    if s.proposal.suggested_upper is not None
                )
                if upper_sum > 100:
                    warnings.append(
                        f"Conflito: as frequencias de {len(static_sels)} valores de `{col}` "
                        f"somam ate {upper_sum:.0f}% (maximo possivel: 100%). "
                        f"Revise os limites superiores das regras de frequencia."
                    )

        # Check 4: IsPrimaryKey + Completeness redundancy
        pk_sels = [s for s in enabled if s.proposal.rule_type == RuleType.IS_PRIMARY_KEY]
        completeness_sels = [s for s in enabled if s.proposal.rule_type == RuleType.COMPLETENESS]

        if pk_sels and completeness_sels:
            pk_cols: set[str] = set()
            for s in pk_sels:
                # IsPrimaryKey column field contains space-separated columns
                if s.proposal.target_column:
                    pk_cols.update(s.proposal.target_column.split())

            redundant = [
                s for s in completeness_sels
                if s.proposal.target_column in pk_cols
            ]
            if redundant:
                cols_str = ", ".join(
                    s.proposal.target_column for s in redundant
                    if s.proposal.target_column
                )
                warnings.append(
                    f"Redundancia: `Completeness` para {cols_str} e redundante com "
                    f"`IsPrimaryKey` que ja valida completude dessas colunas."
                )

        # Check 5: RowCount + Mean with very different N
        rowcount_sels = [
            s for s in enabled
            if s.proposal.rule_type == RuleType.ROW_COUNT_DUAL_GUARD
        ]
        mean_sels = [
            s for s in enabled
            if s.proposal.rule_type == RuleType.MEAN_DUAL_GUARD
        ]

        if rowcount_sels and mean_sels:
            rc_n = rowcount_sels[0].proposal.baseline_window
            for ms in mean_sels:
                mr_n = ms.proposal.baseline_window
                if mr_n and rc_n and abs(mr_n - rc_n) > 15:
                    warnings.append(
                        f"Aviso: RowCount usa N={rc_n} mas Mean `{ms.proposal.target_column}` "
                        f"usa N={mr_n}. "
                        f"Janelas de analise muito diferentes podem causar "
                        f"resultados inconsistentes."
                    )
                    break  # Only warn once

        return warnings

    def export(
        self,
        selections: list[RuleSelection],
        mode: ExportOutputMode = ExportOutputMode.GDQ_RUNTIME,
    ) -> ExportResult:
        """Exporta regras no formato solicitado.

        Args:
            selections: Lista de RuleSelection.
            mode: Formato de output.

        Returns:
            ExportResult com texto, metadados e relatório (se ANALYTICAL_REPORT).
        """
        syntax = self.generate_syntax(selections)
        warnings = self.validate_syntax(syntax)
        warnings.extend(self.check_consistency(selections))
        enabled_count = sum(1 for s in selections if s.enabled and s.final_gdq_syntax.strip())

        report = ""
        if mode == ExportOutputMode.ANALYTICAL_REPORT:
            report = self.export_analytical_report(selections)

        return ExportResult(
            rules_text=syntax,
            rules_count=enabled_count,
            warnings=warnings,
            report=report,
        )

    def export_analytical_report(
        self,
        selections: list[RuleSelection],
        table_name: Optional[str] = None,
    ) -> str:
        """Gera relatório analítico markdown.

        Inclui por regra: sintaxe GDQ, evidência de backtest e racional
        em linguagem natural.

        Args:
            selections: Lista de RuleSelection do carrinho.
            table_name: Nome da tabela (schema.table). Se None, infere do proposal.

        Returns:
            String markdown com relatório completo.
        """
        enabled = [s for s in selections if s.enabled and s.final_gdq_syntax.strip()]
        if not enabled:
            return "# Relatorio vazio\nNenhuma regra habilitada."

        # Inferir nome da tabela
        if not table_name:
            p0 = enabled[0].proposal
            table_name = p0.target_table

        # Contagens
        total = len(enabled)
        high_conf = sum(
            1 for s in enabled if s.proposal.confidence == ConfidenceLevel.HIGH
        )
        med_conf = sum(
            1 for s in enabled if s.proposal.confidence == ConfidenceLevel.MEDIUM
        )
        low_conf = sum(
            1 for s in enabled if s.proposal.confidence == ConfidenceLevel.LOW
        )
        with_warnings = sum(1 for s in enabled if s.proposal.warnings)

        lines = [
            "# Relatorio Analitico de Regras GDQ",
            "",
            f"**Tabela:** `{table_name}`",
            f"**Gerado em:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
            "## Resumo Executivo",
            "",
            f"- **Total de regras:** {total}",
            f"- **Alta confianca:** {high_conf}",
            f"- **Media confianca:** {med_conf}",
            f"- **Baixa confianca:** {low_conf}",
        ]
        if with_warnings:
            lines.append(f"- **Regras com avisos:** {with_warnings}")
        lines.extend(["", "---", "", "## Regras Propostas", ""])

        for idx, sel in enumerate(enabled, 1):
            p = sel.proposal
            target = p.target_column or "(tabela)"
            rule_label = get_rule_label(p.rule_type)
            confidence_map = {
                ConfidenceLevel.HIGH: "ALTA",
                ConfidenceLevel.MEDIUM: "MEDIA",
                ConfidenceLevel.LOW: "BAIXA",
            }

            lines.append(f"### {idx}. {rule_label} — {target}")
            lines.append("")
            lines.append(
                f"**Confianca:** {confidence_map.get(p.confidence, p.confidence.value)}"
            )
            lines.append("")

            # Racional (explanation)
            lines.append("**Racional:**")
            lines.append(explain_rule(p))
            lines.append("")

            # Evidencia (backtest detail)
            detail = explain_rule_detail(p)
            # Extrair a parte de parametros e evidencia (apos a primeira linha)
            detail_parts = detail.split("\n")
            # Pular a primeira linha (que é a mesma do explain_rule)
            extra = [l for l in detail_parts[1:] if l.strip()]
            if extra:
                for l in extra:
                    lines.append(l)
                lines.append("")

            # Sintaxe GDQ
            lines.append("**Sintaxe GDQ:**")
            lines.append("```")
            lines.append(sel.final_gdq_syntax)
            lines.append("```")
            lines.append("")

            # Warnings
            if p.warnings:
                lines.append("**Avisos:**")
                for w in p.warnings:
                    lines.append(f"- {w}")
                lines.append("")

            lines.extend(["---", ""])

        # Consistency warnings
        consistency = self.check_consistency(selections)
        if consistency:
            lines.append("## Avisos de Consistencia")
            lines.append("")
            for w in consistency:
                lines.append(f"- {w}")
            lines.extend(["", "---", ""])

        # Recomendacoes
        lines.append("## Recomendacoes")
        lines.append("")
        lines.append("- Regras de **alta confianca** podem ser cadastradas imediatamente")
        if med_conf:
            lines.append(
                "- Regras de **media confianca** devem ter parametros revisados antes do cadastro"
            )
        if low_conf:
            lines.append(
                "- Regras de **baixa confianca** nao sao recomendadas para producao"
            )
        if with_warnings:
            lines.append("- Regras com avisos devem ser analisadas individualmente")
        lines.append(
            "- Considere ajustar parametros de regras com cobertura abaixo de 75%"
        )

        return "\n".join(lines)
