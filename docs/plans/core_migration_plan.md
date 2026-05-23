# OMEGA_QUANT Core Migration Plan

## 1. Migration Overview
Migrate 36 modules from V21_QUANT `layer_01_core_intelligence` to OMEGA_QUANT `omega.core` canonical structure.
Enforce T-1 lag, `as_of` <= `available_at` PIT safety, 100% vectorization, and canonical imports.
Target: `packages/omega-core/src/omega/core/`

## 2. Dependency Graph & Phases

### Phase 1: Data Infrastructure & Utilities (Foundation)
Base datasources, config, and sanitizers required by higher-level modules.
- `data_source_config.py` (Low) -> Infra Agent
- `vn_trading_calendar.py` (Low) -> Infra Agent
- `data_validator.py` (Low) -> Infra Agent
- `data_sanitizer.py` (Medium) -> Data/Feature Agent
- `vnstock_datasource.py` (Medium) -> Infra Agent
- `vci_integration.py` (Medium) -> Infra Agent
- `vnstock_vci_datasource.py` (Low) -> Infra Agent
- `vnstock_vci_ingest.py` (Low) -> Infra Agent
- `vn_market_flow_datasource.py` (Medium) -> Infra Agent
- `live_ingestor.py` (Medium) -> Infra Agent
- `corporate_action.py` (Medium) -> Feature Agent

### Phase 2: Feature Engineering & Processing
Core feature pipelines and pruning logic.
- `feature_module.py` (Medium) -> Feature Agent
- `data_module.py` (Medium) -> Feature Agent
- `structure_features.py` (High) -> Feature Agent
- `smart_money_features.py` (Medium) -> Feature Agent
- `advanced_features.py` (Medium) -> Feature Agent
- `feature_pruning.py` (High) -> Feature Agent
- `feature_discovery.py` (Medium) -> Feature Agent
- `sector_classifier.py` (Medium) -> Feature Agent

### Phase 3: Alpha Generation & Validation
Alpha generation, sanitization, and heavy compute modules.
- `alpha_sanitizer.py` (Medium) -> Alpha Agent
- `vn_alphas.py` (Medium) -> Alpha Agent
- `macro_alphas.py` (Medium) -> Alpha Agent
- `microstructure_alphas.py` (Low) -> Alpha Agent
- `phase34_microstructure_alphas.py` (Medium) -> Alpha Agent
- `genetic_programming.py` (High) -> Alpha Agent
- `high_alpha_filter.py` (High) -> Alpha Agent
- `midas_filters.py` (Low) -> Alpha Agent
- `decorrelation_engine.py` (Low) -> Alpha Agent
- `ultimate_alpha_arsenal.py` (High) -> Alpha Agent [Requires Heavy Resources]

### Phase 4: Validation, Signals & Promotion
Walk-forward optimization, signal generation, and promotion logic.
- `target_module.py` (Medium) -> Research Agent
- `wfo_validation.py` (Medium) -> Research Agent
- `phase35_walk_forward.py` (Medium) -> Research Agent
- `signal_sanitizer.py` (Low) -> Research Agent
- `signal_module.py` (Medium) -> Research Agent
- `promoted_alphas.py` (Low) -> Research Agent

## 3. Standard Requirements
For ALL modules migrated:
1. **PIT Safety**: Absolute enforcement of `as_of <= available_at`.
2. **T-1 Lag**: Features must be computed on T-1 data for T trading.
3. **Vectorization**: No `iterrows` or `apply` where Pandas/NumPy native ops exist.
4. **Imports**: Canonical paths (`from omega.core import ...`).
5. **Testing**: 10+ comprehensive tests per module (unit + property-based).

## 4. Agent Assignments & Estimated Effort

| Agent | Modules Assigned | Total Complexity | Priority |
|---|---|---|---|
| **Infra Agent** | Config, Calendars, Validators, Datasources (9 modules) | Medium | 1 (Highest) |
| **Feature Agent** | Feature modules, Pruning, CA, Sector Classifier (8 modules) | High | 2 |
| **Alpha Agent** | Alphas, GP, Decorrelation, Arsenal (10 modules) | Very High | 3 |
| **Research Agent** | WFO, Signals, Promoted Alphas, Targets (6 modules) | Medium | 4 |

## 5. Execution Protocol
1. Assign tasks strictly according to the phases to avoid unresolved imports.
2. Agents must write tests *first* or *concurrently* (10+ tests).
3. Agents must run `pytest` on their module before moving to the next.
4. The Verification/Review Agent must audit each migrated file for the 4 Standard Requirements.