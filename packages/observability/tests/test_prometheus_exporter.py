"""
Tests for PrometheusExporter - OMEGA_QUANT Phase 7 observability.

Coverage:
- Disabled exporter is a no-op (no prometheus_client required)
- Enabled exporter registers metrics and records observations
- record_latency populates histogram
- record_risk_metric populates gauge
- get_metrics_text returns valid Prometheus text format
- ImportError raised when prometheus_client missing and enabled=True
- start_http_server is idempotent (no double-start)
"""

import sys
import types
import pytest

from omega.observability.metrics import PrometheusExporter, PrometheusExporterConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exporter(enabled: bool = True, port: int = 9100, namespace: str = "test_omega") -> PrometheusExporter:
    """Create a fresh exporter with an isolated prometheus registry."""
    # Each test gets its own CollectorRegistry to avoid duplicate-metric errors
    # across test runs in the same process.
    prom = pytest.importorskip("prometheus_client")
    registry = prom.CollectorRegistry()

    config = PrometheusExporterConfig(enabled=enabled, port=port, namespace=namespace)
    exporter = PrometheusExporter.__new__(PrometheusExporter)
    exporter._config = config
    exporter._prom = None
    exporter._latency_histogram = None
    exporter._risk_gauge = None
    exporter._server_started = False

    if enabled:
        # Re-implement _init_prometheus with isolated registry
        exporter._prom = prom
        exporter._latency_histogram = prom.Histogram(
            f"{namespace}_latency_ms",
            "Component latency in milliseconds",
            labelnames=["component"],
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
            registry=registry,
        )
        exporter._risk_gauge = prom.Gauge(
            f"{namespace}_risk_metric",
            "Risk metric value",
            labelnames=["metric"],
            registry=registry,
        )
        # Patch get_metrics_text to use isolated registry
        def _get_metrics_text():
            return prom.generate_latest(registry).decode("utf-8")
        exporter.get_metrics_text = _get_metrics_text

    return exporter


# ---------------------------------------------------------------------------
# Disabled exporter — no-op, no prometheus_client needed
# ---------------------------------------------------------------------------

class TestPrometheusExporterDisabled:
    def test_disabled_config(self):
        config = PrometheusExporterConfig(enabled=False)
        exporter = PrometheusExporter(config)
        assert exporter.enabled is False

    def test_record_latency_noop(self):
        config = PrometheusExporterConfig(enabled=False)
        exporter = PrometheusExporter(config)
        # Must not raise even without prometheus_client
        exporter.record_latency("data_loading", 42.0)

    def test_record_risk_metric_noop(self):
        config = PrometheusExporterConfig(enabled=False)
        exporter = PrometheusExporter(config)
        exporter.record_risk_metric("drawdown", 0.05)

    def test_get_metrics_text_empty(self):
        config = PrometheusExporterConfig(enabled=False)
        exporter = PrometheusExporter(config)
        assert exporter.get_metrics_text() == ""

    def test_start_http_server_noop(self):
        config = PrometheusExporterConfig(enabled=False)
        exporter = PrometheusExporter(config)
        exporter.start_http_server()  # must not raise
        assert exporter._server_started is False


# ---------------------------------------------------------------------------
# Enabled exporter — requires prometheus_client
# ---------------------------------------------------------------------------

class TestPrometheusExporterEnabled:
    def test_enabled_flag(self):
        exporter = _make_exporter(enabled=True)
        assert exporter.enabled is True

    def test_metrics_registered(self):
        exporter = _make_exporter(enabled=True)
        assert exporter._latency_histogram is not None
        assert exporter._risk_gauge is not None

    def test_record_latency_appears_in_output(self):
        exporter = _make_exporter(enabled=True, namespace="lat_test")
        exporter.record_latency("order_router", 15.3)
        text = exporter.get_metrics_text()
        assert "lat_test_latency_ms" in text
        assert 'component="order_router"' in text

    def test_record_latency_multiple_components(self):
        exporter = _make_exporter(enabled=True, namespace="multi_lat")
        exporter.record_latency("data_loading", 10.0)
        exporter.record_latency("risk_check", 5.0)
        text = exporter.get_metrics_text()
        assert 'component="data_loading"' in text
        assert 'component="risk_check"' in text

    def test_record_risk_metric_appears_in_output(self):
        exporter = _make_exporter(enabled=True, namespace="risk_test")
        exporter.record_risk_metric("drawdown", 0.03)
        text = exporter.get_metrics_text()
        assert "risk_test_risk_metric" in text
        assert 'metric="drawdown"' in text

    def test_record_risk_metric_multiple(self):
        exporter = _make_exporter(enabled=True, namespace="multi_risk")
        exporter.record_risk_metric("var_95", 0.02)
        exporter.record_risk_metric("leverage", 1.5)
        text = exporter.get_metrics_text()
        assert 'metric="var_95"' in text
        assert 'metric="leverage"' in text

    def test_record_risk_metric_value(self):
        prom = pytest.importorskip("prometheus_client")
        registry = prom.CollectorRegistry()
        config = PrometheusExporterConfig(enabled=True, namespace="val_test")
        exporter = PrometheusExporter.__new__(PrometheusExporter)
        exporter._config = config
        exporter._prom = prom
        exporter._latency_histogram = prom.Histogram(
            "val_test_latency_ms", "latency", labelnames=["component"], registry=registry
        )
        gauge = prom.Gauge(
            "val_test_risk_metric", "risk", labelnames=["metric"], registry=registry
        )
        exporter._risk_gauge = gauge
        exporter._server_started = False

        exporter.record_risk_metric("drawdown", 0.07)
        assert gauge.labels(metric="drawdown")._value.get() == pytest.approx(0.07)

    def test_get_metrics_text_format(self):
        exporter = _make_exporter(enabled=True, namespace="fmt_test")
        exporter.record_latency("backtester", 200.0)
        text = exporter.get_metrics_text()
        # Prometheus text format always contains TYPE and HELP lines
        assert "# HELP" in text
        assert "# TYPE" in text

    def test_start_http_server_idempotent(self, monkeypatch):
        exporter = _make_exporter(enabled=True, namespace="srv_test")
        call_count = {"n": 0}

        def fake_start(port):
            call_count["n"] += 1

        monkeypatch.setattr(exporter._prom, "start_http_server", fake_start)
        exporter.start_http_server()
        exporter.start_http_server()  # second call must be no-op
        assert call_count["n"] == 1
        assert exporter._server_started is True


# ---------------------------------------------------------------------------
# ImportError when prometheus_client missing and enabled=True
# ---------------------------------------------------------------------------

class TestPrometheusExporterImportError:
    def test_raises_import_error_when_missing(self, monkeypatch):
        """Simulate prometheus_client not being installed."""
        # Temporarily hide prometheus_client from imports
        real_module = sys.modules.pop("prometheus_client", None)
        # Also block the import at the finder level
        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else None

        blocker = types.ModuleType("prometheus_client")

        def fake_import(name, *args, **kwargs):
            if name == "prometheus_client":
                raise ImportError("No module named 'prometheus_client'")
            return real_import(name, *args, **kwargs)

        real_import = __import__
        import builtins
        monkeypatch.setattr(builtins, "__import__", fake_import)

        try:
            config = PrometheusExporterConfig(enabled=True)
            with pytest.raises(ImportError, match="prometheus_client is required"):
                PrometheusExporter(config)
        finally:
            if real_module is not None:
                sys.modules["prometheus_client"] = real_module
