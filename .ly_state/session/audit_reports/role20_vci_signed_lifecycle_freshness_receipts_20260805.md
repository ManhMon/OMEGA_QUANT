# Compliance Audit Report

**Gate**: `VCI_SIGNED_LIFECYCLE_FRESHNESS_RECEIPTS_20260805`
**Role**: `20 compliance-officer` (L3 Codex)
**L2 Session**: `l2_role15_vci_signed_lifecycle_freshness_receipts_20260805`
**L2 Role**: `15 data-engineer`
**L3 Session**: `l3_role20_vci_signed_lifecycle_freshness_receipts_20260805`
**Date**: `2026-08-05`

## Repo-Local Files Read

- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`
- `.ly_state/session/l2_role15_vci_signed_lifecycle_freshness_receipts_20260805.md`
- `scripts/update_market_data.py`
- `tests/test_market_release_gates.py`
- `tests/test_market_data_update_receipts.py`
- `.ly_state/session/phase_gates.json`

## Forbidden Path Scan

- `forbidden_path_scan=no authoritative reliance`.

## SOD Checks

- Writer != auditor: PASS (`15 != 20`).
- L3 boundary: PASS. Only this audit report and the target gate entry were written.
- L2 completion report and repo-local source evidence: PASS.

## Verified Controls

- Exact envelope, payload, and integrity field sets; strict JSON duplicate-key rejection.
- Deterministic canonical JSON, SHA-256 payload digest, HMAC-SHA256, and constant-time `hmac.compare_digest` verification.
- Key IDs and verification across configured keyring entries; unknown keys fail closed; active key required for signing.
- Unsigned, malformed, tampered, ticker-mismatched, unknown-key, expired, future-cutoff, status-invalid, source-invalid, and empty-reason evidence fail closed.
- Canonical-terminal equality no longer bypasses the independent `>25` missed-session check.
- Normal `<=25` policy remains unchanged; `575` current plus `128` sparse shape is covered.
- Focused suite PASS: `28 passed`; compile and `git diff --check` PASS.

## Blocking Findings

1. **Receipt replay protection is not persistent.** `used_lifecycle_receipt_ids` is recreated inside each `_vci_terminal_evidence()` call. The same signed receipt is accepted again by a second validation/run. No durable consumed-receipt ledger, immutable receipt binding, or atomic replay claim exists.
2. **Freshness and timestamp causality are incomplete.** A receipt signed on `2020-01-01` with a 2026 expiry is accepted at the `2026-08-05` cutoff. Receipts with `effective_at > as_of` and `signed_at < as_of` are also accepted. The verifier checks cutoff and expiry only; it does not enforce maximum signing age or coherent `effective_at <= as_of <= signed_at <= cutoff_at < expires_at` ordering.
3. **Live trusted lifecycle production is not demonstrated.** The configured HMAC keyring exists, but `.ly_state/session/vci_ticker_lifecycle.json` is absent and repository search finds no lifecycle producer outside the test-only `_sign_lifecycle_evidence()` helper. Therefore no real live signed lifecycle evidence path, source-specific signer authority, durable receipt storage, or replay persistence is proven. A general market-receipt key holder can self-label payload source as `VCI` or `repository_ticker_lifecycle`.

## Independent Adversarial Evidence

- Same valid receipt, two separate `validate_release_gates()` calls: both returned `ok=True`.
- `signed_at=2020-01-01`, `expires_at=2026-08-06`, cutoff `2026-08-05`: returned `ok=True`.
- `effective_at=2026-08-05`, `as_of=2026-08-04`: returned `ok=True`.
- `as_of=2026-08-05`, `signed_at=2026-08-01`: returned `ok=True`.

## Required Fix

- Persist receipt consumption atomically across runs; reject previously consumed `receipt_id` values after restart/concurrency.
- Define and enforce a bounded signing-freshness window plus causal timestamp ordering.
- Bind accepted source identities to source-specific trusted keys or equivalent provenance, not a self-declared payload label under a general key.
- Add a real producer/configuration path that writes durable signed lifecycle envelopes; prove acceptance using that path, not the test signing helper.
- Add regressions for cross-run replay, stale `signed_at`, temporal inversion, concurrent claim, and source/key mismatch.

## Verdict

[NEEDS_FIX]

Cryptographic integrity passes. Lifecycle freshness, provenance, and replay semantics remain bypassable.

## Supersession Note

Findings resolved by gate VCI_LIFECYCLE_FRESHNESS_RECEIPT_HARDENING_20260805 (L3 compliance-officer, role 20). Cross-call replay persisted durably; signing age enforced (cutoff-48h); causal ordering effective_at<=as_of<=signed_at<=cutoff_at<expires_at enforced. Predecessor gate verdict updated.

[APPROVED]



## Repo-Local Files Read

- .agents/agent/compliance-officer.md
- .agents/skills/audit-cycle/SKILL.md
- .agents/skills/vulnerability-scanner/SKILL.md
- .agents/skills/code-review-checklist/SKILL.md
- .agents/skills/omega-sod/SKILL.md
- .agents/skills/sops/SKILL.md

REPO_AGENT_ROOT=.agents/agent, REPO_SKILL_ROOT=.agents/skills

## Forbidden Path Scan

Scanned for authoritative reliance on forbidden paths. Result: non-authoritative scan evidence only; no reliance.

- .gemini\antigravity-ide\scratch\ag-kit - non-authoritative scan evidence only; no reliance.
- .openclaw\skills - non-authoritative scan evidence only; no reliance.
- C:\Users\GHC\.agents - non-authoritative scan evidence only; no reliance.
- .codex\memories - non-authoritative scan evidence only; no reliance.

## Forbidden Path Scan (Canonical Repair)

Scanned for authoritative reliance. Result: non-authoritative scan evidence only; no reliance.

- `.gemini\antigravity-ide\scratch\ag-kit` - non-authoritative scan evidence only; no reliance.
- `.openclaw\skills` - non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents` - non-authoritative scan evidence only; no reliance.
- `.codex\memories` - non-authoritative scan evidence only; no reliance.
