#!/usr/bin/env python3
"""Fetch all HOSE + HNX symbols from vnstock"""
import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from vnstock import Reference
import pandas as pd

print("=" * 70)
print("FETCHING ALL HOSE + HNX SYMBOLS")
print("=" * 70)

ref = Reference()

# Get HOSE symbols
print("\n✓ Fetching HOSE symbols...")
try:
    hose = ref.listing(exchange='HOSE')
    print(f"  HOSE: {len(hose)} symbols")
    print(hose[['symbol', 'name']].head())
except Exception as e:
    print(f"  Error: {e}")
    hose = pd.DataFrame()

# Get HNX symbols
print("\n✓ Fetching HNX symbols...")
try:
    hnx = ref.listing(exchange='HNX')
    print(f"  HNX: {len(hnx)} symbols")
    print(hnx[['symbol', 'name']].head())
except Exception as e:
    print(f"  Error: {e}")
    hnx = pd.DataFrame()

# Combine
if not hose.empty and not hnx.empty:
    all_symbols = pd.concat([hose, hnx], ignore_index=True)
    symbols_list = all_symbols['symbol'].unique().tolist()
    print(f"\n✓ Total symbols: {len(symbols_list)}")
    print(f"  Symbols: {symbols_list[:20]}...")
    
    # Save to file
    with open('all_symbols.txt', 'w') as f:
        f.write('\n'.join(symbols_list))
    print(f"\n✓ Saved to all_symbols.txt")
