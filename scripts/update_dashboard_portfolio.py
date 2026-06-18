"""
OMEGA_QUANT Dashboard Portfolio Sync
Gate: DASHBOARD_PORTFOLIO_SYNC_20260618

Reads the latest paper-trading signal output and synchronises
two dashboard artefacts under ``.ly_state/session/``:

  * risk_status.json  – positions, trades, regime, metrics
  * pnl_latest.json   – PnL snapshot for the latest signal date

Importable as a module (``sync_dashboard_portfolio``) and runnable
as a CLI script.

Author: Backend Engineer (Role 09)
Date: 2026-06-18
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Repo-relative paths
SESSION_DIR = _REPO_ROOT / ".ly_state" / "session"
SIGNAL_DIR = _REPO_ROOT / "data" / "paper_trading"
RISK_STATUS_FILE = SESSION_DIR / "risk_status.json"
PNL_LATEST_FILE = SESSION_DIR / "pnl_latest.json"
SECTOR_MAPPING_FILE = _REPO_ROOT / "data" / "sector_mapping_level2.csv"

# Metrics owned by the monitoring / circuit-breaker subsystem.
# Only these survive a merge; signal-owned metrics (num_trades, exposure,
# regime_exposure, beta) are always taken from the fresh signal payload.
MONITORING_METRICS: frozenset = frozenset({
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "total_return",
    "win_rate",
    "profit_factor",
    "avg_trade",
    "var_95",
    "var_99",
    "cvar_95",
    "cvar_99",
    "volatility",
})


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON file, returning None on failure."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.error("Failed to load %s: %s", path, exc)
        return None


def _save_json(path: Path, data: Dict[str, Any]) -> bool:
    """Atomically write JSON to *path*."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        tmp_path.replace(path)
        logger.info("Saved %s", path)
        return True
    except Exception as exc:
        logger.error("Failed to save %s: %s", path, exc)
        return False


def _find_latest_signal_file() -> Optional[Path]:
    """Return the newest signals_YYYY-MM-DD.json file, or None."""
    if not SIGNAL_DIR.exists():
        return None
    candidates = sorted(SIGNAL_DIR.glob("signals_*.json"), reverse=True)
    return candidates[0] if candidates else None


def _load_sector_mapping() -> Dict[str, str]:
    """Load ticker -> sector mapping if available."""
    if not SECTOR_MAPPING_FILE.exists():
        return {}
    try:
        import pandas as pd
        df = pd.read_csv(SECTOR_MAPPING_FILE)
        return dict(zip(df["symbol"], df["sector"]))
    except Exception as exc:
        logger.warning("Sector mapping load failed: %s", exc)
        return {}


# ------------------------------------------------------------------ #
# Transform: signal -> risk_status
# ------------------------------------------------------------------ #

def _build_portfolio_section(signal: Dict[str, Any], sector_map: Dict[str, str]) -> Dict[str, Any]:
    """Build the ``portfolio`` section expected by the dashboard Portfolio page."""
    positions: Dict[str, Any] = signal.get("positions", {})
    capital: float = signal.get("capital", 0.0)

    holdings: List[Dict[str, Any]] = []
    sectors: Dict[str, float] = {}
    total_value = 0.0

    for sym, pos in positions.items():
        value = pos.get("value_vnd", 0.0)
        total_value += value
        sector = sector_map.get(sym, "Unknown")

        holdings.append({
            "symbol": sym,
            "shares": pos.get("shares", 0),
            "avg_price": pos.get("price", 0.0),
            "current_price": pos.get("price", 0.0),
            "value": value,
            "weight": pos.get("weight", 0.0),
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "sector": sector,
        })

        sectors[sector] = sectors.get(sector, 0.0) + pos.get("weight", 0.0)

    cash = capital - total_value
    market_exposure = total_value / capital if capital > 0 else 0.0

    return {
        "total_value": capital,
        "invested_value": round(total_value, 2),
        "cash": round(cash, 2),
        "num_positions": len(positions),
        "market_exposure": round(market_exposure, 4),
        "holdings": holdings,
        "sectors": {k: round(v, 4) for k, v in sectors.items()},
    }


def _build_trades_section(signal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert positions to a trades list for the dashboard Trades page."""
    positions: Dict[str, Any] = signal.get("positions", {})
    trade_date = signal.get("date", "")
    trades: List[Dict[str, Any]] = []

    for sym, pos in positions.items():
        trades.append({
            "symbol": sym,
            "side": "BUY",
            "shares": pos.get("shares", 0),
            "price": pos.get("price", 0.0),
            "value": pos.get("value_vnd", 0.0),
            "weight": pos.get("weight", 0.0),
            "date": trade_date,
            "signal_source": "paper_trading_daily",
        })

    return trades


def _build_metrics_section(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Build dashboard-compatible risk metrics from the signal output."""
    regime = signal.get("regime", {})
    exposure = regime.get("exposure", 1.0)
    total_exposure = signal.get("total_exposure", 0.0)

    return {
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "max_drawdown": 0.0,
        "total_return": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "num_trades": signal.get("n_positions", 0),
        "avg_trade": 0.0,
        "var_95": 0.0,
        "var_99": 0.0,
        "cvar_95": 0.0,
        "cvar_99": 0.0,
        "beta": 1.0,
        "volatility": 0.0,
        "exposure": round(total_exposure, 4),
        "regime_exposure": exposure,
    }


def build_risk_status(signal: Dict[str, Any], sector_map: Dict[str, str]) -> Dict[str, Any]:
    """Assemble a complete risk_status.json payload from a signal dict."""
    regime = signal.get("regime", {})

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system_state": "RUNNING",
        "signal_date": signal.get("date", ""),
        "gate": signal.get("gate", ""),
        "regime": regime,
        "alpha_sources": signal.get("alpha_sources", {}),
        "hrp_weights": signal.get("hrp_weights", {}),
        "metrics": _build_metrics_section(signal),
        "portfolio": _build_portfolio_section(signal, sector_map),
        "trades": _build_trades_section(signal),
        "breached": False,
        "breached_reasons": [],
    }


# ------------------------------------------------------------------ #
# Transform: signal -> pnl_latest
# ------------------------------------------------------------------ #

def build_pnl_latest(signal: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble a pnl_latest.json payload from a signal dict."""
    positions: Dict[str, Any] = signal.get("positions", {})
    capital: float = signal.get("capital", 0.0)
    total_exposure = signal.get("total_exposure", 0.0)

    position_summaries = [
        {
            "symbol": sym,
            "weight": pos.get("weight", 0.0),
            "shares": pos.get("shares", 0),
            "price": pos.get("price", 0.0),
            "value_vnd": pos.get("value_vnd", 0.0),
        }
        for sym, pos in positions.items()
    ]

    return {
        "date": signal.get("date", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate": signal.get("gate", ""),
        "capital": capital,
        "total_exposure": round(total_exposure, 4),
        "invested_vnd": round(total_exposure * capital, 2),
        "cash_vnd": round((1.0 - total_exposure) * capital, 2),
        "n_positions": signal.get("n_positions", 0),
        "regime": signal.get("regime", {}),
        "positions": position_summaries,
        "daily_pnl": 0.0,
        "cumulative_pnl": 0.0,
    }


# ------------------------------------------------------------------ #
# Merge strategy
# ------------------------------------------------------------------ #

def _merge_risk_status(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Merge a new signal snapshot into the existing risk_status.json.

    Preserves only monitoring / circuit-breaker metrics (VaR, drawdown,
    performance) from the existing file.  Signal-owned metrics
    (``num_trades``, ``exposure``, ``regime_exposure``, ``beta``) are
    always taken from the new payload so that ``risk_status.json`` stays
    internally consistent with the freshly written portfolio and trades.
    """
    existing_metrics = existing.get("metrics", {})
    new_metrics = new.get("metrics", {})

    for key in MONITORING_METRICS:
        val = existing_metrics.get(key)
        if isinstance(val, (int, float)) and val != 0.0:
            new_metrics[key] = val

    new["metrics"] = new_metrics

    if existing.get("breached", False):
        new["breached"] = True
        new["breached_reasons"] = existing.get("breached_reasons", [])

    return new


# ------------------------------------------------------------------ #
# Public entry point
# ------------------------------------------------------------------ #

def sync_dashboard_portfolio(
    signal_file: Optional[str] = None,
    dry_run: bool = False,
) -> Tuple[bool, Dict[str, Any]]:
    """Synchronise dashboard artefacts from the latest signal output.

    Parameters
    ----------
    signal_file : str or None
        Explicit path to a signals JSON file.  When *None* the newest
        file in ``data/paper_trading/`` is used.
    dry_run : bool
        If True, build payloads but skip writing to disk.

    Returns
    -------
    (success, summary) : tuple[bool, dict]
    """
    # 1. Locate signal file
    if signal_file:
        sig_path = Path(signal_file)
    else:
        sig_path_opt = _find_latest_signal_file()
        if sig_path_opt is None:
            logger.error("No signal files found in %s", SIGNAL_DIR)
            return False, {"error": "no signal files found"}
        sig_path = sig_path_opt

    if not sig_path.exists():
        logger.error("Signal file not found: %s", sig_path)
        return False, {"error": f"file not found: {sig_path}"}

    logger.info("Loading signal from %s", sig_path)
    signal = _load_json(sig_path)
    if signal is None:
        return False, {"error": f"failed to load {sig_path}"}

    # 2. Load sector mapping
    sector_map = _load_sector_mapping()

    # 3. Build payloads
    risk_status = build_risk_status(signal, sector_map)
    pnl_latest = build_pnl_latest(signal)

    # 4. Merge with existing risk_status (preserve monitoring metrics)
    existing_risk = _load_json(RISK_STATUS_FILE)
    if existing_risk is not None:
        risk_status = _merge_risk_status(existing_risk, risk_status)
        logger.info("Merged with existing risk_status.json")

    summary = {
        "signal_file": str(sig_path),
        "signal_date": signal.get("date", ""),
        "n_positions": signal.get("n_positions", 0),
        "total_exposure": signal.get("total_exposure", 0.0),
        "regime": signal.get("regime", {}).get("state", "UNKNOWN"),
    }

    if dry_run:
        logger.info("DRY RUN – payloads built, not written")
        summary["dry_run"] = True
        return True, summary

    # 5. Write artefacts
    ok_risk = _save_json(RISK_STATUS_FILE, risk_status)
    ok_pnl = _save_json(PNL_LATEST_FILE, pnl_latest)

    success = ok_risk and ok_pnl
    summary["risk_status_written"] = ok_risk
    summary["pnl_latest_written"] = ok_pnl

    if success:
        logger.info(
            "Dashboard sync complete: %d positions, regime=%s, exposure=%.2f%%",
            summary["n_positions"],
            summary["regime"],
            summary["total_exposure"] * 100,
        )
    else:
        logger.error("Dashboard sync FAILED – check errors above")

    return success, summary


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync latest paper-trading signals to dashboard artefacts"
    )
    parser.add_argument(
        "--signal-file",
        type=str,
        default=None,
        help="Explicit path to a signals JSON file (default: latest in data/paper_trading/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Build payloads without writing to disk",
    )
    args = parser.parse_args()

    success, summary = sync_dashboard_portfolio(
        signal_file=args.signal_file,
        dry_run=args.dry_run,
    )

    print(json.dumps(summary, indent=2, default=str))
    sys.exit(0 if success else 1)
