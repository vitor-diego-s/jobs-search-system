# Project Task List
# jobs-search-engine

**Started:** 2026-02-24
**Methodology:** Plan → Confirm → Execute → Verify → Summarize → Capture lessons

---

## Milestone 0 — Foundation ✓

- [x] Write PRD (`docs/PRD.md`)
- [x] Write Architecture (`docs/ARCHITECTURE.md`)
- [x] Write lessons-applied (`docs/lessons-applied.md`)
- [x] Answer open questions (OQ-1 through OQ-4 in PRD.md)
  - OQ-1: Defer platform choice until LinkedIn is stable
  - OQ-2: Rule-based scoring first; LLM scoring in backlog
  - OQ-3: Shared DB between search and apply projects
  - OQ-4: Per-search config (`fetch_description: true`)
- [x] Create `pyproject.toml` (Python 3.12, patchright, pydantic v2, pytest)
- [x] Initialize project structure (dirs, empty `__init__.py`)
- [x] Set up pre-commit hooks (ruff, mypy)
- [x] Create `.gitignore`

---

## Milestone 1 — Core Schemas and DB ✓

**Goal:** Importable models and working DB layer with tests.

- [x] `src/core/schemas.py` — `JobCandidate`, `ScoredCandidate`, `SearchRunResult`
- [x] `src/core/config.py` — `Settings`, `SearchConfig`, `QuotasConfig` (Pydantic v2)
- [x] `src/core/db.py` — SQLite init, `candidates`, `quota`, `search_runs` tables
- [x] `config/settings.yaml` — example configuration (LinkedIn remote Python search)
- [x] Unit tests: schemas validation, config loading, DB upsert + dedup

**Verification:**
- [x] `ruff check src/ tests/` — passes
- [x] `mypy src/` — passes (0 issues, 9 source files)
- [x] `pytest tests/unit/` — 47 tests passed
- [x] Inserting same `(external_id, platform)` twice → single row in DB
- [x] Config loading from YAML validates correctly
- [x] Invalid config raises readable Pydantic errors

---

## Milestone 2 — LinkedIn Adapter (URL + Parser) ✓

**Goal:** URL builder and DOM parser fully tested with HTML fixtures.

- [x] `src/platforms/base.py` — `PlatformAdapter` abstract class
- [x] `src/platforms/linkedin/selectors.py` — selector constants with fallbacks
- [x] `src/platforms/linkedin/searcher.py` — URL builder + pagination logic
- [x] `src/platforms/linkedin/parser.py` — DOM → `JobCandidate` (with L5+L12 fixes)
- [x] `src/platforms/linkedin/adapter.py` — skeleton adapter (M3 TODOs for scroll/sleep)
- [x] `tests/fixtures/linkedin_results_page.html` — reference HTML fixture
- [x] Unit tests: URL builder (38 tests), parser (18 tests) — 57 new, 104 total

**Verification:**
- [x] `ruff check src/ tests/` — passes
- [x] `mypy src/` — passes (0 issues, 14 source files)
- [x] `pytest tests/unit/` — 104 tests passed
- [x] Title never contains `\n` (L5)
- [x] `external_id` parsed from `data-occludable-job-id` attr (fallback `data-job-id`)
- [x] Company field returns `""` (not crash) when selector misses (L12)
- [x] `is_easy_apply` from config, not DOM (L2)
- [x] All URL params roundtrip correctly
- [x] Unknown filter values skipped with warning

---

## Milestone 3 — Browser Session + Scroll ✓

**Goal:** Working browser session and scroll-until-stable action.

- [x] `src/browser/session.py` — patchright init, cookie loading, headless=False hardcoded
- [x] `src/browser/actions.py` — `scroll_until_stable()`, `random_sleep()` with floor enforcement
- [x] `src/platforms/linkedin/adapter.py` — wired scroll + inter-page delays (replaced M3 TODOs)
- [x] Unit tests: actions (14 tests), session/cookies (9 tests) — 23 new, 127 total

**Verification:**
- [x] `ruff check src/ tests/` — passes
- [x] `mypy src/` — passes (0 issues, 16 source files)
- [x] `pytest tests/unit/` — 127 tests passed
- [x] `random_sleep(min, max)` never sleeps less than `min` (floor enforcement)
- [x] `scroll_until_stable()` stops when card count stabilizes (L6)
- [x] Scroll delay floor 1.5s enforced regardless of caller args (L7)
- [x] Inter-page delay 3-7s wired in adapter (L7)
- [x] Cookie loading handles missing file, invalid JSON, non-array gracefully

---

## Milestone 4 — Filter Chain + Scorer ✓

**Goal:** Matcher and scorer working, independently tested.

- [x] `src/pipeline/matcher.py` — `ExcludeKeywordsFilter`, `PositiveKeywordsFilter`, `DeduplicationFilter`, `AlreadySeenFilter`, `run_filter_chain()`
- [x] `src/pipeline/scorer.py` — rule-based scoring (title match, seniority, easy apply, remote, recency decay)
- [x] Unit tests: matcher (22 tests), scorer (18 tests) — 40 new, 167 total

**Verification:**
- [x] `ruff check src/ tests/` — passes
- [x] `mypy src/` — passes (0 issues, 18 source files)
- [x] `pytest tests/unit/` — 167 tests passed
- [x] Synthetic run: 10 in → 3 excluded → 1 deduped → 1 already_seen → 5 surviving
- [x] Score range: 0-100 (clamped, never overflows or goes negative)
- [x] Each filter independently testable and composable

---

## Milestone 5 — Quota Manager ✓

**Goal:** Quota gate prevents over-searching, resets daily.

- [x] `src/pipeline/quota_manager.py` — `can_search()`, `record_search()`, `remaining_candidates()`, `record_candidates()`
- [x] Unit tests: 14 new tests, 181 total

**Verification:**
- [x] `ruff check src/ tests/` — passes
- [x] `mypy src/` — passes (0 issues, 19 source files)
- [x] `pytest tests/unit/` — 181 tests passed
- [x] 2 searches on same day: 2nd succeeds, 3rd blocked
- [x] Day rollover: yesterday's quota does not affect today
- [x] Platform isolation: linkedin quota doesn't affect glassdoor
- [x] Unknown platform always allowed (no config = no limit)

---

## Milestone 6 — Orchestrator + CLI

**Goal:** `python main.py` runs a search, writes to DB, prints summary.

- [ ] `src/pipeline/orchestrator.py` — wires: quota → adapter → filter → score → DB write
- [ ] `main.py` — CLI (argparse or click): `--config`, `--dry-run`, `--export json`
- [ ] Integration test with mock adapter: full pipeline without browser

**Verification (dry-run):**
```
$ python main.py --config config/settings.yaml --dry-run
[DRY RUN] 2 searches configured
[DRY RUN] Quota check: OK (0/2 searches used today)
[DRY RUN] Would write 0 candidates (no browser in dry-run)
```

---

## Milestone 7 — Live Run + Validation

**Goal:** Confirmed working against live LinkedIn.

- [ ] Manual run with real cookies + 1 keyword
- [ ] Verify: 25 cards parsed per page (not 14 — L6 fix)
- [ ] Verify: company names populated (not empty — L12 fix)
- [ ] Verify: no title `\n` duplicates (L5 fix)
- [ ] Verify: quota enforced across 2 CLI invocations

**Verification:**
```
$ python main.py --config config/settings.yaml
...
Search complete: 50 raw, 12 filtered, 12 new candidates written to DB.
```

---

## Milestone 8 - Improve Matcher and Scorer capabilities
[TODO] 
- current - user is collecting, analysing and categorizing jobs from current linkeding recommendations
- [] Should review the list of constraints for job removal ( CLT + hibrido + junior + etc )

## Backlog (Post-MVP)

- [ ] Glassdoor adapter (M8)
- [ ] Description fetching (opt-in, +2-3s per job) (M9)
- [ ] LLM-assisted relevance scoring (M10) — deferred from OQ-2
- [ ] Email/notification when N new candidates found (M11)
- [ ] Web UI for reviewing candidates (M12)
- [ ] Export to Notion or Airtable (M13)
