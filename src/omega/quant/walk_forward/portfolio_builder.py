"""Portfolio construction mixin for walk-forward engine."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage 2: reuse sector-cap enforcement from alpha_pipeline (no duplication)
# ---------------------------------------------------------------------------
def _import_apply_sector_caps():
    """Lazy import of _apply_sector_caps from alpha_pipeline.

    Searches for alpha_pipeline.py relative to this file's location so the
    import works regardless of the working directory.
    """
    _scripts_dir = str(Path(__file__).resolve().parents[4] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    from alpha_pipeline import _apply_sector_caps  # noqa: PLC0415
    return _apply_sector_caps


class PortfolioBuilderMixin:
    """Sharpe, drawdown, rebalance, and Stage 2 portfolio constraints."""

    def compute_sharpe_ratio(
        self,
        returns: pd.Series,
        periods_per_year: int = 252,
    ) -> float:
        """Compute annualized Sharpe ratio.

        Parameters
        ----------
        returns : pd.Series
            Period returns
        periods_per_year : int
            Number of periods per year (252 for daily)

        Returns
        -------
        float
            Annualized Sharpe ratio
        """
        if len(returns) < 2:
            return 0.0

        mean_return = returns.mean()
        std_return = returns.std()

        if std_return == 0 or np.isnan(std_return):
            return 0.0

        sharpe = (mean_return / std_return) * np.sqrt(periods_per_year)

        return sharpe if not np.isnan(sharpe) else 0.0

    def compute_max_drawdown(
        self,
        returns: pd.Series,
    ) -> float:
        """Compute maximum drawdown.

        Parameters
        ----------
        returns : pd.Series
            Period returns

        Returns
        -------
        float
            Maximum drawdown (negative value)
        """
        if len(returns) < 2:
            return 0.0

        # Compute cumulative returns
        cum_returns = (1 + returns).cumprod()

        # Compute running maximum
        running_max = cum_returns.expanding().max()

        # Compute drawdown
        drawdown = (cum_returns - running_max) / running_max

        # Return maximum drawdown (most negative)
        max_dd = drawdown.min()

        return max_dd if not np.isnan(max_dd) else 0.0

    def _compute_sequential_dynamic_freq(
        self,
        train_df: pd.DataFrame,
        available_test_df: pd.DataFrame,
        base_freq: int = 7,
    ) -> int:
        """Compute dynamic rebalance frequency for a specific point in time.

        P9 v4 (PIT-safe): Adjust rebalance frequency based on market volatility regime
        using only data available up to the decision point.

        - Compare CURRENT volatility (recent available data) vs HISTORICAL baseline (train period)
        - High volatility (current > 1.5x baseline): rebalance more often (freq=5)
        - Low volatility (current < 0.67x baseline): rebalance less often (freq=10)
        - Medium volatility: use base_freq (7)

        Parameters
        ----------
        train_df : pd.DataFrame
            Training period data with 'close' and 'date' columns (historical baseline)
        available_test_df : pd.DataFrame
            Test period data available up to (but not including) the decision date.
            Must contain only rows with date < decision_date for PIT safety.
        base_freq : int
            Default rebalance frequency

        Returns
        -------
        int
            Adjusted rebalance frequency

        Notes
        -----
        PIT safety: This function only uses train_df and available_test_df (strictly
        prior dates). The caller is responsible for filtering test_df to exclude
        current and future dates relative to the decision point.
        """
        # Guard: if train_df not provided, cannot compute baseline
        if train_df is None or train_df.empty:
            logger.warning("P9: train_df is None/empty, cannot compute baseline vol, using base_freq")
            return base_freq

        # Compute baseline volatility from TRAINING period (historical).
        # Sort first: pct_change is order-sensitive inside each ticker group.
        train_work = train_df.sort_values(['ticker', 'date'])
        train_returns = train_work.groupby('ticker')['close'].pct_change().clip(-0.5, 0.5)
        train_daily_vol = train_returns.groupby(train_work['date']).std()
        train_median_vol = train_daily_vol.median()

        if pd.isna(train_median_vol) or train_median_vol < 1e-9:
            logger.warning("P9: Cannot compute baseline volatility from train_df, using base_freq")
            return base_freq

        # Compute current volatility from AVAILABLE test data (strictly prior dates).
        # If no test data available yet (first OOS date), use train baseline only.
        if available_test_df is None or available_test_df.empty:
            # No OOS data available yet: use train median as current estimate
            current_vol = train_median_vol
            logger.debug("P9: No available test data, using train baseline as current vol")
        else:
            # Sort first: pct_change is order-sensitive inside each ticker group.
            # Clip like forward returns to avoid corporate-action/data jumps dominating regime.
            test_work = available_test_df.sort_values(['ticker', 'date'])
            test_returns = test_work.groupby('ticker')['close'].pct_change().clip(-0.5, 0.5)
            test_daily_vol = test_returns.groupby(test_work['date']).std()

            # Use recent 20-day rolling average for stability
            if len(test_daily_vol) >= 20:
                current_vol = test_daily_vol.rolling(window=20, min_periods=10).mean().iloc[-1]
            else:
                current_vol = test_daily_vol.median()

            if pd.isna(current_vol):
                current_vol = test_daily_vol.median()

            # Fallback to train baseline if still invalid
            if pd.isna(current_vol):
                current_vol = train_median_vol
                logger.debug("P9: Could not compute current vol from available test data, using train baseline")

        # Compare current vs baseline
        vol_ratio = current_vol / train_median_vol

        if vol_ratio > 1.5:
            # High volatility regime: rebalance more often
            adjusted_freq = max(5, base_freq - 2)
            regime = "HIGH"
        elif vol_ratio < 0.67:
            # Low volatility regime: rebalance less often
            adjusted_freq = min(10, base_freq + 3)
            regime = "LOW"
        else:
            # Medium volatility regime: use base frequency
            adjusted_freq = base_freq
            regime = "MEDIUM"

        logger.debug(
            f"P9 Sequential Dynamic: regime={regime}, current_vol={current_vol:.6f}, "
            f"baseline_vol={train_median_vol:.6f}, ratio={vol_ratio:.2f}, freq={base_freq}->{adjusted_freq}"
        )

        return adjusted_freq

    def _apply_stage2_constraints(
        self,
        test_df: pd.DataFrame,
        raw_signal: pd.Series,
        top_alphas: List[str],
        dynamic_rebalance: bool = False,
        train_df: Optional[pd.DataFrame] = None,
    ) -> pd.Series:
        """Apply Stage 2 behavioral constraints to the raw IC-weighted signal.

        Enforces in order:
          1. Top-N stock selection per rebalance date (nlargest on signal)
          2. Rebalance cadence (only recompute weights every rebalance_freq dates)
          3. Sector cap (delegate to alpha_pipeline._apply_sector_caps)

        Parameters
        ----------
        test_df : pd.DataFrame
            Test-set rows with columns 'date', 'ticker', and optionally 'sector'.
            Rows are in the same order as raw_signal.
        raw_signal : pd.Series
            IC-weighted combined signal, indexed identically to test_df.index.
        top_alphas : list of str
            Selected alpha column names (used only for logging context).
        dynamic_rebalance : bool
            If True, adjust rebalance frequency based on market volatility regime.
            P9 v4: Uses sequential PIT-safe frequency computation.
        train_df : pd.DataFrame, optional
            Training data for baseline volatility computation (P9 dynamic rebalance).

        Returns
        -------
        pd.Series
            Per-row portfolio weight Series, same index as raw_signal.
            Sums to ~1.0 across tickers on each date (after sector cap renorm).

        Notes
        -----
        PIT safety: test_df signals are already T-1 lagged by compute_alphas().
        P9 v4: Dynamic rebalance frequency is computed sequentially per rebalance
        checkpoint using only train_df + strictly prior test dates.
        """
        top_n = self.top_n_stocks
        sector_cap = self.sector_cap_pct

        # Attach raw signal to a working frame aligned by position
        work = test_df[['date', 'ticker']].copy().reset_index(drop=True)
        work['_signal'] = raw_signal.values

        # Build sector_map from 'sector' column if present
        if 'sector' in test_df.columns:
            sector_map: Dict[str, str] = (
                test_df[['ticker', 'sector']]
                .drop_duplicates('ticker')
                .set_index('ticker')['sector']
                .to_dict()
            )
        else:
            # No sector metadata: each ticker is its own sector (cap has no effect)
            sector_map = {t: t for t in work['ticker'].unique()}

        all_sectors = set(sector_map.values())
        resolved_caps: Dict[str, float] = {s: sector_cap for s in all_sectors}

        # Sorted unique dates in test fold (chronological)
        sorted_dates = sorted(work['date'].unique())

        # Build wide signal matrix: rows=dates, cols=tickers
        signal_wide = work.pivot_table(
            index='date', columns='ticker', values='_signal', aggfunc='first'
        )

        # Weight matrix (same shape, filled with 0)
        weight_wide = pd.DataFrame(
            0.0, index=signal_wide.index, columns=signal_wide.columns
        )

        last_weights: Optional[pd.Series] = None
        apply_sector_caps = _import_apply_sector_caps()

        # P9 v4 fix: Track current rebalance frequency (updated sequentially at checkpoints)
        # Drive both frequency recompute and rebalance eligibility from elapsed distance
        current_rebal_freq = self.rebalance_freq
        last_rebal_checkpoint_idx = None

        for idx, date in enumerate(sorted_dates):
            if date not in signal_wide.index:
                continue

            # P9 v4 fix: Determine if we should rebalance at this date FIRST
            # Use elapsed distance from last actual checkpoint
            if last_rebal_checkpoint_idx is None:
                # First checkpoint: always rebalance
                should_rebalance = (idx == 0)
            else:
                # Check if enough dates have passed since last checkpoint
                elapsed = idx - last_rebal_checkpoint_idx
                should_rebalance = (elapsed >= current_rebal_freq)

            if should_rebalance:
                # P9 v4 fix: At rebalance dates, recompute frequency using PIT-safe data
                # BEFORE executing rebalance, so new frequency applies to NEXT interval
                if dynamic_rebalance:
                    # Use only data available strictly BEFORE this date (train_df + prior test dates)
                    # This ensures no lookahead: decision at date D uses data < D only
                    available_test = test_df[test_df['date'] < date]
                    current_rebal_freq = self._compute_sequential_dynamic_freq(
                        train_df, available_test, self.rebalance_freq
                    )
                    logger.debug(
                        f"P9 v4: Rebalance at idx={idx}, date={date}, "
                        f"updated freq to {current_rebal_freq} for next interval"
                    )

                # Execute rebalance: select top-N by signal, build equal-weight, apply sector cap
                alpha_row = signal_wide.loc[date].dropna()
                if len(alpha_row) > 0:
                    top_stocks = alpha_row.nlargest(min(top_n, len(alpha_row)))
                    target = pd.Series(0.0, index=signal_wide.columns)
                    target[top_stocks.index] = 1.0 / len(top_stocks)
                    # Apply sector caps (reuse alpha_pipeline logic, no duplication)
                    target = apply_sector_caps(target, sector_map, resolved_caps)
                    last_weights = target

                # Update checkpoint tracker AFTER rebalance
                last_rebal_checkpoint_idx = idx

            if last_weights is not None:
                weight_wide.loc[date] = last_weights

        # Log final applied frequency (may have changed during fold)
        logger.info(
            f"Stage 2 constraints applied: top_n={top_n}, "
            f"final_rebal_freq={current_rebal_freq}, sector_cap={sector_cap:.0%}, "
            f"alphas={top_alphas}, dynamic={'YES' if dynamic_rebalance else 'NO'}"
        )

        # Flatten back to per-row Series aligned with original test_df index
        work_with_weights = work.merge(
            weight_wide.stack().rename('_weight').reset_index().rename(
                columns={'ticker': 'ticker', 'date': 'date'}
            ),
            on=['date', 'ticker'],
            how='left',
        )
        result = work_with_weights['_weight'].fillna(0.0)
        result.index = raw_signal.index
        return result
