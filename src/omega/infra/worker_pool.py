"""Worker Pool with lifecycle management, heartbeat, and crash recovery.

Spec Section 4.4 (Worker Lifecycle) - Infrastructure layer for OMEGA_QUANT.
Worker states: BOOT -> LOAD_CONTEXT -> EXECUTE -> VERIFY -> REPORT -> UNLOAD -> IDLE
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkerState(str, Enum):
    """Worker lifecycle states per Spec Section 4.4."""

    BOOT = "BOOT"
    LOAD_CONTEXT = "LOAD_CONTEXT"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    REPORT = "REPORT"
    UNLOAD = "UNLOAD"
    IDLE = "IDLE"
    DEAD = "DEAD"
    STOPPED = "STOPPED"


@dataclass
class WorkerInfo:
    """Metadata for a single worker."""

    worker_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: WorkerState = WorkerState.IDLE
    current_task: Optional[Any] = None
    last_heartbeat: float = field(default_factory=time.time)
    tasks_completed: int = 0
    tasks_failed: int = 0
    started_at: float = field(default_factory=time.time)
    error: Optional[str] = None


@dataclass
class TaskResult:
    """Result of a worker task execution."""

    task: Any
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration: float = 0.0


class WorkerPool:
    """Thread-based worker pool with heartbeat monitoring and crash recovery.

    Parameters
    ----------
    max_workers : int
        Maximum number of concurrent workers.
    heartbeat_interval : float
        Seconds between heartbeat checks.
    heartbeat_timeout : float
        Seconds before a worker is considered dead.
    max_restarts : int
        Maximum times a crashed worker can be restarted.
    task_handler : callable, optional
        Function to execute for each task. Signature: (task) -> result.
    """

    def __init__(
        self,
        max_workers: int = 4,
        heartbeat_interval: float = 5.0,
        heartbeat_timeout: float = 30.0,
        max_restarts: int = 3,
        task_handler: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        self._max_workers = max_workers
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._max_restarts = max_restarts
        self._task_handler = task_handler or self._default_handler

        # Worker registry
        self._workers: Dict[str, WorkerInfo] = {}
        self._worker_threads: Dict[str, threading.Thread] = {}
        self._workers_lock = threading.Lock()

        # Task submission
        self._task_queue: List[Any] = []
        self._task_lock = threading.Lock()
        self._task_available = threading.Condition(self._task_lock)

        # Results
        self._results: List[TaskResult] = []
        self._results_lock = threading.Lock()

        # Restart tracking
        self._restart_counts: Dict[str, int] = {}

        # Control
        self._shutdown = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

        logger.info(
            "WorkerPool initialized: max_workers=%d, heartbeat_timeout=%.1fs",
            max_workers,
            heartbeat_timeout,
        )

    def start(self) -> None:
        """Start the worker pool and heartbeat monitor."""
        if self._shutdown.is_set():
            raise RuntimeError("Cannot start a shut-down pool")

        # Spawn workers
        for _ in range(self._max_workers):
            self._spawn_worker()

        # Start heartbeat monitor
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_monitor, daemon=True, name="heartbeat-monitor"
        )
        self._heartbeat_thread.start()
        logger.info("WorkerPool started with %d workers", self._max_workers)

    def _spawn_worker(self) -> str:
        """Spawn a new worker thread."""
        info = WorkerInfo()
        info.state = WorkerState.BOOT

        thread = threading.Thread(
            target=self._worker_loop,
            args=(info,),
            daemon=True,
            name=f"worker-{info.worker_id[:8]}",
        )

        with self._workers_lock:
            self._workers[info.worker_id] = info
            self._worker_threads[info.worker_id] = thread

        thread.start()
        logger.debug("Worker %s spawned", info.worker_id[:8])
        return info.worker_id

    def _worker_loop(self, info: WorkerInfo) -> None:
        """Main loop for a worker thread."""
        try:
            # BOOT phase
            info.state = WorkerState.BOOT
            info.last_heartbeat = time.time()

            # Transition to IDLE
            info.state = WorkerState.IDLE

            while not self._shutdown.is_set():
                # Wait for task
                task = self._wait_for_task()
                if task is None:
                    # Shutdown signal
                    break

                info.current_task = task
                start_time = time.time()

                try:
                    # LOAD_CONTEXT
                    info.state = WorkerState.LOAD_CONTEXT
                    info.last_heartbeat = time.time()

                    # EXECUTE
                    info.state = WorkerState.EXECUTE
                    info.last_heartbeat = time.time()
                    result = self._task_handler(task)

                    # VERIFY
                    info.state = WorkerState.VERIFY
                    info.last_heartbeat = time.time()

                    # REPORT
                    info.state = WorkerState.REPORT
                    info.last_heartbeat = time.time()
                    duration = time.time() - start_time

                    task_result = TaskResult(
                        task=task, success=True, result=result, duration=duration
                    )
                    with self._results_lock:
                        self._results.append(task_result)

                    info.tasks_completed += 1
                    logger.debug(
                        "Worker %s completed task in %.2fs",
                        info.worker_id[:8],
                        duration,
                    )

                except Exception as exc:
                    # Task failed
                    duration = time.time() - start_time
                    info.tasks_failed += 1
                    info.error = str(exc)

                    task_result = TaskResult(
                        task=task,
                        success=False,
                        error=str(exc),
                        duration=duration,
                    )
                    with self._results_lock:
                        self._results.append(task_result)

                    logger.error(
                        "Worker %s task failed: %s", info.worker_id[:8], exc
                    )

                finally:
                    # UNLOAD
                    info.state = WorkerState.UNLOAD
                    info.current_task = None
                    info.last_heartbeat = time.time()

                    # Back to IDLE
                    info.state = WorkerState.IDLE
                    info.last_heartbeat = time.time()

        except Exception as exc:
            info.state = WorkerState.DEAD
            info.error = str(exc)
            logger.error("Worker %s crashed: %s", info.worker_id[:8], exc)

        finally:
            if not self._shutdown.is_set() and info.state == WorkerState.DEAD:
                # Trigger crash recovery
                self._handle_crash(info.worker_id)

    def _wait_for_task(self) -> Optional[Any]:
        """Wait for a task from the internal queue."""
        with self._task_available:
            while not self._task_queue and not self._shutdown.is_set():
                self._task_available.wait(timeout=1.0)

            if self._shutdown.is_set() and not self._task_queue:
                return None

            if self._task_queue:
                return self._task_queue.pop(0)
            return None

    def _heartbeat_monitor(self) -> None:
        """Monitor worker heartbeats and detect dead workers."""
        while not self._shutdown.is_set():
            time.sleep(self._heartbeat_interval)

            if self._shutdown.is_set():
                break

            now = time.time()
            with self._workers_lock:
                for worker_id, info in list(self._workers.items()):
                    if info.state in (WorkerState.STOPPED, WorkerState.DEAD):
                        continue

                    elapsed = now - info.last_heartbeat
                    if elapsed > self._heartbeat_timeout:
                        logger.warning(
                            "Worker %s heartbeat timeout (%.1fs). Marking DEAD.",
                            worker_id[:8],
                            elapsed,
                        )
                        info.state = WorkerState.DEAD
                        self._handle_crash(worker_id)

    def _handle_crash(self, worker_id: str) -> None:
        """Handle a crashed worker - restart if under limit."""
        restart_count = self._restart_counts.get(worker_id, 0)

        if restart_count >= self._max_restarts:
            logger.error(
                "Worker %s exceeded max restarts (%d). Not restarting.",
                worker_id[:8],
                self._max_restarts,
            )
            return

        self._restart_counts[worker_id] = restart_count + 1
        logger.info(
            "Restarting worker %s (attempt %d/%d)",
            worker_id[:8],
            restart_count + 1,
            self._max_restarts,
        )

        # Remove old worker
        with self._workers_lock:
            self._workers.pop(worker_id, None)
            self._worker_threads.pop(worker_id, None)

        # Spawn replacement
        self._spawn_worker()

    def submit(self, task: Any) -> None:
        """Submit a task to the worker pool.

        Parameters
        ----------
        task : Any
            The task payload to be processed by a worker.
        """
        if self._shutdown.is_set():
            raise RuntimeError("Pool is shut down, cannot accept new tasks")

        with self._task_available:
            self._task_queue.append(task)
            self._task_available.notify()

        logger.debug("Task submitted to pool")

    def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Gracefully shut down the worker pool.

        Parameters
        ----------
        wait : bool
            If True, wait for workers to finish current tasks.
        timeout : float
            Maximum seconds to wait for workers to finish.
        """
        logger.info("WorkerPool shutdown initiated (wait=%s)", wait)
        self._shutdown.set()

        # Wake up waiting workers
        with self._task_available:
            self._task_available.notify_all()

        if wait:
            deadline = time.time() + timeout
            with self._workers_lock:
                threads = list(self._worker_threads.values())

            for thread in threads:
                remaining = deadline - time.time()
                if remaining > 0:
                    thread.join(timeout=remaining)

        # Mark all workers as stopped
        with self._workers_lock:
            for info in self._workers.values():
                if info.state != WorkerState.DEAD:
                    info.state = WorkerState.STOPPED

        logger.info("WorkerPool shutdown complete")

    def get_status(self) -> Dict[str, Any]:
        """Get pool status summary.

        Returns
        -------
        dict
            Pool status including worker states, task counts, etc.
        """
        with self._workers_lock:
            workers_snapshot = {
                wid: {
                    "state": info.state.value,
                    "tasks_completed": info.tasks_completed,
                    "tasks_failed": info.tasks_failed,
                    "current_task": info.current_task is not None,
                    "last_heartbeat_age": time.time() - info.last_heartbeat,
                    "error": info.error,
                }
                for wid, info in self._workers.items()
            }

        with self._task_lock:
            pending_tasks = len(self._task_queue)

        with self._results_lock:
            total_results = len(self._results)

        return {
            "max_workers": self._max_workers,
            "active_workers": len(workers_snapshot),
            "pending_tasks": pending_tasks,
            "total_results": total_results,
            "is_shutdown": self._shutdown.is_set(),
            "workers": workers_snapshot,
        }

    def get_results(self) -> List[TaskResult]:
        """Return a copy of all task results collected so far."""
        with self._results_lock:
            return list(self._results)

    @staticmethod
    def _default_handler(task: Any) -> Any:
        """Default no-op task handler."""
        return task
