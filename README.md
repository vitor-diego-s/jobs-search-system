# jobs-search-engine

A general-purpose, multi-platform job search engine that automates discovery and filtering of job listings. It owns the **search and match phases only** — outputting structured `JobCandidate` records to a SQLite database for a downstream apply pipeline to consume.

---

## What It Does

1. Runs keyword searches across job platforms (LinkedIn first, others planned)
2. Applies a configurable filter chain: exclude keywords → positive keywords → deduplication → already-seen
3. Scores candidates by relevance (title match, seniority, workplace type, recency)
4. Writes new candidates to a local SQLite database
5. Enforces daily search quotas per platform to avoid rate limiting

It does **not** apply to jobs, manage profiles, or automate logins.

---

## Architecture Overview

```
Config (settings.yaml)
        │
        ▼
  Orchestrator
  ├── QuotaManager     → gate: can we search today?
  ├── PlatformAdapter  → search + parse (LinkedIn, ...)
  ├── FilterChain      → exclude → dedup → already-seen
  ├── Scorer           → relevance score 0–100
  └── DB Writer        → SQLite upsert
```

Each platform is isolated behind a `PlatformAdapter` interface. Core pipeline logic (filtering, scoring, quota) is platform-agnostic and fully testable without a browser.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design including module structure, DB schema, interfaces, and architecture decision records.

---

## Platform Support

| Platform | Status | Auth |
|----------|--------|------|
| LinkedIn | Planned (M2) | Cookie injection |
| Glassdoor | Backlog | TBD |
| Indeed | Backlog | TBD |

---

## Configuration

All behavior is driven by `config/settings.yaml`:

```yaml
database:
  path: data/candidates.db

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
├── config/             # settings.yaml, linkedin_cookies.json
├── src/
│   ├── core/           # schemas, config models, DB layer
│   ├── pipeline/       # orchestrator, matcher, quota manager, scorer
│   ├── platforms/      # platform adapters (linkedin/, ...)
│   └── browser/        # patchright session + reusable actions
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

---

## Status

**Milestone 0 — Foundation** (current): documentation and planning complete, implementation starting.
