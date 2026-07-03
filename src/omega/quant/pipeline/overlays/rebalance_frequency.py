"""Rebalance frequency overlay - holds weights between rebalance dates.

Reduces trading frequency by only allowing weight changes on scheduled
rebalance dates.  Between rebalances, previous weights are carried forward,
eliminating turnover on non-rebalance bars.

PIT-safe: only uses current/past dates to determine rebalance schedule.
No look-ahead bias introduced.

Gate: HYBRID_REGIME_BACKTEST_PERF_20260621
"""
from __future__ import annotations

import logging
from typing import Dict, Any

import numpy as np
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay

logger = logging.getLogger(__name__)

VALID_MODES = ("fixed_interval", "day_of_week", "day_of_month")


class RebalanceFrequencyOverlay(WeightOverlay):
    """Gate rebalances to a configurable schedule, carrying forward weights
    on non-rebalance bars.

    Modes
    -----
    fixed_interval : Rebalance every ``rebalance_every_n_days`` trading bars.
    day_of_week    : Rebalance on a specific weekday (0=Mon … 4=Fri).
    day_of_month   : Rebalance on a specific calendar day (1–28).

    Parameters
    ----------
    rebalance_every_n_days : int
        For ``fixed_interval`` mode — number of trading bars between
        rebalances (default 5 ≈ weekly on VN market, ~248 trading days/yr).
    mode : str
        One of ``fixed_interval``, ``day_of_week``, ``day_of_month``.
    day_of_week : int
        For ``day_of_week`` mode — target weekday (0=Mon, 4=Fri).
    day_of_month : int
        For ``day_of_month`` mode — target calendar day (1–28).

    Notes
    -----
    * The first bar is always a rebalance (initial position establishment).
    * If a target day falls on a non-trading day, the next available trading
      day is used (forward-fill to next bar in index).
    * PIT-safe: rebalance schedule is derived solely from the weights index
      dates — no future data is accessed.
    """

    def __init__(
        self,
        rebalance_every_n_days: int = 5,
        bear_multiplier: float = 2.0,
        mode: str = "fixed_interval",
        day_of_week: int = 0,
        day_of_month: int = 1,
    ):
        if mode not in VALID_MODES:
            raise ValueError(
                f"Invalid mode '{mode}'. Must be one of {VALID_MODES}"
            )
        if rebalance_every_n_days < 1:
            raise ValueError("rebalance_every_n_days must be >= 1")
        if bear_multiplier < 1:
            raise ValueError("bear_multiplier must be >= 1")

        self.rebalance_every_n_days = rebalance_every_n_days
        self.bear_multiplier = bear_multiplier
        self.mode = mode
        self.day_of_week = day_of_week
        self.day_of_month = day_of_month

    def _build_rebalance_mask(self, dates: pd.DatetimeIndex) -> np.ndarray:
        """Return boolean mask (True = rebalance bar) over the date index.

        PIT-safe: uses only the provided dates array (no future peeking).
        """
        n = len(dates)
        if n == 0:
            return np.array([], dtype=bool)

        mask = np.zeros(n, dtype=bool)
        mask[0] = True  # first bar always rebalances

        if self.mode == "fixed_interval":
            mask[self.rebalance_every_n_days :: self.rebalance_every_n_days] = True

        elif self.mode == "day_of_week":
            weekdays = dates.weekday
            target_hits = np.where(weekdays == self.day_of_week)[0]
            if len(target_hits) > 0:
                # Pick first occurrence per ISO week to avoid double-rebalance
                # when two bars share the same weekday in a short week.
                prev_week = -1
                for idx in target_hits:
                    iso_week = dates[idx].isocalendar()[1]
                    iso_year = dates[idx].isocalendar()[0]
                    week_id = iso_year * 100 + iso_week
                    if week_id != prev_week:
                        mask[idx] = True
                        prev_week = week_id

        elif self.mode == "day_of_month":
            days = dates.day
            target_hits = np.where(days == self.day_of_month)[0]
            if len(target_hits) > 0:
                mask[target_hits] = True
            else:
                # Fallback: if exact day never appears (e.g. holidays),
                # pick the first trading day of each month.
                ym = dates.to_period("M")
                prev_ym = None
                for i, p in enumerate(ym):
                    if p != prev_ym:
                        mask[i] = True
                        prev_ym = p

        return mask

    def _build_dynamic_rebalance_mask(
        self,
        dates: pd.DatetimeIndex,
        regime_labels: Dict[str, Any],
    ) -> np.ndarray:
        n = len(dates)
        if n == 0:
            return np.array([], dtype=bool)

        mask = np.zeros(n, dtype=bool)
        idx = 0
        while idx < n:
            mask[idx] = True
            label = str(regime_labels.get(dates[idx].strftime("%Y-%m-%d"), "Sideways"))
            interval = self.rebalance_every_n_days
            if label != "Bull":
                interval = max(1, int(np.ceil(interval * self.bear_multiplier)))
            idx += interval
        return mask

    def apply(
        self,
        weights: pd.DataFrame,
        panel: pd.DataFrame,
        state: Dict[str, Any],
    ) -> pd.DataFrame:
        if not isinstance(weights.index, pd.DatetimeIndex):
            logger.warning(
                "RebalanceFrequencyOverlay: weights index is not DatetimeIndex — "
                "passing through unchanged."
            )
            return weights

        dates = weights.index
        regime_labels = state.get("gmm_regime_labels")
        if self.mode == "fixed_interval" and isinstance(regime_labels, dict) and regime_labels:
            rebalance_mask = self._build_dynamic_rebalance_mask(dates, regime_labels)
        else:
            rebalance_mask = self._build_rebalance_mask(dates)
        n_rebalances = int(rebalance_mask.sum())
        n_total = len(dates)

        if n_rebalances == n_total:
            logger.info(
                "RebalanceFrequencyOverlay: all %d bars are rebalance bars "
                "(mode=%s, n_days=%d) — no change.",
                n_total, self.mode, self.rebalance_every_n_days,
            )
            return weights

        # Carry forward: on non-rebalance bars, copy weights from the
        # most recent rebalance bar.
        result = weights.copy()
        last_rebalance_weights = None

        for i in range(n_total):
            if rebalance_mask[i]:
                last_rebalance_weights = result.iloc[i].copy()
            elif last_rebalance_weights is not None:
                result.iloc[i] = last_rebalance_weights

        reduction_pct = (1.0 - n_rebalances / n_total) * 100 if n_total > 0 else 0.0
        logger.info(
            "RebalanceFrequencyOverlay: %d/%d bars rebalanced (%.1f%% reduction), "
            "mode=%s, param=%d, bear_multiplier=%.2f",
            n_rebalances, n_total, reduction_pct,
            self.mode, self.rebalance_every_n_days, self.bear_multiplier,
        )

        return result
