"""Target portfolio contracts: authentic inputs, estimated basket NAV, fail-closed PIT."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from omega.api.routes import portfolio
from omega.api.server import app
from omega.data.calendar import VNTradingCalendar

client = TestClient(app)
AS_OF = "2026-01-30T08:30:00Z"


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    hybrid = tmp_path / "hybrid.parquet"
    market = tmp_path / "market.parquet"
    monkeypatch.setattr(portfolio, "HYBRID_EVAL_PATH", hybrid)
    monkeypatch.setattr(portfolio, "MARKET_PARQUET_PATH", market)
    candidates = pd.DataFrame([
        {"symbol": symbol, "sector": sector, "hybrid_score": 0.8,
         "adv20_billion_vnd": 25.0, "market_cap_billion_vnd": 0.01,
         "status": "ACTIVE", "as_of": AS_OF, "available_at": AS_OF}
        for symbol, sector in [("AAA", "Finance"), ("BBB", "Finance"),
                               ("CCC", "Technology"), ("DDD", "Consumer"),
                               ("EEE", "Industrial")]
    ])
    days = [day for day in pd.date_range("2025-12-01", "2026-01-30")
            if VNTradingCalendar.is_trading_day(day.to_pydatetime())][-30:]
    rows = []
    for asset, symbol in enumerate(candidates.symbol):
        for i, day in enumerate(days):
            close = int(100_000 + 700 * i + 1800 * np.sin(i * (asset + 1) / 3))
            clock = (day + pd.Timedelta(hours=15, minutes=30)).tz_localize(portfolio.ICT).isoformat()
            rows.append({"ticker": symbol, "date": day, "close": close,
                         "price_scale": "VND_FULL", "as_of": clock, "available_at": clock})
    history = pd.DataFrame(rows)
    candidates.to_parquet(hybrid, index=False)
    history.to_parquet(market, index=False)
    return hybrid, market, candidates, history


def get(endpoint="state", as_of=AS_OF, **params):
    return client.get(f"/api/v1/portfolio/{endpoint}", params={"as_of": as_of, **params})


def test_target_state_reconciles_real_basket_nav_and_cash(artifacts):
    response = get()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["account_model"] == "target_institutional_allocation"
    assert body["price_scale"] == "VND_FULL"
    assert body["weighting_method"] == "hrp"
    assert body["nav_method"] == "fixed_weight_daily_basket_estimate_not_realized_performance"
    assert body["aum_method"] == "candidate_market_cap_reference_not_broker_assets"
    assert body["total_aum_vnd"] == pytest.approx(50_000_000)
    assert sum(body["hrp_weights"].values()) == pytest.approx(1)
    assert sum(h["marketValueBillionVnd"] * 1e9 for h in body["holdings"]) + body["cash_balance_vnd"] == pytest.approx(body["total_aum_vnd"])
    assert body["unallocated_cash_vnd"] == body["total_aum_vnd"] * max(0, 1 - sum(body["hrp_weights"].values()))
    prices = artifacts[3].pivot(index="date", columns="ticker", values="close").sort_index()
    weights = pd.Series(body["hrp_weights"]).reindex(prices.columns)
    basket = prices.pct_change(fill_method=None).iloc[1:].dot(weights)
    nav = np.r_[body["total_aum_vnd"], body["total_aum_vnd"] * (1 + basket).cumprod()]
    assert [r["nav_vnd"] for r in body["nav_history"]] == pytest.approx(nav)
    assert [r["drawdown_percent"] for r in body["drawdown_series"]] == pytest.approx((nav / np.maximum.accumulate(nav) - 1) * 100)
    assert body["portfolioBeta"] is None and body["icTStat"] is None
    proof = body["provenance"]
    assert proof["is_synthetic"] is False
    assert pd.Timestamp(proof["effective_cutoff"]) == pd.Timestamp(AS_OF)
    assert pd.Timestamp(proof["max_included_available_at"]) <= pd.Timestamp(proof["effective_cutoff"])
    assert len(proof["content_hash"]) == 64


def test_dynamic_universe_deterministic_sector_cap_and_filters(artifacts):
    response = get("dynamic-universe", top_n=5, sector_cap=0.3)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["symbols"] == ["AAA", "CCC", "DDD", "EEE"]
    assert body["total_selected"] == 4
    assert max(body["sector_weights"].values()) <= 0.3
    assert sum(body["sector_weights"].values()) == pytest.approx(1)
    assert list(body["scores"]) == body["symbols"]
    assert body["selected_symbols"] == body["symbols"]
    artifacts[2].sample(frac=1, random_state=7).to_parquet(artifacts[0], index=False)
    repeated = get("dynamic-universe", top_n=5, sector_cap=0.3).json()
    repeated["provenance"].pop("computed_at")
    body["provenance"].pop("computed_at")
    assert repeated == body
    empty = get("dynamic-universe", min_adv_billion=30).json()
    assert empty["symbols"] == [] and empty["sector_weights"] == {}
    assert get("dynamic-universe", min_score=0.9).json()["symbols"] == []


@pytest.mark.parametrize("decision,expected", [
    ("2026-01-30T15:29:59+07:00", "2026-01-29T08:30:00Z"),
    ("2026-01-30T15:30:00+07:00", AS_OF),
    ("2026-01-30T16:30:00+07:00", AS_OF),
    ("2026-01-31T15:30:00+07:00", AS_OF),
    ("2026-01-01T15:30:00+07:00", "2025-12-31T08:30:00Z"),
])
def test_dim06_07_session_boundary_and_calendar(decision, expected):
    _, cutoff = portfolio._session_cutoff(datetime.fromisoformat(decision))
    assert pd.Timestamp(cutoff) == pd.Timestamp(expected)


@pytest.mark.parametrize("endpoint", ["state", "dynamic-universe"])
@pytest.mark.parametrize("value", ["2026-01-30T08:30:00", "2099-01-01T08:30:00Z", "bad", "NaN", ""])
def test_dim01_06_invalid_query_before_dependency(endpoint, value, artifacts):
    artifacts[0].unlink()
    assert get(endpoint, as_of=value).status_code == 422


@pytest.mark.parametrize("params", [
    {"min_adv_billion": "NaN"}, {"min_score": "inf"}, {"sector_cap": "-inf"},
    {"top_n": 101}, {"top_n": 0}, {"top_n": "[]"}, {"min_score": -1},
    {"min_adv_billion": 1e13}, {"sector_cap": 0},
])
def test_dim01_08_14_bounded_query_validation(artifacts, params):
    assert get("dynamic-universe", **params).status_code == 422


@pytest.mark.parametrize("endpoint", ["state", "dynamic-universe"])
@pytest.mark.parametrize("fault", ["missing", "directory", "corrupt", "bom_crlf"])
def test_dim02_03_04_dependency_faults(artifacts, endpoint, fault):
    path = artifacts[0]
    path.unlink()
    if fault == "directory":
        path.mkdir()
    elif fault == "corrupt":
        path.write_bytes(b"partial parquet")
    elif fault == "bom_crlf":
        path.write_bytes(b"\xef\xbb\xbf{}\r\n")
    response = get(endpoint)
    assert response.status_code == 424
    assert response.json() == {"detail": "DATA_DEPENDENCY_UNAVAILABLE"}


@pytest.mark.parametrize("fault", ["missing", "corrupt", "insufficient", "missing_asset", "gap", "all_asset_gap", "stale"])
def test_dim03_04_market_history_dependency(artifacts, fault):
    path, history = artifacts[1], artifacts[3].copy()
    if fault == "missing":
        path.unlink()
    elif fault == "corrupt":
        path.write_bytes(b"corrupt")
    else:
        if fault == "insufficient":
            history = history.groupby("ticker").head(20)
        elif fault == "missing_asset":
            history = history[history.ticker != "AAA"]
        elif fault == "all_asset_gap":
            history = history[history.date != sorted(history.date.unique())[1]]
        elif fault == "stale":
            history = history[history.date != history.date.max()]
        else:
            history = history.drop(history.index[0])
        history.to_parquet(path, index=False)
    response = get()
    assert response.status_code == 424
    assert response.json() == {"detail": "DATA_DEPENDENCY_UNAVAILABLE"}


@pytest.mark.parametrize("column,value", [
    ("as_of", None), ("as_of", "2026-01-30T08:30:00"),
    ("as_of", "bad"), ("as_of", "2026-01-30T08:31:00Z"),
    ("available_at", "2026-01-30T08:29:59Z"),
    ("available_at", "2026-01-30T08:30:01Z"),
])
def test_dim06_13_authenticated_timestamp_ordering(artifacts, column, value):
    frame = artifacts[2].copy()
    frame.loc[0, column] = value
    frame.to_parquet(artifacts[0], index=False)
    for endpoint in ("state", "dynamic-universe"):
        response = get(endpoint)
        assert response.status_code == 424
        assert response.json() == {"detail": "DATASET_PIT_INVALID"}


@pytest.mark.parametrize("column,value", [
    ("hybrid_score", np.nan), ("hybrid_score", np.inf), ("hybrid_score", -np.inf),
    ("hybrid_score", -1), ("hybrid_score", 2), ("hybrid_score", "0.8"),
    ("adv20_billion_vnd", -1), ("adv20_billion_vnd", 1e13),
    ("market_cap_billion_vnd", -1), ("market_cap_billion_vnd", 1e13),
    ("symbol", "AAA --config=evil"), ("symbol", "../AAA"), ("symbol", ""),
    ("sector", ""), ("status", "unknown"),
])
def test_dim01_08_12_13_invalid_candidate_values(artifacts, column, value):
    frame = artifacts[2].copy()
    if isinstance(value, str):
        frame[column] = frame[column].astype(object)
        if column == "hybrid_score":
            frame[column] = value
    frame.loc[0, column] = value
    frame.to_parquet(artifacts[0], index=False)
    assert get().status_code == 424


@pytest.mark.parametrize("fault", ["duplicate", "no_pit", "zero_aum", "overflow_aum"])
def test_dim03_08_13_candidate_integrity(artifacts, fault):
    frame = artifacts[2].copy()
    if fault == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]])
    elif fault == "no_pit":
        frame = frame.drop(columns=["available_at"]).assign(decision_cutoff=AS_OF)
    else:
        frame["market_cap_billion_vnd"] = 0 if fault == "zero_aum" else 1000
    frame.to_parquet(artifacts[0], index=False)
    assert get().status_code == 424


@pytest.mark.parametrize("column,value", [
    ("close", 0), ("close", -1), ("close", np.nan), ("close", np.inf),
    ("close", 1e13), ("close", 100_000.5), ("close", 100),
    ("price_scale", "THOUSANDS"), ("available_at", "2099-01-01T08:30:00Z"),
    ("date", "2026-01-31"),
])
def test_dim06_07_08_10_market_scale_and_pit(artifacts, column, value):
    frame = artifacts[3].copy()
    if column == "date":
        frame[column] = frame[column].astype(str)
    frame.loc[0, column] = value
    frame.to_parquet(artifacts[1], index=False)
    assert get().status_code == 424


def test_dim03_duplicate_market_shard(artifacts):
    pd.concat([artifacts[3], artifacts[3].iloc[:1]]).to_parquet(artifacts[1], index=False)
    assert get().status_code == 424


def test_dim07_unknown_calendar_coverage(artifacts, monkeypatch):
    monkeypatch.setattr(portfolio, "_get_json_holidays", lambda: {})
    assert get().json() == {"detail": "TRADING_CALENDAR_UNAVAILABLE"}


def test_dim08_zero_variance_no_invented_weights(artifacts):
    frame = artifacts[3].copy()
    frame["close"] = 100_000
    frame.to_parquet(artifacts[1], index=False)
    assert get().json() == {"detail": "DATA_DEPENDENCY_UNAVAILABLE"}


@pytest.mark.parametrize("fault", [ValueError, ImportError, ArithmeticError])
def test_hrp_fallback_is_explicit_and_history_based(artifacts, monkeypatch, fault):
    from scipy.cluster import hierarchy

    monkeypatch.setattr(hierarchy, "linkage", lambda *args, **kwargs: (_ for _ in ()).throw(fault("clustering fault")))
    response = get()
    assert response.status_code == 200
    body = response.json()
    assert body["weighting_method"] == "hrp_inverse_vol_fallback"
    prices = artifacts[3].pivot(index="date", columns="ticker", values="close").sort_index()
    inverse = 1 / prices.pct_change(fill_method=None).iloc[1:].std()
    assert body["hrp_weights"] == pytest.approx((inverse / inverse.sum()).to_dict())


def test_dim11_latest_authenticated_lifecycle_excludes_delisted(artifacts):
    frame = artifacts[2].copy()
    frame["as_of"] = "2026-01-29T08:30:00Z"
    frame["available_at"] = frame["as_of"]
    newer = artifacts[2].iloc[:1].copy()
    newer["status"] = "DELISTED"
    pd.concat([frame, newer]).to_parquet(artifacts[0], index=False)
    assert "AAA" not in get("dynamic-universe", sector_cap=1).json()["symbols"]
    assert "AAA" not in get().json()["hrp_weights"]


def test_dim05_09_read_only_concurrent_isolation(artifacts):
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts[:2]}
    queue = list(portfolio.smart_router.queue)
    schedule = list(portfolio.smart_router.schedule)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: get().json(), range(8)))
    for response in responses:
        response["provenance"].pop("computed_at")
    assert all(r == responses[0] for r in responses)
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts[:2]}
    assert portfolio.smart_router.queue == queue and portfolio.smart_router.schedule == schedule


@pytest.mark.parametrize("dimension,fault", [(15, TimeoutError), (16, RuntimeError), (23, ConnectionError)])
def test_dim15_16_23_dependency_faults_bounded_secret_safe(artifacts, monkeypatch, dimension, fault):
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise fault("https://user:SECRET@provider.invalid?token=SECRET 429")

    monkeypatch.setattr(portfolio.pd, "read_parquet", fail)
    response = get()
    assert response.status_code == 424 and len(calls) == 1
    assert "SECRET" not in response.text
    assert response.json() == {"detail": "DATA_DEPENDENCY_UNAVAILABLE"}


def test_dim14_pre_materialization_resource_bounds(artifacts, monkeypatch):
    monkeypatch.setattr(portfolio, "MAX_PORTFOLIO_BYTES", 1)
    monkeypatch.setattr(portfolio.pd, "read_parquet", lambda *args, **kwargs: pytest.fail("must reject before read"))
    assert get().status_code == 424


def test_dim14_pre_materialization_row_bounds(artifacts, monkeypatch):
    monkeypatch.setattr(portfolio, "MAX_PORTFOLIO_ROWS", 1)
    monkeypatch.setattr(portfolio.pd, "read_parquet", lambda *args, **kwargs: pytest.fail("must reject before read"))
    assert get().status_code == 424


def test_dim19_20_provenance_digest_changes_with_authentic_inputs(artifacts):
    first = get().json()["provenance"]
    frame = artifacts[2].copy()
    frame.loc[0, "hybrid_score"] = 0.81
    frame.to_parquet(artifacts[0], index=False)
    second = get().json()["provenance"]
    assert first["content_hash"] != second["content_hash"]
    assert first["dataset_id"] == second["dataset_id"] == "target_portfolio_state"
    assert first["effective_cutoff"] == second["effective_cutoff"]


@pytest.mark.parametrize("dimension", [17, 18, 21, 22, 24])
def test_orchestration_dimensions_not_consumed_or_published(artifacts, dimension):
    """Read routes accept no JEV decisions, roles, models, locks, or publication paths."""
    before = {path: path.read_bytes() for path in artifacts[:2]}
    result = client.get("/api/v1/portfolio/state", params={
        "as_of": AS_OF, "role_id": "-1", "model": "foreign-tier", "risk": "invalid",
        "gate": "replay", "session_id": "replay", "token": "SECRET", "output_path": "../escape",
    })
    assert result.status_code == 200
    assert "SECRET" not in result.text and "replay" not in result.text
    assert before == {path: path.read_bytes() for path in artifacts[:2]}


@pytest.mark.parametrize("count,status", [(20, 424), (21, 200)])
def test_history_threshold_exactly_twenty_returns(artifacts, count, status):
    artifacts[3].groupby("ticker").tail(count).to_parquet(artifacts[1], index=False)
    assert get().status_code == status


def test_sector_cap_no_feasible_nonempty_basket(artifacts):
    frame = artifacts[2].copy()
    frame["sector"] = "Finance"
    frame.to_parquet(artifacts[0], index=False)
    body = get("dynamic-universe", sector_cap=0.3).json()
    assert body["symbols"] == []
    assert get("dynamic-universe", sector_cap=1).json()["symbols"] == list(frame.symbol)


def test_dim08_nav_overflow_is_rejected(artifacts):
    frame = artifacts[2].copy()
    frame["market_cap_billion_vnd"] = 200
    frame.to_parquet(artifacts[0], index=False)
    assert get().json() == {"detail": "DATA_SCHEMA_INVALID"}


def test_dim14_filtered_market_rows_checked_before_materialization(artifacts, monkeypatch):
    monkeypatch.setattr(portfolio, "MAX_PORTFOLIO_ROWS", 100)
    read = portfolio.pd.read_parquet
    calls = []

    def bounded(path, **kwargs):
        calls.append(path)
        assert path != artifacts[1], "oversized filtered market must not materialize"
        return read(path, **kwargs)

    monkeypatch.setattr(portfolio.pd, "read_parquet", bounded)
    assert get().status_code == 424
    assert calls == [artifacts[0]]
