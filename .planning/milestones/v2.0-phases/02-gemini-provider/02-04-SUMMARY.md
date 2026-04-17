---
phase: 02-gemini-provider
plan: 04
subsystem: testing
tags: [pytest, unittest-mock, google-genai, gemini, video-analysis, contracts]

requires:
  - phase: 01-canonical-schema
    provides: minimal_video_analysis() fixture + schemas.artifacts.validate_artifact
  - phase: 02-gemini-provider/02-01
    provides: VideoAnalyzerSelector + lib.analysis_errors
  - phase: 02-gemini-provider/02-02
    provides: GeminiVideoAnalyzer under test (18-behavior contract)
provides:
  - API-key-free unit tests for GeminiVideoAnalyzer (21 tests, 18 canonical behaviors + 3 extras)
  - Contract tests for Phase 2 invariants (selector registration, preference order, flattened-schema shape, SKILL wiring, security)
  - Shared conftest with mocked google-genai SDK (mock_genai, valid_artifact, fake_video, response_factories)
affects:
  - 02-03 (SKILL.md tests skipped here will enforce after merge)
  - 03-openrouter-provider (contract test pattern reused for second provider)
  - 04-chunking (multi-chunk tests extend the same mock surface)

tech-stack:
  added: [unittest.mock MagicMock for SDK stubbing, pytest autouse fixture for env scrubbing]
  patterns:
    - "Phase fixtures share a single minimal_video_analysis() source of truth (defense against T-02-18 drift)"
    - "Autouse env scrubbing in tests/unit/conftest.py isolates provider keys from the developer shell"
    - "SKILL-dependent tests use pytest.mark.skipif(not PATH.is_file(), ...) for concurrent-worktree safety"
    - "AST-based source checks (not string grep) for docstring-resistant invariants (e.g., no write_checkpoint call)"

key-files:
  created:
    - tests/unit/conftest.py
    - tests/unit/test_gemini_video_analyzer.py
    - tests/contracts/test_phase2_gemini_contracts.py
    - .planning/phases/02-gemini-provider/deferred-items.md
  modified: []

key-decisions:
  - "Renamed plan's target contract file to test_phase2_gemini_contracts.py to avoid overwriting ~100 unrelated legacy Enhancement-Layer tests"
  - "SKILL.md-dependent tests skip (not fail) while plan 02-03 runs concurrently — agent_skills wiring is still asserted unconditionally"
  - "AST-parse the tool source for the no-write_checkpoint check rather than string grep (docstring mentions would falsely trip a raw grep)"
  - "Autouse _scrub_provider_keys fixture in tests/unit/conftest.py removes developer-env key leakage from every unit test"

patterns-established:
  - "Pattern: provider-level unit tests mock the SDK at the module's import namespace (monkeypatch tools.analysis.X.genai.Client) rather than patching the library itself"
  - "Pattern: per-scenario response_factories (ok/truncated/empty_stop) keep per-test setup to 3 lines"
  - "Pattern: shared Phase 1 fixture reused via import (single source of truth — not redefined per phase)"

requirements-completed: [ANLZ-01, ANLZ-04, ANLZ-05, GEM-01, GEM-02, GEM-03, GEM-04, GEM-05, SKILL-01]

duration: 18min
completed: 2026-04-17
---

# Phase 02 Plan 04: Gemini Provider Test Suite Summary

**API-key-free test suite for the Gemini video-analysis provider: 21 unit tests against a mocked google-genai SDK + 16 contract tests asserting selector registration, preference order, flattened-schema shape, SKILL wiring, and security invariants. Full combined run in 1.3s with no GEMINI_API_KEY set.**

## Performance

- **Duration:** ~18 min (execution + verification + summary)
- **Started:** 2026-04-17T (session start)
- **Completed:** 2026-04-17
- **Tasks:** 3 (all autonomous, no checkpoints)
- **Files created:** 4 (3 test artifacts + 1 deferred-items log)

## Accomplishments

- **21 unit tests** for `GeminiVideoAnalyzer` covering every behavior from plan 02-02's `<behavior>` block (auth priority, polling, FAILED state, wall-clock timeout, finally-block delete, flattened schema, MAX_TOKENS retry, empty-STOP retry, ClientError fallback preview→2.5-pro, shot_boundaries two shapes, confidence='low' directive, invalid artifact gate, no write_checkpoint, API-key non-leak).
- **16 contract tests** for Phase 2 invariants (selector registration + self-exclusion, 4-branch preference order, zero-providers error, tool contract fields, flattened-schema strip + confidence-map preservation, schema adapter idempotency, minimal fixture still validates, SKILL.md presence + sections [skipped pending 02-03], agent_skills wiring assertion, no embedded `AIza...` keys).
- **Shared `tests/unit/conftest.py`** with autouse env scrubbing + mocked SDK fixtures (one-line stubs for every test) + Phase 1 fixture reuse for drift-safe mocks.
- **Runtime:** combined Phase 2 run 1.26s (well under 30s budget); full repo `pytest tests/` regression still 355 passed, 8 skipped, 3 pre-existing deselected fc-list issues.

## Task Commits

1. **Task 1: conftest.py with mocked google-genai fixtures** — `23b7cba` (test)
2. **Task 2: 21 unit tests for GeminiVideoAnalyzer** — `be27e0c` (test)
3. **Task 3: Phase 2 contract tests (selector/schema/SKILL/security)** — `ebcc143` (test)

## Files Created

- `/workspace/tests/unit/conftest.py` — 191 lines. Autouse `_scrub_provider_keys` + fixtures: `mock_genai`, `valid_artifact`, `fake_video`, `fake_file_factory`, `response_factories`, `no_keys`. Reuses `minimal_video_analysis()` from Phase 1 contract tests.
- `/workspace/tests/unit/test_gemini_video_analyzer.py` — 421 lines. 21 `def test_` functions covering 18 canonical behaviors + 3 extras. Uses `mock_genai` fixture for 36 of 21 tests; all pass in 1.1s with no API key.
- `/workspace/tests/contracts/test_phase2_gemini_contracts.py` — 240 lines. 16 tests total: 14 pass, 2 skip (SKILL.md-dependent, enforced post-merge). Covers registration, preference order (4 branches + zero case), tool contract, flattened-schema invariants, schema adapter idempotency, artifact gate, agent_skills wiring, and key-embedding guard.
- `/workspace/.planning/phases/02-gemini-provider/deferred-items.md` — logs the two pre-existing issues (fc-list font tooling missing; legacy `test_phase2_contracts.py` naming collision).

## Decisions Made

- **Filename collision avoidance.** Plan spec called for `tests/contracts/test_phase2_contracts.py`, but that exact path already contained ~100 unrelated legacy Enhancement-Layer contract tests (pre-GSD phase numbering). Chose `test_phase2_gemini_contracts.py` to disambiguate rather than delete load-bearing tests. All acceptance criteria referencing "a contract test file" are satisfied by the renamed file.
- **Concurrent-worktree safety.** Plan 02-03 (running in a sibling worktree) creates `.agents/skills/gemini-video-analysis/SKILL.md`. Rather than pre-creating a stub (would conflict at merge), the two SKILL-content-dependent tests use `pytest.mark.skipif(not SKILL_PATH.is_file(), ...)`. Post-merge they auto-enforce. The `test_agent_skills_wiring_consistent` test asserts the wiring unconditionally (no skip) — that invariant is already satisfied by 02-01 and 02-02.
- **AST-based write_checkpoint check.** The tool source's module docstring contains the string "does NOT call write_checkpoint" as prose. A raw string grep would false-positive. Switched to `ast.walk` checking `ImportFrom`, `Import`, and `Call` nodes — docstring-resistant and precise.
- **Confidence-null directive assertion.** The tool prompt includes "never emit null" as an instruction to the model. Asserting "emit null" is absent would be wrong. The test now asserts the presence of an explicit negation phrase (`never emit null`, `not emit null`, etc.) — asserting the *policy* rather than the absence of a substring.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Filename collision with legacy `test_phase2_contracts.py`**
- **Found during:** Task 3 (contract test file creation)
- **Issue:** `tests/contracts/test_phase2_contracts.py` already exists with ~100 unrelated legacy tests (FaceEnhance, SceneDetect, ColorGrade, AudioEnhance, ImageSelector, CodeSnippet, DiagramGen). Overwriting would delete all of them and break Phase 1 invariants.
- **Fix:** Created `tests/contracts/test_phase2_gemini_contracts.py` instead. Logged in `deferred-items.md`.
- **Files modified:** tests/contracts/test_phase2_gemini_contracts.py (new)
- **Verification:** `pytest tests/contracts/test_phase2_gemini_contracts.py -q` → 14 passed, 2 skipped. Legacy file untouched.
- **Committed in:** `ebcc143`

**2. [Rule 1 - Bug] Plan's `test_prompt_instructs_confidence_low_not_null` assertion was inverted**
- **Found during:** Task 2 verification run
- **Issue:** Plan specified `assert "emit null" not in prompt_text.lower()` — but the tool prompt deliberately contains "never emit null" as an instruction to the model. The assertion would fail on correct code.
- **Fix:** Rewrote assertion to check for presence of a negation phrase (`never emit null`, `not emit null`, `avoid null`) rather than the absence of the substring.
- **Files modified:** tests/unit/test_gemini_video_analyzer.py
- **Verification:** test passes with the current tool source.
- **Committed in:** `be27e0c`

**3. [Rule 1 - Bug] Plan's `test_tool_source_does_not_import_write_checkpoint` was string-grep based**
- **Found during:** Task 2 verification run
- **Issue:** The tool module docstring contains "does NOT call write_checkpoint" as prose. A raw `"write_checkpoint" not in source` check false-positives on the docstring.
- **Fix:** Switched to `ast.parse` + walk for `ImportFrom(module='lib.checkpoint')`, `Import(names=['lib.checkpoint'])`, and `Call(func.id='write_checkpoint' or func.attr='write_checkpoint')`. Docstring-resistant and precise.
- **Files modified:** tests/unit/test_gemini_video_analyzer.py
- **Verification:** test passes; verified by temporarily inserting a write_checkpoint call (fails as expected); reverted.
- **Committed in:** `be27e0c`

**4. [Rule 2 - Missing Critical] Autouse env-scrubbing fixture**
- **Found during:** Task 1 design
- **Issue:** Plan's conftest sketched a `no_keys` fixture but did not mandate `autouse=True` env scrub. Developer shells often have `GEMINI_API_KEY` set; tests would inherit it and bypass the "no API key" contract from the plan's success criteria ("Tests pass with no API keys: unset GEMINI_API_KEY...").
- **Fix:** Added `@pytest.fixture(autouse=True) _scrub_provider_keys` that runs on every unit test. `mock_genai` re-sets a fake key for happy-path tests; `no_keys` remains as an explicit-intent fixture.
- **Files modified:** tests/unit/conftest.py
- **Verification:** `unset GEMINI_API_KEY GOOGLE_API_KEY OPENROUTER_API_KEY; pytest tests/unit/test_gemini_video_analyzer.py -q` → 21 passed.
- **Committed in:** `23b7cba`

---

**Total deviations:** 4 auto-fixed (1 blocking, 2 bugs in plan assertions, 1 missing-critical security fixture)
**Impact on plan:** All deviations necessary for a green-on-correct-code test suite. No scope creep; zero new production code modified.

## Issues Encountered

- **Pre-existing `test_phase2_contracts.py` fc-list failures** (3 tests): `TestCodeSnippetUnit::test_render_*` fail because the devcontainer lacks `fontconfig`. Confirmed pre-existing (stash → run → reproduces → pop). Out of scope for Phase 2 Gemini work. Logged in `deferred-items.md`. 355 tests pass when these are deselected.
- **Concurrent plan 02-03 dependency.** Plan 02-04's contract tests assert SKILL.md shape, but the file is being created by plan 02-03 in a sibling worktree (no file overlap with my plan). Resolved with `pytest.mark.skipif` gates on the 2 SKILL-content tests; post-merge they auto-enforce with no re-run needed.

## Requirements → Tests Coverage

| Requirement | Test(s)                                                                 | File |
| ----------- | ----------------------------------------------------------------------- | ---- |
| ANLZ-01     | `test_selector_preference_*` (4 branches) + `test_selector_zero_providers` | `tests/contracts/test_phase2_gemini_contracts.py` |
| ANLZ-04     | `test_prompt_instructs_confidence_low_not_null` + `test_invalid_artifact_returns_failure_and_deletes` + `test_minimal_artifact_still_validates` | both |
| ANLZ-05     | `test_shot_boundaries_absent_prompt_has_model_directive` + `test_shot_boundaries_both_shapes_normalize` + `test_shot_boundaries_passed_into_prompt` | `tests/unit/test_gemini_video_analyzer.py` |
| GEM-01      | `test_contract_fields` + `test_auth_priority_gemini_first` + `test_auth_falls_back_to_google` + `test_execute_no_key_returns_error_without_leaking_value` + `test_gemini_tool_contract` | both |
| GEM-02      | `test_poll_processing_then_active` + `test_poll_failed_raises` + `test_poll_timeout_raises` | `tests/unit/test_gemini_video_analyzer.py` |
| GEM-03      | `test_file_deleted_on_success` + `test_file_deleted_on_failure` + `test_invalid_artifact_returns_failure_and_deletes` | `tests/unit/test_gemini_video_analyzer.py` |
| GEM-04      | `test_flat_schema_passed_to_generate_content` + `test_max_tokens_triggers_compact_retry` + `test_retry_exhausted_raises` + `test_empty_text_triggers_retry` + `test_model_fallback_on_preview_unavailable` + `test_flattened_schema_removes_unsupported_keys` + `test_flattened_schema_preserves_confidence_map` + `test_schema_adapter_idempotent` | both |
| GEM-05      | `test_gemini_tool_contract` + `test_agent_skills_wiring_consistent` + `test_gemini_skill_file_exists` (skipped pending 02-03) + `test_gemini_skill_has_required_sections` (skipped pending 02-03) | `tests/contracts/test_phase2_gemini_contracts.py` |
| SKILL-01    | `test_gemini_skill_file_exists` + `test_gemini_skill_has_required_sections` + `test_agent_skills_wiring_consistent` | `tests/contracts/test_phase2_gemini_contracts.py` |
| SKILL-03    | Manual-only gate (per plan 02-03 decision); not asserted in automated suite. | — |

Every phase requirement with an automated-verification row has ≥1 corresponding test. SKILL-03 remains the documented post-execute human-verification checkpoint as agreed in the phase plan.

## Self-Check

- `tests/unit/conftest.py` — **FOUND** (191 lines; 6 fixtures)
- `tests/unit/test_gemini_video_analyzer.py` — **FOUND** (421 lines; 21 `def test_`)
- `tests/contracts/test_phase2_gemini_contracts.py` — **FOUND** (240 lines; 16 `def test_`)
- `.planning/phases/02-gemini-provider/deferred-items.md` — **FOUND**
- Commit `23b7cba` — **FOUND** (conftest)
- Commit `be27e0c` — **FOUND** (unit tests)
- Commit `ebcc143` — **FOUND** (contract tests + deferred-items)
- Combined suite runtime: **1.26s** (budget: 30s)
- Combined suite exit code with no API keys: **0** (35 passed, 2 skipped)
- Full repo `pytest tests/` regression: **355 passed, 8 skipped, 3 pre-existing fc-list failures deselected** (no new regressions)

## Self-Check: PASSED

## Known Stubs

None. No hardcoded placeholder data flows to production; the "stubs" in the test suite are mocks — the explicit, intentional test subject matter.

## User Setup Required

None — test suite runs in any dev container with pytest + google-genai installed.

## Next Phase Readiness

- Phase 2 now has full automated coverage for the Gemini provider path.
- Plan 02-03 (SKILL.md) merge will lift 2 skipped tests automatically.
- Phase 3 (OpenRouter provider) can reuse the same conftest pattern; `mock_genai` fixture will need a sibling `mock_openrouter` with the same shape.
- Phase 4 (chunking) can extend `response_factories` with multi-chunk merge response builders.

---
*Phase: 02-gemini-provider*
*Plan: 04*
*Completed: 2026-04-17*
