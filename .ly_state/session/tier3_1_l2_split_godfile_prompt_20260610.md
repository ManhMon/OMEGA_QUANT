# L2 Implementation Prompt: Tier 3.1 - Split God-File (98KB)

**Role**: Backend Engineer (Role 9)
**Platform**: OpenCode (L2)
**Task**: Split `phase35_walk_forward.py` (2250 lines) into modular `walk_forward/` package
**Date**: 2026-06-10
**SOD Compliance**: L2 implements → L3 audits → L4 verifies

---

## 📋 Context

### Current State
- **File**: `src/omega/quant/phase35_walk_forward.py` (98KB, 2250 lines)
- **Problem**: God-file violates SRP, hard to maintain
- **Solution**: Extract into `src/omega/quant/walk_forward/` package with 10 modules

### Constraints
- **Backward Compatibility**: `from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine` MUST still work
- **PIT Safety**: All T-1 lag enforcement must be preserved
- **PEP 8**: max-line-length=120, 0 violations
- **Tests**: 351 tests must pass (pytest)

---

## 🎯 Deliverables

### 1. Package Structure
```
src/omega/quant/walk_forward/
├── __init__.py              # Re-export for backward compat
├── metrics.py               # FoldMetrics, WalkForwardResult (lines 111-166)
├── gate_utils.py            # _is_gate_verdict_pass (lines 37-93)
├── alpha_selector.py        # AlphaSelectionMixin (7 methods, lines 324-789)
├── signal_blender.py        # SignalBlendingMixin (3 methods, lines 791-1564)
├── portfolio_builder.py     # PortfolioBuilderMixin (4 methods, lines 1566-2050)
├── evolved_blender.py       # EvolvedBlendingMixin (1 method, lines 408-525)
└── fold_executor.py         # FoldExecutorMixin (run_fold, lines 1566-2148)
```

### 2. Module Specifications

#### `metrics.py`
```python
@dataclass
class FoldMetrics:
    # ... fields from lines 111-133 ...

@dataclass  
class WalkForwardResult:
    # ... fields from lines 136-166 ...
    def summary(self) -> str: ...
```

#### `gate_utils.py`
```python
def _is_gate_verdict_pass(verdict) -> bool:
    """Check if gate verdict is pass (robust truthiness)."""
    # ... implementation from lines 37-93 ...
```

#### `alpha_selector.py`
```python
class AlphaSelectionMixin:
    def compute_ic(self, alpha_values, returns) -> float: ...
    def compute_daily_cs_ic(self, df, signal_col, return_col, min_cross_section=5) -> float: ...
    def compute_alpha_ics(self, df, alpha_cols, return_col='fwd_ret_5') -> Dict: ...
    def _estimate_alpha_turnover(self, df, alpha_col) -> float: ...
    def adjust_alphas_for_cost(self, df, alpha_cols, train_ics, cost_per_turnover=None) -> Dict: ...
    def select_top_alphas(self, alpha_ics) -> List[str]: ...
    def validate_alpha_with_research_gate(self, top_alphas, train_ics, train_df_clean, return_col='fwd_ret_5', rolling_window=20) -> Tuple: ...
```

#### `signal_blender.py`
```python
class SignalBlendingMixin:
    def compute_portfolio_signal(self, df, alpha_cols, alpha_ics) -> pd.Series: ...
    def _compute_horizon_signal(self, fold_id, train_df, test_df, alpha_cols, return_col, horizon, cost_aware, final_objective_return_col='fwd_ret_5') -> Tuple: ...
    def _blend_horizon_signals(self, horizon_results, method="validation_ic") -> Optional[pd.Series]: ...
```

#### `portfolio_builder.py`
```python
class PortfolioBuilderMixin:
    def compute_sharpe_ratio(self, returns, periods_per_year=252) -> float: ...
    def compute_max_drawdown(self, returns) -> float: ...
    def _compute_sequential_dynamic_freq(self, train_df, available_test_df, base_freq=7) -> int: ...
    def _apply_stage2_constraints(self, test_df, raw_signal, top_alphas, dynamic_rebalance=False, train_df=None) -> pd.Series: ...
```

#### `evolved_blender.py`
```python
class EvolvedBlendingMixin:
    def _evolve_inline_signal(self, train_df, test_df, return_col) -> Tuple[Optional[np.ndarray], float]: ...
```

#### `fold_executor.py`
```python
class FoldExecutorMixin:
    def run_fold(self, fold_id, train_df, test_df, alpha_cols, return_col='fwd_ret_5', cost_aware=None) -> FoldMetrics: ...
    def run_walk_forward(self, splits, alpha_cols, return_col='fwd_ret_5') -> WalkForwardResult: ...
```

#### `__init__.py`
```python
"""Walk-Forward Package - Tier 3.1 Refactoring."""
from omega.quant.walk_forward.metrics import FoldMetrics, WalkForwardResult
from omega.quant.walk_forward.gate_utils import _is_gate_verdict_pass
from omega.quant.walk_forward.alpha_selector import AlphaSelectionMixin
from omega.quant.walk_forward.signal_blender import SignalBlendingMixin
from omega.quant.walk_forward.portfolio_builder import PortfolioBuilderMixin
from omega.quant.walk_forward.evolved_blender import EvolvedBlendingMixin
from omega.quant.walk_forward.fold_executor import FoldExecutorMixin

__all__ = [
    "FoldMetrics",
    "WalkForwardResult",
    "_is_gate_verdict_pass",
    "AlphaSelectionMixin",
    "SignalBlendingMixin",
    "PortfolioBuilderMixin",
    "EvolvedBlendingMixin",
    "FoldExecutorMixin",
]
```

### 3. Refactored Main Engine

**File**: `src/omega/quant/phase35_walk_forward.py` (becomes thin shim)

```python
"""Phase 3.5 Walk-Forward Backtest Engine (Tier 3.1 Refactored).

Backward compatibility shim. Primary implementation in walk_forward/ package.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional, List

from omega.quant.walk_forward import (
    FoldMetrics,
    WalkForwardResult,
    _is_gate_verdict_pass,
    AlphaSelectionMixin,
    SignalBlendingMixin,
    PortfolioBuilderMixin,
    EvolvedBlendingMixin,
    FoldExecutorMixin,
)

logger = logging.getLogger(__name__)


def _import_apply_sector_caps():
    """Lazy import of _apply_sector_caps from alpha_pipeline."""
    _scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    from alpha_pipeline import _apply_sector_caps
    return _apply_sector_caps


class Phase35WalkForwardEngine(
    AlphaSelectionMixin,
    SignalBlendingMixin,
    PortfolioBuilderMixin,
    EvolvedBlendingMixin,
    FoldExecutorMixin,
):
    """Walk-forward backtest engine for Phase 3.4 microstructure alphas."""
    
    def __init__(
        self,
        alpha_module,
        min_ic_threshold: float = 0.02,
        top_n_alphas: int = 5,
        top_n_stocks: int = 15,
        rebalance_freq: int = 7,
        sector_cap_pct: float = 0.40,
        use_xgboost: bool = False,
        cost_aware: bool = False,
        cost_per_turnover: float = 0.0025,
        drawdown_control: bool = False,
        drawdown_threshold: float = 0.05,
        strategy: str = "multi_factor",
        initial_capital: float = 1_000_000_000.0,
        enable_evolved: bool = False,
        evolved_blend_weight: float = 0.5,
        multi_horizon_blend: bool = False,
        blend_horizons: Optional[List[int]] = None,
        blend_weight_method: str = "validation_ic",
        p10_gate_mode: str = "strict",
        p10_gate_min_pass: int = 1,
        p10_gate_allow_fallback_candidates: bool = False,
    ):
        """Initialize walk-forward engine."""
        self.alpha_module = alpha_module
        self.min_ic_threshold = min_ic_threshold
        self.top_n_alphas = top_n_alphas
        self.top_n_stocks = top_n_stocks
        self.rebalance_freq = rebalance_freq
        self.sector_cap_pct = sector_cap_pct
        self.use_xgboost = use_xgboost
        self.cost_aware = cost_aware
        self.cost_per_turnover = cost_per_turnover
        self.drawdown_control = drawdown_control
        self.drawdown_threshold = drawdown_threshold
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.enable_evolved = enable_evolved
        
        # Validate blend weight
        if not 0 <= evolved_blend_weight <= 1:
            raise ValueError(f"evolved_blend_weight must be in [0, 1], got {evolved_blend_weight}")
        self.evolved_blend_weight = evolved_blend_weight
        
        # P10: Multi-horizon blending
        self.multi_horizon_blend = multi_horizon_blend
        self.blend_horizons = blend_horizons if blend_horizons is not None else [1, 3, 5]
        self.blend_weight_method = blend_weight_method
        
        # P10: Gate tuning validation
        valid_gate_modes = ["strict", "relaxed"]
        if p10_gate_mode not in valid_gate_modes:
            raise ValueError(f"p10_gate_mode must be one of {valid_gate_modes}, got '{p10_gate_mode}'")
        self.p10_gate_mode = p10_gate_mode
        
        if not isinstance(p10_gate_min_pass, int) or p10_gate_min_pass < 0:
            raise ValueError(f"p10_gate_min_pass must be a non-negative integer, got {p10_gate_min_pass}")
        self.p10_gate_min_pass = p10_gate_min_pass
        
        if not isinstance(p10_gate_allow_fallback_candidates, bool):
            raise ValueError(f"p10_gate_allow_fallback_candidates must be a boolean, got {p10_gate_allow_fallback_candidates}")
        self.p10_gate_allow_fallback_candidates = p10_gate_allow_fallback_candidates
        
        # Store reference alpha columns
        self.alpha_cols_ref = getattr(alpha_module, 'PHASE34_ALPHA_COLUMNS', [])
    
    def compute_alphas(self, df):
        """Compute Phase 3.4 alphas on data."""
        return self.alpha_module.compute_phase34_microstructure_alphas(
            df,
            symbol_col='ticker',
            date_col='date',
            open_col='open',
            high_col='high',
            low_col='low',
            close_col='close',
            volume_col='volume',
        )


# Re-export for backward compatibility
__all__ = ["Phase35WalkForwardEngine", "FoldMetrics", "WalkForwardResult"]
```

---

## ✅ Verification Steps

After implementation, run:

```powershell
# 1. PEP 8 compliance
pycodestyle --max-line-length=120 src/omega/quant/walk_forward/*.py src/omega/quant/phase35_walk_forward.py

# 2. All tests pass
pytest tests/test_pipeline_v2.py -v

# 3. Backward compatibility check
python -c "from omega.quant.phase35_walk_forward import Phase35WalkForwardEngine; print('OK')"
```

**Expected Results**:
- pycodestyle: 0 violations
- pytest: 351 passed
- Import: OK

---

## 🛡️ Safety Rules

1. **No behavior change**: Extract only, no logic modifications
2. **PIT Safety**: Preserve all T-1 lag enforcement
3. **Backward compat**: Old import paths must work
4. **Type hints**: All public methods must have type hints
5. **Docstrings**: All public classes/methods must have docstrings

---

## 📝 Notes for L2

- Use `view_file` tool (not `read_file`) to read source
- PowerShell: use `;` not `&&`
- Do NOT modify tests/ directory
- Do NOT modify .ly_state/ directory
- Maintain all `# Role21 Fix 2026-06-10` comments
- Keep all PIT safety comments (`# T-1 lag`, `# Embargo`, etc.)

---

**Prompt prepared by**: L4 (Gemini)
**Ready for**: L2 (Codex CLI Role 9) execution
