# L2 Role 14 (Data Scientist) — Recovery Pool A/B Diagnostics

**GATE**: RECOVERY_POOL_AB_DIAGNOSTICS_20260614
**Role**: 14 (data-scientist) — L2 implementation only
**Date**: 2026-06-14
**Status**: COMPLETE — submit to Tier 3 audit

---

## Source Provenance

### Repo-Local Files Read
- **Agent**: `.agents/agent/data-scientist.md` (role_id: 14, tier: 2, 9 skills declared)
- **Skills** (all from `.agents/skills/*/SKILL.md`):
  1. `python-patterns` — Python dev principles
  2. `clean-code` — Pragmatic coding standards
  3. `testing-patterns` — Testing patterns and principles
  4. `systematic-debugging` — 4-phase debugging methodology
  5. `performance-profiling` — Performance profiling principles
  6. `quant-research` — Factor/alpha research for OMEGA_QUANT
  7. `vietnam-market-data` — Vietnam equity market data principles
  8. `backtesting-pit-safety` — Backtesting integrity and PIT safety
  9. `data-science-workflow` — EDA, experiment tracking, reproducibility

### Forbidden Path Scan Result
- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source — **not present** in repo
- `.openclaw\skills` is non-authoritative and not used as source — **not present** in repo
- `C:\Users\GHC\.agents` is non-authoritative and not used as source — **exists on filesystem but NOT accessed or used**
- `.codex\memories` is non-authoritative and not used as source — **not present** in repo

---

## Scope Files Modified

| File | Change Type |
|------|-------------|
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | Bug fix + enhancement |
| `scripts/analyze_alpha_weakness.py` | Feature: recovery pool A/B diagnostics |
| `tests/test_risk_adjusted_alpha_score.py` | Tests: regime_threshold_ic parameter |
| `tests/test_analyze_alpha_weakness.py` | Tests: recovery pool A/B opt-in behavior |

## Scope Files Generated

| File | Purpose |
|------|---------|
| `.ly_state/session/recovery_pool_ab_report_20260614.md` | Recovery pool A/B diagnostics report (490 lines) |
| `.ly_state/session/l2_role14_recovery_pool_ab_diagnostics_20260614.md` | This L2 report |

---

## Changes Implemented

### 1. Fix: `regime_threshold_ic` Parameter Honored

**Problem**: `compute_regime_conditioned_ic()` declared `regime_threshold_ic: float = 0.0` but hard-coded `ic < -0.01` in the bear-like classification body, ignoring the parameter.

**Fix**:
- Changed default from `0.0` to `-0.01` to preserve backward-compatible behavior
- Changed hard-coded `ic < -0.01` to `ic < regime_threshold_ic` in the fold classification logic
- Updated `compute_alpha_recovery_diagnostics()` to accept and pass through `regime_threshold_ic`
- Updated docstrings to reflect the change

**Backward Compatibility**: Default value `-0.01` produces identical results to the previous hard-coded behavior.

### 2. Feature: `--recovery-pool-ab` Opt-In Diagnostics

**CLI Flags Added**:
- `--recovery-pool-ab` — enables recovery pool A/B diagnostics
- `--regime-threshold-ic` — configurable IC threshold for bear-like regime (default: -0.01)

**Report Section**: "Recovery Pool A/B Diagnostics (Opt-In)" includes:
- Pool definitions (full pool vs recovery-only pool)
- Per-fold mean alpha IC comparison table
- Summary statistics (mean fold IC, positive fold rate)
- RECOVERABLE vs RESEARCH_ONLY sub-pool breakdown
- Assessment of whether excluding CONFIRMED_RETIRE improves signal quality

**Pool Logic**:
- **Full pool**: All alphas
- **Recovery-only pool**: RECOVERABLE + RESEARCH_ONLY, excluding CONFIRMED_RETIRE
- Uses existing OOS fold alpha IC evidence (PIT-safe, no look-ahead)

### 3. Safety Boundaries Preserved
- No live trading / default production behavior changes
- All new features are opt-in (disabled by default)
- PIT safety maintained: only fold-level OOS metrics used
- Fallback remains failure semantics unchanged

---

## Test Results

### pytest Command
```
python -m pytest tests/test_risk_adjusted_alpha_score.py tests/test_analyze_alpha_weakness.py -q
```

### Result: ALL 273 TESTS PASSED

New tests added:
- `TestRegimeThresholdICParameter` (4 tests): default threshold, custom threshold=0.0, custom threshold=-0.05, pass-through via recovery diagnostics
- `TestRecoveryPoolABOptIn` (10 tests): default no section, opt-in has section, excludes CONFIRMED_RETIRE, works with research gates, per-fold comparison, no live trading note, RECOVERABLE/RESEARCH_ONLY breakdown, backward compatibility, CLI flag, CLI default, CLI regime-threshold-ic flag

### Script Command
```
python scripts/analyze_alpha_weakness.py \
    --input-dir data/phase35_results/ab_guard_20260614_101727 \
    --output .ly_state/session/recovery_pool_ab_report_20260614.md \
    --research-gates --recovery-diagnostics --recovery-pool-ab
```

### Result: SUCCESS — Report generated (490 lines, 3 variants analyzed)

---

## SOD Boundary Compliance

- **L2 implementation only** — no self-approval
- **No live trading paths modified**
- **Submit to Tier 3 audit**: Code Reviewer (role 21) + QA Engineer (role 17)
- **PIT safety**: All new logic uses only existing OOS fold metrics
- **Evidence persisted**: Report and L2 report in `.ly_state/session/`

---

*Implementation by Role 14 (data-scientist) L2. Submit to Tier 3 audit.*
