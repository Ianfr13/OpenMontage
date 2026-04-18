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
    - 30 LO/NI items with explicit disposition and commit SHA / evidence
    - atomic commits for each fix (18 landed)
    - REQUIREMENTS.md Future Requirements entries for deferred items (9)
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
    - tools/analysis/openrouter_video_analyzer.py
    - tests/unit/test_openrouter_video_analyzer.py
    - lib/analysis_merger.py
    - lib/chunked_analyzer.py
    - lib/video_chunker.py
    - lib/pipeline_synthesizer.py
    - lib/llm_fill.py
    - tests/contracts/test_phase5_synthesis.py
    - tests/unit/test_pipeline_synthesizer.py
    - .planning/REQUIREMENTS.md
decisions:
  - "NITS-01: deferred any fix that required a new test or observable behavior change"
  - "NITS-01: used (11-nits) scope on every absorb commit so git log --grep is a clean audit trail"
  - "P5-LR-03: fix attempt broke test_llm_fill_env_controlled; reverted and deferred as NITS-DEF-P5-LR-03"
metrics:
  duration_minutes: ~40
  tasks_completed: 2
  commits: 20
  tests_added: 0
  tests_total_after: 689
  completed_date: "2026-04-18"
---

# Phase 11-02: NITS-01 Absorption — Classification

**Catalogue source:** 03-REVIEW.md (9 items) + 04-REVIEW.md (11 items) + 05-REVIEW.md (10 items) = **30 items total**
**Classified:** 2026-04-18
**Executed:** 2026-04-18
**Target test baseline:** >=689 passing (inherited from Plan 11-01) — **preserved**

## One-liner

Absorbed 30 LOW/NIT findings from Phase 3/4/5 v2.0 code reviews as 19 narrow atomic commits (`(11-nits)` scope) + 9 explicit defers to REQUIREMENTS.md Future Requirements + 2 already-resolved by prior phases; full suite stays 689-passing.

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
| P3-LO-01 | 03-REVIEW.md#LO-01 | tools/analysis/openrouter_video_analyzer.py:76 | fix | `10e1dff` | Delete dead FALLBACK_MODEL constant + matching test-import (test never asserts it) |
| P3-LO-02 | 03-REVIEW.md#LO-02 | tools/analysis/openrouter_video_analyzer.py:512-516 | fix | `cec9fbe` | Add inline comment explaining asymmetric ladder (truncation-on-both stops; BadRequest falls through) |
| P3-LO-03 | 03-REVIEW.md#LO-03 | tools/analysis/openrouter_video_analyzer.py:412, 649 | defer | NITS-DEF-P3-LO-03 | Defense-in-depth key redaction needs a new unit test mocking APIError.__str__; current SDK is test-verified safe — defer per 11-CONTEXT.md D-02 (no new tests in absorb) |
| P3-LO-04 | 03-REVIEW.md#LO-04 | tools/analysis/openrouter_video_analyzer.py:309-321 | defer | NITS-DEF-P3-LO-04 | Markdown-fence stripping needs a new unit test with a fenced response; review acknowledges current mock does not exercise this. Behavior-change + new-test — defer |
| P3-NI-01 | 03-REVIEW.md#NI-01 | tools/analysis/openrouter_video_analyzer.py:141-172 | defer | NITS-DEF-P3-NI-01 | Duplicated `_normalize_shot_boundaries` / `_format_shot_boundaries` — review says "extract to lib/ only when a third provider materializes." Refactor out of absorb scope |
| P3-NI-02 | 03-REVIEW.md#NI-02 | tools/analysis/openrouter_video_analyzer.py:219 | defer | NITS-DEF-P3-NI-02 | `_FLAT_SCHEMA: dict \| None = None` shared-mutable class attribute. Review explicitly says "Not worth changing for this phase." Defer per review disposition |
| P3-NI-03 | 03-REVIEW.md#NI-03 | tools/analysis/openrouter_video_analyzer.py:74-76 | already-resolved | Phase 8 commit `2995862` (CLEAN-04) centralized OPENROUTER_BASE_URL; FALLBACK_MODEL deletion handled under P3-LO-01 (`10e1dff`). Evidence: `grep -n 'OPENROUTER_BASE_URL' tools/analysis/openrouter_video_analyzer.py` shows the constant used at line 614 (OpenAI ctor) | Phase 8 CLEAN-04 already centralized OPENROUTER_BASE_URL (commit 2995862); FALLBACK_MODEL removal handled by P3-LO-01 (`10e1dff`). Both items from NI-03 covered |
| P3-NI-04 | 03-REVIEW.md#NI-04 | tests/unit/test_openrouter_video_analyzer.py:529-541 | fix | `fe7cdbb` | Trim over-provisioned truncated responses from 6 → 4 (comment already says "up to 4") |
| P3-NI-05 | 03-REVIEW.md#NI-05 | tools/analysis/openrouter_video_analyzer.py:297-300 | fix | `25ea232` | Extract "30 words" magic number to `COMPACT_FIELD_WORD_LIMIT = 30` module constant |
| P4-LO-01 | 04-REVIEW.md#LO-01 | lib/analysis_merger.py:73-98 | fix | `bd07702` | Add docstring note on `_weighted_avg` explaining `0.0` vs "no data" semantics |
| P4-LO-02 | 04-REVIEW.md#LO-02 | lib/analysis_merger.py:752-776 | fix | `7d4b0eb` | Add field-level comment on `_merge_shot_boundary_source` documenting the "hybrid on disagreement" escalation |
| P4-LO-03 | 04-REVIEW.md#LO-03 | lib/analysis_merger.py:782-815 | fix | `c29baa5` | Log debug warning when `_cost_usd` missing + docstring note on merger API expectations |
| P4-LO-04 | 04-REVIEW.md#LO-04 | lib/analysis_merger.py:463-486 | fix | `9e1f06a` | Inline comment explaining `tempo_seen` three-way signal (weighted-avg / explicit-None / omit) |
| P4-LO-05 | 04-REVIEW.md#LO-05 | lib/chunked_analyzer.py:299-315 | defer | NITS-DEF-P4-LO-05 | Orphan cost-tracker reservations on fail_fast with max_workers>1 — fix needs multi-worker regression test + new error-path reconcile loop. Behavior change — defer |
| P4-LO-06 | 04-REVIEW.md#LO-06 | lib/video_chunker.py:140-150 | defer | NITS-DEF-P4-LO-06 | Zero-duration video guard needs a regression test stubbing ffprobe to "0.0" and asserting VideoChunkingError. New-test — defer |
| P4-NI-01 | 04-REVIEW.md#NI-01 | lib/video_chunker.py:55 | defer | NITS-DEF-P4-NI-01 | `Chunk.local_path: str` vs `Path` — review says "Not worth changing — either choice is defensible." Defer per review disposition |
| P4-NI-02 | 04-REVIEW.md#NI-02 | lib/video_chunker.py:62-66, 117; lib/chunked_analyzer.py:80-85, 183 | fix | `6b51640` | Extract `_MAX_CHUNK_SECONDS_DEFAULT = 300.0` module constant; import into chunked_analyzer and reference at both default-arg sites |
| P4-NI-03 | 04-REVIEW.md#NI-03 | lib/analysis_merger.py:57 | fix | `0560f3d` | Drop unused `Callable` from typing import (F401 source) |
| P4-NI-04 | 04-REVIEW.md#NI-04 | lib/chunked_analyzer.py:84 | fix | `206bcfb` | Remove misleading `# noqa: F401` — Chunk, cleanup_chunks, split_video are ALL actively used |
| P4-NI-05 | 04-REVIEW.md#NI-05 | lib/chunked_analyzer.py:95, 124-131 | fix | `7d6cefe` | Add module-level sanity assertion referencing `_PRICING_VERIFIED_AT` to keep per-entry `verified` stamps in sync |
| P5-LR-01 | 05-REVIEW.md#LR-01 | lib/pipeline_synthesizer.py:289-312 | fix | `5a64d14` | Wrap `json.dumps(artifact, ...)` in try/except TypeError → helpful ValueError |
| P5-LR-02 | 05-REVIEW.md#LR-02 | lib/pipeline_synthesizer.py:370-383 | fix | `10ead5d` | Add `logger.warning(...)` on pipeline-loader exceptions in `match_base_pipeline`; keep 0.0 score |
| P5-LR-03 | 05-REVIEW.md#LR-03 | lib/pipeline_synthesizer.py:564-575 + lib/llm_fill.py:271-273 | defer | NITS-DEF-P5-LR-03 | Attempted single-gate simplification in Task 2 — broke `test_llm_fill_env_controlled` which asserts the outer env check prevents the call. Reverted. Fix needs test-contract refactor first — behavior change — defer |
| P5-LR-04 | 05-REVIEW.md#LR-04 | lib/llm_fill.py:195-198 | fix | `c170ed1` | Annotate unreachable `return None` with `# pragma: no cover` + explanatory comment |
| P5-LR-05 | 05-REVIEW.md#LR-05 | lib/pipeline_synthesizer.py:456-475 | fix | `35d972f` | Scope `_body_without_timestamp` strip to ISO-8601 regex via `_AT_LINE_RE` |
| P5-LR-06 | 05-REVIEW.md#LR-06 | tests/contracts/test_phase5_synthesis.py:269-275 | fix | `0dab00f` | Tighten contract assertion: reject `"pending"` per Pitfall 2 |
| P5-NR-01 | 05-REVIEW.md#NR-01 | lib/llm_fill.py:69-85 | fix | `25d555e` | Document the FILLABLE_FIELDS truthy-check as a one-way-door design choice in module docstring |
| P5-NR-02 | 05-REVIEW.md#NR-02 | tests/unit/test_pipeline_synthesizer.py:1-28 | fix | `4171368` | Refresh module docstring test count from 12 → 19, list Plan 05-02 additions |
| P5-NR-03 | 05-REVIEW.md#NR-03 | lib/pipeline_synthesizer.py:705-715 | already-resolved | Phase 10-02 commit `331be2d` (refactor accept/reject to dedicated schemas). Evidence: current `accept_synthesis` calls `_relative_staging_path(dst)` NOT `_relative_staging_path(src)` — `grep -n '_relative_staging_path' lib/pipeline_synthesizer.py` shows only `(dst)` in accept path | Phase 10 CLEAN-09 refactor replaced the post-move `_relative_staging_path(src)` call with `_relative_staging_path(dst)`; ordering concern no longer applies |
| P5-NR-04 | 05-REVIEW.md#NR-04 | lib/pipeline_synthesizer.py:580-618 | defer | NITS-DEF-P5-NR-04 | Round-trip validation via `load_pipeline(slug, defs_dir=STAGING_DIR)` adds disk-read + schema-validate per synthesis. Behavior change — defer per 11-CONTEXT.md D-02 |

## Summary Counts

- **`fix`: 19 items** (each landed as one atomic `(11-nits)` commit)
- **`already-resolved`: 2 items** (P3-NI-03, P5-NR-03 — both documented with prior-phase commit SHAs)
- **`defer`: 9 items** (added to REQUIREMENTS.md Future Requirements under Code Hygiene)
- **Total: 30** ✓ (matches catalogue)

Note: plan classification expected 19 fix / 9 defer. Classification counts: 19 fix + 2 already-resolved + 9 defer = 30 ✓. During Task 2 a first attempt at P5-LR-03 (single-gate simplification) was made and immediately reverted when `test_llm_fill_env_controlled` failed (that test pins the outer-gate-prevents-call contract the review's proposed fix would remove). The revert restored the prior two-gate shape; no P5-LR-03 commit landed; P5-LR-03's final disposition stayed `defer` as Task 1 predicted. See "Deviations from Plan" below for the detailed revert log. Final count 19 fix / 9 defer.

## Deferred Items (appended to REQUIREMENTS.md Future Requirements)

See `.planning/REQUIREMENTS.md` → `Future Requirements` → `Code Hygiene (deferred from NITS-01)` for the full per-ID entry. Summary of NITS-DEF-* IDs added:

- `NITS-DEF-P3-LO-03` — safe_exc_str key redaction (new-test)
- `NITS-DEF-P3-LO-04` — markdown fence stripping (new-test)
- `NITS-DEF-P3-NI-01` — extract duplicated helpers to lib/ (refactor)
- `NITS-DEF-P3-NI-02` — `_FLAT_SCHEMA` → `functools.lru_cache` (review says defer)
- `NITS-DEF-P4-LO-05` — orphan cost reservations on fail_fast (behavior change)
- `NITS-DEF-P4-LO-06` — zero-duration video guard (new-test)
- `NITS-DEF-P4-NI-01` — `Chunk.local_path: str` → `Path` (review says defer)
- `NITS-DEF-P5-LR-03` — deduplicate VIDEO_SYNTH_LLM_FILL env check (needs test-contract refactor first)
- `NITS-DEF-P5-NR-04` — round-trip staging validation (behavior change)

## Commits

| # | ID | SHA | Commit message |
|---|-----|-----|-----------------|
| 1 | classification | `9a955cf` | `docs(11-02): classify 30 LO/NI findings (19 fix / 2 already-resolved / 9 defer)` |
| 2 | P3-LO-01 | `10e1dff` | `fix(11-nits): P3-LO-01 remove dead FALLBACK_MODEL constant` |
| 3 | P3-LO-02 | `cec9fbe` | `docs(11-nits): P3-LO-02 document asymmetric fallback ladder` |
| 4 | P3-NI-05 | `25ea232` | `refactor(11-nits): P3-NI-05 extract COMPACT_FIELD_WORD_LIMIT constant` |
| 5 | P3-NI-04 | `fe7cdbb` | `test(11-nits): P3-NI-04 trim retry-exhausted mock responses from 6 to 4` |
| 6 | P4-NI-03 | `0560f3d` | `refactor(11-nits): P4-NI-03 drop unused Callable import` |
| 7 | P4-NI-04 | `206bcfb` | `refactor(11-nits): P4-NI-04 drop misleading noqa F401 on video_chunker import` |
| 8 | P4-NI-05 | `7d6cefe` | `feat(11-nits): P4-NI-05 add _PRICING_VERIFIED_AT sanity assertion` |
| 9 | P4-NI-02 | `6b51640` | `refactor(11-nits): P4-NI-02 extract _MAX_CHUNK_SECONDS_DEFAULT constant` |
| 10 | P4-LO-01 | `bd07702` | `docs(11-nits): P4-LO-01 note _weighted_avg 0.0-vs-no-data semantics` |
| 11 | P4-LO-02 | `7d4b0eb` | `docs(11-nits): P4-LO-02 document _merge_shot_boundary_source hybrid escalation` |
| 12 | P4-LO-03 | `c29baa5` | `fix(11-nits): P4-LO-03 log debug when per-chunk _cost_usd missing` |
| 13 | P4-LO-04 | `9e1f06a` | `docs(11-nits): P4-LO-04 document tempo_seen three-way signal` |
| 14 | P5-LR-04 | `c170ed1` | `docs(11-nits): P5-LR-04 annotate unreachable return in _call_with_retry` |
| 15 | P5-NR-01 | `25d555e` | `docs(11-nits): P5-NR-01 document FILLABLE_FIELDS one-way-door` |
| 16 | P5-LR-01 | `5a64d14` | `fix(11-nits): P5-LR-01 wrap _canonical_sha256 json.dumps in friendlier TypeError` |
| 17 | P5-LR-02 | `10ead5d` | `fix(11-nits): P5-LR-02 log warning when matcher skips a malformed pipeline` |
| 18 | P5-LR-05 | `35d972f` | `fix(11-nits): P5-LR-05 scope _body_without_timestamp strip to ISO-8601 pattern` |
| 19 | P5-LR-06 | `0dab00f` | `test(11-nits): P5-LR-06 tighten contract assertion to reject 'pending'` |
| 20 | P5-NR-02 | `4171368` | `docs(11-nits): P5-NR-02 refresh test_pipeline_synthesizer docstring count` |
| 21 | defer | `302a622` | `docs(11-02): defer 9 LO/NI items to Future Requirements (NITS-01)` |
| 22 | finalize | TBD (this commit) | `docs(11-02): finalize 11-02-SUMMARY with commit SHAs` |

## Full Suite Result

- **Pre-fix baseline:** 689 passed, 3 failed (pre-existing fc-list), 13 skipped
- **Final:** 689 passed, 3 failed (pre-existing fc-list — unchanged), 13 skipped

```
$ TMPDIR=/workspace/.tmp/pytest pytest tests/ --ignore=tests/qa -q
3 failed, 689 passed, 13 skipped in 54.05s
```

The 3 failing tests are the pre-existing `tests/contracts/test_phase2_contracts.py::TestCodeSnippetUnit::test_render_*` fc-list / fontconfig failures documented in STATE.md — not touched by this plan. Zero new failures introduced.

## Commit Count Verification

- `grep -cE "^\| P[345]-[A-Z]{2}-[0-9]{2} .* \| fix \| " 11-02-SUMMARY.md` → 19
- `git log --oneline --grep='(11-nits)' | wc -l` → 19 (one per fix) ✓
- `git log --oneline --grep='(11-02)' | wc -l` → 3 (classification + defer + finalize)
- Total `(11-nits)` or `(11-02)` commits in this plan: 22 (19 fix + classification + defer + finalize)

No monolithic commit — every fix has its own atomic commit with the ID in the message.

## Deviations from Plan

### P5-LR-03 reclassified fix → defer during Task 2

**Found during:** Task 2 execution
**Issue:** The plan's classification expected P5-LR-03 (dedup VIDEO_SYNTH_LLM_FILL env check) to be a narrow fix. On implementation, removing the outer env check in `synthesize_pipeline` broke `tests/unit/test_accept_reject.py::test_llm_fill_env_controlled`, which asserts that env=false prevents the LLM-fill function from being CALLED at all (not just that it returns the base manifest). My change made the outer gate a no-op and relied on the inner gate to return base, but the test mocks the inner function and counts invocations.
**Fix:** Reverted the source change; kept both env checks in place; reclassified P5-LR-03 as `defer` with rationale recorded in REQUIREMENTS.md. The fix needs a test-contract change first (either accept inner-gate behavior or drop the outer-gate counting assertion) before the source can land.
**Files affected:** `lib/pipeline_synthesizer.py` (reverted to original two-gate shape)
**Commit:** N/A (revert; P5-LR-03 has no fix commit, the REQUIREMENTS.md defer entry is its disposition)

## Threat Flags

None. Every fix is internal hygiene — no new network endpoints, auth paths, or schema changes at trust boundaries. The threat register in 11-02-PLAN.md enumerates only T-11-02-01..04 which are all `mitigate` dispositions against this plan's own execution risk, not new surface introduced by the plan.

## Self-Check: PASSED

Artifact verification:

- ✓ `.planning/phases/11-drift-hygiene/11-02-SUMMARY.md` exists (this file)
- ✓ `.planning/REQUIREMENTS.md` contains `Code Hygiene (deferred from NITS-01)` section with 9 `NITS-DEF-*` entries matching the defer rows
- ✓ Every `fix` row has a 7-char SHA that `git log --oneline` locates
- ✓ Every `already-resolved` row cites a prior-phase commit SHA + grep evidence
- ✓ Every `defer` row has a `NITS-DEF-*` ID that resolves to a REQUIREMENTS.md line
- ✓ `git log --oneline --grep='(11-nits)'` returns 19 commits (one per fix) — no monolithic absorb
- ✓ `pytest tests/ --ignore=tests/qa -q` → 689 passed, 3 pre-existing fc-list failures, 13 skipped

Commit count check (SHAs verified against `git log --oneline`):
- `10e1dff` ✓, `cec9fbe` ✓, `25ea232` ✓, `fe7cdbb` ✓, `0560f3d` ✓, `206bcfb` ✓, `7d6cefe` ✓, `6b51640` ✓, `bd07702` ✓, `7d4b0eb` ✓, `c29baa5` ✓, `9e1f06a` ✓, `c170ed1` ✓, `25d555e` ✓, `5a64d14` ✓, `10ead5d` ✓, `35d972f` ✓, `0dab00f` ✓, `4171368` ✓, `302a622` ✓, `9a955cf` ✓
