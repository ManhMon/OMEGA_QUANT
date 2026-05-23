import pandas as pd
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'

df = pd.read_parquet('data/market_2015_now.parquet')
print(f'Market data: {len(df)} rows')
print(f'Columns: {list(df.columns)}')
print(f'Tickers: {df["ticker"].nunique()} unique')
print(f'Tickers: {sorted(df["ticker"].unique())}')
print(f'\nFirst 3 rows:')
print(df.head(3))
print(f'\nDate range:')
print(f'  Min: {df["date"].min()}')
print(f'  Max: {df["date"].max()}')
print(f'\nData types:')
print(df.dtypes)
