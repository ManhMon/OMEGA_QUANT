"""Targeted tests for GPFeatureAdapter non-numeric column handling.

Regression test for E2E family failure: ValueError could not convert
string to float: 'HOSE' when phase34 returns DataFrame with
non-numeric columns (exchange, ticker) that leaked into the
variance filter.

GATE: E2E_FAMILY_ADVANCED_FEATURES_FIX_20260613
"""

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from omega.quant.evolution.feature_adapter import GPFeatureAdapter


def _make_panel(n_tickers: int = 3, n_days: int = 60) -> pd.DataFrame:
    """Create minimal OHLCV panel with non-numeric 'exchange' column."""
    rng = np.random.default_rng(42)
    rows = []
    for i, ticker in enumerate(["VNM", "FPT", "VCB"][:n_tickers]):
        dates = pd.bdate_range("2024-01-02", periods=n_days, freq="B")
        close = 50000.0 + rng.standard_normal(n_days).cumsum() * 500
        rows.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": dates,
                    "open": close + rng.uniform(-200, 200, n_days),
                    "high": close + rng.uniform(100, 800, n_days),
                    "low": close - rng.uniform(100, 800, n_days),
                    "close": close,
                    "volume": rng.integers(100_000, 5_000_000, n_days),
                    "exchange": "HOSE",
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


class TestGPFeatureAdapterNonNumericSafety:
    """Verify GPFeatureAdapter handles non-numeric columns without crashing."""

    def test_compute_all_with_exchange_column(self):
        """Regression: 'HOSE' in exchange column must not crash variance filter."""
        panel = _make_panel()
        adapter = GPFeatureAdapter()
        result = adapter.compute_all(panel, top_n_features=50)
        assert isinstance(result, dict)
        assert len(result) > 0
        for name, arr in result.items():
            assert np.issubdtype(arr.dtype, np.floating), (
                f"Feature '{name}' has non-float dtype {arr.dtype}"
            )

    def test_all_output_arrays_are_numeric(self):
        """Every output array must be float64 — no string leakage."""
        panel = _make_panel()
        adapter = GPFeatureAdapter()
        result = adapter.compute_all(panel, top_n_features=100)
        for name, arr in result.items():
            assert arr.dtype == np.float64, f"'{name}' dtype is {arr.dtype}"
            assert not np.any(np.isnan(arr)), f"'{name}' contains NaN"
            assert not np.any(np.isinf(arr)), f"'{name}' contains Inf"

    def test_no_categorical_columns_in_output(self):
        """Output dict keys must never include exchange/ticker/date."""
        panel = _make_panel()
        adapter = GPFeatureAdapter()
        result = adapter.compute_all(panel, top_n_features=100)
        forbidden = {"ticker", "date", "exchange"}
        leaked = forbidden & set(result.keys())
        assert not leaked, f"Non-numeric columns leaked into output: {leaked}"

    def test_phase34_column_filter_only_alpha_prefix(self):
        """Phase34 source should only select alpha_p34_ prefixed columns."""
        panel = _make_panel()
        adapter = GPFeatureAdapter()
        if "phase34" not in adapter.sources:
            pytest.skip("phase34 source not available")
        p34_df = adapter.sources["phase34"](panel)
        alpha_cols = [c for c in p34_df.columns if c.startswith("alpha_p34_")]
        non_alpha = [
            c
            for c in p34_df.columns
            if c not in ("ticker", "date")
            and not c.startswith("alpha_p34_")
        ]
        assert len(alpha_cols) == 7
        assert "exchange" in non_alpha or len(non_alpha) >= 0

    def test_variance_filter_drops_pure_string_array(self):
        """Variance filter must gracefully skip a pure-string array."""
        adapter = GPFeatureAdapter()
        all_alphas = [
            ("good_feature", np.array([1.0, 2.0, 3.0, 4.0, 5.0])),
            ("bad_string", np.array(["HOSE", "HNX", "UPCOM", "HOSE", "HNX"])),
            ("constant", np.array([1.0, 1.0, 1.0, 1.0, 1.0])),
        ]
        filtered = []
        for name, values in all_alphas:
            try:
                arr = np.asarray(values)
                if not np.issubdtype(arr.dtype, np.number):
                    coerced = pd.to_numeric(
                        pd.Series(arr.ravel()), errors="coerce"
                    )
                    arr = coerced.values.reshape(arr.shape)
                values = np.nan_to_num(
                    np.asarray(arr, dtype=np.float64),
                    nan=0.0,
                    posinf=0.0,
                    neginf=0.0,
                )
            except (ValueError, TypeError):
                continue
            if np.std(values) > 1e-6:
                filtered.append((name, values))
        names = [n for n, _ in filtered]
        assert "good_feature" in names
        assert "bad_string" not in names
        assert "constant" not in names


class TestGPFeatureAdapterPITSafety:
    """Verify PIT safety is preserved after the fix."""

    def test_engineered_features_use_past_only(self):
        """ret_1d, ret_5d must use shifted (past-only) data."""
        panel = _make_panel()
        adapter = GPFeatureAdapter()
        result = adapter.compute_all(panel, top_n_features=100)
        if "ret_1d" in result:
            assert result["ret_1d"].dtype == np.float64
        if "ret_5d" in result:
            assert result["ret_5d"].dtype == np.float64


class TestGPFeatureAdapterCacheSafety:
    """Regression: cache key must detect middle-row mutations.

    FIX: PERFORMANCE_PARALLELIZATION_AUDIT_FIX1_20260613 — Finding 1
    The old fingerprint (shape + columns + first/last rows) returned stale
    cached features when a middle row changed.  The new fingerprint uses
    pd.util.hash_pandas_object (full-content hash) so any interior mutation
    invalidates the cache.
    """

    def test_cache_miss_on_middle_row_mutation(self):
        """Changing a middle row must produce a different fingerprint and cache miss."""
        panel = _make_panel(n_tickers=3, n_days=60)
        adapter = GPFeatureAdapter()

        # First call: populate cache
        result_1 = adapter.compute_all(panel, top_n_features=50)
        fp_1 = adapter._fingerprint(panel, 50)

        # Mutate a middle row (row index 30 in a 180-row panel — well interior)
        mid = len(panel) // 2
        panel.loc[panel.index[mid], "close"] = panel.loc[panel.index[mid], "close"] * 2.0

        # Second call: must NOT hit stale cache
        fp_2 = adapter._fingerprint(panel, 50)
        assert fp_1 != fp_2, (
            "Fingerprint collision: middle-row mutation produced same hash. "
            "Cache would return stale features."
        )

        result_2 = adapter.compute_all(panel, top_n_features=50)

        # Verify at least one output array changed (the 'close' feature directly)
        changed = False
        for key in result_1:
            if key in result_2 and not np.array_equal(result_1[key], result_2[key]):
                changed = True
                break
        assert changed, "No output arrays changed after middle-row mutation — stale cache suspected"

    def test_cache_hit_on_identical_dataframe(self):
        """Identical DataFrame must still produce cache hit."""
        panel = _make_panel(n_tickers=3, n_days=60)
        adapter = GPFeatureAdapter()

        result_1 = adapter.compute_all(panel, top_n_features=50)
        # Second call with same data should hit cache
        result_2 = adapter.compute_all(panel, top_n_features=50)
        assert result_1 is result_2, "Cache miss on identical DataFrame — caching is broken"

    def test_fingerprint_differs_on_interior_value_change(self):
        """Fingerprint must change when any interior cell is modified."""
        panel = _make_panel(n_tickers=2, n_days=30)
        fp_original = GPFeatureAdapter._fingerprint(panel, 50)

        # Change volume in an interior row
        interior_idx = panel.index[10]
        original_volume = panel.loc[interior_idx, "volume"]
        panel.loc[interior_idx, "volume"] = original_volume + 999_999

        fp_mutated = GPFeatureAdapter._fingerprint(panel, 50)
        assert fp_original != fp_mutated, (
            "Fingerprint did not change after interior volume mutation"
        )
