"""Pipeline Console telemetry, DAG, SSE, and absorbing execution lifecycle contracts."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from omega.api.routes import control
from omega.api.server import app


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "TASKS", {})
    monkeypatch.setattr(control, "TASK_EVENT_QUEUES", {})
    monkeypatch.setattr(control, "CANCELLED_JOBS", set())
    monkeypatch.setattr(control, "KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(control, "CONTROL_ARTIFACT_ROOT", tmp_path)


@pytest.mark.parametrize("values,expected", [
    ({}, None), ({"mode": "incremental"}, None), ({"mode": None}, None),
    ({"mode": "full_history"}, "2015-01-01"),
    ({"mode": "full_history", "start_date": None}, "2015-01-01"),
    ({"mode": "incremental", "start_date": "2020-01-01"}, "2020-01-01"),
    ({"mode": "custom_range", "start_date": "2020-01-01"}, "2020-01-01"),
])
def test_ingestion_compatibility_dates(values, expected):
    original = dict(values)
    request = control.IngestDataRequest.model_validate(values)
    assert request.start_date == expected
    assert request.dry_run is False and request.no_refetch is False
    assert values == original


@pytest.mark.parametrize("values", [
    {"mode": "custom_range"}, {"mode": "custom_range", "start_date": None},
    {"mode": "custom_range", "start_date": ""}, {"mode": "invalid"},
    {"end_date": "invalid"}, {"as_of_time": "2099-01-01T00:00:00Z"},
])
def test_ingestion_compatibility_validation(values):
    with pytest.raises(ValidationError):
        control.IngestDataRequest.model_validate(values)


def register(task_id="job-test", pipeline=True):
    request = control.PipelineRunRequest()
    control._register_task_atomic(task_id, {
        "task_id": task_id, "job_id": task_id, "status": "QUEUED", "progress": 0.0,
        "stage": "INIT", "task_type": "REAL_PIPELINE_RUN" if pipeline else "DATA_INGESTION",
        "params": request.model_dump(), "events": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return request


def completion(task_id="job-test"):
    output = {"metrics": {"total_trades": 0}}
    receipt = control._publish_receipt(task_id, "PIPELINE_RUN", control.PipelineRunRequest(),
                                       datetime(2023, 12, 31, tzinfo=timezone.utc), output)
    return {**output, "receipt": receipt}


def test_pipeline_contracts_baseline():
    register()
    with TestClient(app) as client:
        response = client.get("/api/v1/control/tasks/job-test")
        assert response.status_code == 200
        telemetry = control.PipelineTelemetry.model_validate(response.json())
        assert telemetry.schema_version == "pipeline-telemetry/v1"
        assert telemetry.status == "QUEUED"
        assert telemetry.revision == 0
        dag = client.get("/api/v1/control/pipeline/dag").json()
        assert [stage["stage_id"] for stage in dag] == list(control.PIPELINE_STAGES)
        assert [stage["depends_on"] for stage in dag] == [[], *[[s] for s in control.PIPELINE_STAGES[:-1]]]
        assert all(stage["status"] == "PENDING" for stage in dag)
        assert client.get("/api/v1/control/tasks/missing").status_code == 404
        assert set(control.TASKS) == {"job-test"}


@pytest.mark.parametrize("field,value", [
    ("initial_capital", None), ("initial_capital", "invalid"), ("initial_capital", []),
    ("initial_capital", 0), ("initial_capital", -1), ("initial_capital", 1e12 + 1),
    ("initial_capital", float("nan")), ("initial_capital", float("inf")),
    ("initial_capital", float("-inf")), ("slippage_bps", float("nan")),
    ("slippage_bps", float("inf")), ("commission_bps", -1),
    ("max_single_weight", 0), ("universe", []), ("universe", ["FPT;--"]),
    ("universe", [None]), ("alpha_families", []), ("mode", "--shell"),
    ("as_of_time", "2023-12-31T08:30:00"), ("as_of_time", "2099-01-01T00:00:00Z"),
])
def test_request_boundary(field, value):
    with pytest.raises(ValidationError):
        control.PipelineRunRequest(**{field: value})
    assert not control.TASKS


def test_pit_inclusive_ict_session_close_and_vnd_units():
    request = control.PipelineRunRequest(as_of_time="2023-12-31T15:30:00+07:00", initial_capital=1e12)
    cutoff = control._validate_dates(request.start_date, request.end_date, request.as_of_time)
    assert cutoff == datetime(2023, 12, 31, 8, 30, tzinfo=timezone.utc)
    assert control._pipeline_config(request, cutoff).risk_config.initial_capital == 1e12
    with pytest.raises(ValidationError):
        control.PipelineRunRequest(as_of_time="2023-12-31T15:29:59+07:00")


def test_ordered_dag_and_receipt_gated_completion():
    register()
    for i, stage in enumerate(control.PIPELINE_STAGES):
        control._push_task_event("job-test", "PROGRESS", i * 20, stage, "working")
        event = control.TASKS["job-test"]["events"][-1]
        control.PipelineTelemetry.model_validate(event)
        assert event["revision"] == i + 1
        assert [s["status"] for s in event["dag"]] == ["COMPLETED"] * i + ["RUNNING"] + ["PENDING"] * (4 - i)
    control._push_task_event("job-test", "PROGRESS", 100, control.PIPELINE_STAGES[-1], "validating")
    assert control.TASKS["job-test"]["status"] == "RUNNING"
    assert control.TASKS["job-test"]["progress"] == 99.9
    control._push_task_event("job-test", "COMPLETE", 100, "VALIDATED_OUTPUT", "done", completion())
    task = control.TASKS["job-test"]
    assert task["status"] == "COMPLETED" and task["progress"] == 100
    assert all(s["status"] == "COMPLETED" for s in task["dag"])
    for event_type in ("PROGRESS", "ERROR", "CANCELLED", "COMPLETE"):
        control._push_task_event("job-test", event_type, 0, "INIT", "late")
    assert task["revision"] == 7
    with pytest.raises(HTTPException) as exc:
        asyncio.run(control.cancel_pipeline_job("job-test"))
    assert exc.value.status_code == 409


@pytest.mark.parametrize("stage", ["FEATURE_ENGINEERING", "UNKNOWN", "", None])
def test_invalid_dag_transition_fails_closed(stage):
    register()
    control._push_task_event("job-test", "PROGRESS", 20, stage, "working")
    assert control.TASKS["job-test"]["status"] == "FAILED"
    assert control.TASKS["job-test"]["events"][-1]["payload"]["error_code"] in ("INVALID_STAGE_TRANSITION", "INVALID_TELEMETRY")


@pytest.mark.parametrize("progress", [float("nan"), float("inf"), float("-inf"), -1, 101, 1e13, "1", [], True])
def test_invalid_progress_fails_closed(progress):
    register()
    control._push_task_event("job-test", "PROGRESS", progress, "DATA_INGEST", "working")
    task = control.TASKS["job-test"]
    assert task["status"] == "FAILED"
    assert task["events"][-1]["payload"]["error_code"] == "INVALID_TELEMETRY"
    json.dumps(task["events"][-1], allow_nan=False)


@pytest.mark.parametrize("payload", [{"value": float("nan")}, {"value": object()}, [], {"blob": "x" * 65537}])
def test_payload_validation_and_redaction(payload):
    register()
    control._push_task_event("job-test", "PROGRESS", 0, "DATA_INGEST", "working", payload)
    assert control.TASKS["job-test"]["status"] == "FAILED"
    assert control.TASKS["job-test"]["events"][-1]["payload"]["error_code"] == "INVALID_TELEMETRY"


def test_secret_safe_detached_payload_and_status():
    register()
    payload = {"password": "private-value", "nested": {"url": "https://user:private-value@provider.com?a=secret"}, "rows": [1]}
    control._push_task_event("job-test", "PROGRESS", 0, "DATA_INGEST", "Bearer private-value", payload)
    payload["rows"].append(2)
    result = asyncio.run(control.get_control_status())
    assert "private-value" not in json.dumps(result)
    assert control.TASKS["job-test"]["result"]["rows"] == [1]


@pytest.mark.parametrize("fault", ["missing", "modified", "directory", "utf8", "bom", "partial", "request", "output", "oversized"])
def test_receipt_faults_never_complete(fault):
    register()
    payload = completion()
    path = control.CONTROL_ARTIFACT_ROOT / "job-test.json"
    if fault == "missing":
        path.unlink()
    elif fault == "directory":
        path.unlink()
        path.mkdir()
    elif fault == "utf8":
        path.write_bytes(b"\xff")
    elif fault == "bom":
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    elif fault == "partial":
        path.write_text('{"task_id":', encoding="utf-8")
    elif fault == "oversized":
        path.write_bytes(b" " * 65537)
    elif fault == "request":
        control.TASKS["job-test"]["params"]["initial_capital"] = 2e9
    elif fault == "output":
        payload["metrics"]["total_trades"] = 1
    else:
        payload["receipt"]["task_id"] = "other"
    control._push_task_event("job-test", "COMPLETE", 100, "DONE", "done", payload)
    assert control.TASKS["job-test"]["status"] == "FAILED"
    assert control.TASKS["job-test"]["events"][-1]["payload"]["error_code"] == "INVALID_RECEIPT"


def test_receipt_replace_failure_preserves_prior(tmp_path, monkeypatch):
    register()
    path = tmp_path / "job-test.json"
    path.write_text('{"prior":true}', encoding="utf-8")
    def fail(*_):
        raise OSError("disk failure")
    monkeypatch.setattr(control.os, "replace", fail)
    with pytest.raises(OSError):
        completion()
    assert path.read_text(encoding="utf-8") == '{"prior":true}'
    assert not list(tmp_path.glob("*.tmp"))


def test_cancel_idempotent_terminal_and_publication_blocked():
    register()
    first = asyncio.run(control.cancel_pipeline_job("job-test"))
    asyncio.run(control.cancel_pipeline_job("job-test"))
    control._push_task_event("job-test", "COMPLETE", 100, "DONE", "late")
    assert first["cancelled"] and control.TASKS["job-test"]["revision"] == 1
    assert control.TASKS["job-test"]["status"] == "CANCELLED"
    with pytest.raises(RuntimeError, match="terminal"):
        completion()
    assert not list(control.CONTROL_ARTIFACT_ROOT.glob("*.json"))


def test_concurrent_cancel_completion_first_terminal_wins():
    for index in range(10):
        task_id = f"job-{index}"
        register(task_id)
        payload = completion(task_id)
        barrier = Barrier(2)
        def finish():
            barrier.wait()
            control._push_task_event(task_id, "COMPLETE", 100, "DONE", "done", payload)
        def cancel():
            barrier.wait()
            try:
                asyncio.run(control.cancel_pipeline_job(task_id))
            except HTTPException as exc:
                assert exc.status_code == 409
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(finish), workers.submit(cancel)]
            for future in futures:
                future.result(timeout=5)
        task = control.TASKS[task_id]
        assert task["status"] in ("CANCELLED", "COMPLETED")
        assert len(task["events"]) == 1 and task["revision"] == 1


@pytest.mark.parametrize("limit", [-1, 1001, "nan", "inf", "1.5"])
def test_sse_limit_http_validation(limit):
    register()
    with TestClient(app) as client:
        for path in ("/sse/v1/pipeline/job-test/stream", "/sse/v1/tasks/job-test/progress"):
            assert client.get(path, params={"limit": limit}).status_code == 422
    assert control.TASK_EVENT_QUEUES["job-test"] == []


def test_sse_aliases_terminal_snapshot_no_wait():
    register()
    asyncio.run(control.cancel_pipeline_job("job-test"))
    with TestClient(app) as client:
        for path in ("/sse/v1/pipeline/job-test/stream", "/sse/v1/tasks/job-test/progress"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            assert response.headers["x-accel-buffering"] == "no"
            frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            assert len(frames) == 1 and frames[0]["status"] == "CANCELLED"
    assert control.TASK_EVENT_QUEUES["job-test"] == []


def test_sse_snapshot_boundary_backpressure_and_cleanup():
    register(pipeline=False)
    async def check():
        response = await control.sse_pipeline_stream("job-test")
        iterator = response.body_iterator
        assert len(control.TASK_EVENT_QUEUES["job-test"]) == 1
        snapshot = json.loads((await anext(iterator))["data"])
        assert snapshot["revision"] == 0
        for i in range(60):
            control._push_task_event("job-test", "PROGRESS", 100, "FETCH", "working")
        queue = control.TASK_EVENT_QUEUES["job-test"][0]
        assert queue.qsize() == 50
        control._push_task_event("job-test", "ERROR", None, "FAILED", "failed")
        frames = [json.loads(frame["data"]) async for frame in iterator]
        assert frames[-1]["status"] == "FAILED" and frames[-1]["revision"] == 61
        assert len(frames) == 50
        assert control.TASK_EVENT_QUEUES["job-test"] == []
        assert all(frame["progress"] == 99.9 for frame in frames)
    asyncio.run(check())


def test_sse_full_nonprogress_queue_preserves_terminal():
    register(pipeline=False)
    async def check():
        iterator = (await control.sse_pipeline_stream("job-test")).body_iterator
        await anext(iterator)
        queue = control.TASK_EVENT_QUEUES["job-test"][0]
        for _ in range(50):
            queue.put_nowait({"event_type": "PING", "progress": None})
        control._push_task_event("job-test", "CANCELLED", None, "CANCELLED", "stop")
        frames = [json.loads(frame["data"]) async for frame in iterator]
        assert frames[-1]["status"] == "CANCELLED" and len(frames) == 50
        assert control.TASK_EVENT_QUEUES["job-test"] == []
    asyncio.run(check())


def test_sse_disconnect_eviction_and_cross_thread_delivery():
    register(pipeline=False)
    async def check():
        first = (await control.sse_pipeline_stream("job-test")).body_iterator
        await anext(first)
        await asyncio.to_thread(control._push_task_event, "job-test", "PROGRESS", 1, "FETCH", "working")
        event = json.loads((await anext(first))["data"])
        assert event["revision"] == 1
        others = []
        for _ in range(20):
            iterator = (await control.sse_pipeline_stream("job-test")).body_iterator
            await anext(iterator)
            others.append(iterator)
        assert len(control.TASK_EVENT_QUEUES["job-test"]) == 20
        assert json.loads((await anext(first))["data"])["stage"] == "EVICTED"
        await first.aclose()
        for iterator in others:
            await iterator.aclose()
        assert control.TASK_EVENT_QUEUES["job-test"] == []
    asyncio.run(check())


def test_kill_switch_cancels_only_active_jobs(monkeypatch):
    register()
    register("done")
    control._push_task_event("done", "COMPLETE", 100, "DONE", "done", completion("done"))
    monkeypatch.setattr(control, "verify_totp", lambda _: True)
    asyncio.run(control.trigger_kill_switch(control.KillSwitchRequest(totp_code="123456")))
    assert control.TASKS["job-test"]["status"] == "CANCELLED"
    assert control.TASKS["done"]["status"] == "COMPLETED"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(control.trigger_pipeline_run(control.PipelineRunRequest(), BackgroundTasks()))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("runner,request_class", [
    ("_execute_real_pipeline", "PipelineRunRequest"), ("_run_alphas", "ComputeAlphasRequest"),
    ("_run_optimize", "OptimizePortfolioRequest"), ("_run_backtest", "RunBacktestRequest"),
])
def test_worker_cancellation_is_terminal(runner, request_class, monkeypatch):
    register(pipeline=False)
    async def cancelled(*_):
        raise asyncio.CancelledError
    monkeypatch.setattr(control, "_run_pipeline_task", cancelled)
    asyncio.run(getattr(control, runner)("job-test", getattr(control, request_class)()))
    assert control.TASKS["job-test"]["status"] == "CANCELLED"
    assert control.TASKS["job-test"]["result"] == {}


def test_admission_capacity_duplicate_and_missing_cancel(monkeypatch):
    register()
    with pytest.raises(HTTPException) as exc:
        register()
    assert exc.value.status_code == 409
    monkeypatch.setattr(control, "MAX_ACTIVE_TASKS_LIMIT", 1)
    with pytest.raises(HTTPException) as exc:
        register("second")
    assert exc.value.status_code == 429
    with pytest.raises(HTTPException) as exc:
        asyncio.run(control.cancel_pipeline_job("missing"))
    assert exc.value.status_code == 404
    assert set(control.TASKS) == {"job-test"}


@pytest.mark.parametrize("completed,total,stage", [(0, 0, "DATA_INGEST"), (-1, 5, "DATA_INGEST"), (0, 6, "DATA_INGEST"), (0, 5, "UNKNOWN"), (float("nan"), 5, "DATA_INGEST")])
def test_engine_progress_faults_fail_closed(completed, total, stage, monkeypatch):
    request = register()
    class InvalidEngine:
        def __init__(self, _):
            pass
        def run(self, progress, cancel):
            progress(stage, completed, total)
    monkeypatch.setattr(control, "OmegaPipeline", InvalidEngine)
    asyncio.run(control._execute_real_pipeline("job-test", request))
    assert control.TASKS["job-test"]["status"] == "FAILED"
    assert control.TASKS["job-test"]["events"][-1]["payload"]["error_code"] == "INVALID_ENGINE_PROGRESS"
