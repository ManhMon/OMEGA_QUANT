"""Fail-closed official HSX/HNX watermark artifact contract.

This module acquires and validates one official response, then writes its
watermark bundle. Network acquisition is private and internally configured.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import base64
import binascii
import ssl
from types import MappingProxyType
from email.message import Message
from urllib.request import Request, urlopen
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

OFFICIAL_MARKETS = frozenset({"HSX", "HNX"})
_OFFICIAL_SOURCE_URLS = MappingProxyType({
    "HSX": "https://api.hsx.vn/m/api/v1.0/data-feed/files",
    "HNX": "https://hnx.vn/vi-vn/co-phieu-etfs/du-lieu-thi-truong-ny.html",
})
STATUS_COMPLETED = "completed"
STATUS_VCI_CLIENT_MISSING = "vci_client_missing"
STATUS_VCI_FETCH_FAILED = "vci_fetch_failed"
STATUS_MARKET_INVALID = "market_invalid"
STATUS_URL_NOT_ALLOWED = "url_not_allowed"
STATUS_CANDIDATE_DATE_MISMATCH = "candidate_exact_max_date_missing"
STATUS_ARTIFACT_EXISTS = "artifact_exists"
STATUS_PATH_INVALID = "path_invalid"
STATUS_ARTIFACT_TAMPERED = "artifact_tampered"
STATUS_ARTIFACT_MISSING = "artifact_missing"
STATUS_RECEIPT_INVALID = "vci_receipt_invalid"
RECEIPT_VERSION = 3
SOURCE_VALIDATOR_VERSION = "official-source-validator-v1"
PIT_RECEIPT_TIME = "09:00:00+07:00"
EXCEPTIONS_SCHEMA_VERSION = 1


class WatermarkContractError(ValueError):
    """Contract rejection with a stable, machine-readable status."""

    def __init__(self, status: str, detail: str = "") -> None:
        super().__init__(f"{status}: {detail}".rstrip(": "))
        self.status = status


@dataclass(frozen=True)
class OfficialWatermarkConfig:
    artifact_root: Path


@dataclass(frozen=True)
class _OfficialSourceResponse:
    """Validated response kept private to prevent forged provenance."""

    source_url: str
    effective_url: str
    status: int
    content_type: str
    raw: bytes
    retrieved_at: str
    validator_version: str = SOURCE_VALIDATOR_VERSION

    @property
    def sha256(self) -> str:
        return sha256_hex(self.raw)


def _source_receipt_metadata(response: _OfficialSourceResponse) -> dict[str, Any]:
    """Return immutable source evidence for a downstream receipt manifest."""
    return {
        "source_url": response.source_url,
        "effective_url": response.effective_url,
        "http_status": response.status,
        "content_type": response.content_type,
        "response_sha256": response.sha256,
        "validator_version": response.validator_version,
        "retrieved_at": response.retrieved_at,
    }


def _acquire_official_source(
    market: str,
    expected_date: str,
)-> _OfficialSourceResponse:
    """Fetch one exact official structured response and reject unsafe responses."""
    _require_market(market)
    _require_vci_token()
    source_url = _OFFICIAL_SOURCE_URLS[market]
    _require_official_url(market, source_url)
    try:
        _parse_iso_calendar_date(expected_date)
    except (TypeError, ValueError) as exc:
        raise WatermarkContractError(STATUS_CANDIDATE_DATE_MISMATCH, expected_date) from exc
    request = Request(source_url, headers={
        "Accept": "application/json",
        "Authorization": f"Bearer {os.environ['VCI_API_TOKEN']}",
        "User-Agent": "OMEGA_QUANT official receipt/1",
    })
    context = _official_tls_context()
    try:
        with urlopen(request, timeout=30, context=context) as response:
            status = int(response.getcode())
            effective_url = str(response.geturl())
            headers = response.headers
            content_type = headers.get_content_type() if isinstance(headers, Message) else str(headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
            raw = response.read()
    except Exception as exc:
        raise WatermarkContractError(STATUS_VCI_FETCH_FAILED, str(exc)) from exc
    if status != 200 or effective_url != source_url or content_type != "application/json":
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "official response status, redirect, or content type rejected")
    try:
        decoded = raw.decode("utf-8", errors="strict")
        payload = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "official response encoding or JSON invalid") from exc
    if not _structured_response_matches(payload, market, expected_date):
        raise WatermarkContractError(STATUS_CANDIDATE_DATE_MISMATCH, f"{market} {expected_date} not present in official response")
    return _OfficialSourceResponse(
        source_url, effective_url, status, content_type, raw,
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def _require_vci_token() -> str:
    token = os.environ.get("VCI_API_TOKEN", "").strip()
    if not token:
        raise WatermarkContractError(STATUS_VCI_CLIENT_MISSING, "VCI_API_TOKEN is missing")
    if token.count(".") == 2:
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
            if int(payload.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
                raise WatermarkContractError(STATUS_VCI_FETCH_FAILED, "VCI_API_TOKEN is expired")
        except WatermarkContractError:
            raise
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError, binascii.Error):
            raise WatermarkContractError(STATUS_VCI_CLIENT_MISSING, "VCI_API_TOKEN is invalid")
    return token


def _official_tls_context() -> ssl.SSLContext:
    """Use certifi when available; otherwise use the platform CA store."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _structured_response_matches(value: Any, market: str, expected_date: str) -> bool:
    if isinstance(value, str):
        return False
    if isinstance(value, Mapping):
        if value.get("success") is False:
            return False
        date_value = value.get("date", value.get("tradingDate", value.get("reportdate")))
        market_value = value.get("market", value.get("exchange", value.get("exchangeCode")))
        try:
            date_matches = _parse_iso_calendar_date(date_value) == _parse_iso_calendar_date(expected_date)
        except (TypeError, ValueError):
            date_matches = False
        if date_matches and str(market_value).upper() in {market, "HOSE" if market == "HSX" else market}:
            return True
        return any(_structured_response_matches(item, market, expected_date) for item in value.values())
    if isinstance(value, list):
        return any(_structured_response_matches(item, market, expected_date) for item in value)
    return False


def _parse_iso_calendar_date(value: Any) -> date:
    """Parse an ISO date or ISO timestamp, returning its calendar date."""
    if not isinstance(value, str):
        raise ValueError(value)
    if len(value) == 10:
        return date.fromisoformat(value)
    return datetime.fromisoformat(value).date()


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical compact UTF-8 JSON bytes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_aware_timestamp(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, f"{field} is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _aware_receipt_timestamp(value: Any, field: str) -> str:
    return parse_aware_timestamp(value, field).isoformat()


def _require_market(market: str) -> None:
    if market not in OFFICIAL_MARKETS:
        raise WatermarkContractError(STATUS_MARKET_INVALID, market)


def _require_official_url(market: str, source_url: str) -> None:
    _require_market(market)
    if _OFFICIAL_SOURCE_URLS.get(market) != source_url:
        raise WatermarkContractError(STATUS_URL_NOT_ALLOWED, source_url)
    parsed = urlsplit(source_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise WatermarkContractError(STATUS_URL_NOT_ALLOWED, source_url)


def select_candidate(rows: Iterable[Mapping[str, Any]], market: str, expected_date: str) -> Mapping[str, Any]:
    """Select only a row with exact market and exact maximum date."""
    _require_market(market)
    try:
        target = _parse_iso_calendar_date(expected_date)
    except (TypeError, ValueError) as exc:
        raise WatermarkContractError(STATUS_CANDIDATE_DATE_MISMATCH, expected_date) from exc
    matches = [row for row in rows if row.get("market") == market]
    try:
        max_date = max(_parse_iso_calendar_date(row["date"]) for row in matches)
    except (KeyError, TypeError, ValueError) as exc:
        raise WatermarkContractError(STATUS_CANDIDATE_DATE_MISMATCH, expected_date) from exc
    if not matches or max_date != target:
        raise WatermarkContractError(STATUS_CANDIDATE_DATE_MISMATCH, expected_date)
    try:
        exact = [row for row in matches if _parse_iso_calendar_date(row.get("date")) == target]
    except (TypeError, ValueError) as exc:
        raise WatermarkContractError(STATUS_CANDIDATE_DATE_MISMATCH, expected_date) from exc
    if not exact:
        raise WatermarkContractError(STATUS_CANDIDATE_DATE_MISMATCH, expected_date)
    return sorted(exact, key=canonical_json_bytes)[-1]


def _safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not relative or any(part == "" for part in path.parts):
        raise WatermarkContractError(STATUS_PATH_INVALID, relative)
    if root.exists() and root.is_symlink():
        raise WatermarkContractError(STATUS_PATH_INVALID, str(root))
    root = root.resolve()
    target = (root / path).resolve(strict=False)
    if root not in target.parents:
        raise WatermarkContractError(STATUS_PATH_INVALID, relative)
    current = root
    for part in path.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise WatermarkContractError(STATUS_PATH_INVALID, relative)
    if target.is_symlink():
        raise WatermarkContractError(STATUS_PATH_INVALID, relative)
    if target.exists():
        raise WatermarkContractError(STATUS_ARTIFACT_EXISTS, relative)
    return target


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        # Windows has no supported directory fsync. The file handle is already
        # flushed with os.fsync; O_EXCL provides the watermark's atomic create.
        return
    try:
        directory_fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        raise RuntimeError("verified directory durability unavailable") from exc
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _exclusive_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    except FileExistsError as exc:
        raise WatermarkContractError(STATUS_ARTIFACT_EXISTS, str(path)) from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            _fsync_directory(path.parent)
        except OSError as exc:
            raise WatermarkContractError(STATUS_RECEIPT_INVALID, "verified directory durability unavailable") from exc
        except RuntimeError as exc:
            raise WatermarkContractError(STATUS_RECEIPT_INVALID, str(exc)) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise


def verify_artifact(path: Path, expected_sha256: str) -> None:
    actual = sha256_hex(path.read_bytes())
    if actual != expected_sha256:
        raise WatermarkContractError(STATUS_ARTIFACT_TAMPERED, str(path))


def _parse_official_payload(source: _OfficialSourceResponse, market: str, expected_date: str) -> dict[str, Any]:
    payload = json.loads(source.raw.decode("utf-8", errors="strict"))
    if isinstance(payload, Mapping) and isinstance(payload.get("rows"), list):
        rows = payload["rows"]
    elif isinstance(payload, list):
        rows = payload
        payload = {"rows": rows}
    else:
        rows = []
    if not rows or any(not isinstance(row, Mapping) for row in rows):
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "official payload rows invalid")
    return {**payload, "raw": source.raw, "rows": rows}


def materialize_watermark(config: OfficialWatermarkConfig, market: str, expected_date: str) -> dict[str, Any]:
    """Acquire, parse, validate, and atomically materialize official evidence."""
    return _materialize_acquired(config, market, expected_date)


def _materialize_acquired(
    config: OfficialWatermarkConfig,
    market: str,
    expected_date: str,
) -> dict[str, Any]:
    """Materialize only evidence acquired by this module.

    Parsing stays inside the write path so callers cannot supply forged rows,
    candidate, coverage, or metadata to a receipt-producing function.
    """
    _require_market(market)
    source_evidence = _acquire_official_source(market, expected_date)
    source_url = _OFFICIAL_SOURCE_URLS[market]
    _require_official_url(market, source_url)
    if not isinstance(source_evidence, _OfficialSourceResponse):
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "immutable official evidence required")
    if (
        source_evidence.source_url != source_url
        or source_evidence.effective_url != source_url
        or source_evidence.status != 200
        or source_evidence.content_type != "application/json"
        or source_evidence.validator_version != SOURCE_VALIDATOR_VERSION
    ):
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "official evidence metadata mismatch")
    try:
        result = _parse_official_payload(source_evidence, market, expected_date)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "official response encoding or JSON invalid") from exc
    raw = source_evidence.raw
    candidate = select_candidate(result.get("rows", []), market, expected_date)
    canonical = canonical_json_bytes({"market": market, "candidate": candidate})
    rows = list(result.get("rows", []))
    calendar_version = str(result.get("calendar_version", "vietnam-calendar-v1"))
    calendar_closures = result.get("calendar_closures", {})
    calendar_payload = {"version": calendar_version, "closures": calendar_closures, "pit_available_at": PIT_RECEIPT_TIME}
    computed_calendar_hash = sha256_hex(canonical_json_bytes(calendar_payload))
    calendar_hash = str(result.get("calendar_hash", computed_calendar_hash))
    if calendar_hash != computed_calendar_hash:
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "calendar hash mismatch")
    exceptions_version = str(result.get("exceptions_version", f"v{EXCEPTIONS_SCHEMA_VERSION}"))
    symbols_by_exchange = {
        market: sorted({str(row.get("symbol", row.get("ticker", ""))).upper() for row in rows
                        if row.get("market") == market and row.get("symbol", row.get("ticker"))})
    }
    coverage = dict(result.get("coverage") or {})
    coverage.setdefault("final_session", expected_date)
    coverage["by_exchange"] = symbols_by_exchange
    coverage["symbols"] = symbols_by_exchange[market]
    if coverage.get("final_session") != expected_date or coverage.get("by_exchange") != symbols_by_exchange:
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "coverage is not exact per-symbol exchange partition")
    if not result.get("cutoff_at"):
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "real cutoff_at required")
    cutoff_at = _aware_receipt_timestamp(result["cutoff_at"], "cutoff_at")
    retrieved_at = _aware_receipt_timestamp(source_evidence.retrieved_at, "retrieved_at")
    if parse_aware_timestamp(retrieved_at, "retrieved_at") > parse_aware_timestamp(cutoff_at, "cutoff_at"):
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "retrieval after cutoff")
    exceptions = result.get("exceptions")
    if not isinstance(exceptions, list):
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "exceptions must be immutable entries")
    exceptions_hash = sha256_hex(canonical_json_bytes({"version": exceptions_version, "entries": sorted(exceptions, key=canonical_json_bytes)}))
    if result.get("exceptions_hash") and str(result["exceptions_hash"]) != exceptions_hash:
        raise WatermarkContractError(STATUS_RECEIPT_INVALID, "immutable exceptions hash mismatch")
    for entry in exceptions:
        if not isinstance(entry, Mapping) or any(not entry.get(key) for key in ("owner", "reason", "expiry", "exchange")):
            raise WatermarkContractError(STATUS_RECEIPT_INVALID, "exception entries require owner/reason/expiry/exchange")
    exceptions = sorted(exceptions, key=canonical_json_bytes)
    manifest = {
        "receipt_version": RECEIPT_VERSION,
        "provider": "VCI",
        "market": market,
        "source_url": source_url,
        "effective_url": source_evidence.effective_url,
        "http_status": source_evidence.status,
        "content_type": source_evidence.content_type,
        "response_sha256": source_evidence.sha256,
        "validator_version": source_evidence.validator_version,
        "expected_date": expected_date,
        "candidate_date": str(candidate["date"]),
        "raw_sha256": sha256_hex(raw),
        "canonical_sha256": sha256_hex(canonical),
        "calendar_version": calendar_version,
        "calendar_hash": calendar_hash,
        "calendar_closures": calendar_closures,
        "exceptions_version": exceptions_version,
        "exceptions_schema_version": EXCEPTIONS_SCHEMA_VERSION,
        "exceptions_hash": exceptions_hash,
        "exceptions": exceptions,
        "coverage": coverage,
        "cutoff_at": _aware_receipt_timestamp(result.get("cutoff_at"), "cutoff_at"),
        "retrieved_at": retrieved_at,
        "status": STATUS_COMPLETED,
    }
    receipt = canonical_json_bytes(manifest)
    stem = f"{market.lower()}_{expected_date}"
    paths = {
        "raw": _safe_path(config.artifact_root, f"{stem}.raw"),
        "canonical": _safe_path(config.artifact_root, f"{stem}.json"),
        "receipt": _safe_path(config.artifact_root, f"{stem}.receipt.json"),
    }
    written = []
    try:
        for path, content in ((paths["raw"], raw), (paths["canonical"], canonical), (paths["receipt"], receipt)):
            _exclusive_write(path, content)
            written.append(path)
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return {"status": STATUS_COMPLETED, "manifest": manifest, "paths": {key: str(value) for key, value in paths.items()}}
