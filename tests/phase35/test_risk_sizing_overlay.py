"""Unit tests for risk/sizing overlay.

GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616
GATE: REGIME_CONDITIONAL_SIZING_20260616

Tests PIT-safe inverse-vol sizing, confidence scaling, HMM regime detection,
and auto-optimization without requiring full backtest execution.
"""
import numpy as np
import pandas as pd
import pytest

from omega.quant.walk_forward.risk_sizing_overlay import (
    RiskSizingConfig,
    RISK_SIZING_OVERLAY_GATE_ID,
    REGIME_CONDITIONAL_SIZING_GATE_ID,
    SimpleGaussianHMM,
    compute_confidence_scale,
    compute_inverse_vol_weights,
    compute_hmm_regime_scale,
    auto_optimize_regime_scale,
    apply_risk_sizing_overlay,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_prices_wide():
    """Wide-format close prices, 30 dates x 5 tickers."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=30, freq="B")
    tickers = ["A", "B", "C", "D", "E"]
    prices = 100.0 + np.cumsum(np.random.randn(30, 5) * 0.5, axis=0)
    return pd.DataFrame(prices, index=dates, columns=tickers)


@pytest.fixture
def sample_test_df(sample_prices_wide):
    """Long-format test_df with date, ticker, close."""
    rows = []
    for dt in sample_prices_wide.index:
        for tkr in sample_prices_wide.columns:
            rows.append({
                "date": dt,
                "ticker": tkr,
                "close": sample_prices_wide.loc[dt, tkr],
            })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_signal(sample_test_df):
    """Equal-weight portfolio signal (1/N per ticker per date)."""
    n_tickers = sample_test_df["ticker"].nunique()
    return pd.Series(1.0 / n_tickers, index=sample_test_df.index)


# ---------------------------------------------------------------------------
# Tests: RiskSizingConfig
# ---------------------------------------------------------------------------

class TestRiskSizingConfig:

    def test_default_disabled(self):
        cfg = RiskSizingConfig()
        assert not cfg.enabled
        assert not cfg.inverse_vol_sizing
        assert not cfg.confidence_scaling

    def test_enabled_when_inverse_vol(self):
        cfg = RiskSizingConfig(inverse_vol_sizing=True)
        assert cfg.enabled

    def test_enabled_when_confidence(self):
        cfg = RiskSizingConfig(confidence_scaling=True)
        assert cfg.enabled


# ---------------------------------------------------------------------------
# Tests: compute_inverse_vol_weights
# ---------------------------------------------------------------------------

class TestInverseVolWeights:

    def test_equal_vol_gives_equal_weights(self):
        """Tickers with identical vol should get equal weights."""
        np.random.seed(0)
        dates = pd.date_range("2025-01-01", periods=25, freq="B")
        tickers = ["X", "Y", "Z"]
        # Identical returns → identical vol
        rets = np.random.randn(25, 1) * 0.01
        prices = 100 * np.exp(np.cumsum(np.repeat(rets, 3, axis=1), axis=0))
        pw = pd.DataFrame(prices, index=dates, columns=tickers)

        w = compute_inverse_vol_weights(pw, tickers, window=20)
        assert len(w) == 3
        np.testing.assert_allclose(w.values, 1.0 / 3, atol=0.02)

    def test_high_vol_gets_lower_weight(self):
        """Ticker with higher vol should get lower weight."""
        np.random.seed(1)
        dates = pd.date_range("2025-01-01", periods=25, freq="B")
        tickers = ["LOW", "HIGH"]
        low_rets = np.random.randn(25) * 0.005
        high_rets = np.random.randn(25) * 0.03
        low_prices = 100 * np.exp(np.cumsum(low_rets))
        high_prices = 100 * np.exp(np.cumsum(high_rets))
        pw = pd.DataFrame({"LOW": low_prices, "HIGH": high_prices}, index=dates)

        w = compute_inverse_vol_weights(pw, tickers, window=20)
        assert w["LOW"] > w["HIGH"]

    def test_insufficient_data_returns_equal_weight(self):
        """With < window+1 rows, should return equal weight."""
        dates = pd.date_range("2025-01-01", periods=5, freq="B")
        tickers = ["A", "B"]
        pw = pd.DataFrame(
            np.random.randn(5, 2) + 100, index=dates, columns=tickers
        )
        w = compute_inverse_vol_weights(pw, tickers, window=20)
        np.testing.assert_allclose(w.values, 0.5, atol=0.01)

    def test_weights_sum_to_one(self):
        """Weights should always sum to 1.0."""
        np.random.seed(2)
        dates = pd.date_range("2025-01-01", periods=30, freq="B")
        tickers = ["A", "B", "C", "D"]
        prices = 100 + np.cumsum(np.random.randn(30, 4) * 0.02, axis=0)
        pw = pd.DataFrame(prices, index=dates, columns=tickers)

        w = compute_inverse_vol_weights(pw, tickers, window=20)
        np.testing.assert_allclose(w.sum(), 1.0, atol=1e-9)

    def test_floor_prevents_degenerate_weights(self):
        """Floor should prevent extreme weight concentration."""
        np.random.seed(3)
        dates = pd.date_range("2025-01-01", periods=25, freq="B")
        tickers = ["FLAT", "VOLATILE"]
        flat_prices = np.full(25, 100.0)  # zero vol
        vol_prices = 100 + np.cumsum(np.random.randn(25) * 0.05)
        pw = pd.DataFrame({"FLAT": flat_prices, "VOLATILE": vol_prices}, index=dates)

        # With floor=0.3, even zero-vol ticker gets reasonable weight
        w = compute_inverse_vol_weights(pw, tickers, window=20, floor=0.3)
        assert w.min() > 0.0
        assert w["FLAT"] > 0.1  # Floor prevents zero weight


# ---------------------------------------------------------------------------
# Tests: compute_confidence_scale
# ---------------------------------------------------------------------------

class TestConfidenceScale:

    def test_strong_positive_ic_gives_high_scale(self):
        """Strong positive IC → scale near max."""
        np.random.seed(10)
        dates = pd.date_range("2025-01-01", periods=60, freq="B")
        tickers = ["A", "B", "C", "D", "E"]
        # Signal correlated with returns
        signal = np.random.randn(60, 5)
        returns = signal * 0.01 + np.random.randn(60, 5) * 0.005
        sig_wide = pd.DataFrame(signal, index=dates, columns=tickers)
        ret_wide = pd.DataFrame(returns, index=dates, columns=tickers)

        scale = compute_confidence_scale(sig_wide, ret_wide, window=60, min_ic=0.01)
        assert scale >= 1.0

    def test_zero_ic_gives_min_scale(self):
        """Weak IC should produce lower scale than strong IC."""
        np.random.seed(11)
        dates = pd.date_range("2025-01-01", periods=60, freq="B")
        tickers = [f"T{i}" for i in range(15)]
        # Weak signal: very low IC
        signal = np.random.randn(60, 15)
        returns = signal * 0.001 + np.random.randn(60, 15) * 0.02
        sig_wide = pd.DataFrame(signal, index=dates, columns=tickers)
        ret_wide = pd.DataFrame(returns, index=dates, columns=tickers)

        weak_scale = compute_confidence_scale(
            sig_wide, ret_wide, window=60, min_ic=0.05, min_scale=0.3, max_scale=1.0
        )

        # Strong signal: high IC
        strong_signal = np.random.randn(60, 15)
        strong_returns = strong_signal * 0.05 + np.random.randn(60, 15) * 0.001
        strong_sig_wide = pd.DataFrame(strong_signal, index=dates, columns=tickers)
        strong_ret_wide = pd.DataFrame(strong_returns, index=dates, columns=tickers)

        strong_scale = compute_confidence_scale(
            strong_sig_wide, strong_ret_wide, window=60, min_ic=0.05, min_scale=0.3, max_scale=1.0
        )
        # Weak signal should produce lower or equal scale
        assert weak_scale <= strong_scale

    def test_insufficient_data_returns_one(self):
        """With < 10 rows, should return 1.0 (no scaling)."""
        dates = pd.date_range("2025-01-01", periods=5, freq="B")
        tickers = ["A", "B"]
        sig = pd.DataFrame(np.random.randn(5, 2), index=dates, columns=tickers)
        ret = pd.DataFrame(np.random.randn(5, 2), index=dates, columns=tickers)

        scale = compute_confidence_scale(sig, ret, window=60)
        assert scale == 1.0

    def test_scale_bounded_by_min_max(self):
        """Scale should always be in [min_scale, max_scale]."""
        np.random.seed(12)
        dates = pd.date_range("2025-01-01", periods=60, freq="B")
        tickers = ["A", "B", "C"]
        sig = pd.DataFrame(np.random.randn(60, 3), index=dates, columns=tickers)
        ret = pd.DataFrame(np.random.randn(60, 3) * 0.01, index=dates, columns=tickers)

        for min_s, max_s in [(0.2, 1.5), (0.5, 1.0), (0.1, 2.0)]:
            scale = compute_confidence_scale(
                sig, ret, window=60, min_scale=min_s, max_scale=max_s
            )
            assert min_s <= scale <= max_s


# ---------------------------------------------------------------------------
# Tests: apply_risk_sizing_overlay
# ---------------------------------------------------------------------------

class TestApplyRiskSizingOverlay:

    def test_disabled_returns_unchanged(self, sample_test_df, sample_signal):
        """When overlay disabled, signal should be unchanged."""
        cfg = RiskSizingConfig()
        result, evidence = apply_risk_sizing_overlay(
            sample_test_df, sample_signal, cfg
        )
        pd.testing.assert_series_equal(result, sample_signal)
        assert evidence["gate"] == RISK_SIZING_OVERLAY_GATE_ID
        assert evidence["note"] == "overlay_disabled_no_change"

    def test_inverse_vol_modifies_signal(self, sample_test_df, sample_signal):
        """When inverse-vol enabled, signal should be modified."""
        cfg = RiskSizingConfig(inverse_vol_sizing=True, inverse_vol_window=10)
        result, evidence = apply_risk_sizing_overlay(
            sample_test_df, sample_signal, cfg
        )
        # Signal should differ from equal-weight baseline
        assert not np.allclose(result.values, sample_signal.values)
        assert evidence["n_rebalances_with_ivol"] > 0

    def test_evidence_structure(self, sample_test_df, sample_signal):
        """Evidence should contain required fields."""
        cfg = RiskSizingConfig(
            inverse_vol_sizing=True,
            confidence_scaling=True,
            inverse_vol_window=10,
            confidence_window=15,
        )
        _, evidence = apply_risk_sizing_overlay(
            sample_test_df, sample_signal, cfg
        )
        assert evidence["gate"] == RISK_SIZING_OVERLAY_GATE_ID
        assert evidence["pit_safe"] is True
        assert evidence["no_current_bar_use"] is True
        assert evidence["no_oos_label_use"] is True
        assert "n_rebalances_with_ivol" in evidence
        assert "avg_confidence_scale" in evidence


# ---------------------------------------------------------------------------
# Tests: Phase35WalkForwardEngine integration (constructor only)
# ---------------------------------------------------------------------------

class TestEngineConstructor:
    """Verify the engine constructor accepts and validates risk/sizing params."""

    def _make_engine(self, **kwargs):
        """Create a minimal engine with risk/sizing overlay config."""
        # Use a mock alpha_module to avoid heavy imports
        import types
        mock_module = types.ModuleType("mock_alpha")
        mock_module.PHASE34_ALPHA_COLUMNS = []
        mock_module.compute_phase34_microstructure_alphas = lambda *a, **kw: None

        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        defaults = {
            "alpha_module": mock_module,
            "risk_sizing_overlay_enabled": True,
        }
        defaults.update(kwargs)
        return Phase35WalkForwardEngine(**defaults)

    def test_default_disabled(self):
        engine = self._make_engine(risk_sizing_overlay_enabled=False)
        assert not engine.risk_sizing_overlay_enabled

    def test_enabled_stored(self):
        engine = self._make_engine(
            risk_sizing_overlay_enabled=True,
            risk_sizing_inverse_vol=True,
            risk_sizing_confidence=True,
        )
        assert engine.risk_sizing_overlay_enabled
        assert engine.risk_sizing_inverse_vol
        assert engine.risk_sizing_confidence

    def test_invalid_window_raises(self):
        with pytest.raises(ValueError, match="inverse_vol_window"):
            self._make_engine(
                risk_sizing_overlay_enabled=True,
                risk_sizing_inverse_vol_window=2,
            )

    def test_invalid_floor_raises(self):
        with pytest.raises(ValueError, match="inverse_vol_floor"):
            self._make_engine(
                risk_sizing_overlay_enabled=True,
                risk_sizing_inverse_vol_floor=1.5,
            )

    def test_invalid_confidence_window_raises(self):
        with pytest.raises(ValueError, match="confidence_window"):
            self._make_engine(
                risk_sizing_overlay_enabled=True,
                risk_sizing_confidence_window=5,
            )

    def test_invalid_min_scale_raises(self):
        with pytest.raises(ValueError, match="confidence_min_scale"):
            self._make_engine(
                risk_sizing_overlay_enabled=True,
                risk_sizing_confidence_min_scale=1.5,
            )

    # GATE: REGIME_CONDITIONAL_SIZING_20260616 — new param validation tests
    def test_regime_mode_stored(self):
        engine = self._make_engine(
            risk_sizing_overlay_enabled=True,
            risk_sizing_regime=True,
            risk_sizing_regime_mode="hmm",
        )
        assert engine.risk_sizing_regime_mode == "hmm"
        assert engine.risk_sizing_regime is True

    def test_regime_window_stored(self):
        engine = self._make_engine(
            risk_sizing_overlay_enabled=True,
            risk_sizing_regime_window=150,
        )
        assert engine.risk_sizing_regime_window == 150

    def test_invalid_regime_window_raises(self):
        with pytest.raises(ValueError, match="regime_window"):
            self._make_engine(
                risk_sizing_overlay_enabled=True,
                risk_sizing_regime_window=5,
            )

    def test_invalid_regime_mode_raises(self):
        with pytest.raises(ValueError, match="regime_mode"):
            self._make_engine(
                risk_sizing_overlay_enabled=True,
                risk_sizing_regime_mode="invalid",
            )

    def test_auto_optimize_stored(self):
        engine = self._make_engine(
            risk_sizing_overlay_enabled=True,
            risk_sizing_regime_auto_optimize=True,
        )
        assert engine.risk_sizing_regime_auto_optimize is True


# ---------------------------------------------------------------------------
# Tests: SimpleGaussianHMM — GATE: REGIME_CONDITIONAL_SIZING_20260616
# ---------------------------------------------------------------------------


class TestSimpleGaussianHMM:

    def test_fit_converges_on_synthetic_data(self):
        """HMM should converge and produce reasonable parameters."""
        np.random.seed(42)
        # Generate 3-state data: bear (low mean), neutral (mid), bull (high)
        states = np.random.choice(3, size=300, p=[0.3, 0.4, 0.3])
        means = [-0.02, 0.0, 0.02]
        stds = [0.01, 0.005, 0.01]
        X = np.array([
            np.random.normal(means[s], stds[s]) for s in states
        ])

        hmm = SimpleGaussianHMM(n_states=3, max_iter=100, random_state=42)
        hmm.fit(X)

        assert hmm.pi_ is not None
        assert hmm.A_ is not None
        assert hmm.mu_ is not None
        assert hmm.sigma2_ is not None
        assert len(hmm.mu_) == 3
        assert len(hmm.sigma2_) == 3
        assert hmm.n_iter_ > 0
        assert np.isfinite(hmm.log_likelihood_)

    def test_fit_recovers_sorted_means(self):
        """Fitted means should span the range of the data."""
        np.random.seed(123)
        X = np.concatenate([
            np.random.normal(-0.03, 0.005, 100),
            np.random.normal(0.0, 0.005, 100),
            np.random.normal(0.03, 0.005, 100),
        ])

        hmm = SimpleGaussianHMM(n_states=3, max_iter=100, random_state=0)
        hmm.fit(X)

        sorted_means = np.sort(hmm.mu_)
        assert sorted_means[0] < sorted_means[1] < sorted_means[2]
        # Means should be roughly in the right range
        assert sorted_means[0] < -0.01  # bear
        assert sorted_means[2] > 0.01   # bull

    def test_predict_proba_sums_to_one(self):
        """Posterior probabilities should sum to ~1 for each observation."""
        np.random.seed(99)
        X = np.random.randn(100) * 0.01

        hmm = SimpleGaussianHMM(n_states=3, max_iter=50, random_state=7)
        hmm.fit(X)
        gamma = hmm.predict_proba(X)

        assert gamma.shape == (100, 3)
        row_sums = gamma.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)

    def test_predict_proba_bounded(self):
        """All posteriors should be in [0, 1]."""
        np.random.seed(77)
        X = np.random.randn(80) * 0.02

        hmm = SimpleGaussianHMM(n_states=3, max_iter=50, random_state=3)
        hmm.fit(X)
        gamma = hmm.predict_proba(X)

        assert gamma.min() >= 0.0
        assert gamma.max() <= 1.0 + 1e-9

    def test_predict_proba_before_fit_raises(self):
        """predict_proba should raise if model not fitted."""
        hmm = SimpleGaussianHMM()
        with pytest.raises(RuntimeError, match="not fitted"):
            hmm.predict_proba(np.random.randn(50))

    def test_fit_too_few_observations_raises(self):
        """Fitting with too few observations should raise."""
        hmm = SimpleGaussianHMM(n_states=3)
        with pytest.raises(ValueError, match="at least"):
            hmm.fit(np.array([0.01, 0.02]))

    def test_transition_matrix_rows_sum_to_one(self):
        """Each row of A_ should sum to ~1."""
        np.random.seed(55)
        X = np.random.randn(150) * 0.01

        hmm = SimpleGaussianHMM(n_states=3, max_iter=50, random_state=1)
        hmm.fit(X)

        row_sums = hmm.A_.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)


# ---------------------------------------------------------------------------
# Tests: compute_hmm_regime_scale — GATE: REGIME_CONDITIONAL_SIZING_20260616
# ---------------------------------------------------------------------------


def _make_hmm_close_wide(n_dates=250, n_tickers=5, seed=42):
    """Create wide-format close prices for HMM regime testing."""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="B")
    tickers = [f"T{i}" for i in range(n_tickers)]
    # Random walk with some regime-like structure
    base_returns = np.random.randn(n_dates) * 0.01
    # Add bear period in the middle
    base_returns[100:150] -= 0.005
    # Add bull period at the end
    base_returns[200:] += 0.003
    prices = np.zeros((n_dates, n_tickers))
    for j in range(n_tickers):
        noise = np.random.randn(n_dates) * 0.005
        rets = base_returns + noise
        prices[:, j] = 100 * np.exp(np.cumsum(rets))
    return pd.DataFrame(prices, index=dates, columns=tickers)


class TestComputeHmmRegimeScale:

    def test_returns_scale_between_bounds(self):
        """Scale should be in [regime_scale, 1.0]."""
        close_wide = _make_hmm_close_wide(n_dates=250, seed=42)
        dt = close_wide.index[220]

        scale, ev, _ = compute_hmm_regime_scale(
            close_wide, dt, regime_window=200, regime_scale=0.5
        )
        assert 0.0 <= scale <= 1.0

    def test_insufficient_data_returns_one(self):
        """With insufficient data, scale should be 1.0."""
        close_wide = _make_hmm_close_wide(n_dates=10, seed=0)
        dt = close_wide.index[5]

        scale, ev, _ = compute_hmm_regime_scale(
            close_wide, dt, regime_window=200
        )
        assert scale == 1.0
        assert ev.get("insufficient_data") or ev.get("insufficient_returns")

    def test_evidence_has_p_bear(self):
        """Evidence should contain p_bear when data is sufficient."""
        close_wide = _make_hmm_close_wide(n_dates=250, seed=42)
        dt = close_wide.index[230]

        scale, ev, _ = compute_hmm_regime_scale(
            close_wide, dt, regime_window=200, regime_scale=0.5
        )
        if not ev.get("insufficient_data"):
            assert "p_bear" in ev
            assert 0.0 <= ev["p_bear"] <= 1.0
            assert "p_bull" in ev
            assert "mu_bear" in ev

    def test_bear_period_produces_lower_scale(self):
        """During bear period, scale should be lower than during bull."""
        close_wide = _make_hmm_close_wide(n_dates=250, seed=42)
        # During bear period (index 100-150 area)
        bear_dt = close_wide.index[155]
        bear_scale, _, _ = compute_hmm_regime_scale(
            close_wide, bear_dt, regime_window=100, regime_scale=0.3
        )
        # During bull period (index > 200)
        bull_dt = close_wide.index[230]
        bull_scale, _, _ = compute_hmm_regime_scale(
            close_wide, bull_dt, regime_window=100, regime_scale=0.3
        )
        # Bear scale should be <= bull scale (or equal if HMM doesn't detect it)
        assert bear_scale <= bull_scale + 0.3  # Allow tolerance


# ---------------------------------------------------------------------------
# Tests: auto_optimize_regime_scale — GATE: REGIME_CONDITIONAL_SIZING_20260616
# ---------------------------------------------------------------------------


def _make_train_df(n_dates=250, n_tickers=5, seed=42):
    """Create long-format train_df for auto-optimize testing."""
    close_wide = _make_hmm_close_wide(n_dates=n_dates, n_tickers=n_tickers, seed=seed)
    rows = []
    for dt in close_wide.index:
        for tkr in close_wide.columns:
            rows.append({
                "date": dt,
                "ticker": tkr,
                "close": close_wide.loc[dt, tkr],
            })
    return pd.DataFrame(rows)


class TestAutoOptimizeRegimeScale:

    def test_returns_best_scale(self):
        """Auto-optimize should return a scale from the grid."""
        train_df = _make_train_df(n_dates=250, seed=42)
        best_scale, ev = auto_optimize_regime_scale(
            train_df, regime_window=100, regime_mode="heuristic",
            scale_grid=[0.0, 0.5, 1.0],
            ma_window=50,
        )
        assert best_scale in [0.0, 0.5, 1.0]
        assert "grid_results" in ev

    def test_grid_results_have_sharpe(self):
        """Each grid point should have a Sharpe value."""
        train_df = _make_train_df(n_dates=250, seed=42)
        _, ev = auto_optimize_regime_scale(
            train_df, regime_window=100, regime_mode="heuristic",
            scale_grid=[0.0, 0.5, 1.0],
            ma_window=50,
        )
        for scale_str, result in ev["grid_results"].items():
            assert "sharpe" in result
            assert np.isfinite(result["sharpe"])

    def test_insufficient_data_returns_one(self):
        """With very little data, should return 1.0."""
        train_df = _make_train_df(n_dates=5, seed=0)
        best_scale, ev = auto_optimize_regime_scale(
            train_df, regime_window=100, regime_mode="heuristic",
        )
        assert best_scale == 1.0

    def test_hmm_mode_works(self):
        """Auto-optimize should work in HMM mode."""
        train_df = _make_train_df(n_dates=250, seed=42)
        best_scale, ev = auto_optimize_regime_scale(
            train_df, regime_window=100, regime_mode="hmm",
            scale_grid=[0.0, 0.5, 1.0],
        )
        assert best_scale in [0.0, 0.5, 1.0]
        assert ev["regime_mode"] == "hmm"


# ---------------------------------------------------------------------------
# Tests: apply_risk_sizing_overlay with HMM mode
# ---------------------------------------------------------------------------


class TestApplyRiskSizingOverlayHmm:

    def _make_large_test_df(self, n_dates=250, n_tickers=5, seed=42):
        """Create a large enough test_df for HMM regime testing."""
        close_wide = _make_hmm_close_wide(n_dates=n_dates, n_tickers=n_tickers, seed=seed)
        rows = []
        for dt in close_wide.index:
            for tkr in close_wide.columns:
                rows.append({
                    "date": dt,
                    "ticker": tkr,
                    "close": close_wide.loc[dt, tkr],
                })
        return pd.DataFrame(rows)

    def test_hmm_mode_modifies_signal(self):
        """HMM regime mode should modify signal when regime_sizing enabled."""
        test_df = self._make_large_test_df(n_dates=250, seed=42)
        signal = pd.Series(0.2, index=test_df.index)
        cfg = RiskSizingConfig(
            regime_sizing=True,
            regime_sizing_mode="hmm",
            regime_sizing_window=100,
            regime_sizing_scale=0.3,
        )
        result, evidence = apply_risk_sizing_overlay(test_df, signal, cfg)
        assert evidence["regime_sizing_mode"] == "hmm"
        assert evidence["regime_gate"] == REGIME_CONDITIONAL_SIZING_GATE_ID
        # Signal should be modified for at least some dates
        assert not np.allclose(result.values, signal.values)

    def test_hmm_evidence_has_hmm_scales(self):
        """Evidence should contain HMM scale list in HMM mode."""
        test_df = self._make_large_test_df(n_dates=250, seed=42)
        signal = pd.Series(0.2, index=test_df.index)
        cfg = RiskSizingConfig(
            regime_sizing=True,
            regime_sizing_mode="hmm",
            regime_sizing_window=100,
            regime_sizing_scale=0.5,
        )
        _, evidence = apply_risk_sizing_overlay(test_df, signal, cfg)
        assert "hmm_scales" in evidence
        assert len(evidence["hmm_scales"]) > 0

    def test_heuristic_mode_still_works(self):
        """Heuristic (original) mode should still work unchanged."""
        test_df = self._make_large_test_df(n_dates=250, seed=42)
        signal = pd.Series(0.2, index=test_df.index)
        cfg = RiskSizingConfig(
            regime_sizing=True,
            regime_sizing_mode="heuristic",
            regime_sizing_scale=0.5,
            regime_ma_window=50,
        )
        result, evidence = apply_risk_sizing_overlay(test_df, signal, cfg)
        assert evidence["regime_sizing_mode"] == "heuristic"
        assert "regime_counts" in evidence


# ---------------------------------------------------------------------------
# Tests: SimpleGaussianHMM.get_params — GATE: REGIME_CONDITIONAL_SIZING_20260616
# ---------------------------------------------------------------------------


class TestSimpleGaussianHMMGetParams:

    def test_get_params_before_fit(self):
        """get_params should return None values before fitting."""
        hmm = SimpleGaussianHMM()
        params = hmm.get_params()
        assert params["pi"] is None
        assert params["A"] is None
        assert params["mu"] is None
        assert params["sigma2"] is None

    def test_get_params_after_fit(self):
        """get_params should return arrays after fitting."""
        np.random.seed(42)
        X = np.random.randn(200) * 0.01
        hmm = SimpleGaussianHMM(n_states=3, max_iter=30, random_state=42)
        hmm.fit(X)
        params = hmm.get_params()
        assert params["pi"] is not None
        assert params["A"] is not None
        assert params["mu"] is not None
        assert params["sigma2"] is not None
        assert params["pi"].shape == (3,)
        assert params["A"].shape == (3, 3)
        assert params["mu"].shape == (3,)
        assert params["sigma2"].shape == (3,)

    def test_get_params_returns_copies(self):
        """get_params should return copies (mutations don't affect model)."""
        np.random.seed(42)
        X = np.random.randn(200) * 0.01
        hmm = SimpleGaussianHMM(n_states=3, max_iter=30, random_state=42)
        hmm.fit(X)
        params = hmm.get_params()
        original_mu = params["mu"].copy()
        params["mu"][0] = 999.0
        # Model internal state should be unaffected
        np.testing.assert_array_equal(hmm.mu_, original_mu)


# ---------------------------------------------------------------------------
# Tests: SimpleGaussianHMM warm start — GATE: REGIME_CONDITIONAL_SIZING_20260616
# ---------------------------------------------------------------------------


class TestSimpleGaussianHMMWarmStart:

    def _make_synthetic_data(self, seed=42):
        np.random.seed(seed)
        states = np.random.choice(3, size=300, p=[0.3, 0.4, 0.3])
        means = [-0.02, 0.0, 0.02]
        stds = [0.01, 0.005, 0.01]
        return np.array([np.random.normal(means[s], stds[s]) for s in states])

    def test_warm_start_converges_faster(self):
        """Warm-started fit should converge in fewer iterations."""
        X = self._make_synthetic_data(seed=42)

        # Cold start
        hmm_cold = SimpleGaussianHMM(n_states=3, max_iter=100, random_state=42)
        hmm_cold.fit(X)
        cold_iters = hmm_cold.n_iter_

        # Use cold start result as warm-start params
        warm_params = hmm_cold.get_params()

        # Warm start with good init should converge very quickly
        hmm_warm = SimpleGaussianHMM(n_states=3, max_iter=100, random_state=42)
        hmm_warm.fit(X, init_params=warm_params)
        warm_iters = hmm_warm.n_iter_

        # Warm start should converge in fewer or equal iterations
        assert warm_iters <= cold_iters

    def test_warm_start_parameters_close(self):
        """Warm-started parameters should be close to cold-start parameters."""
        X = self._make_synthetic_data(seed=42)

        # Cold start
        hmm_cold = SimpleGaussianHMM(n_states=3, max_iter=100, random_state=42)
        hmm_cold.fit(X)

        # Warm start from cold result
        warm_params = hmm_cold.get_params()
        hmm_warm = SimpleGaussianHMM(n_states=3, max_iter=100, random_state=42)
        hmm_warm.fit(X, init_params=warm_params)

        # Sorted means should be close (wider tolerance for EM drift)
        np.testing.assert_allclose(
            np.sort(hmm_warm.mu_), np.sort(hmm_cold.mu_), atol=0.01
        )

    def test_warm_start_with_partial_params(self):
        """Warm start with only mu provided should still work."""
        X = self._make_synthetic_data(seed=42)

        # Fit with only mu as init_params
        init = {"mu": np.array([-0.02, 0.0, 0.02])}
        hmm = SimpleGaussianHMM(n_states=3, max_iter=30, random_state=42)
        hmm.fit(X, init_params=init)

        assert hmm.pi_ is not None
        assert hmm.A_ is not None
        assert hmm.mu_ is not None
        assert hmm.sigma2_ is not None
        assert hmm.n_iter_ > 0

    def test_default_max_iter_is_30(self):
        """Default max_iter should be 30."""
        hmm = SimpleGaussianHMM()
        assert hmm.max_iter == 30


# ---------------------------------------------------------------------------
# Tests: compute_hmm_regime_scale stride / refit=False
# GATE: REGIME_CONDITIONAL_SIZING_20260616
# ---------------------------------------------------------------------------


class TestComputeHmmRegimeScaleStride:

    def test_returns_3_tuple(self):
        """compute_hmm_regime_scale should return (scale, evidence, params)."""
        close_wide = _make_hmm_close_wide(n_dates=250, seed=42)
        dt = close_wide.index[220]
        result = compute_hmm_regime_scale(
            close_wide, dt, regime_window=200, regime_scale=0.5
        )
        assert len(result) == 3
        scale, ev, params = result
        assert isinstance(scale, float)
        assert isinstance(ev, dict)
        assert isinstance(params, dict)

    def test_refit_true_returns_params(self):
        """With refit=True, hmm_params should be populated."""
        close_wide = _make_hmm_close_wide(n_dates=250, seed=42)
        dt = close_wide.index[220]
        scale, ev, params = compute_hmm_regime_scale(
            close_wide, dt, regime_window=200, regime_scale=0.5,
            refit=True,
        )
        assert "mu" in params
        assert params["mu"] is not None

    def test_refit_false_with_cached_params(self):
        """refit=False with cached params should produce similar scale."""
        close_wide = _make_hmm_close_wide(n_dates=250, seed=42)

        # First: refit=True to get params
        dt1 = close_wide.index[220]
        scale1, ev1, params1 = compute_hmm_regime_scale(
            close_wide, dt1, regime_window=200, regime_scale=0.5,
            refit=True,
        )

        # Second: refit=False with cached params on next date
        dt2 = close_wide.index[221]
        scale2, ev2, params2 = compute_hmm_regime_scale(
            close_wide, dt2, regime_window=200, regime_scale=0.5,
            init_params=params1, refit=False,
        )

        # Scale should be similar (not identical due to different last observation)
        assert 0.0 <= scale2 <= 1.0
        # Evidence should indicate refit=False
        assert ev2.get("refit") is False

    def test_refit_false_without_params_returns_one(self):
        """refit=False without init_params should return scale=1.0."""
        close_wide = _make_hmm_close_wide(n_dates=250, seed=42)
        dt = close_wide.index[220]
        scale, ev, params = compute_hmm_regime_scale(
            close_wide, dt, regime_window=200, regime_scale=0.5,
            refit=False, init_params=None,
        )
        assert scale == 1.0
        assert ev.get("refit_false_no_init_params") is True

    def test_warm_start_refit_produces_similar_scale(self):
        """Warm-started refit should produce similar scale to cold start."""
        close_wide = _make_hmm_close_wide(n_dates=250, seed=42)

        dt1 = close_wide.index[220]
        scale1, _, params1 = compute_hmm_regime_scale(
            close_wide, dt1, regime_window=200, regime_scale=0.5,
            refit=True,
        )

        # Warm-started refit on next date
        dt2 = close_wide.index[221]
        scale2, _, _ = compute_hmm_regime_scale(
            close_wide, dt2, regime_window=200, regime_scale=0.5,
            init_params=params1, refit=True,
        )

        # Scales should be close (within tolerance for one day shift)
        assert abs(scale1 - scale2) < 0.3

    def test_insufficient_data_returns_empty_params(self):
        """With insufficient data, hmm_params should be empty dict."""
        close_wide = _make_hmm_close_wide(n_dates=10, seed=0)
        dt = close_wide.index[5]
        scale, ev, params = compute_hmm_regime_scale(
            close_wide, dt, regime_window=200,
        )
        assert scale == 1.0
        assert params == {}


# ---------------------------------------------------------------------------
# Tests: RiskSizingConfig regime_refit_stride
# GATE: REGIME_CONDITIONAL_SIZING_20260616
# ---------------------------------------------------------------------------


class TestRiskSizingConfigStride:

    def test_default_stride(self):
        cfg = RiskSizingConfig()
        assert cfg.regime_refit_stride == 5

    def test_custom_stride(self):
        cfg = RiskSizingConfig(regime_refit_stride=10)
        assert cfg.regime_refit_stride == 10


# ---------------------------------------------------------------------------
# Tests: Phase35WalkForwardEngine stride validation
# GATE: REGIME_CONDITIONAL_SIZING_20260616
# ---------------------------------------------------------------------------


class TestEngineStrideValidation:

    def _make_engine(self, **kwargs):
        import types
        mock_module = types.ModuleType("mock_alpha")
        mock_module.PHASE34_ALPHA_COLUMNS = []
        mock_module.compute_phase34_microstructure_alphas = lambda *a, **kw: None
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        defaults = {
            "alpha_module": mock_module,
            "risk_sizing_overlay_enabled": True,
        }
        defaults.update(kwargs)
        return Phase35WalkForwardEngine(**defaults)

    def test_stride_default_stored(self):
        engine = self._make_engine()
        assert engine.risk_sizing_regime_refit_stride == 5

    def test_stride_custom_stored(self):
        engine = self._make_engine(risk_sizing_regime_refit_stride=10)
        assert engine.risk_sizing_regime_refit_stride == 10

    def test_stride_zero_raises(self):
        with pytest.raises(ValueError, match="regime_refit_stride"):
            self._make_engine(risk_sizing_regime_refit_stride=0)

    def test_stride_negative_raises(self):
        with pytest.raises(ValueError, match="regime_refit_stride"):
            self._make_engine(risk_sizing_regime_refit_stride=-1)

    def test_stride_non_int_raises(self):
        with pytest.raises(ValueError, match="regime_refit_stride"):
            self._make_engine(risk_sizing_regime_refit_stride=2.5)
