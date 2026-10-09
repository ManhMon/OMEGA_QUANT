"""Fundamental contracts: real filings, tri-state criteria, fail-closed boundaries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from omega.api.routes import quant

CUTOFF = "2026-04-01T08:30:00Z"
ROUTES = ["screener", "fundamental/valuation-matrix", "fundamental/dupont/AAA", "fundamental/piotroski/AAA"]


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    financial = tmp_path / "financial.parquet"
    hybrid = tmp_path / "hybrid.parquet"
    monkeypatch.setattr(quant, "FINANCIAL_PARQUET_PATH", financial)
    monkeypatch.setattr(quant, "QUANT_PARQUET_PATH", hybrid)
    rows = []
    for year, income, revenue, assets, equity, debt, current_assets, shares, gross in [
        (2024, 10, 100, 100, 40, 30, 40, 100, 20),
        (2025, 30, 240, 200, 80, 40, 80, 100, 72),
    ]:
        items = {"income": income, "revenue": revenue, "assets": assets, "equity": equity,
                 "debt": debt, "current_assets": current_assets, "current_liabilities": 20,
                 "shares": shares, "gross_profit": gross, "cash_flow": income + 10}
        for name, value in items.items():
            endpoint, codes = quant.FINANCIAL_ITEMS[name]
            clock = f"{year + 1}-04-01T08:30:00Z"
            rows.append(dict(symbol="AAA", endpoint=endpoint, period_type="year", fiscal_year=year,
                fiscal_quarter=0, item_code=codes[0], item_value=float(value),
                fiscal_period_end=date(year, 12, 31), source_publish_at=clock, available_at=clock))
    statements = pd.DataFrame(rows)
    universe = pd.DataFrame([
        dict(symbol=symbol, sector="Công nghệ", exchange="HOSE", status="WATCH", pe=pe, pb=2.0,
             roe=roe, piotroski_f=8.0, altman_z=3.0, is_fallback=False, is_veto=False,
             as_of=CUTOFF, available_at=CUTOFF)
        for symbol, pe, roe in [("AAA", 12.0, 50.0), ("BBB", 0.0, 0.0), ("CCC", -2.0, -10.0),
                                ("DDD", None, 10.0), ("EEE", 10.0, None)]
    ])
    statements.to_parquet(financial, index=False)
    universe.to_parquet(hybrid, index=False)
    app = FastAPI()
    app.include_router(quant.router)
    return TestClient(app), financial, hybrid, statements, universe


def get(inputs, route=ROUTES[0], **params):
    return inputs[0].get("/api/v1/quant/" + route, params={"as_of": CUTOFF, **params})


def test_dupont_average_balances_product_and_filing_dates(inputs):
    result = get(inputs, ROUTES[2])
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "success"
    assert body["net_margin"] == pytest.approx(30 / 240)
    assert body["asset_turnover"] == pytest.approx(240 / 150)
    assert body["equity_multiplier"] == pytest.approx(150 / 60)
    assert body["roe"] == pytest.approx(body["net_margin"] * body["asset_turnover"] * body["equity_multiplier"])
    assert body["roe_percent"] == pytest.approx(50)
    assert len(body["filing_dates"]) == 2
    assert body["historical_pit_verified"] is False
    proof = body["provenance"]
    assert pd.Timestamp(proof["max_included_available_at"]) == pd.Timestamp(CUTOFF)
    assert proof["effective_cutoff"] == proof["requested_pit_cutoff"]
    assert len(proof["content_hash"]) == 64 and proof["is_synthetic"] is False


@pytest.mark.parametrize("year,equity", [(2024, 0), (2025, 0), (2024, -1), (2025, -1), (2025, -80)])
def test_dim08_nonpositive_equity_is_not_meaningful(inputs, year, equity):
    frame = inputs[3].copy()
    frame.loc[frame.fiscal_year.eq(year) & frame.item_code.eq("owners_equity"), "item_value"] = equity
    frame.to_parquet(inputs[1], index=False)
    body = get(inputs, ROUTES[2]).json()
    assert body["status"] == "not_meaningful"
    assert body["roe"] is None and body["equity_multiplier"] is None
    assert body["reason"] == "NONPOSITIVE_EQUITY"


@pytest.mark.parametrize("item,value", [("total_assets", 0), ("total_assets", -1), ("revenue", 0),
    ("revenue", -1), ("total_assets", 1e-15), ("owners_equity", 1e-15)])
def test_dim08_invalid_divisors_and_ratio_overflow(inputs, item, value):
    frame = inputs[3].copy()
    frame.loc[frame.item_code.eq(item), "item_value"] = value
    frame.to_parquet(inputs[1], index=False)
    body = get(inputs, ROUTES[2]).json()
    assert body["status"] != "success" and body["roe"] is None


def test_piotroski_nine_known_passes(inputs):
    result = get(inputs, ROUTES[3])
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["score"] == 9 and body["known_passes"] == 9 and body["unknown_count"] == 0
    assert len(body["criteria"]) == 9
    assert len({c["id"] for c in body["criteria"]}) == 9
    assert all(c["status"] == "pass" and c["reason"] is None and c["filing_dates"] for c in body["criteria"])


@pytest.mark.parametrize("fault", ["missing_income", "missing_cash", "null_value", "missing_publication", "missing_previous", "missing_balance", "unknown_symbol"])
def test_piotroski_missing_data_is_unknown_not_failure(inputs, fault):
    frame = inputs[3].copy()
    route = ROUTES[3]
    if fault == "missing_income":
        frame = frame[frame.item_code.ne("net_profit")]
    elif fault == "missing_cash":
        frame = frame[frame.endpoint.ne("cash_flow")]
    elif fault == "null_value":
        frame["item_value"] = np.nan
    elif fault == "missing_publication":
        frame["source_publish_at"] = None
    elif fault == "missing_previous":
        frame = frame[frame.fiscal_year.eq(2025)]
    elif fault == "missing_balance":
        frame = frame[frame.endpoint.ne("balance_sheet")]
    else:
        route = "fundamental/piotroski/ZZZ"
    frame.to_parquet(inputs[1], index=False)
    result = get(inputs, route)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["score"] is None and body["unknown_count"] > 0
    assert all(c["status"] != "fail" for c in body["criteria"])


def test_piotroski_known_failures_remain_failures(inputs):
    frame = inputs[3].copy()
    frame.loc[frame.fiscal_year.eq(2025) & frame.item_code.eq("net_profit"), "item_value"] = -30
    frame.loc[frame.fiscal_year.eq(2025) & frame.item_code.eq("operating_cash_flow"), "item_value"] = -40
    frame.to_parquet(inputs[1], index=False)
    body = get(inputs, ROUTES[3]).json()
    status = {c["id"]: c["status"] for c in body["criteria"]}
    assert status["positive_roa"] == status["positive_operating_cash_flow"] == "fail"
    assert status["improved_roa"] == status["cash_flow_exceeds_income"] == "fail"
    assert body["score"] == 5 and body["unknown_count"] == 0


def test_valuation_finite_meaningful_pairs_metadata(inputs):
    result = get(inputs, ROUTES[1])
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["total"] == 1 and body["excluded_not_meaningful"] == 4
    assert body["data"][0]["symbol"] == "AAA"
    assert body["data"][0]["pe"] == 12 and body["data"][0]["roe"] == 50
    assert body["data"][0]["sector"] == "Công nghệ" and body["data"][0]["exchange"] == "HOSE"
    assert body["roe_unit"] == "percent"


@pytest.mark.parametrize("limit,page,length", [(1, 1, 1), (2, 3, 1), (25, 2, 0), (703, 2, 0)])
def test_screener_stable_pagination(inputs, limit, page, length):
    result = get(inputs, limit=limit, page=page)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["total"] == 5 and body["total_pages"] == (5 + limit - 1) // limit
    assert len(body["data"]) == length
    assert body["page"] == page and body["limit"] == limit
    assert body["provenance"]["dataset_id"] == "hybrid_eval_full_703"


@pytest.mark.parametrize("params,length", [({"symbol": "AA"}, 1), ({"min_roe": 1}, 2),
    ({"min_piotroski": 9}, 0), ({"min_altman_z": 4}, 0), ({"status": "QUALIFIED"}, 0),
    ({"sector": "Công nghệ"}, 5), ({"exchange": "HNX"}, 0), ({"is_fallback": True}, 0),
    ({"is_veto": True}, 0)])
def test_screener_every_filter(inputs, params, length):
    body = get(inputs, **params).json()
    assert body["total"] == length and len(body["data"]) == length


@pytest.mark.parametrize("params", [{"symbol": "A.*"}, {"symbol": "--config=evil"}, {"symbol": "aaa"},
    {"symbol": "A\r\n"}, {"symbol": ""}, {"page": 0}, {"page": 1_000_001}, {"limit": 0},
    {"limit": 704}, {"limit": "[]"}, {"min_piotroski": -1}, {"min_piotroski": 10},
    {"min_piotroski": 1.5}, {"min_roe": "NaN"}, {"min_roe": "Inf"}, {"min_roe": "-Inf"},
    {"min_roe": 1e13}, {"min_altman_z": "nonsense"}, {"is_veto": "maybe"}, {"status": "ACTIVE"},
    {"exchange": "OTHER"}, {"sector": "x\r\ny"}, {"sector": "﻿test"}, {"sector": "x" * 129}])
def test_dim01_12_14_bounded_query_validation(inputs, params):
    result = get(inputs, **params)
    assert result.status_code == 422
    assert result.json() == {"detail": "INVALID_FUNDAMENTAL_REQUEST"}


@pytest.mark.parametrize("clock", ["", "2026-01-01", "bad", "2026-04-01T08:30:00", "2099-01-01T00:00:00Z", "NaN"])
@pytest.mark.parametrize("route", ROUTES)
def test_dim06_invalid_cutoff_symmetry(inputs, clock, route):
    assert get(inputs, route, as_of=clock).status_code == 422


@pytest.mark.parametrize("route", ROUTES)
def test_duplicate_query_is_rejected(inputs, route):
    response = inputs[0].get("/api/v1/quant/" + route, params=[("as_of", CUTOFF), ("as_of", CUTOFF)])
    assert response.status_code == 422


@pytest.mark.parametrize("clock,year", [("2026-04-01T15:29:59+07:00", 2024),
    ("2026-04-01T15:30:00+07:00", 2025), ("2026-04-01T08:30:00Z", 2025)])
def test_dim06_inclusive_filing_pit_session_boundary(inputs, clock, year):
    body = get(inputs, ROUTES[2], as_of=clock).json()
    assert body["fiscal_year"] == year
    assert pd.Timestamp(body["provenance"]["max_included_available_at"]) <= pd.Timestamp(clock)


@pytest.mark.parametrize("clock", ["2026-04-04T08:30:00Z", "2026-04-30T08:30:00Z", "2026-05-01T08:30:00Z"])
def test_dim07_public_filings_not_shifted_by_holidays(inputs, clock):
    body = get(inputs, ROUTES[2], as_of=clock).json()
    assert body["status"] == "success"
    assert pd.Timestamp(body["provenance"]["effective_cutoff"]) == pd.Timestamp(clock)


def test_dim06_future_revision_excluded_then_included(inputs):
    original = get(inputs, ROUTES[2]).json()
    row = inputs[3][inputs[3].fiscal_year.eq(2025) & inputs[3].item_code.eq("net_profit")].copy()
    row["item_value"] = 60
    row["source_publish_at"] = row["available_at"] = "2026-04-02T08:30:00Z"
    pd.concat([inputs[3], row]).to_parquet(inputs[1], index=False)
    body = get(inputs, ROUTES[2]).json()
    assert body["roe"] == original["roe"]
    assert body["provenance"]["content_hash"] == original["provenance"]["content_hash"]
    assert body["provenance"]["excluded_future_rows"] == 1
    assert get(inputs, ROUTES[2], as_of="2026-04-02T08:30:00Z").json()["roe"] == 1


@pytest.mark.parametrize("lifecycle", ["DELISTED", "SUSPENDED", "FROZEN", "DISQUALIFIED"])
def test_dim11_pit_latest_lifecycle_excludes_ineligible(inputs, lifecycle):
    current = inputs[4].iloc[:1].copy()
    current["as_of"] = current["available_at"] = "2026-04-02T08:30:00Z"
    current["status"] = lifecycle
    pd.concat([inputs[4], current]).to_parquet(inputs[2], index=False)
    assert get(inputs, ROUTES[1]).json()["total"] == 1
    assert get(inputs, ROUTES[1], as_of="2026-04-02T08:30:00Z").json()["total"] == 0


@pytest.mark.parametrize("column,value", [("pe", np.inf), ("roe", -np.inf), ("pe", 1e13),
    ("piotroski_f", 9.5), ("piotroski_f", -1), ("exchange", "OTHER"), ("sector", "a\r\nb"),
    ("sector", "﻿a"), ("symbol", "AAA --flag"), ("is_veto", None), ("as_of", None),
    ("available_at", "bad"), ("as_of", "2026-04-02T08:30:00Z"), ("available_at", "2026-04-01T08:30:00")])
def test_dim01_06_08_13_bad_hybrid_schema(inputs, column, value):
    frame = inputs[4].copy()
    frame.loc[0, column] = value
    frame.to_parquet(inputs[2], index=False)
    for route in ROUTES[:2]:
        result = get(inputs, route)
        assert result.status_code == 424, result.text


@pytest.mark.parametrize("column,value", [("item_value", np.inf), ("item_value", -np.inf), ("item_value", 1e19),
    ("fiscal_year", 2025.5), ("fiscal_year", None), ("fiscal_quarter", 5), ("endpoint", "unknown"),
    ("period_type", "month"), ("available_at", None), ("available_at", "bad"),
    ("available_at", "2023-01-01T00:00:00Z"), ("source_publish_at", "2026-04-03T00:00:00Z")])
def test_dim01_06_08_13_bad_financial_schema(inputs, column, value):
    frame = inputs[3].copy()
    frame.loc[0, column] = value
    frame.to_parquet(inputs[1], index=False)
    for route in ROUTES[2:]:
        assert get(inputs, route).status_code == 424


@pytest.mark.parametrize("which", [1, 2])
@pytest.mark.parametrize("fault", ["missing", "directory", "corrupt", "partial", "duplicate", "missing_column"])
def test_dim02_03_04_13_fail_closed_dependencies(inputs, which, fault):
    path = inputs[which]
    frame = inputs[which + 2].copy()
    if fault == "missing":
        path.unlink()
    elif fault == "directory":
        path.unlink()
        path.mkdir()
    elif fault == "corrupt":
        path.write_bytes(b"\xef\xbb\xbf{}\r\n")
    elif fault == "partial":
        path.write_bytes(path.read_bytes()[:32])
    elif fault == "duplicate":
        pd.concat([frame, frame.iloc[:1]]).to_parquet(path, index=False)
    else:
        frame.drop(columns=["available_at"]).to_parquet(path, index=False)
    routes = ROUTES[2:] if which == 1 else ROUTES[:2]
    for route in routes:
        assert get(inputs, route).status_code == 424


@pytest.mark.parametrize("which", [1, 2])
@pytest.mark.parametrize("bound", ["MAX_FUNDAMENTAL_BYTES", "MAX_FUNDAMENTAL_ROWS"])
def test_dim14_bounds_checked_before_materialization(inputs, monkeypatch, which, bound):
    monkeypatch.setattr(quant, bound, 1)
    monkeypatch.setattr(quant.pd, "read_parquet", lambda *a, **kw: pytest.fail("materialized oversized input"))
    route = ROUTES[2] if which == 1 else ROUTES[0]
    assert get(inputs, route).status_code == 424


def test_dim10_vnd_scale_invariant_ratios(inputs):
    original = get(inputs, ROUTES[2]).json()
    frame = inputs[3].copy()
    frame["item_value"] *= 1e12
    frame.to_parquet(inputs[1], index=False)
    body = get(inputs, ROUTES[2]).json()
    for metric in ("net_margin", "asset_turnover", "equity_multiplier", "roe", "roe_percent"):
        assert body[metric] == pytest.approx(original[metric])
    assert get(inputs, ROUTES[3]).json()["score"] == 9


def test_dim05_09_21_22_read_only_concurrent_isolation(inputs):
    before = {p: p.read_bytes() for p in inputs[1:3]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda route: get(inputs, route), ROUTES * 3))
    assert all(r.status_code == 200 for r in responses)
    assert before == {p: p.read_bytes() for p in inputs[1:3]}


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("dimension,key", [(17, "role_id"), (18, "model"), (19, "gate"),
    (20, "content_sha256"), (21, "output_path"), (22, "lock_owner"), (24, "token")])
def test_orchestration_dimensions_cannot_promote_or_publish(inputs, route, dimension, key):
    before = {p: p.read_bytes() for p in inputs[1:3]}
    response = get(inputs, route, **{key: "SECRET_REPLAY"})
    assert response.status_code == 422
    assert "SECRET_REPLAY" not in response.text
    assert before == {p: p.read_bytes() for p in inputs[1:3]}


@pytest.mark.parametrize("route", ROUTES)
def test_dim15_16_23_no_provider_retry_fallback_or_secret_leak(inputs, route, monkeypatch, caplog):
    calls = []
    def failure(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("429 https://user:SECRET@example.com token=SECRET")
    monkeypatch.setattr(quant.pd, "read_parquet", failure)
    response = get(inputs, route)
    assert response.status_code == 424
    assert len(calls) == 1
    assert "SECRET" not in response.text + caplog.text


def test_dim19_20_digest_determinism_and_input_binding(inputs):
    original = get(inputs).json()["provenance"]["content_hash"]
    inputs[4].sample(frac=1, random_state=1).to_parquet(inputs[2], index=False)
    assert get(inputs).json()["provenance"]["content_hash"] == original
    frame = inputs[4].copy()
    frame.loc[0, "roe"] = 51
    frame.to_parquet(inputs[2], index=False)
    assert get(inputs).json()["provenance"]["content_hash"] != original


def test_dim02_source_files_strict_utf8_lf_no_bom():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for relative in ("src/omega/api/routes/quant.py", "tests/api/test_fundamental_contracts.py"):
        raw = (root / relative).read_bytes()
        raw.decode("utf-8", errors="strict")
        assert not raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw


@pytest.mark.parametrize("item,value", [("long_term_debt", -1), ("current_assets", -1),
    ("shares_outstanding", 0), ("shares_outstanding", -1)])
def test_piotroski_invalid_accounting_inputs_are_unknown(inputs, item, value):
    frame = inputs[3].copy()
    frame.loc[frame.fiscal_year.eq(2025) & frame.item_code.eq(item), "item_value"] = value
    frame.to_parquet(inputs[1], index=False)
    body = get(inputs, ROUTES[3]).json()
    assert body["unknown_count"] == 1 and body["score"] is None


@pytest.mark.parametrize("fault", ["year_mismatch", "annual_quarter", "quarter_zero", "alias_conflict"])
def test_financial_period_identity_and_alias_ambiguity(inputs, fault):
    frame = inputs[3].copy()
    if fault == "year_mismatch":
        frame.loc[0, "fiscal_period_end"] = date(2023, 12, 31)
    elif fault == "annual_quarter":
        frame.loc[0, "fiscal_quarter"] = 1
    elif fault == "quarter_zero":
        frame.loc[0, "period_type"] = "quarter"
    else:
        row = frame[frame.item_code.eq("owners_equity") & frame.fiscal_year.eq(2025)].copy()
        row["item_code"] = "equity"
        frame = pd.concat([frame, row])
    frame.to_parquet(inputs[1], index=False)
    for route in ROUTES[2:]:
        assert get(inputs, route).status_code == 424


def test_dim14_universe_response_bound(inputs):
    frame = pd.concat([inputs[4].iloc[:1]] * 704, ignore_index=True)
    frame["symbol"] = [f"X{i}" for i in range(704)]
    frame.to_parquet(inputs[2], index=False)
    for route in ROUTES[:2]:
        assert get(inputs, route).status_code == 424


def test_dim05_09_file_mutation_during_read_fails_closed(inputs, monkeypatch):
    original = quant.pd.read_parquet
    def mutate(stream, **kwargs):
        result = original(stream, **kwargs)
        with inputs[2].open("ab") as writer:
            writer.write(b"changed")
        return result
    monkeypatch.setattr(quant.pd, "read_parquet", mutate)
    assert get(inputs).status_code == 424


@pytest.mark.parametrize("which,column", [(1, "item_value"), (2, "pe")])
def test_numeric_strings_and_booleans_rejected_at_artifact_boundary(inputs, which, column):
    frame = inputs[which + 2].copy()
    for replacement in ("12", True):
        bad = frame.copy()
        bad[column] = replacement
        bad.to_parquet(inputs[which], index=False)
        route = ROUTES[2] if which == 1 else ROUTES[0]
        assert get(inputs, route).status_code == 424


def test_empty_universe_and_missing_symbol_are_explicit(inputs):
    inputs[4].iloc[:0].to_parquet(inputs[2], index=False)
    for route in ROUTES[:2]:
        response = get(inputs, route)
        assert response.status_code == 200, response.text
        assert response.json()["data"] == []
    body = get(inputs, "fundamental/dupont/ZZZ").json()
    assert body["status"] == "unavailable" and body["roe"] is None
    assert body["filing_dates"] == []
