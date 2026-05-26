"""
Advanced Circuit Breaker - Phase 4.1
Layer 04: Risk Management

Real-time VaR/CVaR breach monitoring with Vietnam market-specific features:
- VaR/CVaR breach detection
- Limit-lock awareness (Vietnam: ±7% daily limits)
- Automatic portfolio de-risking when CVaR > 8%
- Beta monitoring
- Sector contagion detection

Key Features:
- PIT-compliant (no lookahead bias)
- Vectorized operations (NumPy/Pandas)
- Vietnam market microstructure awareness
- Institutional-grade risk controls

Version: v21.0
Date: 2026-05-06
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import logging
from datetime import datetime, timezone


@dataclass
class AdvancedCircuitBreakerConfig:
    """Configuration for Advanced Circuit Breaker"""
    
    # VaR/CVaR Limits
    var_limit: float = 0.03  # 3% daily VaR limit
    cvar_limit: float = 0.08  # 8% CVaR limit (triggers de-risking)
    confidence_level: float = 0.95  # 95% confidence for VaR/CVaR
    
    # Beta Limits
    beta_limit: float = 1.5  # Maximum portfolio beta
    
    # Correlation Hard Stop (P1 UPGRADE)
    correlation_hard_stop: float = 0.75  # Maximum pairwise correlation
    correlation_dynamic_threshold: bool = True  # Enable regime-based dynamic threshold
    
    # ADV Participation Cap (P1 UPGRADE)
    adv_participation_cap: float = 0.40  # 40% hard cap for Individual Scale (2B-5B)
    
    # Auto De-risking
    auto_derisk_enabled: bool = True
    derisk_target_cvar: float = 0.05  # Target CVaR after de-risking
    derisk_multiplier: float = 0.6  # Reduce exposure to 60% when triggered
    
    # Vietnam Market Limits
    vietnam_floor_limit: float = -0.07  # -7% floor
    vietnam_ceiling_limit: float = 0.07  # +7% ceiling
    min_bid_volume_threshold: float = 100.0  # Minimum bid volume to consider liquid
    
    # Lookback Windows
    var_lookback_days: int = 252  # 1 year for VaR
    cvar_lookback_days: int = 252  # 1 year for CVaR
    beta_lookback_days: int = 60  # 3 months for beta
    correlation_lookback_days: int = 60  # 3 months for correlation


@dataclass
class RiskBreachStatus:
    """Status of risk breach check"""
    
    metric_name: str
    metric_value: float
    limit: float
    is_breached: bool
    breach_severity: float  # How much over limit (0 = no breach, >0 = breach)
    action: str  # 'allow', 'warn', 'block_new_positions', 'reduce_exposure'
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Additional metrics
    var_value: Optional[float] = None
    cvar_value: Optional[float] = None
    beta_value: Optional[float] = None
    correlation_value: Optional[float] = None  # P1 UPGRADE
    adv_participation: Optional[float] = None  # P1 UPGRADE


@dataclass
class LimitLockStatus:
    """Status of limit-lock check for a stock"""
    
    ticker: str
    is_limit_locked: bool
    lock_type: Optional[str] = None  # 'floor', 'ceiling', 'foreign_room', or None
    current_price: float = 0.0
    reference_price: float = 0.0
    price_change_pct: float = 0.0
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    can_buy: bool = True
    can_sell: bool = True
    reason: str = ""
    
    # P1 UPGRADE: Foreign room exhaustion
    foreign_ownership_pct: Optional[float] = None
    foreign_limit_pct: Optional[float] = None
    foreign_room_exhausted: bool = False


class AdvancedCircuitBreaker:
    """
    Advanced Circuit Breaker with real-time VaR/CVaR monitoring.
    
    Features:
    - Real-time VaR/CVaR breach detection
    - Limit-lock awareness (Vietnam market)
    - Automatic portfolio de-risking
    - Beta monitoring
    - Sector contagion detection
    
    PIT Compliance:
        - All calculations use only historical data (no lookahead)
        - Returns must be properly lagged
        - Market data must be T-1 or earlier
    
    Vectorization:
        - All operations use NumPy/Pandas vectorized methods
        - No Python loops over data points
    """
    
    def __init__(self, config: Optional[AdvancedCircuitBreakerConfig] = None):
        self.config = config or AdvancedCircuitBreakerConfig()
        self.logger = logging.getLogger(__name__)
        
        # State tracking
        self._limit_lock_cache: Dict[str, LimitLockStatus] = {}
        self._block_reasons: Dict[str, str] = {}
        self._last_breach_status: Optional[RiskBreachStatus] = None
    
    def check_var_breach(
        self,
        returns: np.ndarray,
        confidence: Optional[float] = None
    ) -> RiskBreachStatus:
        """
        Check if VaR breaches the limit.
        
        VaR (Value at Risk) = percentile of loss distribution at confidence level
        
        Args:
            returns: Array of portfolio returns (PIT-compliant, no lookahead)
            confidence: Confidence level (default from config)
            
        Returns:
            RiskBreachStatus with VaR breach information
        """
        if confidence is None:
            confidence = self.config.confidence_level
        
        if len(returns) == 0:
            return RiskBreachStatus(
                metric_name='VaR',
                metric_value=0.0,
                limit=self.config.var_limit,
                is_breached=False,
                breach_severity=0.0,
                action='allow',
                message='No returns data available',
                var_value=0.0
            )
        
        # Use only lookback window (PIT-compliant)
        window = min(len(returns), self.config.var_lookback_days)
        recent_returns = returns[-window:]
        
        # Calculate VaR using historical simulation (vectorized)
        var_percentile = (1 - confidence) * 100
        var_value = abs(np.percentile(recent_returns, var_percentile))
        
        # Check breach
        is_breached = var_value > self.config.var_limit
        breach_severity = max(0.0, var_value - self.config.var_limit)
        
        # Determine action
        if is_breached:
            if breach_severity > self.config.var_limit * 0.5:  # >50% over limit
                action = 'block_new_positions'
                message = f'VaR {var_value:.2%} exceeds limit {self.config.var_limit:.2%} by >50%. Blocking new positions.'
            else:
                action = 'warn'
                message = f'VaR {var_value:.2%} exceeds limit {self.config.var_limit:.2%}. Warning issued.'
        else:
            action = 'allow'
            message = f'VaR {var_value:.2%} within limit {self.config.var_limit:.2%}.'
        
        status = RiskBreachStatus(
            metric_name='VaR',
            metric_value=var_value,
            limit=self.config.var_limit,
            is_breached=is_breached,
            breach_severity=breach_severity,
            action=action,
            message=message,
            var_value=var_value
        )
        
        self._last_breach_status = status
        return status
    
    def check_cvar_breach(
        self,
        returns: np.ndarray,
        confidence: Optional[float] = None
    ) -> RiskBreachStatus:
        """
        Check if CVaR (Expected Shortfall) breaches the limit.
        
        CVaR = average of losses beyond VaR threshold
        
        Args:
            returns: Array of portfolio returns (PIT-compliant)
            confidence: Confidence level (default from config)
            
        Returns:
            RiskBreachStatus with CVaR breach information
        """
        if confidence is None:
            confidence = self.config.confidence_level
        
        if len(returns) == 0:
            return RiskBreachStatus(
                metric_name='CVaR',
                metric_value=0.0,
                limit=self.config.cvar_limit,
                is_breached=False,
                breach_severity=0.0,
                action='allow',
                message='No returns data available',
                cvar_value=0.0
            )
        
        # Use only lookback window (PIT-compliant)
        window = min(len(returns), self.config.cvar_lookback_days)
        recent_returns = returns[-window:]
        
        # Calculate CVaR using historical simulation (vectorized)
        var_percentile = (1 - confidence) * 100
        var_threshold = np.percentile(recent_returns, var_percentile)
        
        # Tail losses: all returns below VaR threshold
        tail_losses = recent_returns[recent_returns < var_threshold]
        
        if len(tail_losses) == 0:
            # No tail losses, use VaR as proxy
            cvar_value = abs(var_threshold)
        else:
            # CVaR = average of tail losses (vectorized)
            cvar_value = abs(np.mean(tail_losses))
        
        # Check breach
        is_breached = cvar_value > self.config.cvar_limit
        breach_severity = max(0.0, cvar_value - self.config.cvar_limit)
        
        # Determine action
        if is_breached:
            if self.config.auto_derisk_enabled:
                action = 'reduce_exposure'
                message = f'CVaR {cvar_value:.2%} exceeds limit {self.config.cvar_limit:.2%}. Auto de-risking triggered.'
            else:
                action = 'block_new_positions'
                message = f'CVaR {cvar_value:.2%} exceeds limit {self.config.cvar_limit:.2%}. Blocking new positions.'
        else:
            action = 'allow'
            message = f'CVaR {cvar_value:.2%} within limit {self.config.cvar_limit:.2%}.'
        
        status = RiskBreachStatus(
            metric_name='CVaR',
            metric_value=cvar_value,
            limit=self.config.cvar_limit,
            is_breached=is_breached,
            breach_severity=breach_severity,
            action=action,
            message=message,
            cvar_value=cvar_value
        )
        
        self._last_breach_status = status
        return status
    
    def compute_derisk_action(
        self,
        returns: np.ndarray
    ) -> Dict[str, Any]:
        """
        Compute de-risking action when CVaR > 8%.
        
        Args:
            returns: Array of portfolio returns
            
        Returns:
            Dictionary with de-risking action details
        """
        cvar_status = self.check_cvar_breach(returns)
        
        if not cvar_status.is_breached:
            return {
                'action': 'none',
                'target_multiplier': 1.0,
                'reason': 'no_breach',
                'current_cvar': cvar_status.cvar_value,
                'target_cvar': self.config.cvar_limit
            }
        
        # Calculate target exposure multiplier
        # Target: reduce CVaR from current to target level
        current_cvar = cvar_status.cvar_value
        target_cvar = self.config.derisk_target_cvar
        
        # Approximate linear scaling (CVaR scales roughly with exposure)
        if current_cvar > 0:
            target_multiplier = min(
                target_cvar / current_cvar,
                self.config.derisk_multiplier
            )
        else:
            target_multiplier = self.config.derisk_multiplier
        
        # Ensure multiplier is in valid range
        target_multiplier = max(0.0, min(1.0, target_multiplier))
        
        self.logger.warning(
            f"De-risking triggered: CVaR {current_cvar:.2%} > {self.config.cvar_limit:.2%}. "
            f"Reducing exposure to {target_multiplier:.1%}"
        )
        
        return {
            'action': 'reduce_exposure',
            'target_multiplier': target_multiplier,
            'reason': 'cvar_breach',
            'current_cvar': current_cvar,
            'target_cvar': target_cvar,
            'breach_severity': cvar_status.breach_severity
        }
    
    def check_beta_breach(
        self,
        portfolio_returns: np.ndarray,
        market_returns: np.ndarray
    ) -> RiskBreachStatus:
        """
        Check if portfolio beta breaches the limit.
        
        Beta = Cov(portfolio, market) / Var(market)
        
        Args:
            portfolio_returns: Array of portfolio returns
            market_returns: Array of market returns (e.g., VN-Index)
            
        Returns:
            RiskBreachStatus with beta breach information
        """
        if len(portfolio_returns) == 0 or len(market_returns) == 0:
            return RiskBreachStatus(
                metric_name='Beta',
                metric_value=0.0,
                limit=self.config.beta_limit,
                is_breached=False,
                breach_severity=0.0,
                action='allow',
                message='No returns data available',
                beta_value=0.0
            )
        
        # Align lengths
        min_len = min(len(portfolio_returns), len(market_returns))
        portfolio_returns = portfolio_returns[-min_len:]
        market_returns = market_returns[-min_len:]
        
        # Use only lookback window
        window = min(min_len, self.config.beta_lookback_days)
        portfolio_returns = portfolio_returns[-window:]
        market_returns = market_returns[-window:]
        
        # Calculate beta (vectorized)
        covariance = np.cov(portfolio_returns, market_returns)[0, 1]
        market_variance = np.var(market_returns, ddof=1)
        
        if market_variance == 0:
            beta_value = 0.0
        else:
            beta_value = covariance / market_variance
        
        # Check breach
        is_breached = abs(beta_value) > self.config.beta_limit
        breach_severity = max(0.0, abs(beta_value) - self.config.beta_limit)
        
        # Determine action
        if is_breached:
            action = 'warn'
            message = f'Beta {beta_value:.2f} exceeds limit {self.config.beta_limit:.2f}. High market correlation.'
        else:
            action = 'allow'
            message = f'Beta {beta_value:.2f} within limit {self.config.beta_limit:.2f}.'
        
        return RiskBreachStatus(
            metric_name='Beta',
            metric_value=abs(beta_value),
            limit=self.config.beta_limit,
            is_breached=is_breached,
            breach_severity=breach_severity,
            action=action,
            message=message,
            beta_value=beta_value
        )
    
    def check_correlation_breach(
        self,
        returns_matrix: np.ndarray,
        tickers: List[str],
        regime: Optional[str] = None
    ) -> RiskBreachStatus:
        """
        P1 UPGRADE: Check if pairwise correlation exceeds HARD STOP (0.75).
        
        Dynamic Threshold based on Regime:
        - Bull: 0.80 (more tolerance for correlation in rising markets)
        - Bear: 0.70 (stricter in falling markets to avoid contagion)
        - Sideways: 0.75 (default)
        
        Args:
            returns_matrix: Matrix of returns (shape: [n_periods, n_assets])
            tickers: List of ticker symbols
            regime: Market regime ('bull', 'bear', 'sideways', or None for default)
            
        Returns:
            RiskBreachStatus with correlation breach information
        """
        if returns_matrix.shape[0] == 0 or returns_matrix.shape[1] < 2:
            return RiskBreachStatus(
                metric_name='Correlation',
                metric_value=0.0,
                limit=self.config.correlation_hard_stop,
                is_breached=False,
                breach_severity=0.0,
                action='allow',
                message='Insufficient data for correlation check',
                correlation_value=0.0
            )
        
        # P1 UPGRADE: Dynamic threshold based on regime
        if self.config.correlation_dynamic_threshold and regime is not None:
            regime_lower = regime.lower()
            if regime_lower == 'bull':
                correlation_limit = 0.80  # More tolerance in bull markets
            elif regime_lower == 'bear':
                correlation_limit = 0.70  # Stricter in bear markets
            else:  # sideways or unknown
                correlation_limit = self.config.correlation_hard_stop
        else:
            correlation_limit = self.config.correlation_hard_stop
        
        # Use only lookback window (PIT-compliant)
        window = min(returns_matrix.shape[0], self.config.correlation_lookback_days)
        recent_returns = returns_matrix[-window:, :]
        
        # Calculate correlation matrix (vectorized)
        corr_matrix = np.corrcoef(recent_returns, rowvar=False)
        
        # Find maximum pairwise correlation (excluding diagonal)
        np.fill_diagonal(corr_matrix, 0.0)
        max_corr = np.max(np.abs(corr_matrix))
        
        # Find the pair with max correlation
        max_idx = np.unravel_index(np.argmax(np.abs(corr_matrix)), corr_matrix.shape)
        ticker1 = tickers[max_idx[0]] if max_idx[0] < len(tickers) else f"Asset_{max_idx[0]}"
        ticker2 = tickers[max_idx[1]] if max_idx[1] < len(tickers) else f"Asset_{max_idx[1]}"
        
        # Check breach
        is_breached = max_corr > correlation_limit
        breach_severity = max(0.0, max_corr - correlation_limit)
        
        # Determine action
        if is_breached:
            action = 'reduce_exposure'
            regime_msg = f" (regime: {regime}, limit: {correlation_limit:.2f})" if regime else ""
            message = (
                f'Correlation {max_corr:.2f} between {ticker1} and {ticker2} '
                f'exceeds HARD STOP{regime_msg}. Immediate de-risking triggered.'
            )
        else:
            action = 'allow'
            regime_msg = f" (regime: {regime}, limit: {correlation_limit:.2f})" if regime else ""
            message = f'Max correlation {max_corr:.2f} within HARD STOP{regime_msg}.'
        
        status = RiskBreachStatus(
            metric_name='Correlation',
            metric_value=max_corr,
            limit=correlation_limit,
            is_breached=is_breached,
            breach_severity=breach_severity,
            action=action,
            message=message,
            correlation_value=max_corr
        )
        
        if is_breached:
            self.logger.error(f"CORRELATION BREACH: {message}")
        
        return status
    
    def check_adv_breach(
        self,
        position_size: float,
        adv: float,
        ticker: str
    ) -> RiskBreachStatus:
        """
        P1 UPGRADE: Check if ADV participation exceeds HARD CAP (40% for Individual Scale 2B-5B).
        
        Args:
            position_size: Position size in shares
            adv: Average Daily Volume in shares
            ticker: Stock ticker
            
        Returns:
            RiskBreachStatus with ADV breach information
        """
        if adv <= 0:
            return RiskBreachStatus(
                metric_name='ADV',
                metric_value=0.0,
                limit=self.config.adv_participation_cap,
                is_breached=False,
                breach_severity=0.0,
                action='allow',
                message=f'{ticker}: No ADV data available',
                adv_participation=0.0
            )
        
        # Calculate ADV participation
        adv_participation = position_size / adv
        
        # Check breach
        is_breached = adv_participation > self.config.adv_participation_cap
        breach_severity = max(0.0, adv_participation - self.config.adv_participation_cap)
        
        # Determine action
        if is_breached:
            action = 'block_new_positions'
            message = (
                f'{ticker}: ADV participation {adv_participation:.1%} '
                f'exceeds HARD CAP {self.config.adv_participation_cap:.0%} (Individual Scale 2B-5B). '
                f'Blocking new positions.'
            )
        else:
            action = 'allow'
            message = f'{ticker}: ADV participation {adv_participation:.1%} within HARD CAP {self.config.adv_participation_cap:.0%}.'
        
        status = RiskBreachStatus(
            metric_name='ADV',
            metric_value=adv_participation,
            limit=self.config.adv_participation_cap,
            is_breached=is_breached,
            breach_severity=breach_severity,
            action=action,
            message=message,
            adv_participation=adv_participation
        )
        
        if is_breached:
            self.logger.error(f"ADV BREACH: {message}")
        
        return status
    
    def check_limit_lock(
        self,
        market_data: pd.DataFrame
    ) -> Dict[str, LimitLockStatus]:
        """
        Check for limit-lock conditions (Vietnam market specific).
        
        P1 UPGRADE: Vectorized implementation with Foreign Room Exhaustion logic.
        
        Limit-lock occurs when:
        - Stock hits floor (-7%) with zero or minimal bids
        - Stock hits ceiling (+7%) with zero or minimal asks
        - Foreign room exhausted: foreign_ownership_pct >= foreign_limit_pct
        
        Args:
            market_data: DataFrame with columns:
                - ticker: Stock ticker
                - current_price: Current price
                - reference_price: Reference price (previous close)
                - bid_volume: Total bid volume
                - ask_volume: Total ask volume
                - foreign_ownership_pct: Current foreign ownership % (optional, P1 UPGRADE)
                - foreign_limit_pct: Foreign ownership limit % (optional, P1 UPGRADE)
                
        Returns:
            Dictionary mapping ticker -> LimitLockStatus
        """
        limit_lock_status = {}
        
        if market_data.empty:
            return limit_lock_status

        current_price = market_data.get('current_price')
        if current_price is None:
            current_price = market_data.get(
                'price',
                pd.Series(0.0, index=market_data.index, dtype=np.float64)
            )
        current_price = current_price.fillna(0.0).astype(np.float64)

        # Backward compatibility: older pipeline fixtures only provide `price`.
        # In that case we cannot infer a limit move, so use current price as
        # a neutral reference and keep price_change_pct at 0 unless provided.
        reference_price = market_data.get('reference_price', current_price)
        reference_price = reference_price.fillna(current_price).astype(np.float64)
        
        # P1 UPGRADE: Vectorized calculation (no iterrows for performance)
        # Calculate price change percentage (vectorized)
        price_change_pct = np.where(
            reference_price > 0,
            (current_price - reference_price) / reference_price,
            0.0
        )
        
        # Get bid/ask volumes with defaults
        bid_volume = market_data.get('bid_volume', pd.Series(0.0, index=market_data.index)).fillna(0.0)
        ask_volume = market_data.get('ask_volume', pd.Series(0.0, index=market_data.index)).fillna(0.0)
        
        # P1 UPGRADE: Get foreign ownership data with defaults
        foreign_ownership_pct = market_data.get('foreign_ownership_pct', pd.Series(None, index=market_data.index))
        foreign_limit_pct = market_data.get('foreign_limit_pct', pd.Series(None, index=market_data.index))
        
        # Check for floor limit-lock (vectorized)
        is_floor_locked = (
            (price_change_pct <= (self.config.vietnam_floor_limit + 0.005)) &
            (price_change_pct >= (self.config.vietnam_floor_limit - 0.005)) &
            (bid_volume < self.config.min_bid_volume_threshold)
        )
        
        # Check for ceiling limit-lock (vectorized)
        is_ceiling_locked = (
            (price_change_pct >= (self.config.vietnam_ceiling_limit - 0.005)) &
            (price_change_pct <= (self.config.vietnam_ceiling_limit + 0.005)) &
            (ask_volume < self.config.min_bid_volume_threshold)
        )
        
        # P1 UPGRADE: Check for foreign room exhaustion (vectorized)
        is_foreign_room_exhausted = pd.Series(False, index=market_data.index)
        has_foreign_data = foreign_ownership_pct.notna() & foreign_limit_pct.notna()
        is_foreign_room_exhausted[has_foreign_data] = (
            foreign_ownership_pct[has_foreign_data] >= foreign_limit_pct[has_foreign_data]
        )
        
        # Build status for each ticker
        for idx in market_data.index:
            ticker = market_data.loc[idx, 'ticker']
            current_price_value = current_price.loc[idx]
            reference_price_value = reference_price.loc[idx]
            pct_change = price_change_pct[idx]
            bid_vol = bid_volume.iloc[idx]
            ask_vol = ask_volume.iloc[idx]
            floor_locked = is_floor_locked.iloc[idx]
            ceiling_locked = is_ceiling_locked.iloc[idx]
            foreign_room_exhausted = is_foreign_room_exhausted.iloc[idx]
            
            # P1 UPGRADE: Get foreign ownership data
            foreign_own_pct = foreign_ownership_pct.iloc[idx] if pd.notna(foreign_ownership_pct.iloc[idx]) else None
            foreign_lim_pct = foreign_limit_pct.iloc[idx] if pd.notna(foreign_limit_pct.iloc[idx]) else None
            
            is_limit_locked = floor_locked or ceiling_locked or foreign_room_exhausted
            
            if floor_locked:
                lock_type = 'floor'
                can_sell = False  # Cannot sell at floor with no bids
                can_buy = True
                reason = 'Floor lock: zero bids - BLOCKING SELL to avoid slippage spiral'
            elif ceiling_locked:
                lock_type = 'ceiling'
                can_sell = True
                can_buy = False  # Cannot buy at ceiling with no asks
                reason = 'Ceiling lock: zero asks - BLOCKING BUY'
            elif foreign_room_exhausted:
                # P1 UPGRADE: Foreign room exhaustion
                lock_type = 'foreign_room'
                can_sell = True  # Can sell (reduces foreign ownership)
                can_buy = False  # BLOCK buy (would increase foreign ownership)
                reason = f'Foreign room exhausted: {foreign_own_pct:.1%} >= {foreign_lim_pct:.1%} - BLOCKING BUY'
            else:
                lock_type = None
                can_sell = True
                can_buy = True
                reason = ''
            
            status = LimitLockStatus(
                ticker=ticker,
                is_limit_locked=is_limit_locked,
                lock_type=lock_type,
                current_price=current_price_value,
                reference_price=reference_price_value,
                price_change_pct=pct_change,
                bid_volume=bid_vol,
                ask_volume=ask_vol,
                can_buy=can_buy,
                can_sell=can_sell,
                reason=reason,
                foreign_ownership_pct=foreign_own_pct,
                foreign_limit_pct=foreign_lim_pct,
                foreign_room_exhausted=foreign_room_exhausted
            )
            
            limit_lock_status[ticker] = status
            self._limit_lock_cache[ticker] = status
            
            if is_limit_locked:
                if lock_type == 'floor':
                    self._block_reasons[ticker] = 'limit_locked_floor_no_bids'
                elif lock_type == 'ceiling':
                    self._block_reasons[ticker] = 'limit_locked_ceiling_no_asks'
                elif lock_type == 'foreign_room':
                    self._block_reasons[ticker] = 'limit_locked_foreign_room'
                else:
                    self._block_reasons[ticker] = f'limit_locked_{lock_type}'
                self.logger.warning(f"Limit-lock detected: {ticker} at {lock_type} with {reason}")
        
        return limit_lock_status
    
    def can_execute_order(
        self,
        order: Dict[str, Any],
        market_data: pd.DataFrame
    ) -> bool:
        """
        Check if an order can be executed given limit-lock conditions.
        
        Args:
            order: Order dictionary with keys: ticker, side, quantity
            market_data: Current market data
            
        Returns:
            True if order can be executed, False otherwise
        """
        ticker = order['ticker']
        side = order['side']
        
        # Check limit-lock status
        limit_lock_status = self.check_limit_lock(market_data)
        
        if ticker not in limit_lock_status:
            # No market data, allow by default
            return True
        
        status = limit_lock_status[ticker]
        
        if not status.is_limit_locked:
            return True
        
        # Check if order side is blocked
        if side == 'buy' and not status.can_buy:
            self.logger.warning(f"Order blocked: Cannot buy {ticker} (limit-locked at ceiling)")
            return False
        
        if side == 'sell' and not status.can_sell:
            self.logger.warning(f"Order blocked: Cannot sell {ticker} (limit-locked at floor with no bids)")
            return False
        
        return True
    
    def get_block_reason(self, ticker: str) -> Optional[str]:
        """Get the reason why a ticker is blocked"""
        return self._block_reasons.get(ticker)
    
    def check_sector_contagion(
        self,
        market_data: pd.DataFrame,
        limit_lock_status: Dict[str, LimitLockStatus]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Check for sector-wide contagion (multiple stocks in same sector limit-locked).
        
        Args:
            market_data: DataFrame with 'sector' column
            limit_lock_status: Limit-lock status for each ticker
            
        Returns:
            Dictionary mapping sector -> contagion metrics
        """
        if 'sector' not in market_data.columns:
            return {}
        
        sector_stats = {}
        
        for sector in market_data['sector'].unique():
            sector_stocks = market_data[market_data['sector'] == sector]['ticker'].tolist()
            
            locked_count = sum(
                1 for ticker in sector_stocks
                if ticker in limit_lock_status and limit_lock_status[ticker].is_limit_locked
            )
            
            total_count = len(sector_stocks)
            locked_ratio = locked_count / total_count if total_count > 0 else 0.0
            
            contagion_detected = locked_ratio > 0.5  # >50% of sector locked
            
            sector_stats[sector] = {
                'total_stocks': total_count,
                'locked_stocks': locked_count,
                'locked_ratio': locked_ratio,
                'contagion_detected': contagion_detected
            }
            
            if contagion_detected:
                self.logger.error(
                    f"SECTOR CONTAGION DETECTED: {sector} - "
                    f"{locked_count}/{total_count} stocks limit-locked ({locked_ratio:.1%})"
                )
        
        return sector_stats
    
    def reset(self):
        """Reset circuit breaker state"""
        self._limit_lock_cache.clear()
        self._block_reasons.clear()
        self._last_breach_status = None
        self.logger.info("Advanced circuit breaker reset")


if __name__ == '__main__':
    print("=" * 80)
    print("ADVANCED CIRCUIT BREAKER - DEMO")
    print("=" * 80)
    
    # Initialize
    config = AdvancedCircuitBreakerConfig(
        var_limit=0.03,
        cvar_limit=0.08,
        beta_limit=1.5
    )
    breaker = AdvancedCircuitBreaker(config)
    
    # Test 1: VaR breach detection
    print("\n1. VaR Breach Detection")
    np.random.seed(42)
    returns = np.random.randn(252) * 0.05  # High volatility
    var_status = breaker.check_var_breach(returns)
    print(f"   VaR: {var_status.var_value:.2%}")
    print(f"   Breached: {var_status.is_breached}")
    print(f"   Action: {var_status.action}")
    
    # Test 2: CVaR breach detection
    print("\n2. CVaR Breach Detection")
    tail_returns = np.concatenate([
        np.random.randn(240) * 0.02,
        np.random.randn(12) * 0.15  # Fat tail
    ])
    cvar_status = breaker.check_cvar_breach(tail_returns)
    print(f"   CVaR: {cvar_status.cvar_value:.2%}")
    print(f"   Breached: {cvar_status.is_breached}")
    print(f"   Action: {cvar_status.action}")
    
    # Test 3: Auto de-risking
    if cvar_status.is_breached:
        print("\n3. Auto De-risking")
        derisk_action = breaker.compute_derisk_action(tail_returns)
        print(f"   Action: {derisk_action['action']}")
        print(f"   Target Multiplier: {derisk_action['target_multiplier']:.1%}")
        print(f"   Reason: {derisk_action['reason']}")
    
    # Test 4: Limit-lock detection
    print("\n4. Limit-Lock Detection (Vietnam Market)")
    market_data = pd.DataFrame({
        'ticker': ['VNM', 'HPG', 'VCB'],
        'current_price': [69750, 28500, 95000],
        'reference_price': [75000, 30000, 100000],
        'bid_volume': [0, 1000, 5000],
        'ask_volume': [50000, 20000, 30000]
    })
    
    limit_lock_status = breaker.check_limit_lock(market_data)
    for ticker, status in limit_lock_status.items():
        print(f"   {ticker}: Locked={status.is_limit_locked}, "
              f"Type={status.lock_type}, "
              f"Change={status.price_change_pct:.2%}")
    
    # Test 5: Order execution check
    print("\n5. Order Execution Check")
    sell_order = {'ticker': 'VNM', 'side': 'sell', 'quantity': 1000}
    can_execute = breaker.can_execute_order(sell_order, market_data)
    print(f"   Can execute sell VNM: {can_execute}")
    if not can_execute:
        print(f"   Block reason: {breaker.get_block_reason('VNM')}")
    
    print("\n" + "=" * 80)
    print("Advanced Circuit Breaker demo complete")
    print("=" * 80)
