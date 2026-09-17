# L2 Implementation Report: Audit Wiring Fix
**Role**: [L2-Impl:Role9-BackendEngineer]  
**Date**: 2026-06-09  
**Time**: 08:20 UTC  
**Task**: Fix wiring audit false positives after monolith migration

---

## Executive Summary
Successfully fixed the audit_wiring.py script to eliminate 6 false positive orphan file reports from legacy compatibility roots (`src/evolution`, `src/features`, `src/indicators`). The audit now correctly focuses on canonical `src/omega/quant/*` package wiring by default.

---

## Changed Files

### 1. `scripts/audit_wiring.py`
**Changes**:
- Added `argparse` import for CLI flag support
- Introduced `LEGACY_COMPAT_ROOTS` constant: `{'evolution', 'features', 'indicators'}`
- Added `--include-legacy` CLI flag (optional, backward compatible)
- Modified file collection logic to skip legacy roots by default (lines 49-73)
- Updated report header to indicate exclusion status

**Key Logic**:
```python
# Skip legacy compat roots unless explicitly requested
if not args.include_legacy and len(mod_parts) > 0 and mod_parts[0] in LEGACY_COMPAT_ROOTS:
    continue
```

### 2. `tests/test_audit_wiring.py` (NEW)
**Purpose**: Regression test for legacy root exclusion behavior

**Test Coverage**:
- `test_audit_wiring_excludes_legacy_by_default()`: Verifies 6 legacy modules are NOT in default output
- `test_audit_wiring_includes_legacy_with_flag()`: Verifies 6 legacy modules ARE included with `--include-legacy`

---

## Verification Results

### 1. Default Audit (Legacy Excluded)
**Command**: `python scripts/audit_wiring.py`

**Output**:
```
========================================================================
WIRING AUDIT (RESOLVED RELATIVE IMPORTS) - UNIMPORTED/ORPHAN MODULES IN src/
(Excluding legacy compatibility roots: evolution, features, indicators)
========================================================================

========================================================================
Total unimported files in src/: 0
========================================================================
```

**Result**: ✓ PASS - Zero false positives, legacy roots excluded

### 2. Audit with Legacy Included
**Command**: `python scripts/audit_wiring.py --include-legacy`

**Output**:
```
========================================================================
WIRING AUDIT (RESOLVED RELATIVE IMPORTS) - UNIMPORTED/ORPHAN MODULES IN src/
========================================================================

Package: src/evolution (2 orphan files)
------------------------------------------------------------------------
  - evolution.fitness -> src\evolution\fitness.py
  - evolution.genetic_alpha -> src\evolution\genetic_alpha.py

Package: src/features (3 orphan files)
------------------------------------------------------------------------
  - features.pit_guard -> src\features\pit_guard.py
  - features.signal_module -> src\features\signal_module.py
  - features.signal_sanitizer -> src\features\signal_sanitizer.py

Package: src/indicators (1 orphan files)
------------------------------------------------------------------------
  - indicators.alpha_discovery -> src\indicators\alpha_discovery.py

========================================================================
Total unimported files in src/: 6
========================================================================
```

**Result**: ✓ PASS - All 6 legacy files correctly detected when flag is used

### 3. Regression Tests
**Command**: `python tests/test_audit_wiring.py`

**Output**:
```
Running test_audit_wiring_excludes_legacy_by_default...
PASS: test_audit_wiring_excludes_legacy_by_default

Running test_audit_wiring_includes_legacy_with_flag...
PASS: test_audit_wiring_includes_legacy_with_flag

All tests passed!
```

**Result**: ✓ PASS - Both test cases passed

---

## Implementation Details

### Design Decisions
1. **Exclusion at Collection Time**: Legacy files are filtered during the `src_files` dictionary population (line 63-65), not during import analysis. This ensures clean separation.

2. **Explicit Opt-In for Legacy**: Used `--include-legacy` flag (not `--exclude-legacy`) to make the safe default behavior (exclude) the path of least resistance.

3. **Preserved Backward Compatibility**: Script still accepts no arguments and produces a report; only the content changed (fewer false positives).

4. **Clear User Feedback**: Report header explicitly states when legacy roots are excluded.

### Relative Import Resolution
The existing relative import resolution logic (lines 7-47) was preserved intact. The fix only affects which files are candidates for the orphan check, not how imports are resolved.

---

## Residual Risks

### 1. **False Negatives (Low Risk)**
If a canonical module under `src/omega/quant/` is genuinely orphaned but shares a name pattern with legacy roots, it would still be detected because:
- Legacy exclusion only applies to top-level `evolution/`, `features/`, `indicators/`
- `src/omega/quant/evolution/` (if it existed) would NOT be excluded

**Mitigation**: The exclusion logic checks `mod_parts[0] in LEGACY_COMPAT_ROOTS`, which only matches direct children of `src/`.

### 2. **CLI Confusion (Low Risk)**
Users unfamiliar with the change might wonder where the 6 files went.

**Mitigation**: 
- Report header explicitly states exclusion
- `--include-legacy` flag is self-documenting
- Legacy files are not deleted, only excluded from audit

### 3. **Future Legacy Roots (Medium Risk)**
If additional legacy compatibility shim packages are added (e.g., `src/backtest_compat/`), they would appear as false positives again.

**Mitigation**: 
- `LEGACY_COMPAT_ROOTS` is a clearly documented constant at line 54
- Future engineers can easily add new roots to the set
- Test suite (`test_audit_wiring.py`) provides regression protection

---

## Testing Strategy

### Test Coverage
- **Default behavior**: Legacy roots excluded, 0 orphans reported
- **Opt-in behavior**: Legacy roots included, 6 orphans reported
- **Regression protection**: Any future changes that break exclusion logic will fail tests

### Not Tested (Out of Scope)
- Deep relative import edge cases (existing logic preserved, not modified)
- Performance with large codebases (no performance changes introduced)
- Windows path handling (existing code already uses `pathlib`)

---

## Compliance Notes

### SOD Protocol
- **Implementation only**: No L3 audit requested per task spec
- **No commits**: Changes remain in working directory
- **No production deployment**: Awaiting L3 approval cycle

### Code Standards
- **PEP 8 compliant**: Used 4-space indentation, clear variable names
- **No external dependencies**: Only stdlib (`argparse`, `ast`, `pathlib`, `subprocess`)
- **Backward compatible**: Existing CI/CD scripts calling `audit_wiring.py` without flags continue to work

---

## Recommendations

### Immediate Next Steps
1. **L3 Audit**: Submit this implementation to Codex (Role 21: Code Reviewer) for approval
2. **Documentation**: Update `CONTRIBUTING.md` or `scripts/README.md` to document `--include-legacy` flag
3. **CI Integration**: Ensure CI pipelines use default `python scripts/audit_wiring.py` (no flags needed)

### Future Enhancements (Post-Approval)
1. **Configurable Exclusions**: Move `LEGACY_COMPAT_ROOTS` to `.ly_state/config/audit_config.json`
2. **HTML Report**: Add `--format html` for dashboard integration
3. **Diff Mode**: Add `--since <commit>` to show new orphans only

---

## Conclusion

The implementation successfully:
- ✓ Eliminated 6 false positive orphan reports
- ✓ Maintained backward compatibility
- ✓ Added regression test coverage
- ✓ Preserved relative import resolution logic
- ✓ Provided clear user feedback via report header

**Status**: Ready for L3 Audit  
**Confidence**: High (100% test pass rate, zero functional regressions)

---

**End of L2 Report**
