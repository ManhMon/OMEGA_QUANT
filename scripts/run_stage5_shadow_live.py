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
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from omega.quant.execution_sim import ExecutionSimulator, ExecutionConfig, ExecutionResult
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
PORTFOLIO_VALUE = 10_000_000.0  # 10M VND notional
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
) -> ExecutionResult:
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
    ExecutionResult
        Execution result with slippage, cost, and trade details
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
        # Return empty result
        return ExecutionResult(
            timestamp=pd.Timestamp(date).to_pydatetime(),
            trades=[],
            num_trades=0,
            total_volume=0.0,
            total_slippage_bps=0.0,
            total_commission_bps=0.0,
            total_cost_bps=0.0,
            total_pnl=0.0,
            execution_time_ms=0.0,
        )

    target_weights = weights[common]
    target_weights = target_weights / target_weights.sum()  # renormalize
    current_weights = pd.Series(0.0, index=common)
    current_prices = latest[common]

    config = ExecutionConfig(
        latency_ms=50.0,
        slippage_bps=5.0,
        commission_bps=1.5,
        market_impact_coeff=0.1,
        min_trade_size=0.001,
    )
    sim = ExecutionSimulator(config=config)

    result = sim.execute_trades(
        target_weights=target_weights,
        current_weights=current_weights,
        current_prices=current_prices,
        timestamp=pd.Timestamp(date).to_pydatetime(),
        portfolio_value=PORTFOLIO_VALUE,
    )

    logger.info(
        f"Execution simulated for {date}: {result.num_trades} trades, "
        f"slippage={result.total_slippage_bps:.2f}bps, "
        f"cost={result.total_cost_bps:.2f}bps"
    )
    return result


def log_execution_metrics(result: ExecutionResult, date: str) -> Path:
    """Persist execution metrics to .ly_state/shadow_live/YYYY-MM-DD.json.

    Parameters
    ----------
    result : ExecutionResult
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

    # Serialize trades (exclude non-serializable datetime objects)
    trades_data = []
    for t in result.trades:
        trades_data.append({
            "symbol": t.symbol,
            "trade_size": float(t.trade_size),
            "execution_price": float(t.execution_price),
            "slippage_bps": float(t.slippage_bps),
            "commission_bps": float(t.commission_bps),
            "total_cost_bps": float(t.total_cost_bps),
            "pnl": float(t.pnl),
        })

    payload: Dict[str, Any] = {
        "date": date,
        "logged_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pit_cutoff": (pd.Timestamp(date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "status": "OK",
        "num_trades": result.num_trades,
        "total_volume": float(result.total_volume),
        "total_slippage_bps": float(result.total_slippage_bps),
        "total_commission_bps": float(result.total_commission_bps),
        "total_cost_bps": float(result.total_cost_bps),
        "total_pnl": float(result.total_pnl),
        "execution_time_ms": float(result.execution_time_ms),
        "trades": trades_data,
    }

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

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

        return {
            "date": date,
            "status": "OK",
            "num_trades": result.num_trades,
            "slippage_bps": result.total_slippage_bps,
            "cost_bps": result.total_cost_bps,
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
