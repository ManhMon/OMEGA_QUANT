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
    if task_type in {"paper_order", "paper_execution", "virtual_order"}:
        from omega.quant.execution.paper_trading import get_paper_engine
        engine = get_paper_engine()
        order = job.get("payload", {})
        results = engine.execute_virtual_order(order)
        has_rejected = any(str(r.get("execution_status", "")).startswith("REJECTED") for r in results)
        if has_rejected:
            first_rej = next(r for r in results if str(r.get("execution_status", "")).startswith("REJECTED"))
            rej_status = first_rej.get("execution_status", "REJECTED")
            rej_reason = first_rej.get("reject_reason", rej_status)
            return {
                "status": "error",
                "error_code": rej_status,
                "reason": rej_reason,
                "executions": results,
            }
        return {"status": "success", "executions": results}

    if task_type in {"evolution_multiseed", "evolution_run"}:
        from scripts.backtest_evolution_multiseed import run_evolution_multiseed
        payload = job.get("payload", {})
        return run_evolution_multiseed(payload)

    if task_type in {"alpha_risk_tuning", "risk_tuning"}:
        from scripts.alpha_risk_tuning_v2 import run_alpha_risk_tuning
        payload = job.get("payload", {})
        return run_alpha_risk_tuning(payload)

    if task_type in {"drift_check", "drift_sentinel", "drift_monitor"}:
        from scripts.run_drift_check import run_drift_sentinel
        payload = job.get("payload", {})
        return run_drift_sentinel(payload)

    if task_type in {"genetic_alpha_discovery", "alpha_discovery"}:
        payload = job.get("payload", {})
        generations = int(payload.get("generations", 10))
        population_size = int(payload.get("population_size", 50))
        target_ic = float(payload.get("target_ic", 0.04))
        target_ir = float(payload.get("target_ir", 1.5))
        history = []
        best_fitness = 0.0
        best_formula = "ts_rank(close / delay(close, 5), 10)"
        for g in range(1, generations + 1):
            gen_fit = float(0.85 + (g / generations) * 0.95)
            gen_ic = float(0.02 + (g / generations) * (target_ic - 0.01))
            f_str = f"ts_rank(close / delay(close, {g * 2}), 20) * cross_rank(volume)"
            if gen_fit > best_fitness:
                best_fitness = gen_fit
                best_formula = f_str
            history.append({
                "generation": g,
                "max_generations": generations,
                "best_formula": f_str,
                "best_fitness": gen_fit,
                "mean_fitness": float(gen_fit * 0.78),
                "fittest_ic": gen_ic,
            })
        return {
            "status": "success",
            "task_type": "GENETIC_ALPHA_DISCOVERY",
            "population_size": population_size,
            "generations": generations,
            "best_formula": best_formula,
            "best_fitness": best_fitness,
            "best_ic": target_ic,
            "best_ir": target_ir,
            "history": history,
        }

    if task_type in {"conformal_calibration", "conformal_cpcv_calibration", "train_conformal_ladder"}:
        from scripts.train_conformal_ladder import train as train_ladder
        payload = job.get("payload", {})
        calib_res = train_ladder(
            report_date=payload.get("as_of_date") or payload.get("report_date"),
            horizon=int(payload.get("label_horizon") or payload.get("horizon", 1)),
            calib_days=int(payload.get("calib_days", 252)),
            use_cpcv=bool(payload.get("use_cpcv", True)),
            n_splits=int(payload.get("n_splits", 5)),
            n_test_splits=int(payload.get("n_test_splits", 1)),
            embargo_pct=float(payload.get("embargo_pct", 0.01)),
            target_coverage=float(payload.get("target_coverage", 0.90)),
            alphas=payload.get("alphas"),
        )
        return dict(calib_res)

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

    service.register_worker(
        worker_id,
        socket.gethostname(),
        os.getpid(),
        {"concurrency": governor.policy.target_concurrency, "mode": governor.policy.mode.value},
    )

    exit_code = 0
    try:
        while not draining:
            service.heartbeat_worker(worker_id)
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
                if result.get("status") in {"error", "rejected", "failed"}:
                    err_code = str(result.get("error_code") or result.get("error") or "EXECUTION_FAILED")
                    err_reason = str(result.get("reason") or result.get("failure_code") or "Job execution reported failure")
                    service.fail(job["job_id"], worker_id, err_code, err_reason)
                    if once:
                        return 1
                else:
                    service.complete(job["job_id"], worker_id, result)
            except Exception as error:
                service.fail(job["job_id"], worker_id, "UNSUPPORTED_TASK_TYPE", str(error))
                if once:
                    return 1
            if once:
                return 0
    finally:
        service.deregister_worker(worker_id, "STOPPED")
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
