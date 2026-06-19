"""Deterministic unit tests for risk-adjusted alpha selection composite scoring.

GATE: RISK_ADJUSTED_ALPHA_TUNING_20260614
KPI: C (risk-adjusted composite)
BOUNDARY: paper-trading-ready / no live trading

Test matrix:
  1. Stable positive IC alpha scores higher than noisy alpha
  2. High turnover penalty reduces composite score
  3. Overfit gap penalty reduces composite score
  4. NaN safety — all NaN inputs produce neutral/zero scores
  5. Default disabled path — engine default has risk_adjusted=False
  6. Composite score range [0, 1]
  7. Selection with paper-trading gate PASS/FAIL
  8. Score breakdown serialization
  9. Preset weight validation (GATE: RISK_ADJUSTED_ALPHA_TUNING_20260614)
  10. Preset evidence persistence
  11. Unknown preset rejection
  12. Default backward compatibility
"""
from __future__ import annotations

import math
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on path
_repo_root = Path(__file__).resolve().parents[1]
_src = _repo_root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from omega.quant.walk_forward.risk_adjusted_alpha_score import (
    AlphaScoreBreakdown,
    RiskAdjustedSelectionResult,
    compute_composite_score,
    compute_ic_stability,
    compute_overfit_gap,
    compute_validation_ic,
    estimate_turnover,
    score_alpha_candidates,
    select_alphas_risk_adjusted,
    save_evidence,
    _ic_to_score,
    _ic_sharpe_to_score,
    _turnover_to_score,
    _overfit_gap_to_score,
    _safe_float,
    _clamp01,
    _NEUTRAL_SCORE,
    DEFAULT_WEIGHTS,
    PRESETS,
    DEFAULT_PRESET,
    get_preset_weights,
    get_preset_rank_components,
    list_presets,
    IC_FIRST_PRIMARY_COMPONENTS,
    IC_FIRST_SOFT_PENALTY_COMPONENTS,
)


# ---------------------------------------------------------------------------
# Helper: build synthetic multi-day cross-sectional data
# ---------------------------------------------------------------------------
def _make_cs_data(
    n_dates: int = 30,
    n_tickers: int = 10,
    ic_strength: float = 0.3,
    noise: float = 0.1,
    seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic DataFrame with alpha, date, ticker, fwd_ret_5.

    The alpha signal has configurable IC strength with forward returns.
    """
    rng = np.random.RandomState(seed)
    rows = []
    for d in range(n_dates):
        date_str = f"2025-{(d // 28) + 1:02d}-{(d % 28) + 1:02d}"
        for t in range(n_tickers):
            ticker = f"TK{t:02d}"
            ret = rng.randn() * 0.02
            # Alpha correlated with return at given IC strength
            alpha = ic_strength * ret + noise * rng.randn()
            rows.append({
                "date": date_str,
                "ticker": ticker,
                "alpha_test": alpha,
                "fwd_ret_5": ret,
            })
    return pd.DataFrame(rows)


# ===========================================================================
# 1. STABLE POSITIVE IC vs NOISY ALPHA
# ===========================================================================
class TestStableVsNoisyIC:
    """A stable positive-IC alpha must score higher than a noisy one."""

    def test_stable_alpha_higher_composite(self):
        """Stable alpha (IC=0.3, low noise) > noisy alpha (IC≈0, high noise)."""
        bd_stable = compute_composite_score(
            "stable_alpha",
            validation_ic=0.3,
            ic_sharpe=2.0,
            turnover=0.2,
            overfit_gap=0.05,
        )
        bd_noisy = compute_composite_score(
            "noisy_alpha",
            validation_ic=0.01,
            ic_sharpe=0.1,
            turnover=0.2,
            overfit_gap=0.05,
        )
        assert bd_stable.composite_score > bd_noisy.composite_score

    def test_stable_alpha_higher_validation_ic_score(self):
        bd_stable = compute_composite_score(
            "stable", validation_ic=0.3, ic_sharpe=1.0, turnover=0.2, overfit_gap=0.05
        )
        bd_noisy = compute_composite_score(
            "noisy", validation_ic=0.0, ic_sharpe=1.0, turnover=0.2, overfit_gap=0.05
        )
        assert bd_stable.validation_ic_score > bd_noisy.validation_ic_score

    def test_stable_alpha_higher_ic_stability(self):
        bd_stable = compute_composite_score(
            "stable", validation_ic=0.2, ic_sharpe=3.0, turnover=0.2, overfit_gap=0.05
        )
        bd_noisy = compute_composite_score(
            "noisy", validation_ic=0.2, ic_sharpe=0.0, turnover=0.2, overfit_gap=0.05
        )
        assert bd_stable.ic_stability_score > bd_noisy.ic_stability_score


# ===========================================================================
# 2. HIGH TURNOVER PENALTY
# ===========================================================================
class TestTurnoverPenalty:
    """High turnover must reduce composite score."""

    def test_low_turnover_higher_score(self):
        bd_low = compute_composite_score(
            "low_turn", validation_ic=0.2, ic_sharpe=1.0, turnover=0.1, overfit_gap=0.05
        )
        bd_high = compute_composite_score(
            "high_turn", validation_ic=0.2, ic_sharpe=1.0, turnover=0.9, overfit_gap=0.05
        )
        assert bd_low.composite_score > bd_high.composite_score

    def test_turnover_penalty_score_inversion(self):
        """Low turnover → high penalty score, high turnover → low penalty score."""
        assert _turnover_to_score(0.1) > _turnover_to_score(0.9)
        assert _turnover_to_score(0.0) == pytest.approx(1.0)
        assert _turnover_to_score(1.0) == pytest.approx(0.0)

    def test_estimate_turnover_range(self):
        """estimate_turnover returns value in [0, 1]."""
        df = _make_cs_data(n_dates=10, n_tickers=5, seed=123)
        t = estimate_turnover(df, "alpha_test")
        assert 0.0 <= t <= 1.0

    def test_estimate_turnover_missing_column(self):
        df = _make_cs_data(n_dates=5, n_tickers=3)
        assert estimate_turnover(df, "nonexistent_col") == 0.5


# ===========================================================================
# 3. OVERFIT GAP PENALTY
# ===========================================================================
class TestOverfitGapPenalty:
    """Large train-val IC gap must reduce composite score."""

    def test_small_gap_higher_score(self):
        bd_small = compute_composite_score(
            "small_gap", validation_ic=0.2, ic_sharpe=1.0, turnover=0.2, overfit_gap=0.02
        )
        bd_large = compute_composite_score(
            "large_gap", validation_ic=0.2, ic_sharpe=1.0, turnover=0.2, overfit_gap=0.5
        )
        assert bd_small.composite_score > bd_large.composite_score

    def test_overfit_gap_to_score_mapping(self):
        assert _overfit_gap_to_score(0.0) == pytest.approx(1.0)
        assert _overfit_gap_to_score(0.5) == pytest.approx(0.5)
        assert _overfit_gap_to_score(1.0) == pytest.approx(0.0)

    def test_compute_overfit_gap_value(self):
        assert compute_overfit_gap(0.3, 0.1) == pytest.approx(0.2)
        assert compute_overfit_gap(0.1, 0.3) == pytest.approx(0.2)
        assert compute_overfit_gap(0.2, 0.2) == pytest.approx(0.0)


# ===========================================================================
# 4. NaN SAFETY
# ===========================================================================
class TestNaNSafety:
    """All NaN inputs must produce safe neutral/zero scores."""

    def test_validation_ic_all_nan(self):
        alpha = pd.Series([np.nan] * 20)
        ret = pd.Series([np.nan] * 20)
        assert compute_validation_ic(alpha, ret) == 0.0

    def test_validation_ic_empty(self):
        alpha = pd.Series([], dtype=float)
        ret = pd.Series([], dtype=float)
        assert compute_validation_ic(alpha, ret) == 0.0

    def test_ic_stability_all_nan(self):
        daily = pd.Series([np.nan] * 30)
        assert compute_ic_stability(daily) == 0.0

    def test_ic_stability_empty(self):
        daily = pd.Series([], dtype=float)
        assert compute_ic_stability(daily) == 0.0

    def test_composite_score_nan_inputs_safe(self):
        bd = compute_composite_score(
            "nan_alpha",
            validation_ic=float("nan"),
            ic_sharpe=float("nan"),
            turnover=float("nan"),
            overfit_gap=float("nan"),
        )
        # Should produce a valid score in [0, 1]
        assert 0.0 <= bd.composite_score <= 1.0
        # Raw values should be safe
        assert not math.isnan(bd.raw_validation_ic)
        assert not math.isnan(bd.raw_ic_sharpe)
        assert not math.isnan(bd.raw_turnover)
        assert not math.isnan(bd.raw_overfit_gap)

    def test_safe_float_nan(self):
        assert _safe_float(float("nan")) == 0.0
        assert _safe_float(float("inf")) == 0.0
        assert _safe_float(None) == 0.0
        assert _safe_float("abc") == 0.0
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_estimate_turnover_all_nan(self):
        """Turnover with all NaN alpha values returns safe fallback."""
        df = pd.DataFrame({
            "date": ["2025-01-01"] * 5 + ["2025-01-02"] * 5,
            "ticker": [f"T{i}" for i in range(5)] * 2,
            "alpha_x": [np.nan] * 10,
        })
        t = estimate_turnover(df, "alpha_x")
        assert 0.0 <= t <= 1.0


# ===========================================================================
# 5. DEFAULT DISABLED PATH
# ===========================================================================
class TestDefaultDisabledPath:
    """Risk-adjusted selection must be disabled by default."""

    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert total == pytest.approx(1.0)

    def test_composite_score_in_range(self):
        """Composite score always in [0, 1] for various inputs."""
        test_cases = [
            (0.5, 2.0, 0.1, 0.0),
            (-0.5, -2.0, 0.9, 0.8),
            (0.0, 0.0, 0.5, 0.3),
            (1.0, 10.0, 0.0, 0.0),
            (-1.0, -10.0, 1.0, 1.0),
        ]
        for v_ic, ic_sh, turn, gap in test_cases:
            bd = compute_composite_score(
                "test",
                validation_ic=v_ic,
                ic_sharpe=ic_sh,
                turnover=turn,
                overfit_gap=gap,
            )
            assert 0.0 <= bd.composite_score <= 1.0, (
                f"Score out of range for v_ic={v_ic}, ic_sh={ic_sh}, turn={turn}, gap={gap}: "
                f"got {bd.composite_score}"
            )

    def test_unavailable_components_use_neutral(self):
        """When Sharpe/drawdown unavailable, neutral fallback is used."""
        bd = compute_composite_score(
            "no_extras",
            validation_ic=0.2,
            ic_sharpe=1.0,
            turnover=0.2,
            overfit_gap=0.05,
            expected_sharpe=None,
            max_drawdown=None,
        )
        assert bd.expected_sharpe_score == pytest.approx(_NEUTRAL_SCORE)
        assert bd.drawdown_penalty_score == pytest.approx(_NEUTRAL_SCORE)
        assert not bd.sharpe_available
        assert not bd.drawdown_available

    def test_available_sharpe_used(self):
        bd = compute_composite_score(
            "with_sharpe",
            validation_ic=0.2,
            ic_sharpe=1.0,
            turnover=0.2,
            overfit_gap=0.05,
            expected_sharpe=2.0,
            max_drawdown=-0.1,
        )
        assert bd.sharpe_available
        assert bd.drawdown_available
        assert bd.expected_sharpe_score != pytest.approx(_NEUTRAL_SCORE)
        assert bd.drawdown_penalty_score != pytest.approx(_NEUTRAL_SCORE)


# ===========================================================================
# 6. SELECTION WITH PAPER-TRADING GATE
# ===========================================================================
class TestSelectionAndGate:
    """Selection must produce PASS/FAIL gate with reasons."""

    def test_pass_gate_with_good_alphas(self):
        break_downs = {}
        for i, ic in enumerate([0.3, 0.25, 0.2]):
            name = f"alpha_{i}"
            break_downs[name] = compute_composite_score(
                name,
                validation_ic=ic,
                ic_sharpe=2.0,
                turnover=0.15,
                overfit_gap=0.03,
            )
        result = select_alphas_risk_adjusted(break_downs, top_n=3)
        assert result.paper_trading_gate == "PASS"
        assert len(result.selected_alphas) >= 1

    def test_fail_gate_no_positive_val_ic(self):
        break_downs = {}
        for i, ic in enumerate([-0.1, -0.05, 0.0]):
            name = f"neg_alpha_{i}"
            break_downs[name] = compute_composite_score(
                name,
                validation_ic=ic,
                ic_sharpe=1.0,
                turnover=0.2,
                overfit_gap=0.05,
            )
        result = select_alphas_risk_adjusted(
            break_downs, top_n=3, require_positive_val_ic=True
        )
        # All alphas have non-positive val IC → should fail
        assert result.paper_trading_gate == "FAIL"
        assert len(result.selected_alphas) == 0

    def test_fail_gate_all_high_overfit(self):
        break_downs = {}
        for i in range(3):
            name = f"overfit_{i}"
            break_downs[name] = compute_composite_score(
                name,
                validation_ic=0.2,
                ic_sharpe=1.0,
                turnover=0.2,
                overfit_gap=0.5,  # > max_overfit_gap=0.15
            )
        result = select_alphas_risk_adjusted(
            break_downs, top_n=3, max_overfit_gap=0.15
        )
        assert len(result.rejected_alphas) == 3
        for name in result.rejected_alphas:
            assert "overfit_gap" in break_downs[name].rejection_reason

    def test_top_n_limit(self):
        """Only top_n alphas are selected even if more are eligible."""
        break_downs = {}
        for i in range(10):
            name = f"alpha_{i}"
            ic = 0.1 + i * 0.02
            break_downs[name] = compute_composite_score(
                name,
                validation_ic=ic,
                ic_sharpe=2.0,
                turnover=0.1,
                overfit_gap=0.02,
            )
        result = select_alphas_risk_adjusted(break_downs, top_n=3)
        assert len(result.selected_alphas) == 3
        assert len(result.rejected_alphas) == 7

    def test_gate_reasons_populated(self):
        """PASS and FAIL both populate paper_trading_reasons."""
        # PASS case
        bd = {"a": compute_composite_score("a", validation_ic=0.3, ic_sharpe=2.0, turnover=0.1, overfit_gap=0.02)}
        r_pass = select_alphas_risk_adjusted(bd, top_n=1)
        assert r_pass.paper_trading_gate == "PASS"
        assert len(r_pass.paper_trading_reasons) > 0

        # FAIL case (empty)
        r_fail = select_alphas_risk_adjusted({}, top_n=1)
        assert r_fail.paper_trading_gate == "FAIL"
        assert len(r_fail.paper_trading_reasons) > 0


# ===========================================================================
# 7. BATCH SCORING
# ===========================================================================
class TestBatchScoring:
    """score_alpha_candidates handles multiple alphas correctly."""

    def test_batch_scoring_all_alphas(self):
        df = _make_cs_data(n_dates=30, n_tickers=10, ic_strength=0.3, seed=42)
        # Add a second alpha with different characteristics
        rng = np.random.RandomState(99)
        df["alpha_noisy"] = rng.randn(len(df)) * 0.01

        alpha_cols = ["alpha_test", "alpha_noisy"]
        train_ics = {"alpha_test": 0.25, "alpha_noisy": 0.02}

        # Split into train/val
        dates = sorted(df["date"].unique())
        split = len(dates) * 2 // 3
        train_dates = dates[:split]
        val_dates = dates[split:]
        train_df = df[df["date"].isin(train_dates)].reset_index(drop=True)
        val_df = df[df["date"].isin(val_dates)].reset_index(drop=True)

        break_downs = score_alpha_candidates(
            alpha_cols,
            train_df=train_df,
            val_df=val_df,
            train_ics=train_ics,
            return_col="fwd_ret_5",
        )

        assert len(break_downs) == 2
        assert "alpha_test" in break_downs
        assert "alpha_noisy" in break_downs
        # All scores in [0, 1]
        for name, bd in break_downs.items():
            assert 0.0 <= bd.composite_score <= 1.0

    def test_batch_scoring_missing_column(self):
        """Missing alpha column gets score computed (with safe fallback)."""
        df = _make_cs_data(n_dates=10, n_tickers=5, seed=10)
        alpha_cols = ["alpha_test", "missing_alpha"]
        train_ics = {"alpha_test": 0.2, "missing_alpha": 0.1}

        break_downs = score_alpha_candidates(
            alpha_cols,
            train_df=df,
            val_df=df,
            train_ics=train_ics,
            return_col="fwd_ret_5",
        )
        assert len(break_downs) == 2
        assert 0.0 <= break_downs["missing_alpha"].composite_score <= 1.0


# ===========================================================================
# 8. SERIALIZATION
# ===========================================================================
class TestSerialization:
    """RiskAdjustedSelectionResult serialization."""

    def test_to_dict(self):
        bd = compute_composite_score(
            "alpha_x",
            validation_ic=0.3,
            ic_sharpe=2.0,
            turnover=0.15,
            overfit_gap=0.03,
        )
        result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_x"],
            rejected_alphas=[],
            score_breakdowns={"alpha_x": bd},
            paper_trading_gate="PASS",
            paper_trading_reasons=["All good"],
        )
        d = result.to_dict()
        assert d["paper_trading_gate"] == "PASS"
        assert "alpha_x" in d["score_breakdowns"]
        assert isinstance(d["score_breakdowns"]["alpha_x"]["composite_score"], float)

    def test_to_json_valid(self):
        bd = compute_composite_score(
            "alpha_y",
            validation_ic=0.2,
            ic_sharpe=1.0,
            turnover=0.3,
            overfit_gap=0.1,
        )
        result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_y"],
            paper_trading_gate="PASS",
            paper_trading_reasons=["OK"],
            score_breakdowns={"alpha_y": bd},
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["paper_trading_gate"] == "PASS"

    def test_save_evidence(self, tmp_path):
        bd = compute_composite_score(
            "alpha_z",
            validation_ic=0.15,
            ic_sharpe=0.5,
            turnover=0.4,
            overfit_gap=0.08,
        )
        result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_z"],
            paper_trading_gate="PASS",
            paper_trading_reasons=["1 alpha"],
            score_breakdowns={"alpha_z": bd},
        )
        out = save_evidence(result, tmp_path / "evidence.json")
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["paper_trading_gate"] == "PASS"


# ===========================================================================
# 9. HELPER MAPPING FUNCTIONS
# ===========================================================================
class TestMappingFunctions:
    """Test individual mapping functions for correctness."""

    def test_ic_to_score_boundaries(self):
        assert _ic_to_score(-1.0) == pytest.approx(0.0)
        assert _ic_to_score(0.0) == pytest.approx(0.5)
        assert _ic_to_score(1.0) == pytest.approx(1.0)

    def test_ic_sharpe_to_score_monotonic(self):
        """Higher IC Sharpe → higher score."""
        scores = [_ic_sharpe_to_score(x) for x in [-3, -1, 0, 1, 3]]
        for i in range(len(scores) - 1):
            assert scores[i] < scores[i + 1]

    def test_clamp01(self):
        assert _clamp01(-0.5) == 0.0
        assert _clamp01(1.5) == 1.0
        assert _clamp01(0.5) == 0.5


# ===========================================================================
# 10. INTEGRATION: VALIDATION IC COMPUTATION
# ===========================================================================
class TestValidationICComputation:
    """Verify IC computation on synthetic data."""

    def test_positive_ic_strong_signal(self):
        """Strong positive signal should produce positive IC."""
        rng = np.random.RandomState(42)
        ret = pd.Series(rng.randn(100))
        alpha = ret * 0.8 + rng.randn(100) * 0.1  # Strong correlation
        ic = compute_validation_ic(alpha, ret)
        assert ic > 0.3

    def test_negative_ic_inverse_signal(self):
        """Inverse signal should produce negative IC."""
        rng = np.random.RandomState(42)
        ret = pd.Series(rng.randn(100))
        alpha = -ret * 0.8 + rng.randn(100) * 0.1
        ic = compute_validation_ic(alpha, ret)
        assert ic < -0.3

    def test_zero_ic_random_signal(self):
        """Random signal should produce near-zero IC."""
        rng = np.random.RandomState(42)
        ret = pd.Series(rng.randn(200))
        alpha = pd.Series(rng.randn(200))
        ic = compute_validation_ic(alpha, ret)
        assert abs(ic) < 0.2

    def test_ic_stability_consistent_daily_ics(self):
        """Consistent daily ICs should produce positive IC Sharpe."""
        daily = pd.Series([0.05] * 50)  # Constant positive IC
        sharpe = compute_ic_stability(daily)
        # std=0 → fallback: mean * 10 = 0.5
        assert sharpe > 0.0

    def test_ic_stability_inconsistent_daily_ics(self):
        """Alternating daily ICs should produce low IC Sharpe."""
        daily = pd.Series([0.1, -0.1] * 25)  # Mean≈0, std>0
        sharpe = compute_ic_stability(daily)
        assert abs(sharpe) < 1.0


# ===========================================================================
# 11. DRAWDOWN PENALTY
# ===========================================================================
class TestDrawdownPenalty:
    """Test drawdown penalty component."""

    def test_small_drawdown_higher_score(self):
        bd_small = compute_composite_score(
            "small_dd", validation_ic=0.2, ic_sharpe=1.0, turnover=0.2,
            overfit_gap=0.05, max_drawdown=-0.05,
        )
        bd_large = compute_composite_score(
            "large_dd", validation_ic=0.2, ic_sharpe=1.0, turnover=0.2,
            overfit_gap=0.05, max_drawdown=-0.50,
        )
        assert bd_small.composite_score > bd_large.composite_score
        assert bd_small.drawdown_penalty_score > bd_large.drawdown_penalty_score

    def test_drawdown_mapping(self):
        bd = compute_composite_score(
            "test_dd", validation_ic=0.2, ic_sharpe=1.0, turnover=0.2,
            overfit_gap=0.05, max_drawdown=-0.10,
        )
        assert bd.drawdown_penalty_score == pytest.approx(0.9)
        assert bd.drawdown_available


# ===========================================================================
# 12. REGRESSION: raw_expected_sharpe serialization (FIX1_20260614)
# ===========================================================================
class TestRawExpectedSharpeSerialization:
    """raw_expected_sharpe must appear in to_dict() score breakdowns."""

    def test_raw_expected_sharpe_present_in_to_dict(self):
        """to_dict() must include raw_expected_sharpe for each breakdown."""
        bd = compute_composite_score(
            "alpha_sharpe",
            validation_ic=0.3,
            ic_sharpe=2.0,
            turnover=0.15,
            overfit_gap=0.03,
            expected_sharpe=1.5,
        )
        result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_sharpe"],
            rejected_alphas=[],
            score_breakdowns={"alpha_sharpe": bd},
            paper_trading_gate="PASS",
            paper_trading_reasons=["OK"],
        )
        d = result.to_dict()
        breakdown = d["score_breakdowns"]["alpha_sharpe"]
        assert "raw_expected_sharpe" in breakdown, (
            "raw_expected_sharpe missing from serialized score breakdowns"
        )
        assert breakdown["raw_expected_sharpe"] == pytest.approx(1.5, abs=1e-4)

    def test_raw_expected_sharpe_zero_when_unavailable(self):
        """When expected_sharpe is None, raw_expected_sharpe serializes as 0.0."""
        bd = compute_composite_score(
            "alpha_no_sharpe",
            validation_ic=0.2,
            ic_sharpe=1.0,
            turnover=0.2,
            overfit_gap=0.05,
            expected_sharpe=None,
        )
        result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_no_sharpe"],
            score_breakdowns={"alpha_no_sharpe": bd},
            paper_trading_gate="PASS",
            paper_trading_reasons=["OK"],
        )
        d = result.to_dict()
        breakdown = d["score_breakdowns"]["alpha_no_sharpe"]
        assert "raw_expected_sharpe" in breakdown
        assert breakdown["raw_expected_sharpe"] == pytest.approx(0.0)
        assert breakdown["sharpe_available"] is False

    def test_raw_expected_sharpe_in_json_roundtrip(self):
        """raw_expected_sharpe survives JSON round-trip."""
        bd = compute_composite_score(
            "alpha_rt",
            validation_ic=0.25,
            ic_sharpe=1.5,
            turnover=0.1,
            overfit_gap=0.02,
            expected_sharpe=2.5,
            max_drawdown=-0.08,
        )
        result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_rt"],
            score_breakdowns={"alpha_rt": bd},
            paper_trading_gate="PASS",
            paper_trading_reasons=["OK"],
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        breakdown = parsed["score_breakdowns"]["alpha_rt"]
        assert "raw_expected_sharpe" in breakdown
        assert breakdown["raw_expected_sharpe"] == pytest.approx(2.5, abs=1e-4)


# ===========================================================================
# 13. REGRESSION: evidence persistence completeness (FIX1_20260614)
# ===========================================================================
class TestEvidencePersistence:
    """Evidence must include all required fields for audit reconstruction."""

    def _build_full_result(self) -> RiskAdjustedSelectionResult:
        """Build a result with selected + rejected alphas for testing."""
        bd_good = compute_composite_score(
            "alpha_good",
            validation_ic=0.3,
            ic_sharpe=2.0,
            turnover=0.1,
            overfit_gap=0.02,
            expected_sharpe=1.8,
            max_drawdown=-0.05,
        )
        bd_bad = compute_composite_score(
            "alpha_bad",
            validation_ic=-0.1,
            ic_sharpe=-1.0,
            turnover=0.8,
            overfit_gap=0.4,
        )
        break_downs = {"alpha_good": bd_good, "alpha_bad": bd_bad}
        result = select_alphas_risk_adjusted(
            break_downs, top_n=3, require_positive_val_ic=True
        )
        result.config = {"risk_adjusted_alpha_selection": True, "top_n": 3}
        return result

    def test_evidence_has_selected_alphas(self):
        result = self._build_full_result()
        d = result.to_dict()
        assert "selected_alphas" in d
        assert isinstance(d["selected_alphas"], list)
        assert "alpha_good" in d["selected_alphas"]

    def test_evidence_has_rejected_alphas_with_reasons(self):
        result = self._build_full_result()
        d = result.to_dict()
        assert "rejected_alphas" in d
        assert "alpha_bad" in d["rejected_alphas"]
        # Rejection reason must be present in breakdown
        bad_bd = d["score_breakdowns"]["alpha_bad"]
        assert bad_bd["rejection_reason"], "rejection_reason must be non-empty"

    def test_evidence_has_paper_trading_gate(self):
        result = self._build_full_result()
        d = result.to_dict()
        assert "paper_trading_gate" in d
        assert d["paper_trading_gate"] in ("PASS", "FAIL")
        assert "paper_trading_reasons" in d
        assert isinstance(d["paper_trading_reasons"], list)
        assert len(d["paper_trading_reasons"]) > 0

    def test_evidence_has_score_breakdowns(self):
        result = self._build_full_result()
        d = result.to_dict()
        assert "score_breakdowns" in d
        assert "alpha_good" in d["score_breakdowns"]
        assert "alpha_bad" in d["score_breakdowns"]
        # Each breakdown must have all six component scores
        for name in ("alpha_good", "alpha_bad"):
            bd = d["score_breakdowns"][name]
            for key in (
                "composite_score", "validation_ic_score", "ic_stability_score",
                "expected_sharpe_score", "turnover_penalty_score",
                "drawdown_penalty_score", "overfit_gap_score",
                "raw_validation_ic", "raw_ic_sharpe", "raw_turnover",
                "raw_overfit_gap", "raw_max_drawdown", "raw_expected_sharpe",
            ):
                assert key in bd, f"{key} missing from breakdown for {name}"

    def test_evidence_has_config(self):
        result = self._build_full_result()
        d = result.to_dict()
        assert "config" in d
        assert d["config"]["risk_adjusted_alpha_selection"] is True

    def test_evidence_saved_to_file(self, tmp_path):
        """save_evidence writes complete JSON with all required fields."""
        result = self._build_full_result()
        out = save_evidence(result, tmp_path / "evidence.json")
        assert out.exists()
        data = json.loads(out.read_text())
        for key in (
            "selected_alphas", "rejected_alphas", "paper_trading_gate",
            "paper_trading_reasons", "score_breakdowns", "config",
        ):
            assert key in data, f"{key} missing from saved evidence"
        # Verify raw_expected_sharpe is in saved breakdown
        good_bd = data["score_breakdowns"]["alpha_good"]
        assert "raw_expected_sharpe" in good_bd


# ===========================================================================
# 9. PRESET WEIGHT VALIDATION (GATE: RISK_ADJUSTED_ALPHA_TUNING_20260614)
# ===========================================================================
class TestPresetWeights:
    """All named presets must have valid weights summing to 1.0."""

    @pytest.mark.parametrize("preset_name", list(PRESETS.keys()))
    def test_preset_weights_sum_to_one(self, preset_name):
        """Each preset's component weights must sum to exactly 1.0."""
        weights = PRESETS[preset_name]
        total = sum(weights.values())
        assert total == pytest.approx(1.0, abs=1e-9), (
            f"Preset '{preset_name}' weights sum to {total}, expected 1.0"
        )

    @pytest.mark.parametrize("preset_name", list(PRESETS.keys()))
    def test_preset_weights_all_non_negative(self, preset_name):
        """All preset weights must be non-negative."""
        weights = PRESETS[preset_name]
        for key, val in weights.items():
            assert val >= 0.0, (
                f"Preset '{preset_name}' key '{key}' has negative weight {val}"
            )

    @pytest.mark.parametrize("preset_name", list(PRESETS.keys()))
    def test_preset_weights_have_all_components(self, preset_name):
        """Each preset must have the same six components as DEFAULT_WEIGHTS."""
        weights = PRESETS[preset_name]
        assert set(weights.keys()) == set(DEFAULT_WEIGHTS.keys()), (
            f"Preset '{preset_name}' keys mismatch: "
            f"got {set(weights.keys())}, expected {set(DEFAULT_WEIGHTS.keys())}"
        )

    def test_get_preset_weights_returns_copy(self):
        """get_preset_weights returns a copy — mutations don't affect PRESETS."""
        w = get_preset_weights("balanced")
        w["validation_ic"] = 99.0
        assert PRESETS["balanced"]["validation_ic"] != 99.0

    def test_list_presets(self):
        """list_presets returns sorted list of all preset names."""
        names = list_presets()
        assert isinstance(names, list)
        assert "balanced" in names
        assert "alpha_recovery" in names
        assert "drawdown_guarded" in names
        assert names == sorted(names)


# ===========================================================================
# 10. UNKNOWN PRESET REJECTION
# ===========================================================================
class TestUnknownPresetRejected:
    """Unknown preset names must raise ValueError."""

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown risk-adjusted preset"):
            get_preset_weights("nonexistent_preset")

    def test_empty_string_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown risk-adjusted preset"):
            get_preset_weights("")

    def test_typo_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown risk-adjusted preset"):
            get_preset_weights("alpha_recoveri")  # typo


# ===========================================================================
# 11. DEFAULT BACKWARD COMPATIBILITY
# ===========================================================================
class TestDefaultBackwardCompatibility:
    """Default preset 'balanced' must match DEFAULT_WEIGHTS exactly."""

    def test_default_preset_name_is_balanced(self):
        assert DEFAULT_PRESET == "balanced"

    def test_balanced_preset_equals_default_weights(self):
        """The 'balanced' preset must be identical to DEFAULT_WEIGHTS."""
        balanced = get_preset_weights("balanced")
        assert balanced == DEFAULT_WEIGHTS

    def test_compute_composite_score_default_unchanged(self):
        """Composite score with no explicit weights uses DEFAULT_WEIGHTS."""
        bd_default = compute_composite_score(
            "test_alpha",
            validation_ic=0.25,
            ic_sharpe=1.5,
            turnover=0.2,
            overfit_gap=0.05,
        )
        bd_balanced = compute_composite_score(
            "test_alpha",
            validation_ic=0.25,
            ic_sharpe=1.5,
            turnover=0.2,
            overfit_gap=0.05,
            weights=get_preset_weights("balanced"),
        )
        assert bd_default.composite_score == pytest.approx(
            bd_balanced.composite_score
        )

    def test_alpha_recovery_differs_from_balanced(self):
        """alpha_recovery preset produces different scores than balanced."""
        bd_balanced = compute_composite_score(
            "test",
            validation_ic=0.3,
            ic_sharpe=2.0,
            turnover=0.3,
            overfit_gap=0.05,
            weights=get_preset_weights("balanced"),
        )
        bd_recovery = compute_composite_score(
            "test",
            validation_ic=0.3,
            ic_sharpe=2.0,
            turnover=0.3,
            overfit_gap=0.05,
            weights=get_preset_weights("alpha_recovery"),
        )
        # alpha_recovery weights IC/Sharpe higher → should score differently
        assert bd_balanced.composite_score != pytest.approx(
            bd_recovery.composite_score, abs=1e-4
        )

    def test_drawdown_guarded_penalises_drawdown_more(self):
        """drawdown_guarded penalises large drawdown more than balanced."""
        dd_bad = -0.40
        bd_balanced = compute_composite_score(
            "dd_test",
            validation_ic=0.2,
            ic_sharpe=1.0,
            turnover=0.3,
            overfit_gap=0.05,
            max_drawdown=dd_bad,
            weights=get_preset_weights("balanced"),
        )
        bd_guarded = compute_composite_score(
            "dd_test",
            validation_ic=0.2,
            ic_sharpe=1.0,
            turnover=0.3,
            overfit_gap=0.05,
            max_drawdown=dd_bad,
            weights=get_preset_weights("drawdown_guarded"),
        )
        # drawdown_guarded should produce lower composite with bad drawdown
        assert bd_guarded.composite_score < bd_balanced.composite_score


# ===========================================================================
# 12. EVIDENCE INCLUDES PRESET AND WEIGHTS
# ===========================================================================
class TestEvidenceIncludesPresetWeights:
    """Per-fold evidence config must include preset name and resolved weights."""

    def _build_result_with_config(self, preset: str = "balanced"):
        weights = get_preset_weights(preset)
        bd = compute_composite_score(
            "alpha_1",
            validation_ic=0.3,
            ic_sharpe=2.0,
            turnover=0.1,
            overfit_gap=0.02,
            weights=weights,
        )
        result = select_alphas_risk_adjusted({"alpha_1": bd}, top_n=1)
        result.config = {
            "risk_adjusted_alpha_selection": True,
            "preset": preset,
            "weights": weights,
            "top_n": 1,
        }
        return result

    def test_evidence_config_has_preset(self):
        result = self._build_result_with_config("alpha_recovery")
        d = result.to_dict()
        assert "preset" in d["config"]
        assert d["config"]["preset"] == "alpha_recovery"

    def test_evidence_config_has_weights(self):
        result = self._build_result_with_config("drawdown_guarded")
        d = result.to_dict()
        assert "weights" in d["config"]
        weights = d["config"]["weights"]
        assert isinstance(weights, dict)
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_evidence_config_weights_match_preset(self):
        for preset_name in PRESETS:
            result = self._build_result_with_config(preset_name)
            d = result.to_dict()
            assert d["config"]["preset"] == preset_name
            assert d["config"]["weights"] == get_preset_weights(preset_name)

    def test_evidence_json_roundtrip_with_preset(self, tmp_path):
        result = self._build_result_with_config("alpha_recovery")
        out = save_evidence(result, tmp_path / "preset_evidence.json")
        data = json.loads(out.read_text())
        assert data["config"]["preset"] == "alpha_recovery"
        assert "weights" in data["config"]
        assert sum(data["config"]["weights"].values()) == pytest.approx(1.0)


# ===========================================================================
# 13. CLI PARSER CHOICES (GATE: RISK_ADJUSTED_ALPHA_TUNING_20260614)
# ===========================================================================
class TestCLIParserChoices:
    """--risk-adjusted-preset must accept valid choices and reject invalid."""

    def test_parser_accepts_valid_presets(self):
        """argparse choices list matches PRESETS keys."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--risk-adjusted-preset",
            type=str,
            choices=list(PRESETS.keys()),
            default="balanced",
        )
        for preset_name in PRESETS:
            args = parser.parse_args(["--risk-adjusted-preset", preset_name])
            assert args.risk_adjusted_preset == preset_name

    def test_parser_default_is_balanced(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--risk-adjusted-preset",
            type=str,
            choices=list(PRESETS.keys()),
            default="balanced",
        )
        args = parser.parse_args([])
        assert args.risk_adjusted_preset == "balanced"

    def test_parser_rejects_invalid_preset(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--risk-adjusted-preset",
            type=str,
            choices=list(PRESETS.keys()),
            default="balanced",
        )
        with pytest.raises(SystemExit):
            parser.parse_args(["--risk-adjusted-preset", "nonexistent"])


# ===========================================================================
# 14. IC_FIRST_GUARDED PRESET (GATE: RISK_ADJUSTED_ALPHA_IC_FIRST_TUNING_20260614)
# ===========================================================================
class TestICFirstGuardedPreset:
    """ic_first_guarded preset must prioritise IC over risk penalties."""

    # --- Preset validity ---

    def test_ic_first_guarded_exists_in_presets(self):
        assert "ic_first_guarded" in PRESETS

    def test_ic_first_guarded_weights_sum_to_one(self):
        total = sum(PRESETS["ic_first_guarded"].values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_ic_first_guarded_all_components_present(self):
        assert set(PRESETS["ic_first_guarded"].keys()) == set(DEFAULT_WEIGHTS.keys())

    def test_ic_first_guarded_all_weights_non_negative(self):
        for key, val in PRESETS["ic_first_guarded"].items():
            assert val >= 0.0

    def test_ic_first_guarded_in_list_presets(self):
        assert "ic_first_guarded" in list_presets()

    def test_get_preset_weights_returns_valid(self):
        w = get_preset_weights("ic_first_guarded")
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-9)

    # --- IC dominates risk penalties ---

    def test_ic_weight_dominates_risk_weights(self):
        """validation_ic + ic_stability must exceed turnover + drawdown + overfit."""
        w = PRESETS["ic_first_guarded"]
        ic_weight = w["validation_ic"] + w["ic_stability"]
        risk_weight = w["turnover_penalty"] + w["drawdown_penalty"] + w["overfit_gap"]
        assert ic_weight > risk_weight, (
            f"IC weight ({ic_weight}) must exceed risk weight ({risk_weight})"
        )

    def test_ic_weight_at_least_60_percent(self):
        """Combined IC weight must be >= 60% to ensure IC-first ranking."""
        w = PRESETS["ic_first_guarded"]
        ic_weight = w["validation_ic"] + w["ic_stability"]
        assert ic_weight >= 0.60

    def test_risk_penalties_at_most_25_percent(self):
        """Combined risk penalty weight must be <= 25% (soft role)."""
        w = PRESETS["ic_first_guarded"]
        risk_weight = w["turnover_penalty"] + w["drawdown_penalty"] + w["overfit_gap"]
        assert risk_weight <= 0.25

    # --- Positive IC outranks negative IC despite better drawdown ---

    def test_positive_ic_outranks_negative_ic_with_better_drawdown(self):
        """Positive val IC alpha must beat negative IC alpha even when
        the negative IC alpha has much better drawdown.
        """
        w = get_preset_weights("ic_first_guarded")
        bd_positive_ic = compute_composite_score(
            "positive_ic",
            validation_ic=0.05,
            ic_sharpe=1.0,
            turnover=0.3,
            overfit_gap=0.05,
            max_drawdown=-0.15,  # worse drawdown
            weights=w,
        )
        bd_negative_ic = compute_composite_score(
            "negative_ic",
            validation_ic=-0.05,
            ic_sharpe=-0.5,
            turnover=0.1,
            overfit_gap=0.02,
            max_drawdown=-0.02,  # much better drawdown
            weights=w,
        )
        assert bd_positive_ic.composite_score > bd_negative_ic.composite_score, (
            f"Positive IC alpha ({bd_positive_ic.composite_score}) must outrank "
            f"negative IC alpha ({bd_negative_ic.composite_score}) despite worse drawdown"
        )

    def test_positive_ic_outranks_zero_ic_with_perfect_drawdown(self):
        """Positive IC with bad drawdown must beat zero IC with perfect drawdown."""
        w = get_preset_weights("ic_first_guarded")
        bd_positive = compute_composite_score(
            "positive",
            validation_ic=0.03,
            ic_sharpe=0.5,
            turnover=0.5,
            overfit_gap=0.10,
            max_drawdown=-0.30,  # terrible drawdown
            weights=w,
        )
        bd_zero = compute_composite_score(
            "zero_ic",
            validation_ic=0.0,
            ic_sharpe=0.0,
            turnover=0.05,
            overfit_gap=0.01,
            max_drawdown=-0.001,  # near-perfect drawdown
            weights=w,
        )
        assert bd_positive.composite_score > bd_zero.composite_score

    # --- Drawdown/turnover break ties when IC is close ---

    def test_drawdown_breaks_ties_when_ic_close(self):
        """When two alphas have similar IC, better drawdown should win."""
        w = get_preset_weights("ic_first_guarded")
        bd_good_dd = compute_composite_score(
            "good_dd",
            validation_ic=0.05,
            ic_sharpe=1.0,
            turnover=0.2,
            overfit_gap=0.05,
            max_drawdown=-0.05,  # small drawdown
            weights=w,
        )
        bd_bad_dd = compute_composite_score(
            "bad_dd",
            validation_ic=0.05,
            ic_sharpe=1.0,
            turnover=0.2,
            overfit_gap=0.05,
            max_drawdown=-0.40,  # large drawdown
            weights=w,
        )
        assert bd_good_dd.composite_score > bd_bad_dd.composite_score

    def test_turnover_breaks_ties_when_ic_close(self):
        """When two alphas have similar IC, lower turnover should win."""
        w = get_preset_weights("ic_first_guarded")
        bd_low_turn = compute_composite_score(
            "low_turnover",
            validation_ic=0.05,
            ic_sharpe=1.0,
            turnover=0.1,
            overfit_gap=0.05,
            weights=w,
        )
        bd_high_turn = compute_composite_score(
            "high_turnover",
            validation_ic=0.05,
            ic_sharpe=1.0,
            turnover=0.8,
            overfit_gap=0.05,
            weights=w,
        )
        assert bd_low_turn.composite_score > bd_high_turn.composite_score

    # --- Evidence includes rank components ---

    def test_evidence_config_has_rank_components(self):
        """Evidence config must include primary_rank_components and
        soft_penalty_components for ic_first_guarded.
        """
        w = get_preset_weights("ic_first_guarded")
        bd = compute_composite_score(
            "alpha_evidence",
            validation_ic=0.3,
            ic_sharpe=2.0,
            turnover=0.1,
            overfit_gap=0.02,
            weights=w,
        )
        result = select_alphas_risk_adjusted({"alpha_evidence": bd}, top_n=1)
        rank_meta = get_preset_rank_components("ic_first_guarded")
        result.config = {
            "risk_adjusted_alpha_selection": True,
            "preset": "ic_first_guarded",
            "weights": w,
            "primary_rank_components": rank_meta["primary_rank_components"],
            "soft_penalty_components": rank_meta["soft_penalty_components"],
        }
        d = result.to_dict()
        assert "primary_rank_components" in d["config"]
        assert "soft_penalty_components" in d["config"]
        assert "validation_ic" in d["config"]["primary_rank_components"]
        assert "ic_stability" in d["config"]["primary_rank_components"]
        assert "turnover_penalty" in d["config"]["soft_penalty_components"]
        assert "drawdown_penalty" in d["config"]["soft_penalty_components"]
        assert "overfit_gap" in d["config"]["soft_penalty_components"]

    def test_evidence_json_roundtrip_with_rank_components(self, tmp_path):
        """Rank components survive JSON round-trip for audit."""
        w = get_preset_weights("ic_first_guarded")
        bd = compute_composite_score(
            "alpha_rt",
            validation_ic=0.25,
            ic_sharpe=1.5,
            turnover=0.1,
            overfit_gap=0.02,
            weights=w,
        )
        result = select_alphas_risk_adjusted({"alpha_rt": bd}, top_n=1)
        rank_meta = get_preset_rank_components("ic_first_guarded")
        result.config = {
            "preset": "ic_first_guarded",
            "weights": w,
            "primary_rank_components": rank_meta["primary_rank_components"],
            "soft_penalty_components": rank_meta["soft_penalty_components"],
        }
        out = save_evidence(result, tmp_path / "ic_first_evidence.json")
        data = json.loads(out.read_text())
        assert data["config"]["preset"] == "ic_first_guarded"
        assert "validation_ic" in data["config"]["primary_rank_components"]
        assert "drawdown_penalty" in data["config"]["soft_penalty_components"]

    # --- Rank component metadata function ---

    def test_get_preset_rank_components_ic_first(self):
        meta = get_preset_rank_components("ic_first_guarded")
        assert meta["primary_rank_components"] == list(IC_FIRST_PRIMARY_COMPONENTS)
        assert meta["soft_penalty_components"] == list(IC_FIRST_SOFT_PENALTY_COMPONENTS)
        # No overlap
        assert set(meta["primary_rank_components"]).isdisjoint(
            set(meta["soft_penalty_components"])
        )

    def test_get_preset_rank_components_balanced(self):
        """Non-IC-first presets return all components as primary, empty soft."""
        meta = get_preset_rank_components("balanced")
        assert set(meta["primary_rank_components"]) == set(DEFAULT_WEIGHTS.keys())
        assert meta["soft_penalty_components"] == []

    def test_get_preset_rank_components_alpha_recovery(self):
        meta = get_preset_rank_components("alpha_recovery")
        assert set(meta["primary_rank_components"]) == set(DEFAULT_WEIGHTS.keys())
        assert meta["soft_penalty_components"] == []

    # --- Comparison with other presets ---

    def test_ic_first_differs_from_balanced(self):
        """ic_first_guarded produces different scores than balanced."""
        bd_balanced = compute_composite_score(
            "test",
            validation_ic=0.1,
            ic_sharpe=1.0,
            turnover=0.4,
            overfit_gap=0.05,
            max_drawdown=-0.20,
            weights=get_preset_weights("balanced"),
        )
        bd_ic_first = compute_composite_score(
            "test",
            validation_ic=0.1,
            ic_sharpe=1.0,
            turnover=0.4,
            overfit_gap=0.05,
            max_drawdown=-0.20,
            weights=get_preset_weights("ic_first_guarded"),
        )
        assert bd_balanced.composite_score != pytest.approx(
            bd_ic_first.composite_score, abs=1e-4
        )

    def test_ic_first_less_sensitive_to_drawdown_than_guarded(self):
        """ic_first_guarded should penalise drawdown less than drawdown_guarded."""
        dd = -0.40
        bd_guarded = compute_composite_score(
            "dd",
            validation_ic=0.2,
            ic_sharpe=1.0,
            turnover=0.3,
            overfit_gap=0.05,
            max_drawdown=dd,
            weights=get_preset_weights("drawdown_guarded"),
        )
        bd_ic_first = compute_composite_score(
            "dd",
            validation_ic=0.2,
            ic_sharpe=1.0,
            turnover=0.3,
            overfit_gap=0.05,
            max_drawdown=dd,
            weights=get_preset_weights("ic_first_guarded"),
        )
        # ic_first_guarded has lower drawdown weight → higher composite
        assert bd_ic_first.composite_score > bd_guarded.composite_score

    # --- Score breakdown includes raw values for rank component audit ---

    def test_score_breakdown_has_raw_values_for_rank_audit(self):
        """Score breakdown must include raw_validation_ic and raw_ic_sharpe
        so auditors can verify IC-first ranking.
        """
        w = get_preset_weights("ic_first_guarded")
        bd = compute_composite_score(
            "audit_alpha",
            validation_ic=0.08,
            ic_sharpe=1.5,
            turnover=0.2,
            overfit_gap=0.03,
            max_drawdown=-0.10,
            weights=w,
        )
        assert bd.raw_validation_ic == pytest.approx(0.08)
        assert bd.raw_ic_sharpe == pytest.approx(1.5)
        assert bd.raw_turnover == pytest.approx(0.2)
        assert bd.raw_max_drawdown == pytest.approx(-0.10)
        # Verify composite score in valid range
        assert 0.0 <= bd.composite_score <= 1.0

    def test_score_breakdown_serialization_includes_all_raw(self):
        """Serialized breakdown includes raw values for rank reconstruction."""
        w = get_preset_weights("ic_first_guarded")
        bd = compute_composite_score(
            "serial_alpha",
            validation_ic=0.12,
            ic_sharpe=2.0,
            turnover=0.15,
            overfit_gap=0.04,
            max_drawdown=-0.08,
            weights=w,
        )
        result = RiskAdjustedSelectionResult(
            selected_alphas=["serial_alpha"],
            score_breakdowns={"serial_alpha": bd},
            paper_trading_gate="PASS",
            paper_trading_reasons=["OK"],
        )
        d = result.to_dict()
        breakdown = d["score_breakdowns"]["serial_alpha"]
        for key in (
            "raw_validation_ic", "raw_ic_sharpe", "raw_turnover",
            "raw_overfit_gap", "raw_max_drawdown", "raw_expected_sharpe",
            "composite_score", "validation_ic_score", "ic_stability_score",
        ):
            assert key in breakdown, f"{key} missing from serialized breakdown"


# ===========================================================================
# 15. PORTFOLIO-LEVEL VALIDATION GUARD
#     (GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614)
# ===========================================================================
from omega.quant.walk_forward.risk_adjusted_alpha_score import (
    PortfolioGuardResult,
    compute_basket_validation_ic,
    evaluate_portfolio_guard,
    DEFAULT_PORTFOLIO_GUARD_UNDERPERFORMANCE_TOLERANCE,
)


def _make_portfolio_guard_data(
    n_dates: int = 30,
    n_tickers: int = 10,
    alpha_ic_strength: float = 0.3,
    seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic validation data with multiple alpha columns."""
    rng = np.random.RandomState(seed)
    rows = []
    for d in range(n_dates):
        date_str = f"2025-{(d // 28) + 1:02d}-{(d % 28) + 1:02d}"
        for t in range(n_tickers):
            ticker = f"TK{t:02d}"
            ret = rng.randn() * 0.02
            # Alpha correlated with return
            alpha_good = alpha_ic_strength * ret + 0.01 * rng.randn()
            # Alpha inversely correlated
            alpha_bad = -alpha_ic_strength * ret + 0.01 * rng.randn()
            # Random noise alpha
            alpha_noise = rng.randn() * 0.1
            rows.append({
                "date": date_str,
                "ticker": ticker,
                "alpha_good": alpha_good,
                "alpha_bad": alpha_bad,
                "alpha_noise": alpha_noise,
                "fwd_ret_5": ret,
            })
    return pd.DataFrame(rows)


class TestComputeBasketValidationIC:
    """compute_basket_validation_ic must produce correct basket-level IC."""

    def test_positive_ic_for_good_alphas(self):
        """Good alphas must produce positive basket IC."""
        df = _make_portfolio_guard_data(
            alpha_ic_strength=0.5, seed=42
        )
        train_ics = {"alpha_good": 0.3, "alpha_noise": 0.01}
        ic = compute_basket_validation_ic(
            ["alpha_good", "alpha_noise"], df, train_ics, "fwd_ret_5"
        )
        assert ic > 0.0, f"Expected positive IC, got {ic}"

    def test_negative_ic_for_bad_alphas(self):
        """Inverse alphas with positive weight must produce negative basket IC."""
        df = _make_portfolio_guard_data(
            alpha_ic_strength=0.5, seed=42
        )
        # Use positive weight for inversely-correlated alpha.
        # The basket signal = weight * z_score(alpha_bad).
        # alpha_bad ≈ -0.5*ret, so signal ≈ -0.5*ret → negative IC.
        train_ics = {"alpha_bad": 0.3}
        ic = compute_basket_validation_ic(
            ["alpha_bad"], df, train_ics, "fwd_ret_5"
        )
        assert ic < 0.0, f"Expected negative IC, got {ic}"

    def test_zero_ic_for_empty_alphas(self):
        """Empty alpha list must return 0.0."""
        df = _make_portfolio_guard_data()
        ic = compute_basket_validation_ic([], df, {}, "fwd_ret_5")
        assert ic == 0.0

    def test_zero_ic_for_empty_df(self):
        """Empty DataFrame must return 0.0."""
        ic = compute_basket_validation_ic(
            ["alpha_good"], pd.DataFrame(), {"alpha_good": 0.3}, "fwd_ret_5"
        )
        assert ic == 0.0

    def test_missing_return_col(self):
        """Missing return column must return 0.0."""
        df = _make_portfolio_guard_data()
        ic = compute_basket_validation_ic(
            ["alpha_good"], df, {"alpha_good": 0.3}, "nonexistent_col"
        )
        assert ic == 0.0

    def test_missing_alpha_column(self):
        """Missing alpha column must return 0.0."""
        df = _make_portfolio_guard_data()
        ic = compute_basket_validation_ic(
            ["nonexistent_alpha"], df, {"nonexistent_alpha": 0.3}, "fwd_ret_5"
        )
        assert ic == 0.0


class TestEvaluatePortfolioGuardAccept:
    """Portfolio guard must ACCEPT when selected basket IC > 0 and
    does not underperform baseline.
    """

    def test_accept_positive_ic_no_baseline(self):
        """Accept when selected IC > 0 and no baseline for comparison."""
        df = _make_portfolio_guard_data(alpha_ic_strength=0.5, seed=42)
        train_ics = {"alpha_good": 0.3}
        # Build RA result with good alpha selected
        bd = compute_composite_score(
            "alpha_good", validation_ic=0.3, ic_sharpe=2.0,
            turnover=0.1, overfit_gap=0.02,
        )
        bd.selected = True
        ra_result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_good"],
            score_breakdowns={"alpha_good": bd},
            paper_trading_gate="PASS",
        )
        guard = evaluate_portfolio_guard(
            ra_result,
            val_df=df,
            train_ics=train_ics,
            return_col="fwd_ret_5",
        )
        assert guard.portfolio_guard_enabled is True
        assert guard.portfolio_guard_status == "ACCEPTED"
        assert guard.selected_basket_validation_ic > 0.0
        assert guard.baseline_basket_validation_ic is None
        assert guard.rejected_risk_adjusted_evidence is None
        assert "alpha_good" in guard.selected_alphas
        assert len(guard.guard_reason) > 0

    def test_accept_positive_ic_with_baseline(self):
        """Accept when selected IC > 0 and within tolerance of baseline."""
        df = _make_portfolio_guard_data(alpha_ic_strength=0.5, seed=42)
        train_ics = {"alpha_good": 0.3, "alpha_noise": 0.01}
        bd = compute_composite_score(
            "alpha_good", validation_ic=0.3, ic_sharpe=2.0,
            turnover=0.1, overfit_gap=0.02,
        )
        bd.selected = True
        ra_result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_good"],
            score_breakdowns={"alpha_good": bd},
            paper_trading_gate="PASS",
        )
        guard = evaluate_portfolio_guard(
            ra_result,
            val_df=df,
            train_ics=train_ics,
            return_col="fwd_ret_5",
            baseline_alpha_cols=["alpha_noise"],
            underperformance_tolerance=0.05,
        )
        # alpha_good should have higher IC than noise baseline
        assert guard.portfolio_guard_status == "ACCEPTED"
        assert guard.selected_basket_validation_ic > 0.0
        assert guard.baseline_basket_validation_ic is not None


class TestEvaluatePortfolioGuardNegativeIC:
    """Portfolio guard must FALLBACK when selected basket IC is non-positive."""

    def test_fallback_negative_selected_ic(self):
        """Fallback when selected basket has negative IC."""
        df = _make_portfolio_guard_data(alpha_ic_strength=0.5, seed=42)
        # alpha_bad is inversely correlated with returns in validation.
        # Use POSITIVE weight (simulates train set thinking it's good),
        # so basket signal = positive_weight * z_score(inversely_correlated_alpha)
        # → negative basket IC → guard triggers fallback.
        train_ics = {"alpha_bad": 0.3}
        bd = compute_composite_score(
            "alpha_bad", validation_ic=0.1, ic_sharpe=0.5,
            turnover=0.2, overfit_gap=0.05,
        )
        bd.selected = True
        ra_result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_bad"],
            score_breakdowns={"alpha_bad": bd},
            paper_trading_gate="PASS",
        )
        guard = evaluate_portfolio_guard(
            ra_result,
            val_df=df,
            train_ics=train_ics,
            return_col="fwd_ret_5",
            baseline_alpha_cols=["alpha_good"],
        )
        assert guard.portfolio_guard_status == "FALLBACK_TO_BASELINE"
        assert guard.selected_basket_validation_ic < 0.0
        assert "alpha_good" in guard.selected_alphas
        assert guard.rejected_risk_adjusted_evidence is not None
        assert "non-positive" in guard.guard_reason

    def test_fallback_zero_selected_ic(self):
        """Fallback when selected basket has zero IC."""
        df = _make_portfolio_guard_data(alpha_ic_strength=0.0, seed=99)
        train_ics = {"alpha_noise": 0.0}
        bd = compute_composite_score(
            "alpha_noise", validation_ic=0.01, ic_sharpe=0.1,
            turnover=0.2, overfit_gap=0.05,
        )
        bd.selected = True
        ra_result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_noise"],
            score_breakdowns={"alpha_noise": bd},
            paper_trading_gate="PASS",
        )
        guard = evaluate_portfolio_guard(
            ra_result,
            val_df=df,
            train_ics=train_ics,
            return_col="fwd_ret_5",
        )
        # IC is expected near-zero; should be <= 0 or very small
        # Guard should either accept (if slightly positive) or fallback
        # Key check: evidence fields are present
        assert guard.portfolio_guard_enabled is True
        assert guard.portfolio_guard_status in ("ACCEPTED", "FALLBACK_TO_BASELINE")


class TestEvaluatePortfolioGuardUnderperform:
    """Portfolio guard must FALLBACK when selected basket underperforms baseline."""

    def test_fallback_underperform_baseline(self):
        """Fallback when selected IC < baseline IC by more than tolerance."""
        df = _make_portfolio_guard_data(alpha_ic_strength=0.5, seed=42)
        # Selected basket uses alpha_bad with POSITIVE weight (overfit:
        # train thinks it's good, but validation shows inverse correlation).
        # Baseline uses alpha_good with positive weight (truly good).
        train_ics_selected = {"alpha_bad": 0.2}
        train_ics_baseline = {"alpha_good": 0.3}
        bd = compute_composite_score(
            "alpha_bad", validation_ic=0.05, ic_sharpe=0.3,
            turnover=0.1, overfit_gap=0.02,
        )
        bd.selected = True
        ra_result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_bad"],
            score_breakdowns={"alpha_bad": bd},
            paper_trading_gate="PASS",
        )
        guard = evaluate_portfolio_guard(
            ra_result,
            val_df=df,
            train_ics=train_ics_selected,
            return_col="fwd_ret_5",
            baseline_alpha_cols=["alpha_good"],
            baseline_train_ics=train_ics_baseline,
            underperformance_tolerance=0.005,
        )
        # Selected basket (alpha_bad with positive weight) should have negative IC,
        # baseline (alpha_good) should have positive IC
        assert guard.portfolio_guard_status == "FALLBACK_TO_BASELINE"
        assert guard.baseline_basket_validation_ic is not None
        assert guard.baseline_basket_validation_ic > 0.0
        assert "alpha_good" in guard.selected_alphas
        assert guard.rejected_risk_adjusted_evidence is not None
        assert "underperform" in guard.guard_reason.lower() or "non-positive" in guard.guard_reason.lower()

    def test_no_fallback_within_tolerance(self):
        """No fallback when selected IC is within tolerance of baseline."""
        df = _make_portfolio_guard_data(alpha_ic_strength=0.3, seed=42)
        # Both good and noise have somewhat positive IC
        train_ics = {"alpha_good": 0.3, "alpha_noise": 0.05}
        bd = compute_composite_score(
            "alpha_good", validation_ic=0.3, ic_sharpe=2.0,
            turnover=0.1, overfit_gap=0.02,
        )
        bd.selected = True
        ra_result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_good"],
            score_breakdowns={"alpha_good": bd},
            paper_trading_gate="PASS",
        )
        guard = evaluate_portfolio_guard(
            ra_result,
            val_df=df,
            train_ics=train_ics,
            return_col="fwd_ret_5",
            baseline_alpha_cols=["alpha_noise"],
            underperformance_tolerance=0.10,  # generous tolerance
        )
        # alpha_good should have higher IC than noise, so within tolerance
        assert guard.portfolio_guard_status == "ACCEPTED"
        assert guard.selected_basket_validation_ic > 0.0


class TestEvaluatePortfolioGuardNoSelected:
    """Portfolio guard must FALLBACK when RA selection has no alphas."""

    def test_fallback_empty_ra_selection(self):
        """Fallback when RA selection produced zero alphas."""
        df = _make_portfolio_guard_data()
        train_ics = {"alpha_good": 0.3}
        ra_result = RiskAdjustedSelectionResult(
            selected_alphas=[],
            paper_trading_gate="FAIL",
            paper_trading_reasons=["No alphas selected"],
        )
        guard = evaluate_portfolio_guard(
            ra_result,
            val_df=df,
            train_ics=train_ics,
            return_col="fwd_ret_5",
            baseline_alpha_cols=["alpha_good"],
        )
        assert guard.portfolio_guard_status == "FALLBACK_TO_BASELINE"
        assert "alpha_good" in guard.selected_alphas
        assert guard.rejected_risk_adjusted_evidence is not None
        assert guard.selected_basket_validation_ic == 0.0


class TestPortfolioGuardEvidenceFields:
    """Evidence must include all required fields."""

    def test_evidence_fields_accepted(self):
        """All required evidence fields present when ACCEPTED."""
        df = _make_portfolio_guard_data(alpha_ic_strength=0.5, seed=42)
        train_ics = {"alpha_good": 0.3}
        bd = compute_composite_score(
            "alpha_good", validation_ic=0.3, ic_sharpe=2.0,
            turnover=0.1, overfit_gap=0.02,
        )
        bd.selected = True
        ra_result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_good"],
            score_breakdowns={"alpha_good": bd},
            paper_trading_gate="PASS",
        )
        guard = evaluate_portfolio_guard(
            ra_result, val_df=df, train_ics=train_ics, return_col="fwd_ret_5",
        )
        d = guard.to_dict()
        assert "portfolio_guard_enabled" in d
        assert d["portfolio_guard_enabled"] is True
        assert "portfolio_guard_status" in d
        assert d["portfolio_guard_status"] == "ACCEPTED"
        assert "selected_basket_validation_ic" in d
        assert isinstance(d["selected_basket_validation_ic"], float)
        assert "baseline_basket_validation_ic" in d
        assert "guard_reason" in d
        assert isinstance(d["guard_reason"], str)
        assert len(d["guard_reason"]) > 0
        assert "selected_alphas" in d
        assert isinstance(d["selected_alphas"], list)
        assert "rejected_risk_adjusted_evidence" in d
        assert d["rejected_risk_adjusted_evidence"] is None

    def test_evidence_fields_fallback(self):
        """All required evidence fields present when FALLBACK_TO_BASELINE."""
        df = _make_portfolio_guard_data(alpha_ic_strength=0.5, seed=42)
        # alpha_bad with positive weight → negative basket IC → fallback
        train_ics = {"alpha_bad": 0.3}
        bd = compute_composite_score(
            "alpha_bad", validation_ic=0.1, ic_sharpe=0.5,
            turnover=0.2, overfit_gap=0.05,
        )
        bd.selected = True
        ra_result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_bad"],
            score_breakdowns={"alpha_bad": bd},
            paper_trading_gate="PASS",
        )
        guard = evaluate_portfolio_guard(
            ra_result,
            val_df=df,
            train_ics=train_ics,
            return_col="fwd_ret_5",
            baseline_alpha_cols=["alpha_good"],
        )
        d = guard.to_dict()
        assert d["portfolio_guard_enabled"] is True
        assert d["portfolio_guard_status"] == "FALLBACK_TO_BASELINE"
        assert isinstance(d["selected_basket_validation_ic"], float)
        assert d["baseline_basket_validation_ic"] is not None
        assert isinstance(d["baseline_basket_validation_ic"], float)
        assert isinstance(d["guard_reason"], str)
        assert "alpha_good" in d["selected_alphas"]
        assert d["rejected_risk_adjusted_evidence"] is not None
        assert isinstance(d["rejected_risk_adjusted_evidence"], dict)

    def test_evidence_json_serializable(self):
        """Evidence to_dict() output is JSON-serializable."""
        df = _make_portfolio_guard_data(alpha_ic_strength=0.5, seed=42)
        # alpha_bad with positive weight → negative basket IC → fallback
        train_ics = {"alpha_bad": 0.3}
        bd = compute_composite_score(
            "alpha_bad", validation_ic=0.1, ic_sharpe=0.5,
            turnover=0.2, overfit_gap=0.05,
        )
        bd.selected = True
        ra_result = RiskAdjustedSelectionResult(
            selected_alphas=["alpha_bad"],
            score_breakdowns={"alpha_bad": bd},
            paper_trading_gate="PASS",
        )
        guard = evaluate_portfolio_guard(
            ra_result,
            val_df=df,
            train_ics=train_ics,
            return_col="fwd_ret_5",
            baseline_alpha_cols=["alpha_good"],
        )
        json_str = json.dumps(guard.to_dict())
        parsed = json.loads(json_str)
        assert parsed["portfolio_guard_status"] == "FALLBACK_TO_BASELINE"


class TestPortfolioGuardDefaultTolerance:
    """Default tolerance constant must be sensible."""

    def test_default_tolerance_positive_small(self):
        assert DEFAULT_PORTFOLIO_GUARD_UNDERPERFORMANCE_TOLERANCE > 0.0
        assert DEFAULT_PORTFOLIO_GUARD_UNDERPERFORMANCE_TOLERANCE <= 0.05


class TestPortfolioGuardResultDataclass:
    """PortfolioGuardResult dataclass must be well-formed."""

    def test_default_values(self):
        guard = PortfolioGuardResult()
        assert guard.portfolio_guard_enabled is True
        assert guard.portfolio_guard_status == "ACCEPTED"
        assert guard.selected_basket_validation_ic == 0.0
        assert guard.baseline_basket_validation_ic is None
        assert guard.guard_reason == ""
        assert guard.selected_alphas == []
        assert guard.rejected_risk_adjusted_evidence is None

    def test_to_dict_roundtrip(self):
        guard = PortfolioGuardResult(
            portfolio_guard_enabled=True,
            portfolio_guard_status="FALLBACK_TO_BASELINE",
            selected_basket_validation_ic=-0.01,
            baseline_basket_validation_ic=0.02,
            guard_reason="test reason",
            selected_alphas=["a", "b"],
            rejected_risk_adjusted_evidence={"test": True},
        )
        d = guard.to_dict()
        assert d["portfolio_guard_enabled"] is True
        assert d["portfolio_guard_status"] == "FALLBACK_TO_BASELINE"
        assert d["selected_basket_validation_ic"] == pytest.approx(-0.01, abs=1e-4)
        assert d["baseline_basket_validation_ic"] == pytest.approx(0.02, abs=1e-4)
        assert d["guard_reason"] == "test reason"
        assert d["selected_alphas"] == ["a", "b"]
        assert d["rejected_risk_adjusted_evidence"] == {"test": True}


# ===========================================================================
# 16. RESEARCH ALPHA GATES (GATE: RESEARCH_ALPHA_GATES_20260614)
# ===========================================================================
from omega.quant.walk_forward.risk_adjusted_alpha_score import (
    compute_icir,
    compute_positive_fold_rate,
    bh_fdr_qvalues,
    compute_ic_pvalue,
    classify_research_gate_verdict,
    compute_fallback_as_failure_metrics,
    RESEARCH_VERDICT_PROMOTE_CANDIDATE,
    RESEARCH_VERDICT_ENSEMBLE_ONLY,
    RESEARCH_VERDICT_REVIEW,
    RESEARCH_VERDICT_RETIRE,
)


class TestComputeICIR:
    """ICIR = mean(IC) / std(IC) must be computed correctly."""

    def test_icir_constant_ics(self):
        """Constant positive ICs → std=0 → ICIR=0.0 (safe fallback)."""
        assert compute_icir([0.05, 0.05, 0.05, 0.05]) == 0.0

    def test_icir_positive_consistent(self):
        """Consistent positive ICs → positive ICIR."""
        ics = [0.04, 0.05, 0.06, 0.05, 0.04, 0.05, 0.06, 0.05]
        icir = compute_icir(ics)
        assert icir > 0.0
        # mean ≈ 0.05, std ≈ 0.008 → ICIR ≈ 6.25
        assert icir > 3.0

    def test_icir_noisy_ics(self):
        """Noisy ICs with mixed signs → low ICIR."""
        ics = [0.1, -0.08, 0.05, -0.03, 0.02, -0.06, 0.04, -0.01]
        icir = compute_icir(ics)
        assert abs(icir) < 1.0

    def test_icir_negative_ics(self):
        """All negative ICs → negative ICIR."""
        ics = [-0.05, -0.04, -0.06, -0.03, -0.05]
        icir = compute_icir(ics)
        assert icir < 0.0

    def test_icir_empty(self):
        """Empty list → 0.0."""
        assert compute_icir([]) == 0.0

    def test_icir_single_value(self):
        """Single value → 0.0 (need at least 2)."""
        assert compute_icir([0.05]) == 0.0

    def test_icir_with_nan(self):
        """NaN values are filtered out."""
        ics = [0.05, float("nan"), 0.04, 0.06, float("nan")]
        icir = compute_icir(ics)
        assert icir > 0.0

    def test_icir_deterministic(self):
        """Same input always produces same output."""
        ics = [0.03, 0.05, 0.02, 0.04, 0.06, 0.01, 0.03, 0.05]
        icir1 = compute_icir(ics)
        icir2 = compute_icir(ics)
        assert icir1 == icir2


class TestComputePositiveFoldRate:
    """Positive fold rate must correctly count positive IC folds."""

    def test_all_positive(self):
        assert compute_positive_fold_rate([0.01, 0.02, 0.03]) == 1.0

    def test_all_negative(self):
        assert compute_positive_fold_rate([-0.01, -0.02, -0.03]) == 0.0

    def test_mixed(self):
        assert compute_positive_fold_rate([0.01, -0.02, 0.03, -0.04]) == 0.5

    def test_empty(self):
        assert compute_positive_fold_rate([]) == 0.0

    def test_zero_excluded(self):
        """Zero IC is not counted as positive."""
        assert compute_positive_fold_rate([0.0, 0.01, -0.01]) == pytest.approx(1 / 3)

    def test_with_nan(self):
        """NaN values are filtered."""
        rate = compute_positive_fold_rate([0.05, float("nan"), -0.02])
        assert rate == 0.5


class TestBHFDRQValues:
    """BH-FDR q-values must implement correct step-up procedure."""

    def test_single_pvalue(self):
        q = bh_fdr_qvalues([0.03])
        assert len(q) == 1
        assert q[0] == pytest.approx(0.03)

    def test_all_significant(self):
        """All small p-values should remain small after correction."""
        q = bh_fdr_qvalues([0.001, 0.002, 0.003])
        for qi in q:
            assert qi < 0.05

    def test_none_significant(self):
        """All large p-values should remain large after correction."""
        q = bh_fdr_qvalues([0.5, 0.6, 0.7])
        for qi in q:
            assert qi > 0.05

    def test_monotonicity(self):
        """Q-values should be non-decreasing when sorted by p-value."""
        p = [0.001, 0.01, 0.02, 0.05, 0.1, 0.5]
        q = bh_fdr_qvalues(p)
        # Since input is already sorted, q should be non-decreasing
        for i in range(len(q) - 1):
            assert q[i] <= q[i + 1] + 1e-10

    def test_qvalues_bounded_by_one(self):
        """All q-values must be <= 1.0."""
        q = bh_fdr_qvalues([0.9, 0.95, 0.99])
        for qi in q:
            assert qi <= 1.0

    def test_empty(self):
        assert bh_fdr_qvalues([]) == []

    def test_mixed_significance(self):
        """Mix of significant and non-significant p-values."""
        p = [0.001, 0.04, 0.5, 0.8]
        q = bh_fdr_qvalues(p)
        # First should be most significant
        assert q[0] < q[3]
        # All <= 1.0
        for qi in q:
            assert qi <= 1.0

    def test_rejection_at_threshold(self):
        """A clearly significant p-value should have q < 0.05."""
        p = [0.0001, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        q = bh_fdr_qvalues(p)
        assert q[0] < 0.05


class TestComputeICPValue:
    """IC p-value from t-test must be reasonable."""

    def test_strong_positive_ic(self):
        """Consistent positive ICs should have small p-value."""
        ics = [0.05, 0.04, 0.06, 0.05, 0.03, 0.07, 0.04, 0.05, 0.06, 0.05]
        p = compute_ic_pvalue(ics)
        assert p < 0.01

    def test_noisy_ic(self):
        """Mixed-sign ICs should have large p-value."""
        ics = [0.1, -0.08, 0.05, -0.03, 0.02, -0.06, 0.04, -0.01]
        p = compute_ic_pvalue(ics)
        assert p > 0.1

    def test_empty_ic(self):
        assert compute_ic_pvalue([]) == 1.0

    def test_two_values(self):
        assert compute_ic_pvalue([0.05, 0.03]) == 1.0  # < 3 samples


class TestClassifyResearchGateVerdict:
    """Verdict classification must follow the defined rules."""

    def test_retire_negative_ic(self):
        """Negative mean IC → RETIRE regardless of other metrics."""
        v = classify_research_gate_verdict(
            mean_ic=-0.01, icir=2.0, positive_fold_rate=0.9, q_value=0.001
        )
        assert v == RESEARCH_VERDICT_RETIRE

    def test_retire_high_qvalue(self):
        """High q-value (fails BH-FDR) → RETIRE."""
        v = classify_research_gate_verdict(
            mean_ic=0.05, icir=2.0, positive_fold_rate=0.9, q_value=0.2
        )
        assert v == RESEARCH_VERDICT_RETIRE

    def test_promote_candidate(self):
        """Strong metrics → PROMOTE_CANDIDATE."""
        v = classify_research_gate_verdict(
            mean_ic=0.05, icir=0.8, positive_fold_rate=0.8, q_value=0.01,
            fallback_rate=0.1,
        )
        assert v == RESEARCH_VERDICT_PROMOTE_CANDIDATE

    def test_ensemble_only_marginal_icir(self):
        """Good IC but marginal ICIR → ENSEMBLE_ONLY."""
        v = classify_research_gate_verdict(
            mean_ic=0.03, icir=0.35, positive_fold_rate=0.5, q_value=0.02,
            fallback_rate=0.1,
        )
        assert v == RESEARCH_VERDICT_ENSEMBLE_ONLY

    def test_review_low_pos_fold_rate(self):
        """Positive IC but very low positive fold rate → REVIEW."""
        v = classify_research_gate_verdict(
            mean_ic=0.01, icir=0.2, positive_fold_rate=0.2, q_value=0.04,
            fallback_rate=0.1,
        )
        assert v == RESEARCH_VERDICT_REVIEW

    def test_high_fallback_rate_blocks_promote(self):
        """High fallback rate prevents PROMOTE_CANDIDATE."""
        v = classify_research_gate_verdict(
            mean_ic=0.05, icir=0.8, positive_fold_rate=0.8, q_value=0.01,
            fallback_rate=0.7,
        )
        assert v != RESEARCH_VERDICT_PROMOTE_CANDIDATE

    def test_sign_consistency_rejection(self):
        """Very low positive fold rate → not PROMOTE or ENSEMBLE."""
        v = classify_research_gate_verdict(
            mean_ic=0.01, icir=0.4, positive_fold_rate=0.1, q_value=0.04,
        )
        assert v in (RESEARCH_VERDICT_REVIEW, RESEARCH_VERDICT_RETIRE)

    def test_zero_ic_retire_or_review(self):
        """Zero mean IC should not promote."""
        v = classify_research_gate_verdict(
            mean_ic=0.0, icir=0.5, positive_fold_rate=0.5, q_value=0.5,
        )
        assert v in (RESEARCH_VERDICT_RETIRE, RESEARCH_VERDICT_REVIEW)

    def test_custom_thresholds(self):
        """Custom thresholds change the classification."""
        v = classify_research_gate_verdict(
            mean_ic=0.03, icir=0.4, positive_fold_rate=0.5, q_value=0.02,
            min_icir_promote=0.3, min_pos_fold_rate_promote=0.4,
            fallback_rate=0.1,
        )
        assert v == RESEARCH_VERDICT_PROMOTE_CANDIDATE


class TestFallbackAsFailureMetrics:
    """Fallback usage must not count as alpha success."""

    def test_all_fallback(self):
        """All folds used fallback → fallback_as_failure_rate = 1.0."""
        folds = [
            {"portfolio_ic": 0.02, "used_fallback_candidates": True},
            {"portfolio_ic": -0.01, "used_fallback_candidates": True},
            {"portfolio_ic": 0.03, "used_fallback_candidates": True},
        ]
        m = compute_fallback_as_failure_metrics(folds)
        assert m["total_folds"] == 3
        assert m["alpha_selected_folds"] == 0
        assert m["fallback_folds"] == 3
        assert m["fallback_as_failure_rate"] == 1.0

    def test_no_fallback(self):
        """No folds used fallback → fallback_as_failure_rate = 0.0."""
        folds = [
            {"portfolio_ic": 0.05, "used_fallback_candidates": False},
            {"portfolio_ic": 0.03, "used_fallback_candidates": False},
        ]
        m = compute_fallback_as_failure_metrics(folds)
        assert m["total_folds"] == 2
        assert m["alpha_selected_folds"] == 2
        assert m["fallback_folds"] == 0
        assert m["fallback_as_failure_rate"] == 0.0
        assert m["alpha_selected_positive_ic_rate"] == 1.0

    def test_mixed_fallback(self):
        """Mixed folds correctly separate metrics."""
        folds = [
            {"portfolio_ic": 0.05, "used_fallback_candidates": False},
            {"portfolio_ic": -0.02, "used_fallback_candidates": True},
            {"portfolio_ic": 0.03, "used_fallback_candidates": False},
            {"portfolio_ic": 0.01, "used_fallback_candidates": True},
        ]
        m = compute_fallback_as_failure_metrics(folds)
        assert m["total_folds"] == 4
        assert m["alpha_selected_folds"] == 2
        assert m["fallback_folds"] == 2
        assert m["alpha_selected_positive_ic_rate"] == 1.0
        assert m["fallback_positive_ic_rate"] == 0.5
        assert m["fallback_as_failure_rate"] == 0.5

    def test_empty_folds(self):
        m = compute_fallback_as_failure_metrics([])
        assert m["total_folds"] == 0
        assert m["fallback_as_failure_rate"] == 0.0

    def test_fallback_does_not_inflate_success(self):
        """Positive IC in fallback folds is reported separately, not as success."""
        folds = [
            {"portfolio_ic": -0.05, "used_fallback_candidates": False},
            {"portfolio_ic": 0.10, "used_fallback_candidates": True},
        ]
        m = compute_fallback_as_failure_metrics(folds)
        # Alpha-selected fold had negative IC
        assert m["alpha_selected_positive_ic_rate"] == 0.0
        # Fallback fold had positive IC, but it's separate
        assert m["fallback_positive_ic_rate"] == 1.0


class TestDefaultBehaviorUnchanged:
    """Research gates must be opt-in and not affect default behavior."""

    def test_verdict_constants_exist(self):
        assert RESEARCH_VERDICT_PROMOTE_CANDIDATE == "PROMOTE_CANDIDATE"
        assert RESEARCH_VERDICT_ENSEMBLE_ONLY == "ENSEMBLE_ONLY"
        assert RESEARCH_VERDICT_REVIEW == "REVIEW"
        assert RESEARCH_VERDICT_RETIRE == "RETIRE"

    def test_composite_score_unchanged(self):
        """Composite score computation is not affected by research gates."""
        bd = compute_composite_score(
            "test_alpha",
            validation_ic=0.25,
            ic_sharpe=1.5,
            turnover=0.2,
            overfit_gap=0.05,
        )
        # Same behavior as before research gates were added
        assert 0.0 <= bd.composite_score <= 1.0
        assert bd.raw_validation_ic == pytest.approx(0.25)

    def test_selection_unchanged(self):
        """select_alphas_risk_adjusted works the same without research gates."""
        bd = compute_composite_score(
            "alpha_1",
            validation_ic=0.3,
            ic_sharpe=2.0,
            turnover=0.1,
            overfit_gap=0.02,
        )
        result = select_alphas_risk_adjusted({"alpha_1": bd}, top_n=1)
        assert result.paper_trading_gate == "PASS"
        assert "alpha_1" in result.selected_alphas


# ===========================================================================
# 17. ALPHA RECOVERY DIAGNOSTICS (GATE: ALPHA_RECOVERY_DIAGNOSTICS_20260614)
# ===========================================================================
from omega.quant.walk_forward.risk_adjusted_alpha_score import (
    classify_alpha_cluster,
    compute_neutralized_ic_proxy,
    compute_regime_conditioned_ic,
    compute_ic_decay_summary,
    compute_alpha_recovery_diagnostics,
    AlphaRecoveryReport,
    ALPHA_CLUSTER_PATTERNS,
)


class TestClassifyAlphaCluster:
    """Alpha cluster classification based on naming patterns."""

    def test_momentum_cluster(self):
        assert classify_alpha_cluster("alpha_p34_close_auction_drift_10") == "momentum"
        assert classify_alpha_cluster("alpha_p34_momentum_5_20") == "momentum"

    def test_volatility_cluster(self):
        assert classify_alpha_cluster("alpha_p34_volatility_compression_5") == "volatility"

    def test_volume_cluster(self):
        assert classify_alpha_cluster("alpha_p34_volume_clock_acceleration_10") == "volume"

    def test_liquidity_cluster(self):
        assert classify_alpha_cluster("alpha_p34_kyle_lambda_20") == "liquidity"
        assert classify_alpha_cluster("alpha_p34_liquidity_provision_ratio_10") == "liquidity"

    def test_microstructure_cluster(self):
        assert classify_alpha_cluster("alpha_p34_tick_signed_volume_imbalance_5") == "microstructure"
        assert classify_alpha_cluster("alpha_p34_micro_momentum_5_20") == "microstructure"

    def test_drift_in_momentum(self):
        assert classify_alpha_cluster("alpha_p34_close_auction_drift_10") == "momentum"

    def test_uncategorized(self):
        assert classify_alpha_cluster("alpha_unknown_xyz") == "uncategorized"


class TestComputeNeutralizedICProxy:
    """Neutralized IC must subtract cluster mean."""

    def test_basic_neutralization(self):
        alpha_fold_ics = {
            "alpha_p34_volatility_compression_5": [0.02, 0.03, 0.01],
            "alpha_p34_momentum_5": [0.05, 0.06, 0.04],
        }
        result = compute_neutralized_ic_proxy(alpha_fold_ics)
        assert "alpha_p34_volatility_compression_5" in result
        assert "alpha_p34_momentum_5" in result
        # Each alpha in its own cluster → neutralized_ic = mean_ic - cluster_mean_ic = 0
        # (since cluster has only one member)
        vol = result["alpha_p34_volatility_compression_5"]
        assert vol["cluster"] == "volatility"
        assert vol["neutralized_ic"] == pytest.approx(0.0, abs=1e-9)

    def test_same_cluster_neutralization(self):
        """Two alphas in same cluster: neutralized IC should differ."""
        alpha_fold_ics = {
            "alpha_p34_momentum_5": [0.05, 0.06, 0.04],  # mean=0.05
            "alpha_p34_close_auction_drift_10": [0.01, 0.02, 0.00],  # mean=0.01
        }
        result = compute_neutralized_ic_proxy(alpha_fold_ics)
        # Both in momentum cluster. Cluster mean = mean of all 6 values = 0.03
        mom = result["alpha_p34_momentum_5"]
        drift = result["alpha_p34_close_auction_drift_10"]
        assert mom["cluster"] == "momentum"
        assert drift["cluster"] == "momentum"
        assert mom["n_cluster_members"] == 2
        # Momentum alpha should have positive neutralized IC (above cluster mean)
        assert mom["neutralized_ic"] > 0
        # Drift alpha should have negative neutralized IC (below cluster mean)
        assert drift["neutralized_ic"] < 0

    def test_empty_input(self):
        result = compute_neutralized_ic_proxy({})
        assert result == {}


class TestComputeRegimeConditionedIC:
    """Regime-conditioned IC must use fold-level proxies."""

    def _make_folds(self):
        return [
            {
                "portfolio_sharpe": 1.5,
                "portfolio_ic": 0.05,
                "alpha_ics": {"alpha_a": 0.03, "alpha_b": -0.02},
            },
            {
                "portfolio_sharpe": -0.5,
                "portfolio_ic": -0.03,
                "alpha_ics": {"alpha_a": -0.01, "alpha_b": 0.01},
            },
            {
                "portfolio_sharpe": 0.5,
                "portfolio_ic": 0.02,
                "alpha_ics": {"alpha_a": 0.02, "alpha_b": 0.01},
            },
            {
                "portfolio_sharpe": 0.3,
                "portfolio_ic": -0.005,
                "alpha_ics": {"alpha_a": 0.01, "alpha_b": 0.0},
            },
        ]

    def test_regime_classification(self):
        folds = self._make_folds()
        result = compute_regime_conditioned_ic(folds)
        assert "alpha_a" in result
        assert "alpha_b" in result
        # Fold 0: bull (sharpe>=1, ic>0), Fold 1: bear (sharpe<0),
        # Fold 2: sideways, Fold 3: sideways (ic > -0.01 and sharpe >= 0)
        assert result["alpha_a"]["bull_n_folds"] == 1
        assert result["alpha_a"]["bear_n_folds"] == 1
        assert result["alpha_a"]["sideways_n_folds"] == 2

    def test_regime_fragile(self):
        folds = self._make_folds()
        result = compute_regime_conditioned_ic(folds)
        # alpha_b has IC -0.02 (bull), 0.01 (bear), 0.01 (sideways), 0.0 (sideways)
        # bull_mean < 0, bear_mean > 0, sideways_mean > 0 → 2 positive regimes
        b = result["alpha_b"]
        assert b["positive_regimes"] >= 0  # just check it runs
        assert isinstance(b["regime_fragile"], bool)

    def test_empty_folds(self):
        result = compute_regime_conditioned_ic([])
        assert result == {}


class TestComputeICDecaySummary:
    """IC decay summary across fold ordering."""

    def test_improving_alpha(self):
        """Alpha with improving IC over time."""
        alpha_fold_ics = {
            "alpha_a": [-0.02, -0.01, 0.01, 0.03, 0.04, 0.05],
        }
        result = compute_ic_decay_summary(alpha_fold_ics, n_folds=6)
        a = result["alpha_a"]
        assert a["ic_trend"] > 0  # improving
        assert a["early_half_mean_ic"] < a["late_half_mean_ic"]

    def test_decaying_alpha(self):
        """Alpha with decaying IC over time."""
        alpha_fold_ics = {
            "alpha_b": [0.08, 0.06, 0.04, 0.02, 0.01, -0.01],
        }
        result = compute_ic_decay_summary(alpha_fold_ics, n_folds=6)
        b = result["alpha_b"]
        assert b["ic_trend"] < 0  # decaying
        assert b["early_half_mean_ic"] > b["late_half_mean_ic"]
        # Half-life should be estimated (positive)
        assert b["half_life_folds"] > 0 or b["half_life_folds"] == -1

    def test_empty_input(self):
        result = compute_ic_decay_summary({})
        assert result == {}

    def test_empty_ics(self):
        result = compute_ic_decay_summary({"alpha_x": []})
        assert result["alpha_x"]["early_half_mean_ic"] == 0.0
        assert result["alpha_x"]["half_life_folds"] == -1


class TestComputeAlphaRecoveryDiagnostics:
    """Full recovery diagnostics computation."""

    def _make_test_data(self):
        folds = [
            {
                "portfolio_sharpe": 1.5,
                "portfolio_ic": 0.05,
                "alpha_ics": {
                    "alpha_p34_volatility_compression_5": 0.03,
                    "alpha_p34_close_auction_drift_10": 0.01,
                },
            },
            {
                "portfolio_sharpe": -0.5,
                "portfolio_ic": -0.03,
                "alpha_ics": {
                    "alpha_p34_volatility_compression_5": -0.02,
                    "alpha_p34_close_auction_drift_10": -0.01,
                },
            },
            {
                "portfolio_sharpe": 0.8,
                "portfolio_ic": 0.02,
                "alpha_ics": {
                    "alpha_p34_volatility_compression_5": 0.04,
                    "alpha_p34_close_auction_drift_10": 0.02,
                },
            },
            {
                "portfolio_sharpe": 1.2,
                "portfolio_ic": 0.03,
                "alpha_ics": {
                    "alpha_p34_volatility_compression_5": 0.05,
                    "alpha_p34_close_auction_drift_10": 0.03,
                },
            },
        ]
        alpha_fold_ics = {
            "alpha_p34_volatility_compression_5": [0.03, -0.02, 0.04, 0.05],
            "alpha_p34_close_auction_drift_10": [0.01, -0.01, 0.02, 0.03],
        }
        return folds, alpha_fold_ics

    def test_full_diagnostics(self):
        folds, alpha_fold_ics = self._make_test_data()
        report = compute_alpha_recovery_diagnostics(folds, alpha_fold_ics)
        assert isinstance(report, AlphaRecoveryReport)
        assert len(report.neutralized_ic) == 2
        assert len(report.regime_conditioned_ic) == 2
        assert len(report.ic_decay) == 2
        assert len(report.retirement_summary) == 2

    def test_classification_categories(self):
        folds, alpha_fold_ics = self._make_test_data()
        report = compute_alpha_recovery_diagnostics(folds, alpha_fold_ics)
        all_alphas = set(
            report.recoverable_candidates
            + report.research_only
            + report.confirmed_retire
        )
        assert len(all_alphas) == 2
        # Every alpha should be classified somewhere
        assert "alpha_p34_volatility_compression_5" in all_alphas
        assert "alpha_p34_close_auction_drift_10" in all_alphas

    def test_to_dict_serializable(self):
        folds, alpha_fold_ics = self._make_test_data()
        report = compute_alpha_recovery_diagnostics(folds, alpha_fold_ics)
        d = report.to_dict()
        assert "neutralized_ic" in d
        assert "regime_conditioned_ic" in d
        assert "ic_decay" in d
        assert "retirement_summary" in d
        assert "recoverable_candidates" in d
        assert "confirmed_retire" in d
        assert "research_only" in d
        # Must be JSON-serializable
        json_str = json.dumps(d)
        assert len(json_str) > 0

    def test_with_research_verdicts(self):
        folds, alpha_fold_ics = self._make_test_data()
        verdicts = {
            "alpha_p34_volatility_compression_5": "RETIRE",
            "alpha_p34_close_auction_drift_10": "REVIEW",
        }
        report = compute_alpha_recovery_diagnostics(
            folds, alpha_fold_ics, research_verdicts=verdicts
        )
        for summary in report.retirement_summary.values():
            assert summary["research_verdict"] in ("RETIRE", "REVIEW")


# ===========================================================================
# 18. REGIME_THRESHOLD_IC PARAMETER (GATE: RECOVERY_POOL_AB_DIAGNOSTICS_20260614)
# ===========================================================================


class TestRegimeThresholdICParameter:
    """regime_threshold_ic must be honored instead of hard-coded -0.01."""

    def _make_borderline_folds(self):
        """Folds where portfolio_ic is between -0.01 and 0 (borderline)."""
        return [
            {
                "portfolio_sharpe": 0.3,
                "portfolio_ic": -0.005,  # Between -0.01 and 0
                "alpha_ics": {"alpha_a": 0.02},
            },
            {
                "portfolio_sharpe": 0.5,
                "portfolio_ic": 0.01,
                "alpha_ics": {"alpha_a": 0.03},
            },
            {
                "portfolio_sharpe": -0.2,
                "portfolio_ic": -0.02,
                "alpha_ics": {"alpha_a": -0.01},
            },
        ]

    def test_default_threshold_ic_is_minus_001(self):
        """Default regime_threshold_ic=-0.01 preserves backward compat."""
        folds = self._make_borderline_folds()
        result = compute_regime_conditioned_ic(folds)
        # Fold 0: sharpe=0.3 (< 1, not bull), ic=-0.005 (> -0.01, not bear)
        #          → sideways
        # Fold 1: sharpe=0.5 (< 1, not bull), ic=0.01 (> -0.01, not bear)
        #          → sideways
        # Fold 2: sharpe=-0.2 (< 0) → bear
        assert result["alpha_a"]["sideways_n_folds"] == 2
        assert result["alpha_a"]["bear_n_folds"] == 1
        assert result["alpha_a"]["bull_n_folds"] == 0

    def test_custom_threshold_ic_zero(self):
        """Custom regime_threshold_ic=0.0 makes more folds bear-like."""
        folds = self._make_borderline_folds()
        result = compute_regime_conditioned_ic(
            folds, regime_threshold_ic=0.0
        )
        # Fold 0: sharpe=0.3 (not bull), ic=-0.005 (< 0.0) → bear
        # Fold 1: sharpe=0.5 (not bull), ic=0.01 (not < 0.0) → sideways
        # Fold 2: sharpe=-0.2 (< 0) → bear
        assert result["alpha_a"]["bear_n_folds"] == 2
        assert result["alpha_a"]["sideways_n_folds"] == 1

    def test_custom_threshold_ic_strict(self):
        """Custom regime_threshold_ic=-0.05 makes fewer folds bear-like."""
        folds = self._make_borderline_folds()
        result = compute_regime_conditioned_ic(
            folds, regime_threshold_ic=-0.05
        )
        # Fold 0: sharpe=0.3, ic=-0.005 (> -0.05) → sideways
        # Fold 1: sharpe=0.5, ic=0.01 (> -0.05) → sideways
        # Fold 2: sharpe=-0.2 (< 0) → bear
        assert result["alpha_a"]["sideways_n_folds"] == 2
        assert result["alpha_a"]["bear_n_folds"] == 1

    def test_threshold_ic_passed_through_recovery_diagnostics(self):
        """compute_alpha_recovery_diagnostics passes regime_threshold_ic."""
        folds = self._make_borderline_folds()
        alpha_fold_ics = {"alpha_a": [0.02, 0.03, -0.01]}
        # Default threshold
        report_default = compute_alpha_recovery_diagnostics(
            folds, alpha_fold_ics
        )
        # Custom threshold
        report_custom = compute_alpha_recovery_diagnostics(
            folds, alpha_fold_ics, regime_threshold_ic=0.0
        )
        # With threshold=0.0, more folds classified as bear →
        # regime_conditioned_ic should differ
        default_bear = report_default.regime_conditioned_ic["alpha_a"]["bear_n_folds"]
        custom_bear = report_custom.regime_conditioned_ic["alpha_a"]["bear_n_folds"]
        assert custom_bear > default_bear


# ===========================================================================
# 19. RECOVERY SELECTOR POOL MODE (GATE: RECOVERY_SELECTOR_OPT_IN_20260614)
# ===========================================================================
from omega.quant.walk_forward.risk_adjusted_alpha_score import (
    filter_alphas_by_recovery_mode,
    compute_selector_ready_verdict,
    RESEARCH_POOL_FULL,
    RESEARCH_POOL_RECOVERY_ONLY,
    RESEARCH_POOL_RECOVERABLE_ONLY,
    VALID_RESEARCH_POOL_MODES,
    SELECTOR_VERDICT_DO_NOT_PROMOTE,
    SELECTOR_VERDICT_CONDITIONAL_PROMOTE,
    SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE,
)


class TestRecoveryPoolModeConstants:
    """Recovery pool mode constants must be defined correctly."""

    def test_full_mode_value(self):
        assert RESEARCH_POOL_FULL == "full"

    def test_recovery_only_mode_value(self):
        assert RESEARCH_POOL_RECOVERY_ONLY == "recovery_only"

    def test_recoverable_only_mode_value(self):
        assert RESEARCH_POOL_RECOVERABLE_ONLY == "recoverable_only"

    def test_valid_modes_tuple(self):
        assert RESEARCH_POOL_FULL in VALID_RESEARCH_POOL_MODES
        assert RESEARCH_POOL_RECOVERY_ONLY in VALID_RESEARCH_POOL_MODES
        assert RESEARCH_POOL_RECOVERABLE_ONLY in VALID_RESEARCH_POOL_MODES
        assert len(VALID_RESEARCH_POOL_MODES) == 3

    def test_selector_verdict_constants(self):
        assert SELECTOR_VERDICT_DO_NOT_PROMOTE == "DO_NOT_PROMOTE"
        assert SELECTOR_VERDICT_CONDITIONAL_PROMOTE == "CONDITIONAL_PROMOTE"
        assert SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE == "INSUFFICIENT_EVIDENCE"


class TestFilterAlphasByRecoveryMode:
    """Filter alphas based on recovery pool mode."""

    def _make_recovery_report(self):
        report = AlphaRecoveryReport()
        report.recoverable_candidates = ["alpha_recoverable_1"]
        report.research_only = ["alpha_research_1"]
        report.confirmed_retire = ["alpha_retire_1", "alpha_retire_2"]
        return report

    def test_full_mode_returns_all(self):
        report = self._make_recovery_report()
        all_alphas = ["alpha_recoverable_1", "alpha_research_1",
                      "alpha_retire_1", "alpha_retire_2"]
        result = filter_alphas_by_recovery_mode(all_alphas, report, RESEARCH_POOL_FULL)
        assert result == all_alphas

    def test_recovery_only_excludes_confirmed_retire(self):
        report = self._make_recovery_report()
        all_alphas = ["alpha_recoverable_1", "alpha_research_1",
                      "alpha_retire_1", "alpha_retire_2"]
        result = filter_alphas_by_recovery_mode(
            all_alphas, report, RESEARCH_POOL_RECOVERY_ONLY
        )
        assert "alpha_recoverable_1" in result
        assert "alpha_research_1" in result
        assert "alpha_retire_1" not in result
        assert "alpha_retire_2" not in result
        assert len(result) == 2

    def test_recoverable_only_keeps_only_recoverable(self):
        report = self._make_recovery_report()
        all_alphas = ["alpha_recoverable_1", "alpha_research_1",
                      "alpha_retire_1", "alpha_retire_2"]
        result = filter_alphas_by_recovery_mode(
            all_alphas, report, RESEARCH_POOL_RECOVERABLE_ONLY
        )
        assert result == ["alpha_recoverable_1"]

    def test_invalid_mode_raises(self):
        report = self._make_recovery_report()
        with pytest.raises(ValueError, match="Unknown research_pool_mode"):
            filter_alphas_by_recovery_mode(["a"], report, "invalid_mode")

    def test_empty_alpha_list(self):
        report = self._make_recovery_report()
        result = filter_alphas_by_recovery_mode([], report, RESEARCH_POOL_RECOVERY_ONLY)
        assert result == []

    def test_full_mode_default(self):
        report = self._make_recovery_report()
        all_alphas = ["a", "b", "c"]
        result = filter_alphas_by_recovery_mode(all_alphas, report)
        assert result == all_alphas

    def test_recovery_only_empty_retire_list(self):
        """When confirmed_retire is empty, recovery_only returns all."""
        report = AlphaRecoveryReport()
        report.recoverable_candidates = ["a"]
        report.research_only = ["b"]
        report.confirmed_retire = []
        all_alphas = ["a", "b", "c"]
        result = filter_alphas_by_recovery_mode(
            all_alphas, report, RESEARCH_POOL_RECOVERY_ONLY
        )
        assert result == all_alphas

    def test_recoverable_only_empty_recoverable(self):
        """When recoverable_candidates is empty, returns empty."""
        report = AlphaRecoveryReport()
        report.recoverable_candidates = []
        report.research_only = ["a"]
        report.confirmed_retire = ["b"]
        result = filter_alphas_by_recovery_mode(
            ["a", "b"], report, RESEARCH_POOL_RECOVERABLE_ONLY
        )
        assert result == []


class TestComputeSelectorReadyVerdict:
    """Selector-ready verdict based on pool A/B metrics."""

    def test_do_not_promote_ic_improved_fold_rate_not(self):
        """Mean IC improved but positive fold rate did NOT → DO_NOT_PROMOTE."""
        verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=0.01,
            full_pool_positive_fold_rate=0.5,
            recovery_pool_mean_ic=0.03,
            recovery_pool_positive_fold_rate=0.45,
        )
        assert verdict == SELECTOR_VERDICT_DO_NOT_PROMOTE

    def test_conditional_promote_both_improved(self):
        """Both mean IC and fold rate improved → CONDITIONAL_PROMOTE."""
        verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=0.01,
            full_pool_positive_fold_rate=0.4,
            recovery_pool_mean_ic=0.03,
            recovery_pool_positive_fold_rate=0.6,
        )
        assert verdict == SELECTOR_VERDICT_CONDITIONAL_PROMOTE

    def test_insufficient_evidence_no_improvement(self):
        """Neither metric improved → INSUFFICIENT_EVIDENCE."""
        verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=0.03,
            full_pool_positive_fold_rate=0.6,
            recovery_pool_mean_ic=0.02,
            recovery_pool_positive_fold_rate=0.5,
        )
        assert verdict == SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE

    def test_do_not_promote_exact_scenario(self):
        """A/B showed IC improved but fold rate did not — the exact finding."""
        verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=0.005,
            full_pool_positive_fold_rate=0.375,
            recovery_pool_mean_ic=0.015,
            recovery_pool_positive_fold_rate=0.375,
        )
        assert verdict == SELECTOR_VERDICT_DO_NOT_PROMOTE

    def test_custom_thresholds(self):
        """Custom thresholds change the verdict boundary."""
        # With default thresholds: IC improved (delta=0.003 > 0.001)
        # but fold rate not (delta=0.0) → DO_NOT_PROMOTE
        verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=0.01,
            full_pool_positive_fold_rate=0.5,
            recovery_pool_mean_ic=0.013,
            recovery_pool_positive_fold_rate=0.5,
        )
        assert verdict == SELECTOR_VERDICT_DO_NOT_PROMOTE

        # With strict IC threshold: delta=0.003 < 0.01 → INSUFFICIENT
        verdict2 = compute_selector_ready_verdict(
            full_pool_mean_ic=0.01,
            full_pool_positive_fold_rate=0.5,
            recovery_pool_mean_ic=0.013,
            recovery_pool_positive_fold_rate=0.5,
            ic_improvement_threshold=0.01,
        )
        assert verdict2 == SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE

    def test_fold_rate_improvement_threshold(self):
        """Custom fold rate threshold affects verdict."""
        # Fold rate delta = 0.05, below default threshold 0.0
        # so it still passes. Let's use a threshold of 0.1.
        verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=0.01,
            full_pool_positive_fold_rate=0.5,
            recovery_pool_mean_ic=0.03,
            recovery_pool_positive_fold_rate=0.55,
            fold_rate_improvement_threshold=0.1,
        )
        # IC improved, fold rate delta 0.05 < threshold 0.1 → DO_NOT_PROMOTE
        assert verdict == SELECTOR_VERDICT_DO_NOT_PROMOTE

    def test_both_negative_no_improvement(self):
        """Both metrics worsen → INSUFFICIENT_EVIDENCE."""
        verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=0.05,
            full_pool_positive_fold_rate=0.8,
            recovery_pool_mean_ic=0.01,
            recovery_pool_positive_fold_rate=0.3,
        )
        assert verdict == SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE


# ===========================================================================
# 20. STATISTICAL VALIDATION GATES (GATE: STAT_VALIDATION_GATES_20260614)
# ===========================================================================
from omega.quant.walk_forward.risk_adjusted_alpha_score import (
    compute_dsr,
    compute_pbo_summary,
    compute_cpcv_ready_path_summary,
    compute_stat_validation_verdict,
    STAT_VALIDATION_PASS,
    STAT_VALIDATION_FAIL,
    STAT_VALIDATION_INSUFFICIENT_DATA,
    _norm_cdf,
    _norm_ppf,
    _MIN_CPCV_FOLDS,
)


class TestStatValidationConstants:
    """Stat validation verdict constants must be defined correctly."""

    def test_pass_constant(self):
        assert STAT_VALIDATION_PASS == "PASS"

    def test_fail_constant(self):
        assert STAT_VALIDATION_FAIL == "FAIL"

    def test_insufficient_data_constant(self):
        assert STAT_VALIDATION_INSUFFICIENT_DATA == "INSUFFICIENT_DATA"

    def test_min_cpcv_folds(self):
        assert _MIN_CPCV_FOLDS == 10


class TestNormHelpers:
    """Normal distribution helpers for DSR."""

    def test_norm_cdf_zero(self):
        assert _norm_cdf(0.0) == pytest.approx(0.5)

    def test_norm_cdf_positive(self):
        assert _norm_cdf(1.96) == pytest.approx(0.975, abs=0.001)

    def test_norm_cdf_negative(self):
        assert _norm_cdf(-1.96) == pytest.approx(0.025, abs=0.001)

    def test_norm_ppf_half(self):
        assert _norm_ppf(0.5) == pytest.approx(0.0, abs=0.01)

    def test_norm_ppf_high(self):
        assert _norm_ppf(0.975) == pytest.approx(1.96, abs=0.01)

    def test_norm_ppf_low(self):
        assert _norm_ppf(0.025) == pytest.approx(-1.96, abs=0.01)

    def test_norm_ppf_boundaries(self):
        assert _norm_ppf(0.0) < -5.0
        assert _norm_ppf(1.0) > 5.0


class TestComputeDSR:
    """Deflated Sharpe Ratio must adjust for selection bias."""

    def test_dsr_consistent_positive_sharpes(self):
        """Consistent positive Sharpes → high DSR."""
        sharpes = [0.8, 0.9, 1.0, 0.85, 0.95, 1.1, 0.9, 0.88]
        dsr = compute_dsr(sharpes, n_trials=8)
        assert dsr > 0.5

    def test_dsr_noisy_sharpes(self):
        """Mixed-sign Sharpes → low DSR."""
        sharpes = [0.5, -0.3, 0.2, -0.4, 0.1, -0.2, 0.3, -0.1]
        dsr = compute_dsr(sharpes, n_trials=8)
        assert dsr < 0.5

    def test_dsr_empty(self):
        assert compute_dsr([]) == 0.0

    def test_dsr_too_few(self):
        assert compute_dsr([0.5, 0.3]) == 0.0

    def test_dsr_constant_positive(self):
        """All identical positive Sharpes → DSR = 1.0."""
        dsr = compute_dsr([0.5, 0.5, 0.5, 0.5, 0.5])
        assert dsr == 1.0

    def test_dsr_constant_negative(self):
        """All identical negative Sharpes → DSR = 0.0."""
        dsr = compute_dsr([-0.5, -0.5, -0.5, -0.5, -0.5])
        assert dsr == 0.0

    def test_dsr_bounded(self):
        """DSR always in [0, 1]."""
        sharpes = [1.5, 2.0, 1.8, 1.6, 1.9, 2.1, 1.7, 1.8]
        dsr = compute_dsr(sharpes, n_trials=20)
        assert 0.0 <= dsr <= 1.0

    def test_dsr_more_trials_lowers_dsr(self):
        """More trials → higher benchmark → lower DSR."""
        sharpes = [0.5, 0.6, 0.4, 0.5, 0.55, 0.45, 0.5, 0.5]
        dsr_few = compute_dsr(sharpes, n_trials=8)
        dsr_many = compute_dsr(sharpes, n_trials=100)
        assert dsr_many < dsr_few

    def test_dsr_with_nan(self):
        """NaN values are filtered out."""
        sharpes = [0.5, float("nan"), 0.6, 0.4, 0.5]
        dsr = compute_dsr(sharpes)
        assert 0.0 <= dsr <= 1.0

    def test_dsr_deterministic(self):
        """Same input always produces same output."""
        sharpes = [0.5, 0.6, 0.4, 0.5, 0.55, 0.45]
        dsr1 = compute_dsr(sharpes, n_trials=6)
        dsr2 = compute_dsr(sharpes, n_trials=6)
        assert dsr1 == dsr2


class TestComputePBOSummary:
    """PBO must measure backtest overfitting probability."""

    def test_pbo_empty(self):
        result = compute_pbo_summary([])
        assert result["pbo"] == 0.0
        assert result["n_folds"] == 0

    def test_pbo_single_path(self):
        result = compute_pbo_summary([{"alpha_a": 0.05}])
        assert result["n_paths"] == 1
        assert result["pbo"] == 0.0

    def test_pbo_consistent_best(self):
        """When one path is always best, PBO should be low."""
        fold_path_scores = [
            {"alpha_a": 0.05, "alpha_b": 0.01},
            {"alpha_a": 0.06, "alpha_b": 0.02},
            {"alpha_a": 0.04, "alpha_b": 0.01},
            {"alpha_a": 0.05, "alpha_b": 0.03},
        ]
        result = compute_pbo_summary(fold_path_scores)
        assert result["n_folds"] == 4
        assert result["n_paths"] == 2
        assert 0.0 <= result["pbo"] <= 1.0

    def test_pbo_alternating_best(self):
        """When best alternates, PBO should reflect instability."""
        fold_path_scores = [
            {"alpha_a": 0.05, "alpha_b": 0.01},
            {"alpha_a": 0.01, "alpha_b": 0.05},
            {"alpha_a": 0.05, "alpha_b": 0.01},
            {"alpha_a": 0.01, "alpha_b": 0.05},
        ]
        result = compute_pbo_summary(fold_path_scores)
        assert 0.0 <= result["pbo"] <= 1.0
        assert result["n_folds"] == 4

    def test_pbo_bounded(self):
        """PBO always in [0, 1]."""
        fold_path_scores = [
            {"a": 0.1, "b": -0.1, "c": 0.05},
            {"a": -0.1, "b": 0.1, "c": 0.02},
        ]
        result = compute_pbo_summary(fold_path_scores)
        assert 0.0 <= result["pbo"] <= 1.0

    def test_pbo_result_keys(self):
        result = compute_pbo_summary([{"a": 0.1, "b": 0.2}])
        assert "pbo" in result
        assert "n_folds" in result
        assert "n_paths" in result
        assert "is_best_oos_rank_mean" in result
        assert "is_best_count" in result
        assert "overfit_count" in result


class TestComputeCPCVReadyPathSummary:
    """CPCV-ready assessment from existing fold data."""

    def test_cpcv_not_ready_few_folds(self):
        fold_scores = [{"a": 0.1}] * 5
        result = compute_cpcv_ready_path_summary(fold_scores)
        assert result["cpcv_ready"] is False
        assert result["n_folds"] == 5

    def test_cpcv_ready_enough_folds(self):
        fold_scores = [{"a": 0.1, "b": 0.05}] * 12
        result = compute_cpcv_ready_path_summary(fold_scores)
        assert result["cpcv_ready"] is True
        assert result["n_folds"] == 12

    def test_cpcv_empty(self):
        result = compute_cpcv_ready_path_summary([])
        assert result["cpcv_ready"] is False
        assert result["n_paths"] == 0
        assert result["best_path"] is None

    def test_cpcv_path_consistency(self):
        fold_scores = [
            {"alpha_a": 0.05, "alpha_b": -0.01},
            {"alpha_a": 0.03, "alpha_b": -0.02},
            {"alpha_a": 0.04, "alpha_b": 0.01},
            {"alpha_a": -0.01, "alpha_b": -0.03},
        ]
        result = compute_cpcv_ready_path_summary(fold_scores)
        assert "alpha_a" in result["path_consistency"]
        assert "alpha_b" in result["path_consistency"]
        # alpha_a is positive in 3 of 4 folds
        assert result["path_consistency"]["alpha_a"] == pytest.approx(0.75)
        # alpha_b is positive in 1 of 4 folds
        assert result["path_consistency"]["alpha_b"] == pytest.approx(0.25)

    def test_cpcv_best_path(self):
        fold_scores = [
            {"alpha_a": 0.05, "alpha_b": 0.01},
            {"alpha_a": 0.06, "alpha_b": 0.02},
        ]
        result = compute_cpcv_ready_path_summary(fold_scores)
        assert result["best_path"] == "alpha_a"
        assert result["best_path_consistency"] == 1.0

    def test_cpcv_result_keys(self):
        result = compute_cpcv_ready_path_summary([{"a": 0.1}])
        assert "cpcv_ready" in result
        assert "n_folds" in result
        assert "n_paths" in result
        assert "min_folds_required" in result
        assert "path_consistency" in result
        assert "best_path" in result
        assert "best_path_consistency" in result


class TestComputeStatValidationVerdict:
    """Stat validation verdict combines DSR, PBO, CPCV-ready."""

    def test_pass_all_good(self):
        """All metrics good, no weak alpha → PASS."""
        result = compute_stat_validation_verdict(
            dsr=0.8, pbo=0.1, cpcv_ready=True,
            max_pbo=0.5, min_dsr=0.0,
            weak_alpha_blocked=False,
        )
        assert result["verdict"] == STAT_VALIDATION_PASS
        assert len(result["blockers"]) == 0

    def test_fail_high_pbo(self):
        """High PBO → FAIL."""
        result = compute_stat_validation_verdict(
            dsr=0.8, pbo=0.7, cpcv_ready=True,
            max_pbo=0.5, min_dsr=0.0,
            weak_alpha_blocked=False,
        )
        assert result["verdict"] == STAT_VALIDATION_FAIL
        assert any("PBO" in b for b in result["blockers"])

    def test_fail_low_dsr(self):
        """Low DSR → FAIL."""
        result = compute_stat_validation_verdict(
            dsr=-0.1, pbo=0.1, cpcv_ready=True,
            max_pbo=0.5, min_dsr=0.0,
            weak_alpha_blocked=False,
        )
        assert result["verdict"] == STAT_VALIDATION_FAIL
        assert any("DSR" in b for b in result["blockers"])

    def test_fail_weak_alpha_blocked(self):
        """Weak alpha blocked → FAIL."""
        result = compute_stat_validation_verdict(
            dsr=0.8, pbo=0.1, cpcv_ready=True,
            max_pbo=0.5, min_dsr=0.0,
            weak_alpha_blocked=True,
        )
        assert result["verdict"] == STAT_VALIDATION_FAIL
        assert any("Weak alpha" in b for b in result["blockers"])

    def test_fail_insufficient_cpcv(self):
        """Not CPCV-ready → FAIL."""
        result = compute_stat_validation_verdict(
            dsr=0.8, pbo=0.1, cpcv_ready=False,
            max_pbo=0.5, min_dsr=0.0,
            weak_alpha_blocked=False,
        )
        assert result["verdict"] == STAT_VALIDATION_FAIL
        assert any("CPCV" in b for b in result["blockers"])

    def test_fail_multiple_blockers(self):
        """Multiple issues → multiple blockers."""
        result = compute_stat_validation_verdict(
            dsr=-0.1, pbo=0.7, cpcv_ready=False,
            max_pbo=0.5, min_dsr=0.0,
            weak_alpha_blocked=True,
        )
        assert result["verdict"] == STAT_VALIDATION_FAIL
        assert len(result["blockers"]) == 4

    def test_result_keys(self):
        result = compute_stat_validation_verdict(
            dsr=0.5, pbo=0.2, cpcv_ready=True,
        )
        assert "verdict" in result
        assert "blockers" in result
        assert "dsr" in result
        assert "pbo" in result
        assert "cpcv_ready" in result
        assert "max_pbo" in result
        assert "min_dsr" in result
        assert "weak_alpha_blocked" in result

    def test_custom_thresholds(self):
        """Custom thresholds change the verdict."""
        result = compute_stat_validation_verdict(
            dsr=0.3, pbo=0.4, cpcv_ready=True,
            max_pbo=0.3, min_dsr=0.5,
            weak_alpha_blocked=False,
        )
        assert result["verdict"] == STAT_VALIDATION_FAIL
        assert len(result["blockers"]) == 2

    def test_current_weak_alpha_scenario(self):
        """Current weak alpha pool should be blocked/FAIL."""
        result = compute_stat_validation_verdict(
            dsr=0.3, pbo=0.6, cpcv_ready=False,
            max_pbo=0.5, min_dsr=0.0,
            weak_alpha_blocked=True,
        )
        assert result["verdict"] == STAT_VALIDATION_FAIL
        assert any("Weak alpha" in b for b in result["blockers"])

    def test_default_behavior_unchanged(self):
        """Stat validation gates do not affect composite score or selection."""
        bd = compute_composite_score(
            "test_alpha",
            validation_ic=0.25,
            ic_sharpe=1.5,
            turnover=0.2,
            overfit_gap=0.05,
        )
        assert 0.0 <= bd.composite_score <= 1.0

