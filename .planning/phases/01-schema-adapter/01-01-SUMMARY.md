---
phase: 01-schema-adapter
plan: 01
subsystem: schemas
tags: [jsonschema, draft-2020-12, video-analysis, pytest, contract-tests]

requires:
  - phase: 00-baseline
    provides: schemas/artifacts/__init__.py (load_schema + ARTIFACT_NAMES pattern), tests/contracts/test_phase0_contracts.py (pytest class + inline-fixture conventions), jsonschema>=4.20 already installed
provides:
  - Canonical v2.0 video_analysis contract (schemas/artifacts/video_analysis.schema.json)
  - Contract tests (tests/contracts/test_video_analysis_schema.py — 12 tests, API-key-free)
  - Source-of-truth for the 4 dimensions (editing_pacing, audio, visual_style, narrative) consumed by Phase 2+
affects: [01-02-pipeline-synthesis-schema, 01-03-schema-adapter, 01-04-checkpoint-registration, 02-gemini-provider, 03-openrouter-provider, 04-analysis-merger, 05-pipeline-synthesizer]

tech-stack:
  added: []
  patterns:
    - "Draft 2020-12 inline authoring (no $ref, no additionalProperties:false at root) — matches existing schemas/artifacts/*.json"
    - "Confidence map pattern: dimension-level confidence: { additionalProperties: { enum: [low, medium, high] } } (single map per dimension, NOT per-field siblings)"
    - "Inline pytest dict fixtures via minimal_video_analysis() helper — no tests/fixtures/ dir (per Research Finding 5)"

key-files:
  created:
    - schemas/artifacts/video_analysis.schema.json
    - tests/contracts/test_video_analysis_schema.py
    - .planning/phases/01-schema-adapter/deferred-items.md
  modified: []

key-decisions:
  - "Chose dimension-level confidence map (not sibling per-field) — resolves Research Assumption A1 toward the compact form"
  - "Used version: { const: \"2.0\" } (not 1.0) — aligns the new schema with milestone branding; v1.0 brief still uses const: \"1.0\""
  - "Declared $id openmontage/artifacts/video_analysis — aligns with brief.schema.json / render_report.schema.json convention (not the $id-less v1.0 outlier)"
  - "12 tests instead of the plan's 8 — added test_minimal_fixture_not_mutated_by_validate as a correctness sanity check (still scoped to plan intent)"

patterns-established:
  - "Canonical artifact schemas authored inline, no $ref — the Phase 1-03 adapter is defensive for non-existent $refs"
  - "Contract tests parametrize the set of required top-level dimensions for one rejection test per dimension"

requirements-completed: [ANLZ-02, ANLZ-03]

duration: 3min
completed: 2026-04-17
---

# Phase 01 Plan 01: video_analysis Canonical Schema Summary

**Canonical v2.0 video_analysis JSON Schema (Draft 2020-12) with 4 required dimension keys (editing_pacing, audio, visual_style, narrative) plus 12 passing contract tests — the typed contract every Phase 2+ provider validates against, shipped before any provider code.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-04-17T15:23:49Z
- **Completed:** 2026-04-17T15:26:46Z
- **Tasks:** 2/2
- **Files created:** 3 (schema, tests, deferred-items)
- **Files modified:** 0

## Accomplishments

- `schemas/artifacts/video_analysis.schema.json` authored: Draft 2020-12, `$id: openmontage/artifacts/video_analysis`, 6 required top-level keys (version, source + 4 dimensions), ~50 typed fields across the 4 dimensions per FEATURES.md inventory, optional `chunking_metadata` + `shot_boundary_source` top-level fields.
- All enum vocabularies from FEATURES.md / 01-PLAN.md locked in as JSON Schema `enum` arrays: `pacing_style`, `narration_style`, `voice_music_mix`, `production_quality`, `aspect_ratio`, `hook_type`, `narrative_arc`, `target_platform`, `content_tone`, `voice_tone`, `music_intensity`, `color_temperature`, `color_grading_style`, `background_treatment`, `typography_weight`, `text_card_usage`, `motion_style`, `overlay_style`, `cta_type`, `information_density`, `transition_types`, `energy_level`, `shot_boundary_source`, `chunking_metadata.provider`.
- `tests/contracts/test_video_analysis_schema.py` authored: 12 tests, all passing, all API-key-free and network-free.
- v1.0 `schemas/artifacts/video_analysis_brief.schema.json` untouched (zero diff — coexists per locked REQ ANLZ-02 decision).

## Task Commits

Each task was committed atomically on main:

1. **Task 1: Author schemas/artifacts/video_analysis.schema.json** — `9deb50b` (feat)
2. **Task 2: Contract tests for video_analysis schema** — `afbaef1` (test)

**Plan metadata:** pending final commit (docs: complete plan)

## Files Created/Modified

- `schemas/artifacts/video_analysis.schema.json` — Canonical v2.0 video_analysis contract, 339 lines, Draft 2020-12 inline authoring.
- `tests/contracts/test_video_analysis_schema.py` — 12 contract tests covering loadability, `load_schema` helper, fixture validation, 4 parametrized missing-dimension rejections, 2 invalid-enum rejections, chunking_metadata optionality + merger-shape acceptance, and a no-mutation sanity check.
- `.planning/phases/01-schema-adapter/deferred-items.md` — Logs a pre-existing Phase 0 `numpy` ModuleNotFoundError (in `test_support_envelope`) as out of scope for this plan.

## Decisions Made

- **Confidence shape = dimension-level map.** Resolved Research Assumption A1 by adopting a single `confidence: { additionalProperties: { type: "string", enum: ["low","medium","high"] } }` object per dimension rather than sibling `<field>_confidence` siblings per uncertain field. Rationale: schema stays compact and discoverable; providers fill a single map per dimension; future fields automatically inherit the confidence-reporting shape.
- **`version` const = `"2.0"`.** Aligns the new schema with milestone branding (matches plan frontmatter). v1.0 brief keeps its `version: "1.0"`.
- **Added 12th test (`test_minimal_fixture_not_mutated_by_validate`).** Plan required ≥8; added one extra correctness-sanity test that `jsonschema.validate` does not mutate the instance. Zero scope creep; high-leverage for debugging regressions.
- **Did NOT add `version` or `source` required-key rejection tests.** Plan explicitly scoped rejection tests to the 4 dimensions + 2 enum cases; adding more would have been scope creep.

## Deviations from Plan

None structural. The only scope-adjacent addition was the single extra sanity test (`test_minimal_fixture_not_mutated_by_validate`), which reinforces — not alters — the plan's stated behavior. No Rule 1/2/3 auto-fixes applied; no Rule 4 architectural escalations.

## Issues Encountered

### Pre-existing (logged, out of scope)

`pytest tests/contracts/test_phase0_contracts.py -x -q` surfaces a single failure: `TestToolRegistry::test_support_envelope` fails with `ModuleNotFoundError: No module named 'numpy'` (from `tools/video/green_screen_composite.py:19`). Confirmed pre-existing by stashing all 01-01 changes and re-running — same failure. Logged in `.planning/phases/01-schema-adapter/deferred-items.md`. The scope-relevant Phase 0 regression (schemas + checkpoints) passes 11/11.

## Verification Evidence

| Check | Result |
| - | - |
| `python3 -c "import json; json.load(open('schemas/artifacts/video_analysis.schema.json'))"` | exit 0 |
| `grep -c '"\\$ref"' schemas/artifacts/video_analysis.schema.json` | 0 |
| `grep '"title": "video_analysis"' schemas/artifacts/video_analysis.schema.json` | match |
| `git status --porcelain schemas/artifacts/video_analysis_brief.schema.json` | empty |
| `pytest tests/contracts/test_video_analysis_schema.py -x -q` | 12 passed |
| `pytest tests/contracts/test_phase0_contracts.py::TestSchemas tests/contracts/test_phase0_contracts.py::TestCheckpoint -q` | 11 passed |
| `test ! -d tests/fixtures` | OK |
| `grep -c 'GEMINI_API_KEY\|OPENROUTER_API_KEY' tests/contracts/test_video_analysis_schema.py` | 0 |

## User Setup Required

None — no external service configuration. Pure schema + test work, runs entirely in the devcontainer.

## Next Phase Readiness

**Ready to execute 01-02 (pipeline_synthesis schema) and 01-03 (schema adapter).**

- 01-02 can proceed independently (no code dep on the video_analysis schema — it authors `pipeline_synthesis.schema.json`).
- 01-03 (adapter) can proceed; it uses inline synthetic schemas in its tests. The canonical `video_analysis.schema.json` is available for the adapter's adapter-round-trip regression test if the planner wants one there.
- 01-04 (checkpoint registration) has the file it needs on disk — `load_schema("video_analysis")` already works (confirmed by `test_load_schema_helper_works` which passes). It still needs the Plan 04 edit to `ARTIFACT_NAMES` for `validate_artifact("video_analysis", ...)` to flow through `_validate_artifacts_for_stage` — that's a scope item for 01-04, not 01-01.

No blockers. v1.0 backward compatibility holds.

## Self-Check: PASSED

- `schemas/artifacts/video_analysis.schema.json` — FOUND
- `tests/contracts/test_video_analysis_schema.py` — FOUND
- `.planning/phases/01-schema-adapter/deferred-items.md` — FOUND
- Commit `9deb50b` (Task 1 feat) — FOUND in `git log`
- Commit `afbaef1` (Task 2 test) — FOUND in `git log`
- v1.0 brief untouched — confirmed via `git status --porcelain`

---
*Phase: 01-schema-adapter*
*Completed: 2026-04-17*
