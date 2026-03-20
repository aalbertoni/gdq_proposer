"""Testes para infra/query_safety.py."""

import pytest
from infra.query_safety import (
    validate_identifier,
    validate_lookback,
    validate_reference_date,
    sanitize_filter,
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
