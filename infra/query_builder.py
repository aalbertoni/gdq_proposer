"""
Montagem de queries SQL a partir de templates Jinja2.
Injeta funções adaptadas ao dialeto (Athena ou DuckDB).
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from infra.sql_dialect import SQLDialect, adapt_function


class QueryBuilder:
    """Constrói queries SQL a partir de templates Jinja2 com suporte a dialeto."""

    def __init__(
        self,
        dialect: SQLDialect = SQLDialect.ATHENA,
        templates_dir: str = "queries/templates",
    ):
        self.dialect = dialect
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            keep_trailing_newline=True,
        )

    def build_metadata_discovery(self, schema: str, table: str) -> str:
        """Query para descobrir colunas e tipos de uma tabela."""
        template = self.env.get_template("metadata_discovery.sql")
        return template.render(
            table=table,
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
        )

    def build_date_range(
        self,
        schema: str,
        table: str,
        temporal_col: str,
        date_expression: str = "",
        base_filter: str = "",
    ) -> str:
        """Query para min/max da coluna temporal e contagem de períodos."""
        template = self.env.get_template("date_range.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            temporal_col=temporal_col,
            date_expression=date_expression,
            base_filter=base_filter,
        )

    def build_volume_by_period(
        self,
        schema: str,
        table: str,
        temporal_col: str,
        date_expression: str = "",
        base_filter: str = "",
        limit: int = 50,
    ) -> str:
        """Query para row count por período."""
        template = self.env.get_template("volume_by_period.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            temporal_col=temporal_col,
            date_expression=date_expression,
            base_filter=base_filter,
            limit=limit,
        )

    def build_show_partitions(
        self,
        schema: str,
        table: str,
        partition_col: str = "partition_0",
    ) -> str:
        """Query para listar partições via SELECT DISTINCT."""
        template = self.env.get_template("show_partitions.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            partition_col=partition_col,
        )

    def resolve_date_expression(self, temporal_col: str, date_expression: str = "") -> str:
        """Resolve the date expression for WHERE clauses with date comparisons.

        DuckDB cannot compare VARCHAR columns to DATE values directly.
        When no date_expression is given, this wraps the column in
        TRY_CAST(... AS DATE) for DuckDB to handle string date columns.
        For Athena, Presto handles VARCHAR-to-DATE coercion implicitly,
        so the raw column reference is returned.
        """
        if date_expression:
            return date_expression
        if self.dialect == SQLDialect.DUCKDB:
            return f'TRY_CAST("{temporal_col}" AS DATE)'
        return f'"{temporal_col}"'

    def build_column_sample(
        self,
        schema: str,
        table: str,
        col: str,
        temporal_col: str,
        date_expression: str = "",
        sample_periods: int = 10,
        base_filter: str = "",
    ) -> str:
        """Query para profiling de uma coluna (contagens + cast numérico)."""
        template = self.env.get_template("column_sample.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            col=col,
            temporal_col=temporal_col,
            date_expression=self.resolve_date_expression(temporal_col, date_expression),
            date_lookback_expr=adapt_function(
                "DATE_SUBTRACT_DAYS", self.dialect, n=sample_periods,
            ),
            base_filter=base_filter,
        )

    def build_row_count_history(
        self,
        schema: str,
        table: str,
        date_expression: str,
        lookback_value: int,
        base_filter: str = "",
    ) -> str:
        """Query para row count por periodo (analise RowCount)."""
        template = self.env.get_template("row_count_history.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            date_expression=date_expression,
            date_lookback_expr=adapt_function(
                "DATE_SUBTRACT_DAYS", self.dialect, n=lookback_value,
            ),
            base_filter=base_filter,
        )

    def build_categorical_distribution(
        self,
        schema: str,
        table: str,
        col: str,
        date_expression: str,
        lookback_value: int,
        base_filter: str = "",
    ) -> str:
        """Query para distribuicao de valores categoricos por periodo."""
        template = self.env.get_template("categorical_distribution.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            col=col,
            date_expression=date_expression,
            date_lookback_expr=adapt_function(
                "DATE_SUBTRACT_DAYS", self.dialect, n=lookback_value,
            ),
            base_filter=base_filter,
        )

    def build_categorical_domain(
        self,
        schema: str,
        table: str,
        col: str,
        date_expression: str,
        lookback_value: int,
        base_filter: str = "",
        limit: int = 0,
    ) -> str:
        """Query para valores distintos e frequencia global."""
        template = self.env.get_template("categorical_domain.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            col=col,
            date_expression=date_expression,
            date_lookback_expr=adapt_function(
                "DATE_SUBTRACT_DAYS", self.dialect, n=lookback_value,
            ),
            base_filter=base_filter,
            limit=limit,
        )

    def build_numeric_history(
        self,
        schema: str,
        table: str,
        col: str,
        date_expression: str,
        lookback_value: int,
        base_filter: str = "",
    ) -> str:
        """Query para análise histórica de coluna numérica."""
        template = self.env.get_template("numeric_history.sql")

        quantiles = "0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99"
        approx_expr = adapt_function(
            "APPROX_PERCENTILE",
            self.dialect,
            col=f'CAST("{col}" AS DOUBLE)',
            quantiles=quantiles,
        )

        return template.render(
            col=col,
            date_expression=date_expression,
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            stddev_func=adapt_function(
                "STDDEV", self.dialect, expr="",
            ).split("(")[0],  # pega só o nome da função
            approx_percentile_expr=approx_expr,
            date_lookback_expr=adapt_function(
                "DATE_SUBTRACT_DAYS", self.dialect, n=lookback_value,
            ),
            base_filter=base_filter,
        )
