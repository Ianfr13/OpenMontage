---
phase: 05-synthesizer
verified: 2026-04-17T21:54:54Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 5: Synthesizer + Staging Verification Report

**Phase Goal:** A validated `video_analysis` artifact can be turned into a rule-matched, semantically-validated pipeline YAML that lands in `_staging/` and waits for human approval before touching `pipeline_defs/`.
**Verified:** 2026-04-17T21:54:54Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                                                                                                                                      | Status     | Evidence |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------- |
| 1   | `lib/pipeline_synthesizer.py` writes ONLY to `pipeline_defs/_staging/<slug>.yaml`; `lib/pipeline_loader.py::list_pipelines()` never returns paths under `_staging/`                                         | ✓ VERIFIED | `_write_staging` constrains target to `STAGING_DIR = PIPELINE_DEFS_DIR / "_staging"` (synthesizer.py:61, 417-448); `list_pipelines()` uses non-recursive `glob("*.yaml")` + defense-in-depth underscore filter (loader.py:53-67); runtime check confirmed 12 pipelines returned, zero `_staging` in output. Contract test `test_staging_path_under_pipeline_defs` + `test_staging_only_write` passing. |
| 2   | Rule-based matching selects base from 12 pipelines using pacing_style + talking_head_heavy (mapped from `shot_type_distribution.talking_head`) + motion signals; `match_score` surfaced in synthesis record | ✓ VERIFIED | `match_base_pipeline` (synthesizer.py:271-353) implements the 5-signal rule table bounded [0, 1], iterates `list_pipelines()` (12 names), maps `close_up_heavy → talking_head > 0.5` and `static_heavy → static_image > 0.5` (lines 305-306). `match_score` is in the returned record (line 545). Behavioral run returned `base_pipeline=cinematic, match_score=0.55`. Tests: `test_matcher_exact_pacing`, `test_matcher_close_up_heavy`, `test_matcher_static_heavy`, `test_deterministic_ties` all passing. |
| 3   | Every `skill:` path in synthesized YAML exists; every tool in `tools_available` is registered; semantic validation rejects before approval if either check fails                                            | ✓ VERIFIED | `validate_synthesized_pipeline` (synthesizer.py:118-169) checks `SKILLS_DIR / f"{skill}.md"` existence and membership of each tool in `registry.list_all()` after `registry.ensure_discovered()`. Record's `validation_status` is set to `"invalid"` when issues exist (line 537). `SynthesisValidationError` raised via `raise_if_invalid`. Tests: `test_validate_missing_skill`, `test_validate_unknown_tool`, `test_synthesis_validation_error_raises`, `test_validation_status_invalid` all passing. |
| 4   | Slug includes short content hash; idempotent on same video; no silent overwrite                                                                                                                            | ✓ VERIFIED | `_build_slug` returns `f"{base_pipeline}-{checksum[:8]}"` (line 254) using SHA-256 of canonical JSON (`_canonical_sha256`, line 237-249). Collision handling: byte-equal re-runs reuse existing path (line 429-431); differing content iterates `-v2..-v99` (lines 433-446) with DoS cap. Tests: `test_slug_idempotent`, `test_collision_bytes_equal_noop`, `test_collision_bytes_differ_v2` all passing. |
| 5   | Accept/reject via explicit calls (`accept_synthesis` / `reject_synthesis`); no auto-approval path exists — contract test enforces this guard                                                                | ✓ VERIFIED | `accept_synthesis(slug) -> (Path, record)` (synthesizer.py:579-649) and `reject_synthesis(slug) -> record` (lines 652-690) are separate, named functions. Grep for forbidden `synthes\w*accept` pattern returns 0 matches. Contract test `test_no_auto_approval_path` at `tests/contracts/test_phase5_synthesis.py` structurally guards this via order-aware regex that forbids `synthes\w*accept` but permits `accept_synthesis`. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact                                                       | Expected                                                                                                  | Status     | Details |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ---------- | ------- |
| `lib/pipeline_synthesizer.py`                                  | Module-level `match_base_pipeline`, `synthesize_pipeline`, `accept_synthesis`, `reject_synthesis`, `validate_synthesized_pipeline`, `SynthesisValidationError`, `raise_if_invalid` | ✓ VERIFIED | 692 lines; all exports importable; 3 required defs (synthesize_pipeline/accept_synthesis/reject_synthesis) present; 17 `_staging` references; 3 `SynthesisValidationError` references; 7 `validation_status` references; ruamel.yaml imported. Wired: imported by `tests/unit/test_pipeline_synthesizer.py`, `test_semantic_validation.py`, `test_accept_reject.py`, `tests/contracts/test_phase5_synthesis.py`, `lib/llm_fill.py`. |
| `lib/llm_fill.py`                                              | `fill_stage_details()` with 6-step fallback ladder; MODEL_DEFAULT, MAX_TOKENS=2000, FILLABLE_FIELDS       | ✓ VERIFIED | 322 lines; `fill_stage_details` exported; fallback ladder implemented (env opt-out, missing key, SDK exception, 2-attempt JSON retry, post-merge validation). Wired: imported conditionally by `synthesize_pipeline` (line 510) when `use_llm_fill=True`. Used by `tests/unit/test_llm_fill.py`. |
| `lib/pipeline_loader.py`                                       | `list_pipelines()` with explicit `startswith("_")` filter                                                 | ✓ VERIFIED | Line 53-67 contains the underscore-prefix filter. 1 `startswith` match. Non-recursive `glob("*.yaml")` + defense-in-depth filter. Test `test_loader_excludes_staging` + `test_loader_underscore_filter_on_recursive` passing. |
| `schemas/pipelines/pipeline_manifest.schema.json`              | Optional `expected_analysis` top-level block                                                              | ✓ VERIFIED | `expected_analysis` in schema root `properties`; verified via `json.load(...).properties`. |
| `requirements.txt`                                             | `ruamel.yaml>=0.18,<0.20` pinned                                                                          | ✓ VERIFIED | 1 match: `ruamel.yaml>=0.18,<0.20`. Installed version: `ruamel.yaml 0.19.1` (within pin range). |
| `pipeline_defs/*.yaml` (12 files)                              | All carry `expected_analysis` block + still load                                                          | ✓ VERIFIED | `grep -l "expected_analysis:" pipeline_defs/*.yaml \| wc -l` = 12. Runtime check: all 12 load via `load_pipeline()`. Values differentiate (`slow_contemplative`, `steady_educational`, `rapid_fire`, `dynamic_social`, `variable`) with per-pipeline stage counts. |
| `tests/unit/test_pipeline_synthesizer.py`                      | Matcher + slug + writer + record tests                                                                    | ✓ VERIFIED | 574 lines; 19 tests all pass. |
| `tests/unit/test_semantic_validation.py`                       | Missing skill + unknown tool + staging exclusion coverage                                                 | ✓ VERIFIED | 293 lines; 9 tests all pass. |
| `tests/unit/test_llm_fill.py`                                  | Mocked LLM happy path + failure modes + mode differentiation                                              | ✓ VERIFIED | 422 lines; 10 tests all pass. |
| `tests/unit/test_accept_reject.py`                             | Accept moves file + reject unlinks + record schema + idempotency                                          | ✓ VERIFIED | 335 lines; 11 tests all pass. |
| `tests/contracts/test_phase5_synthesis.py`                     | End-to-end synthesize → validate → accept + no-auto-approval guard                                        | ✓ VERIFIED | 289 lines; 6 tests all pass including `test_no_auto_approval_path` + `test_end_to_end_synthesize_accept`. |
| `.gitignore`                                                   | `pipeline_defs/_staging/` entry                                                                           | ✓ VERIFIED | `grep "_staging" .gitignore` → `pipeline_defs/_staging/`. |

### Key Link Verification

| From                                   | To                                                                      | Via                                                                 | Status    | Details |
| -------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------- | --------- | ------- |
| `lib/pipeline_synthesizer.py`          | `lib/pipeline_loader.list_pipelines()`                                  | `from lib.pipeline_loader import PIPELINE_DEFS_DIR, list_pipelines, load_pipeline` (line 54) | ✓ WIRED   | Imported and called in `match_base_pipeline` (line 309) and `accept_synthesis` via `load_pipeline` (line 627). |
| `lib/pipeline_synthesizer.py`          | `ruamel.yaml.YAML`                                                      | `from ruamel.yaml import YAML` (line 52)                            | ✓ WIRED   | Used in `_unified_diff` (line 207) and `_dump_manifest_body` (line 382). |
| `lib/pipeline_synthesizer.py`          | `tools/tool_registry.registry.list_all`                                 | local import in `validate_synthesized_pipeline` (line 142)          | ✓ WIRED   | Calls `registry.ensure_discovered()` then `registry.list_all()` (lines 147-148). |
| `lib/pipeline_synthesizer.py`          | `schemas/artifacts/pipeline_synthesis.schema.json`                      | `_SYNTHESIS_SCHEMA_PATH` + `jsonschema.validate` (line 557, 648, 689) | ✓ WIRED | Record emitted from `synthesize_pipeline`, `accept_synthesis`, `reject_synthesis` all jsonschema-validated before return. |
| `lib/pipeline_synthesizer.py`          | `lib/llm_fill.py`                                                       | `from lib import llm_fill` (line 510)                               | ✓ WIRED   | Conditional import inside `synthesize_pipeline`; called when `use_llm_fill=True`. |
| `lib/llm_fill.py`                      | OpenAI client at `https://openrouter.ai/api/v1`                         | `client = OpenAI(base_url="https://openrouter.ai/api/v1", ...)` (line 274-277) | ✓ WIRED | Client construction + `client.chat.completions.create` (line 177). |
| `lib/pipeline_synthesizer.py`          | `shutil.move` for staging → pipeline_defs/ promotion                    | `shutil.move(str(src), str(dst))` (line 620)                        | ✓ WIRED   | `accept_synthesis` uses `shutil.move` — the single authorized path into `pipeline_defs/`. |
| `lib/pipeline_loader.py::list_pipelines` | `pipeline_defs/_staging/` exclusion                                   | `if not p.parent.name.startswith("_")` (line 66)                    | ✓ WIRED   | Defense-in-depth filter; runtime test confirmed no `_staging` leaks. |
| `pipeline_defs/*.yaml`                 | `schemas/pipelines/pipeline_manifest.schema.json`                       | `jsonschema.validate` inside `load_pipeline`                        | ✓ WIRED   | All 12 pipelines load with extended schema (expected_analysis accepted). |

### Data-Flow Trace (Level 4)

| Artifact                              | Data Variable          | Source                                           | Produces Real Data | Status     |
| ------------------------------------- | ---------------------- | ------------------------------------------------ | ------------------ | ---------- |
| `synthesize_pipeline` record          | `record` dict          | Computed from `match_base_pipeline(analysis)` + `load_pipeline(base)` + `validate_synthesized_pipeline(synthesized)` + `_unified_diff(...)` — all 9 schema-required fields populated from real computation | ✓ FLOWING | Behavioral run: record had `base_pipeline=cinematic, match_score=0.55, validation_status=invalid, staging_path=pipeline_defs/_staging/cinematic-484ea357.yaml`, all sourced from live matcher + validator, not static returns. |
| `match_base_pipeline` result          | `scores` list          | Iterates `list_pipelines()` (12 real files) and loads each via `load_pipeline()` to read `expected_analysis` | ✓ FLOWING | 12 real scored entries; alternatives list non-empty. |
| `validate_synthesized_pipeline` issues | `issues` list          | Real `os.path.exists` checks against `skills/` + real `registry.list_all()` set membership | ✓ FLOWING | Validator correctly flagged `web_search` in cinematic.yaml as unknown tool (pre-existing desync, deferred). |
| `accept_synthesis` record             | `record` dict          | Post-move re-validation (`load_pipeline(slug)` + `validate_synthesized_pipeline`); 9 schema-required fields | ✓ FLOWING | Test `test_accept_record_schema_valid` exercises round-trip. |
| `reject_synthesis` record             | `record` dict          | `validation_status="invalid"` per Pitfall 2 resolution; other fields computed from slug + timestamp | ✓ FLOWING | Test `test_reject_record_schema_valid_and_invalid_status` validates against schema. |
| `_staging/<slug>.yaml`                | file bytes             | `ruamel.yaml` round-trip dump of `synthesized` (= base_manifest or LLM-filled) + provenance header | ✓ FLOWING | End-to-end contract test `test_staging_file_loads_as_yaml` re-loads the staged file successfully. |

### Behavioral Spot-Checks

| Behavior                                                            | Command                                                                                                                                                            | Result                                                                                                       | Status  |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ | ------- |
| Phase 5 test suite (prompt-specified)                               | `unset OPENROUTER_API_KEY && pytest tests/unit/test_pipeline_synthesizer.py tests/unit/test_semantic_validation.py tests/unit/test_llm_fill.py tests/unit/test_accept_reject.py tests/contracts/test_phase5_synthesis.py -q` | `55 passed in 11.79s`                                                                                        | ✓ PASS  |
| Phase 1 schema regression                                           | `pytest tests/contracts/test_pipeline_synthesis_schema.py -q`                                                                                                      | `17 passed in 0.10s`                                                                                         | ✓ PASS  |
| Full Phase 5 API surface importable                                 | `python3 -c "from lib.pipeline_synthesizer import ...; from lib.llm_fill import fill_stage_details"`                                                               | `All public exports importable`                                                                              | ✓ PASS  |
| 12 pipelines listed, no `_staging` leaks                            | `python3 -c "from lib.pipeline_loader import list_pipelines; ..."`                                                                                                 | 12 pipelines, no staging in output                                                                           | ✓ PASS  |
| Live synthesize_pipeline end-to-end (no LLM; deterministic matcher) | `synthesize_pipeline(sample_analysis, mode='template')` with `VIDEO_SYNTH_LLM_FILL=false`                                                                          | `base_pipeline=cinematic, match_score=0.55, validation_status=invalid, staging_path=pipeline_defs/_staging/cinematic-484ea357.yaml` — all from live code | ✓ PASS  |
| Grep: zero forbidden `synthes\w*accept` functions                   | `grep -cE "^def\s+synthes\w*accept\|^def\s+synth\w*accept" lib/pipeline_synthesizer.py`                                                                            | `0`                                                                                                          | ✓ PASS  |
| Grep: exactly 3 required def statements                             | `grep -c "def synthesize_pipeline\|def accept_synthesis\|def reject_synthesis" lib/pipeline_synthesizer.py`                                                        | `3`                                                                                                          | ✓ PASS  |

**Total Phase 5 test count: 72 (55 Phase 5 + 17 Phase 1 schema regression), 100% pass rate.**

### Requirements Coverage

| Requirement | Source Plan  | Description                                                                                                                                              | Status       | Evidence                                                                                                                                                |
| ----------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SYNTH-01    | 05-01        | `lib/pipeline_synthesizer.py` is a pure lib module with module-level functions (no class defs beyond `SynthesisValidationError(Exception)`)                | ✓ SATISFIED  | Only locally-defined class is the Exception subclass; `test_module_shape` enforces this.                                                                 |
| SYNTH-02    | 05-01        | Rule-based matcher with 5-signal table, bounded [0, 1], deterministic tie-break                                                                            | ✓ SATISFIED  | `match_base_pipeline` implements exact spec; 4 matcher tests pass; behavioral run selected correct base.                                                |
| SYNTH-03    | 05-03        | LLM fill-in is advisory — never invents stage structure, falls back to base on any failure                                                                 | ✓ SATISFIED  | `lib/llm_fill.py` + `_merge_stage_details` drops extras; `test_llm_never_invents_stages` + `test_post_fill_validation_reverts_on_failure` pass.           |
| SYNTH-04    | 05-01 + 05-03 | `mode="template"` / `mode="replica"` accepted and routed; invalid mode raises `ValueError`                                                                | ✓ SATISFIED  | `test_mode_parameter_accepted` + `test_modes_differ` pass; mode strings branch prompt in `_build_prompt`.                                               |
| SYNTH-05    | 05-01        | Writes ONLY to `pipeline_defs/_staging/<slug>.yaml`; ruamel.yaml round-trip; provenance header                                                             | ✓ SATISFIED  | `_write_staging` constrains target to `STAGING_DIR`; `test_staging_only_write` + `test_provenance_header` pass.                                         |
| SYNTH-06    | 05-01        | Slug `{base}-{hash[:8]}` from SHA-256 of canonical JSON; idempotent; collision = `-vN` suffix                                                              | ✓ SATISFIED  | `_canonical_sha256` + `_build_slug` + collision loop at `_MAX_COLLISION_SUFFIX=99`; 3 related tests pass.                                                |
| SYNTH-07    | 05-02        | `list_pipelines()` explicitly excludes `_staging/` and any underscore-prefixed subdir                                                                      | ✓ SATISFIED  | `startswith("_")` filter at loader.py:66; `test_loader_excludes_staging` + `test_loader_underscore_filter_on_recursive` pass.                            |
| SYNTH-08    | 05-02        | Semantic validation catches missing skill + unknown tool; record carries `validation_status`                                                               | ✓ SATISFIED  | `validate_synthesized_pipeline` + `SynthesisValidationError` + `raise_if_invalid`; 9 tests in `test_semantic_validation.py` pass.                        |
| SYNTH-10    | 05-03        | Accept/reject via explicit calls; no auto-approval path                                                                                                    | ✓ SATISFIED  | `accept_synthesis` / `reject_synthesis` separate functions; `test_no_auto_approval_path` contract guard + zero `synthes\w*accept` matches in grep.      |

Note: SYNTH-09 (schema file creation) was shipped in Phase 1 and is not listed in this phase's requirements. It is honored by Phase 5 — emitted records are `jsonschema.validate`-d against the schema.

### Anti-Patterns Found

No blockers. Minor stub-like values in `accept_synthesis` / `reject_synthesis` records are intentional:

| File                              | Line    | Pattern                                              | Severity   | Impact |
| --------------------------------- | ------- | ---------------------------------------------------- | ---------- | ------ |
| `lib/pipeline_synthesizer.py`     | 639-642 | `match_score: 0.0`, `diff_against_base: ""`, `source_analysis_checksum: "post-accept"` in accept/reject records | ℹ️ Info     | Accept/reject API is flow-agnostic (caller supplies semantic context); documented in 05-03-SUMMARY.md key-decisions. Schema enum is honored. Not a stub — these are meaningful sentinel values per the plan. |
| `pipeline_defs/cinematic.yaml`    | research stage | `web_search` tool not in registry → triggers `validation_status=invalid` when cinematic is chosen | ℹ️ Info | Pre-existing manifest/registry desync documented in `deferred-items.md`; explicitly out of scope for Phase 5. The synthesizer correctly flags and surfaces this — validator is working as designed. |

### Human Verification Required

None. All goal-critical behaviors are programmatically verified by the 72-test Phase 5 suite (55 in-scope + 17 regression), behavioral end-to-end synthesis run, and structural grep guards. Prompt explicitly states "No human-needed gates expected."

A Phase 7 integration test (TEST-02) will exercise the LLM fill path against a live `OPENROUTER_API_KEY` — not a Phase 5 blocker.

### Gaps Summary

None. Phase 5 goal fully achieved:

- A validated `video_analysis` artifact → matcher selects one of 12 base pipelines by rule (`match_score ∈ [0, 1]`) with deterministic tie-break.
- Synthesized YAML lands ONLY under `pipeline_defs/_staging/<slug>.yaml` with content-hash idempotency, collision guards, and provenance header.
- Semantic validation (skill paths + tool registry) runs before any record emission; record carries `validation_status ∈ {valid, invalid}` (pending reserved).
- Record validates against `schemas/artifacts/pipeline_synthesis.schema.json` every time — synthesize, accept, reject.
- Accept/reject are explicit separate named functions; no auto-approval exists (structurally guarded).
- Advisory LLM fill wired with 6-step fallback ladder — never raises, never invents stages, reverts on post-merge validation failure.
- 72 tests pass (including Phase 1 schema regression); all 12 base pipelines still load under the extended schema.

---

_Verified: 2026-04-17T21:54:54Z_
_Verifier: Claude (gsd-verifier)_
