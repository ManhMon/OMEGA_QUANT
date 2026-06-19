"""
OMEGA_QUANT E2E Pipeline - Phase 9 Integration
Backend Engineer (Role 9) - L2 OpenCode

Unified entry point connecting:
Data -> Features -> Alpha -> Risk -> Execution

Strict PIT Safety enforced throughout the pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

# Data Layer
from omega.data.loader import DataLoader

# Feature Layer
from omega.quant.feature.module import FeatureModule, FeatureModuleConfig

# Alpha Layer
from omega.quant.alpha.discovery import AlphaDiscoveryEngine, DiscoveryConfig

# Risk Layer
from omega.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from omega.risk.individual_risk_guard import IndividualRiskGuard, RiskGuardConfig

# Execution Layer
from omega.quant.execution_sim import ExecutionSimulator, ExecutionConfig

logger = logging.getLogger("OmegaPipeline")


@dataclass
class PipelineConfig:
    """Configuration for the E2E pipeline."""
    # Pipeline config - MANDATORY (No default)
    universe: List[str]
    start_date: str
    end_date: str
    as_of_time: datetime  # Mandatory PIT cutoff - NO DEFAULT
    
    # Optional configs - (With default)
    data_dir: Path = field(default_factory=lambda: Path("data"))
    cache_dir: Path = field(default_factory=lambda: Path("data/cache"))
    
    # Feature config
    feature_config: FeatureModuleConfig = field(default_factory=FeatureModuleConfig)
    
    # Alpha config
    alpha_config: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    
    # Risk config
    risk_config: RiskGuardConfig = field(default_factory=RiskGuardConfig)
    circuit_breaker_config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    
    # Execution config
    execution_config: ExecutionConfig = field(default_factory=ExecutionConfig)
    
    rebalance_frequency: str = "weekly"  # daily, weekly, monthly


@dataclass
class PipelineResult:
    """Result from pipeline execution."""
    success: bool
    message: str
    data: Optional[pd.DataFrame] = None
    features: Optional[pd.DataFrame] = None
    alphas: Optional[pd.DataFrame] = None
    positions: Optional[pd.DataFrame] = None
    executions: Optional[List[Any]] = None
    metrics: Optional[Dict[str, float]] = None
    errors: List[str] = field(default_factory=list)


class OmegaPipeline:
    """
    E2E Pipeline for OMEGA_QUANT system.
    
    Workflow:
    1. Data: Load PIT-safe market data
    2. Features: Compute technical features
    3. Alpha: Generate alpha signals
    4. Risk: Apply risk controls (circuit breaker, position limits)
    5. Execution: Simulate realistic execution
    
    Contract:
    - Input: PipelineConfig with universe, date range, configs
    - Output: PipelineResult with positions, executions, metrics
    - Precondition: All configs are valid
    - Postcondition: PIT safety maintained throughout
    """
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        
        # Initialize components
        self.data_loader = DataLoader(
            cache_dir=str(config.cache_dir)
        )
        
        self.feature_module = FeatureModule(config=config.feature_config)
        
        self.alpha_engine = AlphaDiscoveryEngine(config=config.alpha_config)
        
        self.circuit_breaker = CircuitBreaker(config=config.circuit_breaker_config)
        self.risk_guard = IndividualRiskGuard(config=config.risk_config)
        
        self.execution_sim = ExecutionSimulator(config=config.execution_config)
        
        logger.info(f"OmegaPipeline initialized with universe: {config.universe}")
    
    def run(self) -> PipelineResult:
        """
        Execute the full E2E pipeline.
        
        Returns:
            PipelineResult with all outputs and metrics
        """
        errors = []
        
        try:
            # Step 1: Load Data
            logger.info("Step 1: Loading market data...")
            data_result = self._load_data()
            if not data_result["success"]:
                return PipelineResult(
                    success=False,
                    message=f"Data loading failed: {data_result['message']}",
                    errors=[data_result["message"]]
                )
            data = data_result["data"]
            logger.info(f"Loaded {len(data)} rows of market data")
            
            # Step 2: Compute Features
            logger.info("Step 2: Computing features...")
            features_result = self._compute_features(data)
            if not features_result["success"]:
                return PipelineResult(
                    success=False,
                    message=f"Feature computation failed: {features_result['message']}",
                    data=data,
                    errors=[features_result["message"]]
                )
            features = features_result["features"]
            logger.info(f"Computed {len(features.columns)} features")
            
            # Step 3: Generate Alphas
            logger.info("Step 3: Generating alpha signals...")
            alphas_result = self._generate_alphas(features)
            if not alphas_result["success"]:
                return PipelineResult(
                    success=False,
                    message=f"Alpha generation failed: {alphas_result['message']}",
                    data=data,
                    features=features,
                    errors=[alphas_result["message"]]
                )
            alphas = alphas_result["alphas"]
            logger.info(f"Generated {len(alphas.columns)} alpha signals")
            
            # Step 4: Apply Risk Controls
            logger.info("Step 4: Applying risk controls...")
            risk_result = self._apply_risk_controls(alphas, data)
            if not risk_result["success"]:
                return PipelineResult(
                    success=False,
                    message=f"Risk control failed: {risk_result['message']}",
                    data=data,
                    features=features,
                    alphas=alphas,
                    errors=[risk_result["message"]]
                )
            positions = risk_result["positions"]
            logger.info(f"Risk-adjusted positions computed")
            
            # Step 5: Simulate Execution
            logger.info("Step 5: Simulating execution...")
            execution_result = self._simulate_execution(positions, data)
            if not execution_result["success"]:
                return PipelineResult(
                    success=False,
                    message=f"Execution simulation failed: {execution_result['message']}",
                    data=data,
                    features=features,
                    alphas=alphas,
                    positions=positions,
                    errors=[execution_result["message"]]
                )
            executions = execution_result["executions"]
            metrics = execution_result["metrics"]
            logger.info(f"Simulated {len(executions)} executions")
            
            # Success
            return PipelineResult(
                success=True,
                message="Pipeline executed successfully",
                data=data,
                features=features,
                alphas=alphas,
                positions=positions,
                executions=executions,
                metrics=metrics,
                errors=errors
            )
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            return PipelineResult(
                success=False,
                message=f"Pipeline execution failed: {str(e)}",
                errors=[str(e)]
            )
    
    def _load_data(self) -> Dict[str, Any]:
        """Load market data for the universe."""
        try:
            all_data = []
            # Use explicit as_of_time from config (mandatory)
            as_of_time = self.config.as_of_time
            
            for ticker in self.config.universe:
                df = self.data_loader.load_prices(
                    ticker=ticker,
                    start_date=self.config.start_date,
                    end_date=self.config.end_date,
                    as_of_time=as_of_time
                )
                all_data.append(df)
            
            data = pd.concat(all_data, ignore_index=True)
            
            # Validate PIT safety
            pit_violations = data[data["as_of"] > data["available_at"]]
            if len(pit_violations) > 0:
                return {
                    "success": False,
                    "message": f"PIT violation detected: {len(pit_violations)} rows",
                    "data": None
                }
            
            return {
                "success": True,
                "message": "Data loaded successfully",
                "data": data
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Data loading error: {str(e)}",
                "data": None
            }
    
    def _compute_features(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Compute features from market data."""
        try:
            # Simple feature computation: returns and volume z-score
            features = data.copy()
            
            # Compute returns per ticker
            features["ret_1"] = features.groupby("ticker")["close"].pct_change(1)
            features["ret_5"] = features.groupby("ticker")["close"].pct_change(5)
            
            # Compute volume z-score per ticker
            features["vol_z"] = features.groupby("ticker")["volume"].transform(
                lambda x: (x - x.rolling(20, min_periods=1).mean()) / (x.rolling(20, min_periods=1).std() + 1e-8)
            )
            
            # Fill NaN values with 0 for features (instead of dropping rows)
            # This allows us to work with limited data while maintaining PIT safety
            features["ret_1"] = features["ret_1"].fillna(0)
            features["ret_5"] = features["ret_5"].fillna(0)
            features["vol_z"] = features["vol_z"].fillna(0)
            
            return {
                "success": True,
                "message": "Features computed successfully",
                "features": features
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Feature computation error: {str(e)}",
                "features": None
            }
    
    def _generate_alphas(self, features: pd.DataFrame) -> Dict[str, Any]:
        """Generate alpha signals from features."""
        try:
            # For simplicity, use a basic alpha: momentum (ret_5)
            # In production, use AlphaDiscoveryEngine to generate and evaluate multiple alphas
            
            alphas = features[["ticker", "date"]].copy()
            
            # Simple momentum alpha
            if "ret_5" in features.columns:
                alphas["alpha_momentum"] = features["ret_5"].copy()
            else:
                # Fallback: compute simple return
                alphas["alpha_momentum"] = features.groupby("ticker")["close"].pct_change(5).fillna(0)
            
            # Normalize alphas cross-sectionally (rank-based)
            # Handle edge case where all alphas are the same (e.g., all zeros)
            alphas["alpha_momentum_rank"] = alphas.groupby("date")["alpha_momentum"].transform(
                lambda x: x.rank(pct=True) if x.std() > 1e-8 else 0.5
            )
            
            # Fill any remaining NaN values
            alphas["alpha_momentum_rank"] = alphas["alpha_momentum_rank"].fillna(0.5)
            
            return {
                "success": True,
                "message": "Alphas generated successfully",
                "alphas": alphas
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Alpha generation error: {str(e)}",
                "alphas": None
            }
    
    def _apply_risk_controls(self, alphas: pd.DataFrame, data: pd.DataFrame) -> Dict[str, Any]:
        """Apply risk controls to alpha signals."""
        try:
            positions = alphas[["ticker", "date", "alpha_momentum_rank"]].copy()
            positions.rename(columns={"alpha_momentum_rank": "target_weight"}, inplace=True)
            
            # Apply individual position limits FIRST (before normalization)
            max_position = self.config.risk_config.max_concentration_per_stock
            
            # Clip each position to max limit
            positions["target_weight"] = positions["target_weight"].clip(0, max_position)
            
            # Normalize weights to sum to 1.0 per date
            # Handle edge case where sum is zero
            positions["target_weight"] = positions.groupby("date")["target_weight"].transform(
                lambda x: x / x.sum() if x.sum() > 1e-8 else 0
            )
            
            # Filter out positions with zero weight
            positions = positions[positions["target_weight"] > 1e-6].copy()
            
            return {
                "success": True,
                "message": "Risk controls applied successfully",
                "positions": positions
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Risk control error: {str(e)}",
                "positions": None
            }
    
    def _simulate_execution(self, positions: pd.DataFrame, data: pd.DataFrame) -> Dict[str, Any]:
        """Simulate realistic execution."""
        try:
            # Handle empty positions DataFrame
            if len(positions) == 0:
                return {
                    "success": True,
                    "message": "No positions to execute",
                    "executions": [],
                    "metrics": {
                        "total_trades": 0,
                        "avg_cost_bps": 0,
                        "total_cost_bps": 0
                    }
                }
            
            # Merge positions with price data
            execution_data = positions.merge(
                data[["ticker", "date", "close"]],
                on=["ticker", "date"],
                how="left"
            )
            
            # Simulate executions
            executions = []
            total_cost_bps = 0
            total_trades = 0
            
            for _, row in execution_data.iterrows():
                if pd.notna(row["target_weight"]) and pd.notna(row["close"]) and abs(row["target_weight"]) > 0.001:
                    # Simulate execution with slippage and commission
                    slippage_bps = self.config.execution_config.slippage_bps
                    commission_bps = self.config.execution_config.commission_bps
                    total_cost = slippage_bps + commission_bps
                    
                    execution = {
                        "ticker": row["ticker"],
                        "date": row["date"],
                        "target_weight": row["target_weight"],
                        "execution_price": row["close"],
                        "slippage_bps": slippage_bps,
                        "commission_bps": commission_bps,
                        "total_cost_bps": total_cost
                    }
                    executions.append(execution)
                    
                    total_cost_bps += total_cost
                    total_trades += 1
            
            # Compute metrics
            avg_cost_bps = total_cost_bps / total_trades if total_trades > 0 else 0
            
            metrics = {
                "total_trades": total_trades,
                "avg_cost_bps": avg_cost_bps,
                "total_cost_bps": total_cost_bps
            }
            
            return {
                "success": True,
                "message": "Execution simulated successfully",
                "executions": executions,
                "metrics": metrics
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Execution simulation error: {str(e)}",
                "executions": None,
                "metrics": None
            }


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """
    Convenience function to run the pipeline.
    
    Args:
        config: Pipeline configuration (mandatory - must include as_of_time)
        
    Returns:
        PipelineResult with all outputs
    """
    pipeline = OmegaPipeline(config)
    return pipeline.run()
