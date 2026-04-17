# Phase 1: Schema + Adapter - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The canonical `video_analysis` contract exists and is verifiable before any provider code is written. This phase produces JSON Schema files, a schema adapter that converts canonical schemas to a flat representation accepted by Gemini/OpenAI-compatible APIs, and a checkpoint stage registration — all independently testable with no API key and no external services.

**In scope:**
- `schemas/artifacts/video_analysis.schema.json` (canonical, 4 top-level dimension keys: `editing_pacing`, `audio`, `visual_style`, `narrative`)
- `schemas/artifacts/pipeline_synthesis.schema.json` (synthesis run record)
- `lib/schema_adapter.py` (canonical → flat conversion, stripping `$ref`, `additionalProperties: false`, `uniqueItems`)
- `lib/checkpoint.py` `CANONICAL_STAGE_ARTIFACTS` mapping for both new stages
- Contract tests (no API key)

**Out of scope for this phase:**
- Any provider tool code (Phase 2/3)
- Any pipeline synthesizer code beyond the schema file itself (Phase 5)
- Any selector code (Phase 2)
- Layer 3 skills (Phase 2/3)

</domain>

<decisions>
## Implementation Decisions

### Schema Collision (from STATE.md blocker)
- Create NEW file `schemas/artifacts/video_analysis.schema.json` — NOT an extension of the existing `video_analysis_brief.schema.json`. Both schemas coexist. Brief stays unchanged for v1.0 backward compatibility.
- Reason: explicit user decision during requirements definition (REQ ANLZ-02) — cleaner separation between the two artifact contracts, zero risk of breaking v1.0 VideoAnalyzer consumers.

### Schema Shape
- 4 top-level keys: `editing_pacing`, `audio`, `visual_style`, `narrative` (per ANLZ-02)
- Each dimension has typed fields per the inventory in `.planning/research/FEATURES.md`
- Every field that can be uncertain declares a sibling `confidence: "low" | "medium" | "high"` — providers fill this rather than null-defaulting (per ANLZ-04)
- `chunking_metadata` key at top level for merged artifacts (per CHUNK-05) — optional at the schema level, populated by the merger

### Adapter Design
- `lib/schema_adapter.py` exposes a pure function `to_api_schema(canonical: dict) -> dict` with no side effects
- Strips the following unsupported features from the canonical schema: `$ref` (inlined), `additionalProperties: false` (removed), `uniqueItems` (removed), `$schema` (removed), `$id` (removed)
- Does NOT strip `required`, `enum`, `type`, `properties`, `items` — those are supported by Gemini/OpenAI structured output
- Unit tests cover at least: (a) simple schema round-trip, (b) nested $ref inlining, (c) idempotency (adapter output is already flat)

### Checkpoint Mapping (from STATE.md blocker)
- Read `lib/checkpoint.py` FIRST to confirm the exact structure of `CANONICAL_STAGE_ARTIFACTS` before editing
- Add two entries: `video_analysis` → `schemas/artifacts/video_analysis.schema.json`, `pipeline_synthesis` → `schemas/artifacts/pipeline_synthesis.schema.json`
- Preserve all existing entries; do not rename or re-order

### Claude's Discretion
- Exact JSON Schema draft version (2020-12 recommended, matching existing `pipeline_manifest.schema.json`)
- Whether to use a hand-crafted fixture or a Pydantic model for the contract test — pick whichever matches existing codebase patterns (likely `tests/contracts/` has existing examples)
- Error class names in `schema_adapter.py` if any (prefer no exceptions — pure function that returns a new dict)
- File naming/location of the adapter unit tests (follow existing `tests/contracts/` conventions)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `schemas/pipelines/pipeline_manifest.schema.json` — existing schema; use its draft version and authoring style as the template
- `schemas/artifacts/video_analysis_brief.schema.json` (v1.0) — existing artifact schema; read to avoid accidental naming collision and to match the existing file-header style
- `lib/checkpoint.py` — existing canonical stage artifact registry; new entries piggyback on the existing dict (shape must be confirmed before editing)
- `lib/env_loader.py` — pattern for typed env var access, not used directly in this phase but relevant for Phase 2+
- `tests/contracts/` — likely contains schema loadability and validation tests; new adapter tests follow the same structure

### Established Patterns
- JSON Schema Draft 2020-12 (per ARCHITECTURE research)
- Pydantic models for typed config (`lib/config_model.py`)
- No hardcoded tool lists — all discovery via registry (not relevant here, but flag for Phase 2)
- Contract tests run without any API keys (must hold for this phase)

### Integration Points
- Checkpoint system: `lib/checkpoint.py:CANONICAL_STAGE_ARTIFACTS`
- Schema loader: `schemas/artifacts/` filesystem glob (if one exists — research suggested glob-based loading; confirm during planning)
- No tools/selectors touched in this phase

</code_context>

<specifics>
## Specific Ideas

- Use the field inventory from `.planning/research/FEATURES.md` as the source of truth for each dimension's schema fields. Do not invent new fields; if a field seems missing, surface it as a deferred idea rather than adding it.
- Keep the schema strict (`required` + `type` on every field) but free of features Gemini rejects — the adapter exists precisely to bridge canonical strictness and API tolerance.

</specifics>

<deferred>
## Deferred Ideas

- Versioning scheme for the canonical schema (v2.0 implied but no `version` field yet) — defer unless the planner surfaces it as a requirement
- Auto-documentation generation from schema → markdown — out of scope for v2.0
- Pydantic model generation from JSON Schema — considered but unnecessary; provider tools can validate directly

</deferred>
