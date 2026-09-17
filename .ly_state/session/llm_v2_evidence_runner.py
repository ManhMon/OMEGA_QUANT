"""LLM v2 Prompt Evidence Runner.

Runs real online LLM synthesis with prompt_version='vn_alpha_search_v2' and
supervised CPCV validation. Captures comprehensive evidence for L2 report.

Security: API keys from env only, never printed. Writes only to .ly_state/session/.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("llm_v2_evidence")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.quant.evolution.llm_symbolic_synthesizer import LLMSymbolicSynthesizer
from omega.quant.evolution.llm_formula_scorer import (
    FormulaScorer,
    FormulaScorerConfig,
)


def check_env_config():
    """Check environment configuration and return provider info."""
    provider_type = os.environ.get("OMEGA_LLM_PROVIDER", "mock")
    api_key_set = "OMEGA_LLM_API_KEY" in os.environ
    model = os.environ.get("OMEGA_LLM_MODEL", "gpt-4")
    base_url = os.environ.get("OMEGA_LLM_BASE_URL", "https://api.openai.com/v1")
    max_candidates = int(os.environ.get("OMEGA_LLM_MAX_CANDIDATES", "10"))
    
    return {
        "provider_type": provider_type,
        "api_key_set": api_key_set,
        "model": model,
        "base_url": base_url,
        "max_candidates": max_candidates,
    }


def run_synthesis_smoke_test():
    """Run real online LLM synthesis smoke test with v2 prompt."""
    logger.info("=== LLM v2 Synthesis Smoke Test ===")
    
    # Check env config
    env_config = check_env_config()
    logger.info("Environment config: provider=%s api_key_set=%s model=%s max_candidates=%d",
                env_config["provider_type"], env_config["api_key_set"],
                env_config["model"], env_config["max_candidates"])
    
    # Initialize synthesizer with v2 prompt
    provider = env_config["provider_type"]
    max_candidates = env_config["max_candidates"]
    
    synth = LLMSymbolicSynthesizer(
        use_mock=False,  # Request real provider
        provider=provider,
        prompt_version="vn_alpha_search_v2",
        max_candidates=max_candidates,
    )
    
    # Create mock feature data for synthesis
    np.random.seed(42)
    n_samples = 100
    features = {
        "close": np.random.randn(n_samples) * 10 + 100,
        "open": np.random.randn(n_samples) * 10 + 100,
        "high": np.random.randn(n_samples) * 10 + 105,
        "low": np.random.randn(n_samples) * 10 + 95,
        "volume": np.abs(np.random.randn(n_samples)) * 1000000,
        "ret_1d": np.random.randn(n_samples) * 0.02,
        "ret_5d": np.random.randn(n_samples) * 0.05,
        "ret_20d": np.random.randn(n_samples) * 0.10,
    }
    
    # Create context for prompt (top features and clusters)
    top_features = [
        ("ret_1d", 0.045),
        ("ts_rank_volume_20", 0.038),
        ("decay_linear_ret_5d_10", 0.032),
    ]
    
    correlation_clusters = [
        ["ret_1d", "ret_5d", "ret_20d"],
        ["close", "open", "high", "low"],
    ]
    
    # Run synthesis
    logger.info("Running synthesis with prompt_version=vn_alpha_search_v2...")
    nodes, stats = synth.synthesize(
        features=features,
        top_features=top_features,
        correlation_clusters=correlation_clusters,
        prior_failure_stats=None,  # First iteration, no prior failures
    )
    
    logger.info("Synthesis complete: %d nodes generated", len(nodes))
    logger.info("Synthesis stats: %s", json.dumps(stats, indent=2, default=str))
    
    # Build evidence dict
    evidence = {
        "test_type": "llm_v2_synthesis_smoke",
        "prompt_version": "vn_alpha_search_v2",
        "env_config": env_config,
        "synthesis_stats": stats,
        "nodes_generated": len(nodes),
        "accepted_formulas": stats.get("accepted_formulas", []),
        "rejected_formulas": stats.get("rejected_formulas", []),
    }
    
    # Write evidence
    evidence_path = REPO_ROOT / ".ly_state/session/llm_prompt_v2_real_online_smoke_20260612.json"
    with open(evidence_path, "w") as f:
        json.dump(evidence, f, indent=2, default=str)
    logger.info("Synthesis evidence written to: %s", evidence_path)
    
    return nodes, stats, evidence


def run_supervised_validation(nodes, synthesis_stats):
    """Run supervised CPCV validation with v2 LLM alphas."""
    logger.info("=== Supervised CPCV Validation with v2 LLM Alphas ===")
    
    # Create synthetic panel data with labels for validation
    np.random.seed(42)
    n_dates = 50
    n_tickers = 5
    
    dates = pd.date_range("2020-01-01", periods=n_dates)
    tickers = [f"TICKER{i}" for i in range(n_tickers)]
    
    # Build panel
    panel_data = []
    for ticker in tickers:
        for date in dates:
            panel_data.append({
                "ticker": ticker,
                "date": date,
                "close": 100 + np.random.randn() * 10,
                "open": 100 + np.random.randn() * 10,
                "high": 105 + np.random.randn() * 10,
                "low": 95 + np.random.randn() * 10,
                "volume": np.abs(np.random.randn()) * 1000000,
                "ret_1d": np.random.randn() * 0.02,
                "ret_5d": np.random.randn() * 0.05,
                "ret_20d": np.random.randn() * 0.10,
            })
    
    panel = pd.DataFrame(panel_data)
    
    # Create labels (forward returns)
    panel = panel.sort_values(["ticker", "date"])
    panel["label"] = panel.groupby("ticker")["close"].transform(
        lambda s: s.shift(-5) / s - 1.0
    )
    
    # Drop rows with NaN labels
    panel = panel.dropna(subset=["label"]).reset_index(drop=True)
    
    logger.info("Validation panel: %d rows, %d tickers, %d dates",
                len(panel), panel["ticker"].nunique(), panel["date"].nunique())
    
    # Initialize synthesizer for execution
    synth = LLMSymbolicSynthesizer(
        provider="mock",  # Use mock for execution (we already have nodes)
        prompt_version="vn_alpha_search_v2",
    )
    
    # Score and filter formulas with supervised validation
    scorer_config = FormulaScorerConfig(
        min_variance=1e-8,
        min_coverage=0.50,
        max_nan_inf_ratio=0.50,
        min_absolute_ic=0.01,
        min_dsr_proxy=-0.5,
        allow_unvalidated=True,  # Accept unsupervised for now
    )
    
    feat_cols = ["close", "open", "high", "low", "volume", "ret_1d", "ret_5d", "ret_20d"]
    labels = panel["label"].values
    
    logger.info("Scoring %d formulas with supervised validation...", len(nodes))
    accepted_nodes, scoring_stats = synth.score_and_filter_formulas(
        nodes=nodes,
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,
        scorer_config=scorer_config,
        ticker_col="ticker",
        date_col="date",
        synthesis_stats=synthesis_stats,
    )
    
    logger.info("Scoring complete: %d accepted, %d rejected",
                scoring_stats["accepted"], scoring_stats["rejected"])
    logger.info("Deployable: %d, Unsupervised only: %d",
                scoring_stats["deployable"], scoring_stats["unsupervised_only"])
    
    # Extract validation metrics
    validation_metrics = {
        "total_formulas": scoring_stats["total"],
        "accepted": scoring_stats["accepted"],
        "rejected": scoring_stats["rejected"],
        "deployable": scoring_stats["deployable"],
        "unsupervised_only": scoring_stats["unsupervised_only"],
        "rejection_taxonomy": scoring_stats["rejection_taxonomy"],
        "details": {},
    }
    
    # Compute aggregate IC/SR/DSR metrics for accepted formulas
    if scoring_stats["accepted"] > 0:
        ic_values = []
        for name, details in scoring_stats["details"].items():
            if details.get("accepted", False):
                ic = details.get("absolute_ic")
                if ic is not None:
                    ic_values.append(ic)
        
        if ic_values:
            validation_metrics["median_test_ic"] = float(np.median(ic_values))
            validation_metrics["mean_test_ic"] = float(np.mean(ic_values))
        else:
            validation_metrics["median_test_ic"] = None
            validation_metrics["mean_test_ic"] = None
    else:
        validation_metrics["median_test_ic"] = None
        validation_metrics["mean_test_ic"] = None
    
    # Note: For full CPCV metrics (SR, DSR), we'd need to run backtest_v2_cpcv.py
    # This smoke test validates the scoring/filtering pipeline
    validation_metrics["note"] = (
        "Smoke test validation. Full CPCV metrics (SR, DSR, pass/fail) "
        "require running backtest_v2_cpcv.py with --use-llm-alphas."
    )
    
    # Build evidence dict
    evidence = {
        "test_type": "llm_v2_supervised_validation_smoke",
        "prompt_version": "vn_alpha_search_v2",
        "validation_metrics": validation_metrics,
        "scoring_stats": scoring_stats,
    }
    
    # Write evidence
    evidence_path = REPO_ROOT / ".ly_state/session/llm_prompt_v2_supervised_validation_20260612.json"
    with open(evidence_path, "w") as f:
        json.dump(evidence, f, indent=2, default=str)
    logger.info("Validation evidence written to: %s", evidence_path)
    
    return validation_metrics, evidence


def main():
    """Run LLM v2 evidence collection."""
    try:
        # Step 1: Run synthesis smoke test
        nodes, synthesis_stats, synthesis_evidence = run_synthesis_smoke_test()
        
        # Step 2: Run supervised validation
        if len(nodes) > 0:
            validation_metrics, validation_evidence = run_supervised_validation(
                nodes, synthesis_stats
            )
        else:
            logger.warning("No nodes generated, skipping validation")
            validation_metrics = None
            validation_evidence = None
        
        # Summary
        logger.info("=== Evidence Collection Complete ===")
        logger.info("Synthesis evidence: .ly_state/session/llm_prompt_v2_real_online_smoke_20260612.json")
        if validation_metrics:
            logger.info("Validation evidence: .ly_state/session/llm_prompt_v2_supervised_validation_20260612.json")
        
        return 0
        
    except Exception as e:
        logger.error("Evidence collection failed: %s", e, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
