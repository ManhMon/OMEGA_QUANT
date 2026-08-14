**Required Amendments**
1. Define provider-specific completeness modes: cursor token, authoritative numbered pages, explicit single-envelope terminal, immutable HTML snapshot. Pin adapter versions and source.
2. Use current release_id for artifact membership; add immutable origin_release_id or first_seen_release_id.
3. Separate receipt_sha256, canonical record-evidence hash, provider revision key, and deterministic serialization.
4. Include source in revision-stream identity. Add explicit canonical-provider reconciliation output.
5. Add derived-record schema: exact metric_id, formula ID/version, ordered parent lineage, lineage hash, source/revision semantics.
6. Make pointer CAS the publication authority. Keep manifest state validated/sealed; record activation in pointer and attempt ledger.
7. Specify first-generation sentinel, --output compatibility/export behavior, legacy reader transition, rollback floor.
8. Name the forecast module/function and its tests.
9. Replace verification prose with:
   - python -m pytest tests/test_fetch_financial_statements.py tests/test_macro_pipeline.py tests/test_financial_loader.py tests/test_macro_micro_release.py -q
   - python .agents/scripts/checklist.py . --skip-performance
   - python scripts/sod_gate_enforcer.py
10. Repair gate metadata and make post-cutoff missing fields hard-blocking independent of a discoverable strict gate.
