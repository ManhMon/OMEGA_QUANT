"""Debug script to analyze filter impacts on data cleaning."""
import pandas as pd
import logging
logging.basicConfig(level=logging.INFO)

# Load data
df = pd.read_parquet('data/market_2015_now.parquet')
print(f'Initial rows: {len(df):,}')
print(f'Initial symbols: {df["ticker"].nunique()}')
print()

# Step 1: Check duplicates
duplicates = df.duplicated(subset=['date', 'ticker'], keep='first').sum()
print(f'Step 1 - Duplicates: {duplicates:,} ({duplicates/len(df)*100:.2f}%)')
print()

# Step 2: Check NaN
ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
nan_counts = {col: df[col].isna().sum() for col in ohlcv_cols}
print(f'Step 2 - NaN values:')
for col, count in nan_counts.items():
    print(f'  {col}: {count:,} ({count/len(df)*100:.2f}%)')
print()

# Step 3: Check min_price filter
min_price = 1.0
below_min_price = (df['close'] < min_price).sum()
print(f'Step 3 - Rows with close < {min_price} VND: {below_min_price:,} ({below_min_price/len(df)*100:.2f}%)')
print()

# Step 4: Check min_volume filter
min_volume = 1000.0
below_min_volume = (df['volume'] < min_volume).sum()
print(f'Step 4 - Rows with volume < {min_volume}: {below_min_volume:,} ({below_min_volume/len(df)*100:.2f}%)')
print()

# Step 5: Check min_history filter
min_history_days = 60
symbol_counts = df.groupby('ticker').size()
symbols_below_min = (symbol_counts < min_history_days).sum()
rows_from_short_symbols = symbol_counts[symbol_counts < min_history_days].sum()
print(f'Step 5 - Symbols with < {min_history_days} days: {symbols_below_min} symbols')
print(f'        Rows from short-history symbols: {rows_from_short_symbols:,} ({rows_from_short_symbols/len(df)*100:.2f}%)')
print()

# Step 6: Check invalid OHLC
invalid_ohlc = ~((df['high'] >= df['low']) & 
                 (df['close'] >= df['low']) & 
                 (df['close'] <= df['high']))
print(f'Step 6 - Invalid OHLC: {invalid_ohlc.sum():,} ({invalid_ohlc.sum()/len(df)*100:.2f}%)')
print()

# Step 7: Check invalid prices (< 0.01 VND)
price_cols = ['open', 'high', 'low', 'close']
invalid_prices = pd.Series([False] * len(df))
for col in price_cols:
    invalid_prices = invalid_prices | (df[col] < 0.01)
print(f'Step 7 - Invalid prices (< 0.01 VND): {invalid_prices.sum():,} ({invalid_prices.sum()/len(df)*100:.2f}%)')
print()

# Total impact
total_filtered = (below_min_price + below_min_volume + rows_from_short_symbols + 
                  invalid_ohlc.sum() + invalid_prices.sum())
print(f'Total rows filtered: {total_filtered:,} ({total_filtered/len(df)*100:.2f}%)')
print(f'Remaining rows: {len(df) - total_filtered:,}')
