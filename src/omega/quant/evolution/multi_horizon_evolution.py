"""
OMEGA_QUANT Multi-Horizon Alpha Evolution
Evolve alphas independently per return horizon (1d, 3d, 5d, 10d, 20d).
Alphas from different horizons are naturally uncorrelated -> ensemble benefit.

Key insight: Sharpe(ensemble) ~ Sharpe(single) * sqrt(N) when alphas uncorrelated.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 1.0.0
PIT Safety: PASS - T-1 lag enforced, chronological split, purge gap.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from omega.quant.evolution.genetic_alpha import Genome, enforce_t_minus_1_lag
from omega.quant.evolution.alpha_evolution_pipeline import (
    AlphaEvolutionPipeline,
    AlphaCandidate,
    EvolutionConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class MultiHorizonConfig:
    """Configuration for multi-horizon evolution."""
    horizons: List[int] = field(default_factory=lambda: [1, 3, 5, 10, 20])
    population_size: int = 100
    generations: int = 20
    max_depth: int = 5
    ic_threshold: float = 0.03       # Lower per-horizon; ensemble compensates
    min_hit_rate: float = 0.51
    corr_threshold: float = 0.5      # Cross-horizon filter
    max_alphas_per_horizon: int = 3
    max_total_alphas: int = 10
    state_dir: str = "data/multi_horizon_evolution"


class MultiHorizonEvolution:
    """
    Evolve alphas independently per return horizon.
    Each horizon gets its own GP run with horizon-specific target.
    Final ensemble combines best alphas across all horizons.
    """

    def __init__(self, config: Optional[MultiHorizonConfig] = None):
        self.config = config or MultiHorizonConfig()

    def _build_horizon_target(self, panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Add forward return target for specific horizon (PIT-safe: shift(-N))."""
        col_name = f"fwd_ret_{horizon}"
        panel = panel.copy()
        panel[col_name] = panel.groupby(level='symbol')['close'].pct_change(horizon).shift(-horizon)
        return panel

    def _evolve_single_horizon(
        self,
        train_panel: pd.DataFrame,
        val_panel: pd.DataFrame,
        horizon: int,
    ) -> List[AlphaCandidate]:
        """Run GP evolution for a single horizon."""
        target_col = f"fwd_ret_{horizon}"

        # Add target to panels
        train_h = self._build_horizon_target(train_panel, horizon)
        val_h = self._build_horizon_target(val_panel, horizon)

        # Drop NaN targets
        train_h = train_h.dropna(subset=[target_col])
        val_h = val_h.dropna(subset=[target_col])

        if len(train_h) < 100 or len(val_h) < 50:
            logger.warning("Horizon %dd: insufficient data (train=%d, val=%d)", horizon, len(train_h), len(val_h))
            return []

        # Configure evolution for this horizon
        evo_config = EvolutionConfig(
            population_size=self.config.population_size,
            generations=self.config.generations,
            max_depth=self.config.max_depth,
            mutation_rate=0.35,
            crossover_rate=0.6,
            elitism_count=3,
            ic_threshold=self.config.ic_threshold,
            decay_threshold=0.5,
            corr_threshold=0.7,
            min_hit_rate=self.config.min_hit_rate,
            backtest_workers=2,
            state_dir=f"{self.config.state_dir}/horizon_{horizon}d",
            max_active_alphas=self.config.max_alphas_per_horizon,
        )

        pipeline = AlphaEvolutionPipeline(config=evo_config)
        result = pipeline.run(
            train_df=train_h,
            test_df=val_h,
            target_col=target_col,
            prices=None,
            n_generations=self.config.generations,
        )

        # Tag alphas with horizon info
        for alpha in pipeline.active_alphas:
            alpha.expression = f"H{horizon}d:{alpha.expression}"

        logger.info("Horizon %dd: %d alphas (best IC=%.4f)",
                    horizon, len(pipeline.active_alphas),
                    pipeline.active_alphas[0].test_ic if pipeline.active_alphas else 0)

        return list(pipeline.active_alphas)

    def _cross_horizon_filter(
        self, all_alphas: List[AlphaCandidate], val_panel: pd.DataFrame
    ) -> List[AlphaCandidate]:
        """Filter across horizons: keep diverse alphas (corr < threshold)."""
        if not all_alphas:
            return []

        # Sort by IC descending
        all_alphas.sort(key=lambda a: abs(a.test_ic), reverse=True)

        accepted = []
        accepted_sigs: Dict[str, pd.Series] = {}

        for alpha in all_alphas:
            try:
                sig = alpha.genome.evaluate_vectorized(val_panel)
                # Explicit T-1 lag guard (PIT safety - do not rely on pipeline internals)
                sig = enforce_t_minus_1_lag(sig)
                if sig.std() < 1e-8:
                    continue

                # Check correlation against accepted
                is_diverse = True
                for _, esig in accepted_sigs.items():
                    common = sig.index.intersection(esig.index)
                    if len(common) > 50:
                        corr = sig.loc[common].corr(esig.loc[common])
                        if abs(corr) > self.config.corr_threshold:
                            is_diverse = False
                            break

                if is_diverse:
                    accepted.append(alpha)
                    accepted_sigs[alpha.expression[:60]] = sig

                if len(accepted) >= self.config.max_total_alphas:
                    break
            except Exception:
                continue

        return accepted

    def run(
        self,
        train_panel: pd.DataFrame,
        val_panel: pd.DataFrame,
    ) -> Tuple[List[AlphaCandidate], Dict[str, Any]]:
        """
        Run multi-horizon evolution pipeline.

        Args:
            train_panel: Training data with MultiIndex [date, symbol] + OHLCV + returns
            val_panel: Validation data (same format)

        Returns:
            (final_alphas, summary_dict)
        """
        t0 = time.time()
        logger.info("=" * 70)
        logger.info("MULTI-HORIZON EVOLUTION: horizons=%s", self.config.horizons)
        logger.info("=" * 70)

        # Evolve per horizon
        horizon_results = {}
        all_alphas = []

        for horizon in self.config.horizons:
            logger.info("")
            logger.info("--- Horizon %dd ---", horizon)
            alphas = self._evolve_single_horizon(train_panel, val_panel, horizon)
            horizon_results[horizon] = {
                "n_alphas": len(alphas),
                "best_ic": alphas[0].test_ic if alphas else 0,
            }
            all_alphas.extend(alphas)

        logger.info("")
        logger.info("Total alphas across all horizons: %d", len(all_alphas))

        # Cross-horizon diversity filter
        final_alphas = self._cross_horizon_filter(all_alphas, val_panel)
        logger.info("After cross-horizon filter (corr<%.1f): %d alphas",
                    self.config.corr_threshold, len(final_alphas))

        elapsed = time.time() - t0
        summary = {
            "horizons": self.config.horizons,
            "horizon_results": horizon_results,
            "total_candidates": len(all_alphas),
            "final_alphas": len(final_alphas),
            "duration_s": elapsed,
            "alphas": [{"expr": a.expression[:80], "ic": a.test_ic, "hit": a.hit_rate} for a in final_alphas],
        }

        logger.info("=== MULTI-HORIZON COMPLETE: %d diverse alphas, %.1fs ===", len(final_alphas), elapsed)
        return final_alphas, summary
