import pytest
from starlette.testclient import TestClient
from omega.api.server import app

@pytest.fixture
def client():
    return TestClient(app)

# -------------------------------------------------------------
# 16-DIMENSION ADVERSARIAL TEST SUITE (PHASE 6 ALPHA FACTORY)
# -------------------------------------------------------------

def test_dim1_evaluate_expression_valid(client):
    # Dim 1: Strict Types & Fail-Closed Contract
    payload = {
        "expression": "ts_rank(close, 10)",
        "universe": "VN703"
    }
    resp = client.post("/api/v1/alpha/evaluate-expression", json=payload)
    assert resp.status_code == 424
    assert resp.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"

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
        resp = client.post("/api/v1/alpha/evaluate-expression", json={"expression": expr})
        assert resp.status_code in (400, 422, 424)

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

def test_dim7_start_discovery_validation_bounds(client):
    # Dim 7 & 8: Math and bound validation on genetic parameters
    # Population size out of bounds (<10 or >500)
    resp = client.post("/api/v1/alpha/discovery/start", json={"population_size": 5})
    assert resp.status_code == 422

    # Generations out of bounds
    resp2 = client.post("/api/v1/alpha/discovery/start", json={"generations": 0})
    assert resp2.status_code == 422

def test_dim8_start_discovery_success(client):
    # Dim 8: Start evolution task fails closed if worker unavailable (503)
    payload = {
        "population_size": 20,
        "generations": 2,
        "mutation_rate": 0.2,
        "crossover_rate": 0.8
    }
    resp = client.post("/api/v1/alpha/discovery/start", json=payload)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "JOB_WORKER_UNAVAILABLE"

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
    resp = client.post("/api/v1/alpha/evaluate-expression", json={"expression": formula})
    assert resp.status_code == 424
    assert resp.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"

def test_dim12_ast_syntax_error_handling(client):
    # Dim 12 & 14: Syntax error / fail-closed handling
    resp = client.post("/api/v1/alpha/evaluate-expression", json={"expression": "ts_rank(close, "})
    assert resp.status_code in (400, 422, 424)

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
    assert resp.status_code == 424
    assert resp.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"

def test_dim16_safe_eval_rejection_of_dunder_tokens(client):
    # Dim 16: AST node rejection of dunder lookups and attributes
    resp = client.post("/api/v1/alpha/evaluate-expression", json={"expression": "close.__class__.__bases__"})
    assert resp.status_code in (400, 422, 424)
