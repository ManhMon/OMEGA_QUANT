"""omega.quant.drift_detector - shim wrapper for evolution with W6 decay attribution."""
from __future__ import annotations

import hashlib
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from omega.core.llm_config import _canonical
from omega.quant.evolution.drift_detector import (
    DriftDetectorEnsemble as RealEnsemble,
    DriftDetectorConfig as RealConfig,
)

W6_DECAY_SCHEMA_VERSION = "w6_decay_attribution_v1"
DRIFT_LABELS = ("structural_microstructure_change", "cyclical_regime_rotation", "noise")
ATTRIBUTION_CATEGORIES = ("data_issue", "cost_shift", "regime_mismatch", "unclear")
RECOMMENDATIONS = ("full_retrain", "incremental_update", "wait")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")


def attach_decay_attribution(
    *,
    gross_before: float,
    gross_after: float,
    cost_before: float,
    cost_after: float,
    trigger_detected: bool,
    cutoff: datetime,
    maturity: datetime,
    data_issue_flag: bool = False,
    regime_mismatch_flag: bool = False,
    cost_shift_flag: bool = False,
    drift_label: Optional[str] = None,
    attribution: Optional[str] = None,
    recommendation: Optional[str] = None,
    decision_id: Optional[str] = None,
    gate_id: str = "GATE_JEV_DEEP_INTEGRATION_W6_20260930",
    policy_version: str = "1.0.0",
    source_revision: str = "HEAD",
    synthetic: bool = False,
) -> Dict[str, Any]:
    """Attach deterministic decay attribution to numerical drift triggers."""
    if gate_id != "GATE_JEV_DEEP_INTEGRATION_W6_20260930" or policy_version != "1.0.0":
        raise ValueError("unsupported decay context")
    if type(synthetic) is not bool:
        raise TypeError("synthetic must be strict bool")
    if type(trigger_detected) is not bool:
        raise TypeError("trigger_detected must be strict bool")
    if not trigger_detected and not synthetic:
        raise ValueError("trigger required for decay attribution")

    for f_name, f_val in [
        ("data_issue_flag", data_issue_flag),
        ("regime_mismatch_flag", regime_mismatch_flag),
        ("cost_shift_flag", cost_shift_flag),
    ]:
        if type(f_val) is not bool:
            raise TypeError(f"{f_name} must be strict bool")

    for name, val in [
        ("gross_before", gross_before),
        ("gross_after", gross_after),
        ("cost_before", cost_before),
        ("cost_after", cost_after),
    ]:
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise TypeError(f"{name} must be a real finite number")
        if not -sys.float_info.max <= val <= sys.float_info.max or not math.isfinite(float(val)):
            raise ValueError(f"{name} must be finite")

    if cost_before < 0.0 or cost_after < 0.0:
        raise ValueError("costs must be non-negative")

    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware UTC datetime")
    if not isinstance(maturity, datetime) or maturity.tzinfo is None or maturity.utcoffset() is None:
        raise ValueError("maturity must be timezone-aware UTC datetime")

    cutoff_utc = cutoff.astimezone(timezone.utc)
    maturity_utc = maturity.astimezone(timezone.utc)
    if maturity_utc > cutoff_utc:
        raise ValueError("PIT violation: maturity exceeds cutoff")

    for id_name, id_val in [
        ("gate_id", gate_id),
        ("policy_version", policy_version),
        ("source_revision", source_revision),
    ]:
        if not isinstance(id_val, str) or not _SAFE_IDENTIFIER.fullmatch(id_val):
            raise ValueError(f"{id_name} invalid format")

    if decision_id is not None:
        if not isinstance(decision_id, str) or not _SAFE_IDENTIFIER.fullmatch(decision_id):
            raise ValueError("decision_id invalid format")

    if drift_label is not None and drift_label not in DRIFT_LABELS:
        raise ValueError("invalid drift_label")
    if attribution is not None and attribution not in ATTRIBUTION_CATEGORIES:
        raise ValueError("invalid attribution")
    if recommendation is not None and recommendation not in RECOMMENDATIONS:
        raise ValueError("invalid recommendation")

    gb = float(gross_before)
    ga = float(gross_after)
    cb = float(cost_before)
    ca = float(cost_after)

    net_before = gb - cb
    net_after = ga - ca
    delta_gross = ga - gb
    delta_cost = ca - cb
    delta_net = net_after - net_before

    if not all(math.isfinite(x) for x in (net_before, net_after, delta_gross, delta_cost, delta_net)):
        raise ValueError("non-finite arithmetic in decay decomposition")
    if not math.isclose(delta_net, delta_gross - delta_cost, abs_tol=1e-12):
        raise ValueError("decomposition identity violated: delta_net != delta_gross - delta_cost")

    candidates: List[str] = []
    if data_issue_flag:
        candidates.append("data_issue")
    if cost_shift_flag or (delta_cost > 1e-9 and (delta_cost >= abs(delta_gross) or delta_gross >= 0)):
        candidates.append("cost_shift")
    if regime_mismatch_flag:
        candidates.append("regime_mismatch")

    # Competing evidence cannot be overridden by explicit request
    if len(candidates) > 1:
        eff_attribution = "unclear"
    elif len(candidates) == 1:
        eff_attribution = candidates[0] if attribution in (None, candidates[0]) else "unclear"
    else:
        if delta_cost > 1e-9 and delta_gross >= 0:
            eff_attribution = "cost_shift"
        else:
            eff_attribution = "unclear"

    if drift_label is not None:
        eff_drift_label = drift_label
    else:
        # Default to noise for numeric research; do not invent drift label from cost mechanism
        eff_drift_label = "noise"

    if recommendation is not None:
        eff_recommendation = recommendation
    else:
        if eff_attribution == "regime_mismatch":
            eff_recommendation = "incremental_update"
        elif eff_drift_label == "structural_microstructure_change":
            eff_recommendation = "full_retrain"
        else:
            eff_recommendation = "wait"

    pre_payload = {
        "advisory_only": True,
        "applied": False,
        "attribution": eff_attribution,
        "auto_promote_executed": False,
        "auto_retrain_executed": False,
        "cost_after": ca,
        "cost_before": cb,
        "cost_shift_flag": cost_shift_flag,
        "cutoff": cutoff_utc.isoformat(),
        "data_issue_flag": data_issue_flag,
        "delta_cost": delta_cost,
        "delta_gross": delta_gross,
        "delta_net": delta_net,
        "domain": "drift_decay",
        "drift_label": eff_drift_label,
        "execution_status": "no_execution",
        "gate_id": gate_id,
        "gross_after": ga,
        "gross_before": gb,
        "maturity": maturity_utc.isoformat(),
        "net_after": net_after,
        "net_before": net_before,
        "policy_version": policy_version,
        "recommendation": eff_recommendation,
        "regime_mismatch_flag": regime_mismatch_flag,
        "schema_version": W6_DECAY_SCHEMA_VERSION,
        "source_revision": source_revision,
        "synthetic": synthetic,
        "trigger_detected": trigger_detected,
    }

    if decision_id is None:
        pre_digest = hashlib.sha256(_canonical(pre_payload)).hexdigest()
        eff_decision_id = f"DECAY_{pre_digest[:16]}"
    else:
        eff_decision_id = decision_id

    payload_with_id = {**pre_payload, "decision_id": eff_decision_id}
    canonical_digest = hashlib.sha256(_canonical(payload_with_id)).hexdigest()

    return {**payload_with_id, "canonical_digest": canonical_digest}


@dataclass
class DriftThresholds:
    """Thresholds configuration wrapper."""
    sharpe_drop: float = 0.3
    ic_drop: float = 0.01
    turnover_spike: float = 2.0
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
    attach_decay_attribution = staticmethod(attach_decay_attribution)

    def __init__(self, detectors=None, thresholds: DriftThresholds = None):
        self.detectors = detectors or []
        self.thresholds = thresholds or DriftThresholds()
        self._baseline = None
        self._total = 0
        self._drift_events = 0

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
            turnover_spike_threshold=turnover_t,
        )
        self._real = RealEnsemble(config)

    def detect(self, series: pd.Series) -> bool:
        return False

    def detect_drift(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        self._total += 1
        sharpe = metrics.get("sharpe", 0.0)
        ic = metrics.get("ic", 0.0)
        turnover = metrics.get("turnover", 0.0)

        res = self._real.check_drift(sharpe, ic, turnover)
        now = pd.Timestamp.now()
        self._real.record_metrics(now, sharpe, ic, turnover)

        drift_detected = res.get("drift_detected", False)
        if drift_detected:
            self._drift_events += 1

        detectors_map = {
            "sharpe": res.get("sharpe_drift", False),
            "ic": res.get("ic_drift", False),
            "turnover": res.get("turnover_drift", False),
        }

        return {
            "drift_detected": drift_detected,
            "votes": len(res.get("detectors_triggered", [])),
            "detectors": detectors_map,
        }

    def set_baseline(self, metrics: Dict[str, Any]) -> None:
        self._baseline = metrics
        now = pd.Timestamp.now()
        sharpe = metrics.get("sharpe", 0.0)
        ic = metrics.get("ic", 0.0)
        turnover = metrics.get("turnover", 0.0)

        self._real.record_metrics(now - pd.Timedelta(days=2), sharpe, ic, turnover)
        self._real.record_metrics(now - pd.Timedelta(days=1), sharpe, ic, turnover)

    def reset_baseline_on_rollback(self, metrics: Dict[str, Any]) -> None:
        self.set_baseline(metrics)

    def reset(self) -> None:
        self._baseline = None
        self._real.history.clear()

    def get_summary(self) -> Dict[str, Any]:
        rate = self._drift_events / self._total if self._total > 0 else 0.0
        return {
            "total_detections": self._total,
            "drift_events": self._drift_events,
            "drift_rate": rate,
        }
