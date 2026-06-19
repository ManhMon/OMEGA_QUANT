"""Analyze volume distribution in market data."""
import pandas as pd

df = pd.read_parquet('data/market_2015_now.parquet')

print('=== VOLUME DISTRIBUTION ===')
print()
print('General Statistics:')
print(df['volume'].describe())
print()

print('Rows by volume threshold:')
thresholds = [100, 500, 1000, 5000, 10000, 50000, 100000]
for i, threshold in enumerate(thresholds):
    if i == 0:
        count = (df['volume'] < threshold).sum()
        print(f'< {threshold:>6,}: {count:>10,} rows ({count/len(df)*100:5.1f}%)')
    if i < len(thresholds) - 1:
        count = ((df['volume'] >= threshold) & (df['volume'] < thresholds[i+1])).sum()
        print(f'{threshold:>6,} - {thresholds[i+1]:<6,}: {count:>10,} rows ({count/len(df)*100:5.1f}%)')

count = (df['volume'] >= thresholds[-1]).sum()
print(f'>= {thresholds[-1]:>6,}: {count:>10,} rows ({count/len(df)*100:5.1f}%)')

print()
print('=== TOP 10 LOWEST VOLUME STOCKS ===')
low_vol = df[df['volume'] < 1000].groupby('ticker').size().sort_values()
print(low_vol.head(10))

print()
print('=== SPECIFIC EXAMPLE ===')
sample_ticker = low_vol.index[0]
sample_data = df[df['ticker'] == sample_ticker].head(5)
print(f'Stock: {sample_ticker}')
print(sample_data[['date', 'ticker', 'close', 'volume']])
