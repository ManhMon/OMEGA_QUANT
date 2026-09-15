"""16-Dimension resilience and unit tests for direct VCI client."""

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.ingest_all_market_data as iam

from omega.data.vci_direct import (
    DirectVCIClient,
    TokenBucket,
    redact,
    unpack_vietcap_columnar,
    validate_price_bounds,
)
from omega.data.market_flow import VNMarketFlowDataSource
from omega.data.vnstock_client import RateLimiter, UpstreamTransportException, VnstockClient, atomic_write_with_backup
from omega.quant.graph.fetcher import GraphFetcher, slice_vci_statement_envelope


def payload():
    return {"t": [1704067200000], "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100]}


def test_direct_client_is_wired_into_data_adapters():
    direct = DirectVCIClient()
    assert VnstockClient(direct_vci=True, direct_vci_client=direct).direct_vci_client is direct
    assert VNMarketFlowDataSource(vci_client=direct).vci_client is direct
    assert GraphFetcher(vci_client=direct).vci_client is direct


def test_market_flow_uses_injected_vci_client():
    class Client:
        def foreign_trade(self, **kwargs):
            return pd.DataFrame([{"trading_date": "2026-01-02"}])

    rows = VNMarketFlowDataSource(vci_client=Client()).fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")
    assert rows[0]["timestamp"]


def test_market_flow_propagates_injected_transport_error():
    class Client:
        def foreign_trade(self, **kwargs):
            raise TimeoutError("VCI timeout")

    with pytest.raises(TimeoutError):
        VNMarketFlowDataSource(vci_client=Client()).fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")


@pytest.mark.parametrize("bad_value", [math.nan, math.inf, -math.inf])
def test_market_flow_rejects_non_finite_numeric_fields(bad_value):
    class Client:
        def foreign_trade(self, **kwargs):
            return pd.DataFrame([{"trading_date": "2026-01-02", "fr_buy_value_matched": bad_value}])

    with pytest.raises(ValueError, match="finite"):
        VNMarketFlowDataSource(vci_client=Client()).fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")


def test_market_flow_converts_ict_date_to_utc():
    class Client:
        def foreign_trade(self, **kwargs):
            return pd.DataFrame([{"trading_date": "2026-01-02"}])

    row = VNMarketFlowDataSource(vci_client=Client()).fetch_foreign_flow("HPG", "2026-01-01", "2026-01-02")[0]
    assert row["timestamp"] == int(pd.Timestamp("2026-01-01 17:00:00", tz="UTC").timestamp())


def test_graph_fetcher_uses_injected_vci_client():
    class Response:
        offset = 0

        def raise_for_status(self):
            pass

        def json(self):
            if "statistics-financial" in self.url:
                return {"data": [{"value": 1}]}
            return {"data": {"years": [2026], "quarters": [1]}}

    class Client:
        def get(self, *args, **kwargs):
            response = Response()
            response.url = args[0]
            return response

    result = GraphFetcher(vci_client=Client()).vci_financial_raw("HPG")
    assert set(result) == {"income_statement", "balance_sheet", "cash_flow", "ratios"}


def test_graph_fetcher_retry_exhaustion_does_not_make_extra_call(monkeypatch):
    calls = 0

    def rate_limited():
        nonlocal calls
        calls += 1
        raise RuntimeError("HTTP 429 rate limit")

    monkeypatch.setattr("omega.quant.graph.fetcher.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        GraphFetcher(max_retry_wall_time=0.001, retry_delay=60.0)._call(rate_limited)
    assert calls == 2


@pytest.mark.parametrize("symbol", [None, "", " ", 123, math.nan, math.inf, "HPG/../x", "HPG?x=1", "HPG#x", "A" * 17])
def test_graph_fetcher_vci_financial_raw_rejects_invalid_tickers(symbol):
    calls = 0

    class Client:
        def get(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("HTTP dispatch must not occur for invalid ticker")

    with pytest.raises(ValueError, match="Invalid ticker"):
        GraphFetcher(vci_client=Client()).vci_financial_raw(symbol)
    assert calls == 0


def test_graph_fetcher_vci_financial_raw_normalizes_and_escapes_ticker():
    urls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"value": 1}]} if "statistics-financial" in urls[-1] else {"data": {"years": [2026], "quarters": [1]}}

    class Client:
        def get(self, url, **_kwargs):
            urls.append(url)
            return Response()

    GraphFetcher(vci_client=Client()).vci_financial_raw("  hpg  ")
    assert all("/HPG/" in url for url in urls)
    assert all("?" not in url.split("?")[0] for url in urls)


def test_graph_fetcher_retry_wall_time_is_bounded_with_injected_clock():
    now = 0.0
    sleeps = []
    calls = 0

    def clock():
        return now

    def sleep(delay):
        nonlocal now
        sleeps.append(delay)
        now += delay

    def rate_limited():
        nonlocal calls
        calls += 1
        raise RuntimeError("HTTP 429 rate limit")

    with pytest.raises(RuntimeError, match="HTTP 429"):
        GraphFetcher(max_retry_wall_time=120.0, retry_delay=60.0, time_fn=clock, sleep_fn=sleep)._call(rate_limited)
    assert calls == 3
    assert sleeps == [60.0, 60.0]


def test_graph_fetcher_does_not_retry_non_rate_limit_errors(monkeypatch):
    calls = 0
    sleeps = 0

    def failed():
        nonlocal calls
        calls += 1
        raise ValueError("invalid response")

    def sleep(_):
        nonlocal sleeps
        sleeps += 1

    monkeypatch.setattr("omega.quant.graph.fetcher.time.sleep", sleep)
    with pytest.raises(ValueError, match="invalid response"):
        GraphFetcher()._call(failed)
    assert calls == 1
    assert sleeps == 0


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit()])
def test_graph_fetcher_propagates_base_exception(error):
    calls = 0

    def halted():
        nonlocal calls
        calls += 1
        raise error

    with pytest.raises(type(error)):
        GraphFetcher()._call(halted)
    assert calls == 1


def test_direct_client_rejects_invalid_dates_before_http_dispatch():
    calls = 0

    def opener(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("HTTP must not be called")

    client = DirectVCIClient(opener=opener)
    for start, end in [(None, "2026-01-02"), ("", "2026-01-02"), ("2026-02-01", "2026-1-1"), ("bad-date", "2026-01-02"), ("NaN", "2026-01-02")]:
        with pytest.raises(ValueError, match="date range"):
            client.fetch_history("HPG", start, end)
    assert calls == 0


def test_direct_client_normalizes_date_bounds_in_request():
    requests = []

    class Response:
        offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, amount):
            raw = json.dumps({"data": payload()}).encode()
            chunk = raw[self.offset:self.offset + amount]
            self.offset += len(chunk)
            return chunk

    def opener(request, **_kwargs):
        requests.append(json.loads(request.data))
        return Response()

    client = DirectVCIClient(opener=opener)
    with pytest.raises(ValueError, match="trading-session"):
        client.fetch_history("HPG", "2026-01-01T07:00:00+07:00", "2026-01-02T07:00:00+07:00")
    request_data = requests[-1]
    assert "from" not in request_data
    assert request_data["to"] == int(pd.Timestamp("2026-01-02T00:00:00+00:00").timestamp())
    assert request_data["countBack"] == 2


def test_vnstock_direct_transport_error_is_typed(monkeypatch):
    from omega.data import vnstock_client

    monkeypatch.setattr(vnstock_client, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("timeout")))
    client = VnstockClient(direct_vci=True)
    with pytest.raises(UpstreamTransportException):
        client.fetch_history("VCB", "2026-01-01", "2026-01-02")


def test_ingest_cli_bootstraps_src_path_from_external_cwd(tmp_path):
    script = REPO_ROOT / "scripts" / "ingest_all_market_data.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout


def test_unpack_normalizes_vnd_full_and_preserves_contract():
    frame = unpack_vietcap_columnar("HPG", payload())
    assert frame.raw_close.iloc[0] == 27500
    assert frame.close.iloc[0] == 27500.0
    assert frame.value.iloc[0] == 2_750_000


@pytest.mark.parametrize("bad", [None, {"t": [1]}, {"t": [1], "o": [1], "h": [1], "l": [1], "c": [1, 2], "v": [1]}, {"t": [1], "o": [math.nan], "h": [1], "l": [1], "c": [1], "v": [1]}])
def test_unpack_rejects_malformed_payloads(bad):
    with pytest.raises(ValueError):
        unpack_vietcap_columnar("HPG", bad)


def test_price_bounds_exchange_and_corporate_action():
    assert validate_price_bounds(10_700, 10_000, "HOSE")
    assert not validate_price_bounds(11_000, 10_000, "HOSE")
    assert validate_price_bounds(11_000, 10_000, "HOSE", is_corporate_action_date=True)


def test_client_rejects_credentialed_endpoint_and_invalid_timeout():
    with pytest.raises(ValueError):
        DirectVCIClient("https://user:secret@example.test")
    with pytest.raises(ValueError):
        DirectVCIClient(timeout=0)


@pytest.mark.parametrize("endpoint", [None, 123, ""])
def test_direct_client_rejects_invalid_endpoint_types(endpoint):
    with pytest.raises(ValueError):
        DirectVCIClient(endpoint=endpoint)


@pytest.mark.parametrize("timeout", [None, "15", math.nan, math.inf])
def test_direct_client_rejects_invalid_timeout_types(timeout):
    with pytest.raises(ValueError):
        DirectVCIClient(timeout=timeout)


def test_unpack_normalizes_integer_valued_kvnd_prices():
    integer_payload = {"t": [1704067200000], "o": [27], "h": [28], "l": [26], "c": [27], "v": [100]}
    assert unpack_vietcap_columnar("HPG", integer_payload).raw_close.iloc[0] == 27000


@pytest.mark.parametrize("max_requests,period_seconds", [(0, 60), (-1, 60), (60, 0), (60, math.nan), (60, math.inf), ("60", 60)])
def test_rate_limiter_rejects_invalid_settings(max_requests, period_seconds):
    with pytest.raises(ValueError):
        RateLimiter(max_requests=max_requests, period_seconds=period_seconds)


def test_vnstock_client_atomic_write_restores_backup_on_dir_fsync_failure(tmp_path, monkeypatch):
    import omega.data.vnstock_client as vsc
    target = tmp_path / "market.parquet"
    atomic_write_with_backup(pd.DataFrame({"value": [1]}), target)
    monkeypatch.setattr(vsc.os, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("directory fsync failure")))
    with pytest.raises(OSError, match="directory fsync failure"):
        atomic_write_with_backup(pd.DataFrame({"value": [2]}), target)
    assert pd.read_parquet(target)["value"].tolist() == [1]


@pytest.mark.parametrize("start,end", [("2026-01-02", "2026-01-01"), (None, "2026-01-01"), ("bad", "2026-01-01")])
def test_market_flow_rejects_invalid_date_range_before_dispatch(start, end):
    class Client:
        def foreign_trade(self, **kwargs):
            raise AssertionError("provider dispatch must not occur")
    with pytest.raises(ValueError, match="date range"):
        VNMarketFlowDataSource(vci_client=Client()).fetch_foreign_flow("HPG", start, end)


def test_archive_fallback_validates_ticker_and_bounds(tmp_path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    pd.DataFrame({"time": pd.to_datetime(["2026-01-01", "2026-02-01"], utc=True), "ticker": ["VIC", "VIC"], "close": [1, 2]}).to_parquet(archive_dir / "HPG.parquet", index=False)
    with pytest.raises(ValueError, match="ticker mismatch"):
        iam._validated_archive_frame(pd.read_parquet(archive_dir / "HPG.parquet"), "HPG", "2026-01-01", "2026-01-31")


def test_archive_fallback_rejects_stale_rows(tmp_path):
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    pd.DataFrame({"time": pd.to_datetime(["2020-01-01"], utc=True), "ticker": ["HPG"], "close": [27000]}).to_parquet(archive_dir / "HPG.parquet", index=False)
    assert iam._validated_archive_frame(pd.read_parquet(archive_dir / "HPG.parquet"), "HPG", "2026-01-01", "2026-01-31").empty


def test_token_bucket_rejects_non_finite_rate():
    with pytest.raises(ValueError):
        TokenBucket(rate=math.inf)


def test_unpack_rejects_empty_mixed_scale_duplicate_and_overflow_payloads():
    empty = {key: [] for key in ("t", "o", "h", "l", "c", "v")}
    with pytest.raises(ValueError, match="no records"):
        unpack_vietcap_columnar("HPG", empty)
    mixed = {"t": [1, 2], "o": [27, 27000], "h": [28, 28000], "l": [26, 26000], "c": [27.5, 27500], "v": [100, 100]}
    with pytest.raises(ValueError, match="Mixed price scale"):
        unpack_vietcap_columnar("HPG", mixed)
    duplicate = payload()
    duplicate["t"] = [1, 1]
    for key in duplicate:
        duplicate[key] = duplicate[key] * 2 if key != "t" else duplicate[key]
    with pytest.raises(ValueError, match="Duplicate timestamps"):
        unpack_vietcap_columnar("HPG", duplicate)
    overflow = payload()
    overflow["v"] = [2**63]
    with pytest.raises(ValueError, match="overflows"):
        unpack_vietcap_columnar("HPG", overflow)


def test_redact_sanitizes_authorization_schemes():
    assert redact("Authorization: Basic dXNlcjpwYXNz") == "Authorization: Basic [REDACTED]"
    assert redact("Authorization: Bearer secret") == "Authorization: Bearer [REDACTED]"


def test_unpack_rejects_nested_timestamp_types():
    for bad_t in ([[1704067200000]], [{"time": 1704067200000}]):
        bad = {"t": bad_t, "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100]}
        with pytest.raises(ValueError):
            unpack_vietcap_columnar("HPG", bad)


def test_unpack_rejects_mixed_unit_duplicate_timestamps():
    bad = {"t": [1704067200, 1704067200000], "o": [27, 27], "h": [28, 28], "l": [26, 26], "c": [27.5, 27.5], "v": [100, 100]}
    with pytest.raises(ValueError, match="Duplicate timestamps"):
        unpack_vietcap_columnar("HPG", bad)


def test_unpack_rejects_non_integral_timestamps():
    bad = payload()
    bad["t"] = [1704067200.5]
    with pytest.raises(ValueError, match="timestamps"):
        unpack_vietcap_columnar("HPG", bad)


def test_redact_sanitizes_url_userinfo():
    url = "https://user:secret@trading.vietcap.com.vn/api/chart"
    redacted = redact(url)
    assert "secret" not in redacted


def test_unpack_preserves_valid_vnd_full_under_1000():
    valid_penny = {"t": [1704067200000], "o": [500], "h": [500], "l": [500], "c": [500], "v": [100]}
    frame = unpack_vietcap_columnar("HPG", valid_penny)
    assert frame.raw_close.iloc[0] == 500
    assert frame.close.iloc[0] == 500.0


def test_unpack_rejects_adjusted_price_inf_overflow():
    with pytest.raises(ValueError):
        unpack_vietcap_columnar("HPG", payload(), adj_ratio=1e308)


def test_client_enforces_ict_1530_same_day_boundary(monkeypatch):
    trading_day = "2026-09-14"
    day_start_ms = 1789344000000
    body = json.dumps({"data": [{"t": [day_start_ms], "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100]}]}).encode()

    class _MockResponse:
        offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, amount):
            chunk = body[self.offset:self.offset + amount]
            self.offset += len(chunk)
            return chunk

    client = DirectVCIClient(opener=lambda req, timeout: _MockResponse())
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: pd.Timestamp("2026-09-14 02:20:00", tz="UTC")))
    with pytest.raises(ValueError, match="15:30|cutoff|trading-session|PIT"):
        client.fetch_history("HPG", trading_day, trading_day)


def _sample_frame(ticker="HPG", n=3):
    return pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC"),
        "ticker": ticker,
        "open": [27000.0] * n,
        "high": [28000.0] * n,
        "low": [26500.0] * n,
        "close": [27500.0] * n,
        "volume": [100000] * n,
    })


def test_production_atomic_write_frame_rejects_empty_frame(tmp_path):
    with pytest.raises(ValueError, match="empty market data"):
        iam.atomic_write_frame(pd.DataFrame(), tmp_path / "empty.parquet")


def test_production_atomic_write_frame_writes_valid_data(tmp_path):
    frame = _sample_frame()
    target = tmp_path / "valid.parquet"
    iam.atomic_write_frame(frame, target)
    assert target.exists()
    assert len(pd.read_parquet(target)) == len(frame)


def test_production_atomic_write_frame_rejects_none_and_non_finite(tmp_path):
    target = tmp_path / "invalid.parquet"
    with pytest.raises(TypeError, match="cannot be None"):
        iam.atomic_write_frame(None, target)
    invalid = _sample_frame()
    invalid.loc[0, "close"] = math.nan
    with pytest.raises(ValueError, match="NaN or Inf"):
        iam.atomic_write_frame(invalid, target)


def test_production_atomic_write_post_replace_failure_reports_rollback(tmp_path):
    target = tmp_path / "market.parquet"
    iam.atomic_write_frame(_sample_frame(), target)
    original = target.read_bytes()
    with pytest.raises(iam.AtomicWriteError) as exc_info:
        iam.atomic_write_frame(
            _sample_frame(n=4),
            target,
            post_replace_hook=lambda: (_ for _ in ()).throw(OSError("directory fsync crash")),
        )
    assert exc_info.value.rolled_back is True
    assert target.read_bytes() == original


def test_production_fetch_history_propagates_provider_transport_error(monkeypatch):
    class FailedVCI:
        def __init__(self, **kwargs):
            pass

        def fetch_history(self, *args):
            raise OSError("VCI unavailable")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"data": [
                {"time": "2026-01-01", "open": 27, "high": 28, "low": 26, "close": 27, "volume": 100},
            ]}).encode()

    monkeypatch.setattr(iam, "DirectVCIClient", FailedVCI)
    with pytest.raises(OSError, match="VCI unavailable"):
        iam.fetch_history("hpg", "2026-01-01", "2026-01-02")


def test_production_fetch_history_does_not_fallback_on_provider_transport_error(monkeypatch):
    class FailedVCI:
        def __init__(self, **kwargs):
            pass

        def fetch_history(self, *args):
            raise OSError("VCI unavailable")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps({"data": [
                {"time": "2025-12-31", "close": 26},
                {"time": "2026-01-01", "close": 27},
                {"time": "2026-01-02", "close": 28},
                {"time": "2026-01-03", "close": 29},
            ]}).encode()

    monkeypatch.setattr(iam, "DirectVCIClient", FailedVCI)
    with pytest.raises(OSError, match="VCI unavailable"):
        iam.fetch_history("HPG", "2026-01-01", "2026-01-02")


def test_production_tcbs_fallback_rejects_unparseable_dates(monkeypatch):
    class FailedVCI:
        def __init__(self, **kwargs):
            pass

        def fetch_history(self, *args):
            return pd.DataFrame()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"data": [{"time": "not-a-date", "close": 27}]}'

    monkeypatch.setattr(iam, "DirectVCIClient", FailedVCI)
    monkeypatch.setattr(iam, "urlopen", lambda request, timeout: Response())
    with pytest.raises(ValueError, match="unparseable dates"):
        iam.fetch_history("HPG", "2026-01-01", "2026-01-02")


@pytest.mark.parametrize("start,end", [(None, "2026-01-02"), ("bad-date", "2026-01-02"), ("2026-01-03", "2026-01-02")])
def test_production_fetch_history_rejects_invalid_date_bounds(start, end):
    with pytest.raises(ValueError, match="date range|date"):
        iam.fetch_history("HPG", start, end)


def test_production_ingest_empty_remote_preserves_cache(tmp_path, monkeypatch):
    target = tmp_path / "FLC.parquet"
    iam.atomic_write_frame(_sample_frame("FLC"), target)
    original = target.read_bytes()
    registry = tmp_path / "symbols_delisted.json"
    registry.write_text(json.dumps(["FLC"]), encoding="utf-8")
    class EmptyVCI:
        def __init__(self, **kwargs):
            pass

        def fetch_history(self, *args):
            return pd.DataFrame()

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"data": []}'

    monkeypatch.setattr(iam, "DirectVCIClient", EmptyVCI)
    monkeypatch.setattr(iam, "urlopen", lambda request, timeout: EmptyResponse())
    with pytest.raises(ValueError, match="delisted=True"):
        iam.ingest_symbol("FLC", "2026-01-01", "2026-01-02", target, registry=registry, archive_dir=tmp_path / "archive")
    assert target.read_bytes() == original


def test_ingest_symbol_propagates_provider_transport_error_without_archive(tmp_path, monkeypatch):
    target = tmp_path / "HPG.parquet"
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("provider down")))
    with pytest.raises(ConnectionError, match="provider down"):
        iam.ingest_symbol("HPG", "2026-01-01", "2026-01-02", target, archive_dir=tmp_path)


def test_ingest_fetch_history_rejects_malformed_symbol_without_tcbs_fallback():
    with pytest.raises(ValueError, match="Invalid ticker"):
        iam.fetch_history("HPG/../x", "2026-01-01", "2026-01-02")


def test_production_ingest_uses_delisted_archive_when_provider_empty(tmp_path, monkeypatch):
    archive_dir = tmp_path / "delisted_archive"
    archive_dir.mkdir()
    archive = archive_dir / "FLC.parquet"
    archived = _sample_frame("FLC", n=2)
    archived.to_parquet(archive, index=False)
    target = tmp_path / "FLC.output.parquet"
    class EmptyVCI:
        def __init__(self, **kwargs):
            pass

        def fetch_history(self, *args):
            return pd.DataFrame()

    class EmptyResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"data": []}'

    monkeypatch.setattr(iam, "DirectVCIClient", EmptyVCI)
    monkeypatch.setattr(iam, "urlopen", lambda request, timeout: EmptyResponse())
    iam.ingest_symbol("flc", "2026-01-01", "2026-01-02", target, archive_dir=archive_dir)
    assert target.exists()
    pd.testing.assert_frame_equal(pd.read_parquet(target), archived)


def test_production_main_routes_through_ingest_symbol(monkeypatch, tmp_path):
    archive_dir = tmp_path / "delisted_archive"
    archive_dir.mkdir()
    archived = _sample_frame("HPG", n=2)
    archived.to_parquet(archive_dir / "HPG.parquet", index=False)
    target = tmp_path / "HPG.parquet"
    registry = tmp_path / "symbols_delisted.json"
    registry.write_text(json.dumps(["HPG"]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "ingest_all_market_data.py", "HPG", "2026-01-01", "2026-01-02",
        "--output", str(target), "--registry", str(registry), "--archive-dir", str(archive_dir),
    ])
    monkeypatch.setattr(iam, "fetch_history", lambda *args, **kwargs: pd.DataFrame())
    assert iam.main() == 0
    pd.testing.assert_frame_equal(pd.read_parquet(target), archived)


class _FakeTransportResponse:
    def __init__(self, raw: bytes, status: int = 200):
        self._raw = raw
        self._offset = 0
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, *args):
        amount = args[0] if args else -1
        if amount < 0:
            amount = len(self._raw) - self._offset
        chunk = self._raw[self._offset:self._offset + amount]
        self._offset += len(chunk)
        return chunk


def test_graph_fetcher_vci_financial_raw_exercises_genuine_direct_vci_client_get():
    recorded_urls = []
    recorded_timeouts = []

    def fake_transport_opener(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        recorded_urls.append(url)
        recorded_timeouts.append(timeout)
        assert request.get_method() == "GET"
        user_agent = request.headers.get("User-agent", request.headers.get("User-Agent", ""))
        assert "Mozilla" in user_agent or "OMEGA_QUANT" in user_agent
        if "statistics-financial" in url:
            data = {"data": [{"ticker": "HPG", "pe": 10.5, "pb": 1.2}]}
        else:
            data = {"data": {"years": [2025, 2026], "quarters": [1, 2]}}
        return _FakeTransportResponse(json.dumps(data).encode(), status=200)

    client = DirectVCIClient(opener=fake_transport_opener)
    fetcher = GraphFetcher(vci_client=client)
    res = fetcher.vci_financial_raw("HPG", timeout=22)

    assert set(res.keys()) == {"income_statement", "balance_sheet", "cash_flow", "ratios"}
    assert res["ratios"]["data"][0]["pe"] == 10.5
    assert res["income_statement"]["data"]["years"] == [2025, 2026]
    assert len(recorded_urls) == 4
    assert all(t == 22 for t in recorded_timeouts)
    assert all("/HPG/" in u for u in recorded_urls)


def test_graph_fetcher_vci_financial_raw_direct_vci_timeout_error():
    def timing_out_opener(request, timeout=None):
        raise TimeoutError("connection timed out to Vietcap gateway")

    client = DirectVCIClient(opener=timing_out_opener)
    fetcher = GraphFetcher(vci_client=client)
    with pytest.raises(RuntimeError, match="VCI request failed: connection timed out"):
        fetcher.vci_financial_raw("HPG")


def test_graph_fetcher_vci_financial_raw_direct_vci_http_404_error():
    def not_found_opener(request, timeout=None):
        raise HTTPError(request.full_url, 404, "Not Found", {}, None)

    client = DirectVCIClient(opener=not_found_opener)
    fetcher = GraphFetcher(vci_client=client)
    with pytest.raises(RuntimeError, match="HTTP Error 404"):
        fetcher.vci_financial_raw("HPG")


def test_graph_fetcher_vci_financial_raw_direct_vci_http_429_retry_exhaustion(monkeypatch):
    calls = 0
    sleeps = []

    def rate_limited_opener(request, timeout=None):
        nonlocal calls
        calls += 1
        raise HTTPError(request.full_url, 429, "Too Many Requests", {"Retry-After": "0.5"}, None)

    monkeypatch.setattr(time, "sleep", lambda delay: sleeps.append(delay))
    client = DirectVCIClient(opener=rate_limited_opener, max_attempts=3)
    fetcher = GraphFetcher(vci_client=client)

    with pytest.raises(RuntimeError, match="429"):
        fetcher.vci_financial_raw("HPG")

    assert calls == 3
    assert sleeps == [0.5, 0.5]


def test_direct_client_get_retries_normal_429_response(monkeypatch):
    calls = 0
    sleeps = []

    def opener(request, timeout=None):
        nonlocal calls
        calls += 1
        return _FakeTransportResponse(b"{}", status=429 if calls == 1 else 200)

    monkeypatch.setattr(time, "sleep", lambda delay: sleeps.append(delay))
    response = DirectVCIClient(opener=opener).get("https://iq.vietcap.com.vn/api/iq-insight-service/v1/test")
    assert response.status_code == 200
    assert calls == 2
    assert sleeps == [1]


@pytest.mark.parametrize("status_code", [300, 301, 302, 400, 404, 500, 503])
def test_direct_client_get_rejects_all_non_success_statuses(status_code):
    calls = 0

    def opener(request, timeout=None):
        nonlocal calls
        calls += 1
        return _FakeTransportResponse(b"{}", status=status_code)

    with pytest.raises(RuntimeError, match=f"HTTP Error {status_code}"):
        DirectVCIClient(opener=opener, max_attempts=10).get("https://iq.vietcap.com.vn/api/test")
    assert calls == 1


def test_direct_client_get_bounds_normal_429_retry(monkeypatch):
    calls = 0
    sleeps = []

    def opener(request, timeout=None):
        nonlocal calls
        calls += 1
        return _FakeTransportResponse(b"{}", status=429)

    monkeypatch.setattr(time, "sleep", lambda delay: sleeps.append(delay))
    with pytest.raises(RuntimeError, match="HTTP 429"):
        DirectVCIClient(opener=opener, max_attempts=3).get("https://iq.vietcap.com.vn/api/test")
    assert calls == 3
    assert sleeps == [1, 2]


@pytest.mark.parametrize("url", [
    "https://example.com/api/test",
    "https://iq.vietcap.com.vn/private/test",
    "https://127.0.0.1/api/test",
])
def test_direct_client_get_rejects_unapproved_origins_and_paths(url):
    with pytest.raises(ValueError, match="approved VCI"):
        DirectVCIClient().get(url)


def test_graph_fetcher_vci_financial_raw_direct_vci_payload_size_limit():
    def huge_payload_opener(request, timeout=None):
        return _FakeTransportResponse(b"X" * 1024)

    client = DirectVCIClient(opener=huge_payload_opener, max_payload_bytes=512)
    fetcher = GraphFetcher(vci_client=client)
    with pytest.raises(ValueError, match="exceeds size limit"):
        fetcher.vci_financial_raw("HPG")


@pytest.mark.parametrize("bad_envelope,expected_err", [
    ({"data": {"years": [], "quarters": [1]}}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
    ({"data": {"years": [2026], "quarters": []}}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
    ({"data": None}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
    ({}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
    ({"data": {"years": [2026], "quarters": [1]}, "error": "upstream fault"}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
    ({"data": {"years": [2026], "quarters": [1]}, "truncated": True}, "VCI_STATEMENT_CONTRACT_VIOLATION"),
])
def test_graph_fetcher_vci_financial_raw_statement_contract_violations(bad_envelope, expected_err):
    def opener(request, timeout=None):
        return _FakeTransportResponse(json.dumps(bad_envelope).encode())

    client = DirectVCIClient(opener=opener)
    fetcher = GraphFetcher(vci_client=client)
    with pytest.raises(ValueError, match=expected_err):
        fetcher.vci_financial_raw("HPG")


@pytest.mark.parametrize("bad_ratios", [
    {"data": []},
    {"data": None},
    {"data": {}},
    {},
])
def test_graph_fetcher_vci_financial_raw_ratio_contract_violations(bad_ratios):
    def opener(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "statistics-financial" in url:
            data = bad_ratios
        else:
            data = {"data": {"years": [2026], "quarters": [1]}}
        return _FakeTransportResponse(json.dumps(data).encode())

    client = DirectVCIClient(opener=opener)
    fetcher = GraphFetcher(vci_client=client)
    with pytest.raises(ValueError, match="VCI_RATIO_CONTRACT_VIOLATION"):
        fetcher.vci_financial_raw("HPG")


@pytest.mark.parametrize("bad_endpoint", [
    None,
    "",
    "http://insecure.vietcap.com.vn",
    "ftp://vietcap.com.vn",
    "https://user:pass@iq.vietcap.com.vn",
])
def test_direct_client_get_rejects_invalid_endpoints(bad_endpoint):
    client = DirectVCIClient()
    with pytest.raises((ValueError, TypeError)):
        client.get(bad_endpoint)


@pytest.mark.parametrize("bad_timeout", [
    math.nan,
    math.inf,
    -1.0,
    0,
    0.0,
])
def test_direct_client_get_and_init_rejects_non_finite_or_non_positive_timeout(bad_timeout):
    with pytest.raises(ValueError, match="timeout must be positive and finite"):
        DirectVCIClient(timeout=bad_timeout)

    client = DirectVCIClient()
    with pytest.raises(ValueError, match="timeout must be positive and finite"):
        client.get("https://iq.vietcap.com.vn/api/test", timeout=bad_timeout)


def test_direct_client_init_rejects_unapproved_post_endpoint():
    for bad_endpoint in (
        "https://evil.example/api/chart/OHLCChart/gap-chart",
        "https://trading.vietcap.com.vn/private/chart",
        "http://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
    ):
        with pytest.raises(ValueError):
            DirectVCIClient(endpoint=bad_endpoint)


def test_direct_client_get_rejects_bool_timeout():
    for bad_timeout in (True, False):
        with pytest.raises(ValueError, match="timeout must be positive and finite"):
            DirectVCIClient().get("https://iq.vietcap.com.vn/api/test", timeout=bad_timeout)


def test_unpack_vietcap_columnar_rejects_bool_scalars():
    for key in ("t", "o", "h", "l", "c", "v"):
        bad = payload()
        bad[key] = [True]
        with pytest.raises(ValueError):
            unpack_vietcap_columnar("HPG", bad)
    with pytest.raises(ValueError):
        unpack_vietcap_columnar("HPG", payload(), adj_ratio=True)


def test_f001_oversized_integer_scalars_fail_closed():
    for key in ("t", "o", "h", "l", "c", "v"):
        bad = payload()
        bad[key] = [10**400]
        with pytest.raises(ValueError):
            unpack_vietcap_columnar("HPG", bad)


def test_f001_oversized_price_bound_scalars_fail_closed():
    assert not validate_price_bounds(10**400, 10_000, "HOSE")
    assert not validate_price_bounds(10_000, 10**400, "HOSE")


def test_f002_url_validation_rejects_traversal_query_and_fragment():
    for url in (
        "https://trading.vietcap.com.vn/api/../private",
        "https://trading.vietcap.com.vn/api/%2e%2e/private",
        "https://trading.vietcap.com.vn/api/%252e%252e/private",
        "https://iq.vietcap.com.vn/v1/test?smuggled=1",
        "https://iq.vietcap.com.vn/v1/test#fragment",
    ):
        with pytest.raises(ValueError, match="approved VCI"):
            DirectVCIClient().get(url)


@pytest.mark.parametrize("bad_ratio", [None, "1", 0.0, -1.0, math.nan, math.inf, 1000.0001])
def test_unpack_rejects_invalid_or_unbounded_adjustment_ratio(bad_ratio):
    with pytest.raises((ValueError, TypeError), match="adjustment ratio|float"):
        unpack_vietcap_columnar("HPG", payload(), adj_ratio=bad_ratio)


@pytest.mark.parametrize("ratio", [0.01, 1000.0])
def test_unpack_rejects_adjusted_prices_outside_vnd_full_bounds(ratio):
    with pytest.raises(ValueError, match="VND_FULL bounds"):
        unpack_vietcap_columnar("HPG", payload(), adj_ratio=ratio)


def test_direct_client_enforces_hard_resource_ceilings():
    with pytest.raises(ValueError):
        DirectVCIClient(max_payload_bytes=64 * 1024 * 1024 + 1)
    with pytest.raises(ValueError):
        DirectVCIClient(max_attempts=11)
    client = DirectVCIClient(max_payload_bytes=64 * 1024 * 1024, max_attempts=10)
    assert client.max_payload_bytes == 64 * 1024 * 1024
    assert client.max_attempts == 10


def test_unpack_vietcap_columnar_rejects_unsorted_timestamps():
    bad = payload()
    bad.update({key: [value[0], value[0]] for key, value in bad.items()})
    bad["t"] = [1704067200000, 1703980800000]
    with pytest.raises(ValueError, match="chronological"):
        unpack_vietcap_columnar("HPG", bad)


def test_direct_client_fetch_history_checks_http_status():
    def opener(request, timeout=None):
        return _FakeTransportResponse(b'{"data": {}}', status=500)

    with pytest.raises(RuntimeError, match="HTTP Error 500"):
        DirectVCIClient(opener=opener, max_attempts=1).fetch_history("HPG", "2026-01-01", "2026-01-02")


def test_direct_client_fetch_history_rejects_countback_overflow():
    with pytest.raises(ValueError, match="countBack"):
        DirectVCIClient().fetch_history("HPG", "1800-01-01", "2026-01-01")


@pytest.mark.parametrize("bad_rate,bad_cap", [
    (math.nan, 10.0),
    (math.inf, 10.0),
    (-1.0, 10.0),
    (0.0, 10.0),
    (10.0, math.nan),
    (10.0, math.inf),
    (10.0, -1.0),
    (10.0, 0.0),
])
def test_token_bucket_boundary_rejections(bad_rate, bad_cap):
    with pytest.raises(ValueError):
        TokenBucket(rate=bad_rate, capacity=bad_cap)


@pytest.mark.parametrize("raw_c,prev_c", [
    (math.nan, 10000),
    (math.inf, 10000),
    (10000, math.nan),
    (10000, math.inf),
    (None, 10000),
    (10000, None),
])
def test_validate_price_bounds_rejects_non_finite_or_none(raw_c, prev_c):
    assert not validate_price_bounds(raw_c, prev_c, "HOSE")


@pytest.mark.parametrize("bad_bool", [True, False])
def test_f001_numeric_limits_reject_booleans(bad_bool):
    with pytest.raises(ValueError):
        DirectVCIClient(max_payload_bytes=bad_bool)
    with pytest.raises(ValueError):
        DirectVCIClient(max_attempts=bad_bool)
    with pytest.raises(ValueError):
        TokenBucket(rate=bad_bool)
    with pytest.raises(ValueError):
        TokenBucket(capacity=bad_bool)


@pytest.mark.parametrize("raw_c,prev_c,exchange", [(True, 10000, "HOSE"), (10000, True, "HOSE"), (10000, 10000, None), (10000, 10000, 123)])
def test_f001_validate_price_bounds_rejects_bool_and_invalid_exchange(raw_c, prev_c, exchange):
    assert not validate_price_bounds(raw_c, prev_c, exchange)


@pytest.mark.parametrize("flag_name", ["is_corporate_action_date", "is_first_listing_date"])
@pytest.mark.parametrize("flag", [0, 1, "true", "false", 1.0, None])
def test_f001_validate_price_bounds_rejects_non_bool_flags(flag_name, flag):
    flags = {flag_name: flag}
    assert not validate_price_bounds(10_000, 10_000, "HOSE", **flags)


@pytest.mark.parametrize("exchange", ["", " ", "BOGUS", "NYSE", "NASDAQ", "hose_extra", None, 123])
def test_f001_validate_price_bounds_rejects_unknown_exchanges(exchange):
    assert not validate_price_bounds(10_000, 10_000, exchange)


def test_f002_url_validation_rejects_oversized_url_before_request():
    client = DirectVCIClient(opener=lambda *_args, **_kwargs: pytest.fail("HTTP dispatch must not occur"))
    oversized_url = "https://iq.vietcap.com.vn/api/" + ("a" * 2020)
    with pytest.raises(ValueError, match="approved VCI"):
        client.get(oversized_url)


def test_f002_url_validation_rejects_oversized_query_before_parse():
    client = DirectVCIClient(opener=lambda *_args, **_kwargs: pytest.fail("HTTP dispatch must not occur"))
    oversized_query = "https://iq.vietcap.com.vn/api/test?" + ("a" * 1025)
    with pytest.raises(ValueError, match="approved VCI"):
        client.get(oversized_query)


def test_f002_fetch_history_returns_explicit_pit_fields():
    bar_ms = 1704153600000
    raw = json.dumps({"data": [{"t": [bar_ms], "o": [27], "h": [28], "l": [26], "c": [27.5], "v": [100]}]}).encode()
    client = DirectVCIClient(opener=lambda request, timeout=None: _FakeTransportResponse(raw))
    frame = client.fetch_history("HPG", "2024-01-01", "2024-01-05", as_of="2024-01-03T15:30:00Z")
    assert {"as_of", "available_at"}.issubset(frame.columns)
    assert (frame["as_of"] <= frame["available_at"]).all()
    assert (frame["available_at"] <= pd.Timestamp("2024-01-03T15:30:00Z")).all()


@pytest.mark.parametrize("cli_args", [["--unknown-flag"], ["--malicious=true"], ["-x"], ["--output", "target.parquet", "--bogus"]])
def test_f003_ingest_cli_rejects_unknown_and_flag_smuggling(cli_args):
    script = REPO_ROOT / "scripts" / "ingest_all_market_data.py"
    result = subprocess.run([sys.executable, str(script), "HPG", "2026-01-01", "2026-01-02", *cli_args], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr


def test_f004_capped_reader_reads_chunks_and_rejects_oversized_stream():
    class Stream(_FakeTransportResponse):
        def __init__(self):
            super().__init__(b"", 200)
            self.calls = []
            self.remaining = 3

        def read(self, amount):
            self.calls.append(amount)
            self.remaining -= 1
            return b"x" * 1024 if self.remaining >= 0 else b""

    stream = Stream()
    client = DirectVCIClient(opener=lambda request, timeout=None: stream, max_payload_bytes=2048)
    with pytest.raises(ValueError, match="exceeds size limit"):
        client.get("https://iq.vietcap.com.vn/api/test")
    assert stream.calls == [2048, 1024]


@pytest.mark.parametrize("bad_val", [math.nan, math.inf, 0, -1.0])
def test_graph_fetcher_retry_timing_boundaries_reject_non_finite_or_non_positive(bad_val):
    with pytest.raises(ValueError, match="max_retry_wall_time must be positive and finite"):
        GraphFetcher(max_retry_wall_time=bad_val)
    with pytest.raises(ValueError, match="retry_delay must be positive and finite"):
        GraphFetcher(retry_delay=bad_val)


def test_production_atomic_write_frame_rollback_cleans_temporary_files_on_failure(tmp_path):
    target = tmp_path / "protected_target.parquet"
    original_frame = _sample_frame("HPG", n=3)
    iam.atomic_write_frame(original_frame, target)
    original_bytes = target.read_bytes()

    corrupt_frame = _sample_frame("HPG", n=2)
    corrupt_frame.loc[0, "close"] = math.nan

    with pytest.raises(ValueError, match="NaN or Inf"):
        iam.atomic_write_frame(corrupt_frame, target)

    assert target.read_bytes() == original_bytes
    tmp_files = list(tmp_path.glob("*.tmp")) + list(tmp_path.glob(".*.tmp"))
    assert tmp_files == []
