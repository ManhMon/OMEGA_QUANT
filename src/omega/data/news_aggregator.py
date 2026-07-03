"""PIT-safe VN news aggregation via vnstock + Vietstock."""

import json
import logging
from pathlib import Path
import re
import time
from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

VIETSTOCK_HTML_URL = "https://vietstock.vn/chung-khoan.htm"
MAX_ARTICLES_PER_SOURCE = 100
REQUEST_TIMEOUT = 15
UNIVERSE_PATH = Path(".ly_state/session/vci_universe_hsx_hnx.json")
BULLISH_KEYWORDS = {
    "tang",
    "tăng",
    "bứt phá",
    "bùng nổ",
    "đột phá",
    "vượt",
    "lãi",
    "tích cực",
    "khởi sắc",
    "hồi phục",
    "mua ròng",
    "tăng trần",
}
BEARISH_KEYWORDS = {
    "giam",
    "giảm",
    "giảm sâu",
    "bán ròng",
    "áp lực",
    "margin call",
    "lao dốc",
    "đè nặng",
    "rủi ro",
    "tiêu cực",
    "mất mốc",
    "giảm sàn",
}
COMMON_TICKERS = (
    "VNM", "FPT", "VIC", "VHM", "HPG", "MSN", "MWG",
    "TCB", "VCB", "BID", "CTG", "MBB", "ACB", "STB",
    "VNI", "SSI", "HCM", "VND", "PNJ", "REE", "DGC",
)


def infer_tickers_from_text(text: Optional[str], candidates: Optional[List[str]] = None) -> List[str]:
    if not text:
        return []
    text_upper = text.upper()
    return [ticker for ticker in (candidates or list(COMMON_TICKERS)) if ticker in text_upper]


@dataclass
class SentimentInput:
    """Input structure for sentiment analysis (PIT safe)."""
    text: str
    source: str
    timestamp: datetime
    ticker: Optional[str] = None
    weight_override: Optional[float] = None


class NewsAggregator:
    """Vietnamese financial news collector with strict PIT safety."""

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

    # ── Vnstock ─────────────────────────────────────────────────────

    def _load_universe_tickers(self) -> List[str]:
        if not UNIVERSE_PATH.exists():
            logger.warning("Universe file not found: %s", UNIVERSE_PATH)
            return []
        try:
            with UNIVERSE_PATH.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            logger.error("Failed reading universe file %s: %s", UNIVERSE_PATH, exc)
            return []
        tickers = data.get("hsx", []) + data.get("hnx", [])
        return [ticker.strip().upper() for ticker in tickers if isinstance(ticker, str) and ticker.strip()]

    def _matches_sentiment_keywords(self, title: Optional[str], summary: Optional[str]) -> bool:
        haystack = f"{title or ''} {summary or ''}".lower()
        return any(keyword in haystack for keyword in BULLISH_KEYWORDS | BEARISH_KEYWORDS)

    def _parse_public_date(self, public_date: Optional[str]) -> Optional[datetime]:
        if not public_date:
            return None
        try:
            return datetime.fromisoformat(public_date)
        except ValueError:
            logger.warning("Invalid vnstock public_date: %s", public_date)
            return None

    def _scrape_vnstock_news(self, as_of_time: datetime, hours_back: int = 24) -> List[SentimentInput]:
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")

        cutoff = as_of_time - timedelta(hours=hours_back)
        results: List[SentimentInput] = []

        try:
            from vnstock import Company
        except Exception as exc:
            logger.error("vnstock import failed: %s", exc)
            return results

        for ticker in self._load_universe_tickers():
            if len(results) >= MAX_ARTICLES_PER_SOURCE:
                break
            try:
                self._rate_limit("vnstock")
                frame = Company(symbol=ticker, source="VCI").news()
            except Exception as exc:
                logger.warning("vnstock news fetch failed for %s: %s", ticker, exc)
                continue
            if frame is None or frame.empty:
                continue

            for row in frame.to_dict(orient="records"):
                if len(results) >= MAX_ARTICLES_PER_SOURCE:
                    break
                timestamp = self._parse_public_date(row.get("public_date"))
                if timestamp is None or timestamp >= as_of_time or timestamp <= cutoff:
                    continue
                title = row.get("news_title")
                summary = row.get("news_short_content")
                if not self._matches_sentiment_keywords(title, summary):
                    continue
                text = " ".join(part.strip() for part in [title or "", summary or ""] if part and part.strip())
                if not text:
                    continue
                results.append(SentimentInput(
                    text=text,
                    source="vnstock",
                    timestamp=timestamp,
                    ticker=ticker,
                ))
        return results

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
                if timestamp >= as_of_time or timestamp <= cutoff:
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
            vnstock_news = self._scrape_vnstock_news(as_of_time, hours_back)
            all_news.extend(vnstock_news)
            logger.info("vnstock: %d articles", len(vnstock_news))
        except Exception as exc:
            logger.error("vnstock scraping failed: %s", exc)

        try:
            vietstock_news = self._scrape_vietstock(as_of_time, hours_back)
            all_news.extend(vietstock_news)
            logger.info("Vietstock: %d articles", len(vietstock_news))
        except Exception as exc:
            logger.error("Vietstock scraping failed: %s", exc)

        all_news.sort(key=lambda x: x.timestamp, reverse=True)
        return all_news
