# Pitfalls Research

**Domain:** Multimodal LLM video analysis + pipeline synthesis added to instruction-driven video production system
**Researched:** 2026-04-17
**Confidence:** HIGH (Gemini API pitfalls verified via official forums and GitHub issues; integration pitfalls derived from existing OpenMontage architecture)

---

## Critical Pitfalls

### Pitfall 1: Timecode Hallucination in Gemini Video Analysis

**What goes wrong:**
Gemini 2.5 Pro returns shot lists and scene boundaries with timestamps that do not correspond to actual video content. Timecodes jump erratically, exceed actual video duration, or cluster within the first few minutes while fabricating the rest. The model returns data with high apparent confidence — no error signal, just wrong numbers.

**Why it happens:**
Gemini's temporal attention degrades on videos longer than 3-5 minutes. The model's training conflates content summarization with precise temporal localization. At 1 FPS default sampling on a 10-minute video = 600 frames in context — positional encoding accuracy drops across the context window. Forum threads confirm this is a known regression in 2.5 Pro stable vs. preview builds.

**How to avoid:**
- Hard-cap analysis segments at 5 minutes maximum; split longer videos at scene boundaries using FFmpeg scene detection (`SceneDetect` tool already exists in `tools/analysis/scene_detect.py`) before sending to Gemini
- Request timestamps in `MM:SS` format explicitly in the system prompt — millisecond precision invites hallucination
- Cross-validate returned timecodes against `video_analyzer` scene detection output: if Gemini's `start_time` / `end_time` fields diverge by more than 3 seconds from FFmpeg scene cuts, flag the analysis as `confidence: low` in the `video_analysis` artifact
- In the `gemini_video_analyzer` tool, implement a `timecode_sanity_check()` that rejects any timestamp > `source.duration_seconds` and surfaces a `validation_warnings[]` array in the output artifact

**Warning signs:**
- Returned timecodes that exceed video duration
- Multiple scenes sharing the same start/end time
- All timecodes clustered in the first 20% of video duration
- `avg_scene_duration_seconds` returning values inconsistent with `total_scenes` and `duration_seconds`

**Phase to address:** Phase 1 — `gemini_video_analyzer` tool implementation. The sanity check must be built into the tool, not left to the agent.

---

### Pitfall 2: Structured Output Returns None on Max Tokens

**What goes wrong:**
When `response_mime_type="application/json"` with `response_schema` set and the generated JSON exceeds `max_output_tokens`, the Gemini API returns `None` for both `response.text` and `response.parsed` — no partial output, no truncated JSON, no error message. The call appears to succeed (HTTP 200) but yields nothing.

**Why it happens:**
Confirmed GitHub issue in `googleapis/python-genai` (#1039). When `finish_reason=MAX_TOKENS`, structured output mode silently drops the response instead of returning the partial string. The `video_analysis.schema.json` v2.0 covers 4 dimensions with per-scene objects; a 30-scene video at full extraction depth will routinely exceed 8,192 output tokens.

**How to avoid:**
- Set `max_output_tokens=65536` explicitly (not default) on all `gemini_video_analyzer` calls
- Check `response.candidates[0].finish_reason` before consuming output — if `MAX_TOKENS`, retry with `analysis_depth="compact"` which reduces per-scene field count
- Design `video_analysis.schema.json` with a `compact` profile variant that omits `shot_language`, `dominant_colors`, and `on_screen_text` per scene — use compact for videos with >20 scenes
- Never assume `response.parsed` is populated without an explicit null check; raise `VideoAnalysisError("model returned empty structured output")` with `finish_reason` in the message

**Warning signs:**
- Tool returns success but `video_analysis` artifact is empty or missing required fields
- No exception raised but output dict is `None`
- Works on 60-second test video, fails on 5-minute reference video

**Phase to address:** Phase 1 — tool implementation. Must be in `gemini_video_analyzer.execute()`, not post-processing.

---

### Pitfall 3: Schema Complexity Triggers 400 InvalidArgument

**What goes wrong:**
Sending `video_analysis.schema.json` as `response_schema` to the Gemini API triggers a `400 InvalidArgument: Schema too complex` error. This happens silently during integration — the schema validates locally against JSON Schema Draft 2020-12 but is rejected by the Gemini SDK's stricter internal schema transformer.

**Why it happens:**
The Gemini Python SDK's `_transformers.py` validates and transforms schemas before sending them. Known incompatibilities as of 2025-2026: `additionalProperties: false` causes client-side rejection (GitHub issue #1815), schemas with deeply nested `$ref` chains fail, and `uniqueItems: true` on arrays is unsupported. The v2.0 `video_analysis` schema with 4 dimensions + per-scene arrays + narration segments is at high risk.

**How to avoid:**
- Maintain two schema representations: the canonical `schemas/artifacts/video_analysis.schema.json` (for artifact validation) and a Gemini-compatible inline schema dict in the tool (manually flattened, no `$ref`, no `additionalProperties`)
- Test Gemini schema compatibility as a contract test with no API key: instantiate the `genai` client, call `types.GenerateContentConfig(response_schema=SCHEMA)` with `genai.protos.Schema` and assert no exception is raised during schema serialization
- Strip `additionalProperties`, `$defs`, `$ref`, and `uniqueItems` from the Gemini-facing schema; these are unsupported
- Add a CI contract test: `test_gemini_schema_compatibility()` in `tests/contracts/` that validates schema serializes without error using the SDK

**Warning signs:**
- `400 InvalidArgument` on first real API call after local development
- Error message mentions "schema" or "response_mime_type"
- Works in AI Studio but fails via SDK

**Phase to address:** Phase 1 — tool implementation. Contract test in Phase 3 (test coverage phase).

---

### Pitfall 4: Files API Upload Stuck in PROCESSING State

**What goes wrong:**
`genai.upload_file()` returns a file object in `PROCESSING` state. The tool proceeds to send analysis requests, which fail with `FAILED_PRECONDITION: File is not in ACTIVE state`. Large videos (>100MB) or under API load can stay in `PROCESSING` for minutes; occasionally they never transition to `ACTIVE` without explanation.

**Why it happens:**
Google's Files API processes video server-side after upload. Processing time is variable (seconds to minutes) and is not surfaced in the upload response. The SDK does not block on `ACTIVE` state — it returns immediately after upload. Community reports confirm videos can stay in `PROCESSING` for 10+ minutes or silently enter `FAILED` state.

**How to avoid:**
- Implement polling in `gemini_video_analyzer` with exponential backoff: poll `genai.get_file(file_name)` every 5 seconds, max 30 retries (150 seconds total timeout)
- Pattern: `while file.state == "PROCESSING": sleep(5); file = client.files.get(file.name)`
- On `FAILED` state, raise `VideoUploadError` with the file name for debugging
- Enforce client-side upload size check: if local file > 500MB, reject with `VideoTooLargeError` before upload — the analysis token cost alone would be prohibitive
- Log file URI and state transitions to the project decision log for debugging

**Warning signs:**
- Tool hangs indefinitely after upload
- `FAILED_PRECONDITION` error on analysis call immediately after upload returns
- Works on short test videos, hangs on long reference videos

**Phase to address:** Phase 1 — tool implementation. No workaround is viable without proper polling.

---

### Pitfall 5: Synthesized Pipeline References Non-Existent Director Skills

**What goes wrong:**
`pipeline_synthesizer` generates a YAML that validates against `pipeline_manifest.schema.json` (which only checks `skill` is a string) but points to `skills/pipelines/reference-synthesis/idea-director.md` — a path that does not exist. The pipeline passes all schema checks, gets saved to `pipeline_defs/`, and fails only when the agent tries to execute it.

**Why it happens:**
The `pipeline_manifest.schema.json` uses `"type": "string"` for `skill` fields — it cannot validate path existence. The synthesizer LLM invents plausible-sounding paths by analogy with the reference video's detected format without cross-checking the actual `skills/pipelines/` directory contents.

**How to avoid:**
- In `pipeline_synthesizer`, enumerate actual available director skills via `glob("skills/pipelines/**/*-director.md")` before synthesis — pass the enumerated list as `available_director_skills[]` in the synthesis prompt, explicitly instructing the model to only reference paths from that list
- Add a `semantic_validator.py` post-synthesis step that checks every `skill:` value in the generated YAML against the filesystem before the approval checkpoint
- The semantic validator must also check `tools_available[]` entries against `registry.get_all_names()` — same problem exists for tool references
- Reject the synthesized pipeline with a structured error if any skill path or tool name fails validation; do not present invalid YAML to the human for approval

**Warning signs:**
- Synthesized pipeline YAML passes `jsonschema.validate()` but agent errors on first execution
- `skills/pipelines/<name>/` directory does not exist
- Pipeline references a pipeline type not in the existing 12

**Phase to address:** Phase 2 — pipeline synthesizer tool implementation.

---

### Pitfall 6: Cost Blowup on Long Reference Videos

**What goes wrong:**
A 60-minute reference video sent to Gemini Pro 3.1 via Files API consumes approximately 108,000 tokens for video frames alone (1 FPS × 3600 seconds × 30 tokens/frame) plus audio tokens, plus the schema-guided prompt. At Gemini Pro pricing ($2.00/million input tokens as of 2026), one analysis run on a 1-hour video costs $0.22+ in input tokens alone — but a 1-hour video also burns through a significant fraction of the 1M token context window, degrading output quality on the analysis dimensions that matter most.

**Why it happens:**
Users provide a full YouTube video URL ("make something like this 45-minute documentary") without understanding that Gemini tokenizes at ~300 tokens/second of video (258 for frames + 32 for audio). There is no guard in the current `video_analyzer` or `video_reference-analyst.md` skill that warns about this.

**How to avoid:**
- Implement a pre-flight token estimator in `gemini_video_analyzer`: `estimated_tokens = duration_seconds * 300`; if estimated > 500,000 tokens (at current pricing ~$0.50 input per run), surface a cost warning and offer to analyze only the first N minutes or a sampled subset
- Hard reject videos > 3600 seconds (1 hour) with a clear error message: "Video too long for direct analysis. Extract a representative 3-5 minute segment first."
- Add `max_duration_seconds` parameter (default: 300) to `gemini_video_analyzer` input schema
- Register the estimated cost in `cost_tracker` before making the API call, using the existing `estimate()` → `reserve()` → `reconcile()` pattern from `lib/cost_tracker.py`

**Warning signs:**
- Video URL is a full-length film, documentary, or live stream recording
- `source.duration_seconds > 600` in the analysis request
- User says "make something like this" and pastes a YouTube link to a 30+ minute video

**Phase to address:** Phase 1 — tool implementation. Cost estimation must be in the tool, not the skill.

---

## Integration Pitfalls

### Pitfall 7: Hardcoding Gemini Instead of Routing via video_analysis Selector

**What goes wrong:**
The `gemini_video_analyzer` tool is called directly from the `video-reference-analyst.md` skill and the synthesizer instead of routing through a `video_analysis_selector`. When a second provider (e.g., Claude 3.5 Sonnet vision, GPT-4o Video) becomes available, every skill and pipeline that hardcodes `gemini_video_analyzer` must be manually updated — exactly the coupling pattern the existing `tts_selector` / `image_selector` / `video_selector` architecture was designed to prevent.

**Why it happens:**
"We only have Gemini for now, so a selector seems like overkill" — a common rationalization during single-provider milestones. The PROJECT.md explicitly acknowledges "selector-ready but only Gemini implemented" but without a selector skeleton, future providers require refactoring.

**How to avoid:**
- Create `tools/analysis/video_analysis_selector.py` with `capability = "video_analysis"` in Phase 1, even if it routes to exactly one provider
- The selector pattern from `tts_selector` is the reference implementation: `registry.get_by_capability("video_analysis")`, filter by availability, apply user preference
- Update `AGENT_GUIDE.md` and `video-reference-analyst.md` to reference `video_analysis_selector`, never `gemini_video_analyzer` directly
- The `gemini_video_analyzer` tool declares `capability = "video_analysis"` so the selector discovers it automatically

**Warning signs:**
- Skill files contain the string `gemini_video_analyzer` as a literal tool call
- Pipeline YAML `tools_available` lists `gemini_video_analyzer` instead of `video_analysis_selector`
- Adding a second video analysis provider requires editing skills and pipelines

**Phase to address:** Phase 1 — must be established at the same time the tool is built, not retrofitted.

---

### Pitfall 8: Missing Layer 3 Skill for Gemini Video Analysis

**What goes wrong:**
The agent calls `video_analysis_selector` → routes to `gemini_video_analyzer` — but there is no Layer 3 skill documenting Gemini-specific prompting patterns for video analysis. The agent falls back to generic prompts: "analyze this video and return JSON." Generic prompts produce summary-style narrative output instead of structured extraction — the model describes what it sees rather than populating the schema fields with measurable facts (cuts-per-minute, narration WPM, exact color hex values, etc.).

**Why it happens:**
Phase 1 focuses on making the API call work. Layer 3 skills are treated as polish and deferred. But the quality gap between a generic prompt and a schema-informed, field-specific prompt for Gemini video analysis is enormous — this is not polish, it is the difference between a useful artifact and a free-text summary dressed up as JSON.

**How to avoid:**
- Create `.agents/skills/gemini-video-analysis/SKILL.md` in Phase 1 alongside the tool, not after
- Skill must include: field-by-field prompting strategy (e.g., "For `cuts_per_minute`: count visible hard cuts in the first 30 seconds and extrapolate, do not estimate"), Gemini-specific system prompt template for structured extraction, known failure modes and mitigation phrases, and example output per field
- The `gemini_video_analyzer` tool's `agent_skills` field must reference this skill path
- AGENT_GUIDE.md Layer 3 skill table must include `gemini-video-analysis` under the analysis category

**Warning signs:**
- `gemini_video_analyzer` tool has `agent_skills = []` or references only `video-understand`
- Returned `video_analysis` artifacts have null fields that should have values
- `narration_transcript.segments` is empty but the video clearly has narration
- `pacing_profile.cuts_per_minute` is always the same round number (hallucinated, not measured)

**Phase to address:** Phase 1 — Layer 3 skill is not optional. Block Phase 1 exit on its existence.

---

### Pitfall 9: New Workflow Not Registered in AGENT_GUIDE.md

**What goes wrong:**
The end-to-end workflow (URL/file → analysis → proposal → approval → `pipeline_defs/<name>.yaml` saved) is fully implemented but not documented in `AGENT_GUIDE.md`. The agent never learns the workflow exists. Users who say "make something like this YouTube video" continue to hit the old `video-reference-analyst.md` path that produces a free-text summary and routes to an existing pipeline — the new synthesis capability is invisible.

**Why it happens:**
`AGENT_GUIDE.md` is treated as documentation rather than as a routing contract. But per the existing architecture, AGENT_GUIDE.md IS the agent's routing table — "Reference Video Entry Point" is already defined there and the agent reads it at every invocation. Any new workflow that isn't added to AGENT_GUIDE.md simply does not exist from the agent's perspective.

**How to avoid:**
- AGENT_GUIDE.md update is a non-optional deliverable of the phase that implements the end-to-end workflow (Phase 2 or the integration phase)
- Add a "Reference Synthesis Entry Point" section that distinguishes: "make something like this" (existing, routes to `video-reference-analyst.md` for production) vs. "synthesize a pipeline from this reference" (new, routes to the synthesis workflow)
- Acceptance criterion for the integration phase: an agent fresh-reading only `AGENT_GUIDE.md` should be able to locate the synthesis workflow within 2 hops

**Warning signs:**
- Agent responds to "synthesize a pipeline from this video" by routing to the old analysis-only workflow
- No "Reference Synthesis" section in AGENT_GUIDE.md after the integration phase is marked complete
- The synthesis capability is only discoverable by knowing to ask for it specifically

**Phase to address:** Phase 2 or integration phase — AGENT_GUIDE.md update is a gate condition, not a follow-up task.

---

### Pitfall 10: Schema Drift — video_analysis.schema.json Not Registered in Artifact Registry

**What goes wrong:**
`schemas/artifacts/video_analysis.schema.json` is added (it already exists as `video_analysis_brief.schema.json` in v1.0 — the v2.0 version expands it significantly). The `schemas/artifacts/__init__.py` module's `list_schemas()` and `validate_artifact()` functions are not updated to include the new schema. Contract tests that check "all artifacts in schemas/ are loadable and valid JSON Schema" pass because the file exists, but `validate_artifact("video_analysis", artifact)` silently falls through to a no-op or raises `SchemaNotFoundError` at runtime.

**Why it happens:**
The v1.0 schema file is named `video_analysis_brief.schema.json`; the v2.0 canonical name may differ. If the Phase 1 implementer creates `video_analysis.schema.json` without updating `__init__.py`'s registry mapping, the artifact validation gap is invisible until a pipeline stage tries to checkpoint with a `video_analysis` artifact.

**How to avoid:**
- Audit `schemas/artifacts/__init__.py` before creating the new schema file — understand how `load_schema()` maps artifact names to file paths
- If the mapping is explicit, update it in the same commit as the schema file; if it's filesystem-glob-based, verify the naming convention matches
- Add a contract test: `test_video_analysis_schema_loadable()` that calls `load_schema("video_analysis")` and `validate_artifact("video_analysis", MINIMAL_VALID_FIXTURE)` and asserts no exception
- The v1.0 `video_analysis_brief` schema must remain loadable (backward compat); do not delete or rename it

**Warning signs:**
- `validate_artifact("video_analysis", ...)` raises `KeyError` or `SchemaNotFoundError`
- `list_schemas()` does not include `video_analysis` in its output
- Phase 0 contract tests pass but runtime artifact validation fails

**Phase to address:** Phase 1 alongside schema creation. The contract test belongs in Phase 3.

---

### Pitfall 11: Human Approval Bypass — Pipeline Saved Before Review

**What goes wrong:**
The synthesizer writes the new YAML to `pipeline_defs/<name>.yaml` immediately after generation, before human review. The `pipeline_loader.list_pipelines()` function auto-discovers all YAMLs in that directory. Any subsequent preflight or agent invocation can now select the unreviewed pipeline. If the pipeline is semantically broken (Pitfall 5), it gets used in production.

**Why it happens:**
The synthesizer tool is designed to "produce a file" (like all other production tools), so the natural instinct is to write the output. But this is a registry-affecting write — unlike generating an asset that goes to `projects/<name>/assets/`, writing to `pipeline_defs/` changes the system's capability envelope permanently.

**How to avoid:**
- The `pipeline_synthesizer` tool must write to a staging path: `pipeline_defs/_staging/<name>.yaml`, never directly to `pipeline_defs/`
- Human approval checkpoint reads from staging and, on approval, moves to `pipeline_defs/` — this move is the gate
- The `pipeline_loader` must not discover files from `pipeline_defs/_staging/`; add `_staging/` to its glob exclude list
- The `checkpoint-protocol.md` meta skill must explicitly flag `pipeline_synthesis` stage as `human_approval_default: true` with the note that approval triggers the file move, not just a status update

**Warning signs:**
- Synthesized pipeline appears in `registry.list_pipelines()` before the user has reviewed it
- The approval checkpoint is `awaiting_human` but the pipeline is already usable
- `pipeline_defs/` contains YAML files with `stability: beta` from synthesis with no changelog entry

**Phase to address:** Phase 2 — synthesizer tool implementation. The staging path is architectural, not configurable.

---

### Pitfall 12: Integration Tests Call Real Gemini API on Every CI Run

**What goes wrong:**
Tests in `tests/qa/` that validate end-to-end reference analysis make real Gemini API calls. Each run of the test suite costs $0.10-$0.50 in API tokens and adds 30-60 seconds of latency. On a busy repo with multiple PRs, this creates flaky tests (rate limits), developer friction (tests skipped to save money), and eventually a dead test suite that nobody runs.

**Why it happens:**
The integration test is written correctly for manual validation but not designed for CI. The existing `tests/contracts/` suite explicitly avoids API keys — the v2.0 test author forgets this constraint because the new capability is inherently API-dependent.

**How to avoid:**
- Separate `tests/` directories by API-cost tier: `tests/contracts/` (no key, always run in CI), `tests/integration/` (real API, gated by `RUN_INTEGRATION_TESTS=1` env var), `tests/eval/` (expensive benchmarks, manual only)
- Create `tests/integration/fixtures/video_analysis_response.json` — a recorded real Gemini response for a known test video — and use it via `unittest.mock.patch` in contract tests: test that the tool correctly processes the fixture, not that Gemini returns it
- For the synthesizer, create fixture `video_analysis_brief_sample.json` (hand-crafted valid artifact) and test synthesis logic independently of analysis
- Add `@pytest.mark.integration` marker and CI exclusion rule to all tests requiring `GEMINI_API_KEY`

**Warning signs:**
- `GEMINI_API_KEY` checked in `tests/contracts/` files
- `make test-contracts` fails with `AuthenticationError`
- Tests pass locally but fail in CI with `429 Resource Exhausted`
- `make test` takes >5 minutes

**Phase to address:** Phase 3 — test coverage phase. The fixture strategy must be designed before tests are written.

---

### Pitfall 13: Overfitting Pipeline to One Reference Video — Brittle Generalization

**What goes wrong:**
A synthesized pipeline extracted from a single reference video encodes hyper-specific values: `cuts_per_minute: 12`, `target_duration_seconds: 87`, `voice_style: "conversational-hushed"`. The pipeline "works" for videos modeled on that exact reference but fails or produces poor results when reused for different content because the values are constraints, not guidelines.

**Why it happens:**
The synthesis prompt instructs the model to "extract the grammar of this video" — the model obeys literally and copies specific measurements. The existing 12 pipelines in `pipeline_defs/` are intentionally general: `animated-explainer.yaml` specifies `pacing_style: "dynamic_social"` with ranges, not exact values. Synthesized pipelines that specify exact numbers create false precision.

**How to avoid:**
- The synthesis prompt must explicitly distinguish: "structural patterns to encode as pipeline defaults" (hook structure, stage sequence, b-roll ratio) vs. "content-specific measurements to omit or make ranges" (exact duration, specific color hex, exact WPM)
- Add a `synthesis_mode` parameter to `pipeline_synthesizer`: `"template"` (generalized, reusable) vs. `"replica"` (close match to reference, single-use)
- Default to `"template"` mode; `"replica"` requires explicit user opt-in with a warning
- The proposal checkpoint must show the user a diff of the synthesized pipeline against the most similar existing pipeline — if the diff is >80% similar, recommend extending the existing pipeline rather than creating a new one

**Warning signs:**
- Synthesized pipeline YAML contains exact numeric values for duration, pace, and color palette
- `pipeline_synthesizer` output has no range fields (min/max), only single values
- User runs the synthesized pipeline on different content and reports it "feels wrong"
- `pipeline_defs/` accumulates many nearly-identical pipelines

**Phase to address:** Phase 2 — synthesis prompt design. The `synthesis_mode` parameter is the lever.

---

### Pitfall 14: Synthesized Pipeline References Tools Not Available in User Environment

**What goes wrong:**
`pipeline_synthesizer` detects that the reference video used ElevenLabs-style narration and synthesizes a pipeline with `tools_available: [elevenlabs_tts, ...]`. The user's environment only has `openai_tts` configured. The synthesized pipeline is technically valid YAML but will fail preflight with `blocked` status for every user who doesn't have ElevenLabs configured.

**Why it happens:**
The synthesizer's analysis-to-YAML prompt does not know what tools are available in the user's environment. It reasons from the reference video's observed characteristics to the "best" tool for replication without checking the registry.

**How to avoid:**
- Before synthesis, run `registry.support_envelope()` and pass the `available_tools[]` list to the synthesis prompt as a hard constraint: "Only reference tools from this list in `tools_available`"
- For required capabilities (TTS, image gen, video gen), use selector tool names (`tts_selector`, `image_selector`, `video_selector`) in `tools_available` instead of specific provider tools — selectors degrade gracefully, hardcoded providers do not
- The semantic validator (Pitfall 5) must also check: for each non-selector tool in `tools_available`, verify it appears in `registry.get_all_names()` with status `AVAILABLE`

**Warning signs:**
- Synthesized pipeline YAML lists specific provider tools (e.g., `elevenlabs_tts`) instead of selectors
- Preflight fails with `blocked` on the first run of a freshly synthesized pipeline
- User has to manually edit the synthesized pipeline before it passes preflight

**Phase to address:** Phase 2 — synthesis prompt design and the semantic validator.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip `video_analysis_selector`, call `gemini_video_analyzer` directly | Faster Phase 1 | Refactor every skill and pipeline when second provider added | Never |
| Use `video_analysis_brief.schema.json` v1.0 as-is | No schema work | v2.0 fields are missing from artifact; synthesis has no data to work with | Never |
| Validate synthesized YAML only with `jsonschema`, skip semantic check | Simple validation | Broken pipelines reach `pipeline_defs/` and mislead the agent | Never for production |
| Write synthesized pipeline directly to `pipeline_defs/` (skip staging) | Simpler file handling | Human approval is bypassed; unreviewed pipelines become available | Never |
| Record real Gemini responses as fixtures once, never refresh | No fixture maintenance burden | Fixtures go stale when schema evolves; tests pass against obsolete contracts | Acceptable for Phase 3 if fixtures are versioned alongside schema |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Gemini Files API | Not polling for ACTIVE state before sending analysis request | Poll `client.files.get(file_name)` with exponential backoff, max 150s timeout |
| Gemini structured output | Using canonical JSON Schema with `$ref`, `additionalProperties: false` | Flatten to inline schema; strip unsupported keywords; test with SDK before Phase 1 exit |
| Gemini video analysis | Sending 1080p source video (large file, slow upload, high token cost) | Downsample to 720p max with FFmpeg before upload; reduces tokens ~40% with no analytical loss |
| `pipeline_loader.list_pipelines()` | Discovering staging YAML before approval | Exclude `pipeline_defs/_staging/` from glob in `pipeline_loader.py` |
| `video_analysis` selector | `capability="video_analysis"` not declared in `gemini_video_analyzer` | Declare `capability = "video_analysis"` in tool class; selector discovers via `get_by_capability()` |
| `GOOGLE_API_KEY` vs. `GEMINI_API_KEY` | New tool uses its own env var name | Follow existing pattern: `os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")` (already established in `google_tts.py` and `google_imagen.py`) |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Uploading full video to Files API for every analysis | Analysis of same reference video costs double on retry | Cache uploaded file URI keyed to video content hash in project artifacts; reuse URI if file state is ACTIVE | First retry on a 100MB video |
| Running `video_analyzer` (local) + `gemini_video_analyzer` (API) sequentially | 2x latency on reference analysis workflow | Run local FFmpeg analysis and Gemini upload in parallel; merge results | Every analysis run |
| Gemini 1 FPS default on rapid-cut social media videos (TikTok, Reels) | `cuts_per_minute` severely underreported; beats missed | Set `fps=2` for videos with detected `pacing_style: rapid_fire`; use `SceneDetect` to pre-compute cut count independently | Any video with >30 cuts/minute |

---

## "Looks Done But Isn't" Checklist

- [ ] **video_analysis selector:** `video_analysis_selector.py` exists with `capability="video_analysis"` — verify `registry.get_by_capability("video_analysis")` returns the selector, not only the raw Gemini tool
- [ ] **Staging path enforcement:** `pipeline_defs/_staging/` is excluded from `pipeline_loader.list_pipelines()` — verify `list_pipelines()` does not return staging files after synthesis
- [ ] **AGENT_GUIDE.md routing:** "Reference Synthesis Entry Point" section added and distinguishes from existing "Reference Video Entry Point" — verify agent routes correctly on "synthesize a pipeline from this video"
- [ ] **Layer 3 skill registered:** `gemini_video_analyzer` tool has `agent_skills = ["gemini-video-analysis"]` and the skill file exists at `.agents/skills/gemini-video-analysis/SKILL.md`
- [ ] **Backward compat:** All 12 existing v1.0 pipelines load and pass `make test-contracts` after schema and tool changes — verify `python -c "from lib.pipeline_loader import list_pipelines; print(list_pipelines())"` returns all 12
- [ ] **Cost guard:** `gemini_video_analyzer` raises or warns before processing any video with estimated token cost > threshold — verify by passing a 1-hour video path

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 — Timecode hallucination | Phase 1 (tool build) | Contract test: `timecode_sanity_check()` rejects timestamps > duration |
| 2 — Structured output returns None on max tokens | Phase 1 (tool build) | Unit test: mock `finish_reason=MAX_TOKENS`, assert `VideoAnalysisError` raised |
| 3 — Schema complexity 400 error | Phase 1 (tool build) | Contract test: `test_gemini_schema_compatibility()` with no API key |
| 4 — Files API stuck in PROCESSING | Phase 1 (tool build) | Unit test: mock PROCESSING→ACTIVE state machine, verify polling |
| 5 — Synthesized pipeline references non-existent skills | Phase 2 (synthesizer build) | Contract test: semantic validator rejects YAML with unknown skill paths |
| 6 — Cost blowup on long videos | Phase 1 (tool build) | Unit test: `max_duration_seconds` enforcement; cost estimator output |
| 7 — Hardcoding Gemini instead of selector | Phase 1 (tool build) | Code review gate: no direct `gemini_video_analyzer` references in skills/pipelines |
| 8 — Missing Layer 3 skill | Phase 1 (tool build) | Phase exit checklist: `.agents/skills/gemini-video-analysis/SKILL.md` must exist |
| 9 — New workflow not in AGENT_GUIDE.md | Phase 2 or integration phase | Phase exit checklist: AGENT_GUIDE.md "Reference Synthesis" section present |
| 10 — Schema drift / artifact registry | Phase 1 (schema creation) | Contract test: `load_schema("video_analysis")` + `validate_artifact()` pass |
| 11 — Human approval bypass | Phase 2 (synthesizer build) | Acceptance test: synthesized file appears in `_staging/`, not `pipeline_defs/`, until approved |
| 12 — Integration tests call real API in CI | Phase 3 (test coverage) | CI config: `make test-contracts` passes without `GEMINI_API_KEY` set |
| 13 — Overfitting to one reference video | Phase 2 (synthesis prompt) | Manual eval: synthesize from one video, run on different content, check pacing flexibility |
| 14 — Pipeline references unavailable tools | Phase 2 (synthesizer build) | Contract test: semantic validator rejects pipeline with tools not in `registry.get_all_names()` |

---

## Sources

- Gemini 2.5 Pro timecode issues: https://discuss.ai.google.dev/t/gemini-2-5-pro-severe-timestamp-timecode-jumping-issues-in-video-transcription-need-workarounds/87242
- Structured output returns None on MAX_TOKENS: https://github.com/googleapis/python-genai/issues/1039
- Schema additionalProperties rejection: https://github.com/googleapis/python-genai/issues/1815
- Files API stuck in PROCESSING: https://discuss.ai.google.dev/t/file-api-always-processing/85107
- Gemini video token rate (~300 tokens/second): https://ai.google.dev/gemini-api/docs/video-understanding
- Gemini structured output limitations: https://ubaidullahmomer.medium.com/why-google-geminis-response-schema-isn-t-ready-for-complex-json-46f35c3aaaea
- Gemini rate limits and pricing 2026: https://www.aifreeapi.com/en/posts/gemini-api-pricing-and-quotas
- Gemini 1 FPS sampling default and override: https://ai.google.dev/gemini-api/docs/video-understanding
- Files API upload size limits: https://ai.google.dev/gemini-api/docs/files

---
*Pitfalls research for: OpenMontage v2.0 Reference Synthesis — video analysis + pipeline synthesis capability*
*Researched: 2026-04-17*
