"""
HOSE/HNX Full Market Data Rebuild Script
Phase 12 Audit - 2026-06-12
Target: data/market_hose_hnx_2015_now_rebuilt_20260612.parquet
Source: vnstock VCI Quote.history() per symbol
Price: Source thousands -> VND (x1000)
"""
import sys
import os
import time
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

# ── Config ──
REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = REPO_ROOT / "data" / "market_2015_now.parquet"
OUTPUT_PATH = REPO_ROOT / "data" / "market_hose_hnx_2015_now_rebuilt_20260612.parquet"
START_DATE = "2015-01-01"
END_DATE = "2026-06-12"
VND_SCALE = 1000.0
RAW_THRESHOLD = 1000.0
RATE_LIMIT_SEC = 0.3  # seconds between API calls
MAX_RETRIES = 3
BATCH_SIZE = 50  # save progress every 50 symbols

# Known exchange mapping (from VCI data, structure_features, and prior audits)
EXCHANGE_MAP = {
    # HOSE
    'VCB': 'HOSE', 'HPG': 'HOSE', 'FPT': 'HOSE', 'VIC': 'HOSE', 'VHM': 'HOSE',
    'MSN': 'HOSE', 'MWG': 'HOSE', 'VNM': 'HOSE', 'SAB': 'HOSE', 'GAS': 'HOSE',
    'BID': 'HOSE', 'VPB': 'HOSE', 'CTG': 'HOSE', 'TCB': 'HOSE', 'MBB': 'HOSE',
    'HDB': 'HOSE', 'STB': 'HOSE', 'VIB': 'HOSE', 'TPB': 'HOSE', 'ACB': 'HOSE',
    'MSN': 'HOSE', 'PLX': 'HOSE', 'VJC': 'HOSE', 'VRE': 'HOSE', 'POW': 'HOSE',
    'BCM': 'HOSE', 'GVR': 'HOSE', 'VPI': 'HOSE', 'NVL': 'HOSE', 'PDR': 'HOSE',
    'KDH': 'HOSE', 'REE': 'HOSE', 'SSI': 'HOSE', 'HCM': 'HOSE', 'VCI': 'HOSE',
    'FUEVFVND': 'HOSE', 'E1VFVN30': 'HOSE', 'FUEKIVFS': 'HOSE',
    'DXG': 'HOSE', 'NLG': 'HOSE', 'HPX': 'HOSE', 'HDG': 'HOSE',
    'HSG': 'HOSE', 'NKG': 'HOSE', 'POM': 'HOSE', 'TLH': 'HOSE',
    'DPM': 'HOSE', 'DGC': 'HOSE', 'BMP': 'HOSE', 'NTP': 'HOSE',
    'DHG': 'HOSE', 'IMP': 'HOSE', 'TRA': 'HOSE', 'DBT': 'HOSE',
    'VSC': 'HOSE', 'GMD': 'HOSE', 'STG': 'HOSE',
    'PET': 'HOSE', 'PVD': 'HOSE', 'PVS': 'HOSE', 'PVT': 'HOSE',
    'NT2': 'HOSE', 'VSH': 'HOSE', 'TMP': 'HOSE', 'TDM': 'HOSE',
    'FCN': 'HOSE', 'HHV': 'HOSE', 'CTD': 'HOSE', 'HBC': 'HOSE',
    'PNJ': 'HOSE', 'FRT': 'HOSE', 'DGW': 'HOSE',
    # HNX
    'SHB': 'HNX', 'SHS': 'HNX', 'VCG': 'HNX', 'VNR': 'HNX',
    'PVS': 'HNX', 'PVC': 'HNX', 'PVX': 'HNX',
    'LCG': 'HNX', 'IDJ': 'HNX', 'CEO': 'HNX',
    'LHC': 'HNX', 'NTP': 'HNX', 'BCC': 'HNX',
    'HUT': 'HNX', 'VGC': 'HNX', 'NRC': 'HNX',
    'TNG': 'HNX', 'MBS': 'HNX', 'IVS': 'HNX',
    'VC3': 'HNX', 'VC6': 'HNX', 'VC9': 'HNX',
    'DNP': 'HNX', 'SLS': 'HNX', 'S99': 'HNX',
    'SBS': 'HNX', 'BVS': 'HNX', 'WSS': 'HNX',
    # UPCOM
    'QNS': 'UPCOM', 'LTG': 'UPCOM', 'ACV': 'UPCOM',
    'VTP': 'UPCOM', 'BSR': 'UPCOM', 'OIL': 'UPCOM',
    'MCH': 'UPCOM', 'MSN': 'UPCOM',
}

def get_exchange(ticker: str) -> str:
    """Get exchange for ticker from known mapping, or UNKNOWN."""
    return EXCHANGE_MAP.get(ticker.upper(), 'UNKNOWN')


def fetch_symbol_history(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch OHLCV history for a single symbol from VCI via vnstock."""
    from vnstock import Quote
    q = Quote(symbol=symbol, source='VCI')
    df = q.history(start=start, end=end, interval='1D')
    if df is None or df.empty:
        return pd.DataFrame()

    # Standardize columns
    df = df.rename(columns={'time': 'date'})
    df['date'] = pd.to_datetime(df['date']).dt.normalize()

    # Price scaling: VCI returns thousands, convert to VND
    price_cols = ['open', 'high', 'low', 'close']
    for col in price_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Heuristic: if median close < 1000, scale x1000
    if 'close' in df.columns:
        ref = df['close'].median()
        if pd.notna(ref) and 0 < ref < RAW_THRESHOLD:
            for col in price_cols:
                if col in df.columns:
                    df[col] = df[col] * VND_SCALE

    df['volume'] = pd.to_numeric(df.get('volume', pd.Series(dtype=float)), errors='coerce').fillna(0)
    df['ticker'] = symbol.upper()
    df['exchange'] = get_exchange(symbol)

    # PIT columns
    df['as_of'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    df['available_at'] = df['date'] + timedelta(days=1)

    # Select & order columns
    cols = ['ticker', 'date', 'exchange', 'open', 'high', 'low', 'close', 'volume', 'as_of', 'available_at']
    existing_cols = [c for c in cols if c in df.columns]
    return df[existing_cols].copy()


def main():
    t0 = time.time()
    print(f"[{datetime.now().isoformat()}] Starting HOSE/HNX rebuild")
    print(f"  Canonical: {CANONICAL_PATH}")
    print(f"  Output:    {OUTPUT_PATH}")
    print(f"  Period:    {START_DATE} to {END_DATE}")

    # Get ticker universe from canonical
    canonical = pd.read_parquet(CANONICAL_PATH)
    all_tickers = sorted(canonical['ticker'].unique().tolist())
    print(f"  Universe:  {len(all_tickers)} tickers from canonical")
    del canonical

    # Filter to len <= 3 (exclude covered warrants etc)
    tickers = [t for t in all_tickers if len(t) <= 3]
    print(f"  Filtered:  {len(tickers)} tickers (len <= 3)")

    # Check for checkpoint
    checkpoint_path = REPO_ROOT / ".ly_state" / "session" / "hose_hnx_rebuild_checkpoint.json"
    completed = set()
    all_frames = []
    if checkpoint_path.exists():
        with open(checkpoint_path) as f:
            ckpt = json.load(f)
        completed = set(ckpt.get('completed', []))
        if ckpt.get('partial_path'):
            try:
                partial = pd.read_parquet(ckpt['partial_path'])
                all_frames.append(partial)
                print(f"  Resuming:  {len(completed)} tickers done, loaded partial file")
            except Exception as e:
                print(f"  Checkpoint load failed: {e}, starting fresh")
                completed = set()
                all_frames = []

    remaining = [t for t in tickers if t not in completed]
    print(f"  Remaining: {len(remaining)} tickers to fetch")

    # Fetch loop
    errors = []
    stats = {'fetched': 0, 'empty': 0, 'errors': 0, 'rows': 0}

    for i, symbol in enumerate(remaining):
        try:
            df = fetch_symbol_history(symbol, START_DATE, END_DATE)
            if df.empty:
                stats['empty'] += 1
            else:
                # OHLC invariant filter
                valid = (
                    (df['high'] >= df['low']) &
                    (df['high'] >= df['open']) &
                    (df['high'] >= df['close']) &
                    (df['low'] <= df['open']) &
                    (df['low'] <= df['close']) &
                    (df['close'] > 0)
                )
                df = df[valid].copy()
                all_frames.append(df)
                stats['fetched'] += 1
                stats['rows'] += len(df)

            completed.add(symbol)

            # Progress report
            if (i + 1) % 10 == 0 or i == len(remaining) - 1:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (len(remaining) - i - 1) / rate if rate > 0 else 0
                print(f"  [{i+1}/{len(remaining)}] {symbol}: {len(df)} rows | "
                      f"Total rows: {stats['rows']} | "
                      f"Rate: {rate:.1f}/s | ETA: {eta:.0f}s")

            # Save checkpoint every BATCH_SIZE
            if (i + 1) % BATCH_SIZE == 0:
                _save_checkpoint(all_frames, completed, checkpoint_path, OUTPUT_PATH, stats)

        except Exception as e:
            stats['errors'] += 1
            errors.append({'symbol': symbol, 'error': str(e), 'tb': traceback.format_exc()})
            if stats['errors'] <= 5:
                print(f"  ERROR {symbol}: {e}")

        time.sleep(RATE_LIMIT_SEC)

    # Final save
    if all_frames:
        result = pd.concat(all_frames, ignore_index=True)
        # Deduplicate
        result = result.drop_duplicates(subset=['ticker', 'date'], keep='last')
        result = result.sort_values(['ticker', 'date']).reset_index(drop=True)
        result.to_parquet(OUTPUT_PATH, index=False)
        print(f"\n[DONE] Saved {len(result)} rows to {OUTPUT_PATH}")
        print(f"  Tickers: {result['ticker'].nunique()}")
        print(f"  Date range: {result['date'].min()} to {result['date'].max()}")
    else:
        print("\n[WARN] No data fetched at all!")

    # Save final stats
    summary = {
        'timestamp': datetime.now().isoformat(),
        'total_tickers_attempted': len(tickers),
        'completed': len(completed),
        'stats': stats,
        'errors': errors[:50],  # first 50 errors
        'output_path': str(OUTPUT_PATH),
        'elapsed_seconds': time.time() - t0,
    }
    stats_path = REPO_ROOT / ".ly_state" / "session" / "hose_hnx_rebuild_stats.json"
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    with open(stats_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  Stats saved to {stats_path}")

    return result if all_frames else None


def _save_checkpoint(frames, completed, ckpt_path, output_path, stats):
    """Save intermediate checkpoint."""
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    if frames:
        partial = pd.concat(frames, ignore_index=True)
        partial_path = str(output_path).replace('.parquet', '_partial.parquet')
        partial.to_parquet(partial_path, index=False)
    else:
        partial_path = None
    ckpt = {
        'completed': list(completed),
        'partial_path': partial_path,
        'stats': stats,
        'timestamp': datetime.now().isoformat()
    }
    with open(ckpt_path, 'w') as f:
        json.dump(ckpt, f, indent=2, default=str)


if __name__ == '__main__':
    result = main()
