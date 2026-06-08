"""
Metrics Collector - OMEGA_QUANT Phase 7.
Lightweight in-memory metrics for latency, throughput, and error rates.
"""

from typing import Dict, Any, List
import time
from collections import defaultdict


class MetricsCollector:
    """Metrics collector for pipeline execution metrics."""
    
    def __init__(self):
        self._metrics: Dict[str, Any] = {}
        self._start_times: Dict[str, float] = {}
        self._metric_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)  # Store history of metrics
    
    def record_metric(self, name: str, value: Any, tags: Dict[str, str] = None) -> None:
        """Record a metric value."""
        key = self._format_key(name, tags)
        self._metrics[key] = value
    
    def start_timer(self, name: str, tags: Dict[str, str] = None) -> None:
        """Start a timer for a metric."""
        key = self._format_key(name, tags)
        self._start_times[key] = time.time()
    
    def stop_timer(self, name: str, tags: Dict[str, str] = None) -> float:
        """Stop a timer and record the duration."""
        key = self._format_key(name, tags)
        if key not in self._start_times:
            return 0.0
        duration = time.time() - self._start_times[key]
        self._metrics[key] = duration
        del self._start_times[key]
        return duration
    
    def get_metric(self, name: str, tags: Dict[str, str] = None) -> Any:
        """Get a metric value."""
        key = self._format_key(name, tags)
        return self._metrics.get(key)
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all recorded metrics."""
        return self._metrics.copy()
    
    def reset(self) -> None:
        """Reset all metrics."""
        self._metrics.clear()
        self._start_times.clear()
    
    def _format_key(self, name: str, tags: Dict[str, str] = None) -> str:
        """Format metric key with tags."""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"
    
    def record_pipeline_metrics(self, metrics: Dict[str, Any]) -> None:
        """Record pipeline execution metrics."""
        # Store in history for get_metrics to return as list
        self._metric_history['pipeline'].append(metrics.copy())
        # Also store individual metrics
        for key, value in metrics.items():
            self.record_metric(key, value)
    
    def record_return(self, date: Any, return_value: float) -> None:
        """Record a return value for a specific date."""
        if not hasattr(self, '_returns'):
            self._returns = []
        self._returns.append({'date': date, 'return': return_value})
    
    def record_latency(self, component: str, latency_ms: float) -> None:
        """Record latency for a component."""
        if not hasattr(self, '_latencies'):
            self._latencies = defaultdict(list)
        self._latencies[component].append(latency_ms)
        # Also record as metric for backward compatibility
        self.record_metric(f"{component}_latency_ms", latency_ms)
    
    def increment_counter(self, name: str, tags: Dict[str, str] = None) -> None:
        """Increment a counter metric."""
        key = self._format_key(name, tags)
        current = self._metrics.get(key, 0)
        self._metrics[key] = current + 1
    
    def compute_performance_metrics(self, end_date=None) -> Dict[str, float]:
        """
        Compute performance metrics from recorded returns.
        
        Args:
            end_date: Optional cutoff date for PIT-safe computation.
                     Only returns up to and including this date will be used.
        
        Returns:
            Dictionary with performance metrics.
        """
        if not hasattr(self, '_returns') or not self._returns:
            return {
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'volatility': 0.0,
                'win_rate': 0.0
            }
        
        import numpy as np
        import pandas as pd
        
        # Filter returns by end_date if provided (PIT safety)
        if end_date is not None:
            filtered_returns = [r for r in self._returns if r['date'] <= end_date]
            if not filtered_returns:
                return {
                    'total_return': 0.0,
                    'sharpe_ratio': 0.0,
                    'max_drawdown': 0.0,
                    'volatility': 0.0,
                    'win_rate': 0.0
                }
            returns = np.array([r['return'] for r in filtered_returns])
        else:
            returns = np.array([r['return'] for r in self._returns])
        
        total_return = np.prod(1 + returns) - 1
        sharpe_ratio = returns.mean() / (returns.std() + 1e-10) * np.sqrt(252)
        
        # Calculate max drawdown (return as positive value)
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = abs(drawdown.min())  # Convert to positive value
        
        volatility = returns.std() * np.sqrt(252)
        
        # Calculate win rate
        win_rate = (returns > 0).sum() / len(returns) if len(returns) > 0 else 0.0
        
        return {
            'total_return': float(total_return),
            'sharpe_ratio': float(sharpe_ratio),
            'max_drawdown': float(max_drawdown),
            'volatility': float(volatility),
            'win_rate': float(win_rate)
        }
    
    def get_metrics(self, namespace: str) -> List[Dict[str, Any]]:
        """
        Get all metrics for a specific namespace.
        
        Args:
            namespace: Metric namespace (e.g., 'pipeline', 'execution').
            
        Returns:
            List of metric records in that namespace (for time-series data).
            If no history exists, returns dict wrapped in list for compatibility.
        """
        # Return history if available (for pipeline metrics)
        if namespace in self._metric_history and self._metric_history[namespace]:
            return self._metric_history[namespace]
        
        # Fallback: return current metrics as dict (legacy behavior)
        result = {}
        prefix = f"{namespace}."
        
        for key, value in self._metrics.items():
            if key.startswith(prefix) or key.startswith(namespace):
                # Remove prefix for cleaner keys
                clean_key = key.replace(prefix, '').replace(f"{namespace}_", '')
                result[clean_key] = value
        
        return [result] if result else []
    
    def get_latency_stats(self) -> Dict[str, Any]:
        """
        Get latency statistics from recorded metrics.
        
        Returns:
            Dictionary with per-component latency statistics.
        """
        import numpy as np
        
        result = {}
        
        # Use _latencies if available (new approach)
        if hasattr(self, '_latencies'):
            for component, values in self._latencies.items():
                if values:
                    values_array = np.array(values)
                    result[component] = {
                        'count': len(values_array),
                        'mean': float(np.mean(values_array)),
                        'median': float(np.median(values_array)),
                        'min': float(np.min(values_array)),
                        'max': float(np.max(values_array)),
                        'p95': float(np.percentile(values_array, 95)),
                        'p99': float(np.percentile(values_array, 99))
                    }
            return result
        
        # Fallback: old approach (single value per component)
        latency_stats = {}
        
        # Find all latency metrics and group by component
        for key, value in self._metrics.items():
            if '_latency_ms' in key:
                # Extract component name (e.g., "data_loading_latency_ms" -> "data_loading")
                component = key.replace('_latency_ms', '')
                
                if component not in latency_stats:
                    latency_stats[component] = []
                
                if isinstance(value, (int, float)):
                    latency_stats[component].append(value)
        
        # Compute stats for each component
        for component, values in latency_stats.items():
            if values:
                values_array = np.array(values)
                result[component] = {
                    'count': len(values_array),
                    'mean': float(np.mean(values_array)),
                    'median': float(np.median(values_array)),
                    'min': float(np.min(values_array)),
                    'max': float(np.max(values_array)),
                    'p95': float(np.percentile(values_array, 95)),
                    'p99': float(np.percentile(values_array, 99))
                }
        
        return result


class MetricsRegistry:
    """In-memory metrics registry for testing/local execution."""
    
    def __init__(self):
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        
    def increment(self, name: str, value: int = 1, tags: Dict[str, str] = None) -> None:
        """Increment a counter."""
        tag_suffix = self._format_tags(tags)
        self._counters[f"{name}{tag_suffix}"] += value
        
    def gauge(self, name: str, value: float, tags: Dict[str, str] = None) -> None:
        """Set a gauge value (e.g., current active users, memory used)."""
        tag_suffix = self._format_tags(tags)
        self._gauges[f"{name}{tag_suffix}"] = value
        
    def record(self, name: str, value: float, tags: Dict[str, str] = None) -> None:
        """Record a histogram value (e.g., latency)."""
        tag_suffix = self._format_tags(tags)
        self._histograms[f"{name}{tag_suffix}"].append(value)
        
    def _format_tags(self, tags: Dict[str, str] = None) -> str:
        """Format tags for key storage."""
        if not tags:
            return ""
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"[{tag_str}]"
    
    def get_snapshot(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        hist_stats = {}
        for key, values in self._histograms.items():
            if values:
                hist_stats[key] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values)
                }
                
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": hist_stats
        }

from dataclasses import dataclass

@dataclass
class PrometheusExporterConfig:
    """Configuration for Prometheus metric export."""
    enabled: bool = False
    port: int = 9090
    namespace: str = "omega"

class PrometheusExporter:
    """Exports metrics to Prometheus when enabled."""
    
    def __init__(self, config: PrometheusExporterConfig):
        self._config = config
        self._server_started = False
        self._prom = None
        self._latency_histogram = None
        self._risk_gauge = None
        
        if config.enabled:
            self._init_prometheus()
            
    def _init_prometheus(self):
        try:
            import prometheus_client
            self._prom = prometheus_client
            self._latency_histogram = prometheus_client.Histogram(
                f"{self._config.namespace}_latency_ms",
                "Component latency in milliseconds",
                labelnames=["component"],
                buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
            )
            self._risk_gauge = prometheus_client.Gauge(
                f"{self._config.namespace}_risk_metric",
                "Risk metric value",
                labelnames=["metric"],
            )
        except ImportError:
            raise ImportError("prometheus_client is required when exporter is enabled")

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def record_latency(self, component: str, latency_ms: float) -> None:
        """Record component latency in milliseconds."""
        if not self._config.enabled or not self._latency_histogram:
            return
        self._latency_histogram.labels(component=component).observe(latency_ms)

    def record_risk_metric(self, metric: str, value: float) -> None:
        """Record a risk-related metric value."""
        if not self._config.enabled or not self._risk_gauge:
            return
        self._risk_gauge.labels(metric=metric).set(value)

    def get_metrics_text(self) -> str:
        """Get metrics in Prometheus text format."""
        if not self._config.enabled or not self._prom:
            return ""
        return self._prom.generate_latest().decode('utf-8')

    def start_http_server(self) -> None:
        """Start the Prometheus HTTP server."""
        if not self._config.enabled or not self._prom or self._server_started:
            return
        self._prom.start_http_server(self._config.port)
        self._server_started = True

# Global registry for easy access
registry = MetricsRegistry()


from dataclasses import dataclass as _dataclass


@_dataclass
class PrometheusExporterConfig:
    """Configuration for PrometheusExporter."""
    enabled: bool = True
    port: int = 9100
    namespace: str = "omega"


class PrometheusExporter:
    """
    Prometheus metrics exporter for OMEGA_QUANT Phase 7 observability.

    When enabled=False, all methods are no-ops and prometheus_client is
    not required. When enabled=True, prometheus_client must be installed.
    """

    def __init__(self, config: PrometheusExporterConfig):
        self._config = config
        self._prom = None
        self._latency_histogram = None
        self._risk_gauge = None
        self._server_started = False

        if config.enabled:
            self._init_prometheus()

    def _init_prometheus(self) -> None:
        """Import and initialise prometheus_client metrics."""
        try:
            import prometheus_client as prom
        except ImportError:
            raise ImportError(
                "prometheus_client is required when PrometheusExporterConfig.enabled=True. "
                "Install it with: pip install prometheus-client"
            )
        self._prom = prom
        ns = self._config.namespace
        self._latency_histogram = prom.Histogram(
            f"{ns}_latency_ms",
            "Component latency in milliseconds",
            labelnames=["component"],
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
        )
        self._risk_gauge = prom.Gauge(
            f"{ns}_risk_metric",
            "Risk metric value",
            labelnames=["metric"],
        )

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def record_latency(self, component: str, latency_ms: float) -> None:
        """Record a latency observation for a component."""
        if not self._config.enabled or self._latency_histogram is None:
            return
        self._latency_histogram.labels(component=component).observe(latency_ms)

    def record_risk_metric(self, metric: str, value: float) -> None:
        """Set a risk gauge value."""
        if not self._config.enabled or self._risk_gauge is None:
            return
        self._risk_gauge.labels(metric=metric).set(value)

    def get_metrics_text(self) -> str:
        """Return current metrics in Prometheus text exposition format."""
        if not self._config.enabled or self._prom is None:
            return ""
        return self._prom.generate_latest().decode("utf-8")

    def start_http_server(self) -> None:
        """Start the Prometheus HTTP server (idempotent)."""
        if not self._config.enabled or self._prom is None:
            return
        if self._server_started:
            return
        self._prom.start_http_server(self._config.port)
        self._server_started = True
