# Research: LinkedIn "Requirements added by the job poster" Section

**Date:** 2026-03-03
**Status:** Discovery complete, implementation pending
**Branch:** `feat/requirements-section-visa-filter`

---

## Problem

The `DescriptionExcludeFilter` checks `description_snippet` for visa phrases (e.g., "authorized to work", "visa sponsorship"). However, LinkedIn places these phrases in a **separate "Requirements added by the job poster" section** that our pipeline never captures.

## Evidence — DB Candidates

| external_id | Title | Company | Visa Phrase (on LinkedIn) |
|---|---|---|---|
| `4379980427` | Staff ML Engineer | Storm3 | "Authorized to work in the United States" |
| `4378121014` | Senior Python Dev | SwissPine Tech | "Authorized to work in Philippines" |

Both candidates have `description_snippet` populated (1271 and 2272 chars respectively) but **no visa phrases** in that text.

## Root Cause — DOM Analysis

Diagnostic script: `scripts/diagnose_description.py`

### Search Panel Mode (how our pipeline works)

- `#job-details` exists and contains the job description body (1424-2419 chars)
- The "Requirements added by the job poster" section is **NOT rendered** in the search side panel
- Only one sibling of `#job-details`: `div.jobs-description__details` (11 chars, negligible)
- **Visa phrases are completely absent from the DOM** in this mode

### Direct View Mode (`/jobs/view/{id}/`)

- `#job-details` does **NOT exist** — completely different DOM (CSS module hashes)
- "Requirements added by the job poster" section IS present
- Visa phrases ARE present (e.g., `<p class='_0b0793cb c33da4c6 ...'>`)
- All class names are CSS module hashes — **not stable for selectors**
- The section has this structure:
  ```
  <p class="_0b0793cb b9ecf803 ...">Requirements added by the job poster</p>
  <p class="_0b0793cb c33da4c6 ...">* Authorized to work in ...</p>
  ```
- These are siblings within a container ~1500-2300 chars, using hashed class names

### Key Finding

The requirements section is a **LinkedIn platform feature**, not part of the employer's job description. LinkedIn only renders it on the **full job view page**, not in the **search results side panel** that our adapter uses.

## LLM Inference Test (Strategy 2)

Tested whether Gemini can infer visa restrictions from the side-panel description alone (without the hidden requirements section).

### Results

| Job | Explicit Visa? | Gemini Inference | Confidence | Correct? |
|---|---|---|---|---|
| Storm3 (Staff ML Eng) | No | **YES flag** — "US (remote)", $225k, US recruiter | 95% | CORRECT |
| SwissPine Tech (Sr Python) | No | **NO flag** — "global platforms" suggests open | 85% | **WRONG** |

### Analysis

- **Storm3**: Strong implicit signals (US-only remote, high USD salary, startup context) — LLM inferred correctly.
- **SwissPine Tech**: Description actively misleads — "global platforms", "global stakeholders" made the LLM *more confident* there were no restrictions. But the hidden section requires Philippine work authorization.

**Conclusion:** LLM inference alone is **unreliable** for visa detection — catches obvious cases but produces dangerous false negatives when the description has misleading "global" language.

## Possible Solutions

### Option A: Navigate to full job view page (recommended)

After the search panel extraction, navigate to `/jobs/view/{external_id}/` for each candidate and extract the requirements section from the full page.

**Pros:**
- Captures the actual LinkedIn-added requirements section
- Reliable — directly reads the data

**Cons:**
- Extra page load per candidate (~3-5s each with anti-detection delays)
- Different DOM structure (CSS module hashes, no `#job-details`)
- Need text-based detection: find "Requirements added by the job poster" text node, then extract sibling text
- More network requests = higher detection risk

### Option B: LinkedIn API / hidden endpoints

Check if LinkedIn has a public or semi-public API that returns the requirements section as structured data.

**Pros:** Fast, no DOM parsing needed
**Cons:** Likely requires authentication, may violate ToS, endpoints may change

### Option C: Hybrid — LLM inference with profile context

Enhance the LLM scoring prompt to explicitly flag visa/work-auth concerns for the candidate's geography. Accept the false negative risk for edge cases.

**Pros:** No extra page loads, uses existing pipeline
**Cons:** Unreliable for cases like SwissPine Tech (demonstrated above)

### Option D: Full-page navigation only for top-N candidates

Only fetch the full job view page for candidates that pass the filter chain and score above a threshold — reduces the number of extra page loads.

**Pros:** Balances reliability with performance
**Cons:** Still need to solve the DOM parsing for the full page

## Files

| File | Purpose |
|---|---|
| `scripts/diagnose_description.py` | Diagnostic script — tests both panel and direct view modes |
| `docs/research/requirements-section-discovery.md` | This document |
| `tasks/todo.md` | Backlog item added |

## Next Steps

1. Choose a solution strategy (A or D recommended)
2. Implement full-page navigation + text-based requirements extraction
3. Add visa phrase detection to the filter chain using the new data source
4. Test with the two known candidates above
