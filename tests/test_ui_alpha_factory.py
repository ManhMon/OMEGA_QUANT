import math
from pathlib import Path
import subprocess
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient
from omega.api.routes import alpha
from omega.api.schemas.advanced_quant import AlphaDecayProfileResponse, AlphaEvaluationResponse, CallerSampleProvenance, ParetoFrontierResponse, ParetoPointDTO
from omega.api.services import job_service
from omega.api.server import app

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", tmp_path / "missing.parquet")
    service = job_service.JobService(tmp_path / "jobs.sqlite")
    monkeypatch.setattr(job_service, "get_job_service", lambda: service)
    monkeypatch.setattr(alpha, "DISCOVERY_SESSIONS", {})
    with TestClient(app) as test_client:
        yield test_client

# -------------------------------------------------------------
# 16-DIMENSION ADVERSARIAL TEST SUITE (PHASE 6 ALPHA FACTORY)
# -------------------------------------------------------------

def test_dim1_evaluate_expression_valid(client):
    # Dim 1: Strict Types & Fail-Closed Contract
    payload = {
        "expression": "ts_rank(close, 10)",
        "universe": "VN703",
        "sample_data": {"close": [50000.0, 51000.0, 50500.0, 52000.0, 53000.0]}
    }
    resp = client.post("/api/v1/alpha/evaluate-expression", json=payload)
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True
    assert resp.json()["sample_result"] == payload["sample_data"]["close"]

def test_dim1_evaluate_expression_empty_fail_closed(client):
    # Dim 1 & 11: Fail-closed on empty/whitespace expression
    resp = client.post("/api/v1/alpha/evaluate-expression", json={"expression": "   "})
    assert resp.status_code in (400, 422, 424)

def test_dim2_evaluate_security_sandbox_rejection(client):
    # Dim 2 & 16: Security sandbox / fail closed
    malicious = [
        "__import__('os').system('ls')",
        "eval('1+1')",
        "exec('x = 1')",
        "open('/etc/passwd').read()",
    ]
    for expr in malicious:
        resp = client.post("/api/v1/alpha/evaluate-expression", json={
            "expression": expr, "sample_data": {"close": [50000.0]}
        })
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is False
        assert resp.json()["sample_result"] is None

def test_dim3_alpha_arsenal_signals_endpoint(client):
    # Dim 3 & 13: Metric consistency & fail-closed contract
    resp = client.get("/api/v1/alpha/arsenal/signals?limit=200")
    assert resp.status_code == 424
    assert resp.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"

def test_dim4_alpha_arsenal_filtering_and_search(client):
    # Dim 4 & 10: Filtering by category, status, search string & fail-closed contract
    resp = client.get("/api/v1/alpha/arsenal/signals?category=MOMENTUM&limit=50")
    assert resp.status_code == 424
    assert resp.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"

    # Search
    resp_search = client.get("/api/v1/alpha/arsenal/signals?search=alp_001")
    assert resp_search.status_code == 424
    assert resp_search.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"

def test_dim5_decay_profile_endpoint(client):
    # Dim 5 & 8: 404 DATA_NOT_FOUND when not persisted
    resp = client.get("/api/v1/alpha/decay-profile/ALP_001")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "DATA_NOT_FOUND"

def test_dim6_decay_profile_case_insensitivity(client):
    # Dim 6 & 10: Case canonicalization
    resp = client.get("/api/v1/alpha/decay-profile/alp_002")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "DATA_NOT_FOUND"

@pytest.mark.parametrize("alpha_id", ["ALPHA_0001_VNM", "alpha_0001_vnm", " ALPHA_0001_VNM "])
def test_seeded_decay_profile_calculated_without_dependency(client, monkeypatch, alpha_id):
    def forbidden_read(*args, **kwargs):
        pytest.fail("Seeded decay must not read market data")

    monkeypatch.setattr(alpha.pd, "read_parquet", forbidden_read)
    resp = client.get(f"/api/v1/alpha/decay-profile/{alpha_id}")
    assert resp.status_code == 200
    data = resp.json()
    AlphaDecayProfileResponse.model_validate(data)
    assert data["alpha_id"] == "ALPHA_0001_VNM"
    assert data["half_life_days"] == 8
    assert len(data["profile"]) == 20
    assert data["provenance"] is None
    for lag, point in enumerate(data["profile"], 1):
        decay = math.exp(-lag / 8)
        assert point["lag_days"] == lag
        assert point["correlation_decay"] == pytest.approx(decay)
        assert point["ic"] == pytest.approx(0.054 * decay)
        assert point["ir"] == pytest.approx(0.054 * decay * 30)
        assert all(math.isfinite(point[key]) for key in ("ic", "ir", "correlation_decay"))


@pytest.mark.parametrize("alpha_id", [
    "ALPHA_0001_VNM_EXTRA", "ALPHA_0002_VNM", "ALPHA_0001_FPT", "NaN", "Infinity", "[]", "x" * 65,
])
def test_decay_profile_unknown_seed_variants_fail_closed(client, alpha_id):
    resp = client.get(f"/api/v1/alpha/decay-profile/{alpha_id}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "DATA_NOT_FOUND"


def test_decay_profile_empty_id_rejected(client):
    resp = client.get("/api/v1/alpha/decay-profile/%20")
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Alpha ID cannot be empty"


def test_seeded_decay_profile_response_isolation(client):
    first = client.get("/api/v1/alpha/decay-profile/ALPHA_0001_VNM").json()
    first["profile"][0]["ic"] = -1.0
    second = client.get("/api/v1/alpha/decay-profile/ALPHA_0001_VNM").json()
    assert second["profile"][0]["ic"] == pytest.approx(0.054 * math.exp(-1 / 8))
    assert alpha.DISCOVERY_SESSIONS == {}


def test_dim7_start_discovery_validation_bounds(client):
    # Dim 7 & 8: Math and bound validation on genetic parameters
    # Population size out of bounds (<10 or >500)
    resp = client.post("/api/v1/alpha/discovery/start", json={"population_size": 5})
    assert resp.status_code == 422

    # Generations out of bounds
    resp2 = client.post("/api/v1/alpha/discovery/start", json={"generations": 0})
    assert resp2.status_code == 422

def test_dim8_start_discovery_success(client):
    # Dim 8: Durable queue accepts work independently of worker availability.
    payload = {
        "population_size": 20,
        "generations": 2,
        "mutation_rate": 0.2,
        "crossover_rate": 0.8
    }
    resp = client.post("/api/v1/alpha/discovery/start", json=payload)
    assert resp.status_code == 200
    queued = job_service.get_job_service().get(resp.json()["job_id"])
    assert queued["status"] == "QUEUED"
    assert queued["task_type"] == "genetic_alpha_discovery"

def test_dim9_sse_alpha_discovery_stream(client):
    # Dim 5 & 9: SSE streaming fails closed on un-persisted job
    sse_res = client.get("/sse/v1/alpha/discovery/stream?session_id=sess_12345")
    assert sse_res.status_code == 404
    assert sse_res.json()["detail"] == "JOB_NOT_FOUND"

def test_dim10_sse_unknown_session_graceful_connect(client):
    # Dim 10 & 14: Non-existent session handling in SSE returns 404
    sse_res = client.get("/sse/v1/alpha/discovery/stream?session_id=unknown-sess-1234")
    assert sse_res.status_code == 404
    assert sse_res.json()["detail"] == "JOB_NOT_FOUND"

def test_dim11_ast_complex_formula_evaluation(client):
    # Dim 11: Complex compound AST expression evaluation
    formula = "decay_linear(obi_depth_10, 5) - decay_linear(obi_depth_10, 20) + cross_rank(volume)"
    resp = client.post("/api/v1/alpha/evaluate-expression", json={
        "expression": formula,
        "sample_data": {"obi_depth_10": [0.15] * 30, "volume": [100000.0] * 30}
    })
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True
    assert all(math.isfinite(value) for value in resp.json()["sample_result"])

def test_dim12_ast_syntax_error_handling(client):
    # Dim 12 & 14: Syntax error / fail-closed handling
    resp = client.post("/api/v1/alpha/evaluate-expression", json={
        "expression": "ts_rank(close, ", "sample_data": {"close": [50000.0]}
    })
    assert resp.status_code == 422

def test_dim13_arsenal_limit_bounds(client):
    # Dim 13: Query param bound tests
    resp = client.get("/api/v1/alpha/arsenal/signals?limit=0")
    assert resp.status_code == 422

    resp2 = client.get("/api/v1/alpha/arsenal/signals?limit=1500")
    assert resp2.status_code == 422

def test_dim14_decay_profile_nonexistent_fallback(client):
    # Dim 14: Dynamic fallback for unregistered alpha IDs
    resp = client.get("/api/v1/alpha/decay-profile/CUSTOM_NEW_ALPHA_999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "DATA_NOT_FOUND"

def test_dim15_ast_custom_sample_data_injection(client):
    # Dim 15: Sample data injection for offline custom variable evaluation
    payload = {
        "expression": "ts_rank(custom_feature, 5)",
        "sample_data": {
            "custom_feature": [1.2, 3.4, 2.1, 5.6, 4.3]
        }
    }
    resp = client.post("/api/v1/alpha/evaluate-expression", json=payload)
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True
    assert resp.json()["sample_result"] == [1.2, 3.4, 2.1, 5.6, 0.6]

def test_dim16_safe_eval_rejection_of_dunder_tokens(client):
    # Dim 16: AST node rejection of dunder lookups and attributes
    resp = client.post("/api/v1/alpha/evaluate-expression", json={
        "expression": "close.__class__.__bases__", "sample_data": {"close": [50000.0]}
    })
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is False
    assert resp.json()["sample_result"] is None


def test_pareto_frontier_empty_contract(client):
    resp = client.get("/api/v1/alpha/pareto-frontier")
    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "points": [], "provenance": None}
    ParetoFrontierResponse.model_validate(resp.json())
    assert ParetoFrontierResponse().points is not ParetoFrontierResponse().points


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
@pytest.mark.parametrize("sample_data", [None, "omitted"])
def test_evaluation_missing_dependency(client, endpoint, sample_data):
    payload = {"expression": "close"}
    if sample_data is None:
        payload["sample_data"] = None
    resp = client.post(f"/api/v1/alpha/{endpoint}", json=payload)
    assert resp.status_code == 424
    assert resp.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"


@pytest.mark.parametrize("failure", ["directory", "read_error", "empty", "schema", "nonfinite"])
def test_evaluation_dependency_faults(client, monkeypatch, tmp_path, failure):
    path = tmp_path / "market.parquet"
    if failure == "directory":
        path.mkdir()
    else:
        path.write_bytes(b"corrupted parquet")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)

    def read_parquet(*args, **kwargs):
        if failure in ("directory", "read_error"):
            raise OSError("https://user:private@example.invalid/private.parquet")
        if failure == "schema":
            return pd.DataFrame({"unexpected": [1.0]})
        return pd.DataFrame({
            "ticker": ["OTHER" if failure == "empty" else "FPT"],
            "date": ["2026-10-01"],
            "close": [float("nan")], "volume": [100000.0]
        })

    monkeypatch.setattr(alpha.pd, "read_parquet", read_parquet)
    resp = client.post("/api/v1/alpha/evaluate-expression", json={"expression": "close"})
    assert resp.status_code == 424
    assert resp.json() == {"detail": "DATA_DEPENDENCY_UNAVAILABLE"}
    assert "private" not in resp.text


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
@pytest.mark.parametrize("closes,volume", [
    pytest.param([0.0] + [1.0] * 21, 1.0, id="zero-denominator"),
    pytest.param([0.0] * 22, 1.0, id="zero-over-zero"),
    pytest.param([1.0] * 21 + [0.0], 1.0, id="zero-numerator"),
    pytest.param([-1.0] + [1.0] * 21, 1.0, id="negative-close"),
    pytest.param([1e-320] + [1.0] * 21, 1.0, id="return-overflow"),
    pytest.param([1e-13] + [1.0] * 21, 1.0, id="return-out-of-bounds"),
    pytest.param([1e12 + 1.0] * 22, 1.0, id="close-out-of-bounds"),
    pytest.param([1.0] * 22, 1e12 + 1.0, id="volume-out-of-bounds"),
    pytest.param([float("inf")] * 22, 1.0, id="nonfinite-close"),
    pytest.param([1.0] * 22, float("nan"), id="nonfinite-volume"),
])
def test_evaluation_invalid_market_samples_fail_closed(client, monkeypatch, tmp_path, endpoint, closes, volume):
    path = tmp_path / "market.parquet"
    path.write_bytes(b"test reader supplies adversarial market samples")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)
    monkeypatch.setattr(alpha.pd, "read_parquet", lambda *args, **kwargs: pd.DataFrame({
        "ticker": ["FPT"] * len(closes),
        "date": pd.date_range("2026-09-01", periods=len(closes)),
        "close": closes, "volume": [volume] * len(closes),
    }))

    def forbidden_evaluation(*args, **kwargs):
        pytest.fail("Invalid market samples must not reach provenance or evaluation")

    monkeypatch.setattr(alpha, "ProvenanceEnvelope", forbidden_evaluation)
    monkeypatch.setattr(alpha, "safe_eval_expression", forbidden_evaluation)
    resp = client.post(f"/api/v1/alpha/{endpoint}", json={
        "expression": "ret_20", "as_of": "2026-10-08T00:00:00Z",
    })
    assert resp.status_code == 424
    assert resp.json() == {"detail": "DATA_DEPENDENCY_UNAVAILABLE"}


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
@pytest.mark.parametrize("derived_return", [
    pytest.param(float("inf"), id="inf"),
    pytest.param(float("-inf"), id="negative-inf"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(1e12 + 1.0, id="out-of-bounds"),
])
def test_evaluation_invalid_derived_returns_fail_closed(client, monkeypatch, tmp_path, endpoint, derived_return):
    path = tmp_path / "market.parquet"
    path.write_bytes(b"test reader supplies valid closes")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)
    monkeypatch.setattr(alpha.pd, "read_parquet", lambda *args, **kwargs: pd.DataFrame({
        "ticker": ["FPT"] * 22, "date": pd.date_range("2026-09-01", periods=22),
        "close": [1.0] * 22, "volume": [1.0] * 22,
    }))
    returns = pd.Series([float("nan")] * 20 + [derived_return] * 2)
    monkeypatch.setattr(alpha.pd.Series, "pct_change", lambda *args, **kwargs: returns.copy())
    resp = client.post(f"/api/v1/alpha/{endpoint}", json={
        "expression": "ret_20", "as_of": "2026-10-08T00:00:00Z",
    })
    assert resp.status_code == 424
    assert resp.json() == {"detail": "DATA_DEPENDENCY_UNAVAILABLE"}
    assert np.isnan(returns.iloc[:20]).all()
    if math.isnan(derived_return):
        assert returns.isna().all()
    else:
        assert returns.iloc[20:].eq(derived_return).all()


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
@pytest.mark.parametrize("close", [1.0, 1e12])
def test_evaluation_zero_market_returns_preserved(client, monkeypatch, tmp_path, endpoint, close):
    path = tmp_path / "market.parquet"
    path.write_bytes(b"test reader supplies flat market")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)
    monkeypatch.setattr(alpha.pd, "read_parquet", lambda *args, **kwargs: pd.DataFrame({
        "ticker": ["FPT"] * 22, "date": pd.date_range("2026-09-01", periods=22),
        "close": [close] * 22, "volume": [1e12] * 22,
    }))
    for expression in ("ret_20", "ret_20[-1]"):
        resp = client.post(f"/api/v1/alpha/{endpoint}", json={
            "expression": expression, "as_of": "2026-10-08T00:00:00Z",
        })
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is True
        assert resp.json()["sample_result"] == ([0.0] * 10 if expression == "ret_20" else [0.0])
        assert len(resp.json()["provenance"]["content_hash"]) == 64


def test_evaluation_market_dependency_success(client, monkeypatch, tmp_path):
    path = tmp_path / "market.parquet"
    path.write_bytes(b"test reader supplies market rows")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)
    monkeypatch.setattr(alpha.pd, "read_parquet", lambda *args, **kwargs: pd.DataFrame({
        "ticker": ["FPT", "OTHER", "FPT"],
        "date": ["2026-10-02", "2026-10-01", "2026-10-01"],
        "close": [51000.0, 99999.0, 50000.0],
        "volume": [120000.0, 1.0, 100000.0]
    }))
    resp = client.post("/api/v1/alpha/evaluate-expression", json={"expression": "close"})
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True
    assert resp.json()["sample_result"] == [50000.0, 51000.0]


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
@pytest.mark.parametrize("timestamps", [
    {},
    {"as_of": None, "pit_cutoff": None},
    {"as_of": "2026-10-02T00:00:00+07:00"},
    {"pit_cutoff": "2026-10-02T00:00:00+07:00"},
    {"as_of": "2026-10-03T00:00:00Z", "pit_cutoff": "2026-10-02T00:00:00+07:00"},
])
def test_evaluation_excludes_future_market_rows(client, monkeypatch, tmp_path, endpoint, timestamps):
    path = tmp_path / "market.parquet"
    path.write_bytes(b"test reader supplies market rows")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)
    # Future rows must not displace history before tail(60), including derived returns.
    frame = pd.DataFrame({
        "ticker": ["FPT"] * 62,
        "date": ["2099-01-01"] * 61 + ["2026-10-01"],
        "close": [99999.0] * 61 + [50000.0],
        "volume": [99999.0] * 61 + [100000.0],
    })
    monkeypatch.setattr(alpha.pd, "read_parquet", lambda *args, **kwargs: frame)
    real_eval = alpha.safe_eval_expression

    def evaluate(expression, **kwargs):
        scope = kwargs["locals_dict"]
        assert scope["close"].tolist() == [50000.0]
        assert scope["volume"].tolist() == [100000.0]
        assert scope["ret_20"].tolist() == [0.0]
        return real_eval(expression, **kwargs)

    monkeypatch.setattr(alpha, "safe_eval_expression", evaluate)
    resp = client.post(f"/api/v1/alpha/{endpoint}", json={"expression": "close", **timestamps})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is True
    assert data["sample_result"] == [50000.0]
    provenance = data["provenance"]
    assert provenance["excluded_future_rows"] == 61
    assert provenance["source"] == "ast_expression"
    assert provenance["dataset_id"] == "alpha_eval"
    assert provenance["is_synthetic"] is False
    assert "pit_verified" not in provenance
    assert pd.Timestamp(provenance["max_included_available_at"]) == pd.Timestamp("2026-10-01T08:30:00Z")
    expected_as_of = pd.Timestamp(timestamps["as_of"]) if timestamps.get("as_of") else pd.Timestamp(provenance["as_of"])
    expected_cutoff = pd.Timestamp(timestamps["pit_cutoff"]) if timestamps.get("pit_cutoff") else expected_as_of
    assert pd.Timestamp(provenance["as_of"]) == expected_as_of
    assert pd.Timestamp(provenance["effective_cutoff"]) == expected_cutoff
    assert provenance["cutoff_resolution"] == ("REQUESTED" if timestamps.get("pit_cutoff") else "AS_OF_DEFAULT")
    assert (pd.Timestamp(provenance["requested_pit_cutoff"]) if provenance["requested_pit_cutoff"] else None) == (
        pd.Timestamp(timestamps["pit_cutoff"]) if timestamps.get("pit_cutoff") else None
    )
    assert frame.iloc[0]["close"] == 99999.0


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
@pytest.mark.parametrize("market_date", [
    "2026-10-02", date(2026, 10, 2), datetime(2026, 10, 2, 23, 59),
    pd.Timestamp("2026-10-02"), np.datetime64("2026-10-02"),
])
@pytest.mark.parametrize("cutoff,include_today", [
    ("2026-10-02T15:29:59.999999+07:00", False),
    ("2026-10-02T08:29:59.999999Z", False),
    ("2026-10-02T15:30:00+07:00", True),
    ("2026-10-02T08:30:00Z", True),
    ("2026-10-02T15:30:00.000001+07:00", True),
])
@pytest.mark.parametrize("cutoff_field", ["as_of", "pit_cutoff"])
def test_evaluation_daily_close_availability(client, monkeypatch, tmp_path, endpoint, market_date, cutoff, include_today, cutoff_field):
    path = tmp_path / "market.parquet"
    path.write_bytes(b"test reader supplies daily session labels")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)
    frame = pd.DataFrame({
        "ticker": ["FPT", "FPT"],
        "date": pd.Series([market_date, "2026-10-01"], dtype=object),
        "close": [99999.0, 50000.0], "volume": [1.0, 100000.0],
    })
    monkeypatch.setattr(alpha.pd, "read_parquet", lambda *args, **kwargs: frame)
    resp = client.post(f"/api/v1/alpha/{endpoint}", json={
        "expression": "close", "as_of": "2026-10-03T00:00:00Z", cutoff_field: cutoff,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is True
    assert data["sample_result"] == ([50000.0, 99999.0] if include_today else [50000.0])
    provenance = data["provenance"]
    assert provenance["excluded_future_rows"] == (0 if include_today else 1)
    expected_max = "2026-10-02T08:30:00Z" if include_today else "2026-10-01T08:30:00Z"
    assert pd.Timestamp(provenance["max_included_available_at"]) == pd.Timestamp(expected_max)
    assert pd.Timestamp(provenance["max_included_available_at"]) <= pd.Timestamp(cutoff)
    assert frame["close"].tolist() == [99999.0, 50000.0]


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
def test_evaluation_preclose_empty_history_fail_closed(client, monkeypatch, tmp_path, endpoint):
    path = tmp_path / "market.parquet"
    path.write_bytes(b"test reader supplies unavailable daily close")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)
    monkeypatch.setattr(alpha.pd, "read_parquet", lambda *args, **kwargs: pd.DataFrame({
        "ticker": ["FPT"], "date": ["2026-10-02"],
        "close": [99999.0], "volume": [100000.0],
    }))

    def forbidden_evaluation(*args, **kwargs):
        pytest.fail("Unavailable daily close must not reach evaluation")

    monkeypatch.setattr(alpha, "safe_eval_expression", forbidden_evaluation)
    resp = client.post(f"/api/v1/alpha/{endpoint}", json={
        "expression": "close", "as_of": "2026-10-02T15:29:59+07:00",
    })
    assert resp.status_code == 424
    assert resp.json() == {"detail": "DATA_DEPENDENCY_UNAVAILABLE"}


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
@pytest.mark.parametrize("date", ["2099-01-01", None, "not-a-date", 123456789])
def test_evaluation_unusable_market_dates_fail_closed(client, monkeypatch, tmp_path, endpoint, date):
    path = tmp_path / "market.parquet"
    path.write_bytes(b"test reader supplies unusable dates")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)
    monkeypatch.setattr(alpha.pd, "read_parquet", lambda *args, **kwargs: pd.DataFrame({
        "ticker": ["FPT"], "date": [date], "close": [99999.0], "volume": [100000.0],
    }))

    def forbidden_evaluation(*args, **kwargs):
        pytest.fail("Unusable market dates must not reach evaluation")

    monkeypatch.setattr(alpha, "safe_eval_expression", forbidden_evaluation)
    resp = client.post(f"/api/v1/alpha/{endpoint}", json={"expression": "close"})
    assert resp.status_code == 424
    assert resp.json() == {"detail": "DATA_DEPENDENCY_UNAVAILABLE"}


def test_evaluation_provenance_hash_binds_cutoff_and_eligible_inputs(client, monkeypatch, tmp_path):
    path = tmp_path / "market.parquet"
    path.write_bytes(b"test reader supplies mutable future rows")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)
    frame = pd.DataFrame({
        "ticker": ["FPT", "FPT"], "date": ["2026-10-01", "2099-01-01"],
        "close": [50000.0, 99999.0], "volume": [100000.0, 1.0],
    })
    monkeypatch.setattr(alpha.pd, "read_parquet", lambda *args, **kwargs: frame)
    payload = {"expression": "close", "as_of": "2026-10-03T00:00:00Z", "pit_cutoff": "2026-10-02T00:00:00Z"}

    def content_hash():
        resp = client.post("/api/v1/alpha/evaluate-expression", json=payload)
        assert resp.status_code == 200
        assert resp.json()["sample_result"] == [frame.iloc[0]["close"]]
        return resp.json()["provenance"]["content_hash"]

    first = content_hash()
    frame.loc[1, "close"] = 123456.0
    assert content_hash() == first
    payload["pit_cutoff"] = "2026-10-03T00:00:00Z"
    second = content_hash()
    assert second != first
    frame.loc[0, "close"] = 51000.0
    assert content_hash() != second


@pytest.mark.parametrize("expression", ["close", "unknown_feature"])
def test_evaluation_aware_date_boundary_and_provenance(client, monkeypatch, tmp_path, expression):
    path = tmp_path / "market.parquet"
    path.write_bytes(b"test reader supplies timezone boundaries")
    monkeypatch.setattr(alpha, "MARKET_PARQUET_PATH", path)
    monkeypatch.setattr(alpha.pd, "read_parquet", lambda *args, **kwargs: pd.DataFrame({
        "ticker": ["FPT"] * 3,
        "date": ["2026-10-01T15:30:01+07:00", "2026-10-01T08:30:00Z", "2026-09-30"],
        "close": [99999.0, 51000.0, 50000.0], "volume": [1.0, 120000.0, 100000.0],
    }))
    resp = client.post("/api/v1/alpha/ast/evaluate", json={
        "expression": expression, "as_of": "2026-10-01T15:30:00+07:00",
        "pit_cutoff": "2026-10-01T08:30:00Z",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is (expression == "close")
    assert data["sample_result"] == ([50000.0, 51000.0] if expression == "close" else None)
    provenance = data["provenance"]
    for field in ("as_of", "effective_cutoff", "requested_pit_cutoff", "max_included_available_at"):
        assert pd.Timestamp(provenance[field]) == pd.Timestamp("2026-10-01T08:30:00Z")
    assert provenance["excluded_future_rows"] == 1
    assert provenance["cutoff_resolution"] == "REQUESTED"


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
@pytest.mark.parametrize("timestamps", [
    {"as_of": "2026-10-01T00:00:00"},
    {"pit_cutoff": "2026-10-01T00:00:00"},
    {"as_of": "invalid"},
    {"as_of": "2026-10-01T00:00:00Z", "pit_cutoff": "2026-10-02T00:00:00Z"},
    {"pit_cutoff": "2099-01-01T00:00:00Z"},
])
def test_evaluation_invalid_cutoff_rejected_before_io(client, monkeypatch, endpoint, timestamps):
    def forbidden_read(*args, **kwargs):
        pytest.fail("Invalid temporal input must not read market data")

    monkeypatch.setattr(alpha.pd, "read_parquet", forbidden_read)
    for sample in ({}, {"sample_data": {"close": [50000.0]}}):
        resp = client.post(f"/api/v1/alpha/{endpoint}", json={"expression": "close", **timestamps, **sample})
        assert resp.status_code == 422


@pytest.mark.parametrize("missing", [None, "alt_0", "interbank_on_spread", "term_structure_slope", "interbank_vol_5d", "macro_monetary_regime"])
def test_hybrid_alt_data_contract_faults(monkeypatch, missing):
    from scripts import run_hybrid_alpha_evolution as hybrid

    monkeypatch.setattr(hybrid, "ACTIVE_FEATURE_COLUMNS", list(hybrid.BASE_FEATURE_COLUMNS))
    expected = ["interbank_on_spread", "term_structure_slope", "interbank_vol_5d", "macro_monetary_regime"]
    assert hybrid.ALT_DATA_FEATURE_COUNT == 14
    assert len(hybrid.ALT_DATA_FEATURE_COLUMNS) == 14
    assert hybrid.ALT_DATA_FEATURE_COLUMNS[-4:] == expected
    features = [f"alt_{i}" for i in range(25)]

    class Adapter:
        def __init__(self, **kwargs):
            pass

        def generate_all(self, frame):
            return frame.assign(**{name: 1.0 for name in features + hybrid.ALT_DATA_FEATURE_COLUMNS if name != missing})

        def get_feature_groups(self):
            return {"alt_features": features, "alt_data": hybrid.ALT_DATA_FEATURE_COLUMNS}

    monkeypatch.setattr(hybrid, "UnifiedFeatureAdapter", Adapter)
    frame = pd.DataFrame({"date": [pd.Timestamp("2026-10-01")], "ticker": ["FPT"], **{
        name: [50000.0] for name in hybrid.BASE_FEATURE_COLUMNS
    }})
    if missing:
        with pytest.raises(ValueError, match="missing required features"):
            hybrid.enrich_with_unified_features(frame)
        assert hybrid.ACTIVE_FEATURE_COLUMNS == hybrid.BASE_FEATURE_COLUMNS
    else:
        enriched, columns = hybrid.enrich_with_unified_features(frame)
        assert len(columns) == 44
        assert all(enriched[name].iloc[0] == 1.0 for name in expected)


def test_standing_llm_config_snapshot_restore():
    from copy import deepcopy
    from omega.api.routes import copilot
    from tests.test_ui_llm_config import restore_llm_config

    snapshot = deepcopy(copilot._IN_MEMORY_LLM_CONFIG)
    fixture = restore_llm_config.__wrapped__()
    next(fixture)
    try:
        copilot._IN_MEMORY_LLM_CONFIG.clear()
        copilot._IN_MEMORY_LLM_CONFIG["fault_injected"] = {"profiles": ["mutated"]}
    finally:
        with pytest.raises(StopIteration):
            next(fixture)
    assert copilot._IN_MEMORY_LLM_CONFIG == snapshot


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
def test_explicit_sample_bypasses_dependency(client, monkeypatch, endpoint):
    def forbidden_read(*args, **kwargs):
        pytest.fail("Explicit sample data must not read the market dependency")

    monkeypatch.setattr(alpha.pd, "read_parquet", forbidden_read)
    resp = client.post(f"/api/v1/alpha/{endpoint}", json={
        "expression": "custom_feature", "sample_data": {"custom_feature": [1.0] * 30}
    })
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True
    assert resp.json()["sample_result"] == [1.0] * 10


@pytest.mark.parametrize("endpoint", ["evaluate-expression", "ast/evaluate"])
@pytest.mark.parametrize("timestamps", [
    {},
    {"as_of": "2015-01-01T00:00:00Z"},
    {"pit_cutoff": "2015-01-01T00:00:00Z"},
    {"as_of": "2015-01-02T07:00:00+07:00", "pit_cutoff": "2015-01-01T00:00:00Z"},
])
@pytest.mark.parametrize("expression", ["close", "unknown_feature", "close / 0", "__import__('os')"])
def test_caller_sample_historical_cutoff_never_claims_market_pit(client, monkeypatch, endpoint, timestamps, expression):
    def forbidden_read(*args, **kwargs):
        pytest.fail("Caller samples cannot acquire market provenance through I/O")

    monkeypatch.setattr(alpha.pd, "read_parquet", forbidden_read)
    resp = client.post(f"/api/v1/alpha/{endpoint}", json={
        "expression": expression, "sample_data": {"close": [99999.0]}, **timestamps,
    })
    assert resp.status_code == 200
    data = resp.json()
    AlphaEvaluationResponse.model_validate(data)
    assert data["is_valid"] is (expression == "close")
    provenance = data["provenance"]
    assert provenance["source"] == "caller_sample"
    assert provenance["dataset_id"] == (
        "alpha_eval_caller_sample" if data["is_valid"] else "alpha_eval_caller_sample_rejected"
    )
    assert provenance["is_synthetic"] is True
    assert provenance["pit_verified"] is False
    assert provenance["input_timezone"] == "UNVERIFIED"
    assert provenance["max_included_available_at"] is None
    assert provenance["excluded_future_rows"] == 0
    assert pd.Timestamp(provenance["effective_cutoff"]) == pd.Timestamp(
        timestamps.get("pit_cutoff") or timestamps.get("as_of") or provenance["as_of"]
    )


@pytest.mark.parametrize("override", [
    {"is_synthetic": False}, {"pit_verified": True}, {"source": "ast_expression"},
    {"dataset_id": "alpha_eval"}, {"input_timezone": "UTC+7"},
    {"max_included_available_at": "2015-01-01T00:00:00Z"}, {"excluded_future_rows": 1},
])
def test_caller_sample_provenance_rejects_verified_claims(client, override):
    response = client.post("/api/v1/alpha/evaluate-expression", json={
        "expression": "close", "sample_data": {"close": [1.0]},
        "as_of": "2015-01-02T00:00:00Z", "pit_cutoff": "2015-01-01T00:00:00Z",
    }).json()
    with pytest.raises(ValidationError):
        CallerSampleProvenance.model_validate({**response["provenance"], **override})
    with pytest.raises(ValidationError):
        AlphaEvaluationResponse.model_validate({
            **response, "provenance": {**response["provenance"], **override},
        })


@pytest.mark.parametrize("sample_data", [
    {}, [], {"close": []}, {"close": "50000"}, {"close": ["50000"]},
    {"close": [None]}, {"close": [True]}, {"close": [1e13]},
    {"close": [50000.0] * 10001}, {f"feature_{i}": [1.0] for i in range(65)}
])
def test_invalid_explicit_samples_do_not_fallback(client, sample_data):
    resp = client.post("/api/v1/alpha/evaluate-expression", json={
        "expression": "close", "sample_data": sample_data
    })
    assert resp.status_code == 422


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_explicit_samples_rejected(client, value):
    resp = client.post("/api/v1/alpha/evaluate-expression", content=(
        '{"expression":"close","sample_data":{"close":[' + value + ']}}'
    ), headers={"Content-Type": "application/json"})
    assert resp.status_code == 422


@pytest.mark.parametrize("expression", ["1e309", "close / 0", "unknown_feature"])
def test_evaluation_invalid_result_not_dependency_failure(client, expression):
    resp = client.post("/api/v1/alpha/evaluate-expression", json={
        "expression": expression, "sample_data": {"close": [50000.0]}
    })
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is False
    assert resp.json()["sample_result"] is None


@pytest.mark.parametrize("field,value", [
    ("ic_mean", float("nan")), ("ir_annualized", float("inf")),
    ("ic_mean", 1.1), ("turnover_pct", -1.0), ("turnover_pct", 101.0),
    ("complexity_score", 0), ("complexity_score", True), ("alpha_id", ""),
    ("ir_annualized", "1.5"), ("unexpected", 1)
])
def test_pareto_point_strict_contract(field, value):
    point = {
        "alpha_id": "ALP_001", "ic_mean": 0.04, "ir_annualized": 1.5,
        "turnover_pct": 10.0, "complexity_score": 5
    }
    ParetoPointDTO.model_validate(point)
    with pytest.raises(ValidationError):
        ParetoPointDTO.model_validate({**point, field: value})


@pytest.fixture(scope="module")
def alpha_ui_runtime(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    runner = tmp_path_factory.mktemp("alpha_ui_runtime") / "check.cjs"
    runner.write_text(r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const root = process.argv[2];
const mode = process.argv[3];
const ts = require(path.join(root, 'omega-ui/node_modules/typescript'));
const load = file => {
  const m = new Module(file, module);
  m.filename = file; m.paths = Module._nodeModulePaths(path.dirname(file));
  require.cache[file] = m;
  m._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, file);
  return m.exports;
};
const oldTs = require.extensions['.ts'];
require.extensions['.ts'] = (m, file) => { m.exports = load(file); };
const api = load(path.join(root, 'omega-ui/src/api/advancedQuant.ts'));
const evalResult = { status: 'success', expression: 'close', is_valid: true, ast_type: 'Name',
  ic_estimate: 0, ir_estimate: 0, turnover_estimate_pct: 0, complexity_score: 1, sample_result: [0, -1, 50000] };
const decay = { status: 'success', alpha_id: 'ALPHA_0001_VNM', name: 'Seed', half_life_days: 8,
  decay_regime: 'EXPONENTIAL_PERSISTENT', profile: [{ lag_days: 1, ic: 0, ir: 0, correlation_decay: 0 }] };
const event = { session_id: 'session', event_type: 'GENERATION_UPDATE', generation: 1, max_generations: 2,
  progress: 50, best_fitness: 0, best_formula: 'close', timestamp: '2026-10-08T08:30:00Z' };
const provenance = { source: 'ast_expression', dataset_id: 'alpha_eval', dataset_version: 'v1', content_hash: 'a'.repeat(64),
  computed_at: '2026-10-08T08:30:00Z', excluded_future_rows: 0, as_of: '2026-10-08T15:30:00+07:00',
  effective_cutoff: '2026-10-08T08:30:00Z', requested_pit_cutoff: '2026-10-08T15:30:00+07:00',
  normalized_timezone: 'UTC', is_synthetic: false, max_included_available_at: '2026-10-08T08:30:00Z' };
async function main() {
  if (mode === 'numeric') {
    assert.equal(api.formatAlphaMetric(0, 3), '0.000');
    assert.equal(api.formatAlphaMetric(-0.5, 2), '-0.50');
    for (const value of [null, undefined, '', '0', [], {}, true, NaN, Infinity, -Infinity, 1e12 + 1]) {
      assert.equal(api.formatAlphaMetric(value), '--');
      assert.throws(() => api.validateAlphaEvaluation({ ...evalResult, ic_estimate: value }));
      assert.throws(() => api.validateAlphaDecay({ ...decay, half_life_days: value }));
    }
    assert.equal(api.validateAlphaEvaluation(evalResult).sample_result[2], 50000);
    assert.equal(api.validateAlphaDecay(decay).profile[0].ir, 0);
    for (const divisor of [0, -1]) assert.throws(() => api.validateAlphaDecay({ ...decay, half_life_days: divisor }));
    for (const result of [null, [], {}, { ...evalResult, sample_result: [Infinity] }, { ...evalResult, sample_result: Array(11).fill(0) }])
      assert.throws(() => api.validateAlphaEvaluation(result));
    assert.equal(api.validateAlphaArsenal({ status: 'success', total_available: 0, count: 0, signals: [] }).total_available, 0);
    assert.throws(() => api.validateAlphaArsenal({ status: 'success', total_available: 0, count: 1, signals: [] }));
    assert.throws(() => api.validateAlphaDecay({ ...decay, profile: [decay.profile[0], decay.profile[0]] }));
  }
  if (mode === 'pit') {
    api.validateAlphaProvenance(provenance);
    api.validateAlphaProvenance({ ...provenance, max_included_available_at: '2026-10-08T08:29:59Z' });
    assert.throws(() => api.validateAlphaProvenance({ ...provenance, max_included_available_at: '2026-10-08T08:30:00.001Z' }));
    assert.throws(() => api.validateAlphaProvenance({ ...provenance, effective_cutoff: '2026-10-08T08:30:01Z' }));
    const caller = { ...provenance, source: 'caller_sample', dataset_id: 'caller_sample', is_synthetic: true, pit_verified: false,
      input_timezone: 'UNVERIFIED', max_included_available_at: null };
    api.validateAlphaProvenance(caller);
    assert.throws(() => api.validateAlphaProvenance({ ...caller, pit_verified: true }));
    let body;
    global.fetch = async (_, init) => { body = JSON.parse(init.body); return { ok: true, json: async () => ({ ...evalResult, provenance }) }; };
    const request = { expression: 'close', as_of: provenance.as_of, pit_cutoff: provenance.requested_pit_cutoff };
    await api.advancedQuantApi.evaluateAlphaAst(request);
    assert.deepEqual(body, request);
    await assert.rejects(api.advancedQuantApi.evaluateAlphaAst({ ...request, as_of:'2026-10-08T08:31:00Z' }));
    await assert.rejects(api.advancedQuantApi.evaluateAlphaAst({ ...request, sample_data:{close:[50000]} }));
    global.fetch = async () => ({ ok:true, json:async () => ({ ...evalResult, provenance:caller }) });
    assert.equal((await api.advancedQuantApi.evaluateAlphaAst({ ...request, sample_data:{close:[50000]} })).provenance.pit_verified,false);
    for (const stamp of ['2026-10-08T15:30:00', '2026-02-30T08:30:00Z', 'garbage', '', null])
      await assert.rejects(api.advancedQuantApi.evaluateAlphaAst({ expression: 'close', as_of: stamp }));
    assert.equal(api.validateAlphaEvaluation({ ...evalResult, provenance: caller }).provenance.pit_verified, false);
  }
  if (mode === 'transport') {
    for (const request of [null, [], { expression:'close', unexpected:1 }]) await assert.rejects(api.advancedQuantApi.evaluateAlphaAst(request));
    for (const request of [null, [], { unexpected:1 }]) await assert.rejects(api.advancedQuantApi.startAlphaDiscovery(request));
    for (const request of [null, [], { search:[] }, { category:1 }, { unexpected:1 }]) await assert.rejects(Promise.resolve().then(() => api.advancedQuantApi.getAlphaArsenalSignals(request)));
    for (const field of ['generations', 'population_size', 'mutation_rate', 'crossover_rate', 'target_ic', 'target_ir'])
      for (const value of [0, -1, NaN, Infinity, 1e12 + 1, '', [], null]) {
        await assert.rejects(api.advancedQuantApi.startAlphaDiscovery({ [field]: value }));
      }
    let calls = 0;
    global.fetch = async () => { calls++; throw new Error('https://user:secret@example.invalid'); };
    await assert.rejects(api.advancedQuantApi.getAlphaDecayProfile('ALPHA_0001_VNM'));
    assert.equal(calls, 1);
    assert.ok(!api.alphaErrorMessage(new Error('https://user:secret@example.invalid')).includes('secret'));
    for (const status of [422, 424, 429, 500]) {
      calls = 0;
      global.fetch = async () => { calls++; return { ok: false, status, json: async () => ({ detail: 'DATA_DEPENDENCY_UNAVAILABLE' }) }; };
      await assert.rejects(api.advancedQuantApi.getAlphaArsenalSignals(), e => e.status === status);
      assert.equal(calls, 1);
    }
    for (const value of [0, -1, NaN, Infinity]) await assert.rejects(Promise.resolve().then(() => api.advancedQuantApi.getAlphaArsenalSignals({ limit: value })));
    const originalTimeout = global.setTimeout;
    global.setTimeout = (fn, ms, ...args) => originalTimeout(fn, ms === 10000 ? 1 : ms, ...args);
    global.fetch = (_, init) => new Promise((resolve, reject) => init.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))));
    try { await assert.rejects(api.advancedQuantApi.getAlphaDecayProfile('ALPHA_0001_VNM'), /timed out/); }
    finally { global.setTimeout = originalTimeout; }
    const aborted = new AbortController(); aborted.abort();
    await assert.rejects(api.advancedQuantApi.getAlphaDecayProfile('ALPHA_0001_VNM', aborted.signal), /Aborted/);
    assert.throws(() => api.alphaDiscoveryUrl('/sse/v1/alpha/discovery/stream?session_id=other', 'session'));
    for (const url of ['https://user:secret@example.invalid/sse/v1/alpha/discovery/stream', 'https://other.invalid/sse/v1/alpha/discovery/stream', '/unexpected'])
      assert.throws(() => api.alphaDiscoveryUrl(url));
  }
  if (mode === 'events') {
    assert.equal(api.validateAlphaDiscoveryEvent(event, 'session').best_fitness, 0);
    for (const value of [null, [], { ...event, session_id: 'other' }, { ...event, progress: Infinity },
      { ...event, generation: 3 }, { ...event, max_generations: 0 }, { ...event, best_fitness: 1e12 + 1 },
      { ...event, event_type: 'UNKNOWN' }, { ...event, event_type: 'DISCOVERY_COMPLETED' }])
      assert.throws(() => api.validateAlphaDiscoveryEvent(value, 'session'));
    assert.equal(api.validateAlphaDiscoveryEvent({ ...event, event_type: 'DISCOVERY_COMPLETED', generation: 2, progress: 100 }, 'session').progress, 100);
    assert.equal(api.validateAlphaDiscoveryEvent({ session_id: 'session', event_type: 'DISCOVERY_FAILED' }, 'session').event_type, 'DISCOVERY_FAILED');
  }
  if (mode === 'lifecycle') {
    const { JSDOM } = require(path.join(root, 'omega-ui/node_modules/jsdom'));
    const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost:3000' });
    global.window = dom.window; global.document = dom.window.document;
    global.IS_REACT_ACT_ENVIRONMENT = true;
    const React = require(path.join(root, 'omega-ui/node_modules/react'));
    const { createRoot } = require(path.join(root, 'omega-ui/node_modules/react-dom/client'));
    const uiRequire = Module.createRequire(path.join(root, 'omega-ui/package.json'));
    const { QueryClient, QueryClientProvider } = uiRequire('@tanstack/react-query');
    const hook = load(path.join(root, 'omega-ui/src/hooks/useAlphaFactory.ts'));
    let current, evalCalls = [], decayCalls = [], submissions = [], streams = [];
    const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return {promise,resolve,reject}; };
    api.advancedQuantApi.getAlphaArsenalSignals = async () => ({ status: 'success', total_available: 0, count: 0, signals: [] });
    api.advancedQuantApi.getAlphaDecayProfile = (id, signal) => { const d = deferred(); decayCalls.push({ id, signal, ...d }); return d.promise; };
    api.advancedQuantApi.evaluateAlphaAst = (payload, signal) => { const d = deferred(); evalCalls.push({payload, signal, ...d}); return d.promise; };
    api.advancedQuantApi.startAlphaDiscovery = (params, signal) => { const d = deferred(); submissions.push({params, signal, ...d}); return d.promise; };
    global.EventSource = class { constructor(url) { this.url=url; streams.push(this); } close() { this.closed=true; } };
    function Probe() { current=hook.useAlphaFactory(); return null; }
    const qc = new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});
    const renderRoot = createRoot(document.getElementById('root'));
    const flush = async (fn = () => {}) => React.act(async () => { fn(); await new Promise(resolve => setTimeout(resolve, 10)); });
    await flush(() => renderRoot.render(React.createElement(QueryClientProvider,{client:qc},React.createElement(Probe))));
    await flush(() => current.handleEvaluate());
    assert.equal(decayCalls[0].signal.aborted, false);
    await flush(() => current.setExpression('volume'));
    assert.equal(evalCalls[0].signal.aborted, true);
    await flush(() => evalCalls[0].resolve(evalResult));
    assert.equal(current.evaluationResult, undefined);
    await flush(() => current.handleEvaluate());
    await flush(() => current.setSelectedAlphaId('NEW'));
    assert.equal(evalCalls[1].signal.aborted, false);
    await flush(() => decayCalls[0].resolve(decay));
    assert.equal(current.decayProfile, undefined);
    await flush(() => evalCalls[1].resolve({ ...evalResult, expression: 'volume' }));
    assert.equal(current.evaluationResult.expression, 'volume');
    assert.equal(current.totalArsenalCount, 0);
    const response = { status:'success',job_id:'session',session_id:'session',stream_url:'/sse/v1/alpha/discovery/stream?session_id=session',generations:2 };
    await flush(() => current.handleStartDiscovery({ generations: 2 }));
    await flush(() => submissions[0].resolve(response));
    await flush(() => streams[0].onmessage({ data: JSON.stringify(event) }));
    assert.equal(current.discoveryState.bestFitness, 0);
    await flush(() => streams[0].onmessage({ data: JSON.stringify({ ...event, progress: 100 }) }));
    assert.equal(current.discoveryState.status, 'RUNNING');
    await flush(() => streams[0].onmessage({ data: JSON.stringify({ session_id:'session', event_type:'DISCOVERY_FAILED' }) }));
    assert.equal(current.discoveryState.status, 'ERROR'); assert.equal(streams[0].closed,true);
    await flush(() => current.handleStartDiscovery({ generations: 2 }));
    await flush(() => submissions[1].resolve(response));
    await flush(() => streams[0].onmessage({ data: JSON.stringify({ ...event, event_type:'DISCOVERY_COMPLETED', generation:2, progress:100 }) }));
    assert.equal(current.discoveryState.status, 'RUNNING');
    await flush(() => streams[1].onmessage({ data: '{malformed' }));
    assert.equal(current.discoveryState.status, 'ERROR');
    await flush(() => current.handleStartDiscovery({ generations: 2 }));
    await flush(() => submissions[2].resolve({ ...response, stream_url: null, history: [] }));
    assert.equal(current.discoveryState.status, 'ERROR');
    await flush(() => current.handleStartDiscovery({ generations: 2 }));
    await flush(() => submissions[3].resolve(response));
    await flush(() => streams[2].onmessage({ data: JSON.stringify({ ...event, event_type:'DISCOVERY_COMPLETED', generation:2, progress:100 }) }));
    assert.equal(current.discoveryState.status, 'COMPLETED'); assert.equal(streams[2].closed, true);
    await flush(() => current.handleStartDiscovery({ generations: 2 }));
    await flush(() => current.handleStartDiscovery({ generations: 2 }));
    assert.equal(submissions[4].signal.aborted, true);
    await flush(() => submissions[4].resolve(response));
    assert.equal(streams.length, 3);
    await flush(() => submissions[5].reject(new Error('https://user:secret@example.invalid')));
    assert.equal(current.discoveryState.status, 'ERROR'); assert.ok(!current.discoveryError.includes('secret'));
    await flush(() => renderRoot.unmount()); qc.clear();
    assert.equal(decayCalls.at(-1).signal.aborted,true);
    require.extensions['.tsx'] = (m, file) => { m.exports = load(file); };
    api.advancedQuantApi.getAlphaDecayProfile = async () => decay;
    api.advancedQuantApi.evaluateAlphaAst = async () => ({ ...evalResult, is_valid:false, error:'Invalid formula' });
    const { useUiStore } = load(path.join(root, 'omega-ui/src/store/uiStore.ts'));
    useUiStore.setState({ locale:'en', activeFeatureId:null, activeSubTabs:{alpha_factory:'AST_STUDIO'} });
    const { AlphaFactoryDiscoveryStation } = load(path.join(root, 'omega-ui/src/modules/alpha_factory/AlphaFactoryDiscoveryStation.tsx'));
    const stationRoot = createRoot(document.getElementById('root'));
    await flush(() => stationRoot.render(React.createElement(QueryClientProvider,{client:qc},React.createElement(AlphaFactoryDiscoveryStation))));
    const evaluateButton = Array.from(document.querySelectorAll('button')).find(b => /Evaluate/i.test(b.textContent));
    assert.ok(evaluateButton);
    await flush(() => evaluateButton.click());
    assert.ok(document.body.textContent.includes('Invalid formula or result'));
    assert.ok(document.body.textContent.includes('--'));
    assert.ok(!/NaN|Infinity|\+-/.test(document.body.textContent));
    assert.equal(document.querySelector('select[aria-label="Universe Selection"]').value, 'VN703');
    await flush(() => useUiStore.setState({activeSubTabs:{alpha_factory:'GENETIC_EVOLUTION'}}));
    const generations = document.querySelector('input[aria-label="Generations"]');
    assert.ok(generations);
    await flush(() => {
      Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(generations,'0');
      generations.dispatchEvent(new dom.window.Event('input',{bubbles:true}));
    });
    assert.equal(document.querySelector('[data-testid="launch-discovery-btn"]').disabled,true);
    await flush(() => stationRoot.unmount()); qc.clear(); dom.window.close();
  }
  console.log(`alpha-ui ${mode}: passed`);
}
main().then(() => { require.extensions['.ts']=oldTs; process.exit(0); }, e => { console.error(e); process.exit(1); });
''', encoding="utf-8", newline="\n")
    return root, runner


@pytest.mark.parametrize("mode", ["numeric", "pit", "transport", "events", "lifecycle"])
def test_alpha_ui_runtime_boundaries(alpha_ui_runtime, mode):
    root, runner = alpha_ui_runtime
    result = subprocess.run(
        ["node", str(runner), str(root), mode], cwd=root,
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    if result.returncode:
        pytest.fail(result.stdout + result.stderr)
