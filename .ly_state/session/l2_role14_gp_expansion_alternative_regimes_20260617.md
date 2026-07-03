# L2 Implementation Summary — `scripts/run_weekly_evolution.py`

### Role Load Evidence
| Field | Value |
|-------|-------|
| **Role** | data-scientist (ID 14, Tier L2) |
| **Role file** | `.agents/agent/data-scientist.md` |
| **Role SHA256** | `ba6b3397ec3ae9826dd06e24a33f2d0f62f6315ed10f9540788edc0ca31dcba3` ✅ |
| **SOD Skill** | `.agents/skills/omega-sod/SKILL.md` |
| **SOD SHA256** | `44ab0b9a8462216d3f52ec55e52bf9f9deae9598a22b4ad78fbc4e271f5a7e9a` ✅ |
| **Platform** | OpenCode (L2 Developer) |
| **SOD Boundary** | implementation-only, no self-approval, submit to Tier 3 |

---

### Changes Implemented

**File:** `scripts/run_weekly_evolution.py` (632 → 1088 lines)

#### 1. AlternativeFeatureGenerator Integration
- **Function:** `_generate_alternative_features()` (line 378)
- Converts flat DataFrame → MultiIndex `[date, symbol]` panel (with proper `ticker→symbol` level rename)
- Calls `AlternativeFeatureGenerator.generate_all()` → 25 features
- Calls `AlternativeDataFetcher.generate_all()` → 10 features
- Prefixes all new columns with `alt_` to avoid name collisions
- Merges back to flat DataFrame with `symbol→ticker` rename
- Graceful fallback on failure (try/except per generator)
- **T-1 PIT lag** applied to all alt features in `prepare_features()` (line 354)
- **Toggle:** `--no-alt-features` CLI flag to disable

#### 2. AlternativeDataFetcher Integration
- Integrated within `_generate_alternative_features()` alongside AlternativeFeatureGenerator
- Uses `use_api=False` (OHLCV-derived proxy mode)
- Features: `alt_foreign_flow`, `alt_margin_proxy`, `alt_sector_rotation`, `alt_order_imbalance`, `alt_liquidity_shock`, `alt_foreign_flow_ma5`, `alt_margin_trend`, `alt_rotation_momentum`, `alt_vsi_score`, `alt_focal_stress_score`

#### 3. Multi-Horizon Targets: `target_h3` / `target_h5` / `target_h10`
- **Constants updated:** `MULTI_TARGET_HORIZONS = [3, 5, 10]` (was `[5, 10, 20]`)
- **Weights:** `MULTI_TARGET_WEIGHTS = [0.5, 0.3, 0.2]` (short > medium > long)
- **Target computation** in `prepare_features()` (line 360): computes `target_h3`, `target_h5`, `target_h10` per ticker
- **GP integration:** `run_evolution()` injects `target_h{N}` into features dict for `_compute_combined_ic()` (line 644)
- **Primary target** remains `target` (T+5) for backward compatibility and bridge registration

#### 4. Orthogonalization CLI Switch (`--orthogonalize`)
- **CLI arguments added:**
  - `--orthogonalize {promoted,momentum,file,none}` — main switch
  - `--ortho-baseline-path` — custom baseline JSON path
  - `--ortho-penalty-weight` (default: 0.05)
  - `--ortho-correlation-threshold` (default: 0.5)
- **Baseline sources:**
  - `promoted`: Loads previously evolved alpha formulas from `evolved_alphas.json`, re-evaluates via `_parse_formula_string()` + `GPIndividual._execute_tree()`
  - `momentum`: Uses raw momentum features (returns_1d/5d/10d, rsi_14, ma_ratio_5_20)
  - `file`: Custom JSON baseline
  - `none`: Disabled (default)
- **Formula parser:** `_parse_formula_string()` — recursive descent parser that handles all GPNode.to_string() formats (terminal, unary, binary, TS ops) with **10/10 roundtrip accuracy** (exact match, max_diff=0.000000)
- **Fallback:** Composite approximation when tree parsing fails
- **Wiring:** Baseline set passed to `GPConfig.ortho_baseline_set` → `GPIndividual.orthogonalization_penalty` in fitness

#### 5. Updated Functions
- `evaluate_and_promote()`: Test feature dict includes alt features + multi-horizon targets
- `save_results()`: Output JSON includes `multi_target_horizons`, `multi_target_weights`, `orthogonalization.enabled`, `alternative_features.enabled`
- Validation culling in `main()`: Feature dict includes alt features + multi-horizon targets

---

### PIT Safety Verification
| Check | Status |
|-------|--------|
| T-1 lag on standard features | ✅ (line 348, per ticker) |
| T-1 lag on alternative features | ✅ (line 354, per ticker) |
| Chronological walk-forward split | ✅ (unchanged) |
| No look-ahead in target computation | ✅ (shift(-horizon), line 360-365) |
| MultiIndex level rename prevents data leak | ✅ (ticker→symbol→ticker) |

### Validation Results
| Test | Result |
|------|--------|
| Python syntax check | ✅ PASS |
| Module import | ✅ PASS |
| CLI `--help` output | ✅ All 9 arguments shown |
| `_parse_formula_string` roundtrip (10 random trees) | ✅ 10/10 PASS, max_diff=0.000000 |
| `_generate_alternative_features` mock data | ✅ 35 alt features generated |
| `_build_ortho_baseline_set` (momentum) | ✅ 5 baselines |
| `_build_ortho_baseline_set` (promoted) | ✅ 2 baselines loaded |
| Existing `test_memory_evolution.py` (5 tests) | ✅ 5/5 PASS |

---

### L3 Audit Handoff

**Submitted to:**
- Code Reviewer (Role 21): Code quality, reproducibility, formula parser correctness
- QA Engineer (Role 17): PIT safety verification, integration testing, edge cases

**Key areas for L3 review:**
1. Formula parser robustness against adversarial/malformed formula strings
2. Memory efficiency of `_generate_alternative_features()` with large datasets (~millions of rows)
3. `_build_ortho_baseline_set("promoted")` — graceful handling when evolved_alphas.json contains formulas referencing features not in current feature set
4. `_no_alt_features` monkey-patch approach — is it acceptable or should it be refactored to a parameter?
5. Bridge horizon restriction: `AlphaToExecutionBridge.register_alpha()` only accepts horizon ∈ {3, 5}, but multi-target uses [3, 5, 10]. Currently uses primary horizon (5) for registration.

**Status: Awaiting L3 verdict. Cannot self-approve per SOD boundary.**
