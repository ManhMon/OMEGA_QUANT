import pandas as pd

df = pd.read_parquet('OMEGA_QUANT/data/market_2015_now.parquet')

# Filter 2008-2015
df_early = df[(df['date'] >= '2008-01-01') & (df['date'] < '2015-01-01')]

print('Data 2008-2014 (before 2015):')
print(f'Total rows: {len(df_early)}')
print(f'\nBy year:')
print(df_early['date'].dt.year.value_counts().sort_index())

print(f'\nBy ticker (top 20):')
print(df_early['ticker'].value_counts().head(20))

# Check continuity
print(f'\n=== Continuity Check ===')
for year in range(2008, 2015):
    df_year = df_early[df_early['date'].dt.year == year]
    if len(df_year) > 0:
        print(f'{year}: {len(df_year)} rows, {df_year["ticker"].nunique()} tickers, date range: {df_year["date"].min().date()} to {df_year["date"].max().date()}')
    else:
        print(f'{year}: NO DATA')
