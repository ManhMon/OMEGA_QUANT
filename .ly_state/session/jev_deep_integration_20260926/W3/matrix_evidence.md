# W3 24-Dimension Compliance Evidence Matrix

Current verified coverage: scoped corporate-action PIT, production pipeline replacement rollback, micro-LLM retry bounds, news/forensic tests. `pytest -q tests/test_data_loader_corporate_action_pit.py tests/test_data_corporate_action_pit.py tests/test_jev_event_forensics.py tests/test_micro_llm.py tests/test_news_aggregator.py tests/test_news_aggregator_scrapers.py`: **194 passed, 12 warnings in 13.87s**. Remaining historical status labels are claims, not verified controls; untested dimensions remain **Unverified**.

| Dim | Dimension Name | Status | Evidence Details |
|---|---|---|---|
| 1 | Malformed types | Enforced | `math.isfinite` guards on dividend, split, and rights parameters; strict typing on `SentimentInput` and `CorporateAction`. Tested in `test_f003_nonfinite_and_calendar_rejections`. |
| 2 | Invalid I/O paths | Enforced | Micro LLM and news caching reject directory targets; temp files placed in same parent directory before atomic replacement. |
| 3 | Corrupt checkpoints | Enforced | Stored news JSON payload includes SHA-256 digest verified before deserialization; missing digest, corrupt or schema-mismatched records fail closed. Committed generation manifest binds data and report SHA-256; tampered artifact bytes or absent digest fail closed for both pair readers. |
| 4 | Fail-closed exits | Partially verified | Falsey malformed forensic `as_of` and `events` rejected; invalid prior news history rejected; missing time/basis rejected; tests exercise staging fsync failure. Mixed/all-failed micro-LLM batches raise before publication. Other exit paths unverified. |
| 5 | Rollback/atomicity | Partially verified | Manifest sync failure restores the previous pointer and legacy pair; first publication removes pointer. Restore-failure backups retained. `read_legacy_output_pair` now reads the committed generation; direct file readers remain outside this contract. |
| 6 | PIT/look-ahead | Enforced | Naive corporate-action query timestamps localized to ICT then UTC; both production pipelines compare ex-date to ICT day across 17:00 UTC midnight boundary; same-day dividend only applied after availability. Caller-provided news history requires published timestamp <= available_at and key equal event identity; future valid history filtered. |
| 7 | Trading calendar | Enforced | `VNTradingCalendar.is_trading_day` validates Vietnam statutory holidays, Tet, and exchange closures. Tested in `test_closed_calendar_fails`. |
| 8 | Numeric precision | Enforced | Non-finite values rejected (`math.isfinite`); adjustment factor preserves numeric precision; zero-division prevented. |
| 9 | Concurrency | Partially verified | Both pair readers resolve the same committed manifest under the writer FileLock; fault injection checks the legacy reader during first-file replacement. Independent direct reads of legacy files remain unsafe. |
| 10 | VND_FULL scale | Enforced | Dividend amounts verified in VND_FULL scale; backward adjustment factor maintains relative price ratio without unit distortion. |
| 11 | Survivorship | Enforced | Shadow forensic evaluation operates counterfactually without production vetoes; handles delisted/frozen tickers safely. |
| 12 | CLI injection | Not applicable | No shell execution sinks; all inputs parsed as domain models. |
| 13 | Schema drift | Partially verified | Explicit `price_basis: raw|adjusted` validation prevents double adjustment in scoped pipeline test. Other schemas unverified. |
| 14 | Resource bounds | Partially verified | Uncached micro-LLM coroutines dispatched in batches of at most `max_concurrency` (<=5); completed result rows and input dataframe remain proportional to input size. |
| 15 | Network/429 | Partially verified | Micro LLM max_retries constrained to 1–5; exhausted inference failures abort batch without publishing partial results. News ingestion retry behavior unverified. |
| 16 | Secret redaction | Enforced | Sensitive credentials stripped before logging; no API keys written to event stores. |
| 17 | JEV routing input validation | Not applicable | Upstream JEV routing; outside scoped diff. |
| 18 | Model catalog allowlisting | Not applicable | Upstream model catalog; outside scoped diff. |
| 19 | Decision context binding | Not applicable | Upstream decision envelopes; outside scoped diff. |
| 20 | Decision schema & digest | Not applicable | Upstream decision digests; outside scoped diff. |
| 21 | Publication durability | Partially verified | Manifest backup fsynced before replacement; `committed` only after parent sync; sync failure restores prior pointer and legacy files. Pair readers fail closed without a committed manifest; direct unlocked legacy file reads and crash-interrupted rollback remain unverified. |
| 22 | Decision lock ownership | Not applicable | Upstream decision locks; outside scoped diff. |
| 23 | Provider fallback safety | Enforced | Bounded retry and safe fallback without lookahead contamination. |
| 24 | JEV secret-safe routing | Not applicable | Upstream prompt routing; outside scoped diff. |
