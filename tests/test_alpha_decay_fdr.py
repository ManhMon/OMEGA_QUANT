from __future__ import annotations

from datetime import time
import time as wall_time

import numpy as np
import pytest

from omega.observability.alpha_decay_fdr import AlphaDecayMonitorFDR
from omega.observability.resource_scaler import DynamicResourceScaler
from omega.quant.accelerated_ops import decay_linear, ts_mean, ts_std
from omega.quant.walk_forward.risk_adjusted_alpha_score import bh_fdr_qvalues


def test_alpha_decay_monitor_uses_left_tailed_decay_rule_only_when_recent_mean_is_worse():
    monitor = AlphaDecayMonitorFDR(q_threshold=0.05, min_samples=5)

    results = monitor.evaluate_pool(
        recent_ic_by_alpha={
            "decayed": [0.01, 0.02, 0.015, 0.005, 0.01, 0.0, 0.012, 0.008],
            "improved": [0.12, 0.11, 0.13, 0.10, 0.12, 0.11, 0.14, 0.12],
        },
        baseline_ic_by_alpha={"decayed": 0.08, "improved": 0.08},
    )

    by_name = {row.alpha_name: row for row in results}
    assert by_name["decayed"].recent_mean_ic < by_name["decayed"].baseline_ic
    assert by_name["decayed"].p_value < 0.05
    assert by_name["decayed"].is_decayed is True

    assert by_name["improved"].recent_mean_ic > by_name["improved"].baseline_ic
    assert by_name["improved"].p_value == 1.0
    assert by_name["improved"].is_decayed is False


def test_alpha_decay_monitor_applies_bh_fdr_across_pool():
    monitor = AlphaDecayMonitorFDR(q_threshold=0.05, min_samples=5)
    recent = {
        "alpha_a": [0.005, 0.01, 0.0, 0.015, 0.01, 0.005, 0.012, 0.008],
        "alpha_b": [0.03, 0.025, 0.035, 0.02, 0.03, 0.028, 0.031, 0.029],
        "alpha_c": [0.079, 0.081, 0.08, 0.082, 0.078, 0.08, 0.081, 0.079],
    }
    baseline = {name: 0.08 for name in recent}

    results = monitor.evaluate_pool(recent, baseline)
    expected_q = bh_fdr_qvalues([row.p_value for row in results])

    assert [pytest.approx(row.q_value) for row in results] == expected_q
    assert [row.is_decayed for row in results] == [True, True, False]


def test_dynamic_resource_scaler_boundaries_are_non_overlapping_and_inclusive():
    scaler = DynamicResourceScaler(cpus_pct=0.85, memory_pct=0.85, total_cpus=16, total_memory_bytes=64 * 1024 ** 3)

    before_open = scaler.get_limits(time(8, 29, 59))
    at_open = scaler.get_limits(time(8, 30, 0))
    at_close = scaler.get_limits(time(15, 30, 0))
    after_close = scaler.get_limits(time(15, 30, 1))

    assert before_open.mode == "off_hours"
    assert before_open.cpu_limit == 13.6
    assert before_open.memory_limit == "54g"

    assert at_open.mode == "market"
    assert at_open.cpu_limit == 2.0
    assert at_open.memory_limit == "4g"

    assert at_close.mode == "market"
    assert at_close.cpu_limit == 2.0
    assert at_close.memory_limit == "4g"

    assert after_close.mode == "off_hours"
    assert after_close.cpu_limit == 13.6
    assert after_close.memory_limit == "54g"


def _python_ts_mean(x: np.ndarray, window: int) -> np.ndarray:
    out = np.zeros(x.shape[0], dtype=np.float64)
    for i in range(window - 1, x.shape[0]):
        window_slice = x[i - window + 1 : i + 1]
        if np.isnan(window_slice).any():
            continue
        out[i] = float(window_slice.mean())
    return out


def _python_ts_std(x: np.ndarray, window: int) -> np.ndarray:
    out = np.zeros(x.shape[0], dtype=np.float64)
    for i in range(window - 1, x.shape[0]):
        window_slice = x[i - window + 1 : i + 1]
        if np.isnan(window_slice).any():
            continue
        out[i] = float(window_slice.std(ddof=1))
    return out


def _python_decay_linear(x: np.ndarray, window: int) -> np.ndarray:
    out = np.zeros(x.shape[0], dtype=np.float64)
    weights = np.arange(1, window + 1, dtype=np.float64)
    weight_sum = weights.sum()
    for i in range(window - 1, x.shape[0]):
        window_slice = x[i - window + 1 : i + 1]
        if np.isnan(window_slice).any():
            continue
        out[i] = float(np.dot(window_slice, weights) / weight_sum)
    return out


def test_jit_ops_match_reference_and_deliver_10x_speedup():
    small = np.array([1.0, 2.0, 3.0, np.nan, 5.0, 6.0, 7.0], dtype=np.float64)
    window = 3

    np.testing.assert_allclose(ts_mean(small, window), _python_ts_mean(small, window), equal_nan=True)
    np.testing.assert_allclose(ts_std(small, window), _python_ts_std(small, window), equal_nan=True)
    np.testing.assert_allclose(decay_linear(small, window), _python_decay_linear(small, window), equal_nan=True)

    large = np.linspace(1.0, 200000.0, 200000, dtype=np.float64)
    perf_window = 20

    ts_mean(large, perf_window)
    ts_std(large, perf_window)
    decay_linear(large, perf_window)

    start = wall_time.perf_counter()
    expected_mean = _python_ts_mean(large, perf_window)
    expected_std = _python_ts_std(large, perf_window)
    expected_decay = _python_decay_linear(large, perf_window)
    python_elapsed = wall_time.perf_counter() - start

    start = wall_time.perf_counter()
    actual_mean = ts_mean(large, perf_window)
    actual_std = ts_std(large, perf_window)
    actual_decay = decay_linear(large, perf_window)
    jit_elapsed = wall_time.perf_counter() - start

    np.testing.assert_allclose(actual_mean, expected_mean)
    np.testing.assert_allclose(actual_std, expected_std, atol=1e-10)
    np.testing.assert_allclose(actual_decay, expected_decay)
    assert python_elapsed / jit_elapsed >= 10.0
