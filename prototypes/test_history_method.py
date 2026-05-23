import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from vnstock import Trading
import pandas as pd

t = Trading()
print("Testing history()...")

try:
    # Testing alternative method 'history'
    df = t.history(symbol='VNM', start_date='2025-01-01', end_date='2025-01-31')
    print(f"✅ SUCCESS! Got {len(df)} rows.")
    print(df.head())
except Exception as e:
    print(f"❌ history() FAILED: {e}")
