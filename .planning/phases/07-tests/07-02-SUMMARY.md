---
phase: 07-tests
plan: 02
subsystem: tests/integration
tags: [tests, integration, gemini, openrouter, fixture-gated, pytest-marker]
requirements: [TEST-02]
dependency-graph:
  requires:
    - tools/analysis/video_analyzer_selector.py      # Phase 2 — selector routing
    - tools/analysis/gemini_video_analyzer.py        # Phase 2 — Gemini provider
    - tools/analysis/openrouter_video_analyzer.py    # Phase 3 — OpenRouter provider
    - lib/chunked_analyzer.py                        # Phase 4 — chunked path (>5min)
    - schemas/artifacts/video_analysis.schema.json   # Phase 1 — canonical shape
  provides:
    - tests/integration/conftest.py                  # double-gate helpers
    - tests/integration/test_phase7_integration_gemini.py
    - tests/integration/test_phase7_integration_openrouter.py
    - pytest.ini (marker registration)
  affects:
    - .gitignore (excludes tests/integration/fixtures/)
tech-stack:
  added: []
  patterns:
    - Double-gate skip (env + fixture presence)
    - Module-level pytestmark (pytest.mark.integration)
    - Indirect parametrization via pytest fixture (fixture_video)
    - Selector-level routing (not raw tool) to exercise Phase 2/3 contracts
key-files:
  created:
    - tests/integration/__init__.py
    - tests/integration/conftest.py
    - tests/integration/README.md
    - tests/integration/test_phase7_integration_gemini.py
    - tests/integration/test_phase7_integration_openrouter.py
    - pytest.ini
  modified:
    - .gitignore
decisions:
  - Double-gate: RUN_INTEGRATION_TESTS=1 + fixture file existence. Missing
    gate yields SKIP (never FAIL) so default pytest stays green.
  - Tests target the capability SELECTOR, not the raw provider tools, so the
    Phase 2 routing contract is part of the acceptance.
  - No numeric value assertions — real model output is non-deterministic;
    tests assert SHAPE (schema validity + top-level keys + chunking metadata).
  - Fixtures user-provisioned post-milestone (not shipped) — size 10-100MB
    and licensing of clips would otherwise leak into the repo.
metrics:
  duration: ~15 min
  completed: 2026-04-17
---

# Phase 7 Plan 02: Integration Test Scaffolding Summary

Integration test scaffolding under `tests/integration/` with real-API suites for Gemini and OpenRouter, each covering three fixture video tiers (short <2min, medium 3-5min, long >5min chunked) — all double-gated on `RUN_INTEGRATION_TESTS=1` + fixture-file existence + provider API key, with the `integration` pytest marker registered so the default run stays key-free and green.

## Scope

TEST-02 from Phase 7 — the integration layer that proves end-to-end behavior against real provider APIs. Plan 07-02 produces the scaffolding + both provider suites; user provisions fixture videos post-milestone per the shipped `tests/integration/README.md`.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Scaffold tests/integration/ (conftest, README, marker, gitignore) | `dba3878` | `tests/integration/__init__.py`, `tests/integration/conftest.py`, `tests/integration/README.md`, `pytest.ini`, `.gitignore` |
| 2 | Gemini real-API integration suite (3 fixture tiers) | `9e2c9a3` | `tests/integration/test_phase7_integration_gemini.py` |
| 3 | OpenRouter real-API integration suite (3 fixture tiers) | `c429376` | `tests/integration/test_phase7_integration_openrouter.py` |

Total: 3 commits, 7 files created/modified, 420 lines added.

## Artifacts Produced

### tests/integration/conftest.py — double-gate helpers (108 lines)

Exposes the contract that makes every downstream test deterministic:

- `FIXTURES_DIR` + `FIXTURE_VIDEOS` dict (short / medium / long -> Path).
- `require_integration_enabled()` — skips on `RUN_INTEGRATION_TESTS != "1"`.
- `require_fixture(tier)` — skips if the tier's video file is missing on disk.
- `require_gemini_key()` — skips if neither `GEMINI_API_KEY` nor `GOOGLE_API_KEY` set.
- `require_openrouter_key()` — skips if `OPENROUTER_API_KEY` unset.
- `fixture_video` pytest fixture — indirect-parametrizable (`["short"]`, `["medium"]`, `["long"]`) that chains `require_integration_enabled` + `require_fixture` and returns a `Path` to the existing file.

**Design note:** unlike `tests/unit/conftest.py` (which autouse-scrubs provider env vars so mocks reign), this conftest does NOT touch env — real keys must pass through.

### tests/integration/test_phase7_integration_gemini.py — 3 tests (105 lines)

- `test_short_video_single_call` — <2min fixture, validates canonical `video_analysis` artifact, asserts absence of `chunking_metadata` + presence of all 6 top-level keys (`version`, `source`, `editing_pacing`, `audio`, `visual_style`, `narrative`).
- `test_medium_video_single_call` — 3-5min boundary test; still single-call under the 300s chunking threshold.
- `test_long_video_chunked` — >5min fixture, asserts `chunking_metadata.chunk_count >= 2` (Phase 4 merge contract).

Module-level `pytestmark = pytest.mark.integration`. Shared helper `_run_gemini_selector` drives `VideoAnalyzerSelector` with `preferred_provider="gemini"` so the Phase 2 routing path is part of the acceptance.

### tests/integration/test_phase7_integration_openrouter.py — 3 tests (101 lines)

Structurally mirrors the Gemini file for apples-to-apples comparison (intentional parity — keeps the Plan 07-03 cross-provider tolerance test trivially parametrizable). Same 3 assertions per tier; exercises the OR-03 base64-inline encoding path via `preferred_provider="openrouter"`.

### tests/integration/README.md (96 lines)

Documents the 3 fixture tiers with exact file paths, duration bands, provenance suggestions (Creative Commons YouTube, Blender Foundation classics, Pexels, yt-dlp example), run commands for Gemini-only / OpenRouter-only / both / default-skip, cost estimate (~$0.44 per full run), and rationale for not shipping fixtures (size + licensing + shape-based assertions).

### pytest.ini (3 lines)

```ini
[pytest]
markers =
    integration: real-API tests gated by RUN_INTEGRATION_TESTS=1 + fixture presence (see tests/integration/README.md)
```

Minimal — marker registration only. No `testpaths`, no `addopts`. Suppresses `PytestUnknownMarkWarning` and enables `pytest -m integration` / `pytest -m 'not integration'`.

### .gitignore entry

```
# Integration test fixtures (10-100MB video clips — user-provisioned, not part of repo)
tests/integration/fixtures/
```

Prevents the multi-MB clips from entering history.

## Verification Evidence

### Clean-skip run (the contract)

```
$ pytest tests/integration/ -v
collected 6 items

tests/integration/test_phase7_integration_gemini.py::test_short_video_single_call[short] SKIPPED [ 16%]
tests/integration/test_phase7_integration_gemini.py::test_medium_video_single_call[medium] SKIPPED [ 33%]
tests/integration/test_phase7_integration_gemini.py::test_long_video_chunked[long] SKIPPED [ 50%]
tests/integration/test_phase7_integration_openrouter.py::test_short_video_single_call[short] SKIPPED [ 66%]
tests/integration/test_phase7_integration_openrouter.py::test_medium_video_single_call[medium] SKIPPED [ 83%]
tests/integration/test_phase7_integration_openrouter.py::test_long_video_chunked[long] SKIPPED [100%]

============================== 6 skipped in 0.07s ==============================
```

6 SKIPs, 0 failures, 0 errors — the default-env contract holds.

### Marker filter works bidirectionally

```
$ pytest -m integration tests/integration/ --collect-only -q
6 tests collected in 0.05s

$ pytest -m 'not integration' tests/integration/ --collect-only -q
no tests collected (6 deselected) in 0.05s
```

### No PytestUnknownMarkWarning

`pytest tests/integration/ -v` emits zero warnings about the `integration` marker — confirming `pytest.ini` registration works.

### Contract + unit suites unaffected

`pytest tests/contracts/ tests/unit/` — still 580 passed, 6 skipped. (3 pre-existing `fc-list`-dependent failures in `test_phase2_contracts.py::TestCodeSnippetUnit` are unrelated to this plan; already documented in `.planning/phases/07-tests/deferred-items.md` by sibling plan 07-01.)

## Post-Milestone User Action

Integration tests are **code-complete** but require user-provided fixture videos to actually run. The shipped `tests/integration/README.md` documents:

1. The 3 fixture tiers and their exact file paths.
2. Container requirement (H.264 MP4 at <= 720p recommended).
3. Suggested sources — Creative Commons YouTube, Blender Foundation classics (Big Buck Bunny, Sintel, Tears of Steel), Pexels, your own screen recordings.
4. A copy-paste `yt-dlp` command template.
5. How to run the suite once fixtures + keys are in place.

Until fixtures land, the suite silently skips — exactly the contract Plan 07-02 is built around.

## Cost estimate (from README)

| Tier | Approx provider cost | Why |
|------|----------------------|-----|
| short (<2min) | ~$0.02 | Single-call, small token budget |
| medium (3-5min) | ~$0.05 | Single-call, boundary |
| long (>5min, chunked) | ~$0.15 | ~3 chunks x ~$0.05 |

Full integration run (both providers x 3 tiers) ≈ **$0.44** per invocation.

## Deviations from Plan

None — plan executed exactly as written. All artifacts, acceptance criteria, and verification commands matched the PLAN.md contract.

No deviations invoked Rule 1 (auto-fix bug), Rule 2 (auto-add critical functionality), Rule 3 (auto-fix blocking issue), or Rule 4 (ask about architectural change).

## Threat Surface Assessment

No new surface introduced. The threat register in the plan's `<threat_model>` remained accurate:

- T-07-04 (API key disclosure): mitigated — tests never echo env vars; `result.error` trusting Phase 2/3 SDK redaction.
- T-07-05 (fixture commit): mitigated — `.gitignore` entry + README warning.
- T-07-06 (API spend): accepted — README surfaces ~$0.44 per run; user controls trigger.
- T-07-07 (fixture tampering): accepted — out of scope for integration tests.

No threat flags to escalate.

## Self-Check: PASSED

- FOUND: `tests/integration/__init__.py`
- FOUND: `tests/integration/conftest.py` (108 lines; contains RUN_INTEGRATION_TESTS, require_integration_enabled, require_fixture, require_gemini_key, require_openrouter_key, FIXTURE_VIDEOS)
- FOUND: `tests/integration/README.md` (96 lines; contains RUN_INTEGRATION_TESTS=1, short.mp4, medium.mp4, long.mp4)
- FOUND: `tests/integration/test_phase7_integration_gemini.py` (105 lines; 3 test functions; module-level integration marker)
- FOUND: `tests/integration/test_phase7_integration_openrouter.py` (101 lines; 3 test functions; module-level integration marker)
- FOUND: `pytest.ini` (with `[pytest]` + `integration:` marker line)
- FOUND: `.gitignore` line `tests/integration/fixtures/`
- FOUND: commit `dba3878` (scaffold)
- FOUND: commit `9e2c9a3` (Gemini suite)
- FOUND: commit `c429376` (OpenRouter suite)
- VERIFIED: `pytest tests/integration/ -v` -> 6 SKIPs, 0 failures
- VERIFIED: `pytest -m integration tests/integration/` -> 6 collected
- VERIFIED: `pytest -m 'not integration' tests/integration/` -> 0 collected
- VERIFIED: no `PytestUnknownMarkWarning` in output
