---
name: quant-research
description: Factor/alpha research principles for OMEGA_QUANT Vietnam equity quant pipeline. IC/IR, turnover, capacity, neutralization, regime awareness, transaction-cost-aware alpha evaluation.
when_to_use: "When developing or evaluating alpha signals, factor models, cross-sectional or time-series strategies, genetic alpha evolution, or portfolio construction for Vietnam equities."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Quant Research — OMEGA_QUANT Alpha/Factor Pipeline

> Domain skill for quantitative alpha research on Vietnam equities (HOSE/HNX/UPCOM).
> **Principles first: every alpha must survive PIT safety, transaction costs, and regime changes.**

---

## 1. Alpha Lifecycle

```
Hypothesis → Feature Engineer → Signal Generate → PIT Validate → IC/IR Evaluate
    → Turnover/Cost Check → Neutralize → Regime Test → Walk-Forward OOS → Promote/Retire
```

### Decision Tree: Is This Alpha Worth Pursuing?

| Gate | Threshold | Action |
|------|-----------|--------|
| **IC mean** | > 0.02 (net of costs) | Proceed if passes |
| **IR (IC/sd(IC))** | > 0.5 | Strong signal |
| **Turnover** | < 30% daily (one-way) | Acceptable for VN market |
| **Capacity** | > 5B VND daily ADV | Must clear liquidity gate |
| **PIT-safe** | T-1 lag verified | Mandatory — no exceptions |
| **Cost-adjusted Sharpe** | > 0.5 after 27bps round-trip | Required for live |

---

## 2. IC / IR Metrics

### Information Coefficient (IC)

| Metric | Formula | OMEGA_QUANT Usage |
|--------|---------|-------------------|
| **Rank IC** | Spearman(signal_t, return_t+1) | Primary metric — robust to outliers |
| **Pearson IC** | Pearson(signal_t, return_t+1) | Secondary — sensitive to tails |
| **IC decay** | IC at T+1, T+3, T+5, T+10 | Assess signal half-life |

### Information Ratio (IR)

```
IR = mean(IC) / std(IC)
```

| IR Range | Quality |
|----------|---------|
| < 0.3 | Weak — likely noise |
| 0.3 - 0.5 | Marginal — needs ensemble |
| 0.5 - 1.0 | Good — candidate for live |
| > 1.0 | Excellent — verify no leakage |

### IC Evaluation Checklist

- [ ] IC computed on RANK (Spearman) not just Pearson
- [ ] IC computed per-day cross-sectionally, then averaged
- [ ] IC decay curve inspected (monotonic decay expected)
- [ ] IC stability across regimes (bull/bear/sideways)
- [ ] IC computed NET of estimated transaction costs

---

## 3. Turnover and Transaction Costs

### Vietnam Market Cost Model

| Cost Component | Rate | Notes |
|----------------|------|-------|
| **Commission** | 0.15% (one-way) | SSI broker standard |
| **Tax** | 0.10% (sell only) | Vietnam securities tax |
| **Slippage** | ~2 bps (one-way) | Market impact estimate |
| **Round-trip** | ~27 bps | Total estimated cost |

### Turnover Control Principles

| Principle | Implementation |
|-----------|---------------|
| **Measure turnover** | Sum(abs(weight_change)) per rebalance |
| **Penalize high turnover** | Fitness = Sharpe - 0.1 * Turnover (genetic alpha) |
| **Apply turnover caps** | Max 30% daily one-way turnover |
| **Use turnover buffers** | Only rebalance when signal delta > threshold |
| **Decay signals** | Smooth alpha weights to reduce churn |

### Cost-Adjusted Evaluation

```
net_IC = gross_IC - (turnover_per_rebalance * round_trip_cost)
net_Sharpe = gross_Sharpe - annualized_cost_drag
```

---

## 4. Capacity Analysis

### Vietnam Market Liquidity Constraints

| Factor | VN Market Reality |
|--------|-------------------|
| **ADV concentration** | Top 10 stocks ~ 60% of market ADV |
| **Mid/small cap** | Thin books, 100-share board lots |
| **Foreign room** | Some stocks at foreign ownership limit |
| **Ceiling/floor** | ±7% daily limits create liquidity traps |

### Capacity Estimation

```
max_AUM = min_over_universe(
    signal_weight[i] * ADV[i] * participation_rate
) / max_concentration
```

| Check | Threshold |
|-------|-----------|
| Participation rate | < 10% of ADV per name |
| Position count | 20-50 names for diversification |
| Max single-name weight | < 5% of portfolio |
| Sector concentration | < 25% in any one sector |

---

## 5. Neutralization

### Why Neutralize

Raw alpha signals often embed factor exposures (market beta, sector, size) that are NOT the intended alpha source. Neutralization isolates the pure signal.

### Neutralization Hierarchy

| Level | Neutralize Against | OMEGA_QUANT Module |
|-------|--------------------|--------------------|
| **Market** | Index return (VN-Index/VN30) | `core/feature_neutralizer.py` |
| **Sector** | ICB Level-2 sector returns | `data/sector_mapping_level2.csv` |
| **Style** | Size, value, momentum factors | `features/neutralization.py` |
| **Full** | All of the above | Cross-sectional regression residual |

### Neutralization Process

```python
# Cross-sectional residual alpha (conceptual)
# For each day t:
#   signal_rank = rank(signal_t)
#   residuals = OLS(signal_rank ~ market_cap + sector_dummies + style_factors).resid
#   alpha_t = rank(residuals)
```

### Verification

- [ ] Post-neutralization market beta < 0.1
- [ ] Post-neutralization sector exposure < 0.05
- [ ] IC retained after neutralization (some decay is normal)
- [ ] Turnover not excessively increased

---

## 6. Regime Awareness

### OMEGA_QUANT 4-Regime Model

| Regime | Characteristics | Strategy Preference |
|--------|-----------------|-------------------|
| **Bull** | Rising trend, low vol | Momentum, trend-following |
| **Sideways** | Flat, low vol | Mean-reversion |
| **Volatile Sideways** | Flat, high vol | Reduce exposure, tight stops |
| **Bear** | Falling trend, high vol | Defensive, cash, short alpha |

### Regime-Conditional Alpha Evaluation

| Check | Requirement |
|-------|-------------|
| **IC per regime** | Report IC separately for each regime |
| **Regime stability** | Alpha must work in at least 2 regimes |
| **Bear regime** | Alpha must not have negative Sharpe in bear |
| **Hysteresis** | Account for regime transition delays |

### Regime Switcher Integration

- Regime detection uses HMM with asymmetric hysteresis
- Transition ramps prevent abrupt strategy switches
- Bear-cooldown prevents premature re-entry
- Alpha signals should be regime-tagged in evaluation

---

## 7. Alpha Discovery Methods

### Genetic Programming (OMEGA_QUANT Evolution Pipeline)

| Component | Implementation |
|-----------|---------------|
| **Tree structure** | Terminals: OHLCV, returns, RSI, MACD. Operators: add/sub/mul/div/rank/delay |
| **Fitness** | Sharpe - 0.1 * Turnover - 0.01 * TreeDepth |
| **Mutation** | Replace random subtree |
| **Crossover** | Swap subtrees between parents (deep-copy) |
| **PIT enforcement** | Double T-1 shift in both `genetic_alpha.py` and `fitness.py` |

### Ensemble Alpha

| Method | Description |
|--------|-------------|
| **XGBoost Ranker** | Pairwise ranking of alpha signals |
| **Voting** | Majority vote across signal directions |
| **Stacking** | Meta-learner on alpha predictions |
| **IC-weighted** | Weight signals by rolling IC |

---

## 8. Verification Checklist

Before promoting any alpha to live:

- [ ] **PIT-safe**: T-1 lag verified by `signal_sanitizer.validate_t_minus_1_lag()`
- [ ] **IC > 0.02** net of estimated costs
- [ ] **IR > 0.5** over at least 3 years of backtest
- [ ] **Turnover < 30%** daily one-way
- [ ] **Capacity > 5B VND** at 10% ADV participation
- [ ] **Neutralized** against market, sector, style
- [ ] **Regime-robust**: IC positive in at least 2/4 regimes
- [ ] **Walk-forward OOS**: positive Sharpe in held-out period
- [ ] **CPCV**: passed Combinatorial Purged CV (N=10, k=2)
- [ ] **No data snooping**: alpha hypothesis pre-specified before testing

---

## 9. Anti-Patterns

| Don't | Do Instead |
|-------|-----------|
| Optimize parameters on full sample | Walk-forward with embargo |
| Report gross IC only | Always report net-of-cost IC |
| Ignore regime | Test IC per regime, flag regime-fragile alphas |
| Use random CV splits | Use chronological or CPCV splits |
| Ignore turnover | Penalize turnover in fitness function |
| Backtest on survivors only | Include delisted stocks (survivorship-free universe) |
| Use Pearson IC for skewed signals | Use Spearman rank IC |
| Neutralize in-sample only | Neutralize cross-sectionally each day |
| Over-fit tree depth in GP | Penalize depth: Fitness -= 0.01 * TreeDepth |

---

## 10. SOD/PIT Guardrails

| Guardrail | Rule |
|-----------|------|
| **PIT: no look-ahead** | All signals shifted T-1 minimum; `as_of <= available_at` always |
| **SOD: no self-approval** | Alpha researcher cannot approve own alpha for live |
| **SOD: Tier 3 audit** | All alpha code submitted to Code Reviewer (role 21) + QA Engineer (role 17) |
| **Data provenance** | Every alpha must document data source, date range, and universe |
| **Reproducibility** | Alpha evaluation must be deterministic (seeds set, no random splits) |

---

> **Remember:** In quant research, the null hypothesis is "this alpha is noise." Burden of proof is on the signal.
