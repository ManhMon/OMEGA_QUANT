"""
OMEGA_QUANT Optuna Parameter Tuner
Tunes hyperparameters on TRAIN period only to avoid overfitting.

Safe params to tune:
- Ridge alpha (0.01-100)
- HRP lookback (20-120 days)
- Corr threshold (0.3-0.7)
- Regime MA short/long (20-100 / 100-300)
- Number of signals (5-30)

NOT tuned (fixed by market reality / L2/L3 consensus):
- Slippage, turnover cap, max weight, IC threshold

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Optimization uses TRAIN period only. VAL/TEST untouched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TunedParams:
    """Optimized parameters from Optuna."""
    ridge_alpha: float = 1.0
    hrp_lookback: int = 60
    corr_threshold: float = 0.5
    regime_ma_short: int = 50
    regime_ma_long: int = 200
    n_signals: int = 20
    objective_value: float = 0.0
    n_trials: int = 0


class OptunaParamTuner:
    """
    Tune hyperparameters using Optuna on TRAIN period.
    Objective: maximize Sharpe ratio of walk-forward backtest on TRAIN.
    """

    def __init__(self, n_trials: int = 30, n_jobs: int = 1):
        self.n_trials = n_trials
        self.n_jobs = n_jobs
        self.best_params: Optional[TunedParams] = None

    def _objective(self, trial, train_panel: pd.DataFrame, features: List[str]):
        """Optuna objective: Sharpe on TRAIN walk-forward."""
        import optuna

        # Sample hyperparameters
        ridge_alpha = trial.suggest_float('ridge_alpha', 0.01, 100.0, log=True)
        hrp_lookback = trial.suggest_int('hrp_lookback', 20, 120, step=10)
        corr_threshold = trial.suggest_float('corr_threshold', 0.3, 0.7, step=0.05)
        regime_ma_short = trial.suggest_int('regime_ma_short', 20, 100, step=10)
        regime_ma_long = trial.suggest_int('regime_ma_long', 100, 300, step=20)
        n_signals = trial.suggest_int('n_signals', 5, 30, step=5)

        try:
            # Split TRAIN into sub-train (70%) and sub-val (30%) for internal CV
            dates = train_panel.index.get_level_values('date').unique().sort_values()
            split_idx = int(len(dates) * 0.7)
            sub_train_dates = dates[:split_idx]
            sub_val_dates = dates[split_idx:]

            sub_train = train_panel.loc[train_panel.index.get_level_values('date').isin(sub_train_dates)]
            sub_val = train_panel.loc[train_panel.index.get_level_values('date').isin(sub_val_dates)]

            # Screen features on sub_val
            target_col = 'fwd_ret_5'
            sub_val_h = sub_val.copy()
            sub_val_h[target_col] = sub_val_h.groupby(level='symbol')['close'].pct_change(5).shift(-5)
            sub_val_h = sub_val_h.dropna(subset=[target_col])

            screened = []
            for feat in features:
                if feat not in sub_val_h.columns:
                    continue
                try:
                    sig = sub_val_h[feat].groupby(level='symbol').shift(1)
                    if sig.std() < 1e-8:
                        continue
                    ic = sig.corr(sub_val_h[target_col], method='spearman')
                    if not np.isnan(ic) and abs(ic) >= 0.03:
                        screened.append({'feature': feat, 'ic': float(ic), 'abs_ic': abs(float(ic))})
                except Exception:
                    continue

            screened.sort(key=lambda x: x['abs_ic'], reverse=True)

            # Orthogonality filter with trial corr_threshold
            accepted = []
            accepted_sigs = {}
            for sa in screened:
                feat = sa['feature']
                try:
                    sig = sub_val_h[feat].groupby(level='symbol').shift(1)
                    if sig.std() < 1e-8:
                        continue
                    is_diverse = True
                    for _, esig in accepted_sigs.items():
                        common = sig.index.intersection(esig.index)
                        if len(common) > 50 and abs(sig.loc[common].corr(esig.loc[common])) > corr_threshold:
                            is_diverse = False
                            break
                    if is_diverse:
                        accepted.append(sa)
                        accepted_sigs[feat] = sig
                        if len(accepted) >= n_signals:
                            break
                except Exception:
                    continue

            if len(accepted) < 3:
                return -999.0

            # Train Ridge on sub_train
            from sklearn.linear_model import Ridge
            sub_train_h = sub_train.copy()
            sub_train_h[target_col] = sub_train_h.groupby(level='symbol')['close'].pct_change(5).shift(-5)
            sub_train_h = sub_train_h.dropna(subset=[target_col])

            feat_names = [a['feature'] for a in accepted if a['feature'] in sub_train_h.columns]
            if len(feat_names) < 3:
                return -999.0

            X = sub_train_h[feat_names].replace([np.inf, -np.inf], np.nan).fillna(0)
            y = sub_train_h[target_col].replace([np.inf, -np.inf], np.nan).fillna(0)

            model = Ridge(alpha=ridge_alpha)
            model.fit(X.values, y.values)

            # Predict on sub_val
            X_val = sub_val_h[feat_names].replace([np.inf, -np.inf], np.nan).fillna(0)
            preds = model.predict(X_val.values)
            pred_series = pd.Series(preds, index=sub_val_h.index)
            pred_lagged = pred_series.groupby(level='symbol').shift(1).fillna(0)

            # Compute Sharpe from signal
            target = sub_val_h[target_col]
            # Signal-weighted return
            signal_ret = pred_lagged * target
            daily_ret = signal_ret.groupby(level='date').mean()
            if daily_ret.std() < 1e-8:
                return -999.0

            sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252)
            return float(sharpe)

        except Exception:
            return -999.0

    def tune(
        self,
        train_panel: pd.DataFrame,
        features: List[str],
    ) -> TunedParams:
        """
        Run Optuna optimization on TRAIN period.

        Args:
            train_panel: TRAIN data with features already generated
            features: List of feature names

        Returns:
            TunedParams with best hyperparameters.
        """
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        logger.info("=== OPTUNA TUNING: %d trials on TRAIN ===", self.n_trials)

        study = optuna.create_study(direction='maximize', study_name='omega_param_tune')
        study.optimize(
            lambda trial: self._objective(trial, train_panel, features),
            n_trials=self.n_trials,
            n_jobs=self.n_jobs,
            show_progress_bar=False,
        )

        best = study.best_params
        self.best_params = TunedParams(
            ridge_alpha=best.get('ridge_alpha', 1.0),
            hrp_lookback=best.get('hrp_lookback', 60),
            corr_threshold=best.get('corr_threshold', 0.5),
            regime_ma_short=best.get('regime_ma_short', 50),
            regime_ma_long=best.get('regime_ma_long', 200),
            n_signals=best.get('n_signals', 20),
            objective_value=study.best_value,
            n_trials=self.n_trials,
        )

        logger.info("Best Sharpe on TRAIN: %.4f", study.best_value)
        logger.info("Best params: ridge=%.3f, hrp_lb=%d, corr=%.2f, ma=%d/%d, n_sig=%d",
                    self.best_params.ridge_alpha, self.best_params.hrp_lookback,
                    self.best_params.corr_threshold, self.best_params.regime_ma_short,
                    self.best_params.regime_ma_long, self.best_params.n_signals)

        return self.best_params
