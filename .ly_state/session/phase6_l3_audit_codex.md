# L3 Audit — Phase 6 GP+Test Infra (Codex)

**Date**: 2026-05-30 13:50 GMT+7 (audit retroactive on commit 38f1fef2)
**Auditor**: Role21-CodeReviewer (Codex CLI v0.134.0)
**Codex session**: `019e77a3-3414-7de0-a288-02357fe998ef`
**Rollout**: `~/.codex/sessions/2026/05/30/rollout-2026-05-30T13-47-*.jsonl`
**Wall time**: ~5 min, 12 file reads + 1 reproduction script + git inspection.
**Invocation**: SOUL.md Rule 9.1 (stdin pipe).
**SOD note**: Ly committed Phase 6 (commit 38f1fef2) before any L3 verdict. This audit is retroactive. Phase 6 fixes for the 2 P1 findings are applied in a follow-up commit; gate locks under [APPROVED] only AFTER P1 fixes verified green.

## Inputs reviewed
- `packages/quant/src/omega/quant/evolution/genetic_engine.py`
- `packages/quant/src/omega/quant/models/lstm_alpha.py`
- `packages/quant/tests/conftest.py`
- `scripts/backtest_evolution.py`
- `scripts/backtest_v2_cpcv.py`
- `scripts/full_project_audit.py` (impacted by portfolio rename)
- Reproduced broken import in sandboxed `python -c` to verify P1#2

## Verdict (initial)

**[NEEDS_FIX]** with 2 P1 + 3 P2.

## Findings

### P1 — Fixed in follow-up commit

1. **`scripts/backtest_evolution.py:313`**: comment claimed `random.seed`/`np.random.seed` set "at module load time before evolve()", but no seed call existed anywhere in the import chain. With `n_jobs=10` joblib parallel, GP runs were non-deterministic.
   **Fix applied**: added `import random; random.seed(42); np.random.seed(42)` at module top (after numpy import). Comment in `train_gp()` updated to reference the actual location.

2. **`scripts/full_project_audit.py:43`**: short-form `from omega.quant.portfolio import PortfolioOptimizer` previously resolved to the flat `src/omega/quant/portfolio.py`. After rename + empty `__init__.py`, this import raised `ImportError`, breaking the project audit script.
   **Fix applied**: populated `packages/quant/src/omega/quant/portfolio/__init__.py` to re-export `PortfolioOptimizer` from `portfolio_optimizer.py`. Verified by sandbox `python -c "from omega.quant.portfolio import PortfolioOptimizer"` -> OK. All other callers already use the fully-qualified path; they remain unbroken.

### P2 — Deferred (cosmetic / micro-optimization)

3. **`genetic_engine.py:529`** stale `_alpha_cache` invalidation: `if hasattr(self.hall_of_fame, '_alpha_cache')` is dead code (fresh list never has the attr). Minor: diversity penalty cache may persist across HoF rebuilds. Low impact (cache is keyed on `id(features)` which changes per fold).

4. **`genetic_engine.py:537`** `if candidate.fitness <= 0: continue` could be `break` (candidates sorted desc → all remainders also negative). Wasteful but correct.

5. **`genetic_engine.py:541`** HoF acceptance gate uses prior-generation diversity_penalty; combined with stale cache (#3) can under-fill HoF. Lower-priority research item.

### Confirmed correct (no fix)

- **Signed IC**: `genetic_engine.py:285` `self.ic_score = float(ic)`; no `abs(ic)` survives in fitness path. Final fitness `ic_score - complexity - diversity - tx_cost`.
- **HoF size cap** intact (`>= hall_of_fame_size: break`).
- **LSTM IC loss**: `LSTMAlphaConfig.loss="mse"` default preserved; `_ic_loss` mean-centered Pearson with `+1e-12` epsilon both inside `sqrt` and at outer divisor.
- **conftest.py prepend**: removes prior occurrence first, then `sys.path.insert(0, ...)`.
- **Portfolio rename**: `git show --stat` confirms `quant/{portfolio.py => _portfolio_legacy.py}`; canonical callers (`pipeline.py`, `live_test_e2e_mock_smoke.py`, `test_pipeline.py`, `test_portfolio_optimizer.py`) use fully-qualified path.
- **PIT/SOD**: no PIT regressions in any of the 5 changes.

## Disposition after P1 fixes applied

- **Gate APPROVED** for Phase 6 once both P1 items fixed (commit follow-up after this report).
- **560/560 tests PASS** verified after P1 fixes.
- **P2 #3-5** logged for future GP-architecture research session (not blocking; GP is not on production path).

## Evidence chain

- `.ly_state/session/phase6_codex_audit_v2.stdout` — codex agent_message extracted from rollout
- `~/.codex/sessions/2026/05/30/rollout-2026-05-30T13-47-*.jsonl` — full session log
- `pytest packages/quant/tests -q` -> 560 passed (run after P1 fixes)
