"""Priority Task Queue with Dead-Letter Queue and Retry Logic.

Spec Section 4.3 (Scheduler) - Infrastructure layer for OMEGA_QUANT.
Provides bounded-concurrency priority queue with exponential backoff retry
and dead-letter queue for persistently failing tasks.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from queue import Empty, PriorityQueue
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskPriority(IntEnum):
    """Task priority levels (lower value = higher priority)."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class TaskStatus:
    """Task lifecycle states."""

    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


@dataclass(order=True)
class TaskItem:
    """A prioritized task item in the queue."""

    priority: int
    timestamp: float = field(compare=True)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    payload: Any = field(default=None, compare=False)
    status: str = field(default=TaskStatus.PENDING, compare=False)
    retry_count: int = field(default=0, compare=False)
    max_retries: int = field(default=3, compare=False)
    last_error: Optional[str] = field(default=None, compare=False)
    created_at: float = field(default_factory=time.time, compare=False)


class PriorityTaskQueue:
    """Priority queue with dead-letter queue, retry, and bounded concurrency.

    Parameters
    ----------
    max_workers : int
        Maximum number of tasks that can be in-flight concurrently.
    max_retries : int
        Default max retry attempts before sending to DLQ.
    base_backoff : float
        Base delay in seconds for exponential backoff.
    max_backoff : float
        Maximum backoff delay in seconds.
    """

    def __init__(
        self,
        max_workers: int = 4,
        max_retries: int = 3,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ) -> None:
        self._queue: PriorityQueue[TaskItem] = PriorityQueue()
        self._max_workers = max_workers
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff

        # Track in-flight tasks
        self._in_flight: Dict[str, TaskItem] = {}
        self._in_flight_lock = threading.Lock()

        # Semaphore for bounded concurrency
        self._semaphore = threading.Semaphore(max_workers)

        # Dead-letter queue
        self._dlq: List[TaskItem] = []
        self._dlq_lock = threading.Lock()

        # All tasks registry
        self._registry: Dict[str, TaskItem] = {}
        self._registry_lock = threading.Lock()

        # Shutdown flag
        self._shutdown = threading.Event()

        logger.info(
            "PriorityTaskQueue initialized: max_workers=%d, max_retries=%d",
            max_workers,
            max_retries,
        )

    def put(
        self,
        payload: Any,
        priority: int = TaskPriority.NORMAL,
        max_retries: Optional[int] = None,
    ) -> str:
        """Enqueue a task with given priority.

        Parameters
        ----------
        payload : Any
            The task payload/data.
        priority : int
            Priority level (lower = higher priority).
        max_retries : int, optional
            Override default max retries for this task.

        Returns
        -------
        str
            The task_id assigned to this task.
        """
        if self._shutdown.is_set():
            raise RuntimeError("Queue is shut down, cannot accept new tasks")

        task = TaskItem(
            priority=priority,
            timestamp=time.time(),
            payload=payload,
            max_retries=max_retries if max_retries is not None else self._max_retries,
        )

        with self._registry_lock:
            self._registry[task.task_id] = task

        self._queue.put(task)
        logger.debug("Task %s enqueued with priority %d", task.task_id, priority)
        return task.task_id

    def get(self, timeout: Optional[float] = None) -> Optional[TaskItem]:
        """Dequeue the highest-priority task, respecting concurrency limits.

        Blocks until a task is available and a worker slot is free,
        or until timeout expires.

        Parameters
        ----------
        timeout : float, optional
            Maximum seconds to wait. None = block indefinitely.

        Returns
        -------
        TaskItem or None
            The next task, or None if timeout expired or queue is shut down.
        """
        if self._shutdown.is_set():
            return None

        # Acquire worker slot (bounded concurrency)
        acquired = self._semaphore.acquire(timeout=timeout)
        if not acquired:
            return None

        if self._shutdown.is_set():
            self._semaphore.release()
            return None

        try:
            task = self._queue.get(timeout=timeout if timeout else 0.1)
        except Empty:
            self._semaphore.release()
            return None

        # Mark as in-flight
        task.status = TaskStatus.IN_FLIGHT
        with self._in_flight_lock:
            self._in_flight[task.task_id] = task

        logger.debug("Task %s dequeued (in-flight)", task.task_id)
        return task

    def ack(self, task_id: str) -> bool:
        """Acknowledge successful task completion.

        Parameters
        ----------
        task_id : str
            The task to acknowledge.

        Returns
        -------
        bool
            True if task was in-flight and acknowledged.
        """
        with self._in_flight_lock:
            task = self._in_flight.pop(task_id, None)

        if task is None:
            logger.warning("ack called for unknown/non-in-flight task: %s", task_id)
            return False

        task.status = TaskStatus.COMPLETED
        self._semaphore.release()
        logger.debug("Task %s acknowledged (completed)", task_id)
        return True

    def nack(self, task_id: str, error: Optional[str] = None) -> bool:
        """Negative-acknowledge a task (failed). Retries with backoff or sends to DLQ.

        Parameters
        ----------
        task_id : str
            The task that failed.
        error : str, optional
            Error description.

        Returns
        -------
        bool
            True if task was in-flight and processed.
        """
        with self._in_flight_lock:
            task = self._in_flight.pop(task_id, None)

        if task is None:
            logger.warning("nack called for unknown/non-in-flight task: %s", task_id)
            return False

        task.last_error = error
        task.retry_count += 1
        self._semaphore.release()

        if task.retry_count >= task.max_retries:
            # Send to dead-letter queue
            task.status = TaskStatus.DEAD_LETTER
            with self._dlq_lock:
                self._dlq.append(task)
            logger.warning(
                "Task %s moved to DLQ after %d retries. Error: %s",
                task_id,
                task.retry_count,
                error,
            )
        else:
            # Retry with exponential backoff
            backoff = min(
                self._base_backoff * (2 ** (task.retry_count - 1)),
                self._max_backoff,
            )
            task.status = TaskStatus.PENDING
            logger.info(
                "Task %s scheduled for retry #%d in %.1fs. Error: %s",
                task_id,
                task.retry_count,
                backoff,
                error,
            )
            # Schedule re-enqueue after backoff
            timer = threading.Timer(backoff, self._reenqueue, args=(task,))
            timer.daemon = True
            timer.start()

        return True

    def _reenqueue(self, task: TaskItem) -> None:
        """Re-enqueue a task after backoff delay."""
        if not self._shutdown.is_set():
            task.timestamp = time.time()
            self._queue.put(task)
            logger.debug("Task %s re-enqueued after backoff", task.task_id)

    def get_dlq(self) -> List[TaskItem]:
        """Return a copy of the dead-letter queue contents."""
        with self._dlq_lock:
            return list(self._dlq)

    def dlq_size(self) -> int:
        """Return the number of tasks in the dead-letter queue."""
        with self._dlq_lock:
            return len(self._dlq)

    def retry_dlq_task(self, task_id: str) -> bool:
        """Move a task from DLQ back to the main queue for retry.

        Parameters
        ----------
        task_id : str
            The DLQ task to retry.

        Returns
        -------
        bool
            True if task was found in DLQ and re-enqueued.
        """
        with self._dlq_lock:
            for i, task in enumerate(self._dlq):
                if task.task_id == task_id:
                    self._dlq.pop(i)
                    task.status = TaskStatus.PENDING
                    task.retry_count = 0
                    task.timestamp = time.time()
                    self._queue.put(task)
                    logger.info("Task %s moved from DLQ back to queue", task_id)
                    return True
        return False

    def pending_size(self) -> int:
        """Approximate number of tasks waiting in the queue."""
        return self._queue.qsize()

    def in_flight_count(self) -> int:
        """Number of tasks currently being processed."""
        with self._in_flight_lock:
            return len(self._in_flight)

    def shutdown(self) -> None:
        """Gracefully shut down the queue. No new tasks accepted."""
        self._shutdown.set()
        logger.info("PriorityTaskQueue shutdown initiated")

    @property
    def is_shutdown(self) -> bool:
        """Whether the queue has been shut down."""
        return self._shutdown.is_set()

# Alias for import compatibility
TaskQueue = PriorityTaskQueue
