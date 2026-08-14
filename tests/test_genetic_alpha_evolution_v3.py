import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

from genetic_alpha_evolution_v3 import (
    build_vn_trading_days,
    build_split_windows,
    compute_daily_cs_ic,
    evaluate_ensemble,
    select_ensemble,
)
from omega.data.calendar import VNTradingCalendar


def test_compute_daily_cs_ic_uses_daily_cross_sections():
    dates = np.array([1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2])
    signal = np.array([1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], dtype=float)
    target = np.array([1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], dtype=float)
    assert compute_daily_cs_ic(signal, target, dates) == 0.0


def test_build_split_windows_preserves_embargo_and_lockbox():
    dates = list(pd.date_range('2020-01-01', periods=900, freq='B'))
    windows = build_split_windows(dates)
    assert windows['train'][1] < windows['val'][0]
    assert windows['val'][1] < windows['oos'][0]
    assert windows['oos'][1] < windows['lockbox'][0]


def test_gate4_split_boundaries_are_trading_session_dates():
    dates = list(pd.date_range('2020-01-01', periods=900, freq='B'))
    windows = build_split_windows(dates)
    calendar = build_vn_trading_days(dates[0], dates[-1])

    assert all(boundary in calendar for window in windows.values() for boundary in window)
    assert VNTradingCalendar.is_valid_trading_timestamp(datetime(2020, 1, 2, 14, 45))
    assert not VNTradingCalendar.is_valid_trading_timestamp(datetime(2020, 1, 2, 14, 46))


def test_gate4_calendar_excludes_vietnam_holiday_from_split_calendar():
    calendar = build_vn_trading_days(pd.Timestamp('2024-04-29'), pd.Timestamp('2024-05-02'))

    assert pd.Timestamp('2024-04-29') in calendar
    assert pd.Timestamp('2024-04-30') not in calendar
    assert pd.Timestamp('2024-05-01') not in calendar
    assert pd.Timestamp('2024-05-02') in calendar


def test_select_ensemble_filters_high_corr_and_shrinks_weights_to_equal():
    candidates = [
        {
            'id': 'a',
            'val_IC_daily': 0.05,
            'val_signal': np.array([1, 2, 3, 4, 5, 6], dtype=float),
            'oos_signal': np.zeros(6, dtype=float),
            'lockbox_signal': np.zeros(6, dtype=float),
        },
        {
            'id': 'b',
            'val_IC_daily': 0.04,
            'val_signal': np.array([2, 4, 6, 8, 10, 12], dtype=float),
            'oos_signal': np.zeros(6, dtype=float),
            'lockbox_signal': np.zeros(6, dtype=float),
        },
        {
            'id': 'c',
            'val_IC_daily': 0.03,
            'val_signal': np.array([1, 6, 2, 5, 3, 4], dtype=float),
            'oos_signal': np.zeros(6, dtype=float),
            'lockbox_signal': np.zeros(6, dtype=float),
        },
    ]

    selected, weights = select_ensemble(candidates, val_ic_threshold=0.015, max_corr=0.6, max_alphas=10)

    assert [candidate['id'] for candidate in selected] == ['a', 'c']
    np.testing.assert_allclose(weights.sum(), 1.0)
    np.testing.assert_allclose(weights, np.array([0.5625, 0.4375]))


def test_select_ensemble_skips_nan_corr_pair_and_keeps_candidate():
    candidates = [
        {
            'id': 'a',
            'val_IC_daily': 0.05,
            'val_signal': np.array([1, 2, 3, 4, 5, 6], dtype=float),
            'oos_signal': np.zeros(6, dtype=float),
            'lockbox_signal': np.zeros(6, dtype=float),
        },
        {
            'id': 'b',
            'val_IC_daily': 0.04,
            'val_signal': np.ones(6, dtype=float),
            'oos_signal': np.zeros(6, dtype=float),
            'lockbox_signal': np.zeros(6, dtype=float),
        },
    ]

    selected, weights = select_ensemble(candidates, val_ic_threshold=0.015, max_corr=0.6, max_alphas=10)

    assert [candidate['id'] for candidate in selected] == ['a', 'b']
    np.testing.assert_allclose(weights.sum(), 1.0)


def test_evaluate_ensemble_reports_oos_and_lockbox_only():
    selected = [
        {
            'id': 'a',
            'val_IC_daily': 0.05,
            'val_signal': np.zeros(12, dtype=float),
            'oos_signal': np.array([1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], dtype=float),
            'lockbox_signal': np.array([6, 5, 4, 3, 2, 1, 6, 5, 4, 3, 2, 1], dtype=float),
        },
        {
            'id': 'b',
            'val_IC_daily': 0.03,
            'val_signal': np.zeros(12, dtype=float),
            'oos_signal': np.array([6, 5, 4, 3, 2, 1, 6, 5, 4, 3, 2, 1], dtype=float),
            'lockbox_signal': np.array([1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], dtype=float),
        },
    ]
    weights = np.array([0.75, 0.25], dtype=float)
    dates = np.array([1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2])
    target_up = np.array([1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], dtype=float)
    target_down = np.array([6, 5, 4, 3, 2, 1, 6, 5, 4, 3, 2, 1], dtype=float)

    metrics = evaluate_ensemble(
        selected=selected,
        weights=weights,
        oos_target=target_up,
        lockbox_target=target_down,
        oos_dates=dates,
        lockbox_dates=dates,
    )

    assert metrics['oos_IC_daily'] == 1.0
    assert metrics['lockbox_IC_daily'] == 1.0
