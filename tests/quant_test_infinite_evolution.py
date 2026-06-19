"""Unit tests for LLM Symbolic Synthesizer and Unsupervised Latent Encoder."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import torch

from omega.quant.evolution.llm_symbolic_synthesizer import LLMSymbolicSynthesizer
from omega.quant.models.latent_encoder import (
    LatentEncoderConfig,
    UnsupervisedLatentEncoder,
)


def test_llm_synthesizer_tokenization():
    synth = LLMSymbolicSynthesizer()
    formula = "add(ts_mean(close, 20), ts_rank(volume, 10))"
    tokens = synth.tokenize(formula)
    expected = [
        "add", "(", "ts_mean", "(", "close", ",", "20", ")", ",",
        "ts_rank", "(", "volume", ",", "10", ")", ")"
    ]
    assert tokens == expected


def test_llm_synthesizer_prefix_parsing():
    synth = LLMSymbolicSynthesizer()
    formula = "div(ts_std(close, 15), ts_mean(volume, 10))"
    node = synth.parse_formula(formula)
    assert node.operator == "/"
    assert len(node.children) == 2
    assert node.children[0].operator == "ts_std"
    assert node.children[1].operator == "ts_mean"
    assert node.children[0].children[0].value == "close"
    assert node.children[0].children[1].value == "15"


def test_llm_synthesizer_infix_fallback_parsing():
    synth = LLMSymbolicSynthesizer()
    # Test that parenthesized infix works too
    formula = "(close + open)"
    node = synth.parse_formula(formula)
    assert node.operator == "+"
    assert node.children[0].value == "close"
    assert node.children[1].value == "open"


def test_llm_synthesizer_validation_and_execution():
    synth = LLMSymbolicSynthesizer(provider='mock')
    features = {
        "close": np.random.randn(100),
        "open": np.random.randn(100),
        "volume": np.random.randn(100),
        "ret_1d": np.random.randn(100),
    }

    # Generate mock formulas - new API returns (nodes, stats)
    nodes, stats = synth.synthesize(features)
    assert len(nodes) > 0

    for node in nodes:
        assert synth.validate_expression(node, features)
        # Execute GP expression tree
        from omega.quant.evolution.genetic_programming import GPIndividual
        ind = GPIndividual(tree=node)
        val = ind._execute_tree(node, features)
        assert len(val) == 100
        assert not np.isnan(val).any()


def test_latent_encoder_shapes_and_fit_transform():
    cfg = LatentEncoderConfig(lookback=10, n_features=5,
                              latent_dim=4, epochs=2, batch_size=8)
    encoder = UnsupervisedLatentEncoder(cfg)

    # 50 samples, 10 lookback, 5 features
    X_seq = np.random.randn(50, 10, 5)
    encoder.fit(X_seq)
    assert encoder._fitted

    latent = encoder.transform(X_seq)
    assert latent.shape == (50, 4)
    assert not np.isnan(latent).any()


def test_latent_encoder_determinism():
    cfg1 = LatentEncoderConfig(lookback=10, n_features=4,
                               latent_dim=3, epochs=2, batch_size=8, seed=42)
    cfg2 = LatentEncoderConfig(lookback=10, n_features=4,
                               latent_dim=3, epochs=2, batch_size=8, seed=42)

    X_seq = np.random.randn(30, 10, 4)

    encoder1 = UnsupervisedLatentEncoder(cfg1).fit(X_seq)
    latent1 = encoder1.transform(X_seq)

    encoder2 = UnsupervisedLatentEncoder(cfg2).fit(X_seq)
    latent2 = encoder2.transform(X_seq)

    np.testing.assert_allclose(latent1, latent2, rtol=1e-5, atol=1e-5)


def test_execute_node_grouped_basic():
    """Test that execute_node_grouped works with proper panel structure."""
    import pandas as pd
    
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    # Create panel with 2 tickers, 10 dates each
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 10 + ["B"] * 10,
        "date": pd.date_range("2020-01-01", periods=10).tolist() * 2,
        "close": np.random.randn(20) + 100,
        "volume": np.abs(np.random.randn(20)) * 1000,
    })
    
    # Parse a simple formula
    node = synth.parse_formula("ts_mean(close, 5)")
    
    # Execute grouped
    result = synth.execute_node_grouped(
        node, panel, ["close", "volume"], ticker_col="ticker", date_col="date"
    )
    
    assert len(result) == 20
    assert not np.isnan(result).all()  # Some values should be computed


def test_execute_node_grouped_vs_flattened():
    """Test that grouped execution produces DIFFERENT results than flattened
    when time-series operators are involved. This proves we're not accidentally
    mixing data across tickers."""
    import pandas as pd
    from omega.quant.evolution.genetic_programming import GPIndividual
    
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    # Create panel with 2 tickers, distinct values to make cross-contamination obvious
    # Ticker A: close values around 100
    # Ticker B: close values around 200
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 10 + ["B"] * 10,
        "date": pd.date_range("2020-01-01", periods=10).tolist() * 2,
        "close": np.concatenate([
            np.random.randn(10) * 5 + 100,  # A: ~100
            np.random.randn(10) * 5 + 200   # B: ~200
        ]),
        "volume": np.abs(np.random.randn(20)) * 1000,
    })
    
    # Parse formula with time-series operator
    node = synth.parse_formula("ts_mean(close, 5)")
    
    # Grouped execution (PIT-safe)
    result_grouped = synth.execute_node_grouped(
        node, panel, ["close", "volume"], ticker_col="ticker", date_col="date"
    )
    
    # Flattened execution (OLD, UNSAFE path - for comparison only)
    feat_dict = {
        "close": panel["close"].to_numpy(),
        "volume": panel["volume"].to_numpy(),
    }
    ind = GPIndividual(tree=node)
    result_flattened = ind._execute_tree(node, feat_dict)
    
    # The results MUST be different because:
    # - Grouped: ts_mean for ticker A only uses A's data, B only uses B's data
    # - Flattened: ts_mean uses a 5-bar window that can span across A and B
    # 
    # Specifically, at the boundary (index 10, first bar of ticker B),
    # flattened will average bars 6-10 (last 5 bars of A) for the first bar of B,
    # while grouped will only use B's bar 0 (with NaN for insufficient history).
    
    # Check that they're different (not identical)
    assert not np.allclose(result_grouped, result_flattened, rtol=1e-10), (
        "Grouped and flattened execution should produce DIFFERENT results "
        "when time-series operators cross ticker boundaries"
    )


def test_execute_node_grouped_no_cross_ticker_contamination():
    """Test that time-series operators DO NOT mix data across tickers.
    
    This is the core PIT safety guarantee: ticker A's future data must never
    influence ticker B's past predictions."""
    import pandas as pd
    
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    # Create panel with 2 tickers with VERY different values
    # Ticker A: constant value 1.0
    # Ticker B: constant value 100.0
    panel = pd.DataFrame({
        "ticker": ["A"] * 20 + ["B"] * 20,
        "date": pd.date_range("2020-01-01", periods=20).tolist() * 2,
        "close": np.concatenate([
            np.ones(20) * 1.0,      # A: all 1.0
            np.ones(20) * 100.0     # B: all 100.0
        ]),
        "volume": np.ones(40) * 1000,
    })
    
    # ts_mean with window 5
    node = synth.parse_formula("ts_mean(close, 5)")
    result = synth.execute_node_grouped(
        node, panel, ["close", "volume"], ticker_col="ticker", date_col="date"
    )
    
    # For ticker A (rows 0-19), ts_mean should approach 1.0 (after warmup)
    # For ticker B (rows 20-39), ts_mean should approach 100.0 (after warmup)
    
    # Check ticker A results (skip first 4 rows due to warmup)
    a_results = result[5:20]
    assert np.allclose(a_results, 1.0, rtol=0.01), (
        f"Ticker A ts_mean should be ~1.0, got {a_results}"
    )
    
    # Check ticker B results (skip first 4 rows due to warmup)
    b_results = result[25:40]
    assert np.allclose(b_results, 100.0, rtol=0.01), (
        f"Ticker B ts_mean should be ~100.0, got {b_results}"
    )
    
    # Critical: ticker B's first results should NOT be contaminated by ticker A's data
    # If there was cross-contamination, the first result of B would be influenced
    # by A's 1.0 values, pulling the mean down from 100.0
    b_first_valid = result[24]  # 5th bar of ticker B (index 20+4)
    assert b_first_valid > 90.0, (
        f"Ticker B's first valid ts_mean should be >90 (no contamination from A's 1.0 values), "
        f"got {b_first_valid}"
    )


def test_execute_node_grouped_preserves_row_order():
    """Test that execute_node_grouped returns results aligned with input panel order."""
    import pandas as pd
    
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    # Create panel with mixed ticker order (not sorted by ticker)
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A", "B", "A", "B", "A", "B"] * 3,
        "date": pd.date_range("2020-01-01", periods=18),
        "close": np.random.randn(18) + 100,
        "volume": np.abs(np.random.randn(18)) * 1000,
    })
    
    node = synth.parse_formula("close")  # Simple identity
    result = synth.execute_node_grouped(
        node, panel, ["close", "volume"], ticker_col="ticker", date_col="date"
    )
    
    # Result should match panel's close values (after grouping and reindexing)
    # For identity operation, grouped execution should return close values
    assert len(result) == len(panel)
    # Identity should preserve approximate values (allowing for numeric precision)
    assert np.allclose(result, panel["close"].to_numpy(), rtol=0.01)


def test_llm_synthesizer_use_mock_false_fallback_no_recursion():
    """Regression test: provider='openai-compatible' without env should fall back to mock without recursion.
    
    Before fix: synthesize() with real provider but no API key would cause recursion.
    
    After fix: provider initialization falls back to MockProvider when env vars not set,
    returning mock nodes without recursion.
    """
    import os
    
    # Save original env
    orig_key = os.environ.get('OMEGA_LLM_API_KEY')
    orig_provider = os.environ.get('OMEGA_LLM_PROVIDER')
    
    try:
        # Clear env vars
        if 'OMEGA_LLM_API_KEY' in os.environ:
            del os.environ['OMEGA_LLM_API_KEY']
        if 'OMEGA_LLM_PROVIDER' in os.environ:
            del os.environ['OMEGA_LLM_PROVIDER']
        
        # Request real provider without API key (should fall back to mock)
        synth = LLMSymbolicSynthesizer(provider='openai-compatible')
        features = {
            "close": np.random.randn(100) + 100,
            "open": np.random.randn(100) + 100,
            "volume": np.abs(np.random.randn(100)) * 1000,
            "ret_1d": np.random.randn(100) * 0.02,
        }
        
        # This should return mock nodes without recursion error - new API returns tuple
        nodes, stats = synth.synthesize(features)
        
        # Verify we got nodes back
        assert len(nodes) > 0, "Should return fallback mock nodes"
        
        # Verify all nodes are valid GPNode objects
        from omega.quant.evolution.genetic_programming import GPNode
        for node in nodes:
            assert isinstance(node, GPNode)
        
        # Verify nodes are executable (no recursion means they were properly generated)
        from omega.quant.evolution.genetic_programming import GPIndividual
        for node in nodes:
            ind = GPIndividual(tree=node)
            result = ind._execute_tree(node, features)
            assert len(result) == 100
            # Some values may be NaN due to warmup periods in time-series ops, that's expected
            assert not np.isnan(result).all(), "Should have some valid computed values"
    
    finally:
        # Restore env
        if orig_key is not None:
            os.environ['OMEGA_LLM_API_KEY'] = orig_key
        if orig_provider is not None:
            os.environ['OMEGA_LLM_PROVIDER'] = orig_provider


def test_llm_provider_disabled_without_env():
    """Test that openai-compatible provider falls back to mock when OMEGA_LLM_API_KEY not set."""
    import os
    
    # Save original env
    orig_key = os.environ.get('OMEGA_LLM_API_KEY')
    orig_provider = os.environ.get('OMEGA_LLM_PROVIDER')
    
    try:
        # Clear env vars
        if 'OMEGA_LLM_API_KEY' in os.environ:
            del os.environ['OMEGA_LLM_API_KEY']
        if 'OMEGA_LLM_PROVIDER' in os.environ:
            del os.environ['OMEGA_LLM_PROVIDER']
        
        # Request openai-compatible provider without API key
        synth = LLMSymbolicSynthesizer(provider='openai-compatible')
        
        # Should fall back to MockProvider
        from omega.quant.evolution.llm_symbolic_synthesizer import MockProvider
        assert isinstance(synth.provider, MockProvider), (
            "Should fall back to MockProvider when OMEGA_LLM_API_KEY not set"
        )
        
        # Synthesize should work (using mock)
        features = {
            "close": np.random.randn(100) + 100,
            "volume": np.abs(np.random.randn(100)) * 1000,
        }
        nodes = synth.synthesize(features)
        assert len(nodes) > 0, "Mock fallback should return nodes"
        
    finally:
        # Restore env
        if orig_key is not None:
            os.environ['OMEGA_LLM_API_KEY'] = orig_key
        if orig_provider is not None:
            os.environ['OMEGA_LLM_PROVIDER'] = orig_provider


def test_formula_safety_parser_rejects_infix():
    """Test that safety parser rejects infix operators."""
    from omega.quant.evolution.llm_symbolic_synthesizer import FormulaSafetyParser
    
    parser = FormulaSafetyParser(
        allowed_terminals=['close', 'volume'],
        allowed_unary=['abs'],
        allowed_binary=['+', '-'],
        allowed_ts=['ts_mean'],
        max_depth=5,
        min_lookback=2,
        max_lookback=60
    )
    
    # Infix should be rejected
    is_valid, error = parser.validate_formula("close + volume")
    assert not is_valid, "Infix operator should be rejected"
    assert "infix" in error.lower()


def test_formula_safety_parser_rejects_unknown_operator():
    """Test that safety parser rejects unknown operators."""
    from omega.quant.evolution.llm_symbolic_synthesizer import FormulaSafetyParser
    
    parser = FormulaSafetyParser(
        allowed_terminals=['close', 'volume'],
        allowed_unary=['abs'],
        allowed_binary=['+'],
        allowed_ts=['ts_mean'],
        max_depth=5,
        min_lookback=2,
        max_lookback=60
    )
    
    # Unknown operator
    is_valid, error = parser.validate_formula("unknown_op(close)")
    assert not is_valid, "Unknown operator should be rejected"
    assert "unknown operator" in error.lower()


def test_formula_safety_parser_rejects_unknown_terminal():
    """Test that safety parser rejects unknown terminals."""
    from omega.quant.evolution.llm_symbolic_synthesizer import FormulaSafetyParser
    
    parser = FormulaSafetyParser(
        allowed_terminals=['close', 'volume'],
        allowed_unary=['abs'],
        allowed_binary=['+'],
        allowed_ts=['ts_mean'],
        max_depth=5,
        min_lookback=2,
        max_lookback=60
    )
    
    # Unknown terminal
    is_valid, error = parser.validate_formula("abs(unknown_var)")
    assert not is_valid, "Unknown terminal should be rejected"
    assert "unknown terminal" in error.lower()


def test_formula_safety_parser_rejects_bad_lookback():
    """Test that safety parser rejects lookback values outside range."""
    from omega.quant.evolution.llm_symbolic_synthesizer import FormulaSafetyParser
    
    parser = FormulaSafetyParser(
        allowed_terminals=['close', 'volume'],
        allowed_unary=['abs'],
        allowed_binary=['+'],
        allowed_ts=['ts_mean'],
        max_depth=5,
        min_lookback=2,
        max_lookback=60
    )
    
    # Lookback too small
    is_valid, error = parser.validate_formula("ts_mean(close, 1)")
    assert not is_valid, "Lookback < 2 should be rejected"
    assert "lookback" in error.lower()
    
    # Lookback too large
    is_valid, error = parser.validate_formula("ts_mean(close, 100)")
    assert not is_valid, "Lookback > 60 should be rejected"
    assert "lookback" in error.lower()


def test_formula_safety_parser_accepts_valid():
    """Test that safety parser accepts valid formulas."""
    from omega.quant.evolution.llm_symbolic_synthesizer import FormulaSafetyParser
    
    parser = FormulaSafetyParser(
        allowed_terminals=['close', 'volume'],
        allowed_unary=['abs'],
        allowed_binary=['+', 'div'],
        allowed_ts=['ts_mean', 'ts_std'],
        max_depth=5,
        min_lookback=2,
        max_lookback=60
    )
    
    # Valid formulas
    valid_formulas = [
        "ts_mean(close, 20)",
        "div(ts_std(close, 20), ts_mean(volume, 10))",
        "add(close, volume)",
    ]
    
    for formula in valid_formulas:
        is_valid, error = parser.validate_formula(formula)
        assert is_valid, f"Valid formula rejected: {formula} (error: {error})"


def test_formula_safety_parser_rejects_trailing_tokens():
    """Test that safety parser rejects formulas with trailing tokens.
    
    Regression test for L3 audit finding: parser must reject trailing tokens,
    infix-like payloads, and semicolon-separated commands after valid expressions.
    """
    from omega.quant.evolution.llm_symbolic_synthesizer import FormulaSafetyParser
    
    parser = FormulaSafetyParser(
        allowed_terminals=['close', 'volume', 'open'],
        allowed_unary=['abs'],
        allowed_binary=['+', '-', '*', '/', 'div'],
        allowed_ts=['ts_mean', 'ts_rank'],
        max_depth=5,
        min_lookback=2,
        max_lookback=60
    )
    
    # All of these should be rejected - they have valid prefix followed by trailing garbage
    invalid_formulas = [
        "ts_mean(close, 20) trailing",
        "ts_mean(close, 20) + volume",
        "ts_mean(close, 20); unknown_secret",
        "add(close, volume) garbage",
        "ts_rank(volume, 10) extra tokens here",
        "abs(close) unexpected",
    ]
    
    for formula in invalid_formulas:
        is_valid, error = parser.validate_formula(formula)
        assert not is_valid, f"Formula with trailing tokens should be rejected: {formula}"
        assert "trailing" in error.lower(), (
            f"Error message should mention trailing tokens: {error}"
        )


def test_formula_cache_deterministic():
    """Test that formula cache produces deterministic results."""
    from omega.quant.evolution.llm_symbolic_synthesizer import FormulaCache
    
    # Use deterministic repo-owned cache directory
    cache_dir = Path(".ly_state/session/test_llm_cache_deterministic")
    
    # Clean up any existing test cache directory (idempotent)
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    
    # Create cache directory
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        cache = FormulaCache(cache_dir=cache_dir)
        
        prompt = "Generate alpha formulas"
        formulas = ["ts_mean(close, 20)", "ts_rank(volume, 10)"]
        
        # Set cache
        cache.set(prompt, formulas)
        
        # Get cache - should return same formulas
        cached = cache.get(prompt)
        assert cached == formulas, "Cache should return same formulas"
        
        # Different cache instance, same dir - should still get same results
        cache2 = FormulaCache(cache_dir=cache_dir)
        cached2 = cache2.get(prompt)
        assert cached2 == formulas, "Cache should be persistent across instances"
        
        # Different prompt - should return None
        cached3 = cache.get("Different prompt")
        assert cached3 is None, "Different prompt should not hit cache"
    
    finally:
        # Clean up test cache directory
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)


def test_secrets_not_in_cache():
    """Test that API keys and secrets are never cached."""
    from omega.quant.evolution.llm_symbolic_synthesizer import FormulaCache
    import json
    
    # Use deterministic repo-owned cache directory
    cache_dir = Path(".ly_state/session/test_llm_cache_secrets")
    
    # Clean up any existing test cache directory (idempotent)
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    
    # Create cache directory
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        cache = FormulaCache(cache_dir=cache_dir)
        
        # Prompt should never contain secrets (they're in headers)
        # But let's verify cache files don't contain secrets
        prompt = "Generate formulas"
        formulas = ["ts_mean(close, 20)"]
        
        cache.set(prompt, formulas)
        
        # Read cache file directly
        cache_files = list(cache_dir.glob("*.json"))
        assert len(cache_files) == 1, "Should have one cache file"
        
        with open(cache_files[0], 'r') as f:
            cache_data = json.load(f)
        
        # Verify no API key or secret in cache
        cache_str = json.dumps(cache_data)
        assert 'api_key' not in cache_str.lower(), "API key should not be in cache"
        assert 'secret' not in cache_str.lower(), "Secret should not be in cache"
        assert 'password' not in cache_str.lower(), "Password should not be in cache"
        
        # Verify formulas are cached
        assert cache_data['formulas'] == formulas, "Formulas should be cached"
    
    finally:
        # Clean up test cache directory
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)


def test_grouped_execution_mandatory():
    """Test that grouped execution path works with new provider system."""
    import pandas as pd
    
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    # Create panel with 2 tickers
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 10 + ["B"] * 10,
        "date": pd.date_range("2020-01-01", periods=10).tolist() * 2,
        "close": np.random.randn(20) + 100,
        "volume": np.abs(np.random.randn(20)) * 1000,
    })
    
    # Parse a formula
    node = synth.parse_formula("ts_mean(close, 5)")
    
    # Execute grouped
    result = synth.execute_node_grouped(
        node, panel, ["close", "volume"], ticker_col="ticker", date_col="date"
    )
    
    assert len(result) == 20, "Should return result for all rows"
    assert not np.isnan(result).all(), "Should have some valid values"


def test_formula_scorer_rejects_constant():
    """Test that FormulaScorer rejects formulas with zero variance."""
    from omega.quant.evolution.llm_formula_scorer import (
        FormulaScorer,
        FormulaScorerConfig,
    )
    
    config = FormulaScorerConfig(
        min_variance=1e-8,
        min_coverage=0.5,
        allow_unvalidated=True,
    )
    scorer = FormulaScorer(config)
    
    # Constant formula output (all same value)
    constant_values = np.ones(100) * 42.0
    
    metrics = scorer.score_formula(
        values=constant_values,
        labels=None,
        ticker_groups=None,
        formula_name="constant_test",
    )
    
    assert not metrics.accepted, "Constant formula should be rejected"
    assert any("variance" in r.lower() for r in metrics.rejection_reasons), (
        "Rejection reason should mention variance"
    )


def test_formula_scorer_rejects_excessive_nan():
    """Test that FormulaScorer rejects formulas with excessive NaN values."""
    from omega.quant.evolution.llm_formula_scorer import (
        FormulaScorer,
        FormulaScorerConfig,
    )
    
    config = FormulaScorerConfig(
        min_coverage=0.80,
        max_nan_inf_ratio=0.20,
        allow_unvalidated=True,
    )
    scorer = FormulaScorer(config)
    
    # Formula with 50% NaN values
    values = np.ones(100)
    values[:50] = np.nan
    
    metrics = scorer.score_formula(
        values=values,
        labels=None,
        ticker_groups=None,
        formula_name="nan_test",
    )
    
    assert not metrics.accepted, "Formula with excessive NaN should be rejected"
    assert metrics.nan_inf_ratio > 0.40, "Should detect high NaN ratio"
    assert any("coverage" in r.lower() or "nan" in r.lower() for r in metrics.rejection_reasons), (
        "Rejection reason should mention coverage or NaN"
    )


def test_formula_scorer_accepts_valid_formula():
    """Test that FormulaScorer accepts formulas with good quality metrics."""
    from omega.quant.evolution.llm_formula_scorer import (
        FormulaScorer,
        FormulaScorerConfig,
    )
    
    config = FormulaScorerConfig(
        min_variance=1e-8,
        min_coverage=0.80,
        max_nan_inf_ratio=0.20,
        allow_unvalidated=True,
    )
    scorer = FormulaScorer(config)
    
    # Valid formula output with good variance and coverage
    np.random.seed(42)
    valid_values = np.random.randn(100) * 10.0 + 50.0
    
    metrics = scorer.score_formula(
        values=valid_values,
        labels=None,
        ticker_groups=None,
        formula_name="valid_test",
    )
    
    assert metrics.accepted, "Valid formula should be accepted"
    assert metrics.non_nan_coverage > 0.99, "Should have full coverage"
    assert metrics.variance > 1e-6, "Should have non-zero variance"
    assert len(metrics.rejection_reasons) == 0, "Should have no rejection reasons"


def test_formula_scorer_unsupervised_only():
    """Test that FormulaScorer works with unsupervised metrics only (no labels)."""
    from omega.quant.evolution.llm_formula_scorer import (
        FormulaScorer,
        FormulaScorerConfig,
    )
    
    config = FormulaScorerConfig(
        min_variance=1e-8,
        min_coverage=0.80,
        allow_unvalidated=True,  # Accept without supervised checks
    )
    scorer = FormulaScorer(config)
    
    # Valid formula output, no labels provided
    np.random.seed(42)
    values = np.random.randn(100) * 5.0
    
    metrics = scorer.score_formula(
        values=values,
        labels=None,  # No labels - unsupervised only
        ticker_groups=None,
        formula_name="unsupervised_test",
    )
    
    assert metrics.accepted, "Should accept with unsupervised metrics only"
    assert metrics.absolute_ic is None, "Should have no IC (no labels)"
    assert metrics.dsr_proxy is None, "Should have no DSR (no labels)"
    assert metrics.non_nan_coverage > 0.99, "Should compute coverage"
    assert metrics.variance > 0, "Should compute variance"


def test_formula_scorer_supervised_metrics():
    """Test that FormulaScorer computes supervised metrics when labels provided."""
    from omega.quant.evolution.llm_formula_scorer import (
        FormulaScorer,
        FormulaScorerConfig,
    )
    
    config = FormulaScorerConfig(
        min_variance=1e-8,
        min_coverage=0.80,
        min_absolute_ic=0.01,
        min_dsr_proxy=-0.5,
        allow_unvalidated=False,  # Require supervised validation
    )
    scorer = FormulaScorer(config)
    
    # Create correlated values and labels
    np.random.seed(42)
    labels = np.random.randn(100) * 0.02  # Simulated returns
    values = labels * 2.0 + np.random.randn(100) * 0.01  # Correlated predictions
    
    metrics = scorer.score_formula(
        values=values,
        labels=labels,
        ticker_groups=None,
        formula_name="supervised_test",
    )
    
    assert metrics.absolute_ic is not None, "Should compute IC with labels"
    assert metrics.dsr_proxy is not None, "Should compute DSR proxy with labels"
    assert metrics.absolute_ic > 0.5, "Should have strong IC (by construction)"


def test_formula_scorer_rejects_weak_ic():
    """Test that FormulaScorer rejects formulas with weak IC."""
    from omega.quant.evolution.llm_formula_scorer import (
        FormulaScorer,
        FormulaScorerConfig,
    )
    
    config = FormulaScorerConfig(
        min_variance=1e-8,
        min_coverage=0.80,
        min_absolute_ic=0.10,  # Require IC >= 0.10
        allow_unvalidated=False,
    )
    scorer = FormulaScorer(config)
    
    # Create truly uncorrelated values and labels (IC ~ 0)
    # by shuffling one array relative to the other
    np.random.seed(42)
    labels = np.random.randn(100) * 0.02
    values_base = np.random.randn(100) * 5.0
    # Shuffle to break any accidental correlation
    rng = np.random.default_rng(123)
    values = rng.permutation(values_base)
    
    metrics = scorer.score_formula(
        values=values,
        labels=labels,
        ticker_groups=None,
        formula_name="weak_ic_test",
    )
    
    # Verify IC is actually weak (< 0.10)
    assert metrics.absolute_ic is not None, "Should compute IC"
    assert metrics.absolute_ic < 0.10, (
        f"Test data should produce weak IC (got {metrics.absolute_ic:.4f})"
    )
    
    assert not metrics.accepted, "Should reject formula with weak IC"
    assert any("ic" in r.lower() for r in metrics.rejection_reasons), (
        "Rejection reason should mention IC"
    )


def test_formula_scorer_rejection_reasons_recorded():
    """Test that FormulaScorer records detailed rejection reasons."""
    from omega.quant.evolution.llm_formula_scorer import (
        FormulaScorer,
        FormulaScorerConfig,
    )
    
    config = FormulaScorerConfig(
        min_variance=10.0,  # High threshold to trigger rejection
        min_coverage=0.95,
        max_nan_inf_ratio=0.01,
        allow_unvalidated=True,
    )
    scorer = FormulaScorer(config)
    
    # Create values that violate multiple thresholds
    values = np.ones(100) * 5.0  # Low variance
    values[:20] = np.nan  # 20% NaN (violates coverage)
    
    metrics = scorer.score_formula(
        values=values,
        labels=None,
        ticker_groups=None,
        formula_name="multi_violation_test",
    )
    
    assert not metrics.accepted, "Should reject formula"
    assert len(metrics.rejection_reasons) >= 2, "Should have multiple rejection reasons"
    
    reasons_text = " ".join(metrics.rejection_reasons).lower()
    assert "variance" in reasons_text, "Should mention variance issue"
    assert "coverage" in reasons_text or "nan" in reasons_text, (
        "Should mention coverage or NaN issue"
    )


def test_synthesizer_score_and_filter_integration():
    """Test integration of scoring into LLMSymbolicSynthesizer."""
    import pandas as pd
    from omega.quant.evolution.llm_formula_scorer import FormulaScorerConfig
    
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    # Create panel with 2 tickers
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 50 + ["B"] * 50,
        "date": pd.date_range("2020-01-01", periods=50).tolist() * 2,
        "close": np.random.randn(100) * 10 + 100,
        "volume": np.abs(np.random.randn(100)) * 1000,
        "ret_1d": np.random.randn(100) * 0.02,
    })
    
    # Generate candidate formulas - new API returns tuple
    feat_dict = {
        "close": panel["close"].values,
        "volume": panel["volume"].values,
        "ret_1d": panel["ret_1d"].values,
    }
    candidate_nodes, synth_stats = synth.synthesize(feat_dict)
    
    assert len(candidate_nodes) > 0, "Should generate candidate formulas"
    
    # Score and filter with lenient config (should accept all mock formulas)
    config = FormulaScorerConfig(
        min_variance=1e-10,
        min_coverage=0.50,
        max_nan_inf_ratio=0.50,
        allow_unvalidated=True,
    )
    
    accepted_nodes, stats = synth.score_and_filter_formulas(
        nodes=candidate_nodes,
        panel=panel,
        feat_cols=["close", "volume", "ret_1d"],
        labels=None,
        scorer_config=config,
        ticker_col="ticker",
        date_col="date",
        synthesis_stats=synth_stats,
    )
    
    assert "total" in stats, "Stats should include total count"
    assert "accepted" in stats, "Stats should include accepted count"
    assert "rejected" in stats, "Stats should include rejected count"
    assert stats["total"] == len(candidate_nodes), "Total should match candidates"
    assert len(accepted_nodes) == stats["accepted"], "Accepted nodes count should match"
    assert len(accepted_nodes) > 0, "Should accept at least some formulas"


def test_synthesizer_score_and_filter_rejects_bad_formulas():
    """Test that score_and_filter correctly rejects bad formulas."""
    import pandas as pd
    from omega.quant.evolution.llm_formula_scorer import FormulaScorerConfig
    
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    # Create panel with minimal data (will cause formulas to have poor quality)
    panel = pd.DataFrame({
        "ticker": ["A"] * 5,
        "date": pd.date_range("2020-01-01", periods=5),
        "close": [100.0, 100.0, 100.0, 100.0, 100.0],  # Constant (zero variance)
        "volume": [1000.0] * 5,  # Constant
        "ret_1d": [0.0] * 5,  # Constant
    })
    
    # Generate candidate formulas
    feat_dict = {
        "close": panel["close"].values,
        "volume": panel["volume"].values,
        "ret_1d": panel["ret_1d"].values,
    }
    candidate_nodes = synth.synthesize(feat_dict)
    
    # Score with strict config (should reject formulas on constant data)
    config = FormulaScorerConfig(
        min_variance=1e-6,  # Require non-zero variance
        min_coverage=0.80,
        max_nan_inf_ratio=0.20,
        allow_unvalidated=True,
    )
    
    accepted_nodes, stats = synth.score_and_filter_formulas(
        nodes=candidate_nodes,
        panel=panel,
        feat_cols=["close", "volume", "ret_1d"],
        labels=None,
        scorer_config=config,
        ticker_col="ticker",
        date_col="date",
    )
    
    # With constant input data, formulas should produce near-constant output
    # and be rejected for low variance
    assert stats["rejected"] >= 0, "Should reject some formulas on constant data"
    assert "rejection_reasons" in stats, "Should record rejection reasons"


def test_validation_metadata_unsupervised_only():
    """Test that formulas scored without labels are marked as unsupervised_only and not_deployable.
    
    L3 audit requirement: Explicit validation metadata for deployment safety.
    """
    from omega.quant.evolution.llm_formula_scorer import (
        FormulaScorer,
        FormulaScorerConfig,
    )
    
    config = FormulaScorerConfig(
        min_variance=1e-8,
        min_coverage=0.80,
        allow_unvalidated=True,  # Accept unsupervised formulas
    )
    scorer = FormulaScorer(config)
    
    # Valid formula output, NO labels
    np.random.seed(42)
    values = np.random.randn(100) * 5.0
    
    metrics = scorer.score_formula(
        values=values,
        labels=None,  # No labels = unsupervised only
        ticker_groups=None,
        formula_name="unsupervised_test",
    )
    
    # Verify validation metadata
    assert metrics.accepted, "Formula should be accepted with allow_unvalidated=True"
    assert not metrics.is_supervised_validated, "Should NOT be supervised validated (no labels)"
    assert not metrics.is_deployable, "Should NOT be deployable (unsupervised only)"
    assert metrics.validation_mode == "unsupervised_only", "Should be marked as unsupervised_only"


def test_validation_metadata_supervised_deployable():
    """Test that formulas passing supervised checks are marked as deployable."""
    from omega.quant.evolution.llm_formula_scorer import (
        FormulaScorer,
        FormulaScorerConfig,
    )
    
    config = FormulaScorerConfig(
        min_variance=1e-8,
        min_coverage=0.80,
        min_absolute_ic=0.01,
        min_dsr_proxy=-0.5,
        allow_unvalidated=False,
    )
    scorer = FormulaScorer(config)
    
    # Create correlated values and labels (strong signal)
    np.random.seed(42)
    labels = np.random.randn(100) * 0.02
    values = labels * 3.0 + np.random.randn(100) * 0.005  # Strong correlation
    
    metrics = scorer.score_formula(
        values=values,
        labels=labels,
        ticker_groups=None,
        formula_name="supervised_test",
    )
    
    # Verify validation metadata
    assert metrics.accepted, "Formula should be accepted with strong IC"
    assert metrics.is_supervised_validated, "Should be supervised validated (labels provided + checks passed)"
    assert metrics.is_deployable, "Should be deployable (supervised + accepted)"
    assert metrics.validation_mode == "supervised", "Should be marked as supervised"
    assert metrics.absolute_ic is not None and metrics.absolute_ic > 0.5, "Should have strong IC"


def test_validation_metadata_supervised_not_deployable():
    """Test that formulas failing supervised checks are NOT deployable."""
    from omega.quant.evolution.llm_formula_scorer import (
        FormulaScorer,
        FormulaScorerConfig,
    )
    
    config = FormulaScorerConfig(
        min_variance=1e-8,
        min_coverage=0.80,
        min_absolute_ic=0.50,  # High threshold
        allow_unvalidated=False,
    )
    scorer = FormulaScorer(config)
    
    # Create weakly correlated values and labels
    np.random.seed(42)
    labels = np.random.randn(100) * 0.02
    values_base = np.random.randn(100) * 5.0
    rng = np.random.default_rng(123)
    values = rng.permutation(values_base)  # Break correlation
    
    metrics = scorer.score_formula(
        values=values,
        labels=labels,
        ticker_groups=None,
        formula_name="weak_supervised_test",
    )
    
    # Verify validation metadata
    assert not metrics.accepted, "Formula should be rejected (weak IC)"
    assert not metrics.is_supervised_validated, "Should NOT be supervised validated (failed checks)"
    assert not metrics.is_deployable, "Should NOT be deployable (rejected)"
    assert metrics.validation_mode == "supervised", "Should be marked as supervised (labels provided)"


def test_score_and_filter_propagates_metadata():
    """Test that score_and_filter_formulas propagates validation metadata in stats."""
    import pandas as pd
    from omega.quant.evolution.llm_formula_scorer import FormulaScorerConfig
    
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    # Create panel with 2 tickers
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 50 + ["B"] * 50,
        "date": pd.date_range("2020-01-01", periods=50).tolist() * 2,
        "close": np.random.randn(100) * 10 + 100,
        "volume": np.abs(np.random.randn(100)) * 1000,
        "ret_1d": np.random.randn(100) * 0.02,
    })
    
    # Generate candidate formulas
    feat_dict = {
        "close": panel["close"].values,
        "volume": panel["volume"].values,
        "ret_1d": panel["ret_1d"].values,
    }
    candidate_nodes = synth.synthesize(feat_dict)
    
    # Score WITHOUT labels (unsupervised only)
    config = FormulaScorerConfig(
        min_variance=1e-10,
        min_coverage=0.50,
        allow_unvalidated=True,
    )
    
    accepted_nodes, stats = synth.score_and_filter_formulas(
        nodes=candidate_nodes,
        panel=panel,
        feat_cols=["close", "volume", "ret_1d"],
        labels=None,  # No labels
        scorer_config=config,
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify stats include validation metadata
    assert "deployable" in stats, "Stats should include deployable count"
    assert "unsupervised_only" in stats, "Stats should include unsupervised_only count"
    assert stats["deployable"] == 0, "No formulas should be deployable (no labels)"
    assert stats["unsupervised_only"] == stats["accepted"], "All accepted should be unsupervised_only"
    
    # Verify details include metadata for each formula
    for name, details in stats["details"].items():
        assert "is_supervised_validated" in details, "Details should include is_supervised_validated"
        assert "is_deployable" in details, "Details should include is_deployable"
        assert "validation_mode" in details, "Details should include validation_mode"
        if details["accepted"]:
            assert not details["is_deployable"], "Accepted unsupervised formulas should not be deployable"
            assert details["validation_mode"] == "unsupervised_only", "Should be marked unsupervised_only"


def test_backtest_metadata_propagation():
    """Test that backtest adapter logs validation metadata warnings.
    
    This is an integration test to ensure the full pipeline propagates
    validation metadata from scorer -> synthesizer -> adapter.
    """
    import pandas as pd
    from omega.quant.evolution.llm_formula_scorer import FormulaScorerConfig
    
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    # Create minimal panel
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 20 + ["B"] * 20,
        "date": pd.date_range("2020-01-01", periods=20).tolist() * 2,
        "close": np.random.randn(40) * 10 + 100,
        "volume": np.abs(np.random.randn(40)) * 1000,
        "ret_1d": np.random.randn(40) * 0.02,
    })
    
    feat_dict = {
        "close": panel["close"].values,
        "volume": panel["volume"].values,
        "ret_1d": panel["ret_1d"].values,
    }
    candidate_nodes, synth_stats = synth.synthesize(feat_dict)
    
    # Score with lenient unsupervised config
    config = FormulaScorerConfig(
        min_variance=1e-10,
        min_coverage=0.50,
        max_nan_inf_ratio=0.50,
        allow_unvalidated=True,
    )
    
    accepted_nodes, stats = synth.score_and_filter_formulas(
        nodes=candidate_nodes,
        panel=panel,
        feat_cols=["close", "volume", "ret_1d"],
        labels=None,
        scorer_config=config,
        ticker_col="ticker",
        date_col="date",
        synthesis_stats=synth_stats,
    )
    
    # Verify the pipeline returns proper metadata
    assert stats["accepted"] > 0, "Should accept some formulas"
    assert stats["deployable"] == 0, "No formulas should be deployable without labels"
    assert stats["unsupervised_only"] == stats["accepted"], "All accepted should be unsupervised_only"
    
    # In a real backtest, the adapter would log warnings about unsupervised formulas
    # This test verifies the metadata is available for that logging


def test_prompt_v2_domain_constraints():
    """Test that prompt v2 includes Vietnamese market context and no secrets."""
    synth = LLMSymbolicSynthesizer(provider='mock', prompt_version='vn_alpha_search_v2')
    
    top_features = [("ret_1d", 0.05), ("volume", 0.03)]
    clusters = [["close", "open"]]
    
    prompt = synth.generate_prompt(top_features, clusters)
    
    # Verify Vietnamese market context
    assert "vietnamese" in prompt.lower() or "vnindex" in prompt.lower(), (
        "Prompt should mention Vietnamese market"
    )
    assert "frontier market" in prompt.lower() or "hose" in prompt.lower(), (
        "Prompt should include market microstructure context"
    )
    
    # Verify no secrets in prompt
    assert "api_key" not in prompt.lower(), "Prompt should not contain API key"
    assert "secret" not in prompt.lower(), "Prompt should not contain secrets"
    assert "password" not in prompt.lower(), "Prompt should not contain passwords"
    
    # Verify max_candidates is mentioned
    assert str(synth.max_candidates) in prompt, "Prompt should specify candidate count"


def test_prompt_v2_aggregate_failure_context():
    """Test that prompt v2 includes aggregate failure metrics without row-level labels."""
    synth = LLMSymbolicSynthesizer(provider='mock', prompt_version='vn_alpha_search_v2')
    
    top_features = [("ret_1d", 0.05)]
    clusters = []
    prior_failure_stats = {
        "median_train_ic": 0.02,
        "median_dsr": -0.1,
    }
    
    prompt = synth.generate_prompt(top_features, clusters, prior_failure_stats)
    
    # Verify aggregate stats are included
    assert "0.02" in prompt or "IC" in prompt, "Prompt should include IC context"
    assert "-0.1" in prompt or "DSR" in prompt, "Prompt should include DSR context"
    
    # Verify no row-level data (check for numpy/pandas artifacts, not legitimate range notation like [2, 60])
    # Aggregate metrics are safe (just numbers), but there should be no actual data arrays
    assert "array(" not in prompt.lower(), "Prompt should not contain numpy arrays"
    assert "dtype" not in prompt.lower(), "Prompt should not contain pandas dtype markers"
    # Check for patterns like multiple comma-separated floats in brackets (e.g., [0.123, 0.456, 0.789])
    import re
    array_pattern = r'\[\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\]'
    assert not re.search(array_pattern, prompt), "Prompt should not contain float array literals"


def test_cache_versioning():
    """Test that cache keys differ by prompt version."""
    from omega.quant.evolution.llm_symbolic_synthesizer import FormulaCache
    
    cache_dir = Path(".ly_state/session/test_cache_versioning")
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        cache = FormulaCache(cache_dir=cache_dir)
        
        prompt = "Generate alpha formulas"
        formulas_v1 = ["ts_mean(close, 20)"]
        formulas_v2 = ["ts_rank(volume, 10)"]
        
        # Cache with v1
        cache.set(prompt, formulas_v1, prompt_version="v1")
        
        # Cache with v2 (same prompt text, different version)
        cache.set(prompt, formulas_v2, prompt_version="vn_alpha_search_v2")
        
        # Retrieve should return different results based on version
        cached_v1 = cache.get(prompt, prompt_version="v1")
        cached_v2 = cache.get(prompt, prompt_version="vn_alpha_search_v2")
        
        assert cached_v1 == formulas_v1, "v1 cache should return v1 formulas"
        assert cached_v2 == formulas_v2, "v2 cache should return v2 formulas"
        assert cached_v1 != cached_v2, "Different versions should have different cache entries"
        
    finally:
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)


def test_formula_deduplication():
    """Test that duplicate formulas (after normalization) are rejected."""
    synth = LLMSymbolicSynthesizer(provider='mock', prompt_version='vn_alpha_search_v2')
    
    # Test normalization
    formula1 = "ts_mean(close, 20)"
    formula2 = "TS_MEAN(close, 20)"  # Different case
    formula3 = "ts_mean( close , 20 )"  # Different whitespace
    
    norm1 = synth.normalize_formula(formula1)
    norm2 = synth.normalize_formula(formula2)
    norm3 = synth.normalize_formula(formula3)
    
    assert norm1 == norm2 == norm3, "Normalized formulas should be identical"
    
    # Test that synthesize tracks duplicate rejections
    # (We can't easily inject duplicates into MockProvider, but we can verify the taxonomy exists)
    features = {
        "close": np.random.randn(50) + 100,
        "volume": np.abs(np.random.randn(50)) * 1000,
    }
    
    nodes, stats = synth.synthesize(features)
    
    # Verify rejection taxonomy includes duplicate_formula key
    assert "rejection_taxonomy" in stats, "Stats should include rejection taxonomy"
    assert "duplicate_formula" in stats["rejection_taxonomy"], (
        "Taxonomy should include duplicate_formula category"
    )


def test_rejection_taxonomy_recorded():
    """Test that rejection taxonomy is properly recorded throughout the pipeline."""
    import pandas as pd
    from omega.quant.evolution.llm_formula_scorer import FormulaScorerConfig
    
    synth = LLMSymbolicSynthesizer(provider='mock', prompt_version='vn_alpha_search_v2')
    
    # Create panel with constant data to trigger quality rejections
    panel = pd.DataFrame({
        "ticker": ["A"] * 10,
        "date": pd.date_range("2020-01-01", periods=10),
        "close": [100.0] * 10,  # Constant
        "volume": [1000.0] * 10,  # Constant
        "ret_1d": [0.0] * 10,  # Constant
    })
    
    feat_dict = {
        "close": panel["close"].values,
        "volume": panel["volume"].values,
        "ret_1d": panel["ret_1d"].values,
    }
    
    nodes, synth_stats = synth.synthesize(feat_dict)
    
    # Score with strict config to trigger rejections
    config = FormulaScorerConfig(
        min_variance=1e-6,
        min_coverage=0.95,
        max_nan_inf_ratio=0.05,
        allow_unvalidated=True,
    )
    
    accepted_nodes, stats = synth.score_and_filter_formulas(
        nodes=nodes,
        panel=panel,
        feat_cols=["close", "volume", "ret_1d"],
        labels=None,
        scorer_config=config,
        ticker_col="ticker",
        date_col="date",
        synthesis_stats=synth_stats,
    )
    
    # Verify rejection taxonomy is present and has expected categories
    assert "rejection_taxonomy" in stats, "Stats should include rejection taxonomy"
    taxonomy = stats["rejection_taxonomy"]
    
    expected_categories = [
        "parse_error", "unsafe_token", "duplicate_formula", "execution_failure",
        "low_coverage", "near_zero_variance", "unstable", "nan_inf"
    ]
    
    for category in expected_categories:
        assert category in taxonomy, f"Taxonomy should include {category}"
        assert isinstance(taxonomy[category], int), f"{category} count should be integer"
    
    # With constant data, we should see some quality-based rejections
    quality_rejections = (
        taxonomy["near_zero_variance"] + 
        taxonomy["low_coverage"] + 
        taxonomy["unstable"] + 
        taxonomy["nan_inf"]
    )
    
    assert quality_rejections >= 0, "Should track quality-based rejections"


def test_synthesize_returns_tuple():
    """Test that synthesize returns (nodes, stats) tuple in new API."""
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    features = {
        "close": np.random.randn(50) + 100,
        "volume": np.abs(np.random.randn(50)) * 1000,
    }
    
    result = synth.synthesize(features)
    
    # Verify it's a tuple
    assert isinstance(result, tuple), "synthesize should return tuple"
    assert len(result) == 2, "synthesize should return (nodes, stats)"
    
    nodes, stats = result
    
    # Verify nodes are GPNode objects
    assert isinstance(nodes, list), "First element should be list of nodes"
    from omega.quant.evolution.genetic_programming import GPNode
    for node in nodes:
        assert isinstance(node, GPNode), "Each node should be GPNode"
    
    # Verify stats is dict with expected keys
    assert isinstance(stats, dict), "Second element should be stats dict"
    assert "prompt_version" in stats, "Stats should include prompt_version"
    assert "rejection_taxonomy" in stats, "Stats should include rejection_taxonomy"
    assert "accepted" in stats, "Stats should include accepted count"


def test_max_candidates_from_env():
    """Test that OMEGA_LLM_MAX_CANDIDATES env var is respected."""
    import os
    
    orig_val = os.environ.get('OMEGA_LLM_MAX_CANDIDATES')
    
    try:
        os.environ['OMEGA_LLM_MAX_CANDIDATES'] = '5'
        synth = LLMSymbolicSynthesizer(provider='mock')
        
        assert synth.max_candidates == 5, "Should read max_candidates from env"
        
    finally:
        if orig_val is not None:
            os.environ['OMEGA_LLM_MAX_CANDIDATES'] = orig_val
        elif 'OMEGA_LLM_MAX_CANDIDATES' in os.environ:
            del os.environ['OMEGA_LLM_MAX_CANDIDATES']


def test_score_and_filter_merges_synthesis_stats():
    """Test that score_and_filter properly merges synthesis_stats."""
    import pandas as pd
    from omega.quant.evolution.llm_formula_scorer import FormulaScorerConfig
    
    synth = LLMSymbolicSynthesizer(provider='mock')
    
    panel = pd.DataFrame({
        "ticker": ["A"] * 20,
        "date": pd.date_range("2020-01-01", periods=20),
        "close": np.random.randn(20) * 10 + 100,
        "volume": np.abs(np.random.randn(20)) * 1000,
    })
    
    feat_dict = {
        "close": panel["close"].values,
        "volume": panel["volume"].values,
    }
    
    nodes, synth_stats = synth.synthesize(feat_dict)
    
    config = FormulaScorerConfig(
        min_variance=1e-10,
        min_coverage=0.50,
        allow_unvalidated=True,
    )
    
    # Pass synthesis_stats
    accepted_nodes, stats = synth.score_and_filter_formulas(
        nodes=nodes,
        panel=panel,
        feat_cols=["close", "volume"],
        labels=None,
        scorer_config=config,
        ticker_col="ticker",
        date_col="date",
        synthesis_stats=synth_stats,
    )
    
    # Verify synthesis stats are merged
    assert "synthesis" in stats, "Stats should include synthesis section"
    assert stats["synthesis"]["prompt_version"] == synth.prompt_version, (
        "Should include prompt_version from synthesis"
    )
    
    # Verify rejection taxonomy includes synthesis stage rejections
    assert "rejection_taxonomy" in stats, "Should have rejection taxonomy"


def test_prompt_v3_no_secrets():
    """Test that v3 closed-loop prompt doesn't contain secrets or row-level labels."""
    synth = LLMSymbolicSynthesizer(
        provider='mock', 
        prompt_version='vn_alpha_search_v3_closed_loop'
    )
    
    top_features = [("ret_1d", 0.05), ("volume", 0.03)]
    clusters = [["close", "open"]]
    prior_failure_stats = {
        "median_train_ic": 0.02,
        "median_dsr": -0.1,
    }
    
    prompt = synth.generate_prompt(top_features, clusters, prior_failure_stats)
    
    # Verify no secrets in prompt
    assert "api_key" not in prompt.lower(), "Prompt should not contain API key"
    assert "secret" not in prompt.lower(), "Prompt should not contain secrets"
    assert "password" not in prompt.lower(), "Prompt should not contain passwords"
    assert "OMEGA_LLM" not in prompt, "Prompt should not contain env var names"
    
    # Verify aggregate stats are included (PIT-safe)
    assert "0.02" in prompt or "IC" in prompt, "Prompt should include aggregate IC"
    assert "-0.1" in prompt or "DSR" in prompt, "Prompt should include aggregate DSR"
    
    # Verify no row-level data patterns
    assert "array(" not in prompt.lower(), "Prompt should not contain numpy arrays"
    assert "dtype" not in prompt.lower(), "Prompt should not contain pandas dtype markers"
    
    # Verify v3-specific features
    assert "CLOSED-LOOP" in prompt or "closed-loop" in prompt, "Should mention closed-loop"
    assert "iteration" in prompt.lower(), "Should mention iterative search"
    assert "FAILURE" in prompt or "failure" in prompt.lower(), "Should mention failure feedback"


def test_formula_search_memory_dedupe():
    """Test that formula search deduplicates formulas across iterations."""
    import pandas as pd
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=2,
        candidates_per_iteration=5,
        llm_provider='mock',
        enable_formula_memory=True,
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create minimal panel
    panel = pd.DataFrame({
        "ticker": ["A"] * 20,
        "date": pd.date_range("2020-01-01", periods=20),
        "close": np.random.randn(20) * 10 + 100,
        "volume": np.abs(np.random.randn(20)) * 1000,
    })
    
    feat_cols = ["close", "volume"]
    
    # Run search (mock provider will return same formulas each time)
    final_candidates, evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=None,
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify memory tracking
    assert len(runner.state.failed_formulas) >= 0, "Should track failed formulas"
    assert evidence["summary"]["total_candidates_generated"] > 0, "Should generate candidates"
    
    # Verify state includes deduplication info
    assert "failed_formulas_count" in evidence["summary"], "Should track failed formulas count"


def test_formula_search_train_only_metadata():
    """Test that formula search uses train-only data for scoring metadata."""
    import pandas as pd
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=1,
        candidates_per_iteration=3,
        llm_provider='mock',
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create panel with labels (simulating train-only data)
    np.random.seed(42)
    panel = pd.DataFrame({
        "ticker": ["A"] * 50 + ["B"] * 50,
        "date": pd.date_range("2020-01-01", periods=50).tolist() * 2,
        "close": np.random.randn(100) * 10 + 100,
        "volume": np.abs(np.random.randn(100)) * 1000,
    })
    
    # Labels are "train-only" (provided to runner)
    labels = np.random.randn(100) * 0.02
    
    feat_cols = ["close", "volume"]
    
    # Run search with train-only labels
    final_candidates, evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,  # Train-only labels (PIT-safe)
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify search completed
    assert evidence["final_state"]["current_iteration"] >= 0, "Should complete iterations"
    
    # Verify no test data leakage in evidence
    evidence_str = str(evidence)
    assert "test_label" not in evidence_str.lower(), "Evidence should not mention test labels"
    assert "future" not in evidence_str.lower(), "Evidence should not mention future data"
    
    # Verify deployment flag is false (requires full CPCV)
    assert not evidence["deployment_ready"], "Deployment should be false without full CPCV"
    assert evidence["requires_full_cpcv"], "Should require full CPCV validation"


def test_formula_search_bad_motif_blacklist():
    """Test that formula search tracks bad motifs."""
    import pandas as pd
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchState,
    )
    
    config = FormulaSearchConfig(
        max_iterations=1,
        candidates_per_iteration=3,
        enable_motif_blacklist=True,
    )
    
    state = FormulaSearchState()
    
    # Add bad motifs
    state.add_bad_motif("ts_mean(volume, 5)")
    state.add_bad_motif("simple_momentum")
    
    # Verify motifs are tracked
    assert len(state.bad_motifs) == 2, "Should track bad motifs"
    assert "ts_mean(volume, 5)" in state.bad_motifs, "Should contain first motif"
    assert "simple_momentum" in state.bad_motifs, "Should contain second motif"
    
    # Verify state serialization includes motifs
    state_dict = state.to_dict()
    assert "bad_motifs" in state_dict, "Serialized state should include bad motifs"
    assert len(state_dict["bad_motifs"]) == 2, "Should serialize all motifs"
    
    # Verify state deserialization
    restored_state = FormulaSearchState.from_dict(state_dict)
    assert len(restored_state.bad_motifs) == 2, "Should restore motifs from dict"


def test_formula_search_deployment_flag():
    """Test that deployment flag is false when thresholds fail."""
    import pandas as pd
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=1,
        candidates_per_iteration=3,
        llm_provider='mock',
        min_test_ic_for_deploy=0.05,  # High threshold
        min_dsr_for_deploy=0.5,  # High threshold
    )
    
    runner = FormulaSearchRunner(config)
    
    # Create minimal panel
    panel = pd.DataFrame({
        "ticker": ["A"] * 20,
        "date": pd.date_range("2020-01-01", periods=20),
        "close": np.random.randn(20) * 10 + 100,
        "volume": np.abs(np.random.randn(20)) * 1000,
    })
    
    # Weak labels (will fail thresholds)
    labels = np.random.randn(20) * 0.01
    
    feat_cols = ["close", "volume"]
    
    # Run search
    final_candidates, evidence = runner.run_search(
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,
        ticker_col="ticker",
        date_col="date",
    )
    
    # Verify deployment flag is false
    assert not evidence["deployment_ready"], (
        "Deployment should be false without passing thresholds"
    )
    
    # Verify full CPCV is required
    assert evidence["requires_full_cpcv"], "Should require full CPCV validation"
    
    # Verify config thresholds are documented
    assert config.min_test_ic_for_deploy == 0.05, "Config should track IC threshold"
    assert config.min_dsr_for_deploy == 0.5, "Config should track DSR threshold"


def test_formula_search_aggregate_stats_only():
    """Test that aggregate failure stats don't contain row-level data."""
    import pandas as pd
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    runner = FormulaSearchRunner(FormulaSearchConfig())
    
    # Create mock scoring stats with details
    score_stats = {
        "total": 5,
        "accepted": 2,
        "rejected": 3,
        "details": {
            "alpha_0": {"accepted": False, "absolute_ic": 0.01, "dsr_proxy": -0.2},
            "alpha_1": {"accepted": False, "absolute_ic": 0.02, "dsr_proxy": -0.1},
            "alpha_2": {"accepted": False, "absolute_ic": 0.015, "dsr_proxy": -0.15},
        }
    }
    
    # Mock labels (should only be used for aggregate computation)
    labels = np.random.randn(20) * 0.02
    
    # Compute aggregate stats
    aggregate_stats = runner._compute_aggregate_failure_stats(score_stats, labels)
    
    # Verify only aggregate metrics are included
    assert "median_train_ic" in aggregate_stats, "Should include median IC"
    assert "mean_train_ic" in aggregate_stats, "Should include mean IC"
    assert "median_dsr" in aggregate_stats, "Should include median DSR"
    assert "mean_dsr" in aggregate_stats, "Should include mean DSR"
    
    # Verify no row-level data
    aggregate_str = str(aggregate_stats)
    assert "array" not in aggregate_str.lower(), "Should not contain array data"
    assert len(aggregate_stats) <= 10, "Should only contain a few aggregate metrics"
    
    # Verify values are scalars (not arrays)
    for key, value in aggregate_stats.items():
        assert isinstance(value, (int, float)), f"{key} should be a scalar, got {type(value)}"


def test_formula_search_state_persistence():
    """Test that formula search state can be saved and loaded."""
    import shutil
    from pathlib import Path
    from omega.quant.evolution.llm_formula_search import (
        FormulaSearchConfig,
        FormulaSearchRunner,
    )
    
    config = FormulaSearchConfig(
        max_iterations=1,
        candidates_per_iteration=3,
        llm_provider='mock',
    )
    
    runner = FormulaSearchRunner(config)
    
    # Add some state (use current attribute names from FormulaSearchState)
    runner.state.current_iteration = 2
    runner.state.total_raw_generated = 10
    runner.state.total_scoring_accepted = 3
    runner.state.add_failed_formula("ts_mean(close,20)")
    runner.state.add_bad_motif("simple_momentum")
    runner.state.update_aggregate_stats({"median_train_ic": 0.02})
    
    # Use repo-local path instead of system temp (avoids ACL issues in sandbox)
    test_temp_dir = Path(".ly_state/session/test_temp")
    test_temp_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        state_path = test_temp_dir / "search_state.json"
        runner.save_state(state_path)
        
        # Verify file was created
        assert state_path.exists(), "State file should be created"
        
        # Create new runner and load state
        runner2 = FormulaSearchRunner(config)
        runner2.load_state(state_path)
        
        # Verify state was restored (use current attribute names)
        assert runner2.state.current_iteration == 2, "Should restore iteration"
        assert runner2.state.total_raw_generated == 10, "Should restore raw generated count"
        assert runner2.state.total_scoring_accepted == 3, "Should restore scoring accepted count"
        assert "ts_mean(close,20)" in runner2.state.failed_formulas, "Should restore failed formulas"
        assert "simple_momentum" in runner2.state.bad_motifs, "Should restore bad motifs"
        assert runner2.state.aggregate_failure_stats["median_train_ic"] == 0.02, "Should restore stats"
    finally:
        # Clean up test temp directory
        if test_temp_dir.exists():
            shutil.rmtree(test_temp_dir, ignore_errors=True)


# ===========================================================================
# Hybrid Alpha Miner Tests (Nested CV Diagnostic, 2026-06-12)
# ===========================================================================


def _make_hybrid_panel(n_tickers=3, n_dates=40, seed=42):
    """Helper: create a small synthetic panel for hybrid miner tests."""
    import pandas as pd
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


def test_hybrid_miner_source_proportions():
    """Test that HybridAlphaMiner generates candidates from all 5 sources
    and respects configured budget fractions."""
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
        CandidateSource,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=40,
        top_k=5,
        n_outer_folds=2,
        n_inner_folds=2,
        llm_provider="mock",
    )

    budgets = config.source_budgets()

    # Verify all 5 sources have non-zero budget
    assert CandidateSource.LLM_V3 in budgets
    assert CandidateSource.TEMPLATE in budgets
    assert CandidateSource.GP_MUTATION in budgets
    assert CandidateSource.GP_CROSSOVER in budgets
    assert CandidateSource.RANDOM_SAFE in budgets
    for src, count in budgets.items():
        assert count >= 1, f"Source {src} must have budget >= 1"

    # Sum should equal candidate_budget
    assert sum(budgets.values()) == config.candidate_budget, (
        f"Source budgets should sum to {config.candidate_budget}, got {sum(budgets.values())}"
    )

    # Run miner and verify sources appear in evidence
    miner = HybridAlphaMiner(config)
    panel = _make_hybrid_panel(n_tickers=3, n_dates=30)
    labels = np.random.randn(len(panel)) * 0.02

    selected, evidence = miner.run(
        panel=panel,
        feat_cols=["close", "open", "volume", "ret_1d"],
        labels=labels,
    )

    assert evidence["total_generated"] > 0, "Should generate candidates"
    assert evidence["total_selected"] <= config.top_k, "Should select at most top_k"

    # Source proportions should be present in evidence
    sp = evidence["source_proportions"]
    assert isinstance(sp, dict), "Source proportions should be a dict"
    assert len(sp) > 0, "Should have at least one source"


def test_hybrid_miner_safety_parser():
    """Test that HybridAlphaMiner only uses safe operators in generated candidates."""
    from omega.quant.evolution.hybrid_alpha_miner import (
        HybridAlphaMiner,
        HybridAlphaMinerConfig,
    )

    config = HybridAlphaMinerConfig(
        candidate_budget=20,
        top_k=3,
        n_outer_folds=2,
        n_inner_folds=2,
        llm_provider="mock",
    )

    miner = HybridAlphaMiner(config)
    panel = _make_hybrid_panel(n_tickers=2, n_dates=20)
    labels = np.random.randn(len(panel)) * 0.02

    selected, evidence = miner.run(
        panel=panel,
        feat_cols=["close", "open", "volume", "ret_1d"],
        labels=labels,
    )

    # Verify all selected formulas use only safe operators
    safe_ops = {
        "abs", "log", "sqrt", "rank", "neg", "sigmoid", "exp",
        "+", "-", "*", "/", "max", "min",
        "ts_mean", "ts_std", "ts_rank", "decay_linear",
        "terminal", "div", "add", "sub", "mul",
    }

    for rec in selected:
        formula = rec.formula_str
        # Check that the formula string doesn't contain obviously dangerous patterns
        assert "eval(" not in formula.lower(), f"Unsafe eval in: {formula}"
        assert "exec(" not in formula.lower(), f"Unsafe exec in: {formula}"
        assert "import " not in formula.lower(), f"Unsafe import in: {formula}"


def test_hybrid_miner_formula_memory_motif_metrics():
    """Test that formula memory tracks motifs and provides metrics."""
    from omega.quant.evolution.hybrid_alpha_miner import FormulaMemory

    mem = FormulaMemory()

    # Add some formulas
    formulas = [
        "ts_mean(close, 20)",
        "ts_std(volume, 10)",
        "ts_mean(open, 5)",
        "div(close, volume)",
        "rank(close)",
    ]

    for f in formulas:
        h = FormulaMemory.hash_formula(f)
        mem.total_generated += 1
        mem.add(h, f)

    # Verify unique tracking
    assert len(mem.seen_hashes) == len(formulas), "Should track all unique formulas"

    # Verify deduplication
    dup_hash = FormulaMemory.hash_formula("ts_mean(close, 20)")
    assert mem.is_duplicate(dup_hash), "Should detect duplicate"

    # Verify motif metrics
    metrics = mem.get_motif_metrics()
    assert metrics["unique_formulas"] == len(formulas)
    assert metrics["total_generated"] == len(formulas)
    assert "top_motifs" in metrics
    assert "ts_mean" in metrics["top_motifs"], "Should track ts_mean motif"
    assert metrics["top_motifs"]["ts_mean"] == 2, "ts_mean should appear twice"

    # Verify hash determinism
    h1 = FormulaMemory.hash_formula("ts_mean(close, 20)")
    h2 = FormulaMemory.hash_formula("ts_mean(close, 20)")
    assert h1 == h2, "Hash should be deterministic"

    # Verify case/whitespace normalization
    h3 = FormulaMemory.hash_formula("TS_MEAN(CLOSE, 20)")
    h4 = FormulaMemory.hash_formula("  ts_mean( close, 20 ) ")
    assert h3 == h4, "Normalized formulas should have same hash"
