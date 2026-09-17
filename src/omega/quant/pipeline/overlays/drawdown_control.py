"""Drawdown control overlay - stateful stop-out and adaptive re-entry.

Gate: HYBRID_REGIME_DETECTION_20260619
Gate: HYBRID_REGIME_DYNAMIC_BRAKE_20260621

Implements stateful drawdown management with:
1. Stop-out: When portfolio drawdown exceeds threshold, move to cash.
2. Adaptive cooldown: Extend cooldown in bear/high-vol regimes.
3. Regime re-entry filter: Block re-entry during bear ex-ante regime.
4. HWM reset: Reset high-water mark on successful re-entry.
5. **BOCPD risk gating**: Bayesian Online Change Point Detection running
   recursively on trailing portfolio returns. When a change point is
   detected, cooldown is extended and exposure is tightened.
6. **HMM Bear Re-entry Filter** (Giai phap B): At re-entry, block only
   while HMM bear posterior probability remains above threshold.
   If still bearish, extend cooldown with a hard cap to avoid
   permanent cash trapping in prolonged bear/sideways regimes.

PIT Safety: All decisions based on trailing realized returns only.
No forward-looking data or current-bar information used.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay

logger = logging.getLogger(__name__)


class DrawdownControlOverlay(WeightOverlay):
    """Stateful drawdown-based stop-out with BOCPD risk gating.

    Parameters
    ----------
    threshold : float
        Drawdown threshold (negative) to trigger stop-out (default -0.05 = 5%).
    cooldown_days : int
        Base cooldown period in days after stop-out (default 5).
    adaptive_re_entry : bool
        Enable adaptive cooldown extension based on regime (default True).
    adaptive_bear_threshold : float
        HMM bear probability threshold to extend cooldown (default 0.5).
    adaptive_max_cooldown : int
        Maximum cooldown days with adaptive extension (default 20).
    regime_re_entry_filter : bool
        Block re-entry if regime is bear ex-ante (default True).
    bocpd_enabled : bool
        Enable BOCPD change-point gating (default True).
    bocpd_hazard_rate : float
        BOCPD hazard rate 1/E[run_length] (default 1/200).
    bocpd_threshold : float
        Change-point probability threshold to trigger gating (default 0.5).
    bocpd_cooldown_extension : int
        Extra cooldown days when BOCPD fires (default 3).
    bocpd_exposure_scale : float
        Scale exposure by this factor when BOCPD fires (default 0.5).
    hmm_reentry_enabled : bool
        Enable HMM bear re-entry filter (default True).
    hmm_bear_reentry_threshold : float
        Block re-entry while HMM p_bear exceeds this threshold (default 0.6).
    hmm_reentry_cooldown_extension : int
        Extra cooldown days when HMM bear threshold blocks re-entry (default 5).
    max_reentry_cooldown_days : int
        Hard cap on total post-stop-out cooldown days before forced re-entry (default 60).
    gmm_bull_reentry_enabled : bool
        Deprecated fallback gate. When True, use legacy GMM bull posterior gate.
    gmm_bull_confidence : float
        Minimum GMM p_bull for legacy fallback re-entry (default 0.4).
    gmm_partial_reentry_scale : float
        Deprecated legacy field retained for ctor/state compatibility.
    gmm_reentry_cooldown_extension : int
        Extra cooldown days when legacy GMM bull confidence not met (default 3).
    estimated_cost_bps : float
        Estimated one-way transaction cost in basis points per unit of
        turnover (default 20.0).  Subtracted from the per-bar portfolio
        return used for internal NAV tracking so that the drawdown
        budget (max_global_dd) constrains a cost-aware equity curve
        close to the executed / post-cost net curve reported as MaxDD.
        Set to 0.0 to disable cost estimation (pre-cost NAV tracking).
    max_global_dd : float
        Hard cumulative DD floor from initial NAV (default -0.09 = 9%).
        When global DD exceeds this, all weights are forced to zero and
        re-entry is blocked until NAV recovers above the floor.
        Prevents repeated per-cycle stop-outs from compounding past the
        fold-level MaxDD budget.  Set to 0.0 to disable; negative values
        set the floor threshold.
    """

    def __init__(
        self,
        threshold: float = -0.05,
        cooldown_days: int = 5,
        adaptive_re_entry: bool = True,
        adaptive_bear_threshold: float = 0.5,
        adaptive_max_cooldown: int = 20,
        regime_re_entry_filter: bool = True,
        bocpd_enabled: bool = True,
        bocpd_hazard_rate: float = 1.0 / 200.0,
        bocpd_threshold: float = 0.5,
        bocpd_cooldown_extension: int = 3,
        bocpd_exposure_scale: float = 0.5,
        hmm_reentry_enabled: bool = True,
        hmm_bear_reentry_threshold: float = 0.6,
        hmm_reentry_cooldown_extension: int = 5,
        max_reentry_cooldown_days: int = 60,
        gmm_bull_reentry_enabled: bool = False,
        gmm_bull_confidence: float = 0.4,
        gmm_partial_reentry_scale: float = 0.3,
        gmm_reentry_cooldown_extension: int = 3,
        max_global_dd: float = -0.09,
        estimated_cost_bps: float = 20.0,
    ):
        self.threshold = threshold
        self.cooldown_days = cooldown_days
        self.adaptive_re_entry = adaptive_re_entry
        self.adaptive_bear_threshold = adaptive_bear_threshold
        self.adaptive_max_cooldown = adaptive_max_cooldown
        self.regime_re_entry_filter = regime_re_entry_filter

        self.bocpd_enabled = bocpd_enabled
        self.bocpd_hazard_rate = bocpd_hazard_rate
        self.bocpd_threshold = bocpd_threshold
        self.bocpd_cooldown_extension = bocpd_cooldown_extension
        self.bocpd_exposure_scale = bocpd_exposure_scale

        # Giai phap B: HMM bear re-entry filter
        self.hmm_reentry_enabled = hmm_reentry_enabled
        self.hmm_bear_reentry_threshold = hmm_bear_reentry_threshold
        self.hmm_reentry_cooldown_extension = hmm_reentry_cooldown_extension
        self.max_reentry_cooldown_days = max_reentry_cooldown_days

        # Deprecated fallback: GMM Bull Re-entry Filter
        self.gmm_bull_reentry_enabled = gmm_bull_reentry_enabled
        self.gmm_bull_confidence = gmm_bull_confidence
        self.gmm_partial_reentry_scale = gmm_partial_reentry_scale
        self.gmm_reentry_cooldown_extension = gmm_reentry_cooldown_extension

        # Cumulative DD floor (prevents per-cycle compounding past budget)
        self.max_global_dd = max_global_dd

        # Estimated one-way cost per unit turnover (bps).
        # Subtracted from port_ret so NAV tracks a cost-aware curve.
        self.estimated_cost_bps = estimated_cost_bps

        # Internal state
        self._hwm: float = 1.0
        self._nav: float = 1.0
        self._initial_nav: float = 1.0
        self._in_cooldown: bool = False
        self._cooldown_remaining: int = 0
        self._stopped_out: bool = False
        self._global_dd_blocked: bool = False

        # Previous effective weights for turnover-based cost estimation
        self._prev_weights: Optional[np.ndarray] = None

        # Deferred-action flags (persisted across incremental apply() calls)
        self._pending_stop_out: bool = False
        self._pending_bocpd_gate: bool = False
        self._reentry_cooldown_total: int = 0
        self._reentry_ok: Optional[bool] = None

        # Batch-start NAV/HWM: captured at the top of apply() so that
        # sync_executed_returns() can chain from the persisted prior-batch
        # NAV rather than resetting to initial_nav.
        self._batch_start_nav: float = 1.0
        self._batch_start_hwm: float = 1.0

        # BOCPD state
        self._bocpd_detector = None
        self._bocpd_last_cp_prob: float = 0.0
        self._bocpd_cp_count: int = 0

        if self.bocpd_enabled:
            self._init_bocpd()

    def _init_bocpd(self) -> None:
        """Initialize BOCPD detector (lazy import to avoid hard dependency)."""
        try:
            from omega.quant.math.bocpd import BOCPDDetector, BOCPDConfig
            self._bocpd_detector = BOCPDDetector(
                BOCPDConfig(
                    hazard_rate=self.bocpd_hazard_rate,
                    change_point_threshold=self.bocpd_threshold,
                )
            )
        except ImportError:
            logger.warning(
                "DrawdownControlOverlay: BOCPD module not available, "
                "disabling BOCPD risk gating."
            )
            self.bocpd_enabled = False
            self._bocpd_detector = None

    def apply(
        self,
        weights: pd.DataFrame,
        panel: pd.DataFrame,
        state: Dict[str, Any],
    ) -> pd.DataFrame:
        # Restore state from persisted dict
        self._restore_state(state)

        # Snapshot batch-start NAV/HWM so sync_executed_returns() can
        # chain from the persisted prior-batch values instead of
        # resetting to initial_nav (L3 Blocker 1 fix).
        self._batch_start_nav = self._nav
        self._batch_start_hwm = self._hwm

        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel
        returns_pivot = panel_flat.pivot_table(
            index="date", columns="symbol", values="returns"
        ).fillna(0.0)
        returns_pivot = returns_pivot.reindex(
            index=weights.index, columns=weights.columns, fill_value=0.0
        )

        # Extract HMM bear probability from state if available
        hmm_p_bear = state.get("hmm_p_bear", {})
        active_dates = state.get("active_dates")
        active_set = set(active_dates) if active_dates is not None else None

        # Deprecated fallback: extract GMM bull probabilities from state
        gmm_p_bull = state.get("gmm_p_bull", {})
        hmm_reentry_blocked_count = 0
        gmm_reentry_blocked_count = 0

        result = weights.copy()

        # PIT safety: deferred-action flags.  Decisions triggered by day-dt
        # returns are stored here and applied at the START of day dt+1,
        # so that day-dt weights are never retroactively altered.
        # Restore from persisted state so deferred actions survive across
        # incremental apply() calls (e.g. last-day trigger with no dt+1 in batch).
        _pending_stop_out = bool(getattr(self, "_pending_stop_out", False))
        _pending_bocpd_gate = bool(getattr(self, "_pending_bocpd_gate", False))

        for i, dt in enumerate(result.index):
            if active_set is not None and dt not in active_set:
                continue

            # --- Apply deferred actions from the previous day (PIT safe) ---
            if _pending_stop_out:
                self._in_cooldown = True
                self._cooldown_remaining = self.cooldown_days
                self._reentry_cooldown_total = self.cooldown_days
                _pending_stop_out = False

            if _pending_bocpd_gate:
                if not self._in_cooldown:
                    result.loc[dt] = result.loc[dt] * self.bocpd_exposure_scale
                    logger.info(
                        "DrawdownControlOverlay: BOCPD exposure gate applied at %s "
                        "(scale=%.2f)",
                        dt, self.bocpd_exposure_scale,
                    )
                _pending_bocpd_gate = False

            # --- Cooldown management FIRST (may zero weights) ---
            # This must happen BEFORE NAV update so that NAV reflects the
            # effective (post-cooldown) portfolio return, not phantom returns
            # from weights that will be zeroed.
            _reentered_this_bar = False
            if self._in_cooldown:
                # Check if we should extend cooldown (adaptive)
                if self.adaptive_re_entry and self._cooldown_remaining <= 1:
                    dt_str = str(dt)[:10] if hasattr(dt, 'strftime') else str(dt)
                    bear_prob = hmm_p_bear.get(dt_str, 0.0)

                    # Extend if bear probability is high
                    if bear_prob >= self.adaptive_bear_threshold:
                        extension = min(
                            self.adaptive_max_cooldown - self.cooldown_days,
                            3,
                        )
                        self._cooldown_remaining += max(1, extension)
                        self._reentry_cooldown_total += max(1, extension)
                        logger.info(
                            "DrawdownControlOverlay: Extended cooldown at %s (bear_prob=%.2f)",
                            dt, bear_prob,
                        )

                    # Regime re-entry filter: block if bear
                    if self.regime_re_entry_filter and bear_prob >= self.adaptive_bear_threshold:
                        self._cooldown_remaining += 1
                        self._reentry_cooldown_total += 1

                self._cooldown_remaining -= 1

                if self._cooldown_remaining <= 0:
                    reentry_ok = True
                    force_reentry = False
                    dt_str_re = str(dt)[:10] if hasattr(dt, 'strftime') else str(dt)
                    if self.hmm_reentry_enabled:
                        p_bear = float(hmm_p_bear.get(dt_str_re, 0.0))
                        if p_bear > self.hmm_bear_reentry_threshold:
                            reentry_ok = False
                            hmm_reentry_blocked_count += 1
                            self._cooldown_remaining += self.hmm_reentry_cooldown_extension
                            self._reentry_cooldown_total += self.hmm_reentry_cooldown_extension
                            logger.warning(
                                "DrawdownControlOverlay: HMM Re-entry BLOCKED at %s "
                                "(p_bear=%.3f > threshold=%.3f) — extending cooldown +%d days",
                                dt,
                                p_bear,
                                self.hmm_bear_reentry_threshold,
                                self.hmm_reentry_cooldown_extension,
                            )
                            if (
                                self._cooldown_remaining > self.max_reentry_cooldown_days
                                or self._reentry_cooldown_total > self.max_reentry_cooldown_days
                            ):
                                force_reentry = True
                                reentry_ok = True
                                logger.info(
                                    "DrawdownControlOverlay: Re-entry hard cap hit at %s "
                                    "(remaining=%d, total=%d, cap=%d) — forcing re-entry",
                                    dt,
                                    self._cooldown_remaining,
                                    self._reentry_cooldown_total,
                                    self.max_reentry_cooldown_days,
                                )
                    elif self.gmm_bull_reentry_enabled:
                        if dt_str_re in gmm_p_bull:
                            p_bull = gmm_p_bull[dt_str_re]
                            if p_bull < self.gmm_bull_confidence:
                                reentry_ok = False
                                gmm_reentry_blocked_count += 1
                                self._cooldown_remaining += self.gmm_reentry_cooldown_extension
                                self._reentry_cooldown_total += self.gmm_reentry_cooldown_extension
                                logger.info(
                                    "DrawdownControlOverlay: GMM Bull Re-entry BLOCKED at %s "
                                    "(p_bull=%.3f < confidence=%.3f) — extending cooldown +%d days",
                                    dt, p_bull, self.gmm_bull_confidence,
                                    self.gmm_reentry_cooldown_extension,
                                )
                        else:
                            logger.debug(
                                "DrawdownControlOverlay: No GMM p_bull for %s — "
                                "allowing legacy re-entry (missing != bearish)",
                                dt,
                            )

                    # Global DD floor: block re-entry if cumulative DD too deep
                    if reentry_ok and self.max_global_dd < 0:
                        global_dd = (
                            (self._nav - self._initial_nav) / self._initial_nav
                            if self._initial_nav > 0 else 0.0
                        )
                        print(f"DEBUG REENTRY CHECK: dt={dt}, nav={self._nav:.6f}, initial_nav={self._initial_nav:.6f}, global_dd={global_dd:.6f}, reentry_ok={reentry_ok}")
                        if global_dd <= self.max_global_dd:
                            reentry_ok = False
                            self._global_dd_blocked = True
                            self._cooldown_remaining += self.cooldown_days
                            self._reentry_cooldown_total += self.cooldown_days
                            logger.info(
                                "DrawdownControlOverlay: GLOBAL DD FLOOR at %s "
                                "(global_dd=%.2f%%, floor=%.2f%%) — blocking re-entry",
                                dt, global_dd * 100, self.max_global_dd * 100,
                            )

                    self._reentry_ok = reentry_ok

                    if reentry_ok:
                        # Full re-entry
                        logger.info("DrawdownControlOverlay: RE-ENTRY at %s", dt)
                        self._in_cooldown = False
                        self._stopped_out = False
                        self._global_dd_blocked = False
                        self._cooldown_remaining = 0
                        self._reentry_cooldown_total = 0
                        # HWM reset: set HWM to current NAV for new cycle
                        self._hwm = self._nav
                        # Reset BOCPD on re-entry to start fresh cycle
                        if self.bocpd_enabled and self._bocpd_detector is not None:
                            self._bocpd_detector.reset()
                        _reentered_this_bar = True
                    else:
                        # Still in cooldown: zero out weights (cash)
                        result.loc[dt] = 0.0
                else:
                    # Still in cooldown: zero out weights (cash)
                    result.loc[dt] = 0.0

            # --- Compute effective portfolio return from POST-cooldown weights ---
            # During cooldown, weights are zeroed → port_ret = 0 (cash).
            # This fixes the phantom-loss bug where NAV accumulated fictitious
            # returns from weights that were subsequently zeroed.
            w = result.loc[dt]
            r = returns_pivot.loc[dt]
            gross_ret = float((w * r).sum())

            # Estimate transaction cost drag from turnover (cost-aware NAV).
            # This ensures max_global_dd binds against a curve that includes
            # cost drag, matching the executed / post-cost equity curve used
            # by reported MaxDD.
            cost_drag = 0.0
            if self.estimated_cost_bps > 0:
                w_arr = w.values if hasattr(w, "values") else np.asarray(w, dtype=float)
                if self._prev_weights is not None:
                    turnover = float(np.abs(w_arr - self._prev_weights).sum())
                else:
                    turnover = float(np.abs(w_arr).sum())
                cost_drag = turnover * self.estimated_cost_bps * 1e-4
                self._prev_weights = w_arr.copy()

            port_ret = gross_ret - cost_drag

            # Update NAV using effective return
            self._nav *= (1.0 + port_ret)

            # Update HWM
            if self._nav > self._hwm:
                self._hwm = self._nav

            # Current drawdown (from per-cycle HWM)
            dd = (self._nav - self._hwm) / self._hwm if self._hwm > 0 else 0.0

            # BOCPD update: feed effective trailing return, check for change point
            bocpd_cp_detected = False
            if self.bocpd_enabled and self._bocpd_detector is not None:
                cp_prob, _ = self._bocpd_detector.update(port_ret)
                self._bocpd_last_cp_prob = cp_prob
                bocpd_cp_detected = self._bocpd_detector.is_regime_change()
                if bocpd_cp_detected:
                    self._bocpd_cp_count += 1
                    logger.info(
                        "DrawdownControlOverlay: BOCPD change-point at %s "
                        "(cp_prob=%.3f, count=%d)",
                        dt, cp_prob, self._bocpd_cp_count,
                    )

            # BOCPD cooldown extension (applied to current cooldown if active)
            if self._in_cooldown and bocpd_cp_detected:
                self._cooldown_remaining += self.bocpd_cooldown_extension
                self._reentry_cooldown_total += self.bocpd_cooldown_extension
                logger.info(
                    "DrawdownControlOverlay: BOCPD extended cooldown at %s "
                    "(+%d days, remaining=%d)",
                    dt, self.bocpd_cooldown_extension,
                    self._cooldown_remaining,
                )

            # Stop-out check — DEFER effect to dt+1 (PIT safety)
            # Only check when NOT in cooldown (avoid re-triggering during cash)
            if not self._stopped_out and not self._in_cooldown and dd <= self.threshold:
                logger.info(
                    "DrawdownControlOverlay: STOP-OUT detected at %s "
                    "(DD=%.2f%%, threshold=%.2f%%) — deferred to next day",
                    dt, dd * 100, self.threshold * 100,
                )
                self._stopped_out = True
                _pending_stop_out = True

            # BOCPD risk gating — DEFER effect to dt+1 (PIT safety)
            if bocpd_cp_detected and not self._in_cooldown:
                _pending_bocpd_gate = True

        # Carry deferred-action flags to the next apply() call so that a
        # stop-out or BOCPD gate triggered on the last day of the current
        # batch is correctly applied at the start of the next batch.
        self._pending_stop_out = _pending_stop_out
        self._pending_bocpd_gate = _pending_bocpd_gate

        # Persist state
        state["drawdown_control"] = self.snapshot_state(
            hmm_reentry_blocked_count=hmm_reentry_blocked_count,
            gmm_reentry_blocked_count=gmm_reentry_blocked_count,
        )

        return result

    def snapshot_state(
        self,
        hmm_reentry_blocked_count: int = 0,
        gmm_reentry_blocked_count: int = 0,
    ) -> Dict[str, Any]:
        """Return a full snapshot of overlay state for persistence.

        Used both at the end of ``apply()`` and by the pipeline after
        post-sync reconciliation so that *all* fields (not just nav/hwm)
        carry across batches (L3 Blocker 3 fix).
        """
        return {
            "hwm": self._hwm,
            "nav": self._nav,
            "initial_nav": self._initial_nav,
            "in_cooldown": self._in_cooldown,
            "cooldown_remaining": self._cooldown_remaining,
            "stopped_out": self._stopped_out,
            "global_dd_blocked": self._global_dd_blocked,
            "bocpd_cp_count": self._bocpd_cp_count,
            "bocpd_last_cp_prob": self._bocpd_last_cp_prob,
            "pending_stop_out": self._pending_stop_out,
            "pending_bocpd_gate": self._pending_bocpd_gate,
            "reentry_cooldown_total": self._reentry_cooldown_total,
            "hmm_reentry_enabled": self.hmm_reentry_enabled,
            "hmm_bear_reentry_threshold": self.hmm_bear_reentry_threshold,
            "hmm_reentry_cooldown_extension": self.hmm_reentry_cooldown_extension,
            "max_reentry_cooldown_days": self.max_reentry_cooldown_days,
            "hmm_reentry_blocked_count": hmm_reentry_blocked_count,
            "gmm_bull_reentry_enabled": self.gmm_bull_reentry_enabled,
            "gmm_bull_confidence": self.gmm_bull_confidence,
            "gmm_partial_reentry_scale": self.gmm_partial_reentry_scale,
            "gmm_reentry_cooldown_extension": self.gmm_reentry_cooldown_extension,
            "gmm_reentry_blocked_count": gmm_reentry_blocked_count,
            "max_global_dd": self.max_global_dd,
            "estimated_cost_bps": self.estimated_cost_bps,
            "prev_weights": (
                self._prev_weights.tolist()
                if self._prev_weights is not None else None
            ),
            "batch_start_nav": self._batch_start_nav,
            "batch_start_hwm": self._batch_start_hwm,
        }

    def _restore_state(self, state: Dict[str, Any]) -> None:
        dd_state = state.get("drawdown_control", {})
        if dd_state:
            self._hwm = dd_state.get("hwm", 1.0)
            self._nav = dd_state.get("nav", 1.0)
            self._initial_nav = dd_state.get("initial_nav", 1.0)
            self._in_cooldown = dd_state.get("in_cooldown", False)
            self._cooldown_remaining = dd_state.get("cooldown_remaining", 0)
            self._stopped_out = dd_state.get("stopped_out", False)
            self._global_dd_blocked = dd_state.get("global_dd_blocked", False)
            self._bocpd_cp_count = dd_state.get("bocpd_cp_count", 0)
            self._bocpd_last_cp_prob = dd_state.get("bocpd_last_cp_prob", 0.0)
            # Restore deferred-action flags so a stop-out or BOCPD gate
            # triggered on the last day of a previous batch is not lost.
            self._pending_stop_out = dd_state.get("pending_stop_out", False)
            self._pending_bocpd_gate = dd_state.get("pending_bocpd_gate", False)
            self._reentry_cooldown_total = dd_state.get(
                "reentry_cooldown_total",
                self._cooldown_remaining,
            )
            self.hmm_reentry_enabled = dd_state.get(
                "hmm_reentry_enabled",
                self.hmm_reentry_enabled,
            )
            self.hmm_bear_reentry_threshold = dd_state.get(
                "hmm_bear_reentry_threshold",
                self.hmm_bear_reentry_threshold,
            )
            self.hmm_reentry_cooldown_extension = dd_state.get(
                "hmm_reentry_cooldown_extension",
                self.hmm_reentry_cooldown_extension,
            )
            self.max_reentry_cooldown_days = dd_state.get(
                "max_reentry_cooldown_days",
                self.max_reentry_cooldown_days,
            )
            self.gmm_bull_reentry_enabled = dd_state.get(
                "gmm_bull_reentry_enabled",
                self.gmm_bull_reentry_enabled,
            )
            self.gmm_bull_confidence = dd_state.get(
                "gmm_bull_confidence",
                self.gmm_bull_confidence,
            )
            self.gmm_partial_reentry_scale = dd_state.get(
                "gmm_partial_reentry_scale",
                self.gmm_partial_reentry_scale,
            )
            self.gmm_reentry_cooldown_extension = dd_state.get(
                "gmm_reentry_cooldown_extension",
                self.gmm_reentry_cooldown_extension,
            )
            self.max_global_dd = dd_state.get("max_global_dd", self.max_global_dd)
            self.estimated_cost_bps = dd_state.get(
                "estimated_cost_bps",
                self.estimated_cost_bps,
            )
            # Restore prev_weights for turnover cost estimation continuity
            prev_w = dd_state.get("prev_weights", None)
            if prev_w is not None:
                self._prev_weights = np.asarray(prev_w, dtype=float)
            else:
                self._prev_weights = None
            # Restore batch-start NAV/HWM for sync_executed_returns() chaining.
            # If not present (older state format), fall back to current nav/hwm
            # which will be overwritten by apply() anyway.
            self._batch_start_nav = dd_state.get("batch_start_nav", self._nav)
            self._batch_start_hwm = dd_state.get("batch_start_hwm", self._hwm)

    def sync_executed_returns(self, net_rets: np.ndarray) -> None:
        """Re-sync internal NAV / HWM to the executed (post-cost) equity curve.

        Call after ``apply_realistic_tc()`` to ensure ``max_global_dd``
        constrains the same net equity curve used by reported MaxDD.

        NAV Chaining (L3 Blocker 1 fix)
        --------------------------------
        Chains from the *batch-start* NAV/HWM captured at the top of
        ``apply()``, NOT from ``_initial_nav``.  This preserves cross-batch
        continuity: if the prior batch ended at NAV=0.80 and the current
        batch's executed return is +1%, the reconciled NAV is 0.808, not
        the incorrect 1.01 that would result from starting at initial_nav=1.

        PIT Safety
        ----------
        Only updates ``_nav`` and ``_hwm``.  Does NOT retroactively alter
        any weight decisions from the current batch.  The reconciled state
        affects ``max_global_dd`` re-entry checks in the *next* batch only
        (unless the pipeline performs additional post-sync reconciliation).

        Parameters
        ----------
        net_rets : np.ndarray
            Post-cost daily return series from ``apply_realistic_tc()``.
        """
        net_rets = np.asarray(net_rets, dtype=float)
        if net_rets.size == 0:
            return
        # Chain from batch-start NAV (persisted prior-batch end NAV),
        # not from initial_nav which is always 1.0.
        base_nav = self._batch_start_nav
        cum = base_nav * np.cumprod(1.0 + net_rets)
        self._nav = float(cum[-1])
        # HWM: max of prior-batch HWM and all points in the current batch
        self._hwm = float(max(self._batch_start_hwm, float(np.max(cum))))
