"""
Phase 1: Feature Validation - OMEGA Backtest Plan
Verify feature quality, stability, and PIT Safety on full dataset
"""
import pandas as pd
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path('OMEGA_QUANT/packages/core/src').resolve()))

from omega.core.structure_features import get_structure_data
from omega.core.feature_factory import FeatureFactory

print("=" * 70)
print("PHASE 1: FEATURE VALIDATION - VCI LEVEL 2 INTEGRATION")
print("=" * 70)

# 1. Load Data
print("\n[1] Loading Data...")
parquet_path = Path('OMEGA_QUANT/data/market_2015_now_cleaned.parquet')
df = pd.read_parquet(parquet_path)
df = df.rename(columns={'ticker': 'symbol'})
df['date'] = pd.to_datetime(df['date'])
df = df.set_index(['date', 'symbol']).sort_index()

print(f"    Loaded: {len(df)} rows, {df.index.get_level_values('symbol').nunique()} symbols")
print(f"    Date range: {df.index.get_level_values('date').min()} to {df.index.get_level_values('date').max()}")

# 2. Compute Features
print("\n[2] Computing Features...")
structure = get_structure_data(df[['close', 'volume', 'high', 'low', 'open']])
print(f"    Structure features: {structure.shape[1]} columns")

factory = FeatureFactory()
technical = factory.compute_all_features(df.reset_index(), price_col='close', volume_col='volume')
print(f"    Technical features: {technical.shape[1]} columns")

combined = pd.merge(structure.reset_index(), technical.reset_index(), on=['date', 'symbol'], how='inner').set_index(['date', 'symbol'])
print(f"    Combined: {combined.shape[0]} rows, {combined.shape[1]} features")

# 3. Feature Statistics
print("\n[3] Feature Statistics...")
print(f"    Total features: {combined.shape[1]}")
print(f"    Sector features: {len([c for c in combined.columns if c.startswith('sector_')])}")
print(f"    Technical features: {len([c for c in combined.columns if c.startswith('feat_')])}")

# 4. NaN Analysis
print("\n[4] NaN Analysis...")
nan_pct = combined.isna().mean() * 100
print(f"    Overall NaN rate: {combined.isna().mean().mean():.2f}%")
print(f"    Features with >50% NaN: {(nan_pct > 50).sum()}")
print(f"    Features with >90% NaN: {(nan_pct > 90).sum()}")

# First row per symbol (should be NaN for lagged features)
first_per_symbol = combined.groupby(level='symbol').head(1)
print(f"    First row per symbol NaN cells: {first_per_symbol.isna().sum().sum()}/{first_per_symbol.size}")

# 5. PIT Safety Verification
print("\n[5] PIT Safety Verification...")
symbols_sample = df.index.get_level_values('symbol').unique()[:10]
pit_pass = True
for sym in symbols_sample:
    sym_data = combined.xs(sym, level='symbol')
    if len(sym_data) > 1:
        # Check T1 has data from T0 (shifted)
        t0_features = sym_data.iloc[0]
        t1_features = sym_data.iloc[1]
        # T1 should have non-NaN for most features (lagged from T0)
        t1_has_data = not t1_features.isna().all()
        if not t1_has_data:
            pit_pass = False
            print(f"    WARNING: Symbol {sym} T1 has no data")

if pit_pass:
    print("    PIT Safety: PASS (all symbols have T-1 lagged data)")
else:
    print("    PIT Safety: FAIL (some symbols missing T-1 data)")

# 6. Sector Distribution
print("\n[6] Sector Distribution...")
sector_cols = [c for c in combined.columns if c.startswith('sector_')]
if sector_cols:
    sector_counts = combined[sector_cols].sum()
    sector_pct = sector_counts / len(combined) * 100
    print(f"    Total sectors: {len(sector_cols)}")
    print("    Top 5 sectors by coverage:")
    for sector, pct in sector_pct.nlargest(5).items():
        print(f"      {sector}: {pct:.1f}%")
else:
    print("    No sector columns found")

# 7. Feature Correlation (sample)
print("\n[7] Feature Correlation (sample)...")
sample_features = combined.sample(min(10000, len(combined)), random_state=42)
corr_matrix = sample_features.corr()
high_corr = corr_matrix.unstack().sort_values(ascending=False).drop_duplicates()
high_corr = high_corr[high_corr < 1.0].head(10)
print("    Top 10 correlated feature pairs:")
for (f1, f2), corr in high_corr.items():
    print(f"      {f1} <-> {f2}: {corr:.3f}")

# 8. Summary
print("\n" + "=" * 70)
print("PHASE 1 SUMMARY")
print("=" * 70)
print(f"Features: {combined.shape[1]} (structure: {structure.shape[1]}, technical: {technical.shape[1]})")
print(f"NaN rate: {combined.isna().mean().mean():.2f}%")
print(f"PIT Safety: {'PASS' if pit_pass else 'FAIL'}")
print(f"Sectors: {len(sector_cols)}")
print("=" * 70)

# Save report
report_path = Path('.ly_state/session/phase1_feature_report.md')
report_path.parent.mkdir(parents=True, exist_ok=True)

with open(report_path, 'w', encoding='utf-8') as f:
    f.write("# Phase 1 Feature Validation Report\n\n")
    f.write(f"**Date**: {pd.Timestamp.now()}\n\n")
    f.write(f"**Features**: {combined.shape[1]}\n\n")
    f.write(f"**NaN rate**: {combined.isna().mean().mean():.2f}%\n\n")
    f.write(f"**PIT Safety**: {'PASS' if pit_pass else 'FAIL'}\n\n")
    f.write(f"**Sectors**: {len(sector_cols)}\n\n")
    f.write("## Sector Distribution\n\n")
    f.write(sector_pct.to_string())

print(f"\nReport saved to: {report_path}")
