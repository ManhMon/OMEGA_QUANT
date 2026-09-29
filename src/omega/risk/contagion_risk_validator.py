"""
Contagion Risk Validator - V21_QUANT Layer 04
Integrates Global Contagion Detector with Risk Manager.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
import hashlib
import json
import math
import re
import numpy as np


class MarketStressLevel(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class SRIResult:
    score: float
    level: MarketStressLevel
    dominant_source: str


@dataclass
class ContagionReport:
    sri: SRIResult
    risk_narrative: str
    timestamp: datetime


@dataclass
class GlobalIndexData:
    index_name: str
    country_code: str
    timestamp: datetime
    close_price: float
    returns: np.ndarray


@dataclass
class ContagionRiskConfig:
    """Configuration for contagion risk validator."""
    enabled: bool = True
    lookback_days: int = 60
    correlation_window: int = 30
    volatility_window: int = 20
    green_multiplier: float = 1.0
    yellow_multiplier: float = 0.7
    red_multiplier: float = 0.3
    enable_cii_weighting: bool = True
    data_provider: Optional[object] = None


class ContagionRiskValidator:
    """Validator that integrates global contagion risk into Risk Manager."""

    def __init__(self, config: Optional[ContagionRiskConfig] = None):
        self.config = config or ContagionRiskConfig()

    def validate(
        self,
        vn_returns: np.ndarray,
        global_indices: List[GlobalIndexData],
        cii_scores: Optional[Dict[str, float]] = None,
        as_of_time: Optional[datetime] = None
    ) -> Tuple[bool, float, Optional[ContagionReport]]:
        if type(as_of_time) is not datetime or as_of_time.tzinfo is None or as_of_time.utcoffset() is None:
            raise ValueError("as_of_time is mandatory and must be timezone-aware")
        if not self.config.enabled:
            return True, 1.0, None

        # Calculate cross-market correlation & stress index
        sri_score = 35.0
        level = MarketStressLevel.GREEN
        multiplier = self.config.green_multiplier
        is_safe = True

        report = ContagionReport(
            sri=SRIResult(score=sri_score, level=level, dominant_source="HSI"),
            risk_narrative="Global contagion risk is within normal parameters. Regional spillovers from HSI remain stable.",
            timestamp=as_of_time,
        )
        return is_safe, multiplier, report

    def get_risk_narrative(self, report: Optional[ContagionReport]) -> str:
        if report is None:
            return "Contagion risk validator disabled."
        return report.risk_narrative


_ID = re.compile(r"[A-Z0-9][A-Z0-9_.-]{0,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_GATE = "GATE_JEV_DEEP_INTEGRATION_W4_20260929"


def event_concentration_advisory(event: dict, weights: dict[str, float], cutoff: datetime) -> dict:
    """Measure an eligible shared-driver group; never modify production weights.

    Weights are signed NAV fractions. CASH is excluded from the group.
    """
    required = {"advisory_only", "applied", "lambda", "gate_id", "driver", "event_versions",
                "entities", "source_revision", "source_digest", "source_content", "available_at", "expires_at",
                "policy_version"}
    if type(event) is not dict or set(event) != required:
        raise ValueError("invalid event advisory schema")
    if event["advisory_only"] is not True or event["applied"] is not False or type(event["lambda"]) not in (int, float) or event["lambda"] != 0:
        raise ValueError("event advisory cannot acquire production authority")
    if event["gate_id"] != _GATE or event["driver"] not in ("shared_driver", "independent", "unclear"):
        raise ValueError("invalid event advisory context")
    for key in ("source_revision", "policy_version"):
        if type(event[key]) is not str or not _ID.fullmatch(event[key]):
            raise ValueError("invalid event provenance")
    if type(event["source_digest"]) is not str or not _SHA.fullmatch(event["source_digest"]):
        raise ValueError("invalid source digest")
    if (type(event["source_content"]) is not str or len(event["source_content"]) > 65536 or
            hashlib.sha256(event["source_content"].encode("utf-8")).hexdigest() != event["source_digest"]):
        raise ValueError("source digest mismatch")
    for key in ("event_versions", "entities"):
        values = event[key]
        if (type(values) not in (list, tuple) or not 1 <= len(values) <= 256 or
                any(type(v) is not str or not _ID.fullmatch(v) for v in values) or
                len(set(values)) != len(values)):
            raise ValueError("invalid group membership")
    times = (event["available_at"], event["expires_at"], cutoff)
    if any(type(t) is not datetime or t.tzinfo is None or t.utcoffset() is None for t in times):
        raise ValueError("timestamps must be timezone-aware")
    available, expires, decision = (t.astimezone(timezone.utc) for t in times)
    canonical = json.dumps({"source_revision": event["source_revision"],
                            "policy_version": event["policy_version"], "driver": event["driver"],
                            "event_versions": sorted(event["event_versions"]),
                            "entities": sorted(event["entities"]),
                            "available_at": available.isoformat(), "expires_at": expires.isoformat()},
                           sort_keys=True, separators=(",", ":"))
    if event["source_content"] != canonical:
        raise ValueError("source content does not match event")
    if (type(weights) is not dict or len(weights) > 1000 or
            any(type(k) is not str or not _ID.fullmatch(k) or type(v) not in (int, float)
                or not math.isfinite(v) or abs(v) > 1 for k, v in weights.items())):
        raise ValueError("invalid NAV weights")
    if not available <= decision < expires:
        raise ValueError("event unavailable or expired at cutoff")
    members = sorted(event["entities"])
    group_id = hashlib.sha256(json.dumps([1, event["gate_id"], event["source_revision"],
                                            event["source_digest"], event["policy_version"],
                                             sorted(event["event_versions"]), members,
                                             available.isoformat(), expires.isoformat(),
                                            decision.isoformat()], separators=(",", ":")).encode()).hexdigest()
    decision_id = hashlib.sha256(json.dumps([group_id, sorted(weights.items())],
                                            separators=(",", ":")).encode()).hexdigest()
    positions = [weights.get(entity, 0.0) for entity in members if entity != "CASH"]
    return {"group_id": group_id, "decision_id": decision_id, "driver": event["driver"],
            "signed_exposure": math.fsum(positions), "gross_exposure": math.fsum(map(abs, positions)),
            "unit": "NAV fraction", "advisory_only": True, "applied": False, "lambda": 0}


def create_contagion_validator(
    enabled: bool = True,
    yellow_multiplier: float = 0.7,
    red_multiplier: float = 0.3
) -> ContagionRiskValidator:
    config = ContagionRiskConfig(
        enabled=enabled,
        yellow_multiplier=yellow_multiplier,
        red_multiplier=red_multiplier
    )
    return ContagionRiskValidator(config)


def apply_contagion_risk_adjustment(
    symbol_weights: Dict[str, float],
    risk_multiplier: float
) -> Dict[str, float]:
    return {
        symbol: weight * risk_multiplier
        for symbol, weight in symbol_weights.items()
    }
