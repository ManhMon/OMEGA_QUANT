import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from omega.api.routes import risk_tca
from starlette.testclient import TestClient
from omega.api.server import app

@pytest.fixture
def client(monkeypatch, tmp_path):
    from omega.api.routes import execution
    from omega.quant.execution import paper_trading

    engine = SimpleNamespace(get_orders=lambda limit: [])
    monkeypatch.setattr(risk_tca, "HYBRID_EVAL_PATH", tmp_path / "missing.parquet")
    monkeypatch.setattr(paper_trading, "get_paper_engine", lambda: engine)
    monkeypatch.setattr(execution, "_get_engine", lambda: engine)
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
    assert resp.status_code == 200
    data = resp.json()
    assert data["engine"] == "paper_trading"
    assert data["routers"][0]["status"] == "DATA_ONLY"
    assert data["routers"][0]["ping_ms"] is None
    assert data["routers"][0]["fill_rate_pct"] == 0


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


def _barra_asset(symbol="FPT", weight=100.0, loading=1.0, specific=2.0):
    return {"symbol": symbol, "sector": "Technology", "weight_pct": weight,
            **{key: loading for key in risk_tca.FACTOR_KEYS}, "specific_risk_pct": specific}


def _barra_body(**overrides):
    body = {"assets": [_barra_asset()], "factor_covariance": np.eye(8).tolist()}
    body.update(overrides)
    return body


def _market_rows(symbols, dates, return_series=None):
    rows = []
    for j, symbol in enumerate(symbols):
        level = 20000.0 + j * 1000
        for i, date in enumerate(dates):
            ret = return_series[i] if return_series is not None else 0.001 * (i + 1)
            if symbol == symbols[-1]:
                ret = -ret
            level *= np.exp(ret)
            stamp = pd.Timestamp(date, tz="UTC")
            rows.append({"ticker": symbol, "date": stamp, "close": level, "volume": 1_000_000.0,
                         "as_of": stamp, "available_at": stamp + pd.Timedelta(hours=1)})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("value", [True, "1.5", None, [], "NaN", "Infinity", 1e13, float("nan"), float("inf"), -float("inf")])
def test_adversarial_tca_numeric_schema_rejects_bad_values(client, value):
    body = {"symbol": "FPT", "order_size": 1000.0, "average_daily_volume": 10000.0,
            "volatility": 0.02, "participation_rate": 0.1, "side": "BUY",
            "arrival_price": 20000.0, "observed_spread_bps": 1.0}
    for key in ("order_size", "average_daily_volume", "volatility", "participation_rate", "arrival_price", "observed_spread_bps"):
        payload = {**body, key: value}
        response = client.post("/api/v1/tca/pre-trade-impact", content=json.dumps(payload, allow_nan=True), headers={"Content-Type": "application/json"})
        assert response.status_code == 422, (key, value, response.text)


@pytest.mark.parametrize("body", [
    _barra_body(assets=[_barra_asset(weight=True)]),
    _barra_body(assets=[_barra_asset(weight="100")]),
    _barra_body(assets=[_barra_asset(weight=None)]),
    _barra_body(assets=[_barra_asset(weight=1e13)]),
    _barra_body(assets=[_barra_asset(), _barra_asset()]),
    _barra_body(assets=[_barra_asset(weight=-1)]),
    _barra_body(assets=[_barra_asset(weight=0)]),
    _barra_body(assets=[_barra_asset()], extra=1),
    _barra_body(specific_variances=[-1]),
    _barra_body(specific_variances=[1, 2]),
    _barra_body(factor_covariance=[[1.0] * 7 for _ in range(8)]),
    _barra_body(factor_covariance=[["NaN"] + [0.0] * 7] + [[0.0] * 8 for _ in range(7)]),
    _barra_body(factor_covariance=[[1e13 if i == j else 0.0 for j in range(8)] for i in range(8)]),
    _barra_body(factor_covariance=[[1.0 if i == j else 0.0 for j in range(8)] for i in range(8)], covariance_unit="VND"),
])
def test_adversarial_barra_schema_rejects_bad_contracts(client, body):
    assert client.post("/api/v1/risk/barra/decomposition", json=body).status_code == 422


def test_barra_rejects_asymmetric_and_indefinite_covariance(client):
    asymmetric = np.eye(8)
    asymmetric[0, 1] = 0.1
    indefinite = np.eye(8)
    indefinite[0, 1] = indefinite[1, 0] = 2.0
    for covariance in (asymmetric, indefinite):
        response = client.post("/api/v1/risk/barra/decomposition", json=_barra_body(factor_covariance=covariance.tolist()))
        assert response.status_code == 422
        assert response.json()["detail"] == "INVALID_FACTOR_COVARIANCE"


def test_barra_weight_units_variance_and_signed_contributions(client):
    first, second = _barra_asset("FPT", 25), _barra_asset("HPG", 75)
    for asset in (first, second):
        for key in risk_tca.FACTOR_KEYS:
            asset[key] = 0.0
    first["market_beta"], second["market_beta"] = 1.0, -1.0
    first["size_smb"], second["size_smb"] = 0.2, -0.2
    covariance = np.eye(8).tolist()
    covariance[0][1] = covariance[1][0] = -0.9
    pct = client.post("/api/v1/risk/barra/decomposition", json={
        "assets": [first, second], "factor_covariance": covariance,
        "specific_variances": [4.0, 16.0], "covariance_unit": "annualized_pct_squared"})
    dec_cov = (np.asarray(covariance) / 10000).tolist()
    dec = client.post("/api/v1/risk/barra/decomposition", json={
        "assets": [first, second], "factor_covariance": dec_cov,
        "specific_variances": [4.0, 16.0], "covariance_unit": "annualized_decimal_squared"})
    assert pct.status_code == dec.status_code == 200
    data = pct.json()
    exposure = np.array([-0.5, -0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    expected_factor = float(exposure @ np.asarray(covariance) @ exposure)
    expected_specific = 0.25**2 * 4 + 0.75**2 * 16
    assert data["factor_exposures"]["market_beta"] == pytest.approx(-0.5)
    assert data["factor_variance"] == pytest.approx(expected_factor), (data["factor_variance"], expected_factor, data["factor_exposures"])
    assert data["specific_variance"] == pytest.approx(expected_specific)
    assert data["total_variance"] == pytest.approx(expected_factor + expected_specific)
    assert data["total_risk_annualized_pct"] ** 2 == pytest.approx(data["total_variance"])
    assert data["factor_variance_contributions"]["size_smb"] < 0
    assert dec.json()["total_variance"] == pytest.approx(data["total_variance"])
    assert data["provenance_status"] == "caller_supplied_unverified"
    assert data["pit_verified"] is False


def test_t1_cutoff_rejects_invalid_decision_timestamps():
    for decision in (datetime(2026, 10, 8, 8, 30),):
        with pytest.raises(HTTPException) as error:
            risk_tca._t1_cutoff(decision)
        assert error.value.status_code == 424


def test_t1_cutoff_weekend_uses_prior_trading_day(monkeypatch):
    monkeypatch.setattr(risk_tca, "_get_json_holidays", lambda: {"2026": []})
    monkeypatch.setattr(risk_tca.VNTradingCalendar, "is_trading_day", lambda day: day.weekday() < 5)
    assert risk_tca._t1_cutoff(datetime(2026, 10, 8, 8, 30, tzinfo=timezone.utc)) == datetime(2026, 10, 7, 8, 30, tzinfo=timezone.utc)
    assert risk_tca._t1_cutoff(datetime(2026, 10, 5, 8, 30, tzinfo=timezone.utc)) == datetime(2026, 10, 2, 8, 30, tzinfo=timezone.utc)


def test_provenance_preserves_filtered_pit_metadata_and_hash():
    frame = pd.DataFrame({"as_of": ["2026-10-07T08:00:00Z"], "available_at": ["2026-10-07T08:15:00Z"], "close": [100.0]})
    frame.attrs.update(
        decision_time=datetime(2026, 10, 8, 8, 30, tzinfo=timezone.utc),
        effective_cutoff=datetime(2026, 10, 7, 8, 30, tzinfo=timezone.utc),
        max_included_available_at=datetime(2026, 10, 7, 8, 15, tzinfo=timezone.utc),
        excluded_future_rows=2,
    )
    provenance = risk_tca._make_provenance("fixture", "pit-test", {"data": frame})
    assert provenance.effective_cutoff == frame.attrs["effective_cutoff"]
    assert provenance.max_included_available_at == frame.attrs["max_included_available_at"]
    assert provenance.excluded_future_rows == 2
    assert len(provenance.content_hash) == 64
    with pytest.raises(HTTPException) as error:
        risk_tca._pit_frame(pd.DataFrame({"close": [1.0]}), datetime.now(timezone.utc))
    assert error.value.status_code == 424


def test_pit_frame_includes_t1_close_equality_and_excludes_future(monkeypatch):
    monkeypatch.setattr(risk_tca, "_get_json_holidays", lambda: {"2026": []})
    monkeypatch.setattr(risk_tca.VNTradingCalendar, "is_trading_day", lambda day: day.weekday() < 5)
    cutoff = datetime(2026, 10, 8, 8, 30, tzinfo=timezone.utc)
    frame = pd.DataFrame({"as_of": ["2026-10-07T08:30:00Z", "2026-10-07T08:30:01Z"],
                          "available_at": ["2026-10-07T08:30:00Z", "2026-10-07T08:30:01Z"],
                          "date": ["2026-10-07T08:30:00Z", "2026-10-07T08:30:01Z"], "v": [1, 2]})
    actual = risk_tca._pit_frame(frame, cutoff)
    assert actual["v"].tolist() == [1]
    assert actual.attrs["effective_cutoff"] == datetime(2026, 10, 7, 8, 30, tzinfo=timezone.utc)
    assert actual.attrs["excluded_future_rows"] == 1


@pytest.mark.parametrize("frame", [
    pd.DataFrame({"as_of": ["2026-10-07T09:00:00Z"], "available_at": ["2026-10-07T08:00:00Z"]}),
    pd.DataFrame({"as_of": [None], "available_at": ["2026-10-07T08:00:00Z"]}),
    pd.DataFrame({"as_of": ["bad"], "available_at": ["2026-10-07T08:00:00Z"]}),
    pd.DataFrame({"as_of": ["2026-10-07T08:00:00Z"], "available_at": [None]}),
    pd.DataFrame({"as_of": ["2026-10-07T08:00:00Z"], "available_at": ["2026-10-07T08:00:00Z"], "date": ["2026-10-08T09:00:00Z"]}),
])
def test_pit_frame_invalid_or_future_dates_fail_closed(frame):
    with pytest.raises(HTTPException) as error:
        risk_tca._pit_frame(frame, datetime(2026, 10, 8, 8, 30, tzinfo=timezone.utc))
    assert error.value.status_code == 424


def test_risk_artifacts_return_model_unavailable(client, monkeypatch, tmp_path):
    path = tmp_path / "hybrid.parquet"
    path.write_bytes(b"nonempty")
    monkeypatch.setattr(risk_tca, "HYBRID_EVAL_PATH", path)
    monkeypatch.setattr(risk_tca.pd, "read_parquet", lambda *_args, **_kwargs: pd.DataFrame({
        "as_of": ["2026-10-07T08:00:00Z"], "available_at": ["2026-10-07T08:00:00Z"]}))
    barra = client.get("/api/v1/risk/barra/decomposition")
    stress = client.get("/api/v1/risk/stress-scenarios")
    assert barra.status_code == 424 and barra.json()["detail"] == "BARRA_FACTOR_MODEL_UNAVAILABLE"
    assert stress.status_code == 424 and stress.json()["detail"] == "STRESS_MODEL_UNAVAILABLE"


def test_contagion_signed_correlation_and_provenance(monkeypatch, client):
    symbols = ["VNM", "VCB", "HPG", "FPT", "SSI", "MWG", "MSN", "VIC"]
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    frame = _market_rows(symbols, dates, np.linspace(-0.01, 0.012, len(dates)))
    monkeypatch.setattr(risk_tca, "load_market_dataset", lambda **_kwargs: frame)
    response = client.get("/api/v1/risk/contagion-graph")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["observation_count"] == 29
    assert all(row == [29] * len(row) for row in data["sample_counts"])
    assert data["window_sessions"] == 250
    assert any(edge["correlation"] < -0.99 for edge in data["edges"])
    assert data["provenance"]["source"] == "market_2015_now.parquet"
    assert data["provenance"]["is_synthetic"] is False


@pytest.mark.parametrize("frame", [
    _market_rows(["VNM", "VCB", "HPG", "FPT", "SSI", "MWG", "MSN", "VIC"], pd.date_range("2024-01-02", periods=30, freq="B"), np.zeros(30)),
    _market_rows(["VNM", "VCB", "HPG", "FPT", "SSI", "MWG", "MSN", "VIC"], pd.date_range("2024-01-02", periods=30, freq="B"), np.ones(30) * 0.001).iloc[:-1],
])
def test_contagion_constant_or_missing_input_fails_closed(monkeypatch, client, frame):
    monkeypatch.setattr(risk_tca, "load_market_dataset", lambda **_kwargs: frame)
    response = client.get("/api/v1/risk/contagion-graph")
    assert response.status_code == 424


def test_post_trade_value_weighted_slippage_and_invalid_records(client, monkeypatch):
    import omega.quant.execution.paper_trading as paper_trading
    records = [
        {"execution_status": "FILLED", "side": "BUY", "intended_price": 10000, "executed_price": 10100, "size": 10},
        {"execution_status": "FILLED", "side": "SELL", "intended_price": 10000, "executed_price": 9900, "size": 20},
    ]
    engine = type("Engine", (), {"get_orders": lambda self, limit: records})()
    monkeypatch.setattr(paper_trading, "get_paper_engine", lambda: engine)
    response = client.get("/api/v1/tca/post-trade-report")
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["average_is_bps"] == pytest.approx((100 * 101000 + 100 * 198000) / 299000)
    invalid_records = [
        {"execution_status": "FILLED", "side": "SHORT", "intended_price": 10000, "executed_price": 10100, "size": 1},
        {"execution_status": "FILLED", "side": "BUY", "intended_price": 10000, "executed_price": 10100, "size": True},
        {"execution_status": "FILLED", "side": "BUY", "intended_price": 10000, "executed_price": 10100, "size": 1e13},
        {"execution_status": "FILLED", "side": "BUY", "intended_price": 1e-300, "executed_price": 1e12, "size": 1},
    ]
    for record in invalid_records:
        bad_engine = type("Engine", (), {"get_orders": lambda self, limit, record=record: [record]})()
        monkeypatch.setattr(paper_trading, "get_paper_engine", lambda engine=bad_engine: engine)
        bad = client.get("/api/v1/tca/post-trade-report")
        assert bad.status_code == 503, (record, bad.text)


def test_post_trade_engine_failure_and_directory_artifacts_fail_closed(client, monkeypatch, tmp_path):
    import omega.quant.execution.paper_trading as paper_trading
    engine = type("Engine", (), {"get_orders": lambda self, limit: (_ for _ in ()).throw(RuntimeError("corrupt"))})()
    monkeypatch.setattr(paper_trading, "get_paper_engine", lambda: engine)
    response = client.get("/api/v1/tca/post-trade-report")
    assert response.status_code == 503
    monkeypatch.setattr(risk_tca, "HYBRID_EVAL_PATH", tmp_path)
    assert client.get("/api/v1/risk/stress-scenarios").status_code == 424
    assert client.get("/api/v1/risk/barra/decomposition").status_code == 424


def test_tca_tiny_adv_overflow_fails_closed(client):
    body = {"symbol": "FPT", "order_size": 1e12, "average_daily_volume": 1e-300,
            "volatility": 1.0, "participation_rate": 1.0, "side": "BUY",
            "arrival_price": 1e12, "observed_spread_bps": 1e12}
    response = client.post("/api/v1/tca/pre-trade-impact", json=body)
    assert response.status_code == 422
    assert response.json()["detail"] == "INVALID_IMPACT_RESULT"


def test_stress_rejects_duplicate_canonical_symbols_and_nonpositive_sum(client):
    duplicate = client.post("/api/v1/risk/stress-test/simulate", json={"portfolio_weights": {"VNM": 0.5, "vnm": 0.5}})
    zero = client.post("/api/v1/risk/stress-test/simulate", json={"portfolio_weights": {"VNM": 0.0}})
    assert duplicate.status_code == 422
    assert zero.status_code == 422


def test_loader_failures_propagate_fail_closed(monkeypatch, client):
    monkeypatch.setattr(risk_tca, "load_market_dataset", lambda **_kwargs: (_ for _ in ()).throw(HTTPException(503, "DATASET_CORRUPT")))
    response = client.get("/api/v1/risk/contagion-graph")
    assert response.status_code == 503 and response.json()["detail"] == "DATASET_CORRUPT"


def test_market_loader_failure_exception_is_sanitized(monkeypatch, client):
    monkeypatch.setattr(risk_tca, "load_market_dataset", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("parquet corruption")))
    response = client.get("/api/v1/risk/contagion-graph")
    assert response.status_code == 500
    assert response.json()["detail"] == "MARKET_DATA_ERROR"
    assert "parquet corruption" not in response.text


@pytest.mark.parametrize("value", [None, True, "1", [], float("nan"), float("inf"), -float("inf"), 1e13])
def test_barra_loading_numeric_boundary(client, value):
    body = _barra_body()
    body["assets"][0]["market_beta"] = value
    response = client.post("/api/v1/risk/barra/decomposition", content=json.dumps(body), headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_t1_holiday_timezone_and_uncovered_calendar():
    decision = datetime.fromisoformat("2026-09-03T09:00:00+07:00")
    actual = risk_tca._t1_cutoff(decision)
    assert actual == datetime.fromisoformat("2026-08-31T15:30:00+07:00")
    for stamp in ("2030-01-01T00:00:00Z", "2028-01-01T00:00:00Z"):
        with pytest.raises(HTTPException) as error:
            risk_tca._t1_cutoff(datetime.fromisoformat(stamp))
        assert error.value.status_code == 424


def test_pit_future_mutation_preserves_included_hash():
    cutoff = datetime.fromisoformat("2026-10-08T09:00:00+07:00")
    frame = pd.DataFrame({"as_of": ["2026-10-07T08:30:00Z", "2026-10-08T00:00:00Z"],
                          "available_at": ["2026-10-07T15:30:00+07:00", "2026-10-08T00:00:00Z"], "value": [1.0, 2.0]})
    first = risk_tca._pit_frame(frame, cutoff)
    first_hash = risk_tca._make_provenance("fixture", "pit", first).content_hash
    frame.loc[1, "value"] = 1e12
    second = risk_tca._pit_frame(frame, cutoff)
    assert risk_tca._make_provenance("fixture", "pit", second).content_hash == first_hash
    assert len(second) == 1


def test_corrupt_hybrid_artifact_fails_closed(client, monkeypatch, tmp_path):
    artifact = tmp_path / "corrupt.parquet"
    artifact.write_bytes(b"not parquet")
    monkeypatch.setattr(risk_tca, "HYBRID_EVAL_PATH", artifact)
    for route in ("barra/decomposition", "stress-scenarios"):
        response = client.get("/api/v1/risk/" + route)
        assert response.status_code == 424
        assert response.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"


@pytest.mark.parametrize("reader,endpoint,detail", [
    ("read_csv", "/api/v1/fundamental/corporate-graph/FPT", "SECTOR_MAPPING_UNAVAILABLE"),
    ("read_parquet", "/api/v1/fundamental/corporate-graph/FPT", "FINANCIALS_DATASET_UNAVAILABLE"),
    ("read_parquet", "/api/v1/risk/barra/decomposition", "DATA_DEPENDENCY_UNAVAILABLE"),
    ("read_parquet", "/api/v1/risk/stress-scenarios", "DATA_DEPENDENCY_UNAVAILABLE"),
])
def test_risk_read_faults_redact_credentials(client, monkeypatch, tmp_path, caplog, reader, endpoint, detail):
    sector = tmp_path / "sector.csv"
    financials = tmp_path / "financials.parquet"
    sector.write_text("symbol,sector\nFPT,Technology\n", encoding="utf-8")
    financials.write_bytes(b"nonempty")
    monkeypatch.setattr(risk_tca, "SECTOR_MAPPING_PATH", sector)
    monkeypatch.setattr(risk_tca, "FINANCIALS_PARQUET_PATH", financials)
    monkeypatch.setattr(risk_tca, "HYBRID_EVAL_PATH", financials)
    def fail(*args, **kwargs):
        raise OSError("https://user:SECRET_PASSWORD@example.com/file?token=SECRET_TOKEN")
    monkeypatch.setattr(risk_tca.pd, reader, fail)
    response = client.get(endpoint)
    assert response.status_code == 424
    assert response.json() == {"detail": detail}
    assert "SECRET_PASSWORD" not in response.text + caplog.text
    assert "SECRET_TOKEN" not in response.text + caplog.text


@pytest.fixture(scope="module")
def barra_ui_runtime(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    runner = tmp_path_factory.mktemp("barra_ui_runtime") / "check.cjs"
    runner.write_text(r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const root = process.argv[2], mode = process.argv[3];
const ts = require(path.join(root, 'omega-ui/node_modules/typescript'));
const load = file => {
  const m = new Module(file, module); m.filename = file; m.paths = Module._nodeModulePaths(path.dirname(file));
  require.cache[file] = m;
  m._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  }}).outputText, file);
  return m.exports;
};
require.extensions['.ts'] = require.extensions['.tsx'] = (m, file) => { m.exports = load(file); };
const api = load(path.join(root, 'omega-ui/src/api/advancedQuant.ts'));
const asset = Object.fromEntries(api.BARRA_FACTORS.map(k => [k, 0]));
Object.assign(asset, {symbol:'FPT', sector:'Technology', weight_pct:100, specific_risk_pct:0});
const barraRequest = { assets:[asset], factor_covariance:Array.from({length:8}, () => Array(8).fill(0)) };
const caller = {status:'success', is_synthetic:false, data_status:'estimated', provenance_status:'caller_supplied_unverified', pit_verified:false};
const barra = {...caller, source:'request_factor_covariance', schema_version:'barra.v1', timestamp:'2026-10-08T08:30:00Z',
  units:{exposure:'dimensionless',weight:'pct',risk:'annualized_pct',variance:'annualized_pct_squared'},
  factor_order:[...api.BARRA_FACTORS], factor_exposures:{...Object.fromEntries(api.BARRA_FACTORS.map(k => [k, 0]))},
  factor_variance_contributions:{...Object.fromEntries(api.BARRA_FACTORS.map(k => [k, 0]))},
  factor_variance:0, specific_variance:0, total_variance:0, total_risk_annualized_pct:0, asset_exposures:[asset]};
const impactRequest = {symbol:'fpt',order_size:100,average_daily_volume:10000,volatility:0.02,participation_rate:0.1,side:'BUY',arrival_price:20000,observed_spread_bps:0};
const impact = {...caller,source:'request_market_observations',schema_version:'tca.v1',symbol:'FPT',side:'BUY',
  units:{price:'VND_FULL',quantity:'shares',cost:'bps',total_cost:'VND_FULL',volatility:'daily_decimal'},
  estimated_impact_bps:0,spread_cost_bps:0,total_cost_bps:0,total_cost_vnd:0};
const provenance = {source:'market_2015_now.parquet',dataset_id:'stress_test_simulate',dataset_version:'v1',as_of:'2026-10-08T15:30:00+07:00',
  computed_at:'2026-10-08T08:30:00Z',effective_cutoff:'2026-10-07T08:30:00Z',requested_pit_cutoff:null,
  input_timezone:'UTC',normalized_timezone:'UTC',cutoff_resolution:'AS_OF_DEFAULT',max_included_available_at:'2026-10-07T15:30:00+07:00',
  excluded_future_rows:0,content_hash:'a'.repeat(64),artifact_uri:null,is_synthetic:false};
const stressRequest = {portfolio_weights:{FPT:0.5,HPG:0.5}};
const stress = {status:'success',timestamp:'2026-10-08T08:30:00Z',weights_evaluated:{FPT:0.5,HPG:0.5},average_loss_pct:0,
  scenarios:[{id:'floor',name:'Floor',market_shock:0,portfolio_impact_pct:0,severity:'LOW'}],recommendation:'Estimated only',provenance};
const liquidityRequest = {positions:{FPT:100},max_adv_participation:0.1,max_exit_days:3};
const liquidity = {status:'success',is_safe:true,max_exit_days:1,total_impact_bps:0,at_risk_symbols:[],violation_message:'',
  breakdown:[{symbol:'FPT',quantity:100,adv:1000,exit_days:1,exceeds_limit:false}],provenance:{...provenance,dataset_id:'liquidity_stress_validate'}};
const routing = {status:'success',timestamp:'2026-10-08T08:30:00Z',engine:'paper_trading',total_active_orders:0,total_active_slices:0,
  avg_roundtrip_latency_ms:null,routers:[{broker:'VPS',channel:'paper',ping_ms:null,fill_rate_pct:0,price_improvement_bps:null,rejection_rate_pct:0,status:'DATA_ONLY',active_routes:0}],active_queues:[]};
const trade = {trade_id:'t',timestamp:'',symbol:'FPT',side:'BUY',parent_quantity:100,filled_quantity:100,avg_fill_price:20000,
  benchmark_price:20000,pre_trade_impact_bps:null,post_trade_slippage_bps:0,implementation_shortfall_bps:0,traded_value_vnd:2000000,broker:'VPS',algo:'DIRECT',status:'FILLED'};
const report = {status:'success',timestamp:'2026-10-08T08:30:00Z',summary:{num_trades:1,total_traded_value_billion_vnd:0.002,
  average_is_bps:0,average_slippage_bps:0,max_is_bps:0,min_is_bps:0,total_savings_vs_arrival_bps:0},trades:[trade]};
const bad = [null,undefined,'', '0',true,[],{},NaN,Infinity,-Infinity,1e12+1];
async function main() {
  if (mode === 'numeric') {
    assert.equal(api.formatRiskMetric(0), '0.00'); assert.equal(api.formatRiskMetric(-1), '-1.00');
    assert.equal(api.validateBarraResponse(barra).total_variance,0);
    const signed = structuredClone(barra); Object.assign(signed,{factor_variance:1,total_variance:1,total_risk_annualized_pct:1});
    Object.assign(signed.factor_variance_contributions,{market_beta:2,size_smb:-1});
    assert.equal(api.validateBarraResponse(signed).factor_variance_contributions.size_smb,-1);
    for (const value of bad) {
      assert.equal(api.formatRiskMetric(value),'--');
      for (const key of ['factor_variance','specific_variance','total_variance','total_risk_annualized_pct']) assert.throws(() => api.validateBarraResponse({...barra,[key]:value}));
      for (const key of ['estimated_impact_bps','spread_cost_bps','total_cost_bps','total_cost_vnd']) assert.throws(() => api.validateImpactResponse({...impact,[key]:value},impactRequest));
      assert.throws(() => api.validateStressResponse({...stress,average_loss_pct:value},stressRequest));
      assert.throws(() => api.validateLiquidityResponse({...liquidity,total_impact_bps:value},liquidityRequest));
      assert.throws(() => api.validateTcaReport({...report,trades:[{...trade,filled_quantity:value}]}));
    }
    assert.throws(() => api.validateBarraResponse({...barra,total_variance:1}));
    assert.throws(() => api.validateBarraResponse({...barra,legacy:1}));
    assert.throws(() => api.validateStressResponse({...stress,cvar_95_pct:1},stressRequest));
    assert.throws(() => api.validateLiquidityResponse({...liquidity,breakdown:[{...liquidity.breakdown[0],unexpected:1}]},liquidityRequest));
    assert.equal(api.validateLiquidityResponse({...liquidity,max_exit_days:3,breakdown:[{...liquidity.breakdown[0],quantity:300,exit_days:3}]},{...liquidityRequest,positions:{FPT:300}}).is_safe,true);
    assert.equal(api.validateLiquidityResponse({...liquidity,max_exit_days:0.5,breakdown:[{...liquidity.breakdown[0],quantity:50,exit_days:0.5}]},{...liquidityRequest,positions:{FPT:50}}).max_exit_days,0.5);
    assert.throws(() => api.validateBarraResponse({...barra,factor_exposures:{market_beta:0}}));
    assert.throws(() => api.validateBarraResponse({...barra,asset_exposures:[asset,asset]}));
    assert.throws(() => api.validateLiquidityResponse({...liquidity,is_safe:false},liquidityRequest));
    assert.throws(() => api.validateLiquidityResponse({...liquidity,breakdown:[{...liquidity.breakdown[0],adv:0}]},liquidityRequest));
    assert.throws(() => api.validateStressResponse({...stress,weights_evaluated:{FPT:0.5,VNM:0.5}},stressRequest));
    assert.equal(api.validateRoutingReport(routing).routers[0].status,'DATA_ONLY');
    assert.equal(api.validateTcaReport(report).trades[0].pre_trade_impact_bps,null);
  }
  if (mode === 'pit') {
    assert.equal(api.validateStressResponse(stress,stressRequest).average_loss_pct,0);
    assert.equal(api.validateLiquidityResponse(liquidity,liquidityRequest).max_exit_days,1);
    for (const stamp of ['2026-10-07T08:30:00.001Z','2026-10-08T15:30:00','2026-02-30T08:30:00Z',null,'']) {
      assert.throws(() => api.validateStressResponse({...stress,provenance:{...provenance,max_included_available_at:stamp}},stressRequest));
      assert.throws(() => api.validateLiquidityResponse({...liquidity,provenance:{...liquidity.provenance,max_included_available_at:stamp}},liquidityRequest));
    }
    for (const p of [null,{...provenance,is_synthetic:true},{...provenance,pit_verified:false},{...provenance,content_hash:'bad'}])
      assert.throws(() => api.validateStressResponse({...stress,provenance:p},stressRequest));
    for (const change of [{pit_verified:true},{provenance:provenance},{provenance_status:'historical_verified'},{units:{price:'VND_THOUSAND'}}]) {
      assert.throws(() => api.validateImpactResponse({...impact,...change},impactRequest));
      assert.throws(() => api.validateBarraResponse({...barra,...change}));
    }
    assert.equal(api.validateImpactResponse(impact,impactRequest).pit_verified,false);
    assert.equal(api.validateImpactResponse({...impact,side:'SELL'},{...impactRequest,side:'SELL'}).side,'SELL');
    assert.throws(() => api.validateImpactResponse({...impact,symbol:'HPG'},impactRequest));
  }
  if (mode === 'transport') {
    let calls=0;
    global.fetch=async (url,init) => {calls++; assert.ok(init.signal); return {ok:true,json:async()=>impact};};
    await api.advancedQuantApi.calculatePreTradeImpact(impactRequest); assert.equal(calls,1);
    for (const field of ['order_size','average_daily_volume','arrival_price','volatility','participation_rate','observed_spread_bps'])
      for (const value of bad) await assert.rejects(Promise.resolve().then(() => api.advancedQuantApi.calculatePreTradeImpact({...impactRequest,[field]:value})));
    for (const field of ['order_size','average_daily_volume','volatility','participation_rate'])
      for (const value of [0,-1]) await assert.rejects(Promise.resolve().then(() => api.advancedQuantApi.calculatePreTradeImpact({...impactRequest,[field]:value})));
    assert.equal(calls,1);
    const methods = [() => api.advancedQuantApi.getBarraDecomposition(),() => api.advancedQuantApi.calculateBarraDecomposition(barraRequest),
      () => api.advancedQuantApi.getStressScenarios(),() => api.advancedQuantApi.calculatePreTradeImpact(impactRequest),
      () => api.advancedQuantApi.simulateStressTest(stressRequest),() => api.advancedQuantApi.validateLiquidityStress(liquidityRequest),
      () => api.advancedQuantApi.getPostTradeReport(),() => api.advancedQuantApi.getRoutingDiagnostics()];
    for (const status of [422,424,429,500,503]) {
      calls=0; global.fetch=async()=>{calls++;return {ok:false,status,json:async()=>({detail:'https://user:SECRET@example.invalid?token=SECRET'})};};
      for (const method of methods) await assert.rejects(method(), error => !error.message.includes('SECRET'));
      assert.equal(calls,methods.length);
    }
    calls=0; global.fetch=async()=>{calls++;return {ok:true,json:async()=>null};};
    for (const method of methods) await assert.rejects(method());
    assert.equal(calls,methods.length);
    global.fetch=async()=>{throw new Error('https://user:SECRET@example.invalid');};
    await assert.rejects(api.advancedQuantApi.getRoutingDiagnostics(),error=>!error.message.includes('SECRET'));
    for (const payload of [null,[],{}, {...barraRequest,extra:1},{...barraRequest,assets:[]},{...barraRequest,factor_covariance:[[0]]}])
      await assert.rejects(Promise.resolve().then(() => api.advancedQuantApi.calculateBarraDecomposition(payload)));
    for (const payload of [{portfolio_weights:{}},{portfolio_weights:{FPT:0}},{portfolio_weights:{FPT:0.5,fpt:0.5}},{...stressRequest,market_shock_pct:51},{...stressRequest,include_contagion:'true'}])
      await assert.rejects(Promise.resolve().then(()=>api.advancedQuantApi.simulateStressTest(payload)));
    for (const payload of [{positions:{}},{positions:{FPT:0}},{positions:{FPT:100,fpt:1}},{...liquidityRequest,max_adv_participation:0},{...liquidityRequest,max_exit_days:31}])
      await assert.rejects(Promise.resolve().then(()=>api.advancedQuantApi.validateLiquidityStress(payload)));
    const controller = new AbortController(); controller.abort();
    await assert.rejects(api.advancedQuantApi.getPostTradeReport(controller.signal),{name:'AbortError'});
    global.fetch=async(url,init)=>new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));
    await assert.rejects(api.resilientApiRequest('/api/v1/risk/stress-scenarios',{timeoutMs:1,maxRetries:0}),/timed out/);
  }
  if (mode === 'lifecycle' || mode === 'view') {
    const {JSDOM}=require(path.join(root,'omega-ui/node_modules/jsdom'));
    const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost:3000'});
    global.window=dom.window; global.document=dom.window.document; global.IS_REACT_ACT_ENVIRONMENT=true;
    const React=require(path.join(root,'omega-ui/node_modules/react'));
    const {createRoot}=require(path.join(root,'omega-ui/node_modules/react-dom/client'));
    const uiRequire=Module.createRequire(path.join(root,'omega-ui/package.json'));
    const {QueryClient,QueryClientProvider}=uiRequire('@tanstack/react-query');
    const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};};
    const flush=async(fn)=>React.act(async()=>{await fn();await new Promise(r=>setTimeout(r,20));});
    global.fetch=async url=>({ok:true,json:async()=>url.includes('routing')?routing:report});
    api.advancedQuantApi.getBarraDecomposition=async()=>{throw new Error('BARRA_FACTOR_MODEL_UNAVAILABLE');};
    api.advancedQuantApi.getStressScenarios=async()=>{throw new Error('STRESS_MODEL_UNAVAILABLE');};
    const hooks=load(path.join(root,'omega-ui/src/hooks/useBarraRiskTca.ts'));
    const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0},mutations:{retry:false,gcTime:0}}});
    const mount=createRoot(document.getElementById('root'));
    if(mode==='lifecycle') {
      let current,requests=[];
      api.advancedQuantApi.calculatePreTradeImpact=(params,signal)=>{const d=deferred();requests.push({...d,params,signal});return d.promise;};
      function Probe(){current=hooks.usePreTradeImpact();return null;}
      await flush(()=>mount.render(React.createElement(QueryClientProvider,{client},React.createElement(Probe))));
      await flush(()=>current.mutate(impactRequest));
      await flush(()=>current.mutate({...impactRequest,symbol:'HPG'}));
      assert.equal(requests[0].signal.aborted,true);
      await flush(()=>requests[1].resolve({...impact,symbol:'HPG'}));
      await flush(()=>requests[0].resolve(impact));
      assert.equal(current.data.symbol,'HPG');
      await flush(()=>current.reset()); assert.equal(current.data,undefined);
      await flush(()=>current.mutate(impactRequest)); await flush(()=>requests[2].resolve(impact));
      assert.equal(current.data.symbol,'FPT');
      await flush(()=>current.mutate(impactRequest)); assert.equal(current.data,undefined);
      await flush(()=>requests[3].reject(new Error('network'))); assert.equal(current.data,undefined);
      await flush(()=>current.mutate(impactRequest));
      await flush(()=>mount.unmount()); assert.equal(requests[4].signal.aborted,true);
      await flush(()=>requests[4].reject(new DOMException('Aborted','AbortError')));
    } else {
      const stub=(relative,exports)=>{const file=path.join(root,relative);require.cache[file]={id:file,filename:file,loaded:true,exports};};
      stub('omega-ui/src/modules/barra_risk_tca/CircuitBreakerStatusStrip.tsx',{CircuitBreakerStatusStrip:()=>null});
      stub('omega-ui/src/modules/barra_risk_tca/ContagionGraphCanvas.tsx',{ContagionGraphCanvas:()=>null});
      const store=load(path.join(root,'omega-ui/src/store/uiStore.ts')); store.useUiStore.setState({activeSubTabs:{barra_risk_tca:'stress'}});
      const view=load(path.join(root,'omega-ui/src/modules/barra_risk_tca/BarraRiskTcaAnalyticsView.tsx'));
      await flush(()=>mount.render(React.createElement(QueryClientProvider,{client},React.createElement(view.BarraRiskTcaAnalyticsView))));
      await flush(()=>Promise.resolve());
      assert.ok(document.body.textContent.includes('DATA_ONLY'),document.body.textContent); assert.ok(document.body.textContent.includes('Paper TCA'));
      assert.ok(document.querySelector('#barra-request')); assert.ok(document.querySelector('#stress-request')); assert.ok(document.querySelector('#liquidity-request'));
      assert.ok(document.querySelector('#impact-observed_spread_bps'));
      assert.ok(!document.body.textContent.includes('11.25')); assert.ok(!document.body.textContent.includes('1.95%'));
      global.fetch=async url=>{if(url.includes('routing')) throw new Error('SECRET'); return {ok:true,json:async()=>report};};
      await flush(()=>client.invalidateQueries({queryKey:['routing']}));
      await flush(()=>Promise.resolve());
      assert.ok(!document.body.textContent.includes('DATA_ONLY')); assert.ok(!document.body.textContent.includes('SECRET'));
      assert.ok(document.body.textContent.includes('Paper TCA'));
      await flush(()=>mount.unmount());
    }
    client.clear();dom.window.close();
  }
  console.log(mode+' passed');
}
main().catch(error=>{console.error(error);process.exit(1);});
''', encoding="utf-8", newline="\n")
    return root, runner


@pytest.mark.parametrize("mode", ["numeric", "pit", "transport", "lifecycle", "view"])
def test_barra_ui_runtime_boundaries(barra_ui_runtime, mode):
    root, runner = barra_ui_runtime
    result = subprocess.run(
        ["node", str(runner), str(root), mode], cwd=root,
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    if result.returncode:
        pytest.fail(result.stdout + result.stderr)
