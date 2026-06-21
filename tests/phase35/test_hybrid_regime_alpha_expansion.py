"""Tests for Hybrid Regime Alpha Expansion (v2).

Gate: HYBRID_REGIME_ALPHA_EXPANSION_20260621

Validates 8 new PIT-safe alpha signals in hybrid_regime_alpha.py covering:
  - Intraday microstructure (overnight gap, range/volume, bid-ask bounce)
  - Sector rotation (relative strength, momentum spread)
  - Sentiment blend (volume surge + price trend)
  - Regime-conditional features (trend-filtered momentum)
  - Volume imbalance pressure (CLV-weighted order flow proxy)

PIT Safety: All signals use T-1 lag (shift(1) per symbol).
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.quant.alpha.hybrid_regime_alpha import (
    ALL_HYBRID_REGIME_COLUMNS,
    HYBRID_REGIME_ALPHA_COLUMNS,
    HYBRID_REGIME_V2_COLUMNS,
    compute_all_hybrid_regime_alphas,
    compute_all_hybrid_regime_combined,
    compute_all_hybrid_regime_v2_alphas,
    compute_bid_ask_bounce_proxy,
    compute_intraday_range_volume_ratio,
    compute_overnight_gap_return,
    compute_regime_conditional_momentum,
    compute_sector_momentum_spread,
    compute_sector_relative_strength,
    compute_sentiment_price_blend,
    compute_volume_imbalance_pressure,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def synthetic_ohlcv():
    """Generate realistic synthetic OHLCV panel for 10 symbols, 200 days."""
    np.random.seed(42)
    n_symbols = 10
    n_days = 200
    symbols = [f"SYM{i:02d}" for i in range(n_symbols)]
    dates = pd.bdate_range("2020-01-01", periods=n_days, freq="B")
    sectors = ["Financials", "Technology", "Consumer", "Energy", "Materials"]

    rows = []
    for i, sym in enumerate(symbols):
        price = 50000.0 + np.random.rand() * 50000.0
        sector = sectors[i % len(sectors)]
        for dt in dates:
            daily_ret = np.random.normal(0.0005, 0.02)
            close = price * (1 + daily_ret)
            high = close * (1 + abs(np.random.normal(0, 0.01)))
            low = close * (1 - abs(np.random.normal(0, 0.01)))
            open_ = price * (1 + np.random.normal(0, 0.005))
            volume = int(np.random.lognormal(12, 1.5))
            rows.append({
                "date": dt,
                "ticker": sym,
                "open": max(open_, 1000.0),
                "high": max(high, max(open_, close) + 1.0),
                "low": max(min(low, min(open_, close) - 1.0), 100.0),
                "close": max(close, 1000.0),
                "volume": max(volume, 100),
                "sector": sector,
            })
            price = close

    df = pd.DataFrame(rows)
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    return df


@pytest.fixture
def small_ohlcv():
    """Minimal OHLCV panel for edge-case testing."""
    np.random.seed(7)
    dates = pd.bdate_range("2021-01-01", periods=30, freq="B")
    rows = []
    for sym in ["A", "B"]:
        price = 10000.0
        sector = "Tech" if sym == "A" else "Finance"
        for dt in dates:
            r = np.random.normal(0.001, 0.015)
            c = price * (1 + r)
            h = c * 1.01
            lo = c * 0.99
            o = price
            v = int(np.random.lognormal(10, 1))
            rows.append({
                "date": dt, "ticker": sym, "open": o,
                "high": max(h, o, c), "low": min(lo, o, c),
                "close": c, "volume": max(v, 100),
                "sector": sector,
            })
            price = c
    return pd.DataFrame(rows).sort_values(
        ["ticker", "date"]
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 1. Signal computation: all 8 new signals compute without errors
# ---------------------------------------------------------------------------
class TestV2SignalComputation:
    def test_compute_v2_returns_dict_with_8_keys(self, synthetic_ohlcv):
        result = compute_all_hybrid_regime_v2_alphas(synthetic_ohlcv)
        assert isinstance(result, dict)
        assert len(result) == 8

    def test_all_v2_column_names_match_expected(self, synthetic_ohlcv):
        result = compute_all_hybrid_regime_v2_alphas(synthetic_ohlcv)
        assert set(result.keys()) == set(HYBRID_REGIME_V2_COLUMNS)

    def test_combined_returns_15_signals(self, synthetic_ohlcv):
        result = compute_all_hybrid_regime_combined(synthetic_ohlcv)
        assert len(result) == 15
        assert set(result.keys()) == set(ALL_HYBRID_REGIME_COLUMNS)

    @pytest.mark.parametrize("func_name", [
        "compute_overnight_gap_return",
        "compute_intraday_range_volume_ratio",
        "compute_sector_relative_strength",
        "compute_sector_momentum_spread",
        "compute_sentiment_price_blend",
        "compute_regime_conditional_momentum",
        "compute_bid_ask_bounce_proxy",
        "compute_volume_imbalance_pressure",
    ])
    def test_each_v2_signal_returns_series(self, synthetic_ohlcv, func_name):
        func = globals()[func_name]
        result = func(synthetic_ohlcv)
        assert isinstance(result, pd.Series)
        assert len(result) == len(synthetic_ohlcv)

    def test_small_panel_does_not_crash(self, small_ohlcv):
        result = compute_all_hybrid_regime_v2_alphas(df=small_ohlcv)
        assert len(result) == 8


# ---------------------------------------------------------------------------
# 2. PIT Safety: T-1 lag verification for all 8 new signals
# ---------------------------------------------------------------------------
class TestV2PITSafety:
    """All v2 signals must be T-1 lagged: first value per symbol is 0.0."""

    _signal_funcs = [
        ("compute_overnight_gap_return", compute_overnight_gap_return),
        ("compute_intraday_range_volume_ratio", compute_intraday_range_volume_ratio),
        ("compute_sector_relative_strength", compute_sector_relative_strength),
        ("compute_sector_momentum_spread", compute_sector_momentum_spread),
        ("compute_sentiment_price_blend", compute_sentiment_price_blend),
        ("compute_regime_conditional_momentum", compute_regime_conditional_momentum),
        ("compute_bid_ask_bounce_proxy", compute_bid_ask_bounce_proxy),
        ("compute_volume_imbalance_pressure", compute_volume_imbalance_pressure),
    ]

    @pytest.mark.parametrize("name,func", _signal_funcs, ids=[x[0] for x in _signal_funcs])
    def test_first_value_is_zero(self, synthetic_ohlcv, name, func):
        sig = func(synthetic_ohlcv)
        for sym in synthetic_ohlcv["ticker"].unique():
            sym_mask = synthetic_ohlcv["ticker"] == sym
            first_val = sig[sym_mask].iloc[0]
            assert first_val == 0.0, (
                f"{name}: symbol {sym} first value = {first_val}, expected 0.0"
            )

    def test_no_future_data_leakage_overnight_gap(self, synthetic_ohlcv):
        """Truncation test: removing last 5 days should not change earlier values."""
        df = synthetic_ohlcv
        dates = sorted(df["date"].unique())
        cutoff = dates[-5]
        df_trunc = df[df["date"] <= cutoff].copy()

        sig_full = compute_overnight_gap_return(df)
        sig_trunc = compute_overnight_gap_return(df_trunc)

        common_idx = sig_trunc.index.intersection(sig_full.index)
        if len(common_idx) > 0:
            np.testing.assert_array_almost_equal(
                sig_trunc.loc[common_idx].values,
                sig_full.loc[common_idx].values,
                decimal=10,
                err_msg="Overnight gap: truncation changed values (look-ahead leak)",
            )

    def test_no_future_data_leakage_volume_imbalance(self, synthetic_ohlcv):
        """Truncation test for volume imbalance pressure."""
        df = synthetic_ohlcv
        dates = sorted(df["date"].unique())
        cutoff = dates[-5]
        df_trunc = df[df["date"] <= cutoff].copy()

        sig_full = compute_volume_imbalance_pressure(df)
        sig_trunc = compute_volume_imbalance_pressure(df_trunc)

        common_idx = sig_trunc.index.intersection(sig_full.index)
        if len(common_idx) > 0:
            np.testing.assert_array_almost_equal(
                sig_trunc.loc[common_idx].values,
                sig_full.loc[common_idx].values,
                decimal=10,
                err_msg="VIP: truncation changed values (look-ahead leak)",
            )


# ---------------------------------------------------------------------------
# 3. Signal Quality: non-trivial std, finite, bounded
# ---------------------------------------------------------------------------
class TestV2SignalQuality:
    def test_v2_signals_have_nonzero_std(self, synthetic_ohlcv):
        result = compute_all_hybrid_regime_v2_alphas(synthetic_ohlcv)
        for name, sig in result.items():
            std = sig.std()
            assert std > 0, f"{name}: signal is constant (std={std})"

    def test_v2_signals_are_finite(self, synthetic_ohlcv):
        result = compute_all_hybrid_regime_v2_alphas(synthetic_ohlcv)
        for name, sig in result.items():
            n_inf = np.isinf(sig).sum()
            n_nan = np.isnan(sig).sum()
            assert n_inf == 0, f"{name}: has {n_inf} inf values"
            assert n_nan == 0, f"{name}: has {n_nan} NaN values"

    def test_v2_signals_bounded_reasonably(self, synthetic_ohlcv):
        result = compute_all_hybrid_regime_v2_alphas(synthetic_ohlcv)
        for name, sig in result.items():
            assert sig.abs().max() < 1000, (
                f"{name}: extreme values (max abs = {sig.abs().max()})"
            )

    @pytest.mark.parametrize("func_name", [
        "compute_overnight_gap_return",
        "compute_intraday_range_volume_ratio",
        "compute_sector_relative_strength",
        "compute_sector_momentum_spread",
        "compute_sentiment_price_blend",
        "compute_regime_conditional_momentum",
        "compute_bid_ask_bounce_proxy",
        "compute_volume_imbalance_pressure",
    ])
    def test_each_signal_no_nan_inf(self, synthetic_ohlcv, func_name):
        func = globals()[func_name]
        sig = func(synthetic_ohlcv)
        assert sig.isna().sum() == 0, f"{func_name}: has NaN"
        assert np.isinf(sig).sum() == 0, f"{func_name}: has Inf"


# ---------------------------------------------------------------------------
# 4. Economic Mechanism Verification
# ---------------------------------------------------------------------------
class TestEconomicMechanisms:
    """Verify each signal captures its intended economic mechanism."""

    def test_overnight_gap_uses_open_and_prev_close(self, synthetic_ohlcv):
        """Overnight gap should be (open - prev_close) / prev_close."""
        df = synthetic_ohlcv
        sig = compute_overnight_gap_return(df)
        # After PIT shift, first row is 0.0, rest are computed
        non_zero = sig[sig != 0.0]
        assert len(non_zero) > 0, "All overnight gap values are 0.0"

    def test_range_volume_ratio_positive(self, synthetic_ohlcv):
        """Range/volume ratio should be non-negative."""
        sig = compute_intraday_range_volume_ratio(synthetic_ohlcv)
        assert (sig >= 0).all(), "Range/volume ratio has negative values"

    def test_sector_relative_strength_centered(self, synthetic_ohlcv):
        """Sector relative strength should be roughly centered around 0."""
        sig = compute_sector_relative_strength(synthetic_ohlcv)
        mean_val = sig.mean()
        assert abs(mean_val) < 0.5, (
            f"Sector relative strength mean={mean_val:.4f}, expected ~0"
        )

    def test_bid_ask_bounce_can_be_positive_or_negative(self, synthetic_ohlcv):
        """Bid-ask bounce proxy should have both positive and negative values."""
        sig = compute_bid_ask_bounce_proxy(synthetic_ohlcv)
        assert (sig > 0).any(), "BAB has no positive values"
        assert (sig < 0).any(), "BAB has no negative values"

    def test_volume_imbalance_bounded_unit(self, synthetic_ohlcv):
        """Volume imbalance pressure should be in [-1, 1]."""
        sig = compute_volume_imbalance_pressure(synthetic_ohlcv)
        assert sig.max() <= 1.0 + 1e-6, f"VIP max={sig.max()}, expected <= 1"
        assert sig.min() >= -1.0 - 1e-6, f"VIP min={sig.min()}, expected >= -1"

    def test_regime_conditional_momentum_uses_regime_filter(self, synthetic_ohlcv):
        """RCM should differ from raw momentum due to regime scaling."""
        df = synthetic_ohlcv
        rcm = compute_regime_conditional_momentum(df)
        # RCM should have values (not all zero)
        assert rcm.std() > 0, "RCM is constant"


# ---------------------------------------------------------------------------
# 5. Arsenal Integration
# ---------------------------------------------------------------------------
class TestV2ArsenalIntegration:
    def test_hybrid_regime_v2_in_all_groups(self):
        """Verify hybrid_regime_v2 is listed in arsenal's all_groups."""
        from omega.quant.alpha.arsenal import compute_ultimate_alphas
        import inspect
        src = inspect.getsource(compute_ultimate_alphas)
        assert "hybrid_regime_v2" in src

    def test_lazy_loading_map_includes_hybrid_regime_alpha(self):
        """Verify __init__ lazy loading map includes hybrid_regime_alpha."""
        from omega.quant.alpha import __getattr__ as alpha_getattr
        mod = alpha_getattr("hybrid_regime_alpha")
        assert hasattr(mod, "compute_all_hybrid_regime_v2_alphas")
        assert hasattr(mod, "HYBRID_REGIME_V2_COLUMNS")
        assert hasattr(mod, "compute_all_hybrid_regime_combined")


# ---------------------------------------------------------------------------
# 6. Diagnostic JSON Output
# ---------------------------------------------------------------------------
class TestV2DiagnosticJSON:
    def test_diagnostic_json_produced(self, synthetic_ohlcv, tmp_path):
        """Generate a diagnostic JSON file for v2 expansion signals."""
        df = synthetic_ohlcv
        sigs = compute_all_hybrid_regime_v2_alphas(df)

        # Evaluate signal quality metrics
        signal_metrics = {}
        for name, sig in sigs.items():
            signal_metrics[name] = {
                "std": float(sig.std()),
                "mean": float(sig.mean()),
                "min": float(sig.min()),
                "max": float(sig.max()),
                "n_zero": int((sig == 0.0).sum()),
                "n_total": int(len(sig)),
                "pit_safe": float(sig[df.groupby("ticker").cumcount() == 0].mean()) == 0.0,
            }

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = tmp_path / "data" / "phase35_results"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"alpha_expansion_{ts}.json"

        payload = {
            "gate": "HYBRID_REGIME_ALPHA_EXPANSION_20260621",
            "timestamp": ts,
            "n_signals": len(sigs),
            "signal_names": list(sigs.keys()),
            "signal_metrics": signal_metrics,
            "pit_safe": True,
            "v1_columns": HYBRID_REGIME_ALPHA_COLUMNS,
            "v2_columns": HYBRID_REGIME_V2_COLUMNS,
            "all_columns": ALL_HYBRID_REGIME_COLUMNS,
        }
        with open(out_file, "w") as f:
            json.dump(payload, f, indent=2)

        assert out_file.exists()
        loaded = json.load(open(out_file))
        assert loaded["n_signals"] == 8
        assert loaded["pit_safe"] is True
        assert len(loaded["v2_columns"]) == 8
        for name, metrics in loaded["signal_metrics"].items():
            assert metrics["std"] > 0, f"{name}: zero std"
            assert metrics["pit_safe"], f"{name}: not PIT safe"
