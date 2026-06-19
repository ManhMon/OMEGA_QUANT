---
name: ml-dl-rl
description: ML/DL/RL for OMEGA_QUANT time-series and portfolio optimization. Tree-based models (XGBoost/LightGBM/CatBoost), LSTM, autoencoder, PPO reinforcement learning. Leakage prevention, validation protocols, feature stores, RL environment and reward design.
when_to_use: "When building, training, evaluating, or deploying machine learning, deep learning, or reinforcement learning models for alpha prediction, portfolio optimization, or regime detection in OMEGA_QUANT."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# ML/DL/RL — OMEGA_QUANT Model Engineering

> Domain skill for machine learning, deep learning, and reinforcement learning in quant trading.
> **Leakage prevention is the #1 ML principle. Chronological validation is the #1 evaluation protocol.**

---

## 1. Model Architecture Overview

### OMEGA_QUANT Model Stack

| Category | Models | Primary Use |
|----------|--------|-------------|
| **Tree-based ML** | XGBoost (Regressor + Ranker), LightGBM, CatBoost, RandomForest | Cross-sectional alpha prediction |
| **Deep Learning** | LSTM (single-layer), MLP Autoencoder (LatentEncoder) | Time-series features, unsupervised representation |
| **Reinforcement Learning** | PPO Actor-Critic (RLPortfolioAgent) | Portfolio weight optimization |
| **Ensemble** | Voting, Stacking, XGBoost Ranker ensemble | Multi-model combination |
| **Hyperparameter** | Optuna (TPESampler + MedianPruner) | Bayesian hyperparameter search |
| **Experiment tracking** | MLflow | Run tracking, model registry |

---

## 2. Leakage Prevention — Critical

### Types of Leakage in Quant ML

| Leakage Type | Example | Prevention |
|-------------|---------|------------|
| **Look-ahead** | Feature uses T data, label is T+1 return | T-1 shift all features |
| **Label leakage** | Feature correlated with label through future info | Verify feature `available_at` < label `as_of` |
| **Survivorship** | Train only on currently listed stocks | Use PIT universe including delistings |
| **Normalization leakage** | Z-score computed on full sample | Compute statistics on train window only |
| **Feature selection leakage** | Feature importance evaluated on test set | Feature selection inside CV fold only |
| **Preprocessing leakage** | Imputation uses future values | Impute using only past data |

### Leakage Prevention Checklist

- [ ] All features shifted T-1 minimum (`enforce_t_minus_1_lag()`)
- [ ] Normalization parameters (mean, std) computed on TRAIN only
- [ ] Feature selection performed INSIDE each CV fold
- [ ] No future data used in imputation or interpolation
- [ ] Label horizon does not overlap with feature computation window
- [ ] `_validate_chronological_split()` passes — blocks random shuffles
- [ ] Cross-validation uses embargo between train and test

### The Golden Rule

```
At time T, the model can ONLY use:
  - Features computed from data with available_at <= T
  - Parameters fitted on data with available_at <= T
  - Labels from returns realized BEFORE T (for training only)
```

---

## 3. Tree-Based Models

### XGBoost

| Aspect | OMEGA_QUANT Configuration |
|--------|---------------------------|
| **Regressor** | `XGBRegressor` — scalar alpha prediction |
| **Ranker** | `XGBRanker` with `objective=rank:pairwise` — cross-sectional ranking |
| **DMatrix API** | `xgb.DMatrix(X, label=y)` for efficient training |
| **Early stopping** | `eval_set=[(X_val, y_val)]`, `early_stopping_rounds=50` |
| **Feature importance** | Gain-based importance (not weight-based) |
| **Determinism** | `seed=42`, `tree_method='hist'` for reproducibility |

### LightGBM

| Aspect | Configuration |
|--------|--------------|
| **Regressor** | `LGBMRegressor` — alternative to XGBoost |
| **Booster API** | `lgb.train()` with early stopping |
| **Importance** | Gain-based importance |
| **Categorical** | Native categorical feature support |

### CatBoost

| Aspect | Configuration |
|--------|--------------|
| **Regressor** | `CatBoostRegressor` — handles categorical features natively |
| **Graceful fallback** | Used when XGBoost/LightGBM fail to converge |

### ML Engine (`src/omega/ml/ml_engine.py`)

| Feature | Implementation |
|---------|---------------|
| **Walk-forward training** | Chronological split validation |
| **IC-based evaluation** | Rank IC computed per-fold |
| **Model comparison** | XGBoost vs LightGBM vs CatBoost per-fold |
| **Feature importance** | Aggregated across folds |

---

## 4. Deep Learning Models

### LSTM Alpha Model (`src/omega/models/lstm_alpha.py`)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Architecture** | Single-layer LSTM → mean-pool → linear head → scalar | Simple, avoids overfitting |
| **Lookback** | 60 days | ~3 months of context |
| **Hidden size** | 64 | Moderate capacity |
| **Epochs** | 8 | Short training to prevent overfitting |
| **Batch size** | 512 | Efficient GPU utilization |
| **Determinism** | `torch.manual_seed()`, `use_deterministic_algorithms=True` | Reproducibility |

### Latent Encoder (`src/omega/models/latent_encoder.py`)

| Parameter | Value | Purpose |
|-----------|-------|---------|
| **Architecture** | MLP Autoencoder (input → 128 → 16 → 128 → output) | Unsupervised feature extraction |
| **Latent dim** | 16 | Compressed representation |
| **Hidden dim** | 128 | Encoder/decoder width |
| **Training** | Reconstruction loss (MSE) | Learn market structure |

### Deep Learning Verification

- [ ] Deterministic seeds set (`torch.manual_seed`, `numpy.random.seed`)
- [ ] `torch.use_deterministic_algorithms(True)` enabled
- [ ] Lookback window does not extend into future
- [ ] Batch normalization statistics from train set only
- [ ] Dropout active during training, disabled during evaluation
- [ ] Model checkpoint based on validation loss, not training loss

---

## 5. Reinforcement Learning

### PPO Portfolio Agent (`src/omega/strategy/rl_agent.py`)

| Component | Design |
|-----------|--------|
| **Architecture** | Actor-Critic with shared trunk (input → 128 → 64 → actor/critic heads) |
| **Action space** | Softmax output → long-only portfolio weights (sum to 1.0) |
| **Observation** | Market state features (returns, volumes, indicators, regime) |
| **PPO** | Clipped advantages, value function baseline |
| **Reward** | Configurable: Sharpe, Sortino, or raw return minus transaction cost penalty |

### RL Environment Design Principles

| Principle | OMEGA_QUANT Implementation |
|-----------|---------------------------|
| **State** | PIT-safe observation (only past data available) |
| **Action** | Portfolio weight vector (softmax, long-only) |
| **Reward** | Risk-adjusted return NET of transaction costs |
| **Transition** | Step forward 1 day, observe new state |
| **Termination** | End of backtest period or max drawdown trigger |

### Reward Function Pitfalls

| Pitfall | Consequence | Fix |
|---------|------------|-----|
| **Reward without cost** | Agent trades excessively | Subtract transaction cost from reward |
| **Reward = raw return** | Agent ignores risk | Use Sharpe or Sortino reward |
| **Reward too sparse** | Agent can't learn | Use step-wise reward, not terminal-only |
| **Reward hacking** | Agent finds degenerate strategy | Add regularization (turnover penalty, drawdown penalty) |
| **No regime awareness** | Agent fails in regime shifts | Include regime state in observation |

### RL Training Protocol

| Step | Action |
|------|--------|
| **1. Environment** | Initialize with historical data, PIT-safe observations |
| **2. Warm-up** | Run random policy to verify environment mechanics |
| **3. Training** | PPO with clipped advantages, multiple epochs |
| **4. Validation** | Evaluate on held-out period (chronological) |
| **5. Robustness** | Test across regimes (bull/bear/sideways) |
| **6. Cost check** | Verify net-of-cost performance |

### RL Verification

- [ ] Observation space is PIT-safe (no future data)
- [ ] Reward includes transaction cost penalty
- [ ] Action space produces valid portfolio weights (sum ≈ 1.0, all >= 0)
- [ ] Training uses chronological data (no random episode sampling from future)
- [ ] Evaluation on held-out period not used in training
- [ ] Performance reported net of all costs
- [ ] Turnover is within acceptable bounds (< 30% daily)

---

## 6. Validation Protocols

### Chronological Cross-Validation (MANDATORY)

```python
# CORRECT: Chronological split
train_end = train_start + train_window
val_start = train_end + embargo
val_end = val_start + val_window
test_start = val_end + embargo

# WRONG: Random split
X_train, X_test = train_test_split(X, y, test_size=0.2)  # LEAKAGE!
```

### Walk-Forward Protocol

| Parameter | Value |
|-----------|-------|
| Train window | 252 days |
| Validation window | 63 days |
| Step | 21 days |
| Embargo | 3 days |
| Minimum folds | 12 |

### CPCV Protocol

| Parameter | Value |
|-----------|-------|
| Groups (N) | 10 |
| Test groups (k) | 2 |
| Folds | C(10,2) = 45 |
| Purge | Bidirectional |
| Embargo | ~5% of samples |

### Validation Verification

- [ ] `_validate_chronological_split()` passes
- [ ] No temporal overlap between train/val/test
- [ ] Embargo >= label horizon
- [ ] Model parameters fixed before test evaluation
- [ ] Feature selection inside each fold (not global)
- [ ] Normalization statistics from train only

---

## 7. Feature Store Principles

### Feature Categories

| Category | Examples | PIT Consideration |
|----------|----------|-------------------|
| **Price-based** | Returns, RSI, MACD, Bollinger | Must use T-1 prices |
| **Volume-based** | VWAP, volume ratio, turnover | Must use T-1 volumes |
| **Cross-sectional** | Rank, demean, z-score | Computed per-day cross-section |
| **Statistical** | Rolling mean, std, skew, kurtosis | Rolling window must not include future |
| **Regime** | HMM state, volatility regime | Regime detection uses only past data |
| **Alternative** | Smart money, market structure | Verify data availability timestamp |

### Feature Engineering Rules

| Rule | Detail |
|------|--------|
| **Vectorized** | All computations use pandas/numpy vectorized ops |
| **T-1 shifted** | Every feature output shifted minimum 1 period |
| **No NaN leakage** | NaN from shift is NOT forward-filled |
| **Documented** | Every feature has docstring with PIT safety note |
| **Tested** | Unit test verifies no future data access |

---

## 8. Ensemble Methods

### OMEGA_QUANT Ensemble Stack

| Method | Description | Use Case |
|--------|-------------|----------|
| **Voting** | Majority direction vote | Simple, robust |
| **Stacking** | Meta-learner on base model outputs | Capture non-linear combination |
| **XGBoost Ranker** | Pairwise ranking ensemble | Cross-sectional alpha combination |
| **IC-weighted** | Weight by rolling IC | Adaptive to signal quality |

### Ensemble Verification

- [ ] Base models trained independently (no shared test data)
- [ ] Meta-learner trained on validation set, not test set
- [ ] Ensemble evaluated on held-out OOS period
- [ ] Ensemble Sharpe > best individual model Sharpe (otherwise use individual)

---

## 9. Hyperparameter Optimization

### Optuna Configuration

| Parameter | Value |
|-----------|-------|
| **Sampler** | `TPESampler` (Bayesian) |
| **Pruner** | `MedianPruner` (early stopping) |
| **Direction** | `maximize` (Sharpe or IC) |
| **N trials** | 100-500 |
| **CV inside trial** | Walk-forward CV per trial |

### Hyperopt Verification

- [ ] Each trial uses walk-forward CV (not full-sample)
- [ ] Best hyperparameters evaluated on held-out test
- [ ] No hyperparameter search on test data
- [ ] Optuna study persisted for reproducibility

---

## 10. Experiment Tracking (MLflow)

| Tracked Item | Purpose |
|-------------|---------|
| **Parameters** | Model hyperparameters, data config |
| **Metrics** | IC, IR, Sharpe, max_drawdown per fold |
| **Artifacts** | Model checkpoints, feature importance plots |
| **Tags** | Regime, universe, date range |

---

## 11. Anti-Patterns

| Don't | Do |
|-------|-----|
| Random train/test split on time-series | Chronological split with embargo |
| Normalize on full dataset | Normalize on train window only |
| Select features on test set | Feature selection inside CV fold |
| Report training-set accuracy | Report OOS walk-forward metrics |
| Ignore transaction costs in RL reward | Subtract cost from every reward step |
| Use deep model for small dataset | Start with XGBoost, escalate if needed |
| Train RL on full history | Walk-forward RL training with OOS evaluation |
| Ignore regime in features | Include regime state as observation |
| Tune hyperparameters on test set | Optuna inside walk-forward CV folds |
| Forget deterministic seeds | Set torch.manual_seed + numpy seed + use_deterministic_algorithms |

---

## 12. SOD/PIT Guardrails

| Guardrail | Rule |
|-----------|------|
| **PIT: no leakage** | `enforce_t_minus_1_lag()` on all features; `_validate_chronological_split()` on all splits |
| **PIT: RL observations** | RL agent observes only data with `available_at <= current_time` |
| **SOD: model != deployer** | ML engineer (L2) builds model; cannot approve for live deployment |
| **SOD: Tier 3 audit** | ML code submitted to Code Reviewer (role 21) + QA Engineer (role 17) + Performance Tester (role 23) |
| **SOD: experiment log** | All MLflow runs persisted; results in `.ly_state/session/` |
| **Reproducibility** | All seeds set; deterministic execution; model checkpoints versioned |

---

> **Remember:** In quant ML, overfitting is the default outcome. Every design choice should fight leakage and overfitting.
