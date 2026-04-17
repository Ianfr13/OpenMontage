---
phase: 05-synthesizer
plan: 01
subsystem: synthesis

tags: [ruamel-yaml, rule-matching, sha256, staging, yaml-round-trip]

requires:
  - phase: 01-contracts
    provides: video_analysis schema + pipeline_manifest schema + pipeline_synthesis schema
  - phase: 00-foundation
    provides: lib/pipeline_loader, 12 base pipeline_defs/*.yaml

provides:
  - lib/pipeline_synthesizer.py with _canonical_sha256, _build_slug, _is_adjacent_pacing, match_base_pipeline, _write_staging, synthesize_pipeline
  - expected_analysis block on all 12 base pipelines (SYNTH-02 enabler)
  - pipeline_manifest schema extension (optional expected_analysis + production_modes + documentary category)
  - pipeline_defs/_staging/ staging dir (gitignored)
  - ruamel.yaml>=0.18,<0.20 pinned in requirements.txt

affects: [05-02 validation+record writer, 05-03 accept/reject+LLM fill, 06 meta-skill]

tech-stack:
  added: [ruamel.yaml 0.19.1]
  patterns: [module-level lib (no class), rule-based signal scorer, ruamel YAML(typ="rt") + file-handle header, -vN collision capped at 99]

key-files:
  created:
    - lib/pipeline_synthesizer.py
    - tests/unit/test_pipeline_synthesizer.py
  modified:
    - requirements.txt
    - .gitignore
    - schemas/pipelines/pipeline_manifest.schema.json
    - pipeline_defs/animated-explainer.yaml
    - pipeline_defs/animation.yaml
    - pipeline_defs/avatar-spokesperson.yaml
    - pipeline_defs/cinematic.yaml
    - pipeline_defs/clip-factory.yaml
    - pipeline_defs/documentary-montage.yaml
    - pipeline_defs/framework-smoke.yaml
    - pipeline_defs/hybrid.yaml
    - pipeline_defs/localization-dub.yaml
    - pipeline_defs/podcast-repurpose.yaml
    - pipeline_defs/screen-demo.yaml
    - pipeline_defs/talking-head.yaml

key-decisions:
  - "Use actual stage counts (grep -cE '^  - name:') instead of the plan's estimate table — determinism trumps table"
  - "close_up_heavy maps to shot_type_distribution.talking_head > 0.5 (research Finding #4; canonical schema has no close_up key)"
  - "Strip '# at:' timestamp line before byte-comparing staging files so idempotent re-runs are a true noop"
  - "-vN collision suffix capped at 99 (T-05-04 DoS mitigation)"
  - "Mode parameter accepted and routed in 05-01; template and replica emit same body since LLM fill lands in Plan 05-03"

patterns-established:
  - "Pure-lib synthesizer: module-level functions only, no class (SYNTH-01)"
  - "Canonical checksum: SHA-256 over json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False)"
  - "Provenance header as the first 5 lines of every _staging/<slug>.yaml file, written via direct file_handle.write() (not via ruamel comment API)"

requirements-completed: [SYNTH-01, SYNTH-02, SYNTH-04, SYNTH-05, SYNTH-06]

duration: 7min
completed: 2026-04-17
---

# Phase 5 Plan 01: Synthesizer Core Summary

**Deterministic rule-based pipeline synthesizer with ruamel round-trip YAML staging — matcher, slug, writer, 12 annotated base pipelines, 12 unit tests all green.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-04-17T20:56:40Z
- **Completed:** 2026-04-17T21:03:35Z
- **Tasks:** 3 (Task 1 Wave 0 deps/schema/gitignore; Task 2 TDD synthesizer core; Task 3 annotate 12 pipelines)
- **Files modified:** 15 (2 created, 13 modified)

## Accomplishments

- `lib/pipeline_synthesizer.py` — module-level matcher + canonical checksum + slug builder + staging writer; 100% rule-based, zero LLM, zero classes.
- 12 unit tests in `tests/unit/test_pipeline_synthesizer.py`, all green, covering SYNTH-01/02/04/05/06 behaviors: module shape, SHA-256 determinism, matcher signal math (exact pacing, close_up_heavy, static_heavy, ties), slug idempotency, staging-only writes, provenance header, collision noop vs `-v2`, mode validation.
- All 12 base pipelines annotated with `expected_analysis` and still load via `lib.pipeline_loader.load_pipeline`.
- Schema extended with optional `expected_analysis` root block (non-breaking), plus defensive additions (`production_modes` array, `documentary` category) that unblocked two pre-existing broken pipelines.
- `ruamel.yaml 0.19.1` pinned in `requirements.txt`; `pipeline_defs/_staging/` gitignored.

## Task Commits

1. **Task 1: Wave 0 deps + schema + gitignore** — `e25d67a` (chore)
2. **Task 2 RED: failing unit tests** — `d5542ad` (test)
3. **Task 2 GREEN: synthesizer implementation + schema unblock fixes** — `1c8b79e` (feat)
4. **Task 3: annotate 12 pipelines with expected_analysis** — `0e2c27e` (feat)

_Note: Task 2 had TDD red/green commits; no refactor phase needed._

## Files Created/Modified

**Created:**
- `lib/pipeline_synthesizer.py` — matcher + checksum + slug + staging writer
- `tests/unit/test_pipeline_synthesizer.py` — 12 behavior tests

**Modified:**
- `requirements.txt` — pin `ruamel.yaml>=0.18,<0.20`
- `.gitignore` — ignore `pipeline_defs/_staging/`
- `schemas/pipelines/pipeline_manifest.schema.json` — optional `expected_analysis` block, optional `production_modes` array, `documentary` added to category enum
- `pipeline_defs/*.yaml` (12 files) — `expected_analysis` annotations with actual stage counts

## Decisions Made

- Actual stage counts used (not the plan's estimate table) for every pipeline annotation — determinism trumps the table.
- Collision suffix capped at 99 per threat model T-05-04.
- Timestamp line stripped when comparing bodies for idempotency — keeps pure re-runs as byte-equal no-ops even across time.
- `synthesized = base_manifest` verbatim in this plan — template/replica divergence is Plan 05-03's responsibility once LLM fill lands.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pre-existing pipeline validation failures unblocked via schema extension**
- **Found during:** Task 3 (after-annotation load check across all 12 pipelines)
- **Issue:** Two pipelines failed schema validation BEFORE my annotations were added:
  - `pipeline_defs/screen-demo.yaml` has a top-level `production_modes` block that was not in the schema (`additionalProperties: false` at root rejected it).
  - `pipeline_defs/documentary-montage.yaml` uses `category: documentary` which was absent from the category enum.
- **Why blocking:** Plan 05-01's verification step 4-5 requires ALL 12 pipelines to load via `load_pipeline()`. Without this fix, the task could not complete.
- **Fix:** Schema extended with an optional `production_modes` array (items `{type: object}`) and `documentary` added to the `category` enum. Both changes are additive, non-breaking; the two pipelines now pass validation without edits to the pipeline files themselves.
- **Files modified:** `schemas/pipelines/pipeline_manifest.schema.json`
- **Verification:** `python3 -c "from lib.pipeline_loader import list_pipelines, load_pipeline; [load_pipeline(n) for n in list_pipelines()]"` succeeds on all 12; `pytest tests/contracts -k 'pipeline or manifest'` stays green (59 passed).
- **Committed in:** `1c8b79e` (Task 2 commit — the schema fix was required to implement and test the matcher at all, so it landed with the synthesizer).

**2. [Deviation - Data] Stage counts in expected_analysis annotations**
- **Found during:** Task 3 (stage count audit before annotation)
- **Issue:** The plan's `<pipelines_annotation_guide>` table contained estimated stage counts. Per-pipeline actual counts (verified via `grep -c '^  - name:'`) differed in 11 of 12 files.
- **Fix:** Used actual counts as the plan explicitly instructs ("determinism matters more than the table"). Differences:

  | Pipeline              | Table | Actual |
  | --------------------- | ----- | ------ |
  | animated-explainer    | 6     | 8      |
  | animation             | 5     | 8      |
  | avatar-spokesperson   | 5     | 7      |
  | cinematic             | 8     | 8 (match) |
  | clip-factory          | 4     | 7      |
  | documentary-montage   | 7     | 5      |
  | framework-smoke       | 3     | 2      |
  | hybrid                | 6     | 7      |
  | localization-dub      | 4     | 7      |
  | podcast-repurpose     | 5     | 7      |
  | screen-demo           | 6     | 9      |
  | talking-head          | 5     | 7      |
- **Impact:** Matcher behavior is grounded in disk reality. Test 4 had to pick a `stages=7` section_structure to hit the talking-head stage-count bonus correctly.

---

**Total deviations:** 2 (1 blocking fix — Rule 3; 1 data deviation pre-approved by plan text).
**Impact on plan:** Both deviations are explicitly sanctioned. No scope creep.

## Issues Encountered

- `pip` on the devcontainer is externally-managed (PEP 668); the install required `--break-system-packages`. Not a project-level issue.
- 3 pre-existing contract tests in `tests/contracts/test_phase2_contracts.py::TestCodeSnippetUnit` fail because the devcontainer lacks `fc-list` (fontconfig). Unrelated to this plan; already present before Task 1. Out of scope per scope-boundary rule.

## Ruamel quirks

None encountered in this plan (Pitfall 3 about empty `tools_available: []` rendering is not triggered because template mode does not currently mutate the base manifest). Will need re-verification in Plan 05-03 once LLM fill potentially populates those lists.

## User Setup Required

None — all work is code-only, no external service wiring.

## Handoff notes for Plan 05-02

- Public surface of `synthesize_pipeline()` returns the run-record dict but does NOT yet `jsonschema.validate` against `schemas/artifacts/pipeline_synthesis.schema.json`. Plan 05-02 should:
  1. Add `validate_synthesized_pipeline(manifest)` (returns `list[str]` issues; empty = pass).
  2. Add `SynthesisValidationError(issues)` class (in `lib/pipeline_synthesizer.py` — new local class is fine; SYNTH-01 forbids a class for the synthesizer's primary surface, but a small `Exception` subclass is idiomatic Python and does not violate the rule).
  3. Compute `diff_against_base` via `difflib.unified_diff(base_dump, synthesized_dump)` and set in the record.
  4. Run `jsonschema.validate(record, pipeline_synthesis.schema)` before return.
  5. Fold `validation_status` transitions (`pending` → `valid` / `invalid`) based on semantic checks.
- `list_pipelines()` already excludes `_staging/` by virtue of non-recursive `glob("*.yaml")`. The defense-in-depth filter `if not p.parent.name.startswith("_")` is SYNTH-07's explicit task — add it in Plan 05-02.
- Verifier must re-confirm: no `synthesize_and_accept` wrapper exists anywhere in `lib/`. Currently confirmed via `grep -rE "def synthesize_and_accept|def synth_and_accept" lib/` → empty.

## Self-Check: PASSED

Verified post-write:

```
[FOUND] lib/pipeline_synthesizer.py
[FOUND] tests/unit/test_pipeline_synthesizer.py
[FOUND] commit e25d67a (Task 1 Wave 0)
[FOUND] commit d5542ad (Task 2 RED)
[FOUND] commit 1c8b79e (Task 2 GREEN)
[FOUND] commit 0e2c27e (Task 3 annotations)
[VERIFIED] ruamel.yaml 0.19.1 installed
[VERIFIED] 'expected_analysis' in pipeline_manifest.schema.json properties
[VERIFIED] 'pipeline_defs/_staging/' in .gitignore
[VERIFIED] all 12 pipelines load with expected_analysis block
[VERIFIED] 12/12 tests green: pytest tests/unit/test_pipeline_synthesizer.py
[VERIFIED] no classes in lib/pipeline_synthesizer.py (grep '^class ' empty)
[VERIFIED] no synthesize_and_accept wrapper in lib/
```

---
*Phase: 05-synthesizer*
*Completed: 2026-04-17*
