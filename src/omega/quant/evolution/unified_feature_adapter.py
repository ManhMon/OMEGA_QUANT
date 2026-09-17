"""
OMEGA_QUANT Unified Feature Adapter
Merges 3 feature systems into 1 unified interface:
1. FeatureModule (10 basic features)
2. AlternativeFeatureGenerator (25 derived features)
3. ultimate_alpha_arsenal (130 institutional alphas)

Provides single entry point for backtest/screening pipeline.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - All underlying systems enforce T-1 lag.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class UnifiedFeatureAdapter:
    """
    Single entry point for all feature generation.
    Combines FeatureModule + AlternativeFeatureGenerator + ultimate_alpha_arsenal.
    """

    def __init__(
        self,
        use_arsenal: bool = True,
        use_alt_features: bool = True,
        use_alt_data: bool = True,
        use_llm_synth: bool = False,
        llm_provider: Optional[str] = None,
    ):
        self.use_arsenal = use_arsenal
        self.use_alt_features = use_alt_features
        self.use_alt_data = use_alt_data
        self.use_llm_synth = use_llm_synth
        self.llm_provider = llm_provider
        self._arsenal_features: List[str] = []
        self._alt_features: List[str] = []
        self._alt_data_features: List[str] = []
        self._llm_features: List[str] = []

    def generate_all(self, panel: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all features from all 3 systems.

        Args:
            panel: MultiIndex [date, symbol] DataFrame with open/high/low/close/volume

        Returns:
            Panel with all features added.
        """
        result = panel.copy()
        total_before = len(result.columns)

        # 1. Alternative Features (25 derived from OHLCV)
        if self.use_alt_features:
            try:
                from omega.quant.evolution.alternative_features import (
                    AlternativeFeatureGenerator,
                )
                feat_gen = AlternativeFeatureGenerator()
                result = feat_gen.generate_all(result)
                self._alt_features = feat_gen.get_feature_names()
                logger.info("Alt features: +%d", len(self._alt_features))
            except Exception as e:
                logger.warning("AlternativeFeatureGenerator failed: %s", e)

        # 2. Alternative Data (8 proxy signals)
        if self.use_alt_data:
            try:
                from omega.quant.evolution.alternative_data_fetcher import (
                    AlternativeDataFetcher,
                )
                fetcher = AlternativeDataFetcher()
                result = fetcher.generate_all(result)
                self._alt_data_features = fetcher.get_feature_names()
                logger.info("Alt data: +%d", len(self._alt_data_features))
            except Exception as e:
                logger.warning("AlternativeDataFetcher failed: %s", e)

        flat = result.reset_index()
        flat.columns = ['date', 'ticker'] + list(flat.columns[2:])
        required = ['date', 'ticker', 'open', 'high', 'low', 'close', 'volume']

        # 3. Ultimate Alpha Arsenal (130 institutional alphas)
        if self.use_arsenal:
            try:
                from omega.quant.alpha.arsenal import compute_ultimate_alphas
                # Arsenal expects flat DataFrame with ticker/date columns
                # Ensure required columns
                if all(c in flat.columns for c in required):
                    arsenal_df = compute_ultimate_alphas(
                        flat[required], symbol_col='ticker')
                    # Get alpha columns (prefixed with alpha_)
                    alpha_cols = [
                        c for c in arsenal_df.columns if c.startswith('alpha_')]
                    if alpha_cols:
                        # Merge back to MultiIndex
                        arsenal_df = arsenal_df.set_index(
                            ['date', 'ticker'])[alpha_cols]
                        arsenal_df.index.names = ['date', 'symbol']
                        # Join to result
                        result = result.join(arsenal_df, how='left')
                        self._arsenal_features = alpha_cols
                        logger.info("Arsenal alphas: +%d", len(alpha_cols))
                else:
                    logger.warning("Arsenal skipped: missing required columns")
            except Exception as e:
                logger.warning("ultimate_alpha_arsenal failed: %s", e)

        # 4. Microstructure alphas (P2 wire)
        try:
            from omega.quant.strategy.market_microstructure import (
                compute_microstructure_alphas,
            )
            if all(c in flat.columns for c in required):
                micro_df = compute_microstructure_alphas(
                    flat[required], symbol_col='ticker')
                micro_cols = [c for c in micro_df.columns if c.startswith(
                    'micro_') or c.startswith('alpha_micro')]
                if not micro_cols:
                    micro_cols = [c for c in micro_df.columns if c not in required]
                if micro_cols:
                    micro_df = micro_df.set_index(['date', 'ticker'])[micro_cols]
                    micro_df.index.names = ['date', 'symbol']
                    # Only add columns not already present
                    new_cols = [c for c in micro_cols if c not in result.columns]
                    if new_cols:
                        result = result.join(micro_df[new_cols], how='left')
                        self._arsenal_features.extend(new_cols)
                        logger.info("Microstructure alphas: +%d", len(new_cols))
        except Exception as e:
            logger.debug("Microstructure alphas skipped: %s", e)

        # 5. Macro alphas (P2 wire)
        try:
            from omega.quant.alpha.macro import compute_macro_alphas
            if all(c in flat.columns for c in required):
                macro_df = compute_macro_alphas(flat[required], symbol_col='ticker')
                macro_cols = [c for c in macro_df.columns if c.startswith(
                    'macro_') or c.startswith('alpha_macro')]
                if not macro_cols:
                    macro_cols = [c for c in macro_df.columns if c not in required]
                if macro_cols:
                    macro_df = macro_df.set_index(['date', 'ticker'])[macro_cols]
                    macro_df.index.names = ['date', 'symbol']
                    new_cols = [c for c in macro_cols if c not in result.columns]
                    if new_cols:
                        result = result.join(macro_df[new_cols], how='left')
                        self._arsenal_features.extend(new_cols)
                        logger.info("Macro alphas: +%d", len(new_cols))
        except Exception as e:
            logger.debug("Macro alphas skipped: %s", e)

        # 6. LLM-in-the-Loop Symbolic Synthesis with Quality Filtering
        if self.use_llm_synth:
            try:
                from omega.quant.evolution.genetic_programming import GPIndividual
                from omega.quant.evolution.llm_symbolic_synthesizer import (
                    LLMSymbolicSynthesizer,
                )
                from omega.quant.evolution.llm_formula_scorer import (
                    FormulaScorerConfig,
                )

                # Provider defaults to 'mock' for safety (can be overridden via env)
                synthesizer = LLMSymbolicSynthesizer(
                    provider=self.llm_provider or 'mock'
                )
                
                # Numeric feature columns only (exclude index-level labels).
                feat_cols = [
                    col for col in result.columns
                    if col not in ("date", "symbol")
                    and pd.api.types.is_numeric_dtype(result[col])
                ]
                
                # Pass flat dict to synthesizer for formula/node generation only.
                flat_feat_dict = {col: result[col].to_numpy() for col in feat_cols}
                candidate_nodes = synthesizer.synthesize(flat_feat_dict)
                
                # NEW: Score and filter formulas using unsupervised quality checks.
                # At this stage we have OHLCV data but no forward returns (labels),
                # so we use unsupervised-only scoring with allow_unvalidated=True.
                # This filters out broken formulas (excessive NaN, zero variance,
                # unstable per-ticker output) while preserving formulas that pass
                # basic quality checks.
                scorer_config = FormulaScorerConfig(
                    min_coverage=0.70,  # Require 70% non-NaN coverage
                    min_variance=1e-8,  # Reject near-constant formulas
                    max_per_ticker_variance=1e6,  # Reject unstable formulas
                    max_nan_inf_ratio=0.30,  # Allow up to 30% NaN/inf (lenient for warmup)
                    allow_unvalidated=True,  # Accept formulas without supervised checks
                )
                
                # Build temporary panel DataFrame for scoring
                # Need to reset index to flat DataFrame with ticker/date columns
                temp_panel = result.reset_index()
                if temp_panel.index.names == ['date', 'symbol']:
                    # MultiIndex: date, symbol
                    temp_panel.columns = ['date', 'symbol'] + list(temp_panel.columns[2:])
                    ticker_col = 'symbol'
                else:
                    # Already flat, ensure we have ticker/date columns
                    ticker_col = 'symbol' if 'symbol' in temp_panel.columns else 'ticker'
                
                # Score and filter formulas (no labels = unsupervised only)
                accepted_nodes, scoring_stats = synthesizer.score_and_filter_formulas(
                    nodes=candidate_nodes,
                    panel=temp_panel,
                    feat_cols=feat_cols,
                    labels=None,  # No labels at feature generation stage
                    scorer_config=scorer_config,
                    ticker_col=ticker_col,
                    date_col='date',
                )
                
                # Execute and add only accepted formulas
                for i, node in enumerate(accepted_nodes):
                    col_name = f"alpha_llm_{i}"
                    # P2 fix (L3 audit): execute tree per-ticker so that
                    # time-series operators (ts_mean, decay_linear, ts_rank,
                    # ts_std) roll within each ticker's sorted date sequence,
                    # not across cross-ticker flattened arrays.
                    series_parts: list = []
                    for _ticker, grp in result.groupby(level="symbol"):
                        grp_sorted = grp.sort_index(level="date")
                        feat_dict_tk = {
                            col: grp_sorted[col].to_numpy()
                            for col in feat_cols
                        }
                        ind = GPIndividual(tree=node)
                        tv = ind._execute_tree(node, feat_dict_tk)
                        series_parts.append(
                            pd.Series(tv, index=grp_sorted.index, name=col_name)
                        )
                    result[col_name] = (
                        pd.concat(series_parts).reindex(result.index)
                    )
                    self._llm_features.append(col_name)
                
                logger.info(
                    "LLM Synthesized alphas: %d candidates, %d accepted (%d deployable, %d unsupervised_only), %d rejected",
                    scoring_stats['total'],
                    scoring_stats['accepted'],
                    scoring_stats.get('deployable', 0),
                    scoring_stats.get('unsupervised_only', 0),
                    scoring_stats['rejected'],
                )
                
                # L3 audit requirement: explicit warning for unsupervised-only formulas
                if scoring_stats.get('unsupervised_only', 0) > 0:
                    logger.warning(
                        "LLM formulas accepted with UNSUPERVISED checks only - "
                        "NOT PRODUCTION-DEPLOYABLE. These formulas passed basic quality "
                        "checks (coverage, variance, stability) but have NOT been validated "
                        "against forward returns. Use for research/exploration only, not live trading."
                    )
                
                if scoring_stats['rejected'] > 0:
                    logger.info(
                        "Rejected formulas: %s",
                        ", ".join(scoring_stats.get('rejected_names', []))
                    )
            except Exception as e:
                logger.warning("LLM Symbolic Synthesizer failed: %s", e)

        total_after = len(result.columns)
        logger.info("UnifiedFeatureAdapter: %d -> %d columns (+%d features)",
                    total_before, total_after, total_after - total_before)
        return result

    def get_all_feature_names(self) -> List[str]:
        """Return all generated feature names across all systems."""
        return (
            self._alt_features
            + self._alt_data_features
            + self._arsenal_features
            + self._llm_features
        )

    def get_feature_groups(self) -> dict:
        """Return features grouped by source system."""
        return {
            "alt_features": self._alt_features,
            "alt_data": self._alt_data_features,
            "arsenal": self._arsenal_features,
            "llm_synth": self._llm_features,
        }
