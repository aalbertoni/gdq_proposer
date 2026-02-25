"""
Camada E: Exportação de regras GDQ.

Gera sintaxe final, valida e exporta em diferentes formatos.

Definido conforme docs/technical_spec_v1.md seção 4.5.
"""

from dataclasses import dataclass, field

from core.models.enums import ExportOutputMode
from core.models.rule_selection import RuleSelection


@dataclass
class ExportResult:
    """Resultado da exportação."""
    rules_text: str = ""
    rules_count: int = 0
    warnings: list[str] = field(default_factory=list)


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
        """Validação básica da sintaxe GDQ.

        Retorna lista de warnings (vazia = OK).
        Validação completa será implementada no Sprint C1.
        """
        warnings = []
        if not syntax.strip():
            warnings.append("Sintaxe vazia")
            return warnings

        # Parenteses balanceados
        if syntax.count("(") != syntax.count(")"):
            warnings.append(
                f"Parenteses desbalanceados: {syntax.count('(')} abre, {syntax.count(')')} fecha"
            )

        # Cada linha deve ter conteudo
        for i, line in enumerate(syntax.strip().split("\n"), 1):
            if not line.strip():
                warnings.append(f"Linha {i} vazia")

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
            ExportResult com texto e metadados.
        """
        syntax = self.generate_syntax(selections)
        warnings = self.validate_syntax(syntax)
        enabled_count = sum(1 for s in selections if s.enabled and s.final_gdq_syntax.strip())

        return ExportResult(
            rules_text=syntax,
            rules_count=enabled_count,
            warnings=warnings,
        )
