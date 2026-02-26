"""
Renderizador de sintaxe GDQ a partir de DualGuardSpec.

Converte a representação intermediária DualGuardSpec em string GDQ
exata, respeitando rigorosamente as regras de formatação de produção.

NUNCA gerar string GDQ diretamente — sempre usar este renderer.

Definido conforme docs/gdq_syntax_reference.md.
"""

from core.models.dual_guard import DualGuardSpec
from core.models.enums import MetricRef


class DualGuardRenderer:
    """Renderiza DualGuardSpec como string GDQ válida."""

    def render(self, spec: DualGuardSpec) -> str:
        """Converte DualGuardSpec em string GDQ.

        Args:
            spec: Especificação intermediária da regra dual guard.

        Returns:
            String GDQ formatada para produção.
        """
        if spec.metric == MetricRef.CUSTOM_SQL:
            return self._render_custom_sql(spec)

        profile = spec.profile
        metric = spec.metric.value  # "Mean", "StandardDeviation", "RowCount"
        target = f" {spec.target}" if spec.target else ""
        n = spec.n_periods
        k = self._format_k(spec.n_sigma, profile.k_as_float)
        buffer = spec.buffer
        margin = spec.margin_pct

        # --- Sigma guard ---
        sigma_lower = self._build_sigma_lower(
            metric, target, n, k, buffer, profile,
        )
        sigma_upper = self._build_sigma_upper(
            metric, target, n, k, buffer, profile,
        )
        sigma_guard = f"({sigma_lower} AND {sigma_upper})"

        # Sigma-only mode: sem banda margem
        if not spec.margin_enabled:
            return sigma_guard

        # --- Margin guard ---
        margin_lower = self._build_margin_lower(
            metric, target, n, margin, buffer, profile,
        )
        margin_upper = self._build_margin_upper(
            metric, target, n, margin, buffer, profile,
        )
        margin_guard = f"({margin_lower} AND {margin_upper})"

        return f"({sigma_guard} OR {margin_guard})"

    def _render_custom_sql(self, spec: DualGuardSpec) -> str:
        """Renderiza CustomSql dinâmico (dual guard) ou híbrido (+ floor/ceiling)."""
        sql_expr = spec.custom_sql_expression
        n = spec.n_periods
        k = self._format_k(spec.n_sigma, spec.profile.k_as_float)
        buffer = spec.buffer
        margin = spec.margin_pct

        lo_margin = round(1 - margin, 2)
        hi_margin = round(1 + margin, 2)

        sigma_part = (
            f'(CustomSql "{sql_expr}" between '
            f"(avg(last({n})) - ({k} * std(last({n}))) - {buffer}) "
            f"and (avg(last({n})) + ({k} * std(last({n}))) + {buffer}))"
        )

        if not spec.margin_enabled:
            return sigma_part

        margin_part = (
            f'(CustomSql "{sql_expr}" between '
            f"(avg(last({n})) * {lo_margin} - {buffer}) "
            f"and (avg(last({n})) * {hi_margin} + {buffer}))"
        )

        dual_guard = f"({sigma_part} OR {margin_part})"

        # Modo hibrido: adiciona AND com floor/ceiling absolutos
        is_hybrid = spec.floor_pct > 0.0 or spec.ceiling_pct < 100.0
        if is_hybrid:
            floor_ceil = (
                f'(CustomSql "{sql_expr}" between '
                f"{spec.floor_pct} and {spec.ceiling_pct})"
            )
            return f"({dual_guard} AND {floor_ceil})"

        return dual_guard

    def _format_k(self, k: float, as_float: bool) -> str:
        if as_float:
            return f"{k:.1f}" if k == int(k) else f"{k}"
        return str(int(k)) if k == int(k) else f"{k}"

    def _build_sigma_lower(self, metric, target, n, k, buffer, profile):
        avg_expr = f"avg(last({n}))"
        std_expr = f"std(last({n}))"

        if profile.avg_multiply_one:
            center = f"{avg_expr} * 1.0"
        else:
            center = avg_expr

        sigma_part = f"({k} * {std_expr})"

        if profile.avg_multiply_one:
            # RowCount format: (avg(last(N)) * 1.0 - (K * std(last(N))))
            expr = f"({center} - {sigma_part})"
        else:
            # Mean/StdDev format: (avg(last(N)) - (K * std(last(N))) - buffer)
            expr = f"({center} - {sigma_part})"
            if profile.include_buffer and buffer > 0:
                expr = f"({center} - {sigma_part} - {buffer})"

        return f"({metric}{target} >= {expr})"

    def _build_sigma_upper(self, metric, target, n, k, buffer, profile):
        avg_expr = f"avg(last({n}))"
        std_expr = f"std(last({n}))"

        if profile.avg_multiply_one:
            center = f"{avg_expr} * 1.0"
        else:
            center = avg_expr

        sigma_part = f"({k} * {std_expr})"

        if profile.avg_multiply_one:
            expr = f"({center} + {sigma_part})"
        else:
            expr = f"({center} + {sigma_part})"
            if profile.include_buffer and buffer > 0:
                expr = f"({center} + {sigma_part} + {buffer})"

        return f"({metric}{target} <= {expr})"

    def _build_margin_lower(self, metric, target, n, margin, buffer, profile):
        avg_expr = f"avg(last({n}))"

        if profile.margin_format == "delta":
            # RowCount: avg - (avg * margin)
            expr = f"({avg_expr} - ({avg_expr} * {margin}))"
        else:
            # Mean/StdDev: avg * (1 - margin)
            lo_factor = round(1 - margin, 4)
            expr = f"({avg_expr} * {lo_factor})"
            if profile.include_buffer and buffer > 0:
                expr = f"{expr} - {buffer}"

        return f"({metric}{target} >= {expr})"

    def _build_margin_upper(self, metric, target, n, margin, buffer, profile):
        avg_expr = f"avg(last({n}))"

        if profile.margin_format == "delta":
            # RowCount: avg + (avg * margin)
            expr = f"({avg_expr} + ({avg_expr} * {margin}))"
        else:
            # Mean/StdDev: avg * (1 + margin)
            hi_factor = round(1 + margin, 4)
            expr = f"({avg_expr} * {hi_factor})"
            if profile.include_buffer and buffer > 0:
                expr = f"{expr} + {buffer}"

        return f"({metric}{target} <= {expr})"
