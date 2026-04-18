# Requirements: OpenMontage v2.1 Cleanup & Hardening

**Defined:** 2026-04-17
**Core Value:** Agente instruction-driven que entrega vídeo end-to-end sem vazar decisões criativas para Python.

**Scope:** Absorver tech debt diferido do v2.0 — fixes HIGH/MEDIUM do code review, drift pré-existente em `cinematic.yaml`, LOW/NIT hygiene, e gates human-UAT. Sem feature nova.

## v2.1 Requirements

### Error Surfacing

- [ ] **CLEAN-01**: `openrouter_video_analyzer._run_once` must surface `AuthenticationError` (401), `PermissionDeniedError` (403), and `RateLimitError` (429) immediately without triggering `_analyze_with_fallback` compact-retry. (Phase 3 HI-01 — `tools/analysis/openrouter_video_analyzer.py:355-359, 439-457`)

### Safety & Bounds

- [ ] **CLEAN-02**: `openrouter_video_analyzer._build_data_url` cap must be lowered from 2GB to ~100MB (above that, chunking is the intended path). (Phase 3 MD-01 — `openrouter_video_analyzer.py:146-154`)
- [ ] **CLEAN-03**: `openrouter_video_analyzer._guess_mime` must use an explicit MIME whitelist and fall through to `None` for unknown extensions (no `video/mp4` fail-open default). (Phase 3 MD-02 — `openrouter_video_analyzer.py:106-109`)
- [ ] **CLEAN-08**: `pipeline_synthesizer.accept_synthesis(slug)` and `reject_synthesis(slug)` must validate slug format (regex) and resolve the target path under the expected staging root (defense-in-depth against path traversal). (Phase 5 MR-01 — `lib/pipeline_synthesizer.py:606, 670`)

### Config Dedup

- [ ] **CLEAN-04**: `OPENROUTER_BASE_URL` constant must be the single source of truth; remove hardcoded literal at the call site and update the test that currently asserts both. (Phase 3 MD-03)

### Chunked Merge Correctness

- [ ] **CLEAN-05**: `chunked_analyzer` must validate `provider_tool.provider` against `{"gemini","openrouter"}` before populating `chunking_metadata.provider` so schema validation does not fail at merge time. (Phase 4 MR-01 — `lib/chunked_analyzer.py:418, 469`)
- [ ] **CLEAN-06**: `analysis_merger` must not apply hardcoded default fallbacks on required fields (e.g., `target_platform` falling back to `"unknown"` which is out of enum). Violations of the single-validation-gate must be removed. (Phase 4 MR-02 — `lib/analysis_merger.py:295, 394, 400, 538, 551, 602, 637, 655`)
- [ ] **CLEAN-07**: `chunked_analyzer` with `on_chunk_error="continue"` must honor position when picking hook (lowest-index successful chunk) and CTA (highest-index successful chunk), not silently violate the positional rule. (Phase 4 MR-03 — `chunked_analyzer.py:454-462`)

### Synthesis Record Validity

- [ ] **CLEAN-09**: `accept_synthesis` / `reject_synthesis` must stop emitting synthetic run records with `base_pipeline=slug`, `match_score=0.0`, `source_analysis_checksum="post-accept"`. Either split into `pipeline_acceptance` / `pipeline_rejection` schemas or tighten the existing schema with a sentinel allow-list. (Phase 5 MR-02 — `pipeline_synthesizer.py:636-648, 677-690`)

### Pre-existing Drift

- [ ] **DRIFT-01**: `pipeline_defs/cinematic.yaml` references unregistered `web_search` tool; either register the tool or remove the reference so the semantic validator stops flagging it. (deferred from Phase 5 in `.planning/milestones/v2.0-phases/05-synthesizer/deferred-items.md`)

### Code Hygiene

- [ ] **NITS-01**: Absorb the 16 LOW + 14 NIT findings from Phase 3, 4, 5 REVIEW.md — including dead constants, redundant env checks, unreachable returns, missing logging on silent failures, prompt-embedded markdown fences, and `_PRICING_VERIFIED_AT` redundancy. Each fix must be a narrow atomic commit; preserve all 588 existing tests green. (Full list: `.planning/milestones/v2.0-phases/{03-openrouter-provider,04-chunking,05-synthesizer}/*-REVIEW.md`)

### Human UAT Gates

- [ ] **UAT-01**: Run SKILL-03 Gemini real-video quality review with a user-provided fixture video + `GEMINI_API_KEY`, following instructions in `.planning/milestones/v2.0-phases/02-gemini-provider/02-HUMAN-UAT.md`. Record verdict in a dated report.
- [ ] **UAT-02**: Run SKILL-03 OpenRouter real-video quality review with a user-provided fixture video + `OPENROUTER_API_KEY`, following instructions in `.planning/milestones/v2.0-phases/03-openrouter-provider/03-HUMAN-UAT.md`. Record verdict in a dated report.

## Future Requirements

Deferred beyond v2.1 — tracked but not in this milestone's roadmap.

### Synthesizer Quality (SYNTH2-*)

- **SYNTH2-01**: LLM-scored match confidence (supplement rule-based matching with a confidence score)
- **SYNTH2-02**: Interactive diff UI for staging approval
- **SYNTH2-03**: Auto-regenerate refactor path

### Observability (OBS-*)

- **OBS-01**: Cross-chunk cost tracking (group_id correlation in `cost_tracker`)
- **OBS-02**: Analysis cache keyed by input checksum (avoid paying twice for the same video)

### Infrastructure

- **INFRA-01**: Python 3.10 in devcontainer (host has 3.9.6 — see TODO.md)
- **INFRA-02**: FFmpeg on host (TODO.md)
- **INFRA-03**: Sync 11 GSAP / grok-media skills to `.claude/skills/` (TODO.md)
- **INFRA-04**: Populate `docs/stage-gates/` (TODO.md)
- **INFRA-05**: README inflated skill-count claim (TODO.md)
- **INFRA-06**: E2E with real Remotion render (TODO.md)

## Out of Scope

| Feature | Reason |
|---------|--------|
| New providers (Claude video, local/offline analyzer) | Cleanup milestone — no feature work. Also: Claude video input doesn't exist yet. |
| Synthesizer quality improvements (SYNTH2-*) | Separate milestone; not part of cleanup scope |
| Observability (OBS-*) | Separate milestone; not part of cleanup scope |
| Schema / API changes beyond what HI-01, MR-01, MR-02 fixes require | Would break backward compat (588 v2.0 tests); scope creep |
| Refactors beyond the review findings | Narrow fixes only — each must be atomic and test-preserving |

## Traceability

Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLEAN-01 | — | Pending |
| CLEAN-02 | — | Pending |
| CLEAN-03 | — | Pending |
| CLEAN-04 | — | Pending |
| CLEAN-05 | — | Pending |
| CLEAN-06 | — | Pending |
| CLEAN-07 | — | Pending |
| CLEAN-08 | — | Pending |
| CLEAN-09 | — | Pending |
| DRIFT-01 | — | Pending |
| NITS-01 | — | Pending |
| UAT-01 | — | Pending |
| UAT-02 | — | Pending |

**Coverage:**
- v2.1 requirements: 13 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 13 ⚠️

---
*Requirements defined: 2026-04-17*
*Last updated: 2026-04-17 after initial v2.1 scoping*
