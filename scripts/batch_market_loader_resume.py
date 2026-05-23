#!/usr/bin/env python3
"""
Batch Market Data Loader with Resume & Checkpoint (PARALLEL VERSION)
=====================================================================
Loads full Vietnam market (1,535 symbols) with:
- Parallel fetching (5 threads, 60 req/min rate limit)
- Batch processing (100 symbols/batch)
- Individual batch file saves (no main parquet rewrite)
- Checkpoint after each batch
- Resume from last checkpoint (skip already-loaded symbols)

Usage:
    python scripts/batch_market_loader_resume.py --output OMEGA_QUANT/data/market_2015_now.parquet --start-date 2015-01-01 --end-date 2026-05-12
"""

import argparse
import json
import logging
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set, Dict, Tuple

import pandas as pd
from vnstock import Listing

# Add packages to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "data" / "src"))

from omega.data.vnstock_vci import VnstockVCIDataSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("BatchMarketLoaderResume")


class RateLimiter:
    """Thread-safe rate limiter for API calls (60 req/min = 1 req/sec)."""
    
    def __init__(self, max_requests: int = 60, time_window: float = 60.0):
        self.max_requests = max_requests
        self.time_window = time_window
        self.min_interval = time_window / max_requests  # 1.0 second per request
        self.lock = threading.Lock()
        self.last_request_time = 0.0
    
    def acquire(self):
        """Block until rate limit allows next request."""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            
            if time_since_last < self.min_interval:
                sleep_time = self.min_interval - time_since_last
                time.sleep(sleep_time)
            
            self.last_request_time = time.time()


class BatchMarketLoaderResume:
    """Batch loader with parallel fetching, resume & checkpoint support."""
    
    def __init__(
        self,
        batch_size: int = 100,
        max_workers: int = 5,
        rate_limit_delay: float = 10.0,
        cache_dir: str = "data/cache",
        as_of_time: Optional[datetime] = None
    ):
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.rate_limit_delay = rate_limit_delay
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.as_of_time = as_of_time  # PIT enforcement: must be explicit
        
        # Rate limiter: 60 req/min
        self.rate_limiter = RateLimiter(max_requests=60, time_window=60.0)
        
        self.vnstock_source = VnstockVCIDataSource()
        
        logger.info(f"BatchMarketLoaderResume initialized: batch_size={batch_size}, max_workers={max_workers}, as_of_time={as_of_time}")
    
    def get_batch_dir(self, output_path: str) -> Path:
        """Get directory for individual batch files."""
        output_file = Path(output_path)
        batch_dir = output_file.parent / f"{output_file.stem}_batches"
        batch_dir.mkdir(parents=True, exist_ok=True)
        return batch_dir
    
    def get_checkpoint_path(self, output_path: str) -> Path:
        """Get checkpoint file path for output (in .ly_state/session/)."""
        output_file = Path(output_path)
        # Move to .ly_state/session/ for centralized state management
        state_dir = Path(".ly_state/session")
        state_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_file = state_dir / f"{output_file.stem}_checkpoint.json"
        return checkpoint_file
    
    def load_checkpoint(self, output_path: str) -> dict:
        """Load checkpoint if exists."""
        checkpoint_file = self.get_checkpoint_path(output_path)
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file, 'r') as f:
                    checkpoint = json.load(f)
                logger.info(f"Loaded checkpoint: {len(checkpoint.get('loaded_symbols', []))} symbols already loaded")
                return checkpoint
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")
        return {"loaded_symbols": [], "total_rows": 0, "batches_completed": 0}
    
    def save_checkpoint(self, output_path: str, checkpoint: dict):
        """Save checkpoint with atomic write."""
        checkpoint_file = self.get_checkpoint_path(output_path)
        temp_file = checkpoint_file.with_suffix('.tmp')
        try:
            # Atomic write: write to temp, then rename
            with open(temp_file, 'w') as f:
                json.dump(checkpoint, f, indent=2)
            temp_file.replace(checkpoint_file)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            if temp_file.exists():
                temp_file.unlink()
    
    def get_all_symbols(self) -> List[str]:
        """Get all Vietnam market symbols (excluding covered warrants)."""
        try:
            listing = Listing()
            df_all = listing.all_symbols()
            symbols = df_all['symbol'].tolist()
            
            # Filter out covered warrants (CW patterns)
            # CW symbols typically have names longer than 3 characters
            # Examples: CHPG2301, CFPT2301, CHVM2301, etc.
            # Legitimate equities: DGW, MBS, TCH, POW, OCH, etc. (3 chars or less)
            equity_symbols = [s for s in symbols if len(s) <= 3]
            
            logger.info(f"Fetched {len(symbols)} total symbols, filtered to {len(equity_symbols)} equity symbols (excluded CW with len > 3)")
            return equity_symbols
        except Exception as e:
            logger.error(f"Failed to fetch symbols: {e}")
            raise
    
    def fetch_symbol_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> Tuple[str, Optional[List[Dict]], Optional[str]]:
        """Fetch data for a single symbol with rate limiting.
        
        Returns:
            (symbol, data, error_message)
        """
        try:
            # Rate limit before API call
            self.rate_limiter.acquire()
            
            data = self.vnstock_source.fetch_price_data(symbol, start_date, end_date)
            if data:
                return (symbol, data, None)
            else:
                return (symbol, None, "No data returned")
        except Exception as e:
            return (symbol, None, str(e))
    
    def load_batch(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        batch_num: int,
        total_batches: int
    ) -> pd.DataFrame:
        """Load a batch of symbols with parallel fetching."""
        logger.info(f"Loading batch {batch_num}/{total_batches} ({len(symbols)} symbols) with {self.max_workers} threads...")
        
        # Parallel fetch with ThreadPoolExecutor
        all_data = []
        failed_symbols = []
        successful_count = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_symbol = {
                executor.submit(self.fetch_symbol_data, symbol, start_date, end_date): symbol
                for symbol in symbols
            }
            
            # Process completed tasks
            for future in as_completed(future_to_symbol):
                symbol, data, error = future.result()
                
                if data:
                    all_data.extend(data)
                    successful_count += 1
                    if successful_count % 10 == 0:
                        logger.info(f"  Progress: {successful_count}/{len(symbols)} symbols fetched")
                elif error:
                    logger.warning(f"  {symbol}: {error}")
                    failed_symbols.append(symbol)
        
        if not all_data:
            logger.warning(f"Batch {batch_num}: No data fetched")
            return pd.DataFrame()
        
        # Vectorized DataFrame operations (no row-by-row loops)
        df = pd.DataFrame(all_data)
        
        # Vectorized rename
        df.rename(columns={'symbol': 'ticker', 'timestamp': 'date'}, inplace=True)
        
        # Vectorized datetime conversion
        df['date'] = pd.to_datetime(df['date'], unit='s')
        
        # Vectorized filter: date >= start_date AND date <= end_date (PIT enforcement with upper bound)
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
        
        # P0 Fix (Codex L3): Filter invalid OHLC rows (data quality enforcement)
        # Remove rows where high < low (invalid candle) or close <= 0 (delisted/halt)
        valid_candle = (
            (df['high'] >= df['low']) &
            (df['high'] >= df['open']) &
            (df['high'] >= df['close']) &
            (df['low'] <= df['open']) &
            (df['low'] <= df['close']) &
            (df['close'] > 0)
        )
        df = df[valid_candle].copy()
        
        # P0 Fix (Codex L3): Add PIT columns for T-1 lag enforcement
        # as_of: Point-in-time timestamp (when query was made)
        # available_at: T+1 timestamp (when data becomes available for trading)
        if self.as_of_time:
            df['as_of'] = self.as_of_time
            df['available_at'] = df['date'] + pd.Timedelta(days=1)
        
        # Vectorized column selection (include PIT columns)
        pit_columns = ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'as_of', 'available_at']
        df = df[pit_columns]
        
        logger.info(f"Batch {batch_num}: {len(df)} rows fetched, {successful_count} symbols succeeded, {len(failed_symbols)} failed")
        return df
    
    def load_full_market(
        self,
        start_date: str,
        end_date: str,
        output_path: str
    ) -> pd.DataFrame:
        """Load full Vietnam market with resume support and batch file saves."""
        logger.info("="*70)
        logger.info("BATCH MARKET DATA LOADER (PARALLEL WITH RESUME)")
        logger.info("="*70)
        logger.info(f"Date Range: {start_date} to {end_date}")
        logger.info(f"Output: {output_path}")
        logger.info(f"Max Workers: {self.max_workers}")
        logger.info(f"Rate Limit: 60 req/min")
        logger.info("")
        
        # Load checkpoint
        checkpoint = self.load_checkpoint(output_path)
        loaded_symbols: Set[str] = set(checkpoint.get("loaded_symbols", []))
        
        # Get all symbols
        all_symbols = self.get_all_symbols()
        logger.info(f"Total symbols: {len(all_symbols)}")
        logger.info(f"Already loaded: {len(loaded_symbols)}")
        
        # Filter out already-loaded symbols
        remaining_symbols = [s for s in all_symbols if s not in loaded_symbols]
        logger.info(f"Remaining to load: {len(remaining_symbols)}")
        logger.info("")
        
        # Get batch directory
        batch_dir = self.get_batch_dir(output_path)
        logger.info(f"Batch files directory: {batch_dir}")
        logger.info("")
        
        # Split remaining into batches
        batches = [
            remaining_symbols[i:i + self.batch_size]
            for i in range(0, len(remaining_symbols), self.batch_size)
        ]
        logger.info(f"Batches to process: {len(batches)} (size: {self.batch_size})")
        logger.info("")
        
        # Load batches
        start_time = time.time()
        batches_completed = checkpoint.get("batches_completed", 0)
        
        for batch_num, batch_symbols in enumerate(batches, 1):
            actual_batch_num = batches_completed + batch_num
            
            # Load batch
            df_batch = self.load_batch(
                batch_symbols,
                start_date,
                end_date,
                actual_batch_num,
                batches_completed + len(batches)
            )
            
            if not df_batch.empty:
                # Save batch to individual file (no main parquet rewrite)
                batch_file = batch_dir / f"batch_{actual_batch_num:04d}.parquet"
                df_batch.to_parquet(batch_file, index=False)
                logger.info(f"Saved batch file: {batch_file} ({len(df_batch)} rows)")
                
                # Update checkpoint
                # Only mark symbols as loaded if they were successfully fetched in this batch
                successful_symbols = df_batch['ticker'].unique().tolist()
                loaded_symbols.update(successful_symbols)
                
                checkpoint["loaded_symbols"] = list(loaded_symbols)
                checkpoint["batches_completed"] = actual_batch_num
                checkpoint["batch_files"] = checkpoint.get("batch_files", []) + [str(batch_file)]
                
                if self.as_of_time:
                    checkpoint["last_updated"] = self.as_of_time.isoformat()
                else:
                    raise ValueError("as_of_time must be set for PIT compliance")
                self.save_checkpoint(output_path, checkpoint)
                
                logger.info(f"Checkpoint saved: {len(loaded_symbols)} symbols total")
            
            # Rate limit delay between batches (except last batch)
            if batch_num < len(batches):
                logger.info(f"Waiting {self.rate_limit_delay}s before next batch...")
                time.sleep(self.rate_limit_delay)
            
            logger.info("")
        
        # Consolidate all batch files into final parquet
        logger.info("Consolidating batch files into final parquet...")
        batch_files = list(batch_dir.glob("batch_*.parquet"))
        
        if not batch_files:
            logger.error("No batch files found")
            return pd.DataFrame()
        
        logger.info(f"Found {len(batch_files)} batch files to consolidate")
        
        # Read and concatenate all batch files
        all_batches = []
        for batch_file in sorted(batch_files):
            df_batch = pd.read_parquet(batch_file)
            all_batches.append(df_batch)
            logger.info(f"  Loaded {batch_file.name}: {len(df_batch)} rows")
        
        df_final = pd.concat(all_batches, ignore_index=True)
        
        # Apply date filter to final dataset (PIT enforcement)
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        df_final = df_final[(df_final['date'] >= start_dt) & (df_final['date'] <= end_dt)]
        
        # Save final consolidated parquet
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df_final.to_parquet(output_file, index=False)
        logger.info(f"Saved final parquet: {output_file}")
        
        # P0 Fix (Codex L3): Cleanup batch files after successful consolidation
        try:
            import shutil
            if batch_dir.exists():
                shutil.rmtree(batch_dir)
                logger.info(f"Cleaned up batch directory: {batch_dir}")
        except Exception as e:
            logger.warning(f"Failed to cleanup batch directory: {e}")
        
        # Final summary
        logger.info("")
        logger.info(f"Total rows: {len(df_final)}")
        logger.info(f"Unique tickers: {df_final['ticker'].nunique()}")
        logger.info(f"Date range: {df_final['date'].min()} to {df_final['date'].max()}")
        logger.info("")
        
        elapsed = time.time() - start_time
        logger.info(f"Total time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        logger.info("="*70)
        
        return df_final


def main():
    parser = argparse.ArgumentParser(
        description="Batch Market Data Loader with Resume & Checkpoint",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="OMEGA_QUANT/data/market_2015_now.parquet",
        help="Output Parquet file path"
    )
    
    parser.add_argument(
        "--start-date",
        type=str,
        default="2015-01-01",
        help="Start date (YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD, required for PIT compliance)"
    )
    
    parser.add_argument(
        "--as-of-time",
        type=str,
        default=None,
        help="As-of timestamp for PIT compliance (ISO format, required)"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Symbols per batch (default: 100)"
    )
    
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="Max parallel threads (default: 5, limit for 60 req/min)"
    )
    
    args = parser.parse_args()
    
    # Enforce as_of_time for PIT compliance
    if not args.as_of_time:
        logger.error("--as-of-time is required for PIT compliance")
        sys.exit(1)
    
    try:
        as_of_time = datetime.fromisoformat(args.as_of_time)
    except ValueError:
        logger.error(f"Invalid --as-of-time format: {args.as_of_time}. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
        sys.exit(1)
    
    # Determine date range
    start_date = pd.to_datetime(args.start_date)
    
    if args.end_date:
        end_date = pd.to_datetime(args.end_date)
    else:
        logger.error("--end-date is required for PIT compliance")
        sys.exit(1)
    
    if start_date > end_date:
        logger.error(f"start_date ({start_date.date()}) must be <= end_date ({end_date.date()})")
        sys.exit(1)
    
    # Load
    loader = BatchMarketLoaderResume(
        batch_size=args.batch_size,
        max_workers=args.max_workers,
        as_of_time=as_of_time
    )
    
    try:
        df = loader.load_full_market(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            output_path=args.output
        )
        
        logger.info("SUCCESS: Market data loaded and saved")
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"FAILED: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
