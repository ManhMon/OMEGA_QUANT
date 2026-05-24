#!/usr/bin/env python3
"""
Stage 5: Shadow Live Daily Runner
===================================
Simulates daily portfolio rebalancing using real end-of-day VN market data.
Logs execution metrics (slippage, fill rate, latency) to .ly_state/shadow_live/.

PIT Safety: All market data uses T-1 lag (date <= run_date - 1 day).

Author: Backend Engineer (Role 09) [L2-Impl:Role9-Backend]
Date: 2026-05-22
Version: 1.0.0
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
from datetime import timezone

# ---------------------------------------------------------------------------
# Path setup - reuse existing repo modules only
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "quant" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "execution" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from omega.execution.execution_engine import ExecutionEngine, ExecutionEngineConfig
from omega.execution.order_router import OrderRouterConfig, TradingMode, LatencyConfig
from phase35_data_loader import Phase35DataLoader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("stage5_shadow_live")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SHADOW_LIVE_DIR = PROJECT_ROOT / ".ly_state" / "shadow_live"
WAREHOUSE_PATH = PROJECT_ROOT / "data" / "market_2015_now.parquet"
PORTFOLIO_VALUE = 5_000_000_000.0  # 5B VND notional
TOP_N_SYMBOLS = 20
LOOKBACK_DAYS = 252  # 1 year of history for weight generation


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def load_market_data_for_date(date: str) -> pd.DataFrame:
    """Load VN market data up to T-1 (PIT safe).

    Parameters
    ----------
    date : str
        Target date YYYY-MM-DD (T). Data loaded up to T-1.

    Returns
    -------
    pd.DataFrame
        OHLCV data with columns: date, ticker, open, high, low, close, volume
    """
    run_date = pd.Timestamp(date)
    pit_cutoff = run_date - pd.Timedelta(days=1)  # T-1 lag enforcement

    start_date = (pit_cutoff - pd.Timedelta(days=LOOKBACK_DAYS + 30)).strftime("%Y-%m-%d")
    end_date = pit_cutoff.strftime("%Y-%m-%d")

    loader = Phase35DataLoader(
        warehouse_path=str(WAREHOUSE_PATH),
        min_price=1.0,
        min_volume=1000.0,
        min_history_days=60,
    )

    df = loader.load_raw_data(start_date=start_date, end_date=end_date)
    df = loader.apply_filters(df)

    # PIT assertion: no data beyond T-1
    if not df.empty:
        max_date = pd.to_datetime(df["date"]).max()
        if max_date > pit_cutoff:
            raise ValueError(
                f"PIT Safety violation: data contains date {max_date} > T-1 cutoff {pit_cutoff}"
            )

    logger.info(f"Loaded {len(df):,} rows up to T-1={pit_cutoff.date()} for run_date={date}")
    return df


def generate_portfolio_weights(data: pd.DataFrame, date: str) -> pd.Series:
    """Generate equal-risk portfolio weights from T-1 data.

    Uses inverse-volatility weighting on the top N symbols by average volume.
    All inputs are T-1 data only (PIT safe by construction from load_market_data_for_date).

    Parameters
    ----------
    data : pd.DataFrame
        OHLCV data (already PIT-safe, date <= T-1)
    date : str
        Target date YYYY-MM-DD (used only for logging)

    Returns
    -------
    pd.Series
        Portfolio weights indexed by ticker, summing to 1.0
    """
    if data.empty:
        logger.warning(f"Empty data for {date}, returning empty weights")
        return pd.Series(dtype=float)

    df = data.copy()
    df["date"] = pd.to_datetime(df["date"])

    # Select top N symbols by average daily value (close * volume)
    df["value"] = df["close"] * df["volume"]
    avg_value = df.groupby("ticker")["value"].mean()
    top_symbols = avg_value.nlargest(TOP_N_SYMBOLS).index.tolist()
    df = df[df["ticker"].isin(top_symbols)]

    # Compute daily returns per symbol - vectorized
    df = df.sort_values(["ticker", "date"])
    df["ret"] = df.groupby("ticker")["close"].pct_change()

    # Compute rolling 20-day volatility per symbol
    vol = (
        df.groupby("ticker")["ret"]
        .std()
        .replace(0, np.nan)
        .dropna()
    )

    if vol.empty:
        logger.warning(f"No valid volatility estimates for {date}")
        return pd.Series(dtype=float)

    # Inverse-volatility weights
    inv_vol = 1.0 / vol
    weights = inv_vol / inv_vol.sum()

    logger.info(
        f"Generated weights for {len(weights)} symbols on {date}: "
        f"top={weights.idxmax()} ({weights.max():.3f})"
    )
    return weights


def simulate_execution(
    weights: pd.Series,
    data: pd.DataFrame,
    date: str,
) -> Dict[str, Any]:
    """Simulate execution using T-1 close prices as reference.

    Parameters
    ----------
    weights : pd.Series
        Target portfolio weights indexed by ticker
    data : pd.DataFrame
        OHLCV data (PIT-safe, date <= T-1)
    date : str
        Target date YYYY-MM-DD

    Returns
    -------
    dict
        Execution result summary
    """
    pit_cutoff = pd.Timestamp(date) - pd.Timedelta(days=1)

    df = data.copy()
    df["date"] = pd.to_datetime(df["date"])

    # Use T-1 close prices as reference (most recent available)
    latest = (
        df[df["date"] <= pit_cutoff]
        .sort_values("date")
        .groupby("ticker")
        .last()
        ["close"]
    )

    # Align weights to available prices
    common = weights.index.intersection(latest.index)
    if common.empty:
        logger.warning(f"No common symbols between weights and prices for {date}")
        return {"success": False, "orders": [], "metrics": {}}

    target_weights = weights[common]
    target_weights = target_weights / target_weights.sum()  # renormalize
    current_prices = latest[common]

    # Convert weights to target portfolio quantities based on PORTFOLIO_VALUE
    target_portfolio = {}
    for sym, w in target_weights.items():
        price = current_prices[sym]
        qty = int((PORTFOLIO_VALUE * w) // price)
        # Ensure minimum odd-lot/board-lot if needed (assuming 100 lot size for VN)
        qty = (qty // 100) * 100
        target_portfolio[sym] = {"quantity": qty}
        
    logger.info(f"Target portfolio quantities generated: {target_portfolio}")

    # Shadow Live assumes starting from cash daily for the sake of simulation, or could persist state.
    # For this simulation, we start empty and execute the target portfolio.
    current_portfolio = {sym: {"quantity": 0} for sym in target_portfolio.keys()}

    # Envelope
    prices_envelope = {
        "data": current_prices.to_dict(),
        "timestamp": time.time(),
        "provenance": "vnstock-shadow-live"
    }

    # Initialize Phase 16 Execution Engine
    router_cfg = OrderRouterConfig(
        mode=TradingMode.PAPER, 
        simulate_latency=True, 
        latency_config=LatencyConfig(paper_base_ms=12.0)
    )
    engine_cfg = ExecutionEngineConfig(
        mode=TradingMode.PAPER,
        router_config=router_cfg,
        liquidation_mode=True,
    )
    engine = ExecutionEngine(engine_cfg)

    result = engine.execute_workflow(
        target_portfolio=target_portfolio,
        current_portfolio=current_portfolio,
        current_prices=prices_envelope,
        allow_odd_lot=False
    )

    metrics = engine.get_execution_metrics()
    
    logger.info(
        f"Execution simulated for {date}: {metrics.get('total_filled', 0)} orders filled, "
        f"latency={metrics.get('router_average_latency_ms', 0):.2f}ms"
    )
    return result


def log_execution_metrics(result: Dict[str, Any], date: str) -> Path:
    """Persist execution metrics to .ly_state/shadow_live/YYYY-MM-DD.json.

    Parameters
    ----------
    result : dict
        Execution result from simulate_execution
    date : str
        Target date YYYY-MM-DD

    Returns
    -------
    Path
        Path to the written log file
    """
    SHADOW_LIVE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = SHADOW_LIVE_DIR / f"{date}.json"

    metrics = result.get("metrics", {})
    payload: Dict[str, Any] = {
        "date": date,
        "logged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pit_cutoff": (pd.Timestamp(date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "status": "OK" if result.get("success") else "FAILED",
        "num_trades": metrics.get("total_filled", 0),
        "total_volume": 0.0, # Not tracking volume per share directly in top level metrics yet
        "total_slippage_bps": metrics.get("estimated_slippage_bps", 0.0),
        "execution_time_ms": metrics.get("router_average_latency_ms", 0.0),
        "trades": result.get("orders", []),
    }

    class EnumEncoder(json.JSONEncoder):
        def default(self, obj):
            if hasattr(obj, "name"):
                return obj.name
            return super().default(obj)

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, cls=EnumEncoder)

    logger.info(f"Execution metrics logged to {log_path}")
    return log_path


def run_shadow_day(date: str) -> Dict[str, Any]:
    """Run one shadow trading day end-to-end.

    Parameters
    ----------
    date : str
        Target date YYYY-MM-DD

    Returns
    -------
    dict
        Summary with status, slippage_bps, log_path
    """
    logger.info(f"=== Shadow Live: {date} ===")

    try:
        data = load_market_data_for_date(date)
        if data.empty:
            return {"date": date, "status": "NO_DATA", "slippage_bps": None}

        weights = generate_portfolio_weights(data, date)
        if weights.empty:
            return {"date": date, "status": "NO_WEIGHTS", "slippage_bps": None}

        result = simulate_execution(weights, data, date)
        log_path = log_execution_metrics(result, date)
        metrics = result.get("metrics", {})

        return {
            "date": date,
            "status": "OK" if result.get("success") else "FAILED",
            "num_trades": metrics.get("total_filled", 0),
            "slippage_bps": metrics.get("estimated_slippage_bps", 0),
            "latency_ms": metrics.get("router_average_latency_ms", 0),
            "log_path": str(log_path),
        }

    except Exception as exc:
        logger.error(f"Shadow day {date} failed: {exc}", exc_info=True)
        return {"date": date, "status": "ERROR", "error": str(exc), "slippage_bps": None}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 5 Shadow Live Daily Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--date",
        type=str,
        required=True,
        help="Target date YYYY-MM-DD (T). Data uses T-1 lag.",
    )
    args = parser.parse_args()

    summary = run_shadow_day(args.date)

    print("\n" + "=" * 50)
    print(f"STAGE 5 SHADOW LIVE - {args.date}")
    print("=" * 50)
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print("=" * 50)

    sys.exit(0 if summary["status"] == "OK" else 1)


if __name__ == "__main__":
    main()
