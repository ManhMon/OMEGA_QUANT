import sys
import os
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../packages/quant/src')))

from omega.quant.pit_guard import (
    validate_temporal_shift,
    detect_lookahead_leakage,
    enforce_t_minus_1_lag
)

def test_temporal_shift_valid():
    df = pd.DataFrame({
        'as_of': [datetime(2023,1,1), datetime(2023,1,2)],
        'available_at': [datetime(2023,1,2), datetime(2023,1,3)]
    })
    assert validate_temporal_shift(df, 'as_of', 'available_at') == True

def test_temporal_shift_invalid():
    df = pd.DataFrame({
        'as_of': [datetime(2023,1,3), datetime(2023,1,2)],
        'available_at': [datetime(2023,1,2), datetime(2023,1,3)]
    })
    with pytest.raises(ValueError):
        validate_temporal_shift(df, 'as_of', 'available_at')

def test_leakage_detection_true():
    idx = pd.date_range('2023-01-01', periods=3)
    features = pd.DataFrame({'f1': [1,2,3]}, index=idx)
    labels = pd.DataFrame({'l1': [4,5,6]}, index=idx)
    assert detect_lookahead_leakage(features, labels, 1) == True

def test_leakage_detection_false():
    idx_f = pd.date_range('2023-01-02', periods=3)
    idx_l = pd.date_range('2023-01-01', periods=3)
    features = pd.DataFrame({'f1': [1,2,3]}, index=idx_f)
    labels = pd.DataFrame({'l1': [4,5,6]}, index=idx_l)
    assert detect_lookahead_leakage(features, labels, 1) == False

def test_lag_enforcement_single_col():
    df = pd.DataFrame({'val': [10, 20, 30]})
    shifted = enforce_t_minus_1_lag(df, 1)
    assert pd.isna(shifted['val'].iloc[0])
    assert shifted['val'].iloc[1] == 10

def test_lag_enforcement_multi_col():
    df = pd.DataFrame({'a': [1,2], 'b': [3,4]})
    shifted = enforce_t_minus_1_lag(df, 1)
    assert shifted.isna().all().all() == False
    assert shifted['a'].iloc[1] == 1

def test_edge_cases_empty_df():
    df = pd.DataFrame()
    assert enforce_t_minus_1_lag(df).empty
    assert detect_lookahead_leakage(df, df, 1) == False
    assert validate_temporal_shift(df, 'a', 'b') == True

def test_edge_cases_missing_cols():
    df = pd.DataFrame({'a': [1]})
    with pytest.raises(KeyError):
        validate_temporal_shift(df, 'a', 'b')

def test_nat_null_handling():
    df = pd.DataFrame({
        'as_of': [datetime(2023,1,1), pd.NaT],
        'available_at': [pd.NaT, datetime(2023,1,3)]
    })
    # Since NaT > datetime is False and datetime > NaT is False,
    # validation should pass (or handle gracefully depending on pandas version)
    assert validate_temporal_shift(df, 'as_of', 'available_at') == True

def test_negative_lag_raises():
    df = pd.DataFrame({'val': [1, 2, 3]})
    with pytest.raises(ValueError, match="lag_days must be > 0"):
        enforce_t_minus_1_lag(df, lag_days=0)
    with pytest.raises(ValueError, match="lag_days must be > 0"):
        enforce_t_minus_1_lag(df, lag_days=-1)

def test_duplicate_index_leakage():
    idx = [datetime(2023,1,1), datetime(2023,1,1)]
    features = pd.DataFrame({'f': [1,2]}, index=idx)
    labels = pd.DataFrame({'l': [3,4]}, index=idx)
    assert detect_lookahead_leakage(features, labels, 1) == True

def test_explicit_t0_leakage():
    # Lengths are same, indices match exactly at position 1
    idx_f = pd.DatetimeIndex(['2023-01-01', '2023-01-02', '2023-01-03'])
    idx_l = pd.DatetimeIndex(['2023-01-01', '2023-01-02', '2023-01-03'])
    features = pd.DataFrame({'f': [1,2,3]}, index=idx_f)
    labels = pd.DataFrame({'l': [4,5,6]}, index=idx_l)
    assert detect_lookahead_leakage(features, labels, 1) == True

