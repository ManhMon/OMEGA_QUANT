from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Sequence

import numpy as np

from omega.quant.validation.dsr import annualized_sharpe
from omega.quant.validation.dsr import deflated_sharpe_ratio


@dataclass
class SharpeAudit:
    n: int
    mean_return: float
    std_return: float
    risk_free_rate: float
    sharpe_per_bar: float
    sharpe_annualized: float
    periods_per_year: int
    excess_return_applied: bool


def audit_sharpe(
    returns: Sequence[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> SharpeAudit:
    values = np.asarray(list(returns), dtype=float)
    excess = values - float(risk_free_rate)
    n_obs = int(excess.size)
    mean = float(excess.mean()) if n_obs else 0.0
    if n_obs < 2:
        return SharpeAudit(
            n=n_obs,
            mean_return=mean,
            std_return=0.0,
            risk_free_rate=float(risk_free_rate),
            sharpe_per_bar=0.0,
            sharpe_annualized=0.0,
            periods_per_year=int(periods_per_year),
            excess_return_applied=bool(risk_free_rate),
        )
    std = float(np.std(excess, ddof=1))
    tol = 1e-12 * max(abs(mean), 1.0)
    sharpe = 0.0 if std < tol else float(mean / std)
    return SharpeAudit(
        n=n_obs,
        mean_return=mean,
        std_return=0.0 if std < tol else std,
        risk_free_rate=float(risk_free_rate),
        sharpe_per_bar=sharpe,
        sharpe_annualized=float(sharpe * sqrt(periods_per_year)),
        periods_per_year=int(periods_per_year),
        excess_return_applied=bool(risk_free_rate),
    )


def assert_matches_production(returns: Sequence[float]) -> None:
    values = np.asarray(list(returns), dtype=float)
    audit = audit_sharpe(values)
    dsr_ann = annualized_sharpe(
        values,
        periods_per_year=audit.periods_per_year,
    )
    dsr_res = deflated_sharpe_ratio(
        values,
        n_trials=1,
        periods_per_year=audit.periods_per_year,
    )
    if abs(dsr_ann - audit.sharpe_annualized) > 1e-9:
        raise AssertionError(
            f"annualized_sharpe mismatch: {dsr_ann} != "
            f"{audit.sharpe_annualized}"
        )
    if abs(dsr_res.sr - audit.sharpe_per_bar) > 1e-9:
        raise AssertionError(
            f"deflated_sharpe_ratio.sr mismatch: {dsr_res.sr} != "
            f"{audit.sharpe_per_bar}"
        )
    if abs(dsr_res.sr_annualized - audit.sharpe_annualized) > 1e-9:
        raise AssertionError(
            "deflated_sharpe_ratio.sr_annualized mismatch: "
            f"{dsr_res.sr_annualized} != {audit.sharpe_annualized}"
        )
