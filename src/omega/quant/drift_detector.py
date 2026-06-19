"""omega.quant.drift_detector - shim wrapper for evolution"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import pandas as pd

from omega.quant.evolution.drift_detector import (
    DriftDetectorEnsemble as RealEnsemble,
    DriftDetectorConfig as RealConfig
)


@dataclass
class DriftThresholds:
    """Thresholds configuration wrapper."""
    sharpe_drop: float = 0.3
    ic_drop: float = 0.01
    turnover_spike: float = 2.0
    # Extra parameters from phase6_evolution_engine.py config
    sharpe_drop_pct: float = 0.30
    ic_drop_pct: float = 0.20
    turnover_spike_pct: float = 0.50


class DriftDetector:
    """Compatibility base class."""
    def __init__(self, config=None):
        pass

    def detect(self, series: pd.Series) -> bool:
        return False

    def reset(self):
        pass


class ConceptDriftDetector(DriftDetector):
    pass


class DataDriftDetector(DriftDetector):
    pass


class DriftDetectorEnsemble:
    """Wrapper delegating to the real DriftDetectorEnsemble from evolution."""
    def __init__(self, detectors=None, thresholds: DriftThresholds = None):
        self.detectors = detectors or []
        self.thresholds = thresholds or DriftThresholds()
        self._baseline = None
        self._total = 0
        self._drift_events = 0

        # Map thresholds to config
        # Use phase6 config values if provided, otherwise default to
        # DriftThresholds
        s_pct = self.thresholds.sharpe_drop_pct
        s_drop = self.thresholds.sharpe_drop
        sharpe_t = s_pct if s_pct != 0.30 else s_drop

        ic_pct = self.thresholds.ic_drop_pct
        ic_drop = self.thresholds.ic_drop
        ic_t = ic_pct if ic_pct != 0.20 else ic_drop

        t_pct = self.thresholds.turnover_spike_pct
        t_spike = self.thresholds.turnover_spike
        turnover_t = t_pct if t_pct != 0.50 else t_spike

        config = RealConfig(
            sharpe_drop_threshold=sharpe_t,
            ic_drop_threshold=ic_t,
            turnover_spike_threshold=turnover_t
        )
        self._real = RealEnsemble(config)

    def detect(self, series: pd.Series) -> bool:
        return False

    def detect_drift(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        self._total += 1
        sharpe = metrics.get('sharpe', 0.0)
        ic = metrics.get('ic', 0.0)
        turnover = metrics.get('turnover', 0.0)

        # Check drift using historical values
        res = self._real.check_drift(sharpe, ic, turnover)

        # Record current metrics for future checks
        now = pd.Timestamp.now()
        self._real.record_metrics(now, sharpe, ic, turnover)

        drift_detected = res.get("drift_detected", False)
        if drift_detected:
            self._drift_events += 1

        detectors_map = {
            'sharpe': res.get("sharpe_drift", False),
            'ic': res.get("ic_drift", False),
            'turnover': res.get("turnover_drift", False)
        }

        return {
            'drift_detected': drift_detected,
            'votes': len(res.get("detectors_triggered", [])),
            'detectors': detectors_map
        }

    def set_baseline(self, metrics: Dict[str, Any]) -> None:
        self._baseline = metrics
        # Record baseline metrics twice backdated to seed history for
        # comparison
        now = pd.Timestamp.now()
        sharpe = metrics.get('sharpe', 0.0)
        ic = metrics.get('ic', 0.0)
        turnover = metrics.get('turnover', 0.0)

        self._real.record_metrics(
            now - pd.Timedelta(days=2), sharpe, ic, turnover
        )
        self._real.record_metrics(
            now - pd.Timedelta(days=1), sharpe, ic, turnover
        )

    def reset_baseline_on_rollback(self, metrics: Dict[str, Any]) -> None:
        self.set_baseline(metrics)

    def reset(self) -> None:
        self._baseline = None
        self._real.history.clear()

    def get_summary(self) -> Dict[str, Any]:
        rate = self._drift_events / self._total if self._total > 0 else 0.0
        return {
            'total_detections': self._total,
            'drift_events': self._drift_events,
            'drift_rate': rate
        }
