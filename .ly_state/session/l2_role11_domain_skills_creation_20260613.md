# L2 Report: Domain Skills Creation for OMEGA_QUANT

**Gate:** DOMAIN_SKILLS_CREATION_20260613
**Role:** devops-engineer (role_id: 11, tier: 2, platform: OpenCode)
**Date:** 2026-06-13
**Session ID:** l2_role11_domain_skills_creation_20260613

---

## Repo-Local Role/Skill Source Evidence

### REPO_AGENT_ROOT: `C:/Users/GHC/repos/OMEGA_QUANT/.agents/agent`

Exact repo-local agent files read:

1. `.agents/agent/devops-engineer.md` — role_id=11, tier=2, platform=OpenCode, skills=[deployment-procedures, server-management, clean-code, testing-patterns, systematic-debugging]
2. `.agents/agent/data-scientist.md` — role_id=14, tier=2, platform=OpenCode, skills updated
3. `.agents/agent/machine-learning-engineer.md` — role_id=16, tier=2, platform=OpenCode, skills updated
4. `.agents/agent/data-engineer.md` — role_id=15, tier=2, platform=OpenCode, skills updated

### REPO_SKILL_ROOT: `C:/Users/GHC/repos/OMEGA_QUANT/.agents/skills`

Exact repo-local skill files read (declared by devops-engineer frontmatter):

1. `.agents/skills/deployment-procedures/SKILL.md` — Production deployment principles
2. `.agents/skills/server-management/SKILL.md` — Server management principles
3. `.agents/skills/clean-code/SKILL.md` — Pragmatic coding standards
4. `.agents/skills/testing-patterns/SKILL.md` — Testing patterns and principles
5. `.agents/skills/systematic-debugging/SKILL.md` — 4-phase debugging methodology

---

## Forbidden Path Scan Evidence

Scan of all four forbidden paths — every mention below is non-authoritative:

| Forbidden Path | Exists on Disk | Scan Result |
|----------------|---------------|-------------|
| `.gemini\antigravity-ide\scratch\ag-kit` | NOT FOUND | non-authoritative — path does not exist in repo, not used as source |
| `.openclaw\skills` | NOT FOUND | non-authoritative — path does not exist in repo, not used as source |
| `C:\Users\GHC\.agents` | FOUND (contains `skills/` subdir) | non-authoritative — this is the global user-level `.agents` directory outside the repo, forbidden-path scan evidence confirms it is not used as a source; only repo-local `.agents/` is authoritative |
| `.codex\memories` | NOT FOUND | non-authoritative — path does not exist in repo, not used as source |

**Forbidden path scan result: clean.** No authoritative reliance on any forbidden path. All skill and role content was read exclusively from repo-local paths under `REPO_AGENT_ROOT=C:/Users/GHC/repos/OMEGA_QUANT/.agents/agent` and `REPO_SKILL_ROOT=C:/Users/GHC/repos/OMEGA_QUANT/.agents/skills`.

---

## Files Created

| File | Description | Lines |
|------|-------------|-------|
| `.agents/skills/quant-research/SKILL.md` | Factor/alpha research: IC/IR, turnover, capacity, neutralization, regime, transaction costs, GP alpha evolution | ~210 |
| `.agents/skills/vietnam-market-data/SKILL.md` | HOSE/HNX/UPCOM, VCI/vnstock, VND_FULL price scale, ticker lifecycle, delisting/survivorship, sector mapping, canonical schema | ~260 |
| `.agents/skills/backtesting-pit-safety/SKILL.md` | PIT/no look-ahead, survivorship bias, walk-forward, CPCV, corporate actions, slippage/fees | ~280 |
| `.agents/skills/ml-dl-rl/SKILL.md` | ML/DL/RL for time-series/portfolio: XGBoost/LightGBM/CatBoost, LSTM, autoencoder, PPO, leakage prevention, validation | ~300 |
| `.agents/skills/data-science-workflow/SKILL.md` | EDA, data quality, experiment tracking, statistical tests, reproducibility, MLflow | ~260 |

## Files Updated

| File | Change |
|------|--------|
| `.agents/agent/data-scientist.md` | Added skills: quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow |
| `.agents/agent/machine-learning-engineer.md` | Added skills: ml-dl-rl, backtesting-pit-safety, vietnam-market-data |
| `.agents/agent/data-engineer.md` | Added skills: vietnam-market-data, data-science-workflow |

---

## Validation Evidence

### YAML Frontmatter Validation

```
PASS: .agents/skills/quant-research/SKILL.md - all required fields present (4 fields)
       name=quant-research
PASS: .agents/skills/vietnam-market-data/SKILL.md - all required fields present (4 fields)
       name=vietnam-market-data
PASS: .agents/skills/backtesting-pit-safety/SKILL.md - all required fields present (4 fields)
       name=backtesting-pit-safety
PASS: .agents/skills/ml-dl-rl/SKILL.md - all required fields present (4 fields)
       name=ml-dl-rl
PASS: .agents/skills/data-science-workflow/SKILL.md - all required fields present (4 fields)
       name=data-science-workflow
PASS: .agents/agent/data-scientist.md - all required fields present (7 fields)
       name=data-scientist, skills includes new domain skills
PASS: .agents/agent/machine-learning-engineer.md - all required fields present (7 fields)
       name=machine-learning-engineer, skills includes new domain skills
PASS: .agents/agent/data-engineer.md - all required fields present (7 fields)
       name=data-engineer, skills includes new domain skills

ALL YAML FRONTMATTER VALIDATION PASSED
```

### SOD Gate Enforcer

```
python scripts/sod_gate_enforcer.py
[PASS] SOD GATE CHECK PASSED
   Verified 119 phases
   All L3 audit evidence present
   All role boundary checks validated
   All P0/P1/P2 hardening checks passed
   STRICT_REPO_LOCAL_SKILL_LOADING: repo-local skill sources validated
   STRICT_REPO_LOCAL_SKILL_LOADING: forbidden path scan clean
   STRICT_REPO_LOCAL_SKILL_LOADING: L2/audit report evidence verified
   51 pre-strict legacy gates (advisory, not blocking — grandfathered)
   All phases APPROVED
[PASS] SAFE TO PUSH
```

---

## Skill Content Summary

### 1. quant-research (`SKILL.md`)
- Alpha lifecycle and decision gates (IC > 0.02, IR > 0.5, turnover < 30%)
- IC/IR metrics: Rank IC (Spearman), Pearson IC, IC decay, IR
- Vietnam transaction cost model: 27bps round-trip (15bps commission + 10bps tax + 2bps slippage)
- Capacity analysis with VN-specific liquidity constraints (ADV concentration, foreign room, ceiling/floor traps)
- Neutralization hierarchy: market → sector (ICB L2) → style → full
- Regime-conditional evaluation across 4 regimes (Bull/Sideways/Volatile Sideways/Bear)
- Genetic programming alpha discovery (Sharpe fitness with turnover/depth penalties)
- Ensemble methods (XGBoost Ranker, voting, stacking, IC-weighted)
- SOD/PIT guardrails: no self-approval, Tier 3 audit required

### 2. vietnam-market-data (`SKILL.md`)
- Exchange structure: HOSE, HNX, UPCOM with trading sessions (ATO/ATC/Continuous)
- Market rules: 100-share board lots, price-dependent tick sizes, ±7% daily limits, T+2.5 settlement
- Data sources: vnstock + VCI provider, local parquet caching
- VND_FULL price scale contract: VCI returns prices in THOUSANDS, `ensure_vnd_scale()` mandatory
- Ticker lifecycle: IPO → listed → warning → suspended → delisted
- Corporate actions: stock splits, bonus shares, dividends, rights issues, mergers
- Survivorship bias prevention: PIT universe, delisted stocks included, terminal returns
- Sector mapping: ICB Level-2 from `data/sector_mapping_level2.csv`
- Canonical EOD OHLCV parquet schema with PIT timestamps (as_of, available_at)
- Trading calendar: `config/vn_holidays.json` (2015-2027)

### 3. backtesting-pit-safety (`SKILL.md`)
- PIT safety: no look-ahead, T-1 lag mandatory, `as_of <= available_at`
- Defense-in-depth: double T-1 shift in generator and evaluator
- PIT validation functions: `enforce_t_minus_1_lag()`, `validate_t_minus_1_lag()`, `PITViolationError`
- Survivorship-free protocol: full history, PIT universe, delisting returns
- Walk-forward validation: 252-day train, 63-day val, 21-day step, 3-day embargo
- CPCV: N=10 groups, k=2, C(10,2)=45 folds, bidirectional purge + embargo
- Corporate action handling: adjust at available_at, not retroactively
- Slippage/fee model: 27bps round-trip with VN-specific considerations
- BacktestEngine defaults: 1B VND capital, metrics (Sharpe, Sortino, max_drawdown, win_rate)
- Red flags: Sharpe > 3.0 = look-ahead, IC = 1.0 = label leakage

### 4. ml-dl-rl (`SKILL.md`)
- Model stack: XGBoost (Regressor + Ranker), LightGBM, CatBoost, LSTM, autoencoder, PPO
- Leakage prevention: 7 types of leakage with prevention strategies
- Tree-based models: DMatrix API, early stopping, gain importance, deterministic seeds
- LSTM: single-layer, lookback=60, hidden=64, deterministic algorithms
- PPO: Actor-Critic, Softmax long-only weights, Sharpe/Sortino reward with cost penalty
- RL reward pitfalls: cost omission, sparsity, hacking, regime ignorance
- Validation: chronological CV mandatory, walk-forward protocol, CPCV protocol
- Feature store: price/volume/cross-sectional/statistical/regime/alternative categories
- Hyperparameter optimization: Optuna TPE + MedianPruner, walk-forward inside each trial
- MLflow experiment tracking with reproducibility checklist

### 5. data-science-workflow (`SKILL.md`)
- EDA protocol: 8-step analysis with VN-specific checks
- Data quality: 6 dimensions (completeness, accuracy, timeliness, consistency, validity, uniqueness)
- Statistical tests: Spearman IC, t-test, ADF/KPSS, KS, Mann-Whitney, bootstrap CI
- Multiple testing correction: Bonferroni, BH-FDR, Deflated Sharpe Ratio
- Experiment tracking: MLflow integration with naming conventions
- Reproducibility protocol: seeds, deterministic execution, config, data versioning
- Analysis reporting template with structured sections
- Statistical pitfalls: p-hacking, data snooping, survivorship bias, non-stationarity

---

## Design Decisions

1. **OMEGA_QUANT-specific content**: Every skill references actual OMEGA_QUANT modules, file paths, configurations, and Vietnam market rules — not generic filler.
2. **PIT safety cross-cutting**: All 5 skills include SOD/PIT guardrail sections, since PIT safety is the #1 architectural principle.
3. **Verification checklists**: Every skill includes a verification checklist for pre-approval validation.
4. **Anti-patterns**: Every skill includes an anti-patterns table with specific don'ts and corrections.
5. **Agent skill wiring**: Added domain skills to data-scientist (role 14), machine-learning-engineer (role 16), and data-engineer (role 15) frontmatters — these are the roles that directly use these domain skills.
6. **No global/scratch edits**: No files written to non-authoritative forbidden paths (`.gemini/`, `.openclaw/`, `C:\Users\GHC\.agents` [non-authoritative], or `.codex\memories` [non-authoritative]). All changes are strictly repo-local under `.agents/`.

---

## SOD Boundary

- **Writer:** devops-engineer (role 11, tier 2, OpenCode)
- **Cannot self-approve:** Must submit to Tier 3 for audit
- **Submit to:** Code Reviewer (role 21), QA Engineer (role 17)
- **sod_boundary_checked:** true
- **writer_auditor_separated:** true

---

## repo_local_skill_sources

```yaml
repo_agent_root: C:/Users/GHC/repos/OMEGA_QUANT/.agents/agent
repo_skill_root: C:/Users/GHC/repos/OMEGA_QUANT/.agents/skills
agent_files_read:
  - .agents/agent/devops-engineer.md
  - .agents/agent/data-scientist.md
  - .agents/agent/machine-learning-engineer.md
  - .agents/agent/data-engineer.md
skill_files_read:
  - .agents/skills/deployment-procedures/SKILL.md
  - .agents/skills/server-management/SKILL.md
  - .agents/skills/clean-code/SKILL.md
  - .agents/skills/testing-patterns/SKILL.md
  - .agents/skills/systematic-debugging/SKILL.md
```

## forbidden_path_scan

```yaml
result: clean
paths_scanned:
  - ".gemini\\antigravity-ide\\scratch\\ag-kit: NOT FOUND, non-authoritative, not used as source"
  - ".openclaw\\skills: NOT FOUND, non-authoritative, not used as source"
  - "C:\\Users\\GHC\\.agents: FOUND (global), non-authoritative, forbidden-path scan evidence confirms not used as source"
  - ".codex\\memories: NOT FOUND, non-authoritative, not used as source"
authoritative_reliance: none
```
