import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

from genetic_alpha_evolution_v3 import build_split_windows, compute_daily_cs_ic


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
