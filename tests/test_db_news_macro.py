from datetime import datetime
from unittest.mock import Mock

from omega.core.database import Database, DatabaseConfig
from omega.data.news_rss_scraper import FreeNewsRSSScraper


def _make_db(tmp_path):
    db_path = tmp_path / "news_macro_test.db"
    return Database(DatabaseConfig(db_path=str(db_path), auto_init=True))


def _xml_response(body: str):
    response = Mock()
    response.raise_for_status = Mock()
    response.content = body.encode("utf-8")
    return response


def test_schema_includes_news_macro_and_sector_tables_with_indexes(tmp_path):
    db = _make_db(tmp_path)
    try:
        tables = set(db.get_tables())
        assert {"news_articles", "macro_data", "ticker_sectors"}.issubset(tables)

        news_indexes = {index["name"] for index in db.get_indexes("news_articles")}
        macro_indexes = {index["name"] for index in db.get_indexes("macro_data")}
        sector_indexes = {index["name"] for index in db.get_indexes("ticker_sectors")}

        assert "idx_news_articles_public_date" in news_indexes
        assert "idx_news_articles_source_date" in news_indexes
        assert "idx_macro_data_series_date" in macro_indexes
        assert "idx_macro_data_source_date" in macro_indexes
        assert "idx_ticker_sectors_source" in sector_indexes
        assert "idx_ticker_sectors_effective_date" in sector_indexes
    finally:
        db.close()


def test_news_macro_and_sector_helpers_insert_and_query(tmp_path):
    db = _make_db(tmp_path)
    try:
        db.insert_news_article(
            {
                "source": "CafeF",
                "headline": "Headline A",
                "news_short_content": "Summary A",
                "public_date": datetime(2026, 7, 1, 2, 0, 0),
                "url": "https://cafef.vn/a",
            }
        )
        db.insert_news_article(
            {
                "source": "VietStock",
                "headline": "Headline B",
                "news_short_content": "Summary B",
                "public_date": datetime(2026, 7, 1, 3, 0, 0),
                "url": "https://vietstock.vn/b",
            }
        )

        articles = db.get_news_articles(
            start_date=datetime(2026, 7, 1, 2, 30, 0),
            end_date=datetime(2026, 7, 1, 4, 0, 0),
        )
        assert [article["headline"] for article in articles] == ["Headline B"]

        db.insert_macro_row(
            {
                "series_key": "cpi_yoy",
                "observation_date": datetime(2026, 6, 1),
                "value": 3.2,
                "source": "gso",
            }
        )
        db.insert_macro_row(
            {
                "series_key": "cpi_yoy",
                "observation_date": datetime(2026, 7, 1),
                "value": 3.5,
                "source": "gso",
            }
        )

        macro_rows = db.get_macro_data(
            series_key="cpi_yoy",
            start_date=datetime(2026, 6, 15),
        )
        assert [(row["series_key"], row["value"]) for row in macro_rows] == [("cpi_yoy", 3.5)]

        db.insert_ticker_sector(
            {
                "ticker": "HPG",
                "sector": "Materials",
                "source": "internal",
                "effective_date": datetime(2026, 7, 1),
            }
        )

        sector = db.get_ticker_sector("HPG")
        assert sector is not None
        assert sector["sector"] == "Materials"
        assert sector["source"] == "internal"
    finally:
        db.close()


def test_rss_scraper_persists_articles_when_database_provided(tmp_path):
    session = Mock()
    session.get.side_effect = [
        _xml_response(
            """
            <rss><channel>
              <item>
                <title>CafeF old</title>
                <description>Older summary</description>
                <pubDate>Wed, 01 Jul 2026 09:00:00 +0700</pubDate>
                <link>https://cafef.vn/old</link>
              </item>
            </channel></rss>
            """
        ),
        _xml_response("<rss><channel></channel></rss>"),
        _xml_response("<rss><channel></channel></rss>"),
    ]
    db = _make_db(tmp_path)
    try:
        scraper = FreeNewsRSSScraper(session=session, database=db)

        articles = scraper.fetch_recent_news(as_of_time=datetime(2026, 7, 1, 4, 0, 0))

        stored = db.get_news_articles(source="CafeF")
        assert len(articles) == 1
        assert len(stored) == 1
        assert stored[0]["url"] == "https://cafef.vn/old"
    finally:
        db.close()
