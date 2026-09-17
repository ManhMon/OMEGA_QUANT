"""Risk sizing overlay - inverse-vol, confidence scaling, regime-conditional sizing.

Gate: HYBRID_REGIME_DETECTION_20260619

Delegates to ``apply_risk_sizing_overlay()`` from the walk-forward module
(``src/omega/quant/walk_forward/risk_sizing_overlay.py``). Wraps it in the
standard ``WeightOverlay`` interface for use in ``TradingPipelineV2``.

Integrates Latent GMM clustering on Latent AE space
(``latent_ae_00``, ``latent_ae_01``, ``latent_ae_11``) for ex-ante alpha
selection / exposure routing.

PIT Safety: All risk metrics (vol, IC, regime) computed from trailing data only.
GMM is fitted walk-forward on data strictly before current date.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd

from omega.quant.pipeline.overlays.base import WeightOverlay

logger = logging.getLogger(__name__)


class RiskSizingOverlay(WeightOverlay):
    """Wrap walk-forward risk sizing overlay for pipeline V2.

    Parameters
    ----------
    inverse_vol_sizing : bool
        Weight positions by 1/realized_vol (default True).
    inverse_vol_window : int
        Trailing window for realized vol (default 20).
    inverse_vol_floor : float
        Min weight fraction for inverse vol (default 0.3).
    confidence_scaling : bool
        Scale exposure by rolling IC strength (default True).
    confidence_window : int
        Trailing window for IC estimation (default 60).
    regime_sizing : bool
        Enable regime-conditional sizing (default True).
    regime_sizing_mode : str
        'heuristic' or 'hmm' (default 'hmm').
    regime_sizing_scale : float
        Bear regime exposure scale (default 0.5).
    regime_sizing_window : int
        Trailing window for HMM fitting (default 200).
    regime_refit_stride : int
        Refit HMM every N days (default 5).
    latent_gmm_enabled : bool
        Enable Latent GMM exposure routing on AE features (default False).
    latent_gmm_columns : list of str
        Latent AE column names (default ['latent_ae_00', 'latent_ae_01', 'latent_ae_11']).
    latent_gmm_n_components : int
        Number of GMM components (default 3).
    latent_gmm_bear_dampening : float
        Exposure multiplier for GMM Bear regime (default 0.3).
    latent_gmm_bull_boost : float
        Exposure multiplier for GMM Bull regime (default 1.1).
    latent_gmm_sideways_scale : float
        Exposure multiplier for GMM Sideways regime (default 0.8).
    latent_gmm_refit_stride : int
        Refit GMM every N days (default 5).
    latent_gmm_smooth_transition : bool
        Enable sigmoid-based smooth transition between bear and bull
        exposure scales in GMM routing (default False).
    latent_gmm_smooth_transition_temp : float
        Temperature for smooth transition sigmoid (default 0.1).
    gmm_model : LatentGMMRegime or None
        Pre-fitted GMM model for inference-only mode (bypasses walk-forward fitting).
    hmm_params : dict or None
        Pre-fitted HMM parameters for inference-only mode (forwarded to RiskSizingConfig).
    """

    def __init__(
        self,
        inverse_vol_sizing: bool = True,
        inverse_vol_window: int = 20,
        inverse_vol_floor: float = 0.3,
        confidence_scaling: bool = True,
        confidence_window: int = 60,
        regime_sizing: bool = True,
        regime_sizing_mode: str = "hmm",
        regime_sizing_scale: float = 0.5,
        regime_sizing_window: int = 200,
        regime_refit_stride: int = 5,
        latent_gmm_enabled: bool = False,
        latent_gmm_columns: Optional[list] = None,
        latent_gmm_n_components: int = 3,
        latent_gmm_bear_dampening: float = 0.3,
        latent_gmm_bull_boost: float = 1.1,
        latent_gmm_sideways_scale: float = 0.8,
        latent_gmm_refit_stride: int = 5,
        latent_gmm_smooth_transition: bool = False,
        latent_gmm_smooth_transition_temp: float = 0.1,
        gmm_model: Optional[Any] = None,
        hmm_params: Optional[dict] = None,
    ):
        self.inverse_vol_sizing = inverse_vol_sizing
        self.inverse_vol_window = inverse_vol_window
        self.inverse_vol_floor = inverse_vol_floor
        self.confidence_scaling = confidence_scaling
        self.confidence_window = confidence_window
        self.regime_sizing = regime_sizing
        self.regime_sizing_mode = regime_sizing_mode
        self.regime_sizing_scale = regime_sizing_scale
        self.regime_sizing_window = regime_sizing_window
        self.regime_refit_stride = regime_refit_stride

        # Latent GMM parameters
        self.latent_gmm_enabled = latent_gmm_enabled
        self.latent_gmm_columns = latent_gmm_columns or [
            "latent_ae_00", "latent_ae_01", "latent_ae_11"
        ]
        self.latent_gmm_n_components = latent_gmm_n_components
        self.latent_gmm_bear_dampening = latent_gmm_bear_dampening
        self.latent_gmm_bull_boost = latent_gmm_bull_boost
        self.latent_gmm_sideways_scale = latent_gmm_sideways_scale
        self.latent_gmm_refit_stride = latent_gmm_refit_stride
        self.latent_gmm_smooth_transition = latent_gmm_smooth_transition
        self.latent_gmm_smooth_transition_temp = latent_gmm_smooth_transition_temp

        # Pre-fitted models for inference-only mode (SoD: train in backtest script)
        self.gmm_model = gmm_model
        self.hmm_params = hmm_params

    def apply(
        self,
        weights: pd.DataFrame,
        panel: pd.DataFrame,
        state: Dict[str, Any],
    ) -> pd.DataFrame:
        # Apply base walk-forward risk sizing (HMM + inverse-vol + confidence)
        result = self._apply_base_risk_sizing(weights, panel, state)

        # Apply Latent GMM exposure routing if enabled
        if self.latent_gmm_enabled:
            result = self._apply_latent_gmm_routing(result, panel, state)

        return result

    def _apply_base_risk_sizing(
        self,
        weights: pd.DataFrame,
        panel: pd.DataFrame,
        state: Dict[str, Any],
    ) -> pd.DataFrame:
        """Apply existing walk-forward risk sizing (HMM + inverse-vol)."""
        try:
            from omega.quant.walk_forward.risk_sizing_overlay import (
                apply_risk_sizing_overlay,
                RiskSizingConfig,
            )
        except ImportError:
            logger.warning("RiskSizingOverlay: walk_forward module not available, returning weights unchanged.")
            return weights

        config = RiskSizingConfig(
            inverse_vol_sizing=self.inverse_vol_sizing,
            inverse_vol_window=self.inverse_vol_window,
            inverse_vol_floor=self.inverse_vol_floor,
            confidence_scaling=self.confidence_scaling,
            confidence_window=self.confidence_window,
            regime_sizing=self.regime_sizing,
            regime_sizing_mode=self.regime_sizing_mode,
            regime_sizing_scale=self.regime_sizing_scale,
            regime_sizing_window=self.regime_sizing_window,
            regime_refit_stride=self.regime_refit_stride,
        )

        if not config.enabled:
            return weights

        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel

        required_cols = ["date", "ticker", "close"]
        if "ticker" not in panel_flat.columns and "symbol" in panel_flat.columns:
            panel_flat = panel_flat.rename(columns={"symbol": "ticker"})
        if not all(c in panel_flat.columns for c in required_cols):
            logger.warning("RiskSizingOverlay: missing required columns, returning weights unchanged.")
            return weights

        test_df = panel_flat[required_cols].copy()
        test_df["date"] = pd.to_datetime(test_df["date"])

        # Build portfolio signal from weights: per-date, per-ticker gross weight
        portfolio_signal = pd.Series(0.0, index=test_df.index)
        weights_wide = weights.copy()

        for dt in weights_wide.index:
            dt_mask = test_df["date"] == dt
            if not dt_mask.any():
                continue
            day_indices = test_df.index[dt_mask]
            for idx in day_indices:
                ticker = test_df.loc[idx, "ticker"]
                if ticker in weights_wide.columns:
                    portfolio_signal.loc[idx] = weights_wide.loc[dt, ticker]

        try:
            modified_signal, evidence = apply_risk_sizing_overlay(
                test_df=test_df,
                portfolio_signal=portfolio_signal,
                config=config,
            )
        except Exception as e:
            logger.warning("RiskSizingOverlay: apply_risk_sizing_overlay failed: %s", e)
            return weights

        # Store evidence in state for downstream consumers (e.g. HMM p_bear)
        state["risk_sizing_evidence"] = evidence
        if "hmm_p_bear" in evidence:
            p_bear_data = evidence["hmm_p_bear"]
            if isinstance(p_bear_data, dict) and "dates" in p_bear_data:
                p_bear_map = dict(zip(p_bear_data["dates"], p_bear_data["values"]))
                state["hmm_p_bear"] = p_bear_map

        result = weights.copy()
        for dt in result.index:
            dt_mask = test_df["date"] == dt
            if not dt_mask.any():
                continue
            day_indices = test_df.index[dt_mask]
            for idx in day_indices:
                ticker = test_df.loc[idx, "ticker"]
                if ticker in result.columns:
                    result.loc[dt, ticker] = modified_signal.loc[idx]

        return result

    def _apply_latent_gmm_routing(
        self,
        weights: pd.DataFrame,
        panel: pd.DataFrame,
        state: Dict[str, Any],
    ) -> pd.DataFrame:
        """Apply Latent GMM exposure routing on AE features.

        PIT Safety: When ``self.gmm_model`` is provided (pre-fitted on train data),
        uses inference-only mode — no walk-forward fitting during the test loop.
        Otherwise, GMM is fitted walk-forward using only data < current date.
        """
        try:
            from omega.quant.strategy.latent_gmm import LatentGMMRegime, LatentGMMConfig
        except ImportError:
            logger.warning("RiskSizingOverlay: latent_gmm module not available, skipping GMM routing.")
            return weights

        panel_flat = panel.reset_index() if not {"date", "symbol"}.issubset(panel.columns) else panel

        # Check latent columns are available
        latent_cols = self.latent_gmm_columns
        available_cols = [c for c in latent_cols if c in panel_flat.columns]
        if len(available_cols) < 1:
            logger.debug("RiskSizingOverlay: No latent AE columns found, skipping GMM routing.")
            return weights

        gmm_config = LatentGMMConfig(
            n_components=self.latent_gmm_n_components,
            latent_columns=available_cols,
            bear_dampening=self.latent_gmm_bear_dampening,
            bull_boost=self.latent_gmm_bull_boost,
            sideways_scale=self.latent_gmm_sideways_scale,
            refit_stride=self.latent_gmm_refit_stride,
            smooth_transition=self.latent_gmm_smooth_transition,
            smooth_transition_temp=self.latent_gmm_smooth_transition_temp,
        )

        # Use pre-fitted GMM model if provided (inference-only, SoD-safe)
        inference_only = self.gmm_model is not None and self.gmm_model.is_fitted
        if inference_only:
            gmm = self.gmm_model
        else:
            gmm = LatentGMMRegime(gmm_config)

        # Ensure date column
        if "date" not in panel_flat.columns:
            return weights
        panel_flat["date"] = pd.to_datetime(panel_flat["date"])

        result = weights.copy()
        dates = sorted(result.index)
        step_counter = 0
        gmm_evidence: Dict[str, Any] = {
            "regime_labels": [],
            "regime_scales": [],
            "dates": [],
            "inference_only": inference_only,
        }

        for dt in dates:
            step_counter += 1

            # In inference-only mode, skip refitting entirely.
            # Otherwise, refit GMM periodically (PIT-safe: only data < dt).
            if not inference_only:
                should_refit = (
                    not gmm.is_fitted
                    or step_counter % max(1, gmm_config.refit_stride) == 0
                )
                if should_refit:
                    gmm.walk_forward_fit(panel_flat, pd.Timestamp(dt))

            if not gmm.is_fitted:
                continue

            # Extract latent features for current date
            dt_mask = panel_flat["date"] == pd.Timestamp(dt)
            if not dt_mask.any():
                continue

            day_data = panel_flat.loc[dt_mask]
            day_latent = day_data[available_cols].fillna(0.0)

            # Predict regime and get probabilities
            labels, probabilities = gmm.predict_regime(day_latent)
            scales = gmm.get_exposure_scale(probabilities)

            # Average scale across symbols for this date
            avg_scale = float(np.mean(scales))
            avg_scale = np.clip(avg_scale, 0.1, 2.0)

            # Apply exposure scale to all tickers on this date
            result.loc[dt] = result.loc[dt] * avg_scale

            # Track evidence
            dominant_regime = labels[0] if len(labels) > 0 else "Unknown"
            gmm_evidence["regime_labels"].append(dominant_regime)
            gmm_evidence["regime_scales"].append(avg_scale)
            gmm_evidence["dates"].append(str(dt)[:10])

        # Store GMM evidence in state
        state["latent_gmm_evidence"] = gmm_evidence

        # Giai phap B: expose per-date GMM bull probability for re-entry filter
        # Build a date→p_bull map from the per-date probabilities
        gmm_p_bull_map: Dict[str, float] = {}
        gmm_p_bear_map: Dict[str, float] = {}
        for dt_key, dt in zip(gmm_evidence["dates"], dates):
            dt_mask = panel_flat["date"] == pd.Timestamp(dt)
            if not dt_mask.any():
                continue
            day_data = panel_flat.loc[dt_mask]
            day_latent = day_data[available_cols].fillna(0.0)
            _, probabilities = gmm.predict_regime(day_latent)
            # Extract per-regime probabilities (avg across symbols)
            regime_prob_map = gmm.get_regime_probability_map(probabilities)
            avg_p_bull = float(np.mean(regime_prob_map.get("Bull", np.array([0.0]))))
            avg_p_bear = float(np.mean(regime_prob_map.get("Bear", np.array([0.0]))))
            gmm_p_bull_map[dt_key] = avg_p_bull
            gmm_p_bear_map[dt_key] = avg_p_bear
        state["gmm_p_bull"] = gmm_p_bull_map
        state["gmm_p_bear"] = gmm_p_bear_map

        logger.info(
            "RiskSizingOverlay: Latent GMM routing applied across %d dates (inference_only=%s).",
            len(gmm_evidence["dates"]),
            inference_only,
        )

        return result
