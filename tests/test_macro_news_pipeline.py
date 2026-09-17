from datetime import datetime, timezone
import multiprocessing
import os
import time
from tempfile import TemporaryDirectory
from pathlib import Path

import pandas as pd
import pytest

from omega.data.macro_news_pipeline import MacroNewsPipeline, RSSAdapter, SCHEMA, ScraperAdapter, V1_SCHEMA, VnstockNewsAdapter, _stop_provider_process, load_source_registry, load_universe_snapshot


RSS = b"""<rss><channel><item><title>Policy update</title><link>https://example.com/a</link><description>Details</description><pubDate>Tue, 12 Aug 2026 09:00:00 +0700</pubDate></item><item><title>Missing date</title><link>https://example.com/b</link></item></channel></rss>"""
HTML = b"""<article><a href='/report'>Macro report</a><time datetime='2026-08-12T09:00:00+07:00'>12/08/2026</time></article>"""
SETTINGS = {"allowed_hosts": ["example.com"], "display_name": "Example", "tier": "reputable_media", "source_delay_minutes": 15, "max_items": 200, "max_response_bytes": 5_000_000, "timeout_seconds": 15}


class Response:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield self.content


class Session:
    headers = {}

    def get(self, url, timeout):
        return Response(RSS if url.endswith("rss") else HTML)


def _blocked_provider():
    while True:
        time.sleep(1)


def test_adapters_require_published_at_and_normalize_to_utc():
    ingested_at = datetime(2026, 8, 12, 3, 0, tzinfo=timezone.utc)
    rss = RSSAdapter().parse("CafeF", "https://example.com/feed.rss", RSS, ingested_at)
    html = ScraperAdapter().parse("VCBS", "https://example.com/research", HTML, ingested_at)

    assert len(rss) == 1
    assert rss[0]["published_at"] == datetime(2026, 8, 12, 2, 0, tzinfo=timezone.utc)
    assert html[0]["available_at"] == datetime(2026, 8, 11, 17, 15, tzinfo=timezone.utc)


def test_pipeline_deduplicates_and_writes_pit_safe_parquet(tmp_path):
    pipeline = MacroNewsPipeline(Session(), {"cafef_macro": ("rss", "https://example.com/feed.rss"), "vcbs_research": ("html", "https://example.com/research")}, source_settings={"cafef_macro": SETTINGS, "vcbs_research": SETTINGS})
    output = tmp_path / "macro_news.parquet"

    result = pipeline.run(output)
    stored = pd.read_parquet(output)

    assert list(stored.columns) == SCHEMA
    assert len(result) == len(stored) == 2
    assert (pd.to_datetime(stored["available_at"], utc=True) >= pd.to_datetime(stored["published_at"], utc=True)).all()


def test_pipeline_filters_static_sources_to_pit_window():
    pipeline = MacroNewsPipeline(Session(), {"cafef_macro": ("rss", "https://example.com/feed.rss")}, source_settings={"cafef_macro": SETTINGS})

    result = pipeline.fetch(datetime(2026, 8, 12, 1, tzinfo=timezone.utc), datetime(2026, 8, 12, 2, 14, tzinfo=timezone.utc))

    assert result.empty


def test_universe_snapshot_rejects_session_state_and_preserves_byte_hash():
    raw = b'{"schema_version":1,"universe_id":"vci_hsx_hnx","universe_version":"20260812","generated_at":"2026-08-12T00:00:00Z","effective_from":"2026-08-12T00:00:00Z","effective_to":null,"members":[{"ticker":"AAA","exchange":"HSX"}]}'
    with TemporaryDirectory() as directory:
        universe = Path(directory) / "universe.json"
        universe.write_bytes(raw)
        snapshot = load_universe_snapshot(universe, datetime(2026, 8, 12, 1, tzinfo=timezone.utc))

    assert snapshot.members == (("AAA", "HSX"),)
    assert len(snapshot.universe_sha256) == 64


def test_universe_snapshot_rejects_naive_lifecycle_timestamp():
    with TemporaryDirectory() as directory:
        universe = Path(directory) / "universe.json"
        universe.write_text('{"schema_version":1,"universe_id":"vci_hsx_hnx","universe_version":"20260812","generated_at":"2026-08-12T00:00:00","effective_from":"2026-08-12T00:00:00Z","effective_to":null,"members":[{"ticker":"AAA","exchange":"HSX"}]}')

        with pytest.raises(ValueError, match="UTC-aware"):
            load_universe_snapshot(universe, datetime(2026, 8, 12, 1, tzinfo=timezone.utc))


def test_universe_snapshot_uses_prevalidated_bytes_after_path_replacement(tmp_path):
    as_of = datetime(2026, 8, 12, 1, tzinfo=timezone.utc)
    universe = tmp_path / "universe.json"
    universe.write_text('{"schema_version":1,"universe_id":"vci_hsx_hnx","universe_version":"20260812","generated_at":"2026-08-12T00:00:00Z","effective_from":"2026-08-12T00:00:00Z","effective_to":null,"members":[{"ticker":"AAA","exchange":"HSX"}]}')
    snapshot_bytes = universe.read_bytes()
    universe.write_text('{"schema_version":1,"universe_id":"vci_hsx_hnx","universe_version":"20260812","generated_at":"2026-08-12T00:00:00Z","effective_from":"2026-08-12T00:00:00Z","effective_to":null,"members":[{"ticker":"BBB","exchange":"HSX"}]}')

    assert load_universe_snapshot(snapshot_bytes, as_of).members == (("AAA", "HSX"),)


def test_vnstock_stops_pagination_at_cutoff(monkeypatch):
    calls = []
    universe = load_universe_snapshot(b'{"schema_version":1,"universe_id":"vci_hsx_hnx","universe_version":"20260812","generated_at":"2026-08-12T00:00:00Z","effective_from":"2026-08-12T00:00:00Z","effective_to":null,"members":[{"ticker":"AAA","exchange":"HSX"}]}', datetime(2026, 8, 12, 1, tzinfo=timezone.utc))
    adapter = VnstockNewsAdapter(universe)

    def fetch_page(ticker, cursor):
        calls.append(cursor)
        frame = pd.DataFrame([{"news_title": "Old", "public_date": "2026-08-11T00:00:00Z"}])
        frame.attrs["pagination"] = {"next_cursor": "page2"}
        return frame

    monkeypatch.setattr(adapter, "_fetch_page", fetch_page)

    assert adapter.fetch(datetime(2026, 8, 12, tzinfo=timezone.utc), datetime(2026, 8, 12, 1, tzinfo=timezone.utc), datetime(2026, 8, 12, 1, tzinfo=timezone.utc))[0] == []
    assert calls == [None]


def test_vnstock_timeout_terminates_blocked_provider_process():
    process = multiprocessing.get_context().Process(target=_blocked_provider)
    started = time.monotonic()
    process.start()
    _stop_provider_process(process)

    assert time.monotonic() - started < 0.5
    assert not process.is_alive()


def test_vnstock_fetch_timeout_terminates_provider_process(monkeypatch):
    universe = load_universe_snapshot(b'{"schema_version":1,"universe_id":"vci_hsx_hnx","universe_version":"20260812","generated_at":"2026-08-12T00:00:00Z","effective_from":"2026-08-12T00:00:00Z","effective_to":null,"members":[{"ticker":"AAA","exchange":"HSX"}]}', datetime(2026, 8, 12, 1, tzinfo=timezone.utc))

    class BlockedProcess:
        daemon = False
        started = False
        terminated = False

        def start(self): self.started = True
        def is_alive(self): return self.started and not self.terminated
        def terminate(self): self.terminated = True
        def kill(self): self.terminated = True
        def join(self, timeout=None): pass

    process = BlockedProcess()

    class Context:
        Pipe = staticmethod(multiprocessing.get_context().Pipe)

        def Process(self, **_): return process

    context = Context()
    monkeypatch.setattr("omega.data.macro_news_pipeline.multiprocessing.get_context", lambda: context)

    with pytest.raises(TimeoutError, match="vnstock request exceeds timeout"):
        VnstockNewsAdapter(universe, timeout_seconds=0.001)._fetch_page("AAA", None)

    assert process.daemon and process.terminated and not process.is_alive()


def test_vnstock_broken_pipe_terminates_provider_process(monkeypatch):
    universe = load_universe_snapshot(b'{"schema_version":1,"universe_id":"vci_hsx_hnx","universe_version":"20260812","generated_at":"2026-08-12T00:00:00Z","effective_from":"2026-08-12T00:00:00Z","effective_to":null,"members":[{"ticker":"AAA","exchange":"HSX"}]}', datetime(2026, 8, 12, 1, tzinfo=timezone.utc))

    class BrokenParent:
        closed = False

        def poll(self, timeout): raise BrokenPipeError
        def close(self): self.closed = True

    class Child:
        def close(self): pass

    class Process:
        daemon = False
        started = False
        terminated = False

        def start(self): self.started = True
        def is_alive(self): return self.started and not self.terminated
        def terminate(self): self.terminated = True
        def kill(self): self.terminated = True
        def join(self, timeout=None): pass

    parent, process = BrokenParent(), Process()

    class Context:
        Pipe = staticmethod(lambda duplex=False: (parent, Child()))

        def Process(self, **_): return process

    monkeypatch.setattr("omega.data.macro_news_pipeline.multiprocessing.get_context", lambda: Context())

    with pytest.raises(TimeoutError, match="vnstock request exceeds timeout"):
        VnstockNewsAdapter(universe)._fetch_page("AAA", None)

    assert parent.closed and process.daemon and process.terminated and not process.is_alive()


def test_v1_migration_preserves_legacy_available_at(tmp_path):
    output = tmp_path / "macro_news.parquet"
    legacy_available_at = datetime(2026, 8, 12, 1, 5, tzinfo=timezone.utc)
    pd.DataFrame([["CafeF", "Title", "Summary", "https://example.com/a", datetime(2026, 8, 12, 1, tzinfo=timezone.utc), legacy_available_at, datetime(2026, 8, 12, 3, tzinfo=timezone.utc)]], columns=V1_SCHEMA).to_parquet(output, index=False)

    stored = MacroNewsPipeline.persist(pd.DataFrame(columns=SCHEMA), output)

    assert pd.to_datetime(stored.loc[0, "available_at"], utc=True) == pd.Timestamp(legacy_available_at)


def test_source_delay_preserves_historical_static_availability():
    ingested_at = datetime(2026, 8, 12, 3, tzinfo=timezone.utc)
    record = RSSAdapter().parse("CafeF", "https://example.com/feed.rss", RSS, ingested_at)[0]

    assert record["available_at"] == datetime(2026, 8, 12, 2, 15, tzinfo=timezone.utc)


def test_static_source_honors_registry_max_items_and_allowlist():
    pipeline = MacroNewsPipeline(Session(), {"cafef_macro": ("rss", "https://example.com/feed.rss")}, source_settings={"cafef_macro": {**SETTINGS, "max_items": 0, "max_response_bytes": len(RSS)}})

    assert pipeline.fetch().empty


def test_vcbs_detail_enrichment_binds_body_to_revision():
    from omega.data.macro_news_pipeline import VCBSAdapter

    record = VCBSAdapter().parse("vcbs_research", "https://www.vcbs.com.vn/research", HTML, datetime(2026, 8, 12, 3, tzinfo=timezone.utc))[0]
    original = record["revision_id"]
    enriched = VCBSAdapter.enrich(record, b"<html><body>Detailed macro report</body></html>", "text/html")

    assert enriched["body_text"] == "Detailed macro report" and enriched["revision_id"] != original


def test_registry_rejects_private_and_invalid_controls(tmp_path):
    registry = [{"source_id":"bad","display_name":"Bad","tier":"official","kind":"rss","enabled":True,"required":False,"discovery_url":"http://127.0.0.1/feed","allowed_hosts":["127.0.0.1"],"adapter":"rss","source_delay_minutes":-1,"timestamp_policy":"utc","max_pages":0,"max_items":0,"request_interval_seconds":-1,"timeout_seconds":0,"max_response_bytes":0,"allow_pdf":False,"allow_browser_fallback":False,"disabled_reason":None}]
    path = tmp_path / "sources.json"
    path.write_text(__import__("json").dumps(registry))

    with pytest.raises(ValueError):
        load_source_registry(path)


def test_checked_in_registry_accepts_vnstock_without_discovery_url(monkeypatch):
    monkeypatch.setattr("omega.data.macro_news_pipeline._public_host", lambda host: True)
    registry = load_source_registry(Path("config/macro_news_sources.json"))

    assert next(entry for entry in registry if entry["source_id"] == "vnstock_vci")["discovery_url"] is None


def test_validation_rejects_invalid_schema_and_vnstock_bindings():
    record = RSSAdapter().parse("cafef_macro", "https://example.com/feed.rss", RSS, datetime(2026, 8, 12, 3, tzinfo=timezone.utc))[0]
    record["schema_version"] = 1

    with pytest.raises(ValueError):
        MacroNewsPipeline._frame([record])


@pytest.mark.parametrize("field", ["content_hash", "article_id", "revision_id", "provenance_id", "raw_record_id"])
def test_validation_recomputes_identity_bindings(field):
    record = RSSAdapter().parse("cafef_macro", "https://example.com/feed.rss", RSS, datetime(2026, 8, 12, 3, tzinfo=timezone.utc))[0]
    record[field] = "0" * 64

    with pytest.raises(ValueError, match="identity bindings"):
        MacroNewsPipeline._frame([record])


def test_persist_revalidates_parquet_identity_bindings(tmp_path):
    output = tmp_path / "macro_news.parquet"
    incoming = MacroNewsPipeline._frame(RSSAdapter().parse("cafef_macro", "https://example.com/feed.rss", RSS, datetime(2026, 8, 12, 3, tzinfo=timezone.utc)))

    MacroNewsPipeline.persist(incoming, output)
    assert len(MacroNewsPipeline.persist(pd.DataFrame(columns=SCHEMA), output)) == 1
