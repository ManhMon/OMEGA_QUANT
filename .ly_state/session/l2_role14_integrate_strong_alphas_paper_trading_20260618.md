# L2 Implementation Report: Strong Alphas Integration into Paper Trading

**Gate:** `STRONG_ALPHAS_INTEGRATION_20260618`
**Role:** 14 (Data Scientist)
**Tier:** 2 (Implementation Only)
**Date:** 2026-06-18
**Scope:** `scripts/paper_trading_daily.py`
**Status:** COMPLETED - Submitted to Tier 3 Audit

---

## 1. Agent & Skill Provenance

### Agent Definition (Repo-Local)
- **File:** `.agents/agent/data-scientist.md`
- **Frontmatter:**
  - `name: data-scientist`
  - `role_id: 14`
  - `tier: 2`
  - `platform: OpenCode`
  - `skills: [python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow]`
  - `sod_boundary: "implementation-only, test required, no self-approval, submit to Tier3"`

### Skills Loaded (Repo-Local: `.agents/skills/`)
| Skill | Path | Status |
|-------|------|--------|
| `quant-research` | `.agents/skills/quant-research/SKILL.md` | LOADED |
| `vietnam-market-data` | `.agents/skills/vietnam-market-data/SKILL.md` | LOADED |
| `python-patterns` | `.agents/skills/python-patterns/SKILL.md` | LOADED |
| `backtesting-pit-safety` | `.agents/skills/backtesting-pit-safety/SKILL.md` | LOADED |

### Forbidden Path Scan
| Path | Scanned | Result |
|------|---------|--------|
| `C:\Users\GHC\.agents\` | NO | Not accessed |
| `C:\Users\GHC\.openclaw\` | NO | Not accessed |
| `C:\Users\GHC\.gemini\` | NO | Not accessed |
| Antigravity scratch paths | NO | Not accessed |
| Codex memory paths | NO | Not accessed |

**Result:** All role/skill files read exclusively from `REPO_AGENT_ROOT` and `REPO_SKILL_ROOT` within `C:\Users\GHC\repos\OMEGA_QUANT\`.

---

## 2. Implementation Summary

### Changes Made to `scripts/paper_trading_daily.py`

**Lines changed:** ~270 lines (from 425 to 692 lines)

#### 2.1 New Alpha Source Imports (Lines 46-47)
```python
from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
```

#### 2.2 New Configuration Constants (Lines 59-68)
| Constant | Value | Purpose |
|----------|-------|---------|
| `LATENT_ALPHAS_PATH` | `_REPO_ROOT / "data" / "latent_alphas_components.parquet"` | Repo-relative path to latent AE parquet |
| `STRONG_LATENT_AE_COLS` | `['latent_ae_00', 'latent_ae_01', 'latent_ae_11']` | Top 3 IR components (|IR| >= 0.3) |
| `USE_LLM_ALPHAS` | `False` | Opt-in flag for LLM alphas |

#### 2.3 VN-Specific Signal Features (Lines 89-125)
- **25 VN-specific alpha features** organized by batch:
  - BATCH 1: VN Liquidity (4 features)
  - BATCH 2: Advanced Mean Reversion (4 features)
  - BATCH 3: Microstructure & Foreign Flows (4 features)
  - Core VN (4 features)
  - BATCH 4: T+2 Settlement & Limit Mechanics (3 features)
  - PHASE 3.4: VN Microstructure (4 features)
  - RESCUE P3 WEEK 1 (2 features)

#### 2.4 Latent AE Signal Features (Lines 127-132)
| Feature | IR | IC (approx) |
|---------|-----|-------------|
| `latent_ae_00` | -0.83 | -0.29 |
| `latent_ae_01` | +0.84 | +0.31 |
| `latent_ae_11` | ~-0.87 | -0.31 |

#### 2.5 Helper Function: `_inject_latent_alphas()` (Lines 138-209)
- Loads `data/latent_alphas_components.parquet`
- Filters to strong IR components
- Merges into panel via left join on (date, symbol) MultiIndex
- NaN for dates outside latent parquet range (2024-01-03 to 2026-06-12)
- Logs coverage diagnostics per column
- Graceful degradation: returns panel unchanged on failure

#### 2.6 Helper Function: `_generate_features_unified()` (Lines 212-264)
- Replaces direct `AlternativeFeatureGenerator` + `AlternativeDataFetcher` calls
- Uses `UnifiedFeatureAdapter` which includes:
  1. Alternative features (25 derived OHLCV)
  2. Alternative data (8 proxy signals)
  3. Arsenal VN-specific alphas (27 functions via `compute_ultimate_alphas`)
  4. Microstructure alphas (P2 wire)
  5. Macro alphas (P2 wire)
  6. LLM symbolic synthesis (opt-in)
- **Legacy fallback:** If `UnifiedFeatureAdapter` fails, falls back to original direct generators
- **LLM safety:** Uses `mock` provider by default for paper trading

#### 2.7 Updated Pipeline (Lines 324-393)
- Step 3: Feature generation now uses `_generate_features_unified()`
- Step 3b: Latent AE injection via `_inject_latent_alphas()`
- Step 5: Combined feature list from all 5 sources:
  1. Legacy alt features (10 signals)
  2. Alt data features (4 signals)
  3. VN-specific alphas (up to 25 signals)
  4. Latent AE components (up to 3 signals)
  5. LLM alphas (dynamic, `alpha_llm_*` columns)
- All signals go through existing T-1 lag enforcement (`panel[feat].groupby(level='symbol').shift(1)`)

#### 2.8 Updated Output (Lines 636-661)
- Added `gate` field: `'STRONG_ALPHAS_INTEGRATION_20260618'`
- Added `alpha_sources` dict with counts per source type

#### 2.9 CLI Arguments (Lines 684-692)
| Argument | Default | Purpose |
|----------|---------|---------|
| `--data-path` | `data/market_2015_now.parquet` | Market data parquet path |
| `--use-llm-alphas` | `False` | Enable LLM-synthesized formulas |

---

## 3. Alpha Sources Integration Matrix

| Source | Module | Columns | IC Range | PIT Safety | Default |
|--------|--------|---------|-----------|------------|---------|
| **Legacy Alt Features** | `alternative_features.py` | 10 signals | 0.04 - 0.41 | T-1 lag | ON |
| **Alt Data** | `alternative_data_fetcher.py` | 4 signals | ~0.05 | T-1 lag | ON |
| **VN-Specific Alphas** | `arsenal.py` -> `vn_specific.py` | 25 signals | 0.04 - 0.08 | T-1 lag (built-in) | ON |
| **Latent AE** | `latent_alphas_components.parquet` | 3 signals | 0.29 - 0.31 | T-1 lag (downstream) | ON (if parquet exists) |
| **LLM Symbolic** | `llm_symbolic_synthesizer.py` | Dynamic | ~0.03 | T-1 lag + grouped execution | OFF (opt-in) |

---

## 4. PIT Safety Analysis

| Alpha Source | PIT Mechanism | Verification |
|-------------|--------------|-------------|
| Legacy signals | `panel[feat].groupby(level='symbol').shift(1)` at line 400 | Existing, unchanged |
| VN-specific | Built-in T-1 lag in each `vn_specific.compute_*()` function | Verified in source |
| Arsenal | `compute_ultimate_alphas()` applies shift in each alpha function | Verified in source |
| Latent AE | Raw features merged, then T-1 lag applied at line 400 | Same downstream path |
| LLM | Per-ticker grouped execution + T-1 lag at line 400 | Verified in `unified_feature_adapter.py` |

**Defense-in-depth:** All signals go through the same T-1 lag enforcement in the signal generation loop (line 400), regardless of source.

---

## 5. Graceful Degradation

| Failure Mode | Behavior |
|-------------|----------|
| `UnifiedFeatureAdapter` import fails | Falls back to legacy `AlternativeFeatureGenerator` + `AlternativeDataFetcher` |
| Arsenal computation fails | Caught by adapter's try/except, logs warning, continues |
| Latent AE parquet missing | `_inject_latent_alphas()` returns panel unchanged, logs warning |
| Latent AE columns not in panel | Skipped in signal feature list |
| LLM provider unavailable | Caught by adapter's try/except, logs warning |
| VN-specific alpha function error | Caught by arsenal's try/except per alpha, continues |

---

## 6. Verification Results

### Syntax Check
```
$ python -m py_compile scripts/paper_trading_daily.py
(no errors)
```

### Import Test
```
$ python scripts/paper_trading_daily.py --help
usage: paper_trading_daily.py [-h] [--data-path DATA_PATH] [--use-llm-alphas]
```

### Module Load Verification
```
VN_SPECIFIC_SIGNAL_FEATURES: 25
LATENT_AE_SIGNAL_FEATURES: 3
STRONG_LATENT_AE_COLS: ['latent_ae_00', 'latent_ae_01', 'latent_ae_11']
LATENT_ALPHAS_PATH exists: True
run_daily_signal callable: True
_inject_latent_alphas callable: True
_generate_features_unified callable: True
```

---

## 7. Files Modified

| File | Change Type | Lines |
|------|-------------|-------|
| `scripts/paper_trading_daily.py` | MODIFY | 425 -> 692 (+267 lines) |

---

## 8. Source Files Read (Repo-Relative)

| File | Purpose |
|------|---------|
| `.agents/agent/data-scientist.md` | Agent definition and role constraints |
| `.agents/skills/quant-research/SKILL.md` | Alpha research principles |
| `.agents/skills/vietnam-market-data/SKILL.md` | VN market data contract |
| `.agents/skills/python-patterns/SKILL.md` | Python development principles |
| `.agents/skills/backtesting-pit-safety/SKILL.md` | PIT safety requirements |
| `src/omega/quant/alpha/arsenal.py` | VN-specific alpha orchestration |
| `src/omega/quant/alpha/vn_specific.py` | 27 VN-specific alpha functions |
| `src/omega/quant/alpha/vn.py` | Optimized 10-group VN features |
| `src/omega/quant/evolution/unified_feature_adapter.py` | Unified feature generation |
| `src/omega/quant/models/latent_encoder.py` | NonlinearDeepLatentEncoder |
| `data/latent_alphas_components.parquet` | Pre-computed latent AE components |
| `.ly_state/session/latent_alphas_report_20260617.md` | Latent AE IR analysis |
| `.ly_state/session/vn_alphas_evaluation.json` | VN alpha IC/IR evaluation |

---

## 9. Tier 3 Audit Submission

**Submitted to:**
- Code Reviewer (Role 21): Code quality, reproducibility, PIT safety review
- QA Engineer (Role 17): Model validation, integration testing review

**Audit Checklist:**
- [ ] All new alpha sources T-1 lagged (PIT-safe)
- [ ] Graceful degradation on all new sources
- [ ] Repo-relative paths only (no external paths)
- [ ] CLI arguments for opt-in features
- [ ] Output JSON includes alpha source metadata
- [ ] Legacy backward compatibility preserved
- [ ] No self-approval (Tier 2 constraint)

---

## 10. Notes for Tier 3 Reviewers

1. **VN-specific alphas** are computed by `arsenal.compute_ultimate_alphas()` which is already tested in the phase 3.5 backtest pipeline. Each function has built-in T-1 lag.

2. **Latent AE components** are pre-computed and stored in parquet. The injection is a simple merge operation. The strong components (IR >= 0.3) were selected from the latent_alphas_report_20260617.md analysis.

3. **LLM alphas** are opt-in only (default off) because:
   - Mock provider produces deterministic templates, not genuine alpha signals
   - Real provider requires API key configuration
   - Unsupervised-only formulas are flagged as "NOT PRODUCTION-DEPLOYABLE"

4. **Backward compatibility:** The script falls back to legacy feature generators if `UnifiedFeatureAdapter` fails, ensuring no regression in paper trading signal generation.
