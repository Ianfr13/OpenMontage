# Phase 3: OpenRouter Provider - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, tight cadence — inherits Phase 2 plan decomposition + SKILL-03 deferral)

<domain>
## Phase Boundary

Deliver a second interchangeable video_analysis provider that slots into the existing `video_analyzer_selector` (Phase 2) with zero selector-code changes. Uses the `openai>=1.0` SDK with `base_url="https://openrouter.ai/api/v1"` and inline base64 encoding (no Files API equivalent — OpenRouter's Gemini route does NOT accept URL input). Rejects videos above `max_upload_bytes` before encoding. Handles `finish_reason == "length"` silent truncation with one compact-depth retry. Artifacts from both providers pass the same canonical schema — selector callers cannot tell which backend served the response (ANLZ-06 gate lands here). Layer 3 skill `.agents/skills/openrouter-video-analysis/SKILL.md` mirrors the Phase 2 Gemini skill shape with OpenRouter-specific quirks.

Out of scope: chunking (Phase 4), synthesizer (Phase 5), requirements.txt canonicalization (Phase 6 INT-02 — Phase 3 adds `openai>=1.0` immediately).

</domain>

<decisions>
## Implementation Decisions

### Plan Decomposition (mirrors Phase 2 shape)
- `03-01-PLAN.md` — `tools/analysis/openrouter_video_analyzer.py` (BaseTool with `provider="openrouter"`, inline base64 encoding, `/chat/completions` with `video_url` content type, `response_format={"type": "json_schema", "json_schema": {...}}` when model supports, fallback to prompt-embedded schema + post-validation retry, `finish_reason=="length"` detection, compact retry, `max_upload_bytes` gate). Add `openai>=1.0` to requirements.txt.
- `03-02-PLAN.md` — `.agents/skills/openrouter-video-analysis/SKILL.md` (Layer 3 knowledge — base64-only inline, model swapping via `OPENROUTER_MODEL` env, `response_format` compatibility per model, cost surfacing via OpenRouter credits header).
- `03-03-PLAN.md` — Contract + unit tests (API-key-free, mocked openai SDK, cross-provider consistency test using both providers with mocked responses — ANLZ-06 gate).

### Tool Shape (from OR-01..06, ANLZ-06)
- `BaseTool` subclass, `capability="video_analysis"`, `provider="openrouter"`, `runtime=ToolRuntime.API`
- Auth: `OPENROUTER_API_KEY` primary (no fallback — unlike Gemini's GEMINI_API_KEY/GOOGLE_API_KEY pair). Pass explicitly to `openai.OpenAI(api_key=..., base_url="https://openrouter.ai/api/v1")` — OpenAI SDK reads OPENAI_API_KEY by default, which is wrong for us.
- Model: `OPENROUTER_MODEL` env (default `google/gemini-3.1-pro-preview`). Model alias format is `vendor/model-name` per OpenRouter convention.
- Encoding: read file bytes, `base64.b64encode(...).decode()`, prefix `data:video/mp4;base64,...`. Reject with `VideoUploadError("video exceeds max_upload_bytes")` BEFORE encoding if `os.path.getsize(path) > max_upload_bytes` (default 20MB per OpenRouter inline cap).
- Message shape: `[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "video_url", "video_url": {"url": data_url}}]}]`
- Structured output: attempt `response_format={"type": "json_schema", "json_schema": {"name": "video_analysis", "schema": <flattened>, "strict": true}}`. On 4xx "unsupported response_format" from the underlying model (some OpenRouter routes don't support it), fall back to prompt-embedded schema + post-hoc `jsonschema.validate` with one retry on parse failure.
- Truncation detection: `response.choices[0].finish_reason == "length"` (string, not enum — differs from Gemini). Also treat empty `response.choices[0].message.content` as truncated.
- Retry: ONE retry with `analysis_depth="compact"` prompt directive appended. Second failure → `VideoAnalysisRetryExhausted`.
- `client.close()` is NOT needed (openai SDK uses context manager internally); no Files API cleanup required (inline encoding has no server-side state).
- `agent_skills = ["openrouter-video-analysis"]`

### Selector Integration (ANLZ-06)
- Zero selector code changes — Phase 2 `VideoAnalyzerSelector._providers()` already auto-discovers via `registry.get_by_capability("video_analysis")`.
- ANLZ-01 preference order already supports `VIDEO_ANALYZER_PROVIDER=openrouter` env override and `preferred_provider="openrouter"` explicit input.
- Cross-provider consistency test (Phase 3 contract): same canonical fixture through both mocked providers → both artifacts pass the same schema validation → selector caller cannot distinguish.

### SKILL-03 Gate (same deferral as Phase 2)
- Real-video quality review deferred to post-execute human-needed gate (HUMAN-UAT).
- Instruction: run one real <2min video through `video_analyzer_selector` with `OPENROUTER_API_KEY` set and `VIDEO_ANALYZER_PROVIDER=openrouter`; confirm ≥12 of 16 canonical fields populated appropriately.

### Dependencies
- Add `openai>=1.0` to `requirements.txt` (Phase 6 INT-02 finalizes with `ruamel.yaml>=0.18`).
- No conflicting deps — openai SDK is already a common transitive of other tools in this repo.

### Claude's Discretion
- Exact base64 streaming strategy (buffered vs full-read) — planner's call; recommend `Path(...).read_bytes()` + single `b64encode` for <20MB files (simpler)
- Whether to record `x-openrouter-credit-remaining` response header in ToolResult.data for cost observability — recommend yes (cheap win)
- Whether to support `response_format` auto-detection by probing the model before main call — recommend NO (extra call cost); instead try json_schema first and fall back on error

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 2)
- `tools/analysis/video_analyzer_selector.py` — auto-discovers providers; needs zero changes
- `tools/analysis/gemini_video_analyzer.py` — template for BaseTool shape, error handling, prompt building, shot_boundary normalization, artifact validation gate
- `lib/analysis_errors.py` — VideoUploadError, VideoAnalysisError, VideoAnalysisRetryExhausted — ALL reusable
- `lib/schema_adapter.py::to_api_schema` — same flattening applies to OpenRouter's json_schema mode
- `schemas/artifacts/__init__.py::load_schema, validate_artifact` — artifact validation gate
- `tests/unit/conftest.py` — autouse env-scrubbing fixture (include OPENROUTER_API_KEY in scrub list — already there)
- Phase 2's `_normalize_shot_boundaries` helper can be DRY'd into lib/analysis_errors.py OR duplicated (decide during planning — recommend DUPLICATION for now; extract in Phase 6 if a third provider materializes)

### Established Patterns (from Phase 2)
- Lazy `_flat_schema()` classmethod for cached flattened schema (MD-01 fix)
- Clamped `max_upload_bytes` / `max_poll_seconds` inputs (MD-04 fix) — apply same pattern: `max_upload_bytes` clamped to [1, 2*1024*1024*1024] (2GB OpenRouter hard cap)
- Narrow `except errors.APIError` at client init (MD-03 fix) — for openai SDK, that's `openai.APIError`
- Tool does NOT write checkpoints (Phase 1 WR-05)
- Tool does NOT stamp selector metadata on `result.data` (ANLZ-06)
- Tests mock SDK module at import scope; autouse env-scrub fixture blocks accidental real-API calls
- SKILL.md mirrors `.agents/skills/gemini-video-analysis/SKILL.md` shape (8 sections, 280-450 lines)

### Integration Points
- Phase 2's `video_analyzer_selector._pick()` now returns `None` on unknown `preferred_provider` (Phase 2 MD-05 fix) — Phase 3's tests can assert `preferred_provider="openrouter"` returns the OpenRouter tool once shipped
- `VIDEO_ANALYZER_PROVIDER` env is already read in selector — just needs the OpenRouter tool present

</code_context>

<specifics>
## Specific Ideas

- `response_format={"type": "json_schema", "json_schema": {"name": "video_analysis", "schema": <flattened>, "strict": true}}` is the preferred path. When strict mode rejects, fall back to prompt-embedded schema (append a schema string to the prompt) + post-hoc `jsonschema.validate` with one retry. Document in SKILL.md which OpenRouter model routes support strict json_schema.
- `data:video/mp4;base64,...` MIME must match the actual file type — probe via `mimetypes.guess_type(path)` and raise `VideoUploadError` for unsupported types (non-mp4/webm/mov).
- ANLZ-06 cross-provider test: use a canonical fixture artifact (mock both providers to return the same structured payload); assert both pass `validate_artifact("video_analysis", ...)` and both have identical top-level keys.
- Tests MUST be API-key-free: mock `openai.OpenAI` constructor with `unittest.mock.MagicMock()`, mock `client.chat.completions.create(...)` to return a response object with `.choices[0].finish_reason`, `.choices[0].message.content` (JSON string), and `.usage.total_tokens`.

</specifics>

<deferred>
## Deferred Ideas

- PROV-01..03 (other providers) — v2.1+
- OpenRouter credits API for pre-flight cost check — recommend simple header-based observability in v2.0; full cost integration in Phase 4 (CHUNK-06) or v2.1 OBS-01
- Streaming response parsing — out of v2.0 scope
- Model alias routing (automatic upgrade to latest gemini-pro variant via OpenRouter) — v2.1

</deferred>
