from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import os

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


MARKET_OPEN = time(8, 30, 0)
MARKET_CLOSE = time(15, 30, 0)
GIB = 1024 ** 3


@dataclass(frozen=True)
class ResourceLimits:
    cpu_limit: float
    memory_limit: str
    mode: str


class DynamicResourceScaler:
    def __init__(
        self,
        cpus_pct: float = 0.85,
        memory_pct: float = 0.85,
        *,
        total_cpus: int | None = None,
        total_memory_bytes: int | None = None,
    ):
        self.cpus_pct = float(cpus_pct)
        self.memory_pct = float(memory_pct)
        self._total_cpus = total_cpus
        self._total_memory_bytes = total_memory_bytes

    def get_limits(self, current_time: datetime | time | None = None) -> ResourceLimits:
        current = self._normalize_time(current_time)
        if MARKET_OPEN <= current <= MARKET_CLOSE:
            return ResourceLimits(cpu_limit=2.0, memory_limit="4g", mode="market")

        total_cpus = self._physical_cpu_count()
        total_memory_bytes = self._physical_memory_bytes()
        cpu_limit = max(1.0, round(total_cpus * self.cpus_pct, 2))
        memory_gb = max(1, int((total_memory_bytes * self.memory_pct) // GIB))
        return ResourceLimits(cpu_limit=cpu_limit, memory_limit=f"{memory_gb}g", mode="off_hours")

    def _physical_cpu_count(self) -> int:
        if self._total_cpus is not None:
            return max(1, int(self._total_cpus))
        return max(1, int(os.cpu_count() or 1))

    def _physical_memory_bytes(self) -> int:
        if self._total_memory_bytes is not None:
            return max(GIB, int(self._total_memory_bytes))
        if psutil is not None:
            return max(GIB, int(psutil.virtual_memory().total))
        return 4 * GIB

    @staticmethod
    def _normalize_time(current_time: datetime | time | None) -> time:
        if current_time is None:
            return datetime.now().time().replace(microsecond=0)
        if isinstance(current_time, datetime):
            return current_time.time().replace(microsecond=0)
        return current_time.replace(microsecond=0)
