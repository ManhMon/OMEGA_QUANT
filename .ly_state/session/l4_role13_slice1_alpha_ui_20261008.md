# L4 Implementation Report

- **Role**: 13 ui-ux-integrator - Claude Code L4 Implementation
- **Gate**: `GATE_L4_MODULAR_QUANT_SLICE1_ALPHA_UI_20261008`
- **Session**: `l4_role13_slice1_alpha_ui_20261008`
- **Date**: `2026-10-08`
- **Anti-Drip Mode**: `baseline`
- **Anti-Drip Contract**: `.ly_state/session/anti_drip_contract_l4_role13_slice1_alpha_ui_20261008.json`
- **Anti-Drip Contract SHA-256**: `63cb84a4c2666b7753c484aa4fda240eff326b35713b8ffd62e876b929c16e9b`

## Summary

Implemented alpha UI wiring through one validated advancedQuant boundary. Independent evaluation/decay cancellation; finite bounded metrics; legitimate zero/negative values preserved; explicit dependency errors; inclusive 15:30 ICT cutoff forwarding; caller-sample provenance separation; bounded single-attempt requests; fail-closed session-bound SSE handling. Implementation-only; no audit or gate approval.

Graph SHA-256 verified before use: `1b282c613f01440dde3f68c0f1b2aa5c8135258a1963d7ee16846e21383ef2a0`. HEAD matched `68a020cf8dfd27a30b79cfd3971046e0fbed08cd`. Contract SHA matched intact header; required findings empty. Baseline mode: no Root-Cause Architectural Sweep JSON. Contract, sidecar, prompt, audit reports and phase gates untouched.

Assumption: preserve existing design; backend remains market/calendar authority. Never advance cutoff to session close. Missing provenance never means verified data.

Advisor response returned launch-bound role 9/local-development gate rather than requested role 13/task gate. Excluded from task-bound evidence; no reliance for authorization or approval.

## Repo-Local Files Read

- .agents/agent/ui-ux-integrator.md
- .agents/skills/frontend-design/skill.md
- .agents/skills/mobile-design/skill.md
- .agents/skills/tailwind-patterns/skill.md
- .agents/skills/nextjs-react-expert/skill.md
- .agents/skills/web-design-guidelines/skill.md
- .agents/skills/clean-code/skill.md
- .agents/skills/testing-patterns/skill.md
- .agents/skills/app-builder/skill.md
- .agents/skills/seo-fundamentals/skill.md
- .agents/skills/webapp-testing/skill.md

Role frontmatter parsed: role_id 13, tier 2, implementation-only/test-required/no-self-approval; ten declared skills present. No external agent/skill source substituted. Native-mobile/scaffolding/SEO work not applicable. Bundled dataviz method loaded for existing metric/progress semantics; no chart redesign or categorical palette added.

## Changes Made

- `omega-ui/src/api/advancedQuant.ts`: typed aware timestamps and unverified caller provenance; validated request/response numeric, schema, resource boundaries; preserved actual zero; rejected malformed/non-finite/overflow values and nonpositive discovery inputs; checked PIT ordering and request cutoff binding; same-origin credential-free session-bound SSE URLs; ten-second timeout, zero retries for alpha requests.
- `omega-ui/src/hooks/useAlphaFactory.ts`: removed active legacy alpha API path; one cancellable arsenal/decay source; independent evaluation cancellation; clear obsolete results; backend-supported seeded decay ID; explicit errors, no fabricated counts/fitness; bounded history/events; strict terminal handling; stale-session isolation; unmount cleanup.
- `omega-ui/src/modules/alpha_factory/AlphaFactoryDiscoveryStation.tsx`: removed duplicate local requests/shared AbortController/RAF lifecycle; controlled universe; explicit errors/provenance; invalid metrics unavailable rather than synthetic zero; bounded form submission; keyboard signal selection, named controls, progress semantics; no forced positive IC prefix or fake 703 zero-count fallback.
- `tests/test_ui_alpha_factory.py`: runtime TypeScript/React adversarial checks inside existing Python suite; no new dependency. Numeric, PIT, transport, events, concurrent lifecycle and rendered component cases.
- This report plus scoped JUnit evidence in `.ly_state/session/`.

Read/write/list/delete/rollback symmetry: evaluate/start writes, arsenal/decay reads inspected. No UI filesystem persistence/delete or durable rollback operations exist; none invented.

### Scoped root-cause search accounting

Counts are matching lines in HEAD baseline. Changed matches: removed/replaced baseline matching lines; retained non-actionable matches justified below. Final matches include new guards/tests. Unresolved actionable scoped patterns: zero.

| Regex | Path | Baseline total | Changed | Non-actionable retained | Final | unresolved_matches |
|---|---|---:|---:|---:|---:|---:|
| `toFixed\|Math\.\|\\|\\|\|Number\(\|JSON\.parse\|apiClient\.\|advancedQuantApi\.\|AbortController\|requestAnimationFrame` | `omega-ui/src/modules/alpha_factory/AlphaFactoryDiscoveryStation.tsx` | 31 | 21 | 10 | 13 | 0 |
| `toFixed\|Math\.\|\\|\\|\|Number\(\|JSON\.parse\|apiClient\.\|advancedQuantApi\.\|AbortController\|requestAnimationFrame` | `omega-ui/src/hooks/useAlphaFactory.ts` | 20 | 20 | 0 | 19 | 0 |
| `toFixed\|Math\.\|\\|\\|\|Number\(\|JSON\.parse\|apiClient\.\|advancedQuantApi\.\|AbortController\|requestAnimationFrame` | `omega-ui/src/api/advancedQuant.ts` | 3 | 0 | 3 | 53 | 0 |
| `toFixed\|Math\.\|\\|\\|\|Number\(\|JSON\.parse\|apiClient\.\|advancedQuantApi\.\|AbortController\|requestAnimationFrame` | `tests/test_ui_alpha_factory.py` | 0 | 0 | 0 | 22 | 0 |
| `as_of\|pit_cutoff\|provenance\|15:30\|available_at\|is_synthetic\|pit_verified` | `omega-ui/src/modules/alpha_factory/AlphaFactoryDiscoveryStation.tsx` | 0 | 0 | 0 | 2 | 0 |
| `as_of\|pit_cutoff\|provenance\|15:30\|available_at\|is_synthetic\|pit_verified` | `omega-ui/src/hooks/useAlphaFactory.ts` | 0 | 0 | 0 | 1 | 0 |
| `as_of\|pit_cutoff\|provenance\|15:30\|available_at\|is_synthetic\|pit_verified` | `omega-ui/src/api/advancedQuant.ts` | 36 | 1 | 35 | 57 | 0 |
| `as_of\|pit_cutoff\|provenance\|15:30\|available_at\|is_synthetic\|pit_verified` | `tests/test_ui_alpha_factory.py` | 72 | 0 | 72 | 91 | 0 |
| `catch\|onError\|onerror\|onSuccess\|abort\|close\(\|retry\|history\|stream_url` | `omega-ui/src/modules/alpha_factory/AlphaFactoryDiscoveryStation.tsx` | 16 | 14 | 2 | 2 | 0 |
| `catch\|onError\|onerror\|onSuccess\|abort\|close\(\|retry\|history\|stream_url` | `omega-ui/src/hooks/useAlphaFactory.ts` | 22 | 19 | 3 | 29 | 0 |
| `catch\|onError\|onerror\|onSuccess\|abort\|close\(\|retry\|history\|stream_url` | `omega-ui/src/api/advancedQuant.ts` | 14 | 0 | 14 | 17 | 0 |
| `catch\|onError\|onerror\|onSuccess\|abort\|close\(\|retry\|history\|stream_url` | `tests/test_ui_alpha_factory.py` | 6 | 0 | 6 | 19 | 0 |

Paths correspond exactly to the four modified scope files listed above. Retained UI patterns: tab fallback, finite pagination, numeric input conversion guarded before submit, bounded typed discovery/history. Retained API patterns: unrelated resilient transport and shared quant interfaces, not alpha defects. Existing Python backend tests preserved. Final counts recorded after consolidated implementation, not a claim that every match required editing.

Call-site regex `useAlphaFactory|evaluateAlphaAst|getAlphaArsenalSignals|getAlphaDecayProfile|startAlphaDiscovery`, scan `omega-ui/src/**/*.{ts,tsx}`: 20 baseline matches; 8 changed scoped call sites; 12 non-actionable declarations/legacy exports/test mocks; unresolved_matches=0. Legacy client exports retained for compatibility; active hook/component use advancedQuant. Initial `type=tsx` search rejected by ripgrep; rerun without type filter succeeded; failed search provided no evidence.

## Verification

All commands repository-root, foreground, no orchestration polling. Safe pytest flags used. Terminal plugin disabled: successful commands emit no text; actual totals from XML.

1. `python -m pytest tests/test_ui_alpha_factory.py tests/test_ui_llm_config.py tests/test_ui_copilot_direct_llm.py -o addopts="" --capture=sys -p no:terminal --collect-only --junitxml=.ly_state/session/role13_alpha_related_collect.xml` — exit 0; no collection errors. Collect-only XML has zero executed tests by design. Every executed node below belongs to these collected files.
2. `python -m pytest tests/test_ui_alpha_factory.py -o addopts="" --capture=sys -p no:terminal -k alpha_ui_runtime --junitxml=.ly_state/session/role13_alpha_ui_focused.xml` — exit 0; 5 passed, zero failures/errors/skips.
3. `python -m pytest tests/test_ui_alpha_factory.py tests/test_ui_llm_config.py tests/test_ui_copilot_direct_llm.py -o addopts="" --capture=sys -p no:terminal --junitxml=.ly_state/session/role13_alpha_related.xml` — exit 0; 444 passed, zero failures/errors/skips; 34.613 seconds.
4. `node omega-ui/node_modules/vitest/vitest.mjs run --config omega-ui/vite.config.ts src/test/phase3_lifecycle.test.ts` — exit 0; `Test Files 1 passed (1)`, `Tests 17 passed (17)`.
5. `node omega-ui/node_modules/typescript/bin/tsc -p omega-ui/tsconfig.json --noEmit --noUnusedLocals false --noUnusedParameters false --pretty false` — exit 0; no output. Unrelated unused-symbol diagnostics disabled; not a full build pass.
6. `git diff --check -- omega-ui/src/api/advancedQuant.ts omega-ui/src/hooks/useAlphaFactory.ts omega-ui/src/modules/alpha_factory/AlphaFactoryDiscoveryStation.tsx tests/test_ui_alpha_factory.py` — exit 0; no output. Scoped files LF, CRLF count zero.

Initial failures corrected: duplicate QueryClient context in Node test loader (package-name resolution fixed); library timers retained after assertions (explicit process completion); missing numeric-control accessible names (implementation fixed). Final suites zero failures. Initial wrong tsconfig path returned TS5058; rerun used actual `omega-ui/tsconfig.json`.

Full build remains **NEEDS_FIX outside authorized scope**. `node omega-ui/node_modules/typescript/bin/tsc -b omega-ui --pretty false` returned exit 1:

```text
omega-ui/src/App.tsx(1,36): error TS6133: 'useState' is declared but its value is never read.
omega-ui/src/App.tsx(70,9): error TS6133: 'isStreamingConnected' is declared but its value is never read.
omega-ui/src/App.tsx(85,9): error TS6133: 'toggleLocale' is declared but its value is never read.
omega-ui/src/App.tsx(87,9): error TS6133: 'opsOpenerRef' is declared but its value is never read.
omega-ui/src/layout/TopNavBar.tsx(5,15): error TS6133: 'Settings' is declared but its value is never read.
```

Those files not modified. Real-browser screenshots, screen reader, live-provider checks not run; JSDOM interactions are not visual verification. Backend arsenal currently returns 424; UI reports dependency failure rather than inventing a historical arsenal.

### Standing regressions

All eight classes re-tested against production paths:

1. Literal/legacy IPv4: `tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns`, `::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins`, all collected variants passed.
2. IPv6 embedded IPv4: `tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns`, all variants passed.
3. Special-use: `tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges`, all variants passed.
4. Sparse merge: `tests/test_ui_llm_config.py::test_dim7_sparse_calendar_and_profile_isolation`, passed.
5. Snapshot restore: `tests/test_ui_alpha_factory.py::test_standing_llm_config_snapshot_restore`, passed.
6. Durable TLS SNI transport evidence: `tests/test_ui_copilot_direct_llm.py::test_safe_transport_uses_concrete_backend_and_preserves_host_header`, passed. Mocked transport verifies HTTP Host/TLS SNI preservation; not live TLS network testing.
7. Userinfo: `tests/test_ui_llm_config.py::test_config_rejects_userinfo_before_dns_without_secret_or_state_mutation`, all variants passed.
8. URL redaction: `tests/test_ui_llm_config.py::test_config_url_errors_redact_credentials_without_dns`, `::test_config_test_rejection_redaction_matrix`, `::test_free_text_url_redaction_helper_strips_credentials_only`, all variants passed.

### 24-dimension applicability

| # | Result / evidence |
|---|---|
| 1 | Strict malformed/null/empty/list/string/bool/non-finite/bounds runtime numeric/transport and backend sample checks passed. |
| 2 | Backend directory/read/schema faults passed; scoped LF checked. UI has no filesystem input. |
| 3 | Duplicate/partial payload checks passed; no UI checkpoint/shards. |
| 4 | Explicit 422/424/429/500 and invalid-result failures passed; no successful synthetic-zero metrics. |
| 5 | Independent cancellation/stale isolation passed; no UI durable replacement/rollback. |
| 6 | Inclusive UTC/ICT 15:30 cutoff, future availability, request binding, unverified caller samples passed. |
| 7 | Preclose/close backend tests passed. Calendar/holiday authority stays backend; no new UI calendar algorithm. |
| 8 | Zero/negative divisors, legitimate zero returns, NaN/Inf and >1e12 checks passed. |
| 9 | Concurrent evaluation/decay, superseded jobs, stale SSE, unmount cancellation passed. |
| 10 | VND_FULL 50000 sample unchanged; no scale conversion. |
| 11 | No new listing/universe selection decision; missing data never promoted to successful historical signals. Delisting implementation outside scope. |
| 12 | No shell built from caller input; IDs encoded, URLs constrained, request keys allowlisted. |
| 13 | Unknown request fields, malformed response counts/types and bounded arrays rejected. |
| 14 | Bounded 64 sample features, 10000 values/feature, ten previews, signals/profile/history; 65536-char SSE and twenty retained events. |
| 15 | Ten-second timeout abort and single-attempt 429/errors passed; no retry loop. |
| 16 | Generic UI errors, credential-free stream URLs and standing redaction suite passed. |
| 17 | N/A: no JEV routing implementation change. |
| 18 | N/A: no model catalog/selection implementation change. |
| 19 | Stream URL/session binding, wrong-session and stale replay checks passed; no gate approval. |
| 20 | Graph/contract SHA verified; provenance hash shape/temporal schema checked. No claim of verifying backend hash against unavailable dataset bytes. |
| 21 | N/A: no decision publisher/durable UI file operation. |
| 22 | N/A: no decision-lock implementation. |
| 23 | Alpha API has zero retries/fallback; timeout/429 checks passed. |
| 24 | No JEV prompt-routing change; no credentials in report; mismatched advisory binding excluded. |

### Exact executed pytest node IDs

Final JUnit XML supplies all exact executed IDs below. Each collected by command 1, executed by command 3. New adversarial checks: `tests/test_ui_alpha_factory.py::test_alpha_ui_runtime_boundaries[numeric]`, `[pit]`, `[transport]`, `[events]`, `[lifecycle]`.

```text
tests/test_ui_alpha_factory.py::test_dim1_evaluate_expression_valid
tests/test_ui_alpha_factory.py::test_dim1_evaluate_expression_empty_fail_closed
tests/test_ui_alpha_factory.py::test_dim2_evaluate_security_sandbox_rejection
tests/test_ui_alpha_factory.py::test_dim3_alpha_arsenal_signals_endpoint
tests/test_ui_alpha_factory.py::test_dim4_alpha_arsenal_filtering_and_search
tests/test_ui_alpha_factory.py::test_dim5_decay_profile_endpoint
tests/test_ui_alpha_factory.py::test_dim6_decay_profile_case_insensitivity
tests/test_ui_alpha_factory.py::test_seeded_decay_profile_calculated_without_dependency[ALPHA_0001_VNM]
tests/test_ui_alpha_factory.py::test_seeded_decay_profile_calculated_without_dependency[alpha_0001_vnm]
tests/test_ui_alpha_factory.py::test_seeded_decay_profile_calculated_without_dependency[ ALPHA_0001_VNM ]
tests/test_ui_alpha_factory.py::test_decay_profile_unknown_seed_variants_fail_closed[ALPHA_0001_VNM_EXTRA]
tests/test_ui_alpha_factory.py::test_decay_profile_unknown_seed_variants_fail_closed[ALPHA_0002_VNM]
tests/test_ui_alpha_factory.py::test_decay_profile_unknown_seed_variants_fail_closed[ALPHA_0001_FPT]
tests/test_ui_alpha_factory.py::test_decay_profile_unknown_seed_variants_fail_closed[NaN]
tests/test_ui_alpha_factory.py::test_decay_profile_unknown_seed_variants_fail_closed[Infinity]
tests/test_ui_alpha_factory.py::test_decay_profile_unknown_seed_variants_fail_closed[[]]
tests/test_ui_alpha_factory.py::test_decay_profile_unknown_seed_variants_fail_closed[xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx]
tests/test_ui_alpha_factory.py::test_decay_profile_empty_id_rejected
tests/test_ui_alpha_factory.py::test_seeded_decay_profile_response_isolation
tests/test_ui_alpha_factory.py::test_dim7_start_discovery_validation_bounds
tests/test_ui_alpha_factory.py::test_dim8_start_discovery_success
tests/test_ui_alpha_factory.py::test_dim9_sse_alpha_discovery_stream
tests/test_ui_alpha_factory.py::test_dim10_sse_unknown_session_graceful_connect
tests/test_ui_alpha_factory.py::test_dim11_ast_complex_formula_evaluation
tests/test_ui_alpha_factory.py::test_dim12_ast_syntax_error_handling
tests/test_ui_alpha_factory.py::test_dim13_arsenal_limit_bounds
tests/test_ui_alpha_factory.py::test_dim14_decay_profile_nonexistent_fallback
tests/test_ui_alpha_factory.py::test_dim15_ast_custom_sample_data_injection
tests/test_ui_alpha_factory.py::test_dim16_safe_eval_rejection_of_dunder_tokens
tests/test_ui_alpha_factory.py::test_pareto_frontier_empty_contract
tests/test_ui_alpha_factory.py::test_evaluation_missing_dependency[None-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_missing_dependency[None-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_missing_dependency[omitted-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_missing_dependency[omitted-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_dependency_faults[directory]
tests/test_ui_alpha_factory.py::test_evaluation_dependency_faults[read_error]
tests/test_ui_alpha_factory.py::test_evaluation_dependency_faults[empty]
tests/test_ui_alpha_factory.py::test_evaluation_dependency_faults[schema]
tests/test_ui_alpha_factory.py::test_evaluation_dependency_faults[nonfinite]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[zero-denominator-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[zero-denominator-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[zero-over-zero-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[zero-over-zero-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[zero-numerator-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[zero-numerator-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[negative-close-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[negative-close-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[return-overflow-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[return-overflow-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[return-out-of-bounds-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[return-out-of-bounds-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[close-out-of-bounds-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[close-out-of-bounds-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[volume-out-of-bounds-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[volume-out-of-bounds-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[nonfinite-close-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[nonfinite-close-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[nonfinite-volume-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_market_samples_fail_closed[nonfinite-volume-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_derived_returns_fail_closed[inf-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_derived_returns_fail_closed[inf-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_derived_returns_fail_closed[negative-inf-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_derived_returns_fail_closed[negative-inf-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_derived_returns_fail_closed[nan-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_derived_returns_fail_closed[nan-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_derived_returns_fail_closed[out-of-bounds-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_derived_returns_fail_closed[out-of-bounds-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_zero_market_returns_preserved[1.0-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_zero_market_returns_preserved[1.0-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_zero_market_returns_preserved[1000000000000.0-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_zero_market_returns_preserved[1000000000000.0-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_market_dependency_success
tests/test_ui_alpha_factory.py::test_evaluation_excludes_future_market_rows[timestamps0-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_excludes_future_market_rows[timestamps0-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_excludes_future_market_rows[timestamps1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_excludes_future_market_rows[timestamps1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_excludes_future_market_rows[timestamps2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_excludes_future_market_rows[timestamps2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_excludes_future_market_rows[timestamps3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_excludes_future_market_rows[timestamps3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_excludes_future_market_rows[timestamps4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_excludes_future_market_rows[timestamps4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:29:59.999999+07:00-False-2026-10-02-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:29:59.999999+07:00-False-2026-10-02-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:29:59.999999+07:00-False-market_date1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:29:59.999999+07:00-False-market_date1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:29:59.999999+07:00-False-market_date2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:29:59.999999+07:00-False-market_date2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:29:59.999999+07:00-False-market_date3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:29:59.999999+07:00-False-market_date3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:29:59.999999+07:00-False-market_date4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:29:59.999999+07:00-False-market_date4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:29:59.999999Z-False-2026-10-02-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:29:59.999999Z-False-2026-10-02-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:29:59.999999Z-False-market_date1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:29:59.999999Z-False-market_date1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:29:59.999999Z-False-market_date2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:29:59.999999Z-False-market_date2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:29:59.999999Z-False-market_date3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:29:59.999999Z-False-market_date3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:29:59.999999Z-False-market_date4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:29:59.999999Z-False-market_date4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00+07:00-True-2026-10-02-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00+07:00-True-2026-10-02-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00+07:00-True-market_date1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00+07:00-True-market_date1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00+07:00-True-market_date2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00+07:00-True-market_date2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00+07:00-True-market_date3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00+07:00-True-market_date3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00+07:00-True-market_date4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00+07:00-True-market_date4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:30:00Z-True-2026-10-02-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:30:00Z-True-2026-10-02-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:30:00Z-True-market_date1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:30:00Z-True-market_date1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:30:00Z-True-market_date2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:30:00Z-True-market_date2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:30:00Z-True-market_date3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:30:00Z-True-market_date3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:30:00Z-True-market_date4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T08:30:00Z-True-market_date4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00.000001+07:00-True-2026-10-02-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00.000001+07:00-True-2026-10-02-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00.000001+07:00-True-market_date1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00.000001+07:00-True-market_date1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00.000001+07:00-True-market_date2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00.000001+07:00-True-market_date2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00.000001+07:00-True-market_date3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00.000001+07:00-True-market_date3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00.000001+07:00-True-market_date4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[as_of-2026-10-02T15:30:00.000001+07:00-True-market_date4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:29:59.999999+07:00-False-2026-10-02-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:29:59.999999+07:00-False-2026-10-02-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:29:59.999999+07:00-False-market_date1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:29:59.999999+07:00-False-market_date1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:29:59.999999+07:00-False-market_date2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:29:59.999999+07:00-False-market_date2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:29:59.999999+07:00-False-market_date3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:29:59.999999+07:00-False-market_date3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:29:59.999999+07:00-False-market_date4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:29:59.999999+07:00-False-market_date4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:29:59.999999Z-False-2026-10-02-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:29:59.999999Z-False-2026-10-02-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:29:59.999999Z-False-market_date1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:29:59.999999Z-False-market_date1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:29:59.999999Z-False-market_date2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:29:59.999999Z-False-market_date2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:29:59.999999Z-False-market_date3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:29:59.999999Z-False-market_date3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:29:59.999999Z-False-market_date4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:29:59.999999Z-False-market_date4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00+07:00-True-2026-10-02-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00+07:00-True-2026-10-02-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00+07:00-True-market_date1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00+07:00-True-market_date1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00+07:00-True-market_date2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00+07:00-True-market_date2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00+07:00-True-market_date3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00+07:00-True-market_date3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00+07:00-True-market_date4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00+07:00-True-market_date4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:30:00Z-True-2026-10-02-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:30:00Z-True-2026-10-02-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:30:00Z-True-market_date1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:30:00Z-True-market_date1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:30:00Z-True-market_date2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:30:00Z-True-market_date2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:30:00Z-True-market_date3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:30:00Z-True-market_date3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:30:00Z-True-market_date4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T08:30:00Z-True-market_date4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00.000001+07:00-True-2026-10-02-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00.000001+07:00-True-2026-10-02-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00.000001+07:00-True-market_date1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00.000001+07:00-True-market_date1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00.000001+07:00-True-market_date2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00.000001+07:00-True-market_date2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00.000001+07:00-True-market_date3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00.000001+07:00-True-market_date3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00.000001+07:00-True-market_date4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_daily_close_availability[pit_cutoff-2026-10-02T15:30:00.000001+07:00-True-market_date4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_preclose_empty_history_fail_closed[evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_preclose_empty_history_fail_closed[ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_unusable_market_dates_fail_closed[2099-01-01-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_unusable_market_dates_fail_closed[2099-01-01-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_unusable_market_dates_fail_closed[None-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_unusable_market_dates_fail_closed[None-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_unusable_market_dates_fail_closed[not-a-date-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_unusable_market_dates_fail_closed[not-a-date-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_unusable_market_dates_fail_closed[123456789-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_unusable_market_dates_fail_closed[123456789-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_provenance_hash_binds_cutoff_and_eligible_inputs
tests/test_ui_alpha_factory.py::test_evaluation_aware_date_boundary_and_provenance[close]
tests/test_ui_alpha_factory.py::test_evaluation_aware_date_boundary_and_provenance[unknown_feature]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_cutoff_rejected_before_io[timestamps0-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_cutoff_rejected_before_io[timestamps0-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_cutoff_rejected_before_io[timestamps1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_cutoff_rejected_before_io[timestamps1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_cutoff_rejected_before_io[timestamps2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_cutoff_rejected_before_io[timestamps2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_cutoff_rejected_before_io[timestamps3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_cutoff_rejected_before_io[timestamps3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_cutoff_rejected_before_io[timestamps4-evaluate-expression]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_cutoff_rejected_before_io[timestamps4-ast/evaluate]
tests/test_ui_alpha_factory.py::test_hybrid_alt_data_contract_faults[None]
tests/test_ui_alpha_factory.py::test_hybrid_alt_data_contract_faults[alt_0]
tests/test_ui_alpha_factory.py::test_hybrid_alt_data_contract_faults[interbank_on_spread]
tests/test_ui_alpha_factory.py::test_hybrid_alt_data_contract_faults[term_structure_slope]
tests/test_ui_alpha_factory.py::test_hybrid_alt_data_contract_faults[interbank_vol_5d]
tests/test_ui_alpha_factory.py::test_hybrid_alt_data_contract_faults[macro_monetary_regime]
tests/test_ui_alpha_factory.py::test_standing_llm_config_snapshot_restore
tests/test_ui_alpha_factory.py::test_explicit_sample_bypasses_dependency[evaluate-expression]
tests/test_ui_alpha_factory.py::test_explicit_sample_bypasses_dependency[ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close-timestamps0-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close-timestamps0-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close-timestamps1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close-timestamps1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close-timestamps2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close-timestamps2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close-timestamps3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close-timestamps3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[unknown_feature-timestamps0-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[unknown_feature-timestamps0-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[unknown_feature-timestamps1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[unknown_feature-timestamps1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[unknown_feature-timestamps2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[unknown_feature-timestamps2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[unknown_feature-timestamps3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[unknown_feature-timestamps3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close / 0-timestamps0-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close / 0-timestamps0-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close / 0-timestamps1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close / 0-timestamps1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close / 0-timestamps2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close / 0-timestamps2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close / 0-timestamps3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[close / 0-timestamps3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[__import__('os')-timestamps0-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[__import__('os')-timestamps0-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[__import__('os')-timestamps1-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[__import__('os')-timestamps1-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[__import__('os')-timestamps2-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[__import__('os')-timestamps2-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[__import__('os')-timestamps3-evaluate-expression]
tests/test_ui_alpha_factory.py::test_caller_sample_historical_cutoff_never_claims_market_pit[__import__('os')-timestamps3-ast/evaluate]
tests/test_ui_alpha_factory.py::test_caller_sample_provenance_rejects_verified_claims[override0]
tests/test_ui_alpha_factory.py::test_caller_sample_provenance_rejects_verified_claims[override1]
tests/test_ui_alpha_factory.py::test_caller_sample_provenance_rejects_verified_claims[override2]
tests/test_ui_alpha_factory.py::test_caller_sample_provenance_rejects_verified_claims[override3]
tests/test_ui_alpha_factory.py::test_caller_sample_provenance_rejects_verified_claims[override4]
tests/test_ui_alpha_factory.py::test_caller_sample_provenance_rejects_verified_claims[override5]
tests/test_ui_alpha_factory.py::test_caller_sample_provenance_rejects_verified_claims[override6]
tests/test_ui_alpha_factory.py::test_invalid_explicit_samples_do_not_fallback[sample_data0]
tests/test_ui_alpha_factory.py::test_invalid_explicit_samples_do_not_fallback[sample_data1]
tests/test_ui_alpha_factory.py::test_invalid_explicit_samples_do_not_fallback[sample_data2]
tests/test_ui_alpha_factory.py::test_invalid_explicit_samples_do_not_fallback[sample_data3]
tests/test_ui_alpha_factory.py::test_invalid_explicit_samples_do_not_fallback[sample_data4]
tests/test_ui_alpha_factory.py::test_invalid_explicit_samples_do_not_fallback[sample_data5]
tests/test_ui_alpha_factory.py::test_invalid_explicit_samples_do_not_fallback[sample_data6]
tests/test_ui_alpha_factory.py::test_invalid_explicit_samples_do_not_fallback[sample_data7]
tests/test_ui_alpha_factory.py::test_invalid_explicit_samples_do_not_fallback[sample_data8]
tests/test_ui_alpha_factory.py::test_invalid_explicit_samples_do_not_fallback[sample_data9]
tests/test_ui_alpha_factory.py::test_nonfinite_explicit_samples_rejected[NaN]
tests/test_ui_alpha_factory.py::test_nonfinite_explicit_samples_rejected[Infinity]
tests/test_ui_alpha_factory.py::test_nonfinite_explicit_samples_rejected[-Infinity]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_result_not_dependency_failure[1e309]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_result_not_dependency_failure[close / 0]
tests/test_ui_alpha_factory.py::test_evaluation_invalid_result_not_dependency_failure[unknown_feature]
tests/test_ui_alpha_factory.py::test_pareto_point_strict_contract[ic_mean-nan]
tests/test_ui_alpha_factory.py::test_pareto_point_strict_contract[ir_annualized-inf]
tests/test_ui_alpha_factory.py::test_pareto_point_strict_contract[ic_mean-1.1]
tests/test_ui_alpha_factory.py::test_pareto_point_strict_contract[turnover_pct--1.0]
tests/test_ui_alpha_factory.py::test_pareto_point_strict_contract[turnover_pct-101.0]
tests/test_ui_alpha_factory.py::test_pareto_point_strict_contract[complexity_score-0]
tests/test_ui_alpha_factory.py::test_pareto_point_strict_contract[complexity_score-True]
tests/test_ui_alpha_factory.py::test_pareto_point_strict_contract[alpha_id-]
tests/test_ui_alpha_factory.py::test_pareto_point_strict_contract[ir_annualized-1.5]
tests/test_ui_alpha_factory.py::test_pareto_point_strict_contract[unexpected-1]
tests/test_ui_alpha_factory.py::test_alpha_ui_runtime_boundaries[numeric]
tests/test_ui_alpha_factory.py::test_alpha_ui_runtime_boundaries[pit]
tests/test_ui_alpha_factory.py::test_alpha_ui_runtime_boundaries[transport]
tests/test_ui_alpha_factory.py::test_alpha_ui_runtime_boundaries[events]
tests/test_ui_alpha_factory.py::test_alpha_ui_runtime_boundaries[lifecycle]
tests/test_ui_llm_config.py::test_dim1_strict_types_and_schema_validation
tests/test_ui_llm_config.py::test_dim2_file_io_and_endpoint_routing
tests/test_ui_llm_config.py::test_dim3_transactional_durability_and_secret_retention
tests/test_ui_llm_config.py::test_dim4_memory_bounds_and_sanitized_payload
tests/test_ui_llm_config.py::test_dim5_concurrency_and_probe_connectivity
tests/test_ui_llm_config.py::test_dim6_pit_temporal_clock_iso_formatting
tests/test_ui_llm_config.py::test_dim7_sparse_calendar_and_profile_isolation
tests/test_ui_llm_config.py::test_dim8_mathematical_extremes_and_temperature_bounds
tests/test_ui_llm_config.py::test_dim9_financial_and_engine_specialization
tests/test_ui_llm_config.py::test_dim10_case_insensitive_and_provider_canonicalization
tests/test_ui_llm_config.py::test_dim11_fail_closed_and_invalid_profile_key
tests/test_ui_llm_config.py::test_dim12_full_suite_regression_closure
tests/test_ui_llm_config.py::test_dim13_metric_and_artifact_consistency
tests/test_ui_llm_config.py::test_dim14_exception_chaining_and_missing_key_probe
tests/test_ui_llm_config.py::test_dim15_opt_in_safety_defaults
tests/test_ui_llm_config.py::test_dim16_security_and_secret_leakage_prevention
tests/test_ui_llm_config.py::test_config_rejects_userinfo_before_dns_without_secret_or_state_mutation[https://username-only-secret@proxy.example.com/v1-username-only-secret]
tests/test_ui_llm_config.py::test_config_rejects_userinfo_before_dns_without_secret_or_state_mutation[https://user-secret:password-secret@proxy.example.com/v1-password-secret]
tests/test_ui_llm_config.py::test_config_rejects_userinfo_before_dns_without_secret_or_state_mutation[https://%75serinfo%2Dsecret@proxy.example.com/v1-%75serinfo%2Dsecret]
tests/test_ui_llm_config.py::test_config_rejects_userinfo_before_dns_without_secret_or_state_mutation[https://@proxy.example.com/v1-@proxy.example.com]
tests/test_ui_llm_config.py::test_config_rejects_userinfo_before_dns_without_secret_or_state_mutation[https://:blank-username-password-secret@proxy.example.com/v1-blank-username-password-secret]
tests/test_ui_llm_config.py::test_config_rejects_userinfo_before_dns_without_secret_or_state_mutation[https://blank-password-secret:@proxy.example.com/v1-blank-password-secret]
tests/test_ui_llm_config.py::test_config_url_errors_redact_credentials_without_dns[/api/v1/copilot/config-payload0]
tests/test_ui_llm_config.py::test_config_url_errors_redact_credentials_without_dns[/api/v1/copilot/config/test-payload1]
tests/test_ui_llm_config.py::test_config_allows_public_custom_hostname_when_opted_in
tests/test_ui_llm_config.py::test_config_test_rejection_redaction_matrix[https://username-only-secret@proxy.example.com/v1-secrets0]
tests/test_ui_llm_config.py::test_config_test_rejection_redaction_matrix[https://userinfo-secret:password-secret@proxy.example.com/v1-secrets1]
tests/test_ui_llm_config.py::test_config_test_rejection_redaction_matrix[https://%75ser%2Dsecret:%70assword%2Dsecret@proxy.example.com/v1-secrets2]
tests/test_ui_llm_config.py::test_config_test_rejection_redaction_matrix[https://:empty-username-password-secret@proxy.example.com/v1-secrets3]
tests/test_ui_llm_config.py::test_config_test_rejection_redaction_matrix[https://empty-password-username-secret:@proxy.example.com/v1-secrets4]
tests/test_ui_llm_config.py::test_free_text_url_redaction_helper_strips_credentials_only
tests/test_ui_copilot_direct_llm.py::test_jev_cache_rejects_future_decision[09:00-08:00-11:00-10:00-09:00]
tests/test_ui_copilot_direct_llm.py::test_jev_cache_rejects_future_decision[09:00-08:00-09:30-10:00-09:00]
tests/test_ui_copilot_direct_llm.py::test_jev_cache_rejects_future_decision[09:00-08:00-08:30-10:00-08:00]
tests/test_ui_copilot_direct_llm.py::test_jev_system_two_changes_execution_prompt[yes]
tests/test_ui_copilot_direct_llm.py::test_jev_system_two_changes_execution_prompt[no]
tests/test_ui_copilot_direct_llm.py::test_jev_safe_tool_and_classifier_failure_provenance
tests/test_ui_copilot_direct_llm.py::test_tool_exception_does_not_disclose_secrets[hello_dispatch]
tests/test_ui_copilot_direct_llm.py::test_tool_exception_does_not_disclose_secrets[trigger_backtest_dispatch]
tests/test_ui_copilot_direct_llm.py::test_dim1_strict_types_and_schema_validation
tests/test_ui_copilot_direct_llm.py::test_dim2_file_io_path_aliasing_and_auto_init_env_config
tests/test_ui_copilot_direct_llm.py::test_dim3_fsync_durability_and_async_llm_structured_json
tests/test_ui_copilot_direct_llm.py::test_dim4_memory_bounds_and_raw_markdown_verbatim_preservation
tests/test_ui_copilot_direct_llm.py::test_dim5_concurrency_and_local_ollama_provider_without_key
tests/test_ui_copilot_direct_llm.py::test_dim6_point_in_time_and_temporal_iso_timestamp
tests/test_ui_copilot_direct_llm.py::test_dim7_sparse_calendar_and_vietnam_ticker_natural_extraction
tests/test_ui_copilot_direct_llm.py::test_dim8_mathematical_extremes_and_temperature_bounds
tests/test_ui_copilot_direct_llm.py::test_dim9_financial_reasoning_domain1_price_drivers
tests/test_ui_copilot_direct_llm.py::test_dim10_financial_reasoning_domain2_valuation_fundamentals
tests/test_ui_copilot_direct_llm.py::test_dim11_financial_reasoning_domain3_ast_alpha_signals
tests/test_ui_copilot_direct_llm.py::test_dim12_financial_reasoning_domain4_barra_risk_tca
tests/test_ui_copilot_direct_llm.py::test_dim13_financial_reasoning_domain5_portfolio_rebalancing
tests/test_ui_copilot_direct_llm.py::test_dim14_financial_reasoning_domain6_macro_sbv_regime
tests/test_ui_copilot_direct_llm.py::test_dim15_exception_chaining_and_network_fail_closed_graceful_fallback
tests/test_ui_copilot_direct_llm.py::test_dim16_security_and_zero_secret_leakage_in_config
tests/test_ui_copilot_direct_llm.py::test_dns_rebinding_is_pinned_at_models_endpoint
tests/test_ui_copilot_direct_llm.py::test_dns_rebinding_is_pinned_at_ask_endpoint
tests/test_ui_copilot_direct_llm.py::test_localhost_rebinding_is_blocked_at_models_endpoint
tests/test_ui_copilot_direct_llm.py::test_localhost_rebinding_is_blocked_at_ask_endpoint
tests/test_ui_copilot_direct_llm.py::test_safe_transport_uses_concrete_backend_and_preserves_host_header
tests/test_ui_copilot_direct_llm.py::test_localhost_must_resolve_to_loopback
tests/test_ui_copilot_direct_llm.py::test_allowlisted_provider_rejects_mixed_private_public_dns_with_local_mode[answers0]
tests/test_ui_copilot_direct_llm.py::test_allowlisted_provider_rejects_mixed_private_public_dns_with_local_mode[answers1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_cgnat_dns
tests/test_ui_copilot_direct_llm.py::test_custom_proxy_rejects_public_ip_literals_and_accepts_public_hostname
tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns[010.010.010.010]
tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns[0x08080808]
tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns[134744072]
tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns[3758096385]
tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns[127.1]
tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns[0x7f.1]
tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns[127.0.0.1.]
tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns[0177.0.0.1.]
tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns[0x7f000001.]
tests/test_ui_copilot_direct_llm.py::test_legacy_numeric_ipv4_hostnames_are_rejected_before_dns[2130706433.]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[http://127.0.0.1:11434/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://127.0.0.1/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://10.0.0.1/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://172.16.0.1/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://192.168.1.1/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://100.64.0.1/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://169.254.169.254/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://192.0.2.1/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://198.51.100.1/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://203.0.113.1/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://224.0.0.1/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://0.0.0.0/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[http://[::1]:11434/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://[fc00::1]/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://[fe80::1]/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://[2001:db8::1]/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://[ff02::1]/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://[::]/v1]
tests/test_ui_copilot_direct_llm.py::test_all_ip_literal_base_urls_are_rejected_regardless_of_opt_ins[https://[2001:4860:4860::8888]/v1]
tests/test_ui_copilot_direct_llm.py::test_localhost_rejects_unsafe_dns_answers[169.254.169.254]
tests/test_ui_copilot_direct_llm.py::test_localhost_rejects_unsafe_dns_answers[192.0.2.1]
tests/test_ui_copilot_direct_llm.py::test_localhost_rejects_unsafe_dns_answers[100.64.0.1]
tests/test_ui_copilot_direct_llm.py::test_localhost_rejects_unsafe_dns_answers[192.168.1.50]
tests/test_ui_copilot_direct_llm.py::test_localhost_rejects_unsafe_dns_answers[fe80::1]
tests/test_ui_copilot_direct_llm.py::test_localhost_rejects_unsafe_dns_answers[2001:db8::1]
tests/test_ui_copilot_direct_llm.py::test_localhost_rejects_unsafe_dns_answers[ff02::1]
tests/test_ui_copilot_direct_llm.py::test_localhost_rejects_unsafe_dns_answers[::]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[api.openai.com-environment0-224.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[api.openai.com-environment0-ff02::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[api.openai.com-environment0-fec0::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[api.openai.com-environment0-64:ff9b::7f00:1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[api.openai.com-environment0-64:ff9b::a00:1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[api.openai.com-environment0-::127.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[api.openai.com-environment0-::ffff:127.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[api.openai.com-environment0-::ffff:0:7f00:1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[api.openai.com-environment0-2002:7f00:1::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[proxy.example.com-environment1-224.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[proxy.example.com-environment1-ff02::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[proxy.example.com-environment1-fec0::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[proxy.example.com-environment1-64:ff9b::7f00:1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[proxy.example.com-environment1-64:ff9b::a00:1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[proxy.example.com-environment1-::127.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[proxy.example.com-environment1-::ffff:127.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[proxy.example.com-environment1-::ffff:0:7f00:1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_unsafe_global_looking_dns[proxy.example.com-environment1-2002:7f00:1::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[api.openai.com-environment0-0.1.2.3]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[api.openai.com-environment0-192.0.0.9]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[api.openai.com-environment0-192.88.99.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[api.openai.com-environment0-198.18.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[api.openai.com-environment0-240.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[api.openai.com-environment0-100::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[api.openai.com-environment0-2001:db8::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[api.openai.com-environment0-3ffe::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[api.openai.com-environment0-fc00::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[proxy.example.com-environment1-0.1.2.3]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[proxy.example.com-environment1-192.0.0.9]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[proxy.example.com-environment1-192.88.99.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[proxy.example.com-environment1-198.18.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[proxy.example.com-environment1-240.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[proxy.example.com-environment1-100::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[proxy.example.com-environment1-2001:db8::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[proxy.example.com-environment1-3ffe::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_dns_ranges[proxy.example.com-environment1-fc00::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-192.31.196.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-192.52.193.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-192.175.48.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-2620:4f:8000::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-::ffff:127.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-::ffff:10.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-::ffff:192.168.1.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-::ffff:172.16.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-::ffff:169.254.169.254]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-2606:4700:4700::5efe:a00:1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[api.openai.com-environment0-2001:4860:4860::ffff:7f00:1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-192.31.196.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-192.52.193.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-192.175.48.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-2620:4f:8000::1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-::ffff:127.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-::ffff:10.0.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-::ffff:192.168.1.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-::ffff:172.16.0.1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-::ffff:169.254.169.254]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-2606:4700:4700::5efe:a00:1]
tests/test_ui_copilot_direct_llm.py::test_provider_and_custom_proxy_reject_special_use_and_embedded_ipv4_dns[proxy.example.com-environment1-2001:4860:4860::ffff:7f00:1]
```

## Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit`: not read; non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: not read; non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: not read; non-authoritative scan evidence only; no reliance.
- `.codex\memories`: not read; non-authoritative scan evidence only; no reliance.
