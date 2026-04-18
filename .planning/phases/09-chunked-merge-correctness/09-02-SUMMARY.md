---
phase: 09-chunked-merge-correctness
plan: 02
subsystem: lib.chunked_analyzer + lib.analysis_merger
tags: [clean-05, clean-07, provider-validation, positional-hook-cta, backward-compat]
requirements: [CLEAN-05, CLEAN-07]
dependency_graph:
  requires:
    - "lib/analysis_errors.py (Phase 9 Plan 01 — MergeConsensusError taxonomy)"
    - "schemas/artifacts/video_analysis.schema.json (provider enum {gemini, openrouter})"
  provides:
    - "lib.chunked_analyzer._ALLOWED_PROVIDERS frozenset"
    - "lib.analysis_merger.merge_analyses(..., full_chunks=...) API"
    - "Guaranteed invariant: invalid providers fail before split_video runs"
    - "Guaranteed invariant: continue-mode hook/CTA picks track original submission index"
  affects:
    - "lib/chunked_analyzer.py (provider validation + full_chunks plumbing)"
    - "lib/analysis_merger.py (_merge_narrative + _pass_through_single + merge_analyses signature)"
    - "tests/unit/test_chunked_analyzer.py (8 new tests across 2 classes)"
    - "tests/unit/test_analysis_merger.py (2 new tests in TestFullChunksKwarg)"
tech_stack:
  added: []
  patterns:
    - "Top-of-function argument validation with schema-enum-anchored error message"
    - "Backward-compatible kwarg extension (full_chunks: list|None = None) for position-aware merge"
    - "Caller-side gated plumbing — call shape unchanged on happy path"
key_files:
  created: []
  modified:
    - "lib/chunked_analyzer.py (+31 -5 lines: _ALLOWED_PROVIDERS constant L130–134, provider_name validation L419–430, full_chunks list building L447–464, conditional merge_analyses call L482–491)"
    - "lib/analysis_merger.py (+61 -9 lines: merge_analyses signature + docstring, _merge_narrative positional picker, _pass_through_single warning, plumbing to _merge_narrative and _pass_through_single)"
    - "tests/unit/test_chunked_analyzer.py (+212 lines: TestProviderValidation 4 tests, TestContinueModePositionalHookCta 4 tests, 3 helper provider subclasses)"
    - "tests/unit/test_analysis_merger.py (+49 lines: TestFullChunksKwarg 2 tests)"
decisions:
  - "Full_chunks is a keyword-only optional arg (default None) — preserves backward compat for every pre-existing caller and test"
  - "analyze_chunked only passes full_chunks when failed_idxs is non-empty — keeps happy-path call shape identical to v2.0 so tests that monkeypatch merge_analyses with a `(pairs, provider)` signature continue to pass"
  - "N=1 pass-through with non-index-0 survivor emits WARNING but does NOT refuse the field — refusing would regress `test_continue_mode_merges_survivors` and provide no better value to the caller"
  - "Provider validation raises plain ValueError (not a VideoAnalysisError subclass) — it's an argument contract violation, not a runtime analysis failure"
metrics:
  duration_minutes: ~12
  tasks_completed: 2
  files_modified: 4
  commits: 4
  tests_added: 10
  suite_delta: "652 -> 662 passing (+10 new Plan 02 tests)"
  completed_date: "2026-04-18"
---

# Phase 9 Plan 2: Provider Validation + Positional Hook/CTA Summary

`lib/chunked_analyzer.py` now fails fast with a clear `ValueError` when `provider_tool.provider` is outside `{"gemini", "openrouter"}` (before `split_video` runs, before any cost-tracker reservation), and `lib/analysis_merger.merge_analyses` accepts an optional `full_chunks` kwarg so continue-mode merged artifacts pick `hook_*` from the lowest-index successful chunk and `cta_*` from the highest-index successful chunk — even when edge chunks die.

## Final API Signatures

### `lib/analysis_merger.py::merge_analyses`

```python
def merge_analyses(
    chunks: list[tuple[Chunk, dict]],
    provider: str = "gemini",
    *,
    full_chunks: list[tuple[Chunk, Any]] | None = None,
) -> dict:
```

`full_chunks` is keyword-only so every pre-existing positional call site (all v2.0 callers, all 66 pre-existing merger tests, the Plan 01 `TestMergeConsensusError` class) keeps the exact same signature with zero edits. When omitted or `None`, the merger behaves byte-identically to v2.0 on the happy path and Plan 01's raise-on-missing path alike.

### `lib/analysis_merger.py::_merge_narrative`

```python
def _merge_narrative(
    chunks: list[tuple[Chunk, dict]],
    weights: list[float],
    full_chunks: list[tuple[Chunk, Any]] | None = None,
) -> dict:
```

Internally, when `full_chunks is not None`, `first` and `last` are re-scoped to the narrative dims of the lowest-index and highest-index entries where `art is not None`. All other merge math (weighted averages, majority votes, concat with `approx_start_s` shifting) still runs over the survivor-only `chunks` argument — unchanged.

### `lib/analysis_merger.py::_pass_through_single`

```python
def _pass_through_single(
    pair: tuple[Chunk, dict],
    provider: str,
    full_chunks: list[tuple[Chunk, Any]] | None = None,
) -> dict:
```

When `full_chunks` is provided AND the sole surviving pair corresponds to a non-zero original index, a WARNING is logged: the emitted `hook_*` is the survivor's local middle-of-video hook, not the video-wide opening. No refusal — best-effort emit keeps `test_continue_mode_merges_survivors` green.

## Code Diffs

### `lib/chunked_analyzer.py` — 4 edit regions

**Region 1: module constant (L130–134)**

```python
# CLEAN-05 / v2.0 Phase 4 REVIEW MR-01 — chunking_metadata.provider is
# schema-constrained to this set. Validated at argument-entry time so
# invalid providers fail before split_video runs (saves a full pipeline).
_ALLOWED_PROVIDERS: frozenset[str] = frozenset({"gemini", "openrouter"})
```

**Region 2: provider_name validation (L419–430)**

Before:
```python
provider_name = getattr(provider_tool, "provider", None) or "unknown"
```

After:
```python
# CLEAN-05: pull the provider name WITHOUT a silent "unknown" default — we
# want None to surface here so the validation below catches the contract
# violation with a specific error rather than a downstream schema error.
provider_name = getattr(provider_tool, "provider", None)
if provider_name not in _ALLOWED_PROVIDERS:
    raise ValueError(
        f"provider_tool.provider={provider_name!r} is not in the "
        f"schema enum {sorted(_ALLOWED_PROVIDERS)} — merged artifact "
        f"would fail schema validation"
    )
```

Placement: runs before `split_video(video_path_str)` and before any `cost_tracker.estimate` call inside `_analyze_chunks`.

**Region 3: full_chunks list building (L447–464)**

Before (L440–454):
```python
pairs: list[tuple[Chunk, dict]] = []
failed_idxs: list[int] = []
for idx, chunk, tool_result in results:
    if not tool_result.success:
        failed_idxs.append(idx)
        continue
    artifact = dict(tool_result.data or {})
    artifact["_cost_usd"] = float(tool_result.cost_usd or 0.0)
    artifact["_provider_used"] = str(tool_result.model or provider_name)
    pairs.append((chunk, artifact))
```

After:
```python
# CLEAN-07 / MR-03: ALSO build a `full_chunks` list preserving original
# submission order with None slots for failures so merge_analyses can
# pick hook/cta from the position-correct survivor.
pairs: list[tuple[Chunk, dict]] = []
full_chunks: list[tuple[Chunk, Any]] = []
failed_idxs: list[int] = []
for idx, chunk, tool_result in results:
    if not tool_result.success:
        failed_idxs.append(idx)
        full_chunks.append((chunk, None))
        continue
    artifact = dict(tool_result.data or {})
    artifact["_cost_usd"] = float(tool_result.cost_usd or 0.0)
    artifact["_provider_used"] = str(tool_result.model or provider_name)
    pairs.append((chunk, artifact))
    full_chunks.append((chunk, artifact))
```

**Region 4: conditional merge_analyses call (L482–491)**

Before:
```python
merged = merge_analyses(pairs, provider=provider_name)
```

After:
```python
# CLEAN-07: pass full_chunks only when there are failures — when all chunks
# succeeded, the survivor list IS the full list and passing it is redundant
# (but not incorrect). Keep the call site narrow so backward-compat tests
# that patch merge_analyses see the same call shape on the happy path.
if failed_idxs:
    merged = merge_analyses(
        pairs, provider=provider_name, full_chunks=full_chunks
    )
else:
    merged = merge_analyses(pairs, provider=provider_name)
```

This gating is load-bearing: `TestArtifactStamping::test_cost_and_provider_stamped_on_artifact` and `test_provider_used_falls_back_to_provider_name_when_model_none` both monkeypatch `merge_analyses` with a lambda of signature `(pairs, provider)` — passing `full_chunks` unconditionally would break them with a `TypeError`. The happy path with no failures keeps the exact v2.0 call shape.

### `lib/analysis_merger.py` — 3 edit regions

**Region A: merge_analyses signature + docstring (L802–854)**

- Added keyword-only `full_chunks: list[tuple[Chunk, Any]] | None = None`
- Appended Parameters section describing the kwarg and its v2.0-compat default
- Updated `if len(chunks) == 1: return _pass_through_single(...)` to forward `full_chunks`
- Updated `"narrative": _merge_narrative(chunks, weights)` to forward `full_chunks=full_chunks`

**Region B: _merge_narrative positional picker (L619–641)**

Before:
```python
dims = _chunks_dim(chunks, "narrative")
first = dims[0]
last = dims[-1]
```

After:
```python
dims = _chunks_dim(chunks, "narrative")
# CLEAN-07 / MR-03: pick hook/cta by ORIGINAL submission index.
if full_chunks is not None:
    successful = [art for _c, art in full_chunks if art is not None]
    if successful:
        first = (successful[0].get("narrative") or {})
        last = (successful[-1].get("narrative") or {})
    else:
        # Defensive: should never happen (empty survivors raise upstream)
        first = dims[0]
        last = dims[-1]
else:
    first = dims[0]
    last = dims[-1]
```

All other consensus logic (`_weighted_majority` over `dims`, `first.get("narrative_arc")` fallbacks, concat shifts) is unchanged — `first`/`last` just carry position-correct values when the caller supplies `full_chunks`.

**Region C: _pass_through_single warning (L786–822)**

Added a diagnostic WARNING when the sole survivor's original index is not 0 — emitted once per merge, keyed on the survivor's `start_global` to match against `full_chunks`. The function still emits the artifact verbatim (matches pre-existing `TestSingleChunkPassThrough` contract).

## Test IDs Added (10 total)

### `tests/unit/test_chunked_analyzer.py::TestProviderValidation` (4 tests)

| Test | Covers |
|---|---|
| `test_invalid_provider_name_raises_before_split` | `_BadProvider` (provider="anthropic") → ValueError; split_video + provider.execute never called |
| `test_none_provider_raises_before_split` | `_NoneProvider` (provider=None) → ValueError with "None" in message |
| `test_invalid_provider_does_not_touch_cost_tracker` | cost_tracker.estimate and cost_tracker.reserve never called when provider is rejected |
| `test_openrouter_provider_accepted` | `_OpenRouterProvider` (provider="openrouter") → merges end-to-end; proves enum not over-narrowed |

### `tests/unit/test_chunked_analyzer.py::TestContinueModePositionalHookCta` (4 tests)

| Test | Covers |
|---|---|
| `test_fail_chunk_0_hook_from_chunk_1` | Chunk 0 fails in 3-chunk video → hook = "bold_claim" (chunk 1), cta = "purchase" (chunk 2) |
| `test_fail_last_chunk_cta_from_second_to_last` | Chunk N-1 fails → cta = "visit_link" (chunk 1); hook unchanged from chunk 0 |
| `test_fail_both_edges_hook_from_1_cta_from_nminus2` | Chunks 0 and 3 fail in 4-chunk video → hook = "bold_claim" (chunk 1), cta = "purchase" (chunk 2) |
| `test_continue_mode_merged_artifact_schema_valid` | validate_artifact("video_analysis", merged) passes on survivor scenarios |

### `tests/unit/test_analysis_merger.py::TestFullChunksKwarg` (2 tests)

| Test | Covers |
|---|---|
| `test_full_chunks_none_is_backward_compatible` | merge_analyses(..., full_chunks=None) equals merge_analyses without the kwarg |
| `test_full_chunks_with_none_slots_preserves_position` | Direct merger API: 3-chunk with middle (idx 1) as None → hook from idx 0, cta from idx 2 |

## Commits

| Task | Commit | Title |
|---|---|---|
| 1 (RED) | `74905f0` | test(09-02): add failing tests for provider validation (CLEAN-05) |
| 1 (GREEN) | `35663da` | feat(09-02): add _ALLOWED_PROVIDERS + top-of-function validation (CLEAN-05) |
| 2 (RED) | `6b71482` | test(09-02): add failing tests for positional hook/CTA merger (CLEAN-07) |
| 2 (GREEN) | `f68658a` | feat(09-02): position-aware hook/CTA via full_chunks kwarg (CLEAN-07) |

## Observations from execution (not deviations)

**Task 2 RED: 4 of 6 new tests unexpectedly passed.** The `TestContinueModePositionalHookCta` class (fail-chunk-0, fail-chunk-N-1, fail-both-edges, schema-valid-survivors) passed against pre-Task-2 code. Root cause: per the plan's `<interfaces>` Option A analysis, `chunked_analyzer.results.sort(key=lambda t: t[0])` (line 335) already yields survivor pairs in submission-index order, and the drop-on-failure filter preserves that order; so `dims[0]`/`dims[-1]` in the original `_merge_narrative` already corresponded to the lowest/highest-index SURVIVING chunks for N≥2 survivors. The 2 `TestFullChunksKwarg` tests at the merger API boundary DID fail as expected (no `full_chunks` kwarg).

This confirms the plan's observation that the real gap closed by `full_chunks` is:
1. The **N=1 survivor warning path** (`_pass_through_single` now logs when sole survivor is not at original idx 0)
2. The **merger-direct API contract** (callers constructing their own survivor/full lists can now pick position-correct hook/CTA without re-implementing the logic in `chunked_analyzer`)
3. **Documented intent** — the `full_chunks` kwarg makes the positional contract explicit rather than an incidental byproduct of sort+filter order

Implementation proceeded per the plan's locked Option A without deviation.

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

**Task 1 acceptance (CLEAN-05):**
- `grep -c "_ALLOWED_PROVIDERS" lib/chunked_analyzer.py` → `3` ✓ (≥ 2)
- `grep -c "frozenset({\"gemini\", \"openrouter\"})" lib/chunked_analyzer.py` → `1` ✓
- `grep -n "provider_name not in _ALLOWED_PROVIDERS" lib/chunked_analyzer.py` → exactly 1 match inside `analyze_chunked` ✓
- `grep -nE 'or "unknown"' lib/chunked_analyzer.py` → zero matches on executable code ✓
- 4 new tests in `TestProviderValidation` all pass ✓
- `python3 -c "from lib.chunked_analyzer import _ALLOWED_PROVIDERS; assert _ALLOWED_PROVIDERS == frozenset({'gemini','openrouter'})"` → exits 0 ✓

**Task 2 acceptance (CLEAN-07):**
- `grep -c "full_chunks" lib/analysis_merger.py` → `12` ✓ (≥ 6)
- `grep -c "full_chunks" lib/chunked_analyzer.py` → `6` ✓ (≥ 3)
- `grep -nE "CLEAN-07|MR-03" lib/analysis_merger.py` → `4` matches ✓ (≥ 1)
- `grep -nE "CLEAN-07|MR-03" lib/chunked_analyzer.py` → `2` matches ✓ (≥ 1)
- `python3 -c "from lib.analysis_merger import merge_analyses; import inspect; assert 'full_chunks' in inspect.signature(merge_analyses).parameters"` → passes ✓
- 6 new tests across `TestContinueModePositionalHookCta` + `TestFullChunksKwarg` all pass ✓
- `TestContinueMode::test_continue_mode_merges_survivors` (v2.0 regression guard) still passes ✓
- `TestSingleChunkPassThrough` (N=1 backward-compat) still passes ✓

**Happy-path backward compat:**
- `TestArtifactStamping::test_cost_and_provider_stamped_on_artifact` uses a `fake_merge(pairs, provider)` lambda → still passes because analyze_chunked only passes `full_chunks` when failures occurred ✓
- `TestArtifactStamping::test_provider_used_falls_back_to_provider_name_when_model_none` same path → still passes ✓

**Full-suite regression:**
- Baseline (d48180f, Plan 01 SHIPPED): `652 passed, 13 skipped, 3 failed`
- Post-Task 1: `656 passed, 13 skipped, 3 failed` (+4 CLEAN-05 tests)
- Post-Task 2: `662 passed, 13 skipped, 3 failed` (+6 CLEAN-07 tests)
- The 3 `fc-list` failures in `tests/contracts/test_phase2_contracts.py::TestCodeSnippetUnit` are pre-existing and documented in STATE.md — fontconfig (`fc-list` binary) is absent from this devcontainer; unrelated to Phase 9 scope.

## Phase 9 Overall Status

- **CLEAN-05** — closed (Plan 02, this SUMMARY)
- **CLEAN-06** — closed (Plan 01, SHIPPED 2026-04-18, commit chain `870ee14..cff672b`)
- **CLEAN-07** — closed (Plan 02, this SUMMARY)

All 3 Phase 9 requirements satisfied. Ready for Phase 10 (Synthesizer Records / CLEAN-08 / CLEAN-09).

## Self-Check: PASSED

- [x] `lib/chunked_analyzer.py` contains `_ALLOWED_PROVIDERS` constant (verified via import)
- [x] `lib/chunked_analyzer.py` contains `provider_name not in _ALLOWED_PROVIDERS` validation before `split_video`
- [x] `lib/chunked_analyzer.py` contains 6+ references to `full_chunks` (declaration, append None, append art, conditional call, kwarg, arg)
- [x] `lib/analysis_merger.py` contains `full_chunks` in `merge_analyses` signature (verified via `inspect.signature`)
- [x] `lib/analysis_merger.py` contains `full_chunks` in `_merge_narrative` + `_pass_through_single` signatures
- [x] `tests/unit/test_chunked_analyzer.py` contains `class TestProviderValidation` + `class TestContinueModePositionalHookCta`
- [x] `tests/unit/test_analysis_merger.py` contains `class TestFullChunksKwarg`
- [x] Commit `74905f0` present in git log
- [x] Commit `35663da` present in git log
- [x] Commit `6b71482` present in git log
- [x] Commit `f68658a` present in git log
- [x] Full regression at 662 passing / 13 skipped / 3 pre-existing fc-list failures
- [x] ROADMAP Phase 9 success criteria #1, #3, #4, #5 all satisfied
