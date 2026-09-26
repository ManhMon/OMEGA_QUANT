# Master Implementation Plan: JEV Deep Integration

Date: 2026-09-26

Planning gate: `GATE_MASTER_PLAN_JEV_DEEP_INTEGRATION_20260926`

Role: 26, planning-architect, Codex L3 Planning. NON-AUDIT. NON-GATE-APPROVAL.

Status: Planning deliverable for L1 review and subsequent independent implementation dispatch. This document neither approves its planning gate nor certifies any implementation, test result, investment benefit, or production readiness.

Repository: `C:\Users\GHC\repos\OMEGA_QUANT`

Planning model assignment: lead `cx/gpt-6-astra`; delegated research workers `gpt-6-luna`. Model assignments are task requirements, not evidence of provider-side model identity. Three read-only workers examined the consolidated research, deeper research, and prior-plan governance. They made no implementation changes and issued no audit verdicts.

## 1. Objective, scope, and controlling decisions

Integrate JEV as a bounded information sensor within the existing quantitative pipeline. Preserve deterministic portfolio construction, risk enforcement, reproducible evidence, and a valid quantitative baseline. Determine experimentally whether each extension improves net utility compared with both the baseline and a simpler deterministic rule.

JEV must never issue executable BUY/SELL/HOLD instructions, invent order prices or sizes, override risk controls, approve its own evidence, or close a governance gate. Typed labels establish a data contract; they establish neither calibrated probability nor investment value.

This planning task writes only this document. Production code, test code, test execution, deployment, audit verdicts, and gate mutations are outside this task. The requested comprehensive document and explicit destination take precedence over the plan-writing skill's generic one-page/root-directory suggestions.

### 1.1 Source register and precedence

| ID | Source | Use and evidentiary status |
|---|---|---|
| R1 | `C:\Users\GHC\.gemini\antigravity-ide\brain\d438d845-f147-4915-bf60-7dd9566e3662\jev_deep_integration_research.md` | Original module roadmap, proposed labels, batch names and numerical defaults. Performance estimates are hypotheses, not measured results. |
| R2 | `C:\Users\GHC\.gemini\antigravity-ide\brain\d438d845-f147-4915-bf60-7dd9566e3662\jev_deeper_research.md` | Calibrated research constraints, six incremental hypotheses, authority limits, prospective evidence and rejection rules. Sections 3-7 constrain R1 where they conflict. |
| P1 | `.ly_state/session/master_plan_jev_hybrid_integration_20260925.md` | Existing integration lineage, four prior gates, shared contracts and canonical JEV 16D matrix, particularly lines 97-112. A plan is not proof that those gates passed. |
| G1 | `.agents/agent/planning-architect.md` | Role 26 planning-only boundary; L1 review before implementation dispatch. |
| G2 | `.agents/AGENTS.md`, `.agents/ARCHITECTURE.md` | Role separation, independent review, report validation and authorized gate closure. |
| S1 | `.agents/skills/plan-writing/SKILL.md` | Dependency ordering, actionable deliverables and verification criteria. |
| C1 | `src/omega/core/llm_config.py`, `src/omega/quant/ensemble_optimizer.py`, `src/omega/quant/portfolio/regime_overlay.py` | Read-only inspection confirms existing JEV seams. Presence is not correctness or gate approval. |
| C2 | `src/omega/quant/regime/hmm_model.py`, `tests/test_jev_regime_alpha_weighting.py`, `tests/test_sod_jev_model_routing.py` | Existing regime model and regression surfaces; tests were inspected, not run. |

### 1.2 Conflict-resolution ledger

| Topic | Original proposal | Binding treatment in this plan |
|---|---|---|
| Forensic veto | Absolute exclusion for non-clean audit or suspicious asset transfer | Research/shadow recommendation only. Existing deterministic vetoes remain binding. New JEV veto needs a separate future authority decision supported by prospective evidence. |
| Regime blend | 60% JEV / 40% HMM | Existing candidate baseline, not calibrated confidence or an approved optimum. Compare with pure quant and deterministic rules. |
| Emergency exposure | Exposure 1.0 to 0.3; stop-loss 7% to 5% | Research examples only. No automatic modification of risk policy from JEV labels. |
| Corporate action | Multiply ScoreVector by 0.7 | Candidate treatment for an experiment, disabled by default; quantify double counting and net effect before consideration. |
| Expected gains | Return, Sharpe and slippage improvement estimates | No benefit booked into acceptance or business case. Require measured, uncertainty-qualified results. |
| Cached historical output | Described as PIT-safe | Data availability and model-knowledge leakage are separate. A cache created today does not prove historical model PIT safety. |
| Confidence / numeric score | BL confidence and forensic score 0-100 | No fabricated probabilities. Keep numeric adapters disabled unless scale, provenance and out-of-sample calibration are established. |
| Module count | Roadmap heading says 11 subsystems | Explicit A1-A3, B1-B6 and C1 enumerate ten. Track the separately mentioned Alpha Judge as advisory scope requiring a contract; do not invent an eleventh implemented subsystem. |
| Production status | R1 describes phases 1-4 as integrated | Verify exact commit, receipts, tests and gate state before relying on them. Planning language is not runtime evidence. |

## 2. Current baseline and integration boundaries

Preserve lineage to `GATE_JEV_MACRO_MICRO_HYBRID_20260925`, `GATE_JEV_MACRO_NEWS_SENTIMENT_20260925`, `GATE_JEV_COPILOT_SMART_ROUTER_20260925`, and `GATE_JEV_SOD_MULTI_AGENT_GOVERNANCE_20260925`. Do not reopen, close or rename those gates from this planning artifact. L1 must resolve their actual state before dispatching dependent work.

The existing `classify_jev` helper supplies label allowlists, a SQLite cache, availability checks and a UTC-day fingerprint. `EnsembleOptimizer.apply_jev_weight_tilt` already selects momentum/reversion/balanced/defensive profiles, uses 1.25/0.75 multipliers and projects weights onto a bounded simplex. The regime overlay already exposes `JEV_ARBITRATED` and a 0.6/0.4 exposure blend. Extend these seams only after regression baselining; do not create a parallel provider client or duplicate portfolio engine.

There is a material regime mismatch: the overlay uses BULL/BEAR/SIDEWAYS while the separate regime model supports four bull/bear and calm/volatile states. A four-state label cannot be silently mapped into a three-state enum or treated as a posterior. Define and validate the mapping, missing-state handling and exposure semantics before changing consumers. Existing model-name substring grouping for alpha families also requires an explicit validated mapping before introducing new profile names.

Intended sequence:

1. Freeze eligible source revisions and the PIT universe at the decision cutoff.
2. Run deterministic validation, deduplication and selective-invocation policy.
3. Read a compatible cached label or, only in an allowed live mode, request a bounded JEV classification.
4. Validate the response envelope and map approved labels to fixed quantitative profiles.
5. Construct the proposal with the existing optimizer; measure aggregate change from the baseline.
6. Reapply every portfolio and execution constraint. Infeasible JEV proposals contribute no adjustment.
7. Record the baseline, proposal, final deterministic decision, costs and reasons. Execution consumes only authorized quantitative output.

No separate agent framework, new model, vector database or dependency is justified by this plan. Reuse existing routing, caching, numerical and execution facilities.

## 3. Contracts, schemas, and evidence storage

These are proposed implementation contracts, not claims that the current helper already accepts the fields. First implement versioned adapters and prove compatibility with current callers. Choose concrete storage migrations in the implementation packet after inspecting the existing SQLite schema; do not create a second cache merely to match this document.

### 3.1 Common classification envelope

| Field group | Required contract |
|---|---|
| Identity | `decision_id`, `domain`, `schema_version`, `gate_id`, `mode`, `entity_ids`, `request_fingerprint`; bounded nonempty identifiers and registered domains only. |
| Time | `event_time`, `available_at`, `decision_cutoff`, `decision_time`, `generated_at`, `expires_at`; timezone-aware timestamps normalized to UTC; retain exchange calendar identity. |
| Source | Source identifier, immutable revision identifier, content hash, ingestion timestamp and evidence references. Hash sanitized canonical facts, never credentials. |
| Reproducibility | Provider and model version where available, prompt version/hash, policy version, feature/profile version, input dataset manifest and code revision. If provider revision is unavailable, record that limitation explicitly. |
| Response | `selected` containing exactly the domain's finite enum fields; no unregistered fields, arbitrary code, executable text or implicit numeric confidence. |
| Outcome | `status` in `accepted`, `skipped`, `fallback`, `rejected`, `cancelled`; reason code; cache hit; attempt count; latency; measured or explicitly estimated cost. No success status for failed persistence or cancellation. |
| Authority | `research_only`, `shadow_only`, or separately authorized `bounded_profile`; record the policy authorizing any applied adjustment. Labels cannot elevate this authority. |

Recommended reason-code vocabulary: `disabled`, `no_new_information`, `rule_sufficient`, `benefit_unproven`, `budget_exhausted`, `timeout`, `rate_limited`, `auth_failure`, `schema_invalid`, `source_invalid`, `future_information`, `expired`, `cache_miss`, `version_mismatch`, `unresolved_conflict`, `infeasible_proposal`, `cancelled`, `storage_failure`. Version the vocabulary with the envelope. Store safe diagnostics without raw prompts, secrets or unrestricted provider bodies.

For facts with multiple source records, every record must meet the availability condition. Do not use a maximum or average timestamp that hides future records. Define `as_of` once per adapter as either observation time or decision cutoff; never infer its meaning from the field name.

### 3.2 Domain registry

| Domain | Proposed finite output contract | Consumer and permitted effect |
|---|---|---|
| Regime arbitration | Existing BULL/BEAR/SIDEWAYS contract retained until a versioned adapter is validated. R1 extension: four bull/bear x calm/volatile states; liquidity `expansionary`, `neutral`, `tightening_stress`, `liquidity_crunch`; valuation `deep_value_trough`, `fair_value`, `bubble_euphoria`; trend `strong_uptrend`, `exhaustion_reversal`, `range_compression`, `panic_selloff`. | Existing regime overlay; fixed validated exposure profile only. Exact four-state serialization must match the actual model enum, not guessed strings. |
| Alpha profile | `momentum_heavy`, `mean_reversion_heavy`, `balanced`, `defensive`. | Existing ensemble optimizer; policy-controlled profile mapping and feasible projection. |
| Alpha disagreement | `trend_supported`, `reversal_supported`, `mixed`, `insufficient`. | Select among prevalidated profiles; `insufficient` means baseline. |
| Event novelty | `new_material`, `repeat`, `unresolved`, `irrelevant`. | Bounded event profile only for eligible information; repeated/irrelevant/unresolved news creates no new JEV tilt. |
| Forensic audit | `audit_verdict`: `clean`, `qualified_exception`, `disclaimer`, `adverse`; `revenue_quality`: `organic_cash_backed`, `unbilled_receivable_inflation`, `channel_stuffing`; `asset_siphoning_risk`: `low`, `unusual_lending_to_affiliates`, `cross_pledge_collateral`. | Research flags with source passages and expiry. No live universe exclusion. Proposed `forensic_score` is excluded from the initial contract until a deterministic or calibrated score definition exists. |
| Corporate action | `cash_dividend`, `stock_dividend`, `dilutive_rights_issue`, `esop_excessive`, `private_placement_discount`. | Event classification; numerical adjustment comes from authoritative action data and tested formulas. |
| Data anomaly | `valid_market_breakout`, `unadjusted_corporate_action_gap`, `block_trade_noise`, `stale_feed_error`. | Advisory triage queue. Deterministic data validation controls quarantine; preserve original values and lineage. |
| Risk sentinel | Action `hold`, `reduce_exposure`, `halt_new_entries`, `full_de_risk`; recovery `wait`, `resume_gradual`, `resume_full`. | Advisory report only; full de-risk and recovery remain under existing risk authority. |
| Shared event driver | `shared_driver`, `independent`, `unclear`. | Suggest event groups; quant risk engine computes concentration and admissible caps. |
| Execution context | `routine`, `event_sensitive`, `unclear`. R1 tactic candidates: `passive_limit_post_only`, `twap_bounded`, `vwap_volume_tracking`, `aggressive_take`, `iceberg`; urgency `patient`, `moderate`, `urgent`. | Choose only an implemented, venue-supported, prevalidated execution profile. Unsupported tactics and unclear context fall back. |
| Drift / decay | Drift `structural_microstructure_change`, `cyclical_regime_rotation`, `noise`; recommendation `full_retrain`, `incremental_update`, `wait`; deeper attribution `data_issue`, `cost_shift`, `regime_mismatch`, `unclear`. | Research explanation and review queue; never automatic training or model promotion. Keep drift and attribution as distinct versioned fields. |
| Tie-breaker | No provider-specific `Score` / `NoulCriteria` API assumed valid. Start with an allowlisted ordering of the eligible tie set, with deterministic stable fallback. | Ranking within a predefined tie tolerance only; validate permutation, cardinality and eligibility. No broad universe rescoring. |
| Black-Litterman | Sector labels and qualitative direction schema must be specified against supported provider primitives before implementation. | Quant code constructs P, Q and uncertainty from validated mappings; no arbitrary LLM expected return or invented confidence. Initial live effect disabled. |
| Alpha Judge | No complete schema in R1; retain advisory-only scope. | Research review of candidate alphas; cannot approve, veto, deploy or retrain. Contract approval is a prerequisite to any implementation packet. |

### 3.3 Cache and persistence invariants

The cache key must distinguish canonical sanitized facts, domain, entity set, source revisions, full decision cutoff, schema/prompt/model/policy/profile versions and relevant gate scope. Intraday reuse must not collapse distinct information sets into one UTC day. Verify the current validator and call sites before replacing the day-based key. Migration must either validate legacy entries explicitly or invalidate them; never silently reinterpret them.

Use bounded transactions, atomic commits, existing SQLite WAL support where applicable, a single-writer discipline where required and finite lock waits. Persist status only with its associated envelope. Duplicate requests are idempotent. Failed, partial, corrupt or incompatible entries cannot be treated as successful labels. Retention, maximum row/payload size and storage cap are required configuration before enabling a domain.

Historical replay performs no provider/network fallback. Cache miss returns a documented baseline result or stops a completeness-required experiment; distinguish these experiment policies in advance. Live cache TTL must follow domain freshness and source revision semantics, not a universal expiry. A report revision invalidates a prior forensic label even before its nominal TTL.

## 4. Quantitative authority and combined risk budget

Let `w0` be the valid quantitative baseline and `wp` a prevalidated target profile. A candidate mixture is `w = (1 - lambda) * w0 + lambda * wp`. Validation policy selects lambda; JEV never supplies it. The initial value for every new production influence is zero until authorized evidence and configuration exist.

After all overlays, recompute per-name and sector exposure, gross/net exposure, cash, liquidity/participation, turnover, permitted sells, settlement constraints and event-group concentration. Quantify both maximum per-name deviation and total absolute deviation from `w0`; measure gross/net and turnover deltas separately. Separate layer-level caps do not substitute for a combined cap.

Before any nonzero deployment, L2 must produce a versioned policy with numerical limits, units, calibration sample, rationale and owner for lambda, aggregate deviations, risk budgets, freshness, provider deadline, calls/day, spend/day, payload/storage/memory and concurrency. L1 must route it through independent review. An unset limit disables the new influence; it does not select a favorable default. This explicit disable rule resolves missing research calibrations without inventing thresholds.

A feasible baseline is the fallback for timeout, malformed output, stale evidence, conflict, unknown profile or infeasible projection. If the baseline itself violates constraints, the existing deterministic risk engine handles it; do not normalize invalid weights and call them safe. No JEV failure may lift an existing deterministic veto or relax a risk bound.

Finite-value checks precede all arithmetic. Check zero denominators, empty universes, zero variance, impossible simplex caps and covariance conditioning. Do not turn NaN into zero silently or discard negative weights without respecting the strategy's constraints. A fixed projection iteration count is not evidence of feasibility; verify its residuals and bounds.

## 5. Research workstreams and controlled integration

### 5.1 Baselines and selective invocation: P0

Implement a deterministic decision policy using freshness, valid source, novelty, disagreement and potential decision materiality. Compare no-call, always-call, cache-only and selective-call modes under the same eligible information. Do not use a second LLM to decide whether to call JEV.

Call only where validation estimates support benefit exceeding total inference cost and latency cost. If benefit cannot yet be estimated, run a bounded research sample; production stays on baseline. Account for retries, escalated/System 2 calls, routing, failed calls and fallback overhead. Report inference savings separately from trading-cost savings.

Deliverables: reproducible baseline decision ledger, invocation policy version, provider cost accounting, cache metrics, reasons for skipped calls and a paired utility/cost comparison. High cache hit rate alone cannot satisfy acceptance.

### 5.2 Regime and alpha disagreement: P1

Reconcile three-state/four-state contracts, then compare fixed profiles, deterministic same-feature regime rules, numeric-only JEV and JEV with text context. Evaluate existing 60/40, 1.25/0.75 candidates without treating them as optimized parameters. Freeze mapping and parameter choices before test evaluation.

Use alpha IC, decay and disagreement evidence available at the cutoff. Attribute performance to individual overlays and interactions. Remove numeric-only JEV if a deterministic rule matches it; remove text context if it adds no robust out-of-sample utility. No expansion of leverage or trading universe follows automatically from an optimistic label.

### 5.3 Event novelty, corporate action and forensic research: P1/P2

Compare novelty classification with normalized-content hashing and simple entity/event rules. Treat an updated announcement as a new revision, not necessarily a new economic event. Retain correction chains and distinguish publication from ingestion/availability.

Corporate-action treatment must avoid applying both an adjusted-price correction and a duplicate economic penalty. Verify ex-date, record date, payment date and the trading calendar. Rights, dividends, splits and ESOP examples require units and entitlement definitions. The original 0.7 multiplier is only an experimental arm.

Forensics records audit qualification, report revision, reporting period, source passage and label validity. Do not equate every qualified exception with fraud. Compare proposed exclusions counterfactually, including missed profit, avoided loss, turnover and tail outcomes. Record inconclusive evidence explicitly. No new JEV-driven hard veto in production.

### 5.4 Event concentration and advisory risk: P2

Compare shared-driver labels with sector grouping and simple return correlation. Quantify incremental expected shortfall, drawdown and concentration evidence; an event group is a suggestion, not a risk-limit override. Conflicting event labels add no exposure adjustment.

Risk sentinel actions and recovery labels produce alerts for the existing risk workflow. Record baseline action beside the suggestion. Neither `resume_full` nor absence of a risk label may clear deterministic stops. The R1 emergency 0.3 exposure and 5% stop examples remain unapproved research candidates.

### 5.5 Tie-breaker and execution: conditional P2

Define the tie tolerance from baseline scores on validation data. Bound the request to the original suggested 10-15 eligible ties, enforced as a configured ceiling of 15 for this initial research design. If more names tie, use the existing stable deterministic rule rather than selectively choosing a favorable subset. Compare JEV ordering against stable rank and simple same-input tie rules.

Execution work depends on reliable order-book, quote, trade and timestamp data. T-1 volume cannot substitute for contemporaneous book depth. Verify actual exchange/broker support for post-only and iceberg semantics before exposing those choices; the initial allowlist is only the intersection with supported existing profiles.

Evaluate implementation shortfall, fill probability, missed opportunity, adverse selection and total net utility on the same intended orders. Distinguish selecting an easier order from executing the same order better. Counterfactual fills must disclose liquidity and matching assumptions. No JEV-specified price, size or arbitrary urgency multiplier reaches a broker.

### 5.6 Data guard, Black-Litterman and decay attribution: later research

Data guard annotates anomalies and preserves raw inputs. Deterministic validation decides quarantine. Test legitimate splits, block trades, halts and stale feeds so that an advisory label cannot erase valid observations or contaminate future labels.

BL work requires a defined sector taxonomy, dimensional consistency of P/Q, covariance regularization and an uncertainty mapping. Unless provider scores exist and are calibrated out of sample, do not manufacture confidence. Missing or invalid views mean baseline allocation. This work is deferred behind proven core evidence.

Compare drift and decay explanations with the existing numerical monitor. Measure detection delay and false alarms. Recommendations may request data repair or research; retraining and promotion require their own implementation and review workflow. Alpha Judge likewise remains advisory until a concrete bounded contract is available.

## 6. PIT, experiment design, and promotion evidence

### 6.1 Two independent leakage boundaries

Data PIT requires every source revision to have `available_at <= decision_cutoff`. Record event time separately; a backdated publication date does not make later-ingested content historically available. Preserve source snapshots, delisted symbols, suspensions, corporate actions and exchange calendars. A delayed decision cannot retroactively execute at a pre-decision price.

Model PIT is not proven by historical input timestamps. A modern model may know subsequent outcomes. Label retrospective runs as retrospective-model experiments. Masking tickers/dates is sensitivity analysis only. Prospective shadow with decisions recorded before outcomes and mature labels is mandatory before considering trading authority.

### 6.2 Falsifiable comparisons

| Arm | Definition | Purpose |
|---|---|---|
| B0 | Current pure quantitative baseline | Reference behavior and costs. |
| B1 | Deterministic rule using the same information | Test whether simpler code captures the value. |
| B2 | Existing JEV overlays, enabled individually | Establish current incremental contribution. |
| B3 | Exactly one new JEV extension | Attribute incremental benefit; interactions tested only after isolated effects. |
| B4 | Shuffled/random labels preserving distribution | Negative control, research only, never connected to execution. |

Use identical PIT universe, prices, calendar, execution timing and cost model across paired arms. Fit on train, select on validation, freeze on test. Use walk-forward splits with purge and embargo matching each label horizon; derive actual date ranges from available data rather than reusing an unrelated historical dataset. Record dataset coverage, missing periods, event counts, universe density and minimum independent sample requirements before selecting ranges.

The research manifest must contain concrete train/validation/test dates, horizons, embargo rules, random seeds, all attempted hypotheses/profiles, primary metric, minimum economically relevant effect, risk noninferiority limits and sample-size/precision rationale. Missing values block the experiment or promotion; they are not placeholders to be silently filled after seeing results.

Metrics: after-fee/tax/slippage return, drawdown, expected shortfall, turnover, IC where relevant, implementation shortfall/fill/missed opportunity for execution; p95 latency, timeout, cache hit, baseline fallback, call count and full inference cost for operations. Use paired same-day deltas and time-dependent block bootstrap. State uncertainty, multiple-comparison exposure and regime/sector sensitivity; do not promote on win rate alone.

Stress fees/slippage, liquidity, limit-up/down sessions, unavailable fills, suspended/delisted symbols, zero volume, holidays, VND units and settlement restrictions. All stressed risk budgets must remain satisfied. Freeze labels and parameters; any test-informed change requires a new version and a fresh holdout.

### 6.3 Continue, stop, and shadow criteria

Continue only if B3 improves on both B0 and B1 out of sample under the preregistered economic and uncertainty criteria, stays inside risk budgets, survives cost stress and meets operational budgets. Stop or simplify when gains disappear after fees, occur only in sample or one regime, match shuffled-label outcomes, or are matched by a cheaper baseline. Inconclusive evidence stays research-only.

Shadow logs every eligible decision, baseline and JEV proposal, including skipped, unfilled and rejected cases. Do not evaluate only selected JEV trades. Required duration is determined by independent event count and mature outcomes, not an arbitrary number of weeks. Independently review observed model/version drift and source coverage before advancing.

## 7. Implementation packets, dependencies, and ownership

All roles below are candidate assignments for future L1 dispatch. No dispatch, approval or completion is asserted here. L2 role IDs must be 6-16; independent L3 roles must be valid audit-capable roles in 17-30. Role 26 is planning-only and is excluded from auditing this plan's implementation.

| Packet | Dependency | L2 owner candidate | Scope and deliverable | Acceptance evidence | Independent L3 candidate |
|---|---|---|---|---|---|
| W0: inventory and frozen baseline | L1 review of this plan | 6 system-architect with 14 data-scientist | Resolve active commits/gates, source schemas, exact consumers and dataset coverage; record baseline and compatibility inventory. | Reproducible manifests; no unverified claim of existing gate completion. | 20 compliance-officer and 21 code-reviewer, independently selected. |
| W1: contracts, PIT, bounded invocation | W0 | 16 machine-learning-engineer; 10 database-admin for cache migration | Extend existing `src/omega/core/llm_config.py` and caller adapters; domain registry, versioned cache keys, bounded budgets, deterministic selective calls. | Negative schema/PIT cases, migration/rollback evidence, no-network replay, complete fallback reasons and resource limits. | 19 security-auditor plus 18 sdet. |
| W2: regime and alpha calibration | W1 | 14 data-scientist | Existing `regime_overlay.py`, `hmm_model.py`, `ensemble_optimizer.py`; resolve state mismatch and family mapping; bounded aggregate influence. | B0-B4 experiment manifest/results, feasibility residuals, baseline equality when disabled; existing regression coverage extended by L2. | 20 compliance-officer plus 21 code-reviewer. |
| W3: event and forensic shadow | W1 | 15 data-engineer with 14 data-scientist | Existing micro/event ingestion adapter; proposed `src/omega/quant/alpha/forensic_filter.py` only if no suitable existing seam; novelty, revisions and counterfactual forensics. | Rule-dedup comparison, revision/expiry tests, corporate-action accounting, proof no production veto. | 20 compliance-officer plus 17 qa-engineer. |
| W4: concentration and risk advisory | W2, W3 evidence | 14 data-scientist with 9 backend-engineer | Existing portfolio/risk consumer located in W0; combined risk budget and advisory action ledger. | Sector/correlation baseline comparison, stacked-overlay stress, deterministic stop/recovery preservation. | 25 it-systems-auditor plus 20 compliance-officer. |
| W5: tie-break and execution research | W1 plus W0 data-readiness evidence | 14 data-scientist with 9 backend-engineer | Existing ranking and execution simulator consumers located in W0; eligible permutations and supported tactic profiles. | Same-order comparisons, 15-name cap, deadline/unsupported-profile fallback, realistic fill assumptions. | 23 performance-tester plus 18 sdet. |
| W6: later data/BL/decay research | W2-W4 evidence; W5 where execution costs required | 15 data-engineer and 14 data-scientist | Reuse existing `black_litterman_overlay.py`, `drift_detector.py`, `continuous_learning.py` only after confirming paths/contracts; anomaly triage and decay attribution. | Validated numeric mappings, zero automatic retraining, retained raw data and matched deterministic controls. | 20 compliance-officer plus 21 code-reviewer. |
| W7: integrated verification and handoff | All in-scope packets completed or explicitly deferred by L1 | 11 devops-engineer packages L2 evidence only | Deterministic replay bundle, prospective shadow ledger, rollback drill, 16D evidence index, operating runbook. | Independent L3 review on exact candidate revision; L1 determines next action under governance. | Independent qualified L3 team; none of the implementation contributors. |

Critical path: W0, W1, W2, W4, W7. W3 can proceed after W1 independently of W2, with file ownership separated. W5 remains blocked until execution measurements are trustworthy. W6 is intentionally later; failure of an earlier economic hypothesis is grounds to drop its downstream extension. Verification and handoff are the final phase; each packet still carries local acceptance criteria.

The consolidated research's batch gate names remain lineage references: `GATE_JEV_REGIME_ALPHA_WEIGHTING_20260926`, `GATE_JEV_FORENSIC_TIEBREAKER_EXEC_20260926`, `GATE_JEV_RISK_DATA_GUARD_20260926`, `GATE_JEV_BL_DRIFT_20260926`. W2 maps primarily to the first; W3/W5 to the second; W3/W4/data guard to the third; BL/decay to the fourth. Shared W1 evidence must be referenced explicitly in each dependent packet. L1 must reconcile active ownership and packet boundaries before dispatch; no two writers edit shared files concurrently.

Each packet must name exact owned files, exclusions, schema version, dependencies, evidence paths and reviewer identity before implementation begins. Assign exactly one primary L2 lead per packet; other named L2 roles are same-tier specialists. Paths not yet verified are discovery prerequisites in W0, not permission for broad edits. A material scope expansion requires a revised packet and fresh independent review.

Future evidence belongs under `.ly_state/session/jev_deep_integration_20260926/`, with packet subdirectories `W0` through `W7`. Each dispatched packet produces `scope.md`, `input_manifest.json`, `l2_report.md`, `matrix_evidence.md` and `rollback.md`; experiments also produce `experiment_manifest.json` and `metrics.json`, and independent reviewers own `l3_report.md`. These paths are a proposed handoff convention, not files created or results claimed by this planning task. Governance-native receipts remain at the locations required by the existing workflow and are linked by path and hash rather than replaced.

## 8. Governance and canonical 16-Dimension Adversarial Matrix

The numbering below preserves P1's JEV-specific matrix. The repository also contains a screener-specific 16D suite with different labels; it is useful for probe ideas but is not substituted for this matrix. UTF-8, zero division, memory bounds and schema drift are explicit acceptance requirements within the appropriate dimensions.

| D | Dimension | Required adversarial cases and invariant | Evidence and review focus |
|---|---|---|---|
| 1 | Scope | Cross-gate payloads, wrong file ownership, accidental live call in replay, unsupported domain, new veto or auto-retrain path. Only the dispatched contract and allowed authority execute. | Owned-file diff, domain/gate routing cases, disabled-mode trace; L3 code review. |
| 2 | Schema and enum | Missing/extra keys, wrong types, unknown labels, malformed JSON, oversized strings, schema drift, invalid UTF-8, Vietnamese diacritics, normalized versus distinct source text. Reject incompatible data; hash/persist explicit UTF-8 canonical representations without corrupting identifiers. | Versioned schema fixtures, strict UTF-8 round trip and migration compatibility results; L3 QA/security. |
| 3 | PIT integrity | Future availability, revised report, after-session update, timezone/DST conversion, Tet/holiday cutoffs, intraday collision, stale universe, suspended/delisted symbol. Every consumed revision was available at cutoff. | Source manifest, timestamp boundary cases, PIT universe and historical/prospective evidence separation; L3 compliance. |
| 4 | Determinism and replay | Reordered equivalent inputs, changed model/prompt/profile versions, missing cache, repeated replay. Stable canonical inputs produce identical keys and deterministic consumer outputs; historical replay has zero provider calls. | Repeated replay hashes and network-denial evidence. Fresh provider generation is not claimed deterministic; L3 SDET. |
| 5 | Retry and timeout | Timeout, 429, transport failure, auth failure, schema error, slow provider. Preserve prior maximum two attempts with 2.0-second delay only when total deadline permits; no auth/schema retries; exhausted deadline returns explicit fallback. | Attempt/deadline traces including routing/escalation cost; L3 performance/SDET. |
| 6 | Rate and concurrency | Parallel duplicate requests, cancellation under load, lock contention, oversized batch, memory pressure. Bound in-flight requests, queue, payload, batch and resident memory; no unbounded futures or prompt accumulation. | Load profile with configured limits and measured peak memory; idempotency and lock timeout results; L3 performance. |
| 7 | Cache | Partial/corrupt/duplicate rows, source revision, expired entry, incompatible schema, full disk, WAL contention, legacy day-key collision. Atomic valid envelopes only; bounded retention/storage; invalid entries never accepted. | Migration/rollback fixtures, concurrent reader/writer results, storage-failure trace; L3 SDET/systems. |
| 8 | Fallback | API disabled, no key, stale evidence, unresolved conflict, invalid projection or baseline. Valid quant baseline on classification failure; invalid baseline reaches deterministic risk handling; no fallback can clear a veto. | Exact baseline comparison and risk-preservation assertions; L3 QA/compliance. |
| 9 | Budget | Simultaneous reservations, expensive escalation, retries, cancelled calls, overspend near limit. Atomic accounting includes all chargeable work; reservations cannot oversubscribe; uncertain spend blocks further calls pending reconciliation. | Budget ledger and saturation/cancellation cases; L3 systems. |
| 10 | Injection | Malicious news/report/provider text, fake role instructions, embedded shell flags, prompt injection, path traversal. Treat text as data; no execution, tool invocation, policy override or unsafe file path derives from it. | Adversarial payload suite and trust-boundary review; L3 security. |
| 11 | Secrets | Keys in URL/userinfo, exception text, prompts, cache fields, hashes, logs and evidence. Credentials and sensitive payloads remain absent; sanitize before hashing/logging; secret hashes are not an accepted substitute. | Redacted error/output scans and safe fixture assertions; L3 security. |
| 12 | Network | SSRF, literal/private/special-use IPs, IPv6-mapped IPv4, redirects, DNS rebinding, TLS/SNI failure, untrusted endpoint and no timeout. Preserve existing allowlist/TLS controls; deny replay egress. | Endpoint validation and transport traces without credentials; L3 security/penetration test. |
| 13 | Numerical integrity | NaN/Inf, zero denominator/variance/volume/assets, overflow, empty universe, infeasible cap, singular covariance, VND scale mismatch, all overlays amplifying exposure. Reject invalid arithmetic; quant computes numbers and final limits; no fabricated confidence. | Feasibility residuals, unit invariance, zero-division and aggregate-cap cases; L3 compliance/code review. |
| 14 | Provenance | Missing revision/hash, wrong code commit, mismatched gate/envelope, mutable source, unknown model revision, immature labels. Trace every result to exact inputs and limitations; no historical evidence presented as prospective. | Manifest-to-decision-to-outcome join completeness and receipt hashes; L3 compliance. |
| 15 | Cancellation | Interrupted request/SSE stream, process termination, interrupted transaction, cancellation after reservation. No partial-success record, orphaned order action or leaked reservation; recovery is idempotent. | Fault-injection/restart evidence and reconciled budget/storage state; L3 SDET/systems. |
| 16 | SoD and rollback | Same writer/reviewer under different role IDs, stale report, forged approval, unauthorized closure, disable during incident. Independent identities and exact-revision evidence required; rollback restores baseline deterministically. | Identity/conflict register, validated L2/L3 reports, authorized closure evidence when separately permitted, rollback drill; L3 systems/L1. |

### 8.1 Writer != Auditor enforcement

1. L1 selects a valid L2 writer from roles 6-16 and an independent audit-capable L3 reviewer from roles 17-30. Resolve each role from its actual role specification. The architecture table currently names only through role 26; do not invent names or grant authority to unspecified 27-30 roles.
2. Enforce both `l2_role_id != l3_role_id` and distinct agent/person identities. Changing a role label does not erase authorship. A worker that implements, coauthors or repairs code cannot audit that same work.
3. Role 26 and this planning team produce no audit verdict or gate approval. Planning participation and later implementation participation must be disclosed to L1 when checking reviewer conflicts.
4. L2 submits an exact revision, scoped diff, implementation report, reproducible commands/results, limitations, 16D evidence index and rollback instructions, then exits and saves state before L3 starts. Validate the report using the repository workflow before independent review; concurrent L2 edits invalidate the review snapshot.
5. L3 reviews the submitted revision independently. Review findings and remedial work remain separate artifacts. Remediation invalidates prior acceptance for the changed revision and requires fresh independent review under repository policy.
6. Only authorized L1 closure may advance a gate after the required independent verdict and successful `sod_gate_enforcer.py` validation. This document does not run that workflow, emit its receipt or represent its exit status.

Required future receipt metadata: gate, packet, source/code revision, writer identity and role, auditor identity and role, schema/policy versions, evidence artifact hashes, report validation result, exceptions, timestamps and authorized closure reference if closure actually occurs. Missing or mismatched metadata blocks advancement.

## 9. Rollout, observability, incident handling, and rollback

Deployment states are disabled, retrospective research, prospective shadow, and separately authorized bounded-profile use. No automatic transition follows elapsed time, an attractive backtest or a valid schema. New veto, autonomous retraining and unsupported execution tactics are excluded from this progression.

Every new domain starts disabled for production influence. Record baseline/proposal/final allocations, reason codes, applied policy version, aggregate deviations, cache outcomes, timeout rate, p95 latency, call/spend reservations and finalized cost, memory/storage use, invalid-schema rate and source age. Redact before persistence. Alert against the frozen operational budgets, not uncalibrated universal thresholds.

Immediate deterministic fallback is required for expired evidence, incompatible contract, exceeded combined cap, provider outage or exhausted operational budget. Integrity/security incidents disable the affected JEV path and follow the existing incident procedure. Failure of the classification cache must not bypass risk checks or stop baseline computation where the existing architecture supports it.

Rollback procedure for future operators:

1. Disable the affected JEV feature/profile through the authorized configuration path; record the incident and last effective revision.
2. Verify subsequent decisions use the valid quantitative baseline with unchanged deterministic risk vetoes. Do not cancel or replace real orders solely because a label disappeared; apply the existing order-management policy.
3. Stop new provider requests, reconcile in-flight reservations and quarantine incompatible cache records while preserving evidence.
4. Restore the prior compatible policy/schema/code revision using the normal deployment procedure; reverse data migration only after proving compatibility and retaining a backup.
5. Replay the captured incident inputs without provider access, demonstrate baseline equivalence and obtain fresh independent review before any re-enable request.

## 10. Final verification and handoff requirements

Future W7 verification must cover existing macro/micro/router/SoD consumers as well as changed quant paths. Reuse existing regression surfaces, including `tests/test_jev_regime_alpha_weighting.py` and `tests/test_sod_jev_model_routing.py`; L2 defines additional tests for the matrix and actual changed contracts. Exact commands must use the repository's verified environment and test configuration. No command or result is fabricated in this plan.

The handoff bundle must contain: approved implementation scope, exact revision and dependency manifest, contract/profile registry, frozen experiment manifest, B0-B4 results and uncertainty, prospective shadow evidence with mature labels, all 16D rows linked to concrete cases/results, operational budget/load results, redaction checks, migration/rollback evidence, independent reports and unresolved limitations.

Completion conditions for implementation consideration:

- Every enabled domain has a finite contract, clear authority, valid source lineage, expiration policy and deterministic fallback.
- Replay is offline and reproducible; retrospective-model results are not mislabeled as full PIT evidence.
- All combined portfolio constraints hold after all overlays; disabling JEV reproduces the valid baseline.
- Net benefit exceeds both baseline and deterministic controls under the preregistered criteria; inconclusive domains remain disabled or are removed.
- Prospective shadow has sufficient independent observations and mature outcomes; cost and resource budgets hold under stress.
- Every matrix dimension has attributable evidence on the candidate revision; independent Writer != Auditor separation is proven.
- L1 receives concrete artifacts for any subsequent authorization. No gate is deemed approved by this checklist or by delivery of this document.

Planning handoff: comprehensive implementation scope and decision rules are documented. Actual implementation, investment validation, independent audit and gate decisions remain future work under their respective authorized roles.
