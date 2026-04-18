# Roadmap: OpenMontage

## Milestones

- ✅ **v2.0 Reference Synthesis** — Phases 1-7 (shipped 2026-04-17) · 23 plans · 588 tests · [Archive](milestones/v2.0-ROADMAP.md)
- 🚧 **v2.1 Cleanup & Hardening** — Phases 8-12 (in progress)

## Shipped Milestones

- ✅ **v2.0 Reference Synthesis** — Shipped 2026-04-17 · 7 phases · 23 plans · 588 tests · [Archive](milestones/v2.0-ROADMAP.md)

## Current Milestone

### 🚧 v2.1 Cleanup & Hardening (In Progress)

**Milestone Goal:** Absorver tech debt diferido do v2.0 — 1 HIGH + 8 MEDIUM code-review fixes, `cinematic.yaml` drift, 30 LOW/NIT hygiene, e gates human-UAT — sem adicionar feature nova. 588 v2.0 tests devem continuar verdes em cada phase.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)
- Phase numbers never reset between milestones — v2.1 continues from Phase 8

- [ ] **Phase 8: OpenRouter Provider Hardening** — Fix auth error surfacing, tighten size cap, MIME whitelist, dedupe base URL constant in `tools/analysis/openrouter_video_analyzer.py`
- [ ] **Phase 9: Chunked Merge Correctness** — Validate provider enum, remove silent fallback defaults, honor hook/CTA positional rule in `lib/chunked_analyzer.py` + `lib/analysis_merger.py`
- [ ] **Phase 10: Synthesizer Record Validity** — Harden slug/path validation and stop emitting synthetic run records in `lib/pipeline_synthesizer.py`
- [ ] **Phase 11: Drift & Hygiene** — Resolve `cinematic.yaml` `web_search` drift and absorb 30 LOW/NIT code-review findings across Phases 3, 4, 5
- [ ] **Phase 12: Human UAT** — Run SKILL-03 real-video quality review for Gemini and OpenRouter providers (manual gate, requires fixture + API keys)

## Phase Details

### Phase 8: OpenRouter Provider Hardening
**Goal**: Harden the OpenRouter video analyzer so auth/rate errors fail fast, payload sizing matches the chunking contract, MIME detection is explicit, and config is deduplicated.
**Depends on**: Nothing (first v2.1 phase; builds on shipped v2.0)
**Requirements**: CLEAN-01, CLEAN-02, CLEAN-03, CLEAN-04
**Success Criteria** (what must be TRUE):
  1. A test asserts `_run_once` re-raises `AuthenticationError`, `PermissionDeniedError`, and `RateLimitError` without calling `_analyze_with_fallback` (no compact retry on 401/403/429)
  2. `_build_data_url` raises on payloads above the lowered ~100MB cap; a test covers both the allow-path and the reject-path above the new cap
  3. `_guess_mime` returns `None` for any extension outside the explicit whitelist; a unit test parametrizes `.mp4/.mov/.webm/.mkv/.m4v` (allowed — per CONTEXT.md locked whitelist) vs `.exe/.txt/.bin/.pdf/.avi` (rejected)
  4. `grep -n '"https://openrouter.ai/api/v1"' tools/analysis/openrouter_video_analyzer.py` returns exactly one match (the `OPENROUTER_BASE_URL` constant definition); no call-site literals remain
  5. Full suite stays green: `pytest tests/ --ignore=tests/qa -q` reports at least the 621 pre-Phase-8 baseline passing + new Phase-8 tests, with 13 skipped and 3 pre-existing fc-list failures unchanged (the fc-list failures are pre-existing and documented in STATE.md)
**Plans:** 2 plans
Plans:
- [x] 08-01-PLAN.md — CLEAN-01: sentinel exception classes + narrow except for 401/403/429 + 4 unit tests proving fast-fail
- [x] 08-02-PLAN.md — CLEAN-02/03/04: 100MB cap + explicit MIME whitelist + OPENROUTER_BASE_URL dedup + corresponding tests

### Phase 9: Chunked Merge Correctness
**Goal**: Make the chunked analyzer + merger produce artifacts that pass canonical schema validation without hardcoded fallback cheats and with positional hook/CTA rules honored.
**Depends on**: Phase 8
**Requirements**: CLEAN-05, CLEAN-06, CLEAN-07
**Success Criteria** (what must be TRUE):
  1. `chunked_analyzer` rejects any `provider_tool.provider` outside `{"gemini","openrouter"}` before writing `chunking_metadata.provider`; a contract test feeds an invalid provider and asserts a clear error (not a downstream schema failure)
  2. `grep -n '"unknown"\|or "unknown"\|\.get(.*, *"unknown")' lib/analysis_merger.py` returns zero matches on required-field code paths; merger surfaces missing values instead of silently defaulting them
  3. With `on_chunk_error="continue"` and a mix of successful/failed chunks, the merged artifact's hook comes from the lowest-index successful chunk and CTA from the highest-index — verified by a parametrized test fixture
  4. `validate_artifact("video_analysis", merged)` passes on every merger output path covered by `tests/test_analysis_merger.py` and `tests/test_chunked_analyzer.py`, with no test relying on the removed fallback defaults
  5. Full suite stays green: `pytest tests/ -q` reports 588+ passing tests after this phase
**Plans:** 2 plans
Plans:
- [x] 09-01-PLAN.md — CLEAN-06: MergeConsensusError sentinel + remove 8 hardcoded fallback defaults in analysis_merger
- [x] 09-02-PLAN.md — CLEAN-05 + CLEAN-07: provider enum validation + position-preserving hook/CTA in continue mode

### Phase 10: Synthesizer Record Validity
**Goal**: Harden synthesizer acceptance/rejection so slug/path inputs are validated defensively and the emitted records no longer abuse `pipeline_synthesis_run` with synthetic sentinel values.
**Depends on**: Phase 9
**Requirements**: CLEAN-08, CLEAN-09
**Success Criteria** (what must be TRUE):
  1. `accept_synthesis` / `reject_synthesis` raise on malformed slugs (regex-rejected) and on target paths that resolve outside the staging root; a parametrized test covers traversal payloads (`../`, absolute paths, empty string, invalid chars)
  2. `grep -n 'match_score=0\.0\|base_pipeline=slug\|"post-accept"' lib/pipeline_synthesizer.py` returns zero matches — synthetic sentinel records are gone
  3. Acceptance/rejection records validate against their schemas (either new split `pipeline_acceptance` / `pipeline_rejection` schemas or the existing schema tightened with a sentinel allow-list — decision recorded in the phase plan)
  4. End-to-end synthesis flow test (`test_phase7_e2e_smoke.py::test_e2e_synthesis_flow_mocked`) still passes with the new record shape; reject path cleanup test still passes
  5. Full suite stays green: `pytest tests/ -q` reports 588+ passing tests after this phase
**Plans:** 2 plans
Plans:
- [ ] 10-01-PLAN.md — CLEAN-08: InvalidPipelineSlug sentinel + slug regex/resolved-path guard on accept_synthesis and reject_synthesis + parametrized traversal tests
- [ ] 10-02-PLAN.md — CLEAN-09: schema split (pipeline_acceptance + pipeline_rejection) + delete sentinel record fields + update pinning tests

### Phase 11: Drift & Hygiene
**Goal**: Clear the last pre-existing pipeline drift and absorb the 30 deferred LOW/NIT code-review findings from Phases 3, 4, 5 as narrow atomic commits.
**Depends on**: Phase 10
**Requirements**: DRIFT-01, NITS-01
**Success Criteria** (what must be TRUE):
  1. `pipeline_defs/cinematic.yaml` no longer references `web_search` (either the tool is registered and discoverable via `tool_registry`, or the reference is removed); the semantic validator stops flagging it
  2. All 16 LOW + 14 NIT items from `.planning/milestones/v2.0-phases/{03-openrouter-provider,04-chunking,05-synthesizer}/*-REVIEW.md` are either fixed (with a referenced commit) or explicitly deferred with rationale in a phase deferral record — zero items left unresolved
  3. `git log --oneline v2.0..HEAD -- lib/ tools/` shows commits that are narrow and atomic (one concern per commit, as required by NITS-01), not a monolithic absorb commit
  4. Full suite stays green: `pytest tests/ -q` reports 588+ passing tests after the absorption
**Plans**: TBD

### Phase 12: Human UAT
**Goal**: Close the by-design manual quality gate on both video analyzer providers with a user-provided fixture video and real API keys, recording a dated verdict per provider.
**Depends on**: Phases 8, 9, 10, 11 (all code paths must be hardened before UAT — otherwise the fixture review is invalid)
**Requirements**: UAT-01, UAT-02
**Success Criteria** (what must be TRUE):
  1. A dated report lives at `.planning/phases/12-human-uat/UAT-01-gemini-<date>.md` following `.planning/milestones/v2.0-phases/02-gemini-provider/02-HUMAN-UAT.md` instructions, with verdict (pass/fail) and per-field evidence
  2. A dated report lives at `.planning/phases/12-human-uat/UAT-02-openrouter-<date>.md` following `.planning/milestones/v2.0-phases/03-openrouter-provider/03-HUMAN-UAT.md` instructions, with verdict (pass/fail) and per-field evidence
  3. Each report records fixture video metadata (duration, codec, resolution), model + provider used, and a diff between expected and observed structured analysis output
  4. If either UAT fails, the failure is logged in PROJECT.md Key Decisions and a follow-up requirement is opened; no silent pass-through
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 8 → 9 → 10 → 11 → 12

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 8. OpenRouter Provider Hardening | v2.1 | 2/2 | Shipped | 2026-04-18 |
| 9. Chunked Merge Correctness | v2.1 | 0/2 | Not started | - |
| 10. Synthesizer Record Validity | v2.1 | 0/2 | Not started | - |
| 11. Drift & Hygiene | v2.1 | 0/TBD | Not started | - |
| 12. Human UAT | v2.1 | 0/TBD | Not started | - |

---

*Last updated: 2026-04-18 — Phase 10 plans created (CLEAN-08/09)*
