# Code Review Audit Report
**Role**: Code Reviewer (Role 21, Codex L3)
**Date**: 2026-06-12T19:53:53+07:00
**Gate**: VNSTOCK_LATEST_STANDARDIZATION_20260612
**Submission**: l2_role15_vnstock_latest_standardization_20260612
**Tier 2 Engineer**: data-engineer (Role 15)

## CODEX AUDIT VERDICT

**Status:** [NEEDS_FIX]

## Boundary Evidence

- Writer != auditor: PASS (L2 role_id=15, L3 role_id=21).
- L2 role spec: PASS (`data-engineer`, tier=2, platform=OpenCode).
- L3 role spec: PASS (`code-reviewer`, tier=3, platform=Codex, sod_boundary present).
- L3 write boundary: PASS. This audit wrote only this report and the target `VNSTOCK_LATEST_STANDARDIZATION_20260612` gate entry.
- Antigravity scratch paths: PASS for scoped L2 evidence and active code search; only generic in-repo uses of the word `scratch` found.

## Verification Run

- `python -m pip show vnstock`: PASS, installed version is `4.0.4`.
- `python -c ... importlib.metadata`: PASS, `vnstock=4.0.4`; `vnstock3` and `vnstock_data` not installed.
- `rg` import scan for `vnstock3` / `vnstock_data` in `src scripts`: PASS, no active import statements found.
- `python -m compileall -q` on scoped Python files: PASS.
- `python -m pytest -q tests/test_benchmark_provider.py tests/data_test_vnd_full_exchange_fix.py tests/test_data_loader_corporate_action_pit.py`: PASS, 74 passed.
- `python -m pytest -q tests/execution_test_order_router.py`: PASS, 44 passed.
- `python -m pytest -q tests/data_test_deployment_flow.py`: BLOCKED/FAIL in this sandbox: 13 failures creating temp `.models` under `C:\Users\GHC\AppData\Local\Temp`; rerun with `TEMP/TMP/TMPDIR=C:\tmp` and `--basetemp=C:\tmp\pytest-omega-vnstock` still used AppData temp.

## Findings

1. **HIGH - Canonical parquet is modified despite L2 evidence claiming it was not.**
   - Location: `data/market_2015_now.parquet`
   - Evidence: `git status --short -- data/market_2015_now.parquet` reports modified; `git diff --stat` shows binary size changed from `35513722` to `20804033` bytes.
   - Impact: This violates the explicit audit check `canonical parquet not modified` and contradicts `.ly_state/session/vnstock_latest_smoke_20260612.json` (`canonical_data_modified=false`). L2 must either restore this canonical artifact or provide file-backed proof it is unrelated/pre-existing and outside the gate.

2. **HIGH - Scoped adapter surface still leaks a hardcoded vnstock API key.**
   - Location: `src/omega/data/vnstock_adapter.py:66`; related existing occurrence `src/omega/quant/data/vnstock.py:64-78`.
   - Evidence: `self.api_key = os.getenv("VNSTOCK_API_KEY", "vnstock_e05b9f4c0d4eacd20b900cf99688d3c1")`.
   - Impact: The gate explicitly asks to verify the adapter does not leak secrets. Even if pre-existing, this file is in scope and was edited; L2 report says env-var handling was preserved, but the scoped code contains a literal credential-like key and exports it into `os.environ`.

3. **MEDIUM - New unified adapter does not preserve VND_FULL guard for intraday price data.**
   - Location: `src/omega/data/vnstock_client.py:193-206`.
   - Evidence: `fetch_intraday()` returns `df if df is not None else pd.DataFrame()` with no `ensure_vnd_scale()` call or price-column normalization, while the L2 report claims `fetch_intraday()` has a VND_FULL guard and that all price-returning methods are guarded.
   - Impact: Intraday consumers can receive raw vnstock units while daily history and market OHLCV are normalized, creating mixed price scales.

4. **MEDIUM - L2 verification evidence overstates deployment/execution test pass count.**
   - Location: `.ly_state/session/vnstock_latest_smoke_20260612.json`, `.ly_state/session/l2_role15_vnstock_latest_standardization_20260612.md`.
   - Evidence: L2 records `57 passed`; L3 rerun produced 13 deployment-flow failures plus 44 execution tests passing. Failures appear sandbox/temp-path related, but the current audit cannot reproduce the claimed 57/57 result.
   - Impact: Gate evidence is not reproducible as written. L2 should rerun with file-backed logs from the repo environment or mark the temp-path limitation clearly.

## Checks Summary

- vnstock 4.0.2 -> 4.0.4: PASS.
- No `vnstock3` / `vnstock_data` imports in active `src/scripts`: PASS.
- VCI + KBS listing fallback: PASS in `vnstock_client.py`, `vnstock_adapter.py`, and `omega.quant.data.vnstock.py`.
- VND_FULL guard: PARTIAL; daily/market paths guarded, intraday path unguarded.
- PIT/no look-ahead: PASS for reviewed changes; no new time-travel feature engineering or target leakage found.
- Secrets: FAIL due hardcoded vnstock key in scoped adapter surface.
- Canonical parquet untouched: FAIL.

## Required Fix Scope

1. Restore or explicitly remove the `data/market_2015_now.parquet` modification from this gate; update smoke evidence to match real git state.
2. Remove hardcoded vnstock API key fallbacks from scoped vnstock adapters; require env var, documented dummy test value, or non-secret provider default that is not credential-shaped.
3. Apply VND_FULL normalization to `VnstockClient.fetch_intraday()` for its price columns, with a focused test or smoke evidence.
4. Refresh L2 report/smoke JSON with reproducible test commands and outputs.

## Final Verdict

[NEEDS_FIX]

**Signature:** Codex L3 Auditor, Role 21 code-reviewer
