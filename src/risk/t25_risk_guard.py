from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class SettlementBucket:
    settlement_date: str
    trade_date: str
    ticker: str
    quantity: float
    avg_price: float
    total_value: float
    direction: str


@dataclass
class PurchasingPowerState:
    as_of_date: str
    total_cash: float
    unsettled_buy_t0: float
    unsettled_buy_t1: float
    unsettled_buy_t2: float
    unsettled_sell_t0: float
    unsettled_sell_t1: float
    unsettled_sell_t2: float
    available_now: float
    projected_t1: float
    projected_t2: float
    projected_t3: float


class T25RiskGuard:
    def __init__(
        self,
        initial_cash: float,
        settlement_delay_days: int = 2,
        safety_buffer: float = 0.05,
        state_file: str | Path = ".ly_state/session/t25_risk_guard_status.json",
    ) -> None:
        if settlement_delay_days < 0:
            raise ValueError("settlement_delay_days must be >= 0")
        if safety_buffer < 0.0:
            raise ValueError("safety_buffer must be >= 0")
        self.initial_cash = float(initial_cash)
        self.settlement_delay_days = settlement_delay_days
        self.safety_buffer = float(safety_buffer)
        self.current_state: PurchasingPowerState | None = None
        self.settlement_buckets: dict[str, list[SettlementBucket]] = {}
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def _add_business_days(self, start_date: pd.Timestamp, num_days: int) -> pd.Timestamp:
        return start_date + pd.offsets.BusinessDay(num_days)

    def _business_days_between(self, start_date: pd.Timestamp, end_date: pd.Timestamp) -> int:
        if end_date < start_date:
            return 0
        return int(np.busday_count(start_date.date(), end_date.date()))

    def _trades_frame(self, pending_trades: list[dict]) -> pd.DataFrame:
        frame = pd.DataFrame(pending_trades).copy()
        if frame.empty:
            return pd.DataFrame(
                columns=[
                    "trade_date",
                    "ticker",
                    "quantity",
                    "price",
                    "direction",
                    "settlement_date",
                    "business_days_to_settle",
                    "total_value",
                ]
            )
        required = {"trade_date", "ticker", "quantity", "price", "direction"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"pending_trades missing required fields: {sorted(missing)}")
        frame = frame.loc[:, ["trade_date", "ticker", "quantity", "price", "direction"]]
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        frame["quantity"] = pd.to_numeric(frame["quantity"], errors="raise")
        frame["price"] = pd.to_numeric(frame["price"], errors="raise")
        frame["direction"] = frame["direction"].astype("string").str.upper()
        invalid = frame.loc[~frame["direction"].isin(["BUY", "SELL"]), "direction"]
        if not invalid.empty:
            raise ValueError("direction must be BUY or SELL")
        frame["settlement_date"] = frame["trade_date"] + pd.offsets.BusinessDay(self.settlement_delay_days)
        frame["total_value"] = frame["quantity"] * frame["price"]
        return frame

    def update_state(
        self,
        as_of_date: str,
        current_cash: float,
        pending_trades: list[dict],
    ) -> PurchasingPowerState:
        as_of_ts = pd.Timestamp(as_of_date)
        trades = self._trades_frame(pending_trades)
        self.settlement_buckets.clear()

        if not trades.empty:
            trades["business_days_to_settle"] = np.busday_count(
                np.full(len(trades), as_of_ts.date(), dtype="datetime64[D]"),
                trades["settlement_date"].to_numpy(dtype="datetime64[D]"),
            )
            horizon_trades = trades.loc[trades["business_days_to_settle"].between(0, 2)].copy()
        else:
            trades["business_days_to_settle"] = pd.Series(dtype="int64")
            horizon_trades = trades

        if not horizon_trades.empty:
            grouped = horizon_trades.groupby(["direction", "business_days_to_settle"])["total_value"].sum()
        else:
            grouped = pd.Series(dtype="float64")

        def amount(direction: str, horizon: int) -> float:
            return float(grouped.get((direction, horizon), 0.0))

        unsettled_buy_t0 = amount("BUY", 0)
        unsettled_buy_t1 = amount("BUY", 1)
        unsettled_buy_t2 = amount("BUY", 2)
        unsettled_sell_t0 = amount("SELL", 0)
        unsettled_sell_t1 = amount("SELL", 1)
        unsettled_sell_t2 = amount("SELL", 2)

        total_unsettled_buys = unsettled_buy_t0 + unsettled_buy_t1 + unsettled_buy_t2
        available_now = max(0.0, float(current_cash) - total_unsettled_buys * (1.0 + self.safety_buffer))
        projected_t1 = float(current_cash) - unsettled_buy_t0 + unsettled_sell_t0
        projected_t2 = projected_t1 - unsettled_buy_t1 + unsettled_sell_t1
        projected_t3 = projected_t2 - unsettled_buy_t2 + unsettled_sell_t2

        self.current_state = PurchasingPowerState(
            as_of_date=as_of_ts.strftime("%Y-%m-%d"),
            total_cash=float(current_cash),
            unsettled_buy_t0=unsettled_buy_t0,
            unsettled_buy_t1=unsettled_buy_t1,
            unsettled_buy_t2=unsettled_buy_t2,
            unsettled_sell_t0=unsettled_sell_t0,
            unsettled_sell_t1=unsettled_sell_t1,
            unsettled_sell_t2=unsettled_sell_t2,
            available_now=available_now,
            projected_t1=projected_t1,
            projected_t2=projected_t2,
            projected_t3=projected_t3,
        )

        if not trades.empty:
            for settlement_date, group in trades.groupby(trades["settlement_date"].dt.strftime("%Y-%m-%d")):
                self.settlement_buckets[settlement_date] = [
                    SettlementBucket(
                        settlement_date=settlement_date,
                        trade_date=row.trade_date.strftime("%Y-%m-%d"),
                        ticker=str(row.ticker),
                        quantity=float(row.quantity),
                        avg_price=float(row.price),
                        total_value=float(row.total_value),
                        direction=str(row.direction),
                    )
                    for row in group.itertuples(index=False)
                ]

        self._save_state()
        return self.current_state

    def check_allocation(self, proposed_trades: list[dict]) -> tuple[bool, str, dict]:
        if self.current_state is None:
            return False, "Risk Guard not initialized. Call update_state() first.", {}
        frame = pd.DataFrame(proposed_trades)
        if frame.empty:
            total_buy_value = 0.0
        else:
            required = {"quantity", "price", "direction"}
            missing = required.difference(frame.columns)
            if missing:
                raise ValueError(f"proposed_trades missing required fields: {sorted(missing)}")
            buy_mask = frame["direction"].astype("string").str.upper().eq("BUY")
            total_buy_value = float(
                pd.to_numeric(frame.loc[buy_mask, "quantity"], errors="raise")
                .mul(pd.to_numeric(frame.loc[buy_mask, "price"], errors="raise"))
                .sum()
            )

        available = self.current_state.available_now
        utilization = float("inf") if available <= 0.0 and total_buy_value > 0.0 else (total_buy_value / available * 100.0 if available > 0.0 else 0.0)
        if total_buy_value > available:
            shortage = total_buy_value - available
            return (
                False,
                (
                    f"OVER-ALLOCATION DETECTED: Proposed buys ({total_buy_value:,.0f} VND) exceed "
                    f"available purchasing power ({available:,.0f} VND). Shortage: {shortage:,.0f} VND"
                ),
                {
                    "proposed_buy_value": total_buy_value,
                    "available_purchasing_power": available,
                    "shortage": shortage,
                    "utilization_pct": utilization,
                    "safety_buffer_pct": self.safety_buffer * 100.0,
                },
            )
        return (
            True,
            (
                f"ALLOCATION SAFE: Proposed buys ({total_buy_value:,.0f} VND) within "
                f"available purchasing power ({available:,.0f} VND). Utilization: {utilization:.1f}%"
            ),
            {
                "proposed_buy_value": total_buy_value,
                "available_purchasing_power": available,
                "remaining_power": available - total_buy_value,
                "utilization_pct": utilization,
                "safety_buffer_pct": self.safety_buffer * 100.0,
            },
        )

    def get_max_position_size(self, ticker: str, price: float) -> float:
        del ticker
        if self.current_state is None or price <= 0:
            return 0.0
        return float(np.floor((self.current_state.available_now / price) / 100.0) * 100.0)

    def get_settlement_schedule(self) -> pd.DataFrame:
        if not self.settlement_buckets:
            return pd.DataFrame()
        rows = [asdict(bucket) for buckets in self.settlement_buckets.values() for bucket in buckets]
        return pd.DataFrame(rows).sort_values(["settlement_date", "ticker", "trade_date"]).reset_index(drop=True)

    def _save_state(self) -> None:
        if self.current_state is None:
            return
        payload = {
            "purchasing_power_state": asdict(self.current_state),
            "settlement_buckets": {
                date: [asdict(bucket) for bucket in buckets] for date, buckets in self.settlement_buckets.items()
            },
            "config": {
                "initial_cash": self.initial_cash,
                "settlement_delay_days": self.settlement_delay_days,
                "safety_buffer": self.safety_buffer,
            },
        }
        self.state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_state(self) -> bool:
        if not self.state_file.exists():
            return False
        payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.current_state = PurchasingPowerState(**payload["purchasing_power_state"])
        self.settlement_buckets = {
            date: [SettlementBucket(**bucket) for bucket in buckets]
            for date, buckets in payload.get("settlement_buckets", {}).items()
        }
        return True
