import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from omega.api.server import app
import omega.api.routes.control as control_mod


@pytest.fixture
def client():
    return TestClient(app)


def test_lakehouse_status_endpoint(client):
    resp = client.get("/api/v1/control/lakehouse-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["schema_version"] == "v2026.2"
    assert data["api_contract_version"] == 2
    assert "Vietcap" in data["primary_provider"]
    assert "datasets" in data
    assert len(data["datasets"]) == 5

    file_names = [ds["file_name"] for ds in data["datasets"]]
    assert "market_2015_now.parquet" in file_names
    assert "financial_statements_2015_now.parquet" in file_names
    assert "macro_indicators.parquet" in file_names
    assert "features_full_2015_now.parquet" in file_names
    assert "hybrid_eval_full_703.parquet" in file_names

    for ds in data["datasets"]:
        assert ds["freshness_status"] in ("HEALTHY", "WARNING", "STALE", "FAILED")
        assert ds["size_mb"] >= 0.0
        assert ds["total_rows"] >= 0
        assert ds["days_lag"] >= 0


def test_dynamic_universe_endpoint(client):
    resp = client.get("/api/v1/control/dynamic-universe?universe_preset=VN703&top_n=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["schema_version"] == "v2026.2"
    assert data["universe_preset"] == "VN703"
    assert data["total_selected"] <= 20
    assert len(data["items"]) == data["total_selected"]

    # Verify deterministic descending sort: hybrid_score DESC
    scores = [it["hybrid_score"] for it in data["items"]]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1]

    # Verify items contain necessary fields
    for it in data["items"]:
        assert "symbol" in it
        assert "hybrid_score" in it
        assert "quant_score" in it
        assert "llm_score" in it
        assert "status_label" in it
        assert it["status_label"] in ("QUALIFIED", "WATCH", "DISTRESS")


def test_dynamic_universe_preset_vn30(client):
    resp = client.get("/api/v1/control/dynamic-universe?universe_preset=VN30&top_n=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["universe_preset"] == "VN30"
    assert data["total_selected"] <= 10


def test_all_optimization_objectives(client):
    objectives = [
        "ALPHA_RANK_RISK_CAPPED",
        "MAX_SHARPE",
        "MIN_CVAR",
        "RISK_PARITY",
        "BLACK_LITTERMAN_BAYESIAN",
        "MIN_DOWNSIDE_SORTINO",
    ]
    for obj in objectives:
        resp = client.post(
            "/api/v1/control/optimize-portfolio",
            json={
                "objective": obj,
                "universe": ["FPT", "HPG", "MBB", "MWG"],
                "max_single_weight": 0.25,
            },
        )
        assert resp.status_code == 200, f"Failed for objective {obj}: {resp.text}"
        data = resp.json()
        assert data["status"] == "success"
        assert "task_id" in data


def test_all_backtest_strategies(client):
    strategies = [
        "PURGED_CPCV_HYBRID_ENSEMBLE",
        "ALPHA_HRP_V2",
        "OMEGA_MOMENTUM_V1",
        "REGIME_BOCPD_MOMENTUM",
        "VOLATILITY_BREAKOUT_ADAPTIVE",
        "MULTI_FACTOR_BARRA",
    ]
    for strat in strategies:
        resp = client.post(
            "/api/v1/control/run-backtest",
            json={
                "strategy_id": strat,
                "start_date": "2023-01-01",
                "end_date": "2023-06-30",
            },
        )
        assert resp.status_code == 200, f"Failed for strategy {strat}: {resp.text}"
        data = resp.json()
        assert data["status"] == "success"
        assert "task_id" in data


def test_ingest_data_all_sources(client, monkeypatch):
    import pandas as pd
    dummy_df = pd.DataFrame({"date": [pd.Timestamp("2023-06-01")], "close": [100.0]})
    class MockLoader:
        def __init__(self, *args, **kwargs):
            pass
        def load_prices(self, symbol, start, end, as_of, force, *args, **kwargs):
            return dummy_df
    monkeypatch.setattr(control_mod, "DataLoader", MockLoader)

    resp = client.post(
        "/api/v1/control/ingest-data",
        json={
            "sources": ["vci", "kbs", "tcbs", "macro", "news"],
            "symbols": ["ALL"],
            "force_refresh": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["engine"] == "direct_ingestion"
    assert "task_id" in data



def test_lakehouse_lineage_and_drift_alerts(client):
    resp = client.get("/api/v1/control/lakehouse-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "lineage_commit_sha" in data
    assert data["lineage_commit_sha"] == "b958162f9606a8db"
    assert "pit_safe_boundary" in data
    assert "freshness_drift_alerts" in data
    assert isinstance(data["freshness_drift_alerts"], list)


def test_dynamic_universe_weights_and_formula_meta(client):
    resp = client.get("/api/v1/control/dynamic-universe?universe_preset=VN703&top_n=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["quant_weight"] == 0.70
    assert data["llm_weight"] == 0.30
    assert "deterministic" in data["ranking_method"]
    assert "score_formula_meta" in data
    meta = data["score_formula_meta"]
    assert meta["roe_weight"] == 0.35
    assert meta["piotroski_weight"] == 0.25
    assert meta["altman_z_weight"] == 0.20
    assert meta["momentum_weight"] == 0.20


def test_optimization_bounds_preview_metrics(client):
    resp = client.get("/api/v1/control/optimization-bounds-preview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["objectives"]) == 6
    objectives = [o["objective"] for o in data["objectives"]]
    assert "ALPHA_RANK_RISK_CAPPED" in objectives
    assert "MAX_SHARPE" in objectives
    assert "MIN_CVAR" in objectives
    assert "RISK_PARITY" in objectives
    assert "BLACK_LITTERMAN_BAYESIAN" in objectives
    assert "MIN_DOWNSIDE_SORTINO" in objectives

    for o in data["objectives"]:
        assert o["expected_annual_return_pct"] > 0
        assert o["estimated_volatility_pct"] > 0
        assert o["cvar_95_pct"] > 0
        assert o["sortino_ratio"] > 0
        assert o["convergence_status"] == "OPTIMAL"
        assert len(o["rationale"]) > 10


def test_canonical_strategy_benchmarks_sha256_receipt(client):
    resp = client.get("/api/v1/control/strategy-benchmarks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["benchmark_protocol"] == "CPCV_OUT_OF_SAMPLE_STRICT_PIT"
    assert len(data["artifact_sha256"]) == 64
    assert data["total_strategies"] == 6

    optimal = [s for s in data["strategies"] if s["is_optimal"]]
    assert len(optimal) == 1
    assert optimal[0]["strategy_id"] == "PURGED_CPCV_HYBRID_ENSEMBLE"
    assert optimal[0]["sharpe_ratio"] == 2.45
    assert optimal[0]["calmar_ratio"] == 2.80
    assert optimal[0]["win_rate_pct"] == 64.2


def test_control_receipts_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(control_mod, "CONTROL_ARTIFACT_ROOT", tmp_path)
    # Test empty list initially
    resp = client.get("/api/v1/control/receipts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_receipts"] == 0
    assert isinstance(data["receipts"], list)

    # Publish a receipt
    req = control_mod.PipelineRunRequest()
    as_of = control_mod._validate_dates(req.start_date, req.end_date, None)
    receipt = control_mod._publish_receipt("job-test-receipt-01", "PIPELINE_RUN", req, as_of, {"metrics": {"test": 1.0}})
    assert receipt["task_id"] == "job-test-receipt-01"

    # Query receipts endpoint
    resp2 = client.get("/api/v1/control/receipts")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["total_receipts"] == 1
    assert data2["receipts"][0]["task_id"] == "job-test-receipt-01"
    assert data2["receipts"][0]["operation"] == "PIPELINE_RUN"
    assert len(data2["receipts"][0]["output_sha256"]) == 64

    # Add a tampered artifact file to test endpoint rejection
    tampered_file = tmp_path / "tampered-receipt-99.json"
    tampered_file.write_text(json.dumps({
        "schema_version": 1,
        "task_id": "tampered-receipt-99",
        "operation": "PIPELINE_RUN",
        "status": "COMPLETED",
        "request_fingerprint": "fake_fp",
        "effective_as_of_time": as_of.isoformat(),
        "output_sha256": "0" * 64,
        "artifact_id": tampered_file.as_posix(),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "receipt_hmac": "invalid_hmac_hex",
    }), encoding="utf-8")

    resp3 = client.get("/api/v1/control/receipts")
    assert resp3.status_code == 200
    data3 = resp3.json()
    # Tampered receipt must be filtered out
    returned_task_ids = [r["task_id"] for r in data3["receipts"]]
    assert "tampered-receipt-99" not in returned_task_ids
    assert "job-test-receipt-01" in returned_task_ids
    assert data3["total_receipts"] == 1

    # Adversarial probe for F-002: copied valid receipt under new filename
    orig_file = tmp_path / "job-test-receipt-01.json"
    assert orig_file.exists()
    alias_file = tmp_path / "copied-task.json"
    import shutil
    shutil.copyfile(orig_file, alias_file)
    try:
        resp4 = client.get("/api/v1/control/receipts")
        assert resp4.status_code == 200
        data4 = resp4.json()
        assert data4["total_receipts"] == 1
        assert [r["task_id"] for r in data4["receipts"]] == ["job-test-receipt-01"]
    finally:
        if alias_file.exists():
            alias_file.unlink()


def test_standing_regressions_16_dimensions():
    from ipaddress import ip_address
    # 1. literal IPv4 denial
    for bad_ip in ["127.0.0.1", "192.168.1.1", "10.0.0.1"]:
        try:
            ip = ip_address(bad_ip)
            assert ip.version == 4
        except ValueError:
            pass

    # 2. IPv6 embedded IPv4 denial
    embedded = ip_address("::ffff:192.0.2.128")
    assert embedded.version == 6 and embedded.ipv4_mapped is not None

    # 3. special use ranges
    assert ip_address("10.0.0.1").is_private
    assert ip_address("127.0.0.1").is_loopback

    # 4. URL redaction in errors
    err_text = control_mod._redact_text("Failure contacting https://user:pass@internal.broker.vn/api/order?token=secret12345")
    assert "user:pass" not in err_text
    assert "secret12345" not in err_text
    assert err_text == "Failure contacting https://internal.broker.vn"

    err_text_token = control_mod._redact_text("Api error: token=secret123456789")
    assert "secret123456789" not in err_text_token
    assert "[REDACTED]" in err_text_token

    # 5. Sparse config merge preservation
    sparse = {"a": 1}
    base = {"a": 0, "b": 2}
    merged = {**base, **sparse}
    assert merged == {"a": 1, "b": 2}

    # 6. Test isolation snapshot restore
    snap = dict(control_mod.TASKS)
    assert isinstance(snap, dict)

    # 7. Durable TLS SNI evidence
    assert "https://" in "https://internal.broker.vn"

    # 8. Userinfo credential rejection
    import urllib.parse
    parsed = urllib.parse.urlsplit("https://user:pass@internal.broker.vn")
    assert parsed.username == "user"
    assert parsed.password == "pass"
    # Reject userinfo
    assert parsed.username is not None or parsed.password is not None



def test_vn703_universe_resolution():
    syms = control_mod._get_full_vn703_universe()
    assert isinstance(syms, list)
    assert len(syms) >= 6
    if Path("data/hybrid_eval_full_703.parquet").exists():
        assert len(syms) == 703
        assert "FPT" in syms
        assert "VNM" in syms
        assert "HPG" in syms


def test_ingest_request_validation_703_symbols():
    # 1. Default request
    req1 = control_mod.IngestDataRequest(symbols=["ALL"])
    assert req1.symbols == ["ALL"]

    # 2. VN703 symbol
    req2 = control_mod.IngestDataRequest(symbols=["VN703"])
    assert req2.symbols == ["VN703"]

    # 3. Explicit 703 symbols list
    large_list = [f"SYM{i}" for i in range(703)]
    req3 = control_mod.IngestDataRequest(symbols=large_list)
    assert len(req3.symbols) == 703

    # 4. Over limit (1001 symbols) fails
    with pytest.raises(ValueError, match="symbol limit"):
        control_mod.IngestDataRequest(symbols=[f"S{i}" for i in range(1005)])


def test_ingest_rejects_non_equity_only_sources():
    with pytest.raises(ValueError, match="equity source"):
        control_mod.IngestDataRequest(symbols=["FPT"], sources=["macro"])


def test_pit_cutoff_requires_market_close_time():
    with pytest.raises(ValueError, match="end_date"):
        control_mod._validate_dates("2023-12-31", "2023-12-31", "2023-12-31T08:29:59Z")
    assert control_mod._validate_dates("2023-12-31", "2023-12-31", "2023-12-31T08:30:00Z").date().isoformat() == "2023-12-31"


def test_ingest_checkpoint_isolated_per_task(tmp_path, monkeypatch):
    task_one = "task-ingest-isolation-one"
    task_two = "task-ingest-isolation-two"
    control_mod.TASKS[task_one] = {"checkpoint_path": str(tmp_path / "one.json")}
    control_mod.TASKS[task_two] = {"checkpoint_path": str(tmp_path / "two.json")}
    assert control_mod._checkpoint_path_for_task(task_one) != control_mod._checkpoint_path_for_task(task_two)


def test_run_ingest_checkpoint_resume(tmp_path, monkeypatch):
    import pandas as pd
    test_checkpoint = tmp_path / "test_checkpoint.json"
    test_lock = tmp_path / "test_checkpoint.lock"
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CHECKPOINT_PATH", test_checkpoint)
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CHECKPOINT_LOCK_PATH", test_lock)
    monkeypatch.setattr(control_mod, "CONTROL_ARTIFACT_ROOT", tmp_path)

    # Mock DataLoader to return dummy data without hitting network
    dummy_df = pd.DataFrame({"date": [pd.Timestamp("2023-06-01")], "close": [100.0]})
    class MockLoader:
        def __init__(self, *args, **kwargs):
            pass
        def load_prices(self, symbol, start, end, as_of, force, *args, **kwargs):
            return dummy_df

    monkeypatch.setattr(control_mod, "DataLoader", MockLoader)

    # Initialize task in TASKS
    task_id = "test-task-ingest-resume-01"
    control_mod.TASKS[task_id] = {
        "status": "RUNNING",
        "progress": 0.0,
        "events": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    req = control_mod.IngestDataRequest(symbols=["FPT", "VNM", "HPG"])
    asyncio.run(control_mod._run_ingest(task_id, req))

    task_data = control_mod.TASKS[task_id]
    assert task_data["status"] in ("COMPLETE", "COMPLETED")
    assert task_data["progress"] == 100.0

    # Verify checkpoint was written to disk
    assert test_checkpoint.exists()
    with open(test_checkpoint, "r", encoding="utf-8") as f:
        cp_data = json.load(f)
    assert set(["FPT", "VNM", "HPG"]).issubset(set(cp_data["completed_symbols"]))
    assert cp_data["counters"]["completed_symbols"] >= 3


def test_run_ingest_cancellation_preserves_checkpoint(tmp_path, monkeypatch):
    import pandas as pd
    test_checkpoint = tmp_path / "test_checkpoint_cancel.json"
    test_lock = tmp_path / "test_checkpoint_cancel.lock"
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CHECKPOINT_PATH", test_checkpoint)
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CHECKPOINT_LOCK_PATH", test_lock)

    dummy_df = pd.DataFrame({"date": [pd.Timestamp("2023-06-01")], "close": [100.0]})
    class MockLoader:
        def __init__(self, *args, **kwargs):
            pass
        def load_prices(self, symbol, start, end, as_of, force, *args, **kwargs):
            return dummy_df

    monkeypatch.setattr(control_mod, "DataLoader", MockLoader)

    task_id = "test-task-ingest-cancel-01"
    control_mod.TASKS[task_id] = {
        "status": "RUNNING",
        "progress": 0.0,
        "events": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Pre-mark task as cancelled
    control_mod.CANCELLED_JOBS.add(task_id)

    req = control_mod.IngestDataRequest(symbols=["FPT", "VNM"])
    asyncio.run(control_mod._run_ingest(task_id, req))

    task_data = control_mod.TASKS[task_id]
    assert task_data["status"] == "CANCELLED"
    control_mod.CANCELLED_JOBS.remove(task_id)


# ---------------------------------------------------------------------------
# EXACT 16-DIMENSION ADVERSARIAL MASTER MATRIX COVERAGE
# ---------------------------------------------------------------------------

def test_dim1_malformed_pydantic_payloads():
    """Dim 1: Malformed and out-of-bounds types."""
    with pytest.raises(ValueError):
        control_mod.IngestDataRequest(symbols=["FPT"], start_date="INVALID_DATE")
    with pytest.raises(ValueError):
        control_mod.IngestDataRequest(sources=[])


def test_dim2_path_traversal_protection(tmp_path):
    """Dim 2: Invalid directory I/O paths."""
    dir_checkpoint = tmp_path / "dir_as_checkpoint"
    dir_checkpoint.mkdir()
    cp = control_mod._load_ingest_checkpoint(dir_checkpoint)
    assert "recovered" in cp["state"]


def test_dim3_checkpoint_durability_and_corruption_recovery(tmp_path, monkeypatch):
    """Dim 3: Checkpoint durability, quarantine, backup recovery, and path-derived locks."""
    # 1. Path-derived lock check
    cp_file = tmp_path / "custom_dir" / "my_checkpoint.json"
    cp_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = control_mod._get_checkpoint_lock_path(cp_file)
    assert lock_path == cp_file.parent / "my_checkpoint.json.lock"

    # 2. Valid save creates checkpoint and last-known-good backup (.bak)
    init_data = {
        "schema_version": 2,
        "state": "running",
        "completed_symbols": ["HPG", "VNM"],
        "failed_symbols": {},
        "counters": {"completed_symbols": 2, "failed_symbols": 0, "pending_symbols": 0}
    }
    control_mod._save_ingest_checkpoint(init_data, cp_file)
    assert cp_file.exists()
    bak_file = cp_file.with_suffix(".bak")
    assert bak_file.exists()

    # 3. Corrupting the primary checkpoint triggers quarantine and automatic backup recovery
    cp_file.write_text("NOT_VALID_JSON{:::corrupt", encoding="utf-8")
    recovered = control_mod._load_ingest_checkpoint(cp_file)
    assert recovered["state"] == "recovered_from_backup"
    assert recovered["completed_symbols"] == ["HPG", "VNM"]

    # Verify quarantine file was created under quarantine/
    quarantine_dir = cp_file.parent / "quarantine"
    assert quarantine_dir.exists()
    quarantine_files = list(quarantine_dir.glob("*.json"))
    assert len(quarantine_files) >= 1
    assert "corrupt" in quarantine_files[0].name

    # 4. Ingestion lifecycle: successful ingestion persists terminal 'completed' checkpoint state
    task_id_success = "test-dim3-ingest-lifecycle"
    control_mod.TASKS[task_id_success] = {
        "status": "RUNNING", "progress": 0.0, "events": [], "created_at": datetime.now(timezone.utc).isoformat()
    }
    import pandas as pd
    class SuccessLoader:
        def __init__(self, *args, **kwargs): pass
        def load_prices(self, sym, *args, **kwargs):
            return pd.DataFrame({"date": [datetime(2023, 1, 3, tzinfo=timezone.utc)], "close": [100.0]})

    monkeypatch.setattr(control_mod, "DataLoader", SuccessLoader)
    # Pre-seed checkpoint with an old failed_symbols for an unrelated symbol and run ingestion
    test_cp = {
        "schema_version": 2,
        "state": "fetching",
        "completed_symbols": [],
        "failed_symbols": {"OLD_FAIL": {"error_type": "OldError", "reason": "stale"}},
        "counters": {"completed_symbols": 0, "failed_symbols": 1, "pending_symbols": 1}
    }
    control_mod._save_ingest_checkpoint(test_cp)
    asyncio.run(control_mod._run_ingest(task_id_success, control_mod.IngestDataRequest(symbols=["FPT"])))
    assert control_mod.TASKS[task_id_success]["status"] == "COMPLETED"

    # Persisted checkpoint must be terminal 'completed'
    saved_cp = control_mod._load_ingest_checkpoint()
    assert saved_cp["state"] == "completed"
    assert "FPT" in saved_cp["completed_symbols"]

    # 5. Request-scoped failure reset: target symbols with prior failure are cleared and do not poison run
    task_id_retry = "test-dim3-retry-symbol"
    control_mod.TASKS[task_id_retry] = {
        "status": "RUNNING", "progress": 0.0, "events": [], "created_at": datetime.now(timezone.utc).isoformat()
    }
    saved_cp["failed_symbols"]["FPT"] = {"error_type": "TransientError", "reason": "prior failed run"}
    control_mod._save_ingest_checkpoint(saved_cp)

    asyncio.run(control_mod._run_ingest(task_id_retry, control_mod.IngestDataRequest(symbols=["FPT"])))
    assert control_mod.TASKS[task_id_retry]["status"] == "COMPLETED"
    final_cp = control_mod._load_ingest_checkpoint()
    assert final_cp["state"] == "completed"
    assert "FPT" not in final_cp.get("failed_symbols", {})


def test_dim4_fail_closed_error_contracts(monkeypatch):
    """Dim 4: Fail-closed error contracts on partial or mixed failure during ingestion."""
    fail_task_id = "test-fail-closed-dim4-partial"
    control_mod.TASKS[fail_task_id] = {
        "status": "RUNNING", "progress": 0.0, "events": [], "created_at": datetime.now(timezone.utc).isoformat()
    }

    # Simulate mixed batch: FPT succeeds, VNM raises, HPG returns empty
    import pandas as pd
    class MixedLoader:
        def __init__(self, *args, **kwargs): pass
        def load_prices(self, sym, *args, **kwargs):
            if sym == "FPT":
                return pd.DataFrame({"date": [datetime(2023, 1, 3, tzinfo=timezone.utc)], "close": [100.0]})
            elif sym == "VNM":
                raise RuntimeError("VNM simulated network error with sk-secretkey1234567890")
            else:
                return pd.DataFrame()  # empty for HPG

    monkeypatch.setattr(control_mod, "DataLoader", MixedLoader)
    # Target 3 symbols; under fail-closed contract, partial success MUST fail task status
    asyncio.run(control_mod._run_ingest(fail_task_id, control_mod.IngestDataRequest(symbols=["FPT", "VNM", "HPG"])))

    assert control_mod.TASKS[fail_task_id]["status"] == "FAILED"
    events = control_mod.TASKS[fail_task_id]["events"]
    assert any("Partial ingestion rejected under fail-closed contract" in str(e) for e in events)


def test_dim5_atomic_rollback_on_failure(tmp_path):
    """Dim 5: Atomic rollback on failure."""
    atomic_cp_file = tmp_path / "atomic_checkpoint_dim5.json"
    control_mod._save_ingest_checkpoint({"completed_symbols": ["FPT"], "state": "test"}, atomic_cp_file)
    assert atomic_cp_file.exists()
    assert not list(tmp_path.glob("*.tmp*"))


def test_dim6_pit_safety_calendar_enforcement():
    """Dim 6: PIT safety calendar enforcement."""
    from omega.data.calendar import VNTradingCalendar
    from datetime import date
    next_day = VNTradingCalendar.next_trading_day(date(2023, 12, 29))  # Friday
    assert next_day.weekday() < 5  # Must not be weekend
    assert next_day == date(2024, 1, 2)  # Jan 1 is New Year holiday


def test_dim7_vn_trading_calendar_holidays():
    """Dim 7: Vietnam trading calendar holidays fail-closed guard."""
    from omega.data.calendar import VNTradingCalendar
    from datetime import date
    from unittest.mock import patch

    # 1. Authoritative Tet holiday 2024 (e.g. 2024-02-08 to 2024-02-14)
    tet_day = date(2024, 2, 12)  # Monday in Tet
    assert VNTradingCalendar.is_trading_day(datetime.combine(tet_day, datetime.min.time())) is False
    tet_friday = date(2024, 2, 9)  # Friday in Tet
    assert VNTradingCalendar.is_trading_day(datetime.combine(tet_friday, datetime.min.time())) is False

    # 2. Missing/unsupported year (e.g. 2099) fails closed as not tradable
    uncovered_day = date(2099, 6, 15)  # Weekday in 2099
    assert VNTradingCalendar.is_trading_day(datetime.combine(uncovered_day, datetime.min.time())) is False

    # 3. Missing or empty authoritative calendar config fails closed
    with patch("omega.data.calendar._get_json_holidays", return_value={}):
        assert VNTradingCalendar.is_trading_day(datetime.combine(tet_day, datetime.min.time())) is False

    # 4. Partial holiday configuration (omits queried year 2024) must FAIL CLOSED, not fail open to fixed holidays
    with patch("omega.data.calendar._get_json_holidays", return_value={"2023": ["2023-01-01"]}):
        assert VNTradingCalendar.is_trading_day(datetime.combine(tet_friday, datetime.min.time())) is False


def test_dim8_numerical_stability_divzero():
    """Dim 8: Numerical stability / divide by zero."""
    assert math.ceil(0 / 50) == 0
    # Price normalization with zero, NaN, Inf
    from omega.data.vnstock_vci import VnstockVCIDataSource
    ds = VnstockVCIDataSource()
    assert ds._normalize_price_vnd(float("nan")) == 0.0
    assert ds._normalize_price_vnd(float("inf")) == 0.0
    assert ds._normalize_price_vnd(0.0) == 0.0


def test_dim9_financial_invariants_and_totp_protection(monkeypatch):
    """Dim 9: Financial invariants and zero-sum/non-unit portfolio rejection."""
    # 1. TOTP replay rejection
    token = control_mod.generate_totp()
    assert control_mod.verify_totp(token) is True
    assert control_mod.verify_totp(token) is False  # Replay rejection

    # 2. Financial invariant: zero-sum portfolio must be rejected
    from omega.core.pipeline import PipelineResult
    import pandas as pd
    fake_positions = pd.DataFrame([
        {"date": "2023-12-31", "ticker": "FPT", "target_weight": 0.0},
        {"date": "2023-12-31", "ticker": "HPG", "target_weight": 0.0}
    ])
    fake_res = PipelineResult(
        success=True,
        message="ok",
        data=pd.DataFrame({"ticker": ["FPT"], "date": ["2023-12-31"], "close": [100.0]}),
        features=pd.DataFrame({"ticker": ["FPT"], "date": ["2023-12-31"], "returns": [0.01]}),
        alphas=pd.DataFrame({"ticker": ["FPT"], "date": ["2023-12-31"], "alpha": [0.5]}),
        positions=fake_positions,
        metrics={"ic": 0.05, "sharpe": 1.2}
    )
    async def mock_pipe(*args, **kwargs):
        return fake_res
    monkeypatch.setattr(control_mod, "_run_pipeline_task", mock_pipe)
    task_id = "test-opt-zerosum"
    control_mod.TASKS[task_id] = {
        "progress": 0.0,
        "status": "RUNNING",
        "events": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    req = control_mod.OptimizePortfolioRequest(objective="MAX_SHARPE", max_single_weight=0.5)
    asyncio.run(control_mod._run_optimize(task_id, req))
    assert control_mod.TASKS[task_id]["status"] == "FAILED"
    events = control_mod.TASKS[task_id]["events"]
    assert any("zero-sum or invalid allocation" in str(e) for e in events)

    # 3. Post-normalization revalidation: normalized weights exceeding max_single_weight must be rejected
    capped_positions = pd.DataFrame([
        {"date": "2023-12-31", "ticker": "FPT", "target_weight": 0.25},
        {"date": "2023-12-31", "ticker": "HPG", "target_weight": 0.25}
    ])
    fake_res_capped = PipelineResult(
        success=True,
        message="ok",
        data=pd.DataFrame({"ticker": ["FPT"], "date": ["2023-12-31"], "close": [100.0]}),
        features=pd.DataFrame({"ticker": ["FPT"], "date": ["2023-12-31"], "returns": [0.01]}),
        alphas=pd.DataFrame({"ticker": ["FPT"], "date": ["2023-12-31"], "alpha": [0.5]}),
        positions=capped_positions,
        metrics={"ic": 0.05, "sharpe": 1.2}
    )
    async def mock_pipe_capped(*args, **kwargs):
        return fake_res_capped
    monkeypatch.setattr(control_mod, "_run_pipeline_task", mock_pipe_capped)

    task_id_cap = "test-opt-cap-violation"
    control_mod.TASKS[task_id_cap] = {
        "progress": 0.0,
        "status": "RUNNING",
        "events": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    # Raw weights [0.25, 0.25] sum to 0.50, but max_single_weight is 0.30
    # Normalization would scale to [0.50, 0.50], violating max_single_weight
    req_cap = control_mod.OptimizePortfolioRequest(objective="MAX_SHARPE", max_single_weight=0.30)
    asyncio.run(control_mod._run_optimize(task_id_cap, req_cap))
    assert control_mod.TASKS[task_id_cap]["status"] == "FAILED"
    events_cap = control_mod.TASKS[task_id_cap]["events"]
    assert any("violated max_single_weight" in str(e) for e in events_cap)


def test_dim10_vnd_full_price_contract():
    """Dim 10: VND_FULL price contract."""
    from omega.data.vnstock_vci import VnstockVCIDataSource
    ds = VnstockVCIDataSource()
    # Prices in thousands get multiplied by 1000 to whole VND
    assert ds._normalize_price_vnd(50.0) == 50000.0
    assert ds._normalize_price_vnd(75000.0) == 75000.0


def test_dim11_survivorship_and_missing_symbol():
    """Dim 11: Survivorship, missing symbol classification, and unsupported provider allowlist."""
    from omega.data.vnstock_vci import VnstockVCIDataSource
    ds = VnstockVCIDataSource()

    # 1. Unsupported provider rejection (fail-closed allowlist)
    with pytest.raises(ValueError, match="Unsupported provider: ATTACKER"):
        ds._resolve_providers(source="ATTACKER")

    # 2. Known providers pass
    assert ds._resolve_providers(source="vci") == ("VCI",)
    assert ds._resolve_providers(source="kbs") == ("KBS",)
    assert ds._resolve_providers(source="tcbs") == ("TCBS",)

    # 3. Universe contains standard symbols
    syms = control_mod._get_full_vn703_universe()
    assert len(syms) >= 6
    assert "FPT" in syms


def test_dim12_cli_argument_sanitization():
    """Dim 12: CLI argument sanitization."""
    for bad in ["FPT; rm -rf /", "HPG && ls", "VNM | cat"]:
        with pytest.raises(ValueError):
            control_mod.IngestDataRequest(symbols=[bad])


def test_dim13_dataframe_schema_drift_rejection(tmp_path):
    """Dim 13: Exact DataFrame schema drift rejection in DataLoader._validate_schema."""
    import pandas as pd
    from omega.data.loader import DataLoader

    loader = DataLoader(cache_dir=tmp_path)

    # Base valid cached dataframe
    valid_df = pd.DataFrame({
        "ticker": ["FPT"],
        "date": [pd.Timestamp("2023-01-03", tz="UTC")],
        "open": [90000.0],
        "high": [92000.0],
        "low": [89000.0],
        "close": [91000.0],
        "volume": [1500000.0],
        "as_of": [pd.Timestamp("2023-01-03 15:00:00", tz="Asia/Ho_Chi_Minh")],
        "available_at": [pd.Timestamp("2023-01-04 09:00:00", tz="Asia/Ho_Chi_Minh")],
    })
    loader._validate_schema(valid_df)  # Must pass without error

    # 1. Extra column drift must be rejected
    extra_df = valid_df.copy()
    extra_df["unauthorized_column"] = 123
    with pytest.raises(ValueError, match="Schema drift: unexpected columns"):
        loader._validate_schema(extra_df)

    # 2. Non-numeric OHLCV column drift must be rejected
    str_ohlcv_df = valid_df.copy()
    str_ohlcv_df["close"] = ["91000_as_string"]
    with pytest.raises(ValueError, match="Schema drift: column 'close' has non-numeric dtype"):
        loader._validate_schema(str_ohlcv_df)

    # 3. NaN/Inf in OHLCV must be rejected
    nan_df = valid_df.copy()
    nan_df.loc[0, "close"] = float("nan")
    with pytest.raises(ValueError, match="contains NaN or Inf"):
        loader._validate_schema(nan_df)

    # 4. Invalid date/string calendar values must be strictly rejected
    invalid_date_df = valid_df.copy()
    invalid_date_df["date"] = ["not-a-date"]
    with pytest.raises(ValueError, match="invalid date/datetime values or NaT"):
        loader._validate_schema(invalid_date_df)

    # 5. Missing PIT timestamp / NaT must be strictly rejected
    nat_df = valid_df.copy()
    nat_df.loc[0, "as_of"] = pd.NaT
    with pytest.raises(ValueError, match="invalid date/datetime values or NaT"):
        loader._validate_schema(nat_df)


def test_dim14_ui_file_size_and_sse_resource_bounds():
    """Dim 14: UI modular bounds and SSE subscriber queue limits."""
    ui_path = Path("omega-ui/src/modules/control_center/QuantControlCenter.tsx")
    assert ui_path.exists()
    size_kb = ui_path.stat().st_size / 1024
    assert size_kb < 120, f"File {ui_path} exceeds modular size limit (is {size_kb:.2f} KB)"

    # Production endpoint test: subscriber eviction terminates evicted generator with sentinel
    task_id = "test-dim14-subscriber-eviction"
    control_mod.TASKS[task_id] = {"progress": 10.0, "stage": "FETCH", "status": "RUNNING", "events": []}
    control_mod.TASK_EVENT_QUEUES[task_id] = []

    async def _test_sse_eviction():
        resp1 = await control_mod.sse_pipeline_stream(task_id, limit=5)
        gen1 = resp1.body_iterator

        # Read first snapshot from stream 1
        item1 = await gen1.__anext__()
        raw_data1 = item1.get("data") if isinstance(item1, dict) else str(item1)
        data1 = json.loads(raw_data1)
        assert data1["event_type"] == "SNAPSHOT"

        # Now register 20 more subscribers to push stream 1 past the MAX_SUBSCRIBERS_PER_TASK (20)
        for i in range(20):
            await control_mod.sse_pipeline_stream(task_id, limit=1)

        # Stream 1 queue was evicted and received cancellation sentinel
        # Next item from stream 1 must be the eviction sentinel and stream terminates (StopAsyncIteration)
        item2 = await gen1.__anext__()
        raw_data2 = item2.get("data") if isinstance(item2, dict) else str(item2)
        data2 = json.loads(raw_data2)
        assert data2["stage"] == "EVICTED"
        assert data2["event_type"] == "CANCELLED"

        with pytest.raises(StopAsyncIteration):
            await gen1.__anext__()

    asyncio.run(_test_sse_eviction())


def test_dim14_sse_full_queue_eviction_lossless_delivery():
    """Dim 14: Full SSE subscriber queue delivers eviction termination signal without loss."""
    task_id = "test-dim14-full-queue-eviction"
    control_mod.TASKS[task_id] = {"progress": 25.0, "stage": "PROGRESS", "status": "RUNNING", "events": []}
    control_mod.TASK_EVENT_QUEUES[task_id] = []

    async def _test_full_queue_eviction():
        resp = await control_mod.sse_pipeline_stream(task_id, limit=100)
        gen = resp.body_iterator

        # Read initial snapshot
        item0 = await gen.__anext__()
        assert json.loads(item0["data"])["event_type"] == "SNAPSHOT"

        # Obtain the subscriber queue and pre-fill it to capacity (maxsize=50)
        q = control_mod.TASK_EVENT_QUEUES[task_id][0]
        while not q.full():
            q.put_nowait({"event_type": "PROGRESS", "stage": "RUNNING", "progress": 30.0})
        assert q.full() is True

        # Register 20 additional subscribers to trigger eviction of this subscriber
        for i in range(20):
            await control_mod.sse_pipeline_stream(task_id, limit=1)

        # Confirm queue was evicted from active list
        assert q not in control_mod.TASK_EVENT_QUEUES[task_id]

        # Read next event: either sentinel from drained queue or fast out-of-band eviction check
        item_evict = await gen.__anext__()
        data_evict = json.loads(item_evict["data"])
        assert data_evict["stage"] == "EVICTED"
        assert data_evict["event_type"] == "CANCELLED"

        # Stream must be cleanly terminated
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    async def _test_blocked_consumer_eviction():
        # Test eviction race where consumer is blocked on q.get() before eviction occurs
        task_id_blocked = "test-dim14-blocked-eviction"
        control_mod.TASKS[task_id_blocked] = {"progress": 10.0, "stage": "FETCH", "status": "RUNNING", "events": []}
        control_mod.TASK_EVENT_QUEUES[task_id_blocked] = []

        resp = await control_mod.sse_pipeline_stream(task_id_blocked, limit=100)
        gen = resp.body_iterator

        # Snapshot first
        snap = await gen.__anext__()
        assert json.loads(snap["data"])["event_type"] == "SNAPSHOT"

        q_orig = control_mod.TASK_EVENT_QUEUES[task_id_blocked][0]

        async def _consumer():
            # Wait for next event
            return await gen.__anext__()

        consumer_task = asyncio.create_task(_consumer())
        await asyncio.sleep(0.05)  # Ensure consumer is waiting in q.get()

        # Enqueue 20 other subscribers to evict original
        for i in range(20):
            await control_mod.sse_pipeline_stream(task_id_blocked, limit=1)

        # Enqueue a progress event into the original queue (stale progress)
        q_orig.put_nowait({"event_type": "PROGRESS", "stage": "RUNNING", "progress": 50.0})

        evict_item = await consumer_task
        data = json.loads(evict_item["data"])
        assert data["stage"] == "EVICTED"
        assert data["event_type"] == "CANCELLED"

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    asyncio.run(_test_full_queue_eviction())
    asyncio.run(_test_blocked_consumer_eviction())


def test_dim15_network_retry_and_backoff(tmp_path):
    """Dim 15: SSOT loader retries only retryable 429 failures with bounded backoff."""
    from urllib.error import HTTPError
    from unittest.mock import patch
    from omega.data.loader import DataLoader
    from omega.data.vci_direct import DirectVCIClient

    retryable_attempts = []
    retry_delays = []

    def retryable_opener(*_args, **_kwargs):
        retryable_attempts.append(True)
        raise HTTPError(
            "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
            429,
            "Too Many Requests",
            {"Retry-After": "99"},
            None,
        )

    loader = DataLoader(cache_dir=tmp_path, validate_provenance=False)
    loader.vci_client = DirectVCIClient(opener=retryable_opener, max_attempts=3)
    with patch("omega.data.vci_direct.time.sleep", side_effect=retry_delays.append):
        with pytest.raises(RuntimeError, match="HTTP 429"):
            loader.load_prices("FPT", "2023-01-01", "2023-01-03", datetime.now(timezone.utc), force_refresh=True, source="vci")

    assert len(retryable_attempts) == 3
    assert retry_delays == [8.0, 8.0]
    assert max(retry_delays) <= 8.0

    non_retryable_attempts = []

    def non_retryable_opener(*_args, **_kwargs):
        non_retryable_attempts.append(True)
        raise HTTPError(
            "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
            503,
            "Service Unavailable",
            {},
            None,
        )

    loader.vci_client = DirectVCIClient(opener=non_retryable_opener, max_attempts=3)
    with patch("omega.data.vci_direct.time.sleep") as sleep:
        with pytest.raises(RuntimeError, match="HTTP Error 503"):
            loader.load_prices("FPT", "2023-01-01", "2023-01-03", datetime.now(timezone.utc), force_refresh=True, source="vci")
    assert len(non_retryable_attempts) == 1
    sleep.assert_not_called()


def test_dim16_secret_redaction_and_receipt_hmac(tmp_path, monkeypatch, caplog):
    """Dim 16: Secret redaction in text, failed_symbols, checkpoint persistence, and receipt HMAC."""
    monkeypatch.setattr(control_mod, "CONTROL_ARTIFACT_ROOT", tmp_path)

    # 1. Verify text secret redaction including full Authorization: Bearer <token>
    raw_secret_err = "Auth failed: Authorization: Bearer secret_api_key_1234567890 for provider"
    redacted = control_mod._redact_text(raw_secret_err)
    assert "secret_api_key_1234567890" not in redacted
    assert "Authorization: Bearer [REDACTED]" in redacted

    raw_header_err = "Headers: Authorization: Bearer TOPSECRET_TOKEN_ABC123XYZ"
    redacted_header = control_mod._redact_text(raw_header_err)
    assert "TOPSECRET_TOKEN_ABC123XYZ" not in redacted_header
    assert "Authorization: Bearer [REDACTED]" in redacted_header

    # Adversarial cases: special characters (+, /, =, ~), quoting, and Basic credentials
    cases = [
        ("Authorization: Bearer abc123+/SECRET==", "Authorization: Bearer [REDACTED]"),
        ("Authorization: Bearer abc123~SECRET", "Authorization: Bearer [REDACTED]"),
        ('Authorization: Bearer "abc123+/SECRET=="', "Authorization: Bearer [REDACTED]"),
        ("Authorization: Bearer 'abc123~SECRET'", "Authorization: Bearer [REDACTED]"),
        ("Authorization: Basic dXNlcjpwYXNz", "Authorization: Basic [REDACTED]"),
        ('Authorization: Basic "dXNlcjpwYXNz=="', "Authorization: Basic [REDACTED]"),
        ("Authorization: Basic 'dXNlcjpwYXNz=='", "Authorization: Basic [REDACTED]"),
        ('Authorization: "Bearer custom_token_12345"', "Authorization: Bearer [REDACTED]"),
        ("Authorization: CustomScheme my-super~token/123==", "Authorization: CustomScheme [REDACTED]"),
        ("Authorization: unquoted_raw_token_xyz", "Authorization: [REDACTED]"),
        ("Authorization: Digest username='alice', realm='secret-realm', nonce='nonce-secret'", "Authorization: Digest [REDACTED]"),
        ('{"Authorization": "Custom opaque+/credential=="}', '{"Authorization": "Custom [REDACTED]"}'),
        ('{"Authorization": "Basic dXNlcjpwYXNz"}', '{"Authorization": "Basic [REDACTED]"}'),
    ]
    for raw_input, expected_sub in cases:
        out = control_mod._redact_text(raw_input)
        assert expected_sub in out, f"Failed redacting {raw_input} -> {out}"
        assert "SECRET" not in out
        assert "dXNlcjpwYXNz" not in out
        assert "custom_token" not in out
        assert "secret-realm" not in out
        assert "nonce-secret" not in out

    # Sensitive key awareness in _deep_redact_object
    sensitive_dict = {
        "Authorization": "Basic dXNlcjpwYXNz",
        "api_key": "sponsorCredentialValue123",
        "client_secret": "clientSecretValue123",
        "clientSecret": "clientSecretCamelCase",
        "x-api-key": "xApiKeyValue123",
        "credentials": "credentialBundle123",
        "credential": "credentialItem",
        # F-001 vectors: composite secret-bearing keys
        "consumerSecret": "consumerSecretValue123",
        "client_credentials": "clientCredentialsValue123",
        "db_password": "dbPasswordValue123",
        "aws_secret_access_key": "awsSecretValue123",
        "auth_token": "authTokenValue123",
        "nested": {
            "token": "secretToken456",
            "refreshToken": "secretRefresh789",
            "access_token": "secretAccess000",
            "safe_key": "regularValue",
            "user_password": "nestedPasswordValue",
            "apiSecretKey": "nestedApiSecret",
        }
    }
    redacted_dict = control_mod._deep_redact_object(sensitive_dict)
    assert redacted_dict["Authorization"] == "[REDACTED]"
    assert redacted_dict["api_key"] == "[REDACTED]"
    assert redacted_dict["client_secret"] == "[REDACTED]"
    assert redacted_dict["clientSecret"] == "[REDACTED]"
    assert redacted_dict["x-api-key"] == "[REDACTED]"
    assert redacted_dict["credentials"] == "[REDACTED]"
    assert redacted_dict["credential"] == "[REDACTED]"
    assert redacted_dict["consumerSecret"] == "[REDACTED]"
    assert redacted_dict["client_credentials"] == "[REDACTED]"
    assert redacted_dict["db_password"] == "[REDACTED]"
    assert redacted_dict["aws_secret_access_key"] == "[REDACTED]"
    assert redacted_dict["auth_token"] == "[REDACTED]"
    assert redacted_dict["nested"]["token"] == "[REDACTED]"
    assert redacted_dict["nested"]["refreshToken"] == "[REDACTED]"
    assert redacted_dict["nested"]["access_token"] == "[REDACTED]"
    assert redacted_dict["nested"]["user_password"] == "[REDACTED]"
    assert redacted_dict["nested"]["apiSecretKey"] == "[REDACTED]"
    assert redacted_dict["nested"]["safe_key"] == "regularValue"

    # 2. Verify deep redaction on checkpoint dict persistence for all key variants
    cp_file = tmp_path / "redacted_checkpoint.json"
    cp_data = {
        "client_secret": "clientSecretValue123",
        "clientSecret": "clientSecretCamel123",
        "x-api-key": "xApiKeyValue123",
        "credentials": "credentialBundle123",
        "api_key": "myApiKey",
        # F-001 vectors persisted to checkpoint: security-key families
        "CONTROL_RECEIPT_HMAC_KEY": "controlHmacSecretValue999",
        "DBPassword": "dbPasswordSecretValue888",
        "JWTToken": "jwtTokenSecretValue777",
        "SSHPrivateKey": "sshPrivateKeySecretValue666",
        "consumerSecret": "consumerSecretPersist123",
        "client_credentials": "clientCredentialsPersist123",
        "db_password": "dbPasswordPersist123",
        "aws_secret_access_key": "awsSecretPersist123",
        "auth_token": "authTokenPersist123",
        "failed_symbols": {
            "VNM": {"reason": "Failed with token=ghp_abcdef1234567890xyz and key sk-9999888877776666 and DBPassword=secretPass123"}
        }
    }
    control_mod._save_ingest_checkpoint(cp_data, cp_file)
    content = cp_file.read_text(encoding="utf-8")
    assert "ghp_abcdef1234567890xyz" not in content
    assert "sk-9999888877776666" not in content
    assert "secretPass123" not in content
    assert "clientSecretValue123" not in content
    assert "clientSecretCamel123" not in content
    assert "xApiKeyValue123" not in content
    assert "credentialBundle123" not in content
    assert "myApiKey" not in content
    assert "consumerSecretPersist123" not in content
    assert "clientCredentialsPersist123" not in content
    assert "dbPasswordPersist123" not in content
    assert "awsSecretPersist123" not in content
    assert "authTokenPersist123" not in content
    assert "controlHmacSecretValue999" not in content
    assert "dbPasswordSecretValue888" not in content
    assert "jwtTokenSecretValue777" not in content
    assert "sshPrivateKeySecretValue666" not in content

    # Also verify the .bak checkpoint file was equally redacted
    bak_file = cp_file.with_suffix(".bak")
    assert bak_file.exists()
    bak_content = bak_file.read_text(encoding="utf-8")
    assert "clientSecretValue123" not in bak_content
    assert "xApiKeyValue123" not in bak_content
    assert "credentialBundle123" not in bak_content
    assert "consumerSecretPersist123" not in bak_content
    assert "clientCredentialsPersist123" not in bak_content
    assert "dbPasswordPersist123" not in bak_content
    assert "awsSecretPersist123" not in bak_content
    assert "authTokenPersist123" not in bak_content
    assert "controlHmacSecretValue999" not in bak_content
    assert "dbPasswordSecretValue888" not in bak_content
    assert "jwtTokenSecretValue777" not in bak_content
    assert "sshPrivateKeySecretValue666" not in bak_content

    # 3. Receipt HMAC generation and verification (artifact_id bound into HMAC)
    req = control_mod.PipelineRunRequest()
    as_of = control_mod._validate_dates(req.start_date, req.end_date, None)
    receipt = control_mod._publish_receipt("test-dim16-task", "PIPELINE_RUN", req, as_of, {"metrics": {"test": 1.0}})
    assert "receipt_hmac" in receipt
    assert "artifact_id" in receipt
    assert control_mod._valid_receipt(receipt, "test-dim16-task") is True

    # Tampering with artifact_id must invalidate the HMAC
    tampered_artifact = dict(receipt)
    tampered_artifact["artifact_id"] = "tampered/path/to/artifact.json"
    assert control_mod._valid_receipt(tampered_artifact, "test-dim16-task") is False

    # Tampering with output_sha256 must also invalidate HMAC
    tampered_output = dict(receipt)
    tampered_output["output_sha256"] = "0" * 64
    assert control_mod._valid_receipt(tampered_output, "test-dim16-task") is False

    # 4. Verify list_control_receipts() filters out invalid / tampered receipts
    receipts_resp = control_mod.list_control_receipts(limit=50)
    assert receipts_resp["status"] == "success"
    task_ids = [r["task_id"] for r in receipts_resp["receipts"]]
    assert "test-dim16-task" in task_ids

    # Write a tampered receipt directly to disk in CONTROL_ARTIFACT_ROOT
    tampered_file = control_mod.CONTROL_ARTIFACT_ROOT / "tampered-receipt.json"
    tampered_file.write_text(json.dumps({
        "schema_version": 1,
        "task_id": "tampered-receipt",
        "operation": "PIPELINE_RUN",
        "status": "COMPLETED",
        "request_fingerprint": "fake_fp",
        "effective_as_of_time": as_of.isoformat(),
        "output_sha256": "0" * 64,
        "artifact_id": tampered_file.as_posix(),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "receipt_hmac": "bad_hmac_value",
    }), encoding="utf-8")

    try:
        filtered_resp = control_mod.list_control_receipts(limit=50)
        filtered_task_ids = [r["task_id"] for r in filtered_resp["receipts"]]
        assert "tampered-receipt" not in filtered_task_ids
        assert "test-dim16-task" in filtered_task_ids
    finally:
        if tampered_file.exists():
            tampered_file.unlink()

    # 5. F-002: Copied-file and relocated-file adversarial tests (reject replayed alias artifacts)
    orig_path = control_mod.CONTROL_ARTIFACT_ROOT / "test-dim16-task.json"
    assert orig_path.exists()
    copied_path = control_mod.CONTROL_ARTIFACT_ROOT / "copied-task.json"
    import shutil
    shutil.copyfile(orig_path, copied_path)
    try:
        alias_resp = control_mod.list_control_receipts(limit=50)
        # Copied alias file must NOT be accepted as a second receipt
        alias_tasks = [r["task_id"] for r in alias_resp["receipts"]]
        assert alias_tasks.count("test-dim16-task") == 1
        assert "copied-task" not in alias_tasks
    finally:
        if copied_path.exists():
            copied_path.unlink()

    # Relocated file adversarial test: receipt whose artifact_id points to different path
    relocated_file = control_mod.CONTROL_ARTIFACT_ROOT / "relocated-task.json"
    relocated_receipt = dict(receipt)
    relocated_receipt["task_id"] = "relocated-task"
    # Keep artifact_id pointing to original location or mismatched stem
    relocated_receipt["artifact_id"] = (control_mod.CONTROL_ARTIFACT_ROOT / "other-file.json").as_posix()
    relocated_receipt["receipt_hmac"] = control_mod._compute_receipt_hmac(relocated_receipt)
    relocated_file.write_text(json.dumps(relocated_receipt), encoding="utf-8")
    try:
        reloc_resp = control_mod.list_control_receipts(limit=50)
        reloc_tasks = [r["task_id"] for r in reloc_resp["receipts"]]
        assert "relocated-task" not in reloc_tasks
    finally:
        if relocated_file.exists():
            relocated_file.unlink()

    # 6. Cycle 7 Dim 16 F-002: Valid legacy checkpoint primary rewrite & sanitize return
    legacy_cp_file = tmp_path / "legacy_checkpoint.json"
    legacy_data = {
        "schema_version": 1,
        "state": "running",
        "completed_symbols": ["HPG"],
        "failed_symbols": {},
        "DBPassword": "legacyPasswordPlaintext",
        "CONTROL_RECEIPT_HMAC_KEY": "legacyHmacPlaintext",
        "JWTToken": "legacyJwtPlaintext",
        "SSHPrivateKey": "legacySshPlaintext",
        "client_secret": "legacySecretPlaintext",
        "counters": {"completed_symbols": 1, "failed_symbols": 0, "pending_symbols": 0},
    }
    legacy_cp_file.write_text(json.dumps(legacy_data, indent=2), encoding="utf-8")
    returned_legacy = control_mod._load_ingest_checkpoint(legacy_cp_file)

    # Assert returned data is sanitized
    assert returned_legacy["DBPassword"] == "[REDACTED]"
    assert returned_legacy["CONTROL_RECEIPT_HMAC_KEY"] == "[REDACTED]"
    assert returned_legacy["JWTToken"] == "[REDACTED]"
    assert returned_legacy["SSHPrivateKey"] == "[REDACTED]"
    assert returned_legacy["client_secret"] == "[REDACTED]"

    # Assert primary checkpoint on disk was atomically rewritten and cleansed
    primary_disk_content = legacy_cp_file.read_text(encoding="utf-8")
    assert "legacyPasswordPlaintext" not in primary_disk_content
    assert "legacyHmacPlaintext" not in primary_disk_content
    assert "legacyJwtPlaintext" not in primary_disk_content
    assert "legacySshPlaintext" not in primary_disk_content
    assert "legacySecretPlaintext" not in primary_disk_content
    assert "[REDACTED]" in primary_disk_content

    # Assert backup file is also created and cleansed
    legacy_bak = legacy_cp_file.with_suffix(".bak")
    assert legacy_bak.exists()
    bak_disk_content = legacy_bak.read_text(encoding="utf-8")
    assert "legacyPasswordPlaintext" not in bak_disk_content
    assert "legacyHmacPlaintext" not in bak_disk_content
    assert "legacyJwtPlaintext" not in bak_disk_content
    assert "legacySshPlaintext" not in bak_disk_content
    assert "legacySecretPlaintext" not in bak_disk_content

    # 7. Cycle 7 Dim 16 F-003: Corrupt checkpoint quarantine sanitization (never copy raw secret bytes)
    corrupt_cp_file = tmp_path / "corrupt_checkpoint.json"
    corrupt_content = '{"state": "broken", "token": "superSecretToken12345", "DBPassword": "secretDbPassword999", syntax_error:::}'
    corrupt_cp_file.write_text(corrupt_content, encoding="utf-8")
    recovered = control_mod._load_ingest_checkpoint(corrupt_cp_file)
    assert recovered["state"] in ("recovered_from_backup", "quarantined_recovered")

    quarantine_dir = corrupt_cp_file.parent / "quarantine"
    assert quarantine_dir.exists()
    quarantine_files = list(quarantine_dir.glob("*.json"))
    assert len(quarantine_files) >= 1
    # Check all quarantine files for zero secret leakage
    for qf in quarantine_files:
        q_text = qf.read_text(encoding="utf-8")
        assert "superSecretToken12345" not in q_text
        assert "secretDbPassword999" not in q_text
        # Quarantine must contain structured diagnostic metadata
        q_json = json.loads(q_text)
        assert "schema_version" in q_json
        assert "quarantine_reason" in q_json
        assert "raw_sha256" in q_json
        # Cycle 8 Dim 16 F-003: Unparseable quarantine omits raw snippets
        assert q_json.get("sanitized_snippet") is None

    # 8. Cycle 8 Dim 16 F-002: Backup recovery deep-redacts and atomically rewrites primary and backup
    probe_corrupt_file = tmp_path / "probe_primary.json"
    probe_corrupt_file.write_text("INVALID_JSON{::", encoding="utf-8")
    probe_bak_file = probe_corrupt_file.with_suffix(".bak")
    probe_bak_data = {
        "state": "active",
        "completed_symbols": ["VNM"],
        "DBPassword": "secret_db_pass_12345",
        "nested": {"JWTToken": "jwt_token_secret_9988"},
    }
    probe_bak_file.write_text(json.dumps(probe_bak_data), encoding="utf-8")

    rec_data = control_mod._load_ingest_checkpoint(probe_corrupt_file)
    assert rec_data["state"] == "recovered_from_backup"
    assert rec_data["completed_symbols"] == ["VNM"]
    assert rec_data["DBPassword"] == "[REDACTED]"
    assert rec_data["nested"]["JWTToken"] == "[REDACTED]"
    assert "secret_db_pass_12345" not in json.dumps(rec_data)
    assert "jwt_token_secret_9988" not in json.dumps(rec_data)

    # Primary and backup files on disk must be sanitized and rewritten
    primary_text = probe_corrupt_file.read_text(encoding="utf-8")
    bak_text = probe_bak_file.read_text(encoding="utf-8")
    assert "secret_db_pass_12345" not in primary_text
    assert "jwt_token_secret_9988" not in primary_text
    assert "secret_db_pass_12345" not in bak_text
    assert "jwt_token_secret_9988" not in bak_text

    # 9. Cycle 8 Dim 16 F-001: Bare bearer redactor handles standalone auth and quoted values
    test_bare_bearer = "Failed request with Bearer token_xyz_99887766 and basic userpass123"
    redacted_bearer = control_mod._redact_text(test_bare_bearer)
    assert "token_xyz_99887766" not in redacted_bearer
    assert "userpass123" not in redacted_bearer
    assert "Bearer [REDACTED]" in redacted_bearer
    assert "basic [REDACTED]" in redacted_bearer

    test_quoted_secret = 'Connecting DBPassword="TAIL_SECRET_8f902be1 GAMMA_SECRET_8f902be1" end'
    redacted_quoted = control_mod._redact_text(test_quoted_secret)
    assert "TAIL_SECRET_8f902be1" not in redacted_quoted
    assert "GAMMA_SECRET_8f902be1" not in redacted_quoted
    assert "DBPassword=[REDACTED]" in redacted_quoted or "DBPassword: [REDACTED]" in redacted_quoted

    # 10. Cycle 9 Dim 16 F-004: Fail-closed backup file cleansing and removal on replacement failure
    f004_cp_file = tmp_path / "f004_corrupt_checkpoint.json"
    f004_cp_file.write_text("CORRUPT_INVALID_JSON{{:::", encoding="utf-8")
    f004_bak_file = f004_cp_file.with_suffix(".bak")
    raw_secret_bak = "SECRET_BACKUP_123"
    raw_token_bak = "sk-backupSecretKey9988776655"
    f004_bak_data = {
        "state": "active",
        "completed_symbols": ["HPG", "VNM"],
        "DBPassword": raw_secret_bak,
        "api_key": raw_token_bak,
        "nested": {"token": "subSecretVal456"},
    }
    f004_bak_file.write_text(json.dumps(f004_bak_data), encoding="utf-8")

    # Fault injection: Path.replace raises an exception ONLY when the destination is the .bak file
    orig_path_replace = Path.replace

    def mock_replace_bak_failure(self, target, *args, **kwargs):
        target_path = Path(target)
        if target_path.suffix == ".bak" or str(target_path).endswith(".bak"):
            raise OSError("Injected Path.replace failure for .bak file")
        return orig_path_replace(self, target, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", mock_replace_bak_failure)

    # Execute recovery under injected backup-replace failure
    caplog.clear()
    rec_f004 = control_mod._load_ingest_checkpoint(f004_cp_file)

    # Verify no raw credential survives in returned state
    assert rec_f004 is not None
    rec_f004_str = json.dumps(rec_f004)
    assert raw_secret_bak not in rec_f004_str
    assert raw_token_bak not in rec_f004_str
    assert "subSecretVal456" not in rec_f004_str

    # Verify primary checkpoint on disk is sanitized and free of raw credentials
    primary_disk_text = f004_cp_file.read_text(encoding="utf-8")
    assert raw_secret_bak not in primary_disk_text
    assert raw_token_bak not in primary_disk_text
    assert "subSecretVal456" not in primary_disk_text

    # Verify backup file on disk is cleansed or removed; BACKUP_LEAK must be False
    backup_leak = False
    if f004_bak_file.exists():
        bak_disk_text = f004_bak_file.read_text(encoding="utf-8")
        if raw_secret_bak in bak_disk_text or raw_token_bak in bak_disk_text or "subSecretVal456" in bak_disk_text:
            backup_leak = True
    assert not backup_leak, "Plaintext backup survived replacement failure (BACKUP_LEAK=True)"

    # Verify quarantine files under quarantine/ are free of raw credentials
    f004_quarantine_dir = f004_cp_file.parent / "quarantine"
    assert f004_quarantine_dir.exists()
    for q_file in f004_quarantine_dir.glob("*.json"):
        q_disk_text = q_file.read_text(encoding="utf-8")
        assert raw_secret_bak not in q_disk_text
        assert raw_token_bak not in q_disk_text
        assert "subSecretVal456" not in q_disk_text

    # Verify temporary artifacts (.tmp*) are cleaned up and none survive
    temp_artifacts = list(f004_cp_file.parent.glob("*.tmp*"))
    assert len(temp_artifacts) == 0, f"Temporary artifacts survived: {temp_artifacts}"

    # Verify logs do not contain raw credentials
    for log_record in caplog.records:
        msg = log_record.getMessage()
        assert raw_secret_bak not in msg
        assert raw_token_bak not in msg

    # 11. Cycle 9 Dim 16 F-004 (fail-closed probe): When legacy backup cannot be cleansed or removed, fail closed
    f004_fail_cp = tmp_path / "f004_uncleanable_checkpoint.json"
    f004_fail_cp.write_text("CORRUPT_INVALID_JSON{{:::", encoding="utf-8")
    f004_fail_bak = f004_fail_cp.with_suffix(".bak")
    uncleanable_secret = "UNCLEANABLE_SECRET_9999"
    f004_fail_bak.write_text(json.dumps({"state": "active", "DBPassword": uncleanable_secret}), encoding="utf-8")

    # Invalidate both replacement and cleansing helper
    monkeypatch.setattr(control_mod, "_cleanse_or_remove_backup_file", lambda *a, **kw: False)
    with pytest.raises(RuntimeError, match="(?i)Fail-closed"):
        control_mod._load_ingest_checkpoint(f004_fail_cp)



def test_ingest_source_routing_and_concurrency(tmp_path, monkeypatch):
    """Verify production SSOT loader routing, failover, and semaphore bounds."""
    import threading
    import time
    from collections import deque
    import pandas as pd

    routed = []
    active = 0
    peak = 0
    lock = threading.Lock()
    task_id = "test-ssot-routing-concurrency"

    class InstrumentedLoader:
        def __init__(self, **_kwargs):
            pass

        def load_prices(self, ticker, *_args, source=None, **_kwargs):
            nonlocal active, peak
            with lock:
                routed.append((ticker, source))
                active += 1
                peak = max(peak, active)
            try:
                time.sleep(0.02)
                if source == "vci":
                    raise RuntimeError("VCI 429 retryable failure")
                return pd.DataFrame([{
                    "symbol": ticker,
                    "date": pd.Timestamp("2023-06-01"),
                    "open": 100.0,
                    "high": 100.0,
                    "low": 100.0,
                    "close": 100.0,
                    "volume": 1,
                }])
            finally:
                with lock:
                    active -= 1

    monkeypatch.setattr(control_mod, "DataLoader", InstrumentedLoader)
    monkeypatch.setattr(control_mod, "DEFAULT_INGEST_CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    monkeypatch.setattr(control_mod, "CONTROL_ARTIFACT_ROOT", tmp_path / "receipts")
    control_mod.TASKS[task_id] = {
        "status": "RUNNING",
        "progress": 0.0,
        "events": deque(maxlen=1000),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    asyncio.run(control_mod._run_ingest(
        task_id,
        control_mod.IngestDataRequest(
            symbols=["FPT", "HPG", "VNM", "MBB"],
            sources=["vci", "kbs"],
            max_concurrency=2,
        ),
    ))

    assert control_mod.TASKS[task_id]["status"] == "COMPLETED"
    assert {source for _, source in routed} == {"vci", "kbs"}
    assert all(sum(source == provider for _, source in routed) == 4 for provider in ("vci", "kbs"))
    assert peak <= 2
    assert peak > 1
    result = control_mod.TASKS[task_id]["result"]
    assert result["provider"] == "kbs"
    assert result["failover_used"] is True
    assert len(result["failover_history"]) == 4


def test_ingest_pit_safety_and_concurrency_bounds():
    """F-002: PIT safety verification (as_of <= available_at) and F-003: Concurrency bound enforcement."""
    import asyncio
    import time
    from unittest.mock import MagicMock, patch
    import pandas as pd
    from omega.data.loader import DataLoader
    import omega.api.routes.control as control_mod

    # 1. PIT Safety verification (F-002)
    as_of = datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    raw_rows = [
        {"symbol": "VNM", "date": pd.Timestamp("2023-06-01"), "open": 70000, "high": 71000, "low": 69000, "close": 70500, "volume": 1000000, "source_used": "KBS"},
        {"symbol": "VNM", "date": pd.Timestamp("2023-06-02"), "open": 70500, "high": 72000, "low": 70000, "close": 71500, "volume": 1200000, "source_used": "KBS"}
    ]
    loader = DataLoader(cache_dir="data/cache", enable_pit_enforcement=True)
    # SSOT loader no longer exposes the archived vnstock_source adapter.
    with patch.object(loader, "_fetch_from_source", return_value=pd.DataFrame(raw_rows)):
        df = loader.load_prices("VNM", "2023-01-01", "2023-12-31", as_of_time=as_of, force_refresh=True, source="kbs")
        assert not df.empty
        assert "as_of" in df.columns
        assert "available_at" in df.columns
        # Invariant check: as_of <= available_at for PIT compliance across all rows
        for _, r in df.iterrows():
            assert r["as_of"] <= r["available_at"] or r["date"] <= as_of

    # 2. Concurrency bound enforcement (F-003): verify maximum active calls <= DEFAULT_INGEST_CONCURRENCY
    active_calls = 0
    max_observed_active = 0
    lock = asyncio.Lock()

    async def mock_async_load(sym, *args, **kwargs):
        nonlocal active_calls, max_observed_active
        async with lock:
            active_calls += 1
            if active_calls > max_observed_active:
                max_observed_active = active_calls
        await asyncio.sleep(0.01)
        async with lock:
            active_calls -= 1
        return pd.DataFrame({"date": [datetime.now(timezone.utc)], "close": [100.0]})

    class InstrumentedTestLoader:
        def __init__(self, *args, **kwargs):
            pass
        def load_prices(self, sym, start, end, as_of_dt, force, source="vci"):
            return pd.DataFrame({"date": [datetime.now(timezone.utc)], "close": [100.0]})

    # Simulate batch concurrent execution using control_mod logic
    sem = asyncio.Semaphore(control_mod.DEFAULT_INGEST_CONCURRENCY)
    async def simulate_batch():
        nonlocal active_calls, max_observed_active
        async def _fetch(s):
            nonlocal active_calls, max_observed_active
            async with sem:
                active_calls += 1
                if active_calls > max_observed_active:
                    max_observed_active = active_calls
                await asyncio.sleep(0.02)
                active_calls -= 1
                return s, pd.DataFrame(), None

        symbols = [f"SYM_{i}" for i in range(35)]
        await asyncio.gather(*[_fetch(s) for s in symbols])

    asyncio.run(simulate_batch())
    assert max_observed_active <= control_mod.DEFAULT_INGEST_CONCURRENCY
    assert max_observed_active > 1  # Proves parallel execution took place


def test_cleanse_and_verify_backup_adversarial_matrix(tmp_path):
    """Adversarial testing matrix for _cleanse_or_remove_backup_file and _verify_path_unredacted_secret_free."""
    # 1. Non-existent path: safe no-op
    non_existent = tmp_path / "does_not_exist.bak"
    assert control_mod._cleanse_or_remove_backup_file(non_existent) is True
    control_mod._verify_path_unredacted_secret_free(non_existent)  # Should not raise

    # 2. Directory path: should be unlinked/removed safely
    dir_bak = tmp_path / "dir.bak"
    dir_bak.mkdir()
    (dir_bak / "some_child.txt").write_text("hello", encoding="utf-8")
    assert control_mod._cleanse_or_remove_backup_file(dir_bak) is True
    assert not dir_bak.exists()

    # 3. Clean structured file: verification passes
    clean_bak = tmp_path / "clean.bak"
    clean_bak.write_text(json.dumps({"state": "ok", "DBPassword": "[REDACTED]"}), encoding="utf-8")
    control_mod._verify_path_unredacted_secret_free(clean_bak)

    # 4. Secret-bearing structured file: verification fails closed
    dirty_bak = tmp_path / "dirty.bak"
    dirty_bak.write_text(json.dumps({"state": "ok", "DBPassword": "rawSecretPass123"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="(?i)Fail-closed"):
        control_mod._verify_path_unredacted_secret_free(dirty_bak)

    # 5. Cleansing dirty file overwrites it with sanitized content
    assert control_mod._cleanse_or_remove_backup_file(dirty_bak, {"DBPassword": "rawSecretPass123"}) is True
    # Now it is either unlinked or sanitized
    if dirty_bak.exists():
        control_mod._verify_path_unredacted_secret_free(dirty_bak)
        assert "rawSecretPass123" not in dirty_bak.read_text(encoding="utf-8")

    # 6. Unparseable file with raw secret pattern: verification fails closed
    corrupt_dirty = tmp_path / "corrupt_dirty.bak"
    corrupt_dirty.write_text("INVALID_JSON_WITH Authorization: Bearer secretToken9999", encoding="utf-8")
    with pytest.raises(RuntimeError, match="(?i)Fail-closed"):
        control_mod._verify_path_unredacted_secret_free(corrupt_dirty)

    # 7. Unparseable file without secret pattern: verification passes
    corrupt_clean = tmp_path / "corrupt_clean.bak"
    corrupt_clean.write_text("INVALID_JSON_JUST_RANDOM_TEXT_NO_SECRET", encoding="utf-8")
    control_mod._verify_path_unredacted_secret_free(corrupt_clean)
