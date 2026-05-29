"""Fetch intraday tick/minute data from vnstock for top 30 liquid tickers.

Backend Engineer (Role 9) - OMEGA_QUANT

Design:
- Source: vnstock v4.0.2 (Quote.intraday)
- Universe: top 30 most-liquid tickers by median daily volume from
  ``data/market_2015_now.parquet``.
- Per-ticker fallback chain: VCI -> TCBS.
- Output:
    * ``data/intraday/{date}/{ticker}.parquet`` per ticker
    * ``data/intraday/{date}_all.parquet`` combined frame
- PIT Safety: only fetches up to ``datetime.now()``; for past dates we still
  let vnstock return its full session data because that data is already
  finalized and historical.

Usage:
    python scripts/fetch_intraday_data.py
    python scripts/fetch_intraday_data.py --date 2026-05-29 --interval 1m
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import datetime, date as date_cls
from pathlib import Path
from typing import List, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKET_PARQUET = REPO_ROOT / "data" / "market_2015_now.parquet"
INTRADAY_ROOT = REPO_ROOT / "data" / "intraday"
DEFAULT_TOP_N = 30
DEFAULT_PAGE_SIZE = 10_000
DEFAULT_SOURCES = ("VCI", "TCBS")


# ---------------------------------------------------------------------------
# Universe selection
# ---------------------------------------------------------------------------


def load_top_liquid_tickers(
    market_path: Path = MARKET_PARQUET,
    top_n: int = DEFAULT_TOP_N,
    lookback_days: int = 252,
) -> List[str]:
    """Return the ``top_n`` tickers ranked by median daily volume.

    Uses the most recent ``lookback_days`` of trading data so the universe
    reflects current liquidity rather than historical heavyweights.
    """
    if not market_path.exists():
        raise FileNotFoundError(f"Market parquet not found: {market_path}")

    df = pd.read_parquet(market_path, columns=["ticker", "date", "volume"])
    if df.empty:
        raise ValueError(f"Market parquet is empty: {market_path}")

    df["date"] = pd.to_datetime(df["date"])
    cutoff = df["date"].max() - pd.Timedelta(days=lookback_days)
    recent = df[df["date"] >= cutoff]
    if recent.empty:
        recent = df  # fallback to full history

    median_vol = (
        recent.groupby("ticker", as_index=True)["volume"]
        .median()
        .sort_values(ascending=False)
    )
    return median_vol.head(top_n).index.tolist()


# ---------------------------------------------------------------------------
# vnstock fetch helpers
# ---------------------------------------------------------------------------


def _fetch_with_source(
    ticker: str,
    source: str,
    page_size: int,
) -> Optional[pd.DataFrame]:
    """Fetch intraday data for one ticker via a specific vnstock source."""
    from vnstock import Quote  # local import keeps module import light

    quote = Quote(symbol=ticker, source=source)
    df = quote.intraday(symbol=ticker, page_size=page_size)
    if df is None or len(df) == 0:
        return None
    df = df.copy()
    df["ticker"] = ticker
    df["source"] = source
    return df


def fetch_intraday_for_ticker(
    ticker: str,
    sources: tuple = DEFAULT_SOURCES,
    page_size: int = DEFAULT_PAGE_SIZE,
    sleep_between_sources: float = 0.5,
) -> Optional[pd.DataFrame]:
    """Try each source in order; return the first non-empty frame."""
    for src in sources:
        try:
            df = _fetch_with_source(ticker, src, page_size)
            if df is not None and not df.empty:
                return df
        except Exception as exc:  # noqa: BLE001 - intentional broad catch
            print(
                f"  [{ticker}] source={src} failed: {exc.__class__.__name__}: {exc}",
                flush=True,
            )
        time.sleep(sleep_between_sources)
    return None


# ---------------------------------------------------------------------------
# PIT-safe time clipping
# ---------------------------------------------------------------------------


def clip_to_pit(
    df: pd.DataFrame,
    target_date: date_cls,
    now: datetime,
) -> pd.DataFrame:
    """Drop rows that occur after ``now`` when fetching today's data.

    For historical dates the data is already finalized; we still filter to
    ``target_date`` so we never accidentally store future bars.
    """
    if df.empty:
        return df

    time_col = None
    for cand in ("time", "timestamp", "datetime", "tradingDate"):
        if cand in df.columns:
            time_col = cand
            break
    if time_col is None:
        return df  # nothing to clip on

    ts = pd.to_datetime(df[time_col], errors="coerce")
    mask = ts.notna() & (ts.dt.date == target_date)
    if target_date == now.date():
        mask &= ts <= pd.Timestamp(now)
    return df.loc[mask].copy()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def fetch_all(
    target_date: date_cls,
    interval: str,
    top_n: int,
    page_size: int,
) -> pd.DataFrame:
    """Fetch intraday for the top-N universe and persist per-ticker parquets."""
    tickers = load_top_liquid_tickers(top_n=top_n)
    print(f"Universe ({len(tickers)} tickers): {', '.join(tickers)}", flush=True)

    out_dir = INTRADAY_ROOT / target_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    frames: List[pd.DataFrame] = []
    failed: List[str] = []

    for i, tkr in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {tkr} ...", flush=True)
        try:
            raw = fetch_intraday_for_ticker(tkr, page_size=page_size)
            if raw is None or raw.empty:
                failed.append(tkr)
                print(f"  [{tkr}] no data from any source", flush=True)
                continue

            clipped = clip_to_pit(raw, target_date, now)
            if clipped.empty:
                # Persist raw too so we have an audit trail, but warn.
                print(
                    f"  [{tkr}] no rows for {target_date} after PIT clip "
                    f"(raw={len(raw)} rows)",
                    flush=True,
                )
                continue

            clipped["interval"] = interval
            ticker_path = out_dir / f"{tkr}.parquet"
            clipped.to_parquet(ticker_path, index=False)
            frames.append(clipped)
            print(
                f"  [{tkr}] saved {len(clipped)} rows -> {ticker_path.name}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - keep going on per-ticker errors
            failed.append(tkr)
            print(f"  [{tkr}] unexpected error: {exc}", flush=True)
            traceback.print_exc()

    combined = (
        pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    )

    combined_path = INTRADAY_ROOT / f"{target_date.isoformat()}_all.parquet"
    if not combined.empty:
        combined.to_parquet(combined_path, index=False)

    print("=" * 60, flush=True)
    print(
        "Summary: "
        f"date={target_date} interval={interval} "
        f"tickers_ok={len(frames)} tickers_failed={len(failed)} "
        f"total_rows={len(combined)}",
        flush=True,
    )
    if failed:
        print(f"Failed tickers: {', '.join(failed)}", flush=True)
    if not combined.empty:
        print(f"Combined parquet: {combined_path}", flush=True)

    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().date().isoformat(),
        help="Trading date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default="1m",
        help="Bar interval label stored alongside the data (default: 1m).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help="Number of most-liquid tickers to fetch (default: 30).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="vnstock page size per request (default: 10000).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError as exc:
        print(f"Invalid --date '{args.date}': {exc}", file=sys.stderr)
        return 2

    fetch_all(
        target_date=target,
        interval=args.interval,
        top_n=args.top_n,
        page_size=args.page_size,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
