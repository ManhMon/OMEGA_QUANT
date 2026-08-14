# Official Exchange Lifecycle Evidence Discovery

**Role**: data-engineer (Role 15, L2 OpenCode)
**Session**: `l2_role15_official_exchange_lifecycle_evidence_20260805`
**Gate**: `OFFICIAL_EXCHANGE_LIFECYCLE_EVIDENCE_20260805`
**Date**: 2026-08-05
**Outcome**: [NEEDS_FIX] external lifecycle evidence source and signed checkpoint facility unavailable.

## Discovery And Quarantine

- HSX fixed official endpoint `https://api.hsx.vn/m/api/v1.0/data-feed/files` returned HTTP 401 in the repo-local 2026-08-03 discovery evidence. It cannot provide a compliant public lifecycle notice response.
- HNX official listed-stock page `https://hnx.vn/vi-vn/co-phieu-etfs/du-lieu-thi-truong-ny.html` returned HTML. Its date-specific endpoint redirected and did not provide compliant JSON evidence.
- No repository configuration supplies an external signed lifecycle checkpoint, approved lifecycle notice endpoint, signer separation, or key revocation trust contract.
- `.ly_state/session/vci_ticker_lifecycle.json` is mutable local state. It is quarantined from updater trust decisions.

## Minimal Safe Integration

- `scripts/update_market_data.py` no longer loads mutable lifecycle state during `run_updater`.
- Sparse terminal histories receive no lifecycle exception without independently supplied compliant evidence, so release gating blocks publication.
- The updater performs no lifecycle network request.
- No lifecycle scanner, fetcher, parser, signer, endpoint, or configuration was fabricated.

## Verification

- Fixture-only regression test makes `_load_ticker_lifecycle` raise if `run_updater` calls it. The HNX candidate path remains publishable when no sparse exception is needed.
- Existing receipt tests cover invalid signatures, replay, stale PIT timestamps, and unknown keys for independently supplied evidence.

## Required Follow-Up

Provide an approved exchange lifecycle endpoint and externally signed checkpoint service with scoped verification keys, revocation data, immutable raw/manifest storage, and documented terms/robots authorization. Implement the scanner only after those inputs exist.

## Repo-Local Files Read

`REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`
`REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`

- `.agents/AGENTS.md`
- `.agents/agent/data-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan

`.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
`.openclaw\skills`: non-authoritative scan evidence only; no reliance.
`C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
`.codex\memories`: non-authoritative scan evidence only; no reliance.
