"""Free RSS news scraper with point-in-time filtering."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree as ET

import requests

from omega.core.pit import to_utc_aware
from omega.core.database import Database
from omega.data.news_aggregator import infer_tickers_from_text

DEFAULT_TIMEOUT = 15
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; OMEGA_QUANT/1.0; +https://github.com/)"
RSS_FEEDS = {
    "CafeF": "https://cafef.vn/thi-truong-chung-khoan.rss",
    "VietStock": "https://vietstock.vn/RSS/chung-khoan.rss",
    "VnExpress": "https://vnexpress.net/rss/kinh-doanh.rss",
}


class FreeNewsRSSScraper:
    """Fetch RSS articles mapped to the internal news schema."""

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        database: Database | None = None,
    ) -> None:
        self.session = session or requests.Session()
        if getattr(self.session, "headers", None) is not None:
            self.session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
        self.timeout = timeout
        self.database = database

    def fetch_recent_news(self, as_of_time: datetime) -> list[dict[str, Any]]:
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")
        cutoff = to_utc_aware(as_of_time)
        articles: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for source, url in RSS_FEEDS.items():
            try:
                for article in self._fetch_feed(source, url, cutoff):
                    dedup_key = (article["url"], self._normalize_title(article["headline"]))
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    articles.append(article)
            except requests.RequestException:
                continue
        articles.sort(key=lambda item: item["public_date"], reverse=True)
        if self.database is not None:
            for article in articles:
                self.database.insert_news_article(article)
        return articles

    def _fetch_feed(self, source: str, url: str, as_of_time: datetime) -> list[dict[str, Any]]:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        cleaned_content = re.sub(b"&(?!amp;|lt;|gt;|apos;|quot;)", b"&amp;", response.content)
        items = []
        try:
            root = ET.fromstring(cleaned_content)
            raw_items = (self._map_item(source, item) for item in root.findall(".//item"))
        except ET.ParseError:
            raw_items = (
                self._map_item_text(source, match.group(1).decode("utf-8", errors="ignore"))
                for match in re.finditer(rb"<item\b[^>]*>(.*?)</item>", cleaned_content, flags=re.IGNORECASE | re.DOTALL)
            )
        for mapped in raw_items:
            if mapped is None:
                continue
            public_date = to_utc_aware(mapped["public_date"])
            if public_date > as_of_time:
                continue
            mapped["public_date"] = public_date
            mapped["available_at"] = public_date
            items.append(mapped)
        return items

    def _map_item(self, source: str, item: ET.Element) -> dict[str, Any] | None:
        headline = self._get_text(item, "title")
        public_date = self._parse_public_date(self._get_text(item, "pubDate"))
        if not headline or public_date is None:
            return None
        return {
            "source": source,
            "headline": headline,
            "news_short_content": self._clean_html(self._get_text(item, "description")),
            "public_date": public_date,
            "url": self._get_text(item, "link"),
            "metadata": {"tickers": infer_tickers_from_text(f"{headline} {self._get_text(item, 'description')}")},
        }

    def _get_text(self, item: ET.Element, tag: str) -> str:
        element = item.find(tag)
        return (element.text or "").strip() if element is not None and element.text else ""

    def _map_item_text(self, source: str, item_text: str) -> dict[str, Any] | None:
        headline = self._get_tag_text(item_text, "title")
        public_date = self._parse_public_date(self._get_tag_text(item_text, "pubDate"))
        if not headline or public_date is None:
            return None
        return {
            "source": source,
            "headline": headline,
            "news_short_content": self._clean_html(self._get_tag_text(item_text, "description")),
            "public_date": public_date,
            "url": self._get_tag_text(item_text, "link"),
            "metadata": {"tickers": infer_tickers_from_text(f"{headline} {self._get_tag_text(item_text, 'description')}")},
        }

    def _get_tag_text(self, item_text: str, tag: str) -> str:
        match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", item_text, flags=re.IGNORECASE | re.DOTALL)
        if match is None:
            return ""
        value = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", match.group(1), flags=re.DOTALL)
        return html.unescape(value).strip()

    def _parse_public_date(self, value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return None
        return to_utc_aware(parsed)

    def _normalize_title(self, value: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(value or "")).strip().lower()

    def _clean_html(self, value: str) -> str:
        if not value:
            return ""
        plain = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", html.unescape(plain)).strip()
