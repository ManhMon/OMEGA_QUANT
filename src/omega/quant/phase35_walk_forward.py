"""Phase 3.5 Walk-Forward Backtest Engine.

Version: v21.38-Phase35-Stage3
Date: 2026-05-22

Walk-forward backtest for 7 Phase 3.4 microstructure alphas using real VN market data.

COMPLIANCE:
  - PIT Safety: T-1 lag enforcement
  - Vectorization: 100% Pandas/NumPy
  - Error Handling: Graceful degradation
  - Metrics: IC, Sharpe, Max DD per fold
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
    _scripts_dir = str(Path(__file__).resolve().parents[3] / "scripts")
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
    portfolio_pnl_vnd: float = 0.0
    portfolio_ic: float = 0.0
    raw_signal_ic: float = 0.0
    raw_signal_daily_cs_ic: float = 0.0
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
    avg_raw_signal_ic: float = 0.0
    avg_raw_signal_daily_cs_ic: float = 0.0
    avg_portfolio_pnl_vnd: float = 0.0
    total_folds: int = 0
    
    def summary(self) -> str:
        """Generate summary string."""
        lines = [
            f"Walk-Forward Backtest Results ({self.total_folds} folds)",
            "=" * 60,
            f"Average Portfolio IC (post Stage 2): {self.avg_portfolio_ic:.4f}",
            f"Average Raw Signal IC (pre Stage 2):  {self.avg_raw_signal_ic:.4f}",
            f"Average Raw Signal Daily CS IC:       {self.avg_raw_signal_daily_cs_ic:.4f}",
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
        top_n_stocks: int = 15,
        rebalance_freq: int = 7,
        sector_cap_pct: float = 0.40,
        use_xgboost: bool = False,
        cost_aware: bool = False,
        cost_per_turnover: float = 0.0025,
        drawdown_control: bool = False,
        drawdown_threshold: float = 0.05,
        strategy: str = "multi_factor",
        initial_capital: float = 1_000_000_000.0,
        enable_evolved: bool = False,
        evolved_blend_weight: float = 0.5,
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
            Stage 2 diversification: number of stocks in portfolio (default 15, relaxed from 8)
        rebalance_freq : int
            Stage 2 diversification: rebalance every N days (default 7)
        sector_cap_pct : float
            Stage 2 diversification: max sector weight fraction (default 0.40, relaxed from 0.30)
        use_xgboost : bool
            Stage 4: if True, replace IC-weighted signal with XGBoostAlphaEnsemble
            predictions. Baseline raw-alpha path is used when False (default).
        cost_aware : bool
            Stage 6.2: if True, penalise high-turnover alphas in selection
        cost_per_turnover : float
            Stage 6.2: cost penalty multiplier per unit of turnover (default 0.0025)
        drawdown_control : bool
            Stage 6.3: if True, stop out to cash if max drawdown threshold is breached
        drawdown_threshold : float
            Stage 6.3: drawdown threshold to trigger stop-out (default 0.05)
        strategy : str
            Trading strategy (multi_factor, momentum, mean_reversion)
        initial_capital : float
            Initial capital in VND
        enable_evolved : bool
            If True, run inline GP evolution per fold and blend evolved signal
        evolved_blend_weight : float
            Weight of evolved signal in blend (0-1), remainder is hand-crafted
        """
        self.alpha_module = alpha_module
        self.min_ic_threshold = min_ic_threshold
        self.top_n_alphas = top_n_alphas
        self.top_n_stocks = top_n_stocks
        self.rebalance_freq = rebalance_freq
        self.sector_cap_pct = sector_cap_pct
        self.use_xgboost = use_xgboost
        self.cost_aware = cost_aware
        self.cost_per_turnover = cost_per_turnover
        self.drawdown_control = drawdown_control
        self.drawdown_threshold = drawdown_threshold
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.enable_evolved = enable_evolved
        # Validate and clamp blend weight to [0, 1]
        if not 0 <= evolved_blend_weight <= 1:
            raise ValueError(f"evolved_blend_weight must be in [0, 1], got {evolved_blend_weight}")
        self.evolved_blend_weight = evolved_blend_weight
        
        # Store reference alpha columns for feature whitelist
        self.alpha_cols_ref = getattr(alpha_module, 'PHASE34_ALPHA_COLUMNS', [])
    
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

    def compute_daily_cs_ic(
        self,
        df: pd.DataFrame,
        signal_col: str,
        return_col: str,
        min_cross_section: int = 5,
    ) -> float:
        """Compute daily cross-sectional Spearman IC, then average across dates.

        For each unique date in df, computes Spearman IC between signal_col and
        return_col across tickers. Returns the mean of per-date ICs.

        Parameters
        ----------
        df : pd.DataFrame
            Must have 'date', signal_col, return_col columns.
        signal_col : str
            Column name for the signal (alpha or portfolio weight).
        return_col : str
            Column name for forward returns.
        min_cross_section : int
            Minimum number of non-NaN pairs per date to compute IC (default 5).

        Returns
        -------
        float
            Mean daily cross-sectional Spearman IC.
        """
        if signal_col not in df.columns or return_col not in df.columns:
            return 0.0

        def _cs_ic(group: pd.DataFrame) -> float:
            mask = ~(group[signal_col].isna() | group[return_col].isna())
            if mask.sum() < min_cross_section:
                return np.nan
            try:
                ic, _ = spearmanr(
                    group.loc[mask, signal_col].values,
                    group.loc[mask, return_col].values,
                )
                return ic if not np.isnan(ic) else np.nan
            except Exception:
                return np.nan

        daily_ics = df.groupby('date').apply(_cs_ic, include_groups=False)
        valid = daily_ics.dropna()
        if valid.empty:
            return 0.0
        return float(valid.mean())

    def _evolve_inline_signal(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        return_col: str,
    ) -> Tuple[Optional[np.ndarray], float]:
        """Run inline GP evolution on train_df, execute best on test_df.

        PIT-safe: evolves only on train_actual, executes on test_df.
        Returns (evolved_signal_array, train_ic) or (None, 0.0) on failure.
        train_ic is used by caller for adaptive blend weighting.
        """
        try:
            from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig
        except ImportError:
            logger.warning("Cannot import GeneticEngine, skipping evolved signal")
            return None, 0.0

        # Extract features from train_df (OHLCV + any alpha/feature columns)
        base_cols = ['open', 'high', 'low', 'close', 'volume']
        # Add any additional numeric columns available (alphas, fwd returns, etc.)
        alpha_cols = [c for c in self.alpha_cols_ref if c in train_df.columns]
        
        # Explicitly exclude return_col and any fwd_ret_* columns (prevent look-ahead leak)
        exclude_patterns = [return_col] + [c for c in train_df.columns if c.startswith('fwd_ret_')]
        available_cols = [c for c in base_cols + alpha_cols 
                         if c in train_df.columns and c not in exclude_patterns]
        
        if len(available_cols) < 5:
            logger.warning(f"Insufficient features ({len(available_cols)}), skipping evolution")
            return None, 0.0

        # PIT Safety: T-1 lag raw OHLCV per ticker before GP sees them
        # Alpha columns are already T-1 lagged by compute_alphas(), but raw OHLCV are not.
        lagged_train = train_df.copy()
        lagged_test = test_df.copy()
        for col in base_cols:
            if col in lagged_train.columns:
                lagged_train[col] = lagged_train.groupby('ticker')[col].shift(1)
            if col in lagged_test.columns:
                lagged_test[col] = lagged_test.groupby('ticker')[col].shift(1)
        # Drop rows with NaN from lagging
        lagged_train = lagged_train.dropna(subset=[c for c in base_cols if c in lagged_train.columns])

        # Build features dict for train (using lagged OHLCV)
        train_features = {col: lagged_train[col].values for col in available_cols if col in lagged_train.columns}
        # Add target
        if return_col not in lagged_train.columns:
            logger.warning(f"Target {return_col} not in train_df, skipping evolution")
            return None, 0.0
        train_target = lagged_train[return_col].values
        # GP config: keep simple to avoid overfitting (V2 proven config)
        # Adaptive blend weight handles quality variance instead
        config = GPConfig(
            population_size=150,
            generations=3,
            max_depth=3,
            hall_of_fame_size=3,
        )
        engine = GeneticEngine(config)
        # features dict = OHLCV + alpha columns, target = forward returns
        train_target = lagged_train[return_col].values
        # Align hall_of_fame evolve with lagged train features
        hall_of_fame = engine.evolve(train_features, train_target)

        if not hall_of_fame:
            logger.warning("Evolution produced no individuals, skipping")
            return None, 0.0

        # P1: Ensemble top 3 GP trees (not just best) for robustness
        # Average signals from hall_of_fame[0:3] to reduce variance
        test_features = {col: lagged_test[col].values if col in lagged_test.columns else np.zeros(len(lagged_test))
                        for col in available_cols}
        
        try:
            # Execute all individuals in hall_of_fame
            ensemble_signals = []
            for individual in hall_of_fame:
                signal = individual._execute_tree(individual.tree, test_features)
                signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
                # Normalize each signal to zero mean, unit std
                std_val = np.std(signal)
                if std_val > 1e-9:
                    signal = (signal - np.mean(signal)) / std_val
                ensemble_signals.append(signal)
            
            # Average ensemble signals
            evolved_signal = np.mean(ensemble_signals, axis=0)
            
            # Compute train IC on ensemble signal for adaptive blending
            train_ensemble_signals = []
            for individual in hall_of_fame:
                signal = individual._execute_tree(individual.tree, train_features)
                signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
                train_ensemble_signals.append(signal)
            
            train_signal = np.mean(train_ensemble_signals, axis=0)
            train_ic = float(np.corrcoef(train_signal, train_target)[0, 1]) if len(train_signal) > 1 else 0.0
            if np.isnan(train_ic):
                train_ic = 0.0
            
            test_ret = lagged_test[return_col].values if return_col in lagged_test.columns else np.zeros(len(lagged_test))
            test_ic = float(np.corrcoef(evolved_signal, test_ret)[0, 1]) if len(evolved_signal) > 1 else 0.0
            if np.isnan(test_ic):
                test_ic = 0.0
            
            logger.info(
                f"GP ensemble (n={len(hall_of_fame)}): train_ic={train_ic:.4f}, "
                f"test_ic={test_ic:.4f}, signal_std={np.std(evolved_signal):.4f}"
            )
            return evolved_signal, train_ic
        except Exception as e:
            logger.error(f"GP ensemble execution failed: {e}")
            return None, 0.0
    
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
    
    def _estimate_alpha_turnover(self, df: pd.DataFrame, alpha_col: str) -> float:
        """Estimate day-over-day rank turnover of alpha_col in [0, 1].

        If column missing or single-date DataFrame, return conservative fallback 0.5.
        Turnover = mean( abs( rank_t - rank_{t-1} ) ) / (N_assets - 1)
        """
        if alpha_col not in df.columns:
            return 0.5

        # Check unique dates
        dates = sorted(df['date'].unique())
        if len(dates) < 2:
            return 0.5

        # Pivoting date x ticker to compute rank turnover
        pivot = df.pivot(index='date', columns='ticker', values=alpha_col)
        
        # Rank cross-sectionally per day, normalized to [0, 1]
        # method='average' is stable, pct=True maps rank to [0, 1]
        ranks = pivot.rank(axis=1, pct=True)
        
        # Day-over-day absolute change in rank pct
        diffs = ranks.diff(axis=0).abs()
        
        # Mean absolute change over time and assets
        # If there are NaN values we drop them
        mean_diff = diffs.mean(axis=1).mean()
        if pd.isna(mean_diff):
            return 0.5
            
        # Clip to ensure in [0, 1]
        return float(np.clip(mean_diff, 0.0, 1.0))

    def adjust_alphas_for_cost(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
        train_ics: Dict[str, float],
        cost_per_turnover: float | None = None,
    ) -> Dict[str, float]:
        """Compute cost-adjusted IC for each alpha.

        adjusted_ic = raw_ic - cost * turnover
        """
        if cost_per_turnover is None:
            cost_per_turnover = self.cost_per_turnover

        adjusted_ics = {}
        for col in alpha_cols:
            raw_ic = train_ics.get(col, 0.0)
            turnover = self._estimate_alpha_turnover(df, col)
            adjusted_ics[col] = raw_ic - cost_per_turnover * turnover

        return adjusted_ics

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
        # Vectorized: groupby date, compute all alpha ICs per group
        dates = sorted(train_df_clean['date'].unique())
        _avail_alphas = [a for a in top_alphas if a in train_df_clean.columns]

        def _daily_ics(group: pd.DataFrame) -> pd.Series:
            """Return Series of IC per alpha for one date group."""
            ret = group[return_col]
            ics = {}
            for alpha in _avail_alphas:
                mask = ~(group[alpha].isna() | ret.isna())
                if mask.sum() < 5:
                    ics[alpha] = np.nan
                    continue
                try:
                    ic_val, _ = spearmanr(
                        group.loc[mask, alpha].values,
                        group.loc[mask, return_col].values,
                    )
                    ics[alpha] = ic_val if not np.isnan(ic_val) else np.nan
                except Exception:
                    ics[alpha] = np.nan
            return pd.Series(ics)

        ic_df = train_df_clean.groupby('date').apply(
            _daily_ics, include_groups=False
        )  # index=date, columns=alphas

        daily_ics: Dict[str, pd.Series] = {}
        for alpha in top_alphas:
            if alpha in ic_df.columns:
                daily_ics[alpha] = ic_df[alpha].reindex(dates)
            else:
                daily_ics[alpha] = pd.Series(dtype=float)

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
        
        # Per-alpha z-score normalization (cross-sectional per date) BEFORE blend
        # Prevents high-scale alphas from dominating IC-weighted combination
        df_norm = df[alpha_cols].copy()
        for col in alpha_cols:
            df_norm[col] = df.groupby('date')[col].transform(
                lambda x: (x - x.mean()) / (x.std() + 1e-9)
            )
        
        # Compute weighted average on normalized alphas
        alpha_matrix = df_norm[alpha_cols].values
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

    def run_fold(
        self,
        fold_id: int,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        alpha_cols: List[str],
        return_col: str = 'fwd_ret_5',
        cost_aware: bool | None = None,
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
        cost_aware : bool, optional
            If True, cost-aware alpha selection is enabled for this fold.
            If None, uses self.cost_aware.
        
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
        """
        logger.info(f"Running fold {fold_id}")

        if cost_aware is None:
            cost_aware = self.cost_aware
        
        # Compute alphas on train (full train_df — no embargo yet)
        train_df = self.compute_alphas(train_df)

        # --- Cold-start fix: prepend train tail to test_df for alpha computation ---
        # Phase34 uses rolling windows (5, 10, 20 bars). Without train history,
        # the first ~20 test days get NaN/zero-fill distortion.
        # PIT safe: we only prepend already-embargoed train data, then strip it back.
        warmup_n = 30  # rows per symbol to prepend (covers max rolling window)
        train_tail = (
            train_df
            .groupby('ticker', group_keys=False)
            .tail(warmup_n)
            .copy()
        )
        # Mark original test rows so we can strip warmup back after alpha computation
        is_test_mask = pd.Series(True, index=test_df.index)
        test_df = test_df.copy()
        test_df['_is_test'] = True
        test_with_warmup = pd.concat([train_tail, test_df], ignore_index=True)
        test_with_warmup = test_with_warmup.sort_values(
            ['ticker', 'date'], ignore_index=True
        )
        test_with_warmup = self.compute_alphas(test_with_warmup)
        # Strip warmup rows — keep only original test rows
        keep_mask = test_with_warmup['_is_test'].fillna(False).astype(bool)
        test_df = (
            test_with_warmup.loc[keep_mask]
            .drop(columns=['_is_test'], errors='ignore')
            .reset_index(drop=True)
        )
        
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
        # Split train_df_clean into Train Actual and Validation dynamically (e.g. 2:1 ratio by unique dates)
        unique_dates = sorted(train_df_clean['date'].unique())
        if len(unique_dates) >= 3:
            split_idx = int(len(unique_dates) * 2 / 3)
            val_start_date = unique_dates[split_idx]
            train_actual = train_df_clean[train_df_clean['date'] < val_start_date].reset_index(drop=True)
            val_actual = train_df_clean[train_df_clean['date'] >= val_start_date].reset_index(drop=True)
        else:
            train_actual = train_df_clean
            val_actual = train_df_clean
            
        logger.info(
            f"Fold {fold_id} validation split: "
            f"train_actual={len(train_actual)} rows, val_actual={len(val_actual)} rows"
        )
        
        # Compute IC on actual training set (no label leakage)
        train_ics = self.compute_alpha_ics(train_actual, alpha_cols, return_col)
        
        # Strategy filter: momentum only keeps positive IC alphas
        if hasattr(self, "strategy") and self.strategy == "momentum":
            train_ics = {k: v for k, v in train_ics.items() if v > 0.0}
            
        logger.info(f"Fold {fold_id} train ICs (strategy={self.strategy}): {train_ics}")

        # Stage 6.2: Cost-aware alpha selection
        if cost_aware:
            adjusted_ics = self.adjust_alphas_for_cost(
                train_actual, alpha_cols, train_ics
            )
            top_alphas = self.select_top_alphas(adjusted_ics)
        else:
            # Select top alphas based on train IC
            top_alphas = self.select_top_alphas(train_ics)

        # ------------------------------------------------------------------
        # Stage 3 ML Gate: filter top_alphas through Research Gate
        # Uses validation set (val_actual) — PIT safe, no look-ahead.
        # ------------------------------------------------------------------
        gated_alphas, gate_results = self.validate_alpha_with_research_gate(
            top_alphas=top_alphas,
            train_ics=train_ics,
            train_df_clean=val_actual,
            return_col=return_col,
        )

        # ------------------------------------------------------------------
        # Stage 4: optional XGBoost path (use_xgboost=True) vs baseline
        # Baseline: IC-weighted signal from gated alphas (unchanged).
        # XGBoost: train XGBoostAlphaEnsemble on train_actual MultiIndex,
        #          predict on test_df MultiIndex, standardize to portfolio_signal.
        # PIT Safety: ensemble trains only on embargoed train_actual.
        # ------------------------------------------------------------------
        if self.use_xgboost and len(train_actual) > 0 and len(gated_alphas) > 0:
            try:
                # Convert flat ['date','ticker'] -> MultiIndex ['date','symbol']
                X_train_multi = (
                    train_actual
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
                # Align raw_preds (indexed by date, symbol) with test_df (columns date, ticker) to prevent drift
                preds_df = raw_preds.reset_index().rename(columns={'symbol': 'ticker', 0: 'pred'})
                merged = test_df[['date', 'ticker']].merge(preds_df, on=['date', 'ticker'], how='left')
                preds_flat = merged['pred'].fillna(0.0).values
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
        # Evolved Alpha Blending (optional) with Adaptive Weight
        # If enable_evolved=True, run inline GP evolution on train_actual,
        # execute best tree on test_df, and blend with hand-crafted signal.
        # PIT Safety: evolution trains only on train_actual (embargoed).
        # Adaptive: blend weight scales with train_ic quality (cap at user weight).
        # ------------------------------------------------------------------
        if self.enable_evolved and len(train_actual) > 0:
            evolved_signal, gp_train_ic = self._evolve_inline_signal(train_actual, test_df, return_col)
            if evolved_signal is not None:
                # Align evolved signal length with portfolio_signal
                if len(evolved_signal) == len(portfolio_signal):
                    # Adaptive blend: scale weight by GP train quality
                    # w_adaptive = min(user_weight, abs(train_ic) * scale_factor)
                    # scale_factor=2 means IC=0.05 → weight=0.10, IC=0.10 → weight=0.20
                    abs_train_ic = abs(gp_train_ic)
                    scale_factor = 2.0
                    w_adaptive = min(self.evolved_blend_weight, abs_train_ic * scale_factor)
                    # P2: Ceiling protection - cap at 25% to prevent overfit
                    # Ensures hand-crafted signal dominates (≥75%)
                    ceiling = 0.25
                    w_evo = min(w_adaptive, ceiling)
                    # Floor: at least 10% of user weight to avoid zero contribution
                    w_evo = max(w_evo, self.evolved_blend_weight * 0.1)
                    w_hand = 1.0 - w_evo
                    portfolio_signal = pd.Series(
                        w_evo * evolved_signal + w_hand * portfolio_signal.values,
                        index=portfolio_signal.index
                    )
                    logger.info(
                        f"Fold {fold_id}: Evolved signal blended "
                        f"(evolved={w_evo:.3f}, handcrafted={w_hand:.3f}, "
                        f"gp_train_ic={gp_train_ic:.4f}, adaptive=True)"
                    )
                else:
                    logger.warning(
                        f"Fold {fold_id}: Evolved signal length mismatch "
                        f"({len(evolved_signal)} vs {len(portfolio_signal)}), skipping blend"
                    )

        # Strategy filter: mean reversion reverses signal direction
        if hasattr(self, "strategy") and self.strategy == "mean_reversion":
            portfolio_signal = -portfolio_signal

        # --- Fix 3+4: Raw signal IC (before Stage 2) + Z-score normalization ---
        # Apply cross-sectional z-score normalization to raw signal before blending
        # This prevents scale differences between alphas from dominating weights
        test_df_copy = test_df.copy()
        test_df_copy['_raw_signal'] = portfolio_signal
        # Z-score per date (cross-sectional)
        test_df_copy['_raw_signal'] = test_df_copy.groupby('date')['_raw_signal'].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-9)
        )
        portfolio_signal = test_df_copy['_raw_signal']

        # Compute raw signal IC (pre Stage 2) — this is the true predictive power
        raw_signal_ic = self.compute_ic(portfolio_signal, test_df[return_col])
        
        # Compute daily cross-sectional IC for raw signal (more robust metric)
        test_df_with_signal = test_df.copy()
        test_df_with_signal['_raw_signal'] = portfolio_signal
        raw_signal_daily_cs_ic = self.compute_daily_cs_ic(
            test_df_with_signal, '_raw_signal', return_col
        )
        
        logger.info(
            f"Fold {fold_id} raw signal IC: {raw_signal_ic:.4f}, "
            f"daily CS IC: {raw_signal_daily_cs_ic:.4f}"
        )

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

        # Compute test IC for each alpha
        test_ics = self.compute_alpha_ics(test_df, alpha_cols, return_col)
        
        # Compute portfolio IC on test set
        portfolio_ic = self.compute_ic(portfolio_signal, test_df[return_col])
        
        # Compute portfolio returns (signal * forward return)
        portfolio_returns = portfolio_signal * test_df[return_col]
        portfolio_returns = portfolio_returns.dropna()

        # Build daily aggregated returns (sum over assets on each date)
        # We must align portfolio_returns with date and group/sum.
        # Ensure PIT Safety: date aggregation is done on test_df date series.
        # Since portfolio_returns might have dropped NaNs, we align with test_df index first.
        aligned_df = pd.DataFrame({
            'date': test_df.loc[portfolio_returns.index, 'date'],
            'p_ret': portfolio_returns
        })
        daily_series = aligned_df.groupby('date')['p_ret'].sum().sort_index()

        # Plumb slippage and commission to actual realized portfolio returns
        df_weights = pd.DataFrame({'date': test_df['date'], 'ticker': test_df['ticker'], 'weight': portfolio_signal})
        pivot_weights = df_weights.pivot(index='date', columns='ticker', values='weight').fillna(0.0)
        daily_turnover = pivot_weights.diff(axis=0).abs().sum(axis=1)
        if len(daily_turnover) > 0:
            daily_turnover.iloc[0] = pivot_weights.iloc[0].abs().sum()

        daily_turnover = daily_turnover.reindex(daily_series.index, fill_value=0.0)
        daily_series = daily_series - (daily_turnover * self.cost_per_turnover)

        # Stage 6.3: Active Drawdown Control
        if self.drawdown_control and len(daily_series) > 0:
            # We track cumulative NAV/drawdowns strictly sequentially
            cum_rets = (1 + daily_series).cumprod()
            running_max = cum_rets.expanding().max()
            drawdowns = (cum_rets - running_max) / running_max
            
            # Find the first date where drawdown breaches the threshold
            # Drawdowns are <= 0. Threshold is positive e.g. 0.05. Breach is drawdown < -drawdown_threshold
            breaches = drawdowns < -self.drawdown_threshold
            
            if breaches.any():
                breach_date = breaches.idxmax() # First date where True
                
                # Daily return = 0.0 strictly after the first breach day, preserving the breach day return
                # So for dates > breach_date, daily return is 0
                dates_after = daily_series.index > breach_date
                daily_series.loc[dates_after] = 0.0
                
                # Update row-level portfolio_returns to be zeroed out as well, aligning with daily returns
                # Every row in portfolio_returns whose date is > breach_date should be 0.0
                # Let's map date back to aligned_df
                aligned_df['date_dt'] = pd.to_datetime(aligned_df['date'])
                breach_dt = pd.to_datetime(breach_date)
                
                # Find indices where date > breach_date
                indices_after = aligned_df[aligned_df['date_dt'] > breach_dt].index
                portfolio_returns.loc[indices_after] = 0.0
                
                logger.info(f"Fold {fold_id}: Drawdown control stop-out triggered at {breach_date}")

        # Compute Sharpe and Max DD from daily aggregated returns series
        sharpe = self.compute_sharpe_ratio(daily_series)
        max_dd = self.compute_max_drawdown(daily_series)
        total_return = daily_series.sum()
        pnl_val = total_return * self.initial_capital
        
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
            portfolio_pnl_vnd=pnl_val,
            portfolio_ic=portfolio_ic,
            raw_signal_ic=raw_signal_ic,
            raw_signal_daily_cs_ic=raw_signal_daily_cs_ic,
            n_train_samples=len(train_df_clean),
            n_test_samples=len(test_df),
            gate_results=gate_results,
            gated_alphas=gated_alphas,
        )
        
        logger.info(
            f"Fold {fold_id} results: RawIC={raw_signal_ic:.4f}, "
            f"RawCS_IC={raw_signal_daily_cs_ic:.4f}, "
            f"PortfolioIC={portfolio_ic:.4f}, "
            f"Sharpe={sharpe:.4f}, MaxDD={max_dd:.2%}, PnL={pnl_val:+,.0f} VND"
        )
        
        return metrics
    
    def run_walk_forward(
        self,
        splits: List[Tuple[pd.DataFrame, pd.DataFrame]],
        alpha_cols: List[str],
        return_col: str = 'fwd_ret_5',
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
        
        Returns
        -------
        WalkForwardResult
            Complete backtest results
        """
        logger.info(f"Starting walk-forward backtest with {len(splits)} folds")
        
        fold_metrics = []
        
        for fold_id, (train_df, test_df) in enumerate(splits, start=1):
            metrics = self.run_fold(fold_id, train_df, test_df, alpha_cols, return_col)
            fold_metrics.append(metrics)
        
        # Aggregate results
        avg_ic_by_alpha = {}
        for alpha_col in alpha_cols:
            ics = [m.alpha_ics.get(alpha_col, 0.0) for m in fold_metrics]
            avg_ic_by_alpha[alpha_col] = np.mean(ics)
        
        avg_portfolio_ic = np.mean([m.portfolio_ic for m in fold_metrics])
        avg_raw_signal_ic = np.mean([m.raw_signal_ic for m in fold_metrics])
        avg_raw_signal_daily_cs_ic = np.mean([m.raw_signal_daily_cs_ic for m in fold_metrics])
        avg_portfolio_sharpe = np.mean([m.portfolio_sharpe for m in fold_metrics])
        avg_portfolio_max_dd = np.mean([m.portfolio_max_dd for m in fold_metrics])
        avg_portfolio_pnl_vnd = np.mean([m.portfolio_pnl_vnd for m in fold_metrics])
        
        result = WalkForwardResult(
            fold_metrics=fold_metrics,
            avg_ic_by_alpha=avg_ic_by_alpha,
            avg_portfolio_sharpe=avg_portfolio_sharpe,
            avg_portfolio_max_dd=avg_portfolio_max_dd,
            avg_portfolio_ic=avg_portfolio_ic,
            avg_raw_signal_ic=avg_raw_signal_ic,
            avg_raw_signal_daily_cs_ic=avg_raw_signal_daily_cs_ic,
            avg_portfolio_pnl_vnd=avg_portfolio_pnl_vnd,
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
    
    workspace = Path(__file__).resolve().parents[3]
    _REPO_ROOT = workspace
    if str(_REPO_ROOT / 'src') not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / 'src'))
        
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
