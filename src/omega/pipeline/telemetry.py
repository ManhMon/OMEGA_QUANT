"""Bounded, local-only W7 telemetry; no exporter I/O in decision cycles."""

from collections import Counter, deque
import math
from threading import Lock

import psutil

STAGES = ("baseline", "forensics", "regime", "black_litterman", "execution", "concentration", "decay", "publication")
OUTCOMES = ("baseline", "proposal", "fallback", "rejected", "uncommitted", "replay")
REASONS = ("disabled", "success", "missing", "invalid", "deadline", "resource", "advisory_error", "risk", "storage", "integrity", "duplicate")
BUCKETS = (.01, .05, .1, .25, .5, 1., 2.)


def get_telemetry_version() -> str:
    return "w7/v1"


def process_tree_rss() -> int:
    process = psutil.Process()
    children = process.children(recursive=True)
    if len(children) > 64:
        raise ValueError("process tree exceeds bound")
    total = process.memory_info().rss
    for child in children:
        try:
            total += child.memory_info().rss
        except psutil.NoSuchProcess:
            pass
    return total


class Telemetry:
    def __init__(self, window: int = 256):
        if type(window) is not int or not 1 <= window <= 256:
            raise ValueError("invalid telemetry window")
        self._samples = deque(maxlen=window)
        self._counts = Counter()
        self._buckets = [0] * (len(BUCKETS) + 1)
        self._maxima = {"cycle_seconds": 0., "rss_bytes": 0, "cache_bytes": 0}
        self._stage_maxima = dict.fromkeys(STAGES, 0.)
        self._lock = Lock()

    def record(self, *, outcome: str, reason: str, seconds: float, rss_bytes: int,
               cache_bytes: int, stages: dict[str, float]) -> None:
        if (outcome not in OUTCOMES or reason not in REASONS or
                type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0 or
                any(type(v) is not int or v < 0 for v in (rss_bytes, cache_bytes)) or
                type(stages) is not dict or not set(stages) <= set(STAGES) or
                any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in stages.values())):
            raise ValueError("invalid telemetry sample")
        with self._lock:
            self._samples.append(float(seconds))
            self._counts[(outcome, reason)] += 1
            for i, bound in enumerate((*BUCKETS, math.inf)):
                if seconds <= bound:
                    self._buckets[i] += 1
            for key, value in (("cycle_seconds", seconds), ("rss_bytes", rss_bytes), ("cache_bytes", cache_bytes)):
                self._maxima[key] = max(self._maxima[key], value)
            for stage, value in stages.items():
                self._stage_maxima[stage] = max(self._stage_maxima[stage], value)

    def snapshot(self) -> dict:
        with self._lock:
            samples = sorted(self._samples)
            percentile = lambda p: samples[max(0, math.ceil(p * len(samples)) - 1)] if samples else None
            return {"schema_version": "w7/v1", "samples_retained": len(samples),
                    "cycles": sum(self._counts.values()), "maxima": dict(self._maxima),
                    "p50_seconds": percentile(.5), "p95_seconds": percentile(.95), "p99_seconds": percentile(.99),
                    "stage_max_seconds": dict(self._stage_maxima),
                    "outcomes": [{"outcome": k[0], "reason": k[1], "count": v} for k, v in sorted(self._counts.items())],
                    "bucket_counts": list(self._buckets), "broker_calls": 0, "provider_calls": 0,
                    "training_calls": 0, "promotion_calls": 0}

    def prometheus(self) -> str:
        snap = self.snapshot()
        lines = [f'omega_shadow_{key}_max {value}' for key, value in snap["maxima"].items()]
        lines.extend(f'omega_shadow_cycles_total{{outcome="{r["outcome"]}",reason="{r["reason"]}"}} {r["count"]}'
                     for r in snap["outcomes"])
        lines.extend(f'omega_shadow_cycle_seconds_bucket{{le="{bound}"}} {count}'
                     for bound, count in zip((*BUCKETS, "+Inf"), snap["bucket_counts"]))
        return "\n".join(lines) + "\n"
