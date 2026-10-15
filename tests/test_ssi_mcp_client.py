"""Adversarial SSI transport, comparison and updater integration checks."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest

from omega.data.ssi_mcp_client import SSI_ENDPOINT, SSIMCPClient, reconcile_ssi_vci

NOW = pd.Timestamp("2026-10-15T10:00:00Z")


def row(**changes):
    return dict(symbol="SSI", trading_date="14/10/2026", open=30000,
                high=31000, low=29000, close=30500, volume=1000, **changes)


def client(payload=None, **kwargs):
    return SSIMCPClient(call_tool=lambda *_: {"stocks": [row()]} if payload is None else payload,
                        clock=lambda: NOW, **kwargs)


def test_ssi_canonical_units_provenance_and_cutoff():
    frame = client().fetch_history("SSI", "2026-10-14", "2026-10-14")
    assert frame.close.tolist() == [30500]
    assert frame.volume.tolist() == [1000]
    assert frame.available_at.tolist() == [NOW]
    assert frame.as_of.iloc[0] == pd.Timestamp("2026-10-14T15:30:00+07:00")
    assert frame.attrs["historical_pit_verified"] is False
    assert client().fetch_history("SSI", "2026-10-14", "2026-10-14", as_of=NOW).shape[0] == 1
    assert client().fetch_history("SSI", "2026-10-14", "2026-10-14", as_of=NOW - pd.Timedelta(nanoseconds=1)).empty


@pytest.mark.parametrize("value", [None, "", True, [], {}, float("nan"), float("inf"), -float("inf"), -1, 0, 1e13, "NaN", "1e309"])
def test_invalid_prices_fail_closed(value):
    data = row()
    data["close"] = value
    with pytest.raises(ValueError):
        client({"stocks": [data]}).fetch_history("SSI", "2026-10-14", "2026-10-14")


@pytest.mark.parametrize("value", [None, [], True, -1, 0.5, 1e13, "Infinity"])
def test_invalid_volumes_fail_closed(value):
    data = row()
    data["volume"] = value
    with pytest.raises(ValueError):
        client({"stocks": [data]}).fetch_history("SSI", "2026-10-14", "2026-10-14")


@pytest.mark.parametrize("payload", [[], {}, {"stocks": None}, {"stocks": {}}, {"stocks": [None]},
                                      {"stocks": [row()] * 201}, {"stocks": [row(), row()]},
                                      {"stocks": [], "extra": float("nan")}])
def test_malformed_partial_duplicate_payloads(payload):
    with pytest.raises(ValueError):
        client(payload).fetch_history("SSI", "2026-10-14", "2026-10-14")


@pytest.mark.parametrize("symbol,start,end", [(None, "2026-10-14", "2026-10-14"),
    ("SSI;pwd", "2026-10-14", "2026-10-14"), ("--help", "2026-10-14", "2026-10-14"),
    ("SSI", None, "2026-10-14"), ("SSI", "2026-02-30", "2026-10-14"),
    ("SSI", "2015-01-01", "2026-10-14"), ("SSI", "2026-10-16", "2026-10-16"),
    ("SSI", "2026-10-14", "2026-10-13"), ("SSI", "﻿2026-10-14", "2026-10-14"),
    ("SSI", "2026-10-14\r\n", "2026-10-14")])
def test_request_validation(symbol, start, end):
    with pytest.raises(ValueError):
        client().fetch_history(symbol, start, end)


@pytest.mark.parametrize("change", [{"symbol": "VCB"}, {"trading_date": "2026-10-14"},
    {"trading_date": "10/10/2026"}, {"trading_date": "02/09/2026"},
    {"trading_date": "16/10/2026"}, {"low": 40000}, {"high": 1}])
def test_row_identity_calendar_and_ohlc(change):
    data = row()
    data.update(change)
    with pytest.raises(ValueError):
        client({"stocks": [data]}).fetch_history("SSI", "2026-09-01", "2026-10-15")


def test_session_close_inclusive():
    data = row()
    data["trading_date"] = "15/10/2026"
    for now, valid in [(pd.Timestamp("2026-10-15T15:30:00+07:00"), True),
                       (pd.Timestamp("2026-10-15T15:29:59.999999999+07:00"), False)]:
        instance = SSIMCPClient(call_tool=lambda *_: {"stocks": [data]}, clock=lambda: now)
        if valid:
            assert len(instance.fetch_history("SSI", "2026-10-15", "2026-10-15")) == 1
        else:
            with pytest.raises(ValueError):
                instance.fetch_history("SSI", "2026-10-15", "2026-10-15")


def test_pagination_short_page_and_replay():
    dates = pd.bdate_range("2025-10-01", "2026-10-14")
    from omega.data.calendar import VNTradingCalendar
    dates = [d for d in dates if VNTradingCalendar.is_trading_day(d.to_pydatetime())][:201]
    records = []
    for date in dates:
        data = row()
        data["trading_date"] = date.strftime("%d/%m/%Y")
        records.append(data)
    calls = []

    def call(tool, arguments):
        calls.append(arguments)
        offset = (arguments["pageIndex"] - 1) * 200
        return {"stocks": records[offset:offset + 200]}

    instance = SSIMCPClient(call_tool=call, clock=lambda: NOW)
    assert len(instance.fetch_history("SSI", "2025-10-01", "2026-10-14")) == 201
    assert [c["pageIndex"] for c in calls] == [1, 2]
    instance.call_tool = lambda *_: {"stocks": records[:200]}
    with pytest.raises(ValueError, match="Duplicate"):
        instance.fetch_history("SSI", "2025-10-01", "2026-10-14")


def test_timeout_and_429_retry_exhaustion_redacts():
    import httpx
    for error in (TimeoutError("https://user:secret@example.com?token=secret"),
                  httpx.HTTPStatusError("secret", request=httpx.Request("POST", SSI_ENDPOINT),
                                        response=httpx.Response(429))):
        calls, delays = [], []

        def call(*_):
            calls.append(1)
            raise error

        instance = SSIMCPClient(call_tool=call, sleeper=delays.append, clock=lambda: NOW)
        with pytest.raises(TimeoutError) as caught:
            instance.fetch_history("SSI", "2026-10-14", "2026-10-14")
        assert len(calls) == 3 and delays == [1, 2]
        assert "secret" not in str(caught.value) and caught.value.__suppress_context__


def test_nonretryable_failure_and_payload_bound():
    calls = []

    def call(*_):
        calls.append(1)
        raise ValueError("https://user:password@example.com")

    with pytest.raises(RuntimeError, match="^SSI MCP request failed$"):
        SSIMCPClient(call_tool=call, clock=lambda: NOW).fetch_history("SSI", "2026-10-14", "2026-10-14")
    assert len(calls) == 1
    with pytest.raises(ValueError):
        client({"stocks": [], "padding": "a" * (2 * 1024 * 1024)}).fetch_history("SSI", "2026-10-14", "2026-10-14")


@pytest.mark.parametrize("endpoint", ["http://mcp.ssi.com.vn/mcp", "https://127.0.0.1/mcp",
    "https://2130706433/mcp", "https://0177.0.0.1/mcp", "https://0x7f000001/mcp",
    "https://[::ffff:127.0.0.1]/mcp", "https://[64:ff9b::7f00:1]/mcp",
    "https://169.254.169.254/mcp", "https://192.0.2.1/mcp", "https://100.64.0.1/mcp",
    "https://user:secret@mcp.ssi.com.vn/mcp", "https://mcp.ssi.com.vn/mcp?token=secret",
    "https://mcp.ssi.com.vn.evil/mcp", "https://mcp.ssi.com.vn:443/mcp"])
def test_endpoint_identity_ipv4_ipv6_special_use_userinfo_redaction(endpoint):
    with pytest.raises(ValueError) as caught:
        SSIMCPClient(endpoint=endpoint)
    assert "secret" not in str(caught.value) and endpoint not in str(caught.value)


def test_concurrent_callers_are_isolated():
    barrier = threading.Barrier(2)

    def call(_, arguments):
        barrier.wait(timeout=5)
        data = row()
        data["symbol"] = arguments["symbol"]
        arguments.clear()
        return {"stocks": [data]}

    instance = SSIMCPClient(call_tool=call, clock=lambda: NOW)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(instance.fetch_history, symbol, "2026-10-14", "2026-10-14") for symbol in ("SSI", "VCB")]
        assert [f.result().ticker.tolist() for f in futures] == [["SSI"], ["VCB"]]


def comparison_frame():
    return client().fetch_history("SSI", "2026-10-14", "2026-10-14").rename(columns={"time": "date"})


def test_reconciliation_never_overwrites_or_promotes_provenance():
    ssi = comparison_frame()
    before = ssi.copy(deep=True)
    vci = ssi.copy(deep=True)
    vci["adjusted"] = "backward_adjusted"
    result = reconcile_ssi_vci(ssi, vci)
    assert result["findings"][0]["reason"] == "not_comparable"
    pd.testing.assert_frame_equal(ssi, before)
    vci["adjusted"] = "provider_adjusted"
    vci["close"] = 30000
    assert reconcile_ssi_vci(ssi, vci)["findings"][0]["field"] == "close"
    assert reconcile_ssi_vci(ssi, None)["status"] == "unavailable"
    assert ssi.attrs["historical_pit_verified"] is False


def test_reconciliation_zero_volume_missing_keys_and_duplicates():
    ssi = comparison_frame()
    ssi["volume"] = 0
    vci = ssi.copy(deep=True)
    assert reconcile_ssi_vci(ssi, vci)["status"] == "ok"
    vci["ticker"] = "VCB"
    assert {f["reason"] for f in reconcile_ssi_vci(ssi, vci)["findings"]} == {"missing_ssi", "missing_vci"}
    with pytest.raises(ValueError):
        reconcile_ssi_vci(ssi, pd.concat([ssi, ssi]))


def test_sparse_env_preserved(monkeypatch):
    monkeypatch.setenv("SSI_MCP_TOKEN", "secret")
    monkeypatch.setenv("OMEGA_UNRELATED", "preserved")
    client().fetch_history("SSI", "2026-10-14", "2026-10-14")
    import os
    assert os.environ["SSI_MCP_TOKEN"] == "secret"
    assert os.environ["OMEGA_UNRELATED"] == "preserved"


def test_updater_ssi_preserves_observed_metadata_and_compressed_storage(tmp_path):
    from scripts import update_market_data as updater
    frame = updater.fetch_one_symbol(client(), "SSI", "2026-10-14", "2026-10-14", "HOSE")
    assert frame.columns.tolist() == updater.CANONICAL_COLUMNS
    assert frame.source.tolist() == ["SSI_MCP"]
    assert frame.available_at.tolist() == [NOW]
    assert updater.validate_dataframe(frame)[0]
    path = tmp_path / "canonical.parquet"
    updater.atomic_write_with_backup(frame, path, backup=False)
    import pyarrow.parquet as pq
    assert pq.ParquetFile(path).metadata.row_group(0).column(0).compression == "ZSTD"
    pd.testing.assert_frame_equal(pd.read_parquet(path), frame)


def test_updater_ssi_workers_overlap_and_failure_has_no_fallback(monkeypatch):
    from scripts import update_market_data as updater
    barrier = threading.Barrier(2)

    def call(_, arguments):
        barrier.wait(timeout=5)
        data = row()
        data["symbol"] = arguments["symbol"]
        return {"stocks": [data]}

    instance = SSIMCPClient(call_tool=call, clock=lambda: NOW)
    frame, stats = updater.fetch_symbols(instance, ["SSI", "VCB"],
        {"SSI": "HOSE", "VCB": "HOSE"}, "2026-10-14", "2026-10-14")
    assert stats["fetched"] == 2 and stats["errors"] == 0
    assert set(frame.source) == {"SSI_MCP"}
    calls = []

    def fail(*_):
        calls.append(1)
        raise TimeoutError("secret")

    instance.call_tool = fail
    instance.sleeper = lambda _: None
    frame, stats = updater.fetch_symbols(instance, ["SSI"], {"SSI": "HOSE"},
                                          "2026-10-14", "2026-10-14")
    assert frame.empty and stats["errors"] == 1 and len(calls) == 3
    assert "secret" not in json.dumps(stats)


def test_updater_reconciliation_vci_is_reference_only(monkeypatch, tmp_path):
    from scripts import update_market_data as updater
    primary = updater.fetch_one_symbol(client(), "SSI", "2026-10-14", "2026-10-14", "HOSE")
    before = primary.copy(deep=True)
    reference = primary.copy(deep=True)
    reference["close"] = 30000
    monkeypatch.setattr(updater, "_create_vci_reference_client", lambda: object())
    monkeypatch.setattr(updater, "fetch_symbols", lambda *a: (reference, {"errors": 0}))
    result = updater._run_reconciliation(primary, ["SSI"], {"SSI": "HOSE"}, "2026-10-14",
        tmp_path / "state.json", tmp_path / "latest.json")
    assert result["provider_primary"] == "SSI_MCP" and result["status"] == "warning"
    pd.testing.assert_frame_equal(primary, before)


def test_updater_atomic_write_failure_preserves_old_data(monkeypatch, tmp_path):
    from scripts import update_market_data as updater
    path = tmp_path / "canonical.parquet"
    path.write_bytes(b"previous")

    def fail(*args, **kwargs):
        raise OSError("injected write failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail)
    with pytest.raises(OSError):
        updater.atomic_write_with_backup(comparison_frame(), path, backup=False)
    assert path.read_bytes() == b"previous"


def test_reconciliation_rejects_invalid_reference_even_if_adjustment_differs():
    primary = comparison_frame()
    reference = primary.copy(deep=True)
    reference["adjusted"] = "backward_adjusted"
    reference["close"] = float("inf")
    with pytest.raises(ValueError):
        reconcile_ssi_vci(primary, reference)


def test_migration_equal_overlap_preserves_vci_and_ssi_evidence():
    from scripts import update_market_data as updater
    incoming = updater.fetch_one_symbol(client(), "SSI", "2026-10-14", "2026-10-14", "HOSE")
    retained = incoming.copy(deep=True)
    retained["source"] = "vnstock_vci"
    retained["adjusted"] = "backward_adjusted"
    retained["available_at"] = updater._vci_available_at(retained.date)
    old = retained.copy(deep=True)
    merged, errors = updater.merge_canonical_and_new(retained, incoming, in_place=False)
    assert not errors
    pd.testing.assert_frame_equal(merged, old, check_dtype=False)
    assert incoming.available_at.iloc[0] == NOW
    assert incoming.adjusted.iloc[0] == "provider_adjusted"
    assert incoming.attrs.get("historical_pit_verified", False) is False
    ancient = old.copy(deep=True)
    ancient["date"] = pd.Timestamp("2015-01-05")
    ancient["available_at"] = updater._vci_available_at(ancient.date)
    incremental = incoming.copy(deep=True)
    incremental["date"] = pd.Timestamp("2026-10-15")
    incremental["as_of"] = pd.Timestamp("2026-10-15T15:30:00+07:00")
    merged, errors = updater.merge_canonical_and_new(pd.concat([ancient, old]), pd.concat([incoming, incremental]), in_place=False)
    assert not errors and len(merged) == 3
    assert merged.source.tolist() == ["vnstock_vci", "vnstock_vci", "SSI_MCP"]
    assert merged.available_at.iloc[-1] == NOW
    later = incoming.copy(deep=True)
    later["available_at"] = NOW + pd.Timedelta(seconds=1)
    merged, errors = updater.merge_canonical_and_new(incoming, later, in_place=False)
    assert not errors and merged.available_at.iloc[0] == NOW


@pytest.mark.parametrize("field,value", [("open", 30001), ("volume", 1001),
    ("exchange", "HNX"), ("price_scale", "THOUSANDS")])
def test_migration_conflicts_fail_closed(field, value):
    from scripts import update_market_data as updater
    incoming = updater.fetch_one_symbol(client(), "SSI", "2026-10-14", "2026-10-14", "HOSE")
    retained = incoming.copy(deep=True)
    retained["source"] = "vnstock_vci"
    retained["adjusted"] = "backward_adjusted"
    incoming[field] = value
    _, errors = updater.merge_canonical_and_new(retained, incoming, in_place=False)
    assert errors == ["overlap conflict: SSI 2026-10-14"]


def test_ssi_bootstrap_and_old_backfill_report_unsupported(monkeypatch, tmp_path):
    from scripts import update_market_data as updater
    monkeypatch.setattr(updater, "load_universe_from_json", lambda _: {"hsx": ["SSI"], "hnx": []})
    monkeypatch.setattr(updater, "_create_vnstock_client", client)
    monkeypatch.setattr(updater, "fetch_symbols", lambda *a, **k: pytest.fail("unsupported fetch"))
    path = tmp_path / "canonical.parquet"
    result = updater.run_updater(canonical_path=path, end_date="2026-10-14")
    assert result["status"] == "unsupported_history" and not path.exists()
    retained = updater.fetch_one_symbol(client(), "SSI", "2026-10-14", "2026-10-14", "HOSE")
    retained["date"] = pd.Timestamp("2015-01-05")
    retained.to_parquet(path)
    before = path.read_bytes()
    result = updater.run_updater(canonical_path=path, start_date="2015-01-01", end_date="2026-10-14")
    assert result["status"] == "unsupported_history" and path.read_bytes() == before


def test_ssi_full_repair_preserves_old_history_without_network(tmp_path):
    from scripts import update_market_data as updater
    instance = SSIMCPClient(clock=lambda: NOW, call_tool=lambda *a: pytest.fail("unsupported repair"))
    frame, stats = updater.run_full_history_refetch(instance, [{"symbol": "SSI"}], {"SSI": "HOSE"}, "2026-10-14")
    assert frame.empty and stats["failed"] == 1 and stats["success"] == 0
    assert stats["details"][0]["status"] == "unsupported_history"
    assert "2015-01-01" in stats["details"][0]["reason"]


def test_ssi_history_bound_inclusive_and_no_silent_truncation():
    instance = client({"stocks": []})
    assert instance.history_start() == pd.Timestamp("2024-10-15")
    assert instance.fetch_history("SSI", "2024-10-15", "2026-10-14").empty
    with pytest.raises(ValueError, match="earliest supported date 2024-10-15"):
        instance.fetch_history("SSI", "2024-10-14", "2026-10-14")


def test_cleanup_cannot_delete_active_writer_or_unowned_artifacts(monkeypatch, tmp_path):
    from scripts import update_market_data as updater
    from filelock import FileLock, Timeout
    target = tmp_path / "canonical.parquet"
    foreign = tmp_path / "foreign.parquet.tmp"
    foreign.write_bytes(b"foreign")
    chunks = tmp_path / "omega_fetch_chunks_foreign"
    chunks.mkdir()
    (chunks / "chunk.parquet").write_bytes(b"active")
    original = pd.DataFrame.to_parquet
    entered, release = threading.Event(), threading.Event()

    def paused(frame, path, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return original(frame, path, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_parquet", paused)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(updater.atomic_write_with_backup, comparison_frame(), target, False)
        try:
            assert entered.wait(timeout=10)
            assert updater.cleanup_temporary_market_files(tmp_path) == 0
            assert foreign.read_bytes() == b"foreign"
            assert (chunks / "chunk.parquet").read_bytes() == b"active"
            assert list(tmp_path.glob(".tmp_*.parquet.tmp"))
            with pytest.raises(Timeout):
                with FileLock(str(tmp_path / ".canonical.parquet.lock"), timeout=0):
                    pytest.fail("writer exclusion lost")
        finally:
            release.set()
        future.result(timeout=10)
    assert target.is_file() and not list(tmp_path.glob(".tmp_*.parquet.tmp"))
    assert foreign.exists() and chunks.exists()


@pytest.mark.parametrize("source", ["SSI_MCP", "VCI", "OTHER"])
@pytest.mark.parametrize("failure", ["batch-write", "tail-write", "read", "read-memory",
                                    "read-directory", "read-corrupt", "success", "empty"])
def test_fetch_symbols_owned_staging_cleanup(monkeypatch, tmp_path, source, failure):
    from pathlib import Path
    from types import SimpleNamespace
    from scripts import update_market_data as updater

    foreign = tmp_path / "omega_fetch_chunks_foreign"
    foreign.mkdir()
    foreign_shard = foreign / "chunk_0.parquet"
    foreign_shard.write_bytes(b"foreign active shard")
    canonical = tmp_path / "canonical.parquet"
    canonical.write_bytes(b"retained canonical")
    prior_artifacts = set(tmp_path.iterdir())
    allocated, writes, reads = [], [], []
    original_mkdtemp = updater.tempfile.mkdtemp
    original_write, original_read = pd.DataFrame.to_parquet, pd.read_parquet

    def allocate(*args, **kwargs):
        path = Path(original_mkdtemp(*args, **kwargs, dir=tmp_path))
        allocated.append(path)
        return str(path)

    def write(frame, path, **kwargs):
        writes.append(Path(path))
        if failure == "tail-write" or (failure == "batch-write" and len(writes) == 2):
            Path(path).write_bytes(b"partial parquet")
            raise OSError('injected parquet write failure')
        return original_write(frame, path, **kwargs)

    def read(path, **kwargs):
        reads.append(Path(path))
        if failure.startswith("read") and len(reads) == 2:
            if failure == "read-memory":
                raise MemoryError("injected parquet read failure")
            if failure == "read-directory":
                Path(path).unlink()
                Path(path).mkdir()
                (Path(path) / "invalid.parquet").write_bytes(b"corrupt parquet")
            elif failure == "read-corrupt":
                Path(path).write_bytes(b"corrupt parquet")
            else:
                raise OSError("injected parquet read failure")
        return original_read(path, **kwargs)

    frame = comparison_frame()
    monkeypatch.setattr(updater.tempfile, "mkdtemp", allocate)
    monkeypatch.setattr(updater, "BATCH_SIZE", 3 if failure == "tail-write" else 1)
    monkeypatch.setattr(updater.time, "sleep", lambda _: None)
    monkeypatch.setattr(updater, "fetch_one_symbol", lambda *a: frame.copy(deep=True))
    monkeypatch.setattr(pd.DataFrame, "to_parquet", write)
    monkeypatch.setattr(pd, "read_parquet", read)
    instance = SimpleNamespace(source=source, direct_vci=source == "VCI")
    symbols = [] if failure == "empty" else ["SSI", "VCB"]

    def fetch():
        return updater.fetch_symbols(instance, symbols, {s: "HOSE" for s in symbols},
                                     "2026-10-14", "2026-10-14")

    if failure in {"success", "empty"}:
        combined, stats = fetch()
        assert len(combined) == stats["rows"] == len(symbols)
    else:
        expected = MemoryError if failure == "read-memory" else (ValueError if failure in {"read-corrupt", "read-directory"} else OSError)
        with pytest.raises(expected):
            fetch()
        assert len(writes) == (1 if failure == "tail-write" else 2)
        assert len(reads) == (2 if failure.startswith("read") else 0)
    assert len(allocated) == 1 and not allocated[0].exists()
    assert set(tmp_path.iterdir()) == prior_artifacts
    assert foreign_shard.read_bytes() == b"foreign active shard"
    assert canonical.read_bytes() == b"retained canonical"


def test_native_tls_identity_config_and_snapshot_restore(monkeypatch, tmp_path):
    import os
    import ssl
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from urllib.parse import urlsplit
    import mcp
    import mcp.client.streamable_http as transport
    evidence = {}

    @asynccontextmanager
    async def stream(endpoint, **kwargs):
        async with kwargs["httpx_client_factory"]() as http:
            context = http._transport._pool._ssl_context
            evidence.update(hostname=urlsplit(endpoint).hostname,
                            check_hostname=context.check_hostname,
                            certificate_required=context.verify_mode == ssl.CERT_REQUIRED,
                            redirects=http.follow_redirects)
        yield None, None, None

    class Session:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def initialize(self):
            pass

        async def call_tool(self, *args):
            return SimpleNamespace(isError=False, structuredContent={"stocks": [row()]})

    snapshot = dict(os.environ)
    with monkeypatch.context() as scoped:
        scoped.setenv("SSI_MCP_TOKEN", "secret")
        scoped.setenv("OMEGA_UNRELATED", "preserved")
        scoped.setattr(transport, "streamablehttp_client", stream)
        scoped.setattr(mcp, "ClientSession", Session)
        frame = SSIMCPClient(clock=lambda: NOW).fetch_history("SSI", "2026-10-14", "2026-10-14")
        assert len(frame) == 1 and os.environ["OMEGA_UNRELATED"] == "preserved"
    assert dict(os.environ) == snapshot
    path = tmp_path / "tls_evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "hostname": "mcp.ssi.com.vn", "check_hostname": True,
        "certificate_required": True, "redirects": False}
