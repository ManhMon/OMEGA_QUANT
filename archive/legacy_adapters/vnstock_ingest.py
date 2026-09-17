"""
V21 Data Ingestion - VNStock with VCI Source
Fetches historical OHLCV data and saves to Parquet format.
"""

import os
import warnings
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd
from vnstock import Vnstock

# VND_FULL price-unit contract guard (centralized)
from omega.data.vnd_price_contract import (
    VND_FULL,
    ensure_vnd_scale,
    RAW_PRICE_THRESHOLD,
    VND_PRICE_SCALE,
)

warnings.filterwarnings('ignore')

def normalize_price_columns_to_vnd(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize price columns to VND_FULL using centralized guard."""
    return ensure_vnd_scale(df, price_cols=["open", "high", "low", "close"])

def ingest_vci_data(symbols: List[str], start_date: str, end_date: str, output_path: str = 'data/v21_market_data.parquet') -> Optional[pd.DataFrame]:
    api_key = os.getenv("VNSTOCK_API_KEY", "dummy_key")
    os.environ['VNSTOCK_API_KEY'] = api_key

    if not symbols:
        return None

    stock = Vnstock().stock(symbol=symbols[0], source='vci')
    all_data = []
    
    for symbol in symbols:
        try:
            stock = Vnstock().stock(symbol=symbol, source='vci')
            df = stock.quote.history(start=start_date, end=end_date)
            
            if df is not None and not df.empty:
                df['symbol'] = symbol
                all_data.append(df)
        except Exception:
            pass
            
    if not all_data:
        return None
        
    full_df = pd.concat(all_data, ignore_index=True)
    full_df = normalize_price_columns_to_vnd(full_df)
    
    if 'time' in full_df.columns:
        full_df['date'] = pd.to_datetime(full_df['time'])
    elif 'date' in full_df.columns:
        full_df['date'] = pd.to_datetime(full_df['date'])
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    full_df.to_parquet(output_path, index=False)
    
    return full_df
