"""Slice 12 execution read contracts: strict schemas, PIT, costs, settlement."""
import copy
import json
import string
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from omega.api.routes import execution

BASE = "/api/v1/execution"
READS = ["blotter", "timeline", "routing-diagnostics", "slippage-distribution", "settlement-timeline"]
CUTOFF = "2026-10-09T08:30:00Z"


def record(**changes):
    row = dict(order_id="o1", execution_ts="2026-10-05T03:00:00Z",
               recorded_at="2026-10-05T03:00:00Z", feature_ts="2026-10-05T02:00:00Z",
               available_at="2026-10-05T02:00:00Z", decision_ts="2026-10-05T02:30:00Z",
               symbol="VCB", side="BUY", quantity=100.0, intended_price=10000.0,
               executed_price=10100.0, execution_status="FILLED", arrival_price=10000.0,
               fee_vnd=1000.0, venue="HOSE")
    row.update(changes)
    return row


def telemetry():
    return dict(state="STOPPED", active=False, mode="SHADOW", initial_capital_vnd=1e9,
                cash_vnd=1e9, portfolio_equity_vnd=1e9, total_pnl_vnd=0.0, daily_pnl_vnd=0.0,
                realized_pnl_vnd=0.0, unrealized_pnl_vnd=0.0, uptime_seconds=0.0,
                last_heartbeat=None, processed_orders_count=0, active_orders_count=0,
                positions_count=0, positions={}, model_pnl={})


@pytest.fixture
def api(monkeypatch):
    class Engine:
        rows = []
        status = telemetry()

        def get_orders(self, limit):
            assert limit == 5000
            return self.rows

        def get_status(self):
            return self.status

    engine = Engine()
    app = FastAPI()
    app.include_router(execution.router)
    app.dependency_overrides[execution.job_service_dependency] = lambda: None
    monkeypatch.setattr(execution, "_get_engine", lambda: engine)
    with TestClient(app) as client:
        yield client, engine


@pytest.mark.parametrize("endpoint", READS)
def test_empty_schemas(api, endpoint):
    client, _ = api
    response = client.get(f"{BASE}/{endpoint}")
    assert response.status_code == 200, response.text
    assert response.json()["effective_cutoff"]
    assert response.json()["price_unit"] == "VND_FULL"


def test_openapi_strict_models(api):
    client, _ = api
    schema = client.get("/openapi.json").json()
    for endpoint in READS + ["status"]:
        result = schema["paths"][f"{BASE}/{endpoint}"]["get"]["responses"]["200"]
        name = result["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
        assert schema["components"]["schemas"][name]["additionalProperties"] is False
    with pytest.raises(ValidationError):
        execution.ExecutionRecord.model_validate(record(extra_field=1))


@pytest.mark.parametrize("endpoint", READS)
@pytest.mark.parametrize("field,value", [
    ("quantity", None), ("quantity", "100"), ("quantity", []), ("quantity", True),
    ("quantity", -1), ("quantity", 1e13), ("quantity", float("nan")),
    ("executed_price", float("inf")), ("fee_vnd", float("-inf")),
    ("arrival_price", 0), ("arrival_price", -10), ("arrival_price", 10),
    ("execution_ts", "2026-10-05T03:00:00"), ("side", "UNKNOWN"),
    ("symbol", "--shell"), ("price_unit", "VND_THOUSAND"),
    ("quantity", {}), ("execution_status", "NEW_STATE"),
    ("recorded_at", "2026-10-05T02:00:00Z"),
    ("available_at", "2026-10-05T02:45:00Z"),
])
def test_invalid_records_fail_closed(api, endpoint, field, value):
    client, engine = api
    engine.rows = [record(**{field: value})]
    response = client.get(f"{BASE}/{endpoint}")
    assert response.status_code == 424, response.text
    assert response.json()["detail"] == "EXECUTION_DATA_INVALID"


@pytest.mark.parametrize("endpoint", READS)
def test_pit_inclusive_availability_and_future_exclusion(api, endpoint):
    client, engine = api
    engine.rows = [record(recorded_at=CUTOFF), record(order_id="future", recorded_at="2026-10-09T08:30:00.000001Z")]
    result = client.get(f"{BASE}/{endpoint}", params={"as_of": CUTOFF})
    assert result.status_code == 200, result.text
    assert "future" not in result.text
    assert result.json()["provenance"] == "RECORDED"
    engine.rows[0].pop("recorded_at")
    assert client.get(f"{BASE}/{endpoint}", params={"as_of": CUTOFF}).status_code == 424
    live = client.get(f"{BASE}/{endpoint}")
    assert live.status_code == 200
    assert live.json()["provenance"] == "LIVE_UNVERIFIED"


@pytest.mark.parametrize("cutoff", ["", "bad", "2026-10-09", "2026-10-09T03:00:00", "2999-01-01T00:00:00Z"])
@pytest.mark.parametrize("endpoint", READS)
def test_invalid_cutoff(api, endpoint, cutoff):
    client, _ = api
    assert client.get(f"{BASE}/{endpoint}", params={"as_of": cutoff}).status_code == 422


def test_blotter_status_and_limit(api):
    client, engine = api
    engine.rows = [record(execution_status="REJECTED_PIT_LOOKAHEAD", executed_price=0),
                   record(order_id="cancel", execution_status="CANCELLED", executed_price=0,
                          execution_ts="2026-10-05T03:01:00Z", recorded_at="2026-10-05T03:01:00Z")]
    result = client.get(f"{BASE}/blotter", params={"limit": 1}).json()
    assert result["orders"][0]["status"] == "CANCELLED"
    assert result["orders"][0]["filledQty"] == 0
    assert client.get(f"{BASE}/blotter", params={"limit": 0}).status_code == 422
    assert client.get(f"{BASE}/blotter", params={"limit": 5001}).status_code == 422
    assert client.get(f"{BASE}/routing-diagnostics").json()["routers"][0]["rejection_rate_pct"] == 50


def family(algo="TWAP"):
    return [record(order_id="parent", quantity=200.0, execution_status="PENDING", executed_price=0, algo_type=algo),
            record(order_id="child1", parent_order_id="parent", sequence=0, algo_type=algo),
            record(order_id="child2", parent_order_id="parent", sequence=1, algo_type=algo,
                   execution_status="PENDING", executed_price=0)]


@pytest.mark.parametrize("algo", ["TWAP", "VWAP"])
def test_timeline_parent_child_progress_and_no_double_count(api, algo):
    client, engine = api
    engine.rows = family(algo)
    result = client.get(f"{BASE}/timeline").json()
    parent = result["parents"][0]
    assert parent["target_qty"] == 200
    assert parent["filled_qty"] == 100
    assert parent["completion_pct"] == 50
    assert parent["sequence_complete"] is True
    assert result["standalone"] == []
    assert len(client.get(f"{BASE}/slippage-distribution").json()["points"]) == 1
    routing = client.get(f"{BASE}/routing-diagnostics").json()
    assert routing["total_active_orders"] == 1
    assert routing["total_active_slices"] == 1


@pytest.mark.parametrize("change", ["orphan", "nested", "duplicate", "sequence", "overflow", "side"])
def test_invalid_families(api, change):
    client, engine = api
    engine.rows = family()
    if change == "orphan":
        engine.rows.pop(0)
    elif change == "nested":
        engine.rows[2]["parent_order_id"] = "child1"
    elif change == "duplicate":
        engine.rows[2]["order_id"] = "child1"
    elif change == "sequence":
        engine.rows[2]["sequence"] = 0
    elif change == "overflow":
        engine.rows[0]["quantity"] = 100.0
    else:
        engine.rows[1]["side"] = "SELL"
    assert client.get(f"{BASE}/timeline").status_code == 424


def test_zero_targets_partial_fills_and_sequence_gap(api):
    client, engine = api
    engine.rows = family()
    engine.rows[2]["sequence"] = 3
    engine.rows[1].update(execution_status="PARTIALLY_FILLED", filled_quantity=50.0)
    parent = client.get(f"{BASE}/timeline").json()["parents"][0]
    assert parent["filled_qty"] == 50
    assert parent["sequence_complete"] is False
    engine.rows = [record(order_id="p", quantity=0.0, execution_status="PENDING", executed_price=0),
                   record(order_id="c", parent_order_id="p", sequence=0, quantity=0.0,
                          execution_status="PENDING", executed_price=0)]
    assert client.get(f"{BASE}/timeline").json()["parents"][0]["completion_pct"] is None


def test_slippage_sign_fees_and_weighted_venues(api):
    client, engine = api
    engine.rows = [record(), record(order_id="sell", side="SELL", executed_price=9900.0, quantity=200.0)]
    result = client.get(f"{BASE}/slippage-distribution").json()
    assert [p["slippage_bps"] for p in result["points"]] == pytest.approx([110, 105])
    assert result["venues"][0]["average_slippage_bps"] == pytest.approx(320 / 3)
    engine.rows[1]["executed_price"] = 10100.0
    assert client.get(f"{BASE}/slippage-distribution").json()["points"][1]["slippage_bps"] == pytest.approx(-95)
    engine.rows[0].pop("fee_vnd")
    engine.rows[0]["total_cost_vnd"] = 1000.0
    result = client.get(f"{BASE}/slippage-distribution").json()
    assert result["excluded_missing_benchmark_or_fee"] == 1


def test_slippage_notional_overflow(api):
    client, engine = api
    engine.rows = [record(quantity=1e8, arrival_price=1e8)]
    assert client.get(f"{BASE}/slippage-distribution").status_code == 424


def test_settlement_forecast_holidays_and_unconfirmed_cash(api):
    client, engine = api
    engine.rows = [record(execution_ts="2026-04-29T03:00:00Z", recorded_at="2026-04-29T03:00:00Z",
                          feature_ts=None, available_at=None, decision_ts=None,
                          cash_available_vnd=999999.0, shares_available=100.0)]
    result = client.get(f"{BASE}/settlement-timeline").json()["settlements"][0]
    assert result["expected_settlement_at"] == "2026-05-05T08:30:00Z"
    assert "2026-04-30" in result["skipped_closed_dates"]
    assert "2026-05-01" in result["skipped_closed_dates"]
    assert result["confirmed"] is False
    assert result["cash_available_vnd"] is None
    assert result["shares_available"] is None


def test_settlement_confirmation_cutoff_and_close(api):
    client, engine = api
    engine.rows = [record(broker_effective_at="2026-10-07T08:30:00Z",
                          settlement_effective_at="2026-10-07T08:30:00Z",
                          confirmation_available_at=CUTOFF, cash_available_vnd=0.0, shares_available=100.0)]
    result = client.get(f"{BASE}/settlement-timeline", params={"as_of": CUTOFF}).json()["settlements"][0]
    assert result["confirmed"] is True
    assert result["shares_available"] == 100
    response = client.get(f"{BASE}/settlement-timeline", params={"as_of": "2026-10-09T08:29:59Z"})
    assert response.json()["settlements"][0]["confirmed"] is False
    engine.rows[0]["settlement_effective_at"] = "2026-10-07T08:29:59Z"
    assert client.get(f"{BASE}/settlement-timeline").status_code == 424


@pytest.mark.parametrize("changes", [
    {"broker_effective_at": None}, {"shares_available": 101.0}, {"cash_available_vnd": 100.0},
    {"settlement_effective_at": "2026-10-10T08:30:00Z"},
])
def test_invalid_confirmation(api, changes):
    client, engine = api
    engine.rows = [record(broker_effective_at="2026-10-07T08:30:00Z",
                          settlement_effective_at="2026-10-07T08:30:00Z",
                          confirmation_available_at=CUTOFF, cash_available_vnd=0.0, shares_available=100.0)]
    engine.rows[0].update(changes)
    assert client.get(f"{BASE}/settlement-timeline").status_code == 424


def test_snapshot_bounds_failure_redaction_and_no_mutation(api, monkeypatch):
    client, engine = api
    engine.rows = [record()]
    original = copy.deepcopy(engine.rows)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.get(f"{BASE}/timeline").status_code, range(8)))
    assert responses == [200] * 8
    assert engine.rows == original
    engine.rows = [record(order_id=f"o{i}") for i in range(5001)]
    assert client.get(f"{BASE}/timeline").status_code == 424
    engine.rows = [record(reject_reason="x" * (1024 * 1024))]
    assert client.get(f"{BASE}/timeline").status_code == 424

    def failed(limit):
        raise OSError("https://user:secret@example.com/private")

    monkeypatch.setattr(engine, "get_orders", failed)
    response = client.get(f"{BASE}/blotter")
    assert response.status_code == 424
    assert "secret" not in response.text


@pytest.mark.parametrize("endpoint", READS)
@pytest.mark.parametrize("text", ["x", "\x00", "€", "\U0001f600"])
def test_snapshot_byte_budget_stops_before_serialization(api, monkeypatch, endpoint, text):
    client, engine = api

    class Unvisited(dict):
        def items(self):
            pytest.fail("snapshot traversed beyond exhausted byte budget")

    row = record(reject_reason=text * 2048)
    engine.rows = [row] * 4998 + [Unvisited(row)]
    oversized = engine.rows
    original_dumps = execution.json.dumps
    original_copy = execution.copy.deepcopy

    def dumps(value, *args, **kwargs):
        assert value is not oversized, "oversized snapshot serialized"
        return original_dumps(value, *args, **kwargs)

    def deepcopy(value, *args, **kwargs):
        assert value is not oversized, "oversized snapshot copied"
        return original_copy(value, *args, **kwargs)

    monkeypatch.setattr(execution.json, "dumps", dumps)
    monkeypatch.setattr(execution.copy, "deepcopy", deepcopy)
    response = client.get(f"{BASE}/{endpoint}")
    assert response.status_code == 424
    assert response.json()["detail"] == "EXECUTION_DATA_INVALID"
    assert engine.rows[0] is row
    engine.rows = [record()]
    assert client.get(f"{BASE}/{endpoint}").status_code == 200


@pytest.mark.parametrize("field", ["mode", "positions", "model_pnl"])
@pytest.mark.parametrize("text", ["x", "\x00", "€", "\U0001f600"])
def test_status_byte_budget_stops_before_serialization(api, monkeypatch, field, text):
    client, engine = api
    large = text * (1024 * 1024 + 1)
    engine.status[field] = large if field == "mode" else {large: 0.0}
    oversized = engine.status
    original_dumps = execution.json.dumps
    original_copy = execution.copy.deepcopy

    def dumps(value, *args, **kwargs):
        assert value is not oversized, "oversized status serialized"
        return original_dumps(value, *args, **kwargs)

    def deepcopy(value, *args, **kwargs):
        assert value is not oversized, "oversized status copied"
        return original_copy(value, *args, **kwargs)

    monkeypatch.setattr(execution.json, "dumps", dumps)
    monkeypatch.setattr(execution.copy, "deepcopy", deepcopy)
    response = client.get(f"{BASE}/status")
    assert response.status_code == 424
    assert response.json()["detail"] == "EXECUTION_STATUS_INVALID"
    assert engine.status[field] == (large if field == "mode" else {large: 0.0})
    engine.status = telemetry()
    assert client.get(f"{BASE}/status").status_code == 200


@pytest.mark.parametrize("field", ["positions", "model_pnl"])
def test_status_aggregate_byte_budget_stops_early(api, monkeypatch, field):
    client, engine = api

    class Unvisited(dict):
        def items(self):
            pytest.fail("status traversed beyond exhausted byte budget")

    large = "\U0001f600" * 2048
    engine.status[field] = {f"k{i}": large for i in range(4999)}
    engine.status[field]["last"] = Unvisited()
    oversized = engine.status
    original_dumps = execution.json.dumps

    def dumps(value, *args, **kwargs):
        assert value is not oversized, "oversized aggregate status serialized"
        return original_dumps(value, *args, **kwargs)

    monkeypatch.setattr(execution.json, "dumps", dumps)
    response = client.get(f"{BASE}/status")
    assert response.status_code == 424
    assert response.json()["detail"] == "EXECUTION_STATUS_INVALID"


@pytest.mark.parametrize("value", [None, True, False, 0, -1, 1e12, 1.5, "", "\"\\\\\b\f\n\r\t\x00\x1f\x7f€\U0001f600\ud800",
                                   [], {}, [None, True, False], {"x": [{"y": "z"}]}])
def test_json_budget_exact_boundary(value):
    size = len(execution.json.dumps(value, allow_nan=False, ensure_ascii=True))
    assert execution._json_budget(value, size) == 0
    with pytest.raises(ValueError):
        execution._json_budget(value, size - 1)


@pytest.mark.parametrize("text", ["x", "\x00", "€", "\U0001f600"])
def test_json_budget_one_mib_boundary(text):
    limit = 1024 * 1024
    width = len(execution.json.dumps(text)) - 2
    value = text * ((limit - 2) // width) + "x" * ((limit - 2) % width)
    assert execution._json_budget(value, limit) == 0
    with pytest.raises(ValueError):
        execution._json_budget(value + "x", limit)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), {1: "x"}, object(), pytest.param(1 << (4 * 1024 * 1024), id="oversized_integer"), [[[[[[[[[[[0]]]]]]]]]]]])
def test_json_budget_invalid_values(value):
    with pytest.raises(ValueError):
        execution._json_budget(value, 1024 * 1024)


@pytest.mark.parametrize("field,value", [("cash_vnd", float("nan")), ("total_pnl_vnd", float("inf")),
                                         ("uptime_seconds", -1), ("cash_vnd", "100"),
                                         ("initial_capital_vnd", 1e13), ("positions_count", 1)])
def test_status_finite_and_consistent(api, field, value):
    client, engine = api
    engine.status[field] = value
    assert client.get(f"{BASE}/status").status_code == 424


def test_status_valid_and_worker_unavailable(api):
    client, engine = api
    engine.status["mode"] = "LIVE_PAPER"
    result = client.get(f"{BASE}/status")
    assert result.status_code == 200, result.text
    assert result.json()["workers_available"] is False
    assert "workers" not in engine.status


@pytest.mark.parametrize("endpoint", READS + ["status"])
def test_query_schema_rejects_extras_and_replay(api, endpoint):
    client, _ = api
    assert client.get(f"{BASE}/{endpoint}", params={"unknown": "x"}).status_code == 422
    assert client.get(f"{BASE}/{endpoint}?as_of={CUTOFF}&as_of={CUTOFF}").status_code == 422


@pytest.mark.parametrize("count", [5000, 5001])
def test_snapshot_cap_never_claims_complete(api, count):
    client, engine = api
    engine.rows = [record(order_id=f"o{i}") for i in range(count)]
    assert client.get(f"{BASE}/routing-diagnostics").status_code == 424


def test_worker_failure_and_valid_worker(api):
    client, engine = api
    original = copy.deepcopy(engine.status)

    class Service:
        def list_active_workers(self, timeout_seconds):
            assert timeout_seconds == 60
            return [dict(worker_id="worker1", hostname="host", pid=1, status="ACTIVE",
                         started_at="2026-10-05T00:00:00Z", last_heartbeat=CUTOFF,
                         metadata={"token": "not-published"})]

    client.app.dependency_overrides[execution.job_service_dependency] = Service
    response = client.get(f"{BASE}/status")
    assert response.status_code == 200, response.text
    assert response.json()["workers_available"] is True
    assert response.json()["active_workers"] == 1
    assert "not-published" not in response.text
    assert engine.status == original

    class FailedService:
        def list_active_workers(self, timeout_seconds):
            raise TimeoutError("provider unavailable")

    client.app.dependency_overrides[execution.job_service_dependency] = FailedService
    response = client.get(f"{BASE}/status")
    assert response.status_code == 200
    assert response.json()["workers_available"] is False


def test_closed_trade_and_missing_calendar_fail_closed(api, monkeypatch):
    client, engine = api
    engine.rows = [record(execution_ts="2026-10-04T03:00:00Z", recorded_at="2026-10-04T03:00:00Z",
                          feature_ts=None, available_at=None, decision_ts=None)]
    assert client.get(f"{BASE}/settlement-timeline").status_code == 424
    engine.rows = [record()]

    def missing_calendar(value):
        raise ValueError("missing year coverage")

    monkeypatch.setattr(execution.VNTradingCalendar, "is_trading_day", missing_calendar)
    assert client.get(f"{BASE}/settlement-timeline").status_code == 424


def test_rejection_does_not_inherit_pit_claims(api):
    client, engine = api
    engine.rows = [record(execution_status="REJECTED_PIT_LOOKAHEAD", executed_price=0,
                          feature_ts="2027-01-01T00:00:00Z", available_at="2027-01-01T00:00:00Z")]
    item = client.get(f"{BASE}/blotter").json()["orders"][0]
    assert item["status"] == "REJECTED"
    assert item["availableAt"] == "2026-10-05T03:00:00Z"
    assert "2027" not in str(item)


@pytest.fixture
def real_api(monkeypatch, tmp_path):
    from omega.quant.execution import paper_trading

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 9, 8, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(paper_trading, "datetime", Clock)
    engine = paper_trading.PaperTradingEngine(log_dir=str(tmp_path))
    monkeypatch.setattr(execution, "_get_engine", lambda: engine)
    app = FastAPI()
    app.include_router(execution.router)
    app.dependency_overrides[execution.job_service_dependency] = lambda: None
    with TestClient(app) as client:
        assert client.post(f"{BASE}/start", json={}).status_code == 200
        order = dict(symbol="VCB", side="BUY", size=100.0, price=10000.0,
                     feature_ts=CUTOFF, decision_ts=CUTOFF, available_at=CUTOFF)
        response = client.post(f"{BASE}/orders", json=order)
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "FILLED"
        yield client, engine, order


def engine_snapshot(engine):
    from pathlib import Path

    return copy.deepcopy(dict(status=engine.get_status(), orders=engine.orders_history,
                              daily_pnl=engine.daily_pnl, realized_pnl=engine.realized_pnl,
                              started_at=engine.started_at, heartbeat=engine.last_heartbeat,
                              files={path.name: path.read_bytes()
                                     for path in Path(engine.log_dir).iterdir() if path.is_file()}))


@pytest.mark.parametrize("state", ["STOPPED", "RUNNING", "PAUSED"])
@pytest.mark.parametrize("endpoint,field,cap", [("start", "mode", 32), ("orders", "model_id", 64)])
def test_invalid_identifiers_leave_real_engine_unchanged(real_api, monkeypatch, state, endpoint, field, cap):
    client, engine, order = real_api
    if state != "RUNNING":
        action = "stop" if state == "STOPPED" else "pause"
        assert client.post(f"{BASE}/{action}").status_code == 200
    before = engine_snapshot(engine)
    calls = []

    def get_engine():
        calls.append(True)
        return engine

    monkeypatch.setattr(execution, "_get_engine", get_engine)
    invalid = [None, True, 0, -1, 1e13, float("nan"), float("inf"), float("-inf"), [], {}, "", "x" * (cap + 1)]
    invalid += [f"a{chr(code)}b" for code in range(128)
                if chr(code) not in string.ascii_letters + string.digits + "_.:-"]
    invalid += [" valid", "valid ", "valid\n", "valid\r\n", "café", "模型", "Ａ", " ", "​", "😀"]
    for value in invalid:
        payload = {field: value} if endpoint == "start" else {**order, field: value}
        calls.clear()
        response = client.post(f"{BASE}/{endpoint}", content=json.dumps(payload),
                               headers={"Content-Type": "application/json"})
        assert response.status_code == 422, (field, repr(value), response.text)
        assert response.json()["detail"] == "INVALID_REQUEST"
        assert calls == [], "invalid identifier reached the engine"
        assert engine_snapshot(engine) == before, (field, repr(value))
        assert client.get(f"{BASE}/status").status_code == 200
        for read in READS:
            assert client.get(f"{BASE}/{read}").status_code == 200


@pytest.mark.parametrize("mode,model_id", [("a", "z"), ("aZ09_.:-", "aZ09_.:-"), ("m" * 32, "v" * 64)])
def test_valid_identifier_boundaries_round_trip_real_engine(real_api, mode, model_id):
    client, engine, order = real_api
    assert client.post(f"{BASE}/stop").status_code == 200
    response = client.post(f"{BASE}/start", json={"mode": mode})
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == mode.upper()
    response = client.post(f"{BASE}/orders", json={**order, "model_id": model_id})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "FILLED"
    assert response.json()["executions"][0]["model_id"] == model_id
    assert model_id in engine.daily_pnl
    assert client.get(f"{BASE}/status").json()["mode"] == mode.upper()
    for read in READS:
        assert client.get(f"{BASE}/{read}").status_code == 200


@pytest.mark.parametrize("state", ["STOPPED", "RUNNING", "PAUSED"])
@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("order_book_data", [None, {"ref_price": 20000.0, "exchange_label": "HOSE"}],
                         ids=["direct", "price-band"])
def test_invalid_symbols_leave_real_engine_unchanged(real_api, monkeypatch, state, side, order_book_data):
    client, engine, order = real_api
    if state != "RUNNING":
        action = "stop" if state == "STOPPED" else "pause"
        assert client.post(f"{BASE}/{action}").status_code == 200
    before = engine_snapshot(engine)
    calls = []

    def get_engine():
        calls.append(True)
        return engine

    monkeypatch.setattr(execution, "_get_engine", get_engine)
    invalid = [None, True, 0, -1, 1e13, float("nan"), float("inf"), float("-inf"), [], {},
               "", " ", "a" * 17, "界", "café", "Ａ", "١", "²", "😀", "​",
               "ß" * 9, "ß" * 16, "a" * 15 + "ß", "a\nB", "a\rB"]
    invalid += [f"a{chr(code)}b" for code in range(128)
                if chr(code) not in string.ascii_letters + string.digits]
    for symbol in invalid:
        calls.clear()
        response = client.post(f"{BASE}/orders", content=json.dumps(
            {**order, "symbol": symbol, "side": side, "order_book_data": order_book_data}),
            headers={"Content-Type": "application/json"})
        assert response.status_code == 422, (repr(symbol), response.text)
        assert response.json() == {"detail": "INVALID_REQUEST"}
        assert calls == [], "invalid symbol reached engine lookup"
        assert engine_snapshot(engine) == before, repr(symbol)
    assert client.get(f"{BASE}/status").status_code == 200
    for read in READS:
        assert client.get(f"{BASE}/{read}").status_code == 200


@pytest.mark.parametrize("symbol", ["vCb", " vcb ", "a", "0", "aZ09" * 4, "ß" * 8])
def test_normalized_symbol_boundaries_round_trip_real_engine(real_api, symbol):
    client, engine, order = real_api
    response = client.post(f"{BASE}/orders", json={**order, "symbol": symbol, "size": 200.0})
    assert response.status_code == 201, response.text
    normalized = symbol.strip().upper()
    assert response.json()["symbol"] == normalized
    assert response.json()["executions"]
    assert all(row["symbol"] == normalized for row in response.json()["executions"])
    assert engine.get_orders(limit=1)[0]["symbol"] == normalized
    for read in READS:
        assert client.get(f"{BASE}/{read}").status_code == 200


@pytest.mark.parametrize("availability", ["omitted", "null", "explicit"])
@pytest.mark.parametrize("branch", [
    "fill", "stopped", "paused", "short_sell", "calendar", "delisted",
    "price_band", "append_failure", "snapshot_failure", "rollback_failure",
])
def test_optional_availability_round_trip_real_engine(real_api, monkeypatch, availability, branch):
    client, engine, order = real_api
    payload = {**order, "symbol": " vcb ", "size": 200.0}
    if availability == "omitted":
        payload.pop("available_at")
    elif availability == "null":
        payload["available_at"] = None
    expected = "FILLED"
    if branch in {"stopped", "paused"}:
        assert client.post(f"{BASE}/{'stop' if branch == 'stopped' else 'pause'}").status_code == 200
        expected = f"REJECTED_DAEMON_{branch.upper()}"
    elif branch == "short_sell":
        payload.update(side="SELL", size=200.0)
        expected = "REJECTED_SHORT_SELL_PROHIBITED"
    elif branch == "calendar":
        payload.update(feature_ts="2026-10-04T03:00:00Z", decision_ts="2026-10-04T03:00:00Z")
        if availability == "explicit":
            payload["available_at"] = payload["feature_ts"]
        expected = "REJECTED_TRADING_CALENDAR"
    elif branch == "delisted":
        payload["symbol"] = " ros "
        expected = "REJECTED_DELISTED_SYMBOL"
    elif branch == "price_band":
        payload["order_book_data"] = {"ref_price": 10000.0, "is_suspended": True}
        expected = "REJECTED_PRICE_BAND"
    before = engine_snapshot(engine)
    if branch in {"append_failure", "snapshot_failure", "rollback_failure"}:
        def fail(*args, **kwargs):
            raise OSError("injected durability failure")

        monkeypatch.setattr(engine, "_log_virtual_order" if branch == "append_failure" else "_save_daemon_state", fail)
        if branch == "rollback_failure":
            monkeypatch.setattr(engine, "_rollback_virtual_order", fail)
        expected = "REJECTED_DURABILITY_FAILURE"
    execute = engine.execute_virtual_order
    handoffs = []

    def capture(order_payload, **kwargs):
        handoffs.append(copy.deepcopy(order_payload))
        return execute(order_payload, **kwargs)

    monkeypatch.setattr(engine, "execute_virtual_order", capture)
    response = client.post(f"{BASE}/orders", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == expected, response.text
    assert handoffs[0]["available_at"] == payload["feature_ts"]
    row = response.json()["executions"][0]
    execution.ExecutionRecord.model_validate(row)
    if branch not in {"append_failure", "snapshot_failure", "rollback_failure"}:
        assert row["available_at"] == payload["feature_ts"]
        assert row["symbol"] == payload["symbol"].strip().upper()
        assert engine.get_orders(limit=1)[0] == row
    else:
        after = engine_snapshot(engine)
        for key in ("orders", "daily_pnl", "realized_pnl"):
            assert after[key] == before[key]
        for key in ("cash_vnd", "positions", "portfolio_equity_vnd"):
            assert after["status"][key] == before["status"][key]
        if branch != "rollback_failure":
            assert after["files"] == before["files"]
    for endpoint in READS:
        result = client.get(f"{BASE}/{endpoint}")
        assert result.status_code == 200, (endpoint, result.text)
        assert result.json()["provenance"] == "LIVE_UNVERIFIED"
    if branch == "fill":
        from omega.quant.execution.paper_trading import PaperTradingEngine

        restarted = PaperTradingEngine(log_dir=engine.log_dir)
        assert restarted.rehydrate_from_log() >= 1
        monkeypatch.setattr(execution, "_get_engine", lambda: restarted)
        assert all(row["available_at"] == order["feature_ts"] for row in restarted.get_orders())
        for endpoint in READS:
            assert client.get(f"{BASE}/{endpoint}").status_code == 200


@pytest.mark.parametrize("availability", ["omitted", "null", "explicit"])
def test_optional_availability_concurrent_real_engine(real_api, availability):
    client, engine, order = real_api
    payload = dict(order)
    if availability == "omitted":
        payload.pop("available_at")
    elif availability == "null":
        payload["available_at"] = None
    assert client.post(f"{BASE}/stop").status_code == 200
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda index: client.post(f"{BASE}/orders", json={**payload, "size": 200.0 + index}), range(8)))
    assert all(response.status_code == 201 for response in responses)
    assert len(engine.get_orders()) == 9
    assert all(row["available_at"] == order["feature_ts"] for row in engine.get_orders())
    for endpoint in READS:
        assert client.get(f"{BASE}/{endpoint}").status_code == 200


@pytest.mark.parametrize("timestamp", ["2026-10-09T08:30:00Z", "2026-10-09T15:30:00+07:00"])
@pytest.mark.parametrize("availability", ["omitted", "null", "explicit"])
def test_optional_availability_model_boundary(timestamp, availability):
    payload = dict(symbol=" vcb ", side="BUY", size=100.0, price=10000.0,
                   feature_ts=timestamp, decision_ts=timestamp)
    if availability != "omitted":
        payload["available_at"] = None if availability == "null" else timestamp
    model = execution.PaperOrderRequest.model_validate(payload)
    assert model.available_at == timestamp
    assert model.model_dump()["available_at"] == timestamp
    assert payload.get("available_at") == (timestamp if availability == "explicit" else None)
    assert model.symbol == "VCB"
    explicit = {**payload, "feature_ts": "2026-10-09T08:00:00Z", "available_at": timestamp}
    assert execution.PaperOrderRequest.model_validate(explicit).available_at == timestamp


@pytest.mark.parametrize("field", ["available_at", "symbol"])
def test_optional_availability_invalid_inputs_do_not_mutate_real_engine(real_api, field):
    client, engine, order = real_api
    before = engine_snapshot(engine)
    values = [True, 0, -1, 1e13, float("nan"), float("inf"), float("-inf"), [], {}, "", " ", "None"]
    if field == "symbol":
        values = [None, *[value for value in values if value != "None"], "VCB​", "VCB\x00", "a" * 17]
    else:
        values += ["2026-10-09T08:29:59Z", "2026-10-09T08:30:00.000001Z", "2026-10-09T08:30:00"]
    for value in values:
        payload = {**order, "available_at": None, field: value}
        response = client.post(f"{BASE}/orders", content=json.dumps(payload), headers={"Content-Type": "application/json"})
        assert response.status_code == 422, (field, repr(value), response.text)
        assert response.json() == {"detail": "INVALID_REQUEST"}
        assert engine_snapshot(engine) == before
    for endpoint in READS:
        assert client.get(f"{BASE}/{endpoint}").status_code == 200


def test_real_server_mount():
    from omega.api.server import app
    paths = {route.path for route in app.routes}
    assert {f"{BASE}/{endpoint}" for endpoint in READS + ["status"]} <= paths
