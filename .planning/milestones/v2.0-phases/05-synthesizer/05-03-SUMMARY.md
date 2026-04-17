---
phase: 05-synthesizer
plan: 03
subsystem: synthesis

tags:
  - synthesis
  - llm
  - openrouter
  - accept-reject
  - gemini-2.5-flash

# Dependency graph
requires:
  - phase: 05-synthesizer/01
    provides: synthesize_pipeline, match_base_pipeline, STAGING_DIR, _build_slug, _write_staging
  - phase: 05-synthesizer/02
    provides: validate_synthesized_pipeline, raise_if_invalid, SynthesisValidationError, _load_synthesis_schema
  - phase: 03-openrouter
    provides: openai>=1.0 SDK pointed at OpenRouter base_url; VIDEO_ANALYZER provider reference pattern
  - phase: 01-foundation
    provides: schemas/artifacts/pipeline_synthesis.schema.json (enum valid|invalid|pending)

provides:
  - lib/llm_fill.py (fill_stage_details — bounded, fallback-on-failure LLM helper)
  - accept_synthesis(slug) → (Path, record) — the ONLY authorized write into pipeline_defs/
  - reject_synthesis(slug) → record — staging unlink + rejection record
  - LLM fill wired into synthesize_pipeline via use_llm_fill argument + VIDEO_SYNTH_LLM_FILL env
  - Order-aware SYNTH-10 contract guard (accept_synthesis permitted; synthesize_and_accept forbidden)
  - End-to-end contract test synthesize → validate → accept with mocked LLM (no API key required)

affects:
  - phase-06 (meta skill reference-synthesis will call these functions)
  - cost tracking (v2.1) — LLM fill cost recording deferred (OBS-01)

# Tech tracking
tech-stack:
  added:
    - openrouter routing for google/gemini-2.5-flash (text-only chat completion)
  patterns:
    - "Advisory-helper pattern: never-raises fallback to input on any failure"
    - "Retry-bounded LLM call (_MAX_ATTEMPTS=2) with JSON parse retries only"
    - "Post-merge semantic validation as LLM safety net (T-05-14 spoofing mitigation)"
    - "Separation-of-concerns: accept/reject are SEPARATE named functions, not wrapped (SYNTH-10)"
    - "Order-aware regex guard: synthes\\w*accept forbidden, accept_synthesis permitted"

key-files:
  created:
    - lib/llm_fill.py
    - tests/unit/test_llm_fill.py
    - tests/unit/test_accept_reject.py
  modified:
    - lib/pipeline_synthesizer.py
    - tests/contracts/test_phase5_synthesis.py
    - .planning/phases/05-synthesizer/deferred-items.md

key-decisions:
  - "LLM fill uses response_format=json_object + in-prompt schema (not json_schema) for OpenRouter passthrough breadth (Pitfall 4)"
  - "FILLABLE_FIELDS = (tools_available, review_focus, success_criteria) — structural keys never modified"
  - "Merge drops stages not in base manifest (SYNTH-03 hard rule: LLM can't invent structure)"
  - "accept_synthesis re-validates the promoted manifest and encodes result in record.validation_status"
  - "reject_synthesis emits validation_status=invalid (schema enum has no 'rejected' — Pitfall 2)"
  - "LLM fill resolution: use_llm_fill=True forces on; =False forces off; =None delegates to VIDEO_SYNTH_LLM_FILL env"
  - "Staging file preserved on FileExistsError (no partial state — caller retries with different slug)"

patterns-established:
  - "Fallback ladder documented in module docstring: env → key → SDK error → JSON parse (1 retry) → post-merge validation → happy path"
  - "API-key-free test suite: every LLM test mocks openai.OpenAI at the module level (lf.OpenAI)"
  - "Contract guard on lib source (regex over def statements) — structural, grep-verifiable rule"

requirements-completed:
  - SYNTH-03
  - SYNTH-10

# Metrics
duration: 7m 2s
completed: 2026-04-17
---

# Phase 05 Plan 03: LLM Fill + Accept/Reject API Summary

**OpenRouter-backed advisory LLM fill (google/gemini-2.5-flash) with 6-step fallback + explicit accept_synthesis/reject_synthesis API — the single authorized write into pipeline_defs/.**

## Performance

- **Duration:** 7m 2s
- **Started:** 2026-04-17T21:43:08Z
- **Completed:** 2026-04-17T21:50:10Z
- **Tasks:** 2 (both TDD — RED then GREEN)
- **Files modified:** 6 (2 new lib files, 2 new test files, 2 modified)

## Accomplishments

- `lib/llm_fill.py` — bounded OpenRouter text-only helper; 322 lines. Never raises; falls back to base on any failure (env opt-out, missing key, SDK exception, double JSON parse failure, post-merge semantic validation failure).
- `accept_synthesis(slug) → (Path, record)` added to `lib/pipeline_synthesizer.py` — the ONE authorized write into `pipeline_defs/`. Post-promotion re-validation encodes the result into the returned record's `validation_status`.
- `reject_synthesis(slug) → record` — staging unlink + schema-valid rejection record (`validation_status="invalid"` per Pitfall 2 resolution).
- LLM fill wired into `synthesize_pipeline` — precedence: `use_llm_fill=True/False` argument overrides; `None` delegates to `VIDEO_SYNTH_LLM_FILL` env.
- Order-aware SYNTH-10 contract guard: `synthes\w*accept` forbidden, `accept_synthesis`/`reject_synthesis` permitted.
- End-to-end contract test (`test_end_to_end_synthesize_accept`) exercises synthesize → validate → accept with mocked LLM — zero API keys required.
- Test suite: 28 new tests (10 unit/llm_fill, 11 unit/accept_reject, 1 contract e2e) — all green; full Phase 5 regression (72 tests) green.

## Task Commits

Each task shipped as TDD RED → GREEN pair:

1. **Task 1 RED: failing tests for lib/llm_fill.py** — `930c9fb` (test)
2. **Task 1 GREEN: lib/llm_fill.py bounded OpenRouter helper** — `ecee252` (feat)
3. **Task 2 RED: failing tests for accept/reject + LLM wiring + e2e** — `89ce625` (test)
4. **Task 2 GREEN: accept_synthesis + reject_synthesis + LLM wiring** — `b796305` (feat)

## Files Created/Modified

- `lib/llm_fill.py` — Advisory LLM helper with 6-step fallback ladder (322 lines).
- `lib/pipeline_synthesizer.py` — Extended with `accept_synthesis`, `reject_synthesis`, `_relative_staging_path`, and LLM fill branching inside `synthesize_pipeline`. Added imports: `os`, `shutil`, `deepcopy`. (+162 lines net)
- `tests/unit/test_llm_fill.py` — 10 behaviors mocking `openai.OpenAI` (422 lines).
- `tests/unit/test_accept_reject.py` — 11 behaviors (335 lines).
- `tests/contracts/test_phase5_synthesis.py` — Order-aware guard regex + end-to-end test.
- `.planning/phases/05-synthesizer/deferred-items.md` — Logged pre-existing Phase 2 `fc-list` env gap.

## Decisions Made

1. **Advisory-never-raises contract for `fill_stage_details`** — any exception (APIError, APIConnectionError, unexpected) is caught and the base manifest returned. Synthesizer determinism takes priority over LLM enrichment.
2. **`response_format={"type": "json_object"}` + in-prompt schema** (not `json_schema`) — broader OpenRouter passthrough per Phase 3 Pitfall 4.
3. **`_merge_stage_details` drops extra stages silently** — SYNTH-03 enforced in the merge step; prompt also tells the model, but merge is the non-negotiable guard.
4. **`accept_synthesis` returns `(Path, record)` tuple** (plan allowed this or `Path` alone) — tuple chosen because the meta skill needs the schema-validated record to persist run history without re-constructing it.
5. **`accept_synthesis` on FileExistsError preserves staging** — no partial-state; caller retries with a different slug after inspecting the conflict.
6. **Rejection encoded as `validation_status="invalid"`** — schema enum has no `"rejected"` value; Pitfall 2 resolution. Phase 6 meta skill preserves human-sentiment context (rejection reason) alongside.
7. **Order-aware SYNTH-10 regex `synthes\w*accept`** — forbids `synthesize_and_accept`, `synth_accept`; permits `accept_synthesis`, `reject_synthesis`.

## Deviations from Plan

None — plan executed exactly as written. TDD sequence preserved; fallback ladder from `<fallback_contract>` implemented verbatim; test counts meet or exceed plan minimums (10/6/1 vs plan 5/6/1).

## Issues Encountered

- **Deferred (out-of-scope):** `tests/contracts/test_phase2_contracts.py::TestCodeSnippetUnit::test_render_python` fails with `FileNotFoundError: 'fc-list'` — pre-existing devcontainer env gap (fontconfig binary absent). Logged to `deferred-items.md`; unrelated to Phase 5.

## LLM Behavior Notes

All LLM tests use mocked `openai.OpenAI`. Observed mock behavior:
- `_MAX_ATTEMPTS=2`: single retry on JSON parse failure only; SDK exceptions get the same retry budget (both attempts funnel through the same try/except).
- Prompt distinction: `template` mode contains `"generalizable"`; `replica` mode contains `"closer reproduction"`. Test 8 asserts both substrings appear in the exact mode they should.
- `max_tokens=2000` always passed; tests inspect `client.chat.completions.create.call_args.kwargs`.
- No live-API smoke run executed (by design — plan specifies API-key-free test suite).

## Full Phase 5 Public API Surface (one-line summary)

```python
# lib/pipeline_synthesizer.py
synthesize_pipeline(analysis, *, mode, provider_used, use_llm_fill)  -> record dict
match_base_pipeline(analysis)                                        -> {base_pipeline, match_score, alternatives}
validate_synthesized_pipeline(manifest)                              -> list[str] (issues)
raise_if_invalid(manifest)                                           -> None (raises SynthesisValidationError)
accept_synthesis(slug)                                               -> (Path, record)   # Plan 05-03
reject_synthesis(slug)                                               -> record           # Plan 05-03
SynthesisValidationError(issues: list[str])
STAGING_DIR, PIPELINE_DEFS_DIR constants

# lib/llm_fill.py (Plan 05-03)
fill_stage_details(base_manifest, analysis, *, mode)                 -> manifest dict
```

## Full Phase 5 Test Count + Pass Rate

- **tests/unit/test_pipeline_synthesizer.py** — 19 tests, 100% green (05-01 + 05-02)
- **tests/unit/test_semantic_validation.py** — 9 tests, 100% green (05-02)
- **tests/unit/test_llm_fill.py** — 10 tests, 100% green (05-03)
- **tests/unit/test_accept_reject.py** — 11 tests, 100% green (05-03)
- **tests/contracts/test_phase5_synthesis.py** — 6 tests, 100% green (05-02 + 05-03)
- **tests/contracts/test_pipeline_synthesis_schema.py** — 17 tests, 100% green (Phase 1 regression, unchanged)

**Total Phase 5 test count: 72 tests, 100% pass rate.**

## User Setup Required

None — no new env vars required for Phase 5 to ship. `VIDEO_SYNTH_LLM_FILL` is an optional opt-out; `OPENROUTER_API_KEY` is shared with the Phase 3 provider (already provisioned). `VIDEO_SYNTH_LLM_MODEL` is optional (default: `google/gemini-2.5-flash`).

## Next Phase Readiness — Hand-off to Phase 6

**Meta skill `skills/meta/reference-synthesis.md` integration contract:**

1. Call `synthesize_pipeline(video_analysis_artifact, mode="template"|"replica")` — returns schema-valid run record with `staging_path`.
2. Read the staged YAML; render diff against base for the user (record already carries `diff_against_base` as a unified diff string).
3. Present match_score + alternatives; ask the user to approve, revise, or reject.
4. On approval: `accept_synthesis(slug)` → promoted pipeline lives under `pipeline_defs/<slug>.yaml`; persist the returned record to the project's run log.
5. On rejection: `reject_synthesis(slug)` → staging unlinked; persist the returned record with any user-provided reason attached.

**Dependency status:**
- `requirements.txt` already has `ruamel.yaml` (Plan 05-01 added it). Phase 6 INT-02 becomes a no-op confirmation.
- No new env vars required for Phase 5 to ship.
- Order-aware SYNTH-10 guard in contract test prevents future refactors from introducing a combined synthesize+accept path.

## Self-Check: PASSED

- `lib/llm_fill.py` — FOUND (322 lines, meets plan min 140)
- `lib/pipeline_synthesizer.py` — FOUND (692 lines post-edit; contains `accept_synthesis`, `reject_synthesis`, `fill_stage_details` import)
- `tests/unit/test_llm_fill.py` — FOUND (422 lines, 10 tests)
- `tests/unit/test_accept_reject.py` — FOUND (335 lines, 11 tests)
- `tests/contracts/test_phase5_synthesis.py` — FOUND (extended with Test 6 e2e)
- Commits `930c9fb`, `ecee252`, `89ce625`, `b796305` — all FOUND in `git log`
- Full Phase 5 regression (72 tests) — GREEN
- Pipelines all load — 12/12 verified
- API surface — `from lib.pipeline_synthesizer import accept_synthesis, reject_synthesis, synthesize_pipeline, validate_synthesized_pipeline, SynthesisValidationError; from lib.llm_fill import fill_stage_details` — OK
- `grep -nE "^def\s+(synthes\w*accept)" lib/pipeline_synthesizer.py` — empty (no forbidden combined function)
- `OPENROUTER_API_KEY` — only used via `os.environ.get` / `os.environ[key]`, never logged

---
*Phase: 05-synthesizer*
*Completed: 2026-04-17*
