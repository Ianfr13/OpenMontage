---
phase: 10-synthesizer-record-validity
plan: 02
subsystem: schema-integrity
tags: [schema-split, artifact-contract, synthesizer, clean-09, audit-fidelity]

# Dependency graph
requires:
  - phase: v2.0-05-synthesizer
    provides: "accept_synthesis / reject_synthesis public API + legacy pipeline_synthesis schema (unchanged)"
  - phase: 10-01
    provides: "InvalidPipelineSlug guard at the top of accept/reject entry points — lets Plan 10-02 focus on record-shape without re-deriving slug safety"
provides:
  - "schemas/artifacts/pipeline_acceptance.schema.json — dedicated post-accept record schema (promoted_slug, promoted_path, validation_status, created_at, optional validation_issues)"
  - "schemas/artifacts/pipeline_rejection.schema.json — dedicated post-reject record schema (rejected_slug, staging_path, created_at, optional reason)"
  - "accept_synthesis emits against pipeline_acceptance via validate_artifact; reject_synthesis emits against pipeline_rejection via validate_artifact"
  - "Deletion of all 4 CLEAN-09 sentinel patterns (match_score=0.0, base_pipeline=slug, \"post-accept\", \"post-reject\") from lib/pipeline_synthesizer.py"
  - "Removal of the Pitfall 2 hack (validation_status=\"invalid\" as user-rejection proxy) — rejection is now its own semantic event"
affects:
  - "phase 11 drift + NITS — no schema changes expected; Phase 11 can absorb NR-03 (_relative_staging_path misnaming) and the remaining NITS without touching Phase 10 contracts"
  - "phase 12 human UAT — fixture-driven review validates the new record shapes against real video analyses; no blocker because record shape is backward-compatible for any consumer that correlates by slug"
  - "any downstream audit consumer — must now correlate pipeline_synthesis (pre-approval) with pipeline_acceptance (post-promotion) by slug rather than reading match_score / source_analysis_checksum from the post-accept record"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Schema split over sentinel allow-list — when a single schema is reused for semantically distinct events, add a new schema rather than expanding the enum / allowing magic strings"
    - "Honest contract: every required field in a schema MUST be a field the event actually has; every optional field MUST describe real optionality, not a migration artefact"
    - "Audit-by-correlation pattern — the post-event record carries an identifier (slug) that lets consumers JOIN with the pre-event record; sentinel duplication is not needed"

key-files:
  created:
    - "schemas/artifacts/pipeline_acceptance.schema.json — draft-2020-12 schema, $id openmontage/artifacts/pipeline_acceptance, 5 required fields + 1 optional (validation_issues)"
    - "schemas/artifacts/pipeline_rejection.schema.json — draft-2020-12 schema, $id openmontage/artifacts/pipeline_rejection, 4 required fields + 1 optional (reason)"
  modified:
    - "schemas/artifacts/__init__.py — appended pipeline_acceptance + pipeline_rejection to ARTIFACT_NAMES (adjacent to pipeline_synthesis)"
    - "lib/pipeline_synthesizer.py — accept_synthesis + reject_synthesis now emit against new schemas via validate_artifact; sentinel fields deleted; docstrings updated to document the schema split and reference CLEAN-09 / v2.0 Phase 5 REVIEW MR-02"
    - "tests/unit/test_accept_reject.py — Test 7 loads pipeline_acceptance; Test 8 renamed test_reject_record_schema_valid, loads pipeline_rejection, asserts rejected_slug present + validation_status absent; module docstring index updated"
    - "tests/contracts/test_phase7_e2e_smoke.py — accept-roundtrip loads pipeline_acceptance for accept_record + asserts promoted_slug; reject test loads pipeline_rejection + asserts rejected_slug + staging_path prefix; Pitfall 2 validation_status assertion removed"
    - "tests/contracts/test_phase5_synthesis.py — Test 6 accept record loads pipeline_acceptance"

key-decisions:
  - "Schema split chosen over sentinel allow-list (CONTEXT.md D-CLEAN-09, locked before planning) — two new schemas carrying only fields the event actually has, rather than expanding pipeline_synthesis with a validation_status=rejected enum and nullable sentinels"
  - "pipeline_synthesis.schema.json left byte-identical — still governs the pre-approval synthesis event emitted by synthesize_pipeline; splitting would have forced a test cascade across test_phase5_synthesis.py tests 1-5 for zero correctness gain"
  - "No jsonschema.validate calls left in accept_synthesis / reject_synthesis — both entry points now route through validate_artifact, which wraps jsonschema.validate and resolves schema-by-name via SCHEMA_DIR. Removes a dual-pathway inconsistency (the existing ARTIFACT_NAMES convention is the single source of truth)"
  - "optional validation_issues on pipeline_acceptance — populates when validation_status=invalid, absent on valid records. Gives the meta-skill layer actionable structured data without forcing callers to look elsewhere when the promoted manifest has issues"
  - "reject schema has an optional reason field (not populated by this version) — pre-wires the schema for a future phase that forwards a user-provided rejection reason from the meta skill; adding it later would have required a schema version bump"

patterns-established:
  - "Dedicated-schema-per-semantic-event — when a handler emits structurally similar records for semantically distinct events, give each event its own schema rather than reusing one schema with discriminator fields. The contract is self-describing and misuse fails at validation, not at audit-time"
  - "Backward-compatible migration via append — the new schemas are added next to the legacy one; the legacy consumer path (synthesize_pipeline) is untouched; only the two handlers whose output-semantics changed were refactored"
  - "Test migration by schema-name swap — when a test pins an artifact shape, the update is a one-line load_schema() change plus a field assertion update; no test logic rewrite, no fixture rebuild"

requirements-completed: [CLEAN-09]

# Metrics
duration: 4min
completed: 2026-04-18
---

# Phase 10 Plan 02: Accept/Reject Record Schema Split Summary

**Split `pipeline_synthesis` catch-all into dedicated `pipeline_acceptance` + `pipeline_rejection` schemas; accept_synthesis + reject_synthesis now emit honest contracts carrying only fields the event actually has — all 4 CLEAN-09 sentinel patterns (`match_score=0.0`, `base_pipeline=slug`, `"post-accept"`, `"post-reject"`) deleted from `lib/pipeline_synthesizer.py` and the Pitfall 2 `validation_status="invalid"` rejection-proxy hack removed.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-18T01:43:31Z
- **Completed:** 2026-04-18T01:47:28Z
- **Tasks:** 3 (1 schema + 1 refactor + 1 test-migration)
- **Files created:** 2 (pipeline_acceptance.schema.json, pipeline_rejection.schema.json)
- **Files modified:** 4 (__init__.py, pipeline_synthesizer.py, test_accept_reject.py, test_phase7_e2e_smoke.py, test_phase5_synthesis.py)

## Accomplishments

- Two new draft-2020-12 schemas (`schemas/artifacts/pipeline_acceptance.schema.json` and `schemas/artifacts/pipeline_rejection.schema.json`) mirror `pipeline_synthesis.schema.json` styling ($id prefix, title, top-level description, per-property description, required array, version const "1.0"). Neither carries the sentinel fields — promoted_slug + promoted_path + validation_status + created_at on accept; rejected_slug + staging_path + created_at on reject.
- Both schemas registered in `ARTIFACT_NAMES` (adjacent to `pipeline_synthesis`) and load via the existing `load_schema` / `validate_artifact` helpers — zero bespoke validator code, zero dual-pathway inconsistency.
- `accept_synthesis` refactored to emit against `pipeline_acceptance`: tuple return shape `(Path, dict)` preserved per CONTEXT.md; record carries `promoted_slug` (was `base_pipeline`), `promoted_path` (repo-relative path to the promoted YAML), `validation_status` (semantic validation of the promoted manifest), `created_at`, and optional `validation_issues` list when status=invalid. All sentinel writes deleted.
- `reject_synthesis` refactored to emit against `pipeline_rejection`: record carries `rejected_slug`, `staging_path` (repo-relative path where staged YAML used to live), `created_at`. No `validation_status` field — Pitfall 2 hack (`validation_status="invalid"` as user-rejection proxy) removed. Optional `reason` field reserved for future meta-skill phase.
- `synthesize_pipeline` path completely untouched — still emits `pipeline_synthesis` via `_load_synthesis_schema()` for the pre-approval synthesis event. Legacy consumers who read pipeline_synthesis for synthesis-time context continue to work.
- 3 test files updated with one-line schema-name swaps + field-assertion migrations: `tests/unit/test_accept_reject.py` (tests 7, 8), `tests/contracts/test_phase5_synthesis.py` (test 6), `tests/contracts/test_phase7_e2e_smoke.py` (tests 1, 2). Pitfall 2 `validation_status=="invalid"` assertion removed from both files (0 matches in final grep).
- Full suite `pytest tests/ --ignore=tests/qa -q` reports **687 passed / 13 skipped / 3 pre-existing fc-list failures** — Plan 10-01 baseline preserved, no new failures. SYNTH-10 grep-anchor (`test_no_auto_approval_path`) green. `pipeline_synthesis.schema.json` byte-identical to pre-plan state (confirmed via `diff` against `git show HEAD:...`).

## Task Commits

Each task committed atomically with `--no-verify`:

1. **Task 1: Create pipeline_acceptance + pipeline_rejection schemas + register them** — `d65544d` (feat)
2. **Task 2: Refactor accept_synthesis + reject_synthesis to emit against the new schemas** — `331be2d` (refactor)
3. **Task 3: Update pinning tests (unit + contracts/e2e) + full-suite regression** — `87bb09c` (test)

## Files Created/Modified

- **Created** `schemas/artifacts/pipeline_acceptance.schema.json` — 34 lines; draft-2020-12, `$id: openmontage/artifacts/pipeline_acceptance`, required = [version, promoted_slug, promoted_path, validation_status, created_at]; optional = validation_issues; every property has an inline description referencing semantic intent (no ambiguity about what each field means at promotion time).
- **Created** `schemas/artifacts/pipeline_rejection.schema.json` — 33 lines; draft-2020-12, `$id: openmontage/artifacts/pipeline_rejection`, required = [version, rejected_slug, staging_path, created_at]; optional = reason; description explicitly references CLEAN-09 / Phase 5 REVIEW MR-02 and documents that it replaces the v2.0 Pitfall 2 hack.
- **Modified** `schemas/artifacts/__init__.py` — appended `"pipeline_acceptance"` and `"pipeline_rejection"` to `ARTIFACT_NAMES` (2 lines inserted). Registration is name-agnostic; `load_schema` + `validate_artifact` find the new files via `SCHEMA_DIR / f"{name}.schema.json"`.
- **Modified** `lib/pipeline_synthesizer.py` — added `from schemas.artifacts import validate_artifact` import; rewrote `accept_synthesis` record block to emit pipeline_acceptance (11 lines of new record body vs. the old 11 lines — net 0 line delta but semantically different); rewrote `reject_synthesis` record block to emit pipeline_rejection (6 lines of new record body). Both docstrings updated to document the new schema contract and cross-reference CLEAN-09 / v2.0 Phase 5 REVIEW MR-02. `_load_synthesis_schema` still called by `synthesize_pipeline` (1 legitimate call-site) — definition preserved.
- **Modified** `tests/unit/test_accept_reject.py` — Test 7 (`test_accept_record_schema_valid`) loads `pipeline_acceptance` instead of `pipeline_synthesis`, asserts `promoted_slug` present; Test 8 renamed from `test_reject_record_schema_valid_and_invalid_status` to `test_reject_record_schema_valid`, loads `pipeline_rejection`, asserts `rejected_slug == "foo-abcd1234"` and `validation_status not in record`. Module docstring index updated to reflect the rename.
- **Modified** `tests/contracts/test_phase7_e2e_smoke.py` — `test_e2e_mocked_synthesis_accept_roundtrip` loads `pipeline_acceptance` for the accept_record + adds `assert accept_record["promoted_slug"] == slug`; `test_e2e_mocked_synthesis_reject` loads `pipeline_rejection`, asserts `rejected_slug == slug` and `staging_path.startswith("pipeline_defs/_staging/")`, removes the `validation_status == "invalid"` assertion.
- **Modified** `tests/contracts/test_phase5_synthesis.py` — `test_end_to_end_synthesize_accept` loads `pipeline_acceptance` for the accept_record (Test 6 at line 288).

## Decisions Made

- **Schema split over sentinel allow-list (locked in CONTEXT.md D-CLEAN-09 before planning)** — the alternative (expand `pipeline_synthesis` with a `validation_status="rejected"` enum + nullable sentinels) would have kept one schema for three semantically distinct events (synthesis, promotion, rejection) and required every downstream audit consumer to branch on discriminator fields. Splitting gives three honest contracts, three clean consumer paths, zero discriminator logic at the audit layer.
- **`pipeline_synthesis.schema.json` left byte-identical** — the pre-approval synthesis event (`synthesize_pipeline`) still has exactly the fields the schema describes. Splitting that path too would have forced test_phase5_synthesis.py tests 1-5 to migrate for zero correctness gain. Verified via `diff schemas/artifacts/pipeline_synthesis.schema.json <(git show HEAD:schemas/artifacts/pipeline_synthesis.schema.json)` → empty.
- **`validate_artifact` over raw jsonschema.validate in the refactored handlers** — removes a dual-pathway inconsistency (before: `synthesize_pipeline` used `_load_synthesis_schema` + raw jsonschema; after: `accept_synthesis`/`reject_synthesis` route through the canonical `validate_artifact(name, data)` helper that ARTIFACT_NAMES uses). `synthesize_pipeline` still uses the raw path — migrating it was out of scope (plan-local boundary) and would have touched tests 1-5 of test_phase5_synthesis.py.
- **Optional `validation_issues` on pipeline_acceptance, populated only when status=invalid** — gives the meta-skill layer actionable structured data (a list of human-readable issue descriptions) without forcing it elsewhere on promoted-but-invalid manifests. Empty/absent when status=valid so the common case has minimal record size.
- **Optional `reason` on pipeline_rejection, NOT populated by this version** — pre-wires the schema for a future meta-skill phase that will forward a user-provided rejection reason. Adding the field later would have required a schema version bump; adding it now as optional costs nothing and unblocks that future work.

## Deviations from Plan

None. The plan executed exactly as written.

All tasks landed on the first attempt with zero Rule 1/2/3 auto-fixes. The plan's acceptance criteria were all directly verifiable via grep / python -c / pytest and all passed on the first run. The only CLAUDE.md-driven adjustment was using `--no-verify` on commits per the executor prompt's parallel-execution directive.

## Authentication Gates

None. This plan touches only local Python + JSON schema files and `pytest`. No external services, no credentials, no env vars.

## Issues Encountered

None.

## Threat Flags

No new security-relevant surface introduced. This plan **closes** the T-10-07 (Information Disclosure) and T-10-08 (Repudiation partial) threats from the plan's own `<threat_model>` block by making the accept/reject record fields semantically honest. The T-10-09 (Tampering — re-introduction of sentinels) mitigation is now grep-verifiable and confirmed: `grep -nE 'match_score=0\.0|base_pipeline=slug|"post-accept"|"post-reject"' lib/pipeline_synthesizer.py` returns 0 matches.

Post-accept / post-reject audit consumers that need the matcher's `match_score` or the analysis `source_analysis_checksum` now correlate by `promoted_slug` / `rejected_slug` with the earlier `pipeline_synthesis` record from the same synthesis run. That correlation is a documented pattern in the acceptance schema's top-level description ("Audit consumer needs match_score → correlate by promoted_slug with the earlier pipeline_synthesis record").

## User Setup Required

None — no external service configuration, no new environment variables, no dashboard steps.

## Next Phase Readiness

- CLEAN-09 closed. All 4 sentinel patterns verifiably gone. Both new schemas loadable via the existing helper. Test suite 687 passing (Plan 10-01 baseline preserved). SYNTH-10 grep-anchor and Phase 7 E2E smoke both green.
- Plan 10-03 (if any — none planned per ROADMAP) unblocked; Phase 11 (DRIFT-01 + NITS-01) unblocked. Phase 11 can absorb the NR-level NITS (including the `_relative_staging_path` misnaming acknowledged in the plan's action notes) without touching Phase 10 contracts.
- Phase 12 Human UAT remains gated on `GEMINI_API_KEY` / `OPENROUTER_API_KEY` + a user-supplied fixture video — no Phase 10 work blocks it. The new record schemas are backward-compatible for any downstream audit consumer that adapts to correlate-by-slug.
- v2.1 milestone progress after this plan: Phases 8 (done), 9 (done), 10 plan 01 (done), 10 plan 02 (done). Next action is Phase 11 plan creation.

## Self-Check

- [x] `schemas/artifacts/pipeline_acceptance.schema.json` exists — FOUND
- [x] `schemas/artifacts/pipeline_rejection.schema.json` exists — FOUND
- [x] `ARTIFACT_NAMES` includes both new names — FOUND (lines 31, 32 of schemas/artifacts/__init__.py)
- [x] `pipeline_synthesis.schema.json` byte-identical to HEAD — FOUND (`diff` output empty)
- [x] `grep -nE 'match_score=0\.0|base_pipeline=slug|"post-accept"|"post-reject"' lib/pipeline_synthesizer.py` → 0 matches — FOUND
- [x] `grep -n 'validate_artifact("pipeline_acceptance"' lib/pipeline_synthesizer.py` → 1 match (line 714) — FOUND
- [x] `grep -n 'validate_artifact("pipeline_rejection"' lib/pipeline_synthesizer.py` → 1 match (line 757) — FOUND
- [x] `_load_synthesis_schema` still present for `synthesize_pipeline` (1 def + 1 call, line 238 + 607) — FOUND
- [x] accept_synthesis return signature still `(slug: 'str') -> 'tuple[Path, dict[str, Any]]'` — FOUND via inspect.signature
- [x] `pytest tests/unit/test_accept_reject.py tests/contracts/test_phase5_synthesis.py tests/contracts/test_phase7_e2e_smoke.py -q` → 46 passed — FOUND
- [x] `pytest tests/contracts/test_phase5_synthesis.py::test_no_auto_approval_path -q` → 1 passed (SYNTH-10 green) — FOUND
- [x] `pytest tests/ --ignore=tests/qa -q` → 687 passed, 13 skipped, 3 pre-existing fc-list failures (Plan 10-01 baseline preserved, no new failures) — FOUND
- [x] Commit `d65544d` on current branch — FOUND
- [x] Commit `331be2d` on current branch — FOUND
- [x] Commit `87bb09c` on current branch — FOUND

## Self-Check: PASSED

---
*Phase: 10-synthesizer-record-validity*
*Completed: 2026-04-18*
