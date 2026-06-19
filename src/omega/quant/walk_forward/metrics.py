"""Walk-forward metrics dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FoldMetrics:
    """Metrics for a single walk-forward fold."""
    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    alpha_ics: Dict[str, float] = field(default_factory=dict)
    portfolio_sharpe: float = 0.0
    portfolio_max_dd: float = 0.0
    portfolio_total_return: float = 0.0
    portfolio_pnl_vnd: float = 0.0
    portfolio_ic: float = 0.0
    raw_signal_ic: float = 0.0
    raw_signal_daily_cs_ic: float = 0.0
    n_train_samples: int = 0
    n_test_samples: int = 0
    # Stage 3 ML Gate fields
    gate_results: Dict[str, dict] = field(default_factory=dict)
    gated_alphas: List[str] = field(default_factory=list)
    # P10 Gate Tuning: structured fallback-candidate labeling (Role21 Fix 2026-06-10)
    gate_metadata: Optional[Dict[str, any]] = field(default_factory=lambda: None)


@dataclass
class WalkForwardResult:
    """Complete walk-forward backtest results."""
    fold_metrics: List[FoldMetrics] = field(default_factory=list)
    avg_ic_by_alpha: Dict[str, float] = field(default_factory=dict)
    avg_portfolio_sharpe: float = 0.0
    avg_portfolio_max_dd: float = 0.0
    avg_portfolio_ic: float = 0.0
    avg_raw_signal_ic: float = 0.0
    avg_raw_signal_daily_cs_ic: float = 0.0
    avg_portfolio_pnl_vnd: float = 0.0
    total_folds: int = 0

    def summary(self) -> str:
        """Generate summary string."""
        lines = [
            f"Walk-Forward Backtest Results ({self.total_folds} folds)",
            "=" * 60,
            f"Average Portfolio IC (post Stage 2): {self.avg_portfolio_ic:.4f}",
            f"Average Raw Signal IC (pre Stage 2):  {self.avg_raw_signal_ic:.4f}",
            f"Average Raw Signal Daily CS IC:       {self.avg_raw_signal_daily_cs_ic:.4f}",
            f"Average Portfolio Sharpe: {self.avg_portfolio_sharpe:.4f}",
            f"Average Max Drawdown: {self.avg_portfolio_max_dd:.2%}",
            "",
            "Alpha IC Summary:",
        ]

        for alpha, ic in sorted(self.avg_ic_by_alpha.items(), key=lambda x: abs(x[1]), reverse=True):
            lines.append(f"  {alpha}: {ic:.4f}")

        return "\n".join(lines)
