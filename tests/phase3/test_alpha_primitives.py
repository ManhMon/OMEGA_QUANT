import pytest
import numpy as np
import pandas as pd
from omega.quant.alpha_primitives import (
    calculate_ic, calculate_rank_ic, calculate_turnover,
    calculate_sharpe, calculate_max_drawdown
)

def test_calculate_ic():
    s = pd.Series([1, 2, 3, 4])
    l = pd.Series([2, 4, 6, 8])
    assert np.isclose(calculate_ic(s, l), 1.0)

def test_calculate_ic_nans():
    s = pd.Series([1, np.nan, 3])
    l = pd.Series([2, 4, 6])
    assert np.isclose(calculate_ic(s, l), 1.0)

def test_calculate_ic_single_pair():
    s = pd.Series([1.0])
    l = pd.Series([2.0])
    assert np.isnan(calculate_ic(s, l))

def test_calculate_rank_ic():
    s = pd.Series([10, 20, 30])
    l = pd.Series([100, 50, 200])
    assert np.isclose(calculate_rank_ic(s, l), 0.5)

def test_calculate_rank_ic_empty():
    s = pd.Series([np.nan, np.nan])
    l = pd.Series([1, 2])
    assert np.isnan(calculate_rank_ic(s, l))

def test_calculate_turnover_same():
    w1 = pd.Series([0.5, 0.5], index=['A', 'B'])
    w2 = pd.Series([0.5, 0.5], index=['A', 'B'])
    assert calculate_turnover(w1, w2) == 0.0

def test_calculate_turnover_diff():
    w1 = pd.Series([0.6, 0.4], index=['A', 'B'])
    w2 = pd.Series([0.4, 0.6], index=['A', 'B'])
    assert np.isclose(calculate_turnover(w1, w2), 0.2)

def test_calculate_turnover_new_assets():
    w1 = pd.Series([1.0], index=['A'])
    w2 = pd.Series([1.0], index=['B'])
    assert np.isclose(calculate_turnover(w1, w2), 1.0)

def test_calculate_sharpe():
    rets = pd.Series([0.01, 0.02, -0.01, 0.01, 0.00])
    val = calculate_sharpe(rets)
    assert val > 0

def test_calculate_sharpe_zero_std():
    rets = pd.Series([0.01, 0.01, 0.01])
    assert np.isnan(calculate_sharpe(rets))

def test_calculate_max_drawdown():
    rets = pd.Series([0.1, -0.1, -0.1, 0.2])
    val = calculate_max_drawdown(rets)
    assert np.isclose(val, (0.891 - 1.1) / 1.1)

def test_calculate_max_drawdown_first_negative():
    rets = pd.Series([-0.1, 0.2])
    val = calculate_max_drawdown(rets)
    assert np.isclose(val, -0.1)
