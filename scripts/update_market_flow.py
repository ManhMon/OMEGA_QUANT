#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Historical CafeF flows and VNDirect futures, with retrieval-time PIT availability."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import math
import os
import re
import shutil
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from filelock import FileLock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.data.market_flow import MarketFlowLakehouse, is_market_flow_trading_day

HEADERS = {"User-Agent": "Mozilla/5.0"}
DATA_DIR = REPO_ROOT / "data"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_ROWS = 3_000_000
MAX_UNIVERSE_CHUNK_BYTES = 65536
PAGE_SIZE = 300
MAX_PAGES = 72
MAX_ATTEMPTS = 3
LOCK_TIMEOUT = 10
CAFEF_ROOT = "https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/"
DCHART_ROOT = "https://dchart-api.vndirect.com.vn/dchart/history"
VN30_TICKERS = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE",
]


def _now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _symbols(symbols: list[str], *, derivatives: bool = False) -> list[str]:
    pattern = r"VN30F(?:[12]M|[12]Q|\d{4})" if derivatives else r"[A-Z][A-Z0-9]{1,9}"
    if (not isinstance(symbols, list) or not 1 <= len(symbols) <= 1000
            or any(not isinstance(s, str) or re.fullmatch(pattern, s) is None for s in symbols)
            or len(set(symbols)) != len(symbols)):
        raise ValueError("Invalid or duplicate symbols")
    return symbols


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Provider redirects are forbidden")


def _invalid_json_constant(value):
    raise ValueError("Non-finite JSON number")


def _request_json(url: str) -> dict:
    parsed = urllib.parse.urlsplit(url)
    allowed = {("cafef.vn", "/du-lieu/Ajax/PageNew/DataHistory/GDKhoiNgoai.ashx"),
               ("cafef.vn", "/du-lieu/Ajax/PageNew/DataHistory/GDTuDoanh.ashx"),
               ("dchart-api.vndirect.com.vn", "/dchart/history")}
    if (parsed.scheme != "https" or (parsed.hostname, parsed.path) not in allowed
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443) or parsed.fragment or len(url) > 2048):
        raise ValueError("Invalid provider URL")
    opener = urllib.request.build_opener(_NoRedirect())
    deadline = time.monotonic() + 60
    for attempt in range(MAX_ATTEMPTS):
        if time.monotonic() >= deadline:
            break
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with opener.open(req, timeout=min(15, max(0.001, deadline - time.monotonic()))) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if time.monotonic() > deadline:
                raise TimeoutError
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("Provider response exceeds byte limit")
            data = json.loads(raw.decode("utf-8"), parse_constant=_invalid_json_constant)
            if not isinstance(data, dict):
                raise ValueError("Provider response must be an object")
            return data
        except urllib.error.HTTPError as exc:
            retry = exc.code == 429 or 500 <= exc.code <= 599
            exc.close()
            if not retry:
                raise RuntimeError("Provider request rejected") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        except (UnicodeError, ValueError, RecursionError):
            raise ValueError("Invalid provider response") from None
        if attempt + 1 < MAX_ATTEMPTS:
            time.sleep(0.25 * (2 ** attempt))
    raise RuntimeError("Provider retries exhausted") from None


def _number(value, *, integral: bool = False, price: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Invalid numeric field")
    try:
        number = float(value)
    except OverflowError:
        raise ValueError("Numeric field exceeds bounds") from None
    limit = 10_000_000 if price else (1e12 if integral else 9_000_000_000_000_000)
    if (not math.isfinite(number) or not 0 <= number <= limit
            or price and number == 0 or integral and not number.is_integer()):
        raise ValueError("Numeric field exceeds bounds")
    return number


def _event(day: pd.Timestamp) -> pd.Timestamp:
    if not is_market_flow_trading_day(day):
        raise ValueError("Provider returned a non-trading session")
    return day.tz_localize("Asia/Ho_Chi_Minh") + pd.Timedelta(hours=15, minutes=30)


def _cafef_page(kind: str, sym: str, page: int, start: pd.Timestamp, end: pd.Timestamp):
    endpoint = "GDTuDoanh.ashx" if kind == "proprietary" else "GDKhoiNgoai.ashx"
    query = urllib.parse.urlencode({"Symbol": sym, "Exchange": "HOSE",
                                   "StartDate": start.strftime("%m/%d/%Y"),
                                   "EndDate": end.strftime("%m/%d/%Y"),
                                   "PageIndex": page, "PageSize": PAGE_SIZE})
    payload = _request_json(CAFEF_ROOT + endpoint + "?" + query)
    try:
        if payload["Success"] is not True:
            raise ValueError
        body = payload["Data"]
        total = body["TotalCount"]
        items = body["Data"]
        if kind == "proprietary":
            items = items["ListDataTudoanh"]
        if (type(total) is not int or not 0 <= total <= MAX_PAGES * PAGE_SIZE
                or not isinstance(items, list) or len(items) > PAGE_SIZE
                or any(not isinstance(item, dict) for item in items)):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError("Invalid CafeF page schema") from None
    return total, items


def _fetch_flow(sym: str, kind: str, windows: list[tuple[pd.Timestamp, pd.Timestamp]]):
    _symbols([sym])
    rows, seen = [], set()
    received = 0
    deadline = time.monotonic() + 1800
    for start, end in windows:
        count, expected = 0, None
        for page in range(1, MAX_PAGES + 1):
            if time.monotonic() >= deadline:
                raise RuntimeError("CafeF retrieval deadline exhausted")
            total, items = _cafef_page(kind, sym, page, start, end)
            observed = _now()
            if expected is not None and total != expected:
                raise ValueError("CafeF pagination changed during retrieval")
            expected = total
            count += len(items)
            received += len(items)
            if count > total or not items and count != total:
                raise ValueError("Incomplete CafeF pagination")
            for item in items:
                try:
                    key = "Date" if kind == "proprietary" else "Ngay"
                    date = item[key]
                    if not isinstance(date, str) or re.fullmatch(r"\d{2}/\d{2}/\d{4}", date) is None:
                        raise ValueError
                    day = pd.to_datetime(date, format="%d/%m/%Y")
                    if item["Symbol"] != sym or not start <= day <= end:
                        raise ValueError
                    event = _event(day)
                    buy, sell = (_number(item[k]) for k in ("GtMua", "GtBan"))
                    volume_keys = ("KLcpMua", "KlcpBan") if kind == "proprietary" else ("KLMua", "KLBan")
                    bv, sv = (_number(item[k], integral=True) for k in volume_keys)
                except (KeyError, TypeError, ValueError, OverflowError):
                    raise ValueError("Invalid CafeF observation") from None
                if event > observed:
                    continue  # An unfinished current session is not an EOD observation.
                if day in seen:
                    continue
                # ponytail: retain first eligible provider snapshot; no intraday ordering metadata.
                seen.add(day)
                names = (("total_buy_trade_value", "total_sell_trade_value", "total_trade_net_value",
                          "total_buy_trade_volume", "total_sell_trade_volume", "total_trade_net_volume")
                         if kind == "proprietary" else
                         ("fr_buy_value_total", "fr_sell_value_total", "fr_net_value_total",
                          "fr_buy_volume_total", "fr_sell_volume_total", "fr_net_volume_total"))
                row = dict(zip(names, (buy, sell, buy - sell, bv, sv, bv - sv)))
                row.update(trading_date=day.date().isoformat(), ticker=sym, time=day,
                           as_of=event, available_at=observed, price_scale="VND_FULL", volume_unit="shares",
                           source="PROPRIETARY" if kind == "proprietary" else "CAFEF",
                           historical_pit_verified=False)
                rows.append(row)
            if count == total:
                break
        else:
            raise ValueError("CafeF pagination limit exhausted")
    if not received:
        return sym, pd.DataFrame()
    if not rows:
        raise ValueError("No completed market-flow observations")
    frame = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
    MarketFlowLakehouse._validate_partition(frame, kind, sym)
    return sym, frame


def _history_windows(start_year: int, end_year: int | None):
    today = _now().tz_convert("Asia/Ho_Chi_Minh").tz_localize(None).normalize()
    end_year = today.year if end_year is None else end_year
    if (type(start_year) is not int or type(end_year) is not int
            or not 2015 <= start_year <= end_year <= today.year):
        raise ValueError("Invalid flow history years")
    return [(pd.Timestamp(year, 1, 1), min(pd.Timestamp(year, 12, 31), today))
            for year in range(start_year, end_year + 1)]


def fetch_prop_ticker(sym: str, start_year: int = 2015, end_year: int | None = None) -> tuple[str, pd.DataFrame]:
    return _fetch_flow(sym, "proprietary", _history_windows(start_year, end_year))


def fetch_foreign_ticker(sym: str, start_year: int = 2015, end_year: int | None = None):
    return _fetch_flow(sym, "foreign", _history_windows(start_year, end_year))


def _fetch_derivatives(sym: str) -> pd.DataFrame:
    _symbols([sym], derivatives=True)
    upper = _now()
    start = pd.Timestamp("2017-08-10", tz="Asia/Ho_Chi_Minh")
    query = urllib.parse.urlencode({"resolution": "D", "symbol": sym,
                                   "from": int(start.timestamp()), "to": int(upper.timestamp())})
    payload = _request_json(DCHART_ROOT + "?" + query)
    fields = ("t", "o", "h", "l", "c", "v")
    if (payload.get("s") != "ok" or any(not isinstance(payload.get(k), list) for k in fields)
            or not 1 <= len(payload["t"]) <= 5000
            or any(len(payload[k]) != len(payload["t"]) for k in fields)):
        raise ValueError("Invalid DChart arrays")
    observed = _now()
    rows, seen = [], set()
    for t, o, h, l, c, v in zip(*(payload[k] for k in fields)):
        if type(t) is not int or not int(start.timestamp()) <= t <= int(upper.timestamp()):
            raise ValueError("Invalid DChart timestamp")
        day = pd.Timestamp(t, unit="s", tz="UTC").tz_convert("Asia/Ho_Chi_Minh").tz_localize(None).normalize()
        event = _event(day)
        if day in seen:
            raise ValueError("Duplicate DChart session")
        seen.add(day)
        o, h, l, c = (_number(n, price=True) for n in (o, h, l, c))
        v = _number(v, integral=True)
        if not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError("Invalid DChart OHLC")
        if event > observed:
            continue
        rows.append(dict(time=day, ticker=sym, open=o, high=h, low=l, close=c, volume=int(v),
                         as_of=event, available_at=observed, source="VNDIRECT", price_scale="points",
                         adjusted="provider_adjusted", rebuild_date=observed.date().isoformat(),
                         volume_unit="contracts", historical_pit_verified=False))
    if not rows:
        raise ValueError("No completed derivatives observations")
    frame = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
    MarketFlowLakehouse._validate_derivatives(frame, sym)
    return frame


def _validate(frame: pd.DataFrame, kind: str) -> None:
    if (not isinstance(frame, pd.DataFrame) or frame.empty or len(frame) > MAX_ROWS
            or "ticker" not in frame or frame["ticker"].isna().any()):
        raise ValueError("Invalid market-flow partition")
    for sym, group in frame.groupby("ticker"):
        _symbols([sym], derivatives=kind == "derivatives")
        MarketFlowLakehouse._validate_partition(group, kind, sym)


def _merge(old: pd.DataFrame, new: pd.DataFrame, kind: str) -> pd.DataFrame:
    _validate(old, kind)
    if set(old.columns) != set(new.columns):
        raise ValueError("Stored schema differs from incoming schema")
    # Unchanged observations retain their original availability; revisions are newly available.
    values = [c for c in new.columns if c not in ("available_at", "rebuild_date")]
    new = new.merge(old[values], on=values, how="left", indicator=True)
    new = new.loc[new.pop("_merge").eq("left_only")]
    merged = pd.concat([old, new], ignore_index=True).drop_duplicates(["ticker", "time"], keep="last")
    _validate(merged, kind)
    return merged.sort_values(["ticker", "time"]).reset_index(drop=True)


def _sync_file(path: Path) -> None:
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _sync_directory(path: Path) -> None:
    # ponytail: Windows has no directory fsync; synced files plus same-volume replace.
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _regular(path: Path) -> None:
    if path.is_symlink() or path.exists() and (not path.is_file() or path.stat().st_size > MAX_FILE_BYTES):
        raise ValueError("Invalid destination file")


def atomic_write(df: pd.DataFrame, target: Path, *, kind: str | None = None) -> None:
    """Locked per-file publication; preserve old data and a synced backup on failure."""
    target = Path(target)
    if not target.is_absolute():
        target = REPO_ROOT / target
    if not target.resolve().is_relative_to(REPO_ROOT.resolve()) or target.suffix != ".parquet":
        raise ValueError("Destination must be a repo-local parquet file")
    backup = target.with_suffix(".parquet.bak")
    lock = Path(str(target) + ".ingest.lock")
    for path in (target, backup, lock):
        _regular(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(lock), timeout=LOCK_TIMEOUT):
        for path in (target, backup):
            _regular(path)
        if kind is not None:
            _validate(df, kind)
            if target.exists():
                df = _merge(pd.read_parquet(target), df, kind)
        temps = []
        replaced, existed = False, target.exists()
        try:
            fd, name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
            os.close(fd)
            candidate = Path(name)
            temps.append(candidate)
            df.to_parquet(candidate, index=False)
            _regular(candidate)
            _sync_file(candidate)
            if kind is not None:
                _validate(pd.read_parquet(candidate), kind)
            if existed:
                fd, name = tempfile.mkstemp(prefix=backup.name + ".", suffix=".tmp", dir=target.parent)
                os.close(fd)
                saved = Path(name)
                temps.append(saved)
                shutil.copyfile(target, saved)
                _sync_file(saved)
                os.replace(saved, backup)
            _sync_directory(target.parent)
            os.replace(candidate, target)
            replaced = True
            _sync_directory(target.parent)
        except BaseException:
            if replaced:
                try:
                    if existed:
                        fd, name = tempfile.mkstemp(prefix=target.name + ".rollback.", dir=target.parent)
                        os.close(fd)
                        restore = Path(name)
                        temps.append(restore)
                        shutil.copyfile(backup, restore)
                        _sync_file(restore)
                        os.replace(restore, target)
                    else:
                        target.unlink()
                    _sync_directory(target.parent)
                except OSError:
                    raise OSError("Publication failed; rollback incomplete; backup retained") from None
            raise
        finally:
            for path in temps:
                path.unlink(missing_ok=True)


def _publish(symbols: list[str], fetch, kind: str, dry_run: bool, workers: int) -> list[pd.DataFrame]:
    _symbols(symbols, derivatives=kind == "derivatives")
    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError("Workers must be an integer from 1 to 16")
    frames = {}
    remaining = iter(symbols)
    with ThreadPoolExecutor(max_workers=min(workers, len(symbols))) as pool:
        pending = {pool.submit(fetch, sym): sym for sym in
                   [next(remaining) for _ in range(min(workers, len(symbols)))]}
        try:
            while pending:
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for job in completed:
                    sym = pending.pop(job)
                    frame = job.result()
                    if kind != "derivatives" and isinstance(frame, pd.DataFrame) and frame.empty:
                        frames[sym] = frame
                    else:
                        _validate(frame, kind)
                        if not frame["ticker"].eq(sym).all():
                            raise ValueError("Fetched partition identity mismatch")
                        if not dry_run:
                            atomic_write(frame, DATA_DIR / f"{kind}_{sym}.parquet", kind=kind)
                        frames[sym] = frame
                    next_sym = next(remaining, None)
                    if next_sym is not None:
                        pending[pool.submit(fetch, next_sym)] = next_sym
        except BaseException:
            for job in pending:
                job.cancel()
            raise
    ordered = [frames[sym] for sym in symbols if not frames[sym].empty]
    if ordered and not dry_run and kind != "derivatives":
        name = "foreign_flow_2015_now.parquet" if kind == "foreign" else "proprietary_flow_2025_now.parquet"
        atomic_write(pd.concat(ordered, ignore_index=True), DATA_DIR / name, kind=kind)
    return ordered


def ingest_derivatives(symbols: list[str], dry_run: bool = False, workers: int = 4) -> list[pd.DataFrame]:
    return _publish(symbols, _fetch_derivatives, "derivatives", dry_run, workers)


def ingest_proprietary(symbols: list[str], dry_run: bool = False, workers: int = 4,
                       start_year: int = 2015, end_year: int | None = None) -> list[pd.DataFrame]:
    _history_windows(start_year, end_year)
    return _publish(symbols, lambda sym: fetch_prop_ticker(sym, start_year, end_year)[1],
                    "proprietary", dry_run, workers)


def ingest_foreign(symbols: list[str], start_year: int = 2015, end_year: int | None = None,
                   dry_run: bool = False, workers: int = 4) -> list[pd.DataFrame]:
    _history_windows(start_year, end_year)
    return _publish(symbols, lambda sym: fetch_foreign_ticker(sym, start_year, end_year)[1],
                    "foreign", dry_run, workers)


def _full_universe() -> list[str]:
    """Current snapshot membership only; not a historical PIT universe."""
    path = DATA_DIR / "hybrid_eval_full_703.parquet"
    if not path.resolve().is_relative_to(REPO_ROOT.resolve()):
        raise ValueError("Universe must be repo-local")
    _regular(path)
    symbols = set()
    with path.open("rb") as source:
        opened = os.fstat(source.fileno())
        _regular(path)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_FILE_BYTES
                or not os.path.samestat(opened, path.stat())):
            raise ValueError("Invalid universe file")
        parquet = pq.ParquetFile(source)
        if not 1 <= parquet.metadata.num_rows <= MAX_ROWS:
            raise ValueError("Invalid universe row count")
        columns = [i for i in range(len(parquet.metadata.schema))
                   if parquet.metadata.schema.column(i).path.split(".")[0] == "symbol"]
        if len(columns) != 1 or parquet.metadata.schema.column(columns[0]).path != "symbol":
            raise ValueError("Invalid universe symbol column")
        for i in range(parquet.metadata.num_row_groups):
            chunk = parquet.metadata.row_group(i).column(columns[0])
            if not 0 <= chunk.total_uncompressed_size <= MAX_UNIVERSE_CHUNK_BYTES:
                raise ValueError("Universe symbol chunk exceeds uncompressed byte limit")
        for batch in parquet.iter_batches(columns=["symbol"], batch_size=1000):
            for symbol in batch.column("symbol").to_pylist():
                _symbols([symbol])
                symbols.add(symbol)
            _symbols(list(symbols))
    return _symbols(sorted(symbols))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["all", "derivatives", "proprietary", "foreign"], default="all")
    parser.add_argument("--symbols", help="Comma-separated ticker list; overrides --universe")
    parser.add_argument("--universe", choices=["vn30", "full"], default="vn30",
                        help="Equity universe; full uses the current local 703-symbol snapshot")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int)
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 17))
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = parser.parse_args(argv)
    try:
        symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols is not None else None
        if args.kind == "derivatives":
            ingest_derivatives(symbols if symbols is not None else ["VN30F1M", "VN30F2M"], args.dry_run, args.workers)
        else:
            if symbols is None:
                symbols = _full_universe() if args.universe == "full" else VN30_TICKERS
            _symbols(symbols)
            if args.kind == "all":
                ingest_derivatives(["VN30F1M", "VN30F2M"], args.dry_run, args.workers)
            if args.kind in ("all", "proprietary"):
                ingest_proprietary(symbols, args.dry_run, args.workers, args.start_year, args.end_year)
            if args.kind in ("all", "foreign"):
                ingest_foreign(symbols, args.start_year, args.end_year, args.dry_run, args.workers)
    except Exception as exc:
        print(f"Market flow ingestion failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    print("Market flow ingestion completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
