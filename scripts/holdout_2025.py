"""Holdout validation: train 2020-2024, test 2025. Phase 12 best params."""
import sys, importlib.util, json, logging, time
from pathlib import Path
import numpy as np, pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("holdout_2025")
ROOT = Path(__file__).resolve().parent.parent
QUANT_SRC = ROOT / "packages" / "quant" / "src"
for _p in (QUANT_SRC, ROOT/"packages"/"data"/"src", ROOT/"src"):
    sp = str(_p)
    if _p.exists() and sp not in sys.path: sys.path.insert(0, sp)
sys.path.insert(0, str(ROOT / "scripts"))
import backtest_v2_cpcv as bt

def _import(name, rel):
    spec = importlib.util.spec_from_file_location(name, str(QUANT_SRC / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

cpcv_mod = _import("_cpcv", "omega/quant/validation/cpcv.py")
dsr_mod = _import("_dsr", "omega/quant/validation/dsr.py")
feat_mod = _import("_feat", "omega/quant/evolution/feature_adapter.py")
tail_mod = _import("_tc", "omega/quant/portfolio/tail_controls.py")
exec_mod = _import("_es", "omega/quant/portfolio/execution_sim.py")

# Phase 12 best params
BEST = dict(label_horizon=60, signal_ema=3, vol_target=0.15, max_abs_weight=0.03, dd_threshold=0.05, embargo_pct=0.01)

def main():
    t0 = time.time()
    # Train: 2020-2024, Test: 2025
    wf_train = bt.load_universe_walk_forward(2020, 2024)
    wf_test = bt.load_universe_walk_forward(2025, 2025)
    panel_train = bt.load_panel_walk_forward(wf_train, 2020, 2024)
    panel_test = bt.load_panel_walk_forward(wf_test, 2025, 2025)
    logger.info("Train: %d rows, Test: %d rows", len(panel_train), len(panel_test))

    # Build features on train
    target_train = bt.compute_target(panel_train, horizon=BEST["label_horizon"])
    target_test = bt.compute_target(panel_test, horizon=BEST["label_horizon"])

    feat_dict_train = feat_mod.GPFeatureAdapter().compute_all(panel_train, top_n_features=125)
    feat_dict_test = feat_mod.GPFeatureAdapter().compute_all(panel_test, top_n_features=125)
    # Use intersection of features (some alphas may not compute on smaller test panel)
    feat_names = sorted(set(feat_dict_train.keys()) & set(feat_dict_test.keys()))
    logger.info("Feature intersection: %d (train had %d, test had %d)", len(feat_names), len(feat_dict_train), len(feat_dict_test))
    feat_df_train = pd.DataFrame({k: feat_dict_train[k] for k in feat_names}, index=panel_train.index)
    feat_df_train["ticker"] = panel_train["ticker"].values
    feat_df_train["date"] = panel_train["date"].values
    feat_df_train["target"] = target_train.values
    feat_df_train = feat_df_train.sort_values(["date","ticker"]).reset_index(drop=True)
    valid_tr = ~feat_df_train["target"].isna() & ~feat_df_train[feat_names].isna().any(axis=1)
    feat_df_train = feat_df_train[valid_tr].reset_index(drop=True)

    feat_df_test = pd.DataFrame({k: feat_dict_test[k] for k in feat_names}, index=panel_test.index)
    feat_df_test["ticker"] = panel_test["ticker"].values
    feat_df_test["date"] = panel_test["date"].values
    feat_df_test["target"] = target_test.values
    feat_df_test = feat_df_test.sort_values(["date","ticker"]).reset_index(drop=True)
    valid_te = ~feat_df_test["target"].isna() & ~feat_df_test[feat_names].isna().any(axis=1)
    feat_df_test = feat_df_test[valid_te].reset_index(drop=True)

    X_tr = feat_df_train[feat_names].to_numpy()
    y_tr = feat_df_train["target"].to_numpy()
    X_te = feat_df_test[feat_names].to_numpy()
    y_te = feat_df_test["target"].to_numpy()
    logger.info("X_tr: %s, X_te: %s", X_tr.shape, X_te.shape)

    # Winsorize + zscore (train-only stats)
    lo = np.nanpercentile(X_tr, 1.0, axis=0)
    hi = np.nanpercentile(X_tr, 99.0, axis=0)
    X_tr = np.clip(X_tr, lo, hi)
    X_te = np.clip(X_te, lo, hi)
    mu = np.nanmean(X_tr, axis=0)
    sd = np.nanstd(X_tr, axis=0, ddof=1)
    sd = np.where(sd < 1e-12, 1.0, sd)
    X_tr = (X_tr - mu) / sd
    X_te = (X_te - mu) / sd

    # Ridge fit on full train, predict on test
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold
    alphas = [0.1, 1.0, 10.0, 100.0]
    best_alpha, best_ic = 0.1, -999
    kf = KFold(n_splits=5, shuffle=False)
    for a in alphas:
        ics = []
        for tr_i, va_i in kf.split(X_tr):
            m = Ridge(alpha=a).fit(X_tr[tr_i], y_tr[tr_i])
            p = m.predict(X_tr[va_i])
            ic = float(np.corrcoef(p, y_tr[va_i])[0,1]) if np.std(p) > 1e-12 else 0
            ics.append(ic)
        mean_ic = np.mean(ics)
        if mean_ic > best_ic:
            best_ic = mean_ic
            best_alpha = a
    logger.info("Best alpha: %s (train CV IC: %.4f)", best_alpha, best_ic)

    # Final fit + predict
    model = Ridge(alpha=best_alpha).fit(X_tr, y_tr)
    pred = model.predict(X_te)

    # EMA smoothing (ema=3) per ticker on test predictions
    df_pred = pd.DataFrame({"pred": pred, "ticker": feat_df_test["ticker"].values, "date": feat_df_test["date"].values})
    df_pred = df_pred.sort_values(["ticker","date"]).reset_index(drop=True)
    df_pred["pred_ema"] = df_pred.groupby("ticker")["pred"].transform(lambda s: s.ewm(span=3, adjust=False).mean())
    df_pred = df_pred.sort_values(["date","ticker"]).reset_index(drop=True)
    pred_ema = df_pred["pred_ema"].to_numpy()

    # Metrics
    ic = float(np.corrcoef(pred_ema, y_te)[0,1])
    # Daily L/S returns
    dates_te = feat_df_test["date"].to_numpy()
    tickers_te = feat_df_test["ticker"].to_numpy()
    daily_rets = []
    for d in sorted(np.unique(dates_te)):
        mask = dates_te == d
        p_d = pred_ema[mask]
        y_d = y_te[mask]
        if len(p_d) < 2: continue
        pos = np.sign(p_d - np.median(p_d))
        if np.all(pos == 0): continue
        nl = max(int((pos>0).sum()), 1)
        ns = max(int((pos<0).sum()), 1)
        w = np.where(pos>0, 1.0/nl, np.where(pos<0, -1.0/ns, 0.0))
        daily_rets.append(float(np.sum(w * y_d)))
    daily_rets = np.array(daily_rets)
    sr = float(np.mean(daily_rets) / np.std(daily_rets, ddof=1)) if len(daily_rets) > 1 else 0
    sr_ann = sr * np.sqrt(252)
    elapsed = time.time() - t0

    results = {
        "holdout_year": 2025,
        "train_years": "2020-2024",
        "best_params": BEST,
        "best_alpha": best_alpha,
        "train_cv_ic": best_ic,
        "holdout_ic": ic,
        "holdout_sr_per_bar": sr,
        "holdout_sr_ann": sr_ann,
        "holdout_n_days": len(daily_rets),
        "holdout_n_samples": len(y_te),
        "holdout_mean_daily_ret": float(np.mean(daily_rets)),
        "holdout_std_daily_ret": float(np.std(daily_rets, ddof=1)),
        "holdout_max_dd": float(np.min(np.cumsum(daily_rets) - np.maximum.accumulate(np.cumsum(daily_rets)))),
        "elapsed_s": elapsed,
    }
    out = ROOT / ".ly_state/session/phase12_holdout_2025.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("HOLDOUT 2025: IC=%.4f SR_ann=%.3f n_days=%d elapsed=%.1fs", ic, sr_ann, len(daily_rets), elapsed)
    logger.info("Saved: %s", out)

if __name__ == "__main__":
    main()
