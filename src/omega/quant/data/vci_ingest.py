"""
V21 Data Ingestion - VNStock with VCI Source
Fetches historical OHLCV data and saves to Parquet format.

Requirements:
- pip install vnstock3 pyarrow fastparquet
- Valid VNSTOCK_API_KEY
"""

import os
import pandas as pd
from vnstock import Vnstock
from datetime import datetime, timedelta
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

RAW_PRICE_THRESHOLD = 1_000.0
VND_PRICE_SCALE = 1_000.0

def normalize_price_columns_to_vnd(df):
    price_cols = [col for col in ['open', 'high', 'low', 'close'] if col in df.columns]
    if not price_cols:
        return df
    ref_col = 'close' if 'close' in price_cols else price_cols[0]
    ref_price = pd.to_numeric(df[ref_col], errors='coerce').replace([float('inf'), float('-inf')], float('nan')).median()
    if pd.notna(ref_price) and 0 < float(ref_price) < RAW_PRICE_THRESHOLD:
        df[price_cols] = df[price_cols].astype(float) * VND_PRICE_SCALE
    return df

def ingest_vci_data(symbols, start_date, end_date, output_path='data/v21_market_data.parquet'):
    """
    Ingest data from VCI source using vnstock3 and save to Parquet.
    """
    # Get API Key from environment or prompt
    api_key = os.getenv("VNSTOCK_API_KEY")
    if not api_key:
        print("Error: VNSTOCK_API_KEY not found in environment variables.")
        return None

    # Initialize vnstock3
    stock = Vnstock().stock(symbol=symbols[0], source='vci')
    
    all_data = []
    
    print(f"Starting ingestion for {len(symbols)} symbols from {start_date} to {end_date} using VCI...")
    
    for symbol in symbols:
        try:
            # Update symbol for the stock object
            stock = Vnstock().stock(symbol=symbol, source='vci')
            
            # Fetch historical data
            # vnstock3 history uses start_date and end_date in YYYY-MM-DD
            df = stock.quote.history(start=start_date, end=end_date)
            
            if df is not None and not df.empty:
                df['symbol'] = symbol
                all_data.append(df)
                print(f"  Successfully fetched {len(df)} rows for {symbol}")
            else:
                print(f"  No data found for {symbol}")
                
        except Exception as e:
            print(f"  Error fetching {symbol}: {e}")
            
    if not all_data:
        print("No data collected.")
        return None
        
    # Combine all DataFrames
    full_df = pd.concat(all_data, ignore_index=True)
    full_df = normalize_price_columns_to_vnd(full_df)
    
    # Ensure date column is datetime
    if 'time' in full_df.columns:
        full_df['date'] = pd.to_datetime(full_df['time'])
    elif 'date' in full_df.columns:
        full_df['date'] = pd.to_datetime(full_df['date'])
        
    # Save to Parquet
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    full_df.to_parquet(output_path, index=False)
    
    print(f"\nSUCCESS: Saved {len(full_df)} rows to {output_path}")
    return full_df

if __name__ == "__main__":
    # Example symbols (VN30)
    vn30_symbols = [
        'ACB', 'BCM', 'BID', 'BVH', 'CTG', 'FPT', 'GAS', 'GVR', 'HDB', 'HPG', 
        'MBB', 'MSN', 'MWG', 'PLX', 'POW', 'SAB', 'SHB', 'SSB', 'SSI', 'STB', 
        'TCB', 'TPB', 'VCB', 'VHM', 'VIB', 'VIC', 'VJC', 'VNM', 'VPB', 'VRE'
    ]
    
    # Set timeframe
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d') # 5 years
    
    # Execute
    ingest_vci_data(vn30_symbols, start_date, end_date)
