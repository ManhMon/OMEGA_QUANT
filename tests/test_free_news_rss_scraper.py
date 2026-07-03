from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from omega.data.news_rss_scraper import FreeNewsRSSScraper, RSS_FEEDS


def _xml_response(body: str):
    response = Mock()
    response.raise_for_status = Mock()
    response.content = body.encode("utf-8")
    return response


def test_fetch_recent_news_filters_future_articles_and_sorts_desc():
    session = Mock()
    session.get.side_effect = [
        _xml_response(
            """
            <rss><channel>
              <item>
                <title>CafeF old</title>
                <description><![CDATA[<p>Older summary</p>]]></description>
                <pubDate>Wed, 01 Jul 2026 09:00:00 +0700</pubDate>
                <link>https://cafef.vn/old</link>
              </item>
              <item>
                <title>CafeF future</title>
                <description>skip</description>
                <pubDate>Wed, 01 Jul 2026 12:30:00 +0700</pubDate>
                <link>https://cafef.vn/future</link>
              </item>
            </channel></rss>
            """
        ),
        _xml_response(
            """
            <rss><channel>
              <item>
                <title>VietStock current</title>
                <description><![CDATA[<div>Current <b>summary</b></div>]]></description>
                <pubDate>Wed, 01 Jul 2026 10:00:00 +0700</pubDate>
                <link>https://vietstock.vn/current</link>
              </item>
            </channel></rss>
            """
        ),
        _xml_response(
            """
            <rss><channel>
              <item>
                <title>VnExpress older</title>
                <description>Third summary</description>
                <pubDate>2026-07-01T01:30:00</pubDate>
                <link>https://vnexpress.net/older</link>
              </item>
            </channel></rss>
            """
        ),
    ]
    scraper = FreeNewsRSSScraper(session=session)

    articles = scraper.fetch_recent_news(as_of_time=datetime(2026, 7, 1, 4, 0, 0, tzinfo=timezone.utc))

    assert [article["headline"] for article in articles] == [
        "VietStock current",
        "CafeF old",
        "VnExpress older",
    ]
    assert articles[0]["news_short_content"] == "Current summary"
    assert articles[1]["public_date"] == datetime(2026, 7, 1, 2, 0, 0, tzinfo=timezone.utc)
    assert all(article["public_date"] <= datetime(2026, 7, 1, 4, 0, 0, tzinfo=timezone.utc) for article in articles)


def test_fetch_recent_news_requires_as_of_time():
    with pytest.raises(ValueError, match="as_of_time is mandatory"):
        FreeNewsRSSScraper().fetch_recent_news(as_of_time=None)


def test_map_item_drops_missing_required_fields():
    scraper = FreeNewsRSSScraper(session=Mock())
    item = """
    <item>
      <description>Missing title and date</description>
      <link>https://example.com</link>
    </item>
    """

    mapped = scraper._map_item("CafeF", __import__("xml.etree.ElementTree").etree.ElementTree.fromstring(item))

    assert mapped is None


def test_fetch_feed_falls_back_to_regex_for_malformed_xml():
    session = Mock()
    session.get.return_value = _xml_response(
        """
        <rss><channel>
          <item>
            <title>Alpha & Beta</title>
            <description><![CDATA[Bad token <b>kept</b>]]></description>
            <pubDate>Wed, 01 Jul 2026 09:00:00 +0700</pubDate>
            <link>https://cafef.vn/alpha</link>
          </item>
          <item>
            <title>Broken</title>
            <description>oops</description>
        </channel></rss>
        """
    )
    scraper = FreeNewsRSSScraper(session=session)

    articles = scraper._fetch_feed("CafeF", RSS_FEEDS["CafeF"], datetime(2026, 7, 1, 4, 0, 0, tzinfo=timezone.utc))

    assert articles == [
        {
            "source": "CafeF",
            "headline": "Alpha & Beta",
            "news_short_content": "Bad token kept",
            "public_date": datetime(2026, 7, 1, 2, 0, 0, tzinfo=timezone.utc),
            "available_at": datetime(2026, 7, 1, 2, 0, 0, tzinfo=timezone.utc),
            "url": "https://cafef.vn/alpha",
            "metadata": {"tickers": []},
        }
    ]


def test_init_sets_default_user_agent_header_and_cafef_url():
    session = requests.Session()

    FreeNewsRSSScraper(session=session)

    assert session.headers["User-Agent"]
    assert RSS_FEEDS["CafeF"] == "https://cafef.vn/thi-truong-chung-khoan.rss"


def test_rss_one_dead_feed_does_not_abort():
    session = Mock()
    session.get.side_effect = [requests.HTTPError("boom"), _xml_response("<rss><channel><item><title>ok</title><description>x</description><pubDate>Wed, 01 Jul 2026 09:00:00 +0700</pubDate><link>https://ok</link></item></channel></rss>"), _xml_response("<rss><channel></channel></rss>")]
    articles = FreeNewsRSSScraper(session=session).fetch_recent_news(datetime(2026, 7, 1, 4, 0, 0, tzinfo=timezone.utc))
    assert [article["headline"] for article in articles] == ["ok"]


def test_rss_dedup_by_url_and_title():
    session = Mock()
    body = "<rss><channel><item><title>Alpha</title><description>x</description><pubDate>Wed, 01 Jul 2026 09:00:00 +0700</pubDate><link>https://same</link></item></channel></rss>"
    session.get.side_effect = [_xml_response(body), _xml_response(body), _xml_response("<rss><channel></channel></rss>")]
    articles = FreeNewsRSSScraper(session=session).fetch_recent_news(datetime(2026, 7, 1, 4, 0, 0, tzinfo=timezone.utc))
    assert len(articles) == 1


def test_rss_clock_skew_rejects_future_public_date():
    session = Mock()
    session.get.side_effect = [_xml_response("<rss><channel><item><title>future</title><description>x</description><pubDate>Wed, 01 Jul 2026 13:00:00 +0700</pubDate><link>https://future</link></item></channel></rss>"), _xml_response("<rss><channel></channel></rss>"), _xml_response("<rss><channel></channel></rss>")]
    articles = FreeNewsRSSScraper(session=session).fetch_recent_news(datetime(2026, 7, 1, 4, 0, 0, tzinfo=timezone.utc))
    assert articles == []
