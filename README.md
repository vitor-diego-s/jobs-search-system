# jobs-search-engine

A general-purpose, multi-platform job search engine that automates discovery and filtering of job listings. It owns the **search and match phases only** — outputting structured `JobCandidate` records to a SQLite database for a downstream apply pipeline to consume.

---

## What It Does

1. Runs keyword searches across job platforms (LinkedIn first, others planned)
2. Fetches full job descriptions from listing side-panels
3. Applies a configurable filter chain: exclude keywords → positive keywords → deduplication → already-seen
4. Scores candidates by relevance using a **dual-scorer pipeline**:
   - Rule-based: title keyword match, seniority, easy_apply, remote, recency
   - LLM-assisted: sends structured profile + job description to an LLM for semantic evaluation
   - Blended: `0.4 × rule_score + 0.6 × llm_score`
5. Extracts `scoring_keywords` from your resume PDF via LLM analysis
6. Writes new candidates to a local SQLite database
7. Enforces daily search quotas per platform to avoid rate limiting

It does **not** apply to jobs, manage profiles, or automate logins.

---

## Architecture Overview

```
Config (settings.yaml) + Profile (profile.yaml)
        │
        ▼
  Orchestrator
  ├── QuotaManager     → gate: can we search today?
  ├── PlatformAdapter  → search + parse + fetch descriptions (LinkedIn, ...)
  ├── FilterChain      → exclude → dedup → already-seen
  ├── Scorer           → rule-based relevance score 0–100
  ├── LLM Scorer       → LLM-assisted scoring (optional, blended with rules)
  │   └── LLM Provider → gemini | anthropic | openai | ollama
  └── DB Writer        → SQLite upsert (score + llm_score + llm_reasoning)
```

Each platform is isolated behind a `PlatformAdapter` interface. Core pipeline logic (filtering, scoring, quota) is platform-agnostic and fully testable without a browser.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design including module structure, DB schema, interfaces, and architecture decision records.

---

## Platform Support

| Platform | Status | Auth |
|----------|--------|------|
| LinkedIn | Complete (M2–M10) | Cookie injection |
| Glassdoor | Backlog | TBD |
| Indeed | Backlog | TBD |

---

## Configuration

All behavior is driven by `config/settings.yaml`:

```yaml
database:
  path: data/candidates.db

profile_path: config/profile.yaml   # Resume-derived profile for LLM scoring

quotas:
  linkedin:
    max_searches_per_day: 2
    max_candidates_per_day: 150

searches:
  - keyword: "Senior Python Engineer"
    platform: linkedin
    filters:
      geo_id: 92000000        # Worldwide
      workplace_type: [remote]
      easy_apply_only: true
      max_pages: 3
    exclude_keywords:
      - Junior
      - PHP
      - Frontend
    scoring_keywords:          # LLM-extracted skills for title matching + LLM context
      - Python
      - FastAPI
      - PostgreSQL
    fetch_description: false   # Enable job description extraction

scoring:
  llm_enabled: false           # Enable dual-scorer pipeline
  llm_provider: gemini         # gemini | anthropic | openai | ollama
  rule_weight: 0.4
  llm_weight: 0.6
```

---

## Usage

```bash
# Standard run
python main.py --config config/settings.yaml

# Dry run (no browser, no DB writes)
python main.py --config config/settings.yaml --dry-run

# Export results
python main.py --config config/settings.yaml --export json
```

> **Note:** LinkedIn requires pre-exported cookies at `config/linkedin_cookies.json`. Login automation is explicitly out of scope.

---

## Anti-Detection Requirements

For browser-based platforms (LinkedIn), these are hard constraints — not configurable:

- `headless=False` always (patchright anti-detection patches require headed mode)
- Randomized delays between all actions (scroll: 1.5–3s, page: 3–7s, keyword: 5–12s)
- Single browser session per run
- Cookie-based auth only — no login automation

---

## Development

### Requirements

- Python 3.12+
- [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (browser automation)
- pydantic v2
- pytest

### Project Structure

```
jobs-search-engine/
├── config/             # settings.yaml, profile.yaml, linkedin_cookies.json
├── src/
│   ├── core/           # schemas, config models, DB layer
│   ├── pipeline/       # orchestrator, matcher, quota manager, scorer, llm_scorer
│   ├── platforms/      # platform adapters (linkedin/, ...)
│   ├── profile/        # resume extraction, LLM analyzer, profile schema
│   │   └── llm/        # provider adapters (anthropic, gemini, openai, ollama)
│   └── browser/        # patchright session + reusable actions
├── scripts/            # benchmark_llm_scoring.py, extract_cookies.py
├── tests/
│   ├── unit/           # pure logic tests (no browser required)
│   ├── integration/    # full pipeline with mock adapter
│   └── fixtures/       # saved HTML pages for parser tests
├── docs/               # PRD, architecture, lessons
└── tasks/              # milestone checklist
```

### Testing

No test requires a live browser or internet connection.

```bash
pytest tests/unit/
pytest tests/integration/
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/PRD.md`](docs/PRD.md) | Product requirements, goals, open questions |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design, interfaces, DB schema, ADRs |
| [`docs/lessons-applied.md`](docs/lessons-applied.md) | Engineering lessons from the previous iteration |
| [`tasks/todo.md`](tasks/todo.md) | Milestone checklist |
| [`tasks/plan-m10.md`](tasks/plan-m10.md) | M10 LLM-assisted relevance scoring implementation plan |

---

## Status

**Milestone 10 — LLM-Assisted Relevance Scoring** (current): 301 tests passing. Full pipeline operational: LinkedIn search, description fetching, rule-based + LLM-assisted dual scoring, multi-provider support (Gemini, Anthropic, OpenAI, Ollama).
