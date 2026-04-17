---
phase: 01-schema-adapter
plan: 02
subsystem: schemas
tags: [schema, jsonschema, pipeline_synthesis, contract-tests, SYNTH-09]
dependency_graph:
  requires:
    - "schemas/artifacts/__init__.py:load_schema (existing helper)"
    - "jsonschema>=4.20 (already in requirements.txt)"
    - "pytest (already in devcontainer)"
  provides:
    - "schemas/artifacts/pipeline_synthesis.schema.json (SYNTH-09 contract)"
    - "Canonical record shape for Phase 5 synthesizer output"
    - "Enum vocabularies for mode, provider_used, validation_status"
  affects:
    - "Phase 5 (synthesizer) — must emit records matching this schema"
    - "Phase 1 Plan 03 (ARTIFACT_NAMES registration) — will add 'pipeline_synthesis'"
    - "Phase 1 Plan 04 (checkpoint registration) — will map stage to this artifact"
tech_stack:
  added: []
  patterns:
    - "JSON Schema Draft 2020-12 (matches v1.0 artifacts + pipeline_manifest)"
    - "Inline authoring style (no $ref) — mirrors video_analysis.schema.json"
    - "Pytest class with parametrize for field-level rejection tests"
key_files:
  created:
    - "schemas/artifacts/pipeline_synthesis.schema.json"
    - "tests/contracts/test_pipeline_synthesis_schema.py"
  modified: []
decisions:
  - "version const = '1.0' (first canonical shape of synthesis record; milestone is v2.0 but this artifact has no prior form)"
  - "validation_status enum = [valid, invalid, pending] (reasonable starting shape per RESEARCH A2; Phase 5 may amend)"
  - "diff_against_base kept as free-form string (unified-diff or human-readable) — Phase 5 chooses representation"
  - "created_at field included as optional for traceability; not required"
metrics:
  duration: "~8 minutes"
  tasks: 2
  files_created: 2
  files_modified: 0
  tests_added: 17
  commits: 2
  completed_date: "2026-04-17"
---

# Phase 01 Plan 02: Pipeline Synthesis Schema Summary

**One-liner:** Canonical JSON Schema Draft 2020-12 for pipeline synthesis run records — the 8 SYNTH-09 fields (`base_pipeline`, `match_score`, `mode`, `staging_path`, `diff_against_base`, `validation_status`, `source_analysis_checksum`, `provider_used`) plus a `version: "1.0"` const — plus 17 contract tests that verify loadability, fixture validation, enum restrictions, and numeric bounds, all without requiring any API key.

## What Was Built

### schemas/artifacts/pipeline_synthesis.schema.json (new)

Draft 2020-12 JSON Schema with `$id: openmontage/artifacts/pipeline_synthesis`, authored inline (no `$ref`) in the same style as `video_analysis.schema.json` (Plan 01-01).

**Required fields (9):**
- `version` — const `"1.0"`
- `base_pipeline` — string (slug of matched base pipeline)
- `match_score` — number, bounded `[0, 1]`
- `mode` — enum `["template", "replica"]` (SYNTH-04)
- `staging_path` — string (path under `pipeline_defs/_staging/<slug>.yaml`, SYNTH-05)
- `diff_against_base` — string (free-form diff text)
- `validation_status` — enum `["valid", "invalid", "pending"]`
- `source_analysis_checksum` — string (content hash for idempotency, SYNTH-06)
- `provider_used` — enum `["gemini", "openrouter"]`

**Optional:** `created_at` (ISO-8601 timestamp).

### tests/contracts/test_pipeline_synthesis_schema.py (new)

17 tests grouped in `TestPipelineSynthesisSchema`:

| Test | Purpose |
|------|---------|
| `test_schema_loads` | File exists, `$schema` is Draft 2020-12, title correct, required set contains SYNTH-09 + version |
| `test_load_schema_helper_works` | `schemas.artifacts.load_schema("pipeline_synthesis")` returns the parsed schema |
| `test_fixture_validates` | Minimal fully-populated fixture passes `jsonschema.validate` |
| `test_rejects_missing_required[field]` × 8 | Parametrized: removing any SYNTH-09 required field raises `ValidationError` |
| `test_rejects_match_score_above_one` | `match_score = 1.5` rejected |
| `test_rejects_match_score_below_zero` | `match_score = -0.1` rejected |
| `test_rejects_invalid_mode` | `mode = "freeform"` rejected |
| `test_rejects_invalid_provider` | `provider_used = "claude"` rejected |
| `test_rejects_invalid_validation_status` | `validation_status = "unknown"` rejected |
| `test_rejects_invalid_version_const` | `version = "2.0"` rejected (const mismatch) |

All 17 tests pass in ~0.14 s. Zero network, zero API keys, zero external processes.

## Requirements Satisfied

| Req | Description | Status |
|-----|-------------|--------|
| SYNTH-09 | `schemas/artifacts/pipeline_synthesis.schema.json` captures synthesis run record with the 8 listed fields | Complete |

## Enum Vocabularies Locked

- **mode**: `template` (default per SYNTH-04, generalizable adaptation), `replica` (closer reproduction of exact reference)
- **provider_used**: `gemini` (direct SDK), `openrouter` (via OpenAI SDK)
- **validation_status**: `valid`, `invalid`, `pending` (Phase 5 may extend if new states needed)

## Verification

```
$ python3 -c "import json; s=json.load(open('schemas/artifacts/pipeline_synthesis.schema.json')); \
  assert set(s['required'])=={'version','base_pipeline','match_score','mode','staging_path', \
  'diff_against_base','validation_status','source_analysis_checksum','provider_used'}; \
  assert s['properties']['match_score']['minimum']==0 and s['properties']['match_score']['maximum']==1; \
  assert s['properties']['mode']['enum']==['template','replica']; \
  assert s['properties']['provider_used']['enum']==['gemini','openrouter']; print('OK')"
OK

$ pytest tests/contracts/test_pipeline_synthesis_schema.py -x -q
.................                                                        [100%]
17 passed in 0.14s
```

## Deviations from Plan

None — plan executed exactly as written. The Task 1 and Task 2 action blocks contained the complete intended content; both tasks were executed verbatim.

**Note on Phase 0 regression:** `pytest tests/contracts/test_phase0_contracts.py` reports one pre-existing failure (`TestToolRegistry::test_support_envelope` — `ModuleNotFoundError: No module named 'numpy'`). Verified pre-existing via `git stash` + rerun. Already logged in `deferred-items.md` by Plan 01-01. Out of scope for Plan 01-02 (scope boundary rule). Remaining 34 Phase 0 tests pass.

## Commits

| Task | Hash | Message |
|------|------|---------|
| 1 | `ef25c51` | `feat(01-02): add pipeline_synthesis canonical schema (SYNTH-09)` |
| 2 | `bb3ca35` | `test(01-02): contract tests for pipeline_synthesis schema` |

## Follow-ups for Later Plans

- **Plan 01-03** must add `"pipeline_synthesis"` to `ARTIFACT_NAMES` in `schemas/artifacts/__init__.py` so `validate_artifact("pipeline_synthesis", data)` can be gated consistently.
- **Plan 01-04** must add `"pipeline_synthesis": "pipeline_synthesis"` to `lib/checkpoint.py:CANONICAL_STAGE_ARTIFACTS` so checkpoint validation can reach this schema.
- **Phase 5** synthesizer must emit records conforming to this schema; `validation_status` enum may be revisited then if new states are needed.

## Self-Check: PASSED

- `schemas/artifacts/pipeline_synthesis.schema.json` — FOUND on disk
- `tests/contracts/test_pipeline_synthesis_schema.py` — FOUND on disk
- Commit `ef25c51` — FOUND in `git log`
- Commit `bb3ca35` — FOUND in `git log`
- 17/17 tests green
- No API keys / network / external services used
