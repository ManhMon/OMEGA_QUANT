"""Resource Manager with budget enforcement, adaptive batching, and throttling.

Spec Section 13 (Infrastructure) - Resource management for OMEGA_QUANT.
Enforces RAM/CPU limits, adapts batch sizes based on load, and throttles
task submission when resources are constrained.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ResourceType(str, Enum):
    """Supported resource types."""

    RAM_MB = "RAM_MB"
    CPU_PERCENT = "CPU_PERCENT"
    WORKERS = "WORKERS"
    CONNECTIONS = "CONNECTIONS"


class ThrottleLevel(str, Enum):
    """Throttle severity levels."""

    NONE = "NONE"
    LIGHT = "LIGHT"       # 75-85% usage - reduce batch size
    MODERATE = "MODERATE"  # 85-95% usage - pause new tasks
    CRITICAL = "CRITICAL"  # >95% usage - emergency stop


@dataclass
class ResourceBudget:
    """Budget definition for a single resource type."""

    resource_type: ResourceType
    total: float
    allocated: float = 0.0
    reserved: float = 0.0  # Reserved for system overhead

    @property
    def available(self) -> float:
        """Available capacity after allocation and reservation."""
        return max(0.0, self.total - self.allocated - self.reserved)

    @property
    def usage_ratio(self) -> float:
        """Current usage as a ratio [0.0, 1.0]."""
        effective_total = self.total - self.reserved
        if effective_total <= 0:
            return 1.0
        return min(1.0, self.allocated / effective_total)


@dataclass
class ResourceSnapshot:
    """Point-in-time snapshot of resource usage."""

    timestamp: float = field(default_factory=time.time)
    budgets: Dict[str, Dict[str, float]] = field(default_factory=dict)
    throttle_level: str = ThrottleLevel.NONE.value
    recommended_batch_size: int = 1


class ResourceManager:
    """Resource manager with budget enforcement and adaptive batching.

    Parameters
    ----------
    budgets : dict, optional
        Initial resource budgets. Keys are ResourceType values,
        values are dicts with 'total' and optional 'reserved'.
    throttle_thresholds : dict, optional
        Thresholds for throttle levels. Keys: 'light', 'moderate', 'critical'.
    default_batch_size : int
        Default batch size when no throttling is active.
    min_batch_size : int
        Minimum batch size under throttling.
    """

    def __init__(
        self,
        budgets: Optional[Dict[str, Dict[str, float]]] = None,
        throttle_thresholds: Optional[Dict[str, float]] = None,
        default_batch_size: int = 10,
        min_batch_size: int = 1,
    ) -> None:
        self._budgets: Dict[ResourceType, ResourceBudget] = {}
        self._lock = threading.Lock()
        self._default_batch_size = default_batch_size
        self._min_batch_size = min_batch_size

        # Throttle thresholds (usage ratio)
        self._thresholds = throttle_thresholds or {
            "light": 0.75,
            "moderate": 0.85,
            "critical": 0.95,
        }

        # Current throttle state
        self._throttle_level = ThrottleLevel.NONE
        self._throttle_lock = threading.Lock()

        # Throttle event - blocks when critical
        self._throttle_gate = threading.Event()
        self._throttle_gate.set()  # Open by default

        # Initialize budgets
        if budgets:
            for resource_key, config in budgets.items():
                resource_type = ResourceType(resource_key)
                self._budgets[resource_type] = ResourceBudget(
                    resource_type=resource_type,
                    total=config.get("total", 0.0),
                    reserved=config.get("reserved", 0.0),
                )

        # Default budgets if none provided
        if not self._budgets:
            self._budgets = {
                ResourceType.RAM_MB: ResourceBudget(
                    resource_type=ResourceType.RAM_MB,
                    total=4096.0,  # 4GB default per Spec Section 13
                    reserved=512.0,
                ),
                ResourceType.CPU_PERCENT: ResourceBudget(
                    resource_type=ResourceType.CPU_PERCENT,
                    total=100.0,
                    reserved=10.0,
                ),
                ResourceType.WORKERS: ResourceBudget(
                    resource_type=ResourceType.WORKERS,
                    total=4.0,
                    reserved=0.0,
                ),
            }

        logger.info(
            "ResourceManager initialized with %d resource types", len(self._budgets)
        )

    def acquire(
        self,
        resource_type: str,
        amount: float,
        blocking: bool = True,
        timeout: Optional[float] = None,
    ) -> bool:
        """Acquire a resource allocation.

        Parameters
        ----------
        resource_type : str
            The resource type to acquire (e.g., 'RAM_MB', 'CPU_PERCENT').
        amount : float
            Amount to allocate.
        blocking : bool
            If True, wait for resource availability when throttled.
        timeout : float, optional
            Maximum seconds to wait if blocking.

        Returns
        -------
        bool
            True if resource was successfully acquired.
        """
        rt = ResourceType(resource_type)

        # Wait if critically throttled
        if blocking and self._throttle_level == ThrottleLevel.CRITICAL:
            if not self._throttle_gate.wait(timeout=timeout):
                logger.warning(
                    "Resource acquire timed out (critical throttle): %s %.1f",
                    resource_type,
                    amount,
                )
                return False

        with self._lock:
            budget = self._budgets.get(rt)
            if budget is None:
                logger.error("Unknown resource type: %s", resource_type)
                return False

            if amount > budget.available:
                logger.warning(
                    "Resource %s: requested %.1f but only %.1f available",
                    resource_type,
                    amount,
                    budget.available,
                )
                return False

            budget.allocated += amount
            logger.debug(
                "Acquired %.1f %s (usage: %.1f%%)",
                amount,
                resource_type,
                budget.usage_ratio * 100,
            )

        # Update throttle level
        self._update_throttle()
        return True

    def release(self, resource_type: str, amount: float) -> bool:
        """Release a previously acquired resource allocation.

        Parameters
        ----------
        resource_type : str
            The resource type to release.
        amount : float
            Amount to release.

        Returns
        -------
        bool
            True if resource was successfully released.
        """
        rt = ResourceType(resource_type)

        with self._lock:
            budget = self._budgets.get(rt)
            if budget is None:
                logger.error("Unknown resource type: %s", resource_type)
                return False

            budget.allocated = max(0.0, budget.allocated - amount)
            logger.debug(
                "Released %.1f %s (usage: %.1f%%)",
                amount,
                resource_type,
                budget.usage_ratio * 100,
            )

        # Update throttle level
        self._update_throttle()
        return True

    def get_usage(self) -> ResourceSnapshot:
        """Get current resource usage snapshot.

        Returns
        -------
        ResourceSnapshot
            Current state of all resources.
        """
        with self._lock:
            budgets_data = {}
            for rt, budget in self._budgets.items():
                budgets_data[rt.value] = {
                    "total": budget.total,
                    "allocated": budget.allocated,
                    "reserved": budget.reserved,
                    "available": budget.available,
                    "usage_ratio": budget.usage_ratio,
                }

        return ResourceSnapshot(
            budgets=budgets_data,
            throttle_level=self._throttle_level.value,
            recommended_batch_size=self.get_recommended_batch_size(),
        )

    def get_recommended_batch_size(self) -> int:
        """Calculate recommended batch size based on current resource pressure.

        Returns
        -------
        int
            Recommended batch size (adaptive).
        """
        with self._throttle_lock:
            level = self._throttle_level

        if level == ThrottleLevel.NONE:
            return self._default_batch_size
        elif level == ThrottleLevel.LIGHT:
            # Reduce by 50%
            return max(self._min_batch_size, self._default_batch_size // 2)
        elif level == ThrottleLevel.MODERATE:
            # Reduce by 75%
            return max(self._min_batch_size, self._default_batch_size // 4)
        else:
            # Critical - minimum
            return self._min_batch_size

    def _update_throttle(self) -> None:
        """Recalculate throttle level based on current resource usage."""
        max_usage = 0.0
        with self._lock:
            for budget in self._budgets.values():
                max_usage = max(max_usage, budget.usage_ratio)

        with self._throttle_lock:
            old_level = self._throttle_level

            if max_usage >= self._thresholds["critical"]:
                self._throttle_level = ThrottleLevel.CRITICAL
                self._throttle_gate.clear()  # Block new acquisitions
            elif max_usage >= self._thresholds["moderate"]:
                self._throttle_level = ThrottleLevel.MODERATE
                self._throttle_gate.set()
            elif max_usage >= self._thresholds["light"]:
                self._throttle_level = ThrottleLevel.LIGHT
                self._throttle_gate.set()
            else:
                self._throttle_level = ThrottleLevel.NONE
                self._throttle_gate.set()

            if self._throttle_level != old_level:
                logger.info(
                    "Throttle level changed: %s -> %s (max_usage=%.1f%%)",
                    old_level.value,
                    self._throttle_level.value,
                    max_usage * 100,
                )

    @property
    def throttle_level(self) -> ThrottleLevel:
        """Current throttle level."""
        with self._throttle_lock:
            return self._throttle_level

    def set_budget(
        self, resource_type: str, total: float, reserved: float = 0.0
    ) -> None:
        """Set or update a resource budget.

        Parameters
        ----------
        resource_type : str
            The resource type.
        total : float
            Total capacity.
        reserved : float
            Amount reserved for system overhead.
        """
        rt = ResourceType(resource_type)
        with self._lock:
            if rt in self._budgets:
                self._budgets[rt].total = total
                self._budgets[rt].reserved = reserved
            else:
                self._budgets[rt] = ResourceBudget(
                    resource_type=rt, total=total, reserved=reserved
                )
        self._update_throttle()
        logger.info("Budget updated: %s total=%.1f reserved=%.1f", resource_type, total, reserved)

    def reset(self) -> None:
        """Reset all allocations to zero."""
        with self._lock:
            for budget in self._budgets.values():
                budget.allocated = 0.0
        self._update_throttle()
        logger.info("All resource allocations reset")


def compute_safe_workers(
    max_fraction_cpu: float = 0.75,
    min_ram_mb_per_worker: float = 512.0,
    hard_cap: int = 16,
) -> int:
    """Return a safe default worker count based on CPU and available RAM.

    Caps workers to avoid OOM or CPU saturation on shared machines.

    Parameters
    ----------
    max_fraction_cpu : float
        Fraction of logical CPUs to use (default 75 %).
    min_ram_mb_per_worker : float
        Minimum RAM in MB reserved per worker (default 512 MB).
    hard_cap : int
        Absolute upper bound regardless of hardware (default 16).

    Returns
    -------
    int
        Safe worker count >= 1.
    """
    import os

    cpu_count = os.cpu_count() or 2
    cpu_workers = max(1, int(cpu_count * max_fraction_cpu))

    ram_workers = cpu_workers  # fallback if psutil unavailable
    try:
        import psutil  # type: ignore

        available_mb = psutil.virtual_memory().available / (1024 * 1024)
        ram_workers = max(1, int(available_mb / min_ram_mb_per_worker))
    except ImportError:
        pass

    workers = min(cpu_workers, ram_workers, hard_cap)
    return max(1, workers)
