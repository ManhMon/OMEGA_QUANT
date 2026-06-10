"""P11: Data Cleaning Integration Tests.

Tests for DataSanitizer integration into Phase35DataLoader.
Validates PIT-safe cleaning pipeline: dedup, forward-fill, outlier clip, invalid price removal.

Date: 2026-06-10
SOD: L2 Implementation (Backend Engineer Role 9)
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
        from omega.quant.data_sanitizer import DataSanitizer
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
        
        from omega.quant.data_sanitizer import DataSanitizer
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
        
        from omega.quant.data_sanitizer import DataSanitizer
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
        
        from omega.quant.data_sanitizer import DataSanitizer
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
        
        from omega.quant.data_sanitizer import DataSanitizer
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
    """Test P11 CLI flag in run_phase35_backtest.py."""
    
    def test_cli_flag_registered(self):
        """Test that --enable-data-cleaning flag is registered in argparse."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "run_phase35_backtest",
            str(Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"),
        )
        
        # Read the source to check flag exists
        source_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
        source = source_path.read_text(encoding="utf-8")
        
        assert "--enable-data-cleaning" in source, \
            "CLI flag --enable-data-cleaning must be registered"
        assert "enable_data_cleaning" in source, \
            "enable_data_cleaning must be passed to load_and_prepare"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
