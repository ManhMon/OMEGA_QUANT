"""Quick profiling of backtest bottlenecks."""
import sys
import time
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

REPO_ROOT = Path(__file__).resolve().parent.parent

t0 = time.time()
raw_df = pd.read_parquet(REPO_ROOT / "data/market_2015_now.parquet")
raw_df["date"] = pd.to_datetime(raw_df["date"])
mask = (raw_df["date"] >= "2015-01-01") & (raw_df["date"] <= "2026-12-31")
raw_df = raw_df[mask]
print(f"[{time.time()-t0:.1f}s] Data load: {len(raw_df)} rows")

t0 = time.time()
tickers = raw_df.groupby("ticker")["volume"].sum().nlargest(30).index.tolist()
print(f"[{time.time()-t0:.1f}s] Universe selection: {len(tickers)} tickers")

# Panel prep
t0 = time.time()
panel = raw_df[raw_df["ticker"].isin(tickers)].copy()
panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
panel = panel.rename(columns={"ticker": "symbol"})
panel["returns"] = panel.groupby("symbol")["close"].pct_change()
panel["adv_vnd"] = (
    panel.groupby("symbol")["volume"]
    .transform(lambda x: x.rolling(20, min_periods=5).mean())
) * panel["close"]
print(f"[{time.time()-t0:.1f}s] Panel prep: {len(panel)} rows, {panel['date'].nunique()} dates")

# Feature generation
t0 = time.time()
panel_mi = panel.set_index(["date", "symbol"]).sort_index()
from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
adapter = UnifiedFeatureAdapter(
    use_arsenal=True, use_alt_features=True,
    use_alt_data=True, use_llm_synth=False,
)
feat_panel = adapter.generate_all(panel_mi)
feat_df = feat_panel.reset_index()
feat_df = feat_df.dropna(subset=["close", "volume", "returns"])
feat_df = feat_df.sort_values(["symbol", "date"]).reset_index(drop=True)
print(f"[{time.time()-t0:.1f}s] Feature generation: {len(feat_df)} rows, {len(feat_df.columns)} cols")

# Profile per-fold operations
alpha_cols = [c for c in feat_df.columns if c.startswith("alpha_") and not c.endswith("_lag1")]
print(f"\nAlpha columns: {len(alpha_cols)}")

unique_dates = np.sort(feat_df["date"].unique())
ts_index = pd.DatetimeIndex(unique_dates)
n_dates = len(ts_index)

# Simulate one fold (first 60% train, last 40% test)
train_cutoff = int(n_dates * 0.6)
train_dates = ts_index[:train_cutoff]
train_date_set = set(pd.Timestamp(d) for d in train_dates)
train_feat = feat_df[feat_df["date"].isin(train_date_set)]
print(f"Train fold: {len(train_feat)} rows, {train_feat['symbol'].nunique()} symbols")

# Bottleneck 1: Training lag computation
t0 = time.time()
train_sorted = train_feat.sort_values(["symbol", "date"])
train_lag_df = pd.DataFrame(index=train_sorted.index)
for col in alpha_cols:
    train_lag_df[f"{col}_lag1"] = train_sorted.groupby("symbol")[col].shift(1)
print(f"[{time.time()-t0:.1f}s] Training lag computation ({len(alpha_cols)} cols)")

# Bottleneck 2: Prediction lag computation (on FULL panel)
t0 = time.time()
full_sorted = feat_df.sort_values(["symbol", "date"])
pred_lag_df = pd.DataFrame(index=full_sorted.index)
for col in alpha_cols:
    pred_lag_df[f"{col}_lag1"] = full_sorted.groupby("symbol")[col].shift(1)
print(f"[{time.time()-t0:.1f}s] Prediction lag computation (full panel, {len(alpha_cols)} cols)")

# Bottleneck 3: Vectorized version of prediction lag
t0 = time.time()
full_sorted2 = feat_df.sort_values(["symbol", "date"])
pred_lag_cols = {f"{c}_lag1": full_sorted2.groupby("symbol")[c].shift(1) for c in alpha_cols}
pred_lag_df2 = pd.DataFrame(pred_lag_cols, index=full_sorted2.index)
print(f"[{time.time()-t0:.1f}s] Vectorized prediction lag (dict comprehension)")

# Bottleneck 4: Even more optimized - single groupby
t0 = time.time()
full_sorted3 = feat_df.sort_values(["symbol", "date"])
pred_lag_df3 = full_sorted3.groupby("symbol")[alpha_cols].shift(1)
pred_lag_df3.columns = [f"{c}_lag1" for c in alpha_cols]
print(f"[{time.time()-t0:.1f}s] Single groupby prediction lag")

# Verify outputs match
lag_col_names = [f"{c}_lag1" for c in alpha_cols]
diff = (pred_lag_df[lag_col_names].values - pred_lag_df3[lag_col_names].values)
print(f"Max diff between methods: {np.nanmax(np.abs(diff))}")

# Bottleneck 5: HMM pivot
t0 = time.time()
close_pivot = train_feat.pivot(index="date", columns="symbol", values="close")
close_pivot = close_pivot.sort_index()
market_proxy = close_pivot.mean(axis=1)
mp_returns = market_proxy.pct_change().dropna().values
print(f"[{time.time()-t0:.1f}s] HMM pivot + market proxy")

# Bottleneck 6: IC computation
t0 = time.time()
panel_sorted = train_feat.sort_values(["symbol", "date"])
if "composite_signal" in panel_sorted.columns:
    fwd_ret = panel_sorted.groupby("symbol")["returns"].shift(-1)
    panel_with_fwd = panel_sorted.copy()
    panel_with_fwd["fwd_return"] = fwd_ret
    ic_vals_all = []
    for dt, grp in panel_with_fwd.groupby("date"):
        sig = grp["composite_signal"].values
        ret = grp["fwd_return"].values
        mask2 = np.isfinite(sig) & np.isfinite(ret)
        if mask2.sum() >= 5:
            corr = np.corrcoef(sig[mask2], ret[mask2])[0, 1]
            if np.isfinite(corr):
                ic_vals_all.append(corr)
    print(f"[{time.time()-t0:.1f}s] IC computation (loop): {len(ic_vals_all)} dates")

# Vectorized IC
t0 = time.time()
if "composite_signal" in panel_with_fwd.columns:
    sig_pivot = panel_with_fwd.pivot(index="date", columns="symbol", values="composite_signal")
    ret_pivot = panel_with_fwd.pivot(index="date", columns="symbol", values="fwd_return")
    common_dates = sig_pivot.index.intersection(ret_pivot.index)
    ic_vec = []
    for dt in common_dates:
        s = sig_pivot.loc[dt].dropna()
        r = ret_pivot.loc[dt].dropna()
        common_syms = s.index.intersection(r.index)
        if len(common_syms) >= 5:
            corr = np.corrcoef(s[common_syms].values, r[common_syms].values)[0, 1]
            if np.isfinite(corr):
                ic_vec.append(corr)
    print(f"[{time.time()-t0:.1f}s] IC computation (pivot-based): {len(ic_vec)} dates")

print("\n=== Summary ===")
print(f"Prediction lag is the BIGGEST bottleneck: called {45}x in 45-fold CPCV")
print(f"Pre-computing once saves ~{(time.time()-t0)*44:.0f}s across all folds")
