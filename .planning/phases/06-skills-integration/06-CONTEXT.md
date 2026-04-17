# Phase 6: Skills + Integration - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, tight cadence)

<domain>
## Phase Boundary

Close the loop: document the end-to-end reference-synthesis workflow in the agent instruction layer and finalize integration docs. Three deliverables: (1) `skills/meta/reference-synthesis.md` meta skill orchestrating `video → selector → analyze (chunked if needed) → synthesize → present diff → approve/reject`; (2) refactor existing `skills/meta/video-reference-analyst.md` to consume structured `video_analysis` artifact fields as primary path (freeform fallback only when structured absent); (3) update `AGENT_GUIDE.md` Reference Video Entry Point with disambiguation (concepts only → video-reference-analyst; pipeline synthesis → reference-synthesis); update `CONTEXT.md` tools table with new tools/analysis rows; finalize `requirements.txt` (already done — confirm); document env vars in `lib/env_loader.py`.

Out of scope: tests (Phase 7). All code already shipped — this phase is docs + integration.

</domain>

<decisions>
## Implementation Decisions

### Plan Decomposition (3 plans, parallel-safe)
- `06-01-PLAN.md` — `skills/meta/reference-synthesis.md` new meta skill (orchestrates the full flow with 2 `awaiting_human` checkpoints). SKILL-04.
- `06-02-PLAN.md` — refactor `skills/meta/video-reference-analyst.md` to consume structured video_analysis fields with freeform fallback. SKILL-05, SKILL-06 (partial — disambiguation).
- `06-03-PLAN.md` — `AGENT_GUIDE.md` Reference Video Entry Point disambiguation + `CONTEXT.md` tools table extension + `lib/env_loader.py` env var documentation. INT-01, INT-02 (verify already-pinned deps), INT-03. SKILL-06 (disambiguation rule fully landed).

### Reference-Synthesis Meta Skill Shape (SKILL-04)
- Markdown document at `skills/meta/reference-synthesis.md`, ~250-350 lines
- Frontmatter: `name: reference-synthesis, description: ...`
- Sections:
  1. When to invoke (trigger phrases: "synthesize a pipeline from this reference", "make this video's format reusable", "save this reference as a template")
  2. Workflow overview (5 steps: receive video → select provider → analyze → synthesize → approve/reject)
  3. Step 1: receive video (local path or URL fetch; refuse URL for now — local only in v2.0)
  4. Step 2: select provider via `video_analyzer_selector` (explain preference order)
  5. Step 3: analyze (call `analyze_chunked` from `lib/chunked_analyzer.py` if duration >5min, else direct selector call)
  6. Step 4: **Checkpoint 1 — human review of analysis artifact** (awaiting_human); present canonical fields, ask if shape looks right before synthesis
  7. Step 5: `synthesize_pipeline(analysis, mode="template")` — produces staging YAML
  8. Step 6: present diff (read staging YAML + base pipeline, show unified diff)
  9. Step 7: **Checkpoint 2 — human approval** (awaiting_human); user says accept/reject
  10. Step 8: `accept_synthesis(slug)` or `reject_synthesis(slug)`
- Two `awaiting_human` checkpoints MUST be explicitly called out — this is the safety gate
- Code examples show exact function imports and call signatures

### Video-Reference-Analyst Refactor (SKILL-05)
- Existing skill produces "concepts" output (subjective analysis); refactor to ALSO consume structured fields when caller provides video_analysis artifact
- Add a new "## Structured Path" section that:
  - Accepts optional `analysis_artifact` parameter
  - When present: consume `editing_pacing`, `audio`, `visual_style`, `narrative` fields directly; skip freeform extraction
  - When absent: fall back to existing freeform flow (backward compat — SKILL-05 requirement)
- Preserve existing "## Creative Response" section for backward compat
- Add cross-reference to `skills/meta/reference-synthesis.md` when user intent is "synthesize a pipeline" (not concept generation)

### AGENT_GUIDE Disambiguation (SKILL-06)
- Edit `AGENT_GUIDE.md` Reference Video Entry Point section (exists at lines 17-48)
- Add a disambiguation block: "When user says X → route to Y":
  - "make me a video like this" / "use this as inspiration" → `video-reference-analyst.md` (existing flow)
  - "synthesize a pipeline from this" / "save this format as reusable" / "make a template" → `reference-synthesis.md` (NEW flow)
- Agent reading AGENT_GUIDE alone must reach synthesis skill in ≤2 hops (count hops: AGENT_GUIDE → reference-synthesis.md = 1 hop)

### CONTEXT.md Update (INT-01)
- Existing `CONTEXT.md` at /workspace/CONTEXT.md has a tools table (check structure during planning)
- Add rows for:
  - `video_analyzer_selector` (capability=video_analysis, provider=selector)
  - `gemini_video_analyzer` (capability=video_analysis, provider=gemini)
  - `openrouter_video_analyzer` (capability=video_analysis, provider=openrouter)
- Add new "Libraries" section (if not present) for:
  - `lib/video_chunker.py`, `lib/analysis_merger.py`, `lib/chunked_analyzer.py`, `lib/pipeline_synthesizer.py`, `lib/llm_fill.py`, `lib/schema_adapter.py`, `lib/analysis_errors.py`

### requirements.txt (INT-02)
- Already finalized in Phase 2/3/5: `google-genai>=1.73,<2`, `openai>=1.0,<3`, `ruamel.yaml>=0.18,<0.20`
- Phase 6 audits + confirms no conflicting deps; no changes expected

### Env Vars (INT-03)
- Update `lib/env_loader.py` (or equivalent doc block) to document:
  - `GEMINI_API_KEY` / `GOOGLE_API_KEY` (Gemini direct, priority order: GEMINI first per tool override)
  - `OPENROUTER_API_KEY` (OpenRouter provider)
  - `GEMINI_VIDEO_MODEL` (default `gemini-3.1-pro-preview`, fallback `gemini-2.5-pro`)
  - `OPENROUTER_MODEL` (default `google/gemini-3.1-pro-preview`)
  - `VIDEO_ANALYZER_PROVIDER` (override: `gemini|openrouter|auto`, default `auto`)
  - `VIDEO_CHUNK_WORKERS` (default 4, clamped [1, 8])
  - `VIDEO_SYNTH_LLM_FILL` (default based on OPENROUTER_API_KEY presence)

### Claude's Discretion
- Exact trigger phrases in reference-synthesis skill — planner can refine
- Whether to add a high-level flow diagram (ASCII art) — recommend yes, adds ≤20 lines for major clarity
- Whether to split meta skill into SKILL.md + reference.md for detail — recommend single SKILL.md (matches reference-analyst + onboarding patterns)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `skills/meta/video-reference-analyst.md` — EXISTING skill to refactor (not replace)
- `skills/meta/onboarding.md`, `skills/meta/reviewer.md`, `skills/meta/checkpoint-protocol.md` — shape templates for meta skill
- `skills/meta/creative-intake.md` — similar pattern for "receive creative input → orchestrate" workflow
- `AGENT_GUIDE.md` Reference Video Entry Point section — already exists at lines 17-48; Phase 6 EDITS it (targeted, not wholesale)
- `CONTEXT.md` at repo root — existing tools table (structure TBD during execution)
- `lib/env_loader.py` or similar — read during planning to confirm path

### Established Patterns
- Meta skills live in `skills/meta/` with `name: <kebab-name>` frontmatter
- Two-checkpoint flows (analysis review + final approval) exist in similar creative skills
- Layer 3 references use `agent_skills: [name]` on BaseTool, but meta skills reference libs directly via Python import syntax in code blocks

</code_context>

<specifics>
## Specific Ideas

- `awaiting_human` checkpoint pattern from `checkpoint-protocol.md` — reference it directly rather than re-documenting
- Use unified-diff output for diff presentation (already produced by `lib/pipeline_synthesizer.py::_write_synthesis_record` via `diff_against_base`)
- SKILL.md frontmatter description should trigger the skill when user mentions "synthesize pipeline" / "save as template" / "reusable format"

</specifics>

<deferred>
## Deferred Ideas

- Video URL fetch (YouTube, etc.) — v2.1 (PROV-01)
- Interactive diff UI (SYNTH2-02) — v2.1
- Auto-regenerate on analysis tweak (SYNTH2-03) — v2.1

</deferred>
