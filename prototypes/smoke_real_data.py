import pandas as pd
import numpy as np
from pathlib import Path

path = Path('data/market_2015_now.parquet')
syms = ['VNM','VIC','HPG','TCB','BID']

print('=== REAL DATA E2E SMOKE ===')
print(f'file={path} exists={path.exists()}')

df = pd.read_parquet(path, columns=['ticker','date','close','as_of','available_at'])
df = df[df['ticker'].isin(syms)].copy()
df['date'] = pd.to_datetime(df['date'])

if not df.empty:
    pit_fail = (pd.to_datetime(df['available_at']).dt.normalize() <= df['date'].dt.normalize()).sum()
    print(f'rows={len(df):,} pit_available_at_le_date={pit_fail}')

px = df.pivot_table(index='date', columns='ticker', values='close', aggfunc='last').sort_index()
px = px.dropna(how='any')
ret = px.pct_change().dropna(how='any')
ret = ret.tail(252)

print(f'date_range={ret.index.min().date()} -> {ret.index.max().date()} n_days={len(ret)} symbols={list(ret.columns)}')

# LIVE-style rolling path
momentum = ret.rolling(20).mean()
z = momentum.apply(lambda x: (x - x.mean()) / (x.std() if x.std() > 1e-12 else 1.0), axis=1).fillna(0)
w = z.apply(lambda x: np.exp(x) / np.sum(np.exp(x)), axis=1)
w_lag = w.shift(1)
port_roll = (ret * w_lag).sum(axis=1).fillna(0)
turn = w_lag.diff().abs().sum(axis=1) / 2.0
cost = 0.001 * turn.reindex(port_roll.index).fillna(0)
net_roll = port_roll - cost

sg = (port_roll.mean()/port_roll.std()*np.sqrt(252)) if port_roll.std()>1e-12 else float('nan')
sn = (net_roll.mean()/net_roll.std()*np.sqrt(252)) if net_roll.std()>1e-12 else float('nan')
print(f'LIVE_REAL rolling_gross_sharpe={sg:.6f}')
print(f'LIVE_REAL rolling_net_sharpe={sn:.6f}')
print(f'LIVE_REAL mean_turnover={turn.reindex(port_roll.index).fillna(0).mean():.6f}')

# BACKTEST-style path (same as script after fix)
mom2 = ret.rolling(20).mean()
z2 = mom2.apply(lambda x: (x - x.mean()) / (x.std() if x.std() > 1e-12 else 1.0), axis=1).fillna(0)
w2 = z2.apply(lambda x: np.exp(x) / np.sum(np.exp(x)), axis=1)
port2 = (ret * w2.shift(1)).sum(axis=1).replace([np.inf, -np.inf], np.nan).fillna(0)
turn2 = w2.shift(1).diff().abs().sum(axis=1) / 2.0
net2 = port2 - (0.001 * turn2).reindex(port2.index).fillna(0)

sg2 = (port2.mean()/port2.std()*np.sqrt(252)) if port2.std()>1e-12 else float('nan')
sn2 = (net2.mean()/net2.std()*np.sqrt(252)) if net2.std()>1e-12 else float('nan')
print(f'BACKTEST_REAL gross_sharpe={sg2:.6f}')
print(f'BACKTEST_REAL net_sharpe={sn2:.6f}')
print(f'BACKTEST_REAL total_return_net={(1+net2).prod()-1:.6f}')
print('STATUS=PASS')
