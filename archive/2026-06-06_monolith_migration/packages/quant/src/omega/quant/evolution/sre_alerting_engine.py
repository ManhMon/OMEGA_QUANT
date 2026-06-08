"""
SRE Alerting Engine for continuous learning drift detection.

PIT-safe rolling baselines use only historical observations via explicit lagging.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd


@dataclass
class SREAlertingConfig:
    """Configuration for continuous learning drift alerting."""

    sharpe_threshold: float = 0.15
    ic_threshold: float = 0.02
    lookback_days: int = 30


class SREAlertingEngine:
    """Vectorized drift detector for time-ordered Sharpe and IC monitoring."""

    def __init__(self, config: Optional[SREAlertingConfig] = None) -> None:
        self.config = config or SREAlertingConfig()
        if self.config.lookback_days <= 0:
            raise ValueError("lookback_days must be positive")

        self._metric_history = pd.DataFrame(columns=["timestamp", "name", "value"])

    def register_metric(self, name: str, value: float, timestamp: pd.Timestamp) -> None:
        """Register single metric observation for drift monitoring."""

        metric_name = str(name).strip().lower()
        metric_timestamp = pd.Timestamp(timestamp)

        new_row = pd.DataFrame(
            {
                "timestamp": [metric_timestamp],
                "name": [metric_name],
                "value": [float(value)],
            }
        )
        self._metric_history = pd.concat([self._metric_history, new_row], ignore_index=True)

    def check_drift(self) -> Tuple[bool, str]:
        """Check latest Sharpe and IC observations against PIT-safe rolling baselines."""

        if self._metric_history.empty:
            return False, "No metrics registered"

        wide_history = (
            self._metric_history.assign(timestamp=lambda frame: pd.to_datetime(frame["timestamp"], utc=False))
            .sort_values(["timestamp", "name"])
            .drop_duplicates(subset=["timestamp", "name"], keep="last")
            .pivot(index="timestamp", columns="name", values="value")
            .sort_index()
        )

        monitored = wide_history.reindex(columns=["sharpe", "ic"])
        if monitored.dropna(how="all").empty:
            return False, "No sharpe/ic metrics registered"

        rolling_baseline = monitored.shift(1).rolling(
            window=f"{self.config.lookback_days}D",
            min_periods=self.config.lookback_days,
        ).mean()

        latest_values = monitored.iloc[-1]
        latest_baseline = rolling_baseline.iloc[-1]

        triggered_metrics: List[str] = []

        sharpe_value = latest_values.get("sharpe")
        sharpe_baseline = latest_baseline.get("sharpe")
        if pd.notna(sharpe_value) and pd.notna(sharpe_baseline):
            if float(sharpe_value) < min(float(sharpe_baseline), self.config.sharpe_threshold):
                triggered_metrics.append(
                    f"sharpe drift: current={float(sharpe_value):.4f}, baseline={float(sharpe_baseline):.4f}, threshold={self.config.sharpe_threshold:.4f}"
                )

        ic_value = latest_values.get("ic")
        ic_baseline = latest_baseline.get("ic")
        if pd.notna(ic_value) and pd.notna(ic_baseline):
            if float(ic_value) < min(float(ic_baseline), self.config.ic_threshold):
                triggered_metrics.append(
                    f"ic drift: current={float(ic_value):.4f}, baseline={float(ic_baseline):.4f}, threshold={self.config.ic_threshold:.4f}"
                )

        if not triggered_metrics:
            if latest_baseline.isna().all():
                return False, "Insufficient lookback history for drift check"
            return False, "No drift detected"

        return True, "; ".join(triggered_metrics)
