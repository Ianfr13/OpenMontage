---
phase: 05-synthesizer
plan: 02
subsystem: synthesis

tags: [semantic-validation, jsonschema, unified-diff, registry, loader-hardening]

requires:
  - phase: 05-synthesizer
    provides: lib/pipeline_synthesizer core (matcher + slug + staging writer)
  - phase: 01-contracts
    provides: pipeline_synthesis.schema.json (SYNTH-09 shipped; here we honor it)

provides:
  - lib/pipeline_synthesizer.SynthesisValidationError (exception)
  - lib/pipeline_synthesizer.validate_synthesized_pipeline(manifest) -> list[str]
  - lib/pipeline_synthesizer.raise_if_invalid(manifest) — escalation helper
  - lib/pipeline_synthesizer._unified_diff(base, synth, base_name) — internal diff helper
  - synthesize_pipeline now emits a jsonschema-validated run record with validation_status in {valid, invalid}
  - lib/pipeline_loader.list_pipelines() explicit underscore-prefix filter (SYNTH-07 defense-in-depth)

affects: [05-03 accept/reject+LLM fill, 06 meta-skill]

tech-stack:
  added: []
  patterns:
    - "Validator-returns-list-of-strings, raise-is-opt-in helper on top"
    - "Emit-then-validate record (jsonschema.validate BEFORE return to guarantee downstream consumers see a well-formed record)"
    - "Unified-diff from same ruamel config used by staging writer — diff reflects actual YAML bytes"

key-files:
  created:
    - tests/unit/test_semantic_validation.py
    - tests/contracts/test_phase5_synthesis.py
    - .planning/phases/05-synthesizer/deferred-items.md
  modified:
    - lib/pipeline_synthesizer.py
    - lib/pipeline_loader.py
    - tests/unit/test_pipeline_synthesizer.py

key-decisions:
  - "validation_status enum resolution: synthesize_pipeline emits 'valid' OR 'invalid' only; 'pending' is reserved for future async flows and never emitted by this code path (Pitfall 2)"
  - "Validator returns list[str]; raise_if_invalid is opt-in. Callers that want explicit escalation call raise_if_invalid; the synthesizer does not short-circuit on invalid — record is still returned with validation_status='invalid'"
  - "Test fixture switched from cinematic to animated-explainer because cinematic.yaml references 'web_search' which is not a registered BaseTool (pre-existing desync; logged in deferred-items.md)"
  - "Plan 05-01 module-shape test relaxed to allow Exception subclasses — SynthesisValidationError is idiomatic Python and does not violate SYNTH-01's 'no class' rule (confirmed in 05-01 handoff notes)"
  - "Unified diff uses the EXACT same ruamel.yaml configuration as the staging writer — diff reflects actual on-disk bytes, not Python dict repr"

patterns-established:
  - "Validator API: callable returns list[str] issues (empty = pass); separate raise_if_invalid() for explicit escalation; never raise from the validator itself"
  - "SynthesisValidationError.issues: list[str] — callers treat as display text, not machine-parsed format"
  - "Emit-then-validate: record.validate BEFORE return so producer catches shape drift — downstream consumers never see a malformed record"

requirements-completed: [SYNTH-07, SYNTH-08]

duration: 7min
completed: 2026-04-17
---

# Phase 5 Plan 02: Semantic Validation + Run-Record Emission Summary

**Semantic validator (skill-path + tool-registry checks), SynthesisValidationError, unified-diff against base, and jsonschema-validated run records — plus loader defense-in-depth filter. 33 tests green.**

## Performance

- **Duration:** 7 min 25 sec
- **Started:** 2026-04-17T21:31:49Z
- **Completed:** 2026-04-17T21:39:14Z
- **Tasks:** 2 (TDD red/green for each)
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments

- `validate_synthesized_pipeline(manifest) -> list[str]` — checks every stage's `skill:` path exists under `skills/*.md` AND every `tools_available` entry is in `registry.list_all()` after `registry.ensure_discovered()`.
- `SynthesisValidationError(Exception)` + `raise_if_invalid(manifest)` — optional escalation helper; validator itself never raises.
- `synthesize_pipeline` now emits a record with `validation_status in {"valid", "invalid"}`, a unified-diff `diff_against_base`, and an ISO-8601 `created_at`; record is `jsonschema.validate`-d against `pipeline_synthesis.schema.json` before return.
- `list_pipelines()` hardened with explicit `startswith("_")` filter — defense-in-depth against a future switch to recursive glob (SYNTH-07 + Pitfall 1).
- 9 new unit tests (`test_semantic_validation.py`) + 7 new unit tests (extended `test_pipeline_synthesizer.py`) + 5 new contract tests (`test_phase5_synthesis.py`) — all 33 green; full unit+contract regression (minus pre-existing fontconfig failures) at 473 pass, 0 fail.

## Task Commits

1. **Task 1 RED: failing tests for semantic validation + loader hardening** — `195170d` (test)
2. **Task 1 GREEN: validator + SynthesisValidationError + loader filter** — `39b22eb` (feat)
3. **Task 2 RED: failing tests for record emission + diff + validation_status** — `0cd7121` (test)
4. **Task 2 GREEN: wire validation + diff into synthesize_pipeline record** — `73f6ed7` (feat)

Plan metadata commit follows in `final_commit` step.

## Files Created/Modified

**Created:**
- `tests/unit/test_semantic_validation.py` — 9 behaviors (SYNTH-07 + SYNTH-08)
- `tests/contracts/test_phase5_synthesis.py` — 5 contract tests (record → schema; no-auto-approval guard)
- `.planning/phases/05-synthesizer/deferred-items.md` — cinematic.yaml web_search desync

**Modified:**
- `lib/pipeline_synthesizer.py` — add `SKILLS_DIR`, `SynthesisValidationError`, `validate_synthesized_pipeline`, `raise_if_invalid`, `_load_synthesis_schema`, `_unified_diff`; wire them into `synthesize_pipeline` return path; record now `jsonschema.validate`-d
- `lib/pipeline_loader.py` — `list_pipelines()` explicit underscore-prefix filter
- `tests/unit/test_pipeline_synthesizer.py` — relax module-shape test to allow Exception subclasses; append 7 new tests for Plan 05-02 record behavior

## Decisions Made

- **validation_status enum resolution:** `synthesize_pipeline` emits only `"valid"` or `"invalid"`. `"pending"` is reserved for future async validation flows and is never emitted by this code path. This honors Pitfall 2 without extending the schema.
- **Opt-in raising:** `validate_synthesized_pipeline` is non-raising; callers that want escalation call `raise_if_invalid`. The synthesizer itself returns the record even when `validation_status == "invalid"` so the Plan 05-03 meta skill can surface issues to the user with full context.
- **Validator-checks-scope:** only skill existence + tool membership. Schema-shape validation is already handled by `load_pipeline` (which calls `jsonschema.validate` against `pipeline_manifest.schema.json`). No redundant check here.
- **Diff format:** unified-diff via `difflib.unified_diff`, dumping both manifests through the same `ruamel.yaml` config as the staging writer. This ensures the diff reflects on-disk bytes, not Python dict repr. Diff is empty string when synthesized equals base (template mode without LLM fill — the Plan 05-02 steady state).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Relax Plan 05-01 module-shape test to allow Exception subclasses**

- **Found during:** Task 1 GREEN verification (running `tests/unit/test_pipeline_synthesizer.py`)
- **Issue:** The Plan 05-01 test `test_module_shape` asserted `local_classes == []` — i.e., NO locally-defined classes at all. Plan 05-02 adds `SynthesisValidationError(Exception)`, which is idiomatic Python (not an orchestration class) and explicitly endorsed in the Plan 05-01 SUMMARY handoff note.
- **Fix:** Narrowed the assertion to non-exception classes only: `not issubclass(obj, BaseException)`. Documented the reasoning inline.
- **Files modified:** `tests/unit/test_pipeline_synthesizer.py`
- **Verification:** All 12 Plan 05-01 tests + 7 new Plan 05-02 unit tests green.
- **Committed in:** `39b22eb` (Task 1 GREEN commit — the test relaxation and the new code are a paired change)

**2. [Rule 3 - Scope Boundary] Fixture switched from cinematic to animated-explainer**

- **Found during:** Task 1 `test_validate_empty_returns_no_issues` first run — cinematic.yaml reported one validation issue.
- **Issue:** `pipeline_defs/cinematic.yaml` lists `web_search` in its `research` stage's `tools_available`, but `web_search` is NOT registered in `tools/tool_registry` (it's not a BaseTool — likely an intrinsic agent capability). The validator correctly reports this as an unknown tool. The desync is pre-existing and unrelated to Plan 05-02.
- **Fix:** Switched the "clean base manifest" test fixture from `cinematic` to `animated-explainer` (audited all 12 pipelines: only `cinematic` is dirty). Logged the cinematic desync to `.planning/phases/05-synthesizer/deferred-items.md` with remediation options for a future plan.
- **Files modified:** `tests/unit/test_semantic_validation.py`, `.planning/phases/05-synthesizer/deferred-items.md`
- **Verification:** `test_validate_empty_returns_no_issues` now green; audit script confirms `animated-explainer` has zero unknown tools / zero missing skills.
- **Committed in:** `39b22eb` (Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - Blocking).
**Impact on plan:** Both were necessary to complete the task on a project in its real state — no scope creep. The cinematic desync is deferred, not silently ignored.

## Issues Encountered

- None beyond the two Rule-3 deviations above. Tests drove implementation cleanly.
- The `web_search` desync in `cinematic.yaml` is a real issue for that pipeline but is not a Phase 5 Plan 02 concern. It is documented in `deferred-items.md` for a future audit plan.

## Downstream-consumer format notes

- `diff_against_base` is **unified-diff text** (lines starting with `---`, `+++`, `@@`, `-`, `+`) OR an empty string. Consumers should handle empty-string as "no diff" (template mode steady state) rather than treating it as an error.
- `created_at` is an ISO-8601 UTC timestamp with `+00:00` suffix and seconds precision (e.g., `2026-04-17T21:38:55+00:00`). The schema doesn't constrain format beyond `string`, so consumers should parse defensively.
- `validation_status` is a closed enum `{"valid", "invalid", "pending"}` per schema. This plan emits only `"valid"` or `"invalid"`. Plan 05-03's `accept_synthesis`/`reject_synthesis` will emit additional records using the same enum (not `"accepted"`/`"rejected"` — those values are not in the schema).

## Hand-off notes for Plan 05-03

Plan 05-03 adds `accept_synthesis(slug)` and `reject_synthesis(slug)` plus LLM fill. Critical constraints:

1. **Both accept/reject MUST emit a NEW run record that validates against `pipeline_synthesis.schema.json`.** The staged file at `_staging/<slug>.yaml` can be re-loaded and re-validated via `validate_synthesized_pipeline` then recorded as `validation_status = "valid"` after promotion (or `"invalid"` if the reject is a rejection-due-to-validation-failure).
2. **NO function combining synthesize + accept.** The `test_no_auto_approval_path` contract test enforces this structurally — `accept_synthesis` and `reject_synthesis` must have names that do not contain both "synthes" and "accept" (current proposed names are fine).
3. **User-sentiment labels (accepted/rejected) do NOT go in `validation_status`.** The schema enum is closed to `valid|invalid|pending`. User-action metadata belongs in a different field (e.g., surface via `diff_against_base` narrative, a future `user_action` field, or logs). Do NOT extend the schema in Plan 05-03 without user approval.
4. **LLM fill output MUST be re-validated.** After filling stage details, call `validate_synthesized_pipeline` again before writing to `_staging/`. LLM can introduce unknown tool names or malformed skill paths — these MUST be caught before the user sees the diff.
5. **`_unified_diff` helper is already exported** from `lib.pipeline_synthesizer` (underscore-prefixed but accessible). Plan 05-03's accept-record writer should reuse it rather than re-implement diff logic.

## Self-Check: PASSED

```
[FOUND] lib/pipeline_synthesizer.py
[FOUND] lib/pipeline_loader.py
[FOUND] tests/unit/test_semantic_validation.py
[FOUND] tests/contracts/test_phase5_synthesis.py
[FOUND] .planning/phases/05-synthesizer/deferred-items.md
[FOUND] commit 195170d (Task 1 RED)
[FOUND] commit 39b22eb (Task 1 GREEN)
[FOUND] commit 0cd7121 (Task 2 RED)
[FOUND] commit 73f6ed7 (Task 2 GREEN)
[VERIFIED] grep 'startswith("_")' lib/pipeline_loader.py → match at line 66
[VERIFIED] all exports importable: validate_synthesized_pipeline, SynthesisValidationError, raise_if_invalid, synthesize_pipeline
[VERIFIED] grep -nE "def\s+\w*synthes\w*accept" lib/pipeline_synthesizer.py → empty (SYNTH-10 structural guard)
[VERIFIED] 33/33 new + existing tests green (pytest tests/unit/test_pipeline_synthesizer.py tests/unit/test_semantic_validation.py tests/contracts/test_phase5_synthesis.py)
[VERIFIED] full unit+contract regression 473 pass, 0 fail, 6 skip (minus pre-existing fontconfig failures)
```

---
*Phase: 05-synthesizer*
*Completed: 2026-04-17*
