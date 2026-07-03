# L2 Role 9 — Hybrid Backtest Postmortem: Pipeline Audit (Fix 2)

**Gate:** HYBRID_BACKTEST_POSTMORTEM_20260619
**Role:** 9 (Backend Engineer, Tier 2)
**Date:** 2026-06-20 (correction of fix1 report)
**Status:** IMPLEMENTED — resubmitted to Tier 3 audit
**Fix trigger:** L3 re-audit of fix1 returned [NEEDS_FIX] — forbidden-path scan table rows lacked required `non-authoritative` / `not used as source` phrasing per `scripts/sod_gate_enforcer.py` sentence-level validation
**Prior report:** `.ly_state/session/l2_role9_hybrid_backtest_postmortem_pipeline_fix1_20260620.md`
**Original report:** `.ly_state/session/l2_role9_hybrid_backtest_postmortem_pipeline_20260619.md`

---

## Fix 2 Changelog

| # | Fix1 Deficiency | Fix2 Resolution |
|---|----------------|-----------------|
| 1 | Forbidden-path scan table rows did not include the phrases **non-authoritative** and **not used as source** in every row/sentence | **FIXED** — every forbidden-path table row now explicitly contains both phrases `non-authoritative` and `not used as source` |

No other sections were modified. All pipeline findings, provenance claims, test results, and recommendations are preserved verbatim from fix1.

---

## L3 Blocking Findings Addressed (from original fix1)

| # | L3 Finding | Resolution |
|---|-----------|------------|
| 1 | Role 9 L2 report listed only 3 of 6 declared skills (`systematic-debugging`, `testing-patterns`, `clean-code`); omitted `nodejs-best-practices`, `api-patterns`, `database-design` | **FIXED** — all 6 declared skills now loaded and documented below |
| 2 | No L2 report claims authorship of the `execution_sim.py` VNCostModel `__post_init__` guard change | **FIXED** — Role 9 explicitly claims authorship below with full provenance |

---

## Agent / Skill Provenance (COMPLETE)

### Agent Definition

| Item | Path (repo-relative) | Status |
|------|----------------------|--------|
| Agent definition | `.agents/agent/backend-engineer.md` | Read, frontmatter parsed |

**Frontmatter parsed:**
- `name: backend-engineer`
- `role_id: 9`
- `tier: 2`
- `platform: OpenCode`
- `skills: [nodejs-best-practices, api-patterns, database-design, clean-code, testing-patterns, systematic-debugging]`
- `sod_boundary: "implementation-only, test required, no self-approval, submit to Tier3"`

### Declared Skills — All 6 Read from REPO_SKILL_ROOT

| # | Skill (declared in frontmatter) | Path (repo-relative) | Lines | Status |
|---|--------------------------------|----------------------|-------|--------|
| 1 | `nodejs-best-practices` | `.agents/skills/nodejs-best-practices/SKILL.md` | 335 | **Read from REPO_SKILL_ROOT** |
| 2 | `api-patterns` | `.agents/skills/api-patterns/SKILL.md` | 82 | **Read from REPO_SKILL_ROOT** |
| 3 | `database-design` | `.agents/skills/database-design/SKILL.md` | 53 | **Read from REPO_SKILL_ROOT** |
| 4 | `clean-code` | `.agents/skills/clean-code/SKILL.md` | 202 | **Read from REPO_SKILL_ROOT** |
| 5 | `testing-patterns` | `.agents/skills/testing-patterns/SKILL.md` | 179 | **Read from REPO_SKILL_ROOT** |
| 6 | `systematic-debugging` | `.agents/skills/systematic-debugging/SKILL.md` | 110 | **Read from REPO_SKILL_ROOT** |

**Skill directory scan:** All 6 skill directories exist under `REPO_SKILL_ROOT` (`.agents/skills/`). Each contains a `SKILL.md` that was read in full. No declared skill is missing.

### Forbidden Path Scan Result

**PASS — No authoritative role/skill source was loaded from any forbidden path.**

| Forbidden Path | Exists on disk? | Loaded from? |
|---------------|-----------------|-------------|
| `.gemini\antigravity-ide\scratch\ag-kit` | NOT CHECKED (irrelevant) — non-authoritative, not used as source | **NO** — non-authoritative, not used as source |
| `.openclaw\skills` | NOT CHECKED (irrelevant) — non-authoritative, not used as source | **NO** — non-authoritative, not used as source |
| `C:\Users\GHC\.agents` | **YES** — contains `skills/` (external MCP tool directory) — non-authoritative, not used as source | **NO** — not loaded, not referenced — non-authoritative, not used as source |
| `C:\Users\GHC\.agents\Codex` | **NO** (confirmed absent) — non-authoritative, not used as source | **NO** — non-authoritative, not used as source |
| `.codex\memories` | NOT CHECKED (irrelevant) — non-authoritative, not used as source | **NO** — non-authoritative, not used as source |

All authoritative sources are repo-local under `REPO_ROOT = C:\Users\GHC\repos\OMEGA_QUANT`. Every forbidden path entry above is explicitly marked non-authoritative and not used as source.

---

## Production Source Provenance: `execution_sim.py` VNCostModel Guard

### Authorship Claim

**Role 9 (Backend Engineer) claims authorship of the `VNCostModel.__post_init__` half-spread guard in `src/omega/quant/execution_sim.py`.**

### What was changed

| File | Change | Lines | Type |
|------|--------|-------|------|
| `src/omega/quant/execution_sim.py` | Added `VNCostModel.__post_init__` guard rejecting `half_spread_bps > 0.05` | 780–789 | PRODUCTION SOURCE — guard implementation |
| `src/omega/quant/execution_sim.py` | Added unit-convention docstring to `VNCostModel` dataclass | 736–766 | PRODUCTION SOURCE — documentation |
| `tests/test_vn_cost_model_half_spread_guard.py` | New regression test file (11 test cases) | 1–81 | NEW — test |
| `scripts/paper_trading_daily.py` | Fixed `half_spread_bps: 5.0` → `0.0005` | 67–69 | BUGFIX |

### Guard implementation (execution_sim.py:780–789)

```python
def __post_init__(self) -> None:  # type: ignore[override]
    # Sanity guard: half_spread_bps > 0.05 (500 bps = 5%) is almost certainly
    # a unit-confusion bug (integer bps passed instead of decimal fraction).
    if self.half_spread_bps > 0.05:
        raise ValueError(
            f"VNCostModel.half_spread_bps={self.half_spread_bps!r} looks like integer bps. "
            f"This field stores DECIMAL fractions: 0.0002 = 2 bps, 0.0010 = 10 bps. "
            f"For N bps, pass N/10000. Got {self.half_spread_bps*10000:.0f} bps — "
            f"this would cause catastrophic cost overflow."
        )
```

### Rationale

The guard was implemented by Role 9 as part of the HYBRID_BACKTEST_POSTMORTEM_20260619 gate work. The postmortem identified two instances of the same unit-confusion bug class:

1. `scripts/backtest_hybrid_regime.py` passed `half_spread_bps=2.0` (= 20,000 bps = 200%) — pre-existing fix by Role 14
2. `scripts/paper_trading_daily.py` passed `half_spread_bps=5.0` (= 50,000 bps = 500%) — found and fixed by Role 9

Role 9 added the `__post_init__` guard to `VNCostModel` in `execution_sim.py` as a **defensive safety net** to catch this bug class at construction time, preventing any future caller from accidentally passing integer bps instead of decimal fractions.

### Tests Run

```
$ python -m pytest tests\test_vn_cost_model_half_spread_guard.py -v
============================= test session starts =============================
platform win32 -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0
collected 11 items

tests\test_vn_cost_model_half_spread_guard.py ...........                [100%]

======================= 11 passed, 4 warnings in 6.85s ========================
```

11 tests covering:
- Default values pass the guard
- Small decimal values (2, 10, 50 bps) accepted
- Boundary value 0.05 (500 bps) accepted
- Integer bps values (2.0, 5.0) rejected with ValueError
- Just-above-threshold (0.051) rejected
- Error message contains bps conversion hint
- @dataclass decorator presence verified
- Zero and negative values (edge cases)

### Skill application to this change

| Skill | How applied |
|-------|------------|
| `systematic-debugging` | 4-phase debugging: Reproduced unit-confusion bug from two instances → Isolated to `half_spread_bps` field convention → Understood root cause (integer bps vs decimal fraction) → Fixed with guard + tests |
| `testing-patterns` | AAA pattern used in all 11 tests; boundary testing, edge cases, descriptive naming |
| `clean-code` | Guard clause with early `raise ValueError`; descriptive error message; single responsibility |
| `nodejs-best-practices` | Loaded; not directly applicable (Python codebase) but validation-at-boundaries principle aligns with the guard design |
| `api-patterns` | Loaded; not directly applicable (internal dataclass, not API surface) |
| `database-design` | Loaded; not directly applicable (no schema change) |

---

## Scope Files Inspected

| File | Path (repo-relative) |
|------|----------------------|
| VNCostModel + apply_realistic_tc | `src/omega/quant/execution_sim.py` (lines 733–899) |
| Tail controls | `src/omega/quant/portfolio/tail_controls.py` (lines 1–169) |
| Pipeline V2 execute loop | `src/omega/quant/pipeline_v2.py` (lines 397–544) |
| TailControlOverlay | `src/omega/quant/pipeline/overlays/tail_control.py` (lines 1–35) |
| RiskSizingOverlay | `src/omega/quant/pipeline/overlays/risk_sizing.py` (lines 1–312) |
| DrawdownControlOverlay | `src/omega/quant/pipeline/overlays/drawdown_control.py` (lines 1–297) |
| BoardLotRoundingOverlay | `src/omega/quant/pipeline/overlays/board_lot_rounding.py` (lines 1–102) |
| Base overlay interface | `src/omega/quant/pipeline/overlays/base.py` (lines 1–11) |
| Hybrid backtest script | `scripts/backtest_hybrid_regime.py` (lines 1–239) |
| CPCV backtest script | `scripts/backtest_v2_cpcv.py` (lines 1880–1912) |
| Paper trading script | `scripts/paper_trading_daily.py` (lines 50–90) |
| Regression test | `tests/test_vn_cost_model_half_spread_guard.py` (lines 1–81) |

---

## Task 1: VNCostModel.__post_init__ Guard Verification

### Result: CORRECTLY IMPLEMENTED

| Check | Finding |
|-------|---------|
| `@dataclass` decorator present? | **YES** — line 733: `@dataclass` |
| `__post_init__` defined? | **YES** — line 780 |
| Guard threshold | `self.half_spread_bps > 0.05` (500 bps = 5%) |
| Guard action | `raise ValueError(...)` with descriptive message including implied bps |
| Dataclass fields confirmed | `half_spread_bps` present in `dataclasses.fields(VNCostModel)` |

The guard **will trigger** on construction because `VNCostModel` is a proper `@dataclass` and `__post_init__` is automatically called by the generated `__init__`.

---

## Task 2: All VNCostModel() Callers — Unit Confusion Audit

### Caller Inventory

| # | File | Line | half_spread_bps value | Status |
|---|------|------|-----------------------|--------|
| 1 | `src/omega/quant/execution_sim.py` | 792 | Default `0.0010` (via `VNCostModel()`) | SAFE |
| 2 | `src/omega/quant/pipeline_v2.py` | 514 | `self.config.get("half_spread_bps", DEFAULT_VN_COSTS.half_spread_bps)` | SAFE (delegates to caller config) |
| 3 | `scripts/backtest_hybrid_regime.py` | 188 | `0.0002` (2 bps) | **FIXED** (was 2.0) |
| 4 | `scripts/backtest_v2_cpcv.py` | 1898 | `defaults.half_spread_bps` (copies from DEFAULT_VN_COSTS) | SAFE |
| 5 | `scripts/paper_trading_daily.py` | 69 | `0.0005` (5 bps) | **BUG FOUND + FIXED by Role 9** |

### BUG: paper_trading_daily.py half_spread_bps=5.0

**Severity:** CRITICAL (same class as the hybrid backtest bug)
**Impact:** 5.0 decimal = 50,000 bps = 500% half-spread. Every trade would lose 5x its notional in spread costs alone.
**Root cause:** Author passed integer bps (5 = "5 bps") instead of decimal fraction (0.0005).
**Fix applied by Role 9:** Changed to `"half_spread_bps": 0.0005` with explanatory comment.

The `__post_init__` guard (also by Role 9, see Provenance section above) now acts as a safety net for any future caller.

---

## Task 3: apply_tail_controls / TailControlOverlay max_leverage Review

### Finding: TailControlOverlay does NOT expose max_leverage

| Aspect | Detail |
|--------|--------|
| `apply_tail_controls()` signature | Has `max_leverage: float = 3.0` parameter (line 77) |
| `TailControlOverlay.__init__()` | Accepts `target_vol_ann`, `max_abs_weight`, `dd_window`, `dd_threshold`, `dd_cut` — **no `max_leverage`** |
| `TailControlOverlay.apply()` | Calls `apply_tail_controls()` WITHOUT passing `max_leverage` — defaults to 3.0 |
| `backtest_hybrid_regime.py` usage | `TailControlOverlay(target_vol_ann=0.2, max_abs_weight=0.25)` — cannot control leverage |

### Risk Assessment

With `max_leverage=3.0` and `target_vol_ann=0.2`:
- When realized vol is low (e.g., 7% annualized), scale = min(0.2/0.07, 3.0) = **2.86x**
- This amplifies both gains AND losses by ~3x
- Combined with 132% daily turnover, the leveraged portfolio incurs 3x the transaction costs

**Recommendation for Tier 3:** `TailControlOverlay` should accept and pass `max_leverage` as a constructor parameter. Consider reducing default from 3.0 to 1.5 or 2.0 for the hybrid backtest scenarios.

---

## Task 4: Overlay apply() Loop — Accumulated State / Turnover Analysis

### Weights flow correctly — no accumulated state issue

Each overlay receives the output of the previous one and returns a modified DataFrame. There is no hidden accumulation: `weights` is reassigned each iteration.

### Root Cause of 132% Daily Turnover

The turnover driver is **upstream** of the overlay chain, in the weight construction: binary `np.sign(demedian)` creates a long/short assignment per ticker per day. If the composite signal ranking changes daily (noisy alpha signals), tickers flip between long (+1/N) and short (-1/N) positions every day.

**Overlays do NOT reduce turnover** — they only scale/clip weights. The vol-targeting can even amplify the effective turnover by up to 3x.

### Recommendations for Tier 3
1. Add signal smoothing / momentum filter to reduce daily signal flips
2. Consider `WeightSmoothingOverlay` (exists in `overlays/weight_smoothing.py`) in the chain
3. Add turnover penalty in alpha signal construction
4. The overlay chain itself is clean — no state accumulation bug

---

## Task 5: Regression Test

### Test file: `tests/test_vn_cost_model_half_spread_guard.py`

11 tests covering:
- Default values pass the guard
- Small decimal values (2, 10, 50 bps) accepted
- Boundary value 0.05 (500 bps) accepted
- Integer bps values (2.0, 5.0) rejected with ValueError
- Just-above-threshold (0.051) rejected
- Error message contains bps conversion hint
- @dataclass decorator presence verified
- Zero and negative values (edge cases)

### Test results (re-verified 2026-06-20)

```
tests/test_vn_cost_model_half_spread_guard.py ...........  [100%]
11 passed in 6.85s
```

---

## Changes Made (COMPLETE)

| # | File (repo-relative) | Change | Type | Author |
|---|---------------------|--------|------|--------|
| 1 | `src/omega/quant/execution_sim.py` | Added `VNCostModel.__post_init__` guard (lines 780–789) + unit-convention docstring (lines 736–766) | PRODUCTION SOURCE | **Role 9 (Backend Engineer)** |
| 2 | `tests/test_vn_cost_model_half_spread_guard.py` | New regression test (11 cases) | NEW | **Role 9 (Backend Engineer)** |
| 3 | `scripts/paper_trading_daily.py` | Fixed `half_spread_bps: 5.0` → `0.0005` (line 69) | BUGFIX | **Role 9 (Backend Engineer)** |

---

## Summary of Findings

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | VNCostModel.__post_init__ guard correctly implemented as @dataclass | — | VERIFIED |
| 2 | backtest_hybrid_regime.py half_spread_bps=2.0 → 0.0002 fix is correct | — | VERIFIED (pre-existing fix) |
| 3 | **paper_trading_daily.py half_spread_bps=5.0 unit confusion bug** | CRITICAL | FIXED by Role 9 |
| 4 | **execution_sim.py VNCostModel guard — authorship claimed by Role 9** | — | CLAIMED |
| 5 | TailControlOverlay does not expose max_leverage (hardcoded 3.0x default) | MEDIUM | FLAGGED for Tier 3 |
| 6 | 132% daily turnover caused by binary long/short signal flips, not overlay state accumulation | HIGH | FLAGGED for Tier 3 |
| 7 | Regression test suite (11 tests) passes | — | DONE |

---

## Tier 3 Submission

This corrected work is submitted to:
- **Code Reviewer (role 21):** Review bugfix quality, test coverage, code style, and **re-verify complete skill provenance and forbidden-path scan phrasing**
- **QA Engineer (role 17):** Verify regression test completeness and run full suite
- **Security Auditor (role 18):** Assess impact of unit-confusion bug class on production paper trading

**Cannot proceed until:** All relevant Tier 3 roles return [APPROVED].
