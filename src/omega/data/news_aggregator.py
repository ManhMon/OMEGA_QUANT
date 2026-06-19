"""
News Aggregator Module - OMEGA_QUANT Data Layer
Phase 25.2: Centralized PIT-Safe Web Scraping for Vietnamese Financial News

Provides:
- Rate-limited scraping from CafeF (RSS primary, HTML fallback) and Vietstock
- Mandatory PIT-safety (reference date is strictly required)
- Normalized output structures compatible with VSIPortfolioEngine
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CAFEF_RSS_URL = "https://cafef.vn/thi-truong-chung-khoan.rss"
CAFEF_HTML_URL = "https://cafef.vn/thi-truong-chung-khoan.chn"
VIETSTOCK_HTML_URL = "https://vietstock.vn/chung-khoan.htm"
MAX_ARTICLES_PER_SOURCE = 100
REQUEST_TIMEOUT = 15


@dataclass
class SentimentInput:
    """Input structure for sentiment analysis (PIT safe)."""
    text: str
    source: str
    timestamp: datetime
    ticker: Optional[str] = None
    weight_override: Optional[float] = None


class NewsAggregator:
    """Web scraper for Vietnamese financial news sources with strict PIT safety."""

    def __init__(self):
        self.last_request_time = {}
        self.rate_limit_seconds = 2.0
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    def _rate_limit(self, domain: str) -> None:
        if domain in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain]
            if elapsed < self.rate_limit_seconds:
                time.sleep(self.rate_limit_seconds - elapsed)
        self.last_request_time[domain] = time.time()

    def _fetch_raw(self, url: str, domain: str) -> Optional[requests.Response]:
        self._rate_limit(domain)
        try:
            response = requests.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", url, exc)
            return None

    def _fetch_html(self, url: str, domain: str) -> Optional[BeautifulSoup]:
        response = self._fetch_raw(url, domain)
        if response is None:
            return None
        return BeautifulSoup(response.content, "html.parser")

    # ── CafeF ──────────────────────────────────────────────────────

    def _scrape_cafef(self, as_of_time: datetime, hours_back: int = 24) -> List[SentimentInput]:
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")

        results = self._scrape_cafef_rss(as_of_time, hours_back)
        if not results:
            logger.info("CafeF RSS empty, falling back to HTML scraping")
            results = self._scrape_cafef_html(as_of_time, hours_back)
        return results

    def _scrape_cafef_rss(self, as_of_time: datetime, hours_back: int) -> List[SentimentInput]:
        """Primary: parse CafeF RSS feed for structured article data."""
        results = []
        response = self._fetch_raw(CAFEF_RSS_URL, "cafef.vn")
        if response is None:
            return results

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            logger.warning("CafeF RSS parse error: %s", exc)
            return results

        cutoff = as_of_time - timedelta(hours=hours_back)

        for item in root.iter("item"):
            if len(results) >= MAX_ARTICLES_PER_SOURCE:
                break
            try:
                title_el = item.find("title")
                pubdate_el = item.find("pubDate")
                if title_el is None or title_el.text is None:
                    continue

                headline = title_el.text.strip()
                if not headline:
                    continue

                timestamp = as_of_time
                if pubdate_el is not None and pubdate_el.text:
                    try:
                        vntz = timezone(timedelta(hours=7))
                        parsed = parsedate_to_datetime(pubdate_el.text.strip())
                        timestamp = parsed.astimezone(vntz).replace(tzinfo=None)
                    except Exception:
                        timestamp = as_of_time

                if timestamp > as_of_time:
                    continue
                if timestamp < cutoff:
                    continue

                results.append(SentimentInput(
                    text=headline,
                    source="CafeF",
                    timestamp=timestamp,
                ))
            except Exception as exc:
                logger.warning("CafeF RSS item error: %s", exc)
        return results

    def _scrape_cafef_html(self, as_of_time: datetime, hours_back: int) -> List[SentimentInput]:
        """Fallback: scrape CafeF HTML listing page."""
        results = []
        soup = self._fetch_html(CAFEF_HTML_URL, "cafef.vn")
        if soup is None:
            return results

        cutoff = as_of_time - timedelta(hours=hours_back)

        # Featured articles (top section)
        self._extract_cafef_featured(soup, as_of_time, cutoff, results)

        # Stream articles (main list)
        self._extract_cafef_stream(soup, as_of_time, cutoff, results)

        return results

    def _extract_cafef_featured(
        self, soup: BeautifulSoup, as_of_time: datetime,
        cutoff: datetime, results: List[SentimentInput]
    ) -> None:
        first_item = soup.find("div", class_="firstitem")
        if first_item:
            link = first_item.find("h2")
            if link:
                link = link.find("a")
            time_tag = first_item.find("p", class_="time")
            self._add_cafef_article(link, time_tag, "data-time", as_of_time, cutoff, results)

        for big_item in soup.find_all("div", class_="big"):
            if len(results) >= MAX_ARTICLES_PER_SOURCE:
                break
            link = big_item.find("h3")
            if link:
                link = link.find("a")
            time_tag = big_item.find("p", class_="time")
            self._add_cafef_article(link, time_tag, "data-time", as_of_time, cutoff, results)

    def _extract_cafef_stream(
        self, soup: BeautifulSoup, as_of_time: datetime,
        cutoff: datetime, results: List[SentimentInput]
    ) -> None:
        for tlitem in soup.find_all("div", class_="tlitem"):
            if len(results) >= MAX_ARTICLES_PER_SOURCE:
                break
            link = tlitem.find("h3")
            if link:
                link = link.find("a")
            time_tag = tlitem.find("span", class_="time")
            self._add_cafef_article(link, time_tag, "title", as_of_time, cutoff, results)

    def _add_cafef_article(
        self, link_tag, time_tag, time_attr: str,
        as_of_time: datetime, cutoff: datetime,
        results: List[SentimentInput]
    ) -> None:
        if not link_tag:
            return
        headline = (link_tag.get("title") or link_tag.get_text()).strip()
        if not headline:
            return

        timestamp = as_of_time
        if time_tag:
            raw_time = time_tag.get(time_attr) or time_tag.get_text(strip=True)
            timestamp = self._parse_cafef_time(raw_time, as_of_time)

        if timestamp > as_of_time or timestamp < cutoff:
            return

        results.append(SentimentInput(
            text=headline,
            source="CafeF",
            timestamp=timestamp,
        ))

    def _parse_cafef_time(self, time_text: str, reference: datetime) -> datetime:
        if not time_text:
            return reference
        text = time_text.strip()

        # ISO 8601 from <span title="2026-06-19T08:16:00">
        iso_match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", text)
        if iso_match:
            try:
                return datetime.strptime(iso_match.group(1), "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass

        # Featured format "DD/MM/YYYY - HH:MM"
        featured_match = re.search(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}:\d{2})", text)
        if featured_match:
            try:
                return datetime.strptime(
                    f"{featured_match.group(1)} {featured_match.group(2)}",
                    "%d/%m/%Y %H:%M"
                )
            except ValueError:
                pass

        # Relative: "X phút trước", "X giờ trước"
        text_lower = text.lower()
        minutes_match = re.search(r"(\d+)\s*phút", text_lower)
        if minutes_match:
            return reference - timedelta(minutes=int(minutes_match.group(1)))

        hours_match = re.search(r"(\d+)\s*giờ", text_lower)
        if hours_match:
            return reference - timedelta(hours=int(hours_match.group(1)))

        # Legacy: "DD/MM/YYYY HH:MM"
        if "/" in text and ":" in text:
            try:
                return datetime.strptime(text, "%d/%m/%Y %H:%M")
            except ValueError:
                pass

        return reference

    # ── Vietstock ──────────────────────────────────────────────────

    def _scrape_vietstock(self, as_of_time: datetime, hours_back: int = 24) -> List[SentimentInput]:
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")

        results = []
        soup = self._fetch_html(VIETSTOCK_HTML_URL, "vietstock.vn")
        if soup is None:
            return results

        cutoff = as_of_time - timedelta(hours=hours_back)

        for article in soup.find_all("div", class_="channelContent"):
            if len(results) >= MAX_ARTICLES_PER_SOURCE:
                break
            try:
                headline, timestamp = self._extract_vietstock_article(article, as_of_time)
                if not headline:
                    continue
                if timestamp > as_of_time or timestamp < cutoff:
                    continue

                results.append(SentimentInput(
                    text=headline,
                    source="Vietstock",
                    timestamp=timestamp,
                ))
            except Exception as exc:
                logger.warning("Vietstock article parse error: %s", exc)
        return results

    def _extract_vietstock_article(
        self, article: BeautifulSoup, as_of_time: datetime
    ) -> tuple:
        # Headline: h4 > a.fontbold
        h4_tag = article.find("h4")
        if not h4_tag:
            return None, as_of_time
        link_tag = h4_tag.find("a", class_="fontbold")
        if not link_tag:
            link_tag = h4_tag.find("a")
        if not link_tag:
            return None, as_of_time

        headline = (link_tag.get("title") or link_tag.get_text()).strip()
        if not headline:
            return None, as_of_time

        # Timestamp: second <a> inside div.meta3
        meta3 = article.find("div", class_="meta3")
        timestamp = as_of_time
        if meta3:
            meta_links = meta3.find_all("a")
            if len(meta_links) >= 2:
                time_text = meta_links[1].get("title") or meta_links[1].get_text(strip=True)
                timestamp = self._parse_vietstock_time(time_text, as_of_time)

        return headline, timestamp

    def _parse_vietstock_time(self, time_text: str, reference: datetime) -> datetime:
        if not time_text:
            return reference
        text = time_text.strip().lower()

        # Relative: "X phút trước", "X giờ trước"
        minutes_match = re.search(r"(\d+)\s*phút", text)
        if minutes_match:
            return reference - timedelta(minutes=int(minutes_match.group(1)))

        hours_match = re.search(r"(\d+)\s*giờ", text)
        if hours_match:
            return reference - timedelta(hours=int(hours_match.group(1)))

        # Short format "DD/MM HH:MM"
        short_match = re.search(r"(\d{2}/\d{2})\s+(\d{2}:\d{2})", text)
        if short_match:
            try:
                day_month = short_match.group(1)
                hhmm = short_match.group(2)
                year = reference.year
                return datetime.strptime(f"{day_month}/{year} {hhmm}", "%d/%m/%Y %H:%M")
            except ValueError:
                pass

        # Full format "DD/MM/YYYY HH:MM"
        if "/" in text and ":" in text:
            try:
                return datetime.strptime(text, "%d/%m/%Y %H:%M")
            except ValueError:
                pass

        return reference

    # ── Public API ─────────────────────────────────────────────────

    def fetch_recent_news(self, as_of_time: datetime, hours_back: int = 24) -> List[SentimentInput]:
        """Fetch recent news from all VN sources. Mandatory as_of_time for PIT safety."""
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")

        all_news = []
        logger.info("Fetching news from last %d hours as of %s...", hours_back, as_of_time)

        try:
            cafef_news = self._scrape_cafef(as_of_time, hours_back)
            all_news.extend(cafef_news)
            logger.info("CafeF: %d articles", len(cafef_news))
        except Exception as exc:
            logger.error("CafeF scraping failed: %s", exc)

        try:
            vietstock_news = self._scrape_vietstock(as_of_time, hours_back)
            all_news.extend(vietstock_news)
            logger.info("Vietstock: %d articles", len(vietstock_news))
        except Exception as exc:
            logger.error("Vietstock scraping failed: %s", exc)

        all_news.sort(key=lambda x: x.timestamp, reverse=True)
        return all_news
