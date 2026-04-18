---
phase: 10-synthesizer-record-validity
plan: 01
subsystem: security
tags: [path-traversal, input-validation, error-taxonomy, sentinel-exceptions, synthesizer]

# Dependency graph
requires:
  - phase: 08-openrouter-hardening
    provides: "VideoAnalysisAuthError / VideoAnalysisRateLimitError sentinel pattern in lib/analysis_errors.py"
  - phase: 09-chunked-merge-consensus
    provides: "MergeConsensusError sentinel subclassing VideoAnalysisError — umbrella-handler convention"
  - phase: v2.0-05-synthesizer
    provides: "accept_synthesis / reject_synthesis public API (SYNTH-10), _build_slug deterministic hex+hyphen output, STAGING_DIR isolation contract (SYNTH-05)"
provides:
  - "InvalidPipelineSlug sentinel class in lib/analysis_errors.py (subclasses VideoAnalysisError)"
  - "_SLUG_RE regex + _validate_slug() helper in lib/pipeline_synthesizer.py — two-gate guard (regex + resolved-path check)"
  - "accept_synthesis(slug) and reject_synthesis(slug) both short-circuit on malformed / path-traversal input before any shutil.move / src.unlink call"
  - "Parametrized unit-test coverage for 11 malformed / traversal payloads × 2 entry points + inheritance lock + no-filesystem-side-effects assertion"
affects:
  - "phase 10 plan 02 — accept/reject record schema split (CLEAN-09) will reuse the same InvalidPipelineSlug guard; this plan establishes the guard so 10-02 does not need to re-derive the slug shape"
  - "any future caller that surfaces user input to accept_synthesis / reject_synthesis — the guard closes the latent path-traversal hole at the library boundary"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-gate slug validation: regex (fast, rejects obvious payloads) + resolved-path check (defense-in-depth against symlink escape)"
    - "Sentinel subclassing VideoAnalysisError — keeps umbrella `except VideoAnalysisError` callers catching new guard failures uniformly with existing Phase 8 / Phase 9 auth / merge sentinels"
    - "Guard invocation as first post-docstring statement in the validated entry point — locks the 'validate before any fs call' contract against refactor drift"

key-files:
  created: []
  modified:
    - "lib/analysis_errors.py — appended InvalidPipelineSlug class after MergeConsensusError"
    - "lib/pipeline_synthesizer.py — added `import re`, imported InvalidPipelineSlug, defined _SLUG_RE + _validate_slug, wired into accept_synthesis and reject_synthesis"
    - "tests/unit/test_accept_reject.py — migrated 5 existing tests from slug 'foo' (too short for new regex) to canonical 'foo-abcd1234'; appended 5 new test functions (Test A/B parametrized over 11 payloads, Test C happy path, Test D inheritance lock, Test E no-filesystem-side-effects)"

key-decisions:
  - "Regex `^[a-z0-9][a-z0-9\\-_]{7,127}$` (lowercase only, min length 8) — matches _build_slug output `<base>-<hex[:8]>` exactly, rejects uppercase / path separators / leading dot / absolute paths by character class"
  - "Sentinel InvalidPipelineSlug (not generic ValueError) — consistent with Phase 8 VideoAnalysisAuthError and Phase 9 MergeConsensusError family; umbrella `except VideoAnalysisError` handlers catch it for free"
  - "Two-gate guard applied to BOTH accept_synthesis and reject_synthesis — symmetric surface closes T-10-02 (reject-path traversal deletes arbitrary file) alongside T-10-01 (accept-path traversal moves arbitrary file)"
  - "Validation as the first post-docstring statement in each entry point — guarantees short-circuit before any filesystem mutation (verified by Test E)"
  - "Helper named `_validate_slug` (not `_validate_synthesis_slug`) to preserve the SYNTH-10 grep-anchor contract test (`synthes\\w*accept` must not match any symbol in the module)"

patterns-established:
  - "Slug validation at library boundary: every public entry point that joins user-controlled input under a filesystem root invokes a `_validate_*` helper BEFORE any path construction"
  - "Sentinel family grows by appending subclasses to `lib/analysis_errors.py` in chronological phase order (Phase 8 auth → Phase 9 merge → Phase 10 slug)"
  - "Defense-in-depth resolved-path check even when regex would already catch the payload — cheap insurance against hypothetical regex-bypass via symlink"

requirements-completed: [CLEAN-08]

# Metrics
duration: 12min
completed: 2026-04-18
---

# Phase 10 Plan 01: Synthesizer Slug Validation Summary

**InvalidPipelineSlug sentinel + two-gate slug validator (regex `^[a-z0-9][a-z0-9\-_]{7,127}$` + resolved-path check) wired into accept_synthesis and reject_synthesis, closing v2.0 Phase 5 REVIEW MR-01 latent path-traversal hole.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-04-18T01:28:34Z
- **Completed:** 2026-04-18T01:40:43Z
- **Tasks:** 3 (2 code + 1 verification)
- **Files modified:** 3

## Accomplishments

- New `InvalidPipelineSlug(VideoAnalysisError)` sentinel appended after `MergeConsensusError` in `lib/analysis_errors.py` — mirrors Phase 8 / Phase 9 docstring + inheritance convention so umbrella `except VideoAnalysisError` handlers catch it uniformly.
- `_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{7,127}$")` + `_validate_slug(slug)` helper in `lib/pipeline_synthesizer.py`. Two gates: regex (matches `_build_slug` output exactly, rejects `..` / `/` / `\` / `.` / uppercase / absolute-path / shell-metachar by character class) + resolved-path check (`(STAGING_DIR / f"{slug}.yaml").resolve().parent == STAGING_DIR.resolve()` — catches any hypothetical regex bypass via symlink escape).
- Both `accept_synthesis(slug)` and `reject_synthesis(slug)` now invoke `_validate_slug(slug)` as the first executable statement after the docstring, BEFORE any `shutil.move` / `src.unlink()` / `.exists()` filesystem call. T-10-01 (accept traversal) and T-10-02 (reject traversal) both mitigated.
- 5 new unit-test functions appended to `tests/unit/test_accept_reject.py`: parametrized coverage across 11 malformed / traversal payloads × 2 entry points (22 items), plus a happy-path regression lock for `_build_slug`-shaped slugs, an inheritance-chain lock (`issubclass(InvalidPipelineSlug, VideoAnalysisError) is True`), and a no-filesystem-side-effects assertion (staged file untouched after `InvalidPipelineSlug` is raised).
- Full suite `pytest tests/ --ignore=tests/qa -q` reports **687 passing / 13 skipped / 3 pre-existing fc-list failures** — 662 baseline + 25 new Plan 10-01 items, no new failures attributable to this plan. SYNTH-10 grep-anchor (`test_no_auto_approval_path`) and Phase 7 E2E smoke both green.

## Task Commits

Each task committed atomically with `--no-verify`:

1. **Task 1: Add InvalidPipelineSlug sentinel + _validate_slug helper + wire both entry points** — `0977c89` (feat)
2. **Task 2: Parametrized unit tests — malformed slugs + traversal + backward-compat happy path** — `1723c56` (test)
3. **Task 3: Full-suite regression check** — no source changes; verification only (687 passing, 13 skipped, 3 pre-existing fc-list fails — all as expected)

## Files Created/Modified

- `lib/analysis_errors.py` — appended `InvalidPipelineSlug(VideoAnalysisError)` class with Phase 10 CLEAN-08 / v2.0 Phase 5 REVIEW MR-01 cross-references; docstring mirrors `MergeConsensusError` structure.
- `lib/pipeline_synthesizer.py` — added `import re`, added `from lib.analysis_errors import InvalidPipelineSlug`, defined `_SLUG_RE` constant + `_validate_slug` helper (both documented inline, referencing SYNTH-06 _build_slug shape), inserted `_validate_slug(slug)` as first post-docstring statement in `accept_synthesis` (line 606 area) and `reject_synthesis` (line 670 area). `Raises:` docstring sections updated in both entry points.
- `tests/unit/test_accept_reject.py` — migrated tests 1, 2, 5, 7, 8 from slug `"foo"` (3 chars — fails new regex) to canonical `"foo-abcd1234"` (12 chars, matches regex and `_build_slug` shape); tests 3, 4, 6 already used valid-regex slugs (`"cinematic"`, `"does-not-exist"`) and were left unchanged. Appended 5 new test functions: `test_accept_rejects_malformed_slug` (parametrized), `test_reject_rejects_malformed_slug` (parametrized), `test_accept_happy_path_canonical_slug_still_works`, `test_invalid_pipeline_slug_is_video_analysis_error`, `test_accept_slug_validation_short_circuits_filesystem`.

## Decisions Made

- **Regex exact shape `^[a-z0-9][a-z0-9\-_]{7,127}$`** — lowercase only with minimum length 8, picked to match `_build_slug(base, checksum)` output `<base>-<hex[:8]>` (so the deterministic caller path never regresses) while rejecting the full vector set from MR-01 (`..`, absolute paths, uppercase, shell metachars, whitespace) by character class. Min length 8 is tight — the shortest realistic slug is `<3-char-base>-<8-hex>` = 12 chars, and 8 chars covers a hypothetical `<hex-only>` slug of exactly 8 hex digits.
- **Sentinel over ValueError** — the v2.0 MR-01 fix sketch suggested `ValueError`; CONTEXT.md D-CLEAN-08 upgraded this to a dedicated `InvalidPipelineSlug` sentinel to match the Phase 8 / Phase 9 error-family convention and keep umbrella `except VideoAnalysisError` handlers working uniformly. Zero existing caller relies on `ValueError` from these entry points (they never raised `ValueError` before this plan).
- **Guard at function entry, before any filesystem stat** — test E explicitly verifies that a malformed slug does not trigger any `.exists()` / `shutil.move` / `src.unlink` side effect. This locks the contract against a future refactor that might accidentally move the guard after an `exists()` check and leak timing information.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Updated 5 pre-existing tests from slug `"foo"` to canonical `"foo-abcd1234"`**
- **Found during:** Task 1 (Wire _validate_slug into accept_synthesis / reject_synthesis)
- **Issue:** Tests 1, 2, 5, 7, 8 in `tests/unit/test_accept_reject.py` used slug `"foo"` (3 characters, all lowercase-alphanumeric). The new `_SLUG_RE = ^[a-z0-9][a-z0-9\-_]{7,127}$` has a minimum length of 8 characters (to match `_build_slug` output `<base>-<hex[:8]>`). With the guard wired into `accept_synthesis`/`reject_synthesis`, these 5 tests began raising `InvalidPipelineSlug` at the validation step instead of exercising the downstream behavior they were written to test (file move, record shape, schema validity). The plan's must-have #3 states "no existing accept/reject test regresses except ones that were asserting ValueError where we now raise InvalidPipelineSlug" — these regressions are a different class (input shape, not error type).
- **Fix:** Updated all five tests to use slug `"foo-abcd1234"` — 12 chars, lowercase hex + hyphen, canonical `_build_slug` shape. Only the literal string was changed; test intent and assertions remain identical. Added an inline comment on test 1 pointing to CLEAN-08 so future readers understand the slug constraint.
- **Files modified:** `tests/unit/test_accept_reject.py` (5 test functions; ~15 literal string substitutions)
- **Verification:** `pytest tests/unit/test_accept_reject.py -q` → 36 passed. The 2 pre-existing missing-staging tests (tests 4 and 6) already used regex-compliant slugs (`"does-not-exist"`, `"cinematic"`) and were left unchanged.
- **Committed in:** `0977c89` (Task 1 commit — bundled because the test migration is strictly a consequence of wiring the guard; keeping them in one commit preserves bisectability).

---

**Total deviations:** 1 auto-fixed (1 blocking — test-fixture input shape incompatible with new validation contract).
**Impact on plan:** Deviation was necessary to land Task 1's guard without breaking the suite. Test intent is unchanged; only the literal slug string was migrated to the canonical `_build_slug` shape the plan itself standardizes on. No scope creep; the 5 tests still assert the same behavior (file move, tuple return, schema validity, reject deletion, invalid-status record). The plan's success-criteria #6 ("Full suite `pytest tests/ --ignore=tests/qa -q` reports ≥667 passing") is met with 687 passing.

## Issues Encountered

None. The plan's research explicitly called out the migration risk on must-have #3 but underspecified the exact slugs that would need updating; this was handled inline as a Rule 3 auto-fix.

## Threat Flags

No new security-relevant surface introduced. This plan **closes** the T-10-01 / T-10-02 / T-10-03 threats from the plan's own `<threat_model>` block and adds no new trust boundaries or schema changes.

## User Setup Required

None — no external service configuration, no new environment variables, no dashboard steps.

## Next Phase Readiness

- Plan 10-02 (CLEAN-09, accept/reject record schema split) is unblocked. The `InvalidPipelineSlug` guard established here is a pure pre-condition: 10-02 modifies the record shape emitted AFTER the guard has already passed, so the two plans are cleanly separable.
- SYNTH-10 grep-anchor contract (`synthes\w*accept` forbidden) remains intact — helper name `_validate_slug` does not match and `test_no_auto_approval_path` is green.
- Phase 7 E2E smoke (`tests/contracts/test_phase7_e2e_smoke.py`) is green — real `_build_slug` output (lowercase base + hex suffix) passes the new regex unchanged; the v2.0 happy-path staging → accept → pipeline_defs flow is backward-compatible.
- No blockers for Phase 11 (drift + NITS) or Phase 12 (human UAT). The `VideoAnalysisError` umbrella-handler pattern is now 3 sentinels deep (auth, merge, slug) and ready to absorb further hardening.

## Self-Check

- [x] `lib/analysis_errors.py` contains `class InvalidPipelineSlug(VideoAnalysisError)` — FOUND
- [x] `lib/pipeline_synthesizer.py` defines `_SLUG_RE` and `_validate_slug` — FOUND (1 match each)
- [x] `_validate_slug(slug)` invoked exactly 2× in `lib/pipeline_synthesizer.py` (accept + reject) — FOUND
- [x] `grep -nE "synthes\w*accept" lib/pipeline_synthesizer.py` → 0 matches (helper safe) — FOUND
- [x] Commit `0977c89` exists on current branch — FOUND
- [x] Commit `1723c56` exists on current branch — FOUND
- [x] `pytest tests/unit/test_accept_reject.py -q` → 36 passed — FOUND
- [x] `pytest tests/ --ignore=tests/qa -q` → 687 passed, 13 skipped, 3 pre-existing fc-list failures — FOUND

## Self-Check: PASSED

---
*Phase: 10-synthesizer-record-validity*
*Completed: 2026-04-18*
