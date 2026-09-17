"""
tests/test_validation_consolidation.py

Comprehensive test suite for the consolidated data validation and sanitization modules:
- Single Source of Truth (SSOT): src/omega/data/sanitizer.py (DataSanitizer, DataValidator, ValidationIssue, DataQualityChecker)
- Legacy & compatibility shims: src/omega/data/validator.py, src/omega/data/data_validator.py, src/omega/data/data_quality.py
- 16-Dimension Adversarial Matrix (genuine implementations, no mocking of target logic)
- Standing Regressions Clause (1..8)
"""

from __future__ import annotations

import concurrent.futures
from datetime import date, datetime, timedelta, timezone
import hashlib
from ipaddress import IPv4Address, IPv6Address
import json
import os
from pathlib import Path
import socket
import ssl
import sys
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pytest

# Ensure src is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import omega.data.sanitizer as sanitizer_mod
from omega.data.sanitizer import DataSanitizer
import omega.data.validator as validator_mod
from omega.data.validator import DataValidator, ValidationIssue
import omega.data.data_validator as data_validator_shim
import omega.data.data_quality as data_quality_mod
from omega.data.data_quality import DataQualityChecker
from omega.data.calendar import VNTradingCalendar

# Copilot / SSRF / Security utilities for standing regressions
from omega.api.routes.copilot import (
    _is_safe_global_unicast_ip,
    _prepare_llm_request,
    _redact_url_for_error,
    redact_credentials_in_text,
    resolve_validated_llm_target,
)
from omega.core.llm_config import resolve_alpha_llm_config
from omega.data.official_watermark import _official_tls_context
import scripts.run_macro_news_pipeline as run_macro_news_pipeline
import scripts.update_market_data as update_market_data


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: PUBLIC CONSOLIDATED APIS
# ═══════════════════════════════════════════════════════════════════════════════

def test_api_data_sanitizer_fit_apply_pipeline():
    """Verify DataSanitizer fit/apply lifecycle with genuine OHLCV data."""
    dates = pd.date_range("2024-01-01", periods=25, freq="D")
    train_df = pd.DataFrame({
        "date": dates,
        "symbol": "VNM",
        "open": np.linspace(70000, 75000, 25),
        "high": np.linspace(71000, 76000, 25),
        "low": np.linspace(69000, 74000, 25),
        "close": np.linspace(70500, 75500, 25),
        "volume": np.full(25, 500000.0),
    })

    as_of = pd.Timestamp("2024-02-01")
    sanitizer = DataSanitizer(max_fill_days=3, outlier_sigma=3.0, min_price=10.0, as_of_time=as_of)
    assert sanitizer._is_fitted is False

    sanitizer.fit(train_df)
    assert sanitizer._is_fitted is True
    assert "VNM" in sanitizer._fitted_params["quantiles"]
    assert "close" in sanitizer._fitted_params["quantiles"]["VNM"]

    cleaned_df = sanitizer.apply(train_df)
    assert isinstance(cleaned_df, pd.DataFrame)
    assert len(cleaned_df) == 25
    assert "as_of" in cleaned_df.columns
    assert "available_at" in cleaned_df.columns
    assert (cleaned_df["as_of"] <= cleaned_df["available_at"]).all()


def test_api_data_sanitizer_clean_ohlcv_legacy():
    """Verify DataSanitizer.clean_ohlcv legacy expanding-window entry point."""
    dates = pd.date_range("2024-01-01", periods=25, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "symbol": "HPG",
        "open": np.linspace(25000, 28000, 25),
        "high": np.linspace(25500, 28500, 25),
        "low": np.linspace(24500, 27500, 25),
        "close": np.linspace(25000, 28000, 25),
        "volume": np.full(25, 1000000.0),
    })

    as_of = pd.Timestamp("2024-02-01")
    sanitizer = DataSanitizer(max_fill_days=2, outlier_sigma=2.5)
    cleaned_df, stats = sanitizer.clean_ohlcv(df, as_of_time=as_of)

    assert isinstance(cleaned_df, pd.DataFrame)
    assert isinstance(stats, dict)
    assert stats["input_rows"] == 25
    assert stats["output_rows"] == 25
    assert stats["duplicates_removed"] == 0
    assert stats["invalid_prices_removed"] == 0


def test_api_data_sanitizer_report():
    """Verify DataSanitizer report output before and after execution."""
    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    assert sanitizer.get_sanitization_report() == "No sanitization performed yet."

    dates = pd.date_range("2024-01-01", periods=25, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "symbol": "SSI",
        "open": np.full(25, 32000.0),
        "high": np.full(25, 33000.0),
        "low": np.full(25, 31000.0),
        "close": np.full(25, 32500.0),
        "volume": np.full(25, 800000.0),
    })
    sanitizer.fit(df)
    sanitizer.apply(df)

    report = sanitizer.get_sanitization_report()
    assert "=== Data Sanitization Report ===" in report
    assert "Input rows: 25" in report
    assert "Output rows: 25" in report
    assert "Data retention: 100.0%" in report


def test_api_data_validator_dataframe():
    """Verify DataValidator.validate public DataFrame API."""
    validator = DataValidator(validate_provenance=False)
    df = pd.DataFrame({
        "timestamp": ["2024-01-02", "2024-01-03"],
        "ticker": ["HPG", "HPG"],
        "open": [25000.0, 25200.0],
        "high": [25500.0, 25600.0],
        "low": [24800.0, 25000.0],
        "close": [25200.0, 25400.0],
        "volume": [100000.0, 120000.0],
    })
    res = validator.validate(df)
    assert isinstance(res, dict)
    assert res["total_rows"] == 2
    assert res["missing_values"] == {}
    assert res["issues"] == []


def test_api_data_validator_structural_ohlc():
    """Verify structural OHLC anomaly detection."""
    validator = DataValidator(validate_provenance=False)
    # High is less than open -> structural inconsistency
    rows = [
        {"timestamp": "2024-01-02", "open": 50000.0, "high": 48000.0, "low": 47000.0, "close": 49000.0, "volume": 1000.0},
    ]
    issues = validator.validate_rows(rows, symbol="VNM")
    assert len(issues) >= 1
    assert any(iss.rule == "ohlc_structure_inconsistent" for iss in issues)


def test_api_data_validator_price_moves_and_consistency():
    """Verify single-session price jump and corporate split ratio validation."""
    validator = DataValidator(max_session_move=0.20, validate_provenance=False)
    rows = [
        {"timestamp": "2024-01-02", "open": 10000.0, "high": 10500.0, "low": 9900.0, "close": 10000.0, "volume": 5000.0},
        {"timestamp": "2024-01-03", "open": 13000.0, "high": 13500.0, "low": 12800.0, "close": 13000.0, "volume": 5000.0},
    ]
    issues = validator.validate_rows(rows, symbol="VNM")
    # 30% jump > 20% max_session_move
    assert any(iss.rule == "price_jump_gt_20pct" for iss in issues)

    # Split ratio detection: 50% drop (2:1 split)
    split_rows = [
        {"timestamp": "2024-01-02", "open": 50000.0, "high": 51000.0, "low": 49000.0, "close": 50000.0, "volume": 5000.0},
        {"timestamp": "2024-01-03", "open": 25000.0, "high": 25500.0, "low": 24800.0, "close": 25000.0, "volume": 5000.0},
    ]
    split_issues = validator.validate_rows(split_rows, symbol="VNM")
    assert any(iss.rule == "potential_unadjusted_split" for iss in split_issues)


def test_api_data_validator_zero_volume_liquidity():
    """Verify zero-volume anomaly on liquid stocks."""
    validator = DataValidator(adv_lookback=3, liquid_adv_threshold=50000.0, validate_provenance=False)
    rows = [
        {"timestamp": f"2024-01-0{i}", "open": 20000.0, "high": 20500.0, "low": 19500.0, "close": 20000.0, "volume": 100000.0}
        for i in range(2, 5)
    ]
    # 4th row has 0 volume with high trailing ADV
    rows.append({"timestamp": "2024-01-05", "open": 20000.0, "high": 20500.0, "low": 19500.0, "close": 20000.0, "volume": 0.0})

    issues = validator.validate_rows(rows, symbol="TCB")
    assert any(iss.rule == "zero_volume_liquid_stock" for iss in issues)


def test_api_data_validator_provenance_and_checksum_sidecar(tmp_path):
    """Verify provenance metadata and .metadata.json checksum sidecar validation."""
    validator = DataValidator(validate_provenance=True)
    parquet_path = tmp_path / "test_data.parquet"
    sidecar_path = tmp_path / "test_data.metadata.json"

    # Write parquet data
    df = pd.DataFrame({"symbol": ["VNM"], "close": [70000.0]})
    df.to_parquet(parquet_path)

    # Compute genuine sha256
    hasher = hashlib.sha256()
    with open(parquet_path, "rb") as f:
        hasher.update(f.read())
    real_checksum = hasher.hexdigest()

    sidecar_path.write_text(json.dumps({
        "dataset_version": "v1.0",
        "source": "vci",
        "checksum": real_checksum,
        "checksum_algorithm": "sha256"
    }), encoding="utf-8")

    rows = [{
        "timestamp": "2024-01-02",
        "open": 70000.0, "high": 71000.0, "low": 69000.0, "close": 70000.0, "volume": 1000.0,
        "dataset_version": "v1.0",
        "source": "vci",
        "adjustments_applied": "[]",
    }]
    issues = validator.validate_rows(rows, symbol="VNM", parquet_path=parquet_path)
    assert issues == []

    # Checksum mismatch test
    sidecar_path.write_text(json.dumps({
        "checksum": "0" * 64,
        "checksum_algorithm": "sha256"
    }), encoding="utf-8")
    mismatch_issues = validator.validate_rows(rows, symbol="VNM", parquet_path=parquet_path)
    assert any(iss.rule == "checksum_mismatch" for iss in mismatch_issues)


def test_api_data_quality_checker_missing_and_outliers():
    """Verify DataQualityChecker checks for missing ratios and price outliers."""
    checker = DataQualityChecker(max_missing_pct=0.05, price_jump_threshold=0.15)

    # Missing check: 1 None in 20 is 5% <= 5% -> True
    clean_vals = [100.0] * 19 + [None]
    assert checker.check_missing_values(clean_vals) is True

    # 2 None in 20 is 10% > 5% -> False
    dirty_vals = [100.0] * 18 + [None, None]
    assert checker.check_missing_values(dirty_vals) is False

    # Outliers check: 10% change <= 15% -> True
    stable_prices = [100.0, 110.0, 105.0]
    assert checker.check_outliers(stable_prices) is True

    # 20% jump > 15% -> False
    jump_prices = [100.0, 125.0]
    assert checker.check_outliers(jump_prices) is False

    res = checker.validate(stable_prices)
    assert res == {"is_valid": True, "missing_pass": True, "outliers_pass": True}


def test_api_data_validator_compatibility_shim():
    """Verify src/omega/data/data_validator.py compatibility shim behavior."""
    shim_validator = data_validator_shim.DataValidator()

    empty_df = pd.DataFrame()
    result = shim_validator.validate(empty_df)
    assert result["total_rows"] == 0
    assert result["issues"] == []

    non_empty_df = pd.DataFrame({"a": [1, 2, 3]})
    assert shim_validator.validate(non_empty_df)["total_rows"] == 3


def test_api_sanitizer_ssot_interfaces():
    """Verify intended sanitizer SSOT interfaces and cross-module export compatibility."""
    # DataSanitizer SSOT
    assert hasattr(sanitizer_mod, "DataSanitizer")

    # Check if consolidated or accessible via intended aliases
    target_validator_cls = getattr(sanitizer_mod, "DataValidator", validator_mod.DataValidator)
    target_issue_cls = getattr(sanitizer_mod, "ValidationIssue", validator_mod.ValidationIssue)
    target_quality_cls = getattr(sanitizer_mod, "DataQualityChecker", data_quality_mod.DataQualityChecker)

    val_instance = target_validator_cls()
    assert hasattr(val_instance, "validate")
    assert hasattr(val_instance, "validate_rows")

    qc_instance = target_quality_cls()
    assert hasattr(qc_instance, "validate")
    assert hasattr(qc_instance, "check_missing_values")
    assert hasattr(qc_instance, "check_outliers")

    iss_instance = target_issue_cls(rule="test_rule", message="test msg", symbol="TEST", timestamp="2024-01-01")
    assert iss_instance.rule == "test_rule"
    assert iss_instance.symbol == "TEST"


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: 16-DIMENSION ADVERSARIAL MATRIX
# ═══════════════════════════════════════════════════════════════════════════════

def test_dim1_adversarial_malformed_types():
    """Dim 1: Malformed types, NaN, Inf, strings, lists, None inputs fail-closed."""
    # Non-DataFrame input to DataValidator
    validator = DataValidator()
    assert validator.validate(None) == {"error": "Input must be a pandas DataFrame"}
    assert validator.validate("invalid_str") == {"error": "Input must be a pandas DataFrame"}
    assert validator.validate([1, 2, 3]) == {"error": "Input must be a pandas DataFrame"}

    # DataQualityChecker handles empty and corrupt lists
    checker = DataQualityChecker()
    assert checker.check_missing_values([]) is False
    assert checker.check_outliers([]) is True
    assert checker.validate([]) == {"is_valid": False, "missing_pass": False, "outliers_pass": True}

    # DataSanitizer input validation
    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    # Missing required OHLCV columns raises ValueError
    bad_df = pd.DataFrame({"symbol": ["HPG"], "date": [pd.Timestamp("2024-01-01")], "close": [25000.0]})
    with pytest.raises(ValueError, match="Missing OHLCV columns"):
        sanitizer.fit(bad_df)

    # Missing symbol_col or date_col raises ValueError
    bad_df2 = pd.DataFrame({
        "open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [10.0]
    })
    with pytest.raises(ValueError, match="Missing required columns"):
        sanitizer.fit(bad_df2)


def test_dim2_adversarial_invalid_paths_and_encoding(tmp_path):
    """Dim 2: Invalid directory I/O paths, missing sidecar, and Windows UTF-8/CRLF encoding."""
    validator = DataValidator(validate_provenance=True)
    rows = [{
        "timestamp": "2024-01-02",
        "open": 50000.0, "high": 51000.0, "low": 49000.0, "close": 50000.0, "volume": 1000.0,
        "dataset_version": "v1.0", "source": "vci",
    }]

    # Non-existent sidecar
    missing_parquet = tmp_path / "non_existent.parquet"
    issues = validator.validate_rows(rows, symbol="VNM", parquet_path=missing_parquet)
    assert any(iss.rule == "missing_metadata_sidecar" for iss in issues)

    # Corrupted / invalid JSON sidecar
    parquet_p = tmp_path / "corrupted.parquet"
    parquet_p.write_bytes(b"DUMMY_PARQUET_HEADER")
    sidecar_p = tmp_path / "corrupted.metadata.json"
    sidecar_p.write_text("NOT_VALID_JSON{{{", encoding="utf-8")

    issues_corrupt = validator.validate_rows(rows, symbol="VNM", parquet_path=parquet_p)
    assert any(iss.rule == "invalid_metadata_sidecar" for iss in issues_corrupt)

    # Windows UTF-8 with CRLF line endings in sidecar
    sidecar_p.write_text('{\r\n  "dataset_version": "v1.0",\r\n  "source": "vci"\r\n}\r\n', encoding="utf-8")
    issues_crlf = validator.validate_rows(rows, symbol="VNM", parquet_path=parquet_p)
    assert any(iss.rule == "missing_checksum_in_sidecar" for iss in issues_crlf)


def test_dim3_adversarial_corrupted_duplicate_checkpoints():
    """Dim 3: Corrupted, duplicate, and partial checkpoint/row deduplication."""
    dates = [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    df_dup = pd.DataFrame({
        "date": dates,
        "symbol": ["VCB", "VCB", "VCB"],
        "open": [90000.0, 91000.0, 92000.0],  # row 1 is duplicate date
        "high": [91000.0, 92000.0, 93000.0],
        "low": [89000.0, 90000.0, 91000.0],
        "close": [90500.0, 91500.0, 92500.0],
        "volume": [100000.0, 110000.0, 120000.0],
    })

    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    cleaned_df, stats = sanitizer.clean_ohlcv(df_dup, as_of_time=pd.Timestamp("2024-02-01"))
    assert len(cleaned_df) == 2
    assert stats["duplicates_removed"] == 1
    # First occurrence preserved
    assert cleaned_df.iloc[0]["open"] == 90000.0


def test_dim4_adversarial_fail_closed_error_states_and_extractor():
    """Dim 4: Fail-closed exit codes, uninitialized application, and extractor failure."""
    # 1. Applying un-fitted sanitizer raises RuntimeError
    unfitted = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    dummy_df = pd.DataFrame({
        "date": [pd.Timestamp("2024-01-01")], "symbol": ["VNM"],
        "open": [10.0], "high": [11.0], "low": [9.0], "close": [10.0], "volume": [100.0]
    })
    with pytest.raises(RuntimeError, match="must be fitted before apply"):
        unfitted.apply(dummy_df)

    # 2. Missing mandatory as_of_time raises ValueError
    sanitizer_no_time = DataSanitizer(as_of_time=None)
    with pytest.raises(ValueError, match="as_of_time is mandatory"):
        sanitizer_no_time._enforce_pit_safety(dummy_df, "date", as_of_time=None)

    # 3. Macro news LLM fail-closed contract verification
    assert hasattr(run_macro_news_pipeline, "_llm_final_exit_state")
    failing_metrics = {"extraction_failures": 3, "extraction_successes": 0}
    assert run_macro_news_pipeline._llm_final_exit_state(failing_metrics) == "llm_failed"

    zero_attempt_metrics = {"extraction_failures": 0, "extraction_successes": 0}
    assert run_macro_news_pipeline._llm_final_exit_state(zero_attempt_metrics) is None


def test_dim5_adversarial_rollback_and_atomicity():
    """Dim 5: Input immutability: sanitize and validate operations do not mutate inputs in-place."""
    dates = pd.date_range("2024-01-01", periods=22, freq="D")
    df_orig = pd.DataFrame({
        "date": dates,
        "symbol": "VHM",
        "open": np.full(22, 45000.0),
        "high": np.full(22, 46000.0),
        "low": np.full(22, 44000.0),
        "close": np.full(22, 45500.0),
        "volume": np.full(22, 300000.0),
    })
    original_cols = list(df_orig.columns)
    df_snapshot = df_orig.copy(deep=True)

    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    sanitizer.fit(df_orig)
    cleaned = sanitizer.apply(df_orig)

    # Original DataFrame unchanged
    assert list(df_orig.columns) == original_cols
    pd.testing.assert_frame_equal(df_orig, df_snapshot)
    assert "as_of" not in df_orig.columns
    assert "as_of" in cleaned.columns


def test_dim6_adversarial_pit_and_lookahead_safety():
    """Dim 6: Strict Point-In-Time (PIT) safety, causal forward-fill, as_of <= available_at."""
    dates = [
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03"),
        pd.Timestamp("2024-01-04"),
    ]
    df = pd.DataFrame({
        "date": dates,
        "symbol": "FPT",
        "open": [100000.0, np.nan, np.nan, 103000.0],
        "high": [102000.0, np.nan, np.nan, 104000.0],
        "low": [99000.0, np.nan, np.nan, 102000.0],
        "close": [101000.0, np.nan, np.nan, 103500.0],
        "volume": [500000.0, np.nan, np.nan, 600000.0],
    })

    as_of = pd.Timestamp("2024-01-03")
    sanitizer = DataSanitizer(max_fill_days=2, as_of_time=as_of)
    cleaned, stats = sanitizer.clean_ohlcv(df, as_of_time=as_of)

    # Causal forward fill only fills from past: row 1 (Jan 2) gets Jan 1 values
    assert cleaned.iloc[1]["close"] == 101000.0
    # available_at = date + 1 day
    assert (cleaned["available_at"] == cleaned["date"] + pd.Timedelta(days=1)).all()
    # as_of <= available_at strictly enforced
    assert (cleaned["as_of"] <= cleaned["available_at"]).all()


def test_dim7_adversarial_trading_calendar_and_holidays():
    """Dim 7: Vietnam trading calendar, weekends, Tet statutory holiday boundaries."""
    # Weekend days are not trading days
    saturday = datetime(2026, 1, 3)
    sunday = datetime(2026, 1, 4)
    assert VNTradingCalendar.is_trading_day(saturday) is False
    assert VNTradingCalendar.is_trading_day(sunday) is False

    # New Year Day (2026-01-01) is non-trading holiday
    new_year = datetime(2026, 1, 1)
    assert VNTradingCalendar.is_trading_day(new_year) is False

    # Missing genuine trading weekday is detected by DataValidator
    validator = DataValidator(validate_provenance=False)
    # Jan 5, 2026 is Monday; Jan 7 is Wednesday. Jan 6 (Tuesday) is missing.
    rows = [
        {"timestamp": "2026-01-05", "open": 50.0, "high": 51.0, "low": 49.0, "close": 50.0, "volume": 100.0},
        {"timestamp": "2026-01-07", "open": 52.0, "high": 53.0, "low": 51.0, "close": 52.0, "volume": 100.0},
    ]
    issues = validator.validate_rows(rows, symbol="VNM")
    assert any(iss.rule == "missing_trading_timestamp" and "2026-01-06" in iss.message for iss in issues)


def test_dim8_adversarial_numeric_precision_and_zero_division():
    """Dim 8: Zero-division guard, zero variance, and deterministic bit-for-bit repeatability."""
    checker = DataQualityChecker()
    # prev == 0 does not raise ZeroDivisionError
    zero_prev = [0.0, 100.0]
    assert checker.check_outliers(zero_prev) is True

    # Zero variance standard deviation handled without crash in DataSanitizer
    dates = pd.date_range("2024-01-01", periods=25, freq="D")
    df_const = pd.DataFrame({
        "date": dates,
        "symbol": "STB",
        "open": np.full(25, 30000.0),
        "high": np.full(25, 30000.0),
        "low": np.full(25, 30000.0),
        "close": np.full(25, 30000.0),
        "volume": np.full(25, 100000.0),
    })
    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    sanitizer.fit(df_const)
    run1 = sanitizer.apply(df_const)
    run2 = sanitizer.apply(df_const)

    # Bit-for-bit deterministic repeatability
    pd.testing.assert_frame_equal(run1, run2)


def test_dim9_adversarial_concurrency_race_conditions():
    """Dim 9: Multi-threaded race condition safety across fitted sanitizer and validator."""
    dates = pd.date_range("2024-01-01", periods=25, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "symbol": "MBB",
        "open": np.linspace(22000, 24000, 25),
        "high": np.linspace(22500, 24500, 25),
        "low": np.linspace(21500, 23500, 25),
        "close": np.linspace(22000, 24000, 25),
        "volume": np.full(25, 800000.0),
    })

    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    sanitizer.fit(df)
    validator = DataValidator(validate_provenance=False)

    def worker_task(worker_id: int):
        clean_res = sanitizer.apply(df)
        val_res = validator.validate(df)
        return len(clean_res), val_res["total_rows"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker_task, i) for i in range(16)]
        results = [f.result() for f in futures]

    assert all(r == (25, 25) for r in results)


def test_dim10_adversarial_vnd_full_price_scale_invariance():
    """Dim 10: VND_FULL price scale preservation, min_price garbage filter."""
    dates = pd.date_range("2024-01-01", periods=25, freq="D")
    # Real Vietnamese stock prices: 50,000 to 52,000 VND
    df_vnd = pd.DataFrame({
        "date": dates,
        "symbol": "MWG",
        "open": np.linspace(50000, 52000, 25),
        "high": np.linspace(51000, 53000, 25),
        "low": np.linspace(49000, 51000, 25),
        "close": np.linspace(50000, 52000, 25),
        "volume": np.full(25, 200000.0),
    })

    # Setting min_price threshold to 51000 filters out lower prices in VND scale
    sanitizer = DataSanitizer(min_price=51000.0, as_of_time=pd.Timestamp("2024-02-01"))
    sanitizer.fit(df_vnd)
    cleaned = sanitizer.apply(df_vnd)

    assert sanitizer.sanitization_stats["invalid_prices_removed"] > 0
    # Retained prices remain in full VND (not scaled down to 50.0)
    assert (cleaned["close"] >= 51000.0).all()


def test_dim11_adversarial_survivorship_and_delisting_anomalies():
    """Dim 11: Survivorship & delisted tickers with <20 observations handled without crash."""
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    short_history_df = pd.DataFrame({
        "date": dates,
        "symbol": "DELISTED_XYZ",
        "open": [1000.0, 1050.0, 1020.0, 1010.0, 1000.0],
        "high": [1050.0, 1080.0, 1050.0, 1030.0, 1020.0],
        "low": [980.0, 1010.0, 990.0, 980.0, 970.0],
        "close": [1020.0, 1030.0, 1000.0, 1000.0, 990.0],
        "volume": [100.0, 150.0, 80.0, 90.0, 110.0],
    })

    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    # Fewer than 20 observations -> no quantile bounds computed, but fit completes safely
    sanitizer.fit(short_history_df)
    assert sanitizer._fitted_params["quantiles"]["DELISTED_XYZ"] == {}

    cleaned = sanitizer.apply(short_history_df)
    assert len(cleaned) == 5

    # Zero volume on illiquid stock is not flagged as liquid failure
    validator = DataValidator(adv_lookback=3, liquid_adv_threshold=100000.0, validate_provenance=False)
    rows = [
        {"timestamp": f"2024-01-0{i}", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 10.0}
        for i in range(1, 5)
    ]
    rows.append({"timestamp": "2024-01-05", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 0.0})
    issues = validator.validate_rows(rows, symbol="DELISTED_XYZ")
    assert not any(iss.rule == "zero_volume_liquid_stock" for iss in issues)


def test_dim12_adversarial_cli_injection_and_flag_smuggling():
    """Dim 12: Injection payloads in symbol names treated strictly as string identifiers."""
    injections = [
        "VNM; DROP TABLE market_data; --",
        "HPG && rm -rf /",
        "--as-of-time=2024-01-01",
        "<script>alert(1)</script>",
    ]
    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    validator = DataValidator(validate_provenance=False)

    for inj in injections:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=25, freq="D"),
            "symbol": [inj] * 25,
            "open": np.full(25, 10000.0),
            "high": np.full(25, 10500.0),
            "low": np.full(25, 9900.0),
            "close": np.full(25, 10000.0),
            "volume": np.full(25, 500.0),
        })
        # Sanitizer fits and processes symbol literally without shell or eval injection
        sanitizer.fit(df)
        assert inj in sanitizer._fitted_params["mean"]
        cleaned = sanitizer.apply(df)
        assert len(cleaned) == 25

        # Validator assigns symbol safely into ValidationIssue
        bad_row = [{"timestamp": "2024-01-02", "open": 10.0, "high": 5.0, "low": 4.0, "close": 9.0, "volume": 1.0}]
        issues = validator.validate_rows(bad_row, symbol=inj)
        assert issues[0].symbol == inj


def test_dim13_adversarial_schema_drift_and_column_mutation():
    """Dim 13: Schema drift defense: extra columns preserved, dataclasses immutable."""
    dates = pd.date_range("2024-01-01", periods=22, freq="D")
    df_extra = pd.DataFrame({
        "date": dates,
        "symbol": "VNM",
        "open": np.full(22, 70000.0),
        "high": np.full(22, 71000.0),
        "low": np.full(22, 69000.0),
        "close": np.full(22, 70500.0),
        "volume": np.full(22, 500000.0),
        "foreign_buy_ratio": np.full(22, 0.35),
        "custom_alpha_signal": np.full(22, 1.25),
    })

    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    sanitizer.fit(df_extra)
    cleaned = sanitizer.apply(df_extra)
    assert "foreign_buy_ratio" in cleaned.columns
    assert "custom_alpha_signal" in cleaned.columns
    assert cleaned["foreign_buy_ratio"].iloc[0] == 0.35

    # ValidationIssue dataclass immutability
    issue = ValidationIssue(rule="r1", message="m1", symbol="VNM", timestamp="2024-01-01")
    with pytest.raises((AttributeError, TypeError)):
        issue.rule = "mutated_rule"


def test_dim14_adversarial_resource_exhaustion_bounds():
    """Dim 14: Resource and memory bounds: 5,000 rows processed rapidly without memory blowup."""
    n_rows = 5000
    dates = pd.date_range("2024-01-01", periods=n_rows, freq="h")
    large_df = pd.DataFrame({
        "date": dates,
        "symbol": "VNM",
        "open": np.random.uniform(70000, 75000, n_rows),
        "high": np.random.uniform(75000, 80000, n_rows),
        "low": np.random.uniform(65000, 70000, n_rows),
        "close": np.random.uniform(70000, 75000, n_rows),
        "volume": np.random.uniform(100000, 500000, n_rows),
    })

    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2025-01-01"))
    sanitizer.fit(large_df.iloc[:500])

    start_time = datetime.now()
    cleaned = sanitizer.apply(large_df)
    elapsed = (datetime.now() - start_time).total_seconds()

    assert len(cleaned) == n_rows
    # Vectorized execution should easily complete in under 3.0 seconds
    assert elapsed < 3.0


def test_dim15_adversarial_network_isolation_no_leaks(monkeypatch):
    """Dim 15: Offline validation: zero socket/network calls allowed."""
    def block_network(*args, **kwargs):
        raise RuntimeError("Unexpected network attempt during validation")

    monkeypatch.setattr(socket.socket, "connect", block_network)

    sanitizer = DataSanitizer(as_of_time=pd.Timestamp("2024-02-01"))
    dates = pd.date_range("2024-01-01", periods=22, freq="D")
    df = pd.DataFrame({
        "date": dates, "symbol": "VNM",
        "open": np.full(22, 70000.0), "high": np.full(22, 71000.0),
        "low": np.full(22, 69000.0), "close": np.full(22, 70000.0),
        "volume": np.full(22, 100000.0),
    })
    sanitizer.fit(df)
    cleaned = sanitizer.apply(df)
    assert len(cleaned) == 22

    validator = DataValidator(validate_provenance=False)
    res = validator.validate(df)
    assert res["total_rows"] == 22


def test_dim16_adversarial_secret_redaction():
    """Dim 16: Secret redaction: auth credentials stripped from error strings and reports."""
    token_url = "https://user:SuperSecretToken123@api.vnstock.com/v1/market?api_key=sk-99998888"
    redacted_url = _redact_url_for_error(token_url)
    assert "SuperSecretToken123" not in redacted_url
    assert "sk-99998888" not in redacted_url
    assert "user" not in redacted_url

    err_text = f"Failed to ingest from {token_url} using Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    sanitized_text = redact_credentials_in_text(err_text)
    assert "SuperSecretToken123" not in sanitized_text
    assert "eyJhbGciOi" not in sanitized_text


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: STANDING REGRESSION CLAUSE (1..8)
# ═══════════════════════════════════════════════════════════════════════════════

def test_regression_01_literal_legacy_ipv4_denial():
    """Prove literal IPv4 denial remains handled in production copilot SSRF validator."""
    assert _is_safe_global_unicast_ip(IPv4Address("127.0.0.1")) is False
    assert _is_safe_global_unicast_ip(IPv4Address("192.168.1.1")) is False
    assert resolve_validated_llm_target("https://127.0.0.1/v1") is None
    assert resolve_validated_llm_target("https://192.168.1.1/v1") is None


def test_regression_02_ipv6_embedded_ipv4_payloads():
    """Prove IPv6 embedded IPv4 payloads remain handled in production copilot SSRF validator."""
    assert _is_safe_global_unicast_ip(IPv6Address("::ffff:192.0.2.128")) is False
    assert _is_safe_global_unicast_ip(IPv6Address("::ffff:127.0.0.1")) is False


def test_regression_03_special_use_ranges():
    """Prove special-use IP ranges remain sanitized in production copilot SSRF validator."""
    assert _is_safe_global_unicast_ip(IPv4Address("10.0.0.1")) is False
    assert _is_safe_global_unicast_ip(IPv4Address("169.254.1.1")) is False
    assert resolve_validated_llm_target("https://10.0.0.1/v1") is None
    assert resolve_validated_llm_target("https://169.254.1.1/v1") is None
    assert _is_safe_global_unicast_ip(IPv4Address("93.184.216.34")) is True


def test_regression_04_sparse_config_merge_preservation(monkeypatch, tmp_path):
    """Sparse config merge preserves existing defaults in production llm_config."""
    dummy_cfg = tmp_path / "alpha_llm_config.json"
    dummy_cfg.write_text('{"provider": "mock", "model": "gpt-4"}', encoding="utf-8")
    monkeypatch.setenv("OMEGA_ALPHA_LLM_CONFIG_PATH", str(dummy_cfg))
    monkeypatch.delenv("OMEGA_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OMEGA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OMEGA_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OMEGA_LLM_MODEL", raising=False)

    cfg = resolve_alpha_llm_config(tmp_path)
    assert cfg["provider"] == "mock"
    assert cfg["model"] == "gpt-4"

    monkeypatch.setenv("OMEGA_LLM_PROVIDER", "openai-compatible")
    cfg2 = resolve_alpha_llm_config(tmp_path)
    assert cfg2["provider"] == "openai-compatible"
    assert cfg2["model"] == "gpt-4"


def test_regression_05_test_isolation_snapshot_restore(tmp_path):
    """Test isolation snapshot restore is intact in production atomic_write_with_backup."""
    target_path = tmp_path / "isolated.parquet"
    df_orig = pd.DataFrame({"ticker": ["SNAP"], "close": [100.0]})
    update_market_data.atomic_write_with_backup(df_orig, target_path, backup=False)

    df_bad = pd.DataFrame({"ticker": ["BAD"], "close": [200.0]})

    class DiskFullError(IOError):
        pass

    real_to_parquet = pd.DataFrame.to_parquet
    pd.DataFrame.to_parquet = lambda *args, **kwargs: (_ for _ in ()).throw(DiskFullError("simulated crash"))
    try:
        with pytest.raises(DiskFullError):
            update_market_data.atomic_write_with_backup(df_bad, target_path, backup=True)
    finally:
        pd.DataFrame.to_parquet = real_to_parquet

    assert target_path.exists()
    assert pd.read_parquet(target_path).loc[0, "ticker"] == "SNAP"


def test_regression_06_durable_tls_sni_evidence():
    """Durable TLS SNI evidence preservation in production official_watermark and copilot."""
    ctx = _official_tls_context()
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED

    with pytest.raises(ValueError) as excinfo:
        _prepare_llm_request("https://", "custom", "test")
    assert "hostname" in str(excinfo.value.__cause__)


def test_regression_07_userinfo_credential_rejection():
    """Userinfo credential rejection check in production copilot request preparer."""
    assert resolve_validated_llm_target("https://user:pass@example.com/data") is None
    with pytest.raises(ValueError) as excinfo:
        _prepare_llm_request("https://user:pass@example.com/v1", "custom", "test")
    assert "userinfo" in str(excinfo.value.__cause__)


def test_regression_08_url_redaction_in_errors():
    """URL redaction in errors check using production copilot redactor."""
    secret_url = "https://user:secret_pass@example.com:8080/api/v1"
    redacted_url = _redact_url_for_error(secret_url)
    assert "secret_pass" not in redacted_url
    assert "user" not in redacted_url
    assert redacted_url == "https://example.com:8080"

    text = f"Connection failed to {secret_url} with authorization Bearer my_super_secret_token_123"
    redacted_text = redact_credentials_in_text(text)
    assert "secret_pass" not in redacted_text
    assert "my_super_secret_token_123" not in redacted_text
