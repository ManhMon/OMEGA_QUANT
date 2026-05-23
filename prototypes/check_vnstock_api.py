#!/usr/bin/env python3
"""Check vnstock Trading.price_history structure"""
from vnstock import Trading

t = Trading()
print("=== Trading.price_history help ===")
help(t.price_history)

print("\n=== Testing price_history sample ===")
try:
    df = t.price_history(symbol='VCB', start_date='2024-01-01', end_date='2024-01-10')
    print(df.head())
except Exception as e:
    print(f"Error: {e}")
