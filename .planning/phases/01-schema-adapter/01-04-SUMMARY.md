---
phase: 01-schema-adapter
plan: 04
subsystem: testing
tags: [jsonschema, pytest, checkpoint, artifact-registry, regression, backward-compat]

# Dependency graph
requires:
  - phase: 01-01
    provides: schemas/artifacts/video_analysis.schema.json (target of ARTIFACT_NAMES registration)
  - phase: 01-02
    provides: schemas/artifacts/pipeline_synthesis.schema.json (target of ARTIFACT_NAMES registration)
  - phase: 01-03
    provides: lib/schema_adapter.py (Phase 1 adapter shipped separately; unrelated to this plan's runtime path)
provides:
  - ARTIFACT_NAMES allowlist gates validate_artifact for video_analysis + pipeline_synthesis (silent-skip path closed)
  - CANONICAL_STAGE_ARTIFACTS entries for both new stages (stage → artifact-name bare string)
  - Phase 1 INT-04 verification test suite (11 tests, TestCheckpointRegistration)
  - v1.0 brief schema regression guard (6 tests, TestV1BriefRegression)
affects: [phase-02, phase-03, phase-05, phase-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pytest class-based contract tests mirroring tests/contracts/test_phase0_contracts.py conventions"
    - "Additive-only edits to ARTIFACT_NAMES + CANONICAL_STAGE_ARTIFACTS; STAGES/ALL_KNOWN_STAGES untouched per RESEARCH Finding 8"
    - "Regression pattern: assert canonical top-level shape + required-set + version const on stable v1.0 schema files"

key-files:
  created:
    - tests/contracts/test_checkpoint_registration.py
    - tests/contracts/test_brief_schema_regression.py
  modified:
    - schemas/artifacts/__init__.py
    - lib/checkpoint.py

key-decisions:
  - "STAGES / ALL_KNOWN_STAGES intentionally unchanged — pipeline-manifest integration is Phase 6 territory (RESEARCH Finding 8, Open Question 3 RESOLVED)"
  - "CANONICAL_STAGE_ARTIFACTS values are bare artifact names, not schema paths — matches existing convention and load_schema's SCHEMA_DIR/f'{name}.schema.json' resolver"
  - "v1.0 brief schema locked by an explicit regression test asserting required-set + version const (defense against accidental Phase 1 drift)"

patterns-established:
  - "Registration test pattern: assert both new names in registry + preservation of original set as a first-class test (not just a comment)"
  - "v1.0 regression gate: every phase adding to a schema family writes a file-content-shape test for any locked predecessor"

requirements-completed: [INT-04, ANLZ-02]

# Metrics
duration: 5min
completed: 2026-04-17
---

# Phase 1 Plan 4: Checkpoint Registration + v1.0 Regression Guard Summary

**ARTIFACT_NAMES + CANONICAL_STAGE_ARTIFACTS now allowlist `video_analysis` and `pipeline_synthesis`; 17 new tests lock the registration and guard v1.0 brief schema from drift.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-17T15:41:00Z (approx)
- **Completed:** 2026-04-17T15:46:00Z (approx)
- **Tasks:** 2
- **Files modified:** 4 (2 edited, 2 created)

## Accomplishments

- Registered `"video_analysis"` and `"pipeline_synthesis"` in `schemas/artifacts/__init__.py:ARTIFACT_NAMES` (now 17 entries; 15 originals preserved in order)
- Registered matching entries in `lib/checkpoint.py:CANONICAL_STAGE_ARTIFACTS` (now 11 entries; 9 originals preserved in order)
- Closed the `_validate_artifacts_for_stage` silent-skip path for both new artifacts (if artifact not in ARTIFACT_NAMES: continue — no longer hit for these two)
- Created `tests/contracts/test_checkpoint_registration.py` — 11 tests covering membership, mapping, validate_artifact round-trip accept/reject, preservation of all pre-existing entries, and an explicit `test_stages_list_unchanged` regression guard
- Created `tests/contracts/test_brief_schema_regression.py` — 6 tests locking the v1.0 `video_analysis_brief.schema.json` against accidental edits (required-set + version const pinned)
- Full Phase 1 test surface green: 62 tests across 5 files (video_analysis schema, pipeline_synthesis schema, schema_adapter, checkpoint_registration, brief_schema_regression)

## Task Commits

Each task was committed atomically:

1. **Task 1: Register video_analysis and pipeline_synthesis in ARTIFACT_NAMES and CANONICAL_STAGE_ARTIFACTS** — `dab9ad6` (feat)
2. **Task 2: Checkpoint registration test + v1.0 brief regression test** — `02e4aba` (test)

**Plan metadata:** pending (docs commit, final step)

_Note: Task 1 combined edit + verification in a single `feat` commit because the plan's verification step is a one-liner python assertion, not a separate test file (the test file is Task 2 and was committed as `test` after Task 1 was green). TDD order was followed: Task 1 changes verified before Task 2 tests were written._

## Files Created/Modified

- `schemas/artifacts/__init__.py` — **modified**: appended `"video_analysis"` + `"pipeline_synthesis"` to ARTIFACT_NAMES (lines 28-30). 2 lines added; no existing line touched.
- `lib/checkpoint.py` — **modified**: appended `"video_analysis": "video_analysis"` + `"pipeline_synthesis": "pipeline_synthesis"` to CANONICAL_STAGE_ARTIFACTS (lines 39-40 of the updated dict). 2 lines added; STAGES/ALL_KNOWN_STAGES untouched.
- `tests/contracts/test_checkpoint_registration.py` — **created**: 126 lines, 11 pytest methods in TestCheckpointRegistration; inline fixtures `_minimal_video_analysis()` + `_minimal_synthesis()` mirror Plan 01/02 fixtures.
- `tests/contracts/test_brief_schema_regression.py` — **created**: 87 lines, 6 pytest methods in TestV1BriefRegression; inline `_minimal_brief()` fixture derived from v1.0 required set (version, source, content_analysis, structure_analysis with 5 scenes + pacing_profile).

## Decisions Made

- **STAGES intentionally untouched.** Per RESEARCH Finding 8 + Open Question 3 RESOLVED: `video_analysis` and `pipeline_synthesis` are capability / synthesis-run names, not pipeline-stage names. Adding them to `STAGES` or `ALL_KNOWN_STAGES` would falsely suggest they're part of the canonical research→publish pipeline and would break `validate_checkpoint` for stages that don't live in any pipeline manifest yet. Phase 6 owns pipeline-manifest integration.
- **Test file split 2-for-2.** Registration tests and regression tests live in separate files (`test_checkpoint_registration.py`, `test_brief_schema_regression.py`) rather than a single `test_phase1_checkpoint_and_regression.py` — matches Plan 01/02 style (one test file per concern) and makes blast-radius debugging easier.
- **Canonical shape assertion for v1.0 brief.** Rather than a byte-exact schema fingerprint (fragile to JSON re-formatting), the regression test pins three invariants: `type == "object"`, `required == {version, source, content_analysis, structure_analysis}`, and `properties.version.const == "1.0"`. These are the load-bearing v1.0 contract pieces; any accidental edit to any of the three would immediately fail.

## Deviations from Plan

None — plan executed exactly as written.

The `.gitignore` was updated to add `.pytest_tmp/` (a workspace-local pytest TMPDIR used to work around the devcontainer overlay-fs disk-space issue documented in `deferred-items.md`). This is environmental plumbing, not a plan deviation — the committed `.gitignore` update lives in the Task 1 commit alongside the registration changes.

## Issues Encountered

- **Devcontainer overlay fs still at 100%** (inherited from Plan 01-03): `pytest` default `/tmp/pytest-of-*` directory cannot be created. Worked around by exporting `TMPDIR=/workspace/.pytest_tmp` for all pytest invocations. This is the same issue already tracked in `deferred-items.md`; not a scope item for this plan. Followed the `deferred-items.md` recommendation by scoping Phase 0 regression to `TestSchemas` + `TestCheckpoint` classes (the schema-relevant surface), all green.
- **Pre-existing `numpy` import failure** in `tests/contracts/test_phase0_contracts.py::TestToolRegistry::test_support_envelope` (inherited from Plan 01-01): out of scope; tracked in `deferred-items.md`. Phase 1's schema + checkpoint surface is fully green.

## User Setup Required

None — no external service configuration required.

## Verification Evidence

- **Registration round-trip (from Task 1 verify step):**
  ```
  ARTIFACT_NAMES[-2:] == ['video_analysis', 'pipeline_synthesis']   # OK
  CANONICAL_STAGE_ARTIFACTS['video_analysis']=='video_analysis'    # OK
  CANONICAL_STAGE_ARTIFACTS['pipeline_synthesis']=='pipeline_synthesis'  # OK
  len(ARTIFACT_NAMES) == 17                                        # OK
  len(CANONICAL_STAGE_ARTIFACTS) == 11                             # OK
  STAGES == 9 original elements unchanged                          # OK
  load_schema('video_analysis')['title'] == 'video_analysis'       # OK
  load_schema('pipeline_synthesis')['title'] == 'pipeline_synthesis'  # OK
  ```
- **Task 2 suite:** `pytest tests/contracts/test_checkpoint_registration.py tests/contracts/test_brief_schema_regression.py -x -q` → **17 passed in 0.20s**
- **Full Phase 1 group:** `pytest tests/contracts/test_video_analysis_schema.py tests/contracts/test_pipeline_synthesis_schema.py tests/unit/test_schema_adapter.py tests/contracts/test_checkpoint_registration.py tests/contracts/test_brief_schema_regression.py -x -q` → **62 passed in 1.69s**
- **Phase 0 scoped regression:** `pytest tests/contracts/test_phase0_contracts.py::TestSchemas tests/contracts/test_phase0_contracts.py::TestCheckpoint -q` → **11 passed in 3.18s**
- **v1.0 brief schema unmodified:** `git diff --name-only schemas/artifacts/video_analysis_brief.schema.json` → empty

## Phase 1 Completion Status

Phase 1 (schema-adapter) ships **all 4 plans** complete:

| Plan | Deliverable | Requirements |
|------|-------------|--------------|
| 01-01 | `schemas/artifacts/video_analysis.schema.json` (v2.0, 4 dimensions) | ANLZ-02 |
| 01-02 | `schemas/artifacts/pipeline_synthesis.schema.json` (v1.0, SYNTH-09 fields) | SYNTH-09 |
| 01-03 | `lib/schema_adapter.py` + 16 unit tests (hand-rolled `$ref` inliner, strips `additionalProperties:false` / `uniqueItems` / `$schema` / `$id`) | ANLZ-03 |
| 01-04 | Registration in ARTIFACT_NAMES + CANONICAL_STAGE_ARTIFACTS + 17 regression tests | INT-04, ANLZ-02 (registration half) |

**Phase 1 total test surface (all green):** 62 tests across 5 files (plus 11 Phase 0 schema-relevant regression tests).

## Next Phase Readiness

- **Phase 2 (video_analyzer_selector + first provider, likely Gemini):** All schema + registry surface ready. `validate_artifact("video_analysis", provider_output)` will now fail-fast on malformed provider responses — no silent skips. `lib/schema_adapter.to_api_schema()` is ready to convert canonical schemas into Gemini/OpenAI-compatible flat dicts.
- **Phase 6 (pipeline-manifest integration):** Open item — Phase 6 owns adding `video_analysis` / `pipeline_synthesis` stages to `STAGES` / `ALL_KNOWN_STAGES` *if* a reference-synthesis pipeline manifest declares them as stages (not confirmed yet; may stay at capability-only).
- **Known environment blockers (devcontainer):**
  - Overlay fs at 100% — recommended follow-up: prune `/home/node/.cache/ms-playwright` (unused for this milestone) or rebuild devcontainer with larger overlay. See `deferred-items.md`.
  - `numpy` missing — recommended follow-up: add to `requirements.txt` or guard `tools/video/green_screen_composite.py` import. See `deferred-items.md`.

## Self-Check: PASSED

All 5 declared files exist on disk:
- schemas/artifacts/__init__.py — FOUND
- lib/checkpoint.py — FOUND
- tests/contracts/test_checkpoint_registration.py — FOUND
- tests/contracts/test_brief_schema_regression.py — FOUND
- .planning/phases/01-schema-adapter/01-04-SUMMARY.md — FOUND

All 2 declared commit hashes resolve:
- dab9ad6 (Task 1: feat) — FOUND
- 02e4aba (Task 2: test) — FOUND

---
*Phase: 01-schema-adapter*
*Completed: 2026-04-17*
