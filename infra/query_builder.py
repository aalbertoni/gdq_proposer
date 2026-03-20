"""
Montagem de queries SQL a partir de templates Jinja2.
Injeta funções adaptadas ao dialeto (Athena ou DuckDB).
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from infra.query_safety import validate_identifier, validate_reference_date
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

    def date_lookback_expr(self, n: int, reference_date: str = "") -> str:
        """Gera expressao de lookback temporal.

        Se reference_date fornecido (YYYY-MM-DD), usa como ancora em vez
        de CURRENT_DATE. Isso permite analisar tabelas com dados historicos.
        """
        if reference_date:
            validate_reference_date(reference_date)
            return adapt_function(
                "DATE_SUBTRACT_DAYS_FROM", self.dialect,
                n=n, reference_date=reference_date,
            )
        return adapt_function("DATE_SUBTRACT_DAYS", self.dialect, n=n)

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
        partition_filter: str = "",
    ) -> str:
        """Query para min/max da coluna temporal e contagem de períodos.

        Aceita partition_filter para evitar full scan em tabelas particionadas.
        """
        template = self.env.get_template("date_range.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            temporal_col=temporal_col,
            date_expression=date_expression,
            base_filter=base_filter,
            partition_filter=partition_filter,
        )

    def build_volume_by_period(
        self,
        schema: str,
        table: str,
        temporal_col: str,
        date_expression: str = "",
        base_filter: str = "",
        partition_filter: str = "",
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
            partition_filter=partition_filter,
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

    def resolve_partition_filter(
        self,
        partition_column: str | None,
        partition_format: str | None = None,
        lookback_value: int = 30,
        reference_date: str = "",
        partition_is_integer: bool = False,
        # Deprecated — ignorado. Mantido para retrocompatibilidade de assinatura.
        date_expression: str | None = None,
    ) -> str:
        """Gera filtro de particao fisico para pruning de custo.

        O predicado NUNCA aplica funcao sobre a coluna de particao.
        Calcula o cutoff em Python e formata no layout fisico da particao.

        Returns:
            String SQL para WHERE ou string vazia se nao aplicavel.
        """
        if not partition_column:
            return ""
        from infra.partition_pruning import compute_cutoff_date, build_partition_predicate
        cutoff = compute_cutoff_date(reference_date or None, lookback_value)
        return build_partition_predicate(
            partition_column, partition_format, cutoff, self.dialect,
            is_integer=partition_is_integer,
        )

    def build_column_sample(
        self,
        schema: str,
        table: str,
        col: str,
        temporal_col: str,
        date_expression: str = "",
        sample_periods: int = 10,
        base_filter: str = "",
        partition_filter: str = "",
        reference_date: str = "",
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
            date_lookback_expr=self.date_lookback_expr(sample_periods, reference_date),
            approx_distinct_expr=adapt_function(
                "APPROX_DISTINCT", self.dialect, col=f'"{col}"',
            ),
            partition_filter=partition_filter,
            base_filter=base_filter,
        )

    def build_batch_column_sample(
        self,
        schema: str,
        table: str,
        string_cols: list[str],
        numeric_cols: list[str],
        temporal_col: str,
        date_expression: str = "",
        sample_periods: int = 10,
        base_filter: str = "",
        partition_filter: str = "",
        reference_date: str = "",
    ) -> str:
        """Batch profiling de múltiplas colunas em uma única query.

        Reduz N scans para 1, usando APPROX_DISTINCT para cardinalidade.
        """
        template = self.env.get_template("batch_column_sample.sql")

        str_col_data = [
            {
                "name": col,
                "approx_distinct_expr": adapt_function(
                    "APPROX_DISTINCT", self.dialect, col=f'"{col}"',
                ),
            }
            for col in string_cols
        ]
        num_col_data = [
            {
                "name": col,
                "approx_distinct_expr": adapt_function(
                    "APPROX_DISTINCT", self.dialect, col=f'"{col}"',
                ),
            }
            for col in numeric_cols
        ]

        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            string_cols=str_col_data,
            numeric_cols=num_col_data,
            date_expression=self.resolve_date_expression(temporal_col, date_expression),
            date_lookback_expr=self.date_lookback_expr(sample_periods, reference_date),
            partition_filter=partition_filter,
            base_filter=base_filter,
        )

    def build_row_count_history(
        self,
        schema: str,
        table: str,
        date_expression: str,
        lookback_value: int,
        base_filter: str = "",
        partition_filter: str = "",
        reference_date: str = "",
    ) -> str:
        """Query para row count por periodo (analise RowCount)."""
        template = self.env.get_template("row_count_history.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            date_expression=date_expression,
            date_lookback_expr=self.date_lookback_expr(lookback_value, reference_date),
            base_filter=base_filter,
            partition_filter=partition_filter,
        )

    def build_distinct_count_history(
        self,
        schema: str,
        table: str,
        col: str,
        date_expression: str,
        lookback_value: int,
        base_filter: str = "",
        partition_filter: str = "",
        reference_date: str = "",
    ) -> str:
        """Query para contagem de valores distintos por periodo.

        Args:
            schema: Schema da tabela.
            table: Nome da tabela.
            col: Coluna categorica.
            date_expression: Expressao SQL para eixo temporal.
            lookback_value: Dias de lookback.
            base_filter: Filtro SQL opcional.
            partition_filter: Filtro de particao para pruning.
            reference_date: Data ancora (YYYY-MM-DD) em vez de CURRENT_DATE.

        Returns:
            SQL renderizado.
        """
        template = self.env.get_template("distinct_count_history.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            col=col,
            date_expression=date_expression,
            date_lookback_expr=self.date_lookback_expr(lookback_value, reference_date),
            approx_distinct_expr=adapt_function(
                "APPROX_DISTINCT", self.dialect, col=f'CAST("{col}" AS VARCHAR)',
            ),
            base_filter=base_filter,
            partition_filter=partition_filter,
        )

    def build_categorical_distribution(
        self,
        schema: str,
        table: str,
        col: str,
        date_expression: str,
        lookback_value: int,
        base_filter: str = "",
        partition_filter: str = "",
        reference_date: str = "",
    ) -> str:
        """Query para distribuicao de valores categoricos por periodo."""
        template = self.env.get_template("categorical_distribution.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            col=col,
            date_expression=date_expression,
            date_lookback_expr=self.date_lookback_expr(lookback_value, reference_date),
            base_filter=base_filter,
            partition_filter=partition_filter,
        )

    def build_categorical_domain(
        self,
        schema: str,
        table: str,
        col: str,
        date_expression: str,
        lookback_value: int,
        base_filter: str = "",
        partition_filter: str = "",
        limit: int = 0,
        reference_date: str = "",
    ) -> str:
        """Query para valores distintos e frequencia global."""
        template = self.env.get_template("categorical_domain.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            col=col,
            date_expression=date_expression,
            date_lookback_expr=self.date_lookback_expr(lookback_value, reference_date),
            base_filter=base_filter,
            partition_filter=partition_filter,
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
        partition_filter: str = "",
        reference_date: str = "",
    ) -> str:
        """Query para análise histórica de coluna numérica."""
        template = self.env.get_template("numeric_history.sql")

        quantiles = "0.01, 0.05, 0.10, 0.25, 0.5, 0.75, 0.90, 0.95, 0.99"
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
            date_lookback_expr=self.date_lookback_expr(lookback_value, reference_date),
            base_filter=base_filter,
            partition_filter=partition_filter,
        )

    def build_uniqueness_check(
        self,
        schema: str,
        table: str,
        key_columns: list[str],
        date_expression: str,
        lookback_value: int,
        base_filter: str = "",
        partition_filter: str = "",
        reference_date: str = "",
    ) -> str:
        """Query para verificar unicidade e completude de colunas-chave por periodo.

        Handles composite keys by CONCATing columns with '||' separator.
        Athena does NOT support COUNT(DISTINCT col1, col2), so we use
        CONCAT(CAST(col1 AS VARCHAR), '||', CAST(col2 AS VARCHAR)).

        Args:
            schema: Schema da tabela.
            table: Nome da tabela.
            key_columns: Lista de colunas que compoe a chave primaria.
            date_expression: Expressao SQL para eixo temporal.
            lookback_value: Dias de lookback.
            base_filter: Filtro SQL opcional.
            partition_filter: Filtro de particao para pruning.
            reference_date: Data ancora (YYYY-MM-DD) em vez de CURRENT_DATE.

        Returns:
            SQL renderizado.

        Raises:
            ValueError: Se key_columns esta vazio ou contem identificador invalido.
        """
        if not key_columns:
            raise ValueError("key_columns nao pode ser vazio")

        # Validate all column names
        for col in key_columns:
            validate_identifier(col)

        # Build key expression: single column or CONCAT for composite
        if len(key_columns) == 1:
            key_expr = f'CAST("{key_columns[0]}" AS VARCHAR)'
        else:
            parts = [f'CAST("{col}" AS VARCHAR)' for col in key_columns]
            key_expr = "CONCAT(" + ", '||', ".join(parts) + ")"

        template = self.env.get_template("uniqueness_check.sql")
        return template.render(
            table_ref=adapt_function(
                "TABLE_REF", self.dialect, schema=schema, table=table,
            ),
            key_expr=key_expr,
            key_cols=key_columns,
            date_expression=date_expression,
            date_lookback_expr=self.date_lookback_expr(lookback_value, reference_date),
            base_filter=base_filter,
            partition_filter=partition_filter,
        )
