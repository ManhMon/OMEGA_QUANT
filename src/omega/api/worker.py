"""Executable durable worker with dynamic resource governance."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import time
from dataclasses import dataclass
from typing import Any

import psutil

from omega.api.schemas.advanced_quant import GovernorMode, ResourceGovernorPolicy
from omega.api.services.job_service import JobService, get_job_service


@dataclass(frozen=True)
class GovernorDecision:
    policy: ResourceGovernorPolicy
    reason: str
    telemetry: dict[str, float]


class DynamicWorkerResourceGovernor:
    def __init__(self, policy: ResourceGovernorPolicy) -> None:
        self.policy = policy

    def decide(self, queue_depth: int = 0) -> GovernorDecision:
        cpu_percent = float(psutil.cpu_percent(interval=None))
        memory_percent = float(psutil.virtual_memory().percent)
        process_rss = float(psutil.Process().memory_info().rss)
        effective_depth = float(max(queue_depth, 0))

        telemetry = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "process_rss": process_rss,
            "queue_depth": effective_depth,
        }
        if self.policy.mode == GovernorMode.MANUAL:
            return GovernorDecision(self.policy, "manual policy", telemetry)

        cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1
        available_fraction = max(0.0, (1 - cpu_percent / 100)) * max(0.0, (1 - memory_percent / 100))
        telemetry_capacity = max(1, min(cpu_count * 2, round(cpu_count * available_fraction)))
        desired = max(1, min(int(effective_depth), telemetry_capacity))

        concurrency = self.policy.target_concurrency
        if desired < concurrency:
            concurrency = max(1, concurrency - 1)
            reason = "live telemetry capacity decreased"
        elif desired > concurrency:
            concurrency = min(cpu_count * 2, concurrency + 1)
            reason = "queue pressure fits live telemetry capacity"
        else:
            reason = "hysteresis hold"

        # Bounds check chunk / batch size
        bounded_batch = max(1, min(self.policy.batch_size, 1000))
        bounded_threads = max(1, min(self.policy.thread_pool_size, cpu_count * 4))

        policy = self.policy.model_copy(
            update={
                "target_concurrency": concurrency,
                "batch_size": bounded_batch,
                "thread_pool_size": bounded_threads,
                "version": self.policy.version + int(concurrency != self.policy.target_concurrency),
            }
        )
        self.policy = policy
        return GovernorDecision(policy, reason, telemetry)


def policy_from_environment() -> ResourceGovernorPolicy:
    mode = GovernorMode(os.environ.get("OMEGA_WORKER_GOVERNOR_MODE", "COPILOT").upper())
    cpu_count = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1
    return ResourceGovernorPolicy(
        mode=mode,
        target_concurrency=int(os.environ.get("OMEGA_WORKER_CONCURRENCY", cpu_count)),
        thread_pool_size=int(os.environ.get("OMEGA_WORKER_THREAD_POOL_SIZE", cpu_count)),
        batch_size=int(os.environ.get("OMEGA_WORKER_BATCH_SIZE", max(cpu_count, 1))),
    )


def execute_job(job: dict[str, Any]) -> dict[str, Any]:
    task_type = job.get("task_type", "")
    if task_type in {"noop", "sample", "test", "health_probe"}:
        return {"status": "success", "echo": job.get("payload", {})}
    raise RuntimeError(f"No real handler registered for task type {task_type}")


def run_worker(service: JobService | None = None, once: bool = False) -> int:
    service = service or get_job_service()
    governor = DynamicWorkerResourceGovernor(policy_from_environment())
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    draining = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal draining
        draining = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    service.recover_stale()

    exit_code = 0
    while not draining:
        # Calculate real queue depth for telemetry input
        queue_depth = 0
        try:
            with service._connect() as db:
                row = db.execute("SELECT COUNT(*) as count FROM omega_jobs WHERE status='QUEUED'").fetchone()
                if row:
                    queue_depth = int(row["count"])
        except Exception:
            queue_depth = 0

        governor.decide(queue_depth=queue_depth)
        job = service.claim(worker_id)
        if job is None:
            if once:
                return 0
            time.sleep(1)
            continue
        if job["cancellation_requested_at"]:
            service.acknowledge_cancellation(job["job_id"], worker_id)
            if once:
                return 0
            continue
        try:
            result = execute_job(job)
            service.complete(job["job_id"], worker_id, result)
        except Exception as error:
            service.fail(job["job_id"], worker_id, "UNSUPPORTED_TASK_TYPE", str(error))
            if once:
                return 1
        if once:
            return 0
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OMEGA Durable Worker")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    
    args, unknown = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    if unknown:
        sys.stderr.write(f"Unknown arguments: {unknown}\n")
        return 2

    run_once = args.once or (os.environ.get("OMEGA_WORKER_ONCE") == "1")
    return run_worker(once=run_once)


if __name__ == "__main__":
    raise SystemExit(main())
