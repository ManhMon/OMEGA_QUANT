"""Alpha selection mixin for Phase 3.5 walk-forward engine."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from omega.quant.ml.gate_validator import validate_research_gate
from omega.quant.walk_forward.risk_adjusted_alpha_score import (
    compute_icir,
    compute_positive_fold_rate,
    bh_fdr_qvalues,
    compute_ic_pvalue,
    classify_research_gate_verdict,
    filter_alphas_by_recovery_mode,
    RESEARCH_VERDICT_PROMOTE_CANDIDATE,
    RESEARCH_VERDICT_ENSEMBLE_ONLY,
    RESEARCH_VERDICT_REVIEW,
    RESEARCH_VERDICT_RETIRE,
    RESEARCH_POOL_FULL,
    RESEARCH_POOL_RECOVERY_ONLY,
    RESEARCH_POOL_RECOVERABLE_ONLY,
    VALID_RESEARCH_POOL_MODES,
)

logger = logging.getLogger(__name__)


class AlphaSelectionMixin:
    """Alpha IC computation, cost adjustment, selection, and gate validation."""

    def risk_adjusted_select(
        self,
        alpha_cols: List[str],
        *,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        train_ics: Dict[str, float],
        val_ics: Optional[Dict[str, float]] = None,
        daily_ics: Optional[Dict[str, pd.Series]] = None,
        expected_sharpe_contrib: Optional[Dict[str, float]] = None,
        max_drawdowns: Optional[Dict[str, float]] = None,
        return_col: str = "fwd_ret_5",
        top_n: int = 5,
        min_composite_score: float = 0.35,
        require_positive_val_ic: bool = True,
        max_overfit_gap: float = 0.15,
    ) -> "RiskAdjustedSelectionResult":
        """Opt-in risk-adjusted alpha selection (GATE: RISK_ADJUSTED_ALPHA_SELECTION_20260614).

        Computes composite risk-adjusted scores using only embargoed train/val
        data (no test future) and returns a selection result with paper-trading
        gate PASS/FAIL and evidence.

        Parameters
        ----------
        alpha_cols : list of str
            Alpha column names.
        train_df, val_df : pd.DataFrame
            Embargoed training and validation data.
        train_ics : dict
            Per-alpha IC on training set.
        val_ics, daily_ics : dict, optional
            Precomputed validation ICs / daily IC series.
        expected_sharpe_contrib, max_drawdowns : dict, optional
            Per-alpha Sharpe / drawdown if safely available.
        return_col : str
            Forward return column.
        top_n : int
            Max alphas to select.
        min_composite_score : float
            Minimum composite score threshold.
        require_positive_val_ic : bool
            Require positive validation IC.
        max_overfit_gap : float
            Maximum allowed overfit gap.

        Returns
        -------
        RiskAdjustedSelectionResult
        """
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            score_alpha_candidates,
            select_alphas_risk_adjusted,
        )

        break_downs = score_alpha_candidates(
            alpha_cols,
            train_df=train_df,
            val_df=val_df,
            train_ics=train_ics,
            val_ics=val_ics,
            daily_ics=daily_ics,
            expected_sharpe_contrib=expected_sharpe_contrib,
            max_drawdowns=max_drawdowns,
            return_col=return_col,
        )

        result = select_alphas_risk_adjusted(
            break_downs,
            top_n=top_n,
            min_composite_score=min_composite_score,
            require_positive_val_ic=require_positive_val_ic,
            max_overfit_gap=max_overfit_gap,
        )

        logger.info(
            f"[RiskAdj] Selected {len(result.selected_alphas)}/{len(alpha_cols)} alphas: "
            f"gate={result.paper_trading_gate}"
        )
        return result

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

            # P8: IC-Decay Weighting - compute IC on 3 sub-windows with exponential decay
            # Weights: [0.2, 0.3, 0.5] for [old, middle, recent] thirds of training data
            dates = sorted(df['date'].unique())
            n_dates = len(dates)

            if n_dates >= 30:  # Only apply decay if enough history
                third = n_dates // 3
                windows = [
                    (0, third, 0.2),           # oldest third
                    (third, 2*third, 0.3),     # middle third
                    (2*third, n_dates, 0.5)    # most recent third
                ]

                weighted_ic = 0.0
                weight_sum = 0.0

                for start_idx, end_idx, weight in windows:
                    window_dates = dates[start_idx:end_idx]
                    window_df = df[df['date'].isin(window_dates)]

                    if len(window_df) > 0:
                        ic_val = self.compute_ic(window_df[alpha_col], window_df[return_col])
                        weighted_ic += ic_val * weight
                        weight_sum += weight

                if weight_sum > 0:
                    ics[alpha_col] = weighted_ic / weight_sum
                else:
                    ics[alpha_col] = self.compute_ic(df[alpha_col], df[return_col])
            else:
                # Fallback to simple IC if insufficient history
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
        used_fallback = False
        if not gated_alphas:
            logger.warning(
                "All alphas failed Research Gate — falling back to top_alphas "
                f"({top_alphas})"
            )
            gated_alphas = list(top_alphas)
            used_fallback = True

        # Role21 Fix 2026-06-10: Clarify selection source in logs
        if used_fallback:
            logger.info(
                f"Selected alphas (fallback candidates) "
                f"({len(gated_alphas)}/{len(top_alphas)}): {gated_alphas}"
            )
        else:
            logger.info(
                f"Selected alphas (gate-passed) "
                f"({len(gated_alphas)}/{len(top_alphas)}): {gated_alphas}"
            )
        return gated_alphas, gate_results

    def apply_research_alpha_gates(
        self,
        alpha_fold_ics: Dict[str, List[float]],
        *,
        fallback_rate: float = 0.0,
        bh_fdr_threshold: float = 0.05,
        min_icir_promote: float = 0.5,
        min_icir_ensemble: float = 0.3,
        min_pos_fold_rate_promote: float = 0.6,
        min_pos_fold_rate_ensemble: float = 0.4,
        allowed_verdicts: Optional[List[str]] = None,
    ) -> Tuple[List[str], Dict[str, dict]]:
        """Apply research alpha gates to filter alphas by verdict.

        GATE: RESEARCH_ALPHA_GATES_20260614
        Opt-in only — does not change default behavior.

        Parameters
        ----------
        alpha_fold_ics : dict
            Mapping of alpha name to list of per-fold IC values.
        fallback_rate : float
            Overall fallback rate for the variant (0 to 1).
        bh_fdr_threshold : float
            BH-FDR significance threshold.
        min_icir_promote : float
            Minimum ICIR for PROMOTE_CANDIDATE.
        min_icir_ensemble : float
            Minimum ICIR for ENSEMBLE_ONLY.
        min_pos_fold_rate_promote : float
            Minimum positive fold rate for PROMOTE_CANDIDATE.
        min_pos_fold_rate_ensemble : float
            Minimum positive fold rate for ENSEMBLE_ONLY.
        allowed_verdicts : list of str, optional
            If provided, only alphas with these verdicts are kept.
            Default: [PROMOTE_CANDIDATE, ENSEMBLE_ONLY].

        Returns
        -------
        gated_alphas : list of str
            Alphas that passed the research gates.
        gate_details : dict
            Per-alpha gate metrics and verdict.
        """
        if allowed_verdicts is None:
            allowed_verdicts = [
                RESEARCH_VERDICT_PROMOTE_CANDIDATE,
                RESEARCH_VERDICT_ENSEMBLE_ONLY,
            ]

        # Compute per-alpha metrics
        p_values: Dict[str, float] = {}
        alpha_metrics: Dict[str, dict] = {}

        for alpha_name, ics in alpha_fold_ics.items():
            mean_ic = sum(ics) / len(ics) if ics else 0.0
            icir = compute_icir(ics)
            pos_rate = compute_positive_fold_rate(ics)
            p_val = compute_ic_pvalue(ics)
            p_values[alpha_name] = p_val
            alpha_metrics[alpha_name] = {
                "mean_ic": mean_ic,
                "icir": icir,
                "positive_fold_rate": pos_rate,
            }

        # Compute BH-FDR q-values
        alpha_names = sorted(p_values.keys())
        p_vals_ordered = [p_values[a] for a in alpha_names]
        q_vals = bh_fdr_qvalues(p_vals_ordered)
        q_value_map = dict(zip(alpha_names, q_vals))

        # Classify verdicts
        gate_details: Dict[str, dict] = {}
        gated_alphas: List[str] = []

        for alpha_name in alpha_names:
            metrics = alpha_metrics[alpha_name]
            q_val = q_value_map.get(alpha_name, 1.0)
            verdict = classify_research_gate_verdict(
                mean_ic=metrics["mean_ic"],
                icir=metrics["icir"],
                positive_fold_rate=metrics["positive_fold_rate"],
                q_value=q_val,
                fallback_rate=fallback_rate,
                min_icir_promote=min_icir_promote,
                min_icir_ensemble=min_icir_ensemble,
                min_pos_fold_rate_promote=min_pos_fold_rate_promote,
                min_pos_fold_rate_ensemble=min_pos_fold_rate_ensemble,
                bh_fdr_threshold=bh_fdr_threshold,
            )
            gate_details[alpha_name] = {
                "mean_ic": metrics["mean_ic"],
                "icir": metrics["icir"],
                "positive_fold_rate": metrics["positive_fold_rate"],
                "p_value": p_values[alpha_name],
                "q_value": q_val,
                "verdict": verdict,
            }
            if verdict in allowed_verdicts:
                gated_alphas.append(alpha_name)

            logger.info(
                f"Research Gate [{alpha_name}]: verdict={verdict} "
                f"(mean_ic={metrics['mean_ic']:.4f}, icir={metrics['icir']:.4f}, "
                f"pos_fold_rate={metrics['positive_fold_rate']:.2f}, q={q_val:.4f})"
            )

        return gated_alphas, gate_details

    def filter_recovery_pool(
        self,
        alpha_cols: List[str],
        recovery_report,
        *,
        research_pool_mode: str = RESEARCH_POOL_FULL,
    ) -> List[str]:
        """Filter alpha pool by recovery classification (opt-in).

        GATE: RECOVERY_SELECTOR_OPT_IN_20260614

        Opt-in only — default ``research_pool_mode='full'`` returns the
        input unchanged.  Supports:

        - ``full``: no filtering (default, backward-compatible).
        - ``recovery_only``: exclude CONFIRMED_RETIRE alphas.
        - ``recoverable_only``: keep only RECOVERABLE alphas.

        PIT Safety
        ----------
        Uses only recovery classifications derived from OOS fold-level
        metrics.  No new data access or look-ahead.

        Fallback
        --------
        If filtering produces an empty list, logs a warning and returns
        the original ``alpha_cols`` unchanged.  Fallback remains failure
        — no silent degradation.

        Parameters
        ----------
        alpha_cols : list of str
            Full alpha column names.
        recovery_report : AlphaRecoveryReport
            Recovery diagnostics from
            ``compute_alpha_recovery_diagnostics()``.
        research_pool_mode : str
            One of ``'full'``, ``'recovery_only'``,
            ``'recoverable_only'``.

        Returns
        -------
        list of str
            Filtered alpha names.
        """
        filtered = filter_alphas_by_recovery_mode(
            alpha_cols, recovery_report, mode=research_pool_mode
        )

        if research_pool_mode != RESEARCH_POOL_FULL:
            logger.info(
                f"[RecoveryPool] mode={research_pool_mode}: "
                f"{len(filtered)}/{len(alpha_cols)} alphas retained"
            )

        if not filtered and alpha_cols:
            logger.warning(
                f"[RecoveryPool] mode={research_pool_mode} produced empty pool "
                f"from {len(alpha_cols)} alphas — falling back to full pool"
            )
            return list(alpha_cols)

        return filtered
