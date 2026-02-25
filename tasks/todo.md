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

## Milestone 2 — LinkedIn Adapter (URL + Parser)

**Goal:** URL builder and DOM parser fully tested with HTML fixtures.

- [ ] `src/platforms/base.py` — `PlatformAdapter` abstract class
- [ ] `src/platforms/linkedin/selectors.py` — selector constants with fallbacks
- [ ] `src/platforms/linkedin/searcher.py` — URL builder + pagination logic
- [ ] `src/platforms/linkedin/parser.py` — DOM → `JobCandidate` (with L5+L12 fixes)
- [ ] `tests/fixtures/linkedin_results_page.html` — saved real page for parser tests
- [ ] Unit tests: URL builder (all params), parser (title, company, id, url, dates)

**Verification:**
- Title never contains `\n`
- `external_id` parsed from `data-job-id` (not URL)
- Company field returns `""` (not crash) when selector misses
- All URL params roundtrip correctly

---

## Milestone 3 — Browser Session + Scroll

**Goal:** Working browser session and scroll-until-stable action.

- [ ] `src/browser/session.py` — patchright init, cookie loading
- [ ] `src/browser/actions.py` — `scroll_until_stable()`, `random_sleep()` with floor enforcement
- [ ] Integration test: mock page object → `scroll_until_stable()` terminates correctly

**Verification:**
- `random_sleep(min, max)` never sleeps less than `min`
- `scroll_until_stable()` calls stop when card count stabilizes

---

## Milestone 4 — Filter Chain + Scorer

**Goal:** Matcher and scorer working, independently tested.

- [ ] `src/pipeline/matcher.py` — `ExcludeKeywordsFilter`, `PositiveKeywordsFilter`, `DeduplicationFilter`, `AlreadySeenFilter`
- [ ] `src/pipeline/scorer.py` — rule-based scoring (title match, seniority, remote, recency)
- [ ] Unit tests: each filter in isolation, full chain with synthetic data

**Verification:**
- Synthetic run: 10 candidates in, 3 after exclude, 2 after dedup, 1 after already_seen
- Score range: 0–100 (no overflow)

---

## Milestone 5 — Quota Manager

**Goal:** Quota gate prevents over-searching, resets daily.

- [ ] `src/pipeline/quota_manager.py` — `can_search()`, `record_search()`, `remaining_candidates()`
- [ ] Unit tests: date rollover resets counters, gate blocks when limit reached

**Verification:**
- Running 2 searches on the same day: 2nd succeeds, 3rd blocked
- Day rollover: counters reset to 0

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

## Backlog (Post-MVP)

- [ ] Glassdoor adapter (M8)
- [ ] Description fetching (opt-in, +2-3s per job) (M9)
- [ ] LLM-assisted relevance scoring (M10) — deferred from OQ-2
- [ ] Email/notification when N new candidates found (M11)
- [ ] Web UI for reviewing candidates (M12)
- [ ] Export to Notion or Airtable (M13)
