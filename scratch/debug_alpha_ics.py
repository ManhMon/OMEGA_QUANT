import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

REPO_ROOT = Path("C:/Users/GHC/repos/OMEGA_QUANT")
sys.path.insert(0, str(REPO_ROOT / "src"))

# Mô phỏng load_raw_data và prepare_panel
raw_df = pd.read_parquet(REPO_ROOT / "data/market_2015_now.parquet")
raw_df["date"] = pd.to_datetime(raw_df["date"])

# Dùng DynamicUniverseSelector để chọn ticker giống Fold 1
# Fold 1 có test period: 2015-01-05 .. 2017-04-19
# Để đơn giản, lấy các tickers giống Fold 1 (merged tickers trong log: ['AAA', 'ACB', 'ASM', 'BCG', 'BID', 'BSR', 'BVH', 'CEO', 'CII'])
tickers = ['AAA', 'ACB', 'ASM', 'BCG', 'BID', 'BVH', 'CEO', 'CII'] # BSR, BCG...
# Filter date range cho Fold 1 train (CPCV Fold 1 train dates)
# Trong CPCV với n_splits=10, n_test=2, Fold 1 có test_dates từ 2015-01-05 đến 2017-04-19
# Do đó train dates sẽ là phần còn lại của dữ liệu (từ 2017-04-20 đến 2026-06-18)
train_mask = (raw_df["date"] >= "2017-04-20") & (raw_df["date"] <= "2026-06-18")
train_df = raw_df[train_mask].copy()

# Load precomputed alphas
precomputed_path = REPO_ROOT / "data/precomputed_alpha_features.parquet"
precomp_df = pd.read_parquet(precomputed_path)
precomp_df["date"] = pd.to_datetime(precomp_df["date"])

# Merge alphas
panel = train_df[train_df["ticker"].isin(tickers)].copy()
panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
panel = panel.rename(columns={"ticker": "symbol"})
panel["returns"] = panel.groupby("symbol")["close"].pct_change()

alpha_cols = [c for c in precomp_df.columns if c.startswith("alpha_")]
merge_cols = ["date", "symbol"] + alpha_cols
panel = panel.merge(precomp_df[merge_cols], on=["date", "symbol"], how="left")

# Tính toán lags giống trong code
train_sorted = panel.sort_values(["symbol", "date"])
all_alpha_cols = [c for c in train_sorted.columns if c.startswith("alpha_") and not c.endswith("_lag1")]

train_lag_df = train_sorted.groupby("symbol")[all_alpha_cols].shift(1)
train_lag_df.columns = [f"{c}_lag1" for c in all_alpha_cols]
train_lag_df.index = train_sorted.index

temp_train = train_sorted[["returns", "date"]].copy()
lag_col_names_all = [f"{c}_lag1" for c in all_alpha_cols]
for lc in lag_col_names_all:
    temp_train[lc] = train_lag_df[lc]

first_row_indices = train_sorted.groupby("symbol").head(1).index
temp_train = temp_train.drop(index=first_row_indices, errors="ignore")
temp_train = temp_train.dropna(subset=["returns"])

print("Temp train shape:", temp_train.shape)
print("Any NaN in returns:", temp_train["returns"].isna().sum())
print("Returns std:", temp_train["returns"].std())
print("Returns sample values:\n", temp_train["returns"].head())

alpha_ics = {}
y_vals = temp_train["returns"].values
for lc in lag_col_names_all[:10]:
    x_vals = temp_train[lc].values
    std_x = np.std(x_vals)
    std_y = np.std(y_vals)
    print(f"\nFeature: {lc}")
    print(f"  std(x): {std_x:.6f}, std(y): {std_y:.6f}")
    if std_x > 1e-9 and std_y > 1e-9:
        corr = np.corrcoef(x_vals, y_vals)[0, 1]
        print(f"  Corrcoef: {corr}")
        # In thêm correlation nếu bỏ NaN
        mask = np.isfinite(x_vals) & np.isfinite(y_vals)
        if mask.sum() > 10:
            corr_clean = np.corrcoef(x_vals[mask], y_vals[mask])[0, 1]
            print(f"  Corrcoef (clean): {corr_clean}")
            print(f"  Finite count: {mask.sum()} / {len(mask)}")
        else:
            print("  Too few finite samples")
    else:
        print("  Std too small!")
