"""
ML Gate Validator - Stage 3 MASTER_BACKTEST_PLAN
Role: Backend Engineer (Role 9) | Platform: OpenCode (L2)

Validates Research Gate and Production Gate criteria for ML model promotion.
PIT Safety: rolling IC computed on historical data only (no look-ahead).
"""

import pandas as pd
import numpy as np


def validate_research_gate(
    val_ic: float,
    rolling_ic_series: pd.Series,
    min_samples: int = 60,
) -> dict:
    """
    Validate Research Gate criteria for ML model promotion.

    Criteria:
    1. val_ic >= 0.05
    2. stability_ratio = rolling_ic_mean / rolling_ic_std > 1.5
    3. len(rolling_ic_series) >= min_samples

    Args:
        val_ic: Validation set Information Coefficient.
        rolling_ic_series: Historical rolling IC series (no future data).
        min_samples: Minimum number of samples required (default 60).

    Returns:
        dict with keys: passed, val_ic, stability_ratio, n_samples, verdict
    """
    n_samples = len(rolling_ic_series)

    # Check sample count first
    if n_samples < min_samples:
        return {
            "passed": False,
            "val_ic": val_ic,
            "stability_ratio": float("nan"),
            "n_samples": n_samples,
            "verdict": f"FAIL: insufficient samples ({n_samples} < {min_samples})",
        }

    # Compute stability ratio from historical series only (PIT safe)
    ic_mean = rolling_ic_series.mean()
    ic_std = rolling_ic_series.std()

    if np.isclose(ic_std, 0.0) or np.isnan(ic_std):
        stability_ratio = float("nan")
    else:
        stability_ratio = ic_mean / ic_std

    # Check val_ic threshold
    if val_ic < 0.05:
        return {
            "passed": False,
            "val_ic": val_ic,
            "stability_ratio": float(stability_ratio),
            "n_samples": n_samples,
            "verdict": f"FAIL: val_ic {val_ic:.4f} < 0.05",
        }

    # Check stability ratio
    if np.isnan(stability_ratio) or stability_ratio <= 1.5:
        return {
            "passed": False,
            "val_ic": val_ic,
            "stability_ratio": float(stability_ratio),
            "n_samples": n_samples,
            "verdict": f"FAIL: stability_ratio {stability_ratio:.4f} <= 1.5",
        }

    return {
        "passed": True,
        "val_ic": val_ic,
        "stability_ratio": float(stability_ratio),
        "n_samples": n_samples,
        "verdict": "PASS",
    }


def validate_production_gate(val_ic: float) -> dict:
    """
    Validate Production Gate criteria for ML model deployment.

    Criteria:
    1. val_ic >= 0.08 (production floor IC)

    Args:
        val_ic: Validation set Information Coefficient.

    Returns:
        dict with keys: passed, val_ic, verdict
    """
    if val_ic >= 0.08:
        return {
            "passed": True,
            "val_ic": val_ic,
            "verdict": "PASS",
        }

    return {
        "passed": False,
        "val_ic": val_ic,
        "verdict": f"FAIL: val_ic {val_ic:.4f} < 0.08",
    }
