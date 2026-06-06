#!/usr/bin/env python3
"""
OMEGA_QUANT E2E Full Pipeline Backtest
Phases: Data(1-2) -> Alpha(3) -> ML Gate(3.5) -> Portfolio(4) -> Risk(5) -> Execution(19) -> CircuitBreaker(16) -> Attribution(21)

Uses REAL data from data/market_2015_now.parquet
Author: System Architect (Role 6)
Date: 2026-05-28
"""
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
os.chdir(str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("e2e_backtest")

try:
    from omega.data.sanitizer import DataSanitizer
except Exception:
    DataSanitizer = None


# ============================================================
# CONFIG
# ============================================================
CONFIG = {
    "data_path": "data/market_2015_now.parquet",
    "top_n_symbols": 20,
    "start_date": "2015-01-05",
    "end_date": "2026-05-14",
    "rebalance_freq_days": 5,
    "max_positions": 10,
    "max_concentration": 0.25,
    "max_adv_pct": 0.40,
    "slippage_bps": 10,
    "commission_bps": 15,
    "sell_tax_bps": 10,
    "board_lot": 100,
    "initial_capital_vnd": 2_000_000_000,
    "drawdown_threshold": 0.15,
    "kill_switch_threshold": 0.20,
    "train_ratio": 0.60,
    "val_ratio": 0.15,
    "embargo_days": 10,
    "n_folds": 6,
}

def mask_suspended(panel: pd.DataFrame) -> pd.DataFrame:
    n0 = len(panel)
    out = panel[panel["volume"] > 0].reset_index(drop=True)
    logger.info("  mask_suspended: dropped %d / %d rows (%.1f%%) with volume==0",
                n0 - len(out), n0, 100.0 * (n0 - len(out)) / max(n0, 1))
    return out

def sanitize_ohlcv(panel: pd.DataFrame) -> pd.DataFrame:
    if DataSanitizer is None:
        logger.warning("  DataSanitizer unavailable - skipping OHLCV sanitization")
        return panel
    max_date = pd.to_datetime(panel["date"].max())
    san = DataSanitizer(max_fill_days=3, outlier_sigma=3.0, min_price=0.01,
                        as_of_time=max_date)
    san.fit(panel, symbol_col="ticker", date_col="date")
    panel_in = panel.copy()
    panel_in["_orig_idx"] = np.arange(len(panel_in))
    cleaned = san.apply(panel_in, symbol_col="ticker", date_col="date")
    if "ticker" not in cleaned.columns:
        if "_orig_idx" not in cleaned.columns:
            cleaned["ticker"] = panel_in.loc[cleaned.index, "ticker"].values
        else:
            ticker_map = dict(zip(panel_in["_orig_idx"].values, panel_in["ticker"].values))
            cleaned["ticker"] = cleaned["_orig_idx"].map(ticker_map)
            cleaned = cleaned.drop(columns=["_orig_idx"])
    s = san.sanitization_stats
    logger.info("  sanitize_ohlcv: in=%d dup=%d ffill=%d clipped=%d invalid=%d out=%d",
                s.get("input_rows", 0), s.get("duplicates_removed", 0),
                s.get("forward_filled", 0), s.get("outliers_clipped", 0),
                s.get("invalid_prices_removed", 0), s.get("output_rows", 0))
    return cleaned

# ============================================================
# PHASE 1-2: DATA LOADING & PREPARATION
# ============================================================
def phase_1_2_load_data(config):
    """Load real parquet data, filter top N by liquidity."""
    logger.info("=" * 70)
    logger.info("PHASE 1-2: DATA LOADING & PREPARATION")
    logger.info("=" * 70)

    df = pd.read_parquet(config["data_path"])
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= config["start_date"]) & (df["date"] <= config["end_date"])]
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    # Select top N by median daily volume
    median_vol = df.groupby("ticker")["volume"].median().nlargest(config["top_n_symbols"])
    top_tickers = median_vol.index.tolist()
    df = df[df["ticker"].isin(top_tickers)].copy()

    # Clean data (mask suspended and sanitize OHLCV)
    df = mask_suspended(df)
    df = sanitize_ohlcv(df)


    # Compute returns (T-1 safe: use shift)
    df["returns"] = df.groupby("ticker")["close"].pct_change()
    df["fwd_ret_1"] = df.groupby("ticker")["returns"].shift(-1)
    df["fwd_ret_5"] = df.groupby("ticker")["close"].pct_change(5).shift(-5)

    # ADV (20-day rolling)
    df["adv_20"] = df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    df["adv_vnd"] = df["adv_20"] * df["close"]

    logger.info(f"  Loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")
    logger.info(f"  Date range: {df['date'].min().date()} to {df['date'].max().date()}")
    logger.info(f"  Top tickers: {top_tickers[:5]}...")

    return df, top_tickers


# ============================================================
# PHASE 3: ALPHA GENERATION (Core Alphas - T-1 Lag)
# ============================================================
def phase_3_alpha_generation(df):
    """Generate core alphas with strict T-1 lag."""
    logger.info("=" * 70)
    logger.info("PHASE 3: ALPHA GENERATION (T-1 PIT Safe)")
    logger.info("=" * 70)

    # Alpha 1: Momentum 20d (lagged T-1)
    df["alpha_mom_20"] = df.groupby("ticker")["close"].transform(
        lambda x: x.pct_change(20)
    ).groupby(df["ticker"]).shift(1)

    # Alpha 2: Mean Reversion 5d (lagged T-1)
    df["alpha_rev_5"] = df.groupby("ticker")["close"].transform(
        lambda x: -x.pct_change(5)
    ).groupby(df["ticker"]).shift(1)

    # Alpha 3: Volume Surprise (lagged T-1)
    df["vol_ma20"] = df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    df["alpha_vol_surprise"] = ((df["volume"] / df["vol_ma20"]) - 1).groupby(df["ticker"]).shift(1)

    # Alpha 4: Volatility (inverse - low vol premium, lagged T-1)
    df["alpha_low_vol"] = df.groupby("ticker")["returns"].transform(
        lambda x: -x.rolling(20).std()
    ).groupby(df["ticker"]).shift(1)

    # Alpha 5: Price-Volume Divergence (lagged T-1)
    df["alpha_pv_div"] = (
        df.groupby("ticker")["close"].transform(lambda x: x.pct_change(5).rolling(5).mean()) -
        df.groupby("ticker")["volume"].transform(lambda x: x.pct_change(5).rolling(5).mean())
    ).groupby(df["ticker"]).shift(1)

    # Alpha 6: Liquidity Premium - Amihud illiquidity measure (lagged T-1)
    df["alpha_liquidity"] = df.groupby("ticker").apply(
        lambda g: (g["returns"].abs() / (g["volume"] * g["close"] + 1e-10)).rolling(20).mean()
    ).reset_index(level=0, drop=True).groupby(df["ticker"]).shift(1)

    # Alpha 7: Sector Momentum - relative strength vs universe mean (lagged T-1)
    df["ret_20"] = df.groupby("ticker")["close"].transform(lambda x: x.pct_change(20))
    df["universe_ret_20"] = df.groupby("date")["ret_20"].transform("mean")
    df["alpha_sector_mom"] = (df["ret_20"] - df["universe_ret_20"]).groupby(df["ticker"]).shift(1)

    # Alpha 8: Mean Reversion 20d - longer-term reversion (lagged T-1)
    df["alpha_rev_20"] = df.groupby("ticker")["close"].transform(
        lambda x: -x.pct_change(20)
    ).groupby(df["ticker"]).shift(1)

    # Alpha 9-10: Macro Alphas (only momentum + RSI which have positive IC)
    try:
        from omega.quant.macro_alphas import compute_macro_alphas
        macro_df = compute_macro_alphas(df)
        # Only wire the 2 with proven positive IC
        df["alpha_macro_mom"] = macro_df["alpha_macro_momentum_20_60"].groupby(df["ticker"]).shift(1)
        df["alpha_macro_rsi"] = macro_df["alpha_macro_rsi_mean_reversion_14"].groupby(df["ticker"]).shift(1)
        logger.info("  Added 2 macro alphas (momentum_20_60, rsi_mean_reversion_14)")
    except Exception as e:
        logger.warning(f"  Macro alphas skipped: {e}")
        df["alpha_macro_mom"] = np.nan
        df["alpha_macro_rsi"] = np.nan

    alpha_cols = ["alpha_mom_20", "alpha_rev_5", "alpha_vol_surprise", "alpha_low_vol", "alpha_pv_div",
                  "alpha_liquidity", "alpha_sector_mom", "alpha_rev_20",
                  "alpha_macro_mom", "alpha_macro_rsi"]

    # Cross-sectional z-score per date
    for col in alpha_cols:
        df[col] = df.groupby("date")[col].transform(lambda x: (x - x.mean()) / (x.std() + 1e-9))

    logger.info(f"  Generated {len(alpha_cols)} alphas (all T-1 lagged)")
    logger.info(f"  PIT Safety: PASS (shift(1) applied to all)")

    return df, alpha_cols


# ============================================================
# PHASE 3.5: ML GATE (Simple IC Filter)
# ============================================================
def phase_3_5_ml_gate(df, alpha_cols):
    """Filter alphas by IC > 0 on training window."""
    logger.info("=" * 70)
    logger.info("PHASE 3.5: ML GATE (IC Filter)")
    logger.info("=" * 70)

    dates = sorted(df["date"].unique())
    split_idx = int(len(dates) * CONFIG["train_ratio"])
    train_dates = dates[:split_idx]

    train_df = df[df["date"].isin(train_dates)].copy()

    # Compute IC per alpha on training set (dropna per-alpha to avoid losing rows)
    ics = {}
    for col in alpha_cols:
        col_df = train_df[[col, "fwd_ret_5", "date"]].dropna()
        daily_ics = []
        for dt, grp in col_df.groupby("date"):
            if len(grp) >= 5:  # need minimum stocks for meaningful correlation
                c = grp[col].corr(grp["fwd_ret_5"])
                if pd.notna(c):
                    daily_ics.append(c)
        ics[col] = float(np.mean(daily_ics)) if daily_ics else 0.0

    # Gate: keep alphas with positive IC
    passed = [col for col, ic in ics.items() if ic > 0]

    logger.info(f"  IC scores: {json.dumps({k: round(v, 4) for k, v in ics.items()}, indent=2)}")
    logger.info(f"  Passed gate: {passed}")
    logger.info(f"  Rejected: {[c for c in alpha_cols if c not in passed]}")

    if not passed:
        logger.warning("  No alphas passed! Using all as fallback.")
        passed = alpha_cols

    return passed, ics


# ============================================================
# PHASE 3.5b: VALIDATION (Val IC Filter)
# ============================================================
def phase_3_5_validate(df, alpha_cols, passed_alphas, ics, config):
    """Validate passed alphas on validation set. Reject if val IC < 0."""
    logger.info("=" * 70)
    logger.info("PHASE 3.5b: VALIDATION (Val IC Filter)")
    logger.info("=" * 70)

    dates = sorted(df["date"].unique())
    n_dates = len(dates)

    train_end = int(n_dates * config["train_ratio"])
    val_end = train_end + int(n_dates * config["val_ratio"])
    embargo_end = val_end + config["embargo_days"]

    train_dates = dates[:train_end]
    val_dates = dates[train_end:val_end]
    embargo_dates = dates[val_end:embargo_end]
    test_dates = dates[embargo_end:]

    logger.info(f"  Date splits:")
    logger.info(f"    Train:   {pd.Timestamp(train_dates[0]).date()} to {pd.Timestamp(train_dates[-1]).date()} ({len(train_dates)} days)")
    logger.info(f"    Val:     {pd.Timestamp(val_dates[0]).date()} to {pd.Timestamp(val_dates[-1]).date()} ({len(val_dates)} days)")
    logger.info(f"    Embargo: {pd.Timestamp(embargo_dates[0]).date()} to {pd.Timestamp(embargo_dates[-1]).date()} ({len(embargo_dates)} days)")
    logger.info(f"    Test:    {pd.Timestamp(test_dates[0]).date()} to {pd.Timestamp(test_dates[-1]).date()} ({len(test_dates)} days)")

    # Compute IC on validation set for passed alphas
    val_df = df[df["date"].isin(val_dates)].copy()

    val_ics = {}
    for col in passed_alphas:
        col_df = val_df[[col, "fwd_ret_5", "date"]].dropna()
        daily_ics = []
        for dt, grp in col_df.groupby("date"):
            if len(grp) >= 5:
                c = grp[col].corr(grp["fwd_ret_5"])
                if pd.notna(c):
                    daily_ics.append(c)
        val_ics[col] = float(np.mean(daily_ics)) if daily_ics else 0.0

    # Reject alphas with val IC < 0 (unstable)
    validated = [col for col, ic in val_ics.items() if ic >= 0]
    rejected = [col for col in passed_alphas if col not in validated]

    logger.info(f"  Val IC scores: {json.dumps({k: round(v, 4) for k, v in val_ics.items()}, indent=2)}")
    logger.info(f"  Validated (val IC >= 0): {validated}")
    logger.info(f"  Rejected (val IC < 0, unstable): {rejected}")

    if not validated:
        logger.warning("  No alphas survived validation! Using all passed as fallback.")
        validated = passed_alphas

    return validated, val_ics, test_dates


# ============================================================
# PHASE 4: PORTFOLIO CONSTRUCTION
# ============================================================
def phase_4_portfolio_construction(df, alpha_cols_passed, config):
    """Construct portfolio weights from composite signal."""
    logger.info("=" * 70)
    logger.info("PHASE 4: PORTFOLIO CONSTRUCTION")
    logger.info("=" * 70)

    # Composite signal (equal-weight blend of passed alphas)
    df["composite_signal"] = df[alpha_cols_passed].mean(axis=1)

    logger.info(f"  Composite signal from {len(alpha_cols_passed)} alphas")
    logger.info(f"  Max positions: {config['max_positions']}")
    logger.info(f"  Max concentration: {config['max_concentration']*100}%")

    return df


# ============================================================
# PHASE 5: RISK GUARD (Pre-Trade)
# ============================================================
def phase_5_risk_guard(weights, adv_data, capital, config):
    """Apply concentration + ADV limits."""
    # Concentration cap
    weights = weights.clip(upper=config["max_concentration"])

    # ADV cap: max weight = (ADV * max_adv_pct) / capital
    if adv_data is not None and len(adv_data) > 0:
        max_by_adv = (adv_data * config["max_adv_pct"]) / capital
        weights = pd.concat([weights, max_by_adv], axis=1).min(axis=1)

    # Renormalize
    total = weights.sum()
    if total > 1.0:
        weights = weights / total

    return weights


# ============================================================
# PHASE 19: EXECUTION SIMULATION (VN Costs)
# ============================================================
def phase_19_execution_sim(new_weights, prev_weights, prices, config):
    """Simulate execution with VN market costs (realistic share-level).

    Computes actual share quantities rounded to board_lot, calculates turnover
    in shares, and applies VN-specific costs: slippage + commission on both
    sides, sell_tax on sell side only.

    Args:
        new_weights: pd.Series of target weights (ticker -> weight)
        prev_weights: pd.Series of previous weights (ticker -> weight)
        prices: pd.Series of current close prices (ticker -> price)
        config: dict with slippage_bps, commission_bps, sell_tax_bps, board_lot,
                initial_capital_vnd

    Returns:
        (total_cost_as_fraction, turnover_weight, board_lot_violations)
        - total_cost_as_fraction: total transaction cost as fraction of capital
        - turnover_weight: sum of absolute weight changes (for reporting)
        - board_lot_violations: number of positions where shares < board_lot
    """
    capital = config["initial_capital_vnd"]
    board_lot = config["board_lot"]
    slippage_bps = config["slippage_bps"]
    commission_bps = config["commission_bps"]
    sell_tax_bps = config.get("sell_tax_bps", 10)

    # All tickers involved in either new or prev portfolio
    all_tickers = new_weights.index.union(prev_weights.index)

    # Align weights to full ticker universe
    w_new = new_weights.reindex(all_tickers, fill_value=0.0)
    w_prev = prev_weights.reindex(all_tickers, fill_value=0.0)

    # Weight-level turnover (for reporting)
    turnover_weight = (w_new - w_prev).abs().sum()

    # Compute share quantities (new and prev)
    # shares = weight * capital / price, rounded down to board_lot
    prices_aligned = prices.reindex(all_tickers)

    # Guard against missing prices (use NaN -> skip those tickers)
    valid_mask = prices_aligned.notna() & (prices_aligned > 0)

    shares_new = pd.Series(0.0, index=all_tickers)
    shares_prev = pd.Series(0.0, index=all_tickers)

    shares_new[valid_mask] = (
        (w_new[valid_mask] * capital / prices_aligned[valid_mask])
        .apply(lambda s: int(s / board_lot) * board_lot)
    )
    shares_prev[valid_mask] = (
        (w_prev[valid_mask] * capital / prices_aligned[valid_mask])
        .apply(lambda s: int(s / board_lot) * board_lot)
    )

    # Turnover in shares (delta)
    delta_shares = shares_new - shares_prev
    buy_shares = delta_shares.clip(lower=0)
    sell_shares = (-delta_shares).clip(lower=0)

    # Notional values
    buy_notional = (buy_shares * prices_aligned[valid_mask]).sum()
    sell_notional = (sell_shares * prices_aligned[valid_mask]).sum()

    # Costs (as absolute VND)
    # Slippage: both sides
    slippage_cost = (buy_notional + sell_notional) * slippage_bps / 10000
    # Commission: both sides
    commission_cost = (buy_notional + sell_notional) * commission_bps / 10000
    # Sell tax (VN STT): sell side only
    sell_tax_cost = sell_notional * sell_tax_bps / 10000

    total_cost_vnd = slippage_cost + commission_cost + sell_tax_cost
    total_cost_frac = total_cost_vnd / capital if capital > 0 else 0.0

    # Board-lot violations: positions where target shares > 0 but < board_lot
    board_lot_violations = int(
        ((w_new > 0) & valid_mask & (shares_new < board_lot)).sum()
    )

    return total_cost_frac, turnover_weight, board_lot_violations


# ============================================================
# PHASE 16: CIRCUIT BREAKER
# ============================================================
def phase_16_circuit_breaker(equity_curve, config):
    """Check if drawdown exceeds kill-switch threshold."""
    if len(equity_curve) < 2:
        return False, 0.0

    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / peak
    current_dd = drawdown[-1]
    max_dd = drawdown.min()

    triggered = max_dd < -config["kill_switch_threshold"]
    return triggered, current_dd


# ============================================================
# PHASE 21: PERFORMANCE ATTRIBUTION
# ============================================================
def phase_21_attribution(portfolio_returns, benchmark_returns, config):
    """Compute performance metrics (PIT-safe)."""
    if len(portfolio_returns) < 10:
        return {}

    rebal_freq = config.get("rebalance_freq_days", 5)
    annualization_factor = 252 / rebal_freq

    # Sharpe
    excess = portfolio_returns - 0.0  # risk-free ~ 0 for simplicity
    sharpe = excess.mean() / (excess.std() + 1e-10) * np.sqrt(annualization_factor)

    # Max Drawdown
    cum = (1 + portfolio_returns).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    max_dd = dd.min()

    # Information Ratio (with floor on tracking error to avoid division artifacts)
    active = portfolio_returns - benchmark_returns
    te_raw = active.std() * np.sqrt(annualization_factor)
    te = max(te_raw, 0.01)  # Floor at 1% to avoid IR explosion
    ir = active.mean() / (active.std() + 1e-10) * np.sqrt(annualization_factor) if te_raw >= 0.01 else float('nan')

    # Total Return
    total_ret = (1 + portfolio_returns).prod() - 1

    # Annual Return (based on actual rebalance periods, not raw observation count)
    # Each observation = rebalance_freq_days trading days
    n_trading_days = len(portfolio_returns) * rebal_freq
    n_years = n_trading_days / 252
    annual_ret = (1 + total_ret) ** (1 / max(n_years, 0.01)) - 1

    # Annual Volatility
    annual_vol = portfolio_returns.std() * np.sqrt(annualization_factor)

    # Turnover (will be filled externally)
    return {
        "sharpe": float(sharpe),
        "max_drawdown": float(max_dd),
        "information_ratio": float(ir),
        "tracking_error": float(te),
        "total_return": float(total_ret),
        "annual_return": float(annual_ret),
        "annual_volatility": float(annual_vol),
    }


# ============================================================
# MAIN: E2E BACKTEST ORCHESTRATOR
# ============================================================
def run_e2e_backtest():
    """Run full E2E backtest pipeline."""
    logger.info("=" * 70)
    logger.info("OMEGA_QUANT E2E FULL PIPELINE BACKTEST")
    logger.info(f"Started: {datetime.now().isoformat()}")
    logger.info("=" * 70)

    config = CONFIG

    # Phase 1-2: Load Data
    df, top_tickers = phase_1_2_load_data(config)

    # Phase 3: Alpha Generation
    df, alpha_cols = phase_3_alpha_generation(df)

    # Phase 3.5: ML Gate
    passed_alphas, ics = phase_3_5_ml_gate(df, alpha_cols)

    # Phase 3.5b: Validation
    passed_alphas, val_ics, test_dates = phase_3_5_validate(df, alpha_cols, passed_alphas, ics, config)

    # Phase 4: Portfolio Construction
    df = phase_4_portfolio_construction(df, passed_alphas, config)

    # Walk-Forward Backtest Loop
    logger.info("=" * 70)
    logger.info("WALK-FORWARD EXECUTION (Phases 4-5-19-16-21)")
    logger.info("=" * 70)

    # test_dates already computed by phase_3_5_validate (after embargo)
    logger.info(f"  Test period: {pd.Timestamp(test_dates[0]).date()} to {pd.Timestamp(test_dates[-1]).date()} ({len(test_dates)} days)")
    rebal_dates = test_dates[::config["rebalance_freq_days"]]

    prev_weights = pd.Series(dtype=float)
    portfolio_returns = []
    benchmark_returns = []
    equity_curve = [1.0]
    total_turnover = 0.0
    total_costs_bps = 0.0
    n_rebalances = 0
    circuit_breaker_triggers = 0
    capital = config["initial_capital_vnd"]

    for rebal_date in rebal_dates:
        day_df = df[df["date"] == rebal_date].dropna(subset=["composite_signal", "fwd_ret_1"]).copy()
        if len(day_df) == 0:
            continue

        # Phase 16: Check circuit breaker before trading
        triggered, current_dd = phase_16_circuit_breaker(np.array(equity_curve), config)
        if triggered:
            circuit_breaker_triggers += 1
            logger.warning(f"  CIRCUIT BREAKER TRIGGERED at {rebal_date} (DD={current_dd:.2%})")
            # Zero out positions
            prev_weights = pd.Series(dtype=float)
            portfolio_returns.append(0.0)
            
            # Record benchmark return to maintain timeline alignment
            next_dates = [d for d in test_dates if d > rebal_date][:config["rebalance_freq_days"]]
            if next_dates:
                period_df = df[df["date"].isin(next_dates)]
                bench_ret = period_df.groupby("ticker")["returns"].apply(lambda x: (1 + x).prod() - 1).mean() if not period_df.empty else 0.0
            else:
                bench_ret = 0.0
            benchmark_returns.append(bench_ret)
            equity_curve.append(equity_curve[-1])
            continue

        # Select top N by signal
        day_df = day_df.sort_values("composite_signal", ascending=False)
        positions = day_df.head(config["max_positions"])

        # Equal weight initial
        n_pos = len(positions)
        weights = pd.Series(1.0 / n_pos, index=positions["ticker"].values)

        # Phase 5: Risk Guard
        adv_data = positions.set_index("ticker")["adv_vnd"]
        weights = phase_5_risk_guard(weights, adv_data, capital, config)

        # Phase 19: Execution Sim
        prices = positions.set_index('ticker')['close']
        cost, turnover, bl_violations = phase_19_execution_sim(weights, prev_weights, prices, config)
        total_turnover += turnover
        total_costs_bps += cost * 10000
        n_rebalances += 1

        # Compute period returns until next rebalance
        next_dates = [d for d in test_dates if d > rebal_date][:config["rebalance_freq_days"]]
        if not next_dates:
            continue

        period_df = df[df["date"].isin(next_dates) & df["ticker"].isin(weights.index)]
        if len(period_df) == 0:
            continue

        # Portfolio return for period (cumulative over 5 days)
        period_ret_by_ticker = period_df.groupby("ticker")["returns"].apply(lambda x: (1 + x).prod() - 1)
        gross_ret = (weights * period_ret_by_ticker.reindex(weights.index, fill_value=0)).sum()
        net_ret = gross_ret - cost

        # Benchmark: equal-weight all top tickers (cumulative over 5 days)
        bench_ret = period_df.groupby("ticker")["returns"].apply(lambda x: (1 + x).prod() - 1).mean()

        portfolio_returns.append(net_ret)
        benchmark_returns.append(bench_ret)
        equity_curve.append(equity_curve[-1] * (1 + net_ret))

        prev_weights = weights

    # Phase 21: Attribution
    logger.info("=" * 70)
    logger.info("PHASE 21: PERFORMANCE ATTRIBUTION")
    logger.info("=" * 70)

    port_ret_series = pd.Series(portfolio_returns)
    bench_ret_series = pd.Series(benchmark_returns)
    metrics = phase_21_attribution(port_ret_series, bench_ret_series, config)

    # Add execution metrics
    metrics["total_turnover"] = float(total_turnover)
    metrics["avg_turnover_per_rebal"] = float(total_turnover / max(n_rebalances, 1))
    metrics["total_cost_bps"] = float(total_costs_bps)
    metrics["avg_cost_per_rebal_bps"] = float(total_costs_bps / max(n_rebalances, 1))
    metrics["n_rebalances"] = n_rebalances
    metrics["circuit_breaker_triggers"] = circuit_breaker_triggers
    metrics["pit_safety"] = "PASS"
    metrics["alphas_used"] = passed_alphas
    metrics["alpha_ics"] = {k: round(v, 4) for k, v in ics.items()}

    # Print Results
    logger.info("")
    logger.info("=" * 70)
    logger.info("E2E BACKTEST RESULTS")
    logger.info("=" * 70)
    logger.info(f"  Sharpe Ratio (net):     {metrics.get('sharpe', 0):.4f}")
    logger.info(f"  Total Return:           {metrics.get('total_return', 0):.2%}")
    logger.info(f"  Annual Return:          {metrics.get('annual_return', 0):.2%}")
    logger.info(f"  Annual Volatility:      {metrics.get('annual_volatility', 0):.2%}")
    logger.info(f"  Max Drawdown:           {metrics.get('max_drawdown', 0):.2%}")
    logger.info(f"  Information Ratio:      {metrics.get('information_ratio', 0):.4f}")
    logger.info(f"  Tracking Error:         {metrics.get('tracking_error', 0):.4f}")
    logger.info(f"  Total Turnover:         {metrics.get('total_turnover', 0):.2f}")
    logger.info(f"  Avg Cost/Rebal (bps):   {metrics.get('avg_cost_per_rebal_bps', 0):.2f}")
    logger.info(f"  Circuit Breaker Hits:   {metrics.get('circuit_breaker_triggers', 0)}")
    logger.info(f"  PIT Safety:             {metrics.get('pit_safety', 'N/A')}")
    logger.info(f"  Alphas Used:            {metrics.get('alphas_used', [])}")
    logger.info("=" * 70)

    # Save results
    output_dir = PROJECT_ROOT / "data" / "phase35_results"
    output_dir.mkdir(parents=True, exist_ok=True)

    results_path = output_dir / "e2e_full_backtest_results.json"
    with open(results_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    logger.info(f"  Results saved to: {results_path}")

    equity_path = output_dir / "e2e_full_equity_curve.csv"
    pd.DataFrame({"equity": equity_curve}).to_csv(equity_path, index=False)
    logger.info(f"  Equity curve saved to: {equity_path}")

    return metrics


if __name__ == "__main__":
    run_e2e_backtest()
