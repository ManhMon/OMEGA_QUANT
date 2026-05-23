#!/usr/bin/env python3
"""
Sample Data Generator for OMEGA_QUANT Demo
Backend Engineer (Role 9) - Phase 10

Generates sample market data for demo purposes.
"""

from __future__ import annotations

import argparse
import logging
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("SampleDataGenerator")


def generate_sample_data(
    symbols: List[str],
    start_date: str,
    end_date: str,
    output_dir: str
) -> None:
    """Generate sample market data for demo."""
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    dates = pd.date_range(start=start, end=end, freq="B")  # Business days only
    
    logger.info(f"Generating data for {len(symbols)} symbols over {len(dates)} trading days")
    
    for symbol in symbols:
        # Generate OHLCV data
        data = []
        price = 100000 + random.uniform(-50000, 50000)  # Start around 100k-150k VND
        
        for date in dates:
            # Random walk with drift
            drift = 0.0002  # Slight upward trend
            volatility = 0.02  # 2% daily volatility
            
            change = np.random.normal(drift, volatility)
            price = price * (1 + change)
            
            # Generate OHLC
            high = price * (1 + abs(np.random.normal(0, 0.01)))
            low = price * (1 - abs(np.random.normal(0, 0.01)))
            open_price = low + random.uniform(0, price - low)
            close = price
            volume = random.randint(10000, 1000000)
            
            data.append({
                "date": date.strftime("%Y-%m-%d"),
                "symbol": symbol,
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": volume
            })
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Save to CSV
        symbol_path = output_path / f"{symbol.lower()}.csv"
        df.to_csv(symbol_path, index=False)
        
        logger.info(f"Generated {len(df)} rows for {symbol} -> {symbol_path}")
    
    logger.info(f"Sample data generation complete. Output: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate sample market data for OMEGA_QUANT demo")
    parser.add_argument("--symbols", nargs="+", default=["VCB", "FPT", "VHM", "HPG", "MSB"],
                        help="List of symbols to generate data for")
    parser.add_argument("--start-date", default="2025-01-01",
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2025-12-31",
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="data/market",
                        help="Output directory for generated data")
    
    args = parser.parse_args()
    
    generate_sample_data(
        symbols=args.symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir
    )


if __name__ == "__main__":
    main()
