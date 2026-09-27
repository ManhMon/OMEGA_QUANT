# W1 16-Dimension Compliance Evidence Matrix

| Dim | Dimension Name | Status | Evidence Details |
|---|---|---|---|
| 1 | Malformed types | Enforced | Strict type checking on envelope fields, enum membership validation, non-empty IDs. |
| 2 | Invalid I/O paths | Partial | Cache path rejects directories; caller controls location and parent directories are created. No traversal allowlist. |
| 3 | Corrupt checkpoints | Partial | Cached JSON and envelope metadata validated on read. No per-row digest or atomic temporary file replacement. |
| 4 | Fail-closed exits | Enforced | Invalid inputs and replay misses raise exceptions; callers own process exit codes. Transient retries exhaust with `RuntimeError`. |
| 5 | Rollback/atomicity | Partial | SQLite WAL short transactions commit usage charges before provider calls; provider errors retain charges. Competing same-key publications use INSERT OR IGNORE and validate the stored envelope. No atomic file replacement. |
| 6 | PIT/look-ahead | Enforced | `available_at <= as_of`; v2 live/selective rejects historical cutoff before provider; v2 cached and fresh `decided_at <= as_of`. Legacy v1 retains daily-key compatibility. |
| 7 | Trading calendar | Not applicable | Classifier accepts timestamps; upstream data source owns exchange calendar. |
| 8 | Numeric precision | Partial | Budget and cost inputs must be finite; SQLite REAL accounting has floating-point precision. No confidence or division here. |
| 9 | Concurrency | Partial | SQLite `BEGIN IMMEDIATE` is limited to maintenance, budget reservation and publication; provider calls hold no writer lock. Concurrent same-key cache requests share the first published decision when the second observes it, but overlapping misses may incur duplicate paid calls. |
| 10 | VND_FULL scale | Not applicable | Classifier does not transform prices; tests pass VND_FULL facts. |
| 11 | Survivorship | Not applicable | Classifier does not select a trading universe. |
| 12 | CLI injection | Not applicable | No CLI or subprocess execution; domain registry and identifiers are validated. |
| 13 | Schema drift | Enforced | Versioned envelope schemas (`v1` legacy / `v2` registered), unknown field rejection. |
| 14 | Resource bounds | Partial | 1 MiB request payload and 10,000 decision-row limit; no retention policy or process memory cap. |
| 15 | Network/429 | Enforced | At most two attempts with bounded timeout and fixed retry delay. |
| 16 | Secret rejection | Partial | Nested fact keys and recognizable secret values are rejected before provider and cache access. No general-purpose redaction of arbitrary opaque credentials or provider exception text. |
