# L3 Audit — Phase 7 Capacity Sweep + Falsification (Codex 2-step retroactive)

**Date**: 2026-05-30 14:11 GMT+7
**Auditor**: Role21-CodeReviewer (Codex CLI v0.134.0)
**Codex session**: `019e77b7-90bb-74c1-afee-794be5e1c3b9`
**Rollout**: `~/.codex/sessions/2026/05/30/rollout-2026-05-30T14-09-39-019e77b7-*.jsonl`
**Wall time**: ~1.5 min, multi-file read + cross-check.
**Invocation**: SOUL.md Rule 9.1 (stdin pipe).
**Replaces**: prior Python audit `phase7_audit_python.stdout` (Phase 7 was originally audited by `scripts/audit_phase7.py` only).

## Verdict

**[APPROVED]** — All 6 invariants satisfied with margin. 1 cosmetic P2 finding.

## Findings

All findings are P2 (cosmetic / hardening, not blocking):

1. **`scripts/audit_phase7.py:79`** — Mojibake in not-monotone error message (UTF-8 arrow corrupted). No functional impact since check passes. **STATUS**: deferred.
2. **`scripts/audit_phase7.py:24`** — Shuffle artifact identified by filename only; doesn't cross-check JSON `label` field. Mis-named artifact could silently pass. **STATUS**: deferred.
3. Tolerance for slippage linearity is 10% in script, user spec was ~5%. Both satisfied (actual ratios are 0.000% rel_err). **STATUS**: tighten optional, not required.

## Confirmed by codex

| # | Invariant | Observed | Status |
|--|--|--|--|
| 1 | Alpha invariance | median_test_ic = 0.017292154827137016 IDENTICAL bit-for-bit across 1B/5B/10B/30B/50B/100B | PASS |
| 2 | Capacity monotone | fold_SR_ann: 3.6715 → 3.5167 → 3.3195 → 2.5264 → 1.7795 → 0.1883 strictly decreasing | PASS |
| 3 | Slippage linearity | Ratios 5.000/2.000/3.000/1.6667/2.000 match capital ratios with **rel_err = 0.000%** | PASS |
| 4 | Commission/spread/turnover invariance | Bit-for-bit identical (range diff = 0.0) for all 6 capitals | PASS |
| 5 | Falsification y-shuffle | fold_SR collapses 76.1% (3.67 → -0.88), IC sign-flips +0.017 → -0.018 | PASS |
| 6 | Fold stability | 36/45 = 80% positive folds (mean +0.231, median +0.232, std 0.264) | PASS |

## Cross-validation

Codex verified that:
- `phase5_capacity_report.txt` printed values reproduce exactly from JSON sources
- `audit_phase7.py` script logic correctly encodes each of the 6 invariants
- Sign-flip-OR-magnitude criterion in FALS-IC is correct (sign-flip is the discriminator since shuffle |IC| is 105.7% of real magnitude)

## SOD/PIT

- `audit_phase7.py` is read-only on pre-computed JSON artifacts.
- No data join, no model fit, no file writes.
- Cannot induce look-ahead leakage.
- Verdict aggregation `overall &= ok` across independent checks; no self-approval path.
- L3 (Codex) reading L2 (OpenCode) artifacts. Writer ≠ Reviewer.

## Disposition

**Phase 7 gate APPROVED** with codex audit (replacing prior Python-only audit).
P2 findings deferred — no blocking issues for production.

## Evidence chain

- `.ly_state/session/phase7_codex_audit.stdout` — codex agent_message extracted
- `~/.codex/sessions/2026/05/30/rollout-2026-05-30T14-09-39-*.jsonl` — full session log
- Original Python audit: `.ly_state/session/phase7_audit_python.stdout` (kept as supplementary evidence)
