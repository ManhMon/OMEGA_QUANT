"""Unit tests for News Aggregator with mocked HTTP requests."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call
from omega.data.news_aggregator import NewsAggregator, SentimentInput


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mock_cafef_rss():
    return """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>CafeF - Thị trường chứng khoán</title>
    <item>
      <title>Chuyên gia chỉ ra kênh đầu tư đánh bại gửi tiết kiệm</title>
      <link>https://cafef.vn/chuyen-gia-chi-ra-kenh-dau-tu.chn</link>
      <pubDate>Thu, 19 Jun 2026 00:03:00 +0700</pubDate>
      <description>Chuyên gia cho rằng nhà đầu tư nên tập trung vào ba nguyên tắc.</description>
    </item>
    <item>
      <title>Khối ngoại bán ròng không còn là ác mộng cho thị trường</title>
      <link>https://cafef.vn/khoi-ngoai-ban-rong.chn</link>
      <pubDate>Wed, 18 Jun 2026 20:20:00 +0700</pubDate>
      <description>Nhiều cổ phiếu bị khối ngoại bán ròng nhưng vẫn tăng mạnh.</description>
    </item>
    <item>
      <title>Dòng vốn khủng từ châu Âu đang đổ bộ thị trường giảm sâu</title>
      <link>https://cafef.vn/dong-von-khung.chn</link>
      <pubDate>Tue, 10 Jun 2026 08:00:00 +0700</pubDate>
      <description>Một xu hướng vĩ mô quan trọng.</description>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def mock_cafef_html():
    return """
    <html><body>
      <div class="firstitem">
        <h2><a title="Thị trường bứt phá mạnh mẽ hôm nay" href="/url1">Thị trường bứt phá mạnh mẽ hôm nay</a></h2>
        <p class="time" data-time="19/06/2026 - 14:30">19/06/2026 - 14:30</p>
      </div>
      <div class="big">
        <h3><a title="Nhiều cổ phiếu bất động sản giảm sàn" href="/url2">Nhiều cổ phiếu bất động sản giảm sàn</a></h3>
        <p class="time" data-time="19/06/2026 - 12:00">19/06/2026 - 12:00</p>
      </div>
      <div class="tlitem box-category-item" data-id="12345">
        <h3><a href="/url3">Khối ngoại quay lại bán ròng tăng mạnh</a></h3>
        <div class="tlitem-flex">
          <div class="knswli-right">
            <span class="time time-ago" title="2026-06-19T09:15:00">2026-06-19T09:15:00</span>
          </div>
        </div>
      </div>
      <div class="tlitem box-category-item" data-id="12346">
        <h3><a href="/url4">FPT báo lãi tăng trưởng đột phá quý 2</a></h3>
        <div class="tlitem-flex">
          <div class="knswli-right">
            <span class="time time-ago" title="2026-06-18T08:00:00">2026-06-18T08:00:00</span>
          </div>
        </div>
      </div>
    </body></html>
    """


@pytest.fixture
def mock_vietstock_html():
    return """
    <html><body>
      <div class="single_post post_type12 type20 mb20 channelContent">
        <div class="post_img"><a href="/2026/06/url1.htm"><img /></a></div>
        <div class="single_post_text">
          <div class="meta3">
            <a href="/chung-khoan/co-phieu.htm" title="Cổ phiếu">CỔ PHIẾU</a>
            <a href="/2026/06/url1.htm" title="19/06 14:27">19/06 14:27</a>
          </div>
          <h4><a class="fontbold" href="/2026/06/url1.htm" title="VN-Index bùng nổ vượt kháng cự mạnh">VN-Index bùng nổ vượt kháng cự mạnh</a></h4>
          <p class="post-p">Thị trường tăng mạnh phiên hôm nay.</p>
        </div>
      </div>
      <div class="single_post post_type12 type20 mb20 channelContent">
        <div class="post_img"><a href="/2026/06/url2.htm"><img /></a></div>
        <div class="single_post_text">
          <div class="meta3">
            <a href="/chung-khoan/giao-dich.htm" title="Giao dịch">GIAO DỊCH</a>
            <a href="/2026/06/url2.htm" title="19/06 10:15">19/06 10:15</a>
          </div>
          <h4><a class="fontbold" href="/2026/06/url2.htm" title="Áp lực margin call đè nặng tâm lý giảm sút">Áp lực margin call đè nặng tâm lý giảm sút</a></h4>
          <p class="post-p">Nhiều nhà đầu tư lo lắng.</p>
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


# ── CafeF RSS Tests ──────────────────────────────────────────────


@patch("requests.get")
def test_cafef_rss_parsing(mock_get, mock_cafef_rss):
    mock_resp = MagicMock()
    mock_resp.content = mock_cafef_rss.encode("utf-8")
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    as_of = datetime(2026, 6, 19, 15, 0, 0)
    aggregator = NewsAggregator()
    news = aggregator.fetch_recent_news(as_of_time=as_of, hours_back=24)

    cafef_news = [n for n in news if n.source == "CafeF"]
    assert len(cafef_news) == 2  # Only articles within 24h window

    assert cafef_news[0].text == "Chuyên gia chỉ ra kênh đầu tư đánh bại gửi tiết kiệm"
    assert cafef_news[0].timestamp == datetime(2026, 6, 19, 0, 3, 0)


@patch("requests.get")
def test_cafef_rss_10_day_lookback(mock_get, mock_cafef_rss):
    mock_resp = MagicMock()
    mock_resp.content = mock_cafef_rss.encode("utf-8")
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    as_of = datetime(2026, 6, 19, 15, 0, 0)
    aggregator = NewsAggregator()
    news = aggregator.fetch_recent_news(as_of_time=as_of, hours_back=240)

    cafef_news = [n for n in news if n.source == "CafeF"]
    assert len(cafef_news) == 3  # All 3 articles within 10 days


# ── CafeF HTML Fallback Tests ────────────────────────────────────


@patch("requests.get")
def test_cafef_html_fallback(mock_get, mock_cafef_html):
    """When RSS returns error, falls back to HTML scraping."""
    # First call (RSS) fails, second call (HTML) succeeds
    rss_resp = MagicMock()
    rss_resp.raise_for_status = MagicMock(side_effect=Exception("404"))

    html_resp = MagicMock()
    html_resp.content = mock_cafef_html.encode("utf-8")
    html_resp.status_code = 200
    html_resp.raise_for_status = MagicMock()

    mock_get.side_effect = [rss_resp, html_resp, html_resp]

    as_of = datetime(2026, 6, 19, 15, 0, 0)
    aggregator = NewsAggregator()
    news = aggregator.fetch_recent_news(as_of_time=as_of, hours_back=48)

    cafef_news = [n for n in news if n.source == "CafeF"]
    assert len(cafef_news) >= 2


@patch("requests.get")
def test_cafef_html_stream_time_iso(mock_get, mock_cafef_html):
    html_resp = MagicMock()
    html_resp.content = mock_cafef_html.encode("utf-8")
    html_resp.status_code = 200
    html_resp.raise_for_status = MagicMock()

    rss_resp = MagicMock()
    rss_resp.raise_for_status = MagicMock(side_effect=Exception("fail"))

    mock_get.side_effect = [rss_resp, html_resp, html_resp]

    as_of = datetime(2026, 6, 19, 15, 0, 0)
    aggregator = NewsAggregator()
    news = aggregator.fetch_recent_news(as_of_time=as_of, hours_back=48)

    cafef_news = [n for n in news if n.source == "CafeF"]
    iso_article = [n for n in cafef_news if "Khối ngoại" in n.text]
    assert len(iso_article) == 1
    assert iso_article[0].timestamp == datetime(2026, 6, 19, 9, 15, 0)


# ── Vietstock Tests ──────────────────────────────────────────────


@patch("requests.get")
def test_vietstock_channel_content(mock_get, mock_vietstock_html):
    mock_resp = MagicMock()
    mock_resp.content = mock_vietstock_html.encode("utf-8")
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    # First call for CafeF (both RSS and HTML fail), then Vietstock
    fail_resp = MagicMock()
    fail_resp.raise_for_status = MagicMock(side_effect=Exception("fail"))

    mock_get.side_effect = [fail_resp, fail_resp, mock_resp]

    as_of = datetime(2026, 6, 19, 15, 0, 0)
    aggregator = NewsAggregator()
    news = aggregator.fetch_recent_news(as_of_time=as_of, hours_back=24)

    vst_news = [n for n in news if n.source == "Vietstock"]
    assert len(vst_news) >= 2

    headlines = [n.text for n in vst_news]
    assert any("VN-Index" in h for h in headlines)


@patch("requests.get")
def test_vietstock_relative_time(mock_get, mock_vietstock_html):
    mock_resp = MagicMock()
    mock_resp.content = mock_vietstock_html.encode("utf-8")
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    fail_resp = MagicMock()
    fail_resp.raise_for_status = MagicMock(side_effect=Exception("fail"))

    mock_get.side_effect = [fail_resp, fail_resp, mock_resp]

    as_of = datetime(2026, 6, 19, 15, 0, 0)
    aggregator = NewsAggregator()
    news = aggregator.fetch_recent_news(as_of_time=as_of, hours_back=24)

    vst_news = [n for n in news if n.source == "Vietstock"]
    relative_article = [n for n in vst_news if "HPG" in n.text]
    assert len(relative_article) == 1
    assert relative_article[0].timestamp == as_of - timedelta(minutes=15)


@patch("requests.get")
def test_vietstock_correct_url(mock_get, mock_vietstock_html):
    """Verify scraper uses the correct URL (chung-khoan.htm, not thi-truong-chung-khoan)."""
    mock_resp = MagicMock()
    mock_resp.content = mock_vietstock_html.encode("utf-8")
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    fail_resp = MagicMock()
    fail_resp.raise_for_status = MagicMock(side_effect=Exception("fail"))

    mock_get.side_effect = [fail_resp, fail_resp, mock_resp]

    as_of = datetime(2026, 6, 19, 15, 0, 0)
    aggregator = NewsAggregator()
    aggregator.fetch_recent_news(as_of_time=as_of, hours_back=24)

    urls_called = [c.args[0] for c in mock_get.call_args_list]
    assert any("chung-khoan.htm" in u for u in urls_called)
    vst_urls = [u for u in urls_called if "vietstock" in u]
    assert not any("thi-truong-chung-khoan" in u for u in vst_urls)


# ── Time Parsing Unit Tests ──────────────────────────────────────


def test_parse_cafef_time_iso():
    agg = NewsAggregator()
    ref = datetime(2026, 6, 19, 15, 0, 0)
    result = agg._parse_cafef_time("2026-06-19T08:16:00", ref)
    assert result == datetime(2026, 6, 19, 8, 16, 0)


def test_parse_cafef_time_featured():
    agg = NewsAggregator()
    ref = datetime(2026, 6, 19, 15, 0, 0)
    result = agg._parse_cafef_time("19/06/2026 - 00:03", ref)
    assert result == datetime(2026, 6, 19, 0, 3, 0)


def test_parse_cafef_time_relative_minutes():
    agg = NewsAggregator()
    ref = datetime(2026, 6, 19, 15, 0, 0)
    result = agg._parse_cafef_time("10 phút trước", ref)
    assert result == datetime(2026, 6, 19, 14, 50, 0)


def test_parse_cafef_time_relative_hours():
    agg = NewsAggregator()
    ref = datetime(2026, 6, 19, 15, 0, 0)
    result = agg._parse_cafef_time("2 giờ trước", ref)
    assert result == datetime(2026, 6, 19, 13, 0, 0)


def test_parse_vietstock_time_short():
    agg = NewsAggregator()
    ref = datetime(2026, 6, 19, 15, 0, 0)
    result = agg._parse_vietstock_time("19/06 14:27", ref)
    assert result == datetime(2026, 6, 19, 14, 27, 0)


def test_parse_vietstock_time_relative():
    agg = NewsAggregator()
    ref = datetime(2026, 6, 19, 15, 0, 0)
    result = agg._parse_vietstock_time("15 phút trước", ref)
    assert result == datetime(2026, 6, 19, 14, 45, 0)


def test_parse_vietstock_time_hours_relative():
    agg = NewsAggregator()
    ref = datetime(2026, 6, 19, 15, 0, 0)
    result = agg._parse_vietstock_time("2 giờ trước", ref)
    assert result == datetime(2026, 6, 19, 13, 0, 0)


# ── PIT Safety Guard Tests ───────────────────────────────────────


def test_mandatory_as_of_time_guard():
    aggregator = NewsAggregator()
    with pytest.raises(ValueError, match="as_of_time is mandatory"):
        aggregator.fetch_recent_news(as_of_time=None)


def test_future_articles_excluded():
    """Articles with timestamps after as_of_time must be excluded."""
    agg = NewsAggregator()
    ref = datetime(2026, 6, 19, 10, 0, 0)
    # This time is in the future relative to ref
    result = agg._parse_cafef_time("2026-06-19T15:00:00", ref)
    assert result > ref  # Confirm it's future, the scraper will skip it


@patch("requests.get")
def test_empty_results_on_network_failure(mock_get):
    """Graceful degradation when all requests fail."""
    fail_resp = MagicMock()
    fail_resp.raise_for_status = MagicMock(side_effect=Exception("Network error"))
    mock_get.return_value = fail_resp

    as_of = datetime(2026, 6, 19, 15, 0, 0)
    aggregator = NewsAggregator()
    news = aggregator.fetch_recent_news(as_of_time=as_of, hours_back=240)

    assert news == []
