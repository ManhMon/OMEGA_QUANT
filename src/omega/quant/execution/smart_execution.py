"""Smart execution schedules and safety checks."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random


class ExecutionSafetyError(RuntimeError):
    """Raised when execution cost breaches hard safety limits."""


VWAP_16_INTERVAL_PROFILE = (
    0.09,
    0.08,
    0.075,
    0.07,
    0.065,
    0.06,
    0.055,
    0.045,
    0.04,
    0.04,
    0.045,
    0.05,
    0.055,
    0.065,
    0.08,
    0.085,
)


@dataclass(frozen=True)
class ExecutionSlice:
    interval_index: int
    weight: float
    duration_minutes: int = 15


def normalized_vwap_profile(profile: tuple[float, ...] = VWAP_16_INTERVAL_PROFILE) -> list[float]:
    total = float(sum(profile))
    if total <= 0:
        raise ValueError("VWAP profile must have positive sum")
    return [float(value / total) for value in profile]


def build_vwap_schedule(profile: tuple[float, ...] = VWAP_16_INTERVAL_PROFILE) -> list[ExecutionSlice]:
    weights = normalized_vwap_profile(profile)
    return [
        ExecutionSlice(interval_index=index, weight=weight, duration_minutes=15)
        for index, weight in enumerate(weights)
    ]


def build_randomized_twap_schedule(
    intervals: int = 16,
    *,
    jitter: float = 0.2,
    seed: int | None = None,
) -> list[ExecutionSlice]:
    if intervals <= 0:
        raise ValueError("intervals must be positive")
    base = 1.0 / intervals
    rng = random.Random(seed)
    raw = [max(base * (1.0 + rng.uniform(-jitter, jitter)), 1e-9) for _ in range(intervals)]
    total = sum(raw)
    return [
        ExecutionSlice(interval_index=index, weight=float(weight / total), duration_minutes=15)
        for index, weight in enumerate(raw)
    ]


def enforce_slippage_kill_switch(cumulative_slippage_bps: float, limit_bps: float = 50.0) -> None:
    if cumulative_slippage_bps > limit_bps:
        raise ExecutionSafetyError(
            f"Cumulative slippage {cumulative_slippage_bps:.2f} bps exceeds kill-switch limit {limit_bps:.2f} bps"
        )


def apply_realistic_tc_kill_switch(slippage_pct: float) -> None:
    if abs(slippage_pct) > 0.10:
        raise ExecutionSafetyError("Slippage exceeds 10.0% kill switch threshold")


def slice_order_volume(total_order_volume: float, weights: list[float]) -> list[float]:
    if total_order_volume < 0:
        raise ValueError("total_order_volume must be non-negative")
    if not weights:
        return []
    total_weight = sum(weights)
    if not math.isclose(total_weight, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("slice weights must sum to 1.0")
    return [float(total_order_volume * weight) for weight in weights]
