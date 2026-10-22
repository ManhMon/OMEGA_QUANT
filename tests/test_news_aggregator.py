"""Unit tests for PIT-safe news aggregation."""

from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import requests

import pandas as pd
import pytest

from omega.data.news_aggregator import NewsAggregator, SentimentInput, _configure_utf8_stdio


@pytest.fixture(autouse=True)
def no_live_news_requests(monkeypatch):
    def offline(*args, **kwargs):
        raise requests.ConnectionError("network disabled in unit tests")

    monkeypatch.setattr(requests, "get", offline)


def test_configure_utf8_stdio_windows_safe():
    _configure_utf8_stdio()


def test_vnstock_exception_resilience_falls_back_to_html():
    aggregator = NewsAggregator()
    with patch.object(NewsAggregator, "_load_universe_tickers", return_value=["VCB"]), patch("omega.data.vci_direct.DirectVCIClient.fetch_company_news") as company:
        company.side_effect = RuntimeError("RateLimitExceeded")
        result = aggregator._scrape_vnstock_news(datetime.now(timezone.utc), hours_back=24)
    assert isinstance(result, list)


@pytest.fixture
def mock_vnstock_news_frame():
    return pd.DataFrame(
        [
            {
                "news_title": "VCB bứt phá mạnh sau tin tích cực",
                "news_short_content": "Nhà đầu tư kỳ vọng đà tăng tiếp diễn.",
                "public_date": "2026-06-19T14:30:00",
            },
            {
                "news_title": "VCB áp lực margin call đè nặng tâm lý",
                "news_short_content": "Rủi ro ngắn hạn tăng lên.",
                "public_date": "2026-06-19T15:00:00",
            },
            {
                "news_title": "VCB cập nhật thông tin doanh nghiệp",
                "news_short_content": "Không có tín hiệu sentiment rõ ràng.",
                "public_date": "2026-06-19T13:00:00",
            },
            {
                "news_title": "VCB tăng trần sau tin tích cực",
                "news_short_content": "Dòng tiền quay lại mạnh.",
                "public_date": "2026-06-18T15:00:01",
            },
            {
                "news_title": "VCB tăng trần sau tin tích cực",
                "news_short_content": "Dòng tiền quay lại mạnh.",
                "public_date": "2026-06-18T15:00:00",
            },
        ]
    )


@pytest.fixture
def mock_vietstock_html():
    return """
    <html><body>
      <div class="single_post post_type12 type20 mb20 channelContent">
        <div class="single_post_text">
          <div class="meta3">
            <a href="/chung-khoan/co-phieu.htm" title="Cổ phiếu">CỔ PHIẾU</a>
            <a href="/2026/06/url1.htm" title="19/06 14:27">19/06 14:27</a>
          </div>
          <h4><a class="fontbold" href="/2026/06/url1.htm" title="VN-Index bùng nổ vượt kháng cự mạnh">VN-Index bùng nổ vượt kháng cự mạnh</a></h4>
        </div>
      </div>
      <div class="single_post post_type12 type20 mb20 channelContent">
        <div class="single_post_text">
          <div class="meta3">
            <a href="/chung-khoan.htm" title="Chứng khoán">CHỨNG KHOÁN</a>
            <a href="/2026/06/url3.htm" title="15 phút trước">15 phút trước</a>
          </div>
          <h4><a class="fontbold" href="/2026/06/url3.htm" title="HPG tăng trần sau tin tích cực">HPG tăng trần sau tin tích cực</a></h4>
        </div>
      </div>
    </body></html>
    """


def test_matches_sentiment_keywords():
    agg = NewsAggregator()
    assert agg._matches_sentiment_keywords("Cổ phiếu bứt phá", None)
    assert agg._matches_sentiment_keywords(None, "Áp lực margin call gia tăng")
    assert not agg._matches_sentiment_keywords("Cập nhật họp cổ đông", "Thông tin trung tính")


def test_parse_public_date_iso():
    agg = NewsAggregator()
    assert agg._parse_public_date("2026-06-24T17:39:34") == datetime(2026, 6, 24, 17, 39, 34)


def test_parse_vietstock_time_short():
    agg = NewsAggregator()
    ref = datetime(2026, 6, 19, 15, 0, 0)
    assert agg._parse_vietstock_time("19/06 14:27", ref) == datetime(2026, 6, 19, 14, 27, 0)


def test_parse_vietstock_time_relative():
    agg = NewsAggregator()
    ref = datetime(2026, 6, 19, 15, 0, 0)
    assert agg._parse_vietstock_time("15 phút trước", ref) == datetime(2026, 6, 19, 14, 45, 0)


def test_mandatory_as_of_time_guard():
    with pytest.raises(ValueError, match="as_of_time is mandatory"):
        NewsAggregator().fetch_recent_news(as_of_time=None)


@patch.object(NewsAggregator, "_load_universe_tickers", return_value=["VCB"])
def test_vnstock_news_filters_keywords_and_pit_window(mock_universe, mock_vnstock_news_frame):
    agg = NewsAggregator()
    as_of = datetime(2026, 6, 19, 15, 0, 0)

    mock_vnstock_news_frame.attrs["next_cursor"] = None

    with patch("omega.data.vci_direct.DirectVCIClient.fetch_company_news", return_value=mock_vnstock_news_frame) as mock_company:
        news = agg._scrape_vnstock_news(as_of_time=as_of, hours_back=24)

    assert [item.ticker for item in news] == ["VCB", "VCB"]
    assert [item.timestamp for item in news] == [
        datetime(2026, 6, 19, 7, 30, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 18, 8, 0, 1, tzinfo=timezone.utc),
    ]
    as_of_utc = datetime(2026, 6, 19, 8, 0, 0, tzinfo=timezone.utc)
    assert all(item.timestamp < as_of_utc for item in news)
    assert all(item.timestamp > as_of_utc - timedelta(hours=24) for item in news)
    assert all(item.source == "vnstock" for item in news)
    assert all(isinstance(item, SentimentInput) for item in news)
    mock_universe.assert_called_once_with()
    mock_company.assert_called_once_with("VCB", page_size=100, cursor=None)


@patch.object(NewsAggregator, "_load_universe_tickers", return_value=["VCB", "HPG"])
def test_vnstock_news_continues_on_symbol_failure(mock_universe, mock_vnstock_news_frame):
    agg = NewsAggregator()
    as_of = datetime(2026, 6, 19, 15, 0, 0)

    frame = mock_vnstock_news_frame.iloc[[0]].copy()
    frame.attrs["next_cursor"] = None

    def company_side_effect(symbol, **kwargs):
        if symbol == "VCB":
            raise RuntimeError("boom")
        return frame

    with patch("omega.data.vci_direct.DirectVCIClient.fetch_company_news", side_effect=company_side_effect):
        news = agg._scrape_vnstock_news(as_of_time=as_of, hours_back=24)

    assert len(news) == 1
    assert news[0].ticker == "HPG"
    mock_universe.assert_called_once_with()


@patch("requests.get")
def test_vietstock_channel_content(mock_get, mock_vietstock_html):
    mock_resp = MagicMock()
    mock_resp.content = mock_vietstock_html.encode("utf-8")
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    as_of = datetime(2026, 6, 19, 15, 0, 0)
    news = NewsAggregator()._scrape_vietstock(as_of_time=as_of, hours_back=24, fetched_at=as_of)

    assert len(news) == 2
    assert any("VN-Index" in item.text for item in news)


@patch("requests.get")
def test_vietstock_relative_time(mock_get, mock_vietstock_html):
    mock_resp = MagicMock()
    mock_resp.content = mock_vietstock_html.encode("utf-8")
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    as_of = datetime(2026, 6, 19, 15, 0, 0)
    news = NewsAggregator()._scrape_vietstock(as_of_time=as_of, hours_back=24, fetched_at=as_of)

    relative_article = [item for item in news if "HPG" in item.text]
    assert len(relative_article) == 1
    assert relative_article[0].timestamp == datetime(2026, 6, 19, 7, 45, tzinfo=timezone.utc)


@patch.object(NewsAggregator, "_scrape_cafef", return_value=[])
@patch.object(NewsAggregator, "_scrape_tinnhanhck", return_value=[])
@patch.object(NewsAggregator, "_scrape_vneconomy", return_value=[])
@patch.object(NewsAggregator, "_scrape_vnstock_news")
@patch.object(NewsAggregator, "_scrape_vietstock")
def test_fetch_recent_news_sorts_desc(mock_vietstock, mock_vnstock, mock_vnecon, mock_tinnhanh, mock_cafef):
    as_of = datetime.now(timezone.utc)
    mock_vnstock.return_value = [
        SentimentInput(text="old", source="vnstock", timestamp=as_of - timedelta(hours=2), ticker="VCB")
    ]
    mock_vietstock.return_value = [
        SentimentInput(text="new", source="Vietstock", timestamp=as_of - timedelta(minutes=15), ticker="HPG")
    ]

    news = NewsAggregator().fetch_recent_news(as_of_time=as_of, hours_back=24)

    assert [item.text for item in news] == ["new", "old"]


@patch.object(NewsAggregator, "_scrape_cafef", return_value=[])
@patch.object(NewsAggregator, "_scrape_tinnhanhck", return_value=[])
@patch.object(NewsAggregator, "_scrape_vneconomy", return_value=[])
@patch.object(NewsAggregator, "_load_universe_tickers", return_value=[])
@patch("requests.get")
def test_empty_results_on_network_failure(mock_get, mock_universe, mock_vnecon, mock_tinnhanh, mock_cafef):
    fail_resp = MagicMock()
    fail_resp.raise_for_status = MagicMock(side_effect=Exception("Network error"))
    mock_get.return_value = fail_resp

    as_of = datetime.now(timezone.utc)
    news = NewsAggregator().fetch_recent_news(as_of_time=as_of, hours_back=24)

    assert news == []
    mock_universe.assert_called_once_with()


def test_vnstock_exception_resilience_and_html_fallback():
    agg = NewsAggregator()
    as_of = datetime.now(timezone.utc)
    fallback = [SentimentInput(text="fallback", source="Vietstock", timestamp=as_of)]
    with patch.object(NewsAggregator, "_load_universe_tickers", return_value=["VCB"]), patch("omega.data.vci_direct.DirectVCIClient.fetch_company_news", side_effect=RuntimeError("RateLimitExceeded")), patch.object(NewsAggregator, "_scrape_vietstock", return_value=fallback):
        assert agg._scrape_vnstock_news(as_of_time=as_of) == []
        assert agg._scrape_vietstock(as_of_time=as_of) == fallback


def test_fetch_recent_news_survives_vnstock_exception_and_retains_html_fallback():
    agg = NewsAggregator()
    as_of = datetime.now(timezone.utc)
    fallback = [SentimentInput(text="html fallback", source="Vietstock", timestamp=as_of - timedelta(minutes=1))]
    with patch.object(NewsAggregator, "_scrape_vnstock_news", side_effect=RuntimeError("RateLimitExceeded")), patch.object(NewsAggregator, "_scrape_vietstock", return_value=fallback), patch.object(NewsAggregator, "_scrape_cafef", return_value=[]), patch.object(NewsAggregator, "_scrape_tinnhanhck", return_value=[]), patch.object(NewsAggregator, "_scrape_vneconomy", return_value=[]):
        news = agg.fetch_recent_news(as_of_time=as_of)

    assert news == fallback


def test_utf8_stdio_config_safe():
    from omega.data.news_aggregator import _configure_utf8_stdio
    _configure_utf8_stdio()

    assert True


def test_vnstock_cursor_failure_uses_narrow_exception_contract():
    agg = NewsAggregator()
    as_of = datetime.now(timezone.utc)
    with patch.object(NewsAggregator, "_fetch_vnstock_page", side_effect=KeyboardInterrupt()):
        with pytest.raises(KeyboardInterrupt):
            agg._scrape_vnstock_news(as_of_time=as_of)


AS_OF = datetime(2026, 10, 22, 15, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
SOURCE_METHODS = {
    "vnstock": "_scrape_vnstock_news", "vietstock": "_scrape_vietstock",
    "vietcap": "_scrape_vietcap_news", "cafef": "_scrape_cafef",
    "tinnhanhck": "_scrape_tinnhanhck", "vneconomy": "_scrape_vneconomy",
}


def live_article(**changes):
    return replace(SentimentInput(
        text="VCB lợi nhuận tăng", source="CafeF", ticker="VCB",
        timestamp=AS_OF - timedelta(minutes=5), url="https://cafef.vn/vcb",
        fetched_at=AS_OF + timedelta(seconds=1),
    ), **changes)


@pytest.mark.parametrize("offset,accepted", [(-1, True), (0, True), (1, False)])
def test_session_availability_cutoff_is_inclusive(offset, accepted):
    session = AS_OF + timedelta(seconds=2)
    article = live_article(available_at=session + timedelta(microseconds=offset))
    assert NewsAggregator.classify_event_revisions([article], AS_OF) == []
    result = NewsAggregator.classify_event_revisions([article], AS_OF, fetched_at=session)
    assert result == ([article] if accepted else [])
    if accepted:
        assert article.available_at == session + timedelta(microseconds=offset)


@pytest.mark.parametrize("changes", [
    {"timestamp": AS_OF + timedelta(microseconds=1)},
    {"fetched_at": AS_OF - timedelta(hours=1)},
    {"available_at": AS_OF + timedelta(seconds=3)},
])
def test_live_cutoff_never_bypasses_publication_or_availability(changes):
    article = live_article(**changes)
    aggregator = NewsAggregator()
    assert aggregator._finalize_news([article], AS_OF, 24, {}, None, fetched_at=AS_OF + timedelta(seconds=2)) == ([], [])


def test_session_history_revision_and_future_revision_do_not_hide_eligible_event():
    session = AS_OF + timedelta(seconds=2)
    prior = live_article(fetched_at=AS_OF + timedelta(milliseconds=500))
    NewsAggregator.classify_event_revisions([prior], AS_OF, fetched_at=session)
    history = {prior.url: prior}
    revision = live_article(text="VCB điều chỉnh lợi nhuận")
    future = live_article(text="VCB tương lai", fetched_at=session + timedelta(seconds=1))
    result, events = NewsAggregator()._finalize_news([future, revision], AS_OF, 24, history, None, fetched_at=session)
    assert result == events == [revision]
    assert revision.novelty == "revision"
    assert revision.revision_of == prior.event_id
    assert revision.event_id != prior.event_id
    duplicate = live_article(text=revision.text, fetched_at=session)
    result, events = NewsAggregator()._finalize_news([duplicate], AS_OF, 24, {}, {revision.url: revision}, fetched_at=session)
    assert result == [duplicate] and events == []
    assert duplicate.novelty == "duplicate" and duplicate.event_id == revision.event_id
    invalid = live_article(text=revision.text, timestamp=AS_OF, fetched_at=AS_OF - timedelta(seconds=1))
    assert NewsAggregator()._finalize_news([invalid], AS_OF, 24, history, None, fetched_at=session) == ([], [])


@pytest.mark.parametrize("sources,skip,expected", [
    (None, False, set(SOURCE_METHODS)), (None, True, set(SOURCE_METHODS) - {"vnstock"}),
    ([], False, set()), (["vnstock"], True, set()),
    *[([name], False, {name}) for name in SOURCE_METHODS],
])
def test_source_filter_dispatches_only_selected_providers(sources, skip, expected):
    with ExitStack() as stack:
        mocks = {name: stack.enter_context(patch.object(NewsAggregator, method, return_value=[])) for name, method in SOURCE_METHODS.items()}
        universe = stack.enter_context(patch.object(NewsAggregator, "_load_universe_tickers", side_effect=AssertionError("ticker scan")))
        client = stack.enter_context(patch("omega.data.news_aggregator.VnstockClient", side_effect=AssertionError("provider initialized")))
        NewsAggregator(sources=sources, skip_vnstock=skip).fetch_recent_news(datetime.now(timezone.utc))
    assert {name for name, mock in mocks.items() if mock.called} == expected
    universe.assert_not_called()
    client.assert_not_called()


@pytest.mark.parametrize("sources", ["cafef", [None], [""], ["vci"], ["--skip-vnstock"], [float("nan")], [float("inf")], [float("-inf")], [10**13]])
def test_source_filter_rejects_malformed_identifiers_before_history_io(sources, tmp_path):
    path = tmp_path / "missing" / "history.sqlite"
    with pytest.raises(ValueError, match="sources"):
        NewsAggregator(sources=sources, event_history_path=path)
    assert not path.parent.exists()


@pytest.mark.parametrize("href", ["https://user:secret@cafef.vn/news", "https://user@cafef.vn/news", "//:secret@cafef.vn/news"])
def test_canonical_news_urls_reject_userinfo(href):
    assert NewsAggregator()._canonical_url("https://cafef.vn/", href) is None
    assert NewsAggregator()._canonical_url("https://cafef.vn/", "/news?utm_source=x") == "https://cafef.vn/news"


def test_news_fetch_errors_redact_url_credentials(caplog):
    url = "https://user:never-print-this@cafef.vn/news"
    with patch("requests.get", side_effect=requests.ConnectionError(url)):
        assert NewsAggregator()._fetch_raw(url, "cafef.vn") is None
    assert "never-print-this" not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_empty_universe_does_not_initialize_vci():
    with patch.object(NewsAggregator, "_load_universe_tickers", return_value=[]), patch("omega.data.news_aggregator.VnstockClient") as client:
        assert NewsAggregator()._scrape_vnstock_news(AS_OF) == []
    client.assert_not_called()


@pytest.mark.parametrize("status", [404, 429, 500])
def test_vietcap_http_errors_404_is_empty_other_errors_propagate(status, caplog):
    response = requests.Response()
    response.status_code = status
    response._content = b"not JSON"
    response.url = "https://api.vietcap.com.vn/api/v1/news"
    with patch("requests.get", return_value=response) as get, patch.object(response, "json", side_effect=AssertionError("unexpected JSON")) as decode:
        aggregator = NewsAggregator()
        aggregator.rate_limit_seconds = 0
        if status == 404:
            assert aggregator._scrape_vietcap_news(AS_OF) == []
            assert not [record for record in caplog.records if record.levelno >= 30]
        else:
            with pytest.raises(requests.HTTPError):
                aggregator._scrape_vietcap_news(AS_OF)
    assert get.call_count == 1
    decode.assert_not_called()


@pytest.mark.parametrize("history_on_disk", [False, True])
def test_live_fetch_keeps_post_as_of_observations_and_history(monkeypatch, tmp_path, history_on_disk):
    from omega.data import news_aggregator as module

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(AS_OF.isoformat()) + timedelta(seconds=2)

    monkeypatch.setattr(module, "datetime", Clock)
    session_as_of = Clock.fromisoformat(AS_OF.isoformat())
    path = tmp_path / "history.sqlite" if history_on_disk else None
    aggregator = NewsAggregator(sources=["cafef"], event_history_path=path)
    with patch.object(aggregator, "_scrape_cafef", side_effect=lambda *_: [live_article(
        timestamp=session_as_of - timedelta(minutes=5), fetched_at=session_as_of + timedelta(seconds=1),
    )]):
        first = aggregator.fetch_recent_news(session_as_of)
        second = aggregator.fetch_recent_news(session_as_of)
    assert len(first) == len(second) == 1
    assert first[0].available_at == AS_OF + timedelta(seconds=1)
    assert second[0].novelty == "duplicate"
    assert second[0].event_id == first[0].event_id
    assert list(aggregator._event_history) == [first[0].url]


def test_live_history_persistence_failure_rolls_back(tmp_path):
    import sqlite3

    path = tmp_path / "events.sqlite"
    aggregator = NewsAggregator(sources=["cafef"], event_history_path=path)
    now = datetime.now(timezone.utc)
    article = live_article(timestamp=now - timedelta(minutes=1), fetched_at=now)
    with patch.object(aggregator, "_scrape_cafef", return_value=[article]):
        aggregator.fetch_recent_news(now)
    before = dict(aggregator._event_history)
    persist = aggregator._persist_event_history

    def fail_after_write(connection, events):
        persist(connection, events)
        raise sqlite3.OperationalError("injected write failure")

    revision = replace(article, text="VCB revised", available_at=None)
    with patch.object(aggregator, "_scrape_cafef", return_value=[revision]), patch.object(aggregator, "_persist_event_history", side_effect=fail_after_write):
        with pytest.raises(sqlite3.OperationalError, match="injected"):
            aggregator.fetch_recent_news(now)
    assert aggregator._event_history == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM news_event_history").fetchone() == (1,)


@pytest.mark.parametrize("source", ["vnstock", "vietcap"])
def test_api_sources_record_observation_time_not_publication_cutoff(source):
    aggregator = NewsAggregator()
    aggregator.rate_limit_seconds = 0
    before = datetime.now(timezone.utc)
    with ExitStack() as stack:
        if source == "vnstock":
            frame = pd.DataFrame([{"news_title": "VCB tăng mạnh", "public_date": (AS_OF - timedelta(minutes=5)).isoformat()}])
            stack.enter_context(patch.object(aggregator, "_load_universe_tickers", return_value=["VCB"]))
            stack.enter_context(patch("omega.data.news_aggregator.VnstockClient"))
            stack.enter_context(patch.object(aggregator, "_fetch_vnstock_page", return_value=(frame, None)))
            articles = aggregator._scrape_vnstock_news(AS_OF)
        else:
            stack.enter_context(patch.object(aggregator, "_fetch_vietcap_page", return_value=([
                {"title": "VCB tăng mạnh", "published_at": (AS_OF - timedelta(minutes=5)).isoformat()},
            ], None, "hash")))
            articles = aggregator._scrape_vietcap_news(AS_OF)
    assert len(articles) == 1
    assert before <= articles[0].fetched_at <= datetime.now(timezone.utc)
    assert articles[0].fetched_at != AS_OF


def test_live_cli_forwards_source_controls(monkeypatch):
    from scripts import fetch_news_sentiment as script

    monkeypatch.setattr("sys.argv", ["fetch_news_sentiment.py", "--skip-vnstock", "--sources", "cafef", "vietstock"])
    with patch.object(script, "build_news_sentiment") as build:
        script.main()
    assert build.call_args.kwargs["skip_vnstock"] is True
    assert build.call_args.kwargs["sources"] == ["cafef", "vietstock"]


@pytest.mark.parametrize("flags", [["--sources", "vci"], ["--sources"], ["--historical", "--skip-vnstock"], ["--historical", "--sources", "cafef"]])
def test_cli_source_errors_exit_before_fetch(monkeypatch, flags):
    from scripts import fetch_news_sentiment as script

    monkeypatch.setattr("sys.argv", ["fetch_news_sentiment.py", *flags])
    with patch.object(script, "build_news_sentiment") as live, patch.object(script, "build_historical_news_sentiment") as historical:
        with pytest.raises(SystemExit) as error:
            script.main()
    assert error.value.code == 2
    live.assert_not_called()
    historical.assert_not_called()


def test_vietstock_relative_time_uses_observation_not_stale_publication_cutoff(monkeypatch):
    from omega.data import news_aggregator as module

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(AS_OF.isoformat()) + timedelta(minutes=50)

    monkeypatch.setattr(module, "datetime", Clock)
    session_as_of = Clock.fromisoformat(AS_OF.isoformat())
    response = MagicMock(content=(
        '<div class="channelContent"><h4><a class="fontbold">VCB news</a></h4>'
        '<div class="meta3"><a>source</a><a>20 phút trước</a></div></div>'
    ).encode("utf-8"))
    aggregator = NewsAggregator(sources=["vietstock"])
    with patch.object(aggregator, "_fetch_raw", return_value=response):
        assert aggregator.fetch_recent_news(session_as_of) == []
        articles = aggregator._scrape_vietstock(Clock.now())
    assert len(articles) == 1
    assert articles[0].timestamp == session_as_of + timedelta(minutes=30)
    assert articles[0].fetched_at == Clock.now()


@pytest.mark.parametrize("bad", ["now", [], float("nan"), float("inf"), float("-inf"), 10**13])
def test_invalid_session_cutoff_is_rejected(bad):
    with pytest.raises(ValueError, match="fetched_at must be datetime"):
        NewsAggregator.classify_event_revisions([live_article()], AS_OF, fetched_at=bad)


@pytest.mark.parametrize("bad", [None, "true", 1, [], float("nan")])
def test_skip_vnstock_requires_boolean(bad):
    with pytest.raises(ValueError, match="skip_vnstock must be bool"):
        NewsAggregator(skip_vnstock=bad)


@pytest.mark.parametrize("changes", [
    {"available_at": AS_OF + timedelta(seconds=3)},
    {"timestamp": AS_OF - timedelta(seconds=1), "fetched_at": AS_OF - timedelta(seconds=2)},
    {"fetched_at": AS_OF - timedelta(minutes=2)},
    {"available_at": AS_OF - timedelta(minutes=2)},
])
def test_duplicate_reinstatement_cannot_bypass_session_eligibility(changes):
    prior = live_article(fetched_at=AS_OF - timedelta(minutes=1))
    NewsAggregator.classify_event_revisions([prior], AS_OF)
    article = live_article(**changes)
    assert NewsAggregator()._finalize_news(
        [article], AS_OF, 24, {prior.url: prior}, None, fetched_at=AS_OF + timedelta(seconds=2),
    ) == ([], [])


def test_builder_rejects_ignored_source_controls_for_injected_aggregator(tmp_path):
    from scripts import fetch_news_sentiment as script

    aggregator = MagicMock()
    output = tmp_path / "news.parquet"
    with pytest.raises(ValueError, match="supplied aggregator"):
        script.build_news_sentiment(output, aggregator, listing_days={}, skip_vnstock=True)
    aggregator.fetch_recent_news.assert_not_called()
    assert not output.exists()


def test_builder_passes_source_controls_to_aggregator(tmp_path):
    from scripts import fetch_news_sentiment as script

    with patch.object(script, "NewsAggregator") as factory:
        factory.return_value.fetch_recent_news.return_value = []
        with pytest.raises(ValueError, match="zero collected articles"):
            script.build_news_sentiment(tmp_path / "news.parquet", listing_days={}, sources=["cafef"], skip_vnstock=True)
    assert factory.call_args.kwargs["sources"] == ["cafef"]
    assert factory.call_args.kwargs["skip_vnstock"] is True


@pytest.mark.parametrize("availability,fetch_delay", [
    ("absent", timedelta(days=3)),
    (None, timedelta(days=3)),
    (timedelta(hours=1), timedelta(days=3)),
    (timedelta(days=3), timedelta(days=3)),
    (timedelta(days=4), timedelta(days=3)),
    (None, timedelta(hours=1)),
    (timedelta(hours=2), timedelta(hours=1)),
    (None, timedelta(0)),
    (None, None),
    ("missing-fetch", None),
])
def test_builder_export_availability_never_precedes_observation(tmp_path, availability, fetch_delay):
    from scripts import fetch_news_sentiment as script

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return AS_OF.astimezone(tz)

    published = AS_OF - timedelta(days=5)
    article = SimpleNamespace(ticker="VCB", text="VCB lợi nhuận tăng", timestamp=published)
    if availability != "missing-fetch":
        article.fetched_at = None if fetch_delay is None else published + fetch_delay
    if availability not in ("absent", "missing-fetch"):
        article.available_at = None if availability is None else published + availability
    expected_fetch = getattr(article, "fetched_at", None) or AS_OF
    expected_available = max(
        expected_fetch, getattr(article, "available_at", None) or published + timedelta(days=1),
    )
    aggregator = MagicMock()
    aggregator.fetch_recent_news.return_value = [article]
    output = tmp_path / "news.parquet"
    with patch.object(script, "datetime", Clock):
        script.build_news_sentiment(
            output, aggregator, checkpoint_path=tmp_path / "checkpoint.json",
            quarantine_path=tmp_path / "quarantine.parquet",
        )

    table = script.pq.read_table(output)
    row = table.to_pylist()[0]
    assert table.schema == script.SCHEMA
    assert row["publish_time"] <= row["fetched_at"] <= row["available_at"]
    assert row["fetched_at"] == expected_fetch
    assert row["available_at"] == expected_available


@pytest.mark.parametrize("field", ["fetched_at", "available_at"])
@pytest.mark.parametrize("bad", ["not-a-time", float("nan"), float("inf"), float("-inf"), 10**13])
def test_builder_invalid_export_time_preserves_outputs(tmp_path, field, bad):
    from scripts import fetch_news_sentiment as script

    paths = [tmp_path / name for name in ("news.parquet", "checkpoint.json", "quarantine.parquet")]
    originals = {}
    for path in paths:
        path.write_bytes(b"prior contents")
        originals[path] = path.read_bytes()
    article = live_article()
    setattr(article, field, bad)
    aggregator = MagicMock()
    aggregator.fetch_recent_news.return_value = [article]
    with pytest.raises((TypeError, ValueError, OverflowError)):
        script.build_news_sentiment(
            paths[0], aggregator, checkpoint_path=paths[1], quarantine_path=paths[2],
        )
    assert {path: path.read_bytes() for path in paths} == originals
    assert not list(tmp_path.glob("*.tmp"))
