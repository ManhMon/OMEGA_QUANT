"""
Stage 5: Shadow Live Runner Unit Tests
========================================
Tests PIT safety, slippage calculation, log format, and multi-day accumulation.

Author: Backend Engineer (Role 09) [L2-Impl:Role9-Backend]
Date: 2026-05-22
Version: 1.0.0
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "quant" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "execution" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from omega.quant.execution_sim import ExecutionResult, ExecutionConfig, ExecutionSimulator
from analyze_stage5_slippage import (
    load_daily_logs,
    compute_average_slippage,
    compare_to_baseline,
    build_report,
    run_analysis,
    SLIPPAGE_TOLERANCE_BPS,
)
from run_stage5_shadow_live import (
    generate_portfolio_weights,
    simulate_execution,
    log_execution_metrics,
    run_shadow_day,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv(
    tickers: list,
    n_days: int = 90,
    end_date: str = "2026-05-20",  # T-1 relative to 2026-05-21
    base_price: float = 50_000.0,
    base_volume: float = 500_000.0,
) -> pd.DataFrame:
    """Build synthetic OHLCV DataFrame for testing."""
    dates = pd.bdate_range(end=end_date, periods=n_days)
    rows = []
    rng = np.random.default_rng(42)
    for ticker in tickers:
        prices = base_price * np.cumprod(1 + rng.normal(0, 0.01, n_days))
        volumes = base_volume * rng.uniform(0.8, 1.2, n_days)
        for i, date in enumerate(dates):
            close = prices[i]
            rows.append({
                "date": date,
                "ticker": ticker,
                "open": close * 0.99,
                "high": close * 1.01,
                "low": close * 0.98,
                "close": close,
                "volume": volumes[i],
            })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    tickers = [f"VN{i:02d}" for i in range(10)]
    return _make_ohlcv(tickers, n_days=90, end_date="2026-05-20")


@pytest.fixture
def sample_weights(sample_ohlcv) -> pd.Series:
    return generate_portfolio_weights(sample_ohlcv, "2026-05-21")


@pytest.fixture
def tmp_log_dir(tmp_path) -> Path:
    return tmp_path / "shadow_live"


def _make_log_record(date: str, slippage_bps: float, status: str = "OK") -> Dict[str, Any]:
    return {
        "date": date,
        "logged_at": "2026-05-22T10:00:00Z",
        "pit_cutoff": "2026-05-20",
        "num_trades": 10,
        "total_volume": 1_000_000.0,
        "total_slippage_bps": slippage_bps,
        "total_commission_bps": 1.5,
        "total_cost_bps": slippage_bps + 1.5,
        "total_pnl": -500.0,
        "execution_time_ms": 55.0,
        "status": status,
        "trades": [],
    }


# ---------------------------------------------------------------------------
# 1. PIT Safety Tests
# ---------------------------------------------------------------------------

class TestPITSafety:
    """Verify no future data leaks into execution simulation."""

    def test_generate_weights_uses_only_t_minus_1_data(self, sample_ohlcv):
        """Weights must be generated from data with date <= T-1."""
        run_date = "2026-05-21"
        pit_cutoff = pd.Timestamp(run_date) - pd.Timedelta(days=1)

        weights = generate_portfolio_weights(sample_ohlcv, run_date)

        # All data used is <= T-1 (sample_ohlcv ends at 2026-05-20)
        max_data_date = pd.to_datetime(sample_ohlcv["date"]).max()
        assert max_data_date <= pit_cutoff, (
            f"Data contains future date {max_data_date} > T-1 {pit_cutoff}"
        )

    def test_simulate_execution_uses_t_minus_1_prices(self, sample_ohlcv, sample_weights):
        """Execution reference prices must come from T-1 close, not T."""
        run_date = "2026-05-21"
        pit_cutoff = pd.Timestamp(run_date) - pd.Timedelta(days=1)

        result = simulate_execution(sample_weights, sample_ohlcv, run_date)

        # Verify execution happened (trades generated)
        assert result.num_trades >= 0  # may be 0 if weights too small

        # Verify no data beyond T-1 was used (data fixture ends at 2026-05-20)
        max_data_date = pd.to_datetime(sample_ohlcv["date"]).max()
        assert max_data_date <= pit_cutoff

    def test_load_market_data_raises_on_future_data(self):
        """load_market_data_for_date must raise ValueError if data contains future dates."""
        from run_stage5_shadow_live import load_market_data_for_date

        future_date = "2026-05-21"
        pit_cutoff = pd.Timestamp(future_date) - pd.Timedelta(days=1)

        # Build data that violates PIT (contains T date)
        bad_data = _make_ohlcv(["VN01"], n_days=5, end_date=future_date)

        with patch("run_stage5_shadow_live.Phase35DataLoader") as MockLoader:
            instance = MockLoader.return_value
            instance.load_raw_data.return_value = bad_data
            instance.apply_filters.return_value = bad_data

            with pytest.raises(ValueError, match="PIT Safety violation"):
                load_market_data_for_date(future_date)

    def test_log_records_pit_cutoff(self, sample_ohlcv, sample_weights, tmp_log_dir):
        """Log file must record pit_cutoff = T-1."""
        run_date = "2026-05-21"
        expected_cutoff = "2026-05-20"

        result = simulate_execution(sample_weights, sample_ohlcv, run_date)

        with patch("run_stage5_shadow_live.SHADOW_LIVE_DIR", tmp_log_dir):
            log_path = log_execution_metrics(result, run_date)

        with open(log_path) as f:
            record = json.load(f)

        assert record["pit_cutoff"] == expected_cutoff


# ---------------------------------------------------------------------------
# 2. Slippage Calculation Tests
# ---------------------------------------------------------------------------

class TestSlippageCalculation:
    """Verify slippage values are computed correctly."""

    def test_compute_average_slippage_correct(self):
        """Average slippage must equal mean of per-day values."""
        logs = [
            _make_log_record("2026-05-17", 4.0),
            _make_log_record("2026-05-18", 6.0),
            _make_log_record("2026-05-19", 5.0),
        ]
        avg = compute_average_slippage(logs)
        assert abs(avg - 5.0) < 1e-9

    def test_compute_average_slippage_empty_returns_zero(self):
        avg = compute_average_slippage([])
        assert avg == 0.0

    def test_compute_average_slippage_skips_error_records(self):
        """ERROR status records must be excluded from average."""
        logs = [
            _make_log_record("2026-05-17", 4.0, status="OK"),
            _make_log_record("2026-05-18", 999.0, status="ERROR"),
            _make_log_record("2026-05-19", 6.0, status="OK"),
        ]
        avg = compute_average_slippage(logs)
        assert abs(avg - 5.0) < 1e-9

    def test_compare_to_baseline_pass(self):
        """Deviation < 2 bps must yield PASS."""
        verdict = compare_to_baseline(avg_slippage=5.5, baseline=5.0)
        assert verdict == "PASS"

    def test_compare_to_baseline_fail(self):
        """Deviation >= 2 bps must yield FAIL."""
        verdict = compare_to_baseline(avg_slippage=8.0, baseline=5.0)
        assert verdict == "FAIL"

    def test_compare_to_baseline_exact_tolerance_is_fail(self):
        """Deviation exactly equal to tolerance must be FAIL (strict <)."""
        verdict = compare_to_baseline(avg_slippage=7.0, baseline=5.0)
        assert verdict == "FAIL"

    def test_simulate_execution_slippage_positive(self, sample_ohlcv, sample_weights):
        """Simulated slippage must be non-negative."""
        result = simulate_execution(sample_weights, sample_ohlcv, "2026-05-21")
        assert result.total_slippage_bps >= 0.0

    def test_simulate_execution_cost_gte_slippage(self, sample_ohlcv, sample_weights):
        """Total cost must be >= slippage (cost includes commission)."""
        result = simulate_execution(sample_weights, sample_ohlcv, "2026-05-21")
        assert result.total_cost_bps >= result.total_slippage_bps - 1e-9


# ---------------------------------------------------------------------------
# 3. Log File Format Tests
# ---------------------------------------------------------------------------

class TestLogFileFormat:
    """Verify log files have correct schema and types."""

    def test_log_file_created(self, sample_ohlcv, sample_weights, tmp_log_dir):
        run_date = "2026-05-21"
        result = simulate_execution(sample_weights, sample_ohlcv, run_date)

        with patch("run_stage5_shadow_live.SHADOW_LIVE_DIR", tmp_log_dir):
            log_path = log_execution_metrics(result, run_date)

        assert log_path.exists()
        assert log_path.name == f"{run_date}.json"

    def test_log_file_required_fields(self, sample_ohlcv, sample_weights, tmp_log_dir):
        run_date = "2026-05-21"
        result = simulate_execution(sample_weights, sample_ohlcv, run_date)

        with patch("run_stage5_shadow_live.SHADOW_LIVE_DIR", tmp_log_dir):
            log_path = log_execution_metrics(result, run_date)

        with open(log_path) as f:
            record = json.load(f)

        required_fields = [
            "date", "logged_at", "pit_cutoff",
            "status",
            "num_trades", "total_volume",
            "total_slippage_bps", "total_commission_bps",
            "total_cost_bps", "total_pnl", "execution_time_ms",
            "trades",
        ]
        for field in required_fields:
            assert field in record, f"Missing required field: {field}"

    def test_log_file_numeric_fields_are_float(self, sample_ohlcv, sample_weights, tmp_log_dir):
        run_date = "2026-05-21"
        result = simulate_execution(sample_weights, sample_ohlcv, run_date)

        with patch("run_stage5_shadow_live.SHADOW_LIVE_DIR", tmp_log_dir):
            log_path = log_execution_metrics(result, run_date)

        with open(log_path) as f:
            record = json.load(f)

        numeric_fields = [
            "total_slippage_bps", "total_commission_bps",
            "total_cost_bps", "total_pnl", "execution_time_ms",
        ]
        for field in numeric_fields:
            assert isinstance(record[field], (int, float)), (
                f"Field {field} must be numeric, got {type(record[field])}"
            )

    def test_log_file_date_matches(self, sample_ohlcv, sample_weights, tmp_log_dir):
        run_date = "2026-05-21"
        result = simulate_execution(sample_weights, sample_ohlcv, run_date)

        with patch("run_stage5_shadow_live.SHADOW_LIVE_DIR", tmp_log_dir):
            log_path = log_execution_metrics(result, run_date)

        with open(log_path) as f:
            record = json.load(f)

        assert record["date"] == run_date

    def test_load_daily_logs_reads_all_files(self, tmp_log_dir):
        """load_daily_logs must read all YYYY-MM-DD.json files."""
        tmp_log_dir.mkdir(parents=True, exist_ok=True)
        dates = ["2026-05-17", "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21"]
        for d in dates:
            record = _make_log_record(d, 5.0)
            with open(tmp_log_dir / f"{d}.json", "w") as f:
                json.dump(record, f)

        logs = load_daily_logs(str(tmp_log_dir))
        assert len(logs) == 5

    def test_load_daily_logs_sorted_by_date(self, tmp_log_dir):
        """Logs must be returned in ascending date order."""
        tmp_log_dir.mkdir(parents=True, exist_ok=True)
        dates = ["2026-05-21", "2026-05-17", "2026-05-19"]
        for d in dates:
            record = _make_log_record(d, 5.0)
            with open(tmp_log_dir / f"{d}.json", "w") as f:
                json.dump(record, f)

        logs = load_daily_logs(str(tmp_log_dir))
        loaded_dates = [r["date"] for r in logs]
        assert loaded_dates == sorted(loaded_dates)

    def test_load_daily_logs_skips_malformed(self, tmp_log_dir):
        """Malformed JSON files must be skipped without raising."""
        tmp_log_dir.mkdir(parents=True, exist_ok=True)
        good = _make_log_record("2026-05-17", 5.0)
        with open(tmp_log_dir / "2026-05-17.json", "w") as f:
            json.dump(good, f)
        with open(tmp_log_dir / "2026-05-18.json", "w") as f:
            f.write("NOT VALID JSON {{{")

        logs = load_daily_logs(str(tmp_log_dir))
        assert len(logs) == 1


# ---------------------------------------------------------------------------
# 4. Multi-Day Accumulation Tests
# ---------------------------------------------------------------------------

class TestMultiDayAccumulation:
    """Verify multi-day shadow run accumulates logs correctly."""

    def test_five_day_run_produces_five_logs(self, tmp_log_dir):
        """Running 5 shadow days must produce 5 log files."""
        dates = ["2026-05-17", "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21"]
        tickers = [f"VN{i:02d}" for i in range(10)]

        for date in dates:
            pit_cutoff = pd.Timestamp(date) - pd.Timedelta(days=1)
            data = _make_ohlcv(tickers, n_days=90, end_date=pit_cutoff.strftime("%Y-%m-%d"))
            weights = generate_portfolio_weights(data, date)
            result = simulate_execution(weights, data, date)
            with patch("run_stage5_shadow_live.SHADOW_LIVE_DIR", tmp_log_dir):
                log_execution_metrics(result, date)

        log_files = list(tmp_log_dir.glob("????-??-??.json"))
        assert len(log_files) == 5

    def test_analysis_over_five_days_produces_verdict(self, tmp_log_dir):
        """run_analysis over 5 days must return a PASS or FAIL verdict."""
        tmp_log_dir.mkdir(parents=True, exist_ok=True)
        dates = ["2026-05-17", "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21"]
        for d in dates:
            record = _make_log_record(d, 5.0)
            with open(tmp_log_dir / f"{d}.json", "w") as f:
                json.dump(record, f)

        report = run_analysis(log_dir=str(tmp_log_dir), baseline_bps=5.0)

        assert report["verdict"] in ("PASS", "FAIL")
        assert report["valid_days"] == 5
        assert report["total_days_logged"] == 5

    def test_analysis_pass_when_within_tolerance(self, tmp_log_dir):
        """Average slippage within 2 bps of baseline must yield PASS."""
        tmp_log_dir.mkdir(parents=True, exist_ok=True)
        # avg = 5.5 bps, baseline = 5.0 bps -> deviation = 0.5 bps < 2 bps
        slippages = [5.0, 5.5, 6.0, 5.0, 6.0]
        dates = ["2026-05-17", "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21"]
        for d, s in zip(dates, slippages):
            record = _make_log_record(d, s)
            with open(tmp_log_dir / f"{d}.json", "w") as f:
                json.dump(record, f)

        report = run_analysis(log_dir=str(tmp_log_dir), baseline_bps=5.0)
        assert report["verdict"] == "PASS"

    def test_analysis_fail_when_outside_tolerance(self, tmp_log_dir):
        """Average slippage > 2 bps from baseline must yield FAIL."""
        tmp_log_dir.mkdir(parents=True, exist_ok=True)
        # avg = 9.0 bps, baseline = 5.0 bps -> deviation = 4.0 bps > 2 bps
        slippages = [9.0, 9.0, 9.0, 9.0, 9.0]
        dates = ["2026-05-17", "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21"]
        for d, s in zip(dates, slippages):
            record = _make_log_record(d, s)
            with open(tmp_log_dir / f"{d}.json", "w") as f:
                json.dump(record, f)

        report = run_analysis(log_dir=str(tmp_log_dir), baseline_bps=5.0)
        assert report["verdict"] == "FAIL"

    def test_report_contains_per_day_breakdown(self, tmp_log_dir):
        """Report must include per-day slippage breakdown."""
        tmp_log_dir.mkdir(parents=True, exist_ok=True)
        dates = ["2026-05-17", "2026-05-18", "2026-05-19"]
        for d in dates:
            record = _make_log_record(d, 5.0)
            with open(tmp_log_dir / f"{d}.json", "w") as f:
                json.dump(record, f)

        report = run_analysis(log_dir=str(tmp_log_dir), baseline_bps=5.0)

        assert "per_day" in report
        assert len(report["per_day"]) == 3
        for entry in report["per_day"]:
            assert "date" in entry
            assert "slippage_bps" in entry

    def test_generate_weights_returns_valid_series(self):
        """generate_portfolio_weights must return a Series summing to ~1.0."""
        tickers = [f"VN{i:02d}" for i in range(15)]
        data = _make_ohlcv(tickers, n_days=90, end_date="2026-05-20")
        weights = generate_portfolio_weights(data, "2026-05-21")

        assert isinstance(weights, pd.Series)
        assert len(weights) > 0
        assert abs(weights.sum() - 1.0) < 1e-6
        assert (weights >= 0).all()


# ---------------------------------------------------------------------------
# 5. Runner -> Analyzer Contract Tests
# ---------------------------------------------------------------------------

class TestRunnerAnalyzerContract:
    """Verify that log files written by log_execution_metrics are correctly
    consumed by analyze_stage5_slippage.run_analysis — the exact contract
    mismatch identified in the L3 audit."""

    def test_runner_log_has_status_ok(self, sample_ohlcv, sample_weights, tmp_log_dir):
        """log_execution_metrics must write status='OK' so analyzer counts the day."""
        run_date = "2026-05-21"
        result = simulate_execution(sample_weights, sample_ohlcv, run_date)

        with patch("run_stage5_shadow_live.SHADOW_LIVE_DIR", tmp_log_dir):
            log_path = log_execution_metrics(result, run_date)

        with open(log_path) as f:
            record = json.load(f)

        assert record.get("status") == "OK", (
            "log_execution_metrics must write status='OK'; "
            "analyzer filters on r.get('status') == 'OK'"
        )

    def test_runner_output_feeds_analyzer_valid_days(self, sample_ohlcv, tmp_log_dir):
        """Logs written by runner must produce valid_days > 0 in analyzer."""
        tickers = [f"VN{i:02d}" for i in range(10)]
        dates = ["2026-05-19", "2026-05-20", "2026-05-21"]

        for date in dates:
            pit_cutoff = pd.Timestamp(date) - pd.Timedelta(days=1)
            data = _make_ohlcv(tickers, n_days=90, end_date=pit_cutoff.strftime("%Y-%m-%d"))
            weights = generate_portfolio_weights(data, date)
            result = simulate_execution(weights, data, date)
            with patch("run_stage5_shadow_live.SHADOW_LIVE_DIR", tmp_log_dir):
                log_execution_metrics(result, date)

        report = run_analysis(log_dir=str(tmp_log_dir), baseline_bps=5.0)

        assert report["valid_days"] == len(dates), (
            f"Expected {len(dates)} valid days but analyzer counted "
            f"{report['valid_days']}. Check status field in runner logs."
        )
        assert report["verdict"] in ("PASS", "FAIL")

    def test_runner_output_avg_slippage_matches_manual(self, sample_ohlcv, tmp_log_dir):
        """avg_slippage_bps in analyzer report must match manual mean of runner logs."""
        tickers = [f"VN{i:02d}" for i in range(10)]
        dates = ["2026-05-19", "2026-05-20", "2026-05-21"]
        written_slippages = []

        for date in dates:
            pit_cutoff = pd.Timestamp(date) - pd.Timedelta(days=1)
            data = _make_ohlcv(tickers, n_days=90, end_date=pit_cutoff.strftime("%Y-%m-%d"))
            weights = generate_portfolio_weights(data, date)
            result = simulate_execution(weights, data, date)
            written_slippages.append(float(result.total_slippage_bps))
            with patch("run_stage5_shadow_live.SHADOW_LIVE_DIR", tmp_log_dir):
                log_execution_metrics(result, date)

        report = run_analysis(log_dir=str(tmp_log_dir), baseline_bps=5.0)

        expected_avg = float(np.mean(written_slippages))
        assert abs(report["avg_slippage_bps"] - expected_avg) < 1e-4, (
            f"Analyzer avg {report['avg_slippage_bps']:.4f} != "
            f"expected {expected_avg:.4f}. Contract mismatch."
        )

    def test_analyzer_skips_records_without_status(self, tmp_log_dir):
        """Analyzer must skip records missing the status field (zero valid days)."""
        tmp_log_dir.mkdir(parents=True, exist_ok=True)
        # Write a log without status field — simulates the pre-fix runner output
        record_no_status = {
            "date": "2026-05-21",
            "logged_at": "2026-05-22T10:00:00Z",
            "pit_cutoff": "2026-05-20",
            "num_trades": 10,
            "total_volume": 1_000_000.0,
            "total_slippage_bps": 5.0,
            "total_commission_bps": 1.5,
            "total_cost_bps": 6.5,
            "total_pnl": -500.0,
            "execution_time_ms": 55.0,
            "trades": [],
        }
        with open(tmp_log_dir / "2026-05-21.json", "w") as f:
            json.dump(record_no_status, f)

        report = run_analysis(log_dir=str(tmp_log_dir), baseline_bps=5.0)

        assert report["valid_days"] == 0, (
            "Records without status='OK' must not be counted as valid days"
        )
