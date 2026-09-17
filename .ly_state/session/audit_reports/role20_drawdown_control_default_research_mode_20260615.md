# Compliance Audit Report

**Role**: Compliance Officer (Role 20)
**Date**: 2026-06-15T00:00:00+07:00
**Gate**: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615
**Submission**: l2_role14_drawdown_control_default_research_mode_20260615
**Tier 2 Engineer**: data-scientist (Role 14)
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/vulnerability-scanner/checklists.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`
- `.agents/agent/data-scientist.md`
- `.ly_state/session/l2_role14_drawdown_control_default_research_mode_20260615.md`
- `scripts/run_phase35_backtest.py`
- `tests/phase35/test_drawdown_control_default_on_cli.py`
- `tests/phase35/test_stage6_3_drawdown_control.py`
- `tests/phase35/test_xgboost_default_off_cli.py`
- `data/phase35_results/phase35_backtest_results_dd_control_10_default_clean_v3_wg_baseline.json`
- `data/phase35_results/phase35_backtest_results_full_e2e_default_clean_v3_wg_no_xgb_baseline.json`
- `data/phase35_results/phase35_backtest_summary_dd_control_10_default_clean_v3_wg_baseline.txt`
- `data/phase35_results/phase35_backtest_summary_full_e2e_default_clean_v3_wg_no_xgb_baseline.txt`

Note: `sops/SKILL.md` references optional SOP detail files, but those files are not present. No role-declared skill source was missing; embedded SOP_AC/BACKTEST/PIT rules in `sops/SKILL.md` were used.

## Forbidden Path Scan

No authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

## Checks

- Writer != auditor: PASS. L2 role_id 14 != L3 role_id 20.
- L3 boundary: PASS. Audit writes limited to `.ly_state/session/audit_reports/` and `.ly_state/session/phase_gates.json`.
- Scope compliance: PASS. Reviewed scoped CLI, new test, related Phase35 tests, L2 report, and evidence artifacts.
- Default-on behavior: PASS. `scripts/run_phase35_backtest.py` sets `args.drawdown_control = not args.disable_drawdown_control`; default is enabled.
- Threshold default: PASS. `--drawdown-threshold` default is `0.10`.
- Opt-out behavior: PASS. `--disable-drawdown-control` makes `drawdown_control=False`.
- Backward compatibility: PASS. `--drawdown-control` remains accepted and is documented as deprecated no-op; disable flag wins when both are passed.
- Config/log/help persistence: PASS. Help text cites gate/evidence, log reports default/opt-out state, result JSON persists `drawdown_control` and `drawdown_threshold`.
- Evidence citation: PASS. Controlled artifact: PortfolioIC `0.03440094686947181`, Sharpe `3.1570130917114425`, MaxDD `-0.12343066627400955`, `drawdown_control=true`, threshold `0.1`. Baseline artifact: same PortfolioIC, Sharpe `2.3273367227028703`, MaxDD `-0.6699281477819367`, `drawdown_control=false`.
- No live alpha promotion: PASS. Change is CLI research default/opt-out behavior; no alpha promotion path modified.
- PIT safety: PASS. Drawdown control acts on realized test-fold returns and related existing tests cover test-fold-only behavior; no future label/date access introduced by this CLI default change.
- L2 repo-local evidence: FAIL. L2 report lists repo-local role/skill files, but `scripts/sod_gate_enforcer.py` rejects the L2 report because each forbidden-path mention must include the required non-authoritative context marker.
- Security/compliance: PASS. CLI flags introduce no new external input sink, secrets, network access, auth, or data exposure path.

## Verification Run

- `python scripts/run_phase35_backtest.py --help` PASS. Real argparse help includes `--drawdown-control`, `--disable-drawdown-control`, threshold default rationale, gate, and evidence text.
- `python -m pytest tests/phase35/test_drawdown_control_default_on_cli.py tests/phase35/test_stage6_3_drawdown_control.py tests/phase35/test_xgboost_default_off_cli.py -q` PASS: 54 passed.
- `python -m pytest tests/phase35 -q` PASS: 514 tests passed by progress count.

Warnings observed are existing deprecation/statistical warnings plus pytest cache write warning; none affect this gate.

## Findings

1. BLOCKING: L2 report forbidden-path wording fails strict gate enforcement. `python scripts/sod_gate_enforcer.py` reports that `.ly_state/session/l2_role14_drawdown_control_default_research_mode_20260615.md` mentions `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` without the required non-authoritative context marker on every forbidden-path mention. L2 must update the report wording and resubmit.

## CODEX AUDIT VERDICT

**Status:** [NEEDS_FIX]
**Date:** 2026-06-15T00:00:00+07:00
**Auditor:** Codex L3 Compliance Officer (Role 20)
**Scope:** Drawdown control default-on research mode for Phase35 CLI.
**audit_report_path:** `.ly_state/session/audit_reports/role20_drawdown_control_default_research_mode_20260615.md`
**final_verdict:** [NEEDS_FIX]

**Rationale:** Implementation behavior, evidence, PIT checks, and tests pass, but strict SOD gate enforcement blocks the submission due L2 report forbidden-path wording. Gate cannot be approved until L2 fixes the report and enforcer exits 0.
