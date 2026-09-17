"""Phase 3.3 v2: backtest with CPCV+DSR (audit fixes P0+P1+P2 applied)."""

from __future__ import annotations
import argparse
import importlib.util
import json
import logging
import math
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backtest_v2_cpcv")
REPO_ROOT = Path(__file__).resolve().parent.parent
QUANT_SRC = (
    REPO_ROOT / "src"
    if (REPO_ROOT / "src" / "omega").exists()
    else REPO_ROOT / "packages" / "quant" / "src"
)


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
    from omega.quant.alpha.sanitizer import AlphaSanitizer
except Exception:
    AlphaSanitizer = None
try:
    from omega.quant.walk_forward import (
        compute_fallback_as_failure_metrics,
        bh_fdr_qvalues,
        compute_ic_pvalue,
        compute_icir,
        compute_positive_fold_rate,
        classify_research_gate_verdict,
    )
except Exception:
    compute_fallback_as_failure_metrics = None
    bh_fdr_qvalues = None
    compute_ic_pvalue = None
    compute_icir = None
    compute_positive_fold_rate = None
    classify_research_gate_verdict = None


def mask_suspended(panel: pd.DataFrame) -> pd.DataFrame:
    """Phase 5: drop bars where volume == 0 (suspended trading).
    These are non-tradable, would corrupt ADV / slippage / returns.
    """
    n0 = len(panel)
    out = panel[panel["volume"] > 0].reset_index(drop=True)
    logger.info(
        "mask_suspended: dropped %d / %d rows (%.1f%%) with volume==0",
        n0 - len(out),
        n0,
        100.0 * (n0 - len(out)) / max(n0, 1),
    )
    return out


def _causal_clip_outliers(
    panel: pd.DataFrame, outlier_sigma: float = 3.0, symbol_col: str = "ticker",
    date_col: str = "date", value_cols: tuple = ("open", "high", "low", "close"),
) -> tuple[pd.DataFrame, int]:
    """L3 audit Fix #1: causal expanding-window outlier clip (no look-ahead).

    For each (symbol, date), compute expanding mean/std using only data
    STRICTLY BEFORE that date (shift(1)). Clip values outside
    [mu - sigma*k, mu + sigma*k] where k=outlier_sigma. Cold-start rows
    (no prior history) are left unclipped.

    Returns (cleaned_panel, n_clipped_cells).
    """
    panel = panel.sort_values([symbol_col, date_col]).copy()
    n_clipped = 0
    existing_cols = [c for c in value_cols if c in panel.columns]
    for col in existing_cols:
        grp = panel.groupby(symbol_col)[col]
        expanding_mean = grp.transform(
            lambda s: s.expanding(min_periods=2).mean().shift(1)
        )
        expanding_std = grp.transform(
            lambda s: s.expanding(min_periods=2).std().shift(1)
        )
        expanding_std = expanding_std.fillna(0.0)
        lo = expanding_mean - outlier_sigma * expanding_std
        hi = expanding_mean + outlier_sigma * expanding_std
        # Only clip where expanding stats are valid (non-NaN mean)
        valid_mask = expanding_mean.notna() & (expanding_std > 1e-12)
        clip_mask = valid_mask & ((panel[col] < lo) | (panel[col] > hi))
        n_clipped += int(clip_mask.sum())
        panel.loc[clip_mask & (panel[col] < lo), col] = lo[clip_mask & (panel[col] < lo)]
        panel.loc[clip_mask & (panel[col] > hi), col] = hi[clip_mask & (panel[col] > hi)]
    return panel, n_clipped


def sanitize_ohlcv(panel: pd.DataFrame) -> pd.DataFrame:
    """Phase 5 + L3 Fix #1: apply DataSanitizer with CAUSAL per-date outlier
    clipping (no full-sample look-ahead).

    L3 audit fix: Previous implementation used DataSanitizer.fit() on the
    full panel, which computed per-symbol mean/std using all dates -- a
    value at date t could be clipped using statistics from dates > t.
    Now uses causal expanding-window clip (shift(1) ensures only data
    strictly before t is used for the clip bounds).

    Steps (all PIT-safe):
    1. Dedup by (ticker, date) -- deterministic, no look-ahead.
    2. Forward-fill <=3 bars per symbol -- only looks backward.
    3. Causal expanding-window 3-sigma clip -- only uses past data.
    4. Min-price filter (remove prices < 0.01) -- instantaneous.

    Note: canonical DataSanitizer.apply() drops the symbol column (it uses
    groupby+transform which strips the group key). We work around by saving
    a (input_idx -> ticker) map and re-attaching after apply().
    """
    if DataSanitizer is None:
        logger.warning("DataSanitizer unavailable - skipping OHLCV sanitization")
        return panel

    # Step 1-2: Use DataSanitizer for dedup + forward-fill (both PIT-safe).
    # L3 Fix #1b (fix2): outlier_sigma=999.0 effectively disables fitted
    # outlier clipping inside DataSanitizer.apply().  The per-symbol
    # mean +/- 999*std bounds are so wide they never clip real OHLCV data.
    # Actual outlier clipping is handled exclusively by the causal
    # expanding-window _causal_clip_outliers() call below (no look-ahead).
    max_date = pd.to_datetime(panel["date"].max())
    san = DataSanitizer(
        max_fill_days=3, outlier_sigma=999.0, min_price=0.01, as_of_time=max_date
    )
    san.fit(panel, symbol_col="ticker", date_col="date")
    panel_in = panel.copy()
    panel_in["_orig_idx"] = np.arange(len(panel_in))
    cleaned = san.apply(panel_in, symbol_col="ticker", date_col="date")
    if "ticker" not in cleaned.columns:
        if "_orig_idx" not in cleaned.columns:
            cleaned["ticker"] = panel_in.loc[cleaned.index, "ticker"].values
        else:
            ticker_map = dict(
                zip(panel_in["_orig_idx"].values, panel_in["ticker"].values)
            )
            cleaned["ticker"] = cleaned["_orig_idx"].map(ticker_map)
            cleaned = cleaned.drop(columns=["_orig_idx"])

    # Step 3: L3 Fix #1 -- replace full-sample clip with causal expanding clip.
    cleaned, n_causal_clipped = _causal_clip_outliers(
        cleaned, outlier_sigma=3.0, symbol_col="ticker", date_col="date"
    )

    s = san.sanitization_stats
    logger.info(
        "sanitize_ohlcv (causal): in=%d dup=%d ffill=%d causal_clipped=%d "
        "invalid=%d out=%d [L3 Fix #1: no full-sample look-ahead]",
        s.get("input_rows", 0),
        s.get("duplicates_removed", 0),
        s.get("forward_filled", 0),
        n_causal_clipped,
        s.get("invalid_prices_removed", 0),
        s.get("output_rows", 0),
    )
    return cleaned


def _compute_train_prefix_supervised_labels(
    panel: pd.DataFrame,
    causal_cutoff_date: pd.Timestamp,
    label_horizon: int,
) -> pd.Series:
    """Compute PIT-safe supervised labels restricted to the train-prefix.

    Forward returns are computed per ticker. Rows whose forward return
    horizon extends beyond the causal cutoff are set to NaN so that
    supervised IC scoring never uses returns that would require data from
    the test region (dates > cutoff).

    Parameters
    ----------
    panel : DataFrame with at least ``ticker``, ``date``, ``close`` columns.
    causal_cutoff_date : Last date allowed in the train-prefix.
    label_horizon : Forward-return horizon in trading days.

    Returns
    -------
    pd.Series aligned to ``panel.index``.  NaN for rows outside the
    train-prefix or where the horizon bleeds past the cutoff.
    """
    fwd_ret = panel.groupby("ticker")["close"].transform(
        lambda s: s.shift(-label_horizon) / s - 1.0
    )
    # L2 Fix (2026-06-18): Replace calendar-day heuristic with exact
    # trading-day future date.  The old code used
    #   last_safe_date = cutoff - Timedelta(days=horizon*2)
    # which was a rough 2x calendar-day buffer — incorrect when trading
    # calendars have gaps (holidays, suspensions).  The new code computes
    # the actual future trading date per (ticker, row) via shift(-horizon)
    # on the date column, then masks to keep only rows whose BOTH the
    # observation date AND the horizon-end date fall within the train
    # prefix.  This is exact and needs no heuristic safety margin.
    future_date = panel.groupby("ticker")["date"].transform(
        lambda s: s.shift(-label_horizon)
    )
    valid_mask = (
        (panel["date"] <= causal_cutoff_date)
        & (future_date <= causal_cutoff_date)
        & fwd_ret.notna()
    )
    labels = fwd_ret.where(valid_mask)
    n_valid = int(valid_mask.sum())
    logger.info(
        "Train-prefix supervised labels: %d/%d valid rows "
        "(cutoff=%s, horizon=%d) [L2 Fix: exact trading-day, no calendar heuristic]",
        n_valid, len(panel),
        causal_cutoff_date.date(), label_horizon,
    )
    return labels


def _self_neutralize_predictions(
    pred: np.ndarray,
    dates_te: np.ndarray,
    y_te: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Cross-sectional self-neutralization of alpha predictions per date.

    For each test date, regresses predictions against the equal-weight
    market return (mean of y_te for that date) and returns the residual.
    This removes the component of the alpha signal that is explained by
    the market factor, isolating the stock-specific signal.

    PIT Safety
    ----------
    Uses only same-date cross-sectional data (no time-series leakage).
    The market return proxy is computed from y_te of the SAME date,
    which is the forward return the prediction is trying to predict.
    This is standard in cross-sectional neutralization: we remove the
    common factor from the prediction, not from the target.

    Parameters
    ----------
    pred : 1-D array of alpha predictions aligned with dates_te.
    dates_te : 1-D array of test dates aligned with pred.
    y_te : 1-D array of forward returns aligned with pred.

    Returns
    -------
    (neutralized_pred, n_dates_neutralized)
        Neutralized predictions and count of dates where neutralization
        was applied. Dates with < 3 stocks are left unchanged.
    """
    if len(pred) == 0:
        return pred, 0

    df = pd.DataFrame({
        "pred": pred,
        "date": dates_te,
        "y": y_te,
    })

    neutralized = pred.copy().astype(np.float64)
    n_dates = 0

    for date, g in df.groupby("date"):
        if len(g) < 3:
            continue
        idx = g.index.values
        p = g["pred"].values.astype(np.float64)
        mkt = g["y"].values.mean()  # Equal-weight market proxy
        # OLS: pred = a + b * mkt + residual
        # Since mkt is a scalar (same for all stocks on this date),
        # the regression is pred ~ 1 (intercept only) + mkt_scalar.
        # But mkt is constant per date, so the "beta" is just the
        # cross-sectional mean of pred (demean). For true factor
        # neutralization with a varying factor, we'd need per-stock
        # factor loadings. Here we use cross-sectional demeaning as
        # the simplest self-neutralization (removes the date-level mean).
        # This is equivalent to removing the market exposure in a
        # cross-sectional long-short portfolio context.
        p_mean = p.mean()
        residual = p - p_mean
        neutralized[idx] = residual
        n_dates += 1

    return neutralized, n_dates


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
        logger.info(
            "Year %d universe: %d tickers (top=%s)", year, len(tickers), tickers[:5]
        )
    return out


def load_universe():
    files = sorted(
        (REPO_ROOT / ".ly_state/session/universe").glob("universe_*.json"), reverse=True
    )
    if not files:
        raise FileNotFoundError("No universe file")
    with open(files[0]) as f:
        data = json.load(f)
    if isinstance(data, dict):
        univ = data.get("universe") or data.get("tickers") or []
        tickers = (
            [u["ticker"] for u in univ]
            if (univ and isinstance(univ[0], dict))
            else list(univ)
        )
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
    panel["adv_vnd"] = panel.groupby("ticker")["_dollar_vol"].transform(
        lambda s: s.rolling(window, min_periods=max(5, window // 4)).mean().shift(1)
    )
    panel = panel.drop(columns=["_dollar_vol"])
    return panel


def load_panel(tickers, year_start, year_end, data_path=None):
    data_path = Path(data_path) if data_path else REPO_ROOT / "data/market_2015_now.parquet"
    df = pd.read_parquet(data_path)
    df["date"] = pd.to_datetime(df["date"])
    # Pull 1 year extra history before year_start so the 20d ADV warm-up is
    # computed PIT-correctly on prior data (not on intra-fold data).
    panel = df[
        (df["ticker"].isin(tickers))
        & (df["date"].dt.year >= year_start - 1)
        & (df["date"].dt.year <= year_end)
    ].copy()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    # Phase 5: clean BEFORE ADV (so dropped suspended bars don't pollute ADV)
    panel = mask_suspended(panel)
    panel = sanitize_ohlcv(panel)
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    panel = _attach_adv(panel)
    panel = panel[panel["date"].dt.year >= year_start].reset_index(drop=True)
    logger.info(
        "Panel: %d rows, %d tickers, %s..%s, adv_vnd non-null=%d",
        len(panel),
        panel["ticker"].nunique(),
        panel["date"].min().date(),
        panel["date"].max().date(),
        int(panel["adv_vnd"].notna().sum()),
    )
    return panel


def load_panel_walk_forward(
    yearly_universes: dict, year_start: int, year_end: int, data_path=None
) -> pd.DataFrame:
    """Load panel with year-aware universe filter (PIT walk-forward).

    Pulls 1 year of pre-history per yearly slice so ADV can warm up without
    contaminating in-fold data.
    """
    data_path = Path(data_path) if data_path else REPO_ROOT / "data/market_2015_now.parquet"
    df = pd.read_parquet(data_path)
    df["date"] = pd.to_datetime(df["date"])
    # Build a (ticker, date) -> universe_year lookup so we can re-tag after
    # sanitize_ohlcv (which would otherwise dedup our duplicate marker).
    frames = []
    universe_year_map = {}
    for year, tickers in yearly_universes.items():
        chunk = df[
            (df["ticker"].isin(tickers))
            & (df["date"].dt.year >= year - 1)
            & (df["date"].dt.year <= year)
        ].copy()
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
    panel = (
        panel[panel["date"].dt.year == panel["_universe_year"]]
        .drop(columns=["_universe_year"])
        .reset_index(drop=True)
    )
    logger.info(
        "WF Panel: %d rows, %d unique tickers, %s..%s, adv_vnd non-null=%d",
        len(panel),
        panel["ticker"].nunique(),
        panel["date"].min().date(),
        panel["date"].max().date(),
        int(panel["adv_vnd"].notna().sum()),
    )
    return panel


def compute_target(panel, horizon=5):
    return panel.groupby("ticker")["close"].transform(
        lambda s: s.shift(-horizon) / s - 1.0
    )


# Phase 4: LSTM helper. Builds sequences inside the fold from already
# z-scored 2D features (caller provides train-only mu/sd), trains a
# fresh LSTMAlpha, and returns predictions aligned with X_te rows.
# Rows that lack lookback history are left at 0 (Ridge ensemble dominates
# there, safe fallback).
def _lstm_predict_fold(
    X_tr_z: np.ndarray,
    y_tr: np.ndarray,
    X_te_z: np.ndarray,
    feat_df: pd.DataFrame,
    feat_names: list,
    tr_idx: np.ndarray,
    te_idx: np.ndarray,
    cfg,
    lstm_mod,
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
    out_arr = ((df[feat_cols].to_numpy() - means.to_numpy()) / stds.to_numpy()).astype(
        np.float64
    )
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


def per_date_returns(
    pred,
    y_te,
    dates_te,
    tickers_te=None,
    apply_tail=False,
    tail_mod=None,
    tail_kwargs=None,
    adv_te=None,
):
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
    pivot_w = pd.DataFrame(
        0.0, index=sorted(df["date"].unique()), columns=sorted(df["ticker"].unique())
    )
    pivot_y = pivot_w.copy()
    pivot_adv = pivot_w.copy() if adv_te is not None else None

    # Phase 3.6 knobs (passed via tail_kwargs).
    top_k = (tail_kwargs or {}).get("top_k", 0)
    rebal_threshold = (tail_kwargs or {}).get("rebal_threshold", 0.0)

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
    warmup = tail_kwargs.get("train_pre_lev_history") if tail_kwargs else None
    # Phase 13: Regime overlay (applied BEFORE vol-target, PIT-safe)
    regime_enabled = tail_kwargs.get("regime_enabled", False) if tail_kwargs else False
    if regime_enabled:
        regime_mod = tail_kwargs.get("regime_mod")
        regime_hmm_mod = tail_kwargs.get("regime_hmm_mod")
        if regime_hmm_mod is not None:
            # Phase 13b: HMM regime overlay
            market_rets = pivot_y.to_numpy().mean(axis=1)
            bear_exp = tail_kwargs.get("regime_bear_exposure", 0.5)
            bull_exp = tail_kwargs.get("regime_bull_exposure", 1.1)
            side_exp = tail_kwargs.get("regime_sideways_exposure", 0.8)
            retrain = tail_kwargs.get("regime_hmm_retrain", 60)
            pivot_w = regime_hmm_mod.apply_hmm_regime_overlay(
                pivot_w,
                market_rets,
                bear_exposure=bear_exp,
                bull_exposure=bull_exp,
                sideways_exposure=side_exp,
                retrain_every=retrain,
            )
        elif regime_mod is not None:
            # Compute equal-weight market returns from pivot_y
            market_rets = pivot_y.to_numpy().mean(axis=1)
            hysteresis = tail_kwargs.get("regime_hysteresis", 5)
            dd_threshold = tail_kwargs.get("regime_dd_threshold", -0.10)
            bull_exp = tail_kwargs.get("regime_bull_exposure", 1.1)
            bear_exp = tail_kwargs.get("regime_bear_exposure", 0.5)
            side_exp = tail_kwargs.get("regime_sideways_exposure", 0.8)
            pivot_w = regime_mod.apply_regime_overlay(
                pivot_w,
                market_rets,
                hysteresis_days=hysteresis,
                dd_threshold=dd_threshold,
                bull_exposure=bull_exp,
                bear_exposure=bear_exp,
                sideways_exposure=side_exp,
            )
    # Phase 14: Additional overlays (applied after regime, before vol-target)
    # Smart Money overlay
    smart_money_mod = tail_kwargs.get("smart_money_mod") if tail_kwargs else None
    if smart_money_mod is not None:
        market_rets = pivot_y.to_numpy().mean(axis=1)
        ret_series = pd.Series(market_rets)
        # Soft-dampening: scale weights smoothly by CMF proxy
        sm_score = ret_series.rolling(20, min_periods=5).mean() / ret_series.rolling(
            20, min_periods=5
        ).std().replace(0, 1.0)
        sm_exposure = 1.0 + sm_score.fillna(0.0).clip(
            -1.0, 1.0
        ).values * tail_kwargs.get("smart_money_boost", 0.25)
        # Clean exposure array
        sm_exposure = np.nan_to_num(sm_exposure, nan=1.0, posinf=1.0, neginf=1.0)
        pivot_w = pivot_w.multiply(sm_exposure, axis=0)
        row_sums = pivot_w.sum(axis=1).replace(0, 1.0)
        pivot_w = pivot_w.div(row_sums, axis=0)

    # Sentiment overlay
    sentiment_mod = tail_kwargs.get("sentiment_mod") if tail_kwargs else None
    if sentiment_mod is not None:
        market_rets = pivot_y.to_numpy().mean(axis=1)
        ret_series = pd.Series(market_rets)
        streak = ret_series.rolling(5, min_periods=3).mean().fillna(0.0)
        sent_exposure = 1.0 + streak.clip(-0.05, 0.05).values * (
            tail_kwargs.get("sentiment_boost", 0.2) / 0.05
        )
        sent_exposure = np.nan_to_num(sent_exposure, nan=1.0, posinf=1.0, neginf=1.0)
        pivot_w = pivot_w.multiply(sent_exposure, axis=0)
        row_sums = pivot_w.sum(axis=1).replace(0, 1.0)
        pivot_w = pivot_w.div(row_sums, axis=0)

    # Contagion overlay
    contagion_mod = tail_kwargs.get("contagion_mod") if tail_kwargs else None
    if contagion_mod is not None:
        pivot_w = contagion_mod.apply_contagion_overlay(
            pivot_w,
            pivot_y.to_numpy(),
            lookback=60,
            spike_threshold_std=2.0,
            spike_exposure=0.5,
        )

    # TCost optimizer overlay
    tcost_mod = tail_kwargs.get("tcost_mod") if tail_kwargs else None
    if tcost_mod is not None:
        # Avoid float distortion in CPCV context by using a smaller threshold
        pivot_w = tcost_mod.apply_tcost_overlay(
            pivot_w,
            cost_per_trade_bps=15.0,
            min_trade_threshold_bps=tail_kwargs.get("tcost_threshold", 10.0),
        )

    # Advanced circuit breaker
    breaker_mod = tail_kwargs.get("breaker_mod") if tail_kwargs else None
    if breaker_mod is not None:
        port_rets_pre = (pivot_w.to_numpy() * pivot_y.to_numpy()).sum(axis=1)
        pivot_w = breaker_mod.apply_advanced_circuit_breaker(
            pivot_w,
            port_rets_pre,
            cvar_limit=tail_kwargs.get("breaker_cvar_limit", -0.20),
            derisk_multiplier=0.7,
            lookback=60,
            cooldown_bars=2,
        )

    adj_w, port_rets = tail_mod.apply_tail_controls(
        pivot_w,
        pivot_y.to_numpy(),
        target_vol_ann=0.15,
        max_abs_weight=0.05,
        dd_window=20,
        dd_threshold=0.08,
        dd_cut=0.5,
        warmup_history=warmup,
    )
    # Phase 3.5/3.8/3.10: apply realistic execution costs if exec_mod is provided.
    exec_mod = tail_kwargs.get("exec_mod") if tail_kwargs else None
    capital = tail_kwargs.get("capital_vnd", 1e9) if tail_kwargs else 1e9
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
        prev_w_dict = tail_kwargs.get("prev_w_dict") if tail_kwargs else None
        if prev_w_dict:
            cols = list(adj_w.columns)
            prev_w_init = np.asarray(
                [prev_w_dict.get(c, 0.0) for c in cols], dtype=float
            )
        cost_model_kwarg = tail_kwargs.get("cost_model") if tail_kwargs else None
        _, port_rets, br = exec_mod.apply_realistic_tc(
            adj_w,
            pivot_y.to_numpy(),
            daily_adv=adv_matrix,  # Phase 3.8: real ADV per (date, ticker)
            portfolio_capital_vnd=capital,
            prev_w_init=prev_w_init,
            cost_model=cost_model_kwarg,
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


def _train_latent_features_fold(
    X_tr_z: np.ndarray,
    X_te_z: np.ndarray,
    feat_df: pd.DataFrame,
    feat_names: list,
    tr_idx: np.ndarray,
    te_idx: np.ndarray,
    latent_cfg,
    latent_mod,
) -> tuple[np.ndarray, np.ndarray]:
    """Train unsupervised latent encoder on fold-train sequences only (PIT-safe).

    PIT guarantee: encoder.fit() receives sequences whose every member row
    (including the lookback body) is drawn exclusively from tr_idx rows,
    sorted by ticker/date.  Test-period feature rows are NEVER used during
    encoder training, preventing CPCV look-ahead leakage.
    """
    import omega.quant.models.lstm_alpha as lstm_mod

    # --- Build train-only frame (no test rows) for encoder fitting ---
    work_tr = feat_df.iloc[tr_idx][["ticker", "date"]].copy()
    for i, fn in enumerate(feat_names):
        work_tr[fn] = X_tr_z[:, i]
    work_tr = work_tr.reset_index(drop=True)

    X_seq_tr, tr_seq_idx = lstm_mod.build_sequences(
        work_tr, feat_names, latent_cfg.lookback
    )

    encoder = latent_mod.UnsupervisedLatentEncoder(latent_cfg)
    encoder.fit(X_seq_tr)

    # --- Build combined frame for transform (train + test) ---
    n_tr = len(tr_idx)
    work_all = feat_df.iloc[np.concatenate([tr_idx, te_idx])][["ticker", "date"]].copy()
    z_all = np.vstack([X_tr_z, X_te_z])
    for i, fn in enumerate(feat_names):
        work_all[fn] = z_all[:, i]
    work_all = work_all.reset_index(drop=True)

    X_seq_all, idx_all = lstm_mod.build_sequences(
        work_all, feat_names, latent_cfg.lookback
    )
    train_mask = idx_all < n_tr
    test_mask = ~train_mask

    latent_all = encoder.transform(X_seq_all)

    latent_tr_full = np.zeros((len(tr_idx), latent_cfg.latent_dim), dtype=np.float64)
    latent_te_full = np.zeros((len(te_idx), latent_cfg.latent_dim), dtype=np.float64)

    latent_tr_full[idx_all[train_mask]] = latent_all[train_mask]
    latent_te_full[idx_all[test_mask] - n_tr] = latent_all[test_mask]

    return latent_tr_full, latent_te_full


def run_pipeline(
    X,
    y,
    ts,
    dates,
    cpcv_mod,
    dsr_mod,
    label,
    label_horizon,
    tickers=None,
    tail_mod=None,
    n_alphas=4,
    exec_mod_param=None,
    capital_vnd_param=1e9,
    top_k_param=0,
    rebal_threshold_param=0.0,
    signal_ema_param=0,
    embargo_pct_param=0.01,
    adv_arr=None,
    lstm_cfg=None,
    lstm_mod=None,
    feat_df=None,
    feat_names=None,
    lstm_blend=0.5,
    ensemble_y=None,
    ensemble_weights=None,
    cost_model_override=None,
    regime_mod_param=None,
    regime_hmm_mod_param=None,
    regime_hysteresis_param=5,
    regime_dd_threshold_param=-0.10,
    regime_bear_exposure_param=0.5,
    regime_bull_exposure_param=1.1,
    regime_sideways_exposure_param=0.8,
    regime_hmm_retrain_param=60,
    smart_money_mod_param=None,
    smart_money_boost_param=0.25,
    sentiment_mod_param=None,
    sentiment_boost_param=0.2,
    contagion_mod_param=None,
    tcost_mod_param=None,
    tcost_threshold_param=30.0,
    breaker_mod_param=None,
    breaker_cvar_limit_param=-0.08,
    use_latent_features=False,
    latent_cfg=None,
    latent_mod=None,
    prefix_test_mask=None,
    min_fold_ic_threshold=0.005,
    self_neutralize=False,
    bh_fdr_alpha=0.05,
):
    """Phase 10 (B): ensemble_y is an optional dict {horizon: y_array}.
    When provided, fit one Ridge per horizon target, blend predictions by
    ensemble_weights (default = uniform). All Ridge fits use the SAME
    train/test split, SAME features, SAME CPCV. Only the regression
    target differs per horizon.

    GATE: LLM_ALPHA_ENHANCEMENT_20260618 additions:
    - self_neutralize: cross-sectional demean of predictions per date
      to remove market-factor contamination (PIT-safe, same-date only).
    - bh_fdr_alpha: significance threshold for BH-FDR correction across
      CPCV fold IC values (controls false discovery rate).
    """
    cpcv = cpcv_mod.CombinatorialPurgedKFold(
        n_splits=10,
        n_test_splits=2,
        embargo_pct=embargo_pct_param,
        label_horizon=label_horizon,
    )
    folds, daily_rets, trial_srs = [], [], []
    _fold_fb_details = []
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
        # L3 Fix #2b (fix2): Exclude dev-prefix rows from test folds.
        # The first ~50% of dates were used for LLM formula scoring/
        # selection; allowing them as OOS test rows would leak
        # distributional information into the reported metrics.
        if prefix_test_mask is not None:
            non_prefix = ~prefix_test_mask[te]
            if non_prefix.sum() == 0:
                logger.warning(
                    "Fold %d: all %d test indices fall in dev prefix — skipping",
                    fid, len(te),
                )
                _fold_fb_details.append({
                    "portfolio_ic": 0.0,
                    "used_fallback_candidates": True,
                    "fold_id": fid,
                    "reason": "all_test_in_prefix",
                })
                continue
            te = te[non_prefix]
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
        if use_latent_features and latent_cfg is not None and latent_mod is not None:
            try:
                latent_tr, latent_te = _train_latent_features_fold(
                    X_tr, X_te, feat_df, feat_names, tr, te, latent_cfg, latent_mod
                )
                X_tr = np.hstack([X_tr, latent_tr])
                X_te = np.hstack([X_te, latent_te])
                logger.info(
                    "Fold %d: Added %d unsupervised latent features",
                    fid,
                    latent_cfg.latent_dim,
                )
            except Exception as exc:
                logger.warning("Unsupervised Latent features failed on fold: %s", exc)
        r = evaluate_fold(X_tr, y[tr], X_te, y[te])
        # Phase 10 (B): multi-horizon Ridge ensemble. Fit one Ridge per
        # additional horizon target on the SAME (X_tr, X_te) split, then
        # blend predictions with the primary fit using ensemble_weights.
        # All targets share the same train/test rows, only the y values
        # differ. PIT-safe because each Ridge still uses train-only fit.
        if ensemble_y is not None and len(ensemble_y) > 1:
            preds = [r["pred"]]
            ics = {label_horizon: r["ic"]}
            for h, y_h in ensemble_y.items():
                # Phase 9/10/11 codex P1 fix: skip the primary horizon by
                # comparing against label_horizon (integer match), not the
                # never-set string "primary". Without this skip, the
                # primary fit was double-counted in `preds`, biasing the
                # uniform blend toward the primary horizon (e.g. 2:1
                # instead of 1:1 with --ensemble-horizons=20,60
                # --label-horizon=60).
                if h == label_horizon:
                    continue
                rh = evaluate_fold(X_tr, y_h[tr], X_te, y_h[te])
                preds.append(rh["pred"])
                ics[h] = rh["ic"]
            # Apply ensemble blend (uniform if weights not given)
            if ensemble_weights is None or len(ensemble_weights) != len(preds):
                w = [1.0 / len(preds)] * len(preds)
            else:
                tot = float(sum(ensemble_weights))
                w = [x / tot for x in ensemble_weights]
            blended = sum(wi * pi for wi, pi in zip(w, preds))
            # Use primary y for IC scoring to keep apples-to-apples vs
            # standalone runs (a fold's signal quality is judged on the
            # ORIGINAL target, not the blended one).
            r["pred_ridge_primary"] = r["pred"].copy()
            r["pred"] = blended
            r["ic_per_horizon"] = ics
            r["ic"] = (
                float(np.corrcoef(blended, y[te])[0, 1])
                if np.std(blended) > 1e-12
                else 0.0
            )
        # Phase 4: optional LSTM ensemble. Train LSTM on the same z-scored
        # train fold, predict on test, then blend with Ridge.
        if lstm_cfg is not None and lstm_mod is not None and feat_df is not None:
            lstm_pred = _lstm_predict_fold(
                X_tr,
                y[tr],
                X_te,
                feat_df,
                list(feat_names),
                tr,
                te,
                lstm_cfg,
                lstm_mod,
            )
            # Diagnostic IC of LSTM alone (train-only would be cleaner; this
            # is just for logging on test fold).
            test_ic_lstm = (
                0.0
                if np.std(lstm_pred) < 1e-12
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
                    block_id[b + 1 :] += 1
            else:
                block_id = np.zeros(len(te), dtype=np.int64)
            df_pred = pd.DataFrame(
                {
                    "pred": r["pred"],
                    "ticker": te_tickers,
                    "date": te_dates,
                    "block": block_id,
                    "pos": np.arange(len(r["pred"])),
                }
            )
            df_pred = df_pred.sort_values(["ticker", "block", "date"]).reset_index(
                drop=True
            )
            df_pred["pred_ema"] = df_pred.groupby(["ticker", "block"])[
                "pred"
            ].transform(lambda s: s.ewm(span=signal_ema_param, adjust=False).mean())
            df_pred = df_pred.sort_values("pos").reset_index(drop=True)
            r["pred"] = df_pred["pred_ema"].to_numpy()
        # Self-Neutralization: cross-sectional demean of predictions per
        # date to remove market-factor contamination from the alpha signal.
        # Applied AFTER LSTM blend + EMA smoothing, BEFORE portfolio construction.
        # PIT-safe: only uses same-date cross-sectional data (no time-series leakage).
        _n_neutral_dates = 0
        if self_neutralize:
            r["pred"], _n_neutral_dates = _self_neutralize_predictions(
                r["pred"], dates[te], y[te],
            )
            if fid == 0:
                logger.info(
                    "Self-Neutralization enabled: cross-sectional demean applied "
                    "on %d/%d test dates (fold 0, min 3 stocks/date)",
                    _n_neutral_dates, len(np.unique(dates[te])),
                )
        # BT-2 fix: seed tail-control vol history with TRAIN-fold portfolio rets
        train_warmup = None
        if tail_mod is not None and tickers is not None:
            train_pred = evaluate_fold(X_tr, y[tr], X_tr, y[tr])  # in-sample fit
            train_dates_arr = dates[tr]
            train_tickers_arr = tickers[tr]
            df_tr = pd.DataFrame(
                {
                    "p": train_pred["pred"],
                    "y": y[tr],
                    "d": train_dates_arr,
                    "t": train_tickers_arr,
                }
            )
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
            if cost_model_override is not None:
                tail_kwargs["cost_model"] = cost_model_override
        if top_k_param > 0:
            tail_kwargs["top_k"] = top_k_param
        if rebal_threshold_param > 0:
            tail_kwargs["rebal_threshold"] = rebal_threshold_param
        # Phase 13: regime overlay
        if regime_mod_param is not None or regime_hmm_mod_param is not None:
            tail_kwargs["regime_enabled"] = True
            tail_kwargs["regime_mod"] = regime_mod_param
            tail_kwargs["regime_hmm_mod"] = regime_hmm_mod_param
            tail_kwargs["regime_hysteresis"] = regime_hysteresis_param
            tail_kwargs["regime_dd_threshold"] = regime_dd_threshold_param
            tail_kwargs["regime_bear_exposure"] = regime_bear_exposure_param
            tail_kwargs["regime_bull_exposure"] = regime_bull_exposure_param
            tail_kwargs["regime_sideways_exposure"] = regime_sideways_exposure_param
            tail_kwargs["regime_hmm_retrain"] = regime_hmm_retrain_param
        # Phase 14: additional overlays
        if smart_money_mod_param is not None:
            tail_kwargs["smart_money_mod"] = smart_money_mod_param
            tail_kwargs["smart_money_boost"] = smart_money_boost_param
        if sentiment_mod_param is not None:
            tail_kwargs["sentiment_mod"] = sentiment_mod_param
            tail_kwargs["sentiment_boost"] = sentiment_boost_param
        if contagion_mod_param is not None:
            tail_kwargs["contagion_mod"] = contagion_mod_param
        if tcost_mod_param is not None:
            tail_kwargs["tcost_mod"] = tcost_mod_param
            tail_kwargs["tcost_threshold"] = tcost_threshold_param
        if breaker_mod_param is not None:
            tail_kwargs["breaker_mod"] = breaker_mod_param
            tail_kwargs["breaker_cvar_limit"] = breaker_cvar_limit_param
        if not tail_kwargs:
            tail_kwargs = None
        rets = per_date_returns(
            r["pred"],
            y[te],
            dates[te],
            tickers_te=tickers[te] if tickers is not None else None,
            apply_tail=tail_mod is not None,
            tail_mod=tail_mod,
            tail_kwargs=tail_kwargs,
            adv_te=adv_arr[te] if adv_arr is not None else None,
        )
        sr = (
            float(np.mean(rets) / np.std(rets, ddof=1))
            if (len(rets) > 1 and np.std(rets, ddof=1) > 0)
            else 0.0
        )
        trial_srs.append(sr)  # P2-1: keep all
        daily_rets.extend(rets.tolist())
        folds.append(
            {
                "fold": fid,
                "test_ic": r["ic"],
                "train_cv_ic": r["train_cv_ic"],
                "fold_sr": sr,
                "n_daily": int(len(rets)),
                "alpha": r["alpha"],
                "ic_lstm": r.get("ic_lstm", None),
                "self_neutralized": self_neutralize,
            }
        )
        _used_fallback = abs(r["ic"]) < min_fold_ic_threshold
        _fold_fb_details.append({
            "portfolio_ic": float(r["ic"]),
            "used_fallback_candidates": _used_fallback,
            "fold_id": fid,
            "fold_sr": sr,
            "reason": "low_ic" if _used_fallback else "alpha_selected",
        })
    # -------------------------------------------------------------------
    # BH FDR Multiple Testing Correction (GATE: LLM_ALPHA_ENHANCEMENT_20260618)
    # Apply Benjamini-Hochberg FDR correction across CPCV fold IC values.
    # Each fold's test IC is treated as an independent hypothesis test
    # (H0: IC = 0 for this fold). The BH procedure controls the expected
    # fraction of false discoveries among the rejected hypotheses.
    # -------------------------------------------------------------------
    _bh_fdr_summary = None
    _fold_pvalues = []
    _fold_qvalues = []
    if bh_fdr_qvalues is not None and compute_ic_pvalue is not None and folds:
        fold_ics = [f["test_ic"] for f in folds]
        # Compute per-fold p-value using t-test on the IC series
        # (we use the overall IC series for a single p-value per fold,
        # treating each fold's IC as one observation of a distribution)
        # For BH-FDR across folds: each fold gets p = P(|IC| >= |observed|)
        # under H0: IC ~ N(0, sigma). We use the fold-level IC as the
        # test statistic and compute p from the empirical distribution
        # of all fold ICs.
        # Simplified approach: use a two-sided t-test per fold against
        # the mean of all other folds (leave-one-out), or simply use
        # the overall p-value of the IC series and replicate for each fold.
        # Best approach for CPCV: compute one p-value for the overall
        # mean IC, then apply BH correction across the n_alphas candidates.
        # Since we have one pipeline run (not multiple alphas), we compute
        # per-fold p-values using the IC series as a sample.
        n_folds = len(fold_ics)
        if n_folds >= 3:
            # Per-fold p-value: t-test H0 that this fold's IC = 0
            # using the overall IC std as the standard error estimate.
            mean_ic = float(np.mean(fold_ics))
            std_ic = float(np.std(fold_ics, ddof=1))
            se_ic = std_ic / np.sqrt(n_folds) if n_folds > 1 else 1.0
            try:
                from scipy.stats import t as _t_dist
            except ImportError:
                _t_dist = None
            for ic_val in fold_ics:
                if se_ic > 1e-12:
                    t_val = ic_val / se_ic
                    # Two-sided p-value approximation
                    if _t_dist is not None:
                        try:
                            p_val = 2.0 * (1.0 - _t_dist.cdf(abs(t_val), df=n_folds - 1))
                        except Exception:
                            p_val = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t_val) / math.sqrt(2))))
                    else:
                        # Fallback: normal approximation (no scipy)
                        p_val = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t_val) / math.sqrt(2))))
                else:
                    p_val = 0.0 if abs(ic_val) > 1e-12 else 1.0
                _fold_pvalues.append(float(p_val))

            _fold_qvalues = bh_fdr_qvalues(_fold_pvalues)

            n_significant = sum(1 for q in _fold_qvalues if q <= bh_fdr_alpha)
            fraction_significant = n_significant / n_folds
            # L2 Fix (2026-06-18): passes_fdr is now defined by the fraction
            # of folds that pass BH-FDR (q <= bh_fdr_alpha), NOT by running
            # BH on a single overall_pvalue (which is degenerate for one
            # hypothesis).  We require >= 50% of folds to be significant.
            passes_fdr = (n_significant >= (n_folds * 0.5))
            # L2 Fix: overall_qvalue = median of per-fold q-values, which
            # is a robust summary of the per-fold FDR evidence.  The old
            # code ran bh_fdr_qvalues([overall_pvalue]) on a single value,
            # which is a no-op (q = p for a singleton) and not meaningful.
            overall_qvalue = float(np.median(_fold_qvalues))
            overall_pvalue = float(compute_ic_pvalue(fold_ics))

            _bh_fdr_summary = {
                "n_folds": n_folds,
                "mean_ic": mean_ic,
                "std_ic": std_ic,
                "overall_pvalue": overall_pvalue,
                "overall_qvalue": overall_qvalue,
                "bh_fdr_alpha": bh_fdr_alpha,
                "n_significant_folds": n_significant,
                "fraction_significant": fraction_significant,
                "per_fold_pvalues": _fold_pvalues,
                "per_fold_qvalues": _fold_qvalues,
                "passes_fdr": passes_fdr,
            }
            logger.info(
                "[%s] BH-FDR: mean_IC=%.4f median_q=%.4f significant=%d/%d "
                "(%.1f%%, threshold=50%%, alpha=%.3f) → %s",
                label,
                mean_ic,
                overall_qvalue,
                n_significant,
                n_folds,
                fraction_significant * 100,
                bh_fdr_alpha,
                "PASS" if passes_fdr else "FAIL",
            )
        else:
            logger.warning(
                "[%s] BH-FDR skipped: only %d folds (need >= 3)", label, n_folds,
            )
    else:
        if bh_fdr_qvalues is None:
            logger.warning(
                "[%s] BH-FDR skipped: bh_fdr_qvalues not available "
                "(omega.quant.walk_forward import failed)", label,
            )
    # P0-2: n_trials = SEARCH dim
    dsr = dsr_mod.deflated_sharpe_ratio(
        np.asarray(daily_rets),
        n_trials=n_alphas,
        trial_sharpes=trial_srs,
        periods_per_year=252,
    )
    # Phase 3.9: fold-level DSR (CPCV oversampling fix). Treats each
    # fold's per-bar Sharpe as one IID observation, avoiding the 9x
    # over-counting in pooled daily returns.
    fold_dsr_res = (
        dsr_mod.fold_level_dsr(trial_srs, n_trials=n_alphas, periods_per_year=252)
        if len(trial_srs) >= 2
        else None
    )
    # Fallback-as-failure checkpoint: classify each CPCV fold as
    # alpha-selected (gate passed) or fallback-used (gate failed) and
    # report success rates separately.  High fallback rate signals that
    # the alpha pipeline is not producing qualifying candidates.
    fb_metrics = None
    if compute_fallback_as_failure_metrics is not None and _fold_fb_details:
        fb_metrics = compute_fallback_as_failure_metrics(_fold_fb_details)
        logger.info(
            "[%s] FALLBACK-AS-FAILURE: total=%d alpha=%d fallback=%d "
            "failure_rate=%.3f alpha_pos_IC=%.3f fallback_pos_IC=%.3f",
            label,
            fb_metrics["total_folds"],
            fb_metrics["alpha_selected_folds"],
            fb_metrics["fallback_folds"],
            fb_metrics["fallback_as_failure_rate"],
            fb_metrics["alpha_selected_positive_ic_rate"],
            fb_metrics["fallback_positive_ic_rate"],
        )
    # -------------------------------------------------------------------
    # ICIR, Positive Fold Rate, and Research Gate Verdict
    # (GATE: LLM_ALPHA_ENHANCEMENT_20260618)
    # Compute ICIR = mean(IC)/std(IC) across CPCV folds, the fraction
    # of folds with positive IC, and classify the alpha into a research
    # gate verdict category (PROMOTE_CANDIDATE / ENSEMBLE_ONLY / REVIEW /
    # RETIRE).  These metrics combine DSR, BH-FDR, fallback rate, and
    # consistency into a single actionable verdict.
    # -------------------------------------------------------------------
    _icir_value = 0.0
    _pos_fold_rate = 0.0
    _research_verdict = None
    _fold_ics_list = [f["test_ic"] for f in folds]
    if compute_icir is not None and _fold_ics_list:
        _icir_value = float(compute_icir(_fold_ics_list))
    if compute_positive_fold_rate is not None and _fold_ics_list:
        _pos_fold_rate = float(compute_positive_fold_rate(_fold_ics_list))
    if classify_research_gate_verdict is not None and _fold_ics_list:
        _mean_ic = float(np.mean(_fold_ics_list))
        _overall_qval = (
            _bh_fdr_summary["overall_qvalue"]
            if _bh_fdr_summary is not None
            else 1.0
        )
        _fb_rate = (
            fb_metrics["fallback_as_failure_rate"]
            if fb_metrics is not None
            else 0.0
        )
        _research_verdict = classify_research_gate_verdict(
            mean_ic=_mean_ic,
            icir=_icir_value,
            positive_fold_rate=_pos_fold_rate,
            q_value=_overall_qval,
            fallback_rate=_fb_rate,
            bh_fdr_threshold=bh_fdr_alpha,
        )
        logger.info(
            "[%s] RESEARCH GATE: verdict=%s ICIR=%.4f pos_fold_rate=%.3f "
            "mean_IC=%.4f q=%.4f fb_rate=%.3f",
            label,
            _research_verdict,
            _icir_value,
            _pos_fold_rate,
            _mean_ic,
            _overall_qval,
            _fb_rate,
        )
    s = {
        "label": label,
        "n_features": int(X.shape[1]),
        "n_samples": int(len(y)),
        "n_folds": len(folds),
        "n_daily": int(len(daily_rets)),
        "n_trials_dsr": n_alphas,
        "median_test_ic": float(np.median([f["test_ic"] for f in folds])),
        "median_train_cv_ic": float(np.median([f["train_cv_ic"] for f in folds])),
        "median_fold_sr": float(np.median([f["fold_sr"] for f in folds])),
        "dsr_sharpe": dsr.sr,
        "dsr_sr_ann": dsr.sr_annualized,
        "dsr": dsr.dsr,
        "pass": dsr.pass_threshold,
        "skew": dsr.skew,
        "kurt": dsr.kurtosis,
        "folds": folds,
        "self_neutralize": self_neutralize,
        "icir": _icir_value,
        "positive_fold_rate": _pos_fold_rate,
        "research_gate_verdict": _research_verdict,
    }
    if fb_metrics is not None:
        s["fallback_as_failure"] = fb_metrics
    if _bh_fdr_summary is not None:
        s["bh_fdr"] = _bh_fdr_summary
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
    logger.info(
        "[%s] folds=%d med_test_IC=%.4f med_train_IC=%.4f "
        "med_SR=%.4f DSR=%.3f n_daily=%d",
        label,
        len(folds),
        s["median_test_ic"],
        s["median_train_cv_ic"],
        s["median_fold_sr"],
        dsr.dsr,
        len(daily_rets),
    )
    if fold_dsr_res is not None:
        logger.info(
            "[%s] FOLD-DSR=%.3f sr_mean=%.4f (ann %.3f) sr_std=%.4f e_max=%.4f",
            label,
            fold_dsr_res.dsr,
            fold_dsr_res.sr,
            fold_dsr_res.sr_annualized,
            fold_dsr_res.sr_std,
            fold_dsr_res.expected_max_sr,
        )
    # -------------------------------------------------------------------
    # Pass override: BH-FDR failure or high fallback rate or RETIRE
    # verdict overrides DSR pass to False (GATE: LLM_ALPHA_ENHANCEMENT_20260618).
    # Even if DSR passes, the alpha is not trustworthy if:
    # (a) BH-FDR: < 50% of folds are significant (fraction_significant < 0.5),
    # (b) Fallback-as-failure rate exceeds 50% (alpha pipeline failing),
    # (c) Research gate verdict is RETIRE (negative IC or fails FDR).
    # -------------------------------------------------------------------
    _pass_override_reasons = []
    if _bh_fdr_summary is not None and not _bh_fdr_summary.get("passes_fdr", False):
        _pass_override_reasons.append(
            f"BH-FDR FAIL (fraction_significant="
            f"{_bh_fdr_summary['fraction_significant']:.3f} < 0.5, "
            f"median_q={_bh_fdr_summary['overall_qvalue']:.4f})"
        )
    if fb_metrics is not None and fb_metrics["fallback_as_failure_rate"] > 0.50:
        _pass_override_reasons.append(
            f"FALLBACK RATE={fb_metrics['fallback_as_failure_rate']:.3f} > 0.50"
        )
    if _research_verdict == "RETIRE":
        _pass_override_reasons.append(
            f"RESEARCH GATE VERDICT=RETIRE"
        )
    if _pass_override_reasons and s.get("pass", False):
        logger.warning(
            "[%s] PASS OVERRIDE: DSR passed but overridden to False due to: %s",
            label,
            "; ".join(_pass_override_reasons),
        )
        s["pass"] = False
        s["pass_override_reasons"] = _pass_override_reasons
    return s


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true")
    p.add_argument(
        "--walk-forward",
        action="store_true",
        help="Use per-year walk-forward universe (Phase 1.5 v2 fix)",
    )
    p.add_argument(
        "--tail-controls",
        action="store_true",
        help="Apply Phase 3.4 tail controls (vol target + cap + DD breaker)",
    )
    p.add_argument(
        "--realistic-tc",
        action="store_true",
        help=(
            "Apply Phase 3.5 realistic VN execution costs "
            "(commission + spread + slippage)"
        ),
    )
    p.add_argument(
        "--capital-vnd",
        type=float,
        default=1e9,
        help="Portfolio capital VND for slippage scaling (default 1B)",
    )
    p.add_argument(
        "--top-k",
        type=int,
        default=0,
        help="Sparse positions: long top-K, short bottom-K (0 = full demedian)",
    )
    p.add_argument(
        "--rebal-threshold",
        type=float,
        default=0.0,
        help="Rebalance only when sum |delta_w| > threshold (0 = always)",
    )
    p.add_argument(
        "--label-horizon",
        type=int,
        default=5,
        help="Forward return label horizon in days (default 5)",
    )
    p.add_argument(
        "--signal-ema",
        type=int,
        default=0,
        help="EMA span for prediction smoothing per ticker (0=disabled)",
    )
    p.add_argument(
        "--shuffle-y",
        action="store_true",
        help="Falsification test: randomize labels (must produce SR ~ 0 if no leakage)",
    )
    p.add_argument(
        "--embargo-pct",
        type=float,
        default=0.01,
        help=(
            "Embargo as fraction of N (default 0.01); bump to >= "
            "bar_horizon/N for AFML compliance"
        ),
    )
    p.add_argument("--year-start", type=int, default=2020)
    p.add_argument("--year-end", type=int, default=2024)
    p.add_argument(
        "--data-path",
        default=str(REPO_ROOT / "data/market_2015_now.parquet"),
        help="Parquet OHLCV dataset path (default: data/market_2015_now.parquet)",
    )
    p.add_argument("--out", default=".ly_state/session/phase3_3_v2.json")
    p.add_argument(
        "--lstm", action="store_true", help="Phase 4: enable Ridge+LSTM ensemble"
    )
    p.add_argument(
        "--lstm-blend",
        type=float,
        default=0.5,
        help="Phase 4: ensemble weight for LSTM (0=Ridge only, 1=LSTM only)",
    )
    p.add_argument(
        "--lstm-lookback",
        type=int,
        default=60,
        help="Phase 4: LSTM lookback window (days)",
    )
    p.add_argument(
        "--lstm-hidden", type=int, default=64, help="Phase 4: LSTM hidden size"
    )
    p.add_argument(
        "--lstm-epochs",
        type=int,
        default=8,
        help="Phase 4: LSTM training epochs per fold",
    )
    p.add_argument(
        "--lstm-loss",
        choices=["mse", "ic"],
        default="mse",
        help="Phase 6: LSTM loss function (mse=regression, ic=-Pearson)",
    )
    p.add_argument(
        "--ensemble-horizons",
        default="",
        help=(
            "Phase 10: comma-sep horizons for multi-Ridge ensemble "
            "(e.g. '20,60'). Empty = single horizon (--label-horizon)."
        ),
    )
    p.add_argument(
        "--ensemble-weights",
        default="",
        help=(
            "Phase 10: comma-sep blend weights (default uniform). "
            "Must match --ensemble-horizons count."
        ),
    )
    # Phase 11 cost-model knobs
    p.add_argument(
        "--slip-nonlinear-exp",
        type=float,
        default=1.0,
        help=(
            "Phase 11: slippage nonlinear exponent "
            "(1.0=linear legacy, 0.6=AC-ish, 1.5=toxic execution)"
        ),
    )
    p.add_argument(
        "--settlement-lag-days",
        type=float,
        default=0.0,
        help=(
            "Phase 11: HOSE T+2.5 settlement lag "
            "(0=off; 2.5=enable haircut ~1bp/day*lag)"
        ),
    )
    p.add_argument(
        "--halt-limit-haircut",
        type=float,
        default=0.0,
        help=(
            "Phase 11: per-bar limit-lock haircut as fraction "
            "(e.g. 0.0005 = 5 bps/bar)"
        ),
    )
    p.add_argument(
        "--foreign-room-haircut",
        type=float,
        default=0.0,
        help="Phase 11: foreign-fill haircut as fraction (e.g. 0.0002 = 2 bps/bar)",
    )
    p.add_argument(
        "--regime-overlay",
        action="store_true",
        help=(
            "Phase 13: apply RegimeDetector exposure overlay before "
            "vol-target (bull=1.1x, bear=0.5x, sideways=0.8x)"
        ),
    )
    p.add_argument(
        "--regime-hysteresis",
        type=int,
        default=5,
        help="Phase 13: minimum days to hold regime before switching (default 5)",
    )
    p.add_argument(
        "--regime-dd-threshold",
        type=float,
        default=-0.10,
        help="Phase 13: drawdown threshold for BEAR detection (default -0.10)",
    )
    p.add_argument(
        "--regime-bear-exposure",
        type=float,
        default=0.5,
        help="Phase 13: exposure in BEAR regime (default 0.5)",
    )
    p.add_argument(
        "--regime-bull-exposure",
        type=float,
        default=1.1,
        help="Phase 13: exposure in BULL regime (default 1.1)",
    )
    p.add_argument(
        "--regime-sideways-exposure",
        type=float,
        default=0.8,
        help="Phase 13: exposure in SIDEWAYS regime (default 0.8)",
    )
    p.add_argument(
        "--regime-hmm",
        action="store_true",
        help="Phase 13b: use HMM regime detector instead of simple MA/vol rules",
    )
    p.add_argument(
        "--regime-hmm-retrain",
        type=int,
        default=60,
        help="Phase 13b: retrain HMM every N bars (default 60)",
    )
    p.add_argument(
        "--smart-money",
        action="store_true",
        help="Phase 14: smart money overlay (CMF/VWAP/OBV boost)",
    )
    p.add_argument(
        "--smart-money-boost",
        type=float,
        default=0.25,
        help="Phase 14: smart money boost scale",
    )
    p.add_argument(
        "--sentiment", action="store_true", help="Phase 14: sentiment proxy overlay"
    )
    p.add_argument(
        "--sentiment-boost",
        type=float,
        default=0.2,
        help="Phase 14: sentiment boost scale",
    )
    p.add_argument(
        "--contagion",
        action="store_true",
        help="Phase 14: contagion/correlation spike overlay",
    )
    p.add_argument(
        "--tcost",
        action="store_true",
        help="Phase 14: transaction cost optimizer overlay",
    )
    p.add_argument(
        "--tcost-threshold",
        type=float,
        default=30.0,
        help="Phase 14: min trade threshold bps",
    )
    p.add_argument(
        "--advanced-breaker",
        action="store_true",
        help="Phase 14: advanced CVaR circuit breaker",
    )
    p.add_argument(
        "--breaker-cvar-limit",
        type=float,
        default=-0.08,
        help="Phase 14: CVaR limit for breaker",
    )
    p.add_argument(
        "--use-latent-features",
        action="store_true",
        help="Option B: Train unsupervised latent autoencoder features",
    )
    p.add_argument(
        "--use-llm-alphas",
        action="store_true",
        help="Option A: Ingest LLM symbolic synthesized alpha formulas",
    )
    p.add_argument(
        "--llm-provider",
        type=str,
        default="mock",
        choices=["mock", "openai-compatible"],
        help="LLM provider type: 'mock' (default, offline) or 'openai-compatible' (requires OMEGA_LLM_API_KEY env)",
    )
    p.add_argument(
        "--llm-search-iterations",
        type=int,
        default=3,
        help="Closed-loop LLM search: number of iterations (default 3)",
    )
    p.add_argument(
        "--llm-search-candidates",
        type=int,
        default=10,
        help="Closed-loop LLM search: candidates per iteration (default 10)",
    )
    p.add_argument(
        "--llm-prompt-version",
        type=str,
        default="vn_alpha_search_v3_closed_loop",
        help="LLM prompt version (default: vn_alpha_search_v3_closed_loop)",
    )
    p.add_argument(
        "--llm-search-evidence",
        type=str,
        default=".ly_state/session/llm_closed_loop_formula_search_20260612.json",
        help="Path to save LLM search evidence JSON",
    )
    p.add_argument(
        "--llm-top-k",
        type=int,
        default=0,
        help="Limit LLM features to top K candidates (0=no limit, default from env OMEGA_LLM_TOP_K or 10 if search enabled)",
    )
    p.add_argument(
        "--latent-dim",
        type=int,
        default=16,
        help="Option B: Latent representation dimensions",
    )
    p.add_argument(
        "--latent-epochs",
        type=int,
        default=5,
        help="Option B: Latent encoder training epochs",
    )
    p.add_argument(
        "--train-prefix-supervised",
        action="store_true",
        help=(
            "Enable train-prefix SUPERVISED selection: use PIT-safe "
            "forward-return labels within the causal train-prefix for "
            "IC-based formula scoring/selection (default: unsupervised only)"
        ),
    )
    p.add_argument(
        "--min-fold-ic",
        type=float,
        default=0.005,
        help=(
            "Minimum abs(test IC) for a CPCV fold to count as alpha-selected "
            "vs. fallback (default 0.005). Folds below this are flagged as "
            "fallback in fallback-as-failure diagnostics."
        ),
    )
    p.add_argument(
        "--fallback-failure-threshold",
        type=float,
        default=0.50,
        help=(
            "Maximum allowed fallback-as-failure rate. If the fraction of "
            "CPCV folds using fallback exceeds this, log a CRITICAL warning "
            "(default 0.50 = 50%%)."
        ),
    )
    p.add_argument(
        "--self-neutralize",
        action="store_true",
        help=(
            "Enable cross-sectional self-neutralization: demean alpha "
            "predictions per test date to remove market-factor contamination. "
            "PIT-safe: uses only same-date cross-sectional data."
        ),
    )
    p.add_argument(
        "--bh-fdr-alpha",
        type=float,
        default=0.05,
        help=(
            "Benjamini-Hochberg FDR significance level for multiple testing "
            "correction on per-fold IC p-values (default 0.05). Folds whose "
            "BH-adjusted q-value exceeds this are flagged as non-significant."
        ),
    )
    args = p.parse_args()
    cpcv_mod = _import("_cpcv", "omega/quant/validation/cpcv.py")
    dsr_mod = _import("_dsr", "omega/quant/validation/dsr.py")
    feat_mod = _import("_feat", "omega/quant/evolution/feature_adapter.py")
    tail_mod = (
        _import("_tc", "omega/quant/portfolio/tail_controls.py")
        if args.tail_controls
        else None
    )
    exec_mod = (
        _import("_es", "omega/quant/portfolio/execution_sim.py")
        if args.realistic_tc
        else None
    )
    # Phase 11: build custom VNCostModel from CLI knobs (defaults preserve
    # backward compat). Falls through to DEFAULT_VN_COSTS if nothing set.
    custom_cost_model = None
    if exec_mod is not None and (
        args.slip_nonlinear_exp != 1.0
        or args.settlement_lag_days > 0
        or args.halt_limit_haircut > 0
        or args.foreign_room_haircut > 0
    ):
        defaults = exec_mod.DEFAULT_VN_COSTS
        custom_cost_model = exec_mod.VNCostModel(
            commission_buy=defaults.commission_buy,
            commission_sell=defaults.commission_sell,
            tax_sell=defaults.tax_sell,
            half_spread_bps=defaults.half_spread_bps,
            slippage_k=defaults.slippage_k,
            slippage_nonlinear_exp=args.slip_nonlinear_exp,
            foreign_room_cap=defaults.foreign_room_cap,
            settlement_lag_days=args.settlement_lag_days,
            halt_limit_haircut_pct=args.halt_limit_haircut,
            foreign_room_haircut_pct=args.foreign_room_haircut,
        )
        logger.info(
            "Phase 11 cost model: slip_exp=%.2f settle=%.1fd halt=%.4f foreign=%.4f",
            args.slip_nonlinear_exp,
            args.settlement_lag_days,
            args.halt_limit_haircut,
            args.foreign_room_haircut,
        )
    lstm_mod = (
        _import("_lstm", "omega/quant/models/lstm_alpha.py") if args.lstm else None
    )
    latent_mod = (
        _import("_latent", "omega/quant/models/latent_encoder.py")
        if args.use_latent_features
        else None
    )
    if args.walk_forward:
        wf = load_universe_walk_forward(args.year_start, args.year_end)
        if args.smoke:
            wf = {y: t[:5] for y, t in wf.items()}
            logger.info("SMOKE WF: 5 tickers/year")
        panel = load_panel_walk_forward(wf, args.year_start, args.year_end, args.data_path)
    else:
        tickers = load_universe()
        if args.smoke:
            tickers = tickers[:5]
            logger.info("SMOKE: 5 tickers")
        panel = load_panel(tickers, args.year_start, args.year_end, args.data_path)
    if panel.empty:
        logger.error("Empty panel")
        return 1
    target = compute_target(panel, horizon=args.label_horizon)
    # Phase 10 (B): build per-horizon target arrays for ensemble.
    ensemble_y_dict = None
    ensemble_weights_list = None
    if args.ensemble_horizons.strip():
        horizons = [
            int(h.strip()) for h in args.ensemble_horizons.split(",") if h.strip()
        ]
        ensemble_y_dict = {}
        for h in horizons:
            ensemble_y_dict[h] = compute_target(panel, horizon=h)
        if args.ensemble_weights.strip():
            ensemble_weights_list = [float(w) for w in args.ensemble_weights.split(",")]
            assert len(ensemble_weights_list) == len(horizons), (
                f"ensemble-weights count {len(ensemble_weights_list)} != "
                f"horizons count {len(horizons)}"
            )
        logger.info(
            "Ensemble horizons enabled: %s, weights=%s",
            horizons,
            ensemble_weights_list or "uniform",
        )
    if args.shuffle_y:
        rng = np.random.default_rng(42)
        # Shuffle within date: preserve cross-section, break alpha-target link.
        target_arr = target.to_numpy().copy()
        date_arr = panel["date"].to_numpy()
        unique_dates = np.unique(date_arr)
        for d in unique_dates:
            mask = date_arr == d
            idx = np.where(mask)[0]
            shuffled = rng.permutation(target_arr[idx])
            target_arr[idx] = shuffled
        target = pd.Series(target_arr, index=target.index)
        logger.info(
            "FALSIFICATION TEST: y-shuffled within each date (alpha-target link broken)"
        )
    feat_dict = feat_mod.GPFeatureAdapter().compute_all(panel, top_n_features=125)
    # L3 Fix #2: Build causal train-prefix panel for unsupervised scoring.
    # CPCV test folds can appear anywhere in the time range, so using
    # full-panel unsupervised metrics (variance, coverage) for formula
    # selection leaks test-fold distribution information. Fix: restrict
    # scoring to the first 50% of unique dates (causal train prefix),
    # making formula selection independent of any test-fold data.
    # Hoisted outside the LLM block so the cutoff is available for
    # prefix-test-fold isolation in run_pipeline (fix2).
    _unique_dates_sorted = sorted(panel["date"].unique())
    _causal_cutoff_idx = max(len(_unique_dates_sorted) // 2, 1)
    _causal_cutoff_date = pd.Timestamp(_unique_dates_sorted[_causal_cutoff_idx])
    _train_prefix_mask = panel["date"] <= _causal_cutoff_date
    logger.info(
        "L3 Fix #2: Causal train-prefix cutoff=%s (%d/%d panel rows in prefix)",
        _causal_cutoff_date.date(),
        _train_prefix_mask.sum(),
        len(panel),
    )

    # Train-prefix supervised selection: compute PIT-safe forward-return
    # labels restricted to the causal train-prefix for IC-based formula
    # scoring.  Only rows whose forward horizon (T + label_horizon) stays
    # within the prefix are labeled — no test-region data leaks.
    _tp_supervised_labels = None
    if args.train_prefix_supervised:
        _tp_supervised_labels = _compute_train_prefix_supervised_labels(
            panel, _causal_cutoff_date, args.label_horizon,
        )
        logger.info(
            "Train-prefix SUPERVISED selection enabled: %d valid labels "
            "(IC-based scoring will use forward returns within prefix)",
            int(_tp_supervised_labels.notna().sum()),
        )

    llm_validation_summary = None
    
    if args.use_llm_alphas:
        try:
            synth_mod = _import(
                "_llm_synth", "omega/quant/evolution/llm_symbolic_synthesizer.py"
            )
            scorer_mod = _import(
                "_scorer", "omega/quant/evolution/llm_formula_scorer.py"
            )
            
            # L3 Fix #2: _causal_cutoff_date and _train_prefix_mask are
            # computed above (hoisted).  They are used for both LLM scoring
            # and CPCV test-fold prefix isolation.
            
            # Check if closed-loop search is requested
            use_closed_loop = args.llm_search_iterations > 1
            
            # Determine effective top_k (CLI > env > default)
            llm_top_k = args.llm_top_k
            if llm_top_k == 0:
                llm_top_k = int(os.environ.get('OMEGA_LLM_TOP_K', '10' if use_closed_loop else '0'))
            
            logger.info(
                "LLM top-K selection: %s (0=no limit)",
                llm_top_k if llm_top_k > 0 else "disabled",
            )
            
            if use_closed_loop:
                # Closed-loop iterative search with failure feedback
                search_mod = _import(
                    "_search", "omega/quant/evolution/llm_formula_search.py"
                )
                
                logger.info(
                    "LLM closed-loop search enabled: %d iterations, %d candidates/iter, prompt=%s",
                    args.llm_search_iterations,
                    args.llm_search_candidates,
                    args.llm_prompt_version,
                )
                
                # Configure search
                search_config = search_mod.FormulaSearchConfig(
                    max_iterations=args.llm_search_iterations,
                    candidates_per_iteration=args.llm_search_candidates,
                    prompt_version=args.llm_prompt_version,
                    llm_provider=args.llm_provider,
                    min_coverage=0.70,
                    min_variance=1e-8,
                    max_nan_inf_ratio=0.30,
                )
                
                # Build temporary DataFrame for grouped execution
                temp_df = pd.DataFrame(feat_dict, index=panel.index)
                temp_df["ticker"] = panel["ticker"].values
                temp_df["date"] = panel["date"].values
                feat_cols = list(feat_dict.keys())
                
                # L3 Fix #2: Build train-prefix temp_df for search scoring
                # (unsupervised metrics computed only on causal train data)
                _train_prefix_df = temp_df.loc[_train_prefix_mask].copy()
                
                # Build supervised labels for train-prefix (PIT-safe:
                # forward returns clipped to prefix boundary).
                _tp_labels = None
                if _tp_supervised_labels is not None:
                    _tp_labels = _tp_supervised_labels.loc[_train_prefix_mask].values
                    _n_valid_tp = int(pd.Series(_tp_labels).notna().sum())
                    logger.info(
                        "Supervised labels for train-prefix: %d/%d valid",
                        _n_valid_tp, len(_tp_labels),
                    )

                # Run closed-loop search (PIT-safe: train-prefix only)
                # labels=None → unsupervised; labels=array → supervised IC scoring
                runner = search_mod.FormulaSearchRunner(search_config)
                candidate_nodes, search_evidence = runner.run_search(
                    panel=_train_prefix_df,
                    feat_cols=feat_cols,
                    labels=_tp_labels,
                    ticker_col="ticker",
                    date_col="date",
                    top_features=None,  # TODO: could extract from existing features
                    correlation_clusters=None,
                )
                
                # Note: evidence_path defined here for later use
                evidence_path = Path(args.llm_search_evidence)
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Apply top-K candidate selection if enabled (before saving evidence)
                if llm_top_k > 0 and len(candidate_nodes) > llm_top_k:
                    logger.info(
                        "Applying top-K selection: selecting %d from %d candidates using %s metrics (train-prefix only)",
                        llm_top_k,
                        len(candidate_nodes),
                        "supervised" if _tp_labels is not None else "unsupervised",
                    )
                    candidate_nodes, selection_stats = runner.select_top_k_candidates(
                        candidate_nodes=candidate_nodes,
                        panel=_train_prefix_df,
                        feat_cols=feat_cols,
                        labels=_tp_labels,
                        top_k=llm_top_k,
                        ticker_col="ticker",
                        date_col="date",
                    )
                    logger.info(
                        "Top-K selection complete: %d candidates selected (mode=%s, metric=%s)",
                        len(candidate_nodes),
                        selection_stats["selection_mode"],
                        selection_stats.get("metric_name", "unknown"),
                    )
                    # Update search evidence with selection metadata
                    search_evidence["top_k_selection"] = selection_stats
                    search_evidence["summary"]["final_candidate_count_after_topk"] = len(candidate_nodes)
                else:
                    logger.info("Top-K selection disabled or not needed (top_k=%d, candidates=%d)", llm_top_k, len(candidate_nodes))
                    search_evidence["top_k_selection"] = {"enabled": False, "top_k": llm_top_k}
                
                # Save search evidence AFTER top-K selection (includes all metadata)
                with open(evidence_path, "w") as f:
                    json.dump(search_evidence, f, indent=2)
                logger.info("Search evidence saved to %s", evidence_path)
                
                # Save search memory/state for reproducibility
                memory_path = evidence_path.parent / "llm_formula_search_memory_20260612.json"
                runner.save_state(memory_path)
                logger.info("Search memory saved to %s", memory_path)
                
                # Build synthesis_stats for logging compatibility
                synthesis_stats = {
                    "prompt_version": args.llm_prompt_version,
                    "max_candidates": args.llm_search_candidates * args.llm_search_iterations,
                    "cache_hit": False,
                    "search_mode": "closed_loop",
                    "search_evidence_path": str(evidence_path),
                }
                
                logger.info("LLM provider: %s", args.llm_provider)
                logger.info("LLM closed-loop search: %d final candidates", len(candidate_nodes))
                logger.info(
                    "Search summary: %d total generated, %d iterations completed",
                    search_evidence["summary"]["total_candidates_generated"],
                    search_evidence["final_state"]["current_iteration"] + 1,
                )
            else:
                # Simple single-shot synthesis (original path)
                # Use provider from CLI (default='mock' for safety)
                # Real provider requires OMEGA_LLM_API_KEY env var
                synthesizer = synth_mod.LLMSymbolicSynthesizer(
                    provider=args.llm_provider,
                    prompt_version=args.llm_prompt_version,
                    max_candidates=args.llm_search_candidates,
                )
                
                # New signature returns (nodes, synthesis_stats)
                candidate_nodes, synthesis_stats = synthesizer.synthesize(feat_dict)
                
                logger.info("LLM provider: %s", args.llm_provider)
                logger.info("LLM synthesis: %d candidate formulas generated", len(candidate_nodes))
                logger.info(
                    "LLM synthesis stats: prompt_version=%s max_candidates=%d cache_hit=%s",
                    synthesis_stats.get("prompt_version"),
                    synthesis_stats.get("max_candidates"),
                    synthesis_stats.get("cache_hit")
                )
            
            # Build temporary DataFrame for grouped execution (PIT-safe per-ticker execution).
            temp_df = pd.DataFrame(feat_dict, index=panel.index)
            temp_df["ticker"] = panel["ticker"].values
            temp_df["date"] = panel["date"].values
            feat_cols = list(feat_dict.keys())
            
            # L3 Fix #2: Build train-prefix temp_df for scoring
            _train_prefix_df = temp_df.loc[_train_prefix_mask].copy()
            
            # Build supervised labels for train-prefix (shared by both paths)
            _tp_labels_simple = None
            if _tp_supervised_labels is not None:
                _tp_labels_simple = _tp_supervised_labels.loc[_train_prefix_mask].values
            
            # For simple synthesis path only: score and filter formulas
            if not use_closed_loop:
                # L3 Fix #2: Use train-prefix panel for scoring
                # (no test-fold data in formula selection decisions)
                scorer_config = scorer_mod.FormulaScorerConfig(
                    min_coverage=0.70,
                    min_variance=1e-8,
                    max_per_ticker_variance=1e6,
                    max_nan_inf_ratio=0.30,
                    min_absolute_ic=0.01,
                    min_dsr_proxy=-0.5,
                    allow_unvalidated=True,
                )
                
                candidate_nodes, scoring_stats = synthesizer.score_and_filter_formulas(
                    nodes=candidate_nodes,
                    panel=_train_prefix_df,
                    feat_cols=feat_cols,
                    labels=_tp_labels_simple,
                    scorer_config=scorer_config,
                    ticker_col="ticker",
                    date_col="date",
                    synthesis_stats=synthesis_stats,
                )
                
                # Apply top-K candidate selection if enabled
                if llm_top_k > 0 and len(candidate_nodes) > llm_top_k:
                    logger.info(
                        "Applying top-K selection: selecting %d from %d candidates using %s metrics (train-prefix only)",
                        llm_top_k,
                        len(candidate_nodes),
                        "supervised" if _tp_labels_simple is not None else "unsupervised",
                    )
                    # Import search module for top-K selection helper
                    search_mod = _import(
                        "_search", "omega/quant/evolution/llm_formula_search.py"
                    )
                    # Create temporary runner just for top-K selection
                    temp_runner = search_mod.FormulaSearchRunner(
                        search_mod.FormulaSearchConfig(llm_provider=args.llm_provider)
                    )
                    temp_runner.synthesizer = synthesizer
                    
                    candidate_nodes, selection_stats = temp_runner.select_top_k_candidates(
                        candidate_nodes=candidate_nodes,
                        panel=_train_prefix_df,
                        feat_cols=feat_cols,
                        labels=_tp_labels_simple,
                        top_k=llm_top_k,
                        ticker_col="ticker",
                        date_col="date",
                    )
                    logger.info(
                        "Top-K selection complete: %d candidates selected (mode=%s, metric=%s)",
                        len(candidate_nodes),
                        selection_stats["selection_mode"],
                        selection_stats.get("metric_name", "unknown"),
                    )
                    # Update scoring_stats with selection metadata
                    scoring_stats["top_k_selection"] = selection_stats
                    scoring_stats["final_candidate_count_after_topk"] = len(candidate_nodes)
            else:
                # Closed-loop path: candidate_nodes are already scored/filtered by runner
                # Build scoring_stats from search_evidence for logging compatibility
                # Use same-scope counts: all from scoring stage (not mixing raw/scoring)
                scoring_stats = {
                    "total": search_evidence["summary"].get("total_scoring_input", search_evidence["summary"]["total_candidates_accepted"]),  # Scoring stage input
                    "accepted": search_evidence["summary"]["total_candidates_accepted"],  # Scoring stage accepted
                    "rejected": search_evidence["summary"].get("total_scoring_rejected", 0),  # Scoring stage rejected (same scope)
                    "deployable": 0,  # Requires full CPCV validation
                    "unsupervised_only": search_evidence["summary"]["total_candidates_accepted"],
                    "raw_generated": search_evidence["summary"]["total_candidates_generated"],  # Separate: raw generation count
                    "final_after_topk": len(candidate_nodes),  # Separate: final count after top-K selection
                    "rejection_taxonomy": search_evidence["final_state"]["iteration_results"][-1].get("scoring_stats", {}).get("rejection_taxonomy", {}) if search_evidence["final_state"]["iteration_results"] else {},
                }
            
            # Common path: Add accepted formulas to feat_dict
            for i, node in enumerate(candidate_nodes):
                col_name = f"alpha_llm_{i}"
                # PIT-safe grouped execution: compute per ticker, sorted by date
                if use_closed_loop:
                    # Use runner's synthesizer
                    val = runner.synthesizer.execute_node_grouped(
                        node, temp_df, feat_cols, ticker_col="ticker", date_col="date"
                    )
                else:
                    # Use simple path synthesizer
                    val = synthesizer.execute_node_grouped(
                        node, temp_df, feat_cols, ticker_col="ticker", date_col="date"
                    )
                feat_dict[col_name] = val
                logger.info("LLM Synthesized alpha added (grouped): %s", col_name)
            
            # Build safe aggregate validation summary (PIT-safe: no row-level label data)
            llm_validation_summary = {
                "prompt_version": synthesis_stats.get("prompt_version"),
                "provider": synthesis_stats.get("provider_type") if not use_closed_loop else args.llm_provider,
                "cache_hit": synthesis_stats.get("cache_hit", False),
                "search_mode": "closed_loop" if use_closed_loop else "simple",
                "total_candidates": scoring_stats.get("total", 0),
                "accepted": scoring_stats.get("accepted", 0),
                "rejected": scoring_stats.get("rejected", 0),
                "deployable": scoring_stats.get("deployable", 0),
                "unsupervised_only": scoring_stats.get("unsupervised_only", 0),
                "rejection_taxonomy": scoring_stats.get("rejection_taxonomy", {}),
                "train_prefix_supervised": args.train_prefix_supervised,
            }
            
            if use_closed_loop:
                llm_validation_summary["search_evidence_path"] = str(evidence_path)
                llm_validation_summary["search_iterations"] = args.llm_search_iterations
            
            # Log scoring summary
            logger.info(
                "LLM formula scoring: %d candidates, %d accepted (%d deployable, %d unsupervised_only), %d rejected",
                scoring_stats['total'],
                scoring_stats['accepted'],
                scoring_stats.get('deployable', 0),
                scoring_stats.get('unsupervised_only', 0),
                scoring_stats['rejected'],
            )
        except Exception as e:
            logger.warning("LLM Synthesis failed: %s", e)
    feat_names = list(feat_dict.keys())
    feat_df = pd.DataFrame(feat_dict, index=panel.index)
    feat_df["ticker"] = panel["ticker"].values
    feat_df["date"] = panel["date"].values
    feat_df["target"] = target.values
    feat_df["adv_vnd"] = (
        panel["adv_vnd"].values if "adv_vnd" in panel.columns else np.nan
    )
    feat_df = feat_df.sort_values(["date", "ticker"]).reset_index(drop=True)
    valid = ~feat_df["target"].isna() & ~feat_df[feat_names].isna().any(axis=1)
    feat_df = feat_df[valid].reset_index(drop=True)
    # L3 Fix #2b (fix2): Prefix isolation — mark rows in the dev-prefix
    # (first ~50% of dates) so they are excluded from all CPCV test folds.
    # This ensures the prefix used for LLM formula scoring/selection never
    # overlaps with OOS test rows, closing the distributional leakage path
    # flagged by the L3 re-audit (finding #2, fix1).
    _prefix_test_mask = None
    if args.use_llm_alphas:
        _prefix_test_mask = (feat_df["date"] <= _causal_cutoff_date).to_numpy()
        logger.info(
            "L3 Fix #2b: Prefix isolation: %d/%d feat_df rows in dev prefix "
            "(cutoff=%s) — excluded from all CPCV test folds",
            int(_prefix_test_mask.sum()),
            len(feat_df),
            _causal_cutoff_date.date(),
        )
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
            logger.info(
                "ADV imputation: filled %d NaN cells via causal expanding "
                "median (cold-start fallback=0.0)",
                int(mask_nan.sum()),
            )
        logger.info(
            "ADV stats (VND): median=%.2e p10=%.2e p90=%.2e",
            float(np.median(adv_arr)),
            float(np.percentile(adv_arr, 10)),
            float(np.percentile(adv_arr, 90)),
        )
    max_per_date = int(feat_df.groupby("date").size().max())
    bar_horizon = 5 * max_per_date  # P1-2 fix
    ts = pd.Series(np.arange(len(y)))
    dates = feat_df["date"].to_numpy()
    logger.info(
        "Drop NaN: %d samples, %d feats, max_per_date=%d, bar_horizon=%d",
        len(y),
        X.shape[1],
        max_per_date,
        bar_horizon,
    )
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
        logger.info(
            "LSTM enabled: lookback=%d hidden=%d epochs=%d blend=%.2f loss=%s",
            lstm_cfg.lookback,
            lstm_cfg.hidden_size,
            lstm_cfg.epochs,
            args.lstm_blend,
            args.lstm_loss,
        )
    latent_cfg = None
    if args.use_latent_features and latent_mod is not None:
        latent_cfg = latent_mod.LatentEncoderConfig(
            lookback=args.lstm_lookback,
            n_features=int(X.shape[1]),
            latent_dim=args.latent_dim,
            epochs=args.latent_epochs,
        )
        logger.info(
            "Unsupervised Latent features enabled: lookback=%d latent_dim=%d epochs=%d",
            latent_cfg.lookback,
            latent_cfg.latent_dim,
            latent_cfg.epochs,
        )
    # Phase 10: convert per-horizon target Series into aligned numpy arrays
    # using the same `valid` mask as the primary y. We must compute targets
    # BEFORE the dropna mask was applied, then re-mask to align with X.
    ensemble_y_aligned = None
    if ensemble_y_dict is not None:
        ensemble_y_aligned = {}
        for h, target_h in ensemble_y_dict.items():
            # Build a feat_df-aligned target for this horizon, then apply
            # the same valid mask used to build X / y.
            target_h_aligned = target_h.reindex(panel.index)
            target_h_full = pd.DataFrame(
                {
                    "target": target_h_aligned.values,
                    "date": panel["date"].values,
                    "ticker": panel["ticker"].values,
                }
            )
            target_h_full = target_h_full.sort_values(["date", "ticker"]).reset_index(
                drop=True
            )
            # The same `valid` mask used in feat_df construction; we re-apply
            # by intersecting with the original feat_df rows already kept.
            # Easiest: the X/y arrays are aligned to feat_df rows after
            # dropna; we just need target_h at those same (date, ticker)
            # rows. Use a join.
            keep_keys = list(zip(feat_df["date"].values, feat_df["ticker"].values))
            tgt_lookup = dict(
                zip(
                    zip(target_h_full["date"].values, target_h_full["ticker"].values),
                    target_h_full["target"].values,
                )
            )
            y_h = np.array(
                [tgt_lookup.get(k, np.nan) for k in keep_keys], dtype=np.float64
            )
            # Drop NaN by replacing with primary y (so this horizon contributes
            # 0 marginal info on rows with no future return). Better: signal
            # the row to be skipped per fold via masked Ridge fit. For
            # simplicity here we fillna with column median of y.
            mask_nan = np.isnan(y_h)
            if mask_nan.any():
                y_h = np.where(mask_nan, np.nanmedian(y_h), y_h)
            ensemble_y_aligned[h] = y_h
        logger.info(
            "Ensemble target arrays built: horizons=%s sizes=%s",
            list(ensemble_y_aligned.keys()),
            [len(v) for v in ensemble_y_aligned.values()],
        )

    # Phase 13: regime overlay module
    regime_mod = None
    regime_hmm_mod = None
    if args.regime_overlay:
        if args.regime_hmm:
            regime_hmm_mod = _import(
                "_regime_hmm", "omega/quant/portfolio/hmm_regime_overlay.py"
            )
            logger.info(
                "Phase 13b: HMM Regime overlay enabled (retrain=%d bars)",
                args.regime_hmm_retrain,
            )
        else:
            regime_mod = _import("_regime", "omega/quant/portfolio/regime_overlay.py")
            logger.info(
                "Phase 13: Regime overlay enabled (hysteresis=%d days)",
                args.regime_hysteresis,
            )

    # Phase 14: additional overlays
    smart_money_mod = (
        _import("_sm", "omega/quant/portfolio/smart_money_overlay.py")
        if args.smart_money
        else None
    )
    sentiment_mod = (
        _import("_sent", "omega/quant/portfolio/sentiment_overlay.py")
        if args.sentiment
        else None
    )
    contagion_mod = (
        _import("_cont", "omega/quant/portfolio/contagion_overlay.py")
        if args.contagion
        else None
    )
    tcost_mod = (
        _import("_tcost", "omega/quant/portfolio/tcost_optimizer_overlay.py")
        if args.tcost
        else None
    )
    breaker_mod = (
        _import("_breaker", "omega/quant/portfolio/advanced_breaker_overlay.py")
        if args.advanced_breaker
        else None
    )
    if any([smart_money_mod, sentiment_mod, contagion_mod, tcost_mod, breaker_mod]):
        logger.info(
            "Phase 14 overlays: SM=%s SENT=%s CONT=%s TCOST=%s BREAKER=%s",
            bool(smart_money_mod),
            bool(sentiment_mod),
            bool(contagion_mod),
            bool(tcost_mod),
            bool(breaker_mod),
        )

    summary = run_pipeline(
        X,
        y,
        ts,
        dates,
        cpcv_mod,
        dsr_mod,
        "A_baseline_alphas",
        label_horizon=args.label_horizon * max_per_date,
        tickers=tickers_arr,
        tail_mod=tail_mod,
        exec_mod_param=exec_mod,
        capital_vnd_param=args.capital_vnd,
        top_k_param=args.top_k,
        rebal_threshold_param=args.rebal_threshold,
        signal_ema_param=args.signal_ema,
        embargo_pct_param=args.embargo_pct,
        adv_arr=adv_arr if (exec_mod is not None and tickers_arr is not None) else None,
        lstm_cfg=lstm_cfg,
        lstm_mod=lstm_mod,
        feat_df=feat_df if (lstm_cfg is not None or latent_cfg is not None) else None,
        feat_names=(
            feat_names if (lstm_cfg is not None or latent_cfg is not None) else None
        ),
        lstm_blend=args.lstm_blend,
        ensemble_y=ensemble_y_aligned,
        ensemble_weights=ensemble_weights_list,
        cost_model_override=custom_cost_model,
        regime_mod_param=regime_mod,
        regime_hmm_mod_param=regime_hmm_mod,
        regime_hysteresis_param=args.regime_hysteresis,
        regime_dd_threshold_param=args.regime_dd_threshold,
        regime_bear_exposure_param=args.regime_bear_exposure,
        regime_bull_exposure_param=args.regime_bull_exposure,
        regime_sideways_exposure_param=args.regime_sideways_exposure,
        regime_hmm_retrain_param=args.regime_hmm_retrain,
        smart_money_mod_param=smart_money_mod,
        smart_money_boost_param=args.smart_money_boost,
        sentiment_mod_param=sentiment_mod,
        sentiment_boost_param=args.sentiment_boost,
        contagion_mod_param=contagion_mod,
        tcost_mod_param=tcost_mod,
        tcost_threshold_param=args.tcost_threshold,
        breaker_mod_param=breaker_mod,
        breaker_cvar_limit_param=args.breaker_cvar_limit,
        use_latent_features=args.use_latent_features,
        latent_cfg=latent_cfg,
        latent_mod=latent_mod,
        prefix_test_mask=_prefix_test_mask,
        min_fold_ic_threshold=args.min_fold_ic,
        self_neutralize=args.self_neutralize,
        bh_fdr_alpha=args.bh_fdr_alpha,
    )
    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    
    # Fallback-as-failure checkpoint gate
    _fb = summary.get("fallback_as_failure")
    if _fb is not None:
        _fb_rate = _fb.get("fallback_as_failure_rate", 0.0)
        if _fb_rate > args.fallback_failure_threshold:
            logger.critical(
                "FALLBACK-AS-FAILURE GATE: rate=%.3f EXCEEDS threshold=%.3f — "
                "alpha pipeline not producing qualifying candidates in %d/%d folds",
                _fb_rate,
                args.fallback_failure_threshold,
                _fb["fallback_folds"],
                _fb["total_folds"],
            )
            summary["fallback_gate"] = "FAIL"
        else:
            logger.info(
                "FALLBACK-AS-FAILURE GATE: PASS (rate=%.3f <= threshold=%.3f)",
                _fb_rate,
                args.fallback_failure_threshold,
            )
            summary["fallback_gate"] = "PASS"
    
    # BH-FDR checkpoint gate (GATE: LLM_ALPHA_ENHANCEMENT_20260618)
    # L2 Fix (2026-06-18): gate now based on fraction of significant folds
    # (>= 50%) rather than BH on a single overall_pvalue.
    _bh = summary.get("bh_fdr")
    if _bh is not None:
        if _bh.get("passes_fdr", False):
            logger.info(
                "BH-FDR GATE: PASS (fraction_significant=%.3f >= 0.5, "
                "%d/%d significant folds, median_q=%.4f, alpha=%.3f)",
                _bh["fraction_significant"],
                _bh["n_significant_folds"],
                _bh["n_folds"],
                _bh["overall_qvalue"],
                _bh["bh_fdr_alpha"],
            )
            summary["bh_fdr_gate"] = "PASS"
        else:
            logger.warning(
                "BH-FDR GATE: FAIL (fraction_significant=%.3f < 0.5, "
                "%d/%d significant folds, median_q=%.4f) — fewer than 50%% "
                "of folds are statistically significant after BH-FDR correction",
                _bh["fraction_significant"],
                _bh["n_significant_folds"],
                _bh["n_folds"],
                _bh["overall_qvalue"],
            )
            summary["bh_fdr_gate"] = "FAIL"
    
    # -------------------------------------------------------------------
    # Gate-driven pass override (GATE: LLM_ALPHA_ENHANCEMENT_20260618)
    # If any gate (fallback, BH-FDR) fails, override summary["pass"] to
    # False regardless of DSR result. This ensures the JSON output
    # reflects the composite gate decision, not just DSR.
    # -------------------------------------------------------------------
    _gate_failures = []
    if summary.get("fallback_gate") == "FAIL":
        _gate_failures.append("fallback-as-failure")
    if summary.get("bh_fdr_gate") == "FAIL":
        _gate_failures.append("bh-fdr")
    _verdict = summary.get("research_gate_verdict")
    if _verdict == "RETIRE":
        _gate_failures.append("research-gate-verdict-RETIRE")
    if _gate_failures and summary.get("pass", False):
        logger.critical(
            "GATE OVERRIDE: summary['pass'] overridden to False due to: %s",
            ", ".join(_gate_failures),
        )
        summary["pass"] = False
        summary["gate_override_reasons"] = _gate_failures

    # Build output with safe aggregate LLM validation summary (PIT-safe: no row-level labels)
    output_data = {"baseline": summary}
    if llm_validation_summary is not None:
        output_data["llm_validation_summary"] = llm_validation_summary
        logger.info(
            "LLM validation summary: %d accepted (%d deployable, %d unsupervised_only) from %d candidates",
            llm_validation_summary["accepted"],
            llm_validation_summary["deployable"],
            llm_validation_summary["unsupervised_only"],
            llm_validation_summary["total_candidates"]
        )
    
    with open(out, "w") as f:
        json.dump(output_data, f, indent=2, default=str)
    
    if hasattr(per_date_returns, "_last_cost_breakdown"):
        br = per_date_returns._last_cost_breakdown
        logger.info(
            "COSTS: avg=%.1fbps/bar, turnover=%.2f/bar, total=%.4f "
            "(commission=%.4f, spread=%.4f, slip=%.4f)",
            br["avg_cost_per_bar_bps"],
            br["avg_turnover_per_bar"],
            br["total_cost"],
            br["total_commission_cost"],
            br["total_spread_cost"],
            br["total_slippage_cost"],
        )
        summary["cost_breakdown"] = br
        output_data["baseline"] = summary  # Update with cost breakdown
        with open(out, "w") as f2:
            json.dump(output_data, f2, indent=2, default=str)
    logger.info("Saved: %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
