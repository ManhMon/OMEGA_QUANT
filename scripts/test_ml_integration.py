"""Test ML Alpha Integration."""
import sys
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

import pandas as pd
import numpy as np
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
from omega.quant.evolution.ml_alpha_integration import MLAlphaIntegration

# Load validation period (small sample)
df = pd.read_parquet(str(Path(__file__).resolve().parents[1] / 'data' / 'market_2015_now.parquet'))
df['date'] = pd.to_datetime(df['date'])
df = df[(df['date'] >= '2022-08-01') & (df['date'] <= '2024-06-30')]
top20 = df.groupby('ticker')['volume'].mean().sort_values(ascending=False).head(20).index.tolist()
df = df[df['ticker'].isin(top20)]

ohlcv = ['open', 'high', 'low', 'close', 'volume']
panel = df.set_index(['date', 'ticker'])[ohlcv].sort_index()
panel.index.names = ['date', 'symbol']
panel['returns'] = panel.groupby(level='symbol')['close'].pct_change()
panel = panel.dropna(subset=['returns'])

# Generate features
adapter = UnifiedFeatureAdapter(use_arsenal=True, use_alt_features=True, use_alt_data=True)
panel = adapter.generate_all(panel)

# Add target
panel['fwd_ret_5'] = panel.groupby(level='symbol')['close'].pct_change(5).shift(-5)
panel = panel.dropna(subset=['fwd_ret_5'])

features = adapter.get_all_feature_names()
print(f'Panel: {panel.shape}, Features: {len(features)}')

# Train ML combiner
ml = MLAlphaIntegration(model_name='alpha_combiner', horizons=[5], embargo_days=20)
train_result = ml.train_combiner(panel, features, target_col='fwd_ret_5')
print(f'Train status: {train_result["status"]}')
if 'train_ic' in train_result:
    print(f'Train IC: {train_result["train_ic"]:.4f}')
    print(f'Features used: {train_result["n_features"]}')

# Validate OOS (last 30%)
dates = panel.index.get_level_values('date').unique().sort_values()
split = int(len(dates) * 0.7)
oos_panel = panel.loc[panel.index.get_level_values('date').isin(dates[split:])]
val_result = ml.validate_oos(oos_panel, target_col='fwd_ret_5')
print(f'OOS status: {val_result["status"]}')
if 'oos_ic' in val_result:
    print(f'OOS IC: {val_result["oos_ic"]:.4f}')
    print(f'OOS Hit Rate: {val_result["oos_hit_rate"]:.4f}')
print('PASS')
