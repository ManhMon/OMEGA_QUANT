import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from vnstock import stock_historical_data
import pandas as pd

print("Testing LEGACY stock_historical_data...")

try:
    # Legacy API for free users
    df = stock_historical_data(symbol='VNM', start_date='2025-01-01', end_date='2025-01-31', resolution='1D', type='stock')
    print(f"✅ SUCCESS! Got {len(df)} rows from LEGACY API.")
    print(df.head())
except Exception as e:
    print(f"❌ LEGACY API FAILED: {type(e).__name__}: {e}")
