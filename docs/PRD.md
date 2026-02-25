# Product Requirements Document
# jobs-search-engine

**Version:** 0.1 (Draft)
**Date:** 2026-02-24
**Status:** Active Design

---

## 1. Problem Statement

Job hunting across platforms is high-friction and repetitive. Manually searching LinkedIn, Glassdoor, Indeed, and others for relevant positions wastes hours daily. Existing automation tools are monolithic: they couple search, match, and apply into one fragile pipeline that is hard to test, hard to evolve, and dangerous to run without supervision.

This project owns **only the search and match phases**: discovering jobs, scoring their relevance, and outputting a clean, structured candidate list for a downstream apply pipeline to consume.

---

## 2. Goals

| # | Goal | Priority |
|---|------|----------|
| G1 | Collect job listings from multiple platforms via configured keyword searches | Must |
| G2 | Filter and score candidates against a relevance profile | Must |
| G3 | Deduplicate across keywords and platforms | Must |
| G4 | Enforce per-platform daily search quotas | Must |
| G5 | Output structured `JobCandidate` records to a SQLite database | Must |
| G6 | Support dry-run mode with no browser and no DB writes | Must |
| G7 | Be fully testable without a live browser (URL building, parsing, filtering) | Must |
| G8 | Support multiple job platforms via a common adapter interface | Should |
| G9 | Produce a relevance score (0–100) per candidate | Should |
| G10 | Support description fetching for precision filtering | Could |
| G11 | Export candidates to JSON/CSV for external tools | Could |

### Out of Scope (Explicit)

- **Applying to jobs** — this project stops at candidate output
- **Profile management** — screening answers, resume selection
- **LinkedIn login automation** — auth is handled externally (cookie injection)
- **CAPTCHA solving**
- **Scheduling / orchestration** — the caller (cron job, CLI) is responsible

---

## 3. Users

**Primary user:** A single job seeker (the system operator) running the tool locally. Not a SaaS product. Configuration is via YAML files.

---

## 4. Functional Requirements

### 4.1 Search

| ID | Requirement |
|----|-------------|
| SR-1 | Accept a list of `(keyword, platform, filters)` search configurations |
| SR-2 | For each search: paginate results up to a configurable max-pages limit |
| SR-3 | Parse each result page into a list of raw `JobCandidate` structs |
| SR-4 | Rate-limit actions (scroll, page navigation, keyword transitions) with randomized delays |
| SR-5 | Detect and handle the "no results" state gracefully (stop paginating) |
| SR-6 | Support LinkedIn as the first platform implementation |
| SR-7 | Be extensible to other platforms via the adapter interface |

### 4.2 Matching / Filtering

| ID | Requirement |
|----|-------------|
| MR-1 | Apply an ordered filter chain: exclude_keywords → dedup → already_seen |
| MR-2 | `exclude_keywords` operates on job title (case-insensitive substring) |
| MR-3 | Deduplication is by `(platform, external_id)` — same job from two keywords counts once |
| MR-4 | `already_seen` checks DB for previously returned candidates (with configurable TTL) |
| MR-5 | Positive keyword matching: optionally require title OR snippet contains a required term |
| MR-6 | Produce a relevance score using configurable weights (title match, seniority, platform) |

### 4.3 Quota Management

| ID | Requirement |
|----|-------------|
| QR-1 | Track `searches_run` and `candidates_returned` per platform per day |
| QR-2 | Auto-reset counters at midnight (by date comparison, not a timer) |
| QR-3 | Enforce `max_searches_per_day` before initiating any search |
| QR-4 | Quota state stored in SQLite (not files) with atomic writes |
| QR-5 | Quota check is the first gate — if exceeded, return early with no browser activity |

### 4.4 Output

| ID | Requirement |
|----|-------------|
| OR-1 | Write matched candidates to a `candidates` table in SQLite |
| OR-2 | Schema: `external_id`, `platform`, `title`, `company`, `location`, `url`, `is_easy_apply`, `workplace_type`, `posted_time`, `score`, `found_at`, `status` |
| OR-3 | Status field: `new`, `reviewed`, `rejected`, `queued_for_apply`, `applied` |
| OR-4 | In dry-run mode: print candidates to stdout, write nothing to DB |
| OR-5 | Optionally export to JSON or CSV via a CLI flag |

### 4.5 Configuration

| ID | Requirement |
|----|-------------|
| CR-1 | All behavior driven by `config/settings.yaml` |
| CR-2 | Config validated at startup with Pydantic; fail fast with readable errors |
| CR-3 | Searches defined as a list under `searches:` — each with `keyword`, `platform`, `filters` |
| CR-4 | Global defaults overridable per search (e.g., max_pages, exclude_keywords) |
| CR-5 | Quota limits configurable per platform |

---

## 5. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | **Testability**: URL construction, parsing helpers, and filter chain must be testable without browser |
| NFR-2 | **Anti-detection**: For browser-based platforms: headed mode only, randomized delays, single session, cookie auth |
| NFR-3 | **Reliability**: Never crash on a single bad card parse — log and continue |
| NFR-4 | **Observability**: Structured logging at INFO level; DEBUG for selector hits/misses |
| NFR-5 | **Reproducibility**: Dry-run against a saved HTML fixture must produce identical output |
| NFR-6 | **Idempotency**: Running the same search twice should not duplicate DB records |

---

## 6. Constraints

1. **Python 3.12+** — no older versions
2. **patchright** for browser automation (not vanilla playwright) — required for anti-detection
3. **Headed browser only** — `headless=False` is mandatory
4. **pydantic v2** for all data models and config
5. **SQLite** for state (no external DB dependencies for a local tool)
6. **No login automation** — caller provides cookies; this system loads them

---

## 7. Platform-Specific Notes

### LinkedIn

- URL filter parameters: `geoId`, `keywords`, `f_AL`, `f_WT`, `f_E`, `sortBy`, `start`
- Use `geoId`, not `location=text` (server-side precision)
- `f_AL=true` is authoritative for Easy Apply — do not re-verify via DOM badge
- Pagination: 25 results per page, max 3 pages per keyword (75 jobs)
- Lazy-loading: incremental scroll required before parsing each page
- Anti-detection delays: scroll 1.5-3s, page 3-7s, keyword 5-12s

### Future Platforms (Architecture Must Support)

- **Glassdoor** (HTML scraping)
- **Indeed** (HTML scraping)
- **Greenhouse / Lever / Workday** (ATS-specific APIs or scraping)
- **Remote.co / We Work Remotely** (simpler HTML, no auth)

---

## 8. Success Criteria

| Metric | Target |
|--------|--------|
| Search completion rate (no crash) | ≥ 95% per run |
| Title parse accuracy | ≥ 98% (no `\n` duplicates) |
| Company name parse accuracy | ≥ 90% |
| Dedup rate | Zero duplicate `(platform, external_id)` in DB |
| Quota compliance | Never exceeds configured limits |
| Unit test coverage | ≥ 80% on pure-logic modules |

---

## 9. Open Questions (Resolved)

| # | Question | Decision |
|---|----------|----------|
| OQ-1 | Which platforms after LinkedIn? Glassdoor first? | **Defer** — decide after LinkedIn adapter is stable |
| OQ-2 | Is relevance scoring rule-based or LLM-assisted? | **Rule-based first** — LLM scoring added to backlog |
| OQ-3 | Should the DB be shared with the apply project, or separate + synced? | **Shared DB** — both search and apply projects use the same SQLite file |
| OQ-4 | Description fetching: opt-in per search config, or global setting? | **Per-search config** — `fetch_description: true` per search entry |
