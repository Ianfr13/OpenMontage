# Phase 9: Chunked Merge Correctness - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning
**Mode:** Auto-generated (cleanup phase — specs are literal v2.0 review findings with file:line references)

<domain>
## Phase Boundary

Harden `lib/chunked_analyzer.py` and `lib/analysis_merger.py` so merged artifacts pass canonical `video_analysis` schema validation without hardcoded fallback defaults, provider name is validated before merge, and the `on_chunk_error="continue"` path respects positional rules for hook (lowest-index) and CTA (highest-index).

Out of boundary: `openrouter_video_analyzer.py` (Phase 8, done), synthesizer (Phase 10), drift/NITs (Phase 11), UAT (Phase 12).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion (per REQUIREMENTS.md spec)

Three REQs for this phase (CLEAN-05, CLEAN-06, CLEAN-07) carry exact file:line refs from the v2.0 Phase 4 REVIEW.md findings. No grey areas worth pausing for.

Narrow defaults:

- **CLEAN-05 (provider validation)**: In `lib/chunked_analyzer.py`, before populating `chunking_metadata.provider` (~lines 418, 469), validate the `provider_tool.provider` string against `{"gemini","openrouter"}`. Raise `VideoAnalysisError` or equivalent on mismatch — do NOT silently fall back. The validation must happen ONCE at the start of each chunk cycle, not per-populate.
- **CLEAN-06 (remove merger fallbacks)**: In `lib/analysis_merger.py` at the exact lines listed (295, 394, 400, 538, 551, 602, 637, 655), the pattern `vote or dims[0].get(field, DEFAULT)` must be replaced. Approach: if consensus yields nothing, raise a `MergeConsensusError` (new) subclass of the existing error family — do NOT pick an arbitrary default. The single-validation-gate is the canonical boundary; the merger is not allowed to invent values that weren't in any chunk.
- **CLEAN-07 (positional hook/CTA)**: In `chunked_analyzer.py` around lines 454-462, when `on_chunk_error="continue"` drops chunks, the current code silently reindexes and loses positional meaning. Fix: pass the full `(chunk, art_or_None)` list to the merger so it can pick `hook = first successful chunk by start_time` and `cta = last successful chunk by start_time`. Chunks with `art is None` are skipped for hook/CTA but still counted in the position order.

### Backward compat

Non-negotiable: `pytest tests/ --ignore=tests/qa -q` must stay at ≥643 passing (current baseline after Phase 8). Where existing tests pin the old behavior (e.g. assume default-fallback `"unknown"` is returned), update them to match the new contract (assert the raise or assert the correct consensus path).

### New error types

If CLEAN-06 introduces `MergeConsensusError`, add it to `lib/analysis_errors.py` (already extended by Phase 8 for auth/rate sentinels). Subclass `VideoAnalysisError`. Keep it exported.

</decisions>

<code_context>
## Existing Code Insights

### Relevant files
- `lib/chunked_analyzer.py` — CLEAN-05 + CLEAN-07
- `lib/analysis_merger.py` — CLEAN-06
- `lib/analysis_errors.py` — new sentinel if needed
- `schemas/artifacts/video_analysis.schema.json` — canonical contract the merger output must validate against
- `tests/unit/test_chunked_analyzer.py`, `tests/unit/test_analysis_merger.py`, `tests/contracts/test_phase4_contracts.py` (or similar) — current baseline

### Patterns already in the repo
- Phase 8 established the `VideoAnalysisError` sentinel subclass pattern in `lib/analysis_errors.py`. Reuse it.
- Existing merger tests likely parametrize `target_platform` values — those may need updates if the `"unknown"` fallback was the pinned default.

### Anchor reviews
- v2.0 Phase 4 REVIEW: `.planning/milestones/v2.0-phases/04-chunking/04-REVIEW.md` — MR-01, MR-02, MR-03.

</code_context>

<specifics>
## Specific Ideas

- User's feedback memory (feedback_validate_api_patterns): before editing merger consensus logic, read the actual schema (`schemas/artifacts/video_analysis.schema.json`) to confirm which fields are required and which enums are valid. Do NOT chute the enum list.
- STATE.md Accumulated Context notes:
  - `analysis_merger violates single-validation-gate with hardcoded fallback defaults` — this is exactly CLEAN-06
  - `Pitfall 7: selector ships in Phase 2 alongside first provider` — not directly relevant but confirms v2.0 architecture

</specifics>

<deferred>
## Deferred Ideas

- Cross-chunk cost tracking (`cost_tracker` group_id correlation) — this is OBS-01, deferred to Future Requirements, not Phase 9.
- Synthesizer-side schema validation — that's Phase 10 (CLEAN-08/09).
- LOW/NIT items from 04-REVIEW.md — absorb into Phase 11 (NITS-01), not Phase 9.

</deferred>
