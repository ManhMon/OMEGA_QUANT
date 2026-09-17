# L2 Runtime Report: VCI Incremental Update v2 Rerun

- Role: `data-engineer` (role ID `15`, Tier `2`, OpenCode).
- Session: `l2_role15_vci_incremental_update_v2_rerun_20260731_20260803`.
- Scope: runtime only. No source, test, or configuration edits.
- Requested command: `python scripts/update_market_data.py --end 2026-07-31`.
- Outcome: `NEEDS_FIX`; no audit or approval performed.

## Repo-Local Source Evidence

Read from `REPO_AGENT_ROOT` / `REPO_SKILL_ROOT` only:

- `.agents/agent/data-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

Role frontmatter validated: `name=data-engineer`, `role_id=15`, `tier=2`, `platform=OpenCode`; filename matches.

Forbidden-path scan: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` are non-authoritative. No authoritative reliance or access occurred.

## Preflight

- `python scripts/update_market_data.py --help`: PASS; `--end` supported.
- Canonical: `data/market_2015_now.parquet`.
- Pre-run canonical length: `21,585,675` bytes.
- Pre-run canonical last-write UTC: `2026-07-02T23:48:38.4390699Z`.
- Pre-run canonical SHA-256: `3446ab3edf79908c6d2b13a0aa16f6d8ab9c4319e83d4838209cf9d1bcac99ad`.
- Pre-run pointer: `data/market_current.json` absent.
- Pre-run release root: `data/market_releases` exists; no release manifest was found.
- Existing projection SHA-256: `32c524e3d410c660d41c015ca0630bb217ff7cb3df3cea835d8057de051ca2da`.

## Execution

```powershell
python scripts/update_market_data.py --end 2026-07-31
```

- Runtime emitted VCI fetch progress for the full `703`-symbol universe, including VND_FULL conversion events.
- No new projection, terminal receipt, signed v2 authority, release manifest, or pointer was published after command completion.
- Latest retained projection remains `validation_failed`: `13,039` duplicate `(ticker, date)` rows and `1,470,532` `available_at` PIT errors.
- Latest retained terminal receipt remains `.ly_state/session/market_data_receipts/20260803T102612206694Z_fdb50f696743444ab131971f54ea4806.terminal.json`.
- Retained terminal receipt SHA-256: `be0203da56e0b5d15645d1d686e01b12544d9dcda387fe97b94d923e619551f1`.
- Terminal receipt is schema v2, `terminal`, `pit_evidence_invalid`, `published=false`, `stale=true`, `execution_allowed=false`. Signing values omitted.

## Preservation And Reconciliation

- Post-run canonical length: `21,585,675` bytes.
- Post-run canonical last-write UTC: `2026-07-02T23:48:38.4390699Z`.
- Post-run canonical SHA-256: `3446ab3edf79908c6d2b13a0aa16f6d8ab9c4319e83d4838209cf9d1bcac99ad`.
- Canonical unchanged.
- Post-run pointer: `data/market_current.json` absent, unchanged.
- No release generation or signed v2 authority was published; pointer precedence was never reached.
- Reconciliation snapshot retained: `.ly_state/session/market_data_reconciliation_latest.json`, `status=ok`, `as_of_date=2026-07-24`, primary `vnstock_vci`, reference `vnstock_kbs`.
- KBS remains warning-only. It did not authorize, block, alter, or publish VCI data.

## Handoff

The rerun remains fail-closed under the retained duplicate/PIT validation failure. Canonical and pointer preservation verified. Remediation requires a new L2 session after the required lesson-extraction gate; do not force publication.
