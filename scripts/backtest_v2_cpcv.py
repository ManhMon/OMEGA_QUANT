"""Phase 3.3 v2: backtest with CPCV+DSR (audit fixes P0+P1+P2 applied)."""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("backtest_v2_cpcv")
REPO_ROOT = Path(__file__).resolve().parent.parent
QUANT_SRC = REPO_ROOT / "packages" / "quant" / "src"

def _import(name, rel):
    spec = importlib.util.spec_from_file_location(name, str(QUANT_SRC / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def load_universe():
    files = sorted((REPO_ROOT / ".ly_state/session/universe").glob("universe_*.json"), reverse=True)
    if not files:
        raise FileNotFoundError("No universe file")
    with open(files[0]) as f:
        data = json.load(f)
    if isinstance(data, dict):
        univ = data.get("universe") or data.get("tickers") or []
        tickers = [u["ticker"] for u in univ] if (univ and isinstance(univ[0], dict)) else list(univ)
    else:
        tickers = list(data)
    logger.info("Universe: %d tickers from %s", len(tickers), files[0].name)
    return tickers

def load_panel(tickers, year_start, year_end):
    df = pd.read_parquet(REPO_ROOT / "data/market_2015_now.parquet")
    df["date"] = pd.to_datetime(df["date"])
    panel = df[(df["ticker"].isin(tickers)) & (df["date"].dt.year >= year_start) & (df["date"].dt.year <= year_end)].copy()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    logger.info("Panel: %d rows, %d tickers, %s..%s", len(panel), panel["ticker"].nunique(), panel["date"].min().date(), panel["date"].max().date())
    return panel

def compute_target(panel, horizon=5):
    return panel.groupby("ticker")["close"].transform(lambda s: s.shift(-horizon) / s - 1.0)

def evaluate_fold(X_tr, y_tr, X_te, y_te, alphas=(0.1, 1.0, 10.0, 100.0)):
    """P0-1: tune alpha on train-only inner KFold; predict once on test."""
    n_inner = min(3, max(2, len(X_tr) // 1000))
    inner = KFold(n_splits=n_inner, shuffle=False)
    best_a, best_ic = alphas[0], -np.inf
    for a in alphas:
        ics = []
        for itr, ite in inner.split(X_tr):
            m = Ridge(alpha=a, random_state=42)
            m.fit(X_tr[itr], y_tr[itr])
            p = m.predict(X_tr[ite])
            if np.std(p) >= 1e-12:
                ics.append(float(np.corrcoef(p, y_tr[ite])[0, 1]))
        ic = float(np.mean(ics)) if ics else 0.0
        if ic > best_ic:
            best_ic, best_a = ic, a
    final = Ridge(alpha=best_a, random_state=42)
    final.fit(X_tr, y_tr)
    pred = final.predict(X_te)
    test_ic = 0.0 if np.std(pred) < 1e-12 else float(np.corrcoef(pred, y_te)[0, 1])
    return {"ic": test_ic, "pred": pred, "alpha": best_a, "train_cv_ic": best_ic}

def per_date_returns(pred, y_te, dates_te):
    """P1-1: per-date long-short demedian portfolio."""
    if len(pred) == 0:
        return np.array([])
    df = pd.DataFrame({"pred": pred, "y": y_te, "date": dates_te})
    daily = []
    for _, g in df.groupby("date"):
        if len(g) < 2:
            continue
        pos = np.sign(g["pred"].values - g["pred"].median())
        if np.all(pos == 0):
            continue
        nl, ns = max(int((pos > 0).sum()), 1), max(int((pos < 0).sum()), 1)
        w = np.where(pos > 0, 1.0 / nl, np.where(pos < 0, -1.0 / ns, 0.0))
        daily.append(float(np.sum(w * g["y"].values)))
    return np.asarray(daily)

def run_pipeline(X, y, ts, dates, cpcv_mod, dsr_mod, label, label_horizon, n_alphas=4):
    cpcv = cpcv_mod.CombinatorialPurgedKFold(n_splits=10, n_test_splits=2, embargo_pct=0.01, label_horizon=label_horizon)
    folds, daily_rets, trial_srs = [], [], []
    for fid, (tr, te) in enumerate(cpcv.split(ts)):
        X_tr, X_te = X[tr], X[te]
        # P1-3: zscore inside fold (train-only stats)
        mu = np.nanmean(X_tr, axis=0)
        sd = np.nanstd(X_tr, axis=0, ddof=1)
        sd = np.where(sd < 1e-12, 1.0, sd)
        X_tr = (X_tr - mu) / sd
        X_te = (X_te - mu) / sd
        r = evaluate_fold(X_tr, y[tr], X_te, y[te])
        rets = per_date_returns(r["pred"], y[te], dates[te])
        sr = float(np.mean(rets) / np.std(rets, ddof=1)) if (len(rets) > 1 and np.std(rets, ddof=1) > 0) else 0.0
        trial_srs.append(sr)  # P2-1: keep all
        daily_rets.extend(rets.tolist())
        folds.append({"fold": fid, "test_ic": r["ic"], "train_cv_ic": r["train_cv_ic"], "fold_sr": sr, "n_daily": int(len(rets)), "alpha": r["alpha"]})
    # P0-2: n_trials = SEARCH dim
    dsr = dsr_mod.deflated_sharpe_ratio(np.asarray(daily_rets), n_trials=n_alphas, trial_sharpes=trial_srs, periods_per_year=252)
    s = {"label": label, "n_features": int(X.shape[1]), "n_samples": int(len(y)), "n_folds": len(folds), "n_daily": int(len(daily_rets)), "n_trials_dsr": n_alphas,
         "median_test_ic": float(np.median([f["test_ic"] for f in folds])),
         "median_train_cv_ic": float(np.median([f["train_cv_ic"] for f in folds])),
         "median_fold_sr": float(np.median([f["fold_sr"] for f in folds])),
         "dsr_sharpe": dsr.sr, "dsr_sr_ann": dsr.sr_annualized, "dsr": dsr.dsr, "pass": dsr.pass_threshold,
         "skew": dsr.skew, "kurt": dsr.kurtosis, "folds": folds}
    logger.info("[%s] folds=%d med_test_IC=%.4f med_train_IC=%.4f med_SR=%.4f DSR=%.3f n_daily=%d", label, len(folds), s["median_test_ic"], s["median_train_cv_ic"], s["median_fold_sr"], dsr.dsr, len(daily_rets))
    return s

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--year-start", type=int, default=2020)
    p.add_argument("--year-end", type=int, default=2024)
    p.add_argument("--out", default=".ly_state/session/phase3_3_v2.json")
    args = p.parse_args()
    cpcv_mod = _import("_cpcv", "omega/quant/validation/cpcv.py")
    dsr_mod = _import("_dsr", "omega/quant/validation/dsr.py")
    feat_mod = _import("_feat", "omega/quant/evolution/feature_adapter.py")
    tickers = load_universe()
    if args.smoke:
        tickers = tickers[:5]
        logger.info("SMOKE: 5 tickers")
    panel = load_panel(tickers, args.year_start, args.year_end)
    if panel.empty:
        logger.error("Empty panel"); return 1
    target = compute_target(panel, horizon=5)
    feat_dict = feat_mod.GPFeatureAdapter().compute_all(panel, top_n_features=125)
    feat_names = list(feat_dict.keys())
    feat_df = pd.DataFrame(feat_dict, index=panel.index)
    feat_df["ticker"] = panel["ticker"].values
    feat_df["date"] = panel["date"].values
    feat_df["target"] = target.values
    feat_df = feat_df.sort_values(["date", "ticker"]).reset_index(drop=True)
    valid = ~feat_df["target"].isna() & ~feat_df[feat_names].isna().any(axis=1)
    feat_df = feat_df[valid].reset_index(drop=True)
    X = feat_df[feat_names].to_numpy()
    y = feat_df["target"].to_numpy()
    max_per_date = int(feat_df.groupby("date").size().max())
    bar_horizon = 5 * max_per_date  # P1-2 fix
    ts = pd.Series(np.arange(len(y)))
    dates = feat_df["date"].to_numpy()
    logger.info("Drop NaN: %d samples, %d feats, max_per_date=%d, bar_horizon=%d", len(y), X.shape[1], max_per_date, bar_horizon)
    summary = run_pipeline(X, y, ts, dates, cpcv_mod, dsr_mod, "A_baseline_alphas", label_horizon=bar_horizon)
    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"baseline": summary}, f, indent=2, default=str)
    logger.info("Saved: %s", out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
