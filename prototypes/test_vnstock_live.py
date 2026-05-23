from vnstock.api.quote import Quote
import pandas as pd
import os

# Force UTF-8 output
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Fetch VNM data (using correct parameter names: start, end)
q = Quote(symbol='VNM', source='VCI')
data = q.history(start='2025-05-01', end='2026-05-15')
print(f"VNM: {len(data)} rows")
print(f"Columns: {list(data.columns)}")
print(f"\nFirst 3 rows:")
print(data.head(3))
print(f"\nLast 3 rows:")
print(data.tail(3))
print(f"\nData types:")
print(data.dtypes)
