"""Fetch whitelisted vnstock graph data and persist point-in-time snapshots."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import os
import sys
import threading
import time
from typing import Any

try:
    from tqdm import tqdm
except ImportError as exc:  # pragma: no cover
    raise SystemExit("tqdm is required: install project dependencies first") from exc

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.quant.data.vnstock import RateLimiter
from omega.quant.graph import snapshot
from omega.quant.graph.fetcher import GraphFetcher


COMPANY_ENDPOINTS = ("info", "shareholders", "subsidiaries", "ownership", "officers", "news")
FINANCIAL_ENDPOINTS = ("income_statement", "cash_flow", "ratios")
INDUSTRY_ENDPOINTS = ("list", "sectors", "list_by_industry")
UNIVERSE_PATH = REPO_ROOT / ".ly_state" / "session" / "vci_universe_hsx_hnx.json"

# Thread-safe RateLimiter wrapper
_rate_lock = threading.Lock()
_original_throttle = RateLimiter.throttle

def _thread_safe_throttle(self):
    with _rate_lock:
        return _original_throttle(self)

RateLimiter.throttle = _thread_safe_throttle  # monkeypatch for thread safety


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", help="Comma-separated symbols overriding the universe file")
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--rate-limit", type=int, default=60)
    parser.add_argument("--workers", type=int, default=4, help="Parallel worker threads (default: 4)")
    parser.add_argument("--pid-file")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    parser.add_argument("--snapshot-root", default=".ly_state/graph_snapshots")
    return parser.parse_args()


def load_symbols(raw_symbols: str | None, max_symbols: int | None) -> list[str]:
    if raw_symbols is not None:
        symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
    else:
        with UNIVERSE_PATH.open(encoding="utf-8") as f:
            universe = json.load(f)
        symbols = sorted({s.upper() for key in ("hsx", "hnx") for s in universe.get(key, [])})
    if max_symbols is not None:
        if max_symbols < 0:
            raise ValueError("--max-symbols must be non-negative")
        symbols = symbols[:max_symbols]
    return symbols


def configure_logging(level: str) -> tuple[logging.Logger, Path]:
    log_dir = REPO_ROOT / ".ly_state"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"graph_bootstrap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("graph_bootstrap")
    logger.setLevel(getattr(logging, level))
    logger.handlers.clear()
    for handler in (logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger, log_path


def as_dataframe(value: Any):
    import pandas as pd
    if isinstance(value, pd.DataFrame):
        return value
    if value is None:
        return pd.DataFrame()
    if isinstance(value, list):
        return pd.DataFrame(value)
    if isinstance(value, dict):
        return pd.DataFrame([value])
    return pd.DataFrame([{"value": value}])


_snapshot_lock = threading.Lock()

def save_result(value: Any, entity_type: str, observed_at: datetime, logger: logging.Logger, symbol: str | None = None) -> Path:
    df = as_dataframe(value)
    with _snapshot_lock:
        path = snapshot.save_snapshot(df, entity_type, observed_at, symbol=symbol)
    logger.info("snapshot saved entity=%s symbol=%s path=%s", entity_type, symbol or "NONE", path)
    return path


def fetch_endpoint(fetcher: GraphFetcher, symbol: str, endpoint: str) -> Any:
    if endpoint in COMPANY_ENDPOINTS:
        return fetcher.company(symbol, endpoint)
    return fetcher.financial(symbol, endpoint)


def fetch_industry(fetcher: GraphFetcher, logger: logging.Logger, observed_at: datetime) -> int:
    errors = 0
    for endpoint in tqdm(INDUSTRY_ENDPOINTS, desc="industry endpoints", leave=False):
        try:
            value = fetcher.industry(endpoint) if endpoint != "list_by_industry" else fetcher.list_by_industry()
            rows = len(as_dataframe(value))
            logger.info("endpoint result symbol=INDUSTRY endpoint=%s rows=%d", endpoint, rows)
            save_result(value, f"industry_{endpoint}", observed_at, logger)
        except Exception:
            errors += 1
            logger.warning("endpoint error symbol=INDUSTRY endpoint=%s", endpoint)
            logger.debug("endpoint traceback symbol=INDUSTRY endpoint=%s", endpoint, exc_info=True)
    return errors


def fetch_symbol(fetcher: GraphFetcher, symbol: str, logger: logging.Logger, outer_bar: Any) -> bool:
    endpoints = COMPANY_ENDPOINTS + FINANCIAL_ENDPOINTS
    observed_at = datetime.now(timezone.utc)
    logger.info("symbol start symbol=%s", symbol)
    errors = 0
    for endpoint in endpoints:
        try:
            value = fetch_endpoint(fetcher, symbol, endpoint)
            rows = len(as_dataframe(value))
            logger.info("endpoint result symbol=%s endpoint=%s rows=%d", symbol, endpoint, rows)
            save_result(value, endpoint, observed_at, logger, symbol=symbol)
        except Exception:
            errors += 1
            logger.warning("endpoint error symbol=%s endpoint=%s", symbol, endpoint)
            logger.debug("endpoint traceback symbol=%s endpoint=%s", symbol, endpoint, exc_info=True)
    logger.info("symbol done symbol=%s errors=%d", symbol, errors)
    outer_bar.update(1)
    outer_bar.set_postfix_str(symbol)
    return errors == 0


def write_pid(pid_file: str | None) -> None:
    if pid_file:
        path = Path(pid_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(os.getpid()), encoding="utf-8")


def main() -> int:
    args = parse_args()
    logger, log_path = configure_logging(args.log_level)
    write_pid(args.pid_file)
    start = time.monotonic()
    try:
        if args.rate_limit <= 0:
            raise ValueError("--rate-limit must be positive")
        symbols = load_symbols(args.symbols, args.max_symbols)
        snapshot.ROOT = Path(args.snapshot_root)
        if not snapshot.ROOT.is_absolute():
            snapshot.ROOT = REPO_ROOT / snapshot.ROOT
        # Shared fetcher — RateLimiter is now thread-safe
        fetcher = GraphFetcher(rate_limiter=RateLimiter(max_requests=args.rate_limit))
        workers = max(1, min(args.workers, 8))
        logger.info("start total_symbols=%d workers=%d log_path=%s", len(symbols), workers, log_path)
        industry_errors = fetch_industry(fetcher, logger, datetime.now(timezone.utc))
        success_count = 0
        error_count = industry_errors
        lock = threading.Lock()

        with tqdm(total=len(symbols), desc="graph symbols", unit="symbol") as outer_bar:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(fetch_symbol, fetcher, sym, logger, outer_bar): sym for sym in symbols}
                for future in as_completed(futures):
                    sym = futures[future]
                    try:
                        ok = future.result()
                        with lock:
                            if ok:
                                success_count += 1
                            else:
                                error_count += 1
                    except Exception:
                        with lock:
                            error_count += 1
                        logger.error("symbol exception symbol=%s", sym, exc_info=True)

        elapsed = time.monotonic() - start
        logger.info(
            "summary total_symbols_attempted=%d success_count=%d error_count=%d skipped=0 total_time=%.2fs snapshot_root=%s",
            len(symbols), success_count, error_count, elapsed, snapshot.ROOT,
        )
        return 0 if error_count == 0 else 1
    except Exception:
        logger.critical("bootstrap failed", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


try:
    from tqdm import tqdm
except ImportError as exc:  # pragma: no cover - dependency contract
    raise SystemExit("tqdm is required: install project dependencies first") from exc

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.quant.data.vnstock import RateLimiter
from omega.quant.graph import snapshot
from omega.quant.graph.fetcher import GraphFetcher


COMPANY_ENDPOINTS = ("info", "shareholders", "subsidiaries", "ownership", "officers", "news")
FINANCIAL_ENDPOINTS = ("income_statement", "cash_flow", "ratios")
INDUSTRY_ENDPOINTS = ("list", "sectors", "list_by_industry")
UNIVERSE_PATH = REPO_ROOT / ".ly_state" / "session" / "vci_universe_hsx_hnx.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", help="Comma-separated symbols overriding the universe file")
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--rate-limit", type=int, default=60)
    parser.add_argument("--pid-file")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    parser.add_argument("--snapshot-root", default=".ly_state/graph_snapshots")
    return parser.parse_args()


def load_symbols(raw_symbols: str | None, max_symbols: int | None) -> list[str]:
    if raw_symbols is not None:
        symbols = [symbol.strip().upper() for symbol in raw_symbols.split(",") if symbol.strip()]
    else:
        with UNIVERSE_PATH.open(encoding="utf-8") as handle:
            universe = json.load(handle)
        symbols = sorted({symbol.upper() for key in ("hsx", "hnx") for symbol in universe.get(key, [])})
    if max_symbols is not None:
        if max_symbols < 0:
            raise ValueError("--max-symbols must be non-negative")
        symbols = symbols[:max_symbols]
    return symbols


def configure_logging(level: str) -> tuple[logging.Logger, Path]:
    log_dir = REPO_ROOT / ".ly_state"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"graph_bootstrap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("graph_bootstrap")
    logger.setLevel(getattr(logging, level))
    logger.handlers.clear()
    for handler in (logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger, log_path


def as_dataframe(value: Any):
    import pandas as pd

    if isinstance(value, pd.DataFrame):
        return value
    if value is None:
        return pd.DataFrame()
    if isinstance(value, list):
        return pd.DataFrame(value)
    if isinstance(value, dict):
        return pd.DataFrame([value])
    return pd.DataFrame([{"value": value}])


def save_result(value: Any, entity_type: str, observed_at: datetime, logger: logging.Logger) -> Path:
    path = snapshot.save_snapshot(as_dataframe(value), entity_type, observed_at)
    logger.info("snapshot saved entity=%s path=%s", entity_type, path)
    return path


def fetch_endpoint(fetcher: GraphFetcher, symbol: str, endpoint: str) -> Any:
    if endpoint in COMPANY_ENDPOINTS:
        return fetcher.company(symbol, endpoint)
    return fetcher.financial(symbol, endpoint)


def fetch_industry(fetcher: GraphFetcher, logger: logging.Logger, observed_at: datetime) -> int:
    errors = 0
    for endpoint in tqdm(INDUSTRY_ENDPOINTS, desc="industry endpoints", leave=False):
        try:
            value = fetcher.industry(endpoint) if endpoint != "list_by_industry" else fetcher.list_by_industry()
            rows = len(as_dataframe(value))
            logger.info("endpoint result symbol=INDUSTRY endpoint=%s rows=%d", endpoint, rows)
            save_result(value, f"industry_{endpoint}", observed_at, logger)
        except Exception:
            errors += 1
            logger.warning("endpoint error symbol=INDUSTRY endpoint=%s", endpoint)
            logger.debug("endpoint traceback symbol=INDUSTRY endpoint=%s", endpoint, exc_info=True)
    return errors


def fetch_symbol(fetcher: GraphFetcher, symbol: str, logger: logging.Logger, outer_bar: Any) -> bool:
    endpoints = COMPANY_ENDPOINTS + FINANCIAL_ENDPOINTS
    observed_at = datetime.now(timezone.utc)
    logger.info("symbol start symbol=%s", symbol)
    errors = 0
    with tqdm(total=len(endpoints), desc=f"{symbol} endpoint groups", leave=False) as inner_bar:
        for endpoint in endpoints:
            try:
                value = fetch_endpoint(fetcher, symbol, endpoint)
                rows = len(as_dataframe(value))
                logger.info("endpoint result symbol=%s endpoint=%s rows=%d", symbol, endpoint, rows)
                save_result(value, endpoint, observed_at, logger)
            except Exception:
                errors += 1
                logger.warning("endpoint error symbol=%s endpoint=%s", symbol, endpoint)
                logger.debug("endpoint traceback symbol=%s endpoint=%s", symbol, endpoint, exc_info=True)
            inner_bar.update(1)
            inner_bar.set_postfix_str(endpoint)
    logger.info("symbol done symbol=%s errors=%d", symbol, errors)
    outer_bar.update(1)
    outer_bar.set_postfix_str(symbol)
    return errors == 0


def write_pid(pid_file: str | None) -> None:
    if pid_file:
        path = Path(pid_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(os.getpid()), encoding="utf-8")


def main() -> int:
    args = parse_args()
    logger, log_path = configure_logging(args.log_level)
    write_pid(args.pid_file)
    start = time.monotonic()
    try:
        if args.rate_limit <= 0:
            raise ValueError("--rate-limit must be positive")
        symbols = load_symbols(args.symbols, args.max_symbols)
        snapshot.ROOT = Path(args.snapshot_root)
        if not snapshot.ROOT.is_absolute():
            snapshot.ROOT = REPO_ROOT / snapshot.ROOT
        fetcher = GraphFetcher(rate_limiter=RateLimiter(max_requests=args.rate_limit))
        logger.info("start total_symbols=%d log_path=%s", len(symbols), log_path)
        industry_errors = fetch_industry(fetcher, logger, datetime.now(timezone.utc))
        success_count = 0
        error_count = industry_errors
        with tqdm(symbols, desc="graph symbols", unit="symbol") as outer_bar:
            for symbol in outer_bar:
                try:
                    if fetch_symbol(fetcher, symbol, logger, outer_bar):
                        success_count += 1
                    else:
                        error_count += 1
                except Exception:
                    error_count += 1
                    logger.error("symbol exception symbol=%s", symbol)
                    logger.debug("symbol traceback symbol=%s", symbol, exc_info=True)
                    outer_bar.update(1)
        elapsed = time.monotonic() - start
        logger.info("summary total_symbols_attempted=%d success_count=%d error_count=%d skipped=0 total_time=%.2fs snapshot_root=%s", len(symbols), success_count, error_count, elapsed, snapshot.ROOT)
        return 0 if error_count == 0 else 1
    except Exception:
        logger.critical("bootstrap failed", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
