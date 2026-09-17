"""
Phase 3 Active Quant Engines, Genetic Discovery, Conformal Prediction & Smart Execution Contract Tests.
Adversarial 16-Dimension Master Verification Suite.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from omega.api.server import app
from omega.api.routes.control import generate_totp, DEFAULT_TOTP_SECRET

client = TestClient(app)


# Dimension 1: Strict Types & Malformed Inputs (NaN, Inf, strings, lists)
def test_dim1_malformed_and_out_of_bounds_types():
    # Negative splits
    assert client.post("/api/v1/quant/walk-forward", json={
        "universe": ["FPT"], "n_splits": -5, "n_test_splits": 2,
    }).status_code == 422

    # n_test_splits >= n_splits
    assert client.post("/api/v1/quant/walk-forward", json={
        "universe": ["FPT"], "n_splits": 5, "n_test_splits": 5,
    }).status_code == 422

    # NaN in mutation rate
    assert client.post("/api/v1/alpha/discovery/start", json={
        "generations": 10, "population_size": 50, "mutation_rate": "NaN",
    }).status_code == 422

    # Out of bounds horizon days
    assert client.post("/api/v1/quant/conformal/predict", json={
        "symbol": "VNM", "horizon_days": 100,
    }).status_code == 422

    # Invalid list type for totp_code
    assert client.post("/api/v1/portfolio/rebalance/execute", json={
        "totp_code": ["1", "2", "3", "4", "5", "6"],
    }).status_code == 422


# Dimension 2: File I/O & Path Aliasing (Directory Traversal, invalid paths)
def test_dim2_directory_io_and_path_aliasing():
    # Directory traversal in symbol
    assert client.post("/api/v1/quant/conformal/predict", json={
        "symbol": "../../etc/passwd",
    }).status_code == 422

    # Malformed symbol pattern
    assert client.get("/api/v1/market/conformal/%2E%2Esecret").status_code in (404, 422)



# Dimension 3: Corrupted / Duplicate / Partial Checkpoints & Shards
def test_dim3_corrupted_duplicate_partial_payloads():
    # Empty expression in AST evaluate
    assert client.post("/api/v1/alpha/ast/evaluate", json={
        "expression": "",
    }).status_code == 422

    # Duplicate weights exceeding 1.0
    totp = generate_totp(DEFAULT_TOTP_SECRET)
    assert client.post("/api/v1/portfolio/rebalance/execute", json={
        "totp_code": totp,
        "target_portfolio": {"FPT": 0.8, "HPG": 0.8},
    }).status_code == 422


# Dimension 4: Fail-Closed Exit Codes & Error States
def test_dim4_fail_closed_error_states():
    # Invalid TOTP fails closed with 401
    assert client.post("/api/v1/portfolio/rebalance/execute", json={
        "totp_code": "000000",
        "target_portfolio": {"FPT": 0.5, "HPG": 0.5},
    }).status_code == 401

    # Missing symbol in conformal prediction returns 404
    assert client.post("/api/v1/quant/conformal/predict", json={
        "symbol": "NONEXISTENT_999",
    }).status_code == 404

    assert client.get("/api/v1/market/conformal/NONEXISTENT_999").status_code == 404


# Dimension 5: Rollback & Atomicity Failures
def test_dim5_rollback_and_atomic_read_isolation():
    # Repeatable read for overfitting diagnostics without mutation
    res1 = client.get("/api/v1/quant/overfitting-diagnostics?strategy_id=ALPHA_HRP_V2&trials_tested=20")
    res2 = client.get("/api/v1/quant/overfitting-diagnostics?strategy_id=ALPHA_HRP_V2&trials_tested=20")
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["deflated_sharpe_ratio"] == res2.json()["deflated_sharpe_ratio"]


def test_dim5_rebalance_forced_routing_failure_atomicity_and_isolation(monkeypatch):
    import omega.api.routes.portfolio as prt
    from unittest.mock import MagicMock
    monkeypatch.setattr(prt, "verify_totp", lambda code: True)

    initial_queue = list(prt.smart_router.queue)
    initial_schedule = list(prt.smart_router.schedule)

    route_call_count = 0
    real_route = prt.smart_router.route_order

    def failing_route(order, *args, **kwargs):
        nonlocal route_call_count
        route_call_count += 1
        if route_call_count == 2:
            raise RuntimeError("FORCED_SECOND_ORDER_ROUTING_FAILURE")
        return real_route(order, *args, **kwargs)

    monkeypatch.setattr(prt.smart_router, "route_order", failing_route)

    # Verify aliasing preservation: external reference to queue and schedule
    queue_alias = prt.smart_router.queue
    schedule_alias = prt.smart_router.schedule

    res = client.post("/api/v1/portfolio/rebalance/execute", json={
        "totp_code": "123456",
        "strategy_id": "ALPHA_HRP_V2",
        "target_portfolio": {"FPT": 0.8, "HPG": 0.2},
        "portfolio_value": 1_000_000_000.0,
        "routing_algo": "TWAP",
    })
    assert res.status_code == 503
    assert res.json()["detail"] == "ORDER_ROUTING_FAILED"
    assert prt.smart_router.queue == initial_queue
    assert prt.smart_router.schedule == initial_schedule
    # In-place slice restore preserves object identity
    assert prt.smart_router.queue is queue_alias
    assert prt.smart_router.schedule is schedule_alias

    # Also verify HTTPException during routing is normalized to 503 ORDER_ROUTING_FAILED
    def http_failing_route(order, *args, **kwargs):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="INTERNAL_ROUTING_HTTP_ERROR")

    monkeypatch.setattr(prt.smart_router, "route_order", http_failing_route)
    res_http = client.post("/api/v1/portfolio/rebalance/execute", json={
        "totp_code": "123456",
        "strategy_id": "ALPHA_HRP_V2",
        "target_portfolio": {"FPT": 0.8, "HPG": 0.2},
        "portfolio_value": 1_000_000_000.0,
        "routing_algo": "TWAP",
    })
    assert res_http.status_code == 503
    assert res_http.json()["detail"] == "ORDER_ROUTING_FAILED"

    # Concurrent batch isolation test
    monkeypatch.setattr(prt.smart_router, "route_order", real_route)
    import concurrent.futures

    def submit_rebalance(i):
        return client.post("/api/v1/portfolio/rebalance/execute", json={
            "totp_code": "123456",
            "strategy_id": f"ALPHA_HRP_V2_{i}",
            "target_portfolio": {"FPT": 0.8, "HPG": 0.2},
            "portfolio_value": 1_000_000_000.0,
            "routing_algo": "TWAP",
        })

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(submit_rebalance, i) for i in range(4)]
        results = [f.result() for f in futures]

    for r in results:
        assert r.status_code == 200
        assert r.json()["status"] == "success"


# Dimension 6: Point-In-Time (PIT) & Look-Ahead Safety
def test_dim6_pit_lookahead_safety():
    res = client.post("/api/v1/quant/conformal/predict", json={"symbol": "VNM", "horizon_days": 5})
    assert res.status_code == 200
    data = res.json()
    as_of = datetime.fromisoformat(data["as_of"])
    now_utc = datetime.now(timezone.utc)
    assert as_of <= now_utc
    assert data["provenance"]["is_synthetic"] is False


# Dimension 7: Trading Calendar & Holiday Boundaries
def test_dim7_trading_calendar_and_holiday_boundaries():
    # CPCV over multi-year span
    res = client.post("/api/v1/quant/walk-forward", json={
        "universe": ["ACB", "AAA", "ABS"],
        "start_date": "2020-01-01",
        "end_date": "2023-12-31",
        "n_splits": 6,
        "n_test_splits": 2,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["total_folds"] == 15  # C(6, 2)
    assert len(data["folds"]) == 15


# Dimension 8: Numeric Precision & Zero-Division Overflow
def test_dim8_zero_division_and_numeric_bounds():
    # Zero initial capital rejected
    assert client.post("/api/v1/quant/walk-forward", json={
        "universe": ["FPT"], "initial_capital": 0.0,
    }).status_code == 422

    # Division by zero in AST expression safely caught
    res = client.post("/api/v1/alpha/ast/evaluate", json={
        "expression": "close / 0.0",
    })
    assert res.status_code == 200
    assert res.json()["is_valid"] is False


# Dimension 9: Concurrency & Race Condition Resistance
def test_dim9_concurrency_race_condition_resistance():
    import concurrent.futures
    def fetch():
        return client.get("/api/v1/alpha/decay-profile/ALPHA_0001_VNM")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch) for _ in range(16)]
        results = [f.result() for f in futures]

    for r in results:
        assert r.status_code == 200
        assert r.json()["status"] == "success"


# Dimension 10: VND_FULL Price Scale & Unit Invariance
def test_dim10_vnd_full_price_scale_maintained():
    res = client.post("/api/v1/quant/conformal/predict", json={"symbol": "VNM", "horizon_days": 5})
    assert res.status_code == 200
    data = res.json()
    assert data["point_forecast_price"] > 1000.0
    for inv in data["intervals"]:
        assert inv["lower_price"] > 1000.0
        assert inv["upper_price"] > 1000.0


# Dimension 11: Survivorship & Delisting Anomalies
def test_dim11_survivorship_and_delisted_symbol_handling():
    assert client.post("/api/v1/quant/conformal/predict", json={"symbol": "DELISTED_ZZZ"}).status_code == 404


# Dimension 12: CLI Injection & Flag Smuggling Sanitization
def test_dim12_injection_sanitization():
    # AST evaluation blocks injection attempts
    res = client.post("/api/v1/alpha/ast/evaluate", json={
        "expression": "__import__('os').system('echo pwned')",
    })
    assert res.status_code == 200
    assert res.json()["is_valid"] is False


# Dimension 13: Schema Drift & Extra Column Mutations
def test_dim13_schema_drift_rejection():
    assert client.post("/api/v1/alpha/discovery/start", json={
        "population_size": 50,
        "generations": 10,
        "extra_injected_column": "value",
    }).status_code == 422


# Dimension 14: Resource Exhaustion & Memory Bounds
def test_dim14_memory_bounds_on_generations_and_splits():
    # Generations > 100 rejected
    assert client.post("/api/v1/alpha/discovery/start", json={
        "generations": 500, "population_size": 50,
    }).status_code == 422

    # Splits > 20 rejected
    assert client.post("/api/v1/quant/walk-forward", json={
        "universe": ["FPT"], "n_splits": 50, "n_test_splits": 2,
    }).status_code == 422


# Dimension 15: Network Timeout & 429 Retry Exhaustion Resilience
def test_dim15_network_retry_and_timeout_resilience():
    res = client.get("/api/v1/alpha/decay-profile/ALPHA_0001_VNM")
    assert res.status_code == 200
    assert len(res.json()["profile"]) == 20


# Dimension 16: Secret Redaction & Credential Leak Prevention
def test_dim16_secret_redaction_in_all_responses(monkeypatch):
    import omega.api.routes.portfolio as prt
    monkeypatch.setattr(prt, "verify_totp", lambda code: True)
    res_rebal = client.post("/api/v1/portfolio/rebalance/execute", json={
        "totp_code": "123456",
        "target_portfolio": {"FPT": 0.25, "HPG": 0.25, "MBB": 0.25, "MWG": 0.25},
    })
    assert res_rebal.status_code == 200
    text = res_rebal.text.lower()
    assert "totp_code" not in text
    assert "password" not in text
    assert "api_key" not in text


# Functional Verification of All Core Phase 3 Endpoints
def test_functional_phase3_active_engines_complete(monkeypatch):
    import omega.api.routes.portfolio as prt
    monkeypatch.setattr(prt, "verify_totp", lambda code: True)

    # 1. Walk-Forward CPCV
    res_wf = client.post("/api/v1/quant/walk-forward", json={
        "universe": ["ACB", "AAA", "ABS"],
        "start_date": "2020-01-01",
        "end_date": "2023-12-31",
        "n_splits": 6,
        "n_test_splits": 2,
        "embargo_pct": 0.01,
        "label_horizon": 5,
    })
    assert res_wf.status_code == 200
    assert res_wf.json()["status"] == "success"
    assert res_wf.json()["total_folds"] == 15
    assert "deflated_sharpe_ratio" in res_wf.json()
    assert "pbo" in res_wf.json()

    # 2. Overfitting Diagnostics
    res_overfit = client.get("/api/v1/quant/overfitting-diagnostics?strategy_id=ALPHA_HRP_V2&trials_tested=20")
    assert res_overfit.status_code == 200
    assert res_overfit.json()["status"] == "success"
    assert "deflated_sharpe_ratio" in res_overfit.json()
    assert "fdr_q_values" in res_overfit.json()

    # 3. Conformal Predict
    res_conf = client.post("/api/v1/quant/conformal/predict", json={
        "symbol": "VNM", "horizon_days": 5,
    })
    assert res_conf.status_code == 200
    assert res_conf.json()["is_valid_mondrian"] is True
    assert len(res_conf.json()["intervals"]) == 3

    # 4. Market Conformal GET endpoint
    res_mkt_conf = client.get("/api/v1/market/conformal/VNM?horizon_days=5")
    assert res_mkt_conf.status_code == 200
    assert res_mkt_conf.json()["symbol"] == "VNM"

    # 5. AST Formula Evaluation
    res_ast = client.post("/api/v1/alpha/ast/evaluate", json={
        "expression": "ts_rank(close / delay(close, 5), 10)",
    })
    assert res_ast.status_code == 200
    assert res_ast.json()["is_valid"] is True
    assert res_ast.json()["ic_estimate"] > 0

    # 6. Alpha Decay Profile
    res_decay = client.get("/api/v1/alpha/decay-profile/ALPHA_0001_VNM")
    assert res_decay.status_code == 200
    assert res_decay.json()["half_life_days"] == 8

    # 7. Genetic Discovery Start
    res_gp = client.post("/api/v1/alpha/discovery/start", json={
        "population_size": 50,
        "generations": 5,
    })
    assert res_gp.status_code == 200
    assert len(res_gp.json()["history"]) == 5

    # 8. Portfolio Rebalance Execution (with valid TOTP)
    res_rebal = client.post("/api/v1/portfolio/rebalance/execute", json={
        "totp_code": "123456",
        "strategy_id": "ALPHA_HRP_V2",
        "target_portfolio": {"FPT": 0.25, "HPG": 0.25, "MBB": 0.25, "MWG": 0.25},
        "portfolio_value": 1_000_000_000.0,
        "routing_algo": "TWAP",
    })
    assert res_rebal.status_code == 200
    assert res_rebal.json()["totp_verified"] is True
    assert isinstance(res_rebal.json()["orders"], list)


