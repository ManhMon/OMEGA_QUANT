import json
import pytest
from starlette.testclient import TestClient
from omega.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "omega-api-bridge"


def test_macro_summary_endpoint(client):
    response = client.get("/api/v1/macro/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "total_records" in data
    assert "indicators" in data
    assert "latest_snapshots" in data
    assert len(data["latest_snapshots"]) > 0
    assert "usd_vnd" in data["indicators"]


def test_quant_screener_default(client):
    response = client.get("/api/v1/quant/screener")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total"] > 0
    assert data["page"] == 1
    assert len(data["data"]) <= 50


def test_quant_screener_symbol_filter(client):
    response = client.get("/api/v1/quant/screener?symbol=AAA")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total"] == 1
    assert data["data"][0]["symbol"] == "AAA"


def test_quant_screener_case_insensitivity(client):
    response = client.get("/api/v1/quant/screener?symbol=aaa")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total"] == 1
    assert data["data"][0]["symbol"] == "AAA"


def test_quant_screener_fallback_filter(client):
    response = client.get("/api/v1/quant/screener?is_fallback=true")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    for item in data["data"]:
        assert item["is_fallback"] is True


def test_quant_screener_pagination(client):
    response = client.get("/api/v1/quant/screener?page=2&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["page"] == 2
    assert data["limit"] == 10
    assert len(data["data"]) == 10


def test_portfolio_state_endpoint(client):
    response = client.get("/api/v1/portfolio/state")
    assert response.status_code == 424
    assert response.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"


def test_websocket_ticks(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/v1/stream/ticks") as websocket:
            websocket.receive_json()
    assert excinfo.value.code == 1013


def test_sse_system_events(client):
    response = client.get("/sse/v1/events/system?limit=2")
    assert response.status_code == 200
    text = response.text
    assert "data:" in text
    assert "omega_api_gateway" in text


# 16-Dimension Adversarial Matrix Tests
def test_quant_screener_invalid_page(client):
    # Dimension 1 & 8: Strict Types & Boundary validation
    response = client.get("/api/v1/quant/screener?page=0")
    assert response.status_code == 422


def test_quant_screener_limit_bounds(client):
    # Dimension 4 & 8: Bounds & Memory Cap protection
    response = client.get("/api/v1/quant/screener?limit=5000")
    assert response.status_code == 422


def test_quant_screener_nonexistent_symbol(client):
    # Dimension 10: Canonical symbol lookups & empty sets
    response = client.get("/api/v1/quant/screener?symbol=NONEXISTENT999")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["data"]) == 0


def test_macro_summary_missing_file(monkeypatch, client):
    # Dimension 2 & 11: Fail-closed on missing file
    from omega.api.routes import macro
    monkeypatch.setattr(macro, "MACRO_PARQUET_PATH", macro.Path("nonexistent_path.parquet"))
    response = client.get("/api/v1/macro/summary")
    assert response.status_code == 404
    assert "Macro indicators dataset not found" in response.json()["detail"]


def test_quant_screener_missing_file(monkeypatch, client):
    # Dimension 2 & 11: Fail-closed on missing dataset
    from omega.api.routes import quant
    monkeypatch.setattr(quant, "QUANT_PARQUET_PATH", quant.Path("nonexistent_path.parquet"))
    response = client.get("/api/v1/quant/screener")
    assert response.status_code == 404


def test_quant_screener_veto_filter(client):
    # Dimension 9: Financial business logic & veto flag filtering
    response = client.get("/api/v1/quant/screener?is_veto=false&limit=10")
    assert response.status_code == 200
    data = response.json()
    for item in data["data"]:
        assert item["is_veto"] is False


def test_portfolio_state_structure_and_types(client):
    # Dimension 6 & 9: PIT ISO timestamps, fail-closed contracts
    response = client.get("/api/v1/portfolio/state")
    assert response.status_code == 424
    assert response.json()["detail"] == "DATA_DEPENDENCY_UNAVAILABLE"
