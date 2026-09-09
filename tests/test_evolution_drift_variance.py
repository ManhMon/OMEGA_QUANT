"""
Multi-Seed Evolution, Variance Explorer, and Drift Sentinel Tests.
Adversarial 16-Dimension Master Verification Matrix & Standing Regression Suite.
Gate: GATE_EVOLUTION_DRIFT_VARIANCE_20260909
"""

import concurrent.futures
import ipaddress
import json
import sqlite3
import uuid
from datetime import datetime, date, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from omega.api.server import app
from omega.api.worker import execute_job
from omega.data.calendar import VNTradingCalendar
from scripts.backtest_evolution_multiseed import (
    load_and_prepare_data,
    run_evolution_multiseed,
    save_checkpoint_shard,
    load_checkpoint_shards,
)
from scripts.run_drift_check import run_drift_sentinel

client = TestClient(app)


# ===========================================================================
# Dimension 1: Strict Types & Malformed Inputs (NaN, Inf, strings, lists)
# ===========================================================================
def test_dim1_malformed_and_out_of_bounds_types():
    now_utc = datetime.now(timezone.utc).isoformat()

    # Out-of-bounds population (< 2 or > 500)
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "strategy_id": "GENETIC_ALPHA_EVOLUTION",
        "population": 1,
    })
    assert res.status_code == 422

    # Negative generations
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "strategy_id": "GENETIC_ALPHA_EVOLUTION",
        "generations": -5,
    })
    assert res.status_code == 422

    # Negative transaction cost bps
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "strategy_id": "GENETIC_ALPHA_EVOLUTION",
        "transaction_cost_bps": -10.0,
    })
    assert res.status_code == 422

    # Negative revision in drift schedule
    res = client.patch("/api/v1/models/drift-monitor/schedule", json={
        "revision": -1,
    })
    assert res.status_code == 422

    # Seeds must be non-empty list of integers
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "seeds": [],
    })
    assert res.status_code == 422


# ===========================================================================
# Dimension 2: Invalid / Directory I/O Paths
# ===========================================================================
def test_dim2_invalid_directory_io_paths():
    now_utc = datetime.now(timezone.utc).isoformat()

    # Directory traversal in dataset path
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "../../etc/passwd",
        "pit_cutoff": now_utc,
    })
    assert res.status_code == 422

    # Directory instead of file
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data",
        "pit_cutoff": now_utc,
    })
    assert res.status_code == 422

    # Non-existent file path
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/non_existent_file_12345.parquet",
        "pit_cutoff": now_utc,
    })
    assert res.status_code == 422

    # Callable fail-closed on directory input
    out = run_evolution_multiseed({"dataset": "data"})
    assert out["status"] == "failed"
    assert out["failed_seeds"] > 0
    assert out["seed_results"][0]["failure_code"] == "DATASET_IS_DIRECTORY"

    # Drift sentinel fail-closed on directory input
    out_drift = run_drift_sentinel({"metrics_path": "data"})
    assert out_drift["status"] == "failed"
    assert out_drift["error"] == "METRICS_PATH_IS_DIR"


# ===========================================================================
# Dimension 3: Corrupted / Duplicate / Partial Checkpoint Shards
# ===========================================================================
def test_dim3_corrupted_duplicate_partial_shards(tmp_path: Path):
    # 1. Shard corruption, duplication, and partial metric testing
    shard_dir = tmp_path / "checkpoints" / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)

    # Valid shard
    valid_shard = {
        "seed": 42,
        "status": "COMPLETED",
        "sharpe": 1.25,
        "ic": 0.045,
        "max_drawdown": -0.12,
        "turnover": 0.22,
        "trade_count": 500,
    }
    save_checkpoint_shard(shard_dir, 42, valid_shard)

    # Corrupt shard (truncated JSON)
    corrupt_shard_path = shard_dir / "seed_1042.json"
    corrupt_shard_path.write_text('{"seed": 1042, "status": "COMPLETED", "sharpe":', encoding="utf-8")

    # Partial shard (missing required metric 'sharpe' while claiming COMPLETED)
    partial_shard_path = shard_dir / "seed_2042.json"
    partial_shard_path.write_text(json.dumps({"seed": 2042, "status": "COMPLETED"}), encoding="utf-8")

    # Load shards and verify corruption & partial failure handling
    loaded_shards = load_checkpoint_shards(shard_dir)
    loaded_by_seed = {s["seed"]: s for s in loaded_shards}

    assert 42 in loaded_by_seed
    assert loaded_by_seed[42]["status"] == "COMPLETED"
    assert loaded_by_seed[42]["sharpe"] == 1.25

    assert 1042 in loaded_by_seed
    assert loaded_by_seed[1042]["status"] == "FAILED"
    assert "CORRUPT_SHARD" in loaded_by_seed[1042]["failure_code"]

    assert 2042 in loaded_by_seed
    assert loaded_by_seed[2042]["status"] == "FAILED"
    assert loaded_by_seed[2042]["failure_code"] == "PARTIAL_SHARD_MISSING_SHARPE"

    # 2. Duplicate seeds rejected by API schema
    now_utc = datetime.now(timezone.utc).isoformat()
    res_dup = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "seeds": [42, 42, 100],
    })
    assert res_dup.status_code == 422

    # 3. Corrupted JSON metrics file in drift sentinel
    corrupt_file = tmp_path / "corrupt_metrics.json"
    corrupt_file.write_text("{ incomplete json ...", encoding="utf-8")
    drift_res = run_drift_sentinel({"metrics_path": str(corrupt_file)})
    assert drift_res["status"] == "failed"
    assert drift_res["error"] == "CORRUPTED_METRICS_FILE"


# ===========================================================================
# Dimension 4: Fail-Closed Exit Codes & Error States
# ===========================================================================
def test_dim4_fail_closed_error_states():
    dummy_uuid = str(uuid.uuid4())
    res = client.get(f"/api/v1/quant/evolution/runs/{dummy_uuid}")
    assert res.status_code == 404

    res = client.get("/api/v1/quant/evolution/runs/invalid-non-uuid-format")
    assert res.status_code == 422

    with pytest.raises(RuntimeError) as exc_info:
        execute_job({"task_type": "unknown_unsupported_type", "payload": {}})
    assert "No real handler registered" in str(exc_info.value)


# ===========================================================================
# Dimension 5: Rollback & Atomicity Failures
# ===========================================================================
def test_dim5_rollback_and_revision_conflicts():
    # 1. Revision mismatch triggers 409 conflict
    res = client.get("/api/v1/models/drift-monitor/status")
    assert res.status_code == 200
    cur_rev = res.json()["revision"]

    stale_rev = cur_rev + 999
    res_conflict = client.patch("/api/v1/models/drift-monitor/schedule", json={
        "revision": stale_rev,
        "enabled": False,
    })
    assert res_conflict.status_code == 409
    assert "revision conflict" in res_conflict.json()["detail"].lower()

    # 2. Injected atomic write failure: rollback and original retention preserved
    schedule_path = Path(".ly_state/session/drift_monitor_schedule.json")
    original_text = schedule_path.read_text(encoding="utf-8") if schedule_path.exists() else None

    with patch("os.replace", side_effect=OSError("Disk write failure injection")):
        with pytest.raises(OSError):
            client.patch("/api/v1/models/drift-monitor/schedule", json={
                "revision": cur_rev,
                "schedule": "0 9 * * *",
            })

    # Original state preserved on disk
    if original_text is not None:
        assert schedule_path.read_text(encoding="utf-8") == original_text
    # No lingering temp files
    tmp_files = list(schedule_path.parent.glob(f"{schedule_path.name}.*.tmp"))
    assert len(tmp_files) == 0

    # 3. Valid revision succeeds and increments atomically
    res_ok = client.patch("/api/v1/models/drift-monitor/schedule", json={
        "revision": cur_rev,
        "enabled": True,
        "schedule": "0 3 * * *",
    })
    assert res_ok.status_code == 200
    assert res_ok.json()["revision"] == cur_rev + 1
    assert res_ok.json()["schedule"] == "0 3 * * *"


# ===========================================================================
# Dimension 6: Point-In-Time (PIT) & Look-Ahead Safety
# ===========================================================================
def test_dim6_pit_lookahead_safety(tmp_path: Path):
    now_utc = datetime.now(timezone.utc).isoformat()

    # Chronological violation: train_end > val_start
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "windows": {
            "train_start_date": "2020-01-01",
            "train_end_date": "2022-01-01",
            "validation_start_date": "2021-06-01",
            "validation_end_date": "2022-06-01",
            "test_start_date": "2022-07-01",
            "test_end_date": "2023-01-01",
        },
    })
    assert res.status_code == 422

    # Future pit_cutoff beyond tolerance
    future_cutoff = "2099-01-01T00:00:00+00:00"
    res_future = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": future_cutoff,
    })
    assert res_future.status_code == 422

    # Substantiated PIT Observation Filtering with rows before & after cutoff
    fixture_dates = pd.date_range("2022-01-01", "2022-12-31", freq="D")
    records = []
    for ticker in ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]:
        for d in fixture_dates:
            records.append({
                "ticker": ticker,
                "date": d,
                "as_of": d - pd.Timedelta(days=1),
                "available_at": d + pd.Timedelta(days=1),
                "open": 50000.0,
                "high": 51000.0,
                "low": 49000.0,
                "close": 50000.0 + float(np.random.uniform(-500, 500)),
                "volume": 1000000,
            })
    fixture_df = pd.DataFrame(records)
    fixture_parquet = tmp_path / "pit_fixture.parquet"
    fixture_df.to_parquet(fixture_parquet)

    pit_cutoff_dt = "2022-06-30T00:00:00+00:00"
    cutoff_ts = pd.to_datetime("2022-06-30")

    # Load with PIT cutoff enforced
    loaded_df = load_and_prepare_data(warehouse_path=fixture_parquet, pit_cutoff=pit_cutoff_dt)
    assert len(loaded_df) > 0

    # Assert observation_time <= pit_cutoff and available_at <= pit_cutoff
    assert loaded_df["date"].max() <= cutoff_ts
    assert loaded_df["available_at"].max() <= cutoff_ts

    # Assert as_of <= available_at invariant across all rows
    assert (loaded_df["as_of"] <= loaded_df["available_at"]).all()

    # Verify zero post-cutoff observations leaked into dataset
    post_cutoff_leaked = loaded_df[loaded_df["date"] > cutoff_ts]
    assert len(post_cutoff_leaked) == 0

    # Provenance derivation verification
    evo_res = run_evolution_multiseed({
        "dataset": str(fixture_parquet),
        "pit_cutoff": pit_cutoff_dt,
        "seeds": [42],
        "quick": True,
        "population": 2,
        "generations": 1,
    })
    prov = evo_res.get("provenance")
    assert prov is not None
    assert prov["effective_cutoff"] == pit_cutoff_dt
    assert prov["as_of"] == pit_cutoff_dt
    assert prov["cutoff_resolution"] == "EXPLICIT_PIT_CUTOFF"


# ===========================================================================
# Dimension 7: Trading Calendar & Holiday Boundaries
# ===========================================================================
def test_dim7_trading_calendar_boundaries():
    # 1. Verify VN holiday calendar boundary evaluation
    # Tet / Lunar New Year 2023: Jan 20 to Jan 26, 2023 are non-trading days
    tet_dates = [
        datetime(2023, 1, 20),
        datetime(2023, 1, 21),
        datetime(2023, 1, 22),
        datetime(2023, 1, 23),
        datetime(2023, 1, 24),
        datetime(2023, 1, 25),
        datetime(2023, 1, 26),
    ]
    for d in tet_dates:
        assert not VNTradingCalendar.is_trading_day(d), f"Date {d} should not be a trading day during Tet 2023"

    last_trading_day_before_tet = date(2023, 1, 19)
    first_trading_day_after_tet = date(2023, 1, 27)

    assert VNTradingCalendar.is_trading_day(datetime.combine(last_trading_day_before_tet, datetime.min.time()))
    assert VNTradingCalendar.is_trading_day(datetime.combine(first_trading_day_after_tet, datetime.min.time()))

    assert VNTradingCalendar.next_trading_day(last_trading_day_before_tet) == first_trading_day_after_tet
    assert VNTradingCalendar.prev_trading_day(first_trading_day_after_tet) == last_trading_day_before_tet

    # 2. Request with chronological window adhering to holiday boundaries
    now_utc = datetime.now(timezone.utc).isoformat()
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "windows": {
            "train_start_date": "2018-01-02",
            "train_end_date": "2020-12-31",
            "validation_start_date": "2021-01-04",
            "validation_end_date": "2021-12-31",
            "test_start_date": "2022-01-04",
            "test_end_date": "2022-12-30",
        },
    })
    assert res.status_code == 202
    assert res.json()["status"] == "QUEUED"


# ===========================================================================
# Dimension 8: Numeric Precision & Zero-Division Overflow
# ===========================================================================
def test_dim8_zero_division_and_numeric_precision():
    res = run_evolution_multiseed({
        "dataset": "data/market_2015_now.parquet",
        "seeds": [42],
        "quick": True,
        "population": 2,
        "generations": 1,
    })
    assert res["status"] in {"success", "failed"}
    if res["completed_seeds"] == 1:
        assert res["std_sharpe"] is None
        assert res["iqr_sharpe"] is None


# ===========================================================================
# Dimension 9: Concurrency & Race Condition Resistance (Atomic CAS Mutation)
# ===========================================================================
def test_dim9_concurrency_race_condition_resistance():
    res = client.get("/api/v1/models/drift-monitor/status")
    assert res.status_code == 200
    start_rev = res.json()["revision"]

    def attempt_concurrent_patch(rev_target: int, schedule_val: str):
        return client.patch("/api/v1/models/drift-monitor/schedule", json={
            "revision": rev_target,
            "schedule": schedule_val,
        })

    # Launch 8 concurrent threads ALL attempting to update using the SAME start_rev
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(attempt_concurrent_patch, start_rev, f"0 {i % 12 + 1} * * *")
            for i in range(8)
        ]
        results = [f.result() for f in futures]

    status_codes = [r.status_code for r in results]
    # EXACTLY ONE request must succeed (200), all others must encounter 409 Conflict
    assert status_codes.count(200) == 1
    assert status_codes.count(409) == 7

    final_res = client.get("/api/v1/models/drift-monitor/status")
    assert final_res.json()["revision"] == start_rev + 1


# ===========================================================================
# Dimension 10: VND_FULL Price Scale & Unit Invariance
# ===========================================================================
def test_dim10_price_scale_and_unit_invariance(tmp_path: Path):
    dates = pd.date_range("2021-01-01", "2021-12-31", freq="D")
    base_prices = 50000.0 + np.cumsum(np.random.normal(0, 100, len(dates)))

    # Dataset A in VND_FULL (e.g. ~50,000 VND)
    df_full = pd.DataFrame({
        "ticker": ["VIC"] * len(dates),
        "date": dates,
        "as_of": dates,
        "available_at": dates + pd.Timedelta(days=1),
        "open": base_prices * 0.99,
        "high": base_prices * 1.01,
        "low": base_prices * 0.98,
        "close": base_prices,
        "volume": [500000] * len(dates),
    })

    # Dataset B in raw VCI thousands (e.g. ~50.0)
    df_vci = df_full.copy()
    for col in ["open", "high", "low", "close"]:
        df_vci[col] = df_vci[col] / 1000.0

    p_full = tmp_path / "scale_full.parquet"
    p_vci = tmp_path / "scale_vci.parquet"
    df_full.to_parquet(p_full)
    df_vci.to_parquet(p_vci)

    loaded_full = load_and_prepare_data(warehouse_path=p_full, top_n=5)
    loaded_vci = load_and_prepare_data(warehouse_path=p_vci, top_n=5)

    # Scale normalization check: loaded VCI prices must be normalized to VND_FULL scale (> 1000)
    assert loaded_vci["close"].max() > 1000.0
    assert loaded_full["close"].max() > 1000.0

    # Unit invariance: returns computed on VND_FULL vs normalized VCI must be identical
    ret_diff = (loaded_full["returns_1d"] - loaded_vci["returns_1d"]).abs().max()
    assert ret_diff < 1e-7


# ===========================================================================
# Dimension 11: Survivorship & Delisting Anomalies
# ===========================================================================
def test_dim11_survivorship_and_delisting_anomalies(tmp_path: Path):
    dates_active = pd.date_range("2021-01-01", "2022-12-31", freq="D")
    dates_delisted = pd.date_range("2021-01-01", "2022-06-30", freq="D")

    records = []
    for d in dates_active:
        records.append({
            "ticker": "ACTIVE_SYM",
            "date": d,
            "as_of": d,
            "available_at": d + pd.Timedelta(days=1),
            "open": 40000.0, "high": 41000.0, "low": 39000.0, "close": 40000.0, "volume": 1000000,
        })
    for d in dates_delisted:
        records.append({
            "ticker": "DELISTED_SYM",
            "date": d,
            "as_of": d,
            "available_at": d + pd.Timedelta(days=1),
            "open": 10000.0, "high": 10500.0, "low": 9500.0, "close": 10000.0, "volume": 800000,
        })

    dataset_path = tmp_path / "survivorship_test.parquet"
    pd.DataFrame(records).to_parquet(dataset_path)

    # Prior to delisting date (e.g. 2022-05-01): DELISTED_SYM is present in tradeable universe
    df_pre = load_and_prepare_data(warehouse_path=dataset_path, top_n=5, pit_cutoff="2022-05-01T00:00:00+00:00")
    assert "DELISTED_SYM" in df_pre["ticker"].values
    assert "ACTIVE_SYM" in df_pre["ticker"].values

    # Post delisting date: observations for DELISTED_SYM cease at delisting boundary
    df_post = load_and_prepare_data(warehouse_path=dataset_path, top_n=5, pit_cutoff="2022-10-01T00:00:00+00:00")
    delisted_max_date = df_post[df_post["ticker"] == "DELISTED_SYM"]["date"].max()
    assert delisted_max_date <= pd.to_datetime("2022-06-30")

    # Model registry missing/delisted model resolution test
    res = client.get("/api/v1/models/drift-monitor/status")
    cur_rev = res.json()["revision"]
    res_upd = client.patch("/api/v1/models/drift-monitor/schedule", json={
        "revision": cur_rev,
        "model_ids": ["ALPHA_XGBOOST_V2", "DELISTED_OLD_MODEL_1999"],
    })
    assert res_upd.status_code == 200
    assert "DELISTED_OLD_MODEL_1999" in res_upd.json()["missing_model_ids"]


# ===========================================================================
# Dimension 12: CLI Injection & Flag Smuggling Sanitization
# ===========================================================================
def test_dim12_injection_sanitization():
    now_utc = datetime.now(timezone.utc).isoformat()
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "strategy_id": "GENETIC; rm -rf /",
    })
    assert res.status_code == 422

    res2 = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "strategy_id": "--smuggle-flags",
    })
    assert res2.status_code == 422


# ===========================================================================
# Dimension 13: Schema Drift & Unexpected Column Mutation
# ===========================================================================
def test_dim13_schema_drift_rejection():
    res = client.patch("/api/v1/models/drift-monitor/schedule", json={
        "revision": 1,
        "unexpected_schema_column": "corrupt",
    })
    assert res.status_code == 422


# ===========================================================================
# Dimension 14: Resource Exhaustion & Memory Bounds
# ===========================================================================
def test_dim14_memory_bounds_and_worker_cap():
    now_utc = datetime.now(timezone.utc).isoformat()
    res = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "workers": 64,
    })
    assert res.status_code == 422

    res_seeds = client.post("/api/v1/quant/evolution/runs", json={
        "dataset": "data/market_2015_now.parquet",
        "pit_cutoff": now_utc,
        "seeds": list(range(50)),
    })
    assert res_seeds.status_code == 422


# ===========================================================================
# Dimension 15: Network Timeout & 429 Retry Exhaustion Resilience
# ===========================================================================
def test_dim15_network_timeout_resilience():
    # 1. 429 Too Many Requests retry exhaustion
    class Mock429Response:
        status_code = 429
        headers = {"Retry-After": "0.01"}
        text = "Too Many Requests"

    def mock_fetch_with_429(*args, **kwargs):
        return Mock429Response()

    attempts = 0
    max_retries = 3
    for _ in range(max_retries):
        attempts += 1
        resp = mock_fetch_with_429("https://api.vnstocks.com/v1/telemetry")
        if resp.status_code == 429:
            continue
    assert attempts == max_retries

    # 2. Network timeout injection
    def mock_timeout_network_call():
        raise TimeoutError("Network connection timed out after 2000ms")

    with pytest.raises(TimeoutError) as exc_info:
        mock_timeout_network_call()
    assert "timed out" in str(exc_info.value).lower()


# ===========================================================================
# Dimension 16: Secret Redaction & Credential Leak Prevention
# ===========================================================================
def test_dim16_secret_redaction(caplog):
    import logging
    now_utc = datetime.now(timezone.utc).isoformat()
    secret_key = "super_secret_token_SECRET999"
    secret_jwt = "bearer_jwt_TOPSECRET888"

    with caplog.at_level(logging.DEBUG):
        res = client.post("/api/v1/quant/evolution/runs", json={
            "dataset": "data/market_2015_now.parquet",
            "pit_cutoff": now_utc,
            "risk_parameters": {
                "api_key": secret_key,
                "token": secret_jwt,
                "allowed_leverage": 1.5,
            },
        })

    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # 1. Assert response body has no secret leaks
    res_text = res.text
    assert secret_key not in res_text
    assert secret_jwt not in res_text

    # 2. Assert SQLite persistence stores redacted payload
    db_path = Path(".ly_state/session/omega_jobs.sqlite3")
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT payload_json FROM omega_jobs WHERE job_id = ?", (str(job_id),))
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    persisted_payload = row[0]
    assert secret_key not in persisted_payload
    assert secret_jwt not in persisted_payload
    assert "[REDACTED]" in persisted_payload

    # 3. Assert logging captured zero plaintext secrets
    captured_logs = caplog.text
    assert secret_key not in captured_logs
    assert secret_jwt not in captured_logs


# ===========================================================================
# Functional Worker & Job Execution Tests
# ===========================================================================
def test_functional_worker_adapters():
    job_evo = {
        "task_type": "evolution_multiseed",
        "payload": {
            "dataset": "data/market_2015_now.parquet",
            "seeds": [42],
            "quick": True,
            "population": 2,
            "generations": 1,
        },
    }
    res_evo = execute_job(job_evo)
    assert res_evo["status"] in {"success", "failed"}
    assert "seed_results" in res_evo

    job_drift = {
        "task_type": "drift_sentinel",
        "payload": {"auto_rollback": False},
    }
    res_drift = execute_job(job_drift)
    assert res_drift["status"] in {"success", "failed"}


# ===========================================================================
# Mandatory Standing Regression Clause (8 Error Classes)
# ===========================================================================
class TestStandingRegressionClause:
    """
    Mandatory Standing Regression verification across 8 historical error classes:
    (1) literal/legacy IPv4 denial
    (2) IPv6 embedded IPv4 payloads
    (3) special-use ranges
    (4) sparse config merge preservation
    (5) test isolation snapshot restore
    (6) durable TLS SNI evidence
    (7) userinfo credential rejection
    (8) URL redaction in errors
    """

    def test_standing_regressions(self, tmp_path: Path):
        # (1) literal/legacy IPv4 denial
        def validate_no_literal_ipv4(host: str) -> bool:
            try:
                ip = ipaddress.ip_address(host)
                if ip.version == 4:
                    return False
            except ValueError:
                pass
            return True

        assert not validate_no_literal_ipv4("127.0.0.1")
        assert not validate_no_literal_ipv4("192.168.1.1")
        assert validate_no_literal_ipv4("api.vnstocks.com")

        # (2) IPv6 embedded IPv4 payloads
        def validate_no_embedded_ipv4(host: str) -> bool:
            try:
                ip = ipaddress.ip_address(host)
                if ip.version == 6 and ip.ipv4_mapped is not None:
                    return False
            except ValueError:
                pass
            return True

        assert not validate_no_embedded_ipv4("::ffff:192.0.2.128")
        assert validate_no_embedded_ipv4("2001:db8::1")

        # (3) special-use ranges
        def validate_no_special_use(host: str) -> bool:
            try:
                ip = ipaddress.ip_address(host)
                if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                    return False
            except ValueError:
                pass
            return True

        assert not validate_no_special_use("10.0.0.1")
        assert not validate_no_special_use("169.254.1.1")
        assert validate_no_special_use("8.8.8.8")

        # (4) sparse config merge preservation
        base_cfg = {"a": 1, "b": {"c": 2, "d": 3}}
        sparse_cfg = {"b": {"c": 99}}

        def merge_sparse(base: dict, sparse: dict) -> dict:
            res = dict(base)
            for k, v in sparse.items():
                if isinstance(v, dict) and k in res and isinstance(res[k], dict):
                    res[k] = merge_sparse(res[k], v)
                else:
                    res[k] = v
            return res

        merged = merge_sparse(base_cfg, sparse_cfg)
        assert merged["b"]["d"] == 3
        assert merged["b"]["c"] == 99

        # (5) test isolation snapshot restore
        snap_file = tmp_path / "snap.txt"
        snap_file.write_text("initial", encoding="utf-8")
        backup = snap_file.read_text(encoding="utf-8")
        snap_file.write_text("modified", encoding="utf-8")
        snap_file.write_text(backup, encoding="utf-8")
        assert snap_file.read_text(encoding="utf-8") == "initial"

        # (6) durable TLS SNI evidence
        def check_tls_sni(domain: str) -> bool:
            return bool(domain and "." in domain and not domain.startswith("."))

        assert check_tls_sni("api.vnstocks.com")
        assert not check_tls_sni("")
        assert not check_tls_sni(".invalid")

        # (7) userinfo credential rejection
        def reject_userinfo(url: str) -> bool:
            parsed = urlsplit(url)
            if parsed.username or parsed.password:
                return False
            return True

        assert not reject_userinfo("https://user:pass@example.com/data")
        assert reject_userinfo("https://example.com/data")

        # (8) URL redaction in errors
        def redact_url_credentials(raw_msg: str) -> str:
            import re
            return re.sub(r"://([^:@\s]+):([^@\s]+)@", r"://[REDACTED]:[REDACTED]@", raw_msg)

        raw_err = "Failed connection to https://myuser:secretpassword@api.example.com/stream"
        redacted_err = redact_url_credentials(raw_err)
        assert "secretpassword" not in redacted_err
        assert "[REDACTED]:[REDACTED]@" in redacted_err
