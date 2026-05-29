"""Phase 3.3: Backtest v2 with CPCV + DSR validation.

Baseline: 114 alpha features -> Ridge ensemble, validated through
CombinatorialPurgedKFold (10/2 splits, 1% embargo, 5-day horizon).

Reuses validation/cpcv.py + validation/dsr.py + evolution/feature_adapter.py.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("backtest_v2_cpcv")

REPO_ROOT = Path(__file__).resolve().parent.parent
QUANT_SRC = REPO_ROOT / "packages" / "quant" / "src"


def _import(name: str, rel: str):
    full = QUANT_SRC / rel
    spec = importlib.util.spec_from_file_location(name, str(full))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_universe() -> list[str]:
    files = sorted((REPO_ROOT / ".ly_state" / "session" / "universe").glob("universe_*.json"),
                   reverse=True)
    if not files:
        raise FileNotFoundError("No universe file from Phase 1.7")
    with open(files[0]) as f:
        data = json.load(f)
    if isinstance(data, dict):
        # Phase 1.7 schema: {"universe": [{"ticker": ..., "score": ...}, ...]}
        univ = data.get("universe") or data.get("tickers") or []
        if univ and isinstance(univ[0], dict):
            tickers = [u["ticker"] for u in univ]
        else:
            tickers = list(univ)
    else:
        tickers = list(data)
    logger.info("Universe: %d tickers from %s", len(tickers), files[0].name)
    return tickers


def load_panel(tickers: list[str], year_start: int, year_end: int) -> pd.DataFrame:
    src = REPO_ROOT / "data" / "market_2015_now.parquet"
    if not src.exists():
        raise FileNotFoundError(f"Missing market data: {src}")
    df = pd.read_parquet(src)
    df["date"] = pd.to_datetime(df["date"])
    panel = df[(df["ticker"].isin(tickers))
               & (df["date"].dt.year >= year_start)
               & (df["date"].dt.year <= year_end)].copy()
    # Compute features need ticker-grouped time order (rolling alphas).
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    logger.info("Panel: %d rows, %d tickers, %s..%s",
                len(panel), panel["ticker"].nunique(),
                panel["date"].min().date(), panel["date"].max().date())
    return panel


def compute_target(panel: pd.DataFrame, horizon: int = 5) -> pd.Series:
    return panel.groupby("ticker")["close"].transform(
        lambda s: s.shift(-horizon) / s - 1.0)


def cs_zscore(df: pd.DataFrame, feat_cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    g = df.groupby("date")
    for c in feat_cols:
        m = g[c].transform("mean")
        s = g[c].transform("std").replace(0, 1.0)
        out[c] = (df[c] - m) / s
    return out


def evaluate_fold(X_tr, y_tr, X_te, y_te,
                  alphas=(0.1, 1.0, 10.0, 100.0)) -> dict:
    best_ic, best_pred, best_a = -np.inf, None, alphas[0]
    for a in alphas:
        m = Ridge(alpha=a, random_state=42)
        m.fit(X_tr, y_tr)
        p = m.predict(X_te)
        ic = 0.0 if np.std(p) < 1e-12 else float(np.corrcoef(p, y_te)[0, 1])
        if ic > best_ic:
            best_ic, best_pred, best_a = ic, p, a
    return {"ic": best_ic, "pred": best_pred, "alpha": best_a}


def fold_returns(pred: np.ndarray, y: np.ndarray) -> np.ndarray:
    if len(pred) == 0:
        return np.array([])
    return np.sign(pred - np.median(pred)) * y


def run_pipeline(X: np.ndarray, y: np.ndarray, ts: pd.Series,
                 cpcv_mod, dsr_mod, label: str,
                 label_horizon: int = 5) -> dict:
    cpcv = cpcv_mod.CombinatorialPurgedKFold(
        n_splits=10, n_test_splits=2, embargo_pct=0.01,
        label_horizon=label_horizon)
    folds, all_rets, trial_srs = [], [], []
    for fid, (tr, te) in enumerate(cpcv.split(ts)):
        r = evaluate_fold(X[tr], y[tr], X[te], y[te])
        rets = fold_returns(r["pred"], y[te])
        sr = (float(np.mean(rets) / np.std(rets, ddof=1))
              if len(rets) > 1 and np.std(rets, ddof=1) > 0 else 0.0)
        if sr != 0.0:
            trial_srs.append(sr)
        all_rets.extend(rets.tolist())
        folds.append({"fold": fid, "ic": r["ic"], "sr": sr,
                      "n_test": int(len(te)), "alpha": r["alpha"]})
    dsr = dsr_mod.deflated_sharpe_ratio(
        np.asarray(all_rets), n_trials=len(folds),
        trial_sharpes=trial_srs, periods_per_year=252)
    summary = {
        "label": label, "n_features": int(X.shape[1]),
        "n_samples": int(len(y)), "n_folds": len(folds),
        "median_fold_ic": float(np.median([f["ic"] for f in folds])),
        "median_fold_sharpe": float(np.median([f["sr"] for f in folds])),
        "dsr_sharpe": dsr.sr, "dsr_sharpe_annualized": dsr.sr_annualized,
        "dsr_value": dsr.dsr, "dsr_pass_threshold": dsr.pass_threshold,
        "dsr_skew": dsr.skew, "dsr_kurtosis": dsr.kurtosis,
        "fold_metrics": folds,
    }
    logger.info("[%s] folds=%d med_IC=%.4f med_SR=%.4f DSR=%.3f",
                label, len(folds), summary["median_fold_ic"],
                summary["median_fold_sharpe"], dsr.dsr)
    return summary


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--year-start", type=int, default=2020)
    p.add_argument("--year-end", type=int, default=2024)
    p.add_argument("--out", default=".ly_state/session/phase3_3_cpcv_results.json")
    args = p.parse_args()

    cpcv_mod = _import("_cpcv", "omega/quant/validation/cpcv.py")
    dsr_mod = _import("_dsr", "omega/quant/validation/dsr.py")
    feat_mod = _import("_feat", "omega/quant/evolution/feature_adapter.py")

    tickers = load_universe()
    if args.smoke:
        tickers = tickers[:5]
        logger.info("SMOKE MODE: 5 tickers")

    panel = load_panel(tickers, args.year_start, args.year_end)
    if panel.empty:
        logger.error("Empty panel after year filter")
        return 1

    target = compute_target(panel, horizon=5)
    adapter = feat_mod.GPFeatureAdapter()
    feat_dict = adapter.compute_all(panel, top_n_features=125)
    feat_names = list(feat_dict.keys())
    feat_df = pd.DataFrame(feat_dict, index=panel.index)
    feat_df["ticker"] = panel["ticker"].values
    feat_df["date"] = panel["date"].values
    feat_df["target"] = target.values

    # Re-sort by (date, ticker) so CPCV sees calendar-time bars.
    feat_df = feat_df.sort_values(["date", "ticker"]).reset_index(drop=True)
    valid_mask = (~feat_df["target"].isna()
                  & ~feat_df[feat_names].isna().any(axis=1))
    feat_df = feat_df[valid_mask].reset_index(drop=True)

    X = feat_df[feat_names].to_numpy()
    y = feat_df["target"].to_numpy()
    # Use integer positions as the bar axis. label_horizon=5 in calendar
    # days = 5 * n_tickers in flattened panel positions.
    n_tickers = feat_df["ticker"].nunique()
    bar_horizon = 5 * n_tickers
    ts = pd.Series(np.arange(len(y)))
    logger.info("After NaN drop: %d samples, %d features, %d tickers, bar_horizon=%d",
                len(y), X.shape[1], n_tickers, bar_horizon)

    summary = run_pipeline(X, y, ts, cpcv_mod, dsr_mod, "A_baseline_alphas",
                            label_horizon=bar_horizon)

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"baseline": summary}, f, indent=2, default=str)
    logger.info("Saved: %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
