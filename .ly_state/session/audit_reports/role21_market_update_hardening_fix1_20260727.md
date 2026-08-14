# Code Review Audit Report — Fix1

**Role**: Code Reviewer (Role 21, L3 Codex)  
**Date**: 2026-07-27  
**L2**: Role 15 `data-engineer`; `l2_role15_production_market_update_hardening_fix1_20260727`  
**Scope**: `scripts/update_market_data.py`, `tests/test_market_release_gates.py`; production-state boundary.

## Repo-Local Source Evidence

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/l2_role15_production_market_update_hardening_fix1_20260727.md`

Forbidden-path scan is non-authoritative only. Writer Role 15 differs from auditor Role 21.

## Hardening

- **PASS**: Watermark reaches `validate_release_gates`; regression rejects publication.
- **PASS**: `(ticker, date)` duplicates reject before release publication.
- **PASS, code only**: A post-pointer exception restores saved pointer bytes and writes `quarantine.json`.
- **FAIL**: No regression test injects a failure *after* `pointer_swapped=True` (for example `prune_releases`). Current pointer-failure test fails before the swap, so rollback is unproven.
- **FAIL**: PIT-manifest retention is not a separate retention class. Every published release has `pit_manifest.json`; it still enters `normal`, then `normal[RELEASE_RETENTION:]` deletes the whole directory, including the PIT manifest, long before `PIT_MANIFEST_RETENTION_DAYS`.
- **FAIL**: Manifest records candidate SHA-256 only. It records `canonical_path`, not canonical-parquet SHA-256; baseline identity is unverifiable.
- **FAIL**: No tests cover retention classes, PIT-manifest preservation, canonical hash persistence, or post-swap rollback/quarantine.

## Production Boundary / Forensics

- **FAIL**: Live `data/market_current.json` exists and selects run `20260727T194815410147Z_69d74953`, a `published` five-row candidate. Pointer, manifest, and candidate hash agree: `e7176127722dc7d17db817ab355a262b7e217fcb0be488ed7e8e6bda7de412d3`.
- **FAIL**: This state remains unauthorized. It was recreated after the prior rollback; it is untracked (`?? data/market_current.json`, `?? data/market_releases/`) and no production refresh was authorized.
- **PASS**: Canonical `data/market_2015_now.parquet` remains unchanged from `HEAD`; observed SHA-256: `3446ab3edf79908c6d2b13a0aa16f6d8ab9c4319e83d4838209cf9d1bcac99ad`.
- **Evidence gap**: No active external producer process matching updater/pointer/release paths was present during audit. The only matching scheduled task runs `C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\scripts\paper_trading_node.py`, not this repository updater. No file-backed attribution identifies who recreated the pointer.

## Exact Safe Recovery

1. L1 opens one recovery-only L2 session; prohibit refresh/download/publication.
2. Freeze all updater writers and pointer consumers. Preserve hashes above plus both live manifests before changing state.
3. With no writer present, atomically remove `data/market_current.json`; do not replace it with an unverified pointer.
4. Move active and orphan release directories into a dated quarantine/forensics location, retaining manifests and candidate hashes; do not delete evidence.
5. Re-check after a monitored interval: pointer absent, no directory recreation, canonical SHA-256 still `3446ab...c99ad`, and data paths no longer untracked.
6. Attribute or disable the recreating producer before any future publication. Then add failing-path tests and re-audit.

## Verification

`PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/test_market_release_gates.py tests/test_vci_updater_validation_write_blocker.py -q --cache-clear -o cache_dir=.ly_state/session/pytest_tmp_role21_market_fix1 --basetemp=.ly_state/session/pytest_tmp_role21_market_fix1_tmp`  
Result: `10 passed`.

## Verdict

[NEEDS_FIX]
## Post-Report Live Recheck

At 2026-07-27 19:51 +07:00, the unauthorized pointer recreated again during this audit: run `20260727T195154822094Z_6de403ad`, pointer SHA-256 `596f290f23ea253398ab2ffa60596ecc0409a3a6eff86431dcf4cf6a7ded428d`, candidate SHA-256 `e7176127722dc7d17db817ab355a262b7e217fcb0be488ed7e8e6bda7de412d3`, release directories `8`. No matching active external producer process was observable. This proves recovery cannot safely proceed until the writer is isolated.