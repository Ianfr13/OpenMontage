---
phase: 01-schema-adapter
plan: 03
subsystem: lib/adapter
tags: [schema-adapter, jsonschema, gemini, openai, structured-output, ANLZ-03, INT-04]
dependency_graph:
  requires:
    - "schemas/artifacts/video_analysis.schema.json (Plan 01-01 — round-trip test source)"
    - "Python stdlib (copy.deepcopy, typing.Any) — no new dependencies"
  provides:
    - "lib.schema_adapter.to_api_schema(canonical: dict) -> dict — pure canonical->API JSON Schema converter"
    - "lib.schema_adapter.SchemaAdapterError(ValueError) — raised on unresolvable/external $ref"
    - "Idempotent, non-mutating, stdlib-only schema flattener"
  affects:
    - "Phase 2 (gemini_video_analyzer) — will call to_api_schema() before every response_json_schema request"
    - "Phase 3 (openrouter_video_analyzer) — will call to_api_schema() before every json_schema request"
    - "Any future provider emitting structured output against canonical schemas"
tech_stack:
  added: []
  patterns:
    - "Pure function with deepcopy-at-entry (no mutation contract)"
    - "Hand-rolled ~30-line recursive walker (no jsonref / no RefResolver) per RESEARCH Finding 6"
    - "Conservative $ref-with-siblings handling: drop $ref, keep siblings (Draft 2020-12 compat)"
    - "Error-class convention: SchemaAdapterError(ValueError) matching lib/checkpoint.py:CheckpointValidationError"
    - "Pytest class + inline dict fixtures (no tests/fixtures/ dir) — matches Phase 0/01-01/01-02 test style"
key_files:
  created:
    - "lib/schema_adapter.py"
    - "tests/unit/test_schema_adapter.py"
  modified:
    - ".planning/phases/01-schema-adapter/deferred-items.md (logged pre-existing devcontainer disk-full env issue)"
decisions:
  - "Strip list: {$schema, $id, uniqueItems} unconditional; additionalProperties only when literally False; $ref always dropped (pure-ref nodes inlined, mixed-sibling nodes keep siblings); definitions and $defs pools dropped after inlining"
  - "Preserve list: type, properties, required, items, enum, const, description, format, minimum, maximum, pattern, additionalProperties-as-schema-dict, and every other keyword"
  - "Hand-rolled $ref inliner (not jsonref / not jsonschema.RefResolver) — jsonref returns lazy proxies incompatible with the 'return a new plain dict' contract; RefResolver is deprecated in jsonschema>=4.18. Hand-roll is ~30 lines."
  - "SchemaAdapterError(ValueError) subclass — raise on unresolvable or external (non-#/) refs (programmer/config error, not data error). Pure function on valid input."
  - "Test file lives in tests/unit/ (new directory) — Plan VALIDATION decreed this split between tests/contracts/ (schema loadability) and tests/unit/ (pure-function behavior)."
metrics:
  duration: "~4 minutes"
  tasks: 2
  files_created: 2
  files_modified: 1
  tests_added: 16
  commits: 2
  completed_date: "2026-04-17"
---

# Phase 01 Plan 03: Schema Adapter Summary

**One-liner:** Pure-function canonical->API JSON Schema converter (`lib/schema_adapter.py`, 94 lines, stdlib-only) with 16-test unit suite verifying deepcopy-non-mutation, idempotency, unconditional strips ($schema/$id/uniqueItems), conditional additionalProperties-False strip, $ref inlining against root (#/definitions and #/$defs), SchemaAdapterError on unresolvable/external refs, and round-trip on Plan 01-01's real `video_analysis.schema.json` asserting zero `$ref`/`uniqueItems`/`$schema`/`$id` in serialized output.

## What Was Built

### `lib/schema_adapter.py` — Public API

```python
from lib.schema_adapter import to_api_schema, SchemaAdapterError

flat_schema = to_api_schema(canonical_draft_2020_12_schema)
# Raises SchemaAdapterError on unresolvable or external $ref.
```

**Two exports only** (enforced via `__all__`):

| Export                | Type                 | Purpose                                                          |
| --------------------- | -------------------- | ---------------------------------------------------------------- |
| `to_api_schema`       | `(dict) -> dict`     | Pure function — deepcopy in, new dict out; never mutates input   |
| `SchemaAdapterError`  | `class(ValueError)`  | Raised when `$ref` cannot be resolved against root               |

### Strip vs Preserve Sets

**Stripped unconditionally (at every nesting level):**

| Keyword        | Reason                                                                |
| -------------- | --------------------------------------------------------------------- |
| `$schema`      | Gemini / OpenAI structured-output endpoints reject meta-schema pointer |
| `$id`          | Not recognized by either provider                                     |
| `uniqueItems`  | Not supported by either provider                                      |
| `definitions`  | Ref-target pool — dropped after inlining (no orphan targets)          |
| `$defs`        | Same as above (Draft 2019-09+ name)                                   |

**Stripped conditionally:**

| Keyword                        | When                                                                                                           |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `additionalProperties`         | Only when value is literally `False`. Schema-dict forms (e.g., `{"type": "string", "enum": [...]}`) preserved. |
| `$ref` (pure-ref node)         | Always — replaced with the deep-copied resolved target, then recursively walked                                |
| `$ref` (with sibling keywords) | `$ref` is dropped; siblings preserved (Draft 2020-12 conservative choice; keeping `$ref` would leak to API)    |

**Preserved (whitelist of what canonical schemas rely on):**

`type`, `properties`, `required`, `items`, `enum`, `const`, `description`, `format`, `minimum`, `maximum`, `pattern`, `additionalProperties` (as schema dict), and every other keyword not listed above (the walker is deny-list-based, not allow-list-based — any future canonical keyword flows through untouched unless explicitly stripped).

### `$ref` Handling Rules

1. **Pure-ref node** (`{"$ref": "#/definitions/Foo"}`, single key): deep-copied resolved target replaces the node; recursion continues into the resolved content.
2. **Mixed-ref node** (`{"$ref": "...", "description": "..."}`, multiple keys): `$ref` key dropped, sibling keys preserved and walked. This is the conservative choice — keeping `$ref` would leak it to the provider API.
3. **Unresolvable ref** (`#/definitions/Missing` where `Missing` doesn't exist): raises `SchemaAdapterError`.
4. **External ref** (`https://example.com/schema.json`, or any string not starting with `#/`): raises `SchemaAdapterError`. Only internal JSON-pointer refs are supported.
5. **JSON-pointer RFC-6901 escapes**: `~1` decoded to `/`, `~0` decoded to `~`. Verified via code path, not test (no current canonical schema uses escaped keys).
6. **After recursion completes**, the top-level `definitions` / `$defs` pools are dropped — all references have already been inlined, so the pools are dead weight.

### Idempotency + Non-Mutation Guarantees

- **Deepcopy at entry:** `to_api_schema` calls `copy.deepcopy(canonical)` as its first line. The walker operates on the copy. Even when `$ref` targets are inlined (which in a naive implementation would mutate the root's `definitions` pool), the caller's dict is untouched.
- **Idempotent:** Applying `to_api_schema` twice returns the same dict. Verified by `test_idempotent` (inline case) and by the real-schema round-trip test (applies to video_analysis canonical).
- **Pure:** No I/O, no globals modified, no imports of `os`/`pathlib`/`requests`. Module imports are strictly `copy.deepcopy` + `typing.Any` + `__future__ import annotations`.

### `tests/unit/test_schema_adapter.py` — 16 Tests

| #  | Test Method                                         | What It Verifies                                                                  |
| -- | --------------------------------------------------- | --------------------------------------------------------------------------------- |
| 1  | `test_strips_schema_and_id`                         | Top-level `$schema` and `$id` both stripped; `type` preserved                     |
| 2  | `test_strips_additional_properties_false`           | `additionalProperties: false` removed                                             |
| 3  | `test_keeps_additional_properties_object`           | `additionalProperties: {"type": "string", "enum": [...]}` preserved exactly       |
| 4  | `test_strips_unique_items`                          | `uniqueItems: True` removed; `items` schema preserved                             |
| 5  | `test_nested_strip`                                 | Strips apply at arbitrarily nested levels (uniqueItems in tags, $id in meta)      |
| 6  | `test_inlines_internal_ref`                         | `#/definitions/Foo` pointer replaced with the resolved schema content             |
| 7  | `test_inlines_defs_variant`                         | `#/$defs/Bar` variant also resolves correctly                                     |
| 8  | `test_drops_definitions_pool_after_inline`          | Top-level `definitions` / `$defs` keys absent from output after inlining          |
| 9  | `test_raises_on_unresolvable_ref`                   | `#/definitions/Missing` raises `SchemaAdapterError`                               |
| 10 | `test_raises_on_external_ref`                       | `https://...` ref raises `SchemaAdapterError`                                     |
| 11 | `test_idempotent`                                   | `to_api_schema(to_api_schema(x)) == to_api_schema(x)` on a mixed-features fixture |
| 12 | `test_does_not_mutate_input`                        | Deepcopy-snapshot equality check after call with internal $ref + nested strips    |
| 13 | `test_preserves_enum_required_type_properties_items` | All core structural keywords flow through untouched                               |
| 14 | `test_preserves_description_format_pattern`         | `description`, `format`, `pattern` preserved                                      |
| 15 | `test_ref_siblings_conservative_behavior`           | `$ref` + sibling `description` → `$ref` dropped, sibling kept                     |
| 16 | `test_real_video_analysis_schema_round_trip`        | Real Plan 01-01 schema: zero $schema/$id/$ref/uniqueItems in output + confidence-map additionalProperties preserved + required dimensions intact + pacing_style enum intact |

## Evidence

### Success Criteria Checkboxes

- [x] `lib/schema_adapter.py` exists and exports `to_api_schema(canonical: dict) -> dict` pure function
- [x] Strips: `$ref` (inlined), `additionalProperties: False` (literal only), `uniqueItems`, `$schema`, `$id`
- [x] Preserves: `required`, `enum`, `type`, `properties`, `items`
- [x] Does NOT mutate input (deep-copy) — verified by `test_does_not_mutate_input`
- [x] Idempotent: `to_api_schema(to_api_schema(x)) == to_api_schema(x)` — verified by `test_idempotent`
- [x] `tests/unit/test_schema_adapter.py` exists and passes — `pytest tests/unit/test_schema_adapter.py -x -q` → 16 passed
- [x] Round-trip test using real `video_analysis.schema.json` passes (last entry in table above)
- [x] No new dependencies — stdlib-only imports verified via `grep -E "^import |^from " lib/schema_adapter.py`

### Round-Trip Evidence on Real Schema

```
$ python3 -c "
import json
from lib.schema_adapter import to_api_schema
c = json.load(open('schemas/artifacts/video_analysis.schema.json'))
a = to_api_schema(c)
s = json.dumps(a)
for k in ['\"\$schema\"', '\"\$id\"', '\"\$ref\"', '\"uniqueItems\"']:
    assert k not in s, f'{k} leaked'
assert 'editing_pacing' in a['required']
assert a['properties']['editing_pacing']['properties']['confidence']['additionalProperties'] == {
    'type': 'string', 'enum': ['low', 'medium', 'high']
}
print('OK')
"
OK
```

### Regression Evidence (Prior Plans Still Green)

```
$ pytest tests/unit/test_schema_adapter.py tests/contracts/test_video_analysis_schema.py tests/contracts/test_pipeline_synthesis_schema.py -q
.............................................                           [100%]
45 passed in 1.04s
```

- 16 new tests (Plan 01-03)
- 12 tests (Plan 01-01 `test_video_analysis_schema.py`)
- 17 tests (Plan 01-02 `test_pipeline_synthesis_schema.py`)

## Deviations from Plan

None — plan executed exactly as written. The exact implementation skeleton from `01-03-PLAN.md` was used verbatim (identical public API, identical walker logic, identical error-message wording). The test file follows the exact skeleton specified in the plan with all 16 tests present.

## Deferred Issues

### Pre-existing devcontainer disk-full environmental failure (out of scope)

- **Found during:** Plan 01-03 verification while running `pytest tests/contracts/test_phase0_contracts.py`
- **Symptom:** Multiple `TestCheckpoint::*` and `TestToolRegistry::*` tests error with `OSError: [Errno 28] No space left on device: '/tmp/pytest-of-*'`
- **Root cause:** Devcontainer overlay filesystem at 100% (`df -h /` reports 56G/59G, 0 Avail). `pytest`'s `tmp_path_factory` cannot create numbered tmp dirs under `/tmp/pytest-of-*`.
- **Scope decision:** Pre-existing environmental issue, reproducible on `git stash` of Plan 01-03 changes. Completely orthogonal to this plan (pure-function Python module + unit tests that touch zero tmp paths). Plan 01-03's own tests and Plans 01-01/01-02 regression tests all pass (45/45). Logged to `.planning/phases/01-schema-adapter/deferred-items.md` under "Devcontainer overlay filesystem full".

## Requirements Completed

- **ANLZ-03** — `lib/schema_adapter.py` produces API-safe flat schema; strips `$ref`, `additionalProperties: false`, `uniqueItems`; unit tests pass without API key. (The adapter half — provider integration lands in Phases 2 and 3.)
- **INT-04** (adapter half) — Adapter function is verifiable before Plan 04 registers the stages. The checkpoint mapping side of INT-04 ships in Plan 01-04.

## Self-Check: PASSED

- FOUND: `lib/schema_adapter.py`
- FOUND: `tests/unit/test_schema_adapter.py`
- FOUND commit: `799c60c` (feat(01-03): implement lib/schema_adapter.py pure canonical->API converter)
- FOUND commit: `848ff32` (test(01-03): unit tests for lib.schema_adapter (16 tests, all green))
- Test run: 16/16 passing; Regression (Plans 01-01, 01-02): 29/29 passing; Combined: 45/45 passing.
