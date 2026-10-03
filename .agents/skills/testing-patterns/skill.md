---
name: testing-patterns
description: Testing patterns and principles. Unit, integration, mocking strategies.
when_to_use: "When writing unit tests, integration tests, choosing testing frameworks, or implementing mocking strategies."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Testing Patterns

> Principles for reliable test suites.

---

## 1. Testing Pyramid

```
        /\          E2E (Few)
       /  \         Critical flows
      /----\
     /      \       Integration (Some)
    /--------\      API, DB queries
   /          \
  /------------\    Unit (Many)
                    Functions, classes
```

---

## 2. AAA Pattern

| Step | Purpose |
|------|---------|
| **Arrange** | Set up test data |
| **Act** | Execute code under test |
| **Assert** | Verify outcome |

---

## 3. Test Type Selection

### When to Use Each

| Type | Best For | Speed |
|------|----------|-------|
| **Unit** | Pure functions, logic | Fast (<100ms) |
| **Integration** | API, DB, services | Medium |
| **E2E** | Critical user flows | Slow |

---

## 4. Unit Test Principles

### Good Unit Tests

| Principle | Meaning |
|-----------|---------|
| Fast | < 100ms each |
| Isolated | No external deps |
| Repeatable | Same result always |
| Self-checking | No manual verification |
| Timely | Written with code |

### What to Unit Test

| Test | Don't Test |
|------|------------|
| Business logic | Framework code |
| Edge cases | Third-party libs |
| Error handling | Simple getters |

---

## 5. Integration Test Principles

### What to Test

| Area | Focus |
|------|-------|
| API endpoints | Request/response |
| Database | Queries, transactions |
| External services | Contracts |

### Setup/Teardown

| Phase | Action |
|-------|--------|
| Before All | Connect resources |
| Before Each | Reset state |
| After Each | Clean up |
| After All | Disconnect |

---

## 6. OMEGA 24-Dimension Adversarial Matrix

For relevant OMEGA changes, select adversarial cases across all applicable dimensions; do not silently omit a dimension touched by the change. Test boundary behavior and failure states, not implementation details.

| # | Dimension | Adversarial test focus |
|---|-----------|-----------------------|
| 1 | Malformed/out-of-bounds types | NaN, Inf, strings, lists, and bounded-input validation |
| 2 | Invalid/directory I/O paths | Regular-file checks; strict UTF-8, BOM, and CRLF handling |
| 3 | Corrupted/duplicate/partial checkpoint shards | Verify integrity before mutating state |
| 4 | Fail-closed exit codes and errors | Fail non-zero; never continue silently |
| 5 | Rollback and atomicity | Atomic replacement, rollback, and durability failures |
| 6 | PIT and look-ahead safety | Enforce `as_of <= available_at <= decision_time`; reject future-available observations and test the inclusive equality boundaries in a consistent UTC/ICT timezone |
| 7 | Trading calendar and holidays | Vietnam exchange sessions, holidays, and closures |
| 8 | Numeric precision and zero division | Finite arithmetic, overflow, precision, and zero guards |
| 9 | Concurrency and races | Lock ownership, worker isolation, and race safety |
| 10 | `VND_FULL` scale and unit invariance | Dong-scale consistency; reject thousand-dong confusion |
| 11 | Survivorship and delisting | Delisted/frozen instruments without look-ahead |
| 12 | CLI injection and flag smuggling | Allowlisted identifiers and shell-safe arguments |
| 13 | Schema drift and column mutation | Strict schemas and immutable contracts |
| 14 | Resource exhaustion and memory bounds | Bound input, response, and memory use |
| 15 | Network timeout and 429 exhaustion | Bounded retries; safe provider failure |
| 16 | Secret redaction | Prevent credential leakage in logs, reports, and artifacts |
| 17 | JEV routing input validation | Validate role, risk, cycle, and model-focus types/ranges |
| 18 | Model catalog and cross-tier allowlisting | Enforce role-specific lead/subagent choices |
| 19 | Decision context binding and replay | Bind gate, role, risk, and session |
| 20 | Decision schema and digest integrity | Exact fields, canonical bytes, SHA-256 verification |
| 21 | Decision publication durability and rollback | Temporary-file fsync, atomic replace, and cleanup |
| 22 | Decision lock ownership and concurrency | Live/stale owner checks; concurrent publisher isolation |
| 23 | Provider retry and fallback safety | Bound timeout/429 retries; allow fallback only for approved low-risk cases |
| 24 | JEV secret-safe prompt routing | Sanitize task context; keep routing evidence credential-safe |

### Anti-Polling and Retry Tests

- Never poll or repeatedly invoke status, task-status, or gate-enforcer commands while waiting for background completion. Use one completion signal; otherwise stop and yield.
- For application-level provider retry behavior, use finite attempt/deadline bounds and backoff; verify exhaustion returns an explicit failure. This is not permission for orchestration/status polling.
- Test timing with a fake clock or injected sleeper; tests must terminate deterministically without real-time polling loops.

---

## 7. Mocking Principles

### When to Mock

| Mock | Don't Mock |
|------|------------|
| External APIs | The code under test |
| Database (unit) | Simple dependencies |
| Time/random | Pure functions |
| Network | In-memory stores |

### Mock Types

| Type | Use |
|------|-----|
| Stub | Return fixed values |
| Spy | Track calls |
| Mock | Set expectations |
| Fake | Simplified implementation |

---

## 8. Test Organization

### Naming

| Pattern | Example |
|---------|---------|
| Should behavior | "should return error when..." |
| When condition | "when user not found..." |
| Given-when-then | "given X, when Y, then Z" |

### Grouping

| Level | Use |
|-------|-----|
| describe | Group related tests |
| it/test | Individual case |
| beforeEach | Common setup |

---

## 9. Test Data

### Strategies

| Approach | Use |
|----------|-----|
| Factories | Generate test data |
| Fixtures | Predefined datasets |
| Builders | Fluent object creation |

### Principles

- Use realistic data
- Randomize non-essential values (faker)
- Share common fixtures
- Keep data minimal

---

## 10. Best Practices

| Practice | Why |
|----------|-----|
| One assert per test | Clear failure reason |
| Independent tests | No order dependency |
| Fast tests | Run frequently |
| Descriptive names | Self-documenting |
| Clean up | Avoid side effects |

---

## 11. Anti-Patterns

| ❌ Don't | ✅ Do |
|----------|-------|
| Test implementation | Test behavior |
| Duplicate test code | Use factories |
| Complex test setup | Simplify or split |
| Ignore flaky tests | Fix root cause |
| Skip cleanup | Reset state |

---

> **Remember:** Tests are documentation. If someone can't understand what the code does from the tests, rewrite them.
