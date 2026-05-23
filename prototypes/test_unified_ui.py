import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Set API key
os.environ['VNSTOCK_API_KEY'] = 'vnstock_e05b9f4c0d4eacd20b900cf99688d3c1'

from vnstock import Market
import pandas as pd

print("=" * 70)
print("VNSTOCK UNIFIED UI - Market Layer (OHLCV)")
print("=" * 70)

try:
    mkt = Market()
    print("✓ Market() initialized")
    
    # Test OHLCV - this is the correct API
    print("\nFetching OHLCV for ACB...")
    df = mkt.equity("ACB").ohlcv(start="2026-04-01", end="2026-04-15")
    print(f"✓ SUCCESS! Got {len(df)} rows from REAL API")
    print(df.head())
    
    print("\nFetching OHLCV for VCB...")
    df2 = mkt.equity("VCB").ohlcv(start="2026-04-01", end="2026-04-15")
    print(f"✓ SUCCESS! Got {len(df2)} rows for VCB")
    print(df2.head())
    
except Exception as e:
    print(f"❌ FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()