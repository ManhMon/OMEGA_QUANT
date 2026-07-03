**Role 20 - Compliance Officer Audit**

**Verdict:** `[NEEDS_FIX]`

Plan is structurally reasonable, but not compliance-approved for institutional quant use yet. Main issue: restructuring `ultimate_alpha_arsenal.py` can silently break PIT behavior unless the plan adds explicit PIT parity gates, alpha output parity tests, data-lineage checks, and SOD gate enforcement.

**P0 Findings**

1. **PIT preservation not specified as a hard gate.**  
Current alpha code is explicitly T-1: `compute_roc()` documents T-1 and applies `groupby(symbol).shift(1)` at [ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:149), [ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:176). Volatility, VN-specific, T+2, market correlation, cross-sectional alphas also use pre-lagged inputs or second-order shifts: [ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:461), [ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:1541), [ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:2901), [ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3485).  
Plan Phase 1 says split by category and preserve imports, but does not require PIT-equivalent outputs per alpha. See plan at line 102 and wrapper-only compat at line 132.

2. **No golden parity requirement before split.**  
`compute_ultimate_alphas()` declares all alphas T-1/PIT-safe at [ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3542) and [ultimate_alpha_arsenal.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/ultimate_alpha_arsenal.py:3555). Plan only requires `pytest`, `pycodestyle`, import smoke, backward compat, docs at plan lines 238-243. Missing mandatory gate: old monolith output == new split output for same fixture, same sort order, same NaN/zero fill, same first-row lag behavior.

3. **Combined L4 approval cannot substitute Role 20 compliance.**  
Combined audit says Codex CLI unavailable due 402 and L4 directly performed Roles 6/21/25 at combined audit lines 3 and 11. It approves with recommendations, but Role 20 PIT compliance was not in scope. Combined audit also found circular dependencies and says add Phase 0 before Phase 1 at lines 17, 93, 123.

**P1 Findings**

4. **Look-ahead risk during module split.**  
Risk scenarios:
- Helper extraction changes `sort_values(['date', symbol])` order before `groupby().shift(1)`.
- Moving cross-sectional functions accidentally computes same-day ranks before lag.
- Thin wrapper re-export preserves imports but not exact execution order.
- Duplicate merge picks older modules with weaker PIT guarantees.
- Import rewrite changes fallback path in promoted/microstructure wrappers.

5. **Data pipeline integrity only partially covered.**  
Actual repo has PIT guards: `PITGuardian` requires `Feature < Decision <= Execution` and fail-closed missing timestamps at [pit_guardian.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/pit_guardian.py:9), [pit_guardian.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/pit_guardian.py:88). `PITGuard` enforces `as_of <= available_at` at [pit_guard.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/pit_guard.py:6). `DataModule` handles delisted universe metadata at [data_module.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/data_module.py:35), [data_module.py](C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/data_module.py:56). Plan does not require preserving these guards across `data/`, `feature/`, `alpha/`, `walk_forward/` boundaries.

6. **Audit trail spec incomplete vs repo enforcement.**  
Plan includes gate contract at lines 245-255 and says update `phase_gates.json` at line 235. But it omits mandatory `python scripts/sod_gate_enforcer.py`. The enforcer exists and checks required L3 fields at [sod_gate_enforcer.py](C:/Users/GHC/repos/OMEGA_QUANT/scripts/sod_gate_enforcer.py:67). Also current `phase_gates.json` has inconsistent key shape: one Tier3 entry uses `name` + `audit_report`, not `phase_name` + `audit_report_path` at [phase_gates.json](C:/Users/GHC/repos/OMEGA_QUANT/.ly_state/session/phase_gates.json:820). Plan must normalize this.

**P2 Findings**

7. **Rollback instruction is unsafe as written.**  
Plan says `git reset --hard pre-restructure-phase-X` at line 263. For compliance, use non-destructive rollback procedure or explicit human approval, plus evidence preservation before reset.

8. **Performance/vectorization gate too weak.**  
Combined audit recommends perf benchmarks at line 134. Plan should require before/after runtime + memory benchmarks for alpha computation, because splitting imports can alter materialization, copies, and vectorized paths.

**Required Fixes Before Approval**

- Add **Phase 0** before Phase 1: resolve circular deps, especially `promoted_alphas ↔ ultimate_alpha_arsenal`.
- Add **PIT golden parity suite**: old monolith vs split modules, all alpha columns, sorted panel fixtures, first-row/ticker-boundary lag checks, NaN/zero-fill parity, no same-day feature leakage.
- Add **data lineage gate**: `as_of`, `available_at`, `feature_ts`, `decision_ts`, `execution_ts` preserved through ingestion → feature → alpha → signal → portfolio.
- Add **look-ahead negative tests**: intentionally unsorted panel, same-day close leak, `fwd_ret_*` in feature cols, target/label keyword columns, cross-sectional rank before lag.
- Add **gate enforcement step**: run `python scripts/sod_gate_enforcer.py` after every phase and record result/checksum in `phase_gates.json`.
- Normalize gate schema: require `phase_name`, `l2_session_id`, `l2_completed`, `l3_session_id`, `l3_session_key`, `audit_report_path`, `final_verdict`, `status`, `report_checksum`.
- Replace destructive rollback wording with approved rollback protocol preserving audit artifacts.

**Coverage Matrix**

- PIT Safety: **FAIL until parity gates added**
- Look-ahead Bias: **FAIL; scenarios not controlled**
- V21/Institutional Standards: **PARTIAL; structure ok, compliance gates weak**
- Data Integrity: **PARTIAL; repo has guards, plan does not preserve them explicitly**
- Audit Trail: **PARTIAL; gate contract exists, enforcer/checksum/schema gaps**
- Compliance Gaps: **Phase 0, PIT parity, lineage, negative leakage tests, gate normalization**

Final: `[NEEDS_FIX]`.

