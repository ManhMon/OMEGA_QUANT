"""
OMEGA_QUANT Paper Execution Pipeline
Gate: SIMULATED_TRADING_INTEGRATION_20260619

Compares current portfolio positions against target positions from
the latest signal file, generates diff orders, and routes 100% of
them through the full LiveTradingPipeline (paper mode).

Outputs:
  - Execution results JSON under .ly_state/session/
  - Updated risk_status.json and pnl_latest.json in dashboard

Author: Backend Engineer (Role 09)
Date: 2026-06-19
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

import json
import logging
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from scripts.update_market_data import _load_strict_json, verify_market_data_receipt, validate_gate_evidence

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("PaperExecutionPipeline")

# Repo-relative paths
SESSION_DIR = _REPO_ROOT / ".ly_state" / "session"
MARKET_DATA_RECEIPT_DIR = SESSION_DIR / "market_data_receipts"
SIGNAL_DIR = _REPO_ROOT / "data" / "paper_trading"
RISK_STATUS_FILE = SESSION_DIR / "risk_status.json"
PNL_LATEST_FILE = SESSION_DIR / "pnl_latest.json"
BOARD_LOT = 100
DEFAULT_CAPITAL = 2_000_000_000.0
DEFAULT_ADV_20D = 5_000_000.0
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
MAX_RECEIPT_FUTURE_SKEW = timedelta(minutes=5)


# ------------------------------------------------------------------ #
# JSON helpers
# ------------------------------------------------------------------ #

def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.error("Failed to load %s: %s", path, exc)
        return None


def _save_json(path: Path, data: Dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        tmp.replace(path)
        return True
    except Exception as exc:
        logger.error("Failed to save %s: %s", path, exc)
        return False


def _sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_receipt_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _receipt_is_future(record: Dict[str, Any], attempt_id: str, now: datetime) -> bool:
    try:
        attempt_time = datetime.strptime(attempt_id.split("_", 1)[0], "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    timestamps = [attempt_time, _parse_receipt_timestamp(record.get("started_at"))]
    if record.get("state") == "terminal":
        timestamps.append(_parse_receipt_timestamp(record.get("completed_at")))
    return any(value is None or value > now + MAX_RECEIPT_FUTURE_SKEW for value in timestamps)


def _market_data_decision(receipt_dir: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Authorize only the newest complete, signed, fresh publication attempt."""
    receipt_dir = receipt_dir or MARKET_DATA_RECEIPT_DIR
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "clock_invalid"}
    if not receipt_dir.is_dir():
        return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "ledger_missing"}
    attempts: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for path in receipt_dir.glob("*.json"):
        match = re.fullmatch(r"(\d{8}T\d{12}Z_[0-9a-f]{32})\.(in_progress|terminal)\.json", path.name)
        if not match:
            return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "ledger_filename_invalid"}
        try:
            record = _load_strict_json(path)
        except ValueError:
            return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "ledger_record_malformed"}
        attempt_id, state = match.group(1), match.group(2)
        if record.get("schema_version") != 2 or record.get("attempt_id") != attempt_id or record.get("state") != state or not verify_market_data_receipt(record):
            return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "ledger_record_invalid"}
        if _receipt_is_future(record, attempt_id, now):
            return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "ledger_timestamp_future"}
        if state in attempts.setdefault(attempt_id, {}):
            return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "ledger_ambiguous"}
        attempts.setdefault(attempt_id, {})[state] = {"path": path, "record": record}
    if not attempts:
        return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "ledger_empty"}
    try:
        attempt_id = max(attempts, key=lambda value: datetime.strptime(value.split("_", 1)[0], "%Y%m%dT%H%M%S%fZ"))
    except ValueError:
        return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "ledger_timestamp_invalid"}
    newest = attempts[attempt_id]
    if "in_progress" not in newest or "terminal" not in newest:
        return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "attempt_orphaned", "attempt_id": attempt_id}
    receipt = newest["terminal"]["record"]
    terminal_session = receipt.get("terminal_session")
    publication = receipt.get("publication")
    gate_evidence = receipt.get("gate_evidence")
    projection_path = receipt.get("projection_path")
    projection_sha256 = receipt.get("projection_sha256")
    projection_attempt_id = receipt.get("projection_attempt_id")
    projection_error = receipt.get("provenance", {}).get("projection_error") if isinstance(receipt.get("provenance"), dict) else None
    if not (
        isinstance(projection_path, str)
        and isinstance(projection_sha256, str)
        and isinstance(projection_attempt_id, str)
        and isinstance(publication, dict)
        and isinstance(publication.get("candidate_path"), str)
        and isinstance(publication.get("pointer_path"), str)
        and isinstance(publication.get("sha256"), str)
    ):
        return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "latest_attempt_ineligible", "attempt_id": attempt_id, "receipt_path": str(newest["terminal"]["path"])}
    projection = Path(projection_path)
    candidate_path = Path(publication["candidate_path"])
    pointer_path = Path(publication["pointer_path"])
    try:
        eligible = (
            receipt.get("published") is True
            and receipt.get("stale") is False
            and isinstance(terminal_session, str)
            and receipt.get("execution_allowed") is True
            and not projection_error
            and projection_attempt_id == attempt_id
            and _sha256(projection) == projection_sha256
            and _load_strict_json(projection).get("market_data_attempt_id") == attempt_id
            and _sha256(candidate_path) == publication["sha256"]
            and pointer_path.is_file()
            and _load_strict_json(pointer_path).get("sha256") == publication["sha256"]
            and validate_gate_evidence(gate_evidence, attempt_id, receipt["completed_at"])
            and gate_evidence["terminal_session"] == terminal_session
            and gate_evidence["candidate_path"] == publication["candidate_path"]
            and gate_evidence["candidate_sha256"] == publication["sha256"]
            and gate_evidence["projection_path"] == projection_path
            and gate_evidence["projection_sha256"] == projection_sha256
        )
    except (OSError, ValueError, TypeError):
        eligible = False
    if not eligible:
        return {"code": "MARKET_DATA_NOT_EXECUTABLE", "reason": "latest_attempt_ineligible", "attempt_id": attempt_id, "receipt_path": str(newest["terminal"]["path"])}
    return {"code": "MARKET_DATA_EXECUTABLE", "attempt_id": attempt_id, "receipt_path": str(newest["terminal"]["path"])}


# ------------------------------------------------------------------ #
# Signal & position loading
# ------------------------------------------------------------------ #

def load_latest_signal(signal_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load the most recent signal file by date suffix."""
    if signal_dir is None:
        signal_dir = SIGNAL_DIR
    candidates = sorted(signal_dir.glob("signals_*.json"), reverse=True)
    if not candidates:
        logger.warning("No signal files found in %s", signal_dir)
        return None
    return _load_json(candidates[0])


def load_current_positions(
    risk_status_path: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    """Extract current holdings from risk_status.json."""
    if risk_status_path is None:
        risk_status_path = RISK_STATUS_FILE
    data = _load_json(risk_status_path)
    if not data:
        return {}
    holdings = data.get("portfolio", {}).get("holdings", [])
    return {h["symbol"]: h for h in holdings}


def _build_risk_exposures(
    current_positions: Dict[str, Dict[str, Any]],
    capital: float,
) -> Dict[str, float]:
    exposures: Dict[str, float] = {}
    if capital <= 0:
        return exposures

    for symbol, position in current_positions.items():
        shares = float(position.get("shares", 0) or 0)
        current_price = float(position.get("current_price", 0) or 0)
        avg_price = float(position.get("avg_price", 0) or 0)

        if shares > 0:
            if current_price > 0:
                exposures[symbol] = shares * current_price
                continue
            if avg_price > 0:
                exposures[symbol] = shares * avg_price
                continue

        if "weight" in position and position["weight"] is not None:
            exposures[symbol] = float(position["weight"]) * capital
            continue

        value = position.get("value", position.get("value_vnd", 0.0))
        exposures[symbol] = float(value or 0.0)

    return exposures


# ------------------------------------------------------------------ #
# Diff computation
# ------------------------------------------------------------------ #

@dataclass
class OrderDiff:
    """Represents a single order to reconcile current -> target."""
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: int
    price: float
    target_weight: float
    current_weight: float


def compute_order_diffs(
    signal: Dict[str, Any],
    current_positions: Dict[str, Dict[str, Any]],
    capital: float = DEFAULT_CAPITAL,
) -> List[OrderDiff]:
    """
    Compare target positions from signal against current portfolio.

    Returns list of OrderDiff with board-lot-rounded quantities.
    """
    target_positions = signal.get("positions", {})
    diffs: List[OrderDiff] = []

    all_symbols = set(target_positions) | set(current_positions)

    for symbol in sorted(all_symbols):
        target = target_positions.get(symbol, {})
        current = current_positions.get(symbol, {})

        target_shares = target.get("shares", 0)
        current_shares = current.get("shares", 0)
        price = target.get("price", current.get("current_price", 0.0))

        if price <= 0:
            logger.warning("Skipping %s: no valid price", symbol)
            continue

        delta = target_shares - current_shares
        if delta == 0:
            continue

        # Round to board lot
        rounded_qty = (abs(delta) // BOARD_LOT) * BOARD_LOT
        if rounded_qty <= 0:
            continue

        side = "BUY" if delta > 0 else "SELL"
        target_weight = target.get("weight", 0.0)
        current_weight = current.get("weight", 0.0)

        diffs.append(OrderDiff(
            symbol=symbol,
            side=side,
            quantity=rounded_qty,
            price=price,
            target_weight=target_weight,
            current_weight=current_weight,
        ))

    return diffs


# ------------------------------------------------------------------ #
# Pipeline execution
# ------------------------------------------------------------------ #

def build_pipeline(
    current_positions: Optional[Dict[str, Dict[str, Any]]] = None,
    capital: float = DEFAULT_CAPITAL,
):
    """
    Construct a LiveTradingPipeline wired for paper execution.

    Returns the pipeline instance.
    """
    from omega.quant.execution.multi_symbol_router import MultiSymbolRouter
    from omega.quant.risk.realtime_risk import RealtimeRiskGuard
    from omega.quant.execution.live_bridge import (
        LiveExecutionBridge,
        BrokerConfig,
    )
    from omega.execution.live_trading_pipeline import LiveTradingPipeline
    from omega.execution.pre_trade_controls import PreTradeGate

    router = MultiSymbolRouter()
    risk_guard = RealtimeRiskGuard()
    risk_guard.set_portfolio_state(
        capital,
        _build_risk_exposures(current_positions or {}, capital),
    )

    broker_config = BrokerConfig(
        broker_name="SSI",
        api_key="PAPER_KEY",
        api_secret="PAPER_SECRET",
        account_id="PAPER_ACCT",
        base_url="paper://localhost",
        paper_trading=True,
    )
    bridge = LiveExecutionBridge(broker_config)

    pre_trade_gate = PreTradeGate()
    pre_trade_gate.update_margin("PAPER_ACCT", capital)

    pipeline = LiveTradingPipeline(
        router=router,
        risk_guard=risk_guard,
        execution=bridge,
        pre_trade_gate=pre_trade_gate,
        account_id="PAPER_ACCT",
    )
    return pipeline


def execute_diffs(
    pipeline,
    diffs: List[OrderDiff],
    adv_20d: float = DEFAULT_ADV_20D,
) -> List[Dict[str, Any]]:
    """
    Submit every diff through LiveTradingPipeline.

    Returns a list of result dicts (one per diff).
    """
    from omega.execution.broker_gateway import OrderSide, OrderType
    from omega.execution.live_trading_pipeline import PipelineState

    results = []
    for diff in diffs:
        side = OrderSide.BUY if diff.side == "BUY" else OrderSide.SELL

        result = pipeline.submit_order(
            symbol=diff.symbol,
            side=side,
            quantity=diff.quantity,
            price=diff.price,
            adv_20d=adv_20d,
            order_type=OrderType.MARKET,
        )

        record = {
            "symbol": diff.symbol,
            "side": diff.side,
            "quantity": diff.quantity,
            "price": diff.price,
            "pipeline_state": result.state.value,
            "order_id": result.order_id,
            "error": result.error,
            "target_weight": diff.target_weight,
            "current_weight": diff.current_weight,
        }
        results.append(record)

        status = "OK" if result.state == PipelineState.COMPLETED else "FAIL"
        logger.info(
            "[%s] %s %s %d @ %.0f => %s (order=%s)",
            status, diff.side, diff.symbol, diff.quantity,
            diff.price, result.state.value, result.order_id,
        )

    return results


# ------------------------------------------------------------------ #
# Dashboard update
# ------------------------------------------------------------------ #

def update_dashboard(
    signal: Dict[str, Any],
    execution_results: List[Dict[str, Any]],
    session_dir: Optional[Path] = None,
    market_data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Update risk_status.json and pnl_latest.json with execution results.
    """
    if session_dir is None:
        session_dir = SESSION_DIR
    now = datetime.now(timezone.utc).isoformat()
    signal_date = signal.get("date", datetime.now().strftime("%Y-%m-%d"))

    # Build trades from execution results
    trades = []
    for r in execution_results:
        if r["pipeline_state"] == "COMPLETED":
            trades.append({
                "symbol": r["symbol"],
                "side": r["side"],
                "shares": r["quantity"],
                "price": r["price"],
                "value": r["quantity"] * r["price"],
                "weight": r["target_weight"],
                "date": signal_date,
                "signal_source": "paper_execution_pipeline",
                "order_id": r["order_id"],
            })

    # Update risk_status.json
    existing = _load_json(session_dir / "risk_status.json") or {}
    positions = signal.get("positions", {})
    total_value = signal.get("capital", DEFAULT_CAPITAL)
    invested = sum(p.get("value_vnd", 0.0) for p in positions.values())

    holdings = []
    for sym, pos in positions.items():
        holdings.append({
            "symbol": sym,
            "shares": pos.get("shares", 0),
            "avg_price": pos.get("price", 0.0),
            "current_price": pos.get("price", 0.0),
            "value": pos.get("value_vnd", 0.0),
            "weight": pos.get("weight", 0.0),
            "pnl": 0.0,
            "pnl_pct": 0.0,
        })

    risk_status = {
        "timestamp": now,
        "system_state": "RUNNING",
        "signal_date": signal_date,
        "gate": "SIMULATED_TRADING_INTEGRATION_20260619",
        "regime": signal.get("regime", {}),
        "alpha_sources": signal.get("alpha_sources", {}),
        "hrp_weights": signal.get("hrp_weights", {}),
        "metrics": existing.get("metrics", {
            "num_trades": len(trades),
            "exposure": signal.get("total_exposure", 0.0),
        }),
        "portfolio": {
            "total_value": total_value,
            "invested_value": invested,
            "cash": total_value - invested,
            "num_positions": len(positions),
            "market_exposure": signal.get("total_exposure", 0.0),
            "holdings": holdings,
        },
        "trades": trades,
        "execution_summary": {
            "total_orders": len(execution_results),
            "completed": sum(1 for r in execution_results if r["pipeline_state"] == "COMPLETED"),
            "failed": sum(1 for r in execution_results if r["pipeline_state"] != "COMPLETED"),
            "timestamp": now,
        },
        "market_data_provenance": market_data or {},
        "breached": existing.get("breached", False),
        "breached_reasons": existing.get("breached_reasons", []),
    }
    _save_json(session_dir / "risk_status.json", risk_status)

    # Update pnl_latest.json
    pnl_latest = {
        "signal_date": signal_date,
        "timestamp": now,
        "gate": "SIMULATED_TRADING_INTEGRATION_20260619",
        "total_value": total_value,
        "invested_value": invested,
        "cash": total_value - invested,
        "num_positions": len(positions),
        "num_trades_executed": len(trades),
        "total_orders_submitted": len(execution_results),
    }
    _save_json(session_dir / "pnl_latest.json", pnl_latest)

    logger.info(
        "Dashboard updated: %d trades, %d/%d orders completed",
        len(trades),
        risk_status["execution_summary"]["completed"],
        risk_status["execution_summary"]["total_orders"],
    )


# ------------------------------------------------------------------ #
# Result persistence
# ------------------------------------------------------------------ #

def save_execution_results(
    results: List[Dict[str, Any]],
    signal: Dict[str, Any],
    diffs: List[OrderDiff],
    session_dir: Optional[Path] = None,
    market_data: Optional[Dict[str, Any]] = None,
) -> Path:
    """Persist execution results to session directory."""
    if session_dir is None:
        session_dir = SESSION_DIR
    now = datetime.now(timezone.utc).isoformat()
    output = {
        "gate": "SIMULATED_TRADING_INTEGRATION_20260619",
        "timestamp": now,
        "signal_date": signal.get("date", ""),
        "signal_source": signal.get("gate", ""),
        "total_diffs": len(diffs),
        "total_executed": len(results),
        "completed": sum(1 for r in results if r["pipeline_state"] == "COMPLETED"),
        "failed": sum(1 for r in results if r["pipeline_state"] != "COMPLETED"),
        "results": results,
        "market_data_provenance": market_data or {},
    }
    out_path = session_dir / f"paper_exec_{signal.get('date', 'unknown')}.json"
    _save_json(out_path, output)
    logger.info("Execution results saved to %s", out_path)
    return out_path


# ------------------------------------------------------------------ #
# Main orchestrator
# ------------------------------------------------------------------ #

def run_paper_execution_pipeline(
    signal: Optional[Dict[str, Any]] = None,
    current_positions: Optional[Dict[str, Dict[str, Any]]] = None,
    dry_run: bool = False,
    market_data_receipt_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Full paper execution pipeline:

    1. Load signal and current positions
    2. Compute order diffs (current vs target)
    3. Submit 100% of diffs through LiveTradingPipeline
    4. Update dashboard (risk_status, pnl_latest)
    5. Save execution results

    Args:
        signal: Optional pre-loaded signal dict. If None, loads from disk.
        current_positions: Optional pre-loaded positions. If None, loads from disk.
        dry_run: If True, compute diffs but skip pipeline execution.

    Returns:
        Summary dict with counts and result path.
    """
    # Step 1: Load signal
    if signal is None:
        signal = load_latest_signal()
    if signal is None:
        logger.error("No signal available — aborting pipeline")
        return {"error": "No signal available", "total_diffs": 0}

    market_data = _market_data_decision(market_data_receipt_dir)
    if market_data["code"] != "MARKET_DATA_EXECUTABLE":
        return {"error": "MARKET_DATA_NOT_EXECUTABLE", "total_diffs": 0, "dry_run": dry_run, "market_data_provenance": market_data}

    # Step 2: Load current positions
    if current_positions is None:
        current_positions = load_current_positions()

    # Step 3: Compute diffs
    capital = signal.get("capital", DEFAULT_CAPITAL)
    diffs = compute_order_diffs(signal, current_positions, capital)
    logger.info("Computed %d order diffs from signal dated %s", len(diffs), signal.get("date"))

    if not diffs:
        logger.info("No orders to execute — portfolio is aligned with target")
        return {
            "signal_date": signal.get("date"),
            "total_diffs": 0,
            "total_executed": 0,
            "completed": 0,
            "failed": 0,
            "market_data_provenance": market_data,
        }

    if dry_run:
        logger.info("DRY RUN — skipping pipeline execution")
        return {
            "signal_date": signal.get("date"),
            "total_diffs": len(diffs),
            "dry_run": True,
            "diffs": [
                {"symbol": d.symbol, "side": d.side, "quantity": d.quantity, "price": d.price}
                for d in diffs
            ],
            "market_data_provenance": market_data,
        }

    # Step 4: Build pipeline and execute
    pipeline = build_pipeline(current_positions=current_positions, capital=capital)
    results = execute_diffs(pipeline, diffs)

    # Step 5: Update dashboard
    update_dashboard(signal, results, market_data=market_data)

    # Step 6: Save results
    result_path = save_execution_results(results, signal, diffs, market_data=market_data)

    completed = sum(1 for r in results if r["pipeline_state"] == "COMPLETED")
    failed = len(results) - completed

    return {
        "signal_date": signal.get("date"),
        "total_diffs": len(diffs),
        "total_executed": len(results),
        "completed": completed,
        "failed": failed,
        "result_path": str(result_path),
        "market_data_provenance": market_data,
    }


# ------------------------------------------------------------------ #
# CLI entry point
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Paper Execution Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Compute diffs without executing")
    parser.add_argument("--signal-file", type=str, help="Path to signal JSON file")
    args = parser.parse_args()

    signal = None
    if args.signal_file:
        signal = _load_json(Path(args.signal_file))
        if signal is None:
            logger.error("Failed to load signal file: %s", args.signal_file)
            sys.exit(1)

    summary = run_paper_execution_pipeline(signal=signal, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, default=str))
