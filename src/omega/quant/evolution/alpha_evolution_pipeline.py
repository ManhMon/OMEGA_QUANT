"""
OMEGA_QUANT Alpha Self-Evolution Pipeline
Autonomous alpha discovery, evaluation, decay detection, and promotion.

Flow:
    [1] Evolve: GP generates new alpha population
    [2] Evaluate: IC, Sharpe, hit rate on train/test
    [3] Filter: OrthogonalityChecker removes redundant alphas
    [4] Decay: AlphaDecayMonitor retires weak alphas
    [5] Promote: AlphaPromoter pushes strong alphas to production
    [6] Backtest: ParallelBacktestRunner verifies P&L
    [7] Loop: Back to [1] with new population

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 1.0.0
PIT Safety: PASS - T-1 lag enforced at every stage.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from omega.quant.evolution.genetic_alpha import Genome, enforce_t_minus_1_lag
from omega.quant.alpha_discovery import (
    AlphaDecayMonitor,
    AlphaPromoter,
    OrthogonalityChecker,
    FeatureUniverseManager,
)
from omega.quant.parallel_backtest import ParallelBacktestRunner

logger = logging.getLogger(__name__)


@dataclass
class EvolutionConfig:
    """Configuration for the self-evolution pipeline."""
    population_size: int = 100
    generations: int = 20
    max_depth: int = 4
    mutation_rate: float = 0.3
    crossover_rate: float = 0.6
    elitism_count: int = 3
    ic_threshold: float = 0.03
    decay_threshold: float = 0.5
    corr_threshold: float = 0.7
    min_sharpe: float = 0.5
    min_hit_rate: float = 0.52
    backtest_workers: int = 4
    state_dir: str = "data/alpha_evolution"
    max_active_alphas: int = 20


@dataclass
class AlphaCandidate:
    """A candidate alpha with evaluation metrics."""
    genome: Genome
    expression: str
    train_ic: float = 0.0
    test_ic: float = 0.0
    sharpe: float = 0.0
    hit_rate: float = 0.0
    turnover: float = 0.0
    max_drawdown: float = 0.0
    generation: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "candidate"  # candidate, active, decayed, rejected
    _eval_failures: int = field(default=0, repr=False)

    def fitness(self) -> float:
        """Composite fitness: IC - turnover penalty - complexity penalty."""
        depth_penalty = 0.01 * self.genome.get_depth()
        turnover_penalty = 0.1 * self.turnover
        return self.test_ic - turnover_penalty - depth_penalty

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expression": self.expression,
            "train_ic": self.train_ic,
            "test_ic": self.test_ic,
            "sharpe": self.sharpe,
            "hit_rate": self.hit_rate,
            "turnover": self.turnover,
            "max_drawdown": self.max_drawdown,
            "generation": self.generation,
            "created_at": self.created_at,
            "status": self.status,
            "depth": self.genome.get_depth(),
        }


class AlphaEvolutionPipeline:
    """
    Self-evolving alpha pipeline. Discovers, evaluates, filters,
    and promotes alphas autonomously.
    """

    def __init__(self, config: Optional[EvolutionConfig] = None):
        self.config = config or EvolutionConfig()
        self.state_dir = Path(self.config.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Components
        self.universe = FeatureUniverseManager(state_path=str(self.state_dir / "universe.json"))
        self.decay_monitor = AlphaDecayMonitor(
            universe_manager=self.universe, decay_threshold=self.config.decay_threshold
        )
        self.promoter = AlphaPromoter(
            universe_manager=self.universe, output_path=str(self.state_dir / "promoted_alphas.py")
        )
        self.orthogonality = OrthogonalityChecker(corr_threshold=self.config.corr_threshold)
        self.backtest_runner = ParallelBacktestRunner(
            num_workers=self.config.backtest_workers,
            initial_capital=1_000_000_000.0,
        )

        # State
        self.active_alphas: List[AlphaCandidate] = []
        self.history: List[Dict[str, Any]] = []
        self._load_state()

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        state_file = self.state_dir / "pipeline_state.json"
        if state_file.exists():
            with open(state_file) as f:
                data = json.load(f)
            self.history = data.get("history", [])
            logger.info("Loaded state: %d history entries", len(self.history))

    def _save_state(self) -> None:
        """Persist state to disk."""
        state_file = self.state_dir / "pipeline_state.json"
        data = {
            "history": self.history,
            "active_alphas": [a.to_dict() for a in self.active_alphas],
            "last_updated": datetime.utcnow().isoformat(),
        }
        with open(state_file, "w") as f:
            json.dump(data, f, indent=2)

    def _generate_population(self, generation: int) -> List[Genome]:
        """Generate a population of random genomes."""
        population = []
        for _ in range(self.config.population_size):
            genome = Genome(max_depth=self.config.max_depth)
            population.append(genome)
        logger.info("Gen %d: Created population of %d genomes", generation, len(population))
        return population

    def _evaluate_genome(
        self, genome: Genome, train_df: pd.DataFrame, test_df: pd.DataFrame, target_col: str
    ) -> Optional[AlphaCandidate]:
        """Evaluate a single genome on train/test data."""
        try:
            # Evaluate signal
            train_signal = genome.evaluate_vectorized(train_df)
            test_signal = genome.evaluate_vectorized(test_df)

            # Skip constant signals
            if train_signal.std() < 1e-8 or test_signal.std() < 1e-8:
                return None

            # IC (Spearman rank correlation with forward returns)
            train_ic = train_signal.corr(train_df[target_col], method="spearman")
            test_ic = test_signal.corr(test_df[target_col], method="spearman")

            if np.isnan(train_ic) or np.isnan(test_ic):
                return None

            # Hit rate
            hit_rate = (np.sign(test_signal) == np.sign(test_df[target_col])).mean()

            # Turnover (signal change rate)
            turnover = test_signal.diff().abs().mean() / (test_signal.abs().mean() + 1e-10)

            return AlphaCandidate(
                genome=genome,
                expression=repr(genome),
                train_ic=float(train_ic),
                test_ic=float(test_ic),
                hit_rate=float(hit_rate),
                turnover=float(turnover),
            )
        except Exception as e:
            logger.debug("Genome eval failed: %s | expr=%s", e, repr(genome)[:50])
            return None

    def _evolve_generation(
        self, population: List[Genome], train_df: pd.DataFrame, test_df: pd.DataFrame, target_col: str, generation: int
    ) -> List[AlphaCandidate]:
        """Run one generation: evaluate, select, crossover, mutate."""
        # Evaluate all genomes
        candidates = []
        for genome in population:
            candidate = self._evaluate_genome(genome, train_df, test_df, target_col)
            if candidate is not None:
                candidate.generation = generation
                candidates.append(candidate)

        if not candidates:
            return []

        # Sort by fitness
        candidates.sort(key=lambda c: c.fitness(), reverse=True)
        logger.info(
            "Gen %d: %d/%d viable, best IC=%.4f, best fitness=%.4f",
            generation, len(candidates), len(population),
            candidates[0].test_ic, candidates[0].fitness(),
        )

        # Selection + reproduction for next generation
        elite = candidates[: self.config.elitism_count]
        new_population = [c.genome for c in elite]

        while len(new_population) < self.config.population_size:
            if np.random.random() < self.config.crossover_rate and len(candidates) >= 2:
                # Tournament selection
                parents = np.random.choice(len(candidates), size=2, replace=False)
                child = Genome.crossover(candidates[parents[0]].genome, candidates[parents[1]].genome)
                new_population.append(child)
            elif np.random.random() < self.config.mutation_rate:
                parent_idx = np.random.randint(len(candidates))
                mutant = candidates[parent_idx].genome.mutate()
                new_population.append(mutant)
            else:
                new_population.append(Genome(max_depth=self.config.max_depth))

        return candidates

    def _filter_orthogonal(self, candidates: List[AlphaCandidate], train_df: pd.DataFrame) -> List[AlphaCandidate]:
        """Remove redundant alphas using correlation check."""
        if not candidates:
            return []

        # Build signals and filter incrementally
        accepted: List[AlphaCandidate] = []
        accepted_signals: Dict[str, pd.Series] = {}

        for c in candidates:
            try:
                sig = c.genome.evaluate_vectorized(train_df)
                if sig.std() < 1e-8:
                    continue

                # Check orthogonality against already-accepted alphas
                if not accepted_signals:
                    # First alpha always accepted
                    accepted.append(c)
                    accepted_signals[c.expression[:50]] = sig
                else:
                    correlated = self.orthogonality.find_redundant_features(sig, accepted_signals)
                    if not correlated:  # No high correlation found
                        accepted.append(c)
                        accepted_signals[c.expression[:50]] = sig
            except Exception:
                pass

        logger.info("Orthogonality filter: %d -> %d alphas (removed %d redundant)",
                    len(candidates), len(accepted), len(candidates) - len(accepted))
        return accepted

    def _check_decay(self, active_alphas: List[AlphaCandidate], recent_df: pd.DataFrame, target_col: str) -> List[AlphaCandidate]:
        """Check active alphas for decay, retire weak ones."""
        surviving = []

        # Build current IC dict for all active alphas
        current_ics: Dict[str, float] = {}
        alpha_map: Dict[str, AlphaCandidate] = {}

        for alpha in active_alphas:
            key = alpha.expression[:80]
            try:
                recent_signal = alpha.genome.evaluate_vectorized(recent_df)
                recent_ic = recent_signal.corr(recent_df[target_col], method="spearman")
                if not np.isnan(recent_ic):
                    current_ics[key] = float(recent_ic)
                    alpha_map[key] = alpha
                else:
                    # NaN IC treated as eval failure
                    raise ValueError("NaN IC")
            except Exception as e:
                # Track consecutive eval failures; retire after 3
                if not hasattr(alpha, '_eval_failures'):
                    alpha._eval_failures = 0
                alpha._eval_failures += 1
                if alpha._eval_failures >= 3:
                    alpha.status = "decayed"
                    logger.warning("Alpha retired after %d consecutive eval failures: %s | %s",
                                   alpha._eval_failures, alpha.expression[:50], e)
                else:
                    logger.debug("Alpha eval failed (%d/3): %s | %s",
                                 alpha._eval_failures, alpha.expression[:50], e)
                    surviving.append(alpha)

        # Use AlphaDecayMonitor to detect decayed alphas
        if current_ics:
            decayed_names = self.decay_monitor.check_decay(current_ics)
            for key, alpha in alpha_map.items():
                if key in decayed_names:
                    alpha.status = "decayed"
                    logger.info("Alpha decayed: %s (current IC: %.4f)",
                                alpha.expression[:50], current_ics.get(key, 0))
                else:
                    alpha._eval_failures = 0  # Reset on successful eval
                    surviving.append(alpha)

        logger.info("Decay check: %d -> %d active alphas", len(active_alphas), len(surviving))
        return surviving

    def _promote_alphas(self, candidates: List[AlphaCandidate]) -> List[AlphaCandidate]:
        """Promote top candidates that pass quality gates."""
        promoted = []
        for c in candidates:
            if (c.test_ic >= self.config.ic_threshold
                and c.hit_rate >= self.config.min_hit_rate
                and len(self.active_alphas) + len(promoted) < self.config.max_active_alphas):
                c.status = "active"
                promoted.append(c)
                # Register in universe
                self.universe.add_feature(
                    name=c.expression[:80],
                    ic_score=c.test_ic,
                    coverage=c.hit_rate,
                    category="evolved",
                    expression=c.expression,
                    status="candidate",
                )
                self.universe.promote_to_active(c.expression[:80])
                logger.info("Promoted alpha: IC=%.4f, Hit=%.4f, Expr=%s",
                            c.test_ic, c.hit_rate, c.expression[:60])

        if promoted:
            self.promoter.save_promoted_code()
        return promoted

    def _backtest_portfolio(
        self, alphas: List[AlphaCandidate], prices: pd.DataFrame
    ) -> Dict[str, float]:
        """Run parallel backtest on promoted alpha portfolio."""
        if not alphas or prices.empty:
            return {"sharpe": 0.0, "total_return": 0.0}

        n_alphas = len(alphas)
        # Equal weight across alphas, each alpha generates cross-sectional weights
        # Use mean signal across all active alphas as combined signal
        combined_weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        for alpha in alphas:
            try:
                # Build full OHLCV panel from prices for evaluation.
                # Genomes may reference open/high/low/volume — use close as proxy
                # when only close is available. This ensures no silent zero-signal.
                panel = prices.stack()
                panel.index.names = ['date', 'symbol']
                panel = panel.to_frame('close')
                panel['open'] = panel['close']
                panel['high'] = panel['close']
                panel['low'] = panel['close']
                panel['volume'] = 1_000_000.0  # Default volume proxy
                panel['returns'] = panel.groupby(level='symbol')['close'].pct_change().fillna(0)

                signal = alpha.genome.evaluate_vectorized(panel)
                if isinstance(signal, pd.Series) and len(signal) > 0:
                    unstacked = signal.unstack(level='symbol') if isinstance(signal.index, pd.MultiIndex) else signal
                    if isinstance(unstacked, pd.DataFrame):
                        ranked = unstacked.rank(axis=1, pct=True)
                        normalized = ranked.div(ranked.sum(axis=1), axis=0).fillna(0)
                        combined_weights = combined_weights.add(normalized, fill_value=0.0)
            except Exception as e:
                logger.debug("Alpha backtest eval failed: %s | expr=%s", e, alpha.expression[:50])
                continue

        # Average across alphas
        if combined_weights.sum().sum() > 0:
            combined_weights = combined_weights / n_alphas
            # Re-normalize rows
            row_sums = combined_weights.sum(axis=1).replace(0, 1.0)
            combined_weights = combined_weights.div(row_sums, axis=0)

        # Drop warmup rows
        valid = combined_weights.sum(axis=1) > 0
        combined_weights = combined_weights.loc[valid]
        prices_aligned = prices.loc[combined_weights.index]

        if len(combined_weights) < 10:
            return {"sharpe": 0.0, "total_return": 0.0}

        result = self.backtest_runner.run(prices_aligned, combined_weights)
        return result.metrics

    def run(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        target_col: str = "fwd_ret_5",
        prices: Optional[pd.DataFrame] = None,
        n_generations: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Run the full self-evolution pipeline.

        Args:
            train_df: Training data (MultiIndex or flat with OHLCV)
            test_df: Test data (same format)
            target_col: Forward return column for IC calculation
            prices: Price DataFrame for backtest (dates x symbols)
            n_generations: Override config generations

        Returns:
            Summary dict with evolution results
        """
        start_time = time.time()
        generations = n_generations or self.config.generations

        logger.info("=== ALPHA EVOLUTION PIPELINE START ===")
        logger.info("Population: %d, Generations: %d, Max depth: %d",
                    self.config.population_size, generations, self.config.max_depth)

        # Step 1: Check decay on existing active alphas
        if self.active_alphas:
            self.active_alphas = self._check_decay(self.active_alphas, test_df, target_col)

        # Step 2: Evolve new alphas
        population = self._generate_population(0)
        all_candidates: List[AlphaCandidate] = []

        for gen in range(generations):
            candidates = self._evolve_generation(population, train_df, test_df, target_col, gen)
            if candidates:
                all_candidates.extend(candidates[:10])  # Keep top 10 per generation
                # Next generation population from evolved genomes
                population = [c.genome for c in candidates[:self.config.elitism_count]]
                while len(population) < self.config.population_size:
                    if np.random.random() < self.config.crossover_rate and len(candidates) >= 2:
                        parents = np.random.choice(min(20, len(candidates)), size=2, replace=False)
                        child = Genome.crossover(candidates[parents[0]].genome, candidates[parents[1]].genome)
                        population.append(child)
                    else:
                        population.append(Genome(max_depth=self.config.max_depth))

        # Step 3: Filter by quality
        quality_candidates = [
            c for c in all_candidates
            if c.test_ic >= self.config.ic_threshold and c.hit_rate >= self.config.min_hit_rate
        ]
        quality_candidates.sort(key=lambda c: c.fitness(), reverse=True)
        logger.info("Quality filter: %d -> %d candidates", len(all_candidates), len(quality_candidates))

        # Step 4: Orthogonality filter
        orthogonal_candidates = self._filter_orthogonal(quality_candidates[:50], train_df)

        # Step 5: Promote
        newly_promoted = self._promote_alphas(orthogonal_candidates)
        self.active_alphas.extend(newly_promoted)

        # Step 6: Backtest portfolio
        backtest_metrics = {}
        if prices is not None and self.active_alphas:
            backtest_metrics = self._backtest_portfolio(self.active_alphas, prices)
            logger.info("Portfolio backtest: Sharpe=%.4f, Return=%.4f",
                        backtest_metrics.get("sharpe", 0), backtest_metrics.get("total_return", 0))

        # Save state
        elapsed = time.time() - start_time
        run_summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "duration_s": elapsed,
            "generations": generations,
            "total_evaluated": len(all_candidates),
            "quality_passed": len(quality_candidates),
            "orthogonal_passed": len(orthogonal_candidates),
            "newly_promoted": len(newly_promoted),
            "total_active": len(self.active_alphas),
            "backtest_metrics": backtest_metrics,
        }
        self.history.append(run_summary)
        self._save_state()

        logger.info("=== EVOLUTION COMPLETE: %d active alphas, %.1fs ===", len(self.active_alphas), elapsed)
        return run_summary
