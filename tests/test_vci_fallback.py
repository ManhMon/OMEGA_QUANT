from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import multiprocessing
import time
from pathlib import Path

import pandas as pd
import pytest

from vnstock.api.quote import Quote

from omega.data.vnstock_vci import VnstockVCIDataSource, _stop_price_process
from omega.data.loader import DataLoader
from omega.data.macro_news_pipeline import VnstockNewsAdapter, load_source_registry, load_universe_snapshot
from omega.data.registry import DatasetRegistry
from omega.core.model_registry import ModelRegistry


def _frame(close):
    return pd.DataFrame([{"time": "2024-01-02", "open": close, "high": close, "low": close, "close": close, "volume": 100}])


def _blocked_price_provider():
    while True:
        time.sleep(1)


def _install_price_context(monkeypatch, fetch):
    processes = []

    class Parent:
        def __init__(self):
            self.message = None
        def poll(self, timeout):
            return self.message is not None
        def recv(self):
            return self.message
        def close(self):
            pass

    class Child:
        def __init__(self, parent):
            self.parent = parent
        def close(self):
            pass

    class Process:
        daemon = False
        alive = False
        def __init__(self, args):
            self.args = args
        def start(self):
            self.alive = True
            _, provider, symbol, start, end, _ = self.args
            try:
                self.args[0].parent.message = (True, fetch(provider, symbol, start, end))
            except Exception as exc:
                self.args[0].parent.message = (False, f"{type(exc).__name__}: {exc}")
            self.alive = False
        def is_alive(self):
            return self.alive
        def terminate(self):
            self.alive = False
        def kill(self):
            self.alive = False
        def join(self, timeout=None):
            pass

    class Context:
        def Pipe(self, duplex=False):
            parent = Parent()
            return parent, Child(parent)
        def Process(self, target, args):
            process = Process(args)
            processes.append(process)
            return process

    monkeypatch.setattr("omega.data.vnstock_vci.multiprocessing.get_context", lambda: Context())
    return processes


def test_vci_is_selected_when_all_providers_succeed(monkeypatch):
    source = VnstockVCIDataSource()
    _install_price_context(monkeypatch, lambda provider, *_: _frame(10 if provider == "KBS" else 20))

    rows = source.fetch_price_data("VCB", "2024-01-01", "2024-01-03")

    assert rows[0]["source_used"] == "VCI"


def test_declared_providers_construct_with_installed_vnstock():
    source = VnstockVCIDataSource()

    for provider in ("VCI", "KBS"):
        Quote(source=provider, symbol="VCB")


def test_macro_source_registry_declares_supported_vnstock_backup():
    registry = load_source_registry(Path("config/macro_news_sources.json"))

    assert {entry["source_id"] for entry in registry if entry["kind"] == "vnstock"} == {
        "vnstock_vci", "vnstock_kbs"
    }


def test_vci_is_selected_when_kbs_fails(monkeypatch):
    source = VnstockVCIDataSource()

    def fetch(provider, *_):
        if provider == "KBS":
            raise TimeoutError("KBS unavailable")
        return _frame(10) if provider == "VCI" else pd.DataFrame()

    _install_price_context(monkeypatch, fetch)

    rows = source.fetch_price_data("VCB", "2024-01-01", "2024-01-03")

    assert rows[0]["source_used"] == "VCI"


def test_kbs_is_selected_after_vci_fails(monkeypatch):
    source = VnstockVCIDataSource()

    def fetch(provider, *_):
        if provider == "VCI":
            raise TimeoutError(f"{provider} unavailable")
        return _frame(10)

    _install_price_context(monkeypatch, fetch)

    rows = source.fetch_price_data("VCB", "2024-01-01", "2024-01-03")

    assert rows[0]["source_used"] == "KBS"


def test_timed_out_price_process_is_terminated(monkeypatch):
    source = VnstockVCIDataSource()
    source.PROVIDER_TIMEOUT_SECONDS = 0.01
    terminated = []

    class Parent:
        def poll(self, timeout): return False
        def close(self): pass
    class Child:
        def close(self): pass
    class Process:
        daemon = False
        alive = False
        def start(self): self.alive = True
        def is_alive(self): return self.alive
        def terminate(self): self.alive = False; terminated.append(True)
        def kill(self): self.alive = False
        def join(self, timeout=None): pass
    class Context:
        def Pipe(self, duplex=False): return Parent(), Child()
        def Process(self, **kwargs): return Process()

    monkeypatch.setattr("omega.data.vnstock_vci.multiprocessing.get_context", lambda: Context())
    started = time.monotonic()

    rows = source.fetch_price_data("VCB", "2024-01-01", "2024-01-03")

    assert time.monotonic() - started < 0.15
    assert rows == []
    assert len(terminated) == len(source.PROVIDERS)


def test_price_process_cleanup_stops_real_blocked_worker():
    process = multiprocessing.get_context().Process(target=_blocked_price_provider)
    process.start()

    _stop_price_process(process)

    assert not process.is_alive()


def test_provider_network_timeout_is_passed_to_vnstock_client(monkeypatch):
    source = VnstockVCIDataSource()
    source.PROVIDER_TIMEOUT_SECONDS = 7
    captured = []

    class Provider:
        __module__ = "vnstock.explorer.vci.quote"

    class FakeQuote:
        _provider = Provider()
        def history(self, **kwargs):
            from vnstock.explorer.vci import quote
            quote.send_request(url="https://example.com", headers={})
            return _frame(10)

    monkeypatch.setattr("omega.data.vnstock_vci.Quote", lambda **kwargs: FakeQuote())
    monkeypatch.setattr("vnstock.explorer.vci.quote.send_request", lambda **kwargs: captured.append(kwargs["timeout"]))

    source._fetch_provider("VCI", "VCB", "2024-01-01", "2024-01-03")

    assert captured == [7]


def test_provider_errors_return_no_rows_when_every_provider_fails(monkeypatch):
    source = VnstockVCIDataSource()
    _install_price_context(monkeypatch, lambda *_: (_ for _ in ()).throw(TimeoutError("timeout")))

    assert source.fetch_price_data("VCB", "2024-01-01", "2024-01-03") == []


@pytest.mark.parametrize("registry_type", [DatasetRegistry, ModelRegistry])
def test_registries_fail_closed_on_corrupt_json(tmp_path, registry_type):
    registry_path = tmp_path / registry_type.__name__
    registry_path.mkdir()
    (registry_path / "registry_metadata.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="Corrupted"):
        registry_type(registry_path)


@pytest.mark.parametrize(
    "as_of_time",
    [
        datetime(2024, 1, 2, 0, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 7, 45, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 8, tzinfo=timezone.utc),
        datetime(2024, 1, 3, 0, tzinfo=timezone.utc),
    ],
)
def test_get_ohlcv_hides_same_day_eod_before_next_open(monkeypatch, as_of_time):
    source = VnstockVCIDataSource()
    _install_price_context(monkeypatch, lambda provider, *_: _frame(10) if provider == "VCI" else pd.DataFrame())

    frame = source.get_ohlcv(["VCB"], days=1, as_of_time=as_of_time)

    assert frame.empty


def test_get_ohlcv_releases_eod_at_next_vietnam_market_open(monkeypatch):
    source = VnstockVCIDataSource()
    _install_price_context(monkeypatch, lambda provider, *_: _frame(10) if provider == "VCI" else pd.DataFrame())

    frame = source.get_ohlcv(["VCB"], days=1, as_of_time=datetime(2024, 1, 3, 2, tzinfo=timezone.utc))

    assert frame.index.get_level_values("date").max() == pd.Timestamp("2024-01-02")
    assert frame["source_used"].eq("VCI").all()


def test_timezone_aware_daily_bar_preserves_vietnam_session_date(monkeypatch):
    source = VnstockVCIDataSource()
    frame = _frame(10)
    frame["time"] = "2024-01-02T00:00:00+07:00"
    _install_price_context(monkeypatch, lambda provider, *_: frame if provider == "VCI" else pd.DataFrame())

    result = source.get_ohlcv(["VCB"], days=1, as_of_time=datetime(2024, 1, 3, 2, tzinfo=timezone.utc))

    assert result.index.get_level_values("date").max() == pd.Timestamp("2024-01-02")


def test_timezone_aware_utc_bar_uses_vietnam_session_date():
    source = VnstockVCIDataSource()

    rows = source._rows_from_frame(_frame(10).assign(time="2024-01-01T17:00:00Z"), "VCB", "VCI")

    assert pd.to_datetime(rows[0]["timestamp"], unit="s") == pd.Timestamp("2024-01-02")


def test_get_ohlcv_waits_until_next_exchange_session_after_national_day(monkeypatch):
    source = VnstockVCIDataSource()
    frame = _frame(10)
    frame["time"] = "2024-08-30"
    _install_price_context(monkeypatch, lambda provider, *_: frame if provider == "VCI" else pd.DataFrame())

    holiday = source.get_ohlcv(["VCB"], days=7, as_of_time=datetime(2024, 9, 2, 2, tzinfo=timezone.utc))
    next_session = source.get_ohlcv(["VCB"], days=7, as_of_time=datetime(2024, 9, 4, 2, tzinfo=timezone.utc))

    assert holiday.empty
    assert not next_session.empty


def test_get_ohlcv_fails_closed_after_calendar_coverage(monkeypatch):
    source = VnstockVCIDataSource()
    frame = _frame(10)
    frame["time"] = "2028-04-28"
    _install_price_context(monkeypatch, lambda provider, *_: frame if provider == "VCI" else pd.DataFrame())

    with pytest.raises(ValueError, match="no holiday coverage for 2028"):
        source.get_ohlcv(["VCB"], days=7, as_of_time=datetime(2028, 5, 1, 2, tzinfo=timezone.utc))


def test_loader_fails_closed_after_calendar_coverage(tmp_path):
    loader = DataLoader(cache_dir=tmp_path)
    frame = pd.DataFrame({"date": ["2028-04-28"]})

    with pytest.raises(ValueError, match="no holiday coverage for 2028"):
        loader._add_pit_timestamps(frame)


def test_macro_news_falls_back_to_registry_kbs_when_vci_fails(monkeypatch):
    universe = load_universe_snapshot(b'{"schema_version":1,"universe_id":"test","universe_version":"1","generated_at":"2024-01-01T00:00:00Z","effective_from":"2024-01-01T00:00:00Z","effective_to":null,"members":[{"ticker":"VCB","exchange":"HSX"}]}', datetime(2024, 1, 2, tzinfo=timezone.utc))
    sources = [entry for entry in load_source_registry(Path("config/macro_news_sources.json")) if entry["kind"] == "vnstock"]
    adapter = VnstockNewsAdapter(universe, sources=sources)
    calls = []
    pipes = []

    class Parent:
        def __init__(self, provider):
            self.provider = provider
        def poll(self, timeout):
            calls.append(self.provider)
            return True
        def recv(self):
            result = pd.DataFrame([{"head": "KBS summary", "article_id": "kbs-1", "title": "KBS", "publish_time": "2024-01-02T00:00:00Z", "url": "/news/kbs-1"}])
            return (False, "VCI unavailable") if self.provider == "VCI" else (True, result)
        def close(self):
            pass

    class Child:
        def close(self):
            pass

    class Process:
        daemon = False
        def start(self):
            pass
        def is_alive(self):
            return False
        def join(self, timeout=None):
            pass

    class Context:
        def Pipe(self, duplex=False):
            parent = Parent(adapter.sources[len(pipes)]["source_id"].removeprefix("vnstock_").upper())
            pipes.append(parent)
            return parent, Child()
        def Process(self, **kwargs):
            return Process()

    monkeypatch.setattr("omega.data.macro_news_pipeline.multiprocessing.get_context", lambda: Context())
    frame, source = adapter._fetch_page("VCB")

    assert not frame.empty and source["source_id"] == "vnstock_kbs"
    assert frame.loc[0, "news_title"] == "KBS" and frame.loc[0, "url"] == "/news/kbs-1"
    assert calls == ["VCI", "KBS"]


def test_reconciliation_compares_against_selected_source(caplog, tmp_path):
    loader = DataLoader(cache_dir=tmp_path)
    selected = VnstockVCIDataSource()._rows_from_frame(_frame(10), "VCB", "VCI")
    kbs = VnstockVCIDataSource()._rows_from_frame(_frame(11), "VCB", "KBS")

    loader._log_provider_close_deviations("VCB", selected, {"VCI": selected, "KBS": kbs})

    assert "selected VCI vs KBS" in caplog.text


def test_reconciliation_evidence_is_call_local_under_concurrency(monkeypatch):
    source = VnstockVCIDataSource()

    def fetch(provider, symbol, *_):
        return _frame(10 if provider == "KBS" else 11 if symbol == "VCB" else 12)

    _install_price_context(monkeypatch, fetch)
    with ThreadPoolExecutor(max_workers=2) as executor:
        calls = [executor.submit(source.fetch_price_data_with_reconciliation, symbol, "2024-01-01", "2024-01-03") for symbol in ("VCB", "VNM")]
        results = [call.result() for call in calls]

    assert {evidence["VCI"][0]["symbol"] for _, evidence in results} == {"VCB", "VNM"}


def test_each_parallel_provider_request_is_rate_limited(monkeypatch):
    source = VnstockVCIDataSource()
    calls = []
    monkeypatch.setattr(source.rate_limiter, "throttle", lambda: calls.append(1))
    _install_price_context(monkeypatch, lambda *_: pd.DataFrame())

    source.fetch_price_data("VCB", "2024-01-01", "2024-01-03")

    assert len(calls) == len(source.PROVIDERS)
