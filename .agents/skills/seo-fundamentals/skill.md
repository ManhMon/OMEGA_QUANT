---
name: seo-fundamentals
description: SEO fundamentals, E-E-A-T, Core Web Vitals, and Google algorithm principles.
when_to_use: "When optimizing web pages for search engines, implementing meta tags, improving E-E-A-T, or fixing Core Web Vitals."
allowed-tools: Read, Glob, Grep
---

# SEO Fundamentals

> Principles for search engine visibility.

---

## 1. E-E-A-T Framework

| Principle | Signals |
|-----------|---------|
| **Experience** | First-hand knowledge, real examples |
| **Expertise** | Credentials, depth of knowledge |
| **Authoritativeness** | Backlinks, mentions, industry recognition |
| **Trustworthiness** | HTTPS, transparency, accurate info |

---

## 2. Core Web Vitals

| Metric | Target | Measures |
|--------|--------|----------|
| **LCP** | < 2.5s | Loading performance |
| **INP** | < 200ms | Interactivity |
| **CLS** | < 0.1 | Visual stability |

---

## 3. Technical SEO Principles

### Site Structure

| Element | Purpose |
|---------|---------|
| XML sitemap | Help crawling |
| robots.txt | Control access |
| Canonical tags | Prevent duplicates |
| HTTPS | Security signal |

### Performance

| Factor | Impact |
|--------|--------|
| Page speed | Core Web Vital |
| Mobile-friendly | Ranking factor |
| Clean URLs | Crawlability |

### Accessibility and Responsive Experience

- Use semantic landmarks, descriptive link text, correctly nested headings, accessible form labels, and useful image alternatives; accessibility improves usability and helps make content understandable, but does not guarantee ranking.
- Ensure mobile-first layouts remain readable and operable at narrow widths, enlarged text, keyboard navigation, and zoom. Avoid content hidden only on small screens.
- Monitor LCP, INP, and CLS on representative devices and routes. Treat Core Web Vitals as page-experience signals, not a substitute for useful content or an SEO guarantee.

---

## 4. Content SEO Principles

### Page Elements

| Element | Best Practice |
|---------|---------------|
| Title tag | Unique, concise, accurate; lead with the page topic where natural |
| Meta description | Accurate, useful summary; search engines may generate a different snippet |
| H1 | One per page, main keyword |
| H2-H6 | Logical hierarchy |
| Alt text | Descriptive, not stuffed |

### Content Quality

| Factor | Importance |
|--------|------------|
| Depth | Comprehensive coverage |
| Freshness | Regular updates |
| Uniqueness | Original value |
| Readability | Clear writing |

---

## 5. Schema Markup Types

| Type | Use |
|------|-----|
| Article | Blog posts, news |
| Organization | Company info |
| Person | Author profiles |
| FAQPage | Q&A content |
| Product | E-commerce |
| Review | Ratings |
| BreadcrumbList | Navigation |

---

## 6. AI Content Guidelines

### What Google Looks For

| ✅ Do | ❌ Don't |
|-------|----------|
| AI draft + human edit | Publish raw AI content |
| Add original insights | Copy without value |
| Expert review | Skip fact-checking |
| Follow E-E-A-T | Keyword stuffing |

---

## 7. Ranking Factors (Prioritized)

| Priority | Factor |
|----------|--------|
| 1 | Quality, relevant content |
| 2 | Backlinks from authority sites |
| 3 | Page experience (Core Web Vitals) |
| 4 | Mobile optimization |
| 5 | Technical SEO fundamentals |

---

## 8. Measurement

| Metric | Tool |
|--------|------|
| Rankings | Search Console, Ahrefs |
| Traffic | Analytics |
| Core Web Vitals | PageSpeed Insights |
| Indexing | Search Console |
| Backlinks | Ahrefs, Semrush |

---

## 9. Version Validation and 24D Review

- Validate framework, SEO plugin, schema generator, and runtime versions from manifests and lockfiles. Check version-matched official documentation and current search-engine guidance before relying on metadata APIs, rendering behavior, or structured-data features.
- Validate structured data against the current supported vocabulary and search-feature policies; never assume a schema type guarantees a rich result.
- Before handoff, review all 24 OMEGA adversarial dimensions in [testing-patterns](../testing-patterns/skill.md). Record a focused test for each applicable dimension; mark unrelated dimensions not applicable with a reason. Include input/schema, output integrity, secrets, and resource cases where SEO generation consumes untrusted or large content; do not misrepresent unrelated market-data dimensions as tested.

---

> **Remember:** SEO is a long-term game. Useful content, accessible responsive pages, and sound technical implementation create durable foundations, not ranking guarantees.
