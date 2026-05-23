"""
T+2 settlement cash guard for VN equity market (T25 = T+2.5 business days).

Public API
----------
T25RiskGuard(initial_cash, safety_buffer, state_file)
  .update_state(as_of_date, current_cash, pending_trades) -> CashProjectionState
  .check_allocation(proposed_trades) -> (bool, str, dict)
  .get_max_position_size(ticker, price) -> float
  .get_settlement_schedule() -> pd.DataFrame
  .load_state() -> bool
  ._business_days_between(t1, t2) -> int

Settlement convention: T+2 business days (VN standard).
VN lot size: 100 shares (rounded down to nearest 100 for max position).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


_VN_LOT = 100  # VN market lot size


@dataclass
class CashProjectionState:
    as_of_date: str
    current_cash: float
    # Unsettled BUY obligations by settlement horizon
    unsettled_buy_t0: float  # settles today (T+0 relative to as_of)
    unsettled_buy_t1: float  # settles in 1 business day
    unsettled_buy_t2: float  # settles in 2 business days
    # Projected cash after netting buys and sells at each horizon
    projected_t1: float
    projected_t2: float
    projected_t3: float
    # Available cash now = current_cash - t0 - t1 - t2 obligations, floored at 0, minus safety buffer
    available_now: float
    # Raw settlement schedule rows for get_settlement_schedule()
    schedule: list[dict[str, Any]]


class T25RiskGuard:
    """
    Cash guard that tracks T+2 settlement obligations and prevents over-allocation.

    Parameters
    ----------
    initial_cash : float
        Starting cash balance.
    safety_buffer : float
        Fraction of current_cash reserved as safety margin (default 0.05 = 5%).
    state_file : Path | str | None
        JSON file for state persistence.  None = no persistence.
    """

    def __init__(
        self,
        initial_cash: float = 0.0,
        safety_buffer: float = 0.05,
        state_file: Path | str | None = None,
    ) -> None:
        self.initial_cash = initial_cash
        self.safety_buffer = safety_buffer
        self.state_file = Path(state_file) if state_file is not None else None
        self.current_state: CashProjectionState | None = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def _business_days_between(self, t1: pd.Timestamp, t2: pd.Timestamp) -> int:
        """Number of business days from t1 (exclusive) to t2 (inclusive)."""
        if t2 <= t1:
            return 0
        return int(len(pd.bdate_range(t1 + pd.Timedelta(days=1), t2)))

    # ------------------------------------------------------------------
    # Core state update
    # ------------------------------------------------------------------

    def update_state(
        self,
        as_of_date: str,
        current_cash: float,
        pending_trades: list[dict[str, Any]],
    ) -> CashProjectionState:
        """
        Compute cash projection from pending trades.

        Each trade dict must have:
            trade_date  : str  (YYYY-MM-DD)
            ticker      : str
            quantity    : int | float
            price       : float
            direction   : "BUY" | "SELL"

        Settlement date = trade_date + 2 business days.
        Horizon bucket = business days from as_of_date to settlement_date.
        """
        as_of = pd.Timestamp(as_of_date)

        buy_t0 = buy_t1 = buy_t2 = 0.0
        sell_t0 = sell_t1 = sell_t2 = 0.0
        schedule_rows: list[dict[str, Any]] = []

        for trade in pending_trades:
            direction = trade["direction"].upper()
            if direction not in ("BUY", "SELL"):
                raise ValueError(
                    f"direction must be 'BUY' or 'SELL', got '{trade['direction']}'"
                )
            trade_dt = pd.Timestamp(trade["trade_date"])
            value = float(trade["quantity"]) * float(trade["price"])

            # Settlement = trade_date + 2 business days
            settlement_dt = trade_dt + pd.offsets.BusinessDay(2)
            horizon = self._business_days_between(as_of, settlement_dt)

            settlement_str = settlement_dt.strftime("%Y-%m-%d")
            schedule_rows.append(
                {
                    "ticker": trade["ticker"],
                    "trade_date": trade["trade_date"],
                    "settlement_date": settlement_str,
                    "direction": direction,
                    "value": value,
                    "horizon": horizon,
                }
            )

            if direction == "BUY":
                if horizon == 0:
                    buy_t0 += value
                elif horizon == 1:
                    buy_t1 += value
                elif horizon == 2:
                    buy_t2 += value
                # horizon > 2: not yet within settlement window, ignore for available_now
            else:  # SELL
                if horizon == 0:
                    sell_t0 += value
                elif horizon == 1:
                    sell_t1 += value
                elif horizon == 2:
                    sell_t2 += value

        # Projected cash at each horizon (cumulative net)
        projected_t1 = current_cash - buy_t0 + sell_t0
        projected_t2 = projected_t1 - buy_t1 + sell_t1
        projected_t3 = projected_t2 - buy_t2 + sell_t2

        # Available now = cash minus each obligation grossed up by safety_buffer, floored at 0
        # e.g. buffer=0.05 means each $1 of obligation reserves $1.05
        buf = 1.0 + self.safety_buffer
        available_now = max(0.0, current_cash - buy_t0 * buf - buy_t1 * buf - buy_t2 * buf)

        state = CashProjectionState(
            as_of_date=as_of_date,
            current_cash=current_cash,
            unsettled_buy_t0=buy_t0,
            unsettled_buy_t1=buy_t1,
            unsettled_buy_t2=buy_t2,
            projected_t1=projected_t1,
            projected_t2=projected_t2,
            projected_t3=projected_t3,
            available_now=available_now,
            schedule=schedule_rows,
        )
        self.current_state = state
        self._save_state()
        return state

    # ------------------------------------------------------------------
    # Allocation check
    # ------------------------------------------------------------------

    def check_allocation(
        self,
        proposed_trades: list[dict[str, Any]],
    ) -> tuple[bool, str, dict[str, Any]]:
        """
        Check whether proposed BUY trades fit within available_now.

        Returns (is_safe, message, details).
        """
        if self.current_state is None:
            return False, "State not initialised. Call update_state first.", {}

        proposed_buy_value = sum(
            float(t["quantity"]) * float(t["price"])
            for t in proposed_trades
            if t.get("direction", "BUY").upper() == "BUY"
        )

        available = self.current_state.available_now
        details: dict[str, Any] = {
            "proposed_buy_value": proposed_buy_value,
            "available_now": available,
        }

        if proposed_buy_value > available:
            shortage = proposed_buy_value - available
            details["shortage"] = shortage
            return (
                False,
                f"OVER-ALLOCATION DETECTED: proposed {proposed_buy_value:.2f} > available {available:.2f} (shortage {shortage:.2f})",
                details,
            )

        return True, "Allocation within limits.", details

    # ------------------------------------------------------------------
    # Max position size
    # ------------------------------------------------------------------

    def get_max_position_size(self, ticker: str, price: float) -> float:
        """
        Maximum shares purchasable given available_now, rounded down to VN lot size (100).
        """
        if self.current_state is None:
            return 0.0
        if price <= 0:
            return 0.0
        raw_shares = self.current_state.available_now / price
        lots = int(raw_shares // _VN_LOT)
        return float(lots * _VN_LOT)

    # ------------------------------------------------------------------
    # Settlement schedule
    # ------------------------------------------------------------------

    def get_settlement_schedule(self) -> pd.DataFrame:
        """Return pending trades sorted by settlement_date then ticker."""
        if self.current_state is None or not self.current_state.schedule:
            return pd.DataFrame(
                columns=["ticker", "trade_date", "settlement_date", "direction", "value", "horizon"]
            )
        df = pd.DataFrame(self.current_state.schedule)
        return df.sort_values(["settlement_date", "ticker"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        if self.state_file is None or self.current_state is None:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as fh:
            json.dump(asdict(self.current_state), fh, indent=2)

    def load_state(self) -> bool:
        """Load state from state_file. Returns True on success."""
        if self.state_file is None or not self.state_file.exists():
            return False
        with open(self.state_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.current_state = CashProjectionState(**data)
        return True
