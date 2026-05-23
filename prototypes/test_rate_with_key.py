import os, sys
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Set the API key BEFORE importing
os.environ['VNSTOCK_API_KEY'] = 'vnstock_e05b9f4c0d4eacd20b900cf99688d3c1'

from vnstock.ui import Market
import time

print("Testing rate limit with API key...")

mkt = Market()
print("Market initialized with API key")

# Try rate test - fetch 3 symbols quickly
symbols = ["VCB", "FPT", "HPG"]
for s in symbols:
    t0 = time.time()
    try:
        df = mkt.equity(s).ohlcv(start="2025-01-01", end="2025-01-31")
        t = time.time() - t0
        print(f"{s}: {len(df)} rows in {t:.2f}s")
    except Exception as e:
        print(f"{s}: Error - {e}")

print("\nRate limit test complete.")
