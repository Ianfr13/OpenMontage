# Phase 10: Synthesizer Record Validity - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning
**Mode:** Auto-generated (cleanup phase — specs are literal v2.0 Phase 5 review findings)

<domain>
## Phase Boundary

Harden `lib/pipeline_synthesizer.py` so `accept_synthesis` / `reject_synthesis`:
- Validate slug input (regex + resolved-path check under staging root) against path traversal.
- Stop emitting bogus synthesis run records with sentinel values (`base_pipeline=slug`, `match_score=0.0`, `source_analysis_checksum="post-accept"`) that pass schema validation but violate semantics.

Out of boundary: providers/merger (Phase 8+9, done), drift/NITs (Phase 11), UAT (Phase 12).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion (per REQUIREMENTS.md + 05-REVIEW.md)

- **CLEAN-08 (slug validation)**: regex `^[a-z0-9]{8,}$` (hex slug format used upstream) or equivalent. After regex pass, resolve the target path and assert it is under the declared staging root (`pipeline_defs/_staging/`). Raise a new `InvalidPipelineSlug` sentinel (subclass of the existing error family in `lib/analysis_errors.py`) on failure. Apply to BOTH `accept_synthesis(slug)` and `reject_synthesis(slug)`.
- **CLEAN-09 (stop bogus records)**: Choose **schema split** over sentinel allow-list — create two new schemas `schemas/artifacts/pipeline_acceptance.schema.json` and `schemas/artifacts/pipeline_rejection.schema.json` with only the fields the post-accept/reject action actually has. Update the synthesizer's accept/reject paths to emit against the new schemas. Delete the sentinel writes (`base_pipeline=slug`, `match_score=0.0`, `source_analysis_checksum="post-accept"`). Leave `pipeline_synthesis_run` schema as-is — it stays the contract for the pre-approval synthesis step.

### Backward compat

Non-negotiable: `pytest tests/ --ignore=tests/qa -q` must stay at ≥662 passing. Existing tests that assert the sentinel values must be updated to assert the new schema fields. Integration tests (e.g., E2E synthesis + reject cleanup in Phase 7 test suite) must still pass — the schema split is additive (new schemas) plus a migration for the post-action records.

### Where new schemas live

`schemas/artifacts/pipeline_acceptance.schema.json` and `schemas/artifacts/pipeline_rejection.schema.json`. Both validated with the existing `validate_artifact` helper (same pattern as `video_analysis`).

</decisions>

<code_context>
## Existing Code Insights

### Relevant files
- `lib/pipeline_synthesizer.py` (lines 606, 670 for slug entry; 636-648, 677-690 for bogus records)
- `lib/analysis_errors.py` (add `InvalidPipelineSlug` sentinel alongside Phase 8's auth/rate + Phase 9's `MergeConsensusError`)
- `schemas/artifacts/pipeline_synthesis_run.schema.json` (existing — DO NOT change; governs pre-approval synthesis record)
- `schemas/artifacts/pipeline_acceptance.schema.json` (NEW)
- `schemas/artifacts/pipeline_rejection.schema.json` (NEW)
- `lib/schema_utils.py` or equivalent `validate_artifact` helper (reuse, do not rewrite)
- `tests/unit/test_pipeline_synthesizer.py` + `tests/contracts/test_phase5_*.py` + `tests/integration/test_phase7_e2e_smoke.py` (existing baselines)

### Anchor review
- v2.0 Phase 5 REVIEW: `.planning/milestones/v2.0-phases/05-synthesizer/05-REVIEW.md` — MR-01 (slug validation), MR-02 (bogus records)

### Known-good facts from STATE.md
- `accept_synthesis` returns `(Path, record)` tuple; `reject_synthesis` currently encodes user rejection as `validation_status=invalid` (Pitfall 2). This behavior changes under CLEAN-09 — explicit rejection schema removes the `validation_status=invalid` hack.
- Order-aware SYNTH-10 regex (`synthes\w*accept` forbidden; `accept_synthesis` permitted) exists in grep-anchor test — must still pass after refactor.

</code_context>

<specifics>
## Specific Ideas

- User memory (feedback_validate_api_patterns): before introducing new schemas, read the existing `pipeline_synthesis_run.schema.json` fields and naming conventions, and mirror them — do NOT invent a new field shape.
- STATE.md decision log item `05-03: accept_synthesis returns (Path, record) tuple` — preserve the tuple return shape; only the record's schema conformance changes.

</specifics>

<deferred>
## Deferred Ideas

- Interactive diff UI for staging approval (SYNTH2-02) — Future Requirements, not Phase 10.
- Cross-chunk cost correlation in synthesis records (OBS-01) — deferred.
- LOW/NIT items from 05-REVIEW.md — absorb into Phase 11 (NITS-01).

</deferred>
