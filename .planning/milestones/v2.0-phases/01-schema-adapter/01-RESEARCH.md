# Phase 1: Schema + Adapter — Research

**Researched:** 2026-04-17
**Domain:** JSON Schema authoring + canonical-to-API schema adapter + checkpoint artifact registration
**Confidence:** HIGH (every finding grounded in a concrete file read; no assumptions about upstream APIs — this phase ships zero provider code)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Schema Collision (from STATE.md blocker):**
- Create NEW file `schemas/artifacts/video_analysis.schema.json` — NOT an extension of the existing `video_analysis_brief.schema.json`. Both schemas coexist. Brief stays unchanged for v1.0 backward compatibility.
- Reason: explicit user decision during requirements definition (REQ ANLZ-02) — cleaner separation between the two artifact contracts, zero risk of breaking v1.0 VideoAnalyzer consumers.

**Schema Shape:**
- 4 top-level keys: `editing_pacing`, `audio`, `visual_style`, `narrative` (per ANLZ-02)
- Each dimension has typed fields per the inventory in `.planning/research/FEATURES.md`
- Every field that can be uncertain declares a sibling `confidence: "low" | "medium" | "high"` — providers fill this rather than null-defaulting (per ANLZ-04)
- `chunking_metadata` key at top level for merged artifacts (per CHUNK-05) — optional at the schema level, populated by the merger

**Adapter Design:**
- `lib/schema_adapter.py` exposes a pure function `to_api_schema(canonical: dict) -> dict` with no side effects
- Strips: `$ref` (inlined), `additionalProperties: false` (removed), `uniqueItems` (removed), `$schema` (removed), `$id` (removed)
- Does NOT strip: `required`, `enum`, `type`, `properties`, `items` — supported by Gemini/OpenAI structured output
- Unit tests cover at least: (a) simple schema round-trip, (b) nested $ref inlining, (c) idempotency (adapter output is already flat)

**Checkpoint Mapping (from STATE.md blocker):**
- Read `lib/checkpoint.py` FIRST to confirm the exact structure of `CANONICAL_STAGE_ARTIFACTS` before editing
- Add two entries: `video_analysis` and `pipeline_synthesis` mapped to their respective schemas
- Preserve all existing entries; do not rename or re-order

### Claude's Discretion
- Exact JSON Schema draft version (2020-12 recommended, matching existing `pipeline_manifest.schema.json`)
- Whether to use a hand-crafted fixture or a Pydantic model for the contract test — pick whichever matches existing codebase patterns
- Error class names in `schema_adapter.py` if any (prefer no exceptions — pure function that returns a new dict)
- File naming/location of the adapter unit tests (follow existing `tests/contracts/` conventions)

### Deferred Ideas (OUT OF SCOPE)
- Versioning scheme for the canonical schema (v2.0 implied but no `version` field yet) — defer unless the planner surfaces it as a requirement
- Auto-documentation generation from schema → markdown — out of scope for v2.0
- Pydantic model generation from JSON Schema — considered but unnecessary; provider tools can validate directly

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ANLZ-02 | `schemas/artifacts/video_analysis.schema.json` exists with 4 top-level dimension keys | Field inventory confirmed in `.planning/research/FEATURES.md` (editing_pacing/audio/visual_style/narrative) — ~50 fields total; canonical template is `schemas/artifacts/video_analysis_brief.schema.json` (same author-style, Draft 2020-12) |
| ANLZ-03 | `lib/schema_adapter.py` produces API-safe flat schema; strips `$ref`, `additionalProperties: false`, `uniqueItems`; unit tests pass without API key | `jsonschema 4.26.0` installed; codebase has no `jsonref`/`RefResolver` usage; all existing artifact schemas use `$ref: 0 occurrences` — $ref support is defensive but mandated; `additionalProperties: false` occurs only in `pipeline_manifest.schema.json` (not in artifact schemas) — adapter must handle it regardless |
| SYNTH-09 | `schemas/artifacts/pipeline_synthesis.schema.json` exists — captures synthesis run record | Required fields per SYNTH-09: `base_pipeline`, `match_score`, `mode`, `staging_path`, `diff_against_base`, `validation_status`, `source_analysis_checksum`, `provider_used` |
| INT-04 | `lib/checkpoint.py:CANONICAL_STAGE_ARTIFACTS` maps the new `video_analysis` and `pipeline_synthesis` stages | Confirmed dict shape `dict[str, str]` where value is the ARTIFACT NAME, not a schema path — see Finding 3; this contradicts CONTEXT.md phrasing and the planner must resolve it |

</phase_requirements>

## Project Constraints (from CLAUDE.md / AGENT_GUIDE.md)

OpenMontage is an instruction-driven video production system. Relevant to this phase:

- **Canonical artifacts must validate against JSON schemas in `schemas/artifacts/`** (AGENT_GUIDE.md:508). This phase adds two new canonical artifacts to that contract.
- **Stage contract rule:** completed/awaiting_human checkpoints must include the stage's canonical artifact (AGENT_GUIDE.md:505). INT-04 enforces this for the new stages.
- **Do not hand-roll tool discovery / hardcoded lists** — not directly relevant to Phase 1 (no tool code ships), but flagged because the `video_analyzer_selector` (Phase 2) depends on registry auto-discovery.
- **Invalid canonical artifacts are contract violations and should fail fast** (AGENT_GUIDE.md:554) — `validate_artifact` raises `jsonschema.ValidationError`; this phase must maintain that behavior for the new artifacts.

No other CLAUDE.md directives conflict with Phase 1 work. This phase ships schemas + a pure adapter function + a checkpoint-registry edit — zero tool code, zero provider code, zero skills.

## Research Scope

Investigated domains:

1. **Existing JSON Schema authoring style** in `schemas/artifacts/` and `schemas/pipelines/` — to template the two new schema files.
2. **`CANONICAL_STAGE_ARTIFACTS` exact shape** in `lib/checkpoint.py` — to resolve INT-04 with the correct edit pattern (this is a called-out blocker in STATE.md and CONTEXT.md).
3. **Existing `validate_artifact` pathway** in `schemas/artifacts/__init__.py` — to understand how Phase 1's new schemas become discoverable and validatable.
4. **Contract test patterns** in `tests/contracts/` — to mirror for new adapter tests.
5. **$ref inlining options** given `jsonschema>=4.20` is the only installed schema library (no `jsonref`).
6. **Collision audit** for stage names `video_analysis` and `pipeline_synthesis` across the codebase.
7. **Dependency footprint** (`requirements.txt`, `pyproject.toml`) to confirm no new deps are needed for Phase 1.
8. **4-dimension field inventory** from `.planning/research/FEATURES.md` — source of truth for `video_analysis` schema properties.

## Key Findings

### Finding 1 — JSON Schema Draft 2020-12 is the codebase standard

**Confidence:** HIGH
**Evidence:** Every artifact schema in `schemas/artifacts/*.json` declares `"$schema": "https://json-schema.org/draft/2020-12/schema"` as its first property. The pipeline manifest schema (`schemas/pipelines/pipeline_manifest.schema.json:1-3`) matches. The v1.0 `video_analysis_brief.schema.json:1-4` also uses 2020-12 but omits `$id`.

**Implication:** The two new schemas MUST use Draft 2020-12. They should also include an `$id` following the convention `openmontage/artifacts/video_analysis` and `openmontage/artifacts/pipeline_synthesis` — this matches `brief.schema.json:3`, `render_report.schema.json:3`, `pipeline_manifest.schema.json:3`. The existing v1.0 `video_analysis_brief.schema.json` is an outlier in omitting `$id`; the new files should align with the broader convention, not the outlier.

### Finding 2 — Authoring style: flat, inline, no `$ref`

**Confidence:** HIGH
**Evidence:** `grep '$ref' /workspace/schemas/artifacts/*.json` returns zero matches. All existing artifact schemas are fully inlined. Nested structures (e.g., `video_analysis_brief.schema.json` lines 34-61 for `content_analysis`) are written inline as nested `type: object` blocks. Only `pipeline_manifest.schema.json` uses `oneOf` (line 22) and `additionalProperties: false` (lines 116, 146, 157, 160) — but no `$ref`.

**Implication:** The new canonical `video_analysis.schema.json` and `pipeline_synthesis.schema.json` SHOULD be authored in the same flat inline style. The adapter's `$ref` inlining capability becomes defensive — it exists so Gemini/OpenAI never see unsupported features if a schema ever gains `$ref`, but in practice Phase 1's schemas will have nothing to inline. The adapter test for `$ref` inlining must therefore exercise a synthetic schema fragment, not an existing file.

### Finding 3 — `CANONICAL_STAGE_ARTIFACTS` maps stage → artifact NAME (not schema path)

**Confidence:** HIGH
**Evidence:** `lib/checkpoint.py:30-40` shows:
```python
CANONICAL_STAGE_ARTIFACTS = {
    "research": "research_brief",
    "proposal": "proposal_packet",
    "idea": "brief",
    "script": "script",
    ...
}
```
Every value is an artifact NAME — a bare string that is joined with `.schema.json` at load time by `schemas/artifacts/__init__.py:33-34`:
```python
path = SCHEMA_DIR / f"{name}.schema.json"
```
The validation chain used by `lib/checkpoint.py:95-119` is: stage → artifact name (via `CANONICAL_STAGE_ARTIFACTS[stage]`) → schema file (via `load_schema(artifact_name)`). `ARTIFACT_NAMES` in `schemas/artifacts/__init__.py:13-29` is a hand-maintained allowlist gating `validate_artifact` calls inside `_validate_artifacts_for_stage`.

**Implication (CRITICAL — CONTEXT.md is slightly misleading):** CONTEXT.md says map `video_analysis → schemas/artifacts/video_analysis.schema.json`. The ACTUAL edit is:

```python
# In lib/checkpoint.py:
CANONICAL_STAGE_ARTIFACTS = {
    ...existing entries...,
    "video_analysis": "video_analysis",
    "pipeline_synthesis": "pipeline_synthesis",
}

# In schemas/artifacts/__init__.py:
ARTIFACT_NAMES = [
    ...existing names...,
    "video_analysis",
    "pipeline_synthesis",
]
```

Then `schemas/artifacts/video_analysis.schema.json` and `schemas/artifacts/pipeline_synthesis.schema.json` must exist on disk (convention drives the path). The planner MUST include an explicit task for editing `schemas/artifacts/__init__.py` as well — without it, `ARTIFACT_NAMES` is stale and `_validate_artifacts_for_stage` silently skips validation (the `if artifact_name not in ARTIFACT_NAMES: continue` at `lib/checkpoint.py:108-109`).

Also note: the values in the dict happen to equal the keys for the new entries because the stage name and the artifact name are the same. Existing entries vary (`research → research_brief`, `idea → brief`) so this alignment is a coincidence, not a rule. Keep the pair of strings explicit.

### Finding 4 — `validate_artifact` is a thin `jsonschema.validate` wrapper

**Confidence:** HIGH
**Evidence:** `schemas/artifacts/__init__.py:41-44`:
```python
def validate_artifact(name: str, data: dict[str, Any]) -> None:
    schema = load_schema(name)
    jsonschema.validate(instance=data, schema=schema)
```
Raises `jsonschema.exceptions.ValidationError` on mismatch (standard library behavior), caught in `lib/checkpoint.py:113-119` and re-raised as `CheckpointValidationError`.

**Implication:** The Phase 1 success-criterion sentence "`validate_artifact("video_analysis", fixture)` does not raise" maps directly to: (a) the file `schemas/artifacts/video_analysis.schema.json` must exist, (b) `"video_analysis"` must appear in `ARTIFACT_NAMES`, (c) the fixture must satisfy the schema. No new validation code is needed — only data.

### Finding 5 — Contract test convention: pytest classes, inline fixtures, no `tests/fixtures/` dir

**Confidence:** HIGH
**Evidence:** `ls /workspace/tests/` shows no `fixtures/` directory. `tests/contracts/test_phase0_contracts.py:46-249` defines a single `sample_artifact(name: str) -> dict` helper that returns minimal schema-valid dicts inline (big if/elif chain keyed by artifact name). Test classes (e.g., `TestSchemas`, `TestCheckpoint`) group related assertions. No `@pytest.fixture` decorators in `tests/contracts/` (confirmed by grep). Tests add the repo root to `sys.path` via `sys.path.insert(0, str(PROJECT_ROOT))` at the top.

**Implication:** Phase 1 tests should mirror this pattern:
- Create a single new file `tests/contracts/test_video_analysis_schema.py` (or extend `test_phase0_contracts.py` — the latter is cleaner given how close the work is to Phase 0 infrastructure; the planner chooses).
- Extend the existing `sample_artifact(name)` function with `"video_analysis"` and `"pipeline_synthesis"` cases, each returning a minimal valid dict covering all 4 dimensions.
- Use pytest classes for grouping: `TestVideoAnalysisSchema`, `TestPipelineSynthesisSchema`, `TestSchemaAdapter`, `TestCheckpointRegistration`.
- Use inline dict fixtures, not fixture files. No `tests/fixtures/` directory should be created.

### Finding 6 — `jsonschema 4.26.0` is installed; no `jsonref`, no `RefResolver` usage

**Confidence:** HIGH
**Evidence:** `requirements.txt` pins `jsonschema>=4.20`. `python3 -c "import jsonschema; print(jsonschema.__version__)"` → `4.26.0`. Grep for `jsonref|RefResolver` across the repo returns zero matches.

**Implication:** `$ref` inlining must be hand-rolled in `lib/schema_adapter.py` OR a new dependency must be added. Recommendation: **hand-roll a minimal inliner.** Reasons:
- Current artifact schemas have no `$ref` (Finding 2). The feature is purely defensive.
- Adding `jsonref` introduces a dependency with its own lazy-resolution quirks (returns proxy objects, not plain dicts) that complicate the "pure function returns a new dict" contract.
- `jsonschema.RefResolver` is deprecated as of jsonschema 4.18 (replaced by the `referencing` library) — risky to rely on.
- A hand-rolled inliner is ~30 lines of recursive walk with a `#/definitions/...`-path dereference. Fits the project's "don't hand-roll what libraries do well" principle only when libraries actually solve the problem — here, they introduce more risk than they remove.

The adapter's function surface remains clean: `to_api_schema(canonical: dict) -> dict` walks the tree, resolves internal `$ref` pointers against the root, and strips the forbidden keys on the way down. A JSON pointer helper (`"#/definitions/foo" → definitions["foo"]`) is 5 lines.

### Finding 7 — v1.0 `video_analysis_brief.schema.json` field overlap audit

**Confidence:** HIGH
**Evidence:** Full read of `schemas/artifacts/video_analysis_brief.schema.json`. The v1.0 file's top-level keys are `version`, `source`, `content_analysis`, `structure_analysis`, `style_profile`, `narration_transcript`, `replication_guidance`, `keyframes`. It has ZERO top-level keys named `editing_pacing`, `audio`, `visual_style`, or `narrative`.

**Implication:** No field-name collisions at the top level between v1.0 brief and v2.0 canonical. Some SECOND-level field names will repeat across both schemas (e.g., `cuts_per_minute` appears in `structure_analysis.pacing_profile` in v1.0 and will appear in `editing_pacing` in v2.0). That's fine — they're in different containers, and JSON Schema has no cross-schema namespace concept. No rename or guardrail is required.

The `transition_types` field (v1.0 at `style_profile.transition_types`, v2.0 planned at `editing_pacing.transition_types`) is the only field with a semantically-identical name in two different locations. The planner should confirm the canonical location — FEATURES.md puts it under `editing_pacing`, so that wins for v2.0. No issue.

### Finding 8 — No stage-name collision for `video_analysis` or `pipeline_synthesis`

**Confidence:** HIGH
**Evidence:** `grep -rn "video_analysis\|pipeline_synthesis" schemas lib pipeline_defs tools` returns hits ONLY for the existing `video_analysis_brief` artifact (15 occurrences across 8 files) and the condition string `"video_analysis_brief_exists"` in three pipeline manifests. No existing code uses the bare strings `video_analysis` (without `_brief`) or `pipeline_synthesis` as stage names, artifact names, or schema file paths.

**Implication:** The new stage names are safe to register. No pipeline manifest refers to `video_analysis` as a stage (stages today are hardcoded in `STAGES = ["research", "proposal", "idea", "script", "scene_plan", "assets", "edit", "compose", "publish"]`). The new entries expand `CANONICAL_STAGE_ARTIFACTS` but will NOT appear in `STAGES` or `ALL_KNOWN_STAGES` — and that's fine, because `_validate_artifacts_for_stage` (`lib/checkpoint.py:95`) is looked up through `CANONICAL_STAGE_ARTIFACTS[stage]`, which will now include them. The stages don't need to join `STAGES`/`ALL_KNOWN_STAGES` in Phase 1 — they'll join via pipeline manifests in later phases. Flag: if a checkpoint is ever written with `stage="video_analysis"`, current code at `lib/checkpoint.py:138-142` will reject it as an invalid stage. That's the correct failure mode for Phase 1 (no pipeline declares `video_analysis` as a stage yet). Do not preemptively add to `STAGES` — Phase 6 owns that integration.

### Finding 9 — Error style in `lib/*.py`: raise explicitly-named subclass, never swallow

**Confidence:** HIGH
**Evidence:** `lib/checkpoint.py:85-87` defines `class CheckpointValidationError(ValueError)` and raises it throughout. `jsonschema.ValidationError` is caught and re-wrapped (`lib/checkpoint.py:113-119`). `lib/env_loader.py` and `lib/config_model.py` follow the same convention (typed exception subclasses; no silent failure).

**Implication:** If `lib/schema_adapter.py` needs any error type (e.g., unresolvable `$ref`), raise `SchemaAdapterError(ValueError)`. BUT the user preference in CONTEXT.md is "prefer no exceptions — pure function that returns a new dict." Reconciliation: `to_api_schema` should be a pure function on valid input; on malformed input (e.g., `$ref` pointing to a missing definition), raising is the right thing to do because that's a programmer error, not a data error. Add a single exception class `SchemaAdapterError(ValueError)` for the unresolvable-ref case only.

### Finding 10 — Synthesis artifact shape (SYNTH-09)

**Confidence:** HIGH
**Evidence:** REQUIREMENTS.md line 59 (SYNTH-09) lists the required fields verbatim: `base_pipeline`, `match_score`, `mode`, `staging_path`, `diff_against_base`, `validation_status`, `source_analysis_checksum`, `provider_used`. ROADMAP.md Phase 5 Success Criteria 2 adds that `match_score` is "(0–1)" and the chosen base pipeline is "surfaced." The `mode` field takes values `template` or `replica` (per SYNTH-04).

**Implication:** The `pipeline_synthesis.schema.json` shape is small and well-specified:

```
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "openmontage/artifacts/pipeline_synthesis",
  "type": "object",
  "required": ["version", "base_pipeline", "match_score", "mode",
               "staging_path", "validation_status", "source_analysis_checksum",
               "provider_used"],
  "properties": {
    "version":                     { "type": "string", "const": "1.0" },
    "base_pipeline":               { "type": "string" },
    "match_score":                 { "type": "number", "minimum": 0, "maximum": 1 },
    "mode":                        { "type": "string", "enum": ["template", "replica"] },
    "staging_path":                { "type": "string" },
    "diff_against_base":           { "type": "string",
                                     "description": "Unified-diff text or structured diff — free-form for v2.0" },
    "validation_status":           { "type": "string",
                                     "enum": ["valid", "invalid", "pending"] },
    "source_analysis_checksum":    { "type": "string",
                                     "description": "Content hash of the video_analysis artifact used as source" },
    "provider_used":               { "type": "string",
                                     "enum": ["gemini", "openrouter"] }
  }
}
```
Planner should refine enum on `validation_status` with STATE.md / Phase 5 research if needed; this is a reasonable starting shape. `diff_against_base` left as string is fine for v2.0 — Phase 5 chose its representation, which is a freeform "diff text" per the natural reading of the requirement.

### Finding 11 — Dependency footprint

**Confidence:** HIGH
**Evidence:** `requirements.txt` contains: `pyyaml>=6.0`, `pydantic>=2.0`, `jsonschema>=4.20`, `python-dotenv>=1.0`, `Pillow>=10.0`, `requests>=2.31`. No `pyproject.toml` present.

**Implication:** Phase 1 adds ZERO new dependencies. Everything the phase needs (schema authoring, validation, adapter walk, test framework) is already available via `jsonschema` + `pytest` + stdlib. The Phase 6 integration requirement INT-02 (`google-genai`, `openai`, `ruamel.yaml`) is explicitly out of scope for Phase 1.

## Recommended Approach

### Task structure (the planner should produce ~5-6 tasks in this phase)

| Order | Task | Files touched | Why separable |
|-------|------|---------------|---------------|
| 1 | Author `schemas/artifacts/video_analysis.schema.json` | NEW file | Most content; independently reviewable; no code dependencies |
| 2 | Author `schemas/artifacts/pipeline_synthesis.schema.json` | NEW file | Small; depends on nothing |
| 3 | Register both artifacts in `schemas/artifacts/__init__.py` | MODIFY `ARTIFACT_NAMES` list | One-liner each; gate for validate_artifact |
| 4 | Register both stages in `lib/checkpoint.py:CANONICAL_STAGE_ARTIFACTS` | MODIFY dict | Depends on Task 3 being done so load_schema works |
| 5 | Implement `lib/schema_adapter.py` with `to_api_schema()` | NEW file | Pure function; no dependency on schema files (tests can use inline schemas) |
| 6 | Contract tests: schema loading, fixture validation, adapter unit tests, checkpoint registration, v1.0 regression | MODIFY or extend `tests/contracts/test_phase0_contracts.py` OR new file | Last: depends on all prior tasks |

Tasks 1–2 can run in parallel (they touch different files). Task 3 blocks on 1 and 2. Task 4 blocks on 3. Task 5 is parallel to 1–4. Task 6 blocks on everything.

### Schema authoring rules for `video_analysis.schema.json`

- Use Draft 2020-12 + `$id: openmontage/artifacts/video_analysis`.
- Top-level: `version` (const `"2.0"` — align with milestone branding), the 4 dimension keys as required, `chunking_metadata` as optional, optional `source` stub (mirroring v1.0 brief's source block is natural so providers can record the analyzed video's origin) and optional `shot_boundary_source` (per ANLZ-05).
- Each dimension object is `type: "object"` with `required` listing only the mandatory fields; the rest are optional. Use `enum` wherever FEATURES.md specifies an enum. Use `type: "number"`/`"integer"`/`"string"`/`"boolean"`/`"array"` matching the inventory.
- `confidence` pattern: for each field that can be uncertain, add a sibling field `<fieldname>_confidence` with `{ "type": "string", "enum": ["low", "medium", "high"] }`. Alternative: a single top-level `confidence` map `{field_name: level}`. **Recommendation:** the sibling-pattern is more discoverable and schema-local, but inflates the schema. If the planner prefers readability, use a single `confidence: { type: "object", additionalProperties: {enum: [low, medium, high]} }` at the dimension level. **The planner should pick one and be consistent** — do not mix.
- `shot_type_distribution` and `motion_type_distribution` are objects whose values are numbers (per FEATURES.md); don't attempt to constrain "must sum to 1.0" via JSON Schema (not expressible in Draft 2020-12 short of a custom keyword — record it as a schema `description` and enforce in the provider's `agent_skills` Layer 3 skill instead, which is Phase 2/3's concern).
- `section_structure` is an array of objects `[{label, approx_start_s, approx_end_s, summary}]`.
- `suggested_remotion_scene_types` is `array[string]` — do NOT constrain via enum (scene types evolve; Phase 6 adds them; keeping it open here prevents coupling).

### Adapter implementation guidance

Skeleton (for the planner — not final code):

```python
# lib/schema_adapter.py
"""Convert canonical JSON Schema (Draft 2020-12) to a flat dict accepted by
Gemini / OpenAI structured-output APIs.

Strips: $ref (inlined), additionalProperties: false, uniqueItems, $schema, $id.
Preserves: type, properties, required, items, enum, const, description, format.

Pure function. No I/O. No mutation of input.
"""
from copy import deepcopy
from typing import Any

STRIP_KEYS = {"$schema", "$id", "additionalProperties", "uniqueItems"}

class SchemaAdapterError(ValueError):
    """Raised when a $ref cannot be resolved within the schema."""


def to_api_schema(canonical: dict) -> dict:
    """Return an API-safe copy of `canonical`. Does not mutate input."""
    root = deepcopy(canonical)
    return _walk(root, root)


def _walk(node: Any, root: dict) -> Any:
    if isinstance(node, dict):
        # Inline $ref first, then recurse
        if "$ref" in node and list(node.keys()) == ["$ref"]:
            return _walk(_resolve_ref(node["$ref"], root), root)
        out = {}
        for k, v in node.items():
            if k in STRIP_KEYS:
                continue  # also silently drops additionalProperties: true — acceptable
            # Special case: keep additionalProperties if it is a schema (dict),
            # only strip when it is literally `false`.
            if k == "additionalProperties" and v is not False:
                out[k] = _walk(v, root)
                continue
            out[k] = _walk(v, root)
        return out
    if isinstance(node, list):
        return [_walk(x, root) for x in node]
    return node


def _resolve_ref(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise SchemaAdapterError(f"Only internal refs supported: {ref!r}")
    node = root
    for part in ref.lstrip("#/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if part not in node:
            raise SchemaAdapterError(f"Unresolvable ref: {ref!r}")
        node = node[part]
    return node
```

Key subtleties for the planner to verify in tests:
- `deepcopy` at the top ensures the input dict is not mutated even when `$ref` is inlined in-place.
- The `additionalProperties` special-case keeps schema-typed values (e.g., `additionalProperties: {type: "string"}` is legal and meaningful); only `additionalProperties: false` is the API-rejected form. Re-read STRIP_KEYS: `additionalProperties` must NOT be in the unconditional strip list. Correct rule: strip only when value is `False`.
- `uniqueItems` always stripped (no conditional).
- `$schema`, `$id` always stripped.

### Contract test structure (Task 6)

Tests to include, all pytest-class-based:

| Test class | Test method(s) |
|------------|----------------|
| `TestVideoAnalysisSchema` | `test_schema_loads`, `test_fixture_validates`, `test_rejects_invalid_pacing_style`, `test_rejects_missing_dimension_key` |
| `TestPipelineSynthesisSchema` | `test_schema_loads`, `test_fixture_validates`, `test_rejects_match_score_out_of_range`, `test_rejects_invalid_mode_enum` |
| `TestSchemaAdapter` | `test_strips_schema_and_id`, `test_strips_additional_properties_false`, `test_keeps_additional_properties_object`, `test_strips_unique_items`, `test_inlines_internal_ref`, `test_raises_on_unresolvable_ref`, `test_idempotent`, `test_does_not_mutate_input`, `test_preserves_enum_required_type_properties_items` |
| `TestCheckpointRegistration` | `test_canonical_stage_artifacts_has_video_analysis`, `test_canonical_stage_artifacts_has_pipeline_synthesis`, `test_validate_artifact_accepts_valid_fixture`, `test_validate_artifact_rejects_empty_dict` |
| `TestV1Regression` | `test_video_analysis_brief_still_loads`, `test_video_analysis_brief_fixture_still_validates` |

All tests must execute with `RUN_INTEGRATION_TESTS` unset — no network, no API keys, no external processes.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (implied by existing `tests/contracts/*.py`; version not pinned in `requirements.txt` — present in the devcontainer) |
| Config file | none detected at repo root — pytest uses auto-discovery |
| Quick run command | `pytest tests/contracts/ -x -q` |
| Full suite command | `pytest tests/ -x` |
| Phase gate command | `pytest tests/contracts/test_phase0_contracts.py tests/contracts/<new-file> -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| ANLZ-02 | `video_analysis.schema.json` exists and loads | unit | `pytest tests/contracts/<new>.py::TestVideoAnalysisSchema::test_schema_loads -x` | Wave 0 |
| ANLZ-02 | Hand-crafted fixture covering 4 dimensions validates | unit | `pytest tests/contracts/<new>.py::TestVideoAnalysisSchema::test_fixture_validates -x` | Wave 0 |
| ANLZ-02 | Schema rejects missing dimension key | unit | `pytest tests/contracts/<new>.py::TestVideoAnalysisSchema::test_rejects_missing_dimension_key -x` | Wave 0 |
| ANLZ-03 | `to_api_schema` strips `$ref`, `additionalProperties: false`, `uniqueItems`, `$schema`, `$id` | unit | `pytest tests/contracts/<new>.py::TestSchemaAdapter -x` | Wave 0 |
| ANLZ-03 | Adapter is idempotent on already-flat schema | unit | `pytest tests/contracts/<new>.py::TestSchemaAdapter::test_idempotent -x` | Wave 0 |
| ANLZ-03 | Adapter is a pure function (input not mutated) | unit | `pytest tests/contracts/<new>.py::TestSchemaAdapter::test_does_not_mutate_input -x` | Wave 0 |
| ANLZ-03 | Adapter preserves `required`, `enum`, `type`, `properties`, `items` | unit | `pytest tests/contracts/<new>.py::TestSchemaAdapter::test_preserves_enum_required_type_properties_items -x` | Wave 0 |
| SYNTH-09 | `pipeline_synthesis.schema.json` exists and loads | unit | `pytest tests/contracts/<new>.py::TestPipelineSynthesisSchema::test_schema_loads -x` | Wave 0 |
| SYNTH-09 | Required SYNTH-09 fields all present and enforced | unit | `pytest tests/contracts/<new>.py::TestPipelineSynthesisSchema::test_fixture_validates -x` | Wave 0 |
| SYNTH-09 | `match_score` bounded [0, 1] | unit | `pytest tests/contracts/<new>.py::TestPipelineSynthesisSchema::test_rejects_match_score_out_of_range -x` | Wave 0 |
| SYNTH-09 | `mode` restricted to `template`/`replica` | unit | `pytest tests/contracts/<new>.py::TestPipelineSynthesisSchema::test_rejects_invalid_mode_enum -x` | Wave 0 |
| INT-04 | `CANONICAL_STAGE_ARTIFACTS["video_analysis"]` present | unit | `pytest tests/contracts/<new>.py::TestCheckpointRegistration::test_canonical_stage_artifacts_has_video_analysis -x` | Wave 0 |
| INT-04 | `CANONICAL_STAGE_ARTIFACTS["pipeline_synthesis"]` present | unit | `pytest tests/contracts/<new>.py::TestCheckpointRegistration::test_canonical_stage_artifacts_has_pipeline_synthesis -x` | Wave 0 |
| INT-04 | `validate_artifact("video_analysis", fixture)` does not raise | unit | `pytest tests/contracts/<new>.py::TestCheckpointRegistration::test_validate_artifact_accepts_valid_fixture -x` | Wave 0 |
| (regression) | v1.0 `video_analysis_brief.schema.json` still loads | unit | `pytest tests/contracts/<new>.py::TestV1Regression -x` | Wave 0 |
| (regression) | Existing Phase 0 contract tests still pass | unit | `pytest tests/contracts/test_phase0_contracts.py -x` | EXISTS |

### Sampling Rate
- **Per task commit:** `pytest tests/contracts/<new_file>.py -x -q` (<5 seconds — pure schema + function tests, no I/O beyond file reads)
- **Per wave merge:** `pytest tests/contracts/ -x` (runs all contract tests including Phase 0 regression)
- **Phase gate:** Full test suite `pytest tests/ -x` green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/contracts/test_phase1_schema_adapter.py` — covers all Phase 1 requirements (OR inline into `test_phase0_contracts.py` — planner decides)
- [ ] Extend `sample_artifact()` helper in `test_phase0_contracts.py` to include `"video_analysis"` and `"pipeline_synthesis"` minimal-valid dicts
- [ ] No framework install needed — pytest + jsonschema already available

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.10+ | All test + adapter code | ✓ (devcontainer) | Per STATE.md devcontainer requirement | — |
| `jsonschema` | Schema loading, `validate_artifact`, adapter tests | ✓ | 4.26.0 | — |
| `pytest` | Contract tests | ✓ (imported in existing tests) | Not pinned; present | — |
| `pyyaml` | Not used in Phase 1 | ✓ | ≥6.0 | — |

**No missing dependencies.** Phase 1 is a code + schema authoring phase with no external services, no GPU, no network. All work runs inside the devcontainer.

## Dependencies

**No new Python packages required.** Phase 1 ships entirely on existing `requirements.txt` (`jsonschema>=4.20` is the only library touched). The Phase 6 integration task (INT-02) adds `google-genai`, `openai`, `ruamel.yaml` later.

## Runtime State Inventory

**Not applicable** — this is a greenfield phase. New files + additive edits to existing Python modules. No rename, no migration, no data store, no running service touched.

| Category | Items Found |
|----------|-------------|
| Stored data | None — no checkpoints or artifacts migrate; existing checkpoints remain valid because `ARTIFACT_NAMES` only gains entries |
| Live service config | None — no external service has `video_analysis` or `pipeline_synthesis` registered as anything today |
| OS-registered state | None |
| Secrets/env vars | None — Phase 1 runs without any env vars |
| Build artifacts | None — pure Python + JSON files; no egg-info or compiled artifacts |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The planner's preferred confidence pattern is sibling-field per uncertain field (not dimension-level map). | Recommended Approach → Schema authoring rules | LOW — easy to refactor before Phase 2 consumes the schema; both patterns validate provider output equally well. The planner / executor can choose based on schema ergonomics. |
| A2 | `pipeline_synthesis.schema.json` `validation_status` enum of `["valid", "invalid", "pending"]` is reasonable. | Finding 10 | LOW — Phase 5 owns the field's producer code; if Phase 5 needs `"staged"` or similar, the schema can be amended then. Not load-bearing for Phase 1 success criteria. |
| A3 | `version: "2.0"` is the right `const` for the canonical schema's version field. | Recommended Approach → Schema authoring rules | LOW — easy to change pre-Phase-2; SYNTH/ANLZ tests don't pin this. Aligns with milestone branding. |
| A4 | The existing `sample_artifact()` helper in `test_phase0_contracts.py` is the canonical place to extend with new artifact fixtures (rather than a new file). | Finding 5 / Recommended Approach | LOW — planner can choose either a new file or extend the existing one; both are consistent with codebase style. |
| A5 | Treat `additionalProperties` with a dict (schema) value as preserved; strip only when value is literally `False`. | Recommended Approach → Adapter implementation | MEDIUM — if `additionalProperties: true` flows through to Gemini, it's harmless; if `additionalProperties: {some schema}` is stripped incorrectly, schemas lose expressiveness. The recommendation is: strip only the literal `False` form. Adapter tests must exercise both the `false` strip and the dict-preserve cases. |

## Open Questions (RESOLVED)

1. **Fixture placement.** Should `video_analysis` and `pipeline_synthesis` minimal fixtures live:
   - (a) extended into `sample_artifact()` inside `tests/contracts/test_phase0_contracts.py`, OR
   - (b) in a new `tests/contracts/test_phase1_schema_adapter.py` with its own helpers?

   **Recommendation:** (b) — new file. Phase 0 contracts are stable; isolating Phase 1 tests keeps the blast radius small and makes per-phase failures easier to attribute.

   **RESOLVED:** Adopted (b). Plans 01/02 create new per-schema test files under `tests/contracts/` (`test_video_analysis_schema.py`, `test_pipeline_synthesis_schema.py`); fixtures are inline Python dicts inside the test modules (no `tests/fixtures/` directory is created — see Finding 5).

2. **`version` const value.** Should `video_analysis.schema.json`'s `version` field be `"1.0"` (first canonical version of THIS schema file) or `"2.0"` (aligning with the milestone name)? The v1.0 brief file uses `"1.0"` for version. The new schema is logically `1.0` of its own contract but is introduced in the v2.0 milestone.

   **Recommendation:** use `"2.0"` for the canonical schema and `"1.0"` for `pipeline_synthesis.schema.json` (the synthesis artifact has no prior form).

   **RESOLVED:** Adopted split. Plan 01 pins `version: { const: "2.0" }` on `video_analysis.schema.json`; Plan 02 pins `version: { const: "1.0" }` on `pipeline_synthesis.schema.json`.

3. **Should Phase 1 extend `STAGES` / `ALL_KNOWN_STAGES`?**

   **Recommendation:** NO. Per Finding 8, neither `video_analysis` nor `pipeline_synthesis` is a pipeline-stage name in the v1.0 sense (they are capability / synthesis-run names). Adding them to `STAGES` would falsely suggest they're part of the canonical research→publish pipeline. The checkpoint system can reference them through `CANONICAL_STAGE_ARTIFACTS` only; when Phase 6 introduces a `reference-synthesis.md` meta-skill, that skill can declare its own stage sequence via a pipeline manifest.

   **RESOLVED:** Adopted NO. Plan 04 Task 1 preserves `STAGES` / `ALL_KNOWN_STAGES` unchanged and adds a regression test `test_stages_list_unchanged` to assert that the only edits are to `CANONICAL_STAGE_ARTIFACTS` (in `lib/checkpoint.py`) and `ARTIFACT_NAMES` (in `schemas/artifacts/__init__.py`). Phase 6 owns pipeline-manifest integration.

## Sources

### Primary (HIGH confidence)
- `/workspace/lib/checkpoint.py` — full read, canonical source for `CANONICAL_STAGE_ARTIFACTS` shape
- `/workspace/schemas/artifacts/__init__.py` — full read, canonical source for `ARTIFACT_NAMES` + `validate_artifact`
- `/workspace/schemas/artifacts/video_analysis_brief.schema.json` — full read, template for v2.0 schema authoring style
- `/workspace/schemas/pipelines/pipeline_manifest.schema.json` — full read, reference for Draft 2020-12 usage with `additionalProperties: false` and `oneOf`
- `/workspace/tests/contracts/test_phase0_contracts.py` — full read, reference for test class structure + `sample_artifact` helper pattern
- `/workspace/tests/contracts/test_phase1_contracts.py` — full read, reference for class-based tool contract tests
- `/workspace/requirements.txt` — full read, dependency footprint
- `/workspace/.planning/research/FEATURES.md` — full read, 4-dimension field inventory
- `/workspace/.planning/REQUIREMENTS.md` — full read, SYNTH-09 field list verbatim

### Secondary (MEDIUM confidence)
- Grep survey `video_analysis|pipeline_synthesis` across `schemas`, `lib`, `pipeline_defs`, `tools` — confirms no name collisions
- Grep survey `additionalProperties|uniqueItems|$ref` across `schemas/` — confirms adapter strip targets exist in manifests but not in artifact schemas (so adapter handling is defensive)
- `jsonschema==4.26.0` confirmed via `python3 -c "import jsonschema; print(jsonschema.__version__)"` in the devcontainer

### Tertiary (LOW confidence)
- None — every claim in this research is grounded in an existing file in the repo.

## Metadata

**Confidence breakdown:**
- Schema shape + authoring style: HIGH — existing schemas define the convention completely
- `CANONICAL_STAGE_ARTIFACTS` edit strategy: HIGH — source code read directly
- Adapter implementation: HIGH — no `$ref` in existing schemas means the defensive logic is simple; dependency footprint verified
- Test patterns: HIGH — Phase 0 tests establish the full template
- Field inventory for `video_analysis`: HIGH — FEATURES.md is explicit and the user locked it as source of truth
- `pipeline_synthesis` shape: MEDIUM — SYNTH-09 names the fields but their types and enum vocabularies are inferred from context; the planner may refine
- Phase sequencing / isolation from Phase 2+: HIGH — no CONTEXT.md ambiguity remains

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (30 days — stable codebase, no external-dependency drift for this phase)

## RESEARCH COMPLETE
