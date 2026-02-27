# M10 — LLM-Assisted Relevance Scoring

## Context

Rule-based scoring (M4) works on structural signals only: title keyword match, seniority, easy_apply, remote, recency. It is **blind to job descriptions** — a perfect-fit job with a generic title scores low, while a bad-fit job with the right keywords scores high.

M9 now provides `description_snippet` (full job description text). M10 uses an LLM to evaluate how well each job matches the user's `ProfileData` (resume/preferences from `config/profile.yaml`), then blends the LLM score with the rule-based score via configurable weights.

**Default LLM:** Gemini 2.0 Flash (cheap, fast, paid plan available via `GOOGLE_API_KEY` in `.env`).

## Design Decisions

1. **Weighted blending:** `final = (rule_weight × rule_score) + (llm_weight × llm_score)`, default 0.4/0.6. Both scores always computed for candidates with descriptions.
2. **Skip LLM for empty descriptions:** Candidates without `description_snippet` keep rule-based score only. Users must enable `fetch_description: true` per search to get meaningful LLM scores.
3. **Generalize `complete()` signature** (not a new method): Add optional `system` kwarg to existing `LLMProvider.complete()`. Each provider changes ~2 lines. Backward-compatible — callers that don't pass `system` get the existing resume-analysis prompt.
4. **Provider instantiation once per batch** in `score_candidates_llm()`, passed to each candidate scorer. Avoids re-importing SDK per candidate.
5. **Graceful failure (L12):** LLM error on any candidate → keep rule-based score, log warning, continue batch.
6. **Persist LLM breakdown:** Add `llm_score` and `llm_reasoning` to `ScoredCandidate` + DB for debugging/benchmarking.

## Implementation Plan

### Step 1 — Extend `ScoringConfig` and `Settings` (`src/core/config.py`)

Add to `ScoringConfig`:
```python
llm_enabled: bool = False
llm_provider: str = "gemini"
llm_model: str | None = None          # None = provider default
rule_weight: float = Field(default=0.4, ge=0.0, le=1.0)
llm_weight: float = Field(default=0.6, ge=0.0, le=1.0)
```

Add `model_validator` to enforce `rule_weight + llm_weight == 1.0` when `llm_enabled=True`.

Add to `Settings`:
```python
profile_path: str = "config/profile.yaml"
```

### Step 2 — Generalize `LLMProvider.complete()` with `system` kwarg

**`src/profile/llm/base.py`** — Update ABC signature:
```python
def complete(self, resume_text: str, model: str | None = None, *, system: str | None = None) -> str:
```

**Each provider** (4 files) — 2-line change per file:
- Add `*, system: str | None = None` to signature
- Replace hardcoded `SYSTEM_PROMPT` with `system if system is not None else SYSTEM_PROMPT`

| Provider file | System prompt usage |
|---|---|
| `src/profile/llm/gemini.py` | `system_instruction=use_system` in `GenerativeModel()` |
| `src/profile/llm/anthropic.py` | `system=use_system` in `client.messages.create()` |
| `src/profile/llm/openai.py` | `{"role": "system", "content": use_system}` |
| `src/profile/llm/ollama.py` | Same as OpenAI |

Backward-compatible: `llm_analyzer.py` calls `provider.complete(resume_text, model=model)` — no `system` arg → falls back to `SYSTEM_PROMPT`.

### Step 3 — Extend `ScoredCandidate` (`src/core/schemas.py`)

```python
class ScoredCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    candidate: JobCandidate
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    llm_score: float | None = None      # NEW: raw LLM score (None = not LLM-scored)
    llm_reasoning: str = ""              # NEW: LLM explanation
```

Backward-compatible — both fields have defaults.

### Step 4 — DB schema evolution (`src/core/db.py`)

Add `_add_column_if_missing()` helper. Call in `init_db()`:
```python
_add_column_if_missing(conn, "candidates", "llm_score", "REAL")
_add_column_if_missing(conn, "candidates", "llm_reasoning", "TEXT NOT NULL DEFAULT ''")
```

Update `upsert_candidate()` to persist `llm_score` and `llm_reasoning`.

### Step 5 — New module: `src/pipeline/llm_scorer.py`

Core scoring module (~130 lines). Key components:

**`_SCORING_SYSTEM_PROMPT`** — Instructs LLM to return JSON `{"score": 0-100, "reasoning": "..."}` with a 5-tier rubric (90-100 perfect, 70-89 strong, 50-69 moderate, 30-49 weak, 0-29 poor). Evaluation criteria ordered: role alignment > skills overlap > seniority > workplace > description relevance.

**`_build_user_prompt(candidate, profile) -> str`** — Assembles:
- Profile section: name, target roles, seniority, skills, years, workplace prefs
- Job section: title, company, location, workplace_type, posted_time, easy_apply, description

**`_parse_llm_score(raw_text) -> tuple[float, str]`** — Parses JSON response (handles markdown wrapping). Clamps score 0-100. Raises `ValueError` on malformed response.

**`score_candidate_llm(scored, profile, config, provider) -> ScoredCandidate`**:
- Skip if `description_snippet` empty → return original
- Build prompt → call `provider.complete(prompt, system=_SCORING_SYSTEM_PROMPT, model=config.llm_model)`
- Parse response → blend: `(rule_weight × rule_score) + (llm_weight × llm_score)`
- On any exception → log warning, return original scored candidate
- Return new `ScoredCandidate(candidate, score=blended, llm_score=llm_score, llm_reasoning=reasoning)`

**`score_candidates_llm(scored_list, profile, config) -> list[ScoredCandidate]`**:
- If `not config.llm_enabled` → return unchanged
- Instantiate provider once: `provider = get_provider(config.llm_provider)`
- Score each candidate, re-sort by blended score descending

### Step 6 — Wire into orchestrator (`src/pipeline/orchestrator.py`)

**`run_all_searches()`** — Load profile once if `scoring.llm_enabled`:
```python
profile: ProfileData | None = None
if settings.scoring.llm_enabled:
    profile = _load_profile(settings.profile_path)
```

Pass `profile` to `run_search()` (new optional param).

**`run_search()`** — Add step 4b between scoring and DB upsert:
```python
# Step 4b: LLM scoring (optional)
if settings.scoring.llm_enabled and profile is not None:
    scored = score_candidates_llm(scored, profile, settings.scoring)
```

**`_load_profile(path) -> ProfileData | None`** — Helper that loads profile, returns `None` on failure with warning.

**`export_results_json()`** — Add `llm_score` and `llm_reasoning` to export dict.

### Step 7 — Update `config/settings.yaml`

```yaml
scoring:
  # ... existing rule-based weights unchanged ...
  # LLM scoring (M10)
  llm_enabled: false       # set to true to enable
  llm_provider: gemini
  llm_model: null          # null = provider default (gemini-2.0-flash)
  rule_weight: 0.4
  llm_weight: 0.6

profile_path: config/profile.yaml
```

### Step 8 — Tests

**New: `tests/unit/test_llm_scorer.py`** (~20 tests):

| Test class | Tests |
|---|---|
| `TestBuildUserPrompt` | includes profile context, includes job data, handles empty description, includes description when present |
| `TestParseLlmScore` | valid JSON, markdown-wrapped, clamped >100, clamped <0, missing reasoning defaults, invalid JSON raises, missing score raises |
| `TestScoreCandidateLlm` | blends correctly (mock LLM=80, rule=50 → 0.4×50+0.6×80=68), skips empty description, LLM failure → fallback, parse failure → fallback, populates llm_score/llm_reasoning |
| `TestScoreCandidatesLlm` | disabled returns unchanged, re-sorts after blending, mixed with/without descriptions, partial failure doesn't crash batch |

**Update: `tests/unit/test_config.py`** — New `ScoringConfig` fields, weight validator.

**Update: `tests/unit/test_schemas.py`** — `ScoredCandidate.llm_score` / `llm_reasoning` defaults.

**Update: `tests/unit/test_llm_providers.py`** — `complete()` with custom `system` kwarg for each provider.

**Update: `tests/integration/test_search_pipeline.py`** — Pipeline with LLM scoring enabled (mock provider).

### Step 9 — Benchmarking script (`scripts/benchmark_llm_scoring.py`)

Standalone developer script (not in main pipeline, lives in `scripts/`):
1. Load candidates from DB (or JSON fixture)
2. Load `config/profile.yaml`
3. Score with Gemini 2.0 Flash → log scores + reasoning
4. Score with Anthropic Opus 4.6 (`llm_model: "claude-opus-4-6"`) → log scores + reasoning
5. Output comparison table: title, rule_score, gemini_score, opus_score, reasoning
6. Compute agreement metrics (correlation, mean absolute difference)

No code changes needed for Opus support — `AnthropicProvider` already accepts model override.

### Step 10 — Update `tasks/todo.md`

Add M10 milestone section. Update backlog (add benchmarking as post-M10 item).

## Files Summary

| File | Change |
|------|--------|
| `src/core/config.py` | Add LLM fields to `ScoringConfig`, `profile_path` to `Settings` |
| `src/core/schemas.py` | Add `llm_score`, `llm_reasoning` to `ScoredCandidate` |
| `src/core/db.py` | Schema evolution + update `upsert_candidate` |
| `src/profile/llm/base.py` | Add `system` kwarg to `complete()` ABC |
| `src/profile/llm/gemini.py` | Use `system` kwarg (~2 lines) |
| `src/profile/llm/anthropic.py` | Use `system` kwarg (~2 lines) |
| `src/profile/llm/openai.py` | Use `system` kwarg (~2 lines) |
| `src/profile/llm/ollama.py` | Use `system` kwarg (~2 lines) |
| `src/pipeline/llm_scorer.py` | **New** — LLM scoring module |
| `src/pipeline/orchestrator.py` | Wire step 4b + profile loading + export fields |
| `config/settings.yaml` | Add LLM scoring config section |
| `tests/unit/test_llm_scorer.py` | **New** — ~20 tests |
| `tests/unit/test_config.py` | ScoringConfig LLM fields + weight validator |
| `tests/unit/test_schemas.py` | ScoredCandidate new fields |
| `tests/unit/test_llm_providers.py` | `complete()` with custom system |
| `tests/integration/test_search_pipeline.py` | Pipeline with LLM scoring |
| `scripts/benchmark_llm_scoring.py` | **New** — benchmarking script |
| `tasks/todo.md` | M10 checklist |

## Data Flow (updated)

```
1. Quota gate
2. Adapter search → raw candidates
3. Filter chain → filtered candidates
4. Rule-based scorer → scored candidates
4b. LLM scorer (if enabled + profile loaded) → re-scored candidates
5. DB upsert (blended score + llm breakdown)
6. Record quota
```

## Verification

1. `ruff check src/ tests/ main.py` — passes
2. `mypy src/ main.py` — passes
3. `pytest tests/ -v` — all existing + new tests pass (~280+)
4. `llm_enabled: false` (default) → zero LLM calls, no regression, all 257 existing tests pass
5. `llm_enabled: true` + mock provider → candidates with descriptions get blended scores, without descriptions keep rule-based
6. Weight validator: `rule_weight=0.3, llm_weight=0.5` → raises ValueError
7. LLM failure for one candidate → others still scored, no crash
8. JSON export includes `llm_score` and `llm_reasoning`
9. DB roundtrip: `llm_score` and `llm_reasoning` persisted
10. Benchmark script runs against both Gemini Flash and Opus with comparison output
