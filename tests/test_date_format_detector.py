"""Testes para core/date_format_detector.py — deteccao inteligente de formato de data."""

from core.date_format_detector import detect_date_format


class TestIntegerFormat:
    def test_yyyymmdd_8_digits(self):
        idx, samples = detect_date_format(["20240115", "20240116", "20240117"], is_integer=True)
        assert idx == 0  # yyyyMMdd

    def test_yyyymm_6_digits(self):
        idx, samples = detect_date_format(["202401", "202402", "202403"], is_integer=True)
        assert idx == 1  # yyyyMM

    def test_epoch_seconds_10_digits(self):
        idx, samples = detect_date_format(["1705276800", "1705363200"], is_integer=True)
        assert idx == 2  # Epoch seconds

    def test_epoch_milliseconds_13_digits(self):
        idx, samples = detect_date_format(["1705276800000", "1705363200000"], is_integer=True)
        assert idx == 3  # Epoch milliseconds

    def test_float_repr_stripped(self):
        """Integer values may arrive as '202401.0' from Athena."""
        idx, _ = detect_date_format(["202401.0", "202402.0"], is_integer=True)
        assert idx == 1  # yyyyMM (6 digits after stripping .0)

    def test_mixed_lengths_majority_wins(self):
        idx, _ = detect_date_format(["20240115", "20240116", "202401"], is_integer=True)
        assert idx == 0  # yyyyMMdd (2 out of 3)

    def test_empty_values(self):
        idx, samples = detect_date_format([], is_integer=True)
        assert idx == 0
        assert samples == []

    def test_non_numeric_fallback(self):
        idx, _ = detect_date_format(["abc", "def"], is_integer=True)
        assert idx == 0  # Default fallback


class TestStringFormat:
    def test_yyyy_mm_dd(self):
        idx, _ = detect_date_format(["2024-01-15", "2024-01-16"], is_integer=False)
        assert idx == 0  # yyyy-MM-dd

    def test_yyyymmdd_string(self):
        idx, _ = detect_date_format(["20240115", "20240116"], is_integer=False)
        assert idx == 1  # yyyyMMdd

    def test_yyyymm_string(self):
        idx, _ = detect_date_format(["202401", "202402"], is_integer=False)
        assert idx == 2  # yyyyMM

    def test_dd_mm_yyyy(self):
        idx, _ = detect_date_format(["15/01/2024", "16/01/2024"], is_integer=False)
        assert idx == 3  # dd/MM/yyyy

    def test_timestamp(self):
        idx, _ = detect_date_format(["2024-01-15 10:30:00", "2024-01-16 11:00:00"], is_integer=False)
        assert idx == 4  # yyyy-MM-dd HH:mm:ss

    def test_empty_values(self):
        idx, samples = detect_date_format([], is_integer=False)
        assert idx == 0
        assert samples == []

    def test_unrecognized_pattern_defaults(self):
        idx, _ = detect_date_format(["Jan 2024", "Feb 2024"], is_integer=False)
        assert idx == 0  # Default fallback

    def test_samples_returned(self):
        vals = ["2024-01-15", "2024-01-16", "2024-01-17"]
        idx, samples = detect_date_format(vals, is_integer=False)
        assert samples == vals

    def test_max_5_samples(self):
        vals = [f"2024-01-{i:02d}" for i in range(1, 10)]
        _, samples = detect_date_format(vals, is_integer=False)
        assert len(samples) == 5
