import pytest
from pathlib import Path
from starlette.testclient import TestClient
from omega.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


# --- 16-Dimension Master Adversarial Matrix Test Suite for Chart Station ---

def test_market_ohlcv_default(client):
    # Dimension 1: Strict Types & Valid Schema Response
    response = client.get("/api/v1/market/ohlcv/FPT")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["symbol"] == "FPT"
    assert "bars" in data
    assert len(data["bars"]) > 0
    bar = data["bars"][-1]
    assert "time" in bar
    assert "open" in bar
    assert "high" in bar
    assert "low" in bar
    assert "close" in bar
    assert "volume" in bar


def test_market_ohlcv_case_insensitivity_and_whitespace(client):
    # Dimension 10: Case-Insensitive Symbol Deduplication & Canonicalization
    response_lower = client.get("/api/v1/market/ohlcv/fpt")
    assert response_lower.status_code == 200
    data_lower = response_lower.json()
    assert data_lower["symbol"] == "FPT"

    response_space = client.get("/api/v1/market/ohlcv/%20hpg%20")
    assert response_space.status_code == 200
    data_space = response_space.json()
    assert data_space["symbol"] == "HPG"


def test_market_ohlcv_date_filtering(client):
    # Dimension 6: Point-in-Time (PIT) & Date Filtering
    response = client.get("/api/v1/market/ohlcv/FPT?start=2024-01-01&end=2024-03-31")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    for b in data["bars"]:
        assert "2024-01-01" <= b["time"] <= "2024-03-31"


def test_market_ohlcv_limit_bounds(client):
    # Dimension 4 & 8: Memory Bounds & Extreme Parameter Defenses
    response = client.get("/api/v1/market/ohlcv/FPT?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["bars"]) <= 10

    # Test invalid limit (0 or > 5000)
    res_zero = client.get("/api/v1/market/ohlcv/FPT?limit=0")
    assert res_zero.status_code == 422
    res_overflow = client.get("/api/v1/market/ohlcv/FPT?limit=99999")
    assert res_overflow.status_code == 422


def test_market_ohlcv_invalid_dates(client):
    # Dimension 1 & 14: Malformed Date Inputs
    res = client.get("/api/v1/market/ohlcv/FPT?start=invalid-date")
    assert res.status_code == 422


def test_market_ohlcv_nonexistent_symbol(client):
    # Dimension 10 & 11: Empty set handling for unknown symbols
    response = client.get("/api/v1/market/ohlcv/UNKNOWN999XYZ")
    assert response.status_code == 200
    data = response.json()
    assert data["total_bars"] == 0
    assert data["bars"] == []


def test_market_ohlcv_missing_file_fail_closed(monkeypatch, client):
    # Dimension 2 & 11: Fail-Closed on Missing Dataset
    from omega.api.routes import market
    monkeypatch.setattr(market, "MARKET_PARQUET_PATH", Path("nonexistent_market.parquet"))
    response = client.get("/api/v1/market/ohlcv/FPT")
    assert response.status_code == 404


def test_market_orderbook_default(client):
    # Dimension 1 & 9: Orderbook Financial Structure & Fail-Closed Real Data Contract
    response = client.get("/api/v1/market/orderbook/FPT")
    assert response.status_code == 503
    assert response.json()["detail"] == "REAL_L2_FEED_UNAVAILABLE"


def test_market_orderbook_depth_param(client):
    # Dimension 4 & 8: Orderbook Depth Boundaries & Fail-Closed
    response = client.get("/api/v1/market/orderbook/MBB?depth=5")
    assert response.status_code == 503
    assert response.json()["detail"] == "REAL_L2_FEED_UNAVAILABLE"


def test_market_orderbook_invalid_depth(client):
    # Dimension 1 & 8: Strict Validation on Depth Range
    res_zero = client.get("/api/v1/market/orderbook/MBB?depth=0")
    assert res_zero.status_code == 422
    res_over = client.get("/api/v1/market/orderbook/MBB?depth=50")
    assert res_over.status_code == 422


def test_market_orderbook_empty_symbol(client):
    # Dimension 1: Strict Validation on Empty Symbol
    response = client.get("/api/v1/market/orderbook/%20")
    assert response.status_code == 422


def test_market_orderbook_spread_and_depth(client):
    # Dimension 8 & 9: Fail-closed verification
    response = client.get("/api/v1/market/orderbook/HPG")
    assert response.status_code == 503
    assert response.json()["detail"] == "REAL_L2_FEED_UNAVAILABLE"


def test_market_orderbook_utc_timestamp(client):
    # Dimension 6: Temporal clocks & fail-closed contract
    response = client.get("/api/v1/market/orderbook/FPT")
    assert response.status_code == 503
    assert response.json()["detail"] == "REAL_L2_FEED_UNAVAILABLE"
