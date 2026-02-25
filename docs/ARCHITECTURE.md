# Architecture Design
# jobs-search-engine

**Version:** 0.1 (Draft)
**Date:** 2026-02-24

---

## 1. Guiding Principles

1. **Search ≠ Apply** — This project is read-only. No side effects beyond writing to our own DB.
2. **Platform-agnostic core** — Filter chain, scoring, dedup, and quota logic know nothing about LinkedIn or DOM.
3. **Testable by default** — Any module that doesn't need a browser must not import one.
4. **Fail safe** — A bad card parse logs a warning and continues; it never crashes the run.
5. **Config-driven** — Behavior changes via YAML, not code changes.

---

## 2. System Context

```
┌─────────────────────────────────────────────────────┐
│                    Caller (CLI / cron)               │
└───────────────────────────┬─────────────────────────┘
                            │  runs
                            ▼
┌─────────────────────────────────────────────────────┐
│               jobs-search-engine (this project)      │
│                                                      │
│  Config ──► Orchestrator ──► [Platform Adapters]     │
│                    │              ↓                  │
│                    │         Raw JobCards            │
│                    ▼              ↓                  │
│             Filter Chain ◄────────┘                  │
│                    │                                 │
│                    ▼                                 │
│             Scored Candidates                        │
│                    │                                 │
│                    ▼                                 │
│              SQLite DB / stdout (dry-run)            │
└─────────────────────────────────────────────────────┘
                            │  reads
                            ▼
┌─────────────────────────────────────────────────────┐
│           Downstream apply project (separate)        │
└─────────────────────────────────────────────────────┘
```

---

## 3. Module Structure

```
jobs-search-engine/
├── config/
│   └── settings.yaml              # User-facing configuration
├── src/
│   ├── core/
│   │   ├── schemas.py             # JobCandidate, SearchRun, QuotaState (Pydantic)
│   │   ├── config.py              # Config models + loader (Pydantic)
│   │   └── db.py                  # SQLite connection + table definitions
│   ├── pipeline/
│   │   ├── orchestrator.py        # Main entry point: loads config, runs searches, writes output
│   │   ├── matcher.py             # Filter chain: exclude → dedup → already_seen → score
│   │   ├── quota_manager.py       # Daily quota tracking + enforcement
│   │   └── scorer.py              # Relevance scoring (rule-based)
│   ├── platforms/
│   │   ├── base.py                # Abstract PlatformAdapter interface
│   │   ├── linkedin/
│   │   │   ├── adapter.py         # Implements PlatformAdapter; wires searcher + browser
│   │   │   ├── searcher.py        # URL building, pagination, lazy-scroll loop
│   │   │   ├── parser.py          # DOM → JobCandidate (all selector logic here)
│   │   │   └── selectors.py       # Selector constants with fallback lists
│   │   └── (glassdoor/, indeed/)  # Future adapters
│   └── browser/
│       ├── session.py             # Patchright browser init, cookie loading
│       └── actions.py             # Reusable: scroll, wait_for_cards, safe_text
├── tests/
│   ├── unit/
│   │   ├── test_url_builder.py    # URL construction (pure, no browser)
│   │   ├── test_parser.py         # Parser with HTML fixtures (no browser)
│   │   ├── test_matcher.py        # Filter chain logic
│   │   ├── test_quota_manager.py  # Quota: reset, gate, increment
│   │   └── test_scorer.py         # Scoring logic
│   ├── integration/
│   │   └── test_search_pipeline.py  # Full search with mock adapter
│   └── fixtures/
│       └── linkedin_results_page.html  # Saved HTML for parser tests
├── tasks/
│   └── todo.md                    # Milestone tracking
├── docs/
│   ├── PRD.md                     # This document's companion
│   ├── ARCHITECTURE.md            # This document
│   └── lessons-applied.md         # Lessons from previous project
├── main.py                        # CLI entry point
└── pyproject.toml
```

---

## 4. Key Interfaces

### 4.1 `PlatformAdapter` (abstract base)

```python
class PlatformAdapter(ABC):
    """One implementation per job platform."""

    @abstractmethod
    async def search(self, config: SearchConfig) -> list[JobCandidate]:
        """
        Execute a single keyword search and return raw (unfiltered) candidates.
        Handles pagination, scroll, and rate limiting internally.
        """
        ...

    @property
    @abstractmethod
    def platform_id(self) -> str:
        """e.g. 'linkedin', 'glassdoor'"""
        ...
```

### 4.2 `JobCandidate` (core schema)

```python
class JobCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_id: str           # Platform-specific job ID
    platform: str              # "linkedin", "glassdoor", etc.
    title: str                 # Cleaned title (no \n duplicates)
    company: str               # Company name ("" if unparseable)
    location: str              # Location text
    url: str                   # Absolute canonical URL
    is_easy_apply: bool        # True if platform confirmed easy/quick apply
    workplace_type: str        # "remote" | "hybrid" | "onsite" | ""
    posted_time: str           # Human-readable: "2 days ago"
    description_snippet: str   # "" unless description fetch is enabled
    score: float = 0.0         # Filled by scorer after filtering
    found_at: datetime         # When this candidate was collected
```

### 4.3 `FilterChain` (pipeline step)

The matcher applies filters **in order**. Each filter receives `list[JobCandidate]` and returns a subset.

```
Input candidates
    │
    ▼ ExcludeKeywordsFilter(title, case_insensitive)
    ▼ PositiveKeywordsFilter(title OR snippet, optional)
    ▼ DeduplicationFilter(platform + external_id, in-memory within run)
    ▼ AlreadySeenFilter(DB lookup, configurable TTL in days)
    │
Output: filtered candidates → Scorer
```

Each filter is a callable `(candidates: list[JobCandidate]) -> list[JobCandidate]`.
Filters are composable and independently testable.

### 4.4 `QuotaManager`

```python
class QuotaManager:
    def can_search(self, platform: str) -> bool: ...
    def record_search(self, platform: str) -> None: ...
    def remaining_candidates(self, platform: str) -> int: ...
    def record_candidates(self, platform: str, count: int) -> None: ...
```

State stored in `quota` table in SQLite. Auto-resets when `date != today`.

---

## 5. Data Flow (Single Search Run)

```
1. CLI invoked  →  load + validate config/settings.yaml
2. QuotaManager.can_search(platform)  →  if False, exit early
3. Browser session init (patchright, load cookies)
4. For each search in config.searches:
   a. LinkedInAdapter.search(search_config)
      - Build paginated URLs
      - For each page:
          i.  page.goto(url)
          ii. scroll_until_stable()
          iii. parser.parse_cards(page) → list[JobCandidate]
      - return all candidates from all pages
   b. FilterChain.apply(candidates)  →  filtered candidates
   c. Scorer.score(filtered)  →  scored candidates
   d. DB.upsert(scored)
   e. QuotaManager.record_search(platform)
5. Print summary: N searched, M filtered, K new
6. Browser close
```

---

## 6. Database Schema (SQLite)

### `candidates` table

```sql
CREATE TABLE IF NOT EXISTS candidates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id   TEXT    NOT NULL,
    platform      TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    company       TEXT    NOT NULL DEFAULT '',
    location      TEXT    NOT NULL DEFAULT '',
    url           TEXT    NOT NULL,
    is_easy_apply INTEGER NOT NULL DEFAULT 0,
    workplace_type TEXT   NOT NULL DEFAULT '',
    posted_time   TEXT    NOT NULL DEFAULT '',
    description_snippet TEXT NOT NULL DEFAULT '',
    score         REAL    NOT NULL DEFAULT 0.0,
    status        TEXT    NOT NULL DEFAULT 'new',
    found_at      TEXT    NOT NULL,
    UNIQUE(external_id, platform)
);
```

### `quota` table

```sql
CREATE TABLE IF NOT EXISTS quota (
    platform      TEXT NOT NULL,
    date          TEXT NOT NULL,
    searches_run  INTEGER NOT NULL DEFAULT 0,
    candidates_found INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (platform, date)
);
```

### `search_runs` table

```sql
CREATE TABLE IF NOT EXISTS search_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT NOT NULL,
    keyword       TEXT NOT NULL,
    filters_json  TEXT NOT NULL,
    raw_count     INTEGER NOT NULL,
    filtered_count INTEGER NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT NOT NULL
);
```

---

## 7. Configuration Schema (`settings.yaml`)

```yaml
database:
  path: data/candidates.db

quotas:
  linkedin:
    max_searches_per_day: 2
    max_candidates_per_day: 150

browser:
  cookies_path: config/linkedin_cookies.json
  timeout_ms: 30000

searches:
  - keyword: "Senior Python Engineer"
    platform: linkedin
    filters:
      geo_id: 92000000           # Worldwide
      workplace_type: [remote]
      experience_level: [senior, director]
      easy_apply_only: true
      max_pages: 3
    exclude_keywords:
      - Junior
      - PHP
      - Ruby
      - Frontend
      - "React Native"
    require_keywords: []        # Optional: title must contain one of these

  - keyword: "Staff Backend Engineer Python"
    platform: linkedin
    filters:
      geo_id: 92000000
      workplace_type: [remote]
      easy_apply_only: true
      max_pages: 2

scoring:
  title_match_bonus: 20         # Points for each require_keyword hit
  seniority_match_bonus: 15     # Points for matching seniority level
  easy_apply_bonus: 10
  remote_bonus: 10
  recency_weight: 0.3           # Higher = prefer recent posts
```

---

## 8. Anti-Detection Constraints (Hard Rules)

These are non-negotiable for LinkedIn and any browser-based platform:

| Rule | Enforcement |
|------|-------------|
| `headless=False` always | Hardcoded in `browser/session.py`; no config override |
| Random delays between ALL actions | `actions.py` exposes `random_sleep(min, max)` only |
| Single browser session per run | `session.py` creates one context; adapter receives it |
| Cookie auth only | `session.py` loads from file; no login flow anywhere |
| patchright (not playwright) | Listed as only browser dep in `pyproject.toml` |

---

## 9. Testing Strategy

| Layer | Approach | Tools |
|-------|----------|-------|
| URL builder | Pure unit tests — no browser | pytest |
| Parser | Tests against saved HTML fixtures | pytest + BeautifulSoup (for fixture gen) |
| Filter chain | Pure unit tests with synthetic candidates | pytest |
| Scorer | Pure unit tests with synthetic inputs | pytest |
| Quota manager | Unit tests with in-memory SQLite | pytest |
| Platform adapter | Integration tests with mock `page` object | pytest + AsyncMock |
| Full pipeline | E2E dry-run with saved HTML | pytest |

No test should require a live browser or internet connection.

---

## 10. Architecture Decision Records

### ADR-001: SQLite over file-based quota
**Decision:** Use SQLite for all state (quota, candidates, run history).
**Rationale:** File-based JSON quota is fragile (concurrent write corruption, slow O(n) scans for dedup). SQLite is zero-dependency, ACID, and O(1) by indexed `(external_id, platform)`.
**Trade-off:** Slightly more setup than a JSON file.

### ADR-002: patchright over vanilla playwright
**Decision:** Use `patchright` as the browser automation library.
**Rationale:** Vanilla Playwright leaks CDP fingerprint markers that LinkedIn detects. Patchright patches these vectors. Confirmed in production by the previous project.
**Trade-off:** Patchright is a third-party fork; must monitor for upstream divergence.

### ADR-003: Adapter pattern for platforms
**Decision:** Each platform is a class implementing `PlatformAdapter`.
**Rationale:** LinkedIn-specific logic (geoId, f_AL, DOM selectors) must not leak into core pipeline. Adding Glassdoor/Indeed should not require touching the filter chain.
**Trade-off:** Small amount of boilerplate per platform.

### ADR-004: Filter chain as composable callables
**Decision:** Each filter is a standalone function/class, not a monolithic `match()` function.
**Rationale:** Enables independent testing of each filter, easy reordering, and addition of new filters without regression risk.

### ADR-005: Score field on JobCandidate is mutable
**Decision:** `JobCandidate` is frozen except for `score` (added as a separate step).
**Rationale:** Scoring happens after filtering, so score is not part of the parsed data. Two options: (a) mutable score field, (b) `ScoredCandidate(candidate=..., score=...)` wrapper. Chose wrapper to keep the core schema frozen.
