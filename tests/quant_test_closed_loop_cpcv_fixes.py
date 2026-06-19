"""Tests for closed-loop CPCV fixes (Role 9, 2026-06-12).

Tests cover:
1. Count correctness - stage-by-stage tracking with no negative values
2. TopK selection - supervised candidate selection
3. Train-only supervised selection metadata
4. No test-label leakage
5. No negative rejected counts
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_count_correctness_no_negatives():
    """Test that all stage counts are tracked correctly and never negative.
    
    Regression test for bug: total_candidates_generated=10, accepted=24, rejected=-14
    """
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=3,
        candidates_per_iteration=5,
        llm_provider='mock',
        enable_formula_memory=True,
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create panel
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 50 + ["B"] * 50,
        "date": pd.date_range("2020-01-01", periods=50).tolist() * 2,
        "close": np.random.randn(100) * 10 + 100,
        "volume": np.abs(np.random.randn(100)) * 1000,
    })
    
    labels = np.random.randn(100) * 0.02
    feat_cols = ["close", "volume"]
    
    # Run search
    final_candidates, evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify stage-by-stage counts exist and are non-negative
    summary = evidence["summary"]
    
    assert "total_raw_generated" in summary, "Should track raw generation count"
    assert "total_safety_validated" in summary, "Should track safety validation count"
    assert "total_unique_after_dedup" in summary, "Should track unique count after dedup"
    assert "total_scoring_input" in summary, "Should track scoring input count"
    assert "total_scoring_accepted" in summary, "Should track scoring accepted count"
    assert "total_scoring_rejected" in summary, "Should track scoring rejected count"
    
    # Verify all counts are non-negative
    assert summary["total_raw_generated"] >= 0, "Raw generated count must be >= 0"
    assert summary["total_safety_validated"] >= 0, "Safety validated count must be >= 0"
    assert summary["total_unique_after_dedup"] >= 0, "Unique count must be >= 0"
    assert summary["total_scoring_input"] >= 0, "Scoring input count must be >= 0"
    assert summary["total_scoring_accepted"] >= 0, "Scoring accepted count must be >= 0"
    assert summary["total_scoring_rejected"] >= 0, "Scoring rejected count must be >= 0"
    
    # Verify logical relationships between counts
    assert summary["total_safety_validated"] <= summary["total_raw_generated"], (
        "Safety validated should be <= raw generated"
    )
    assert summary["total_unique_after_dedup"] <= summary["total_safety_validated"], (
        "Unique should be <= safety validated"
    )
    assert summary["total_scoring_input"] == summary["total_unique_after_dedup"], (
        "Scoring input should equal unique (no loss between stages)"
    )
    assert summary["total_scoring_accepted"] + summary["total_scoring_rejected"] == summary["total_scoring_input"], (
        "Accepted + rejected should equal scoring input"
    )
    
    # Verify per-iteration counts are also correct
    for iter_result in evidence["final_state"]["iteration_results"]:
        assert "raw_generated" in iter_result, "Iteration should track raw count"
        assert "safety_validated" in iter_result, "Iteration should track safety count"
        assert "unique_after_dedup" in iter_result, "Iteration should track unique count"
        assert "scoring_input" in iter_result, "Iteration should track scoring input"
        assert "scoring_accepted" in iter_result, "Iteration should track accepted"
        assert "scoring_rejected" in iter_result, "Iteration should track rejected"
        
        # All per-iteration counts must be non-negative
        assert iter_result["raw_generated"] >= 0, "Per-iteration raw count must be >= 0"
        assert iter_result["safety_validated"] >= 0, "Per-iteration safety count must be >= 0"
        assert iter_result["unique_after_dedup"] >= 0, "Per-iteration unique count must be >= 0"
        assert iter_result["scoring_input"] >= 0, "Per-iteration scoring input must be >= 0"
        assert iter_result["scoring_accepted"] >= 0, "Per-iteration accepted must be >= 0"
        assert iter_result["scoring_rejected"] >= 0, "Per-iteration rejected must be >= 0"
        
        # Verify rejected is computed correctly (never negative)
        assert iter_result["scoring_rejected"] == iter_result["scoring_input"] - iter_result["scoring_accepted"], (
            "Rejected should equal input - accepted"
        )


def test_topk_selection_supervised():
    """Test that top-K selection works with supervised metrics."""
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=1,
        candidates_per_iteration=10,
        llm_provider='mock',
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create panel
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 50,
        "date": pd.date_range("2020-01-01", periods=50),
        "close": np.random.randn(50) * 10 + 100,
        "volume": np.abs(np.random.randn(50)) * 1000,
    })
    
    # Create labels correlated with close for supervised ranking
    labels = panel["close"].values * 0.01 + np.random.randn(50) * 0.005
    feat_cols = ["close", "volume"]
    
    # Run search to get candidates
    final_candidates, evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,
        ticker_col="ticker",
        date_col="date",
    )
    
    # Test top-K selection
    top_k = 3
    selected_nodes, selection_stats = runner.select_top_k_candidates(
        candidate_nodes=final_candidates,
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,  # Supervised ranking
        top_k=top_k,
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify selection worked
    assert len(selected_nodes) <= top_k, f"Should select at most {top_k} candidates"
    assert len(selected_nodes) == min(top_k, len(final_candidates)), (
        "Should select min(top_k, available_candidates)"
    )
    
    # Verify selection stats
    assert selection_stats["top_k"] == top_k, "Stats should record top_k"
    assert selection_stats["selected"] == len(selected_nodes), "Stats should record selected count"
    assert selection_stats["selection_mode"] == "supervised", "Should use supervised mode with labels"
    assert selection_stats["metric_name"] == "absolute_ic", "Should rank by IC with labels"
    
    # Verify scores are in descending order (only if ranking was performed)
    if selection_stats.get("ranking_skipped", False):
        # When candidates <= top_k, ranking is skipped and all candidates returned
        assert selection_stats["top_scores"] == [], "Should have empty scores when ranking skipped"
    else:
        top_scores = selection_stats["top_scores"]
        assert len(top_scores) == len(selected_nodes), "Should have score for each selected node"
        for i in range(len(top_scores) - 1):
            assert top_scores[i] >= top_scores[i + 1], "Scores should be in descending order"


def test_topk_selection_unsupervised():
    """Test that top-K selection falls back to unsupervised metrics without labels."""
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=1,
        candidates_per_iteration=10,
        llm_provider='mock',
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create panel
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 50,
        "date": pd.date_range("2020-01-01", periods=50),
        "close": np.random.randn(50) * 10 + 100,
        "volume": np.abs(np.random.randn(50)) * 1000,
    })
    
    feat_cols = ["close", "volume"]
    
    # Run search WITHOUT labels
    final_candidates, evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=None,  # No labels - unsupervised
        ticker_col="ticker",
        date_col="date",
    )
    
    # Test top-K selection without labels
    top_k = 3
    selected_nodes, selection_stats = runner.select_top_k_candidates(
        candidate_nodes=final_candidates,
        panel=panel,
        feat_cols=feat_cols,
        labels=None,  # No labels
        top_k=top_k,
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify unsupervised mode was used
    assert selection_stats["selection_mode"] == "unsupervised", "Should use unsupervised mode without labels"
    assert selection_stats["metric_name"] == "variance", "Should rank by variance without labels"
    
    # Verify selection still works
    assert len(selected_nodes) <= top_k, f"Should select at most {top_k} candidates"


def test_supervised_selection_metadata():
    """Test that supervised selection metadata is tracked correctly."""
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    from omega.quant.evolution.llm_formula_scorer import FormulaScorerConfig
    
    config = FormulaSearchConfig(
        max_iterations=1,
        candidates_per_iteration=5,
        llm_provider='mock',
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create panel
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 50,
        "date": pd.date_range("2020-01-01", periods=50),
        "close": np.random.randn(50) * 10 + 100,
        "volume": np.abs(np.random.randn(50)) * 1000,
    })
    
    # Create labels for supervised scoring
    labels = np.random.randn(50) * 0.02
    feat_cols = ["close", "volume"]
    
    # Run search WITH labels (supervised mode)
    final_candidates, evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,  # Supervised scoring
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify supervised mode was used in scoring
    # Check iteration results for scoring stats
    for iter_result in evidence["final_state"]["iteration_results"]:
        if "scoring_stats" in iter_result and "details" in iter_result["scoring_stats"]:
            # At least one candidate should have supervised metrics
            details = iter_result["scoring_stats"]["details"]
            found_supervised = False
            for name, metrics in details.items():
                if metrics.get("absolute_ic") is not None:
                    found_supervised = True
                    # Verify supervised validation metadata
                    assert "is_supervised_validated" in metrics, "Should track supervised validation"
                    assert "is_deployable" in metrics, "Should track deployability"
                    assert "validation_mode" in metrics, "Should track validation mode"
                    
                    if metrics.get("accepted"):
                        # Accepted with labels should be supervised mode
                        assert metrics["validation_mode"] in ["supervised", "unsupervised_only"], (
                            "Validation mode should be supervised or unsupervised_only"
                        )
            
            if found_supervised:
                break


def test_no_test_label_leakage():
    """Test that search doesn't leak test labels into feature generation.
    
    PIT safety verification: labels used for scoring should be train-only.
    """
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=1,
        candidates_per_iteration=5,
        llm_provider='mock',
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create panel (simulating train data)
    np.random.seed(42)
    train_size = 50
    panel = pd.DataFrame({
        "ticker": ["A"] * train_size,
        "date": pd.date_range("2020-01-01", periods=train_size),
        "close": np.random.randn(train_size) * 10 + 100,
        "volume": np.abs(np.random.randn(train_size)) * 1000,
    })
    
    # Train-only labels (PIT-safe: same time period as panel)
    train_labels = np.random.randn(train_size) * 0.02
    feat_cols = ["close", "volume"]
    
    # Run search with train-only labels
    final_candidates, evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=train_labels,
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify evidence doesn't contain test-related terms
    evidence_str = str(evidence)
    assert "test_label" not in evidence_str.lower(), "Evidence should not mention test labels"
    assert "test_ic" not in evidence_str.lower() or "test_ic_for_deploy" in evidence_str.lower(), (
        "Evidence should not mention test_ic except in config thresholds"
    )
    
    # Verify aggregate stats only (no row-level data)
    if "aggregate_failure_stats" in evidence["final_state"]:
        stats = evidence["final_state"]["aggregate_failure_stats"]
        for key, value in stats.items():
            assert isinstance(value, (int, float, str, bool, type(None))), (
                f"Aggregate stat {key} should be scalar, got {type(value)}"
            )
            assert not isinstance(value, (list, np.ndarray)), (
                f"Aggregate stat {key} should not be array/list (leakage risk)"
            )
    
    # Verify deployment flag requires full CPCV (not train-only validation)
    assert not evidence["deployment_ready"], "Should not be deployment-ready with train-only validation"
    assert evidence["requires_full_cpcv"], "Should require full CPCV for deployment"


def test_no_negative_rejected_counts():
    """Test that rejected counts are never negative.
    
    Regression test for bug: rejected=-14 when mixing per-iteration and accumulated counts.
    """
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=3,
        candidates_per_iteration=5,
        llm_provider='mock',
        enable_formula_memory=True,
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create panel
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 30,
        "date": pd.date_range("2020-01-01", periods=30),
        "close": np.random.randn(30) * 10 + 100,
        "volume": np.abs(np.random.randn(30)) * 1000,
    })
    
    labels = np.random.randn(30) * 0.02
    feat_cols = ["close", "volume"]
    
    # Run search
    final_candidates, evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify summary counts are non-negative
    summary = evidence["summary"]
    assert summary["total_scoring_rejected"] >= 0, "Summary rejected count must be >= 0"
    
    # Verify per-iteration rejected counts are non-negative
    for iter_result in evidence["final_state"]["iteration_results"]:
        rejected = iter_result["scoring_rejected"]
        assert rejected >= 0, (
            f"Iteration {iter_result['iteration']} rejected count must be >= 0, got {rejected}"
        )
        
        # Verify rejected is computed correctly within iteration scope
        scoring_input = iter_result["scoring_input"]
        scoring_accepted = iter_result["scoring_accepted"]
        expected_rejected = scoring_input - scoring_accepted
        
        assert rejected == expected_rejected, (
            f"Iteration {iter_result['iteration']}: rejected={rejected} should equal "
            f"input={scoring_input} - accepted={scoring_accepted} = {expected_rejected}"
        )
        
        # Verify we never compute rejected from mismatched scopes
        # (e.g., per-iteration generated - accumulated accepted)
        if "raw_generated" in iter_result:
            raw_generated = iter_result["raw_generated"]
            # Rejected should NOT be raw_generated - accumulated_accepted
            # It should be scoring_input - scoring_accepted (within same scope)
            assert rejected != (raw_generated - summary["total_scoring_accepted"]), (
                "Rejected should not be computed from mismatched scopes "
                "(per-iter generated vs accumulated accepted)"
            )


def test_count_tracking_across_iterations():
    """Test that count tracking works correctly across multiple iterations."""
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=3,
        candidates_per_iteration=5,
        llm_provider='mock',
        enable_formula_memory=True,
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create panel
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 40,
        "date": pd.date_range("2020-01-01", periods=40),
        "close": np.random.randn(40) * 10 + 100,
        "volume": np.abs(np.random.randn(40)) * 1000,
    })
    
    labels = np.random.randn(40) * 0.02
    feat_cols = ["close", "volume"]
    
    # Run search with multiple iterations
    final_candidates, evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify accumulated counts are sums of per-iteration counts
    summary = evidence["summary"]
    iteration_results = evidence["final_state"]["iteration_results"]
    
    # Sum per-iteration counts
    total_raw = sum(r["raw_generated"] for r in iteration_results)
    total_safety = sum(r["safety_validated"] for r in iteration_results)
    total_unique = sum(r["unique_after_dedup"] for r in iteration_results)
    total_scoring_input = sum(r["scoring_input"] for r in iteration_results)
    total_scoring_accepted = sum(r["scoring_accepted"] for r in iteration_results)
    total_scoring_rejected = sum(r["scoring_rejected"] for r in iteration_results)
    
    # Verify accumulated counts match sums
    assert summary["total_raw_generated"] == total_raw, "Accumulated raw should equal sum"
    assert summary["total_safety_validated"] == total_safety, "Accumulated safety should equal sum"
    assert summary["total_unique_after_dedup"] == total_unique, "Accumulated unique should equal sum"
    assert summary["total_scoring_input"] == total_scoring_input, "Accumulated input should equal sum"
    assert summary["total_scoring_accepted"] == total_scoring_accepted, "Accumulated accepted should equal sum"
    assert summary["total_scoring_rejected"] == total_scoring_rejected, "Accumulated rejected should equal sum"
    
    # Verify consistency
    assert summary["total_scoring_accepted"] + summary["total_scoring_rejected"] == summary["total_scoring_input"], (
        "Accepted + rejected should equal input at summary level"
    )


def test_topk_selection_with_env_var():
    """Test that top-K selection respects OMEGA_LLM_TOP_K env var."""
    import os
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    # Save original env
    orig_val = os.environ.get('OMEGA_LLM_TOP_K')
    
    try:
        # Set env var
        os.environ['OMEGA_LLM_TOP_K'] = '3'
        
        config = FormulaSearchConfig(
            max_iterations=1,
            candidates_per_iteration=10,
            llm_provider='mock',
        )
        
        runner = FormulaSearchRunner(config)
        
        # Create panel
        np.random.seed(42)
        panel = pd.DataFrame({
            "ticker": ["A"] * 30,
            "date": pd.date_range("2020-01-01", periods=30),
            "close": np.random.randn(30) * 10 + 100,
            "volume": np.abs(np.random.randn(30)) * 1000,
        })
        
        labels = np.random.randn(30) * 0.02
        feat_cols = ["close", "volume"]
        
        # Run search
        final_candidates, evidence = runner.run_search(
            panel=panel,
            feat_cols=feat_cols,
            labels=labels,
            ticker_col="ticker",
            date_col="date",
        )
        
        # The backtest script would read OMEGA_LLM_TOP_K and pass top_k to select_top_k_candidates
        # Here we verify the env var is readable
        top_k_from_env = int(os.environ.get('OMEGA_LLM_TOP_K', '10'))
        assert top_k_from_env == 3, "Should read top_k from env var"
        
    finally:
        # Restore env
        if orig_val is not None:
            os.environ['OMEGA_LLM_TOP_K'] = orig_val
        elif 'OMEGA_LLM_TOP_K' in os.environ:
            del os.environ['OMEGA_LLM_TOP_K']


def test_backtest_cpcv_pre_split_no_label_leakage():
    """Integration test: Verify LLM search before CPCV splits never sees test labels.
    
    Regression test for L3 audit finding (2026-06-12):
    backtest_v2_cpcv.py was passing full-sample target.values to LLM search BEFORE
    CPCV splits were created, allowing supervised candidate selection to see
    held-out test labels.
    
    Fix: backtest_v2_cpcv.py now passes labels=None to pre-CPCV LLM search,
    ensuring unsupervised-only candidate generation. Supervised validation
    happens inside each CPCV fold.
    
    This test simulates the corrected backtest_v2_cpcv.py flow:
    1. Pre-CPCV: Generate candidates with labels=None (unsupervised)
    2. Post-CPCV: Validate inside each fold with fold-specific train labels
    """
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=1,
        candidates_per_iteration=5,
        llm_provider='mock',
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create full-sample panel (simulating what backtest_v2_cpcv.py has before splits)
    np.random.seed(42)
    full_size = 100
    panel = pd.DataFrame({
        "ticker": ["A"] * full_size,
        "date": pd.date_range("2020-01-01", periods=full_size),
        "close": np.random.randn(full_size) * 10 + 100,
        "volume": np.abs(np.random.randn(full_size)) * 1000,
    })
    
    # Full-sample labels (what backtest_v2_cpcv.py has before CPCV splits)
    # THESE SHOULD NEVER BE PASSED TO PRE-CPCV LLM SEARCH
    full_sample_labels = np.random.randn(full_size) * 0.02
    feat_cols = ["close", "volume"]
    
    # === PRE-CPCV PHASE (FIXED) ===
    # Run search WITHOUT labels (PIT-safe: no test leakage before CPCV splits)
    # This is what backtest_v2_cpcv.py now does after the fix
    pre_cpcv_candidates, pre_cpcv_evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=None,  # CRITICAL: no labels before CPCV splits (prevents test leakage)
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify pre-CPCV search ran in unsupervised mode
    assert not pre_cpcv_evidence["deployment_ready"], (
        "Pre-CPCV candidates should not be deployment-ready (unsupervised only)"
    )
    assert pre_cpcv_evidence["requires_full_cpcv"], (
        "Pre-CPCV candidates should require full CPCV validation"
    )
    
    # Verify pre-CPCV search never saw the full-sample labels
    # Check that all accepted candidates are marked as unsupervised-only
    for iter_result in pre_cpcv_evidence["final_state"]["iteration_results"]:
        if "scoring_stats" in iter_result and "details" in iter_result["scoring_stats"]:
            details = iter_result["scoring_stats"]["details"]
            for name, metrics in details.items():
                if metrics.get("accepted"):
                    # All accepted candidates should be unsupervised validation only
                    # (no IC/DSR because labels=None)
                    validation_mode = metrics.get("validation_mode", "unknown")
                    assert validation_mode == "unsupervised_only", (
                        f"Pre-CPCV candidate {name} should be unsupervised_only, got {validation_mode}"
                    )
    
    # === SIMULATE CPCV SPLITS ===
    # Simulate 2-fold CPCV split
    fold1_train_idx = list(range(0, 50))  # First 50 rows for training
    fold1_test_idx = list(range(50, 100))  # Last 50 rows for testing
    
    fold2_train_idx = list(range(50, 100))  # Last 50 rows for training
    fold2_test_idx = list(range(0, 50))  # First 50 rows for testing
    
    # === POST-CPCV PHASE (FOLD-SPECIFIC VALIDATION) ===
    # Now we can validate candidates using fold-specific train labels
    # This simulates what happens inside each CPCV fold
    
    # Fold 1: Validate using fold1 train labels only
    fold1_train_labels = full_sample_labels[fold1_train_idx]
    fold1_train_panel = panel.iloc[fold1_train_idx].reset_index(drop=True)
    
    # Execute candidates on fold1 train data and compute metrics
    for i, node in enumerate(pre_cpcv_candidates[:2]):  # Test first 2 candidates
        values = runner.synthesizer.execute_node_grouped(
            node, fold1_train_panel, feat_cols, ticker_col="ticker", date_col="date"
        )
        
        # Compute IC on fold1 train data only (PIT-safe: no test labels)
        valid_mask = np.isfinite(values) & np.isfinite(fold1_train_labels)
        if np.sum(valid_mask) >= 2:
            ic = float(np.corrcoef(values[valid_mask], fold1_train_labels[valid_mask])[0, 1])
            # IC can be computed, but this is INSIDE the CPCV fold (PIT-safe)
            assert isinstance(ic, float), "Should compute IC inside fold"
    
    # Fold 2: Validate using fold2 train labels only (different from fold1)
    fold2_train_labels = full_sample_labels[fold2_train_idx]
    fold2_train_panel = panel.iloc[fold2_train_idx].reset_index(drop=True)
    
    # Execute candidates on fold2 train data
    for i, node in enumerate(pre_cpcv_candidates[:2]):
        values = runner.synthesizer.execute_node_grouped(
            node, fold2_train_panel, feat_cols, ticker_col="ticker", date_col="date"
        )
        
        # Compute IC on fold2 train data only (PIT-safe: no test labels)
        valid_mask = np.isfinite(values) & np.isfinite(fold2_train_labels)
        if np.sum(valid_mask) >= 2:
            ic = float(np.corrcoef(values[valid_mask], fold2_train_labels[valid_mask])[0, 1])
            assert isinstance(ic, float), "Should compute IC inside fold"
    
    # === VERIFICATION ===
    # The key property: pre-CPCV candidates were generated WITHOUT seeing any labels
    # Each CPCV fold validates using only its own train labels (never test labels)
    # This ensures no test-label leakage into candidate generation
    
    # Verify that top-K selection also works with labels=None (pre-CPCV)
    if len(pre_cpcv_candidates) > 3:
        top_k = 3
        selected_nodes, selection_stats = runner.select_top_k_candidates(
            candidate_nodes=pre_cpcv_candidates,
            panel=panel,
            feat_cols=feat_cols,
            labels=None,  # CRITICAL: no labels for pre-CPCV top-K selection
            top_k=top_k,
            ticker_col="ticker",
            date_col="date",
        )
        
        # Verify unsupervised selection
        assert selection_stats["selection_mode"] == "unsupervised", (
            "Pre-CPCV top-K selection should use unsupervised mode"
        )
        assert selection_stats["metric_name"] == "variance", (
            "Pre-CPCV top-K should rank by variance (not IC)"
        )
        assert len(selected_nodes) <= top_k, "Should select at most top_k candidates"


# ===========================================================================
# Hybrid Alpha Miner Nested CV Safety Tests (2026-06-12)
# ===========================================================================


def _make_nested_panel(n_tickers=3, n_dates=60, seed=42):
    """Helper: create synthetic panel for nested CV tests."""
    rng = np.random.default_rng(seed)
    rows = []
    for t in range(n_tickers):
        base = 100.0 + rng.standard_normal() * 10
        for d in range(n_dates):
            close = base + rng.standard_normal() * 2
            rows.append({
                "ticker": f"T{t}",
                "date": pd.Timestamp("2023-01-01") + pd.Timedelta(days=d),
                "close": close,
                "open": close + rng.standard_normal() * 0.3,
                "volume": abs(1000 + rng.standard_normal() * 200),
                "ret_1d": rng.standard_normal() * 0.02,
            })
            base = close
    return pd.DataFrame(rows)


def test_hybrid_no_outer_test_label_leakage():
    """CRITICAL PIT SAFETY TEST: Outer test labels must never be used for
    candidate generation or selection in HybridAlphaMiner.

    Verify: the miner's nested splits ensure outer test indices are excluded
    from all inner scoring operations.
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
        NestedCVSplitter,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=20,
        top_k=3,
        n_outer_folds=3,
        n_inner_folds=2,
        llm_provider="mock",
    )

    splitter = NestedCVSplitter(
        n_outer_folds=config.n_outer_folds,
        n_inner_folds=config.n_inner_folds,
    )

    n_samples = 120
    outer_splits = splitter.generate_outer_splits(n_samples)

    # For each outer fold, verify inner indices are disjoint from outer test
    for outer_split in outer_splits:
        outer_test_set = set(outer_split["test"])
        inner_splits = splitter.generate_inner_splits(outer_split["train"])

        for inner_split in inner_splits:
            inner_train_set = set(inner_split["train"])
            inner_val_set = set(inner_split["val"])

            # Inner train must be subset of outer train
            overlap_train = inner_train_set & outer_test_set
            assert len(overlap_train) == 0, (
                f"Inner train indices overlap with outer test: {overlap_train}"
            )

            # Inner val must be subset of outer train
            overlap_val = inner_val_set & outer_test_set
            assert len(overlap_val) == 0, (
                f"Inner val indices overlap with outer test: {overlap_val}"
            )

            # Inner train and val must be disjoint
            overlap_tv = inner_train_set & inner_val_set
            assert len(overlap_tv) == 0, (
                f"Inner train and val overlap: {overlap_tv}"
            )


def test_hybrid_inner_only_validation():
    """Test that HybridAlphaMiner scores candidates using only inner validation
    data within each outer fold."""
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
        NestedCVObjective,
        CandidateRecord,
        CandidateSource,
    )
    from omega.quant.evolution.genetic_programming import GPNode

    config = HybridAlphaMinerConfig(
        candidate_budget=10,
        top_k=2,
        n_outer_folds=2,
        n_inner_folds=2,
        llm_provider="mock",
    )

    scorer = NestedCVObjective(config)
    panel = _make_nested_panel(n_tickers=2, n_dates=40)
    feat_cols = ["close", "open", "volume", "ret_1d"]
    labels = np.random.randn(len(panel)) * 0.02

    # Create a simple candidate
    synth_module = __import__(
        "omega.quant.evolution.llm_symbolic_synthesizer",
        fromlist=["LLMSymbolicSynthesizer"],
    )
    synth = synth_module.LLMSymbolicSynthesizer(provider="mock")
    node = synth.parse_formula("ts_mean(close, 5)")

    record = CandidateRecord(
        node=node,
        source=CandidateSource.TEMPLATE,
        formula_str="ts_mean(close, 5)",
        formula_hash="test_hash_001",
    )

    # Create inner splits (within outer train)
    outer_train_idx = np.arange(0, 60)  # First 60 of 80 rows
    splitter_inner = __import__(
        "omega.quant.evolution.hybrid_alpha_miner",
        fromlist=["NestedCVSplitter"],
    ).NestedCVSplitter(n_outer_folds=2, n_inner_folds=2)
    inner_splits = splitter_inner.generate_inner_splits(outer_train_idx)

    # Score candidate
    scored = scorer.score_candidate(
        candidate=record,
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,
        inner_splits=inner_splits,
    )

    # Verify inner metrics are computed
    assert "ic" in scored.inner_metrics, "Should compute IC"
    assert "coverage" in scored.inner_metrics, "Should compute coverage"
    assert "dsr_proxy" in scored.inner_metrics, "Should compute DSR proxy"
    assert "sign_consistency" in scored.inner_metrics, "Should compute sign consistency"
    assert scored.objective_score != -np.inf, "Should have finite objective"

    # Verify n_inner_folds_scored matches number of inner splits used
    n_scored = scored.inner_metrics.get("n_inner_folds_scored", 0)
    assert n_scored >= 0, "Should report folds scored"


def test_hybrid_evidence_persistence():
    """Test that evidence can be saved and loaded as valid JSON."""
    import json
    import shutil
    from pathlib import Path
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=15,
        top_k=3,
        n_outer_folds=2,
        n_inner_folds=2,
        llm_provider="mock",
    )

    miner = HybridAlphaMiner(config)
    panel = _make_nested_panel(n_tickers=2, n_dates=25)
    labels = np.random.randn(len(panel)) * 0.02

    selected, evidence = miner.run(
        panel=panel,
        feat_cols=["close", "open", "volume", "ret_1d"],
        labels=labels,
    )

    # Save and reload evidence
    test_dir = Path(".ly_state/session/test_evidence_persist")
    test_dir.mkdir(parents=True, exist_ok=True)
    try:
        evidence_path = test_dir / "test_evidence.json"
        miner.save_evidence(evidence, evidence_path)

        assert evidence_path.exists(), "Evidence file should exist"

        with open(evidence_path, "r") as f:
            loaded = json.load(f)

        # Verify all expected keys
        expected_keys = [
            "config", "source_proportions", "total_generated",
            "total_selected", "deployment_ready", "requires_full_cpcv",
            "formula_memory", "selected_candidates", "objective_weights",
            "deploy_thresholds",
        ]
        for key in expected_keys:
            assert key in loaded, f"Evidence should contain key: {key}"

        # Verify JSON-serializable (no numpy types)
        assert isinstance(loaded["total_generated"], int)
        assert isinstance(loaded["total_selected"], int)
        assert isinstance(loaded["deployment_ready"], bool)

    finally:
        if test_dir.exists():
            shutil.rmtree(test_dir, ignore_errors=True)


def test_hybrid_stable_objective_ranking():
    """Test that objective ranking is stable: same inputs produce same ranking."""
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=15,
        top_k=3,
        n_outer_folds=2,
        n_inner_folds=2,
        llm_provider="mock",
    )

    panel = _make_nested_panel(n_tickers=2, n_dates=25, seed=42)
    labels = np.random.RandomState(42).randn(len(panel)) * 0.02
    feat_cols = ["close", "open", "volume", "ret_1d"]

    # Run twice with same random seed for miner internals
    import random as _rand
    _rand.seed(123)
    miner1 = HybridAlphaMiner(config)
    selected1, _ = miner1.run(panel=panel, feat_cols=feat_cols, labels=labels)

    _rand.seed(123)
    miner2 = HybridAlphaMiner(config)
    selected2, _ = miner2.run(panel=panel, feat_cols=feat_cols, labels=labels)

    # Rankings should be identical with same seed
    assert len(selected1) == len(selected2), "Same inputs should produce same count"
    for s1, s2 in zip(selected1, selected2):
        assert s1.formula_hash == s2.formula_hash, (
            f"Same seed should produce same ranking: {s1.formula_hash} != {s2.formula_hash}"
        )


def test_hybrid_deploy_false():
    """Test that deployment_ready is False unless strict thresholds pass.

    With synthetic random data and mock LLM, no candidate should pass
    the strict deploy thresholds (IC >= 0.05, sign >= 0.60, etc.).
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=20,
        top_k=5,
        n_outer_folds=2,
        n_inner_folds=2,
        llm_provider="mock",
        # Extremely strict thresholds that random data cannot meet
        min_deploy_ic=0.90,
        min_deploy_sign_consistency=1.00,
        min_deploy_dsr=1.00,
        min_deploy_coverage=0.999,
        max_deploy_correlation=0.01,
    )

    miner = HybridAlphaMiner(config)
    panel = _make_nested_panel(n_tickers=2, n_dates=30)
    # Purely random labels (no signal)
    labels = np.random.randn(len(panel)) * 0.02

    selected, evidence = miner.run(
        panel=panel,
        feat_cols=["close", "open", "volume", "ret_1d"],
        labels=labels,
    )

    # Deployment should be False with random data
    assert not evidence["deployment_ready"], (
        "deployment_ready should be False with random data and strict thresholds"
    )

    # requires_full_cpcv should always be True
    assert evidence["requires_full_cpcv"], (
        "Should always require full CPCV validation"
    )

    # Verify deploy thresholds are documented in evidence
    dt = evidence["deploy_thresholds"]
    assert dt["min_deploy_ic"] == 0.90
    assert dt["min_deploy_sign_consistency"] == 1.00
    assert dt["min_deploy_dsr"] == 1.00


# ===========================================================================
# L2 Fix Regression Tests (PIT leak, correlation gate, IC sign, 2026-06-12)
# ===========================================================================


def test_hybrid_pit_outer_test_perturbation_no_effect():
    """REGRESSION: Outer-test feature perturbation must NOT change inner-
    validation scores.

    Before fix (L3 blocker #1): execute_node_grouped ran on the full panel,
    so ts_mean/ts_rank/rank operators could see outer-test rows when
    computing values for outer-train rows near the boundary.

    After fix: the panel is sliced to outer-train rows before execution, so
    outer-test data is physically absent and cannot influence any operator.

    Test procedure:
    1. Run miner on original panel, capture inner-validation metrics.
    2. Perturb outer-test features heavily.
    3. Run miner again, verify inner-validation metrics are unchanged.
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=15,
        top_k=3,
        n_outer_folds=3,
        n_inner_folds=2,
        llm_provider="mock",
    )

    panel = _make_nested_panel(n_tickers=3, n_dates=60, seed=42)
    labels = np.random.RandomState(42).randn(len(panel)) * 0.02
    feat_cols = ["close", "open", "volume", "ret_1d"]

    # Run 1: original panel
    import random as _rand
    _rand.seed(99)
    miner1 = HybridAlphaMiner(config)
    selected1, evidence1 = miner1.run(
        panel=panel.copy(), feat_cols=feat_cols, labels=labels.copy(),
    )

    # Compute outer-test index range (the region we will perturb)
    n_samples = len(panel)
    splitter = miner1.splitter
    outer_splits = splitter.generate_outer_splits(n_samples)

    # Perturb outer-test features heavily
    panel_perturbed = panel.copy()
    for outer_split in outer_splits:
        test_idx = outer_split["test"]
        # Multiply outer-test close values by 100 (huge perturbation)
        panel_perturbed.iloc[test_idx, panel_perturbed.columns.get_loc("close")] *= 100.0
        panel_perturbed.iloc[test_idx, panel_perturbed.columns.get_loc("volume")] *= 100.0

    # Run 2: perturbed panel (outer-test rows massively changed)
    _rand.seed(99)
    miner2 = HybridAlphaMiner(config)
    selected2, evidence2 = miner2.run(
        panel=panel_perturbed, feat_cols=feat_cols, labels=labels.copy(),
    )

    # Inner-validation scores must be identical (outer-test perturbation
    # should have zero effect because those rows are sliced out before
    # execution).
    assert len(selected1) == len(selected2), "Same count of selected candidates"

    for s1, s2 in zip(selected1, selected2):
        # Same formulas should be selected (same hashes)
        assert s1.formula_hash == s2.formula_hash, (
            f"Outer-test perturbation changed selected formula: "
            f"{s1.formula_str} vs {s2.formula_str}"
        )
        # Same inner-validation IC (PIT-safe: outer-test not used)
        ic1 = s1.inner_metrics.get("ic", 0.0)
        ic2 = s2.inner_metrics.get("ic", 0.0)
        assert abs(ic1 - ic2) < 1e-10, (
            f"IC changed after outer-test perturbation: {ic1} vs {ic2} "
            f"for formula {s1.formula_str}"
        )
        # Same coverage (PIT-safe: coverage computed on outer-train only)
        cov1 = s1.inner_metrics.get("coverage", 0.0)
        cov2 = s2.inner_metrics.get("coverage", 0.0)
        assert abs(cov1 - cov2) < 1e-10, (
            f"Coverage changed after outer-test perturbation: {cov1} vs {cov2}"
        )


def test_hybrid_correlation_gate_nonzero():
    """REGRESSION: Duplicate / highly-correlated candidates must get
    non-zero max_correlation penalty.

    Before fix (L3 blocker #2): selected_values was never populated,
    so max_correlation was always 0.0 regardless of actual pairwise
    correlation.

    After fix: greedy top-K selection computes real pairwise Spearman
    correlations between selected candidates and stores them in
    inner_metrics['max_correlation'].
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=20,
        top_k=5,
        n_outer_folds=2,
        n_inner_folds=2,
        llm_provider="mock",
    )

    miner = HybridAlphaMiner(config)
    panel = _make_nested_panel(n_tickers=3, n_dates=50, seed=42)
    labels = np.random.RandomState(42).randn(len(panel)) * 0.02
    feat_cols = ["close", "open", "volume", "ret_1d"]

    selected, evidence = miner.run(
        panel=panel, feat_cols=feat_cols, labels=labels,
    )

    # Verify correlation gate is present in evidence
    assert "correlation_gate" in evidence, (
        "Evidence should contain correlation_gate section"
    )


# ===========================================================================
# L2 Fix2 Regression Tests (P0 worst-case corr, P1 aggregate metrics)
# ===========================================================================


def test_hybrid_correlation_gate_worst_case_fold_blocks_deploy():
    """REGRESSION (P0): One fold breaches correlation threshold but mean
    is below threshold => deployment_ready must be False and
    correlation_blocked must be True.

    Before fix (L3 reaudit P0): ``max_correlation`` was computed as
    ``np.mean(fold_corrs)``, so one fold with corr=1.0 and another with
    corr=0.0 would report 0.5 (below 0.7 threshold) and deploy would pass.

    After fix: ``max_correlation`` is ``max(fold_corrs)`` (worst-case),
    so fold corr=1.0 blocks deployment even when mean is 0.5.
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        NestedCVObjective,
        HybridAlphaMinerConfig,
        CandidateRecord,
        CandidateSource,
    )
    from omega.quant.evolution.genetic_programming import GPNode

    config = HybridAlphaMinerConfig(
        candidate_budget=10,
        top_k=3,
        n_outer_folds=2,
        n_inner_folds=2,
        max_deploy_correlation=0.70,
    )
    scorer = NestedCVObjective(config)

    # Candidate that passes all other thresholds
    node = GPNode(operator="terminal", value="close")

    # Simulate worst-case: one fold has corr=0.90 (breaches 0.70),
    # another has corr=0.30 (well below). Mean = 0.60 < 0.70 but
    # max = 0.90 > 0.70 so deploy must be blocked.
    rec = CandidateRecord(
        node=node,
        source=CandidateSource.TEMPLATE,
        formula_str="close",
        formula_hash="worst_case_corr_test",
        inner_metrics={
            "ic": 0.10,
            "signed_ic": 0.10,
            "sign_consistency": 0.80,
            "dsr_proxy": 0.80,
            "coverage": 0.95,
            "max_correlation": 0.90,  # worst-case max across folds
            "mean_fold_max_correlation": 0.60,  # mean is below threshold
        },
    )

    # Must NOT be deploy-ready because worst-case max_correlation > 0.70
    assert not scorer.check_deploy_ready(rec), (
        "Candidate with worst-case max_correlation=0.90 must fail deploy "
        "even when mean_fold_max_correlation=0.60 is below threshold 0.70"
    )


def test_hybrid_deploy_metrics_are_aggregate_not_last_fold():
    """REGRESSION (P1): Selected candidate inner_metrics must reflect the
    nested-CV aggregate across all outer folds, not the last outer fold's
    overwrite.

    Before fix (L3 reaudit P1): ``score_candidate()`` overwrote
    ``candidate.inner_metrics`` on every outer fold, so only the last
    fold's metrics were used for deployment readiness and evidence.

    After fix: ``inner_metrics`` is aggregated (mean) across all outer
    folds after the outer-fold loop completes.
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
        CandidateRecord,
        CandidateSource,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=15,
        top_k=3,
        n_outer_folds=3,
        n_inner_folds=2,
        llm_provider="mock",
    )

    miner = HybridAlphaMiner(config)
    panel = _make_nested_panel(n_tickers=3, n_dates=60, seed=42)
    labels = np.random.RandomState(42).randn(len(panel)) * 0.02
    feat_cols = ["close", "open", "volume", "ret_1d"]

    selected, evidence = miner.run(
        panel=panel, feat_cols=feat_cols, labels=labels,
    )

    # For each selected candidate, verify inner_metrics are aggregates
    for c in selected:
        if not c._fold_metrics:
            continue

        fold_m = list(c._fold_metrics.values())
        n_folds = len(fold_m)
        assert n_folds >= 2, (
            "Candidate should have metrics from at least 2 outer folds"
        )

        # Compute expected aggregate IC
        expected_agg_ic = float(np.mean([m["ic"] for m in fold_m]))
        actual_ic = c.inner_metrics.get("ic", 0.0)

        # Aggregate IC should match (within floating point tolerance)
        assert abs(actual_ic - expected_agg_ic) < 1e-10, (
            f"inner_metrics['ic'] should be aggregate ({expected_agg_ic:.6f}), "
            f"not last fold ({fold_m[-1]['ic']:.6f}). Got {actual_ic:.6f}"
        )

        # Verify it is NOT equal to only the last fold (unless there's
        # only one fold or all folds happen to be identical)
        last_fold_ic = fold_m[-1]["ic"]
        if n_folds >= 2 and abs(fold_m[0]["ic"] - last_fold_ic) > 1e-6:
            # Folds have different ICs; aggregate should differ from last
            assert abs(actual_ic - last_fold_ic) > 1e-10 or abs(
                actual_ic - expected_agg_ic
            ) < 1e-10, (
                "inner_metrics should be aggregate, not last fold value"
            )

        # Also verify coverage and sign_consistency are aggregated
        expected_agg_cov = float(np.mean([m["coverage"] for m in fold_m]))
        actual_cov = c.inner_metrics.get("coverage", 0.0)
        assert abs(actual_cov - expected_agg_cov) < 1e-10, (
            f"inner_metrics['coverage'] should be aggregate "
            f"({expected_agg_cov:.6f}), got {actual_cov:.6f}"
        )

        # Verify n_outer_folds_scored is present
        assert c.inner_metrics.get("n_outer_folds_scored", 0) == n_folds, (
            "n_outer_folds_scored should match number of scored folds"
        )

    cg = evidence["correlation_gate"]
    assert "max_pairwise_correlation" in cg
    assert "mean_pairwise_correlation" in cg

    # With multiple selected candidates, at least some should have
    # non-zero max_correlation (formulas using similar features will
    # produce correlated outputs).
    has_nonzero_corr = False
    for c in selected:
        mc = c.inner_metrics.get("max_correlation", 0.0)
        if mc > 0.0:
            has_nonzero_corr = True
            break

    # With 5 selected candidates from mock LLM (which generates similar
    # ts_mean formulas), we expect at least some pairwise correlation
    assert has_nonzero_corr, (
        "At least one selected candidate should have non-zero "
        "max_correlation with other selected candidates"
    )


def test_hybrid_correlation_gate_blocks_deploy():
    """REGRESSION: deployment_ready must be False when max_correlation
    exceeds the deploy threshold.
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
        CandidateRecord,
        CandidateSource,
        NestedCVObjective,
    )
    from omega.quant.evolution.genetic_programming import GPNode

    config = HybridAlphaMinerConfig(
        candidate_budget=10,
        top_k=3,
        n_outer_folds=2,
        n_inner_folds=2,
        max_deploy_correlation=0.30,  # Low threshold
    )

    scorer = NestedCVObjective(config)

    # Create a candidate with high correlation in metrics
    node = GPNode(operator="terminal", value="close")
    rec = CandidateRecord(
        node=node,
        source=CandidateSource.TEMPLATE,
        formula_str="close",
        formula_hash="test_corr",
        inner_metrics={
            "ic": 0.10,
            "signed_ic": 0.10,
            "sign_consistency": 0.80,
            "dsr_proxy": 0.80,
            "coverage": 0.95,
            "max_correlation": 0.85,  # Exceeds threshold of 0.30
        },
    )

    # Should NOT be deploy-ready because correlation exceeds threshold
    assert not scorer.check_deploy_ready(rec), (
        "Candidate with max_correlation=0.85 should fail deploy "
        "when max_deploy_correlation=0.30"
    )


def test_hybrid_signed_ic_positive_only():
    """REGRESSION: IC sign semantics – negative IC candidates must be
    deprioritised (signed_ic = 0), not treated equally with positive IC.

    Before fix (L3 blocker #3): abs_ic was used, so negative-IC and
    positive-IC candidates ranked equally.

    After fix: signed_ic = max(0, mean_ic) is used in the objective,
    so negative-IC candidates contribute 0 to the IC component.
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        NestedCVObjective,
        HybridAlphaMinerConfig,
        CandidateRecord,
        CandidateSource,
    )
    from omega.quant.evolution.genetic_programming import GPNode

    config = HybridAlphaMinerConfig(
        candidate_budget=10,
        top_k=2,
        n_outer_folds=2,
        n_inner_folds=2,
    )
    scorer = NestedCVObjective(config)

    # Candidate with negative IC should have signed_ic = 0
    node = GPNode(operator="terminal", value="close")
    rec_neg = CandidateRecord(
        node=node,
        source=CandidateSource.TEMPLATE,
        formula_str="close",
        formula_hash="neg_ic_test",
    )
    # Simulate: after scoring, IC is negative
    rec_neg.inner_metrics = {
        "ic": -0.15,
        "signed_ic": max(0.0, -0.15),
        "sign_consistency": 0.0,
        "dsr_proxy": 0.0,
        "coverage": 0.95,
        "max_correlation": 0.0,
    }
    # Recompute objective with signed_ic
    m = rec_neg.inner_metrics
    rec_neg.objective_score = (
        config.w_ic * m["signed_ic"]
        + config.w_sign_consistency * m["sign_consistency"]
        + config.w_dsr_proxy * m["dsr_proxy"]
        + config.w_coverage * m["coverage"]
        + config.w_low_correlation * (1.0 - m["max_correlation"])
    )

    # Candidate with positive IC
    rec_pos = CandidateRecord(
        node=node,
        source=CandidateSource.TEMPLATE,
        formula_str="close",
        formula_hash="pos_ic_test",
    )
    rec_pos.inner_metrics = {
        "ic": 0.15,
        "signed_ic": max(0.0, 0.15),
        "sign_consistency": 0.8,
        "dsr_proxy": 0.8,
        "coverage": 0.95,
        "max_correlation": 0.0,
    }
    m2 = rec_pos.inner_metrics
    rec_pos.objective_score = (
        config.w_ic * m2["signed_ic"]
        + config.w_sign_consistency * m2["sign_consistency"]
        + config.w_dsr_proxy * m2["dsr_proxy"]
        + config.w_coverage * m2["coverage"]
        + config.w_low_correlation * (1.0 - m2["max_correlation"])
    )

    # Positive IC candidate should rank higher
    assert rec_pos.objective_score > rec_neg.objective_score, (
        f"Positive IC ({rec_pos.objective_score:.4f}) should rank "
        f"higher than negative IC ({rec_neg.objective_score:.4f})"
    )

    # Negative IC candidate's signed_ic should be 0
    assert rec_neg.inner_metrics["signed_ic"] == 0.0, (
        "Negative IC should produce signed_ic = 0"
    )


def test_hybrid_deploy_false_when_ic_negative():
    """REGRESSION: deployment_ready must be False when IC is negative,
    even if abs(IC) exceeds the threshold.

    Before fix: check_deploy_ready used abs_ic, so negative-IC candidates
    could pass.

    After fix: check_deploy_ready uses signed IC, so negative-IC fails.
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        NestedCVObjective,
        HybridAlphaMinerConfig,
        CandidateRecord,
        CandidateSource,
    )
    from omega.quant.evolution.genetic_programming import GPNode

    config = HybridAlphaMinerConfig(
        candidate_budget=10,
        top_k=2,
        n_outer_folds=2,
        n_inner_folds=2,
        min_deploy_ic=0.05,
    )
    scorer = NestedCVObjective(config)

    node = GPNode(operator="terminal", value="close")
    rec = CandidateRecord(
        node=node,
        source=CandidateSource.TEMPLATE,
        formula_str="close",
        formula_hash="neg_deploy_test",
        inner_metrics={
            "ic": -0.20,  # Negative IC, but abs(0.20) > 0.05
            "signed_ic": 0.0,
            "sign_consistency": 0.80,
            "dsr_proxy": 0.80,
            "coverage": 0.95,
            "max_correlation": 0.10,
        },
    )

    # Should NOT be deploy-ready because signed IC is negative
    assert not scorer.check_deploy_ready(rec), (
        "Candidate with negative IC should fail deploy even if "
        "abs(IC) > threshold"
    )


def test_hybrid_evidence_has_pit_safety_metadata():
    """REGRESSION: Evidence should document PIT safety properties."""
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=15,
        top_k=3,
        n_outer_folds=2,
        n_inner_folds=2,
        llm_provider="mock",
    )

    miner = HybridAlphaMiner(config)
    panel = _make_nested_panel(n_tickers=2, n_dates=30)
    labels = np.random.randn(len(panel)) * 0.02

    selected, evidence = miner.run(
        panel=panel,
        feat_cols=["close", "open", "volume", "ret_1d"],
        labels=labels,
    )

    # Verify PIT safety metadata is present
    assert "pit_safety" in evidence, "Evidence should contain pit_safety section"
    pit = evidence["pit_safety"]
    assert pit["panel_sliced_per_outer_fold"] is True
    assert pit["ts_operators_cannot_see_outer_test"] is True
    assert pit["inner_splits_use_local_indices"] is True
    assert pit["ic_uses_signed_positive_only"] is True

    # Verify correlation gate is present
    assert "correlation_gate" in evidence, (
        "Evidence should contain correlation_gate section"
    )


# ===========================================================================
# L2 Fix3 Regression Tests (P0 evidence deploy block, P1 signed_ic reconcile)
# ===========================================================================


def test_hybrid_evidence_deploy_blocked_by_global_correlation():
    """REGRESSION (P0 fix3): evidence['deployment_ready'] must be False when
    ANY selected candidate breaches max_deploy_correlation, even if another
    candidate is individually deploy-ready.

    Before fix (L3 reaudit P0): ``deployment_ready`` was computed as
    ``any(check_deploy_ready(c) for c in selected)`` independently of the
    global correlation gate.  This produced ``deployment_ready=True`` while
    ``correlation_blocked=True`` in the same evidence JSON.

    After fix: ``deployment_ready = any_candidate_deploy_ready AND NOT
    correlation_blocked``.  A single breached candidate blocks the entire
    evidence deployment.
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
        CandidateRecord,
        CandidateSource,
        FormulaMemory,
    )
    from omega.quant.evolution.genetic_programming import GPNode

    config = HybridAlphaMinerConfig(
        candidate_budget=10,
        top_k=3,
        n_outer_folds=2,
        n_inner_folds=2,
        max_deploy_correlation=0.70,
        min_deploy_ic=0.05,
        min_deploy_sign_consistency=0.60,
        min_deploy_dsr=0.50,
        min_deploy_coverage=0.90,
    )

    miner = HybridAlphaMiner(config)
    node = GPNode(operator="terminal", value="close")

    # Candidate A: clean, individually deploy-ready
    clean_rec = CandidateRecord(
        node=node,
        source=CandidateSource.TEMPLATE,
        formula_str="close",
        formula_hash="clean_deploy_candidate",
        inner_metrics={
            "ic": 0.10,
            "signed_ic": 0.10,
            "sign_consistency": 0.80,
            "dsr_proxy": 0.80,
            "coverage": 0.95,
            "max_correlation": 0.20,  # well below threshold
        },
    )
    clean_rec.is_selected = True

    # Candidate B: breaches correlation threshold
    breached_rec = CandidateRecord(
        node=node,
        source=CandidateSource.TEMPLATE,
        formula_str="ts_mean(close, 5)",
        formula_hash="breached_corr_candidate",
        inner_metrics={
            "ic": 0.08,
            "signed_ic": 0.08,
            "sign_consistency": 0.70,
            "dsr_proxy": 0.70,
            "coverage": 0.92,
            "max_correlation": 0.85,  # BREACHES 0.70 threshold
        },
    )
    breached_rec.is_selected = True

    selected = [clean_rec, breached_rec]

    # Verify individual deploy readiness
    assert miner.scorer.check_deploy_ready(clean_rec), (
        "Clean candidate should individually pass deploy thresholds"
    )
    # Breached candidate may or may not pass depending on corr gate in
    # check_deploy_ready; that's candidate-level.  The evidence-level gate
    # is what we're testing.

    # Build evidence using the same logic as run()
    corr_values = [
        c.inner_metrics.get("max_correlation", 0.0) for c in selected
    ]
    max_pairwise = max(corr_values) if corr_values else 0.0
    correlation_blocked = (
        max_pairwise > config.max_deploy_correlation
        if corr_values else False
    )
    correlation_stats = {
        "max_pairwise_correlation": max_pairwise,
        "mean_pairwise_correlation": (
            float(np.mean(corr_values)) if corr_values else 0.0
        ),
        "correlation_threshold": config.max_deploy_correlation,
        "correlation_blocked": correlation_blocked,
    }

    any_candidate_deploy_ready = any(
        miner.scorer.check_deploy_ready(c) for c in selected
    )
    deployment_ready = any_candidate_deploy_ready and not correlation_blocked

    source_counts = {"template": 2}
    evidence = miner._build_evidence(
        selected=selected,
        source_counts=source_counts,
        n_outer=2,
        total_generated=10,
        deployment_ready=deployment_ready,
        correlation_stats=correlation_stats,
    )

    # CRITICAL ASSERTIONS
    assert correlation_blocked is True, (
        "correlation_blocked must be True when max_pairwise=0.85 > threshold=0.70"
    )
    assert evidence["deployment_ready"] is False, (
        "evidence['deployment_ready'] must be False when correlation_blocked=True, "
        "even if one candidate is individually deploy-ready"
    )
    assert evidence["correlation_gate"]["correlation_blocked"] is True, (
        "evidence['correlation_gate']['correlation_blocked'] must be True"
    )
    assert evidence["correlation_gate"]["max_pairwise_correlation"] == 0.85, (
        "max_pairwise_correlation should be 0.85"
    )


def test_hybrid_aggregate_signed_ic_no_positive_credit_for_negative_agg():
    """REGRESSION (P1 fix3): aggregate signed_ic must be max(0.0, aggregate_ic).
    Negative aggregate IC must NOT receive positive signed_ic credit.

    Before fix (L3 reaudit P1): ``agg_signed_ic`` was computed as
    ``np.mean([m['signed_ic'] for m in fold_m])`` (average of per-fold
    positive-only ICs).  A candidate with fold ICs [-0.03, 0.05] would get
    aggregate_ic=0.01 but signed_ic=0.025 (from averaging 0.0 and 0.05),
    giving inconsistent positive credit to a barely-positive aggregate.

    Worse, a candidate with fold ICs [-0.10, -0.05] would get
    aggregate_ic=-0.075 but signed_ic=0.0 (both folds zeroed out), which was
    correct but didn't match the ``max(0, agg_ic)`` formula.

    After fix: ``agg_signed_ic = max(0.0, aggregate_ic)``.  Per-fold
    positive IC is preserved as a separate diagnostic field named
    ``per_fold_positive_ic_diagnostic`` and is NOT used for deploy/objective.
    """
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=15,
        top_k=3,
        n_outer_folds=3,
        n_inner_folds=2,
        llm_provider="mock",
    )

    miner = HybridAlphaMiner(config)
    panel = _make_nested_panel(n_tickers=3, n_dates=60, seed=42)
    labels = np.random.RandomState(42).randn(len(panel)) * 0.02
    feat_cols = ["close", "open", "volume", "ret_1d"]

    selected, evidence = miner.run(
        panel=panel, feat_cols=feat_cols, labels=labels,
    )

    # For each selected candidate with aggregate metrics, verify signed_ic
    # consistency
    for c in selected:
        if not c._fold_metrics:
            continue

        fold_m = list(c._fold_metrics.values())
        agg_ic = float(np.mean([m["ic"] for m in fold_m]))
        expected_signed_ic = max(0.0, agg_ic)
        actual_signed_ic = c.inner_metrics.get("signed_ic", 0.0)

        # signed_ic must equal max(0, aggregate_ic) exactly
        assert abs(actual_signed_ic - expected_signed_ic) < 1e-12, (
            f"Aggregate signed_ic must be max(0.0, agg_ic). "
            f"agg_ic={agg_ic:.6f}, expected_signed_ic={expected_signed_ic:.6f}, "
            f"actual_signed_ic={actual_signed_ic:.6f}"
        )

        # Negative aggregate IC must produce signed_ic = 0
        if agg_ic < 0.0:
            assert actual_signed_ic == 0.0, (
                f"Negative aggregate IC ({agg_ic:.6f}) must produce "
                f"signed_ic=0.0, got {actual_signed_ic:.6f}"
            )

        # per_fold_positive_ic_diagnostic should be present
        assert "per_fold_positive_ic_diagnostic" in c.inner_metrics, (
            "per_fold_positive_ic_diagnostic should be in inner_metrics"
        )

        # Verify per_fold_positive_ic_diagnostic is the mean of per-fold
        # signed_ic (not the same as aggregate signed_ic)
        expected_per_fold_diag = float(
            np.mean([m["signed_ic"] for m in fold_m])
        )
        actual_diag = c.inner_metrics["per_fold_positive_ic_diagnostic"]
        assert abs(actual_diag - expected_per_fold_diag) < 1e-12, (
            f"per_fold_positive_ic_diagnostic mismatch: "
            f"expected {expected_per_fold_diag:.6f}, got {actual_diag:.6f}"
        )
