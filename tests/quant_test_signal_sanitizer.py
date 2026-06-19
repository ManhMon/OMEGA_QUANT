import pandas as pd
import numpy as np
import pytest

from omega.quant.signal.sanitizer import SignalSanitizer


class TestSignalSanitizer:
    def test_sanitize_signal_multiindex_symbol_shift(self):
        index = pd.MultiIndex.from_tuples(
            [
                ("2026-01-01", "AAA"),
                ("2026-01-02", "AAA"),
                ("2026-01-01", "BBB"),
                ("2026-01-02", "BBB"),
            ],
            names=["date", "symbol"],
        )
        df = pd.DataFrame({"signal": [1.0, 2.0, 10.0, 20.0]}, index=index)

        result = SignalSanitizer.sanitize_signal(df, "signal")

        expected = pd.Series([np.nan, 1.0, np.nan, 10.0], index=index, name="signal")
        pd.testing.assert_series_equal(result, expected)

    def test_sanitize_signal_symbol_column_shift(self):
        df = pd.DataFrame(
            {
                "symbol": ["AAA", "AAA", "BBB", "BBB"],
                "signal": [1.0, 2.0, 10.0, 20.0],
            }
        )

        result = SignalSanitizer.sanitize_signal(df, "signal")

        expected = pd.Series([np.nan, 1.0, np.nan, 10.0], name="signal")
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected)

    def test_sanitize_signal_single_symbol_shift(self):
        df = pd.DataFrame({"signal": [1.0, 2.0, 3.0]})

        result = SignalSanitizer.sanitize_signal(df, "signal")

        expected = pd.Series([np.nan, 1.0, 2.0], name="signal")
        pd.testing.assert_series_equal(result, expected)

    def test_sanitize_signal_no_force_shift(self):
        df = pd.DataFrame({"signal": [1.0, 2.0, 3.0]})

        result = SignalSanitizer.sanitize_signal(df, "signal", force_shift=False)

        expected = pd.Series([1.0, 2.0, 3.0], name="signal")
        pd.testing.assert_series_equal(result, expected)

    def test_smooth_signal_rolling_symbol_aware(self):
        df = pd.DataFrame(
            {
                "symbol": ["AAA", "AAA", "AAA", "BBB", "BBB", "BBB"],
                "signal": [1.0, 3.0, 5.0, 10.0, 20.0, 30.0],
            }
        )

        result = SignalSanitizer.smooth_signal(df, "signal", window=2, method="rolling")

        expected = pd.Series([1.0, 2.0, 4.0, 10.0, 15.0, 25.0], name="signal")
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected)

    def test_smooth_signal_ewm_symbol_aware(self):
        df = pd.DataFrame(
            {
                "symbol": ["AAA", "AAA", "AAA"],
                "signal": [1.0, 3.0, 5.0],
            }
        )

        result = SignalSanitizer.smooth_signal(df, "signal", window=2, method="ewm")

        alpha = 2 / (2 + 1)
        expected = df.groupby("symbol")["signal"].transform(
            lambda x: x.ewm(alpha=alpha, adjust=False).mean()
        )
        pd.testing.assert_series_equal(result, expected)

    def test_smooth_signal_invalid_method_raises(self):
        df = pd.DataFrame({"signal": [1.0, 2.0, 3.0]})

        with pytest.raises(ValueError, match="Unknown method"):
            SignalSanitizer.smooth_signal(df, "signal", method="bad")

    def test_apply_midas_smooth_multiindex(self):
        index = pd.MultiIndex.from_tuples(
            [
                ("2026-01-01", "AAA"),
                ("2026-01-02", "AAA"),
                ("2026-01-03", "AAA"),
            ],
            names=["date", "symbol"],
        )
        df = pd.DataFrame({"signal": [1.0, 2.0, 3.0]}, index=index)

        result = SignalSanitizer.apply_midas_smooth(df, "signal", alpha=0.5)

        expected = df.groupby(level="symbol")["signal"].transform(
            lambda x: x.shift(1).ewm(alpha=0.5, adjust=False).mean()
        )
        pd.testing.assert_series_equal(result, expected)

    def test_calculate_adaptive_threshold_single_symbol(self):
        df = pd.DataFrame({"signal": [1.0, 2.0, 3.0, 4.0, 5.0]})

        result = SignalSanitizer.calculate_adaptive_threshold(
            df, "signal", percentile=50, window=2
        )

        expected = df["signal"].shift(1).rolling(2, min_periods=2).quantile(0.5)
        pd.testing.assert_series_equal(result, expected)

    def test_calculate_weighted_signal(self):
        df = pd.DataFrame(
            {
                "signal": [1.0, -2.0, 3.0],
                "weight": [0.5, 0.25, 1.0],
            }
        )

        result = SignalSanitizer.calculate_weighted_signal(df, "signal", "weight")

        expected = pd.Series([0.5, -0.5, 3.0])
        pd.testing.assert_series_equal(result, expected, check_names=False)
