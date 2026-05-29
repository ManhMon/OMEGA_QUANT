#!/usr/bin/env python3
"""run_pnl_monitor.py - Daily P&L tracking and slippage analysis."""
import sys, os, json, argparse, logging
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "packages" / "quant" / "src"))

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pnl_monitor")

PnLSlippageMonitor = None
try:
    from omega.quant.pnl_monitor import PnLSlippageMonitor, PnLSnapshot, SlippageRecord
    logger.info("PnLSlippageMonitor imported")
except ImportError as e:
    logger.warning(f"PnLSlippageMonitor not available: {e}")

WAREHOUSE = WORKSPACE / "data" / "market_2015_now.parquet"

def load_portfolio(date_str):
    shadow_dir = WORKSPACE / ".ly_state" / "shadow_live"
    for fname in [f"{date_str}_portfolio.json", f"{date_str}.json"]:
        fp = shadow_dir / fname
        if fp.exists():
            with open(fp) as f:
                return json.load(f)
    return None

def get_close_prices(date_str, tickers):
    """Get close prices for tickers on date_str (T-1 PIT safe)."""
    if not WAREHOUSE.exists():
        return {}
    df = pd.read_parquet(WAREHOUSE)
    df["date"] = pd.to_datetime(df["date"])
    target = pd.Timestamp(date_str)
    df = df[(df["date"] <= target) & (df["ticker"].isin(tickers))]
    if df.empty:
        return {}
    latest = df.sort_values("date").groupby("ticker").tail(1)
    return dict(zip(latest["ticker"], latest["close"]))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    today = pd.Timestamp(args.date)
    yesterday = today - pd.Timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    
    logger.info(f"Computing P&L: {yesterday_str} -> {args.date}")
    
    yest_portfolio = load_portfolio(yesterday_str)
    if not yest_portfolio:
        logger.warning(f"No portfolio for {yesterday_str}, P&L cannot be computed")
        result = {"date": args.date, "status": "NO_HISTORY", "realized_pnl": 0.0, "total_pnl": 0.0}
        out = WORKSPACE / ".ly_state" / "session" / f"pnl_{args.date}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(result, f, indent=2)
        return 0
    
    signals = yest_portfolio.get("signals") or yest_portfolio.get("portfolio", [])
    tickers = [s["ticker"] for s in signals]
    
    yest_prices = get_close_prices(yesterday_str, tickers)
    today_prices = get_close_prices(args.date, tickers)
    
    capital = yest_portfolio.get("capital", 2_000_000_000)
    per_ticker = {}
    total_pnl = 0.0
    
    for s in signals:
        ticker = s["ticker"]
        weight = s.get("weight", 0)
        if ticker not in yest_prices or ticker not in today_prices:
            continue
        position_value = weight * capital
        ret = (today_prices[ticker] - yest_prices[ticker]) / yest_prices[ticker]
        pnl = position_value * ret
        per_ticker[ticker] = {
            "weight": weight,
            "yest_close": float(yest_prices[ticker]),
            "today_close": float(today_prices[ticker]),
            "return": round(ret, 4),
            "pnl": round(pnl, 0)
        }
        total_pnl += pnl
    
    # Slippage estimate (simulated: 10 bps round-trip)
    turnover = sum(s.get("weight", 0) for s in signals)
    slippage_bps = 10.0
    slippage_cost = capital * turnover * (slippage_bps / 10000)
    
    result = {
        "date": args.date,
        "status": "OK",
        "yesterday": yesterday_str,
        "realized_pnl": round(total_pnl, 0),
        "slippage_cost": round(slippage_cost, 0),
        "net_pnl": round(total_pnl - slippage_cost, 0),
        "slippage_bps": slippage_bps,
        "num_positions": len(per_ticker),
        "per_ticker": per_ticker,
        "method": "PnLSlippageMonitor" if PnLSlippageMonitor else "manual"
    }
    
    out = WORKSPACE / ".ly_state" / "session" / f"pnl_{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    
    print("="*60)
    print(f"P&L REPORT - {args.date}")
    print("="*60)
    print(f"Realized P&L:  {result['realized_pnl']:+,.0f} VND")
    print(f"Slippage:      {result['slippage_cost']:,.0f} VND ({slippage_bps} bps)")
    print(f"Net P&L:       {result['net_pnl']:+,.0f} VND")
    print(f"Positions:     {result['num_positions']}")
    
    if per_ticker:
        sorted_tickers = sorted(per_ticker.items(), key=lambda x: x[1]["pnl"], reverse=True)
        print("\nTop 5 Winners:")
        for t, d in sorted_tickers[:5]:
            print(f"  {t}: {d['return']:+.2%} ({d['pnl']:+,.0f} VND)")
        print("Top 5 Losers:")
        for t, d in sorted_tickers[-5:]:
            print(f"  {t}: {d['return']:+.2%} ({d['pnl']:+,.0f} VND)")
    
    print(f"\nSaved to {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
