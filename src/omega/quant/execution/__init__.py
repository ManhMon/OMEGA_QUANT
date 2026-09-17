"""Execution domain package."""

from .market_impact import (
    THETA_1,
    THETA_2,
    TMinusOneImpactSnapshot,
    calculate_nonlinear_slippage,
    calculate_nonlinear_slippage_bps,
)
from .smart_execution import (
    ExecutionSafetyError,
    ExecutionSlice,
    VWAP_16_INTERVAL_PROFILE,
    build_randomized_twap_schedule,
    build_vwap_schedule,
    enforce_slippage_kill_switch,
    normalized_vwap_profile,
    slice_order_volume,
)

__all__ = [
    "THETA_1",
    "THETA_2",
    "TMinusOneImpactSnapshot",
    "calculate_nonlinear_slippage",
    "calculate_nonlinear_slippage_bps",
    "ExecutionSafetyError",
    "ExecutionSlice",
    "VWAP_16_INTERVAL_PROFILE",
    "build_randomized_twap_schedule",
    "build_vwap_schedule",
    "enforce_slippage_kill_switch",
    "normalized_vwap_profile",
    "slice_order_volume",
]
