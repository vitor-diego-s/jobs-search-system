# Lessons Learned: Search, Match & Quota Pipeline

**Source project:** `jobs-profile-system` (LinkedIn job automation)
**Date:** 2026-02-23
**Purpose:** Knowledge transfer document for a new decoupled project that owns the search, match, and quota phases independently from the apply pipeline.

---

## 1. LinkedIn Search URL Construction

### What works

LinkedIn job search URLs are stable and filter server-side. The canonical form:

```
https://www.linkedin.com/jobs/search/?geoId=92000000&keywords=python&f_AL=true&f_WT=2&f_E=4,5&sortBy=DD&start=0
```

| Parameter | Purpose | Values |
|-----------|---------|--------|
| `geoId` | Geographic filter (numeric ID) | `92000000` = Worldwide |
| `keywords` | Search terms | URL-encoded string |
| `f_AL` | Easy Apply filter | `true` = only Easy Apply jobs |
| `f_WT` | Workplace type | `1` = onsite, `2` = remote, `3` = hybrid (comma-separated) |
| `f_E` | Experience level | `1`-`6` (1=Intern, 2=Entry, 3=Associate, 4=Senior, 5=Director, 6=Executive) |
| `sortBy` | Sort order | `DD` = date descending (most recent first) |
| `start` | Pagination offset | multiples of 25 (0, 25, 50) |

### Lesson: use `geoId`, not `location`

The `location=Brazil` text parameter produces inconsistent results. LinkedIn's own search UI uses `geoId` for precise filtering. For remote-worldwide searches, `geoId=92000000` matches the behavior of LinkedIn's native search.

Known geoId values:
- `92000000` — Worldwide
- `106057199` — Brazil
- `103644278` — United States

Discovery method: perform a search in LinkedIn's web UI, inspect the URL.

### Lesson: `f_AL=true` is authoritative

When `f_AL=true` is in the search URL, LinkedIn filters server-side. All returned results ARE Easy Apply jobs. Do not rely on badge detection in the DOM to verify this — the Easy Apply badge selector (`span.job-card-container__easy-apply-label`) is unreliable and changes frequently. Trust the server-side filter.

---

## 2. Keyword Strategy

### Problem observed

The keyword `"Staff Software Engineer"` (without `"Python"`) returned PHP, Java, .NET, DBA, and "Data Scientist" positions. The search matched the job title structure but not the tech stack.

Evidence from pipeline run:
- `"Desenvolvedor php"` — matched and attempted (PHP job)
- `"DBA Engineer"` — matched and attempted
- `"Data Scientist (React and watchtower skills)"` — matched and attempted
- `"Forward Deployed Engineer"` — matched (no Python relevance)

### Fix applied

1. **Append the core tech to every keyword**: `"Staff Software Engineer"` became `"Staff Software Engineer Python"`. This constrains LinkedIn's server-side matching.

2. **Expanded exclude_keywords list**: The original 3-item list (`"Java only"`, `"Junior"`, `".NET only"`) missed most irrelevant titles. The expanded list:

```yaml
exclude_keywords:
  - "Junior"
  - "Intern"
  - "Java only"
  - ".NET only"
  - "PHP"
  - "Ruby"
  - "Scala"
  - "Salesforce"
  - "iOS"
  - "Android"
  - "Frontend"
  - "Front End"
  - "React Native"
```

### Design recommendation for the new project

The exclude_keywords filter operates on **job title only** (case-insensitive substring match). This is fast but imprecise. A title like `"Senior Full Stack Engineer"` passes the filter but may be 90% React. For the new project, consider:

- **Title-based exclusion** (current, fast, no I/O) — good first pass
- **Description-based exclusion** (requires fetching job detail page) — expensive but precise
- **Positive keyword matching** — require that the title OR description contains at least one core skill (e.g., "Python", "FastAPI", "Django", "Flask")

---

## 3. Search Results Parsing (DOM)

### Card structure (as of Feb 2026)

LinkedIn renders search results as `<li>` items inside a scrollable container. Each card contains:

| Data point | Selector used | Reliability |
|------------|---------------|-------------|
| Job ID | `data-job-id` attribute on card | High — stable across redesigns |
| Title + URL | `a.job-card-list__title` or `a.job-card-container__link` | Medium — class names change |
| Company | `span.job-card-container__primary-description` | Medium |
| Location | `li.job-card-container__metadata-item` | Medium |
| Easy Apply badge | `span.job-card-container__easy-apply-label` | **Low** — not detected in Feb 2026 run |
| Workplace type | `li.job-card-container__metadata-item--workplace-type` | Low |
| Posted time | `time` element or `span[class*="listed-time"]` | Medium |

### Lesson: always use fallback selectors

LinkedIn's class names are semi-obfuscated and change between A/B test variants. Every selector constant should have 2-3 comma-separated fallbacks. Prefer:
1. `aria-label` and `data-*` attributes (most stable)
2. Semantic HTML elements (`time`, `a[href*="/jobs/view/"]`)
3. Class names (least stable, but sometimes the only option)

### Lesson: lazy loading requires incremental scroll

Search results lazy-load as the user scrolls. A single `scrollTo(0, document.body.scrollHeight)` may not trigger all cards. The working pattern:

```
loop (max 5 iterations):
    count cards on page
    if count == previous count → break (all loaded)
    scroll to bottom
    sleep 1.5-3s (random)
    previous count = count
```

### Lesson: title parsing has a duplication artifact

Card titles are sometimes parsed with the text duplicated: `"Senior Python Engineer\nSenior Python Engineer"`. This happens because the link element contains visible text + an `aria-hidden` duplicate. The new project should `.split('\n')[0]` or strip duplicates during parsing.

---

## 4. Pagination Behavior

- LinkedIn returns **25 results per page** (controlled by the `start` parameter).
- Maximum useful pagination: **3 pages (75 jobs)** per keyword. Beyond page 3, results become highly repetitive or irrelevant.
- When the result count on a page is **< 25**, it's the last page — stop paginating.
- A "no results" banner (`div.jobs-search-no-results-banner`) means the keyword produced zero matches at that offset.

### Anti-detection delays between pages

| Action | Delay range | Rationale |
|--------|-------------|-----------|
| Between scroll attempts | 1.5 - 3.0s | Mimics human reading speed |
| Between pages (same keyword) | 3.0 - 7.0s | Mimics clicking "next page" |
| Between keywords | 5.0 - 12.0s | Mimics typing a new search |

These are **not optional**. Removing them triggers LinkedIn's bot detection, resulting in CAPTCHA or session invalidation.

---

## 5. Matcher Filter Chain

### Order matters

The filter chain runs in this sequence:

1. **Easy Apply filter** — drop non-Easy Apply (if `easy_apply_only=true`)
2. **Exclude keywords** — drop titles containing blocked terms
3. **Deduplication** — keep first occurrence per `external_id` (cross-keyword overlap is common)
4. **Already applied** — drop IDs found in historical results

### Observed numbers (production run)

```
42 candidates found (3 keywords x 14 cards each)
→ Easy Apply filter: 42 → 42 (all were Easy Apply via f_AL=true)
→ Exclude keywords:  42 → ~11 (dropped PHP, Frontend, Data Scientist, etc.)
→ Dedup:             ~11 → ~8 (cross-keyword overlap)
→ Already applied:    ~8 → 8 (3 prior applications, but none overlapped)
Final: 8 matched
```

Deduplication is essential: the same job frequently appears across multiple keyword searches (e.g., "Senior Python Engineer" and "Senior Backend Engineer Python" surface the same postings).

### Already-applied detection

The current system scans `knowledge/apply_result_*.json` files for `job_id` where `result == "success"`. This is fragile:
- File-based glob is slow at scale
- Failed attempts (`form_error`) are not tracked as "already attempted" — the system will retry them
- No TTL — a job applied to 6 months ago still blocks re-application

**Recommendation for the new project:** Use a lightweight DB (SQLite or Postgres) with an `applied_jobs` table: `(external_id, platform, result, applied_at)`. Query is O(1) via index instead of O(n) file scan.

---

## 6. Quota Management

### Design

File-based daily quota via `knowledge/daily_quota.json`:

```json
{"date": "2026-02-23", "searches_run": 1, "applications_sent": 5}
```

- **Auto-reset**: if `date != today`, counters reset to 0
- **Atomic writes**: write to temp file, then `rename()` (prevents corruption on crash)
- **Limits**: 2 searches/day, 20 applications/day (configurable via `settings.yaml`)

### Why these limits exist

- **20 applies/day**: LinkedIn's own Easy Apply has an internal rate limit. Exceeding ~25-30 per day triggers a soft ban (applications silently fail or accounts get flagged for review).
- **2 searches/day**: Each search run navigates 3-9 pages with scrolling. More than 2 runs/day creates abnormal traffic patterns.

### Lesson: quota gate must precede search, not just apply

The original TODO placement put quota checks only before the apply phase. But searching itself is a rate-limited action. The correct order is:

```
if not quota.can_search_today():
    return early (no search, no match, no apply)

search()
quota.record_search()
match()

remaining = quota.remaining_applies()
apply(matched[:remaining])  # truncate to quota
```

---

## 7. Screening Questions — The Real Bottleneck

### Problem

Of 8 application attempts across all runs, only **3 succeeded** (37.5% success rate). All 5 failures were caused by **unanswered required screening questions**.

### Observed question patterns

**Questions answered successfully** (matched via fuzzy key lookup in `profile.yaml`):

| Question text | Matched key | Answer |
|---------------|-------------|--------|
| "Há quantos anos você já usa Python no trabalho?" | `quantos anos você já usa Python` | `11` |
| "Há quantos anos você já usa SQL no trabalho?" | `quantos anos você já usa SQL` | `11` |
| "How many years of work experience do you have with Python" | `how many years` heuristic | `11` |
| "How many years of work experience do you have with React.js?" | `how many years` heuristic | `11` |
| "Are you interested in a contract role?" | `interested in a contract role` | `Yes` |
| "Are you based in the UK?" | `based in the UK` | `No` |
| "Will you now or in the future require sponsorship..." | `require sponsorship` | `No` |
| "SQL Alchemy" | `SQL Alchemy` | `8` |

**Questions that blocked applications** (no matching key):

| Question | Why it failed |
|----------|---------------|
| "How much yearly cash compensation do you require?" | No `compensation`/`salary` key |
| "Are you comfortable working on-site at customer locations in the San Francisco Bay Area?" | No `on-site`/`relocate` key |
| "The position will be about 65% backend engineering, the rest on AI. Is that a fit?" | Free-text question, not a standard pattern |
| "Do you have at least 2 years working with AI/LLMs in production?" | No `AI`/`LLM` key |
| "The job will initially be 100% IC, then ramping up to 50% people management..." | Free-text, compound question |

### The "years of experience" heuristic works well — but has a blind spot

The applier has a built-in heuristic: if a question contains `"years of experience"` / `"how many years"` / `"quantos anos"`, it answers with `profile.candidate.years_of_experience`. This correctly answered React.js, Go, AWS, and SQL experience questions — but it's **always the same number** (`11`). A "How many years with React.js?" → `11` answer is technically a lie and could be caught by recruiters.

### Recommendation for the new project

The new project should own a **screening answer knowledge base** that:

1. Categorizes questions into types: `years_experience`, `yes_no`, `salary`, `location`, `free_text`
2. Maps technology-specific experience separately (Python=11, React=3, Go=2)
3. Has default answers for common yes/no patterns (`sponsorship` → No, `authorized to work` → Yes, `contract role` → Yes)
4. Flags unknown questions for human review rather than silently failing

---

## 8. Anti-Detection Constraints

These are hard requirements that any browser-based LinkedIn automation must follow:

1. **`headless=False` always** — patchright's anti-detection patches only work in headed mode. `headless=True` is instantly detected.
2. **No `--headless` flag** — even `--headless=new` (Chrome's new headless) is detected.
3. **Random delays between ALL actions** — scrolls, page navigations, clicks. Never use fixed intervals.
4. **Single browser session per pipeline run** — launching multiple browsers or recycling sessions across runs changes the fingerprint.
5. **Cookie-based auth only** — do not automate the login flow. Load pre-exported cookies.
6. **patchright, not playwright** — patchright patches CDP detection vectors that vanilla Playwright leaks.

---

## 9. Architecture: Why Decouple Search from Apply

The search and apply phases have fundamentally different characteristics:

| Dimension | Search + Match | Apply |
|-----------|----------------|-------|
| **I/O pattern** | Read-only: navigate, scroll, parse | Write: fill forms, click submit |
| **Reversibility** | Fully reversible (no side effects) | Irreversible (application submitted) |
| **Failure cost** | Low (retry anytime) | High (duplicate applications, stuck modals) |
| **Browser dependency** | Needs `page.goto` + `query_selector` | Needs full modal interaction, CDP events |
| **State required** | Config + cookies | Config + cookies + profile + screening answers |
| **Rate sensitivity** | 2 runs/day sufficient | 20/day cap, 45-120s between applies |
| **Testability** | URL building is pure logic; parsing testable with mock DOM | Multi-step modal requires complex async mocks |

Decoupling means the search project can:
- Run more frequently (e.g., search 4x/day, apply 1x/day)
- Be tested independently without risk of accidental submissions
- Evolve selectors and parsing without touching the apply pipeline
- Store candidates in a proper database for the apply project to consume

---

## 10. Data Contract Between Search and Apply

The search project should output candidates in this schema (Pydantic v2):

```python
class JobCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_id: str           # LinkedIn job ID (numeric string)
    title: str                 # Job title (first line only, strip \n duplicates)
    company: str               # Company name
    location: str              # Location text from card
    url: str                   # Absolute URL: https://www.linkedin.com/jobs/view/{id}/
    is_easy_apply: bool        # True when f_AL=true was in search URL
    workplace_type: str        # "remote", "hybrid", "onsite", or ""
    description_snippet: str   # Empty from search cards (would need detail page fetch)
    posted_time: str           # e.g. "2 days ago"
```

The apply project reads from this schema (via DB or file) and processes candidates.

---

## 11. File Inventory for the New Project

Source files to migrate (copy + adapt):

| File | Lines | Migrate as |
|------|-------|------------|
| `src/platforms/linkedin/searcher.py` | 250 | Core — URL building, pagination, card parsing |
| `src/platforms/linkedin/selectors.py` (search section) | 50 | Selector constants for search results |
| `src/pipeline/matcher.py` | 81 | Core — filter chain logic |
| `src/pipeline/quota_manager.py` | 90 | Core — daily quota enforcement |
| `src/core/schemas.py` (`JobCandidate`, `SearchRunResult`) | 25 | Data models |
| `src/config/loader.py` (`SearchConfig`, `QuotasConfig`, `LinkedInSearchConfig`) | 30 | Config models |
| `tests/unit/test_searcher.py` | 120 | URL + parsing tests |
| `tests/unit/test_matcher.py` | 100 | Filter chain tests |
| `tests/unit/test_quota_manager.py` | 90 | Quota logic tests |

Files NOT to migrate (apply-only):
- `applier.py`, `handler.py` (apply_to_job), `session_manager.py` (check_premium)
- `profile_loader.py` (screening answers are apply-phase only)
- `orchestrator.py` (the wiring is specific to the monolith architecture)

---

## 12. Known Technical Debt

1. **Company name not parsed** — all result files show `"company": ""`. The selector `span.job-card-container__primary-description` likely doesn't match current DOM. Needs selector update.

2. **Title duplication** — titles are stored as `"Senior Python Engineer\nSenior Python Engineer"`. The parser should strip the duplicate.

3. **No description fetching** — `description_snippet` is always empty because it requires navigating to the job detail page (expensive, +2-3s per job). The matcher can't filter on description content without this.

4. **Workplace type badge not detected** — similar to the Easy Apply badge, the workplace type selector doesn't match current DOM. Currently inferred from config (`f_WT=2` → assume remote).

5. **14 cards per page instead of 25** — all 3 keywords returned exactly 14 cards per page, suggesting LinkedIn serves fewer results for certain geoId/filter combinations, or the scroll-to-load logic exits too early.
