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

from core.models.enums import ConfidenceLevel, ExportOutputMode, RuleType
from core.models.rule_proposal import RuleProposal
from core.models.rule_selection import RuleSelection
from core.rule_explainer import explain_rule, explain_rule_detail


@dataclass
class ExportResult:
    """Resultado da exportação."""
    rules_text: str = ""
    rules_count: int = 0
    warnings: list[str] = field(default_factory=list)
    report: str = ""  # Relatório analítico markdown (modo ANALYTICAL_REPORT)


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
            if re.search(
                r'(Mean|StandardDeviation|Completeness|ColumnValues|DistinctValuesCount|RowCount)\s+"',
                stripped,
            ):
                warnings.append(f"Linha {i}: coluna com aspas (deve ser sem aspas na sintaxe GDQ)")

            # Funcoes dinamicas devem ser lowercase
            if re.search(r'(AVG|STD|LAST)\(', stripped):
                warnings.append(
                    f"Linha {i}: funcoes dinamicas devem ser lowercase (avg, std, last)"
                )

            # CustomSql checks
            if "CustomSql" in stripped:
                # Aspas duplas balanceadas
                if stripped.count('"') % 2 != 0:
                    warnings.append(f"Linha {i}: CustomSql com aspas duplas desbalanceadas")
                # 'from primary' presente
                if "from primary" not in stripped.lower():
                    warnings.append(f"Linha {i}: CustomSql sem 'from primary'")

            # Completeness com between (deve usar >=)
            if "Completeness" in stripped and "between" in stripped.lower():
                warnings.append(f"Linha {i}: Completeness deve usar >=, nao between")

            # IsPrimaryKey com virgula (deve ser espaco)
            if "IsPrimaryKey" in stripped and "," in stripped:
                warnings.append(
                    f"Linha {i}: IsPrimaryKey — colunas separadas por espaco, nao virgula"
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
                label = p.rule_type.value.replace("_", " ").title()
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
            rule_label = p.rule_type.value.replace("_", " ").title()
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
