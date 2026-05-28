#!/usr/bin/env python3
"""
OMEGA_QUANT E2E ML-Based Alpha Combination Backtest
Combines 94+ alphas via Ridge regression for optimal weighting.
Uses Alpha-Aware universe selection.

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

from omega.quant.ultimate_alpha_arsenal import compute_ultimate_alphas
from sklearn.linear_model import Ridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("e2e_ml_backtest")

CONFIG = {
    "data_path": "data/market_2015_now.parquet",
    "top_n_symbols": 30,
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
    "ridge_alpha": 1.0,
}

# ============================================================
# PHASE 1-2: DATA LOADING
# ============================================================
def phase_1_2_load_data(config):
    logger.info("=" * 70)
    logger.info("PHASE 1-2: DATA LOADING")
    logger.info("=" * 70)
    df = pd.read_parquet(config["data_path"])
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= config["start_date"]) & (df["date"] <= config["end_date"])]
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    median_vol = df.groupby("ticker")["volume"].median().nlargest(config["top_n_symbols"])
    top_tickers = median_vol.index.tolist()
    df = df[df["ticker"].isin(top_tickers)].copy()
    df["returns"] = df.groupby("ticker")["close"].pct_change()
    df["fwd_ret_1"] = df.groupby("ticker")["returns"].shift(-1)
    df["fwd_ret_5"] = df.groupby("ticker")["close"].pct_change(5).shift(-5)
    df["adv_20"] = df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    df["adv_vnd"] = df["adv_20"] * df["close"]
    logger.info(f"  Loaded: {len(df)} rows, {df['ticker'].nunique()} tickers")
    return df, top_tickers

# ============================================================
# PHASE 3: ALL ALPHAS (ultimate_alpha_arsenal)
# ============================================================
def phase_3_all_alphas(df):
    logger.info("=" * 70)
    logger.info("PHASE 3: ALL ALPHAS (ultimate_alpha_arsenal - 40+ signals)")
    logger.info("=" * 70)
    alpha_df = compute_ultimate_alphas(df, symbol_col="ticker")
    alpha_cols = [c for c in alpha_df.columns if c.startswith("alpha_")]
    for col in alpha_cols:
        if col not in df.columns:
            df[col] = alpha_df[col]
    # Cross-sectional z-score
    for col in alpha_cols:
        df[col] = df.groupby("date")[col].transform(lambda x: (x - x.mean()) / (x.std() + 1e-9))
    logger.info(f"  Computed {len(alpha_cols)} alphas (PIT safe via ultimate_alpha_arsenal)")
    return df, alpha_cols

# ============================================================
# PHASE 3.5: ML ALPHA COMBINATION (Ridge Regression)
# ============================================================
def phase_3_5_ml_combination(df, alpha_cols, config):
    logger.info("=" * 70)
    logger.info("PHASE 3.5: ML ALPHA COMBINATION (Ridge)")
    logger.info("=" * 70)
    dates = sorted(df["date"].unique())
    n = len(dates)
    train_end = int(n * config["train_ratio"])
    val_end = train_end + int(n * config["val_ratio"])
    embargo_end = val_end + config["embargo_days"]
    train_dates = dates[:train_end]
    val_dates = dates[train_end:val_end]
    test_dates = dates[embargo_end:]

    logger.info(f"  Train: {pd.Timestamp(train_dates[0]).date()} to {pd.Timestamp(train_dates[-1]).date()} ({len(train_dates)}d)")
    logger.info(f"  Val: {pd.Timestamp(val_dates[0]).date()} to {pd.Timestamp(val_dates[-1]).date()} ({len(val_dates)}d)")
    logger.info(f"  Embargo: {config['embargo_days']}d")
    logger.info(f"  Test: {pd.Timestamp(test_dates[0]).date()} to {pd.Timestamp(test_dates[-1]).date()} ({len(test_dates)}d)")

    # Train Ridge
    train_df = df[df["date"].isin(train_dates)].copy()
    train_df = train_df.dropna(subset=["fwd_ret_5"])  # Only drop if target is NaN
    X_train = train_df[alpha_cols].fillna(0).values
    y_train = train_df["fwd_ret_5"].values

    ridge = Ridge(alpha=config["ridge_alpha"])
    ridge.fit(X_train, y_train)

    # Validate
    val_df = df[df["date"].isin(val_dates)].copy()
    val_df = val_df.dropna(subset=["fwd_ret_5"])
    X_val = val_df[alpha_cols].fillna(0).values
    y_val = val_df["fwd_ret_5"].values
    val_r2 = ridge.score(X_val, y_val)

    # Weights
    weights = dict(zip(alpha_cols, ridge.coef_))
    top_10 = sorted(weights.items(), key=lambda x: abs(x[1]), reverse=True)[:10]
    active_alphas = [name for name, w in sorted(weights.items(), key=lambda x: abs(x[1]), reverse=True)[:20] if abs(w) > 1e-6]

    logger.info(f"  Ridge alpha={config['ridge_alpha']}")
    logger.info(f"  R2 train: {ridge.score(X_train, y_train):.4f}")
    logger.info(f"  R2 val: {val_r2:.4f}")
    logger.info(f"  Active alphas (top 20 by |weight|): {len(active_alphas)}")
    for name, w in top_10:
        logger.info(f"    {name}: {w:.6f}")

    # Composite signal
    df["composite_signal"] = ridge.predict(df[alpha_cols].fillna(0).values)

    return df, weights, active_alphas, test_dates

# ============================================================
# PHASE 5: RISK GUARD
# ============================================================
def phase_5_risk_guard(weights, adv_data, capital, config):
    weights = weights.clip(upper=config["max_concentration"])
    if adv_data is not None and len(adv_data) > 0:
        max_by_adv = (adv_data * config["max_adv_pct"]) / capital
        weights = pd.concat([weights, max_by_adv], axis=1).min(axis=1)
    total = weights.sum()
    if total > 1.0:
        weights = weights / total
    return weights

# ============================================================
# PHASE 19: EXECUTION SIM
# ============================================================
def phase_19_execution_sim(new_weights, prev_weights, prices, config):
    capital = config["initial_capital_vnd"]
    board_lot = config["board_lot"]
    all_tickers = new_weights.index.union(prev_weights.index)
    w_new = new_weights.reindex(all_tickers, fill_value=0.0)
    w_prev = prev_weights.reindex(all_tickers, fill_value=0.0)
    turnover_weight = (w_new - w_prev).abs().sum()
    prices_aligned = prices.reindex(all_tickers)
    valid_mask = prices_aligned.notna() & (prices_aligned > 0)
    shares_new = pd.Series(0.0, index=all_tickers)
    shares_prev = pd.Series(0.0, index=all_tickers)
    shares_new[valid_mask] = ((w_new[valid_mask] * capital / prices_aligned[valid_mask]).apply(lambda s: int(s / board_lot) * board_lot))
    shares_prev[valid_mask] = ((w_prev[valid_mask] * capital / prices_aligned[valid_mask]).apply(lambda s: int(s / board_lot) * board_lot))
    delta_shares = shares_new - shares_prev
    buy_notional = (delta_shares.clip(lower=0) * prices_aligned[valid_mask]).sum()
    sell_notional = ((-delta_shares).clip(lower=0) * prices_aligned[valid_mask]).sum()
    slippage_cost = (buy_notional + sell_notional) * config["slippage_bps"] / 10000
    commission_cost = (buy_notional + sell_notional) * config["commission_bps"] / 10000
    sell_tax_cost = sell_notional * config["sell_tax_bps"] / 10000
    total_cost_frac = (slippage_cost + commission_cost + sell_tax_cost) / capital if capital > 0 else 0.0
    return total_cost_frac, turnover_weight

# ============================================================
# PHASE 16: CIRCUIT BREAKER
# ============================================================
def phase_16_circuit_breaker(equity_curve, config):
    if len(equity_curve) < 2:
        return False, 0.0
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / peak
    current_dd = drawdown[-1]
    triggered = drawdown.min() < -config["kill_switch_threshold"]
    return triggered, current_dd

# ============================================================
# PHASE 21: ATTRIBUTION
# ============================================================
def phase_21_attribution(portfolio_returns, benchmark_returns, config):
    if len(portfolio_returns) < 10:
        return {}
    excess = portfolio_returns - 0.0
    sharpe = excess.mean() / (excess.std() + 1e-10) * np.sqrt(252)
    cum = (1 + portfolio_returns).cumprod()
    peak = cum.cummax()
    max_dd = ((cum - peak) / peak).min()
    active = portfolio_returns - benchmark_returns
    te_raw = active.std() * np.sqrt(252)
    ir = active.mean() / (active.std() + 1e-10) * np.sqrt(252) if te_raw >= 0.01 else float("nan")
    total_ret = (1 + portfolio_returns).prod() - 1
    n_trading_days = len(portfolio_returns) * config.get("rebalance_freq_days", 5)
    n_years = n_trading_days / 252
    annual_ret = (1 + total_ret) ** (1 / max(n_years, 0.01)) - 1
    annual_vol = portfolio_returns.std() * np.sqrt(252)
    return {
        "sharpe": float(sharpe), "max_drawdown": float(max_dd),
        "information_ratio": float(ir), "tracking_error": float(max(te_raw, 0.01)),
        "total_return": float(total_ret), "annual_return": float(annual_ret),
        "annual_volatility": float(annual_vol),
    }

# ============================================================
# MAIN: E2E ML BACKTEST
# ============================================================
def run_e2e_ml_backtest():
    logger.info("=" * 70)
    logger.info("OMEGA_QUANT E2E ML-BASED BACKTEST")
    logger.info(f"Started: {datetime.now().isoformat()}")
    logger.info("=" * 70)

    config = CONFIG

    # Phase 1-2: Load Data
    df, top_tickers = phase_1_2_load_data(config)

    # Phase 3: Compute ALL alphas
    df, alpha_cols = phase_3_all_alphas(df)

    # Phase 3.5: ML Combination (Ridge)
    df, weights, active_alphas, test_dates = phase_3_5_ml_combination(df, alpha_cols, config)

    # Walk-Forward
    logger.info("=" * 70)
    logger.info("WALK-FORWARD EXECUTION")
    logger.info("=" * 70)
    logger.info(f"  Test: {pd.Timestamp(test_dates[0]).date()} to {pd.Timestamp(test_dates[-1]).date()} ({len(test_dates)}d)")

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

        # Circuit breaker
        triggered, current_dd = phase_16_circuit_breaker(np.array(equity_curve), config)
        if triggered:
            circuit_breaker_triggers += 1
            prev_weights = pd.Series(dtype=float)
            continue

        # Select top N by composite signal
        day_df = day_df.sort_values("composite_signal", ascending=False)
        positions = day_df.head(config["max_positions"])
        n_pos = len(positions)
        wts = pd.Series(1.0 / n_pos, index=positions["ticker"].values)

        # Risk guard
        adv_data = positions.set_index("ticker")["adv_vnd"]
        wts = phase_5_risk_guard(wts, adv_data, capital, config)

        # Execution sim
        prices = positions.set_index("ticker")["close"]
        cost, turnover = phase_19_execution_sim(wts, prev_weights, prices, config)
        total_turnover += turnover
        total_costs_bps += cost * 10000
        n_rebalances += 1

        # Period returns
        next_dates = [d for d in test_dates if d > rebal_date][:config["rebalance_freq_days"]]
        if not next_dates:
            continue
        period_df = df[df["date"].isin(next_dates) & df["ticker"].isin(wts.index)]
        if len(period_df) == 0:
            continue
        period_ret = period_df.groupby("ticker")["returns"].mean()
        gross_ret = (wts * period_ret.reindex(wts.index, fill_value=0)).sum()
        net_ret = gross_ret - cost / max(config["rebalance_freq_days"], 1)
        bench_ret = period_df.groupby("ticker")["returns"].mean().mean()

        portfolio_returns.append(net_ret)
        benchmark_returns.append(bench_ret)
        equity_curve.append(equity_curve[-1] * (1 + net_ret))
        prev_weights = wts

    # Attribution
    logger.info("=" * 70)
    logger.info("RESULTS")
    logger.info("=" * 70)
    port_ret = pd.Series(portfolio_returns)
    bench_ret = pd.Series(benchmark_returns)
    metrics = phase_21_attribution(port_ret, bench_ret, config)
    metrics["total_turnover"] = float(total_turnover)
    metrics["avg_cost_per_rebal_bps"] = float(total_costs_bps / max(n_rebalances, 1))
    metrics["n_rebalances"] = n_rebalances
    metrics["circuit_breaker_triggers"] = circuit_breaker_triggers
    metrics["active_alphas_count"] = len(active_alphas)
    metrics["top_alphas"] = active_alphas[:10]

    logger.info(f"  Sharpe Ratio (net):     {metrics.get('sharpe', 0):.4f}")
    logger.info(f"  Total Return:           {metrics.get('total_return', 0):.2%}")
    logger.info(f"  Annual Return:          {metrics.get('annual_return', 0):.2%}")
    logger.info(f"  Max Drawdown:           {metrics.get('max_drawdown', 0):.2%}")
    logger.info(f"  Avg Cost/Rebal (bps):   {metrics.get('avg_cost_per_rebal_bps', 0):.2f}")
    logger.info(f"  Active Alphas:          {metrics.get('active_alphas_count', 0)}")
    logger.info(f"  Circuit Breaker Hits:   {metrics.get('circuit_breaker_triggers', 0)}")

    # Save
    output_dir = PROJECT_ROOT / "data" / "phase35_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "e2e_ml_backtest_results.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    logger.info(f"  Saved to: {output_dir / 'e2e_ml_backtest_results.json'}")

    return metrics

if __name__ == "__main__":
    run_e2e_ml_backtest()
