# News Sentiment, Graph, Macro & PEAD: P7 Verification and L3 Handoff

## Scope and authority

Gate: `GATE_NEWS_SENTIMENT_MACRO_ALPHA_P7_HANDOFF_20261020`.
Session: `l4_role6_p7_handoff_rem1_20261021`. L4 implementation only; independent L3 review remains pending. No gate approval, deployment, broker activation or observed alpha performance is asserted.

Authorized remediation targets are this runbook, `tests/test_news_sentiment_macro_p7_handoff.py` and `src/omega/data/macro_pipeline.py`. Execution results belong in `.ly_state/session/l4_role6_p7_handoff_rem1_20261021.md`; commands below are reproduction instructions, not assertions of success.

## Public seams and provenance limits

| Component | Public seam | Boundary |
|---|---|---|
| Scorer | `src/omega/data/llm_sentiment_scorer.py::TypeSafeJEVScorer` | P7 injects a local deterministic responder and synthetic registry; no live provider or certified artifact history. |
| Direct news | `src/omega/quant/signal/sentiment_alpha.py::direct_news_features` | Caller supplies completed-session ages; output remains historically ineligible. |
| Spillover | `src/omega/quant/signal/sentiment_alpha.py::ecosystem_sentiment_spillover` | Supplied directed edges, one-hop propagation, lagged availability. Caller coverage assertions do not certify graph history. |
| Macro | `src/omega/data/macro_pipeline.py::MacroDataPipeline.query_as_of` | Both availability and ingestion clocks constrain eligible vintages. No macro-to-multiplier policy is established by P7. |
| PEAD | `src/omega/data/earnings_ledger.py::EarningsLedger`; `src/omega/quant/strategy/pead_drift.py::PEADDriftEngine` | Unverified announcement remains unavailable, not a zero surprise. |
| Blend | `src/omega/quant/strategy/unified_alpha_evaluator.py::blend_features` | Exact ordered symbols/schema, aware PIT clocks, missing-stream masks, no missing-weight renormalization. |
| Shadow | `src/omega/pipeline/shadow_pipeline.py::ShadowPipeline` | Disabled default; replay/shadow research is not live activation. |

P7 assembles fixture outputs explicitly; no joined four-stream production path is claimed. The macro multiplier `0.5` is a fixture constant, not inferred from CPI or a calibrated policy. JEV/direct-news/spillover historical eligibility stays false. Fixture prices are not evidence of `VND_FULL` ingestion certification. SBV session/release defaults are not verified source-release timestamps; do not use them to certify historical availability.

The launch graph evidence is SHA-bound but both targets are unindexed. Zero reported impact is not proof of absent dependencies; direct source and test discovery remains necessary.

## Mixed-precision remediation

The original focused run failed on valid whole-second and fractional-second ISO8601 values before vintage filtering. Shared `_timestamp_column` now uses explicit `format="ISO8601"`, `utc=True`, `errors="raise"` and rejects parsed `NaT`. All four persisted clocks use this boundary during validation; queries retain inclusive availability and ingestion cutoffs. pandas 2.3.3 is the verified runtime; older pandas compatibility is not claimed.

The original future-vintage probes remain intact. Precision parameter IDs are bound directly to `pytest.param` values, preserving collected node IDs. Added probes cover both row orders, UTC/ICT equivalence, datetime64 and Timestamp inputs, all four clocks, nanosecond exclusion, invalid/null timestamps, write validation, idempotent revisions and publication rollback. No fixture-only normalization or `xfail` conceals the production defect. Execution outcomes and any remaining blockers are recorded in the remediation report; independent L3 review remains required.

## Verification coverage

P7 uses offline, deterministic inputs and isolated temporary parquet storage. It covers real scorer/direct-news/graph/PEAD/macro/blend seams, exact cutoff equality, one-microsecond future availability/ingestion, UTC/ICT equivalence, unavailable PEAD, unknown news, valid zero versus None/NaN, schema/index faults, non-finite/overflow inputs, repeatability and input immutability. No network or model-provider call is required by these fixtures.

### Related suites

- Source ledger/news: `tests/test_macro_news_pipeline.py`, `tests/test_news_aggregator.py`, `tests/test_news_aggregator_scrapers.py`.
- Scorer/direct news: `tests/test_llm_sentiment_scorer.py`, `tests/test_sentiment_alpha_opt.py`, `tests/test_sentiment_dual_engine.py`, `tests/test_sentiment_blend.py`, `tests/test_sentiment_loader.py`.
- Macro: `tests/test_macro_pipeline.py`, `tests/test_macro_rates.py`, `tests/test_macro_features.py`.
- Graph: `tests/test_quant_network_graph.py`, `tests/phase7/test_graph_bootstrap.py`, `tests/phase7/test_graph_materialize.py`.
- PEAD: `tests/test_pead_drift.py`.
- Blend/shadow: `tests/test_news_sentiment_macro_shadow.py`.
- Cross-boundary/regressions: `tests/api/test_phase4_macro_news_contracts.py`, `tests/test_validation_consolidation.py`.
- Routing/advisor, not alpha-formula certification: `tests/test_sod_jev_model_routing.py`, `tests/test_l4_mcp_advisor.py`.

### 24-dimension adversarial map

These are test-suite pointers, not claims that a fixture certifies production data or deployment. The report and XML distinguish executed, failed and skipped cases.

| # | Dimension | Verification boundary |
|---|---|---|
| 1 | Malformed types/bounds | P7 rejection parameters; scorer and sentiment-alpha suites. |
| 2 | Paths/UTF-8/BOM/CRLF | News-pipeline, macro-rates and PEAD suites; P7 uses isolated parquet. |
| 3 | Corrupt/duplicate checkpoint | News-pipeline and macro-rates suites. |
| 4 | Fail-closed errors | P7 clock/schema rejection; news-pipeline failure branches. |
| 5 | Atomicity/rollback | News-pipeline, PEAD and shadow suites. |
| 6 | PIT/look-ahead | P7 inclusive cutoff/future vintages/UTC equivalence; macro and PEAD suites. |
| 7 | Calendar/holidays | Macro-rates, macro-pipeline and PEAD suites. |
| 8 | Precision/zero/overflow | P7 NaN/Inf/huge integer and valid-zero masks; sentiment-alpha and macro-rates suites. |
| 9 | Concurrency/races | News-pipeline, PEAD and shadow suites. |
| 10 | VND scale | Validation-consolidation and quant-network-graph suites; no P7 unit certification. |
| 11 | Survivorship/delisting | Quant-network-graph and validation-consolidation suites. |
| 12 | CLI injection | Validation-consolidation and routing suites; no P7 CLI added. |
| 13 | Schema drift | P7 exact columns/duplicate/reordered symbols; shadow suite. |
| 14 | Resource bounds | Sentiment-alpha and validation-consolidation suites; tiny bounded fixtures. |
| 15 | Timeout/429 exhaustion | News-pipeline and advisor suites; no live request needed. |
| 16 | Secret redaction | Validation-consolidation, news-pipeline and advisor suites. |
| 17 | Routing validation | Routing/advisor suites; no routing implementation changed. |
| 18 | Model allowlists | Routing/advisor suites; synthetic registry is not production model approval. |
| 19 | Context/replay binding | Routing/advisor suites; session/gate-bound advisory receipts. |
| 20 | Schema/digest integrity | Routing/advisor suites; launch graph/contract digests verified separately. |
| 21 | Publication durability | Routing/advisor suites; P7 adds no decision publisher. |
| 22 | Lock ownership | Routing/advisor suites; platform-specific skips must remain explicit. |
| 23 | Retry/fallback | Routing/advisor and shadow suites; no high-risk fallback authorization. |
| 24 | Secret-safe prompts | Routing/advisor suites; no credentials in fixtures or handoff. |

### Eight standing regressions

Run all `test_regression_01_*` through `test_regression_08_*` in `tests/test_validation_consolidation.py`: literal IPv4, embedded IPv4, special-use ranges, sparse configuration, snapshot restore, TLS verification, userinfo rejection and URL redaction.

The names alone do not establish exhaustive coverage: the IPv4 test does not cover every legacy numeric spelling; the TLS test checks certificate/hostname policy, not an observed live handshake. Supplement with `tests/test_macro_news_pipeline.py::test_cafef_timestamp_rejects_malformed_or_untrusted_url`, `test_cafef_dns_special_use_and_embedded_ipv4_denied`, `test_cafef_tls_pinning_retains_original_sni` and `test_cafef_response_and_detail_faults_fail_closed`. Mocked SNI forwarding plus certificate-policy assertions are offline evidence only.

## Reproduction

From the repository root, use safe Windows pytest flags for every invocation:

```powershell
pytest -o addopts="" --capture=sys -p no:terminal --junitxml=.ly_state/session/l4_role6_p7_handoff_rem1_20261021_test.xml --collect-only tests/test_news_sentiment_macro_p7_handoff.py
pytest -o addopts="" --capture=sys -p no:terminal --junitxml=.ly_state/session/l4_role6_p7_handoff_rem1_20261021_test.xml tests/test_news_sentiment_macro_p7_handoff.py
```

Preserve failed-run XML before rerunning. Collect every named related suite before its execution; record exact node IDs, exit codes, failures and skips. Do not replace a failing result with an unqualified pass statement. Run the related suites above, not the entire repository.

## L3 handoff checklist

1. Confirm graph/contract hashes and unchanged governance artifacts. Baseline contract has no required finding IDs; create no Root-Cause Architectural Sweep JSON.
2. Review all three scoped diffs, preserved failing macro evidence, regression collection and execution evidence, all eight standing regressions, 24-dimension applicability and advisor receipts.
3. Independently assess the shared timestamp fix and fail-closed behavior. No self-approval, gate metadata edits or live activation by L4.
4. Independent L3 roles own findings and disposition. Passing synthetic tests alone cannot establish verified historical coverage or readiness.
