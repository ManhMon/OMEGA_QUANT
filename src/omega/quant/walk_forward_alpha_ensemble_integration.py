"""
Walk-Forward Alpha Ensemble Integration - Phase 3.5
V21 Institutional Grade

Integrates layer_08/walk_forward_engine.py with layer_02/ensemble_builder.py
to enable ensemble-based alpha discovery with PIT-safe walk-forward validation.

Key Features:
- Bridge between Layer 08 (Self-Evolving) and Layer 02 (Strategy Logic)
- Ensemble-weighted alpha signals with walk-forward validation
- PIT-safe signal generation with T+3 embargo
- IC-based model gating and weight optimization
- Full audit trail of fold results and ensemble weights

Architecture:
  Layer 08 WalkForwardEngine (T+3/T+5 signals)
       ↓
  Integration Layer (this module)
       ↓
  Layer 02 OOFEnsembleBuilder (model gating + weights)
       ↓
  Ensemble-weighted ScoreVector

Version: v21.5-Phase3.5
Date: 2026-05-06
Author: OpenCode (L2-CODER)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import logging

from omega.quant.walk_forward_engine import (
    WalkForwardEngine as L8_WalkForwardEngine,
    WalkForwardConfig as L8_WalkForwardConfig,
    WalkForwardResult as L8_WalkForwardResult,
    FoldResult as L8_FoldResult,
    generate_t3_signals_pit,
    generate_t5_signals_pit,
)

from omega.quant.ensemble_builder import (
    OOFEnsembleBuilder,
    EnsembleConfig,
)

logger = logging.getLogger(__name__)

# ─── CONFIG ────────────────────────────────────────────────────────────────────

@dataclass
class IntegrationConfig:
    """Configuration for Walk-Forward Alpha Ensemble Integration"""
    # Layer 08 config
    train_window_days: int = 252
    validation_window_days: int = 63
    step_size_days: int = 21
    embargo_days: int = 3
    
    # Layer 02 ensemble config
    max_weight: float = 0.6
    min_weight: float = 0.0
    min_ic_threshold: float = 0.05
    max_correlation: float = 0.85
    use_smoothing: bool = True
    smoothness: float = 0.2
    
    # Integration config
    use_t3_signals: bool = True
    use_t5_signals: bool = True
    ensemble_mode: str = "weighted"  # "weighted" or "best_single"

@dataclass
class IntegratedFoldResult:
    """Result of a single integrated walk-forward fold"""
    fold_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    val_start: pd.Timestamp
    val_end: pd.Timestamp
    
    # Layer 08 metrics
    t3_ic: float = 0.0
    t5_ic: float = 0.0
    sharpe: float = 0.0
    n_samples: int = 0
    
    # Layer 02 ensemble metrics
    ensemble_weights: Dict[str, float] = field(default_factory=dict)
    rejected_models: List[str] = field(default_factory=list)
    ensemble_ic: float = 0.0
    ensemble_sharpe: float = 0.0
    
    # Integration metrics
    ic_improvement: float = 0.0  # ensemble_ic - baseline_ic
    status: str = "ok"

@dataclass
class IntegratedWalkForwardResult:
    """Aggregated integrated walk-forward result"""
    folds: List[IntegratedFoldResult] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    
    def summary(self) -> str:
        if not self.folds:
            return "No folds evaluated"
        
        avg_t3_ic = np.mean([f.t3_ic for f in self.folds])
        avg_t5_ic = np.mean([f.t5_ic for f in self.folds])
        avg_ensemble_ic = np.mean([f.ensemble_ic for f in self.folds])
        avg_improvement = np.mean([f.ic_improvement for f in self.folds])
        
        return (
            f"Integrated Walk-Forward Summary\n"
            f"  Folds: {len(self.folds)}\n"
            f"  Avg T+3 IC: {avg_t3_ic:.4f}\n"
            f"  Avg T+5 IC: {avg_t5_ic:.4f}\n"
            f"  Avg Ensemble IC: {avg_ensemble_ic:.4f}\n"
            f"  Avg IC Improvement: {avg_improvement:.4f}\n"
            f"  Overall IC: {self.metrics.get('overall_ic', 0):.4f}"
        )

# ─── INTEGRATION ENGINE ────────────────────────────────────────────────────────

class WalkForwardAlphaEnsembleIntegration:
    """
    Integration layer between Layer 08 WalkForwardEngine and Layer 02 OOFEnsembleBuilder.
    
    Workflow:
    1. Generate walk-forward splits (Layer 08)
    2. For each fold:
       a. Generate T+3 and T+5 signals (Layer 08)
       b. Treat signals as "model predictions" for ensemble
       c. Build ensemble weights using OOFEnsembleBuilder (Layer 02)
       d. Compute ensemble-weighted IC
       e. Track improvement over baseline
    3. Aggregate results across folds
    
    Usage:
        config = IntegrationConfig(train_window_days=252, min_ic_threshold=0.05)
        integration = WalkForwardAlphaEnsembleIntegration(config)
        result = integration.run(data, features, returns)
        print(result.summary())
    """
    
    def __init__(self, config: Optional[IntegrationConfig] = None):
        self.config = config or IntegrationConfig()
        self.logger = logging.getLogger(__name__)
        
        # Initialize Layer 08 engine
        l8_config = L8_WalkForwardConfig(
            train_window_days=self.config.train_window_days,
            validation_window_days=self.config.validation_window_days,
            step_size_days=self.config.step_size_days,
            embargo_days=self.config.embargo_days,
        )
        self.l8_engine = L8_WalkForwardEngine(l8_config)
        
        # Initialize Layer 02 ensemble builder
        l2_config = EnsembleConfig(
            max_weight=self.config.max_weight,
            min_weight=self.config.min_weight,
            min_ic_threshold=self.config.min_ic_threshold,
            max_correlation=self.config.max_correlation,
            use_smoothing=self.config.use_smoothing,
            smoothness=self.config.smoothness,
        )
        self.l2_builder = OOFEnsembleBuilder(l2_config)
    
    def _signals_to_oof_format(
        self,
        t3_signals: pd.DataFrame,
        t5_signals: pd.DataFrame,
        timestamps: List[int]
    ) -> Dict[str, Dict[int, Dict[str, float]]]:
        """
        Convert Layer 08 signal DataFrames to Layer 02 OOF format.
        
        Layer 08 signals: DataFrame with MultiIndex (date, ticker) and columns ['t3_signal', ...]
        Layer 02 OOF format: {model_name: {timestamp: {'score': float}}}
        
        Handles both MultiIndex and scalar index DataFrames.
        
        FIXED BUG 6: Detect timestamp unit (us vs ns) from index dtype and convert accordingly.
        """
        oof_data = {}
        
        # FIXED BUG 6: Detect the unit of timestamps from the index
        # Pandas may use datetime64[us] or datetime64[ns] depending on version
        if isinstance(t3_signals.index, pd.MultiIndex):
            date_dtype = t3_signals.index.levels[0].dtype
        else:
            date_dtype = t3_signals.index.dtype
        
        # Determine the unit: datetime64[us] = microseconds, datetime64[ns] = nanoseconds, int64 = seconds
        dtype_str = str(date_dtype).lower()
        if 'us' in dtype_str:
            ts_unit = 'us'
        elif 'ns' in dtype_str:
            ts_unit = 'ns'
        elif date_dtype == np.int64:
            # int64 Unix epoch seconds (e.g., 1609459200 = 2021-01-01)
            ts_unit = 's'
        else:
            ts_unit = 'ns'  # Default to nanoseconds
        
        # Build OOF data for T+3 signals
        if self.config.use_t3_signals and 't3_signal' in t3_signals.columns:
            oof_data['t3_model'] = {}
            for ts in timestamps:
                try:
                    if isinstance(t3_signals.index, pd.MultiIndex):
                        # FIXED BUG 6: For datetime64 MultiIndex, convert; for int64, use raw
                        if date_dtype == np.int64:
                            ts_key = ts
                        else:
                            ts_key = pd.Timestamp(ts, unit=ts_unit)
                        rows = t3_signals.loc[ts_key]
                        if isinstance(rows, pd.Series):
                            score = rows['t3_signal']
                            if pd.notna(score):
                                oof_data['t3_model'][ts] = {'score': float(score)}
                        else:
                            scores = rows['t3_signal'].dropna()
                            if len(scores) > 0:
                                oof_data['t3_model'][ts] = {'score': float(scores.mean())}
                    else:
                        # Scalar index: use raw timestamp for int64, convert for datetime64
                        if date_dtype == np.int64:
                            ts_key = ts
                        else:
                            ts_key = pd.Timestamp(ts, unit=ts_unit)
                        score = t3_signals.loc[ts_key, 't3_signal']
                        if pd.notna(score):
                            oof_data['t3_model'][ts] = {'score': float(score)}
                except KeyError:
                    pass
        
        # Build OOF data for T+5 signals
        if self.config.use_t5_signals and 't5_signal' in t5_signals.columns:
            oof_data['t5_model'] = {}
            for ts in timestamps:
                try:
                    if isinstance(t5_signals.index, pd.MultiIndex):
                        # FIXED BUG 6: For datetime64 MultiIndex, convert; for int64, use raw
                        if date_dtype == np.int64:
                            ts_key = ts
                        else:
                            ts_key = pd.Timestamp(ts, unit=ts_unit)
                        rows = t5_signals.loc[ts_key]
                        if isinstance(rows, pd.Series):
                            score = rows['t5_signal']
                            if pd.notna(score):
                                oof_data['t5_model'][ts] = {'score': float(score)}
                        else:
                            scores = rows['t5_signal'].dropna()
                            if len(scores) > 0:
                                oof_data['t5_model'][ts] = {'score': float(scores.mean())}
                    else:
                        # Scalar index: use raw timestamp for int64, convert for datetime64
                        if date_dtype == np.int64:
                            ts_key = ts
                        else:
                            ts_key = pd.Timestamp(ts, unit=ts_unit)
                        score = t5_signals.loc[ts_key, 't5_signal']
                        if pd.notna(score):
                            oof_data['t5_model'][ts] = {'score': float(score)}
                except KeyError:
                    pass
        
        return oof_data
    
    def _compute_fold_metrics(
        self,
        oof_data: Dict[str, Dict[int, Dict[str, float]]],
        returns: pd.Series,
        timestamps: List[int]
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute IC metrics for each model (T+3, T+5) on validation fold.
        
        FIXED BUG 6: Handle MultiIndex returns properly by converting timestamps to dates
        and aggregating returns by date level.
        """
        fold_metrics = {}
        
        # FIXED: If returns has MultiIndex, aggregate by date level first
        if isinstance(returns.index, pd.MultiIndex):
            # Aggregate returns by date (mean across tickers)
            returns_by_date = returns.groupby(level=0).mean()
            date_dtype = returns.index.levels[0].dtype
        else:
            returns_by_date = returns
            date_dtype = returns.index.dtype
        
        # FIXED BUG 6: Detect timestamp unit from dtype
        dtype_str = str(date_dtype).lower()
        if 'us' in dtype_str:
            ts_unit = 'us'
        elif 'ns' in dtype_str:
            ts_unit = 'ns'
        elif date_dtype == np.int64:
            # int64 Unix epoch seconds (e.g., 1609459200 = 2021-01-01)
            ts_unit = 's'
        else:
            ts_unit = 'ns'
        
        for model_name, model_data in oof_data.items():
            scores = []
            rets = []
            
            for ts in timestamps:
                if ts in model_data:
                    score = model_data[ts].get('score', 0.0)
                    
                    # FIXED BUG 6: For int64 index, use raw timestamp; for datetime64, convert
                    if date_dtype == np.int64:
                        ts_key = ts  # Use raw int64 timestamp
                    else:
                        ts_key = pd.Timestamp(ts, unit=ts_unit)  # Convert to datetime
                    
                    if ts_key in returns_by_date.index:
                        ret = returns_by_date.loc[ts_key]
                        if pd.notna(score) and pd.notna(ret):
                            scores.append(score)
                            rets.append(ret)
            
            if len(scores) >= 10:
                ic = np.corrcoef(scores, rets)[0, 1] if np.std(scores) > 1e-10 and np.std(rets) > 1e-10 else 0.0
                fold_metrics[model_name] = {'mean_ic': float(ic)}
            else:
                fold_metrics[model_name] = {'mean_ic': 0.0}
        
        return fold_metrics
    
    def _compute_ensemble_ic(
        self,
        ensemble_weights: Dict[str, float],
        oof_data: Dict[str, Dict[int, Dict[str, float]]],
        returns: pd.Series,
        timestamps: List[int]
    ) -> Tuple[float, float]:
        """
        Compute IC and Sharpe for ensemble-weighted signals.
        
        FIXED BUG 6: Handle MultiIndex returns properly by converting timestamps to dates
        and aggregating returns by date level.
        """
        ensemble_scores = []
        rets = []
        
        # FIXED: If returns has MultiIndex, aggregate by date level first
        if isinstance(returns.index, pd.MultiIndex):
            # Aggregate returns by date (mean across tickers)
            returns_by_date = returns.groupby(level=0).mean()
            date_dtype = returns.index.levels[0].dtype
        else:
            returns_by_date = returns
            date_dtype = returns.index.dtype
        
        # FIXED BUG 6: Detect timestamp unit from dtype
        dtype_str = str(date_dtype).lower()
        if 'us' in dtype_str:
            ts_unit = 'us'
        elif 'ns' in dtype_str:
            ts_unit = 'ns'
        elif date_dtype == np.int64:
            # int64 Unix epoch seconds (e.g., 1609459200 = 2021-01-01)
            ts_unit = 's'
        else:
            ts_unit = 'ns'
        
        for ts in timestamps:
            weighted_score = 0.0
            for model_name, weight in ensemble_weights.items():
                if model_name in oof_data and ts in oof_data[model_name]:
                    weighted_score += weight * oof_data[model_name][ts].get('score', 0.0)
            
            # FIXED BUG 6: For int64 index, use raw timestamp; for datetime64, convert
            if date_dtype == np.int64:
                ts_key = ts  # Use raw int64 timestamp
            else:
                ts_key = pd.Timestamp(ts, unit=ts_unit)  # Convert to datetime
            
            if ts_key in returns_by_date.index:
                ret = returns_by_date.loc[ts_key]
                if pd.notna(ret):
                    ensemble_scores.append(weighted_score)
                    rets.append(ret)
        
        if len(ensemble_scores) < 10:
            return 0.0, 0.0
        
        scores_arr = np.array(ensemble_scores)
        rets_arr = np.array(rets)
        
        if np.std(scores_arr) < 1e-10 or np.std(rets_arr) < 1e-10:
            return 0.0, 0.0
        
        ic = np.corrcoef(scores_arr, rets_arr)[0, 1]
        
        # Sharpe-like metric
        pnl = scores_arr * rets_arr
        sharpe = np.mean(pnl) / (np.std(pnl) + 1e-10) * np.sqrt(252 / 3)
        
        return float(ic), float(sharpe)
    
    def run(
        self,
        data: pd.DataFrame,
        features: pd.DataFrame,
        returns: pd.Series,
        price_data: Optional[pd.Series] = None
    ) -> IntegratedWalkForwardResult:
        """
        Run integrated walk-forward analysis with ensemble optimization.
        
        Args:
            data: Raw market data (for date index reference)
            features: Feature matrix (PIT-OK: pre-shifted)
            returns: Forward returns series (T+3 or T+5 labels)
            price_data: Optional price data for signal generation
        
        Returns:
            IntegratedWalkForwardResult with fold results and summary metrics
        """
        splits = self.l8_engine.generate_splits(data)
        fold_results: List[IntegratedFoldResult] = []
        
        for fold_idx, split in enumerate(splits):
            ts, te = split['train_start'], split['train_end']
            vs, ve = split['val_start'], split['val_end']
            
            # Slice validation data
            val_feats = self.l8_engine._slice_data(features, vs, ve)
            val_rets = self.l8_engine._slice_data(returns.to_frame(), vs, ve)[returns.name or 'return']
            
            # Generate PIT-safe signals (Layer 08)
            t3_signals = generate_t3_signals_pit(val_feats, price_data)
            t5_signals = generate_t5_signals_pit(val_feats, price_data)
            
            # Convert to timestamps (handle MultiIndex)
            if isinstance(val_feats.index, pd.MultiIndex):
                timestamps = sorted(val_feats.index.get_level_values(0).unique().astype(int).tolist())
            else:
                timestamps = sorted(val_feats.index.astype(int).tolist())
            
            # Convert signals to OOF format for ensemble builder
            oof_data = self._signals_to_oof_format(t3_signals, t5_signals, timestamps)
            
            if not oof_data:
                self.logger.warning(f"Fold {fold_idx}: No signals generated, skipping")
                continue
            
            # Compute fold metrics for model gating
            fold_metrics = self._compute_fold_metrics(oof_data, val_rets, timestamps)
            
            # Build ensemble weights (Layer 02)
            ensemble_weights = self.l2_builder.build_ensemble(
                oof_data,
                fold_metrics,
                fold_id=f"fold_{fold_idx}"
            )
            
            # Compute ensemble IC
            ensemble_ic, ensemble_sharpe = self._compute_ensemble_ic(
                ensemble_weights, oof_data, val_rets, timestamps
            )
            
            # Compute baseline IC (average of individual models)
            baseline_ic = np.mean([m['mean_ic'] for m in fold_metrics.values()])
            ic_improvement = ensemble_ic - baseline_ic
            
            # Extract individual model ICs
            t3_ic = fold_metrics.get('t3_model', {}).get('mean_ic', 0.0)
            t5_ic = fold_metrics.get('t5_model', {}).get('mean_ic', 0.0)
            
            fold_result = IntegratedFoldResult(
                fold_id=fold_idx,
                train_start=ts,
                train_end=te,
                val_start=vs,
                val_end=ve,
                t3_ic=t3_ic,
                t5_ic=t5_ic,
                sharpe=np.mean([t3_ic, t5_ic]),  # baseline sharpe proxy
                n_samples=len(val_feats),
                ensemble_weights=ensemble_weights,
                rejected_models=self.l2_builder.rejected_models,
                ensemble_ic=ensemble_ic,
                ensemble_sharpe=ensemble_sharpe,
                ic_improvement=ic_improvement,
                status="ok"
            )
            fold_results.append(fold_result)
        
        result = IntegratedWalkForwardResult(folds=fold_results)
        
        if fold_results:
            t3_ics = [f.t3_ic for f in fold_results]
            t5_ics = [f.t5_ic for f in fold_results]
            ensemble_ics = [f.ensemble_ic for f in fold_results]
            improvements = [f.ic_improvement for f in fold_results]
            
            result.metrics = {
                'avg_t3_ic': float(np.mean(t3_ics)),
                'avg_t5_ic': float(np.mean(t5_ics)),
                'avg_ensemble_ic': float(np.mean(ensemble_ics)),
                'avg_ic_improvement': float(np.mean(improvements)),
                'fold_count': len(fold_results),
                'overall_ic': float(np.mean(ensemble_ics)),
            }
        
        self.logger.info(f"Integrated walk-forward complete: {result.summary()}")
        return result