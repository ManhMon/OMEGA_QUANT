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

# Phase 5: wire existing DataSanitizer + AlphaSanitizer modules
for _p in (
    REPO_ROOT / "packages" / "data" / "src",
    REPO_ROOT / "src",
):
    sp = str(_p)
    if _p.exists() and sp not in sys.path:
        sys.path.insert(0, sp)
try:
    from omega.data.sanitizer import DataSanitizer  # canonical
except Exception:
    DataSanitizer = None
try:
    from omega.quant.alpha_sanitizer import AlphaSanitizer
except Exception:
    AlphaSanitizer = None


def mask_suspended(panel: pd.DataFrame) -> pd.DataFrame:
    """Phase 5: drop bars where volume == 0 (suspended trading).
    These are non-tradable, would corrupt ADV / slippage / returns.
    """
    n0 = len(panel)
    out = panel[panel["volume"] > 0].reset_index(drop=True)
    logger.info("mask_suspended: dropped %d / %d rows (%.1f%%) with volume==0",
                n0 - len(out), n0, 100.0 * (n0 - len(out)) / max(n0, 1))
    return out


def sanitize_ohlcv(panel: pd.DataFrame) -> pd.DataFrame:
    """Phase 5: apply DataSanitizer (forward-fill <=3d, clip 3 sigma per
    symbol, dedup, min_price=0.01).

    PIT scope: BOUNDED to backtest slice, NOT strict per-date.
    DataSanitizer.fit/apply uses full-sample per-symbol mean/std for
    the 3-sigma outlier clip. Cleaning of an early date can technically
    see later in-slice statistics, but never sees data outside the
    backtest panel (which is restricted by ticker universe + year range
    BEFORE this call). Acceptable for backtest reporting; for live
    paper-trading switch to the legacy expanding-window path
    (DataSanitizer._clip_outliers, sanitizer.py:325-367) or per-fold
    sanitize.

    Note: canonical DataSanitizer.apply() drops the symbol column (it uses
    groupby+transform which strips the group key). We work around by saving
    a (input_idx -> ticker) map and re-attaching after apply().
    """
    if DataSanitizer is None:
        logger.warning("DataSanitizer unavailable - skipping OHLCV sanitization")
        return panel
    max_date = pd.to_datetime(panel["date"].max())
    san = DataSanitizer(max_fill_days=3, outlier_sigma=3.0, min_price=0.01,
                        as_of_time=max_date)
    san.fit(panel, symbol_col="ticker", date_col="date")
    # Save ticker by original index BEFORE apply (which drops the column).
    panel_in = panel.copy()
    panel_in["_orig_idx"] = np.arange(len(panel_in))
    cleaned = san.apply(panel_in, symbol_col="ticker", date_col="date")
    if "ticker" not in cleaned.columns:
        # Use _orig_idx (preserved through groupby+transform) to reattach ticker.
        if "_orig_idx" not in cleaned.columns:
            # Fallback: index-align (DataSanitizer keeps the original index).
            cleaned["ticker"] = panel_in.loc[cleaned.index, "ticker"].values
        else:
            ticker_map = dict(zip(panel_in["_orig_idx"].values, panel_in["ticker"].values))
            cleaned["ticker"] = cleaned["_orig_idx"].map(ticker_map)
            cleaned = cleaned.drop(columns=["_orig_idx"])
    s = san.sanitization_stats
    logger.info("sanitize_ohlcv: in=%d dup=%d ffill=%d clipped=%d invalid=%d out=%d",
                s.get("input_rows", 0), s.get("duplicates_removed", 0),
                s.get("forward_filled", 0), s.get("outliers_clipped", 0),
                s.get("invalid_prices_removed", 0), s.get("output_rows", 0))
    return cleaned


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

def _attach_adv(panel: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Phase 3.8: Add per-ticker ADV (VND) with T-1 PIT lag.

    ADV_t = rolling_<window>(volume_t * close_t).mean().shift(1)
    Shift(1) ensures execution at bar t uses ADV computed strictly before t.
    """
    panel = panel.sort_values(["ticker", "date"]).copy()
    panel["_dollar_vol"] = panel["volume"].astype(float) * panel["close"].astype(float)
    panel["adv_vnd"] = (
        panel.groupby("ticker")["_dollar_vol"]
             .transform(lambda s: s.rolling(window, min_periods=max(5, window // 4)).mean().shift(1))
    )
    panel = panel.drop(columns=["_dollar_vol"])
    return panel

def load_panel(tickers, year_start, year_end):
    df = pd.read_parquet(REPO_ROOT / "data/market_2015_now.parquet")
    df["date"] = pd.to_datetime(df["date"])
    # Pull 1 year extra history before year_start so the 20d ADV warm-up is
    # computed PIT-correctly on prior data (not on intra-fold data).
    panel = df[(df["ticker"].isin(tickers)) & (df["date"].dt.year >= year_start - 1) & (df["date"].dt.year <= year_end)].copy()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    # Phase 5: clean BEFORE ADV (so dropped suspended bars don't pollute ADV)
    panel = mask_suspended(panel)
    panel = sanitize_ohlcv(panel)
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    panel = _attach_adv(panel)
    panel = panel[panel["date"].dt.year >= year_start].reset_index(drop=True)
    logger.info("Panel: %d rows, %d tickers, %s..%s, adv_vnd non-null=%d", len(panel), panel["ticker"].nunique(), panel["date"].min().date(), panel["date"].max().date(), int(panel["adv_vnd"].notna().sum()))
    return panel

def load_panel_walk_forward(yearly_universes: dict, year_start: int, year_end: int) -> pd.DataFrame:
    """Load panel with year-aware universe filter (PIT walk-forward).

    Pulls 1 year of pre-history per yearly slice so ADV can warm up without
    contaminating in-fold data.
    """
    df = pd.read_parquet(REPO_ROOT / "data/market_2015_now.parquet")
    df["date"] = pd.to_datetime(df["date"])
    # Build a (ticker, date) -> universe_year lookup so we can re-tag after
    # sanitize_ohlcv (which would otherwise dedup our duplicate marker).
    frames = []
    universe_year_map = {}
    for year, tickers in yearly_universes.items():
        chunk = df[(df["ticker"].isin(tickers))
                   & (df["date"].dt.year >= year - 1)
                   & (df["date"].dt.year <= year)].copy()
        # If a (ticker, date) pair appears in multiple yearly slices, keep
        # the LARGEST year (= the slice that owns the in-fold rows).
        for ticker, date in zip(chunk["ticker"].values, chunk["date"].values):
            key = (ticker, pd.Timestamp(date))
            universe_year_map[key] = max(universe_year_map.get(key, 0), year)
        frames.append(chunk)
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    # Phase 5: clean BEFORE ADV (so dropped suspended bars don't pollute ADV)
    panel = mask_suspended(panel)
    panel = sanitize_ohlcv(panel)
    # Re-tag universe_year (sanitize_ohlcv may have deduped or reordered)
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    panel["_universe_year"] = [
        universe_year_map.get((t, pd.Timestamp(d)), 0)
        for t, d in zip(panel["ticker"].values, panel["date"].values)
    ]
    panel = _attach_adv(panel)
    # Keep only rows whose date.year matches the universe year that owns them.
    panel = panel[panel["date"].dt.year == panel["_universe_year"]].drop(columns=["_universe_year"]).reset_index(drop=True)
    logger.info("WF Panel: %d rows, %d unique tickers, %s..%s, adv_vnd non-null=%d",
                len(panel), panel["ticker"].nunique(),
                panel["date"].min().date(), panel["date"].max().date(),
                int(panel["adv_vnd"].notna().sum()))
    return panel

def compute_target(panel, horizon=5):
    return panel.groupby("ticker")["close"].transform(lambda s: s.shift(-horizon) / s - 1.0)


# Phase 4: LSTM helper. Builds sequences inside the fold from already
# z-scored 2D features (caller provides train-only mu/sd), trains a
# fresh LSTMAlpha, and returns predictions aligned with X_te rows.
# Rows that lack lookback history are left at 0 (Ridge ensemble dominates
# there, safe fallback).
def _lstm_predict_fold(
    X_tr_z: np.ndarray, y_tr: np.ndarray,
    X_te_z: np.ndarray,
    feat_df: pd.DataFrame, feat_names: list,
    tr_idx: np.ndarray, te_idx: np.ndarray,
    cfg, lstm_mod,
):
    work = feat_df.iloc[np.concatenate([tr_idx, te_idx])][["ticker", "date"]].copy()
    z_all = np.vstack([X_tr_z, X_te_z])
    for i, fn in enumerate(feat_names):
        work[fn] = z_all[:, i]
    work = work.reset_index(drop=True)
    X_seq, idx_into_work = lstm_mod.build_sequences(work, feat_names, cfg.lookback)
    if len(X_seq) == 0:
        return np.zeros(len(te_idx), dtype=np.float64)
    n_tr = len(tr_idx)
    train_mask = idx_into_work < n_tr
    test_mask = ~train_mask
    y_full = np.concatenate([y_tr, np.zeros(len(te_idx))])
    X_seq_tr = X_seq[train_mask]
    y_seq_tr = y_full[idx_into_work[train_mask]]
    X_seq_te = X_seq[test_mask]
    te_targets = idx_into_work[test_mask] - n_tr
    if len(X_seq_tr) < cfg.min_train_samples or len(X_seq_te) == 0:
        return np.zeros(len(te_idx), dtype=np.float64)
    model = lstm_mod.LSTMAlpha(cfg).fit(X_seq_tr, y_seq_tr)
    pred_te = model.predict(X_seq_te)
    out = np.zeros(len(te_idx), dtype=np.float64)
    out[te_targets] = pred_te
    return out


def _per_date_zscore(X: np.ndarray, dates: np.ndarray) -> np.ndarray:
    """Phase 8 vector #1: cross-sectional z-score per day, vectorized.

    For each unique date, demean and rescale features by within-day mean/std.
    Cross-sectional ops only use same-day data, so this is strictly PIT.
    Zero-std days fall back to scale=1 (preserves sign-only information).
    NaN/Inf cells are zeroed.
    """
    if X.size == 0:
        return X
    df = pd.DataFrame(X)
    df["_date"] = dates
    feat_cols = [c for c in df.columns if c != "_date"]
    grp = df.groupby("_date", sort=False)
    means = grp[feat_cols].transform("mean")
    stds = grp[feat_cols].transform("std").replace(0.0, np.nan).fillna(1.0)
    out_arr = ((df[feat_cols].to_numpy() - means.to_numpy()) / stds.to_numpy()).astype(np.float64)
    return np.nan_to_num(out_arr, nan=0.0, posinf=0.0, neginf=0.0)


def evaluate_fold(X_tr, y_tr, X_te, y_te, alphas=(0.1, 1.0, 10.0, 100.0)):
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
                     apply_tail=False, tail_mod=None, tail_kwargs=None,
                     adv_te=None):
    """P1-1: per-date long-short demedian portfolio.

    If apply_tail=True and tail_mod is the tail_controls module,
    apply 3 tail controls (per-name cap, vol target, DD breaker).

    adv_te: optional 1-D array of ADV (VND) aligned with pred/y_te/tickers_te.
             When provided, slippage uses real per-name ADV instead of None.
    """
    if len(pred) == 0:
        return np.array([])
    if tail_kwargs is None:
        tail_kwargs = {}
    df = pd.DataFrame({"pred": pred, "y": y_te, "date": dates_te})
    if tickers_te is not None:
        df["ticker"] = tickers_te
    if adv_te is not None and tickers_te is not None:
        df["adv"] = adv_te

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
    pivot_adv = pivot_w.copy() if adv_te is not None else None

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
        if pivot_adv is not None:
            for tk, adv_val in zip(g["ticker"].values, g["adv"].values):
                pivot_adv.loc[date, tk] = adv_val
        prev_date_w = row_to_set
    # BT-2 fix: seed warmup_history with TRAIN portfolio returns to avoid
    # 60-bar scale=1.0 warmup at start of every test fold.
    warmup = tail_kwargs.get('train_pre_lev_history') if tail_kwargs else None
    adj_w, port_rets = tail_mod.apply_tail_controls(
        pivot_w, pivot_y.to_numpy(),
        target_vol_ann=0.15, max_abs_weight=0.05,
        dd_window=20, dd_threshold=0.08, dd_cut=0.5,
        warmup_history=warmup)
    # Phase 3.5/3.8/3.10: apply realistic execution costs if exec_mod is provided.
    exec_mod = tail_kwargs.get('exec_mod') if tail_kwargs else None
    capital = tail_kwargs.get('capital_vnd', 1e9) if tail_kwargs else 1e9
    if exec_mod is not None:
        adv_matrix = pivot_adv.to_numpy() if pivot_adv is not None else None
        # Phase 3.10 P1 (codex L3 follow-up): prev_w_dict path is wired
        # but DELIBERATELY left disconnected from run_pipeline's CPCV
        # loop -- it is here for the live-trading harness, not for
        # combinatorial CPCV (auto-carry across non-adjacent folds was
        # measured to inflate turnover +1.8%). Live callers can pass
        # tail_kwargs["prev_w_dict"] = <last_run_final_w> to chain runs;
        # CPCV path leaves it None so prev_w_init defaults to zeros.
        prev_w_init = None
        prev_w_dict = tail_kwargs.get('prev_w_dict') if tail_kwargs else None
        if prev_w_dict:
            cols = list(adj_w.columns)
            prev_w_init = np.asarray(
                [prev_w_dict.get(c, 0.0) for c in cols], dtype=float
            )
        _, port_rets, br = exec_mod.apply_realistic_tc(
            adj_w, pivot_y.to_numpy(),
            daily_adv=adv_matrix,  # Phase 3.8: real ADV per (date, ticker)
            portfolio_capital_vnd=capital,
            prev_w_init=prev_w_init,
        )
        # Stash breakdown in module-level for run_pipeline to log
        per_date_returns._last_cost_breakdown = br
        # Expose final weights so live-harness callers can chain runs.
        # (Unused inside CPCV run_pipeline by design; see note above.)
        final_w_arr = br.get("final_w")
        if final_w_arr is not None:
            per_date_returns._last_final_w_dict = dict(
                zip(list(adj_w.columns), [float(x) for x in final_w_arr])
            )
        else:
            per_date_returns._last_final_w_dict = {}
    return np.asarray(port_rets)

def run_pipeline(X, y, ts, dates, cpcv_mod, dsr_mod, label, label_horizon,
                 tickers=None, tail_mod=None, n_alphas=4,
                 exec_mod_param=None, capital_vnd_param=1e9,
                 top_k_param=0, rebal_threshold_param=0.0,
                 signal_ema_param=0, embargo_pct_param=0.01,
                 adv_arr=None,
                 lstm_cfg=None, lstm_mod=None, feat_df=None, feat_names=None,
                 lstm_blend=0.5):
    cpcv = cpcv_mod.CombinatorialPurgedKFold(n_splits=10, n_test_splits=2,
                                              embargo_pct=embargo_pct_param,
                                              label_horizon=label_horizon)
    folds, daily_rets, trial_srs = [], [], []
    # Phase 3.10 P1 note: codex audit suggested carrying prev_w between
    # folds to avoid the bar-0 open-from-cash bias. We initially tried
    # auto-carrying across consecutive CPCV folds, but CPCV folds are
    # COMBINATORIAL (45 folds = C(10,2)), not chronological -- their
    # test windows interleave on the calendar. Carrying weights between
    # non-adjacent folds frequently flips signs and INFLATES turnover
    # (Phase 3.10 measured +1.8%). The principled fix would be to seed
    # each fold's prev_w with the last bar of THAT fold's train period,
    # which requires running the cost loop on the in-sample fit too.
    # For now we keep prev_w_init=None (zero cold-start, codex-known
    # 0.4% bias, RELATIVE capacity ranking unaffected) and rely on the
    # explicit prev_w_init API for live-trading callers.
    for fid, (tr, te) in enumerate(cpcv.split(ts)):
        X_tr, X_te = X[tr], X[te]
        # P1-3: zscore inside fold (train-only stats)
        # Phase 5: also winsorize columns at train-fold percentiles to
        # tame outliers (e.g. unadjusted CA spikes) BEFORE z-scoring.
        # Both ops are train-only fitted -> PIT-safe.
        try:
            lo = np.nanpercentile(X_tr, 1.0, axis=0)
            hi = np.nanpercentile(X_tr, 99.0, axis=0)
            X_tr = np.clip(X_tr, lo, hi)
            X_te = np.clip(X_te, lo, hi)
        except Exception as exc:
            logger.warning("winsorize skipped: %s", exc)
        # Phase 8 attempted vector #1 (per-DATE z-score on features) -
        # REVERTED. Empirically destroys alpha (IC +0.16 -> -0.006 in
        # smoke). Cross-sectional zscore on features removes the
        # information Ridge needs to rank tickers across days.
        mu = np.nanmean(X_tr, axis=0)
        sd = np.nanstd(X_tr, axis=0, ddof=1)
        sd = np.where(sd < 1e-12, 1.0, sd)
        X_tr = (X_tr - mu) / sd
        X_te = (X_te - mu) / sd
        r = evaluate_fold(X_tr, y[tr], X_te, y[te])
        # Phase 4: optional LSTM ensemble. Train LSTM on the same z-scored
        # train fold, predict on test, then blend with Ridge.
        if lstm_cfg is not None and lstm_mod is not None and feat_df is not None:
            lstm_pred = _lstm_predict_fold(
                X_tr, y[tr], X_te, feat_df, list(feat_names),
                tr, te, lstm_cfg, lstm_mod,
            )
            # Diagnostic IC of LSTM alone (train-only would be cleaner; this
            # is just for logging on test fold).
            test_ic_lstm = (
                0.0 if np.std(lstm_pred) < 1e-12
                else float(np.corrcoef(lstm_pred, y[te])[0, 1])
            )
            r["pred_ridge"] = r["pred"].copy()
            r["pred_lstm"] = lstm_pred
            r["pred"] = (1.0 - lstm_blend) * r["pred"] + lstm_blend * lstm_pred
            r["ic_lstm"] = test_ic_lstm
        # Phase 3.7: per-ticker EMA smoothing of predictions
        # Note: previous attempt with sort_index() returned to feat_df-row index
        # (NOT te-position index) -> shuffled predictions and inverted alpha sign.
        # Fix: keep original te positions, smooth in (ticker, date) sorted view,
        # then map back via stable position index.
        if signal_ema_param > 0 and tickers is not None:
            te_tickers = tickers[te]
            te_dates = dates[te]
            # Phase 3.11: identify contiguous CPCV calendar blocks inside
            # this fold's test indices. CPCV(N=10, k=2) emits test_idx as
            # the union of two contiguous integer ranges (np.arange per
            # group), sorted. np.diff(te) > 1 cleanly marks the boundary.
            # EMA must RESET at each block boundary so the smoothing
            # span does not span the calendar gap between the two test
            # windows (e.g., Q1 2020 and Q3 2022 cannot share EMA state).
            if len(te) > 1:
                block_breaks = np.where(np.diff(te) > 1)[0]
                block_id = np.zeros(len(te), dtype=np.int64)
                for b in block_breaks:
                    block_id[b + 1:] += 1
            else:
                block_id = np.zeros(len(te), dtype=np.int64)
            df_pred = pd.DataFrame({
                "pred": r["pred"], "ticker": te_tickers, "date": te_dates,
                "block": block_id,
                "pos": np.arange(len(r["pred"]))
            })
            df_pred = df_pred.sort_values(["ticker", "block", "date"]).reset_index(drop=True)
            df_pred["pred_ema"] = df_pred.groupby(["ticker", "block"])["pred"].transform(
                lambda s: s.ewm(span=signal_ema_param, adjust=False).mean()
            )
            df_pred = df_pred.sort_values("pos").reset_index(drop=True)
            r["pred"] = df_pred["pred_ema"].to_numpy()
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
                                tail_kwargs=tail_kwargs,
                                adv_te=adv_arr[te] if adv_arr is not None else None)
        sr = float(np.mean(rets) / np.std(rets, ddof=1)) if (len(rets) > 1 and np.std(rets, ddof=1) > 0) else 0.0
        trial_srs.append(sr)  # P2-1: keep all
        daily_rets.extend(rets.tolist())
        folds.append({"fold": fid, "test_ic": r["ic"], "train_cv_ic": r["train_cv_ic"], "fold_sr": sr, "n_daily": int(len(rets)), "alpha": r["alpha"], "ic_lstm": r.get("ic_lstm", None)})
    # P0-2: n_trials = SEARCH dim
    dsr = dsr_mod.deflated_sharpe_ratio(np.asarray(daily_rets), n_trials=n_alphas, trial_sharpes=trial_srs, periods_per_year=252)
    # Phase 3.9: fold-level DSR (CPCV oversampling fix). Treats each
    # fold's per-bar Sharpe as one IID observation, avoiding the 9x
    # over-counting in pooled daily returns.
    fold_dsr_res = dsr_mod.fold_level_dsr(
        trial_srs, n_trials=n_alphas, periods_per_year=252
    ) if len(trial_srs) >= 2 else None
    s = {"label": label, "n_features": int(X.shape[1]), "n_samples": int(len(y)), "n_folds": len(folds), "n_daily": int(len(daily_rets)), "n_trials_dsr": n_alphas,
         "median_test_ic": float(np.median([f["test_ic"] for f in folds])),
         "median_train_cv_ic": float(np.median([f["train_cv_ic"] for f in folds])),
         "median_fold_sr": float(np.median([f["fold_sr"] for f in folds])),
         "dsr_sharpe": dsr.sr, "dsr_sr_ann": dsr.sr_annualized, "dsr": dsr.dsr, "pass": dsr.pass_threshold,
         "skew": dsr.skew, "kurt": dsr.kurtosis, "folds": folds}
    if fold_dsr_res is not None:
        s["fold_dsr"] = {
            "sr_mean_per_bar": fold_dsr_res.sr,
            "sr_mean_annualized": fold_dsr_res.sr_annualized,
            "sr_std_estim": fold_dsr_res.sr_std,
            "expected_max_sr": fold_dsr_res.expected_max_sr,
            "dsr": fold_dsr_res.dsr,
            "pass": fold_dsr_res.pass_threshold,
            "n_folds": fold_dsr_res.n_obs,
            "skew": fold_dsr_res.skew,
            "kurt": fold_dsr_res.kurtosis,
        }
    logger.info("[%s] folds=%d med_test_IC=%.4f med_train_IC=%.4f med_SR=%.4f DSR=%.3f n_daily=%d", label, len(folds), s["median_test_ic"], s["median_train_cv_ic"], s["median_fold_sr"], dsr.dsr, len(daily_rets))
    if fold_dsr_res is not None:
        logger.info("[%s] FOLD-DSR=%.3f sr_mean=%.4f (ann %.3f) sr_std=%.4f e_max=%.4f",
                    label, fold_dsr_res.dsr, fold_dsr_res.sr,
                    fold_dsr_res.sr_annualized, fold_dsr_res.sr_std,
                    fold_dsr_res.expected_max_sr)
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
    p.add_argument("--label-horizon", type=int, default=5, help="Forward return label horizon in days (default 5)")
    p.add_argument("--signal-ema", type=int, default=0, help="EMA span for prediction smoothing per ticker (0=disabled)")
    p.add_argument("--shuffle-y", action="store_true", help="Falsification test: randomize labels (must produce SR ~ 0 if no leakage)")
    p.add_argument("--embargo-pct", type=float, default=0.01, help="Embargo as fraction of N (default 0.01); bump to >= bar_horizon/N for AFML compliance")
    p.add_argument("--year-start", type=int, default=2020)
    p.add_argument("--year-end", type=int, default=2024)
    p.add_argument("--out", default=".ly_state/session/phase3_3_v2.json")
    p.add_argument("--lstm", action="store_true", help="Phase 4: enable Ridge+LSTM ensemble")
    p.add_argument("--lstm-blend", type=float, default=0.5, help="Phase 4: ensemble weight for LSTM (0=Ridge only, 1=LSTM only)")
    p.add_argument("--lstm-lookback", type=int, default=60, help="Phase 4: LSTM lookback window (days)")
    p.add_argument("--lstm-hidden", type=int, default=64, help="Phase 4: LSTM hidden size")
    p.add_argument("--lstm-epochs", type=int, default=8, help="Phase 4: LSTM training epochs per fold")
    p.add_argument("--lstm-loss", choices=["mse", "ic"], default="mse", help="Phase 6: LSTM loss function (mse=regression, ic=-Pearson)")
    args = p.parse_args()
    cpcv_mod = _import("_cpcv", "omega/quant/validation/cpcv.py")
    dsr_mod = _import("_dsr", "omega/quant/validation/dsr.py")
    feat_mod = _import("_feat", "omega/quant/evolution/feature_adapter.py")
    tail_mod = _import("_tc", "omega/quant/portfolio/tail_controls.py") if args.tail_controls else None
    exec_mod = _import("_es", "omega/quant/portfolio/execution_sim.py") if args.realistic_tc else None
    lstm_mod = _import("_lstm", "omega/quant/models/lstm_alpha.py") if args.lstm else None
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
    target = compute_target(panel, horizon=args.label_horizon)
    if args.shuffle_y:
        rng = np.random.default_rng(42)
        # Shuffle within each date (preserve cross-section structure but break alpha-target link)
        target_arr = target.to_numpy().copy()
        date_arr = panel["date"].to_numpy()
        unique_dates = np.unique(date_arr)
        for d in unique_dates:
            mask = date_arr == d
            idx = np.where(mask)[0]
            shuffled = rng.permutation(target_arr[idx])
            target_arr[idx] = shuffled
        target = pd.Series(target_arr, index=target.index)
        logger.info("FALSIFICATION TEST: y-shuffled within each date (alpha-target link broken)")
    feat_dict = feat_mod.GPFeatureAdapter().compute_all(panel, top_n_features=125)
    feat_names = list(feat_dict.keys())
    feat_df = pd.DataFrame(feat_dict, index=panel.index)
    feat_df["ticker"] = panel["ticker"].values
    feat_df["date"] = panel["date"].values
    feat_df["target"] = target.values
    feat_df["adv_vnd"] = panel["adv_vnd"].values if "adv_vnd" in panel.columns else np.nan
    feat_df = feat_df.sort_values(["date", "ticker"]).reset_index(drop=True)
    valid = ~feat_df["target"].isna() & ~feat_df[feat_names].isna().any(axis=1)
    feat_df = feat_df[valid].reset_index(drop=True)
    X = feat_df[feat_names].to_numpy()
    y = feat_df["target"].to_numpy()
    adv_arr = feat_df["adv_vnd"].to_numpy() if "adv_vnd" in feat_df.columns else None
    if adv_arr is not None:
        # Phase 3.10 P1 fix (codex L3): causal/PIT-safe ADV imputation.
        # OLD (Phase 3.8): np.nanmedian over full panel -> leaks future ADV.
        # NEW: expanding-median in date order, shifted by 1 row so bar t
        # only sees ADV history strictly before t. Cold-start NaN rows
        # (no prior history at all) are filled with 0.0, which forces
        # apply_realistic_tc to set slippage=0 for those bars (via the
        # adv_row > 0 guard) -- strictly PIT, no future-value leakage.
        # In the current CPCV pipeline this branch is dead code because
        # load_panel_walk_forward prefetches year-1 history; this is
        # purely defensive for live-trading callers without prehistory.
        if np.isnan(adv_arr).any():
            adv_series = pd.Series(adv_arr)
            causal_med = adv_series.expanding(min_periods=1).median().shift(1)
            # Strictly PIT: leading rows with no prior history get 0
            # (= no ADV known yet -> exec sim uses zero-slippage path).
            causal_med = causal_med.fillna(0.0)
            mask_nan = np.isnan(adv_arr)
            adv_arr = np.where(mask_nan, causal_med.to_numpy(), adv_arr)
            logger.info("ADV imputation: filled %d NaN cells via causal expanding median (cold-start fallback=0.0)",
                        int(mask_nan.sum()))
        logger.info("ADV stats (VND): median=%.2e p10=%.2e p90=%.2e",
                    float(np.median(adv_arr)), float(np.percentile(adv_arr, 10)),
                    float(np.percentile(adv_arr, 90)))
    max_per_date = int(feat_df.groupby("date").size().max())
    bar_horizon = 5 * max_per_date  # P1-2 fix
    ts = pd.Series(np.arange(len(y)))
    dates = feat_df["date"].to_numpy()
    logger.info("Drop NaN: %d samples, %d feats, max_per_date=%d, bar_horizon=%d", len(y), X.shape[1], max_per_date, bar_horizon)
    tickers_arr = feat_df["ticker"].to_numpy() if args.tail_controls else None
    # bar_horizon = args.label_horizon * max_per_date
    lstm_cfg = None
    if args.lstm and lstm_mod is not None:
        lstm_cfg = lstm_mod.LSTMAlphaConfig(
            lookback=args.lstm_lookback,
            n_features=int(X.shape[1]),
            hidden_size=args.lstm_hidden,
            epochs=args.lstm_epochs,
            loss=args.lstm_loss,
        )
        logger.info("LSTM enabled: lookback=%d hidden=%d epochs=%d blend=%.2f loss=%s",
                    lstm_cfg.lookback, lstm_cfg.hidden_size, lstm_cfg.epochs, args.lstm_blend, args.lstm_loss)
    summary = run_pipeline(X, y, ts, dates, cpcv_mod, dsr_mod, "A_baseline_alphas",
                            label_horizon=args.label_horizon * max_per_date,
                            tickers=tickers_arr, tail_mod=tail_mod,
                            exec_mod_param=exec_mod, capital_vnd_param=args.capital_vnd,
                            top_k_param=args.top_k, rebal_threshold_param=args.rebal_threshold,
                            signal_ema_param=args.signal_ema,
                            embargo_pct_param=args.embargo_pct,
                            adv_arr=adv_arr if (exec_mod is not None and tickers_arr is not None) else None,
                            lstm_cfg=lstm_cfg, lstm_mod=lstm_mod,
                            feat_df=feat_df if lstm_cfg is not None else None,
                            feat_names=feat_names if lstm_cfg is not None else None,
                            lstm_blend=args.lstm_blend)
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
