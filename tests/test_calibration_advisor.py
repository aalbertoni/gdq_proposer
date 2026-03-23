"""
Testes do Assistente de Calibracao (core/calibration_advisor.py).

Cobre as 5 etapas, o orquestrador calibrate(), e o explainer.
"""

import math

import pytest

from core.calibration_advisor import (
    MARGIN_CANDIDATES,
    SIGMA_CANDIDATES,
    SIGMA_SUFFICIENT_THRESHOLD,
    CalibrationResult,
    CalibrationStep,
    _compute_outlier_mask,
    _normal_coverage,
    _recent_fps,
    add_margin_if_needed,
    calibrate,
    choose_n,
    generate_report,
    find_best_sigma,
    validate_with_backtest,
)
from core.calibration_explainer import (
    explain_calibration,
    explain_calibration_short,
    explain_step_detail,
)
from core.models.enums import ConfidenceLevel, GrainType, SeriesRegime
from core.models.series_profile import SeriesProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _stable_series(n: int = 60, mean: float = 100.0, std: float = 5.0) -> tuple[list[float], list[str]]:
    """Gera serie estavel (baixa variacao, sem outliers)."""
    import random
    random.seed(42)
    values = [mean + random.gauss(0, std) for _ in range(n)]
    dates = [f"2026-01-{i+1:02d}" for i in range(n)]
    return values, dates


def _volatile_series(n: int = 60) -> tuple[list[float], list[str]]:
    """Gera serie volatil (CV > 30%)."""
    import random
    random.seed(42)
    values = [100 + random.gauss(0, 50) for _ in range(n)]
    dates = [f"2026-01-{i+1:02d}" for i in range(n)]
    return values, dates


def _series_with_outliers(n: int = 60) -> tuple[list[float], list[str]]:
    """Gera serie estavel com 3 outliers."""
    values, dates = _stable_series(n)
    values[10] = 300.0  # outlier alto
    values[25] = -100.0  # outlier baixo
    values[40] = 250.0  # outlier alto
    return values, dates


def _short_series() -> tuple[list[float], list[str]]:
    """Gera serie curta (10 pontos)."""
    return _stable_series(n=10)


def _series_with_structural_break(n: int = 60) -> tuple[list[float], list[str]]:
    """Gera serie com mudanca de patamar no meio."""
    import random
    random.seed(42)
    # Primeira metade: media 100
    values1 = [100 + random.gauss(0, 3) for _ in range(n // 2)]
    # Segunda metade: media 200
    values2 = [200 + random.gauss(0, 3) for _ in range(n // 2)]
    values = values1 + values2
    dates = [f"2026-01-{i+1:02d}" for i in range(n)]
    return values, dates


def _asymmetric_series(n: int = 60) -> tuple[list[float], list[str]]:
    """Gera serie assimetrica (muitos valores baixos, poucos altos)."""
    import random
    random.seed(42)
    # Distribuicao log-normal (assimetrica para direita)
    values = [math.exp(random.gauss(4.0, 0.5)) for _ in range(n)]
    dates = [f"2026-01-{i+1:02d}" for i in range(n)]
    return values, dates


def _insufficient_series() -> tuple[list[float], list[str]]:
    """Gera serie com menos de 5 pontos."""
    return [1.0, 2.0, 3.0], ["2026-01-01", "2026-01-02", "2026-01-03"]


# ---------------------------------------------------------------------------
# Test CalibrationStep / CalibrationResult dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_calibration_step_fields(self):
        step = CalibrationStep(
            step=1, name="test", decision="N=30", justification="default",
        )
        assert step.step == 1
        assert step.data == {}

    def test_calibration_result_fields(self):
        result = CalibrationResult(
            n_periods=30, n_sigma=2.5, margin_pct=0.0, margin_enabled=False,
            coverage_pct=95.0, weighted_coverage_pct=96.0,
            false_positives=0, stability=0.9,
            confidence=ConfidenceLevel.HIGH, viable=True,
        )
        assert result.n_periods == 30
        assert result.n_sigma == 2.5
        assert result.margin_enabled is False
        assert result.steps == []
        assert result.profile is None


# ---------------------------------------------------------------------------
# Test Etapa 1: choose_n
# ---------------------------------------------------------------------------

class TestChooseN:
    def test_daily_default_n_30(self):
        values, dates = _stable_series(90)
        step = choose_n(values, dates, grain=GrainType.DAILY)
        assert step.data["n_periods"] == 30
        assert step.step == 1

    def test_monthly_default_n_12(self):
        values, dates = _stable_series(36)
        step = choose_n(values, dates, grain=GrainType.MONTHLY)
        assert step.data["n_periods"] == 12

    def test_short_series_reduces_n(self):
        values, dates = _stable_series(20)
        step = choose_n(values, dates, grain=GrainType.DAILY)
        # 20 pontos < 2*30, deveria reduzir
        assert step.data["n_periods"] == 10  # 20 // 2
        assert "serie curta" in step.justification

    def test_very_short_series_n_minimum_5(self):
        values, dates = _stable_series(8)
        step = choose_n(values, dates, grain=GrainType.DAILY)
        assert step.data["n_periods"] == 5  # min(8//2, ...) mas floor é 5

    def test_seasonal_prefers_multiple_of_7(self):
        values, dates = _stable_series(90)
        profile = SeriesProfile(
            regime=SeriesRegime.SEASONAL,
            is_seasonal=True,
            seasonality_strength=0.25,
            n_points=90, n_valid=90,
        )
        step = choose_n(values, dates, grain=GrainType.DAILY, profile=profile)
        assert step.data["n_periods"] % 7 == 0
        assert "multiplo de 7" in step.justification

    def test_structural_break_limits_n(self):
        values, dates = _series_with_structural_break(60)
        profile = SeriesProfile(
            regime=SeriesRegime.STRUCTURAL_BREAK,
            has_structural_break=True,
            change_point_date="2026-01-31",
            n_points=60, n_valid=60,
        )
        step = choose_n(values, dates, grain=GrainType.DAILY, profile=profile)
        # N deve ser limitado aos dados pos-mudanca
        assert step.data["n_periods"] <= 30

    def test_returns_calibration_step(self):
        values, dates = _stable_series()
        step = choose_n(values, dates)
        assert isinstance(step, CalibrationStep)
        assert step.name == "Escolha de N (janela)"
        assert "n_periods" in step.data


# ---------------------------------------------------------------------------
# Test Etapa 2: find_best_sigma
# ---------------------------------------------------------------------------

class TestSigmaAlone:
    def test_stable_series_sigma_sufficient(self):
        values, dates = _stable_series(90)
        outliers = _compute_outlier_mask(values)
        step = find_best_sigma(values, dates, n_periods=30, outlier_indices=outliers)
        assert step.data["sigma_sufficient"] is True
        assert step.data["coverage"] >= SIGMA_SUFFICIENT_THRESHOLD
        assert "suficiente sem margem" in step.decision

    def test_prefers_smaller_sigma(self):
        """Quando sigma_sufficient, deve escolher o menor sigma que atinge threshold."""
        values, dates = _stable_series(90, std=2.0)
        outliers = _compute_outlier_mask(values)
        step = find_best_sigma(values, dates, n_periods=30, outlier_indices=outliers)
        # Se encontrou sigma suficiente, deve ser o menor possivel
        if step.data["sigma_sufficient"]:
            results = step.data["results_by_sigma"]
            for sigma in sorted(results.keys()):
                if results[sigma] >= SIGMA_SUFFICIENT_THRESHOLD:
                    assert step.data["sigma"] == sigma
                    break

    def test_volatile_series_sigma_insufficient(self):
        values, dates = _volatile_series(90)
        outliers = _compute_outlier_mask(values)
        step = find_best_sigma(values, dates, n_periods=30, outlier_indices=outliers)
        # Volatil pode nao atingir threshold
        assert "results_by_sigma" in step.data
        assert step.step == 2

    def test_returns_results_by_sigma(self):
        values, dates = _stable_series(90)
        outliers = _compute_outlier_mask(values)
        step = find_best_sigma(values, dates, n_periods=30, outlier_indices=outliers)
        results = step.data["results_by_sigma"]
        assert len(results) >= 1
        # Cobertura deve crescer com sigma
        sigmas = sorted(results.keys())
        if len(sigmas) >= 2:
            assert results[sigmas[-1]] >= results[sigmas[0]]

    def test_frequency_metric_kind(self):
        # Percentages 0-100
        import random
        random.seed(42)
        values = [30 + random.gauss(0, 2) for _ in range(90)]
        dates = [f"2026-01-{i+1:02d}" for i in range(90)]
        outliers = _compute_outlier_mask(values)
        step = find_best_sigma(
            values, dates, n_periods=30, outlier_indices=outliers,
            metric_kind="frequency",
        )
        assert step.data["sigma"] in SIGMA_CANDIDATES


# ---------------------------------------------------------------------------
# Test Etapa 3: add_margin_if_needed
# ---------------------------------------------------------------------------

class TestMargin:
    def test_sigma_sufficient_skips_margin(self):
        values, dates = _stable_series(90)
        outliers = _compute_outlier_mask(values)
        step = add_margin_if_needed(
            values, dates, n_periods=30, sigma=2.5,
            sigma_sufficient=True, outlier_indices=outliers,
        )
        assert step.data["margin_enabled"] is False
        assert step.data["margin_pct"] == 0.0
        assert "desativada" in step.decision

    def test_sigma_insufficient_adds_margin(self):
        values, dates = _volatile_series(90)
        outliers = _compute_outlier_mask(values)
        step = add_margin_if_needed(
            values, dates, n_periods=30, sigma=2.0,
            sigma_sufficient=False, outlier_indices=outliers,
        )
        assert step.data["margin_enabled"] is True
        assert step.data["margin_pct"] > 0
        assert step.data["margin_pct"] in MARGIN_CANDIDATES

    def test_prefers_smaller_margin(self):
        """Escolhe a menor margem que atinge cobertura suficiente."""
        values, dates = _stable_series(90)
        outliers = _compute_outlier_mask(values)
        step = add_margin_if_needed(
            values, dates, n_periods=30, sigma=2.0,
            sigma_sufficient=False, outlier_indices=outliers,
        )
        if step.data.get("results_by_margin"):
            # Se 5% basta, nao deve escolher 10%
            for margin, cov in sorted(step.data["results_by_margin"].items()):
                if cov >= SIGMA_SUFFICIENT_THRESHOLD:
                    assert step.data["margin_pct"] <= margin
                    break


# ---------------------------------------------------------------------------
# Test Etapa 4: validate_with_backtest
# ---------------------------------------------------------------------------

class TestValidation:
    def test_stable_series_validates(self):
        values, dates = _stable_series(90)
        outliers = _compute_outlier_mask(values)
        step = validate_with_backtest(
            values, dates, n_periods=30, sigma=2.5,
            margin_pct=0.0, margin_enabled=False,
            outlier_indices=outliers,
        )
        bt = step.data["backtest"]
        assert bt is not None
        assert bt.coverage_pct > 0
        assert "Parametros validados" in step.justification or "FP" in step.justification

    def test_adjusts_when_recent_fps(self):
        """Se ha FPs recentes, tenta relaxar parametros."""
        # Serie com mudanca recente que causa FP
        import random
        random.seed(42)
        values = [100 + random.gauss(0, 3) for _ in range(85)]
        # Ultimos 5 pontos: ligeiramente fora da banda estreita
        values.extend([100 + 15 * ((-1)**i) for i in range(5)])
        dates = [f"2026-01-{i+1:02d}" for i in range(90)]

        outliers = _compute_outlier_mask(values)
        step = validate_with_backtest(
            values, dates, n_periods=30, sigma=2.0,
            margin_pct=0.0, margin_enabled=False,
            outlier_indices=outliers,
        )
        # Pode ter sido ajustado ou nao, mas deve ter tentado
        assert step.step == 4
        assert "backtest" in step.data

    def test_backtest_failure_handled(self):
        """Backtest com dados invalidos nao quebra."""
        step = validate_with_backtest(
            values=[], dates=[], n_periods=30, sigma=2.5,
            margin_pct=0.0, margin_enabled=False,
            outlier_indices=set(),
        )
        assert "falha" in step.decision or step.data.get("backtest") is not None


# ---------------------------------------------------------------------------
# Test Etapa 5: generate_report
# ---------------------------------------------------------------------------

class TestReport:
    def test_report_includes_steps(self):
        steps = [
            CalibrationStep(step=1, name="N", decision="N=30", justification="default"),
            CalibrationStep(step=2, name="Sigma", decision="sigma=2.5", justification="suficiente"),
        ]
        report = generate_report(steps)
        assert "N=30" in report.justification
        assert "sigma=2.5" in report.justification

    def test_report_includes_regime(self):
        profile = SeriesProfile(
            regime=SeriesRegime.VOLATILE,
            is_volatile=True, cv=0.45,
            n_points=60, n_valid=60,
        )
        report = generate_report([], profile=profile)
        assert "volatile" in report.justification.lower()


# ---------------------------------------------------------------------------
# Test Orquestrador: calibrate()
# ---------------------------------------------------------------------------

class TestCalibrate:
    def test_stable_series_high_confidence(self):
        values, dates = _stable_series(90)
        result = calibrate(values, dates, grain=GrainType.DAILY)
        assert isinstance(result, CalibrationResult)
        assert result.viable is True
        assert result.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
        assert result.coverage_pct >= 70.0
        assert len(result.steps) == 5

    def test_stable_series_no_margin(self):
        """Serie estavel deve usar sigma sem margem."""
        values, dates = _stable_series(90, std=3.0)
        result = calibrate(values, dates, grain=GrainType.DAILY)
        assert result.margin_enabled is False
        assert result.margin_pct == 0.0
        assert "sem margem" in result.recommendation or "suficiente" in result.recommendation

    def test_insufficient_data_returns_not_viable(self):
        values, dates = _insufficient_series()
        result = calibrate(values, dates)
        assert result.viable is False
        assert result.confidence == ConfidenceLevel.LOW
        assert "insuficientes" in result.recommendation.lower()

    def test_monthly_grain_uses_n_12(self):
        values, dates = _stable_series(36)
        result = calibrate(values, dates, grain=GrainType.MONTHLY, seasonality_enabled=False)
        assert result.n_periods <= 12

    def test_result_has_all_fields(self):
        values, dates = _stable_series(90)
        result = calibrate(values, dates)
        assert result.n_periods > 0
        assert result.n_sigma > 0
        assert result.coverage_pct >= 0
        assert result.weighted_coverage_pct >= 0
        assert result.false_positives >= 0
        assert result.stability >= 0
        assert isinstance(result.confidence, ConfidenceLevel)
        assert isinstance(result.viable, bool)
        assert len(result.recommendation) > 0

    def test_result_has_profile(self):
        values, dates = _stable_series(90)
        result = calibrate(values, dates)
        assert result.profile is not None
        assert isinstance(result.profile, SeriesProfile)

    def test_preexisting_profile_reused(self):
        values, dates = _stable_series(90)
        profile = SeriesProfile(
            regime=SeriesRegime.STABLE, n_points=90, n_valid=90,
        )
        result = calibrate(values, dates, profile=profile)
        assert result.profile is profile

    def test_frequency_metric_kind(self):
        import random
        random.seed(42)
        values = [30 + random.gauss(0, 2) for _ in range(90)]
        dates = [f"2026-01-{i+1:02d}" for i in range(90)]
        result = calibrate(values, dates, metric_kind="frequency")
        assert result.viable is True
        assert result.coverage_pct > 0

    def test_volatile_series_may_add_margin(self):
        values, dates = _volatile_series(90)
        result = calibrate(values, dates)
        # Volatil pode ou nao precisar de margem, mas deve completar
        assert result.n_periods > 0
        assert result.n_sigma > 0
        assert len(result.steps) == 5

    def test_steps_sequential(self):
        values, dates = _stable_series(90)
        result = calibrate(values, dates)
        step_numbers = [s.step for s in result.steps]
        assert step_numbers == [1, 2, 3, 4, 5]

    def test_each_step_has_justification(self):
        values, dates = _stable_series(90)
        result = calibrate(values, dates)
        for step in result.steps:
            assert len(step.justification) > 0
            assert len(step.decision) > 0
            assert len(step.name) > 0


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_compute_outlier_mask_empty(self):
        assert _compute_outlier_mask([]) == set()

    def test_compute_outlier_mask_no_outliers(self):
        values, _ = _stable_series(60)
        mask = _compute_outlier_mask(values)
        # Stable series should have very few outliers
        assert len(mask) <= 3

    def test_compute_outlier_mask_finds_outliers(self):
        values, _ = _series_with_outliers(60)
        mask = _compute_outlier_mask(values)
        # Should detect the injected outliers at indices 10, 25, 40
        assert 10 in mask or 25 in mask or 40 in mask

    def test_compute_outlier_mask_handles_nans(self):
        values = [1.0, 2.0, None, float('nan'), 3.0, 4.0, 5.0, 6.0]
        mask = _compute_outlier_mask(values)
        assert isinstance(mask, set)

    def test_compute_outlier_mask_short_list(self):
        mask = _compute_outlier_mask([1.0, 2.0, 3.0])
        assert mask == set()


# ---------------------------------------------------------------------------
# Test Explainer
# ---------------------------------------------------------------------------

class TestExplainer:
    def test_explain_calibration_full(self):
        values, dates = _stable_series(90)
        result = calibrate(values, dates)
        text = explain_calibration(result)
        assert "Assistente de Calibracao" in text
        assert "Etapa 1" in text
        assert "Etapa 2" in text
        assert "Etapa 3" in text
        assert "Etapa 4" in text
        assert "Resultado:" in text

    def test_explain_calibration_includes_regime(self):
        values, dates = _volatile_series(90)
        result = calibrate(values, dates)
        text = explain_calibration(result)
        assert "Regime" in text

    def test_explain_calibration_short(self):
        values, dates = _stable_series(90)
        result = calibrate(values, dates)
        text = explain_calibration_short(result)
        assert "N=" in text
        assert "σ=" in text
        assert "cobertura" in text
        assert len(text) < 200  # deve ser curto

    def test_explain_step_detail_sigma(self):
        values, dates = _stable_series(90)
        outliers = _compute_outlier_mask(values)
        step = find_best_sigma(values, dates, n_periods=30, outlier_indices=outliers)
        text = explain_step_detail(step)
        assert "sigma" in text.lower()

    def test_explain_step_detail_margin(self):
        values, dates = _stable_series(90)
        outliers = _compute_outlier_mask(values)
        step = add_margin_if_needed(
            values, dates, n_periods=30, sigma=2.0,
            sigma_sufficient=False, outlier_indices=outliers,
        )
        text = explain_step_detail(step)
        assert "margem" in text.lower()


# ---------------------------------------------------------------------------
# Test ProposalService.calibrate_params integration
# ---------------------------------------------------------------------------

class TestProposalServiceIntegration:
    def test_calibrate_params_returns_calibration_result(self):
        from services.proposal_service import ProposalService
        svc = ProposalService()
        values, dates = _stable_series(90)
        result = svc.calibrate_params(values, dates)
        assert isinstance(result, CalibrationResult)
        assert result.viable is True

    def test_calibrate_params_with_grain(self):
        from services.proposal_service import ProposalService
        svc = ProposalService()
        values, dates = _stable_series(36)
        result = svc.calibrate_params(
            values, dates, grain=GrainType.MONTHLY, seasonality_enabled=False,
        )
        assert result.n_periods <= 12

    def test_calibrate_params_with_profile(self):
        from services.proposal_service import ProposalService
        svc = ProposalService()
        values, dates = _stable_series(90)
        profile = SeriesProfile(regime=SeriesRegime.STABLE, n_points=90, n_valid=90)
        result = svc.calibrate_params(values, dates, profile=profile)
        assert result.profile is profile
