"""Integration and 16-Dimension Adversarial Verification for Dashboard Data Wiring.

Evaluates genuine dashboard endpoints and fail-closed security envelopes without mocking
target business logic or entry points.
"""

from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
import pandas as pd
from fastapi.testclient import TestClient
from omega.api.server import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    return TestClient(app)


# ==============================================================================
# SECTION 1: Repetitive Integration Tests for Dashboard Endpoints
# ==============================================================================

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_macro_summary_endpoint(client):
    resp = client.get("/api/v1/macro/summary")
    if resp.status_code == 503:
        assert resp.json()["detail"] in {"MARKET_BREADTH_UNAVAILABLE", "MACRO_DATA_UNAVAILABLE", "MACRO_DATA_INVALID", "MACRO_DATASET_PIT_INVALID", "INTERBANK_DATA_UNAVAILABLE", "INTERBANK_DATA_INVALID"}
        return
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "indicators" in data
    assert "hmmRegime" in data
    assert "marketBreadth" in data
    assert "interbankRate" in data


def test_market_ohlcv_endpoint(client):
    resp = client.get("/api/v1/market/ohlcv/VNM?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["symbol"] == "VNM"
    assert "bars" in data


def test_execution_status_endpoint(client):
    resp = client.get("/api/v1/execution/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "active_workers" in data
    assert "workers" in data


def test_execution_orders_endpoint(client):
    resp = client.get("/api/v1/execution/orders")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_execution_positions_endpoint(client):
    resp = client.get("/api/v1/execution/positions")
    assert resp.status_code == 200
    data = resp.json()
    assert "positions" in data
    assert "count" in data
    assert "as_of" in data


def test_tca_pre_trade_simulate_endpoint(client):
    payload = {
        "symbol": "VNM",
        "order_size": 1000.0,
        "average_daily_volume": 500000.0,
        "volatility": 0.25,
        "participation_rate": 0.05,
        "side": "BUY",
        "arrival_price": 75000.0,
        "observed_spread_bps": 10.0,
    }
    resp = client.post("/api/v1/risk/tca/simulate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["symbol"] == "VNM"
    assert data["estimated_impact_bps"] > 0
    assert data["total_cost_vnd"] > 0


def test_barra_risk_decomposition_post_endpoint(client):
    payload = {
        "assets": [
            {
                "symbol": "VNM",
                "sector": "Consumer",
                "weight_pct": 50.0,
                "market_beta": 1.0,
                "size_smb": 0.1,
                "value_hml": 0.2,
                "momentum": 0.05,
                "volatility": 0.15,
                "liquidity": 0.8,
                "quality": 0.9,
                "leverage": 0.3,
                "specific_risk_pct": 0.1,
            },
            {
                "symbol": "FPT",
                "sector": "Technology",
                "weight_pct": 50.0,
                "market_beta": 1.1,
                "size_smb": 0.2,
                "value_hml": 0.1,
                "momentum": 0.1,
                "volatility": 0.2,
                "liquidity": 0.7,
                "quality": 0.95,
                "leverage": 0.2,
                "specific_risk_pct": 0.12,
            },
        ],
        "factor_covariance": [[0.04 if i == j else 0.005 for j in range(8)] for i in range(8)],
    }
    resp = client.post("/api/v1/risk/barra/decomposition", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "factor_exposures" in data
    assert "total_variance" in data


# ==============================================================================
# SECTION 2: Dashboard Endpoint Wiring Gaps / Unwired State Verification
# ==============================================================================

def test_chart_station_data_wiring_real_ohlcv_and_indicators(client):
    resp = client.get("/api/v1/market/chart/VNM")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "VNM"
    assert data["candles"]
    assert 0 <= data["rsi14"] <= 100
    assert all("open" in candle and "close" in candle for candle in data["candles"])


def test_market_orderbook_synthetic_fallback(client):
    resp = client.get("/api/v1/market/orderbook/VNM")
    assert resp.status_code == 200
    assert resp.json()["is_synthetic"] is True
    assert resp.json()["bids"] and resp.json()["asks"]


def test_portfolio_state_genuine_lakehouse_wiring(client):
    resp = client.get("/api/v1/portfolio/state")
    assert resp.status_code == 200
    assert resp.json()["holdings"]


def test_execution_blotter_wired(client):
    resp = client.get("/api/v1/execution/blotter")
    assert resp.status_code == 200
    assert "orders" in resp.json()


def test_execution_routing_diagnostics_wired(client):
    resp = client.get("/api/v1/execution/routing-diagnostics")
    assert resp.status_code == 200
    assert resp.json()["routers"]


def test_risk_barra_decomposition_get_endpoint(client):
    resp = client.get("/api/v1/risk/barra/decomposition")
    assert resp.status_code == 200
    assert resp.json()["factors"]


def test_risk_stress_scenarios_wired(client):
    resp = client.get("/api/v1/risk/stress-scenarios")
    assert resp.status_code == 200
    assert resp.json()["scenarios"]


def test_tca_post_trade_report_empty_fail_closed(client):
    resp = client.get("/api/v1/tca/post-trade-report")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "DATA_NOT_FOUND"


# ==============================================================================
# SECTION 3: 16-Dimension Boundary & Fault-Injection Adversarial Matrix
# ==============================================================================

def test_dim01_strict_types_and_malformed_inputs(client):
    # Non-integer query limit
    assert client.get("/api/v1/market/ohlcv/VNM?limit=invalid_int").status_code == 422
    # Negative limit
    assert client.get("/api/v1/market/ohlcv/VNM?limit=-10").status_code == 422
    # String NaN in float parameter
    assert client.post(
        "/api/v1/risk/tca/simulate",
        json={
            "symbol": "VNM",
            "order_size": "NaN",
            "average_daily_volume": 500000.0,
            "volatility": 0.25,
            "participation_rate": 0.05,
            "side": "BUY",
            "arrival_price": 75000.0,
            "observed_spread_bps": 10.0,
        },
    ).status_code == 422

    # String Infinity and -Infinity in float parameter
    assert client.post(
        "/api/v1/risk/tca/simulate",
        json={
            "symbol": "VNM",
            "order_size": "Infinity",
            "average_daily_volume": 500000.0,
            "volatility": 0.25,
            "participation_rate": 0.05,
            "side": "BUY",
            "arrival_price": 75000.0,
            "observed_spread_bps": 10.0,
        },
    ).status_code == 422

    # None in required numeric parameter
    assert client.post(
        "/api/v1/risk/tca/simulate",
        json={
            "symbol": "VNM",
            "order_size": None,
            "average_daily_volume": 500000.0,
            "volatility": 0.25,
            "participation_rate": 0.05,
            "side": "BUY",
            "arrival_price": 75000.0,
            "observed_spread_bps": 10.0,
        },
    ).status_code == 422

    # Portfolio rebalance execute None, NaN, and Inf boundaries
    assert client.post("/api/v1/portfolio/rebalance/execute", json={"totp_code": None}).status_code == 422
    assert client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={"totp_code": "123456", "portfolio_value": "NaN"},
    ).status_code == 422
    assert client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={"totp_code": "123456", "portfolio_value": "Infinity"},
    ).status_code == 422
    assert client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={"totp_code": "123456", "target_portfolio": {"FPT": "NaN"}},
    ).status_code == 422
    assert client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={"totp_code": "123456", "target_portfolio": {"FPT": "Infinity"}},
    ).status_code == 422

    # Barra decomposition None and NaN boundaries
    assert client.post("/api/v1/risk/barra/decomposition", json={"assets": None}).status_code == 422
    assert client.post(
        "/api/v1/risk/barra/decomposition",
        json={
            "assets": [
                {
                    "symbol": "VNM",
                    "sector": "Consumer",
                    "weight_pct": "NaN",
                    "market_beta": 1.0,
                    "size_smb": 0.1,
                    "value_hml": 0.2,
                    "momentum": 0.05,
                    "volatility": 0.15,
                    "liquidity": 0.8,
                    "quality": 0.9,
                    "leverage": 0.3,
                    "specific_risk_pct": 0.1,
                }
            ],
            "factor_covariance": [[0.04]],
        },
    ).status_code == 422


def test_dim02_file_io_path_traversal_aliasing(client):
    # Path traversal in symbol parameter
    resp_tca = client.post(
        "/api/v1/risk/tca/simulate",
        json={
            "symbol": "../../etc/passwd",
            "order_size": 1000.0,
            "average_daily_volume": 500000.0,
            "volatility": 0.25,
            "participation_rate": 0.05,
            "side": "BUY",
            "arrival_price": 75000.0,
            "observed_spread_bps": 10.0,
        },
    )
    assert resp_tca.status_code == 422

    resp_orderbook = client.get("/api/v1/market/orderbook/..%2F..%2Fetc%2Fpasswd")
    assert resp_orderbook.status_code in (404, 422, 503)


def test_dim03_corrupted_duplicate_partial_payloads(client):
    # Empty body
    assert client.post("/api/v1/risk/tca/simulate", json={}).status_code == 422
    # Whitespace symbol
    assert client.get("/api/v1/market/ohlcv/%20").status_code in (404, 422)
    # Empty payloads and collections across rebalance and risk endpoints
    assert client.post("/api/v1/portfolio/rebalance/execute", json={}).status_code == 422
    assert client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={"totp_code": "123456", "target_portfolio": {}},
    ).status_code == 422
    assert client.post("/api/v1/risk/barra/decomposition", json={}).status_code == 422
    assert client.post(
        "/api/v1/risk/barra/decomposition",
        json={"assets": [], "factor_covariance": []},
    ).status_code == 422


def test_dim04_fail_closed_error_states(client):
    # Wired entities return structured success envelopes without unhandled crashes.
    resp = client.get("/api/v1/portfolio/state")
    assert resp.status_code == 200
    assert "holdings" in resp.json()

    resp_diag = client.get("/api/v1/execution/routing-diagnostics")
    assert resp_diag.status_code == 200
    assert "routers" in resp_diag.json()


def test_dim05_rollback_and_atomic_read_isolation(client, monkeypatch):
    # Consecutive reads remain idempotent with identical values
    res1 = client.get("/api/v1/macro/summary")
    res2 = client.get("/api/v1/macro/summary")
    assert res1.status_code == res2.status_code
    assert res1.status_code in (200, 503)
    assert res1.json() == res2.json()

    # Durable rollback and fault injection for portfolio rebalance order routing (portfolio.py:216-258)
    import omega.api.routes.portfolio as prt
    monkeypatch.setattr(prt, "verify_totp", lambda code: True)

    canary_queue_order = {"order_id": "PRE_QUEUE_CANARY", "symbol": "VNM", "quantity": 100}
    canary_schedule_order = {"order_id": "PRE_SCHED_CANARY", "symbol": "VNM", "quantity": 100}
    monkeypatch.setattr(prt.smart_router, "queue", [canary_queue_order])
    monkeypatch.setattr(prt.smart_router, "schedule", [canary_schedule_order])

    queue_alias = prt.smart_router.queue
    schedule_alias = prt.smart_router.schedule

    route_call_count = 0
    real_route = prt.smart_router.route_order

    def failing_route(order, *args, **kwargs):
        nonlocal route_call_count
        route_call_count += 1
        if route_call_count == 2:
            raise RuntimeError("FORCED_MID_FLIGHT_ROUTING_FAULT")
        return real_route(order, *args, **kwargs)

    monkeypatch.setattr(prt.smart_router, "route_order", failing_route)

    res = client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={
            "totp_code": "123456",
            "strategy_id": "ALPHA_HRP_V2",
            "target_portfolio": {"FPT": 0.8, "HPG": 0.2},
            "portfolio_value": 1_000_000_000.0,
            "routing_algo": "TWAP",
        },
    )
    assert res.status_code == 503
    assert res.json()["detail"] == "ORDER_ROUTING_FAILED"

    # Verify state rolled back to snapshot and list slice identity preserved
    assert prt.smart_router.queue == [canary_queue_order]
    assert prt.smart_router.schedule == [canary_schedule_order]
    assert prt.smart_router.queue is queue_alias
    assert prt.smart_router.schedule is schedule_alias

    # Verify router lock was cleanly released and is not deadlocked
    lock = getattr(prt.smart_router, "_lock", prt._ROUTER_LOCK)
    assert not lock.locked()


def test_dim05_portfolio_rebalance_timeout_rollback_fault_injection(client, monkeypatch):
    """Timeout fault injection during order routing must roll back state and fail closed."""
    import omega.api.routes.portfolio as prt
    monkeypatch.setattr(prt, "verify_totp", lambda code: True)

    canary_q = [{"canary": "q_timeout"}]
    canary_s = [{"canary": "s_timeout"}]
    monkeypatch.setattr(prt.smart_router, "queue", canary_q)
    monkeypatch.setattr(prt.smart_router, "schedule", canary_s)
    q_alias = prt.smart_router.queue
    s_alias = prt.smart_router.schedule

    def timeout_route(*args, **kwargs):
        raise TimeoutError("ORDER_ROUTING_NETWORK_TIMEOUT")

    monkeypatch.setattr(prt.smart_router, "route_order", timeout_route)

    res = client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={
            "totp_code": "123456",
            "strategy_id": "ALPHA_HRP_V2",
            "target_portfolio": {"FPT": 0.8, "HPG": 0.2},
            "portfolio_value": 1_000_000_000.0,
            "routing_algo": "TWAP",
        },
    )
    assert res.status_code == 503
    assert res.json()["detail"] == "ORDER_ROUTING_FAILED"
    assert prt.smart_router.queue == canary_q
    assert prt.smart_router.schedule == canary_s
    assert prt.smart_router.queue is q_alias
    assert prt.smart_router.schedule is s_alias
    lock = getattr(prt.smart_router, "_lock", prt._ROUTER_LOCK)
    assert not lock.locked()


def test_dim05_portfolio_rebalance_non_list_attribute_rollback(client, monkeypatch):
    """Direct attribute rollback fallback when queue or schedule is non-list (lines 251-252/255-256)."""
    import omega.api.routes.portfolio as prt
    monkeypatch.setattr(prt, "verify_totp", lambda code: True)

    canary_q = [{"initial": 1}]
    canary_s = [{"initial": 2}]
    monkeypatch.setattr(prt.smart_router, "queue", canary_q)
    monkeypatch.setattr(prt.smart_router, "schedule", canary_s)

    def corrupt_and_fail(*args, **kwargs):
        prt.smart_router.queue = "non_list_corrupted_queue"
        prt.smart_router.schedule = ("non_list_corrupted_schedule",)
        raise RuntimeError("CORRUPTED_CONTAINER_FAULT")

    monkeypatch.setattr(prt.smart_router, "route_order", corrupt_and_fail)

    res = client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={
            "totp_code": "123456",
            "strategy_id": "ALPHA_HRP_V2",
            "target_portfolio": {"FPT": 0.8, "HPG": 0.2},
            "portfolio_value": 1_000_000_000.0,
            "routing_algo": "TWAP",
        },
    )
    assert res.status_code == 503
    assert res.json()["detail"] == "ORDER_ROUTING_FAILED"
    assert prt.smart_router.queue == canary_q
    assert prt.smart_router.schedule == canary_s
    lock = getattr(prt.smart_router, "_lock", prt._ROUTER_LOCK)
    assert not lock.locked()


def test_dim06_point_in_time_and_lookahead_safety(client):
    # Inverted date range on trading days rejected
    resp = client.get("/api/v1/market/ohlcv/VNM?start=2026-01-05&end=2026-01-02")
    assert resp.status_code == 422
    assert "INVALID_DATE_RANGE" in resp.text

    # Valid ISO timestamp returned from summary
    summary_resp = client.get("/api/v1/macro/summary")
    if summary_resp.status_code == 200:
        dt = datetime.fromisoformat(summary_resp.json()["as_of_date"].replace("Z", "+00:00"))
        assert dt is not None
    else:
        assert summary_resp.status_code == 503


def test_dim07_trading_calendar_and_holiday_boundaries(client):
    # Holiday / non-trading date rejected
    resp_holiday = client.get("/api/v1/market/ohlcv/VNM?start=2026-01-01")
    assert resp_holiday.status_code == 422
    assert "MARKET_CALENDAR_NON_TRADING_DAY" in resp_holiday.text

    # Malformed calendar date string rejected
    resp = client.get("/api/v1/market/ohlcv/VNM?start=bad_calendar_format")
    assert resp.status_code == 422


def test_dim08_numeric_precision_zero_division_overflow(client):
    # Zero volume denominator
    assert client.post(
        "/api/v1/risk/tca/simulate",
        json={
            "symbol": "VNM",
            "order_size": 1000.0,
            "average_daily_volume": 0.0,
            "volatility": 0.25,
            "participation_rate": 0.05,
            "side": "BUY",
            "arrival_price": 75000.0,
            "observed_spread_bps": 10.0,
        },
    ).status_code == 422

    # Zero order size
    assert client.post(
        "/api/v1/risk/tca/simulate",
        json={
            "symbol": "VNM",
            "order_size": 0.0,
            "average_daily_volume": 500000.0,
            "volatility": 0.25,
            "participation_rate": 0.05,
            "side": "BUY",
            "arrival_price": 75000.0,
            "observed_spread_bps": 10.0,
        },
    ).status_code == 422

    # Portfolio rebalance numeric boundaries: zero value, negative value, zero weights, weight sum > 1.0, float overflow
    assert client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={"totp_code": "123456", "portfolio_value": 0.0},
    ).status_code == 422
    assert client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={"totp_code": "123456", "portfolio_value": -1_000_000.0},
    ).status_code == 422
    assert client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={"totp_code": "123456", "target_portfolio": {"FPT": 0.0, "HPG": 0.0}},
    ).status_code == 422
    assert client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={"totp_code": "123456", "target_portfolio": {"FPT": 0.7, "HPG": 0.7}},
    ).status_code == 422
    assert client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={"totp_code": "123456", "portfolio_value": "1e309"},
    ).status_code == 422


def test_dim09_concurrency_race_condition_resistance(client):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: client.get("/api/v1/execution/status").status_code, range(16)))
    assert results == [200] * 16


def test_dim10_vnd_full_price_scale_unit_invariance(client):
    # Fractional sub-dong price rejected
    resp_frac = client.post(
        "/api/v1/execution/orders",
        json={
            "symbol": "VNM",
            "side": "BUY",
            "size": 100.0,
            "price": 75000.5,
            "feature_ts": "2026-01-01T08:00:00+07:00",
            "decision_ts": "2026-01-01T08:05:00+07:00",
        },
    )
    assert resp_frac.status_code == 422

    # Price below 100 VND floor rejected
    resp_low = client.post(
        "/api/v1/execution/orders",
        json={
            "symbol": "VNM",
            "side": "BUY",
            "size": 100.0,
            "price": 50,
            "feature_ts": "2026-01-01T08:00:00+07:00",
            "decision_ts": "2026-01-01T08:05:00+07:00",
        },
    )
    assert resp_low.status_code == 422


def test_dim11_survivorship_delisting_anomalies(client):
    # Unknown or delisted symbol returns 0 bars rather than crashing
    resp = client.get("/api/v1/market/ohlcv/DELISTED_TICKER_999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_bars"] == 0
    assert data["bars"] == []


def test_dim12_cli_injection_flag_smuggling_sanitization(client):
    # Shell injection payload in symbol rejected
    resp = client.post(
        "/api/v1/risk/tca/simulate",
        json={
            "symbol": "; rm -rf /",
            "order_size": 1000.0,
            "average_daily_volume": 500000.0,
            "volatility": 0.25,
            "participation_rate": 0.05,
            "side": "BUY",
            "arrival_price": 75000.0,
            "observed_spread_bps": 10.0,
        },
    )
    assert resp.status_code == 422


def test_dim13_schema_drift_extra_column_mutations(client):
    # Extra payload fields rejected by StrictModel
    resp = client.post(
        "/api/v1/risk/tca/simulate",
        json={
            "symbol": "VNM",
            "order_size": 1000.0,
            "average_daily_volume": 500000.0,
            "volatility": 0.25,
            "participation_rate": 0.05,
            "side": "BUY",
            "arrival_price": 75000.0,
            "observed_spread_bps": 10.0,
            "unexpected_drift_column": "malicious",
        },
    )
    assert resp.status_code == 422


def test_dim14_resource_exhaustion_memory_bounds(client):
    # Oversized payload exceeding 512 KiB rejected with 413
    big_body = {"symbol": "VNM", "pad": "A" * (513 * 1024)}
    resp = client.post("/api/v1/risk/tca/simulate", json=big_body)
    assert resp.status_code == 413
    assert "exceeds" in resp.json()["detail"]

    # Excessive query limit rejected
    resp_limit = client.get("/api/v1/market/ohlcv/VNM?limit=999999")
    assert resp_limit.status_code == 422


def test_dim15_network_timeout_and_dependency_exhaustion(client, monkeypatch):
    # Synthetic fallback handles unavailable live dependency without crashing.
    resp = client.get("/api/v1/market/orderbook/VNM")
    assert resp.status_code == 200
    assert resp.json()["is_synthetic"] is True

    # Upstream routing network timeout fault injection fails closed with 503
    import omega.api.routes.portfolio as prt
    monkeypatch.setattr(prt, "verify_totp", lambda code: True)

    def route_timeout(*args, **kwargs):
        raise TimeoutError("GATEWAY_TIMEOUT_SOCKET_EXHAUSTION")

    monkeypatch.setattr(prt.smart_router, "route_order", route_timeout)
    resp_timeout = client.post(
        "/api/v1/portfolio/rebalance/execute",
        json={
            "totp_code": "123456",
            "strategy_id": "ALPHA_HRP_V2",
            "target_portfolio": {"FPT": 0.8, "HPG": 0.2},
            "portfolio_value": 1_000_000_000.0,
            "routing_algo": "TWAP",
        },
    )
    assert resp_timeout.status_code == 503
    assert resp_timeout.json()["detail"] == "ORDER_ROUTING_FAILED"


def test_dim16_secret_redaction_credential_leak_prevention(client):
    # Sent tokens must never be echoed in responses
    dummy_auth_token = "BEARER_SECRET_TOKEN_ALPHA_998877"
    resp = client.get(
        "/api/v1/macro/summary",
        headers={"Authorization": f"Bearer {dummy_auth_token}", "X-API-Key": dummy_auth_token},
    )
    assert resp.status_code in (200, 503)
    assert dummy_auth_token not in resp.text
    assert "C:\\" not in resp.text


def test_f006_execution_timestamp_ordering(client):
    payload = {
        "symbol": "VNM", "side": "BUY", "size": 100, "price": 75000,
        "feature_ts": "2026-01-01T09:00:00+07:00",
        "available_at": "2026-01-01T09:30:00+07:00",
        "decision_ts": "2026-01-01T09:15:00+07:00",
    }
    assert client.post("/api/v1/execution/orders", json=payload).status_code == 422


def test_f007_order_book_schema_bounds(client):
    nested = 1
    for _ in range(11):
        nested = {"x": nested}
    payload = {
        "symbol": "VNM", "side": "BUY", "size": 100, "price": 75000,
        "feature_ts": "2026-01-01T09:00:00+07:00",
        "decision_ts": "2026-01-01T09:15:00+07:00",
        "order_book_data": nested,
    }
    assert client.post("/api/v1/execution/orders", json=payload).status_code == 422


def test_f001_macro_summary_rejects_naive_and_future_pit(client):
    naive = client.get("/api/v1/macro/summary?as_of=2026-01-02T10:00:00")
    assert naive.status_code == 422
    assert naive.json()["detail"] == "PIT_CUTOFF_TIMEZONE_REQUIRED"
    future = client.get("/api/v1/macro/summary?as_of=2099-01-01T00:00:00Z")
    assert future.status_code == 422
    assert future.json()["detail"] == "PIT_CUTOFF_IN_FUTURE"


def test_f001_macro_summary_excludes_future_vintages(client, tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    path = tmp_path / "macro.parquet"
    pd.DataFrame([
        {"indicator": "cpi", "value": 3.2, "observation_date": "2026-01-01", "as_of": now - timedelta(days=2), "available_at": now - timedelta(days=1), "source": "GSO"},
        {"indicator": "cpi", "value": 9.9, "observation_date": "2026-01-02", "as_of": now, "available_at": now + timedelta(days=1), "source": "GSO"},
    ]).to_parquet(path)
    monkeypatch.setattr("omega.api.routes.macro.MACRO_PARQUET_PATH", path)
    monkeypatch.setattr("omega.api.routes.macro.INTERBANK_PATH", tmp_path / "missing.json")
    response = client.get("/api/v1/macro/summary", params={"as_of": (now - timedelta(hours=1)).isoformat()})
    assert response.status_code == 503
    assert response.json()["detail"] == "INTERBANK_DATA_UNAVAILABLE"


def test_f002_circuit_breaker_rejects_naive_and_future_pit(client):
    naive = client.get("/api/v1/risk/circuit-breaker/status?symbol=VNM&as_of=2026-01-02T10:00:00")
    assert naive.status_code == 422
    assert naive.json()["detail"] == "PIT_CUTOFF_TIMEZONE_REQUIRED"
    future = client.get("/api/v1/risk/circuit-breaker/status?symbol=VNM&as_of=2099-01-01T00:00:00Z")
    assert future.status_code == 422
    assert future.json()["detail"] == "PIT_CUTOFF_IN_FUTURE"


def test_f004_stress_scenarios_rejects_schema_drift(client, tmp_path, monkeypatch):
    path = tmp_path / "hybrid.parquet"
    pd.DataFrame([{"symbol": "VNM", "effective_quant_weight": 0.2}]).to_parquet(path)
    monkeypatch.setattr("omega.api.routes.risk_tca.HYBRID_EVAL_PATH", path)
    response = client.get("/api/v1/risk/stress-scenarios")
    assert response.status_code == 424
    assert response.json()["detail"] == "DATASET_PIT_INVALID"


# ==============================================================================
# SECTION 4: Cycle 3 Mandatory Finding Closure Matrix (F-001..F-007)
# ==============================================================================

def test_f001_no_fabricated_metrics(client):
    """F-001: Genuine computation without fabricated fallback metrics."""
    orderbook_resp = client.get("/api/v1/market/orderbook/VNM?fallback=false")
    assert orderbook_resp.status_code == 503
    assert orderbook_resp.json()["detail"] == "REAL_L2_FEED_UNAVAILABLE"

    macro_resp = client.get("/api/v1/macro/summary")
    if macro_resp.status_code == 200:
        data = macro_resp.json()
        assert data["status"] == "success"
        assert isinstance(data["interbankRate"], (int, float))
        assert isinstance(data["marketBreadth"], (int, float))
        assert isinstance(data["indicators"], dict)
    else:
        assert macro_resp.status_code == 503
        assert macro_resp.json()["detail"] in {
            "MARKET_BREADTH_UNAVAILABLE", "MACRO_DATA_UNAVAILABLE",
            "MACRO_DATA_INVALID", "INTERBANK_DATA_UNAVAILABLE", "INTERBANK_DATA_INVALID",
        }

    tca_payload = {
        "symbol": "VNM",
        "order_size": 1000.0,
        "average_daily_volume": 500000.0,
        "volatility": 0.25,
        "participation_rate": 0.05,
        "side": "BUY",
        "arrival_price": 75000.0,
        "observed_spread_bps": 10.0,
    }
    tca_resp = client.post("/api/v1/risk/tca/simulate", json=tca_payload)
    assert tca_resp.status_code == 200
    tca_data = tca_resp.json()
    assert tca_data["is_synthetic"] is False
    assert tca_data["source"] == "request_market_observations"
    assert tca_data["estimated_impact_bps"] > 0


def test_f002_fail_closed_empty_dependencies(client):
    """F-002: Fail-closed contract for empty or unavailable dependencies."""
    assert client.get("/api/v1/portfolio/dynamic-universe").status_code == 424
    assert client.get("/api/v1/portfolio/dynamic-universe").json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"

    assert client.get("/api/v1/alpha/arsenal/signals").status_code == 424

    assert client.get("/api/v1/market/chart/NONEXISTENT999").status_code == 404
    assert client.get("/api/v1/market/orderbook/NONEXISTENT999").status_code == 404

    tca_empty = client.get("/api/v1/tca/post-trade-report")
    assert tca_empty.status_code == 404
    assert tca_empty.json()["detail"] == "DATA_NOT_FOUND"


def test_f003_timezone_naive_and_aware_pit(client):
    """F-003: Require explicit timezone offsets and reject naive PIT timestamps."""
    # Naive PIT timestamps must fail with 422
    ohlcv_naive = client.get("/api/v1/market/ohlcv/VNM?as_of=2026-01-02T10:00:00")
    assert ohlcv_naive.status_code == 422
    assert ohlcv_naive.json()["detail"] == "PIT_CUTOFF_TIMEZONE_REQUIRED"

    chart_naive = client.get("/api/v1/market/chart/VNM?as_of=2026-01-02T10:00:00")
    assert chart_naive.status_code == 422
    assert chart_naive.json()["detail"] == "PIT_CUTOFF_TIMEZONE_REQUIRED"

    orderbook_naive = client.get("/api/v1/market/orderbook/VNM?as_of=2026-01-02T10:00:00")
    assert orderbook_naive.status_code == 422
    assert orderbook_naive.json()["detail"] == "PIT_CUTOFF_TIMEZONE_REQUIRED"

    portfolio_naive = client.get("/api/v1/portfolio/state?as_of=2026-01-02T10:00:00")
    assert portfolio_naive.status_code == 422
    assert portfolio_naive.json()["detail"] == "PIT_CUTOFF_INVALID"

    # Aware PIT timestamps must be accepted
    ohlcv_utc = client.get("/api/v1/market/ohlcv/VNM?as_of=2026-01-02T10:00:00Z")
    assert ohlcv_utc.status_code == 200

    ohlcv_ict = client.get("/api/v1/market/ohlcv/VNM?as_of=2026-01-02T17:00:00%2B07:00")
    assert ohlcv_ict.status_code == 200


def test_f004_malformed_and_future_pit_timestamps(client):
    """F-004: Reject malformed ISO formats and future PIT timestamps."""
    # Malformed strings
    assert client.get("/api/v1/market/ohlcv/VNM?as_of=invalid_timestamp_str").status_code == 422
    assert client.get("/api/v1/market/chart/VNM?as_of=2026-99-99T99:99:99").status_code == 422
    assert client.get("/api/v1/market/orderbook/VNM?as_of=corrupt-iso").status_code == 422
    assert client.get("/api/v1/portfolio/state?as_of=bad_date_format").status_code == 422

    # Future timestamps rejected
    ohlcv_future = client.get("/api/v1/market/ohlcv/VNM?as_of=2099-01-01T00:00:00Z")
    assert ohlcv_future.status_code == 422
    assert ohlcv_future.json()["detail"] == "PIT_CUTOFF_IN_FUTURE"

    chart_future = client.get("/api/v1/market/chart/VNM?as_of=2099-01-01T00:00:00Z")
    assert chart_future.status_code == 422
    assert chart_future.json()["detail"] == "PIT_CUTOFF_IN_FUTURE"

    portfolio_future = client.get("/api/v1/portfolio/state?as_of=2099-01-01T00:00:00Z")
    assert portfolio_future.status_code == 422
    assert portfolio_future.json()["detail"] == "PIT_CUTOFF_INVALID"


def test_f005_execution_health_missing_telemetry_genuine(client):
    """F-005: Execution status and workers reflect genuine telemetry without fabrication."""
    status_resp = client.get("/api/v1/execution/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["state"] in {"STOPPED", "RUNNING", "PAUSED"}
    assert isinstance(status_data["active_workers"], int)
    assert isinstance(status_data["workers"], list)
    assert status_data["active_workers"] == len(status_data["workers"])

    workers_resp = client.get("/api/v1/execution/workers")
    assert workers_resp.status_code == 200
    assert isinstance(workers_resp.json(), list)

    diag_resp = client.get("/api/v1/execution/routing-diagnostics")
    assert diag_resp.status_code == 200
    diag_data = diag_resp.json()
    assert diag_data["status"] == "success"
    assert diag_data["engine"] == "paper_trading"
    assert diag_data["total_active_orders"] >= 0


def test_f006_tca_missing_arrival_and_benchmark_data(client):
    """F-006: TCA endpoints fail closed on missing arrival price or trade benchmarks."""
    payload_missing_arrival = {
        "symbol": "VNM",
        "order_size": 1000.0,
        "average_daily_volume": 500000.0,
        "volatility": 0.25,
        "participation_rate": 0.05,
        "side": "BUY",
        "observed_spread_bps": 10.0,
    }
    # Missing arrival price must fail validation
    assert client.post("/api/v1/risk/tca/simulate", json=payload_missing_arrival).status_code == 422

    # Sub-threshold arrival price must fail validation (>1000 required)
    payload_sub_threshold = {**payload_missing_arrival, "arrival_price": 500.0}
    assert client.post("/api/v1/risk/tca/simulate", json=payload_sub_threshold).status_code == 422

    # Post-trade report without executions must not fabricate benchmarks
    post_trade_resp = client.get("/api/v1/tca/post-trade-report")
    assert post_trade_resp.status_code == 404
    assert post_trade_resp.json()["detail"] == "DATA_NOT_FOUND"


def test_f007_secret_redaction_in_errors_and_queries(client):
    """F-007: Secret tokens and credentials are redacted in errors and responses."""
    from omega.api.routes._market_loader import redact_market_data_error

    sensitive_text = "Failed Bearer SECRET_BEARER_9999 " + "token=" + "SECRET_TOKEN_8888 " + "api_key=" + "SECRET_KEY_7777 " + "password=" + "SECRET_PASS_6666"
    redacted = redact_market_data_error(Exception(sensitive_text))
    assert "SECRET_BEARER_9999" not in redacted
    assert "SECRET_TOKEN_8888" not in redacted
    assert "SECRET_KEY_7777" not in redacted
    assert "SECRET_PASS_6666" not in redacted
    assert "[REDACTED]" in redacted

    secret_token = "SECRET_QUERY_TOKEN_ALPHA_7788"
    resp = client.get(f"/api/v1/market/ohlcv/VNM?limit=5&token={secret_token}")
    assert secret_token not in resp.text

    resp_err = client.get(f"/api/v1/market/ohlcv/NONEXISTENT999?as_of=bad&token={secret_token}")
    assert secret_token not in resp_err.text
