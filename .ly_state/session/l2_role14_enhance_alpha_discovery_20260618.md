# L2 Implementation Report — Role 14 (Data Scientist)

## Train-Prefix Supervised Selection & Fallback-as-Failure Checkpoint

| Field | Value |
|-------|-------|
| **Date** | 2026-06-18 |
| **Role** | 14 — Data Scientist (OpenCode L2) |
| **Gate** | `AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615` |
| **Scope** | `scripts/backtest_v2_cpcv.py` |
| **Git base** | `b93d0e9` |
| **Status** | IMPLEMENTED — awaiting Tier 3 audit |

---

## 1. Source Files Read (Repo-Local Only)

### Agent Definition
- `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent\data-scientist.md` (73 lines, role_id=14, tier=2)

### Skills Loaded (from `REPO_SKILL_ROOT` only)
| # | Skill | Path |
|---|-------|------|
| 1 | python-patterns | `.agents/skills/python-patterns/SKILL.md` (442 lines) |
| 2 | clean-code | `.agents/skills/clean-code/SKILL.md` (202 lines) |
| 3 | testing-patterns | `.agents/skills/testing-patterns/SKILL.md` (179 lines) |
| 4 | systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` (110 lines) |
| 5 | performance-profiling | `.agents/skills/performance-profiling/SKILL.md` (144 lines) |
| 6 | quant-research | `.agents/skills/quant-research/SKILL.md` (257 lines) |
| 7 | vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` (315 lines) |
| 8 | backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` (322 lines) |
| 9 | data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` (303 lines) |

### Forbidden Path Scan
| Path | Exists | Used |
|------|--------|------|
| `C:\Users\GHC\.agents\Codex` | NO | N/A |
| `.agents/skills/antigravity` | NO | N/A |
| Antigravity scratch / OpenClaw | NO | N/A |

**Result:** Zero forbidden paths scanned. All skill content sourced exclusively from `REPO_AGENT_ROOT` and `REPO_SKILL_ROOT`.

---

## 2. Implementation Summary

### Feature A: Train-Prefix Supervised Selection

**Problem:** The existing L3 Fix #2 train-prefix code (causal 50% date cutoff) only supports **unsupervised** formula scoring (`labels=None`). Without supervised IC metrics, the LLM formula scorer cannot rank candidates by predictive quality, limiting selection to variance/coverage heuristics.

**Solution:** Added `_compute_train_prefix_supervised_labels()` that computes PIT-safe forward-return labels restricted to the causal train-prefix. Labels are NaN for rows whose forward horizon (`T + label_horizon`) extends beyond the prefix boundary, preventing any test-region data leakage.

**PIT Safety Guarantee:**
- Forward returns: `close.shift(-horizon) / close - 1`
- Last safe date: `causal_cutoff_date - Timedelta(days=horizon*2)` (conservative buffer)
- Only rows where `date <= last_safe_date` AND `fwd_ret.notna()` are labeled
- Labels never use data from dates > cutoff

**New CLI Flags:**
| Flag | Default | Description |
|------|---------|-------------|
| `--train-prefix-supervised` | off | Enable PIT-safe supervised IC-based formula scoring within the train-prefix |

**Wired to:**
- Closed-loop search: `runner.run_search(labels=_tp_labels)`
- Simple scoring: `synthesizer.score_and_filter_formulas(labels=_tp_labels_simple)`
- Top-K selection: both paths pass labels through

### Feature B: Fallback-as-Failure Checkpoint

**Problem:** CPCV folds where the alpha pipeline produces near-zero predictions (IC below threshold) or where all test rows fall in the dev prefix were not tracked as "fallback" failures. No gate existed to flag when the alpha pipeline is systematically failing to produce qualifying candidates.

**Solution:** Wired `compute_fallback_as_failure_metrics()` (from `omega.quant.walk_forward`) into the CPCV pipeline:

1. Each fold is classified as:
   - **alpha-selected**: `abs(test_ic) >= min_fold_ic_threshold`
   - **fallback**: fold skipped (all test in prefix) OR `abs(test_ic) < threshold`
2. After CPCV loop, computes aggregate metrics via the existing library function
3. Checks against `--fallback-failure-threshold`; logs CRITICAL if exceeded

**New CLI Flags:**
| Flag | Default | Description |
|------|---------|-------------|
| `--min-fold-ic` | 0.005 | Minimum abs(IC) for alpha-selected classification |
| `--fallback-failure-threshold` | 0.50 | Maximum allowed fallback rate before gate FAIL |

**Output:** `summary["fallback_as_failure"]` dict with keys: `total_folds`, `alpha_selected_folds`, `fallback_folds`, `alpha_selected_positive_ic_rate`, `fallback_positive_ic_rate`, `fallback_as_failure_rate`.

**Gate:** `summary["fallback_gate"]` = `"PASS"` or `"FAIL"`.

---

## 3. Code Changes (Diff Summary)

| Location | Change | Lines Affected |
|----------|--------|---------------|
| Module-level imports | Added `compute_fallback_as_failure_metrics` try/except import | +4 |
| Helper functions | Added `_compute_train_prefix_supervised_labels()` | +36 |
| `run_pipeline()` signature | Added `min_fold_ic_threshold` parameter | +1 |
| `run_pipeline()` fold loop | Added `_fold_fb_details` tracking list | +1 |
| `run_pipeline()` skip block | Added fallback detail for skipped folds | +6 |
| `run_pipeline()` fold append | Added fallback detail for processed folds | +6 |
| `run_pipeline()` post-DSR | Added `compute_fallback_as_failure_metrics()` call | +13 |
| `run_pipeline()` summary | Added `fallback_as_failure` key to `s` dict | +2 |
| `main()` CLI args | Added 3 new argparse arguments | +28 |
| `main()` prefix mask | Added supervised label computation | +14 |
| `main()` LLM closed-loop | Build `_tp_labels`, pass to search/top-K | +12/-6 |
| `main()` LLM simple path | Build `_tp_labels_simple`, pass to scorer/top-K | +15/-10 |
| `main()` validation summary | Added `train_prefix_supervised` key | +1 |
| `main()` run_pipeline call | Added `min_fold_ic_threshold` kwarg | +1 |
| `main()` post-pipeline | Added fallback gate check (CRITICAL/PASS) | +16 |

**Net change:** ~160 lines added/modified, 0 lines deleted from external APIs.

---

## 4. Test Results

### Syntax Check
```
python -c "import ast; ast.parse(open('scripts/backtest_v2_cpcv.py').read())"
→ SYNTAX OK
```

### Smoke Test — Baseline (no LLM, no supervised)
```
--smoke --min-fold-ic 0.005 --fallback-failure-threshold 0.5
→ FALLBACK-AS-FAILURE: total=45 alpha=41 fallback=4 failure_rate=0.089
→ alpha_pos_IC=0.488 fallback_pos_IC=0.250
→ GATE: PASS
```

### Smoke Test — Supervised (no LLM)
```
--smoke --train-prefix-supervised --min-fold-ic 0.005
→ Train-prefix supervised labels: 2472/5000 valid rows
→ FALLBACK-AS-FAILURE GATE: PASS (rate=0.089 <= 0.500)
```

### Smoke Test — LLM + Supervised
```
--smoke --use-llm-alphas --train-prefix-supervised
→ Supervised labels for train-prefix: 2472/2504 valid
→ Iteration 1: Using supervised scoring (IC >= 0.01, DSR >= -0.5)
→ FALLBACK-AS-FAILURE: total=45 alpha=32 fallback=13 failure_rate=0.289
→ alpha_pos_IC=0.781 fallback_pos_IC=0.077
→ GATE: PASS
```

### Regression Test Suite
```
pytest tests/ -x -q -k "backtest or cpcv or fallback"
→ 162 passed, 0 failed
```

### Key Observations
| Configuration | Fallback Rate | Alpha Pos IC Rate | Fallback Pos IC Rate |
|---------------|---------------|-------------------|---------------------|
| Baseline (no LLM) | 8.9% | 48.8% | 25.0% |
| LLM + Supervised | 28.9% | 78.1% | 7.7% |

The supervised selection with LLM alphas produces a **more discriminating** pipeline: alpha-selected folds have much higher positive IC rate (78% vs 49%), while fallback folds are correctly identified as weak (7.7% vs 25%).

---

## 5. Backward Compatibility

- All existing CLI flags preserved with identical defaults
- `--train-prefix-supervised` is opt-in (off by default) → existing behavior unchanged
- Fallback-as-failure metrics are **always computed** (no CLI flag to disable) — additive only
- `compute_fallback_as_failure_metrics` import is wrapped in try/except — graceful degradation if walk_forward module unavailable

---

## 6. PIT Safety Analysis

| Component | PIT Mechanism | Verified |
|-----------|---------------|----------|
| Train-prefix labels | Forward returns clipped to `cutoff - 2*horizon` | Yes — 2472 valid of 5000 |
| CPCV prefix exclusion | `prefix_test_mask` excludes dev-prefix rows from test folds | Yes — existing L3 Fix #2 |
| Fallback classification | Uses only fold test IC (no label leakage) | Yes |
| Unsupervised fallback | `labels=None` preserved when `--train-prefix-supervised` off | Yes |

---

## 7. Tier 3 Audit Submission

This implementation is submitted for review by:
- **Code Reviewer (role 21):** Code quality, reproducibility, naming conventions
- **QA Engineer (role 17):** Model validation, PIT safety verification, test coverage

**Cannot proceed until:** Both roles return [APPROVED].
