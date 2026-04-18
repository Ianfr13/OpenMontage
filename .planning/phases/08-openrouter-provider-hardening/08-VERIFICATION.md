---
phase: 08-openrouter-provider-hardening
verified: 2026-04-17T00:00:00Z
status: passed
score: 13/13 must-haves verified
overrides_applied: 0
---

# Phase 8: OpenRouter Provider Hardening Verification Report

**Phase Goal:** Harden the OpenRouter video analyzer so auth/rate errors fail fast, payload sizing matches the chunking contract, MIME detection is explicit, and config is deduplicated.
**Verified:** 2026-04-17
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Merged from ROADMAP success criteria + PLAN frontmatter must-haves. Deduplicated where PLAN truths restate roadmap SCs.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `_run_once` re-raises `AuthenticationError`, `PermissionDeniedError`, and `RateLimitError` without calling `_analyze_with_fallback` (no compact retry on 401/403/429) — ROADMAP SC1 / CLEAN-01 | VERIFIED | `tools/analysis/openrouter_video_analyzer.py:386-405` three narrow `except` clauses raise `VideoAnalysisAuthError` / `VideoAnalysisRateLimitError` BEFORE the generic `except APIError` at line 406. `execute()` at line 629 catches the sentinels BEFORE the generic `VideoAnalysisError` branch at line 634. 4 isinstance guards in `_analyze_with_fallback` re-raise sentinels at every `except VideoAnalysisError` site (lines 493, 510, 526, 540). 3 unit tests (`test_authentication_error_surfaces_without_retry`, `test_permission_denied_error_surfaces_without_retry`, `test_rate_limit_error_surfaces_without_retry`) each assert `call_count == 1` and "retry exhausted" NOT in error. 1 guardrail test (`test_generic_apierror_still_retries_compact`) asserts generic APIError still triggers compact retry. All 4 passed in suite run. |
| 2 | `_build_data_url` (via size gate) rejects payloads above the lowered ~100MB cap; tests cover allow-path and reject-path above the new cap — ROADMAP SC2 / CLEAN-02 | VERIFIED | `HARD_MAX_UPLOAD_BYTES = 100 * 1024 * 1024` at line 78 (runtime-asserted: `python3 -c "... == 100 * 1024 * 1024"` returns True). Size gate at line 575 (`if size > max_upload`) rejects BEFORE `_build_data_url` call at line 598. Error message at lines 579-583 names "Phase 4 chunking" and "100 MB". Tests: `test_hard_max_upload_bytes_is_100mb` (value assertion), `test_oversize_above_hard_cap_rejected_before_encode` (reject-path, spies on `base64.b64encode` to prove no encoding), `test_oversize_at_hard_cap_boundary_allowed` (allow-path at exact cap). All passing. |
| 3 | `_guess_mime` returns `None` for any extension outside the explicit whitelist; parametrized test covers `.mp4/.mov/.webm/.mkv/.m4v` (allowed) vs `.exe/.txt/.bin/.pdf/.avi` (rejected) — ROADMAP SC3 / CLEAN-03 | VERIFIED | `_EXT_TO_MIME` dict at lines 92-98 with exactly 5 CONTEXT-spec entries. `_guess_mime` at line 138 uses `_EXT_TO_MIME.get(path.suffix.lower())` — returns `None` on miss. Runtime check: `_guess_mime(Path('x.bin'))` → `None`, `_guess_mime(Path('x.mp4'))` → `'video/mp4'`, `_guess_mime(Path('x.mkv'))` → `'video/x-matroska'`. Parametrized tests: `test_guess_mime_whitelist_allow` (6 cases incl. `.MP4` case-insensitivity), `test_guess_mime_whitelist_reject` (7 cases: `.bin`, `.pdf`, `.txt`, `.exe`, `.avi`, `.zip`, `no_extension`). End-to-end `test_execute_rejects_bin_and_pdf_before_api_call` confirms `execute()` gate with no `create()` call. |
| 4 | `grep -n '"https://openrouter.ai/api/v1"' tools/analysis/openrouter_video_analyzer.py` returns exactly one match (the `OPENROUTER_BASE_URL` constant definition); no call-site literals remain — ROADMAP SC4 / CLEAN-04 | VERIFIED | `grep -c "https://openrouter.ai/api/v1" tools/analysis/openrouter_video_analyzer.py` → `1` (only line 74: the constant definition). Call site at line 614 uses `base_url=OPENROUTER_BASE_URL`. Source-grep invariant enforced by new test `test_openrouter_base_url_literal_appears_exactly_once` which asserts `src.count('"https://openrouter.ai/api/v1"') == 1`. Existing `test_openai_client_base_url` updated to drop redundant literal assertion. |
| 5 | Full suite stays green: at least 621 baseline + Phase 8 tests, 13 skipped, 3 pre-existing fc-list failures unchanged — ROADMAP SC5 | VERIFIED | `python3 -m pytest tests/ --ignore=tests/qa -q` → `3 failed, 643 passed, 13 skipped in 20.39s`. The 3 failures are `TestCodeSnippetUnit::test_render_{python,with_title,different_themes}` in `tests/contracts/test_phase2_contracts.py`, all caused by `FileNotFoundError: [Errno 2] No such file or directory: 'fc-list'` — pre-existing per Plan 08-02 SUMMARY (verified on base commit `c99159e`). Suite count delta: baseline 621 → end-of-phase 643 (+22 new from plans 08-01 [+4] and 08-02 [+18]). Skipped count 13 unchanged. |
| 6 | `AuthenticationError`, `PermissionDeniedError`, `RateLimitError` surface immediately from `_run_once` without entering the `_analyze_with_fallback` ladder — PLAN 08-01 truth | VERIFIED | Narrow `except` clauses at lines 386-405 of `_run_once` re-raise as sentinels BEFORE the generic `except APIError` at line 406. Python first-match semantics guarantee sentinels are preferred. |
| 7 | No auth/permission/rate-limit failure produces `VideoAnalysisRetryExhausted` — PLAN 08-01 truth | VERIFIED | 4 isinstance guards (`isinstance(exc, (VideoAnalysisAuthError, VideoAnalysisRateLimitError))`) at every `except VideoAnalysisError` site in `_analyze_with_fallback` re-raise the sentinel BEFORE any `raise VideoAnalysisRetryExhausted(...) from exc` wrapping. Verified by `test_authentication_error_surfaces_without_retry` asserting `"retry exhausted" not in low`. |
| 8 | `APITimeoutError` still wraps to `VideoAnalysisError` (transient path) — NOT into the new sentinels — PLAN 08-01 truth | VERIFIED | Generic `except APIError as exc:` at line 406 of `_run_once` is the default wrapping branch for every APIError subclass not explicitly enumerated. `APITimeoutError` is NOT in the narrow list (only 401/403/429 are). Confirmed via code inspection + guardrail test `test_generic_apierror_still_retries_compact` which feeds a bare `APIError` and asserts `call_count >= 2` (compact retry fires). |
| 9 | Generic `APIError` subclasses still wrap to `VideoAnalysisError` so BadRequest / fallback ladder is unchanged — PLAN 08-01 truth | VERIFIED | Generic `except APIError` at line 406 preserves existing behavior. `BadRequestError` is handled by its own earlier `except BadRequestError:` clause at line 380 (re-raises for `_analyze_with_fallback` to trigger the prompt-embedded fallback). `test_bad_request_falls_back_to_prompt_embedded` (existing) still passes. |
| 10 | `HARD_MAX_UPLOAD_BYTES` is `100 * 1024 * 1024` (100 MB); any call passing `max_upload_bytes` above that clamps down to 100 MB — PLAN 08-02 truth | VERIFIED | Constant defined at line 78. `_clamp_max_upload` at line 124 uses `min(v, HARD_MAX_UPLOAD_BYTES)`. Existing `test_max_upload_clamp_huge` asserts `_clamp_max_upload(10**20) == HARD_MAX_UPLOAD_BYTES` (still passing — now clamps to 100 MB). New test `test_oversize_above_hard_cap_rejected_before_encode` passes `max_upload_bytes=200*1024*1024` (clamps down to 100 MB) and 100MB+1 byte file → rejection. |
| 11 | A video of size `HARD_MAX_UPLOAD_BYTES + 1` bytes is rejected BEFORE base64 encoding (no `create()`, no `b64encode`) with error that names chunking — PLAN 08-02 truth | VERIFIED | `test_oversize_above_hard_cap_rejected_before_encode` monkeypatches `base64.b64encode` with a `MagicMock(side_effect=base64.b64encode)` spy; creates a sparse file at `HARD_MAX_UPLOAD_BYTES + 1` bytes; asserts `result.success is False`, `"chunking" in low or "phase 4" in low`, `mock_openai.chat.completions.create.assert_not_called()`, `spy.assert_not_called()`. Error message at lines 579-583 explicitly includes "use Phase 4 chunking". |
| 12 | A `.bin`, `.pdf`, `.exe`, or `.txt` file is rejected BEFORE any `create()` call — fail-closed rather than the previous `video/mp4` fail-open default — PLAN 08-02 truth | VERIFIED | `_guess_mime` returns `None` for all 4 extensions (confirmed runtime). `execute()` MIME gate at line 587 (`if mime not in SUPPORTED_MIMES:`) rejects `None` (since `None not in SUPPORTED_MIMES`). `test_execute_rejects_bin_and_pdf_before_api_call` loops over `("evil.bin", "report.pdf", "notes.txt")`, asserts `result.success is False` for each, and asserts `mock_openai.chat.completions.create.assert_not_called()`. |
| 13 | `OPENROUTER_BASE_URL` is the single source of truth: the literal `"https://openrouter.ai/api/v1"` appears exactly ONCE in the source — PLAN 08-02 truth | VERIFIED | Same evidence as Truth 4. `grep -c` returns 1. Source-grep invariant now enforced by `test_openrouter_base_url_literal_appears_exactly_once`. |

**Score:** 13/13 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `lib/analysis_errors.py` | `VideoAnalysisAuthError` and `VideoAnalysisRateLimitError` sentinel subclasses of `VideoAnalysisError` | VERIFIED | Lines 59-68 (`VideoAnalysisAuthError`) and 71-78 (`VideoAnalysisRateLimitError`). Both subclass `VideoAnalysisError` (runtime-asserted via `issubclass`). Docstrings reference CLEAN-01 / HI-01. |
| `tools/analysis/openrouter_video_analyzer.py` (CLEAN-01) | Narrowed except chain in `_run_once` re-raising 401/403/429 as sentinels; explicit handler in `execute()` returning ToolResult without `_analyze_with_fallback` | VERIFIED | `_run_once` lines 386-405: three narrow except clauses BEFORE generic `except APIError` at line 406. `execute()` line 629: `except (VideoAnalysisAuthError, VideoAnalysisRateLimitError)` branch BEFORE generic `except (VideoAnalysisError, VideoAnalysisRetryExhausted)` at line 634. 4 isinstance guards in `_analyze_with_fallback`. |
| `tools/analysis/openrouter_video_analyzer.py` (CLEAN-02/03/04) | `HARD_MAX_UPLOAD_BYTES = 100 * 1024 * 1024`, `_EXT_TO_MIME` whitelist dict, `_guess_mime` returning None on miss, `OpenAI(base_url=OPENROUTER_BASE_URL)` | VERIFIED | Line 78 (constant). Lines 92-98 (`_EXT_TO_MIME` with 5 entries). Line 138 (`_guess_mime` returns `_EXT_TO_MIME.get(path.suffix.lower())`). Line 614 (client constructor with constant). Dead `import mimetypes` removed. |
| `tests/unit/test_openrouter_video_analyzer.py` | 4 CLEAN-01 tests + 3 CLEAN-02 tests + 2 parametrized + 1 e2e CLEAN-03 tests + 1 new + 1 updated CLEAN-04 tests | VERIFIED | All test function names present: `test_authentication_error_surfaces_without_retry`, `test_permission_denied_error_surfaces_without_retry`, `test_rate_limit_error_surfaces_without_retry`, `test_generic_apierror_still_retries_compact`, `test_hard_max_upload_bytes_is_100mb`, `test_oversize_above_hard_cap_rejected_before_encode`, `test_oversize_at_hard_cap_boundary_allowed`, `test_guess_mime_whitelist_allow` (6 params), `test_guess_mime_whitelist_reject` (7 params), `test_execute_rejects_bin_and_pdf_before_api_call`, `test_openrouter_base_url_literal_appears_exactly_once`. Updated: `test_openai_client_base_url` (drops redundant literal assertion), `test_supported_mimes_whitelist` (adds `video/x-matroska`), `test_unsupported_mime_rejected` (docstring updated). All passing in suite run. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `openrouter_video_analyzer.py::_run_once` | `lib.analysis_errors.VideoAnalysisAuthError` / `VideoAnalysisRateLimitError` | `raise ... from exc` | WIRED | Three `raise Video...Error(...) from exc` sites at lines 390, 396, 403. Pattern `raise VideoAnalysisAuthError\|raise VideoAnalysisRateLimitError` → grep confirmed present. |
| `openrouter_video_analyzer.py::execute` | `ToolResult(success=False, ...)` | `except (VideoAnalysisAuthError, VideoAnalysisRateLimitError)` | WIRED | Line 629: `except (VideoAnalysisAuthError, VideoAnalysisRateLimitError) as exc: return ToolResult(success=False, error=str(exc))`. Appears BEFORE generic `except (VideoAnalysisError, VideoAnalysisRetryExhausted)` at line 634 — Python first-match ordering satisfied. |
| `openrouter_video_analyzer.py::execute (size gate)` | `HARD_MAX_UPLOAD_BYTES` constant | `_clamp_max_upload` + `size > max_upload` rejection | WIRED | Line 568: `max_upload = _clamp_max_upload(inputs.get("max_upload_bytes"))`. Line 575: `if size > max_upload:` triggers rejection with chunking-referring error (lines 579-583). `_clamp_max_upload` references `HARD_MAX_UPLOAD_BYTES` at line 124. |
| `openrouter_video_analyzer.py::_guess_mime` | `_EXT_TO_MIME` dict | `dict.get(suffix.lower())` | WIRED | Line 138: `return _EXT_TO_MIME.get(path.suffix.lower())`. Dict defined at lines 92-98. `execute()` MIME gate at line 587 handles `None` return by failing `mime not in SUPPORTED_MIMES` check. |
| `openrouter_video_analyzer.py::execute (client init)` | `OPENROUTER_BASE_URL` constant | `OpenAI(api_key=..., base_url=OPENROUTER_BASE_URL, ...)` | WIRED | Line 614: `client = OpenAI(api_key=key, base_url=OPENROUTER_BASE_URL, default_headers=default_headers)`. Constant defined at line 74. |

### Data-Flow Trace (Level 4)

N/A — Phase 8 modifies error-handling control flow, size/MIME gates, and a constant reference. None of the changes render dynamic data or depend on an upstream data source. The behavioral tests (exception → ToolResult, size gate → rejection, MIME gate → rejection) ARE the data-flow traces and are all verified green.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| HARD_MAX_UPLOAD_BYTES is 100 MB | `python3 -c "from tools.analysis.openrouter_video_analyzer import HARD_MAX_UPLOAD_BYTES; print(HARD_MAX_UPLOAD_BYTES == 100 * 1024 * 1024)"` | `True` | PASS |
| Sentinels subclass VideoAnalysisError | `python3 -c "from lib.analysis_errors import VideoAnalysisAuthError, VideoAnalysisRateLimitError, VideoAnalysisError; assert issubclass(VideoAnalysisAuthError, VideoAnalysisError); assert issubclass(VideoAnalysisRateLimitError, VideoAnalysisError); print('OK')"` | `OK` | PASS |
| `_guess_mime` whitelist behavior | `python3 -c "from tools.analysis.openrouter_video_analyzer import _guess_mime; from pathlib import Path; print(_guess_mime(Path('x.mp4')), _guess_mime(Path('x.mkv')), _guess_mime(Path('x.bin')))"` | `video/mp4 video/x-matroska None` | PASS |
| OpenRouter URL literal appears exactly once | `grep -c "https://openrouter.ai/api/v1" tools/analysis/openrouter_video_analyzer.py` | `1` | PASS |
| Phase 8 unit test module passes | (part of full suite) | 52 tests in `test_openrouter_video_analyzer.py`, all green | PASS |
| Full suite regression | `python3 -m pytest tests/ --ignore=tests/qa -q` | `3 failed, 643 passed, 13 skipped` (3 failures = pre-existing fc-list FileNotFoundError in TestCodeSnippetUnit) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CLEAN-01 | 08-01-PLAN.md | `_run_once` must surface `AuthenticationError` (401), `PermissionDeniedError` (403), and `RateLimitError` (429) immediately without triggering `_analyze_with_fallback` compact-retry | SATISFIED | Truths 1, 6, 7, 8, 9 verified. Sentinel classes shipped; narrow except chain in place; 4 passing tests prove the contract. |
| CLEAN-02 | 08-02-PLAN.md | `_build_data_url` cap lowered from 2GB to ~100MB | SATISFIED | Truths 2, 10, 11 verified. Constant value `100 * 1024 * 1024` at line 78. Size gate rejects before encoding with chunking-referring error. 3 passing tests. |
| CLEAN-03 | 08-02-PLAN.md | `_guess_mime` uses explicit MIME whitelist; falls through to `None` for unknown extensions | SATISFIED | Truths 3, 12 verified. `_EXT_TO_MIME` dict with 5 entries; `dict.get` returns `None` on miss; `SUPPORTED_MIMES` extended with `video/x-matroska`; dead `mimetypes` import removed. 3 tests with 14 parametrized cases. |
| CLEAN-04 | 08-02-PLAN.md | `OPENROUTER_BASE_URL` constant is single source of truth | SATISFIED | Truths 4, 13 verified. Literal appears exactly once (the constant definition). Call site uses constant. Source-grep invariant enforced by new test. |

**All 4 declared requirement IDs (CLEAN-01, CLEAN-02, CLEAN-03, CLEAN-04) accounted for.** REQUIREMENTS.md maps these 4 IDs to Phase 8 exclusively — no additional orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | None found. No TODO/FIXME/XXX/HACK/PLACEHOLDER markers in `tools/analysis/openrouter_video_analyzer.py` or `lib/analysis_errors.py`. |

### Human Verification Required

None. All must-haves verified programmatically via:
- Structural grep checks (class definitions, constant values, except-ordering)
- Runtime Python imports and assertions (subclass relationships, `_guess_mime` behavior)
- Full pytest suite execution (643 passed including all Phase 8 new/updated tests)

UAT-02 (OpenRouter real-video human review) is explicitly scheduled for Phase 12 per REQUIREMENTS.md traceability table — it is NOT a Phase 8 gate.

### Gaps Summary

No gaps. Phase 8 achieved its goal: the OpenRouter video analyzer now fails fast on auth/rate errors (CLEAN-01), enforces a 100 MB payload ceiling that matches the Phase 4 chunking contract (CLEAN-02), explicitly whitelists video MIMEs with fail-closed rejection for unknown extensions (CLEAN-03), and uses `OPENROUTER_BASE_URL` as the single source of truth at the client call site (CLEAN-04). All 4 declared requirement IDs satisfied. All 5 ROADMAP success criteria met. Full test suite at 643 passing / 13 skipped / 3 pre-existing fc-list failures (unchanged from baseline).

---

*Verified: 2026-04-17*
*Verifier: Claude (gsd-verifier)*
