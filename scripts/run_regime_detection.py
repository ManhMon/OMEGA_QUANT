"""
Run Regime Detection Pipeline
==============================
Wires RegimeDetectorHMM into the daily pipeline for enhanced drift detection.
Uses HMM-based regime classification to determine market state and dampening factor.

PIT Safety: Only uses data up to T-1 (no look-ahead bias).

Exit codes:
  0 - Bull or neutral regime (safe to trade full size)
  1 - Bear regime (high vol, negative momentum - reduce exposure)
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Ensure quant package is importable
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

import numpy as np
import pandas as pd

from omega.quant.strategy.regime_detector import RegimeDetectorHMM, HMMRegimeConfig

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("regime_detection")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REGIME_LABELS = {0: "bull", 1: "neutral", 2: "bear"}
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "market_2015_now.parquet"
STATE_DIR = Path(__file__).resolve().parent.parent / ".ly_state" / "session"
OUTPUT_FILE = STATE_DIR / "regime_status.json"

TOP_N_LIQUID = 30
LOOKBACK_DAYS = 252
ROLLING_VOL_WINDOW = 20
ROLLING_MOM_WINDOW = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily regime detection pipeline")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Reference date (YYYY-MM-DD). Default: today.",
    )
    return parser.parse_args()


def load_market_data(reference_date: str) -> pd.DataFrame:
    """Load market data up to T-1 for PIT safety."""
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Market data not found: {DATA_PATH}")

    df = pd.read_parquet(DATA_PATH)
    logger.info("Loaded market data: %d rows, %d columns", len(df), len(df.columns))

    # Ensure date column is datetime
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    elif df.index.name == "date":
        df.index = pd.to_datetime(df.index)
        df = df.reset_index()
    else:
        raise ValueError("Market data must have a 'date' column or index")

    # PIT Safety: only use data up to T-1
    ref_dt = pd.Timestamp(reference_date)
    t_minus_1 = ref_dt - timedelta(days=1)
    df = df[df["date"] <= t_minus_1].copy()

    if df.empty:
        raise ValueError(f"No data available up to T-1 ({t_minus_1.date()})")

    logger.info("PIT-safe data cutoff: %s (T-1)", t_minus_1.date())
    return df


def select_top_liquid(df: pd.DataFrame, n: int = TOP_N_LIQUID) -> list:
    """Select top N most liquid stocks by average daily volume."""
    if "volume" not in df.columns or "ticker" not in df.columns:
        # If no ticker/volume columns, assume wide-format returns
        logger.warning("No ticker/volume columns; using all available columns as assets")
        return []

    avg_volume = df.groupby("ticker")["volume"].mean().nlargest(n)
    tickers = avg_volume.index.tolist()
    logger.info("Selected top %d liquid stocks: %s", n, tickers[:5])
    return tickers


def compute_market_features(df: pd.DataFrame, tickers: list) -> pd.DataFrame:
    """
    Compute market features for regime detection:
    - VNIndex proxy: equal-weight daily returns of top 30 liquid stocks
    - Rolling volatility (20d)
    - Rolling momentum (20d)
    """
    if tickers and "ticker" in df.columns:
        # Long-format data with ticker column
        subset = df[df["ticker"].isin(tickers)].copy()
        if "close" not in subset.columns:
            raise ValueError("Market data must have a 'close' column")

        # Pivot to wide format: date x ticker
        pivot = subset.pivot_table(index="date", columns="ticker", values="close")
        pivot = pivot.sort_index()

        # Daily returns
        returns = pivot.pct_change().dropna(how="all")

        # Equal-weight market return (VNIndex proxy)
        market_return = returns.mean(axis=1)
    elif "close" in df.columns:
        # Single index/market data
        df = df.sort_values("date").set_index("date")
        market_return = df["close"].pct_change().dropna()
    else:
        raise ValueError("Cannot compute market features from available data")

    # Build feature DataFrame
    features = pd.DataFrame(index=market_return.index)
    features["market_return"] = market_return
    features["rolling_vol"] = market_return.rolling(window=ROLLING_VOL_WINDOW).std()
    features["rolling_momentum"] = market_return.rolling(window=ROLLING_MOM_WINDOW).sum()

    # Drop NaN rows from rolling calculations
    features = features.dropna()

    # Keep only last LOOKBACK_DAYS for training
    features = features.iloc[-LOOKBACK_DAYS:]

    logger.info(
        "Computed features: %d days, columns=%s", len(features), list(features.columns)
    )
    return features


def run_regime_detection(reference_date: str) -> int:
    """
    Main pipeline:
    1. Load market data (PIT-safe, up to T-1)
    2. Select top 30 liquid stocks
    3. Compute market features
    4. Fit HMM regime detector
    5. Predict current regime
    6. Save results and return exit code
    """
    logger.info("=== Regime Detection Pipeline ===")
    logger.info("Reference date: %s", reference_date)

    # Step 1: Load data
    df = load_market_data(reference_date)

    # Step 2: Select top liquid stocks
    tickers = select_top_liquid(df, TOP_N_LIQUID)

    # Step 3: Compute features
    features_df = compute_market_features(df, tickers)

    if len(features_df) < ROLLING_MOM_WINDOW:
        raise ValueError(
            f"Insufficient data for regime detection: {len(features_df)} days "
            f"(need at least {ROLLING_MOM_WINDOW})"
        )

    # Step 4: Fit HMM
    config = HMMRegimeConfig(n_regimes=3, lookback_days=LOOKBACK_DAYS)
    detector = RegimeDetectorHMM(config)

    features_array = features_df.values  # shape: (n_days, n_features)
    logger.info("Fitting HMM on %d days x %d features", *features_array.shape)
    detector.fit(features_array)

    # Step 5: Predict current regime (latest observation)
    latest_features = features_array[-1:, :]  # shape: (1, n_features)
    regime_id = detector.predict_regime(latest_features)
    dampening_factor = detector.get_dampening_factor()

    regime_label = REGIME_LABELS.get(regime_id, "unknown")
    logger.info(
        "Regime prediction: id=%d, label=%s, dampening_factor=%.3f",
        regime_id,
        regime_label,
        dampening_factor,
    )

    # Step 6: Save results
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "date": reference_date,
        "regime": regime_id,
        "dampening_factor": round(dampening_factor, 4),
        "regime_label": regime_label,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    logger.info("Saved regime status to %s", OUTPUT_FILE)

    # Step 7: Exit code based on regime
    if regime_label == "bear":
        logger.warning(
            "BEAR regime detected! High volatility, negative momentum. "
            "Dampening factor: %.3f. Reduce position sizes.",
            dampening_factor,
        )
        return 1

    logger.info("Regime is %s. Full position sizing allowed.", regime_label)
    return 0


def main() -> None:
    args = parse_args()

    try:
        exit_code = run_regime_detection(args.date)
    except FileNotFoundError as e:
        logger.error("Data file missing: %s", e)
        sys.exit(2)
    except ValueError as e:
        logger.error("Data validation error: %s", e)
        sys.exit(2)
    except Exception as e:
        logger.exception("Unexpected error in regime detection: %s", e)
        sys.exit(2)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
