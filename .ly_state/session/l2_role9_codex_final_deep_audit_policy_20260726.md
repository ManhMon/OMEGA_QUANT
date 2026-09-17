# L2 Role 9 Report: Codex Final Deep Audit Policy

## Scope

- Updated `.agents/AGENTS.md` required-flow references.
- Replaced the obsolete Claude-specific final deep audit dispatch rule with Codex CLI model `cx/gpt-5.6-sol`.
- Preserved Codex L3 `[APPROVED]` as the sole approval authority.
- Defined the final deep audit as advisory, read-only, after L3 approval and before the final enforcer.
- Prohibited final deep audit edits to source, tests, phase gates, and audit reports.
- Added the exact safe command pattern using `echo`, `codex exec`, `-m cx/gpt-5.6-sol`, and `--dangerously-bypass-approvals-and-sandbox`.

## Verification

- Focused wording search confirms no Claude-specific dispatch rule remains in `.agents/AGENTS.md`.
- Focused wording search confirms the required Codex model, ordering, read-only boundary, advisory status, and command flags.
- `python scripts/lint_sod_report_evidence.py .ly_state/session/l2_role9_codex_final_deep_audit_policy_20260726.md --gate CODEX_FINAL_DEEP_AUDIT_POLICY_20260726` passes.

## Repo-Local Files Read

- `REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`
- `REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`
- `.agents/AGENTS.md`
- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/documentation-templates/SKILL.md`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.

## Remediation Addendum

- Removed only the unrelated canonical-lint early-feedback additions from the L2 and L3 dispatch templates in `.agents/AGENTS.md`.
- Authoritative roots remained unchanged: `REPO_ROOT=C:\Users\GHC\repos\OMEGA_QUANT`, `REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`, and `REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`.
- Preserved the final Codex deep audit rule, final `python scripts/sod_gate_enforcer.py` command, Plan Approval Rule, lesson policy, and preexisting dispatch language.
- Evidence: `.agents/AGENTS.md` diff contains only the Claude-to-Codex final audit replacement, Plan Approval Claude removal, and removal of the two canonical-lint additions.
- No phase gates, audit reports, source, or tests were edited.

## Verdict

Policy update complete. No source, tests, phase gates, or audit reports modified by the final deep audit policy.
