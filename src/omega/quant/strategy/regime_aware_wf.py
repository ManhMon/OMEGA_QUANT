"""
Regime-Aware Walk-Forward Integration - Phase 3.6
V21 Institutional Grade

Integrates layer_08/walk_forward_engine.py with layer_02/regime_detector_hmm.py
to enable market-regime-conditional model selection and validation.

Key Features:
- Market Regime Detection (HMM: Bull, Sideways, Bear)
- Conditional Model Selection (T+3 for Bull, T+5 for Bear)
- Dynamic Parameter Switching based on latent market states
- PIT-safe walk-forward validation with regime context
- Aggregated metrics per regime state

Version: v21.5-Phase3.6
Date: 2026-05-06
Author: OpenCode (L2-CODER)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import logging

from omega.quant.backtest.walk_forward_engine import (
    WalkForwardEngine as L8_WalkForwardEngine,
    WalkForwardConfig as L8_WalkForwardConfig,
    generate_t3_signals_pit,
    generate_t5_signals_pit,
)

from omega.quant.strategy.regime_detector import (
    RegimeDetectorHMM,
    HMMRegimeConfig,
)

logger = logging.getLogger(__name__)

# ─── CONFIG ────────────────────────────────────────────────────────────────────

@dataclass
class RegimeAwareConfig:
    """Configuration for Regime-Aware Walk-Forward Integration"""
    # Walk-Forward config
    train_window_days: int = 252
    validation_window_days: int = 63
    step_size_days: int = 21
    embargo_days: int = 3
    
    # HMM config
    n_regimes: int = 3
    hmm_features: List[str] = field(default_factory=lambda: ['returns', 'volatility', 'volume_change'])
    
    # Switching logic
    regime_model_map: Dict[str, str] = field(default_factory=lambda: {
        "Bull": "t3_model",
        "Sideways": "t3_model",
        "Bear": "t5_model"
    })
    
    # Dampening
    bear_dampening: float = 0.5
    sideways_dampening: float = 0.8


@dataclass
class RegimeFoldResult:
    """Result of a single fold with regime context"""
    fold_id: int
    val_start: pd.Timestamp
    val_end: pd.Timestamp
    
    # Regime info
    dominant_regime: str
    regime_confidence: float
    regime_stats: Dict[str, float]  # Occupancy of each regime in fold
    
    # Performance metrics
    selected_model: str
    selected_model_ic: float
    baseline_t3_ic: float
    baseline_t5_ic: float
    
    # Regime-aware score
    ensemble_ic: float
    improvement: float


# ─── INTEGRATION ENGINE ────────────────────────────────────────────────────────

class RegimeAwareWalkForward:
    """
    Integrates WalkForwardEngine with HMM Regime Detector.
    
    Workflow:
    1. Generate walk-forward splits.
    2. For each fold:
       a. Train HMM on historical market data (PIT-safe).
       b. Detect regime for the current validation window.
       c. Select optimal alpha model (T+3/T+5) based on regime.
       d. Apply regime-based dampening to signals.
       e. Evaluate performance and aggregate by regime.
    """
    
    def __init__(self, config: Optional[RegimeAwareConfig] = None):
        self.config = config or RegimeAwareConfig()
        
        # Initialize L8 Engine
        l8_config = L8_WalkForwardConfig(
            train_window_days=self.config.train_window_days,
            validation_window_days=self.config.validation_window_days,
            step_size_days=self.config.step_size_days,
            embargo_days=self.config.embargo_days
        )
        self.wf_engine = L8_WalkForwardEngine(l8_config)
        
        # Initialize L2 HMM Detector
        hmm_config = HMMRegimeConfig(
            n_components=self.config.n_regimes,
            features=self.config.hmm_features,
            bear_dampening=self.config.bear_dampening
        )
        self.hmm_detector = RegimeDetectorHMM(hmm_config)
    
    def _prepare_market_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Extract market-level features for HMM (Returns, Vol, Volume)."""
        # Handle both MultiIndex and simple DatetimeIndex
        if isinstance(data.index, pd.MultiIndex):
            # Group by date level
            mkt_rets = data.groupby(level='date')['return_1_pit'].mean()
            mkt_vol = mkt_rets.rolling(20).std()
            
            if 'volume' in data.columns:
                mkt_volm = data.groupby(level='date')['volume'].sum().pct_change()
            else:
                mkt_volm = mkt_rets.abs()
        else:
            # Simple DatetimeIndex - use index directly
            if 'return_1_pit' in data.columns:
                mkt_rets = data['return_1_pit']
            else:
                mkt_rets = data.iloc[:, 0]  # Use first column
            
            mkt_vol = mkt_rets.rolling(20).std()
            
            if 'volume' in data.columns:
                mkt_volm = data['volume'].pct_change()
            else:
                mkt_volm = mkt_rets.abs()
        
        features = pd.DataFrame({
            'returns': mkt_rets,
            'volatility': mkt_vol,
            'volume_change': mkt_volm
        }).dropna()
        
        return features

    def run(
        self,
        data: pd.DataFrame,
        features: pd.DataFrame,
        returns: pd.Series,
        price_data: Optional[pd.Series] = None
    ) -> List[RegimeFoldResult]:
        """Run regime-aware walk-forward validation."""
        splits = self.wf_engine.generate_splits(data)
        market_features = self._prepare_market_features(data)
        
        fold_results = []
        
        for fold_idx, split in enumerate(splits):
            vs, ve = split['val_start'], split['val_end']
            ts, te = split['train_start'], split['train_end']
            
            # 1. Train HMM on training window (PIT-safe)
            train_mkt = market_features[market_features.index < vs]
            if len(train_mkt) < 100:
                continue
                
            self.hmm_detector.fit(train_mkt, target_returns=train_mkt['returns'])
            
            # 2. Predict regimes for validation window
            val_mkt = market_features[(market_features.index >= vs) & (market_features.index <= ve)]
            if val_mkt.empty:
                continue
                
            regimes = []
            probs_list = []
            for date in val_mkt.index:
                lbl, probs = self.hmm_detector.predict_regime(val_mkt.loc[[date]])
                regimes.append(lbl)
                probs_list.append(probs)
            
            # 3. Aggregate regime stats for fold
            regime_series = pd.Series(regimes, index=val_mkt.index)
            occ = regime_series.value_counts(normalize=True).to_dict()
            dominant = regime_series.mode()[0]
            
            # 4. Generate Alpha Signals
            val_feats = self.wf_engine._slice_data(features, vs, ve)
            val_rets = self.wf_engine._slice_data(returns.to_frame(), vs, ve).iloc[:, 0]
            
            t3_signals = generate_t3_signals_pit(val_feats, price_data)
            t5_signals = generate_t5_signals_pit(val_feats, price_data)
            
            # 5. Selected model evaluation
            selected_model_name = self.config.regime_model_map.get(dominant, "t3_model")
            
            # Map signal to selected model
            if selected_model_name == "t3_model":
                selected_signals = t3_signals['t3_signal']
            else:
                selected_signals = t5_signals['t5_signal']
                
            # Align and compute IC
            common_idx = val_rets.index.intersection(selected_signals.index)
            if len(common_idx) < 20:
                continue
            
            # FIXED BUG 7: Add robust IC computation with NaN handling
            def compute_ic_safe(sig, ret):
                """Compute IC with NaN handling and variance checks."""
                sig_clean = sig.dropna()
                ret_clean = ret.dropna()
                common = sig_clean.index.intersection(ret_clean.index)
                
                if len(common) < 10:
                    return 0.0
                
                sig_vals = sig_clean.loc[common].values
                ret_vals = ret_clean.loc[common].values
                
                if np.std(sig_vals) < 1e-10 or np.std(ret_vals) < 1e-10:
                    return 0.0
                
                ic = np.corrcoef(sig_vals, ret_vals)[0, 1]
                return 0.0 if np.isnan(ic) else float(ic)
            
            # Baseline ICs
            t3_ic = compute_ic_safe(t3_signals['t3_signal'].loc[common_idx], val_rets.loc[common_idx])
            t5_ic = compute_ic_safe(t5_signals['t5_signal'].loc[common_idx], val_rets.loc[common_idx])
            
            # Selected IC
            sel_ic = compute_ic_safe(selected_signals.loc[common_idx], val_rets.loc[common_idx])
            
            # 6. Apply dampening (Regime-aware)
            # Bear dampening
            dampened_signals = selected_signals.copy()
            dampening_factor = 1.0
            if dominant == "Bear":
                dampening_factor = self.config.bear_dampening
                dampened_signals *= dampening_factor
            elif dominant == "Sideways":
                dampening_factor = self.config.sideways_dampening
                dampened_signals *= dampening_factor
                
            ensemble_ic = compute_ic_safe(dampened_signals.loc[common_idx], val_rets.loc[common_idx])
            
            # FIXED: Validate dampening correctness
            # Verify that dampening actually affected the signals
            if dampening_factor < 1.0:
                # Check that dampened signal magnitude is reduced
                original_mean_abs = selected_signals.loc[common_idx].abs().mean()
                dampened_mean_abs = dampened_signals.loc[common_idx].abs().mean()
                expected_ratio = dampening_factor
                actual_ratio = dampened_mean_abs / (original_mean_abs + 1e-10)
                
                # Validate dampening was applied correctly (within 1% tolerance)
                if abs(actual_ratio - expected_ratio) > 0.01:
                    self.logger.warning(
                        f"Fold {fold_idx}: Dampening validation failed. "
                        f"Expected ratio {expected_ratio:.4f}, got {actual_ratio:.4f}"
                    )
            
            fold_results.append(RegimeFoldResult(
                fold_id=fold_idx,
                val_start=vs,
                val_end=ve,
                dominant_regime=dominant,
                regime_confidence=np.mean([p.max() for p in probs_list]),
                regime_stats=occ,
                selected_model=selected_model_name,
                selected_model_ic=float(sel_ic),
                baseline_t3_ic=float(t3_ic),
                baseline_t5_ic=float(t5_ic),
                ensemble_ic=float(ensemble_ic),
                improvement=float(ensemble_ic - t3_ic)
            ))
            
        return fold_results
