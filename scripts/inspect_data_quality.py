"""Inspect raw data quality + target distribution."""
import pandas as pd
import numpy as np

df = pd.read_parquet("data/market_2015_now.parquet")
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

# Target like backtest_v2_cpcv.py:compute_target
target = df.groupby("ticker")["close"].transform(lambda s: s.shift(-20) / s - 1.0)
print("Target (forward 20d return) distribution:")
print(f"  total rows: {len(target)}")
print(f"  NaN: {target.isna().sum()}")
print(f"  median: {target.median():.4f}")
print(f"  std: {target.std():.4f}")
print(f"  > +50%: {(target > 0.50).sum()}")
print(f"  > +100%: {(target > 1.00).sum()}")
print(f"  < -50%: {(target < -0.50).sum()}")
print()

df["ret_1d"] = df.groupby("ticker")["close"].pct_change()
print(f"close == 0 rows: {(df['close'] == 0).sum()}")
print(f"ret_1d > 100% (split candidates): {(df['ret_1d'] > 1.0).sum()}")
print(f"ret_1d < -50%: {(df['ret_1d'] < -0.5).sum()}")
print()

print("Top suspicious 1-day jumps (likely unadjusted CA):")
top = df[df["ret_1d"] > 1.0].sort_values("ret_1d", ascending=False).head(8)
print(top[["ticker", "date", "close", "ret_1d"]].to_string(index=False))
print()

print("VN HOSE limit-up = +7%, HNX = +10%, UPCOM = +15%.")
print(f"  ret_1d > +20% (above any sane VN limit): {(df['ret_1d'] > 0.20).sum()}")
print(f"  ret_1d < -20%: {(df['ret_1d'] < -0.20).sum()}")
