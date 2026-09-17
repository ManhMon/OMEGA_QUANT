"""
Regression test: Automatic Targeted Re-fetch on price jump / split detection.
Gate: AUTOMATIC_TARGETED_REFETCH_20260618

Proves that:
  1. detect_price_anomalies correctly flags price jumps > 25% at boundary
  2. classify_anomaly distinguishes SPLIT_LIKE from PRICE_JUMP
  3. run_targeted_refetch replaces only PRICE_JUMP symbols
  4. run_updater integrates re-fetch and passes skip_refetch flag
  5. CLI --no-refetch flag is wired correctly
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import update_market_data as umd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(
    ticker: str,
    dates: pd.DatetimeIndex,
    close: float,
    exchange: str = "HOSE",
    volume: int = 100000,
) -> pd.DataFrame:
    """Build a canonical-schema DataFrame for one ticker."""
    n = len(dates)
    return pd.DataFrame({
        "ticker": ticker,
        "date": dates,
        "exchange": exchange,
        "open": np.full(n, close * 0.99),
        "high": np.full(n, close * 1.02),
        "low": np.full(n, close * 0.98),
        "close": np.full(n, close),
        "volume": np.full(n, volume, dtype=np.int64),
        "as_of": "2026-06-18 00:00:00",
        "available_at": dates + pd.Timedelta(days=1),
        "source": "vnstock_vci",
        "price_scale": "VND",
        "adjusted": "backward_adjusted",
        "rebuild_date": "2026-06-18",
    })


def _make_canonical_with_boundary(ticker: str, last_close: float, n_days: int = 30):
    """Build canonical data ending at a known date/close."""
    dates = pd.bdate_range("2026-05-01", periods=n_days)
    return _make_ohlcv(ticker, dates, last_close, volume=100000)


def _make_new_data(ticker: str, first_close: float, n_days: int = 5, volume: int = 120000):
    """Build new data starting the day after canonical ends."""
    start = pd.Timestamp("2026-06-15")
    dates = pd.bdate_range(start, periods=n_days)
    return _make_ohlcv(ticker, dates, first_close, volume=volume)


def _make_overlap_data(
    ticker: str,
    start: str,
    canon_close: float,
    new_close: float,
    n_days: int = 5,
    volume: int = 120000,
):
    """Build canonical/new frames that share dates for direct overlap tests."""
    dates = pd.bdate_range(start, periods=n_days)
    canon = _make_ohlcv(ticker, dates, canon_close, volume=100000)
    new = _make_ohlcv(ticker, dates, new_close, volume=volume)
    return canon, new


# ---------------------------------------------------------------------------
# 1. detect_price_anomalies
# ---------------------------------------------------------------------------

class TestDetectPriceAnomalies:

    def test_no_anomaly_without_overlap(self):
        """No shared dates -> no anomaly."""
        canon = _make_canonical_with_boundary("VCB", 50000.0)
        new = _make_new_data("VCB", 52000.0)
        anomalies = umd.detect_price_anomalies(new, canon)
        assert anomalies == []

    def test_detects_overlap_price_drop(self):
        """Shared-date 50% price drop should be flagged."""
        canon, new = _make_overlap_data("AAA", "2026-06-16", 50000.0, 25000.0)
        anomalies = umd.detect_price_anomalies(new, canon)
        assert len(anomalies) == 1
        assert anomalies[0]["symbol"] == "AAA"
        assert anomalies[0]["return_pct"] == pytest.approx(-50.0, abs=0.1)
        assert anomalies[0]["classification"] == "PRICE_JUMP"

    def test_detects_overlap_price_increase(self):
        """Shared-date 50% price increase should be flagged."""
        canon, new = _make_overlap_data("BBB", "2026-06-16", 30000.0, 45000.0)
        anomalies = umd.detect_price_anomalies(new, canon)
        assert len(anomalies) == 1
        assert anomalies[0]["return_pct"] == pytest.approx(50.0, abs=0.1)
        assert anomalies[0]["date"] == "2026-06-16"

    def test_multiple_tickers_mixed(self):
        """Only tickers with overlap mismatches should be flagged."""
        canon_ok1, new_ok1 = _make_overlap_data("OK1", "2026-06-16", 50000.0, 50025.0)
        canon_bad1, new_bad1 = _make_overlap_data("BAD1", "2026-06-16", 50000.0, 10000.0)
        canon_ok2, new_ok2 = _make_overlap_data("OK2", "2026-06-16", 20000.0, 20010.0)
        canon = pd.concat([
            canon_ok1,
            canon_bad1,
            canon_ok2,
        ], ignore_index=True)
        new = pd.concat([
            new_ok1,
            new_bad1,
            new_ok2,
        ], ignore_index=True)
        anomalies = umd.detect_price_anomalies(new, canon)
        assert len(anomalies) == 1
        assert anomalies[0]["symbol"] == "BAD1"

    def test_empty_inputs(self):
        """Empty canonical or new data returns no anomalies."""
        assert umd.detect_price_anomalies(pd.DataFrame(), None) == []
        assert umd.detect_price_anomalies(
            _make_new_data("X", 10000.0), pd.DataFrame()
        ) == []
        assert umd.detect_price_anomalies(
            _make_new_data("X", 10000.0), None
        ) == []

    def test_new_ticker_not_in_canonical(self):
        """Ticker absent from canonical should be skipped."""
        canon = _make_canonical_with_boundary("OLD", 50000.0)
        new = _make_new_data("NEW", 10000.0)
        anomalies = umd.detect_price_anomalies(new, canon)
        assert anomalies == []

    def test_volume_ratio_computed(self):
        """Volume ratio should use overlapping row volumes."""
        canon, new = _make_overlap_data("CCC", "2026-06-16", 50000.0, 10000.0, volume=300000)
        anomalies = umd.detect_price_anomalies(new, canon)
        assert len(anomalies) == 1
        assert anomalies[0]["volume_ratio"] > 0

    def test_ignores_small_overlap_difference_within_tolerance(self):
        """0.05% shared-date diff should not trigger anomaly."""
        canon, new = _make_overlap_data("TOL", "2026-06-16", 50000.0, 49975.0)
        anomalies = umd.detect_price_anomalies(new, canon)
        assert anomalies == []


# ---------------------------------------------------------------------------
# 2. classify_anomaly
# ---------------------------------------------------------------------------

class TestClassifyAnomaly:

    def test_split_like(self):
        """Price ratio ~0.5 + volume spike → SPLIT_LIKE."""
        assert umd.classify_anomaly(0.50, 2.0) == "SPLIT_LIKE"
        assert umd.classify_anomaly(0.55, 1.8) == "SPLIT_LIKE"
        assert umd.classify_anomaly(0.35, 3.0) == "SPLIT_LIKE"  # 3:1 split

    def test_price_jump_down(self):
        """Large price drop without split signature → PRICE_JUMP."""
        assert umd.classify_anomaly(0.50, 0.5) == "PRICE_JUMP"  # no vol spike
        assert umd.classify_anomaly(0.10, 2.0) == "PRICE_JUMP"  # too low ratio
        assert umd.classify_anomaly(0.80, 2.0) == "PRICE_JUMP"  # too high ratio

    def test_price_jump_up(self):
        """Large price increase → PRICE_JUMP."""
        assert umd.classify_anomaly(1.50, 2.0) == "PRICE_JUMP"
        assert umd.classify_anomaly(2.00, 1.0) == "PRICE_JUMP"

    def test_boundary_cases(self):
        """Edge cases at ratio boundaries."""
        # Just below SPLIT_RATIO_LOW
        assert umd.classify_anomaly(0.29, 2.0) == "PRICE_JUMP"
        # Just above SPLIT_RATIO_HIGH
        assert umd.classify_anomaly(0.73, 2.0) == "PRICE_JUMP"
        # Exactly at boundaries with volume
        assert umd.classify_anomaly(0.30, 1.5) == "SPLIT_LIKE"
        assert umd.classify_anomaly(0.72, 1.5) == "SPLIT_LIKE"


# ---------------------------------------------------------------------------
# 3. run_targeted_refetch (mocked client)
# ---------------------------------------------------------------------------

class TestRunTargetedRefetch:

    def _mock_client(self, return_df=None):
        client = MagicMock()
        if return_df is not None:
            client.fetch_history.return_value = return_df
        else:
            client.fetch_history.return_value = pd.DataFrame()
        return client

    def test_no_price_jump_anomalies(self):
        """SPLIT_LIKE anomalies should not trigger re-fetch."""
        anomalies = [
            {"symbol": "A", "classification": "SPLIT_LIKE",
             "return_pct": -50.0, "exchange": "HOSE",
             "canon_close": 50000.0},
        ]
        client = self._mock_client()
        df, stats = umd.run_targeted_refetch(
            client, anomalies, {"A": "HOSE"}, "2026-06-18"
        )
        assert df.empty
        assert stats["targets"] == 0

    def test_refetch_replaces_price_jump(self):
        """PRICE_JUMP anomaly should be re-fetched and validated."""
        # Simulate re-fetched data with correct boundary
        refetch_dates = pd.bdate_range("2026-03-20", periods=60)
        refetch_df = _make_ohlcv("BAD1", refetch_dates, 49000.0)

        anomalies = [
            {"symbol": "BAD1", "classification": "PRICE_JUMP",
             "return_pct": -80.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": "2026-03-19",
             "price_ratio": 0.2, "volume_ratio": 1.0},
        ]

        client = MagicMock()
        # The fetch_one_symbol function will be called; mock at the client level
        # We need to mock fetch_one_symbol since it processes the raw data
        with patch.object(umd, 'fetch_one_symbol', return_value=refetch_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"BAD1": "HOSE"}, "2026-06-18"
            )
        assert stats["targets"] == 1
        assert stats["success"] == 1
        assert not df.empty

    def test_refetch_fails_empty(self):
        """Empty re-fetch result should be counted as failed."""
        anomalies = [
            {"symbol": "FAIL1", "classification": "PRICE_JUMP",
             "return_pct": -60.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": "2026-03-19",
             "price_ratio": 0.4, "volume_ratio": 1.0},
        ]
        client = self._mock_client()
        with patch.object(umd, 'fetch_one_symbol', return_value=pd.DataFrame()):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"FAIL1": "HOSE"}, "2026-06-18"
            )
        assert stats["failed"] == 1
        assert stats["success"] == 0
        assert df.empty

    def test_refetch_still_anomalous(self):
        """Re-fetched data that is still anomalous should be discarded."""
        # Re-fetched data still has wrong boundary price
        refetch_dates = pd.bdate_range("2026-03-20", periods=60)
        refetch_df = _make_ohlcv("BAD1", refetch_dates, 10000.0)  # still 80% off

        anomalies = [
            {"symbol": "BAD1", "classification": "PRICE_JUMP",
             "return_pct": -80.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": "2026-03-19",
             "price_ratio": 0.2, "volume_ratio": 1.0},
        ]
        client = self._mock_client()
        with patch.object(umd, 'fetch_one_symbol', return_value=refetch_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"BAD1": "HOSE"}, "2026-06-18"
            )
        assert stats["failed"] == 1
        assert stats["details"][0]["status"] == "still_anomalous"

    def test_refetch_cap_enforced(self):
        """Should not re-fetch more than MAX_REFETCH_SYMBOLS."""
        anomalies = [
            {"symbol": f"SYM{i}", "classification": "PRICE_JUMP",
             "return_pct": -60.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": "2026-03-19",
             "price_ratio": 0.4, "volume_ratio": 1.0}
            for i in range(umd.MAX_REFETCH_SYMBOLS + 5)
        ]
        exchange_map = {f"SYM{i}": "HOSE" for i in range(umd.MAX_REFETCH_SYMBOLS + 5)}
        client = self._mock_client()
        with patch.object(umd, 'fetch_one_symbol', return_value=pd.DataFrame()):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, exchange_map, "2026-06-18"
            )
        assert stats["targets"] == umd.MAX_REFETCH_SYMBOLS

    def test_refetch_uses_symbol_specific_last_date_minus_15_days(self):
        """Refetch window should start from symbol canon_date minus 15 days."""
        refetch_df = _make_ohlcv(
            "WIN1",
            pd.bdate_range("2026-05-22", periods=25),
            49000.0,
        )
        anomalies = [
            {"symbol": "WIN1", "classification": "PRICE_JUMP",
             "return_pct": -30.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": "2026-06-01",
             "price_ratio": 0.7, "volume_ratio": 1.0},
        ]
        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=refetch_df) as mock_fetch:
            umd.run_targeted_refetch(
                client, anomalies, {"WIN1": "HOSE"}, "2026-06-18"
            )
        assert mock_fetch.call_args[0][2] == "2026-05-17"
        assert mock_fetch.call_args[0][3] == "2026-06-18"


class TestFetchSymbolsOverlapPreload:

    def test_fetch_symbols_subtracts_15_days_from_symbol_max_dates(self):
        client = MagicMock()
        exchange_map = {"AAA": "HOSE", "BBB": "HNX"}

        def fake_fetch_one_symbol(_client, symbol, start_date, end_date, exchange):
            return _make_ohlcv(symbol, pd.bdate_range(start_date, periods=2), 50000.0, exchange=exchange)

        with patch.object(umd, "fetch_one_symbol", side_effect=fake_fetch_one_symbol) as mock_fetch, \
             patch.object(umd.time, "sleep", return_value=None):
            df, stats = umd.fetch_symbols(
                client=client,
                symbols=["AAA", "BBB"],
                exchange_map=exchange_map,
                start_date="2026-05-01",
                end_date="2026-06-18",
                symbol_max_dates={
                    "AAA": pd.Timestamp("2026-06-10"),
                    "BBB": pd.Timestamp("2026-05-20"),
                },
            )

        starts = {call.args[1]: call.args[2] for call in mock_fetch.call_args_list}
        assert starts == {"AAA": "2026-05-26", "BBB": "2026-05-05"}
        assert stats["fetched"] == 2
        assert set(df["ticker"]) == {"AAA", "BBB"}

    def test_run_targeted_refetch_composition(self):
        """run_targeted_refetch should accept detect_price_anomalies output directly."""
        canon, new = _make_overlap_data("CMP1", "2026-06-16", 50000.0, 40000.0)
        anomalies = umd.detect_price_anomalies(new, canon)
        ref_df = _make_ohlcv("CMP1", pd.bdate_range("2026-06-16", periods=10), 49975.0)

        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client,
                anomalies,
                {"CMP1": "HOSE"},
                "2026-06-30",
                canonical_df=canon,
            )

        assert len(anomalies) == 1
        assert anomalies[0]["canon_date"] == anomalies[0]["date"]
        assert stats["success"] == 1
        assert stats["failed"] == 0
        assert stats["details"][0]["status"] == "success"
        assert not df.empty


# ---------------------------------------------------------------------------
# 4. Integration: run_updater with skip_refetch
# ---------------------------------------------------------------------------

class TestRunUpdaterRefetch:

    def test_skip_refetch_flag(self):
        """skip_refetch=True should skip anomaly detection entirely."""
        with patch.object(umd, 'load_universe_from_json', return_value={"hsx": ["VCB"], "hnx": []}), \
             patch.object(umd, 'read_canonical_max_date', return_value=pd.Timestamp("2026-06-17")), \
             patch.object(umd, '_create_vnstock_client') as mock_client_fn, \
             patch.object(umd, 'fetch_symbols') as mock_fetch, \
             patch.object(umd, 'read_canonical') as mock_read_canon, \
             patch.object(umd, 'detect_price_anomalies') as mock_detect, \
             patch.object(umd, 'validate_dataframe', return_value=(True, [])), \
             patch.object(umd, 'atomic_write_with_backup') as mock_write:

            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client

            new_data = _make_new_data("VCB", 50000.0, n_days=1)
            mock_fetch.return_value = (new_data, {"fetched": 1, "empty": 0, "errors": 0, "rows": 1, "total_symbols": 1})
            mock_read_canon.return_value = _make_canonical_with_boundary("VCB", 50000.0)
            mock_write.return_value = Path("/fake/output.parquet")

            result = umd.run_updater(
                canonical_path=Path("/fake/canonical.parquet"),
                skip_refetch=True,
            )

            mock_detect.assert_not_called()

    def test_refetch_triggered_on_anomaly(self):
        """When overlap mismatches detected, full refetch should be invoked directly."""
        with patch.object(umd, 'load_universe_from_json', return_value={"hsx": ["BAD1"], "hnx": []}), \
             patch.object(umd, 'read_canonical_max_date', return_value=pd.Timestamp("2026-06-14")), \
             patch.object(umd, '_create_vnstock_client') as mock_client_fn, \
             patch.object(umd, 'fetch_symbols') as mock_fetch, \
             patch.object(umd, 'read_canonical') as mock_read_canon, \
             patch.object(umd, 'detect_price_anomalies') as mock_detect, \
             patch.object(umd, 'run_full_history_refetch') as mock_full_refetch, \
             patch.object(umd, 'validate_dataframe', return_value=(True, [])), \
             patch.object(umd, 'atomic_write_with_backup') as mock_write:

            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client

            new_data = _make_new_data("BAD1", 10000.0, n_days=3)
            mock_fetch.return_value = (new_data, {"fetched": 1, "empty": 0, "errors": 0, "rows": 3, "total_symbols": 1})

            canon = _make_canonical_with_boundary("BAD1", 50000.0)
            mock_read_canon.return_value = canon

            anomaly = {
                "symbol": "BAD1", "classification": "PRICE_JUMP",
                "return_pct": -80.0, "exchange": "HOSE",
                "canon_close": 50000.0, "price_ratio": 0.2,
                "volume_ratio": 1.0, "date": "2026-06-16",
                "diff_pct": 80.0, "overlap_rows": 3, "mismatch_rows": 3,
                "reason": "shared-date close mismatch > 0.10% on 2026-06-16",
            }
            mock_detect.return_value = [anomaly]

            refetched = _make_ohlcv("BAD1", pd.bdate_range("2015-01-02", periods=60), 49000.0)
            mock_full_refetch.return_value = (refetched, {
                "targets": 1, "success": 1, "failed": 0,
                "details": [{"symbol": "BAD1", "status": "success", "rows": 60}],
            })
            mock_write.return_value = Path("/fake/output.parquet")

            result = umd.run_updater(
                canonical_path=Path("/fake/canonical.parquet"),
                skip_refetch=False,
            )

            mock_detect.assert_called_once()
            mock_full_refetch.assert_called_once()
            assert result.get("anomalies_detected") == 1
            assert result.get("refetch_stats", {}).get("targets") == 0
            assert result.get("full_history_refetch_stats", {}).get("success") == 1


# ---------------------------------------------------------------------------
# 5. CLI --no-refetch flag
# ---------------------------------------------------------------------------

class TestCLI:

    def test_no_refetch_flag_parsed(self):
        """--no-refetch should be parsed and passed through."""
        args = umd.parse_args(["--no-refetch", "--dry-run"])
        assert args.no_refetch is True
        assert args.dry_run is True

    def test_no_refetch_default_false(self):
        """Default: --no-refetch is False (refetch enabled)."""
        args = umd.parse_args([])
        assert args.no_refetch is False

    def test_main_passes_skip_refetch(self):
        """main() should pass skip_refetch to run_updater."""
        with patch.object(umd, 'run_updater', return_value={"status": "ok"}) as mock_run:
            umd.main(["--no-refetch", "--dry-run"])
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["skip_refetch"] is True

# ---------------------------------------------------------------------------
# 6. Constants sanity
# ---------------------------------------------------------------------------

class TestConstants:

    def test_thresholds_defined(self):
        assert umd.PRICE_JUMP_THRESHOLD > 0
        assert umd.SPLIT_RATIO_LOW > 0
        assert umd.SPLIT_RATIO_HIGH > umd.SPLIT_RATIO_LOW
        assert umd.VOLUME_SPIKE_SPLIT > 0
        assert umd.REFETCH_LOOKBACK_DAYS == 15
        assert umd.MAX_REFETCH_SYMBOLS > 0

    def test_overlap_constants_defined(self):
        """Overlap check constants should be sensible."""
        assert umd.OVERLAP_PRICE_TOLERANCE == 0.001
        assert umd.OVERLAP_MIN_ROWS == 1
        assert umd.OVERLAP_PASS_RATIO == 1.0

    def test_price_jump_above_vn_limit(self):
        """Threshold should be well above Vietnam ±7% daily limit."""
        assert umd.PRICE_JUMP_THRESHOLD > 0.10  # at least 10%


# ---------------------------------------------------------------------------
# 7. check_overlap_consistency
# ---------------------------------------------------------------------------

class TestCheckOverlapConsistency:

    def test_no_canonical_passes(self):
        """No canonical data → overlap check passes (nothing to compare)."""
        ref = _make_ohlcv("AAA", pd.bdate_range("2026-04-01", periods=10), 50000.0)
        result = umd.check_overlap_consistency(ref, None, "AAA")
        assert result["passed"] is True
        assert result["overlap_rows"] == 0

    def test_no_overlap_dates_passes(self):
        """Non-overlapping date ranges → passes."""
        canon = _make_ohlcv("BBB", pd.bdate_range("2026-01-01", periods=20), 50000.0)
        ref = _make_ohlcv("BBB", pd.bdate_range("2026-06-01", periods=10), 50000.0)
        result = umd.check_overlap_consistency(ref, canon, "BBB")
        assert result["passed"] is True
        assert result["overlap_rows"] == 0

    def test_matching_overlap_passes(self):
        """Identical prices on overlapping dates → passes with high match ratio."""
        dates = pd.bdate_range("2026-04-01", periods=20)
        canon = _make_ohlcv("CCC", dates, 50000.0)
        # Refetched covers same dates + extra new dates, same prices
        ref_dates = pd.bdate_range("2026-04-01", periods=30)
        ref = _make_ohlcv("CCC", ref_dates, 50000.0)
        result = umd.check_overlap_consistency(ref, canon, "CCC")
        assert result["passed"] is True
        assert result["overlap_rows"] == 20
        assert result["match_ratio"] == 1.0
        # Trimmed should have only the new (non-overlapping) rows
        assert len(result["trimmed_df"]) == 10

    def test_mismatched_overlap_fails(self):
        """Different prices on overlapping dates → fails."""
        dates = pd.bdate_range("2026-04-01", periods=20)
        canon = _make_ohlcv("DDD", dates, 50000.0)
        # Refetched same dates but with very different prices
        ref = _make_ohlcv("DDD", dates, 40000.0)  # 20% off
        result = umd.check_overlap_consistency(ref, canon, "DDD")
        assert result["passed"] is False
        assert "MISMATCH" in result["reason"]
        assert result["match_ratio"] < umd.OVERLAP_PASS_RATIO

    def test_partial_match_below_threshold(self):
        """If fewer than OVERLAP_PASS_RATIO match → fails."""
        dates = pd.bdate_range("2026-04-01", periods=10)
        canon = _make_ohlcv("EEE", dates, 50000.0)
        ref = _make_ohlcv("EEE", dates, 50000.0).copy()
        # Corrupt 5 out of 10 rows → 50% match < 80% threshold
        ref.loc[ref.index[:5], "close"] = 40000.0
        result = umd.check_overlap_consistency(ref, canon, "EEE")
        assert result["passed"] is False
        assert result["match_rows"] == 5

    def test_trimmed_df_removes_overlap(self):
        """Trimmed DataFrame should contain only non-overlapping dates."""
        canon_dates = pd.bdate_range("2026-04-01", periods=15)
        canon = _make_ohlcv("FFF", canon_dates, 50000.0)
        # Refetched: 15 overlap + 10 new
        ref_dates = pd.bdate_range("2026-04-01", periods=25)
        ref = _make_ohlcv("FFF", ref_dates, 50000.0)
        result = umd.check_overlap_consistency(ref, canon, "FFF")
        assert result["passed"] is True
        trimmed = result["trimmed_df"]
        assert len(trimmed) == 10
        # All trimmed dates should be AFTER canonical max
        canon_max = pd.to_datetime(canon["date"]).max()
        assert (pd.to_datetime(trimmed["date"]) > canon_max).all()

    def test_symbol_not_in_canonical_passes(self):
        """Symbol present in refetched but not canonical → passes."""
        canon = _make_ohlcv("OLD", pd.bdate_range("2026-04-01", periods=10), 50000.0)
        ref = _make_ohlcv("NEW", pd.bdate_range("2026-04-01", periods=10), 30000.0)
        result = umd.check_overlap_consistency(ref, canon, "NEW")
        assert result["passed"] is True

    def test_single_shared_row_mismatch_fails(self):
        """Direct overlap check should fail on the first shared mismatch."""
        canon = _make_ohlcv("GGG", pd.bdate_range("2026-04-01", periods=1), 50000.0)
        ref_dates = pd.bdate_range("2026-04-01", periods=10)
        ref = _make_ohlcv("GGG", ref_dates, 40000.0)
        result = umd.check_overlap_consistency(ref, canon, "GGG")
        assert result["passed"] is False
        assert result["overlap_rows"] == 1
        assert len(result["trimmed_df"]) == 9

    def test_canonical_max_date_reported(self):
        """canonical_max should be populated when symbol is in canonical."""
        dates = pd.bdate_range("2026-04-01", periods=10)
        canon = _make_ohlcv("HHH", dates, 50000.0)
        ref = _make_ohlcv("HHH", pd.bdate_range("2026-04-01", periods=15), 50000.0)
        result = umd.check_overlap_consistency(ref, canon, "HHH")
        assert result["canonical_max"] is not None
        assert result["canonical_max"] == str(dates[-1].date())


# ---------------------------------------------------------------------------
# 8. run_targeted_refetch with overlap check integration
# ---------------------------------------------------------------------------

class TestRefetchWithOverlapCheck:

    def test_refetch_with_matching_overlap_succeeds(self):
        """Re-fetch with matching overlap → accepted, overlap trimmed."""
        canon_dates = pd.bdate_range("2026-03-01", periods=40)
        canon = _make_ohlcv("GOOD1", canon_dates, 50000.0)
        canon_max_date = canon_dates[-1]

        # Re-fetched data: overlaps canonical tail + extends beyond
        # 49980 is 0.04% off 50000 → within 0.1% OVERLAP_PRICE_TOLERANCE
        ref_dates = pd.bdate_range("2026-04-01", periods=50)
        ref_df = _make_ohlcv("GOOD1", ref_dates, 49980.0)

        anomalies = [
            {"symbol": "GOOD1", "classification": "PRICE_JUMP",
             "return_pct": -30.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": str(canon_max_date),
             "price_ratio": 0.7, "volume_ratio": 1.0},
        ]
        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"GOOD1": "HOSE"}, "2026-06-18",
                canonical_df=canon,
            )
        assert stats["success"] == 1
        assert stats["overlap_checks"] == 1
        assert stats["overlap_passed"] == 1
        detail = stats["details"][0]
        assert detail["status"] == "success"
        assert detail["overlap_rows"] > 0

    def test_refetch_with_mismatched_overlap_rejected(self):
        """Re-fetch with mismatched overlap → queued for full-history refetch."""
        canon_dates = pd.bdate_range("2026-03-01", periods=40)
        canon = _make_ohlcv("BAD_OV", canon_dates, 50000.0)
        canon_max_date = canon_dates[-1]

        # 49000 is 2% off 50000 → passes boundary (< 25%) but fails overlap (> 0.1%)
        ref_dates = pd.bdate_range("2026-04-01", periods=50)
        ref_df = _make_ohlcv("BAD_OV", ref_dates, 49000.0)

        anomalies = [
            {"symbol": "BAD_OV", "classification": "PRICE_JUMP",
             "return_pct": -2.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": str(canon_max_date),
             "price_ratio": 0.98, "volume_ratio": 1.0},
        ]
        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"BAD_OV": "HOSE"}, "2026-06-18",
                canonical_df=canon,
            )
        assert stats["overlap_failed"] == 1
        # Overlap mismatch no longer counts as hard-fail; queued for full refetch
        assert len(stats["needs_full_refetch"]) == 1
        assert stats["needs_full_refetch"][0]["symbol"] == "BAD_OV"
        detail = stats["details"][0]
        assert detail["status"] == "overlap_mismatch_queued_full_refetch"
        assert df.empty

    def test_refetch_no_canonical_still_works(self):
        """Re-fetch without canonical_df → overlap check skipped, still works."""
        ref_dates = pd.bdate_range("2026-04-01", periods=30)
        ref_df = _make_ohlcv("NC1", ref_dates, 49000.0)

        anomalies = [
            {"symbol": "NC1", "classification": "PRICE_JUMP",
             "return_pct": -40.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": "2026-03-31",
             "price_ratio": 0.6, "volume_ratio": 1.0},
        ]
        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"NC1": "HOSE"}, "2026-06-18",
                canonical_df=None,
            )
        assert stats["success"] == 1
        assert stats["overlap_checks"] == 1
        assert stats["overlap_passed"] == 1

    def test_refetch_overlap_trims_all_rows(self):
        """If all re-fetched rows overlap with canonical → Stage 1 rejects.

        When re-fetched data covers only dates <= canonical max date,
        there are no rows after the boundary to validate.  Stage 1
        correctly treats this as anomalous (ref_boundary_close=None
        → new_ret=1.0 → still_anomalous).  The overlap check (Stage 2)
        is never reached.
        """
        dates = pd.bdate_range("2026-04-01", periods=10)
        canon = _make_ohlcv("ALL_OV", dates, 50000.0)
        canon_max_date = dates[-1]
        # Re-fetched covers exactly the same dates — no post-boundary rows
        ref_df = _make_ohlcv("ALL_OV", dates, 50000.0)

        anomalies = [
            {"symbol": "ALL_OV", "classification": "PRICE_JUMP",
             "return_pct": -30.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": str(canon_max_date),
             "price_ratio": 0.7, "volume_ratio": 1.0},
        ]
        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"ALL_OV": "HOSE"}, "2026-06-18",
                canonical_df=canon,
            )
        assert stats["failed"] == 1
        # Stage 1 rejects: no rows after canonical max date → boundary
        # close is None → new_ret defaults to 1.0 (100%) → still_anomalous
        assert stats["details"][0]["status"] == "still_anomalous"
        assert df.empty


# ---------------------------------------------------------------------------
# 9. Regression: Stage 1 boundary validation fix
#    Bug: iloc[0] of lookback window used instead of close at max_date + 1.
#    Fix: compare close at first trading day AFTER canonical max date.
# ---------------------------------------------------------------------------

def _make_ohlcv_varying(
    ticker: str,
    dates: pd.DatetimeIndex,
    close_before_boundary: float,
    close_after_boundary: float,
    boundary_date: pd.Timestamp,
    exchange: str = "HOSE",
    volume: int = 100000,
) -> pd.DataFrame:
    """Build a canonical-schema DataFrame with two close-price zones.

    Rows with date <= boundary_date get close_before_boundary.
    Rows with date > boundary_date get close_after_boundary.
    """
    closes = np.where(
        dates <= boundary_date,
        close_before_boundary,
        close_after_boundary,
    )
    n = len(dates)
    return pd.DataFrame({
        "ticker": ticker,
        "date": dates,
        "exchange": exchange,
        "open": closes * 0.99,
        "high": closes * 1.02,
        "low": closes * 0.98,
        "close": closes,
        "volume": np.full(n, volume, dtype=np.int64),
        "as_of": "2026-06-18 00:00:00",
        "available_at": dates + pd.Timedelta(days=1),
        "source": "vnstock_vci",
        "price_scale": "VND",
        "adjusted": "backward_adjusted",
        "rebuild_date": "2026-06-18",
    })


def _make_ohlcv_three_zone(
    ticker: str,
    dates: pd.DatetimeIndex,
    close_pre_canonical: float,
    close_overlap: float,
    close_post_canonical: float,
    canon_start_date: pd.Timestamp,
    canon_end_date: pd.Timestamp,
    exchange: str = "HOSE",
    volume: int = 100000,
) -> pd.DataFrame:
    """Build a canonical-schema DataFrame with three close-price zones.

    Zone 1 (date < canon_start_date):  close_pre_canonical   — iloc[0] sees this
    Zone 2 (canon_start <= date <= canon_end): close_overlap — matches canonical
    Zone 3 (date > canon_end_date):    close_post_canonical  — boundary close

    This is used to regression-test the iloc[0] bug: the old code used
    iloc[0] (Zone 1 close) for boundary validation instead of the first
    post-canonical close (Zone 3).  Zone 2 must match canonical so the
    overlap check passes.
    """
    closes = np.where(
        dates < canon_start_date,
        close_pre_canonical,
        np.where(
            dates <= canon_end_date,
            close_overlap,
            close_post_canonical,
        ),
    )
    n = len(dates)
    return pd.DataFrame({
        "ticker": ticker,
        "date": dates,
        "exchange": exchange,
        "open": closes * 0.99,
        "high": closes * 1.02,
        "low": closes * 0.98,
        "close": closes,
        "volume": np.full(n, volume, dtype=np.int64),
        "as_of": "2026-06-18 00:00:00",
        "available_at": dates + pd.Timedelta(days=1),
        "source": "vnstock_vci",
        "price_scale": "VND",
        "adjusted": "backward_adjusted",
        "rebuild_date": "2026-06-18",
    })


class TestStage1BoundaryValidationFix:
    """Regression tests for the Stage 1 boundary validation bug.

    OLD BEHAVIOR (buggy):
        ref_first_close = df.sort_values("date").iloc[0]["close"]
        → uses close at earliest lookback date (e.g. 90 days ago)

    NEW BEHAVIOR (fixed):
        → uses close at first trading day AFTER canonical max date
        → correctly validates the actual boundary between old and new data
    """

    def test_false_rejection_prevented_boundary_ok_lookback_different(self):
        """REGRESSION: iloc[0] close differs from canonical but boundary close is fine.

        Old buggy code used iloc[0] (close=30000 at lookback start) ->
        |30000-50000|/50000 = 40% > 25% -> falsely rejected as "still_anomalous".

        Fixed code uses boundary close (49000, 2% from 50000) -> passes Stage 1.

        Uses 3-zone data so the overlap check (Stage 2) also passes:
          Zone 1 (pre-canonical):  close=30000  -- iloc[0] sees this (old bug)
          Zone 2 (canonical overlap): close=50000 -- matches canonical exactly
          Zone 3 (post-canonical): close=49000  -- boundary close (2% off)
        """
        # Canonical: 2026-05-01 to 2026-06-01 (22 business days)
        canon_dates = pd.bdate_range("2026-05-01", periods=22)
        canon_start_date = canon_dates[0]
        canon_max_date = canon_dates[-1]
        canon = _make_ohlcv("FIX1", canon_dates, 50000.0)

        # Re-fetched: 90-day lookback with THREE price zones
        #   Zone 1: 2026-03-20 to 2026-04-30 (pre-canonical): close=30000
        #   Zone 2: 2026-05-01 to 2026-06-01 (overlap):       close=50000 (matches)
        #   Zone 3: 2026-06-02 to 2026-06-18 (post-canonical): close=49000
        ref_dates = pd.bdate_range("2026-03-20", "2026-06-18")
        ref_df = _make_ohlcv_three_zone(
            "FIX1", ref_dates,
            close_pre_canonical=30000.0,   # iloc[0] close (old bug)
            close_overlap=50000.0,         # matches canonical exactly
            close_post_canonical=49000.0,  # boundary close (2% off -> passes)
            canon_start_date=canon_start_date,
            canon_end_date=canon_max_date,
        )

        anomalies = [
            {"symbol": "FIX1", "classification": "PRICE_JUMP",
             "return_pct": -80.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": str(canon_max_date),
             "price_ratio": 0.2, "volume_ratio": 1.0},
        ]

        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"FIX1": "HOSE"}, "2026-06-18",
                canonical_df=canon,
            )

        # Fixed code: boundary close 49000 is 2% from 50000 -> passes Stage 1
        # Overlap zone matches canonical (50000) -> passes Stage 2
        assert stats["success"] == 1, (
            f"Expected success=1 but got {stats}. "
            f"Stage 1 should use boundary close (49000), not iloc[0] close (30000)."
        )
        assert stats["failed"] == 0
        assert stats["details"][0]["status"] == "success"

    def test_false_acceptance_prevented_boundary_anomalous_lookback_ok(self):
        """REGRESSION: iloc[0] close is fine but boundary close is anomalous.

        Old buggy code used iloc[0] (close=49000 at lookback start) →
        |49000-50000|/50000 = 2% < 25% → falsely accepted.

        Fixed code uses boundary close (10000, 80% off) → correctly rejected.
        """
        # Canonical ends at ~2026-05-30
        canon_dates = pd.bdate_range("2026-05-01", periods=22)
        canon_max_date = canon_dates[-1]
        canon = _make_ohlcv("FIX2", canon_dates, 50000.0)

        # Re-fetched: TWO price zones (inverse of test above)
        #   2026-03-20 to canon_max_date: close=49000 (fine, 2% off)
        #   after canon_max_date: close=10000 (80% off → should FAIL)
        ref_dates = pd.bdate_range("2026-03-20", "2026-06-18")
        ref_df = _make_ohlcv_varying(
            "FIX2", ref_dates,
            close_before_boundary=49000.0,  # iloc[0] close (old bug accepts)
            close_after_boundary=10000.0,   # boundary close (should reject)
            boundary_date=canon_max_date,
        )

        anomalies = [
            {"symbol": "FIX2", "classification": "PRICE_JUMP",
             "return_pct": -80.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": str(canon_max_date),
             "price_ratio": 0.2, "volume_ratio": 1.0},
        ]

        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"FIX2": "HOSE"}, "2026-06-18",
                canonical_df=canon,
            )

        # Fixed code: boundary close 10000 is 80% from 50000 → still_anomalous
        assert stats["failed"] == 1, (
            f"Expected failed=1 but got {stats}. "
            f"Stage 1 should use boundary close (10000), not iloc[0] close (49000)."
        )
        assert stats["success"] == 0
        assert stats["details"][0]["status"] == "still_anomalous"

    def test_no_rows_after_canonical_max_date(self):
        """REGRESSION: Re-fetched data has no rows after canonical max date.

        All re-fetched dates are on or before canonical max date.
        Should be treated as anomalous (cannot validate boundary).
        """
        canon_dates = pd.bdate_range("2026-05-01", periods=22)
        canon_max_date = canon_dates[-1]
        canon = _make_ohlcv("FIX3", canon_dates, 50000.0)

        # Re-fetched data only covers dates BEFORE canonical max
        ref_dates = pd.bdate_range("2026-03-20", periods=30)
        # Ensure all ref dates are <= canon_max_date
        ref_dates = ref_dates[ref_dates <= canon_max_date]
        ref_df = _make_ohlcv("FIX3", ref_dates, 49000.0)

        anomalies = [
            {"symbol": "FIX3", "classification": "PRICE_JUMP",
             "return_pct": -40.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": str(canon_max_date),
             "price_ratio": 0.6, "volume_ratio": 1.0},
        ]

        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"FIX3": "HOSE"}, "2026-06-18",
                canonical_df=canon,
            )

        # No boundary data → treated as anomalous
        assert stats["failed"] == 1
        assert stats["details"][0]["status"] == "still_anomalous"
        assert df.empty

    def test_boundary_close_exactly_at_threshold(self):
        """Boundary close exactly at PRICE_JUMP_THRESHOLD should be rejected.

        |ret| >= 25% → still_anomalous (uses >=, not >).
        """
        canon_dates = pd.bdate_range("2026-05-01", periods=22)
        canon_max_date = canon_dates[-1]
        canon = _make_ohlcv("FIX4", canon_dates, 50000.0)

        # 37500 is exactly 25% below 50000 → >= threshold → reject
        ref_dates = pd.bdate_range("2026-03-20", "2026-06-18")
        ref_df = _make_ohlcv_varying(
            "FIX4", ref_dates,
            close_before_boundary=49000.0,
            close_after_boundary=37500.0,  # exactly 25% off
            boundary_date=canon_max_date,
        )

        anomalies = [
            {"symbol": "FIX4", "classification": "PRICE_JUMP",
             "return_pct": -50.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": str(canon_max_date),
             "price_ratio": 0.5, "volume_ratio": 1.0},
        ]

        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"FIX4": "HOSE"}, "2026-06-18",
                canonical_df=canon,
            )

        assert stats["failed"] == 1
        assert stats["details"][0]["status"] == "still_anomalous"

    def test_boundary_close_just_below_threshold_passes(self):
        """Boundary close just below threshold should pass Stage 1.

        |ret| < 25% → passes to overlap check.
        """
        canon_dates = pd.bdate_range("2026-05-01", periods=22)
        canon_max_date = canon_dates[-1]
        canon = _make_ohlcv("FIX5", canon_dates, 50000.0)

        # 38000 is 24% below 50000 → < threshold → passes Stage 1
        ref_dates = pd.bdate_range("2026-03-20", "2026-06-18")
        ref_df = _make_ohlcv_varying(
            "FIX5", ref_dates,
            close_before_boundary=30000.0,  # iloc[0] very different
            close_after_boundary=38000.0,   # 24% off, < 25% threshold
            boundary_date=canon_max_date,
        )

        anomalies = [
            {"symbol": "FIX5", "classification": "PRICE_JUMP",
             "return_pct": -50.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": str(canon_max_date),
             "price_ratio": 0.5, "volume_ratio": 1.0},
        ]

        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"FIX5": "HOSE"}, "2026-06-18",
                canonical_df=canon,
            )

        # Should pass Stage 1 (24% < 25% threshold)
        detail = stats["details"][0]
        assert detail["status"] != "still_anomalous", (
            f"Expected to pass Stage 1 but got '{detail['status']}'. "
            f"24% return should be below 25% threshold."
        )


# ---------------------------------------------------------------------------
# 10. run_full_history_refetch
# ---------------------------------------------------------------------------

class TestRunFullHistoryRefetch:

    def test_empty_input_returns_empty(self):
        """No symbols to refetch → empty result."""
        client = MagicMock()
        df, stats = umd.run_full_history_refetch(client, [], {}, "2026-06-18")
        assert df.empty
        assert stats["targets"] == 0

    def test_successful_full_refetch(self):
        """Successful full-history refetch returns data from 2015-01-01."""
        full_dates = pd.bdate_range("2015-01-02", periods=2800)
        full_df = _make_ohlcv("SPLIT1", full_dates, 50000.0)

        symbols = [{"symbol": "SPLIT1", "exchange": "HOSE", "reason": "phase shift"}]
        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=full_df):
            df, stats = umd.run_full_history_refetch(
                client, symbols, {"SPLIT1": "HOSE"}, "2026-06-18",
            )
        assert stats["success"] == 1
        assert stats["failed"] == 0
        assert not df.empty
        assert df["ticker"].iloc[0] == "SPLIT1"
        # Should start near 2015-01-01
        assert df["date"].min() < pd.Timestamp("2015-02-01")

    def test_failed_full_refetch_empty_result(self):
        """Empty fetch result → counted as failed."""
        symbols = [{"symbol": "FAIL1", "exchange": "HOSE", "reason": "phase shift"}]
        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=pd.DataFrame()):
            df, stats = umd.run_full_history_refetch(
                client, symbols, {"FAIL1": "HOSE"}, "2026-06-18",
            )
        assert stats["failed"] == 1
        assert stats["success"] == 0
        assert df.empty

    def test_multiple_symbols_mixed_results(self):
        """Mix of success and failure across multiple symbols."""
        full_dates = pd.bdate_range("2015-01-02", periods=2000)
        good_df = _make_ohlcv("GOOD", full_dates, 50000.0)

        symbols = [
            {"symbol": "GOOD", "exchange": "HOSE", "reason": "split"},
            {"symbol": "BAD", "exchange": "HNX", "reason": "dividend"},
        ]

        def mock_fetch(client, sym, start, end, exchange):
            if sym == "GOOD":
                return good_df.copy()
            return pd.DataFrame()

        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', side_effect=mock_fetch):
            df, stats = umd.run_full_history_refetch(
                client, symbols, {"GOOD": "HOSE", "BAD": "HNX"}, "2026-06-18",
            )
        assert stats["success"] == 1
        assert stats["failed"] == 1
        assert df["ticker"].unique().tolist() == ["GOOD"]


# ---------------------------------------------------------------------------
# 11. 0.1% overlap threshold sensitivity
# ---------------------------------------------------------------------------

class TestOverlapThresholdSensitivity:

    def test_detects_0_2_percent_discrepancy(self):
        """A 0.2% price discrepancy should FAIL at 0.1% tolerance.

        This would have PASSED at the old 0.5% tolerance.  Detecting these
        small mismatches catches small stock splits and cash dividends.
        """
        dates = pd.bdate_range("2026-04-01", periods=20)
        canon = _make_ohlcv("SMALL", dates, 50000.0)
        # 49900 is 0.2% off 50000 → fails at 0.1%
        ref = _make_ohlcv("SMALL", dates, 49900.0)
        result = umd.check_overlap_consistency(ref, canon, "SMALL")
        assert result["passed"] is False
        assert result["match_ratio"] == 0.0

    def test_passes_0_05_percent_discrepancy(self):
        """A 0.05% price discrepancy should PASS at 0.1% tolerance."""
        dates = pd.bdate_range("2026-04-01", periods=20)
        canon = _make_ohlcv("TINY", dates, 50000.0)
        # 49975 is 0.05% off 50000 → within 0.1%
        ref = _make_ohlcv("TINY", dates, 49975.0)
        result = umd.check_overlap_consistency(ref, canon, "TINY")
        assert result["passed"] is True
        assert result["match_ratio"] == 1.0

    def test_cash_dividend_detected(self):
        """Simulate a small cash dividend causing ~0.3% price shift.

        Before ex-date: 50000 → after adjustment: 49850 (0.3% off).
        This should be caught by the 0.1% overlap check.
        """
        dates = pd.bdate_range("2026-04-01", periods=20)
        canon = _make_ohlcv("DIV1", dates, 50000.0)
        ref = _make_ohlcv("DIV1", dates, 49850.0)  # 0.3% off
        result = umd.check_overlap_consistency(ref, canon, "DIV1")
        assert result["passed"] is False

    def test_small_split_detected(self):
        """Simulate a small 10:11 bonus share causing ~9% price shift.

        This would already be caught at 0.5%, but verifies 0.1% also catches it.
        """
        dates = pd.bdate_range("2026-04-01", periods=20)
        canon = _make_ohlcv("BONUS1", dates, 50000.0)
        ref = _make_ohlcv("BONUS1", dates, 45454.0)  # ~9.1% off
        result = umd.check_overlap_consistency(ref, canon, "BONUS1")
        assert result["passed"] is False

    def test_overlap_tolerance_constant_is_0_1_percent(self):
        """OVERLAP_PRICE_TOLERANCE should be exactly 0.001 (0.1%)."""
        assert umd.OVERLAP_PRICE_TOLERANCE == 0.001


# ---------------------------------------------------------------------------
# 12. Full-history refetch: delete-and-overwrite integration
# ---------------------------------------------------------------------------

class TestFullHistoryDeleteAndOverwrite:

    def test_overlap_mismatch_queues_full_refetch(self):
        """Overlap mismatch in targeted refetch should queue for full history."""
        canon_dates = pd.bdate_range("2026-03-01", periods=40)
        canon = _make_ohlcv("PHASE1", canon_dates, 50000.0)
        canon_max_date = canon_dates[-1]

        # 48000 is 4% off → fails overlap at 0.1%
        ref_dates = pd.bdate_range("2026-04-01", periods=50)
        ref_df = _make_ohlcv("PHASE1", ref_dates, 48000.0)

        anomalies = [
            {"symbol": "PHASE1", "classification": "PRICE_JUMP",
             "return_pct": -4.0, "exchange": "HOSE",
             "canon_close": 50000.0, "canon_date": str(canon_max_date),
             "price_ratio": 0.96, "volume_ratio": 1.0},
        ]
        client = MagicMock()
        with patch.object(umd, 'fetch_one_symbol', return_value=ref_df):
            df, stats = umd.run_targeted_refetch(
                client, anomalies, {"PHASE1": "HOSE"}, "2026-06-18",
                canonical_df=canon,
            )
        assert len(stats["needs_full_refetch"]) == 1
        assert stats["needs_full_refetch"][0]["symbol"] == "PHASE1"

    def test_run_updater_deletes_old_and_overwrites(self):
        """Integration: run_updater deletes old canonical for phase-shifted symbols
        and overwrites with full-history refetched data."""
        with patch.object(umd, 'load_universe_from_json',
                          return_value={"hsx": ["SYM1"], "hnx": []}), \
             patch.object(umd, 'read_canonical_max_date',
                          return_value=pd.Timestamp("2026-06-14")), \
             patch.object(umd, '_create_vnstock_client') as mock_client_fn, \
             patch.object(umd, 'fetch_symbols') as mock_fetch, \
             patch.object(umd, 'read_canonical') as mock_read_canon, \
             patch.object(umd, 'detect_price_anomalies') as mock_detect, \
             patch.object(umd, 'run_full_history_refetch') as mock_full, \
             patch.object(umd, 'validate_dataframe', return_value=(True, [])), \
             patch.object(umd, 'atomic_write_with_backup') as mock_write:

            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client

            new_data = _make_new_data("SYM1", 48000.0, n_days=3)
            mock_fetch.return_value = (
                new_data,
                {"fetched": 1, "empty": 0, "errors": 0, "rows": 3, "total_symbols": 1},
            )

            canon = _make_canonical_with_boundary("SYM1", 50000.0)
            mock_read_canon.return_value = canon

            anomaly = {
                "symbol": "SYM1", "classification": "PRICE_JUMP",
                "return_pct": -4.0, "exchange": "HOSE",
                "canon_close": 50000.0, "price_ratio": 0.96,
                "volume_ratio": 1.0, "date": "2026-06-16",
                "diff_pct": 4.0, "overlap_rows": 10, "mismatch_rows": 10,
                "reason": "overlap mismatch",
            }
            mock_detect.return_value = [anomaly]

            # Full history refetch succeeds
            full_dates = pd.bdate_range("2015-01-02", periods=2800)
            full_df = _make_ohlcv("SYM1", full_dates, 50000.0)
            mock_full.return_value = (full_df, {
                "targets": 1, "success": 1, "failed": 0,
                "details": [{"symbol": "SYM1", "status": "success",
                             "rows": 2800}],
            })
            mock_write.return_value = Path("/fake/output.parquet")

            result = umd.run_updater(
                canonical_path=Path("/fake/canonical.parquet"),
                skip_refetch=False,
            )

            # Verify full-history refetch was called
            mock_full.assert_called_once()
            full_call_args = mock_full.call_args
            assert full_call_args[0][1][0]["symbol"] == "SYM1"

            # Verify write was called (data was written)
            mock_write.assert_called_once()

            # Verify the result includes full_history_refetch_stats
            assert "full_history_refetch_stats" in result
            assert result["full_history_refetch_stats"]["success"] == 1
            assert result["full_history_symbols"] == ["SYM1"]

            # Verify the written DataFrame does NOT contain old canonical data
            # (it should only have the full-history refetched data)
            written_df = mock_write.call_args[0][0]
            sym1_data = written_df[written_df["ticker"] == "SYM1"]
            assert not sym1_data.empty
            # Full history should start near 2015
            assert sym1_data["date"].min() < pd.Timestamp("2015-02-01")

    def test_full_history_start_constant(self):
        """FULL_HISTORY_START should be 2015-01-01."""
        assert umd.FULL_HISTORY_START == "2015-01-01"

    def test_needs_full_refetch_key_in_stats(self):
        """run_targeted_refetch stats should include needs_full_refetch key."""
        anomalies = [
            {"symbol": "X", "classification": "SPLIT_LIKE",
             "return_pct": -50.0, "exchange": "HOSE",
             "canon_close": 50000.0},
        ]
        client = MagicMock()
        df, stats = umd.run_targeted_refetch(
            client, anomalies, {"X": "HOSE"}, "2026-06-18"
        )
        assert "needs_full_refetch" in stats
        assert stats["needs_full_refetch"] == []

    def test_run_updater_no_anomalies_no_full_refetch(self):
        """When no anomalies, full_refetch_stats should be zeroed out."""
        with patch.object(umd, 'load_universe_from_json',
                          return_value={"hsx": ["OK1"], "hnx": []}), \
             patch.object(umd, 'read_canonical_max_date',
                          return_value=pd.Timestamp("2026-06-17")), \
             patch.object(umd, '_create_vnstock_client') as mock_client_fn, \
             patch.object(umd, 'fetch_symbols') as mock_fetch, \
             patch.object(umd, 'read_canonical') as mock_read_canon, \
             patch.object(umd, 'detect_price_anomalies', return_value=[]), \
             patch.object(umd, 'validate_dataframe', return_value=(True, [])), \
             patch.object(umd, 'atomic_write_with_backup') as mock_write:

            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            new_data = _make_new_data("OK1", 50000.0, n_days=1)
            mock_fetch.return_value = (
                new_data,
                {"fetched": 1, "empty": 0, "errors": 0, "rows": 1, "total_symbols": 1},
            )
            mock_read_canon.return_value = _make_canonical_with_boundary("OK1", 50000.0)
            mock_write.return_value = Path("/fake/output.parquet")

            result = umd.run_updater(
                canonical_path=Path("/fake/canonical.parquet"),
            )
            assert result.get("full_history_refetch_stats", {}).get("targets", 0) == 0
            assert result.get("full_history_symbols", []) == []
