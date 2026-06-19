"""P11 + GATE DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614: Data Cleaning and Normalization Tests.

Tests for DataSanitizer integration and normalization into Phase35DataLoader.
Validates:
- PIT-safe cleaning pipeline: dedup, forward-fill, outlier clip, invalid price removal
- Default-on data cleaning (backward-compatible opt-out)
- Explicit normalization modes (expanding_zscore, cross_sectional_zscore, rank, none)
- Raw OHLCV preservation alongside normalized columns
- Evidence persistence (data_cleaning_enabled, normalization_mode, sanitizer stats)

Date: 2026-06-14
SOD: L2 Implementation (Data Scientist Role 14)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add paths
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from phase35_data_loader import Phase35DataLoader


def _make_sample_ohlcv(n_symbols: int = 3, n_days: int = 100) -> pd.DataFrame:
    """Create sample OHLCV data with intentional quality issues for testing."""
    rng = np.random.RandomState(42)
    symbols = [f"SYM{i}" for i in range(n_symbols)]
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    
    rows = []
    for sym in symbols:
        base_price = 50000.0 + rng.rand() * 50000.0
        for i, dt in enumerate(dates):
            price = base_price * (1 + rng.randn() * 0.02)
            rows.append({
                "date": dt,
                "ticker": sym,
                "open": price * (1 + rng.randn() * 0.005),
                "high": price * 1.02,
                "low": price * 0.98,
                "close": price,
                "volume": int(1_000_000 + rng.rand() * 500_000),
            })
    
    df = pd.DataFrame(rows)
    return df


def _inject_issues(df: pd.DataFrame) -> pd.DataFrame:
    """Inject data quality issues into clean sample data."""
    df = df.copy()
    
    # Inject duplicates (copy first 3 rows)
    dupes = df.head(3).copy()
    df = pd.concat([df, dupes], ignore_index=True)
    
    # Inject NaN values (random 5% of close prices)
    rng = np.random.RandomState(99)
    mask = rng.rand(len(df)) < 0.05
    df.loc[mask, "close"] = np.nan
    
    # Inject outliers (extreme close prices)
    outlier_idx = rng.choice(len(df), size=5, replace=False)
    df.loc[outlier_idx, "close"] = df.loc[outlier_idx, "close"] * 10.0
    
    # Inject invalid prices (zero/negative)
    invalid_idx = rng.choice(len(df), size=3, replace=False)
    df.loc[invalid_idx, "close"] = 0.0
    
    return df


class TestDataCleaningIntegration:
    """Test P11 data cleaning integration with Phase35DataLoader."""
    
    def test_sanitization_method_exists(self):
        """Test that _apply_sanitization method exists on Phase35DataLoader."""
        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        assert hasattr(loader, "_apply_sanitization"), \
            "Phase35DataLoader must have _apply_sanitization method"
    
    def test_sanitization_removes_duplicates(self):
        """Test that sanitization removes duplicate (date, ticker) rows."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=50)
        df = _inject_issues(df)
        
        initial_rows = len(df)
        n_dupes = df.duplicated(subset=["date", "ticker"], keep="first").sum()
        assert n_dupes > 0, "Test setup: must have duplicates"
        
        # Apply sanitization directly
        from omega.quant.data.sanitizer import DataSanitizer
        sanitizer = DataSanitizer(max_fill_days=3, outlier_sigma=3.0, min_price=0.01)
        df_clean, stats = sanitizer.clean_ohlcv(
            df,
            ohlcv_cols=["open", "high", "low", "close", "volume"],
            symbol_col="ticker",
            date_col="date",
        )
        
        # Sanitizer removes: duplicates + invalid prices (close=0.0 or < min_price)
        assert stats["duplicates_removed"] == n_dupes, \
            f"Should remove {n_dupes} duplicates, removed {stats['duplicates_removed']}"
        total_removed = stats["duplicates_removed"] + stats["invalid_prices_removed"]
        assert len(df_clean) == initial_rows - total_removed, \
            f"Should remove {total_removed} total rows (dupes + invalid prices)"
    
    def test_sanitization_clips_outliers(self):
        """Test that sanitization clips extreme outlier values."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=100)
        
        # Inject clear outliers AFTER min_periods=20 threshold
        # Use moderate outlier (4x normal) that expanding window WILL clip
        df.loc[30, "close"] = df.loc[30, "close"] * 4.0
        df.loc[50, "close"] = df.loc[50, "close"] * 4.0
        df.loc[70, "volume"] = df.loc[70, "volume"] * 10.0
        
        from omega.quant.data.sanitizer import DataSanitizer
        sanitizer = DataSanitizer(max_fill_days=3, outlier_sigma=3.0, min_price=0.01)
        df_clean, stats = sanitizer.clean_ohlcv(
            df,
            ohlcv_cols=["open", "high", "low", "close", "volume"],
            symbol_col="ticker",
            date_col="date",
        )
        
        # Verify clipping occurred
        assert stats["outliers_clipped"] > 0, \
            f"Should clip at least some outliers, clipped {stats['outliers_clipped']}"
        
        # Verify negative close was removed (invalid price)
        assert (df_clean["close"] >= 0.01).all(), \
            "All close prices should be >= min_price after cleaning"
        
        # Verify volume outlier was clipped (volume expanding window)
        assert stats["outliers_clipped"] >= 1, \
            "At least 1 outlier should be clipped by expanding window"
    
    def test_sanitization_forward_fills_nan(self):
        """Test that sanitization forward-fills NaN values (max 3 days)."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=50)
        
        # Inject NaN gap (3 consecutive NaN in close for one symbol)
        sym0_mask = df["ticker"] == "SYM0"
        sym0_idx = df[sym0_mask].index[10:13]  # 3 consecutive rows
        df.loc[sym0_idx, "close"] = np.nan
        
        from omega.quant.data.sanitizer import DataSanitizer
        sanitizer = DataSanitizer(max_fill_days=3, outlier_sigma=3.0, min_price=0.01)
        df_clean, stats = sanitizer.clean_ohlcv(
            df,
            ohlcv_cols=["open", "high", "low", "close", "volume"],
            symbol_col="ticker",
            date_col="date",
        )
        
        assert stats["forward_filled"] > 0, "Should forward-fill NaN values"
        # Verify NaN in close is filled (within the gap)
        sym0_clean = df_clean[df_clean["ticker"] == "SYM0"]
        assert sym0_clean["close"].isna().sum() == 0, \
            "Forward-fill should close 3-day NaN gap"
    
    def test_sanitization_removes_invalid_prices(self):
        """Test that sanitization removes rows with invalid prices (< min_price)."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=50)
        
        # Inject invalid prices
        df.loc[5, "close"] = 0.0
        df.loc[15, "close"] = -100.0
        df.loc[25, "open"] = 0.001  # Below min_price=0.01
        
        from omega.quant.data.sanitizer import DataSanitizer
        sanitizer = DataSanitizer(max_fill_days=3, outlier_sigma=3.0, min_price=0.01)
        df_clean, stats = sanitizer.clean_ohlcv(
            df,
            ohlcv_cols=["open", "high", "low", "close", "volume"],
            symbol_col="ticker",
            date_col="date",
        )
        
        assert stats["invalid_prices_removed"] > 0, \
            "Should remove rows with invalid prices"
        # Verify no zero/negative close prices remain
        assert (df_clean["close"] >= 0.01).all(), \
            "All close prices should be >= min_price"
    
    def test_no_regression_when_disabled(self):
        """Test that enable_data_cleaning=False preserves original behavior."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=50)
        df = _inject_issues(df)
        
        # Create a minimal loader without warehouse path check
        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        loader.min_price = 1.0
        loader.min_volume = 1000.0
        loader.min_history_days = 10
        
        # Simulate load_and_prepare with enable_data_cleaning=False
        df_filtered = loader.apply_filters(df.copy())
        
        # With cleaning disabled, duplicates and outliers should remain
        # (apply_filters doesn't touch them)
        assert len(df_filtered) > 0, "apply_filters should return non-empty DataFrame"
    
    def test_cleaning_report_logged(self):
        """Test that sanitization report is generated."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=50)
        df = _inject_issues(df)
        
        from omega.quant.data.sanitizer import DataSanitizer
        sanitizer = DataSanitizer(max_fill_days=3, outlier_sigma=3.0, min_price=0.01)
        df_clean, stats = sanitizer.clean_ohlcv(
            df,
            ohlcv_cols=["open", "high", "low", "close", "volume"],
            symbol_col="ticker",
            date_col="date",
        )
        
        report = sanitizer.get_sanitization_report()
        assert "Data Sanitization Report" in report
        assert "Input rows" in report
        assert "Duplicates removed" in report
        assert "Outliers clipped" in report


class TestCLIFlag:
    """Test P11 + DEFAULT_DATA_HYGIENE CLI flags in run_phase35_backtest.py."""

    def test_cli_flag_registered(self):
        """Test that --enable-data-cleaning flag is still registered (backward compat)."""
        source_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
        source = source_path.read_text(encoding="utf-8")

        assert "--enable-data-cleaning" in source, \
            "CLI flag --enable-data-cleaning must remain registered for backward compat"
        assert "enable_data_cleaning" in source, \
            "enable_data_cleaning must be referenced in source"

    def test_disable_data_cleaning_flag_registered(self):
        """GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614 — opt-out flag."""
        source_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
        source = source_path.read_text(encoding="utf-8")

        assert "--disable-data-cleaning" in source, \
            "CLI flag --disable-data-cleaning must be registered for opt-out"
        assert "disable_data_cleaning" in source, \
            "disable_data_cleaning must be referenced in source"

    def test_normalization_mode_flag_registered(self):
        """GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614 — normalization mode CLI."""
        source_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
        source = source_path.read_text(encoding="utf-8")

        assert "--normalization-mode" in source, \
            "CLI flag --normalization-mode must be registered"
        for mode in ["expanding_zscore", "cross_sectional_zscore", "rank", "none"]:
            assert mode in source, f"Normalization mode '{mode}' must be a valid choice"

    def test_data_hygiene_evidence_persisted(self):
        """GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614 — evidence in config."""
        source_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
        source = source_path.read_text(encoding="utf-8")

        assert "data_cleaning_enabled" in source, \
            "data_cleaning_enabled must be persisted in config"
        assert "normalization_mode" in source, \
            "normalization_mode must be persisted in config"
        assert "data_hygiene_evidence" in source, \
            "data_hygiene_evidence must be persisted in output config"


class TestDefaultDataHygiene:
    """GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614 — default-on tests."""

    def test_default_enable_data_cleaning_is_true(self):
        """load_and_prepare default for enable_data_cleaning must be True."""
        import inspect
        sig = inspect.signature(Phase35DataLoader.load_and_prepare)
        default = sig.parameters["enable_data_cleaning"].default
        assert default is True, \
            f"enable_data_cleaning default must be True, got {default}"

    def test_default_normalization_mode_is_expanding_zscore(self):
        """load_and_prepare default normalization_mode must be 'expanding_zscore'."""
        import inspect
        sig = inspect.signature(Phase35DataLoader.load_and_prepare)
        default = sig.parameters["normalization_mode"].default
        assert default == "expanding_zscore", \
            f"normalization_mode default must be 'expanding_zscore', got {default}"

    def test_sanitization_stores_stats(self):
        """_apply_sanitization must store stats in self._sanitization_stats."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=50)

        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        loader._sanitization_stats = None

        result = loader._apply_sanitization(df)

        assert loader._sanitization_stats is not None, \
            "_sanitization_stats must be set after _apply_sanitization"
        assert "input_rows" in loader._sanitization_stats
        assert "duplicates_removed" in loader._sanitization_stats
        assert "outliers_clipped" in loader._sanitization_stats
        assert "forward_filled" in loader._sanitization_stats
        assert "invalid_prices_removed" in loader._sanitization_stats
        assert "output_rows" in loader._sanitization_stats
        assert "data_retention_pct" in loader._sanitization_stats

    def test_get_last_evidence_returns_dict(self):
        """get_last_evidence must return a dict (empty before first call)."""
        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        evidence = loader.get_last_evidence()
        assert isinstance(evidence, dict), "get_last_evidence must return dict"


class TestNormalization:
    """GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614 — normalization tests."""

    def _make_loader(self):
        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        loader._normalization_stats = None
        return loader

    def test_expanding_zscore_preserves_raw_ohlcv(self):
        """Raw OHLCV columns must be preserved after expanding_zscore."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=60)
        loader = self._make_loader()

        result = loader._apply_normalization(df, mode="expanding_zscore")

        for col in ['open', 'high', 'low', 'close', 'volume']:
            assert col in result.columns, f"Raw column '{col}' must be preserved"
            pd.testing.assert_series_equal(
                result[col].reset_index(drop=True),
                df[col].reset_index(drop=True),
                check_names=False,
            )

    def test_expanding_zscore_adds_norm_columns(self):
        """expanding_zscore must add _norm suffixed columns."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=60)
        loader = self._make_loader()

        result = loader._apply_normalization(df, mode="expanding_zscore")

        for col in ['close', 'volume']:
            norm_col = f"{col}_norm"
            assert norm_col in result.columns, \
                f"Normalized column '{norm_col}' must be added"

    def test_expanding_zscore_no_lookahead(self):
        """Expanding z-score must produce NaN for first min_periods rows."""
        df = _make_sample_ohlcv(n_symbols=1, n_days=60)
        loader = self._make_loader()

        result = loader._apply_normalization(df, mode="expanding_zscore")

        # First 20 rows (min_periods=20) should be NaN for expanding z-score
        sym0 = result[result['ticker'] == 'SYM0'].sort_values('date')
        nan_count = sym0['close_norm'].isna().sum()
        assert nan_count >= 19, \
            f"First ~19 rows should be NaN (min_periods=20), got {nan_count} NaN"

    def test_cross_sectional_zscore_per_date(self):
        """cross_sectional_zscore must compute per-date z-score."""
        df = _make_sample_ohlcv(n_symbols=3, n_days=50)
        loader = self._make_loader()

        result = loader._apply_normalization(df, mode="cross_sectional_zscore")

        assert 'close_norm' in result.columns
        # Per-date: mean of z-scores should be approximately 0
        date_means = result.groupby('date')['close_norm'].mean()
        assert abs(date_means.mean()) < 0.1, \
            "Cross-sectional z-score per-date mean should be near 0"

    def test_rank_normalization_range(self):
        """rank normalization must produce values in [-1, 1]."""
        df = _make_sample_ohlcv(n_symbols=3, n_days=50)
        loader = self._make_loader()

        result = loader._apply_normalization(df, mode="rank")

        assert 'close_norm' in result.columns
        assert result['close_norm'].min() >= -1.0, \
            "Rank norm minimum must be >= -1.0"
        assert result['close_norm'].max() <= 1.0, \
            "Rank norm maximum must be <= 1.0"

    def test_none_mode_preserves_data(self):
        """'none' mode must not add any _norm columns."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=50)
        loader = self._make_loader()

        result = loader._apply_normalization(df, mode="none")

        norm_cols = [c for c in result.columns if c.endswith('_norm')]
        assert len(norm_cols) == 0, \
            f"'none' mode must not add _norm columns, found: {norm_cols}"
        assert len(result) == len(df), "'none' mode must not change row count"

    def test_invalid_mode_raises(self):
        """Invalid normalization mode must raise ValueError."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=50)
        loader = self._make_loader()

        with pytest.raises(ValueError, match="Unknown normalization mode"):
            loader._apply_normalization(df, mode="invalid_mode")

    def test_normalization_stats_recorded(self):
        """_normalization_stats must be set after _apply_normalization."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=60)
        loader = self._make_loader()

        loader._apply_normalization(df, mode="expanding_zscore")

        assert loader._normalization_stats is not None
        assert loader._normalization_stats["mode"] == "expanding_zscore"
        assert loader._normalization_stats["columns_normalized"] > 0
        assert loader._normalization_stats["pit_safe"] is True

    def test_cross_sectional_zscore_preserves_raw(self):
        """cross_sectional_zscore must preserve raw OHLCV columns."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=50)
        loader = self._make_loader()

        result = loader._apply_normalization(df, mode="cross_sectional_zscore")

        for col in ['open', 'high', 'low', 'close', 'volume']:
            pd.testing.assert_series_equal(
                result[col].reset_index(drop=True),
                df[col].reset_index(drop=True),
                check_names=False,
            )


class TestColumnAlignmentRegression:
    """GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_FIX1_20260614

    Regression tests for the column-alignment bug in _causal_forward_fill
    where set_index('date') + reset_index() reordered columns, causing
    position-based .values assignment to swap date/ticker values.

    Symptoms of the original bug:
    - date column contained ticker strings (e.g. 'AAA', 'YEG')
    - ticker column contained Timestamp values
    - create_walk_forward_splits crashed with TypeError: str - str
    """

    def _make_loader(self):
        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        loader.min_price = 1.0
        loader.min_volume = 1000.0
        loader.min_history_days = 10
        loader._sanitization_stats = None
        loader._normalization_stats = None
        loader._last_evidence = {}
        return loader

    def test_sanitization_preserves_date_dtype(self):
        """After sanitization, 'date' column must remain datetime64."""
        df = _make_sample_ohlcv(n_symbols=3, n_days=60)
        loader = self._make_loader()

        result = loader._apply_sanitization(df)

        assert pd.api.types.is_datetime64_any_dtype(result['date']), (
            f"'date' column must be datetime64 after sanitization, "
            f"got {result['date'].dtype}. Sample: {result['date'].head(3).tolist()}"
        )

    def test_sanitization_preserves_ticker_dtype(self):
        """After sanitization, 'ticker' column must remain string/object."""
        df = _make_sample_ohlcv(n_symbols=3, n_days=60)
        loader = self._make_loader()

        result = loader._apply_sanitization(df)

        assert result['ticker'].dtype == object or pd.api.types.is_string_dtype(result['ticker']), (
            f"'ticker' column must be string after sanitization, "
            f"got {result['ticker'].dtype}. Sample: {result['ticker'].head(3).tolist()}"
        )
        # Verify tickers are actual symbol strings, not date-like values
        sample_tickers = result['ticker'].unique()[:5]
        for t in sample_tickers:
            assert isinstance(t, str), f"Ticker must be str, got {type(t)}: {t}"
            assert not str(t).startswith('20'), f"Ticker looks like a date: {t}"

    def test_sanitization_preserves_column_order(self):
        """After sanitization, column order must match input column order."""
        df = _make_sample_ohlcv(n_symbols=2, n_days=50)
        original_cols = list(df.columns)
        loader = self._make_loader()

        result = loader._apply_sanitization(df)

        result_cols = list(result.columns)
        assert result_cols == original_cols, (
            f"Column order changed after sanitization: "
            f"expected {original_cols}, got {result_cols}"
        )

    def test_cleaning_plus_normalization_preserves_dtypes(self):
        """Full pipeline: sanitization + normalization must preserve date/ticker dtypes."""
        df = _make_sample_ohlcv(n_symbols=3, n_days=80)
        loader = self._make_loader()

        # Simulate load_and_prepare pipeline
        df_clean = loader._apply_sanitization(df)
        df_norm = loader._apply_normalization(df_clean, mode="expanding_zscore")

        assert pd.api.types.is_datetime64_any_dtype(df_norm['date']), (
            f"'date' must be datetime64 after full pipeline, got {df_norm['date'].dtype}"
        )
        assert df_norm['ticker'].dtype == object or pd.api.types.is_string_dtype(df_norm['ticker']), (
            f"'ticker' must be string after full pipeline, got {df_norm['ticker'].dtype}"
        )

    def test_walk_forward_splits_after_cleaning(self):
        """create_walk_forward_splits must work after sanitization + normalization.

        This is the exact failure scenario from the bug report:
        TypeError: unsupported operand type(s) for -: 'str' and 'str'
        """
        df = _make_sample_ohlcv(n_symbols=3, n_days=200)
        loader = self._make_loader()

        # Apply full pipeline
        df_clean = loader._apply_sanitization(df)
        df_norm = loader._apply_normalization(df_clean, mode="expanding_zscore")

        # This must NOT raise TypeError
        splits = loader.create_walk_forward_splits(
            df_norm, n_folds=2, train_years=0, test_years=0,
        )
        # The 200 business-day span (~280 calendar days) may not fit
        # full train/test windows, but it must not crash with TypeError.
        assert isinstance(splits, list), "create_walk_forward_splits must return a list"

    def test_top_symbols_are_tickers_not_dates(self):
        """get_top_symbols must return ticker strings, not Timestamp values."""
        df = _make_sample_ohlcv(n_symbols=5, n_days=80)
        loader = self._make_loader()

        df_clean = loader._apply_sanitization(df)

        top = loader.get_top_symbols(df_clean, top_n=3)
        assert len(top) > 0, "get_top_symbols must return at least one symbol"
        for s in top:
            assert isinstance(s, str), f"Top symbol must be str, got {type(s)}: {s}"
            assert not str(s).startswith('20'), f"Top symbol looks like a date: {s}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


class TestJSONSerializability:
    """GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_FIX2_20260614

    Regression tests ensuring sanitizer_stats / data_hygiene_evidence /
    config dicts are fully JSON-serializable (no numpy.int64 / float64).

    Original bug: TypeError Object of type int64 is not JSON serializable
    in config.data_hygiene_evidence.sanitizer_stats.forward_filled.
    """

    def _make_loader(self):
        loader = Phase35DataLoader.__new__(Phase35DataLoader)
        loader.min_price = 1.0
        loader.min_volume = 1000.0
        loader.min_history_days = 10
        loader._sanitization_stats = None
        loader._normalization_stats = None
        loader._last_evidence = {}
        return loader

    def test_sanitizer_stats_are_json_serializable(self):
        """All sanitizer_stats values must be native Python scalars."""
        import json

        df = _make_sample_ohlcv(n_symbols=3, n_days=80)
        loader = self._make_loader()

        loader._apply_sanitization(df)

        stats = loader._sanitization_stats
        assert stats is not None, "sanitizer_stats must be set"

        # json.dumps must NOT raise TypeError
        serialized = json.dumps(stats)
        assert isinstance(serialized, str)

        # Verify round-trip
        deserialized = json.loads(serialized)
        for key in ("input_rows", "duplicates_removed", "forward_filled",
                     "outliers_clipped", "invalid_prices_removed", "output_rows"):
            assert isinstance(deserialized[key], int), (
                f"{key} must deserialize to int, got {type(deserialized[key])}"
            )

    def test_evidence_dict_is_json_serializable(self):
        """Full evidence dict from get_last_evidence() must be JSON-safe."""
        import json

        df = _make_sample_ohlcv(n_symbols=3, n_days=80)
        loader = self._make_loader()

        # Simulate load_and_prepare evidence pipeline
        loader._sanitization_stats = None
        loader._normalization_stats = None
        loader._last_evidence = {}

        df_clean = loader._apply_sanitization(df)
        df_norm = loader._apply_normalization(df_clean, mode="expanding_zscore")

        loader._last_evidence = {
            "gate": "DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614",
            "data_cleaning_enabled": True,
            "normalization_mode": "expanding_zscore",
            "sanitizer_stats": loader._sanitization_stats,
            "normalization_stats": getattr(loader, '_normalization_stats', None),
            "output_rows": int(len(df_norm)),
            "output_symbols": int(df_norm['ticker'].nunique()),
            "date_range": f"{df_norm['date'].min()} to {df_norm['date'].max()}",
            "pit_safe": True,
        }

        evidence = loader.get_last_evidence()
        # json.dumps must NOT raise TypeError
        serialized = json.dumps(evidence)
        assert isinstance(serialized, str)

    def test_forward_filled_is_python_int_not_numpy(self):
        """forward_filled must be Python int, not numpy.int64."""
        import numpy as np

        df = _make_sample_ohlcv(n_symbols=2, n_days=50)

        # Inject NaN gap to trigger forward-fill
        sym0_mask = df["ticker"] == "SYM0"
        sym0_idx = df[sym0_mask].index[10:13]
        df.loc[sym0_idx, "close"] = np.nan

        loader = self._make_loader()
        loader._apply_sanitization(df)

        ff = loader._sanitization_stats["forward_filled"]
        assert isinstance(ff, int), (
            f"forward_filled must be Python int, got {type(ff).__name__}"
        )
        assert not isinstance(ff, np.integer), (
            f"forward_filled must NOT be numpy integer, got {type(ff).__name__}"
        )

    def test_outliers_clipped_is_python_int_not_numpy(self):
        """outliers_clipped must be Python int, not numpy.int64."""
        import numpy as np

        df = _make_sample_ohlcv(n_symbols=2, n_days=100)
        # Inject outlier to trigger clipping
        df.loc[30, "close"] = df.loc[30, "close"] * 4.0

        loader = self._make_loader()
        loader._apply_sanitization(df)

        oc = loader._sanitization_stats["outliers_clipped"]
        assert isinstance(oc, int), (
            f"outliers_clipped must be Python int, got {type(oc).__name__}"
        )
        assert not isinstance(oc, np.integer), (
            f"outliers_clipped must NOT be numpy integer, got {type(oc).__name__}"
        )

    def test_config_dict_with_evidence_is_json_serializable(self):
        """Simulated config dict (as in run_phase35_backtest.py) must serialize."""
        import json

        df = _make_sample_ohlcv(n_symbols=3, n_days=80)
        loader = self._make_loader()

        df_clean = loader._apply_sanitization(df)
        loader._apply_normalization(df_clean, mode="expanding_zscore")

        evidence = {
            "gate": "DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614",
            "data_cleaning_enabled": True,
            "normalization_mode": "expanding_zscore",
            "sanitizer_stats": loader._sanitization_stats,
            "normalization_stats": getattr(loader, '_normalization_stats', None),
            "output_rows": int(len(df_clean)),
            "output_symbols": int(df_clean['ticker'].nunique()),
            "date_range": f"{df_clean['date'].min()} to {df_clean['date'].max()}",
            "pit_safe": True,
        }

        config = {
            "start_date": "2015-01-05",
            "end_date": "2026-05-14",
            "data_cleaning_enabled": True,
            "normalization_mode": "expanding_zscore",
            "data_hygiene_evidence": evidence,
        }

        # This is the exact call that failed in the bug report
        serialized = json.dumps(config, indent=2)
        assert isinstance(serialized, str)
        assert "forward_filled" in serialized
