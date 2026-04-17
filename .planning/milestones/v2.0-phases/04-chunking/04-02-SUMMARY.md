---
phase: 04-chunking
plan: 02
subsystem: analysis_merger
tags: [chunking, merger, schema, aggregation, video_analysis]
requires:
  - lib.video_chunker.Chunk (Plan 04-01)
  - schemas.artifacts.validate_artifact (Phase 1)
  - tests.contracts.test_video_analysis_schema.minimal_video_analysis (Phase 1)
provides:
  - lib.analysis_merger.merge_analyses
  - tests.unit.conftest.fake_video_chunks fixture
affects:
  - Plan 04-03 (chunked_analyzer orchestrator — consumes merge_analyses)
  - Phase 6 reference-synthesis meta skill (downstream consumer of merged artifact)
tech_stack_added: []
patterns:
  - "Duration-weighted aggregation (numeric avg, categorical majority)"
  - "Order-preserving union-dedup via dict.fromkeys"
  - "Top-N-by-frequency capping for color-like arrays (Counter.most_common)"
  - "Worst-case min confidence aggregation — any 'low' → 'low'"
  - "Free-text concat with [chunk N/M] markers"
  - "Single validate_artifact gate at merge end (RESEARCH Pitfall 2)"
key_files_created:
  - lib/analysis_merger.py
  - tests/unit/test_analysis_merger.py
key_files_modified:
  - tests/unit/conftest.py
decisions:
  - "shot_boundary_source='hybrid' on cross-chunk disagreement OR any chunk='hybrid' (RESEARCH Open Question 2)"
  - "Single-chunk path strips private '_*' keys before schema validation (prevents _cost_usd hint from polluting canonical output)"
  - "_worst_confidence defaults to 'high' on empty input (no pessimism signal)"
  - "aspect_ratio disagreement logged at WARNING, merged uses chunks[0]"
  - "_merge_confidence_map honors 'missing != low' — keys only tracked in chunks that emit them"
metrics:
  tasks: 2
  completed_date: "2026-04-17"
  commits: 3
---

# Phase 04 Plan 02: analysis_merger Summary

Shipped `lib/analysis_merger.py` — the per-dimension video_analysis aggregator that walks `list[(Chunk, per_chunk_artifact)]`, applies field-level merge rules derived from the canonical schema, and returns one schema-valid merged artifact with globally-shifted timecodes, duration-weighted averages/votes, worst-case confidence aggregation, and full `chunking_metadata` traceability. Pure lib module, no BaseTool, no side effects.

## What Changed

| File | Lines | Role |
|------|-------|------|
| `lib/analysis_merger.py` | 805 | Merger module: 7 primitives, 4 per-dimension mergers (editing_pacing / audio / visual_style / narrative), `_merge_shot_boundary_source`, `_build_chunking_metadata`, `_pass_through_single`, `merge_analyses` public API |
| `tests/unit/test_analysis_merger.py` | 804 | 66 unit tests: primitives, single-chunk pass-through, fixture sanity, multi-chunk per-dimension rules, confidence aggregation, shot_boundary_source, chunking_metadata, schema gate |
| `tests/unit/conftest.py` | +70 | `fake_video_chunks` factory fixture + `_deep_merge` helper (applies per-chunk override dicts onto the Phase 1 canonical artifact) |

## Test Coverage by Rule Category

| Category | Tests | Key assertions |
|----------|-------|----------------|
| Primitives | 15 | weighted_avg (equal/unequal/zero weights/empty), weighted_majority (all-None sentinel), union_dedup order-preserving, top_n_by_frequency cap + tie-break, worst_confidence (low-wins, all-high, mixed-no-low, empty→high), concat_freetext skips empties |
| Single-chunk pass-through | 4 | Schema-valid output, chunking_metadata shape, source.duration unchanged, input deep-copied (mutation-safe) |
| Fixture sanity | 3 | Each per-chunk artifact is schema-valid, monotonic chunk timeline, deep-merge overrides reach nested fields |
| Error paths | 1 | `ValueError("≥1 chunk")` on empty input |
| `editing_pacing` | 9 | total_shots sum, cuts_per_minute weighted avg (equal + unequal weights), pacing_style weighted-majority tie-break, shortest/longest min/max, shot_type_distribution renormalized, transition_types dedup, energy_arc concat+shift |
| `audio` | 7 | has_narration/has_music OR, narration_wpm weighted over narrating-chunks only, music_tempo_bpm all-null → null, mixed-null → avg, voice_music_mix majority, suggested_tts_voice_profile first-chunk |
| `visual_style` | 5 | color_palette capped at 5, aspect_ratio first-chunk + WARNING log on disagreement (caplog), typography_style first-chunk prose, production_quality majority, dominant_colors_hex top-N |
| `narrative` | 8 | hook_type from chunks[0], cta_type from chunks[-1], hook/cta durations positional, section_count sum, section_structure concat+shift (approx_start_s, approx_end_s), target_duration_seconds sum, paragraph_pattern [chunk N/M] markers |
| Confidence aggregation | 3 | Worst-case low wins, all-high stays high, mixed-no-low → medium |
| `shot_boundary_source` | 4 | all-model → model, disagreement → hybrid, any-hybrid → hybrid, absent → field omitted |
| `chunking_metadata` | 3 | per_chunk index/start/end/cost/provider populated, total_duration_s == source.duration_seconds, per-chunk `_provider_used` override |
| Schema validation | 4 | N=3 + N=10 valid, validate_artifact called exactly once per merge, N-chunk idempotent (first-chunk rules) |
| **Total** | **66** | All green in `pytest tests/unit/test_analysis_merger.py -x -q` |

## RESEARCH Assumptions Validated

- **A7 (color cap N=5):** Validated. Plan's `_COLOR_CAP = 5` constant; `test_color_palette_capped_at_5` (8 distinct primary colors → merged has exactly 5) and `test_dominant_colors_hex_top_5` (frequency ranking preserved, `#A` wins because it appears in 3 chunks) both pass. Kept as a module-level constant so a future bump to N=8 is a one-line change.
- **A8 (`[chunk N/M]` concat marker):** Validated. `_concat_freetext` emits `[chunk 1/3] …  | [chunk 2/3] …` verbatim; `test_paragraph_pattern_concat_markers` asserts all three markers present. If Phase 5 synthesizer wants a different delimiter (``\n`` instead of ` | `) the change is isolated to `_concat_freetext`.

## Open Question Resolution

- **Open Question 2 — `shot_boundary_source` on disagreement:** Implemented as **"hybrid" if ANY chunk is 'hybrid' OR cross-chunk values differ, else first-chunk's value, else field omitted (all-None)**. Rationale: "hybrid" at the schema level means "this artifact's boundaries came from >1 source", which is literally true when chunks disagree (chunk-A used `scene_detect`, chunk-B used `model`). Verified by `test_disagreement_becomes_hybrid`, `test_any_hybrid_stays_hybrid`, `test_all_model` (stays `model`), and `test_absent_omits_field` (no `shot_boundary_source` key when all chunks omit it).

## Deviations from Plan

### Auto-fixed

**1. [Rule 2 - Missing critical functionality] Strip private `_*` keys before validation in single-chunk pass-through**

- **Found during:** Task 1 GREEN run
- **Issue:** Plan said "deep-copy chunks[0][1], attach chunking_metadata, validate, return". But per-chunk artifacts carry private hints (`_cost_usd`, `_provider_used`) that the chunked_analyzer stamps. These are NOT part of the canonical `video_analysis` schema; while `additionalProperties` is unset (implicitly true) at the top level today, they are implementation-leak — downstream consumers (Phase 5 synthesizer) should never see them.
- **Fix:** Added a `for key in list(merged.keys()): if key.startswith("_"): merged.pop(key, None)` pass in `_pass_through_single` before `validate_artifact`. Multi-chunk path builds a fresh dict so it's already clean.
- **Why it's Rule 2, not an architectural change:** Schema purity at a trust boundary (merger → downstream) — correctness requirement, not new functionality.
- **Files modified:** `lib/analysis_merger.py`
- **Commit:** d5ece46

**2. [Rule 2 - Missing critical functionality] Default `_worst_confidence([]) = "high"`**

- **Issue:** `_merge_confidence_map` can pass an empty list when no chunk has data for a given key. The plan didn't specify this edge case; naive code would have IndexError'd.
- **Fix:** Documented semantics: empty → "high" (no pessimism signal; missing != low).
- **Files modified:** `lib/analysis_merger.py`
- **Commit:** d5ece46

### Out-of-scope (not touched)

- Pre-existing `.planning/ROADMAP.md`, `.planning/STATE.md` dirty state from Phase-4 planning step. Not fixed here — belongs to the planner workflow's commit, not this plan's scope.

## Authentication Gates

None. This plan is pure lib + unit tests, no external services.

## Threat Flags

None beyond the declared STRIDE register. `validate_artifact` fires exactly once at merge end (T-04-07 mitigation verified by `test_validate_called_once_per_merge`); worst-case confidence is the ONLY aggregation path (T-04-08 mitigated); `_top_n_by_frequency(..., n=5)` caps all color-like arrays (T-04-09 mitigated); `chunking_metadata.per_chunk[]` captures cost + provider per chunk (T-04-10 mitigated); all 3 time-valued fields shift by `chunk.start_global` (T-04-11 mitigated by `test_energy_arc_concat_with_shift` + `test_section_structure_concat_and_shift`).

## Pointer to Plan 03

`lib/chunked_analyzer.py::analyze_chunked` will:

1. Call `lib.video_chunker.split_video` → `list[Chunk]`
2. ThreadPoolExecutor-fan-out `(chunk, provider_tool.execute({"video_path": chunk.local_path}))` → per-chunk `ToolResult`
3. Stamp `artifact["_cost_usd"] = tool_result.cost_usd` and `artifact["_provider_used"] = tool_result.model` (or similar) on each per-chunk `ToolResult.data`
4. Pass `[(chunk, artifact), …]` into `lib.analysis_merger.merge_analyses(chunks, provider=<resolved>)` → canonical merged `video_analysis` artifact
5. In a `try/finally`, call `lib.video_chunker.cleanup_chunks(chunks, original_path)` — cleanup must happen AFTER merge, not before

The merger is the schema-validation gate for the whole chunked path — a merger bug raises `jsonschema.ValidationError` at Plan 03's call site, making failures loud.

## Verification

```bash
# Test suite: 66 tests green
python3 -m pytest tests/unit/test_analysis_merger.py -x -q
# ➜  66 passed in 1.50s

# Full unit suite (regression check): 152 green
python3 -m pytest tests/unit/ -x -q
# ➜  152 passed in 7.90s

# Import gate
python3 -c "from lib.analysis_merger import merge_analyses; from lib.video_chunker import Chunk; print('OK')"
# ➜  OK

# No side-effect imports
grep -n 'write_checkpoint(\|cost_tracker\.' lib/analysis_merger.py
# ➜  No function calls found
```

## Commits

| Hash | Message |
|------|---------|
| 4ab2095 | test(04-02): add failing tests for analysis_merger primitives + N=1 pass-through |
| d5ece46 | feat(04-02): scaffold analysis_merger with primitives + N=1 pass-through |
| 94acbb2 | test(04-02): multi-chunk dispatch coverage (editing_pacing/audio/visual_style/narrative + confidence + shot_boundary_source + chunking_metadata) |

## Self-Check: PASSED

- `lib/analysis_merger.py` exists (805 lines, ≥280 target).
- `tests/unit/test_analysis_merger.py` exists (804 lines, ≥350 target; 66 tests, ≥35 target).
- `tests/unit/conftest.py` has `fake_video_chunks` fixture (verified via `grep -n 'def _build' tests/unit/conftest.py`).
- Commits 4ab2095, d5ece46, 94acbb2 all in git log.
- `merge_analyses` is importable.
- No `write_checkpoint` / `cost_tracker` calls in merger.
- Schema validation gate fires exactly once per merge (verified by `test_validate_called_once_per_merge`).
