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

def load_universe_walk_forward(year_start: int, year_end: int) -> dict:
    """Walk-forward: load yearly universe files {year: [tickers]} for OOS years.

    For year Y, uses universe_<Y>-01-02.json (trained on data <= Y-1).
    No look-ahead at universe level.
    """
    base = REPO_ROOT / ".ly_state/session/universe"
    out = {}
    for year in range(year_start, year_end + 1):
        f = base / f"universe_{year}-01-02.json"
        if not f.exists():
            raise FileNotFoundError(f"Walk-forward file missing: {f}")
        with open(f) as fh:
            data = json.load(fh)
        tickers = [u["ticker"] for u in data["universe"]]
        out[year] = tickers
        logger.info("Year %d universe: %d tickers (top=%s)", year, len(tickers), tickers[:5])
    return out

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

def load_panel_walk_forward(yearly_universes: dict, year_start: int, year_end: int) -> pd.DataFrame:
    """Load panel with year-aware universe filter (PIT walk-forward)."""
    df = pd.read_parquet(REPO_ROOT / "data/market_2015_now.parquet")
    df["date"] = pd.to_datetime(df["date"])
    frames = []
    for year, tickers in yearly_universes.items():
        chunk = df[(df["ticker"].isin(tickers))
                   & (df["date"].dt.year == year)].copy()
        frames.append(chunk)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    logger.info("WF Panel: %d rows, %d unique tickers, %s..%s",
                len(panel), panel["ticker"].nunique(),
                panel["date"].min().date(), panel["date"].max().date())
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

def per_date_returns(pred, y_te, dates_te, tickers_te=None,
                     apply_tail=False, tail_mod=None, tail_kwargs=None):
    """P1-1: per-date long-short demedian portfolio.

    If apply_tail=True and tail_mod is the tail_controls module,
    apply 3 tail controls (per-name cap, vol target, DD breaker).
    """
    if len(pred) == 0:
        return np.array([])
    if tail_kwargs is None:
        tail_kwargs = {}
    df = pd.DataFrame({"pred": pred, "y": y_te, "date": dates_te})
    if tickers_te is not None:
        df["ticker"] = tickers_te

    if not apply_tail or tail_mod is None or tickers_te is None:
        # Original aggregated path
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

    # Tail-control path: build (T x N) weight + return matrices.
    pivot_w = pd.DataFrame(0.0, index=sorted(df["date"].unique()),
                            columns=sorted(df["ticker"].unique()))
    pivot_y = pivot_w.copy()

    # Phase 3.6 knobs (passed via tail_kwargs).
    top_k = (tail_kwargs or {}).get('top_k', 0)
    rebal_threshold = (tail_kwargs or {}).get('rebal_threshold', 0.0)

    prev_date_w = None
    sorted_dates = sorted(df["date"].unique())
    for date in sorted_dates:
        g = df[df["date"] == date]
        if len(g) < 2:
            if prev_date_w is not None:
                # Sticky: copy previous weights when we cannot rebalance
                pivot_w.loc[date] = prev_date_w
            for tk, ret in zip(g["ticker"].values, g["y"].values):
                pivot_y.loc[date, tk] = ret
            continue

        if top_k > 0:
            # Sparse: top-K long, bottom-K short, equal weight, others zero
            ranked = g.sort_values("pred", ascending=False)
            n = len(ranked)
            k_eff = min(top_k, n // 2)
            longs = ranked.head(k_eff)["ticker"].tolist()
            shorts = ranked.tail(k_eff)["ticker"].tolist()
            w_dict = {}
            for tk in longs:
                w_dict[tk] = 1.0 / k_eff
            for tk in shorts:
                w_dict[tk] = -1.0 / k_eff
        else:
            # Full demedian
            pos = np.sign(g["pred"].values - g["pred"].median())
            if np.all(pos == 0):
                if prev_date_w is not None:
                    pivot_w.loc[date] = prev_date_w
                continue
            nl = max(int((pos > 0).sum()), 1)
            ns = max(int((pos < 0).sum()), 1)
            w_arr = np.where(pos > 0, 1.0 / nl, np.where(pos < 0, -1.0 / ns, 0.0))
            w_dict = dict(zip(g["ticker"].values, w_arr))

        # Threshold rebalance: stick with previous weights if change is small
        if prev_date_w is not None and rebal_threshold > 0:
            new_row = pd.Series(0.0, index=pivot_w.columns)
            for tk, wt in w_dict.items():
                if tk in new_row.index:
                    new_row[tk] = wt
            delta = (new_row - prev_date_w).abs().sum()
            if delta < rebal_threshold:
                pivot_w.loc[date] = prev_date_w
                for tk, ret in zip(g["ticker"].values, g["y"].values):
                    pivot_y.loc[date, tk] = ret
                continue
            row_to_set = new_row
        else:
            row_to_set = pd.Series(0.0, index=pivot_w.columns)
            for tk, wt in w_dict.items():
                if tk in row_to_set.index:
                    row_to_set[tk] = wt

        pivot_w.loc[date] = row_to_set
        for tk, ret in zip(g["ticker"].values, g["y"].values):
            pivot_y.loc[date, tk] = ret
        prev_date_w = row_to_set
    # BT-2 fix: seed warmup_history with TRAIN portfolio returns to avoid
    # 60-bar scale=1.0 warmup at start of every test fold.
    warmup = tail_kwargs.get('train_pre_lev_history') if tail_kwargs else None
    adj_w, port_rets = tail_mod.apply_tail_controls(
        pivot_w, pivot_y.to_numpy(),
        target_vol_ann=0.15, max_abs_weight=0.05,
        dd_window=20, dd_threshold=0.08, dd_cut=0.5,
        warmup_history=warmup)
    # Phase 3.5: apply realistic execution costs if exec_mod is provided.
    exec_mod = tail_kwargs.get('exec_mod') if tail_kwargs else None
    capital = tail_kwargs.get('capital_vnd', 1e9) if tail_kwargs else 1e9
    if exec_mod is not None:
        _, port_rets, br = exec_mod.apply_realistic_tc(
            adj_w, pivot_y.to_numpy(),
            daily_adv=None,  # ADV not yet wired through panel
            portfolio_capital_vnd=capital,
        )
        # Stash breakdown in module-level for run_pipeline to log
        per_date_returns._last_cost_breakdown = br
    return np.asarray(port_rets)

def run_pipeline(X, y, ts, dates, cpcv_mod, dsr_mod, label, label_horizon,
                 tickers=None, tail_mod=None, n_alphas=4,
                 exec_mod_param=None, capital_vnd_param=1e9,
                 top_k_param=0, rebal_threshold_param=0.0):
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
        # BT-2 fix: seed tail-control vol history with TRAIN-fold portfolio rets
        train_warmup = None
        if tail_mod is not None and tickers is not None:
            train_pred = evaluate_fold(X_tr, y[tr], X_tr, y[tr])  # in-sample fit
            train_dates_arr = dates[tr]
            train_tickers_arr = tickers[tr]
            df_tr = pd.DataFrame({"p": train_pred["pred"], "y": y[tr],
                                  "d": train_dates_arr, "t": train_tickers_arr})
            daily_tr = []
            for _, g in df_tr.groupby("d"):
                if len(g) < 2:
                    continue
                pos = np.sign(g["p"].values - g["p"].median())
                if np.all(pos == 0):
                    continue
                nl, ns = max(int((pos > 0).sum()), 1), max(int((pos < 0).sum()), 1)
                w = np.where(pos > 0, 1.0 / nl, np.where(pos < 0, -1.0 / ns, 0.0))
                daily_tr.append(float(np.sum(w * g["y"].values)))
            train_warmup = np.asarray(daily_tr[-120:]) if daily_tr else None
        tail_kwargs = {}
        if train_warmup is not None:
            tail_kwargs["train_pre_lev_history"] = train_warmup
        if exec_mod_param is not None:
            tail_kwargs["exec_mod"] = exec_mod_param
            tail_kwargs["capital_vnd"] = capital_vnd_param
        if top_k_param > 0:
            tail_kwargs["top_k"] = top_k_param
        if rebal_threshold_param > 0:
            tail_kwargs["rebal_threshold"] = rebal_threshold_param
        if not tail_kwargs:
            tail_kwargs = None
        rets = per_date_returns(r["pred"], y[te], dates[te],
                                tickers_te=tickers[te] if tickers is not None else None,
                                apply_tail=tail_mod is not None, tail_mod=tail_mod,
                                tail_kwargs=tail_kwargs)
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
    p.add_argument("--walk-forward", action="store_true", help="Use per-year walk-forward universe (Phase 1.5 v2 fix)")
    p.add_argument("--tail-controls", action="store_true", help="Apply Phase 3.4 tail controls (vol target + cap + DD breaker)")
    p.add_argument("--realistic-tc", action="store_true", help="Apply Phase 3.5 realistic VN execution costs (commission + spread + slippage)")
    p.add_argument("--capital-vnd", type=float, default=1e9, help="Portfolio capital VND for slippage scaling (default 1B)")
    p.add_argument("--top-k", type=int, default=0, help="Sparse positions: long top-K, short bottom-K (0 = full demedian)")
    p.add_argument("--rebal-threshold", type=float, default=0.0, help="Rebalance only when sum |delta_w| > threshold (0 = always)")
    p.add_argument("--year-start", type=int, default=2020)
    p.add_argument("--year-end", type=int, default=2024)
    p.add_argument("--out", default=".ly_state/session/phase3_3_v2.json")
    args = p.parse_args()
    cpcv_mod = _import("_cpcv", "omega/quant/validation/cpcv.py")
    dsr_mod = _import("_dsr", "omega/quant/validation/dsr.py")
    feat_mod = _import("_feat", "omega/quant/evolution/feature_adapter.py")
    tail_mod = _import("_tc", "omega/quant/portfolio/tail_controls.py") if args.tail_controls else None
    exec_mod = _import("_es", "omega/quant/portfolio/execution_sim.py") if args.realistic_tc else None
    if args.walk_forward:
        wf = load_universe_walk_forward(args.year_start, args.year_end)
        if args.smoke:
            wf = {y: t[:5] for y, t in wf.items()}
            logger.info("SMOKE WF: 5 tickers/year")
        panel = load_panel_walk_forward(wf, args.year_start, args.year_end)
    else:
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
    tickers_arr = feat_df["ticker"].to_numpy() if args.tail_controls else None
    summary = run_pipeline(X, y, ts, dates, cpcv_mod, dsr_mod, "A_baseline_alphas",
                            label_horizon=bar_horizon, tickers=tickers_arr, tail_mod=tail_mod,
                            exec_mod_param=exec_mod, capital_vnd_param=args.capital_vnd,
                            top_k_param=args.top_k, rebal_threshold_param=args.rebal_threshold)
    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"baseline": summary}, f, indent=2, default=str)
    if hasattr(per_date_returns, '_last_cost_breakdown'):
        br = per_date_returns._last_cost_breakdown
        logger.info("COSTS: avg=%.1fbps/bar, turnover=%.2f/bar, total=%.4f (commission=%.4f, spread=%.4f, slip=%.4f)",
                     br["avg_cost_per_bar_bps"], br["avg_turnover_per_bar"],
                     br["total_cost"], br["total_commission_cost"],
                     br["total_spread_cost"], br["total_slippage_cost"])
        summary["cost_breakdown"] = br
        with open(out, "w") as f2:
            json.dump({"baseline": summary}, f2, indent=2, default=str)
    logger.info("Saved: %s", out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
