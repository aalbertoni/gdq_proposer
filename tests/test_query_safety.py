"""Testes para infra/query_safety.py."""

import pytest
from infra.query_safety import (
    validate_identifier,
    validate_lookback,
    validate_reference_date,
    sanitize_filter,
    build_equality_filter,
    LookbackMode,
    MAX_LOOKBACK_DAYS,
    MAX_LOOKBACK_PERIODS,
)


# ---------------------------------------------------------------------------
# validate_identifier
# ---------------------------------------------------------------------------

class TestValidateIdentifier:
    @pytest.mark.parametrize("name", [
        "VLR_SALD_AVNC_OPCR",
        "col1",
        "DT_REF",
        "_private",
        "a",
        "table_name_123",
        "ABC",
    ])
    def test_valid_identifiers(self, name):
        assert validate_identifier(name) == name

    @pytest.mark.parametrize("name, reason", [
        ('"quoted"', "aspas duplas"),
        ("col name", "espaço"),
        ("col;name", "ponto-e-vírgula"),
        ("1starts_with_number", "começa com número"),
        ("col-name", "hífen"),
        ("col.name", "ponto"),
        ("", "vazio"),
        ("DROP TABLE users--", "SQL injection"),
        ("col\nname", "newline"),
        ("col\tname", "tab"),
        ("col'name", "aspas simples"),
        ("col*", "asterisco"),
        ("col=1", "igual"),
    ])
    def test_invalid_identifiers(self, name, reason):
        with pytest.raises(ValueError, match="Identificador inválido"):
            validate_identifier(name)


# ---------------------------------------------------------------------------
# validate_lookback
# ---------------------------------------------------------------------------

class TestValidateLookback:
    def test_valid_days(self):
        assert validate_lookback(30, LookbackMode.DAYS) == 30

    def test_valid_periods(self):
        assert validate_lookback(50, LookbackMode.PERIODS) == 50

    def test_days_at_limit(self):
        assert validate_lookback(MAX_LOOKBACK_DAYS, LookbackMode.DAYS) == MAX_LOOKBACK_DAYS

    def test_periods_at_limit(self):
        assert validate_lookback(MAX_LOOKBACK_PERIODS, LookbackMode.PERIODS) == MAX_LOOKBACK_PERIODS

    def test_days_over_limit(self):
        with pytest.raises(ValueError, match="excede limite"):
            validate_lookback(MAX_LOOKBACK_DAYS + 1, LookbackMode.DAYS)

    def test_periods_over_limit(self):
        with pytest.raises(ValueError, match="excede limite"):
            validate_lookback(MAX_LOOKBACK_PERIODS + 1, LookbackMode.PERIODS)

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="positivo"):
            validate_lookback(0, LookbackMode.DAYS)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="positivo"):
            validate_lookback(-10, LookbackMode.PERIODS)

    def test_defaults_to_days(self):
        assert validate_lookback(30) == 30


# ---------------------------------------------------------------------------
# sanitize_filter
# ---------------------------------------------------------------------------

class TestSanitizeFilter:
    @pytest.mark.parametrize("sql", [
        "COD_SITU_OPCR = '1'",
        "VLR_SALD > 100.0",
        "COD_SITU_OPCR IN ('1', '2', '3')",
        "VLR_SALD BETWEEN 0 AND 10000",
        "IND_ATIVO = 1 AND VLR_SALD > 0",
        "DT_REF >= '2026-01-01'",
    ])
    def test_valid_filters(self, sql):
        assert sanitize_filter(sql) == sql.strip()

    def test_strips_whitespace(self):
        assert sanitize_filter("  col = 1  ") == "col = 1"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="vazio"):
            sanitize_filter("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="vazio"):
            sanitize_filter("   ")

    # --- Tokens bloqueados ---

    def test_semicolon_blocked(self):
        with pytest.raises(ValueError, match="token bloqueado"):
            sanitize_filter("col = 1; DROP TABLE users")

    def test_line_comment_blocked(self):
        with pytest.raises(ValueError, match="token bloqueado"):
            sanitize_filter("col = 1 -- comment")

    def test_block_comment_blocked(self):
        with pytest.raises(ValueError, match="token bloqueado"):
            sanitize_filter("col = 1 /* comment */")

    # --- Keywords bloqueadas ---

    @pytest.mark.parametrize("dangerous_sql", [
        "col = 1 UNION SELECT * FROM secrets",
        "col = 1 union select * from secrets",
        "INSERT INTO log VALUES (1)",
        "DELETE FROM users WHERE 1=1",
        "DROP TABLE users",
        "ALTER TABLE users ADD col int",
        "CREATE TABLE hack (id int)",
        "UPDATE users SET admin=1",
        "EXEC xp_cmdshell('dir')",
    ])
    def test_dangerous_keywords_blocked(self, dangerous_sql):
        with pytest.raises(ValueError, match="keyword bloqueada"):
            sanitize_filter(dangerous_sql)

    def test_keyword_as_substring_allowed(self):
        # "UPDATED_AT" contém "UPDATE" mas não como palavra isolada
        result = sanitize_filter("UPDATED_AT >= '2026-01-01'")
        assert result == "UPDATED_AT >= '2026-01-01'"

    def test_keyword_as_substring_exec_allowed(self):
        result = sanitize_filter("EXECUTION_STATUS = 'OK'")
        assert result == "EXECUTION_STATUS = 'OK'"

    def test_keyword_as_substring_union_allowed(self):
        result = sanitize_filter("REUNION_TYPE = 'A'")
        assert result == "REUNION_TYPE = 'A'"

    def test_keyword_as_substring_select_allowed(self):
        result = sanitize_filter("SELECTED_FLAG = 1")
        assert result == "SELECTED_FLAG = 1"

    # --- SELECT bloqueado (subquery prevention) ---

    def test_select_subquery_blocked(self):
        with pytest.raises(ValueError, match="keyword bloqueada"):
            sanitize_filter("col IN (SELECT id FROM users)")

    def test_select_standalone_blocked(self):
        with pytest.raises(ValueError, match="keyword bloqueada"):
            sanitize_filter("SELECT * FROM users")

    # --- Parenteses desbalanceados ---

    def test_balanced_parens_allowed(self):
        result = sanitize_filter("(COL1 = 1 OR COL2 = 2) AND COL3 > 0")
        assert "COL1" in result

    def test_unbalanced_open_paren_blocked(self):
        with pytest.raises(ValueError, match="parênteses desbalanceados"):
            sanitize_filter("(COL = 1 AND COL2 = 2")

    def test_unbalanced_close_paren_blocked(self):
        with pytest.raises(ValueError, match="parênteses desbalanceados"):
            sanitize_filter("COL = 1) AND COL2 = 2")

    def test_nested_parens_allowed(self):
        result = sanitize_filter("((A = 1 OR B = 2) AND (C = 3))")
        assert "A = 1" in result


# ---------------------------------------------------------------------------
# validate_reference_date
# ---------------------------------------------------------------------------

class TestValidateReferenceDate:
    def test_valid_date(self):
        assert validate_reference_date("2024-12-31") == "2024-12-31"

    def test_valid_date_start_of_year(self):
        assert validate_reference_date("2025-01-01") == "2025-01-01"

    def test_rejects_datetime(self):
        with pytest.raises(ValueError):
            validate_reference_date("2024-12-31 10:00:00")

    def test_rejects_slash_format(self):
        with pytest.raises(ValueError):
            validate_reference_date("31/12/2024")

    def test_rejects_sql_injection(self):
        with pytest.raises(ValueError):
            validate_reference_date("2024-01-01'); DROP TABLE x; --")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            validate_reference_date("")

    def test_rejects_word(self):
        with pytest.raises(ValueError):
            validate_reference_date("today")


# ---------------------------------------------------------------------------
# Subpopulation filter construction safety
# ---------------------------------------------------------------------------

class TestBuildEqualityFilter:
    """Testa build_equality_filter (funcao pura de query_safety)."""

    # --- String path (is_numeric_column=False) ---

    def test_string_simple_value(self):
        result = build_equality_filter("TIPO_PRODUTO", "CONSIGNADO")
        assert result == '"TIPO_PRODUTO" = \'CONSIGNADO\''

    def test_string_value_with_single_quote_escaped(self):
        result = build_equality_filter("NOME", "O'Brien")
        assert result == '"NOME" = \'O\'\'Brien\''

    def test_string_invalid_column_rejected(self):
        with pytest.raises(ValueError, match="Identificador"):
            build_equality_filter("col; DROP", "value")

    def test_string_semicolon_in_value_rejected(self):
        with pytest.raises(ValueError, match="token bloqueado"):
            build_equality_filter("COL", "val; DROP TABLE x")

    def test_string_comment_in_value_rejected(self):
        with pytest.raises(ValueError, match="token bloqueado"):
            build_equality_filter("COL", "val -- comment")

    # --- Numeric path (is_numeric_column=True) ---

    def test_numeric_int(self):
        result = build_equality_filter("COD_SITU", 1, is_numeric_column=True)
        assert result == '"COD_SITU" = 1'

    def test_numeric_bigint(self):
        result = build_equality_filter("COD_TIPO", 12345, is_numeric_column=True)
        assert result == '"COD_TIPO" = 12345'

    def test_numeric_float(self):
        result = build_equality_filter("VALOR", 3.14, is_numeric_column=True)
        assert result == '"VALOR" = 3.14'

    def test_numeric_negative(self):
        result = build_equality_filter("SALDO", -100, is_numeric_column=True)
        assert result == '"SALDO" = -100'

    def test_numeric_string_castable_to_int(self):
        result = build_equality_filter("COD", "42", is_numeric_column=True)
        assert result == '"COD" = 42'

    def test_numeric_string_castable_to_float(self):
        result = build_equality_filter("TAXA", "0.05", is_numeric_column=True)
        assert result == '"TAXA" = 0.05'

    def test_numeric_injection_or_rejected(self):
        with pytest.raises(ValueError, match="nao e numerico"):
            build_equality_filter("COL", "1 OR 1=1", is_numeric_column=True)

    def test_numeric_injection_semicolon_rejected(self):
        with pytest.raises(ValueError, match="nao e numerico"):
            build_equality_filter("COL", "1; DROP TABLE x", is_numeric_column=True)

    def test_numeric_injection_comment_rejected(self):
        with pytest.raises(ValueError, match="nao e numerico"):
            build_equality_filter("COL", "1 -- comment", is_numeric_column=True)

    def test_numeric_none_rejected(self):
        with pytest.raises(ValueError, match="nao e numerico"):
            build_equality_filter("COL", None, is_numeric_column=True)

    def test_numeric_nan_string_rejected(self):
        with pytest.raises(ValueError, match="nao e numerico"):
            build_equality_filter("COL", "NaN", is_numeric_column=True)

    def test_numeric_infinity_string_rejected(self):
        with pytest.raises(ValueError, match="nao e numerico"):
            build_equality_filter("COL", "Infinity", is_numeric_column=True)

    def test_numeric_float_nan_rejected(self):
        with pytest.raises(ValueError, match="nao e numerico"):
            build_equality_filter("COL", float("nan"), is_numeric_column=True)

    def test_numeric_float_inf_rejected(self):
        with pytest.raises(ValueError, match="nao e numerico"):
            build_equality_filter("COL", float("inf"), is_numeric_column=True)

    def test_numeric_empty_string_rejected(self):
        with pytest.raises(ValueError, match="nao e numerico"):
            build_equality_filter("COL", "", is_numeric_column=True)

    def test_numeric_bigint_precision_preserved(self):
        """BIGINT grande nao perde precisao (nao passa por float)."""
        big = 9007199254740993  # > 2^53
        result = build_equality_filter("ID", big, is_numeric_column=True)
        assert result == f'"ID" = {big}'

    def test_numeric_bigint_string_precision_preserved(self):
        result = build_equality_filter("ID", "9007199254740993", is_numeric_column=True)
        assert result == '"ID" = 9007199254740993'

    def test_numeric_zero(self):
        result = build_equality_filter("FLAG", 0, is_numeric_column=True)
        assert result == '"FLAG" = 0'
