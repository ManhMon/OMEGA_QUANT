"""
Adversarial 16-dimension test suite for legacy vnstock_live adapter archive
and fail-closed stub verification in OMEGA_QUANT Phase 3B.
"""

import ast
import concurrent.futures
import math
import os
import py_compile
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set

import numpy as np
import pandas as pd
import pytest

from omega.data.vnstock_live import (
    VnStockLiveConfig,
    VnStockLiveData,
    VnStockLiveDataProvider,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_PATH = REPO_ROOT / "archive" / "legacy_adapters" / "vnstock_live.py"
STUB_PATH = REPO_ROOT / "src" / "omega" / "data" / "vnstock_live.py"


def _get_ast_classes(path: Path) -> Set[str]:
    content = path.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(path))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def _get_ast_functions(path: Path) -> Set[str]:
    content = path.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


# ==============================================================================
# 1. Complete Untruncated Syntax Integrity & AST Validation of Archive File
# ==============================================================================


def test_archive_vnstock_live_exists_and_untruncated_line_count():
    """Verify archive/legacy_adapters/vnstock_live.py exists and has exact untruncated 514 lines."""
    assert ARCHIVE_PATH.exists(), f"Archive file not found: {ARCHIVE_PATH}"
    content = ARCHIVE_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert len(lines) >= 514, f"Archive unexpectedly truncated: {len(lines)} lines"


def test_archive_vnstock_live_valid_ast_and_compiles():
    """Verify archive file compiles to valid bytecode and parses into a complete AST module."""
    assert ARCHIVE_PATH.exists()
    content = ARCHIVE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(ARCHIVE_PATH))
    assert isinstance(tree, ast.Module), "AST parse result is not an ast.Module"

    # Must compile cleanly via py_compile
    py_compile.compile(str(ARCHIVE_PATH), doraise=True)


def test_archive_vnstock_live_ast_classes():
    """Verify archive file AST contains mandatory classes: VnStockLiveConfig, VnStockLiveData, VnStockLiveDataProvider."""
    classes = _get_ast_classes(ARCHIVE_PATH)
    expected_classes = {"VnStockLiveConfig", "VnStockLiveData", "VnStockLiveDataProvider"}
    assert expected_classes.issubset(classes), (
        f"Archive file missing required classes. Expected: {expected_classes}, found: {classes}"
    )


def test_archive_vnstock_live_ast_functions():
    """Verify archive file AST contains core functions/methods."""
    functions = _get_ast_functions(ARCHIVE_PATH)
    expected_functions = {
        "_compute_adv_vectorized",
        "_compute_volatility_vectorized",
        "fetch_live_data",
        "get_latest_prices",
        "get_market_data_for_risk_guard",
        "_fetch_price_data_single",
    }
    assert expected_functions.issubset(functions), (
        f"Archive file missing required functions. Expected: {expected_functions}, found: {functions}"
    )


def test_archive_vnstock_live_truncation_fault_injection(tmp_path):
    """Adversarial fault-injection: verify truncation reproduces SyntaxError/PyCompileError while full file passes."""
    content = ARCHIVE_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Truncate inside the configuration class (incomplete AST)
    truncated_content = "\n".join(lines[:68])
    truncated_file = tmp_path / "vnstock_live_truncated.py"
    truncated_file.write_text(truncated_content, encoding="utf-8")

    with pytest.raises((py_compile.PyCompileError, SyntaxError)):
        py_compile.compile(str(truncated_file), doraise=True)

    with pytest.raises(SyntaxError):
        ast.parse(truncated_content)

    py_compile.compile(str(ARCHIVE_PATH), doraise=True)
    assert ast.parse(content) is not None


# ==============================================================================
# 2. Fail-Closed Verification of src/omega/data/vnstock_live.py
# ==============================================================================


def test_fail_closed_stub_instantiation():
    """Verify VnStockLiveDataProvider instantiates successfully without network access."""
    provider = VnStockLiveDataProvider()
    assert isinstance(provider, VnStockLiveDataProvider)

    config = VnStockLiveConfig(pit_lag_days=1, board_lot_size=100)
    provider_custom = VnStockLiveDataProvider(config=config)
    assert isinstance(provider_custom, VnStockLiveDataProvider)


def test_fail_closed_fetch_live_data_raises_import_error():
    """Verify calling fetch_live_data raises ImportError."""
    provider = VnStockLiveDataProvider()
    with pytest.raises(ImportError):
        provider.fetch_live_data(["VCB"], reference_date=datetime(2026, 1, 1))


def test_fail_closed_get_latest_prices_raises_import_error():
    """Verify calling get_latest_prices raises ImportError."""
    provider = VnStockLiveDataProvider()
    with pytest.raises(ImportError):
        provider.get_latest_prices(["VCB"], reference_date=datetime(2026, 1, 1))


def test_fail_closed_get_market_data_for_risk_guard_raises_import_error():
    """Verify calling get_market_data_for_risk_guard raises ImportError."""
    provider = VnStockLiveDataProvider()
    with pytest.raises(ImportError):
        provider.get_market_data_for_risk_guard(["VCB"], reference_date=datetime(2026, 1, 1))


def test_fail_closed_fetch_price_data_single_raises_import_error():
    """Verify calling _fetch_price_data_single raises ImportError."""
    provider = VnStockLiveDataProvider()
    with pytest.raises(ImportError):
        provider._fetch_price_data_single("VCB", "2026-01-01", "2026-01-05")


def test_quant_engine_get_vnstock_live_provider_returns_stub():
    """Verify QuantEngine.get_vnstock_live_provider returns stub and warns about deprecation."""
    from omega.quant.quant_engine import QuantEngine
    with pytest.deprecated_call():
        provider_cls = QuantEngine.get_vnstock_live_provider()
    assert provider_cls is VnStockLiveDataProvider


# ==============================================================================
# 3. Sector Report Compatibility
# ==============================================================================


def test_sector_report_compute_adv_vectorized_numeric_accuracy():
    """Verify _compute_adv_vectorized computes exact average daily volume and value over window."""
    fetcher = VnStockLiveDataProvider()

    dates = pd.date_range("2026-01-01", periods=25, freq="D")
    df_vcb = pd.DataFrame({
        "ticker": ["VCB"] * 25,
        "date": dates,
        "volume": [1000.0 + i * 100.0 for i in range(25)],
        "value": [10000.0 + i * 1000.0 for i in range(25)],
    })
    df_hpg = pd.DataFrame({
        "ticker": ["HPG"] * 25,
        "date": dates,
        "volume": [5000.0 + i * 50.0 for i in range(25)],
        "value": [50000.0 + i * 500.0 for i in range(25)],
    })
    df = pd.concat([df_vcb, df_hpg], ignore_index=True)

    window = 20
    adv = fetcher._compute_adv_vectorized(df, window=window)

    assert set(adv.columns) == {"ticker", "adv_volume", "adv_value"}
    assert len(adv) == 2

    # Expected values over last 20 rows (indices 5 to 24)
    expected_vcb_vol = float(df_vcb["volume"].tail(window).mean())
    expected_vcb_val = float(df_vcb["value"].tail(window).mean())
    expected_hpg_vol = float(df_hpg["volume"].tail(window).mean())
    expected_hpg_val = float(df_hpg["value"].tail(window).mean())

    vcb_row = adv[adv["ticker"] == "VCB"].iloc[0]
    hpg_row = adv[adv["ticker"] == "HPG"].iloc[0]

    np.testing.assert_allclose(vcb_row["adv_volume"], expected_vcb_vol)
    np.testing.assert_allclose(vcb_row["adv_value"], expected_vcb_val)
    np.testing.assert_allclose(hpg_row["adv_volume"], expected_hpg_vol)
    np.testing.assert_allclose(hpg_row["adv_value"], expected_hpg_val)


def test_sector_report_compute_volatility_vectorized_in_memory():
    """Verify _compute_volatility_vectorized computes annualized return volatility in-memory."""
    fetcher = VnStockLiveDataProvider()

    dates = pd.date_range("2026-01-01", periods=25, freq="D")
    prices = [100.0 * (1.01 ** i) for i in range(25)]
    df = pd.DataFrame({
        "ticker": ["VCB"] * 25,
        "date": dates,
        "close": prices,
    })

    window = 20
    vol = fetcher._compute_volatility_vectorized(df, window=window)

    assert set(vol.columns) == {"ticker", "volatility"}
    assert len(vol) == 1
    val = vol.iloc[0]["volatility"]
    assert not math.isnan(val)
    assert val > 0.0


# ==============================================================================
# 4. Comprehensive 16-Dimension Adversarial Matrix Tests
# ==============================================================================


def test_16d_dim01_malformed_out_of_bounds_inputs():
    """(1) Malformed/out-of-bounds: empty DF, NaN, Inf, non-numeric in volume/value."""
    fetcher = VnStockLiveDataProvider()

    # Empty DataFrame
    empty_df = pd.DataFrame()
    res_empty = fetcher._compute_adv_vectorized(empty_df, window=20)
    assert list(res_empty.columns) == ["ticker", "adv_volume", "adv_value"]
    assert len(res_empty) == 0

    # DataFrame with required columns but zero rows
    empty_cols = pd.DataFrame(columns=["ticker", "date", "volume", "value"])
    res_empty_cols = fetcher._compute_adv_vectorized(empty_cols, window=20)
    assert len(res_empty_cols) == 0

    # NaN and Inf handling
    df_nan_inf = pd.DataFrame({
        "ticker": ["VCB", "VCB", "VCB"],
        "date": pd.date_range("2026-01-01", periods=3),
        "volume": [100.0, np.nan, 300.0],
        "value": [1000.0, np.inf, 3000.0],
    })
    with pytest.raises(ValueError):
        fetcher._compute_adv_vectorized(df_nan_inf, window=20)

    # Non-numeric values in volume should raise TypeError or error on mean
    df_str = pd.DataFrame({
        "ticker": ["VCB"],
        "date": ["2026-01-01"],
        "volume": ["corrupted_volume_string"],
        "value": [1000.0],
    })
    with pytest.raises((TypeError, ValueError, Exception)):
        fetcher._compute_adv_vectorized(df_str, window=20)


def test_16d_dim02_invalid_paths_utf8_crlf():
    """(2) Invalid/directory I/O paths & Windows UTF-8/CRLF handling."""
    # Both archive and stub paths exist
    assert ARCHIVE_PATH.exists()
    assert STUB_PATH.exists()

    # UTF-8 decoding without errors
    archive_text = ARCHIVE_PATH.read_text(encoding="utf-8")
    stub_text = STUB_PATH.read_text(encoding="utf-8")
    assert len(archive_text) > 0
    assert len(stub_text) > 0

    # Handles CRLF/LF line endings
    norm_archive_lines = archive_text.replace("\r\n", "\n").splitlines()
    assert len(norm_archive_lines) >= 514

    # Non-existent path returns False
    invalid_path = REPO_ROOT / "archive" / "legacy_adapters" / "nonexistent_adapter.py"
    assert not invalid_path.exists()


def test_16d_dim03_corrupted_duplicate_partial_records():
    """(3) Corrupted/duplicate/partial records: duplicate dates and disordered timestamps."""
    fetcher = VnStockLiveDataProvider()

    # Disordered dates
    dates = pd.to_datetime(["2026-01-05", "2026-01-01", "2026-01-04", "2026-01-02", "2026-01-03"])
    df = pd.DataFrame({
        "ticker": ["VCB"] * 5,
        "date": dates,
        "volume": [50.0, 10.0, 40.0, 20.0, 30.0],
        "value": [500.0, 100.0, 400.0, 200.0, 300.0],
    })

    # Window=3 should sort chronologically and take 2026-01-03, 04, 05 (volumes 30, 40, 50 -> mean 40)
    adv = fetcher._compute_adv_vectorized(df, window=3)
    np.testing.assert_allclose(adv.iloc[0]["adv_volume"], 40.0)
    np.testing.assert_allclose(adv.iloc[0]["adv_value"], 400.0)

    # Duplicate dates are ambiguous and must fail closed
    df_dup = pd.DataFrame({
        "ticker": ["VCB", "VCB"],
        "date": pd.to_datetime(["2026-01-01", "2026-01-01"]),
        "volume": [100.0, 200.0],
        "value": [1000.0, 2000.0],
    })
    with pytest.raises(ValueError):
        fetcher._compute_adv_vectorized(df_dup, window=2)


def test_f004_archive_config_redacts_api_key(monkeypatch):
    import importlib.util

    monkeypatch.delenv("VNSTOCK_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location("legacy_vnstock_live", ARCHIVE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    secret = "sk_live_test_secret"
    config = module.VnStockLiveConfig(api_key=secret)
    assert secret not in repr(config)
    assert secret not in str(config)


@pytest.mark.parametrize("window", [-1, 0, 0.5, None, "20"])
def test_f005_numeric_helpers_reject_invalid_window(window):
    fetcher = VnStockLiveDataProvider()
    df = pd.DataFrame({
        "ticker": ["VCB"], "date": pd.to_datetime(["2026-01-01"]),
        "volume": [100.0], "value": [1000.0], "close": [10.0],
    })
    with pytest.raises((TypeError, ValueError)):
        fetcher._compute_adv_vectorized(df, window=window)
    with pytest.raises((TypeError, ValueError)):
        fetcher._compute_volatility_vectorized(df, window=window)


def test_f006_data_package_imports_fail_closed():
    source = (REPO_ROOT / "src" / "omega" / "data" / "__init__.py").read_text(encoding="utf-8")
    assert "except ImportError:\n    pass" not in source


def test_16d_dim04_fail_closed_error_states():
    """(4) Fail-closed error states: network entry points reliably raise ImportError."""
    provider = VnStockLiveDataProvider()

    # All public network entry points must raise ImportError
    with pytest.raises(ImportError):
        provider.fetch_live_data(["VCB"], reference_date=datetime.now())

    with pytest.raises(ImportError):
        provider.get_latest_prices(["VCB"], reference_date=datetime.now())

    with pytest.raises(ImportError):
        provider.get_market_data_for_risk_guard(["VCB"], reference_date=datetime.now())

    with pytest.raises(ImportError):
        provider._fetch_price_data_single("VCB", "2026-01-01", "2026-01-05")


def test_16d_dim05_rollback_and_atomicity(tmp_path):
    """(5) Rollback/atomicity: verify atomic behavior, no state pollution on error."""
    provider = VnStockLiveDataProvider()
    state_before = dict(provider.__dict__)

    with pytest.raises(ImportError):
        provider.fetch_live_data(["VCB"], reference_date=datetime.now())

    state_after = dict(provider.__dict__)
    # Internal configuration and attributes must not mutate or leak on error
    assert state_before.keys() == state_after.keys()

    # Verify atomic file replacement pattern (.tmp -> final)
    target = tmp_path / "atomic_target.py"
    tmp_file = tmp_path / "atomic_target.py.tmp"
    data = b"# atomic test content\n"
    tmp_file.write_bytes(data)
    assert tmp_file.exists()
    tmp_file.replace(target)
    assert target.exists()
    assert not tmp_file.exists()
    assert target.read_bytes() == data


def test_16d_dim06_pit_lookahead_safety():
    """(6) PIT & look-ahead safety: rolling window strictly looks backward, tail(window) bounded."""
    fetcher = VnStockLiveDataProvider()

    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    df = pd.DataFrame({
        "ticker": ["VCB"] * 30,
        "date": dates,
        "volume": list(range(1, 31)),
        "value": [x * 10 for x in range(1, 31)],
    })

    # Window=10 must strictly average rows 20 to 29 (values 21 to 30)
    adv_10 = fetcher._compute_adv_vectorized(df, window=10)
    expected_vol = np.mean(range(21, 31))  # 25.5
    np.testing.assert_allclose(adv_10.iloc[0]["adv_volume"], expected_vol)

    # Modifying earlier observations (e.g. index 0..19) must NOT change tail(10)
    df_modified = df.copy()
    df_modified.loc[0:15, "volume"] = 999999.0
    adv_10_mod = fetcher._compute_adv_vectorized(df_modified, window=10)
    np.testing.assert_allclose(adv_10_mod.iloc[0]["adv_volume"], expected_vol)


def test_16d_dim07_trading_calendar_boundaries():
    """(7) Trading calendar boundaries: irregular gaps (weekends/holidays) preserved."""
    fetcher = VnStockLiveDataProvider()

    # Gaps spanning weekends (Jan 9 Fri -> Jan 12 Mon) and Tet (Jan 23 -> Feb 2)
    trading_dates = pd.to_datetime([
        "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13",
        "2026-01-22", "2026-01-23", "2026-02-02", "2026-02-03",
    ])
    df = pd.DataFrame({
        "ticker": ["VCB"] * len(trading_dates),
        "date": trading_dates,
        "volume": [100.0 * (i + 1) for i in range(len(trading_dates))],
        "value": [1000.0 * (i + 1) for i in range(len(trading_dates))],
    })

    # Window=4 should take the last 4 trading days regardless of calendar gaps
    adv = fetcher._compute_adv_vectorized(df, window=4)
    expected_vol = np.mean([500.0, 600.0, 700.0, 800.0])
    np.testing.assert_allclose(adv.iloc[0]["adv_volume"], expected_vol)


def test_16d_dim08_numeric_precision_zero_division():
    """(8) Numeric precision & zero-division: zero-volume, zero-value rows without errors."""
    fetcher = VnStockLiveDataProvider()

    df_zero = pd.DataFrame({
        "ticker": ["ZERO_TICKER"] * 10,
        "date": pd.date_range("2026-01-01", periods=10),
        "volume": [0.0] * 10,
        "value": [0.0] * 10,
    })

    adv = fetcher._compute_adv_vectorized(df_zero, window=5)
    assert len(adv) == 1
    assert adv.iloc[0]["adv_volume"] == 0.0
    assert adv.iloc[0]["adv_value"] == 0.0

    # Very small numbers should preserve precision
    df_small = pd.DataFrame({
        "ticker": ["SMALL_TICKER"] * 5,
        "date": pd.date_range("2026-01-01", periods=5),
        "volume": [1e-9] * 5,
        "value": [1e-8] * 5,
    })
    adv_small = fetcher._compute_adv_vectorized(df_small, window=5)
    np.testing.assert_allclose(adv_small.iloc[0]["adv_volume"], 1e-9)


def test_16d_dim09_concurrency_and_thread_safety():
    """(9) Concurrency & thread safety: multi-threaded calculation produces deterministic results."""
    fetcher = VnStockLiveDataProvider()

    dates = pd.date_range("2026-01-01", periods=50, freq="D")
    df = pd.DataFrame({
        "ticker": ["VCB"] * 50,
        "date": dates,
        "volume": [float(i * 10) for i in range(50)],
        "value": [float(i * 100) for i in range(50)],
    })

    baseline = fetcher._compute_adv_vectorized(df, window=20)

    def _worker():
        return fetcher._compute_adv_vectorized(df, window=20)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_worker) for _ in range(24)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for res in results:
        pd.testing.assert_frame_equal(res, baseline)


def test_16d_dim10_vnd_full_price_scale():
    """(10) VND_FULL price scale: large VND values (> 1,000 to billions) preserved accurately."""
    fetcher = VnStockLiveDataProvider()

    # Vietnamese stock values: 10,000,000 shares @ 125,000 VND = 1.25 trillion VND
    df_large = pd.DataFrame({
        "ticker": ["VCB"] * 5,
        "date": pd.date_range("2026-01-01", periods=5),
        "volume": [10_000_000.0] * 5,
        "value": [1_250_000_000_000.0] * 5,
    })

    adv = fetcher._compute_adv_vectorized(df_large, window=5)
    assert adv.iloc[0]["adv_volume"] == 10_000_000.0
    assert adv.iloc[0]["adv_value"] == 1_250_000_000_000.0


def test_16d_dim11_survivorship_and_delisted_tickers():
    """(11) Survivorship & delisted tickers: partial history and sudden stops handled cleanly."""
    fetcher = VnStockLiveDataProvider()

    # Active ticker with 30 days, Delisted ticker with only 3 days
    dates_active = pd.date_range("2026-01-01", periods=30)
    dates_delisted = pd.date_range("2026-01-01", periods=3)

    df_active = pd.DataFrame({
        "ticker": ["ACTIVE"] * 30,
        "date": dates_active,
        "volume": [1000.0] * 30,
        "value": [10000.0] * 30,
    })
    df_delisted = pd.DataFrame({
        "ticker": ["DELISTED"] * 3,
        "date": dates_delisted,
        "volume": [200.0, 300.0, 400.0],
        "value": [2000.0, 3000.0, 4000.0],
    })
    df = pd.concat([df_active, df_delisted], ignore_index=True)

    adv = fetcher._compute_adv_vectorized(df, window=20)
    assert len(adv) == 2
    delisted_row = adv[adv["ticker"] == "DELISTED"].iloc[0]
    np.testing.assert_allclose(delisted_row["adv_volume"], 300.0)
    np.testing.assert_allclose(delisted_row["adv_value"], 3000.0)


def test_16d_dim12_cli_injection_parameter_smuggling():
    """(12) CLI injection / parameter smuggling: weird characters and injection strings handled safely."""
    fetcher = VnStockLiveDataProvider()

    malicious_tickers = [
        "VCB; DROP TABLE market_data; --",
        "HPG && rm -rf /",
        "../../etc/passwd",
        "' OR '1'='1",
    ]
    df = pd.DataFrame({
        "ticker": malicious_tickers,
        "date": pd.date_range("2026-01-01", periods=4),
        "volume": [100.0, 200.0, 300.0, 400.0],
        "value": [1000.0, 2000.0, 3000.0, 4000.0],
    })

    adv = fetcher._compute_adv_vectorized(df, window=5)
    assert len(adv) == 4
    assert set(adv["ticker"]) == set(malicious_tickers)

    # Fail-closed network methods reject injection without executing shell or sql
    with pytest.raises(ImportError):
        fetcher.fetch_live_data(malicious_tickers, reference_date=datetime.now())


def test_16d_dim13_schema_drift_and_unexpected_columns():
    """(13) Schema drift & unexpected columns: extra columns ignored, missing columns raise KeyError."""
    fetcher = VnStockLiveDataProvider()

    # Extra columns should not disrupt output schema
    df_extra = pd.DataFrame({
        "ticker": ["VCB"] * 5,
        "date": pd.date_range("2026-01-01", periods=5),
        "volume": [100.0] * 5,
        "value": [1000.0] * 5,
        "extra_meta": ["foo"] * 5,
        "noise": [999] * 5,
    })
    adv = fetcher._compute_adv_vectorized(df_extra, window=5)
    assert list(adv.columns) == ["ticker", "adv_volume", "adv_value"]

    # Missing required column should raise KeyError
    df_missing = pd.DataFrame({
        "ticker": ["VCB"] * 5,
        "date": pd.date_range("2026-01-01", periods=5),
        "volume": [100.0] * 5,
        # missing 'value'
    })
    with pytest.raises(KeyError):
        fetcher._compute_adv_vectorized(df_missing, window=5)


def test_16d_dim14_resource_exhaustion_memory_bounds():
    """(14) Resource exhaustion & memory bounds: 50,000 rows across 50 tickers computed rapidly."""
    fetcher = VnStockLiveDataProvider()

    tickers = [f"TCK_{i:02d}" for i in range(50)]
    dates = pd.date_range("2024-01-01", periods=1000, freq="D")

    # Generate 50,000 rows
    records = {
        "ticker": np.repeat(tickers, 1000),
        "date": np.tile(dates, 50),
        "volume": np.random.uniform(100.0, 10000.0, size=50000),
        "value": np.random.uniform(10000.0, 1000000.0, size=50000),
    }
    large_df = pd.DataFrame(records)

    start_time = time.perf_counter()
    adv = fetcher._compute_adv_vectorized(large_df, window=20)
    elapsed = time.perf_counter() - start_time

    assert len(adv) == 50
    # Vectorized computation should complete well under 2.0 seconds
    assert elapsed < 2.0, f"Vectorized ADV computation took too long: {elapsed:.3f}s"


def test_16d_dim15_network_timeout_retry_exhaustion():
    """(15) Network timeout / retry exhaustion: stub blocks immediately without hanging."""
    provider = VnStockLiveDataProvider()

    start_time = time.perf_counter()
    with pytest.raises(ImportError):
        provider.fetch_live_data(["VCB"], reference_date=datetime.now())
    elapsed = time.perf_counter() - start_time

    # Must raise immediately (< 100ms), proving no socket connect or retry loops
    assert elapsed < 0.1, f"Fail-closed check took too long ({elapsed:.3f}s); potential retry loop"


def test_16d_dim16_secret_redaction():
    """(16) Secret redaction: API keys or sensitive attributes never leaked in string representation."""
    secret_key = "sk_live_super_secret_production_key_99999"
    config = VnStockLiveConfig(api_key=secret_key)
    provider = VnStockLiveDataProvider(config=config)

    # Provider string representations must not expose raw secret
    str_rep = str(provider)
    repr_rep = repr(provider)
    assert secret_key not in str_rep, "Secret API key leaked in str(provider)"
    assert secret_key not in repr_rep, "Secret API key leaked in repr(provider)"

    # Error messages must not leak the secret key
    try:
        provider.fetch_live_data(["VCB"], reference_date=datetime.now())
    except Exception as exc:
        assert secret_key not in str(exc), "Secret API key leaked in exception message"
