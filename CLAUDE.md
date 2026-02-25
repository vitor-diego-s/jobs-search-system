# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`jobs-search-engine` - A jobs search engine for multiple platforms 
## (heavily inspired by Boris Cherny's Claude Code practices)

### 1. Plan Node Default
- Enter **plan mode first** for ANY task that is non-trivial (≥3 logical steps, selector changes, filter logic, quota behavior, anti-detection impact)
- Write concrete plan → `tasks/todo.md` (checklist style)
- Include verification steps **in the plan** (mock tests, dry-run example, schema check)
- If behavior surprises you or fails verification → STOP, re-plan, don't force through

### 2. Subagent / Parallel Thinking Strategy
- Use subagents (or simulated sub-roles in chat) when exploring options in parallel:
  • "Act as Selector Researcher" → propose & rank 3–4 fallback selectors
  • "Act as Scroll Debugger" → analyze why only 14 cards load
  • "Act as Matcher Critic" → find holes in exclude_keywords logic
- Keep main chat clean: offload research / variants / what-if analysis
- For expensive questions (e.g. "how does LinkedIn behave with geoId X?") → suggest opening a dedicated research chat

### 3. Self-Improvement & Lesson Capture
- After **any correction, bug, or surprise behavior** from me:
  1. Write root cause
  2. Write 1–3 concrete rules / patterns to prevent recurrence
  3. Append to `docs/lessons-from-claude.md` or `tasks/lessons.md`
- At start of session: quickly scan latest lessons for relevant warnings (selectors, scroll, quota, title dup, company empty, etc.)

### 4. Verification Before Considering Done
- Never claim complete without evidence:
  - Unit test pass (or updated golden data)
  - Dry-run / example output matches expected JobCandidate shape
  - No regressions in previously working keywords
  - Anti-detection invariants preserved (delays, headed, single session)
  - Quota gate tested (simulate limit reached → no network)
- Ask yourself: "Would this survive a LinkedIn A/B test or minor DOM tweak next week?"

### 5. Demand Elegance (but stay pragmatic)
- After first working version: pause and ask "Is there a cleaner / more robust way?"
  Examples: better selector resilience, simpler scroll loop exit, more declarative filter chain
- Skip for 5-minute hotfixes (broken selector → just add fallback)

### 6. Autonomous Bug Fixing Expectation
- When I paste logs, failing tests, bad output JSON, wrong parsed fields → **just fix it**
- Point to root cause → propose minimal change → show before/after diff
- No need to ask "what do you think is wrong?" — assume senior-level debugging

### Task Flow Default (when no other instruction given)
1. **Plan** → write numbered checklist to `tasks/todo.md` (or inline if small)
2. **Confirm plan** → wait for my OK or refinements
3. **Execute** → step-by-step, mark items [x] as done
4. **Verify** → show tests / output / dry-run
5. **Summarize changes** → high-level diff explanation
6. **Capture lessons** → update lessons file if anything broke or was surprising