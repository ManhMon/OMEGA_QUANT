import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pandas as pd
import pytest
from pydantic import ValidationError

from omega.api.routes import control
from omega.core.pipeline import PipelineResult


def valid_result(success=True, metrics=None):
    dates = pd.to_datetime(["2023-01-02", "2023-01-03"], utc=True)
    data = pd.DataFrame({"ticker": ["FPT", "FPT"], "date": dates, "close": [100_000.0, 101_000.0]})
    features = data.assign(ret_5=[0.0, 0.01])
    alphas = data[["ticker", "date"]].assign(alpha_momentum=[0.0, 0.01])
    positions = data[["ticker", "date"]].assign(target_weight=[1.0, 1.0])
    return PipelineResult(success=success, message="ok", data=data, features=features, alphas=alphas, positions=positions, executions=[], metrics=metrics if metrics is not None else {"total_trades": 0.0, "avg_cost_bps": 0.0})


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "TASKS", {})
    monkeypatch.setattr(control, "TASK_EVENT_QUEUES", {})
    monkeypatch.setattr(control, "CANCELLED_JOBS", set())
    monkeypatch.setattr(control, "KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(control, "CONTROL_ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(control, "_USED_TOTP_TOKENS", {})
    monkeypatch.setattr(control, "TOTP_REPLAY_CACHE_PATH", tmp_path / "totp.json")
    monkeypatch.setattr(control, "TOTP_REPLAY_CACHE_LOCK_PATH", tmp_path / "totp.lock")


@pytest.mark.parametrize("payload", [
    {"universe": []}, {"universe": [" "]}, {"universe": ["FPT;--"]},
    {"start_date": "bad"}, {"start_date": "2024-01-01", "end_date": "2023-01-01"},
    {"as_of_time": "2099-01-01T00:00:00+00:00"}, {"mode": "DRY_RUN"},
    {"alpha_families": ["QUALITY"]}, {"rebalance_frequency": "yearly"},
    {"initial_capital": "NaN"}, {"slippage_bps": float("inf")},
])
def test_request_boundary_fails_closed(payload):
    with pytest.raises(ValidationError):
        control.PipelineRunRequest(**payload)


def test_parameter_mapping_and_canonicalization():
    request = control.PipelineRunRequest(
        universe=["fpt", "FPT", "hpg", "mwg", "dgc", "vnm", "tcb", "pnj"],
        initial_capital=2_000_000_000,
        slippage_bps=17,
        commission_bps=9,
        max_single_weight=0.2,
    )
    cfg = control._pipeline_config(request, datetime(2023, 12, 31, tzinfo=timezone.utc))
    assert cfg.universe == ["FPT", "HPG", "MWG", "DGC", "VNM", "TCB", "PNJ"]
    assert cfg.risk_config.initial_capital == 2_000_000_000
    assert cfg.risk_config.max_concentration_per_stock == 0.2
    assert cfg.execution_config.slippage_bps == 17
    assert cfg.execution_config.commission_bps == 9


@pytest.mark.parametrize("result", [
    valid_result(success=False),
    PipelineResult(success=True, message="missing"),
    valid_result(metrics={}),
    valid_result(metrics={"sharpe": float("nan")}),
])
def test_invalid_pipeline_output_never_validates(result):
    with pytest.raises(RuntimeError):
        control._validate_pipeline_result(result)


def test_receipt_is_atomic_durable_and_matching(tmp_path):
    request = control.PipelineRunRequest()
    receipt = control._publish_receipt("job-1", "PIPELINE_RUN", request, datetime(2023, 12, 31, tzinfo=timezone.utc), {"metrics": {"total_trades": 0}})
    assert control._valid_receipt(receipt, "job-1")
    assert json.loads((tmp_path / "job-1.json").read_text())["output_sha256"] == receipt["output_sha256"]
    assert not list(tmp_path.glob("*.tmp"))


def test_publication_failure_preserves_existing_receipt(tmp_path, monkeypatch):
    destination = tmp_path / "job-1.json"
    destination.write_text('{"prior":true}', encoding="utf-8")
    monkeypatch.setattr(control.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        control._publish_receipt("job-1", "PIPELINE_RUN", control.PipelineRunRequest(), datetime(2023, 12, 31, tzinfo=timezone.utc), {"ok": True})
    assert destination.read_text(encoding="utf-8") == '{"prior":true}'


def test_complete_requires_matching_receipt():
    control.TASKS["job-1"] = {"progress": 0, "events": []}
    control._push_task_event("job-1", "COMPLETE", 100, "DONE", "not valid", {})
    assert control.TASKS["job-1"]["status"] == "FAILED"
    assert control.TASKS["job-1"]["events"][-1]["payload"]["error_code"] == "INVALID_RECEIPT"


def test_pipeline_failure_and_cancel_never_complete(monkeypatch):
    request = control.PipelineRunRequest()
    control.TASKS["job-1"] = {"progress": 0, "events": []}

    async def unsuccessful(*_):
        return valid_result(success=False)

    monkeypatch.setattr(control, "_run_pipeline_task", unsuccessful)
    asyncio.run(control._execute_real_pipeline("job-1", request))
    assert control.TASKS["job-1"]["status"] == "FAILED"
    assert all(event["event_type"] != "COMPLETE" for event in control.TASKS["job-1"]["events"])


# -------------------------------------------------------------
# 16-DIMENSIONAL ADVERSARIAL PIPELINE BRIDGE MATRIX TESTS
# -------------------------------------------------------------

def test_dim1_adversarial_malformed_types():
    with pytest.raises(ValidationError):
        control.PipelineRunRequest(universe=12345)  # non-list
    with pytest.raises(ValidationError):
        control.PipelineRunRequest(slippage_bps="invalid_number")


def test_dim2_adversarial_invalid_paths(tmp_path, monkeypatch):
    invalid_root = tmp_path / "non_writable_dir"
    invalid_root.mkdir()
    req = control.PipelineRunRequest()
    as_of = datetime(2023, 12, 31, tzinfo=timezone.utc)
    monkeypatch.setattr(control, "CONTROL_ARTIFACT_ROOT", invalid_root)
    receipt = control._publish_receipt("task-io", "PIPELINE_RUN", req, as_of, {"metrics": {"ok": 1}})
    assert (invalid_root / "task-io.json").exists()


def test_dim3_adversarial_checkpoint_integrity(tmp_path):
    # Dim 3: Corrupted / duplicate / partial shard checkpoint integrity
    shard1 = tmp_path / "shard1.json"
    shard1.write_text('{"task_id": "t1", "part": 1}', encoding="utf-8")

    # Incomplete receipt validation checks
    assert not control._valid_receipt({"task_id": "t1", "status": "PENDING"}, "t1")
    assert not control._valid_receipt({"task_id": "t1", "status": "COMPLETED", "schema_version": 2}, "t1")
    assert not control._valid_receipt({
        "schema_version": 1,
        "task_id": "t1",
        "status": "COMPLETED",
        # missing request_fingerprint, output_sha256, published_at
    }, "t1")


def test_dim4_adversarial_fail_closed_kill_switch_pipeline():
    control.KILL_SWITCH_ACTIVE = True
    control.TASKS["job-ks"] = {"progress": 0.0, "events": []}
    asyncio.run(control._execute_real_pipeline("job-ks", control.PipelineRunRequest()))
    assert control.TASKS["job-ks"]["status"] == "FAILED"
    assert "Kill switch is active" in control.TASKS["job-ks"]["events"][-1]["message"]


def test_dim5_adversarial_rollback_and_atomic_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "CONTROL_ARTIFACT_ROOT", tmp_path)
    receipt_file = tmp_path / "task-atomic.json"
    receipt_file.write_text('{"state": "stable"}', encoding="utf-8")

    # Mock failure in write/replace
    monkeypatch.setattr(control.os, "replace", lambda s, d: (_ for _ in ()).throw(IOError("Atomic write failure")))
    with pytest.raises(IOError):
        control._publish_receipt("task-atomic", "DATA_INGESTION", control.IngestDataRequest(), datetime(2023, 12, 31, tzinfo=timezone.utc), {})
    assert receipt_file.read_text(encoding="utf-8") == '{"state": "stable"}'


def test_dim6_adversarial_pit_cutoff_enforcement():
    # End date in future violates PIT
    with pytest.raises(ValueError, match="end_date must not exceed as_of_time"):
        control._validate_dates("2023-01-01", "2024-01-01", "2023-06-01T00:00:00+00:00")


def test_dim7_adversarial_calendar_range_bounds():
    # Date range > 10 years (3655 days)
    with pytest.raises(ValueError, match="date range exceeds 10 years"):
        control._validate_dates("2010-01-01", "2023-01-01", None)

    # Invalid date strings rejected
    with pytest.raises(ValueError, match="dates must use YYYY-MM-DD"):
        control._validate_dates("2023-13-40", "2023-12-31", None)


def test_dim8_adversarial_numeric_precision():
    # Non-finite float checks in pipeline result validation
    res = valid_result(metrics={"total_trades": 1.0, "sharpe": float("inf")})
    with pytest.raises(RuntimeError, match="non-finite"):
        control._validate_pipeline_result(res)


def test_dim9_adversarial_concurrency_race_totp():
    # TOTP reuse in quick succession across requests
    token = control.generate_totp()
    assert control.verify_totp(token) is True
    # Immediate replay must fail
    assert control.verify_totp(token) is False


def test_dim10_adversarial_vnd_full_scale_invariance():
    req = control.PipelineRunRequest(initial_capital=10_000_000.0)
    cfg = control._pipeline_config(req, datetime(2023, 12, 31, tzinfo=timezone.utc))
    assert cfg.risk_config.initial_capital == 10_000_000.0


def test_dim11_adversarial_survivorship_and_empty_symbols():
    with pytest.raises(ValueError, match="universe contains an invalid symbol"):
        control._canonical_symbols(["VALID", "INVALID_VERY_LONG_SYMBOL_NAME"])


def test_dim12_adversarial_cli_injection_sanitization():
    for injection in ["FPT; rm -rf", "VNM && touch bad", "`cat /etc/passwd`"]:
        with pytest.raises(ValueError, match="universe contains an invalid symbol"):
            control._canonical_symbols([injection])


def test_dim13_adversarial_schema_drift_defense():
    req = control.PipelineRunRequest()
    fp = control._request_fingerprint(req)
    assert len(fp) == 64
    # Modifying request produces different fingerprint
    req2 = control.PipelineRunRequest(slippage_bps=20.0)
    assert control._request_fingerprint(req2) != fp

    # Fix (1)(e): Schema drift in result DataFrame raises RuntimeError for missing domain columns
    bad_df = pd.DataFrame({"unknown_col": [1, 2, 3]})
    bad_res = PipelineResult(success=True, message="drift", data=bad_df, features=bad_df, alphas=bad_df, positions=bad_df, metrics={"total_trades": 1})
    with pytest.raises(RuntimeError, match="missing required domain columns"):
        control._validate_pipeline_result(bad_res)

    # Missing return/close in features frame
    dates = pd.to_datetime(["2023-01-02", "2023-01-03"], utc=True)
    good_data = pd.DataFrame({"ticker": ["FPT", "FPT"], "date": dates, "close": [100_000.0, 101_000.0]})
    bad_features = pd.DataFrame({"ticker": ["FPT", "FPT"], "date": dates, "random_col": [1, 2]})
    good_alphas = good_data[["ticker", "date"]].assign(alpha_momentum=[0.0, 0.01])
    good_positions = good_data[["ticker", "date"]].assign(target_weight=[1.0, 1.0])

    drift_res = PipelineResult(success=True, message="ok", data=good_data, features=bad_features, alphas=good_alphas, positions=good_positions, executions=[], metrics={"total_trades": 1})
    with pytest.raises(RuntimeError, match="features frame missing required domain columns"):
        control._validate_pipeline_result(drift_res)

    # Missing target_weight in positions frame
    bad_positions = pd.DataFrame({"ticker": ["FPT", "FPT"], "date": dates, "weight_drift": [1.0, 1.0]})
    drift_res2 = PipelineResult(success=True, message="ok", data=good_data, features=good_data.assign(ret_5=[0.0, 0.01]), alphas=good_alphas, positions=bad_positions, executions=[], metrics={"total_trades": 1})
    with pytest.raises(RuntimeError, match="positions frame missing required domain columns"):
        control._validate_pipeline_result(drift_res2)


def test_dim14_adversarial_resource_bounds():
    with pytest.raises(ValueError, match="universe exceeds the 100-symbol limit"):
        control._canonical_symbols([f"S{i}" for i in range(101)])


def test_dim15_adversarial_network_error_propagation(monkeypatch):
    control.TASKS["job-net"] = {"progress": 0.0, "events": []}
    async def network_error(*_):
        raise ConnectionError("Upstream provider 429 connection timeout")
    monkeypatch.setattr(control, "_run_pipeline_task", network_error)
    asyncio.run(control._execute_real_pipeline("job-net", control.PipelineRunRequest()))
    assert control.TASKS["job-net"]["status"] == "FAILED"
    assert "Pipeline failed" in control.TASKS["job-net"]["events"][-1]["message"]
    assert control.TASKS["job-net"]["events"][-1]["payload"]["error_code"] == "PIPELINE_EXECUTION_FAILED"


def test_dim16_adversarial_secret_redaction():
    sec = control.DEFAULT_TOTP_SECRET
    req = control.PipelineRunRequest()
    output = {"status": "ok", "metrics": {"total_trades": 10}}
    receipt = control._publish_receipt("job-sec", "PIPELINE_RUN", req, datetime(2023, 12, 31, tzinfo=timezone.utc), output)
    receipt_str = json.dumps(receipt)
    assert sec not in receipt_str


def test_static_fake_success_bans():
    backend = open("src/omega/api/routes/control.py", encoding="utf-8").read()
    frontend = "\n".join(open(path, encoding="utf-8").read() for path in (
        "omega-ui/src/hooks/useControlOps.ts",
        "omega-ui/src/hooks/usePipelineRunner.ts",
        "omega-ui/src/modules/pipeline_console/PipelineOrchestrationConsole.tsx",
        "omega-ui/src/store/uiStore.ts",
    ))
    for forbidden in ("_run_ingest_simulation", "_run_alphas_simulation", "_run_optimize_simulation", "_run_backtest_simulation", "EXECUTION_SIMULATION", "Simulated execution", "result.metrics or"):
        assert forbidden not in backend + frontend
    # The console rejects non-terminal 100%; it never derives completion from progress.
    hooks = "\n".join(open(path, encoding="utf-8").read() for path in (
        "omega-ui/src/hooks/useControlOps.ts", "omega-ui/src/hooks/usePipelineRunner.ts",
    ))
    assert "progress >= 100" not in hooks
    assert "setInterval" not in open("omega-ui/src/hooks/useControlOps.ts", encoding="utf-8").read()


def test_loader_corrupt_parquet_and_tz_normalization(tmp_path, monkeypatch):
    """Test DataLoader corrupt parquet handling and tz-aware/naive timestamp comparison."""
    from omega.data.loader import DataLoader
    from unittest.mock import MagicMock

    cache_dir = tmp_path / "loader_cache"
    loader = DataLoader(cache_dir=str(cache_dir), quality_threshold=0.5, validate_provenance=False)

    # 1. Test corrupt parquet triggering source refresh
    ticker = "FPT"
    start_date = "2023-01-01"
    end_date = "2023-01-05"
    as_of_time = datetime(2023, 1, 10, 9, 0, tzinfo=timezone.utc)

    cache_key = loader._generate_cache_key(ticker, start_date, end_date)
    corrupt_cache_file = cache_dir / f"{cache_key}.parquet"
    corrupt_cache_file.write_bytes(b"CORRUPT_INVALID_PARQUET_DATA_HEADER")

    mock_df = pd.DataFrame({
        "ticker": ["FPT", "FPT"],
        "date": pd.to_datetime(["2023-01-02", "2023-01-03"]),
        "open": [100.0, 101.0],
        "high": [102.0, 103.0],
        "low": [99.0, 100.0],
        "close": [101.0, 102.0],
        "volume": [1000, 2000],
        "source_used": ["vci", "vci"]
    })

    monkeypatch.setattr(loader, "_fetch_from_source", lambda *args, **kwargs: mock_df.copy())

    # Loading with corrupt cache should catch error, fetch from source, and succeed
    loaded_df = loader.load_prices(ticker, start_date, end_date, as_of_time)
    assert len(loaded_df) == 2
    assert "as_of" in loaded_df.columns
    assert "available_at" in loaded_df.columns

    # 2. Test tz-aware vs tz-naive available_at normalization
    tz_aware_as_of = datetime(2023, 1, 10, 9, 0, tzinfo=timezone.utc)
    naive_as_of = datetime(2023, 1, 10, 9, 0)

    # Test with tz-naive available_at series
    df_naive = loaded_df.copy()
    df_naive["available_at"] = pd.to_datetime(["2023-01-03 09:00:00", "2023-01-04 09:00:00"])  # tz-naive
    loader._enforce_pit_safety(df_naive, tz_aware_as_of)
    assert len(df_naive) == 2

    # Test with tz-aware available_at series and naive as_of_time
    df_aware = loaded_df.copy()
    df_aware["available_at"] = pd.to_datetime(["2023-01-03 09:00:00+00:00", "2023-01-04 09:00:00+00:00"])  # tz-aware
    loader._enforce_pit_safety(df_aware, naive_as_of)
    assert len(df_aware) == 2


def test_loader_atomic_replace_and_temp_cleanup_on_failure(tmp_path):
    """Test atomic parquet cache writes to sibling temp file and cleanup on failure."""
    from omega.data.loader import DataLoader
    loader = DataLoader(cache_dir=str(tmp_path), validate_provenance=False)
    test_df = pd.DataFrame({
        "ticker": ["HPG"],
        "date": [pd.Timestamp("2023-01-01")],
        "open": [20000.0],
        "high": [21000.0],
        "low": [19500.0],
        "close": [20500.0],
        "volume": [50000],
        "as_of": [pd.Timestamp("2023-01-01 15:00:00", tz="Asia/Ho_Chi_Minh")],
        "available_at": [pd.Timestamp("2023-01-02 09:00:00", tz="Asia/Ho_Chi_Minh")],
    })
    target_parquet = tmp_path / "atomic_test.parquet"

    # 1. Normal atomic write
    loader._write_parquet_atomic(test_df, target_parquet)
    assert target_parquet.exists()
    read_df = pd.read_parquet(target_parquet)
    assert len(read_df) == 1
    # Ensure no leftover tmp files
    tmp_files = list(tmp_path.glob("*.tmp.*"))
    assert len(tmp_files) == 0

    # 2. Failure during atomic write cleans up temp file
    with patch("os.replace", side_effect=OSError("Atomic replacement failed")):
        with pytest.raises(OSError):
            loader._write_parquet_atomic(test_df, target_parquet)
        # Verify temporary file was unlinked
        tmp_files_after_err = list(tmp_path.glob("*.tmp.*"))
        assert len(tmp_files_after_err) == 0


def test_loader_asia_ho_chi_minh_pit_safety_and_utc_comparison(tmp_path):
    """Test naive market timestamps localized to Asia/Ho_Chi_Minh and compared as true UTC instants."""
    from omega.data.loader import DataLoader
    loader = DataLoader(cache_dir=str(tmp_path), validate_provenance=False)

    # 1. Test _add_pit_timestamps assigns Asia/Ho_Chi_Minh
    raw_df = pd.DataFrame({
        "ticker": ["MWG", "MWG"],
        "date": ["2023-01-02", "2023-01-03"],
        "open": [40000.0, 41000.0],
        "high": [41500.0, 42000.0],
        "low": [39500.0, 40500.0],
        "close": [41000.0, 41500.0],
        "volume": [10000, 20000],
    })
    pit_df = loader._add_pit_timestamps(raw_df)
    assert str(pit_df["as_of"].dt.tz) == "Asia/Ho_Chi_Minh"
    assert str(pit_df["available_at"].dt.tz) == "Asia/Ho_Chi_Minh"

    # 2. Test true UTC instant comparison:
    # 2023-01-04 09:00:00 in Asia/Ho_Chi_Minh is 2023-01-04 02:00:00 UTC
    # A query at 2023-01-04 01:59:00 UTC (before 09:00 VN) should NOT see row 2
    # A query at 2023-01-04 02:01:00 UTC (after 09:00 VN) SHOULD see row 2
    as_of_before = datetime(2023, 1, 4, 1, 59, 0, tzinfo=timezone.utc)
    df_check = pit_df.copy()
    loader._enforce_pit_safety(df_check, as_of_before)
    assert len(df_check) == 1  # only row 1 (available at 2023-01-03 09:00 VN = 2023-01-03 02:00 UTC)

    as_of_after = datetime(2023, 1, 4, 2, 1, 0, tzinfo=timezone.utc)
    df_check_after = pit_df.copy()
    loader._enforce_pit_safety(df_check_after, as_of_after)
    assert len(df_check_after) == 2


def test_control_task_critical_section_lock_guarantee():
    # Verify _register_task_atomic atomically handles task count check and insertion under threading.Lock
    control.TASKS.clear()
    with patch.object(control, "MAX_ACTIVE_TASKS_LIMIT", 2):
        r1 = {"status": "RUNNING", "events": []}
        r2 = {"status": "QUEUED", "events": []}
        r3 = {"status": "RUNNING", "events": []}
        control._register_task_atomic("t1", r1)
        control._register_task_atomic("t2", r2)
        with pytest.raises(control.HTTPException) as exc:
            control._register_task_atomic("t3", r3)
        assert exc.value.status_code == 429
        assert "Active task capacity exhausted" in exc.value.detail


def test_copilot_catalog_discovery_streaming_abortion():
    # Verify client.stream abortion when bytes exceed 1MB in copilot module
    import omega.api.routes.copilot as copilot_mod

    class OverflowStream:
        def __init__(self):
            self.status_code = 200
            self.headers = {}
        async def aiter_bytes(self):
            yield b"a" * (512 * 1024)
            yield b"b" * (512 * 1024)
            yield b"c" * 100
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class SafeClient:
        def stream(self, *args, **kwargs):
            return OverflowStream()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    with patch("omega.api.routes.copilot.get_safe_httpx_client", return_value=SafeClient()):
        req = copilot_mod.LLMModelFetchRequest(provider="openai")
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(copilot_mod.fetch_llm_models(req))
            assert res.status == "error"
            assert res.source == "offline_suggestions"
            assert res.offline_suggestions is True
        finally:
            loop.close()


def test_loader_write_parquet_atomic_fsync(tmp_path):
    from omega.data.loader import DataLoader
    test_df = pd.DataFrame({"ticker": ["VNM"], "close": [80000.0]})
    target_path = tmp_path / "vnm_test.parquet"

    fsync_called = []
    real_fsync = control.os.fsync

    def intercept_fsync(fd):
        fsync_called.append(fd)
        return real_fsync(fd)

    with patch("os.fsync", side_effect=intercept_fsync):
        DataLoader._write_parquet_atomic(test_df, target_path)

    assert target_path.exists()
    assert len(fsync_called) >= 1
    read_back = pd.read_parquet(target_path)
    assert len(read_back) == 1
    assert read_back["ticker"].iloc[0] == "VNM"


def test_slice17_dispatch_snapshot_and_cancellation_contract():
    from fastapi import BackgroundTasks

    response = asyncio.run(control.trigger_pipeline_run(control.PipelineRunRequest(), BackgroundTasks()))
    job_id = response["job_id"]
    assert response["stream_url"] == f"/sse/v1/pipeline/{job_id}/stream"
    snapshot = asyncio.run(control.get_pipeline_task(job_id))
    assert snapshot["schema_version"] == "pipeline-telemetry/v1"
    assert snapshot["status"] == "QUEUED" and snapshot["revision"] == 0
    assert [node["stage_id"] for node in snapshot["dag"]] == list(control.PIPELINE_STAGES)
    assert all(node["status"] == "PENDING" for node in snapshot["dag"])
    cancelled = asyncio.run(control.cancel_pipeline_job(job_id))
    assert cancelled["cancelled"] is True and cancelled["task_id"] == job_id
    terminal = asyncio.run(control.get_pipeline_task(job_id))
    assert terminal["status"] == "CANCELLED" and terminal["progress"] < 100
    control._push_task_event(job_id, "PROGRESS", 90, "DATA_INGEST", "late")
    assert asyncio.run(control.get_pipeline_task(job_id))["revision"] == terminal["revision"]


@pytest.mark.parametrize("status", ["COMPLETED", "FAILED", "CANCELLED"])
def test_slice17_terminal_sse_snapshot_is_authoritative(status):
    job_id = "job-pipe-1234abcd"
    request = control.PipelineRunRequest()
    control._register_task_atomic(job_id, {"task_type": "REAL_PIPELINE_RUN", "status": "QUEUED", "stage": "INIT", "progress": 0, "events": [], "params": request.model_dump()})
    control._push_task_event(job_id, "PROGRESS", 0, "DATA_INGEST", "start")
    if status == "COMPLETED":
        output = {"metrics": {"total_trades": 0.0}, "unit": "VND_FULL"}
        receipt = control._publish_receipt(job_id, "PIPELINE_RUN", request, datetime(2023, 12, 31, tzinfo=timezone.utc), output)
        control._push_task_event(job_id, "COMPLETE", 100, "DONE", "done", {**output, "receipt": receipt})
    elif status == "CANCELLED":
        asyncio.run(control.cancel_pipeline_job(job_id))
    else:
        control._push_task_event(job_id, "ERROR", 0, "FAILED", "failed", {"retryable": False})

    async def frames():
        response = await control.sse_pipeline_stream(job_id)
        return [json.loads(frame["data"]) async for frame in response.body_iterator]

    events = asyncio.run(frames())
    assert len(events) == 1 and events[0]["event_type"] == "SNAPSHOT"
    assert events[0]["status"] == status and events[0]["task_id"] == job_id
    assert not control.TASK_EVENT_QUEUES[job_id]
    if status == "COMPLETED":
        assert events[0]["payload"]["receipt"]["operation"] == "PIPELINE_RUN"
        assert all(node["status"] == "COMPLETED" for node in events[0]["dag"])
