---
phase: 02
fixed_at: 2026-04-17
review_path: .planning/phases/02-gemini-provider/02-REVIEW.md
iteration: 1
findings_in_scope: 7
fixes_applied: 7
fixed: 7
skipped: 0
tests_passing: true
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-04-17
**Source review:** `.planning/phases/02-gemini-provider/02-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (2 High + 5 Medium)
- Fixed: 7
- Skipped: 0
- Low + Nit findings deferred to Phase 6 cleanup (per user instruction)

## Fix Table

| Finding ID | Severity | Status | Commit |
|------------|----------|--------|--------|
| HI-01 | High   | fixed  | `f446d21` |
| HI-02 | High   | fixed  | `739aa51` |
| MD-01 | Medium | fixed  | `d6bbdf9` |
| MD-02 | Medium | fixed  | `653ad60` |
| MD-03 | Medium | fixed  | `5fb1508` |
| MD-04 | Medium | fixed  | `be66e0f` |
| MD-05 | Medium | fixed  | `42bfc45` |

## Deferred (out of scope — Phase 6 cleanup)

| Finding ID | Severity | Status |
|------------|----------|--------|
| LO-01 | Low | deferred |
| LO-02 | Low | deferred |
| LO-03 | Low | deferred |
| LO-04 | Low | deferred |
| NI-01 | Nit | deferred |
| NI-02 | Nit | deferred |
| NI-03 | Nit | deferred |

## Fixed Issues

### HI-01: Unmapped exceptions from `client.files.upload()` skip the `VideoUploadError` taxonomy

**File modified:** `tools/analysis/gemini_video_analyzer.py`
**Commit:** `f446d21`
**Applied fix:** Wrapped `client.files.upload(file=str(video_path))` in `try/except errors.APIError` that re-raises as `VideoUploadError("Files API upload failed: ...") from exc`. The new `VideoUploadError` is still caught by the existing outer `except (VideoUploadError, VideoAnalysisError)` handler, preserving behavior while honoring the documented taxonomy.

### HI-02: Fallback-model branch does not catch `errors.ClientError`

**File modified:** `tools/analysis/gemini_video_analyzer.py`
**Commit:** `739aa51`
**Applied fix:** Added `except errors.ClientError as exc` clause in the fallback-model branch (full-depth attempt) of `_analyze_with_fallback`. Raises `VideoAnalysisRetryExhausted(f"Both preview and fallback model ({model}) unavailable: {exc}") from exc`. Since `VideoAnalysisRetryExhausted` extends `VideoAnalysisError`, the outer `execute()` handler catches it and returns a descriptive `ToolResult`.

### MD-01: Class-body `_FLAT_SCHEMA` runs at module import

**File modified:** `tools/analysis/gemini_video_analyzer.py`
**Commit:** `d6bbdf9`
**Applied fix:** Replaced class-body `_FLAT_SCHEMA = to_api_schema(load_schema("video_analysis"))` with `_FLAT_SCHEMA: dict | None = None` plus a `_flat_schema()` classmethod that lazily computes and caches the flattened schema on first access. Updated the one call site in `_run_once` to use `self._flat_schema()`. No test updates needed — tests read the schema via `config.response_json_schema` and `to_api_schema(load_schema(...))`, not via `_FLAT_SCHEMA` directly.

### MD-02: MAX_TOKENS with near-complete text discarded (by spec, but undocumented)

**File modified:** `tools/analysis/gemini_video_analyzer.py`
**Commit:** `653ad60`
**Applied fix:** Added a pinning comment above the `finish_reason == types.FinishReason.MAX_TOKENS` check in `_run_once` documenting that MAX_TOKENS always retries, even if `response.text` is parseable, because the JSON is almost certainly missing a trailing `}` or `"confidence"` key and the compact retry is cheaper than guessing.

### MD-03: Bare `except Exception` on `genai.Client(api_key=key)` masks SDK bugs

**File modified:** `tools/analysis/gemini_video_analyzer.py`
**Commit:** `5fb1508`
**Applied fix:** Replaced `except Exception as exc` with `except errors.APIError as exc`. `TypeError`/`ImportError` from future SDK changes now propagate as real errors rather than being masked as an "auth issue". Comment updated to document the intent.

### MD-04: `_wait_for_active` has no upper bound on `max_poll_seconds`

**File modified:** `tools/analysis/gemini_video_analyzer.py`
**Commit:** `be66e0f`
**Applied fix:** In `execute()`, wrapped `float(max_poll_seconds)` in try/except to catch `TypeError`/`ValueError` (falling back to `DEFAULT_MAX_POLL_SECONDS`), then clamped the result to `[1.0, 1800.0]` so pathological inputs (e.g., `max_poll_seconds=999999`) cannot pin the process for ~11 days. Also added `"minimum": 1, "maximum": 1800` to the `max_poll_seconds` entry in `input_schema` so schema-level validation catches out-of-range inputs up front.

### MD-05: Selector silently ignores unknown `preferred_provider` names

**File modified:** `tools/analysis/video_analyzer_selector.py`
**Commit:** `42bfc45`
**Applied fix:** In `_pick`, when `preferred != "auto"` and no match is found in `by_provider` or tool names, now returns `None` explicitly rather than falling through to the env-var and API-key-presence logic. The caller (`execute()`) surfaces this as `"No available video_analysis provider..."` error instead of silently routing to whichever backend happens to have a key set.

## Test Results

Full Phase 2 test suite (unit + contracts) with no API keys in env:

```bash
unset GEMINI_API_KEY GOOGLE_API_KEY OPENROUTER_API_KEY
pytest tests/unit/test_gemini_video_analyzer.py tests/contracts/test_phase2_gemini_contracts.py -q
```

**Result:** `37 passed in 1.84s` — no regressions.

## Deviations from planned fix

None. All 7 in-scope fixes applied exactly as prescribed in `02-REVIEW.md` (with the small MD-01 nuance that no test updates were required — existing tests read the schema through the public config surface, not `_FLAT_SCHEMA` directly).

## Notes on excluded findings

Per explicit user instruction, `LO-01..04` and `NI-01..03` remain in `02-REVIEW.md` for Phase 6 cleanup and were NOT touched in this iteration. In particular:

- **LO-01** (`test_api_key_value_not_in_any_error` is a no-op) still uses `RuntimeError` as the upload side effect. The HI-01 narrowing (`except errors.APIError`) does NOT catch `RuntimeError`, so the test's existing `try/except RuntimeError: return` branch still fires — the test remains functionally a no-op, consistent with the pre-fix behavior. Phase 6 will tighten it by switching the side effect to `errors.APIError`.

---

_Fixed: 2026-04-17_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
