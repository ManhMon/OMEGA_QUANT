"""Tests for Market Station and Microstructure API contracts."""

import asyncio
import copy
import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from threading import BoundedSemaphore, Event
from time import monotonic

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from omega.api.routes import market

CUTOFF = "2026-10-07T08:30:00Z"
BASE = "/api/v1/market"


@pytest.fixture
def history():
    return pd.DataFrame(
        {
            "ticker": ["FPT", "FPT"],
            "date": ["2026-10-06", "2026-10-07"],
            "open": [50000.0, 50000.0],
            "high": [51000.0, 51000.0],
            "low": [49000.0, 49000.0],
            "close": [51000.0, 49000.0],
            "volume": [1000.0, 1000.0],
            "exchange": ["HOSE", "HOSE"],
            "source": ["fixture", "fixture"],
            "price_scale": ["VND_FULL", "VND_FULL"],
            "as_of": ["2026-10-06T08:30:00Z", CUTOFF],
            "available_at": ["2026-10-06T08:30:00Z", CUTOFF],
        }
    )


@pytest.fixture
def client(monkeypatch, history):
    app = FastAPI()
    app.include_router(market.router)
    monkeypatch.setattr(
        market._market_loader,
        "load_market_dataset",
        lambda **kwargs: history.copy(deep=True),
    )
    return TestClient(app)


def snapshot():
    return {
        "symbol": "FPT",
        "venue": "HOSE",
        "source": "fixture",
        "price_scale": "VND_FULL",
        "as_of": CUTOFF,
        "available_at": CUTOFF,
        "sequence": 8,
        "previous_sequence": 7,
        "bids": [
            {"price": 49900.0, "volume": 300.0},
            {"price": 49800.0, "volume": 100.0},
        ],
        "asks": [{"price": 50100.0, "volume": 100.0}],
    }


def depth(client, **kwargs):
    return client.get(f"{BASE}/orderbook-depth/FPT", params={"as_of": CUTOFF, **kwargs})


def impact_body(**kwargs):
    return {
        "symbol": "FPT",
        "order_size": 1000.0,
        "average_daily_volume": 100000.0,
        "arrival_price": 50000.0,
        "as_of": CUTOFF,
        **kwargs,
    }


@pytest.mark.parametrize("alias", ["vpin", "vpin-toxicity"])
def test_vpin_equal_volume_alias_contract(client, alias):
    response = client.get(
        f"{BASE}/{alias}/FPT", params={"as_of": CUTOFF, "n_buckets": 5}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["bucket_volume"] == 400.0
    assert data["vpin"] == pytest.approx(0.8)
    assert data["ofi"] == 0.0
    assert data["n_buckets"] == len(data["history"]) == 5
    assert [
        point["buy_volume"] + point["sell_volume"] for point in data["history"]
    ] == [400.0] * 5
    assert data["metadata"]["source_kind"] == "estimated"
    assert data["metadata"]["calibration"] == "uncalibrated"
    assert data["classification"] == "close_location_ohlcv_proxy"
    assert data["provenance"]["max_included_available_at"] == "2026-10-07T08:30:00Z"


def test_vpin_incomplete_bucket_and_flat_classification(client, history):
    history["close"] = 50000.0
    result = client.get(
        f"{BASE}/vpin/FPT",
        params={"as_of": CUTOFF, "n_buckets": 5, "bucket_volume": 600},
    ).json()
    assert result["discarded_volume"] == 200.0
    assert result["n_buckets"] == 3
    assert result["vpin"] == result["ofi"] == 0
    history["high"] = history["low"] = history["open"] = history["close"]
    assert client.get(f"{BASE}/vpin/FPT", params={"as_of": CUTOFF}).json()["vpin"] == 0


@pytest.mark.parametrize("volume", [0.0, 1e12])
def test_vpin_zero_and_total_overflow_fail_closed(client, history, volume):
    history["volume"] = volume
    response = client.get(f"{BASE}/vpin/FPT", params={"as_of": CUTOFF})
    assert response.status_code == 424


@pytest.mark.parametrize("size", [0, -1, "nan", "inf", "-inf", 1e13, 1e-300, 3000])
def test_vpin_bucket_bounds(client, size):
    assert (
        client.get(
            f"{BASE}/vpin/FPT", params={"as_of": CUTOFF, "bucket_volume": size}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "buy,sell,expected",
    [(0, 0, None), (5, 0, 1), (0, 5, -1), (1e12, 1e12, 0), (300, 100, 0.5)],
)
def test_normalized_ofi(buy, sell, expected):
    actual = market._normalized_imbalance(buy, sell)
    assert actual is None if expected is None else actual == pytest.approx(expected)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), -float("inf"), 1e13])
def test_normalized_ofi_invalid(value):
    with pytest.raises(HTTPException) as caught:
        market._normalized_imbalance(value, 100)
    assert caught.value.status_code == 424


def test_real_depth_source_missing_and_explicit_estimate(client):
    assert depth(client).status_code == 424
    data = depth(client, mode="estimated", depth=3).json()
    assert data["is_synthetic"] is True
    assert data["metadata"]["source_kind"] == "estimated"
    assert data["sequence"] is data["depth_age_seconds"] is None
    assert data["freshness"] == "not_live_estimate"
    assert data["bids"][-1]["cumulative_volume"] == sum(
        item["volume"] for item in data["bids"]
    )
    assert data["bids"][0]["price"] > data["bids"][-1]["price"]
    assert data["asks"][0]["price"] < data["asks"][-1]["price"]


def test_observed_depth_sequence_freshness_sparse_levels_and_ofi(client):
    client.app.state.market_depth_provider = lambda **kwargs: snapshot()
    response = depth(client, depth=10)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["bids"]) == 2 and len(data["asks"]) == 1
    assert data["depth_levels"] == 2
    assert data["total_bid_depth"] == 400.0 and data["total_ask_depth"] == 100.0
    assert data["ofi"] == pytest.approx(0.6)
    assert data["sequence_integrity"] == "contiguous"
    assert data["depth_age_seconds"] == 0
    assert data["metadata"]["source_kind"] == "observed"
    assert data["is_synthetic"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "gap",
        "duplicate",
        "reorder",
        "crossed",
        "future",
        "stale",
        "symbol",
        "empty",
        "extra",
        "naive",
        "missing",
        "overflow",
        "zero",
        "nan",
        "partial",
    ],
)
def test_real_depth_fault_injection(client, fault):
    data = snapshot()
    if fault == "gap":
        data["previous_sequence"] = 1
    elif fault == "duplicate":
        data["bids"].append(data["bids"][0].copy())
    elif fault == "reorder":
        data["bids"].reverse()
    elif fault == "crossed":
        data["asks"][0]["price"] = 49000.0
    elif fault == "future":
        data["available_at"] = "2026-10-07T08:30:00.000001Z"
    elif fault == "stale":
        data["as_of"] = "2026-10-07T08:29:29Z"
    elif fault == "symbol":
        data["symbol"] = "HPG"
    elif fault == "empty":
        data["asks"] = []
    elif fault == "extra":
        data["unexpected"] = 1
    elif fault == "naive":
        data["as_of"] = "2026-10-07T08:30:00"
    elif fault == "missing":
        del data["sequence"]
    elif fault == "overflow":
        data["bids"][0]["volume"] = 1e13
    elif fault == "zero":
        data["bids"][0]["price"] = 0.0
    elif fault == "nan":
        data["asks"][0]["volume"] = float("nan")
    elif fault == "partial":
        data["bids"] = None
    client.app.state.market_depth_provider = lambda **kwargs: data
    assert depth(client).status_code == 424


def test_zero_depth_is_unknown_not_neutral(client):
    data = snapshot()
    for level in data["bids"] + data["asks"]:
        level["volume"] = 0.0
    client.app.state.market_depth_provider = lambda **kwargs: data
    result = depth(client).json()
    assert result["ofi"] is result["obi"] is None
    assert result["ofi_status"] == "unavailable_zero_volume"


@pytest.mark.parametrize("route", ["vpin", "vpin-toxicity", "orderbook-depth"])
@pytest.mark.parametrize(
    "value", [None, "bad", float("nan"), float("inf"), -float("inf"), -1.0, 1e13]
)
def test_history_numeric_faults_all_routes(client, history, route, value):
    history["close"] = value
    response = client.get(
        f"{BASE}/{route}/FPT", params={"as_of": CUTOFF, "mode": "estimated"}
    )
    assert response.status_code == 424
    assert client.post(f"{BASE}/market-impact", json=impact_body()).status_code == 424


@pytest.mark.parametrize(
    "fault",
    [
        "schema",
        "scale",
        "venue",
        "duplicate",
        "date",
        "naive",
        "pit",
        "before_close",
        "holiday",
        "weekend",
        "empty",
        "symbol",
    ],
)
def test_history_schema_calendar_pit_faults(client, history, fault):
    if fault == "schema":
        history.drop(columns="volume", inplace=True)
    elif fault == "scale":
        history["price_scale"] = "VND_THOUSAND"
    elif fault == "venue":
        history["exchange"] = "UNKNOWN"
    elif fault == "duplicate":
        history.loc[1, "date"] = history.loc[0, "date"]
    elif fault == "date":
        history["date"] = None
    elif fault == "naive":
        history["as_of"] = "2026-10-07T08:30:00"
    elif fault == "pit":
        history.loc[1, "as_of"] = "2026-10-07T08:31:00Z"
    elif fault == "before_close":
        history.loc[1, "as_of"] = "2026-10-07T08:29:59Z"
    elif fault == "holiday":
        history.loc[1, "date"] = "2026-09-02"
    elif fault == "weekend":
        history.loc[1, "date"] = "2026-10-04"
    elif fault == "empty":
        history.drop(history.index, inplace=True)
    elif fault == "symbol":
        history["ticker"] = "DELISTED"
    expected = 404 if fault in {"empty", "symbol"} else 424
    assert (
        client.get(f"{BASE}/vpin/FPT", params={"as_of": CUTOFF}).status_code == expected
    )


def test_pit_inclusive_close_ict_and_future_rows(client, history):
    first = client.get(
        f"{BASE}/vpin/FPT", params={"as_of": "2026-10-07T15:30:00+07:00"}
    )
    assert first.status_code == 200, first.text
    history.loc[1, "available_at"] = "2026-10-07T08:30:00.000001Z"
    history.loc[1, "close"] = float("inf")
    result = client.get(f"{BASE}/vpin/FPT", params={"as_of": CUTOFF})
    assert result.status_code == 200
    assert result.json()["window_bars"] == 1
    assert result.json()["vpin"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    "cutoff", ["2026-10-07T08:30:00", "2099-10-07T08:30:00Z", "bad"]
)
def test_bad_cutoff_all_routes(client, cutoff):
    for route in ("vpin", "vpin-toxicity", "orderbook-depth"):
        assert (
            client.get(f"{BASE}/{route}/FPT", params={"as_of": cutoff}).status_code
            == 422
        )
    assert (
        client.post(f"{BASE}/market-impact", json=impact_body(as_of=cutoff)).status_code
        == 422
    )


@pytest.mark.parametrize("side,sign", [("BUY", 1), ("SELL", -1)])
def test_impact_sizes_fees_sign_and_unverified_parameters(client, side, sign):
    response = client.post(
        f"{BASE}/market-impact", json=impact_body(side=side, fee_bps=10.0)
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["point_signed_price_move_bps"] == sign * data["point_impact_bps"]
    assert data["point_total_cost_bps"] == data["point_impact_bps"] + 10
    assert data["point_cost_vnd"] == pytest.approx(
        1000 * 50000 * data["point_total_cost_bps"] / 10000
    )
    assert [point["order_size"] for point in data["curve"]] == [
        100,
        250,
        500,
        750,
        1000,
    ]
    assert [point["impact_bps"] for point in data["curve"]] == sorted(
        point["impact_bps"] for point in data["curve"]
    )
    assert data["provenance"] is None
    assert data["caller_parameters_verified"] is False
    assert data["kyle_lambda"] is data["amihud_illiquidity"] is None
    assert data["history_provenance"]["is_synthetic"] is False
    assert data["metadata"]["source_kind"] == "estimated"


@pytest.mark.parametrize(
    "field",
    [
        "order_size",
        "average_daily_volume",
        "arrival_price",
        "volatility",
        "participation_rate",
        "impact_coefficient",
    ],
)
@pytest.mark.parametrize(
    "value",
    [
        None,
        "1",
        [],
        True,
        0,
        -1,
        1e13,
        1e308,
        float("nan"),
        float("inf"),
        -float("inf"),
    ],
)
def test_impact_strict_numeric_contract(client, field, value):
    response = client.post(
        f"{BASE}/market-impact",
        content=json.dumps(impact_body(**{field: value})),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "patch",
    [
        {"order_sizes": []},
        {"order_sizes": [100.0, 100.0]},
        {"order_sizes": [200.0, 100.0]},
        {"order_sizes": [float("nan")]},
        {"order_sizes": [100.0] * 51},
        {"order_size": 100001.0},
        {"side": "HOLD"},
        {"fee_bps": -1.0},
        {"extra": 1},
        {"arrival_price": 1e12},
        {"order_sizes": [1e13]},
    ],
)
def test_impact_scenario_bounds(client, patch):
    assert (
        client.post(
            f"{BASE}/market-impact",
            content=json.dumps(impact_body(**patch)),
            headers={"Content-Type": "application/json"},
        ).status_code
        == 422
    )


def test_provider_timeout_redacts_and_does_not_fallback(client, monkeypatch):
    def fail(**kwargs):
        raise TimeoutError("https://user:secret@example.com?token=secret")

    monkeypatch.setattr(market._market_loader, "load_market_dataset", fail)
    client.app.state.market_depth_provider = fail
    for response in (
        depth(client),
        depth(client, mode="estimated"),
        client.get(f"{BASE}/vpin/FPT"),
        client.post(f"{BASE}/market-impact", json=impact_body()),
    ):
        assert response.status_code == 424
        assert "secret" not in response.text


@pytest.mark.parametrize("route", ["real", "estimated", "vpin", "vpin-toxicity", "impact"])
@pytest.mark.parametrize("outcome", ["late_result", "late_error"])
def test_slow_provider_deadline_and_no_fallback(client, monkeypatch, history, route, outcome):
    release, entered = Event(), Event()
    workers = []
    thread = market.Thread
    slots = BoundedSemaphore(4)
    monkeypatch.setattr(market, "_MICRO_IO_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(market, "_MICRO_IO_SLOTS", slots)

    def track(**kwargs):
        worker = thread(**kwargs)
        workers.append(worker)
        return worker

    def slow(**kwargs):
        entered.set()
        assert release.wait(2)
        if outcome == "late_error":
            raise RuntimeError("https://user:secret@example.com?token=secret")
        return snapshot() if route == "real" else history.copy(deep=True)

    monkeypatch.setattr(market, "Thread", track)
    monkeypatch.setattr(market._market_loader, "load_market_dataset", slow)
    client.app.state.market_depth_provider = slow
    try:
        start = monotonic()
        if route in {"real", "estimated"}:
            response = depth(client, mode=route, max_age_seconds=0.001)
        elif route == "impact":
            response = client.post(f"{BASE}/market-impact", json=impact_body())
        else:
            response = client.get(f"{BASE}/{route}/FPT", params={"as_of": CUTOFF})
        assert entered.is_set()
        assert monotonic() - start < 0.5
        expected = (
            "REAL_L2_SNAPSHOT_INVALID_OR_UNAVAILABLE"
            if route == "real" else "MICROSTRUCTURE_HISTORY_INVALID_OR_UNAVAILABLE"
        )
        assert response.status_code == 424
        assert response.json() == {"detail": expected}
        assert len(workers) == 1  # No retry or synthetic fallback.
    finally:
        release.set()
        for worker in workers:
            worker.join(2)
            assert not worker.is_alive()
    for _ in range(4):
        assert slots.acquire(blocking=False)
    assert not slots.acquire(blocking=False)


def test_hung_provider_capacity_shared_and_recovered(client, monkeypatch, history):
    release = Event()
    workers = []
    thread = market.Thread
    slots = BoundedSemaphore(4)
    monkeypatch.setattr(market, "_MICRO_IO_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(market, "_MICRO_IO_SLOTS", slots)

    def track(**kwargs):
        worker = thread(**kwargs)
        workers.append(worker)
        return worker

    def blocked(**kwargs):
        assert release.wait(3)
        return snapshot()

    monkeypatch.setattr(market, "Thread", track)
    client.app.state.market_depth_provider = blocked
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda _: depth(client), range(4)))
        assert all(response.status_code == 424 for response in responses)
        assert len(workers) == 4
        assert all(worker.is_alive() and worker.daemon for worker in workers)
        for _ in range(8):
            assert depth(client).status_code == 424
            assert depth(client, mode="estimated").status_code == 424
            assert client.get(f"{BASE}/vpin/FPT").status_code == 424
            assert client.post(f"{BASE}/market-impact", json=impact_body()).status_code == 424
        assert len(workers) == 4  # Timed-out workers keep their slots; no queue.
        assert not slots.acquire(blocking=False)
    finally:
        release.set()
        for worker in workers:
            worker.join(2)
            assert not worker.is_alive()
    monkeypatch.setattr(market, "_MICRO_IO_TIMEOUT_SECONDS", 1.0)
    client.app.state.market_depth_provider = lambda **kwargs: snapshot()
    assert depth(client).status_code == 200
    assert depth(client, mode="estimated").status_code == 200
    assert client.get(f"{BASE}/vpin/FPT", params={"as_of": CUTOFF}).status_code == 200


@pytest.mark.parametrize("route", ["real", "estimated", "vpin", "vpin-toxicity", "impact"])
@pytest.mark.parametrize("fault", ["future", "constructor", "start"])
def test_provider_setup_failure_preserves_capacity(client, monkeypatch, history, route, fault):
    slots = BoundedSemaphore(4)
    calls, workers = [], []
    thread = market.Thread
    monkeypatch.setattr(market, "_MICRO_IO_SLOTS", slots)

    def provider(**kwargs):
        calls.append(kwargs)
        return snapshot() if route == "real" else history.copy(deep=True)

    def track(**kwargs):
        worker = thread(**kwargs)
        workers.append(worker)
        return worker

    def fail():
        raise MemoryError("https://user:secret@example.com?token=secret")

    class BrokenThread:
        def __init__(self, **kwargs):
            if fault == "constructor":
                fail()

        def start(self):
            fail()

    def request():
        if route in {"real", "estimated"}:
            return depth(client, mode=route)
        if route == "impact":
            return client.post(f"{BASE}/market-impact", json=impact_body())
        return client.get(f"{BASE}/{route}/FPT", params={"as_of": CUTOFF})

    monkeypatch.setattr(market, "Thread", track)
    monkeypatch.setattr(market._market_loader, "load_market_dataset", provider)
    client.app.state.market_depth_provider = provider
    with monkeypatch.context() as injected:
        injected.setattr(market, "Future" if fault == "future" else "Thread",
                         fail if fault == "future" else BrokenThread)
        response = request()
    expected = (
        "REAL_L2_SNAPSHOT_INVALID_OR_UNAVAILABLE"
        if route == "real" else "MICROSTRUCTURE_HISTORY_INVALID_OR_UNAVAILABLE"
    )
    assert response.status_code == 424
    assert response.json() == {"detail": expected}
    assert calls == workers == []
    for _ in range(4):
        assert slots.acquire(blocking=False)
    assert not slots.acquire(blocking=False)
    for _ in range(4):
        slots.release()
    assert request().status_code == 200
    for worker in workers:
        worker.join(2)
        assert not worker.is_alive()
    assert len(calls) == len(workers) == 1
    for _ in range(4):
        assert slots.acquire(blocking=False)
    assert not slots.acquire(blocking=False)
    for _ in range(4):
        slots.release()


@pytest.mark.parametrize("fallback", [None, "false", "0", "true", "1", "", "nan", "inf", "-inf", "[]"])
def test_legacy_orderbook_requires_explicit_fallback(client, monkeypatch, history, fallback):
    calls = []

    def provider(**kwargs):
        calls.append(kwargs)
        if fallback not in {"true", "1"}:
            raise AssertionError("default/invalid fallback must not access history")
        return history.copy(deep=True)

    monkeypatch.setattr(market._market_loader, "load_market_dataset", provider)
    params = {"as_of": CUTOFF}
    if fallback is not None:
        params["fallback"] = fallback
    response = client.get(f"{BASE}/orderbook/FPT", params=params)
    if fallback in {"true", "1"}:
        assert response.status_code == 200, response.text
        assert response.json()["is_synthetic"] is True
        assert len(calls) == 1
    elif fallback in {None, "false", "0"}:
        assert response.status_code == 503
        assert response.json() == {"detail": "REAL_L2_FEED_UNAVAILABLE"}
        assert calls == []
    else:
        assert response.status_code == 422
        assert calls == []


@pytest.mark.parametrize("fault", ["timeout", "malformed", "empty"])
def test_legacy_explicit_fallback_failure_stays_closed(client, monkeypatch, fault):
    calls = []

    def provider(**kwargs):
        calls.append(kwargs)
        if fault == "timeout":
            raise TimeoutError("https://user:secret@example.com?token=secret")
        return pd.DataFrame() if fault == "empty" else None

    monkeypatch.setattr(market._market_loader, "load_market_dataset", provider)
    response = client.get(f"{BASE}/orderbook/FPT", params={"fallback": "true", "as_of": CUTOFF})
    assert response.status_code == 503
    assert response.json()["detail"] in {"MARKET_DATA_UNAVAILABLE", "MARKET_DATASET_PIT_INVALID"}
    assert "secret" not in response.text
    assert len(calls) == 1


@pytest.mark.parametrize("fallback", [None, "false", "true"])
@pytest.mark.parametrize("params", [
    {"depth": 0}, {"depth": -1}, {"depth": 1e13}, {"depth": "nan"},
    {"depth": "inf"}, {"depth": "-inf"}, {"depth": ""}, {"as_of": "malformed"},
    {"as_of": "2026-10-07T08:30:00"}, {"as_of": "2099-10-07T08:30:00Z"},
])
def test_legacy_orderbook_invalid_query_never_loads_history(client, monkeypatch, params, fallback):
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise AssertionError("invalid query must not access history")

    monkeypatch.setattr(market._market_loader, "load_market_dataset", fail)
    query = {**params, **({"fallback": fallback} if fallback is not None else {})}
    assert client.get(f"{BASE}/orderbook/FPT", params=query).status_code == 422
    assert calls == []


def test_provider_late_completed_value_is_rejected(monkeypatch):
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(market, "_MICRO_IO_SLOTS", slots)
    times = iter([0.0, 0.5, 1.0])
    monkeypatch.setattr(market, "monotonic", lambda: next(times))

    class ImmediateThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(market, "Thread", ImmediateThread)
    with pytest.raises(TimeoutError):
        market._micro_provider_call(lambda: snapshot())
    assert slots.acquire(blocking=False)


def test_restored_authentic_resilience_fixture_binding():
    path = Path(".ly_state/session/anti_drip_contract_l2_role15_vci_ingestion_resilience_20260911.json")
    raw = path.read_bytes()
    expected = "555f3eebe6590a0786b1b0d36b3850931969098086575e7c49b1cde8a3464a50"
    assert hashlib.sha256(raw).hexdigest() == expected
    contract = json.loads(raw)
    assert contract["session_id"] == "l2_role15_vci_ingestion_resilience_20260911"
    assert contract["gate_name"] == "CANONICAL_VCI_INGESTION_RESILIENCE_20260911"
    assert contract["mode"] == "remediation"
    assert {finding["finding_id"] for finding in contract["required_findings"]} == {
        "F-001", "F-002", "F-003", "F-004"
    }
    with pytest.raises(AssertionError):
        assert hashlib.sha256(raw + b" ").hexdigest() == expected
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw[:-2])


def test_read_only_concurrency_and_snapshot_isolation(client, history):
    original = history.copy(deep=True)
    supplied = snapshot()
    before = copy.deepcopy(supplied)
    client.app.state.market_depth_provider = lambda **kwargs: supplied
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: depth(client).json(), range(8)))
    assert all(result == results[0] for result in results)
    pd.testing.assert_frame_equal(history, original)
    assert supplied == before


def test_hash_binds_all_selected_rows(client, history):
    first = client.get(f"{BASE}/vpin/FPT", params={"as_of": CUTOFF}).json()[
        "provenance"
    ]["content_hash"]
    history.loc[0, "open"] = 50500.0
    second = client.get(f"{BASE}/vpin/FPT", params={"as_of": CUTOFF}).json()[
        "provenance"
    ]["content_hash"]
    assert first != second


@pytest.mark.parametrize(
    "route,params",
    [
        ("vpin", {"limit": 1001}),
        ("vpin", {"n_buckets": 101}),
        ("vpin", {"n_buckets": 0}),
        ("orderbook-depth", {"depth": 21}),
        ("orderbook-depth", {"depth": 0}),
        ("orderbook-depth", {"spread_bps": "nan"}),
        ("orderbook-depth", {"max_age_seconds": "inf"}),
        ("orderbook-depth", {"mode": "fake"}),
    ],
)
def test_query_resource_bounds(client, route, params):
    assert client.get(f"{BASE}/{route}/FPT", params=params).status_code == 422


@pytest.mark.parametrize("symbol", ["--flag", "DROP;TABLE", "FPT-", "A" * 33])
def test_symbol_allowlist(client, symbol):
    for route in ("vpin", "vpin-toxicity", "orderbook-depth"):
        assert client.get(f"{BASE}/{route}/{symbol}").status_code == 422
    assert (
        client.post(f"{BASE}/market-impact", json=impact_body(symbol=symbol)).status_code
        == 422
    )


@pytest.mark.parametrize(
    "symbol", ["NONEXISTENT_TICKER_999", "DELISTED_TEST_ZZZ", "FPT_", "A" * 32]
)
def test_valid_missing_symbols_reach_history(client, symbol):
    for route in ("vpin", "vpin-toxicity", "orderbook-depth"):
        response = client.get(
            f"{BASE}/{route}/{symbol}",
            params={"as_of": CUTOFF, "mode": "estimated"},
        )
        assert response.status_code == 404, response.text
    assert (
        client.post(f"{BASE}/market-impact", json=impact_body(symbol=symbol)).status_code
        == 404
    )


@pytest.mark.parametrize("symbol", ["FPT_", "A_" + "A" * 30])
def test_extended_symbols_round_trip_all_microstructure_dtos(client, history, symbol):
    history["ticker"] = symbol
    for route in ("vpin", "vpin-toxicity", "orderbook-depth"):
        response = client.get(
            f"{BASE}/{route}/{symbol}",
            params={"as_of": CUTOFF, "mode": "estimated"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["symbol"] == symbol
    response = client.post(f"{BASE}/market-impact", json=impact_body(symbol=symbol))
    assert response.status_code == 200, response.text
    assert response.json()["symbol"] == symbol
    supplied = {**snapshot(), "symbol": symbol}
    client.app.state.market_depth_provider = lambda **kwargs: supplied
    response = client.get(f"{BASE}/orderbook-depth/{symbol}", params={"as_of": CUTOFF})
    assert response.status_code == 200, response.text
    assert response.json()["symbol"] == symbol


@pytest.mark.parametrize("fault", ["directory", "encoding", "429"])
def test_history_io_and_rate_limit_failures(client, monkeypatch, fault):
    errors = {
        "directory": IsADirectoryError("dataset"),
        "encoding": UnicodeError("invalid UTF-8 BOM CRLF"),
        "429": RuntimeError("429 https://user:secret@example.com"),
    }

    def fail(**kwargs):
        raise errors[fault]

    monkeypatch.setattr(market._market_loader, "load_market_dataset", fail)
    assert client.get(f"{BASE}/vpin/FPT").status_code == 424
    assert depth(client, mode="estimated").status_code == 424
    assert client.post(f"{BASE}/market-impact", json=impact_body()).status_code == 424


@pytest.mark.parametrize(
    "route",
    ["get_market_ohlcv", "get_market_orderbook", "get_chart_station_data",
     "get_vpin_toxicity", "get_orderbook_depth_waterfall"],
)
def test_direct_routes_omitted_cutoff(client, route):
    handler = getattr(market, route)
    kwargs = {
        name: parameter.default.default
        for name, parameter in inspect.signature(handler).parameters.items()
        if name != "as_of" and hasattr(parameter.default, "default")
    }
    kwargs.update(symbol="FPT")
    if route == "get_market_orderbook":
        kwargs["fallback"] = True
    if route == "get_orderbook_depth_waterfall":
        kwargs.update(request=market.Request({"type": "http", "app": client.app}), mode="estimated")
    result = handler(**kwargs)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    data = result if isinstance(result, dict) else result.model_dump()
    assert data["ticker" if route == "get_chart_station_data" else "symbol"] == "FPT"
    if "is_synthetic" in data:
        assert data["is_synthetic"] is True


@pytest.mark.parametrize("route,status", [("get_chart_station_data", 503),
                                        ("get_vpin_toxicity", 424),
                                        ("get_orderbook_depth_waterfall", 424)])
def test_direct_routes_omitted_cutoff_provider_failure(client, monkeypatch, route, status):
    def fail(**kwargs):
        raise RuntimeError("https://user:secret@example.com?token=secret")

    monkeypatch.setattr(market._market_loader, "load_market_dataset", fail)
    handler = getattr(market, route)
    kwargs = {"symbol": "FPT"}
    if route == "get_orderbook_depth_waterfall":
        kwargs.update(request=market.Request({"type": "http", "app": client.app}), mode="estimated")
    with pytest.raises(HTTPException) as error:
        result = handler(**kwargs)
        if inspect.isawaitable(result):
            asyncio.run(result)
    assert error.value.status_code == status
    assert "secret" not in error.value.detail
    assert "example.com" not in error.value.detail


@pytest.mark.parametrize("route", ["get_market_ohlcv", "get_market_orderbook",
                                  "get_chart_station_data", "get_vpin_toxicity",
                                  "get_orderbook_depth_waterfall"])
@pytest.mark.parametrize("cutoff", [None, CUTOFF, "2026-10-07T15:30:00+07:00",
                                   "2026-10-07T08:30:00", "2099-10-07T08:30:00Z"])
def test_pit_query_defaults_preserve_cutoff_validation(route, cutoff):
    query = copy.copy(inspect.signature(getattr(market, route)).parameters["as_of"].default)
    query.default = None if cutoff is None else datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    if cutoff in {"2026-10-07T08:30:00", "2099-10-07T08:30:00Z"}:
        with pytest.raises(HTTPException) as error:
            market._pit_cutoff(query)
        assert error.value.status_code == 422
    elif cutoff is None:
        before = pd.Timestamp.now(tz="UTC")
        assert before <= market._pit_cutoff(query) <= pd.Timestamp.now(tz="UTC")
    else:
        assert market._pit_cutoff(query) == pd.Timestamp(CUTOFF)


def test_vpin_adversarial_allocation_conservation(history):
    import random

    rng = random.Random(9)
    for _ in range(100):
        frame = history.copy()
        frame["date"] = pd.to_datetime(frame["date"], utc=True)
        frame["volume"] = [rng.uniform(1, 10000) for _ in range(2)]
        frame["close"] = [rng.uniform(49000, 51000) for _ in range(2)]
        result = market._vpin_buckets(frame, 5, None)
        assert 0 <= result["vpin"] <= 1
        assert -1 <= result["ofi"] <= 1
        assert sum(
            point["buy_volume"] + point["sell_volume"] for point in result["history"]
        ) + result["discarded_volume"] == pytest.approx(frame["volume"].sum())


def test_snapshot_inclusive_freshness_and_future_observation(client):
    supplied = snapshot()
    supplied["as_of"] = "2026-10-07T08:29:30Z"
    client.app.state.market_depth_provider = lambda **kwargs: supplied
    assert depth(client).status_code == 200
    assert depth(client, max_age_seconds=29).status_code == 424
    supplied["as_of"] = supplied["available_at"] = "2026-10-07T08:30:00.000001Z"
    assert depth(client).status_code == 424


def test_strict_response_models_and_metadata():
    with pytest.raises(ValidationError):
        market.DepthSnapshot.model_validate({**snapshot(), "sequence": "8"})
    with pytest.raises(ValidationError):
        market.MicrostructureMetadata(
            source_kind="observed",
            as_of=datetime(2026, 10, 7, 9, tzinfo=timezone.utc),
            available_at=CUTOFF,
            effective_cutoff=CUTOFF,
            method="fixture",
        )
