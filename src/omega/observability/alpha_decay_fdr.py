from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt
from typing import Mapping, Sequence

import numpy as np

from omega.quant.walk_forward.risk_adjusted_alpha_score import bh_fdr_qvalues

try:
    from scipy.stats import ttest_1samp
except ImportError:  # pragma: no cover
    ttest_1samp = None


@dataclass(frozen=True)
class AlphaDecayFDRResult:
    alpha_name: str
    baseline_ic: float
    recent_mean_ic: float
    t_stat: float
    p_value: float
    q_value: float
    sample_size: int
    is_decayed: bool


class AlphaDecayMonitorFDR:
    def __init__(self, q_threshold: float = 0.05, min_samples: int = 5):
        self.q_threshold = float(q_threshold)
        self.min_samples = int(min_samples)

    def evaluate_pool(
        self,
        recent_ic_by_alpha: Mapping[str, Sequence[float]],
        baseline_ic_by_alpha: Mapping[str, float],
    ) -> list[AlphaDecayFDRResult]:
        raw_results: list[dict[str, float | int | str | bool]] = []
        p_values: list[float] = []

        for alpha_name, recent_ic in recent_ic_by_alpha.items():
            if alpha_name not in baseline_ic_by_alpha:
                raise KeyError(f"Missing baseline IC for '{alpha_name}'")

            values = np.asarray(recent_ic, dtype=np.float64)
            values = values[np.isfinite(values)]
            baseline_ic = float(baseline_ic_by_alpha[alpha_name])
            recent_mean_ic = float(values.mean()) if values.size else 0.0
            t_stat, p_value = self._left_tailed_ttest(values, baseline_ic)
            p_values.append(p_value)
            raw_results.append(
                {
                    "alpha_name": alpha_name,
                    "baseline_ic": baseline_ic,
                    "recent_mean_ic": recent_mean_ic,
                    "t_stat": t_stat,
                    "p_value": p_value,
                    "sample_size": int(values.size),
                    "is_below_baseline": recent_mean_ic < baseline_ic,
                }
            )

        q_values = bh_fdr_qvalues(p_values)
        results: list[AlphaDecayFDRResult] = []
        for row, q_value in zip(raw_results, q_values):
            is_decayed = bool(
                row["sample_size"] >= self.min_samples
                and row["is_below_baseline"]
                and q_value <= self.q_threshold
            )
            results.append(
                AlphaDecayFDRResult(
                    alpha_name=str(row["alpha_name"]),
                    baseline_ic=float(row["baseline_ic"]),
                    recent_mean_ic=float(row["recent_mean_ic"]),
                    t_stat=float(row["t_stat"]),
                    p_value=float(row["p_value"]),
                    q_value=float(q_value),
                    sample_size=int(row["sample_size"]),
                    is_decayed=is_decayed,
                )
            )
        return results

    @staticmethod
    def _left_tailed_ttest(values: np.ndarray, baseline_ic: float) -> tuple[float, float]:
        if values.size < 2:
            return 0.0, 1.0

        recent_mean_ic = float(values.mean())
        if ttest_1samp is not None:
            t_stat, p_value = ttest_1samp(values, baseline_ic, alternative="less")
            if np.isfinite(t_stat) and np.isfinite(p_value):
                if recent_mean_ic >= baseline_ic:
                    return float(t_stat), 1.0
                return float(t_stat), float(p_value)

        sample_std = float(np.std(values, ddof=1))
        if sample_std <= 0.0:
            if recent_mean_ic < baseline_ic:
                return float("-inf"), 0.0
            return 0.0, 1.0

        t_stat = (recent_mean_ic - baseline_ic) / (sample_std / sqrt(values.size))
        if recent_mean_ic >= baseline_ic:
            return float(t_stat), 1.0

        # ponytail: normal-tail fallback; upgrade to exact Student-t CDF if scipy ever becomes optional in prod.
        p_value = 0.5 * (1.0 + erf(t_stat / sqrt(2.0)))
        return float(t_stat), float(min(max(p_value, 0.0), 1.0))
