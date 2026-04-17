# Phase 7: Research

**Date:** 2026-04-17
**Confidence:** HIGH

## Scope

Phase 7 closes the milestone by consolidating tests. Primary research concern: how to structure integration tests that require real API keys without breaking the default `pytest` run.

## Key Findings

### Pytest marker pattern for integration tests
Use `@pytest.mark.integration` + `@pytest.mark.skipif(not os.getenv("RUN_INTEGRATION_TESTS"), reason="set RUN_INTEGRATION_TESTS=1")` combo. Register the marker in `pytest.ini` or `pyproject.toml`.

### Fixture file strategy
- Fixtures live in `tests/integration/fixtures/` (gitignored — videos are 10MB-100MB)
- Add fixture paths + download README to plan
- Skipif also gates on fixture file presence: `skipif(not fixture_video.exists(), reason="fixture missing")`

### Backward compat gate
- Single parametrized test: iterates `pipeline_defs/*.yaml` via `Path("pipeline_defs").glob("*.yaml")`
- Each YAML must load via `pipeline_loader.load_pipeline(path)` without raising
- Schema validation via `pipeline_manifest.schema.json` (already extended in Phase 5 for expected_analysis)

### Cross-provider numeric tolerance
- Float extraction from `editing_pacing.cuts_per_minute` (canonical schema)
- Tolerance check: `assert abs(a - b) / max(a, b) <= 0.15`
- Pacing style match: strict equality on enum value

### E2E smoke scope
- Mocked-only (no real API calls) — simulates reference-synthesis.md meta skill flow
- Inputs: fixture canonical artifact (use existing minimal_video_analysis from Phase 1 contract tests)
- Asserts: synthesize → validate → accept produces a pipeline_defs/*.yaml that loads successfully

## Validation Architecture

### Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest 7.x (already in use) |
| Contract run | `pytest tests/contracts/ -q` (no keys needed) |
| Unit run | `pytest tests/unit/ -q` (no keys needed) |
| Integration run | `RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -q` (needs GEMINI_API_KEY or OPENROUTER_API_KEY + fixture videos) |
| Full run | all above combined |
| Estimated runtime | <30s contracts + unit; integration varies (minutes per video) |

### Sampling Rate

- After task commit: run affected subset
- Full suite before verify

### Per-Task Verification Map

| Task | Plan | REQ | Verification |
|------|------|-----|--------------|
| 07-01-01 | 01 | TEST-01, TEST-03 | `pytest tests/contracts/ -q` passes; `pytest tests/contracts/test_v1_backward_compat.py -q` shows 12 pipelines loaded |
| 07-02-01 | 02 | TEST-02 | `pytest tests/integration/ -q` skips cleanly when `RUN_INTEGRATION_TESTS` unset |
| 07-03-01 | 03 | TEST-04 | `pytest tests/contracts/test_phase7_e2e_smoke.py -q` passes |
| 07-03-02 | 03 | TEST-05 | Mocked-mode cross-provider consistency test passes; real-mode skipif-gated |

### Wave 0 Requirements

- Register `integration` marker in pytest config
- Create `tests/integration/` directory + `__init__.py`
- Add `tests/integration/fixtures/` to .gitignore

### Manual-Only Verifications

- Integration test suite run with real API keys — user executes `RUN_INTEGRATION_TESTS=1 GEMINI_API_KEY=... OPENROUTER_API_KEY=... pytest tests/integration/ -q` post-milestone with fixture videos
