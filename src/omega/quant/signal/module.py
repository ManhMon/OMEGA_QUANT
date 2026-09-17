"""
Signal Module - Contract-based score-to-signal transformation.

Implements SIGNAL_MODULE spec:
- ranking, threshold, smoothing only
- output signal: enum[BUY, SELL, HOLD]
- reject on invalid threshold configuration

Input:
- scores: ScoreVector

Output:
- SignalVector

Compliance: OMEGA+++ Quant AI Institutional Grade
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class SignalModuleConfig:
    ranking_field: str = "score"
    top_percent: float = 0.1
    bottom_percent: float = 0.1
    score_threshold: float = 0.0
    neutral_zone: float = 0.0


class SignalModule:
    """Generate trade signals (BUY/SELL/HOLD) from ScoreVector."""

    CONTRACT_HASH = "67f807d6c0a535f40b29f802ac354976fd75d7bab76afe73bd9e07e7508a6126"

    def __init__(self, config: SignalModuleConfig | None = None):
        self.config = config or SignalModuleConfig()

        if self.config.top_percent < 0 or self.config.top_percent > 1:
            raise ValueError("invalid_threshold: top_percent must be in [0, 1]")
        if self.config.bottom_percent < 0 or self.config.bottom_percent > 1:
            raise ValueError("invalid_threshold: bottom_percent must be in [0, 1]")
        if self.config.top_percent + self.config.bottom_percent > 1:
            raise ValueError("invalid_threshold: top_percent + bottom_percent > 1")

    def _validate_input(self, score_vector: Dict[str, Any]) -> None:
        if not isinstance(score_vector, dict):
            raise TypeError("ScoreVector must be a dict")
        if score_vector.get("type") != "ScoreVector":
            raise ValueError("Input type must be ScoreVector")
        if "index" not in score_vector or "data" not in score_vector:
            raise ValueError("Missing index/data in ScoreVector")

    def transform(self, score_vector: Dict[str, Any]) -> Dict[str, Any]:
        """Convert scores to signals via cross-sectional ranking per timestamp."""
        self._validate_input(score_vector)

        cfg = self.config
        idx_ts = sorted(list(set(score_vector["index"]["timestamp"])))
        idx_sym = sorted(list(set(score_vector["index"]["symbol"])))

        out_data: Dict[str, Dict[int, Dict[str, str]]] = {sym: {} for sym in idx_sym}

        for ts in idx_ts:
            ts_scores: List[tuple[str, float]] = []
            for sym in idx_sym:
                sym_data = score_vector["data"].get(sym, {})
                score_dict = sym_data.get(ts)
                if score_dict is not None and cfg.ranking_field in score_dict:
                    if score_dict.get("limit_lock", False):
                        out_data[sym][ts] = {"signal": "HOLD"}
                        continue
                    val = float(score_dict[cfg.ranking_field])
                    if math.isfinite(val):
                        ts_scores.append((sym, val))
                    else:
                        out_data[sym][ts] = {"signal": "HOLD"}

            if not ts_scores:
                continue

            ts_scores.sort(key=lambda x: (x[1], x[0]), reverse=True)

            if len(ts_scores) > 1 and ts_scores[0][1] == ts_scores[-1][1]:
                for sym, _ in ts_scores:
                    out_data[sym][ts] = {"signal": "HOLD"}
                continue

            n = len(ts_scores)
            n_buy = max(1, int(n * cfg.top_percent)) if cfg.top_percent > 0 else 0
            n_sell = max(1, int(n * cfg.bottom_percent)) if cfg.bottom_percent > 0 else 0

            for rank, (sym, score) in enumerate(ts_scores):
                signal = "HOLD"

                if abs(score) <= cfg.neutral_zone:
                    signal = "HOLD"
                else:
                    is_top = rank < n_buy
                    is_bottom = rank >= (n - n_sell)

                    if is_top and score >= cfg.score_threshold:
                        signal = "BUY"
                    elif is_bottom and score <= -cfg.score_threshold:
                        signal = "SELL"

                out_data[sym][ts] = {"signal": signal}

        return {
            "index": score_vector["index"],
            "type": "SignalVector",
            "data": out_data,
        }
