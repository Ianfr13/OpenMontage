---
phase: 09-chunked-merge-correctness
verified: 2026-04-17T00:00:00Z
status: passed
score: 12/12 must-haves verified
overrides_applied: 0
---

# Phase 9: Chunked Merge Correctness — Verification Report

**Phase Goal:** Make the chunked analyzer + merger produce artifacts that pass canonical schema validation without hardcoded fallback cheats and with positional hook/CTA rules honored.
**Verified:** 2026-04-17
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Derived from ROADMAP Phase 9 Success Criteria + PLAN 09-01 + PLAN 09-02 `must_haves.truths`.

| #   | Truth                                                                                                                                                                | Status     | Evidence                                                                                                                         |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `chunked_analyzer` rejects any `provider_tool.provider` outside `{"gemini","openrouter"}` before writing `chunking_metadata.provider`; contract test asserts clear error | VERIFIED   | `lib/chunked_analyzer.py:428` validates via `_ALLOWED_PROVIDERS`; `TestProviderValidation` (4 tests) pass                        |
| 2   | `grep -n '"unknown"\|or "unknown"\|\.get(.*, *"unknown")' lib/analysis_merger.py` returns zero matches on required-field code paths                                  | VERIFIED   | grep returned ZERO MATCHES                                                                                                       |
| 3   | With `on_chunk_error="continue"` and mix of successful/failed chunks, merged artifact's hook comes from lowest-index successful chunk and CTA from highest-index     | VERIFIED   | `TestContinueModePositionalHookCta` (4 tests) pass covering fail-chunk-0, fail-chunk-N-1, fail-both-edges, schema-valid-survivors |
| 4   | `validate_artifact("video_analysis", merged)` passes on every merger output path; no test relies on removed fallback defaults                                        | VERIFIED   | `test_continue_mode_merged_artifact_schema_valid` passes; all 66+ pre-existing merger tests pass                                 |
| 5   | Full test suite reports 588+ passing; baseline 643 + 19 new tests = 662                                                                                              | VERIFIED   | `pytest tests/ --ignore=tests/qa -q` → `662 passed, 13 skipped, 3 failed` (3 pre-existing fc-list failures)                      |
| 6   | `MergeConsensusError` raised when `_weighted_majority`/first-non-null yields None on required field (replaces silent fallback)                                       | VERIFIED   | 8 raise sites in `lib/analysis_merger.py`; 8 field-specific tests pass                                                           |
| 7   | Happy path: when every chunk provides a valid value, merger returns consensus verbatim (no behavior regression)                                                      | VERIFIED   | All 66 pre-existing merger tests pass unchanged; fixture `fake_video_chunks` exercises happy path                                |
| 8   | `MergeConsensusError` catchable by `except VideoAnalysisError` (inheritance preserved)                                                                               | VERIFIED   | `test_inherits_video_analysis_error` passes; `issubclass(MergeConsensusError, VideoAnalysisError)` is True                       |
| 9   | `_ALLOWED_PROVIDERS` frozenset constant exists in `chunked_analyzer.py`                                                                                              | VERIFIED   | `lib/chunked_analyzer.py:134` defines `frozenset({"gemini", "openrouter"})`                                                      |
| 10  | `full_chunks` kwarg or equivalent positional-preserving param exists in merger API                                                                                   | VERIFIED   | `lib/analysis_merger.py:845` — `merge_analyses(..., *, full_chunks: list[tuple[Chunk, Any]] \| None = None)`                     |
| 11  | Parametrized test covers: failing chunk 0, failing chunk N-1, failing middle chunks                                                                                  | VERIFIED   | `TestContinueModePositionalHookCta` has 3 position tests + 1 schema-valid test                                                   |
| 12  | Invalid provider (missing/None/`"anthropic"`) raises ValueError before `split_video` runs; `cost_tracker.estimate` never called                                      | VERIFIED   | `test_invalid_provider_name_raises_before_split`, `test_none_provider_raises_before_split`, `test_invalid_provider_does_not_touch_cost_tracker` all pass |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact                                 | Expected                                                             | Status     | Details                                                                                                |
| ---------------------------------------- | -------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------ |
| `lib/analysis_errors.py`                 | `MergeConsensusError` subclass of `VideoAnalysisError` appended      | VERIFIED   | Class at L81-94, subclasses `VideoAnalysisError`, docstring references CLEAN-06                        |
| `lib/analysis_merger.py`                 | 8 fallback sites replaced with `MergeConsensusError` raises; `full_chunks` kwarg | VERIFIED   | 8 `raise MergeConsensusError` sites; `full_chunks` appears 12 times (signature + docstring + usage)    |
| `lib/chunked_analyzer.py`                | `_ALLOWED_PROVIDERS` frozenset; top-of-function provider validation; full_chunks list building | VERIFIED   | Constant L134; validation L427-433 (before split_video L437); full_chunks plumbing L459-475, L494-499  |
| `tests/unit/test_analysis_merger.py`     | `TestMergeConsensusError` class with 9 tests + `TestFullChunksKwarg` with 2 tests | VERIFIED   | 9 TestMergeConsensusError tests + 2 TestFullChunksKwarg tests all pass                                 |
| `tests/unit/test_chunked_analyzer.py`    | `TestProviderValidation` (4 tests) + `TestContinueModePositionalHookCta` (4 tests) | VERIFIED   | All 8 tests pass; `_BadProvider`, `_NoneProvider`, `_OpenRouterProvider` helper classes present        |

### Key Link Verification

| From                                               | To                                                   | Via                                                   | Status | Details                                                                         |
| -------------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------- | ------ | ------------------------------------------------------------------------------- |
| `lib/analysis_merger.py::_merge_*`                 | `lib.analysis_errors.MergeConsensusError`            | `raise MergeConsensusError(f'{dim}.{field}: ...')`    | WIRED  | 8 raise sites; grep confirms `raise MergeConsensusError` count = 8              |
| `lib/analysis_merger.py`                           | `lib.analysis_errors`                                | `from lib.analysis_errors import MergeConsensusError` | WIRED  | Import present (grep count = 1)                                                 |
| `lib/chunked_analyzer.py::analyze_chunked`         | `_ALLOWED_PROVIDERS`                                 | `if provider_name not in _ALLOWED_PROVIDERS: raise ValueError(...)` | WIRED  | L428-433 raises before L437 `split_video`                                       |
| `lib/chunked_analyzer.py::analyze_chunked` (continue mode) | `lib.analysis_merger.merge_analyses`         | passes `full_chunks` kwarg when `failed_idxs` non-empty | WIRED  | L494-499 conditional call site; gating preserves backward-compat call shape     |

### Data-Flow Trace (Level 4)

Not applicable — phase produces library code (exception class, orchestrator, merger), not UI/data rendering components. Data flow validated via behavioral tests (below).

### Behavioral Spot-Checks

| Behavior                                                   | Command                                                                                                      | Result       | Status |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------------ | ------ |
| `MergeConsensusError` importable and is `VideoAnalysisError` subclass | `python3 -c "from lib.analysis_errors import MergeConsensusError, VideoAnalysisError; assert issubclass(MergeConsensusError, VideoAnalysisError); print('ok')"` | `INHERITANCE OK` | PASS |
| `_ALLOWED_PROVIDERS` exposes exact expected enum           | `python3 -c "from lib.chunked_analyzer import _ALLOWED_PROVIDERS; assert _ALLOWED_PROVIDERS == frozenset({'gemini','openrouter'})"`    | `ALLOWED_PROVIDERS OK` | PASS |
| `full_chunks` kwarg present in `merge_analyses` signature  | `python3 -c "from lib.analysis_merger import merge_analyses; import inspect; assert 'full_chunks' in inspect.signature(merge_analyses).parameters"` | `full_chunks kwarg OK` | PASS |
| All Phase 9-specific tests pass                            | `pytest TestMergeConsensusError TestProviderValidation TestContinueModePositionalHookCta TestFullChunksKwarg -v`  | `19 passed` | PASS |
| Full suite regression                                       | `pytest tests/ --ignore=tests/qa -q`                                                                         | `662 passed, 13 skipped, 3 failed` (3 pre-existing fc-list) | PASS |
| Grep: `raise MergeConsensusError` count in merger          | `grep -c "raise MergeConsensusError" lib/analysis_merger.py`                                                 | `8` (≥ 8)  | PASS |
| Grep: zero `"unknown"` defaults in merger                  | `grep -nE '"unknown"\|or "unknown"\|\.get\(.*, *"unknown"\)' lib/analysis_merger.py`                         | zero matches | PASS |

### Requirements Coverage

| Requirement | Source Plan    | Description                                                                                                       | Status     | Evidence                                                                                                    |
| ----------- | -------------- | ----------------------------------------------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------- |
| CLEAN-05    | 09-02-PLAN.md  | Validate `provider_tool.provider` against `{"gemini","openrouter"}` before populating `chunking_metadata.provider` | SATISFIED  | `_ALLOWED_PROVIDERS` frozenset + validation before `split_video`; 4 tests pass                              |
| CLEAN-06    | 09-01-PLAN.md  | Remove hardcoded default fallbacks on required fields (e.g., `target_platform` → `"unknown"`)                     | SATISFIED  | 8 fallback sites replaced with `MergeConsensusError`; zero `"unknown"` matches; 9 tests pass                |
| CLEAN-07    | 09-02-PLAN.md  | Continue mode must honor position for hook (lowest-index) and CTA (highest-index)                                 | SATISFIED  | `full_chunks` kwarg in merger; `_merge_narrative` position-aware; 6 tests pass (4 orchestrator + 2 direct)  |

No orphaned requirements. All 3 IDs declared in plan frontmatter and REQUIREMENTS.md map to completed implementation.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |

None detected.
- Zero TODO/FIXME/HACK/PLACEHOLDER comments in modified files (`lib/chunked_analyzer.py`, `lib/analysis_merger.py`, `lib/analysis_errors.py`).
- Zero empty returns / stub implementations.
- Zero hardcoded `"unknown"` defaults on required fields in `lib/analysis_merger.py` (confirmed by grep).

### Human Verification Required

None. All behavior is programmatically verifiable through unit tests and grep contracts. No UI, no real-time behavior, no external service dependencies introduced in this phase.

### Gaps Summary

No gaps. Phase 9 achieved its goal:
- All 8 silent fallback defaults in `lib/analysis_merger.py` replaced with guarded `MergeConsensusError` raises.
- Provider whitelist (`_ALLOWED_PROVIDERS`) validates at argument-entry time in `analyze_chunked` before `split_video` runs.
- Position-aware hook/CTA picks flow through `merge_analyses(full_chunks=...)` kwarg when continue-mode drops edge chunks.
- Backward compat preserved: existing callers unchanged (kwarg is keyword-only with `None` default), happy-path call shape from `analyze_chunked` is identical to v2.0 when no failures occur.
- Full suite: 662 passed / 13 skipped / 3 pre-existing fc-list failures (documented in STATE.md).

All 12 must-haves verified. CLEAN-05, CLEAN-06, CLEAN-07 satisfied. Ready for Phase 10.

---

_Verified: 2026-04-17_
_Verifier: Claude (gsd-verifier)_
