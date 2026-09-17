import logging
import os
import json
import urllib.request
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, UTC, timezone
from dataclasses import dataclass, field
from enum import Enum

from omega.quant.execution.live_bridge import ExecutionOrder, ExecutionState

logger = logging.getLogger(__name__)

class SystemState(Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    EMERGENCY_STOP = "EMERGENCY_STOP"

@dataclass
class PerformanceMetrics:
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    turnover: float = 0.0
    win_rate: float = 0.0

class DashboardManager:
    """
    Institutional Dashboard & Monitoring Manager (Phase 17).
    Tracks real-time execution, risk, and performance metrics.
    """
    def __init__(self):
        self._execution_history: List[ExecutionOrder] = []
        self._daily_returns: List[float] = []
        self._risk_alerts: List[Dict] = []
        self._start_time = datetime.now(UTC)
        self._timestamped_returns: List[Dict[str, Any]] = []
        self._timestamped_benchmark_returns: List[Dict[str, Any]] = []

    def update_execution(self, order: ExecutionOrder):
        """Update tracker with new order state."""
        self._execution_history.append(order)
        logger.info(f"Dashboard updated for order {order.order_id}")

    def add_risk_alert(self, symbol: str, reason: str, details: Dict):
        """Log a risk violation alert."""
        alert = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "reason": reason,
            "details": details
        }
        self._risk_alerts.append(alert)
        logger.warning(f"RISK ALERT: {symbol} - {reason}")

    def add_daily_return(self, timestamp: datetime, ret: float):
        """Add daily return with timestamp for chronological/PIT checks."""
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        self._timestamped_returns.append({"timestamp": timestamp, "return": ret})
        self._daily_returns.append(ret)

    def add_benchmark_return(self, timestamp: datetime, ret: float):
        """Add benchmark daily return with timestamp."""
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        self._timestamped_benchmark_returns.append({"timestamp": timestamp, "return": ret})

    def _get_returns_up_to(self, current_time: datetime) -> pd.DataFrame:
        """Filter daily returns chronologically up to current_time to ensure PIT safety."""
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        
        records = []
        for r in self._timestamped_returns:
            ts = r["timestamp"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts <= current_time:
                records.append({"timestamp": ts, "return": r["return"]})
                
        if not records:
            return pd.DataFrame(columns=["timestamp", "return"])
            
        df = pd.DataFrame(records)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def _get_aligned_returns_up_to(self, current_time: datetime) -> pd.DataFrame:
        """Filter and align portfolio and benchmark returns up to current_time to ensure PIT safety."""
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
            
        p_records = []
        for r in self._timestamped_returns:
            ts = r["timestamp"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts <= current_time:
                p_records.append({"timestamp": ts, "portfolio_return": r["return"]})
                
        b_records = []
        for r in self._timestamped_benchmark_returns:
            ts = r["timestamp"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts <= current_time:
                b_records.append({"timestamp": ts, "benchmark_return": r["return"]})
                
        if not p_records or not b_records:
            return pd.DataFrame(columns=["timestamp", "portfolio_return", "benchmark_return"])
            
        df_p = pd.DataFrame(p_records)
        df_b = pd.DataFrame(b_records)
        
        df = pd.merge(df_p, df_b, on="timestamp", how="inner")
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def calculate_var_cvar(self, confidence: float, current_time: datetime) -> tuple[float, float]:
        """
        Compute Historical Simulation VaR & CVaR (vectorized).
        VaR is the negative of the (1 - confidence) percentile of returns.
        CVaR is the negative average of returns that are <= -VaR.
        """
        if confidence > 1.0:
            confidence = confidence / 100.0
            
        df = self._get_returns_up_to(current_time)
        if df.empty or len(df) < 2:
            return 0.0, 0.0
            
        returns = df["return"].values
        percentile = (1.0 - confidence) * 100
        var_val = -np.percentile(returns, percentile)
        
        tail_returns = returns[returns <= -var_val]
        if len(tail_returns) > 0:
            cvar_val = -np.mean(tail_returns)
        else:
            cvar_val = var_val
            
        return float(var_val), float(cvar_val)

    def calculate_portfolio_beta(self, current_time: datetime) -> float:
        """
        Compute Portfolio Beta against benchmark up to current_time.
        Cov(Rp, Rm) / Var(Rm)
        """
        df = self._get_aligned_returns_up_to(current_time)
        if df.empty or len(df) < 2:
            return 0.0
            
        p_ret = df["portfolio_return"].values
        b_ret = df["benchmark_return"].values
        
        cov_matrix = np.cov(p_ret, b_ret)
        cov_p_m = cov_matrix[0, 1]
        var_m = cov_matrix[1, 1]
        
        if var_m > 0:
            return float(cov_p_m / var_m)
        return 0.0

    def calculate_drawdowns(self, current_time: datetime) -> tuple[float, float]:
        """
        Compute max drawdown and current drawdown up to current_time.
        Returns: (max_drawdown, current_drawdown)
        """
        df = self._get_returns_up_to(current_time)
        if df.empty:
            return 0.0, 0.0
            
        returns = np.array([0.0] + list(df["return"].values))
        cum_returns = np.cumsum(returns)
        peaks = np.maximum.accumulate(cum_returns)
        drawdowns = peaks - cum_returns
        
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
        current_dd = float(drawdowns[-1]) if len(drawdowns) > 0 else 0.0
        
        return max_dd, current_dd

    def calculate_sharpe_ratio(self, current_time: datetime) -> float:
        """
        Compute annualized Sharpe ratio up to current_time.
        """
        df = self._get_returns_up_to(current_time)
        if df.empty or len(df) < 2:
            return 0.0
            
        returns = df["return"].values
        mean_ret = np.mean(returns)
        std_ret = np.std(returns, ddof=1)
        
        if std_ret > 0:
            return float((mean_ret / std_ret) * np.sqrt(252))
        return 0.0

    def get_live_metrics(self) -> Dict[str, Any]:
        """Compute live dashboard metrics."""
        metrics = {
            "total_orders": 0,
            "filled_orders": 0,
            "fill_rate": 0.0,
            "total_notional": 0.0,
            "active_alerts": len(self._risk_alerts),
            "uptime_seconds": (datetime.now(UTC) - self._start_time).total_seconds()
        }

        if not self._execution_history:
            metrics["status"] = "NO_DATA_BUT_MONITORING_ACTIVE"
            return metrics

        df = pd.DataFrame([vars(o) for o in self._execution_history])
        filled = df[df['state'] == ExecutionState.FILLED]
        
        metrics.update({
            "total_orders": len(df),
            "filled_orders": len(filled),
            "fill_rate": len(filled) / len(df) if len(df) > 0 else 0,
            "total_notional": (filled['filled_quantity'] * filled['average_fill_price']).sum(),
            "status": "ACTIVE"
        })
        
        return metrics

    def compute_performance(self) -> PerformanceMetrics:
        """Compute advanced portfolio performance metrics."""
        if not self._daily_returns:
            return PerformanceMetrics()
            
        returns = np.array([0.0] + list(self._daily_returns))
        vol = np.std(returns[1:]) * np.sqrt(252)
        sharpe = (np.mean(returns[1:]) * 252) / vol if vol > 0 else 0.0
        
        cum_returns = np.cumsum(returns)
        peak = np.maximum.accumulate(cum_returns)
        drawdown = peak - cum_returns
        max_dd = np.max(drawdown) if len(drawdown) > 0 else 0.0
        
        return PerformanceMetrics(
            total_return=float(np.sum(returns)),
            sharpe_ratio=float(sharpe),
            max_drawdown=float(max_dd)
        )


class ProductionMonitor:
    """
    Production Risk Monitor (Phase 17).
    Tracks real-time metrics and enforces circuit breakers.
    """
    def __init__(
        self,
        dashboard_manager: DashboardManager,
        var_breach_threshold: float,
        max_drawdown_threshold: float,
        max_consecutive_losses: int,
        slack_webhook_url: Optional[str] = None,
        alert_cooldown_seconds: float = 60.0,
        export_path: Optional[str] = None,
    ):
        self.dashboard_manager = dashboard_manager
        self.var_breach_threshold = var_breach_threshold
        self.max_drawdown_threshold = max_drawdown_threshold
        self.max_consecutive_losses = max_consecutive_losses
        self.slack_webhook_url = slack_webhook_url
        self.alert_cooldown_seconds = alert_cooldown_seconds

        self.state = SystemState.RUNNING
        self.last_alert_time: Optional[datetime] = None
        self.alert_history: List[Dict[str, Any]] = []

        # Derive repo-relative path at runtime; accept override via constructor (audit P2-D fix).
        if export_path is not None:
            self.export_path = export_path
        else:
            _repo_root = os.path.dirname(
                os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.dirname(os.path.abspath(__file__))
                        )
                    )
                )
            )
            self.export_path = os.path.join(
                _repo_root, ".ly_state", "session", "risk_status.json"
            )

    def evaluate_circuit_breakers(self, current_time: datetime) -> SystemState:
        """
        Evaluate circuit breakers based on metrics up to current_time.
        Updates state to EMERGENCY_STOP if any threshold is breached.
        """
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        # 1. Compute all metrics
        var_95, cvar_95 = self.dashboard_manager.calculate_var_cvar(0.95, current_time)
        var_99, cvar_99 = self.dashboard_manager.calculate_var_cvar(0.99, current_time)
        portfolio_beta = self.dashboard_manager.calculate_portfolio_beta(current_time)
        max_dd, current_dd = self.dashboard_manager.calculate_drawdowns(current_time)
        sharpe = self.dashboard_manager.calculate_sharpe_ratio(current_time)
        
        # Calculate consecutive losses
        returns_df = self.dashboard_manager._get_returns_up_to(current_time)
        consecutive_losses = 0
        max_consecutive_losses_val = 0
        if not returns_df.empty:
            returns = returns_df["return"].values
            current_consec = 0
            for r in returns:
                if r < 0:
                    current_consec += 1
                    if current_consec > max_consecutive_losses_val:
                        max_consecutive_losses_val = current_consec
                else:
                    current_consec = 0
            
            # Also get currently running consecutive losses at the tail of returns
            current_consec_tail = 0
            for r in reversed(returns):
                if r < 0:
                    current_consec_tail += 1
                else:
                    break
            consecutive_losses = current_consec_tail
            
        # Check breaches
        breached_reasons = []
        
        if var_95 > self.var_breach_threshold:
            breached_reasons.append(f"VaR 95% ({var_95:.4f}) exceeded threshold ({self.var_breach_threshold:.4f})")
        if var_99 > self.var_breach_threshold:
            breached_reasons.append(f"VaR 99% ({var_99:.4f}) exceeded threshold ({self.var_breach_threshold:.4f})")
            
        if max_dd > self.max_drawdown_threshold:
            breached_reasons.append(f"Max Drawdown ({max_dd:.4f}) exceeded threshold ({self.max_drawdown_threshold:.4f})")
            
        if max_consecutive_losses_val > self.max_consecutive_losses:
            breached_reasons.append(f"Max consecutive losses ({max_consecutive_losses_val}) exceeded threshold ({self.max_consecutive_losses})")

        if breached_reasons:
            self.state = SystemState.EMERGENCY_STOP
            alert_msg = f"EMERGENCY CIRCUIT BREAKER TRIGGERED at {current_time.isoformat()}: " + " | ".join(breached_reasons)
            self.send_slack_alert(alert_msg, current_time)
            
        # Auto-export snapshot
        metrics = {
            "var_95": var_95,
            "var_99": var_99,
            "cvar_95": cvar_95,
            "cvar_99": cvar_99,
            "portfolio_beta": portfolio_beta,
            "max_drawdown": max_dd,
            "current_drawdown": current_dd,
            "sharpe_ratio": sharpe,
            "consecutive_losses": consecutive_losses,
            "max_consecutive_losses": max_consecutive_losses_val
        }
        self.export_snapshot(current_time, metrics, breached_reasons)
        
        return self.state

    def send_slack_alert(self, message: str, current_time: datetime):
        if self.last_alert_time is not None:
            elapsed = (current_time - self.last_alert_time).total_seconds()
            if elapsed < self.alert_cooldown_seconds:
                logger.warning(f"Slack alert throttled: {message}")
                return
        
        self.last_alert_time = current_time
        self.alert_history.append({"timestamp": current_time.isoformat(), "message": message})
        
        success = False
        if self.slack_webhook_url:
            try:
                data = json.dumps({"text": message}).encode("utf-8")
                req = urllib.request.Request(
                    self.slack_webhook_url,
                    data=data,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status in (200, 204):
                        success = True
                        logger.info(f"Slack alert sent successfully: {message}")
            except Exception as e:
                logger.error(f"Failed to send Slack alert via webhook: {e}")
        
        if not success:
            logger.error(f"[SLACK ALERT FALLBACK] {message}")

    def export_snapshot(self, current_time: datetime, metrics: Dict[str, Any], breached_reasons: List[str]):
        """Export snapshot data to risk_status.json."""
        os.makedirs(os.path.dirname(self.export_path), exist_ok=True)
        snapshot = {
            "timestamp": current_time.isoformat(),
            "system_state": self.state.value,
            "metrics": metrics,
            "breached": len(breached_reasons) > 0,
            "breached_reasons": breached_reasons
        }
        try:
            with open(self.export_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=4)
            logger.info(f"Risk snapshot exported to {self.export_path}")
        except Exception as e:
            logger.error(f"Failed to export risk snapshot: {e}")
