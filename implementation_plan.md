# Phase 20 Implementation Plan & Technical Specification

**Conformal (CQR) Backtest Integration, Sharpe Objective Verification, and
Dynamic-Sizing CPCV Sweeps**

Status: Draft for review · Date: 2026-07-02 · Branch base:
`fix/cost-reduction-isolation`

---

## 0. Scope & Guiding Constraints

Three deliverables, kept intentionally narrow. No new services, dashboards,
schedulers, or model architectures.

1. **Sharpe Objective Verification** — a *diagnostic* (not a rewrite) that
   proves how Sharpe and the risk-free assumption are actually computed in the
   CPCV comparison path, and asserts the metric is reliable and internally
   consistent.
2. **Conformal (CQR) backtest integration** — wire the existing
   `ConformalTrendPredictor` / price-ladder rungs into
   `scripts/backtest_hybrid_regime.py` as a new **dynamic sizing / gating
   overlay scenario** ("Conformal"), sitting alongside `Baseline` and
   `Hybrid`.
3. **Dynamic-sizing optimization sweeps on CPCV folds** — compare
   **Baseline vs Hybrid vs Conformal-gated** across the CPCV folds with a small,
   explicit sizing parameter grid.

### Non-negotiable constraints (from repo conventions)

- **PIT integrity is a hard gate.** The CQR model consumed inside a CPCV test
  fold must be fit *only* on data outside that test window (see §2.4). This is
  the single largest design risk and is handled explicitly, not implicitly.
- **Surgical changes.** Existing `Baseline`/`Hybrid` behavior must be
  byte-for-byte unchanged when the new scenario/flags are off. Every new code
  path is opt-in behind a flag or a default that preserves current output.
- **Determinism.** All new randomness is seeded (`random_state=42`, matching
  `ConformalTrendPredictor`).
- **Line length ≤ 79** for `src/`; `scripts/*` and `tests/*` are exempted from
  E501 via `setup.cfg`. New library code goes in `src/` and must obey 79.

### Ground-truth findings that shaped this plan (verified in code)

| Finding | Location |
|---|---|
| Risk-free rate is **implicitly zero** in every Sharpe path; no `rf` subtraction exists | `scripts/backtest_v2_cpcv.py:1209-1213`; `src/omega/quant/validation/dsr.py:148` |
| Per-fold Sharpe is **per-bar, NOT annualized**: `mean(rets)/std(rets, ddof=1)` | `scripts/backtest_v2_cpcv.py:1209-1213` |
| Annualization `sqrt(252)` is applied **only inside DSR**, `periods_per_year=252` hardcoded at both call sites | `dsr.py:149`; call sites `backtest_v2_cpcv.py:1346, 1351` |
| `sr_benchmark=0.0` is a **DSR null-hypothesis threshold**, *not* a per-return risk-free deduction — conflating them would be a bug | `dsr.py:110, 169-180` |
| Return series feeding Sharpe = **per-date portfolio returns, net of transaction cost, gross of rf** | `per_date_returns`, `backtest_v2_cpcv.py:545-816` (simple path `:584`, tail path `:816`) |
| CPCV default = `n_splits=10, n_test_splits=2` → **C(10,2) = 45 folds** | `src/omega/quant/validation/cpcv.py:171-194`; instantiated `backtest_v2_cpcv.py:940-945` |
| `backtest_v2_cpcv.py` runs `run_pipeline` **once** (`"A_baseline_alphas"`); there is **no in-process scenario comparison or sizing sweep** today | `backtest_v2_cpcv.py:2520-2527, 2649` |
| `build_scenario_overlays` returns a plain dict `{"Baseline":[...], "Hybrid":[...]}`; scenario names are **auto-discovered** by aggregation/reporting | `backtest_hybrid_regime.py:539-670, 1965-1967` |
| Overlay contract is `apply(self, weights, panel, state) -> pd.DataFrame` (date×symbol) | `backtest_hybrid_regime.py:90-135` |
| Regime labels reach an overlay via `state["gmm_regime_labels"]` (date-string keyed); liquidity proxy is `adv_vnd` (must be bucketized) | set `backtest_hybrid_regime.py:1922-1925`; `adv_vnd` built `:317-322` |
| `ConformalTrendPredictor.predict(X, groups, alpha)` needs `groups[["regime","liquidity_bucket"]]`; exposes `predict_multi`, `conditional_coverage`, `alphas` ladder | `src/omega/quant/models/conformal_predictor.py:72-107` |

---

## 1. Deliverable 1 — Sharpe Objective Verification Step

### 1.1 Problem statement

The CPCV comparison reports Sharpe-derived verdicts (`median_fold_sr`, DSR,
fold-level DSR). Before we trust those numbers to *rank* Baseline vs Hybrid vs
Conformal, we must verify — mechanically and with a regression test — exactly:

- what return series feeds Sharpe,
- whether a risk-free rate is subtracted (it is not; rf = 0),
- whether the number is annualized (per-fold: no; DSR: yes, ×√252),
- that `sr_benchmark` is a DSR threshold, not an rf deduction,
- that the two independent implementations
  (`backtest_v2_cpcv.py:1209-1213` inline vs `dsr.py:78-91`
  `annualized_sharpe`) agree on the same input.

### 1.2 Design: a self-contained diagnostic (no behavior change)

Add a **read-only diagnostic module + CLI** that (a) documents the assumptions
as executable assertions and (b) can be pointed at a real fold return series to
report the decomposition. It imports the *actual* production functions so it
cannot drift from them.

#### New file: `src/omega/quant/validation/sharpe_diagnostics.py`

Pure library, ≤ 79 cols, no side effects. Public surface:

```python
@dataclass
class SharpeAudit:
    n: int
    mean_return: float
    std_return: float          # ddof=1, matches production
    risk_free_rate: float      # the assumed rf (0.0 today)
    sharpe_per_bar: float      # mean/std, no annualization
    sharpe_annualized: float   # per_bar * sqrt(periods_per_year)
    periods_per_year: int
    excess_return_applied: bool  # True only if rf actually subtracted

def audit_sharpe(
    returns: Sequence[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> SharpeAudit: ...

def assert_matches_production(returns: Sequence[float]) -> None:
    """Compute Sharpe three ways and assert they agree:
    1. inline formula mirrored from backtest_v2_cpcv.py:1209-1213
    2. dsr.annualized_sharpe (src/omega/quant/validation/dsr.py:78-91)
    3. dsr.deflated_sharpe_ratio(...).sr / .sr_annualized
    Raises AssertionError on any mismatch beyond 1e-9.
    """
```

`audit_sharpe` implements the **canonical** definition once:
`excess = returns - risk_free_rate` (per-bar rf), `sharpe_per_bar =
mean(excess)/std(excess, ddof=1)`, `sharpe_annualized = sharpe_per_bar *
sqrt(periods_per_year)`. With `risk_free_rate=0.0` this must equal the
production per-fold Sharpe exactly — the assertion is the whole point.

`assert_matches_production` is the reliability proof: it cross-checks the three
code paths on the same vector, catching any future divergence.

#### New CLI: `scripts/verify_sharpe_objective.py`

Thin wrapper (scripts/ is E501-exempt). Modes:

- `--synthetic` (default): run `assert_matches_production` on seeded random
  returns of several lengths + edge cases (constant series → Sharpe 0; single
  element → 0), print the `SharpeAudit` table, exit non-zero on any failure.
- `--from-json <path>`: load a prior CPCV output
  (`.ly_state/session/phase3_3_v2.json`), extract the pooled/`per_fold_sharpe`
  series if present, and print the audit + the *stated vs recomputed* Sharpe so
  a human can confirm the reported number is reproducible.

Output includes an explicit banner stating the verified assumptions:

```
RISK-FREE RATE: 0.0 (implicit; no subtraction in production path)
RETURN SERIES : per-date portfolio return, net of tcost, gross of rf
ANNUALIZATION : per-fold Sharpe = per-bar (NOT annualized)
                DSR Sharpe      = per-bar * sqrt(252)
sr_benchmark  : DSR null-hypothesis threshold, NOT an rf deduction
```

### 1.3 Why a diagnostic, not a fix

Nothing here is broken — rf = 0 is a legitimate, common convention for
long-short daily strategies. The risk is *silent drift* and
*misinterpretation* (e.g. someone later "adds rf" to `sr_benchmark` thinking it
deducts a rate). The deliverable makes the convention explicit, testable, and
regression-guarded. If review decides rf should be non-zero, `audit_sharpe`
already parameterizes it and the same test becomes the acceptance test for that
change — but **changing rf is out of scope for Phase 20** unless explicitly
approved.

---

## 2. Deliverable 2 — Conformal (CQR) Backtest Integration

Goal: a new `"Conformal"` scenario in `scripts/backtest_hybrid_regime.py` that
uses CQR interval width and group coverage to **scale** (dynamic sizing) and/or
**gate** (filter) positions.

### 2.1 The overlay: `ConformalGateOverlay`

#### New file: `src/omega/quant/backtest/conformal_overlay.py`

Implements the repo's overlay contract (`apply(weights, panel, state) ->
pd.DataFrame`, modeled on `LongOnlyConcentratedOverlay`,
`backtest_hybrid_regime.py:90-135`).

```python
class ConformalGateOverlay(WeightOverlay):
    """Scale/gate per-(date,symbol) weights using CQR interval width
    and Mondrian group coverage from a pre-fit ConformalTrendPredictor.

    Sizing rule (confidence from interval width):
        width      = upper - lower                (per row, chosen alpha)
        conf       = clip(1 - width / width_ref, floor, 1.0)
        weight    *= conf
    Gating rule (coverage reliability):
        if group conditional coverage < min_coverage -> weight = 0
        if width > max_width_abs                      -> weight = 0
    """

    def __init__(
        self,
        predictor: ConformalTrendPredictor,
        feature_cols: list[str],
        alpha: float = 0.2,
        width_ref: float | None = None,   # None -> calibrated median width
        conf_floor: float = 0.25,
        min_coverage: float = 0.0,        # 0 => sizing-only, no gate
        max_width_abs: float | None = None,
        liquidity_col: str = "adv_vnd",
        liquidity_buckets: int = 3,
        mode: str = "size",               # "size" | "gate" | "size_gate"
    ) -> None: ...

    def apply(self, weights, panel, state) -> pd.DataFrame: ...
```

`apply` steps (deterministic, vectorized):

1. Build the `groups` frame the predictor needs:
   - `regime` from `state["gmm_regime_labels"]` (date-string keyed;
     lower-cased to match training labels `bull`/`bear`/…). Fallback to a
     neutral bucket if a date is missing.
   - `liquidity_bucket` by bucketizing `panel["adv_vnd"]` into
     `liquidity_buckets` quantile bins (`low`/`mid`/`high`), reproducing the
     training scheme in `train_conformal_ladder.py:27`.
2. Assemble `X` from `panel[feature_cols]` (must be the columns the predictor
   was trained on — carried in the model's registry metrics `feature_list`,
   see §2.4). Rows with missing features get `conf = conf_floor` (never
   silently dropped).
3. Call `predictor.predict(X, groups, alpha=self.alpha)` →
   `ConformalPrediction(lower, upper, point, groups)`.
4. Compute `width = upper - lower`; `width_ref` defaults to the calibrated
   median width captured at fit time (stored on the model or recomputed once).
5. **Sizing:** `conf = clip(1 - width/width_ref, conf_floor, 1.0)`; multiply
   the matching `(date, symbol)` cells of `weights`.
6. **Gating (if `mode != "size"`):** zero cells whose group coverage
   (`state["conformal_coverage"]`, precomputed once per fold, see §2.3) is
   below `min_coverage`, or whose `width > max_width_abs`.
7. Renormalize only if the preceding overlay guaranteed a normalized book
   (it does not by default — `ConformalGateOverlay` is a *multiplier*, placed
   after `LongOnlyConcentratedOverlay` normalization and after
   `RiskSizingOverlay`, so gross exposure legitimately shrinks when confidence
   is low). No forced renormalization — that is the intended sizing effect.

The overlay never mutates `panel`/`state`; it returns a new weights frame.

### 2.2 Price-ladder linkage (optional, reporting-only)

`build_price_ladder` (`src/omega/quant/models/price_ladder.py`) converts CQR
return bands into VN tick-aligned price rungs. In the backtest we do **not**
trade limit rungs (the engine is close-to-close), so ladder rungs are used for
**diagnostics only**: the overlay optionally records, per date, the number of
`degenerate` ladders and mean rung count into `state["conformal_diag"]` for the
profitability-diagnostics table. This keeps the ladder in the loop without
changing execution semantics. Guarded behind `--conformal-ladder-diag`
(default off).

### 2.3 Wiring into `scripts/backtest_hybrid_regime.py`

All hooks confirmed by structural analysis; scenario names auto-propagate to
aggregation/reporting (`aggregate_fold_results:1965-1967`,
`print_comparison_table`, `save_comparison_json`) with **no changes to those
functions**.

| # | Location | Change |
|---|---|---|
| W1 | `parse_args` (`:149-282`) | Add `--enable-conformal` (default False), `--conformal-model-path` (str), `--conformal-registry-key` (str, alt to path), `--conformal-alpha` (float, 0.2), `--conformal-mode` (`size`/`gate`/`size_gate`), `--conformal-min-coverage` (float, 0.0), `--conformal-conf-floor` (float, 0.25), `--conformal-refit-per-fold` (flag), `--conformal-ladder-diag` (flag). |
| W2 | `main`, after `feat_df` built (~`:2391`) | If `--enable-conformal` and not refit-per-fold: load predictor **once** via `joblib.load(path)` or `DatabaseRegistry` lookup by key (new load pattern — none exists in this file today). Read `feature_list` + `pit_embargo` from registry metrics. |
| W3 | `fold_specs` (`:2429-2446`) + `run_single_fold` signature (`:1759-1776`) | Thread `conformal_predictor`, `conformal_cfg` through, mirroring how `gmm_model`/`hmm_params` already flow. Pass-through only. |
| W4 | `run_single_fold`, before scenario loop (`~:1874`) | If enabled, precompute `conformal_coverage` for this fold's test window via `predictor.conditional_coverage(y_test, pred)` and stash into `initial_state["conformal_coverage"]` (added next to `gmm_regime_labels` at `:1922-1925`). If `--conformal-refit-per-fold`, fit the predictor here on the fold train slice (see §2.4 Strategy B). |
| W5 | `build_scenario_overlays` (`:539-670`) | Add param `conformal_overlay: WeightOverlay \| None = None`. When provided, add a third dict key `"Conformal"` = a copy of the `Hybrid` stack with `ConformalGateOverlay` inserted **after** `RiskSizingOverlay` and **before** `BoardLotRoundingOverlay`/`TCostOverlay` (so it scales the risk-sized book, then costs/rounding apply to the scaled book). |
| W6 | scenario loop (`:1902`) | No change — picks up `"Conformal"` automatically. |

When `--enable-conformal` is absent, `build_scenario_overlays` receives
`conformal_overlay=None`, the dict has exactly `{"Baseline","Hybrid"}`, and
output is identical to today.

### 2.4 PIT correctness (the critical risk)

A globally pre-fit CQR model peeking into a fold's test window reintroduces
look-ahead — the very thing the in-fold GMM/HMM/Ridge training exists to
prevent (`backtest_hybrid_regime.py:1010-1014`,
`:2378-2385`). Two supported strategies, selected by flag:

- **Strategy B — Per-fold refit (default).** Fit a fresh
  `ConformalTrendPredictor` inside `run_single_fold`/`train_fold_models` on the
  fold's train window (train = point/quantile models, calib = a purged tail
  slice), exactly like the GMM/HMM. This is the most robust option for audit-grade
  CPCV and matches CPCV semantics natively.
- **Strategy A — Out-of-sample-by-construction (`--fast-global-embargo`).** The predictor
  supplied via `--conformal-model-path` must be certified fit on a period
  strictly *before* the earliest CPCV test date. We enforce this at load time:
  read the model's registry `pit_embargo` (written by
  `train_conformal_ladder.py:37`) and **assert** `pit_embargo <=
  min(test_dates)` for every fold; abort with a clear error otherwise. Faster
  diagnostic but relies on registry metadata bookkeeping.

The plan **defaults to Strategy B** to eliminate any structural leakage risks from registry metadata, with Strategy A available for fast diagnostic sweeps.

---

## 3. Deliverable 3 — Dynamic-Sizing CPCV Sweeps (Baseline vs Hybrid vs Conformal-gated)

Goal: quantify whether conformal-driven dynamic sizing improves risk-adjusted
performance across the 45 CPCV folds, versus Baseline and Hybrid, over a small
explicit sizing grid.

### 3.1 Harness choice

`scripts/backtest_hybrid_regime.py` already runs multiple scenarios per fold and
aggregates cross-fold Sharpe/DD/return with dispersion
(`aggregate_fold_results:1962-2055`). It is the right harness — it already *is*
a CPCV Baseline-vs-Hybrid comparator. We extend it to also emit a **sizing
sweep** rather than building a parallel harness in `backtest_v2_cpcv.py` (which
runs a single pipeline and has no in-process comparison).

`backtest_v2_cpcv.py` remains the home of Deliverable 1's diagnostic target
(its Sharpe/DSR path) but is **not** modified for the sweep, keeping changes
surgical.

### 3.2 New driver: `scripts/sweep_dynamic_sizing.py`

Thin orchestration over the existing per-fold engine. It loops a small grid and,
per grid point, runs the three scenarios across all folds, then writes a tidy
comparison.

```
grid (default, overridable via CLI):
  conformal_alpha   ∈ {0.1, 0.2}
  conf_floor        ∈ {0.25, 0.5}
  mode              ∈ {size, size_gate}
scenarios per grid point: Baseline, Hybrid, Conformal
folds: whatever CPCV yields (default 45)
```

For each `(grid_point)`:
1. Build the `ConformalGateOverlay` with the grid params.
2. Invoke the existing fold execution (reusing `run_all_folds`, see §3.3) to
   get `all_fold_results`.
3. `aggregate_fold_results(...)` → per-scenario `mean_sharpe`, `std_sharpe`,
   `median_sharpe`, `mean_max_dd`, `worst_max_dd`, `mean_return`,
   `per_fold_sharpe`.
4. Record a row per `(grid_point, scenario)`.

Output: `results/phase20_sizing_sweep_{tag}.csv` (tidy: one row per
grid×scenario) **and** `results/phase20_sizing_sweep_{tag}.json` (full nested,
including `per_fold_sharpe` for paired tests). Baseline/Hybrid are invariant to
the conformal grid, so they are computed **once** and reused across grid points
(logged explicitly to avoid the misread that they were re-run).

### 3.3 Minimal refactor to enable reuse (surgical)

`main()` in `backtest_hybrid_regime.py` currently does data-load → feature-build
→ fold execution inline. To call the fold loop from the sweep without
duplicating ~120 lines, extract the **fold-execution body** (currently
`:2422-2546`) into:

```python
def run_all_folds(fold_specs, config, *, conformal_overlay=None) -> dict:
    """Execute every fold/scenario and return all_fold_results.
    Pure move of existing main() body; behavior identical."""
```

`main()` then calls `run_all_folds(...)` — a no-op refactor verified by
`aggregate`/`print`/`save` output being unchanged (regression test in §4).
`sweep_dynamic_sizing.py` imports `run_all_folds` and drives the grid. This is
the only structural edit to existing logic; everything else is additive.

### 3.4 Comparison statistics

Since folds are shared across scenarios, use **paired** comparison on
`per_fold_sharpe`:

- report `mean_sharpe ± std_sharpe` and `median_sharpe` per scenario per grid
  point (already produced by `aggregate_fold_results`);
- add a paired Sharpe delta `Conformal − Hybrid` and `Hybrid − Baseline` per
  fold, and a sign test / paired-t p-value (small helper in the sweep script;
  scipy is already a dependency per `dsr.py`);
- feed the pooled Conformal daily returns through
  `sharpe_diagnostics.audit_sharpe` (Deliverable 1) so the sweep's headline
  Sharpe is provably the same definition as the CPCV path.

The winning configuration is the grid point maximizing paired median Sharpe of
Conformal over Hybrid **without** worsening `worst_max_dd` beyond Hybrid's —
reported explicitly; no auto-promotion.

---

## 4. Verification Plan (new tests)

All under `tests/`, pytest, `pythonpath=src`. `test_` naming (matches
`tests/test_price_ladder.py`). Deterministic, seeded, fast.

### 4.1 Deliverable 1 — Sharpe diagnostic

`tests/test_sharpe_diagnostics.py`:

- `test_audit_zero_rf_matches_inline_formula` — random seeded returns;
  `audit_sharpe(r, rf=0).sharpe_per_bar == mean(r)/std(r, ddof=1)` to 1e-12.
- `test_annualization_factor` — `sharpe_annualized == sharpe_per_bar *
  sqrt(252)`.
- `test_rf_subtraction_changes_result` — non-zero rf shifts Sharpe in the
  expected direction and `excess_return_applied is True`.
- `test_assert_matches_production_agrees` — `assert_matches_production` passes
  on several lengths; the three paths (inline, `dsr.annualized_sharpe`,
  `dsr.deflated_sharpe_ratio`) agree.
- `test_benchmark_is_not_risk_free` — feeding `sr_benchmark` to
  `deflated_sharpe_ratio` changes the DSR *probability* but leaves `.sr` /
  `.sr_annualized` unchanged, proving it is a threshold not an rf deduction.
- `test_degenerate_series` — constant and single-element series → Sharpe 0, no
  exception.

### 4.2 Deliverable 2 — Conformal overlay

`tests/test_conformal_overlay.py`:

- `test_apply_preserves_shape_and_index` — output weights have identical
  index/columns to input.
- `test_low_confidence_shrinks_weights` — wide intervals (stub predictor
  returning large `upper-lower`) drive `conf → conf_floor`; weights scale down.
- `test_gate_zeroes_low_coverage` — with `mode="gate"` and a group whose
  `conformal_coverage < min_coverage`, those cells become exactly 0.
- `test_missing_regime_falls_back` — a date absent from `gmm_regime_labels`
  uses the neutral bucket, no KeyError.
- `test_liquidity_bucketization_matches_training` — `adv_vnd` → 3 quantile
  buckets labeled `low/mid/high`.
- `test_disabled_is_identity` — `mode="size"` with a stub predictor returning
  zero-width intervals leaves weights unchanged (conf = 1.0).
- One end-to-end case uses a small real `ConformalTrendPredictor` fit on
  synthetic data (pattern from `tests/test_price_ladder.py:13-22`).

### 4.3 Deliverable 2 — scenario wiring / PIT

`tests/test_hybrid_conformal_wiring.py`:

- `test_scenario_absent_when_disabled` — `build_scenario_overlays(...,
  conformal_overlay=None)` returns exactly `{"Baseline","Hybrid"}`.
- `test_scenario_present_when_enabled` — with an overlay, keys include
  `"Conformal"` and its stack contains a `ConformalGateOverlay` positioned
  after `RiskSizingOverlay`.
- `test_pit_embargo_assertion` — Strategy A rejects a model whose
  `pit_embargo` is *after* a fold's test start (raises with a clear message).

### 4.4 Deliverable 3 — sweep harness

`tests/test_sizing_sweep.py`:

- `test_run_all_folds_refactor_is_noop` — run the extracted `run_all_folds` on
  a tiny synthetic fold spec (2 folds, few symbols, few dates) and assert the
  aggregated result equals a captured golden for Baseline/Hybrid (guards the
  §3.3 refactor).
- `test_sweep_reuses_baseline_hybrid` — Baseline/Hybrid aggregates are
  identical across two grid points (proves they are computed once, not
  perturbed by conformal params).
- `test_sweep_output_schema` — CSV has one row per `(grid_point, scenario)`
  with the required columns; JSON contains `per_fold_sharpe` arrays.
- `test_paired_delta_sign` — synthetic case where Conformal dominates Hybrid
  per fold yields positive paired median delta and a significant sign test.

### 4.5 Regression guard (whole repo)

- `pytest tests/quant_test_cpcv.py tests/quant_test_dsr.py
  tests/test_price_ladder.py` must stay green (no change to CPCV/DSR/ladder
  behavior).
- A snapshot run of `backtest_hybrid_regime.py` on a tiny fixture with
  conformal disabled must produce the same `hybrid_regime_cpcv_comparison`
  JSON as before the change (byte-identical scenario keys/values for
  Baseline/Hybrid).

---

## 5. Build Order

Each step ends with a green verification gate before the next begins.

1. **Sharpe diagnostic library** — `src/omega/quant/validation/
   sharpe_diagnostics.py` → verify: `tests/test_sharpe_diagnostics.py` green.
2. **Sharpe diagnostic CLI** — `scripts/verify_sharpe_objective.py` →
   verify: `python scripts/verify_sharpe_objective.py --synthetic` exits 0 and
   prints the assumptions banner.
3. **Conformal overlay library** — `src/omega/quant/backtest/
   conformal_overlay.py` → verify: `tests/test_conformal_overlay.py` green.
4. **Scenario wiring + PIT guard** — edits W1–W6 in
   `backtest_hybrid_regime.py` + Strategy A embargo assertion → verify:
   `tests/test_hybrid_conformal_wiring.py` green; disabled-path snapshot
   unchanged.
5. **Fold-loop refactor** — extract `run_all_folds` (§3.3) → verify:
   `test_run_all_folds_refactor_is_noop` green; live smoke run unchanged.
6. **Sizing sweep driver** — `scripts/sweep_dynamic_sizing.py` → verify:
   `tests/test_sizing_sweep.py` green; produces
   `results/phase20_sizing_sweep_*.csv/json`.
7. **End-to-end sweep run** on a real (small) universe → verify: CSV/JSON
   populated for Baseline/Hybrid/Conformal across folds; headline Sharpe passes
   `audit_sharpe` cross-check.
8. **Full suite + lint** — `pytest -q`; `flake8 src/` clean (79-col) for new
   `src/` files.

Dependencies: 1→2, 3→4, 4→5→6→7. Steps 1–2 and 3 are parallelizable.

---

## 6. Definition of Done

**Deliverable 1 — Sharpe Objective Verification**
- [ ] `sharpe_diagnostics.py` computes Sharpe (per-bar & annualized) with an
      explicit `risk_free_rate` parameter defaulting to 0.0.
- [ ] `assert_matches_production` proves the inline CPCV formula,
      `dsr.annualized_sharpe`, and `dsr.deflated_sharpe_ratio` agree on shared
      input.
- [ ] CLI prints the verified assumptions banner (rf=0, return-series
      definition, annualization, `sr_benchmark` ≠ rf) and can audit a real
      CPCV output JSON.
- [ ] All `tests/test_sharpe_diagnostics.py` pass, including the
      benchmark-is-not-rf test.

**Deliverable 2 — Conformal integration**
- [ ] `ConformalGateOverlay` implements `apply(weights, panel, state)` and
      scales/gates via CQR width + group coverage.
- [ ] `backtest_hybrid_regime.py` exposes `--enable-conformal` (+ params);
      with it off, Baseline/Hybrid output is unchanged (snapshot proven).
- [ ] With it on, a `"Conformal"` scenario appears in the comparison table &
      JSON via existing auto-discovery (no edits to aggregate/print/save).
- [ ] PIT: Strategy B per-fold refit active by default; `--fast-global-embargo` (Strategy A) available; wiring/PIT tests pass.

**Deliverable 3 — Dynamic-sizing CPCV sweep**
- [ ] `run_all_folds` extracted with a proven no-op refactor.
- [ ] `sweep_dynamic_sizing.py` produces per-`(grid_point, scenario)`
      Baseline/Hybrid/Conformal metrics across CPCV folds.
- [ ] Output CSV + JSON include per-fold Sharpe and paired
      Conformal−Hybrid / Hybrid−Baseline deltas with a significance figure.
- [ ] Baseline/Hybrid computed once and reused across the conformal grid
      (proven by test), and the sweep's headline Sharpe passes the Deliverable
      1 cross-check.

**Global**
- [ ] `pytest -q` green; `flake8 src/` clean (79 cols) for new library files.
- [ ] No changes to CPCV (`cpcv.py`), DSR (`dsr.py`), or the price-ladder
      semantics; their existing tests remain green.
- [ ] Every changed line traces to one of the three deliverables (surgical).

---

## 7. Open Questions for Review (resolve before Step 4)

1. **rf policy:** confirm rf = 0 is intended for Phase 20 (plan assumes yes;
   changing it is out of scope but `audit_sharpe` is ready if not).
2. **PIT strategy default:** Strategy B (per-fold refit) vs Strategy A (global model + embargo). Resolved: default to B based on Codex recommendation.
3. **Overlay placement:** confirm `ConformalGateOverlay` after
   `RiskSizingOverlay` (scales the risk-sized book) is the desired semantic
   vs. gating the pre-sizing selection.
4. **Grid size:** default grid is 2×2×2 = 8 points × 3 scenarios × 45 folds.
   Baseline/Hybrid reuse keeps cost near 8×conformal + 1×(baseline+hybrid).
   Confirm this budget or trim the grid.
