# L2 Report - role16 - gp_hybrid_features_fix - 2026-07-24

## Summary

- Scope: `src/omega/quant/evolution/hybrid_alpha_miner.py`
- Task: fix LLM mock feature validation input in `_generate_llm()` so compile-check does not reject formulas using non-first-five features.
- Result: implemented.

## Repo-Local Role/Skill Files Read

- `./.agents/agent/machine-learning-engineer.md`
- `./.agents/skills/python-patterns/SKILL.md`
- `./.agents/skills/clean-code/SKILL.md`
- `./.agents/skills/testing-patterns/SKILL.md`
- `./.agents/skills/performance-profiling/SKILL.md`
- `./.agents/skills/systematic-debugging/SKILL.md`
- `./.agents/skills/ml-dl-rl/SKILL.md`
- `./.agents/skills/backtesting-pit-safety/SKILL.md`
- `./.agents/skills/vietnam-market-data/SKILL.md`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: not used as authoritative source
- `.openclaw\skills`: not used as authoritative source
- `C:\Users\GHC\.agents`: not used as authoritative source
- `.codex\memories`: not used as authoritative source

## Root Cause

- `_generate_llm()` built mock `features` with `self.feature_names[:5]` only.
- `LLMSymbolicSynthesizer.synthesize()` validates parsed formulas against the provided feature dictionary.
- Any LLM formula using a valid terminal outside the first five feature names was rejected during compile/validation.

## Change Made

- Replaced sliced mock feature construction with a full dictionary over all `self.feature_names`.
- Ensured these baseline terminals always exist in the mock dictionary:
  - `close`
  - `open`
  - `high`
  - `low`
  - `volume`
  - `ret_1d`
  - `ret_5d`
  - `ret_20d`
- Left existing fallback behavior intact.

## Diff Intent

Before:

```python
features = {name: np.random.randn(50) for name in self.feature_names[:5]}
```

After:

```python
features = {name: np.random.randn(50) for name in self.feature_names}
for terminal in ("close", "open", "high", "low", "volume", "ret_1d", "ret_5d", "ret_20d"):
    features.setdefault(terminal, np.random.randn(50))
```

## Verification

### Targeted Runtime Check

Command run:

```powershell
$env:PYTHONPATH='src'; python -c "from omega.quant.evolution.hybrid_alpha_miner import HybridCandidateGenerator, HybridAlphaMinerConfig; import omega.quant.evolution.llm_symbolic_synthesizer as mod; captured = {}; original = mod.LLMSymbolicSynthesizer.synthesize; mod.LLMSymbolicSynthesizer.synthesize = lambda self, features: (captured.setdefault('keys', set(features.keys())) or [], {}); gen = HybridCandidateGenerator(HybridAlphaMinerConfig(llm_provider='mock'), ['alpha_x', 'beta_y', 'close']); gen._generate_llm(3); mod.LLMSymbolicSynthesizer.synthesize = original; expected = {'alpha_x', 'beta_y', 'close', 'open', 'high', 'low', 'volume', 'ret_1d', 'ret_5d', 'ret_20d'}; missing = expected - captured['keys']; assert not missing, f'Missing terminals: {sorted(missing)}'; print('OK', len(captured['keys']))"
```

Observed result:

```text
OK 10
```

Interpretation:

- `_generate_llm()` now passes all provided feature names through to `synthesize()`.
- Required base terminals are present even when absent from `self.feature_names`.

## Required Master Script Check

- Searched repo for `checklist.py`: not found.
- Searched repo for `verify_all.py`: not found.
- Could not run these role-mandated scripts because the files are absent in the repository.

## Lessons Applied

- Lesson 1: Validation features dictionary must contain all potential terminals.
- Lesson 2: Construct full mock features dictionary in `_generate_llm`.

## Files Changed

- `src/omega/quant/evolution/hybrid_alpha_miner.py`
