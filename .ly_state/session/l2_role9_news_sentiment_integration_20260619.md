# L2 Implementation Report - Role 9 (Backend Engineer)

**Gate:** NEWS_SENTIMENT_INTEGRATION_20260619
**Date:** 2026-06-19
**Status:** COMPLETE - Submit to Tier 3

---

## Agent Compliance Report

### Repo-Local Files Read (Authoritative)
| File | Purpose |
|------|---------|
| `.agents/agent/backend-engineer.md` | Role definition (role_id: 9, tier: 2) |
| `.agents/skills/clean-code/SKILL.md` | Coding standards (declared skill) |
| `.agents/skills/testing-patterns/SKILL.md` | Test patterns (declared skill) |
| `.agents/skills/systematic-debugging/SKILL.md` | Debugging methodology (declared skill) |

### Forbidden Path Scan
| Path | Status |
|------|--------|
| `C:\Users\GHC\.agents\` (non-authoritative, not accessed) | **EXISTS** - contains `skills/` subdirectory |
| Antigravity scratch | Not scanned (not referenced) |
| OpenClaw | Not scanned (not referenced) |
| Codex memory | Not scanned (not referenced) |

**Result:** `C:\Users\GHC\.agents` (non-authoritative) exists but was NOT used. All skills loaded exclusively from `REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`.

---

## Scope Files Modified

| File | Action |
|------|--------|
| `src/omega/data/news_aggregator.py` | REFACTORED - Full rewrite of scrapers |
| `scripts/run_sentiment_enrichment.py` | UPDATED - Added CLI args, hours_back=240 |
| `tests/test_news_aggregator.py` | REWRITTEN - 17 tests, all passing |

---

## Changes Summary

### 1. CafeF Scraper (`_scrape_cafef`)

**Problem:** Old selectors (`h3 class="title"`, `span class="time"`) no longer match current CafeF HTML structure.

**Solution:**
- **Primary:** RSS feed at `https://cafef.vn/thi-truong-chung-khoan.rss` — structured XML with `<item>`, `<title>`, `<pubDate>` (RFC 2822). Reliable and covers multiple days.
- **Fallback:** HTML scraping with updated selectors:
  - Featured: `div.firstitem h2 a` + `p.time[data-time]` (format `DD/MM/YYYY - HH:MM`)
  - Stream: `div.tlitem h3 a` + `span.time.time-ago[title]` (ISO 8601)
- **Timezone:** RSS pubDates converted to Vietnam time (+0700) before stripping tzinfo, ensuring consistent comparison with naive `as_of_time`.

### 2. Vietstock Scraper (`_scrape_vietstock`)

**Problem:** Old URL `https://vietstock.vn/thi-truong-chung-khoan` returns 404. Old selectors (`div class="news-item"`, `h3/h4`) no longer match.

**Solution:**
- **URL:** Changed to `https://vietstock.vn/chung-khoan.htm` (current canonical URL).
- **Selectors:** `div.channelContent` containers, `h4 a.fontbold` for headlines (using `title` attribute), `div.meta3 a:last-child` for timestamps.
- **Time formats:** Handles `DD/MM HH:MM` (short), `X phút trước`, `X giờ trước` (relative).

### 3. `run_sentiment_enrichment.py`

- **CLI argument:** `--hours-back` with default 240 (10 days).
- **Removed:** Duplicate imports, redundant path setup.
- **Added:** Proper `SentimentInput` to dict conversion for `extract_ticker_scores`.
- **Output:** Includes `hours_back` in output JSON for traceability.

### 4. Tests (`test_news_aggregator.py`)

**17 tests, all passing:**

| Category | Count | Coverage |
|----------|-------|----------|
| CafeF RSS parsing | 2 | Normal + 10-day lookback |
| CafeF HTML fallback | 2 | Fallback trigger + ISO time |
| Vietstock HTML | 3 | Structure + relative time + URL correctness |
| Time parsing (unit) | 7 | ISO, featured, relative (min/hr), short, Vietstock |
| PIT safety | 2 | Guard clause + future exclusion |
| Network failure | 1 | Graceful degradation |

---

## Test Results

```
17 passed in 18.23s
```

---

## Key Design Decisions

1. **RSS-first for CafeF:** RSS feeds are stable, structured, and unaffected by frontend redesigns. HTML scraping is kept as fallback only.
2. **Vietstock HTML-only:** Vietstock does not expose section-specific RSS feeds. Pagination is JS-driven (no `?page=2` URL params), so we scrape only the first page which contains the most recent articles.
3. **Timezone normalization:** All timestamps converted to Vietnam local time (UTC+7) naive datetime for consistent PIT comparison.
4. **No third-party dependencies added:** Uses only `requests`, `bs4`, `xml.etree.ElementTree` (stdlib).

---

## Tier 3 Submission

Submit to:
- **Code Reviewer (Role 21):** Code quality, clean-code compliance
- **QA Engineer (Role 17):** Test coverage, integration validation
- **Security Auditor (Role 18):** Input sanitization, rate-limiting review
