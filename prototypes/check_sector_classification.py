import pandas as pd
from pathlib import Path
import sys

parquet_path = Path('OMEGA_QUANT/OMEGA_QUANT/data/market_2015_now_cleaned.parquet')
df = pd.read_parquet(parquet_path)

print('=== SECTOR CLASSIFICATION ===')
print(f'Total rows: {len(df)}')
print(f'Unique symbols: {len(df["ticker"].unique())}')

if 'sector' in df.columns:
    print(f'Sector column found: {len(df["sector"].unique())} unique sectors')
    print(f'Sector values: {df["sector"].unique()[:10]}')
else:
    print('ERROR: No sector column in data')

sys.path.insert(0, str(Path('OMEGA_QUANT/packages/core/src').resolve()))
from omega.core.structure_features import get_structure_data

df_renamed = df.rename(columns={'ticker': 'symbol'})
df_renamed['date'] = pd.to_datetime(df_renamed['date'])
df_indexed = df_renamed.set_index(['date', 'symbol']).sort_index()

structure = get_structure_data(df_indexed[['close', 'volume', 'high', 'low', 'open']])

sector_cols = [col for col in structure.columns if 'sector' in col.lower()]
print(f'\nSector columns in output: {len(sector_cols)}')
print(f'Columns: {sector_cols}')

print('\nSample sector data (first 5 rows):')
print(structure[sector_cols].head())

print(f'\nSector coverage:')
for col in sector_cols[:5]:
    non_null = structure[col].notna().sum()
    pct = 100 * non_null / len(structure)
    print(f'  {col}: {non_null}/{len(structure)} ({pct:.1f}%)')
