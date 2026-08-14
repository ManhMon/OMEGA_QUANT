#!/usr/bin/env python3
"""Repeatable wall-clock and RSS benchmark for a Python script."""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import psutil

REPO_ROOT = Path(__file__).resolve().parents[1]

def measure_imports():
    sys.path.insert(0, str(REPO_ROOT / "src"))
    # Cold import measurement
    t0 = time.perf_counter()
    import omega.quant.ultimate_alpha_arsenal as uaa
    t1 = time.perf_counter()
    cold_time = t1 - t0
    
    # Warm import
    t0 = time.perf_counter()
    import omega.quant.ultimate_alpha_arsenal as uaa2
    t1 = time.perf_counter()
    warm_time = t1 - t0
    
    print(f"COLD_IMPORT_TIME: {cold_time:.4f}s")
    print(f"WARM_IMPORT_TIME: {warm_time:.4f}s")


def _process_tree_rss(process: psutil.Process) -> int:
    rss = 0
    for candidate in [process, *process.children(recursive=True)]:
        try:
            rss += candidate.memory_info().rss
        except psutil.Error:
            continue
    return rss


def measure_script(script: str, script_args: list[str], warmup: int, runs: int, output_dir: Path | None = None) -> dict:
    if warmup != 1 or runs != 3:
        raise ValueError("Gate 1 requires exactly 1 warm-up and 3 measured runs")
    command = [sys.executable, str(REPO_ROOT / script), *script_args]
    samples = []
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
    for index in range(warmup + runs):
        started = time.perf_counter()
        process = subprocess.Popen(command, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        peak_rss = 0
        ps_process = psutil.Process(process.pid)
        while process.poll() is None:
            try:
                peak_rss = max(peak_rss, _process_tree_rss(ps_process))
            except psutil.Error:
                break
            time.sleep(0.01)
        output, _ = process.communicate()
        elapsed = time.perf_counter() - started
        if output_dir:
            (output_dir / f"run_{index + 1:02d}.log").write_text(output, encoding="utf-8")
        if process.returncode:
            raise RuntimeError(f"run {index + 1} failed ({process.returncode})\n{output}")
        if index >= warmup:
            samples.append({"run": index, "wall_clock_seconds": elapsed, "max_rss_mb": peak_rss / (1024 * 1024)})
    wall_times = [sample["wall_clock_seconds"] for sample in samples]
    rss_values = [sample["max_rss_mb"] for sample in samples]
    return {
        "command": command,
        "workload": "full script execution",
        "warmup_runs": warmup,
        "measured_runs": samples,
        "median_wall_clock_seconds": statistics.median(wall_times),
        "max_rss_mb": max(rss_values),
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", help="Repo-relative Python script to benchmark")
    parser.add_argument("script_args", nargs=argparse.REMAINDER)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path, help="Directory for per-run stdout logs")
    args = parser.parse_args()
    if not args.script:
        measure_imports()
    else:
        script_args = args.script_args[1:] if args.script_args[:1] == ["--"] else args.script_args
        result = measure_script(args.script, script_args, args.warmup, args.runs, args.output_dir)
        print(json.dumps(result, indent=2))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
