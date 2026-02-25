# Lessons Applied from Previous Project
# jobs-search-engine

**Source:** `docs/previous-lessons.md` (migrated from `jobs-profile-system`, 2026-02-23)
**Filtered for:** General-purpose multi-platform search engine context
**Date:** 2026-02-24

---

## Overview

The previous project (`jobs-profile-system`) was a monolithic LinkedIn automation tool coupling search, match, and apply. This document captures the lessons that directly apply to the search-only phase of the new decoupled system.

---

## L1. URL Construction — Use `geoId`, Never `location=text`

**Context:** LinkedIn search URL parameter choice.

**Lesson:** `location=Brazil` produces inconsistent server-side results. LinkedIn's own UI uses `geoId` for geographic filtering. Always use numeric `geoId`.

```
92000000  → Worldwide
106057199 → Brazil
103644278 → United States
```

**Discovery method:** Perform search in LinkedIn web UI → inspect URL in browser.

**Rule:** Any new geoId value must be discovered by inspecting a real LinkedIn search URL, never guessed.

**Applied in:** `src/platforms/linkedin/searcher.py` URL builder.

---

## L2. Server-Side Filters Are Authoritative — Don't Re-Verify in DOM

**Context:** LinkedIn `f_AL=true` (Easy Apply filter).

**Lesson:** When `f_AL=true` is in the URL, LinkedIn filters server-side. All returned jobs ARE Easy Apply. The DOM badge (`span.job-card-container__easy-apply-label`) is unreliable and changed between runs.

**Generalized rule:** For any URL-level filter (easy apply, remote, experience level), trust the server-side result. Verify via DOM only if there is no server-side filter option.

**Applied in:** `src/platforms/linkedin/parser.py` — set `is_easy_apply=True` when `f_AL=true` was in the search URL; do not attempt badge detection.

---

## L3. Keyword Strategy — Constrain with Tech Stack

**Context:** Broad job title keywords produce noisy results.

**Lesson:** `"Staff Software Engineer"` alone returned PHP, Java, .NET, and Data Scientist jobs. Appending the core tech stack constrains LinkedIn's matching:

- Bad: `"Staff Software Engineer"`
- Good: `"Staff Software Engineer Python"`

**Complementary rule:** `exclude_keywords` is a fast first-pass filter on title only. It does not catch disguised mismatches (e.g., `"Senior Full Stack Engineer"` = 90% React). For precision, use `require_keywords` (positive match on title/snippet).

**Exclude keyword baseline for Python backend roles:**
```yaml
exclude_keywords:
  - Junior
  - Intern
  - PHP
  - Ruby
  - Scala
  - Salesforce
  - iOS
  - Android
  - Frontend
  - "Front End"
  - "React Native"
  - "Java only"
  - ".NET only"
```

**Applied in:** `config/settings.yaml` defaults + `src/pipeline/matcher.py` ExcludeKeywordsFilter.

---

## L4. DOM Selectors — Always Provide Fallbacks

**Context:** LinkedIn A/B tests and redesigns change class names frequently.

**Lesson:** Every selector constant must have 2–3 comma-separated fallbacks. Stability ranking:

1. `data-*` attributes (most stable — `data-job-id` has not changed)
2. `aria-label`, semantic HTML (`time`, `a[href*="/jobs/view/"]`)
3. Class names (least stable — treat as temporary)

**Observed stability as of Feb 2026:**

| Data point | Selector | Stability |
|------------|----------|-----------|
| Job ID | `data-job-id` attribute | **High** |
| Title + URL | `a.job-card-list__title` | Medium |
| Company | `span.job-card-container__primary-description` | **Low** (was broken in prior run) |
| Easy Apply badge | `span.job-card-container__easy-apply-label` | **Low** (do not use) |

**Applied in:** `src/platforms/linkedin/selectors.py` — each constant is a list, parser tries in order.

---

## L5. Title Parsing — Strip `\n` Duplicates

**Context:** LinkedIn card title element structure.

**Lesson:** The link element contains visible text + an `aria-hidden` duplicate. Raw `.text_content()` returns `"Senior Python Engineer\nSenior Python Engineer"`.

**Fix:** Always `.split('\n')[0].strip()` on title text. Apply this at parse time, not at call sites.

**Applied in:** `src/platforms/linkedin/parser.py` → `_parse_title()` helper.

---

## L6. Lazy-Loading — Incremental Scroll, Not Single Jump

**Context:** LinkedIn search results page rendering.

**Lesson:** A single `scrollTo(0, document.body.scrollHeight)` only loads some cards. Pages can show 14 cards when 25 are available if the scroll exits early.

**Working pattern:**
```python
previous_count = 0
for _ in range(MAX_SCROLL_ATTEMPTS):  # e.g. 5
    current_count = len(await page.query_selector_all(CARD_SELECTOR))
    if current_count == previous_count:
        break  # stable — all cards loaded
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await random_sleep(1.5, 3.0)
    previous_count = current_count
```

**Applied in:** `src/browser/actions.py` → `scroll_until_stable()`.

---

## L7. Anti-Detection Delays — Non-Negotiable

**Context:** LinkedIn bot detection triggers.

**Lesson:** Fixed or missing delays trigger CAPTCHA or session invalidation. Required minimums:

| Transition | Min | Max | Notes |
|------------|-----|-----|-------|
| Between scroll attempts | 1.5s | 3.0s | Mimics human reading |
| Between pages (same keyword) | 3.0s | 7.0s | Mimics "next page" click |
| Between keywords | 5.0s | 12.0s | Mimics typing a new search |

**Rule:** All delay values are randomized. No `asyncio.sleep(fixed_number)` anywhere except in `actions.py`. Delay ranges are configurable in `settings.yaml` but have floor values enforced in code.

**Applied in:** `src/browser/actions.py` → `random_sleep(min_s, max_s)` with floor enforcement.

---

## L8. Pagination — 25 Results / Page, Max 3 Pages

**Context:** LinkedIn search results pagination.

**Lesson:**
- LinkedIn returns exactly 25 results per page when results exist
- If page returns `< 25` cards → last page, stop paginating
- Beyond 3 pages (offset=75), results become highly repetitive
- Stop condition: `div.jobs-search-no-results-banner` visible = zero results at this offset

**Applied in:** `src/platforms/linkedin/searcher.py` → `_paginate()`.

---

## L9. Deduplication — Across Keywords AND Across Platforms

**Context:** Filter chain ordering.

**Lesson:** The same job frequently surfaces under multiple keyword searches (`"Senior Python Engineer"` and `"Senior Backend Engineer Python"` return the same posting). Dedup by `(platform, external_id)` is essential.

**Filter chain order (matters):**
1. ExcludeKeywords (fast, title-only)
2. PositiveKeywords (optional)
3. Dedup — in-memory within a run (by `(platform, external_id)`)
4. AlreadySeen — DB lookup (persistent cross-run)

**Applied in:** `src/pipeline/matcher.py`.

---

## L10. Already-Seen Storage — Use SQLite, Not File Scans

**Context:** Tracking previously returned candidates to avoid re-surfacing.

**Lesson:** The previous project scanned `apply_result_*.json` files with glob — O(n) and fragile. At 100+ runs, this becomes slow and error-prone.

**Replacement design:**
```sql
-- candidates table with UNIQUE(external_id, platform)
-- Query: SELECT 1 FROM candidates WHERE external_id=? AND platform=? AND found_at > ?
```

**Include TTL:** An `already_seen` hit should expire after N days (default: 30). A job re-posted after 30 days should re-surface.

**Applied in:** `src/pipeline/matcher.py` AlreadySeenFilter + `src/core/db.py`.

---

## L11. Quota Gate — Before Search, Not Just Before Apply

**Context:** Rate limiting in the pipeline order.

**Lesson:** The original system checked quota only before apply. But search itself is rate-limited activity. The correct gate order:

```
can_search() → False → return (no browser, no I/O)
               True  → search() → record_search()
                      → filter/score
                      → write to DB
```

**Applied in:** `src/pipeline/orchestrator.py` — quota check is the first statement.

---

## L12. Company Name — Expect Parsing Failures, Handle Gracefully

**Context:** LinkedIn card structure reliability.

**Lesson:** In the previous project's Feb 2026 run, ALL company names were empty (`""`). The selector `span.job-card-container__primary-description` did not match the live DOM.

**Design consequence:**
- `company` field defaults to `""` (not an error)
- Parser logs a DEBUG warning per failed field, not an exception
- The system continues without company name; it can be enriched later

**Applied in:** `src/platforms/linkedin/parser.py` → every field has a `try/except` that returns `""` or `0` on failure.

---

## L13. Architecture — Search Must Be Decoupled from Apply

**Context:** Why this project is a standalone service.

**Lesson from previous project's architecture:**

| Dimension | Search | Apply |
|-----------|--------|-------|
| I/O | Read-only | Write (form submit) |
| Reversibility | Fully reversible | Irreversible |
| Failure cost | Low | High |
| Rate sensitivity | 2 runs/day | 20/day, 45-120s between |
| Testability | High (URL + parser tests) | Low (modal mocking) |

**Decision:** This project stops at writing `JobCandidate` records to the DB. The apply project reads from the DB. No shared code between the two beyond the `JobCandidate` schema (which can be published as a shared library if needed).

---

## L14. Known Technical Debt Inherited

These were broken in the previous project and must be fixed here:

| Issue | Root Cause | Fix |
|-------|------------|-----|
| Company name always `""` | Selector mismatch (Feb 2026 DOM) | Update selector + add fallbacks |
| Title duplication `\n` artifact | `aria-hidden` span included | `.split('\n')[0].strip()` at parse |
| Workplace type not detected | Badge selector unreliable | Infer from URL `f_WT` param |
| 14 cards instead of 25 | Scroll exits too early | Use `scroll_until_stable()` pattern |

---

## L16. Virtual DOM Occlusion — scrollIntoView Before Parsing

**Source:** M7 live validation (2026-02-25)
**Root cause:** LinkedIn uses virtual DOM (`data-occludable-job-id`) — cards outside the viewport have their inner HTML stripped to ~16 bytes. The `<li>` shell remains with the `data-occludable-job-id` attribute, but `<a>`, `<span>`, company, title elements are removed.

**Rules:**
1. After `scroll_until_stable`, do NOT query all cards and parse in bulk — most cards will be empty shells.
2. Before parsing each card, call `card.scroll_into_view_if_needed()` + brief wait (150ms) to restore content.
3. `external_id` (an attribute on the `<li>`) survives occlusion; all inner elements do not.

**Impact:** Without this fix, 100% of titles and 73% of companies were empty.

---

## L17. Title Extraction — Use `<strong>`, Not `<a>` text_content

**Source:** M7 live validation (2026-02-25)
**Root cause:** The `<a>` title link's `text_content()` returns `"\n                      Title\nTitle\n"` — leading newlines, whitespace, and aria-hidden duplication. The original L5 fix (`split('\n')[0]`) returned empty because the first segment before `\n` is whitespace.

**Rules:**
1. Prefer `<strong>` element inside the title link — always contains clean, single title text.
2. Fallback to `aria-label` attribute (strip " with verification" suffix).
3. Last resort: `text_content().strip().split('\n')[0].strip()` (strip first, then split).

**Impact:** Without this fix, 100% of titles were empty strings.

---

## L15. Lessons NOT Applied (Apply-Phase Only)

The following lessons from the previous project are explicitly out of scope for this search-only system:

- Screening question answering (years_experience heuristic, salary, free-text)
- Form modal navigation (CDP events, button clicks)
- Application success/failure detection
- Session state management (check_premium, login flow)
- Profile YAML loading
