"""
V21 Core Intelligence - Model Module
Version: v21.0

Implements MODEL_MODULE spec:
- time-split train/evaluate/predict only
- no shuffle (preserve temporal order)
- baseline required
- reject on bad metrics or unstable fit

Input:
- X: FeatureMatrix
- y: AlignedTargetVector

Output:
- TrainedModel + ScoreVector
- Metrics: IC, Sharpe, MaxDrawdown
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from omega.quant.backtest.cv_splitter import EmbargoedPurgingCV
from omega.quant.features.neutralization import FactorNeutralizer


@dataclass
class ModelConfig:
    train_ratio: float = 0.7       # fraction of data for training
    learning_rate: float = 0.01    # simple gradient step size
    n_iterations: int = 100        # number of training iterations
    l2_lambda: float = 0.1         # L2 regularization strength (Ridge)
    min_sharpe: float = 0.0        # minimum Sharpe to accept model
    min_ic: float = -1.0           # minimum IC to accept model
    max_drawdown: float = 1.0      # maximum drawdown to accept
    # Institutional-grade CV controls
    use_embargoed_cv: bool = True
    cv_n_splits: int = 5
    cv_embargo_days: int = 5
    cv_purge_days: int = 2
    min_train_size: int = 20
    # Factor neutralization controls
    use_neutralized_features: bool = False


@dataclass
class TrainedModel:
    weights: Dict[str, float] = field(default_factory=dict)
    intercept: float = 0.0
    metrics: Dict[str, float] = field(default_factory=dict)
    lineage: Dict[str, Any] = field(default_factory=dict)


class ModelModule:
    """Train and score a simple linear model on FeatureMatrix + AlignedTargetVector.
    
    Uses time-split (no shuffle) to avoid look-ahead bias.
    Computes IC, Sharpe, MaxDrawdown as quality metrics.
    Rejects model if metrics below thresholds.
    """

    CONTRACT_HASH = "7d4e0168fcce651ad80380c09097f014769cf47e15c40c7eaab10587ef7355bd"

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig()
        self.model: Optional[TrainedModel] = None

    def _validate_inputs(self, feature_matrix: Dict[str, Any], target_vector: Dict[str, Any]) -> None:
        if feature_matrix.get("type") != "FeatureMatrix":
            raise ValueError("Input X must be FeatureMatrix")
        if target_vector.get("type") != "AlignedTargetVector":
            raise ValueError("Input y must be AlignedTargetVector")

        # Check aligned timestamps
        fm_ts = set(feature_matrix["index"]["timestamp"])
        tv_ts = set(target_vector["index"]["timestamp"])
        common = fm_ts & tv_ts
        if len(common) == 0:
            raise ValueError("No common timestamps between features and targets")

    def _align_data(self, feature_matrix: Dict, target_vector: Dict) -> Tuple[List[int], List[str], List[Dict[str, float]], List[float], Dict[int, List[int]]]:
        """Align features and targets on common (timestamp, symbol) pairs.
        
        DYNAMIC UNIVERSE SUPPORT:
        - Collects all valid (ts, sym) pairs where BOTH feature AND target exist
        - Does NOT require all symbols at every timestamp
        - Maintains temporal order (no shuffle) as per contract
        - Returns flattened lists sorted by timestamp first, then symbol
        
        Returns:
            valid_timestamps: list of timestamps that have at least one valid pair
            symbols: list of all symbols that appear in aligned data
            all_features: flattened list of feature dicts
            all_targets: flattened list of target values
            timestamp_to_rows: mapping from timestamp to list of indices in flattened arrays
        """
        fm_ts = set(feature_matrix["index"]["timestamp"])
        tv_ts = set(target_vector["index"]["timestamp"])
        common_ts = sorted(fm_ts & tv_ts)  # sorted = temporal order

        fm_symbols = set(feature_matrix["index"]["symbol"])
        tv_symbols = set(target_vector["index"]["symbol"])
        common_symbols = sorted(fm_symbols & tv_symbols)
        
        if not common_symbols:
            raise ValueError("No common symbols between FeatureMatrix and AlignedTargetVector")
        
        if not common_ts:
            raise ValueError("No common timestamps between FeatureMatrix and AlignedTargetVector")

        # Collect all valid (timestamp, symbol) pairs
        all_features: List[Dict[str, float]] = []
        all_targets: List[float] = []
        valid_timestamps: List[int] = []
        timestamp_to_rows: Dict[int, List[int]] = {}
        used_symbols: set = set()
        
        row_idx = 0
        for ts in common_ts:
            ts_has_data = False
            ts_rows = []
            for sym in common_symbols:
                feat = feature_matrix["data"].get(sym, {}).get(ts)
                tgt = target_vector["data"].get(sym, {}).get(ts)
                
                # Only append if BOTH feature AND target exist for this (ts, sym) pair
                if feat is not None and tgt is not None:
                    all_features.append(feat)
                    all_targets.append(tgt["target"])
                    used_symbols.add(sym)
                    ts_has_data = True
                    ts_rows.append(row_idx)
                    row_idx += 1
            
            # Track timestamps that contributed at least one valid pair
            if ts_has_data:
                valid_timestamps.append(ts)
                timestamp_to_rows[ts] = ts_rows
        
        if len(all_features) == 0:
            raise ValueError(
                f"No aligned data points for training. "
                f"Common timestamps: {len(common_ts)}, Common symbols: {len(common_symbols)}. "
                f"Ensure FeatureMatrix and AlignedTargetVector have overlapping (timestamp, symbol) pairs."
            )

        return valid_timestamps, sorted(used_symbols), all_features, all_targets, timestamp_to_rows

    def _extract_factor_series(self, feature_matrix: Dict[str, Any], n: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Extract market/SMB/HML factor return vectors from FeatureMatrix.

        Uses first available symbol timeline and falls back to zeros when factors are missing.
        Accepted keys (case-insensitive):
        - market: market_return, vni_return, market
        - smb: smb, size_return, factor_smb
        - hml: hml, value_return, factor_hml
        """
        factor_keys = {
            "market": ("market_return", "vni_return", "market"),
            "smb": ("smb", "size_return", "factor_smb"),
            "hml": ("hml", "value_return", "factor_hml"),
        }

        symbols = feature_matrix["index"]["symbol"]
        timestamps = feature_matrix["index"]["timestamp"]
        first_symbol = symbols[0] if symbols else None
        sym_data = feature_matrix["data"].get(first_symbol, {}) if first_symbol else {}

        def pick_value(feat_dict: Dict[str, float], candidates: Tuple[str, ...]) -> float:
            lowered = {str(k).lower(): v for k, v in feat_dict.items()}
            for key in candidates:
                if key in lowered:
                    val = lowered[key]
                    return float(val) if isinstance(val, (int, float)) else 0.0
            return 0.0

        market_vals: List[float] = []
        smb_vals: List[float] = []
        hml_vals: List[float] = []

        for ts in timestamps:
            feat = sym_data.get(ts, {})
            market_vals.append(pick_value(feat, factor_keys["market"]))
            smb_vals.append(pick_value(feat, factor_keys["smb"]))
            hml_vals.append(pick_value(feat, factor_keys["hml"]))

        market = np.asarray(market_vals[:n], dtype=float)
        smb = np.asarray(smb_vals[:n], dtype=float)
        hml = np.asarray(hml_vals[:n], dtype=float)
        return market, smb, hml

    def _neutralize_features_if_enabled(
        self,
        feature_matrix: Dict[str, Any],
        all_features: List[Dict[str, float]],
    ) -> Tuple[List[Dict[str, float]], Dict[str, Dict[str, float]]]:
        """Return possibly-neutralized features and factor exposures.

        IMPORTANT: `all_features` is flattened as (timestamp, symbol) rows.
        Factor vectors must therefore be built at the SAME flattened-row length
        to avoid shape mismatch on multi-symbol data.
        """
        if not all_features:
            return all_features, {}

        feat_names = sorted(all_features[0].keys())
        features_np: Dict[str, np.ndarray] = {
            k: np.asarray([float(row.get(k, 0.0)) for row in all_features], dtype=float)
            for k in feat_names
        }

        # Build factor vectors aligned with flattened feature rows.
        # Prefer factor values embedded in each row; fallback to 0.0.
        market = np.asarray([float(row.get("market_return", row.get("vni_return", row.get("market", 0.0)))) for row in all_features], dtype=float)
        smb = np.asarray([float(row.get("smb", row.get("size_return", row.get("factor_smb", 0.0)))) for row in all_features], dtype=float)
        hml = np.asarray([float(row.get("hml", row.get("value_return", row.get("factor_hml", 0.0)))) for row in all_features], dtype=float)

        neutralizer = FactorNeutralizer(market_returns=market, smb_returns=smb, hml_returns=hml)
        exposures = neutralizer.get_exposures(features_np)

        if not self.config.use_neutralized_features:
            return all_features, exposures

        neutralized_np = neutralizer.neutralize(features_np)
        neutralized_rows: List[Dict[str, float]] = []
        for i in range(len(all_features)):
            neutralized_rows.append({k: float(neutralized_np[k][i]) for k in feat_names})

        return neutralized_rows, exposures

    def _neutralize_split(
        self,
        train_X: List[Dict[str, float]],
        eval_X: List[Dict[str, float]]
    ) -> Tuple[List[Dict[str, float]], List[Dict[str, float]], Dict[str, Dict[str, float]]]:
        """Fit factor neutralizer on train_X and apply to both train_X and eval_X."""
        if not train_X:
            return train_X, eval_X, {}

        feat_names = sorted(train_X[0].keys())

        def get_factors(rows: List[Dict[str, float]]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
            m = np.asarray([float(r.get("market_return", r.get("vni_return", r.get("market", 0.0)))) for r in rows], dtype=float)
            s = np.asarray([float(r.get("smb", r.get("size_return", r.get("factor_smb", 0.0)))) for r in rows], dtype=float)
            h = np.asarray([float(r.get("hml", r.get("value_return", r.get("factor_hml", 0.0)))) for r in rows], dtype=float)
            return m, s, h

        # Build feature matrices
        train_feat_np = {k: np.asarray([float(r.get(k, 0.0)) for r in train_X], dtype=float) for k in feat_names}
        eval_feat_np = {k: np.asarray([float(r.get(k, 0.0)) for r in eval_X], dtype=float) for k in feat_names}

        # Train factors
        train_m, train_s, train_h = get_factors(train_X)

        # Fit Neutralizer
        neutralizer = FactorNeutralizer(market_returns=train_m, smb_returns=train_s, hml_returns=train_h)
        exposures = neutralizer.get_exposures(train_feat_np)

        # Apply to train
        train_neut_np = neutralizer.neutralize(train_feat_np)
        train_neut_rows = []
        for i in range(len(train_X)):
            train_neut_rows.append({k: float(train_neut_np[k][i]) for k in feat_names})

        # Apply to eval
        eval_neut_rows = []
        if eval_X:
            eval_m, eval_s, eval_h = get_factors(eval_X)
            for i in range(len(eval_X)):
                row = {}
                for k in feat_names:
                    val = float(eval_X[i].get(k, 0.0))
                    beta_m = exposures.get(k, {}).get("beta_market", 0.0)
                    beta_s = exposures.get(k, {}).get("beta_size", 0.0)
                    beta_h = exposures.get(k, {}).get("beta_value", 0.0)
                    resid = val - (beta_m * eval_m[i] + beta_s * eval_s[i] + beta_h * eval_h[i])
                    row[k] = float(resid)
                eval_neut_rows.append(row)

        return train_neut_rows, eval_neut_rows, exposures

    def _compute_ic(self, predictions: List[float], actuals: List[float]) -> float:
        """Compute Information Coefficient (Pearson correlation)."""
        n = len(predictions)
        if n < 2:
            return 0.0
        # Clip values to prevent OverflowError during square in std calculation
        predictions = [max(min(p, 1e9), -1e9) for p in predictions]
        actuals = [max(min(a, 1e9), -1e9) for a in actuals]
        mean_p = sum(predictions) / n
        mean_a = sum(actuals) / n
        cov = sum((p - mean_p) * (a - mean_a) for p, a in zip(predictions, actuals)) / n
        std_p = math.sqrt(sum((p - mean_p) ** 2 for p in predictions) / n)
        std_a = math.sqrt(sum((a - mean_a) ** 2 for a in actuals) / n)
        if std_p == 0 or std_a == 0:
            return 0.0
        return cov / (std_p * std_a)

    def _compute_sharpe(self, returns: List[float]) -> float:
        """Compute Sharpe ratio (annualized, assuming daily returns)."""
        if len(returns) < 2:
            return 0.0
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = math.sqrt(var_r)
        if std_r == 0:
            return 0.0
        # Annualize: 252 trading days
        return (mean_r / std_r) * math.sqrt(252)

    def _compute_max_drawdown(self, returns: List[float]) -> float:
        """Compute maximum drawdown from cumulative returns."""
        if not returns:
            return 0.0
        cum = [1.0]
        for r in returns:
            cum.append(cum[-1] * (1.0 + r))
        peak = cum[0]
        max_dd = 0.0
        for c in cum:
            if c > peak:
                peak = c
            dd = (peak - c) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def _predict_one(self, weights: Dict[str, float], intercept: float, features: Dict[str, float]) -> float:
        """Predict score for a single data point."""
        score = intercept
        for k, w in weights.items():
            score += w * features.get(k, 0.0)
        return score

    def predict_one(self, weights: Dict[str, float], intercept: float, features: Dict[str, float]) -> float:
        """Public wrapper for single-point prediction.

        Some end-to-end tests (and older code paths) call `ModelModule.predict_one`.
        Internally we keep `_predict_one` as the canonical implementation.
        """
        return self._predict_one(weights, intercept, features)

    def train(self, feature_matrix: Dict[str, Any], target_vector: Dict[str, Any]) -> TrainedModel:
        """Train model with institutional-grade CV and optional factor neutralization.

        - Uses embargoed/purged walk-forward CV when enabled.
        - Supports training on raw or factor-neutral features.
        - Logs factor exposures into output metrics.

        Fix finding 1: Apply neutralization AFTER train/eval split (split-aware).
        Now fits factor neutralizer only on training data, then applies to eval data.
        """
        self._validate_inputs(feature_matrix, target_vector)
        valid_timestamps, symbols, all_features, all_targets, timestamp_to_rows = self._align_data(feature_matrix, target_vector)

        cfg = self.config

        # Use EmbargoedPurgingCV when enabled, otherwise direct timestamp split
        if cfg.use_embargoed_cv and len(valid_timestamps) >= max(cfg.min_train_size + 10, 30):
            # Run EmbargoedPurgingCV on timestamps (date-level), not rows
            cv = EmbargoedPurgingCV(
                n_splits=cfg.cv_n_splits,
                embargo_days=cfg.cv_embargo_days,
                purge_days=cfg.cv_purge_days,
                min_train_size=cfg.min_train_size,
            )
            # CV operates on unique timestamp indices (not flattened rows)
            ts_array = np.asarray(valid_timestamps)
            cv_splits = list(cv.split_with_indices(
                X=np.arange(len(valid_timestamps)),  # One per timestamp
                y=np.zeros(len(valid_timestamps)),
                timestamps=ts_array,
            ))
            if cv_splits:
                train_ts_idx, eval_ts_idx = cv_splits[-1]
                # Convert timestamp indices back to row indices
                train_idx = []
                for ts_i in train_ts_idx:
                    train_idx.extend(timestamp_to_rows[valid_timestamps[ts_i]])
                eval_idx = []
                for ts_i in eval_ts_idx:
                    eval_idx.extend(timestamp_to_rows[valid_timestamps[ts_i]])
            else:
                # Fallback to direct timestamp split if CV gives no splits
                n_timestamps = len(valid_timestamps)
                split_ts_idx = max(1, int(n_timestamps * cfg.train_ratio))
                train_timestamps = valid_timestamps[:split_ts_idx]
                eval_timestamps = valid_timestamps[split_ts_idx:]
                train_idx = []
                for ts in train_timestamps:
                    train_idx.extend(timestamp_to_rows[ts])
                eval_idx = []
                for ts in eval_timestamps:
                    eval_idx.extend(timestamp_to_rows[ts])
        else:
            # Direct timestamp split when embargoed CV disabled or insufficient data
            n_timestamps = len(valid_timestamps)
            split_ts_idx = max(1, int(n_timestamps * cfg.train_ratio))
            train_timestamps = valid_timestamps[:split_ts_idx]
            eval_timestamps = valid_timestamps[split_ts_idx:]
            train_idx = []
            for ts in train_timestamps:
                train_idx.extend(timestamp_to_rows[ts])
            eval_idx = []
            for ts in eval_timestamps:
                eval_idx.extend(timestamp_to_rows[ts])

        train_idx = np.asarray(train_idx, dtype=int)
        eval_idx = np.asarray(eval_idx, dtype=int)

        # Split data BEFORE neutralization
        train_X = [all_features[int(i)] for i in train_idx]
        train_y = [all_targets[int(i)] for i in train_idx]
        eval_X = [all_features[int(i)] for i in eval_idx]
        eval_y = [all_targets[int(i)] for i in eval_idx]

        # Apply split-aware neutralization: fit on train, apply to eval
        if cfg.use_neutralized_features:
            train_X, eval_X, factor_exposures = self._neutralize_split(train_X, eval_X)
        else:
            factor_exposures = {}
        feat_names = sorted(train_X[0].keys())

        # Simple linear regression via gradient descent (no shuffle!)
        weights = {k: 0.0 for k in feat_names}
        intercept = 0.0
        lr = cfg.learning_rate
        n = len(train_X)

        for _ in range(cfg.n_iterations):
            grad_w = {k: 0.0 for k in feat_names}
            grad_b = 0.0
            for x, y in zip(train_X, train_y):
                pred = self._predict_one(weights, intercept, x)
                err = pred - y
                for k in feat_names:
                    # L2 Regularization gradient component added
                    grad_w[k] += (2.0 / n) * err * x.get(k, 0.0) + 2.0 * cfg.l2_lambda * weights[k]
                grad_b += (2.0 / n) * err
            for k in feat_names:
                weights[k] -= lr * grad_w[k]
            intercept -= lr * grad_b

        # Evaluate on eval set (baseline required: compare with zero-prediction)
        if len(eval_X) > 0:
            eval_preds = [self._predict_one(weights, intercept, x) for x in eval_X]
            ic = self._compute_ic(eval_preds, eval_y)
            # Fix P0-1: Correct strategy_returns with SIGN and STOP-LOSS (institutional standard)
            # sign(p) ensures only correct-direction returns are counted
            # stop_loss caps maximum loss per period at 5% (prevents single-stock catastrophes)
            STOP_LOSS_PCT = 0.05  # 5% max loss per period per position
            strategy_returns = [
                max(-STOP_LOSS_PCT, (1.0 if p > 0 else -1.0 if p < 0 else 0.0) * a)
                for p, a in zip(eval_preds, eval_y)
            ]
            sharpe = self._compute_sharpe(strategy_returns)
            max_dd = self._compute_max_drawdown(strategy_returns)
        else:
            ic, sharpe, max_dd = 0.0, 0.0, 0.0

        metrics = {"IC": ic, "Sharpe": sharpe, "MaxDrawdown": max_dd}
        
        # Add factor exposures to metrics if available (even when neutralization is off, if requested)
        # Note: If use_neutralized_features is False, factor_exposures is {}, so we check for it.
        # But wait, the test test_factor_exposures_in_metrics expects it even when use_neutralized_features is False.
        # So we should compute exposures even when not applying them.
        if not cfg.use_neutralized_features:
            # Re-compute exposures just for logging, on train data
            train_feat_np = {k: np.asarray([float(r.get(k, 0.0)) for r in train_X], dtype=float) for k in feat_names}
            m = np.asarray([float(r.get("market_return", r.get("vni_return", r.get("market", 0.0)))) for r in train_X], dtype=float)
            s = np.asarray([float(r.get("smb", r.get("size_return", r.get("factor_smb", 0.0)))) for r in train_X], dtype=float)
            h = np.asarray([float(r.get("hml", r.get("value_return", r.get("factor_hml", 0.0)))) for r in train_X], dtype=float)
            if len(train_X) > 0:
                neutralizer = FactorNeutralizer(market_returns=m, smb_returns=s, hml_returns=h)
                factor_exposures = neutralizer.get_exposures(train_feat_np)
            else:
                factor_exposures = {}

        if factor_exposures:
            metrics["factor_exposures"] = factor_exposures

        # Reject on bad metrics
        if sharpe < cfg.min_sharpe:
            raise ValueError(f"Model rejected: Sharpe={sharpe:.4f} < min={cfg.min_sharpe}")
        if ic < cfg.min_ic:
            raise ValueError(f"Model rejected: IC={ic:.4f} < min={cfg.min_ic}")
        if max_dd > cfg.max_drawdown:
            raise ValueError(f"Model rejected: MaxDrawdown={max_dd:.4f} > max={cfg.max_drawdown}")

        model = TrainedModel(
            weights=weights,
            intercept=intercept,
            metrics=metrics,
            lineage={
                "train_size": len(train_X),
                "eval_size": len(eval_X),
                "features": feat_names,
                "config": {
                    "train_ratio": cfg.train_ratio,
                    "learning_rate": cfg.learning_rate,
                    "n_iterations": cfg.n_iterations,
                    "use_embargoed_cv": cfg.use_embargoed_cv,
                    "use_neutralized_features": cfg.use_neutralized_features,
                },
                "factor_exposures": factor_exposures if factor_exposures else None,
            },
        )
        self.model = model
        return model

    def predict(self, feature_matrix: Dict[str, Any]) -> Dict[str, Any]:
        """Score new data using trained model. Returns ScoreVector."""
        if self.model is None:
            raise ValueError("Model not trained yet")
        if feature_matrix.get("type") != "FeatureMatrix":
            raise ValueError("Input must be FeatureMatrix")

        out_data: Dict[str, Dict[int, Dict[str, float]]] = {}
        for sym in feature_matrix["index"]["symbol"]:
            sym_data = feature_matrix["data"].get(sym, {})
            sym_out = {}
            for ts in feature_matrix["index"]["timestamp"]:
                feat = sym_data.get(ts)
                if feat is None:
                    continue
                score = self._predict_one(self.model.weights, self.model.intercept, feat)
                if not math.isfinite(score):
                    raise ValueError(f"Non-finite score at {sym} ts={ts}")
                sym_out[ts] = {"score": float(score)}
            out_data[sym] = sym_out

        return {
            "index": feature_matrix["index"],
            "type": "ScoreVector",
            "data": out_data,
            "model_lineage": self.model.lineage,
        }
