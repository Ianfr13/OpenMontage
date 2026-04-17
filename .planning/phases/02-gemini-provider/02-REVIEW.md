---
phase: 02
reviewed: 2026-04-17
status: findings
findings_count:
  blocker: 0
  high: 2
  medium: 5
  low: 4
  nit: 3
---

# Phase 2: Code Review Report

## Summary

Phase 2 ships a credible, well-tested first end-to-end `video_analysis` path. RESEARCH pitfalls 1-6 are all correctly addressed: explicit `api_key=` passed to `genai.Client`, `time.monotonic` for polling, no `lib.checkpoint` import, `finally`-delete on the uploaded file, truncation detection (MAX_TOKENS + empty text), and preview→`gemini-2.5-pro` fallback on `errors.ClientError`. Security posture solid: no hardcoded keys, key value never interpolated into error strings, contract test polices invariants.

The gaps that matter: (1) the fallback ladder has a semantic asymmetry — `ClientError` raised during compact retry is treated as "preview unavailable" even if transient, and a `ClientError` on the fallback-model full attempt is NOT caught; (2) upload-time exceptions from the SDK are not mapped to `VideoUploadError`. Rest are quality smells: per-instance schema flattening at import, no clamping on `max_poll_seconds`, selector silently ignores unknown `preferred_provider` names.

## High

### HI-01 — Unmapped exceptions from `client.files.upload()` skip the `VideoUploadError` taxonomy
**File:** `tools/analysis/gemini_video_analyzer.py:396`
**Issue:** The module docstring and `VideoUploadError` docstring promise upload-time failures use `VideoUploadError`, but only the polling path raises it. Upload failures surface as generic `errors.APIError`.
**Fix:**
```python
try:
    uploaded = client.files.upload(file=str(video_path))
except errors.APIError as exc:
    raise VideoUploadError(f"Files API upload failed: {exc}") from exc
```

### HI-02 — Fallback-model branch does not catch `errors.ClientError`
**File:** `tools/analysis/gemini_video_analyzer.py:349-362`
**Issue:** If `gemini-2.5-pro` also 4xx's, `errors.ClientError` bubbles up uncaught and only the outer `errors.APIError` handler catches it. Caller sees generic message with no model context; `ToolResult.model` is misleading.
**Fix:**
```python
try:
    return self._run_once(client, file_ref, prompt, model), model
except errors.ClientError as exc:
    raise VideoAnalysisRetryExhausted(
        f"Both preview and fallback model ({model}) unavailable: {exc}"
    ) from exc
except VideoAnalysisError:
    ...
```

## Medium

### MD-01 — Class-body `_FLAT_SCHEMA = to_api_schema(load_schema(...))` runs at module import
**File:** `tools/analysis/gemini_video_analyzer.py:173`
**Issue:** Executes schema flattening every import — even for callers that only read the file. Errors in `load_schema` become `ImportError`, breaking the tools package.
**Fix:** Lazy cached classmethod:
```python
_FLAT_SCHEMA: dict | None = None

@classmethod
def _flat_schema(cls) -> dict:
    if cls._FLAT_SCHEMA is None:
        cls._FLAT_SCHEMA = to_api_schema(load_schema("video_analysis"))
    return cls._FLAT_SCHEMA
```

### MD-02 — MAX_TOKENS with near-complete text is discarded (by spec, but undocumented)
**File:** `tools/analysis/gemini_video_analyzer.py:279-285`
**Issue:** MAX_TOKENS responses often contain nearly-complete JSON. Current behavior retries unconditionally. If intentional, add a pinning comment.
**Fix:** Add comment at line 279 documenting the decision.

### MD-03 — Bare `except Exception` on `genai.Client(api_key=key)` masks SDK bugs
**File:** `tools/analysis/gemini_video_analyzer.py:382-387`
**Issue:** A `TypeError`/`ImportError` from a future SDK upgrade reports as "auth issue" and swallows the stack.
**Fix:** Narrow to `errors.APIError`:
```python
try:
    client = genai.Client(api_key=key)
except errors.APIError as exc:
    return ToolResult(success=False, error=f"Gemini client init failed: {exc}")
```

### MD-04 — `_wait_for_active` has no upper bound on `max_poll_seconds`
**File:** `tools/analysis/gemini_video_analyzer.py:389-391, 114-141`
**Issue:** Caller-supplied `max_poll_seconds=999999` pins process ~11 days. `float()` raises `ValueError` on garbage input, uncaught.
**Fix:** Clamp [1.0, 1800.0]; add `"minimum": 1, "maximum": 1800` to input_schema.

### MD-05 — Selector silently ignores unknown `preferred_provider` names
**File:** `tools/analysis/video_analyzer_selector.py:132-139`
**Issue:** `preferred_provider="openrouter"` (pre-Phase-3) falls through to env-var logic and picks whichever provider has a key set. Contract footgun.
**Fix:** Return `None` / error ToolResult if explicit name has no match.

## Low

### LO-01 — `test_api_key_value_not_in_any_error` is effectively a no-op
**File:** `tests/unit/test_gemini_video_analyzer.py:409-421`
**Issue:** Uses `RuntimeError` side_effect which has no handler; exception propagates out and `try/except RuntimeError: return` silently passes without asserting.
**Fix:** Use `errors.APIError` which routes through `execute()`'s error handling.

### LO-02 — `_analyze_with_fallback` duplicates `compact_prompt` construction
**File:** `tools/analysis/gemini_video_analyzer.py:327, 353`
**Fix:** Hoist `compact_prompt = self._build_prompt(inputs, depth="compact")` to top of method.

### LO-03 — `_state_value` edge case on empty-string `state`
**File:** `tools/analysis/gemini_video_analyzer.py:75-81`
**Issue:** Returns `""` which neither equals `ACTIVE` nor `FAILED`; polling continues to timeout with confusing "last state=" diagnostic.
**Fix:** `return value or "STATE_UNSPECIFIED"`.

### LO-04 — SKILL.md confidence-map prose inconsistency
**File:** `.agents/skills/gemini-video-analysis/SKILL.md:156`
**Issue:** Juxtaposing `"music_tempo_bpm": "medium"` (confidence value) with `music_tempo_bpm: number | null` (payload value type) could confuse readers.
**Fix:** One-line clarification on line 149.

## Nit

### NI-01 — Model string hardcoded in 3 places (tool constant + 2 SKILL.md mentions)
No drift test — low priority.

### NI-02 — `_normalize_shot_boundaries` drops malformed entries without `logger.debug`
Document-only fix.

### NI-03 — Selector's `max_poll_seconds` default duplicates provider default
Drift risk if one updated. Remove from selector schema or add drift assertion.

---

## Files reviewed

- `/workspace/lib/analysis_errors.py`
- `/workspace/tools/analysis/video_analyzer_selector.py`
- `/workspace/tools/analysis/gemini_video_analyzer.py`
- `/workspace/.agents/skills/gemini-video-analysis/SKILL.md`
- `/workspace/requirements.txt`
- `/workspace/tests/unit/conftest.py`
- `/workspace/tests/unit/test_gemini_video_analyzer.py`
- `/workspace/tests/contracts/test_phase2_gemini_contracts.py`

No blockers. Ship after addressing HI-01 and HI-02; medium/low items can go into next phase's cleanup.
