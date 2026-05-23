import pandas as pd
from pathlib import Path

omega_data = Path('OMEGA_QUANT/data')

# Check main parquet files
main_files = [
    'market_2015_2026.parquet',
    'mock_market.parquet'
]

print('=== OMEGA_QUANT/data MAIN FILES ===\n')
for fname in main_files:
    fpath = omega_data / fname
    if fpath.exists():
        try:
            df = pd.read_parquet(fpath, engine='pyarrow')
            size_mb = fpath.stat().st_size / (1024**2)
            print(f'{fname}:')
            print(f'  Size: {size_mb:.1f} MB')
            print(f'  Shape: {df.shape[0]} rows x {df.shape[1]} cols')
            print(f'  Columns: {list(df.columns)}')
            if 'date' in df.columns:
                print(f'  Date range: {df["date"].min()} to {df["date"].max()}')
            if 'symbol' in df.columns:
                print(f'  Symbols: {df["symbol"].nunique()} unique')
            print()
        except Exception as e:
            print(f'{fname}: ERROR - {e}\n')
    else:
        print(f'{fname}: NOT FOUND\n')

# Check cache dir
cache_dir = omega_data / 'cache'
if cache_dir.exists():
    cache_files = list(cache_dir.glob('*.parquet'))
    print(f'Cache files: {len(cache_files)} parquet files (symbol-level cache)')
    if cache_files:
        sample = cache_files[0]
        try:
            df = pd.read_parquet(sample, engine='pyarrow')
            print(f'  Sample: {sample.name}')
            print(f'  Shape: {df.shape[0]} rows x {df.shape[1]} cols')
            print(f'  Columns: {list(df.columns)}')
        except Exception as e:
            print(f'  Sample read error: {e}')
