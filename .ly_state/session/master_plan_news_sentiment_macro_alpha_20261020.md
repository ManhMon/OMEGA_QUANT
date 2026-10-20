# Master Plan: News Sentiment, Ecosystem Spillover & Macro Liquidity Alpha Pipeline

- **Phase Gate**: `GATE_MASTER_PLAN_NEWS_SENTIMENT_MACRO_ALPHA_20261020`
- **Owner**: `system-architect` (Role 6); research co-owner `data-scientist` (Role 14); data delivery owner `data-engineer` (Role 15)
- **Status**: DRAFT_FOR_INDEPENDENT_L3_REVIEW
- **Created**: 2026-10-20
- **Version**: 2.1.0
- **Evidence cutoff**: `2026-10-20T02:19:16Z`
- **Repository snapshot**: `d8fd865f28cfbc9946dfb6bc4b433ba3e7b6eaf9`; pre-existing working-tree changes are not certified by that commit.
- **Delivery boundary**: this master plan and the accompanying L4 implementation report only. Every implementation task, test name and operational target below is proposed unless explicitly identified as existing evidence. No production deployment, achieved alpha, audit verdict or gate approval is asserted.

## 1. Objective, assumptions and non-goals

Build a reproducible, point-in-time (PIT), cost-aware Vietnam-equity research pipeline with four independently measurable workstreams:

1. **News Sentiment Decay Alpha**: issuer-specific sentiment, freshness, event novelty and news-volume surprise.
2. **Ecosystem Sentiment Spillover**: incremental propagation of issuer news shocks through historically knowable corporate relationships.
3. **Macro Liquidity Regime Switcher**: a conservative exposure overlay based on published interbank/liquidity conditions, not a claim of causally observed brokerage margin pressure.
4. **PEAD Drift Engine**: post-earnings-announcement drift based on comparable financial surprises and genuinely observable release times.

Success means an independently reviewable plan, then separately authorized implementations which can reconstruct every historical decision from immutable source vintages, model versions, calendar versions and execution assumptions. A rejected hypothesis is a valid research outcome. A positive backtest is not permission to trade.

### Assumptions requiring confirmation before implementation

- Initial strategy is daily, long-only cash equities on HOSE/HNX/UPCOM; short portfolios are diagnostic only unless borrowing and market rules are separately authorized.
- Existing local data, Python numerical libraries, Parquet and existing project storage are preferred. No new service, graph database, broker API, queue or model provider is required for the first implementation.
- Initial daily decision is before the next eligible trading-session execution; minimum T-1 information policy remains mandatory. Exact decision and execution clocks must be frozen in the run manifest.
- The previous draft's **6,498 articles / 703 tickers** are inventory claims, not verified clean/PIT coverage or a tradable historical universe. Recount raw articles, unique events, issuers, valid timestamps, sessions and unavailable records before research. Ten years of OHLCV does not establish ten years of news, graph, macro vintages or earnings consensus.
- External news/financial-source redistribution rights, retention rights and model-processing rights must be documented before provider access or any hosted-model submission. This planning session grants neither new credentials nor a new data-upload authorization.
- Realistic earnings-consensus history, actual release timestamps, vintage macro history and dated relationship edges may be absent. Those absences block the corresponding historical claim; they are not filled with today's data.

### Non-goals

No automatic live execution; no autonomous promotion; no current-graph backfill represented as PIT; no causal inference from correlation alone; no forced coverage of all current tickers; no deep graph neural network, continuous crawler or learned regime model until the simple baseline establishes incremental value. No changes to `.ly_state/session/audit_reports/`, `.ly_state/session/phase_gates.json`, anti-drip contracts, sidecars or prompt artifacts.

## 2. Current-state map and minimum future change surface

Existing sources establish reuse opportunities, not proof of an end-to-end alpha implementation:

| Existing source | Reuse boundary | Required contract before use |
|---|---|---|
| `scripts/fetch_news_sentiment.py`, `src/omega/data/macro_news_pipeline.py`, `src/omega/data/news_aggregator.py`, `src/omega/data/llm_sentiment_scorer.py` | Existing news collection/scoring surfaces; historical fetcher uses `title-substring-clipped-v1`, not proven article-body/LLM scoring | Establish historical first-seen, revisions, entity attribution, score readiness and batch coverage; projected availability includes scoring time, so a current score is not automatically a historical factor |
| `src/omega/quant/signal/sentiment_loader.py`, `src/omega/quant/signal/sentiment_alpha.py`, `scripts/run_sentiment_blend.py` | Existing backward availability join, sentiment alpha/age-decay and score-JSON blend seam | Reuse before adding a new alpha module; alpha decay defaults to zero and age must be supplied; reconnaissance found no production loader-to-alpha connection |
| `src/omega/data/macro_rates.py` | `DirectMacroClient`, interbank, HNX yield, OMO and USD/VND parsing | Explicit rate/amount units, tenor, source publication evidence, vintage identity, timezone and staleness; fallback timestamp strings alone cannot certify historical publication |
| `src/omega/data/hybrid_evaluator.py` | Existing capped LLM contribution, quant-only fallback, null-quant behavior and hard-veto precedence | Do not silently increase the LLM cap or let a new feature manufacture a valid quant score; preserve result schema and lineage |
| `scripts/fetch_financial_statements.py` | Existing financial normalization, immutable raw-snapshot location and atomic-write helpers | Fiscal-period end and conservative embargo are not the actual earnings announcement; preserve source publication/revision evidence independently |
| `src/omega/quant/graph/loader.py` | `FinancialStatementLoader.load_raw()` and `asof_join_market()` | Loader validates fiscal-period/availability ordering; PEAD still needs release-event identity, fiscal comparability and explicit decision timestamps |
| `tests/test_fetch_financial_statements.py`, `tests/test_financial_loader.py` | Existing financial PIT and persistence regression surfaces | Extend only in a future implementation authorization; existing tests do not establish a PEAD strategy |
| Existing graph, alpha, risk, calendar, cost and walk-forward components | Reuse established interfaces after focused call-site reconnaissance | Resolve lag ownership, edge provenance, cost conventions and strictly chronological deployment validation before wiring new factors |

### Reconnaissance inventory limits

`data/historical_news/run_703_full/checkpoint.json` reports 703 collection-scope members, 1,406 shards, `pit_verified: false` and `full_history_verified: false`. Some names are marked `no_articles_observed_history_unverified`; that is incomplete evidence, not verified empty history. `.ly_state/session/sentiment_checkpoint.json` reports a canonical dataset of 1 row / 1 ticker; this is checkpoint metadata, not independent Parquet validation. No bulk shards were summed, so 6,498 remains unverified.

`src/omega/data/interbank_rate_snapshot.py` assigns availability at session open while parser fallbacks use 09:00 UTC; neither substitutes for actual source release evidence. `src/omega/data/calendar.py` has a limited fixed-holiday fallback when holiday JSON fails; a research run must fail closed on an incomplete authoritative calendar rather than assume Tet/Hung Kings closures are covered. These are integration constraints to resolve in future authorized packages, not defects patched by this documentation change.

### Proposed additions or extensions, not implemented here

- Extend `src/omega/data/macro_news_pipeline.py` for a versioned event-to-factor serialization boundary rather than create a second ingestion stack.
- Prefer extending `src/omega/quant/signal/sentiment_loader.py` and `src/omega/quant/signal/sentiment_alpha.py`, wiring at `scripts/run_sentiment_blend.py` or the confirmed current signal seam. The previous draft's `src/omega/quant/alpha/news_sentiment.py` does not exist; do not create a competing module unless the existing contract demonstrably cannot express the factor.
- Reuse `src/omega/quant/network_graph.py` and `config/corporate_ecosystems.json` as the dated corporate-edge source. Existing corporate edges have weight 1.0, not ownership/exposure percentages; `src/omega/quant/graph/builder.py` uses an undirected graph and cannot establish directional propagation. Proposed new `src/omega/quant/alpha/spillover.py` is only a conditional home for the bounded transform, not graph persistence or ingestion.
- Extend `src/omega/data/macro_rates.py` for missing source contracts, then the existing `src/omega/quant/risk/` integration surface for a deterministic liquidity overlay. Do not implement a second macro HTTP client.
- Proposed new `src/omega/quant/alpha/pead.py`: earnings-event eligibility, explicitly typed surprise variants and decay. Use existing financial loader; do not confuse its graph namespace with network-spillover provenance.
- Extend `src/omega/data/hybrid_evaluator.py` only if the existing public boundary cannot accept the research result through metadata/current inputs. Portfolio exposure control belongs in risk, not as a disguised sentiment hard veto.
- Future focused tests belong alongside the corresponding existing tests. New package paths above require separate authorization and a fresh dependency/impact sweep; this plan does not create them.

### Architecture choices and rejected alternatives

| Decision | Choice and reason | Deferred alternative / trigger |
|---|---|---|
| Processing | Bounded daily batches, pure numerical transforms, existing scheduler | Streaming only when measured decision latency demands it |
| Storage | Immutable source files, typed Parquet partitions, small existing metadata store if needed | New DB only for measured concurrent access or query requirements |
| Sentiment | Existing scorer plus frozen deterministic lexicon baseline | New model/provider only after Vietnamese validation, provenance and data-rights review |
| Network | Sparse, bounded, lagged one-hop directed exposure | Multi-hop/diffusion only after incremental OOS evidence and explicit cycle/double-count controls |
| Macro | Transparent robust stress statistic plus hysteresis | HMM/learned switching only if it beats the fixed overlay after costs |
| Earnings | Typed consensus surprise; distinct seasonal-change baseline when consensus absent | Never synthesize consensus from subsequent news or revised actuals |
| Integration | Preserve quant-only baseline and existing evaluator safety contracts | No parallel evaluator or independent sentiment-only trading path |

## 3. Shared temporal and provenance contract

### Time fields and their meanings

Store UTC-aware instants; retain original source timezone and raw timestamp string for traceability. Use `Asia/Ho_Chi_Minh` for session membership. Reject ambiguous naive timestamps unless an allowlisted source contract supplies the timezone; never assume all naive timestamps are UTC.

- `as_of`: economic observation/event time, not an earnings release date when it is actually fiscal-period end.
- `source_published_at`: source-asserted release time, nullable and evidence-linked.
- `first_seen_at`: trustworthy local/provider archive observation time; not reconstructed from a filename.
- `source_available_at`: earliest substantiated availability of the particular vintage.
- `ingested_at`, `extracted_at`, `score_ready_at`, `model_available_at`: operational readiness and model knowledge constraints, separately recorded.
- `available_at` / `feature_ready_at`: conservative maximum of the necessary substantiated input and processing readiness timestamps for that mode.
- `decision_time`, `execution_time`, `label_end_time`: distinct instants; execution cannot precede an eligible decision.

For observations used by a decision, enforce `as_of <= available_at <= decision_time`. When an earnings document refers to a future guidance period, that period is a separate field, not an `as_of` that violates this ordering. Every contributing source, graph edge, scaler, model, consensus vintage and derived artifact must be eligible at the decision boundary.

Two historical evidence modes must never mix:

1. **Operational replay** uses actual first-seen/processing/model readiness. A recent bulk download is not operationally available years earlier.
2. **Retrospective research reconstruction** may use independently archived vintage release evidence and a scoring procedure demonstrably available at the historical cutoff. Store reconstruction assumptions separately. A modern LLM with unknown training cutoff cannot prove historical deployability merely because the input article is old. Such results remain retrospective diagnostics or require prospective shadow evidence.

Unverified caller-supplied rows never inherit archived/PIT-verified provenance from a historical loader or a verified sibling record. Missing availability is quarantined, not defaulted to midnight or copied from `as_of`.

### Session eligibility and lag ownership

- `15:30:00 ICT` (`08:30:00Z`) is the proposed **daily news batching cutoff**, not a universal exchange matching close. Exchange-specific continuous trading, auctions, negotiated trading, holidays and exceptional closures come from the versioned calendar.
- Batch D contains only data ready by its cutoff, inclusively. A record at cutoff + one timestamp unit belongs to a later batch. Closing-price availability follows the market-data contract and may be later than the news batch.
- A batch from session D cannot trade in D under the initial daily T-1 policy. It becomes eligible no earlier than the next valid session after all input availability constraints are satisfied. Friday after-cutoff, holidays and suspensions cannot be handled with a calendar-day shift.
- Explicit example: news ready Monday 15:29 ICT can enter Monday's batch and the next eligible session's decision. News ready Monday 15:30:01 ICT misses that batch; do not relabel it Monday 15:30 to obtain an earlier trade.
- Define one lag-certified decision-panel boundary. Inspect existing generator/evaluator/backtest shifts; document each transformation's additional delay. Preserve required existing defenses or adapt under separate authorization, but never blindly double-shift or remove a defense on the strength of a first-row-NaN check. Verify information and execution timestamps end to end.
- Equality at `available_at == decision_time` is allowed only if the processing-ready certificate and mandatory session lag also hold. Backdated revisions, future model artifacts and batch-before-publication cases fail closed.

### Minimal canonical schemas

| Dataset / proposed location | Identity and required fields | Invariants |
|---|---|---|
| News event ledger, proposed `data/news/events/` | `event_id`, `revision_id`, `source_id`, `source_article_id`, `content_sha256`, `syndication_cluster_id`, bounded text reference, timestamps, `provenance_status` | Immutable revision, strict UTF-8; do not include full URLs or secrets in diagnostic artifacts |
| Event-issuer scores, proposed `data/news/scores/` | event/revision/issuer, attribution weight, event type, signed score, confidence, scorer/model/prompt versions, readiness, evidence reference | Score in [-1,1], confidence/attribution in [0,1]; no target-price or future-return leakage |
| Relationship vintages, proposed `data/network/edges/` | `edge_id`, source/target issuer IDs, relationship type, signed exposure if justified, validity interval, known-at, weight, source evidence | Historical membership and known-at both enforced; no current-edge backfill |
| Macro vintages, proposed `data/macro/vintages/` | series/tenor/unit, economic date, vintage ID, publication/readiness, finite value, source evidence | No overwriting revisions; annual-decimal rates, explicit VND amount scale, explicit flow/stock meaning |
| Earnings release ledger, proposed `data/earnings/events/` | issuer, fiscal period, accounting basis, actual metric/unit/currency, release/revision ID, original/revised flag, consensus vintage if any, readiness | Period end distinct from announcement; compatible EPS share basis and quarterly vs cumulative values |
| Daily factor panel, proposed `data/factors/news_macro_alpha/` | issuer, decision time/session, feature values, validity/coverage masks, source watermark, max input availability, model/calendar/schema versions, lineage digest | Unique issuer/decision/version; immutable published partitions; no forward-filled initial lag holes |
| Run manifest, future `.ly_state/session/` artifact | run ID, source/input hashes, code/config/environment/seeds, calendar, train/validation/test intervals, trial registry, output hashes, coverage/failure totals | Gate/session/role binding; reproducible canonical JSON digest; explicit reconstruction mode |

These are proposed dataset contracts, not new services or a demand to create all directories immediately. Reuse an existing location where equivalent semantics are already enforced. Validate read/write/list/delete and retention symmetry; a listed partition must have a committed manifest and verified hash. Deletions use documented retention/tombstones, not silent removal of lineage still referenced by a run.

## 4. Workstream A — News Sentiment Decay Alpha

### Hypothesis and extraction

Issuer-specific unexpected, credible news may forecast short-horizon executable residual returns. Begin with a Vietnamese finance lexicon baseline; compare the existing scorer on a frozen, independently labeled issuer/event sample. Measure negation, uncertainty, quoted speech, sarcasm, numerical direction, corporate actions, rumors and multiple-issuer attribution. Headline positivity is not automatically positive cash-flow news.

Deduplicate exact content and near-duplicate syndicated events before counting. Duplicate reports increase corroboration metadata under a bounded cap, not unlimited signal strength. Stable issuer IDs prevent ticker reuse and alias collisions; historical names, sector and listing status must be dated. Classify earnings stories so PEAD and generic sentiment can be ablated without counting the same surprise twice. Treat all article text as untrusted data; no article instructions, links or embedded credentials may change tool routing or the scoring contract.

### Baseline mathematics

For eligible unique event e attributed to issuer i, let `s_e in [-1,1]`, `q_e in [0,1]` combine validated source/confidence/attribution weights, and `a_e(t)` be nonnegative completed trading-session age since first eligible batch. For half-life `h > 0`:

`w_e(t) = q_e * exp(-ln(2) * a_e(t) / h)`

`N_i(t) = sum_e(w_e(t) * s_e) / max(1, sum_e(w_e(t)))`

The denominator is deliberately floored at 1 so a lone old story decays toward zero rather than retaining its full signed score forever. This is an attenuated bounded score, not a conventional weighted mean. Retain raw decayed signed mass, effective weight, positive/negative components, unique-event count and coverage separately. Cap per-cluster and per-issuer daily contributions before aggregation; long repeated articles cannot dominate memory or alpha.

News-count surprise uses only prior eligible sessions: `V_i(t) = clip((count_i(t) - mu_i,past) / sigma_i,past, -5, 5)`. Fit window, clipping and seasonal adjustment on training data; do not count unavailable duplicate/revised stories as new independent events. Too little history or near-zero sigma yields unavailable with a warm-up reason, not infinity. Initial half-life candidates are 1, 3 and 5 sessions, registered as separate trials before validation.

Cross-sectional winsorization/neutralization uses contemporaneously eligible issuer characteristics; fitted parameters and any learned weights use training only. Maintain distinct `valid_no_news` (score 0 with complete observed coverage), `unknown_outage` (null), `warmup`, `unverified_timestamp` and `unsupported_language` states. Never backfill missing sources with a future scrape.

### Acceptance evidence for future implementation

- Deterministic duplicate/revision replay; bounded scores and resources; one event at age h contributes exactly half its original mass.
- Negation/entity benchmark, calibration and error slices by source/language/issuer/event type; labelers do not see future returns.
- Reordering source files or adding a future article leaves past panels byte-equivalent after canonical ordering.
- Incremental OOS performance versus quant-only, lexicon-only, count-only and earnings-excluded baselines. Sentiment must add value beyond size, sector, momentum and news attention.

## 5. Workstream B — Ecosystem Sentiment Spillover

### Edge contract and orientation

Use documented parent/subsidiary, ownership, supply/customer, lending or related-business relationships only when dated evidence supports them. A thematic co-mention is a separate, lower-confidence edge class, not an ownership fact. Associate weights with the information actually known at the cutoff, not later realized financial importance. An absent historical edge set makes historical spillover unavailable; a current graph is usable prospectively after its first trustworthy observation.

Let `A_ij(t)` mean **source issuer j affects target issuer i**. Set diagonal to zero; normalize each incoming row by `max(1, sum_j(abs(raw_A_ij)))`, giving `sum_j(abs(A_ij)) <= 1`. Directed asymmetry is intentional. Nonnegative baseline weights are safest; negative weights require a documented economic mechanism and a separately registered experiment. Cap nodes, edges and neighbors; stable deterministic tie-breaking is required when caps are reached and coverage loss is reported.

### Bounded propagation and incremental identification

Define a direct-news innovation relative to a training-fitted expectation, controlling sector/common-market news: `epsilon_j(u) = clip(N_j(u) - expected_news_j(u), -1, 1)`. Require finite eligible observed and expected scores before clipping. A missing required source innovation makes the affected target unavailable, not zero; an absent edge is known-zero only under complete graph coverage. The one-hop candidate is:

`P_i(t) = sum_j(A_ij(t-1) * epsilon_j(t-1))`

Since `abs(epsilon_j) <= 1` and each incoming row has absolute sum <= 1, `abs(P_i) <= 1`; assert this bound within numerical tolerance. Use lagged, PIT-filtered source innovations and edge vintages. No recursive re-ingestion of P as new direct sentiment; no self-loop; no automatic two-hop expansion. This intentionally adds a network lag beyond the direct-event panel. Record both source and target eligibility and lag certificates.

Compare raw propagation with residualized propagation controlling target direct sentiment, common sector sentiment, degree and size. A sector-wide macro story is not 30 independent issuer shocks. Count one underlying syndicated event once per documented attribution policy; normalize and bound source-event contributions across connected targets.

### Acceptance evidence for future implementation

- Two-node directed fixture proves orientation; reverse edge differs; zero-degree target has known-zero spillover only when graph coverage is complete.
- Cycle, self-loop, duplicate edge, unknown weight, future edge, expired edge and high-degree fixtures preserve bounds and provenance. A current-only graph yields no historical eligible edges.
- Adding unrelated nodes or shuffling edges does not change existing normalized signals unless the actual target neighborhood changes.
- OOS ablations: direct news alone; sector-average news; randomized degree-preserving graph; dated economic graph. Promote only incremental evidence after costs and multiple-testing control.

## 6. Workstream C — Macro Liquidity Regime Switcher

### Series and units

Start with published SBV O/N and 1W interbank rates. Consider OMO net injection, USD/VND changes and HNX yields only after independent historical availability, unit and revision contracts exist. A parser that emits a plausible `available_at` string does not prove a release schedule. Use vintage-aware as-of selection; no interpolation from a later revised series.

Canonical rate is annual decimal fraction: a source value `4.25 percent` becomes `0.0425`, exactly once. Preserve original unit/tenor/day-count convention. OMO flow must declare VND, million-VND or billion-VND and sign convention before normalization; positive injection reduces stress only if the source's definition confirms that sign. USD/VND is VND per USD, not an equity price. Negative rates are not globally invalid; validate documented source-specific bounds rather than silently clip economic values.

### Transparent stress and policy

For each eligible rate observation x, compute robust standardized level and change using a prior-only window (initial candidate: 60 valid observations with at least 40 prior values):

`z_x(t) = clip((x(t) - median(x_past)) / (1.4826 * MAD(x_past)), -5, 5)`

Zero/near-zero MAD or insufficient samples produces unavailable, with an explicit fixed floor only if source precision justifies one and it is preregistered. Define `delta_ON(t) = r_ON(t) - r_ON(t-5 eligible trading sessions)` in annual-decimal rate units; both endpoints must be eligible and within their source staleness limits. Stale observations are not five new samples. Define `spread(t) = r_ON(t) - r_1W(t)` using matched economic observation dates and eligible vintages for both tenors, never a future or silently carried counterpart. Standardize each of `r_ON`, `delta_ON` and `spread` separately with its own prior-only median/MAD history and the formula above. The initial stress index is the equal-weight mean of these three valid standardized components; require all three for the initial baseline. Do not dynamically reweight a partially missing index without a separate calibrated policy.

Proposed research policy, frozen before OOS: enter `STRESS` after two eligible batches with index >= 2; leave only after three with index < 1; `NORMAL` multiplier 1.0, `STRESS` multiplier 0.5. These values are hypotheses, not discovered facts or approved limits. Persistent state is versioned/replayable, not recalculated using future observations. A risk owner must ratify thresholds, allowed daily exposure changes and whether exceptional stress warrants zero new risk.

`final_target_exposure = base_target_exposure * liquidity_multiplier`, with `0 <= liquidity_multiplier <= 1`. The overlay cannot create leverage or override an existing veto, position, cash, settlement or liquidity limit. It is portfolio risk control; do not represent a macro warning as proven issuer fraud or an LLM hard veto.

Missing/delayed macro data yields `UNKNOWN`, not `NORMAL`. For the initial shadow policy, `UNKNOWN` blocks new/increased positions; any reduction/exit remains subject to market tradability and existing risk rules. Distinguish this from an outage in an optional sentiment provider, which can fall back to the approved quant-only baseline if the baseline's own inputs remain valid. Report stale age and the source-specific publication schedule; do not demand a new observation on a non-publication holiday.

### Acceptance evidence for future implementation

Percent/fraction equivalence, tenor isolation, zero MAD, non-finite value rejection, vintage correction replay, inclusive availability, stale-weekend handling, hysteresis reset/restart and exposure endpoints 0/1. Evaluate stress classification, turnover, drawdown and net return against no overlay and fixed conservative exposure. No assertion that rising rates mechanically cause a particular stock return or brokerage margin call.

## 7. Workstream D — PEAD Drift Engine

### Event identity and comparable actuals

PEAD requires an **actual earnings announcement**, not merely a financial article, fiscal-period end or statutory reporting deadline. Key by stable issuer, fiscal period, metric, accounting scope, first release and revision. Capture timestamp evidence and extraction readiness; conservative financial-loader embargoes may delay eligibility but cannot identify an earlier true announcement.

Begin with quarterly standalone diluted EPS or attributable profit on a consistently documented basis. Distinguish quarterly from year-to-date/cumulative figures; derive a standalone quarter only if both cumulative vintages were knowable and accounting definitions match. Do not mix consolidated/parent-only, audited/unaudited, net profit/attributable profit, currencies, share counts or split bases. For banks and other incomparable sectors, use explicitly typed metrics or exclude the baseline with a reason.

### Two non-interchangeable surprise variants

1. **Consensus SUE**: `SUE = (actual - consensus_pre_release) / sigma_prior_forecast_errors`. The consensus vintage must predate release, have known contributor/sample provenance and match metric/unit/fiscal scope. Estimate sigma from sufficient comparable past errors, never including the current surprise. If consensus or error history is absent, this variant is unavailable.
2. **Seasonal standardized earnings change**: `SEC = (actual_q - actual_q_minus_4) / sigma_prior_seasonal_changes`, using only historical comparable vintages and a preregistered minimum history (initial research proposal: 8 comparable changes). This is **not** consensus SUE and must be named/reported separately.

Zero/near-zero denominator, overflow, incompatible negative/positive EPS bases or missing comparables produces unavailable, not arbitrary epsilon division. Negative EPS itself is valid; avoid growth ratios divided by prior EPS around zero. Standard-deviation units must match numerator units. Clip standardized surprises under a frozen rule (initial proposal: [-5,5]); retain unclipped diagnostic values and reasons without publishing non-finite features.

At event age `a >= 0` completed eligible trading sessions, proposed drift feature `D_i(t) = clip(surprise_i, -5, 5) * 2^(-a/h_pead)` uses finite, strictly positive, preregistered half-life `h_pead > 0` during an explicitly bounded holding window. Reject negative/non-finite age and nonpositive/non-finite half-life; valid outputs satisfy `abs(D_i) <= 5`. Begin with one latest eligible earnings event per issuer; overlapping events replace the active event prospectively rather than add multiple positions. Restatements are separate revision events and cannot rewrite the original event's past signal or its labels. Missed or unknown announcement timestamps remain excluded from historical PEAD.

### Execution and validation

Entry is the first eligible executable session after release/readiness and the minimum T-1 policy, not the announcement-day close chosen with hindsight. Initial comparable research labels are 3/5/10 trading sessions; a separately registered 20/60-session drift study is allowed only with matching holding/capital constraints, overlap rules, longer purge/embargo and sufficient clean history. Zero-volume/limit-locked stocks produce missed/delayed fills, never invented entry prices.

Compare consensus SUE, seasonal change, earnings-news sentiment, combined direct-news/PEAD and quant-only controls. Separate earnings-day jump from post-entry drift; use issuer/date clustered or block-resampled inference. Earnings-only sentiment must be ablated so two features cannot claim independent alpha from the same disclosure. Minimum historical coverage and sample size are reported per variant; no PEAD claim from unavailable consensus.

## 8. Unified evaluation, costs and portfolio integration

### Hypotheses and splits

Register family, sign, universe rule, half-life, graph variant, macro policy, earnings metric, horizons and all trials before inspecting held-out performance. Freeze a final untouched chronological test interval determined by the intersection of clean PIT data, not by the OHLCV start date. Report when insufficient overlap prevents the proposed evaluation.

Use rolling/expanding strictly chronological train/validation/test deployment simulations. Fit scorer calibration, count baseline, graph weights, scalers, neutralization coefficients, thresholds, feature selection and ensemble weights only on the corresponding training/validation history. Refit only at scheduled boundaries; log artifact readiness. Keep connected syndicated events and earnings-event labels from crossing folds. Purge overlapping entry-to-exit intervals; embargo must cover the longest actual delayed-execution label horizon, not an unconditional three-day default. A 60-session PEAD trial requires its own enlarged gap and adequate data.

Existing purged/CPCV implementations require contract tests before reuse: a generic combinatorial split allowing later training blocks is not a chronological deployment backtest. CPCV is a separate robustness diagnostic, not proof a future-trained model was available historically. Count all attempted variants in multiplicity adjustments; retain negative results.

### Metrics and selection

- Per-session cross-sectional Spearman rank IC, mean, standard deviation, IC IR (`mean(IC)/std(IC)`), coverage and valid sample count for 3/5/10-session executable returns. Constant signal/return or undersized cross-section is undefined and excluded with a reason, not zero or an inflated IR fallback.
- HAC/block-bootstrap uncertainty for overlapping returns; issuer/date clustering for event panels; bootstrap/deflated Sharpe and BH-FDR at 5% across the registered hypothesis family. Do not use naive independent-observation t-statistics on overlapping event returns.
- Gross and net portfolio returns, net Sharpe/Sortino/drawdown, turnover convention, concentration, capacity, fill ratio, holding age, exposure, stale-data frequency and rejected events. Report per fold, venue, sector, size/liquidity bucket and available regime with sample counts.
- Gross IC is a correlation. **Do not subtract turnover times trading cost from IC**. Costs belong in the actual trade/cash ledger and resulting net returns; name any cost-sensitive ranking metric separately.
- Proposed screening goals, not achieved results: mean gross rank IC > 0.03, IC IR > 0.5 and positive incremental net OOS return versus quant-only. Final acceptance additionally requires uncertainty intervals, sufficient predeclared effective sample size, acceptable risk/capacity and independent L3 review; thresholds alone do not promote.

### Units, costs and tradability

Prices and order notionals use **VND_FULL** with explicit schema units; do not infer scale from `price > 1000` or multiply a normalized price twice. Volume is shares; `ADV_notional = trailing mean(price_VND * shares)` uses past eligible sessions. Large valid notionals may exceed 1e12 VND; apply field-specific limits and finite arithmetic rather than a universal numeric cap.

Reconcile existing cost modules before use. For the explicit baseline of **15 bps commission per side + 10 bps sell tax + 2 bps slippage per side**, a completed buy/sell round trip costs **44 bps**, not the legacy skill shorthand 27 bps. Book buy 17 bps and sell 27 bps separately; do not charge 44 bps on both legs. Use provider/broker/venue-dated costs where proven; spread/impact/participation and slippage stress are additional documented assumptions, not silently interchangeable models.

Define turnover explicitly: for a fully invested self-financing rebalance, one-way turnover is `0.5 * sum(abs(delta_weight))`; report buys, sells and cash-flow effects separately. Apply costs to executed not target orders. Candidate research ceilings: participation <= 10% trailing ADV, single-name target <= 5%, sector <= 25%, one-way daily turnover <= 30%; risk-owner ratification is required. Capacity must be computed from order weights and per-name participation budgets, not a dimensionally invalid formula.

Respect exchange/session-specific lots, tick sizes, limit bands, foreign room, listing changes, settlement cash/securities availability and special first-day rules. Settlement is a dated market rule, not a hardcoded universal T+2.5 assumption. Suspended/delisted names stay in historical valuation/risk records; exclude untradeable new orders. A terminal loss/liquidation value requires evidence; do not assign -100% to every delisting automatically. Corporate-action adjustments use only knowable vintages and do not retroactively supply future split information to features.

### Composition and failure precedence

Retain the quant-only result as immutable benchmark. Combine direct-news, spillover and PEAD through a small frozen/train-selected feature blend with bounded weights, validity masks and lineage; measure marginal contribution before adding complexity. A qualified quant score remains necessary for the existing hybrid path. Preserve capped LLM weight, confidence gating, null-quant semantics and original hard-veto precedence.

Apply validated risk constraints and the macro exposure multiplier after signal scoring, before executable order generation. An existing hard veto always dominates. Malformed/unverified input rejects the affected result; optional sentiment outage cannot silently become a confident neutral score. A missing earnings or graph source disables only its explicitly optional component; a missing required risk/price input blocks new risk. Preserve compatibility schemas and use shadow-only opt-in until separately authorized.

## 9. Reliability, security and bounded operation

- Read bounded regular files; strict UTF-8, explicit BOM/CRLF policy, exact schema/version and digest checks before mutation. Reject symlink/path escape, directory input, duplicate identities and conflicting revisions. Lexically sorted files alone do not establish chronology.
- Proposed initial batch ceilings: <= 4 GiB resident memory, <= 1 MiB text per article, <= 100,000 records per chunk and bounded sparse graph neighbors. Profile realistic workloads; report rejected/truncated coverage. No silent sample/top-N truncation in research.
- Immutable shards are written to unique same-filesystem temporary files, flushed/fsynced where supported, validated and atomically replaced. Publish the manifest last as the commit point. Readers see only committed checksummed partitions. Multi-file replacement is not a transaction without this manifest protocol.
- Failure before commit leaves prior valid manifest/data intact; clean only the publisher's own temporary files. Do not delete shared live data on rollback. Explicitly test Windows rename/handle behavior and directory durability limits; do not claim stronger crash durability than the platform demonstrates.
- Single-writer ownership/fencing per publication scope; bounded lock acquisition, stale-owner checks and worker isolation. A lease timeout alone cannot justify stealing a live lock. Restart replays by deterministic event/revision key; output is idempotent.
- Reuse existing provider/network safety boundaries: HTTPS allowlist, no userinfo, no private/special-use targets, approved DNS/IP handling with original-host TLS SNI, redirect revalidation, bounded response size/time/attempts and fail-closed exhaustion. No new arbitrary URL fetch path in the factor layer.
- Network retries are finite under attempt and elapsed-time budgets; 429 respects bounded backoff. Never poll orchestration status waiting for a task. Tests inject clocks/sleepers and do not wait on real provider/network retries.
- Prompts are bounded data-only extraction requests with schema validation. Redact credentials/URLs from logs, errors, reports, checkpoints and advisor contexts. No secrets in model identity, task routing or lineage. Run financial scoring locally unless external processing is separately permitted.
- Keep report/gate/session/model/role/context digests bound. Advisor advice is not independent L3 evidence. No permissive model/provider fallback for an unapproved risk tier.
- Observe record counts, source watermark/latency, duplicate/conflict rates, unavailable provenance, model version, coverage, macro age, factor bounds, memory/runtime, drift and rejected fills. Logs must distinguish partial batch, no-news and outage states.
- Recovery uses the last verified committed manifest and matching model/calendar/config versions; new evidence appends a new vintage. Retention honors source licensing and referenced-run reproducibility. Do not restore a checkpoint whose input digest differs.

## 10. Delivery sequence, ownership and measurable exits

Each package requires a separately scoped implementation authorization, exact changed-file map, related tests and independent L3 review. Estimates below are ordering guidance, not a promised deadline; elapsed research depends on proven data coverage.

| Package | Accountable role | Dependencies | Deliverable and exit check |
|---|---|---|---|
| P0 — inventory and contract freeze | 6 + 14 + 15 | None | Historical W0 inventory drift reconciliation (F-003) and original inventory regression pass; recount sources/events/eligible sessions; verify hashes, rights, clocks, units, calendar, model provenance and interfaces; publish missing-data matrix and frozen hypotheses |
| P1 — PIT ledger and serialization | 15, architecture review by 6 | P0 | TypeSafe JEV Scorer & Swappable Model Registry contracts below; immutable input/score vintages and unique issuer/decision panel; future-data, revision replay and crash tests pass; legacy consumers unchanged |
| P2 — direct-news baseline | 14 | P1 | TypeSafe JEV Scorer & Swappable Model Registry validation below; lexicon/pinned-scorer comparison, bounded decay/count surprise, training-only normalization; deterministic numerical, availability and model-swap tests; no graph or macro dependency |
| P3 — graph incremental baseline | 14 + 15 | P1, P2 | Dated edges, orientation/normalization tests, one-hop innovations and direct/sector/randomized graph ablations; unavailable historical graph explicitly excluded |
| P4 — macro overlay | 14 + risk owner | P1 | Typed eligible vintages, robust stress/hysteresis and unknown-state policy; bounded exposure and restart tests; no new HTTP path |
| P5 — earnings drift baseline | 14 + 15 | P1 | Actual release ledger, comparable actuals, separate SUE/SEC, event overlap and revision controls; coverage sufficient or PEAD explicitly research-blocked |
| P6 — unified OOS and shadow integration | 14 + 6 | P2–P5, or documented exclusion of optional stream | Chronological walk-forward, correct purging/cost ledger, complete trial registry, ablations, compatibility tests; shadow-only pipeline and operational runbook |
| P7 — final verification and L3 handoff | Implementers; independent L3 roles 17/18/21 as assigned | P6 | Scoped collection/focused/full-related runtime tests, including the P0 inventory regression and standing production boundaries; the separate planning gate uses only the dedicated master-plan suite in section 11; adversarial evidence, replay hashes, shadow results and rollback rehearsal; any required failure blocks completion; no live activation before independent decisions and gate enforcement |

P3 graph-input preparation may proceed after its P1 inputs exist, but does not complete P3. P3 acceptance requires P1 completion and successful P2 exit checks before validating one-hop innovations and direct/sector/randomized graph ablations. P4 and P5 can proceed independently after their own P1 inputs exist; P6 may evaluate a reduced baseline but must name excluded workstreams and cannot claim complete four-stream delivery. The critical path is source-vintage eligibility, then verified decision-panel lag, then OOS/shadow evidence. Missing historical data cannot be solved by additional model complexity.

Before a live request, propose at least 20 eligible shadow sessions with no missing mandatory risk controls, deterministic replay and no unexplained divergence. This is an operational minimum, not adequate statistical proof of alpha; effective sample size and untouched OOS history remain separate requirements. Risk owners define incident severity, stale thresholds and kill-switch policy before shadow start. Rollback disables only the new feature integration and restores the last independently accepted baseline/config; never deletes evidence or bypasses existing vetoes.

### P0 — historical inventory reconciliation (F-003)

Historical W0 inventory drift reconciliation is a blocking Package P0 deliverable, not a planning-gate prerequisite. P0 cannot complete and P1 cannot start until independently traceable source reconciliation and the original inventory regression pass. The required P0 regression is `tests/test_sod_jev_model_routing.py::test_w0_inventory_binds_sources_consumers_and_market_release`; do not delete, skip or weaken its assertions. Record per-source consumer bindings, row counts, hashes, release evidence and a reproducible reconciliation report under separately authorized data scope. The source audit identified row-count drift (macro news 0 expected / 250 current; sentiment history 988 expected / 23 current), not proof which inventory is correct; its current market hash matched. Do not guess counts/hashes or overwrite datasets/manifests to obtain green tests. F-003 data reconciliation remains OPEN until this evidence exists; the planning change corrects scope, not provenance.

### P1 — TypeSafe JEV Scorer & Swappable Model Registry

Existing seams are distinct: `src/omega/core/llm_config.py::classify_jev` provides categorical research-only decisions, `src/omega/data/llm_sentiment_scorer.py::LLMSentimentScorer.score` provides sentiment and lexicon fallback, and `src/omega/data/registry.py::ModelRegistry` manages versioned model artifacts. None establishes the proposed end-to-end TypeSafe JEV Scorer or runtime-swappable registry. Extend/reuse these only after package-specific contract tests; do not create a parallel model store or reuse the deprecated core registry. A typed categorical choice is not a scalar investment score: any choice-to-score mapping must be explicit, versioned and training-calibrated. Preserve research-only authority and existing behavior for legacy consumers; the new opt-in adapter must reject unsafe timestamp defaults, coercion and fallback rather than silently inherit them.

P1 defines a typed scorer boundary, not a second ingestion or orchestration stack. Reuse the existing sentiment-scoring seam; JEV dispatch/advisor routing is not financial sentiment inference. Specify strict request/result schemas and stable adapter contract before separate runtime implementation. Request identity binds event/revision/issuer, bounded text reference, input digest, evidence mode and decision cutoff. Result identity additionally binds registry snapshot, provider/model revision, prompt, schema, calibration and preprocessing versions; signed score [-1,1], confidence and attribution [0,1] must be finite, never booleans or coerced strings. Missing/extra fields, malformed identity or out-of-range results reject before persistence; explicit unavailable/error states carry reason codes, not a fabricated neutral score.

Swappable Model Registry entries pin immutable model revisions and artifact digests, supported language/task/schema capabilities, rights, training cutoff evidence and model_available_at. Configuration selects only an allowlisted compatible entry; reject unknown/disabled IDs, duplicate entries, incompatible schemas and digest mismatches. Resolve one immutable registry snapshot per run; a swap starts a new run/version, never mutates in-flight or historical scores. Cache/replay keys bind input, model, prompt, schema, preprocessing, calibration and registry digests. Define canonical digest serialization and effective-time fields before cache implementation; every cache hit revalidates the same schema, lineage, registry eligibility and readiness gates as a fresh result. No silent provider/model fallback; a separately authorized baseline is labeled as a distinct scorer/run. A present-day model with unknown training cutoff remains retrospective-only, never upgraded to verified historical deployment.

For every score, available_at = max(source_available_at, score_ready_at, model_available_at, calibration_available_at), with all required timestamps substantiated and UTC-aware; require as_of <= available_at <= decision_time plus the next eligible trading-session lag. Equality at the inclusive 15:30 ICT batch cutoff is allowed only when readiness and lag certificates hold. Future model/calibration evidence, missing readiness or caller-supplied provenance claims fail closed. Preserve immutable revisions, commit-manifest-last publication and legacy consumer contracts.

### P2 — TypeSafe JEV Scorer & Swappable Model Registry validation

P2 validates each pinned scorer against the frozen lexicon baseline on independently labeled Vietnamese issuer/event samples; calibration and model selection use training/validation only, never the untouched OOS interval. Compare identical eligible events, disclose coverage/latency/cost and unavailable outputs, then apply the existing bounded decay/count-surprise formulas. Registry-swap tests require stable result schema and score bounds, distinct lineage/cache identities and unchanged historical outputs; numerical equality across different models is not required.

Before P2 exit, inject None/empty/malformed payloads, bool/string scores, NaN/Inf/-Inf, overflow, zero/negative normalization denominators, missing/duplicate/unknown registry IDs, incompatible schemas, altered digests, provider timeout/429 exhaustion, unauthorized fallback, future timestamps and cutoff equality/+one-unit cases. Assert rejected results cannot publish scores, unavailable is not valid_no_news, model swaps cannot reuse stale cache or certify old data, and legacy quant-only/hard-veto behavior remains intact. Runtime crash/rollback, concurrent registry reload and publication failures require isolated tests under that package authorization; documentation tests do not implement or certify them.

## 11. Verification contract and 24-dimension adversarial matrix

This delivery edits only the master plan, its dedicated documentation tests and the L4 report; no production scorer, registry, dataset or manifest is changed. Planning-gate verification is limited to tests/test_master_plan_news_sentiment_macro_alpha.py. Collect every reported node, run focused new tests, then the entire dedicated suite; any collection error or test failure blocks this planning delivery. The validator checks section-local delivery/scorer/inventory contracts, malformed/missing/duplicate clauses, fail-closed CLI exits, encoding and the formula self-check. This is documentation evidence, not production alpha behavior, runtime registry certification or independent L3 approval. Future packages must add and collect their own scoped runtime fault-injection tests; do not run an unrelated repository-wide suite.

Current planning verification commands (replace `<implementation_session>` with the actual session ID; collect every additional reported node before execution):

```text
pytest --collect-only -o addopts="" --capture=sys -p no:terminal --junitxml=.ly_state/session/<implementation_session>_collect.xml tests/test_master_plan_news_sentiment_macro_alpha.py
pytest -o addopts="" --capture=sys -p no:terminal --junitxml=.ly_state/session/<implementation_session>_focused.xml tests/test_master_plan_news_sentiment_macro_alpha.py
pytest -o addopts="" --capture=sys -p no:terminal --junitxml=.ly_state/session/<implementation_session>_test.xml tests/test_master_plan_news_sentiment_macro_alpha.py
```

Historical W0 inventory checks are excluded from planning-gate execution and retained as mandatory P0 acceptance evidence. The original inventory test and mutable data/manifest inputs remain unchanged. F-003 remains OPEN as data reconciliation, not a blocker to this documentation-only verification boundary. A passing planning suite cannot satisfy P0 or authorize P1 implementation. Contract finding F-001 remains distinct: correct the fail-closed planning contract and enforce its tests; do not rename it F-003 or claim an audit finding closed by assertion.

| # | Dimension | Required future adversarial probe / expected behavior |
|---|---|---|
| 1 | Types and bounds | None, empty, bool-as-number, string/list, NaN/Inf/-Inf, overflowing score/rate; reject before persistence; field-specific valid large VND values retained |
| 2 | Paths and encoding | Directory/missing/symlink/path escape, invalid UTF-8, BOM and CRLF; reject or explicitly normalize by contract without digest ambiguity |
| 3 | Checkpoint integrity | Corrupt/duplicate/partial shard or wrong input hash; no state mutation; prior manifest remains valid |
| 4 | Fail-closed errors | Invalid source/provenance/schema and exhausted job return explicit non-zero; distinguish rejected data from optional unavailability |
| 5 | Atomicity and rollback | Inject write/fsync/replace/manifest failure; no partial publication; clean only owned temporary files |
| 6 | PIT and look-ahead | Equality cutoff, cutoff plus one unit, future article/edge/consensus/model, late revision, pre-batch feature; past panels unchanged; no caller provenance upgrade |
| 7 | Vietnam calendar | 15:30 ICT inclusive batch boundary, next session, Friday/holiday/Tet/closure, lunch/auction and venue rules; never calendar-day-shift blindly |
| 8 | Numeric correctness | Zero/negative denominator, zero variance/MAD, cancellation, huge/notional overflow, negative EPS/rate cases; unavailable or valid by field policy, never non-finite output |
| 9 | Worker concurrency | Two publishers, reordered shards, reused event ID and crash/restart; deterministic idempotence with owner isolation |
| 10 | VND_FULL and units | Equivalent percent/decimal and VND/thousand-VND fixtures normalize once; mismatched or absent units reject; ADV shares vs VND distinguished |
| 11 | Survivorship | Future listing, delisting, suspension, relisting, ticker reuse, historical sector change and corporate action; historical eligibility preserved |
| 12 | CLI/argument injection | Malicious issuer/provider/path/flag identifiers; allowlisted values and shell-safe argument arrays, no interpreted payload |
| 13 | Schema drift | Extra/missing/renamed columns, mutation after hashing, incompatible schema version; reject before joins or explicit versioned migration |
| 14 | Resource bounds | Oversized article/response, excessive shards/high-degree graph, compressed expansion and memory ceiling; bounded failure with visible coverage impact |
| 15 | Timeout/429 | Inject timeout/429/deadline exhaustion; bounded attempts, no partial commit, explicit unavailable/error state |
| 16 | Secret redaction | Userinfo, token query, provider error and article text containing credentials; no secrets/full sensitive URLs in artifacts or logs |
| 17 | Routing validation | Wrong role/risk/cycle/model-focus type/range; reject routing. Pipeline formulas have no routing implementation; reuse dispatcher tests for that boundary |
| 18 | Model allowlist | Cross-tier model/provider injection; reject non-allowlisted choice; scorer version pinned |
| 19 | Context/replay binding | Wrong gate/session/role/risk and reused request ID; reject mismatched/replayed decisions |
| 20 | Schema/digest integrity | Alter one byte/field, invalid canonical JSON, duplicate keys/non-finite JSON; digest/schema verification fails closed |
| 21 | Decision publication | Inject temporary-write/fsync/commit/cleanup failure in decision evidence; recover prior committed evidence, not partially written receipts |
| 22 | Lock ownership | Live/stale/foreign lock and concurrent evidence writers; ownership/fencing verified; no lock theft or cross-owner cleanup |
| 23 | Retry/fallback | Provider failure, retry exhaustion and unauthorized fallback tier; finite retries, approved low-risk fallback only, never manufacture successful alpha |
| 24 | Prompt routing safety | Article prompt injection, secret-bearing context, oversized payload; treat text as data, redact and bound before scorer/advisor routing |

Dimensions 17–24 partly concern existing routing/advisor infrastructure, not alpha formulas. Future runtime packages must prove integration preserves these boundaries rather than duplicate the framework. This planning delivery tests required documentation contracts only; the matrix is a future implementation obligation, not 24 dimensions of newly certified runtime behavior.

Additional numerical/metamorphic checks: half-life identity; duplicate invariance; edge permutation/orientation; graph row bound and innovation bounds; no-news/outage distinction; zero-MAD behavior and independently standardized tenor spread; multiplier monotonicity/bounds; equivalent-unit invariance; exact 17/27/44 bps cost cases; release-period vs announcement separation; future-data insertion invariance; consistent replay across chunk sizes. Statistical tests need reproducible seeds and frozen input hashes, not selected favorable examples.

### Runnable formula self-check

This stdlib check tests the documented identities and bounds only, not production alpha implementation or statistical performance. Run the following Python block as a standalone script; no source data or provider access is required.

```python
import math


def decay(age, half_life):
    if not all(math.isfinite(x) for x in (age, half_life)) or age < 0 or half_life <= 0:
        raise ValueError("invalid decay clock")
    return 2 ** (-age / half_life)


def clip(x, low, high):
    return max(low, min(high, x))


assert decay(3, 3) == 0.5
for age in (0, 1, 3, 60):
    for half_life in (1, 3, 5):
        mass = decay(age, half_life)
        news = mass / max(1, mass)
        pead = clip(100, -5, 5) * mass
        assert 0 <= news <= 1 and 0 <= pead <= 5
for age, half_life in ((-1, 1), (0, 0), (0, -1), (math.nan, 1), (0, math.inf)):
    try:
        decay(age, half_life)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid clock accepted")
raw = (2.0, -1.0)
weights = tuple(x / max(1, sum(map(abs, raw))) for x in raw)
for innovations in ((1, -1), (-1, 1), (100, -100), (0, 0)):
    propagated = sum(w * clip(e, -1, 1) for w, e in zip(weights, innovations))
    assert abs(propagated) <= 1 + 1e-12
assert math.isclose(4.25 / 100, 0.0425)
assert 15 + 2 == 17 and 15 + 10 + 2 == 27 and 17 + 27 == 44
print("Formula self-check: PASS")
```

### Standing regression classes retained at every handoff

1. Literal/legacy IPv4 denial.
2. IPv6-embedded IPv4 payloads.
3. Special-use address ranges.
4. Sparse configuration merge preservation.
5. Test-isolation snapshot restore.
6. Durable TLS SNI evidence.
7. Userinfo credential rejection.
8. URL redaction in errors.

The eight standing production-boundary classes remain mandatory runtime handoff evidence under P7 and any separately authorized source change. They are not planning-gate prerequisites. A supplemental standing-boundary rerun is reported separately, never conflated with the dedicated planning suite or evidence that W0 inventory is reconciled. Missing or failed runtime evidence blocks the relevant runtime package, not this document contract; no production approval is implied.

## 12. Evidence, unresolved decisions and independent handoff

### Bound planning evidence

- Graph evidence: `.ly_state/session/graph_evidence_l4_role6_news_sentiment_macro_alpha_plan_20261020.json`; SHA-256 `e0d41ca28a671af9b74f1721b52a62763cb4f628901afef4d37361d20301b0d9` verified before use. Commit `d8fd865f28cfbc9946dfb6bc4b433ba3e7b6eaf9` matches HEAD. Both scope targets are **not indexed**; one complete non-truncated impact batch with zero results is not proof of no dependencies. Manual scope sweeps supplement it.
- Pre-edit scope hashes: plan `b803bd3361244923e86835696abe9e13332dc44be6881448df4af7aedb280a3f`; dedicated tests `ff7dc5637c1e0d433eec0151b796474404a3f65028e1ab86eb49ab4ee65243d2`, matching the graph snapshot. Evidence sidecars are not edited.
- Remediation anti-drip contract: `.ly_state/session/anti_drip_contract_l4_role6_news_sentiment_macro_alpha_plan_20261020.json`; SHA-256 `e2e7fc7e32481cd2d70f22125885b26557f43f22f3ddc2a4b0fbe2c888e296d5`; required finding `F-001`, probe strings `[]`. Exactly one Root-Cause Architectural Sweep JSON appears in the L4 report. The source audit SHA-256 is `daa3dc81b01ac364817d8a96bbfff96cf678908c596cf6ec0ebfcac172892d86`; no contract, audit or gate artifact is edited.
- Architecture and correctness consultations use `cx/gpt-6-astra`, role 6, high risk, exact gate/session and `as_of_time=2026-10-20T02:19:16Z`. Responses are advisory only, not independent L3 evidence. Receipt identities/digests and limitations are recorded in the L4 report; later execution times do not extend source-observation availability.
- Repo-local role/skill provenance, forbidden-path metadata scan and actual verification appear in `.ly_state/session/l4_role6_news_sentiment_macro_alpha_plan_20261020.md`.

### Decisions still requiring evidence or owner selection

| Decision | Owner | Blocking effect |
|---|---|---|
| Clean news coverage and historical first-seen/archive proof | 15 | Blocks historical news alpha claims outside verified intersection |
| Historical graph dates, source permissions and edge weights | 15 + 14 | Blocks historical spillover; prospective-only mode remains possible |
| Macro units, publication schedules, vintages and stale limits | 15 + risk owner | Blocks calibrated macro stress and any live overlay |
| Actual earnings timestamps, consensus rights/history and accounting comparability | 15 + 14 | Blocks consensus PEAD where absent; seasonal baseline remains separately labeled |
| Exact alpha/risk API, existing lag chain and execution clock | 6 | Blocks integration and executable label alignment |
| Broker/venue cost, settlement and limit-rule versions | risk owner + implementer | Blocks credible net return/capacity and live readiness claims |
| Effective sample size/power, untouched test interval and trial budget | 14 | Blocks statistical promotion claims; never select a favorable short sample |
| Incident thresholds, live kill switch and promotion authority | risk owner + independent L3 | Blocks live activation regardless of backtest result |

### Completion boundary

This planning delivery is complete only when the plan and L4 report retain LF line endings and mandatory headers, P1/P2 typed scorer/registry contracts, P0-blocking W0 reconciliation, all four workstreams and 24 future dimensions, passing collection/focused/full dedicated planning-suite checks, and successful required advisor responses. F-003 remains OPEN data work assigned to P0; no counts, hashes or historical provenance are repaired by this delivery. Independent L3 decides the planning gate; this plan remains a **draft for independent L3 review**, with no gate/audit edits, enabled live pipeline or alpha-performance claim.
