# Code Review Audit Report

**Role**: 21 code-reviewer - Codex L3 Independent Review  
**Date**: 2026-06-12  
**Gate**: LLM_PROVIDER_SAFE_INTERFACE_20260612  
**L2 Session**: l2_role9_llm_provider_safe_interface_20260612  
**L2 Role**: 9 backend-engineer  
**Verdict**: [NEEDS_FIX]

## Scope

- src/omega/quant/evolution/llm_symbolic_synthesizer.py
- src/omega/quant/evolution/unified_feature_adapter.py
- scripts/backtest_v2_cpcv.py
- tests/quant_test_infinite_evolution.py
- .ly_state/session/l2_role9_llm_provider_safe_interface_20260612.md
- .ly_state/session/phase_gates.json

## SOD Evidence

- L2 role spec verified: role_id=9, tier=2, platform=OpenCode, name=backend-engineer.
- L3 role spec verified: role_id=21, tier=3, platform=Codex, name=code-reviewer, sod_boundary defined.
- Writer != auditor verified: 9 != 21.
- L3 write boundary observed: no production source edits made by Codex L3.

## Findings

1. **P0 - Formula safety parser accepts trailing and infix-like payloads**  
   Location: src/omega/quant/evolution/llm_symbolic_synthesizer.py:242-279, 285-351.  
   `FormulaSafetyParser.validate_formula()` calls `_validate_tree(tokens, 0, 0)` but `_validate_tree()` does not return the consumed token index, so validation never checks that the whole token stream was consumed. Evidence probe returned valid for unsafe inputs:

   ```text
   ts_mean(close, 20) trailing => (True, '')
   ts_mean(close, 20) + volume => (True, '')
   ts_mean(close, 20); unknown_secret => (True, '')
   add(close, volume) garbage => (True, '')
   ```

   This violates check E: strict formula safety parser must reject infix, unknown/trailing tokens. It also weakens cache safety because `validate_batch()` returns the original formula string after partial validation.

2. **P1 - Required scoped pytest did not pass in L3 run**  
   Command: `pytest tests/quant_test_infinite_evolution.py -q`.  
   Result: `18 passed, 2 failed`. Failures:
   - `test_formula_cache_deterministic`: cache write failed with permission denied, then cache read returned `None`.
   - `test_secrets_not_in_cache`: expected one cache file, found zero after cache write failure.

   A second run using repo-local temp plus `pytest.main(... -s -p no:cacheprovider)` still failed the same two tests with `PermissionError` under `.ly_state/session/llm_cache/tmp*`. Because check I requires 20 pass, approval is blocked in this L3 environment.

## Checks

- A writer != auditor: PASS (`9 != 21`).
- B default mock/offline and openai-compatible opt-in: PASS by inspection; default provider resolves to mock, CLI default is mock.
- C API key env-only, never logged/cached/stored: PASS by inspection for `LLMSymbolicSynthesizer`; direct `api_key` arg is ignored with warning.
- D deterministic cache under `.ly_state/session/llm_cache`: BLOCKED by pytest/cache write failures in L3 environment.
- E strict formula safety parser: FAIL; trailing/infix-like token acceptance proven above.
- F tests do not make network calls: PASS by inspection; tests use mock/default fallback, no requests/urllib/socket calls found.
- G grouped per-ticker execution mandatory for generated formulas: PASS by inspection in `execute_node_grouped()` and backtest path.
- H py_compile scoped files: PASS (`python -B -m py_compile ...` exited 0).
- I pytest expected 20 pass: FAIL (`18 passed, 2 failed`).
- J pre-update SOD enforcer: PASS; blocked only `LLM_PROVIDER_SAFE_INTERFACE_20260612: PENDING_L3_AUDIT`.
- K gate update: NOT PERFORMED because verdict is [NEEDS_FIX].
- L post-update SOD enforcer: NOT RUN because gate was not approved/updated.

## Required Fixes

1. Update `FormulaSafetyParser` so validation consumes and verifies the full token stream. Reject any trailing token, dropped punctuation, infix operator token, or unknown terminal/operator after a valid prefix expression.
2. Add explicit tests for trailing payloads, e.g. `ts_mean(close, 20) trailing`, `ts_mean(close, 20) + volume`, and `add(close, volume) garbage` must all reject.
3. Re-run scoped pytest and provide passing 20/20 evidence in a new L2 report. If sandbox temp permissions remain environment-specific, make the cache tests use a repo-owned writable temp/cache fixture that works under the managed L3 sandbox.

## Verdict

[NEEDS_FIX]
