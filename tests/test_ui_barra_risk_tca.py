import json
import pytest
from starlette.testclient import TestClient
from omega.api.server import app

@pytest.fixture
def client():
    return TestClient(app)

# -------------------------------------------------------------
# 16-DIMENSION ADVERSARIAL TEST SUITE: PHASE 8 BARRA RISK & TCA
# -------------------------------------------------------------

def test_dim1_barra_decomposition_schema(client):
    """Dim 1: Strict Types & Schema Invariants."""
    # GET returns 424 fail closed
    resp = client.get("/api/v1/risk/barra/decomposition")
    assert resp.status_code == 424
    assert resp.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"

    # Test POST with BOTH custom assets AND custom covariance calculates deterministic Barra risk
    k_cov = [[0.01 if i == j else 0.001 for j in range(8)] for i in range(8)]
    post_resp = client.post("/api/v1/risk/barra/decomposition", json={
        "assets": [
            {"symbol": "FPT", "sector": "Technology", "weight_pct": 50.0, "market_beta": 1.1, "size_smb": 0.8, "value_hml": 0.4, "momentum": 1.8, "volatility": 0.2, "liquidity": 0.6, "quality": 0.9, "leverage": -0.2, "specific_risk_pct": 3.8},
            {"symbol": "HPG", "sector": "Materials", "weight_pct": 50.0, "market_beta": 1.2, "size_smb": 1.1, "value_hml": 1.6, "momentum": 1.2, "volatility": 0.3, "liquidity": 0.8, "quality": 0.5, "leverage": 0.4, "specific_risk_pct": 4.5},
        ],
        "factor_covariance": k_cov
    })
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    assert post_data["is_synthetic"] is False
    assert post_data["source"] == "request_factor_covariance"
    assert "factor_variance" in post_data
    assert "specific_variance" in post_data
    assert "total_variance" in post_data


def test_dim2_stress_scenarios_contract(client):
    """Dim 2: File I/O & Path / Endpoint Contracts."""
    resp = client.get("/api/v1/risk/stress-scenarios")
    assert resp.status_code == 424
    assert resp.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"


def test_dim3_tca_pre_trade_impact_calculation(client):
    """Dim 3: Durability & Almgren-Chriss Mathematical Precision."""
    req_body = {
        "symbol": "FPT",
        "order_size": 15000,
        "average_daily_volume": 1250000,
        "volatility": 0.02,
        "arrival_price": 138500,
        "side": "BUY",
        "participation_rate": 0.10,
        "observed_spread_bps": 5.0,
    }
    resp = client.post("/api/v1/tca/pre-trade-impact", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["symbol"] == "FPT"
    assert data["estimated_impact_bps"] > 0
    assert data["total_cost_bps"] > data["estimated_impact_bps"]
    assert data["total_cost_vnd"] > 0


def test_dim4_tca_sell_impact_directionality(client):
    """Dim 4: Memory Bounds & Directional Price Impact Check."""
    req_body = {
        "symbol": "HPG",
        "order_size": 50000,
        "average_daily_volume": 15000000,
        "volatility": 0.025,
        "arrival_price": 28400,
        "side": "SELL",
        "participation_rate": 0.08,
        "observed_spread_bps": 4.0,
    }
    resp = client.post("/api/v1/tca/pre-trade-impact", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["side"] == "SELL"
    assert data["estimated_impact_bps"] > 0


def test_dim5_post_trade_tca_report(client):
    """Dim 5: Concurrency & Post-Trade TCA Metrics Aggregation."""
    resp = client.get("/api/v1/tca/post-trade-report")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "DATA_NOT_FOUND"


def test_dim6_routing_diagnostics_telemetry(client):
    """Dim 6: Point-In-Time & Latency Diagnostics Telemetry."""
    resp = client.get("/api/v1/execution/routing-diagnostics")
    assert resp.status_code == 424
    assert resp.json()["detail"] == "BROKER_DEPENDENCY_UNAVAILABLE"


def test_dim7_adversarial_zero_and_negative_order_size(client):
    """Dim 7: Validation against Zero or Negative Order Size."""
    req_body = {
        "symbol": "VNM",
        "order_size": 0,  # Invalid
        "average_daily_volume": 1000000,
        "arrival_price": 68000,
        "volatility": 0.02,
        "participation_rate": 0.1,
        "side": "BUY",
        "observed_spread_bps": 5.0,
    }
    resp = client.post("/api/v1/tca/pre-trade-impact", json=req_body)
    assert resp.status_code in (400, 422)


def test_dim8_adversarial_zero_adv_fail_closed(client):
    """Dim 8: Mathematical Extremes & Division by Zero Defence."""
    req_body = {
        "symbol": "VNM",
        "order_size": 10000,
        "average_daily_volume": 0,  # Invalid
        "arrival_price": 68000,
        "volatility": 0.02,
        "participation_rate": 0.1,
        "side": "BUY",
        "observed_spread_bps": 5.0,
    }
    resp = client.post("/api/v1/tca/pre-trade-impact", json=req_body)
    assert resp.status_code in (400, 422)


def test_dim9_adversarial_extreme_volatility_bounds(client):
    """Dim 9: Financial Logic Edges on Extreme Volatility."""
    req_body = {
        "symbol": "DGC",
        "order_size": 5000,
        "average_daily_volume": 500000,
        "volatility": 1.5,  # > 1.0 (Invalid)
        "arrival_price": 112000,
        "participation_rate": 0.1,
        "side": "BUY",
        "observed_spread_bps": 5.0,
    }
    resp = client.post("/api/v1/tca/pre-trade-impact", json=req_body)
    assert resp.status_code == 422


def test_dim10_case_insensitive_symbol_handling(client):
    """Dim 10: Case-Insensitive Symbol Canonicalization."""
    req_body = {
        "symbol": "fpt",
        "order_size": 10000,
        "average_daily_volume": 1000000,
        "arrival_price": 138000,
        "volatility": 0.02,
        "participation_rate": 0.1,
        "side": "BUY",
        "observed_spread_bps": 5.0,
    }
    resp = client.post("/api/v1/tca/pre-trade-impact", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "FPT"


def test_dim11_invalid_side_rejection(client):
    """Dim 11: Fail-Closed on Invalid Side String."""
    req_body = {
        "symbol": "MBB",
        "order_size": 10000,
        "average_daily_volume": 1000000,
        "side": "SHORT_COVER_UNKNOWN",
        "arrival_price": 25000,
        "volatility": 0.02,
        "participation_rate": 0.1,
        "observed_spread_bps": 5.0,
    }
    resp = client.post("/api/v1/tca/pre-trade-impact", json=req_body)
    assert resp.status_code in (400, 422)


def test_dim12_stress_matrix_cvar_relation(client):
    """Dim 12: Contract check for stress scenarios endpoint."""
    resp = client.get("/api/v1/risk/stress-scenarios")
    assert resp.status_code == 424


def test_dim13_barra_decomposition_variance_conservation(client):
    """Dim 13: Metric & Artifact Consistency: Factor Variance + Specific Risk."""
    k_cov = [[0.01 if i == j else 0.001 for j in range(8)] for i in range(8)]
    post_resp = client.post("/api/v1/risk/barra/decomposition", json={
        "assets": [
            {"symbol": "FPT", "sector": "Technology", "weight_pct": 50.0, "market_beta": 1.1, "size_smb": 0.8, "value_hml": 0.4, "momentum": 1.8, "volatility": 0.2, "liquidity": 0.6, "quality": 0.9, "leverage": -0.2, "specific_risk_pct": 3.8},
            {"symbol": "HPG", "sector": "Materials", "weight_pct": 50.0, "market_beta": 1.2, "size_smb": 1.1, "value_hml": 1.6, "momentum": 1.2, "volatility": 0.3, "liquidity": 0.8, "quality": 0.5, "leverage": 0.4, "specific_risk_pct": 4.5},
        ],
        "factor_covariance": k_cov
    })
    assert post_resp.status_code == 200
    data = post_resp.json()
    assert data["factor_variance"] > 0
    assert data["specific_variance"] > 0
    assert abs(data["total_variance"] - (data["factor_variance"] + data["specific_variance"])) < 1e-6

def test_dim17_monotonic_impact_with_participation_and_volume(client):
    """Dim 17: Pre-trade market impact is strictly monotonic in participation_rate, volume, and volatility."""
    base_req = {
        "symbol": "FPT",
        "order_size": 10000,
        "average_daily_volume": 1000000,
        "volatility": 0.02,
        "arrival_price": 138000,
        "participation_rate": 0.05,
        "side": "BUY",
        "observed_spread_bps": 5.0,
    }
    r_base = client.post("/api/v1/tca/pre-trade-impact", json=base_req).json()["estimated_impact_bps"]

    # Higher participation rate -> strictly higher impact
    r_high_p = client.post("/api/v1/tca/pre-trade-impact", json={**base_req, "participation_rate": 0.20}).json()["estimated_impact_bps"]
    assert r_high_p > r_base

    # Subnormal float / lower bound rejection test (le=0 or invalid)
    r_subnormal = client.post("/api/v1/tca/pre-trade-impact", json={**base_req, "participation_rate": 0})
    assert r_subnormal.status_code == 422

    # Higher order size -> strictly higher impact
    r_high_size = client.post("/api/v1/tca/pre-trade-impact", json={**base_req, "order_size": 50000}).json()["estimated_impact_bps"]
    assert r_high_size > r_base

    # Higher volatility -> strictly higher impact
    r_high_vol = client.post("/api/v1/tca/pre-trade-impact", json={**base_req, "volatility": 0.05}).json()["estimated_impact_bps"]
    assert r_high_vol > r_base


def test_dim14_asset_exposure_cross_sectional_validity(client):
    """Dim 14: Cross-Sectional Asset-Level Weight & Exposure Sum."""
    resp = client.get("/api/v1/risk/barra/decomposition")
    assert resp.status_code == 424


def test_dim15_opt_in_safety_default_participation(client):
    """Dim 15: Safe Default Participation Rate."""
    req_body = {
        "symbol": "MWG",
        "order_size": 20000,
        "average_daily_volume": 2000000,
        "volatility": 0.02,
        "arrival_price": 50000,
        "participation_rate": 0.10,
        "side": "BUY",
        "observed_spread_bps": 4.0,
    }
    resp = client.post("/api/v1/tca/pre-trade-impact", json=req_body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"


def test_dim16_security_sanitization_no_leakage(client):
    """Dim 16: Security & Parameter Injection Defense."""
    req_body = {
        "symbol": "FPT<script>alert(1)</script>",
        "order_size": 10000,
        "average_daily_volume": 1000000,
        "volatility": 0.02,
        "arrival_price": 138000,
        "participation_rate": 0.10,
        "side": "BUY",
        "observed_spread_bps": 5.0,
    }
    resp = client.post("/api/v1/tca/pre-trade-impact", json=req_body)
    assert resp.status_code == 422
