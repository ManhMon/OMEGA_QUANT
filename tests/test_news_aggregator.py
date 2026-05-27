"""Unit tests for News Aggregator with mocked HTTP requests."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup
from omega.data.news_aggregator import NewsAggregator, SentimentInput


@pytest.fixture
def mock_cafef_html():
    return """
    <html>
        <body>
            <h3 class="title"><a href="/url1">Thị trường bứt phá mạnh mẽ hôm nay</a></h3>
            <span class="time">10 phút trước</span>
            
            <h3 class="title"><a href="/url2">Nhiều cổ phiếu bất động sản giảm sàn</a></h3>
            <span class="time">2 giờ trước</span>
            
            <h3 class="title"><a href="/url3">Khối ngoại quay lại bán ròng</a></h3>
            <span class="time">27/05/2026 14:30</span>
        </body>
    </html>
    """


@pytest.fixture
def mock_vietstock_html():
    return """
    <html>
        <body>
            <div class="news-item">
                <a href="/url1">VN-Index bùng nổ vượt kháng cự</a>
                <span class="time">5 phút trước</span>
            </div>
            <div class="news-item">
                <a href="/url2">Áp lực margin call đè nặng tâm lý</a>
                <span class="time">1 giờ trước</span>
            </div>
        </body>
    </html>
    """


@patch('requests.get')
def test_scrape_cafef_mocked(mock_get, mock_cafef_html) -> None:
    # Setup mock response
    mock_resp = MagicMock()
    mock_resp.content = mock_cafef_html.encode('utf-8')
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp

    as_of = datetime(2026, 5, 27, 15, 0, 0)
    aggregator = NewsAggregator()
    
    news = aggregator.fetch_recent_news(as_of_time=as_of, hours_back=24)
    
    # Should fetch all 3 articles
    cafef_news = [n for n in news if n.source == 'CafeF']
    assert len(cafef_news) == 3
    
    # Check relative parsing
    assert cafef_news[0].text == "Thị trường bứt phá mạnh mẽ hôm nay"
    assert cafef_news[0].timestamp == as_of - timedelta(minutes=10)
    
    # Check absolute parsing (which is 14:30, newer than 13:00, so index 1)
    assert cafef_news[1].text == "Khối ngoại quay lại bán ròng"
    assert cafef_news[1].timestamp == datetime(2026, 5, 27, 14, 30, 0)


@patch('requests.get')
def test_scrape_vietstock_mocked(mock_get, mock_vietstock_html) -> None:
    mock_resp = MagicMock()
    mock_resp.content = mock_vietstock_html.encode('utf-8')
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp

    as_of = datetime(2026, 5, 27, 15, 0, 0)
    aggregator = NewsAggregator()
    
    news = aggregator.fetch_recent_news(as_of_time=as_of, hours_back=24)
    
    vietstock_news = [n for n in news if n.source == 'Vietstock']
    assert len(vietstock_news) == 2
    
    assert vietstock_news[0].text == "VN-Index bùng nổ vượt kháng cự"
    assert vietstock_news[0].timestamp == as_of - timedelta(minutes=5)


def test_mandatory_as_of_time_guard() -> None:
    aggregator = NewsAggregator()
    
    with pytest.raises(ValueError, match="as_of_time is mandatory"):
        aggregator.fetch_recent_news(as_of_time=None)
