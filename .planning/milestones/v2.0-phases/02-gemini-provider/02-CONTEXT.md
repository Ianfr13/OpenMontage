# Phase 2: Gemini Provider - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous) — 2 grey areas resolved, rest inherited from REQUIREMENTS.md

<domain>
## Phase Boundary

Deliver the first end-to-end `video_analysis` path: a capability-level selector (`video_analyzer_selector`) that routes to a Gemini-direct provider tool (`gemini_video_analyzer`), which uploads via the Files API, waits for `ACTIVE`, runs structured-output analysis against the flattened canonical schema, retries once on null/truncation, deletes the uploaded file, and returns a validated `video_analysis` artifact. Layer 3 skill (`gemini-video-analysis/SKILL.md`) documents Gemini-specific prompting per dimension. SKILL-03 real-video quality review runs as a human-needed checkpoint *after* execute — not inline.

Out of scope: OpenRouter provider (Phase 3), chunking for >5min videos (Phase 4), synthesis (Phase 5), CONTEXT.md/requirements.txt integration (Phase 6 — INT-02 will canonicalize deps; Phase 2 adds `google-genai>=1.73` to requirements.txt immediately but the final doc pass lives in Phase 6).

</domain>

<decisions>
## Implementation Decisions

### Plan Decomposition
- 4 parallel plans mirroring Phase 1 shape:
  - `02-01-PLAN.md` — selector + error classes (`lib/analysis_errors.py`: `VideoUploadError`, `VideoAnalysisError`; `tools/analysis/video_analyzer_selector.py` auto-discovers via `registry.get_by_capability("video_analysis")`; preference order: explicit → `GEMINI_API_KEY` → `OPENROUTER_API_KEY` → first available)
  - `02-02-PLAN.md` — `tools/analysis/gemini_video_analyzer.py` (Files API upload + ACTIVE polling + generate_content + structured output + retry + delete)
  - `02-03-PLAN.md` — `.agents/skills/gemini-video-analysis/SKILL.md` + `agent_skills` field wiring on the provider tool
  - `02-04-PLAN.md` — Contract tests (selector preference logic, artifact schema validation) + unit tests (mocked Files API, retry paths, error taxonomy) — all API-key-free

### Provider Tool Shape (from GEM-01..05, ANLZ-04, ANLZ-05)
- `BaseTool` subclass, `capability="video_analysis"`, `provider="gemini"`, `runtime=ToolRuntime.API`
- Auth: `GEMINI_API_KEY` primary, `GOOGLE_API_KEY` fallback (both via `os.getenv`)
- Model: `GEMINI_VIDEO_MODEL` env (default `gemini-3.1-pro-preview`, fallback `gemini-2.5-pro` if preview raises model-not-available)
- Files API: `client.files.upload(path)` → poll `get(file.name).state == "ACTIVE"` with exponential backoff (1s → 2s → 5s → 5s cap, 300s max wall; configurable via `max_poll_seconds` param)
- Structured output: `response_mime_type="application/json"` + `response_json_schema=to_api_schema(load_schema("video_analysis"))` (uses Phase 1 adapter)
- On null/truncated (empty string, `MAX_TOKENS` finish reason, or parse failure): one retry with `analysis_depth="compact"` appended to prompt → if still broken, raise `VideoAnalysisError`
- On `FAILED` upload state or 300s timeout: raise `VideoUploadError`
- `finally:` block ensures `client.files.delete(file.name)` runs after analysis (success OR failure) — upload-side isolation per GEM-03
- Optional `shot_boundaries` input (list of `[start, end]` tuples from `scene_detect`); when absent, artifact sets `shot_boundary_source: "model"` (ANLZ-05)
- Missing/uncertain fields: provider writes explicit `{value: ..., confidence: "low"}` on the dimension confidence-map rather than null/absent (ANLZ-04)
- `agent_skills=[".agents/skills/gemini-video-analysis"]` or `["gemini-video-analysis"]` — match existing registry convention (TBD: inspect base_tool.py)

### Selector Shape (from ANLZ-01)
- Mirror `tools/video/video_selector.py` and `tools/audio/tts_selector.py`
- `capability="video_analysis"`, `provider="selector"`, auto-discover via `registry.get_by_capability("video_analysis")` excluding self
- Preference order: `input.preferred_provider` (explicit) > env `VIDEO_ANALYZER_PROVIDER` > first tool with required env var set (Gemini first if both keys present — matches default `auto` semantics) > first available
- Pass-through inputs: `video_path`, `shot_boundaries?`, `analysis_depth?` (enum `full` | `compact`, default `full`)
- Return shape: identical to underlying provider — caller cannot tell which backend was used (ANLZ-06 preview; final test lands in Phase 3)

### SKILL-03 Quality Gate Strategy
- Phase 2 execute completes with code + unit tests + SKILL.md landed; `phase_close_requires_human_verification: true` for SKILL-03
- VERIFICATION.md flags SKILL-03 as `human_needed` with a specific instruction: "Run one real <2min video through the selector; confirm ≥12 of 16 canonical fields are populated with appropriate confidence; confirm pacing_style and dominant_visual_style enums are correct"
- User runs this manually post-execute; gsd-autonomous routes `human_needed` to user decision (validate now / defer)

### Error Taxonomy
- New module `lib/analysis_errors.py` with:
  - `class VideoAnalysisError(Exception)` — base
  - `class VideoUploadError(VideoAnalysisError)` — upload failures (FAILED state, timeout, unsupported format)
  - `class VideoAnalysisRetryExhausted(VideoAnalysisError)` — null/truncated response after retry
- Matches existing `lib/checkpoint.py::CheckpointValidationError` convention (domain-specific exception hierarchy per lib module)

### Dependencies
- Add `google-genai>=1.73` to `requirements.txt` in 02-02 (Phase 6 INT-02 finalizes full dep set including `openai` and `ruamel.yaml`)
- No conflicting deps expected (stdlib + jsonschema 4.26 + pytest 7.x + google-genai is clean per research)

### Claude's Discretion
- Exact polling backoff curve (1s→2s→5s→5s is a suggestion; planner may tune)
- Whether to emit structured logging (stdlib `logging` module) during polling — planner's call based on existing tool conventions
- Whether to support `analysis_depth="compact"` as a user-facing input from the selector OR only as an internal retry mode — planner decides; default recommendation: internal-only for v2.0
- Whether to inline the flattened schema at tool init time (cached) or re-flatten each call — recommend cached at class load; planner confirms

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Phase 1 schema adapter**: `lib/schema_adapter.py::to_api_schema(canonical: dict) -> dict` — stdlib-only, idempotent, deepcopies input. Tool will call `to_api_schema(load_schema("video_analysis"))` at init.
- **Phase 1 checkpoint**: `lib/checkpoint.py::validate_artifact("video_analysis", artifact)` — allowlist-gated; tool output must pass this before returning.
- **Phase 1 schemas**: `schemas/artifacts/video_analysis.schema.json` (11 KB, 4 dims, confidence maps) and `schemas/artifacts/__init__.py::load_schema`.
- **Selector template**: `tools/video/video_selector.py` (auto-discovery pattern, preference routing, 0.3.0) — closest in shape to what `video_analyzer_selector` needs. Also `tools/audio/tts_selector.py` for variant patterns.
- **BaseTool contract**: `tools/base_tool.py` (`ToolRuntime`, `ToolTier`, `ToolStability`, `agent_skills`, `input_schema`, `execute()` returns `ToolResult`).
- **Registry**: `tools/tool_registry.py::registry.get_by_capability("video_analysis")` — auto-discovery at import time.

### Established Patterns
- Error classes per lib module with domain hierarchy (`lib/checkpoint.py::CheckpointValidationError` subclass of `ValueError`)
- Structured output tools pass flattened schema (Phase 1 introduced this pattern; Phase 2 is first consumer)
- `tools/analysis/` is a sibling of `tools/video/`, `tools/audio/`, etc. — `gemini_video_analyzer` and `video_analyzer_selector` land here
- Tools cache expensive init (schema flattening, client construction) at class load where safe
- `agent_skills` field format: list of skill names (e.g., `["ai-video-gen", "create-video"]`); skill files live under `.agents/skills/<name>/SKILL.md`

### Integration Points
- `tools/analysis/video_analyzer.py` exists but is different — it's the legacy brief-only analyzer. New tools live alongside; no overlap beyond the directory.
- `tools/tool_registry.py` auto-discovers via `discover()` walking `tools/` — new files in `tools/analysis/` pick up automatically.
- `lib/checkpoint.py::write_checkpoint(stage="video_analysis", artifact=...)` — Phase 2 tool's return path feeds the next stage's checkpoint.
- `tools/cost_tracker.py` — planner decides whether Phase 2 records cost per call (recommended yes, matches Phase 4's CHUNK-06 expectation).

</code_context>

<specifics>
## Specific Ideas

- `client.files.delete` MUST run in `finally:` — Files API auto-delete is 48h which leaks cost/isolation across runs
- `response_json_schema` uses the *flattened* form (no `$ref`, no `additionalProperties: false`, no `uniqueItems`) — Phase 1's `to_api_schema` is the exact converter
- SKILL.md content scope: Gemini-specific prompting per dimension (editing_pacing / audio / visual_style / narrative) with ≥2 good-vs-bad extraction examples per dimension; 5-min timecode hallucination warning; structured-output pattern block; Files API quirks sidebar
- Tests must be green with NO API keys set (monkeypatch env, mock `client.files.upload`, `get`, `generate_content`, `delete` — verify call sequence + error paths + retry logic)

</specifics>

<deferred>
## Deferred Ideas

- Cost estimation surface from inside the tool (CHUNK-06 surfaces cost before chunked analysis — Phase 4)
- Streaming response parsing (out of v2.0 scope per REQUIREMENTS.md "Out of Scope")
- Automatic fallback from `gemini-3.1-pro-preview` → `gemini-2.5-pro` on model-not-available errors — implement in Phase 2 (mentioned in decisions)
- OpenRouter-specific grey areas — Phase 3

</deferred>
