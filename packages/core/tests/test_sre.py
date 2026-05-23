"""
Tests for OMEGA_QUANT SRE Foundation (Phase 7.1)
=================================================
Covers:
  - sre_logger   : JSON output, trace_id propagation, level filtering
  - metrics_collector : Counter, Gauge, Histogram, LatencyTimer, MetricsCollector
  - kill_switch  : activation, idempotency, callbacks, log flush, state dump

Author: DevOps Engineer (Role 11)
Date: 2026-05-20
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from io import StringIO
from pathlib import Path

import numpy as np
import pytest

from omega.core.sre.sre_logger import (
    get_sre_logger,
    get_trace_id,
    new_trace_id,
    set_trace_id,
)
from omega.core.sre.metrics_collector import (
    Counter,
    Gauge,
    Histogram,
    LatencyTimer,
    MetricsCollector,
    get_metrics_collector,
)
from omega.core.sre.kill_switch import (
    KillSwitch,
    get_kill_switch,
    reset_kill_switch,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _capture_logger(name: str, level: str = "DEBUG") -> tuple[logging.Logger, StringIO]:
    """Return a logger that writes JSON to an in-memory StringIO buffer."""
    buf = StringIO()
    logger = get_sre_logger(name, level=level, stream=buf)
    return logger, buf


def _last_record(buf: StringIO) -> dict:
    """Parse the last JSON line written to *buf*."""
    buf.seek(0)
    lines = [l for l in buf.read().splitlines() if l.strip()]
    assert lines, "No log records found in buffer"
    return json.loads(lines[-1])


# ===========================================================================
# sre_logger
# ===========================================================================

class TestSreLogger:

    def test_emits_json(self):
        logger, buf = _capture_logger("test.json")
        logger.info("hello world")
        rec = _last_record(buf)
        assert rec["message"] == "hello world"
        assert rec["level"] == "INFO"
        assert "timestamp" in rec
        assert "logger" in rec
        assert "trace_id" in rec

    def test_trace_id_propagation(self):
        tid = new_trace_id()
        logger, buf = _capture_logger("test.trace")
        logger.info("with trace")
        rec = _last_record(buf)
        assert rec["trace_id"] == tid

    def test_set_trace_id(self):
        set_trace_id("custom-trace-abc")
        logger, buf = _capture_logger("test.set_trace")
        logger.warning("check trace")
        rec = _last_record(buf)
        assert rec["trace_id"] == "custom-trace-abc"

    def test_get_trace_id_auto_generates(self):
        # Reset to empty so auto-generation fires
        set_trace_id("")
        tid = get_trace_id()
        assert tid != ""
        # Subsequent call returns same id
        assert get_trace_id() == tid

    def test_level_filtering_debug_suppressed(self):
        logger, buf = _capture_logger("test.filter", level="WARNING")
        logger.debug("should be suppressed")
        logger.info("also suppressed")
        logger.warning("visible")
        buf.seek(0)
        lines = [l for l in buf.read().splitlines() if l.strip()]
        assert len(lines) == 1
        assert json.loads(lines[0])["level"] == "WARNING"

    def test_all_severity_levels_emitted(self):
        logger, buf = _capture_logger("test.levels", level="DEBUG")
        for method, lvl in [
            (logger.debug, "DEBUG"),
            (logger.info, "INFO"),
            (logger.warning, "WARNING"),
            (logger.error, "ERROR"),
            (logger.critical, "CRITICAL"),
        ]:
            method(f"msg {lvl}")
        buf.seek(0)
        records = [json.loads(l) for l in buf.read().splitlines() if l.strip()]
        levels = [r["level"] for r in records]
        assert levels == ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def test_extra_fields_included(self):
        logger, buf = _capture_logger("test.extra")
        logger.info("with extra", extra={"order_id": "ORD-001", "symbol": "AAPL"})
        rec = _last_record(buf)
        assert rec["order_id"] == "ORD-001"
        assert rec["symbol"] == "AAPL"

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError, match="Unknown log level"):
            get_sre_logger("test.bad_level", level="VERBOSE")

    def test_exception_info_captured(self):
        logger, buf = _capture_logger("test.exc")
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("caught error")
        rec = _last_record(buf)
        assert "exc_info" in rec
        assert "ValueError" in rec["exc_info"]

    def test_idempotent_reconfiguration(self):
        """Calling get_sre_logger twice with same name/level returns same logger."""
        buf = StringIO()
        l1 = get_sre_logger("test.idem", level="INFO", stream=buf)
        l2 = get_sre_logger("test.idem", level="INFO", stream=buf)
        assert l1 is l2


# ===========================================================================
# Counter
# ===========================================================================

class TestCounter:

    def test_initial_value_zero(self):
        c = Counter(name="test_counter")
        assert c.value == 0.0

    def test_increment_default(self):
        c = Counter(name="c1")
        c.inc()
        assert c.value == 1.0

    def test_increment_custom_amount(self):
        c = Counter(name="c2")
        c.inc(5.5)
        assert c.value == pytest.approx(5.5)

    def test_multiple_increments(self):
        c = Counter(name="c3")
        for _ in range(100):
            c.inc(2.0)
        assert c.value == pytest.approx(200.0)

    def test_negative_increment_raises(self):
        c = Counter(name="c4")
        with pytest.raises(ValueError, match="non-negative"):
            c.inc(-1.0)

    def test_reset(self):
        c = Counter(name="c5")
        c.inc(10)
        c.reset()
        assert c.value == 0.0

    def test_thread_safety(self):
        c = Counter(name="c_thread")
        threads = [threading.Thread(target=lambda: c.inc(1.0)) for _ in range(500)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert c.value == pytest.approx(500.0)


# ===========================================================================
# Gauge
# ===========================================================================

class TestGauge:

    def test_initial_value_zero(self):
        g = Gauge(name="g1")
        assert g.value == 0.0

    def test_set(self):
        g = Gauge(name="g2")
        g.set(42.0)
        assert g.value == pytest.approx(42.0)

    def test_inc_dec(self):
        g = Gauge(name="g3")
        g.inc(10.0)
        g.dec(3.0)
        assert g.value == pytest.approx(7.0)

    def test_can_go_negative(self):
        g = Gauge(name="g4")
        g.dec(5.0)
        assert g.value == pytest.approx(-5.0)

    def test_thread_safety(self):
        g = Gauge(name="g_thread")
        g.set(0.0)
        threads = [threading.Thread(target=lambda: g.inc(1.0)) for _ in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert g.value == pytest.approx(200.0)


# ===========================================================================
# Histogram
# ===========================================================================

class TestHistogram:

    def test_initial_state(self):
        h = Histogram(name="h1")
        assert h.count == 0
        assert h.sum == 0.0
        assert h.mean == 0.0

    def test_single_observation(self):
        h = Histogram(name="h2")
        h.observe(0.05)
        assert h.count == 1
        assert h.sum == pytest.approx(0.05)
        assert h.mean == pytest.approx(0.05)

    def test_multiple_observations(self):
        h = Histogram(name="h3")
        values = [0.01, 0.1, 1.0, 5.0]
        for v in values:
            h.observe(v)
        assert h.count == 4
        assert h.sum == pytest.approx(sum(values))
        assert h.mean == pytest.approx(sum(values) / 4)

    def test_bucket_counts_vectorized(self):
        h = Histogram(name="h4", buckets=[0.1, 0.5, 1.0])
        h.observe(0.05)   # fits in all buckets (0.1, 0.5, 1.0)
        h.observe(0.3)    # fits in 0.5 and 1.0
        h.observe(0.8)    # fits in 1.0 only
        snap = h.snapshot()
        assert snap["buckets"]["0.1"] == 1
        assert snap["buckets"]["0.5"] == 2
        assert snap["buckets"]["1.0"] == 3

    def test_percentile_p50(self):
        h = Histogram(name="h5")
        for v in range(1, 101):
            h.observe(float(v))
        p50 = h.percentile(50)
        assert 49.0 <= p50 <= 51.0

    def test_percentile_p99(self):
        h = Histogram(name="h6")
        for v in range(1, 101):
            h.observe(float(v))
        p99 = h.percentile(99)
        assert p99 >= 98.0

    def test_percentile_empty(self):
        h = Histogram(name="h_empty")
        assert h.percentile(50) == 0.0

    def test_snapshot_keys(self):
        h = Histogram(name="h_snap")
        h.observe(1.0)
        snap = h.snapshot()
        for key in ("name", "count", "sum", "mean", "p50", "p95", "p99", "buckets"):
            assert key in snap

    def test_thread_safety(self):
        h = Histogram(name="h_thread")
        threads = [threading.Thread(target=lambda: h.observe(1.0)) for _ in range(300)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert h.count == 300


# ===========================================================================
# LatencyTimer
# ===========================================================================

class TestLatencyTimer:

    def test_records_elapsed_time(self):
        h = Histogram(name="lat1")
        with LatencyTimer(h):
            time.sleep(0.01)
        assert h.count == 1
        assert h.sum >= 0.005  # at least 5ms

    def test_records_on_exception(self):
        h = Histogram(name="lat2")
        try:
            with LatencyTimer(h):
                raise RuntimeError("test error")
        except RuntimeError:
            pass
        assert h.count == 1


# ===========================================================================
# MetricsCollector
# ===========================================================================

class TestMetricsCollector:

    def test_initial_snapshot(self):
        mc = MetricsCollector()
        snap = mc.snapshot()
        assert snap["orders_submitted"] == 0.0
        assert snap["orders_filled"] == 0.0
        assert snap["orders_rejected"] == 0.0
        assert snap["fill_rate"] == 0.0

    def test_record_slippage(self):
        mc = MetricsCollector()
        mc.record_slippage(2.5)
        mc.record_slippage(7.0)
        snap = mc.snapshot()
        assert snap["slippage_bps"]["count"] == 2
        assert snap["slippage_bps"]["sum"] == pytest.approx(9.5)

    def test_record_fill_full(self):
        mc = MetricsCollector()
        mc.record_fill(filled_qty=100.0, total_qty=100.0)
        snap = mc.snapshot()
        assert snap["orders_submitted"] == 1.0
        assert snap["orders_filled"] == 1.0
        assert snap["fill_rate"] == pytest.approx(1.0)

    def test_record_fill_partial(self):
        mc = MetricsCollector()
        mc.record_fill(filled_qty=50.0, total_qty=100.0)
        snap = mc.snapshot()
        assert snap["orders_submitted"] == 1.0
        assert snap["orders_filled"] == 0.0
        assert snap["fill_rate"] == pytest.approx(0.5)

    def test_record_fill_zero_total_raises(self):
        mc = MetricsCollector()
        with pytest.raises(ValueError, match="positive"):
            mc.record_fill(filled_qty=0.0, total_qty=0.0)

    def test_latency_histograms_present(self):
        mc = MetricsCollector()
        snap = mc.snapshot()
        assert "alpha_to_risk_latency_s" in snap
        assert "risk_to_exec_latency_s" in snap
        assert "end_to_end_latency_s" in snap

    def test_singleton(self):
        c1 = get_metrics_collector()
        c2 = get_metrics_collector()
        assert c1 is c2


# ===========================================================================
# KillSwitch
# ===========================================================================

class TestKillSwitch:

    def setup_method(self):
        """Reset singleton before each test."""
        reset_kill_switch()

    def test_initial_state_not_activated(self):
        ks = KillSwitch()
        assert not ks.is_activated

    def test_activate_sets_flag(self):
        ks = KillSwitch()
        ks.activate(reason="test")
        assert ks.is_activated

    def test_idempotent_activation(self):
        called = []
        ks = KillSwitch()
        ks.register_callback(lambda: called.append(1))
        ks.activate()
        ks.activate()  # second call — must not re-run callbacks
        assert len(called) == 1

    def test_callbacks_called_lifo(self):
        order = []
        ks = KillSwitch()
        ks.register_callback(lambda: order.append("first"))
        ks.register_callback(lambda: order.append("second"))
        ks.register_callback(lambda: order.append("third"))
        ks.activate()
        assert order == ["third", "second", "first"]

    def test_callback_exception_does_not_abort_shutdown(self):
        results = []

        def _raise() -> None:
            raise RuntimeError("boom")

        ks = KillSwitch()
        ks.register_callback(lambda: results.append("safe"))
        ks.register_callback(_raise)
        ks.register_callback(lambda: results.append("also_safe"))
        ks.activate()
        # Both safe callbacks must have run despite the exception
        assert "safe" in results
        assert "also_safe" in results

    def test_register_after_activation_raises(self):
        ks = KillSwitch()
        ks.activate()
        with pytest.raises(RuntimeError, match="already activated"):
            ks.register_callback(lambda: None)

    def test_wait_returns_true_when_activated(self):
        ks = KillSwitch()
        threading.Timer(0.05, ks.activate).start()
        result = ks.wait(timeout=2.0)
        assert result is True

    def test_wait_returns_false_on_timeout(self):
        ks = KillSwitch()
        result = ks.wait(timeout=0.05)
        assert result is False

    def test_dumps_metrics_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mc = MetricsCollector()
            mc.record_slippage(3.0)
            ks = KillSwitch(dump_dir=tmpdir)
            ks.register_metrics_collector(mc)
            ks.activate(reason="test_dump")

            snap_path = Path(tmpdir) / "metrics_snapshot.json"
            assert snap_path.exists()
            data = json.loads(snap_path.read_text())
            assert data["slippage_bps"]["count"] == 1

    def test_dumps_kill_switch_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ks = KillSwitch(dump_dir=tmpdir)
            ks.activate(reason="emergency_stop")

            event_path = Path(tmpdir) / "kill_switch_event.json"
            assert event_path.exists()
            event = json.loads(event_path.read_text())
            assert event["reason"] == "emergency_stop"
            assert "activation_id" in event
            assert "activated_at" in event

    def test_singleton(self):
        reset_kill_switch()
        ks1 = get_kill_switch()
        ks2 = get_kill_switch()
        assert ks1 is ks2

    def test_thread_safe_activation(self):
        """Multiple threads racing to activate — only one should win."""
        ks = KillSwitch()
        called = []
        ks.register_callback(lambda: called.append(1))

        def _activate():
            ks.activate(reason="race")

        threads = [threading.Thread(target=_activate) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert ks.is_activated
        assert len(called) == 1  # callback invoked exactly once
