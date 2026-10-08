"""Strategy Lab contracts: real persisted inputs, fail-closed PIT, 24 dimensions."""
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from scipy.stats import kurtosis, norm, skew

from omega.api.routes import quant
from omega.data.calendar import VNTradingCalendar


CUTOFF = "2023-12-31T08:30:00+00:00"
ENDPOINTS = ["overfitting-diagnostics", "strategy-equity-curve"]


def trading_dates(count=48):
    return [d for d in pd.date_range("2023-03-01", "2023-06-30")
            if VNTradingCalendar.is_trading_day(d)][:count]


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def persist(path, payload):
    path.write_bytes(json.dumps({"payload": payload, "content_sha256": hashlib.sha256(canonical(payload)).hexdigest()}).encode())


@pytest.fixture
def strategy(tmp_path, monkeypatch):
    monkeypatch.setattr(quant, "STRATEGY_RESULT_ROOT", tmp_path)
    observations = []
    for i, day in enumerate(trading_dates()):
        close = quant._session_close(day.date())
        decision = quant._session_close(VNTradingCalendar.prev_trading_day(day.date()))
        observations.append({
            "as_of": close.isoformat(), "available_at": close.isoformat(),
            "signal_available_at": decision.isoformat(), "decision_time": decision.isoformat(),
            "gross_returns": [0.012 * np.sin(i * 1.4) + 0.001, 0.008 * np.cos(i * 1.1) - 0.0005,
                              0.01 * np.sin(i * 0.7) + 0.0004],
            "fee_returns": [0.0002, 0.0003, 0.0001], "benchmark_return": 0.006 * np.cos(i * 0.8),
        })
    payload = dict(schema_version="strategy_lab_v1", strategy_id="TEST_STRATEGY", source="recorded_backtest",
                   price_scale="VND_FULL", initial_capital=1_000_000_000.0, benchmark_id="VNINDEX",
                   trial_ids=["TRIAL_A", "TRIAL_B", "TRIAL_C"], selected_trial="TRIAL_A", observations=observations)
    path = tmp_path / "TEST_STRATEGY.json"
    persist(path, payload)
    app = FastAPI()
    app.include_router(quant.router)
    app.dependency_overrides[quant.job_service_dependency] = lambda: None
    with TestClient(app) as client:
        yield client, path, payload


def get(client, endpoint, **params):
    return client.get(f"/api/v1/quant/{endpoint}", params={"strategy_id": "TEST_STRATEGY", "as_of": CUTOFF, **params})


def test_diagnostics_empirical_psr_dsr_pbo_and_distribution(strategy):
    client, path, payload = strategy
    response = get(client, ENDPOINTS[0], trials_tested=3)
    assert response.status_code == 200, response.text
    data = response.json()
    net = np.array([r["gross_returns"] for r in payload["observations"]]) - np.array([r["fee_returns"] for r in payload["observations"]])
    trial_sr = net.mean(axis=0) / net.std(axis=0, ddof=1)
    r = net[:, 0]
    sr = trial_sr[0]
    variance = (1 - skew(r, bias=False) * sr + (kurtosis(r, fisher=False, bias=False) - 1) / 4 * sr ** 2) / (len(r) - 1)
    expected = np.std(trial_sr, ddof=1) * ((1 - 0.5772156649015329) * norm.ppf(1 - 1 / 3)
                                        + 0.5772156649015329 * norm.ppf(1 - 1 / (3 * np.e)))
    assert data["probabilistic_sharpe_ratio"] == pytest.approx(norm.cdf(sr / np.sqrt(variance)))
    assert data["deflated_sharpe_ratio"] == pytest.approx(norm.cdf((sr - expected) / np.sqrt(variance)))
    assert data["variance_of_trials"] == pytest.approx(trial_sr.var(ddof=1))
    assert data["observed_sharpe"] == pytest.approx(sr)
    assert len(data["trial_distribution"]) == 3
    assert data["fdr_q_values"] == []
    assert 0 <= data["pbo"] <= 1
    assert data["provenance"] is None
    assert data["provenance_verification"] == "CONTENT_INTEGRITY_ONLY_NOT_AUTHENTICATED_LINEAGE"
    assert data["input_integrity"]["content_sha256"] == hashlib.sha256(canonical(payload)).hexdigest()
    assert get(client, ENDPOINTS[0], trials_tested=20).status_code == 422


def test_equity_net_gross_fees_drawdown_benchmark(strategy):
    client, path, payload = strategy
    response = get(client, ENDPOINTS[1])
    assert response.status_code == 200, response.text
    data = response.json()
    gross = np.array([r["gross_returns"][0] for r in payload["observations"]])
    fees = np.array([r["fee_returns"][0] for r in payload["observations"]])
    net = 1e9 * np.r_[1, np.cumprod(1 + gross - fees)]
    gross_nav = 1e9 * np.r_[1, np.cumprod(1 + gross)]
    bench = 1e9 * np.r_[1, np.cumprod(1 + np.array([r["benchmark_return"] for r in payload["observations"]]))]
    assert [p["net_equity"] for p in data["equity_curve"]] == pytest.approx(net)
    assert [p["gross_equity"] for p in data["equity_curve"]] == pytest.approx(gross_nav)
    assert [p["benchmark_equity"] for p in data["equity_curve"]] == pytest.approx(bench)
    assert [p["drawdown_pct"] for p in data["equity_curve"]] == pytest.approx((net / np.maximum.accumulate(net) - 1) * 100)
    assert data["total_fees_vnd"] == pytest.approx(np.sum(net[:-1] * fees))
    assert data["price_scale"] == "VND_FULL"
    assert data["benchmark_id"] == "VNINDEX"


@pytest.mark.parametrize("value", [None, "NaN", "Inf", "-Inf", [], True, 1e13, -1.0])
@pytest.mark.parametrize("field", ["gross_returns", "fee_returns"])
def test_dim01_numeric_trust_boundary(strategy, field, value):
    client, path, payload = strategy
    payload["observations"][0][field][0] = value
    persist(path, payload)
    for endpoint in ENDPOINTS:
        assert get(client, endpoint).status_code == 424


@pytest.mark.parametrize("kind", ["missing", "directory", "utf8", "bom", "partial", "duplicate_json", "digest", "crlf"])
def test_dim02_dim03_artifact_integrity(strategy, kind):
    client, path, payload = strategy
    if kind == "missing":
        path.unlink()
    elif kind == "directory":
        path.unlink()
        path.mkdir()
    elif kind == "crlf":
        document = json.loads(path.read_bytes())
        path.write_bytes(json.dumps(document, indent=2).replace("\n", "\r\n").encode())
    else:
        raw = path.read_bytes()
        raw = {"utf8": b"\xff", "bom": b"\xef\xbb\xbf" + raw, "partial": raw[:100],
               "duplicate_json": b'{"payload":{},"payload":{}}',
               "digest": raw.replace(b'"content_sha256": "', b'"content_sha256": "0', 1)}[kind]
        path.write_bytes(raw)
    for endpoint in ENDPOINTS:
        assert get(client, endpoint).status_code == (200 if kind == "crlf" else 424)


def test_dim04_dim05_fail_closed_read_without_mutation(strategy, monkeypatch):
    client, path, payload = strategy
    before = path.read_bytes()
    original = Path.open
    def fail_open(self, *args, **kwargs):
        if self == path:
            raise OSError("https://user:private@host.example?token=private")
        return original(self, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_open)
        for endpoint in ENDPOINTS:
            response = get(client, endpoint)
            assert response.status_code == 424
            assert "private" not in response.text
    assert path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["future", "naive", "late_signal", "same_close_decision", "wrong_close", "reversed_clocks"])
def test_dim06_pit_and_session_boundaries(strategy, mutation):
    client, path, payload = strategy
    row = payload["observations"][0]
    if mutation == "future":
        row["available_at"] = "2024-01-01T00:00:00+00:00"
    elif mutation == "naive":
        row["as_of"] = row["as_of"][:-6]
    elif mutation == "late_signal":
        row["signal_available_at"] = row["as_of"]
    elif mutation == "same_close_decision":
        row["decision_time"] = row["as_of"]
    elif mutation == "wrong_close":
        row["as_of"] = row["available_at"] = "2023-03-01T08:29:59+00:00"
    else:
        row["available_at"] = "2023-03-01T08:29:59+00:00"
    persist(path, payload)
    for endpoint in ENDPOINTS:
        assert get(client, endpoint).status_code == 424


def test_dim06_inclusive_cutoff_timezone_equivalence(strategy):
    client, path, payload = strategy
    close = payload["observations"][-1]["available_at"]
    assert get(client, ENDPOINTS[1], as_of=close).status_code == 200
    instant = datetime.fromisoformat(close)
    assert get(client, ENDPOINTS[1], as_of=(instant - timedelta(microseconds=1)).isoformat()).status_code == 424
    assert get(client, ENDPOINTS[1], as_of=instant.astimezone(quant.ICT).isoformat()).status_code == 200
    assert get(client, ENDPOINTS[1], as_of="2023-12-31").status_code == 422
    assert get(client, ENDPOINTS[1], as_of="2099-01-01T00:00:00Z").status_code == 422


@pytest.mark.parametrize("day", ["2023-03-04", "2023-04-30", "2030-03-01"])
def test_dim07_calendar_holidays_and_coverage(strategy, day):
    client, path, payload = strategy
    payload["observations"][0]["as_of"] = payload["observations"][0]["available_at"] = day + "T08:30:00+00:00"
    persist(path, payload)
    assert get(client, ENDPOINTS[1]).status_code == 424


def test_dim08_undefined_metrics_and_first_loss_drawdown(strategy):
    client, path, payload = strategy
    for row in payload["observations"]:
        row["gross_returns"] = [-0.01, -0.01, -0.01]
        row["fee_returns"] = [0.0, 0.0, 0.0]
    persist(path, payload)
    diagnostics = get(client, ENDPOINTS[0]).json()
    assert diagnostics["pbo"] is None
    assert diagnostics["probabilistic_sharpe_ratio"] is None
    assert diagnostics["is_overfitted"] is True
    assert get(client, ENDPOINTS[1]).json()["equity_curve"][1]["drawdown_pct"] == pytest.approx(-1)


def test_dim08_overflow_fail_closed(strategy):
    client, path, payload = strategy
    for row in payload["observations"]:
        row["gross_returns"] = [1e12, 1e12, 1e12]
    persist(path, payload)
    for endpoint in ENDPOINTS:
        assert get(client, endpoint).status_code == 424


def test_dim09_dim22_concurrent_read_isolation(strategy):
    client, path, payload = strategy
    before = path.read_bytes()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: get(client, ENDPOINTS[1]).json(), range(8)))
    assert all(r["equity_curve"] == results[0]["equity_curve"] for r in results)
    assert path.read_bytes() == before


@pytest.mark.parametrize("scale", ["VND_THOUSAND", "VND", None, 1000])
def test_dim10_reject_scale_confusion(strategy, scale):
    client, path, payload = strategy
    payload["price_scale"] = scale
    persist(path, payload)
    assert get(client, ENDPOINTS[1]).status_code == 424


@pytest.mark.parametrize("mutation", ["duplicate", "gap", "missing_trial", "missing_fees", "missing_benchmark", "trial_alias"])
def test_dim11_dim13_no_survivorship_or_schema_substitution(strategy, mutation):
    client, path, payload = strategy
    if mutation == "duplicate":
        payload["observations"][1] = copy.deepcopy(payload["observations"][0])
    elif mutation == "gap":
        del payload["observations"][1]
    elif mutation == "missing_trial":
        payload["observations"][0]["gross_returns"].pop()
    elif mutation == "trial_alias":
        payload["trial_ids"][1] = payload["trial_ids"][0]
    else:
        del payload["observations"][0]["fee_returns" if mutation == "missing_fees" else "benchmark_return"]
    persist(path, payload)
    for endpoint in ENDPOINTS:
        assert get(client, endpoint).status_code == 424


@pytest.mark.parametrize("identifier", ["../secret", "--config=secret", "X;whoami", "https://user:secret@example.com", "X" * 65])
def test_dim12_dim16_identifiers_and_secret_safe_errors(strategy, identifier):
    client, path, payload = strategy
    for endpoint in ENDPOINTS:
        response = get(client, endpoint, strategy_id=identifier)
        assert response.status_code == 422
        assert response.json()["detail"] == "INVALID_STRATEGY_ID"
        assert identifier not in response.text


def test_dim14_bounded_artifact_and_response(strategy, monkeypatch):
    client, path, payload = strategy
    monkeypatch.setattr(quant, "MAX_STRATEGY_BYTES", 100)
    assert get(client, ENDPOINTS[1]).status_code == 424
    assert client.post("/api/v1/quant/walk-forward", json={"universe": ["FPT"] * 101}).status_code == 422
    assert get(client, ENDPOINTS[0], trials_tested=101).status_code == 422


def test_dim15_dim23_no_provider_retry_or_synthetic_fallback(strategy, monkeypatch):
    client, path, payload = strategy
    path.unlink()
    def provider_forbidden(*args, **kwargs):
        raise AssertionError("missing strategy must not invoke market/provider fallback")
    monkeypatch.setattr(quant, "load_market_dataset", provider_forbidden)
    for endpoint in ENDPOINTS:
        assert get(client, endpoint).status_code == 424


@pytest.mark.parametrize("field", ["role_id", "risk", "model", "gate", "session_id", "dispatch_token", "lease_owner_id", "fallback_model"])
def test_dim17_dim18_dim19_dim20_dim24_governance_metadata_cannot_promote_data(strategy, field):
    client, path, payload = strategy
    payload[field] = "UNTRUSTED"
    persist(path, payload)
    for endpoint in ENDPOINTS:
        response = get(client, endpoint)
        assert response.status_code == 424
        assert "UNTRUSTED" not in response.text


def test_dim20_digest_identity_binding(strategy):
    client, path, payload = strategy
    payload["strategy_id"] = "OTHER_STRATEGY"
    persist(path, payload)
    assert get(client, ENDPOINTS[1]).status_code == 424
    persist(path, {**payload, "strategy_id": "TEST_STRATEGY"})
    document = json.loads(path.read_bytes())
    document["payload"]["observations"][0]["gross_returns"][0] += 0.01
    path.write_text(json.dumps(document), encoding="utf-8")
    assert get(client, ENDPOINTS[1]).status_code == 424


def test_dim21_no_publication_or_rollback_surface(strategy, monkeypatch):
    client, path, payload = strategy
    before = path.read_bytes()
    monkeypatch.setattr(Path, "write_bytes", lambda *a, **k: pytest.fail("GET attempted publication"))
    monkeypatch.setattr(Path, "replace", lambda *a, **k: pytest.fail("GET attempted atomic replacement"))
    assert get(client, ENDPOINTS[1]).status_code == 200
    assert path.read_bytes() == before


@pytest.fixture
def market(strategy, monkeypatch):
    client, path, payload = strategy
    rows = []
    for i, day in enumerate(trading_dates(72)):
        close = quant._session_close(day.date())
        for ticker, offset in [("FPT", 0), ("HPG", 5000)]:
            rows.append(dict(ticker=ticker, date=day, close=50000.0 + offset + i * 100 + 400 * np.sin(i),
                             as_of=close, available_at=close, source="recorded_market", price_scale="VND_FULL"))
    frame = pd.DataFrame(rows)
    monkeypatch.setattr(quant, "load_market_dataset", lambda **kwargs: frame.copy())
    body = dict(universe=["FPT", "HPG"], start_date="2023-03-01", end_date=frame["date"].max().strftime("%Y-%m-%d"),
                n_splits=4, n_test_splits=1, label_horizon=2, embargo_pct=0.01, as_of=CUTOFF,
                evaluation_method="CHRONOLOGICAL_WALK_FORWARD")
    return client, frame, body


def test_walk_forward_chronological_purge_embargo_compounded_oos(market):
    client, frame, body = market
    response = client.post("/api/v1/quant/walk-forward", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_folds"] == 3
    assert data["pbo"] is None and data["deflated_sharpe_ratio"] is None
    for fold in data["folds"]:
        assert fold["train_end"] < fold["train_label_end"] <= fold["decision_time"] < fold["test_start"]
        assert fold["purged_size"] == 2
        assert fold["embargo_size"] == 1
        assert fold["test_size"] == fold["oos_observations"]
    prices = frame.pivot(index="date", columns="ticker", values="close").sort_index()
    daily = prices.pct_change(fill_method=None).iloc[1:].mean(axis=1).to_numpy()
    blocks = np.array_split(np.arange(len(daily)), 4)
    idx = np.concatenate(blocks[1:])
    expected = (np.prod(1 + daily[idx] - 0.00065) - 1) * 100
    assert data["oos_return_pct"] == pytest.approx(expected)
    assert data["strategy_definition"] == "FIXED_EQUAL_WEIGHT_DAILY_REBALANCE"


def test_pbo_is_selected_trial_rank_not_complement_of_dsr():
    from itertools import combinations
    rng = np.random.default_rng(19)
    net = rng.normal(0.0002, 0.01, (64, 4))
    result = quant._strategy_diagnostics(net, 0)
    outcomes = []
    blocks = np.array_split(np.arange(64), 8)
    for combo in combinations(range(8), 4):
        train = net[np.concatenate([blocks[i] for i in combo])]
        test = net[np.concatenate([blocks[i] for i in range(8) if i not in combo])]
        winner = np.argmax(train.mean(axis=0) / train.std(axis=0, ddof=1))
        scores = test.mean(axis=0) / test.std(axis=0, ddof=1)
        rank = sum(scores < scores[winner]) + 0.5 * sum(scores == scores[winner])
        outcomes.append(rank <= len(scores) / 2)
    assert result["pbo"] == pytest.approx(np.mean(outcomes))
    assert result["pbo"] != pytest.approx(1 - result["dsr"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_dim01_raw_nonfinite_json_rejected(strategy, value):
    client, path, payload = strategy
    payload["observations"][0]["gross_returns"][0] = value
    path.write_text(json.dumps({"payload": payload, "content_sha256": "a" * 64}), encoding="utf-8")
    for endpoint in ENDPOINTS:
        assert get(client, endpoint).status_code == 424


def test_walk_forward_missing_delisted_last_bar_rejected(market):
    client, frame, body = market
    frame.drop(frame.index[-1], inplace=True)
    assert client.post("/api/v1/quant/walk-forward", json=body).status_code == 424


def test_walk_forward_missing_terminal_session_rejected(market):
    client, frame, body = market
    frame.drop(frame[frame["date"] == frame["date"].max()].index, inplace=True)
    assert client.post("/api/v1/quant/walk-forward", json=body).status_code == 424


def test_cpcv_combinatorial_folds_purge_embargo_and_truthful_mode(market):
    client, frame, body = market
    body.pop("evaluation_method")
    body.update(n_splits=6, n_test_splits=2)
    response = client.post("/api/v1/quant/walk-forward", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_folds"] == 15
    assert data["evaluation_method"] == "COMBINATORIAL_PURGED_K_FOLD"
    assert data["historical_pit_verified"] is False
    assert data["provenance"] is None
    assert data["coverage_policy"] == "COMPLETE_CASE_INTERSECTION"
    for fold in data["folds"]:
        train = np.array(fold["train_indices"])
        test = np.array(fold["test_indices"])
        assert fold["decision_time"] is None
        assert not set(train) & set(test)
        assert all(abs(int(a) - int(b)) > body["label_horizon"] for a in train for b in test)
        assert fold["train_size"] == len(train)
        assert fold["test_size"] == len(test)
    assert len({tuple(f["test_indices"]) for f in data["folds"]}) == 15


def test_cpcv_retrospective_metadata_and_disclosed_missing_sessions(market):
    client, frame, body = market
    frame["as_of"] = frame["available_at"] = pd.Timestamp("2023-12-01T08:30:00Z")
    frame.drop(frame.index[5], inplace=True)
    assert client.post("/api/v1/quant/walk-forward", json=body).status_code == 424
    body["evaluation_method"] = "COMBINATORIAL_PURGED_K_FOLD"
    response = client.post("/api/v1/quant/walk-forward", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["excluded_incomplete_sessions"] == 1
    assert response.json()["historical_pit_verified"] is False
    frame["available_at"] = pd.Timestamp("2024-01-01T00:00:00Z")
    assert client.post("/api/v1/quant/walk-forward", json=body).status_code == 424


def test_cpcv_fold_resource_limit(market):
    client, frame, body = market
    body.update(evaluation_method="COMBINATORIAL_PURGED_K_FOLD", n_splits=20, n_test_splits=5)
    assert client.post("/api/v1/quant/walk-forward", json=body).status_code == 422


@pytest.fixture
def market_proxy(market, monkeypatch):
    client, frame, body = market
    from omega.api.routes import control
    monkeypatch.setitem(control.STRATEGY_REGISTRY, "TEST_STRATEGY", {
        "universe": body["universe"], "start_date": body["start_date"], "end_date": body["end_date"],
    })
    path = quant.STRATEGY_RESULT_ROOT / "TEST_STRATEGY.json"
    path.unlink()
    return client, frame, body, path


def test_missing_strategy_fallback_empirical_actual_trial_count(market_proxy):
    client, frame, body, path = market_proxy
    response = get(client, ENDPOINTS[0], trials_tested=20)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["trials_tested"] == 2
    assert data["requested_trials_tested"] == 20
    assert data["diagnostic_basis"] == "EMPIRICAL_INSTRUMENT_PROXY"
    assert data["provenance"] is None
    assert data["provenance_verification"] == "EMPIRICAL_MARKET_PROXY_NOT_STRATEGY_EVIDENCE"
    assert len(data["trial_distribution"]) == 2
    assert 0 <= data["deflated_sharpe_ratio"] <= 1
    assert 0 <= data["pbo"] <= 1
    assert data["fdr_q_values"] == []
    assert not path.exists()
    assert get(client, ENDPOINTS[0], trials_tested=20).json()["deflated_sharpe_ratio"] == data["deflated_sharpe_ratio"]
    assert get(client, ENDPOINTS[1]).status_code == 424


@pytest.mark.parametrize("kind", ["directory", "corrupt", "timeout", "future", "invalid_cutoff", "unknown"])
def test_market_fallback_only_missing_not_corrupt_or_provider_failure(market_proxy, monkeypatch, kind):
    client, frame, body, path = market_proxy
    if kind == "directory":
        path.mkdir()
    elif kind == "corrupt":
        path.write_bytes(b"partial JSON")
    elif kind == "timeout":
        def unavailable(**kwargs):
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail="MARKET_DATASET_UNAVAILABLE")
        monkeypatch.setattr(quant, "load_market_dataset", unavailable)
    elif kind == "future":
        frame["available_at"] = pd.Timestamp("2024-01-01T00:00:00Z")
    elif kind == "invalid_cutoff":
        assert get(client, ENDPOINTS[0], as_of="2020-01-01T08:30:00Z").status_code == 422
        return
    else:
        assert get(client, ENDPOINTS[0], strategy_id="UNKNOWN_STRATEGY").status_code == 424
        return
    assert get(client, ENDPOINTS[0]).status_code == (503 if kind == "timeout" else 424)


def test_market_fallback_concurrent_read_no_publication(market_proxy):
    client, frame, body, path = market_proxy
    before = frame.copy(deep=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: get(client, ENDPOINTS[0]).json(), range(6)))
    assert all(r["deflated_sharpe_ratio"] == results[0]["deflated_sharpe_ratio"] for r in results)
    pd.testing.assert_frame_equal(frame, before)
    assert not path.exists()


def test_walk_forward_future_perturbation_does_not_change_earlier_fold(market):
    client, frame, body = market
    before = client.post("/api/v1/quant/walk-forward", json=body).json()
    last_date = frame["date"].max()
    frame.loc[frame["date"] == last_date, "close"] *= 1.02
    after = client.post("/api/v1/quant/walk-forward", json=body).json()
    assert before["folds"][0] == after["folds"][0]


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "scale", "late", "nan", "zero", "bool", "holiday"])
def test_walk_forward_market_boundary_fail_closed(market, mutation):
    client, frame, body = market
    if mutation == "duplicate":
        frame.loc[len(frame)] = frame.iloc[0]
    elif mutation == "missing":
        frame.drop(frame.index[0], inplace=True)
    elif mutation == "scale":
        frame.loc[0, "price_scale"] = "VND_THOUSAND"
    elif mutation == "late":
        frame.loc[0, "available_at"] += timedelta(microseconds=1)
    elif mutation == "holiday":
        frame.loc[0, "date"] = pd.Timestamp("2023-03-04")
    else:
        frame["close"] = frame["close"].astype(object) if mutation == "bool" else frame["close"]
        frame.loc[0, "close"] = {"nan": float("nan"), "zero": 0.0, "bool": True}[mutation]
    response = client.post("/api/v1/quant/walk-forward", json=body)
    assert response.status_code == 424, response.text


@pytest.mark.parametrize("change", [{"universe": []}, {"universe": ["FPT", "FPT"]}, {"initial_capital": 1e13},
                                   {"price_scale": "VND_THOUSAND"}, {"dataset_id": "other"},
                                   {"as_of": "2023-03-01T08:29:59Z"}, {"n_splits": "4"},
                                   {"commission_bps": "NaN"}, {"role_id": 9}])
def test_walk_forward_strict_request(market, change):
    client, frame, body = market
    assert client.post("/api/v1/quant/walk-forward", json={**body, **change}).status_code == 422
