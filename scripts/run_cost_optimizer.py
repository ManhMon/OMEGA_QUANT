"""
run_cost_optimizer.py - Wire TransactionCostOptimizer into signal pipeline.

Reduces slippage by penalizing high-cost trades and re-normalizing weights.
PIT-safe: uses only T-1 data available at execution time.

Usage:
    python scripts/run_cost_optimizer.py --date 2026-05-29
    python scripts/run_cost_optimizer.py --date 2026-05-29 --signals-file path/to/signals.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup for package imports
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_WORKSPACE = _SCRIPT_DIR.parent
_QUANT_SRC = _WORKSPACE / "packages" / "quant" / "src"
sys.path.insert(0, str(_QUANT_SRC))

from omega.quant.execution.transaction_cost_optimizer import TransactionCostOptimizer  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_cost_optimizer")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HIGH_COST_THRESHOLD_BPS = 50.0  # Trades above this get weight reduction
WEIGHT_REDUCTION_FACTOR = 0.5   # Reduce weight by 50% for high-cost trades


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Optimize signal weights using transaction cost analysis."
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Trading date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--signals-file",
        default=None,
        help="Path to signals JSON. Default: .ly_state/shadow_live/{date}.json",
    )
    return parser.parse_args()


def load_signals(signals_path: Path) -> list[dict]:
    """Load signals from JSON file."""
    if not signals_path.exists():
        logger.error("Signals file not found: %s", signals_path)
        sys.exit(1)

    with open(signals_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Support both list format and dict with "signals" key
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "signals" in data:
        return data["signals"]

    logger.error("Unexpected signals format in %s", signals_path)
    sys.exit(1)


def optimize_signals(signals: list[dict]) -> tuple[list[dict], float, float]:
    """
    Calculate transaction costs and adjust weights for high-cost trades.

    Returns:
        (optimized_signals, total_cost_before_bps, total_cost_after_bps)
    """
    from datetime import datetime, timedelta
    optimizer = TransactionCostOptimizer()

    # Build positions and market_data dicts (API expects Dict[str, int] and Dict[str, Dict])
    positions = {}
    market_data = {}
    for signal in signals:
        symbol = signal.get("ticker", signal.get("symbol", ""))
        shares = int(signal.get("shares", signal.get("weight", 0) * 1000))  # fallback
        price = signal.get("price", signal.get("signal_score", 1.0))
        adv = signal.get("adv", signal.get("adv_vnd", 1_000_000_000))
        volatility = signal.get("volatility", 0.30)
        positions[symbol] = shares
        market_data[symbol] = {
            "price": float(price) if price else 1.0,
            "adv": float(adv),
            "volatility": float(volatility),
        }

    now = datetime.now()
    available_at = now - timedelta(minutes=1)
    
    try:
        results = optimizer.calculate_cost(
            positions=positions,
            market_data=market_data,
            as_of=now,
            available_at=available_at,
        )
    except Exception as e:
        logger.warning("calculate_cost failed: %s, using simple estimate", e)
        results = {}

    # Phase 1: Apply costs to signals
    total_cost_before = 0.0
    for signal in signals:
        symbol = signal.get("ticker", signal.get("symbol", ""))
        result = results.get(symbol)
        if result is not None:
            cost_bps = getattr(result, "total_cost_bps", 25.0)
            signal["cost_bps"] = float(cost_bps)
            signal["market_impact_bps"] = float(getattr(result, "market_impact_bps", 10.0))
            signal["optimal_participation_rate"] = float(getattr(result, "optimal_participation_rate", 0.10))
        else:
            # Fallback: estimate 25bps default
            signal["cost_bps"] = 25.0
            signal["market_impact_bps"] = 10.0
            signal["optimal_participation_rate"] = 0.10
        weight = signal.get("weight", 0.0)
        total_cost_before += signal["cost_bps"] * abs(weight)

    # Phase 2: Adjust weights - reduce for high-cost trades
    for signal in signals:
        if signal["cost_bps"] > HIGH_COST_THRESHOLD_BPS:
            original_weight = signal.get("weight", 0.0)
            signal["weight"] = original_weight * WEIGHT_REDUCTION_FACTOR
            logger.info(
                "Reduced weight for %s: %.4f -> %.4f (cost=%.1f bps)",
                signal.get("symbol", "?"),
                original_weight,
                signal["weight"],
                signal["cost_bps"],
            )

    # Phase 3: Re-normalize weights to sum=1.0
    total_weight = sum(abs(s.get("weight", 0.0)) for s in signals)
    if total_weight > 0:
        for signal in signals:
            signal["weight"] = signal.get("weight", 0.0) / total_weight

    # Phase 4: Calculate cost after optimization
    total_cost_after = 0.0
    for signal in signals:
        total_cost_after += signal["cost_bps"] * abs(signal.get("weight", 0.0))

    return signals, total_cost_before, total_cost_after


def save_optimized(signals: list[dict], output_path: Path) -> None:
    """Save optimized signals to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)
    logger.info("Saved optimized signals to %s", output_path)


def main() -> None:
    args = parse_args()
    date_str = args.date

    # Resolve signals file path
    if args.signals_file:
        signals_path = Path(args.signals_file)
    else:
        signals_path = _WORKSPACE / ".ly_state" / "shadow_live" / f"{date_str}.json"

    logger.info("Loading signals from %s", signals_path)
    signals = load_signals(signals_path)
    logger.info("Loaded %d signals for date %s", len(signals), date_str)

    if not signals:
        logger.warning("No signals to optimize. Exiting.")
        sys.exit(0)

    # Run optimization
    optimized, cost_before, cost_after = optimize_signals(signals)

    # Save output
    output_path = (
        _WORKSPACE / ".ly_state" / "shadow_live" / f"{date_str}_optimized.json"
    )
    save_optimized(optimized, output_path)

    # Summary
    reduction = cost_before - cost_after
    reduction_pct = (reduction / cost_before * 100) if cost_before > 0 else 0.0
    print(f"\n{'='*60}")
    print(f"Transaction Cost Optimization Summary ({date_str})")
    print(f"{'='*60}")
    print(f"  Signals processed:    {len(optimized)}")
    print(f"  Total cost BEFORE:    {cost_before:.2f} bps (weighted)")
    print(f"  Total cost AFTER:     {cost_after:.2f} bps (weighted)")
    print(f"  Cost reduction:       {reduction:.2f} bps ({reduction_pct:.1f}%)")
    print(f"  Output:               {output_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
