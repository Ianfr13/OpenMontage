# Roadmap: OpenMontage v2.0 Reference Synthesis

## Overview

This milestone adds two capabilities to OpenMontage: structured video analysis across 4 dimensions (editing+pacing, audio, visual style, narrative) via two interchangeable providers (Gemini SDK direct and OpenRouter), and a pipeline synthesizer that turns that analysis into a persistent, validated `pipeline_defs/` YAML ready for production use. The build order is contract-first: schemas and the adapter ship before any provider; the selector ships alongside the first provider; chunking layers on top of a working provider; the synthesizer consumes analysis artifacts; meta skills and AGENT_GUIDE close the loop; tests validate the full stack including backward compat.

## Milestones

- 🚧 **v2.0 Reference Synthesis** — Phases 1–7 (in progress)

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Schema + Adapter** — Canonical `video_analysis` schema, `schema_adapter`, and checkpoint registration; the contract every downstream component depends on
- [x] **Phase 2: Gemini Provider** — `gemini_video_analyzer` + `video_analyzer_selector` + Layer 3 Gemini skill; first end-to-end analysis path with selector routing from day one (completed 2026-04-17)
- [x] **Phase 3: OpenRouter Provider** — `openrouter_video_analyzer` slots into the existing selector; both providers produce artifacts passing the same canonical schema (completed 2026-04-17)
- [x] **Phase 4: Chunking** — `lib/video_chunker.py` + `lib/analysis_merger.py`; videos >5 min analyzed in bounded-concurrency chunks with merged canonical output (completed 2026-04-17)
- [x] **Phase 5: Synthesizer + Staging** — `lib/pipeline_synthesizer.py` with rule-based matching, staging path, semantic validation, and human-approval gating (completed 2026-04-17)
- [ ] **Phase 6: Skills + Integration** — `reference-synthesis.md` meta skill, refactored `video-reference-analyst.md`, `AGENT_GUIDE.md` disambiguation, `CONTEXT.md` and `requirements.txt` updates
- [ ] **Phase 7: Tests** — Contract tests (no key), dual-provider integration, cross-provider consistency, backward compat gate, E2E smoke

## Phase Details

### Phase 1: Schema + Adapter
**Goal**: The canonical `video_analysis` contract exists and is verifiable before any provider code is written
**Depends on**: Nothing (first phase)
**Requirements**: ANLZ-02, ANLZ-03, SYNTH-09, INT-04
**Success Criteria** (what must be TRUE):
  1. `schemas/artifacts/video_analysis.schema.json` loads and validates a hand-crafted fixture covering all 4 dimension keys (`editing_pacing`, `audio`, `visual_style`, `narrative`)
  2. `lib/schema_adapter.py` converts the canonical schema to a flat dict that contains no `$ref`, no `additionalProperties`, no `uniqueItems`; unit tests pass with no API key
  3. `lib/checkpoint.py` `CANONICAL_STAGE_ARTIFACTS` maps both `video_analysis` and `pipeline_synthesis` to their schema files; `validate_artifact("video_analysis", fixture)` does not raise
  4. `schemas/artifacts/pipeline_synthesis.schema.json` exists and is valid JSON Schema; the v1.0 `video_analysis_brief.schema.json` still loads (no regression)
**Plans**: 4 plans
- [x] 01-01-PLAN.md — Canonical video_analysis.schema.json + contract tests (ANLZ-02, ANLZ-03)
- [x] 01-02-PLAN.md — pipeline_synthesis.schema.json + contract tests (SYNTH-09)
- [x] 01-03-PLAN.md — lib/schema_adapter.py + unit tests (ANLZ-03, INT-04)
- [x] 01-04-PLAN.md — Checkpoint + ARTIFACT_NAMES registration + v1.0 regression guard (INT-04, ANLZ-02)
**UI hint**: no

### Phase 2: Gemini Provider
**Goal**: Agent can route a local video file through the selector to Gemini and receive a validated `video_analysis` artifact
**Depends on**: Phase 1
**Requirements**: GEM-01, GEM-02, GEM-03, GEM-04, GEM-05, ANLZ-01, ANLZ-04, ANLZ-05, SKILL-01, SKILL-03
**Success Criteria** (what must be TRUE):
  1. `video_analyzer_selector` exists with `capability="video_analysis"`; `registry.get_by_capability("video_analysis")` returns the selector, never the raw provider tool
  2. Agent calling the selector with a short test video receives a `video_analysis` artifact that validates against `schemas/artifacts/video_analysis.schema.json`; missing/uncertain fields show `confidence: "low"` rather than null
  3. Files API upload polling works: if a video takes >5 s to reach `ACTIVE` state, the tool waits and retries; `VideoUploadError` raised on `FAILED` or timeout; uploaded file deleted after analysis
  4. Null/truncated structured output (simulated `MAX_TOKENS`) triggers one retry with `analysis_depth="compact"` before raising `VideoAnalysisError`
  5. `.agents/skills/gemini-video-analysis/SKILL.md` exists and is referenced in the tool's `agent_skills` field; a review of one real video's output confirms field-level quality before this phase is closed (SKILL-03 gate)
**Plans**: TBD
**UI hint**: no

### Phase 3: OpenRouter Provider
**Goal**: A second interchangeable provider slots into the existing selector; both providers produce artifacts that pass the same schema
**Depends on**: Phase 2
**Requirements**: OR-01, OR-02, OR-03, OR-04, OR-05, OR-06, ANLZ-06
**Success Criteria** (what must be TRUE):
  1. `openrouter_video_analyzer` exists with `capability="video_analysis"`, `provider="openrouter"`; selector routes to it when `VIDEO_ANALYZER_PROVIDER=openrouter` or only `OPENROUTER_API_KEY` is present
  2. Tool encodes video as `data:video/mp4;base64,...` inline; files exceeding `max_upload_bytes` are rejected before encoding with a clear error
  3. `finish_reason == "length"` (silent truncation) triggers one retry with `analysis_depth="compact"` before raising
  4. Artifacts from both providers pass `jsonschema.validate()` against the same `video_analysis.schema.json`; the selector caller cannot tell which provider was used from the artifact shape (ANLZ-06)
  5. `.agents/skills/openrouter-video-analysis/SKILL.md` exists and is referenced in the tool's `agent_skills`; field-level quality review on one real video completes before phase close (SKILL-03 gate)
**Plans**: 3 plans
- [x] 03-01-PLAN.md — tools/analysis/openrouter_video_analyzer.py + requirements.txt openai pin (OR-01..05, ANLZ-06 tool-side)
- [x] 03-02-PLAN.md — .agents/skills/openrouter-video-analysis/SKILL.md + agent_skills wiring audit (OR-06, SKILL-02)
- [x] 03-03-PLAN.md — conftest extension + 22 unit tests + contract tests incl. cross-provider consistency (OR-01..06, ANLZ-06, SKILL-02)
**UI hint**: no

### Phase 4: Chunking
**Goal**: Videos longer than 5 minutes are automatically split, analyzed per-chunk, and merged into a single canonical artifact with normalized timecodes
**Depends on**: Phase 2
**Requirements**: CHUNK-01, CHUNK-02, CHUNK-03, CHUNK-04, CHUNK-05, CHUNK-06
**Success Criteria** (what must be TRUE):
  1. A video ≤5 min bypasses chunking entirely and reaches the provider in one call; a video >5 min is split into keyframe-aligned chunks by `lib/video_chunker.py` and each chunk produces a valid `video_analysis` artifact
  2. Chunk analysis runs with bounded concurrency (≤4 workers by default); the caller can observe partial progress during long analyses
  3. `lib/analysis_merger.py` merges per-chunk artifacts into a single artifact: global timecodes are normalized, narrative hook comes from chunk 1, CTA from the last chunk, audio fields weighted-averaged by duration
  4. Merged artifact includes `chunking_metadata` (chunk count, per-chunk cost, total duration, provider); `cost_tracker` records each chunk separately
  5. Estimated cost is surfaced before any analysis run on a video >5 min; the user can abort before tokens are spent
**Plans**: 3 plans
- [x] 04-01-PLAN.md — lib/video_chunker.py + VideoChunkingError + unit tests (CHUNK-01, CHUNK-02)
- [x] 04-02-PLAN.md — lib/analysis_merger.py per-dimension merge rules + unit tests (CHUNK-04, CHUNK-05)
- [x] 04-03-PLAN.md — lib/chunked_analyzer.py ThreadPoolExecutor + cost_tracker + contract test (CHUNK-03, CHUNK-06)
**UI hint**: no

### Phase 5: Synthesizer + Staging
**Goal**: A validated `video_analysis` artifact can be turned into a rule-matched, semantically-validated pipeline YAML that lands in `_staging/` and waits for human approval before touching `pipeline_defs/`
**Depends on**: Phase 2
**Requirements**: SYNTH-01, SYNTH-02, SYNTH-03, SYNTH-04, SYNTH-05, SYNTH-06, SYNTH-07, SYNTH-08, SYNTH-10
**Success Criteria** (what must be TRUE):
  1. `lib/pipeline_synthesizer.py` writes ONLY to `pipeline_defs/_staging/<slug>.yaml`; `lib/pipeline_loader.list_pipelines()` never returns paths under `_staging/`
  2. Rule-based matching selects a base pipeline from the 12 existing ones using `pacing_style` + `shot_type_distribution` + `motion_type_distribution`; the `match_score` (0–1) and the chosen base pipeline are both surfaced in the synthesis artifact
  3. Every `skill:` path in the synthesized YAML exists on the filesystem; every tool in `tools_available` appears in the registry; semantic validation rejects the YAML before it reaches the approval checkpoint if either check fails
  4. Slug includes a short content hash; a second synthesis run on the same video produces the same slug (idempotent) and does not silently overwrite an existing staging file
  5. Agent can accept (move `_staging/<slug>.yaml` → `pipeline_defs/<slug>.yaml`) or reject (delete from `_staging/`) via explicit calls; no auto-approval path exists
**Plans**: 3 plans
- [x] 05-01-PLAN.md — lib/pipeline_synthesizer.py core (matcher + slug + staging writer) + ruamel.yaml dep + manifest schema extension + expected_analysis annotations for all 12 pipelines (SYNTH-01, SYNTH-02, SYNTH-04, SYNTH-05, SYNTH-06)
- [x] 05-02-PLAN.md — Semantic validation (validate_synthesized_pipeline) + loader underscore filter + run record emission (schema-valid) (SYNTH-07, SYNTH-08)
- [x] 05-03-PLAN.md — Accept/reject API + lib/llm_fill.py (OpenRouter text-only, bounded, fallback-on-failure) + end-to-end contract test (SYNTH-03, SYNTH-10)
**UI hint**: no

### Phase 6: Skills + Integration
**Goal**: The end-to-end synthesis workflow is fully documented in the agent's instruction layer and the codebase map is accurate
**Depends on**: Phase 5
**Requirements**: SKILL-04, SKILL-05, SKILL-06, INT-01, INT-02, INT-03
**Success Criteria** (what must be TRUE):
  1. `skills/meta/reference-synthesis.md` exists and orchestrates: receive video → select provider via selector → analyze (chunked if needed) → synthesize → present diff for approval; two `awaiting_human` checkpoints are explicitly defined (analysis review, synthesis diff approval)
  2. `skills/meta/video-reference-analyst.md` consumes structured `video_analysis` artifact fields as the primary path; freeform fallback activates only when structured fields are absent (backward compat preserved)
  3. `AGENT_GUIDE.md` "Reference Video Entry Point" section distinguishes "make something like this" (routes to `video-reference-analyst.md`) from "synthesize a pipeline from this reference" (routes to `reference-synthesis.md`); an agent reading only `AGENT_GUIDE.md` reaches the synthesis skill in ≤2 hops
  4. `CONTEXT.md` tools table includes rows for `video_analyzer_selector`, `gemini_video_analyzer`, `openrouter_video_analyzer`; `requirements.txt` adds `google-genai>=1.73`, `openai>=1.0`, `ruamel.yaml>=0.18` with no conflicting deps
**Plans**: 3 plans
- [ ] 06-01-PLAN.md — skills/meta/reference-synthesis.md NEW meta skill (orchestrates video → selector → analyze → synthesize → 2 awaiting_human checkpoints → accept/reject) (SKILL-04)
- [ ] 06-02-PLAN.md — Refactor skills/meta/video-reference-analyst.md to consume structured video_analysis artifact with freeform fallback preserved (SKILL-05)
- [ ] 06-03-PLAN.md — AGENT_GUIDE.md disambiguation + CONTEXT.md tools/libraries extension + lib/env_loader.py env var docs + requirements.txt audit (SKILL-06, INT-01, INT-02, INT-03)
**UI hint**: no

### Phase 7: Tests
**Goal**: The full v2.0 stack is covered by a tiered test suite: contract tests run in CI without API keys; integration and E2E tests are gated and cover both providers
**Depends on**: Phase 6
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05
**Success Criteria** (what must be TRUE):
  1. `make test-contracts` (or equivalent) passes with no API keys set; tests cover: schema loading, `schema_adapter` conversion, staging exclusion, merger output validation, selector preference logic
  2. Integration tests gated by `RUN_INTEGRATION_TESTS=1` run once with Gemini (requires `GEMINI_API_KEY`) and once with OpenRouter (requires `OPENROUTER_API_KEY`); each covers 3 fixture videos (short <2 min, medium 3-5 min, long >5 min chunked)
  3. All 12 existing v1.0 `pipeline_defs/*.yaml` load via `pipeline_loader` and pass their contract tests with no modification (backward compat gate)
  4. E2E smoke test: given a fixture video, the `reference-synthesis.md` flow produces a valid `pipeline_defs/<slug>.yaml` that passes schema + semantic validation for each provider (auto-approve via test fixture)
  5. Cross-provider consistency test runs on the same fixture video with both providers; `cuts_per_minute` divergence within ±15%, `pacing_style` enum matches; divergences are logged but do not auto-fail the test
**Plans**: TBD
**UI hint**: no

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7
Note: Phase 4 (Chunking) depends on Phase 2 (Gemini Provider) only — it can begin as soon as Phase 2 is complete, independently of Phase 3.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Schema + Adapter | 0/? | Not started | - |
| 2. Gemini Provider | 4/4 | Complete    | 2026-04-17 |
| 3. OpenRouter Provider | 3/3 | Complete    | 2026-04-17 |
| 4. Chunking | 3/3 | Complete    | 2026-04-17 |
| 5. Synthesizer + Staging | 3/3 | Complete    | 2026-04-17 |
| 6. Skills + Integration | 0/3 | Not started | - |
| 7. Tests | 0/? | Not started | - |
