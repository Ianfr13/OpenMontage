---
phase: 08-openrouter-provider-hardening
plan: 01
subsystem: analysis
tags: [openrouter, openai-sdk, error-taxonomy, video-analysis, hi-01, clean-01]

# Dependency graph
requires:
  - phase: 03-openrouter-provider (v2.0, archived)
    provides: _run_once / _analyze_with_fallback / execute() ladder and the VideoAnalysisError taxonomy that this plan narrows
provides:
  - VideoAnalysisAuthError sentinel (401/403 fast-fail class) in lib/analysis_errors.py
  - VideoAnalysisRateLimitError sentinel (429 fast-fail class) in lib/analysis_errors.py
  - Narrowed except chain in openrouter_video_analyzer._run_once that re-raises 401/403/429 as sentinels BEFORE the generic APIError handler
  - isinstance guards in _analyze_with_fallback that propagate the sentinels without invoking compact retry
  - Dedicated except branch in execute() placed BEFORE the generic VideoAnalysisError handler
  - 4 unit tests proving exactly-one-create-call for each SDK sentinel and still-retries for generic APIError
affects:
  - 09-chunked-merge (inherits the same error taxonomy when it wires video_chunker into the analyzer)
  - 12-human-uat (fixture-review flow now surfaces real root cause on bad key instead of "retry exhausted")

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sentinel-subclass fast-fail: subclass the shared error to carry retry policy; isinstance guard in retry drivers re-raises the sentinel"
    - "Python except-ordering contract: sentinel branch MUST appear before its superclass branch, enforced by grep guard on line-number ordering"

key-files:
  created: []
  modified:
    - "lib/analysis_errors.py — added VideoAnalysisAuthError (lines 59-68) and VideoAnalysisRateLimitError (lines 71-78)"
    - "tools/analysis/openrouter_video_analyzer.py — narrow except at lines 364-390; 4 isinstance guards in _analyze_with_fallback (lines 471, 488, 504, 518); fast-fail except branch in execute() at line 604"
    - "tests/unit/test_openrouter_video_analyzer.py — 4 new HI-01 tests (lines 438-491) + openai SDK imports expanded"

key-decisions:
  - "Added isinstance guard at BOTH the inner and outer except sites in each of the two VideoAnalysisError handlers in _analyze_with_fallback (4 guards total vs plan's minimum 3). Defensive: if a future edit inlines a bare `raise` into a nested try, the outer guard still catches the sentinel before it reaches the VideoAnalysisRetryExhausted wrapper."
  - "execute() sentinel branch returns str(exc) — the sentinel already carries a formatted message (`OpenRouter authentication failed: ...`) so no additional prefix is needed. Matches the generic VideoAnalysisError branch's behavior for consistency."

patterns-established:
  - "Sentinel subclass fast-fail for non-retriable SDK exceptions: the sentinel crosses the retry boundary via isinstance guard in the retry driver AND via explicit except branch at execute() — belt and suspenders."
  - "Exception hierarchy ordering: because Python matches the first satisfied except clause, every sentinel subclass branch MUST appear lexically before its superclass branch. Tested via grep line-number ordering."

requirements-completed: [CLEAN-01]

# Metrics
duration: ~30min
completed: 2026-04-18
---

# Phase 8 Plan 1: OpenRouter Auth/Permission/Rate-Limit Fast-Fail Summary

**Narrowed `_run_once` except chain so 401/403/429 raise sentinel subclasses that bypass the compact-retry ladder; four new tests prove exactly-one-create-call and preserved retry semantics for generic APIError.**

## Performance

- **Duration:** ~30 min (first commit 2026-04-18T00:35:21Z, final commit 2026-04-18T00:36:42Z — test-run + summary-write time dominates)
- **Started:** 2026-04-18T00:33Z (plan load)
- **Completed:** 2026-04-18T00:37Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Wasted paid retry eliminated on the most common misconfiguration failure mode (bad OPENROUTER_API_KEY). `AuthenticationError` now surfaces verbatim in ~1 API call instead of masquerading as `VideoAnalysisRetryExhausted` after 2 calls.
- Rate-limit amplification closed: 429 no longer re-fires the compact ladder, which would have compounded the rate-limit against OpenRouter.
- Generic `APIError` retry semantics preserved and guarded by a dedicated regression test, so the narrow fix cannot silently break `APITimeoutError` / other transient-class retry eligibility.
- Full suite delta: 621 → 625 passing (+4), 13 skipped, 3 pre-existing fc-list failures unchanged.

## Task Commits

Each task committed atomically (--no-verify per parallel executor protocol):

1. **Task 1: Add sentinel exception classes and narrow _run_once + _analyze_with_fallback + execute()** — `6655a8f` (feat)
2. **Task 2: Add four unit tests proving AuthenticationError / PermissionDeniedError / RateLimitError fast-fail and generic APIError still retries** — `3810058` (test)

## Files Created/Modified

- `lib/analysis_errors.py` — Added `VideoAnalysisAuthError` (401/403) and `VideoAnalysisRateLimitError` (429) sentinel subclasses of `VideoAnalysisError`, both with docstrings referencing Phase 8 CLEAN-01 / v2.0 Phase 3 REVIEW HI-01.
- `tools/analysis/openrouter_video_analyzer.py`
  - Extended `openai` imports to include `AuthenticationError`, `PermissionDeniedError`, `RateLimitError`.
  - Extended `lib.analysis_errors` imports to include the two new sentinels.
  - `_run_once` (lines 364-390): three narrow except clauses for 401/403/429 raise the sentinels BEFORE the generic `except APIError` (which still wraps `APITimeoutError` and other transient APIError subclasses to `VideoAnalysisError`, status quo).
  - `_analyze_with_fallback` (lines 470-523): isinstance guard at each of the four `except VideoAnalysisError` handlers — the two sentinel classes bypass compact retry and propagate up.
  - `execute()` (line 604): new `except (VideoAnalysisAuthError, VideoAnalysisRateLimitError)` branch placed BEFORE the generic `except (VideoAnalysisError, VideoAnalysisRetryExhausted)` branch (ordering enforced by Python first-match semantics).
- `tests/unit/test_openrouter_video_analyzer.py`
  - Expanded `from openai import` to add `AuthenticationError`, `PermissionDeniedError`, `RateLimitError` (single combined statement, alphabetical).
  - Added helpers `_auth_error` / `_permission_error` / `_rate_limit_error` that build valid SDK exceptions with `httpx.Response` objects for 401/403/429 (same shape as the existing `_bad_request` helper).
  - Added 4 tests under `# HI-01 — Auth / permission / rate-limit fast-fail (CLEAN-01)`:
    - `test_authentication_error_surfaces_without_retry` — call_count == 1, error mentions "auth" / "authentication", no "retry exhausted"
    - `test_permission_denied_error_surfaces_without_retry` — call_count == 1, error mentions "permission", no "retry exhausted"
    - `test_rate_limit_error_surfaces_without_retry` — call_count == 1, error mentions "rate", no "retry exhausted"
    - `test_generic_apierror_still_retries_compact` — a bare `APIError` (no 401/403/429 subclass) still fires the compact-retry ladder; call_count >= 2

## Before/After Exception Flow

**Before (Phase 3 shipped behavior):**
```
client.chat.completions.create(...) raises AuthenticationError(401)
  -> _run_once catches via `except APIError`
  -> re-raised as VideoAnalysisError("OpenRouter API error: ...")
  -> _analyze_with_fallback catches VideoAnalysisError
  -> runs structured+compact retry
  -> second create() call ALSO raises AuthenticationError(401)
  -> re-raised as VideoAnalysisError again
  -> wrapped as VideoAnalysisRetryExhausted
  -> execute() returns ToolResult(success=False, error="Analysis failed after structured+compact retry: ...")
```
Net: 2 paid API calls, root cause masked by "retry exhausted" wording.

**After (this plan):**
```
client.chat.completions.create(...) raises AuthenticationError(401)
  -> _run_once catches via `except AuthenticationError` (BEFORE `except APIError`)
  -> raised as VideoAnalysisAuthError("OpenRouter authentication failed: ...")
  -> _analyze_with_fallback's `except VideoAnalysisError` catches it
  -> isinstance guard sees VideoAnalysisAuthError subclass -> re-raises verbatim
  -> execute()'s `except (VideoAnalysisAuthError, VideoAnalysisRateLimitError)` catches BEFORE the generic branch
  -> returns ToolResult(success=False, error="OpenRouter authentication failed: ...")
```
Net: 1 paid API call, verbatim root cause in `.error`.

Identical flow for `PermissionDeniedError(403)` → `VideoAnalysisAuthError("OpenRouter permission denied: ...")` and `RateLimitError(429)` → `VideoAnalysisRateLimitError("OpenRouter rate-limited: ...")`.

Generic `APIError` subclasses (including `APITimeoutError`) still flow through the existing path: `except APIError` → `VideoAnalysisError("OpenRouter API error: ...")` → compact-retry ladder → `VideoAnalysisRetryExhausted` on terminal failure. This preserves the retry-eligible behavior for transient-class faults.

## Test Coverage Mapping

| Test ID | CLEAN-01 criterion | Coverage |
|---------|--------------------|----------|
| `test_authentication_error_surfaces_without_retry` | 401 fast-fails | create() call_count == 1; error mentions "auth"; no "retry exhausted" |
| `test_permission_denied_error_surfaces_without_retry` | 403 fast-fails | create() call_count == 1; error mentions "permission"; no "retry exhausted" |
| `test_rate_limit_error_surfaces_without_retry` | 429 fast-fails | create() call_count == 1; error mentions "rate"; no "retry exhausted" |
| `test_generic_apierror_still_retries_compact` | Regression guard: non-sentinel APIError keeps retry behavior | call_count >= 2 on bare APIError |

## Suite Count Delta

| Stage | Passed | Skipped | Failed (pre-existing) | Total |
|-------|--------|---------|-----------------------|-------|
| Baseline (before plan 08-01) | 621 | 13 | 3 (fc-list) | 637 |
| After Task 1 (code only, no new tests) | 621 | 13 | 3 (fc-list) | 637 |
| After Task 2 (+4 HI-01 tests) | **625** | 13 | 3 (fc-list) | 641 |
| Net delta | +4 | 0 | 0 | +4 |

`tests/unit/test_openrouter_video_analyzer.py` specifically: 30 → 34 (+4).

## Decisions Made

- **Added isinstance guards at both inner AND outer except sites of each VideoAnalysisError handler** (4 total vs plan's minimum 3). Defensive — if a future edit introduces a nested try that wraps a sentinel, the outer guard still propagates it without a `VideoAnalysisRetryExhausted` wrap. The plan's acceptance criteria allowed `>= 3`; the final count is 4. No behavior change vs 3 guards on the current test matrix.
- **`execute()` sentinel branch returns `str(exc)` directly** rather than prefixing with "OpenRouter fast-fail:" or similar. The sentinel message already includes the provider context (`"OpenRouter authentication failed: ..."`), and doubling the prefix would look odd in the `ToolResult.error`. Matches the generic handler's behavior for consistency.

## Deviations from Plan

None — plan executed exactly as written.

- Task 1 implementation matches the plan's Step A/B sequence verbatim, with the one additive choice noted in "Decisions Made" (4 isinstance guards vs the plan's 3-minimum).
- Task 2 added the 4 tests in the specified section with the exact helper shapes the plan prescribed.
- No Rule 1/2/3 auto-fixes were needed — no bugs surfaced during execution, no missing critical functionality discovered beyond the plan scope, no blocking issues encountered.
- No Rule 4 architectural questions arose.

## Issues Encountered

None.

## Authentication Gates

None — this plan did not require any external auth (tests use mocked `openai` SDK; no real OPENROUTER_API_KEY used).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Phase 8 Plan 2 (CLEAN-02..04):** ready to start on the same analyzer file (100MB cap, explicit MIME whitelist, OPENROUTER_BASE_URL dedup). Error-taxonomy work is isolated from those surfaces.
- **Phase 9 (chunked merge) readiness:** the analyzer's error contract is now clearer — downstream merger code can pattern-match `VideoAnalysisAuthError` / `VideoAnalysisRateLimitError` to decide whether to abort the whole chunk batch vs retry just one chunk. No changes needed in Phase 9 scope but the taxonomy is more useful.
- **Threat flags:** none. The change narrows error surface (better secret-hygiene by re-raising the SDK exception unmodified inside `raise ... from exc`) and does not introduce any new network path, auth path, schema boundary, or file-access surface.

## Self-Check: PASSED

Verified claims before finalization:

- `[ -f lib/analysis_errors.py ]` — FOUND (modified)
- `[ -f tools/analysis/openrouter_video_analyzer.py ]` — FOUND (modified)
- `[ -f tests/unit/test_openrouter_video_analyzer.py ]` — FOUND (modified)
- Commit `6655a8f` (Task 1) — FOUND via `git log --oneline -5`
- Commit `3810058` (Task 2) — FOUND via `git log --oneline -5`
- `grep -c "class VideoAnalysisAuthError" lib/analysis_errors.py` → 1 (required 1)
- `grep -c "class VideoAnalysisRateLimitError" lib/analysis_errors.py` → 1 (required 1)
- `grep -c "VideoAnalysisAuthError" tools/analysis/openrouter_video_analyzer.py` → 8 (required >= 4)
- `grep -c "VideoAnalysisRateLimitError" tools/analysis/openrouter_video_analyzer.py` → 7 (required >= 3)
- `grep -c "isinstance(exc, (VideoAnalysisAuthError, VideoAnalysisRateLimitError))" tools/analysis/openrouter_video_analyzer.py` → 4 (required 3; see decision note — defensive)
- `except (VideoAnalysisAuthError, VideoAnalysisRateLimitError)` appears at line 604; generic `except (VideoAnalysisError, VideoAnalysisRetryExhausted)` at line 609 — sentinel branch first (required)
- 4 new test functions defined (required 4)
- `python3 -m pytest tests/unit/test_openrouter_video_analyzer.py -q` → 34 passed (was 30 baseline, +4)
- `python3 -m pytest tests/ --ignore=tests/qa -q` → 625 passed / 13 skipped / 3 failed (pre-existing fc-list) — target 625 met
- Python import sanity: `from tools.analysis.openrouter_video_analyzer import OpenRouterVideoAnalyzer` exits 0
- Sentinel subclass sanity: `issubclass(VideoAnalysisAuthError, VideoAnalysisError)` and `issubclass(VideoAnalysisRateLimitError, VideoAnalysisError)` both True

---
*Phase: 08-openrouter-provider-hardening*
*Completed: 2026-04-18*
