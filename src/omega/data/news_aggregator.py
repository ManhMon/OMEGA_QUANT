"""PIT-safe VN news aggregation via vnstock, Vietstock, and Vietcap."""

import hashlib
import io
import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from dataclasses import asdict, dataclass, replace
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _configure_utf8_stdio() -> None:
    if os.name != "nt":
        return
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_stdio()

VIETSTOCK_HTML_URL = "https://vietstock.vn/chung-khoan.htm"
CAFEF_HTML_URL = "https://cafef.vn/thi-truong-chung-khoan.chn"
TINNHANHCK_HTML_URL = "https://tinnhanhchungkhoan.vn/chung-khoan/"
VNECONOMY_HTML_URL = "https://vneconomy.vn/chung-khoan.htm"
VNSTOCK_PAGE_SIZE = 100
NEWS_WORKERS = 4
NEWS_PAGE_SIZE = 200
MAX_PAGES_PER_TICKER = 10
NEWS_RATE_LIMIT_SECONDS = 0.5
VIETCAP_NEWS_API_URL = "https://api.vietcap.com.vn/market-news"
VIETCAP_PAGE_SIZE = 100
VIETCAP_HISTORICAL_START = datetime(2015, 1, 1, tzinfo=timezone.utc)
REQUEST_TIMEOUT = 15
UNIVERSE_PATH = Path(".ly_state/session/vci_universe_hsx_hnx.json")
DEFAULT_EVENT_HISTORY_PATH = Path(".ly_state/data/news_event_history.sqlite")
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
ICT = ZoneInfo("Asia/Ho_Chi_Minh")
AMBIGUOUS_TICKER_WORDS = {"HCM", "HN", "VND"}

def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone(timedelta(hours=7)))
    return value.astimezone(timezone.utc)


def infer_tickers_from_text(text: Optional[str], candidates: Optional[List[str]] = None) -> List[str]:
    if not text:
        return []
    candidate_tickers = candidates or list(COMMON_TICKERS)
    ticker_words = {match.group() for match in re.finditer(r"\b[A-Z]{3}\b", text)}
    explicit_tickers = {
        match.group(1)
        for match in re.finditer(r"(?:mã|cổ phiếu|cp)\s+([A-Z]{3})\b", text, re.IGNORECASE)
    }
    return [
        ticker for ticker in candidate_tickers
        if ticker in ticker_words and (ticker not in AMBIGUOUS_TICKER_WORDS or ticker in explicit_tickers)
    ]


@dataclass
class SentimentInput:
    """Input structure for sentiment analysis (PIT safe)."""
    text: str
    source: str
    timestamp: datetime
    ticker: Optional[str] = None
    weight_override: Optional[float] = None
    url: Optional[str] = None
    fetched_at: Optional[datetime] = None
    raw_timestamp: Optional[str] = None
    payload_sha256: Optional[str] = None
    parser_version: str = "news-v10"
    available_at: Optional[datetime] = None
    novelty: str = "new"
    revision_of: Optional[str] = None
    event_id: Optional[str] = None


class NewsAggregator:
    """Vietnamese financial news collector with strict PIT safety."""

    def __init__(
        self, max_articles_per_source: int = 100,
        event_history_path: str | Path | None = None, max_history_size: int = 5000,
    ):
        if max_articles_per_source <= 0:
            raise ValueError("max_articles_per_source must be a positive integer")
        if type(max_history_size) is not int or max_history_size <= 0:
            raise ValueError("max_history_size must be a positive integer")
        self.max_articles_per_source = max_articles_per_source
        self.max_history_size = max_history_size
        self.event_history_path = Path(event_history_path) if event_history_path is not None else None
        if self.event_history_path is not None and str(self.event_history_path) == ":memory:":
            raise ValueError("event_history_path must be a durable file")
        self.last_request_time = {}
        self.rate_limit_seconds = NEWS_RATE_LIMIT_SECONDS
        self._rate_limit_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._event_history: dict[str, SentimentInput] = {}
        if self.event_history_path is not None:
            self.event_history_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.event_history_path, timeout=15)) as connection:
                with connection:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS news_event_history ("
                        "event_id TEXT PRIMARY KEY, identity TEXT NOT NULL, available_at TEXT NOT NULL, "
                        "published_at TEXT NOT NULL, payload TEXT NOT NULL, payload_sha256 TEXT)"
                    )
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(news_event_history)")}
                    if "payload_sha256" not in columns:
                        connection.execute("ALTER TABLE news_event_history ADD COLUMN payload_sha256 TEXT")
                    connection.execute(
                        "CREATE INDEX IF NOT EXISTS news_event_history_available "
                        "ON news_event_history (available_at)"
                    )
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
        with self._rate_limit_lock:
            now = time.monotonic()
            last = self.last_request_time.get(domain, 0.0)
            elapsed = now - last
            if elapsed < self.rate_limit_seconds:
                time.sleep(self.rate_limit_seconds - elapsed)
            self.last_request_time[domain] = time.monotonic()

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

    @staticmethod
    def _payload_sha256(payload: bytes | str) -> str:
        return hashlib.sha256(payload if isinstance(payload, bytes) else payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _dedupe_key(item: SentimentInput) -> tuple[str, str, str]:
        normalized_text = "".join(
            char for char in unicodedata.normalize("NFD", item.text.casefold())
            if unicodedata.category(char) != "Mn"
        ).replace("đ", "d")
        normalized_text = re.sub(
            r"\b(?:co phieu|cong bo|nam truoc|the gioi di dong|vinamilk|truc tuyen|vietjet|masan)\b",
            "",
            normalized_text,
        )
        return (
            item.ticker or "",
            item.timestamp.isoformat(),
            " ".join(sorted(re.findall(r"\w+", normalized_text))),
        )

    @staticmethod
    def classify_event_revisions(
        items: List[SentimentInput], as_of: datetime, prior_seen: Optional[dict[str, SentimentInput]] = None
    ) -> List[SentimentInput]:
        """Annotate observable articles; retain corrections instead of discarding them."""
        if not isinstance(as_of, datetime):
            raise ValueError("as_of must be datetime")
        cutoff = _as_utc(as_of)
        NewsAggregator._validate_prior_seen(prior_seen)
        seen = {
            identity: prior for identity, prior in (prior_seen or {}).items()
            if _as_utc(prior.available_at or prior.fetched_at or prior.timestamp) <= cutoff
            and _as_utc(prior.timestamp) <= cutoff
        }
        output = []
        for item in sorted(items, key=lambda row: _as_utc(row.fetched_at or row.timestamp)):
            available = _as_utc(item.fetched_at or item.timestamp)
            if available > cutoff or _as_utc(item.timestamp) > cutoff or _as_utc(item.timestamp) > available:
                continue
            item.available_at = available
            identity = NewsAggregator._event_identity(item)
            previous = seen.get(identity)
            if previous is not None and _as_utc(previous.available_at or previous.fetched_at or previous.timestamp) > available:
                continue
            if previous is not None and not previous.event_id:
                raise ValueError("prior news event missing event_id")
            item.novelty = "new"
            item.revision_of = None
            revision = previous is not None and item.text != previous.text
            if revision:
                item.event_id = hashlib.sha256(
                    f"{previous.event_id}:{available.isoformat()}:{item.timestamp.isoformat()}:{item.text}".encode("utf-8")
                ).hexdigest()
            else:
                item.event_id = previous.event_id if previous is not None else hashlib.sha256(identity.encode("utf-8")).hexdigest()
            if previous is not None:
                if item.text == previous.text:
                    item.novelty = "duplicate"
                else:
                    item.novelty = "revision"
                    item.revision_of = previous.event_id
            if item.novelty != "duplicate":
                seen[identity] = item
                output.append(item)
        return output

    @staticmethod
    def _event_identity(item: SentimentInput) -> str:
        return item.url or f"{item.source}:{item.ticker or ''}:{NewsAggregator._dedupe_key(item)[2]}"

    @staticmethod
    def _validate_prior_seen(prior_seen: Optional[dict[str, SentimentInput]]) -> None:
        if prior_seen is not None and not isinstance(prior_seen, dict):
            raise ValueError("invalid prior news event history")
        for identity, item in (prior_seen or {}).items():
            if (not isinstance(identity, str) or not isinstance(item, SentimentInput) or item.available_at is None
                      or not item.event_id or not isinstance(item.timestamp, datetime)
                      or not isinstance(item.available_at, datetime)
                      or item.timestamp.tzinfo is None or item.timestamp.utcoffset() is None
                      or item.available_at.tzinfo is None or item.available_at.utcoffset() is None
                     or _as_utc(item.timestamp) > _as_utc(item.available_at)
                    or identity != NewsAggregator._event_identity(item)):
                raise ValueError("invalid prior news event identity or availability")

    def _load_event_history(self, connection: sqlite3.Connection, as_of: datetime) -> dict[str, SentimentInput]:
        cutoff = _as_utc(as_of).isoformat()
        rows = connection.execute(
            "SELECT identity, event_id, available_at, published_at, payload, payload_sha256 FROM news_event_history "
            "WHERE available_at <= ? AND published_at <= ? ORDER BY available_at, rowid",
            (cutoff, cutoff),
        )
        history = {}
        for identity, event_id, available_at, published_at, payload, payload_sha256 in rows:
            if not payload_sha256 or self._payload_sha256(payload) != payload_sha256:
                raise ValueError("invalid persisted news event payload digest")
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError("invalid persisted news event")
            for key in ("timestamp", "fetched_at", "available_at"):
                if data.get(key) is not None:
                    data[key] = datetime.fromisoformat(data[key])
            item = SentimentInput(**data)
            if (item.event_id != event_id or self._event_identity(item) != identity
                     or item.available_at is None or _as_utc(item.available_at).isoformat() != available_at
                     or _as_utc(item.timestamp).isoformat() != published_at
                     or _as_utc(item.timestamp) > _as_utc(item.available_at)):
                raise ValueError("invalid persisted news event identity")
            self._validate_prior_seen({identity: item})
            history[identity] = item
        return history

    def _persist_event_history(self, connection: sqlite3.Connection, events: List[SentimentInput]) -> None:
        for item in events:
            data = asdict(item)
            for key in ("timestamp", "fetched_at", "available_at"):
                if data[key] is not None:
                    data[key] = _as_utc(data[key]).isoformat()
            payload = json.dumps(data, ensure_ascii=False)
            connection.execute(
                "INSERT OR IGNORE INTO news_event_history "
                "(event_id, identity, available_at, published_at, payload, payload_sha256) VALUES (?, ?, ?, ?, ?, ?)",
                (item.event_id, self._event_identity(item), _as_utc(item.available_at).isoformat(),
                 _as_utc(item.timestamp).isoformat(), payload, self._payload_sha256(payload)),
            )
        connection.execute(
            "DELETE FROM news_event_history WHERE event_id IN ("
            "SELECT event_id FROM news_event_history ORDER BY available_at DESC, rowid DESC LIMIT -1 OFFSET ?)",
            (self.max_history_size,),
        )

    def _remember_event_history(self, events: List[SentimentInput]) -> None:
        for item in events:
            identity = self._event_identity(item)
            previous = self._event_history.get(identity)
            if previous is None or _as_utc(item.available_at) >= _as_utc(previous.available_at or previous.fetched_at or previous.timestamp):
                self._event_history[identity] = replace(item)
        # ponytail: oldest identities expire at max_history_size; durable event versions use the same cap.
        if len(self._event_history) > self.max_history_size:
            oldest = sorted(
                self._event_history,
                key=lambda identity: (
                    _as_utc(self._event_history[identity].available_at or self._event_history[identity].fetched_at
                            or self._event_history[identity].timestamp), identity,
                ),
            )[:len(self._event_history) - self.max_history_size]
            for identity in oldest:
                del self._event_history[identity]

    def _canonical_url(self, base_url: str, href: Optional[str]) -> Optional[str]:
        if not href:
            return None
        parsed = urlsplit(urljoin(base_url, href))
        base_domain = urlsplit(base_url).hostname
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or not base_domain
            or (parsed.hostname or "").lower() not in {base_domain.lower()}
            and not (parsed.hostname or "").lower().endswith(f".{base_domain.lower()}")
        ):
            return None
        query = urlencode([
            (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in {"ref", "from", "fbclid", "gclid"}
            and not key.lower().startswith("utm_")
        ], doseq=True)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))

    def _parse_html_time(self, value: Optional[str], fetched_at: datetime) -> Optional[datetime]:
        if not value:
            return None
        fetched_at = _as_utc(fetched_at)
        fetched_at_ict = fetched_at.astimezone(ICT)
        text = " ".join(value.strip().lower().split())
        relative = re.search(r"(\d+)\s*(phút|giờ)\s+trước", text)
        if relative:
            return fetched_at - timedelta(**{"minutes" if relative.group(2) == "phút" else "hours": int(relative.group(1))})
        try:
            return _as_utc(datetime.fromisoformat(text.replace("z", "+00:00")))
        except ValueError:
            pass
        for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return _as_utc(datetime.strptime(text, pattern))
            except ValueError:
                continue
        short = re.search(r"(\d{1,2}/\d{1,2})\s+(\d{1,2}:\d{2})", text)
        if short:
            try:
                timestamp = datetime.strptime(f"{short.group(1)}/{fetched_at_ict.year} {short.group(2)}", "%d/%m/%Y %H:%M")
                if _as_utc(timestamp) > fetched_at:
                    timestamp = timestamp.replace(year=timestamp.year - 1)
                return _as_utc(timestamp)
            except ValueError:
                return None
        return None

    def _scrape_html_source(self, source: str, page_url: str, domain: str, as_of_time: datetime, hours_back: int, fetched_at: Optional[datetime] = None) -> List[SentimentInput]:
        fetched_at = _as_utc(fetched_at or datetime.now(timezone.utc))
        soup = self._fetch_html(page_url, domain)
        if soup is None:
            return []
        payload_sha256 = self._payload_sha256(str(soup))
        cutoff = _as_utc(as_of_time) - timedelta(hours=hours_back)
        results, seen = [], set()
        for link in soup.select("article a[href], h1 a[href], h2 a[href], h3 a[href], h4 a[href], .item a[href], .news-item a[href]"):
            if len(results) >= self.max_articles_per_source:
                break
            headline = (link.get("title") or link.get_text(" ", strip=True)).strip()
            container = link.find_parent(["article", "li", "div"])
            time_tag = container.find("time") if container else None
            time_text = (time_tag.get("datetime") or time_tag.get_text(" ", strip=True)) if time_tag else ""
            if not time_text and container:
                date_node = container.select_one(".time, .date, .publish-time, .news-time")
                time_text = date_node.get_text(" ", strip=True) if date_node else ""
            timestamp = self._parse_html_time(time_text, fetched_at)
            url = self._canonical_url(page_url, link.get("href"))
            if not headline or timestamp is None or url is None or timestamp >= _as_utc(as_of_time) or timestamp <= cutoff:
                continue
            key = (url, headline.casefold())
            if key in seen:
                continue
            seen.add(key)
            results.append(SentimentInput(
                text=headline, source=source, timestamp=timestamp,
                ticker=(infer_tickers_from_text(headline) or [None])[0], url=url,
                fetched_at=fetched_at, raw_timestamp=time_text, payload_sha256=payload_sha256,
            ))
        return results

    def _scrape_cafef(self, as_of_time: datetime, hours_back: int = 24, fetched_at: Optional[datetime] = None) -> List[SentimentInput]:
        return self._scrape_html_source("CafeF", CAFEF_HTML_URL, "cafef.vn", as_of_time, hours_back, fetched_at)

    def _scrape_tinnhanhck(self, as_of_time: datetime, hours_back: int = 24, fetched_at: Optional[datetime] = None) -> List[SentimentInput]:
        return self._scrape_html_source("TinNhanhChungKhoan", TINNHANHCK_HTML_URL, "tinnhanhchungkhoan.vn", as_of_time, hours_back, fetched_at)

    def _scrape_vneconomy(self, as_of_time: datetime, hours_back: int = 24, fetched_at: Optional[datetime] = None) -> List[SentimentInput]:
        return self._scrape_html_source("VnEconomy", VNECONOMY_HTML_URL, "vneconomy.vn", as_of_time, hours_back, fetched_at)

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

    @staticmethod
    def _validate_vnstock_schema(frame: object) -> None:
        required = {"news_title", "public_date"}
        columns = set(getattr(frame, "columns", []))
        missing = required.difference(columns)
        if missing:
            raise ValueError(f"vnstock schema missing required columns: {sorted(missing)}")

    @staticmethod
    def _fetch_vnstock_page(company: object, cursor: Optional[str]) -> tuple[object, Optional[str]]:
        try:
            frame = company.news(cursor=cursor, limit=VNSTOCK_PAGE_SIZE, sort="public_date_desc")
        except TypeError as exc:
            raise ValueError("vnstock endpoint does not expose required server-side cursor pagination") from exc
        attrs = getattr(frame, "attrs", {})
        metadata = attrs.get("pagination") if isinstance(attrs, dict) else None
        next_cursor = metadata.get("next_cursor") if isinstance(metadata, dict) else None
        return frame, next_cursor

    def _scrape_vnstock_news(self, as_of_time: datetime, hours_back: int = 24) -> List[SentimentInput]:
        if not isinstance(as_of_time, datetime):
            raise ValueError("as_of_time is mandatory datetime for PIT safety")

        as_of_time = _as_utc(as_of_time)
        cutoff = as_of_time - timedelta(hours=hours_back)
        results: List[SentimentInput] = []

        try:
            from vnstock import Company
        except Exception as exc:
            logger.error("vnstock import failed: %s", exc)
            return results

        def fetch_ticker(ticker: str) -> List[SentimentInput]:
            ticker_results: List[SentimentInput] = []
            try:
                self._rate_limit("vnstock")
                company = Company(symbol=ticker, source="VCI")
                frame, next_cursor = self._fetch_vnstock_page(company, cursor=None)
            except Exception as exc:
                logger.warning("vnstock news fetch failed for %s: %s", ticker, exc)
                return ticker_results

            if frame is None or frame.empty:
                return ticker_results
            try:
                self._validate_vnstock_schema(frame)
            except Exception as exc:
                logger.warning("vnstock schema validation failed for %s: %s", ticker, exc)
                return ticker_results
            seen_cursors = set()
            page_count = 0
            while page_count < MAX_PAGES_PER_TICKER:
                page_count += 1
                reached_cutoff = False
                for row in frame.to_dict(orient="records"):
                    timestamp = self._parse_public_date(row.get("public_date"))
                    if timestamp is None:
                        continue
                    timestamp = _as_utc(timestamp)
                    if timestamp <= cutoff:
                        reached_cutoff = True
                        break
                    if timestamp >= as_of_time:
                        continue
                    title = row.get("news_title")
                    summary = row.get("news_short_content")
                    if self._matches_sentiment_keywords(title, summary):
                        ticker_results.append(SentimentInput(
                            text=" ".join(part.strip() for part in [title or "", summary or ""] if part and part.strip()),
                            source="vnstock", timestamp=timestamp, ticker=ticker,
                            fetched_at=as_of_time, raw_timestamp=str(row.get("public_date")),
                            payload_sha256=self._payload_sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)),
                        ))
                if next_cursor is not None and next_cursor in seen_cursors:
                    raise ValueError("vnstock cursor pagination repeated cursor")
                if reached_cutoff or next_cursor is None:
                    break
                seen_cursors.add(next_cursor)
                try:
                    frame, next_cursor = self._fetch_vnstock_page(company, cursor=next_cursor)
                    if frame is None or frame.empty:
                        break
                    self._validate_vnstock_schema(frame)
                except ValueError:
                    raise
                except Exception as exc:
                    logger.warning("vnstock cursor page validation/fetch failed for %s: %s", ticker, exc)
                    break
            return ticker_results

        universe_tickers = self._load_universe_tickers()
        with ThreadPoolExecutor(max_workers=NEWS_WORKERS) as executor:
            for ticker_results in executor.map(fetch_ticker, universe_tickers):
                results.extend(ticker_results)
                if len(results) >= self.max_articles_per_source:
                    break
        return results

    @staticmethod
    def _validate_vietcap_schema(payload: object) -> tuple[list[dict], Optional[str]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("Vietcap response missing data list")
        pagination = payload.get("pagination", {})
        if not isinstance(pagination, dict) or "next_cursor" not in pagination:
            raise ValueError("Vietcap response missing cursor pagination metadata")
        if any(not isinstance(row, dict) or "title" not in row or "published_at" not in row for row in payload["data"]):
            raise ValueError("Vietcap response missing title or published_at")
        return payload["data"], pagination["next_cursor"]

    def _fetch_vietcap_page(self, start: datetime, end: datetime, cursor: Optional[str]) -> tuple[list[dict], Optional[str], str]:
        self._rate_limit("api.vietcap.com.vn")
        response = requests.get(
            VIETCAP_NEWS_API_URL,
            headers={**self.headers, "Accept": "application/json"},
            params={
                "from": start.date().isoformat(), "to": end.date().isoformat(),
                "cursor": cursor, "limit": VIETCAP_PAGE_SIZE, "sort": "published_at_desc",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        rows, next_cursor = self._validate_vietcap_schema(response.json())
        return rows, next_cursor, self._payload_sha256(response.content)

    def _scrape_vietcap_news(self, as_of_time: datetime, hours_back: int = 24) -> List[SentimentInput]:
        """Read every server-side cursor page in the requested historical window."""
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")
        as_of_time = _as_utc(as_of_time)
        cutoff = max(as_of_time - timedelta(hours=hours_back), VIETCAP_HISTORICAL_START)
        cursor, seen_cursors, results = None, set(), []
        while True:
            rows, next_cursor, payload_sha256 = self._fetch_vietcap_page(cutoff, as_of_time, cursor)
            oldest = None
            for row in rows:
                timestamp = self._parse_public_date(row["published_at"])
                if timestamp is None:
                    continue
                timestamp = _as_utc(timestamp)
                oldest = timestamp if oldest is None else min(oldest, timestamp)
                if not cutoff <= timestamp < as_of_time:
                    continue
                title = str(row["title"]).strip()
                if not title:
                    continue
                results.append(SentimentInput(
                    text=title, source="Vietcap", timestamp=timestamp,
                    ticker=(infer_tickers_from_text(title) or [None])[0],
                    url=row.get("url"), fetched_at=as_of_time,
                    raw_timestamp=str(row["published_at"]), payload_sha256=payload_sha256,
                ))
                if len(results) >= self.max_articles_per_source:
                    break
            if len(results) >= self.max_articles_per_source:
                break
            if next_cursor is None or oldest is not None and oldest <= cutoff:
                break
            if next_cursor in seen_cursors:
                raise ValueError("Vietcap cursor pagination repeated a cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return results

    # ── Vietstock ──────────────────────────────────────────────────

    def _scrape_vietstock(
        self, as_of_time: datetime, hours_back: int = 24, fetched_at: Optional[datetime] = None
    ) -> List[SentimentInput]:
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety")

        as_of_time = _as_utc(as_of_time)
        fetched_at = _as_utc(fetched_at or as_of_time)
        results = []
        response = self._fetch_raw(VIETSTOCK_HTML_URL, "vietstock.vn")
        if response is None:
            return results
        soup = BeautifulSoup(response.content, "html.parser")
        payload_sha256 = self._payload_sha256(response.content)

        cutoff = as_of_time - timedelta(hours=hours_back)

        for article in soup.find_all("div", class_="channelContent"):
            if len(results) >= self.max_articles_per_source:
                break
            try:
                headline, timestamp = self._extract_vietstock_article(article, fetched_at)
                if not headline:
                    continue
                timestamp = _as_utc(timestamp)
                if timestamp >= as_of_time or timestamp <= cutoff:
                    continue

                results.append(SentimentInput(
                    text=headline,
                    source="Vietstock",
                    timestamp=timestamp,
                    fetched_at=fetched_at,
                    raw_timestamp=timestamp.isoformat(),
                    payload_sha256=payload_sha256,
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
                year = _as_utc(reference).astimezone(ICT).year
                timestamp = datetime.strptime(f"{day_month}/{year} {hhmm}", "%d/%m/%Y %H:%M")
                if _as_utc(timestamp) > _as_utc(reference):
                    timestamp = timestamp.replace(year=timestamp.year - 1)
                return timestamp
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

    def fetch_recent_news(
        self, as_of_time: datetime, hours_back: int = 24,
        prior_seen: Optional[dict[str, SentimentInput]] = None,
    ) -> List[SentimentInput]:
        """Fetch recent news from all VN sources. Mandatory as_of_time for PIT safety."""
        if not isinstance(as_of_time, datetime):
            raise ValueError("as_of_time is mandatory datetime for PIT safety")
        self._validate_prior_seen(prior_seen)

        as_of_time = _as_utc(as_of_time)
        fetched_at = datetime.now(timezone.utc)
        if as_of_time < fetched_at - timedelta(hours=1):
            raise ValueError("as_of_time is stale relative to fetched_at; PIT fetch refused")

        all_news = []
        logger.info("Fetching news from last %d hours as of %s...", hours_back, as_of_time)

        try:
            vnstock_news = self._scrape_vnstock_news(as_of_time, hours_back)
            all_news.extend(vnstock_news)
            logger.info("vnstock: %d articles", len(vnstock_news))
        except Exception as exc:
            logger.error("vnstock scraping failed: %s", exc)

        try:
            vietstock_news = self._scrape_vietstock(as_of_time, hours_back, fetched_at)
            all_news.extend(vietstock_news)
            logger.info("Vietstock: %d articles", len(vietstock_news))
        except Exception as exc:
            logger.error("Vietstock scraping failed: %s", exc)

        try:
            vietcap_news = self._scrape_vietcap_news(as_of_time, hours_back)
            all_news.extend(vietcap_news)
            logger.info("Vietcap: %d articles", len(vietcap_news))
        except Exception as exc:
            logger.warning("Vietcap scraping failed; continuing without Vietcap articles: %s", exc)

        def run_scraper(scraper):
            try:
                return scraper(as_of_time, hours_back, fetched_at)
            except Exception as exc:
                logger.error("HTML news scraping failed: %s", exc)
                return []

        with ThreadPoolExecutor(max_workers=NEWS_WORKERS) as executor:
            for items in executor.map(run_scraper, (self._scrape_cafef, self._scrape_tinnhanhck, self._scrape_vneconomy)):
                all_news.extend(items)

        with self._history_lock:
            if self.event_history_path is None:
                result, events = self._finalize_news(all_news, as_of_time, hours_back, self._event_history, prior_seen)
                self._remember_event_history(events)
            else:
                with closing(sqlite3.connect(self.event_history_path, timeout=15)) as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    with connection:
                        history = self._load_event_history(connection, as_of_time)
                        result, events = self._finalize_news(all_news, as_of_time, hours_back, history, prior_seen)
                        self._persist_event_history(connection, events)
                        retained = self._load_event_history(connection, as_of_time)
                self._event_history = retained
        return result

    def _finalize_news(
        self, all_news: list, as_of_time: datetime, hours_back: int,
        history: dict[str, SentimentInput], prior_seen: Optional[dict[str, SentimentInput]],
    ) -> tuple[list, list[SentimentInput]]:
        self._validate_prior_seen(prior_seen)
        seen_history = {
            identity: item for identity, item in history.items()
            if _as_utc(item.available_at or item.fetched_at or item.timestamp) <= as_of_time
            and _as_utc(item.timestamp) <= as_of_time
        }
        for identity, item in (prior_seen or {}).items():
            if _as_utc(item.available_at or item.fetched_at or item.timestamp) > as_of_time or _as_utc(item.timestamp) > as_of_time:
                continue
            previous = seen_history.get(identity)
            if previous is None or _as_utc(item.available_at or item.fetched_at or item.timestamp) >= _as_utc(
                previous.available_at or previous.fetched_at or previous.timestamp
            ):
                seen_history[identity] = item
        classified = self.classify_event_revisions(
            [item for item in all_news if isinstance(item, SentimentInput)], as_of_time, prior_seen=seen_history
        )
        for item in all_news:
            if not isinstance(item, SentimentInput) or item in classified:
                continue
            previous = seen_history.get(self._event_identity(item))
            if previous is not None and item.text == previous.text and _as_utc(item.fetched_at or item.timestamp) <= as_of_time:
                item.available_at = _as_utc(item.fetched_at or item.timestamp)
                item.novelty = "duplicate"
                item.event_id = previous.event_id
                classified.append(item)
        classified.extend(item for item in all_news if not isinstance(item, SentimentInput))
        deduplicated = []
        seen = set()
        for item in classified:
            if item.timestamp is None or item.timestamp >= as_of_time or item.timestamp <= as_of_time - timedelta(hours=hours_back):
                continue
            key = self._dedupe_key(item)
            if key in seen and getattr(item, 'novelty', None) != 'revision':
                continue
            normalized_title = key[2]
            if getattr(item, 'novelty', None) != 'revision' and any(
                not (item.ticker and existing.ticker and item.ticker != existing.ticker)
                and
                abs((item.timestamp - existing.timestamp).total_seconds()) <= timedelta(hours=48).total_seconds()
                and self._levenshtein_similarity(normalized_title, self._dedupe_key(existing)[2]) > 0.88
                for existing in deduplicated
            ):
                continue
            seen.add(key)
            deduplicated.append(item)
        events = [item for item in deduplicated if isinstance(item, SentimentInput) and item.novelty != "duplicate"]
        return sorted(deduplicated, key=lambda x: (x.timestamp, self._dedupe_key(x)), reverse=True), events

    @staticmethod
    def _levenshtein_similarity(left: str, right: str) -> float:
        if left == right:
            return 1.0
        if not left or not right:
            return 0.0
        if len(left) < len(right):
            left, right = right, left
        previous = list(range(len(right) + 1))
        for left_index, left_character in enumerate(left, start=1):
            current = [left_index]
            for right_index, right_character in enumerate(right, start=1):
                current.append(min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                ))
            previous = current
        return 1 - previous[-1] / len(left)
