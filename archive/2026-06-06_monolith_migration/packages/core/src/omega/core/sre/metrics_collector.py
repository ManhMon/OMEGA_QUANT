"""
OMEGA_QUANT SRE Metrics Collector
===================================
Vectorized counter, gauge, and histogram metric types.
Tracks transaction latency (Alpha -> Risk -> Execution) and
execution metrics (slippage in bps, fill rate).

Author: DevOps Engineer (Role 11)
Date: 2026-05-20
Version: 1.0.0
Phase: 7.1 SRE Foundation
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Metric types
# ---------------------------------------------------------------------------

@dataclass
class Counter:
    """Monotonically increasing counter backed by a numpy scalar."""
    name: str
    description: str = ""
    _value: np.float64 = field(default_factory=lambda: np.float64(0.0), init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.RLock, init=False, repr=False)

    def inc(self, amount: float = 1.0) -> None:
        """Increment counter by *amount* (must be >= 0)."""
        if amount < 0:
            raise ValueError("Counter increment must be non-negative.")
        with self._lock:
            self._value = np.float64(self._value + np.float64(amount))

    @property
    def value(self) -> float:
        with self._lock:
            return float(self._value)

    def reset(self) -> None:
        with self._lock:
            self._value = np.float64(0.0)


@dataclass
class Gauge:
    """Arbitrary up/down gauge backed by a numpy scalar."""
    name: str
    description: str = ""
    _value: np.float64 = field(default_factory=lambda: np.float64(0.0), init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.RLock, init=False, repr=False)

    def set(self, value: float) -> None:
        with self._lock:
            self._value = np.float64(value)

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value = np.float64(self._value + np.float64(amount))

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value = np.float64(self._value - np.float64(amount))

    @property
    def value(self) -> float:
        with self._lock:
            return float(self._value)


@dataclass
class Histogram:
    """
    Fixed-bucket histogram backed by numpy arrays.

    All arithmetic (bucket counts, sum, percentiles) is fully vectorized —
    no Python-level loops in the hot path.
    """
    name: str
    description: str = ""
    buckets: List[float] = field(default_factory=lambda: [
        0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0
    ])

    # Internal numpy state — initialised in __post_init__
    _bucket_bounds: np.ndarray = field(init=False, repr=False)
    _bucket_counts: np.ndarray = field(init=False, repr=False)
    _observations: List[float] = field(default_factory=list, init=False, repr=False)
    _sum: np.float64 = field(default_factory=lambda: np.float64(0.0), init=False, repr=False)
    _count: np.int64 = field(default_factory=lambda: np.int64(0), init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        bounds = sorted(self.buckets)
        self._bucket_bounds = np.array(bounds, dtype=np.float64)
        self._bucket_counts = np.zeros(len(bounds), dtype=np.int64)

    def observe(self, value: float) -> None:
        """Record a single observation (vectorized bucket update)."""
        v = np.float64(value)
        with self._lock:
            # Vectorized: find all buckets whose upper bound >= value
            self._bucket_counts += (self._bucket_bounds >= v).astype(np.int64)
            self._sum = np.float64(self._sum + v)
            self._count = np.int64(self._count + 1)
            self._observations.append(float(v))

    @property
    def count(self) -> int:
        with self._lock:
            return int(self._count)

    @property
    def sum(self) -> float:
        with self._lock:
            return float(self._sum)

    @property
    def mean(self) -> float:
        with self._lock:
            if self._count == 0:
                return 0.0
            return float(self._sum / self._count)

    def percentile(self, p: float) -> float:
        """Return the p-th percentile (0-100) using vectorized numpy."""
        with self._lock:
            if not self._observations:
                return 0.0
            arr = np.array(self._observations, dtype=np.float64)
            return float(np.percentile(arr, p))

    def snapshot(self) -> Dict[str, object]:
        """Return a dict snapshot of current bucket state."""
        with self._lock:
            return {
                "name": self.name,
                "count": int(self._count),
                "sum": float(self._sum),
                "mean": self.mean,
                "p50": self.percentile(50),
                "p95": self.percentile(95),
                "p99": self.percentile(99),
                "buckets": {
                    str(b): int(c)
                    for b, c in zip(self._bucket_bounds.tolist(), self._bucket_counts.tolist())
                },
            }


# ---------------------------------------------------------------------------
# Latency timer context manager
# ---------------------------------------------------------------------------

class LatencyTimer:
    """
    Context manager that records elapsed wall-clock time into a Histogram.

    Usage::

        with LatencyTimer(collector.alpha_to_risk_latency_s):
            run_alpha_pipeline()
    """

    def __init__(self, histogram: Histogram) -> None:
        self._histogram = histogram
        self._start: float = 0.0

    def __enter__(self) -> "LatencyTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        elapsed = time.perf_counter() - self._start
        self._histogram.observe(elapsed)


# ---------------------------------------------------------------------------
# Central collector (singleton-friendly)
# ---------------------------------------------------------------------------

class MetricsCollector:
    """
    Central registry for all OMEGA_QUANT SRE metrics.

    Transaction latency stages
    --------------------------
    alpha_to_risk_latency_s   : seconds from Alpha signal to Risk check entry
    risk_to_exec_latency_s    : seconds from Risk approval to Execution entry
    end_to_end_latency_s      : total Alpha -> Execution round-trip

    Execution metrics
    -----------------
    slippage_bps              : realised slippage in basis points (histogram)
    fill_rate                 : fraction of order filled 0.0-1.0 (gauge, per order)
    orders_submitted          : total orders submitted (counter)
    orders_filled             : total orders fully filled (counter)
    orders_rejected           : total orders rejected (counter)
    """

    def __init__(self) -> None:
        # --- Transaction latency ---
        self.alpha_to_risk_latency_s: Histogram = Histogram(
            name="alpha_to_risk_latency_s",
            description="Latency from Alpha signal generation to Risk check entry (seconds)",
        )
        self.risk_to_exec_latency_s: Histogram = Histogram(
            name="risk_to_exec_latency_s",
            description="Latency from Risk approval to Execution entry (seconds)",
        )
        self.end_to_end_latency_s: Histogram = Histogram(
            name="end_to_end_latency_s",
            description="End-to-end Alpha -> Execution latency (seconds)",
        )

        # --- Execution metrics ---
        self.slippage_bps: Histogram = Histogram(
            name="slippage_bps",
            description="Realised slippage in basis points",
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0],
        )
        self.fill_rate: Gauge = Gauge(
            name="fill_rate",
            description="Last observed order fill rate (0.0 – 1.0)",
        )
        self.orders_submitted: Counter = Counter(
            name="orders_submitted",
            description="Total orders submitted to execution venue",
        )
        self.orders_filled: Counter = Counter(
            name="orders_filled",
            description="Total orders fully filled",
        )
        self.orders_rejected: Counter = Counter(
            name="orders_rejected",
            description="Total orders rejected by venue or risk",
        )

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def record_slippage(self, slippage_bps: float) -> None:
        """Record a single slippage observation in basis points."""
        self.slippage_bps.observe(slippage_bps)

    def record_fill(self, filled_qty: float, total_qty: float) -> None:
        """
        Record fill outcome for one order.

        Args:
            filled_qty: Quantity actually filled.
            total_qty:  Total quantity submitted.
        """
        if total_qty <= 0:
            raise ValueError("total_qty must be positive.")
        rate = np.float64(filled_qty) / np.float64(total_qty)
        self.fill_rate.set(float(np.clip(rate, np.float64(0.0), np.float64(1.0))))
        self.orders_submitted.inc()
        if float(rate) >= 1.0:
            self.orders_filled.inc()

    def snapshot(self) -> Dict[str, object]:
        """Return a full metrics snapshot dict."""
        return {
            "alpha_to_risk_latency_s": self.alpha_to_risk_latency_s.snapshot(),
            "risk_to_exec_latency_s": self.risk_to_exec_latency_s.snapshot(),
            "end_to_end_latency_s": self.end_to_end_latency_s.snapshot(),
            "slippage_bps": self.slippage_bps.snapshot(),
            "fill_rate": self.fill_rate.value,
            "orders_submitted": self.orders_submitted.value,
            "orders_filled": self.orders_filled.value,
            "orders_rejected": self.orders_rejected.value,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_collector: Optional[MetricsCollector] = None
_collector_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    """Return the process-wide MetricsCollector singleton."""
    global _collector
    if _collector is None:
        with _collector_lock:
            if _collector is None:
                _collector = MetricsCollector()
    return _collector
