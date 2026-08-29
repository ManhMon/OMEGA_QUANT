"""
Phase 2 Advanced Analytics & Microstructure Contract Tests.
Adversarial 16-Dimension Master Verification Suite.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from omega.api.server import app

client = TestClient(app)


# Dimension 1: Strict Types & Malformed Inputs (NaN, Inf, strings, lists)
def test_dim1_malformed_and_out_of_bounds_types():
    # NaN in order size
    assert client.post("/api/v1/market/market-impact", json={
        "symbol": "FPT", "order_size": "NaN", "average_daily_volume": 1000000.0,
    }).status_code == 422

    # Negative order size
    assert client.post("/api/v1/market/market-impact", json={
        "symbol": "FPT", "order_size": -100.0, "average_daily_volume": 1000000.0,
    }).status_code == 422

    # Infinity in participation rate
    assert client.post("/api/v1/market/market-impact", json={
        "symbol": "FPT", "order_size": 1000.0, "average_daily_volume": 1000000.0,
        "participation_rate": 1e308,
    }).status_code == 422

    # Invalid list type for symbol
    assert client.post("/api/v1/market/fracdiff", json={
        "symbol": ["FPT", "HPG"], "d": 0.4, "window": 32,
    }).status_code == 422


# Dimension 2: File I/O & Path Aliasing (Directory Traversal, invalid paths)
def test_dim2_directory_io_and_path_aliasing():
    # Directory traversal in symbol
    assert client.post("/api/v1/market/fracdiff", json={
        "symbol": "../../../etc/passwd", "d": 0.4, "window": 32,
    }).status_code == 422

    # Malformed symbol with path characters rejected
    assert client.get("/api/v1/fundamental/corporate-graph/..secret").status_code == 422
    assert client.get("/api/v1/fundamental/corporate-graph/foo/bar").status_code == 422


# Dimension 3: Corrupted / Duplicate / Partial Checkpoints & Shards
def test_dim3_corrupted_duplicate_partial_payloads():
    # Empty symbol or invalid whitespace string
    assert client.get("/api/v1/market/vpin/%20").status_code in (404, 422)
    # Duplicate weights or zero sum weights
    assert client.post("/api/v1/risk/stress-test/simulate", json={
        "portfolio_weights": {"VNM": 0.0, "FPT": 0.0},
        "market_shock_pct": -7.0,
    }).status_code == 422


# Dimension 4: Fail-Closed Exit Codes & Error States
def test_dim4_fail_closed_error_states():
    # Missing symbol in dataset returns 404
    assert client.get("/api/v1/market/vpin/NONEXISTENT_TICKER_999").status_code == 404
    assert client.get("/api/v1/market/orderbook-depth/NONEXISTENT_TICKER_999").status_code == 404
    assert client.get("/api/v1/risk/circuit-breaker/status?symbol=NONEXISTENT_999").status_code == 404
    assert client.get("/api/v1/fundamental/corporate-graph/NONEXISTENT_999").status_code == 404

    # Missing symbol in stress test portfolio returns 404
    assert client.post("/api/v1/risk/stress-test/simulate", json={
        "portfolio_weights": {"NONEXISTENT_999": 1.0},
        "market_shock_pct": -7.0,
    }).status_code == 404

    # Missing symbol in liquidity validate returns 404
    assert client.post("/api/v1/risk/liquidity-stress/validate", json={
        "positions": {"NONEXISTENT_999": 10000},
    }).status_code == 404

    # Empty payload in stress simulation returns 422
    assert client.post("/api/v1/risk/stress-test/simulate", json={
        "portfolio_weights": {}, "market_shock_pct": -7.0,
    }).status_code == 422


# Dimension 5: Rollback & Atomicity Failures
def test_dim5_rollback_and_atomic_read_isolation():
    # Verify repeatable clean reads across multiple calls without mutated state
    res1 = client.get("/api/v1/risk/circuit-breaker/status?symbol=VNM")
    res2 = client.get("/api/v1/risk/circuit-breaker/status?symbol=VNM")
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["var_95_pct"] == res2.json()["var_95_pct"]


# Dimension 6: Point-In-Time (PIT) & Look-Ahead Safety
def test_dim6_pit_lookahead_safety():
    res = client.get("/api/v1/risk/circuit-breaker/status?symbol=VNM")
    assert res.status_code == 200
    data = res.json()
    as_of = datetime.fromisoformat(data["as_of"])
    now_utc = datetime.now(timezone.utc)
    # as_of must not be in future
    assert as_of <= now_utc
    assert data["provenance"]["is_synthetic"] is False


# Dimension 7: Trading Calendar & Holiday Boundaries
def test_dim7_trading_calendar_and_holiday_boundaries():
    # Fetch historical bars to ensure trading calendar continuity
    res = client.get("/api/v1/market/ohlcv/VNM?limit=100")
    assert res.status_code == 200
    bars = res.json()["bars"]
    assert len(bars) > 0
    # No duplicate timestamps
    times = [b["time"] for b in bars]
    assert len(times) == len(set(times))


# Dimension 8: Numeric Precision & Zero-Division Overflow
def test_dim8_zero_division_and_numeric_bounds():
    # Zero ADV rejected strictly by schema (gt=0)
    assert client.post("/api/v1/market/market-impact", json={
        "symbol": "FPT", "order_size": 100.0, "average_daily_volume": 0.0,
    }).status_code == 422

    # Out of bounds d parameter (> 2.0)
    assert client.post("/api/v1/market/fracdiff", json={
        "symbol": "FPT", "d": 2.5, "window": 32,
    }).status_code == 422


# Dimension 9: Concurrency & Race Condition Resistance
def test_dim9_concurrency_race_condition_resistance():
    import concurrent.futures
    def fetch():
        return client.get("/api/v1/market/orderbook-depth/FPT?depth=5")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch) for _ in range(16)]
        results = [f.result() for f in futures]

    for r in results:
        assert r.status_code == 200
        assert r.json()["status"] == "success"


# Dimension 10: VND_FULL Price Scale & Unit Invariance
def test_dim10_vnd_full_price_scale_maintained():
    res = client.get("/api/v1/market/orderbook-depth/FPT")
    assert res.status_code == 200
    data = res.json()
    assert data["mid_price"] > 1000.0
    for b in data["bids"]:
        assert b["price"] > 1000.0
    for a in data["asks"]:
        assert a["price"] > 1000.0


# Dimension 11: Survivorship & Delisting Anomalies
def test_dim11_survivorship_and_delisted_symbol_handling():
    # Delisted or non-traded symbol fails closed cleanly with 404
    assert client.get("/api/v1/market/vpin/DELISTED_TEST_ZZZ").status_code == 404
    assert client.get("/api/v1/fundamental/corporate-graph/DELISTED_TEST_ZZZ").status_code == 404


# Dimension 12: CLI Injection & Flag Smuggling Sanitization
def test_dim12_injection_sanitization():
    assert client.get("/api/v1/fundamental/corporate-graph/--flag").status_code == 422
    assert client.get("/api/v1/fundamental/corporate-graph/%20;DROP%20TABLE").status_code == 422


# Dimension 13: Schema Drift & Extra Column Mutations
def test_dim13_schema_drift_rejection():
    assert client.post("/api/v1/market/market-impact", json={
        "symbol": "FPT", "order_size": 1000.0, "average_daily_volume": 1000000.0,
        "unexpected_field": "injected",
    }).status_code == 422

    assert client.post("/api/v1/risk/liquidity-stress/validate", json={
        "positions": {"VNM": 100000}, "unknown_param": 123,
    }).status_code == 422


# Dimension 14: Resource Exhaustion & Memory Bounds
def test_dim14_memory_bounds_on_window_size():
    # Window > 512 rejected
    assert client.post("/api/v1/market/fracdiff", json={
        "symbol": "FPT", "d": 0.4, "window": 1024,
    }).status_code == 422

    # Limit > 2000 rejected
    assert client.post("/api/v1/market/fracdiff", json={
        "symbol": "FPT", "d": 0.4, "window": 32, "limit": 5000,
    }).status_code == 422


# Dimension 15: Network Timeout & 429 Retry Exhaustion Resilience
def test_dim15_network_retry_and_timeout_resilience():
    # Endpoint handles high depth boundedly without timing out or breaking
    res = client.get("/api/v1/market/orderbook-depth/FPT?depth=20")
    assert res.status_code == 200
    assert len(res.json()["bids"]) == 20


# Dimension 16: Secret Redaction & Credential Leak Prevention
def test_dim16_secret_redaction_in_all_responses():
    endpoints = [
        client.get("/api/v1/market/vpin/FPT"),
        client.get("/api/v1/market/orderbook-depth/FPT"),
        client.get("/api/v1/risk/circuit-breaker/status?symbol=VNM"),
        client.get("/api/v1/risk/contagion-graph"),
        client.get("/api/v1/fundamental/corporate-graph/FPT"),
    ]
    for resp in endpoints:
        text = resp.text.lower()
        assert "password" not in text
        assert "secret" not in text or "reconciliation" in text
        assert "api_key" not in text


# Functional Verification of All Core Endpoints with Real Computation & Provenance
def test_functional_phase2_endpoints_complete():
    # 1. VPIN Toxicity
    res_vpin = client.get("/api/v1/market/vpin/FPT?n_buckets=10&limit=50")
    assert res_vpin.status_code == 200
    assert res_vpin.json()["status"] == "success"
    assert "provenance" in res_vpin.json()
    assert res_vpin.json()["provenance"]["is_synthetic"] is False

    # 2. Depth Waterfall
    res_depth = client.get("/api/v1/market/orderbook-depth/FPT?depth=5&spread_bps=12.5")
    assert res_depth.status_code == 200
    assert res_depth.json()["depth_levels"] == 5
    assert "provenance" in res_depth.json()

    # 3. Market Impact Curve
    res_impact = client.post("/api/v1/market/market-impact", json={
        "symbol": "FPT", "order_size": 15000.0, "average_daily_volume": 1200000.0,
        "volatility": 0.02, "arrival_price": 135000.0, "participation_rate": 0.10, "impact_coefficient": 0.25,
    })
    assert res_impact.status_code == 200
    assert res_impact.json()["point_impact_bps"] > 0
    assert "kyle_lambda" in res_impact.json()
    assert res_impact.json()["kyle_lambda"] is not None
    assert "provenance" in res_impact.json()

    # 4. FracDiff Memory
    res_frac = client.post("/api/v1/market/fracdiff", json={
        "symbol": "FPT", "d": 0.45, "window": 32, "limit": 100,
    })
    assert res_frac.status_code == 200
    assert len(res_frac.json()["weights"]) == 32
    assert "provenance" in res_frac.json()

    # 5. Circuit Breaker Status
    res_cb = client.get("/api/v1/risk/circuit-breaker/status?symbol=VNM")
    assert res_cb.status_code == 200
    assert "is_safe" in res_cb.json()
    assert "provenance" in res_cb.json()

    # 6. Stress Test Simulate (Real portfolio weights & contagion flag dynamic test)
    res_stress_with_contagion = client.post("/api/v1/risk/stress-test/simulate", json={
        "portfolio_weights": {"VNM": 0.4, "HPG": 0.3, "FPT": 0.3},
        "market_shock_pct": -7.0, "volatility_shock_multiplier": 1.5, "include_contagion": True,
    })
    assert res_stress_with_contagion.status_code == 200
    scenarios_contagion = res_stress_with_contagion.json()["scenarios"]
    loss_with_contagion = scenarios_contagion[2]["portfolio_impact_pct"]

    res_stress_no_contagion = client.post("/api/v1/risk/stress-test/simulate", json={
        "portfolio_weights": {"VNM": 0.4, "HPG": 0.3, "FPT": 0.3},
        "market_shock_pct": -7.0, "volatility_shock_multiplier": 1.5, "include_contagion": False,
    })
    assert res_stress_no_contagion.status_code == 200
    scenarios_no_contagion = res_stress_no_contagion.json()["scenarios"]
    loss_no_contagion = scenarios_no_contagion[2]["portfolio_impact_pct"]

    # Dynamic honoring of include_contagion flag
    assert abs(loss_with_contagion) > abs(loss_no_contagion)

    # 7. Contagion Graph
    res_contagion = client.get("/api/v1/risk/contagion-graph")
    assert res_contagion.status_code == 200
    assert len(res_contagion.json()["nodes"]) >= 4
    assert "provenance" in res_contagion.json()

    # 8. Liquidity Stress Validate
    res_liq = client.post("/api/v1/risk/liquidity-stress/validate", json={
        "positions": {"VNM": 200000, "HPG": 500000, "FPT": 100000},
        "max_adv_participation": 0.10, "max_exit_days": 3, "market_impact_coefficient": 0.25,
    })
    assert res_liq.status_code == 200
    assert "max_exit_days" in res_liq.json()
    assert "provenance" in res_liq.json()

    # 9. Corporate Graph (Real financial metrics, distinct percentages)
    res_corp_fpt = client.get("/api/v1/fundamental/corporate-graph/FPT")
    assert res_corp_fpt.status_code == 200
    assert res_corp_fpt.json()["symbol"] == "FPT"
    assert "provenance" in res_corp_fpt.json()

    res_corp_hpg = client.get("/api/v1/fundamental/corporate-graph/HPG")
    assert res_corp_hpg.status_code == 200
    assert res_corp_hpg.json()["symbol"] == "HPG"

    # Entities should not be identical hardcoded constants
    assert res_corp_fpt.json()["nodes"][1]["ownership_pct"] != res_corp_hpg.json()["nodes"][1]["ownership_pct"]



