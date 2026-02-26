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

## Milestone 6 — Orchestrator + CLI ✓

**Goal:** `python main.py` runs a search, writes to DB, prints summary.

- [x] `src/pipeline/orchestrator.py` — wires: quota → adapter → filter → score → DB write
- [x] `main.py` — CLI (argparse): `--config`, `--dry-run`, `--export json`, `--verbose`
- [x] Integration test with mock adapter: full pipeline without browser (10 tests)

**Verification:**
- [x] `ruff check src/ tests/ main.py` — passes
- [x] `mypy src/ main.py` — passes (0 issues, 21 source files)
- [x] `pytest tests/ -v` — 191 tests passed (181 existing + 10 new)
- [x] Pipeline data flow: quota gate → adapter.search → filter chain → score → DB upsert → record quota
- [x] Dedup filter shared across keyword searches (cross-keyword deduplication)
- [x] Quota blocks second search when limit=1
- [x] Already-seen candidates filtered on rerun
- [x] Scores sorted descending
- [x] Candidates and search_runs persisted in DB
- [x] JSON export format correct

---

## Milestone 7 — Live Run + Validation ✓

**Goal:** Confirmed working against live LinkedIn.

- [x] Cookie extraction script (`scripts/extract_cookies.py`)
- [x] Manual run with real cookies + 2 keywords (5 pages total)
- [x] Verify: 25 cards parsed per page (not 14 — L6 fix)
- [x] Verify: company names populated — 0/90 empty (L12 fix + L16 occlusion fix)
- [x] Verify: no title `\n` duplicates (L5 fix + L17 `<strong>` extraction)
- [x] Verify: quota enforced across 2 CLI invocations (BLOCKED on 2nd dry-run)

**Bugs found and fixed:**
- [x] L16: Virtual DOM occlusion — cards outside viewport stripped to 16B empty shells. Fix: `scrollIntoView` + 150ms wait before parsing each card.
- [x] L17: Title extraction — `<a>` text_content starts with `\n` + whitespace, L5 `split('\n')[0]` returned empty. Fix: use `<strong>` element text (priority 1), aria-label (priority 2), strip-then-split (priority 3).

**Verification:**
```
$ python main.py -v
Search complete: 125 raw, 90 filtered, 90 new candidates written to DB.
  'Senior Python Engineer': 75 raw, 70 filtered, 70 new
  'Staff Backend Engineer Python': 50 raw, 20 filtered, 20 new

Empty titles: 0/90, Empty companies: 0/90, Titles with \n: 0
Quota: BLOCKED on second invocation (2/2 searches today)
```

---

## Milestone 8 — Dynamic Keywords Extraction ✓

**Goal:** Extract profile from resume PDF via Claude API, generate settings.yaml.

- [x] `src/profile/schema.py` — `ProfileData` Pydantic model with `from_yaml`/`to_yaml`
- [x] `src/profile/extractor.py` — PDF text extraction via `pymupdf` (optional dep)
- [x] `src/profile/llm_analyzer.py` — Claude API resume analysis → `ProfileData`
- [x] `src/profile/generator.py` — `ProfileData` → `settings.yaml` generation
- [x] `src/core/config.py` — added `scoring_keywords` to `SearchConfig`
- [x] `src/pipeline/scorer.py` — wired `scoring_keywords` (score boost only, no hard filter)
- [x] `src/pipeline/orchestrator.py` — pass `scoring_keywords` through pipeline
- [x] `main.py` — subcommand CLI: `search` (default), `extract-profile`, `generate-config`
- [x] `pyproject.toml` — optional deps `[profile]`, mypy overrides
- [x] `config/profile.yaml.example` — documented example
- [x] Unit tests: 32 new (226 total)

**Verification:**
- [x] `ruff check src/ tests/ main.py` — passes
- [x] `mypy src/ main.py` — passes (0 issues, 26 source files)
- [x] `pytest tests/ -v` — 226 tests passed (194 existing + 32 new)
- [x] Backward compat: `python main.py --dry-run` still works (no subcommand = search)
- [x] Roundtrip: `ProfileData` → `generate_settings_dict` → `Settings.model_validate` succeeds
- [x] Scorer: `scoring_keywords` + `require_keywords` accumulate title_match_bonus

---

## Milestone 8b — LLM Provider Adapter Pattern ✓

**Goal:** Adapter pattern for LLM providers so users can swap between Anthropic, OpenAI, Gemini, Ollama.

- [x] `src/profile/llm/base.py` — `LLMProvider` ABC + shared `SYSTEM_PROMPT` and `parse_response`
- [x] `src/profile/llm/anthropic.py` — `AnthropicProvider` (extracted from `llm_analyzer.py`)
- [x] `src/profile/llm/openai.py` — `OpenAIProvider` (GPT-4o-mini default)
- [x] `src/profile/llm/gemini.py` — `GeminiProvider` (Gemini 2.0 Flash default)
- [x] `src/profile/llm/ollama.py` — `OllamaProvider` (local, OpenAI-compatible API)
- [x] `src/profile/llm/__init__.py` — Provider registry with lazy loading
- [x] `src/profile/llm_analyzer.py` — Refactored to thin facade (backward-compat preserved)
- [x] `main.py` — Added `--provider` flag to `extract-profile` subcommand
- [x] `pyproject.toml` — Granular optional deps (`[anthropic]`, `[openai]`, `[gemini]`, `[profile-all]`)
- [x] `docs/PRD.md` — Section 10: LLM Provider Research (benchmarking table, cost estimates, guide)
- [x] Unit tests: 22 new (248 total)

**Verification:**
- [x] `ruff check src/ tests/ main.py` — passes
- [x] `mypy src/ main.py` — passes (0 issues, 32 source files)
- [x] `pytest tests/ -v` — 248 tests passed (226 existing + 22 new)
- [x] Backward compat: `analyze_resume("text")` defaults to Anthropic
- [x] Backward compat: `_parse_response` re-exported (existing 8 tests pass unchanged)
- [x] CLI: `--provider openai` accepted, `--provider nope` rejected
- [x] Unknown provider: `get_provider("nope")` → clear ValueError

---

## Backlog (Post-MVP)

- [ ] Description fetching (opt-in, +2-3s per job) (M9)
- [ ] LLM-assisted relevance scoring (M10) — deferred from OQ-2
- [ ] Email/notification when N new candidates found (M11)
- [ ] Web UI for reviewing candidates (M12)
- [ ] Export to Notion or Airtable (M13)
- [ ] Glassdoor adapter (M14)