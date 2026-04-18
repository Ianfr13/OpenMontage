---
phase: 11-drift-hygiene
plan: 02
subsystem: code-hygiene
tags: [nits, absorption, atomic-commits, hygiene]
requirements: [NITS-01]
dependency_graph:
  requires:
    - tools/analysis/openrouter_video_analyzer.py (Phase 3)
    - lib/video_chunker.py, lib/analysis_merger.py, lib/chunked_analyzer.py (Phase 4)
    - lib/pipeline_synthesizer.py, lib/llm_fill.py (Phase 5)
  provides:
    - 30 LO/NI items with explicit disposition
    - atomic commits for each fix
    - REQUIREMENTS.md Future Requirements entries for deferred items
  affects:
    - tools/analysis/openrouter_video_analyzer.py
    - tests/unit/test_openrouter_video_analyzer.py
    - tests/unit/test_pipeline_synthesizer.py
    - lib/analysis_merger.py
    - lib/chunked_analyzer.py
    - lib/video_chunker.py
    - lib/pipeline_synthesizer.py
    - lib/llm_fill.py
    - tests/contracts/test_phase5_synthesis.py
    - .planning/REQUIREMENTS.md
tech_stack:
  added: []
  patterns:
    - narrow-atomic-commit-per-fix
    - defer-behavior-changing-nits
    - grep-evidence-for-already-resolved
key_files:
  created: []
  modified:
    - (populated after fix pass — see Commits section below)
decisions:
  - "NITS-01: defer any fix that requires a new test or changes observable behavior"
  - "NITS-01: use (11-nits) scope on every absorb commit so git log --grep is a clean audit trail"
metrics:
  duration_minutes: 0
  tasks_completed: 0
  commits: 0
  tests_added: 0
  completed_date: "TBD"
---

# Phase 11-02: NITS-01 Absorption — Classification

**Catalogue source:** 03-REVIEW.md (9 items) + 04-REVIEW.md (11 items) + 05-REVIEW.md (10 items) = **30 items total**
**Classified:** 2026-04-18
**Target test baseline:** >=689 passing (inherited from Plan 11-01)

## Per-finding Catalogue Count Verification

- Phase 3 LO: LO-01, LO-02, LO-03, LO-04 → 4 items
- Phase 3 NI: NI-01, NI-02, NI-03, NI-04, NI-05 → 5 items
- **Phase 3 subtotal: 9 items** (matches 03-REVIEW.md `low: 4, nit: 5`)
- Phase 4 LO: LO-01, LO-02, LO-03, LO-04, LO-05, LO-06 → 6 items
- Phase 4 NI: NI-01, NI-02, NI-03, NI-04, NI-05 → 5 items
- **Phase 4 subtotal: 11 items** (matches 04-REVIEW.md `low: 6, nit: 5`)
- Phase 5 LR: LR-01, LR-02, LR-03, LR-04, LR-05, LR-06 → 6 items
- Phase 5 NR: NR-01, NR-02, NR-03, NR-04 → 4 items
- **Phase 5 subtotal: 10 items** (matches 05-REVIEW.md `low: 6, nit: 4`)
- **Grand total: 30 items** ✓

## Classification Table

| ID | Origin | File | Disposition | Commit / Evidence | Rationale |
|----|--------|------|-------------|-------------------|-----------|
| P3-LO-01 | 03-REVIEW.md#LO-01 | tools/analysis/openrouter_video_analyzer.py:76 | fix | TBD | Delete dead FALLBACK_MODEL constant + matching test-import (test never asserts it) |
| P3-LO-02 | 03-REVIEW.md#LO-02 | tools/analysis/openrouter_video_analyzer.py:455 | fix | TBD | Add one-line comment explaining asymmetric ladder (branch-1 stops early vs branch-2 continues) |
| P3-LO-03 | 03-REVIEW.md#LO-03 | tools/analysis/openrouter_video_analyzer.py:355-359, 579-581 | defer | NITS-DEF-P3-LO-03 | Defense-in-depth key redaction; review itself says "current SDK verified — defer is cheap"; adding _safe_exc_str requires a new unit test that mocks APIError.__str__ with a fake key — new test = behavior/test change outside absorb scope |
| P3-LO-04 | 03-REVIEW.md#LO-04 | tools/analysis/openrouter_video_analyzer.py:283-290 | defer | NITS-DEF-P3-LO-04 | Stripping markdown fences requires a new unit test against prompt-embedded path with fenced content; review acknowledges current mock test does not exercise this. New test = behavior change; defer |
| P3-NI-01 | 03-REVIEW.md#NI-01 | tools/analysis/openrouter_video_analyzer.py:112-143 | defer | NITS-DEF-P3-NI-01 | Duplicated shot-boundary helpers; review says "Fine disposition for now; flagging so it's on the Phase 6 cleanup list" — extraction to lib/ is a refactor, not an absorb |
| P3-NI-02 | 03-REVIEW.md#NI-02 | tools/analysis/openrouter_video_analyzer.py:187 (now :217) | defer | NITS-DEF-P3-NI-02 | `_FLAT_SCHEMA: dict \| None = None` shared-mutable class attribute. Review explicitly says "Not worth changing for this phase." Defer per review's own disposition |
| P3-NI-03 | 03-REVIEW.md#NI-03 | tools/analysis/openrouter_video_analyzer.py:66-68 | already-resolved | commit 2995862 (Phase 8 CLEAN-04) + commit covers FALLBACK_MODEL under P3-LO-01 | `grep -n 'OPENROUTER_BASE_URL' tools/analysis/openrouter_video_analyzer.py` shows the constant is now used at the OpenAI() constructor (line 614). FALLBACK_MODEL deletion handled as P3-LO-01 |
| P3-NI-04 | 03-REVIEW.md#NI-04 | tests/unit/test_openrouter_video_analyzer.py:529-541 | fix | TBD | Trim over-provisioned truncated responses from 6 → 4 (comment already says "up to 4"); narrow consistency fix |
| P3-NI-05 | 03-REVIEW.md#NI-05 | tools/analysis/openrouter_video_analyzer.py:260-265 (now :291-293) | fix | TBD | Extract "30 words" magic number to `COMPACT_FIELD_WORD_LIMIT` module constant and reference it in the prompt-builder |
| P4-LO-01 | 04-REVIEW.md#LO-01 | lib/analysis_merger.py:86-88 | fix | TBD | Add one-line docstring note on `_weighted_avg` at callers re: `0.0` vs "no data" semantics — documentation-only |
| P4-LO-02 | 04-REVIEW.md#LO-02 | lib/analysis_merger.py:687-690 (now :752-764) | fix | TBD | Add field-level comment on `_merge_shot_boundary_source` explaining the "hybrid on disagreement" escalation rule — doc-only |
| P4-LO-03 | 04-REVIEW.md#LO-03 | lib/analysis_merger.py:710 (now :783) | fix | TBD | Log debug warning when `_cost_usd` missing + docstring note on merger API |
| P4-LO-04 | 04-REVIEW.md#LO-04 | lib/analysis_merger.py:442-452 (now :463-474) | fix | TBD | Inline comment explaining `tempo_seen` semantics ("None" means "no music", omit means "not inspected") |
| P4-LO-05 | 04-REVIEW.md#LO-05 | lib/chunked_analyzer.py:293-309 (now :299-315) | defer | NITS-DEF-P4-LO-05 | Orphan cost-tracker reservations on fail_fast with max_workers>1 — fix needs a new test harness (max_workers=3, chunk 0 raises, verify all three reconciles); behavior change to error handling path — defer |
| P4-LO-06 | 04-REVIEW.md#LO-06 | lib/video_chunker.py:140-150 | defer | NITS-DEF-P4-LO-06 | Zero-duration video guard. Review's own fix suggestion says "Add a `if duration <= 0.0: raise VideoChunkingError(...)` guard" AND acknowledges needing a regression test. New test = behavior change; defer |
| P4-NI-01 | 04-REVIEW.md#NI-01 | lib/video_chunker.py:55 | defer | NITS-DEF-P4-NI-01 | `Chunk.local_path: str` — review explicitly says "Not worth changing — string is simpler for the provider-tool contract. Nit because either choice is defensible." Defer per review disposition |
| P4-NI-02 | 04-REVIEW.md#NI-02 | lib/video_chunker.py:112, 144, 150, 171; lib/chunked_analyzer.py:178, 202 | fix | TBD | Extract `_MAX_CHUNK_SECONDS_DEFAULT = 300.0` module constant (matching `_WORKER_DEFAULT` pattern); tests use explicit arg values so defaults can be centralized without test drift |
| P4-NI-03 | 04-REVIEW.md#NI-03 | lib/analysis_merger.py:57 | fix | TBD | Drop unused `Callable` from typing import — linter will flag F401 |
| P4-NI-04 | 04-REVIEW.md#NI-04 | lib/chunked_analyzer.py:80 | fix | TBD | Remove misleading `# noqa: F401` — Chunk, cleanup_chunks, split_video are ALL actively used |
| P4-NI-05 | 04-REVIEW.md#NI-05 | lib/chunked_analyzer.py:95 | fix | TBD | Add module-level sanity assertion referencing `_PRICING_VERIFIED_AT` (verifies every pricing entry's `verified` field matches the module stamp) |
| P5-LR-01 | 05-REVIEW.md#LR-01 | lib/pipeline_synthesizer.py:243-249 (now :293-299) | fix | TBD | Wrap `json.dumps(artifact, ...)` in try/except TypeError → ValueError with friendlier message |
| P5-LR-02 | 05-REVIEW.md#LR-02 | lib/pipeline_synthesizer.py:310-315 (now :362-365) | fix | TBD | Add `logger.warning(...)` on pipeline-loader exceptions in `match_base_pipeline`; keep 0.0 score behavior |
| P5-LR-03 | 05-REVIEW.md#LR-03 | lib/pipeline_synthesizer.py:503-507 (now :553-557) | fix | TBD | Simplify outer env check; keep inner `fill_stage_details` as the single gate. Update docstring precedence wording |
| P5-LR-04 | 05-REVIEW.md#LR-04 | lib/llm_fill.py:195 | fix | TBD | Delete unreachable `return None` after the retry loop (the loop's final attempt already returns None on exception) |
| P5-LR-05 | 05-REVIEW.md#LR-05 | lib/pipeline_synthesizer.py:393-397 (now :443-447) | fix | TBD | Scope `_body_without_timestamp` strip to ISO-8601 `# at:` pattern via regex, not any line starting with `# at:` |
| P5-LR-06 | 05-REVIEW.md#LR-06 | tests/contracts/test_phase5_synthesis.py:269 | fix | TBD | Tighten assertion: `validation_status in ("valid", "invalid")` — remove "pending" per Pitfall 2 contract |
| P5-NR-01 | 05-REVIEW.md#NR-01 | lib/llm_fill.py:229 | fix | TBD | Document the FILLABLE_FIELDS truthy-check as a one-way-door design choice in module docstring |
| P5-NR-02 | 05-REVIEW.md#NR-02 | tests/unit/test_pipeline_synthesizer.py:1-16 | fix | TBD | Refresh module docstring test count (says "12 tests", file has 19) |
| P5-NR-03 | 05-REVIEW.md#NR-03 | lib/pipeline_synthesizer.py:620-641 (now :705-715) | already-resolved | commit 331be2d (Phase 10-02 CLEAN-09 refactor) | Current `accept_synthesis` calls `_relative_staging_path(dst)` not `_relative_staging_path(src)`. Phase 10 refactored to emit `promoted_path` from `dst`, eliminating the ordering concern |
| P5-NR-04 | 05-REVIEW.md#NR-04 | lib/pipeline_synthesizer.py:519-540 (now :569-607) | defer | NITS-DEF-P5-NR-04 | Round-trip validation via `load_pipeline(slug, defs_dir=STAGING_DIR)` — costs one extra disk-read + schema-validate per synthesis; behavior change; review marks this as "optional"; defer per 11-CONTEXT.md D-02 (no behavior changes) |

## Summary Counts

- **`fix`: 19 items** (each = one atomic commit in Task 2)
- **`already-resolved`: 2 items** (documented with grep / prior-commit evidence)
- **`defer`: 9 items** (added to REQUIREMENTS.md Future Requirements)
- **Total: 30** ✓ (matches catalogue)

## Deferred Items (appended to REQUIREMENTS.md Future Requirements)

### NITS-DEF-P3-LO-03

Defense-in-depth redaction of OpenRouter key patterns (`sk-or-v1-...`) in error strings via a new `_safe_exc_str` helper used at all `f"...: {exc}"` call sites in `openrouter_video_analyzer.py`. Requires a new unit test that mocks `APIError.__str__` to contain a fake `sk-or-v1-...` token and verifies redaction. Current SDK behavior is test-verified safe; defer adds a second gate without touching the already-green happy path.

### NITS-DEF-P3-LO-04

Markdown-fence stripping (`_strip_code_fence`) before `json.loads(content)` in `_run_once` to handle `anthropic/claude-*` routes on the prompt-embedded fallback. Review acknowledges the current MagicMock-based test does not exercise this path; landing the fix needs a new unit test with a realistic fenced response. Deferred as behavior-touching.

### NITS-DEF-P3-NI-01

Duplicated `_normalize_shot_boundaries` / `_format_shot_boundaries` helpers in `openrouter_video_analyzer.py` (byte-identical to the Gemini tool's versions). Extraction to `lib/` waits for a third provider — review disposition is "extract only when a third provider materializes."

### NITS-DEF-P3-NI-02

Shared-mutable class attribute `_FLAT_SCHEMA: dict | None = None` as a lazy cache. Switching to `functools.lru_cache` on `_flat_schema` would be safer in subclass scenarios, but review explicitly says "Not worth changing for this phase." Defer per review.

### NITS-DEF-P4-LO-05

`_analyze_chunks` fail_fast path only reconciles the failing chunk; in-flight futures on other chunks never get their `cost_tracker.reconcile(success=False)` call. Orphan reservations remain in the tracker. Fix needs a multi-worker regression test (max_workers=3, chunk 0 raises, verify all three reconciled). Deferred as behavior-change with new-test requirement.

### NITS-DEF-P4-LO-06

`split_video` bypass path does not validate `duration > 0.0` after ffprobe. Zero-duration (corrupt) videos are silently returned as a single bypass chunk. Fix needs a regression test that stubs ffprobe to return "0.0" and asserts `VideoChunkingError`. Deferred as new-test requirement.

### NITS-DEF-P4-NI-01

`Chunk.local_path: str` vs `pathlib.Path`. Review explicitly marks this as a nit with "either choice defensible" — defer per review's own disposition.

### NITS-DEF-P5-NR-04

Post-staging-write round-trip validation via `load_pipeline(slug, defs_dir=STAGING_DIR)` to catch ruamel-dump vs schema-shape divergence earlier. Adds one disk-read + one schema-validate per synthesis. Behavior change (new I/O) → defer per 11-CONTEXT.md D-02.

## Fix Plan Ordering (Task 2)

Commit batches will be grouped by file for merge friction minimization (still one-commit-per-fix). Planned order:

1. `tools/analysis/openrouter_video_analyzer.py`: P3-LO-01, P3-LO-02, P3-NI-05
2. `tests/unit/test_openrouter_video_analyzer.py`: P3-NI-04 (also P3-LO-01 companion delete in same commit-scope as the fix? No — separate commits per finding ID)
3. `lib/analysis_merger.py`: P4-LO-01, P4-LO-02, P4-LO-03, P4-LO-04, P4-NI-03
4. `lib/chunked_analyzer.py`: P4-NI-02 (shared with video_chunker), P4-NI-04, P4-NI-05
5. `lib/video_chunker.py`: (P4-NI-02 — already counted above)
6. `lib/pipeline_synthesizer.py`: P5-LR-01, P5-LR-02, P5-LR-03, P5-LR-05
7. `lib/llm_fill.py`: P5-LR-04, P5-NR-01
8. `tests/contracts/test_phase5_synthesis.py`: P5-LR-06
9. `tests/unit/test_pipeline_synthesizer.py`: P5-NR-02

Full-suite regression check points:
- After every 5 fixes
- After every same-file batch completes
- Final check at end of fix pass

## Commits (populated during Task 2)

| ID | SHA | Commit message |
|----|-----|-----------------|
| (classification-only, Task 1 boundary) | — | `docs(11-02): classify 30 LO/NI findings (19 fix / 2 already-resolved / 9 defer)` |
| (to be filled) | — | — |

## Full Suite Result (populated at plan end)

- Pre-fix baseline: **689 passed**, 3 failed (pre-existing fc-list), 13 skipped
- Final: TBD

## Commit Count Verification (populated at plan end)

- `grep -c "^| P[345]-.* fix " 11-02-SUMMARY.md` → 19
- `git log --oneline --grep='(11-nits)' | wc -l` → TBD (expected: 19 fix + 0 docs-scoped ≥ 19)
- `git log --oneline --grep='(11-02)' | wc -l` → TBD (expected: classification + defer-commit + finalize + each fix)
