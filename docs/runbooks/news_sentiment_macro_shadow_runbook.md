# News sentiment, graph, macro and PEAD: shadow runbook

## Authority and limits

P6 is opt-in, offline research. No broker submission, live activation, gate approval or verified historical provenance. `applied=false`, `live_lambda=0` always. Caller features remain `caller_supplied_unverified`; neither a timestamp nor lineage identifier establishes historical eligibility. Independent L3 review and separately authorized source evidence remain required.

Optional streams: `direct_news`, graph `spillover`, earnings `pead`. Missing values stay unavailable, not confident neutral. Macro is a separately supplied exposure multiplier, not another sentiment vote. A run lacking a stream must name the exclusion; it cannot claim complete four-stream historical coverage. No clean historical overlap or portfolio execution-return evidence is supplied with this implementation. Net OOS alpha, capacity, Sharpe and statistical acceptance are not established.

## Evaluation contract

Use `omega.quant.strategy.unified_alpha_evaluator` in process; it performs no file I/O or network requests.

1. Freeze the point-in-time universe, input vintages, exchange calendar and trial registry before inspecting held-out returns. Keep the registry and input digest with the research artifact. Register negative results and every attempted variant; do not select a holdout after inspecting performance.
2. Registry `schema_version=p6/trials-v1`: ordered timezone-aware `session_calendar`, explicit `embargo_sessions`, label `evaluation_time`, half-open ordinal `final_holdout=[start,end]`, and `trials`. Each trial binds `trial_id`, `ablation`, generated `score_col`, `return_col`, `label_horizon_sessions`, `validation_windows`, the same `final_holdout` and frozen stream `weights`. Registered score columns must not preexist in the input; the evaluator computes them from the frozen blend. All windows refer to the same fixed calendar; later data insertion must not move them.
3. The panel binds symbol identity, session ordinal, timezone-aware decision/label end/label availability, event group and registered score/return columns. Supply actual delayed-execution label intervals, not nominal three-day labels for 60-session PEAD. `label_horizon_sessions` is the maximum decision-to-exit session distance, including entry delay; a three-session holding period after T+1 entry therefore registers at least four sessions. Actual entry and exit must fall inside active exchange hours; 15:30 ICT is an availability clock, not an execution session. Reject unsupported session times, duplicate identities, nonfinite values and schema drift. Label availability must be recorded separately from release time.
4. `evaluate_walk_forward(panel, trial_registry=registry)` uses strictly earlier training, interval purging, connected-event exclusions and horizon-sized session embargo. Identity transforms and frozen scores only: no full-sample normalization, fitted ensemble or automatic model selection. Learned transforms require separately implemented training-only fitting and readiness evidence.
5. Preserve quant-only scores as immutable benchmark. Preregister quant-only, direct-news, graph, PEAD, combined and macro-policy ablations as applicable; unavailable variants remain explicitly excluded. CPCV with future training blocks is not chronological deployment evidence.
6. Inspect per-fold/session rank IC, valid sample counts, coverage, constant-input flags, uncertainty and trial counts. Full entry-to-exit labels must remain inside each scoring window. HAC and deterministic block-bootstrap intervals are withheld when observed IC sessions contain calendar gaps; no compression of missing sessions into adjacent observations. Familywise adjustment counts every registered validation-window and holdout test. Never subtract transaction costs from IC. Insufficient observations remain insufficient evidence; screening thresholds do not approve deployment.

## Blend and execution-cost contracts

`blend_features(quant, features, weights=..., decision_time=..., macro_multiplier=..., hard_veto=...)` requires identical unique ordered symbol indices. Feature columns: `direct_news`, `spillover`, `pead`, `feature_as_of`, `feature_available_at`, `lineage`. Require `feature_as_of <= feature_available_at <= decision_time`; pipeline ingress additionally requires prior-session observation dates. Preserve null quant: optional streams cannot manufacture a qualified quant signal.

Frozen nonnegative stream weights total at most 0.1. Missing weights are not redistributed to surviving streams. Inspect validity masks and `score_before_macro`. The pipeline optimizes `score_before_macro`, then interpolates from baseline weights toward the candidate by `sum(weights)`; aggregate pre-macro portfolio influence cannot exceed 0.1. Zero stream weights reuse baseline weights without a second optimizer call. Macro multiplier is bounded to [0,1], applied after scoring; pipeline applies it after portfolio optimization, before local executable order simulation. A zero multiplier removes target exposure, not existing settlement constraints. Existing risk halt, asset, sector, drawdown, lifecycle and calendar vetoes dominate.

`annotate_execution_costs` accepts unique executed fill rows with `fill_id`, `side`, integer `quantity`, `price_vnd`, `nav_vnd`; units are VND_FULL, shares, VND_FULL. Never infer a thousand-dong scale from price magnitude. Large valid notionals above 1e12 VND are permitted within field-specific bounds: quantity <= 1e12 shares, price <= 1e9 VND, reference NAV <= 1e18 VND; notional may reach 1e21 VND without premature Decimal rounding. Costs use actual filled notional, not target orders:

- BUY: 15 bps commission + 2 bps slippage = **17 bps**.
- SELL: 15 bps commission + 10 bps tax + 2 bps slippage = **27 bps**.
- Equal-notional completed BUY/SELL: **44 bps** of one-leg notional, not 44 bps per leg.
- One-way turnover: `0.5 * sum(executed_notional / reference_nav)`. Report buy/sell cash flows separately. It is not proof of a self-financing rebalance when cash changes.

P6 ledger annotations compare a research cost scenario against W7 simulated fills using the pre-trade W7 NAV as each fill's turnover denominator. `execution_costs.fills` preserves `fill_id`, side, executed quantity and VND price; empty execution lists remain empty. They are not broker-confirmed executions, are not booked into W7 cash and must not be added again to W7 fees. Decimal arithmetic rounds each fill's fee once to whole VND using ROUND_HALF_UP; rounding can make tiny fills differ from an unrounded bps formula. Preserve the existing baseline cash, fees and digest. Partial/unfilled orders incur only executed-fill costs. Corrections require a new independently traceable execution record; duplicate fill identities are rejected.

## Shadow opt-in

Keep existing `w7/v1` outer request and `B3` arm. Replace only `advisory` with this exact schema; every feature row follows the outer ordered universe:

```json
{
  "schema_version": "p6/v1",
  "features": [
    {
      "symbol": "VCB",
      "direct_news": 0.2,
      "spillover": null,
      "pead": null,
      "feature_as_of": "2026-09-29T07:00:00Z",
      "feature_available_at": "2026-09-29T08:00:00Z",
      "lineage": "research-v1"
    }
  ],
  "weights": {"direct_news": 0.05, "spillover": 0.02, "pead": 0.03},
  "macro_multiplier": 0.8
}
```

This is an advisory fragment, not a runnable complete request. Mandatory market/risk data, ordered universe, covariance, calendar digest and request identifiers remain required. A one-symbol example may violate portfolio limits; do not weaken them. Legacy advisory schema remains supported unchanged.

Use an already-created, verified repository-local W7 sandbox directory. Input must be a bounded regular strict-UTF-8 JSON file, no BOM, duplicate keys, nonfinite values, symlinks, path escape or credentials. State requires a dedicated SQLite `.db` file. Example paths below assume that directory and complete input already exist:

```powershell
$env:PYTHONPATH = "src"
python -m omega.runner --mode shadow --input .ly_state/session/jev_deep_integration_20260926/W7/p6_input.json --state .ly_state/session/jev_deep_integration_20260926/W7/p6_shadow.db
```

P6 permits `shadow` and `replay` only; `disabled` preserves the baseline, `paper` cannot apply P6. The runner defaults disabled. No new command-line flags or runner changes are needed. Replay the identical request against the same state to verify the same decision digest without duplicate fills.

## Monitoring and failure precedence

Record input/calendar/registry revisions, baseline and decision digests, per-stream validity, missing-source exclusions, caller provenance, macro exposure, actual simulated fills, separate cost scenario and outcome/reason. Never log raw credentials or arbitrary URLs. The bounded ingress, strict JSON, transaction, owner lock, deadline and memory controls remain those of W7.

Mandatory market/risk corruption blocks the cycle. A malformed optional P6 advisory, unsupported mode, excessive blend influence, solver/risk failure or resource deadline falls back to the independently computed baseline; inspect `outcome=fallback` and `reason=advisory_error` or `deadline`. A fallback is not a successful P6 evaluation even if the CLI exits zero for a valid committed baseline. Reject `applied=true`, nonzero live lambda, unexplained accounting residual, changing replay digest or unverified history claims.

Operators and risk owners must define source-age thresholds, incident severity and calendar revisions before a shadow campaign; none are inferred here. Stale features cannot be certified fresh merely because their availability precedes cutoff. At least 20 eligible shadow sessions is an operational proposal, not statistical sufficiency or approval.

## Stop, rollback and recovery

1. On unexplained divergence, provenance failure, unexpected order capability or accounting error, stop P6 use. Preserve request, registry, state and digests; do not delete or rewrite evidence.
2. Run the accepted baseline with `--mode disabled` using its accepted configuration and a dedicated baseline state. Do not splice P6 generations into an older state or bypass existing vetoes.
3. Rehearse rollback with a malformed optional advisory and injected publication failure. Verify baseline equality, no partial generation, no duplicate fills and unchanged input objects. W7 SQLite owns atomic publication; P6 adds no checkpoint or lock implementation.
4. Recover only the verified last committed state matching run, universe, calendar, input and policy revisions. Replay unchanged decisions before advancing monotonically. Do not overwrite a conflicting decision; investigate it.
5. Resume shadow only after implementation defects are fixed and independently reviewed. Live activation always requires separate authorization and gate enforcement.

## Local verification

Safe Windows pytest invocation (collection first, then focused tests):

```powershell
python -m pytest tests/test_news_sentiment_macro_shadow.py tests/test_jev_e2e_production_readiness.py tests/test_validation_consolidation.py --collect-only -o addopts="" --capture=sys -p no:terminal --junitxml=.ly_state/session/l4_role14_p6_shadow_rem3_20261021_collect.xml
python -m pytest tests/test_news_sentiment_macro_shadow.py tests/test_jev_e2e_production_readiness.py tests/test_validation_consolidation.py -o addopts="" --capture=sys -p no:terminal --junitxml=.ly_state/session/l4_role14_p6_shadow_rem3_20261021_test.xml
```

The L4 report records actual results, related-suite evidence, standing network/config regressions, advisor receipts, exclusions and unresolved limitations. Neither this runbook nor advisor advice constitutes an independent L3 decision.

### W7 historical binding and REM3 reconciliation

W7 packet `input_manifest.json` seals six candidate files by SHA-256. Their exact bytes are present at commit `a154fb8cfba706f7973fd56a97f5caf6edc7398a`; verification reads raw Git blobs, not later P6 working-tree candidates. The original manifest, evidence files, and recorded hashes remain unchanged. This proves historical candidate integrity only; the REM2 report separately binds current scoped files. Missing Git, unavailable revision, timeout, or changed blob bytes must fail. Default pytest assertion rewriting remains enabled; explicit verifier errors preserve failure messages with `-p no:terminal`.

REM3 uses the explicitly authorized recorded W7 baseline `02bb5a7b41a5bbf4e9ff9cc1e3f61dea667044d7`. Exact predecessor SHA-256 remains the first acceptance path. On mismatch, only `predecessor_metadata` at `.ly_state/session/phase_gates.json` with `binding_mode=historical_snapshot` may use the baseline fallback. Its raw Git bytes must match `baseline_recorded_sha256=92f60946585659af2f10b29e0ea1ed9166c3fe975ae80204034d08f2aa2bd978`. An absent `history_anchor` selects that pinned commit; an explicit anchor must match it. Require all recorded W0–W6 gate IDs exactly once in baseline and current metadata, with type-sensitive unchanged records. Unrelated later gate updates are permitted; missing, rewritten, or duplicated predecessor records fail. Strict UTF-8, duplicate-key, non-finite, object-shape, and size checks apply to fallback metadata. No manifest, recorded digest, or gate file is changed.

This fallback proves the recorded baseline and preserved predecessor records, not recovery of the unavailable `e30ea4b16021b1c2c4a1f710e6ec292b66f1d523b65e00931b3c7bf4a9ae64b1` dispatch snapshot, missing W4/W6 canonical packet roots, or production eligibility. Git failures, digest mismatch, unsupported anchor, and unrelated evidence tampering remain fail-closed. Readiness means ready for independent L3 review only; no gate approval or live authorization.

### Zero-token and adversarial evidence

P6 uses supplied features and deterministic in-process evaluation; it does not request model inference. The positive proposal/replay test rejects socket connection attempts and `_classification` calls. These tripwires establish no network/classification calls on that exercised path, not global provider billing evidence. MCP advisory consultations are separate from the zero-token P6 runtime claim.

REM2 adds immutable-reader fault injection, working-tree rewrite/deletion isolation, predecessor tamper/missing checks, and pre-read path/current-audit rejection. Existing coverage retains strict UTF-8/BOM/CRLF, inclusive cutoff and 15:30 ICT labels, NaN/Inf/overflow, VND costs, rollback, and worker isolation. The report maps all 24 adversarial dimensions with explicit exclusions; unmodified routing/provider infrastructure is not blanket-certified.
