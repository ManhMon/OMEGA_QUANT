# L2 Implementation Prompt: Tier 3.2 - PipelineFactory

**Role**: Backend Engineer (Role 9)
**Platform**: OpenCode (L2)
**Task**: Create unified PipelineFactory entry point
**Date**: 2026-06-10
**SOD Compliance**: L2 implements → L3 audits → L4 verifies

---

## 📋 Context

### Current State
- **Problem**: Scattered pipeline instantiation across scripts/
  - `scripts/run_pipeline_v2_backtest.py`
  - `scripts/run_phase35_backtest.py`
  - `scripts/backtest_evolution.py`
  - 11+ other scripts with manual pipeline setup
- **Solution**: Unified `PipelineFactory` with clean API

### Constraints
- **Backward Compatibility**: Existing scripts must still work
- **Type Safety**: Full type hints
- **Documentation**: Docstrings for all public methods
- **PEP 8**: max-line-length=120, 0 violations

---

## 🎯 Deliverables

### 1. PipelineFactory Module

**File**: `src/omega/quant/pipeline_factory.py`

```python
"""Unified Pipeline Factory for OMEGA_QUANT.

Creates and configures pipeline instances based on mode and config.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Literal, Optional, Union

from omega.quant.pipeline_v2 import TradingPipelineV2
from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine
from omega.quant.walk_forward import FoldMetrics, WalkForwardResult

logger = logging.getLogger(__name__)

PipelineMode = Literal["backtest", "walk_forward", "evolution"]


class PipelineFactory:
    """Factory for creating and configuring OMEGA_QUANT pipelines.
    
    Supported modes:
    - "backtest": TradingPipelineV2 for single-period backtest
    - "walk_forward": Phase35WalkForwardEngine for multi-fold validation
    - "evolution": Alpha evolution pipeline (future)
    
    Example:
        >>> factory = PipelineFactory()
        >>> pipeline = factory.create("walk_forward", config={...})
        >>> results = factory.run(pipeline, data={...})
    """
    
    def create(
        self,
        mode: PipelineMode,
        config: Optional[Dict[str, Any]] = None,
    ) -> Union[TradingPipelineV2, Phase35WalkForwardEngine]:
        """Create pipeline instance based on mode.
        
        Args:
            mode: Pipeline type ("backtest", "walk_forward", "evolution")
            config: Configuration dict for pipeline initialization
            
        Returns:
            Configured pipeline instance
            
        Raises:
            ValueError: If mode is not supported
        """
        config = config or {}
        
        if mode == "backtest":
            return self._create_backtest_pipeline(config)
        elif mode == "walk_forward":
            return self._create_walk_forward_pipeline(config)
        elif mode == "evolution":
            raise NotImplementedError("Evolution pipeline not yet implemented")
        else:
            raise ValueError(f"Unsupported pipeline mode: {mode}")
    
    def _create_backtest_pipeline(
        self,
        config: Dict[str, Any],
    ) -> TradingPipelineV2:
        """Create TradingPipelineV2 instance.
        
        Args:
            config: Pipeline configuration
            
        Returns:
            Configured TradingPipelineV2
        """
        logger.info("Creating backtest pipeline (TradingPipelineV2)")
        
        # Extract pipeline-specific config
        overlays = config.get("overlays", [])
        feature_store = config.get("feature_store", None)
        output_handler = config.get("output_handler", None)
        
        return TradingPipelineV2(
            overlays=overlays,
            feature_store=feature_store,
            output_handler=output_handler,
        )
    
    def _create_walk_forward_pipeline(
        self,
        config: Dict[str, Any],
    ) -> Phase35WalkForwardEngine:
        """Create Phase35WalkForwardEngine instance.
        
        Args:
            config: Walk-forward configuration
            
        Returns:
            Configured Phase35WalkForwardEngine
        """
        logger.info("Creating walk-forward pipeline (Phase35WalkForwardEngine)")
        
        # Extract walk-forward-specific config
        alpha_module = config.get("alpha_module")
        if alpha_module is None:
            raise ValueError("alpha_module is required for walk_forward mode")
        
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
            blend_weight_method=config.get("blend_weight_method", "validation_ic"),
            p10_gate_mode=config.get("p10_gate_mode", "strict"),
            p10_gate_min_pass=config.get("p10_gate_min_pass", 1),
            p10_gate_allow_fallback_candidates=config.get("p10_gate_allow_fallback_candidates", False),
        )
    
    def run(
        self,
        pipeline: Union[TradingPipelineV2, Phase35WalkForwardEngine],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run pipeline with provided data.
        
        Args:
            pipeline: Pipeline instance from create()
            data: Input data dict
            
        Returns:
            Pipeline results dict
        """
        if isinstance(pipeline, TradingPipelineV2):
            return self._run_backtest(pipeline, data)
        elif isinstance(pipeline, Phase35WalkForwardEngine):
            return self._run_walk_forward(pipeline, data)
        else:
            raise TypeError(f"Unsupported pipeline type: {type(pipeline)}")
    
    def _run_backtest(
        self,
        pipeline: TradingPipelineV2,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run backtest pipeline.
        
        Args:
            pipeline: TradingPipelineV2 instance
            data: Input data with 'df' key
            
        Returns:
            Backtest results
        """
        logger.info("Running backtest pipeline")
        
        df = data.get("df")
        if df is None:
            raise ValueError("data['df'] is required for backtest mode")
        
        # Execute pipeline
        results = pipeline.execute(df)
        
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
        """Run walk-forward pipeline.
        
        Args:
            pipeline: Phase35WalkForwardEngine instance
            data: Input data with 'splits' and 'alpha_cols' keys
            
        Returns:
            Walk-forward results
        """
        logger.info("Running walk-forward pipeline")
        
        splits = data.get("splits")
        if splits is None:
            raise ValueError("data['splits'] is required for walk_forward mode")
        
        alpha_cols = data.get("alpha_cols")
        if alpha_cols is None:
            raise ValueError("data['alpha_cols'] is required for walk_forward mode")
        
        return_col = data.get("return_col", "fwd_ret_5")
        
        # Execute pipeline
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


__all__ = ["PipelineFactory", "PipelineMode"]
```

---

## ✅ Verification Steps

After implementation, run:

```powershell
# 1. PEP 8 compliance
pycodestyle --max-line-length=120 src/omega/quant/pipeline_factory.py

# 2. Import test
python -c "from omega.quant.pipeline_factory import PipelineFactory; print('OK')"

# 3. All tests still pass
pytest tests/test_pipeline_v2.py -v
```

**Expected Results**:
- pycodestyle: 0 violations
- Import: OK
- pytest: 6/6 passed

---

## 🛡️ Safety Rules

1. **No breaking changes**: Existing scripts must still work
2. **Type safety**: All public methods must have type hints
3. **Documentation**: All public classes/methods must have docstrings
4. **Error handling**: Raise clear errors for invalid config

---

## 📝 Notes for L2

- Use `view_file` tool (not `read_file`) to read source
- PowerShell: use `;` not `&&`
- Do NOT modify existing scripts/ (future Tier 3.3 will migrate them)
- Do NOT modify .ly_state/ directory
- This is a new module, no behavior changes to existing code

---

**Prompt prepared by**: L4 (Gemini)
**Ready for**: L2 (Codex CLI Role 9) execution
