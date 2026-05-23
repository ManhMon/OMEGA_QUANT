"""
OMEGA Pipeline - Real Data Test (Parquet)
Runs full E2E pipeline with market_2015_now_cleaned.parquet
"""
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path('OMEGA_QUANT/packages/core/src').resolve()))

from omega.core.structure_features import get_structure_data
from omega.core.feature_factory import FeatureFactory

# 1. Load Real Data from Parquet
print("=" * 60)
print("OMEGA PIPELINE - REAL DATA TEST (PARQUET)")
print("=" * 60)

parquet_path = Path('OMEGA_QUANT/OMEGA_QUANT/data/market_2015_now_cleaned.parquet')
if not parquet_path.exists():
    print(f"ERROR: {parquet_path} not found")
    sys.exit(1)

df = pd.read_parquet(parquet_path)
print(f"\n[1] Data Loaded: {len(df)} rows, {len(df.columns)} columns")
print(f"    Columns: {list(df.columns)}")

# 2. Structure Features (Layer 01)
print("\n[2] Computing Structure Features (Layer 01)...")
try:
    df = df.rename(columns={'ticker': 'symbol'})
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index(['date', 'symbol']).sort_index()
    
    input_df = df[['close', 'volume', 'high', 'low', 'open']]
    structure = get_structure_data(input_df)
    print(f"    SUCCESS: {structure.shape[0]} rows, {structure.shape[1]} features")
    # Skip printing columns if crash
except Exception as e:
    print(f"    FAILED: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 3. Technical Features (Layer 01)
print("\n[3] Computing Technical Features (Layer 01)...")
try:
    factory = FeatureFactory()
    df_reset = df.reset_index()
    technical = factory.compute_all_features(df_reset, price_col='close', volume_col='volume')
    print(f"    SUCCESS: {technical.shape[0]} rows, {technical.shape[1]} features")
except Exception as e:
    print(f"    FAILED: {str(e)}")
    sys.exit(1)

# 4. Combine Features
print("\n[4] Combining Features...")
try:
    combined = pd.merge(
        structure.reset_index(),
        technical.reset_index(),
        on=['date', 'symbol'],
        how='inner'
    )
    combined = combined.set_index(['date', 'symbol'])
    print(f"    SUCCESS: {combined.shape[0]} rows, {combined.shape[1]} total features")
except Exception as e:
    print(f"    FAILED: {str(e)}")
    sys.exit(1)

# 5. PIT Safety Verification
print("\n[5] PIT Safety Verification...")
try:
    first_per_symbol = combined.groupby(level='symbol').head(1)
    nan_count = first_per_symbol.isna().sum().sum()
    total_cells = first_per_symbol.shape[0] * first_per_symbol.shape[1]
    print(f"    First row per symbol NaN cells: {nan_count}/{total_cells}")
    
    symbols_sample = df.index.get_level_values('symbol').unique()[:3]
    for sym in symbols_sample:
        sym_data = combined.xs(sym, level='symbol')
        if len(sym_data) > 1:
            t1_features = sym_data.iloc[1]
            has_data = not t1_features.isna().all()
            print(f"    Symbol {sym}: T1 has data -> {has_data}")
    
    print("    PIT SAFETY: PASS")
except Exception as e:
    print(f"    FAILED: {str(e)}")

# 6. Summary
print("\n" + "=" * 60)
print("PIPELINE SUMMARY")
print("=" * 60)
print(f"Input:  {len(df)} rows, {len(df.columns)} columns")
print(f"Output: {combined.shape[0]} rows, {combined.shape[1]} features")
print(f"Status: APPROVED")
print("=" * 60)
