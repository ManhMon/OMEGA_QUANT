"""Worker Main Entry Point - OMEGA_QUANT Worker Process.

Purpose:
    Worker entry point that reads tasks from PriorityTaskQueue,
    dispatches to appropriate handlers based on task_type,
    reports heartbeat, and handles graceful shutdown.

Architecture:
    - Reads from src.omega.infra.task_queue.PriorityTaskQueue
    - Dispatches to handlers by task_type
    - Heartbeat reporting to .ly_state/session/worker_heartbeat.jsonl
    - Graceful shutdown on SIGTERM/SIGINT

Contract:
    - Input: Task from PriorityTaskQueue with task_type field
    - Output: Task result (ack/nack to queue)

Reference:
    - TEAM_ARCHITECTURE.md: L2 Backend Engineer (Role 9)
    - Spec Section 4.4: Worker Lifecycle

Author: Backend Engineer (Role 9)
Date: 2026-05-26
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Add src to path for imports
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from omega.infra.task_queue import PriorityTaskQueue, TaskItem

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Worker configuration."""
    
    worker_id: str
    max_retries: int = 3
    heartbeat_interval: float = 5.0
    state_dir: Path = WORKSPACE_ROOT / ".ly_state"
    log_level: str = "INFO"


class WorkerMain:
    """Main worker process that consumes tasks from PriorityTaskQueue.
    
    Responsibilities:
        1. Read tasks from PriorityTaskQueue
        2. Dispatch to handler based on task_type
        3. Report heartbeat to .ly_state/session/worker_heartbeat.jsonl
        4. Graceful shutdown on signal
        
    Task Types:
        - "alpha_compute": Compute alpha signals
        - "backtest": Run backtest
        - "risk_check": Validate risk constraints
        - "portfolio_optimize": Optimize portfolio weights
        - "execution_plan": Generate execution plan
    """
    
    def __init__(self, config: WorkerConfig, task_queue: PriorityTaskQueue):
        self.config = config
        self.task_queue = task_queue
        self.shutdown_requested = False
        self.current_task_id: Optional[str] = None
        
        # Task handlers registry
        self.handlers: Dict[str, Callable[[Any], Any]] = {
            "alpha_compute": self._handle_alpha_compute,
            "backtest": self._handle_backtest,
            "risk_check": self._handle_risk_check,
            "portfolio_optimize": self._handle_portfolio_optimize,
            "execution_plan": self._handle_execution_plan,
        }
        
        # Ensure state directory exists
        self.heartbeat_file = self.config.state_dir / "session" / "worker_heartbeat.jsonl"
        self.heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Register signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info(
            "WorkerMain initialized: worker_id=%s, heartbeat_interval=%.1fs",
            self.config.worker_id,
            self.config.heartbeat_interval,
        )
    
    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully."""
        sig_name = signal.Signals(signum).name
        logger.info("Received signal %s, initiating graceful shutdown...", sig_name)
        self.shutdown_requested = True
    
    def _report_heartbeat(self, status: str = "idle", task_id: Optional[str] = None) -> None:
        """Report worker heartbeat to state file.
        
        Args:
            status: Worker status (idle, processing, error)
            task_id: Current task ID if processing
        """
        heartbeat = {
            "timestamp": time.time(),
            "worker_id": self.config.worker_id,
            "status": status,
            "task_id": task_id,
        }
        
        try:
            with open(self.heartbeat_file, "a") as f:
                f.write(json.dumps(heartbeat) + "\n")
        except Exception as exc:
            logger.warning("Failed to write heartbeat: %s", exc)
    
    def _dispatch_task(self, task: TaskItem) -> Any:
        """Dispatch task to appropriate handler based on task_type.
        
        Args:
            task: TaskItem from queue
            
        Returns:
            Task result
            
        Raises:
            ValueError: If task_type is unknown
        """
        payload = task.payload
        
        if not isinstance(payload, dict):
            raise ValueError(f"Task payload must be dict, got {type(payload)}")
        
        task_type = payload.get("task_type")
        if not task_type:
            raise ValueError("Task payload missing 'task_type' field")
        
        handler = self.handlers.get(task_type)
        if not handler:
            raise ValueError(f"Unknown task_type: {task_type}")
        
        logger.info(
            "Dispatching task %s (type=%s) to handler",
            task.task_id[:8],
            task_type,
        )
        
        return handler(payload)
    
    def _handle_alpha_compute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle alpha computation task.
        
        Args:
            payload: Task payload with alpha computation parameters
            
        Returns:
            Result dict with computed alphas
        """
        logger.info("Handling alpha_compute task")
        
        # Placeholder: In production, this would call AlphaFactory
        # from v21_system.layer_01_core_intelligence.alpha_factory import AlphaFactory
        # factory = AlphaFactory()
        # result = factory.compute_all_alphas(payload['ohlcv_data'])
        
        return {
            "status": "success",
            "task_type": "alpha_compute",
            "result": "Alpha computation completed (placeholder)",
        }
    
    def _handle_backtest(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle backtest task.
        
        Args:
            payload: Task payload with backtest parameters
            
        Returns:
            Result dict with backtest metrics
        """
        logger.info("Handling backtest task")
        
        # Placeholder: In production, this would call BacktestEngine
        # from v21_system.layer_05_backtesting.backtest_engine import BacktestEngine
        # engine = BacktestEngine()
        # result = engine.run_backtest(payload['config'])
        
        return {
            "status": "success",
            "task_type": "backtest",
            "result": "Backtest completed (placeholder)",
        }
    
    def _handle_risk_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle risk check task.
        
        Args:
            payload: Task payload with risk check parameters
            
        Returns:
            Result dict with risk validation
        """
        logger.info("Handling risk_check task")
        
        # Placeholder: In production, this would call IndividualRiskGuard
        # from v21_system.layer_04_risk_management.individual_risk_guard import IndividualRiskGuard
        # guard = IndividualRiskGuard()
        # result = guard.validate_high_alpha_portfolio(...)
        
        return {
            "status": "success",
            "task_type": "risk_check",
            "result": "Risk check passed (placeholder)",
        }
    
    def _handle_portfolio_optimize(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle portfolio optimization task.
        
        Args:
            payload: Task payload with optimization parameters
            
        Returns:
            Result dict with optimized weights
        """
        logger.info("Handling portfolio_optimize task")
        
        # Placeholder: In production, this would call portfolio optimizer
        
        return {
            "status": "success",
            "task_type": "portfolio_optimize",
            "result": "Portfolio optimization completed (placeholder)",
        }
    
    def _handle_execution_plan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle execution plan generation task.
        
        Args:
            payload: Task payload with execution parameters
            
        Returns:
            Result dict with execution plan
        """
        logger.info("Handling execution_plan task")
        
        # Placeholder: In production, this would call ExecutionEngine
        # from v21_system.layer_03_execution_engine.execution_engine import ExecutionEngine
        # engine = ExecutionEngine()
        # result = engine.generate_execution_plan(...)
        
        return {
            "status": "success",
            "task_type": "execution_plan",
            "result": "Execution plan generated (placeholder)",
        }
    
    def run(self) -> None:
        """Main worker loop.
        
        Continuously:
            1. Get task from queue (blocking with timeout)
            2. Dispatch to handler
            3. Ack/nack based on result
            4. Report heartbeat
            5. Check for shutdown signal
        """
        logger.info("Worker %s starting main loop", self.config.worker_id)
        self._report_heartbeat(status="idle")
        
        last_heartbeat = time.time()
        
        while not self.shutdown_requested:
            # Get task from queue (with timeout to allow heartbeat updates)
            task = self.task_queue.get(timeout=1.0)
            
            if task is None:
                # No task available, check if we need to send heartbeat
                now = time.time()
                if now - last_heartbeat >= self.config.heartbeat_interval:
                    self._report_heartbeat(status="idle")
                    last_heartbeat = now
                continue
            
            self.current_task_id = task.task_id
            logger.info("Worker %s processing task %s", self.config.worker_id, task.task_id[:8])
            
            try:
                # Report heartbeat before processing
                self._report_heartbeat(status="processing", task_id=task.task_id)
                last_heartbeat = time.time()
                
                # Dispatch task to handler
                result = self._dispatch_task(task)
                
                # Acknowledge success
                self.task_queue.ack(task.task_id)
                logger.info("Task %s completed successfully", task.task_id[:8])
                
            except Exception as exc:
                # Negative-acknowledge failure
                error_msg = f"{type(exc).__name__}: {exc}"
                self.task_queue.nack(task.task_id, error=error_msg)
                logger.error("Task %s failed: %s", task.task_id[:8], error_msg)
                
                # Report error heartbeat
                self._report_heartbeat(status="error", task_id=task.task_id)
                last_heartbeat = time.time()
            
            finally:
                self.current_task_id = None
        
        # Shutdown: report final heartbeat
        logger.info("Worker %s shutting down gracefully", self.config.worker_id)
        self._report_heartbeat(status="shutdown")


def main() -> int:
    """Main entry point for worker process.
    
    Returns:
        Exit code (0 = success, 1 = error)
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(WORKSPACE_ROOT / ".ly_state" / "worker.log"),
        ],
    )
    
    logger.info("=" * 80)
    logger.info("OMEGA_QUANT Worker Process Starting")
    logger.info("=" * 80)
    
    # Generate worker ID
    worker_id = f"worker-{os.getpid()}"
    
    # Create config
    config = WorkerConfig(
        worker_id=worker_id,
        max_retries=3,
        heartbeat_interval=5.0,
        state_dir=WORKSPACE_ROOT / ".ly_state",
    )
    
    # Create task queue (shared instance - in production this would be passed in)
    task_queue = PriorityTaskQueue(
        max_workers=4,
        max_retries=config.max_retries,
    )
    
    # Create and run worker
    worker = WorkerMain(config, task_queue)
    
    try:
        worker.run()
        logger.info("Worker exited normally")
        return 0
    except Exception as exc:
        logger.exception("Worker crashed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
