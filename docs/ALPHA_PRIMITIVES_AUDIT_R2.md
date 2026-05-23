# Alpha Primitives Audit R2

## Scope
- `OMEGA_QUANT/packages/quant/src/omega/quant/alpha_primitives.py`
- `OMEGA_QUANT/tests/phase3/test_alpha_primitives.py`

## Checklist
1. `calculate_ic` handles <2 valid pairs safely: Yes (returns `np.nan`).
2. `max_drawdown` anchored with initial capital 1.0: Yes (prepends `1.0` before `cumprod`).
3. New tests present and passing: Yes (`test_calculate_ic_single_pair`, `test_calculate_max_drawdown_first_negative`).
4. Vectorized: Yes.
5. No PIT leakage: Yes.

## Verdict
[APPROVED]