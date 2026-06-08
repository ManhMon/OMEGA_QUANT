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

warnings.filterwarnings('ignore')

RAW_PRICE_THRESHOLD = 1_000.0
VND_PRICE_SCALE = 1_000.0

def normalize_price_columns_to_vnd(df: pd.DataFrame) -> pd.DataFrame:
    price_cols = [col for col in ['open', 'high', 'low', 'close'] if col in df.columns]
    if not price_cols:
        return df
    ref_col = 'close' if 'close' in price_cols else price_cols[0]
    ref_price = pd.to_numeric(df[ref_col], errors='coerce').replace([float('inf'), float('-inf')], float('nan')).median()
    if pd.notna(ref_price) and 0 < float(ref_price) < RAW_PRICE_THRESHOLD:
        df[price_cols] = df[price_cols].astype(float) * VND_PRICE_SCALE
    return df

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
