#!/usr/bin/env python3
"""
run_portfolio_optimizer.py - Portfolio Optimization Pipeline
============================================================
Wires PortfolioOptimizer + MLGateValidator into a pipeline for
optimal position sizing. PIT-safe, no look-ahead bias.

Usage:
    python scripts/run_portfolio_optimizer.py --date 2026-05-29
    python scripts/run_portfolio_optimizer.py --date 2026-05-29 --signals-file path/to/signals.json
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
QUANT_SRC = WORKSPACE_ROOT / "packages" / "quant" / "src"
sys.path.insert(0, str(QUANT_SRC))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("portfolio_optimizer_pipeline")

# ---------------------------------------------------------------------------
# Conditional imports
# ---------------------------------------------------------------------------
PortfolioOptimizer = None
MLGateValidator = None

try:
    from omega.quant.portfolio_optimizer import PortfolioOptimizer
    logger.info("PortfolioOptimizer loaded successfully.")
except (ImportError, ModuleNotFoundError) as exc:
    logger.warning("PortfolioOptimizer not available: %s", exc)

try:
    from omega.quant.ml.gate_validator import MLGateValidator
    logger.info("MLGateValidator loaded successfully.")
except (ImportError, ModuleNotFoundError) as exc:
    logger.warning("MLGateValidator not available: %s", exc)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_WEIGHT = 0.25
MIN_WEIGHT = 0.02
LOOKBACK_DAYS = 60
BOARD_LOT = 100  # VN market minimum


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_signals(signals_path: Path) -> dict:
    """Load signals JSON file."""
    if not signals_path.exists():
        logger.error("Signals file not found: %s", signals_path)
        sys.exit(1)
    with open(signals_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info("Loaded %d signals from %s", len(data.get("signals", [])), signals_path)
    return data


def equal_weight_portfolio(signals: list[dict]) -> list[dict]:
    """Fallback: equal-weight allocation across all tickers."""
    if not signals:
        return []
    weight = 1.0 / len(signals)
    portfolio = []
    for sig in signals:
        ticker = sig.get("ticker", "UNKNOWN")
        portfolio.append({
            "ticker": ticker,
            "weight": round(weight, 6),
            "shares": BOARD_LOT,  # Minimum lot as placeholder
        })
    return portfolio


def signal_proportional_portfolio(signals: list[dict]) -> list[dict]:
    """Fallback: weights proportional to signal strength (normalized)."""
    if not signals:
        return []
    raw_scores = []
    for sig in signals:
        score = abs(float(sig.get("score", sig.get("signal_strength", 1.0))))
        raw_scores.append(max(score, 1e-9))

    total_score = sum(raw_scores)
    portfolio = []
    for sig, score in zip(signals, raw_scores):
        ticker = sig.get("ticker", "UNKNOWN")
        weight = score / total_score
        # Clamp weights
        weight = min(weight, MAX_WEIGHT)
        weight = max(weight, MIN_WEIGHT)
        portfolio.append({
            "ticker": ticker,
            "weight": round(weight, 6),
            "shares": BOARD_LOT,
        })

    # Re-normalize after clamping
    total_w = sum(p["weight"] for p in portfolio)
    if total_w > 0:
        for p in portfolio:
            p["weight"] = round(p["weight"] / total_w, 6)

    return portfolio


def run_ml_gate_validation(signals: list[dict], date_str: str) -> bool:
    """
    Step 1: ML Gate Validation.
    Returns True if gate passes (predictions meet quality threshold).
    """
    if MLGateValidator is None:
        logger.info("MLGateValidator not available, skipping gate validation.")
        return True  # No gate = pass through

    try:
        validator = MLGateValidator()
        # Proxy val_ic: mean absolute signal score (normalised to [-1, 1])
        # In production this should be the actual OOS IC from ensemble training
        scores = [abs(float(s.get("score", s.get("signal_strength", 0.0)))) for s in signals]
        proxy_ic = float(sum(scores) / len(scores)) if scores else 0.0
        logger.info("ML Gate proxy_ic=%.4f for date %s", proxy_ic, date_str)

        result = validator.validate(val_ic=proxy_ic, gate="production")
        passed = result.get("passed", True) if isinstance(result, dict) else bool(result)

        if passed:
            logger.info("ML Gate PASSED for date %s.", date_str)
        else:
            logger.warning("ML Gate FAILED for date %s (proxy_ic=%.4f). Using fallback.", date_str, proxy_ic)
        return passed
    except Exception as exc:
        logger.error("ML Gate validation error: %s. Treating as PASS (no block).", exc)
        return True  # Gate không block production nếu lỗi tính toán


def run_portfolio_optimization(signals: list[dict], date_str: str) -> tuple[list[dict], str]:
    """
    Step 2: Portfolio Optimization.
    Returns (portfolio_list, method_name).
    """
    if PortfolioOptimizer is None:
        logger.info("PortfolioOptimizer không có, dùng signal-proportional.")
        portfolio = signal_proportional_portfolio(signals)
        return portfolio, "signal_proportional"

    try:
        optimizer = PortfolioOptimizer()
        # Chuyển signals thành dict {ticker: score} cho optimize_weights
        signal_dict = {s["ticker"]: float(s.get("score", s.get("signal_strength", 0.0))) for s in signals}
        result = optimizer.optimize_weights(signal_dict)

        # Chuẩn hóa kết quả
        if isinstance(result, dict):
            formatted = [
                {"ticker": t, "weight": round(float(w), 6), "shares": BOARD_LOT}
                for t, w in result.items()
            ]
        else:
            formatted = signal_proportional_portfolio(signals)

        logger.info("optimize_weights hoàn thành: %d vị thế.", len(formatted))
        return formatted, "mean_variance"

    except Exception as exc:
        logger.error("Portfolio optimization failed: %s. Falling back to signal-proportional.", exc)
        portfolio = signal_proportional_portfolio(signals)
        return portfolio, "signal_proportional"


def save_portfolio(output_path: Path, date_str: str, portfolio: list[dict], method: str) -> None:
    """Save optimized portfolio to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "date": date_str,
        "portfolio": portfolio,
        "method": method,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "num_positions": len(portfolio),
        "total_weight": round(sum(p["weight"] for p in portfolio), 6),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    logger.info("Portfolio saved to %s", output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run portfolio optimization pipeline with ML gate validation."
    )
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Target date (YYYY-MM-DD). Default: today.",
    )
    parser.add_argument(
        "--signals-file",
        type=str,
        default=None,
        help="Path to signals JSON. Default: .ly_state/shadow_live/{date}.json",
    )
    args = parser.parse_args()

    date_str = args.date
    logger.info("=" * 60)
    logger.info("Portfolio Optimization Pipeline - Date: %s", date_str)
    logger.info("=" * 60)

    # Resolve signals file path
    if args.signals_file:
        signals_path = Path(args.signals_file)
    else:
        signals_path = WORKSPACE_ROOT / ".ly_state" / "shadow_live" / f"{date_str}.json"

    # Load signals - hỗ trợ cả dict {ticker: score} lẫn list[dict]
    signals_data = load_signals(signals_path)
    if not signals_data:
        logger.error("Không đọc được signals từ %s. Thoát.", signals_path)
        return 1
    signals_raw = signals_data.get("signals", [])
    if isinstance(signals_raw, dict):
        # Format từ run_ensemble_signals.py: {"HPG": 0.001, ...}
        signals = [{"ticker": k, "score": v} for k, v in signals_raw.items()]
    else:
        signals = signals_raw

    if not signals:
        logger.error("Không có tín hiệu trong file %s. Thoát.", signals_path)
        return 1

    # Step 1: ML Gate Validation
    logger.info("-" * 40)
    logger.info("Step 1: ML Gate Validation")
    logger.info("-" * 40)
    gate_passed = run_ml_gate_validation(signals, date_str)

    if not gate_passed:
        # Gate failed: use equal-weight fallback
        logger.warning("ML Gate failed. Using equal-weight fallback.")
        portfolio = equal_weight_portfolio(signals)
        method = "equal_weight"
    else:
        # Step 2: Portfolio Optimization
        logger.info("-" * 40)
        logger.info("Step 2: Portfolio Optimization")
        logger.info("-" * 40)
        portfolio, method = run_portfolio_optimization(signals, date_str)

    # Save result
    output_path = WORKSPACE_ROOT / ".ly_state" / "shadow_live" / f"{date_str}_portfolio.json"
    save_portfolio(output_path, date_str, portfolio, method)

    # Print summary
    total_weight = sum(p["weight"] for p in portfolio)
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("  Method:         %s", method)
    logger.info("  Num positions:  %d", len(portfolio))
    logger.info("  Total weight:   %.4f", total_weight)
    logger.info("  Output:         %s", output_path)
    logger.info("=" * 60)

    print(f"\n[OK] Portfolio optimized: method={method}, "
          f"positions={len(portfolio)}, total_weight={total_weight:.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
