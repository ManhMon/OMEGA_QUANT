import pandas as pd
import numpy as np

class AlphaDiscoveryEngine:
    def __init__(self, decay_half_life: int = 5):
        self.decay_half_life = decay_half_life

    def enforce_t1_lag(self, df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
        df = df.copy()
        if 'ticker' not in df.columns or 'date' not in df.columns:
            raise ValueError("Require 'ticker' and 'date' columns")
        df = df.sort_values(['ticker', 'date'])
        df[feature_cols] = df.groupby('ticker')[feature_cols].shift(1)
        return df

    def score_signals(self, df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
        df = df.copy()
        for col in feature_cols:
            mean = df.groupby('date')[col].transform('mean')
            std = df.groupby('date')[col].transform('std')
            df[f'{col}_score'] = (df[col] - mean) / std.replace(0, np.nan)
        return df

    def track_decay(self, df: pd.DataFrame, score_col: str) -> pd.DataFrame:
        df = df.copy()
        df = df.sort_values(['ticker', 'date'])
        df[f'{score_col}_decayed'] = df.groupby('ticker')[score_col].transform(
            lambda x: x.ewm(halflife=self.decay_half_life, ignore_na=False).mean()
        )
        return df

    def run_pipeline(self, df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
        df = self.enforce_t1_lag(df, feature_cols)
        df = self.score_signals(df, feature_cols)
        for col in feature_cols:
            df = self.track_decay(df, f'{col}_score')
        return df
