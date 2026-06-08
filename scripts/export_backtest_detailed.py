#!/usr/bin/env python3
"""
Export Detailed Backtest Results (REAL DATA)
Generates: portfolio returns, weights time series, trade log, statistics
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from real_data_loader import load_real_vn_data

sys.path.insert(0, 'src')

def _prev_business_day(dt: datetime) -> datetime:
    """Return the previous business day (Mon-Fri) relative to dt."""
    offset = pd.tseries.offsets.BusinessDay(1)
    return (pd.Timestamp(dt) - offset).to_pydatetime()

def generate_vn_data(n_days=252, n_symbols=5):
    """Load REAL VN stock OHLCV data from parquet."""
    symbols = ['VNM', 'VIC', 'HPG', 'TCB', 'BID'][:n_symbols]
    data, loaded_symbols = load_real_vn_data(n_days=n_days, symbols=symbols)
    return data, loaded_symbols

def cap_weights(row, max_w=0.25):
    """Cap weights to max_w and redistribute."""
    w = row.copy()
    n = len(w)
    if n == 0:
        return w
    w = np.maximum(w, 0.0)
    if w.sum() == 0:
        return pd.Series(1.0 / n, index=w.index)
    w = w / w.sum()
    for _ in range(50):
        over = w > max_w
        if not over.any():
            break
        w[over] = max_w
        under = ~over
        if under.any():
            remaining = 1.0 - w[over].sum()
            under_sum = w[under].sum()
            if under_sum > 1e-12:
                w[under] = w[under] * (remaining / under_sum)
            else:
                w[under] = remaining / under.sum()
        else:
            w[:] = 1.0 / n
            break
    w = np.minimum(w, max_w)
    diff = 1.0 - w.sum()
    if abs(diff) > 1e-15:
        under = w < max_w
        if under.any():
            w[under] = w[under] + diff * w[under] / w[under].sum()
            w = np.minimum(w, max_w)
            w = w / w.sum()
    return w

def compute_backtest():
    """Run backtest with AlphaDiscoveryEngine and return detailed results."""
    from alpha_pipeline import run_alpha_pipeline

    print("Generating data...")
    weights, panel, alpha_ics = run_alpha_pipeline(
        n_days=252,
        top_n_liquid=30,
        ic_threshold=0.03,
        top_n_stocks=5,
        rebalance_freq=5,
        min_rebalance_delta=0.05,
    )

    # Extract returns and prices from panel
    returns_df = panel['close'].unstack(level=1).pct_change().fillna(0)
    prices = panel['close'].unstack(level=1)
    symbols = list(weights.columns)

    # Align
    common_idx = returns_df.index.intersection(weights.index)
    returns_df = returns_df.loc[common_idx]
    weights = weights.loc[common_idx].fillna(0)
    prices = prices.loc[common_idx]

    # Portfolio returns (T-1 weights * T returns)
    portfolio_returns = (returns_df * weights.shift(1)).sum(axis=1)
    portfolio_returns = portfolio_returns.replace([np.inf, -np.inf], np.nan).fillna(0)

    # Transaction costs
    SPREAD = 0.001
    daily_turnover = weights.shift(1).diff().abs().sum(axis=1) / 2.0
    daily_cost = SPREAD * daily_turnover
    net_portfolio_returns = portfolio_returns - daily_cost.reindex(portfolio_returns.index).fillna(0)

    return {
        'returns_df': returns_df,
        'weights': weights,
        'portfolio_returns': portfolio_returns,
        'net_portfolio_returns': net_portfolio_returns,
        'daily_turnover': daily_turnover,
        'daily_cost': daily_cost,
        'prices': prices,
        'symbols': symbols
    }

def generate_trade_log(weights, prices):
    """Generate buy/sell trade log including initial setup & per-trade PnL."""
    trades = []
    CAPITAL = 2_000_000_000
    symbols = weights.columns.tolist()
    
    # 1. INITIAL SETUP: From zero position to first day weights
    start_date = weights.index[0]
    w_start = weights.iloc[0]
    
    for sym in symbols:
        weight_target = w_start[sym]
        if weight_target > 0.001:  # Threshold 0.1%
            price = prices.loc[start_date, sym]
            if pd.isna(price) or price <= 0:
                continue
            value_change = weight_target * CAPITAL
            shares = int(value_change / price / 100) * 100  # Board lot
            if shares > 0:
                trades.append({
                    'date': start_date,
                    'symbol': sym,
                    'action': 'INITIAL_BUY',
                    'shares': shares,
                    'price': price,
                    'value': shares * price,
                    'weight_from': 0.0,
                    'weight_to': w_start[sym]
                })
    
    # 2. REBALANCING TRADES
    for i in range(1, len(weights)):
        date = weights.index[i]
        prev_date = weights.index[i-1]
        
        w_prev = weights.iloc[i-1]
        w_curr = weights.iloc[i]
        
        for sym in weights.columns:
            weight_change = w_curr[sym] - w_prev[sym]
            
            if abs(weight_change) > 0.001:  # Threshold 0.1%
                price = prices.loc[date, sym]
                if pd.isna(price) or price <= 0:
                    continue
                value_change = weight_change * CAPITAL
                shares = int(value_change / price / 100) * 100  # Round to board lot
                
                if shares != 0:
                    trades.append({
                        'date': date,
                        'symbol': sym,
                        'action': 'BUY' if shares > 0 else 'SELL',
                        'shares': abs(shares),
                        'price': price,
                        'value': abs(shares * price),
                        'weight_from': w_prev[sym],
                        'weight_to': w_curr[sym]
                    })
    
    df_trades = pd.DataFrame(trades)
    
    # 3. COMPUTE PER-TRADE PnL (mark-to-next-day close)
    pnl_mark = []
    pnl_pct = []
    
    for idx, row in df_trades.iterrows():
        date = row['date']
        sym = row['symbol']
        price = row['price']
        action = row['action']
        shares = row['shares']
        
        # Find next trading day close for this symbol
        sym_prices = prices[sym]
        future_dates = sym_prices.index[sym_prices.index > date]
        
        if len(future_dates) > 0:
            next_date = future_dates[0]
            next_price = sym_prices.loc[next_date]
            if pd.isna(price) or pd.isna(next_price) or price <= 0:
                pnl_val = np.nan
                pnl_p = np.nan
            else:
                # BUY: profit if price rises; SELL: profit if price falls
                if 'BUY' in action:
                    diff = next_price - price
                else:  # SELL
                    diff = price - next_price

                pnl_val = diff * shares
                pnl_p = (diff / price) * 100
        else:
            pnl_val = np.nan
            pnl_p = np.nan
        
        pnl_mark.append(pnl_val)
        pnl_pct.append(pnl_p)
    
    df_trades['pnl_mark_to_next'] = pnl_mark
    df_trades['pnl_pct_to_next'] = pnl_pct
    
    return df_trades

def compute_statistics(results):
    """Compute trading statistics."""
    net_ret = results['net_portfolio_returns']
    turnover = results['daily_turnover']
    
    total_return = (1 + net_ret).prod() - 1
    annual_return = (1 + net_ret.mean()) ** 252 - 1
    annual_vol = net_ret.std() * np.sqrt(252)
    sharpe = (net_ret.mean() / net_ret.std() * np.sqrt(252)) if net_ret.std() > 0 else 0
    
    cum_returns = (1 + net_ret).cumprod()
    running_max = cum_returns.cummax()
    drawdown = (cum_returns - running_max) / running_max
    max_dd = drawdown.min()
    
    avg_turnover = turnover.mean()
    total_cost = results['daily_cost'].sum()
    
    stats = {
        'Total Return (%)': total_return * 100,
        'Annual Return (%)': annual_return * 100,
        'Annual Volatility (%)': annual_vol * 100,
        'Sharpe Ratio': sharpe,
        'Max Drawdown (%)': max_dd * 100,
        'Avg Daily Turnover (%)': avg_turnover * 100,
        'Total Transaction Cost (VND)': total_cost * 2_000_000_000,  # Assuming 2B capital
        'Number of Trading Days': len(net_ret),
    }
    
    return pd.Series(stats)

def main():
    print("=" * 70)
    print("EXPORTING DETAILED BACKTEST RESULTS (V2)")
    print("=" * 70)
    
    # Run backtest
    results = compute_backtest()
    
    # Create output directory
    output_dir = Path('output/backtest_detailed')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Anti-lock: timestamp suffix fallback
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def safe_write(df, base_name, use_index=False):
        """Write CSV with timestamp fallback on lock."""
        path_default = output_dir / f"{base_name}.csv"
        path_ts = output_dir / f"{base_name}_{timestamp_str}.csv"
        try:
            if use_index:
                df.to_csv(path_default)
            else:
                df.to_csv(path_default, index=False)
            print(f"[OK] Exported: {path_default}")
        except PermissionError:
            if use_index:
                df.to_csv(path_ts)
            else:
                df.to_csv(path_ts, index=False)
            print(f"[WARN] {base_name}.csv locked! Exported: {path_ts}")
    
    # Export 1: Portfolio returns
    returns_df = pd.DataFrame({
        'date': results['portfolio_returns'].index,
        'gross_return': results['portfolio_returns'].values,
        'net_return': results['net_portfolio_returns'].values,
        'daily_turnover': results['daily_turnover'].reindex(results['portfolio_returns'].index).fillna(0).values,
        'daily_cost': results['daily_cost'].reindex(results['portfolio_returns'].index).fillna(0).values
    })
    safe_write(returns_df, 'portfolio_returns')
    
    # Export 2: Weights time series
    safe_write(results['weights'], 'weights_timeseries', use_index=True)
    
    # Export 3: Trade log
    trade_log = generate_trade_log(results['weights'], results['prices'])
    safe_write(trade_log, 'trade_log')
    print(f"     Total trades (incl. initial setup): {len(trade_log)}")
    
    # Export 4: Statistics
    stats = compute_statistics(results)
    stats_df = pd.DataFrame(stats).reset_index()
    stats_df.columns = ['Metric', 'Value']
    safe_write(stats_df, 'statistics')
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY STATISTICS")
    print("=" * 70)
    for key, val in stats.items():
        print(f"{key:.<50} {val:>15.2f}")
    
    print("\n" + "=" * 70)
    print(f"All outputs saved to: {output_dir.absolute()}")
    print("=" * 70)

if __name__ == '__main__':
    main()
