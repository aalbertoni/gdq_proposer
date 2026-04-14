"""Testes unitários para core/sampling_calculator.py.

Valida fórmula de Cochran, limites operacionais e edge cases.
"""

import pytest

from core.sampling_calculator import (
    CONFIDENCE_Z,
    MAX_SAMPLE_ROWS,
    MAX_USEFUL_PCT,
    MIN_POPULATION,
    MIN_SAMPLE_PCT,
    compute_sample_pct,
    compute_sample_size,
)


# ---------------------------------------------------------------------------
# compute_sample_size — Cochran + correção finita
# ---------------------------------------------------------------------------

class TestComputeSampleSize:
    """Testes para compute_sample_size."""

    def test_standard_case_95_5(self):
        """N=1M, 95% confiança, 5% margem → ~385."""
        n = compute_sample_size(1_000_000, 0.95, 0.05)
        assert 380 <= n <= 390

    def test_standard_case_99_1(self):
        """N=1M, 99% confiança, 1% margem → ~16590."""
        n = compute_sample_size(1_000_000, 0.99, 0.01)
        assert 16_000 <= n <= 17_000

    def test_standard_case_90_10(self):
        """N=1M, 90% confiança, 10% margem → ~68."""
        n = compute_sample_size(1_000_000, 0.90, 0.10)
        assert 65 <= n <= 70

    def test_small_population_correction(self):
        """População pequena: correção finita reduz n significativamente."""
        n_large = compute_sample_size(10_000_000, 0.95, 0.05)
        n_small = compute_sample_size(1_000, 0.95, 0.05)
        assert n_small < n_large
        assert 270 <= n_small <= 290  # ~278 para N=1000

    def test_very_small_population(self):
        """N=10 → amostra próxima da população."""
        n = compute_sample_size(10, 0.95, 0.05)
        assert n <= 10

    def test_population_1(self):
        """N=1 → n=1."""
        n = compute_sample_size(1, 0.95, 0.05)
        assert n == 1

    def test_minimum_always_1(self):
        """Resultado nunca é menor que 1."""
        n = compute_sample_size(1, 0.90, 0.50)
        assert n >= 1

    @pytest.mark.parametrize("confidence", [0.90, 0.95, 0.99])
    def test_all_confidence_levels(self, confidence):
        """Todos os níveis de confiança suportados."""
        n = compute_sample_size(1_000_000, confidence, 0.05)
        assert n > 0

    @pytest.mark.parametrize("margin", [0.01, 0.02, 0.05, 0.10])
    def test_margin_inversely_proportional(self, margin):
        """Margem menor → amostra maior."""
        n = compute_sample_size(1_000_000, 0.95, margin)
        assert n > 0

    def test_margin_ordering(self):
        """Margem 1% > margem 5% > margem 10%."""
        n1 = compute_sample_size(1_000_000, 0.95, 0.01)
        n5 = compute_sample_size(1_000_000, 0.95, 0.05)
        n10 = compute_sample_size(1_000_000, 0.95, 0.10)
        assert n1 > n5 > n10

    def test_confidence_ordering(self):
        """99% > 95% > 90%."""
        n99 = compute_sample_size(1_000_000, 0.99, 0.05)
        n95 = compute_sample_size(1_000_000, 0.95, 0.05)
        n90 = compute_sample_size(1_000_000, 0.90, 0.05)
        assert n99 > n95 > n90

    def test_invalid_population_zero(self):
        with pytest.raises(ValueError, match="positivo"):
            compute_sample_size(0, 0.95, 0.05)

    def test_invalid_population_negative(self):
        with pytest.raises(ValueError, match="positivo"):
            compute_sample_size(-100, 0.95, 0.05)

    def test_invalid_confidence(self):
        with pytest.raises(ValueError, match="confidence"):
            compute_sample_size(1_000_000, 0.80, 0.05)

    def test_invalid_margin_too_small(self):
        with pytest.raises(ValueError, match="margin"):
            compute_sample_size(1_000_000, 0.95, 0.0001)

    def test_invalid_margin_too_large(self):
        with pytest.raises(ValueError, match="margin"):
            compute_sample_size(1_000_000, 0.95, 0.60)


# ---------------------------------------------------------------------------
# compute_sample_pct — porcentagem para TABLESAMPLE
# ---------------------------------------------------------------------------

class TestComputeSamplePct:
    """Testes para compute_sample_pct."""

    def test_none_for_small_population(self):
        """Tabela < MIN_POPULATION → None."""
        assert compute_sample_pct(10_000, 0.95, 0.05) is None
        assert compute_sample_pct(49_999, 0.95, 0.05) is None

    def test_none_at_boundary(self):
        """Exatamente MIN_POPULATION-1 → None."""
        assert compute_sample_pct(MIN_POPULATION - 1, 0.95, 0.05) is None

    def test_works_at_minimum_population(self):
        """Exatamente MIN_POPULATION → retorna pct."""
        pct = compute_sample_pct(MIN_POPULATION, 0.95, 0.05)
        assert pct is not None
        assert pct > 0

    def test_none_for_high_pct(self):
        """Quando pct > MAX_USEFUL_PCT → None (amostra ineficiente)."""
        # Pop 50k, conf 99%, margin 0.5% → n~28515 → pct~57% > 50%
        pct = compute_sample_pct(50_000, 0.99, 0.005)
        assert pct is None

    def test_floor_applied(self):
        """Para tabelas muito grandes, pct recebe floor de MIN_SAMPLE_PCT."""
        pct = compute_sample_pct(100_000_000, 0.95, 0.05)
        assert pct is not None
        assert pct >= MIN_SAMPLE_PCT

    def test_large_population_gets_floor(self):
        """15M com 95%/5% → n=385, pct=0.0026% → floor 0.1%."""
        pct = compute_sample_pct(15_000_000, 0.95, 0.05)
        assert pct == MIN_SAMPLE_PCT  # 0.1%

    def test_max_sample_rows_ceiling(self):
        """Teto de MAX_SAMPLE_ROWS aplicado."""
        # 1 bilhão de rows, 0.1% = 1M rows > MAX_SAMPLE_ROWS
        pct = compute_sample_pct(1_000_000_000, 0.95, 0.05)
        assert pct is not None
        estimated_rows = 1_000_000_000 * pct / 100
        assert estimated_rows <= MAX_SAMPLE_ROWS + 1  # tolerância de arredondamento

    def test_pct_range(self):
        """pct está sempre entre 0 e 100."""
        for pop in [100_000, 1_000_000, 10_000_000, 100_000_000]:
            pct = compute_sample_pct(pop, 0.95, 0.05)
            if pct is not None:
                assert 0 < pct <= 100

    def test_pct_decreases_with_population(self):
        """Tabela maior → pct menor (ou igual ao floor)."""
        pct_100k = compute_sample_pct(100_000, 0.95, 0.05)
        pct_10m = compute_sample_pct(10_000_000, 0.95, 0.05)
        assert pct_100k is not None
        assert pct_10m is not None
        assert pct_100k >= pct_10m

    def test_precision(self):
        """pct arredondado a 4 casas decimais."""
        pct = compute_sample_pct(200_000, 0.95, 0.05)
        assert pct is not None
        # Verificar que tem no máximo 4 casas decimais
        assert pct == round(pct, 4)
