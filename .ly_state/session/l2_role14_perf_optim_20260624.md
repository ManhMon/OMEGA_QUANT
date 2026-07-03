# L2 Report: HYBRID_REGIME_PERFORMANCE_OPTIM_20260624

## Role / Session
- role_id: 14
- role_name: data-scientist
- session_id: l2_role14_perf_optim_20260624
- gate: HYBRID_REGIME_PERFORMANCE_OPTIM_20260624
- scope: `scripts/backtest_hybrid_regime.py`

## Repo-Local Skill Source Evidence
- Role spec read: `.agents/agent/data-scientist.md`
- Skill read: `.agents/skills/python-patterns/SKILL.md`
- Skill read: `.agents/skills/clean-code/SKILL.md`
- Skill read: `.agents/skills/testing-patterns/SKILL.md`
- Skill read: `.agents/skills/systematic-debugging/SKILL.md`
- Skill read: `.agents/skills/performance-profiling/SKILL.md`
- Skill read: `.agents/skills/quant-research/SKILL.md`
- Skill read: `.agents/skills/vietnam-market-data/SKILL.md`
- Skill read: `.agents/skills/backtesting-pit-safety/SKILL.md`
- Skill read: `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source
- `.openclaw\skills` is non-authoritative and not used as source
- `C:\Users\GHC\.agents` is non-authoritative and not used as source
- `.codex\memories` is non-authoritative and not used as source

## Changes Implemented
- Baseline weekly rebalance added via `RebalanceFrequencyOverlay(rebalance_every_n_days=5)` at `scripts/backtest_hybrid_regime.py:442`
- Baseline TCost added via `TCostOverlay(min_trade_threshold_bps=35.0)` at `scripts/backtest_hybrid_regime.py:447`
- Hybrid weekly rebalance changed to `rebalance_every_n_days=5` at `scripts/backtest_hybrid_regime.py:485`
- Hybrid TCost threshold changed to `min_trade_threshold_bps=35.0` at `scripts/backtest_hybrid_regime.py:490`
- Hybrid GMM bear dampening changed to `latent_gmm_bear_dampening=0.15` at `scripts/backtest_hybrid_regime.py:462`
- Hybrid GMM bull boost changed to `latent_gmm_bull_boost=1.25` at `scripts/backtest_hybrid_regime.py:463`
- Hybrid cooldown extension changed to `gmm_reentry_cooldown_extension=2` at `scripts/backtest_hybrid_regime.py:483`
- Scenario comparison docstring updated to reflect weekly rebalance + TCost on Baseline and tuned Hybrid settings at `scripts/backtest_hybrid_regime.py:1721`

## PIT / Scope Notes
- Change limited to scenario overlay parameterization inside requested file.
- No feature-generation, label, chronology, or data-availability logic changed.
- Weekly rebalance + TCost knobs affect execution cadence / trade gating only.

## Verification
- Ran: `pytest`
- Result: suite not fully green after requested config change
- Failing tests: 3
- Failure 1: `tests/phase35/test_hybrid_regime_backtest_perf.py::TestTCostOverlayTuning::test_hybrid_tcost_threshold_relaxed`
  - Reason: test expects Hybrid `min_trade_threshold_bps < 30.0`; requested value now `35.0`
- Failure 2: `tests/phase35/test_hybrid_regime_backtest_perf.py::TestTCostOverlayTuning::test_baseline_unchanged`
  - Reason: test expects Baseline to have no `TCostOverlay`; requested change adds one
- Failure 3: `tests/phase35/test_hybrid_regime_dynamic_brake.py::TestGMMBullReentryFilter::test_hybrid_scenario_uses_relaxed_bear_market_gmm_params`
  - Reason: test expects `gmm_reentry_cooldown_extension == 1`; requested value now `2`

## Assessment
- Implementation matches requested parameter values.
- Current regression failures are stale test expectations vs requested new behavior, not runtime errors in the edited production file.
- No audit performed. L3 review still required.
