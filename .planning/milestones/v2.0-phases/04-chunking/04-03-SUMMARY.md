---
phase: 04-chunking
plan: 03
subsystem: chunked_analyzer
tags: [chunking, threadpool, cost-tracker, orchestration, video_analysis]

# Dependency graph
requires:
  - phase: 04-chunking/04-01
    provides: lib.video_chunker (split_video + cleanup_chunks + Chunk)
  - phase: 04-chunking/04-02
    provides: lib.analysis_merger.merge_analyses
  - phase: 01-contracts
    provides: schemas.artifacts.validate_artifact (canonical video_analysis schema)
  - phase: 02-gemini / 03-openrouter
    provides: concrete video_analysis provider tools the orchestrator drives
provides:
  - lib.chunked_analyzer.analyze_chunked (ThreadPoolExecutor orchestrator)
  - lib.chunked_analyzer.estimate_chunked_cost (pre-run cost heuristic)
  - tests/contracts/test_phase4_chunked_path.py (offline end-to-end gate)
affects:
  - Phase 6 reference-synthesis.md meta skill (direct caller of analyze_chunked)
  - Phase 7 integration tests (RUN_INTEGRATION_TESTS=1 — real ffmpeg + real provider)

# Tech tracking
tech-stack:
  added: []  # all stdlib + existing repo modules
  patterns:
    - "ThreadPoolExecutor + as_completed with per-chunk progress callback"
    - "Submission-order restoration via result sort after completion"
    - "try/finally cleanup that survives provider AND merger exceptions"
    - "cost_tracker estimate→reserve→reconcile per chunk with descriptive operation strings"
    - "Per-chunk artifact _cost_usd / _provider_used stamping (underscore-prefix internal hint protocol)"
    - "Pricing table with stamped verified date (staleness visibility)"

key-files:
  created:
    - lib/chunked_analyzer.py
    - tests/unit/test_chunked_analyzer.py
    - tests/contracts/test_phase4_chunked_path.py
    - .planning/phases/04-chunking/deferred-items.md
  modified: []

key-decisions:
  - "Worker resolution precedence: arg > env VIDEO_CHUNK_WORKERS > default(4); clamp [1,8]; invalid env → default with WARNING (RESEARCH Pitfall 4)"
  - "cost_tracker.operation string uses Path(video_path).name (basename only) to avoid leaking filesystem paths into cost log (STRIDE T-04-17)"
  - "on_chunk_error='fail_fast' (default) reconciles the failing chunk's tracker entry with success=False before the raise unwinds"
  - "on_chunk_error='continue' + all chunks failed → RuntimeError('All chunks failed...') instead of empty merge (schema requires per-dimension fields)"
  - "Callback exceptions logged and swallowed — a bad caller callback must not kill an otherwise-healthy pool (RESEARCH Pattern 3)"
  - "Merger re-invoked with 'continue' survivors; chunking_metadata.failed_chunks attached post-merge using sorted(failed_idxs)"
  - "Open Question 1 resolved: cost_tracker group_id deferred to v2.1; descriptive operation string (chunked_analysis[chunk i/N of <video_name>]) is the correlation key for now"
  - "Open Question 4 resolved: single-chunk bypass cleanup delegated to cleanup_chunks sentinel guard — analyze_chunked always calls cleanup_chunks; the sentinel protects user's original file"

patterns-established:
  - "Orchestrator owns temp file lifecycle: chunker split → caller analyze → caller cleanup (try/finally) — chunker does NOT own post-split files"
  - "Cost tracker integration pattern: pre-submit estimate+reserve, post-completion reconcile with actual_usd from ToolResult.cost_usd"
  - "Pricing staleness visibility: _PRICING entries carry 'verified: YYYY-MM-DD' dates; module-level _PRICING_VERIFIED_AT constant"

requirements-completed:
  - CHUNK-03
  - CHUNK-06

# Metrics
duration: 7m
completed: 2026-04-17
---

# Phase 04 Plan 03: chunked_analyzer Summary

**ThreadPoolExecutor orchestrator wrapping split→analyze→merge with per-chunk cost_tracker correlation and try/finally cleanup that survives provider and merger exceptions.**

## Performance

- **Duration:** 7m (approx)
- **Started:** 2026-04-17T20:22:01Z
- **Completed:** 2026-04-17T20:28:40Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 4 created, 0 modified

## Accomplishments

- `lib/chunked_analyzer.py` — `analyze_chunked` + `estimate_chunked_cost` public API
- Bounded concurrency via `concurrent.futures.ThreadPoolExecutor` + `as_completed`, worker count resolved `arg > env VIDEO_CHUNK_WORKERS > 4`, clamped `[1, 8]` with invalid-env warning fallback
- Cleanup guaranteed via `try/finally` in `analyze_chunked` — provider exceptions, merger exceptions, and normal success paths all delete temp chunks while the bypass sentinel spares the user's original file
- Cost tracker integration: `estimate → reserve → reconcile` per chunk with descriptive `operation` strings (`chunked_analysis[chunk i/N of <basename>]`) for budget-log correlation; zero API changes to `tools/cost_tracker.py`
- Pricing table stamped `verified: '2026-04-17'` + module-level `_PRICING_VERIFIED_AT` so staleness is visible to future audits
- 34 unit tests + 4 contract tests (38 new) — all offline (subprocess mocked, no FFmpeg, no API keys)

## Task Commits

1. **Task 1+2: chunked_analyzer scaffold + TDD tests** — `a24f6d6` (feat: 34 unit tests covering worker resolution, thread pool dispatch, cleanup, cost estimation, cost tracker integration, error modes, artifact stamping, single-chunk bypass)
2. **Task 2: end-to-end contract test** — `816c6d0` (test: tests/contracts/test_phase4_chunked_path.py — 4 contract tests driving full split→analyze→merge path with StubProvider + real CostTracker)

_Note: Task 1 and Task 2 implementations shipped together in commit `a24f6d6` because the implementation-level tests (including cost tracker + error modes) were authored in the same TDD cycle; the commit message separates the concerns. The contract test landed in its own commit `816c6d0` to keep the end-to-end schema gate traceable._

## Files Created/Modified

| File | Lines | Role |
|------|-------|------|
| `lib/chunked_analyzer.py` | 490 | `analyze_chunked` + `estimate_chunked_cost` + `_resolve_workers` + `_analyze_chunks` + `_fire_callback` helpers; module-level `_PRICING` table |
| `tests/unit/test_chunked_analyzer.py` | 711 | 34 unit tests organized into 7 classes: `TestWorkerResolution`, `TestThreadPoolDispatch`, `TestCleanup`, `TestEstimateChunkedCost`, `TestCostTrackerIntegration`, `TestErrorModes`, `TestArtifactStamping`, `TestSingleChunkBypass` |
| `tests/contracts/test_phase4_chunked_path.py` | 184 | 4 contract tests: multi-chunk end-to-end, cost tracker integration with real `CostTracker(OBSERVE)`, cleanup invocation, single-chunk bypass end-to-end |
| `.planning/phases/04-chunking/deferred-items.md` | 15 | Logs 3 pre-existing unrelated `fc-list` failures in code-snippet tests (not Phase 4 scope) |

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Worker resolution clamp `[1, 8]` enforced AFTER env parse (so env="50" clamps to 8, not falls back to default) | Distinguishes "unparseable" (fallback) from "out-of-range" (clamp) — matches RESEARCH Pitfall 4 phrasing |
| `on_chunk_error='fail_fast'` reconciles the failing chunk's tracker entry with `success=False, actual_usd=0.0` before the raise unwinds | Budget log stays consistent even when caller aborts the run; the unreserved reserve would otherwise stay hanging |
| When `tool_result.model` is `None`, `_provider_used` falls back to `provider_tool.provider` (not `provider_tool.name`) | `.provider` is the stable provider-family identifier used by the merger's `chunking_metadata.provider`; `.name` would leak the tool instance name |
| `cleanup_chunks` exception wrapped in its own try/except inside the finally | The finally MUST NOT swallow the merger's exception by re-raising a cleanup error; `cleanup_chunks` already swallows internally, but defense-in-depth |
| StubProvider.provider = `"gemini"` in tests (not `"stub"`) | `chunking_metadata.provider` schema enum is `{"gemini","openrouter"}`; using `"gemini"` lets merged artifacts validate end-to-end without schema-amendment scope creep |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Schema enum restricts `chunking_metadata.provider` to `{"gemini","openrouter"}`**

- **Found during:** Task 1 — running the first `TestThreadPoolDispatch::test_executor_submits_per_chunk` test
- **Issue:** Initial `StubProvider.provider = "stub"` caused the merger's `validate_artifact` to reject the merged output (`'stub' is not one of ['gemini','openrouter']`), blocking all downstream tests that assert a valid returned artifact
- **Fix:** Changed `StubProvider.provider = "gemini"` in both `tests/unit/test_chunked_analyzer.py` and `tests/contracts/test_phase4_chunked_path.py`. Documented the reason inline so future contributors understand it's a schema-enum constraint, not an arbitrary stub value. Corresponding `test_provider_used_falls_back_to_provider_name_when_model_none` assertion updated to expect `"gemini"` (the new stub provider string)
- **Files modified:** `tests/unit/test_chunked_analyzer.py`
- **Verification:** All 38 tests green; no schema changes needed
- **Committed in:** `a24f6d6` (shipped with Task 1)

---

**Total deviations:** 1 auto-fixed (1 blocking — schema-enum constraint in test fixture)
**Impact on plan:** Zero scope change — test fixture uses a legal enum value instead of a schema-violating placeholder. Production code behavior unaffected.

## Issues Encountered

None. All tests passed on first green run after the schema-enum fix.

## Open-Question Resolutions

| RESEARCH Open Question | Resolution |
|------------------------|-----------|
| #1 — Should `cost_tracker` gain `group_id` for per-run correlation? | **Deferred to v2.1.** Current implementation uses descriptive `operation` strings — `chunked_analysis[chunk i/N of <video_name>]` — as the correlation key. No `cost_tracker.py` modification needed. Grep-able from `cost_log.json` per video. |
| #4 — How does `analyze_chunked` avoid deleting the user's original file in single-chunk bypass? | **Resolved via cleanup sentinel.** `analyze_chunked` always calls `cleanup_chunks(chunks, original_path=video_path_str)` — `cleanup_chunks` itself inspects each chunk's `local_path` against `original_path` and skips the bypass sentinel (Plan 01 implementation, test `test_single_chunk_bypass_cleanup_spares_original`). No conditional in `analyze_chunked` needed. |

## Pricing-Verification Date

**2026-04-17** — `_PRICING_VERIFIED_AT` module constant + `verified:` date stamped on every `_PRICING` table entry. Future audits: `grep -rn 'verified.*2026' lib/chunked_analyzer.py` to spot staleness.

## User Setup Required

None — all Phase 4 code is offline-testable (subprocess mocked, no API key requirement). Integration testing requires FFmpeg + provider API key, gated by `RUN_INTEGRATION_TESTS=1` in Phase 7.

## Next Phase Readiness

- **Phase 6 (reference-synthesis meta skill)** — `analyze_chunked` is the function the meta skill will call. Callback shape `(int, ToolResult) -> None` is stable; pass-through from `provider_tool.execute` is provider-agnostic (works with `video_analyzer_selector` OR a concrete provider tool).
- **Phase 7 (integration tests)** — Contract test `tests/contracts/test_phase4_chunked_path.py` is the offline gate. Phase 7 integration variant must require real ffmpeg on the host and `GEMINI_API_KEY`/`OPENROUTER_API_KEY` via the `RUN_INTEGRATION_TESTS=1` env gate.
- **No blockers.** Full Phase 4 suite (123 tests across video_chunker + analysis_merger + chunked_analyzer + phase4 contract) green on `main@816c6d0`.

## Self-Check: PASSED

**Files claimed → verified:**
- `/workspace/lib/chunked_analyzer.py` — FOUND (490 lines)
- `/workspace/tests/unit/test_chunked_analyzer.py` — FOUND (711 lines)
- `/workspace/tests/contracts/test_phase4_chunked_path.py` — FOUND (184 lines)
- `/workspace/.planning/phases/04-chunking/deferred-items.md` — FOUND (15 lines)

**Commits claimed → verified:**
- `a24f6d6` — FOUND (feat: scaffold chunked_analyzer)
- `816c6d0` — FOUND (test: end-to-end contract test)

**Test counts verified:**
- `tests/unit/test_chunked_analyzer.py`: 34 tests (all pass)
- `tests/contracts/test_phase4_chunked_path.py`: 4 tests (all pass)
- Full Phase 4 suite: 123 tests (video_chunker + analysis_merger + chunked_analyzer + contract)

**Verification commands verified:**
- `grep -nE "ThreadPoolExecutor|as_completed" lib/chunked_analyzer.py` → both present (7 matches)
- `grep -cE "pricing_verified_at|verified.*2026" lib/chunked_analyzer.py` → 7 (≥2 required)
- No actual `write_checkpoint(` call in `lib/chunked_analyzer.py` (only a docstring negation note)
- `python3 -c "from lib.chunked_analyzer import analyze_chunked, estimate_chunked_cost; r=estimate_chunked_cost('gemini', 600, 'gemini-3.1-pro-preview'); assert r['chunk_count']==2 and r['total_usd']>0"` → OK (total_usd=0.3516)

---

*Phase: 04-chunking*
*Completed: 2026-04-17*
