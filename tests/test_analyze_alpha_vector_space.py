"""Tests for scripts/analyze_alpha_vector_space.py

Gate: ALPHA_VECTOR_SPACE_DISCOVERY_20260615
Role: 14 (data-scientist) L2
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from analyze_alpha_vector_space import (
    CLUSTER_CORR_THRESHOLD,
    GATE,
    VERDICT_DO_NOT_PROMOTE,
    VERDICT_RESEARCH_ONLY,
    _count_scalar_features,
    _fmt,
    _fmt_pct,
    _pearson_r,
    _safe_icir,
    _safe_mean,
    _safe_median,
    _safe_skew,
    _safe_std,
    _short_name,
    build_json_summary,
    compute_alpha_vectors,
    compute_pairwise_correlation,
    correlation_distance_clustering,
    extract_alpha_fold_ics,
    extract_fold_portfolio_ics,
    extract_fold_sharpes,
    extract_fold_max_dds,
    extract_fold_total_returns,
    generate_report,
    identify_complementary_candidates,
    identify_redundant_clusters,
    load_phase35_json,
    main,
)


# ---------------------------------------------------------------------------
# Helpers: minimal Phase 3.5 JSON fixtures
# ---------------------------------------------------------------------------

def _make_phase35_data(n_folds=4, alphas=None):
    """Create a minimal Phase 3.5 JSON-like dict."""
    if alphas is None:
        alphas = {
            "alpha_a": [0.02, 0.03, 0.01, 0.04],
            "alpha_b": [0.01, -0.01, 0.02, -0.02],
            "alpha_c": [-0.03, -0.04, -0.02, -0.05],
        }
    fold_details = []
    portfolio_ics = [0.01, 0.02, -0.01, 0.03]
    for i in range(n_folds):
        alpha_ics = {name: vals[i] for name, vals in alphas.items()}
        fold_details.append({
            "fold_id": i + 1,
            "train_start": f"201{i}-01-01",
            "train_end": f"201{i + 2}-12-31",
            "test_start": f"201{i + 3}-01-01",
            "test_end": f"201{i + 3}-12-31",
            "portfolio_ic": portfolio_ics[i] if i < len(portfolio_ics) else 0.0,
            "portfolio_sharpe": 0.5 + 0.1 * i,
            "portfolio_max_dd": -0.05,
            "alpha_ics": alpha_ics,
        })
    return {
        "config": {
            "start_date": "2015-01-05",
            "end_date": "2026-05-14",
            "n_folds": n_folds,
        },
        "summary": {
            "avg_portfolio_ic": 0.01,
            "total_folds": n_folds,
        },
        "fold_details": fold_details,
    }


# ---------------------------------------------------------------------------
# Test statistics helpers
# ---------------------------------------------------------------------------

class TestStatsHelpers:
    def test_safe_mean_empty(self):
        assert _safe_mean([]) == 0.0

    def test_safe_mean_values(self):
        assert abs(_safe_mean([1.0, 2.0, 3.0]) - 2.0) < 1e-10

    def test_safe_std_empty(self):
        assert _safe_std([]) == 0.0

    def test_safe_std_single(self):
        assert _safe_std([5.0]) == 0.0

    def test_safe_std_values(self):
        result = _safe_std([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        assert result > 0

    def test_safe_icir_zero_std(self):
        assert _safe_icir([0.02, 0.02, 0.02]) == 0.0

    def test_safe_icir_normal(self):
        result = _safe_icir([0.02, 0.04, 0.03, 0.01])
        assert isinstance(result, float)
        assert result != 0.0

    def test_pearson_r_identical(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        assert abs(_pearson_r(xs, xs) - 1.0) < 1e-10

    def test_pearson_r_opposite(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [-1.0, -2.0, -3.0, -4.0]
        assert abs(_pearson_r(xs, ys) - (-1.0)) < 1e-10

    def test_pearson_r_uncorrelated(self):
        xs = [1.0, -1.0, 1.0, -1.0]
        ys = [1.0, 1.0, -1.0, -1.0]
        assert abs(_pearson_r(xs, ys)) < 1e-10

    def test_pearson_r_single(self):
        assert _pearson_r([1.0], [2.0]) == 0.0


# ---------------------------------------------------------------------------
# Test formatting helpers
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_fmt(self):
        assert _fmt(0.123456, 4) == "0.1235"

    def test_fmt_pct(self):
        assert _fmt_pct(0.5, 1) == "50.0%"

    def test_short_name_p34(self):
        assert _short_name("alpha_p34_volatility_compression_5") == "p34_volatility_compression_5"

    def test_short_name_fml(self):
        assert _short_name("alpha_fml052_close_zscore_mr_20") == "fml052_close_zscore_mr_20"


# ---------------------------------------------------------------------------
# Test data loading
# ---------------------------------------------------------------------------

class TestDataLoading:
    def test_load_json(self, tmp_path):
        data = _make_phase35_data()
        fpath = tmp_path / "test.json"
        fpath.write_text(json.dumps(data))
        result = load_phase35_json(str(fpath))
        assert "fold_details" in result
        assert len(result["fold_details"]) == 4

    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_phase35_json("/nonexistent/path.json")


# ---------------------------------------------------------------------------
# Test extract_alpha_fold_ics (parsing)
# ---------------------------------------------------------------------------

class TestExtractAlphaFoldICs:
    def test_basic_extraction(self):
        data = _make_phase35_data()
        result = extract_alpha_fold_ics(data)
        assert "alpha_a" in result
        assert "alpha_b" in result
        assert "alpha_c" in result
        assert result["alpha_a"] == [0.02, 0.03, 0.01, 0.04]

    def test_empty_fold_details(self):
        data = {"fold_details": []}
        result = extract_alpha_fold_ics(data)
        assert result == {}

    def test_missing_alpha_ics_field(self):
        data = {
            "fold_details": [
                {"fold_id": 1, "portfolio_ic": 0.01},
                {"fold_id": 2, "portfolio_ic": 0.02},
            ]
        }
        result = extract_alpha_fold_ics(data)
        assert result == {}

    def test_fold_ordering(self):
        """Fold ICs must be ordered by fold_id, not insertion order."""
        data = {
            "fold_details": [
                {"fold_id": 3, "alpha_ics": {"alpha_x": 0.3}},
                {"fold_id": 1, "alpha_ics": {"alpha_x": 0.1}},
                {"fold_id": 2, "alpha_ics": {"alpha_x": 0.2}},
            ]
        }
        result = extract_alpha_fold_ics(data)
        assert result["alpha_x"] == [0.1, 0.2, 0.3]

    def test_partial_alpha_presence(self):
        """Alpha present in only some folds."""
        data = {
            "fold_details": [
                {"fold_id": 1, "alpha_ics": {"alpha_a": 0.01}},
                {"fold_id": 2, "alpha_ics": {"alpha_b": 0.02}},
            ]
        }
        result = extract_alpha_fold_ics(data)
        assert result["alpha_a"] == [0.01]
        assert result["alpha_b"] == [0.02]


class TestExtractFoldPortfolioICs:
    def test_basic(self):
        data = _make_phase35_data()
        result = extract_fold_portfolio_ics(data)
        assert len(result) == 4
        assert result[0] == 0.01

    def test_empty(self):
        data = {"fold_details": []}
        result = extract_fold_portfolio_ics(data)
        assert result == []


# ---------------------------------------------------------------------------
# Test compute_alpha_vectors (deterministic vectors)
# ---------------------------------------------------------------------------

class TestComputeAlphaVectors:
    def test_basic_features(self):
        alpha_fold_ics = {
            "alpha_a": [0.02, 0.03, 0.01, 0.04],
            "alpha_b": [0.01, -0.01, 0.02, -0.02],
        }
        portfolio_ics = [0.01, 0.02, -0.01, 0.03]
        result = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)

        assert "alpha_a" in result
        assert "alpha_b" in result

        va = result["alpha_a"]
        assert va["fold_ic_vector"] == [0.02, 0.03, 0.01, 0.04]
        assert abs(va["mean_ic"] - 0.025) < 1e-10
        assert va["std_ic"] > 0
        assert va["icir"] > 0
        assert va["positive_fold_rate"] == 1.0  # All positive

    def test_deterministic(self):
        """Same input must produce identical output."""
        alpha_fold_ics = {"alpha_a": [0.02, 0.03, 0.01]}
        portfolio_ics = [0.01, 0.02, -0.01]
        r1 = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        r2 = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        assert r1 == r2

    def test_negative_alpha(self):
        alpha_fold_ics = {"alpha_neg": [-0.03, -0.04, -0.02, -0.05]}
        portfolio_ics = [0.01, 0.02, -0.01, 0.03]
        result = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        vn = result["alpha_neg"]
        assert vn["mean_ic"] < 0
        assert vn["positive_fold_rate"] == 0.0

    def test_early_late_trend(self):
        """Early half [0.01, 0.02] mean=0.015, late half [0.03, 0.04] mean=0.035."""
        alpha_fold_ics = {"alpha_a": [0.01, 0.02, 0.03, 0.04]}
        portfolio_ics = [0.01, 0.02, -0.01, 0.03]
        result = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        va = result["alpha_a"]
        assert abs(va["early_half_mean_ic"] - 0.015) < 1e-10
        assert abs(va["late_half_mean_ic"] - 0.035) < 1e-10
        assert abs(va["early_late_trend"] - 0.02) < 1e-10

    def test_bad_fold_association(self):
        """Bad fold association computed for folds where portfolio IC < 0."""
        alpha_fold_ics = {"alpha_a": [0.01, 0.02, -0.03, 0.04]}
        portfolio_ics = [0.01, -0.02, -0.01, 0.03]
        result = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        # Bad folds: index 1 (portfolio=-0.02), index 2 (portfolio=-0.01)
        # alpha at those indices: 0.02, -0.03
        # portfolio at those indices: -0.02, -0.01
        assert "bad_fold_association" in result["alpha_a"]
        assert isinstance(result["alpha_a"]["bad_fold_association"], float)

    def test_empty_ics(self):
        result = compute_alpha_vectors({}, [])
        assert result == {}

    def test_single_fold(self):
        alpha_fold_ics = {"alpha_a": [0.05]}
        portfolio_ics = [0.02]
        result = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        va = result["alpha_a"]
        assert va["mean_ic"] == 0.05
        assert va["std_ic"] == 0.0
        assert va["icir"] == 0.0
        assert va["positive_fold_rate"] == 1.0


# ---------------------------------------------------------------------------
# Test pairwise correlation
# ---------------------------------------------------------------------------

class TestPairwiseCorrelation:
    def test_self_correlation(self):
        alpha_fold_ics = {"alpha_a": [0.01, 0.02, 0.03]}
        result = compute_pairwise_correlation(alpha_fold_ics)
        assert abs(result["alpha_a"]["alpha_a"] - 1.0) < 1e-10

    def test_symmetric(self):
        alpha_fold_ics = {
            "alpha_a": [0.01, 0.02, 0.03],
            "alpha_b": [0.03, 0.02, 0.01],
        }
        result = compute_pairwise_correlation(alpha_fold_ics)
        assert abs(result["alpha_a"]["alpha_b"] - result["alpha_b"]["alpha_a"]) < 1e-10

    def test_opposite_correlation(self):
        alpha_fold_ics = {
            "alpha_a": [1.0, 2.0, 3.0, 4.0],
            "alpha_b": [-1.0, -2.0, -3.0, -4.0],
        }
        result = compute_pairwise_correlation(alpha_fold_ics)
        assert abs(result["alpha_a"]["alpha_b"] - (-1.0)) < 1e-10


# ---------------------------------------------------------------------------
# Test clustering
# ---------------------------------------------------------------------------

class TestClustering:
    def test_all_separate(self):
        """Low correlation → each alpha in its own cluster."""
        corr = {
            "a": {"a": 1.0, "b": 0.1, "c": 0.2},
            "b": {"b": 1.0, "a": 0.1, "c": 0.15},
            "c": {"c": 1.0, "a": 0.2, "b": 0.15},
        }
        labels = correlation_distance_clustering(corr, threshold=0.7)
        assert len(set(labels.values())) == 3

    def test_high_correlation_clustered(self):
        """High correlation → same cluster."""
        corr = {
            "a": {"a": 1.0, "b": 0.85, "c": 0.1},
            "b": {"b": 1.0, "a": 0.85, "c": 0.15},
            "c": {"c": 1.0, "a": 0.1, "b": 0.15},
        }
        labels = correlation_distance_clustering(corr, threshold=0.7)
        assert labels["a"] == labels["b"]
        assert labels["c"] != labels["a"]

    def test_single_linkage_transitivity(self):
        """a-b correlated, b-c correlated, a-c not → all same cluster (single linkage)."""
        corr = {
            "a": {"a": 1.0, "b": 0.8, "c": 0.2},
            "b": {"b": 1.0, "a": 0.8, "c": 0.8},
            "c": {"c": 1.0, "a": 0.2, "b": 0.8},
        }
        labels = correlation_distance_clustering(corr, threshold=0.7)
        assert labels["a"] == labels["b"] == labels["c"]

    def test_negative_correlation_clusters(self):
        """Negative correlation with |r| >= threshold also clusters."""
        corr = {
            "a": {"a": 1.0, "b": -0.85},
            "b": {"b": 1.0, "a": -0.85},
        }
        labels = correlation_distance_clustering(corr, threshold=0.7)
        assert labels["a"] == labels["b"]

    def test_deterministic(self):
        corr = {
            "a": {"a": 1.0, "b": 0.5},
            "b": {"b": 1.0, "a": 0.5},
        }
        l1 = correlation_distance_clustering(corr, threshold=0.7)
        l2 = correlation_distance_clustering(corr, threshold=0.7)
        assert l1 == l2


# ---------------------------------------------------------------------------
# Test redundant clusters
# ---------------------------------------------------------------------------

class TestRedundantClusters:
    def test_no_redundant(self):
        labels = {"a": 0, "b": 1, "c": 2}
        corr = {
            "a": {"a": 1.0, "b": 0.1, "c": 0.2},
            "b": {"b": 1.0, "a": 0.1, "c": 0.15},
            "c": {"c": 1.0, "a": 0.2, "b": 0.15},
        }
        result = identify_redundant_clusters(labels, corr)
        assert result == []

    def test_redundant_detected(self):
        labels = {"a": 0, "b": 0, "c": 1}
        corr = {
            "a": {"a": 1.0, "b": 0.85, "c": 0.1},
            "b": {"b": 1.0, "a": 0.85, "c": 0.15},
            "c": {"c": 1.0, "a": 0.1, "b": 0.15},
        }
        result = identify_redundant_clusters(labels, corr)
        assert len(result) == 1
        assert result[0]["size"] == 2
        assert "a" in result[0]["members"]
        assert "b" in result[0]["members"]


# ---------------------------------------------------------------------------
# Test complementary candidates
# ---------------------------------------------------------------------------

class TestComplementaryCandidates:
    def test_complementary_found(self):
        labels = {"a": 0, "b": 1}
        vectors = {
            "a": {"mean_ic": 0.03},
            "b": {"mean_ic": 0.02},
        }
        corr = {
            "a": {"a": 1.0, "b": 0.1},
            "b": {"b": 1.0, "a": 0.1},
        }
        result = identify_complementary_candidates(labels, vectors, corr)
        assert len(result) == 1
        assert result[0]["abs_correlation"] < 0.3

    def test_same_cluster_excluded(self):
        labels = {"a": 0, "b": 0}
        vectors = {
            "a": {"mean_ic": 0.03},
            "b": {"mean_ic": 0.02},
        }
        corr = {
            "a": {"a": 1.0, "b": 0.1},
            "b": {"b": 1.0, "a": 0.1},
        }
        result = identify_complementary_candidates(labels, vectors, corr)
        assert result == []

    def test_high_correlation_excluded(self):
        labels = {"a": 0, "b": 1}
        vectors = {
            "a": {"mean_ic": 0.03},
            "b": {"mean_ic": 0.02},
        }
        corr = {
            "a": {"a": 1.0, "b": 0.5},
            "b": {"b": 1.0, "a": 0.5},
        }
        result = identify_complementary_candidates(labels, vectors, corr)
        assert result == []


# ---------------------------------------------------------------------------
# Test report generation
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def _make_full_data(self):
        data = _make_phase35_data()
        alpha_fold_ics = extract_alpha_fold_ics(data)
        portfolio_ics = extract_fold_portfolio_ics(data)
        vectors = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        redundant = identify_redundant_clusters(labels, corr)
        complementary = identify_complementary_candidates(labels, vectors, corr)
        return (data, alpha_fold_ics, vectors, corr, labels, redundant, complementary)

    def test_report_has_title(self):
        args = self._make_full_data()
        report = generate_report(*args)
        assert "# Alpha Vector-Space Discovery Report" in report

    def test_report_has_gate(self):
        args = self._make_full_data()
        report = generate_report(*args)
        assert GATE in report

    def test_report_has_research_only_verdict(self):
        args = self._make_full_data()
        report = generate_report(*args)
        assert VERDICT_RESEARCH_ONLY in report
        assert VERDICT_DO_NOT_PROMOTE in report

    def test_report_has_all_sections(self):
        args = self._make_full_data()
        report = generate_report(*args)
        assert "Per-Alpha Vector Features" in report
        assert "## 2. Fold IC Vectors" in report
        assert "## 3. Pairwise Correlation Matrix" in report
        assert "## 4. Cluster Summary" in report
        assert "## 5. Redundant Clusters" in report
        assert "## 6. Complementary Research Candidates" in report
        assert "## 7. Research-Only Verdict" in report
        assert "## 8. Safety and Compliance" in report

    def test_report_no_promotion_language(self):
        args = self._make_full_data()
        report = generate_report(*args)
        report_lower = report.lower()
        # Must NOT claim any alpha was promoted or selected as winner
        assert "we promote" not in report_lower
        assert "selected as winner" not in report_lower
        # But the safety note saying "No alpha is promoted" is allowed
        assert "no alpha is promoted" in report_lower

    def test_report_contains_alpha_names(self):
        args = self._make_full_data()
        report = generate_report(*args)
        assert "alpha_a" in report
        assert "alpha_b" in report
        assert "alpha_c" in report

    def test_report_safety_section(self):
        args = self._make_full_data()
        report = generate_report(*args)
        assert "deterministic" in report.lower()
        assert "no look-ahead" in report.lower() or "PIT" in report


# ---------------------------------------------------------------------------
# Test JSON summary
# ---------------------------------------------------------------------------

class TestBuildJsonSummary:
    def test_summary_structure(self):
        data = _make_phase35_data()
        alpha_fold_ics = extract_alpha_fold_ics(data)
        portfolio_ics = extract_fold_portfolio_ics(data)
        vectors = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        redundant = identify_redundant_clusters(labels, corr)
        complementary = identify_complementary_candidates(labels, vectors, corr)

        summary = build_json_summary(
            data, alpha_fold_ics, vectors, corr, labels, redundant, complementary
        )

        assert summary["gate"] == GATE
        assert VERDICT_RESEARCH_ONLY in summary["verdict"]
        assert VERDICT_DO_NOT_PROMOTE in summary["verdict"]
        assert "alpha_vectors" in summary
        assert "pairwise_correlations" in summary
        assert "cluster_labels" in summary
        assert "redundant_clusters" in summary
        assert "complementary_candidates" in summary

    def test_summary_json_serializable(self):
        data = _make_phase35_data()
        alpha_fold_ics = extract_alpha_fold_ics(data)
        portfolio_ics = extract_fold_portfolio_ics(data)
        vectors = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        redundant = identify_redundant_clusters(labels, corr)
        complementary = identify_complementary_candidates(labels, vectors, corr)

        summary = build_json_summary(
            data, alpha_fold_ics, vectors, corr, labels, redundant, complementary
        )
        json_str = json.dumps(summary)
        assert len(json_str) > 0

    def test_summary_has_fold_vectors(self):
        data = _make_phase35_data()
        alpha_fold_ics = extract_alpha_fold_ics(data)
        portfolio_ics = extract_fold_portfolio_ics(data)
        vectors = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        redundant = identify_redundant_clusters(labels, corr)
        complementary = identify_complementary_candidates(labels, vectors, corr)

        summary = build_json_summary(
            data, alpha_fold_ics, vectors, corr, labels, redundant, complementary
        )
        for alpha_name, alpha_data in summary["alpha_vectors"].items():
            assert "fold_ic_vector" in alpha_data
            assert "cluster_id" in alpha_data
            assert "mean_ic" in alpha_data
            assert "icir" in alpha_data
            # Expanded features
            assert "min_ic" in alpha_data
            assert "max_ic" in alpha_data
            assert "ic_skew" in alpha_data
            assert "mean_abs_corr" in alpha_data
            assert "redundancy_count" in alpha_data

    def test_summary_research_only(self):
        """JSON summary verdict must be RESEARCH_ONLY / DO_NOT_PROMOTE."""
        data = _make_phase35_data()
        alpha_fold_ics = extract_alpha_fold_ics(data)
        portfolio_ics = extract_fold_portfolio_ics(data)
        vectors = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        redundant = identify_redundant_clusters(labels, corr)
        complementary = identify_complementary_candidates(labels, vectors, corr)

        summary = build_json_summary(
            data, alpha_fold_ics, vectors, corr, labels, redundant, complementary
        )
        assert "DO_NOT_PROMOTE" in summary["verdict"]
        assert "RESEARCH_ONLY" in summary["verdict"]


# ---------------------------------------------------------------------------
# Test CLI (main)
# ---------------------------------------------------------------------------

class TestMainCLI:
    def test_end_to_end(self, tmp_path):
        data = _make_phase35_data()
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(data))
        output_report = tmp_path / "report.md"
        output_json = tmp_path / "summary.json"

        rc = main([
            "--input", str(input_file),
            "--output-report", str(output_report),
            "--output-json", str(output_json),
        ])
        assert rc == 0
        assert output_report.exists()
        assert output_json.exists()

        report_text = output_report.read_text(encoding="utf-8")
        assert "# Alpha Vector-Space Discovery Report" in report_text
        assert VERDICT_RESEARCH_ONLY in report_text
        assert VERDICT_DO_NOT_PROMOTE in report_text

        json_data = json.loads(output_json.read_text(encoding="utf-8"))
        assert json_data["gate"] == GATE

    def test_missing_input(self, tmp_path):
        rc = main([
            "--input", str(tmp_path / "nonexistent.json"),
            "--output-report", str(tmp_path / "report.md"),
            "--output-json", str(tmp_path / "summary.json"),
        ])
        assert rc == 1

    def test_empty_fold_details(self, tmp_path):
        data = {"config": {}, "fold_details": []}
        input_file = tmp_path / "empty.json"
        input_file.write_text(json.dumps(data))
        rc = main([
            "--input", str(input_file),
            "--output-report", str(tmp_path / "report.md"),
            "--output-json", str(tmp_path / "summary.json"),
        ])
        assert rc == 1  # No alpha IC data

    def test_custom_threshold(self, tmp_path):
        data = _make_phase35_data()
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(data))
        rc = main([
            "--input", str(input_file),
            "--output-report", str(tmp_path / "report.md"),
            "--output-json", str(tmp_path / "summary.json"),
            "--cluster-threshold", "0.99",
        ])
        assert rc == 0


# ---------------------------------------------------------------------------
# Test forbidden-path disclaimer
# ---------------------------------------------------------------------------

class TestForbiddenPathDisclaimer:
    def test_disclaimer_present(self):
        data = _make_phase35_data()
        alpha_fold_ics = extract_alpha_fold_ics(data)
        portfolio_ics = extract_fold_portfolio_ics(data)
        vectors = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        redundant = identify_redundant_clusters(labels, corr)
        complementary = identify_complementary_candidates(labels, vectors, corr)
        report = generate_report(
            data, alpha_fold_ics, vectors, corr, labels, redundant, complementary
        )
        assert "No authoritative reliance" in report
        assert "non-authoritative and not used as source" in report
        assert "antigravity-ide" in report.lower() or "antigravity" in report.lower()
        assert ".openclaw" in report.lower() or "openclaw" in report.lower()
        assert "C:\\Users\\GHC\\.agents" in report
        assert ".codex" in report.lower() or "codex" in report.lower()


# ---------------------------------------------------------------------------
# Test expanded vector dimensions (GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615)
# ---------------------------------------------------------------------------

class TestExpandedVectorDimensions:
    """Verify expanded ~35-40D scalar features per alpha."""

    def _make_full_vectors(self):
        alpha_fold_ics = {
            "alpha_a": [0.02, 0.03, 0.01, 0.04, -0.01, 0.02],
            "alpha_b": [0.01, -0.01, 0.02, -0.02, 0.03, -0.01],
            "alpha_c": [-0.03, -0.04, -0.02, -0.05, -0.01, -0.03],
        }
        portfolio_ics = [0.01, 0.02, -0.01, 0.03, 0.01, -0.02]
        sharpes = [0.5, 0.6, -0.3, 0.8, 0.4, -0.2]
        max_dds = [-0.05, -0.03, -0.15, -0.02, -0.04, -0.12]
        total_rets = [0.10, 0.15, -0.05, 0.20, 0.08, -0.10]
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        vectors = compute_alpha_vectors(
            alpha_fold_ics, portfolio_ics,
            portfolio_fold_sharpes=sharpes,
            portfolio_fold_max_dds=max_dds,
            portfolio_fold_total_returns=total_rets,
            corr_matrix=corr,
            cluster_labels=labels,
        )
        return vectors

    def test_expanded_features_present(self):
        vectors = self._make_full_vectors()
        va = vectors["alpha_a"]
        expanded_keys = [
            "min_ic", "max_ic", "downside_ic_mean", "ic_skew",
            "sharpe_association", "drawdown_association", "return_association",
            "mean_abs_corr", "redundancy_count", "cluster_centrality",
            "ic_range", "ic_median", "positive_ic_rate_above_threshold",
            "negative_fold_rate", "ic_momentum", "ic_stability",
            "worst_fold_ic", "best_fold_ic", "fold_ic_kurtosis",
            "ic_consistency_score", "ic_coefficient_of_variation",
            "fold_ic_autocorr", "ic_win_loss_ratio", "upside_ic_mean",
            "regime_bull_proxy_mean_ic", "regime_bear_proxy_mean_ic",
            "cross_alpha_mean_ic_deviation", "n_folds_available",
            "quarter_mean_1", "quarter_mean_2", "quarter_mean_3", "quarter_mean_4",
        ]
        for key in expanded_keys:
            assert key in va, f"Missing expanded feature: {key}"

    def test_dim_count_at_least_35(self):
        vectors = self._make_full_vectors()
        va = next(iter(vectors.values()))
        dim_count = _count_scalar_features(va)
        assert dim_count >= 35, f"Expected >= 35 scalar features, got {dim_count}"

    def test_dim_count_deterministic(self):
        v1 = self._make_full_vectors()
        v2 = self._make_full_vectors()
        d1 = _count_scalar_features(next(iter(v1.values())))
        d2 = _count_scalar_features(next(iter(v2.values())))
        assert d1 == d2

    def test_min_max_ic(self):
        vectors = self._make_full_vectors()
        va = vectors["alpha_a"]
        ics = [0.02, 0.03, 0.01, 0.04, -0.01, 0.02]
        assert abs(va["min_ic"] - min(ics)) < 1e-10
        assert abs(va["max_ic"] - max(ics)) < 1e-10
        assert abs(va["ic_range"] - (max(ics) - min(ics))) < 1e-10

    def test_downside_upside_ic(self):
        vectors = self._make_full_vectors()
        va = vectors["alpha_a"]
        neg_ics = [-0.01]
        pos_ics = [0.02, 0.03, 0.01, 0.04, 0.02]
        assert abs(va["downside_ic_mean"] - (sum(neg_ics) / len(neg_ics))) < 1e-10
        assert abs(va["upside_ic_mean"] - (sum(pos_ics) / len(pos_ics))) < 1e-10

    def test_negative_fold_rate(self):
        vectors = self._make_full_vectors()
        va = vectors["alpha_a"]
        # alpha_a has 1 negative out of 6 folds
        assert abs(va["negative_fold_rate"] - 1.0 / 6.0) < 1e-10

    def test_ic_stability_non_negative(self):
        vectors = self._make_full_vectors()
        for name, v in vectors.items():
            assert v["ic_stability"] >= 0.0

    def test_consistency_score_range(self):
        vectors = self._make_full_vectors()
        for name, v in vectors.items():
            assert 0.0 <= v["ic_consistency_score"] <= 1.0

    def test_sharpe_association_nonzero(self):
        vectors = self._make_full_vectors()
        va = vectors["alpha_a"]
        assert isinstance(va["sharpe_association"], float)

    def test_mean_abs_corr_non_negative(self):
        vectors = self._make_full_vectors()
        for name, v in vectors.items():
            assert v["mean_abs_corr"] >= 0.0

    def test_n_folds_available(self):
        vectors = self._make_full_vectors()
        va = vectors["alpha_a"]
        assert va["n_folds_available"] == 6

    def test_quarter_means_exist(self):
        vectors = self._make_full_vectors()
        va = vectors["alpha_a"]
        assert "quarter_mean_1" in va
        assert "quarter_mean_2" in va
        assert "quarter_mean_3" in va
        assert "quarter_mean_4" in va

    def test_json_summary_has_vector_dim_count(self):
        data = _make_phase35_data()
        alpha_fold_ics = extract_alpha_fold_ics(data)
        portfolio_ics = extract_fold_portfolio_ics(data)
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        vectors = compute_alpha_vectors(alpha_fold_ics, portfolio_ics, corr_matrix=corr, cluster_labels=labels)
        redundant = identify_redundant_clusters(labels, corr)
        complementary = identify_complementary_candidates(labels, vectors, corr)
        summary = build_json_summary(data, alpha_fold_ics, vectors, corr, labels, redundant, complementary)
        assert "vector_dim_count" in summary
        assert summary["vector_dim_count"] >= 35

    def test_safe_median(self):
        assert _safe_median([3, 1, 2]) == 2.0
        assert _safe_median([4, 1, 3, 2]) == 2.5
        assert _safe_median([]) == 0.0

    def test_safe_skew(self):
        result = _safe_skew([1, 2, 3, 4, 5])
        assert isinstance(result, float)

    def test_extract_fold_sharpes(self):
        data = _make_phase35_data()
        sharpes = extract_fold_sharpes(data)
        assert len(sharpes) == 4
        assert isinstance(sharpes[0], float)


# ---------------------------------------------------------------------------
# Integration: real data (skip if unavailable)
# ---------------------------------------------------------------------------

class TestIntegration:
    REAL_FILE = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "phase35_results"
        / "phase35_backtest_results_dd_control_10_default_clean_v3_wg_baseline.json"
    )

    @pytest.fixture(autouse=True)
    def _skip_if_no_data(self):
        if not self.REAL_FILE.is_file():
            pytest.skip("Real Phase 3.5 data file not found")

    def test_real_data_loads(self):
        data = load_phase35_json(str(self.REAL_FILE))
        assert "fold_details" in data
        assert len(data["fold_details"]) > 0

    def test_real_analysis_runs(self):
        data = load_phase35_json(str(self.REAL_FILE))
        alpha_fold_ics = extract_alpha_fold_ics(data)
        portfolio_ics = extract_fold_portfolio_ics(data)
        assert len(alpha_fold_ics) > 0
        vectors = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        assert len(vectors) == len(alpha_fold_ics)

    def test_real_clustering(self):
        data = load_phase35_json(str(self.REAL_FILE))
        alpha_fold_ics = extract_alpha_fold_ics(data)
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        assert len(labels) == len(alpha_fold_ics)
        assert all(isinstance(v, int) for v in labels.values())

    def test_real_report_generation(self, tmp_path):
        data = load_phase35_json(str(self.REAL_FILE))
        alpha_fold_ics = extract_alpha_fold_ics(data)
        portfolio_ics = extract_fold_portfolio_ics(data)
        vectors = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        redundant = identify_redundant_clusters(labels, corr)
        complementary = identify_complementary_candidates(labels, vectors, corr)
        report = generate_report(
            data, alpha_fold_ics, vectors, corr, labels, redundant, complementary
        )
        assert len(report) > 1000
        assert VERDICT_RESEARCH_ONLY in report

    def test_real_json_summary(self, tmp_path):
        data = load_phase35_json(str(self.REAL_FILE))
        alpha_fold_ics = extract_alpha_fold_ics(data)
        portfolio_ics = extract_fold_portfolio_ics(data)
        vectors = compute_alpha_vectors(alpha_fold_ics, portfolio_ics)
        corr = compute_pairwise_correlation(alpha_fold_ics)
        labels = correlation_distance_clustering(corr)
        redundant = identify_redundant_clusters(labels, corr)
        complementary = identify_complementary_candidates(labels, vectors, corr)
        summary = build_json_summary(
            data, alpha_fold_ics, vectors, corr, labels, redundant, complementary
        )
        json_str = json.dumps(summary, indent=2)
        assert len(json_str) > 500
