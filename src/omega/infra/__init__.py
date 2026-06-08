"""OMEGA_QUANT Infrastructure Module.

Spec Section 13 (Infrastructure) - Core infrastructure components:
- PriorityTaskQueue: Priority queue with DLQ and retry logic
- WorkerPool: Thread-based worker pool with lifecycle and crash recovery
- ResourceManager: Resource budget enforcement and adaptive batching
"""

from omega.infra.task_queue import (
    PriorityTaskQueue,
    TaskItem,
    TaskPriority,
    TaskStatus,
)
from omega.infra.worker_pool import (
    TaskResult,
    WorkerInfo,
    WorkerPool,
    WorkerState,
)
from omega.infra.resource_manager import (
    ResourceBudget,
    ResourceManager,
    ResourceSnapshot,
    ResourceType,
    ThrottleLevel,
)

__all__ = [
    # task_queue
    "PriorityTaskQueue",
    "TaskItem",
    "TaskPriority",
    "TaskStatus",
    # worker_pool
    "WorkerPool",
    "WorkerInfo",
    "WorkerState",
    "TaskResult",
    # resource_manager
    "ResourceManager",
    "ResourceBudget",
    "ResourceSnapshot",
    "ResourceType",
    "ThrottleLevel",
]

# Auto-wired submodules and subpackages
try:
    from . import resource_manager
except ImportError:
    pass

try:
    from . import task_queue
except ImportError:
    pass

try:
    from . import worker_pool
except ImportError:
    pass
