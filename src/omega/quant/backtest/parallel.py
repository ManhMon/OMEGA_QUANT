"""
OMEGA_QUANT Parallel Backtest Runner
Chia symbols thanh chunks, chay song song qua WorkerPool.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 1.0.0
PIT Safety: PASS - Each chunk uses same temporal data, no cross-chunk leakage.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from omega.infra.worker_pool import WorkerPool, TaskResult
from omega.quant.backtest_engine import BacktestEngine, BacktestResult

logger = logging.getLogger(__name__)


@dataclass
class ChunkTask:
    """A backtest task for a subset of symbols."""
    chunk_id: int
    symbols: List[str]
    prices: pd.DataFrame
    weights: pd.DataFrame
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParallelBacktestResult:
    """Aggregated result from all chunks."""
    equity_curve: pd.Series
    returns: pd.Series
    metrics: Dict[str, float]
    chunk_results: List[BacktestResult]
    chunk_durations: List[float]
    total_duration: float
    num_workers: int
    num_chunks: int


class ParallelBacktestRunner:
    """
    Parallel backtest runner - splits symbols into chunks and runs
    each chunk on a separate worker via WorkerPool.

    Parameters
    ----------
    num_workers : int
        Number of parallel workers (default: 4).
    chunk_size : int or None
        Symbols per chunk. If None, auto-calculated from num_workers.
    initial_capital : float
        Total capital, split proportionally across chunks.
    fee_rate : float
        Trading fee rate.
    tax_rate : float
        Tax rate on profits.
    slippage_bps : float
        Slippage in basis points.
    """

    def __init__(
        self,
        num_workers: int = 4,
        chunk_size: Optional[int] = None,
        initial_capital: float = 1_000_000_000.0,
        fee_rate: float = 0.0015,
        tax_rate: float = 0.0010,
        slippage_bps: float = 2.0,
    ):
        self.num_workers = num_workers
        self.chunk_size = chunk_size
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.tax_rate = tax_rate
        self.slippage_bps = slippage_bps

    def _create_engine(self) -> BacktestEngine:
        """Create a BacktestEngine instance with current config."""
        return BacktestEngine(
            initial_capital=0,  # Set per-chunk below
            fee_rate=self.fee_rate,
            tax_rate=self.tax_rate,
            slippage_bps=self.slippage_bps,
        )

    def _split_symbols(self, symbols: List[str]) -> List[List[str]]:
        """Split symbols into chunks."""
        n = len(symbols)
        if self.chunk_size:
            size = self.chunk_size
        else:
            size = max(1, math.ceil(n / self.num_workers))

        chunks = []
        for i in range(0, n, size):
            chunks.append(symbols[i : i + size])
        return chunks

    def _run_chunk(self, task: ChunkTask) -> BacktestResult:
        """Execute backtest for a single chunk of symbols."""
        n_symbols = len(task.symbols)
        total_symbols = task.config.get("total_symbols", n_symbols)
        chunk_capital = self.initial_capital * (n_symbols / total_symbols)

        engine = BacktestEngine(
            initial_capital=chunk_capital,
            fee_rate=self.fee_rate,
            tax_rate=self.tax_rate,
            slippage_bps=self.slippage_bps,
        )

        # Re-normalize weights within chunk so they sum to 1.0 per row.
        # Design decision: each chunk is treated as an independent sub-portfolio
        # with its proportional share of capital. This ensures BacktestEngine
        # sees fully-invested weights regardless of how many symbols are in the chunk.
        chunk_weights = task.weights.copy()
        row_sums = chunk_weights.sum(axis=1)
        row_sums = row_sums.replace(0, 1.0)  # Avoid division by zero
        chunk_weights = chunk_weights.div(row_sums, axis=0)

        return engine.run(task.prices, chunk_weights)

    def run(
        self,
        prices: pd.DataFrame,
        weights: pd.DataFrame,
    ) -> ParallelBacktestResult:
        """
        Run parallel backtest across symbol chunks.

        Args:
            prices: DataFrame (index=dates, columns=symbols)
            weights: DataFrame (index=dates, columns=symbols)

        Returns:
            ParallelBacktestResult with aggregated metrics.
        """
        start_time = time.time()

        symbols = list(prices.columns)
        n_total = len(symbols)
        logger.info("ParallelBacktest: %d symbols, %d workers", n_total, self.num_workers)

        # Split into chunks
        chunks = self._split_symbols(symbols)
        num_chunks = len(chunks)
        logger.info("Split into %d chunks (avg %.0f symbols/chunk)", num_chunks, n_total / num_chunks)

        # Create tasks
        tasks = []
        for i, chunk_symbols in enumerate(chunks):
            task = ChunkTask(
                chunk_id=i,
                symbols=chunk_symbols,
                prices=prices[chunk_symbols],
                weights=weights[chunk_symbols],
                config={"total_symbols": n_total},
            )
            tasks.append(task)

        # Run via WorkerPool
        pool = WorkerPool(
            max_workers=min(self.num_workers, num_chunks),
            task_handler=self._run_chunk,
            heartbeat_timeout=120.0,
        )

        # Submit all tasks BEFORE starting pool to avoid race condition
        # where pool reports completion before all tasks are queued
        for task in tasks:
            pool.submit(task)

        pool.start()

        # Wait for all results with bounded timeout
        max_wait = max(300.0, num_chunks * 60.0)  # At least 5min or 60s per chunk
        deadline = time.time() + max_wait
        while True:
            results = pool.get_results()
            if len(results) >= num_chunks:
                break
            if time.time() > deadline:
                pool.shutdown(wait=False, timeout=5.0)
                raise TimeoutError(
                    f"ParallelBacktest timed out after {max_wait:.0f}s. "
                    f"Got {len(results)}/{num_chunks} chunk results."
                )
            time.sleep(0.1)

        pool.shutdown(wait=True, timeout=60.0)

        # Collect results
        chunk_results: List[BacktestResult] = []
        chunk_durations: List[float] = []
        failed_chunks: List[int] = []

        for r in results:
            if r.success:
                chunk_results.append(r.result)
                chunk_durations.append(r.duration)
            else:
                failed_chunks.append(r.task.chunk_id)
                logger.error("Chunk %d failed: %s", r.task.chunk_id, r.error)

        if failed_chunks:
            logger.warning("%d/%d chunks failed: %s", len(failed_chunks), num_chunks, failed_chunks)

        if not chunk_results:
            raise RuntimeError("All backtest chunks failed")

        # Aggregate results
        aggregated = self._aggregate_results(chunk_results, prices.index)

        total_duration = time.time() - start_time
        logger.info(
            "ParallelBacktest complete: %.2fs total, %.2fs avg/chunk, Sharpe=%.3f",
            total_duration,
            sum(chunk_durations) / len(chunk_durations) if chunk_durations else 0,
            aggregated["metrics"].get("sharpe", 0),
        )

        return ParallelBacktestResult(
            equity_curve=aggregated["equity_curve"],
            returns=aggregated["returns"],
            metrics=aggregated["metrics"],
            chunk_results=chunk_results,
            chunk_durations=chunk_durations,
            total_duration=total_duration,
            num_workers=self.num_workers,
            num_chunks=num_chunks,
        )

    def _aggregate_results(
        self,
        chunk_results: List[BacktestResult],
        index: pd.DatetimeIndex,
    ) -> Dict[str, Any]:
        """Aggregate chunk results into portfolio-level metrics."""
        # Sum equity curves (each chunk is a portion of total capital)
        combined_equity = pd.Series(0.0, index=index)
        for cr in chunk_results:
            combined_equity = combined_equity.add(cr.equity_curve, fill_value=0.0)

        # Portfolio returns from combined equity
        combined_returns = combined_equity.pct_change().fillna(0.0)

        # Metrics
        total_return = (combined_equity.iloc[-1] - combined_equity.iloc[0]) / combined_equity.iloc[0] if combined_equity.iloc[0] > 0 else 0.0
        volatility = combined_returns.std() * np.sqrt(252)
        sharpe = (combined_returns.mean() * 252) / volatility if volatility > 0 else 0.0

        downside = combined_returns[combined_returns < 0]
        downside_std = downside.std() * np.sqrt(252) if len(downside) > 0 else 0.0
        sortino = (combined_returns.mean() * 252) / downside_std if downside_std > 0 else 0.0

        cumulative = (1 + combined_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        winning = (combined_returns > 0).sum()
        total_days = (combined_returns != 0).sum()
        win_rate = winning / total_days if total_days > 0 else 0.0

        metrics = {
            "total_return": total_return,
            "volatility": volatility,
            "sharpe": sharpe,
            "sortino": sortino,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "num_chunks": len(chunk_results),
        }

        return {
            "equity_curve": combined_equity,
            "returns": combined_returns,
            "metrics": metrics,
        }
