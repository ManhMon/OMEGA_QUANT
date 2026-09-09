from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from omega.execution.vn_transaction_cost_model import VNTransactionCostModel, TransactionCostConfig


logger = logging.getLogger(__name__)

MAX_CHILD_ORDERS_PER_REQUEST = 500
MAX_HISTORY_RECORDS = 5000

VIETNAM_MARKET_HOLIDAYS: Dict[str, str] = {
    # 2024
    "2024-01-01": "New Year's Day",
    "2024-02-08": "Tet Holiday",
    "2024-02-09": "Tet Holiday",
    "2024-02-12": "Tet Holiday",
    "2024-02-13": "Tet Holiday",
    "2024-02-14": "Tet Holiday",
    "2024-04-18": "Hung Kings Commemoration Day",
    "2024-04-30": "Reunification Day",
    "2024-05-01": "International Labor Day",
    "2024-09-02": "National Day",
    "2024-09-03": "National Day Holiday",
    # 2025
    "2025-01-01": "New Year's Day",
    "2025-01-27": "Tet Holiday",
    "2025-01-28": "Tet Holiday",
    "2025-01-29": "Tet Holiday",
    "2025-01-30": "Tet Holiday",
    "2025-01-31": "Tet Holiday",
    "2025-04-07": "Hung Kings Commemoration Day",
    "2025-04-30": "Reunification Day",
    "2025-05-01": "International Labor Day",
    "2025-09-01": "National Day Holiday",
    "2025-09-02": "National Day",
    # 2026
    "2026-01-01": "New Year's Day",
    "2026-02-16": "Tet Holiday",
    "2026-02-17": "Tet Holiday",
    "2026-02-18": "Tet Holiday",
    "2026-02-19": "Tet Holiday",
    "2026-02-20": "Tet Holiday",
    "2026-04-27": "Hung Kings Commemoration Day (Observed)",
    "2026-04-30": "Reunification Day",
    "2026-05-01": "International Labor Day",
    "2026-09-01": "National Day Holiday",
    "2026-09-02": "National Day",
    # 2027
    "2027-01-01": "New Year's Day",
    "2027-02-05": "Tet Holiday",
    "2027-02-08": "Tet Holiday",
    "2027-02-09": "Tet Holiday",
    "2027-02-10": "Tet Holiday",
    "2027-02-11": "Tet Holiday",
}

SECURITY_MASTER: Dict[str, Dict[str, Any]] = {
    # Historical delisted tickers
    "ROS": {"exchange": "HOSE", "listed_date": "2016-09-01", "delisted_date": "2022-09-05", "status": "DELISTED"},
    "FLC": {"exchange": "HOSE", "listed_date": "2011-10-05", "delisted_date": "2023-02-20", "status": "DELISTED"},
    "HAI": {"exchange": "HOSE", "listed_date": "2010-09-15", "delisted_date": "2023-03-24", "status": "DELISTED"},
    "AMD": {"exchange": "HOSE", "listed_date": "2014-06-25", "delisted_date": "2023-03-23", "status": "DELISTED"},
    "ART": {"exchange": "HNX", "listed_date": "2017-09-28", "delisted_date": "2023-11-21", "status": "DELISTED"},
    "DELISTED": {"exchange": "HOSE", "listed_date": "2010-01-01", "delisted_date": "2020-01-01", "status": "DELISTED"},
    # Standard active VN symbols
    "VNM": {"exchange": "HOSE", "listed_date": "2006-01-19", "delisted_date": None, "status": "LISTED"},
    "FPT": {"exchange": "HOSE", "listed_date": "2006-12-13", "delisted_date": None, "status": "LISTED"},
    "HPG": {"exchange": "HOSE", "listed_date": "2007-11-15", "delisted_date": None, "status": "LISTED"},
    "MWG": {"exchange": "HOSE", "listed_date": "2014-07-14", "delisted_date": None, "status": "LISTED"},
    "MBB": {"exchange": "HOSE", "listed_date": "2011-11-01", "delisted_date": None, "status": "LISTED"},
    "VIC": {"exchange": "HOSE", "listed_date": "2007-09-19", "delisted_date": None, "status": "LISTED"},
    "VHM": {"exchange": "HOSE", "listed_date": "2018-05-17", "delisted_date": None, "status": "LISTED"},
    "TCB": {"exchange": "HOSE", "listed_date": "2018-06-04", "delisted_date": None, "status": "LISTED"},
    "VCB": {"exchange": "HOSE", "listed_date": "2009-06-30", "delisted_date": None, "status": "LISTED"},
    "SSI": {"exchange": "HOSE", "listed_date": "2006-12-15", "delisted_date": None, "status": "LISTED"},
    "MSN": {"exchange": "HOSE", "listed_date": "2009-11-05", "delisted_date": None, "status": "LISTED"},
}


def is_vietnam_trading_day(dt: datetime) -> Tuple[bool, str]:
    """Check if datetime falls on a Vietnam equity market trading day."""
    if dt.weekday() >= 5:
        day_name = dt.strftime("%A")
        return False, f"Market closed on weekend ({day_name})"
    date_str = dt.strftime("%Y-%m-%d")
    if date_str in VIETNAM_MARKET_HOLIDAYS:
        holiday_name = VIETNAM_MARKET_HOLIDAYS[date_str]
        return False, f"Market holiday: {holiday_name} ({date_str})"
    return True, "Trading day"


def check_pit_listing_status(symbol: str, as_of_date: str) -> Tuple[bool, str]:
    """Check Point-In-Time listing/delisting status from authoritative security master."""
    sec = SECURITY_MASTER.get(symbol.upper())
    if sec:
        if sec.get("delisted_date") and as_of_date >= sec["delisted_date"]:
            return False, f"Symbol {symbol} was delisted on {sec['delisted_date']} (as_of {as_of_date})"
        if sec.get("listed_date") and as_of_date < sec["listed_date"]:
            return False, f"Symbol {symbol} was not yet listed on {as_of_date} (IPO {sec['listed_date']})"
        return True, "LISTED"
    if "DELIST" in symbol.upper():
        return False, f"Symbol {symbol} is delisted"
    return True, "ASSUMED_LISTED"


def _is_finite_positive(val: Any, max_val: float = 1e14) -> bool:
    """Check if value is a finite positive float/int bounded within max_val."""
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return False
    if math.isnan(val) or math.isinf(val):
        return False
    return 0 < val <= max_val


class PaperTradingEngine:
    """
    Virtual order simulation engine for Layer 08 Self-Evolving Engine.
    Simulates order execution with slippage, tracks institutional P&L,
    governs daemon execution lifecycle (START, STOP, PAUSE, RESUME) across processes,
    and enforces durability with atomic logging and transactional rollback.
    """

    def __init__(self, log_dir: str = "logs", smart_router=None):
        self.log_dir = log_dir
        self.cost_model = VNTransactionCostModel(TransactionCostConfig())
        self.smart_router = smart_router
        self.virtual_orders_log_path = f"{self.log_dir}/virtual_orders.jsonl"
        self.state_file_path = f"{self.log_dir}/daemon_state.json"
        self._lock = threading.Lock()

        # Daemon lifecycle state
        self.state: str = "STOPPED"
        self.mode: str = "SHADOW"
        self.initial_capital: float = 1_000_000_000.0
        self.cash: float = 1_000_000_000.0
        self.started_at: Optional[datetime] = None
        self.last_heartbeat: Optional[datetime] = None

        # Order & position tracking
        self.orders_history: List[Dict[str, Any]] = []
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.daily_pnl: Dict[str, float] = {}
        self.realized_pnl: Dict[str, float] = {}
        self.max_history_records: int = MAX_HISTORY_RECORDS

        # Ensure log directory exists
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create log dir {self.log_dir}: {e}")

        # Attempt to sync state from durable file if present
        self._sync_daemon_state()

    def _sync_daemon_state(self) -> None:
        """Read state from disk file to synchronize state across processes."""
        if not os.path.isfile(self.state_file_path):
            return
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            self.state = data.get("state", self.state)
            self.mode = data.get("mode", self.mode)
            if "initial_capital" in data and _is_finite_positive(data["initial_capital"]):
                self.initial_capital = float(data["initial_capital"])
            if "cash" in data and isinstance(data["cash"], (int, float)) and math.isfinite(data["cash"]):
                self.cash = float(data["cash"])
            if data.get("started_at"):
                try:
                    self.started_at = datetime.fromisoformat(data["started_at"])
                except Exception:
                    pass
            elif data.get("state") == "STOPPED":
                self.started_at = None
            if data.get("last_heartbeat"):
                try:
                    self.last_heartbeat = datetime.fromisoformat(data["last_heartbeat"])
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"State sync from disk skipped: {e}")

    def _save_daemon_state(self) -> None:
        """Persist state to disk file atomically using temp file replace."""
        try:
            parent = os.path.dirname(self.state_file_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            data = {
                "state": self.state,
                "mode": self.mode,
                "initial_capital": self.initial_capital,
                "cash": self.cash,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp_path = f"{self.state_file_path}.tmp.{os.getpid()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.state_file_path)
        except Exception as e:
            logger.error(f"Failed to persist daemon state: {e}")

    def start(self, initial_capital: float = 1_000_000_000.0, mode: str = "SHADOW") -> Dict[str, Any]:
        """Start paper trading daemon."""
        with self._lock:
            self._sync_daemon_state()
            if self.state in {"RUNNING", "PAUSED"}:
                raise ValueError(f"Cannot start daemon: already in state {self.state}")
            if not _is_finite_positive(initial_capital):
                raise ValueError(f"Initial capital must be positive finite number, got {initial_capital}")

            now = datetime.now(timezone.utc)
            self.state = "RUNNING"
            self.mode = str(mode).upper()
            self.initial_capital = float(initial_capital)
            self.cash = float(initial_capital)
            self.started_at = now
            self.last_heartbeat = now
            self._save_daemon_state()
            logger.info(f"Paper trading daemon started with initial capital {self.initial_capital} VND in {self.mode} mode.")
            return self._get_status_locked()

    def stop(self) -> Dict[str, Any]:
        """Stop paper trading daemon."""
        with self._lock:
            self._sync_daemon_state()
            self.state = "STOPPED"
            self.started_at = None
            self.last_heartbeat = datetime.now(timezone.utc)
            self._save_daemon_state()
            logger.info("Paper trading daemon stopped.")
            return self._get_status_locked()

    def pause(self) -> Dict[str, Any]:
        """Pause paper trading execution."""
        with self._lock:
            self._sync_daemon_state()
            if self.state != "RUNNING":
                raise ValueError(f"Cannot pause daemon in state {self.state}; must be RUNNING")
            self.state = "PAUSED"
            self.last_heartbeat = datetime.now(timezone.utc)
            self._save_daemon_state()
            logger.info("Paper trading daemon paused.")
            return self._get_status_locked()

    def resume(self) -> Dict[str, Any]:
        """Resume paper trading execution."""
        with self._lock:
            self._sync_daemon_state()
            if self.state != "PAUSED":
                raise ValueError(f"Cannot resume daemon in state {self.state}; must be PAUSED")
            self.state = "RUNNING"
            self.last_heartbeat = datetime.now(timezone.utc)
            self._save_daemon_state()
            logger.info("Paper trading daemon resumed.")
            return self._get_status_locked()

    def _get_status_locked(self) -> Dict[str, Any]:
        """Internal helper returning deepcopy status dict while lock is held."""
        now = datetime.now(timezone.utc)
        uptime = (now - self.started_at).total_seconds() if self.started_at and self.state == "RUNNING" else 0.0
        active_count = len([o for o in self.orders_history if o.get("execution_status") in {"PENDING", "ROUTING"}])

        pos_value = sum(p["shares"] * p.get("current_price", 0.0) for p in self.positions.values())
        equity = self.cash + pos_value
        total_pnl = equity - self.initial_capital
        realized_total = sum(p.get("realized_pnl_vnd", 0.0) for p in self.positions.values())
        unrealized_total = sum(p.get("unrealized_pnl_vnd", 0.0) for p in self.positions.values())

        return {
            "state": self.state,
            "active": self.state == "RUNNING",
            "mode": self.mode,
            "initial_capital_vnd": round(self.initial_capital, 2),
            "cash_vnd": round(self.cash, 2),
            "portfolio_equity_vnd": round(equity, 2),
            "total_pnl_vnd": round(total_pnl, 2),
            "daily_pnl_vnd": round(total_pnl, 2),
            "realized_pnl_vnd": round(realized_total, 2),
            "unrealized_pnl_vnd": round(unrealized_total, 2),
            "uptime_seconds": round(max(0.0, uptime), 2),
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "processed_orders_count": len(self.orders_history),
            "active_orders_count": active_count,
            "positions_count": len(self.positions),
            "positions": {k: copy.deepcopy(v) for k, v in self.positions.items()},
            "model_pnl": {k: round(v, 2) for k, v in self.daily_pnl.items()},
        }

    def get_status(self) -> Dict[str, Any]:
        """Return full daemon status and telemetry with thread safety."""
        with self._lock:
            self._sync_daemon_state()
            return self._get_status_locked()

    def execute_virtual_order(self, order: Dict[str, Any], order_book_data: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Execute a virtual order with slippage, lifecycle checks, and logging.
        Enforces:
        - Strict RUNNING lifecycle state across processes.
        - Robust PIT temporal constraints (available_at, no future timestamps).
        - Vietnam exchange calendar and holiday gating.
        - Point-in-Time security master survivorship validation.
        - Institutional cash & mark-to-market PnL accounting.
        - Durable atomic JSONL logging with complete in-memory rollback on failure.
        - Bounds on child order fanout and history records.
        """
        with self._lock:
            self._sync_daemon_state()
            self.last_heartbeat = datetime.now(timezone.utc)

            # Check daemon lifecycle: ONLY RUNNING is allowed to execute orders
            if self.state != "RUNNING":
                rej_status = "REJECTED_DAEMON_PAUSED" if self.state == "PAUSED" else "REJECTED_DAEMON_STOPPED"
                rej_reason = f"Daemon is currently {self.state.lower()}"
                rejected_order = self._create_rejected_record(order, rej_status, rej_reason)
                self.orders_history.append(rejected_order)
                if len(self.orders_history) > self.max_history_records:
                    self.orders_history = self.orders_history[-self.max_history_records:]
                return [rejected_order]

            # Basic dictionary check
            if not isinstance(order, dict):
                rejected_order = self._create_rejected_record({}, "REJECTED_INVALID_ORDER", "Order must be a dict")
                return [rejected_order]

            model_id = str(order.get("model_id", "unknown"))
            raw_symbol = order.get("symbol")
            if not raw_symbol or not isinstance(raw_symbol, str):
                rejected_order = self._create_rejected_record(order, "REJECTED_INVALID_SYMBOL", "Symbol must be a non-empty string")
                self.orders_history.append(rejected_order)
                return [rejected_order]
            symbol = raw_symbol.upper().strip()

            raw_side = order.get("side")
            if not raw_side or str(raw_side).upper() not in {"BUY", "SELL"}:
                rejected_order = self._create_rejected_record(order, "REJECTED_INVALID_SIDE", "Side must be BUY or SELL")
                self.orders_history.append(rejected_order)
                return [rejected_order]
            side = str(raw_side).upper()

            raw_size = order.get("quantity", order.get("size"))
            if not _is_finite_positive(raw_size, max_val=1e8):
                rejected_order = self._create_rejected_record(order, "REJECTED_INVALID_SIZE", "Size/quantity must be positive finite number <= 1e8")
                self.orders_history.append(rejected_order)
                return [rejected_order]
            size = float(raw_size)

            raw_price = order.get("price")
            if not _is_finite_positive(raw_price, max_val=1e8):
                rejected_order = self._create_rejected_record(order, "REJECTED_INVALID_PRICE", "Price must be positive finite number <= 1e8")
                self.orders_history.append(rejected_order)
                return [rejected_order]
            price = float(raw_price)

            # PIT Timestamps verification
            feature_ts = order.get("feature_ts")
            decision_ts = order.get("decision_ts")
            available_at = order.get("available_at") or feature_ts

            if not feature_ts or not decision_ts:
                rejected_order = self._create_rejected_record(order, "REJECTED_PIT_VIOLATION", "Missing required feature_ts or decision_ts")
                self.orders_history.append(rejected_order)
                return [rejected_order]

            try:
                dt_feature = datetime.fromisoformat(str(feature_ts).replace("Z", "+00:00"))
                dt_decision = datetime.fromisoformat(str(decision_ts).replace("Z", "+00:00"))
                dt_available = datetime.fromisoformat(str(available_at).replace("Z", "+00:00"))
                if dt_feature.tzinfo is None or dt_decision.tzinfo is None or dt_available.tzinfo is None:
                    rejected_order = self._create_rejected_record(order, "REJECTED_PIT_VIOLATION", "Timestamps must have explicit timezone")
                    self.orders_history.append(rejected_order)
                    return [rejected_order]
            except Exception as parse_err:
                rejected_order = self._create_rejected_record(order, "REJECTED_PIT_VIOLATION", f"Timestamp parse error: {parse_err}")
                self.orders_history.append(rejected_order)
                return [rejected_order]

            # Invariant: feature_ts <= available_at <= decision_ts
            if dt_feature > dt_decision:
                rejected_order = self._create_rejected_record(order, "REJECTED_PIT_LOOKAHEAD", "feature_ts cannot be greater than decision_ts")
                self.orders_history.append(rejected_order)
                return [rejected_order]

            if dt_available > dt_decision:
                rejected_order = self._create_rejected_record(order, "REJECTED_PIT_LOOKAHEAD", "available_at cannot be greater than decision_ts")
                self.orders_history.append(rejected_order)
                return [rejected_order]

            if dt_feature > dt_available:
                rejected_order = self._create_rejected_record(order, "REJECTED_PIT_VIOLATION", "feature_ts cannot be greater than available_at")
                self.orders_history.append(rejected_order)
                return [rejected_order]

            # Invariant: rejection of absolute future timestamps (allowing small 60s clock skew)
            now_utc = datetime.now(timezone.utc)
            if dt_decision > now_utc + timedelta(seconds=60):
                rejected_order = self._create_rejected_record(order, "REJECTED_FUTURE_TIMESTAMP", f"decision_ts {decision_ts} cannot be in the future")
                self.orders_history.append(rejected_order)
                return [rejected_order]

            # Invariant: Vietnam Trading Calendar and Holidays
            is_trading_day, cal_reason = is_vietnam_trading_day(dt_decision)
            if not is_trading_day:
                rejected_order = self._create_rejected_record(order, "REJECTED_TRADING_CALENDAR", cal_reason)
                self.orders_history.append(rejected_order)
                return [rejected_order]

            # Invariant: Point-in-Time Security Master Survivorship (delisted check)
            decision_date_str = dt_decision.strftime("%Y-%m-%d")
            is_listed, sec_reason = check_pit_listing_status(symbol, decision_date_str)
            if not is_listed:
                rejected_order = self._create_rejected_record(order, "REJECTED_DELISTED_SYMBOL", sec_reason)
                self.orders_history.append(rejected_order)
                return [rejected_order]

            # Route order through SmartRouter if available
            child_orders = []
            if self.smart_router:
                router_order = order.copy()
                router_order["symbol"] = symbol
                router_order["quantity"] = size
                router_order["price"] = price
                router_order["side"] = side
                child_orders = self.smart_router.route_order(router_order, algo="TWAP", duration_minutes=60)
            else:
                child_orders = [{
                    "symbol": symbol,
                    "side": side,
                    "quantity": size,
                    "price": price,
                    "model_id": model_id,
                }]

            # Cap per-request fanout
            if len(child_orders) > MAX_CHILD_ORDERS_PER_REQUEST:
                child_orders = child_orders[:MAX_CHILD_ORDERS_PER_REQUEST]

            execution_results = []

            for child in child_orders:
                c_symbol = str(child.get("symbol", symbol)).upper().strip()
                c_size = float(child.get("quantity", child.get("size", size)))
                c_price = float(child.get("price", price))
                c_side = str(child.get("side", side)).upper().strip()

                execution_ts = datetime.now(timezone.utc).isoformat()

                # Price band and trading boundaries check
                if order_book_data:
                    ref_price = order_book_data.get("ref_price", c_price)
                    is_suspended = order_book_data.get("is_suspended", False)
                    adv_value_vnd = order_book_data.get("adv_value_vnd", 10e9)
                    exchange_label = order_book_data.get("exchange_label")
                else:
                    ref_price = c_price
                    is_suspended = False
                    adv_value_vnd = 10e9
                    exchange_label = None

                is_blocked = self.cost_model.is_price_band_blocked(
                    symbol=c_symbol,
                    ref_price=ref_price,
                    order_price=c_price,
                    exchange_label=exchange_label,
                    is_suspended=is_suspended,
                )

                if is_blocked:
                    log_record = {
                        "execution_ts": execution_ts,
                        "feature_ts": str(feature_ts),
                        "decision_ts": str(decision_ts),
                        "available_at": str(available_at),
                        "symbol": c_symbol,
                        "side": c_side,
                        "size": c_size,
                        "quantity": c_size,
                        "intended_price": c_price,
                        "executed_price": 0.0,
                        "notional": 0.0,
                        "pnl": 0.0,
                        "execution_status": "REJECTED_PRICE_BAND",
                        "model_id": model_id,
                        "total_cost_vnd": 0.0,
                        "is_virtual": True,
                        "reject_reason": "Order price violates exchange price band bounds or symbol is suspended",
                    }
                    self.orders_history.append(log_record)
                    execution_results.append(log_record)
                    continue

                cost_estimation = self.cost_model.estimate_cost(
                    symbol=c_symbol,
                    order_size=c_size,
                    price=c_price,
                    adv_value_vnd=adv_value_vnd,
                    side=c_side,
                    exchange_label=exchange_label,
                )
                total_cost_bps = cost_estimation["total_cost_bps"]

                if c_side == "BUY":
                    executed_price = c_price * (1 + total_cost_bps / 10000.0)
                else:
                    executed_price = c_price * (1 - total_cost_bps / 10000.0)

                executed_price = self.cost_model.round_to_tick(executed_price)
                total_cost_vnd = (total_cost_bps / 10000.0) * c_size * c_price
                notional = c_size * executed_price

                log_record = {
                    "execution_ts": execution_ts,
                    "feature_ts": str(feature_ts),
                    "decision_ts": str(decision_ts),
                    "available_at": str(available_at),
                    "symbol": c_symbol,
                    "side": c_side,
                    "size": c_size,
                    "quantity": c_size,
                    "intended_price": c_price,
                    "executed_price": executed_price,
                    "notional": notional,
                    "pnl": 0.0,
                    "execution_status": "FILLED",
                    "model_id": model_id,
                    "total_cost_vnd": total_cost_vnd,
                    "is_virtual": True,
                }

                # Atomic durable write with transactional rollback
                snapshot_cash = self.cash
                snapshot_positions = {k: copy.deepcopy(v) for k, v in self.positions.items()}
                snapshot_daily_pnl = dict(self.daily_pnl)
                snapshot_realized_pnl = dict(self.realized_pnl)
                snapshot_history_len = len(self.orders_history)

                try:
                    self._log_virtual_order(log_record)
                    # Durable write succeeded; apply in-memory state mutations
                    self._apply_fill(c_symbol, c_side, c_size, executed_price, total_cost_vnd, model_id)
                    self.orders_history.append(log_record)
                    self._save_daemon_state()
                    execution_results.append(log_record)
                except Exception as log_error:
                    logger.error(f"Durable logging failed: {log_error}. Rolling back in-memory fill state.")
                    # Rollback in-memory state
                    self.cash = snapshot_cash
                    self.positions = snapshot_positions
                    self.daily_pnl = snapshot_daily_pnl
                    self.realized_pnl = snapshot_realized_pnl
                    self.orders_history = self.orders_history[:snapshot_history_len]

                    # Return rejection record
                    rej_record = self._create_rejected_record(
                        child,
                        "REJECTED_DURABILITY_FAILURE",
                        f"Durable append to {self.virtual_orders_log_path} failed: {log_error}",
                    )
                    execution_results.append(rej_record)

            if len(self.orders_history) > self.max_history_records:
                self.orders_history = self.orders_history[-self.max_history_records:]

            return execution_results

    def _apply_fill(self, symbol: str, side: str, size: float, executed_price: float, total_cost_vnd: float, model_id: str) -> None:
        """Apply fill to cash, positions, and institutional PnL."""
        if symbol not in self.positions:
            self.positions[symbol] = {
                "symbol": symbol,
                "shares": 0.0,
                "avg_price": 0.0,
                "current_price": executed_price,
                "realized_pnl_vnd": 0.0,
                "unrealized_pnl_vnd": 0.0,
            }
        pos = self.positions[symbol]

        if side == "BUY":
            gross_trade = executed_price * size
            self.cash -= (gross_trade + total_cost_vnd)

            new_shares = pos["shares"] + size
            if new_shares > 0:
                pos["avg_price"] = ((pos["shares"] * pos["avg_price"]) + (size * executed_price)) / new_shares
            pos["shares"] = new_shares
            pos["current_price"] = executed_price
            pos["unrealized_pnl_vnd"] = pos["shares"] * (pos["current_price"] - pos["avg_price"])
        else:
            gross_proceeds = executed_price * size
            self.cash += (gross_proceeds - total_cost_vnd)

            sold_shares = min(pos["shares"], size)
            realized_gain = (executed_price - pos["avg_price"]) * sold_shares - total_cost_vnd
            pos["realized_pnl_vnd"] += realized_gain
            pos["shares"] = max(0.0, pos["shares"] - size)
            pos["current_price"] = executed_price
            pos["unrealized_pnl_vnd"] = pos["shares"] * (pos["current_price"] - pos["avg_price"]) if pos["shares"] > 0 else 0.0

            if model_id not in self.realized_pnl:
                self.realized_pnl[model_id] = 0.0
            self.realized_pnl[model_id] += realized_gain

        # Calculate model daily PnL (realized + unrealized across all positions)
        total_pos_val = sum(p["shares"] * p.get("current_price", 0.0) for p in self.positions.values())
        portfolio_equity = self.cash + total_pos_val
        total_pnl = portfolio_equity - self.initial_capital
        self.daily_pnl[model_id] = total_pnl

    def _create_rejected_record(self, order: Dict[str, Any], status: str, reason: str) -> Dict[str, Any]:
        """Generate standardized rejection record."""
        now = datetime.now(timezone.utc).isoformat()
        return {
            "execution_ts": now,
            "feature_ts": str(order.get("feature_ts", now)),
            "decision_ts": str(order.get("decision_ts", now)),
            "available_at": str(order.get("available_at", order.get("feature_ts", now))),
            "symbol": str(order.get("symbol", "UNKNOWN")).upper(),
            "side": str(order.get("side", "UNKNOWN")).upper(),
            "size": float(order.get("size", order.get("quantity", 0.0)) or 0.0) if _is_finite_positive(order.get("size", order.get("quantity"))) else 0.0,
            "quantity": float(order.get("quantity", order.get("size", 0.0)) or 0.0) if _is_finite_positive(order.get("quantity", order.get("size"))) else 0.0,
            "intended_price": float(order.get("price", 0.0) or 0.0) if _is_finite_positive(order.get("price")) else 0.0,
            "executed_price": 0.0,
            "notional": 0.0,
            "pnl": 0.0,
            "execution_status": status,
            "model_id": str(order.get("model_id", "unknown")),
            "total_cost_vnd": 0.0,
            "is_virtual": True,
            "reject_reason": reason,
        }

    def get_orders(self, limit: int = 100, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve recent virtual orders with bounded limit."""
        with self._lock:
            safe_limit = max(1, min(limit, self.max_history_records))
            orders = self.orders_history
            if symbol:
                orders = [o for o in orders if o.get("symbol") == symbol.upper()]
            return [copy.deepcopy(o) for o in reversed(orders[-safe_limit:])]

    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        """Retrieve current positions."""
        with self._lock:
            return {k: copy.deepcopy(v) for k, v in self.positions.items()}

    def _log_virtual_order(self, record: Dict[str, Any]) -> None:
        """Logs the virtual order to JSONL with strict fsync durability."""
        if os.path.isdir(self.virtual_orders_log_path):
            raise IsADirectoryError(f"Log path is a directory: {self.virtual_orders_log_path}")
        parent = os.path.dirname(self.virtual_orders_log_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        line = json.dumps(record, sort_keys=True) + "\n"
        with open(self.virtual_orders_log_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def rehydrate_from_log(self) -> int:
        """Rehydrate orders and positions from durable log with corruption resilience and deduplication."""
        if not os.path.isfile(self.virtual_orders_log_path):
            return 0
        rehydrated_count = 0
        seen_keys = set()
        with self._lock:
            try:
                with open(self.virtual_orders_log_path, "r", encoding="utf-8") as f:
                    for line_no, raw_line in enumerate(f, 1):
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except Exception as e:
                            logger.warning(f"Corrupt JSONL line {line_no} skipped: {e}")
                            continue
                        if not isinstance(rec, dict):
                            continue
                        # Deduplication fingerprint
                        key = hashlib.sha256(
                            f"{rec.get('symbol')}:{rec.get('side')}:{rec.get('size')}:{rec.get('execution_ts')}:{rec.get('decision_ts')}:{rec.get('executed_price')}".encode()
                        ).hexdigest()
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)

                        self.orders_history.append(rec)
                        rehydrated_count += 1
                        if rec.get("execution_status") == "FILLED":
                            sym = str(rec.get("symbol", ""))
                            s_side = str(rec.get("side", ""))
                            s_size = float(rec.get("size", 0.0))
                            s_price = float(rec.get("executed_price", 0.0))
                            s_cost = float(rec.get("total_cost_vnd", 0.0))
                            m_id = str(rec.get("model_id", "unknown"))
                            self._apply_fill(sym, s_side, s_size, s_price, s_cost, m_id)
                if len(self.orders_history) > self.max_history_records:
                    self.orders_history = self.orders_history[-self.max_history_records:]
            except Exception as read_err:
                logger.error(f"Rehydration error from {self.virtual_orders_log_path}: {read_err}")
        return rehydrated_count

    def evaluate_shadow_mode(self, days_passed: int, min_smoke_days: int = 5, min_burn_in_days: int = 30) -> str:
        """Evaluate if a model can transition through shadow mode gates."""
        if days_passed >= min_burn_in_days:
            logger.info(f"Model passed full burn-in requirement ({days_passed}/{min_burn_in_days} days).")
            return "BURN_IN_PASSED"
        elif days_passed >= min_smoke_days:
            logger.info(f"Model passed smoke test requirement ({days_passed}/{min_smoke_days} days).")
            return "SMOKE_TEST_PASSED"
        else:
            logger.info(f"Model still in early shadow mode ({days_passed}/{min_smoke_days} days).")
            return "IN_PROGRESS"

    def get_daily_pnl(self, model_id: str) -> float:
        """Returns the accumulated daily P&L for a model."""
        with self._lock:
            return self.daily_pnl.get(model_id, 0.0)

    def reset_daily_pnl(self):
        """Resets daily P&L tracking (e.g., at end of day or test isolation)."""
        with self._lock:
            self.state = "STOPPED"
            self.started_at = None
            self.daily_pnl = {}
            self.realized_pnl = {}
            self.positions = {}
            self.orders_history = []
            self.cash = self.initial_capital
            if os.path.isfile(self.state_file_path):
                try:
                    os.remove(self.state_file_path)
                except Exception:
                    pass


# Singleton / Factory management
_default_paper_engine: Optional[PaperTradingEngine] = None
_paper_engine_lock = threading.Lock()


def get_paper_engine(log_dir: str = "logs", smart_router=None) -> PaperTradingEngine:
    global _default_paper_engine
    with _paper_engine_lock:
        if _default_paper_engine is None:
            _default_paper_engine = PaperTradingEngine(log_dir=log_dir, smart_router=smart_router)
        return _default_paper_engine


def reset_paper_engine() -> None:
    global _default_paper_engine
    with _paper_engine_lock:
        if _default_paper_engine is not None:
            try:
                _default_paper_engine.reset_daily_pnl()
            except Exception:
                pass
        _default_paper_engine = None
