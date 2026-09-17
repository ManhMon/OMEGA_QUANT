# L2 Reconciliation Evidence — SHARPE_TCOST_PHASE2_HYSTERESIS_FIX

- Session: `l2_role14_b1_hysteresis_reconcile_20260728`
- Role: `14 data-scientist` (OpenCode L2)
- Gate: `SHARPE_TCOST_PHASE2_HYSTERESIS_FIX`
- Purpose: fresh deterministic reconciliation evidence only; no implementation or approval.
- Scope: historical hysteresis fix in `scripts/backtest_hybrid_regime.py`, direct regression coverage in `tests/phase35/test_hybrid_regime_backtest_perf.py`, existing gate/audit artifacts.

## Repo-Local Source Contract

- `REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`
- `REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`
- Role file read: `.agents/agent/data-scientist.md`
- Skill files read:
  - `.agents/skills/python-patterns/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
  - `.agents/skills/performance-profiling/SKILL.md`
  - `.agents/skills/quant-research/SKILL.md`
  - `.agents/skills/vietnam-market-data/SKILL.md`
  - `.agents/skills/backtesting-pit-safety/SKILL.md`
  - `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative; not used.
- `.openclaw\skills`: non-authoritative; not used.
- `C:\Users\GHC\.agents`: non-authoritative; not used.
- `.codex\memories`: non-authoritative; not used.
- Result: no forbidden path used as an authoritative role or skill source; all reads used repo-local paths under `REPO_ROOT`.

## Historical Evidence

- Historical L2 report: `.ly_state/session/l2_role14_sharpe_tcost_phase2_hysteresis_fix_20260629.md`
- Historical L3 audit: `.ly_state/session/audit_reports/role21_sharpe_tcost_phase2_hysteresis_fix_20260629.md`
- Historical L2/L3 identities: role 14 `data-scientist` / role 21 `code-reviewer`; writer != auditor.
- Historical verdict: `[APPROVED]`.
- Current phase-gate entry remains unchanged: `.ly_state/session/phase_gates.json:1180-1203`; prior verdict `[APPROVED]`.
- Historical source/test commit context: `580add49` (`l2-scope-proof-preexisting`); current `HEAD=f1981af123db5b8d828696b5e7a14e3fe1117bce1`.
- Current file hashes:
  - `scripts/backtest_hybrid_regime.py`: `13c82916f5a1933d029f39a5ad287a055de94280`
  - `tests/phase35/test_hybrid_regime_backtest_perf.py`: `fd0c169fb9a3e3c39043442adc7b1b5b114689d2`

## Reconciled Behavior

- Entrypoint: `LongOnlyConcentratedOverlay.apply()` at `scripts/backtest_hybrid_regime.py:95-140`.
- Selection uses current-row positive ranks plus prior processed-row holdings in `top_k + max(hysteresis, 0)`.
- Retained holdings are not truncated back to `top_k`; fill logic adds ranked symbols only until `top_k` is reached.
- State persists only `long_only_concentrated_prev_selected` from the processed prior row.
- No future joins, forward labels, future returns, or forward panel reads occur in this selection path.
- Execution/cost ordering: the overlay produces weights; transaction-cost accounting is downstream through `cost_breakdown` and profitability diagnostics. No metric-before-cost claim made here.

## Fixture / Window / Config

- Fixture input: `.ly_state/session/fixtures/b1_hysteresis_cleanup_input_20260728.json`
- Fixture golden: `.ly_state/session/fixtures/b1_hysteresis_cleanup_golden_20260728.json`
- Window: `2024-01-01` to `2024-01-02`; symbols `A,B,C,D`.
- Config: `top_k=3`, `hysteresis=1`; seed `0` recorded, with no stochastic branch.
- Tolerance: `1e-12` absolute.
- Fixture byte SHA256:
  - input: `9070a0f5aa97a3e60993ca568addec718da9510f9c8297011e58291dbd257b44`
  - golden: `c0e064b1a5c6d5011229660eb72b2302671c6f35af354d89055eb1c16091eb13`

## Fresh Deterministic Verification

1. `python -m pytest tests/phase35/test_hybrid_regime_backtest_perf.py -k "LongOnlyConcentratedOverlay or hysteresis" -q`
   - Result: `5 passed`.
2. `python -m pytest tests/phase35/test_hybrid_regime_backtest_perf.py -q`
   - Result: `52 passed`.
3. Direct two-day oracle invocation with fixed literal weights, `top_k=3`, `hysteresis=1`.
   - Result: `PASS deterministic oracle`.
   - Assertions: day-1 `A=0.44444444444444453`; day-2 `A=0.125`; final state `['A','B','C']`; tolerance `1e-12`.
4. `python scripts/checklist.py` / `python scripts/verify_all.py` were not run: this task permits writing only the evidence file, and neither script is required to reconcile this existing gate.

## Boundary / Outcome

- No source, test, fixture, phase-gate, manifest, or audit-report mutation performed.
- No L3 audit or approval performed.
- Reconciliation result: current behavior and existing approved scope reproduce deterministically; no reproduction failure observed.
- Status: `READY_FOR_INDEPENDENT_L3_REAUDIT`; L3 verdict required.
