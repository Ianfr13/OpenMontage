---
phase: 10-synthesizer-record-validity
verified: 2026-04-17T00:00:00Z
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
---

# Phase 10: Synthesizer Record Validity Verification Report

**Phase Goal:** Harden synthesizer acceptance/rejection so slug/path inputs are validated defensively and the emitted records no longer abuse `pipeline_synthesis_run` with synthetic sentinel values.
**Verified:** 2026-04-17T00:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `accept_synthesis(slug)` raises `InvalidPipelineSlug` (subclass of `VideoAnalysisError`) when slug fails regex `^[a-z0-9][a-z0-9\-_]{7,127}$` or resolves outside STAGING_DIR | VERIFIED | Runtime check: `accept_synthesis('../cinematic')` raised `InvalidPipelineSlug: Invalid slug '../cinematic' — must match '^[a-z0-9][a-z0-9\\-_]{7,127}$'` (lib/pipeline_synthesizer.py:103, 106-142, 673) |
| 2 | `reject_synthesis(slug)` applies identical validation with identical error type and message prefix | VERIFIED | `_validate_slug(slug)` invoked at line 743 (same helper, same regex, same exception) |
| 3 | Valid `_build_slug`-shaped slugs (`<base>-<8-hex>`) still pass the validator | VERIFIED | Test `test_accept_happy_path_canonical_slug_still_works` (line 394 of test_accept_reject.py) green; suite reports 687 passing |
| 4 | Path traversal attempts and special chars raise `InvalidPipelineSlug` before any filesystem call | VERIFIED | Parametrized `test_accept_rejects_malformed_slug` + `test_reject_rejects_malformed_slug` (lines 373, 384) over 11 payloads × 2 entry points — all pass; `test_accept_slug_validation_short_circuits_filesystem` (line 415) locks the no-fs-side-effect contract |
| 5 | `InvalidPipelineSlug` is catchable by `except VideoAnalysisError` | VERIFIED | `issubclass(InvalidPipelineSlug, VideoAnalysisError)` returned True at runtime; lib/analysis_errors.py:97 declares `class InvalidPipelineSlug(VideoAnalysisError)` |
| 6 | `accept_synthesis` returns a record validating against new `pipeline_acceptance` schema (no `base_pipeline=slug`, no `match_score=0.0`, no `source_analysis_checksum="post-accept"`) | VERIFIED | lib/pipeline_synthesizer.py:705-715 record shape + `validate_artifact("pipeline_acceptance", record)`; schema at schemas/artifacts/pipeline_acceptance.schema.json has no `base_pipeline` / `match_score` / `source_analysis_checksum` properties |
| 7 | `reject_synthesis` returns a record validating against new `pipeline_rejection` schema (no sentinel fields, no `validation_status="invalid"` hack) | VERIFIED | lib/pipeline_synthesizer.py:751-758 record shape + `validate_artifact("pipeline_rejection", record)`; schema at schemas/artifacts/pipeline_rejection.schema.json lacks `validation_status` (the Pitfall 2 hack) |
| 8 | Legacy `pipeline_synthesis` schema untouched | VERIFIED | schemas/artifacts/pipeline_synthesis.schema.json still referenced by `_load_synthesis_schema` and used by `synthesize_pipeline`; SUMMARY's `diff` against HEAD confirmed byte-identical |
| 9 | New schemas load via existing `load_schema` / `validate_artifact` helpers and are registered in `ARTIFACT_NAMES` | VERIFIED | schemas/artifacts/__init__.py:30-32 contains all three names; runtime `load_schema('pipeline_acceptance')` / `('pipeline_rejection')` returned valid dicts; test `validate_artifact(...)` calls succeeded |
| 10 | `accept_synthesis` tuple return shape `(Path, dict)` preserved | VERIFIED | lib/pipeline_synthesizer.py:715 `return dst, record`; signature still `-> tuple[Path, dict[str, Any]]` |
| 11 | Full suite stays at baseline (≥662 passing, 13 skipped, 3 pre-existing fc-list failures) | VERIFIED | `pytest tests/ --ignore=tests/qa -q` → **687 passed, 13 skipped, 3 failed (fc-list FileNotFoundError pre-existing)**; SYNTH-10 grep-anchor test (`test_no_auto_approval_path`) passed independently |

**Score:** 11/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `lib/analysis_errors.py` | `InvalidPipelineSlug(VideoAnalysisError)` class appended after `MergeConsensusError` | VERIFIED | Line 97: `class InvalidPipelineSlug(VideoAnalysisError):` with full docstring referencing Phase 10 CLEAN-08 / v2.0 Phase 5 REVIEW MR-01 |
| `lib/pipeline_synthesizer.py` | `_SLUG_RE` + `_validate_slug` helper + validator calls in both entry points | VERIFIED | Line 103 `_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{7,127}$")`; line 106 `def _validate_slug`; 2 call sites (673, 743); import at line 55 |
| `tests/unit/test_accept_reject.py` | 5 new test functions for malformed slug + traversal + inheritance + no-fs-side-effects + happy path | VERIFIED | `test_accept_rejects_malformed_slug` (373), `test_reject_rejects_malformed_slug` (384), `test_accept_happy_path_canonical_slug_still_works` (394), `test_invalid_pipeline_slug_is_video_analysis_error` (406), `test_accept_slug_validation_short_circuits_filesystem` (415) |
| `schemas/artifacts/pipeline_acceptance.schema.json` | draft-2020-12 schema with `promoted_slug`/`promoted_path`/`validation_status`/`created_at`; no sentinel fields | VERIFIED | File exists, 42 lines, `$id: openmontage/artifacts/pipeline_acceptance`, required = [version, promoted_slug, promoted_path, validation_status, created_at], no `base_pipeline`/`match_score`/`source_analysis_checksum` properties |
| `schemas/artifacts/pipeline_rejection.schema.json` | draft-2020-12 schema with `rejected_slug`/`staging_path`/`created_at`; no `validation_status` | VERIFIED | File exists, 35 lines, `$id: openmontage/artifacts/pipeline_rejection`, required = [version, rejected_slug, staging_path, created_at], optional `reason`, no `validation_status`/`base_pipeline` |
| `schemas/artifacts/__init__.py` | `pipeline_acceptance` + `pipeline_rejection` added to `ARTIFACT_NAMES` | VERIFIED | Lines 30-32 list pipeline_synthesis, pipeline_acceptance, pipeline_rejection consecutively |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `lib/pipeline_synthesizer.py::accept_synthesis` | `lib/analysis_errors.py::InvalidPipelineSlug` | Import + `_validate_slug(slug)` at line 673 | WIRED | Import at line 55; `_validate_slug` raises `InvalidPipelineSlug` at lines 131, 138 |
| `lib/pipeline_synthesizer.py::reject_synthesis` | `lib/pipeline_synthesizer.py::_validate_slug` | Direct call at line 743 | WIRED | First post-docstring statement; short-circuits before any `src.unlink()` |
| `lib/pipeline_synthesizer.py::accept_synthesis` | `schemas/artifacts/pipeline_acceptance.schema.json` | `validate_artifact("pipeline_acceptance", record)` at line 714 | WIRED | Import at top of file; 1 grep match confirmed |
| `lib/pipeline_synthesizer.py::reject_synthesis` | `schemas/artifacts/pipeline_rejection.schema.json` | `validate_artifact("pipeline_rejection", record)` at line 757 | WIRED | 1 grep match confirmed |
| `tests/contracts/test_phase7_e2e_smoke.py` | `pipeline_acceptance.schema.json` + `pipeline_rejection.schema.json` | `load_schema("pipeline_acceptance")` line 127; `load_schema("pipeline_rejection")` line 150 | WIRED | Both assertions in place; Pitfall 2 `validation_status=="invalid"` assertion removed |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `accept_synthesis` record | `record` dict | Built from validated `slug` + `_relative_staging_path(dst)` + real validation run of `load_pipeline(slug)` + `validate_synthesized_pipeline` + `datetime.now(...)` | Yes — every field derives from live state or validated input | FLOWING |
| `reject_synthesis` record | `record` dict | Built from validated `slug` + `_relative_staging_path(src)` captured BEFORE `src.unlink()` + `datetime.now(...)` | Yes — no sentinel defaults | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `InvalidPipelineSlug` raised on path-traversal slug | `python -c "from lib.pipeline_synthesizer import accept_synthesis; accept_synthesis('../cinematic')"` | `InvalidPipelineSlug: Invalid slug '../cinematic' — must match '^[a-z0-9][a-z0-9\-_]{7,127}$'` | PASS |
| `InvalidPipelineSlug` subclasses `VideoAnalysisError` | `python -c "from lib.analysis_errors import InvalidPipelineSlug, VideoAnalysisError; assert issubclass(InvalidPipelineSlug, VideoAnalysisError)"` | exit 0 | PASS |
| Both new schemas load + validate minimal records | `python -c "from schemas.artifacts import load_schema, validate_artifact; ..."` | `schemas ok` | PASS |
| ROADMAP-contract sentinel grep | `grep -n 'match_score=0\.0\|base_pipeline=slug\|"post-accept"' lib/pipeline_synthesizer.py` | 0 matches | PASS |
| SYNTH-10 grep-anchor test | `pytest tests/contracts/test_phase5_synthesis.py::test_no_auto_approval_path -q` | 1 passed | PASS |
| Full regression | `pytest tests/ --ignore=tests/qa -q` | 687 passed, 13 skipped, 3 pre-existing fc-list failures | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CLEAN-08 | 10-01-PLAN.md | Validate slug regex + resolve under staging root (defense-in-depth path-traversal guard) | SATISFIED | `InvalidPipelineSlug` sentinel + `_SLUG_RE` + `_validate_slug` helper wired into both `accept_synthesis` (line 673) and `reject_synthesis` (line 743); parametrized tests cover traversal payloads (`../`, absolute paths, empty, invalid chars) |
| CLEAN-09 | 10-02-PLAN.md | Stop emitting synthetic run records with `base_pipeline=slug`, `match_score=0.0`, `source_analysis_checksum="post-accept"` | SATISFIED | Split into `pipeline_acceptance` + `pipeline_rejection` schemas; ROADMAP grep anchor (`match_score=0.0\|base_pipeline=slug\|"post-accept"`) returns 0 matches in `lib/pipeline_synthesizer.py`; both handlers now emit via `validate_artifact(...)` against their dedicated schemas |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `lib/pipeline_synthesizer.py` | 396 | `return {"base_pipeline": "", "match_score": 0.0, "alternatives": []}` | Info | NOT a CLEAN-09 violation — this is the documented legitimate return of `_match_pipeline` when no candidate pipelines exist; it's inside the matcher (not accept/reject record blocks). The ROADMAP contract grep (`match_score=0\.0`, with `=` not `.*`) does not match this line. Unchanged by Phase 10; out of scope. |
| `lib/pipeline_synthesizer.py` | 647 | `post-accept` appears in docstring | Info | NOT a sentinel write — this is a reference to "post-accept events" inside accept_synthesis's docstring explaining the schema split. Documentation, not code. |

No blocker or warning anti-patterns found. All grep-based anti-pattern hits are legitimate (documentation comments or unrelated matcher return defaults).

### Human Verification Required

None. Every truth and artifact was verified programmatically via grep, file inspection, Python runtime smoke tests, and the full pytest suite. Phase 10 is a pure library/schema hardening phase with no UI, no external service integration, no real-time behavior, and no user-flow concerns.

### Gaps Summary

No gaps. All 11 must-have truths are verified, both requirements (CLEAN-08, CLEAN-09) are satisfied, every artifact exists and is substantive, every key link is wired, data flows through both new record shapes correctly, and the full regression suite preserves the baseline (687 passed, 13 skipped, 3 pre-existing fc-list failures unchanged — matching the SUMMARYs and ROADMAP success criterion #5).

The residual grep matches inspected in Step 7 are:
- A legitimate `_match_pipeline` default return at line 396 (not scoped to CLEAN-09; the ROADMAP's contract grep uses the specific assignment pattern `match_score=0.0` which does not match `"match_score": 0.0` dict-literal form anyway)
- A docstring reference to "post-accept events" at line 647 (documentation, not a sentinel write)

Neither constitutes a CLEAN-09 violation.

---

*Verified: 2026-04-17T00:00:00Z*
*Verifier: Claude (gsd-verifier)*
