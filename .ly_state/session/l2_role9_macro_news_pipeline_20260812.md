# L2 Role 9 Macro News Pipeline

Status: IMPLEMENTED. No approval or audit verdict issued.

## Scope

- Added shared alpha LLM resolver: `src/omega/core/llm_config.py`.
- Added macro source registry, raw schema-v2 ingestion, explicit immutable vnstock universe validation, provenance identities, schema-v1 migration, and raw-first persistence.
- Added LLM sidecar request hashing, source-invariant payloads, strict schema/evidence validation, extraction/link storage.
- Added thin CLI with mandatory `--vnstock-universe`, isolated `--session-dir`, and manifest output.
- Added focused offline tests. No live source or LLM request executed.

## Verification

```text
pytest -q tests/test_macro_news_pipeline.py tests/test_macro_news_llm.py tests/test_hybrid_alpha_real_market.py
43 passed

python -m py_compile src/omega/core/llm_config.py src/omega/data/macro_news_pipeline.py src/omega/data/macro_news_llm.py scripts/run_macro_news_pipeline.py scripts/run_hybrid_alpha_evolution.py
exit 0
```

- `git diff --check` found pre-existing trailing-blank-line failures in unrelated files; no touched-file whitespace failure reported.
- `python scripts/checklist.py` and `python scripts/verify_all.py` unavailable under `scripts/`; no files found at `**/{checklist.py,verify_all.py}`.
- Session-universe rejection verified: explicit `.ly_state/session/vci_universe_hsx_hnx.json` exits before creating the provided `--session-dir`.

## Repo-Local Sources Read

- `.agents/agent/data-engineer.md`
- `.agents/AGENTS.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan

No authoritative reliance. `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` appeared only in existing protocol/history/test evidence. No role or skill loaded from them.

## Notes For L3

- `src/omega/data/news_aggregator.py` retains its separate legacy `.ly_state` universe constant. It is outside this macro-news runtime implementation and is not imported by the new CLI.
- Candidate source expansion is intentionally disabled until endpoint/parser validation. No guessed endpoint enabled.
