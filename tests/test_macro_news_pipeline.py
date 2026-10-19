from datetime import datetime, timedelta, timezone
import multiprocessing
import os
import time
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
import sys

import pandas as pd
import pyarrow.parquet as pq
import pytest

from omega.data.macro_news_pipeline import MacroNewsPipeline, RSSAdapter, SCHEMA, ScraperAdapter, V1_SCHEMA, VnstockNewsAdapter, _stop_provider_process, _vnstock_news_worker, load_source_registry, load_universe_snapshot


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


def test_vnstock_error_does_not_expose_provider_credentials(monkeypatch):
    universe = load_universe_snapshot(b'{"schema_version":1,"universe_id":"vci_hsx_hnx","universe_version":"20260812","generated_at":"2026-08-12T00:00:00Z","effective_from":"2026-08-12T00:00:00Z","effective_to":null,"members":[{"ticker":"AAA","exchange":"HSX"}]}', datetime(2026, 8, 12, 1, tzinfo=timezone.utc))

    def fail(*_):
        raise RuntimeError("Authorization: Bearer SECRET")

    monkeypatch.setattr(VnstockNewsAdapter, "_fetch_page", fail)
    _, errors = VnstockNewsAdapter(universe).fetch(datetime(2026, 8, 12, tzinfo=timezone.utc), datetime(2026, 8, 12, 1, tzinfo=timezone.utc), datetime(2026, 8, 12, 1, tzinfo=timezone.utc))
    assert errors == ["AAA: RuntimeError"]


def test_v1_migration_preserves_legacy_available_at(tmp_path):
    output = tmp_path / "macro_news.parquet"
    legacy_available_at = datetime(2026, 8, 12, 1, 5, tzinfo=timezone.utc)
    pd.DataFrame([["CafeF", "Title", "Summary", "https://example.com/a", datetime(2026, 8, 12, 1, tzinfo=timezone.utc), legacy_available_at, datetime(2026, 8, 12, 3, tzinfo=timezone.utc)]], columns=V1_SCHEMA).to_parquet(output, index=False)

    MacroNewsPipeline.persist(pd.DataFrame(columns=SCHEMA), output)
    stored = pd.read_parquet(output)

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
    assert len(pd.read_parquet(output)) == 1


def test_cli_resumes_raw_backlog_across_two_runs(tmp_path, monkeypatch):
    from scripts import run_macro_news_pipeline as cli
    from omega.data import macro_news_llm, macro_news_pipeline

    as_of = datetime(2026, 9, 25, tzinfo=timezone.utc)
    universe = tmp_path / "universe.json"
    universe.write_text('{"schema_version":1,"universe_id":"vci_hsx_hnx","universe_version":"20260925","generated_at":"2026-09-24T00:00:00Z","effective_from":"2026-09-24T00:00:00Z","effective_to":null,"members":[{"ticker":"AAA","exchange":"HSX"}]}')
    records = []
    for index in range(101):
        records.extend(RSSAdapter().parse("cafef_macro", "https://example.com/feed.rss", f"<rss><channel><item><title>Article {index}</title><link>https://example.com/{index}</link><pubDate>Thu, 24 Sep 2026 09:00:00 +0700</pubDate></item></channel></rss>".encode(), as_of))
    incoming = MacroNewsPipeline._frame(records)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli, "_args", lambda: SimpleNamespace(vnstock_universe=universe, as_of=as_of, hours_back=48, sources_config=Path("sources.json"), max_articles=1000, raw_output=Path("raw.parquet"), llm_output=Path("llm.parquet"), llm_links_output=Path("links.parquet"), ingest_only=False, session_dir=Path("session")))
    monkeypatch.setattr(cli, "_validate_universe_before_import", lambda *_: universe.read_bytes())
    monkeypatch.setattr(macro_news_pipeline, "load_source_registry", lambda *_: [{"source_id": "vnstock_vci", "enabled": True, "kind": "vnstock", "required": False, "max_items": 1000, "request_interval_seconds": 0, "timeout_seconds": 1, "max_response_bytes": 1000, "source_delay_minutes": 0}])
    monkeypatch.setattr(macro_news_pipeline.VnstockNewsAdapter, "fetch", lambda *_: ([], []))
    monkeypatch.setattr(macro_news_pipeline.MacroNewsPipeline, "fetch", lambda *_: incoming)
    monkeypatch.setattr("omega.core.llm_config.resolve_alpha_llm_config", lambda *_: {})
    monkeypatch.setattr("omega.core.llm_config.sanitize_llm_config", lambda *_: {})
    seen = []

    def extract(self, batch, output, links, as_of=None):
        seen.append(batch["raw_record_id"].tolist())
        previous = pd.read_parquet(output) if output.exists() else pd.DataFrame(columns=["news_id"])
        pd.concat([previous, batch["raw_record_id"].rename("news_id").to_frame()], ignore_index=True).to_parquet(output, index=False)

    monkeypatch.setattr(macro_news_llm.MacroNewsLLMExtractor, "extract", extract)
    assert cli.main() == 0
    assert cli.main() == 0
    assert [len(batch) for batch in seen] == [100, 1]
    assert len(set(seen[0] + seen[1])) == 101


def test_provider_cap_rejects_before_ipc(monkeypatch):
    class Connection:
        sent = None
        closed = False

        def send(self, value): self.sent = value
        def close(self): self.closed = True

    monkeypatch.setitem(sys.modules, "vnstock", SimpleNamespace(Company=lambda **_: SimpleNamespace(news=lambda: pd.DataFrame({"news_title": ["x" * 1000]}))))
    connection = Connection()
    _vnstock_news_worker(connection, "AAA", 100)
    assert connection.sent == (False, "ValueError") and connection.closed


def test_persist_rollback_on_corrupt_history(tmp_path):
    output = tmp_path / "raw.parquet"
    record = RSSAdapter().parse("cafef_macro", "https://example.com/feed.rss", RSS, datetime(2026, 8, 12, 3, tzinfo=timezone.utc))[0]
    incoming = MacroNewsPipeline._frame([record])
    MacroNewsPipeline.persist(incoming, output)
    corrupt = incoming.copy()
    corrupt.loc[0, "content_hash"] = "0" * 64
    corrupt.to_parquet(output, index=False)
    original = output.read_bytes()
    with pytest.raises(ValueError, match="identity bindings"):
        MacroNewsPipeline.persist(incoming, output)
    assert output.read_bytes() == original


def test_persist_returns_only_incoming_after_256_and_deduplicates(tmp_path):
    output = tmp_path / "raw.parquet"
    ingested = datetime(2026, 8, 12, 3, tzinfo=timezone.utc)
    records = [RSSAdapter().parse("cafef_macro", "https://example.com/feed.rss", f"<rss><channel><item><title>Article {i}</title><link>https://example.com/{i}</link><pubDate>Tue, 12 Aug 2026 09:00:00 +0700</pubDate></item></channel></rss>", ingested)[0] for i in range(257)]
    original = MacroNewsPipeline._frame(records[:256])
    MacroNewsPipeline.persist(original, output)

    result = MacroNewsPipeline.persist(MacroNewsPipeline._frame(records[255:]), output)

    assert len(result) == 2
    assert pq.ParquetFile(output).metadata.num_rows == 257
    assert set(pd.read_parquet(output, columns=["raw_record_id"])["raw_record_id"]) == {record["raw_record_id"] for record in records}


from omega.data.macro_news_pipeline import CafeFHistoricalCrawler, parse_cafef_timestamp


CAFEF_ARTICLE = "https://cafef.vn/story-188150101153000123.chn"
CAFEF_FETCHED = datetime(2026, 10, 18, 16, 43, 57, tzinfo=timezone.utc)


def test_cafef_url_ict_exact_timestamp_and_close_boundary():
    assert parse_cafef_timestamp(CAFEF_ARTICLE) == datetime(2015, 1, 1, 8, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("url", [
    None, "", "https://cafef.vn/x-188150230153000123.chn",
    "https://cafef.vn/x-18815010115300012.chn", "https://cafef.vn/x-20150101153000123.chn",
    "https://secret:password@cafef.vn/x-188150101153000123.chn",
    "https://127.0.0.1/x-188150101153000123.chn", "https://2130706433/x-188150101153000123.chn",
    "https://[::ffff:127.0.0.1]/x-188150101153000123.chn",
    "https://cafef.vn.evil.test/x-188150101153000123.chn",
])
def test_cafef_timestamp_rejects_malformed_or_untrusted_url(url):
    with pytest.raises(ValueError) as error:
        parse_cafef_timestamp(url)
    assert "secret" not in str(error.value) and "password" not in str(error.value)


@pytest.mark.parametrize("kwargs", [
    {"max_pages": v} for v in (None, False, 0, -1, 1.5, 10**13, float("nan"))
] + [{"timeout": v} for v in (None, True, 0, -1, float("nan"), float("inf"), -float("inf"), 10**13)])
def test_cafef_controls_fail_before_network(kwargs):
    with pytest.raises(ValueError):
        CafeFHistoricalCrawler(**kwargs)


def _cafef_fake(monkeypatch, listings, *, max_pages=500):
    crawler = CafeFHistoricalCrawler(max_pages=max_pages, sleeper=lambda _: None, clock=lambda: CAFEF_FETCHED)
    calls = []

    def request(url):
        calls.append(url)
        return b"<h1>Tang truong</h1>" if url == CAFEF_ARTICLE else listings[len([c for c in calls if 'tim-kiem' in c]) - 1]

    monkeypatch.setattr(crawler, "_request", request)
    return crawler, calls


def test_cafef_pagination_overlap_and_research_only_availability(monkeypatch):
    first = f'<a href="{CAFEF_ARTICLE}">Story</a><a rel="next" href="/tim-kiem.chn?keywords=AAA&amp;page=2">Next</a>'.encode()
    second = f'<a href="{CAFEF_ARTICLE}">Overlap</a>'.encode()
    crawler, calls = _cafef_fake(monkeypatch, [first, second])
    published = parse_cafef_timestamp(CAFEF_ARTICLE)
    pages = list(crawler.crawl_symbol("AAA", "HSX", published, published))
    assert list(map(len, pages)) == [1, 0]
    record = pages[0][0]
    MacroNewsPipeline._frame([record])
    assert record["available_at"] == record["ingested_at"] == CAFEF_FETCHED
    assert record["published_at"] == published
    assert record["origin_ticker"] == "AAA"
    assert len(calls) == 3


def test_cafef_shared_story_preserves_symbol_provenance(monkeypatch):
    page = f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()
    crawler, _ = _cafef_fake(monkeypatch, [page, page])
    lower = datetime(2015, 1, 1, tzinfo=timezone.utc)
    a = list(crawler.crawl_symbol("AAA", "HSX", lower, CAFEF_FETCHED))[0][0]
    b = list(crawler.crawl_symbol("BBB", "HSX", lower, CAFEF_FETCHED))[0][0]
    assert a["article_id"] == b["article_id"]
    assert a["raw_record_id"] != b["raw_record_id"]


@pytest.mark.parametrize("mode", ["repeat", "cap", "malformed", "foreign_next"])
def test_cafef_incomplete_listings_fail_closed(monkeypatch, mode):
    page = f'<a href="{CAFEF_ARTICLE}">Story</a><a rel="next" href="/tim-kiem.chn?keywords=AAA&amp;page=2">Next</a>'.encode()
    if mode == "malformed":
        page = b"<html>blocked or changed layout</html>"
    if mode == "foreign_next":
        page = b'<a rel="next" href="https://secret:password@evil.test/">Next</a>'
    crawler, _ = _cafef_fake(monkeypatch, [page, page], max_pages=1 if mode == "cap" else 500)
    with pytest.raises(ValueError) as error:
        list(crawler.crawl_symbol("AAA", "HSX", datetime(2015, 1, 1, tzinfo=timezone.utc), CAFEF_FETCHED))
    assert "secret" not in str(error.value) and "password" not in str(error.value)


@pytest.mark.parametrize("address", ["127.0.0.1", "0.0.0.0", "192.0.2.1", "100.64.0.1", "169.254.1.1", "::1", "::ffff:8.8.8.8", "64:ff9b::808:808", "2002:0808:0808::1"])
def test_cafef_dns_special_use_and_embedded_ipv4_denied(address):
    assert not CafeFHistoricalCrawler._public_address(address)


def test_cafef_dns_rebinding_denied_before_connection(monkeypatch):
    monkeypatch.setattr("omega.data.macro_news_pipeline.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    monkeypatch.setattr("omega.data.macro_news_pipeline._CafeFConnection", lambda *a: pytest.fail("must not connect"))
    with pytest.raises(ValueError, match="DNS policy"):
        CafeFHistoricalCrawler(sleeper=lambda _: None)._request("https://cafef.vn/tim-kiem.chn?keywords=AAA")


def test_cafef_tls_pinning_retains_original_sni(monkeypatch):
    from omega.data.macro_news_pipeline import _CafeFConnection
    seen = {}
    raw = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr("omega.data.macro_news_pipeline.socket.create_connection", lambda address, timeout: seen.update(address=address) or raw)
    connection = _CafeFConnection("cafef.vn", "8.8.8.8", 15)
    connection._context = SimpleNamespace(wrap_socket=lambda sock, server_hostname: seen.update(sni=server_hostname) or sock)
    connection.connect()
    assert seen == {"address": ("8.8.8.8", 443), "sni": "cafef.vn"}


@pytest.mark.parametrize("status", [302, 403, 429, 503])
def test_cafef_http_failures_close_connections_and_exhaust(monkeypatch, status):
    closes, calls = [], []
    class Connection:
        def request(self, *a, **k): calls.append(1)
        def getresponse(self): return SimpleNamespace(status=status)
        def close(self): closes.append(1)
    monkeypatch.setattr("omega.data.macro_news_pipeline.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))])
    monkeypatch.setattr("omega.data.macro_news_pipeline._CafeFConnection", lambda *a: Connection())
    with pytest.raises(ValueError):
        CafeFHistoricalCrawler(sleeper=lambda _: None)._request("https://cafef.vn/tim-kiem.chn?keywords=AAA")
    assert len(closes) == len(calls) == (3 if status in {429, 503} else 1)


@pytest.mark.parametrize("field,value", [("available_at", datetime(2015, 1, 1, 8, 30, tzinfo=timezone.utc)), ("origin_ticker", None), ("origin_exchange", "UPCOM"), ("universe_id", "unverified"), ("published_at", CAFEF_FETCHED)])
def test_cafef_unverified_provenance_cannot_inherit_pit(monkeypatch, field, value):
    crawler, _ = _cafef_fake(monkeypatch, [f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()])
    record = list(crawler.crawl_symbol("AAA", "HSX", datetime(2015, 1, 1, tzinfo=timezone.utc), CAFEF_FETCHED))[0][0]
    record[field] = value
    with pytest.raises(ValueError):
        MacroNewsPipeline._frame([record])


@pytest.mark.parametrize("fault", ["write", "replace"])
def test_cafef_persist_fault_keeps_prior_store(tmp_path, monkeypatch, fault):
    import omega.data.macro_news_pipeline as module
    crawler, _ = _cafef_fake(monkeypatch, [f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()])
    records = list(crawler.crawl_symbol("AAA", "HSX", datetime(2015, 1, 1, tzinfo=timezone.utc), CAFEF_FETCHED))[0]
    frame = MacroNewsPipeline._frame(records)
    output = tmp_path / "research.parquet"
    MacroNewsPipeline.persist(frame, output)
    original = output.read_bytes()
    def fail(*args, **kwargs): raise OSError("injected durability failure")
    monkeypatch.setattr(module.os if fault == "replace" else module.pq, "replace" if fault == "replace" else "ParquetWriter", fail)
    with pytest.raises(OSError):
        MacroNewsPipeline.persist(frame, output)
    assert output.read_bytes() == original
    assert not output.with_name(output.name + ".lock").exists()


@pytest.mark.parametrize("fault", ["bytes", "type", "timeout", "utf8", "title"])
def test_cafef_response_and_detail_faults_fail_closed(monkeypatch, fault):
    if fault in {"utf8", "title"}:
        crawler = CafeFHistoricalCrawler(sleeper=lambda _: None, clock=lambda: CAFEF_FETCHED)
        monkeypatch.setattr(crawler, "_request", lambda url: f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode() if "tim-kiem" in url else (b"\xff" if fault == "utf8" else b"<html>no title</html>"))
        with pytest.raises((ValueError, UnicodeError)):
            list(crawler.crawl_symbol("AAA", "HSX", datetime(2015, 1, 1, tzinfo=timezone.utc), CAFEF_FETCHED))
        return
    counts = []
    class Connection:
        def request(self, *a, **k):
            if fault == "timeout": raise TimeoutError("https://secret:password@cafef.vn/?token=SECRET")
        def getresponse(self): return SimpleNamespace(status=200, getheader=lambda _: "text/plain" if fault == "type" else "text/html", read=lambda n: b"x" * n)
        def close(self): counts.append(1)
    monkeypatch.setattr("omega.data.macro_news_pipeline.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))])
    monkeypatch.setattr("omega.data.macro_news_pipeline._CafeFConnection", lambda *a: Connection())
    with pytest.raises(ValueError) as error:
        CafeFHistoricalCrawler(sleeper=lambda _: None, max_bytes=10)._request("https://cafef.vn/tim-kiem.chn?keywords=AAA")
    assert len(counts) == (3 if fault == "timeout" else 1)
    assert all(secret not in str(error.value) for secret in ("password", "token", "SECRET"))


def _historical_cli_fixture(tmp_path, monkeypatch):
    import json
    from scripts import fetch_news_sentiment as cli
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    manifest = {"schema_version": 1, "universe_id": "collection", "universe_version": "20261018", "generated_at": "2026-10-18T16:00:00Z", "effective_from": "2015-01-01T00:00:00Z", "effective_to": None, "members": [{"ticker": "AAA", "exchange": "HSX"}]}
    (tmp_path / "universe.json").write_text(json.dumps(manifest), encoding="utf-8")
    return cli


def test_cafef_historical_cli_projection_manifest_and_collision(tmp_path, monkeypatch):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    crawler, _ = _cafef_fake(monkeypatch, [f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()])
    manifest = cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=crawler)
    assert manifest["status"] == "results_only"
    assert not manifest["pit_verified"] and not manifest["full_history_verified"]
    root = tmp_path / "data/historical_news/run"
    assert (root / "manifest.json").is_file()
    stored = pd.read_parquet(root / "AAA-HSX-0001-v10.parquet")
    assert stored.loc[0, "available_at"] >= stored.loc[0, "fetched_at"]
    with pytest.raises(ValueError):
        cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=crawler)


@pytest.mark.parametrize("fault", ["crawl", "write", "fsync", "replace", "identity"])
def test_cafef_historical_cli_faults_never_publish_success(tmp_path, monkeypatch, fault):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    crawler, _ = _cafef_fake(monkeypatch, [f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()])
    def fail(*a, **k): raise OSError("https://secret:password@cafef.vn/?token=SECRET")
    if fault == "crawl":
        monkeypatch.setattr(crawler, "crawl_symbol", fail)
    elif fault == "write":
        monkeypatch.setattr(cli.pq, "write_table", fail)
    elif fault in {"fsync", "replace"}:
        monkeypatch.setattr(cli.os, fault, fail)
    elif fault == "identity":
        crawl = crawler.crawl_symbol
        def tampered(*args):
            for records in crawl(*args):
                records[0]["content_hash"] = "0" * 64
                yield records
        monkeypatch.setattr(crawler, "crawl_symbol", tampered)
    if fault in {"fsync", "replace"}:
        with pytest.raises(OSError):
            cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=crawler)
        assert not (tmp_path / "data/historical_news/run/manifest.json").exists()
    else:
        result = cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=crawler)
        assert result["status"] == "failed"
        assert all(secret not in str(result) for secret in ("password", "token=", "SECRET"))


@pytest.mark.parametrize("path", ["../escape", "data/news_sentiment_2015_now.parquet", "/absolute", "data/historical_news"])
def test_cafef_historical_cli_rejects_paths_before_mutation(tmp_path, monkeypatch, path):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, path)
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("offset,expected", [(-1, 0), (0, 1), (1, 1)])
def test_cafef_cutoff_adjacent_microseconds(monkeypatch, offset, expected):
    crawler, _ = _cafef_fake(monkeypatch, [f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()])
    publication = parse_cafef_timestamp(CAFEF_ARTICLE)
    pages = list(crawler.crawl_symbol("AAA", "HSX", publication - timedelta(days=1), publication + timedelta(microseconds=offset)))
    assert sum(map(len, pages)) == expected


def test_cafef_old_pinned_story_never_ends_pagination(monkeypatch):
    old = "https://cafef.vn/old-188140101153000123.chn"
    listing = f'<a href="{old}">Pinned</a><a rel="next" href="/tim-kiem.chn?keywords=AAA&amp;page=2">Next</a>'.encode()
    crawler, _ = _cafef_fake(monkeypatch, [listing, f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()])
    pages = list(crawler.crawl_symbol("AAA", "HSX", datetime(2015, 1, 1, tzinfo=timezone.utc), CAFEF_FETCHED))
    assert list(map(len, pages)) == [0, 1]


def test_cafef_cli_exit_nonzero_for_failed_collection(tmp_path, monkeypatch):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "build_historical_news_sentiment", lambda *a: {"status": "failed"})
    monkeypatch.setattr(sys, "argv", ["fetch_news_sentiment", "--historical", "--universe", "universe.json", "--start", "2015-01-01", "--end", "2026-10-18", "--as-of", CAFEF_FETCHED.isoformat(), "--output", "data/historical_news/run"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1


def test_vnstock_keeps_bounded_top_items_across_universe(monkeypatch):
    import json

    payload = {"schema_version": 1, "universe_id": "vci", "universe_version": "1", "generated_at": "2026-08-12T00:00:00Z", "effective_from": "2026-08-12T00:00:00Z", "effective_to": None, "members": [{"ticker": f"A{i:02d}", "exchange": "HSX"} for i in range(60)]}
    universe = load_universe_snapshot(json.dumps(payload).encode(), datetime(2026, 8, 13, tzinfo=timezone.utc))
    adapter = VnstockNewsAdapter(universe, max_items=3)
    monkeypatch.setattr(adapter, "_fetch_page", lambda ticker, _: pd.DataFrame([{"news_title": ticker, "public_date": f"2026-08-12T{int(ticker[1:]) % 24:02d}:00:00Z", "id": ticker}]))
    monkeypatch.setitem(sys.modules, "vnstock", SimpleNamespace())

    records, errors = adapter.fetch(datetime(2026, 8, 12, tzinfo=timezone.utc), datetime(2026, 8, 13, tzinfo=timezone.utc), datetime(2026, 8, 13, tzinfo=timezone.utc))

    assert errors == []
    assert len(records) == 3
    assert [record["published_at"].hour for record in records] == [23, 23, 22]


@pytest.fixture
def committed_historical_run(tmp_path, monkeypatch):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    crawler, _ = _cafef_fake(monkeypatch, [f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()])
    manifest = cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=crawler)
    return cli, tmp_path / "data/historical_news/run", manifest


@pytest.mark.parametrize("mutation", ["title", "schema", "rows", "truncated"])
def test_historical_semantic_readback_before_durability(tmp_path, monkeypatch, mutation):
    import pyarrow as pa
    from scripts import fetch_news_sentiment as cli

    table = pa.table({"title": ["Expected"]})
    write = cli.pq.write_table
    def corrupt(value, stream):
        if mutation == "truncated":
            stream.write(b"PAR1broken")
            return
        damaged = {"title": pa.table({"title": ["Altered"]}), "schema": pa.table({"other": ["Expected"]}), "rows": table.slice(0, 0)}[mutation]
        write(damaged, stream)
    monkeypatch.setattr(cli.pq, "write_table", corrupt)
    synced = []
    monkeypatch.setattr(cli.os, "fsync", lambda *args: synced.append(True))
    shards = []
    with pytest.raises((ValueError, OSError)):
        cli._write_historical_shard(table, tmp_path / "shard.parquet", shards)
    assert shards[0]["durable"] is False and shards[0]["sha256"] is None
    assert synced == []


def test_historical_resume_committed_run_without_network(committed_historical_run, monkeypatch):
    cli, root, manifest = committed_historical_run
    (root / "manifest.json.tmp").write_text("interrupted newer publication", encoding="utf-8")
    (root / "orphan.parquet").write_bytes(b"uncommitted")
    class NoNetwork:
        def crawl_symbol(self, *args):
            raise AssertionError("resume must not fetch")
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    assert cli.read_historical_manifest("data/historical_news/run") == manifest
    recovered = cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=NoNetwork(), resume=True)
    assert recovered == manifest
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before


@pytest.mark.parametrize("mutation", ["digest", "missing", "pair", "traversal", "duplicate", "rows", "durable", "status", "purpose", "pit", "full_history", "members", "outcome", "extra"])
def test_historical_recovery_rejects_corrupt_commit(committed_historical_run, mutation):
    import json
    cli, root, manifest = committed_historical_run
    shard = manifest["shards"][0]
    if mutation == "digest":
        (root / shard["path"]).write_bytes(b"corrupt")
    elif mutation == "missing":
        (root / shard["path"]).unlink()
    elif mutation == "pair":
        manifest["shards"].pop()
        manifest["shard_count"] -= 1
    elif mutation == "traversal":
        shard["path"] = "../outside.parquet"
    elif mutation == "duplicate":
        manifest["shards"].append(dict(shard))
        manifest["shard_count"] += 1
    elif mutation == "rows":
        shard["rows"] += 1
    elif mutation == "durable":
        shard["durable"] = False
    elif mutation == "status":
        manifest["status"] = "failed"
    elif mutation == "purpose":
        manifest["purpose"] = "investability"
    elif mutation == "pit":
        manifest["pit_verified"] = True
    elif mutation == "full_history":
        manifest["full_history_verified"] = True
    elif mutation == "members":
        manifest["members"] = []
    elif mutation == "outcome":
        manifest["symbols"][0]["rows"] += 1
    elif mutation == "extra":
        extra = dict(shard, path="BBB-HSX-0001-raw.parquet")
        (root / extra["path"]).write_bytes((root / shard["path"]).read_bytes())
        manifest["shards"].append(extra)
        manifest["shard_count"] += 1
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    before = (root / "manifest.json").read_bytes()
    with pytest.raises((ValueError, OSError)):
        cli.read_historical_manifest("data/historical_news/run")
    assert (root / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf"), 10**13, -1.0])
def test_historical_recovery_revalidates_projection_not_just_hash(committed_historical_run, value):
    import hashlib
    import json
    import pyarrow as pa
    cli, root, manifest = committed_historical_run
    entry = manifest["shards"][1]
    path = root / entry["path"]
    table = pq.read_table(path)
    table = table.set_column(table.schema.get_field_index("sentiment_score"), "sentiment_score", pa.array([value], type=pa.float64()))
    pq.write_table(table, path)
    entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        cli.read_historical_manifest("data/historical_news/run")


@pytest.mark.parametrize("field", ["universe", "start", "end", "as_of", "lexicon"])
def test_historical_resume_binds_configuration(committed_historical_run, field, monkeypatch):
    import json
    cli, root, manifest = committed_historical_run
    start, end, as_of = "2015-01-01", "2026-10-18", CAFEF_FETCHED
    if field == "universe":
        path = root.parents[2] / "universe.json"
        data = json.loads(path.read_text())
        data["universe_version"] = "changed"
        path.write_text(json.dumps(data), encoding="utf-8")
    elif field == "start": start = "2015-01-02"
    elif field == "end": end = "2026-10-17"
    elif field == "as_of": as_of += timedelta(seconds=1)
    elif field == "lexicon": monkeypatch.setattr(cli, "BULLISH_KEYWORDS", ["different"])
    with pytest.raises(ValueError):
        cli.build_historical_news_sentiment("universe.json", start, end, as_of, "data/historical_news/run", resume=True)


@pytest.mark.parametrize("crash", ["raw", "projection", "manifest_write", "manifest_replace"])
def test_historical_precommit_crash_never_adopts_shards(tmp_path, monkeypatch, crash):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    crawler, _ = _cafef_fake(monkeypatch, [f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()])
    class Crash(BaseException): pass
    write = cli._write_historical_shard
    def interrupted(table, path, shards):
        write(table, path, shards)
        if path.name.endswith("-raw.parquet" if crash == "raw" else "-v10.parquet"):
            raise Crash()
    with monkeypatch.context() as patch:
        if crash in {"raw", "projection"}:
            patch.setattr(cli, "_write_historical_shard", interrupted)
        elif crash == "manifest_write":
            patch.setattr(cli.json, "dump", lambda *a, **k: (_ for _ in ()).throw(Crash()))
        else:
            patch.setattr(cli.Path, "replace", lambda *a, **k: (_ for _ in ()).throw(Crash()))
        with pytest.raises(Crash):
            cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=crawler)
    root = tmp_path / "data/historical_news/run"
    assert not (root / "manifest.json").exists()
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    if crash in {"raw", "projection"}:
        class Refetch:
            def crawl_symbol(self, *args):
                yield []
        recovered = cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=Refetch(), resume=True)
        assert recovered["symbols"][0]["rows"] == 0  # Orphan article was not adopted.
        assert recovered["status"] == "incomplete"
    else:
        with pytest.raises((ValueError, OSError)):
            cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", resume=True)
        assert {path.name: path.read_bytes() for path in root.iterdir()} == before


def test_historical_postcommit_crash_is_recoverable(tmp_path, monkeypatch):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    crawler, _ = _cafef_fake(monkeypatch, [f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()])
    class Crash(BaseException): pass
    replace = cli.Path.replace
    def interrupted(path, target):
        replace(path, target)
        if target.name == "manifest.json":
            raise Crash()
    with monkeypatch.context() as patch:
        patch.setattr(cli.Path, "replace", interrupted)
        with pytest.raises(Crash):
            cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=crawler)
    assert cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", resume=True)["status"] == "results_only"


def test_historical_101_member_cohort_retains_collection_scope(tmp_path, monkeypatch):
    import json
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    path = tmp_path / "universe.json"
    data = json.loads(path.read_text())
    data["members"] = [{"ticker": f"A{i:02d}", "exchange": "HSX"} for i in range(100)] + [{"ticker": "VCB", "exchange": "HSX"}]
    path.write_text(json.dumps(data), encoding="utf-8")
    class EmptyProvider:
        def crawl_symbol(self, *args):
            yield []
    manifest = cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=EmptyProvider())
    assert manifest["cohort_member_count"] == len(manifest["symbols"]) == 101
    assert "101 frozen snapshot members" in manifest["cohort_rationale"]
    assert all(term not in manifest["cohort_rationale"] for term in ("traded value", "VCB", "VN30"))
    assert manifest["status"] == "incomplete"
    assert all(entry["status"] == "incomplete" and entry["full_history_verified"] is False
               and entry["terminal_reason"] == "no_articles_observed_history_unverified" for entry in manifest["symbols"])
    assert cli.read_historical_manifest("data/historical_news/run") == manifest


@pytest.mark.parametrize("mode", ["no_pages", "provider_error"])
def test_historical_unobserved_symbols_never_commit_as_empty(tmp_path, monkeypatch, mode):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    class UnobservedProvider:
        def crawl_symbol(self, *args):
            if mode == "provider_error":
                raise TimeoutError("https://secret:password@cafef.vn/?token=SECRET")
            return iter(())
    manifest = cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=UnobservedProvider())
    assert manifest["status"] == manifest["symbols"][0]["status"] == "failed"
    assert manifest["symbols"][0]["pages"] == 0
    assert manifest["symbols"][0]["terminal_reason"] == "no_pages_observed"
    assert manifest["symbols"][0]["full_history_verified"] is False
    assert manifest["failures"] == [{"symbol": "AAA", "error": "ValueError" if mode == "no_pages" else "TimeoutError"}]
    with pytest.raises(ValueError, match="committed manifest"):
        cli.read_historical_manifest("data/historical_news/run")


def test_historical_recovery_rejects_fabricated_zero_page_empty(tmp_path, monkeypatch):
    import json
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    class EmptyProvider:
        def crawl_symbol(self, *args):
            yield []
    manifest = cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=EmptyProvider())
    assert cli.read_historical_manifest("data/historical_news/run") == manifest
    manifest["symbols"][0]["pages"] = 0
    manifest["shards"] = []
    manifest["shard_count"] = 0
    path = tmp_path / "data/historical_news/run/manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="outcome"):
        cli.read_historical_manifest("data/historical_news/run")
    assert path.read_bytes() == before


@pytest.fixture
def cafef_provider_contract():
    # Synthetic contract fixture, not a captured provider response or live evidence.
    return {
        "listing": f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode(),
        "detail": b'<html><h1>Revenue growth</h1></html>',
        "empty": "<html>Không tìm thấy</html>".encode(),
    }


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_cafef_fixture_retry_exhaustion_is_bounded(monkeypatch, cafef_provider_contract, status):
    import omega.data.macro_news_pipeline as module
    calls, closed, sleeps = [], [], []
    class Response:
        def __init__(self, code): self.status = code
        def getheader(self, key): return "text/html"
        def read(self, limit): return cafef_provider_contract["listing"]
    class Connection:
        def request(self, *a, **k): calls.append(1)
        def getresponse(self): return Response(status)
        def close(self): closed.append(1)
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 443))])
    monkeypatch.setattr(module, "_CafeFConnection", lambda *a: Connection())
    with pytest.raises(ValueError, match="retry exhausted"):
        CafeFHistoricalCrawler(sleeper=sleeps.append)._request("https://cafef.vn/tim-kiem.chn?keywords=AAA")
    assert len(calls) == len(closed) == 3
    assert len(sleeps) == 5


@pytest.mark.parametrize("kind", ["empty", "ambiguous", "category"])
def test_cafef_fixture_empty_and_category_contract(monkeypatch, cafef_provider_contract, kind):
    listing = cafef_provider_contract["empty"] if kind == "empty" else b"<html>no known listing</html>"
    if kind == "category":
        listing = b'<a rel="next" href="/other-category.chn?keywords=AAA&amp;page=2">Next</a>'
    crawler = CafeFHistoricalCrawler(sleeper=lambda _: None, clock=lambda: CAFEF_FETCHED)
    monkeypatch.setattr(crawler, "_request", lambda url: listing)
    if kind == "empty":
        assert list(crawler.crawl_symbol("AAA", "HSX", datetime(2015, 1, 1, tzinfo=timezone.utc), CAFEF_FETCHED)) == [[]]
    else:
        with pytest.raises(ValueError):
            list(crawler.crawl_symbol("AAA", "HSX", datetime(2015, 1, 1, tzinfo=timezone.utc), CAFEF_FETCHED))


def test_historical_manifest_duplicate_keys_rejected(committed_historical_run):
    cli, root, _ = committed_historical_run
    path = root / "manifest.json"
    path.write_text('{"status":"failed",' + path.read_text()[1:], encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        cli.read_historical_manifest("data/historical_news/run")


def test_historical_concurrent_directory_claim_keeps_owner(tmp_path, monkeypatch):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    root = tmp_path / "data/historical_news/run"
    mkdir = cli.Path.mkdir
    def race(path, *args, **kwargs):
        if path == root:
            mkdir(path)
            (path / "owner").write_bytes(b"other writer")
        return mkdir(path, *args, **kwargs)
    monkeypatch.setattr(cli.Path, "mkdir", race)
    with pytest.raises(FileExistsError):
        cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run")
    assert list(root.iterdir()) == [root / "owner"]
    assert (root / "owner").read_bytes() == b"other writer"


def test_historical_recovery_rejects_symlink_shard(committed_historical_run, tmp_path, monkeypatch):
    cli, root, manifest = committed_historical_run
    path = root / manifest["shards"][0]["path"]
    outside = tmp_path / "outside.parquet"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(outside)
    except OSError:
        # Exercise production link rejection even without Windows symlink privilege.
        path.write_bytes(outside.read_bytes())
        is_symlink = cli.Path.is_symlink
        monkeypatch.setattr(cli.Path, "is_symlink", lambda candidate: candidate == path or is_symlink(candidate))
    with pytest.raises(ValueError, match="links"):
        cli.read_historical_manifest("data/historical_news/run")


@pytest.fixture
def cafef_captured_responses(request):
    import hashlib
    root = Path(__file__).parent / "fixtures/cafef"
    if getattr(request, "param", None) == "empty":
        payload = (root / "empty_search_listing.html").read_bytes()
        capture = {
            "origin_url": "https://cafef.vn/tim-kiem.chn?keywords=ANV",
            "retrieved_at": datetime(2026, 10, 18, 23, 21, 48, tzinfo=timezone.utc),
            "response_bytes": 61044,
            "sha256": "db07600850eb776723cd71083e320ce15551783886962eb8846d03830286dee5",
            # Retained HTML declaration, not independently captured HTTP headers.
            "declared_content_type": "text/html; charset=utf-8",
        }
        assert len(payload) == capture["response_bytes"]
        assert hashlib.sha256(payload).hexdigest() == capture["sha256"]
        return payload, capture
    listing_bytes = (root / "vcb_search_listing.html").read_bytes()
    article_bytes = (root / "vcb_article_detail.html").read_bytes()
    assert len(listing_bytes) == 82595
    assert len(article_bytes) == 114189
    assert hashlib.sha256(listing_bytes).hexdigest() == "f0d7284d2beb08abb74acb1bd9bf2990e616a24b4e5954800e6986e968cd707f"
    assert hashlib.sha256(article_bytes).hexdigest() == "d80e971ef4ba5d6725a9723616a30eb47b12a5881fd8510b0a2290fe73f3fd6a"
    return listing_bytes, article_bytes


def test_cafef_captured_provider_contract_and_dom_fixtures(cafef_captured_responses):
    from omega.data.macro_news_pipeline import _CafeFPage, parse_cafef_timestamp, _text
    listing_bytes, article_bytes = cafef_captured_responses
    parser = _CafeFPage(listing_bytes)
    matches = [l for l in parser.links if "188261016210210067" in l[0]]
    assert len(matches) >= 1
    rel_url, _, title = matches[0]
    assert rel_url == "/xac-minh-loat-giao-dich-tu-10-trieu-dong-qua-cac-ngan-hang-mbbank-bidv-vcb-acb-shb-techcombank-khoi-to-pham-thi-mien-sn-1993-188261016210210067.chn"
    assert "Khởi tố Phạm Thị Miên" in title

    full_url = "https://cafef.vn" + rel_url
    ts = parse_cafef_timestamp(full_url)
    assert ts == datetime(2026, 10, 16, 14, 2, 10, tzinfo=timezone.utc)

    article_page = _CafeFPage(article_bytes)
    article_title = _text(" ".join(article_page.title))
    assert "Khởi tố Phạm Thị Miên" in article_title


@pytest.mark.parametrize("fault", [None, "listing_utf8", "detail_utf8", "detail_title", "detail_transport"])
def test_cafef_captured_responses_replay_production_crawler(monkeypatch, cafef_captured_responses, fault):
    import hashlib
    from omega.data.macro_news_pipeline import CAFEF_VERSION
    listing_bytes, article_bytes = cafef_captured_responses
    article_url = "https://cafef.vn/xac-minh-loat-giao-dich-tu-10-trieu-dong-qua-cac-ngan-hang-mbbank-bidv-vcb-acb-shb-techcombank-khoi-to-pham-thi-mien-sn-1993-188261016210210067.chn"
    listing_url = "https://cafef.vn/tim-kiem.chn?keywords=VCB"
    published = datetime(2026, 10, 16, 14, 2, 10, tzinfo=timezone.utc)
    calls = []

    def request(url):
        calls.append(url)
        if url == listing_url:
            return listing_bytes + b"\xff" if fault == "listing_utf8" else listing_bytes
        assert url == article_url, "Only the captured detail may be replayed"
        if fault == "detail_transport":
            raise TimeoutError("injected detail transport failure")
        if fault == "detail_utf8":
            return article_bytes + b"\xff"
        if fault == "detail_title":
            return article_bytes.replace(b"<h1 ", b"<h2 ").replace(b"</h1>", b"</h2>")
        return article_bytes

    crawler = CafeFHistoricalCrawler(sleeper=lambda _: None, clock=lambda: CAFEF_FETCHED)
    monkeypatch.setattr("omega.data.macro_news_pipeline.socket.getaddrinfo", lambda *a, **k: pytest.fail("captured replay must stay offline"))
    monkeypatch.setattr(crawler, "_request", request)
    # Inclusive publication range isolates the one detail capture, not 17 fabricated responses.
    if fault:
        error, message = {
            "listing_utf8": (UnicodeDecodeError, "utf-8"),
            "detail_utf8": (UnicodeDecodeError, "utf-8"),
            "detail_title": (ValueError, "CafeF detail title rejected"),
            "detail_transport": (TimeoutError, "injected detail transport failure"),
        }[fault]
        with pytest.raises(error, match=message):
            next(crawler.crawl_symbol("VCB", "HSX", published, published))
        assert calls == ([listing_url] if fault == "listing_utf8" else [listing_url, article_url])
        return

    pages = list(crawler.crawl_symbol("VCB", "HSX", published, published))
    assert calls == [listing_url, article_url]
    assert len(pages) == 1 and len(pages[0]) == 1
    record = pages[0][0]
    assert record["title"] == "Xác minh loạt giao dịch từ 10 triệu đồng qua các ngân hàng MBBank, BIDV, VCB, ACB, SHB, TECHCOMBANK,...: Khởi tố Phạm Thị Miên SN 1993"
    assert record["canonical_url"] == article_url
    assert record["source_record_id"] == article_url.removeprefix("https://cafef.vn")
    assert record["published_at"] == published
    assert record["available_at"] == record["ingested_at"] == CAFEF_FETCHED
    assert record["published_at"] < record["available_at"]
    assert record["raw_timestamp"] == "261016210210"
    assert record["payload_sha256"] == hashlib.sha256(article_bytes).hexdigest()
    assert (record["origin_ticker"], record["origin_exchange"]) == ("VCB", "HSX")
    assert record["source_kind"] == "cafef_historical"
    assert record["adapter_version"] == CAFEF_VERSION
    MacroNewsPipeline._validate(MacroNewsPipeline._frame(pages[0]))


@pytest.mark.parametrize("fault", ["size", "digest"])
def test_cafef_captured_empty_listing_binding_rejects_tampering(monkeypatch, fault):
    from types import SimpleNamespace
    read_bytes = Path.read_bytes

    def tampered(path):
        payload = read_bytes(path)
        if path.name == "empty_search_listing.html":
            return payload + b" " if fault == "size" else b"!" + payload[1:]
        return payload

    monkeypatch.setattr(Path, "read_bytes", tampered)
    with pytest.raises(AssertionError):
        cafef_captured_responses.__wrapped__(SimpleNamespace(param="empty"))


@pytest.mark.parametrize("cafef_captured_responses", ["empty"], indirect=True)
@pytest.mark.parametrize("fault", [None, "utf8", "empty_marker", "transport"])
def test_cafef_captured_empty_listing_replay(monkeypatch, cafef_captured_responses, fault):
    payload, capture = cafef_captured_responses
    assert capture["origin_url"] == "https://cafef.vn/tim-kiem.chn?keywords=ANV"
    assert capture["retrieved_at"] == datetime.fromisoformat("2026-10-18T23:21:48+00:00")
    assert capture["retrieved_at"] <= datetime(2026, 10, 19, 0, 25, 42, tzinfo=timezone.utc)
    assert capture["response_bytes"] == 61044
    assert capture["sha256"] == "db07600850eb776723cd71083e320ce15551783886962eb8846d03830286dee5"
    assert f'content="{capture["declared_content_type"]}"'.encode() in payload
    marker = "Không tìm thấy tin bài nào phù hợp với từ khóa ANV".encode()
    assert marker in payload
    calls = []

    def request(url):
        calls.append(url)
        assert url == capture["origin_url"], "Only the bound empty capture may be replayed"
        if fault == "transport":
            raise TimeoutError("injected empty listing transport failure")
        if fault == "utf8":
            return payload + b"\xff"
        if fault == "empty_marker":
            return payload.replace(marker, b"unrecognized provider response")
        return payload

    crawler = CafeFHistoricalCrawler(sleeper=lambda _: None, clock=lambda: capture["retrieved_at"])
    monkeypatch.setattr("omega.data.macro_news_pipeline.socket.getaddrinfo", lambda *a, **k: pytest.fail("captured replay must stay offline"))
    monkeypatch.setattr(crawler, "_request", request)
    pages = crawler.crawl_symbol("ANV", "HSX", datetime(2015, 1, 1, tzinfo=timezone.utc), capture["retrieved_at"])
    if fault:
        error, message = {
            "utf8": (UnicodeDecodeError, "utf-8"),
            "empty_marker": (ValueError, "CafeF unknown empty listing incomplete"),
            "transport": (TimeoutError, "injected empty listing transport failure"),
        }[fault]
        with pytest.raises(error, match=message):
            next(pages)
    else:
        observed = list(pages)
        assert len(observed) == 1
        assert sum(len(page) for page in observed) == 0
        assert observed == [[]]
    assert calls == [capture["origin_url"]]


def test_historical_pilot_p1_top100_staged_artifact_recovery():
    import scripts.fetch_news_sentiment as cli
    import hashlib
    pilot_dir = Path("data/historical_news/pilot_p1_top100")
    assert pilot_dir.is_dir()
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in pilot_dir.iterdir() if path.is_file()}
    manifest = cli.read_historical_manifest(pilot_dir)
    assert manifest["schema_version"] == 2
    assert manifest["status"] == "incomplete"
    assert manifest["purpose"] == "collection_not_investability"
    assert manifest["pit_verified"] is False
    assert manifest["full_history_verified"] is False
    assert manifest["cohort_member_count"] == len(manifest["members"]) == len(manifest["symbols"]) == 101
    # Recovery validates staged bytes, not provider acceptance for 101 members.
    vcb = next(s for s in manifest["symbols"] if s["symbol"] == "VCB")
    assert vcb["status"] == "results_only" and vcb["rows"] == 18 and vcb["pages"] == 1
    unverified_symbols = [s for s in manifest["symbols"] if s["status"] == "incomplete"]
    assert len(unverified_symbols) == 100
    assert all(s["terminal_reason"] == "no_articles_observed_history_unverified"
               and s["full_history_verified"] is False for s in unverified_symbols)
    assert vcb["terminal_reason"] == "provider_results_only" and vcb["full_history_verified"] is False
    assert len({tuple(member) for member in manifest["members"]}) == 101
    assert {s["status"] for s in manifest["symbols"]} == {"results_only", "incomplete"}
    assert len(manifest["shards"]) >= 2
    assert {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in pilot_dir.iterdir() if path.is_file()} == before


@pytest.mark.parametrize("rows", [None, "", True, -1, float("nan"), float("inf"), -float("inf")])
def test_historical_outcome_rejects_invalid_counts(rows):
    from omega.data.macro_news_pipeline import historical_news_outcome
    with pytest.raises(ValueError, match="accepted row count"):
        historical_news_outcome(rows)


@pytest.mark.parametrize("rows", [0, 1, 10**13])
def test_historical_outcome_never_verifies_history(rows):
    from omega.data.macro_news_pipeline import historical_news_outcome
    outcome = historical_news_outcome(rows)
    assert outcome == {
        "status": "results_only" if rows else "incomplete",
        "terminal_reason": "provider_results_only" if rows else "no_articles_observed_history_unverified",
        "full_history_verified": False,
    }


@pytest.mark.parametrize("mode", ["empty", "filtered", "partial_error", "constructor_error"])
def test_historical_terminal_outcomes_roundtrip(tmp_path, monkeypatch, mode):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    listing = "<html>Không tìm thấy</html>".encode() if mode == "empty" else f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()
    crawler, _ = _cafef_fake(monkeypatch, [listing])
    if mode == "partial_error":
        crawl = crawler.crawl_symbol
        def partial(*args):
            yield from crawl(*args)
            raise TimeoutError("https://secret:password@cafef.vn/?token=SECRET")
        monkeypatch.setattr(crawler, "crawl_symbol", partial)
    elif mode == "constructor_error":
        def fail(**kwargs):
            raise TimeoutError("https://secret:password@cafef.vn/?token=SECRET")
        monkeypatch.setattr("omega.data.macro_news_pipeline.CafeFHistoricalCrawler", fail)
    manifest = cli.build_historical_news_sentiment(
        "universe.json", "2015-01-02" if mode == "filtered" else "2015-01-01", "2015-01-02" if mode == "filtered" else "2026-10-18",
        CAFEF_FETCHED, "data/historical_news/run", **({} if mode == "constructor_error" else {"crawler": crawler}))
    outcome = manifest["symbols"][0]
    assert outcome["full_history_verified"] is False
    if mode in {"empty", "filtered"}:
        assert outcome["status"] == manifest["status"] == "incomplete"
        assert outcome["terminal_reason"] == "no_articles_observed_history_unverified"
        assert outcome["rows"] == 0 and outcome["pages"] == 1
        assert cli.read_historical_manifest("data/historical_news/run") == manifest
        assert cli.build_historical_news_sentiment(
            "universe.json", manifest["start"], manifest["end"], CAFEF_FETCHED,
            "data/historical_news/run", resume=True) == manifest
    else:
        assert outcome["status"] == manifest["status"] == "failed"
        assert outcome["terminal_reason"] == ("collection_error" if mode == "partial_error" else "not_attempted")
        assert all(secret not in str(manifest) for secret in ("password", "token=", "SECRET"))
        with pytest.raises(ValueError, match="committed manifest"):
            cli.read_historical_manifest("data/historical_news/run")


@pytest.mark.parametrize("mutation", ["status", "reason", "missing_reason", "verified", "aggregate", "legacy_digest"])
def test_historical_unverified_recovery_rejects_forgery(tmp_path, monkeypatch, mutation):
    import json
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    class EmptyProvider:
        def crawl_symbol(self, *args):
            yield []
    manifest = cli.build_historical_news_sentiment(
        "universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED, "data/historical_news/run", crawler=EmptyProvider())
    outcome = manifest["symbols"][0]
    if mutation == "status":
        outcome["status"] = "empty"
    elif mutation == "reason":
        outcome["terminal_reason"] = "verified_empty_history"
    elif mutation == "missing_reason":
        del outcome["terminal_reason"]
    elif mutation == "verified":
        outcome["full_history_verified"] = True
    elif mutation == "aggregate":
        manifest["status"] = "results_only"
    else:
        manifest.update(schema_version=1, status="results_only")
        outcome["status"] = "empty"
        manifest["shards"][0]["sha256"] = "0" * 64
    path = tmp_path / "data/historical_news/run/manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in path.parent.iterdir()}
    with pytest.raises(ValueError):
        cli.read_historical_manifest("data/historical_news/run")
    assert {p.name: p.read_bytes() for p in path.parent.iterdir()} == before


@pytest.mark.parametrize("status", ["incomplete", "failed", "results_only"])
@pytest.mark.parametrize("resume", [False, True])
def test_historical_cli_incomplete_exits_nonzero(monkeypatch, status, resume):
    import scripts.fetch_news_sentiment as cli
    import sys
    calls = []
    def build(*args, **kwargs):
        calls.append(kwargs)
        return {"status": status}
    monkeypatch.setattr(cli, "build_historical_news_sentiment", build)
    monkeypatch.setattr(sys, "argv", ["fetch_news_sentiment.py", "--historical", "--universe", "universe.json",
                                    "--start", "2015-01-01", "--end", "2026-10-18", "--as-of", CAFEF_FETCHED.isoformat(),
                                    "--output", "data/historical_news/run", *(["--resume"] if resume else [])])
    if status == "results_only":
        cli.main()
    else:
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 1
    assert calls == ([{"resume": True}] if resume else [{}])


@pytest.mark.parametrize("fault", ["size", "digest"])
def test_cafef_vcb_capture_integrity_f003(tmp_path, monkeypatch, fault):
    root = tmp_path / "cafef"
    root.mkdir()
    fixture_root = Path(__file__).parent / "fixtures/cafef"
    for name in ("vcb_search_listing.html", "vcb_article_detail.html"):
        (root / name).write_bytes((fixture_root / name).read_bytes())
    path = root / "vcb_article_detail.html"
    payload = path.read_bytes()
    path.write_bytes(payload + b"x" if fault == "size" else bytes([payload[0] ^ 1]) + payload[1:])
    original = Path.read_bytes
    def redirected(candidate):
        return original(root / candidate.name if candidate.parent == fixture_root else candidate)
    monkeypatch.setattr(Path, "read_bytes", redirected)
    with pytest.raises(AssertionError):
        cafef_captured_responses.__wrapped__(SimpleNamespace(param=None))


@pytest.mark.parametrize("fault", ["directory", "bom", "utf8", "crlf"])
def test_historical_manifest_encoding_preserves_committed_bytes(committed_historical_run, fault):
    cli, directory, manifest = committed_historical_run
    path = directory / "manifest.json"
    raw = path.read_bytes()
    if fault == "directory":
        path.unlink()
        path.mkdir()
    else:
        path.write_bytes({"bom": b"\xef\xbb\xbf" + raw, "utf8": b"\xff" + raw,
                          "crlf": raw.replace(b"\n", b"\r\n") + b"\r\n"}[fault])
    before = None if path.is_dir() else path.read_bytes()
    if fault == "crlf":
        assert cli.read_historical_manifest("data/historical_news/run") == manifest
    else:
        with pytest.raises(ValueError):
            cli.read_historical_manifest("data/historical_news/run")
    assert path.is_dir() if before is None else path.read_bytes() == before


@pytest.mark.parametrize("argument", ["--output=../escape", "--resume", "AAA;whoami", "$(whoami)"])
def test_cafef_symbol_injection_rejected_without_transport(monkeypatch, argument):
    crawler = CafeFHistoricalCrawler()
    monkeypatch.setattr(crawler, "_request", lambda *args: pytest.fail("transport invoked"))
    with pytest.raises(ValueError):
        list(crawler.crawl_symbol(argument, "HSX", datetime(2015, 1, 1, tzinfo=timezone.utc), CAFEF_FETCHED))


def test_historical_cli_unknown_flag_never_calls_collector(monkeypatch):
    import scripts.fetch_news_sentiment as cli
    monkeypatch.setattr(cli, "build_historical_news_sentiment", lambda *a, **k: pytest.fail("collector invoked"))
    monkeypatch.setattr(sys, "argv", ["fetch_news_sentiment.py", "--historical", "--universe", "universe.json",
                                    "--start", "2015-01-01", "--end", "2026-10-18", "--as-of", CAFEF_FETCHED.isoformat(),
                                    "--output", "data/historical_news/run", "--unknown-option"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_news_writer_lock_contender_preserves_owner_and_releases_on_fault(tmp_path):
    from omega.data.macro_news_pipeline import _writer_lock
    output = tmp_path / "news.parquet"
    lock = output.with_name(output.name + ".lock")
    with pytest.raises(OSError, match="injected owner failure"):
        with _writer_lock(output):
            owner = lock.read_bytes()
            with pytest.raises(TimeoutError):
                with _writer_lock(output, timeout=0):
                    pytest.fail("contender acquired owned lock")
            assert lock.read_bytes() == owner
            raise OSError("injected owner failure")
    assert not lock.exists()
    with _writer_lock(output, timeout=0):
        assert lock.read_bytes() == str(os.getpid()).encode()
    assert not lock.exists()


def test_news_concurrent_persist_retains_both_writers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    output = tmp_path / "news.parquet"
    ingested = datetime(2026, 8, 12, 3, tzinfo=timezone.utc)
    records = [RSSAdapter().parse("cafef_macro", "https://example.com/feed.rss",
               f"<rss><channel><item><title>Writer {i}</title><link>https://example.com/{i}</link>"
               "<pubDate>Tue, 12 Aug 2026 09:00:00 +0700</pubDate></item></channel></rss>", ingested)[0]
               for i in range(2)]
    barrier = Barrier(2)
    def persist(record):
        barrier.wait(timeout=5)
        return MacroNewsPipeline.persist(MacroNewsPipeline._frame([record]), output)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(persist, records))
    assert all(len(result) == 1 for result in results)
    assert set(pd.read_parquet(output)["raw_record_id"]) == {record["raw_record_id"] for record in records}
    assert not output.with_name(output.name + ".lock").exists()


def _batch_universe(tmp_path, members):
    import json
    path = tmp_path / "universe.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["members"] = [{"ticker": symbol, "exchange": exchange} for symbol, exchange in members]
    path.write_text(json.dumps(data), encoding="utf-8")


def _run_batch(cli, crawler=None, resume=False):
    return cli.build_historical_news_sentiment("universe.json", "2015-01-01", "2026-10-18", CAFEF_FETCHED,
                                             "data/historical_news/run", crawler=crawler, resume=resume)


def test_historical_dynamic_703_three_exchange_collection(tmp_path, monkeypatch):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    members = [(f"A{i:03d}", ("HSX", "HNX", "UPCOM")[i % 3]) for i in range(703)]
    _batch_universe(tmp_path, members)
    calls = []
    class Empty:
        def crawl_symbol(self, symbol, exchange, *args):
            calls.append((symbol, exchange))
            yield []
    manifest = _run_batch(cli, Empty())
    assert calls == members
    assert manifest["cohort_member_count"] == len(manifest["symbols"]) == 703
    assert manifest["shard_count"] == 1406
    assert "703 frozen snapshot members" in manifest["cohort_rationale"]
    assert manifest["status"] == "incomplete" and not manifest["pit_verified"]
    assert cli.read_historical_manifest("data/historical_news/run") == manifest
    class NoNetwork:
        def crawl_symbol(self, *args): pytest.fail("committed run must not fetch")
    assert _run_batch(cli, NoNetwork(), resume=True) == manifest


def test_cafef_upcom_nonempty_provenance_roundtrip(tmp_path, monkeypatch):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    _batch_universe(tmp_path, [("AAA", "UPCOM")])
    crawler, _ = _cafef_fake(monkeypatch, [f'<a href="{CAFEF_ARTICLE}">Story</a>'.encode()])
    manifest = _run_batch(cli, crawler)
    assert manifest["status"] == "results_only"
    assert manifest["symbols"][0]["exchange"] == "UPCOM"
    assert cli.read_historical_manifest("data/historical_news/run") == manifest
    raw = pd.read_parquet(tmp_path / "data/historical_news/run/AAA-UPCOM-0001-raw.parquet")
    assert raw["origin_exchange"].tolist() == ["UPCOM"]


@pytest.mark.parametrize("exchange", [None, "", "HOSE", "upcom", [], {}, float("nan"), float("inf"), -float("inf"), 10**13])
def test_historical_exchange_validation_before_mutation(tmp_path, monkeypatch, exchange):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    _batch_universe(tmp_path, [("AAA", exchange)])
    with pytest.raises(ValueError): _run_batch(cli)
    with pytest.raises(ValueError):
        list(CafeFHistoricalCrawler().crawl_symbol("AAA", exchange, CAFEF_FETCHED, CAFEF_FETCHED))
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("fault", ["raw", "projection", "checkpoint_write", "checkpoint_fsync", "checkpoint_replace", "checkpoint_after_replace", "provider"])
def test_historical_partial_batch_resume_skips_committed_symbols(tmp_path, monkeypatch, fault):
    import json
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    members = [("AAA", "HSX"), ("BBB", "UPCOM"), ("CCC", "HNX")]
    _batch_universe(tmp_path, members)
    class Crash(BaseException): pass
    class Provider:
        def crawl_symbol(self, symbol, *args):
            if symbol == "BBB" and fault == "provider":
                yield []
                raise TimeoutError("https://secret:password@cafef.vn/?token=SECRET")
            yield []
    write, publish = cli._write_historical_shard, cli._publish_historical_state
    def interrupted_shard(table, path, shards):
        write(table, path, shards)
        if path.name.startswith("BBB-") and path.name.endswith("-raw.parquet" if fault == "raw" else "-v10.parquet"):
            raise Crash()
    def interrupted_publish(value, destination, name):
        if name == "checkpoint.json" and any(entry["symbol"] == "BBB" for entry in value["symbols"]):
            if fault == "checkpoint_after_replace":
                publish(value, destination, name)
                raise Crash()
            with monkeypatch.context() as patch:
                if fault == "checkpoint_write": patch.setattr(cli.json, "dump", lambda *a, **k: (_ for _ in ()).throw(Crash()))
                elif fault == "checkpoint_fsync": patch.setattr(cli.os, "fsync", lambda *a: (_ for _ in ()).throw(Crash()))
                elif fault == "checkpoint_replace": patch.setattr(cli.Path, "replace", lambda *a: (_ for _ in ()).throw(Crash()))
                publish(value, destination, name)
                return
        publish(value, destination, name)
    with monkeypatch.context() as patch:
        if fault in {"raw", "projection"}: patch.setattr(cli, "_write_historical_shard", interrupted_shard)
        else: patch.setattr(cli, "_publish_historical_state", interrupted_publish)
        if fault == "provider":
            failed = _run_batch(cli, Provider())
            assert failed["status"] == "failed" and "SECRET" not in str(failed)
        else:
            with pytest.raises(Crash): _run_batch(cli, Provider())
    root = tmp_path / "data/historical_news/run"
    checkpoint = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
    committed = {entry["path"]: (root / entry["path"]).read_bytes() for entry in checkpoint["shards"]}
    (root / "unrelated.parquet").write_bytes(b"preserve")
    calls = []
    class Resume:
        def crawl_symbol(self, symbol, exchange, *args):
            calls.append((symbol, exchange))
            yield []
    result = _run_batch(cli, Resume(), resume=True)
    assert calls == [member for member in members if member[0] not in {entry["symbol"] for entry in checkpoint["symbols"]}]
    assert result["status"] == "incomplete"
    assert len(result["symbols"]) == 3 and result["shard_count"] == 6
    assert cli.read_historical_manifest("data/historical_news/run") == result
    assert all((root / name).read_bytes() == data for name, data in committed.items())
    assert (root / "unrelated.parquet").read_bytes() == b"preserve"
    assert not (root / "batch.lock").exists()


@pytest.mark.parametrize("mutation", ["digest", "missing", "pair", "duplicate", "members", "rows", "durable", "schema", "configuration", "duplicate_key", "directory", "bom", "utf8", "foreign_orphan", "committed_orphan"])
def test_historical_partial_checkpoint_rejected_before_mutation(tmp_path, monkeypatch, mutation):
    import json
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    _batch_universe(tmp_path, [("AAA", "HSX"), ("BBB", "UPCOM")])
    class Crash(BaseException): pass
    class Provider:
        def crawl_symbol(self, symbol, *args):
            if symbol == "BBB": raise Crash()
            yield []
    with pytest.raises(Crash): _run_batch(cli, Provider())
    root = tmp_path / "data/historical_news/run"
    path = root / "checkpoint.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "digest": (root / data["shards"][0]["path"]).write_bytes(b"bad")
    elif mutation == "missing": (root / data["shards"][0]["path"]).unlink()
    elif mutation == "pair": data["shards"].pop(); data["shard_count"] -= 1
    elif mutation == "duplicate": data["symbols"].append(data["symbols"][0])
    elif mutation == "members": data["members"][1][1] = "HSX"
    elif mutation == "rows": data["symbols"][0]["rows"] = float("inf")
    elif mutation == "durable": data["shards"][0]["durable"] = False
    elif mutation == "schema": data["shards"][0]["schema_sha256"] = "0" * 64
    elif mutation == "configuration": data["scorer_lexicon_sha256"] = "0" * 64
    elif mutation in {"foreign_orphan", "committed_orphan"}:
        (root / ("ZZZ-HSX-0001-raw.parquet" if mutation == "foreign_orphan" else "AAA-HSX-0002-raw.parquet")).write_bytes(b"orphan")
    path.write_text(json.dumps(data), encoding="utf-8")
    if mutation == "duplicate_key": path.write_text('{"schema_version":2,' + path.read_text()[1:], encoding="utf-8")
    elif mutation == "directory": path.unlink(); path.mkdir()
    elif mutation == "bom": path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    elif mutation == "utf8": path.write_bytes(b"\xff")
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    class NoNetwork:
        def crawl_symbol(self, *args): pytest.fail("corrupt checkpoint must not fetch")
    with pytest.raises((ValueError, OSError)): _run_batch(cli, NoNetwork(), resume=True)
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before


def test_historical_partial_resume_lock_preserves_owner(tmp_path, monkeypatch):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    root = tmp_path / "data/historical_news/run"
    root.mkdir(parents=True)
    lock = root / "batch.lock"
    lock.write_bytes(b"owner")
    with pytest.raises(TimeoutError): _run_batch(cli, resume=True)
    assert lock.read_bytes() == b"owner"


def test_historical_complete_checkpoint_final_publication_retry_without_provider(tmp_path, monkeypatch):
    cli = _historical_cli_fixture(tmp_path, monkeypatch)
    class Empty:
        def crawl_symbol(self, *args): yield []
    class Crash(BaseException): pass
    publish = cli._publish_historical_state
    def interrupted(value, destination, name):
        if name == "manifest.json": raise Crash()
        publish(value, destination, name)
    with monkeypatch.context() as patch:
        patch.setattr(cli, "_publish_historical_state", interrupted)
        with pytest.raises(Crash): _run_batch(cli, Empty())
    monkeypatch.setattr("omega.data.macro_news_pipeline.CafeFHistoricalCrawler", lambda **k: pytest.fail("all symbols already committed"))
    result = _run_batch(cli, resume=True)
    assert result["status"] == "incomplete"
    assert cli.read_historical_manifest("data/historical_news/run") == result


def test_historical_legacy_rationale_resume_is_read_only(committed_historical_run):
    import json
    cli, root, manifest = committed_historical_run
    manifest["cohort_rationale"] = "Legacy 101 member VCB VN30 rationale"
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    assert _run_batch(cli, resume=True) == manifest
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
