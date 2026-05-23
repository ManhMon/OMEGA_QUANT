import pandas as pd

df = pd.read_parquet('OMEGA_QUANT/data/market_2015_now.parquet')
print(f'Min date: {df["date"].min()}')
print(f'Max date: {df["date"].max()}')
print(f'\nCounts by year:')
print(df["date"].dt.year.value_counts().sort_index())
