"""Unit tests for PIT-safe news aggregation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from omega.data.news_aggregator import NewsAggregator, SentimentInput, _configure_utf8_stdio


def test_configure_utf8_stdio_windows_safe():
    _configure_utf8_stdio()


def test_vnstock_exception_resilience_falls_back_to_html():
    aggregator = NewsAggregator()
    with patch.object(NewsAggregator, "_load_universe_tickers", return_value=["VCB"]), patch("vnstock.Company") as company:
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

    company = MagicMock()
    company.news.return_value = mock_vnstock_news_frame
    mock_vnstock_news_frame.attrs["pagination"] = {"next_cursor": None}

    with patch("vnstock.Company", return_value=company) as mock_company:
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
    mock_company.assert_called_once_with(symbol="VCB", source="VCI")


@patch.object(NewsAggregator, "_load_universe_tickers", return_value=["VCB", "HPG"])
def test_vnstock_news_continues_on_symbol_failure(mock_universe, mock_vnstock_news_frame):
    agg = NewsAggregator()
    as_of = datetime(2026, 6, 19, 15, 0, 0)

    bad_company = MagicMock()
    bad_company.news.side_effect = RuntimeError("boom")
    good_company = MagicMock()
    good_company.news.return_value = mock_vnstock_news_frame.iloc[[0]].copy()
    good_company.news.return_value.attrs["pagination"] = {"next_cursor": None}

    def company_side_effect(symbol, source):
        assert source == "VCI"
        return bad_company if symbol == "VCB" else good_company

    with patch("vnstock.Company", side_effect=company_side_effect):
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
    news = NewsAggregator()._scrape_vietstock(as_of_time=as_of, hours_back=24)

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
    news = NewsAggregator()._scrape_vietstock(as_of_time=as_of, hours_back=24)

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
    with patch.object(NewsAggregator, "_load_universe_tickers", return_value=["VCB"]), patch("vnstock.Company", side_effect=RuntimeError("RateLimitExceeded")), patch.object(NewsAggregator, "_scrape_vietstock", return_value=fallback):
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
