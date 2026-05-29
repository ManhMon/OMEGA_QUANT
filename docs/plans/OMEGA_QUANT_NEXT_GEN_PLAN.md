# OMEGA_QUANT NEXT-GEN PLAN
**Date**: 2026-05-29
**Status**: APPROVED by anh Manh, ready to execute
**SOD**: L2=opencode CLI, L3=codex CLI, L1=Ly orchestrator

## CONFIRMED DECISIONS

### 1. ML Stack
- XGBoost: Universe classifier (predict P(top performer))
- LSTM: Temporal feature encoder (60-day sequences)
- Ridge: Signal stacking/combiner
- RL (PPO): DEFERRED - chi dung cho position sizing sau khi production stable
- Random Forest: BACKUP cho ensemble diversity

### 2. Portfolio Construction
- Universe pool: 50 stocks (eligible candidates)
- Holdings: 8 mã top alpha (long-only)
- Max concentration: 20% per stock
- Min concentration: 5% per stock
- Cash buffer: 10%
- Rebalance: Weekly

### 3. Validation Framework: CPCV + Embargo + Walk-Forward
- 10 time blocks total
- 2 test blocks per iteration
- 1% embargo (5 days)
- Purging on overlapping labels
- 45 backtest paths (10 choose 2)
- Aggregate Sharpe via DSR (Deflated Sharpe Ratio)

### 4. Features
- Use existing ultimate_alpha_arsenal.py (132 alphas)
- Add phase34_microstructure_alphas (17)
- Add smart_money_features (~10)
- Add structure_features (~10)
- Add sentiment (5-10)
- Add macro proxies (10)
- TOTAL: 200+ features

### 5. GP Evolution Scale-Up
- Population: 50 -> 500
- Generations: 10 -> 50
- Max depth: 4 -> 5
- Multi-target: fwd_ret_1, fwd_ret_5, fwd_ret_20
- Pareto-front fitness: IC + Sharpe + Diversity
- Walk-forward yearly retraining

## EXECUTION PHASES

### Phase 1: ML-Enhanced Universe Selector (~2h)
**L2 (opencode CLI)**:
- packages/quant/src/omega/quant/universe/ml_selector.py
- packages/quant/src/omega/quant/universe/lstm_encoder.py
- scripts/train_universe_classifier.py
- scripts/select_universe_dynamic.py

**Steps**:
1. Compute 50+ features per stock per day (PIT-safe)
2. Label: y=1 if return_3m_forward in top 25%, else 0
3. Train XGBoost classifier on 2015-2023
4. Evaluate on 2024-2026
5. Save model to models/universe_classifier.pkl
6. Output daily: .ly_state/session/universe_{date}.json

**L3 (codex CLI)**: Audit PIT safety, embargo correctness

### Phase 2: GP Evolution Scaled (~3h)
**L2**:
- Wire ultimate_alpha_arsenal (132 alphas) to GP feature input
- Wire microstructure (17) + smart_money (10) + structure (10)
- Update GPConfig: pop=500, gen=50, max_depth=5
- Multi-target fitness combining IC across horizons
- Pareto-front selection in HoF

**L3**: Audit overfitting, computational stability

### Phase 3: CPCV Framework (~1h)
**L2**:
- packages/quant/src/omega/quant/validation/cpcv.py
- CombinatorialPurgedKFold class
- DeflatedSharpeRatio statistical test
- Replace simple walk-forward in backtest_evolution.py
- Aggregate metrics across 45 paths

**L3**: Statistical rigor of CPCV implementation

### Phase 4: ML Stack Integration (~2h)
**L2**:
- packages/quant/src/omega/quant/ml/lstm_encoder.py
- packages/quant/src/omega/quant/ml/stacking_ensemble.py
- scripts/train_full_stack.py
- Backtest with CPCV

**L3**: Compare hybrid vs Mom20 baseline rigorously

## FILES TO CREATE/MODIFY

### New:
- packages/quant/src/omega/quant/universe/ml_selector.py
- packages/quant/src/omega/quant/universe/lstm_encoder.py
- packages/quant/src/omega/quant/validation/cpcv.py
- packages/quant/src/omega/quant/validation/dsr.py
- packages/quant/src/omega/quant/ml/lstm_encoder.py
- packages/quant/src/omega/quant/ml/stacking_ensemble.py
- scripts/train_universe_classifier.py
- scripts/select_universe_dynamic.py
- scripts/train_full_stack.py
- scripts/backtest_v2_cpcv.py

### Modify:
- scripts/backtest_evolution.py (use CPCV)
- scripts/run_daily_oracle.py (Step 0.5: dynamic universe)
- packages/quant/src/omega/quant/evolution/genetic_engine.py (200+ feature support)

## SUCCESS METRICS

### Phase 1 Universe Selector:
- Classifier ROC AUC > 0.65
- Top 50 universe captures 75%+ winners
- Sector diversity: max 5 stocks per sector

### Phase 2 GP Scaled:
- Mean OOS IC > 0.05
- Sharpe with CPCV > Mom20 baseline + 0.3

### Phase 3 CPCV:
- DSR p-value < 0.05 (statistically significant alpha)
- 45 paths variance acceptable

### Phase 4 Full Stack:
- Combined Sharpe > 1.5 (vs Mom20 baseline 1.02)
- Win rate vs Mom20: 6/10 -> 7/10
- Drawdown: -22% -> -18%

## EXPECTED OUTCOMES

### Best case (Renaissance-tier):
- Sharpe 2.0+, DD -15%, Win 8/10
- Cumulative 10y: +500-700%

### Realistic (institutional grade):
- Sharpe 1.4-1.6, DD -18%, Win 7/10
- Cumulative 10y: +400-500%

### Worst case (vs current Mom20):
- Sharpe ~1.0-1.2 (ML doesnt add value)
- Action: Stick with Mom20 as production

## NEXT IMMEDIATE STEPS

1. Save this plan to docs/plans/ (DONE)
2. Commit plan to git
3. Launch Phase 1 L2 opencode CLI background
4. Yield until L2 completes
5. L3 codex audit Phase 1
6. /ac loop until APPROVED
7. Move to Phase 2

## TIMELINE

- Phase 1: 2h compute + 0.5h audit = 2.5h
- Phase 2: 3h compute + 0.5h audit = 3.5h
- Phase 3: 1h compute + 0.5h audit = 1.5h
- Phase 4: 2h compute + 0.5h audit = 2.5h
- TOTAL: ~10h compute (multiple sessions if needed)

## SOD COMPLIANCE CHECKLIST

- [ ] L2 ne L3 ne L1 (Writer != Auditor != Gate)
- [ ] CLI-only execution (opencode + codex)
- [ ] All gates require evidence (l3_session_id, audit_report_path, final_verdict)
- [ ] PIT safety checked at every step
- [ ] Vectorization 100% (no iterrows)
- [ ] Numerical stability (winsorize, z-score, NaN guards)
- [ ] Unit tests for new modules

---
**Approved by**: anh Manh (timestamp: 2026-05-29 17:38 GMT+7)
**Orchestrator**: Ly L1
**Started**: TBD
