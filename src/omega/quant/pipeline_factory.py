"""Unified Pipeline Factory for OMEGA_QUANT.

Creates and configures pipeline instances based on mode and config.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional, Union

from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
from omega.quant.pipeline_v2 import PipelineOutputHandler
from omega.quant.pipeline_v2 import PipelineStateManager
from omega.quant.pipeline_v2 import TradingPipelineV2
from omega.quant.pipeline_v2 import WeightOverlay
from omega.quant.pipeline_v2 import FeatureStoreAdapter
from omega.quant.walk_forward import FoldMetrics, WalkForwardResult

logger = logging.getLogger(__name__)

PipelineMode = Literal["backtest", "walk_forward", "evolution"]
PipelineInstance = Union[TradingPipelineV2, Phase35WalkForwardEngine]


class PipelineFactory:
    """Factory for creating and running OMEGA_QUANT pipelines.

    Supported modes:
    - "backtest": TradingPipelineV2 for single-period backtest
    - "walk_forward": Phase35WalkForwardEngine for multi-fold validation
    - "evolution": alpha evolution pipeline (future)
    """

    def create(
        self,
        mode: PipelineMode,
        config: Optional[Dict[str, Any]] = None,
    ) -> PipelineInstance:
        """Create a configured pipeline instance.

        Args:
            mode: Pipeline type ("backtest", "walk_forward", "evolution").
            config: Configuration dictionary for pipeline initialization.

        Returns:
            Configured pipeline instance.

        Raises:
            NotImplementedError: If the mode is planned but not implemented.
            ValueError: If the mode or required config is invalid.
        """
        config = config or {}

        if mode == "backtest":
            return self._create_backtest_pipeline(config)
        if mode == "walk_forward":
            return self._create_walk_forward_pipeline(config)
        if mode == "evolution":
            raise NotImplementedError("Evolution pipeline not yet implemented")
        raise ValueError(f"Unsupported pipeline mode: {mode}")

    def run(
        self,
        pipeline: PipelineInstance,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run a pipeline with provided input data.

        Args:
            pipeline: Pipeline instance returned by create().
            data: Execution inputs for the selected pipeline.

        Returns:
            Dictionary containing mode, status, and pipeline results.

        Raises:
            TypeError: If pipeline type is unsupported.
            ValueError: If required data keys are missing.
        """
        if isinstance(pipeline, TradingPipelineV2):
            return self._run_backtest(pipeline, data)
        if isinstance(pipeline, Phase35WalkForwardEngine):
            return self._run_walk_forward(pipeline, data)
        raise TypeError(f"Unsupported pipeline type: {type(pipeline)}")

    def _create_backtest_pipeline(
        self,
        config: Dict[str, Any],
    ) -> TradingPipelineV2:
        """Create a TradingPipelineV2 instance."""
        logger.info("Creating backtest pipeline (TradingPipelineV2)")

        feature_store = self._require_config(config, "feature_store")
        state_manager = self._require_config(config, "state_manager")
        output_handler = self._require_config(config, "output_handler")
        overlays = config.get("overlays", [])
        pipeline_config = config.get(
            "pipeline_config",
            config.get("config", {}),
        )

        if not isinstance(feature_store, FeatureStoreAdapter):
            raise TypeError(
                "config['feature_store'] must be a FeatureStoreAdapter"
            )
        if not isinstance(state_manager, PipelineStateManager):
            raise TypeError(
                "config['state_manager'] must be a PipelineStateManager"
            )
        if not isinstance(output_handler, PipelineOutputHandler):
            raise TypeError(
                "config['output_handler'] must be a PipelineOutputHandler"
            )
        if not isinstance(overlays, list):
            raise TypeError("config['overlays'] must be a list")
        if not all(isinstance(overlay, WeightOverlay) for overlay in overlays):
            raise TypeError(
                "config['overlays'] must contain WeightOverlay instances"
            )
        if not isinstance(pipeline_config, dict):
            raise TypeError("config['pipeline_config'] must be a dict")

        return TradingPipelineV2(
            feature_store=feature_store,
            state_manager=state_manager,
            output_handler=output_handler,
            overlays=overlays,
            config=pipeline_config,
        )

    def _create_walk_forward_pipeline(
        self,
        config: Dict[str, Any],
    ) -> Phase35WalkForwardEngine:
        """Create a Phase35WalkForwardEngine instance."""
        logger.info(
            "Creating walk-forward pipeline (Phase35WalkForwardEngine)"
        )

        alpha_module = self._require_config(config, "alpha_module")

        return Phase35WalkForwardEngine(
            alpha_module=alpha_module,
            min_ic_threshold=config.get("min_ic_threshold", 0.02),
            top_n_alphas=config.get("top_n_alphas", 5),
            top_n_stocks=config.get("top_n_stocks", 15),
            rebalance_freq=config.get("rebalance_freq", 7),
            sector_cap_pct=config.get("sector_cap_pct", 0.40),
            use_xgboost=config.get("use_xgboost", False),
            cost_aware=config.get("cost_aware", False),
            cost_per_turnover=config.get("cost_per_turnover", 0.0025),
            drawdown_control=config.get("drawdown_control", False),
            drawdown_threshold=config.get("drawdown_threshold", 0.05),
            strategy=config.get("strategy", "multi_factor"),
            initial_capital=config.get("initial_capital", 1_000_000_000.0),
            enable_evolved=config.get("enable_evolved", False),
            evolved_blend_weight=config.get("evolved_blend_weight", 0.5),
            multi_horizon_blend=config.get("multi_horizon_blend", False),
            blend_horizons=config.get("blend_horizons"),
            blend_weight_method=config.get(
                "blend_weight_method",
                "validation_ic",
            ),
            p10_gate_mode=config.get("p10_gate_mode", "strict"),
            p10_gate_min_pass=config.get("p10_gate_min_pass", 1),
            p10_gate_allow_fallback_candidates=config.get(
                "p10_gate_allow_fallback_candidates",
                False,
            ),
        )

    def _run_backtest(
        self,
        pipeline: TradingPipelineV2,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run a TradingPipelineV2 backtest."""
        logger.info("Running backtest pipeline")

        run_id = self._require_data(data, "run_id")
        date_start = self._require_data(data, "date_start")
        date_end = self._require_data(data, "date_end")

        results = pipeline.execute(
            run_id=run_id,
            date_start=date_start,
            date_end=date_end,
            tickers=data.get("tickers"),
        )

        return {
            "mode": "backtest",
            "results": results,
            "status": "success",
        }

    def _run_walk_forward(
        self,
        pipeline: Phase35WalkForwardEngine,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run a Phase35WalkForwardEngine walk-forward validation."""
        logger.info("Running walk-forward pipeline")

        splits = self._require_data(data, "splits")
        alpha_cols = self._require_data(data, "alpha_cols")
        return_col = data.get("return_col", "fwd_ret_5")

        results = pipeline.run_walk_forward(
            splits=splits,
            alpha_cols=alpha_cols,
            return_col=return_col,
        )

        return {
            "mode": "walk_forward",
            "results": results,
            "status": "success",
        }

    @staticmethod
    def _require_config(config: Dict[str, Any], key: str) -> Any:
        """Return a required config value or raise a clear error."""
        value = config.get(key)
        if value is None:
            raise ValueError(f"config['{key}'] is required")
        return value

    @staticmethod
    def _require_data(data: Dict[str, Any], key: str) -> Any:
        """Return a required data value or raise a clear error."""
        value = data.get(key)
        if value is None:
            raise ValueError(f"data['{key}'] is required")
        return value


__all__ = [
    "FoldMetrics",
    "PipelineFactory",
    "PipelineInstance",
    "PipelineMode",
    "WalkForwardResult",
]
