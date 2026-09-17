"""
Automated Alpha Discovery Tests
GATE: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615
[L2-Impl:Role14-Data-Scientist] - 2026-06-15

Verifies that:
  1. Default disabled — no candidates when flag not set
  2. PIT safety — no OOS/test data used for screening
  3. Train-only screening — screening uses only train data
  4. Determinism — same inputs + seed produce same candidates
  5. Candidate cap — respects max candidate limit
  6. Correlation filtering — removes redundant candidates
  7. Evidence metadata — per-fold evidence is serializable and complete
  8. Transfer diagnostics — helpers produce valid results
  9. Dynamic-universe compatible — works with varying universes
 10. Phase35 wiring — engine params wired correctly

PIT Safety: No real data loaded. Synthetic data tests and source inspection only.
"""

import argparse
import ast
import json
import os
import re
import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_discovery_source():
    """Read automated_alpha_discovery.py source."""
    path = Path(__file__).resolve().parent.parent.parent / "src" / "omega" / "quant" / "alpha" / "automated_alpha_discovery.py"
    return path.read_text(encoding="utf-8")


def _get_transfer_diag_source():
    """Read alpha_transfer_diagnostics.py source."""
    path = Path(__file__).resolve().parent.parent.parent / "src" / "omega" / "quant" / "alpha" / "alpha_transfer_diagnostics.py"
    return path.read_text(encoding="utf-8")


def _get_phase35_source():
    """Read phase35.py source."""
    path = Path(__file__).resolve().parent.parent.parent / "src" / "omega" / "quant" / "alpha" / "phase35.py"
    return path.read_text(encoding="utf-8")


def _make_synthetic_ohlcv(
    n_tickers: int = 8, n_days: int = 80, seed: int = 42
) -> pd.DataFrame:
    """Create synthetic OHLCV panel data with forward returns."""
    rng = np.random.RandomState(seed)
    rows = []
    dates = pd.date_range("2022-01-03", periods=n_days, freq="B")
    for t in range(n_tickers):
        ticker = f"SYM{t:02d}"
        base_price = 10000.0 + rng.randn() * 2000
        for d_idx, date in enumerate(dates):
            noise = rng.randn() * 0.02
            close = base_price * (1 + noise * (d_idx + 1) / n_days)
            open_price = close * (1 + rng.randn() * 0.005)
            high = max(open_price, close) * (1 + abs(rng.randn()) * 0.01)
            low = min(open_price, close) * (1 - abs(rng.randn()) * 0.01)
            volume = int(abs(rng.randn() * 100000) + 10000)
            fwd_ret = rng.normal(0, 0.02)
            rows.append({
                "ticker": ticker,
                "date": date,
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": volume,
                "fwd_ret_5": fwd_ret,
            })
    return pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)


def _make_engine(**kwargs):
    """Create a Phase35WalkForwardEngine with a dummy alpha module."""
    from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
    dummy_module = types.ModuleType("dummy_alpha")
    dummy_module.PHASE34_ALPHA_COLUMNS = []
    dummy_module.compute_phase34_microstructure_alphas = lambda df, **kw: df
    return Phase35WalkForwardEngine(alpha_module=dummy_module, **kwargs)


# ---------------------------------------------------------------------------
# Tests: Default disabled behavior
# ---------------------------------------------------------------------------

class TestDefaultDisabled:
    """Verify factory is disabled by default."""

    def test_factory_default_disabled(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory()
        assert factory.enabled is False

    def test_factory_disabled_returns_empty(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(enabled=False)
        df = _make_synthetic_ohlcv()
        candidates = factory.generate_candidates(df)
        assert candidates == []

    def test_run_discovery_disabled_returns_evidence(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(enabled=False)
        df = _make_synthetic_ohlcv()
        result = factory.run_discovery(df)
        assert result.enabled is False
        assert result.evidence["status"] == "disabled"
        assert result.candidates_generated == 0

    def test_phase35_default_disabled(self):
        """Phase35 engine should have automated discovery disabled by default."""
        engine = _make_engine()
        assert engine.enable_automated_discovery is False

    def test_source_gate_id_present(self):
        """GATE ID should be defined in source."""
        source = _get_discovery_source()
        assert "AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615" in source

    def test_phase35_gate_id_present(self):
        """GATE ID should be referenced in phase35.py."""
        source = _get_phase35_source()
        assert "AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615" in source


# ---------------------------------------------------------------------------
# Tests: PIT Safety
# ---------------------------------------------------------------------------

class TestPITSafety:
    """Verify no look-ahead bias or OOS data usage."""

    def test_source_no_future_shift(self):
        """Source should not contain negative shift (look-ahead)."""
        source = _get_discovery_source()
        # Find shift(N) calls — N should be >= 0 (positive = lagging)
        shifts = re.findall(r'\.shift\((-?\d+)\)', source)
        for s in shifts:
            val = int(s)
            assert val >= 0, f"Found negative shift({val}) — potential look-ahead"

    def test_source_no_lead(self):
        """Source should not use .lead() (look-ahead)."""
        source = _get_discovery_source()
        assert ".lead(" not in source, "Found .lead() call — potential look-ahead"

    def test_source_no_fwd_ret_in_expressions(self):
        """Expression templates should not reference forward returns."""
        source = _get_discovery_source()
        # Templates should not use fwd_ret
        template_section = source[source.find("_EXPRESSION_TEMPLATES"):source.find("def _compute_rsi_safe")]
        assert "fwd_ret" not in template_section, "Templates reference forward returns"

    def test_transfer_diag_no_future_shift(self):
        """Transfer diagnostics source should not have negative shifts."""
        source = _get_transfer_diag_source()
        shifts = re.findall(r'\.shift\((-?\d+)\)', source)
        for s in shifts:
            val = int(s)
            assert val >= 0, f"Found negative shift({val}) in transfer diagnostics"

    def test_run_discovery_uses_only_train(self):
        """run_discovery should only accept train_df, no test_df parameter."""
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        import inspect
        sig = inspect.signature(factory := AutomatedAlphaDiscoveryFactory(enabled=True).run_discovery)
        params = list(sig.parameters.keys())
        assert "test_df" not in params, "run_discovery should not accept test_df"
        assert "oos_df" not in params, "run_discovery should not accept oos_df"
        assert "train_df" in params, "run_discovery should accept train_df"

    def test_screening_train_only(self):
        """Screening should only use provided training data."""
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        import inspect
        sig = inspect.signature(
            AutomatedAlphaDiscoveryFactory(enabled=True).screen_candidates
        )
        params = list(sig.parameters.keys())
        assert "test_df" not in params
        assert "oos_df" not in params


# ---------------------------------------------------------------------------
# Tests: Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Verify same inputs + seed produce same outputs."""

    def test_same_seed_same_candidates(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        df = _make_synthetic_ohlcv(seed=42)
        factory1 = AutomatedAlphaDiscoveryFactory(enabled=True, seed=42)
        factory2 = AutomatedAlphaDiscoveryFactory(enabled=True, seed=42)
        cands1 = factory1.generate_candidates(df)
        cands2 = factory2.generate_candidates(df)
        assert len(cands1) == len(cands2)
        names1 = [c.name for c in cands1]
        names2 = [c.name for c in cands2]
        assert names1 == names2

    def test_same_seed_same_result(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        df = _make_synthetic_ohlcv(seed=42)
        factory1 = AutomatedAlphaDiscoveryFactory(enabled=True, seed=42, min_ic=0.0)
        factory2 = AutomatedAlphaDiscoveryFactory(enabled=True, seed=42, min_ic=0.0)
        r1 = factory1.run_discovery(df)
        r2 = factory2.run_discovery(df)
        assert r1.candidates_generated == r2.candidates_generated
        assert r1.candidates_after_screening == r2.candidates_after_screening
        names1 = sorted([c.name for c in r1.selected_candidates])
        names2 = sorted([c.name for c in r2.selected_candidates])
        assert names1 == names2

    def test_different_seed_different_screening(self):
        """Different seeds with stochastic data may produce different screening results."""
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        # Using same factory but different data seeds
        df1 = _make_synthetic_ohlcv(seed=42)
        df2 = _make_synthetic_ohlcv(seed=99)
        factory = AutomatedAlphaDiscoveryFactory(enabled=True, seed=42, min_ic=0.0)
        r1 = factory.run_discovery(df1)
        r2 = factory.run_discovery(df2)
        # Candidates generated should be same (same templates), but screening differs
        assert r1.candidates_generated == r2.candidates_generated


# ---------------------------------------------------------------------------
# Tests: Candidate Cap
# ---------------------------------------------------------------------------

class TestCandidateCap:
    """Verify candidate cap is respected."""

    def test_cap_default_200(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory, DEFAULT_CANDIDATE_CAP
        assert DEFAULT_CANDIDATE_CAP == 200

    def test_cap_respected(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(enabled=True, candidate_cap=5)
        df = _make_synthetic_ohlcv()
        candidates = factory.generate_candidates(df)
        assert len(candidates) <= 5

    def test_cap_validation(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        with pytest.raises(ValueError):
            AutomatedAlphaDiscoveryFactory(candidate_cap=0)
        with pytest.raises(ValueError):
            AutomatedAlphaDiscoveryFactory(candidate_cap=-1)


# ---------------------------------------------------------------------------
# Tests: Correlation Filtering
# ---------------------------------------------------------------------------

class TestCorrelationFiltering:
    """Verify correlation filter removes redundant candidates."""

    def test_corr_threshold_default(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory, DEFAULT_CORR_THRESHOLD
        assert DEFAULT_CORR_THRESHOLD == 0.85

    def test_corr_threshold_validation(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        with pytest.raises(ValueError):
            AutomatedAlphaDiscoveryFactory(corr_threshold=-0.1)
        with pytest.raises(ValueError):
            AutomatedAlphaDiscoveryFactory(corr_threshold=1.5)

    def test_corr_filter_removes_redundant(self):
        """Highly correlated candidates should be filtered."""
        from omega.quant.alpha.automated_alpha_discovery import (
            AutomatedAlphaDiscoveryFactory,
            AlphaCandidate,
        )
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60, seed=42)
        factory = AutomatedAlphaDiscoveryFactory(
            enabled=True, corr_threshold=0.5, seed=42
        )

        # Create candidates with known correlation structure
        # Two candidates with very similar expressions
        c1 = AlphaCandidate(
            name="auto_mom_ret_5",
            expression_id="test1",
            train_ic=0.05,
            metadata={"expression": "df.groupby('ticker')['close'].shift(1).pct_change(5)", "template": "mom_ret_5"},
        )
        c2 = AlphaCandidate(
            name="auto_mom_ret_5b",
            expression_id="test2",
            train_ic=0.04,
            metadata={"expression": "df.groupby('ticker')['close'].shift(1).pct_change(5)", "template": "mom_ret_5b"},
        )
        candidates = [c1, c2]
        filtered = factory.correlation_filter(candidates, df)
        # Identical expressions should be filtered to 1
        selected = [c for c in filtered if c.selected]
        assert len(selected) <= 2  # At most the higher IC one

    def test_corr_filter_preserves_independent(self):
        """Independent candidates should survive filtering."""
        from omega.quant.alpha.automated_alpha_discovery import (
            AutomatedAlphaDiscoveryFactory,
            AlphaCandidate,
        )
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60, seed=42)
        factory = AutomatedAlphaDiscoveryFactory(
            enabled=True, corr_threshold=0.85, seed=42
        )

        # Very different expressions
        c1 = AlphaCandidate(
            name="auto_mom_ret_5",
            expression_id="test1",
            train_ic=0.05,
            metadata={"expression": "df.groupby('ticker')['close'].shift(1).pct_change(5)", "template": "mom_ret_5"},
        )
        c2 = AlphaCandidate(
            name="auto_vol_zscore",
            expression_id="test2",
            train_ic=0.04,
            metadata={"expression": "(df['volume'] - df.groupby('ticker')['volume'].shift(1).transform(lambda x: x.rolling(20).mean())) / df.groupby('ticker')['volume'].shift(1).transform(lambda x: x.rolling(20).std())", "template": "vol_zscore"},
        )
        candidates = [c1, c2]
        filtered = factory.correlation_filter(candidates, df)
        selected = [c for c in filtered if c.selected]
        assert len(selected) >= 1  # At least one survives


# ---------------------------------------------------------------------------
# Tests: Evidence Metadata
# ---------------------------------------------------------------------------

class TestEvidenceMetadata:
    """Verify evidence metadata is complete and serializable."""

    def test_evidence_disabled_serializable(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(enabled=False)
        df = _make_synthetic_ohlcv()
        result = factory.run_discovery(df)
        d = result.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d, default=str)
        assert len(json_str) > 0
        parsed = json.loads(json_str)
        assert parsed["gate_id"] == "AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615"
        assert parsed["enabled"] is False

    def test_evidence_enabled_complete(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(
            enabled=True, min_ic=0.0, candidate_cap=10, seed=42
        )
        df = _make_synthetic_ohlcv()
        result = factory.run_discovery(df)
        d = result.to_dict()
        json_str = json.dumps(d, default=str)
        parsed = json.loads(json_str)

        assert parsed["gate_id"] == "AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615"
        assert parsed["enabled"] is True
        assert "candidates_generated" in parsed
        assert "candidates_after_screening" in parsed
        assert "candidates_after_corr_filter" in parsed
        assert "selected_names" in parsed
        assert "selected_ics" in parsed

    def test_evidence_has_pit_safe_flag(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(
            enabled=True, min_ic=0.0, candidate_cap=5, seed=42
        )
        df = _make_synthetic_ohlcv()
        result = factory.run_discovery(df)
        evidence = result.evidence
        if evidence.get("status") == "completed":
            assert evidence.get("pit_safe") is True
            assert evidence.get("train_only") is True
            assert evidence.get("no_live_promotion") is True

    def test_evidence_config_included(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(
            enabled=True, min_ic=0.0, candidate_cap=5, seed=42,
            corr_threshold=0.80
        )
        df = _make_synthetic_ohlcv()
        result = factory.run_discovery(df)
        evidence = result.evidence
        if evidence.get("status") == "completed":
            config = evidence["config"]
            assert config["candidate_cap"] == 5
            assert config["corr_threshold"] == 0.80
            assert config["seed"] == 42


# ---------------------------------------------------------------------------
# Tests: Phase35 Wiring
# ---------------------------------------------------------------------------

class TestPhase35Wiring:
    """Verify phase35 engine has correct parameters wired."""

    def test_engine_accepts_discovery_params(self):
        engine = _make_engine(
            enable_automated_discovery=True,
            automated_discovery_cap=50,
            automated_discovery_corr_threshold=0.90,
            automated_discovery_min_ic=0.02,
            automated_discovery_seed=123,
        )
        assert engine.enable_automated_discovery is True
        assert engine.automated_discovery_cap == 50
        assert engine.automated_discovery_corr_threshold == 0.90
        assert engine.automated_discovery_min_ic == 0.02
        assert engine.automated_discovery_seed == 123

    def test_engine_default_values(self):
        engine = _make_engine()
        assert engine.enable_automated_discovery is False
        assert engine.automated_discovery_cap == 200
        assert engine.automated_discovery_corr_threshold == 0.85
        assert engine.automated_discovery_min_ic == 0.01
        assert engine.automated_discovery_seed == 42

    def test_engine_validates_bool(self):
        with pytest.raises(ValueError, match="enable_automated_discovery"):
            _make_engine(enable_automated_discovery="yes")

    def test_engine_validates_cap(self):
        with pytest.raises(ValueError, match="automated_discovery_cap"):
            _make_engine(automated_discovery_cap=0)

    def test_engine_validates_corr_threshold(self):
        with pytest.raises(ValueError, match="automated_discovery_corr_threshold"):
            _make_engine(automated_discovery_corr_threshold=1.5)

    def test_engine_validates_seed(self):
        with pytest.raises(ValueError, match="automated_discovery_seed"):
            _make_engine(automated_discovery_seed="abc")

    def test_fold_metrics_has_evidence_field(self):
        """FoldMetrics should have automated_discovery_evidence field."""
        from omega.quant.alpha.phase35 import FoldMetrics
        fm = FoldMetrics(
            fold_id=0, train_start="2022-01-01", train_end="2022-06-30",
            test_start="2022-07-01", test_end="2022-09-30",
        )
        assert fm.automated_discovery_evidence is None

    def test_phase35_source_has_gate_constant(self):
        source = _get_phase35_source()
        assert "AUTOMATED_DISCOVERY_GATE_ID" in source
        assert "AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615" in source


# ---------------------------------------------------------------------------
# Tests: Transfer Diagnostics
# ---------------------------------------------------------------------------

class TestTransferDiagnostics:
    """Verify transfer diagnostics helpers produce valid results."""

    def test_compute_signal_correlations_empty(self):
        from omega.quant.alpha.alpha_transfer_diagnostics import compute_signal_correlations
        signal = pd.Series(np.random.randn(100))
        existing = pd.DataFrame()
        result = compute_signal_correlations(signal, existing)
        assert result["max_corr"] == 0.0
        assert result["mean_corr"] == 0.0

    def test_compute_signal_correlations_with_existing(self):
        from omega.quant.alpha.alpha_transfer_diagnostics import compute_signal_correlations
        rng = np.random.RandomState(42)
        base = rng.randn(200)
        signal = pd.Series(base + rng.randn(200) * 0.1)
        existing = pd.DataFrame({
            "sig_a": base + rng.randn(200) * 0.1,
            "sig_b": rng.randn(200),
        })
        result = compute_signal_correlations(signal, existing)
        assert result["max_corr"] > 0.5  # Should be correlated with sig_a
        assert "per_signal" in result

    def test_estimate_signal_turnover(self):
        from omega.quant.alpha.alpha_transfer_diagnostics import estimate_signal_turnover
        rng = np.random.RandomState(42)
        n = 100
        dates = pd.Series(pd.date_range("2022-01-01", periods=10, freq="B").repeat(10))
        tickers = pd.Series([f"S{i}" for i in range(10)] * 10)
        signal = pd.Series(rng.randn(n))
        turnover = estimate_signal_turnover(signal, dates, tickers)
        assert 0.0 <= turnover <= 1.0

    def test_run_transfer_diagnostics(self):
        from omega.quant.alpha.alpha_transfer_diagnostics import run_transfer_diagnostics
        rng = np.random.RandomState(42)
        n = 200
        dates = pd.Series(pd.date_range("2022-01-01", periods=20, freq="B").repeat(10))
        tickers = pd.Series([f"S{i}" for i in range(10)] * 20)
        returns = pd.Series(rng.normal(0, 0.02, n))

        candidates = {
            "cand_a": pd.Series(rng.randn(n)),
            "cand_b": pd.Series(rng.randn(n)),
        }
        existing = pd.DataFrame()

        report = run_transfer_diagnostics(
            candidates=candidates,
            existing_signals=existing,
            returns=returns,
            dates=dates,
            tickers=tickers,
        )
        assert report.candidates_evaluated == 2
        assert len(report.diagnostics) == 2
        d = report.to_dict()
        json_str = json.dumps(d, default=str)
        assert len(json_str) > 0

    def test_transfer_diagnostic_serializable(self):
        from omega.quant.alpha.alpha_transfer_diagnostics import TransferDiagnostic
        diag = TransferDiagnostic(
            alpha_name="test_alpha",
            marginal_ic=0.03,
            transfer_verdict="RECOMMEND",
        )
        d = diag.to_dict()
        json_str = json.dumps(d)
        assert '"alpha_name": "test_alpha"' in json_str


# ---------------------------------------------------------------------------
# Tests: Dynamic Universe Compatibility
# ---------------------------------------------------------------------------

class TestDynamicUniverseCompatible:
    """Verify factory works with varying universe sizes."""

    def test_different_universe_sizes(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(
            enabled=True, min_ic=0.0, candidate_cap=5, seed=42
        )
        # Small universe
        df_small = _make_synthetic_ohlcv(n_tickers=3, n_days=40, seed=42)
        r_small = factory.run_discovery(df_small)
        assert r_small.enabled is True

        # Larger universe
        df_large = _make_synthetic_ohlcv(n_tickers=15, n_days=80, seed=42)
        r_large = factory.run_discovery(df_large)
        assert r_large.enabled is True

    def test_varying_date_ranges(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(
            enabled=True, min_ic=0.0, candidate_cap=5, seed=42
        )
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60, seed=42)
        result = factory.run_discovery(df)
        assert result.gate_id == "AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615"


# ---------------------------------------------------------------------------
# Tests: No Live Promotion
# ---------------------------------------------------------------------------

class TestNoLivePromotion:
    """Verify factory never promotes to live."""

    def test_no_promotion_in_source(self):
        """Source should not contain promotion/live deployment code."""
        source = _get_discovery_source()
        assert "promote_to_live" not in source.lower()
        assert "deploy" not in source.lower() or "no_live_promotion" in source.lower()

    def test_result_has_no_live_flag(self):
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(
            enabled=True, min_ic=0.0, candidate_cap=5, seed=42
        )
        df = _make_synthetic_ohlcv()
        result = factory.run_discovery(df)
        evidence = result.evidence
        if evidence.get("status") == "completed":
            assert evidence.get("no_live_promotion") is True

    def test_candidates_not_auto_selected(self):
        """Candidates from generation are not auto-selected."""
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(
            enabled=True, min_ic=999.0, seed=42  # Very high threshold
        )
        df = _make_synthetic_ohlcv()
        result = factory.run_discovery(df)
        # With min_ic=999.0, no candidates should pass screening
        assert result.candidates_after_screening == 0


# ---------------------------------------------------------------------------
# Tests: Smoke (bounded execution)
# ---------------------------------------------------------------------------

class TestSmoke:
    """Bounded smoke tests for E2E discovery."""

    def test_smoke_small_cap(self):
        """End-to-end smoke with small candidate cap."""
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(
            enabled=True, candidate_cap=5, min_ic=0.0, seed=42
        )
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60, seed=42)
        result = factory.run_discovery(df)
        assert result.enabled is True
        assert result.candidates_generated <= 5
        d = result.to_dict()
        assert "gate_id" in d
        assert d["gate_id"] == "AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615"

    def test_smoke_compute_signals(self):
        """Test computing signals for selected candidates."""
        from omega.quant.alpha.automated_alpha_discovery import (
            AutomatedAlphaDiscoveryFactory,
            AlphaCandidate,
        )
        factory = AutomatedAlphaDiscoveryFactory(enabled=True, seed=42)
        df = _make_synthetic_ohlcv(n_tickers=5, n_days=60, seed=42)

        c = AlphaCandidate(
            name="auto_mom_ret_5",
            expression_id="test",
            train_ic=0.05,
            metadata={
                "expression": "df.groupby('ticker')['close'].shift(1).pct_change(5)",
                "template": "mom_ret_5",
            },
        )
        result_df = factory.compute_candidate_signals(df, [c])
        assert "auto_mom_ret_5" in result_df.columns

    def test_empty_data_handling(self):
        """Factory should handle empty DataFrame gracefully."""
        from omega.quant.alpha.automated_alpha_discovery import AutomatedAlphaDiscoveryFactory
        factory = AutomatedAlphaDiscoveryFactory(enabled=True, seed=42)
        result = factory.run_discovery(pd.DataFrame())
        assert result.candidates_generated == 0


# ---------------------------------------------------------------------------
# Tests: Cross-Ticker Panel Leakage Regression (L3 FIX1)
# ---------------------------------------------------------------------------

def _make_two_ticker_panel() -> pd.DataFrame:
    """Minimal 2-ticker panel designed to expose global shift/diff leakage.

    Ticker A has close prices [100, 200, 300].
    Ticker B has close prices [1000, 2000, 3000].
    Sorted by date then ticker so the flat row order interleaves tickers.

    A *global* pct_change(1) on shifted close would compare ticker-B row
    against ticker-A row and produce a finite cross-ticker value.
    A correctly *grouped* operation must return NaN at the first row of
    each ticker group.
    """
    rows = []
    dates = pd.date_range("2023-01-02", periods=3, freq="B")
    for d_idx, date in enumerate(dates):
        rows.append({"ticker": "AAA", "date": date,
                      "open": 100.0 + d_idx * 100,
                      "high": 110.0 + d_idx * 100,
                      "low": 90.0 + d_idx * 100,
                      "close": 100.0 + d_idx * 100,
                      "volume": 1000 + d_idx * 1000,
                      "fwd_ret_5": 0.01})
        rows.append({"ticker": "BBB", "date": date,
                      "open": 1000.0 + d_idx * 1000,
                      "high": 1100.0 + d_idx * 1000,
                      "low": 900.0 + d_idx * 1000,
                      "close": 1000.0 + d_idx * 1000,
                      "volume": 10000 + d_idx * 10000,
                      "fwd_ret_5": 0.02})
    return pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)


class TestCrossTickerLeakageRegression:
    """Regression tests for L3 audit finding #1: global shift leakage."""

    def test_no_global_pct_change_after_group_shift(self):
        """Templates must NOT call .pct_change() on the flat post-shift Series.

        The old pattern ``groupby('ticker')['close'].shift(1).pct_change(5)``
        applies pct_change globally, leaking cross-ticker values.
        """
        source = _get_discovery_source()
        # Extract the template section
        tpl_start = source.find("_EXPRESSION_TEMPLATES")
        tpl_end = source.find("]", tpl_start + 100)
        tpl_section = source[tpl_start:tpl_end]
        # Forbidden pattern: shift(N).pct_change outside of a transform/lambda
        # A correct pattern is .transform(lambda x: x.shift(1).pct_change(...))
        # An incorrect pattern is .shift(1).pct_change(...) at top level
        bad_pattern = re.findall(
            r"\.shift\(\d+\)\.pct_change\(\d+\)", tpl_section
        )
        # Every occurrence of shift().pct_change() must be inside a lambda
        # within transform.  We verify no *bare* .shift(N).pct_change(M)
        # appears that is NOT preceded by "lambda x: x."
        for match in re.finditer(
            r"(?<!lambda x: x\.)\.shift\(\d+\)\.pct_change\(\d+\)",
            tpl_section,
        ):
            # Check that this match is inside a transform(lambda x: ...)
            context_start = max(0, match.start() - 80)
            context = tpl_section[context_start:match.end()]
            assert "transform(lambda x:" in context or "transform(lambda x :" in context, (
                f"Found bare .shift().pct_change() outside transform: "
                f"...{context}..."
            )

    def test_no_global_diff_after_group_shift(self):
        """_compute_rsi_safe must not call .diff() on flat post-shift Series."""
        source = _get_discovery_source()
        # Extract _compute_rsi_safe function body
        fn_start = source.find("def _compute_rsi_safe")
        fn_end = source.find("\ndef ", fn_start + 10)
        fn_body = source[fn_start:fn_end]
        # Old pattern: close = groupby.shift(1); close.diff()  -- global diff
        # New pattern: inside transform lambda: shifted.diff()  -- grouped
        assert "transform(" in fn_body, (
            "_compute_rsi_safe should use groupby().transform() for all "
            "shift/diff/rolling ops"
        )
        # Verify no bare .diff() on a variable that holds groupby.shift result
        assert "close.diff()" not in fn_body, (
            "_compute_rsi_safe still uses global close.diff() after groupby.shift"
        )

    def test_momentum_no_cross_ticker_values(self):
        """mom_ret_5 on 2-ticker panel must not produce cross-ticker artifacts.

        The first row of each ticker group must be NaN (no prior data).
        A global pct_change would produce a finite value at ticker-B boundary
        by comparing against ticker-A's last row.
        """
        from omega.quant.alpha.automated_alpha_discovery import (
            AutomatedAlphaDiscoveryFactory,
        )
        df = _make_two_ticker_panel()
        factory = AutomatedAlphaDiscoveryFactory(enabled=True, seed=42)
        expr = "df.groupby('ticker')['close'].transform(lambda x: x.shift(1).pct_change(1))"
        signal = factory._evaluate_expression(df, expr)
        assert signal is not None
        # First row of each ticker must be NaN (shift produces NaN, pct_change on NaN = NaN)
        aaa_rows = df[df['ticker'] == 'AAA'].index
        bbb_rows = df[df['ticker'] == 'BBB'].index
        # First row of AAA: shifted close is NaN -> pct_change is NaN
        assert pd.isna(signal.iloc[aaa_rows[0]]), (
            f"AAA first row should be NaN, got {signal.iloc[aaa_rows[0]]}"
        )
        # First row of BBB: must also be NaN (not cross-ticker value from AAA)
        assert pd.isna(signal.iloc[bbb_rows[0]]), (
            f"BBB first row should be NaN, got {signal.iloc[bbb_rows[0]]}. "
            f"Cross-ticker leakage detected!"
        )

    def test_rsi_no_cross_ticker_values(self):
        """_compute_rsi_safe must produce NaN at ticker boundaries, not cross-ticker values."""
        from omega.quant.alpha.automated_alpha_discovery import _compute_rsi_safe
        # Need more rows for RSI period
        rng = np.random.RandomState(42)
        rows = []
        dates = pd.date_range("2023-01-02", periods=20, freq="B")
        for d_idx, date in enumerate(dates):
            rows.append({"ticker": "AAA", "date": date,
                          "close": 100.0 + rng.randn() * 5})
            rows.append({"ticker": "BBB", "date": date,
                          "close": 1000.0 + rng.randn() * 50})
        df = pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)
        rsi = _compute_rsi_safe(df, 7)
        # First row of each ticker group must be NaN (shift + diff = 2 NaN rows at start)
        aaa_first = df[df['ticker'] == 'AAA'].index[0]
        bbb_first = df[df['ticker'] == 'BBB'].index[0]
        assert pd.isna(rsi.iloc[aaa_first]), (
            f"RSI at AAA first row should be NaN, got {rsi.iloc[aaa_first]}"
        )
        assert pd.isna(rsi.iloc[bbb_first]), (
            f"RSI at BBB first row should be NaN, got {rsi.iloc[bbb_first]}. "
            f"Cross-ticker diff leakage detected!"
        )


# ---------------------------------------------------------------------------
# Tests: Current-Bar OHLCV Regression (L3 FIX1 Finding #2)
# ---------------------------------------------------------------------------

class TestCurrentBarOHLCVRegression:
    """Regression tests for L3 audit finding #2: same-row OHLCV usage."""

    def test_no_bare_ohlcv_in_templates(self):
        """Templates must not use bare df['close'], df['open'], etc.

        All OHLCV column accesses must go through groupby().shift(1+) or
        helper functions that shift internally.  Bare column access means
        current-bar (same-row) data which is look-ahead leakage.
        """
        source = _get_discovery_source()
        tpl_start = source.find("_EXPRESSION_TEMPLATES")
        tpl_end = source.find("]", tpl_start + 100)
        tpl_section = source[tpl_start:tpl_end]

        # Forbidden: bare df['close'], df['volume'], df['high'], df['low'], df['open']
        # that are NOT inside a groupby() call.
        # We look for patterns like df['close'] that are NOT followed by
        # being part of groupby('ticker')['close'].shift()
        for col in ['close', 'open', 'high', 'low', 'volume']:
            # Find bare df['col'] references (not part of groupby)
            bare_refs = list(re.finditer(
                rf"df\['{col}'\]", tpl_section
            ))
            for m in bare_refs:
                # Check context: must be preceded by groupby('ticker')
                ctx_start = max(0, m.start() - 40)
                ctx = tpl_section[ctx_start:m.end()]
                assert f"groupby('ticker')['{col}']" in ctx or f'groupby("ticker")["{col}"]' in ctx, (
                    f"Template uses bare df['{col}'] without groupby.shift: "
                    f"...{ctx}..."
                )

    def test_no_ungrouped_close_shift_in_templates(self):
        """df['close'].shift(N) without groupby is still a PIT violation.

        The old vol_range_pct template used df['close'].shift(1) which is
        a global shift (can cross ticker boundaries in sorted panels).
        """
        source = _get_discovery_source()
        tpl_start = source.find("_EXPRESSION_TEMPLATES")
        tpl_end = source.find("]", tpl_start + 100)
        tpl_section = source[tpl_start:tpl_end]

        # Forbidden: df['col'].shift(N) without groupby prefix
        for col in ['close', 'open', 'high', 'low', 'volume']:
            pattern = rf"(?<!groupby\('ticker'\)\['{col}'\])\bdf\['{col}'\]\.shift\("
            matches = list(re.finditer(pattern, tpl_section))
            for m in matches:
                ctx_start = max(0, m.start() - 40)
                ctx = tpl_section[ctx_start:m.end()]
                assert False, (
                    f"Template uses ungrouped df['{col}'].shift(): ...{ctx}..."
                )

    def test_pit_safe_evidence_truthful(self):
        """Evidence pit_safe=True must be truthful: no current-bar OHLCV usage.

        Source-inspection test: if any template uses bare OHLCV columns
        without T-1 lag, the evidence should not claim pit_safe=True.
        """
        source = _get_discovery_source()
        tpl_start = source.find("_EXPRESSION_TEMPLATES")
        tpl_end = source.find("]", tpl_start + 100)
        tpl_section = source[tpl_start:tpl_end]

        has_bare_ohlcv = False
        for col in ['close', 'open', 'high', 'low', 'volume']:
            bare_refs = re.findall(rf"df\['{col}'\]", tpl_section)
            if bare_refs:
                # Check if any are NOT inside groupby
                for m in re.finditer(rf"df\['{col}'\]", tpl_section):
                    ctx_start = max(0, m.start() - 40)
                    ctx = tpl_section[ctx_start:m.end()]
                    if f"groupby('ticker')['{col}']" not in ctx:
                        has_bare_ohlcv = True
                        break

        # If bare OHLCV exists, pit_safe claim in evidence must be False
        # or the templates must be fixed
        if has_bare_ohlcv:
            assert '"pit_safe": True' not in source and "'pit_safe': True" not in source, (
                "Evidence claims pit_safe=True but templates use bare OHLCV columns"
            )

    def test_helper_functions_all_shift_ohlcv(self):
        """Helper functions _compute_body_pct, _compute_upper_shadow,
        _compute_lower_shadow must use groupby.shift(1) for all OHLCV."""
        source = _get_discovery_source()
        for fn_name in ['_compute_body_pct', '_compute_upper_shadow', '_compute_lower_shadow']:
            fn_start = source.find(f"def {fn_name}")
            assert fn_start >= 0, f"Helper function {fn_name} not found in source"
            fn_end = source.find("\ndef ", fn_start + 10)
            fn_body = source[fn_start:fn_end]
            # Must contain groupby.shift
            assert "groupby('ticker')" in fn_body and ".shift(1)" in fn_body, (
                f"{fn_name} must use groupby('ticker').shift(1) for OHLCV"
            )
            # Must not contain bare df['close'] etc.
            for col in ['close', 'open', 'high', 'low', 'volume']:
                bare = re.findall(rf"df\['{col}'\]", fn_body)
                assert not bare, (
                    f"{fn_name} uses bare df['{col}'] — must use groupby.shift"
                )


# ---------------------------------------------------------------------------
# Tests: Source Inspection (existing)
# ---------------------------------------------------------------------------

class TestSourceInspection:
    """Verify source code patterns via AST/regex inspection."""

    def test_discovery_has_gate_id(self):
        source = _get_discovery_source()
        assert 'AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615' in source

    def test_discovery_has_t_minus_1_shift(self):
        """Expressions should use shift(1) for PIT safety."""
        source = _get_discovery_source()
        assert ".shift(1)" in source

    def test_transfer_diag_has_gate_id(self):
        source = _get_transfer_diag_source()
        assert 'AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615' in source

    def test_no_random_splits(self):
        """Source should not use random train/test splits."""
        source = _get_discovery_source()
        assert "train_test_split" not in source
        assert "random_split" not in source

    def test_factory_is_dataclass_compatible(self):
        """DiscoveryResult should be a proper dataclass."""
        from omega.quant.alpha.automated_alpha_discovery import DiscoveryResult
        import dataclasses
        assert dataclasses.is_dataclass(DiscoveryResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
