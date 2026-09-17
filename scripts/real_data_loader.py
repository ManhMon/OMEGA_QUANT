#!/usr/bin/env python3
"""
Shared Real Data Loader for OMEGA_QUANT E2E Pipelines
Loads real market data from data/market_2015_now.parquet
"""

import pandas as pd
import numpy as np
from datetime import datetime

def load_real_vn_data(n_days=252, symbols=None):
    """
    Load real VN stock data from parquet and format as a dictionary of OHLCV DataFrames.
    Ensures correct alignment and returns returns_df + price_df.
    """
    if symbols is None:
        symbols = ['VNM', 'VIC', 'HPG', 'TCB', 'BID']
        
    parquet_path = 'data/market_2015_now.parquet'
    try:
        df = pd.read_parquet(parquet_path)
    except Exception as e:
        raise FileNotFoundError(f"Cannot read real market data at {parquet_path}: {e}")
        
    # Filter tickers
    df_filtered = df[df['ticker'].isin(symbols)].copy()
    df_filtered['date'] = pd.to_datetime(df_filtered['date'])
    
    # Pivot to verify structure
    pivot_close = df_filtered.pivot(index='date', columns='ticker', values='close').sort_index()
    
    # Get last n_days
    last_dates = pivot_close.index[-n_days:]
    
    data = {}
    for sym in symbols:
        sym_df = df_filtered[df_filtered['ticker'] == sym].set_index('date').sort_index()
        # Keep only the last n_days index aligned with overall index
        sym_df = sym_df.reindex(last_dates)
        
        # Forward fill only: backward fill would use a future observation.
        sym_df[['open', 'high', 'low', 'close', 'volume']] = sym_df[['open', 'high', 'low', 'close', 'volume']].ffill()
        
        data[sym] = pd.DataFrame({
            'open': sym_df['open'],
            'high': sym_df['high'],
            'low': sym_df['low'],
            'close': sym_df['close'],
            'volume': sym_df['volume']
        }, index=last_dates)
        
    print(f"[LOAD] Loaded REAL VN stock data from {parquet_path} ({len(last_dates)} days, {len(symbols)} symbols)")
    return data, symbols
