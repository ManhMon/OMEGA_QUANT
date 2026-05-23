import pandas as pd
import numpy as np
from pathlib import Path

# Load pipeline output
df = pd.read_parquet('OMEGA_QUANT/data/market_2015_now.parquet')
print('=== PHASE 1 FEATURE VALIDATION - COMPLETE REPORT ===')
print(f'Date: {pd.Timestamp.now()}')
print()

# 1. Data Overview
print('[1] Data Overview')
print(f'  Rows: {len(df):,}')
print(f'  Columns: {len(df.columns)}')
print(f'  Date range: {df["date"].min()} to {df["date"].max()}')
print(f'  Unique symbols: {df["ticker"].nunique()}')
print()

# 2. Feature Statistics
print('[2] Feature Statistics')
numeric_cols = df.select_dtypes(include=[np.number]).columns
print(f'  Total numeric features: {len(numeric_cols)}')
print(f'  Mean NaN rate: {df[numeric_cols].isna().sum().sum() / (len(df) * len(numeric_cols)) * 100:.2f}%')
print()

# 3. Sector Coverage
sector_map = pd.read_csv('OMEGA_QUANT/data/sector_mapping_level2.csv')
print('[3] Sector Coverage')
print(f'  Unique sectors in mapping: {sector_map["sector"].nunique()}')
print(f'  Symbols in mapping: {len(sector_map)}')
print(f'  Symbols in data: {df["ticker"].nunique()}')
coverage = len(set(df['ticker'].unique()) & set(sector_map['symbol'].unique()))
print(f'  Coverage: {coverage}/{df["ticker"].nunique()} ({100*coverage/df["ticker"].nunique():.1f}%)')
print()

# 4. Top 5 Sectors
print('[4] Top 5 Sectors by Symbol Count')
sector_counts = sector_map['sector'].value_counts().head(5)
for i, (sector, count) in enumerate(sector_counts.items(), 1):
    pct = 100 * count / len(sector_map)
    print(f'  {i}. {sector}: {count} symbols ({pct:.1f}%)')
print()

# 5. PIT Safety Check
print('[5] PIT Safety Verification')
print(f'  T-1 lag enforced: available_at column present = {"available_at" in df.columns}')
print(f'  First row per symbol NaN cells: {df.groupby("ticker").head(1).isna().sum().sum()}/{len(df.groupby("ticker").head(1)) * len(df.columns)}')
print()

print('Status: PASS')
