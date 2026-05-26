"""Performance Attribution Engine for OMEGA_QUANT Phase 21.

Implements Brinson-Hood-Beebower (BHB) attribution:
- Active Return = Factor Return + Selection Return
- Risk-adjusted metrics: Sharpe Ratio, Information Ratio
- Sector/Industry attribution (allocation + selection + interaction)

PIT Safety Mandatory:
- All returns at time t must use data from t-1 or earlier (no lookahead)
- metadata['pit_compliant'] = True signals enforcement at call site

Vectorized NumPy/Pandas throughout (no Python loops over rows).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


def _align_series(*series: pd.Series) -> list[pd.Series]:
    """Align multiple Series by index intersection, fail fast if empty."""
    if len(series) < 2:
        return list(series)
    
    # Start with first series
    res = series[0]
    for s in series[1:]:
        res, _ = res.align(s, join="inner")
        
    if len(res) == 0:
        raise ValueError("Index alignment resulted in empty series (no overlapping timestamps).")
    
    # Re-align all to the intersected index
    out = []
    for s in series:
        s_aligned, _ = s.align(res, join="inner")
        out.append(s_aligned)
    return out


def _validate_pit(
    series_list: list[pd.Series],
    current_time: Optional[pd.Timestamp] = None,
    as_of: Optional[pd.Timestamp] = None,
    available_at: Optional[pd.Timestamp] = None,
    pit_strict: bool = True,
    daily_bar: bool = True,
) -> bool:
    """Verify PIT contract: monotonic index, no future dates relative to current_time.

    Enforces strict T-1 lag for daily bars:
    - When daily_bar=True (default), index dates must be strictly before the
      decision date (date(current_time)), i.e. same-day bars are rejected.
    - When daily_bar=False, index timestamps must be strictly before current_time
      (intraday precision).
    - as_of / available_at: available_at must be strictly after as_of.
    - Raises ValueError if pit_strict=True and any check fails.
    """
    now = current_time or pd.Timestamp.now(tz='UTC')

    # Check physical as_of/available_at lag
    if as_of is not None and available_at is not None:
        if available_at <= as_of:
            if pit_strict:
                raise ValueError(
                    f"PIT violation: available_at {available_at} must be strictly "
                    f"after as_of {as_of} (T-1 lag)"
                )
            return False

    for s in series_list:
        # Sector indices use string symbols — skip monotonicity/date checks.
        idx = s.index
        if not isinstance(idx, pd.DatetimeIndex):
            continue

        # 1. Monotonicity check
        if not idx.is_monotonic_increasing:
            if pit_strict:
                raise ValueError("PIT violation: index must be monotonically increasing")
            return False

        # 2. Normalise timezone for comparison
        idx_tz = idx.tz
        if idx_tz is not None and now.tz is None:
            now_cmp = now.tz_localize('UTC')
        elif idx_tz is None and now.tz is not None:
            now_cmp = now.tz_localize(None)
        else:
            now_cmp = now

        # 3. T-1 lag enforcement
        if daily_bar:
            # Daily bars: index DATE must be strictly before decision DATE.
            # Same-day bar (bar_date == decision_date) is rejected — no look-ahead.
            #
            # Cross-timezone leak fix: calendar-date comparison must happen in the
            # index's own timezone. Convert now_cmp into idx.tz so both sides are
            # expressed as local calendar dates in the same zone before normalizing.
            # The opposite (converting idx to now_cmp.tz) is wrong: it shifts the
            # UTC instant, so 2026-05-19 00:00+07:00 becomes 2026-05-18 17:00 UTC
            # and normalizes to 2026-05-18 — incorrectly passing a same-day bar.
            if idx_tz is not None and now_cmp.tz is not None:
                # Both tz-aware: express decision time in the index's local timezone
                decision_date = now_cmp.tz_convert(idx_tz).normalize()
            elif idx_tz is None and now_cmp.tz is None:
                # Both naive: normalize directly
                decision_date = now_cmp.normalize()
            else:
                # Mixed (already handled above by now_cmp adjustment): normalize as-is
                decision_date = now_cmp.normalize()
            if (idx.normalize() >= decision_date).any():
                if pit_strict:
                    raise ValueError(
                        f"PIT violation: daily bar index contains dates on or after "
                        f"decision date {decision_date.date()} (T-1 required)"
                    )
                return False
        else:
            # Intraday precision: timestamp must be strictly before now_cmp
            if (idx >= now_cmp).any():
                if pit_strict:
                    raise ValueError(
                        f"PIT violation: data index contains timestamps at or after "
                        f"decision time {now_cmp}"
                    )
                return False

    return True


@dataclass
class AttributionConfig:
    benchmarks: Dict[str, pd.Series] = field(default_factory=dict)
    factor_groups: Dict[str, List[str]] = field(default_factory=dict)
    risk_free_rate: float = 0.0
    periods_per_year: int = 252
    pit_compliant: bool = True

    def __post_init__(self) -> None:
        if not self.pit_compliant:
            raise ValueError("PIT compliance mandatory. Set pit_compliant=True.")


class PerformanceAttribution:
    """Vectorized performance attribution engine with strict SOD and PIT guards."""

    def __init__(self, config: Optional[AttributionConfig] = None) -> None:
        self.config = config or AttributionConfig()
        self._rfr = self.config.risk_free_rate
        self._ppy = self.config.periods_per_year

    def decompose_returns(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series,
        current_time: Optional[pd.Timestamp] = None,
        as_of: Optional[pd.Timestamp] = None,
        available_at: Optional[pd.Timestamp] = None,
        pit_strict: bool = True,
    ) -> Dict:
        """Decompose active return with strict index alignment and PIT validation."""
        # Sanitize non-finite values (NaN / inf) to prevent propagation
        p_clean = portfolio_returns.copy()
        b_clean = benchmark_returns.copy()
        
        # Replace inf with NaN, then forward fill/zero fill
        p_clean = p_clean.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        b_clean = b_clean.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        
        port, bench = _align_series(p_clean, b_clean)
        pit_valid = _validate_pit(
            [port, bench],
            current_time=current_time,
            as_of=as_of,
            available_at=available_at,
            pit_strict=pit_strict
        )
        
        p = port.values.astype(float)
        b = bench.values.astype(float)

        var_bench = np.var(b, ddof=1)
        cov_pb = np.cov(p, b, ddof=1)[0, 1] if len(p) > 1 else 0.0
        beta = cov_pb / var_bench if var_bench > 1e-12 else 0.0

        total_port = float(np.sum(p))
        total_bench = float(np.sum(b))
        active_return = total_port - total_bench

        factor_return = (beta - 1.0) * total_bench
        selection_return = active_return - factor_return

        return {
            "total_portfolio_return": total_port,
            "total_benchmark_return": total_bench,
            "active_return": active_return,
            "beta": beta,
            "factor_return": factor_return,
            "selection_return": selection_return,
            "metadata": {
                "pit_compliant": pit_valid,
                "n_periods": len(p),
                "phase": "Phase21-Attribution",
            },
        }

    def sharpe_ratio(
        self,
        returns: pd.Series,
        annualise: bool = True,
        current_time: Optional[pd.Timestamp] = None,
        as_of: Optional[pd.Timestamp] = None,
        available_at: Optional[pd.Timestamp] = None,
        pit_strict: bool = True,
    ) -> float:
        """Annualised Sharpe ratio with n<2 guard and PIT validation."""
        if len(returns) < 2:
            return 0.0
        
        # Sanitize non-finite values
        r_clean = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        
        pit_valid = _validate_pit(
            [r_clean],
            current_time=current_time,
            as_of=as_of,
            available_at=available_at,
            pit_strict=pit_strict
        )
            
        r = r_clean.values.astype(float)
        rfr_per_period = self._rfr / self._ppy
        excess = r - rfr_per_period
        mean_e = np.mean(excess)
        std_e = np.std(excess, ddof=1)
        
        if std_e < 1e-12 or not np.isfinite(std_e):
            return 0.0
        
        ratio = mean_e / std_e
        return float(ratio * np.sqrt(self._ppy)) if annualise else float(ratio)

    def information_ratio(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series,
        annualise: bool = True,
        current_time: Optional[pd.Timestamp] = None,
        as_of: Optional[pd.Timestamp] = None,
        available_at: Optional[pd.Timestamp] = None,
        pit_strict: bool = True,
    ) -> float:
        """Annualised IR with strict alignment, n<2 guard, and PIT validation."""
        if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
            return 0.0
            
        p_clean = portfolio_returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        b_clean = benchmark_returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        
        port, bench = _align_series(p_clean, b_clean)
        if len(port) < 2:
            return 0.0
            
        pit_valid = _validate_pit(
            [port, bench],
            current_time=current_time,
            as_of=as_of,
            available_at=available_at,
            pit_strict=pit_strict
        )
        
        a = port.values.astype(float) - bench.values.astype(float)
        mean_a = np.mean(a)
        std_a = np.std(a, ddof=1)
        
        if std_a < 1e-12 or not np.isfinite(std_a):
            return 0.0
            
        ratio = mean_a / std_a
        return float(ratio * np.sqrt(self._ppy)) if annualise else float(ratio)

    def tracking_error(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series,
        annualise: bool = True,
    ) -> float:
        """Annualised tracking error with alignment and n<2 guard."""
        if len(portfolio_returns) < 2 or len(benchmark_returns) < 2:
            return 0.0
            
        p_clean = portfolio_returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        b_clean = benchmark_returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        
        port, bench = _align_series(p_clean, b_clean)
        if len(port) < 2:
            return 0.0
            
        a = port.values.astype(float) - bench.values.astype(float)
        std_a = np.std(a, ddof=1)
        if not np.isfinite(std_a):
            return 0.0
        return float(std_a * np.sqrt(self._ppy)) if annualise else float(std_a)

    def sector_attribution(
        self,
        portfolio_weights: pd.Series,
        benchmark_weights: pd.Series,
        sector_returns: pd.Series,
        sectors: pd.Series,
        current_time: Optional[pd.Timestamp] = None,
        as_of: Optional[pd.Timestamp] = None,
        available_at: Optional[pd.Timestamp] = None,
        pit_strict: bool = True,
    ) -> pd.DataFrame:
        """BHB sector attribution with intersection alignment and PIT validation."""
        # Sanitize inputs
        pw_c = portfolio_weights.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        bw_c = benchmark_weights.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        sr_c = sector_returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        
        assets = pw_c.index.intersection(bw_c.index)\
                           .intersection(sr_c.index)\
                           .intersection(sectors.index)
        
        if len(assets) == 0:
            raise ValueError("No overlapping assets found for sector attribution.")

        pw = pw_c.loc[assets].values.astype(float)
        bw = bw_c.loc[assets].values.astype(float)
        r = sr_c.loc[assets].values.astype(float)
        s = sectors.loc[assets].values

        sector_labels = np.unique(s)
        records = []
        rb_total = float(np.dot(bw, r))

        for sec in sector_labels:
            mask = s == sec
            pw_s = float(pw[mask].sum())
            bw_s = float(bw[mask].sum())

            rp_s = float(np.dot(pw[mask], r[mask]) / pw_s) if pw_s > 1e-12 else 0.0
            rb_s = float(np.dot(bw[mask], r[mask]) / bw_s) if bw_s > 1e-12 else 0.0

            alloc = (pw_s - bw_s) * (rb_s - rb_total)
            select = bw_s * (rp_s - rb_s)
            interact = (pw_s - bw_s) * (rp_s - rb_s)
            total = alloc + select + interact

            records.append({
                "sector": sec,
                "allocation": alloc,
                "selection": select,
                "interaction": interact,
                "total": total,
                "port_weight": pw_s,
                "bench_weight": bw_s,
                "port_return": rp_s,
                "bench_return": rb_s,
            })

        result = pd.DataFrame(records).set_index("sector")
        result.attrs["pit_compliant"] = _validate_pit(
            [sr_c],
            current_time=current_time,
            as_of=as_of,
            available_at=available_at,
            pit_strict=pit_strict
        )
        result.attrs["phase"] = "Phase21-Attribution"
        return result

    def factor_exposures(
        self,
        returns_df: pd.DataFrame,
        factor_returns: pd.DataFrame,
    ) -> pd.DataFrame:
        """OLS factor exposures per asset. Aligns by timestamp index, then drops
        any row where NaN or inf is present in either returns or factors before OLS.
        This prevents missing observations from distorting beta estimates.
        """
        # Replace inf with NaN — do NOT fillna(0) here; zeros would bias OLS.
        ret_c = returns_df.replace([np.inf, -np.inf], np.nan)
        fac_c = factor_returns.replace([np.inf, -np.inf], np.nan)

        # Strict index intersection check
        common_idx = ret_c.index.intersection(fac_c.index)
        if len(common_idx) == 0:
            raise ValueError(
                "Index alignment resulted in empty series (no overlapping timestamps)."
            )

        ret_aligned = ret_c.loc[common_idx]
        fac_aligned = fac_c.loc[common_idx]

        # Drop rows where ANY column in either DataFrame has NaN (per timestamp).
        # This ensures only complete observations enter OLS — no zero-fill distortion.
        combined = pd.concat([fac_aligned, ret_aligned], axis=1)
        valid_mask = combined.notna().all(axis=1)
        ret_clean = ret_aligned.loc[valid_mask]
        fac_clean = fac_aligned.loc[valid_mask]

        if len(ret_clean) == 0:
            raise ValueError(
                "No complete observations remain after dropping rows with NaN/inf "
                "in factor_exposures. Cannot estimate betas."
            )

        R = ret_clean.values.astype(float)
        F = fac_clean.values.astype(float)
        FtF = F.T @ F
        FtR = F.T @ R
        try:
            betas = np.linalg.solve(FtF, FtR)
        except np.linalg.LinAlgError:
            betas = np.linalg.lstsq(F, R, rcond=None)[0]

        return pd.DataFrame(betas, index=factor_returns.columns, columns=returns_df.columns)

    def cumulative_returns(self, returns: pd.Series) -> pd.Series:
        r_clean = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return (1.0 + r_clean).cumprod() - 1.0

    def max_drawdown(self, returns: pd.Series) -> float:
        r_clean = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        cum = (1.0 + r_clean).cumprod()
        rolling_max = cum.cummax()
        drawdowns = cum / rolling_max - 1.0
        val = drawdowns.min()
        return float(val) if np.isfinite(val) else 0.0
