"""
Risk Dashboard - Phase 4.2
Layer 07: Monitoring & Observability

Real-time risk monitoring dashboard with:
- Live VaR/CVaR visualization
- Portfolio Beta tracking
- Portfolio Heatmap (position-level risk)
- JSON export for UI integration

Key Features:
- Real-time metric updates
- Historical tracking
- Export to .ly_state/session/risk_status.json
- Vectorized operations

Version: v21.0
Date: 2026-05-06
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from pathlib import Path
import json
import logging


@dataclass
class RiskDashboardConfig:
    """Configuration for Risk Dashboard"""
    
    # Update frequency
    update_interval_seconds: float = 1.0  # Real-time updates every 1 second
    
    # Export settings
    export_path: str = '.ly_state/session/risk_status.json'
    export_enabled: bool = True
    
    # Visualization settings
    heatmap_color_scheme: str = 'red_green'  # 'red_green' or 'blue_red'
    max_history_length: int = 1000  # Maximum history entries to keep
    
    # Risk thresholds for visualization
    var_warning_threshold: float = 0.025  # 2.5% VaR warning
    var_critical_threshold: float = 0.03  # 3% VaR critical
    cvar_warning_threshold: float = 0.06  # 6% CVaR warning
    cvar_critical_threshold: float = 0.08  # 8% CVaR critical
    beta_warning_threshold: float = 1.3  # Beta warning
    beta_critical_threshold: float = 1.5  # Beta critical


@dataclass
class RiskMetrics:
    """Current risk metrics snapshot"""
    
    timestamp: datetime
    var: float
    cvar: float
    beta: float
    portfolio_volatility: float
    max_drawdown: float
    sharpe_ratio: float
    
    # Status indicators
    var_status: str  # 'normal', 'warning', 'critical'
    cvar_status: str
    beta_status: str
    overall_status: str
    
    # Additional metrics
    num_positions: int = 0
    total_exposure: float = 0.0
    concentration_risk: float = 0.0


class RiskDashboard:
    """
    Real-time Risk Monitoring Dashboard.
    
    Features:
    - Live VaR/CVaR tracking
    - Portfolio Beta monitoring
    - Position-level heatmap
    - JSON export for UI integration
    - Historical tracking
    
    Usage:
        dashboard = RiskDashboard()
        dashboard.update_var_cvar(returns)
        dashboard.update_beta(portfolio_returns, market_returns)
        dashboard.export_risk_status()
    """
    
    def __init__(self, config: Optional[RiskDashboardConfig] = None):
        self.config = config or RiskDashboardConfig()
        self.logger = logging.getLogger(__name__)
        
        # Current metrics
        self._current_metrics: Optional[RiskMetrics] = None
        
        # Historical tracking
        self._var_history: List[Tuple[datetime, float]] = []
        self._cvar_history: List[Tuple[datetime, float]] = []
        self._beta_history: List[Tuple[datetime, float]] = []
        self._update_history: List[Dict[str, Any]] = []
        
        # Portfolio state
        self._portfolio_positions: Optional[pd.DataFrame] = None
        self._heatmap_data: Optional[Dict[str, Any]] = None
        
        # Ensure export directory exists
        if self.config.export_enabled:
            export_dir = Path(self.config.export_path).parent
            export_dir.mkdir(parents=True, exist_ok=True)
    
    def update_var_cvar(
        self,
        returns: np.ndarray,
        confidence: float = 0.95
    ) -> Dict[str, float]:
        """
        Update VaR and CVaR metrics.
        
        Args:
            returns: Array of portfolio returns
            confidence: Confidence level for VaR/CVaR
            
        Returns:
            Dictionary with updated VaR/CVaR values
        """
        timestamp = datetime.now(timezone.utc)
        
        if len(returns) == 0:
            return {'var': 0.0, 'cvar': 0.0}
        
        # Calculate VaR (vectorized)
        var_percentile = (1 - confidence) * 100
        var_value = abs(np.percentile(returns, var_percentile))
        
        # Calculate CVaR (vectorized)
        var_threshold = np.percentile(returns, var_percentile)
        tail_losses = returns[returns < var_threshold]
        
        if len(tail_losses) == 0:
            cvar_value = abs(var_threshold)
        else:
            cvar_value = abs(np.mean(tail_losses))
        
        # Update history
        self._var_history.append((timestamp, var_value))
        self._cvar_history.append((timestamp, cvar_value))
        
        # Trim history if needed
        if len(self._var_history) > self.config.max_history_length:
            self._var_history = self._var_history[-self.config.max_history_length:]
        if len(self._cvar_history) > self.config.max_history_length:
            self._cvar_history = self._cvar_history[-self.config.max_history_length:]
        
        # Determine status
        var_status = self._get_status(
            var_value,
            self.config.var_warning_threshold,
            self.config.var_critical_threshold
        )
        cvar_status = self._get_status(
            cvar_value,
            self.config.cvar_warning_threshold,
            self.config.cvar_critical_threshold
        )
        
        self.logger.info(
            f"VaR/CVaR updated: VaR={var_value:.2%} ({var_status}), "
            f"CVaR={cvar_value:.2%} ({cvar_status})"
        )
        
        return {'var': var_value, 'cvar': cvar_value}
    
    def update_beta(
        self,
        portfolio_returns: np.ndarray,
        market_returns: np.ndarray
    ) -> float:
        """
        Update portfolio beta.
        
        Args:
            portfolio_returns: Array of portfolio returns
            market_returns: Array of market returns
            
        Returns:
            Updated beta value
        """
        timestamp = datetime.now(timezone.utc)
        
        if len(portfolio_returns) == 0 or len(market_returns) == 0:
            return 0.0
        
        # Align lengths
        min_len = min(len(portfolio_returns), len(market_returns))
        portfolio_returns = portfolio_returns[-min_len:]
        market_returns = market_returns[-min_len:]
        
        # Calculate beta (vectorized)
        covariance = np.cov(portfolio_returns, market_returns)[0, 1]
        market_variance = np.var(market_returns, ddof=1)
        
        if market_variance == 0:
            beta_value = 0.0
        else:
            beta_value = covariance / market_variance
        
        # Update history
        self._beta_history.append((timestamp, beta_value))
        
        # Trim history if needed
        if len(self._beta_history) > self.config.max_history_length:
            self._beta_history = self._beta_history[-self.config.max_history_length:]
        
        # Determine status
        beta_status = self._get_status(
            abs(beta_value),
            self.config.beta_warning_threshold,
            self.config.beta_critical_threshold
        )
        
        self.logger.info(f"Beta updated: {beta_value:.2f} ({beta_status})")
        
        return beta_value
    
    def update_portfolio_metrics(
        self,
        returns: np.ndarray,
        market_returns: np.ndarray,
        positions: Optional[pd.DataFrame] = None
    ):
        """
        Update all portfolio metrics at once.
        
        Args:
            returns: Portfolio returns
            market_returns: Market returns
            positions: DataFrame with position details
        """
        timestamp = datetime.now(timezone.utc)
        
        # Update VaR/CVaR
        var_cvar = self.update_var_cvar(returns)
        
        # Update Beta
        beta = self.update_beta(returns, market_returns)
        
        # Calculate additional metrics
        portfolio_volatility = np.std(returns, ddof=1) if len(returns) > 0 else 0.0
        
        # Calculate max drawdown
        if len(returns) > 0:
            cumulative = np.cumprod(1 + returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = abs(np.min(drawdown))
        else:
            max_drawdown = 0.0
        
        # Calculate Sharpe ratio (assuming 0 risk-free rate)
        if portfolio_volatility > 0 and len(returns) > 0:
            sharpe_ratio = np.mean(returns) / portfolio_volatility * np.sqrt(252)
        else:
            sharpe_ratio = 0.0
        
        # Determine overall status
        var_status = self._get_status(
            var_cvar['var'],
            self.config.var_warning_threshold,
            self.config.var_critical_threshold
        )
        cvar_status = self._get_status(
            var_cvar['cvar'],
            self.config.cvar_warning_threshold,
            self.config.cvar_critical_threshold
        )
        beta_status = self._get_status(
            abs(beta),
            self.config.beta_warning_threshold,
            self.config.beta_critical_threshold
        )
        
        overall_status = self._determine_overall_status(
            var_status, cvar_status, beta_status
        )
        
        # Calculate position metrics
        num_positions = 0
        total_exposure = 0.0
        concentration_risk = 0.0
        
        if positions is not None and not positions.empty:
            self._portfolio_positions = positions
            num_positions = len(positions)
            if 'weight' in positions.columns:
                total_exposure = positions['weight'].sum()
                concentration_risk = positions['weight'].max()
        
        # Create metrics snapshot
        self._current_metrics = RiskMetrics(
            timestamp=timestamp,
            var=var_cvar['var'],
            cvar=var_cvar['cvar'],
            beta=beta,
            portfolio_volatility=portfolio_volatility,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            var_status=var_status,
            cvar_status=cvar_status,
            beta_status=beta_status,
            overall_status=overall_status,
            num_positions=num_positions,
            total_exposure=total_exposure,
            concentration_risk=concentration_risk
        )
        
        # Add to update history
        self._update_history.append({
            'timestamp': timestamp.isoformat(),
            'var': var_cvar['var'],
            'cvar': var_cvar['cvar'],
            'beta': beta,
            'overall_status': overall_status
        })
        
        # Trim update history
        if len(self._update_history) > self.config.max_history_length:
            self._update_history = self._update_history[-self.config.max_history_length:]
    
    def generate_portfolio_heatmap(
        self,
        positions: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Generate portfolio heatmap data.
        
        Args:
            positions: DataFrame with columns:
                - ticker: Stock ticker
                - weight: Position weight
                - return_1d: 1-day return
                - volatility: Historical volatility
                - sector: Sector classification (optional)
                
        Returns:
            Dictionary with heatmap data for visualization
        """
        if positions.empty:
            return {
                'tickers': [],
                'weights': [],
                'returns': [],
                'risk_scores': [],
                'sectors': []
            }
        
        # Extract data (vectorized)
        tickers = positions['ticker'].tolist()
        weights = positions['weight'].tolist()
        returns_1d = positions['return_1d'].tolist()
        volatilities = positions['volatility'].tolist()
        
        # Calculate risk scores (weight * volatility)
        risk_scores = (positions['weight'] * positions['volatility']).tolist()
        
        # Get sectors if available
        sectors = positions['sector'].tolist() if 'sector' in positions.columns else ['Unknown'] * len(tickers)
        
        # Sort by weight (descending)
        sorted_indices = np.argsort(weights)[::-1]
        
        heatmap_data = {
            'tickers': [tickers[i] for i in sorted_indices],
            'weights': [weights[i] for i in sorted_indices],
            'returns': [returns_1d[i] for i in sorted_indices],
            'risk_scores': [risk_scores[i] for i in sorted_indices],
            'volatilities': [volatilities[i] for i in sorted_indices],
            'sectors': [sectors[i] for i in sorted_indices],
            'color_scheme': self.config.heatmap_color_scheme
        }
        
        self._heatmap_data = heatmap_data
        
        return heatmap_data
    
    def export_risk_status(self) -> str:
        """
        Export current risk status to JSON file.
        
        Returns:
            Path to exported JSON file
        """
        if not self.config.export_enabled:
            self.logger.warning("Export is disabled in config")
            return ""
        
        if self._current_metrics is None:
            self.logger.warning("No metrics to export")
            return ""
        
        # Prepare export data
        export_data = {
            'timestamp': self._current_metrics.timestamp.isoformat(),
            'status': self._current_metrics.overall_status,
            'metrics': {
                'var': self._current_metrics.var,
                'cvar': self._current_metrics.cvar,
                'beta': self._current_metrics.beta,
                'portfolio_volatility': self._current_metrics.portfolio_volatility,
                'max_drawdown': self._current_metrics.max_drawdown,
                'sharpe_ratio': self._current_metrics.sharpe_ratio
            },
            'status_indicators': {
                'var_status': self._current_metrics.var_status,
                'cvar_status': self._current_metrics.cvar_status,
                'beta_status': self._current_metrics.beta_status
            },
            'portfolio': {
                'num_positions': self._current_metrics.num_positions,
                'total_exposure': self._current_metrics.total_exposure,
                'concentration_risk': self._current_metrics.concentration_risk
            },
            'heatmap': self._heatmap_data if self._heatmap_data else {},
            'history': {
                'var': [(ts.isoformat(), val) for ts, val in self._var_history[-100:]],
                'cvar': [(ts.isoformat(), val) for ts, val in self._cvar_history[-100:]],
                'beta': [(ts.isoformat(), val) for ts, val in self._beta_history[-100:]]
            }
        }
        
        # Write to file
        export_path = Path(self.config.export_path)
        with open(export_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        self.logger.info(f"Risk status exported to {export_path}")
        
        return str(export_path)
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics as dictionary"""
        if self._current_metrics is None:
            return {}
        
        return {
            'timestamp': self._current_metrics.timestamp.isoformat(),
            'var': self._current_metrics.var,
            'cvar': self._current_metrics.cvar,
            'beta': self._current_metrics.beta,
            'portfolio_volatility': self._current_metrics.portfolio_volatility,
            'max_drawdown': self._current_metrics.max_drawdown,
            'sharpe_ratio': self._current_metrics.sharpe_ratio,
            'overall_status': self._current_metrics.overall_status
        }
    
    def get_update_history(self) -> List[Dict[str, Any]]:
        """Get update history"""
        return self._update_history.copy()
    
    def _get_status(
        self,
        value: float,
        warning_threshold: float,
        critical_threshold: float
    ) -> str:
        """Determine status based on thresholds"""
        if value >= critical_threshold:
            return 'critical'
        elif value >= warning_threshold:
            return 'warning'
        else:
            return 'normal'
    
    def _determine_overall_status(
        self,
        var_status: str,
        cvar_status: str,
        beta_status: str
    ) -> str:
        """Determine overall portfolio status"""
        statuses = [var_status, cvar_status, beta_status]
        
        if 'critical' in statuses:
            return 'critical'
        elif 'warning' in statuses:
            return 'warning'
        else:
            return 'normal'
    
    def reset(self):
        """Reset dashboard state"""
        self._current_metrics = None
        self._var_history.clear()
        self._cvar_history.clear()
        self._beta_history.clear()
        self._update_history.clear()
        self._portfolio_positions = None
        self._heatmap_data = None
        self.logger.info("Risk dashboard reset")


if __name__ == '__main__':
    print("=" * 80)
    print("RISK DASHBOARD - DEMO")
    print("=" * 80)
    
    # Initialize
    config = RiskDashboardConfig(
        export_path='.ly_state/session/risk_status.json'
    )
    dashboard = RiskDashboard(config)
    
    # Generate sample data
    np.random.seed(42)
    returns = np.random.randn(252) * 0.02
    market_returns = np.random.randn(252) * 0.02
    
    # Create sample positions
    positions = pd.DataFrame({
        'ticker': ['VNM', 'HPG', 'VCB', 'GAS', 'VIC'],
        'weight': [0.25, 0.20, 0.20, 0.20, 0.15],
        'return_1d': [0.02, -0.03, 0.01, -0.01, 0.04],
        'volatility': [0.015, 0.025, 0.020, 0.018, 0.030],
        'sector': ['Consumer', 'Materials', 'Banking', 'Energy', 'Real Estate']
    })
    
    # Test 1: Update metrics
    print("\n1. Updating Portfolio Metrics...")
    dashboard.update_portfolio_metrics(returns, market_returns, positions)
    
    # Test 2: Get current metrics
    print("\n2. Current Risk Metrics:")
    metrics = dashboard.get_current_metrics()
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"   {key}: {value:.4f}")
        else:
            print(f"   {key}: {value}")
    
    # Test 3: Generate heatmap
    print("\n3. Portfolio Heatmap:")
    heatmap = dashboard.generate_portfolio_heatmap(positions)
    for i, ticker in enumerate(heatmap['tickers']):
        print(f"   {ticker}: Weight={heatmap['weights'][i]:.2%}, "
              f"Return={heatmap['returns'][i]:+.2%}, "
              f"Risk Score={heatmap['risk_scores'][i]:.4f}")
    
    # Test 4: Export to JSON
    print("\n4. Exporting Risk Status...")
    export_path = dashboard.export_risk_status()
    print(f"   Exported to: {export_path}")
    
    # Verify export
    if Path(export_path).exists():
        with open(export_path, 'r') as f:
            data = json.load(f)
        print(f"   Status: {data['status']}")
        print(f"   VaR: {data['metrics']['var']:.2%}")
        print(f"   CVaR: {data['metrics']['cvar']:.2%}")
        print(f"   Beta: {data['metrics']['beta']:.2f}")
    
    print("\n" + "=" * 80)
    print("Risk Dashboard demo complete")
    print("=" * 80)
