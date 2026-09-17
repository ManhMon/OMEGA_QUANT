import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path

REPO_ROOT = Path("C:/Users/GHC/repos/OMEGA_QUANT")
sys.path.insert(0, str(REPO_ROOT / "src"))

# Load data
raw_df = pd.read_parquet(REPO_ROOT / "data/market_2015_now.parquet")
raw_df["date"] = pd.to_datetime(raw_df["date"])

# Select tickers
tickers = ['SHB', 'HPG', 'SSI', 'STB', 'VIX', 'MBB', 'VPB', 'VND', 'HAG', 'DXG']
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

alpha_ics = {}
y_vals = temp_train["returns"].values
for lc in lag_col_names_all:
    x_vals = temp_train[lc].values
    
    # SỬA LỖI: Sử dụng np.nanstd để tránh bị trả về nan khi có NaN
    std_x = np.nanstd(x_vals)
    std_y = np.nanstd(y_vals)
    
    if std_x > 1e-9 and std_y > 1e-9:
        # SỬA LỖI: Chỉ tính correlation trên các phần tử hợp lệ
        mask = np.isfinite(x_vals) & np.isfinite(y_vals)
        if mask.sum() > 10:
            corr = np.corrcoef(x_vals[mask], y_vals[mask])[0, 1]
            if not np.isnan(corr):
                alpha_ics[lc] = corr

print(f"Total calculated ICs with fix: {len(alpha_ics)}")
# Lọc ra top alpha có IC cao nhất
sorted_ics = pd.Series(alpha_ics).abs().sort_values(ascending=False)
print("\nTop 15 alphas by absolute IC:")
for k, v in sorted_ics.head(15).items():
    print(f"  {k}: {alpha_ics[k]:.6f}")

# Phân loại theo quota để xem có chọn được từ 4 nhóm không
QUOTA_PER_CATEGORY = 2
CATEGORY_PREFIXES = {
    "HR": ("alpha_hr_",),
    "GP": ("alpha_gp_",),
    "LLM": ("alpha_llm_",),
    "VN": ("alpha_vn_", "alpha_stock_", "alpha_macro_"),
}

def _category_of(alpha_name: str) -> str:
    for cat, prefixes in CATEGORY_PREFIXES.items():
        if any(alpha_name.startswith(p) for p in prefixes):
            return cat
    return None

selected_lag_cols = []
used_categories = {}
categorized_alphas = {cat: [] for cat in CATEGORY_PREFIXES}
for lc in lag_col_names_all:
    alpha_name = lc.replace("_lag1", "")
    cat = _category_of(alpha_name)
    if cat is None or lc not in alpha_ics:
        continue
    categorized_alphas[cat].append(lc)

for cat, lc_list in categorized_alphas.items():
    lc_list.sort(key=lambda c: abs(alpha_ics[c]), reverse=True)
    selected_lag_cols.extend(lc_list[:QUOTA_PER_CATEGORY])
    used_categories[cat] = min(len(lc_list), QUOTA_PER_CATEGORY)

print(f"\nQuota Feature Selection with fix: {len(selected_lag_cols)} alphas across {len(used_categories)} categories")
for cat, num in used_categories.items():
    print(f"  Category {cat}: {num} selected")
    cat_selected = [c for c in selected_lag_cols if _category_of(c.replace("_lag1", "")) == cat]
    for c in cat_selected:
        print(f"    {c}: {alpha_ics[c]:.6f}")
