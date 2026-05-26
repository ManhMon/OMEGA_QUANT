"""Post-trade controls and fill quality analysis.

Implements post-trade checks after order execution:
- Fill quality vs VWAP
- Slippage detection and alerting
- P&L attribution
- Reconciliation triggers
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import logging
from datetime import datetime
import threading


logger = logging.getLogger(__name__)


class FillQuality(Enum):
    """Fill quality assessment."""
    EXCELLENT = "excellent"  # Better than VWAP
    GOOD = "good"  # Within 5 bps of VWAP
    ACCEPTABLE = "acceptable"  # Within 10 bps of VWAP
    POOR = "poor"  # Within 20 bps of VWAP
    UNACCEPTABLE = "unacceptable"  # Worse than 20 bps


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Fill:
    """Trade fill representation."""
    fill_id: str
    order_id: str
    symbol: str
    side: str  # BUY or SELL
    quantity: float
    price: float
    timestamp: datetime
    account_id: str
    venue: str = "unknown"
    commission: float = 0.0


@dataclass
class PostTradeReport:
    """Post-trade analysis report."""
    fill_id: str
    fill_quality: FillQuality
    vwap: Optional[float]
    slippage_bps: float
    slippage_amount: float
    pnl_impact: float
    alerts: List[Dict] = field(default_factory=list)
    reconciliation_required: bool = False
    details: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class VWAPData:
    """VWAP data for a symbol."""
    symbol: str
    vwap: float
    volume: float
    timestamp: datetime


class PostTradeGate:
    """Post-trade control gate with fill quality analysis."""
    
    def __init__(
        self,
        slippage_warning_bps: float = 10.0,
        slippage_critical_bps: float = 20.0,
        reconciliation_threshold: float = 1000.0
    ):
        """Initialize post-trade gate.
        
        Args:
            slippage_warning_bps: Slippage threshold for warnings (basis points)
            slippage_critical_bps: Slippage threshold for critical alerts (basis points)
            reconciliation_threshold: Dollar threshold for reconciliation trigger
        """
        self.slippage_warning_bps = slippage_warning_bps
        self.slippage_critical_bps = slippage_critical_bps
        self.reconciliation_threshold = reconciliation_threshold
        
        # VWAP cache
        self._vwap_cache: Dict[str, VWAPData] = {}
        self._vwap_lock = threading.Lock()
        
        # Fill history for P&L attribution
        self._fill_history: List[Fill] = []
        self._history_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            "total_fills": 0,
            "excellent_fills": 0,
            "good_fills": 0,
            "acceptable_fills": 0,
            "poor_fills": 0,
            "unacceptable_fills": 0,
            "total_slippage": 0.0,
            "reconciliations_triggered": 0
        }
        self._stats_lock = threading.Lock()
        
        logger.info("PostTradeGate initialized")
    
    def check(self, fill: Fill) -> PostTradeReport:
        """Run post-trade checks on a fill.
        
        Args:
            fill: Fill to analyze
            
        Returns:
            PostTradeReport with analysis results
        """
        report = self._analyze_fill(fill)
        
        # Record fill
        self._record_fill(fill)
        
        # Update statistics
        self._update_statistics(report)
        
        # Log results
        self._log_report(fill, report)
        
        return report
    
    def _analyze_fill(self, fill: Fill) -> PostTradeReport:
        """Analyze fill quality and generate report."""
        # Get VWAP for comparison
        vwap_data = self._get_vwap(fill.symbol)
        vwap = vwap_data.vwap if vwap_data else None
        
        # Calculate slippage
        slippage_bps, slippage_amount = self._calculate_slippage(fill, vwap)
        
        # Assess fill quality
        fill_quality = self._assess_fill_quality(slippage_bps)
        
        # Calculate P&L impact
        pnl_impact = self._calculate_pnl_impact(fill, slippage_amount)
        
        # Generate alerts
        alerts = self._generate_alerts(fill, slippage_bps, slippage_amount)
        
        # Check if reconciliation needed
        reconciliation_required = abs(slippage_amount) > self.reconciliation_threshold
        
        report = PostTradeReport(
            fill_id=fill.fill_id,
            fill_quality=fill_quality,
            vwap=vwap,
            slippage_bps=slippage_bps,
            slippage_amount=slippage_amount,
            pnl_impact=pnl_impact,
            alerts=alerts,
            reconciliation_required=reconciliation_required,
            details={
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "side": fill.side,
                "quantity": fill.quantity,
                "price": fill.price,
                "venue": fill.venue,
                "commission": fill.commission
            }
        )
        
        return report
    
    def _calculate_slippage(self, fill: Fill, vwap: Optional[float]) -> tuple[float, float]:
        """Calculate slippage in basis points and dollar amount.
        
        Returns:
            Tuple of (slippage_bps, slippage_amount)
        """
        if vwap is None or vwap == 0:
            logger.warning("No VWAP data for %s, cannot calculate slippage", fill.symbol)
            return 0.0, 0.0
        
        # Calculate price difference
        price_diff = fill.price - vwap
        
        # Adjust sign based on side (negative slippage is bad for buys, positive for sells)
        if fill.side == "BUY":
            slippage_bps = (price_diff / vwap) * 10000
        else:  # SELL
            slippage_bps = (-price_diff / vwap) * 10000
        
        # Calculate dollar amount
        slippage_amount = price_diff * fill.quantity
        if fill.side == "SELL":
            slippage_amount = -slippage_amount
        
        return slippage_bps, slippage_amount
    
    def _assess_fill_quality(self, slippage_bps: float) -> FillQuality:
        """Assess fill quality based on slippage."""
        abs_slippage = abs(slippage_bps)
        
        if slippage_bps < 0:  # Better than VWAP
            return FillQuality.EXCELLENT
        elif abs_slippage <= 5.0:
            return FillQuality.GOOD
        elif abs_slippage <= 10.0:
            return FillQuality.ACCEPTABLE
        elif abs_slippage <= 20.0:
            return FillQuality.POOR
        else:
            return FillQuality.UNACCEPTABLE
    
    def _calculate_pnl_impact(self, fill: Fill, slippage_amount: float) -> float:
        """Calculate P&L impact of slippage."""
        # P&L impact is negative slippage amount minus commission
        pnl_impact = -slippage_amount - fill.commission
        return pnl_impact
    
    def _generate_alerts(self, fill: Fill, slippage_bps: float, slippage_amount: float) -> List[Dict]:
        """Generate alerts based on fill analysis."""
        alerts = []
        
        abs_slippage_bps = abs(slippage_bps)
        
        # Slippage alerts
        if abs_slippage_bps > self.slippage_critical_bps:
            alerts.append({
                "level": AlertLevel.CRITICAL.value,
                "type": "excessive_slippage",
                "message": f"Critical slippage: {slippage_bps:.2f} bps (${slippage_amount:.2f})",
                "timestamp": datetime.utcnow().isoformat()
            })
        elif abs_slippage_bps > self.slippage_warning_bps:
            alerts.append({
                "level": AlertLevel.WARNING.value,
                "type": "high_slippage",
                "message": f"High slippage: {slippage_bps:.2f} bps (${slippage_amount:.2f})",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Large fill alert
        fill_value = fill.quantity * fill.price
        if fill_value > 100000:  # $100k threshold
            alerts.append({
                "level": AlertLevel.INFO.value,
                "type": "large_fill",
                "message": f"Large fill: ${fill_value:,.2f}",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        return alerts
    
    def _get_vwap(self, symbol: str) -> Optional[VWAPData]:
        """Get VWAP data for symbol."""
        with self._vwap_lock:
            return self._vwap_cache.get(symbol)
    
    def _record_fill(self, fill: Fill):
        """Record fill in history."""
        with self._history_lock:
            self._fill_history.append(fill)
            # Keep last 10000 fills
            if len(self._fill_history) > 10000:
                self._fill_history = self._fill_history[-10000:]
    
    def _update_statistics(self, report: PostTradeReport):
        """Update gate statistics."""
        with self._stats_lock:
            self._stats["total_fills"] += 1
            
            # Update quality counts
            quality_key = f"{report.fill_quality.value}_fills"
            self._stats[quality_key] = self._stats.get(quality_key, 0) + 1
            
            # Update slippage
            self._stats["total_slippage"] += report.slippage_amount
            
            # Update reconciliation count
            if report.reconciliation_required:
                self._stats["reconciliations_triggered"] += 1
    
    def _log_report(self, fill: Fill, report: PostTradeReport):
        """Log post-trade report."""
        log_level = logging.INFO
        
        # Escalate log level for poor fills
        if report.fill_quality in [FillQuality.POOR, FillQuality.UNACCEPTABLE]:
            log_level = logging.WARNING
        
        logger.log(
            log_level,
            "Fill %s: %s quality, slippage %.2f bps ($%.2f), P&L impact $%.2f",
            fill.fill_id,
            report.fill_quality.value,
            report.slippage_bps,
            report.slippage_amount,
            report.pnl_impact
        )
        
        # Log alerts
        for alert in report.alerts:
            alert_level = getattr(logging, alert["level"].upper(), logging.INFO)
            logger.log(alert_level, "Alert: %s", alert["message"])
    
    # Configuration and data management methods
    
    def update_vwap(self, symbol: str, vwap: float, volume: float):
        """Update VWAP data for a symbol."""
        with self._vwap_lock:
            self._vwap_cache[symbol] = VWAPData(
                symbol=symbol,
                vwap=vwap,
                volume=volume,
                timestamp=datetime.utcnow()
            )
        logger.debug("Updated VWAP for %s: %.4f", symbol, vwap)
    
    def get_fill_history(
        self,
        symbol: Optional[str] = None,
        account_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Fill]:
        """Get fill history with optional filters."""
        with self._history_lock:
            fills = self._fill_history.copy()
        
        # Apply filters
        if symbol:
            fills = [f for f in fills if f.symbol == symbol]
        if account_id:
            fills = [f for f in fills if f.account_id == account_id]
        
        # Return most recent fills
        return fills[-limit:]
    
    def calculate_pnl_attribution(
        self,
        symbol: Optional[str] = None,
        account_id: Optional[str] = None
    ) -> Dict:
        """Calculate P&L attribution from fill history."""
        fills = self.get_fill_history(symbol=symbol, account_id=account_id, limit=10000)
        
        total_pnl = 0.0
        total_slippage = 0.0
        total_commission = 0.0
        fill_count = len(fills)
        
        for fill in fills:
            vwap_data = self._get_vwap(fill.symbol)
            if vwap_data:
                _, slippage_amount = self._calculate_slippage(fill, vwap_data.vwap)
                total_slippage += slippage_amount
            
            total_commission += fill.commission
            total_pnl += -total_slippage - fill.commission
        
        return {
            "fill_count": fill_count,
            "total_pnl": total_pnl,
            "total_slippage": total_slippage,
            "total_commission": total_commission,
            "avg_slippage_per_fill": total_slippage / fill_count if fill_count > 0 else 0.0,
            "symbol": symbol,
            "account_id": account_id
        }
    
    def get_statistics(self) -> Dict:
        """Get current gate statistics."""
        with self._stats_lock:
            stats = self._stats.copy()
        
        # Calculate averages
        total_fills = stats.get("total_fills", 0)
        if total_fills > 0:
            stats["avg_slippage"] = stats["total_slippage"] / total_fills
            stats["excellent_fill_rate"] = stats.get("excellent_fills", 0) / total_fills
            stats["good_fill_rate"] = stats.get("good_fills", 0) / total_fills
            stats["acceptable_fill_rate"] = stats.get("acceptable_fills", 0) / total_fills
            stats["poor_fill_rate"] = stats.get("poor_fills", 0) / total_fills
            stats["unacceptable_fill_rate"] = stats.get("unacceptable_fills", 0) / total_fills
        
        return stats
    
    def reset_statistics(self):
        """Reset statistics counters."""
        with self._stats_lock:
            self._stats = {
                "total_fills": 0,
                "excellent_fills": 0,
                "good_fills": 0,
                "acceptable_fills": 0,
                "poor_fills": 0,
                "unacceptable_fills": 0,
                "total_slippage": 0.0,
                "reconciliations_triggered": 0
            }
        logger.info("Statistics reset")
