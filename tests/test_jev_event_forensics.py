from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

import pytest

from omega.data.news_aggregator import NewsAggregator, SentimentInput
from omega.data.corporate_action import CorporateActionAdjuster, create_dividend_action
from omega.quant.alpha.forensic_filter import ForensicFilter


NOW = datetime(2026, 9, 28, 9, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolate_default_news_history(tmp_path, monkeypatch):
    monkeypatch.setattr("omega.data.news_aggregator.DEFAULT_EVENT_HISTORY_PATH", tmp_path / "default.sqlite")


def _stub_news_sources(monkeypatch, aggregator, articles):
    monkeypatch.setattr(aggregator, "_scrape_vnstock_news", lambda *args: articles)
    for source in ("_scrape_vietstock", "_scrape_vietcap_news", "_scrape_cafef", "_scrape_tinnhanhck", "_scrape_vneconomy"):
        monkeypatch.setattr(aggregator, source, lambda *args: [])


def test_revision_and_pit():
    first = SentimentInput("FPT lãi", "feed", NOW - timedelta(hours=2), url="https://example.org/a", fetched_at=NOW - timedelta(hours=1))
    correction = SentimentInput("FPT lỗ", "feed", NOW - timedelta(hours=2), url=first.url, fetched_at=NOW)
    future = SentimentInput("FPT lãi", "feed", NOW, fetched_at=NOW + timedelta(hours=1))
    result = NewsAggregator.classify_event_revisions([correction, future, first], NOW)
    assert [event.novelty for event in result] == ["new", "revision"]
    assert result[1].revision_of == result[0].event_id
    assert result[1].event_id != result[0].event_id


def test_adjusted_price_not_penalized_twice():
    adjuster = CorporateActionAdjuster()
    announced = NOW - timedelta(days=7)
    adjuster.add_action(
        create_dividend_action(
            "FPT",
            "2026-09-28",
            1000,
            announced_at=announced,
            ingested_at=announced,
            available_at=announced,
            source="vci_corporate_action",
        )
    )
    prices = {"price_basis": "raw", "data": {"FPT": {"2026-09-25": {"close": 50000}, "2026-09-28": {"close": 49000}}}}
    once = adjuster.apply_adjustments(prices, as_of_time=NOW)
    assert once["data"]["FPT"]["2026-09-25"]["close"] == 49000
    assert adjuster.apply_adjustments(once, as_of_time=NOW) == once


def test_f001_revision_distinct_chain():
    # Story A: FPT (original -> duplicate -> revision 1 -> revision 2)
    a_orig = SentimentInput("FPT tăng trưởng", "feed", NOW - timedelta(hours=5), url="https://news.vn/fpt-1", fetched_at=NOW - timedelta(hours=4))
    a_dup = SentimentInput("FPT tăng trưởng", "feed", NOW - timedelta(hours=5), url=a_orig.url, fetched_at=NOW - timedelta(hours=3))
    a_rev1 = SentimentInput("FPT điều chỉnh giảm nhẹ", "feed", NOW - timedelta(hours=5), url=a_orig.url, fetched_at=NOW - timedelta(hours=2))
    a_rev2 = SentimentInput("FPT đính chính doanh thu", "feed", NOW - timedelta(hours=5), url=a_orig.url, fetched_at=NOW - timedelta(hours=1))

    # Story B: VNM (original -> revision 1)
    b_orig = SentimentInput("VNM mở rộng thị trường", "feed", NOW - timedelta(hours=4), url="https://news.vn/vnm-1", fetched_at=NOW - timedelta(hours=3))
    b_rev1 = SentimentInput("VNM hoãn mở rộng thị trường", "feed", NOW - timedelta(hours=4), url=b_orig.url, fetched_at=NOW - timedelta(hours=1))

    events = [b_rev1, a_rev2, a_dup, b_orig, a_orig, a_rev1]
    result = NewsAggregator.classify_event_revisions(events, NOW)

    assert len(result) == 5
    by_url = {}
    for ev in result:
        by_url.setdefault(ev.url, []).append(ev)

    fpt_chain = by_url["https://news.vn/fpt-1"]
    vnm_chain = by_url["https://news.vn/vnm-1"]

    assert len(fpt_chain) == 3
    assert [ev.novelty for ev in fpt_chain] == ["new", "revision", "revision"]
    assert fpt_chain[1].revision_of == fpt_chain[0].event_id
    assert fpt_chain[2].revision_of == fpt_chain[1].event_id
    assert len({ev.event_id for ev in fpt_chain}) == 3

    assert len(vnm_chain) == 2
    assert [ev.novelty for ev in vnm_chain] == ["new", "revision"]
    assert vnm_chain[1].revision_of == vnm_chain[0].event_id
    assert len({ev.event_id for ev in result}) == len(result)

    # Lineage isolation across distinct identities
    assert vnm_chain[1].revision_of != fpt_chain[0].event_id
    assert vnm_chain[1].revision_of != fpt_chain[1].event_id
    assert fpt_chain[0].event_id != vnm_chain[0].event_id

    # Forensic shadow evaluation handles qualified events without veto
    forensic = ForensicFilter(enabled=True).evaluate_counterfactual(
        [{"event_id": ev.event_id, "available_at": ev.available_at, "novelty": ev.novelty} for ev in result],
        NOW,
    )
    assert forensic["counterfactual_excluded"] is True
    assert forensic["excluded"] is False
    assert len(forensic["qualified_events"]) == 5


def test_f002_provenance_quarantine():
    from omega.data.corporate_action import CorporateAction

    # 1. Action missing provenance is quarantined and unavailable
    unverified = CorporateAction("FPT", "2026-09-28", "dividend", dividend_amount=1000)
    assert unverified.is_quarantined is True
    assert "missing availability provenance" in (unverified.quarantine_reason or "")
    assert unverified.is_available_at(NOW) is False

    # 2. Invariant: available_at must equal max(announced_at, ingested_at)
    t1 = NOW - timedelta(days=5)
    t2 = NOW - timedelta(days=3)
    t_invalid = NOW - timedelta(days=4)
    with pytest.raises(ValueError, match="available_at must equal max"):
        CorporateAction(
            "FPT",
            "2026-09-28",
            "dividend",
            announced_at=t1,
            ingested_at=t2,
            available_at=t_invalid,
            source="exchange_notice",
            dividend_amount=1000,
        )

    # 3. ForensicFilter rejects timezone-naive timestamps
    filter_inst = ForensicFilter(enabled=True)
    with pytest.raises(ValueError, match="as_of must be timezone-aware"):
        filter_inst.evaluate_counterfactual([], as_of=datetime(2026, 9, 28, 9, 0))

    with pytest.raises(ValueError, match="event available_at must be timezone-aware"):
        filter_inst.evaluate_counterfactual(
            [{"event_id": "e1", "available_at": datetime(2026, 9, 28, 8, 0), "novelty": "new"}],
            as_of=NOW,
        )


def test_f003_nonfinite_and_calendar_rejections():
    from omega.data.corporate_action import create_split_action, create_rights_action
    adjuster = CorporateActionAdjuster()

    # 1. Closed exchange calendar sessions (holidays + weekend) fail closed
    for closed_date in ["2026-01-01", "2026-04-30", "2026-05-01", "2026-09-02", "2026-09-26"]:
        adj = CorporateActionAdjuster()
        adj.add_action(create_dividend_action("FPT", closed_date, 1000, announced_at=NOW, ingested_at=NOW, available_at=NOW, source="exchange"))
        with pytest.raises(ValueError, match="exchange session"):
            adj.apply_adjustments({"price_basis": "raw", "data": {"FPT": {}}}, as_of_time=NOW)

    # 2. Non-positive or out-of-bounds factor calculation rejections
    valid_action = create_dividend_action("FPT", "2026-09-28", 1000)
    with pytest.raises(ValueError, match="Invalid close price"):
        adjuster.calculate_adjustment_factor(valid_action, close_price=0.0)
    with pytest.raises(ValueError, match="Invalid close price"):
        adjuster.calculate_adjustment_factor(valid_action, close_price=-100.0)
    with pytest.raises(ValueError, match="Invalid dividend adjustment factor"):
        adjuster.calculate_adjustment_factor(valid_action, close_price=1000.0)
    with pytest.raises(ValueError, match="Invalid dividend adjustment factor"):
        adjuster.calculate_adjustment_factor(valid_action, close_price=500.0)

    # Split ratio non-positive rejection
    split_action = create_split_action("FPT", "2026-09-28", split_ratio=0.0)
    with pytest.raises(ValueError, match="Invalid split ratio"):
        adjuster.calculate_adjustment_factor(split_action, close_price=50000.0)

    # Rights issue invalid close price rejection
    rights_action = create_rights_action("FPT", "2026-09-28", rights_ratio=1.0, rights_price=10000.0)
    with pytest.raises(ValueError, match="Invalid close price"):
        adjuster.calculate_adjustment_factor(rights_action, close_price=-1.0)


def test_closed_calendar_fails():
    adjuster = CorporateActionAdjuster()
    adjuster.add_action(create_dividend_action("FPT", "2026-09-27", 1000, announced_at=NOW, ingested_at=NOW, available_at=NOW, source="exchange"))
    with pytest.raises(ValueError, match="exchange session"):
        adjuster.apply_adjustments({"price_basis": "raw", "data": {"FPT": {}}}, as_of_time=NOW)


def test_forensic_never_vetoes():
    result = ForensicFilter(enabled=True).evaluate_counterfactual(
        [{"event_id": "a", "available_at": NOW, "novelty": "revision"}], NOW
    )
    assert result["counterfactual_excluded"] is True
    assert result["excluded"] is False


@pytest.mark.parametrize("novelty", [None, "", "unknown", 1, [], {"new": True}])
def test_forensic_rejects_invalid_novelty(novelty):
    with pytest.raises(ValueError, match="novelty"):
        ForensicFilter(enabled=True).evaluate_counterfactual(
            [{"event_id": "a", "available_at": NOW, "novelty": novelty}], NOW
        )


def test_forensic_rejects_missing_novelty_and_malformed_record():
    for event in ({"event_id": "a", "available_at": NOW}, None, "event"):
        with pytest.raises(ValueError, match="novelty|mapping"):
            ForensicFilter(enabled=True).evaluate_counterfactual([event], NOW)


@pytest.mark.parametrize("bad_as_of", [0, "", [], {}])
def test_forensic_rejects_falsey_non_datetime_as_of(bad_as_of):
    with pytest.raises(ValueError, match="as_of must be datetime"):
        ForensicFilter(enabled=True).evaluate_counterfactual([], as_of=bad_as_of)


@pytest.mark.parametrize("bad_events", [0, "", {}, False])
def test_forensic_rejects_invalid_events_container(bad_events):
    with pytest.raises(ValueError, match="events must be a sequence"):
        ForensicFilter(enabled=True).evaluate_counterfactual(bad_events, as_of=NOW)


def test_forensic_none_defaults_remain_valid():
    assert ForensicFilter().evaluate_counterfactual(None, None)["qualified_events"] == []


@pytest.mark.parametrize("bad_prior", [[], 0, {0: SentimentInput("FPT", "feed", NOW, available_at=NOW, event_id="id")}])
def test_news_prior_seen_container_and_key_fail_closed(bad_prior):
    with pytest.raises(ValueError, match="invalid prior news event"):
        NewsAggregator.classify_event_revisions([], NOW, prior_seen=bad_prior)


def test_forensic_duplicate_and_future_events_do_not_qualify():
    result = ForensicFilter(enabled=True).evaluate_counterfactual([
        {"event_id": "duplicate", "available_at": NOW, "novelty": "duplicate"},
        {"event_id": "future", "available_at": NOW + timedelta(seconds=1), "novelty": "new"},
    ], NOW)
    assert result["qualified_events"] == []


def test_fetch_recent_news_keeps_similar_correction_before_dedup(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from omega.data.news_aggregator import NewsAggregator, SentimentInput
    aggregator = NewsAggregator()
    now = datetime.now(timezone.utc)
    first = SentimentInput('VNM tang doanh thu 100 ty', 'Vietstock', now - timedelta(minutes=10),
                           url='https://vietstock.vn/a', fetched_at=now - timedelta(minutes=8))
    correction = SentimentInput('VNM tang doanh thu 101 ty', 'Vietstock', now - timedelta(minutes=10),
                                url=first.url, fetched_at=now - timedelta(minutes=4))
    monkeypatch.setattr(aggregator, '_scrape_vnstock_news', lambda *args: [first, correction])
    monkeypatch.setattr(aggregator, '_scrape_vietstock', lambda *args: [])
    monkeypatch.setattr(aggregator, '_scrape_vietcap_news', lambda *args: [])
    monkeypatch.setattr(aggregator, '_scrape_cafef', lambda *args: [])
    monkeypatch.setattr(aggregator, '_scrape_tinnhanhck', lambda *args: [])
    monkeypatch.setattr(aggregator, '_scrape_vneconomy', lambda *args: [])
    events = aggregator.fetch_recent_news(now + timedelta(seconds=1))
    assert len(events) == 2
    assert events[0].novelty == 'revision'
    assert events[0].revision_of == events[1].event_id


def test_fetch_recent_news_links_correction_only_second_cycle(monkeypatch):
    aggregator = NewsAggregator()
    now = datetime.now(timezone.utc)
    published = now - timedelta(minutes=20)
    first = SentimentInput("FPT doanh thu 100", "feed", published, url="https://news.vn/fpt", fetched_at=now - timedelta(minutes=10))
    correction = SentimentInput("FPT doanh thu 101", "feed", published, url=first.url, fetched_at=now - timedelta(minutes=2))
    responses = iter(([first], [correction], [correction]))
    monkeypatch.setattr(aggregator, "_scrape_vnstock_news", lambda *args: next(responses))
    for source in ("_scrape_vietstock", "_scrape_vietcap_news", "_scrape_cafef", "_scrape_tinnhanhck", "_scrape_vneconomy"):
        monkeypatch.setattr(aggregator, source, lambda *args: [])

    original = aggregator.fetch_recent_news(now)[0]
    revised = aggregator.fetch_recent_news(now + timedelta(seconds=1))[0]
    assert revised.novelty == "revision"
    assert revised.revision_of == original.event_id
    assert revised.event_id != original.event_id
    assert aggregator.fetch_recent_news(now + timedelta(seconds=2))[0].novelty == "duplicate"
    assert aggregator._event_history[first.url].event_id == revised.event_id

    next_correction = SentimentInput("FPT doanh thu 102", "feed", published, url=first.url, fetched_at=now)
    monkeypatch.setattr(aggregator, "_scrape_vnstock_news", lambda *args: [first, correction, next_correction])
    newest = aggregator.fetch_recent_news(now + timedelta(seconds=3))
    assert len(newest) == 1
    assert newest[0].revision_of == revised.event_id


def test_classify_revision_uses_only_valid_prior_history():
    first = SentimentInput("VCB lợi nhuận 100", "feed", NOW - timedelta(hours=2), url="https://news.vn/vcb", fetched_at=NOW - timedelta(hours=1))
    original = NewsAggregator.classify_event_revisions([first], NOW)[0]
    correction = SentimentInput("VCB lợi nhuận 101", "feed", first.timestamp, url=first.url, fetched_at=NOW + timedelta(minutes=1))
    prior_seen = {first.url: original}
    assert NewsAggregator.classify_event_revisions([correction], NOW, prior_seen=prior_seen) == []
    revised = NewsAggregator.classify_event_revisions([correction], NOW + timedelta(minutes=2), prior_seen=prior_seen)[0]
    assert (revised.novelty, revised.revision_of) == ("revision", original.event_id)
    assert prior_seen[first.url] is original

    future_history = SentimentInput("VCB lợi nhuận 100", "feed", first.timestamp, url=first.url,
                                    fetched_at=NOW + timedelta(hours=1), available_at=NOW + timedelta(hours=1), event_id="future")
    same_cutoff = SentimentInput("VCB lợi nhuận 101", "feed", first.timestamp, url=first.url, fetched_at=NOW)
    assert NewsAggregator.classify_event_revisions([same_cutoff], NOW, prior_seen={first.url: future_history})[0].novelty == "new"

    missing_id = SentimentInput("VCB lợi nhuận 100", "feed", first.timestamp, url=first.url,
                                fetched_at=first.fetched_at, available_at=first.fetched_at)
    with pytest.raises(ValueError, match="invalid prior news event"):
        NewsAggregator.classify_event_revisions([SentimentInput("VCB lợi nhuận 102", "feed", first.timestamp, url=first.url, fetched_at=NOW)], NOW, prior_seen={first.url: missing_id})


def test_news_correction_only_after_restart_retains_lineage(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    path = tmp_path / "history.sqlite"
    published = now - timedelta(minutes=20)
    original = SentimentInput("FPT doanh thu 100", "feed", published, url="https://news.vn/fpt", fetched_at=now - timedelta(minutes=10))
    first = NewsAggregator(event_history_path=path)
    _stub_news_sources(monkeypatch, first, [original])
    event_id = first.fetch_recent_news(now)[0].event_id

    correction = SentimentInput("FPT doanh thu 101", "feed", published, url=original.url, fetched_at=now)
    restarted = NewsAggregator(event_history_path=path)
    _stub_news_sources(monkeypatch, restarted, [correction])
    result = restarted.fetch_recent_news(now + timedelta(seconds=1))
    assert len(result) == 1
    assert (result[0].novelty, result[0].revision_of) == ("revision", event_id)
    assert result[0].event_id != event_id
    with sqlite3.connect(path) as connection:
        assert restarted._load_event_history(connection, now + timedelta(seconds=1))[original.url].event_id == result[0].event_id


def test_news_fetch_explicit_prior_seen_filters_future_and_links_revision(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    published = now - timedelta(minutes=15)
    url = "https://news.vn/known"
    original = NewsAggregator.classify_event_revisions(
        [SentimentInput("VCB lãi 100", "feed", published, url=url, fetched_at=now - timedelta(minutes=5))], now
    )[0]
    correction = SentimentInput("VCB lãi 101", "feed", published, url=url, fetched_at=now)
    aggregator = NewsAggregator()
    _stub_news_sources(monkeypatch, aggregator, [correction])
    result = aggregator.fetch_recent_news(now + timedelta(seconds=1), prior_seen={url: original})
    assert (result[0].novelty, result[0].revision_of) == ("revision", original.event_id)
    assert original.text == "VCB lãi 100"

    future = SentimentInput("VCB lãi 102", "feed", published, url=url, fetched_at=now + timedelta(hours=2),
                            available_at=now + timedelta(hours=2), event_id="future")
    fresh = NewsAggregator(event_history_path=tmp_path / "fresh.sqlite")
    _stub_news_sources(monkeypatch, fresh, [SentimentInput("VCB lãi 101", "feed", published, url=url, fetched_at=now)])
    assert fresh.fetch_recent_news(now + timedelta(seconds=1), prior_seen={url: future})[0].novelty == "new"


def test_news_fetch_prior_seen_overrides_future_instance_history(monkeypatch):
    now = datetime.now(timezone.utc)
    published = now - timedelta(minutes=20)
    url = "https://news.vn/prior"
    original = NewsAggregator.classify_event_revisions([
        SentimentInput("FPT 100", "feed", published, url=url, fetched_at=now - timedelta(minutes=4))
    ], now)[0]
    aggregator = NewsAggregator()
    aggregator._event_history[url] = SentimentInput(
        "FPT 102", "feed", published, url=url, fetched_at=now + timedelta(minutes=3), event_id="future"
    )
    _stub_news_sources(monkeypatch, aggregator, [
        SentimentInput("FPT 101", "feed", published, url=url, fetched_at=now)
    ])
    correction = aggregator.fetch_recent_news(now + timedelta(seconds=1), prior_seen={url: original})[0]
    assert (correction.novelty, correction.revision_of) == ("revision", original.event_id)


def test_news_history_bounded_oldest_evicted_across_fetches_and_restart(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    path = tmp_path / "history.sqlite"
    aggregator = NewsAggregator(event_history_path=path, max_history_size=2)
    for index in range(5):
        article = SentimentInput(
            f"Article {index}", "feed", now - timedelta(minutes=20),
            url=f"https://news.vn/{index}", fetched_at=now - timedelta(minutes=5-index),
        )
        _stub_news_sources(monkeypatch, aggregator, [article])
        assert len(aggregator.fetch_recent_news(now)) == 1
        assert len(aggregator._event_history) <= 2
    assert set(aggregator._event_history) == {"https://news.vn/3", "https://news.vn/4"}
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM news_event_history").fetchone()[0] == 2
    restarted = NewsAggregator(event_history_path=path, max_history_size=2)
    _stub_news_sources(monkeypatch, restarted, [
        SentimentInput("Article 3 corrected", "feed", now - timedelta(minutes=20), url="https://news.vn/3", fetched_at=now)
    ])
    assert restarted.fetch_recent_news(now + timedelta(seconds=1))[0].novelty == "revision"
    _stub_news_sources(monkeypatch, restarted, [
        SentimentInput("Article 0 corrected", "feed", now - timedelta(minutes=20), url="https://news.vn/0", fetched_at=now)
    ])
    assert restarted.fetch_recent_news(now + timedelta(seconds=2))[0].novelty == "new"


def test_news_history_in_memory_cap_evicts_by_availability(monkeypatch):
    now = datetime.now(timezone.utc)
    aggregator = NewsAggregator(max_history_size=2)
    for index, minutes_ago in enumerate((4, 2, 3, 1)):
        _stub_news_sources(monkeypatch, aggregator, [SentimentInput(
            f"Report {index}", "feed", now - timedelta(minutes=10),
            url=f"https://news.vn/memory-{index}", fetched_at=now - timedelta(minutes=minutes_ago),
        )])
        aggregator.fetch_recent_news(now)
        assert len(aggregator._event_history) <= 2
    assert set(aggregator._event_history) == {"https://news.vn/memory-1", "https://news.vn/memory-3"}


def test_news_history_write_failure_rolls_back_and_does_not_advance_memory(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    path = tmp_path / "history.sqlite"
    url = "https://news.vn/fail"
    aggregator = NewsAggregator(event_history_path=path, max_history_size=1)
    _stub_news_sources(monkeypatch, aggregator, [
        SentimentInput("FPT 100", "feed", now - timedelta(minutes=20), url=url, fetched_at=now - timedelta(minutes=5))
    ])
    original_id = aggregator.fetch_recent_news(now)[0].event_id
    _stub_news_sources(monkeypatch, aggregator, [
        SentimentInput("FPT 101", "feed", now - timedelta(minutes=20), url=url, fetched_at=now)
    ])
    real_persist = aggregator._persist_event_history

    def fail_after_insert(connection, events):
        real_persist(connection, events)
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(aggregator, "_persist_event_history", fail_after_insert)
    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        aggregator.fetch_recent_news(now + timedelta(seconds=1))
    assert aggregator._event_history[url].event_id == original_id
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM news_event_history").fetchone()[0] == 1
    assert NewsAggregator(event_history_path=path)._event_history == {}
    monkeypatch.setattr(aggregator, "_persist_event_history", real_persist)
    revised = aggregator.fetch_recent_news(now + timedelta(seconds=2))[0]
    assert (revised.novelty, revised.revision_of) == ("revision", original_id)


def test_news_history_corrupted_payload_fails_closed(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    path = tmp_path / "history.sqlite"
    aggregator = NewsAggregator(event_history_path=path)
    _stub_news_sources(monkeypatch, aggregator, [
        SentimentInput("FPT 100", "feed", now - timedelta(minutes=10), url="https://news.vn/corrupt", fetched_at=now)
    ])
    aggregator.fetch_recent_news(now + timedelta(seconds=1))
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE news_event_history SET payload = ?", ('{"event_id":"forged"}',))
    fresh = NewsAggregator(event_history_path=path)
    _stub_news_sources(monkeypatch, fresh, [])
    with pytest.raises((ValueError, TypeError)):
        fresh.fetch_recent_news(now + timedelta(seconds=2))
    assert fresh._event_history == {}


def test_news_history_invalid_database_does_not_overwrite_source(tmp_path):
    path = tmp_path / "history.sqlite"
    path.write_bytes(b"not a sqlite database")
    with pytest.raises(sqlite3.DatabaseError):
        NewsAggregator(event_history_path=path)
    assert path.read_bytes() == b"not a sqlite database"


def test_news_history_parallel_instances_preserve_distinct_events(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    path = tmp_path / "history.sqlite"
    instances = [NewsAggregator(event_history_path=path, max_history_size=2) for _ in range(2)]
    for index, aggregator in enumerate(instances):
        _stub_news_sources(monkeypatch, aggregator, [
            SentimentInput(f"FPT {index}", "feed", now - timedelta(minutes=10),
                           url=f"https://news.vn/thread-{index}", fetched_at=now)
        ])
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert all(executor.map(lambda instance: len(instance.fetch_recent_news(now + timedelta(seconds=1))) == 1, instances))
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM news_event_history").fetchone()[0] == 2


def test_news_history_reloads_only_versions_visible_at_as_of(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    path = tmp_path / "history.sqlite"
    url = "https://news.vn/pit"
    published = now - timedelta(minutes=20)
    aggregator = NewsAggregator(event_history_path=path)
    _stub_news_sources(monkeypatch, aggregator, [SentimentInput(
        "VCB 100", "feed", published, url=url, fetched_at=now - timedelta(minutes=10)
    )])
    original_id = aggregator.fetch_recent_news(now)[0].event_id
    _stub_news_sources(monkeypatch, aggregator, [SentimentInput(
        "VCB 101", "feed", published, url=url, fetched_at=now
    )])
    revised_id = aggregator.fetch_recent_news(now + timedelta(seconds=1))[0].event_id
    with sqlite3.connect(path) as connection:
        assert aggregator._load_event_history(connection, now - timedelta(minutes=5))[url].event_id == original_id
        assert aggregator._load_event_history(connection, now + timedelta(seconds=2))[url].event_id == revised_id


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_news_history_rejects_invalid_capacity(limit):
    with pytest.raises(ValueError, match="max_history_size"):
        NewsAggregator(max_history_size=limit)


def test_news_history_rejects_non_durable_memory_path():
    with pytest.raises(ValueError, match="durable file"):
        NewsAggregator(event_history_path=":memory:")


def test_news_default_history_is_instance_local(tmp_path, monkeypatch):
    monkeypatch.setattr("omega.data.news_aggregator.DEFAULT_EVENT_HISTORY_PATH", tmp_path / "history.sqlite")
    now = datetime.now(timezone.utc)
    published = now - timedelta(minutes=20)
    url = "https://news.vn/default-restart"
    first = NewsAggregator()
    _stub_news_sources(monkeypatch, first, [SentimentInput(
        "FPT 100", "feed", published, url=url, fetched_at=now - timedelta(minutes=5)
    )])
    first_id = first.fetch_recent_news(now)[0].event_id
    assert first.event_history_path is None
    assert not (tmp_path / "history.sqlite").exists()
    restarted = NewsAggregator()
    _stub_news_sources(monkeypatch, restarted, [SentimentInput(
        "FPT 101", "feed", published, url=url, fetched_at=now
    )])
    revision = restarted.fetch_recent_news(now + timedelta(seconds=1))[0]
    assert revision.novelty == "new"
    assert revision.revision_of is None


@pytest.mark.parametrize("defect", ["publication_after_availability", "identity_mismatch", "missing_availability"])
def test_news_prior_seen_invalid_entry_fails_closed(defect, tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    url = "https://news.vn/forged"
    path = tmp_path / "history.sqlite"
    prior = SentimentInput("FPT 100", "feed", now - timedelta(minutes=5),
                           url=url, available_at=now - timedelta(minutes=1), event_id="original")
    identity = url
    if defect == "publication_after_availability":
        prior.timestamp = now
    elif defect == "identity_mismatch":
        identity = "https://news.vn/other"
    else:
        prior.available_at = None
    candidate = SentimentInput("FPT 101", "feed", now - timedelta(minutes=5), url=url, fetched_at=now)
    with pytest.raises(ValueError, match="invalid prior news event"):
        NewsAggregator.classify_event_revisions([candidate], now + timedelta(seconds=1), {identity: prior})
    aggregator = NewsAggregator(event_history_path=path)
    _stub_news_sources(monkeypatch, aggregator, [candidate])
    with pytest.raises(ValueError, match="invalid prior news event"):
        aggregator.fetch_recent_news(now + timedelta(seconds=1), prior_seen={identity: prior})
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM news_event_history").fetchone()[0] == 0
    assert aggregator._event_history == {}


def test_news_history_valid_json_text_tampering_fails_closed(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    path = tmp_path / "history.sqlite"
    original = SentimentInput("FPT 100", "feed", now - timedelta(minutes=10),
                              url="https://news.vn/tampered", fetched_at=now)
    aggregator = NewsAggregator(event_history_path=path)
    _stub_news_sources(monkeypatch, aggregator, [original])
    aggregator.fetch_recent_news(now + timedelta(seconds=1))
    with sqlite3.connect(path) as connection:
        stored, digest = connection.execute("SELECT payload, payload_sha256 FROM news_event_history").fetchone()
        assert digest == aggregator._payload_sha256(stored)
        data = json.loads(stored)
        data["text"] = "FPT 999"
        connection.execute("UPDATE news_event_history SET payload = ?", (json.dumps(data, ensure_ascii=False),))
    restarted = NewsAggregator(event_history_path=path)
    _stub_news_sources(monkeypatch, restarted, [])
    with pytest.raises(ValueError, match="payload digest"):
        restarted.fetch_recent_news(now + timedelta(seconds=2))
    assert restarted._event_history == {}


def test_news_history_missing_digest_fails_closed_without_migration_guess(tmp_path):
    path = tmp_path / "history.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE news_event_history (event_id TEXT PRIMARY KEY, identity TEXT NOT NULL, "
            "available_at TEXT NOT NULL, published_at TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO news_event_history VALUES (?, ?, ?, ?, ?)",
            ("old", "https://news.vn/old", NOW.isoformat(), NOW.isoformat(), "{}"),
        )
    aggregator = NewsAggregator(event_history_path=path)
    with sqlite3.connect(path) as connection:
        with pytest.raises(ValueError, match="payload digest"):
            aggregator._load_event_history(connection, NOW)
        assert connection.execute("SELECT count(*) FROM news_event_history").fetchone()[0] == 1


def test_news_default_duplicate_remains_visible_without_disk(tmp_path, monkeypatch):
    monkeypatch.setattr("omega.data.news_aggregator.DEFAULT_EVENT_HISTORY_PATH", tmp_path / "unused.sqlite")
    now = datetime.now(timezone.utc)
    aggregator = NewsAggregator()
    article = SentimentInput("FPT headline", "feed", now - timedelta(minutes=10),
                             url="https://news.vn/default", fetched_at=now)
    _stub_news_sources(monkeypatch, aggregator, [article])
    assert aggregator.fetch_recent_news(now + timedelta(seconds=1))[0].novelty == "new"
    assert aggregator.fetch_recent_news(now + timedelta(seconds=2))[0].novelty == "duplicate"
    assert not (tmp_path / "unused.sqlite").exists()
    assert NewsAggregator()._event_history == {}


def test_news_prior_seen_naive_availability_fails_closed(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    prior = SentimentInput("FPT 100", "feed", now - timedelta(minutes=10),
                           url="https://news.vn/naive", available_at=now.replace(tzinfo=None), event_id="prior")
    aggregator = NewsAggregator(event_history_path=tmp_path / "history.sqlite")
    _stub_news_sources(monkeypatch, aggregator, [SentimentInput(
        "FPT 101", "feed", now - timedelta(minutes=10), url=prior.url, fetched_at=now
    )])
    with pytest.raises(ValueError, match="invalid prior news event"):
        aggregator.fetch_recent_news(now + timedelta(seconds=1), prior_seen={prior.url: prior})
    with sqlite3.connect(aggregator.event_history_path) as connection:
        assert connection.execute("SELECT count(*) FROM news_event_history").fetchone()[0] == 0
