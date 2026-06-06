from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Tuple

from ..quant.position_sizer import TargetPortfolio


@dataclass(frozen=True)
class ApprovedPortfolio:
    """Portfolio approved by Layer 04 risk gate."""

    target_portfolio: TargetPortfolio
    risk_approved: bool = True
    approval_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskViolation:
    """Portfolio rejected by Layer 04 risk gate."""

    target_portfolio: TargetPortfolio
    violations: Tuple[str, ...]
    risk_approved: bool = False
