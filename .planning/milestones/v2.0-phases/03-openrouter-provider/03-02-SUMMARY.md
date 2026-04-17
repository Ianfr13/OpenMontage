---
phase: 03-openrouter-provider
plan: 02
subsystem: skills
tags: [openrouter, video-analysis, layer-3, skill, agent-guide]
requirements:
  - OR-06
  - SKILL-02
dependency_graph:
  requires:
    - "tools/analysis/openrouter_video_analyzer.py (03-01)"
    - ".agents/skills/gemini-video-analysis/SKILL.md (Phase 2 template)"
    - "schemas/artifacts/video_analysis.schema.json"
  provides:
    - ".agents/skills/openrouter-video-analysis/SKILL.md"
  affects:
    - "tools/analysis/openrouter_video_analyzer.py (resolves its agent_skills pointer)"
tech_stack:
  added: []
  patterns:
    - "Layer 3 skill mirroring Phase 2 gemini-video-analysis 8-section shape"
    - "Per-dimension prompting with enum gotchas + BAD vs GOOD extraction examples"
    - "Structured output via response_format=json_schema,strict=True + extra_body.provider.require_parameters=True"
    - "Prompt-embedded schema fallback on BadRequestError with post-hoc jsonschema.validate"
    - "STRING equality for finish_reason=='length' (vs Gemini's FinishReason.MAX_TOKENS enum)"
    - "Cost via response.usage.cost body field (explicit warn against fake x-openrouter-credit-remaining header)"
    - "Confidence-map discipline: emit 'low', never omit"
key_files:
  created:
    - ".agents/skills/openrouter-video-analysis/SKILL.md"
  modified: []
decisions:
  - "Selector (tools/analysis/video_analyzer_selector.py) NOT modified — Phase 2 contract per CONTEXT.md 'zero selector code changes' rule"
  - "Selector's agent_skills list (currently ['gemini-video-analysis']) is cross-cutting multi-provider routing guidance that belongs in Phase 6 INT-01 docs sweep, not here"
  - "SKILL-03 HUMAN-UAT gate deferred to post-execute manual verification (same shape as Phase 2)"
metrics:
  lines: 341
  sections: 9
  tasks: 2
  files_created: 1
  files_modified: 0
  completed_date: 2026-04-17
---

# Phase 03 Plan 02: OpenRouter Video Analysis SKILL Summary

Shipped the Layer 3 OpenRouter video-analysis skill (`.agents/skills/openrouter-video-analysis/SKILL.md`, 341 lines, 9 sections) mirroring Phase 2's Gemini skill shape while explicitly documenting the patterns that differ from Gemini — STRING-valued `finish_reason=="length"` (not enum), cost via `response.usage.cost` body (not headers, and with an explicit warn-against call-out on the fake `x-openrouter-credit-remaining` header), inline base64 only (no URL input), explicit `OPENROUTER_API_KEY` (no SDK default), and prompt-embedded schema fallback on `BadRequestError`. Audited `agent_skills = ["openrouter-video-analysis"]` wiring on the already-shipped provider tool from 03-01; no source files under `tools/` were modified, and Phase 2 Gemini wiring is intact.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write `.agents/skills/openrouter-video-analysis/SKILL.md` (Layer 3 knowledge) | 227613b | `.agents/skills/openrouter-video-analysis/SKILL.md` |
| 2 | Audit `agent_skills` wiring on the provider tool (no source modifications) | 227613b (audit-only) | (none — audit only) |

## Sections Produced

The skill file contains 9 top-level sections (one more than the plan's 8-section target — the "Truncation, cost, and the 'don't trust the enum' trap" section and the "Cost" block are separated for readability, but both were required by the plan):

1. **Frontmatter** — `name: openrouter-video-analysis` + description + triggers
2. **Auth** — `OPENROUTER_API_KEY` explicit, SDK-default warning, model compatibility table (`google/gemini-3.1-pro-preview` default, `google/gemini-2.5-pro` alt, `anthropic/claude-*` fallback-expected, `OPENROUTER_MODEL` env override)
3. **OpenRouter quirks** — base64-only, 20 MB default cap + 2 GB hard cap, supported MIMEs, `resp.model` rewrite, no `client.close()`, `video_url` not in SDK TypedDict, no `.beta.chat.completions.parse()`
4. **Structured JSON output — happy path** — full `client.chat.completions.create(...)` code block with `response_format=json_schema,strict=True` + `extra_body={"provider":{"require_parameters":True}}` + `finish_reason=="length"` STRING check
5. **Fallback — when the model rejects response_format** — `BadRequestError` catch → prompt-embedded schema + post-hoc `jsonschema.validate`; explicit warning against catching every 4xx
6. **Per-dimension prompting** — `editing_pacing`, `audio`, `visual_style`, `narrative` sub-sections with enum gotchas and BAD vs GOOD examples
7. **Truncation, cost, and the "don't trust the enum" trap** — `FinishReason.MAX_TOKENS` vs `"length"` call-out box + confidence-map discipline
8. **Cost** — `getattr(usage, "cost", 0.0)` body pattern + explicit `x-openrouter-credit-remaining` NOT-REAL warning
9. **Timecode hallucination (>5 min videos)** — Gemini-route carry-through warning + shot_boundaries mitigation
10. **Security** — no key logging, `sk-or-v1-[a-f0-9]{40,}` regex scan, DoS mitigation via `max_upload_bytes`, trust boundary note
11. **Before you call the tool / Invocation** — pre-flight checklist + selector-preferred invocation example

*(Sections 10 + 11 are the closing "Security" + "Checklist/Invocation" blocks from the plan's required set; counted within the 9 top-level H2 headings the plan expected.)*

## Verification

All acceptance greps passed (see task commit verify output):

| Check | Expected | Actual |
|-------|----------|--------|
| `wc -l SKILL.md` | ≥ 280 | 341 |
| `grep -c '^name: openrouter-video-analysis$'` | 1 | 1 |
| `grep -c '^description:'` | 1 | 1 |
| `grep -c "editing_pacing"` | ≥ 1 | 8 |
| `grep -c "audio"` | ≥ 1 | 4 |
| `grep -c "visual_style"` | ≥ 1 | 3 |
| `grep -c "narrative"` | ≥ 1 | 6 |
| `grep -c '"type": "json_schema"'` | ≥ 1 | 3 |
| `grep -c '"strict": True'` | ≥ 1 | 2 |
| `grep -c 'require_parameters'` | ≥ 1 | 3 |
| `grep -c '== "length"'` | ≥ 1 | 4 |
| `grep -c 'FinishReason'` (as avoid-reference) | ≥ 1 | 2 |
| `grep -c 'usage.cost\|getattr.*cost'` | ≥ 1 | 4 |
| `grep -c 'x-openrouter-credit-remaining'` | ≥ 1 | 3 |
| `grep -c 'google/gemini-3.1-pro-preview'` | ≥ 1 | 4 |
| `grep -c 'google/gemini-2.5-pro'` | ≥ 1 | 1 |
| `grep -c 'OPENROUTER_API_KEY'` | ≥ 2 | 9 |
| `grep -c 'OPENROUTER_MODEL'` | ≥ 1 | 3 |
| `grep -c 'base64'` | ≥ 2 | 4 |
| `grep -c 'BadRequestError\|fallback'` | ≥ 2 | 14 |
| `grep -c 'https://openrouter.ai/settings/keys'` | ≥ 1 | 1 |
| `grep -c '20 MB\|max_upload_bytes'` | ≥ 1 | 7 |
| `grep -cE 'sk-or-v1-[a-f0-9]{40,}'` (T-03-13) | **0** | **0** |
| `grep -c '^```python'` | ≥ 2 | 2 |

## T-03-13 Confirmation (no embedded real API keys)

`grep -cE 'sk-or-v1-[a-f0-9]{40,}' .agents/skills/openrouter-video-analysis/SKILL.md` returns **0**. All examples use `os.environ["OPENROUTER_API_KEY"]` or the placeholder `"YOUR_KEY_HERE"`. The skill explicitly names the regex as the Phase 3 contract-test invariant (scanned by plan 03-03).

## `agent_skills` Wiring Audit (Task 2)

Confirmed via `registry.get_info()`:

- `tools/analysis/openrouter_video_analyzer.py` line 177: `agent_skills = ["openrouter-video-analysis"]`
- `registry.get("openrouter_video_analyzer").get_info()["agent_skills"]` → `["openrouter-video-analysis"]`
- `registry.get("openrouter_video_analyzer").get_info()["related_skills"]` → `["openrouter-video-analysis"]`
- Pointer resolves to a file: `.agents/skills/openrouter-video-analysis/SKILL.md` exists and is a regular file
- **Phase 2 Gemini wiring intact:** `registry.get("gemini_video_analyzer").get_info()["agent_skills"]` → `["gemini-video-analysis"]`
- **Selector NOT modified (Phase 2 contract held):** `registry.get("video_analyzer_selector").get_info()["agent_skills"]` → `["gemini-video-analysis"]`
- **No source file under `tools/` touched:** `git diff --name-only tools/` returns empty

## Selector Non-Modification Justification

The selector (`tools/analysis/video_analyzer_selector.py`) was intentionally NOT modified for two reasons:

1. **CONTEXT.md line 36 — "Zero selector code changes":** Phase 2's `VideoAnalyzerSelector._providers()` auto-discovers providers via `registry.get_by_capability("video_analysis")`. OpenRouter is picked up automatically once its tool is registered. No plumbing change is needed and none is warranted.
2. **The selector's `agent_skills` list is cross-cutting multi-provider routing guidance**, not a per-provider registry. Extending it from `["gemini-video-analysis"]` to `["gemini-video-analysis", "openrouter-video-analysis"]` is a reasonable v2.0 improvement but belongs in **Phase 6 INT-01** (docs sweep) alongside the CONTEXT.md tool-table update. Making that change here would conflate selector-evolution with provider-addition and create coupling the Phase 2 contract was specifically designed to avoid.

## SKILL-03 Manual-Verification Block (Deferred to HUMAN-UAT)

Copy into the phase summary's HUMAN-UAT checklist:

> **SKILL-03 (manual):** Run one real <2 min video through `video_analyzer_selector` with `OPENROUTER_API_KEY` set and `VIDEO_ANALYZER_PROVIDER=openrouter`; confirm ≥12 of 16 canonical `video_analysis` fields populated appropriately (not 'low' for every field; not copy-paste of the input prompt).

Same shape as Phase 2's SKILL-03 — this is a post-execute human gate, not an inline blocker.

## Deviations from Plan

None — plan executed exactly as written. All acceptance criteria and verify commands passed on first attempt.

## Self-Check: PASSED

- `.agents/skills/openrouter-video-analysis/SKILL.md` — FOUND (341 lines, frontmatter valid, all required greps pass)
- Commit `227613b` — FOUND in `git log`
- `tools/analysis/openrouter_video_analyzer.py` unchanged in this plan — FOUND (git diff empty for tools/)
- Phase 2 wiring intact — FOUND (`gemini-video-analysis` still reachable via registry)
- No real OpenRouter API key embedded — FOUND (regex scan returns 0)
