---
phase: 09-chunked-merge-correctness
plan: 01
subsystem: lib.analysis_merger
tags: [clean-06, single-validation-gate, error-taxonomy, backward-compat]
requirements: [CLEAN-06]
dependency_graph:
  requires:
    - "lib/analysis_errors.py (Phase 8 sentinel taxonomy — VideoAnalysisAuthError / VideoAnalysisRateLimitError pattern)"
    - "schemas/artifacts/video_analysis.schema.json (required-field enums, not modified)"
  provides:
    - "lib.analysis_errors.MergeConsensusError — subclass of VideoAnalysisError"
    - "Guaranteed invariant: analysis_merger never fabricates values on required fields"
  affects:
    - "lib/analysis_merger.py (8 consensus sites converted)"
    - "tests/unit/test_analysis_merger.py (9 new tests; no existing tests updated)"
tech_stack:
  added: []
  patterns:
    - "Phase 8 sentinel-subclass-of-VideoAnalysisError pattern extended with MergeConsensusError"
    - "Guarded-raise replaces silent-default-fallback at consensus boundaries"
key_files:
  created: []
  modified:
    - "lib/analysis_errors.py (+16 lines, class added at L81–94)"
    - "lib/analysis_merger.py (+72 -15 lines, import L59 + 8 raise sites)"
    - "tests/unit/test_analysis_merger.py (+127 lines, TestMergeConsensusError at L807–932)"
decisions:
  - "Preserve first-chunk fallback; only remove hardcoded string defaults"
  - "Error message uses the literal '(the string literal is schema-valid but would be a merger-invented value)' phrasing instead of the concrete `\"unknown\"` enum value, so the ROADMAP Phase 9 acceptance grep (`grep -n '\"unknown\"' lib/analysis_merger.py`) returns zero matches"
  - "Leave line 244 (_merge_source type=local_file), _weighted_avg 0.0 sentinel, hook_type/cta_type 'none'/'none_detected' untouched — out of CLEAN-06 scope"
metrics:
  duration_minutes: ~8
  tasks_completed: 3
  files_modified: 3
  commits: 3
  tests_added: 9
  suite_delta: "643 -> 652 passing (+9 new CLEAN-06 tests)"
  completed_date: "2026-04-18"
---

# Phase 9 Plan 1: MergeConsensusError — Remove Silent Fallback Defaults Summary

`lib/analysis_merger.py` no longer fabricates schema-valid-but-wrong values on required consensus fields; every `vote or dims[0].get(field, DEFAULT)` site now raises a new `MergeConsensusError` sentinel when no chunk ever provided the field, preserving single-validation-gate and surfacing real upstream provider bugs as pointed errors.

## What Changed

### `lib/analysis_errors.py` (L81–94, appended)

New `MergeConsensusError(VideoAnalysisError)` class mirroring Phase 8's `VideoAnalysisAuthError` / `VideoAnalysisRateLimitError` style (same indentation, same docstring triple-quote convention, same position — after the existing last class). Docstring references CLEAN-06 / v2.0 Phase 4 REVIEW MR-02 for traceability.

### `lib/analysis_merger.py` (L59 import; 8 raise sites)

Import added at line 59: `from lib.analysis_errors import MergeConsensusError`.

All 8 fallback sites converted to the identical pattern: compute consensus → compute first-chunk fallback → if both None, `raise MergeConsensusError("{dim}.{field}: ...")` → else prefer consensus, else first-chunk. The happy path (any chunk provides a value) is byte-identical to v2.0 output; only the hardcoded string default at the tail is removed.

### Per-site before/after

**Site 1 — `editing_pacing.pacing_style` (pre-edit L295 → post-edit raise at L298):**

Before:
```python
merged["pacing_style"] = pacing or dims[0].get("pacing_style", "steady_educational")
```
After:
```python
first_pacing = dims[0].get("pacing_style")
if pacing is None and first_pacing is None:
    raise MergeConsensusError("editing_pacing.pacing_style: no chunk provided a value ...")
merged["pacing_style"] = pacing if pacing is not None else first_pacing
```

**Site 2 — `audio.narration_style` (pre-edit L394 → post-edit raise at L404):**

Before: `merged["narration_style"] = nar_style or dims[0].get("narration_style", "none")`
After: guarded raise + `merged["narration_style"] = nar_style if nar_style is not None else first_nar_style`

**Site 3 — `audio.voice_music_mix` (pre-edit L400 → post-edit raise at L417):**

Before: `merged["voice_music_mix"] = vmm or dims[0].get("voice_music_mix", "narration_dominant")`
After: guarded raise + `merged["voice_music_mix"] = vmm if vmm is not None else first_vmm`

**Site 4 — `visual_style.production_quality` (pre-edit L538 → post-edit raise at L562):**

Before: `merged["production_quality"] = pq or dims[0].get("production_quality", "professional")`
After: guarded raise + `merged["production_quality"] = pq if pq is not None else first_pq`

**Site 5 — `visual_style.aspect_ratio` (pre-edit L551 → post-edit raise at L582):**

Before: `merged["aspect_ratio"] = first_ratio or "16:9"`
After:
```python
if first_ratio is None:
    raise MergeConsensusError("visual_style.aspect_ratio: chunks[0].aspect_ratio is None ...")
merged["aspect_ratio"] = first_ratio
```
First-chunk-wins + warn-on-disagreement semantics preserved; only the `or "16:9"` hardcoded tail removed.

**Site 6 — `narrative.narrative_arc` (pre-edit L602 → post-edit raise at L639):**

Before: `merged["narrative_arc"] = arc or first.get("narrative_arc", "linear")`
After: guarded raise + `merged["narrative_arc"] = arc if arc is not None else first_arc`

**Site 7 — `narrative.target_platform` (pre-edit L637 → post-edit raise at L681):**

Before: `merged["target_platform"] = tp or first.get("target_platform", "unknown")`
After: guarded raise + `merged["target_platform"] = tp if tp is not None else first_tp`

Note: error message deliberately avoids the literal `"unknown"` (uses "the string literal is schema-valid but would be a merger-invented value" wording) so the ROADMAP Phase 9 success-criterion grep `grep -n '"unknown"' lib/analysis_merger.py` returns zero matches. The enum value itself remains schema-valid per `schemas/artifacts/video_analysis.schema.json` lines 272–283 — the removal is a single-validation-gate fix, not an enum fix.

**Site 8 — `narrative.content_tone` (pre-edit L655 → post-edit raise at L707):**

Before: `merged["content_tone"] = tone or first.get("content_tone", "educational")`
After: guarded raise + `merged["content_tone"] = tone if tone is not None else first_tone`

### `tests/unit/test_analysis_merger.py` (L807–932, appended)

New `TestMergeConsensusError` class with 9 tests:

| Test | Covers | Commit |
|---|---|---|
| `test_pacing_style_missing_raises` | editing_pacing.pacing_style raise | cff672b |
| `test_narration_style_missing_raises` | audio.narration_style raise | cff672b |
| `test_voice_music_mix_missing_raises` | audio.voice_music_mix raise | cff672b |
| `test_production_quality_missing_raises` | visual_style.production_quality raise | cff672b |
| `test_aspect_ratio_missing_raises` | visual_style.aspect_ratio raise | cff672b |
| `test_narrative_arc_missing_raises` | narrative.narrative_arc raise | cff672b |
| `test_target_platform_missing_raises` | narrative.target_platform raise | cff672b |
| `test_content_tone_missing_raises` | narrative.content_tone raise | cff672b |
| `test_inherits_video_analysis_error` | Backward-compat inheritance guard | cff672b |

Each raise test uses `pytest.raises(MergeConsensusError, match=r"{dim}\.{field}")` — the regex anchors both the dimension name and the field name in the exception message. The fixture `fake_video_chunks` deep-merges overrides (per `_deep_merge` in `tests/unit/conftest.py`), so `{"editing_pacing": {"pacing_style": None}}` nulls just the target field without clobbering sibling required fields — the chunks remain otherwise schema-valid, so the test hits exactly the targeted raise site.

## Step A Audit — Existing tests that pinned old fallbacks

Audit greps executed:
```
grep -nE 'merged\[.(pacing_style|narration_style|voice_music_mix|production_quality|narrative_arc|target_platform|content_tone).\].*==.*("steady_educational"|"none"|"narration_dominant"|"professional"|"linear"|"unknown"|"educational")' tests/unit/test_analysis_merger.py
grep -nE 'merged\[.aspect_ratio.\].*==.*"16:9"' tests/unit/test_analysis_merger.py
```

**Audit result: zero pre-existing tests pinned an old hardcoded fallback.** Every happy-path test in the file supplies explicit values on every chunk (e.g. `test_production_quality_majority` at L505 sets `"professional"` on every chunk, so the merger returns it via the unchanged consensus path, not via a fabricated default). `test_aspect_ratio_first_chunk_wins_and_warns` at L480 supplies `"16:9"` on chunk[0] — happy path, unchanged.

**No existing tests were updated or deleted.** Backward compat preserved: all 66 pre-existing merger tests still pass verbatim against the new code.

## Out-of-Scope Sites Intentionally Left Unchanged

Per CONTEXT.md and the plan's `<action>` Step D, the following defensive-default patterns are NOT part of CLEAN-06 and remain as-is:

- `lib/analysis_merger.py` L244 — `first["type"] = "local_file"` in `_merge_source`. A 9th site that papers over missing source metadata, but flagged separately from CLEAN-06 (deferred to Phase 11 NITS-01 if desired).
- `lib/analysis_merger.py` L72–88 — `_weighted_avg` returns 0.0 on empty / all-zero-weight input. Tracked as LO-01, Phase 11 NITS-01 territory.
- `lib/analysis_merger.py` L594 / L628 — `first.get("hook_type", "none")` / `last.get("cta_type", "none_detected")`. These strings ARE schema-valid enum members meaning "no hook detected" / "no CTA detected" — they're not fabricated defaults, they're semantically meaningful sentinels. Correct behavior; leave alone.

## Commits

| Task | Commit | Title |
|---|---|---|
| 1 | `870ee14` | feat(09-01): add MergeConsensusError sentinel to analysis_errors |
| 2 | `e9eb86f` | feat(09-01): replace 8 hardcoded-default fallbacks with MergeConsensusError |
| 3 | `cff672b` | test(09-01): add TestMergeConsensusError — 9 tests for required-field raises |

## Deviations from Plan

None — plan executed exactly as written.

One implementation detail worth calling out (explicitly sanctioned by the plan's `<action>` block for site 7): the `target_platform` raise message uses the phrasing "the string literal is schema-valid but would be a merger-invented value" rather than spelling out the literal `"unknown"` string, because the ROADMAP Phase 9 acceptance criterion #2 requires `grep -n '"unknown"' lib/analysis_merger.py` to return zero matches. Including the literal in the error string would have tripped that grep. The CLEAN-06 intent is preserved (no fabricated default) and the test `test_target_platform_missing_raises` still anchors on `r"narrative\.target_platform"` which is the dimension.field prefix — fully decoupled from the literal.

## Verification Results

**Task 1 acceptance:**
- `grep -c "^class MergeConsensusError(VideoAnalysisError):" lib/analysis_errors.py` → `1` ✓
- `grep -c "CLEAN-06" lib/analysis_errors.py` → `1` ✓
- `python3 -c "from lib.analysis_errors import MergeConsensusError, VideoAnalysisError; assert issubclass(MergeConsensusError, VideoAnalysisError); print('ok')"` → `ok` ✓
- All 7 pre-existing exports still import without regression ✓

**Task 2 acceptance:**
- `grep -c "raise MergeConsensusError" lib/analysis_merger.py` → `8` ✓
- `grep -nE '"unknown"|or "unknown"|\.get\(.*, *"unknown"\)' lib/analysis_merger.py` → zero matches ✓ (CLEAN-06 acceptance criterion #2 / ROADMAP Phase 9 SC #2)
- `grep -c "or dims\[0\]\.get(" lib/analysis_merger.py` → `0` ✓
- `grep -c 'or first.get(' lib/analysis_merger.py` → `0` ✓
- `grep -c 'or "16:9"' lib/analysis_merger.py` → `0` ✓
- `grep -c 'or "steady_educational"\|or "none"\|or "narration_dominant"\|or "professional"\|or "linear"\|or "educational"' lib/analysis_merger.py` → `0` ✓
- `grep -c "from lib.analysis_errors import MergeConsensusError" lib/analysis_merger.py` → `1` ✓

**Task 3 acceptance:**
- `grep -c "class TestMergeConsensusError" tests/unit/test_analysis_merger.py` → `1` ✓
- 8 field-specific raise tests + 1 inheritance test = 9 new tests ✓
- `grep -c "MergeConsensusError" tests/unit/test_analysis_merger.py` → `22` (well above the `>= 9` bar) ✓

**Full-suite regression:**
- Baseline (pre-plan, HEAD=ce66ec7): `643 passed, 13 skipped, 3 failed` (3 pre-existing fc-list failures)
- Post-Task 1: `643 passed, 13 skipped, 3 failed` (Task 1 adds no tests, only a class)
- Post-Task 2: `643 passed, 13 skipped, 3 failed` (Task 2 behavior is equivalent on the happy path — no regression)
- Post-Task 3: `652 passed, 13 skipped, 3 failed` (+9 new tests)

The 3 `fc-list` failures in `tests/contracts/test_phase2_contracts.py::TestCodeSnippetUnit` are pre-existing and documented in STATE.md — fontconfig (`fc-list` binary) is absent from this devcontainer; unrelated to Phase 9 scope.

## Self-Check: PASSED

- [x] `lib/analysis_errors.py` exists and contains `MergeConsensusError` class (L81–94)
- [x] `lib/analysis_merger.py` contains import at L59 and 8 `raise MergeConsensusError` sites
- [x] `tests/unit/test_analysis_merger.py` contains `TestMergeConsensusError` class
- [x] Commit `870ee14` present in git log
- [x] Commit `e9eb86f` present in git log
- [x] Commit `cff672b` present in git log
- [x] Full regression at 652 passing / 13 skipped / 3 pre-existing fc-list failures
- [x] `MergeConsensusError` catchable by `except VideoAnalysisError` (verified by `test_inherits_video_analysis_error`)
- [x] ROADMAP Phase 9 success criterion #2 satisfied: zero `"unknown"` string literals on executable code paths in `lib/analysis_merger.py`
