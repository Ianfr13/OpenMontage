# Architecture: v2.0 Reference Synthesis Integration

**Project:** OpenMontage
**Milestone:** v2.0 Reference Synthesis
**Researched:** 2026-04-17
**Confidence:** HIGH — based on direct reading of all referenced source files

---

## Summary

The v2.0 Reference Synthesis capability adds two new execution phases on top of
the existing pipeline system: a **structured analysis phase** (reference video →
`video_analysis` artifact with 4-dimensional extraction) and a **synthesis phase**
(analysis artifact → validated `pipeline_defs/<name>.yaml`). The synthesized
pipeline is then run as a normal production pipeline — no special execution path.

The existing architecture supports this addition without structural changes to
`lib/`, `tools/tool_registry.py`, `lib/pipeline_loader.py`, or any existing
selectors. The registry auto-discovers new tools by inheritance; `pipeline_loader`
reads any `.yaml` in `pipeline_defs/` on demand; no hot-reload mechanism is needed
or appropriate. The key insight from reading the code: **discovery happens at call
time (`registry.discover()`) and manifest loading happens per call (`load_pipeline(name)`),
so files written to disk are immediately available without restart.**

---

## Data Flow

The full reference-synthesis data flow is a two-phase pre-production step that
feeds the normal production loop.

```
Phase 1 — Analysis
──────────────────
User provides URL or path
        │
        ▼
[video_analyzer_selector] ─── routes based on capability="video_analysis" ───►
        │
        ▼
[gemini_video_analyzer]  (or future providers)
  · calls Gemini Pro 3.1 Multimodal API
  · extracts: editing+rhythm, audio, visual style, narrative
  · returns structured dict validated against
    schemas/artifacts/video_analysis.schema.json
        │
        ▼
analysis artifact: projects/<name>/artifacts/video_analysis.json
  · Checkpoint written (status=awaiting_human)
  · Agent enriches with own vision (keyframes already present from
    existing video_analyzer tool if standard depth used first)
  · Human approval gate: "Does this analysis look correct?"

Phase 2 — Synthesis
────────────────────
video_analysis.json  +  existing pipeline_defs/*.yaml  (similarity matching)
        │
        ▼
[pipeline_synthesizer]   (lib/pipeline_synthesizer.py — see below)
  · reads video_analysis artifact
  · reads all existing pipeline_defs/ via pipeline_loader.list_pipelines()
  · runs matching layer: cosine/feature similarity → base pipeline selection
  · constructs new manifest dict reusing existing director skill paths
  · validates against schemas/pipelines/pipeline_manifest.schema.json
  · writes pipeline_defs/<slug>.yaml to disk
        │
        ▼
pipeline_synthesis artifact: projects/<name>/artifacts/pipeline_synthesis.json
  (contains: chosen base pipeline, diff summary, new manifest path, match score)
        │
        ▼
Checkpoint written (status=awaiting_human)
Human approval gate: review diff, approve or reject
        │
(approved)
        ▼
pipeline_defs/<slug>.yaml  is now persisted and registry-discoverable

Phase 3 — Normal Production Run (separate agent session)
──────────────────────────────────────────────────────────
Agent: "make a video using pipeline <slug>"
  → load_pipeline("<slug>")  — reads the just-written YAML
  → normal stage execution: research → proposal → script → assets → edit → compose
```

---

## New Files to Create

### Python Tools

| File | Class | Capability | Tier | Notes |
|------|-------|-----------|------|-------|
| `tools/analysis/gemini_video_analyzer.py` | `GeminiVideoAnalyzer` | `video_analysis` | `ToolTier.ANALYZE` | Calls Gemini Pro 3.1 multimodal API. Structured extraction against 4-dimension schema. |
| `tools/analysis/video_analyzer_selector.py` | `VideoAnalyzerSelector` | `video_analysis` | `ToolTier.ANALYZE` | Mirrors `video_selector` pattern exactly. Discovers providers by `capability="video_analysis"`, routes by preference/availability. |

**Why `tools/analysis/` not `tools/understanding/`:** The `analysis/` subdirectory
already exists and contains `video_analyzer.py` (the structural/local analyzer),
`scene_detect.py`, `frame_sampler.py`, etc. Adding Gemini-powered analysis there
follows the existing family convention. There is no `tools/understanding/` directory
and no precedent to create one — all comprehension/extraction tools live in
`tools/analysis/`.

### Python Lib Utility

| File | Class/Functions | Notes |
|------|----------------|-------|
| `lib/pipeline_synthesizer.py` | `PipelineSynthesizer` | NOT a `BaseTool`. Reason: it writes files to `pipeline_defs/` (a structural mutation of the repo), not artifacts to `projects/`. Tools produce consumable outputs; this is a build-time utility. Follows `lib/` pattern of cross-pipeline infrastructure (see `lib/playbook_generator.py`, `lib/source_media_review.py`). Exposes: `synthesize(analysis_artifact: dict) -> dict` returning synthesis artifact. |

**Matching layer** lives inside `lib/pipeline_synthesizer.py` as a private method,
not as a separate file. It needs to read `pipeline_defs/*.yaml` (via `pipeline_loader`)
and compare structural features from the analysis artifact (pacing style, visual types,
motion required, pipeline recommendation from `replication_guidance.suggested_pipeline`).
This is ~50-100 lines of feature comparison logic, not a standalone module.

### JSON Schemas

| File | Validates | Notes |
|------|-----------|-------|
| `schemas/artifacts/video_analysis.schema.json` | Output of `GeminiVideoAnalyzer` | The existing `video_analysis_brief.schema.json` covers the `VideoAnalyzer` (structural/local) output. The Gemini tool produces a richer 4-dimension artifact. New schema extends the same envelope with `editing_rhythm`, `audio_profile`, `visual_style`, `narrative_structure` sections. |
| `schemas/artifacts/pipeline_synthesis.schema.json` | Output of `PipelineSynthesizer` | Records: `source_analysis_path`, `base_pipeline`, `match_score`, `synthesized_pipeline_name`, `synthesized_pipeline_path`, `diff_summary` (list), `director_skills_reused` (list), `validation_passed` (bool). |

**Note:** The existing `video_analysis_brief.schema.json` (used by `VideoAnalyzer`) is
NOT replaced — it remains as-is. The new `video_analysis.schema.json` is for the
Gemini structured output, which covers different (richer) fields.

### Layer 2 Skills

| File | Purpose |
|------|---------|
| `skills/meta/reference-synthesis.md` | New meta skill orchestrating the full analysis → synthesis → approval workflow. This is the analog of `skills/meta/video-reference-analyst.md` but for pipeline generation (not production). It teaches the agent: how to invoke `video_analyzer_selector`, how to invoke `pipeline_synthesizer`, how to present the diff to the user, and how to checkpoint. |

**Why a new meta skill instead of extending `video-reference-analyst.md`:**
`video-reference-analyst.md` orchestrates production (analysis → proposal → pipeline
execution). `reference-synthesis.md` orchestrates pipeline creation (analysis →
synthesis → pipeline saved). They have different outputs and different checkpoints.
Merging them would violate single-responsibility and break the existing reference
analyst workflow.

**No new `skills/reference-synthesis/` pipeline directory.** Synthesis is not a
production pipeline — it does not have stages like `script`, `assets`, `edit`. It
is a 2-step pre-production workflow driven by a meta skill. Creating a fake pipeline
for it would require `pipeline_defs/reference-synthesis.yaml` and fake director
skills, which would be architecturally misleading.

### Layer 3 Skill

| File | Purpose |
|------|---------|
| `.agents/skills/gemini-video-analysis/SKILL.md` | Layer 3 vendor knowledge for Gemini multimodal video API: which models to use, how to structure the prompt for 4-dimension extraction, token/context limits for video, API auth pattern, structured output mode (JSON schema enforcement), known quirks, cost per minute of video analyzed. |

**Location rationale:** All Layer 3 vendor skills live in `.agents/skills/<tech>/`.
The `video-understand` skill already exists there (general video understanding). The
new skill is specific to Gemini's video analysis API and structured extraction use
case, warranting its own directory.

---

## Modified Files

| File | Change | Why |
|------|--------|-----|
| `skills/meta/video-reference-analyst.md` | Refactor Step 1 to consume structured `video_analysis` artifact fields instead of freeform summary. Update step references to new artifact schema keys (`editing_rhythm`, `audio_profile`, `visual_style`, `narrative_structure`). | PROJECT.md explicitly requires this refactor. The existing skill uses generic `VideoAnalysisBrief` freeform fields; v2.0 binds it to the canonical structured schema. |
| `AGENT_GUIDE.md` — Reference Video Entry Point section | Add paragraph: when user provides reference video AND requests pipeline synthesis (not just inspiration), agent should read `skills/meta/reference-synthesis.md` instead of (or before) `video-reference-analyst.md`. | New entry point must be documented where agents look first. |
| `schemas/artifacts/video_analysis_brief.schema.json` | Add `motion_type` per-scene field (already in `VideoAnalyzer` code but may not be in schema). Minor additive change only. | Ensure schema matches what `video_analyzer.py` already emits. Non-breaking. |
| `lib/checkpoint.py` — `CANONICAL_STAGE_ARTIFACTS` mapping | Add entries: `"video_analysis"` → `"schemas/artifacts/video_analysis.schema.json"` and `"pipeline_synthesis"` → `"schemas/artifacts/pipeline_synthesis.schema.json"`. | Checkpoint write validates canonical artifacts by name lookup. Without this, `write_checkpoint` will fail to validate new artifact types. |
| `CONTEXT.md` — tools/analysis table | Add `video_analyzer_selector` and `gemini_video_analyzer` rows. Add Layer 3 column entry `gemini-video-analysis`. | Keeps the context map accurate for future agents. |

---

## Integration Points

### 1. Registry auto-discovery — no changes needed

`GeminiVideoAnalyzer` and `VideoAnalyzerSelector` both inherit from `BaseTool`.
`tools/tool_registry.py` uses `pkgutil.walk_packages` over the `tools/` package
tree. Placing files in `tools/analysis/` is sufficient — they will be discovered
on the next `registry.discover()` call. **No changes to `tool_registry.py`.**

### 2. Selector pattern — exact mirror of `video_selector`

`VideoAnalyzerSelector` discovers providers via:
```python
registry.get_by_capability("video_analysis")
```
`GeminiVideoAnalyzer` declares `capability = "video_analysis"`. Adding future
providers (e.g., `openai_video_analyzer.py`) requires only creating the file —
no selector code changes. This is the same pattern used by `tts_selector`,
`image_selector`, and `video_selector`.

### 3. Pipeline loader — on-demand, no hot-reload needed

`lib/pipeline_loader.py::load_pipeline(name)` reads `pipeline_defs/<name>.yaml`
on every call. `list_pipelines()` globs `pipeline_defs/*.yaml` on every call.
There is no registry of pipeline names that needs updating. A synthesized pipeline
written to `pipeline_defs/my-pipeline.yaml` is immediately loadable via
`load_pipeline("my-pipeline")` without restart. **No hot-reload mechanism
needed; do not add one.**

### 4. `lib/pipeline_synthesizer.py` — not a tool, not a pipeline stage

The synthesizer writes files. Tools return `ToolResult` objects and write to
`projects/`. The synthesizer's output is a YAML in `pipeline_defs/` — a structural
change to the repo's instruction layer. This maps to the `lib/` pattern:
`lib/playbook_generator.py` writes to `styles/`, `lib/source_media_review.py`
processes source footage. The agent calls the synthesizer directly (by importing
and running it), not via the tool registry.

### 5. Human approval integration with `checkpoint-protocol.md`

The existing checkpoint protocol defines `human_approval_default` per pipeline
stage. The synthesis workflow runs outside a pipeline — it is pre-pipeline. The
`skills/meta/reference-synthesis.md` skill must explicitly teach the checkpoint
behavior:

- After `video_analysis` artifact produced: checkpoint with `status=awaiting_human`.
  Present the analysis summary. Gate: "Does this correctly describe the reference?"
- After `pipeline_synthesis` artifact produced: checkpoint with `status=awaiting_human`.
  Present the YAML diff vs. the base pipeline and the new manifest. Gate: "Approve
  to save this pipeline to `pipeline_defs/`."

These checkpoints are **ad-hoc** (not driven by a pipeline manifest's
`human_approval_default`). `skills/meta/reference-synthesis.md` teaches the
checkpointing manually, referencing the same `lib/checkpoint.py` utilities.
The project directory for a synthesis run uses `projects/_synthesis/<slug>/`.

### 6. `AGENT_GUIDE.md` entry point disambiguation

The existing guide says: "When user provides a video URL → read
`skills/meta/video-reference-analyst.md`." Post-v2.0, there are two paths:

- "Make me a video like this" → `video-reference-analyst.md` (production)
- "Synthesize a pipeline from this reference" → `reference-synthesis.md`
  (pipeline creation)

The guide's Reference Video Entry Point section needs a disambiguation rule.
One paragraph addition, no restructuring.

---

## Build Order

Dependencies flow strictly; each item blocks the next group.

```
Group 1 — Schema contracts (block everything else)
  1a. schemas/artifacts/video_analysis.schema.json
  1b. schemas/artifacts/pipeline_synthesis.schema.json
  1c. Update lib/checkpoint.py CANONICAL_STAGE_ARTIFACTS with 1a + 1b

Group 2 — Layer 3 vendor knowledge (blocks tool prompt quality)
  2.  .agents/skills/gemini-video-analysis/SKILL.md

Group 3 — Selector (blocks tool from being routable)
  3.  tools/analysis/video_analyzer_selector.py
      (can be written before GeminiVideoAnalyzer; selector discovers dynamically)

Group 4 — Provider tool (needs Group 1 schemas for output validation, Group 2 for prompt)
  4.  tools/analysis/gemini_video_analyzer.py
      agent_skills = ["gemini-video-analysis"]
      output validates against schemas/artifacts/video_analysis.schema.json

Group 5 — Synthesis utility (needs Group 1b schema, needs pipeline_loader)
  5.  lib/pipeline_synthesizer.py
      reads: lib/pipeline_loader (already exists)
      writes: pipeline_defs/<slug>.yaml
      output artifact validates against schemas/artifacts/pipeline_synthesis.schema.json

Group 6 — Layer 2 meta skill (needs Groups 2-5 to reference accurately)
  6a. skills/meta/reference-synthesis.md
  6b. Refactor skills/meta/video-reference-analyst.md (needs Group 1a field names)

Group 7 — Agent entry point update (needs Groups 1-6)
  7a. Update AGENT_GUIDE.md entry point section
  7b. Update CONTEXT.md tools map

Group 8 — Test coverage
  8a. tests/contracts/ — schema validation tests for new artifacts
  8b. tests/qa/ — integration test: 2-3 real reference videos → analysis → synthesis
  8c. E2E: synthesized pipeline → normal production run (renders a real video)
```

---

## Risks and Unknowns

### Risk 1: `video_analysis.schema.json` vs `video_analysis_brief.schema.json` collision

**Problem:** There are already `schemas/artifacts/video_analysis_brief.schema.json`
(used by `VideoAnalyzer`) and the new `schemas/artifacts/video_analysis.schema.json`
(for `GeminiVideoAnalyzer`). Two "video analysis" schemas will confuse future agents
and the `lib/checkpoint.py` artifact lookup.

**Mitigation options:**
1. Name the Gemini schema `video_analysis_deep.schema.json` — clearer differentiation.
2. Consolidate: extend `video_analysis_brief.schema.json` with optional v2 fields
   (`editing_rhythm`, `audio_profile`, `visual_style`, `narrative_structure`) and
   have both tools write to the same schema version. The brief's fields become a
   subset.
3. Name based on tool output: `gemini_video_analysis.schema.json`.

**Recommendation:** Option 2 (extend `video_analysis_brief.schema.json`). A single
schema with `version: "2.0"` and new optional fields is backward-compatible and
prevents schema proliferation. Both `VideoAnalyzer` and `GeminiVideoAnalyzer` write
the same schema; the Gemini tool fills more fields. Checkpoint lookup stays simple.
**This is a decision the phase planner should surface explicitly.**

### Risk 2: Idempotency of `pipeline_synthesizer` writes

**Problem:** If the agent runs synthesis twice on the same reference (e.g., retry
after approval rejection), `pipeline_defs/<slug>.yaml` will be overwritten silently.
Pipeline names derived from the reference title could collide with existing pipelines.

**Mitigation:** `PipelineSynthesizer` must:
1. Generate slug from reference title + truncated hash of the analysis artifact,
   not just title (prevents collisions with existing pipelines).
2. Check if `pipeline_defs/<slug>.yaml` exists before writing; if so, either
   increment (`slug-v2`) or require explicit `overwrite=True`.
3. Store `synthesized_pipeline_path` in the `pipeline_synthesis` artifact so the
   agent can present it in the checkpoint and the user can inspect the file.

### Risk 3: Gemini API structured output mode vs. freeform parsing

**Problem:** The 4-dimension extraction requires Gemini to return structured JSON
matching `video_analysis.schema.json`. Gemini Pro supports `response_mime_type:
application/json` with a schema constraint, but the schema passed to the API must
be a simplified subset (Gemini's JSON schema support has known limitations with
`$ref`, `oneOf`, and nested `enum`). If the tool passes the full schema, the API
may fail or fall back to freeform.

**Mitigation:** The Layer 3 skill (`.agents/skills/gemini-video-analysis/SKILL.md`)
must document: (a) which schema fields are safe to enforce at the API level vs.
must be validated post-hoc, (b) prompt structure that guides structured output even
when not enforced by the API, (c) fallback strategy if structured output fails
(attempt freeform JSON parse, log warning, validate manually).

**This is flagged as requiring deeper research during implementation.**

### Risk 4: `lib/checkpoint.py` CANONICAL_STAGE_ARTIFACTS — verify field exists

Reading `lib/checkpoint.py` was not performed in this session (not in `files_to_read`).
The `CONTEXT.md` and `STRUCTURE.md` both state checkpoint validation uses a mapping
from artifact name to schema path. If this mapping is a dict constant (high
probability based on pattern), the modification in Group 1c is a 2-line dict
addition. If it is logic-based, the change is more involved.

**Action:** Phase 1 task must include reading `lib/checkpoint.py` to confirm the
modification scope before writing schema files.

### Risk 5: `video-reference-analyst.md` refactor scope creep

The existing skill is 387 lines with deeply integrated freeform analysis references.
Refactoring to consume structured fields risks breaking the existing reference
production workflow if the skill is also used for production (not just synthesis
reference). The refactor must preserve all Step 2–6 behavior and only change Step 1
field references.

**Mitigation:** Treat this as an additive change: add structured-field consumption
as the primary path with graceful fallback to freeform if the structured fields are
missing (for backward compat with `VideoAnalyzer` outputs that lack the Gemini
fields). Document which fields come from which tool.

---

## Non-Issues (Explicitly Confirmed)

- **Registry hot-reload:** Not needed. `registry.discover()` and
  `pipeline_loader.list_pipelines()` both operate on current disk state at call
  time. A synthesized pipeline file is immediately available.
- **New pipeline category:** The `pipeline_manifest.schema.json` `category` enum
  already includes `"custom"` — synthesized pipelines should use `category: custom`
  and `stability: beta`. No schema change needed.
- **Selector breaking changes:** Adding `video_analyzer_selector.py` does not affect
  `video_selector`, `tts_selector`, or `image_selector`. They filter by
  `capability="video_generation"`, `capability="tts"`, and `capability="image_generation"`
  respectively. A new `capability="video_analysis"` namespace is fully isolated.
- **`pipeline_defs/` backward compat:** `list_pipelines()` globs all `.yaml` files.
  No existing manifest is touched. Existing pipelines continue working.
