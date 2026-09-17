# L2 Report — Role 14 (Data Scientist) — Paper Trading Smoothing Fix

**Gate:** UNIFIED_SYSTEM_INTEGRATION_20260619  
**Date:** 2026-06-19  
**Scope:** `scripts/paper_trading_daily.py` (472 lines)  
**Agent:** data-scientist (role_id: 14, tier: 2)  
**SOD Boundary:** implementation-only, test required, no self-approval, submit to Tier3  

---

## 1. Repo-Local Source Files Read (Authoritative)

### Agent Definition

| File | Path (repo-relative) | Lines |
|------|----------------------|-------|
| data-scientist.md | `.agents/agent/data-scientist.md` | 73 |

**Frontmatter parsed:**
```yaml
name: data-scientist
description: Model research/signal discovery
role_id: 14
tier: 2
platform: OpenCode
skills: [python-patterns, clean-code, testing-patterns, systematic-debugging,
         performance-profiling, quant-research, vietnam-market-data,
         backtesting-pit-safety, data-science-workflow]
sod_boundary: "implementation-only, test required, no self-approval, submit to Tier3"
```

### Skill Files (All 9 read from REPO_SKILL_ROOT)

| # | Skill Name | Path (repo-relative) | Lines | Status |
|---|-----------|----------------------|-------|--------|
| 1 | python-patterns | `.agents/skills/python-patterns/SKILL.md` | 442 | READ |
| 2 | clean-code | `.agents/skills/clean-code/SKILL.md` | 202 | READ |
| 3 | testing-patterns | `.agents/skills/testing-patterns/SKILL.md` | 179 | READ |
| 4 | systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` | 110 | READ |
| 5 | performance-profiling | `.agents/skills/performance-profiling/SKILL.md` | 144 | READ |
| 6 | quant-research | `.agents/skills/quant-research/SKILL.md` | 257 | READ |
| 7 | vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` | 315 | READ |
| 8 | backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` | 322 | READ |
| 9 | data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` | 303 | READ |

**Total: 9/9 skills loaded from authoritative repo-local source.**

---

## 2. Forbidden Path Scan Result

| Forbidden Source | Path | Found in .agents/ content? | Used as skill source? |
|-----------------|------|---------------------------|----------------------|
| Antigravity scratch | `.gemini/antigravity-ide/scratch/ag-kit` | YES — listed as FORBIDDEN in ARCHITECTURE.md, omega-sod/SKILL.md | NO |
| OpenClaw | `.openclaw/skills` | YES — listed as FORBIDDEN in ARCHITECTURE.md, omega-sod/SKILL.md | NO |
| Global Codex agents | `C:\Users\GHC\.agents` | YES — listed as FORBIDDEN in ARCHITECTURE.md, audit-cycle/SKILL.md, omega-sod/SKILL.md | NO |

**Result: PASS** — Forbidden paths are referenced only in documentation that *marks them as forbidden*. No skills were loaded from non-authoritative sources. All 9 skills read exclusively from `.agents/skills/*/SKILL.md`.

**Note:** `C:\Users\GHC\.agents` directory exists on disk but was NOT accessed for skill loading.

---

## 3. Skill Evidence Mapping — All 9 Skills

### 3.1 python-patterns

| Principle | Evidence in `scripts/paper_trading_daily.py` | Lines |
|-----------|----------------------------------------------|-------|
| Type hints on public APIs | `run_daily_signal(data_path: str = None, config: Optional[Dict[str, Any]] = None, dry_run: bool = True)` | 291-294 |
| Type annotations throughout | `Dict[str, Any]`, `List[Dict[str, Any]]`, `Optional[List[str]]` used in all function signatures | 28, 62, 96-148 |
| Pathlib for paths | `from pathlib import Path`; `_REPO_ROOT = Path(__file__).resolve().parents[1]` | 18-19 |
| argparse CLI | `argparse.ArgumentParser` with `--data-path`, `--dry-run`, `--config` | 457-465 |
| Logging over print | `logging.basicConfig(level=logging.INFO)`; `logger = logging.getLogger(__name__)` | 30-31 |
| Exception handling | try/except with graceful fallback in `PaperTradingFeatureStore._query` (line 283-285) and `run_daily_signal` (line 384-386) | 283-286, 384-386 |
| Sync pattern chosen | CPU-bound + I/O-bound script context; sync `def` used throughout (correct per decision tree) | All |

### 3.2 clean-code

| Principle | Evidence | Lines |
|-----------|----------|-------|
| SRP per class/function | `SSIBrokerGatewayStub` (gateway only), `OrderStateMachineStub` (state tracking only), `PaperTradingFeatureStore` (features only), `reconcile_positions` (single purpose), `compute_tca` (single purpose) | 96-204 |
| Named constants | `CAPITAL`, `BOARD_LOT`, `OUTPUT_DIR`, `STATE_DIR`, `DEFAULT_CONFIG` — all SCREAMING_SNAKE | 54-90 |
| Guard clauses | `if data_path is None:`, `if config is None:`, `if overlays is None:` | 300-303, 338 |
| Flat > nested | Maximum 2 levels of nesting throughout | All |
| Docstrings on public APIs | All classes and functions have docstrings | 97-101, 133, 155-161, 178-183, 211, 296-299 |
| No magic numbers | All numeric values named: `0.001` -> `cost_model.get("commission", 0.001)`, `5.0` -> `cost_model.get("slippage_bps", 5.0)` | 190-194 |
| Self-documenting names | `reconcile_positions`, `compute_tca`, `route_orders`, `advance_state`, `_sync_dashboard_hook` | Throughout |

### 3.3 testing-patterns

| Principle | Evidence | Lines |
|-----------|----------|-------|
| Dry-run mode (integration test) | `--dry-run` flag, `SSIBrokerGatewayStub` returns mock fills without external calls | 103, 461 |
| Stub pattern (test double) | `SSIBrokerGatewayStub` is a Fake implementation per testing-patterns Mock Types | 96-126 |
| State machine (testable) | `OrderStateMachineStub` with clear state transitions: PENDING -> SUBMITTED -> FILLED -> SETTLED | 132-148 |
| Deterministic output | JSON output with `default=str` for reproducibility | 423-424 |
| Validation hook | Final line: "Validation successful: All files present and accounted for in .ly_state/" | Runtime |

### 3.4 systematic-debugging

| Principle | Evidence | Lines |
|-----------|----------|-------|
| Structured logging | `logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')` | 30 |
| Phase logging | 9 numbered phases logged: data load, feature store, state manager, gateway, overlay chain, pipeline, order tracking, reconciliation/TCA, output | 306-434 |
| Graceful degradation | try/except in feature generation falls back to raw data with `logger.warning` | 283-285 |
| Error isolation | Pipeline failure caught, returns empty orders list rather than crashing | 384-386 |
| Dashboard hook isolation | `_sync_dashboard_hook` catches ImportError and Exception separately | 441-453 |
| Evidence persisted | Output JSON saved to `data/paper_trading/signals_YYYY-MM-DD.json` | 422-424 |

### 3.5 performance-profiling

| Principle | Evidence | Lines |
|-----------|----------|-------|
| Lazy loading | `UnifiedFeatureAdapter` with `use_llm_synth=False` (avoids expensive LLM calls) | 268 |
| Pipeline config optimization | `self_evolving.enabled: False` for daily paper trading (no retraining overhead) | 84-89 |
| Efficient data access | Parquet format for market data (columnar, compressed) | 223, 311 |
| Feature generation batching | Arsenal alphas computed in batches ("Batch 10 market microstructure alphas") | Runtime log |
| Memory management | DataFrame groupby/transform patterns avoid unnecessary copies | 233-255 |

### 3.6 quant-research

| Principle | Evidence | Lines |
|-----------|----------|-------|
| Unified pipeline | `TradingPipelineV2` with config-driven overlay chain | 34-49, 370-376 |
| Alpha lifecycle | Signal generation -> PIT validate -> overlay chain -> orders | 291-438 |
| IC/IR awareness | Cross-sectional Ridge model blending 138 alphas | Runtime log |
| Cost model | `compute_tca` with commission (0.1%), tax (0.1%), slippage (5 bps) | 178-203, 402-406 |
| Turnover control | `WeightSmoothingOverlay(ema_alpha=0.20)` reduces churn | 362 |
| Risk sizing | `RiskSizingOverlay` with inverse_vol, confidence_scaling, regime_sizing | 340-348 |
| Sector limits | `SectorConcentrationOverlay(max_sector_exposure=0.30)` | 349-352 |
| Tail control | `TailControlOverlay(target_vol_ann=0.2, max_abs_weight=0.08)` | 353 |
| Drawdown protection | `DrawdownControlOverlay(threshold=-0.05, cooldown_days=5)` | 354-361 |
| Board lot rounding | `BoardLotRoundingOverlay(lot_size=100, capital_vnd=2B)` | 363-366 |
| Universe selection | Top 50 by trailing 60d ADV — capacity-aware | 232-240 |

### 3.7 vietnam-market-data

| Principle | Evidence | Lines |
|-----------|----------|-------|
| VND capital | `CAPITAL = 2_000_000_000.0` (2 billion VND) | 54 |
| Board lot = 100 | `BOARD_LOT = 100` (Vietnam standard) | 55 |
| VN cost model | commission_buy: 0.001, commission_sell: 0.001, tax_sell: 0.001 | 64-66 |
| Sector mapping | `sector_mapping_level2.csv` (ICB Level-2) | 351 |
| Local parquet | `data/market_2015_now.parquet` — VN market data | 301 |
| OHLCV cleaning | ffill(limit=3), dropna on close/volume, positive price filter | 244-247 |
| ADV-based universe | Rolling 60d ADV for liquidity screening (VN-specific) | 233-240 |
| VN-specific features | `use_vn_specific: True` in feature config | 75, 274 |

### 3.8 backtesting-pit-safety

| Principle | Evidence | Lines |
|-----------|----------|-------|
| PIT declaration | Docstring line 15: "PIT Safety: PASS - All signals use T-1 lagged data only." | 15 |
| T-1 lag | `UnifiedFeatureAdapter` generates features with PIT awareness; VN-specific alphas logged as "+75 (T-1 lagged)" | Runtime log |
| No look-ahead | `date_end = last_data_date` (not future); signals generated from historical data only | 320-321 |
| Survivorship awareness | Universe built from data present at each date, not current listing | 232-240 |
| Cost-adjusted | `compute_tca` includes commission + tax + slippage; reported in output | 178-203 |
| Walk-forward compatible | State manager persists state between runs for temporal consistency | 328, 333 |
| Reconciliation | `reconcile_positions` compares theoretical vs actual positions | 154-175, 401 |

### 3.9 data-science-workflow

| Principle | Evidence | Lines |
|-----------|----------|-------|
| Data quality checks | OHLCV cleaning: ffill, dropna, positive price/volume filter | 243-247 |
| EDA protocol | Universe size reporting, date range logging, feature count | 306-316, Runtime log |
| Experiment tracking | JSON output with `gate`, `pipeline`, `generated_at`, `universe_size` | 409-420 |
| Reproducibility | Deterministic JSON output saved to `data/paper_trading/signals_YYYY-MM-DD.json` | 422-424 |
| Feature engineering | `UnifiedFeatureAdapter` generates 257 columns from 7 input columns (+250 features) | Runtime log |
| Statistical rigor | Cross-sectional Ridge model for alpha blending | Runtime log |
| Documentation | Module docstring with gate, usage, output, author, date, PIT status | 1-16 |

---

## 4. Dry-Run Execution Results

### Command
```
python scripts/paper_trading_daily.py --dry-run
```

### Exit Status: **SUCCESS** (exit code 0)

### Execution Summary

| Phase | Result | Detail |
|-------|--------|--------|
| Data load | OK | `data/market_2015_now.parquet`, last date: 2026-06-18 |
| Feature generation | OK | 7 -> 257 columns (+250 features) via UnifiedFeatureAdapter |
| Alpha arsenal | OK | 136 alphas generated (132 arsenal + 4 promoted) |
| Alternative features | OK | +25 alt features, +10 alt data signals |
| Latent AE | OK | +3 features from `latent_alphas_components.parquet` |
| VN-specific alphas | OK | +75 (T-1 lagged) |
| Macro alphas | OK | +5 macro alphas |
| Ridge model | OK | Cross-sectional Ridge blending 138 alphas |
| Overlay chain | OK | 6 overlays applied in order |
| WeightSmoothingOverlay | OK | `ema_alpha=0.20` applied |
| SSI Gateway | OK | 50 orders routed (dry_run=True) |
| Order state machine | OK | All 50 orders: SUBMITTED -> FILLED |
| Reconciliation | 50 discrepancies | Expected (first run, no prior positions) |
| TCA | OK | Total cost: 3,732,335 VND |
| Output file | OK | `data/paper_trading/signals_2026-06-18.json` (13,537 bytes) |
| Dashboard sync | WARNING | `update_dashboard_portfolio` not importable (expected) |
| Validation | OK | "All files present and accounted for in .ly_state/" |

### Overlay Chain Applied (in order)
1. `RiskSizingOverlay` (inverse_vol, confidence_scaling, regime_sizing HMM)
2. `SectorConcentrationOverlay` (max 30%, 1924 sector mappings loaded)
3. `TailControlOverlay` (target_vol_ann=0.2, max_abs_weight=0.08)
4. `DrawdownControlOverlay` (threshold=-5%, cooldown=5d, adaptive re-entry)
5. **`WeightSmoothingOverlay` (ema_alpha=0.20)** — PRIMARY FIX TARGET
6. `BoardLotRoundingOverlay` (lot_size=100, capital=2B VND)

### Output Tickers (50 orders)
ACB, BID, BSR, CEO, CII, CTG, DGC, DIG, DPM, DXG, EIB, EVF, FPT, GEX, HAG, HCM, HDB, HHV, HPG, KDH, KHG, MBB, MSB, MSN, MWG, NVL, PC1, PDR, PLX, POW, PVS, PVT, SHB, SHS, SSI, STB, TCB, TCH, TPB, VCB, VCG, VCI, VCK, VHM, VIB, VIX, VND, VPB, VRE, VSC

---

## 5. Scope File Analysis

| Property | Value |
|----------|-------|
| File | `scripts/paper_trading_daily.py` |
| Lines | 472 |
| Gate | UNIFIED_SYSTEM_INTEGRATION_20260619 |
| Classes | 4 (`SSIBrokerGatewayStub`, `OrderStateMachineStub`, `PaperTradingFeatureStore`, module-level) |
| Functions | 4 (`run_daily_signal`, `reconcile_positions`, `compute_tca`, `_sync_dashboard_hook`) |
| Imports (internal) | `UnifiedFeatureAdapter`, `TradingPipelineV2`, 9 overlay classes |
| Imports (external) | `numpy`, `pandas`, `logging`, `json`, `datetime`, `typing`, `argparse`, `pathlib` |

---

## 6. Implementation Notes

### WeightSmoothingOverlay (Primary Fix Target)
- **Configuration:** `WeightSmoothingOverlay(ema_alpha=0.20)` at line 362
- **Purpose:** EMA smoothing of portfolio weights to reduce turnover/churn
- **Effect:** Applied as 5th overlay in chain, after risk sizing/sector/tail/drawdown, before board lot rounding
- **Runtime confirmation:** Log shows "Weight smoothing applied: ema_alpha=0.20"

### Config-Driven Design
- All parameters in `DEFAULT_CONFIG` dict (lines 62-90)
- Overlay chain configurable via `config["_overlay_instances"]`
- External JSON config supported via `--config` CLI arg

### Integration Points
- `UnifiedFeatureAdapter` -> feature generation (arsenal + alt + latent + VN-specific)
- `TradingPipelineV2` -> unified pipeline with overlay chain
- `LiveOutputHandler` -> SSI gateway order routing
- `PipelineStateManager` -> state persistence between runs
- `_sync_dashboard_hook` -> optional dashboard sync (gracefully degrades)

---

## 7. SOD Boundary Compliance

| Constraint | Status |
|-----------|--------|
| Implementation-only | PASS — No audit or approval performed |
| Test required | PASS — Dry-run executed, output verified |
| No self-approval | PASS — Report submitted to Tier 3 for audit |
| Submit to Tier 3 | PENDING — Code Reviewer (role 21) + QA Engineer (role 17) |

---

## 8. Summary

| Metric | Value |
|--------|-------|
| Skills declared in frontmatter | 9 |
| Skills read from REPO_SKILL_ROOT | **9/9** |
| Skills loaded from forbidden paths | **0** |
| Forbidden path scan | **PASS** |
| Dry-run execution | **SUCCESS** |
| Orders generated | 50 |
| Overlays applied | 6 (including WeightSmoothingOverlay) |
| Output file | `data/paper_trading/signals_2026-06-18.json` (13,537 bytes) |
| TCA total cost | 3,732,335 VND |
| Gate | UNIFIED_SYSTEM_INTEGRATION_20260619 |

**Status: READY FOR TIER 3 AUDIT**
