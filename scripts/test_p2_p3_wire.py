"""Test P2+P3: Unified adapter with microstructure/macro + orchestrator bridge."""
import sys
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\quant\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\core\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\infra\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\data\src')

import pandas as pd
import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
from omega.quant.evolution.orchestrator_bridge import OmegaQuantOrchestrator

# Load small sample
df = pd.read_parquet(r'C:\Users\GHC\.openclaw\workspace\data\market_2015_now.parquet')
df['date'] = pd.to_datetime(df['date'])
top10 = df.groupby('ticker')['volume'].mean().sort_values(ascending=False).head(10).index.tolist()
df = df[df['ticker'].isin(top10)]

# Split
val_df = df[(df['date'] >= '2023-01-01') & (df['date'] <= '2024-06-30')]
test_df = df[df['date'] >= '2024-08-01']

ohlcv = ['open', 'high', 'low', 'close', 'volume']
def build(period_df):
    p = period_df.set_index(['date', 'ticker'])[ohlcv].sort_index()
    p.index.names = ['date', 'symbol']
    p['returns'] = p.groupby(level='symbol')['close'].pct_change()
    return p.dropna(subset=['returns'])

val_panel = build(val_df)
test_panel = build(test_df)

# Test P2: Unified adapter now includes microstructure + macro
print("=== P2: Unified Adapter (with micro/macro) ===")
adapter = UnifiedFeatureAdapter(use_arsenal=True)
result = adapter.generate_all(val_panel)
features = adapter.get_all_feature_names()
print(f"Total features: {len(features)}")
print(f"Panel shape: {result.shape}")

# Test P3: Orchestrator bridge
print("\n=== P3: Orchestrator Bridge ===")
orch = OmegaQuantOrchestrator()
output = orch.run_research_pipeline(val_panel, val_panel, test_panel)
print(f"Features: {output['features']}")
print(f"ML: {output['ml_train']['status']}")
print(f"Regime: {output['regime']}")
print(f"Sharpe: {output['metrics'].get('sharpe', 0):.4f}")
print(f"Return: {output['metrics'].get('total_return', 0)*100:.2f}%")
print("\nPASS")
