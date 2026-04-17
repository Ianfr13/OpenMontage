# Phase 7: Tests - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, final phase)

<domain>
## Phase Boundary

Consolidate and extend the test suite to close the milestone. Contract tests already exist across Phases 1-5 (341+ tests). Phase 7 adds: integration tests gated by `RUN_INTEGRATION_TESTS=1` (real API calls against Gemini and OpenRouter), backward-compat gate (confirms all 12 existing pipeline_defs/*.yaml still load), E2E smoke test (reference-synthesis flow from fixture video → synthesized YAML), cross-provider numeric-tolerance consistency test (cuts_per_minute within ±15%, pacing_style enum match).

Out of scope: adding unit tests for Phase 2-5 code (already covered); SKILL-03 real-video quality gate (manual, HUMAN-UAT).

</domain>

<decisions>
## Implementation Decisions

### Plan Decomposition (3 plans)
- `07-01-PLAN.md` — Contract test consolidation + backward-compat gate. TEST-01, TEST-03. Lightweight: add `tests/contracts/test_v1_backward_compat.py` asserting all 12 pipeline_defs load; smoke-test `make test-contracts` command (or `pytest tests/contracts/` equivalent) runs API-key-free.
- `07-02-PLAN.md` — Integration tests gated by env var. TEST-02. New `tests/integration/` directory with `test_phase7_integration_gemini.py` and `test_phase7_integration_openrouter.py`. Each covers 3 fixture videos (short <2min, medium 3-5min, long >5min chunked). Gated by `RUN_INTEGRATION_TESTS=1`. Skipped if no key present.
- `07-03-PLAN.md` — E2E smoke + cross-provider numeric tolerance. TEST-04, TEST-05. `tests/contracts/test_phase7_e2e_smoke.py` mocks providers to simulate reference-synthesis flow end-to-end. Cross-provider test parametrizes over fixture video, asserts cuts_per_minute within ±15%, pacing_style enum match (runs with `RUN_INTEGRATION_TESTS=1` when real keys set; otherwise uses deterministic mock fixture).

### Integration Test Fixtures
- Location: `tests/integration/fixtures/` (gitignored — fixtures are large)
- User provides videos manually post-phase OR we use video-download skill to grab 3 Creative Commons clips
- Since no fixture videos exist in repo yet, integration tests will be `skipif` gated on fixture file existence AS WELL as `RUN_INTEGRATION_TESTS=1` — this prevents test failures when fixtures are missing
- Plan must document how to populate fixtures (README in tests/integration/)

### Backward Compat Gate (TEST-03)
- Simple test: iterate `pipeline_defs/*.yaml`, call `pipeline_loader.load_pipeline(path)`, assert no exception
- All 12 must load (including the ones Phase 5 annotated with `expected_analysis`)
- Catches schema-breaking changes to manifest schema

### Cross-Provider Consistency (TEST-05)
- Two modes:
  - Mocked mode (always runs): both providers mocked to return same canonical artifact; asserts shape/keys match (this is the Phase 3 ANLZ-06 test — already exists)
  - Real mode (RUN_INTEGRATION_TESTS=1): parametrize both providers on same fixture video; extract `cuts_per_minute` from each; assert `abs(gemini_cpm - openrouter_cpm) / max(gemini_cpm, openrouter_cpm) <= 0.15` (±15%); assert `pacing_style` matches

### E2E Smoke (TEST-04)
- Mocked-only: mocks `video_analyzer_selector` to return a canonical analysis artifact; calls `synthesize_pipeline(analysis)` → gets staging path; calls `validate_synthesized_pipeline(yaml)` → passes; calls `accept_synthesis(slug)` → moves to pipeline_defs; cleanup
- Verifies the full flow in Phase 6's reference-synthesis.md meta skill works end-to-end
- Fixture in tests/fixtures/ if not already

### Claude's Discretion
- Exact fixture URL sources (YouTube CC clips) — planner can research; recommend placeholder `README.md` with download instructions
- Whether to add `pytest.ini` / `conftest.py` marker for `integration` — recommend yes for clean test filtering

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- 341+ existing tests across tests/unit/ and tests/contracts/ (Phases 1-5)
- ANLZ-06 cross-provider shape test already exists in tests/contracts/test_phase3_openrouter_contracts.py
- conftest.py already has fixture infrastructure + autouse env scrubbing
- lib/pipeline_loader.py + pipeline_defs/*.yaml ready for backward-compat test

### Established Patterns
- Tests use `pytest` with inline dict fixtures where possible
- API-key-free via `monkeypatch.delenv` autouse fixture
- Mock SDK modules at module scope
- Contract tests live in `tests/contracts/`; unit tests in `tests/unit/`; new: `tests/integration/`

</code_context>

<specifics>
## Specific Ideas

- Integration tests: `pytest.mark.skipif(not os.getenv("RUN_INTEGRATION_TESTS"), reason="...")` decorator
- Mark `@pytest.mark.integration` for filtering (`pytest -m 'not integration'` for CI)
- Fixtures gitignored: add `tests/integration/fixtures/` to `.gitignore`

</specifics>

<deferred>
## Deferred Ideas

- Performance benchmarks (latency per chunk, concurrency saturation) — v2.1
- Load testing (concurrent synthesis requests) — v2.1

</deferred>
