from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import multiprocessing
from pathlib import Path
import time
from urllib.error import HTTPError

import pandas as pd
import pytest

from omega.data.vnstock_vci import VnstockVCIDataSource, _stop_price_process
from omega.data.vci_direct import DirectVCIClient
from omega.data.vnstock_client import VnstockClient
from omega.data.loader import DataLoader
from omega.data.macro_news_pipeline import VnstockNewsAdapter, load_source_registry, load_universe_snapshot
from omega.data.registry import DatasetRegistry
from omega.core.model_registry import ModelRegistry


def _blocked_price_provider():
    while True:
        time.sleep(1)


def _response(day="2024-01-02", close=10):
    body = json.dumps({"data": [{"t": [int(pd.Timestamp(day, tz="UTC").timestamp() * 1000)],
                                 "o": [close], "h": [close], "l": [close],
                                 "c": [close], "v": [100]}]}).encode()

    class Response:
        offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, amount):
            chunk = body[self.offset:self.offset + amount]
            self.offset += len(chunk)
            return chunk

    return Response()


@pytest.mark.parametrize("method,args,kwargs", [
    ("_fetch_provider", ("VCI", "VCB", "2024-01-01", "2024-01-03"), {}),
    ("_fetch_provider_isolated", ("VCI", "VCB", "2024-01-01", "2024-01-03"), {}),
    ("fetch_price_data", ("VCB", "2024-01-01", "2024-01-03"), {}),
    ("fetch_price_data_with_reconciliation", ("VCB", "2024-01-01", "2024-01-03"), {}),
    ("get_ohlcv", (["VCB"],), {"days": 1, "as_of_time": datetime(2024, 1, 3, 2, tzinfo=timezone.utc)}),
])
def test_archived_price_routes_fail_closed_without_network(monkeypatch, method, args, kwargs):
    def forbidden(*args, **kwargs):
        raise AssertionError("Archived route must not dispatch")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("multiprocessing.get_context", forbidden)
    with pytest.raises(ImportError, match="archived.*forbidden"):
        getattr(VnstockVCIDataSource(), method)(*args, **kwargs)


def test_direct_vci_is_selected_without_remote_backup():
    calls = []

    def opener(request, timeout):
        calls.append((request.full_url, json.loads(request.data), timeout))
        return _response()

    frame = DirectVCIClient(opener=opener, timeout=7).fetch_history(
        "VCB", "2024-01-01", "2024-01-03", as_of="2024-01-03T02:00:00Z")

    assert frame.iloc[0]["ticker"] == "VCB"
    assert frame.iloc[0]["close"] == 10000
    assert len(calls) == 1
    assert calls[0][0] == "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
    assert calls[0][1]["symbols"] == ["VCB"]
    assert calls[0][2] == 7


@pytest.mark.parametrize("failure", [TimeoutError("provider timeout"), HTTPError(
    "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart", 403, "Forbidden", {}, None)])
def test_direct_failure_never_returns_empty_success_or_kbs(failure):
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        raise failure

    with pytest.raises(RuntimeError, match="VCI request failed"):
        DirectVCIClient(opener=opener).fetch_history("VCB", "2024-01-01", "2024-01-03")
    assert len(calls) == 1
    assert all("vietcap.com.vn" in url for url in calls)


def test_direct_429_exhaustion_is_bounded_without_remote_backup(monkeypatch):
    calls, sleeps = [], []

    def opener(request, timeout):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 429, "limited", {"Retry-After": "999999"}, None)

    monkeypatch.setattr("omega.data.vci_direct.time.sleep", sleeps.append)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        DirectVCIClient(opener=opener, max_attempts=3).fetch_history("VCB", "2024-01-01", "2024-01-03")
    assert len(calls) == 3
    assert sleeps == [8, 8]


@pytest.mark.parametrize("timeout", [None, "", True, 0, -1, float("nan"), float("inf"), -float("inf")])
def test_direct_invalid_timeout_rejected_before_transport(timeout):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid controls must not dispatch")

    with pytest.raises(ValueError, match="timeout"):
        DirectVCIClient(opener=forbidden, timeout=timeout)


@pytest.mark.parametrize("attempts", [None, "", True, 0, -1, float("nan"), float("inf"), 10**13])
def test_direct_invalid_attempts_rejected_before_transport(attempts):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid controls must not dispatch")

    with pytest.raises(ValueError, match="max_attempts"):
        DirectVCIClient(opener=forbidden, max_attempts=attempts)


@pytest.mark.parametrize("close", [None, "", float("nan"), float("inf"), -float("inf"), 0, -1, 10**13])
def test_direct_malformed_prices_fail_closed(close):
    with pytest.raises(ValueError):
        DirectVCIClient(opener=lambda *args, **kwargs: _response(close=close)).fetch_history(
            "VCB", "2024-01-01", "2024-01-03", as_of="2024-01-03T02:00:00Z")


@pytest.mark.parametrize("as_of", ["2024-01-02T00:00:00Z", "2024-01-02T08:30:00Z",
                                    "2024-01-03T01:59:59.999999Z"])
def test_direct_eod_hidden_before_next_open(as_of):
    with pytest.raises(ValueError, match="PIT trading-session"):
        DirectVCIClient(opener=lambda *args, **kwargs: _response()).fetch_history(
            "VCB", "2024-01-01", "2024-01-03", as_of=as_of)


@pytest.mark.parametrize("as_of", ["2024-01-03T02:00:00Z", "2024-01-03T09:00:00+07:00"])
def test_direct_eod_released_at_inclusive_next_open(as_of):
    frame = DirectVCIClient(opener=lambda *args, **kwargs: _response()).fetch_history(
        "VCB", "2024-01-01", "2024-01-03", as_of=as_of)
    assert frame.iloc[0]["available_at"] == pd.Timestamp("2024-01-03T02:00:00Z")
    assert (frame["as_of"] <= frame["available_at"]).all()


def test_direct_eod_waits_until_next_session_after_national_day():
    client = DirectVCIClient(opener=lambda *args, **kwargs: _response("2024-08-30"))
    with pytest.raises(ValueError, match="PIT trading-session"):
        client.fetch_history("VCB", "2024-08-30", "2024-09-04", as_of="2024-09-02T02:00:00Z")
    frame = client.fetch_history("VCB", "2024-08-30", "2024-09-04", as_of="2024-09-04T02:00:00Z")
    assert frame.iloc[0]["available_at"] == pd.Timestamp("2024-09-04T02:00:00Z")


def test_direct_reconciliation_is_call_local_under_concurrency():
    def opener(request, timeout):
        ticker = json.loads(request.data)["symbols"][0]
        return _response(close=10 if ticker == "VCB" else 20)

    client = DirectVCIClient(opener=opener)
    with ThreadPoolExecutor(max_workers=2) as executor:
        calls = [executor.submit(client.fetch_history, ticker, "2024-01-01", "2024-01-03",
                                 as_of="2024-01-03T02:00:00Z") for ticker in ("VCB", "VNM")]
        frames = [call.result() for call in calls]
    assert [(frame.iloc[0]["ticker"], frame.iloc[0]["close"]) for frame in frames] == [
        ("VCB", 10000), ("VNM", 20000)]


def test_macro_source_registry_declares_only_active_vci():
    registry = load_source_registry(Path("config/macro_news_sources.json"))
    assert {entry["source_id"] for entry in registry if entry["kind"] == "vnstock"} == {"vnstock_vci"}


def test_macro_news_vci_failure_is_explicit_without_registry_backup(monkeypatch):
    universe = load_universe_snapshot(b'{"schema_version":1,"universe_id":"test","universe_version":"1","generated_at":"2024-01-01T00:00:00Z","effective_from":"2024-01-01T00:00:00Z","effective_to":null,"members":[{"ticker":"VCB","exchange":"HSX"}]}', datetime(2024, 1, 2, tzinfo=timezone.utc))
    adapter = VnstockNewsAdapter(universe)
    calls, closed = [], []

    class Parent:
        def poll(self, timeout):
            calls.append(timeout)
            return True

        def recv(self):
            return False, "VCI unavailable"

        def close(self):
            closed.append("parent")

    class Child:
        def close(self):
            closed.append("child")

    class Process:
        def start(self):
            pass

        def is_alive(self):
            return False

        def join(self, timeout=None):
            pass

    class Context:
        def Pipe(self, duplex=False):
            return Parent(), Child()

        def Process(self, **kwargs):
            return Process()

    monkeypatch.setattr("omega.data.macro_news_pipeline.multiprocessing.get_context", lambda: Context())
    with pytest.raises(RuntimeError, match="VCI unavailable"):
        adapter._fetch_page("VCB")
    assert calls == [adapter.timeout_seconds]
    assert closed == ["child", "parent"]


def test_price_process_cleanup_stops_real_blocked_worker():
    process = multiprocessing.get_context().Process(target=_blocked_price_provider)
    process.start()
    try:
        _stop_price_process(process)
        assert not process.is_alive()
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        process.close()


@pytest.mark.parametrize("registry_type", [DatasetRegistry, ModelRegistry])
def test_registries_fail_closed_on_corrupt_json(tmp_path, registry_type):
    registry_path = tmp_path / registry_type.__name__
    registry_path.mkdir()
    (registry_path / "registry_metadata.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="Corrupted"):
        registry_type(registry_path)


def test_loader_fails_closed_after_calendar_coverage(tmp_path):
    loader = DataLoader(cache_dir=tmp_path)
    frame = pd.DataFrame({"date": ["2028-04-28"]})
    with pytest.raises(ValueError, match="no holiday coverage for 2028"):
        loader._add_pit_timestamps(frame)


def test_reconciliation_compares_against_selected_source(caplog, tmp_path):
    loader = DataLoader(cache_dir=tmp_path)
    selected = [{"timestamp": 1704153600, "symbol": "VCB", "source_used": "VCI", "close": 10000}]
    kbs = [{"timestamp": 1704153600, "symbol": "VCB", "source_used": "KBS", "close": 11000}]
    loader._log_provider_close_deviations("VCB", selected, {"VCI": selected, "KBS": kbs})
    assert "selected VCI vs KBS" in caplog.text


def test_fetch_company_profile_uses_injected_direct_client():
    calls = []

    class Client:
        def fetch_company_profile(self, symbol):
            calls.append(symbol)
            return pd.DataFrame([{"symbol": symbol, "name": "VCB"}])

    frame = VnstockClient(direct_vci_client=Client()).fetch_company_profile("VCB")
    assert frame.loc[0, "name"] == "VCB"
    assert calls == ["VCB"]


def test_historical_provider_failure_dominates_unverified_empty(tmp_path, monkeypatch):
    import scripts.fetch_news_sentiment as cli
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    snapshot = {
        "schema_version": 1, "universe_id": "cohort", "universe_version": "1",
        "generated_at": "2026-10-18T00:00:00Z", "effective_from": "2015-01-01T00:00:00Z",
        "effective_to": None, "members": [{"ticker": "AAA", "exchange": "HSX"}, {"ticker": "BBB", "exchange": "HNX"}],
    }
    (tmp_path / "universe.json").write_text(json.dumps(snapshot), encoding="utf-8")
    class Provider:
        def crawl_symbol(self, symbol, *args):
            if symbol == "BBB":
                raise TimeoutError("https://user:secret@cafef.vn/?token=SECRET")
            yield []
    manifest = cli.build_historical_news_sentiment(
        "universe.json", "2015-01-01", "2026-10-18", "2026-10-18T22:00:00Z",
        "data/historical_news/run", crawler=Provider())
    assert manifest["status"] == "failed"
    assert [entry["status"] for entry in manifest["symbols"]] == ["incomplete", "failed"]
    assert [entry["terminal_reason"] for entry in manifest["symbols"]] == [
        "no_articles_observed_history_unverified", "no_pages_observed"]
    assert all(entry["full_history_verified"] is False for entry in manifest["symbols"])
    assert all(secret not in str(manifest) for secret in ("secret", "token=", "SECRET"))
    with pytest.raises(ValueError, match="committed manifest"):
        cli.read_historical_manifest("data/historical_news/run")
