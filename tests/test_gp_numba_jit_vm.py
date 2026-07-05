import os
import sys

import numpy as np
import pandas as pd
import pytest

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
