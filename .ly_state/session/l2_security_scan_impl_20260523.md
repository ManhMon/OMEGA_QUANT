# L2 Implementation: Automated Security Scanning
**Role**: DevOps Engineer (Role 11)  
**Date**: 2026-05-23T11:36:33Z  
**Gap Reference**: docs/FUNCTIONALITY_GAP_ANALYSIS_20260523.md — P1 Gap #3 (Security: Missing Automated Scanning)  
**Status**: COMPLETE ✅

---

## Summary

Implemented automated security scanning for OMEGA_QUANT integrating Bandit (AST-based Python security linting) and Safety (dependency vulnerability checking) with full CI/CD support.

---

## Deliverables

### 1. `scripts/run_security_scan.py` (new)
- Integrates **Bandit** (`-m bandit`) for AST-level Python security scanning
- Integrates **Safety** (`-m safety check`) for known CVE dependency scanning
- Configurable severity threshold (`--severity low|medium|high`, default: `medium`)
- Configurable scan targets (`--path`, default: `packages scripts src`)
- JSON reports written to `--output-dir` (default: `.ly_state/security/`)
  - `bandit_report.json` — full Bandit output
  - `safety_report.json` — full Safety output
  - `security_scan_summary.json` — combined summary
- **CI/CD mode**: `--fail-on-vuln` exits with code `1` when issues found
- Exit codes: `0` = clean, `1` = issues found, `2` = tool error
- `--skip-bandit` / `--skip-safety` flags for selective scanning

### 2. `pyproject.toml` (updated)
- Added `[project.optional-dependencies]` section:
  - `security-scan` extra: `bandit[toml]>=1.7.5`, `safety>=2.3.5`
  - `dev` extra: same tools + pytest/pytest-cov
- Install with: `pip install -e ".[security-scan]"`

### 3. `packages/security/pyproject.toml` (updated)
- Added `[project.optional-dependencies].scan` with same pinned versions
- Added `[tool.bandit]` config block (excludes `tests/`, `__pycache__/`)

---

## Verification

```
python scripts/run_security_scan.py --severity medium --fail-on-vuln
Exit code: 1  ✅ (non-zero on issues found)
```

**Bandit findings** (12 issues at severity>=medium — pre-existing, not introduced by this PR):
| Severity | File | Issue |
|----------|------|-------|
| HIGH | packages/data/src/omega/data/loader.py:440 | Weak MD5 hash |
| HIGH | packages/execution/src/omega/execution/broker_gateway.py:106 | Weak MD5 hash |
| HIGH | packages/observability/src/omega/observability/neural_memory.py:81,88 | Weak MD5 hash |
| HIGH | packages/quant/src/omega/quant/evolution/atomic_snapshot_manager.py:152 | tarfile.extractall no validation |
| HIGH | scripts/sod_automation_runner.py:43,96 | subprocess shell=True |
| MEDIUM | packages/core/src/omega/core/sre/kill_switch.py:76 | Insecure temp file |
| MEDIUM | packages/quant/src/omega/quant/alpha_discovery.py:525 | eval() usage |
| MEDIUM | packages/quant/src/omega/quant/dashboard.py:371 | urlopen file:/ scheme |
| MEDIUM | packages/quant/src/omega/quant/evolution/atomic_snapshot_manager.py:156 | Pickle deserialization |
| MEDIUM | packages/quant/src/omega/quant/factory/discovery_engine.py:135 | eval() usage |

**Safety findings**: 0 known CVEs ✅

---

## Assumptions

1. Bandit and Safety installed into active Python environment (`pip install "bandit[toml]>=1.7.5" "safety>=2.3.5"`).
2. The 12 Bandit findings are **pre-existing** in the codebase — not introduced by this implementation. They are surfaced for the first time by this scanner and should be triaged separately.
3. Safety v2+ JSON format used; script handles both v1 (list) and v2 (dict) output for forward/backward compatibility.
4. `--fail-on-vuln` is the recommended CI flag; omitting it allows informational-only runs.

---

## CI/CD Integration

Add to CI pipeline (GitHub Actions example):
```yaml
- name: Security Scan
  run: python scripts/run_security_scan.py --severity medium --fail-on-vuln
```

Or for non-blocking informational scan:
```yaml
- name: Security Scan (informational)
  run: python scripts/run_security_scan.py --severity medium
  continue-on-error: true
```

---

## Next Steps (out of scope for this L2)

- Triage the 12 pre-existing Bandit findings (assign to relevant package owners)
- Add OWASP ZAP integration for HTTP endpoint scanning (Phase 8 spec)
- Add OAuth integration (separate P1 gap, see `l2_oauth_impl_20260523.md`)
