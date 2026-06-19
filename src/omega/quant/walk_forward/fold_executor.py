"""Fold execution mixin for walk-forward engine."""
from __future__ import annotations

import logging
from typing import List, Tuple

import numpy as np
import pandas as pd

from omega.quant.ml.ensemble_xgboost import XGBoostAlphaEnsemble
from omega.quant.walk_forward.gate_utils import _is_gate_verdict_pass
from omega.quant.walk_forward.metrics import FoldMetrics, WalkForwardResult

logger = logging.getLogger(__name__)


class FoldExecutorMixin:
    """Single-fold and full walk-forward execution."""

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

        # ==============================================================================
        # P10: Multi-Horizon Blending Path (opt-in)
        # ==============================================================================
        if self.multi_horizon_blend:
            logger.info(
                f"[P10] Fold {fold_id}: Multi-horizon blending enabled, "
                f"horizons={self.blend_horizons}, method={self.blend_weight_method}"
            )

            horizon_results = {}
            horizon_details = {}

            # Compute signal for each horizon independently
            for horizon in self.blend_horizons:
                horizon_return_col = f'fwd_ret_{horizon}'

                # FIX 1, 2, 5: Updated signature with quality_metrics dict and final_objective_return_col
                # Role21 Fix 2026-06-10: Now returns gate_metadata as 5th value
                signal, quality_metrics, gated, gate_res, gate_meta = self._compute_horizon_signal(
                    fold_id=fold_id,
                    train_df=train_df,
                    test_df=test_df,
                    alpha_cols=alpha_cols,
                    return_col=horizon_return_col,
                    horizon=horizon,
                    cost_aware=cost_aware,
                    final_objective_return_col=return_col,  # FIX 5: final objective alignment
                )

                if signal is not None:
                    horizon_results[horizon] = (signal, quality_metrics)
                    # FIX 6: Store comprehensive diagnostics
                    # Role21 Fix 2026-06-10: Added gate_metadata to horizon_details
                    horizon_details[horizon] = {
                        'gated_alphas': gated,
                        'gate_results': gate_res,
                        'quality_metrics': quality_metrics,
                        'horizon_return_col': horizon_return_col,
                        'included': True,
                        'gate_metadata': gate_meta,
                    }
                else:
                    # FIX 6: Track excluded horizons in diagnostics
                    # Role21 Fix 2026-06-10: Added gate_metadata to horizon_details
                    horizon_details[horizon] = {
                        'gated_alphas': [],
                        'gate_results': gate_res,
                        'quality_metrics': quality_metrics,
                        'horizon_return_col': horizon_return_col,
                        'included': False,
                        'exclusion_reason': (
                            gate_meta.get('exclusion_reason', 'gate_failed_or_missing_data')
                            if gate_meta
                            else 'gate_failed_or_missing_data'
                        ),
                        'gate_metadata': gate_meta,
                    }

            # FIX 3: All-horizon failure fallback to single-horizon baseline
            portfolio_signal = None
            fallback_used = False
            fallback_reason = None

            if len(horizon_results) == 0:
                fallback_reason = "all_horizons_failed_or_missing"
                logger.warning(
                    f"[P10] Fold {fold_id}: All requested horizons failed/missing. "
                    f"Falling back to single-horizon baseline using return_col={return_col}"
                )
                fallback_used = True
            else:
                # Attempt to blend
                portfolio_signal = self._blend_horizon_signals(
                    horizon_results, method=self.blend_weight_method
                )

                # FIX 3 & 4: If blend returns None (all non-positive quality), fallback
                if portfolio_signal is None:
                    fallback_reason = "all_quality_non_positive"
                    logger.warning(
                        f"[P10] Fold {fold_id}: Blend returned None (all quality non-positive). "
                        f"Falling back to single-horizon baseline using return_col={return_col}"
                    )
                    fallback_used = True

            # FIX 3: Execute fallback to approved single-horizon baseline
            if fallback_used:
                logger.info(
                    f"[P10] Fold {fold_id}: Executing fallback to single-horizon baseline "
                    f"(return_col={return_col})"
                )
                # Fall through to the standard single-horizon path below
                # by setting multi_horizon_blend to False temporarily
                self.multi_horizon_blend = False
                # Recursively call run_fold with single-horizon mode
                # (This ensures we use the exact same baseline logic)
                result = self.run_fold(
                    fold_id=fold_id,
                    train_df=train_df,
                    test_df=test_df,
                    alpha_cols=alpha_cols,
                    return_col=return_col,
                    cost_aware=cost_aware,
                )
                # Restore multi_horizon_blend flag
                self.multi_horizon_blend = True
                # Add fallback diagnostic to result
                # (FoldMetrics doesn't have a diagnostics field, so log it)
                logger.info(
                    f"[P10] Fold {fold_id}: Fallback complete. "
                    f"Reason: {fallback_reason}, "
                    f"Requested horizons: {self.blend_horizons}, "
                    f"Successful horizons: {list(horizon_results.keys())}"
                )
                return result

            # Normal multi-horizon path (blend succeeded)
            # For FoldMetrics reporting: use first successful horizon's details
            # (FoldMetrics doesn't yet support per-horizon reporting)
            # Role21 Fix 2026-06-10: Also extract gate_metadata
            # Role20 P10 Fix 2026-06-10: Use first included horizon, not first requested
            # horizon_results only contains successful horizons where signal != None
            first_horizon = list(horizon_results.keys())[0]
            gated_alphas = horizon_details[first_horizon]['gated_alphas']
            gate_results = horizon_details[first_horizon]['gate_results']
            gate_metadata = horizon_details[first_horizon].get('gate_metadata', None)

            # Compute raw signal IC using default return_col (for P9 comparison)
            raw_signal_ic = self.compute_ic(portfolio_signal, test_df[return_col])
            test_df_with_signal = test_df.copy()
            test_df_with_signal['_raw_signal'] = portfolio_signal
            raw_signal_daily_cs_ic = self.compute_daily_cs_ic(
                test_df_with_signal, '_raw_signal', return_col
            )

            # FIX 6: Log comprehensive diagnostics
            logger.info(
                f"[P10] Fold {fold_id} multi-horizon diagnostics:\n"
                f"  Requested horizons: {self.blend_horizons}\n"
                f"  Included horizons: {[h for h, d in horizon_details.items() if d.get('included', False)]}\n"
                f"  Excluded horizons: {[h for h, d in horizon_details.items() if not d.get('included', True)]}\n"
                f"  Blend method: {self.blend_weight_method}\n"
                f"  Fallback used: {fallback_used}"
            )
            for h, details in horizon_details.items():
                if details.get('included', False):
                    qm = details['quality_metrics']
                    gate_passed = sum(
                        1
                        for res in details['gate_results'].values()
                        if _is_gate_verdict_pass(res.get('verdict'))
                    )
                    gate_total = len(details['gate_results'])
                    logger.info(
                        f"  Horizon {h}: train_ic={qm.get('train_ic', 0):.4f}, "
                        f"val_ic={qm.get('validation_ic', 0):.4f}, "
                        f"final_obj_val_ic={qm.get('final_objective_validation_ic', 0):.4f}, "
                        f"gate={gate_passed}/{gate_total}"
                    )

            logger.info(
                f"[P10] Fold {fold_id} multi-horizon raw signal: "
                f"IC={raw_signal_ic:.4f}, daily_cs_ic={raw_signal_daily_cs_ic:.4f}"
            )

            # Note: XGBoost and evolved signal are disabled in multi-horizon mode
            # to keep P10 implementation focused and avoid complexity

            # For metrics reporting: use train_df as train_df_clean
            # (embargo is applied per-horizon inside _compute_horizon_signal)
            train_df_clean = train_df

        else:
            # ==============================================================================
            # Original Single-Horizon Path (default behavior, unchanged)
            # ==============================================================================

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

            # Role21 Fix 2026-06-10: Single-horizon path doesn't use structured gate metadata
            gate_metadata = None

        # ==============================================================================
        # Both paths converge here: Stage 2 constraints apply to both single-horizon
        # and multi-horizon signals
        # ==============================================================================

        # ------------------------------------------------------------------
        # Stage 2 behavioral enforcement (top-N, rebalance cadence, sector cap)
        # Applied AFTER IC-weighted signal combination, BEFORE return computation.
        # PIT safety preserved: test_df signals are already T-1 lagged upstream.
        # ------------------------------------------------------------------
        try:
            portfolio_signal = self._apply_stage2_constraints(
                test_df=test_df,
                raw_signal=portfolio_signal,
                top_alphas=gated_alphas,
                dynamic_rebalance=True,
                train_df=train_df,
            )
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            # Backward-compatible path for tests or external monkeypatches that
            # still expose the original 3-argument Stage 2 hook signature.
            logger.warning(
                "Stage 2 constraints hook does not accept P9 kwargs; "
                "falling back to legacy call signature"
            )
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
                breach_date = breaches.idxmax()  # First date where True

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
        # Role21 Fix 2026-06-10: Added gate_metadata field
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
            gate_metadata=gate_metadata,
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
