---
phase: 04
reviewed: 2026-04-17
status: findings
findings_count:
  blocker: 0
  high: 0
  medium: 3
  low: 6
  nit: 5
review_mode: full
---

# Phase 4: Code Review Report — Full Review

## Summary

Full read-through of `lib/video_chunker.py` (264 lines), `lib/analysis_merger.py` (805 lines), `lib/chunked_analyzer.py` (490 lines), `lib/analysis_errors.py` (extension), and all four test files (123 tests, all green).

**Bottom line: no blocker or high findings. Phase 4 is well-engineered pure-lib code.**

- Subprocess safety is correct everywhere — `shell=False` explicit, list argv, timeouts enforced, stderr captured into error messages.
- Cleanup paths are correct on all documented failure modes (ffmpeg failure, ffprobe failure in per-chunk loop, provider exception, merger exception, bypass sentinel).
- Merger rules match the schema and RESEARCH § Merger Rules; single validation gate at end (Pitfall 2 honored). Time-shift is applied exhaustively to the three documented fields (`energy_arc.timestamp_s`, `section_structure.approx_start_s`, `section_structure.approx_end_s`).
- ThreadPoolExecutor ownership uses `with` (guaranteed shutdown); worker count clamp `[1, 8]` with the VIDEO_CHUNK_WORKERS env override is correct; submission order is restored for the merger via `results.sort`.
- Cost tracker integration follows the estimate→reserve→reconcile contract per chunk; `video_name` is basename-only (STRIDE T-04-17 satisfied).

Findings below are all defensive-hardening or documentation tightening — none block Phase 4 acceptance. Three medium items represent latent bugs only under non-default configuration or unusual provider behavior.

---

## Medium

### MR-01: `chunking_metadata.provider` can fail schema validation when caller passes a non-enum provider string

**File:** `lib/chunked_analyzer.py:418, 469`
**Issue:** The schema at `schemas/artifacts/video_analysis.schema.json:317` restricts `chunking_metadata.provider` to enum `["gemini", "openrouter"]`. `analyze_chunked` extracts it from `provider_tool.provider` unconditionally:
```python
provider_name = getattr(provider_tool, "provider", None) or "unknown"
...
merged = merge_analyses(pairs, provider=provider_name)
```
If `provider_tool.provider` is anything else — say `"anthropic"`, `"local"`, or the literal fallback `"unknown"` (which triggers when the attribute is missing or None) — the terminal `validate_artifact` call inside `merge_analyses` raises `ValidationError`. Tests sidestep this by making every StubProvider set `provider = "gemini"` (`test_chunked_analyzer.py:50`, `test_phase4_chunked_path.py:47`), so the issue is hidden. A real caller passing `video_analyzer_selector` (which inherits provider from whichever sub-tool won) that happens to not use one of those two strings would crash at merge-time with a confusing schema error instead of an early argument validation.

**Fix:** Validate `provider_name` at the top of `analyze_chunked` before the expensive split/analyze/merge pipeline runs. Cheap and gives a clear error:
```python
_ALLOWED_PROVIDERS = {"gemini", "openrouter"}
provider_name = getattr(provider_tool, "provider", None) or "unknown"
if provider_name not in _ALLOWED_PROVIDERS:
    raise ValueError(
        f"provider_tool.provider={provider_name!r} is not in the "
        f"schema enum {sorted(_ALLOWED_PROVIDERS)} — merged artifact "
        f"would fail schema validation"
    )
```
Alternative: relax the schema enum to `{"type": "string"}` if providers beyond Gemini/OpenRouter are expected. Pick one — current code assumes the enum but doesn't enforce it.

---

### MR-02: Merger assumes each chunk's schema-required fields are present — silent default fallbacks mask bad input

**File:** `lib/analysis_merger.py:295, 394, 400, 538, 551, 602, 637, 655`
**Issue:** Several required-schema fields fall back to a hardcoded default when the weighted majority is `None`. Example at line 295:
```python
merged["pacing_style"] = pacing or dims[0].get("pacing_style", "steady_educational")
```
If every per-chunk artifact is missing `pacing_style` (or the field is somehow `None` across all chunks), the merger silently injects the default value `"steady_educational"` and produces a schema-valid artifact that lies about the actual content. The merger docstring says "Each per-chunk artifact is assumed schema-valid upstream" (line 756) — but the fallback exists specifically for the case when that assumption is violated. This defeats the "single validation gate" guarantee: instead of a `ValidationError` that says "chunk 2 is missing required field", you get a plausible-looking merged artifact with fabricated defaults.

Also the same pattern at 394 (`narration_style` → "none"), 400 (`voice_music_mix` → "narration_dominant"), 538 (`production_quality` → "professional"), 551 (`aspect_ratio` → "16:9"), 602 (`narrative_arc` → "linear"), 637 (`target_platform` → "unknown" — which is NOT in the schema enum and WILL fail validation), 655 (`content_tone` → "educational").

Additional gotcha: `merged["target_platform"] = tp or first.get("target_platform", "unknown")` — `"unknown"` is not a member of the target_platform enum (schema lines 272-284). If every chunk is missing the field, this path produces a schema-invalid artifact and the terminal `validate_artifact` catches it, but with a confusing ValidationError pointing at a value the merger itself inserted.

**Fix:** Prefer one of:
1. **Trust the docstring**: remove the `or dims[0].get(..., DEFAULT)` fallback and let `None` propagate — `validate_artifact` will then correctly flag the missing required field in the per-chunk input.
2. **Early-validate**: validate each per-chunk artifact on entry (`for _, art in chunks: validate_artifact("video_analysis", art)`), pay the double-validation cost, fail loudly on malformed input. Pitfall 2's "single gate" rationale was about catching merger bugs, not masking provider bugs — pre-validation is a different safety axis.
3. At minimum, fix line 637 — `"unknown"` is not a valid `target_platform` enum value; use `"long_form"` or similar.

---

### MR-03: `on_chunk_error="continue"` may produce an invalid merged artifact when survivor set is size 1 and hook/cta chunks died

**File:** `lib/chunked_analyzer.py:454-462`, `lib/analysis_merger.py:589-590, 781`
**Issue:** In `"continue"` mode the orchestrator drops failed chunks from `pairs` (line 448-454) and forwards only the survivors to `merge_analyses`. If `pairs` has length 1 the merger takes the single-chunk pass-through path (`_pass_through_single`) — which uses the surviving chunk's `hook_*` and `cta_*` verbatim. But the surviving chunk may not have been chunk 0 or chunk N-1 — so `hook_type` and `cta_type` now come from a middle-of-video chunk where those fields describe local hooks/CTAs, not the video-as-a-whole hook/CTA. The position-based merge rules (CHUNK-04, merger docstring line 40-45) are silently violated.

Also with multiple survivors but failed chunks at index 0 or N-1: `_merge_narrative` uses `dims[0]` / `dims[-1]` based on surviving pairs, so if the original chunks[0] failed, the "hook" in the merged artifact comes from what was originally chunks[1] — again a silent position lie.

**Fix:** Either
1. In `"continue"` mode, record the ORIGINAL chunk indices of survivors and let the merger re-reason about position. Preferred: pass the full `(chunk, art_or_None)` list to merger and have merger pick the lowest-index successful chunk for hook and highest-index successful chunk for CTA.
2. Document explicitly in the docstring that `"continue"` mode produces merged artifacts with best-effort (not strictly positional) hook/CTA fields — with a warning log when the first or last chunk failed.

Covered test (`test_continue_mode_merges_survivors`) doesn't cover this specifically — it fails chunk 1 (middle), so hook/CTA positions are still correct. Add a test that fails chunk 0 or chunk 2 to surface the issue.

---

## Low

### LO-01: `_weighted_avg` silently converts "unknown" to 0.0 instead of None

**File:** `lib/analysis_merger.py:86-88`
**Issue:** When every weight is zero (or the pair list is empty), `_weighted_avg` returns `0.0`. Callers downstream treat `0.0` and "no data" identically, so `merged["editing_pacing"]["cuts_per_minute"] = 0.0` could mean "zero cuts per minute" or "we never had any data". The merger docstring on the function says "callers can substitute None if they prefer omit semantics" — but callers (line 264-268, 267-272, etc.) never check. If a test scenario has `chunk_seconds=0` for all chunks (weights all zero), every weighted-avg silently becomes 0.0.

**Fix:** Change the sentinel to `None` and guard at each call site, OR document explicitly on each `_weighted_avg` call site that "no data" == 0.0 is accepted. Current behavior is mostly safe because weights are `end_global - start_global` which is always positive for valid chunks, so this is theoretical — but worth a one-line docstring note at the callers.

---

### LO-02: `_merge_shot_boundary_source` emits `"hybrid"` for cross-chunk disagreement between `"scene_detect"` and `"model"` but the schema enum is `["scene_detect", "model", "hybrid"]` — this is correct but undocumented

**File:** `lib/analysis_merger.py:687-690`
**Issue:** The function correctly returns `"hybrid"` both when any chunk reports `"hybrid"` AND when chunks disagree (e.g. one reports `"model"`, one reports `"scene_detect"`). The test `test_disagreement_becomes_hybrid` confirms this. But the public-facing semantics are ambiguous: a reader seeing `shot_boundary_source: "hybrid"` can't distinguish "the model itself used a hybrid approach per chunk" from "chunks disagreed". Downstream tooling that keys on `"hybrid"` gets conflated signals.

**Fix:** Add a brief field-level comment explaining the escalation rule. Not blocking — the schema accepts it — but future maintainers will appreciate the note.

---

### LO-03: `_build_chunking_metadata.per_chunk[].cost_usd` silently defaults to 0.0 for missing `_cost_usd`

**File:** `lib/analysis_merger.py:710`
**Issue:**
```python
"cost_usd": float(art.get("_cost_usd", 0.0) or 0.0),
```
The double-guard `.get(..., 0.0) or 0.0` is to avoid `None` → TypeError, but downstream cost auditing can't distinguish "this chunk actually cost $0.00 (cache hit)" from "this chunk's cost_usd wasn't stamped (bug upstream)". With `chunked_analyzer.py:450` always stamping `_cost_usd` before handing to merger, the missing case only occurs if a caller uses `merge_analyses` directly without the orchestrator — but the merger's public API allows that (it's a pure lib).

**Fix:** If `_cost_usd` is genuinely absent, log a debug/warning once per merge rather than silently zero-ing, and document in the merger docstring that `_cost_usd` is required for cost accuracy.

---

### LO-04: `_merge_audio.music_tempo_bpm` emits `None` only when `tempo_seen` is True but all tempos are None — doesn't distinguish from "all chunks omit the key"

**File:** `lib/analysis_merger.py:442-452`
**Issue:** The branch:
```python
if tempo_pairs:
    merged["music_tempo_bpm"] = _weighted_avg(tempo_pairs)
elif tempo_seen:
    merged["music_tempo_bpm"] = None
# else: field omitted
```
is clever — it emits `None` when at least one chunk provided the key explicitly as `None` (i.e. "no music"), and omits the field when all chunks just didn't set it. But the test `test_music_tempo_all_null` sets `music_tempo_bpm: None` for all chunks, which hits the `elif` and emits `None`. Fine so far. But if some chunks have `music_tempo_bpm: None` and others omit the key entirely, behavior depends on dict contents in a non-obvious way. This is more a maintainability concern than a bug.

**Fix:** Inline comment explaining the tempo_seen semantics (or unify — always omit when all-null, which is simpler and still schema-valid since `music_tempo_bpm` isn't required).

---

### LO-05: `_analyze_chunks` does not call `cost_tracker.reconcile` when `on_chunk_error="fail_fast"` raises — but only if the raise happens from a chunk that was never submitted

**File:** `lib/chunked_analyzer.py:293-309`
**Issue:** On `fail_fast`, the failing chunk gets a best-effort reconcile (`actual_usd=0.0, success=False`) before re-raising (lines 300-308). Correct. But the OTHER chunks — futures that had been submitted and reserved on the cost tracker but haven't resolved yet — never get their reconcile called. The `with ThreadPoolExecutor(...)` context manager (line 269) runs `pool.__exit__` which joins all pending futures, but `as_completed` already broke out of its loop via the raise, so those `reconcile` calls are skipped.

Impact: the cost tracker's "reserved" budget line items for still-pending chunks stay in `reserved` state forever (never moved to `completed` or `failed`). Budget dashboards will show phantom reservations that never clear.

**Fix:** In the `fail_fast` branch, iterate through all remaining `future_to_meta` entries and best-effort reconcile each as `success=False, actual_usd=0.0` before re-raising. OR add a `try/except Exception` wrapper around the outer `with ThreadPoolExecutor` that reconciles any orphan entries in `finally`. Second approach also handles the edge where the `with` exit itself raises.

Not currently tested — `test_fail_fast_default_first_exc_raises` uses `max_workers=1`, so there's only ever one in-flight future. Add a test with `max_workers=3`, chunk 0 raises, and verify all three chunks got reconciled.

---

### LO-06: `split_video` bypass path probes duration but never validates `duration > 0`

**File:** `lib/video_chunker.py:140-150`
**Issue:** If ffprobe returns `0.0` (zero-duration file — corrupt or mp4 with no samples), the bypass branch happily returns `Chunk(0.0, 0.0, path)`. Downstream merger weights this chunk at 0 duration; `_weighted_avg` returns 0.0 for all fields; the cost tracker reports a zero-duration video; validation might still pass. The user gets a "successful" analysis of an empty video.

**Fix:** Add a `if duration <= 0.0: raise VideoChunkingError(...)` guard after line 140. Pennies of defensive check.

---

## Nit

### NI-01: `Chunk` is a namedtuple with a `local_path: str` — could be `pathlib.Path` for consistency with the rest of the module

**File:** `lib/video_chunker.py:55`
**Issue:** `Chunk.local_path` is stringified in `split_video` (`str(vp)`, `str(p)`). Consumers (`chunked_analyzer.py:283`) pass it to `provider_tool.execute({"video_path": chunk.local_path})` as a string. Fine. But the rest of the module uses `Path` objects internally. Choosing `str` for the namedtuple field makes serialization easier but forces callers to `Path(ch.local_path)` if they need path ops.

**Fix:** Not worth changing — string is simpler for the provider-tool contract. Nit because either choice is defensible.

---

### NI-02: Default `max_chunk_seconds=300.0` is hardcoded as a default argument AND inline-compared — should be a module constant

**File:** `lib/video_chunker.py:112, 144, 150, 171`; `lib/chunked_analyzer.py:172, 202`
**Issue:** `300.0` appears as a default argument in two places and as the CHUNK-02 boundary constant. If Phase 5+ decides to tune the boundary (say to 240s for a different provider), both signatures need to stay in sync manually.

**Fix:**
```python
_MAX_CHUNK_SECONDS_DEFAULT = 300.0  # CHUNK-02
...
def split_video(video_path, max_chunk_seconds: float = _MAX_CHUNK_SECONDS_DEFAULT):
```
Matches the `_WORKER_DEFAULT` / `_TOKENS_PER_VIDEO_SECOND` convention already used in `chunked_analyzer.py`.

---

### NI-03: `Callable` imported from `typing` in `lib/analysis_merger.py` but unused

**File:** `lib/analysis_merger.py:57`
**Issue:** `from typing import Any, Callable` — `Callable` is not referenced anywhere in the file. Linters (ruff F401) will flag it.

**Fix:** Remove `Callable` from the import.

---

### NI-04: `from lib.video_chunker import Chunk, cleanup_chunks, split_video  # noqa: F401`

**File:** `lib/chunked_analyzer.py:80`
**Issue:** The `# noqa: F401` suggests `Chunk` is re-exported for callers but the module docstring / `__all__` doesn't declare it. Either the noqa is masking real dead code (Chunk isn't used in this file after all — wait, it IS used at line 245, 252, 266, 441). So `Chunk` IS used, `cleanup_chunks` and `split_video` are used. Why `noqa: F401`?

**Fix:** Remove the `# noqa: F401` — all three symbols are actively referenced. The comment is misleading.

---

### NI-05: `_PRICING_VERIFIED_AT` module constant is defined but never referenced

**File:** `lib/chunked_analyzer.py:95`
**Issue:** `_PRICING_VERIFIED_AT = "2026-04-17"` is defined but code uses `pricing["verified"]` from the nested table entries instead. The module-level stamp is documentation-only.

**Fix:** Either reference it (e.g. assert `all(v["verified"] == _PRICING_VERIFIED_AT for v in _PRICING.values())` in a module-level sanity check), or remove it and keep only the per-entry `verified` key. Having both encourages drift.

---

## Positive Observations

Beyond the findings:

1. **Subprocess safety is exemplary** — `shell=False` explicit (redundant since default, but makes the safety guarantee load-bearing and easy to grep); list argv always; timeouts bounded; stderr captured into domain errors. Both `CalledProcessError` and `TimeoutExpired` handled distinctly.
2. **Cleanup paths have 100% coverage** — ffmpeg failure (line 189), ffmpeg timeout (194), empty glob (201), per-chunk ffprobe failure in loop (233) all rmtree the scratch dir before re-raising. The sole "leak" path is if `sorted()` / `tmpdir.glob()` itself raises — which can't happen in practice.
3. **`cleanup_chunks` bypass sentinel** is the right abstraction — single comparison `ch.local_path == original_str` at line 254 protects the user's input file in the one place deletion could happen. Belt-and-braces.
4. **Merger single-validation-gate** is correctly implemented — `validate_artifact` called exactly once at the end (merger tests explicitly assert `spy.call_count == 1` in `test_validate_called_once_per_merge`).
5. **Energy-arc + section-structure time-shift** is applied to exactly the three documented schema fields — no more, no less. Diligent cross-ref with the schema.
6. **Worker envelope `[1, 8]`** clamp + VIDEO_CHUNK_WORKERS override + unparseable-env fallback with warning log is correct and tested (`test_worker_count_invalid_env`, `test_worker_count_clamp_*`).
7. **Cost tracker calls** use kwargs exclusively (`tool=`, `operation=`, `estimated_usd=`, `actual_usd=`, `success=`) — future-proof against positional-arg drift in the tracker interface.
8. **`video_name = Path(video_path_str).name`** in the cost-tracker operation string — basename only, no filesystem path leakage (STRIDE T-04-17 honored).
9. **Deep-copy in merger** (lines 239, 355, 511, 568, 735) — merger treats inputs as immutable, which the test `test_single_chunk_deep_copied` verifies. Good hygiene.
10. **`ThreadPoolExecutor` used as a context manager** — auto-shutdown via `with pool:` guarantees worker threads drain even on exception paths.

## Test Coverage Assessment

- 123 tests across four files. Cover bypass path, multi-chunk, subprocess failure modes, cleanup on success/failure, worker resolution (all branches), cost tracker estimate/reserve/reconcile, fail_fast vs. continue, per-dimension merger rules, time-shift correctness, schema gate.
- **Gaps identified by this review**:
  - No test for `fail_fast` mode with `max_workers > 1` (LO-05 — orphan reservations).
  - No test for `continue` mode with chunks 0 or N-1 failing (MR-03 — hook/CTA position lie).
  - No test for schema-invalid `provider_name` (MR-01 — validation failure).
  - No test for zero-duration video (LO-06).
  - No test for all-chunks-missing-required-field (MR-02 — silent default injection).

## Conclusion

**Status: findings — all medium or below.** No blocker or high items; Phase 4 is acceptance-ready. Medium items are latent bugs under non-default or degraded-input configurations; low items are defensive-hardening; nits are minor cleanup.

Recommend tracking MR-01, MR-02, MR-03 as follow-up items for Phase 5+ (when real providers exercise the chunked path with production inputs). LO and NI items can be batched into a future cleanup pass.

---

*Review mode: full (read-through of 4 source files + 4 test files + cross-reference against canonical schema).*
