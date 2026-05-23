import pandas as pd
from pathlib import Path

src = Path('OMEGA_QUANT/data/market_2015_now.parquet')
out = Path('OMEGA_QUANT/data/market_2014_now.parquet')
cutoff = pd.Timestamp('2014-01-01')

if not src.exists():
    raise FileNotFoundError(f'Missing source file: {src}')

df = pd.read_parquet(src)
df['date'] = pd.to_datetime(df['date'])
filtered = df[df['date'] >= cutoff].copy()
filtered = filtered.sort_values(['ticker', 'date']).reset_index(drop=True)

out.parent.mkdir(parents=True, exist_ok=True)
filtered.to_parquet(out, index=False)

print(f'source_rows={len(df)}')
print(f'filtered_rows={len(filtered)}')
print(f'source_min_date={df["date"].min()}')
print(f'filtered_min_date={filtered["date"].min()}')
print(f'filtered_max_date={filtered["date"].max()}')
print(f'filtered_unique_tickers={filtered["ticker"].nunique()}')
print(f'output={out}')
print(f'output_size_bytes={out.stat().st_size}')
