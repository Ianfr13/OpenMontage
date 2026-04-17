---
phase: 01-schema-adapter
fixed_at: 2026-04-17T00:00:00Z
review_path: .planning/phases/01-schema-adapter/01-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-04-17
**Source review:** `.planning/phases/01-schema-adapter/01-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (0 Critical, 5 Warning; 6 Info intentionally out of scope)
- Fixed: 5
- Skipped: 0

## Fixed Issues

### WR-01: `ALL_KNOWN_STAGES` misses the new Phase 1 stages

**Files modified:** `lib/checkpoint.py`
**Commit:** `73c69a6`
**Applied fix:** Reordered the module so `CANONICAL_STAGE_ARTIFACTS` is defined before `ALL_KNOWN_STAGES`, then derived `ALL_KNOWN_STAGES = frozenset(CANONICAL_STAGE_ARTIFACTS.keys())`. The two registries can no longer drift — any future canonical stage registration is automatically recognised by `validate_checkpoint` / `write_checkpoint` on the `pipeline_type is None` fallback path. Preserved `STAGES` list intact (per RESEARCH Finding 8) so the existing `test_stages_list_unchanged` regression guard continues to semantically assert what Phase 1 intended. All 62 Phase 1 contract + unit tests pass unchanged.

### WR-02: `to_api_schema` has no guard against circular `$ref` chains

**Files modified:** `lib/schema_adapter.py`
**Commit:** `47ca75f`
**Applied fix:** Added a `seen: frozenset[str]` parameter to `_walk` that tracks the set of `$ref` pointers currently being resolved along the recursion path. When a ref reappears, the adapter raises `SchemaAdapterError("Circular $ref detected: ...")` rather than recursing until `RecursionError` / OOM. Seen set is threaded through all recursive calls (dict siblings, list items). Existing tests still pass because current schemas have no cycles; the guard activates only on pathological input.

### WR-03: `_merge_decision_log` is not concurrency-safe and will `KeyError` on malformed input

**Files modified:** `lib/checkpoint.py`
**Commit:** `ce959c0`
**Applied fix:** Two hardenings.
1. Defensive id filter: `existing_ids` now skips entries that are not dicts or that lack `decision_id`, so a hand-edited / older-format log does not `KeyError` mid-write. New decisions without a `decision_id` are skipped rather than silently collapsing to one entry via `None` set-equality.
2. Atomic write: decisions are written to a sibling temp file (`tempfile.mkstemp` in the same directory, guaranteeing same filesystem) and swapped into place with `os.replace`, which is atomic on POSIX and Windows. Concurrent readers never observe a half-written JSON document, and a crash mid-write leaves the prior file intact. Temp file is cleaned up on failure.

Concurrency-from-multiple-writers (flock) is intentionally deferred — OpenMontage currently has one orchestrator per project, and `fcntl.flock` is POSIX-only; atomicity was the load-bearing concern.

### WR-04: `get_pipeline_stages` catches bare `Exception` and logs on every fallback call

**Files modified:** `lib/checkpoint.py`
**Commit:** `ce7c1a4`
**Applied fix:** Narrowed the `except (FileNotFoundError, Exception)` to `except FileNotFoundError`. Real programming errors in `load_pipeline` / `get_stage_order` (AttributeError, TypeError, etc.) now propagate instead of being silently swallowed as "no manifest." Downgraded the "called without `pipeline_type`" log from WARNING to DEBUG so the orchestrator's normal resume-without-pipeline-type path does not spam warnings. The expected "manifest missing" case logs at INFO level with the pipeline type it was looking for.

### WR-05: `write_checkpoint` masks missing `pipeline_type` with the literal string `"unknown"`

**Files modified:** `lib/checkpoint.py`, `tests/contracts/test_phase0_contracts.py`
**Commit:** `1578e93`
**Applied fix:** Chose the reviewer's preferred option — `pipeline_type` is now required. `write_checkpoint` raises `ValueError("write_checkpoint requires pipeline_type ...")` when `pipeline_type` is `None` or empty, rather than persisting a placeholder `"unknown"` string that would silently mismatch `ALL_KNOWN_STAGES` on read. The checkpoint schema already requires `pipeline_type` (line 7 of `checkpoint.schema.json`), so this brings the Python API in line with the JSON contract.

Updated 6 pre-existing `test_phase0_contracts.py::TestCheckpoint` callers to pass `pipeline_type="animated-explainer"` explicitly (they were relying on the old `"unknown"` masking). Added a new regression test `test_missing_pipeline_type_rejected` that asserts the `ValueError` is raised. All 70 Phase 0 + Phase 1 scoped tests pass.

## Verification Notes

- All 5 warning findings verified via the Phase 1 pytest slice: `tests/contracts/test_checkpoint_registration.py`, `tests/contracts/test_brief_schema_regression.py`, `tests/contracts/test_pipeline_synthesis_schema.py`, `tests/contracts/test_video_analysis_schema.py`, `tests/unit/test_schema_adapter.py` (62 passed) plus `tests/contracts/test_phase0_contracts.py::TestCheckpoint` (8 passed incl. the new WR-05 guard).
- Pre-existing `numpy` / overlay-fs failures documented in `deferred-items.md` were NOT touched — they reproduce without any Phase 1 code change and are orthogonal to the schema-adapter scope.
- `TMPDIR=/workspace/.pytest_tmp` was used to sidestep the documented devcontainer overlay-fs issue on `/tmp`.

## Info Findings Intentionally Deferred

IN-01 through IN-06 are out of scope for this fix pass (review scope was `critical_warning`). They remain documented in `01-REVIEW.md` and can be addressed in a follow-up iteration:

- IN-01: rename or sha-lock `test_schema_file_was_not_modified_in_this_phase`
- IN-02: add missing-version parametrization to pipeline_synthesis schema test
- IN-03: replace `ref.lstrip("#/")` with `ref[2:]`
- IN-04: document or tighten `$ref` + siblings behavior
- IN-05: switch tests from `json.load(open(...))` to context-manager form
- IN-06: walk structure instead of substring-matching JSON dump for `$ref`

---

_Fixed: 2026-04-17_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
