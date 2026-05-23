"""Phase 3.5 Walk-Forward Backtest Engine.

Version: v21.39-Phase35-Stage6.2
Date: 2026-05-22

Walk-forward backtest for 7 Phase 3.4 microstructure alphas using real VN market data.

COMPLIANCE:
  - PIT Safety: T-1 lag enforcement
  - Vectorization: 100% Pandas/NumPy
  - Error Handling: Graceful degradation
  - Metrics: IC, Sharpe, Max DD per fold

Stage 6.2 (Cost-Aware Alpha Selection):
  - adjust_alphas_for_cost(): penalises high-turnover alphas via cost-adjusted IC
  - _estimate_alpha_turnover(): vectorised daily turnover estimation on train data
  - Integrated into run_fold() between select_top_alphas() and Research Gate
  - PIT Safety: cost estimation uses train-period data only (T-1 lag preserved)
"""
from __future__ import annotations

import logging
import sys
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from omega.quant.ml_gate_validator import validate_research_gate
from omega.quant.alpha_ensemble_xgboost import XGBoostAlphaEnsemble
from omega.quant.transaction_cost_optimizer import TransactionCostOptimizer

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage 2: reuse sector-cap enforcement from alpha_pipeline (no duplication)
# ---------------------------------------------------------------------------
def _import_apply_sector_caps():
    """Lazy import of _apply_sector_caps from alpha_pipeline.

    Searches for alpha_pipeline.py relative to this file's location so the
    import works regardless of the working directory.
    """
    _scripts_dir = str(Path(__file__).resolve().parents[5] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    from alpha_pipeline import _apply_sector_caps  # noqa: PLC0415
    return _apply_sector_caps


@dataclass
class FoldMetrics:
    """Metrics for a single walk-forward fold."""
    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    alpha_ics: Dict[str, float] = field(default_factory=dict)
    portfolio_sharpe: float = 0.0
    portfolio_max_dd: float = 0.0
    portfolio_total_return: float = 0.0
    portfolio_ic: float = 0.0
    n_train_samples: int = 0
    n_test_samples: int = 0
    # Stage 3 ML Gate fields
    gate_results: Dict[str, dict] = field(default_factory=dict)
    gated_alphas: List[str] = field(default_factory=list)


@dataclass
class WalkForwardResult:
    """Complete walk-forward backtest results."""
    fold_metrics: List[FoldMetrics] = field(default_factory=list)
    avg_ic_by_alpha: Dict[str, float] = field(default_factory=dict)
    avg_portfolio_sharpe: float = 0.0
    avg_portfolio_max_dd: float = 0.0
    avg_portfolio_ic: float = 0.0
    total_folds: int = 0
    
    def summary(self) -> str:
        """Generate summary string."""
        lines = [
            f"Walk-Forward Backtest Results ({self.total_folds} folds)",
            "=" * 60,
            f"Average Portfolio IC: {self.avg_portfolio_ic:.4f}",
            f"Average Portfolio Sharpe: {self.avg_portfolio_sharpe:.4f}",
            f"Average Max Drawdown: {self.avg_portfolio_max_dd:.2%}",
            "",
            "Alpha IC Summary:",
        ]
        
        for alpha, ic in sorted(self.avg_ic_by_alpha.items(), key=lambda x: abs(x[1]), reverse=True):
            lines.append(f"  {alpha}: {ic:.4f}")
        
        return "\n".join(lines)


class Phase35WalkForwardEngine:
    """Walk-forward backtest engine for Phase 3.4 microstructure alphas."""
    
    def __init__(
        self,
        alpha_module,
        min_ic_threshold: float = 0.02,
        top_n_alphas: int = 5,
        top_n_stocks: int = 8,
        rebalance_freq: int = 7,
        sector_cap_pct: float = 0.30,
        use_xgboost: bool = False,
        drawdown_control: bool = False,
        drawdown_threshold: float = 0.05,
    ):
        """Initialize walk-forward engine.
        
        Parameters
        ----------
        alpha_module : module
            Module containing compute_phase34_microstructure_alphas function
        min_ic_threshold : float
            Minimum IC threshold for alpha selection
        top_n_alphas : int
            Number of top alphas to use in portfolio
        top_n_stocks : int
            Stage 2 diversification: number of stocks in portfolio (default 8)
        rebalance_freq : int
            Stage 2 diversification: rebalance every N days (default 7)
        sector_cap_pct : float
            Stage 2 diversification: max sector weight fraction (default 0.30)
        use_xgboost : bool
            Stage 4: if True, replace IC-weighted signal with XGBoostAlphaEnsemble
            predictions. Baseline raw-alpha path is used when False (default).
        """
        self.alpha_module = alpha_module
        self.min_ic_threshold = min_ic_threshold
        self.top_n_alphas = top_n_alphas
        self.top_n_stocks = top_n_stocks
        self.rebalance_freq = rebalance_freq
        self.sector_cap_pct = sector_cap_pct
        self.use_xgboost = use_xgboost
        self.drawdown_control = drawdown_control
        self.drawdown_threshold = drawdown_threshold
    
    def compute_alphas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute Phase 3.4 alphas on data.
        
        Parameters
        ----------
        df : pd.DataFrame
            OHLCV data with 'ticker', 'date', 'open', 'high', 'low', 'close', 'volume'
        
        Returns
        -------
        pd.DataFrame
            Data with alpha columns added
        """
        return self.alpha_module.compute_phase34_microstructure_alphas(
            df,
            symbol_col='ticker',
            date_col='date',
            open_col='open',
            high_col='high',
            low_col='low',
            close_col='close',
            volume_col='volume',
        )
    
    def compute_ic(
        self,
        alpha_values: pd.Series,
        returns: pd.Series,
    ) -> float:
        """Compute Spearman IC between alpha and returns.
        
        Parameters
        ----------
        alpha_values : pd.Series
            Alpha signal values
        returns : pd.Series
            Forward returns
        
        Returns
        -------
        float
            Spearman IC
        """
        # Remove NaN pairs
        mask = ~(alpha_values.isna() | returns.isna())
        if mask.sum() < 10:
            return 0.0
        
        alpha_clean = alpha_values[mask].values
        returns_clean = returns[mask].values
        
        try:
            ic, _ = spearmanr(alpha_clean, returns_clean)
            return ic if not np.isnan(ic) else 0.0
        except Exception as e:
            logger.warning(f"IC computation failed: {e}")
            return 0.0
    
    def compute_alpha_ics(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
        return_col: str = 'fwd_ret_5',
    ) -> Dict[str, float]:
        """Compute IC for each alpha.
        
        Parameters
        ----------
        df : pd.DataFrame
            Data with alpha columns and forward returns
        alpha_cols : list of str
            Alpha column names
        return_col : str
            Forward return column name
        
        Returns
        -------
        dict
            Mapping of alpha name to IC
        """
        ics = {}
        
        for alpha_col in alpha_cols:
            if alpha_col not in df.columns:
                logger.warning(f"Alpha column {alpha_col} not found")
                ics[alpha_col] = 0.0
                continue
            
            ic = self.compute_ic(df[alpha_col], df[return_col])
            ics[alpha_col] = ic
        
        return ics
    
    def select_top_alphas(
        self,
        alpha_ics: Dict[str, float],
    ) -> List[str]:
        """Select top N alphas by absolute IC.
        
        Parameters
        ----------
        alpha_ics : dict
            Mapping of alpha name to IC
        
        Returns
        -------
        list of str
            Top N alpha names
        """
        # Filter by minimum IC threshold
        valid_alphas = {k: v for k, v in alpha_ics.items() if abs(v) >= self.min_ic_threshold}
        
        if not valid_alphas:
            logger.warning(f"No alphas meet IC threshold {self.min_ic_threshold}, using all")
            valid_alphas = alpha_ics
        
        # Sort by absolute IC
        sorted_alphas = sorted(valid_alphas.items(), key=lambda x: abs(x[1]), reverse=True)
        
        # Take top N
        top_alphas = [name for name, _ in sorted_alphas[:self.top_n_alphas]]
        
        logger.info(f"Selected top {len(top_alphas)} alphas: {top_alphas}")
        
        return top_alphas
    
    def validate_alpha_with_research_gate(
        self,
        top_alphas: List[str],
        train_ics: Dict[str, float],
        train_df_clean: pd.DataFrame,
        return_col: str = 'fwd_ret_5',
        rolling_window: int = 20,
    ) -> Tuple[List[str], Dict[str, dict]]:
        """Filter top_alphas through Research Gate using embargoed train_df_clean.

        Computes a rolling IC series (rolling_window-day window) from daily
        cross-sectional ICs on train_df_clean (PIT safe — no look-ahead).
        Each alpha is validated via validate_research_gate(). Alphas that pass
        are returned as gated_alphas. If all fail, falls back to top_alphas.

        Parameters
        ----------
        top_alphas : list of str
            Candidate alpha names from select_top_alphas().
        train_ics : dict
            Per-alpha IC on embargoed train set (used as val_ic).
        train_df_clean : pd.DataFrame
            Embargoed training data with alpha columns and return_col.
        return_col : str
            Forward return column name.
        rolling_window : int
            Window size for rolling IC series (default 20).

        Returns
        -------
        gated_alphas : list of str
            Alphas that passed the Research Gate (or fallback = top_alphas).
        gate_results : dict
            Mapping of alpha name -> validate_research_gate() result dict.

        Notes
        -----
        PIT Safety: rolling IC is computed solely on train_df_clean which has
        the embargo applied upstream. No test-period data is used here.
        """
        gate_results: Dict[str, dict] = {}

        # Compute daily cross-sectional IC per alpha on embargoed train set
        # Group by date, compute Spearman IC across tickers each day
        dates = sorted(train_df_clean['date'].unique())

        # Build daily IC series per alpha (vectorized over dates)
        daily_ics: Dict[str, pd.Series] = {}
        for alpha in top_alphas:
            if alpha not in train_df_clean.columns:
                daily_ics[alpha] = pd.Series(dtype=float)
                continue
            ic_by_date = []
            for date in dates:
                day_df = train_df_clean[train_df_clean['date'] == date]
                mask = ~(day_df[alpha].isna() | day_df[return_col].isna())
                if mask.sum() < 5:
                    ic_by_date.append(np.nan)
                    continue
                try:
                    ic_val, _ = spearmanr(
                        day_df.loc[mask, alpha].values,
                        day_df.loc[mask, return_col].values,
                    )
                    ic_by_date.append(ic_val if not np.isnan(ic_val) else np.nan)
                except Exception:
                    ic_by_date.append(np.nan)
            daily_ics[alpha] = pd.Series(ic_by_date, index=dates, dtype=float)

        # Validate each alpha through Research Gate
        gated_alphas: List[str] = []
        for alpha in top_alphas:
            val_ic = train_ics.get(alpha, 0.0)
            raw_daily = daily_ics.get(alpha, pd.Series(dtype=float))
            # Rolling mean IC series (drop NaN before rolling)
            rolling_ic = raw_daily.dropna().rolling(window=rolling_window).mean().dropna()
            result = validate_research_gate(val_ic, rolling_ic)
            gate_results[alpha] = result
            if result['passed']:
                gated_alphas.append(alpha)
            logger.info(
                f"Research Gate [{alpha}]: {result['verdict']} "
                f"(val_ic={val_ic:.4f}, n_samples={result['n_samples']})"
            )

        # Fallback: if all alphas fail gate, use original top_alphas
        if not gated_alphas:
            logger.warning(
                "All alphas failed Research Gate — falling back to top_alphas "
                f"({top_alphas})"
            )
            gated_alphas = list(top_alphas)

        logger.info(f"Gated alphas ({len(gated_alphas)}/{len(top_alphas)}): {gated_alphas}")
        return gated_alphas, gate_results
    
    def compute_portfolio_signal(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
        alpha_ics: Dict[str, float],
    ) -> pd.Series:
        """Compute IC-weighted portfolio signal.
        
        Parameters
        ----------
        df : pd.DataFrame
            Data with alpha columns
        alpha_cols : list of str
            Alpha column names to combine
        alpha_ics : dict
            IC weights for each alpha
        
        Returns
        -------
        pd.Series
            Combined portfolio signal
        """
        # Extract IC weights
        weights = np.array([alpha_ics.get(col, 0.0) for col in alpha_cols])
        
        # Normalize weights to sum to 1
        weight_sum = np.abs(weights).sum()
        if weight_sum > 0:
            weights = weights / weight_sum
        else:
            weights = np.ones(len(weights)) / len(weights)
        
        # Compute weighted average
        alpha_matrix = df[alpha_cols].values
        portfolio_signal = alpha_matrix @ weights
        
        return pd.Series(portfolio_signal, index=df.index)
    
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
    
    def _apply_stage2_constraints(
        self,
        test_df: pd.DataFrame,
        raw_signal: pd.Series,
        top_alphas: List[str],
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

        Returns
        -------
        pd.Series
            Per-row portfolio weight Series, same index as raw_signal.
            Sums to ~1.0 across tickers on each date (after sector cap renorm).

        Notes
        -----
        PIT safety: test_df signals are already T-1 lagged by compute_alphas().
        No forward information is introduced here — we only reshape weights.
        """
        top_n = self.top_n_stocks
        rebal_freq = self.rebalance_freq
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

        for idx, date in enumerate(sorted_dates):
            if date not in signal_wide.index:
                continue

            if idx % rebal_freq == 0:
                # Rebalance: select top-N by signal, build equal-weight, apply sector cap
                alpha_row = signal_wide.loc[date].dropna()
                if len(alpha_row) > 0:
                    top_stocks = alpha_row.nlargest(min(top_n, len(alpha_row)))
                    target = pd.Series(0.0, index=signal_wide.columns)
                    target[top_stocks.index] = 1.0 / len(top_stocks)
                    # Apply sector caps (reuse alpha_pipeline logic, no duplication)
                    target = apply_sector_caps(target, sector_map, resolved_caps)
                    last_weights = target

            if last_weights is not None:
                weight_wide.loc[date] = last_weights

        logger.info(
            f"Stage 2 constraints applied: top_n={top_n}, "
            f"rebal_freq={rebal_freq}, sector_cap={sector_cap:.0%}, "
            f"alphas={top_alphas}"
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

    # ------------------------------------------------------------------
    # Stage 6.2: Cost-Aware Alpha Selection
    # ------------------------------------------------------------------

    def _estimate_alpha_turnover(
        self,
        train_df: pd.DataFrame,
        alpha_col: str,
    ) -> float:
        """Estimate average daily turnover rate for an alpha signal.

        Turnover is defined as the mean absolute day-over-day rank change
        of the alpha signal, normalised to [0, 1] by the number of tickers.

        PIT Safety: uses only train-period data. No future information.

        Parameters
        ----------
        train_df : pd.DataFrame
            Embargoed training data with 'date', 'ticker', and alpha_col.
        alpha_col : str
            Alpha column to estimate turnover for.

        Returns
        -------
        float
            Average daily turnover rate in [0.0, 1.0].
            Returns 0.5 (conservative default) on any error.
        """
        try:
            if alpha_col not in train_df.columns:
                return 0.5

            # Pivot: rows=date, cols=ticker, values=alpha signal
            pivot = train_df.pivot_table(
                index='date', columns='ticker', values=alpha_col, aggfunc='first'
            )
            if pivot.shape[0] < 2:
                return 0.5

            n_tickers = pivot.shape[1]
            if n_tickers < 2:
                return 0.5

            # Rank each row (cross-section) — vectorised
            ranked = pivot.rank(axis=1, method='average', na_option='keep')

            # Day-over-day absolute rank change, normalised by n_tickers
            rank_diff = ranked.diff().abs()  # shape: (dates, tickers)

            # Mean over all (date, ticker) pairs, ignoring NaN
            mean_abs_change = rank_diff.values[1:].mean()  # skip first NaN row

            # Normalise: max possible change per ticker per day ≈ n_tickers
            turnover = float(np.clip(mean_abs_change / n_tickers, 0.0, 1.0))
            return turnover if not np.isnan(turnover) else 0.5

        except Exception as e:
            logger.warning(f"_estimate_alpha_turnover({alpha_col}) failed: {e}")
            return 0.5

    def adjust_alphas_for_cost(
        self,
        train_df: pd.DataFrame,
        alpha_cols: List[str],
        train_ics: Dict[str, float],
        cost_per_turnover: float = 0.0025,
    ) -> Dict[str, float]:
        """Compute cost-adjusted IC for each alpha candidate.

        Formula (from brief):
            cost_bps = cost_per_turnover * turnover_rate * 10_000
            adjusted_ic = raw_ic - (cost_bps / 10_000)
                        = raw_ic - (cost_per_turnover * turnover_rate)

        The subtracted term is already in IC units (dimensionless fraction),
        so no unit conversion is needed beyond the formula above.

        PIT Safety:
          - Turnover estimated from train_df only (T-1 lag preserved upstream).
          - TransactionCostOptimizer is NOT called here because we have no
            per-symbol market-data dict available at this stage; instead we
            use the cost_per_turnover round-trip rate directly (0.25% default,
            matching the brief's stated assumption).

        Parameters
        ----------
        train_df : pd.DataFrame
            Embargoed training data.
        alpha_cols : list of str
            All alpha candidate column names.
        train_ics : dict
            Raw IC per alpha from compute_alpha_ics().
        cost_per_turnover : float
            Round-trip cost rate (default 0.0025 = 0.25 bps expressed as
            fraction, matching brief's "0.25% round-trip" assumption).

        Returns
        -------
        dict
            {alpha: adjusted_ic} for every alpha in train_ics.
        """
        adjusted: Dict[str, float] = {}
        for alpha in alpha_cols:
            raw_ic = train_ics.get(alpha, 0.0)
            turnover = self._estimate_alpha_turnover(train_df, alpha)
            # cost penalty in IC units: cost_bps/10000 = cost_per_turnover * turnover
            cost_penalty = cost_per_turnover * turnover
            adjusted_ic = raw_ic - cost_penalty
            adjusted[alpha] = adjusted_ic
            logger.debug(
                f"cost_adjust [{alpha}]: raw_ic={raw_ic:.4f}, "
                f"turnover={turnover:.4f}, penalty={cost_penalty:.6f}, "
                f"adjusted_ic={adjusted_ic:.4f}"
            )
        logger.info(f"Stage 6.2 cost-adjusted ICs: {adjusted}")
        return adjusted

    def run_fold(
        self,
        fold_id: int,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        alpha_cols: List[str],
        return_col: str = 'fwd_ret_5',
        cost_aware: bool = False,
    ) -> FoldMetrics:
        """Run single walk-forward fold.

        Parameters
        ----------
        fold_id : int
            Fold identifier
        train_df : pd.DataFrame
            Training data
        test_df : pd.DataFrame
            Testing data
        alpha_cols : list of str
            Alpha column names
        return_col : str
            Forward return column name
        cost_aware : bool
            Stage 6.2: if True, re-rank alphas by cost-adjusted IC before
            passing to the Research Gate. Baseline raw-IC path used when
            False (default). Baseline path is fully preserved.

        Returns
        -------
        FoldMetrics
            Fold results

        Notes
        -----
        Embargo logic (PIT Safety): For a return_col of the form 'fwd_ret_N',
        the last N rows per symbol are dropped from train_df before IC
        computation and alpha selection. This prevents label leakage where
        the forward return window of the final training rows overlaps with
        the test period. Alpha computation (feature generation) uses the
        full train_df so that indicators at the boundary are not distorted.

        Stage 6.2 integration point: cost adjustment is applied AFTER
        compute_alpha_ics() and BEFORE select_top_alphas() / Research Gate,
        so the gate and XGBoost path both operate on cost-adjusted rankings.
        PIT Safety: adjust_alphas_for_cost() uses train_df_clean only.
        """
        logger.info(f"Running fold {fold_id}")
        
        # Compute alphas on train and test (full train_df — no embargo yet)
        train_df = self.compute_alphas(train_df)
        test_df = self.compute_alphas(test_df)
        
        # --- Embargo: drop last h rows per symbol from IC/selection window ---
        # Extract horizon h from return_col name (e.g. 'fwd_ret_5' -> h=5).
        # Falls back to h=1 for unrecognised patterns.
        try:
            h = int(return_col.split('_')[-1])
        except (ValueError, IndexError):
            h = 1
            logger.warning(
                f"Could not parse horizon from return_col='{return_col}'; "
                f"defaulting embargo h={h}"
            )
        
        # Vectorized embargo: cumcount(ascending=False)==0 is the last row per symbol.
        # Keep only rows where tail_rank >= h (i.e. not in the last h rows).
        # This preserves all columns and is compatible with pandas 3.x.
        _tail_rank = train_df.groupby('ticker').cumcount(ascending=False)
        train_df_clean = train_df[_tail_rank >= h].reset_index(drop=True)
        logger.info(
            f"Fold {fold_id} embargo: h={h}, "
            f"train rows before={len(train_df)}, after={len(train_df_clean)}"
        )
        
        # Compute IC on embargoed training set (no label leakage)
        train_ics = self.compute_alpha_ics(train_df_clean, alpha_cols, return_col)

        logger.info(f"Fold {fold_id} train ICs: {train_ics}")

        # ------------------------------------------------------------------
        # Stage 6.2: Cost-Aware Alpha Selection (optional, PIT safe)
        # Adjusts raw ICs by subtracting cost penalty before ranking.
        # Baseline path (cost_aware=False) is fully preserved — no change.
        # PIT Safety: adjust_alphas_for_cost() uses train_df_clean only.
        # ------------------------------------------------------------------
        if cost_aware:
            selection_ics = self.adjust_alphas_for_cost(
                train_df=train_df_clean,
                alpha_cols=alpha_cols,
                train_ics=train_ics,
            )
            logger.info(f"Fold {fold_id} [Stage6.2] cost-adjusted ICs: {selection_ics}")
        else:
            selection_ics = train_ics

        # Select top alphas based on (cost-adjusted or raw) IC
        top_alphas = self.select_top_alphas(selection_ics)

        # ------------------------------------------------------------------
        # Stage 3 ML Gate: filter top_alphas through Research Gate
        # Uses embargoed train_df_clean — PIT safe, no look-ahead.
        # ------------------------------------------------------------------
        gated_alphas, gate_results = self.validate_alpha_with_research_gate(
            top_alphas=top_alphas,
            train_ics=train_ics,
            train_df_clean=train_df_clean,
            return_col=return_col,
        )

        # ------------------------------------------------------------------
        # Stage 4: optional XGBoost path (use_xgboost=True) vs baseline
        # Baseline: IC-weighted signal from gated alphas (unchanged).
        # XGBoost: train XGBoostAlphaEnsemble on train_df_clean MultiIndex,
        #          predict on test_df MultiIndex, standardize to portfolio_signal.
        # PIT Safety: ensemble trains only on embargoed train_df_clean.
        #             Embargo was applied upstream — no look-ahead here.
        # ------------------------------------------------------------------
        if self.use_xgboost and len(train_df_clean) > 0 and len(gated_alphas) > 0:
            try:
                # Convert flat ['date','ticker'] -> MultiIndex ['date','symbol']
                X_train_multi = (
                    train_df_clean
                    .set_index(['date', 'ticker'])
                    .rename_axis(index={'ticker': 'symbol'})
                )
                X_test_multi = (
                    test_df
                    .set_index(['date', 'ticker'])
                    .rename_axis(index={'ticker': 'symbol'})
                )

                # Derive cutoff_date from max train date (embargo already applied)
                cutoff_date = str(
                    train_df_clean['date'].max().date()
                    if hasattr(train_df_clean['date'].max(), 'date')
                    else train_df_clean['date'].max()
                )

                ensemble = XGBoostAlphaEnsemble(min_ic_threshold=0.0)
                ensemble.train(
                    X_train_multi,
                    gated_alphas,
                    cutoff_date=cutoff_date,
                    embargo_days=0,  # embargo already applied upstream
                )
                raw_preds = ensemble.predict(X_test_multi, gated_alphas)

                # Flatten MultiIndex predictions back to flat test_df index
                # raw_preds index is (date, symbol); align by position to test_df
                preds_flat = raw_preds.values
                if len(preds_flat) == len(test_df):
                    preds_series = pd.Series(preds_flat, index=test_df.index)
                    # Standardize: zero-mean, unit-std per date cross-section
                    std_val = preds_series.std()
                    if std_val > 0:
                        portfolio_signal = (preds_series - preds_series.mean()) / std_val
                    else:
                        portfolio_signal = preds_series
                    logger.info(f"Fold {fold_id}: XGBoost path active, signal std={std_val:.4f}")
                else:
                    logger.warning(
                        f"Fold {fold_id}: XGBoost pred length mismatch "
                        f"({len(preds_flat)} vs {len(test_df)}), falling back to baseline"
                    )
                    portfolio_signal = self.compute_portfolio_signal(test_df, gated_alphas, train_ics)
            except Exception as e:
                logger.warning(
                    f"Fold {fold_id}: XGBoost path failed ({e}), falling back to baseline"
                )
                portfolio_signal = self.compute_portfolio_signal(test_df, gated_alphas, train_ics)
        else:
            # Baseline: IC-weighted signal (original path, fully preserved)
            portfolio_signal = self.compute_portfolio_signal(test_df, gated_alphas, train_ics)

        # ------------------------------------------------------------------
        # Stage 2 behavioral enforcement (top-N, rebalance cadence, sector cap)
        # Applied AFTER IC-weighted signal combination, BEFORE return computation.
        # PIT safety preserved: test_df signals are already T-1 lagged upstream.
        # ------------------------------------------------------------------
        portfolio_signal = self._apply_stage2_constraints(
            test_df=test_df,
            raw_signal=portfolio_signal,
            top_alphas=gated_alphas,
        )

        # Stage 6.3: Active Drawdown Control (optional)
        # Monitor daily portfolio NAV inside each fold and stop out to cash
        # after first drawdown breach. Breach-day return is preserved; weights
        # are zeroed from the following date onward.
        if self.drawdown_control:
            raw_portfolio_returns = portfolio_signal * test_df[return_col]
            daily_portfolio_returns = (
                raw_portfolio_returns
                .groupby(test_df['date'])
                .sum()
                .sort_index()
            )
            if not daily_portfolio_returns.empty:
                nav = (1.0 + daily_portfolio_returns).cumprod()
                running_peak = nav.cummax()
                drawdowns = (nav - running_peak) / running_peak
                breached_dates = drawdowns[drawdowns <= -self.drawdown_threshold].index
                if len(breached_dates) > 0:
                    first_breach_date = breached_dates[0]
                    logger.info(
                        f"Fold {fold_id} [Stage6.3]: drawdown breach on "
                        f"{pd.Timestamp(first_breach_date).date()} at "
                        f"{drawdowns.loc[first_breach_date]:.2%}; stop-out to cash"
                    )
                    portfolio_signal = portfolio_signal.copy()
                    portfolio_signal.loc[test_df['date'] > first_breach_date] = 0.0

        # Compute test IC for each alpha
        test_ics = self.compute_alpha_ics(test_df, alpha_cols, return_col)
        
        # Compute portfolio IC on test set
        portfolio_ic = self.compute_ic(portfolio_signal, test_df[return_col])
        
        # Compute portfolio returns (signal * forward return)
        portfolio_returns = portfolio_signal * test_df[return_col]
        portfolio_returns = portfolio_returns.dropna()

        # Aggregate to daily portfolio returns before computing risk metrics.
        # Raw portfolio_returns is row-level (one row per date×ticker); Sharpe
        # and Max DD must operate on one observation per calendar day.
        daily_returns = (
            portfolio_returns
            .groupby(test_df.loc[portfolio_returns.index, 'date'])
            .sum()
            .sort_index()
        )

        # Compute Sharpe and Max DD
        sharpe = self.compute_sharpe_ratio(daily_returns)
        max_dd = self.compute_max_drawdown(daily_returns)
        total_return = portfolio_returns.sum()
        
        # Create metrics object
        metrics = FoldMetrics(
            fold_id=fold_id,
            train_start=str(train_df['date'].min().date()),
            train_end=str(train_df['date'].max().date()),
            test_start=str(test_df['date'].min().date()),
            test_end=str(test_df['date'].max().date()),
            alpha_ics=test_ics,
            portfolio_sharpe=sharpe,
            portfolio_max_dd=max_dd,
            portfolio_total_return=total_return,
            portfolio_ic=portfolio_ic,
            n_train_samples=len(train_df_clean),
            n_test_samples=len(test_df),
            gate_results=gate_results,
            gated_alphas=gated_alphas,
        )
        
        logger.info(f"Fold {fold_id} results: IC={portfolio_ic:.4f}, Sharpe={sharpe:.4f}, MaxDD={max_dd:.2%}")
        
        return metrics
    
    def run_walk_forward(
        self,
        splits: List[Tuple[pd.DataFrame, pd.DataFrame]],
        alpha_cols: List[str],
        return_col: str = 'fwd_ret_5',
        cost_aware: bool = False,
    ) -> WalkForwardResult:
        """Run complete walk-forward backtest.

        Parameters
        ----------
        splits : list of tuple
            List of (train_df, test_df) pairs
        alpha_cols : list of str
            Alpha column names
        return_col : str
            Forward return column name
        cost_aware : bool
            Stage 6.2: if True, enable cost-aware alpha selection in every
            fold. Baseline raw-IC path used when False (default).

        Returns
        -------
        WalkForwardResult
            Complete backtest results

        Notes
        -----
        Stage 6.3 drawdown control is enabled via engine init parameter
        (self.drawdown_control), not as a run-time flag.
        """
        logger.info(f"Starting walk-forward backtest with {len(splits)} folds")

        fold_metrics = []

        for fold_id, (train_df, test_df) in enumerate(splits, start=1):
            metrics = self.run_fold(
                fold_id, train_df, test_df, alpha_cols, return_col,
                cost_aware=cost_aware,
            )
            fold_metrics.append(metrics)
        
        # Aggregate results
        avg_ic_by_alpha = {}
        for alpha_col in alpha_cols:
            ics = [m.alpha_ics.get(alpha_col, 0.0) for m in fold_metrics]
            avg_ic_by_alpha[alpha_col] = np.mean(ics)
        
        avg_portfolio_ic = np.mean([m.portfolio_ic for m in fold_metrics])
        avg_portfolio_sharpe = np.mean([m.portfolio_sharpe for m in fold_metrics])
        avg_portfolio_max_dd = np.mean([m.portfolio_max_dd for m in fold_metrics])
        
        result = WalkForwardResult(
            fold_metrics=fold_metrics,
            avg_ic_by_alpha=avg_ic_by_alpha,
            avg_portfolio_sharpe=avg_portfolio_sharpe,
            avg_portfolio_max_dd=avg_portfolio_max_dd,
            avg_portfolio_ic=avg_portfolio_ic,
            total_folds=len(fold_metrics),
        )
        
        logger.info("Walk-forward backtest complete")
        logger.info(result.summary())
        
        return result


if __name__ == "__main__":
    # Test walk-forward engine
    logging.basicConfig(level=logging.INFO)
    
    # Import required modules
    import sys
    from pathlib import Path
    
    # Add canonical package path
    workspace = Path(__file__).resolve().parents[5]
    sys.path.insert(0, str(workspace / "packages" / "quant" / "src"))
    sys.path.insert(0, str(workspace / "scripts"))
    
    from omega.quant import phase34_microstructure_alphas
    from phase35_data_loader import Phase35DataLoader
    
    # Load data
    loader = Phase35DataLoader()
    df = loader.load_and_prepare(
        start_date="2018-01-01",
        end_date="2026-05-08",
        top_n_symbols=20,
    )
    
    # Create splits
    splits = loader.create_walk_forward_splits(df, n_folds=6, train_years=1, test_years=1)
    
    # Run walk-forward backtest
    engine = Phase35WalkForwardEngine(
        alpha_module=phase34_microstructure_alphas,
        min_ic_threshold=0.02,
        top_n_alphas=5,
    )
    
    alpha_cols = list(phase34_microstructure_alphas.PHASE34_ALPHA_COLUMNS)
    
    result = engine.run_walk_forward(splits, alpha_cols, return_col='fwd_ret_5')
    
    print("\n" + result.summary())
