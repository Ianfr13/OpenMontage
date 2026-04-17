---
phase: 01-schema-adapter
reviewed: 2026-04-17T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - lib/checkpoint.py
  - lib/schema_adapter.py
  - schemas/artifacts/__init__.py
  - schemas/artifacts/pipeline_synthesis.schema.json
  - schemas/artifacts/video_analysis.schema.json
  - tests/contracts/test_brief_schema_regression.py
  - tests/contracts/test_checkpoint_registration.py
  - tests/contracts/test_pipeline_synthesis_schema.py
  - tests/contracts/test_video_analysis_schema.py
  - tests/unit/test_schema_adapter.py
findings:
  critical: 0
  warning: 5
  info: 6
  total: 11
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-17
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

The schema adapter (`lib/schema_adapter.py`) is clean, well-documented, and honors its pure-function / no-mutation contract. The JSON Schemas are internally consistent and Draft 2020-12 compliant. Test coverage is broad — unit, contract, regression, and a real-schema round-trip.

That said, there are several correctness concerns worth addressing:

1. **Stage registry drift in `lib/checkpoint.py`**: the two new artifact-producing stages (`video_analysis`, `pipeline_synthesis`) are registered in `CANONICAL_STAGE_ARTIFACTS` but *not* in `ALL_KNOWN_STAGES`. A checkpoint for either stage that is written without a `pipeline_type` will be rejected by `validate_checkpoint`, even though the artifact names are otherwise accepted. This is a real inconsistency introduced by Phase 1.
2. **`to_api_schema` has no cycle guard.** Mutually-recursive `$ref` targets would infinite-loop. Current schemas have no cycles, but nothing prevents them in the future.
3. **`_merge_decision_log` is not concurrency-safe** and will `KeyError` on decisions missing `decision_id`.
4. **The v1.0 brief regression guard under-delivers on its name** — the test called `test_schema_file_was_not_modified_in_this_phase` only asserts three top-level fields; any other change to the file would pass silently.
5. **Bare `except Exception` in `get_pipeline_stages`** swallows all errors including programming bugs.

None of these are critical security issues and none block the phase, but they deserve follow-up before this module is relied on in production pipelines.

## Warnings

### WR-01: `ALL_KNOWN_STAGES` misses the new Phase 1 stages

**File:** `lib/checkpoint.py:20-23` (definition) and `lib/checkpoint.py:135-144` (use)
**Issue:** `CANONICAL_STAGE_ARTIFACTS` registers `video_analysis` and `pipeline_synthesis` as canonical stages (lines 40-41), but `ALL_KNOWN_STAGES` does not include them. `validate_checkpoint` falls back to `ALL_KNOWN_STAGES` when `pipeline_type` is absent (line 136-138), so a checkpoint with `stage: "video_analysis"` and no `pipeline_type` raises `CheckpointValidationError: Invalid stage …` — even though the artifact *name* is registered. `write_checkpoint` has the same gap at line 214-222.

This is exactly the kind of silent registry drift the test `test_stages_list_unchanged` (which asserts `STAGES` is unchanged) was designed to detect, but `ALL_KNOWN_STAGES` is a separate constant that escaped the guard.

**Fix:** Either (a) add the two new stages to `ALL_KNOWN_STAGES`, or (b) derive `ALL_KNOWN_STAGES` from `CANONICAL_STAGE_ARTIFACTS.keys()` so they cannot diverge:

```python
# Replace lines 20-23 with:
ALL_KNOWN_STAGES = frozenset(CANONICAL_STAGE_ARTIFACTS.keys())
```

(This requires moving the `CANONICAL_STAGE_ARTIFACTS` definition above `ALL_KNOWN_STAGES`.)

### WR-02: `to_api_schema` has no guard against circular `$ref` chains

**File:** `lib/schema_adapter.py:45-56`
**Issue:** When `_walk` encounters a pure-`$ref` node it calls `_resolve_ref` and then recurses with `_walk(deepcopy(resolved), root)`. If the resolved target contains (directly or transitively) a `$ref` back to itself or an ancestor, recursion never terminates. Current schemas don't have cycles, but the contract offers no protection and callers would see a `RecursionError` (or OOM from `deepcopy`) rather than a `SchemaAdapterError`.

**Fix:** Track a seen-set of ref pointers along the recursion path:

```python
def _walk(node: Any, root: dict, seen: frozenset[str] = frozenset()) -> Any:
    if isinstance(node, dict):
        if "$ref" in node and len(node) == 1:
            ref = node["$ref"]
            if ref in seen:
                raise SchemaAdapterError(f"Circular $ref detected: {ref!r}")
            resolved = _resolve_ref(ref, root)
            return _walk(deepcopy(resolved), root, seen | {ref})
        # ... rest unchanged, pass `seen` through recursive calls
```

### WR-03: `_merge_decision_log` is not concurrency-safe and will `KeyError` on malformed input

**File:** `lib/checkpoint.py:166-193`
**Issue:** Two problems:

1. **Race condition:** The function reads the file, mutates in memory, then writes it back (lines 176-193). Two concurrent `write_checkpoint` calls for the same project can lose decisions — the second write overwrites the first with a version that never saw its changes. There is no file lock or atomic rename.
2. **`KeyError`:** Line 186 uses `{d["decision_id"] for d in existing.get("decisions", [])}`. If any existing decision is missing `decision_id` (schema-invalid log, hand-edited file, older format), the whole checkpoint write fails mid-flight — after the checkpoint schema has been validated but before the checkpoint file is written. Likewise line 188 with `decision.get("decision_id")` compares `None` against a set of strings, silently deduplicating all unkeyed new decisions to the first one.

**Fix:**
- Write to a temp file and `os.replace` for atomicity; add an advisory file lock (`fcntl.flock` on POSIX) if concurrency is possible.
- Filter defensively: `existing_ids = {d["decision_id"] for d in existing.get("decisions", []) if isinstance(d, dict) and "decision_id" in d}` and skip new decisions without an id (or raise a clearer `CheckpointValidationError`).

### WR-04: `get_pipeline_stages` catches bare `Exception` and logs on every fallback call

**File:** `lib/checkpoint.py:62-77`
**Issue:** Two issues in the same function:

1. Line 75: `except (FileNotFoundError, Exception):` — `Exception` already covers `FileNotFoundError`, and catching bare `Exception` swallows programming errors (AttributeError, TypeError in `load_pipeline`/`get_stage_order`) indistinguishably from the expected "manifest missing" case. Silent fallback from a real bug looks like a normal pipeline.
2. Line 63-68: `get_pipeline_stages(None)` logs a WARNING on every call. `get_completed_stages` and `get_next_stage` both call this path whenever `pipeline_type` is `None`, which in turn is called by the orchestrator every time it resumes. Expect warning spam.

**Fix:**

```python
try:
    from lib.pipeline_loader import load_pipeline, get_stage_order
    manifest = load_pipeline(pipeline_type)
    return get_stage_order(manifest)
except FileNotFoundError:
    logging.getLogger(__name__).info(
        "No pipeline manifest for %r, using canonical fallback order.", pipeline_type
    )
    return list(STAGES)
```

Let real exceptions propagate. Downgrade the `None` warning to `debug` or remove it.

### WR-05: `write_checkpoint` masks missing `pipeline_type` with the literal string `"unknown"`

**File:** `lib/checkpoint.py:227`
**Issue:** `"pipeline_type": pipeline_type or "unknown"` writes the string `"unknown"` into the persisted checkpoint when the caller forgot to pass `pipeline_type`. Downstream readers (`get_pipeline_stages`, `validate_checkpoint`) cannot distinguish "legitimately unknown" from "caller bug" — and a checkpoint with `pipeline_type: "unknown"` will be re-validated with the `ALL_KNOWN_STAGES` fallback on read, which (per WR-01) doesn't include `video_analysis` / `pipeline_synthesis`.

**Fix:** Either make `pipeline_type` required for `write_checkpoint` (preferred), or omit the key entirely when `None` and let `validate_checkpoint`'s existing `None` branch handle it consistently. Writing a placeholder string is the worst option.

## Info

### IN-01: `test_schema_file_was_not_modified_in_this_phase` does not actually prove the schema file was not modified

**File:** `tests/contracts/test_brief_schema_regression.py:80-91`
**Issue:** The test name promises a strong guarantee, but the assertions only check `type == "object"`, the set of `required` keys, and `properties.version.const`. Any other change — adding a new property, widening an enum, rewriting a description, changing `$schema` URL — would pass this test. The Phase plan says "editing the v1.0 file is forbidden"; the test does not enforce that.

**Fix:** If the goal is a true lock, store a checksum in the test and compare:

```python
import hashlib
EXPECTED_SHA256 = "abcdef…"  # captured at phase-start
assert hashlib.sha256(BRIEF_SCHEMA_PATH.read_bytes()).hexdigest() == EXPECTED_SHA256
```

If the goal is just "core shape unchanged", rename the test to `test_schema_core_shape_preserved` so it doesn't overclaim.

### IN-02: `test_rejects_missing_required` does not parametrize over `version`

**File:** `tests/contracts/test_pipeline_synthesis_schema.py:20-24, 59-65`
**Issue:** `SYNTH_09_REQUIRED` intentionally excludes `version`, but `version` *is* in the schema's `required` array (`pipeline_synthesis.schema.json:7-17`). The parametrized "rejects missing required field" test therefore never checks that a missing `version` is rejected. `test_rejects_invalid_version_const` covers the *wrong-value* case but not the *missing* case.

**Fix:** Either add `"version"` to `SYNTH_09_REQUIRED`, or add a dedicated `test_rejects_missing_version` next to the invalid-const test.

### IN-03: `_resolve_ref` uses `str.lstrip("#/")` which is character-class strip, not prefix strip

**File:** `lib/schema_adapter.py:87`
**Issue:** `ref.lstrip("#/")` removes any leading run of `#` or `/` characters, not the literal prefix `"#/"`. It works for the common case `"#/foo/bar"` because of the earlier `startswith("#/")` guard, but pointers like `"#//foo"` (double slash) or a hypothetical `"##/foo"` would be quietly "normalized" instead of rejected. The intent is clearer with `ref[2:]`.

**Fix:**

```python
for part in ref[2:].split("/"):  # strip the exact "#/" prefix
```

### IN-04: Silent `$ref`-drop when siblings are present may produce a schema that is looser than canonical

**File:** `lib/schema_adapter.py:61-64`
**Issue:** When a node has both `$ref` and sibling keywords, the adapter drops the `$ref` and keeps the siblings (documented at lines 50-52 and verified by `test_ref_siblings_conservative_behavior`). In Draft 2020-12 the sibling keywords *add to* the referenced schema — so the API-safe output silently *removes* whatever constraints the referenced definition imposed. For current schemas this path is unused; if a future canonical schema uses `$ref`+siblings legitimately, the structured-output call would be validated against a looser schema than intended.

**Fix:** Option A — raise `SchemaAdapterError` in this case so the author is forced to either pure-ref or fully inline. Option B — inline the ref AND merge siblings (with sibling keys overriding). Current behavior is defensible but should be explicit in the module docstring, not just the inline comment.

### IN-05: Multiple tests use `json.load(open(path))` without a context manager

**File:** `tests/contracts/test_brief_schema_regression.py:87`, `tests/contracts/test_pipeline_synthesis_schema.py:44`, `tests/contracts/test_video_analysis_schema.py:76`, `tests/unit/test_schema_adapter.py:150`
**Issue:** `json.load(open(path))` leaks the file handle until garbage collection. On CPython it closes deterministically, but pytest's ResourceWarning mode and PyPy do not. Minor, but inconsistent with the `with open(...)` pattern used throughout `lib/`.

**Fix:** `json.loads(Path(path).read_text())` or wrap in `with open(path) as f: json.load(f)`.

### IN-06: `test_inlines_internal_ref` uses substring match on JSON dump

**File:** `tests/unit/test_schema_adapter.py:73`
**Issue:** `assert "$ref" not in json.dumps(out)` will false-positive if any property *value* happens to contain the literal substring `"$ref"` (e.g., a description string mentioning `$ref`). Current fixture is safe, but the assertion style is fragile.

**Fix:** Walk the structure and assert no dict contains the key `"$ref"`, or keep `json.dumps` but match the serialized *key* form `'"$ref":'`:

```python
assert '"$ref":' not in json.dumps(out)
```

---

_Reviewed: 2026-04-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
