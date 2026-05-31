"""
OMEGA_QUANT Alpha Evolution Scheduler
Continuous decay monitoring + auto re-evolution when alpha pool depletes.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 1.0.0
PIT Safety: PASS - All evaluations use T-1 lagged signals.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pandas as pd

from omega.quant.evolution.alpha_evolution_pipeline import (
    AlphaEvolutionPipeline,
    EvolutionConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class SchedulerConfig:
    """Configuration for the evolution scheduler."""
    decay_check_interval_s: float = 3600.0  # Check decay every hour
    min_active_alphas: int = 3  # Trigger re-evolution below this
    max_evolution_runs: int = 10  # Max consecutive evolution runs
    cooldown_after_evolution_s: float = 1800.0  # 30min cooldown after evolution
    state_dir: str = "data/alpha_evolution"


class EvolutionScheduler:
    """
    Scheduler that continuously monitors alpha decay and triggers
    re-evolution when the active alpha pool depletes.

    States:
        IDLE -> MONITORING -> EVOLVING -> IDLE

    Usage:
        scheduler = EvolutionScheduler(pipeline, config)
        scheduler.run_cycle(train_df, test_df, prices)  # Single cycle
        scheduler.run_loop(data_provider)  # Continuous loop
    """

    def __init__(
        self,
        pipeline: AlphaEvolutionPipeline,
        config: Optional[SchedulerConfig] = None,
    ):
        self.pipeline = pipeline
        self.config = config or SchedulerConfig()
        self.state_dir = Path(self.config.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.state = "IDLE"
        self.last_decay_check: float = 0.0
        self.last_evolution: float = 0.0
        self.evolution_count: int = 0
        self.cycle_history: list = []

    def _should_check_decay(self) -> bool:
        """Check if enough time has passed for decay check."""
        elapsed = time.time() - self.last_decay_check
        return elapsed >= self.config.decay_check_interval_s

    def _should_evolve(self) -> bool:
        """Check if re-evolution is needed."""
        if self.evolution_count >= self.config.max_evolution_runs:
            logger.warning("Max evolution runs reached (%d). Pausing.", self.config.max_evolution_runs)
            return False

        cooldown_elapsed = time.time() - self.last_evolution
        if cooldown_elapsed < self.config.cooldown_after_evolution_s:
            return False

        n_active = len(self.pipeline.active_alphas)
        if n_active < self.config.min_active_alphas:
            logger.info("Active alphas (%d) below threshold (%d). Triggering evolution.",
                        n_active, self.config.min_active_alphas)
            return True
        return False

    def run_cycle(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        target_col: str = "fwd_ret_5",
        prices: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Run one scheduler cycle: decay check + conditional evolution.

        Returns:
            Cycle summary dict.
        """
        cycle_start = time.time()
        cycle_result = {
            "timestamp": datetime.utcnow().isoformat(),
            "actions": [],
            "state_before": self.state,
        }

        # Phase 1: Decay monitoring
        self.state = "MONITORING"
        if self.pipeline.active_alphas:
            before_count = len(self.pipeline.active_alphas)
            self.pipeline.active_alphas = self.pipeline._check_decay(
                self.pipeline.active_alphas, test_df, target_col
            )
            after_count = len(self.pipeline.active_alphas)
            self.last_decay_check = time.time()

            cycle_result["actions"].append({
                "type": "decay_check",
                "before": before_count,
                "after": after_count,
                "retired": before_count - after_count,
            })
            logger.info("Decay check: %d -> %d active alphas", before_count, after_count)

        # Phase 2: Conditional evolution
        if self._should_evolve():
            self.state = "EVOLVING"
            evolution_result = self.pipeline.run(
                train_df, test_df, target_col=target_col, prices=prices
            )
            self.last_evolution = time.time()
            self.evolution_count += 1

            cycle_result["actions"].append({
                "type": "evolution",
                "result": evolution_result,
            })
        else:
            cycle_result["actions"].append({"type": "skip_evolution", "reason": "not needed"})

        # Phase 3: Save state
        self.state = "IDLE"
        cycle_result["duration_s"] = time.time() - cycle_start
        cycle_result["active_alphas"] = len(self.pipeline.active_alphas)
        cycle_result["state_after"] = self.state

        self.cycle_history.append(cycle_result)
        self._save_scheduler_state()

        return cycle_result

    def run_loop(
        self,
        data_provider: Callable[[], tuple],
        max_cycles: int = 100,
        sleep_between_s: float = 60.0,
    ) -> None:
        """
        Continuous monitoring loop.

        Args:
            data_provider: Callable returning (train_df, test_df, prices)
            max_cycles: Maximum cycles before stopping
            sleep_between_s: Sleep between cycles
        """
        logger.info("=== EVOLUTION SCHEDULER LOOP START (max %d cycles) ===", max_cycles)

        for cycle_num in range(max_cycles):
            try:
                train_df, test_df, prices = data_provider()
                result = self.run_cycle(train_df, test_df, prices=prices)

                logger.info(
                    "Cycle %d/%d: %d active alphas, actions=%s",
                    cycle_num + 1, max_cycles,
                    result["active_alphas"],
                    [a["type"] for a in result["actions"]],
                )

                if sleep_between_s > 0:
                    time.sleep(sleep_between_s)

            except KeyboardInterrupt:
                logger.info("Scheduler interrupted by user.")
                break
            except Exception as e:
                logger.error("Cycle %d failed: %s", cycle_num + 1, e)
                time.sleep(sleep_between_s)

        logger.info("=== EVOLUTION SCHEDULER LOOP END ===")

    def _save_scheduler_state(self) -> None:
        """Persist scheduler state."""
        state_file = self.state_dir / "scheduler_state.json"
        data = {
            "state": self.state,
            "last_decay_check": self.last_decay_check,
            "last_evolution": self.last_evolution,
            "evolution_count": self.evolution_count,
            "cycle_count": len(self.cycle_history),
            "last_updated": datetime.utcnow().isoformat(),
        }
        with open(state_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_status(self) -> Dict[str, Any]:
        """Get current scheduler status."""
        return {
            "state": self.state,
            "active_alphas": len(self.pipeline.active_alphas),
            "evolution_count": self.evolution_count,
            "cycles_completed": len(self.cycle_history),
            "last_decay_check_ago_s": time.time() - self.last_decay_check if self.last_decay_check else None,
            "last_evolution_ago_s": time.time() - self.last_evolution if self.last_evolution else None,
        }
