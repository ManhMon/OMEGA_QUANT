# L2 Implementation Report: Drawdown Regime Re-Entry Filter Fix

**Role**: 14 data-scientist (Tier 2)
**Date**: 2026-06-17
**Gate**: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
**Scope**: `src/omega/quant/alpha/phase35.py`

---

## 1. Repo-Local Files Read

### Agent Definition (1 file)
| # | File (repo-relative) | Status |
|---|---------------------|--------|
| 1 | `.agents/agent/data-scientist.md` | READ OK |

**Frontmatter parsed**: name=data-scientist, role_id=14, tier=2, platform=OpenCode, 9 skills declared.

### Skills (9 files)
| # | File (repo-relative) | Status |
|---|---------------------|--------|
| 1 | `.agents/skills/python-patterns/SKILL.md` | READ OK |
| 2 | `.agents/skills/clean-code/SKILL.md` | READ OK |
| 3 | `.agents/skills/testing-patterns/SKILL.md` | READ OK |
| 4 | `.agents/skills/systematic-debugging/SKILL.md` | READ OK |
| 5 | `.agents/skills/performance-profiling/SKILL.md` | READ OK |
| 6 | `.agents/skills/quant-research/SKILL.md` | READ OK |
| 7 | `.agents/skills/vietnam-market-data/SKILL.md` | READ OK |
| 8 | `.agents/skills/backtesting-pit-safety/SKILL.md` | READ OK |
| 9 | `.agents/skills/data-science-workflow/SKILL.md` | READ OK |

### Forbidden Path Scan
| Path | Result |
|------|--------|
| Antigravity scratch (non-authoritative, not used as source) | NOT ACCESSED |
| OpenClaw (non-authoritative, not used as source) | NOT ACCESSED |
| `.agents/Codex` memory (non-authoritative, not used as source, external path `C:\Users\GHC\.agents` never accessed) | NOT ACCESSED |

**Grep scan** of `.agents/` for `Antigravity|OpenClaw|C:\Users\GHC\.agents` (all non-authoritative, not used as source) returned **0 matches**.

---

## 2. L3 Audit Findings Addressed

### Finding 1: Insufficient trailing history for `detect_market_regime` in `_close_wide`

**Problem**: `_close_wide` was built from `test_df` only (line 4928 original). `detect_market_regime` requires trailing MA/vol windows (e.g., 200-day MA, 20-day vol, 60-day median vol). Early test dates had insufficient lookback, causing regime detection to fail silently or return unreliable results.

**Fix**: Combined `train_df` and `test_df` close prices via `pd.concat` when building `_close_wide`, ensuring sufficient trailing history. PIT-safe because `train_df` close prices are already-observed historical data, not future information.

```python
# Before (line 4928):
_work_close = test_df[["date", "ticker", "close"]].copy()

# After:
_work_close = test_df[["date", "ticker", "close"]].copy()
if train_df is not None and not train_df.empty:
    _train_close = train_df[["date", "ticker", "close"]].copy()
    _work_close = pd.concat(
        [_train_close, _work_close], ignore_index=True
    )
```

**Location**: `run_fold()` method, `_close_wide` building block (~line 4931).

### Finding 2: `regime_re_entry_filter_enabled` evidence flag prematurely set to `True`

**Problem**: `evidence["regime_re_entry_filter_enabled"]` was initialized to `self.drawdown_adaptive_re_entry` (line 2909 original), which is `True` whenever adaptive re-entry is configured. However, the regime filter is only functional when both:
1. `detect_market_regime` is successfully lazy-imported, AND
2. `close_wide` is available (not None).

Setting the flag to `True` prematurely could mislead downstream consumers into believing the regime filter was active when it may not have been.

**Fix**: Initialized `evidence["regime_re_entry_filter_enabled"] = False`. Set to `True` only after the lazy import block succeeds and `close_wide is not None`.

```python
# Before (line 2909):
"regime_re_entry_filter_enabled": self.drawdown_adaptive_re_entry,

# After:
"regime_re_entry_filter_enabled": False,

# Added after lazy import block:
if _detect_regime_fn is not None and close_wide is not None:
    evidence["regime_re_entry_filter_enabled"] = True
```

**Location**: `_apply_drawdown_control()` method (~lines 2911, 2944-2947).

---

## 3. Test Results

| Test Suite | Tests | Result |
|-----------|-------|--------|
| `tests/phase35/test_drawdown_control_re_entry.py` | 32 | PASSED |
| `tests/phase35/test_stage6_3_drawdown_control.py` | 5 | PASSED |
| `tests/phase35/test_drawdown_control_default_on_cli.py` | 29 | PASSED |
| **Full `tests/phase35/`** | **1014** | **ALL PASSED** |

---

## 4. SOD Boundary

This is implementation-only work. No self-approval. Submitted to Tier 3 (Code Reviewer role 21 + QA Engineer role 17) for audit.
