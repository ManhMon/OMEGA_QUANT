#!/usr/bin/env python3
import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Set API key
api_key = "vnstock_e05b9f4c0d4eacd20b900cf99688d3c1"
os.environ['VNSTOCK_API_KEY'] = api_key

from vnstock import Trading
import pandas as pd

print(f"Testing price_history with key: {api_key[:12]}...")

try:
    t = Trading()
    # Try to get data for a common stock
    df = t.price_history(symbol='VNM', start_date='2025-01-01', end_date='2025-01-31', resolution='1D')
    print(f"✅ SUCCESS! Got {len(df)} rows from REAL API.")
    print(df.head())
    
    # Check if this is the sponsored tier
    if hasattr(t, 'is_sponsored') and t.is_sponsored:
        print("✓ Authenticated as Sponsored/Insiders tier.")
    else:
        print("! Authenticated as Free tier (with key).")
        
except Exception as e:
    print(f"❌ FAILED: {type(e).__name__}: {e}")
    
    # Try alternative initialization if direct doesn't work
    print("\nTrying legacy/alternative method...")
    try:
        from vnstock import Vnstock
        v = Vnstock(api_key=api_key)
        df = v.stock.price_history(symbol='VNM', start_date='2025-01-01', end_date='2025-01-31')
        print(f"✅ SUCCESS (Legacy)! Got {len(df)} rows.")
    except Exception as e2:
        print(f"❌ LEGACY FAILED: {type(e2).__name__}: {e2}")
