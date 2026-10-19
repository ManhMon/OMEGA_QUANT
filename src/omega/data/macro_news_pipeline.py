"""Point-in-time-safe, provenance-preserving macro news ingestion.

Historical cohorts are frozen collection scopes, not investable universes.
Retain every supplied snapshot member across HSX, HNX, and UPCOM; collection
does not establish historical investability or historical index membership.
"""

from __future__ import annotations

import hashlib
import heapq
import html
import ipaddress
import http.client
import math
import ssl
from html.parser import HTMLParser
import json
import multiprocessing
import os
import re
import socket
import sqlite3
import tempfile
import time
from io import BytesIO
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

DEFAULT_OUTPUT_PATH = Path("data/macro_news.parquet")
SCHEMA = ["schema_version", "raw_record_id", "article_id", "revision_id", "provenance_id", "content_hash", "story_hash", "source_id", "source_name", "source_tier", "source_kind", "origin_ticker", "origin_exchange", "universe_id", "universe_version", "universe_sha256", "universe_generated_at", "universe_effective_from", "universe_effective_to", "source_record_id", "title", "summary", "body_text", "url", "canonical_url", "language", "published_at", "source_updated_at", "timestamp_precision", "available_at", "ingested_at", "raw_timestamp", "payload_sha256", "adapter_version"]
V1_SCHEMA = ["source", "title", "summary", "url", "published_at", "available_at", "ingested_at"]
DEFAULT_SOURCES = {"CafeF": ("rss", "https://cafef.vn/vi-mo-dau-tu.rss"), "Vietstock": ("rss", "https://vietstock.vn/kinh-te-vi-mo.rss"), "BaoChinhPhu": ("rss", "https://baochinhphu.vn/rss/kinh-te.rss"), "SBV": ("html", "https://www.sbv.gov.vn/webcenter/portal/vi/menu/trangchu/tin-tuc-su-kien"), "VCBS": ("html", "https://www.vcbs.com.vn/vn/Communication/Research"), "SSI": ("html", "https://www.ssi.com.vn/khach-hang-ca-nhan/bao-cao-phan-tich"), "VNDirect": ("html", "https://www.vndirect.com.vn/portal/bao-cao-phan-tich.shtml"), "VnEconomy": ("rss", "https://vneconomy.vn/rss/vi-mo.rss"), "BaoDauTu": ("rss", "https://baodautu.vn/rss/kinh-te.htm"), "TinNhanhChungKhoan": ("rss", "https://tinnhanhchungkhoan.vn/rss/vi-mo-kinh-te.rss")}
USER_AGENT = "OMEGA_QUANT macro-news pipeline/2.0"
SOURCE_TIERS = {"official", "multilateral", "institutional_research", "reputable_media", "aggregator"}
SOURCE_KINDS = {"vnstock", "rss", "html", "pdf_research", "browser", "cafef_historical"}
ADAPTERS = {"vnstock", "rss", "html", "vcbs"}
HOST_TOKEN = re.compile(r"(?:\*\.)?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")
SHA256 = re.compile(r"[0-9a-f]{64}")
PROCESS_CLEANUP_TIMEOUT_SECONDS = 0.1


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def _null(value: Any) -> Any:
    return None if pd.isna(value) else value


def _parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    value = html.unescape(value).strip()
    try:
        parsed = parsedate_to_datetime(value)
    except (IndexError, TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed = datetime.strptime(value, pattern)
                    break
                except ValueError:
                    continue
            else:
                return None
    return (parsed.replace(tzinfo=timezone(timedelta(hours=7))) if parsed.tzinfo is None else parsed).astimezone(timezone.utc)


def _utc(value: datetime) -> datetime:
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc)


def _utc_aware(value: str | None) -> datetime | None:
    """Accept only explicit UTC timestamps for universe lifecycle metadata."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0) else None


@contextmanager
def _writer_lock(path: Path, timeout: float = 10) -> Iterator[None]:
    lock_path = path.with_name(f"{path.name}.lock")
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"macro news writer lock unavailable: {lock_path}")
            time.sleep(0.05)
    try:
        os.write(handle, str(os.getpid()).encode())
        yield
    finally:
        os.close(handle)
        lock_path.unlink(missing_ok=True)


def _canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return None
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))


def _host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    host = host.lower().rstrip(".")
    return host in allowed_hosts or any(pattern.startswith("*.") and host.endswith(pattern[1:]) and host != pattern[2:] for pattern in allowed_hosts)


def _public_host(host: str) -> bool:
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except socket.gaierror:
        return False
    return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)


def _safe_response(response: Any, original_url: str, settings: Mapping[str, Any]) -> bytes:
    allowed_hosts = settings["allowed_hosts"]
    urls = [original_url, *(getattr(item, "url", "") for item in getattr(response, "history", [])), getattr(response, "url", original_url)]
    if len(urls) - 1 > 3:
        raise ValueError("source redirect cap exceeded")
    for url in urls:
        canonical = _canonical_url(url)
        host = urlsplit(canonical or "").hostname
        if not canonical or not host or not _host_allowed(host, allowed_hosts) or not _public_host(host):
            raise ValueError("source URL violates public allowlist policy")
    limit = settings["max_response_bytes"]
    content = bytearray()
    for chunk in response.iter_content(chunk_size=min(65_536, limit)):
        content.extend(chunk)
        if len(content) > limit: raise ValueError("source response exceeds byte cap")
    return bytes(content)


def _vnstock_news_worker(connection: Any, ticker: str, max_response_bytes: int) -> None:
    job = None
    try:
        ceiling = max_response_bytes * 16 + 512_000_000
        if multiprocessing.current_process().name != "MainProcess":
            if os.name != "nt":
                import resource
                _, hard = resource.getrlimit(resource.RLIMIT_AS)
                if hard != resource.RLIM_INFINITY:
                    ceiling = min(ceiling, hard)
                resource.setrlimit(resource.RLIMIT_AS, (ceiling, hard))
            else:
                import ctypes
                from ctypes import wintypes

                class IO_COUNTERS(ctypes.Structure):
                    _fields_ = [(name, ctypes.c_uint64) for name in (
                        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

                class BASIC_LIMITS(ctypes.Structure):
                    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                                ("PerJobUserTimeLimit", ctypes.c_int64),
                                ("LimitFlags", wintypes.DWORD),
                                ("MinimumWorkingSetSize", ctypes.c_size_t),
                                ("MaximumWorkingSetSize", ctypes.c_size_t),
                                ("ActiveProcessLimit", wintypes.DWORD),
                                ("Affinity", ctypes.c_size_t),
                                ("PriorityClass", wintypes.DWORD),
                                ("SchedulingClass", wintypes.DWORD)]

                class EXTENDED_LIMITS(ctypes.Structure):
                    _fields_ = [("BasicLimitInformation", BASIC_LIMITS),
                                ("IoInfo", IO_COUNTERS),
                                ("ProcessMemoryLimit", ctypes.c_size_t),
                                ("JobMemoryLimit", ctypes.c_size_t),
                                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                                ("PeakJobMemoryUsed", ctypes.c_size_t)]

                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
                kernel.CreateJobObjectW.restype = wintypes.HANDLE
                kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
                kernel.SetInformationJobObject.restype = wintypes.BOOL
                kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
                kernel.AssignProcessToJobObject.restype = wintypes.BOOL
                kernel.GetCurrentProcess.restype = wintypes.HANDLE
                kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
                job = kernel.CreateJobObjectW(None, None)
                if not job:
                    raise OSError("cannot create provider memory job")
                limits = EXTENDED_LIMITS()
                limits.BasicLimitInformation.LimitFlags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
                limits.ProcessMemoryLimit = ceiling
                if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                    raise OSError("cannot cap provider memory")
                if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
                    raise OSError("cannot assign provider memory job")
        from omega.data.vci_direct import DirectVCIClient
        frame = DirectVCIClient().fetch_company_news(ticker, page_size=100)
        if not isinstance(frame, pd.DataFrame):
            raise ValueError("vnstock news must be a DataFrame")
        if frame.memory_usage(deep=True).sum() > max_response_bytes:
            raise ValueError("vnstock response exceeds byte cap")
        connection.send((True, frame))
    except Exception as exc:
        connection.send((False, type(exc).__name__))
    finally:
        if job is not None:
            kernel.CloseHandle(job)
        connection.close()


def _stop_provider_process(process: Any) -> None:
    if process.is_alive():
        process.terminate()
        process.join(PROCESS_CLEANUP_TIMEOUT_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(PROCESS_CLEANUP_TIMEOUT_SECONDS)
    process.join(0)


@dataclass(frozen=True)
class UniverseSnapshot:
    universe_id: str
    universe_version: str
    universe_sha256: str
    generated_at: datetime
    effective_from: datetime
    effective_to: datetime | None
    members: tuple[tuple[str, str], ...]


def _parse_universe_snapshot(raw: bytes, as_of: datetime) -> UniverseSnapshot:
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("vnstock universe is not valid JSON") from exc
    required = {"schema_version", "universe_id", "universe_version", "generated_at", "effective_from", "effective_to", "members"}
    if not isinstance(data, dict) or set(data) != required or data["schema_version"] != 1:
        raise ValueError("invalid vnstock universe schema")
    parsed = {name: _utc_aware(data[name]) for name in ("generated_at", "effective_from")}
    effective_to = _utc_aware(data["effective_to"]) if data["effective_to"] else None
    if not all(parsed.values()) or (data["effective_to"] and not effective_to):
        raise ValueError("vnstock universe timestamps must be UTC-aware")
    as_of = _utc(as_of)
    if parsed["generated_at"] > as_of or parsed["effective_from"] > as_of or (effective_to and (effective_to <= parsed["effective_from"] or as_of >= effective_to)):
        raise ValueError("vnstock universe is not PIT-eligible for as_of")
    if not all(isinstance(data[key], str) and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", data[key]) for key in ("universe_id", "universe_version")):
        raise ValueError("invalid vnstock universe identity")
    members = data["members"]
    if not isinstance(members, list) or not members:
        raise ValueError("vnstock universe members must be non-empty")
    parsed_members: list[tuple[str, str]] = []
    seen: set[str] = set()
    for member in members:
        if not isinstance(member, dict) or set(member) != {"ticker", "exchange"} or not isinstance(member["ticker"], str) or not re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", member["ticker"]) or not isinstance(member["exchange"], str) or member["exchange"] not in {"HSX", "HNX", "UPCOM"} or member["ticker"] in seen:
            raise ValueError("invalid or duplicate vnstock universe member")
        seen.add(member["ticker"]); parsed_members.append((member["ticker"], member["exchange"]))
    return UniverseSnapshot(data["universe_id"], data["universe_version"], hashlib.sha256(raw).hexdigest(), parsed["generated_at"], parsed["effective_from"], effective_to, tuple(sorted(parsed_members)))


def load_universe_snapshot(path: Path | str | bytes, as_of: datetime) -> UniverseSnapshot:
    if isinstance(path, bytes):
        return _parse_universe_snapshot(path, as_of)
    candidate = Path(path)
    resolved = candidate.resolve(strict=True)
    if not candidate.is_file() or ".ly_state" in {part.lower() for part in resolved.parts}:
        raise ValueError("vnstock universe must be an explicit regular file outside .ly_state")
    return _parse_universe_snapshot(candidate.read_bytes(), as_of)


def load_source_registry(path: Path | str) -> list[dict[str, Any]]:
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("macro source registry must be an array")
    seen: set[str] = set()
    for entry in entries:
        required = {"source_id", "display_name", "tier", "kind", "enabled", "required", "discovery_url", "allowed_hosts", "adapter", "source_delay_minutes", "timestamp_policy", "max_items", "request_interval_seconds", "timeout_seconds", "max_response_bytes", "allow_pdf", "allow_browser_fallback", "disabled_reason"}
        if not isinstance(entry, dict) or set(entry) != required or not isinstance(entry["source_id"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", entry["source_id"]) or entry["source_id"] in seen or not isinstance(entry["display_name"], str) or not entry["display_name"].strip() or entry["tier"] not in SOURCE_TIERS or entry["kind"] not in SOURCE_KINDS or entry["adapter"] not in ADAPTERS or not all(isinstance(entry[key], bool) for key in ("enabled", "required", "allow_pdf", "allow_browser_fallback")) or not isinstance(entry["allowed_hosts"], list) or not entry["allowed_hosts"] or not all(isinstance(host, str) and HOST_TOKEN.fullmatch(host) for host in entry["allowed_hosts"]) or (entry["required"] and not entry["enabled"]):
            raise ValueError("invalid macro source registry entry")
        seen.add(entry["source_id"])
        if entry["timestamp_policy"] != "utc" or not isinstance(entry["source_delay_minutes"], int) or entry["source_delay_minutes"] < 0 or not isinstance(entry["max_items"], int) or entry["max_items"] < 1 or not isinstance(entry["request_interval_seconds"], (int, float)) or entry["request_interval_seconds"] < 0 or not isinstance(entry["timeout_seconds"], (int, float)) or entry["timeout_seconds"] <= 0 or not isinstance(entry["max_response_bytes"], int) or entry["max_response_bytes"] < 1 or (entry["enabled"] and not entry["discovery_url"] and (entry["kind"], entry["adapter"]) != ("vnstock", "vnstock")) or (not entry["enabled"] and not isinstance(entry["disabled_reason"], str)):
            raise ValueError("invalid macro source registry controls")
        url = _canonical_url(entry["discovery_url"]) if entry["discovery_url"] else None
        host = urlsplit(url or "").hostname
        if entry["discovery_url"] and (not url or not host or not _host_allowed(host, entry["allowed_hosts"]) or not _public_host(host)):
            raise ValueError("invalid source discovery URL")
    return entries


def _record(source_id: str, source_name: str, source_kind: str, title: str, summary: str | None, url: str | None, published_at: datetime, ingested_at: datetime, *, source_tier: str = "reputable_media", source_record_id: str | None = None, body_text: str | None = None, origin_ticker: str | None = None, origin_exchange: str | None = None, universe: UniverseSnapshot | None = None, raw_timestamp: str | None = None, payload: bytes | None = None, source_delay_minutes: int = 15, source_updated_at: datetime | None = None) -> dict[str, Any]:
    title, summary, body_text, canonical_url = _text(title), _text(summary), _text(body_text), _canonical_url(url)
    content_hash = _hash({"title": title, "summary": summary, "body_text": body_text})
    article_id = _hash({"v": 1, "source_id": source_id, "source_record_id": source_record_id or canonical_url or {"published_at": published_at, "title": title}})
    revision_id = _hash({"v": 1, "article_id": article_id, "content_hash": content_hash})
    provenance_id = _hash({"v": 1, "source_id": source_id, "origin_ticker": origin_ticker, "origin_exchange": origin_exchange})
    available_at = _utc(source_updated_at or published_at) + timedelta(minutes=source_delay_minutes)
    return {"schema_version": 2, "raw_record_id": _hash({"v": 1, "revision_id": revision_id, "provenance_id": provenance_id}), "article_id": article_id, "revision_id": revision_id, "provenance_id": provenance_id, "content_hash": content_hash, "story_hash": _hash({"title": title.lower()}), "source_id": source_id, "source_name": source_name, "source_tier": source_tier, "source_kind": source_kind, "origin_ticker": origin_ticker, "origin_exchange": origin_exchange, "universe_id": universe.universe_id if universe else None, "universe_version": universe.universe_version if universe else None, "universe_sha256": universe.universe_sha256 if universe else None, "universe_generated_at": universe.generated_at if universe else None, "universe_effective_from": universe.effective_from if universe else None, "universe_effective_to": universe.effective_to if universe else None, "source_record_id": source_record_id, "title": title, "summary": summary or None, "body_text": body_text or None, "url": url, "canonical_url": canonical_url, "language": "vi" if re.search(r"[À-ỹ]", title) else "unknown", "published_at": published_at, "source_updated_at": source_updated_at, "timestamp_precision": "second", "available_at": available_at, "ingested_at": ingested_at, "raw_timestamp": raw_timestamp or published_at.isoformat(), "payload_sha256": hashlib.sha256(payload or _canonical({"title": title, "url": url})).hexdigest(), "adapter_version": "macro_news_v2"}


def historical_news_outcome(rows: int) -> dict[str, Any]:
    """Accepted rows establish results, never verified historical absence."""
    if type(rows) is not int or rows < 0:
        raise ValueError("invalid historical accepted row count")
    return {
        "status": "results_only" if rows else "incomplete",
        "terminal_reason": "provider_results_only" if rows else "no_articles_observed_history_unverified",
        "full_history_verified": False,
    }


CAFEF_VERSION = "cafef-url-ict-v1"
CAFEF_STAMP = re.compile(r"-(?:188([0-9]{12})[0-9]{3}|([0-9]{14})(?:[0-9]{2,3})?)\.chn$")


def _cafef_url(url: str) -> str:
    try:
        if not isinstance(url, str):
            raise ValueError
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc not in {"cafef.vn", "www.cafef.vn"}
                or parts.username is not None or parts.password is not None
                or parts.fragment or "\\" in url or any(ord(c) <= 32 for c in url)):
            raise ValueError
        if parts.path != "/tim-kiem.chn" and not CAFEF_STAMP.search(parts.path):
            raise ValueError
        if parts.path == "/tim-kiem.chn":
            query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=True)
            if (set(query) not in ({"keywords"}, {"keywords", "page"})
                    or any(len(values) != 1 for values in query.values())
                    or not re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", query["keywords"][0])
                    or "page" in query and not re.fullmatch(r"[1-9][0-9]{0,2}", query["page"][0])):
                raise ValueError
        elif parts.query:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("CafeF URL policy rejected") from None
    return url


def parse_cafef_timestamp(url: str) -> datetime:
    """Decode modern/legacy CafeF ICT timestamps to second precision, not availability."""
    _cafef_url(url)
    parts = urlsplit(url)
    match = CAFEF_STAMP.search(parts.path)
    if not match:
        raise ValueError("CafeF publication timestamp missing")
    try:
        stamp = "20" + match[1] if match[1] else match[2]
        value = datetime.strptime(stamp, "%Y%m%d%H%M%S")
        return value.replace(tzinfo=timezone(timedelta(hours=7))).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError("CafeF publication timestamp invalid") from None


class _CafeFPage(HTMLParser):
    def __init__(self, page: bytes) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []
        self.active: tuple[str, str] | None = None
        self.text: list[str] = []
        self.link_title = ""
        self.title: list[str] = []
        self.meta_title = ""
        self.document_title: list[str] = []
        self.visible_text: list[str] = []
        self.empty_text: list[str] = []
        self.empty_depth = 0
        self.in_heading = self.in_title = False
        self.hidden: list[str] = []
        self.feed(page.decode("utf-8", errors="strict"))
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if tag in {"script", "style"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "div" and (self.empty_depth or fields.get("id") == "search_result_empty"):
            self.empty_depth += 1
        if tag == "a":
            self.active = (fields.get("href") or "", fields.get("rel") or "")
            self.text = []
            self.link_title = _text(fields.get("title"))
        if tag == "h1":
            self.in_heading = True
        if tag == "title":
            self.in_title = True
        if tag == "meta" and not self.meta_title and (fields.get("property") or fields.get("name") or "").casefold() == "og:title":
            self.meta_title = _text(fields.get("content"))

    def handle_endtag(self, tag: str) -> None:
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag == "div" and self.empty_depth:
            self.empty_depth -= 1
        if tag == "a" and self.active:
            self.links.append((*self.active, _text(" ".join(self.text)) or self.link_title))
            self.active = None
        if tag == "h1":
            self.in_heading = False
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.hidden:
            return
        if not self.in_title:
            self.visible_text.append(data)
            if self.empty_depth:
                self.empty_text.append(data)
        if self.active:
            self.text.append(data)
        if self.in_heading:
            self.title.append(data)
        if self.in_title:
            self.document_title.append(data)


class _CafeFConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float) -> None:
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self) -> None:
        # Pin validated DNS destination; retain original hostname for TLS SNI/certificate checks.
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class CafeFHistoricalCrawler:
    """Bounded listing traversal. Exhaustion proves provider results only, never archive completeness."""
    def __init__(self, *, max_pages: int = 500, timeout: float = 15,
                 interval: float = 1, max_bytes: int = 5_000_000,
                 sleeper: Any = time.sleep, clock: Any = None) -> None:
        for value, ceiling in ((max_pages, 500), (max_bytes, 5_000_000)):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("invalid CafeF integer bound")
        for value, floor, ceiling in ((timeout, 0, 15), (interval, 1, 60)):
            if type(value) not in {int, float} or not math.isfinite(value) or not floor <= value <= ceiling or value == 0:
                raise ValueError("invalid CafeF timing bound")
        self.max_pages, self.timeout, self.interval, self.max_bytes = max_pages, timeout, interval, max_bytes
        self.sleep = sleeper
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _request(self, url: str) -> bytes:
        _cafef_url(url)
        for attempt in range(3):
            connection = None
            try:
                self.sleep(self.interval)
                parts = urlsplit(url)
                addresses = {item[4][0] for item in socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)}
                if not addresses or not all(self._public_address(address) for address in addresses):
                    raise ValueError("CafeF DNS policy rejected")
                connection = _CafeFConnection(parts.hostname, sorted(addresses)[0], self.timeout)
                connection.request("GET", parts.path + ("?" + parts.query if parts.query else ""), headers={"User-Agent": USER_AGENT})
                response = connection.getresponse()
                if response.status in {429, 500, 502, 503, 504}:
                    if attempt < 2:
                        self.sleep(min(30, 2 ** attempt))
                        continue
                    raise ValueError("CafeF retry exhausted")
                # No implicit redirects: unknown provider routes must not widen this transport.
                if response.status != 200:
                    raise ValueError("CafeF HTTP request rejected")
                if "text/html" not in (response.getheader("Content-Type") or "").lower():
                    raise ValueError("CafeF content type rejected")
                payload = response.read(self.max_bytes + 1)
                if len(payload) > self.max_bytes:
                    raise ValueError("CafeF response exceeds byte cap")
                return payload
            except (OSError, http.client.HTTPException):
                if attempt == 2:
                    raise ValueError("CafeF transport exhausted") from None
            finally:
                if connection is not None:
                    connection.close()
        raise ValueError("CafeF request incomplete")

    @staticmethod
    def _public_address(address: str) -> bool:
        value = ipaddress.ip_address(address)
        return value.is_global and not (isinstance(value, ipaddress.IPv6Address) and
                (value.ipv4_mapped or value.sixtofour or value.teredo or value in ipaddress.ip_network("64:ff9b::/96")))

    def crawl_symbol(self, symbol: str, exchange: str, start: datetime, end: datetime) -> Iterator[list[dict[str, Any]]]:
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", symbol) or not isinstance(exchange, str) or exchange not in {"HSX", "HNX", "UPCOM"}:
            raise ValueError("invalid CafeF member")
        if any(not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None for t in (start, end)) or start > end:
            raise ValueError("invalid CafeF aware date range")
        ict = timezone(timedelta(hours=7))
        first_year, last_year = start.astimezone(ict).year, end.astimezone(ict).year
        url = f"https://cafef.vn/tim-kiem.chn?keywords={symbol}"
        pages, articles, visited = set(), set(), set()
        for _ in range(self.max_pages):
            visited.add(url)
            payload = self._request(url)
            digest = hashlib.sha256(payload).hexdigest()
            if digest in pages:
                raise ValueError("CafeF repeated listing incomplete")
            pages.add(digest)
            page = _CafeFPage(payload)
            records, next_urls, candidates = [], set(), {}
            for href, rel, title in page.links:
                candidate = urljoin(url, href)
                if "next" in rel.split() or title.casefold() in {"trang sau", "sau", "next"}:
                    _cafef_url(candidate)
                    if candidate in visited or urlsplit(candidate).path != "/tim-kiem.chn" or f"keywords={symbol}" not in urlsplit(candidate).query.split("&"):
                        raise ValueError("CafeF pagination binding rejected")
                    next_urls.add(candidate)
                if CAFEF_STAMP.search(urlsplit(candidate).path):
                    _cafef_url(candidate)
                    candidates[candidate] = candidates.get(candidate) or title
            if len(candidates) > 100 or len(next_urls) > 1:
                raise ValueError("CafeF listing bounds rejected")
            if not candidates and not next_urls and (page.empty_depth or not (
                    _text(" ".join(page.visible_text)).casefold().lstrip("﻿ ") in {
                        "không tìm thấy", "không tìm thấy tin bài", "không có gì để hiển thị", "không có gì"}
                    or _text(" ".join(page.empty_text)).casefold()
                        == f"không tìm thấy tin bài nào phù hợp với từ khóa {symbol.casefold()}")):
                raise ValueError("CafeF unknown empty listing incomplete")
            for article_url in sorted(candidates):
                stamp = CAFEF_STAMP.search(urlsplit(article_url).path)
                year = int("20" + stamp[1][:2] if stamp[1] else stamp[2][:4])
                if not first_year <= year <= last_year:
                    continue
                published = parse_cafef_timestamp(article_url)
                if article_url in articles or not start <= published <= end:
                    continue
                articles.add(article_url)
                detail = self._request(article_url)
                detail_page = _CafeFPage(detail)
                title = (_text(" ".join(detail_page.title)) or detail_page.meta_title
                         or _text(" ".join(detail_page.document_title)) or candidates[article_url])
                if not title or len(title) > 100_000:
                    raise ValueError("CafeF detail title rejected")
                fetched = self.clock()
                if not isinstance(fetched, datetime) or fetched.tzinfo is None or fetched < published:
                    raise ValueError("CafeF observation timestamp rejected")
                record = _record("cafef_historical", "CafeF", "cafef_historical", title, None, article_url, published, fetched,
                                 source_record_id=urlsplit(article_url).path, origin_ticker=symbol, origin_exchange=exchange,
                                 raw_timestamp=next(group for group in CAFEF_STAMP.search(urlsplit(article_url).path).groups() if group), payload=detail, source_delay_minutes=0)
                record["available_at"] = fetched
                record["adapter_version"] = CAFEF_VERSION
                records.append(record)
            yield records
            if not next_urls:
                return
            url = next_urls.pop()
        raise ValueError("CafeF page cap incomplete")


class RSSAdapter:
    def parse(self, source: str, url: str, content: bytes | str, ingested_at: datetime, **kwargs: Any) -> list[dict[str, Any]]:
        payload = content.encode() if isinstance(content, str) else content
        try: items = ET.fromstring(re.sub(rb"&(?!amp;|lt;|gt;|apos;|quot;)", b"&amp;", payload)).findall(".//item")
        except ET.ParseError: return []
        return [_record(source, kwargs.get("source_name", source), "rss", _text(item.findtext("title")), _text(item.findtext("description")), _text(item.findtext("link")), published, ingested_at, source_tier=kwargs.get("source_tier", "reputable_media"), raw_timestamp=item.findtext("pubDate") or item.findtext("published"), payload=payload, source_delay_minutes=kwargs.get("source_delay_minutes", 15)) for item in items if _text(item.findtext("title")) and _text(item.findtext("link")) and (published := _parse_published_at(item.findtext("pubDate") or item.findtext("published")))]


class ScraperAdapter:
    def parse(self, source: str, url: str, content: bytes | str, ingested_at: datetime, **kwargs: Any) -> list[dict[str, Any]]:
        page = content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else content; records = []
        for article in re.findall(r"<article\b[^>]*>(.*?)</article>", page, re.I | re.S):
            time_match, link_match = re.search(r"<time\b[^>]*(?:datetime=[\"']([^\"']+)[\"'])?[^>]*>(.*?)</time>", article, re.I | re.S), re.search(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", article, re.I | re.S)
            if time_match and link_match and (published := _parse_published_at(time_match.group(1) or _text(time_match.group(2)))):
                article_url = urljoin(url, html.unescape(link_match.group(1)))
                article_host = urlsplit(_canonical_url(article_url) or "").hostname
                if article_host and _host_allowed(article_host, kwargs.get("allowed_hosts", [urlsplit(url).hostname])): records.append(_record(source, kwargs.get("source_name", source), "html", _text(link_match.group(2)), _text(article), article_url, published, ingested_at, source_tier=kwargs.get("source_tier", "reputable_media"), payload=page.encode(), source_delay_minutes=kwargs.get("source_delay_minutes", 15)))
        return records


class VCBSAdapter(ScraperAdapter):
    """Narrow VCBS listing contract; no permissive fallback when the listing drifts."""
    def parse(self, source: str, url: str, content: bytes | str, ingested_at: datetime, **kwargs: Any) -> list[dict[str, Any]]:
        page = content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else content
        records = super().parse(source, url, page, ingested_at, **kwargs)
        for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>\s*<[^>]*(?:class=["\'][^"\']*(?:date|time)[^"\']*["\'])[^>]*>([^<]+)<', page, re.I):
            published = _parse_published_at(_text(match.group(3)))
            article_url = urljoin(url, html.unescape(match.group(1)))
            if published and _canonical_url(article_url) and urlsplit(article_url).hostname in {"vcbs.com.vn", "www.vcbs.com.vn"}:
                records.append(_record(source, kwargs.get("source_name", source), "html", _text(match.group(2)), None, article_url, published, ingested_at, source_tier=kwargs.get("source_tier", "reputable_media"), payload=page.encode(), source_delay_minutes=kwargs.get("source_delay_minutes", 15)))
        return list({record["raw_record_id"]: record for record in records}.values())

    @staticmethod
    def enrich(record: dict[str, Any], content: bytes, content_type: str) -> dict[str, Any]:
        if len(content) > 5_000_000:
            raise ValueError("VCBS detail exceeds byte cap")
        if "pdf" in content_type.lower() or record.get("canonical_url", "").lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader
                reader = PdfReader(BytesIO(content))
                if reader.is_encrypted or len(reader.pages) > 100:
                    raise ValueError("unsupported VCBS PDF")
                text = " ".join(page.extract_text() or "" for page in reader.pages)[:100_000]
            except ImportError as exc:
                raise ValueError("pypdf is required for VCBS PDF ingestion") from exc
        else:
            text = _text(content.decode("utf-8", errors="ignore"))[:100_000]
        if not text:
            raise ValueError("empty VCBS detail")
        record["body_text"] = text
        record["content_hash"] = _hash({"title": record["title"], "summary": record["summary"] or "", "body_text": text})
        record["revision_id"] = _hash({"v": 1, "article_id": record["article_id"], "content_hash": record["content_hash"]})
        record["raw_record_id"] = _hash({"v": 1, "revision_id": record["revision_id"], "provenance_id": record["provenance_id"]})
        return record


class VnstockNewsAdapter:
    def __init__(self, universe: UniverseSnapshot, max_items: int = 1000, request_interval_seconds: float = 0, timeout_seconds: float = 15, max_response_bytes: int = 5_000_000, source_delay_minutes: int = 15) -> None: self.universe, self.max_items, self.request_interval_seconds, self.timeout_seconds, self.max_response_bytes, self.source_delay_minutes = universe, max_items, request_interval_seconds, timeout_seconds, max_response_bytes, source_delay_minutes
    def fetch(self, cutoff: datetime, as_of: datetime, ingested_at: datetime) -> tuple[list[dict[str, Any]], list[str]]:
        cutoff, as_of = _utc(cutoff), _utc(as_of)
        if cutoff > as_of: raise ValueError("cutoff must not exceed as_of")
        records: list[tuple[tuple[Any, ...], dict[str, Any]]] = []; errors: list[str] = []
        seen: set[str] = set()
        for ticker, exchange in self.universe.members:
            try:
                time.sleep(self.request_interval_seconds)
                frame = self._fetch_page(ticker, None)
                if not isinstance(frame, pd.DataFrame): raise ValueError("vnstock news must be a DataFrame")
                if frame.memory_usage(deep=True).sum() > self.max_response_bytes: raise ValueError("vnstock response exceeds byte cap")
                if not {"news_title", "public_date"}.issubset(frame.columns): raise ValueError("vnstock news missing required columns")
                for _, item in frame.iterrows():
                    published = _parse_published_at(str(item["public_date"]))
                    if not published or not cutoff <= published <= as_of or published + timedelta(minutes=self.source_delay_minutes) > as_of: continue
                    source_url = item.get("url") or item.get("news_url"); source_id = item.get("id") or item.get("news_id")
                    record = _record("vnstock_vci", "vnstock VCI", "vnstock", str(item["news_title"]), item.get("news_short_content"), source_url, published, ingested_at, source_tier="aggregator", source_record_id=str(source_id) if pd.notna(source_id) else None, origin_ticker=ticker, origin_exchange=exchange, universe=self.universe, raw_timestamp=str(item["public_date"]), payload=_canonical(item.to_dict()), source_delay_minutes=self.source_delay_minutes)
                    if record["raw_record_id"] in seen: continue
                    key = (record["published_at"].timestamp(), str(record["source_record_id"] or ""), str(record["canonical_url"] or ""), str(record["origin_ticker"]), str(record["origin_exchange"]), record["raw_record_id"])
                    if len(records) < self.max_items:
                        heapq.heappush(records, (key, record))
                        seen.add(record["raw_record_id"])
                    elif key > records[0][0]:
                        removed = heapq.heapreplace(records, (key, record))[1]
                        seen.remove(removed["raw_record_id"])
                        seen.add(record["raw_record_id"])
            except Exception as exc: errors.append(f"{ticker}: {type(exc).__name__}")
        return [record for _, record in sorted(records, key=lambda pair: (-pair[0][0], *pair[0][1:]))], errors

    def _fetch_page(self, ticker: str, cursor: str | None = None) -> pd.DataFrame:
        context = multiprocessing.get_context()
        parent, child = context.Pipe(duplex=False)
        process = context.Process(target=_vnstock_news_worker, args=(child, ticker, self.max_response_bytes))
        process.daemon = True
        process.start()
        child.close()
        try:
            try:
                has_response = parent.poll(self.timeout_seconds)
            except BrokenPipeError as exc:
                raise TimeoutError("vnstock request exceeds timeout") from exc
            if not has_response:
                raise TimeoutError("vnstock request exceeds timeout")
            success, result = parent.recv()
            if not success:
                raise RuntimeError(result)
            return result
        finally:
            parent.close()
            _stop_provider_process(process)


class MacroNewsPipeline:
    def __init__(self, session: requests.Session | Any | None = None, sources: Mapping[str, tuple[str, str]] | None = None, timeout: int = 15, source_settings: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.session = session or requests.Session(); self.sources = dict(DEFAULT_SOURCES if sources is None else sources); self.timeout = timeout
        self.source_settings = dict(source_settings or {})
        self.source_health: dict[str, dict[str, Any]] = {}
        if getattr(self.session, "headers", None) is not None: self.session.headers.setdefault("User-Agent", USER_AGENT)
    def fetch(self, cutoff: datetime | None = None, as_of: datetime | None = None) -> pd.DataFrame:
        if (cutoff is None) != (as_of is None): raise ValueError("cutoff and as_of must be supplied together")
        if cutoff is not None and (cutoff := _utc(cutoff)) > (as_of := _utc(as_of)): raise ValueError("cutoff must not exceed as_of")
        ingested_at = datetime.now(timezone.utc); records: list[dict[str, Any]] = []
        for source, (kind, url) in self.sources.items():
            started = time.monotonic()
            try:
                settings = self.source_settings.get(source, {})
                host = urlsplit(url).hostname or ""
                allowed_hosts = settings.get("allowed_hosts", [])
                if not allowed_hosts or not _host_allowed(host, allowed_hosts) or not _public_host(host): raise ValueError("source discovery host violates public allowlist policy")
                response = self.session.get(url, timeout=settings.get("timeout_seconds", self.timeout)); response.raise_for_status()
                content = _safe_response(response, url, settings)
                adapter = RSSAdapter() if kind == "rss" else VCBSAdapter() if source in {"VCBS", "VCBS Research", "vcbs_research"} else ScraperAdapter()
                parsed = adapter.parse(source, url, content, ingested_at, source_name=settings.get("display_name", source), source_tier=settings.get("tier", "reputable_media"), source_delay_minutes=settings.get("source_delay_minutes", 15), allowed_hosts=allowed_hosts)[:settings.get("max_items", None)]
                if isinstance(adapter, VCBSAdapter):
                    for record in parsed:
                        detail = self.session.get(record["canonical_url"], timeout=settings.get("timeout_seconds", self.timeout))
                        detail.raise_for_status()
                        adapter.enrich(record, _safe_response(detail, record["canonical_url"], settings), getattr(detail, "headers", {}).get("Content-Type", ""))
                accepted = [record for record in parsed if cutoff is None or cutoff <= record["published_at"] <= as_of and record["available_at"] <= as_of]
                records.extend(accepted)
                self.source_health[source] = {"status": "healthy" if accepted else "healthy_empty", "attempts": 1, "duration_seconds": round(time.monotonic() - started, 3), "accepted": len(accepted), "rejected": len(parsed) - len(accepted)}
            except Exception as exc:
                self.source_health[source] = {"status": "failed", "attempts": 1, "duration_seconds": round(time.monotonic() - started, 3), "accepted": 0, "rejected": 0, "error": type(exc).__name__}
        return self._frame(records)
    @staticmethod
    def _frame(records: list[dict[str, Any]]) -> pd.DataFrame:
        frame = pd.DataFrame(records, columns=SCHEMA); MacroNewsPipeline._validate(frame); return frame.sort_values(["published_at", "raw_record_id"]).reset_index(drop=True) if not frame.empty else frame
    def run(self, output_path: Path | str = DEFAULT_OUTPUT_PATH) -> pd.DataFrame: return self.persist(self.fetch(), output_path)
    @staticmethod
    def persist(incoming: pd.DataFrame, output_path: Path | str) -> pd.DataFrame:
        output_path = Path(output_path); output_path.parent.mkdir(parents=True, exist_ok=True)
        MacroNewsPipeline._validate(incoming)
        with _writer_lock(output_path):
            previous = pq.ParquetFile(output_path) if output_path.exists() else None
            with tempfile.NamedTemporaryFile(dir=output_path.parent, suffix=".parquet", delete=False) as handle: temporary = Path(handle.name)
            try:
                with tempfile.TemporaryDirectory(dir=output_path.parent) as directory:
                    with closing(sqlite3.connect(str(Path(directory) / "ids.sqlite"))) as ids:
                        ids.execute("CREATE TABLE seen (id TEXT PRIMARY KEY)")
                        writer = None
                        try:
                            def write_chunk(chunk: pd.DataFrame) -> None:
                                nonlocal writer
                                MacroNewsPipeline._validate(chunk)
                                keep = []
                                for record_id in chunk["raw_record_id"]:
                                    keep.append(ids.execute("INSERT OR IGNORE INTO seen VALUES (?)", (record_id,)).rowcount == 1)
                                if any(keep):
                                    if writer is None:
                                        writer = pq.ParquetWriter(temporary, pa.Table.from_pandas(chunk.loc[keep], preserve_index=False).schema)
                                    writer.write_table(pa.Table.from_pandas(chunk.loc[keep], schema=writer.schema, preserve_index=False))

                            if previous is not None:
                                legacy = list(previous.schema_arrow.names) == V1_SCHEMA
                                for batch in previous.iter_batches(batch_size=256):
                                    chunk = batch.to_pandas()
                                    write_chunk(MacroNewsPipeline._migrate_v1(chunk) if legacy else chunk)
                            write_chunk(incoming)
                            if writer is None:
                                writer = pq.ParquetWriter(temporary, pa.Table.from_pandas(incoming, preserve_index=False).schema)
                        finally:
                            if writer is not None: writer.close()
                if previous is not None:
                    previous.close()
                    previous = None
                os.replace(temporary, output_path)
            finally:
                if previous is not None: previous.close()
                temporary.unlink(missing_ok=True)
        return incoming
    @staticmethod
    def _migrate_v1(frame: pd.DataFrame) -> pd.DataFrame:
        if list(frame.columns) != V1_SCHEMA: raise ValueError("Invalid macro news store schema")
        records = []
        for row in frame.itertuples(index=False):
            source_name = str(row.source)
            source_id = re.sub(r"[^a-z0-9_]+", "_", source_name.lower()).strip("_")
            record = _record(source_id, source_name, "rss", str(row.title), row.summary, row.url, pd.Timestamp(row.published_at).to_pydatetime(), pd.Timestamp(row.ingested_at).to_pydatetime())
            record["available_at"] = pd.Timestamp(row.available_at).to_pydatetime()
            records.append(record)
        return MacroNewsPipeline._frame(records)
    @staticmethod
    def _validate(frame: pd.DataFrame) -> None:
        if list(frame.columns) != SCHEMA: raise ValueError("Invalid macro news store schema")
        if frame.empty: return
        dates = {column: pd.to_datetime(frame[column], utc=True, errors="coerce") for column in ("published_at", "available_at", "ingested_at")}
        hashes = ("raw_record_id", "article_id", "revision_id", "provenance_id", "content_hash", "story_hash", "payload_sha256")
        required_text = ("source_id", "source_name", "source_tier", "source_kind", "title", "language", "timestamp_precision", "adapter_version")
        vnstock = frame["source_kind"] == "vnstock"
        if (frame["schema_version"] != 2).any() or any(value.isna().any() for value in dates.values()) or any(frame[column].isna().any() or not frame[column].map(lambda value: isinstance(value, str) and bool(SHA256.fullmatch(value))).all() for column in hashes) or any(frame[column].isna().any() or not frame[column].map(lambda value: isinstance(value, str) and bool(value.strip())).all() for column in required_text) or not frame["source_id"].map(lambda value: bool(re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value))).all() or not frame["source_tier"].isin(SOURCE_TIERS).all() or not frame["source_kind"].isin(SOURCE_KINDS).all() or not frame["language"].isin({"vi", "en", "unknown"}).all() or not frame["timestamp_precision"].isin({"second", "minute", "date"}).all() or frame["raw_record_id"].duplicated().any() or (vnstock & (~frame["origin_ticker"].map(lambda value: isinstance(value, str) and bool(re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", value))) | ~frame["origin_exchange"].isin({"HSX", "HNX", "UPCOM"}) | frame[["universe_id", "universe_version", "universe_sha256", "universe_generated_at", "universe_effective_from"]].isna().any(axis=1))).any() or ((~vnstock & (frame["source_kind"] != "cafef_historical")) & frame[["origin_ticker", "origin_exchange", "universe_id", "universe_version", "universe_sha256", "universe_generated_at", "universe_effective_from", "universe_effective_to"]].notna().any(axis=1)).any(): raise ValueError("Invalid macro news records")
        historical = frame["source_kind"] == "cafef_historical"
        if historical.any():
            rows = frame.loc[historical]
            if (not rows["origin_ticker"].map(lambda value: isinstance(value, str) and bool(re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", value))).all()
                    or not rows["origin_exchange"].isin({"HSX", "HNX", "UPCOM"}).all()
                    or rows[["universe_id", "universe_version", "universe_sha256", "universe_generated_at", "universe_effective_from", "universe_effective_to"]].notna().any().any()
                    or not (rows["adapter_version"] == CAFEF_VERSION).all()
                    or not (dates["available_at"][historical] >= dates["ingested_at"][historical]).all()):
                raise ValueError("Invalid CafeF historical provenance")
            for row in rows.itertuples(index=False):
                if parse_cafef_timestamp(row.canonical_url) != pd.Timestamp(row.published_at).to_pydatetime():
                    raise ValueError("Invalid CafeF publication binding")
        if not (dates["available_at"] >= dates["published_at"]).all(): raise ValueError("Macro news available_at precedes publication")
        for row in frame.itertuples(index=False):
            summary, body_text, source_record_id, canonical_url = (_null(value) for value in (row.summary, row.body_text, row.source_record_id, row.canonical_url))
            content_hash = _hash({"title": row.title, "summary": summary or "", "body_text": body_text or ""})
            article_id = _hash({"v": 1, "source_id": row.source_id, "source_record_id": source_record_id or canonical_url or {"published_at": row.published_at, "title": row.title}})
            revision_id = _hash({"v": 1, "article_id": article_id, "content_hash": content_hash})
            provenance_id = _hash({"v": 1, "source_id": row.source_id, "origin_ticker": _null(row.origin_ticker), "origin_exchange": _null(row.origin_exchange)})
            raw_record_id = _hash({"v": 1, "revision_id": revision_id, "provenance_id": provenance_id})
            if (row.content_hash, row.article_id, row.revision_id, row.provenance_id, row.raw_record_id) != (content_hash, article_id, revision_id, provenance_id, raw_record_id):
                raise ValueError("Invalid macro news identity bindings")
