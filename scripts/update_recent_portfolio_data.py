import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from vnstock import Quote

SYMS = ['VNM', 'VIC', 'HPG', 'TCB', 'BID']
BASE = Path('data/market_2015_now.parquet')
OUT = Path('data/market_2015_now.parquet')

# Load current warehouse
m = pd.read_parquet(BASE)
m['date'] = pd.to_datetime(m['date']).dt.normalize()

max_date = m['date'].max().date()
today = datetime.now().date()
yesterday = today - timedelta(days=1)

if max_date >= yesterday:
    print(f'NO_UPDATE_NEEDED max_date={max_date} yesterday={yesterday}')
    raise SystemExit(0)

start_date = (max_date + timedelta(days=1)).isoformat()
end_date = yesterday.isoformat()
print(f'UPDATE_RANGE {start_date} -> {end_date}')

frames = []
for s in SYMS:
    try:
        q = Quote(source='VCI', symbol=s)
        df = q.history(start=start_date, end=end_date, interval='1D')
        if df is None or df.empty:
            print(f'{s}: no new rows')
            continue

        # normalize schema
        df = df.rename(columns={'time': 'date'})
        df['date'] = pd.to_datetime(df['date']).dt.normalize()
        for c in ['open', 'high', 'low', 'close', 'volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')

        # VCI often returns price in thousand units
        if df['close'].median() < 1000:
            for c in ['open', 'high', 'low', 'close']:
                df[c] = df[c] * 1000.0

        df['ticker'] = s
        df['as_of'] = pd.Timestamp(datetime.now().replace(hour=10, minute=0, second=0, microsecond=0))
        df['available_at'] = df['date'] + pd.Timedelta(days=1)

        df = df[['ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'as_of', 'available_at']]
        frames.append(df)
        print(f'{s}: fetched {len(df)} rows ({df.date.min().date()} -> {df.date.max().date()})')
    except Exception as e:
        print(f'{s}: ERROR {e}')

if not frames:
    print('NO_NEW_DATA_FETCHED')
    raise SystemExit(0)

new_data = pd.concat(frames, ignore_index=True)

# remove overlap for updated symbols and date window
mask_overlap = (
    m['ticker'].isin(SYMS)
    & (m['date'] >= pd.to_datetime(start_date))
    & (m['date'] <= pd.to_datetime(end_date))
)
old_removed = int(mask_overlap.sum())
m2 = m.loc[~mask_overlap].copy()

combined = pd.concat([m2, new_data], ignore_index=True)
combined = combined.drop_duplicates(subset=['ticker', 'date'], keep='last')
combined = combined.sort_values(['ticker', 'date']).reset_index(drop=True)

combined.to_parquet(OUT, index=False)
print(f'UPDATED rows_added={len(new_data)} rows_replaced={old_removed} total={len(combined)}')
print('NEW_MAX_DATE', combined['date'].max().date())
print('UPDATED_SYMBOLS_MAX_DATE:')
print(combined[combined['ticker'].isin(SYMS)].groupby('ticker')['date'].max())
