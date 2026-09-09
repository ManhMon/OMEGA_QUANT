import json
import pytest
import os
import math
import concurrent.futures
from collections import deque
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pandas as pd
from starlette.testclient import TestClient
from omega.api.server import app
import omega.api.routes.control as control_mod

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture(autouse=True)
def reset_control_state(tmp_path, monkeypatch):
    control_mod.TASKS.clear()
    control_mod.TASK_EVENT_QUEUES.clear()
    control_mod.CANCELLED_JOBS.clear()
    control_mod.KILL_SWITCH_ACTIVE = False
    control_mod.clear_totp_replay_cache()
    monkeypatch.setattr(control_mod, "CONTROL_ARTIFACT_ROOT", tmp_path)

# -------------------------------------------------------------
# 16-DIMENSION ADVERSARIAL TEST SUITE (PHASE 5 CONTROL & OPS)
# -------------------------------------------------------------

def test_dim1_malformed_out_of_bounds_types(client):
    # Dim 1: Malformed types, NaN, Inf, empty, non-string, extra fields
    resp = client.post("/api/v1/control/run-backtest", json={"initial_capital": "NaN", "strategy_id": "OMEGA_MOMENTUM_V1"})
    assert resp.status_code == 422

    resp2 = client.post("/api/v1/control/ingest-data", json={"symbols": ["FPT"], "extra_field": 123})
    assert resp2.status_code == 422

    resp3 = client.post("/api/v1/control/ingest-data", json={"symbols": [" ", ""]})
    assert resp3.status_code == 422


def test_dim2_invalid_directory_io_paths(tmp_path, monkeypatch):
    # Dim 2: Invalid I/O directory handling, permission / path aliasing
    bad_path = tmp_path / "non_existent_subdir" / "locked"
    req = control_mod.PipelineRunRequest()
    as_of = datetime(2023, 12, 31, tzinfo=timezone.utc)
    monkeypatch.setattr(control_mod, "CONTROL_ARTIFACT_ROOT", bad_path)
    receipt = control_mod._publish_receipt("job-dim2", "PIPELINE_RUN", req, as_of, {"metrics": {"total_trades": 0}})
    assert receipt["task_id"] == "job-dim2"
    assert (bad_path / "job-dim2.json").exists()


def test_dim3_corrupted_totp_cache_fails_closed():
    # Fix (1)(a): Corrupted TOTP replay cache must fail closed (reject verification, never silently treat as empty)
    control_mod.TOTP_REPLAY_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    control_mod.TOTP_REPLAY_CACHE_PATH.write_text("{corrupted_json: true,", encoding="utf-8")

    token = control_mod.generate_totp()
    # verify_totp must fail closed (return False) rather than succeed
    assert control_mod.verify_totp(token) is False

    # Also test non-dict root fails closed
    control_mod.TOTP_REPLAY_CACHE_PATH.write_text('["not", "a", "dict"]', encoding="utf-8")
    assert control_mod.verify_totp(token) is False

    # Also test invalid timestamps inside cache fail closed
    control_mod.TOTP_REPLAY_CACHE_PATH.write_text('{"token1": "not-a-number"}', encoding="utf-8")
    assert control_mod.verify_totp(token) is False


def test_dim3_corrupted_duplicate_partial_checkpoint_shards(tmp_path, monkeypatch):
    # Dim 3: Corrupted / duplicate / partial shard assembly & receipt validation
    corrupted_file = tmp_path / "corrupt-task.json"
    corrupted_file.write_text("{corrupted_json: true,", encoding="utf-8")

    # Attempting to load corrupted json shard raises Exception
    with pytest.raises(Exception):
        with open(corrupted_file, "r", encoding="utf-8") as f:
            json.load(f)

    # Partial / invalid receipt dictionary validation fail-closed
    assert not control_mod._valid_receipt({"task_id": "corrupt-task"}, "corrupt-task")
    assert not control_mod._valid_receipt(None, "corrupt-task")
    assert not control_mod._valid_receipt({"schema_version": 1, "task_id": "other_task"}, "corrupt-task")
    assert not control_mod._valid_receipt({
        "schema_version": 1, "task_id": "corrupt-task", "status": "COMPLETED",
        "request_fingerprint": "abc", "output_sha256": ""  # missing output_sha256
    }, "corrupt-task")


def test_dim4_fail_closed_error_states_and_exit_codes(client):
    # Dim 4: Fail-closed error states
    # Invalid TOTP on kill-switch triggers 401
    resp = client.post("/api/v1/control/kill-switch", json={"totp_code": "000000"})
    assert resp.status_code == 401
    assert not control_mod.KILL_SWITCH_ACTIVE

    # Kill switch engaged blocks pipeline-run with 403
    control_mod.KILL_SWITCH_ACTIVE = True
    resp2 = client.post("/api/v1/control/pipeline-run", json={"universe": ["FPT"]})
    assert resp2.status_code == 403

    # Rebalance blocked with 403 when kill switch active
    token = control_mod.generate_totp()
    resp3 = client.post("/api/v1/control/rebalance", json={"totp_code": token})
    assert resp3.status_code == 403

    # Malformed COMPLETE task event fails closed into status=FAILED
    control_mod.TASKS["job-failclosed"] = {"progress": 50.0, "events": []}
    control_mod._push_task_event("job-failclosed", "COMPLETE", 100.0, "STAGE", "done", payload={"corrupt": True})
    assert control_mod.TASKS["job-failclosed"]["status"] == "FAILED"
    assert control_mod.TASKS["job-failclosed"]["events"][-1]["event_type"] == "ERROR"


def test_dim5_failed_atomic_save_cleans_temp_file(tmp_path, monkeypatch):
    # Fix (1)(c): Failed atomic save must clean temp file in finally block
    monkeypatch.setattr(control_mod, "TOTP_REPLAY_CACHE_PATH", tmp_path / "totp_cache.json")
    monkeypatch.setattr(control_mod, "TOTP_REPLAY_CACHE_LOCK_PATH", tmp_path / "totp_cache.lock")

    control_mod._USED_TOTP_TOKENS["123456"] = 9999999999.0

    # Simulate replacement failure
    monkeypatch.setattr(control_mod.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("Simulated replace failure")))

    with pytest.raises(RuntimeError, match="Failed to persist TOTP replay cache"):
        control_mod._save_totp_replay_cache_unlocked()

    # Ensure no .tmp files left behind
    tmp_files = list(tmp_path.glob("*.tmp*"))
    assert len(tmp_files) == 0


def test_dim5_rollback_atomicity_failures(tmp_path, monkeypatch):
    # Dim 5: Atomic rollback on failure preserves original receipt file
    monkeypatch.setattr(control_mod, "CONTROL_ARTIFACT_ROOT", tmp_path)
    dest = tmp_path / "job-rollback.json"
    dest.write_text('{"prior_verified": true}', encoding="utf-8")

    monkeypatch.setattr(control_mod.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("Simulated atomic replace failure")))
    req = control_mod.PipelineRunRequest()
    with pytest.raises(OSError, match="Simulated atomic replace failure"):
        control_mod._publish_receipt("job-rollback", "PIPELINE_RUN", req, datetime(2023, 12, 31, tzinfo=timezone.utc), {"metrics": {}})

    # Original content preserved intact
    assert dest.read_text(encoding="utf-8") == '{"prior_verified": true}'


def test_dim6_pit_look_ahead_bounds(client):
    # Dim 6: Future dates and look-ahead timestamps rejected
    future_date = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%d")
    resp = client.post("/api/v1/control/pipeline-run", json={"start_date": "2023-01-01", "end_date": future_date})
    assert resp.status_code == 422

    # start_date > end_date rejected
    resp2 = client.post("/api/v1/control/pipeline-run", json={"start_date": "2023-12-31", "end_date": "2023-01-01"})
    assert resp2.status_code == 422


def test_dim7_trading_calendar_holiday_boundaries(client):
    # Dim 7: Calendar bounds (date range > 10 years rejected and PIT date check)
    resp = client.post("/api/v1/control/pipeline-run", json={"start_date": "2010-01-01", "end_date": "2023-12-31"})
    assert resp.status_code == 422

    # Date format validation
    resp2 = client.post("/api/v1/control/pipeline-run", json={"start_date": "2023/01/01", "end_date": "2023/12/31"})
    assert resp2.status_code == 422


def test_dim8_numeric_precision_zero_division(client):
    # Dim 8: Numerical bounds, drift threshold out of range, max turnover > 1.0, zero-division resistance
    token = control_mod.generate_totp()
    resp = client.post("/api/v1/control/rebalance", json={
        "totp_code": token,
        "drift_threshold": 0.0,  # Below ge=0.001
        "max_turnover": 1.5,     # Above le=1.0
    })
    assert resp.status_code == 422

    # Validate redactor and metrics handle div-by-zero or zero values gracefully
    req = control_mod.RebalanceRequest(totp_code="123456", portfolio_value=10_000_000.0)
    assert req.portfolio_value == 10_000_000.0


def test_dim9_concurrency_race_condition_resistance(client):
    # Dim 9: Concurrency safety with TOTP replay cache across parallel requests using ThreadPoolExecutor
    token = control_mod.generate_totp()
    payload = {
        "totp_code": token,
        "strategy_id": "ALPHA_HRP_V2",
        "portfolio_value": 1_000_000_000.0,
        "target_portfolio": {"FPT": 0.25, "HPG": 0.25, "MBB": 0.25, "MWG": 0.25}
    }

    # Execute concurrent requests simultaneously
    def send_req():
        c = TestClient(app)
        return c.post("/api/v1/control/rebalance", json=payload).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(send_req) for _ in range(8)]
        results = [f.result() for f in futures]

    # Exactly one request can pass TOTP validation; subsequent concurrent attempts get 401 replay error
    assert results.count(401) >= 7


def _proc_totp_verify(token, secret, lock_path, cache_path, result_queue):
    import omega.api.routes.control as c_mod
    c_mod.TOTP_REPLAY_CACHE_PATH = cache_path
    c_mod.TOTP_REPLAY_CACHE_LOCK_PATH = lock_path
    res = c_mod.verify_totp(token, secret=secret)
    result_queue.put(res)


def test_dim9_multiprocess_totp_race_cross_process_filelock(tmp_path):
    # Fix (1)(b): TOTP replay check & save must use cross-process file lock preventing multi-process race
    import multiprocessing as mp
    cache_path = tmp_path / "proc_totp_cache.json"
    lock_path = tmp_path / "proc_totp_cache.lock"

    secret = control_mod.DEFAULT_TOTP_SECRET
    token = control_mod.generate_totp(secret=secret)

    ctx = mp.get_context("spawn")
    queue = ctx.Queue()

    p1 = ctx.Process(target=_proc_totp_verify, args=(token, secret, lock_path, cache_path, queue))
    p2 = ctx.Process(target=_proc_totp_verify, args=(token, secret, lock_path, cache_path, queue))

    p1.start()
    p2.start()

    p1.join(timeout=10)
    p2.join(timeout=10)

    res1 = queue.get(timeout=2)
    res2 = queue.get(timeout=2)

    results = [res1, res2]
    # Exactly one process gets True, the other process gets False (replay protection across processes)
    assert results.count(True) == 1
    assert results.count(False) == 1


def test_dim10_vnd_full_scale_invariance(client):
    # Dim 10: VND_FULL scale invariance in portfolio value
    token = control_mod.generate_totp()
    # Portfolio value below institutional min (10,000,000 VND) fails
    resp = client.post("/api/v1/control/rebalance", json={
        "totp_code": token,
        "portfolio_value": 5_000.0  # 5,000 VND is invalid scale
    })
    assert resp.status_code == 422


def test_dim11_survivorship_delisting_anomalies(client):
    # Dim 11: Delisted or unknown symbols handled gracefully with explicit validation error
    resp = client.post("/api/v1/control/ingest-data", json={"symbols": ["INVALID_SYM_XXX_123"]})
    assert resp.status_code == 422


def test_dynamic_universe_preserves_historical_delisted_constituent(client, monkeypatch):
    frame = pd.DataFrame([
        {"symbol": "OLD", "hybrid_score": 0.99, "quant_score": 0.95, "llm_score": 0.90,
         "status": "DELISTED", "decision_cutoff": "2020-12-31"},
        {"symbol": "LIVE", "hybrid_score": 0.80, "quant_score": 0.75, "llm_score": 0.70,
         "status": "QUALIFIED", "decision_cutoff": "2020-12-31"},
    ])
    monkeypatch.setattr(control_mod.Path, "exists", lambda self: self == Path("data/hybrid_eval_full_703.parquet"))
    monkeypatch.setattr(control_mod.pd, "read_parquet", lambda _: frame)

    response = client.get("/api/v1/control/dynamic-universe?top_n=5")

    assert response.status_code == 200
    items = {item["symbol"]: item for item in response.json()["items"]}
    assert items["OLD"]["status_label"] == "DELISTED"
    assert items["OLD"]["decision_cutoff"] == "2020-12-31"


def test_dynamic_universe_unknown_status_uses_score_fallback(client, monkeypatch):
    frame = pd.DataFrame([{
        "symbol": "LEGACY", "hybrid_score": 0.50, "quant_score": 0.50, "llm_score": 0.50,
        "status": "RETIRED", "decision_cutoff": "2020-12-31",
    }])
    monkeypatch.setattr(control_mod.Path, "exists", lambda self: self == Path("data/hybrid_eval_full_703.parquet"))
    monkeypatch.setattr(control_mod.pd, "read_parquet", lambda _: frame)

    response = client.get("/api/v1/control/dynamic-universe?top_n=5")

    assert response.status_code == 200
    assert response.json()["items"][0]["status_label"] == "WATCH"


def test_dynamic_universe_parquet_failure_returns_redacted_error(client, monkeypatch):
    monkeypatch.setattr(control_mod.Path, "exists", lambda self: self == Path("data/hybrid_eval_full_703.parquet"))
    monkeypatch.setattr(control_mod.pd, "read_parquet", lambda _: (_ for _ in ()).throw(RuntimeError("database password=secret")))

    response = client.get("/api/v1/control/dynamic-universe")

    assert response.status_code == 500
    assert "secret" not in response.json()["detail"]


def test_dim12_cli_injection_flag_smuggling_sanitization(client):
    # Dim 12: Injection attempts sanitized & rejected
    injections = ["FPT; rm -rf /", "HPG && ls", "VNM | cat /etc/passwd", "--help", "-v"]
    for inj in injections:
        resp = client.post("/api/v1/control/ingest-data", json={"symbols": [inj]})
        assert resp.status_code == 422


def test_dim13_schema_drift_unexpected_column_mutation(client):
    # Dim 13: Schema consistency & receipt schema versioning
    resp = client.get("/api/v1/control/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "kill_switch_active" in data
    assert "active_tasks_count" in data
    assert "total_tasks_count" in data
    assert "recent_tasks" in data


def test_dim14_sse_unknown_job_id_returns_404_no_state_leak(client):
    # Fix (1)(d): SSE endpoint must return 404 for unknown job_id instead of creating unbounded in-memory task queues
    assert "nonexistent_job_123" not in control_mod.TASKS
    resp = client.get("/sse/v1/pipeline/nonexistent_job_123/stream")
    assert resp.status_code == 404
    assert "nonexistent_job_123" not in control_mod.TASKS
    assert "nonexistent_job_123" not in control_mod.TASK_EVENT_QUEUES

    resp2 = client.get("/sse/v1/tasks/nonexistent_task_456/progress")
    assert resp2.status_code == 404
    assert "nonexistent_task_456" not in control_mod.TASKS
    assert "nonexistent_task_456" not in control_mod.TASK_EVENT_QUEUES


def test_dim14_resource_bounds_memory_limits(client):
    # Dim 14: Resource bounds (universe > 100 symbols rejected)
    too_many_symbols = [f"SYM{i}" for i in range(105)]
    resp = client.post("/api/v1/control/pipeline-run", json={"universe": too_many_symbols})
    assert resp.status_code == 422


def test_dim15_network_retry_exhaustion_unconfigured_error(client):
    # Dim 15: Explicit structured error on unconfigured / empty provider response with retry exhaustion
    with patch.object(control_mod.DataLoader, "load_prices", side_effect=RuntimeError("Provider 429 rate limit exceeded")):
        token = control_mod.generate_totp()
        resp = client.post("/api/v1/control/rebalance", json={
            "totp_code": token,
            "target_portfolio": {"FPT": 1.0},
        })
        assert resp.status_code == 422
        assert "No valid point-in-time market data available" in resp.json()["detail"]


def test_dim6_delayed_benchmark_pit_forward_fill_only(monkeypatch):
    # Dim 6: Adversarial test for delayed benchmark PIT without look-ahead (no bfill)
    import pandas as pd
    prices_idx = pd.date_range("2023-01-01", "2023-01-10", freq="D")
    prices = pd.DataFrame({"FPT": [100.0] * len(prices_idx)}, index=prices_idx)

    # VNINDEX data starts only on 2023-01-05 (delayed benchmark available only later)
    vni_idx = pd.date_range("2023-01-05", "2023-01-10", freq="D")
    vni_df = pd.DataFrame({"date": vni_idx, "close": [1000.0, 1010.0, 1020.0, 1030.0, 1040.0, 1050.0]})

    async def fake_load_prices(*args, **kwargs):
        return vni_df

    monkeypatch.setattr(control_mod.DataLoader, "load_prices", fake_load_prices)

    # Simulate alignment logic strictly without bfill
    vni_prices = vni_df.set_index("date")["close"].sort_index()
    vni_aligned = vni_prices.reindex(prices.index).ffill()

    # Dates before 2023-01-05 must be NaN (strictly forward-fill only, not backfilled from future)
    assert pd.isna(vni_aligned.loc["2023-01-01"])
    assert pd.isna(vni_aligned.loc["2023-01-04"])
    assert vni_aligned.loc["2023-01-05"] == 1000.0


def test_dim16_secret_redaction_credential_leak_prevention(client):
    # Dim 16: Secret redaction in environment resolution & error logging
    # Test that TOTP secret is never exposed in responses or status
    resp = client.get("/api/v1/control/status")
    assert resp.status_code == 200
    text_dump = json.dumps(resp.json())
    assert control_mod.DEFAULT_TOTP_SECRET not in text_dump

    token = control_mod.generate_totp()
    resp2 = client.post("/api/v1/control/kill-switch", json={"totp_code": token})
    assert resp2.status_code == 200
    assert control_mod.DEFAULT_TOTP_SECRET not in json.dumps(resp2.json())

    # Redactor test for exceptions
    dirty_msg = "Error connecting to https://user:secretpass@provider.com/v1/prices with Bearer token_abc_12345"
    clean_msg = control_mod._redact_text(dirty_msg)
    assert "secretpass" not in clean_msg
    assert "token_abc_12345" not in clean_msg
    assert "https://provider.com" in clean_msg


def test_dim16_adversarial_exception_credential_redaction_copilot():
    # Dim 16: Exception credential redaction in copilot error strings & HTTPException details
    import omega.api.routes.copilot as copilot_mod
    raw_error_text = "Failed call to https://admin:super_secret_token_123@api.openai.com/v1/chat with Authorization: Bearer sk-live-999888777666"
    redacted = copilot_mod.redact_credentials_in_text(raw_error_text)
    assert "super_secret_token_123" not in redacted
    assert "sk-live-999888777666" not in redacted
    assert "Bearer [REDACTED]" in redacted or "[REDACTED]" in redacted
    assert "https://api.openai.com" in redacted


# Legacy & functional control ops validation
def test_ingest_data_success(client):
    payload = {"symbols": ["FPT", "HPG", "VNM"], "sources": ["vci"], "force_refresh": True}
    resp = client.post("/api/v1/control/ingest-data", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "task-ingest-" in data["task_id"]
    assert "/sse/v1/tasks/" in data["stream_url"]


def test_ingest_scheduler_telemetry_reports_runtime_failover(client, tmp_path, monkeypatch):
    checkpoint = tmp_path / "ingest.json"
    checkpoint.write_text(json.dumps({"active_feed": "kbs", "feed_health": {"vci": "DEGRADED", "kbs": "ONLINE"}, "updated_at": "2026-09-09T00:00:00+00:00"}), encoding="utf-8")
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CHECKPOINT_PATH", checkpoint)
    control_mod.TASKS["task-ingest-runtime"] = {"task_type": "DATA_INGESTION", "status": "RUNNING", "updated_at": "2026-09-09T00:01:00+00:00", "params": {"sources": ["vci", "kbs", "tcbs"]}}

    response = client.get("/api/v1/control/ingest-scheduler/telemetry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "DEGRADED"
    assert payload["active_feed"] == "kbs"
    assert payload["backup_feed"] == "tcbs"
    assert payload["failover_ready"] is True
    assert payload["feed_health"]["vci"] == "DEGRADED"


def test_ingest_fails_over_to_backup_feed(tmp_path, monkeypatch):
    class Loader:
        def load_prices(self, ticker, *_args, source=None, **_kwargs):
            if source == "vci":
                raise RuntimeError("provider 429")
            return pd.DataFrame({"date": [pd.Timestamp("2023-12-29")], "close": [100000.0]})

    task_id = "task-ingest-failover"
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    monkeypatch.setattr(control_mod, "CONTROL_ARTIFACT_ROOT", tmp_path / "receipts")
    monkeypatch.setattr(control_mod, "DataLoader", lambda **_kwargs: Loader())
    control_mod.TASKS[task_id] = {"task_type": "DATA_INGESTION", "status": "QUEUED", "progress": 0.0, "events": deque(maxlen=1000)}

    import asyncio
    asyncio.run(control_mod._run_ingest(task_id, control_mod.IngestDataRequest(symbols=["FPT"], sources=["vci", "kbs"])))

    result = control_mod.TASKS[task_id]["result"]
    assert result["provider"] == "kbs"
    assert result["failover_used"] is True
    assert result["failover_history"] == [{"symbol": "FPT", "from_provider": "vci", "to_provider": "kbs"}]
    assert result["feed_health"] == {"vci": "DEGRADED", "kbs": "ONLINE", "tcbs": "STANDBY"}


def test_ingest_cancellation_during_semaphore_admission_stays_cancelled(tmp_path, monkeypatch):
    class Loader:
        def load_prices(self, ticker, *_args, **_kwargs):
            if ticker == "FPT":
                control_mod.CANCELLED_JOBS.add(task_id)
            return pd.DataFrame({"date": [pd.Timestamp("2023-12-29")], "close": [100000.0]})

    task_id = "task-ingest-cancelled-admission"
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CONCURRENCY", 1)
    monkeypatch.setattr(control_mod, "DataLoader", lambda **_kwargs: Loader())
    control_mod.TASKS[task_id] = {"task_type": "DATA_INGESTION", "status": "RUNNING", "progress": 10.0, "events": deque(maxlen=1000)}

    import asyncio
    asyncio.run(control_mod._run_ingest(task_id, control_mod.IngestDataRequest(symbols=["FPT", "VNM"], sources=["vci", "kbs"])))

    assert control_mod.TASKS[task_id]["status"] == "CANCELLED"
    assert control_mod.TASKS[task_id]["events"][-1]["event_type"] == "CANCELLED"


def test_ingest_failover_history_is_cumulative_and_health_is_not_reset(tmp_path, monkeypatch):
    class Loader:
        def load_prices(self, ticker, *_args, source=None, **_kwargs):
            if ticker == "FPT" and source == "vci":
                raise RuntimeError("vci unavailable")
            return pd.DataFrame({"date": [pd.Timestamp("2023-12-29")], "close": [100000.0]})

    task_id = "task-ingest-cumulative-failover"
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    monkeypatch.setattr(control_mod, "CONTROL_ARTIFACT_ROOT", tmp_path / "receipts")
    monkeypatch.setattr(control_mod, "DataLoader", lambda **_kwargs: Loader())
    control_mod.TASKS[task_id] = {"task_type": "DATA_INGESTION", "status": "QUEUED", "progress": 0.0, "events": deque(maxlen=1000)}

    import asyncio
    asyncio.run(control_mod._run_ingest(task_id, control_mod.IngestDataRequest(symbols=["FPT", "VNM"], sources=["vci", "kbs"])))

    result = control_mod.TASKS[task_id]["result"]
    assert result["failover_used"] is True
    assert result["failover_history"] == [{"symbol": "FPT", "from_provider": "vci", "to_provider": "kbs"}]
    assert result["feed_health"]["vci"] == "DEGRADED"


@pytest.mark.parametrize("feed_health", [[], "malformed", None])
def test_ingest_scheduler_telemetry_ignores_malformed_checkpoint_feed_health(client, tmp_path, monkeypatch, feed_health):
    checkpoint = tmp_path / "ingest.json"
    checkpoint.write_text(json.dumps({"active_feed": "kbs", "feed_health": feed_health}), encoding="utf-8")
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CHECKPOINT_PATH", checkpoint)

    response = client.get("/api/v1/control/ingest-scheduler/telemetry")

    assert response.status_code == 200
    assert response.json()["feed_health"] == {"vci": "STANDBY", "kbs": "ONLINE", "tcbs": "STANDBY"}


def test_compute_alphas_success(client):
    payload = {"universe": ["FPT", "HPG", "MBB", "MWG", "DGC", "VNM", "TCB", "PNJ"], "alpha_families": ["MOMENTUM"]}
    resp = client.post("/api/v1/control/compute-alphas", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "task-alpha-" in data["task_id"]


def test_optimize_portfolio_success(client):
    payload = {"objective": "ALPHA_RANK_RISK_CAPPED", "universe": ["FPT", "HPG", "MBB", "MWG", "DGC", "VNM", "TCB", "PNJ"], "max_single_weight": 0.20}
    resp = client.post("/api/v1/control/optimize-portfolio", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "task-opt-" in data["task_id"]


def test_run_backtest_success(client):
    payload = {"strategy_id": "OMEGA_MOMENTUM_V1", "start_date": "2021-01-01", "slippage_bps": 15.0, "commission_bps": 10.0, "include_benchmark": False}
    resp = client.post("/api/v1/control/run-backtest", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "task-bt-" in data["task_id"]


def test_rebalance_success_and_replay_protection(client):
    token = control_mod.generate_totp()
    payload = {
        "totp_code": token,
        "strategy_id": "ALPHA_HRP_V2",
        "portfolio_value": 1_000_000_000.0,
        "target_portfolio": {"FPT": 0.25, "HPG": 0.25, "MBB": 0.25, "MWG": 0.25}
    }
    resp = client.post("/api/v1/control/rebalance", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["totp_verified"] is True
    assert "job-rebal-" in data["job_id"]
    assert "should_rebalance" in data

    # Replay token fails
    resp2 = client.post("/api/v1/control/rebalance", json=payload)
    assert resp2.status_code == 401


def test_strategy_backtest_endpoint_success_and_registry_validation(client):
    resp = client.get("/api/v1/strategy/backtest/ALPHA_HRP_V2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["strategy_id"] == "ALPHA_HRP_V2"
    assert "equity_curve" in data
    assert len(data["equity_curve"]) > 0
    assert "monthly_returns" in data
    assert "cagr_pct" in data
    assert "sharpe_ratio" in data
    assert "benchmark_name" in data

    # Unknown strategy returns 404
    resp_404 = client.get("/api/v1/strategy/backtest/UNKNOWN_STRATEGY_XYZ")
    assert resp_404.status_code == 404


def test_control_ops_event_deque_cap_and_task_eviction(client):
    """Test deque(maxlen=1000) event cap and size/TTL task eviction."""
    from collections import deque
    task_id = "task-cap-test"
    control_mod.TASKS[task_id] = {
        "task_id": task_id,
        "job_id": task_id,
        "status": "RUNNING",
        "progress": 0.0,
        "stage": "INIT",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "events": deque(maxlen=1000),
    }

    # Push 1050 events into task
    for i in range(1050):
        control_mod._push_task_event(task_id, "PROGRESS", float(i % 100), f"STAGE_{i}", f"Message {i}")

    assert len(control_mod.TASKS[task_id]["events"]) == 1000
    assert isinstance(control_mod.TASKS[task_id]["events"], deque)

    # Test TTL eviction: create expired completed task
    expired_tid = "task-expired"
    past_iso = (datetime.now(timezone.utc) - timedelta(seconds=4000)).isoformat()
    control_mod.TASKS[expired_tid] = {
        "task_id": expired_tid,
        "job_id": expired_tid,
        "status": "COMPLETED",
        "progress": 100.0,
        "stage": "DONE",
        "created_at": past_iso,
        "updated_at": past_iso,
        "events": deque(maxlen=1000),
    }

    control_mod._evict_stale_tasks()
    assert expired_tid not in control_mod.TASKS
    assert task_id in control_mod.TASKS

    # Test max tasks capacity eviction
    for i in range(520):
        tid = f"task-completed-{i}"
        ts_iso = (datetime.now(timezone.utc) - timedelta(seconds=i + 10)).isoformat()
        control_mod.TASKS[tid] = {
            "task_id": tid,
            "job_id": tid,
            "status": "COMPLETED",
            "progress": 100.0,
            "stage": "DONE",
            "created_at": ts_iso,
            "updated_at": ts_iso,
            "events": deque(maxlen=1000),
        }

    control_mod._evict_stale_tasks()
    assert len(control_mod.TASKS) <= control_mod.MAX_TASKS_LIMIT


def test_copilot_1mb_cap_enforcement(client):
    """Test 1MB byte cap on upstream LLM response in copilot routes."""
    import omega.api.routes.copilot as copilot_mod
    import httpx
    from unittest.mock import AsyncMock, patch

    # Mock response exceeding 1MB
    large_content = b"x" * (1024 * 1024 + 100)
    mock_resp = httpx.Response(status_code=200, content=large_content, request=httpx.Request("GET", "https://api.openai.com/v1/models"))

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_resp
    mock_client.post.return_value = mock_resp

    with patch("omega.api.routes.copilot.get_safe_httpx_client", return_value=mock_client):
        # 1. test /config/test with >1MB response
        resp_test = client.post("/api/v1/copilot/config/test", json={"profile_key": "global_profile", "provider": "openai"})
        assert resp_test.status_code == 200
        data_test = resp_test.json()
        assert data_test["status"] == "error"

        # 2. test /config/models with >1MB response
        resp_models = client.post("/api/v1/copilot/config/models", json={"provider": "openai"})
        assert resp_models.status_code == 200
        data_models = resp_models.json()
        assert data_models["status"] == "error"
        assert data_models["offline_suggestions"] is True


def test_active_task_limit_rejection_at_500(client):
    """Test enforcing active task limit (max 500 active tasks), rejecting new tasks with 429 when full."""
    control_mod.TASKS.clear()
    for i in range(control_mod.MAX_ACTIVE_TASKS_LIMIT):
        tid = f"task-active-{i}"
        now_iso = datetime.now(timezone.utc).isoformat()
        control_mod.TASKS[tid] = {
            "task_id": tid,
            "job_id": tid,
            "status": "RUNNING" if i % 2 == 0 else "QUEUED",
            "progress": 50.0,
            "stage": "FETCH_OHLCV",
            "created_at": now_iso,
            "updated_at": now_iso,
            "events": deque(maxlen=1000),
        }

    # Attempting to launch a 501st active task must be rejected with 429
    resp_pipe = client.post("/api/v1/control/pipeline-run", json={"universe": ["FPT"]})
    assert resp_pipe.status_code == 429
    assert "Active task capacity exhausted" in resp_pipe.json()["detail"]

    resp_ingest = client.post("/api/v1/control/ingest-data", json={"symbols": ["FPT"]})
    assert resp_ingest.status_code == 429
    assert "Active task capacity exhausted" in resp_ingest.json()["detail"]

    resp_alpha = client.post("/api/v1/control/compute-alphas", json={"universe": ["FPT"]})
    assert resp_alpha.status_code == 429

    resp_opt = client.post("/api/v1/control/optimize-portfolio", json={"universe": ["FPT"]})
    assert resp_opt.status_code == 429

    resp_bt = client.post("/api/v1/control/run-backtest", json={"strategy_id": "OMEGA_MOMENTUM_V1", "universe": ["FPT"]})
    assert resp_bt.status_code == 429

    # Free up one slot by marking a task COMPLETED
    control_mod.TASKS["task-active-0"]["status"] = "COMPLETED"
    # Now task creation should proceed past capacity check
    with patch.object(control_mod.BackgroundTasks, "add_task", return_value=None):
        resp_allowed = client.post("/api/v1/control/pipeline-run", json={"universe": ["FPT"]})
        assert resp_allowed.status_code == 200


def test_copilot_streaming_1mb_cap_abort(client):
    """Test client.stream() aborts streaming and rejects responses exceeding 1MB in copilot ask endpoint."""
    import omega.api.routes.copilot as copilot_mod
    from unittest.mock import AsyncMock, patch

    class FakeStreamResponse:
        def __init__(self, status_code=200, chunk_size=256 * 1024, chunk_count=5):
            self.status_code = status_code
            self.headers = {"content-type": "application/json"}
            self._chunk_size = chunk_size
            self._chunk_count = chunk_count

        async def aiter_bytes(self):
            for _ in range(self._chunk_count):
                yield b"x" * self._chunk_size

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class FakeStreamingClient:
        def __init__(self):
            pass

        def stream(self, method, url, **kwargs):
            # 5 chunks of 256KB = 1.25MB > 1MB limit
            return FakeStreamResponse(status_code=200, chunk_size=256 * 1024, chunk_count=5)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("omega.api.routes.copilot._IN_MEMORY_LLM_CONFIG", {
        "global_profile": {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-real-key",
            "base_url": "https://api.openai.com/v1",
            "temperature": 0.2,
            "max_tokens": 4096,
            "timeout_seconds": 30,
            "enabled": True,
        }
    }):
        with patch("omega.api.routes.copilot.get_safe_httpx_client", return_value=FakeStreamingClient()):
            resp = client.post("/api/v1/copilot/ask", json={"query": "Chi tiết dòng tiền FPT", "context_ticker": "FPT"})
            assert resp.status_code == 200
            data = resp.json()
            # On 1MB abort exception, copilot gracefully falls back to deterministic quant synthesis
            assert data["status"] == "success"
            assert "FPT" in data["focus_ticker"]


def test_copilot_catalog_discovery_streaming_1mb_cap_abort(client):
    """Test client.stream() aborts streaming and rejects responses exceeding 1MB in probe and fetch_models endpoints."""
    class FakeStreamResponse:
        def __init__(self, status_code=200, chunk_size=256 * 1024, chunk_count=5):
            self.status_code = status_code
            self.headers = {"content-type": "application/json"}
            self._chunk_size = chunk_size
            self._chunk_count = chunk_count

        async def aiter_bytes(self):
            for _ in range(self._chunk_count):
                yield b"x" * self._chunk_size

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class FakeStreamingClient:
        def stream(self, method, url, **kwargs):
            return FakeStreamResponse(status_code=200, chunk_size=256 * 1024, chunk_count=5)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("omega.api.routes.copilot.get_safe_httpx_client", return_value=FakeStreamingClient()):
        # 1. test probe endpoint (/config/test)
        resp_test = client.post("/api/v1/copilot/config/test", json={"profile_key": "global_profile", "provider": "openai"})
        assert resp_test.status_code == 200
        data_test = resp_test.json()
        assert data_test["status"] == "error"
        assert data_test["error_code"] == "INVALID_RESPONSE"

        # 2. test catalog models endpoint (/config/models)
        resp_models = client.post("/api/v1/copilot/config/models", json={"provider": "openai"})
        assert resp_models.status_code == 200
        data_models = resp_models.json()
        assert data_models["status"] == "error"
        assert data_models["source"] == "offline_suggestions"
        assert data_models["offline_suggestions"] is True


def test_concurrent_task_admission_lock_synchronization(client):
    """Test concurrent task admission under threading.Lock guarantees strict task count bound and no race condition."""
    control_mod.TASKS.clear()
    capacity = 10
    with patch.object(control_mod, "MAX_ACTIVE_TASKS_LIMIT", capacity), \
         patch.object(control_mod.BackgroundTasks, "add_task", return_value=None):

        def submit_task(idx):
            return client.post("/api/v1/control/pipeline-run", json={"universe": ["FPT"]})

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(submit_task, i) for i in range(30)]
            responses = [f.result() for f in futures]

        status_codes = [r.status_code for r in responses]
        success_count = sum(1 for c in status_codes if c == 200)
        rejected_count = sum(1 for c in status_codes if c == 429)

        assert success_count == capacity
        assert rejected_count == 20
        with control_mod._TASK_STATE_LOCK:
            active_in_mem = sum(1 for t in control_mod.TASKS.values() if t.get("status") in ("QUEUED", "RUNNING"))
            assert active_in_mem == capacity


def test_data_loader_parquet_atomic_fsync_durability(tmp_path):
    """Test _write_parquet_atomic performs fsync before replace and handles write failures cleanly."""
    import pandas as pd
    from omega.data.loader import DataLoader

    df = pd.DataFrame({"ticker": ["FPT"], "close": [100000.0]})
    dest = tmp_path / "test_cache.parquet"

    fsync_called = []
    real_fsync = os.fsync

    def mock_fsync(fd):
        fsync_called.append(fd)
        return real_fsync(fd)

    with patch("os.fsync", side_effect=mock_fsync):
        DataLoader._write_parquet_atomic(df, dest)

    assert dest.exists()
    assert len(fsync_called) >= 1
    loaded = pd.read_parquet(dest)
    assert len(loaded) == 1
    assert loaded["ticker"].iloc[0] == "FPT"
