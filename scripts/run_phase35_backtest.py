"""Run Phase 3.5 Walk-Forward Backtest on Real Data.

This script runs the complete walk-forward backtest and saves results.
"""
import logging
import sys
from pathlib import Path
import json
import argparse
from datetime import datetime

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

# Repo root for relative path resolution
REPO_ROOT = Path(__file__).resolve().parent.parent

from phase35_data_loader import Phase35DataLoader
from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
from omega.quant import phase34_microstructure_alphas

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def serialize_fold_details(m):
    """
    Serialize a FoldMetrics object to a JSON-compatible dict.
    
    Includes gate_metadata and convenience aliases if present.
    
    Parameters
    ----------
    m : FoldMetrics
        The fold metrics object to serialize
        
    Returns
    -------
    dict
        JSON-serializable fold details with gate metadata if available
    """
    fold_dict = {
        "fold_id": m.fold_id,
        "train_start": m.train_start,
        "train_end": m.train_end,
        "test_start": m.test_start,
        "test_end": m.test_end,
        "portfolio_ic": m.portfolio_ic,
        "portfolio_sharpe": m.portfolio_sharpe,
        "portfolio_max_dd": m.portfolio_max_dd,
        "portfolio_total_return": m.portfolio_total_return,
        "portfolio_pnl_vnd": getattr(m, "portfolio_pnl_vnd", 0.0),
        "alpha_ics": m.alpha_ics,
        "n_train_samples": m.n_train_samples,
        "n_test_samples": m.n_test_samples,
    }
    
    # Add gate_metadata if present
    gate_meta = getattr(m, "gate_metadata", None)
    if gate_meta is not None:
        # Store the full gate_metadata dict
        fold_dict["gate_metadata"] = gate_meta
        
        # Add convenience aliases for easier access
        fold_dict["selection_source"] = gate_meta.get("selection_source")
        fold_dict["used_fallback_candidates"] = gate_meta.get("used_fallback_candidates")
        fold_dict["gate_passed_count"] = gate_meta.get("gate_passed_count")
        fold_dict["gate_total"] = gate_meta.get("gate_total")
        fold_dict["gate_required_passes"] = gate_meta.get("gate_required_passes")
        fold_dict["gate_mode"] = gate_meta.get("gate_mode")
        fold_dict["gate_passed_alphas"] = gate_meta.get("gate_passed_alphas")
    
    # GATE: RISK_ADJUSTED_ALPHA_SELECTION_FIX1_20260614 — persist per-fold evidence
    ra_evidence = getattr(m, "risk_adjusted_evidence", None)
    if ra_evidence is not None:
        fold_dict["risk_adjusted_alpha_selection"] = ra_evidence
    
    # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_FIX1_20260614 — persist per-fold guard evidence
    pg_evidence = getattr(m, "portfolio_guard_evidence", None)
    if pg_evidence is not None:
        fold_dict["portfolio_guard_evidence"] = pg_evidence
    
    # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614 — persist per-fold winner guard evidence
    wg_evidence = getattr(m, "winner_guard_evidence", None)
    if wg_evidence is not None:
        fold_dict["winner_guard_evidence"] = wg_evidence
    
    # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — persist per-fold regime routing evidence
    rr_evidence = getattr(m, "regime_routing_evidence", None)
    if rr_evidence is not None:
        fold_dict["regime_routing_evidence"] = rr_evidence
    
    # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615 — persist per-fold dynamic universe evidence
    du_evidence = getattr(m, "dynamic_universe_evidence", None)
    if du_evidence is not None:
        fold_dict["dynamic_universe_evidence"] = du_evidence
    
    # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — persist per-fold basket evidence
    db_evidence = getattr(m, "diversified_basket_evidence", None)
    if db_evidence is not None:
        fold_dict["diversified_basket_evidence"] = db_evidence
    
    # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615 — persist per-fold nonredundant alpha evidence
    nr_evidence = getattr(m, "nonredundant_alpha_evidence", None)
    if nr_evidence is not None:
        fold_dict["nonredundant_alpha_evidence"] = nr_evidence
    
    # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615 — persist per-fold automated discovery evidence
    auto_evidence = getattr(m, "automated_discovery_evidence", None)
    if auto_evidence is not None:
        fold_dict["automated_discovery_evidence"] = auto_evidence
    
    # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616 — persist per-fold stability filter evidence
    sf_evidence = getattr(m, "oos_stability_filter_evidence", None)
    if sf_evidence is not None:
        fold_dict["oos_stability_filter_evidence"] = sf_evidence

    # GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616 — persist per-fold risk/sizing overlay evidence
    rs_evidence = getattr(m, "risk_sizing_evidence", None)
    if rs_evidence is not None:
        fold_dict["risk_sizing_evidence"] = rs_evidence

    # GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616 — persist per-fold drawdown re-entry evidence
    dd_re_evidence = getattr(m, "drawdown_re_entry_evidence", None)
    if dd_re_evidence is not None:
        fold_dict["drawdown_re_entry_evidence"] = dd_re_evidence

    # GATE: LATENT_ALPHA_MINING_64D_20260617 — persist per-fold latent alpha evidence
    la_evidence = getattr(m, "latent_alpha_evidence", None)
    if la_evidence is not None:
        fold_dict["latent_alpha_evidence"] = la_evidence

    return fold_dict


def main():
    """Run walk-forward backtest."""
    parser = argparse.ArgumentParser(description="Run Phase 3.5 walk-forward backtest")
    # GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615
    # XGBoost is now opt-in research mode. Default is use_xgboost=False.
    # Evidence: E2E A/B showed XGBoost degrades signal
    #   XGB ON  — PortfolioIC 0.0157, RawIC 0.0049, CSIC 0.0000
    #   XGB OFF — PortfolioIC 0.0344, RawIC 0.0200, CSIC 0.0216
    parser.add_argument(
        "--enable-xgboost",
        action="store_true",
        help=(
            "GATE DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615: "
            "Opt-in to XGBoost research signal path. "
            "XGBoost is DISABLED by default because E2E A/B evidence showed "
            "it degrades signal quality (PortfolioIC 0.0157 vs 0.0344 baseline). "
            "Use this flag only for research experimentation."
        ),
    )
    parser.add_argument(
        "--no-xgboost",
        action="store_true",
        help=(
            "DEPRECATED (no-op). XGBoost is now disabled by default per "
            "GATE DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615. "
            "This flag is preserved for backward compatibility and has no effect."
        ),
    )
    parser.add_argument(
        "--enable-multi-model-ensemble",
        action="store_true",
        help=(
            "GATE MULTI_MODEL_ML_ENSEMBLE_20260616: Opt-in PIT-safe ensemble "
            "using XGBoost, LightGBM, RandomForest, and Ridge. Disabled by default."
        ),
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2015-01-05",
        help="Start date for data loading",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2026-05-14",
        help="End date for data loading",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=1_000_000_000.0,
        help="Initial capital in VND",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="multi_factor",
        help="Trading strategy",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=10.0,
        help="Slippage in basis points",
    )
    parser.add_argument(
        "--commission-bps",
        type=float,
        default=20.0,
        help="Commission in basis points",
    )
    parser.add_argument(
        "--quick-mode",
        action="store_true",
        help="Run quickly with 1 symbol, 2 folds, 1 train year, 1 test year",
    )
    # GATE: CPCV_FOLD_EXPANSION_20260614 — opt-in fold expansion CLI args
    parser.add_argument(
        "--n-folds",
        type=int,
        default=None,
        help="CPCV_FOLD_EXPANSION_20260614: Number of walk-forward folds (default: 8, quick-mode: 2)",
    )
    parser.add_argument(
        "--train-years",
        type=int,
        default=None,
        help="CPCV_FOLD_EXPANSION_20260614: Training window in years (default: 3, quick-mode: 1)",
    )
    parser.add_argument(
        "--test-years",
        type=int,
        default=None,
        help="CPCV_FOLD_EXPANSION_20260614: Test window in years (default: 1, quick-mode: 1)",
    )
    parser.add_argument(
        "--top-n-symbols",
        type=int,
        default=None,
        help="CPCV_FOLD_EXPANSION_20260614: Number of top symbols to use (default: 30, quick-mode: 1)",
    )
    parser.add_argument(
        "--output-tag",
        type=str,
        default=None,
        help="CPCV_FOLD_EXPANSION_20260614: Tag appended to output filenames to avoid overwrite (e.g. cpcv_smoke)",
    )
    # GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615
    # Drawdown control is now DEFAULT-ON (research default).
    # Evidence: E2E risk-layer diagnostic showed MaxDD improved without reducing IC:
    #   no-XGB baseline: PortfolioIC 0.0344, RawIC 0.0200, CSIC 0.0216, Sharpe 2.3273, MaxDD -66.99%
    #   DD10 control:    PortfolioIC 0.0344, RawIC 0.0200, CSIC 0.0216, Sharpe 3.1570, MaxDD -12.34%
    # IC preserved, Sharpe improved 2.33→3.16, MaxDD improved -67%→-12%.
    parser.add_argument(
        "--drawdown-control",
        action="store_true",
        help=(
            "DEPRECATED (no-op). Drawdown control is now ENABLED by default per "
            "GATE DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615. "
            "This flag is preserved for backward compatibility as an explicit "
            "enable and has no effect. Use --disable-drawdown-control to opt out."
        ),
    )
    parser.add_argument(
        "--disable-drawdown-control",
        action="store_true",
        help=(
            "GATE DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615: Opt-out flag. "
            "Disables active drawdown control stop-out. "
            "Drawdown control is ENABLED by default because E2E risk-layer evidence "
            "showed MaxDD improved from -66.99%% to -12.34%% without reducing IC "
            "(PortfolioIC 0.0344 preserved, Sharpe 2.33 to 3.16). "
            "Use this flag only to reproduce uncontrolled baselines."
        ),
    )
    parser.add_argument(
        "--drawdown-threshold",
        type=float,
        default=0.10,
        help=(
            "GATE DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615: "
            "Drawdown threshold (e.g. 0.10 for 10 pct). Default changed from 0.05 "
            "to 0.10 based on E2E risk-layer diagnostic evidence."
        ),
    )
    # GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616 — drawdown re-entry CLI
    parser.add_argument(
        "--drawdown-re-entry",
        action="store_true",
        help=(
            "GATE STAGE6_3_DRAWDOWN_RE_ENTRY_20260616: Enable stateful "
            "drawdown re-entry after stop-out.  After cooldown_days in cash, "
            "the strategy re-enters with optional HWM reset.  Default disabled "
            "(permanent stop-out on breach).  Research-only, opt-in."
        ),
    )
    parser.add_argument(
        "--drawdown-cooldown-days",
        type=int,
        default=5,
        help=(
            "GATE STAGE6_3_DRAWDOWN_RE_ENTRY_20260616: Number of trading "
            "days to stay in cash after a drawdown stop-out before "
            "re-entering the strategy.  Default 5.  Ignored when "
            "--drawdown-re-entry is not set."
        ),
    )
    parser.add_argument(
        "--drawdown-no-hwm-reset",
        action="store_true",
        help=(
            "GATE STAGE6_3_DRAWDOWN_RE_ENTRY_20260616: Disable HWM reset "
            "on re-entry.  By default, HWM is reset to current NAV after "
            "re-entry (prevents repeated stop-outs from the same HWM).  "
            "Use this flag to keep the original HWM (stricter control)."
        ),
    )
    # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616 — adaptive re-entry CLI
    parser.add_argument(
        "--drawdown-adaptive-re-entry",
        action="store_true",
        help=(
            "GATE STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616: Enable "
            "adaptive drawdown re-entry using HMM bear probability and "
            "trailing volatility.  Cooldown is extended when p_bear is "
            "high or volatility is elevated, and shortened when regime "
            "conditions improve.  Requires --drawdown-re-entry and "
            "--risk-sizing-overlay with HMM mode for full effect.  "
            "Research-only, opt-in, default disabled."
        ),
    )
    parser.add_argument(
        "--drawdown-adaptive-bear-threshold",
        type=float,
        default=0.5,
        help=(
            "GATE STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616: HMM bear "
            "probability threshold for adaptive cooldown.  When p_bear >= "
            "threshold, cooldown is extended.  Default 0.5."
        ),
    )
    parser.add_argument(
        "--drawdown-adaptive-vol-window",
        type=int,
        default=20,
        help=(
            "GATE STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616: Trailing "
            "window (days) for realized volatility in adaptive cooldown.  "
            "Default 20."
        ),
    )
    parser.add_argument(
        "--drawdown-adaptive-vol-multiplier",
        type=float,
        default=1.5,
        help=(
            "GATE STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616: Volatility "
            "ratio threshold for extending cooldown.  When current vol / "
            "baseline vol >= multiplier, cooldown is extended.  Default 1.5."
        ),
    )
    parser.add_argument(
        "--drawdown-adaptive-max-cooldown",
        type=int,
        default=20,
        help=(
            "GATE STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616: Maximum "
            "adaptive cooldown days cap.  Prevents infinite cooldown "
            "extension.  Default 20."
        ),
    )
    parser.add_argument(
        "--enable-evolved",
        action="store_true",
        help="Enable inline GP evolution per fold and blend evolved signal with hand-crafted alphas",
    )
    parser.add_argument(
        "--evolved-blend-weight",
        type=float,
        default=0.5,
        help="Weight of evolved signal in blend (0-1), remainder is hand-crafted (default: 0.5)",
    )
    parser.add_argument(
        "--multi-horizon-blend",
        action="store_true",
        help="P10: Enable multi-horizon signal blending (T+1, T+3, T+5)",
    )
    parser.add_argument(
        "--blend-horizons",
        type=str,
        default="1,3,5",
        help="P10: Comma-separated list of horizons to blend (default: 1,3,5)",
    )
    parser.add_argument(
        "--blend-weight-method",
        type=str,
        default="validation_ic",
        help="P10: Method for computing blend weights (validation_ic or train_ic, default: validation_ic)",
    )
    parser.add_argument(
        "--p10-gate-mode",
        type=str,
        choices=["strict", "relaxed"],
        default="strict",
        help="P10 Gate Tuning: gate policy mode (strict or relaxed, default: strict)",
    )
    parser.add_argument(
        "--p10-gate-min-pass",
        type=int,
        default=1,
        help="P10 Gate Tuning: minimum gate passes required for horizon eligibility in relaxed mode (default: 1)",
    )
    parser.add_argument(
        "--p10-gate-allow-fallback-candidates",
        action="store_true",
        help="P10 Gate Tuning: allow horizons with non-empty top_alphas to proceed even if gate passes < min_pass (relaxed mode only)",
    )
    parser.add_argument(
        "--enable-data-cleaning",
        action="store_true",
        help=(
            "P11 (DEPRECATED, kept for backward compat): DataSanitizer cleaning "
            "is now DEFAULT-ON per GATE DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614. "
            "This flag has no effect. Use --disable-data-cleaning to opt out."
        ),
    )
    parser.add_argument(
        "--disable-data-cleaning",
        action="store_true",
        help=(
            "GATE DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614: Opt-out flag. "
            "Disables DataSanitizer cleaning (default is ON). "
            "Backward-compatible: old scripts without this flag get cleaning."
        ),
    )
    parser.add_argument(
        "--normalization-mode",
        type=str,
        choices=["expanding_zscore", "cross_sectional_zscore", "rank", "none"],
        default="expanding_zscore",
        help=(
            "GATE DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614: Normalization "
            "mode applied to OHLCV columns. Raw OHLCV always preserved. "
            "'expanding_zscore' (default): per-symbol causal expanding-window "
            "z-score. 'cross_sectional_zscore': per-date cross-sectional z-score. "
            "'rank': per-date cross-sectional rank [-1,1]. "
            "'none': no normalization. All modes are PIT-safe (no look-ahead)."
        ),
    )
    parser.add_argument(
        "--risk-adjusted-alpha-selection",
        action="store_true",
        help="GATE RISK_ADJUSTED_ALPHA_SELECTION_20260614: Use composite risk-adjusted scoring for alpha selection (opt-in, default disabled). Uses only train/val embargoed data, paper-trading-only boundary.",
    )
    parser.add_argument(
        "--risk-adjusted-preset",
        type=str,
        choices=["balanced", "alpha_recovery", "drawdown_guarded", "ic_first_guarded"],
        default="balanced",
        help=(
            "GATE RISK_ADJUSTED_ALPHA_TUNING_20260614: Weight preset for "
            "risk-adjusted composite scoring.  Choices: balanced (default, "
            "backward-compatible), alpha_recovery (emphasises IC/Sharpe "
            "recovery), drawdown_guarded (emphasises drawdown/turnover "
            "protection), ic_first_guarded (IC-first guarded tuning: "
            "prioritises validation IC and IC stability with risk penalties "
            "as soft tie-breakers).  Ignored when "
            "--risk-adjusted-alpha-selection is not set."
        ),
    )
    parser.add_argument(
        "--disable-risk-adjusted-portfolio-guard",
        action="store_true",
        help=(
            "GATE RISK_ADJUSTED_PORTFOLIO_GUARD_FIX1_20260614: Explicitly "
            "disable portfolio guard even when --risk-adjusted-alpha-selection "
            "is set. By default, the guard is auto-enabled whenever "
            "--risk-adjusted-alpha-selection is active."
        ),
    )
    parser.add_argument(
        "--risk-adjusted-portfolio-guard-tolerance",
        type=float,
        default=0.005,
        help=(
            "GATE RISK_ADJUSTED_PORTFOLIO_GUARD_FIX1_20260614: Maximum "
            "allowed IC underperformance vs baseline (absolute) before "
            "guard triggers fallback. Default 0.005. Ignored when guard "
            "is disabled."
        ),
    )
    # GATE: RECOVERY_SELECTOR_PHASE35_WIRING_20260614 — opt-in research pool mode
    parser.add_argument(
        "--research-pool-mode",
        type=str,
        choices=["full", "recovery_only", "recoverable_only"],
        default="full",
        help=(
            "GATE RECOVERY_SELECTOR_PHASE35_WIRING_20260614: Research-only "
            "recovery pool selector mode. 'full' (default) uses all alphas "
            "unchanged. 'recovery_only' excludes CONFIRMED_RETIRE alphas. "
            "'recoverable_only' keeps only RECOVERABLE alphas. Default 'full' "
            "preserves backward compatibility — no live/default behavior change. "
            "Recovery diagnostics computed post-hoc from OOS fold ICs (PIT-safe)."
        ),
    )
    # GATE: FORMULAIC_ALPHA_ADAPTER_20260614 — opt-in formulaic alpha adapter
    parser.add_argument(
        "--enable-formulaic-alphas",
        action="store_true",
        help=(
            "GATE FORMULAIC_ALPHA_ADAPTER_20260614: Enable Kakushadze-inspired "
            "formulaic alpha adapter.  Research-only, opt-in, default disabled. "
            "Adds PIT-safe formulaic alpha columns to the alpha pool.  "
            "No live/default behavior change when disabled."
        ),
    )
    parser.add_argument(
        "--formulaic-alpha-set",
        type=str,
        default="small",
        choices=["small", "mean_reversion_liquidity", "v3_pruned", "v4_vn_extended"],
        help=(
            "GATE FORMULAIC_ALPHA_ADAPTER_20260614 / "
            "FORMULAIC_ALPHA_V2_20260614 / "
            "FORMULAIC_ALPHA_V3_PRUNE_20260614 / "
            "FORMULAIC_ALPHA_V4_EXTENDED_20260616: Which formulaic alpha set "
            "to compute. 'small' (default, v1, 5 candidates) or "
            "'mean_reversion_liquidity' (v2, 8 candidates, excludes "
            "weak momentum) or 'v3_pruned' (v3, 5 candidates, prunes "
            "negative-IC v2 candidates: amihud, range_compression, "
            "vol_vol_interact) or 'v4_vn_extended' (v4, 7 candidates, "
            "extends v3_pruned with 2 new VN microstructure/liquidity alphas: "
            "fml090_vn_liquidity_momentum, fml091_vn_hl_spread_reversal). "
            "Ignored when --enable-formulaic-alphas is not set."
        ),
    )
    # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614 — opt-in winner guard
    parser.add_argument(
        "--formulaic-winner-guard",
        action="store_true",
        help=(
            "GATE FORMULAIC_WINNER_SELECTION_GUARD_20260614: Enable "
            "research-only formulaic winner selection guard.  When enabled, "
            "constrains alpha selection and fallback candidate pool to the "
            "formulaic winner allowlist (strong positive-IC candidates).  "
            "Prevents negative legacy alphas from entering fallback.  "
            "PIT-safe: uses only current-fold train/validation IC.  "
            "Opt-in, default disabled — no live/default behavior change."
        ),
    )
    parser.add_argument(
        "--winner-alpha-filter",
        action="store_true",
        help=(
            "GATE FORMULAIC_WINNER_SELECTION_GUARD_20260614: Alias for "
            "--formulaic-winner-guard.  If either flag is set, the winner "
            "guard is enabled."
        ),
    )
    # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — opt-in regime routing
    parser.add_argument(
        "--enable-regime-routing",
        action="store_true",
        help=(
            "GATE REGIME_CONDITIONED_ALPHA_ROUTING_20260615: Enable "
            "research-only ex-ante regime-conditioned alpha routing.  "
            "Builds deterministic regimes from lagged/PIT-safe market "
            "features, estimates per-regime IC on train window only, and "
            "routes/scales alpha signals on test using ex-ante regime "
            "labels.  Never uses test returns for routing decisions.  "
            "Opt-in, default disabled — no live/default behavior change."
        ),
    )
    parser.add_argument(
        "--regime-routing-min-train-days",
        type=int,
        default=60,
        help=(
            "GATE REGIME_CONDITIONED_ALPHA_ROUTING_20260615: Minimum "
            "number of training days with regime labels required to "
            "enable routing.  If fewer days available, falls back to "
            "baseline.  Default 60."
        ),
    )
    parser.add_argument(
        "--regime-routing-min-ic",
        type=float,
        default=0.01,
        help=(
            "GATE REGIME_CONDITIONED_ALPHA_ROUTING_20260615: Minimum "
            "absolute per-regime IC required to apply regime routing "
            "scale.  Below this threshold, falls back to baseline "
            "(scale=1.0).  Default 0.01."
        ),
    )
    # GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615 — opt-in rolling universe
    parser.add_argument(
        "--rolling-universe",
        action="store_true",
        help=(
            "GATE PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615: Enable "
            "PIT-safe rolling universe selection. For each fold, selects "
            "top N symbols using ONLY train_df based on mean daily value "
            "(close*volume), ADTV>=5B, avg close>=5000, min history. "
            "Filters both train and test to selected symbols. "
            "Opt-in, default disabled — static universe preserved."
        ),
    )
    # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615 — opt-in per-rebalance dynamic universe
    parser.add_argument(
        "--dynamic-universe",
        action="store_true",
        help=(
            "GATE DYNAMIC_REBALANCE_UNIVERSE_20260615: Enable PIT-safe "
            "per-rebalance dynamic universe selection. For each rebalance "
            "date, selects top-N symbols using trailing lookback window "
            "ending BEFORE the rebalance date. Filters: ADTV>=5B VND, "
            "avg close>=5000 VND, min history. Opt-in, default disabled."
        ),
    )
    parser.add_argument(
        "--dynamic-universe-lookback-days",
        type=int,
        default=252,
        help=(
            "GATE DYNAMIC_REBALANCE_UNIVERSE_20260615: Trailing lookback "
            "window in calendar days for universe selection statistics. "
            "Default 252 (~1 year)."
        ),
    )
    parser.add_argument(
        "--dynamic-universe-rebalance-days",
        type=int,
        default=21,
        help=(
            "GATE DYNAMIC_REBALANCE_UNIVERSE_20260615: Rebalance cadence "
            "in calendar days for dynamic universe selection. "
            "Default 21 (~1 month)."
        ),
    )
    parser.add_argument(
        "--dynamic-universe-top-n",
        type=int,
        default=None,
        help=(
            "GATE DYNAMIC_REBALANCE_UNIVERSE_20260615: Number of top "
            "symbols per rebalance. Defaults to --top-n-symbols value "
            "(typically 30) when not specified."
        ),
    )
    # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — opt-in diversified basket
    parser.add_argument(
        "--diversified-basket",
        action="store_true",
        help=(
            "GATE DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615: Enable "
            "opt-in diversified alpha basket mode. Selects non-redundant "
            "basket by train IC/ICIR + pairwise correlation/cluster. "
            "Max N alphas per cluster, correlation penalty, fallback safe "
            "basket if no pass. Train-only evidence; no OOS/test metrics "
            "available to selector. Default disabled."
        ),
    )
    parser.add_argument(
        "--basket-max-per-cluster",
        type=int,
        default=2,
        help=(
            "GATE DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615: Maximum "
            "alphas per correlation cluster in diversified basket "
            "(default 2)."
        ),
    )
    parser.add_argument(
        "--basket-corr-threshold",
        type=float,
        default=0.70,
        help=(
            "GATE DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615: Absolute "
            "correlation threshold for clustering. |corr| >= threshold "
            "places alphas in same cluster (default 0.70)."
        ),
    )
    parser.add_argument(
        "--basket-redundancy-penalty",
        type=float,
        default=0.3,
        help=(
            "GATE DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615: Redundancy "
            "penalty weight for correlated selected alphas. Applied when "
            "|corr| > threshold/2 (default 0.3)."
        ),
    )
    parser.add_argument(
        "--basket-min-ic",
        type=float,
        default=0.0,
        help=(
            "GATE DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615: Minimum "
            "absolute train IC for a candidate to enter the diversified "
            "basket selector (default 0.0)."
        ),
    )
    # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615 — opt-in nonredundant alphas
    parser.add_argument(
        "--enable-nonredundant-alphas",
        action="store_true",
        help=(
            "GATE NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615: Enable "
            "opt-in nonredundant alpha family set v1. Adds 10 PIT-safe "
            "trailing-window alpha candidates from 5 families: liquidity "
            "shock reversal, range pressure/CLV, volatility compression "
            "breakout, sector/market-relative residual momentum/reversal, "
            "and breadth-conditioned reversal. Default disabled — no "
            "live/default behavior change when disabled."
        ),
    )
    parser.add_argument(
        "--nonredundant-alpha-set",
        type=str,
        default="v1",
        choices=["v1", "v1_pruned", "v1_mrm_only", "v1_mrm_range"],
        help=(
            "GATE NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615 / "
            "NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615: Which "
            "nonredundant alpha set to compute. 'v1' (10 candidates from "
            "5 families) or 'v1_pruned' (5 positive-evidence candidates: "
            "market_relative_momentum_20, range_pressure_momentum_20, "
            "liq_shock_reversal_10, close_location_value_10, "
            "vol_breakout_directional_10) or 'v1_mrm_only' (1 candidate: "
            "market_relative_momentum_20 — focused overlay) or "
            "'v1_mrm_range' (2 candidates: market_relative_momentum_20 + "
            "range_pressure_momentum_20 — focused overlay). Ignored when "
            "--enable-nonredundant-alphas is not set."
        ),
    )
    parser.add_argument(
        "--nonredundant-alpha-max-candidates",
        type=int,
        default=None,
        help=(
            "GATE NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615: Maximum "
            "number of nonredundant alpha candidates to compute. If None, "
            "computes all alphas in the set. Ignored when "
            "--enable-nonredundant-alphas is not set."
        ),
    )
    # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615 — opt-in OOS bundle wiring
    parser.add_argument(
        "--enable-automated-oos-bundle",
        action="store_true",
        help=(
            "GATE AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615: Enable "
            "research-only Phase35 OOS wiring for the approved top "
            "automated alpha bundle.  Injects the pre-approved bundle "
            "auto_top5_real_ic_20260615 (auto_rsi_14, auto_mr_zscore_20, "
            "auto_mom_ret_60, auto_mom_ret_20, auto_vol_std_ratio_10_30) "
            "as additional alpha columns.  PIT-safe: all signals are T-1 "
            "lagged.  Default disabled — no live/default behavior change."
        ),
    )
    parser.add_argument(
        "--automated-oos-bundle-name",
        type=str,
        default="auto_top5_real_ic_20260615",
        help=(
            "GATE AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615: Name of "
            "the approved bundle to inject.  Currently only "
            "'auto_top5_real_ic_20260615' is available.  Ignored when "
            "--enable-automated-oos-bundle is not set."
        ),
    )
    # GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
    parser.add_argument(
        "--enable-auto-winner-guard-allowlist",
        action="store_true",
        help=(
            "GATE AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615: "
            "Extend the formulaic winner guard allowlist to include "
            "auto bundle alpha names (auto_rsi_14, auto_mr_zscore_20, "
            "auto_mom_ret_60, auto_mom_ret_20, auto_vol_std_ratio_10_30).  "
            "Prevents the winner guard from blocking auto bundle alphas "
            "that have positive train-only IC evidence.  Requires both "
            "--formulaic-winner-guard and --enable-automated-oos-bundle.  "
            "Research-only, opt-in, default disabled — no live/default "
            "behavior change when disabled."
        ),
    )
    # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616 — opt-in stability filter
    parser.add_argument(
        "--enable-oos-stability-filter",
        action="store_true",
        help=(
            "GATE AUTO_ALPHA_OOS_STABILITY_FILTER_20260616: Enable "
            "PIT-safe OOS stability filter for auto-alpha bundle.  "
            "Uses ONLY train/in-fold pre-OOS evidence: IC sign "
            "consistency, ICIR threshold, IC decay penalty.  Never "
            "uses OOS/test labels or current-bar data.  Research-only, "
            "opt-in, default disabled — no live/default behavior change."
        ),
    )
    parser.add_argument(
        "--stability-min-icir",
        type=float,
        default=0.15,
        help=(
            "GATE AUTO_ALPHA_OOS_STABILITY_FILTER_20260616: Minimum "
            "absolute ICIR for alpha to pass stability filter. "
            "Default 0.15."
        ),
    )
    parser.add_argument(
        "--stability-min-sign-consistency",
        type=float,
        default=0.55,
        help=(
            "GATE AUTO_ALPHA_OOS_STABILITY_FILTER_20260616: Minimum "
            "IC sign consistency (fraction of sub-windows matching "
            "overall IC sign) for alpha to pass.  Default 0.55."
        ),
    )
    parser.add_argument(
        "--stability-decay-penalty-factor",
        type=float,
        default=1.0,
        help=(
            "GATE AUTO_ALPHA_OOS_STABILITY_FILTER_20260616: Penalty "
            "factor applied when IC decay ratio is negative (recent "
            "IC opposite sign to oldest IC).  Higher values impose "
            "stricter decay filtering.  Default 1.0."
        ),
    )
    parser.add_argument(
        "--enable-vn-specific-alphas",
        action="store_true",
        help="Enable VN-specific alphas in the backtest (opt-in, default disabled)",
    )
    # GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616 — opt-in risk/sizing overlay
    parser.add_argument(
        "--risk-sizing-overlay",
        action="store_true",
        help=(
            "GATE BASELINE_RISK_SIZING_OPTIMIZATION_20260616: Enable "
            "research-only opt-in risk/sizing overlay.  Two sub-features: "
            "inverse-vol sizing (weight by 1/realized_vol) and confidence "
            "scaling (scale exposure by rolling IC).  Both PIT-safe, "
            "trailing-data only.  Default disabled — no live/default "
            "behavior change."
        ),
    )
    parser.add_argument(
        "--risk-sizing-inverse-vol",
        action="store_true",
        help=(
            "GATE BASELINE_RISK_SIZING_OPTIMIZATION_20260616: Enable "
            "inverse-volatility sizing within the risk overlay.  "
            "Replaces equal-weight with 1/realized_vol weights.  "
            "Requires --risk-sizing-overlay."
        ),
    )
    parser.add_argument(
        "--risk-sizing-inverse-vol-window",
        type=int,
        default=20,
        help=(
            "GATE BASELINE_RISK_SIZING_OPTIMIZATION_20260616: Trailing "
            "window (days) for realized volatility estimation.  "
            "Default 20."
        ),
    )
    parser.add_argument(
        "--risk-sizing-inverse-vol-floor",
        type=float,
        default=0.3,
        help=(
            "GATE BASELINE_RISK_SIZING_OPTIMIZATION_20260616: Minimum "
            "weight fraction (prevents degenerate zero-vol weights).  "
            "Default 0.3."
        ),
    )
    parser.add_argument(
        "--risk-sizing-confidence",
        action="store_true",
        help=(
            "GATE BASELINE_RISK_SIZING_OPTIMIZATION_20260616: Enable "
            "confidence scaling within the risk overlay.  Scales total "
            "gross exposure by rolling signal IC strength.  "
            "Requires --risk-sizing-overlay."
        ),
    )
    parser.add_argument(
        "--risk-sizing-confidence-window",
        type=int,
        default=60,
        help=(
            "GATE BASELINE_RISK_SIZING_OPTIMIZATION_20260616: Trailing "
            "window (days) for rolling IC estimation.  Default 60."
        ),
    )
    parser.add_argument(
        "--risk-sizing-confidence-min-ic",
        type=float,
        default=0.01,
        help=(
            "GATE BASELINE_RISK_SIZING_OPTIMIZATION_20260616: Minimum "
            "absolute IC for full exposure.  Below this, scale down.  "
            "Default 0.01."
        ),
    )
    parser.add_argument(
        "--risk-sizing-confidence-max-scale",
        type=float,
        default=1.2,
        help=(
            "GATE BASELINE_RISK_SIZING_OPTIMIZATION_20260616: Maximum "
            "exposure scale (cap upside leverage).  Default 1.2."
        ),
    )
    parser.add_argument(
        "--risk-sizing-confidence-min-scale",
        type=float,
        default=0.3,
        help=(
            "GATE BASELINE_RISK_SIZING_OPTIMIZATION_20260616: Minimum "
            "exposure scale (never fully de-risk to zero).  Default 0.3."
        ),
    )
    # GATE: REGIME_CONDITIONAL_SIZING_20260616 — opt-in regime-conditional sizing
    parser.add_argument(
        "--risk-sizing-regime",
        action="store_true",
        help=(
            "GATE REGIME_CONDITIONAL_SIZING_20260616: Enable "
            "regime-conditional sizing within the risk overlay.  "
            "Detects Bear/Neutral/Bull regimes from PIT-safe trailing "
            "market proxy data and scales exposure in Bear regime.  "
            "Requires --risk-sizing-overlay.  Default disabled."
        ),
    )
    parser.add_argument(
        "--risk-sizing-regime-scale",
        type=float,
        default=0.5,
        help=(
            "GATE REGIME_CONDITIONAL_SIZING_20260616: Exposure scale "
            "applied in Bear regime (default 0.5 = 50%% exposure).  "
            "Must be in (0, 1]."
        ),
    )
    parser.add_argument(
        "--risk-sizing-regime-ma-window",
        type=int,
        default=200,
        help=(
            "GATE REGIME_CONDITIONAL_SIZING_20260616: Moving-average "
            "window for market proxy trend detection (default 200)."
        ),
    )
    parser.add_argument(
        "--risk-sizing-regime-vol-window",
        type=int,
        default=20,
        help=(
            "GATE REGIME_CONDITIONAL_SIZING_20260616: Rolling std "
            "window for market proxy volatility (default 20)."
        ),
    )
    parser.add_argument(
        "--risk-sizing-regime-vol-median-window",
        type=int,
        default=60,
        help=(
            "GATE REGIME_CONDITIONAL_SIZING_20260616: Rolling median "
            "window for adaptive vol threshold (default 60)."
        ),
    )
    # GATE: REGIME_CONDITIONAL_SIZING_20260616 — Hướng 3 HMM + auto-optimize
    parser.add_argument(
        "--risk-sizing-regime-window",
        type=int,
        default=200,
        help=(
            "GATE REGIME_CONDITIONAL_SIZING_20260616: Trailing window "
            "(days) for HMM fitting on market returns (default 200)."
        ),
    )
    parser.add_argument(
        "--risk-sizing-regime-mode",
        type=str,
        choices=["heuristic", "hmm"],
        default="heuristic",
        help=(
            "GATE REGIME_CONDITIONAL_SIZING_20260616: Regime detection "
            "mode. 'heuristic' (MA/vol, default) or 'hmm' (3-state "
            "Gaussian HMM with Baum-Welch EM)."
        ),
    )
    parser.add_argument(
        "--risk-sizing-regime-auto-optimize",
        action="store_true",
        help=(
            "GATE REGIME_CONDITIONAL_SIZING_20260616: Auto-optimize "
            "regime_sizing_scale by grid-searching on train data to "
            "maximize Sharpe ratio.  Overrides --risk-sizing-regime-scale."
        ),
    )
    # GATE: REGIME_CONDITIONAL_SIZING_20260616 — HMM stride refitting
    parser.add_argument(
        "--risk-sizing-regime-refit-stride",
        type=int,
        default=5,
        help=(
            "GATE REGIME_CONDITIONAL_SIZING_20260616: Refit HMM only "
            "every N days during walk-forward OOS.  Between refits, "
            "cached parameters are used for inference only.  Must be "
            ">= 1.  Default 5."
        ),
    )
    # GATE: LATENT_ALPHA_MINING_64D_20260617 — opt-in latent alpha injection
    parser.add_argument(
        "--enable-latent-alphas",
        action="store_true",
        help=(
            "GATE LATENT_ALPHA_MINING_64D_20260617: Enable research-only "
            "latent alpha injection from PCA/ICA decomposition of the 64D "
            "feature space.  Loads pre-computed latent components from "
            "data/latent_alphas_components.parquet and merges into the "
            "backtest dataframe.  PIT-safe: model fit on train-only, "
            "projections frozen.  Default disabled — no live/default "
            "behavior change."
        ),
    )
    parser.add_argument(
        "--latent-alpha-path",
        type=str,
        default=None,
        help=(
            "GATE LATENT_ALPHA_MINING_64D_20260617: Override path to "
            "latent alpha components parquet.  Default: "
            "data/latent_alphas_components.parquet."
        ),
    )
    parser.add_argument(
        "--latent-alpha-top-n",
        type=int,
        default=None,
        help=(
            "GATE LATENT_ALPHA_MINING_64D_20260617: Inject only the top-N "
            "latent components ranked by OOS |IR| from the metrics JSON.  "
            "Default: inject all components."
        ),
    )
    parser.add_argument(
        "--latent-alpha-min-ir",
        type=float,
        default=0.3,
        help=(
            "GATE LATENT_ALPHA_MINING_64D_20260617: Minimum absolute OOS "
            "IR for a latent component to be injected.  Default 0.3 "
            "(matches quant-research skill IR gate)."
        ),
    )
    # GATE: LATENT_ALPHA_MINING_64D_20260617 — PLS variant support
    parser.add_argument(
        "--enable-latent-pls",
        action="store_true",
        help=(
            "GATE LATENT_ALPHA_MINING_64D_20260617: Also inject PLS "
            "(supervised) latent components from the pre-computed parquet. "
            "PLS columns have prefix 'latent_pls_'. Requires --enable-latent-alphas."
        ),
    )
    parser.add_argument(
        "--enable-latent-regime-conditional",
        action="store_true",
        help=(
            "GATE LATENT_ALPHA_MINING_64D_20260617: Also inject "
            "regime-conditional latent components from the pre-computed "
            "parquet. Regime columns have prefix 'latent_r<N>_<method>_'. "
            "Requires --enable-latent-alphas."
        ),
    )
    # GATE: LATENT_ALPHA_MINING_64D_20260617 — Deep Autoencoder variant support
    parser.add_argument(
        "--enable-latent-autoencoder",
        action="store_true",
        help=(
            "GATE LATENT_ALPHA_MINING_64D_20260617: Also inject deep "
            "nonlinear autoencoder latent components from the pre-computed "
            "parquet.  Autoencoder columns have prefix 'latent_ae_'.  "
            "Requires --enable-latent-alphas.  The deep AE uses multiple "
            "hidden layers with GELU activations and batch normalization "
            "to extract nonlinear latent representations."
        ),
    )
    args = parser.parse_args()
    # GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615
    # Default: use_xgboost=False. Only True when --enable-xgboost is set.
    # --no-xgboost is kept for backward compat (no-op, already default-off).
    args.use_xgboost = args.enable_xgboost
    if args.no_xgboost and not args.enable_xgboost:
        logger.info(
            "[DEPRECATED] --no-xgboost is a no-op: XGBoost is disabled by default "
            "per GATE DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615."
        )
    if args.enable_xgboost:
        logger.warning(
            "[XGBoost] Opt-in research mode enabled via --enable-xgboost. "
            "E2E A/B evidence showed XGBoost degrades signal — use with caution."
        )
    if args.enable_multi_model_ensemble and args.enable_xgboost:
        logger.warning("[MultiModel] --enable-multi-model-ensemble overrides --enable-xgboost path.")

    # GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615
    # Default: drawdown_control=True. Only False when --disable-drawdown-control is set.
    # --drawdown-control is kept for backward compat (no-op, already default-on).
    args.drawdown_control = not args.disable_drawdown_control
    if args.drawdown_control and not args.disable_drawdown_control:
        # Check if deprecated --drawdown-control flag was explicitly passed
        if '--drawdown-control' in sys.argv:
            logger.info(
                "[DEPRECATED] --drawdown-control is a no-op: drawdown control is "
                "enabled by default per GATE "
                "DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615."
            )
    if args.disable_drawdown_control:
        logger.warning(
            "[DrawdownControl] Opt-out: drawdown control DISABLED via "
            "--disable-drawdown-control. E2E evidence shows this degrades "
            "MaxDD (-66.99% vs -12.34% controlled). Use only for baseline repro."
        )

    # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614 — combine alias flags
    args.formulaic_winner_guard = (
        args.formulaic_winner_guard or args.winner_alpha_filter
    )

    # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_FIX1_20260614 — auto-enable guard
    # whenever risk-adjusted alpha selection is active, unless explicitly opted out.
    args.portfolio_guard_enabled = (
        args.risk_adjusted_alpha_selection
        and not args.disable_risk_adjusted_portfolio_guard
    )
    args.portfolio_guard_tolerance = args.risk_adjusted_portfolio_guard_tolerance
    
    # Parse blend_horizons string into list of integers
    if args.multi_horizon_blend:
        try:
            args.blend_horizons_list = [int(h.strip()) for h in args.blend_horizons.split(',')]
        except ValueError:
            logger.error(f"Invalid --blend-horizons format: {args.blend_horizons}. Expected comma-separated integers.")
            sys.exit(1)
    else:
        args.blend_horizons_list = None

    logger.info("=" * 80)
    logger.info("Phase 3.5 Walk-Forward Backtest - Real VN Market Data")
    logger.info("=" * 80)
    
    # Configuration translation
    START_DATE = args.start_date
    END_DATE = args.end_date
    
    # GATE: CPCV_FOLD_EXPANSION_20260614 — opt-in fold expansion defaults
    # Defaults unchanged: 8 folds / 3 train-years / 1 test-year / 30 top-n-symbols
    # Quick-mode always overrides to 2/1/1/1 regardless of CLI values
    _DEFAULT_N_FOLDS = 8
    _DEFAULT_TRAIN_YEARS = 3
    _DEFAULT_TEST_YEARS = 1
    _DEFAULT_TOP_N_SYMBOLS = 30

    if args.quick_mode:
        TOP_N_SYMBOLS = 1
        N_FOLDS = 2
        TRAIN_YEARS = 1
        TEST_YEARS = 1
    else:
        TOP_N_SYMBOLS = args.top_n_symbols if args.top_n_symbols is not None else _DEFAULT_TOP_N_SYMBOLS
        N_FOLDS = args.n_folds if args.n_folds is not None else _DEFAULT_N_FOLDS
        TRAIN_YEARS = args.train_years if args.train_years is not None else _DEFAULT_TRAIN_YEARS
        TEST_YEARS = args.test_years if args.test_years is not None else _DEFAULT_TEST_YEARS
        
    # ==================================================================
    # GATE: LATENT_ALPHA_MINING_64D_20260617 — auto-align fold parameters
    # When latent alphas are enabled, pre-check the latent components
    # date range.  If START_DATE < latent min date the walk-forward
    # folds would have all-zero latent_ae_* in train windows because
    # the merge (how='left', fillna(0)) produces zeros for dates
    # outside the latent parquet's coverage.
    # Auto-adjust START_DATE, TRAIN_YEARS, and N_FOLDS so that every
    # fold has meaningful latent alpha coverage.
    # ==================================================================
    if args.enable_latent_alphas:
        from pathlib import Path as _PathAlign
        import pandas as _pdAlign

        _la_align_suffix = "_quick" if args.quick_mode else ""
        _la_align_path = (
            _PathAlign(args.latent_alpha_path)
            if args.latent_alpha_path is not None
            else REPO_ROOT / "data" / f"latent_alphas_components{_la_align_suffix}.parquet"
        )

        if _la_align_path.exists():
            _la_align_df = _pdAlign.read_parquet(
                _la_align_path, columns=["date"]
            )
            _la_min_date = _la_align_df["date"].min()
            _la_max_date = _la_align_df["date"].max()
            _la_span_days = (_la_max_date - _la_min_date).days

            _start_ts = _pdAlign.Timestamp(START_DATE)
            _la_adjusted = False

            # 1) Push START_DATE forward to latent min date
            if _start_ts < _la_min_date:
                logger.warning(
                    "[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                    "START_DATE=%s is before latent data start %s. "
                    "Auto-adjusting START_DATE to %s so walk-forward folds "
                    "have latent alpha coverage in train windows.",
                    START_DATE, _la_min_date.date(), _la_min_date.date(),
                )
                START_DATE = str(_la_min_date.date())
                _la_adjusted = True

            # 2) Shrink TRAIN_YEARS if train+test window exceeds latent span
            _window_days = (TRAIN_YEARS + TEST_YEARS) * 365
            if _window_days > _la_span_days:
                _max_train = max(1, (_la_span_days // 365) - TEST_YEARS)
                if _max_train < TRAIN_YEARS:
                    logger.warning(
                        "[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                        "train_years=%d + test_years=%d (%d days) exceeds "
                        "latent span (%d days). Auto-reducing train_years "
                        "to %d.",
                        TRAIN_YEARS, TEST_YEARS, _window_days,
                        _la_span_days, _max_train,
                    )
                    TRAIN_YEARS = _max_train
                    _la_adjusted = True

            # 3) Cap N_FOLDS so all folds fit within the latent span
            _effective_span = (
                _la_span_days - TRAIN_YEARS * 365 - TEST_YEARS * 365
            )
            if _effective_span > 0 and N_FOLDS > 1:
                # Use 30-day minimum step to avoid excessive fold overlap
                _max_folds = _effective_span // 30 + 1
                if N_FOLDS > _max_folds:
                    logger.warning(
                        "[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                        "n_folds=%d exceeds max folds (%d) that fit within "
                        "latent span at step>=30d. Auto-reducing n_folds "
                        "to %d.",
                        N_FOLDS, _max_folds, _max_folds,
                    )
                    N_FOLDS = _max_folds
                    _la_adjusted = True

            if _la_adjusted:
                logger.info(
                    "[LatentAlphas] Auto-aligned params: START_DATE=%s, "
                    "TRAIN_YEARS=%d, TEST_YEARS=%d, N_FOLDS=%d "
                    "(latent span: %s to %s, %d days)",
                    START_DATE, TRAIN_YEARS, TEST_YEARS, N_FOLDS,
                    _la_min_date.date(), _la_max_date.date(), _la_span_days,
                )
            else:
                logger.info(
                    "[LatentAlphas] No alignment needed: START_DATE=%s "
                    "already within latent span %s to %s.",
                    START_DATE, _la_min_date.date(), _la_max_date.date(),
                )
        else:
            logger.warning(
                "[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                "Latent parquet not found at %s — cannot auto-align. "
                "Run `python scripts/mine_latent_alphas.py` first.",
                _la_align_path,
            )

    MIN_IC_THRESHOLD = 0.02
    TOP_N_ALPHAS = 5
    RETURN_HORIZON = 5  # T+5
    STAGE2_TOP_N_STOCKS = 15       # V5 proven
    STAGE2_REBALANCE_FREQ = 7
    STAGE2_SECTOR_CAP_PCT = 0.40   # V5 proven
    
    # Calculate transaction costs from slippage and commission inputs
    tcost_bps = args.slippage_bps + args.commission_bps
    cost_per_turnover = tcost_bps / 10000.0
    cost_aware = tcost_bps > 0
    
    logger.info(f"Configuration:")
    logger.info(f"  Date Range: {START_DATE} to {END_DATE}")
    logger.info(f"  Top Symbols: {TOP_N_SYMBOLS}")
    logger.info(f"  Folds: {N_FOLDS}")
    logger.info(f"  Train Window: {TRAIN_YEARS} year(s)")
    logger.info(f"  Test Window: {TEST_YEARS} year(s)")
    logger.info(f"  Min IC Threshold: {MIN_IC_THRESHOLD}")
    logger.info(f"  Top Alphas: {TOP_N_ALPHAS}")
    logger.info(f"  Return Horizon: T+{RETURN_HORIZON}")
    logger.info(f"  [Stage2] Top N Stocks: {STAGE2_TOP_N_STOCKS}")
    logger.info(f"  [Stage2] Rebalance Freq: every {STAGE2_REBALANCE_FREQ} days")
    logger.info(f"  [Stage2] Sector Cap: {STAGE2_SECTOR_CAP_PCT:.0%}")
    # GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615 — log XGBoost opt-in status
    _xgb_status = "DISABLED (default, opt-in via --enable-xgboost)" if not args.use_xgboost else "ENABLED (opt-in research mode)"
    logger.info(f"  [Stage4] Use XGBoost: {args.use_xgboost} — {_xgb_status}")
    logger.info(f"  [Stage4] Multi-Model Ensemble: {args.enable_multi_model_ensemble}")
    logger.info(f"  [Stage6.2] Cost Aware: {cost_aware} (tcost={tcost_bps} bps)")
    # GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615 — log drawdown control research default
    _dd_status = "ENABLED (research default, opt-out via --disable-drawdown-control)" if args.drawdown_control else "DISABLED (opt-out)"
    logger.info(f"  [Stage6.3] Drawdown Control: {args.drawdown_control} — {_dd_status} (threshold={args.drawdown_threshold:.1%})")
    # GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616 — log drawdown re-entry config
    _dd_hwm_reset = not args.drawdown_no_hwm_reset
    _re_status = "ENABLED (opt-in)" if args.drawdown_re_entry else "DISABLED (default, permanent stop-out)"
    logger.info(f"  [Stage6.3] Drawdown Re-Entry: {args.drawdown_re_entry} — {_re_status}")
    if args.drawdown_re_entry:
        logger.info(f"  [Stage6.3]   Cooldown Days: {args.drawdown_cooldown_days}")
        logger.info(f"  [Stage6.3]   HWM Reset: {_dd_hwm_reset}")
    # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616 — log adaptive config
    _adr_status = "ENABLED (opt-in)" if args.drawdown_adaptive_re_entry else "DISABLED (default)"
    logger.info(f"  [Stage6.3] Adaptive Re-Entry: {args.drawdown_adaptive_re_entry} — {_adr_status}")
    if args.drawdown_adaptive_re_entry:
        logger.info(f"  [Stage6.3]   Bear Threshold: {args.drawdown_adaptive_bear_threshold}")
        logger.info(f"  [Stage6.3]   Vol Window: {args.drawdown_adaptive_vol_window}")
        logger.info(f"  [Stage6.3]   Vol Multiplier: {args.drawdown_adaptive_vol_multiplier}")
        logger.info(f"  [Stage6.3]   Max Cooldown: {args.drawdown_adaptive_max_cooldown}")
    logger.info(f"  [Evolved] Enable: {args.enable_evolved} (blend_weight={args.evolved_blend_weight:.2f})")
    logger.info(f"  [P10] Multi-Horizon Blend: {args.multi_horizon_blend} (horizons={args.blend_horizons}, method={args.blend_weight_method})")
    logger.info(f"  [P10] Gate Tuning: mode={args.p10_gate_mode}, min_pass={args.p10_gate_min_pass}, allow_fallback={args.p10_gate_allow_fallback_candidates}")
    logger.info(f"  [GATE] Risk-Adjusted Alpha Selection: {args.risk_adjusted_alpha_selection}")
    logger.info(f"  [GATE] Risk-Adjusted Preset: {args.risk_adjusted_preset}")
    logger.info(f"  [GATE] Portfolio Guard Enabled: {args.portfolio_guard_enabled}")
    logger.info(f"  [GATE] Portfolio Guard Tolerance: {args.portfolio_guard_tolerance}")
    logger.info(f"  [GATE] Research Pool Mode: {args.research_pool_mode}")
    # GATE: FORMULAIC_ALPHA_ADAPTER_20260614 — log formulaic alpha config
    logger.info(f"  [GATE] Formulaic Alphas Enabled: {args.enable_formulaic_alphas}")
    logger.info(f"  [GATE] Formulaic Alpha Set: {args.formulaic_alpha_set}")
    # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614 — log winner guard config
    logger.info(f"  [GATE] Formulaic Winner Guard: {args.formulaic_winner_guard}")
    # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — log regime routing config
    logger.info(f"  [GATE] Regime Routing Enabled: {args.enable_regime_routing}")
    logger.info(f"  [GATE] Regime Routing Min Train Days: {args.regime_routing_min_train_days}")
    logger.info(f"  [GATE] Regime Routing Min IC: {args.regime_routing_min_ic}")
    # GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615 — log rolling universe config
    _rolling_status = "DISABLED (default, static universe)" if not args.rolling_universe else "ENABLED (opt-in PIT rolling universe)"
    logger.info(f"  [GATE] Rolling Universe: {args.rolling_universe} — {_rolling_status}")
    # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615 — log dynamic universe config
    _dyn_status = "DISABLED (default, static universe)" if not args.dynamic_universe else "ENABLED (opt-in PIT dynamic universe)"
    logger.info(f"  [GATE] Dynamic Universe: {args.dynamic_universe} — {_dyn_status}")
    logger.info(f"  [GATE] Dynamic Universe Lookback Days: {args.dynamic_universe_lookback_days}")
    logger.info(f"  [GATE] Dynamic Universe Rebalance Days: {args.dynamic_universe_rebalance_days}")
    logger.info(f"  [GATE] Dynamic Universe Top N: {args.dynamic_universe_top_n}")
    # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — log diversified basket config
    _db_status = "DISABLED (default)" if not args.diversified_basket else "ENABLED (opt-in diversified basket)"
    logger.info(f"  [GATE] Diversified Basket: {args.diversified_basket} — {_db_status}")
    logger.info(f"  [GATE] Basket Max Per Cluster: {args.basket_max_per_cluster}")
    logger.info(f"  [GATE] Basket Corr Threshold: {args.basket_corr_threshold}")
    logger.info(f"  [GATE] Basket Redundancy Penalty: {args.basket_redundancy_penalty}")
    logger.info(f"  [GATE] Basket Min IC: {args.basket_min_ic}")
    # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615 — log nonredundant alpha config
    _nr_status = "DISABLED (default)" if not args.enable_nonredundant_alphas else "ENABLED (opt-in nonredundant alphas)"
    logger.info(f"  [GATE] Nonredundant Alphas: {args.enable_nonredundant_alphas} — {_nr_status}")
    logger.info(f"  [GATE] Nonredundant Alpha Set: {args.nonredundant_alpha_set}")
    logger.info(f"  [GATE] Nonredundant Alpha Max Candidates: {args.nonredundant_alpha_max_candidates}")
    # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615 — log OOS bundle config
    _aoos_status = "DISABLED (default)" if not args.enable_automated_oos_bundle else "ENABLED (opt-in OOS bundle)"
    logger.info(f"  [GATE] Automated OOS Bundle: {args.enable_automated_oos_bundle} — {_aoos_status}")
    logger.info(f"  [GATE] Automated OOS Bundle Name: {args.automated_oos_bundle_name}")
    # GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615 — log allowlist config
    _awga_status = "DISABLED (default)" if not args.enable_auto_winner_guard_allowlist else "ENABLED (opt-in)"
    logger.info(
        f"  [GATE] Auto Winner Guard Allowlist: "
        f"{args.enable_auto_winner_guard_allowlist} — {_awga_status}"
    )
    # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616 — log stability filter config
    _sf_status = "DISABLED (default)" if not args.enable_oos_stability_filter else "ENABLED (opt-in)"
    logger.info(
        f"  [GATE] OOS Stability Filter: "
        f"{args.enable_oos_stability_filter} — {_sf_status}"
    )
    logger.info(f"  [GATE] VN-Specific Alphas: {args.enable_vn_specific_alphas}")
    logger.info(f"  [GATE] Stability Min ICIR: {args.stability_min_icir}")
    logger.info(f"  [GATE] Stability Min Sign Consistency: {args.stability_min_sign_consistency}")
    logger.info(f"  [GATE] Stability Decay Penalty Factor: {args.stability_decay_penalty_factor}")
    # GATE: LATENT_ALPHA_MINING_64D_20260617 — log latent alpha config
    # Resolve the actual path early so the log reflects the real file
    # (including _quick suffix when --quick-mode is set).
    _la_status = "DISABLED (default)" if not args.enable_latent_alphas else "ENABLED (opt-in)"
    logger.info(f"  [GATE] Latent Alphas: {args.enable_latent_alphas} — {_la_status}")
    _resolved_latent_alpha_path = args.latent_alpha_path
    if _resolved_latent_alpha_path is None:
        _la_log_suffix = "_quick" if args.quick_mode else ""
        _resolved_latent_alpha_path = str(
            REPO_ROOT / "data" / f"latent_alphas_components{_la_log_suffix}.parquet"
        )
    logger.info(f"  [GATE] Latent Alpha Path (resolved): {_resolved_latent_alpha_path}")
    logger.info(f"  [GATE] Latent Alpha Top N: {args.latent_alpha_top_n or 'all'}")
    logger.info(f"  [GATE] Latent Alpha Min IR: {args.latent_alpha_min_ir}")
    logger.info(f"  [GATE] Latent Alpha PLS: {args.enable_latent_pls}")
    logger.info(f"  [GATE] Latent Alpha Regime-Conditional: {args.enable_latent_regime_conditional}")
    logger.info(f"  [GATE] Latent Alpha Autoencoder: {args.enable_latent_autoencoder}")
    # GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616 — log risk/sizing overlay config
    _rs_status = "DISABLED (default)" if not args.risk_sizing_overlay else "ENABLED (opt-in)"
    logger.info(f"  [GATE] Risk/Sizing Overlay: {args.risk_sizing_overlay} — {_rs_status}")
    if args.risk_sizing_overlay:
        logger.info(f"  [GATE]   Inverse-Vol Sizing: {args.risk_sizing_inverse_vol} (window={args.risk_sizing_inverse_vol_window}, floor={args.risk_sizing_inverse_vol_floor})")
        logger.info(f"  [GATE]   Confidence Scaling: {args.risk_sizing_confidence} (window={args.risk_sizing_confidence_window}, min_ic={args.risk_sizing_confidence_min_ic})")
        logger.info(f"  [GATE]   Confidence Scale Range: [{args.risk_sizing_confidence_min_scale}, {args.risk_sizing_confidence_max_scale}]")
    # GATE: REGIME_CONDITIONAL_SIZING_20260616 — log regime sizing config
    if args.risk_sizing_overlay:
        logger.info(f"  [GATE]   Regime Sizing: {args.risk_sizing_regime} (mode={args.risk_sizing_regime_mode}, scale={args.risk_sizing_regime_scale})")
        logger.info(f"  [GATE]   Regime Window: {args.risk_sizing_regime_window}")
        logger.info(f"  [GATE]   Regime Auto-Optimize: {args.risk_sizing_regime_auto_optimize}")
        logger.info(f"  [GATE]   Regime Refit Stride: {args.risk_sizing_regime_refit_stride}")
    # GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614 — log data hygiene config
    _data_cleaning_on = not args.disable_data_cleaning
    logger.info(f"  [DataHygiene] Data Cleaning Enabled: {_data_cleaning_on} (opt-out via --disable-data-cleaning)")
    logger.info(f"  [DataHygiene] Normalization Mode: {args.normalization_mode}")
    # GATE: CPCV_FOLD_EXPANSION_20260614 — log fold expansion config
    logger.info(f"  [CPCV_FOLD_EXPANSION] n_folds={N_FOLDS}, train_years={TRAIN_YEARS}, test_years={TEST_YEARS}, top_n_symbols={TOP_N_SYMBOLS}")
    logger.info(f"  [CPCV_FOLD_EXPANSION] output_tag={args.output_tag}")
    logger.info(f"  [UI Context] Initial Capital: {args.initial_capital:,.0f} VND | Strategy: {args.strategy}")
    logger.info("")
    
    # FIX 7: Quick-mode smoke-test warning
    if args.quick_mode or TOP_N_SYMBOLS < 5:
        logger.warning("=" * 80)
        logger.warning("SMOKE TEST MODE - NOT PERFORMANCE EVIDENCE")
        logger.warning("=" * 80)
        logger.warning(f"Running with top_n_symbols={TOP_N_SYMBOLS} (< 5 symbols)")
        logger.warning("Cross-sectional metrics (z-score, IC, Sharpe) may collapse to zero/NaN")
        logger.warning("This is a SMOKE TEST to verify code execution, not proof of strategy quality")
        logger.warning("For performance validation, use top_n_symbols >= 30 with full fold configuration")
        logger.warning("=" * 80)
        logger.warning("")
    
    # Step 1: Load and prepare data
    logger.info("Step 1: Loading and preparing data...")
    loader = Phase35DataLoader()

    # GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614
    # Data cleaning is DEFAULT-ON. --disable-data-cleaning opts out.
    data_cleaning_enabled = not args.disable_data_cleaning
    normalization_mode = args.normalization_mode

    df = loader.load_and_prepare(
        start_date=START_DATE,
        end_date=END_DATE,
        top_n_symbols=TOP_N_SYMBOLS,
        forward_horizons=[1, 3, 5],
        enable_data_cleaning=data_cleaning_enabled,
        normalization_mode=normalization_mode,
    )

    # Capture evidence for persistence
    data_hygiene_evidence = loader.get_last_evidence()
    
    logger.info(f"Data loaded: {len(df):,} rows, {df['ticker'].nunique()} symbols")
    logger.info(f"Date range: {df['date'].min()} to {df['date'].max()}")
    logger.info("")

    # ==================================================================
    # GATE: LATENT_ALPHA_MINING_64D_20260617
    # Merge pre-computed latent alpha components into main dataframe.
    # Opt-in, research-only.  No live/default behavior change.
    # ==================================================================
    latent_alpha_evidence = None
    latent_alpha_cols_injected = []
    if args.enable_latent_alphas:
        from pathlib import Path as _Path
        import pandas as _pd

        # GATE: LATENT_ALPHA_MINING_64D_20260617 — reuse the pre-resolved path
        # from the config log section (includes _quick suffix when applicable).
        _la_path = _Path(_resolved_latent_alpha_path)
        # Derive metrics path from components path (respecting _quick suffix)
        _la_stem = _la_path.stem  # e.g. "latent_alphas_components" or "latent_alphas_components_quick"
        _la_metrics_path = _la_path.parent / f"{_la_stem.replace('_components', '_metrics')}.json"

        logger.info("")
        logger.info("=" * 80)
        logger.info(
            "[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
            "Injecting pre-computed latent alpha components"
        )
        logger.info(f"  Source: {_la_path}")
        logger.info(f"  Min IR: {args.latent_alpha_min_ir}")
        logger.info(f"  Top N: {args.latent_alpha_top_n or 'all'}")
        logger.info("=" * 80)

        if not _la_path.exists():
            logger.warning(
                f"[LatentAlphas] File not found: {_la_path}. "
                f"Run `python scripts/mine_latent_alphas.py` first. "
                f"Skipping latent alpha injection."
            )
        else:
            _la_df = _pd.read_parquet(_la_path)
            _la_cols_available = [
                c for c in _la_df.columns if c.startswith("latent_")
            ]

            # GATE: LATENT_ALPHA_MINING_64D_20260617 — filter by model variant
            # By default, only PCA/ICA columns (latent_pca_*, latent_ica_*).
            # With --enable-latent-pls, also include latent_pls_*.
            # With --enable-latent-regime-conditional, also include latent_r*_*.
            # With --enable-latent-autoencoder, also include latent_ae_*.
            _la_pca_ica_cols = [
                c for c in _la_cols_available
                if c.startswith("latent_pca_") or c.startswith("latent_ica_")
            ]
            _la_pls_cols = [
                c for c in _la_cols_available if c.startswith("latent_pls_")
            ] if args.enable_latent_pls else []
            _la_regime_cols = [
                c for c in _la_cols_available
                if c.startswith("latent_r") and "_" in c[9:]
            ] if args.enable_latent_regime_conditional else []
            _la_ae_cols = [
                c for c in _la_cols_available if c.startswith("latent_ae_")
            ] if args.enable_latent_autoencoder else []

            # Combined available columns based on variant selection.
            # L3-Fix: Always restrict to the union of selected variant types.
            # When PLS/regime-conditional/autoencoder are disabled, only PCA/ICA columns
            # are included — latent_pls_*, latent_r*, and latent_ae_* are filtered out.
            _la_cols_available = (
                _la_pca_ica_cols + _la_pls_cols + _la_regime_cols + _la_ae_cols
            )

            logger.info(
                f"[LatentAlphas] Loaded {_la_df.shape[0]} rows, "
                f"{len(_la_cols_available)} latent columns"
                f" (pca/ica={len(_la_pca_ica_cols)}, "
                f"pls={len(_la_pls_cols)}, "
                f"regime={len(_la_regime_cols)}, "
                f"ae={len(_la_ae_cols)})"
            )

            # GATE: LATENT_ALPHA_MINING_64D_20260617 — validate 64D parquet
            # Production mode MUST have exactly 64 latent columns for PCA/ICA.
            # PLS and regime-conditional variants are exempt (different component counts).
            _has_variant_models = args.enable_latent_pls or args.enable_latent_regime_conditional or args.enable_latent_autoencoder
            if not args.quick_mode and not _has_variant_models and len(_la_pca_ica_cols) != 64 and len(_la_pca_ica_cols) > 0:
                raise ValueError(
                    f"[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                    f"Production mode requires exactly 64 latent columns in parquet "
                    f"but found {len(_la_pca_ica_cols)} PCA/ICA columns in {_la_path}. "
                    f"First 5 columns: {_la_pca_ica_cols[:5]}. "
                    f"Run `python scripts/mine_latent_alphas.py` (without --quick-mode) "
                    f"to generate the 64D production artifacts, or use --quick-mode "
                    f"for smoke testing with _quick-suffixed artifacts."
                )

            # Filter by min IR if metrics JSON available
            _selected_cols = list(_la_cols_available)

            # GATE: LATENT_ALPHA_MINING_64D_20260617 — production mode requires
            # metrics JSON to exist.  Prevents silent use of stale/missing metrics.
            if not args.quick_mode and not _la_metrics_path.exists():
                raise ValueError(
                    f"[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                    f"Metrics JSON not found: {_la_metrics_path}. "
                    f"Production mode requires both the components parquet AND the "
                    f"metrics JSON.  Run `python scripts/mine_latent_alphas.py` "
                    f"(without --quick-mode) to generate the 64D production artifacts."
                )

            if _la_metrics_path.exists():
                with open(_la_metrics_path) as _f:
                    _metrics = json.load(_f)

                # GATE: LATENT_ALPHA_MINING_64D_20260617 — validate n_components
                # Production (non-quick) mode MUST use exactly 64 components
                # to satisfy the 64D feature space contract.
                # PLS and regime-conditional variants are exempt.
                _metrics_n_comp = _metrics.get("n_components")
                if not args.quick_mode and not _has_variant_models and _metrics_n_comp != 64:
                    raise ValueError(
                        f"[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                        f"Production mode requires n_components=64 in metrics JSON "
                        f"but found n_components={_metrics_n_comp} in {_la_metrics_path}. "
                        f"Run `python scripts/mine_latent_alphas.py` (without --quick-mode) "
                        f"to generate the 64D production artifacts, or use --quick-mode "
                        f"for smoke testing with _quick-suffixed artifacts."
                    )

                # GATE: LATENT_ALPHA_MINING_64D_20260617 — stale artifact check
                # Metrics n_components must match the PCA/ICA parquet column count.
                # For variant models (PLS, regime-conditional), check is relaxed.
                if not _has_variant_models and _metrics_n_comp is not None and _metrics_n_comp != len(_la_pca_ica_cols):
                    raise ValueError(
                        f"[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                        f"Stale artifact mismatch — metrics JSON reports "
                        f"n_components={_metrics_n_comp} but parquet has "
                        f"{len(_la_pca_ica_cols)} PCA/ICA latent columns. "
                        f"Metrics: {_la_metrics_path}, Parquet: {_la_path}. "
                        f"Re-run `python scripts/mine_latent_alphas.py` to "
                        f"regenerate matching artifacts."
                    )

                _comp_metrics = _metrics.get("component_metrics", {})
                _min_ir = args.latent_alpha_min_ir
                _ir_filtered = [
                    c for c in _selected_cols
                    if abs(_comp_metrics.get(c, {}).get("ir", 0.0)) >= _min_ir
                ]
                logger.info(
                    f"[LatentAlphas] After IR >= {_min_ir} filter: "
                    f"{len(_ir_filtered)} of {len(_selected_cols)} components"
                )
                _selected_cols = _ir_filtered

                # Apply top-N if specified
                if args.latent_alpha_top_n is not None:
                    _ranking = _metrics.get("ranking", [])
                    _top_names = [
                        r["component"]
                        for r in _ranking
                        if r["component"] in set(_selected_cols)
                    ][:args.latent_alpha_top_n]
                    _selected_cols = _top_names
                    logger.info(
                        f"[LatentAlphas] After top-N={args.latent_alpha_top_n}: "
                        f"{len(_selected_cols)} components"
                    )

            if len(_selected_cols) == 0:
                logger.warning(
                    "[LatentAlphas] No latent components passed filters. "
                    "Skipping injection."
                )
            else:
                # Merge on (ticker, date)
                _merge_cols = ["ticker", "date"] + _selected_cols
                _la_merge = _la_df[_merge_cols].copy()
                _n_before = len(df)
                df = df.merge(_la_merge, on=["ticker", "date"], how="left")
                assert len(df) == _n_before, (
                    f"Merge changed row count: {_n_before} -> {len(df)}"
                )
                # Fill NaN (unmatched dates) with 0
                df[_selected_cols] = df[_selected_cols].fillna(0.0)

                # GATE: LATENT_ALPHA_MINING_64D_20260617 — post-merge
                # zero-fill diagnostic.  Warns when latent columns are
                # predominantly zero, which signals a date-range mismatch
                # between the warehouse data and the latent parquet.
                _la_zero_pct = (
                    df[_selected_cols].eq(0.0).sum().sum()
                    / (len(df) * len(_selected_cols))
                    * 100
                )
                _la_nonzero_dates = df.loc[
                    df[_selected_cols].ne(0.0).any(axis=1), "date"
                ]
                _la_date_coverage = (
                    f"{_la_nonzero_dates.min().date()} to "
                    f"{_la_nonzero_dates.max().date()}"
                    if len(_la_nonzero_dates) > 0 else "NONE"
                )
                if _la_zero_pct > 50.0:
                    logger.warning(
                        "[LatentAlphas] WARNING: %.1f%% of injected latent "
                        "values are 0.0 — possible date-range mismatch. "
                        "Non-zero coverage: %s (%d/%d dates). "
                        "Check that START_DATE >= latent parquet min date.",
                        _la_zero_pct, _la_date_coverage,
                        _la_nonzero_dates.nunique(),
                        df["date"].nunique(),
                    )
                else:
                    logger.info(
                        "[LatentAlphas] Zero-fill check: %.1f%% zeros "
                        "(OK). Non-zero coverage: %s.",
                        _la_zero_pct, _la_date_coverage,
                    )

                latent_alpha_cols_injected = _selected_cols
                latent_alpha_evidence = {
                    "source_path": str(_la_path),
                    "n_components_available": len(_la_cols_available),
                    "n_components_injected": len(_selected_cols),
                    "injected_columns": _selected_cols,
                    "min_ir_threshold": args.latent_alpha_min_ir,
                    "n_rows_merged": _n_before,
                    "gate": "LATENT_ALPHA_MINING_64D_20260617",
                    "advanced_variants": {
                        "enable_pls": args.enable_latent_pls,
                        "enable_regime_conditional": args.enable_latent_regime_conditional,
                        "enable_autoencoder": args.enable_latent_autoencoder,
                        "n_pls_cols": len(_la_pls_cols),
                        "n_regime_cols": len(_la_regime_cols),
                        "n_ae_cols": len(_la_ae_cols),
                    },
                    # GATE: LATENT_ALPHA_MINING_64D_20260617 — zero-fill diagnostic
                    "zero_fill_pct": round(float(_la_zero_pct), 2),
                    "nonzero_date_coverage": _la_date_coverage,
                    "n_nonzero_dates": int(_la_nonzero_dates.nunique()),
                    "n_total_dates": int(df["date"].nunique()),
                    "auto_alignment_applied": _la_adjusted if 'args' in dir() else None,
                }

                logger.info(
                    f"[LatentAlphas] Merged {len(_selected_cols)} latent "
                    f"columns into df: {_selected_cols}"
                )
        logger.info("")
    
    # Step 2: Create walk-forward splits
    logger.info("Step 2: Creating walk-forward splits...")
    splits = loader.create_walk_forward_splits(
        df,
        n_folds=N_FOLDS,
        train_years=TRAIN_YEARS,
        test_years=TEST_YEARS,
    )
    
    logger.info(f"Created {len(splits)} valid folds")
    logger.info("")
    
    if len(splits) == 0:
        logger.error("No valid splits created. Exiting.")
        sys.exit(1)
    
    # GATE: CPCV_FOLD_EXPANSION_FIX1_20260614 — persist requested n_folds
    # separately from executed count so discrepancy is visible.
    n_folds_executed = len(splits)
    if n_folds_executed < N_FOLDS:
        logger.warning(
            f"[CPCV_FOLD_EXPANSION_FIX1] Requested {N_FOLDS} folds but only "
            f"{n_folds_executed} were executed (data range constraint)."
        )

    # GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615
    # Apply per-fold rolling universe selection (opt-in, disabled by default).
    rolling_universe_evidence = None
    if args.rolling_universe:
        logger.info("")
        logger.info("=" * 80)
        logger.info(
            "[RollingUniverse] GATE PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615: "
            "Applying PIT-safe per-fold rolling universe selection"
        )
        logger.info("=" * 80)

        rolling_splits = loader.apply_rolling_universe_to_splits(
            splits, top_n=TOP_N_SYMBOLS
        )
        rolling_universe_evidence = loader.get_rolling_universe_evidence()

        for ev in rolling_universe_evidence:
            logger.info(
                f"  Fold {ev['fold_id']}: selected {ev['n_selected']} symbols "
                f"(from {ev['n_candidates_after_filter']} filtered), "
                f"train_rows={ev['train_rows_after']}, "
                f"test_rows={ev['test_rows_after']}, "
                f"test_subset_of_train={ev['test_symbols_subset_of_train']}"
            )

        splits = [(t, te) for t, te, _ in rolling_splits]

        logger.info(
            f"[RollingUniverse] Applied to {len(splits)} folds. "
            f"All test symbols are subsets of train-selected symbols."
        )
        logger.info("")

    # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615
    # Build per-rebalance dynamic universe schedule (opt-in, disabled by default).
    dynamic_universe_schedule = None
    dynamic_universe_evidence = None
    if args.dynamic_universe:
        from phase35_data_loader import DynamicUniverseSelector

        _dyn_top_n = (
            args.dynamic_universe_top_n
            if args.dynamic_universe_top_n is not None
            else TOP_N_SYMBOLS
        )

        logger.info("")
        logger.info("=" * 80)
        logger.info(
            "[DynamicUniverse] GATE DYNAMIC_REBALANCE_UNIVERSE_20260615: "
            "Building PIT-safe per-rebalance dynamic universe schedule"
        )
        logger.info(
            f"  lookback_days={args.dynamic_universe_lookback_days}, "
            f"rebalance_days={args.dynamic_universe_rebalance_days}, "
            f"top_n={_dyn_top_n}"
        )
        logger.info("=" * 80)

        selector = DynamicUniverseSelector(
            lookback_days=args.dynamic_universe_lookback_days,
            rebalance_days=args.dynamic_universe_rebalance_days,
            top_n=_dyn_top_n,
            min_history_days=loader.min_history_days,
        )

        dynamic_universe_schedule, dynamic_universe_evidence = (
            selector.build_dynamic_universe_schedule(df)
        )

        for ev in dynamic_universe_evidence:
            logger.info(
                f"  Rebalance {ev['rebalance_date']}: "
                f"selected {ev['n_selected']} symbols "
                f"(window {ev['selection_window_start']} to "
                f"{ev['selection_window_end_exclusive']}), "
                f"selection_end_before_rebalance="
                f"{ev['selection_end_before_rebalance']}, "
                f"turnover={ev['turnover_from_previous']}"
            )

        logger.info(
            f"[DynamicUniverse] Built schedule with "
            f"{len(dynamic_universe_schedule)} rebalance dates. "
            f"All selection_end < rebalance_date (PIT-safe)."
        )
        logger.info("")

    # Step 3: Run walk-forward backtest
    logger.info("Step 3: Running walk-forward backtest...")
    engine = Phase35WalkForwardEngine(
        alpha_module=phase34_microstructure_alphas,
        min_ic_threshold=MIN_IC_THRESHOLD,
        top_n_alphas=TOP_N_ALPHAS,
        top_n_stocks=STAGE2_TOP_N_STOCKS,
        rebalance_freq=STAGE2_REBALANCE_FREQ,
        sector_cap_pct=STAGE2_SECTOR_CAP_PCT,
        use_xgboost=args.use_xgboost,
        enable_multi_model_ensemble=args.enable_multi_model_ensemble,
        cost_aware=cost_aware,
        cost_per_turnover=cost_per_turnover,
        drawdown_control=args.drawdown_control,
        drawdown_threshold=args.drawdown_threshold,
        # GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616
        drawdown_re_entry_enabled=args.drawdown_re_entry,
        drawdown_cooldown_days=args.drawdown_cooldown_days,
        drawdown_hwm_reset=not args.drawdown_no_hwm_reset,
        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
        drawdown_adaptive_re_entry=args.drawdown_adaptive_re_entry,
        drawdown_adaptive_bear_threshold=args.drawdown_adaptive_bear_threshold,
        drawdown_adaptive_vol_window=args.drawdown_adaptive_vol_window,
        drawdown_adaptive_vol_multiplier=args.drawdown_adaptive_vol_multiplier,
        drawdown_adaptive_max_cooldown=args.drawdown_adaptive_max_cooldown,
        strategy=args.strategy,
        initial_capital=args.initial_capital,
        enable_evolved=args.enable_evolved,
        evolved_blend_weight=args.evolved_blend_weight,
        multi_horizon_blend=args.multi_horizon_blend,
        blend_horizons=args.blend_horizons_list,
        blend_weight_method=args.blend_weight_method,
        p10_gate_mode=args.p10_gate_mode,
        p10_gate_min_pass=args.p10_gate_min_pass,
        p10_gate_allow_fallback_candidates=args.p10_gate_allow_fallback_candidates,
        risk_adjusted_alpha_selection=args.risk_adjusted_alpha_selection,
        risk_adjusted_preset=args.risk_adjusted_preset,
        portfolio_guard_enabled=args.portfolio_guard_enabled,
        portfolio_guard_tolerance=args.portfolio_guard_tolerance,
        # GATE: RECOVERY_SELECTOR_PHASE35_WIRING_20260614
        research_pool_mode=args.research_pool_mode,
        # GATE: FORMULAIC_ALPHA_ADAPTER_20260614
        enable_formulaic_alphas=args.enable_formulaic_alphas,
        formulaic_alpha_set=args.formulaic_alpha_set,
        # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614
        formulaic_winner_guard=args.formulaic_winner_guard,
        # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615
        regime_routing_enabled=args.enable_regime_routing,
        regime_routing_min_train_days=args.regime_routing_min_train_days,
        regime_routing_min_ic=args.regime_routing_min_ic,
        # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615
        dynamic_universe_schedule=dynamic_universe_schedule,
        # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615
        diversified_basket_enabled=args.diversified_basket,
        basket_max_per_cluster=args.basket_max_per_cluster,
        basket_corr_threshold=args.basket_corr_threshold,
        basket_redundancy_penalty=args.basket_redundancy_penalty,
        basket_min_ic=args.basket_min_ic,
        # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615
        enable_nonredundant_alphas=args.enable_nonredundant_alphas,
        nonredundant_alpha_set=args.nonredundant_alpha_set,
        nonredundant_alpha_max_candidates=args.nonredundant_alpha_max_candidates,
        # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615
        enable_automated_oos_bundle=args.enable_automated_oos_bundle,
        automated_oos_bundle_name=args.automated_oos_bundle_name,
        # GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
        enable_auto_winner_guard_allowlist=args.enable_auto_winner_guard_allowlist,
        # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616
        enable_oos_stability_filter=args.enable_oos_stability_filter,
        stability_min_icir=args.stability_min_icir,
        stability_min_sign_consistency=args.stability_min_sign_consistency,
        stability_decay_penalty_factor=args.stability_decay_penalty_factor,
        # GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616
        risk_sizing_overlay_enabled=args.risk_sizing_overlay,
        risk_sizing_inverse_vol=args.risk_sizing_inverse_vol,
        risk_sizing_inverse_vol_window=args.risk_sizing_inverse_vol_window,
        risk_sizing_inverse_vol_floor=args.risk_sizing_inverse_vol_floor,
        risk_sizing_confidence=args.risk_sizing_confidence,
        risk_sizing_confidence_window=args.risk_sizing_confidence_window,
        risk_sizing_confidence_min_ic=args.risk_sizing_confidence_min_ic,
        risk_sizing_confidence_max_scale=args.risk_sizing_confidence_max_scale,
        risk_sizing_confidence_min_scale=args.risk_sizing_confidence_min_scale,
        # GATE: REGIME_CONDITIONAL_SIZING_20260616 — regime sizing config
        risk_sizing_regime=args.risk_sizing_regime,
        risk_sizing_regime_scale=args.risk_sizing_regime_scale,
        risk_sizing_regime_ma_window=args.risk_sizing_regime_ma_window,
        risk_sizing_regime_vol_window=args.risk_sizing_regime_vol_window,
        risk_sizing_regime_vol_median_window=args.risk_sizing_regime_vol_median_window,
        risk_sizing_regime_window=args.risk_sizing_regime_window,
        risk_sizing_regime_mode=args.risk_sizing_regime_mode,
        risk_sizing_regime_auto_optimize=args.risk_sizing_regime_auto_optimize,
        risk_sizing_regime_refit_stride=args.risk_sizing_regime_refit_stride,
    )
    
    alpha_cols = list(phase34_microstructure_alphas.PHASE34_ALPHA_COLUMNS)
    if args.enable_vn_specific_alphas:
        vn_cols = [
            "alpha_vn_amihud_liq_reversal",
            "alpha_vn_illiq_regime_penalty",
            "alpha_vn_volume_shock_reversal",
            "alpha_vn_turnover_exhaustion",
            "alpha_vn_bollinger_snapback",
            "alpha_vn_rsi_divergence_reversal",
            "alpha_vn_sector_neutral_residual_reversion",
            "alpha_vn_close_location_reversion",
            "alpha_vn_foreign_flow_persistence",
            "alpha_vn_foreign_absorption_reversal",
            "alpha_vn_foreign_room_squeeze",
            "alpha_vn_limit_lock_continuation",
            "alpha_limit_lock_streak",
            "alpha_t2_momentum_adj",
            "alpha_penny_trap_score",
            "alpha_smart_money_lite",
            "alpha_vn_t2_momentum_diff",
            "alpha_vn_penny_trap_risk",
            "alpha_liquidity_quality_score",
            "alpha_vn_limit_unlock_exhaustion",
            "alpha_vn_t2_settlement_supply_overhang",
            "alpha_vn_t2_cash_recycling_bounce",
            "alpha_vn_001_post_settlement_momentum",
            "alpha_vn_002_limit_band_reversion",
            "alpha_vn_003_foreign_flow_divergence",
            "alpha_vn_004_intraday_persistence",
            "alpha_vn_005_liquidity_adjusted_reversal",
        ]
        alpha_cols.extend(vn_cols)
        logger.info(
            f"[VNSpecificAlphas] Added {len(vn_cols)} VN-specific alpha columns"
        )
    # GATE: FORMULAIC_ALPHA_ADAPTER_20260614 — append formulaic alpha columns
    if args.enable_formulaic_alphas:
        from omega.quant.alpha.formulaic_alphas import get_formulaic_alpha_columns
        fml_cols = list(get_formulaic_alpha_columns(args.formulaic_alpha_set))
        alpha_cols.extend(fml_cols)
        logger.info(
            f"[FormulaicAlphas] Added {len(fml_cols)} formulaic alpha columns: {fml_cols}"
        )
    # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615 — append nonredundant alpha columns
    if args.enable_nonredundant_alphas:
        from omega.quant.alpha.nonredundant_alphas import get_nonredundant_alpha_columns
        nr_cols = list(get_nonredundant_alpha_columns(args.nonredundant_alpha_set))
        if args.nonredundant_alpha_max_candidates is not None:
            nr_cols = nr_cols[:args.nonredundant_alpha_max_candidates]
        alpha_cols.extend(nr_cols)
        logger.info(
            f"[NonredundantAlphas] Added {len(nr_cols)} nonredundant alpha columns: {nr_cols}"
        )
    # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615 — append bundle columns
    if args.enable_automated_oos_bundle:
        from omega.quant.alpha.phase35 import AUTO_TOP5_REAL_IC_BUNDLE
        bundle_alphas = AUTO_TOP5_REAL_IC_BUNDLE.get(
            args.automated_oos_bundle_name, []
        )
        alpha_cols.extend(bundle_alphas)
        logger.info(
            f"[AutoOOSBundle] Added {len(bundle_alphas)} automated OOS "
            f"bundle columns: {bundle_alphas}"
        )
    # GATE: LATENT_ALPHA_MINING_64D_20260617 — append latent alpha columns
    if latent_alpha_cols_injected:
        alpha_cols.extend(latent_alpha_cols_injected)
        logger.info(
            f"[LatentAlphas] Added {len(latent_alpha_cols_injected)} latent "
            f"alpha columns: {latent_alpha_cols_injected}"
        )
    return_col = f'fwd_ret_{RETURN_HORIZON}'
    
    result = engine.run_walk_forward(splits, alpha_cols, return_col=return_col)
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("BACKTEST RESULTS")
    logger.info("=" * 80)
    logger.info(result.summary())
    logger.info("")
    
    # ======================================================================
    # GATE: RECOVERY_SELECTOR_PHASE35_WIRING_20260614
    # Post-hoc recovery pool selector analysis (research-only, opt-in).
    # Computes recovery diagnostics from OOS fold-level ICs (PIT-safe),
    # applies filter, computes selector verdict.
    # Default mode='full' skips analysis entirely — no behavior change.
    # ======================================================================
    recovery_pool_evidence = None
    if args.research_pool_mode != "full":
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            compute_alpha_recovery_diagnostics,
            filter_alphas_by_recovery_mode,
            compute_selector_ready_verdict,
            compute_icir,
            compute_positive_fold_rate,
        )

        logger.info("")
        logger.info("=" * 80)
        logger.info(
            f"[RecoveryPool] Research-only analysis: mode={args.research_pool_mode}"
        )
        logger.info("=" * 80)

        # Build alpha_fold_ics: {alpha_name: [ic_fold1, ic_fold2, ...]}
        alpha_fold_ics: dict[str, list[float]] = {}
        for m in result.fold_metrics:
            for alpha_name, ic_val in m.alpha_ics.items():
                alpha_fold_ics.setdefault(alpha_name, []).append(ic_val)

        # Build fold_details for regime-conditioned IC computation
        fold_details_list = []
        for m in result.fold_metrics:
            fold_details_list.append({
                "portfolio_sharpe": m.portfolio_sharpe,
                "portfolio_ic": m.portfolio_ic,
                "alpha_ics": m.alpha_ics,
            })

        # Compute recovery diagnostics
        recovery_report = compute_alpha_recovery_diagnostics(
            fold_details=fold_details_list,
            alpha_fold_ics=alpha_fold_ics,
        )

        # Apply filter
        full_pool = list(alpha_fold_ics.keys())
        filtered_pool = filter_alphas_by_recovery_mode(
            full_pool, recovery_report, mode=args.research_pool_mode,
        )
        excluded_pool = [a for a in full_pool if a not in filtered_pool]

        # Compute full-pool metrics
        full_ics_flat = []
        for alpha_name, ics in alpha_fold_ics.items():
            full_ics_flat.extend(ics)
        full_mean_ic = sum(full_ics_flat) / len(full_ics_flat) if full_ics_flat else 0.0
        # Per-fold mean ICs for full pool
        n_folds = len(result.fold_metrics)
        full_per_fold_ics = []
        for i in range(n_folds):
            fold_ic_vals = [
                result.fold_metrics[i].alpha_ics.get(a, 0.0)
                for a in full_pool
            ]
            full_per_fold_ics.append(
                sum(fold_ic_vals) / len(fold_ic_vals) if fold_ic_vals else 0.0
            )
        full_pool_mean_fold_ic = (
            sum(full_per_fold_ics) / len(full_per_fold_ics)
            if full_per_fold_ics else 0.0
        )
        full_pool_pos_fold_rate = compute_positive_fold_rate(full_per_fold_ics)

        # Compute recovery-pool metrics
        recovery_per_fold_ics = []
        for i in range(n_folds):
            fold_ic_vals = [
                result.fold_metrics[i].alpha_ics.get(a, 0.0)
                for a in filtered_pool
            ]
            recovery_per_fold_ics.append(
                sum(fold_ic_vals) / len(fold_ic_vals) if fold_ic_vals else 0.0
            )
        recovery_pool_mean_fold_ic = (
            sum(recovery_per_fold_ics) / len(recovery_per_fold_ics)
            if recovery_per_fold_ics else 0.0
        )
        recovery_pool_pos_fold_rate = compute_positive_fold_rate(
            recovery_per_fold_ics
        )

        # Compute selector verdict
        selector_verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=full_pool_mean_fold_ic,
            full_pool_positive_fold_rate=full_pool_pos_fold_rate,
            recovery_pool_mean_ic=recovery_pool_mean_fold_ic,
            recovery_pool_positive_fold_rate=recovery_pool_pos_fold_rate,
        )

        recovery_pool_evidence = {
            "gate": "RECOVERY_SELECTOR_PHASE35_WIRING_20260614",
            "research_pool_mode": args.research_pool_mode,
            "full_pool_alphas": full_pool,
            "selected_alphas": filtered_pool,
            "excluded_alphas": excluded_pool,
            "n_selected": len(filtered_pool),
            "n_excluded": len(excluded_pool),
            "full_pool_mean_fold_ic": round(full_pool_mean_fold_ic, 6),
            "full_pool_positive_fold_rate": round(full_pool_pos_fold_rate, 4),
            "recovery_pool_mean_fold_ic": round(recovery_pool_mean_fold_ic, 6),
            "recovery_pool_positive_fold_rate": round(
                recovery_pool_pos_fold_rate, 4
            ),
            "ic_delta": round(
                recovery_pool_mean_fold_ic - full_pool_mean_fold_ic, 6
            ),
            "fold_rate_delta": round(
                recovery_pool_pos_fold_rate - full_pool_pos_fold_rate, 4
            ),
            "selector_verdict": selector_verdict,
            "recovery_classifications": {
                "recoverable": recovery_report.recoverable_candidates,
                "research_only": recovery_report.research_only,
                "confirmed_retire": recovery_report.confirmed_retire,
            },
            "pit_safe": True,
        }

        logger.info(
            f"[RecoveryPool] Full pool: {len(full_pool)} alphas, "
            f"mean_fold_IC={full_pool_mean_fold_ic:.4f}, "
            f"pos_fold_rate={full_pool_pos_fold_rate:.2%}"
        )
        logger.info(
            f"[RecoveryPool] Filtered pool: {len(filtered_pool)} alphas, "
            f"mean_fold_IC={recovery_pool_mean_fold_ic:.4f}, "
            f"pos_fold_rate={recovery_pool_pos_fold_rate:.2%}"
        )
        logger.info(
            f"[RecoveryPool] Excluded: {excluded_pool}"
        )
        logger.info(
            f"[RecoveryPool] Selector verdict: {selector_verdict}"
        )
        logger.info("")
    
    # Step 4: Save results
    logger.info("Step 4: Saving results...")
    
    output_dir = Path(__file__).parent.parent / "data" / "phase35_results"
    output_dir.mkdir(exist_ok=True)
    
    # Save detailed results as JSON
    results_dict = {
        "config": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "top_n_symbols": TOP_N_SYMBOLS,
            "n_folds": N_FOLDS,
            "n_folds_executed": n_folds_executed,
            "train_years": TRAIN_YEARS,
            "test_years": TEST_YEARS,
            "min_ic_threshold": MIN_IC_THRESHOLD,
            "top_n_alphas": TOP_N_ALPHAS,
            "return_horizon": RETURN_HORIZON,
            "stage2_top_n_stocks": STAGE2_TOP_N_STOCKS,
            "stage2_rebalance_freq": STAGE2_REBALANCE_FREQ,
            "stage2_sector_cap_pct": STAGE2_SECTOR_CAP_PCT,
            "use_xgboost": args.use_xgboost,
            "enable_multi_model_ensemble": args.enable_multi_model_ensemble,
            "initial_capital": args.initial_capital,
            "strategy": args.strategy,
            "slippage_bps": args.slippage_bps,
            "commission_bps": args.commission_bps,
            "quick_mode": args.quick_mode,
            "drawdown_control": args.drawdown_control,
            "drawdown_threshold": args.drawdown_threshold,
            "enable_evolved": args.enable_evolved,
            "evolved_blend_weight": args.evolved_blend_weight,
            "multi_horizon_blend": args.multi_horizon_blend,
            "blend_horizons": args.blend_horizons,
            "blend_weight_method": args.blend_weight_method,
            "p10_gate_mode": args.p10_gate_mode,
            "p10_gate_min_pass": args.p10_gate_min_pass,
            "p10_gate_allow_fallback_candidates": args.p10_gate_allow_fallback_candidates,
            "risk_adjusted_alpha_selection": args.risk_adjusted_alpha_selection,
            "risk_adjusted_preset": args.risk_adjusted_preset,
            "portfolio_guard_enabled": args.portfolio_guard_enabled,
            "portfolio_guard_tolerance": args.portfolio_guard_tolerance,
            # GATE: RECOVERY_SELECTOR_PHASE35_WIRING_20260614
            "research_pool_mode": args.research_pool_mode,
            # GATE: FORMULAIC_ALPHA_ADAPTER_20260614
            "enable_formulaic_alphas": args.enable_formulaic_alphas,
            "formulaic_alpha_set": args.formulaic_alpha_set,
            # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614
            "formulaic_winner_guard": args.formulaic_winner_guard,
            # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615
            "regime_routing_enabled": args.enable_regime_routing,
            "regime_routing_min_train_days": args.regime_routing_min_train_days,
            "regime_routing_min_ic": args.regime_routing_min_ic,
            # GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615
            "rolling_universe_enabled": args.rolling_universe,
            # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615
            "dynamic_universe_enabled": args.dynamic_universe,
            "dynamic_universe_lookback_days": args.dynamic_universe_lookback_days,
            "dynamic_universe_rebalance_days": args.dynamic_universe_rebalance_days,
            "dynamic_universe_top_n": args.dynamic_universe_top_n,
            # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615
            "diversified_basket_enabled": args.diversified_basket,
            "basket_max_per_cluster": args.basket_max_per_cluster,
            "basket_corr_threshold": args.basket_corr_threshold,
            "basket_redundancy_penalty": args.basket_redundancy_penalty,
            "basket_min_ic": args.basket_min_ic,
            # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615
            "enable_nonredundant_alphas": args.enable_nonredundant_alphas,
            "nonredundant_alpha_set": args.nonredundant_alpha_set,
            "nonredundant_alpha_max_candidates": args.nonredundant_alpha_max_candidates,
            # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615
            "enable_automated_oos_bundle": args.enable_automated_oos_bundle,
            "automated_oos_bundle_name": args.automated_oos_bundle_name,
            # GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
            "enable_auto_winner_guard_allowlist": args.enable_auto_winner_guard_allowlist,
            # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616
            "enable_oos_stability_filter": args.enable_oos_stability_filter,
            "stability_min_icir": args.stability_min_icir,
            "stability_min_sign_consistency": args.stability_min_sign_consistency,
            "stability_decay_penalty_factor": args.stability_decay_penalty_factor,
            # GATE: CPCV_FOLD_EXPANSION_20260614 — persist fold expansion config
            "cpcv_fold_expansion_n_folds": N_FOLDS,
            "cpcv_fold_expansion_train_years": TRAIN_YEARS,
            "cpcv_fold_expansion_test_years": TEST_YEARS,
            "cpcv_fold_expansion_top_n_symbols": TOP_N_SYMBOLS,
            "cpcv_fold_expansion_output_tag": args.output_tag,
            # GATE: DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614
            "data_cleaning_enabled": data_cleaning_enabled,
            "normalization_mode": normalization_mode,
            "data_hygiene_evidence": data_hygiene_evidence,
        },
        "summary": {
            "avg_portfolio_ic": result.avg_portfolio_ic,
            "avg_portfolio_sharpe": result.avg_portfolio_sharpe,
            "avg_portfolio_max_dd": result.avg_portfolio_max_dd,
            "avg_portfolio_pnl_vnd": getattr(result, "avg_portfolio_pnl_vnd", 0.0),
            "total_folds": result.total_folds,
            "n_folds_requested": N_FOLDS,
        },
        "alpha_ics": result.avg_ic_by_alpha,
        "fold_details": [serialize_fold_details(m) for m in result.fold_metrics],
        # GATE: RECOVERY_SELECTOR_PHASE35_WIRING_20260614
        "recovery_pool_evidence": recovery_pool_evidence,
        # GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615
        "rolling_universe_evidence": rolling_universe_evidence,
        # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615
        "dynamic_universe_evidence": dynamic_universe_evidence,
        # GATE: LATENT_ALPHA_MINING_64D_20260617
        "latent_alpha_evidence": latent_alpha_evidence,
        "timestamp": datetime.now().isoformat(),
    }
    
    # GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615 — suffix reflects XGBoost state
    result_suffix = "multi_model_ensemble" if args.enable_multi_model_ensemble else ("xgboost" if args.use_xgboost else "baseline")
    # GATE: CPCV_FOLD_EXPANSION_20260614 — output-tag changes filenames to avoid overwrite
    if args.output_tag:
        result_suffix = f"{args.output_tag}_{result_suffix}"
    json_path = output_dir / f"phase35_backtest_results_{result_suffix}.json"
    with open(json_path, 'w') as f:
        json.dump(results_dict, f, indent=2)
    
    logger.info(f"Results saved to: {json_path}")
    
    # Save summary as text
    summary_path = output_dir / f"phase35_backtest_summary_{result_suffix}.txt"
    with open(summary_path, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("Phase 3.5 Walk-Forward Backtest Results\n")
        f.write("=" * 80 + "\n\n")
        f.write(result.summary())
        f.write("\n\n")
        f.write("Fold Details:\n")
        f.write("-" * 80 + "\n")
        for m in result.fold_metrics:
            f.write(f"\nFold {m.fold_id}:\n")
            f.write(f"  Train: {m.train_start} to {m.train_end} ({m.n_train_samples:,} samples)\n")
            f.write(f"  Test:  {m.test_start} to {m.test_end} ({m.n_test_samples:,} samples)\n")
            f.write(f"  Portfolio IC: {m.portfolio_ic:.4f}\n")
            f.write(f"  Portfolio Sharpe: {m.portfolio_sharpe:.4f}\n")
            f.write(f"  Portfolio Max DD: {m.portfolio_max_dd:.2%}\n")
            f.write(f"  Portfolio Total Return: {m.portfolio_total_return:.2%}\n")
    
    logger.info(f"Summary saved to: {summary_path}")
    logger.info("")
    logger.info("=" * 80)
    logger.info("Phase 3.5 Walk-Forward Backtest Complete!")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
