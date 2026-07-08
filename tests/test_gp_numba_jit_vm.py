import os
import sys

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import genetic_alpha_evolution_v4 as v4
from omega.quant.evolution import genetic_engine as ge


def _make_panel_features() -> dict[str, np.ndarray]:
    tickers = np.array(["AAA", "AAA", "AAA", "BBB", "BBB", "BBB"], dtype=object)
    dates = pd.to_datetime(
        [
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
        ]
    ).to_numpy()
    return {
        "returns_1d": np.array([1.0, 3.0, 9.0, 10.0, 20.0, 40.0]),
        "returns_5d": np.array([4.0, 2.0, 1.0, 7.0, 8.0, 9.0]),
        "hl_range": np.array([2.0, np.nan, 6.0, 1.0, 5.0, 7.0]),
        "__ticker__": tickers,
        "__date__": dates,
    }


def _run_python(tree: ge.GPNode, features: dict[str, np.ndarray]) -> np.ndarray:
    return v4.ORIGINAL_GPINDIVIDUAL(tree=tree)._execute_tree(tree, dict(features))


def _run_vm(tree: ge.GPNode, features: dict[str, np.ndarray]) -> np.ndarray:
    return ge.GPIndividual(tree=tree)._execute_tree(tree, dict(features))


def test_compile_tree_to_rpn_and_vm_match_python_parity():
    features = _make_panel_features()
    features.pop("__ticker__")
    tree = ge.GPNode(
        operator="max",
        children=[
            ge.GPNode(
                operator="log",
                children=[
                    ge.GPNode(
                        operator="/",
                        children=[
                            ge.GPNode(operator="terminal", value="returns_1d"),
                            ge.GPNode(operator="terminal", value="2.0"),
                        ],
                    )
                ],
            ),
            ge.GPNode(
                operator="neg",
                children=[
                    ge.GPNode(
                        operator="abs",
                        children=[ge.GPNode(operator="terminal", value="returns_5d")],
                    )
                ],
            ),
        ],
    )

    program = v4._compile_tree_to_rpn(tree, ["returns_1d", "returns_5d", "hl_range"])
    assert program is not None

    expected = _run_python(tree, features)
    actual = _run_vm(tree, features)
    np.testing.assert_allclose(actual, expected, equal_nan=True)


def test_ts_kernel_respects_ticker_boundaries_and_short_windows_zero_fill():
    features = _make_panel_features()
    tree = ge.GPNode(
        operator="ts_mean",
        children=[
            ge.GPNode(operator="terminal", value="returns_1d"),
            ge.GPNode(operator="terminal", value="2"),
        ],
    )

    actual = _run_vm(tree, features)
    expected = np.array([0.0, 2.0, 6.0, 0.0, 15.0, 30.0])
    np.testing.assert_allclose(actual, expected)


def test_cross_sectional_kernel_respects_date_groups_only():
    features = _make_panel_features()
    tree = ge.GPNode(operator="cs_rank", children=[ge.GPNode(operator="terminal", value="returns_1d")])

    actual = _run_vm(tree, features)
    expected = np.array([0.5, 0.5, 0.5, 1.0, 1.0, 1.0])
    np.testing.assert_allclose(actual, expected)


def test_ts_std_does_not_leak_across_tickers_when_nan_present():
    features = _make_panel_features()
    tree = ge.GPNode(
        operator="ts_std",
        children=[
            ge.GPNode(operator="terminal", value="hl_range"),
            ge.GPNode(operator="terminal", value="2"),
        ],
    )

    actual = _run_vm(tree, features)
    expected = np.array([0.0, 0.0, 0.0, 0.0, np.sqrt(8.0), np.sqrt(2.0)])
    np.testing.assert_allclose(actual, expected, equal_nan=True)


def test_row_order_contract_rejects_unsorted_ticker_date_input():
    features = _make_panel_features()
    features["__ticker__"] = np.array(["AAA", "AAA", "BBB", "BBB", "AAA", "BBB"], dtype=object)
    tree = ge.GPNode(operator="terminal", value="returns_1d")

    with pytest.raises(ValueError, match="row-order contract"):
        ge.GPIndividual(tree=tree)._execute_tree(tree, features)


def _make_neutralization_features() -> dict[str, np.ndarray]:
    dates = pd.to_datetime(
        [
            "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02",
            "2024-01-03", "2024-01-03", "2024-01-03", "2024-01-03",
        ]
    ).to_numpy()
    return {
        "__date__": dates,
        "__log_market_cap__": np.array([1.0, 1.5, 2.0, 2.5, 4.0, 4.5, 5.0, 5.5], dtype=np.float64),
        "__sector__": np.array(["A", "A", "B", "B", "A", "A", "B", "B"], dtype=object),
        "returns_1d": np.array([0.4, 0.7, 1.2, 1.6, 5.0, 5.0, 9.0, 9.0], dtype=np.float64),
    }


def _ridge_expected(alpha: np.ndarray, features: dict[str, np.ndarray]) -> np.ndarray:
    expected = np.asarray(alpha, dtype=np.float64).copy()
    for current_date in pd.unique(features["__date__"]):
        mask = features["__date__"] == current_date
        if np.count_nonzero(mask) < 2:
            continue
        log_mcap = features["__log_market_cap__"][mask]
        sector = features["__sector__"][mask]
        y = expected[mask]
        valid = np.isfinite(log_mcap) & pd.notna(sector) & np.isfinite(y)
        if np.count_nonzero(valid) < 2:
            continue
        sector_dummies = pd.get_dummies(pd.Series(sector[valid]), dtype=float)
        design = np.column_stack([
            np.ones(np.count_nonzero(valid), dtype=np.float64),
            log_mcap[valid],
            sector_dummies.to_numpy()[:, 1:] if sector_dummies.shape[1] > 1 else np.empty((np.count_nonzero(valid), 0)),
        ])
        model = Ridge(alpha=1e-6, fit_intercept=False)
        model.fit(design, y[valid])
        fitted = model.predict(design)
        y_valid = y[valid] - fitted
        y_valid[np.abs(y_valid) < 1e-12] = 0.0
        y[valid] = y_valid
        expected[mask] = y
    return expected


def _build_cache_with_jit(features: dict[str, np.ndarray]) -> dict:
    features = dict(features)
    features[ge.NEUTRALIZATION_CACHE_KEY] = ge._build_neutralization_cache(
        np.asarray(features["__log_market_cap__"], dtype=np.float64),
        np.asarray(features["__sector__"]),
        np.asarray(features["__date__"]),
    )
    v4._get_vm_context(features)
    return features[ge.NEUTRALIZATION_CACHE_KEY]


def test_jit_neutralization_matches_sklearn_ridge_by_date():
    features = _make_neutralization_features()
    alpha = features["returns_1d"]
    cache = _build_cache_with_jit(features)

    actual = v4._optimized_neutralize_cross_section(
        alpha,
        features["__log_market_cap__"],
        features["__sector__"],
        features["__date__"],
        neutralization_cache=cache,
    )
    expected = _ridge_expected(alpha, features)

    np.testing.assert_allclose(actual, expected, rtol=1e-8, atol=1e-8)


def test_jit_neutralization_handles_singular_design_with_ridge():
    features = _make_neutralization_features()
    features["__log_market_cap__"] = np.array([2.0, 2.0, 2.0, 2.0, 7.0, 7.0, 7.0, 7.0], dtype=np.float64)
    alpha = np.array([1.0, 1.0, 3.0, 3.0, 10.0, 10.0, 20.0, 20.0], dtype=np.float64)
    cache = _build_cache_with_jit(features)

    actual = v4._optimized_neutralize_cross_section(
        alpha,
        features["__log_market_cap__"],
        features["__sector__"],
        features["__date__"],
        neutralization_cache=cache,
    )

    assert np.all(np.isfinite(actual))
    np.testing.assert_allclose(actual, _ridge_expected(alpha, features), rtol=1e-8, atol=1e-8)


def test_jit_neutralization_small_n_and_all_nans_are_stable():
    features = _make_neutralization_features()
    features["__date__"] = pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-04"]).to_numpy()
    features["__log_market_cap__"] = np.array([1.0, 2.0, 3.0, np.nan], dtype=np.float64)
    features["__sector__"] = np.array(["A", "B", "A", None], dtype=object)
    features["returns_1d"] = np.array([5.0, 6.0, 7.0, np.nan], dtype=np.float64)
    alpha = np.array([5.0, 6.0, 7.0, np.nan], dtype=np.float64)
    cache = _build_cache_with_jit(features)

    actual = v4._optimized_neutralize_cross_section(
        alpha,
        features["__log_market_cap__"],
        features["__sector__"],
        features["__date__"],
        neutralization_cache=cache,
    )

    np.testing.assert_allclose(actual, _ridge_expected(alpha, features), rtol=1e-8, atol=1e-8)
    assert actual[2] == 7.0
    assert np.isnan(actual[3])


def test_jit_batch_neutralization_matches_columnwise_and_isolates_dates():
    features = _make_neutralization_features()
    alpha_matrix = np.column_stack(
        [
            features["returns_1d"],
            np.array([100.0, 100.0, 200.0, 200.0, -1.0, -1.0, -2.0, -2.0], dtype=np.float64),
        ]
    )
    cache = _build_cache_with_jit(features)

    batch_actual = v4._optimized_batch_neutralize_cross_section(alpha_matrix, features["__date__"], cache)
    col0 = v4._optimized_neutralize_cross_section(
        alpha_matrix[:, 0],
        features["__log_market_cap__"],
        features["__sector__"],
        features["__date__"],
        neutralization_cache=cache,
    )
    col1 = v4._optimized_neutralize_cross_section(
        alpha_matrix[:, 1],
        features["__log_market_cap__"],
        features["__sector__"],
        features["__date__"],
        neutralization_cache=cache,
    )

    np.testing.assert_allclose(batch_actual[:, 0], col0, rtol=1e-8, atol=1e-8)
    np.testing.assert_allclose(batch_actual[:, 1], col1, rtol=1e-8, atol=1e-8)
    np.testing.assert_allclose(batch_actual[:4, 0], _ridge_expected(alpha_matrix[:, 0], features)[:4], rtol=1e-8, atol=1e-8)
    np.testing.assert_allclose(batch_actual[4:, 0], _ridge_expected(alpha_matrix[:, 0], features)[4:], rtol=1e-8, atol=1e-8)


def test_jit_batch_neutralization_uses_slow_path_for_nan_candidates_only():
    features = _make_neutralization_features()
    alpha_matrix = np.column_stack(
        [
            features["returns_1d"],
            np.array([100.0, np.nan, 200.0, 200.0, -1.0, -1.0, -2.0, -2.0], dtype=np.float64),
        ]
    )
    cache = _build_cache_with_jit(features)

    batch_actual = v4._optimized_batch_neutralize_cross_section(alpha_matrix, features["__date__"], cache)
    col0 = v4._optimized_neutralize_cross_section(
        alpha_matrix[:, 0],
        features["__log_market_cap__"],
        features["__sector__"],
        features["__date__"],
        neutralization_cache=cache,
    )
    col1 = v4._optimized_neutralize_cross_section(
        alpha_matrix[:, 1],
        features["__log_market_cap__"],
        features["__sector__"],
        features["__date__"],
        neutralization_cache=cache,
    )

    np.testing.assert_allclose(batch_actual[:, 0], col0, rtol=1e-8, atol=1e-8)
    np.testing.assert_allclose(batch_actual[:, 1], col1, rtol=1e-8, atol=1e-8, equal_nan=True)
