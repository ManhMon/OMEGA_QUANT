import pytest
import pandas as pd
import numpy as np
from spike_alpha_discovery import AlphaDiscoveryEngine

def test_enforce_t1_lag():
    engine = AlphaDiscoveryEngine()
    df = pd.DataFrame({
        'date': pd.date_range('2023-01-01', periods=3).tolist() * 2,
        'ticker': ['A']*3 + ['B']*3,
        'feat1': [10, 20, 30, 100, 200, 300]
    })
    res = engine.enforce_t1_lag(df, ['feat1'])
    assert pd.isna(res.iloc[0]['feat1'])
    assert res.iloc[1]['feat1'] == 10
    assert pd.isna(res.iloc[3]['feat1'])
    assert res.iloc[4]['feat1'] == 100

def test_score_signals():
    engine = AlphaDiscoveryEngine()
    df = pd.DataFrame({
        'date': ['2023-01-01']*2,
        'ticker': ['A', 'B'],
        'feat1': [10, 30]
    })
    res = engine.score_signals(df, ['feat1'])
    assert 'feat1_score' in res.columns
    assert res.loc[0, 'feat1_score'] < 0
    assert res.loc[1, 'feat1_score'] > 0

def test_track_decay():
    engine = AlphaDiscoveryEngine(decay_half_life=1)
    df = pd.DataFrame({
        'date': pd.date_range('2023-01-01', periods=4),
        'ticker': ['A']*4,
        'feat1_score': [1.0, 0.0, 0.0, 0.0]
    })
    res = engine.track_decay(df, 'feat1_score')
    assert 'feat1_score_decayed' in res.columns
    vals = res['feat1_score_decayed'].values
    assert vals[0] == 1.0
    assert vals[1] < vals[0]
