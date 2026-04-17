# Architecture

**Analysis Date:** 2026-04-17

## Pattern Overview

**Overall:** Agent-orchestrated instruction-driven system

OpenMontage is an AI-orchestrated video production platform where the agent (Claude, Cursor, Copilot) is the primary control plane. The agent reads instructions (pipeline manifests in YAML + skill guides in Markdown), calls Python tools via a registry, writes checkpoints to persist state, and presents creative decisions to humans. There is no runtime Python orchestrator—the agent orchestrates the entire production pipeline.

**Key Characteristics:**
- No server runtime or Python orchestrator—agent drives the pipeline
- All intelligence lives in instructions (YAML + Markdown), not Python code
- Tool registry enables auto-discovery of 70+ tools across 9 capability families
- Checkpoint-based state persistence between pipeline stages
- Three-layer knowledge architecture: tools (Layer 1) → project conventions (Layer 2) → technology skills (Layer 3)

---

## Layers

**Layer 1: Tools (Python)**
- Purpose: Concrete capabilities—video generation, TTS, image generation, composition, analysis, enhancement, publishing
- Location: `tools/` with 9 subdirectories by capability family
- Contains: 78 tool classes inheriting from `BaseTool`
- Depends on: External APIs (fal.ai, ElevenLabs, HeyGen), local binaries (FFmpeg), Python packages (torch, librosa)
- Used by: Agent (via tool registry) and Layer 2/3 skills for prompting guidance

**Layer 2: Skills (Markdown)**
- Purpose: OpenMontage-specific instructions—how to use tools in pipelines, quality standards, stage workflows
- Location: `skills/` with 4 subdirectories: `core/` (FFmpeg, Remotion, WhisperX), `creative/` (editing, enhancement, prompting), `meta/` (reviewer, checkpoint-protocol, onboarding), `pipelines/` (per-pipeline stage directors)
- Contains: 100+ markdown skill files teaching the agent how to produce artifacts at each stage
- Depends on: Layer 1 (tool discovery) and Layer 3 (technology knowledge)
- Used by: Agent when executing pipeline stages and reviewing output

**Layer 3: Agent Skills (Markdown)**
- Purpose: Generic technology knowledge—API patterns, parameter optimization, prompting techniques, constraints
- Location: `.agents/skills/` with 47 technology directories (ffmpeg, elevenlabs, remotion, gsap, etc.)
- Contains: Vendor-specific prompting guides, parameter reference, code examples, integration patterns
- Depends on: External vendor documentation
- Used by: Layer 2 skills to know HOW to configure tools before calling them

---

## Data Flow

**Core Pipeline Execution:**

1. **Agent reads pipeline manifest** (`pipeline_defs/<pipeline>.yaml`)
   - Declares stages in order, required tools, artifact schemas, approval gates, cost budgets
   - Example: `animated-explainer.yaml` has 7 stages: research → proposal → script → scene_plan → assets → edit → compose → publish

2. **For each stage:**
   - Agent reads stage director skill (`skills/pipelines/<pipeline>/<stage>-director.md`)
   - Skill teaches the agent the quality bar, workflow, and how to call tools
   - Agent discovers available tools via `registry.discover()` and `registry.get_by_capability()`

3. **Agent calls tools:**
   - All tools are instances of `BaseTool` subclass
   - Agent calls `.execute(params_dict)` → returns `ToolResult` with `.success`, `.data`, `.artifacts`, `.error`, `.cost_usd`
   - Tool registry auto-discovers all `BaseTool` subclasses via `pkgutil.walk_packages()`
   - No manual tool registration needed

4. **Tool execution flow:**
   - Tool checks dependencies (env vars, binaries, Python packages) → returns `UNAVAILABLE` status if missing
   - If available, tool calls provider API or runs local process
   - Writes artifacts (images, videos, audio) to disk
   - Returns `ToolResult` with file paths, metadata, cost, seed for reproducibility

5. **Agent writes checkpoint:**
   - Canonical artifact for the stage goes in `pipeline/<project_id>/checkpoint_<stage>.json`
   - Includes artifact payload, tool metadata, cost summary, timestamp
   - Validated against `schemas/artifacts/<artifact_name>.schema.json`

6. **Agent self-reviews:**
   - Uses `skills/meta/reviewer.md` to evaluate output against pipeline `review_focus` items
   - Applies `quality_rules` from the style playbook
   - Can iterate up to 2 rounds before passing with warnings

7. **Human approval checkpoint:**
   - If `human_approval_default: true` for the stage, agent presents artifact summary
   - User approves, requests revision, or aborts
   - Checkpoint written with status `awaiting_human` or `completed`

8. **Resume on restart:**
   - Agent calls `checkpoint.get_next_stage()` to find where to resume
   - Loads prior stage artifacts and continues from next incomplete stage

---

## Key Abstractions

**BaseTool (Abstract Base Class):**
- Purpose: Contracts tool behavior for registry discovery and execution
- Location: `tools/base_tool.py`
- Pattern: Every tool inherits from `BaseTool` and declares metadata (name, version, tier, capability, provider, status, dependencies, cost, schema, fallback, agent_skills, retry policy)
- Examples: `tools/audio/elevenlabs_tts.py` (ElevenLabsTTS), `tools/video/kling_video.py` (KlingVideo), `tools/graphics/flux_image.py` (FluxImage)

**Tool Registry:**
- Purpose: Central discovery of available tools by capability, provider, status, tier
- Location: `tools/tool_registry.py`
- Pattern: Singleton auto-discovers all `BaseTool` subclasses at import time
- Key queries: `get_by_capability("tts")` → all TTS tools; `get_available()` → tools with satisfied dependencies; `support_envelope()` → full capability report
- Used by: Agent preflight, selectors, pipeline validation

**Selector Tools:**
- Purpose: Multi-provider capability routing (TTS, image generation, video generation)
- Location: `tools/audio/tts_selector.py`, `tools/graphics/image_selector.py`, `tools/video/video_selector.py`
- Pattern: Auto-discovers provider tools from registry, ranks by cost/quality/availability, routes to best match
- Example flow: Agent calls `tts_selector` with text + optional provider preference → selector queries registry for all `capability="tts"` tools → ranks by quality score → returns best available provider

**Pipeline Loader:**
- Purpose: YAML manifest loading and stage order validation
- Location: `lib/pipeline_loader.py`
- Pattern: Loads `pipeline_defs/<name>.yaml`, validates against `schemas/pipelines/pipeline_manifest.schema.json`, provides `load_pipeline()` and `get_stage_order()` helpers
- Used by: Agent to read the pipeline contract at session start

**Checkpoint Utility:**
- Purpose: Checkpoint persistence and stage-transition logic
- Location: `lib/checkpoint.py`
- Pattern: Read/write `pipeline/<project_id>/checkpoint_<stage>.json`; validate canonical artifacts; compute next stage
- Methods: `write_checkpoint(stage, status, artifacts)`, `load_checkpoint(stage)`, `get_next_stage(pipeline_type, project_id)`
- Used by: Agent after each stage completes and at session restart

**Cost Tracker:**
- Purpose: Budget governance (estimate → reserve → reconcile)
- Location: `tools/cost_tracker.py`
- Pattern: Every paid tool call is estimated, reserved (with contingency %), then reconciled against actual cost
- States: `estimated` → `reserved` → `completed`/`failed` with optional refund
- Used by: Agent before executing paid tools; budget alerts in `warn`/`cap` mode

**Artifact Schemas:**
- Purpose: Contract validation for canonical outputs of each stage
- Location: `schemas/artifacts/` with 11 JSON schemas
- Mapping: research_brief, proposal_packet, brief, script, scene_plan, asset_manifest, edit_decisions, render_report, publish_log, source_media_review, video_analysis_brief
- Used by: Checkpoint validator at write time; agent to know what fields to include in artifact

**Style Playbook Loader:**
- Purpose: Load and validate visual style templates (color, typography, motion, asset generation constraints)
- Location: `lib/playbook_loader.py` (reads YAML from `styles/`)
- Pattern: Playbook declares design tokens (color palette, type scale, motion rules), asset generation constraints, accessibility rules
- Used by: Assets stage to know composition rules; edit stage to know color grading rules

---

## Entry Points

**Agent Session Start:**
- Location: User invokes agent with video production request
- Triggers: Agent reads `AGENT_GUIDE.md` → determines pipeline → reads `PROJECT_CONTEXT.md`
- Responsibilities: 
  1. Run preflight (`registry.discover()` + `support_envelope()`)
  2. Present capability menu and offer setup for unavailable tools
  3. Load pipeline manifest and begin orchestration

**Pipeline Initialization:**
- Entry: Agent selects pipeline, user approves production plan
- Location: No code entry point; agent creates project directory and writes first checkpoint
- Responsibilities: Create `projects/<project-name>/` with `artifacts/`, `assets/`, `renders/` subdirs

**Stage Director Skill Execution:**
- Entry: Agent reads `skills/pipelines/<pipeline>/<stage>-director.md`
- Trigger: After reading stage config from manifest
- Responsibilities: Teach agent the quality bar, artifact structure, tool usage pattern for this stage
- Example: `skills/pipelines/animated-explainer/asset-director.md` teaches how to call image_selector, music_generation, and video_selector for assets

**Tool Execution:**
- Entry: `tool.execute(params_dict)` called by agent
- Location: Specific tool class (e.g., `tools/audio/elevenlabs_tts.py`)
- Responsibilities: Validate inputs against `input_schema`, call provider API, write artifacts, return `ToolResult`

**Checkpoint Write:**
- Entry: Agent completes a stage and calls `checkpoint.write_checkpoint(stage, status, artifacts)`
- Location: `lib/checkpoint.py`
- Responsibilities: Validate canonical artifact against schema, write JSON, compute next stage

---

## Cross-Cutting Concerns

**Logging:** 
- Framework: Python `logging` module (no central sink defined in Layer 1/2; agent logs to console)
- Pattern: Tools emit structured logs with tool name, stage, action, result; agent relays to user

**Validation:** 
- Pattern: `jsonschema` used at runtime for artifact validation and manifest validation
- Schemas: JSON Schema v7 in `schemas/artifacts/`, `schemas/pipelines/`, `schemas/checkpoints/`, `schemas/styles/`
- Enforcement: Checkpoint write fails if canonical artifact invalid; pipeline load fails if manifest invalid

**Authentication & Secrets:** 
- Pattern: `.env` file loaded at module import (in `tools/base_tool.py` and `tools/tool_registry.py`)
- Env vars: Tool-specific API keys (ELEVENLABS_API_KEY, FAL_KEY, etc.) read from environment at tool instantiation
- Tools report `UNAVAILABLE` status if required env var missing

**Cost Governance:** 
- Pattern: `cost_tracker.CostTracker` instance per project; estimate before execution, reserve with 10% contingency, reconcile on completion
- Modes: `observe` (no limits), `warn` (alerts over threshold), `cap` (blocks execution over budget)
- Used by: Agent to communicate costs and pauses before expensive tool calls

**Error Handling:** 
- Pattern: `BaseTool.execute()` returns `ToolResult` with `.success=False` and `.error` message on failure
- No exceptions thrown to agent; all errors wrapped in `ToolResult`
- Retry logic: Defined per-tool in `retry_policy` field (max retries, backoff strategy)

**State Persistence:** 
- Pattern: Checkpoints carry all canonical artifacts and metadata; on restart, agent resumes from next incomplete stage
- Directory: `pipeline/<project_id>/checkpoint_<stage>.json` (JSON, not binary)
- Validation: Artifact schemas validated at write time; checkpoint schema validated at load time

---

## Tool Families & Capability Discovery

| Capability | Selector | Tools | Location |
|---|---|---|---|
| tts | tts_selector | ElevenLabs, OpenAI, Google, Piper | `tools/audio/` |
| music_generation | — | Music (singular provider) | `tools/audio/music_gen.py` |
| image_generation | image_selector | FLUX, DALL-E, Recraft, Google Imagen, local diffusion | `tools/graphics/` |
| video_generation | video_selector | 13 providers (Kling, VEO, HunyuanVideo, LTX, etc.) | `tools/video/` |
| audio_processing | — | FFmpeg-based mixing, normalization, enhancement | `tools/audio/` |
| video_post | — | FFmpeg-based composition, stitching, trimming | `tools/video/` |
| analysis | — | Transcription, scene detection, frame sampling, understanding | `tools/analysis/` |
| enhancement | — | Upscale, bg removal, face enhance, color grading | `tools/enhancement/` |
| avatar | — | HeyGen lip-sync, talking head animation | `tools/avatar/` |
| subtitle | — | SRT generation from timestamps | `tools/subtitle/` |

---

## Composition Runtime

**FFmpeg (Local, Free):**
- Purpose: Video encoding, filtering, concat, trim, subtitle burn
- Pattern: Used by `video_compose` when no motion-graphics needed; Ken Burns on stills as fallback
- Fallback: Always available; no setup needed

**Remotion (Node.js/React, Free):**
- Purpose: Still images → animated video; text cards, stat cards, charts, comparisons with spring physics
- Location: `remotion-composer/` (separate Node.js project)
- Pattern: Video composition layer calls `remotion_caption_burn` or `video_compose` with Remotion engine
- Availibility: Requires `node` binary + `npx`; check via `registry._tools['video_compose'].get_info()`
- Scene types: text_card, stat_card, callout, comparison, hero_title, terminal_scene, anime_scene, bar_chart, line_chart, pie_chart, kpi_grid, progress_bar

---

*Architecture analysis: 2026-04-17*
