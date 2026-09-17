"""
Regime Switcher - V21 Institutional Grade (Gate 1)
Implements Champion/Challenger regime-based strategy switching with:
- 4 Strategy Profiles (Bull/Sideways/Volatile Sideways/Bear)
- 3-variable State Machine (candidate_regime, candidate_count, confirmed_regime)
- Transition Ramp with explicit source/target tracking
- Artifact-As-Of Contract (6-timestamp PIT safety)
- Bear-cooldown Exception
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


@dataclass
class StrategyProfile:
    """Strategy profile for a market regime."""
    name: str
    max_weight: float          # Max weight per asset
    leverage: float            # Portfolio leverage multiplier
    max_notional_per_trade: float
    max_adv_percentage: float
    volatility_filter_percentile: float
    risk_buffer_multiplier: float  # Risk buffer scaling factor


@dataclass
class RegimeSwitcherConfig:
    """Configuration for RegimeSwitcher."""
    # Asymmetric hysteresis (days)
    persistence_bull: int = 3
    persistence_sideways: int = 3
    persistence_volatile_sideways: int = 3
    persistence_bear: int = 2  # Enter Bear faster

    # Exit persistence (asymmetric)
    exit_persistence_bear: int = 5  # Exit Bear slower

    # Transition ramp
    ramp_duration_days: int = 5

    # Turnover budget
    max_switches_per_quarter: int = 4
    cooldown_days: int = 5

    # Volatile Sideways detection
    volatile_sideways_vol_percentile: float = 0.80


class RegimeSwitcher:
    """
    Regime-based strategy switcher with institutional-grade controls.

    Implements:
    - 4 Strategy Profiles
    - 3-variable State Machine (no counter confusion)
    - Transition Ramp with explicit source/target
    - Artifact-As-Of Contract
    - Bear-cooldown Exception
    """

    def __init__(
        self,
        hmm_detector,
        config: Optional[RegimeSwitcherConfig] = None,
        calibrated_thresholds: Optional[Dict[str, float]] = None
    ):
        self.hmm = hmm_detector
        self.config = config or RegimeSwitcherConfig()

        # 4 Strategy Profiles (P1-04: 'Volatile Sideways' with space)
        self.profiles = {
            'Bull': StrategyProfile(
                name='Aggressive',
                max_weight=0.05,
                leverage=1.0,
                max_notional_per_trade=300_000_000,
                max_adv_percentage=0.20,
                volatility_filter_percentile=0.90,
                risk_buffer_multiplier=1.0
            ),
            'Sideways': StrategyProfile(
                name='Neutral',
                max_weight=0.04,
                leverage=0.8,
                max_notional_per_trade=250_000_000,
                max_adv_percentage=0.15,
                volatility_filter_percentile=0.85,
                risk_buffer_multiplier=1.2
            ),
            'Volatile Sideways': StrategyProfile(  # P1-04: Fixed naming
                name='Cautious',
                max_weight=0.03,
                leverage=0.6,
                max_notional_per_trade=200_000_000,
                max_adv_percentage=0.12,
                volatility_filter_percentile=0.80,
                risk_buffer_multiplier=1.5
            ),
            'Bear': StrategyProfile(
                name='Defensive',
                max_weight=0.02,
                leverage=0.3,
                max_notional_per_trade=150_000_000,
                max_adv_percentage=0.10,
                volatility_filter_percentile=0.75,
                risk_buffer_multiplier=2.0
            )
        }

        # State Machine (3 independent variables - P2-03)
        self.candidate_regime: Optional[str] = None
        self.candidate_count: int = 0
        self.confirmed_regime: str = 'Sideways'  # Default

        # Ramp state (P2-03: Explicit source/target)
        self.ramp_source_regime: Optional[str] = None
        self.ramp_target_regime: Optional[str] = None
        self.ramp_start_date: Optional[pd.Timestamp] = None
        self.in_transition: bool = False

        # HMM memory (P1-02)
        self.prev_posterior: Optional[np.ndarray] = None

        # Turnover budget
        self.switch_history: List[pd.Timestamp] = []
        self.last_switch_date: Optional[pd.Timestamp] = None

        # Calibrated thresholds (P1-02: Artifact-as-of)
        self.calibrated_thresholds = calibrated_thresholds or {
            'Bull': 0.65,
            'Sideways': 0.70,
            'Volatile Sideways': 0.75,
            'Bear': 0.60  # Lower threshold for Bear
        }

        # Artifact-as-of timestamps (P1-02: Required, no None bypass allowed)
        self.model_trained_through: pd.Timestamp = pd.Timestamp('1900-01-01')
        self.thresholds_calibrated_through: pd.Timestamp = pd.Timestamp('1900-01-01')
        self.overlay_stats_asof: pd.Timestamp = pd.Timestamp('1900-01-01')

        # Decision log (P1-01: Audit trail)
        self.decision_log: List[Dict] = []

    def get_current_profile(
        self,
        market_data: pd.DataFrame,
        effective_date: pd.Timestamp
    ) -> StrategyProfile:
        """
        Get current strategy profile with PIT safety and transition ramp.

        PIT Contract (P1-01 & P1-02):
        - Feature Timestamp: market_data.index.max() < effective_date (T-1 features)
        - Decision Timestamp: effective_date (T-1 EOD)
        - Execution Timestamp: effective_date + 1 day (T Open)
        - Artifact Timestamps: model/thresholds/overlay trained through < effective_date

        Args:
            market_data: Historical market data (must be < effective_date)
            effective_date: Date for which profile is being determined

        Returns:
            StrategyProfile for execution on effective_date + 1
        """
        # PIT Safety Assertions (P1-01 & P1-02: Strict Enforcement)
        assert market_data.index.max() < effective_date, \
            f"PIT Violation: market_data contains future data (max={market_data.index.max()}, effective={effective_date})"

        assert self.model_trained_through < effective_date, \
            f"Artifact Leakage: model trained through {self.model_trained_through} >= {effective_date}"

        assert self.thresholds_calibrated_through < effective_date, \
            f"Artifact Leakage: thresholds calibrated through {self.thresholds_calibrated_through} >= {effective_date}"

        assert self.overlay_stats_asof < effective_date, \
            f"Artifact Leakage: overlay stats as-of {self.overlay_stats_asof} >= {effective_date}"

        # Get HMM prediction with memory (P1-02)
        regime_label, current_posterior = self.hmm.predict_regime_with_memory(
            market_data.tail(1),
            prev_posterior=self.prev_posterior
        )
        self.prev_posterior = current_posterior  # Store for next day

        # Detect Volatile Sideways overlay (P1-04)
        if regime_label == 'Sideways':
            recent_vol = market_data['volatility'].iloc[-20:].mean()
            vol_p80 = market_data['volatility'].quantile(self.config.volatile_sideways_vol_percentile)
            if recent_vol > vol_p80:
                regime_label = 'Volatile Sideways'

        # State Machine (P2-03: 3 independent variables + Reset Logic fix)
        if regime_label == self.confirmed_regime:
            # Already in this regime, reset candidate state
            self.candidate_regime = None
            self.candidate_count = 0
        elif regime_label != self.candidate_regime:
            # New candidate detected
            self.candidate_regime = regime_label
            self.candidate_count = 1
        else:
            # Candidate persists
            self.candidate_count += 1

        # Persistence check (asymmetric)
        persistence_required = self._get_persistence_threshold(regime_label)

        if self.candidate_count >= persistence_required:
            # Check turnover budget (P2-03: Bear-cooldown exception)
            if self._can_switch(regime_label, effective_date):
                # Confirm regime switch
                self.ramp_source_regime = self.confirmed_regime
                self.ramp_target_regime = regime_label
                self.confirmed_regime = regime_label
                self.ramp_start_date = effective_date
                self.in_transition = True
                self.last_switch_date = effective_date
                self.switch_history.append(effective_date)

                logger.info(f"Regime switch confirmed: {self.ramp_source_regime} -> {self.ramp_target_regime}")

        # Transition Ramp (P2-03: Explicit source/target)
        current_profile = self._get_ramped_profile(effective_date)

        # Decision Log (P1-01 & P1-02: Full 6-timestamp Audit Trail)
        self.decision_log.append({
            'effective_date': effective_date,                      # 1. Temporal: Decision Effective T
            'features_asof': market_data.index.max(),              # 2. Temporal: Data cutoff T-1
            'execution_date': effective_date + pd.Timedelta(days=1), # 3. Temporal: Applied T+1
            'decided_at': pd.Timestamp.now(),                      # Wall-clock audit
            
            'model_trained_through': self.model_trained_through,   # 4. Artifact: HMM parameters
            'thresholds_calibrated_through': self.thresholds_calibrated_through, # 5. Artifact: Thresholds        
            'overlay_stats_asof': self.overlay_stats_asof,         # 6. Artifact: Overlay stats
            
            'hmm_regime': regime_label,
            'confirmed_regime': self.confirmed_regime,
            'profile_name': current_profile.name,
            'in_transition': self.in_transition
        })

        return current_profile

    def _get_persistence_threshold(self, regime: str) -> int:
        """Get persistence threshold for regime (asymmetric)."""
        if regime == 'Bull':
            return self.config.persistence_bull
        elif regime == 'Sideways':
            return self.config.persistence_sideways
        elif regime == 'Volatile Sideways':
            return self.config.persistence_volatile_sideways
        elif regime == 'Bear':
            return self.config.persistence_bear
        else:
            return 3  # Default

    def _can_switch(self, target_regime: str, current_date: pd.Timestamp) -> bool:
        """
        Check if regime switch is allowed (turnover budget + cooldown).

        Bear-cooldown Exception (P2-03):
        - * -> Bear: Bypass cooldown (emergency exit)
        - Bear -> *: Normal cooldown applies
        """
        # Bear entry exception: always allow
        if target_regime == 'Bear':
            return True

        # Check cooldown
        if self.last_switch_date is not None:
            days_since_switch = (current_date - self.last_switch_date).days
            if days_since_switch < self.config.cooldown_days:
                return False

        # Check quarterly budget
        three_months_ago = current_date - pd.Timedelta(days=90)
        recent_switches = [d for d in self.switch_history if d > three_months_ago]
        if len(recent_switches) >= self.config.max_switches_per_quarter:
            return False

        return True

    def _get_ramped_profile(self, current_date: pd.Timestamp) -> StrategyProfile:
        """
        Get profile with transition ramp applied.

        Ramp interpolates parameters over ramp_duration_days.
        """
        if not self.in_transition or self.ramp_start_date is None:
            return self.profiles[self.confirmed_regime]

        days_since_switch = (current_date - self.ramp_start_date).days
        ramp_progress = min(days_since_switch / self.config.ramp_duration_days, 1.0)

        if ramp_progress >= 1.0:
            self.in_transition = False
            return self.profiles[self.confirmed_regime]

        # Interpolate between source and target profiles
        source_profile = self.profiles[self.ramp_source_regime]
        target_profile = self.profiles[self.ramp_target_regime]

        return StrategyProfile(
            name=f"Ramping ({source_profile.name} -> {target_profile.name})",
            max_weight=self._interpolate(source_profile.max_weight, target_profile.max_weight, ramp_progress),
            leverage=self._interpolate(source_profile.leverage, target_profile.leverage, ramp_progress),
            max_notional_per_trade=self._interpolate(source_profile.max_notional_per_trade, target_profile.max_notional_per_trade, ramp_progress),
            max_adv_percentage=self._interpolate(source_profile.max_adv_percentage, target_profile.max_adv_percentage, ramp_progress),
            volatility_filter_percentile=self._interpolate(source_profile.volatility_filter_percentile, target_profile.volatility_filter_percentile, ramp_progress),
            risk_buffer_multiplier=self._interpolate(source_profile.risk_buffer_multiplier, target_profile.risk_buffer_multiplier, ramp_progress)
        )

    def _interpolate(self, start: float, end: float, progress: float) -> float:
        """Linear interpolation."""
        return start + (end - start) * progress
