---
phase: 06-skills-integration
plan: 01
subsystem: meta-skill
tags:
  - meta-skill
  - reference-synthesis
  - awaiting_human
  - orchestration
  - SKILL-04
dependency_graph:
  requires:
    - lib/pipeline_synthesizer.py (Phase 5: synthesize_pipeline, accept_synthesis, reject_synthesis)
    - lib/chunked_analyzer.py (Phase 4: analyze_chunked, estimate_chunked_cost)
    - tools/analysis/video_analyzer_selector.py (Phase 2: video_analysis capability selector)
    - skills/meta/checkpoint-protocol.md (cross-referenced, not duplicated)
  provides:
    - SKILL-04 end-to-end reference-synthesis orchestration skill
    - Agent-facing entry point for "save this reference as a reusable pipeline template"
    - Two explicit awaiting_human gates (analysis review + diff approval) as safety architecture
  affects:
    - AGENT_GUIDE.md Reference Video Entry Point (disambiguation rule lands in Plan 06-03)
    - CONTEXT.md Libraries section (tools table update lands in Plan 06-03)
    - skills/meta/video-reference-analyst.md (sister-skill disambiguation referenced from When-to-Use)
tech_stack:
  added: []
  patterns:
    - Instruction-driven meta-skill (markdown + YAML frontmatter)
    - ASCII flow diagram + numbered protocol (mirrors onboarding.md, creative-intake.md)
    - awaiting_human checkpoint cross-reference pattern (defer mechanics to checkpoint-protocol.md)
    - Exact-signature code blocks (agent copy-pastes import + call verbatim; no exploration needed)
key_files:
  created:
    - skills/meta/reference-synthesis.md (400 lines)
  modified: []
decisions:
  - "Used actual `analyze_chunked(video_path, provider_tool, ...)` signature from lib source (BaseTool instance, not provider-name string) — the plan's interfaces block had a minor drift showing `provider='auto'` as a string. Followed source-of-truth from read_first reads."
  - "Used `video_path` key + `analysis_depth: 'full'|'compact'` enum per `video_analyzer_selector.input_schema` — plan example showed `source` + `'standard'` which don't match the tool's schema."
  - "Used `estimate_chunked_cost(provider, duration_seconds, model, max_chunk_seconds)` positional shape from lib (not `estimate_chunked_cost(video_path, provider)` as shown in plan example)."
  - "Kept the single-file shape (SKILL.md only, no SKILL/reference.md split) per CONTEXT.md Claude's Discretion note."
  - "Included YAML frontmatter (name + description) at top — the prompt's success criteria required it; existing meta skills don't use frontmatter, this establishes the pattern for new SDK-compatible skills."
metrics:
  duration: "~4 minutes"
  completed_date: "2026-04-17T22:17:19Z"
  tasks_completed: 2
  files_touched: 1
  commits: 1
---

# Phase 6 Plan 01: Reference-Synthesis Meta Skill Summary

Shipped `skills/meta/reference-synthesis.md` (400 lines) — a new meta skill that teaches the agent to orchestrate video → selector → analyze (chunked if needed) → synthesize → present diff → accept/reject, with two explicit `awaiting_human` safety gates and exact-signature code blocks for every lib call.

## What Was Built

### File Created

| Path | Lines | Purpose |
|------|-------|---------|
| `skills/meta/reference-synthesis.md` | 400 | SKILL-04 end-to-end orchestration meta skill |

### Structure

Sections delivered (in order):

1. **YAML frontmatter** — `name: reference-synthesis`, `description: ...` with trigger framing
2. **H1 title** — `# Reference Synthesis — Meta Skill`
3. **## When to Use** — disambiguation table vs `video-reference-analyst.md`, 6 trigger phrases, 3 do-not-trigger routes
4. **## Scope Limits (v2.0)** — local-paths-only; staging-only writes; single-reference-per-synthesis
5. **## Workflow Overview** — ASCII flow diagram with both `[awaiting_human #1]` and `[awaiting_human #2]` markers + 8-step list
6. **### Step 1: Receive the video** — local path validation, URL rejection with PROV-01 pointer
7. **### Step 2: Select provider** — exact `registry.get_by_capability("video_analysis")[0]` code block + 4-rule preference order
8. **### Step 3: Cost estimation for long-form video** — ffprobe duration probe + `estimate_chunked_cost` call for >5 min
9. **### Step 4: Analyze** — two branches: one-shot selector (≤5 min) OR `analyze_chunked` (>5 min)
10. **### Step 5: [awaiting_human #1] Review analysis artifact** — 4-dimension summary presentation + response handling table
11. **### Step 6: Synthesize** — `synthesize_pipeline(analysis, mode="template")` with record-keys comment
12. **### Step 7: [awaiting_human #2] Review diff + approve or reject** — diff presentation + invalid-status warning protocol
13. **### Step 8: Accept or reject** — `accept_synthesis(slug)` and `reject_synthesis(slug)` terminal branches
14. **## Error Handling** — 7-row failure/action table
15. **## Anti-Patterns** — 5-item do-not list (collapsed from 7; semantics preserved)
16. **## Cross-References** — links to checkpoint-protocol.md, video-reference-analyst.md, CONTEXT.md, AGENT_GUIDE.md

## Grep Verification

| Check | Count | Expected | Status |
|-------|-------|----------|--------|
| `awaiting_human` occurrences | 10 | ≥ 2 | PASS |
| `synthesize_pipeline` citations | 7 | ≥ 1 | PASS |
| `accept_synthesis` citations | 7 | ≥ 1 | PASS |
| `reject_synthesis` citations | 3 | ≥ 1 | PASS |
| `analyze_chunked` citations | 5 | ≥ 1 | PASS |
| `video_analyzer_selector` citations | 5 | ≥ 1 | PASS |
| `checkpoint-protocol` cross-ref | 3 | ≥ 1 | PASS |
| `synthesize a pipeline` trigger | present | yes | PASS |
| `save this format as reusable` trigger | present | yes | PASS |
| Line count | 400 | 200..400 | PASS |

## Success Criteria (from prompt)

- [x] `skills/meta/reference-synthesis.md` exists, 250-400 lines (exactly 400)
- [x] YAML frontmatter with `name: reference-synthesis`, `description:`
- [x] Has "When to Use" section with trigger phrases (6 phrases listed)
- [x] Has numbered workflow steps covering the full orchestration (Steps 1-8)
- [x] Contains 2+ `awaiting_human` checkpoint markers (10 total, with heading markers at Step 5 and Step 7)
- [x] Code examples use specific imports:
  - `from lib.pipeline_synthesizer import synthesize_pipeline, accept_synthesis, reject_synthesis` ✓
  - `from lib.chunked_analyzer import analyze_chunked` (and `estimate_chunked_cost`) ✓
- [x] Cross-references `skills/meta/video-reference-analyst.md` and `skills/meta/checkpoint-protocol.md`
- [x] SUMMARY.md at `.planning/phases/06-skills-integration/06-01-SUMMARY.md`

## Deviations from Plan

### Rule 1 — Bug (Signature correction)

**1. Corrected `analyze_chunked` signature in code block**
- **Found during:** Task 2 read_first (lib/chunked_analyzer.py)
- **Issue:** Plan's `<interfaces>` example showed `analyze_chunked(video_path, provider="auto", max_workers=..., analysis_depth=..., progress_callback=...)` — but the actual function takes `provider_tool: Any` (a BaseTool instance), not a string. There is no `analysis_depth` parameter on `analyze_chunked` (it's on the selector), and there is no `progress_callback` (it's `on_chunk_done`).
- **Fix:** Documented the real signature: `analyze_chunked(video_path, provider_tool=selector, max_workers=None, on_chunk_error="fail_fast")`. Pass the selector instance directly — it satisfies the `provider_tool` protocol (has `.name`, `.provider`, `.execute({"video_path": ...})`).
- **Why:** Following the plan's wrong signature would produce code that raises `TypeError` at import-time. The plan's `read_first` instruction explicitly requires confirming signatures from source — source wins.

**2. Corrected `estimate_chunked_cost` signature**
- **Found during:** Task 2 read_first
- **Issue:** Plan's `<interfaces>` shows `estimate_chunked_cost(video_path: str, provider: str = "auto")`. Real signature is `estimate_chunked_cost(provider: str, duration_seconds: float, model: str, max_chunk_seconds: float = 300.0)` — takes a probed duration, not a path.
- **Fix:** Documented the real signature; added ffprobe duration probe as the upstream step that produces `duration_seconds`.

**3. Corrected selector input schema keys**
- **Found during:** Task 1 read_first (video_analyzer_selector.py)
- **Issue:** Plan's `<interfaces>` example shows `selector.execute({"source": "...", "analysis_depth": "standard"})`. The tool's `input_schema` uses `video_path` (required), not `source`, and the `analysis_depth` enum is `["full", "compact"]`, not `standard`.
- **Fix:** Code blocks use `{"video_path": ..., "analysis_depth": "full", "preferred_provider": "auto"}`.

All three corrections are source-of-truth driven: the skill's purpose is to give the agent copy-pasteable code. Wrong signatures would defeat that.

### No scope expansion, no architectural changes

No Rule 2 (missing critical functionality), Rule 3 (blocking issues), or Rule 4 (architectural decisions) triggered. The plan's task breakdown was well-scoped.

## STRIDE Threat Register — Disposition

| Threat ID | Category | Component | Planned Disposition | Actual Outcome |
|-----------|----------|-----------|--------------------|-----------------|
| T-06-01 | Spoofing | skill trigger routing | mitigate | **Mitigated.** `## When to Use` has explicit disambiguation block with 3 do-not-trigger rows routing to sister skills. |
| T-06-02 | Tampering | staging file integrity | accept | **Accepted.** No code block in the skill writes to `pipeline_defs/_staging/` or `pipeline_defs/` directly — all writes routed through `synthesize_pipeline` / `accept_synthesis` / `reject_synthesis`. Anti-Patterns #3 calls this out explicitly. |
| T-06-03 | Information Disclosure | analysis artifact in checkpoint presentation | mitigate | **Mitigated.** Step 5 presentation template says "inline JSON OR path to saved artifact" (agent discretion). No instruction asks agent to dump env vars or API keys. |
| T-06-04 | Elevation of Privilege | auto-approval bypass | mitigate | **Mitigated.** Anti-Patterns forbids collapsing Steps 7+8; both `awaiting_human` markers are in explicit H3 headings (Step 5 and Step 7), and also inside the ASCII flow diagram — 4 grep-verifiable anchor points so drift detection catches removal. |
| T-06-05 | Denial of Service | uncapped analyze_chunked on adversarial video | mitigate | **Mitigated.** Step 3 mandates `estimate_chunked_cost` for duration > 300s BEFORE `analyze_chunked` runs, with explicit `abort` option presented to user. |
| T-06-06 | Repudiation | skill invoked without leaving trace | accept | **Accepted.** Step 5 and Step 7 defer checkpoint-writing mechanics to `skills/meta/checkpoint-protocol.md` — existing audit trail infrastructure (`lib/checkpoint.py` via the referenced skill) produces the trace. |

## Commits

| Hash | Message |
|------|---------|
| `e32f3b3` | feat(06-01): add reference-synthesis meta skill orchestrating video->pipeline flow |

## Known Stubs

None. The skill is documentation-only — no code stubs, no placeholder functions, no hardcoded empty values. Every code block references a real function with an accurate signature verified against source.

## Self-Check: PASSED

- File `skills/meta/reference-synthesis.md` exists on disk (400 lines)
- Commit `e32f3b3` present in `git log --all`
- All PLAN `<verification>` automated checks PASS
- All prompt `<success_criteria>` items PASS
- No stubs, no unresolved threat flags, no deferred scope leaked past boundary
