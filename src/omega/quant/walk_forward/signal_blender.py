"""Signal blending mixin for walk-forward engine."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from omega.quant.walk_forward.gate_utils import _is_gate_verdict_pass

logger = logging.getLogger(__name__)


class SignalBlendingMixin:
    """IC-weighted signal generation and multi-horizon blending."""

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

    def _compute_horizon_signal(
        self,
        fold_id: int,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        alpha_cols: List[str],
        return_col: str,
        horizon: int,
        cost_aware: bool,
        final_objective_return_col: str = 'fwd_ret_5',
    ) -> Tuple[Optional[pd.Series], Dict[str, float], List[str], Dict[str, dict]]:
        """Compute raw signal for a single horizon without Stage 2 constraints.

        P10: Helper for multi-horizon blending. Computes IC, gates alphas,
        and produces raw portfolio signal for one return horizon.

        Parameters
        ----------
        fold_id : int
            Fold identifier (for logging)
        train_df : pd.DataFrame
            Training data with alphas already computed
        test_df : pd.DataFrame
            Test data with alphas already computed
        alpha_cols : list of str
            Alpha column names
        return_col : str
            Forward return column for this horizon (e.g., 'fwd_ret_1')
        horizon : int
            Horizon length in days (e.g., 1, 3, 5)
        cost_aware : bool
            If True, apply cost-aware alpha selection
        final_objective_return_col : str
            Final objective return column (usually 'fwd_ret_5') for measuring
            contribution to final monetization target

        Returns
        -------
        raw_signal : pd.Series or None
            Raw portfolio signal (no Stage 2 constraints), or None if horizon fails
        quality_metrics : dict
            Quality metrics with keys: 'train_ic', 'validation_ic',
            'final_objective_validation_ic', 'own_target_train_ic', 'own_target_validation_ic'
        gated_alphas : list of str
            Alphas that passed research gate for this horizon
        gate_results : dict
            Research gate results per alpha

        Notes
        -----
        PIT Safety: Applies horizon-specific embargo (last h rows per ticker).
        No Stage 2 constraints applied here (caller applies after blending).

        Gate Failure Detection: If all alphas fail the research gate (all gate
        results are False), this horizon is excluded (returns None) even if
        validate_alpha_with_research_gate() falls back to top_alphas.
        """
        logger.info(f"[P10] Computing horizon signal: fold={fold_id}, horizon={horizon}, return_col={return_col}")

        # Initialize empty quality metrics
        quality_metrics = {
            'train_ic': 0.0,
            'validation_ic': 0.0,
            'final_objective_validation_ic': 0.0,
            'own_target_train_ic': 0.0,
            'own_target_validation_ic': 0.0,
        }

        # Check if return_col exists in data
        if return_col not in train_df.columns or return_col not in test_df.columns:
            logger.warning(f"[P10] Return column {return_col} not found, skipping horizon {horizon}")
            empty_gate_metadata = {
                'selection_source': 'excluded',
                'exclusion_reason': 'return_col_not_found',
                'used_fallback_candidates': False,
                'gate_passed_count': 0,
                'gate_total': 0,
                'gate_required_passes': self.p10_gate_min_pass,
                'gate_mode': self.p10_gate_mode,
                'gate_passed_alphas': [],
            }
            return None, quality_metrics, [], {}, empty_gate_metadata

        # Horizon-specific embargo: drop last h rows per ticker from train IC computation
        _tail_rank = train_df.groupby('ticker').cumcount(ascending=False)
        train_df_clean = train_df[_tail_rank >= horizon].reset_index(drop=True)
        logger.info(
            f"[P10] Horizon {horizon} embargo: "
            f"train rows before={len(train_df)}, after={len(train_df_clean)}"
        )

        if len(train_df_clean) < 10:
            logger.warning(f"[P10] Insufficient train data after embargo for horizon {horizon}")
            empty_gate_metadata = {
                'selection_source': 'excluded',
                'exclusion_reason': 'insufficient_train_data',
                'used_fallback_candidates': False,
                'gate_passed_count': 0,
                'gate_total': 0,
                'gate_required_passes': self.p10_gate_min_pass,
                'gate_mode': self.p10_gate_mode,
                'gate_passed_alphas': [],
            }
            return None, quality_metrics, [], {}, empty_gate_metadata

        # Split into train_actual and validation for IC computation
        unique_dates = sorted(train_df_clean['date'].unique())
        if len(unique_dates) >= 3:
            split_idx = int(len(unique_dates) * 2 / 3)
            val_start_date = unique_dates[split_idx]
            train_actual = train_df_clean[train_df_clean['date'] < val_start_date].reset_index(drop=True)
            val_actual = train_df_clean[train_df_clean['date'] >= val_start_date].reset_index(drop=True)
        else:
            train_actual = train_df_clean
            val_actual = train_df_clean

        # Compute IC on train_actual using this horizon's return column
        train_ics = self.compute_alpha_ics(train_actual, alpha_cols, return_col)

        # Strategy filter: momentum only keeps positive IC alphas
        if hasattr(self, "strategy") and self.strategy == "momentum":
            train_ics = {k: v for k, v in train_ics.items() if v > 0.0}

        logger.info(f"[P10] Horizon {horizon} train ICs: {train_ics}")

        # Cost-aware alpha selection if enabled
        if cost_aware:
            adjusted_ics = self.adjust_alphas_for_cost(train_actual, alpha_cols, train_ics)
            top_alphas = self.select_top_alphas(adjusted_ics)
        else:
            top_alphas = self.select_top_alphas(train_ics)

        # Research gate validation using validation set
        gated_alphas, gate_results = self.validate_alpha_with_research_gate(
            top_alphas=top_alphas,
            train_ics=train_ics,
            train_df_clean=val_actual,
            return_col=return_col,
        )

        # FIX 2 + P10 Gate Tuning: Check horizon eligibility based on gate mode
        # Use robust verdict checker to avoid truthiness bugs (P10 hotfix 2026-06-09)
        gate_passed_count = sum(1 for res in gate_results.values() if _is_gate_verdict_pass(res.get('verdict')))

        # P10 Gate Tuning: Determine if horizon should be excluded based on gate mode
        horizon_excluded = False
        used_fallback_candidates = False
        exclusion_reason = None

        if self.p10_gate_mode == "strict":
            # Strict mode: exclude if no gates passed (current behavior)
            if gate_passed_count == 0:
                horizon_excluded = True
                exclusion_reason = "strict_mode_zero_passes"
        elif self.p10_gate_mode == "relaxed":
            # Relaxed mode: check if horizon meets relaxed eligibility criteria
            meets_min_pass = gate_passed_count >= self.p10_gate_min_pass
            has_fallback_candidates = (
                self.p10_gate_allow_fallback_candidates
                and len(top_alphas) > 0
            )

            if meets_min_pass:
                # Horizon passes minimum gate threshold
                horizon_excluded = False
            elif has_fallback_candidates:
                # Horizon allowed via fallback candidates
                horizon_excluded = False
                used_fallback_candidates = True
                logger.info(
                    f"[P10] Horizon {horizon} relaxed gate: using fallback candidates "
                    f"(gate_passed={gate_passed_count}/{self.p10_gate_min_pass}, "
                    f"top_alphas={len(top_alphas)})"
                )
            else:
                # Horizon does not meet any eligibility criteria
                horizon_excluded = True
                exclusion_reason = "relaxed_mode_insufficient_passes_no_fallback"

        # Log comprehensive gate diagnostics
        logger.info(
            f"[P10] Horizon {horizon} gate diagnostics: "
            f"mode={self.p10_gate_mode}, "
            f"passed={gate_passed_count}/{len(gate_results)}, "
            f"required={self.p10_gate_min_pass}, "
            f"fallback_enabled={self.p10_gate_allow_fallback_candidates}, "
            f"used_fallback={used_fallback_candidates}, "
            f"excluded={horizon_excluded}"
        )

        if horizon_excluded:
            logger.warning(
                f"[P10] Research gate excluded horizon {horizon}: "
                f"reason={exclusion_reason}, "
                f"gate_passed={gate_passed_count}/{len(gate_results)}"
            )
            # Build gate_metadata for excluded horizon
            gate_passed_alphas = [
                alpha for alpha, res in gate_results.items()
                if _is_gate_verdict_pass(res.get('verdict'))
            ]
            excluded_gate_metadata = {
                'selection_source': 'excluded',
                'exclusion_reason': exclusion_reason,
                'used_fallback_candidates': False,
                'gate_passed_count': gate_passed_count,
                'gate_total': len(gate_results),
                'gate_required_passes': self.p10_gate_min_pass,
                'gate_mode': self.p10_gate_mode,
                'gate_passed_alphas': gate_passed_alphas,
            }
            return None, quality_metrics, [], gate_results, excluded_gate_metadata

        if len(gated_alphas) == 0:
            logger.warning(f"[P10] No alphas passed gate for horizon {horizon}")
            # Build gate_metadata for no-alphas case
            no_alphas_gate_metadata = {
                'selection_source': 'excluded',
                'exclusion_reason': 'no_alphas_passed_gate',
                'used_fallback_candidates': False,
                'gate_passed_count': gate_passed_count,
                'gate_total': len(gate_results),
                'gate_required_passes': self.p10_gate_min_pass,
                'gate_mode': self.p10_gate_mode,
                'gate_passed_alphas': [],
            }
            return None, quality_metrics, [], gate_results, no_alphas_gate_metadata

        # Compute raw portfolio signal (IC-weighted, no XGBoost for multi-horizon)
        # XGBoost is disabled in multi-horizon mode to keep implementation simple
        portfolio_signal = self.compute_portfolio_signal(test_df, gated_alphas, train_ics)

        # Z-score normalize signal (cross-sectional per date)
        test_df_copy = test_df.copy()
        test_df_copy['_signal'] = portfolio_signal
        test_df_copy['_signal'] = test_df_copy.groupby('date')['_signal'].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-9)
        )
        portfolio_signal = test_df_copy['_signal']

        # FIX 1 & 5: Compute comprehensive quality metrics
        # Own-target train IC
        train_signal = self.compute_portfolio_signal(train_actual, gated_alphas, train_ics)
        own_target_train_ic = (
            self.compute_ic(train_signal, train_actual[return_col])
            if return_col in train_actual.columns
            else 0.0
        )

        # Own-target validation IC
        val_signal = self.compute_portfolio_signal(val_actual, gated_alphas, train_ics)
        own_target_validation_ic = (
            self.compute_ic(val_signal, val_actual[return_col])
            if return_col in val_actual.columns
            else 0.0
        )

        # Final objective train IC (contribution to final monetization target on train set)
        final_objective_train_ic = 0.0
        if final_objective_return_col in train_actual.columns:
            final_objective_train_ic = self.compute_ic(train_signal, train_actual[final_objective_return_col])

        # Final objective validation IC (contribution to final monetization target)
        final_objective_validation_ic = 0.0
        if final_objective_return_col in val_actual.columns:
            final_objective_validation_ic = self.compute_ic(val_signal, val_actual[final_objective_return_col])

        # Populate quality metrics dict
        # FIX P10 Role21 Re-Audit: train_ic and validation_ic must align to final objective return_col
        quality_metrics = {
            'train_ic': final_objective_train_ic,  # Use final-objective IC for weighting
            'validation_ic': final_objective_validation_ic,  # Use final-objective IC for weighting
            'final_objective_train_ic': final_objective_train_ic,
            'final_objective_validation_ic': final_objective_validation_ic,
            'own_target_train_ic': own_target_train_ic,
            'own_target_validation_ic': own_target_validation_ic,
        }

        # P10 Gate Tuning Role21 Fix: Build structured gate metadata
        # Extract alphas that actually passed the gate (not fallback candidates)
        gate_passed_alphas = [
            alpha for alpha, res in gate_results.items()
            if _is_gate_verdict_pass(res.get('verdict'))
        ]

        # Determine selection source
        selection_source = "fallback_candidate" if used_fallback_candidates else "research_gate"

        gate_metadata = {
            'selection_source': selection_source,
            'used_fallback_candidates': used_fallback_candidates,
            'gate_passed_count': gate_passed_count,
            'gate_total': len(gate_results),
            'gate_required_passes': self.p10_gate_min_pass,
            'gate_mode': self.p10_gate_mode,
            'gate_passed_alphas': gate_passed_alphas,
        }

        logger.info(
            f"[P10] Horizon {horizon} complete: "
            f"gated_alphas={len(gated_alphas)}, "
            f"own_val_ic={own_target_validation_ic:.4f}, "
            f"final_obj_val_ic={final_objective_validation_ic:.4f}, "
            f"gate_passed={gate_passed_count}/{len(gate_results)}, "
            f"selection_source={selection_source}"
        )

        return portfolio_signal, quality_metrics, gated_alphas, gate_results, gate_metadata

    def _blend_horizon_signals(
        self,
        horizon_results: Dict[int, Tuple[pd.Series, Dict[str, float]]],
        method: str = "validation_ic",
    ) -> Optional[pd.Series]:
        """Blend signals from multiple horizons using quality-based weights.

        P10: Combines horizon-specific signals into a single blended signal.

        Parameters
        ----------
        horizon_results : dict
            Mapping of horizon -> (signal, quality_metrics).
            signal is a pd.Series, quality_metrics is a dict with 'train_ic', 'validation_ic', etc.
        method : str
            Weight computation method ('validation_ic' or 'train_ic')

        Returns
        -------
        pd.Series or None
            Blended signal (same index as input signals), or None if all horizons have
            non-positive quality (triggering fallback to baseline)

        Notes
        -----
        PIT Safety: quality_metrics must be computed from train/validation only,
        never from test period. Caller is responsible for ensuring this.

        FIX 4: Negative or zero quality => weight 0 (no abs() weighting).
        If all horizons have non-positive quality, returns None to trigger fallback.
        If only one horizon succeeds, returns that signal directly.
        """
        logger.info(f"[P10] Blending {len(horizon_results)} horizon signals using method={method}")

        # Validate method parameter
        valid_methods = ['validation_ic', 'train_ic']
        if method not in valid_methods:
            logger.warning(f"[P10] Invalid blend_weight_method='{method}', defaulting to 'validation_ic'")
            method = 'validation_ic'

        # Filter out failed horizons (None signal or missing quality metrics)
        valid_horizons = {}
        for h, (sig, qual_dict) in horizon_results.items():
            if sig is None or qual_dict is None:
                continue
            if not isinstance(qual_dict, dict):
                logger.warning(f"[P10] Horizon {h} has invalid quality_metrics type, skipping")
                continue
            valid_horizons[h] = (sig, qual_dict)

        if len(valid_horizons) == 0:
            logger.error("[P10] All horizons failed, returning None to trigger fallback")
            return None

        # FIX P10 Role21 Re-Audit: Single horizon must also pass non-positive quality check
        if len(valid_horizons) == 1:
            h, (sig, qual_dict) = list(valid_horizons.items())[0]
            quality_val = qual_dict.get(method, 0.0)
            if quality_val <= 0:
                logger.warning(
                    f"[P10] Only horizon {h} succeeded but {method}={quality_val:.4f} is non-positive, "
                    "returning None to trigger fallback to baseline"
                )
                return None
            logger.info(f"[P10] Only horizon {h} succeeded, using it directly ({method}={quality_val:.4f})")
            return sig

        # FIX 1 & 4: Extract quality metrics using specified method
        # Use signed quality - negative IC => weight 0
        qualities = []
        for h, (sig, qual_dict) in valid_horizons.items():
            quality_val = qual_dict.get(method, 0.0)
            # FIX 4: Negative or zero quality => 0 weight (no abs())
            if quality_val <= 0:
                quality_val = 0.0
                logger.info(f"[P10] Horizon {h}: {method}={qual_dict.get(method, 0.0):.4f} (non-positive, weight=0)")
            qualities.append(quality_val)

        qualities = np.array(qualities)

        # FIX 4: If all qualities are non-positive, return None to trigger fallback
        if qualities.sum() <= 1e-9:
            logger.warning(
                f"[P10] All quality metrics non-positive using method={method}, "
                "returning None to trigger fallback to baseline"
            )
            return None

        # Normalize weights to sum to 1 (only positive qualities remain)
        weights = qualities / qualities.sum()

        # Blend signals
        signals = [sig for _, (sig, _) in valid_horizons.items()]
        horizons_list = list(valid_horizons.keys())

        # Align all signals to same index (use first signal's index as reference)
        ref_index = signals[0].index
        blended = pd.Series(0.0, index=ref_index)

        for i, (h, weight) in enumerate(zip(horizons_list, weights)):
            sig = signals[i].reindex(ref_index, fill_value=0.0)
            blended += weight * sig
            qual_dict = valid_horizons[h][1]
            logger.info(
                f"[P10] Horizon {h}: weight={weight:.4f}, "
                f"{method}={qual_dict.get(method, 0.0):.4f}"
            )

        logger.info(f"[P10] Blend complete: {len([w for w in weights if w > 0])} horizons combined")
        return blended
