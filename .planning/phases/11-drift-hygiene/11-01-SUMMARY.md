---
phase: 11-drift-hygiene
plan: 01
subsystem: pipeline-manifests
tags: [drift, regression, semantic-validation, cinematic]
requirements: [DRIFT-01]
dependency_graph:
  requires:
    - lib.pipeline_synthesizer.validate_synthesized_pipeline (v2.0 Phase 5)
    - lib.pipeline_loader.load_pipeline
    - tools.tool_registry.registry.ensure_discovered
  provides:
    - clean cinematic.yaml (zero semantic-validator issues)
    - two regression tests blocking re-introduction of unregistered tools
  affects:
    - pipeline_defs/cinematic.yaml (research stage)
    - tests/unit/test_semantic_validation.py
tech_stack:
  added: []
  patterns:
    - narrow-atomic-commit-per-task
    - tdd-red-verifiable-from-git-history
key_files:
  created: []
  modified:
    - pipeline_defs/cinematic.yaml
    - tests/unit/test_semantic_validation.py
decisions:
  - "DRIFT-01: removed web_search reference instead of registering a stub — web_search is an agent intrinsic, not a BaseTool"
metrics:
  duration_minutes: 4
  tasks_completed: 2
  commits: 2
  tests_added: 2
  tests_total_after: 689
  completed_date: "2026-04-18"
---

# Phase 11 Plan 01: Close DRIFT-01 (cinematic.yaml web_search reference) Summary

**One-liner:** Removed unregistered `web_search` from `pipeline_defs/cinematic.yaml` research stage and locked the fix with two regression tests (manifest-specific + pipeline-wide sweep).

## Scope

Close DRIFT-01: the v2.0 semantic validator (`validate_synthesized_pipeline`) flagged `cinematic.yaml`'s research stage on every synthesizer run because `tools_available` listed `web_search`, which is an agent intrinsic (native Web tool) not a `BaseTool` in `tools.tool_registry`. Per `11-CONTEXT.md` D-01 the decision was to remove the reference, not register a stub.

## Tasks Completed

### Task 1: Remove `web_search` from `cinematic.yaml` research stage

- Replaced the 2-line block `tools_available:\n  - web_search` with the 1-line `tools_available: []`, matching the convention already used by the `proposal`, `edit`, and `publish` stages.
- Net diff: `-2 / +1` line in `pipeline_defs/cinematic.yaml`.
- No other stages or fields touched.
- Schema validation against `schemas/pipelines/pipeline_manifest.schema.json` passes.
- Research-director skill's "At least 8 web searches executed" success criterion preserved — it describes agent-level behavior, not a BaseTool contract.
- Commit: `9b12fca` — `fix(11-01): drop web_search from cinematic.yaml research stage (DRIFT-01)`

### Task 2: Add DRIFT-01 regression tests

Added two test functions to `tests/unit/test_semantic_validation.py`:

1. **`test_cinematic_manifest_has_no_unregistered_tools`** — loads the real `pipeline_defs/cinematic.yaml` via `load_pipeline("cinematic")` and asserts `validate_synthesized_pipeline(manifest) == []`. Fails immediately if `web_search` (or any other unregistered tool) is re-added to any stage.
2. **`test_no_pipeline_references_web_search_tool`** — glob-sweeps `pipeline_defs/*.yaml` and asserts no stage's `tools_available` list contains `web_search`. Catches re-introduction AND prevents copy-paste regression in any future pipeline manifest.

Both tests run in <3s, no network, no API keys. The pre-existing `valid_manifest` fixture (which uses `animated-explainer.yaml` with its Phase-5-rationale docstring) was deliberately left untouched — harmless archaeology per plan.

- TDD RED phase verifiable from git history: `git show HEAD~1:pipeline_defs/cinematic.yaml | grep web_search` → line 71 has `- web_search`. The plan explicitly accepted this alternative to the literal revert/restore micro-cycle since Task 1 is already committed.
- Commit: `c62bc2d` — `test(11-01): add DRIFT-01 regression tests for cinematic.yaml + pipeline-wide web_search sweep`

## Before / After: semantic validator output on cinematic

**Before fix (commit `fd32068`):**
```
validate_synthesized_pipeline(load_pipeline('cinematic')) ->
  ["stage 'research': tool 'web_search' not in registry (known 79 tools after ensure_discovered)"]
```

**After fix (commit `9b12fca`):**
```
validate_synthesized_pipeline(load_pipeline('cinematic')) -> []
```

## Test Suite Impact

| Metric | Baseline | After Plan 11-01 |
|--------|----------|-------------------|
| Passing | 687 | **689** (+2) |
| Failing | 3 (pre-existing `fc-list`) | 3 (unchanged) |
| Skipped | 13 | 13 |
| Duration | ~25s | ~32s |

The 3 pre-existing `fc-list` failures are a devcontainer/fontconfig issue in `tests/contracts/test_phase2_contracts.py::TestCodeSnippetUnit` — unrelated to v2.1 scope (STATE.md explicitly notes this).

## Files Changed

| File | Delta | Purpose |
|------|-------|---------|
| `pipeline_defs/cinematic.yaml` | -2 / +1 (net -1 line) | Drop `web_search` from research stage `tools_available` |
| `tests/unit/test_semantic_validation.py` | +56 lines | Two regression tests |

## Commits

| SHA | Type | Message |
|-----|------|---------|
| `9b12fca` | fix | `fix(11-01): drop web_search from cinematic.yaml research stage (DRIFT-01)` |
| `c62bc2d` | test | `test(11-01): add DRIFT-01 regression tests for cinematic.yaml + pipeline-wide web_search sweep` |

Two narrow atomic commits, matching the Phase 8-10 cadence and plan `<success_criteria>`.

## Deviations from Plan

None — plan executed exactly as written. Task 2's TDD RED phase was satisfied through git history inspection (`git show HEAD~1:pipeline_defs/cinematic.yaml | grep web_search`), an alternative the plan explicitly accepts.

## Threat Flags

None. The edit removes noise from the semantic validator (mitigates T-11-01-03 DoS-adjacent signal noise) without changing runtime behavior. `yaml.safe_load` remains the only deserialization path. No new network endpoints, auth paths, or schema boundaries introduced.

## DRIFT-01 Requirement Closure

- ✅ `grep -n "web_search" pipeline_defs/cinematic.yaml` → 0 matches (exit 1)
- ✅ `validate_synthesized_pipeline(load_pipeline('cinematic')) == []`
- ✅ Regression guarded by 2 unit tests (manifest-specific + pipeline-wide sweep)
- ✅ Zero behavior change at runtime — research-director skill still runs web searches via agent's intrinsic Web tool, outside the BaseTool contract
- ✅ Two narrow atomic commits land

## Self-Check: PASSED

Artifact verification:

- ✅ `pipeline_defs/cinematic.yaml` exists and no longer contains `web_search` (line 70 now `tools_available: []`)
- ✅ `tests/unit/test_semantic_validation.py` exists and contains both new `def test_*` lines (line 301 + line 324)
- ✅ Commit `9b12fca` found in `git log` (`fix(11-01): drop web_search...`)
- ✅ Commit `c62bc2d` found in `git log` (`test(11-01): add DRIFT-01 regression...`)
- ✅ `validate_synthesized_pipeline(load_pipeline('cinematic'))` returns `[]`
- ✅ Full suite `pytest tests/ --ignore=tests/qa -q` → 689 passed (baseline 687 + 2 new), 3 pre-existing fc-list failures unchanged, 13 skipped
