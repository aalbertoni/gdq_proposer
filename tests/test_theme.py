"""Testes para pages/components/theme.py — design system Itau."""

from pages.components.theme import (
    ORANGE, NAVY, SUCCESS, ERROR, WARNING,
    badge_html,
)


class TestColorConstants:
    def test_colors_are_hex_strings(self):
        for color in [ORANGE, NAVY, SUCCESS, ERROR, WARNING]:
            assert isinstance(color, str)
            assert color.startswith("#")
            assert len(color) == 7

    def test_orange_is_itau(self):
        assert ORANGE == "#EC7000"

    def test_navy_is_itau(self):
        assert NAVY == "#003087"


class TestBadgeHtml:
    def test_success_variant(self):
        html = badge_html("OK", "success")
        assert "OK" in html
        assert SUCCESS in html
        assert "<span" in html

    def test_error_variant(self):
        html = badge_html("Falhou", "error")
        assert "Falhou" in html
        assert ERROR in html

    def test_warning_variant(self):
        html = badge_html("Atencao", "warning")
        assert "Atencao" in html
        assert WARNING in html

    def test_unknown_variant_falls_back_to_default(self):
        html = badge_html("Test", "nonexistent")
        assert "Test" in html
        # Should use default gray style, not crash
        assert "<span" in html

    def test_xss_sanitization(self):
        html = badge_html("<script>alert('xss')</script>", "success")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_empty_text(self):
        html = badge_html("", "default")
        assert "<span" in html
