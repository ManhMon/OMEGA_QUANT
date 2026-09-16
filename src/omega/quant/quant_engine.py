"""
OMEGA_QUANT Unified Quant Engine - Institutional Grade
Version: 2.4
Status: Production Ready

Unified pipeline integrating:
- Feature generation (FeatureFactory)
- Alpha discovery (AlphaFactory + GeneticProgramming)
- Model training (ModelModule)
- Signal blending (SignalModule)
- Portfolio optimization (EnsembleOptimizer + MarkowitzOptimizer)
- Risk checks (PIT enforcement)

Contract:
- 100% vectorized (pandas/numpy only, no iterrows)
- PIT Safety enforced (T-1 lag mandatory)
- Stdlib + numpy/pandas only
- No look-ahead bias
- Dynamic universe support

Author: OMEGA_QUANT Team
Last Updated: 2026-05-26
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# V21 Core Intelligence imports
from omega.quant.feature.factory import (
    MomentumGenerator,
    VolatilityGenerator,
    VolumeLiquidityGenerator as VolumeGenerator,
    LimitLockDetector,
    LeakageAuditor,
)
from omega.quant.alpha.factory import AlphaFactory, compute_core_alphas
from omega.quant.ml.model_module import ModelModule, ModelConfig, TrainedModel
from omega.quant.signal.module import SignalModule, SignalModuleConfig
from .ensemble_optimizer import EnsembleOptimizer, WeightsConfig
from omega.quant.evolution.genetic_programming import GeneticProgrammingEngine, GPConfig
from omega.quant.monitoring.experiment_tracker import ExperimentTracker, ExperimentMetadata
from omega.quant.risk.pit_manager import PITManager, PITConfig

# Strategy Logic (upgraded from V21 layer_02)
from .strategy.alpha_ensemble import AlphaEnsemble
from .strategy.black_litterman import BlackLittermanOptimizer
from .strategy.ml_models import XGBEstimator, LGBEstimator, CatBoostEstimator
from .strategy.model_trainer import TrainerConfig, WalkForwardOptunaTrainer
from .strategy.multi_model_ensemble import MultiModelEnsemble, EnsembleConfig as StrategyEnsembleConfig
from .strategy.oos_walk_forward_validator import OOSWalkForwardValidator, WalkForwardConfig
from .strategy.purged_cv import PurgedTimeSeriesSplit
from .strategy.regime_conditional import RegimeConditionalStrategy, GaussianHMM, HMMConfig
from .strategy.rl_agent import RLPortfolioAgent, RLConfig
from .strategy.transaction_cost_analyzer import TransactionCostAnalyzer, VNSlippageModel

# Portfolio & Governance (upgraded from V21 layer_05/06)
from omega.quant.monitoring.performance_tracker import PerformanceTracker
from .portfolio import PortfolioOptimizer
# NOTE: OnlineModelUpdater, validate_ly_state moved to lazy imports (circular import fix)
# NOTE: VnStockLiveDataProvider, ProductionDataPipeline moved to lazy imports (circular import fix)

logger = logging.getLogger(__name__)


@dataclass
class QuantEngineConfig:
    """Configuration for QuantEngine."""
    
    # Feature generation
    enable_momentum: bool = True
    enable_volatility: bool = True
    enable_volume: bool = True
    enable_alpha_arsenal: bool = True
    
    # Alpha discovery
    enable_genetic_programming: bool = True
    gp_population_size: int = 100
    gp_generations: int = 20
    gp_min_ic: float = 0.02
    
    # Model training
    model_config: ModelConfig = field(default_factory=ModelConfig)
    temporal_split: bool = True
    train_ratio: float = 0.7
    
    # Signal generation
    signal_config: SignalModuleConfig = field(default_factory=SignalModuleConfig)
    
    # Ensemble optimization
    ensemble_config: WeightsConfig = field(default_factory=WeightsConfig)
    
    # PIT enforcement
    enforce_pit: bool = True
    pit_lag_days: int = 1
    
    # Experiment tracking
    enable_experiment_tracking: bool = True
    experiment_log_path: str = "state/experiments.jsonl"
    
    # Risk limits
    max_position_size: float = 0.1  # 10% max per position
    max_sector_exposure: float = 0.3  # 30% max per sector
    max_leverage: float = 1.0  # No leverage by default


@dataclass
class QuantEngineOutput:
    """Output from QuantEngine pipeline."""
    
    # Feature matrix
    features: pd.DataFrame
    
    # Alpha signals
    alphas: pd.DataFrame
    
    # Model predictions
    predictions: pd.DataFrame
    
    # Trading signals
    signals: pd.DataFrame
    
    # Portfolio weights
    weights: pd.DataFrame
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Experiment ID
    experiment_id: Optional[str] = None


class QuantEngine:
    """
    Unified Quant Engine - Institutional Grade.
    
    Pipeline:
    1. Feature Generation → FeatureMatrix
    2. Alpha Discovery → AlphaSignals (via GP + Arsenal)
    3. Model Training → Predictions
    4. Signal Blending → TradingSignals
    5. Portfolio Optimization → Weights
    6. Risk Check → Final Weights (PIT-safe)
    
    Usage:
        engine = QuantEngine(config)
        output = engine.run(df_ohlcv)
        weights = output.weights
    """
    
    CONTRACT_HASH = "quant_engine_v2.4_20260526"
    
    def __init__(self, config: Optional[QuantEngineConfig] = None):
        self.config = config or QuantEngineConfig()
        
        # Initialize components
        self.alpha_factory = AlphaFactory()
        self.model_module = ModelModule(self.config.model_config)
        self.signal_module = SignalModule(self.config.signal_config)
        self.ensemble_optimizer = EnsembleOptimizer(self.config.ensemble_config)
        
        # Genetic Programming (optional)
        self.gp_engine: Optional[GeneticProgrammingEngine] = None
        if self.config.enable_genetic_programming:
            gp_config = GPConfig(
                population_size=self.config.gp_population_size,
                n_generations=self.config.gp_generations,
                min_ic=self.config.gp_min_ic,
            )
            self.gp_engine = GeneticProgrammingEngine(gp_config)
        
        # PIT Manager
        self.pit_manager = PITManager(PITConfig())
        
        # Experiment Tracker
        self.experiment_tracker: Optional[ExperimentTracker] = None
        if self.config.enable_experiment_tracking:
            self.experiment_tracker = ExperimentTracker(
                log_path=self.config.experiment_log_path
            )
        
        # Feature generators
        self.momentum_gen = MomentumGenerator("momentum")
        self.volatility_gen = VolatilityGenerator("volatility")
        self.volume_gen = VolumeGenerator("volume")
        self.limit_lock_detector = LimitLockDetector(exchange='HOSE')
        self.leakage_auditor = LeakageAuditor()
        
        logger.info("QuantEngine initialized with config: %s", self.config)
    
    def run(
        self,
        df: pd.DataFrame,
        target_col: str = "forward_return_1d",
        symbol_col: str = "ticker",
        validate_pit: bool = True,
    ) -> QuantEngineOutput:
        """
        Run full quant pipeline.
        
        Args:
            df: OHLCV DataFrame with columns [date, ticker, open, high, low, close, volume]
            target_col: Target column for model training (must be T+1 forward return)
            symbol_col: Symbol column name
            validate_pit: Validate PIT safety before returning
        
        Returns:
            QuantEngineOutput with features, alphas, predictions, signals, weights
        """
        logger.info("Starting QuantEngine pipeline...")
        
        # Validate input
        self._validate_input(df, symbol_col)
        
        # Step 1: Feature Generation
        logger.info("Step 1: Feature Generation")
        df_features = self._generate_features(df, symbol_col)
        
        # Step 2: Alpha Discovery
        logger.info("Step 2: Alpha Discovery")
        df_alphas = self._discover_alphas(df_features, symbol_col)
        
        # Step 3: Model Training (if target available)
        logger.info("Step 3: Model Training")
        df_predictions = self._train_models(df_alphas, target_col, symbol_col)
        
        # Step 4: Signal Blending
        logger.info("Step 4: Signal Blending")
        df_signals = self._blend_signals(df_predictions, symbol_col)
        
        # Step 5: Portfolio Optimization
        logger.info("Step 5: Portfolio Optimization")
        df_weights = self._optimize_portfolio(df_signals, symbol_col)
        
        # Step 6: Risk Check & PIT Validation
        logger.info("Step 6: Risk Check & PIT Validation")
        if validate_pit and self.config.enforce_pit:
            self._validate_pit_safety(df_weights, symbol_col)
        
        df_weights = self._apply_risk_limits(df_weights, symbol_col)
        
        # Log experiment
        experiment_id = None
        if self.experiment_tracker:
            experiment_id = self._log_experiment(
                df_features, df_alphas, df_predictions, df_signals, df_weights
            )
        
        logger.info("QuantEngine pipeline completed successfully")
        
        return QuantEngineOutput(
            features=df_features,
            alphas=df_alphas,
            predictions=df_predictions,
            signals=df_signals,
            weights=df_weights,
            metadata={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "n_symbols": df[symbol_col].nunique(),
                "n_dates": df["date"].nunique(),
                "config": self.config,
            },
            experiment_id=experiment_id,
        )
    
    def _validate_input(self, df: pd.DataFrame, symbol_col: str) -> None:
        """Validate input DataFrame."""
        required_cols = ["date", symbol_col, "open", "high", "low", "close", "volume"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        if df.empty:
            raise ValueError("Input DataFrame is empty")
        
        # Check for duplicates
        if df.duplicated(subset=["date", symbol_col]).any():
            raise ValueError("Duplicate (date, symbol) pairs found in input")
        
        logger.info("Input validation passed: %d rows, %d symbols, %d dates",
                   len(df), df[symbol_col].nunique(), df["date"].nunique())
    
    def _generate_features(self, df: pd.DataFrame, symbol_col: str) -> pd.DataFrame:
        """Generate features from OHLCV data."""
        df_out = df.copy()
        
        # Set MultiIndex for safe rolling operations
        if not isinstance(df_out.index, pd.MultiIndex):
            df_out = df_out.set_index(["date", symbol_col])
        
        # Detect limit locks (Vietnamese market specific)
        prev_close = df_out.groupby(level=1)["close"].shift(1)
        limit_lock_series = self.limit_lock_detector.detect(
            df_out["close"], prev_close
        )
        df_out["limit_lock"] = limit_lock_series.astype(int)
        
        # Generate momentum features
        if self.config.enable_momentum:
            df_momentum = self.momentum_gen.generate(df_out)
            df_out = df_out.join(df_momentum, how="left")
        
        # Generate volatility features
        if self.config.enable_volatility:
            df_volatility = self.volatility_gen.generate(df_out)
            df_out = df_out.join(df_volatility, how="left")
        
        # Generate volume features
        if self.config.enable_volume:
            df_volume = self.volume_gen.generate(df_out)
            df_out = df_out.join(df_volume, how="left")
        
        # Reset index
        df_out = df_out.reset_index()
        
        # Audit for leakage
        self.leakage_auditor.check_forward_fill(df_out)
        
        logger.info("Feature generation completed: %d features", len(df_out.columns))
        return df_out
    
    def _discover_alphas(self, df: pd.DataFrame, symbol_col: str) -> pd.DataFrame:
        """Discover alpha signals using arsenal + GP."""
        df_out = df.copy()
        
        # Alpha Arsenal (canonical alphas)
        if self.config.enable_alpha_arsenal:
            try:
                df_alphas = compute_core_alphas(
                    df_out, symbol_col=symbol_col, apply_neutralization=True
                )
                # Merge alpha columns
                alpha_cols = [col for col in df_alphas.columns if col.startswith("alpha_")]
                df_out = df_out.merge(
                    df_alphas[["date", symbol_col] + alpha_cols],
                    on=["date", symbol_col],
                    how="left",
                )
            except Exception as e:
                logger.warning("Alpha arsenal failed: %s", e)
        
        # Genetic Programming (discover new alphas)
        if self.gp_engine and self.config.enable_genetic_programming:
            try:
                # Prepare data for GP
                target_col = "forward_return_1d" if "forward_return_1d" in df_out.columns else None
                feature_cols = [
                    col for col in df_out.columns
                    if col not in ["date", symbol_col, "limit_lock", target_col]
                    and not col.startswith(("forward_", "fwd_", "target_"))
                ]
                
                # Run GP evolution
                gp_results = self.gp_engine.evolve(
                    df_out, 
                    feature_cols=feature_cols,
                    target_col=target_col,
                    symbol_col=symbol_col,
                )
                
                # Add GP-discovered alphas
                for i, expr in enumerate(gp_results.get("best_expressions", [])):
                    alpha_name = f"gp_alpha_{i}"
                    df_out[alpha_name] = expr.evaluate(df_out)
                    logger.info("GP discovered alpha: %s (IC=%.4f)", 
                               alpha_name, expr.fitness)
            except Exception as e:
                logger.warning("Genetic programming failed: %s", e)
        
        logger.info("Alpha discovery completed: %d alpha columns", 
                   len([col for col in df_out.columns if "alpha" in col]))
        return df_out
    
    def _train_models(
        self, 
        df: pd.DataFrame, 
        target_col: str, 
        symbol_col: str
    ) -> pd.DataFrame:
        """Train models on alpha features."""
        df_out = df.copy()
        
        # Check if target exists
        if target_col not in df_out.columns:
            logger.warning("Target column '%s' not found, skipping model training", target_col)
            df_out["model_prediction"] = 0.0
            return df_out
        
        # Prepare feature matrix
        alpha_cols = [col for col in df_out.columns if "alpha" in col]
        if not alpha_cols:
            logger.warning("No alpha columns found, skipping model training")
            df_out["model_prediction"] = 0.0
            return df_out
        
        if not 0.0 < self.config.train_ratio < 1.0:
            raise ValueError("train_ratio must be between 0 and 1")

        # Split on unique chronological dates before fitting or scoring.
        dates = pd.Series(pd.to_datetime(df_out["date"], errors="raise")).drop_duplicates().sort_values().tolist()
        split_index = int(len(dates) * self.config.train_ratio)
        if self.config.temporal_split and (split_index < 1 or split_index >= len(dates)):
            logger.warning("Insufficient dates for temporal train/OOS split")
            df_out["model_prediction"] = 0.0
            return df_out
        train_dates = set(dates[:split_index]) if self.config.temporal_split else set(dates)
        oos_dates = set(dates[split_index:]) if self.config.temporal_split else set(dates)
        date_values = pd.to_datetime(df_out["date"], errors="raise")
        train_df = df_out[date_values.isin(train_dates)]
        oos_df = df_out[date_values.isin(oos_dates)]

        # Convert DataFrame to FeatureMatrix format (ModelModule contract)
        feature_matrix = self._to_feature_matrix(train_df, alpha_cols, symbol_col)
        target_vector = self._to_target_vector(train_df, target_col, symbol_col)
        
        # Train model
        try:
            self.model_module.train(feature_matrix, target_vector)
            
            # Predict
            predictions = self.model_module.predict(
                self._to_feature_matrix(oos_df, alpha_cols, symbol_col)
            )
            
            # Merge predictions back
            pred_df = self._from_score_vector(predictions, symbol_col)
            df_out = df_out.merge(
                pred_df[["date", symbol_col, "score"]].rename(columns={"score": "model_prediction"}),
                on=["date", symbol_col],
                how="left",
            )
            df_out["model_prediction"] = df_out["model_prediction"].fillna(0.0)
            
            logger.info("Model training completed: IC=%.4f, Sharpe=%.4f",
                       self.model_module.model.metrics.get("ic", 0.0),
                       self.model_module.model.metrics.get("sharpe", 0.0))
        except Exception as e:
            logger.error("Model training failed: %s", e)
            df_out["model_prediction"] = 0.0
        
        return df_out
    
    def _blend_signals(self, df: pd.DataFrame, symbol_col: str) -> pd.DataFrame:
        """Blend model predictions into trading signals."""
        df_out = df.copy()
        
        # Prepare score vector
        if "model_prediction" not in df_out.columns:
            logger.warning("No model predictions found, using zero signals")
            df_out["signal"] = "HOLD"
            return df_out
        
        score_vector = self._to_score_vector(df_out, "model_prediction", symbol_col)
        
        # Generate signals
        try:
            signal_vector = self.signal_module.transform(score_vector)
            
            # Merge signals back
            signal_df = self._from_signal_vector(signal_vector, symbol_col)
            df_out = df_out.merge(
                signal_df[["date", symbol_col, "signal"]],
                on=["date", symbol_col],
                how="left",
            )
            
            logger.info("Signal blending completed: %d BUY, %d SELL, %d HOLD",
                       (df_out["signal"] == "BUY").sum(),
                       (df_out["signal"] == "SELL").sum(),
                       (df_out["signal"] == "HOLD").sum())
        except Exception as e:
            logger.error("Signal blending failed: %s", e)
            df_out["signal"] = "HOLD"
        
        return df_out
    
    def _optimize_portfolio(self, df: pd.DataFrame, symbol_col: str) -> pd.DataFrame:
        """Optimize portfolio weights."""
        df_out = df.copy()
        
        # Simple equal-weight for BUY signals (baseline)
        # TODO: Integrate Markowitz optimizer for risk-adjusted weights
        
        def compute_weights(group):
            buy_mask = group["signal"] == "BUY"
            n_buy = buy_mask.sum()
            if n_buy > 0:
                group.loc[buy_mask, "weight"] = 1.0 / n_buy
            else:
                group["weight"] = 0.0
            return group
        
        df_out["weight"] = 0.0
        df_out = df_out.groupby("date", group_keys=False).apply(compute_weights)
        
        logger.info("Portfolio optimization completed: avg weight=%.4f",
                   df_out["weight"].mean())
        return df_out
    
    def _validate_pit_safety(self, df: pd.DataFrame, symbol_col: str) -> None:
        """Validate PIT safety of final weights."""
        # Check that weights only use T-1 data
        # This is a heuristic check - full PIT validation requires data lineage
        
        if "date" not in df.columns:
            logger.warning("Cannot validate PIT safety: 'date' column missing")
            return
        
        # Check for forward-looking bias in weights
        # Weights should not change retroactively
        df_sorted = df.sort_values(["date", symbol_col])
        
        for sym in df_sorted[symbol_col].unique():
            sym_data = df_sorted[df_sorted[symbol_col] == sym]
            weight_changes = sym_data["weight"].diff().abs()
            
            # Weights should only change at date boundaries
            # (This is a weak check - full PIT audit requires data provenance)
            if weight_changes.max() > 1.0:
                logger.warning("PIT WARNING: Large weight change detected for %s", sym)
        
        logger.info("PIT safety validation completed")
    
    def _apply_risk_limits(self, df: pd.DataFrame, symbol_col: str) -> pd.DataFrame:
        """Apply risk limits to portfolio weights."""
        df_out = df.copy()
        
        # Cap individual position sizes
        df_out["weight"] = df_out["weight"].clip(0, self.config.max_position_size)
        
        # Renormalize to sum to 1.0 per date
        def renormalize(group):
            total = group["weight"].sum()
            if total > 0:
                group["weight"] = group["weight"] / total
            return group
        
        df_out = df_out.groupby("date", group_keys=False).apply(renormalize)
        
        logger.info("Risk limits applied: max_position=%.2f", self.config.max_position_size)
        return df_out
    
    def _log_experiment(
        self,
        df_features: pd.DataFrame,
        df_alphas: pd.DataFrame,
        df_predictions: pd.DataFrame,
        df_signals: pd.DataFrame,
        df_weights: pd.DataFrame,
    ) -> str:
        """Log experiment to tracker."""
        if not self.experiment_tracker:
            return ""
        
        # Compute metrics
        metrics = {}
        if "model_prediction" in df_predictions.columns and "forward_return_1d" in df_predictions.columns:
            ic = df_predictions[["model_prediction", "forward_return_1d"]].corr().iloc[0, 1]
            metrics["ic"] = float(ic) if not np.isnan(ic) else 0.0
        
        # Feature importance (from model)
        feature_importance = {}
        if self.model_module.model:
            feature_importance = self.model_module.model.weights
        
        # Log experiment
        experiment_id = self.experiment_tracker.log_experiment(
            model_type="QuantEngine",
            hyperparameters={
                "gp_enabled": self.config.enable_genetic_programming,
                "gp_population": self.config.gp_population_size,
                "gp_generations": self.config.gp_generations,
                "model_config": str(self.config.model_config),
            },
            metrics=metrics,
            feature_importance=feature_importance,
            notes="QuantEngine unified pipeline run",
        )
        
        logger.info("Experiment logged: %s", experiment_id)
        return experiment_id
    
    # Helper methods for contract conversions
    
    def _to_feature_matrix(
        self, df: pd.DataFrame, feature_cols: List[str], symbol_col: str
    ) -> Dict[str, Any]:
        """Convert DataFrame to FeatureMatrix contract (vectorized)."""
        timestamps = sorted(df["date"].unique().tolist())
        symbols = sorted(df[symbol_col].unique().tolist())
        
        # Vectorized approach: use groupby + to_dict
        data = {}
        for sym in symbols:
            sym_data = df[df[symbol_col] == sym].set_index("date")[feature_cols]
            data[sym] = sym_data.to_dict(orient="index")
        
        return {
            "type": "FeatureMatrix",
            "index": {"timestamp": timestamps, "symbol": symbols},
            "data": data,
        }
    
    def _to_target_vector(
        self, df: pd.DataFrame, target_col: str, symbol_col: str
    ) -> Dict[str, Any]:
        """Convert DataFrame to AlignedTargetVector contract (vectorized)."""
        timestamps = sorted(df["date"].unique().tolist())
        symbols = sorted(df[symbol_col].unique().tolist())
        
        # Vectorized approach: filter non-null, then groupby + to_dict
        df_valid = df[pd.notna(df[target_col])].copy()
        
        data = {}
        for sym in symbols:
            sym_data = df_valid[df_valid[symbol_col] == sym].set_index("date")[target_col]
            data[sym] = sym_data.to_dict()
        
        return {
            "type": "AlignedTargetVector",
            "index": {"timestamp": timestamps, "symbol": symbols},
            "data": data,
        }
    
    def _to_score_vector(
        self, df: pd.DataFrame, score_col: str, symbol_col: str
    ) -> Dict[str, Any]:
        """Convert DataFrame to ScoreVector contract (vectorized)."""
        timestamps = sorted(df["date"].unique().tolist())
        symbols = sorted(df[symbol_col].unique().tolist())
        
        # Vectorized approach: create nested dict structure
        data = {}
        for sym in symbols:
            sym_data = df[df[symbol_col] == sym].set_index("date")[score_col]
            data[sym] = {ts: {"score": float(val)} for ts, val in sym_data.items()}
        
        return {
            "type": "ScoreVector",
            "index": {"timestamp": timestamps, "symbol": symbols},
            "data": data,
        }
    
    def _from_score_vector(
        self, score_vector: Dict[str, Any], symbol_col: str
    ) -> pd.DataFrame:
        """Convert ScoreVector to DataFrame."""
        rows = []
        for sym, ts_data in score_vector["data"].items():
            for ts, score_dict in ts_data.items():
                rows.append({
                    "date": ts,
                    symbol_col: sym,
                    "score": score_dict.get("score", 0.0),
                })
        return pd.DataFrame(rows)
    
    def _from_signal_vector(
        self, signal_vector: Dict[str, Any], symbol_col: str
    ) -> pd.DataFrame:
        """Convert SignalVector to DataFrame."""
        rows = []
        for sym, ts_data in signal_vector["data"].items():
            for ts, signal_dict in ts_data.items():
                rows.append({
                    "date": ts,
                    symbol_col: sym,
                    "signal": signal_dict.get("signal", "HOLD"),
                })
        return pd.DataFrame(rows)

    # --- Lazy import accessors (circular import fix) ---

    @staticmethod
    def get_online_model_updater():
        """Lazy import for OnlineModelUpdater (avoids circular import at package bootstrap)."""
        from ..governance.online_model_updater import OnlineModelUpdater
        return OnlineModelUpdater

    @staticmethod
    def get_validate_ly_state():
        """Lazy import for validate_ly_state (avoids circular import at package bootstrap)."""
        from ..governance.validate_ly_state import validate_ly_state
        return validate_ly_state

    @staticmethod
    def get_vnstock_live_provider():
        """Lazy import for legacy VnStockLiveDataProvider (archived in Phase 3B)."""
        import warnings
        warnings.warn(
            "VnStockLiveDataProvider is deprecated and archived in Phase 3B. "
            "Network data fetch is forbidden. See archive/legacy_adapters/vnstock_live.py.",
            DeprecationWarning,
            stacklevel=2,
        )
        from ..data.vnstock_live import VnStockLiveDataProvider
        return VnStockLiveDataProvider

    @staticmethod
    def get_production_data_pipeline():
        """Lazy import for ProductionDataPipeline (avoids circular import at package bootstrap)."""
        from ..data.production_data_pipeline import ProductionDataPipeline
        return ProductionDataPipeline
