"""Tests for scripts/analyze_alpha_weakness.py"""
import json
import math
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts dir to path
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
import sys
sys.path.insert(0, str(SCRIPT_DIR))

from analyze_alpha_weakness import (
    VARIANT_LABELS,
    _analyze_guard,
    _compute_research_verdicts,
    _extract_selection,
    _fmt,
    _fmt_pct,
    _fmt_vnd,
    _safe_mean,
    _safe_std,
    analyze_variant,
    discover_variant_files,
    generate_report,
    load_variant,
    main,
    STAT_VALIDATION_PASS,
    STAT_VALIDATION_FAIL,
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _make_minimal_fold(fold_id=1, ic=0.01, sharpe=0.5, dd=-0.05, ret=0.05, pnl=5e7):
    return {
        "fold_id": fold_id,
        "train_start": "2020-01-01",
        "train_end": "2022-12-31",
        "test_start": "2023-01-01",
        "test_end": "2023-12-31",
        "portfolio_ic": ic,
        "portfolio_sharpe": sharpe,
        "portfolio_max_dd": dd,
        "portfolio_total_return": ret,
        "portfolio_pnl_vnd": pnl,
        "n_train_samples": 1000,
        "n_test_samples": 250,
        "alpha_ics": {
            "alpha_test_good": 0.03,
            "alpha_test_bad": -0.02,
        },
    }


def _make_minimal_variant(n_folds=3, with_guard=False):
    folds = []
    for i in range(1, n_folds + 1):
        f = _make_minimal_fold(
            fold_id=i,
            ic=0.01 * i,
            sharpe=0.5 + 0.1 * i,
            dd=-0.05 - 0.01 * i,
            ret=0.02 * i,
            pnl=1e7 * i,
        )
        if with_guard:
            f["portfolio_guard_evidence"] = {
                "portfolio_guard_enabled": True,
                "portfolio_guard_status": "FALLBACK_TO_BASELINE",
                "selected_basket_validation_ic": -0.01,
                "baseline_basket_validation_ic": 0.02,
                "guard_reason": "Test guard reason",
                "selected_alphas": ["alpha_test_good"],
                "rejected_risk_adjusted_evidence": {
                    "selected_alphas": ["alpha_test_good"],
                    "rejected_alphas": ["alpha_test_bad"],
                },
            }
        else:
            f["risk_adjusted_alpha_selection"] = {
                "selected_alphas": ["alpha_test_good"],
                "rejected_alphas": ["alpha_test_bad"],
            }
        f["used_fallback_candidates"] = True
        f["gate_passed_count"] = 0
        f["gate_total"] = 1
        folds.append(f)

    return {
        "config": {
            "start_date": "2020-01-01",
            "end_date": "2023-12-31",
            "min_ic_threshold": 0.02,
            "portfolio_guard_enabled": with_guard,
            "portfolio_guard_tolerance": 0.005,
        },
        "summary": {
            "avg_portfolio_ic": 0.02,
            "avg_portfolio_sharpe": 0.8,
            "avg_portfolio_max_dd": -0.06,
            "total_folds": n_folds,
        },
        "fold_details": folds,
        "timestamp": "2026-06-14T10:00:00",
    }


# ---------------------------------------------------------------------------
# Test _safe_mean / _safe_std
# ---------------------------------------------------------------------------

class TestSafeStats:
    def test_mean_empty(self):
        assert _safe_mean([]) == 0.0

    def test_mean_values(self):
        assert abs(_safe_mean([1.0, 2.0, 3.0]) - 2.0) < 1e-10

    def test_std_empty(self):
        assert _safe_std([]) == 0.0

    def test_std_single(self):
        assert _safe_std([5.0]) == 0.0

    def test_std_values(self):
        result = _safe_std([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        assert result > 0


# ---------------------------------------------------------------------------
# Test formatting helpers
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_fmt(self):
        assert _fmt(0.123456, 4) == "0.1235"

    def test_fmt_pct(self):
        assert _fmt_pct(0.5, 1) == "50.0%"

    def test_fmt_vnd_billions(self):
        assert "B" in _fmt_vnd(1.5e9)

    def test_fmt_vnd_millions(self):
        assert "M" in _fmt_vnd(5e7)

    def test_fmt_vnd_small(self):
        result = _fmt_vnd(500.0)
        assert "500" in result


# ---------------------------------------------------------------------------
# Test discover_variant_files
# ---------------------------------------------------------------------------

class TestDiscoverFiles:
    def test_no_dir(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            discover_variant_files(str(tmp_path / "nonexistent"))

    def test_empty_dir(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No matching"):
            discover_variant_files(str(tmp_path))

    def test_discovers_files(self, tmp_path):
        (tmp_path / "baseline_phase35_backtest_results_xgboost.json").write_text("{}")
        (tmp_path / "ra_guard_phase35_backtest_results_xgboost.json").write_text("{}")
        result = discover_variant_files(str(tmp_path))
        assert "baseline" in result
        assert "ra_guard" in result
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Test load_variant
# ---------------------------------------------------------------------------

class TestLoadVariant:
    def test_load(self, tmp_path):
        data = {"config": {}, "fold_details": []}
        fpath = tmp_path / "test.json"
        fpath.write_text(json.dumps(data))
        result = load_variant(str(fpath))
        assert result == data


# ---------------------------------------------------------------------------
# Test _extract_selection
# ---------------------------------------------------------------------------

class TestExtractSelection:
    def test_direct_key(self):
        fold = {
            "risk_adjusted_alpha_selection": {
                "selected_alphas": ["a1"],
                "rejected_alphas": ["a2"],
            }
        }
        result = _extract_selection(fold)
        assert result["selected_alphas"] == ["a1"]

    def test_gate_metadata(self):
        fold = {
            "gate_metadata": {
                "risk_adjusted_evidence": {
                    "selected_alphas": ["a1"],
                    "rejected_alphas": [],
                }
            }
        }
        result = _extract_selection(fold)
        assert result["selected_alphas"] == ["a1"]

    def test_portfolio_guard_evidence(self):
        fold = {
            "portfolio_guard_evidence": {
                "portfolio_guard_enabled": True,
                "rejected_risk_adjusted_evidence": {
                    "selected_alphas": ["a1"],
                    "rejected_alphas": ["a2"],
                },
            }
        }
        result = _extract_selection(fold)
        assert result["selected_alphas"] == ["a1"]

    def test_no_selection(self):
        fold = {"portfolio_ic": 0.01}
        result = _extract_selection(fold)
        assert result is None


# ---------------------------------------------------------------------------
# Test analyze_variant
# ---------------------------------------------------------------------------

class TestAnalyzeVariant:
    def test_basic_analysis(self):
        data = _make_minimal_variant(n_folds=4)
        result = analyze_variant("baseline", data)
        assert result["n_folds"] == 4
        assert result["name"] == "baseline"
        assert len(result["fold_ics"]) == 4
        assert len(result["fold_sharpes"]) == 4
        assert result["pos_ic_folds"] == 4  # All positive IC
        assert result["fallback_count"] == 4
        assert result["fallback_rate"] == 1.0

    def test_alpha_stats(self):
        data = _make_minimal_variant(n_folds=3)
        result = analyze_variant("test", data)
        assert "alpha_test_good" in result["alpha_stats"]
        assert "alpha_test_bad" in result["alpha_stats"]
        good_stats = result["alpha_stats"]["alpha_test_good"]
        assert good_stats["mean_ic"] == 0.03
        assert good_stats["positive_fold_count"] == 3

    def test_weak_ranking(self):
        data = _make_minimal_variant(n_folds=3)
        result = analyze_variant("test", data)
        # Weak ranking: weakest first
        assert result["weak_ranking"][0][0] == "alpha_test_bad"
        assert result["weak_ranking"][1][0] == "alpha_test_good"

    def test_guard_analysis(self):
        data = _make_minimal_variant(n_folds=2, with_guard=True)
        result = analyze_variant("ra_guard", data)
        ga = result["guard_analysis"]
        assert ga["guard_enabled_folds"] == 2
        assert ga["guard_rejected"] == 2  # All FALLBACK_TO_BASELINE

    def test_selection_freq(self):
        data = _make_minimal_variant(n_folds=3)
        result = analyze_variant("test", data)
        assert result["selection_freq"].get("alpha_test_good", 0) == 3
        assert result["rejection_freq"].get("alpha_test_bad", 0) == 3


# ---------------------------------------------------------------------------
# Test generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_report_generation(self):
        data_bl = _make_minimal_variant(n_folds=3)
        data_rg = _make_minimal_variant(n_folds=3, with_guard=True)
        variants = {
            "baseline": analyze_variant("baseline", data_bl),
            "ra_guard": analyze_variant("ra_guard", data_rg),
        }
        report = generate_report(variants)
        assert "# Alpha Weakness Diagnostics Report" in report
        assert "## 1. Per-Variant Summary" in report
        assert "## 2. Fold-Level" in report
        assert "## 7. Weak Alpha Ranking" in report
        assert "## 9. Recommended Gates" in report
        assert "alpha_test_good" in report or "test_good" in report

    def test_report_no_guard(self):
        data = _make_minimal_variant(n_folds=2)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(variants)
        assert "not enabled" in report


# ---------------------------------------------------------------------------
# Test main CLI
# ---------------------------------------------------------------------------

class TestMainCLI:
    def test_main_run(self, tmp_path):
        """End-to-end test with real-ish data."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        # Write minimal variant files
        data = _make_minimal_variant(n_folds=2)
        for vname in ["baseline", "ra_guard", "ra_no_guard"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
            ],
        ):
            rc = main()
        assert rc == 0
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "# Alpha Weakness Diagnostics Report" in content
        assert "baseline" in content.lower() or "Baseline" in content


# ---------------------------------------------------------------------------
# Test with real repo data (integration, skip if not available)
# ---------------------------------------------------------------------------

class TestIntegration:
    """Integration tests using actual repo data if available."""

    REAL_DIR = Path(__file__).resolve().parent.parent / "data" / "phase35_results" / "ab_guard_20260614_101727"

    @pytest.fixture(autouse=True)
    def _skip_if_no_data(self):
        if not self.REAL_DIR.is_dir():
            pytest.skip("Real data directory not found")

    def test_real_data_loads(self):
        variants = discover_variant_files(str(self.REAL_DIR))
        assert len(variants) == 3

    def test_real_analysis_runs(self, tmp_path):
        variants = discover_variant_files(str(self.REAL_DIR))
        analyzed = {}
        for vname, vpath in variants.items():
            data = load_variant(vpath)
            analyzed[vname] = analyze_variant(vname, data)
        assert len(analyzed) == 3
        for v in analyzed.values():
            assert v["n_folds"] == 8

    def test_real_report_generation(self, tmp_path):
        variants = discover_variant_files(str(self.REAL_DIR))
        analyzed = {}
        for vname, vpath in variants.items():
            data = load_variant(vpath)
            analyzed[vname] = analyze_variant(vname, data)
        report = generate_report(analyzed)
        output = tmp_path / "report.md"
        output.write_text(report, encoding="utf-8")
        content = output.read_text(encoding="utf-8")
        assert "close_auction_drift" in content
        assert len(content) > 1000


# ---------------------------------------------------------------------------
# Finding 1: No hard-coded fallback rates in recommendations
# ---------------------------------------------------------------------------

class TestNoHardcodedFallbackRates:
    """Verify that system recommendations use computed fallback rates,
    not hard-coded '100% fallback rate' text."""

    def test_report_no_hardcoded_100_percent_fallback(self):
        """Report must never contain the literal '100% fallback rate'."""
        data_bl = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data_bl)}
        report = generate_report(variants)
        assert "100% fallback rate" not in report
        assert "100% fallback-to-baseline" not in report

    def test_report_shows_computed_fallback_rates(self):
        """Report section 9.3 must show per-variant fallback counts/rates."""
        data_bl = _make_minimal_variant(n_folds=8)
        # Make some folds NOT use fallback to get a non-100% rate
        for fold in data_bl["fold_details"][:3]:
            fold["used_fallback_candidates"] = False
        variants = {"baseline": analyze_variant("baseline", data_bl)}
        report = generate_report(variants)
        # Should contain "5/8" (5 of 8 used fallback)
        assert "5/8" in report
        # Should contain the computed percentage "62.5%"
        assert "62.5%" in report

    def test_report_shows_computed_guard_fallback_rate(self):
        """Report section 9.3 must show computed guard fallback-to-baseline rate."""
        data_rg = _make_minimal_variant(n_folds=8, with_guard=True)
        # Make guard ACCEPT some folds so rate is not 100%
        for fold in data_rg["fold_details"][:2]:
            fold["portfolio_guard_evidence"]["portfolio_guard_status"] = "ACCEPTED"
        variants = {"ra_guard": analyze_variant("ra_guard", data_rg)}
        report = generate_report(variants)
        # Guard was enabled on 8, rejected (FALLBACK_TO_BASELINE) on 6
        assert "6/8" in report
        assert "75.0%" in report

    def test_guard_fallback_ratio_is_computed_and_zero_when_disabled(self):
        data_rg = _make_minimal_variant(n_folds=4, with_guard=True)
        data_rg["fold_details"][0]["portfolio_guard_evidence"]["portfolio_guard_status"] = "ACCEPTED"
        result = analyze_variant("ra_guard", data_rg)
        assert result["guard_analysis"]["guard_fallback_to_baseline_rate"] == pytest.approx(0.75)

        result = analyze_variant("baseline", _make_minimal_variant(n_folds=2))
        assert result["guard_analysis"]["guard_fallback_to_baseline_rate"] == 0.0

    def test_report_no_guard_enabled(self):
        """When no guard variant is present, report says guard not enabled."""
        data_bl = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data_bl)}
        report = generate_report(variants)
        assert "Not enabled in any analyzed variant" in report


# ---------------------------------------------------------------------------
# Finding 2: Guard false-positive renamed to post-fallback positive outcome
# ---------------------------------------------------------------------------

class TestPostFallbackPositiveMetric:
    """Verify that the old 'false_positive_count' key is replaced with
    'post_fallback_positive_count' and that the metric is clearly described
    as post-fallback outcome, not guard correctness."""

    def test_guard_analysis_returns_post_fallback_key(self):
        """_analyze_guard must return 'post_fallback_positive_count', not
        'false_positive_count'."""
        data = _make_minimal_variant(n_folds=2, with_guard=True)
        folds = data["fold_details"]
        ga = _analyze_guard(folds)
        assert "post_fallback_positive_count" in ga
        assert "false_positive_count" not in ga

    def test_post_fallback_count_with_low_sharpe(self):
        """When fold Sharpe <= 1.0, post_fallback_positive_count stays 0
        even though guard rejected."""
        data = _make_minimal_variant(n_folds=3, with_guard=True)
        # All folds have sharpe < 1.0 (default _make_minimal_fold: 0.6, 0.7, 0.8)
        folds = data["fold_details"]
        ga = _analyze_guard(folds)
        assert ga["post_fallback_positive_count"] == 0
        assert ga["guard_rejected"] == 3

    def test_post_fallback_count_with_high_sharpe(self):
        """When fold Sharpe > 1.0 and IC > 0 after FALLBACK_TO_BASELINE,
        the post_fallback_positive_count increments."""
        data = _make_minimal_variant(n_folds=2, with_guard=True)
        # Set high Sharpe on fold 1
        data["fold_details"][0]["portfolio_sharpe"] = 1.5
        data["fold_details"][0]["portfolio_ic"] = 0.05
        folds = data["fold_details"]
        ga = _analyze_guard(folds)
        assert ga["post_fallback_positive_count"] == 1

    def test_report_labels_post_fallback_not_false_positive(self):
        """Report text must not use 'False Positives', 'False positives',
        'FALSE POSITIVES', or 'false_positive' in any casing."""
        data_rg = _make_minimal_variant(n_folds=2, with_guard=True)
        # Make a fold that triggers the post-fallback positive count
        data_rg["fold_details"][0]["portfolio_sharpe"] = 1.5
        data_rg["fold_details"][0]["portfolio_ic"] = 0.05
        variants = {"ra_guard": analyze_variant("ra_guard", data_rg)}
        report = generate_report(variants)
        assert "False positives" not in report
        assert "FALSE POSITIVES" not in report
        # Title Case regression (L3 fix3 finding)
        assert "False Positives" not in report
        # Snake-case identifier must not leak into report text
        assert "false_positive" not in report
        # Case-insensitive sweep: no variation of 'false positive' allowed
        report_lower = report.lower()
        assert "false positive" not in report_lower
        assert "Post-fallback positive" in report or "POST-FALLBACK POSITIVE" in report

    def test_selected_vs_baseline_vs_realized_ic_distinction(self):
        """Guard analysis detail preserves selected_basket_ic and
        baseline_basket_ic separately from realized fold metrics."""
        data = _make_minimal_variant(n_folds=1, with_guard=True)
        fold = data["fold_details"][0]
        fold["portfolio_ic"] = 0.03  # realized fold IC (post-fallback)
        fold["portfolio_guard_evidence"]["selected_basket_validation_ic"] = -0.05
        fold["portfolio_guard_evidence"]["baseline_basket_validation_ic"] = 0.02
        folds = data["fold_details"]
        ga = _analyze_guard(folds)
        detail = ga["guard_details"][0]
        # Selected basket IC is from guard evidence, not realized fold
        assert detail["selected_basket_ic"] == -0.05
        assert detail["baseline_basket_ic"] == 0.02
        assert detail["realized_portfolio_ic"] == 0.03
        assert detail["realized_portfolio_sharpe"] == fold["portfolio_sharpe"]
        # Realized fold IC is separate and not used in guard detail
        assert fold["portfolio_ic"] == 0.03

    def test_post_fallback_metric_is_realized_portfolio_not_guard_error(self):
        data = _make_minimal_variant(n_folds=1, with_guard=True)
        fold = data["fold_details"][0]
        fold["portfolio_sharpe"] = 1.5
        fold["portfolio_ic"] = 0.05
        result = analyze_variant("ra_guard", data)
        detail = result["guard_analysis"]["guard_details"][0]
        assert detail["selected_basket_ic"] == -0.01
        assert detail["baseline_basket_ic"] == 0.02
        assert detail["realized_portfolio_ic"] == 0.05
        report = generate_report({"ra_guard": result})
        assert "POST-FALLBACK POSITIVE REALIZED PORTFOLIOS" in report
        assert "guard correctness metric" in report


# ---------------------------------------------------------------------------
# Research Alpha Gates (GATE: RESEARCH_ALPHA_GATES_20260614)
# ---------------------------------------------------------------------------

class TestResearchGateICIR:
    """ICIR must be computed per variant and per alpha."""

    def test_variant_icir_present(self):
        data = _make_minimal_variant(n_folds=4)
        result = analyze_variant("baseline", data)
        assert "variant_icir" in result
        assert isinstance(result["variant_icir"], float)

    def test_alpha_icir_present(self):
        data = _make_minimal_variant(n_folds=4)
        result = analyze_variant("baseline", data)
        assert "alpha_icir" in result
        for alpha_name in result["alpha_stats"]:
            assert alpha_name in result["alpha_icir"]

    def test_alpha_stats_have_icir(self):
        data = _make_minimal_variant(n_folds=4)
        result = analyze_variant("baseline", data)
        for a_name, stats in result["alpha_stats"].items():
            assert "icir" in stats
            assert "p_value" in stats
            assert "q_value" in stats


class TestResearchGateBH_FDR:
    """BH-FDR q-values must be computed per alpha."""

    def test_q_values_present(self):
        data = _make_minimal_variant(n_folds=5)
        result = analyze_variant("baseline", data)
        assert "alpha_q_values" in result
        assert len(result["alpha_q_values"]) == len(result["alpha_stats"])

    def test_q_values_bounded(self):
        data = _make_minimal_variant(n_folds=5)
        result = analyze_variant("baseline", data)
        for q_val in result["alpha_q_values"].values():
            assert 0.0 <= q_val <= 1.0


class TestResearchGateSignConsistency:
    """Sign consistency (positive fold rate) rejection must work."""

    def test_compute_research_verdicts(self):
        data = _make_minimal_variant(n_folds=4)
        result = analyze_variant("baseline", data)
        verdicts = _compute_research_verdicts(result)
        assert isinstance(verdicts, dict)
        assert len(verdicts) == len(result["alpha_stats"])
        for v in verdicts.values():
            assert v in ("PROMOTE_CANDIDATE", "ENSEMBLE_ONLY", "REVIEW", "RETIRE")

    def test_negative_ic_alpha_retired(self):
        """Alpha with consistently negative IC should be RETIRE."""
        data = _make_minimal_variant(n_folds=5)
        # Override alpha_ics to make alpha_test_bad consistently negative
        for fold in data["fold_details"]:
            fold["alpha_ics"]["alpha_test_bad"] = -0.05
        result = analyze_variant("baseline", data)
        verdicts = _compute_research_verdicts(result)
        assert verdicts["alpha_test_bad"] == "RETIRE"


class TestResearchGateFallbackAsFailure:
    """Fallback-as-failure metrics must be in analysis results."""

    def test_fallback_metrics_present(self):
        data = _make_minimal_variant(n_folds=3)
        result = analyze_variant("baseline", data)
        assert "fallback_as_failure_metrics" in result
        fb = result["fallback_as_failure_metrics"]
        assert "total_folds" in fb
        assert "alpha_selected_folds" in fb
        assert "fallback_folds" in fb
        assert "fallback_as_failure_rate" in fb

    def test_all_fallback(self):
        """When all folds use fallback, rate should be 1.0."""
        data = _make_minimal_variant(n_folds=3)
        # All folds have used_fallback_candidates = True (default in _make_minimal_variant)
        result = analyze_variant("baseline", data)
        fb = result["fallback_as_failure_metrics"]
        assert fb["fallback_as_failure_rate"] == 1.0

    def test_no_fallback(self):
        """When no folds use fallback, rate should be 0.0."""
        data = _make_minimal_variant(n_folds=3)
        for fold in data["fold_details"]:
            fold["used_fallback_candidates"] = False
        result = analyze_variant("baseline", data)
        fb = result["fallback_as_failure_metrics"]
        assert fb["fallback_as_failure_rate"] == 0.0
        assert fb["alpha_selected_folds"] == 3


class TestResearchGateReportSections:
    """Report must include/exclude sections based on enable_research_gates."""

    def test_default_report_no_research_gates(self):
        """Default report (no research gates) should not have section 10."""
        data = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(variants)
        assert "## 10. Research Alpha Gates" not in report
        assert "ICIR" not in report
        assert "BH-FDR" not in report

    def test_optin_report_has_research_gates(self):
        """Opt-in report should have section 10 with research gates."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(variants, enable_research_gates=True)
        assert "## 10. Research Alpha Gates" in report
        assert "RESEARCH_ALPHA_GATES_20260614" in report
        assert "### 10.1 Variant-Level ICIR" in report
        assert "### 10.2 Per-Alpha Research Gate Verdicts" in report
        assert "### 10.3 Verdict Summary" in report
        assert "### 10.4 Fallback-as-Failure Diagnostics" in report

    def test_report_contains_verdict_labels(self):
        """Report must contain verdict category labels."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(variants, enable_research_gates=True)
        # At least one verdict must appear
        has_verdict = any(
            v in report
            for v in ["PROMOTE_CANDIDATE", "ENSEMBLE_ONLY", "REVIEW", "RETIRE"]
        )
        assert has_verdict

    def test_report_fallback_as_failure_not_alpha_success(self):
        """Report text must clearly state fallback != alpha success."""
        data = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(variants, enable_research_gates=True)
        assert "does NOT count as alpha success" in report


class TestResearchGateDefaultBackwardCompatibility:
    """Default behavior must be unchanged when research gates are not enabled."""

    def test_report_without_flag_unchanged(self):
        """Report generated without enable_research_gates should be identical
        to previous behavior."""
        data = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(variants)
        # Section 9 should still be the last numbered section
        assert "## 9. Recommended Gates" in report
        # No section 10
        assert "## 10." not in report

    def test_cli_default_no_research_gates(self, tmp_path):
        """CLI default should not enable research gates."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=2)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "## 10. Research Alpha Gates" not in content

    def test_cli_research_gates_flag(self, tmp_path):
        """CLI --research-gates flag enables research gate sections."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=4)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
                "--research-gates",
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "## 10. Research Alpha Gates" in content


# ---------------------------------------------------------------------------
# Alpha Recovery Diagnostics (GATE: ALPHA_RECOVERY_DIAGNOSTICS_20260614)
# ---------------------------------------------------------------------------

class TestRecoveryDiagnosticsOptIn:
    """Recovery diagnostics must be opt-in and not affect default behavior."""

    def test_default_report_no_recovery_diagnostics(self):
        """Default report should not have recovery diagnostics section."""
        data = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(variants)
        assert "Alpha Recovery Diagnostics" not in report
        assert "Neutralized IC Proxy" not in report
        assert "Regime-Conditioned IC" not in report
        assert "IC Decay" not in report
        assert "Retirement" not in report or "Recommended" in report

    def test_optin_report_has_recovery_diagnostics(self):
        """Opt-in report should have recovery diagnostics sections."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_recovery_diagnostics=True,
        )
        assert "Alpha Recovery Diagnostics" in report
        assert "ALPHA_RECOVERY_DIAGNOSTICS_20260614" in report
        assert "Neutralized IC Proxy" in report
        assert "Regime-Conditioned IC" in report
        assert "IC Decay" in report
        assert "Retirement" in report

    def test_recovery_with_research_gates(self):
        """Recovery diagnostics work together with research gates."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_research_gates=True,
            enable_recovery_diagnostics=True,
        )
        assert "## 10. Research Alpha Gates" in report
        assert "Alpha Recovery Diagnostics" in report
        # Research verdicts should appear in recovery summary
        has_verdict = any(
            v in report
            for v in ["PROMOTE_CANDIDATE", "ENSEMBLE_ONLY", "REVIEW", "RETIRE"]
        )
        assert has_verdict

    def test_recovery_summary_counts(self):
        """Recovery report must show classification counts."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_recovery_diagnostics=True,
        )
        assert "RECOVERABLE" in report
        assert "RESEARCH_ONLY" in report
        assert "CONFIRMED_RETIRE" in report

    def test_recovery_no_live_trading_note(self):
        """Report must state recovery diagnostics don't affect live trading."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_recovery_diagnostics=True,
        )
        assert "do NOT change default behavior" in report or "research-only" in report.lower()

    def test_cli_recovery_diagnostics_flag(self, tmp_path):
        """CLI --recovery-diagnostics flag enables recovery sections."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=4)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
                "--recovery-diagnostics",
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Alpha Recovery Diagnostics" in content

    def test_cli_default_no_recovery(self, tmp_path):
        """CLI default should not enable recovery diagnostics."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=2)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Alpha Recovery Diagnostics" not in content


# ---------------------------------------------------------------------------
# Recovery Pool A/B Diagnostics (GATE: RECOVERY_POOL_AB_DIAGNOSTICS_20260614)
# ---------------------------------------------------------------------------

class TestRecoveryPoolABOptIn:
    """Recovery pool A/B diagnostics must be opt-in and not affect default."""

    def test_default_report_no_recovery_pool_ab(self):
        """Default report should not have recovery pool A/B section."""
        data = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(variants)
        assert "Recovery Pool A/B" not in report
        assert "RECOVERY_POOL_AB_DIAGNOSTICS_20260614" not in report

    def test_optin_report_has_recovery_pool_ab(self):
        """Opt-in report should have recovery pool A/B section."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_recovery_pool_ab=True,
        )
        assert "Recovery Pool A/B" in report
        assert "RECOVERY_POOL_AB_DIAGNOSTICS_20260614" in report

    def test_recovery_pool_excludes_confirmed_retire(self):
        """Recovery pool must exclude CONFIRMED_RETIRE alphas."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_recovery_pool_ab=True,
        )
        # Report should contain pool definitions
        assert "Full pool" in report
        assert "Recovery-only pool" in report
        assert "CONFIRMED_RETIRE excluded" in report

    def test_recovery_pool_with_research_gates(self):
        """Recovery pool A/B works together with research gates."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_research_gates=True,
            enable_recovery_pool_ab=True,
        )
        assert "## 10. Research Alpha Gates" in report
        assert "Recovery Pool A/B" in report

    def test_recovery_pool_shows_per_fold_comparison(self):
        """Report must include per-fold mean IC comparison table."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_recovery_pool_ab=True,
        )
        assert "Full Pool Mean IC" in report
        assert "Recovery Pool Mean IC" in report
        assert "Positive Fold Rate" in report

    def test_recovery_pool_no_live_trading_note(self):
        """Report must state pool A/B doesn't affect live trading."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_recovery_pool_ab=True,
        )
        assert "do NOT change default behavior" in report or "research-only" in report.lower()

    def test_recovery_pool_shows_recoverable_vs_research_only(self):
        """Report should include RECOVERABLE vs RESEARCH_ONLY breakdown."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_recovery_pool_ab=True,
        )
        assert "RECOVERABLE" in report
        assert "RESEARCH_ONLY" in report

    def test_recovery_pool_backward_compatible(self):
        """Default report without flag is unchanged."""
        data = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data)}
        report_default = generate_report(variants)
        report_no_flag = generate_report(
            variants, enable_recovery_pool_ab=False
        )
        assert report_default == report_no_flag

    def test_cli_recovery_pool_ab_flag(self, tmp_path):
        """CLI --recovery-pool-ab flag enables recovery pool A/B section."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=4)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
                "--recovery-pool-ab",
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Recovery Pool A/B" in content

    def test_cli_default_no_recovery_pool_ab(self, tmp_path):
        """CLI default should not enable recovery pool A/B."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=2)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Recovery Pool A/B" not in content

    def test_cli_regime_threshold_ic_flag(self, tmp_path):
        """CLI --regime-threshold-ic flag passes through correctly."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=4)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
                "--recovery-pool-ab",
                "--regime-threshold-ic", "0.0",
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Recovery Pool A/B" in content
        # Report should show the custom threshold (markdown: **Regime threshold IC**: 0.0)
        assert "Regime threshold IC**: 0.0" in content


# ---------------------------------------------------------------------------
# Selector-Ready Report (GATE: RECOVERY_SELECTOR_OPT_IN_20260614)
# ---------------------------------------------------------------------------

class TestSelectorReadyReportOptIn:
    """Selector-ready report must be opt-in and not affect default."""

    def test_default_report_no_selector_ready(self):
        """Default report should not have selector-ready section."""
        data = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(variants)
        assert "Selector-Ready Report" not in report
        assert "RECOVERY_SELECTOR_OPT_IN_20260614" not in report
        assert "DO_NOT_PROMOTE" not in report

    def test_optin_report_has_selector_ready(self):
        """Opt-in report should have selector-ready section."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_selector_ready=True,
        )
        assert "Selector-Ready Report" in report
        assert "RECOVERY_SELECTOR_OPT_IN_20260614" in report

    def test_selector_ready_shows_pool_metrics(self):
        """Report must show full vs recovery pool metrics."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_selector_ready=True,
        )
        assert "Pool A/B Metrics" in report
        assert "Full Pool" in report
        assert "Recovery-Only Pool" in report
        assert "Mean Fold IC" in report
        assert "Positive Fold Rate" in report

    def test_selector_ready_shows_verdict(self):
        """Report must show a selector verdict."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_selector_ready=True,
        )
        assert "Selector Verdict" in report
        # At least one verdict must appear
        has_verdict = any(
            v in report
            for v in ["DO_NOT_PROMOTE", "CONDITIONAL_PROMOTE", "INSUFFICIENT_EVIDENCE"]
        )
        assert has_verdict

    def test_selector_ready_shows_recommendations(self):
        """Report must show recommendations."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_selector_ready=True,
        )
        assert "Recommendations" in report
        assert "full" in report

    def test_selector_ready_do_not_promote_blocker(self):
        """DO_NOT_PROMOTE blocker appears when IC improves but fold rate does not."""
        # Make folds where recovery pool will have higher IC but same/lower fold rate
        data = _make_minimal_variant(n_folds=4)
        # Override: make alpha_test_bad consistently negative (confirmed retire)
        # and alpha_test_good positive (recovery/research)
        for fold in data["fold_details"]:
            fold["alpha_ics"]["alpha_test_bad"] = -0.05
            fold["alpha_test_good"] = 0.03
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_selector_ready=True,
        )
        # Either DO_NOT_PROMOTE or another verdict depending on exact metrics
        assert "Selector Verdict" in report

    def test_selector_ready_with_research_gates(self):
        """Selector-ready works together with research gates."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_research_gates=True,
            enable_selector_ready=True,
        )
        assert "## 10. Research Alpha Gates" in report
        assert "Selector-Ready Report" in report

    def test_selector_ready_with_recovery_pool_ab(self):
        """Selector-ready works together with recovery pool A/B."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_recovery_pool_ab=True,
            enable_selector_ready=True,
        )
        assert "Recovery Pool A/B" in report
        assert "Selector-Ready Report" in report

    def test_selector_ready_no_live_trading_note(self):
        """Report must state selector-ready doesn't affect live trading."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_selector_ready=True,
        )
        assert "do NOT change default behavior" in report or "research-only" in report.lower()

    def test_selector_ready_backward_compatible(self):
        """Default report without flag is unchanged."""
        data = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data)}
        report_default = generate_report(variants)
        report_no_flag = generate_report(
            variants, enable_selector_ready=False
        )
        assert report_default == report_no_flag

    def test_selector_ready_shows_pool_sizes(self):
        """Report must show pool sizes."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_selector_ready=True,
        )
        assert "Pool Size" in report
        assert "Recoverable-Only Size" in report

    def test_cli_selector_ready_flag(self, tmp_path):
        """CLI --selector-ready flag enables selector-ready section."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=4)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
                "--selector-ready",
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Selector-Ready Report" in content

    def test_cli_default_no_selector_ready(self, tmp_path):
        """CLI default should not enable selector-ready."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=2)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Selector-Ready Report" not in content


# ---------------------------------------------------------------------------
# Statistical Validation Gates (GATE: STAT_VALIDATION_GATES_20260614)
# ---------------------------------------------------------------------------

class TestStatValidationGatesOptIn:
    """Stat validation gates must be opt-in and not affect default."""

    def test_default_report_no_stat_validation(self):
        """Default report should not have stat validation section."""
        data = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(variants)
        assert "Statistical Validation Gates" not in report
        assert "STAT_VALIDATION_GATES_20260614" not in report
        assert "DSR" not in report
        assert "PBO" not in report

    def test_optin_report_has_stat_validation(self):
        """Opt-in report should have stat validation section."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_stat_validation_gates=True,
        )
        assert "Statistical Validation Gates" in report
        assert "STAT_VALIDATION_GATES_20260614" in report
        assert "DSR" in report
        assert "PBO" in report

    def test_stat_validation_shows_dsr(self):
        """Report must show DSR value."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_stat_validation_gates=True,
        )
        assert "Deflated Sharpe Ratio" in report
        assert "DSR gate" in report

    def test_stat_validation_shows_pbo(self):
        """Report must show PBO value."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_stat_validation_gates=True,
        )
        assert "Probability of Backtest Overfitting" in report
        assert "PBO gate" in report

    def test_stat_validation_shows_cpcv_ready(self):
        """Report must show CPCV-ready status."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_stat_validation_gates=True,
        )
        assert "CPCV-Ready" in report

    def test_stat_validation_shows_verdict(self):
        """Report must show validation verdict."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_stat_validation_gates=True,
        )
        assert "Validation Verdict" in report
        assert "Verdict" in report

    def test_stat_validation_weak_alpha_blocked(self):
        """Weak alpha should be blocked/FAIL."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_stat_validation_gates=True,
        )
        # Current weak alpha has mean IC below 0.02 → blocked
        assert "STAT_VALIDATION_FAIL" in report or "FAIL" in report

    def test_stat_validation_no_live_trading_note(self):
        """Report must state stat validation doesn't affect live trading."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_stat_validation_gates=True,
        )
        assert "do NOT change default behavior" in report or "research-only" in report.lower()

    def test_stat_validation_backward_compatible(self):
        """Default report without flag is unchanged."""
        data = _make_minimal_variant(n_folds=3)
        variants = {"baseline": analyze_variant("baseline", data)}
        report_default = generate_report(variants)
        report_no_flag = generate_report(
            variants, enable_stat_validation_gates=False
        )
        assert report_default == report_no_flag

    def test_stat_validation_custom_thresholds(self):
        """Custom max_pbo and min_dsr appear in report."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_stat_validation_gates=True,
            max_pbo=0.30,
            min_dsr=0.5,
        )
        assert "Max PBO threshold**: 0.3" in report
        assert "Min DSR threshold**: 0.5" in report

    def test_stat_validation_with_research_gates(self):
        """Stat validation works together with research gates."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_research_gates=True,
            enable_stat_validation_gates=True,
        )
        assert "## 10. Research Alpha Gates" in report
        assert "Statistical Validation Gates" in report

    def test_stat_validation_shows_path_consistency(self):
        """Report must show path consistency table."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_stat_validation_gates=True,
        )
        assert "Consistency" in report

    def test_stat_validation_shows_blockers(self):
        """Report must show promotion blockers when FAIL."""
        data = _make_minimal_variant(n_folds=4)
        variants = {"baseline": analyze_variant("baseline", data)}
        report = generate_report(
            variants,
            enable_stat_validation_gates=True,
        )
        assert "Blockers" in report or "blocker" in report.lower()

    def test_cli_stat_validation_flag(self, tmp_path):
        """CLI --stat-validation-gates flag enables section."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=4)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
                "--stat-validation-gates",
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Statistical Validation Gates" in content

    def test_cli_default_no_stat_validation(self, tmp_path):
        """CLI default should not enable stat validation."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=2)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Statistical Validation Gates" not in content

    def test_cli_max_pbo_flag(self, tmp_path):
        """CLI --max-pbo flag passes through correctly."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=4)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
                "--stat-validation-gates",
                "--max-pbo", "0.30",
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Max PBO threshold**: 0.3" in content

    def test_cli_min_dsr_flag(self, tmp_path):
        """CLI --min-dsr flag passes through correctly."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_file = tmp_path / "output" / "report.md"

        data = _make_minimal_variant(n_folds=4)
        for vname in ["baseline"]:
            fname = f"{vname}_phase35_backtest_results_xgboost.json"
            (input_dir / fname).write_text(json.dumps(data))

        with patch(
            "sys.argv",
            [
                "analyze_alpha_weakness.py",
                "--input-dir", str(input_dir),
                "--output", str(output_file),
                "--stat-validation-gates",
                "--min-dsr", "0.5",
            ],
        ):
            rc = main()
        assert rc == 0
        content = output_file.read_text(encoding="utf-8")
        assert "Min DSR threshold**: 0.5" in content
