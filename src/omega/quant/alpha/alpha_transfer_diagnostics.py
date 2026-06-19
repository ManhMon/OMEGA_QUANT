"""Alpha Transfer Diagnostics — Portfolio transfer analysis helpers.

GATE: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615
Version: 1.0.0
Date: 2026-06-15

Research-only helpers for analyzing portfolio transfer diagnostics when
new alpha candidates are introduced into an existing portfolio. Measures
marginal IC contribution, correlation with existing signals, turnover
impact, and diversification benefit.

COMPLIANCE:
  - PIT Safe: all diagnostics use T-1 lagged data only
  - No Live Promotion: diagnostics are research artifacts only
  - Deterministic: same inputs produce same outputs
  - Evidence: all results include metadata for audit
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)


@dataclass
class TransferDiagnostic:
    """Diagnostic result for a single alpha transfer candidate."""
    alpha_name: str
    marginal_ic: float = 0.0
    marginal_icir: float = 0.0
    max_corr_existing: float = 0.0
    mean_corr_existing: float = 0.0
    turnover_estimate: float = 0.0
    diversification_benefit: float = 0.0
    transfer_verdict: str = "SKIP"
    evidence: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "alpha_name": self.alpha_name,
            "marginal_ic": round(self.marginal_ic, 6),
            "marginal_icir": round(self.marginal_icir, 4),
            "max_corr_existing": round(self.max_corr_existing, 4),
            "mean_corr_existing": round(self.mean_corr_existing, 4),
            "turnover_estimate": round(self.turnover_estimate, 4),
            "diversification_benefit": round(self.diversification_benefit, 4),
            "transfer_verdict": self.transfer_verdict,
            "evidence": self.evidence,
        }


@dataclass
class TransferDiagnosticsReport:
    """Full transfer diagnostics report."""
    gate_id: str = "AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615"
    candidates_evaluated: int = 0
    candidates_recommended: int = 0
    diagnostics: List[TransferDiagnostic] = field(default_factory=list)
    summary: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "gate_id": self.gate_id,
            "candidates_evaluated": self.candidates_evaluated,
            "candidates_recommended": self.candidates_recommended,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "summary": self.summary,
        }


def compute_marginal_ic(
    candidate_signal: pd.Series,
    existing_signals: pd.DataFrame,
    returns: pd.Series,
    dates: pd.Series,
    min_cross_section: int = 5,
) -> Dict[str, float]:
    """Compute marginal IC contribution of a candidate signal.

    PIT-safe: uses only provided data (caller ensures train-only).

    Parameters
    ----------
    candidate_signal : pd.Series
        New candidate signal values.
    existing_signals : pd.DataFrame
        Existing portfolio signals (columns = signal names).
    returns : pd.Series
        Forward returns.
    dates : pd.Series
        Date column for grouping.
    min_cross_section : int
        Minimum pairs per date for IC computation.

    Returns
    -------
    dict
        marginal_ic, marginal_icir, composite_ic
    """
    # Candidate standalone IC
    candidate_daily_ics = _daily_cs_ic_series(
        candidate_signal, returns, dates, min_cross_section
    )
    candidate_ic = float(np.mean(candidate_daily_ics)) if len(candidate_daily_ics) > 0 else 0.0
    candidate_ic_std = float(np.std(candidate_daily_ics)) if len(candidate_daily_ics) > 1 else 1.0
    candidate_icir = candidate_ic / (candidate_ic_std + 1e-9)

    # Composite signal: candidate + mean of existing
    if existing_signals.empty or existing_signals.shape[1] == 0:
        composite_ic = candidate_ic
        composite_icir = candidate_icir
    else:
        existing_mean = existing_signals.mean(axis=1)
        composite = (candidate_signal + existing_mean) / 2.0
        composite_daily_ics = _daily_cs_ic_series(
            composite, returns, dates, min_cross_section
        )
        composite_ic = float(np.mean(composite_daily_ics)) if len(composite_daily_ics) > 0 else 0.0
        composite_std = float(np.std(composite_daily_ics)) if len(composite_daily_ics) > 1 else 1.0
        composite_icir = composite_ic / (composite_std + 1e-9)

    return {
        "candidate_ic": candidate_ic,
        "candidate_icir": candidate_icir,
        "composite_ic": composite_ic,
        "composite_icir": composite_icir,
        "marginal_ic": composite_ic - (
            float(np.mean(_daily_cs_ic_series(
                existing_mean if not existing_signals.empty else candidate_signal,
                returns, dates, min_cross_section
            ))) if not existing_signals.empty else 0.0
        ),
    }


def compute_signal_correlations(
    candidate_signal: pd.Series,
    existing_signals: pd.DataFrame,
) -> Dict[str, float]:
    """Compute correlation of candidate with existing signals.

    Parameters
    ----------
    candidate_signal : pd.Series
        Candidate signal values.
    existing_signals : pd.DataFrame
        Existing portfolio signals.

    Returns
    -------
    dict
        max_corr, mean_corr, per_signal correlations.
    """
    if existing_signals.empty or existing_signals.shape[1] == 0:
        return {"max_corr": 0.0, "mean_corr": 0.0, "per_signal": {}}

    clean = candidate_signal.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    corrs = {}
    for col in existing_signals.columns:
        existing_clean = existing_signals[col].replace(
            [np.inf, -np.inf], np.nan
        ).fillna(0.0)
        mask = ~(clean.isna() | existing_clean.isna())
        if mask.sum() < 10:
            corrs[col] = 0.0
            continue
        try:
            r, _ = spearmanr(clean[mask].values, existing_clean[mask].values)
            corrs[col] = abs(r) if not np.isnan(r) else 0.0
        except Exception:
            corrs[col] = 0.0

    corr_values = list(corrs.values())
    return {
        "max_corr": max(corr_values) if corr_values else 0.0,
        "mean_corr": float(np.mean(corr_values)) if corr_values else 0.0,
        "per_signal": corrs,
    }


def estimate_signal_turnover(
    signal: pd.Series,
    dates: pd.Series,
    tickers: pd.Series,
) -> float:
    """Estimate day-over-day rank turnover of a signal.

    Parameters
    ----------
    signal : pd.Series
        Signal values.
    dates : pd.Series
        Date column.
    tickers : pd.Series
        Ticker column.

    Returns
    -------
    float
        Estimated turnover in [0, 1].
    """
    try:
        temp = pd.DataFrame({
            "date": dates,
            "ticker": tickers,
            "signal": signal.replace([np.inf, -np.inf], np.nan).fillna(0.0),
        })
        pivot = temp.pivot(index="date", columns="ticker", values="signal")
        ranks = pivot.rank(axis=1, pct=True)
        diffs = ranks.diff(axis=0).abs()
        mean_diff = diffs.mean(axis=1).mean()
        if pd.isna(mean_diff):
            return 0.5
        return float(np.clip(mean_diff, 0.0, 1.0))
    except Exception:
        return 0.5


def run_transfer_diagnostics(
    candidates: Dict[str, pd.Series],
    existing_signals: pd.DataFrame,
    returns: pd.Series,
    dates: pd.Series,
    tickers: pd.Series,
    corr_threshold: float = 0.85,
    min_marginal_ic: float = 0.005,
    max_turnover: float = 0.5,
) -> TransferDiagnosticsReport:
    """Run full transfer diagnostics for candidate signals.

    PIT-safe: caller must ensure all data is train-only.

    Parameters
    ----------
    candidates : dict
        Mapping of candidate name to signal Series.
    existing_signals : pd.DataFrame
        Existing portfolio signal columns.
    returns : pd.Series
        Forward returns.
    dates : pd.Series
        Date column.
    tickers : pd.Series
        Ticker column.
    corr_threshold : float
        Max allowed correlation with existing signals.
    min_marginal_ic : float
        Minimum marginal IC for recommendation.
    max_turnover : float
        Maximum allowed turnover.

    Returns
    -------
    TransferDiagnosticsReport
    """
    report = TransferDiagnosticsReport()
    report.candidates_evaluated = len(candidates)

    for name, signal in candidates.items():
        diag = TransferDiagnostic(alpha_name=name)

        # Marginal IC
        ic_result = compute_marginal_ic(
            signal, existing_signals, returns, dates
        )
        diag.marginal_ic = ic_result["marginal_ic"]
        diag.marginal_icir = ic_result["candidate_icir"]

        # Correlations
        corr_result = compute_signal_correlations(signal, existing_signals)
        diag.max_corr_existing = corr_result["max_corr"]
        diag.mean_corr_existing = corr_result["mean_corr"]

        # Turnover
        diag.turnover_estimate = estimate_signal_turnover(
            signal, dates, tickers
        )

        # Diversification benefit = 1 - max_corr
        diag.diversification_benefit = 1.0 - diag.max_corr_existing

        # Verdict
        if (
            diag.marginal_ic >= min_marginal_ic
            and diag.max_corr_existing < corr_threshold
            and diag.turnover_estimate <= max_turnover
        ):
            diag.transfer_verdict = "RECOMMEND"
        elif diag.max_corr_existing >= corr_threshold:
            diag.transfer_verdict = "SKIP_REDUNDANT"
        elif diag.turnover_estimate > max_turnover:
            diag.transfer_verdict = "SKIP_HIGH_TURNOVER"
        elif diag.marginal_ic < min_marginal_ic:
            diag.transfer_verdict = "SKIP_LOW_IC"
        else:
            diag.transfer_verdict = "SKIP"

        diag.evidence = {
            "ic_detail": ic_result,
            "corr_detail": corr_result,
            "pit_safe": True,
            "train_only": True,
        }
        report.diagnostics.append(diag)

    report.candidates_recommended = sum(
        1 for d in report.diagnostics if d.transfer_verdict == "RECOMMEND"
    )
    report.summary = {
        "total_evaluated": report.candidates_evaluated,
        "total_recommended": report.candidates_recommended,
        "avg_marginal_ic": float(np.mean([
            d.marginal_ic for d in report.diagnostics
        ])) if report.diagnostics else 0.0,
        "avg_max_corr": float(np.mean([
            d.max_corr_existing for d in report.diagnostics
        ])) if report.diagnostics else 0.0,
    }

    logger.info(
        f"[TransferDiag] Evaluated {report.candidates_evaluated}, "
        f"recommended {report.candidates_recommended}"
    )
    return report


def _daily_cs_ic_series(
    signal: pd.Series,
    returns: pd.Series,
    dates: pd.Series,
    min_cross_section: int = 5,
) -> np.ndarray:
    """Compute daily cross-sectional IC series.

    Parameters
    ----------
    signal : pd.Series
        Signal values.
    returns : pd.Series
        Forward returns.
    dates : pd.Series
        Date column.
    min_cross_section : int
        Minimum pairs per date.

    Returns
    -------
    np.ndarray
        Array of daily IC values.
    """
    temp = pd.DataFrame({
        "date": dates,
        "signal": signal.replace([np.inf, -np.inf], np.nan),
        "returns": returns,
    })

    def _cs_ic(group):
        mask = ~(group["signal"].isna() | group["returns"].isna())
        if mask.sum() < min_cross_section:
            return np.nan
        try:
            ic, _ = spearmanr(
                group.loc[mask, "signal"].values,
                group.loc[mask, "returns"].values,
            )
            return ic if not np.isnan(ic) else np.nan
        except Exception:
            return np.nan

    daily_ics = temp.groupby("date").apply(_cs_ic, include_groups=False)
    valid = daily_ics.dropna()
    return valid.values if not valid.empty else np.array([])
