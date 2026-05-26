"""omega.quant.drift_detector - compatibility shim"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import pandas as pd

@dataclass
class DriftThresholds:
    sharpe_drop: float = 0.3
    ic_drop: float = 0.01
    turnover_spike: float = 2.0

class DriftDetector:
    def __init__(self, config=None): pass
    def detect(self, series: pd.Series) -> bool: return False
    def reset(self): pass

class ConceptDriftDetector(DriftDetector): pass
class DataDriftDetector(DriftDetector): pass

class DriftDetectorEnsemble:
    def __init__(self, detectors=None, thresholds: DriftThresholds = None):
        self.detectors = detectors or []
        self.thresholds = thresholds or DriftThresholds()
        self._baseline = None
        self._total = 0
        self._drift_events = 0

    def detect(self, series: pd.Series) -> bool: return False

    def detect_drift(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        self._total += 1
        return {
            'drift_detected': False,
            'votes': 0,
            'detectors': {'sharpe': False, 'ic': False, 'turnover': False}
        }

    def set_baseline(self, metrics: Dict[str, Any]): self._baseline = metrics

    def reset_baseline_on_rollback(self, metrics: Dict[str, Any]): self._baseline = metrics

    def reset(self): self._baseline = None

    def get_summary(self) -> Dict[str, Any]:
        rate = self._drift_events / self._total if self._total > 0 else 0.0
        return {'total_detections': self._total, 'drift_events': self._drift_events, 'drift_rate': rate}
