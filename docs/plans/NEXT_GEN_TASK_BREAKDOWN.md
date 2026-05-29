# OMEGA_QUANT MICRO-TASK BREAKDOWN
**Date**: 2026-05-29 17:51 GMT+7
**Approved**: anh Manh
**Strategy**: Each sub-agent task <5min, <300 lines/file, L3 audit per file

## EXECUTION RULES (LESSONS LEARNED)

### From last session bugs:
- L2 sub-agent timeout >10min = stuck (kill needed)
- Codex audit timeout when prompt has too many escape chars
- write/edit tool fails when content >5KB sometimes
- `&` in PowerShell breaks multi-arg commands

### Mitigation:
1. **Each L2 task**: ONE file, max 300 lines, ONE clear deliverable
2. **Each L3 audit**: 1-2 files only, plain text output, simple prompts
3. **Save state after each task**: commit + push
4. **Context budget per phase**: <30 sub-agent calls
5. **Use 2-step pattern for Codex**: Step1=collect, Step2=write
6. **Parallel where safe**: independent files spawn together

## PHASE 1: ML UNIVERSE SELECTOR

### Task 1.1: Feature Computer (PIT-safe)
- **L2**: Write `packages/quant/src/omega/quant/universe/feature_computer.py`
- **Scope**: 1 class `UniverseFeatureComputer`, methods compute_momentum, compute_volume, compute_quality
- **Lines**: ~250
- **Time**: 3-5min
- **Output**: pd.DataFrame (ticker, date, 30 features)

### Task 1.2: XGBoost Classifier Wrapper
- **L2**: Write `packages/quant/src/omega/quant/universe/xgb_classifier.py`
- **Scope**: 1 class `UniverseClassifier`, fit/predict_proba/save/load
- **Lines**: ~150
- **Time**: 3-5min

### Task 1.3: Training Script
- **L2**: Write `scripts/train_universe_classifier.py`
- **Scope**: load data, compute features, train, save model, print metrics
- **Lines**: ~120
- **Time**: 3-5min

### Task 1.4: Selection Script (production)
- **L2**: Write `scripts/select_universe_dynamic.py`
- **Scope**: load model, compute today features, predict, save universe JSON
- **Lines**: ~80
- **Time**: 3-5min

### Task 1.5: L3 Audit Phase 1 (parallel with Task 1.6 below)
- **L3**: Codex 2-step audit 4 new files
- Step 1: read files, write findings to `audit_phase1_step1.txt`
- Step 2: read text, write verdict to `audit_phase1_final.md`
- **Time**: 3-5min each step

### Task 1.6: Run Training + Eval
- **Background**: `python scripts/train_universe_classifier.py`
- **Time**: 5-10min (XGBoost on 8 years data)
- **Yield while running** to avoid blocking

### Task 1.7: Backtest with dynamic universe
- **L2**: Update `scripts/backtest_evolution.py` to load universe per year
- **Lines**: ~30 (only modify universe selection)
- **Time**: 2-3min
- **Run**: ~30min compute

### Task 1.8: L3 Audit Backtest Comparison
- Compare static vs dynamic Sharpe
- **Time**: 5min

## PHASE 2: GP EVOLUTION SCALED

### Task 2.1: Feature Adapter
- **L2**: Write `packages/quant/src/omega/quant/evolution/feature_adapter.py`
- **Scope**: Wrap ultimate_alpha_arsenal (132) + microstructure (17) + smart_money (10) -> dict for GP
- **Lines**: ~150
- **Time**: 3-5min

### Task 2.2: Update GPConfig
- **L2**: Edit `packages/quant/src/omega/quant/evolution/genetic_engine.py`
- **Scope**: Add multi-target fitness, scale params
- **Lines**: ~50 lines changed
- **Time**: 3-5min

### Task 2.3: Pareto HoF
- **L2**: Write `packages/quant/src/omega/quant/evolution/pareto_hof.py`
- **Scope**: NSGA-II style Pareto front for diversity
- **Lines**: ~200
- **Time**: 3-5min

### Task 2.4: Run GP Scaled
- **Background**: pop=500, gen=50, 200 features
- **Time**: 30-60min (BIG compute, monitor closely)
- **Strategy**: 1 year at a time, save checkpoints

### Task 2.5: L3 Audit
- 2-step pattern, 3 files

## PHASE 3: CPCV FRAMEWORK

### Task 3.1: CombinatorialPurgedKFold
- **L2**: Write `packages/quant/src/omega/quant/validation/cpcv.py`
- **Lines**: ~250
- **Time**: 5min

### Task 3.2: DSR (Deflated Sharpe Ratio)
- **L2**: Write `packages/quant/src/omega/quant/validation/dsr.py`
- **Lines**: ~150
- **Time**: 3-5min

### Task 3.3: Backtest v2 with CPCV
- **L2**: Write `scripts/backtest_v2_cpcv.py`
- **Lines**: ~250
- **Time**: 5min
- **Run**: ~45min compute (45 paths)

### Task 3.4: L3 Audit Statistical Validity
- Critical: verify embargo, purging, no leakage

## PHASE 4: ML STACK INTEGRATION

### Task 4.1: LSTM Encoder
- **L2**: Write `packages/quant/src/omega/quant/ml/lstm_encoder.py`
- **Lines**: ~200
- **Time**: 5min

### Task 4.2: Stacking Ensemble
- **L2**: Write `packages/quant/src/omega/quant/ml/stacking_ensemble.py`
- **Lines**: ~200
- **Time**: 5min

### Task 4.3: Full Stack Trainer
- **L2**: Write `scripts/train_full_stack.py`
- **Lines**: ~250
- **Time**: 5min
- **Run**: ~30min train

### Task 4.4: Final Backtest
- **L2**: Write `scripts/backtest_full_stack.py`
- **Run**: ~60min CPCV evaluation
- **Output**: Final report comparing all approaches

## TOTAL MICRO-TASKS

| Phase | L2 tasks | L3 audits | Compute |
|:------|:--------:|:---------:|:-------:|
| Phase 1 | 4 | 2 | ~40min |
| Phase 2 | 3 | 1 | ~60min |
| Phase 3 | 3 | 1 | ~45min |
| Phase 4 | 4 | 1 | ~90min |
| **Total** | **14** | **5** | **~3.5h** |

## EXECUTION ORDER (THIS SESSION)

### Today (now -> tonight):
1. Save this breakdown ✅
2. Launch Task 1.1 (feature_computer.py)
3. Launch Task 1.2 (xgb_classifier.py) parallel
4. Wait both done, L3 audit (Task 1.5)
5. Launch Task 1.3 + 1.4 parallel
6. L3 audit again
7. Run Task 1.6 (train) in background
8. Yield -> wait results

### Tomorrow / next session:
- Phase 1.7-1.8 (backtest with dynamic universe)
- Phase 2 (GP scaled) - heavy compute
- Phase 3 (CPCV)
- Phase 4 (Full stack)

## STATE PERSISTENCE

After each task:
- `git add <file>` + `git commit -m "phase X.Y: <what>"`
- Update `.ly_state/session/next_gen_progress.json`:
  ```json
  {
    "phase": "1.1",
    "status": "completed",
    "audit": "approved",
    "next": "1.2"
  }
  ```

## CONTEXT RECOVERY

If context truncated:
- Read `docs/plans/OMEGA_QUANT_NEXT_GEN_PLAN.md`
- Read `.ly_state/session/next_gen_progress.json`
- Resume from `next` field
