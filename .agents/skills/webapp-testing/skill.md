---
name: webapp-testing
description: Web application testing principles. E2E, Playwright, deep audit strategies.
when_to_use: "When writing E2E tests with Playwright, performing deep web app audits, or testing user flows. Use with /test workflow."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Web App Testing

> Map the agreed test scope; cover critical routes and user-visible behavior without expanding into unrelated systems.

## 🔧 Runtime Scripts

**Execute these for automated browser testing:**

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/playwright_runner.py` | Basic browser test | `python scripts/playwright_runner.py https://example.com` |
| | With screenshot | `python scripts/playwright_runner.py <url> --screenshot` |
| | Accessibility check | `python scripts/playwright_runner.py <url> --a11y` |

**Requires:** `pip install playwright && playwright install chromium`

---

## 1. Deep Audit Approach

### Discovery First

| Target | How to Find |
|--------|-------------|
| Routes | Scan app/, pages/, router files |
| API endpoints | Grep for HTTP methods |
| Components | Find component directories |
| Features | Read documentation |

### Systematic Testing

1. **Map** - List all routes/APIs
2. **Scan** - Verify they respond
3. **Test** - Cover critical paths

---

## 2. Testing Pyramid for Web

```
        /\          E2E (Few)
       /  \         Critical user flows
      /----\
     /      \       Integration (Some)
    /--------\      API, data flow
   /          \
  /------------\    Component (Many)
                    Individual UI pieces
```

---

## 3. E2E Test Principles

### What to Test

| Priority | Tests |
|----------|-------|
| 1 | Happy path user flows |
| 2 | Authentication flows |
| 3 | Critical business actions |
| 4 | Error handling |

### E2E Best Practices

| Practice | Why |
|----------|-----|
| Use data-testid | Stable selectors |
| Wait for elements | Avoid flaky tests |
| Clean state | Independent tests |
| Avoid implementation details | Test user behavior |

---

## 4. Playwright Principles

### Core Concepts

| Concept | Use |
|---------|-----|
| Page Object Model | Encapsulate page logic |
| Fixtures | Reusable test setup |
| Assertions | Built-in auto-wait |
| Trace Viewer | Debug failures |

### Configuration

| Setting | Recommendation |
|---------|----------------|
| Retries | 2 on CI |
| Trace | on-first-retry |
| Screenshots | on-failure |
| Video | retain-on-failure |

---

## 5. Visual Testing

### When to Use

| Scenario | Value |
|----------|-------|
| Design system | High |
| Marketing pages | High |
| Component library | Medium |
| Dynamic content | Lower |

### Strategy

- Baseline screenshots
- Compare on changes
- Review visual diffs
- Update intentional changes

---

## 6. API Testing Principles

### Coverage Areas

| Area | Tests |
|------|-------|
| Status codes | 200, 400, 404, 500 |
| Response shape | Matches schema |
| Error messages | User-friendly |
| Edge cases | Empty, large, special chars |

---

## 7. Test Organization

### File Structure

```
tests/
├── e2e/           # Full user flows
├── integration/   # API, data
├── component/     # UI units
└── fixtures/      # Shared data
```

### Naming Convention

| Pattern | Example |
|---------|---------|
| Feature-based | `login.spec.ts` |
| Descriptive | `user-can-checkout.spec.ts` |

---

## 8. CI Integration

### Pipeline Steps

1. Install dependencies
2. Install browsers
3. Run tests
4. Upload artifacts (traces, screenshots)

### Parallelization

| Strategy | Use |
|----------|-----|
| Per file | Playwright default |
| Sharding | Large suites |
| Workers | Multiple browsers |

---

## 9. Anti-Patterns

| ❌ Don't | ✅ Do |
|----------|-------|
| Test implementation | Test behavior |
| Hardcode waits | Use auto-wait |
| Skip cleanup | Isolate tests |
| Ignore flaky tests | Fix root cause |

---

## 10. Accessibility, Responsive, and Performance Coverage

- Test keyboard-only operation, semantic roles/names/states, focus visibility and order, validation/error announcements, contrast, reduced motion, and at least one supported screen reader. Automated scans supplement, not replace, manual checks.
- Exercise representative narrow, tablet, and desktop viewports; orientation, zoom/reflow, long content, and touch/keyboard input. Assert content and controls remain usable, not pixel-identical.
- Add performance checks only for agreed budgets and stable signals. Prefer measured LCP, INP, and CLS evidence; avoid brittle timing assertions in shared CI.
- Validate the app framework, Playwright package, browser binaries, and plugins against manifests/lockfiles before choosing APIs or configuration. Use version-matched documentation and the project's supported browsers; do not assume the newest release.
- Prefer accessible role/label locators; use `data-testid` only when user-facing semantics cannot identify the target. Keep tests isolated, bounded, and deterministic.

## 11. OMEGA 24-Dimension Review

Before handoff, review all 24 OMEGA adversarial dimensions in [testing-patterns](../testing-patterns/skill.md). For each, record an applicable adversarial case and result, or mark not applicable with a concrete reason. Exercise dimensions that affect the tested web surface (including malformed inputs, error states, schema boundaries, secrets, resource limits, and concurrency when present); do not claim unrelated trading or provider dimensions were runtime-tested by UI tests.

---

> **Remember:** E2E tests are expensive. Use them for critical paths; use component and integration tests for the rest.
