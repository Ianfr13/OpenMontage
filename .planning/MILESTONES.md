# Milestones

## v2.1 Cleanup & Hardening (Shipped: 2026-04-18)

**Phases completed:** 5 phases, 8 plans, 13 tasks

**Key accomplishments:**

- Narrowed `_run_once` except chain so 401/403/429 raise sentinel subclasses that bypass the compact-retry ladder; four new tests prove exactly-one-create-call and preserved retry semantics for generic APIError.
- Lowered the inline-base64 ceiling from 2 GB to 100 MB, replaced silent `video/mp4` fail-open with an explicit extension whitelist, and deduplicated the OpenRouter base URL to a single constant reference — with 18 new test assertions locking the contract.
- Site 1 — `editing_pacing.pacing_style` (pre-edit L295 → post-edit raise at L298):
- Region 1: module constant (L130–134)
- InvalidPipelineSlug sentinel + two-gate slug validator (regex `^[a-z0-9][a-z0-9\-_]{7,127}$` + resolved-path check) wired into accept_synthesis and reject_synthesis, closing v2.0 Phase 5 REVIEW MR-01 latent path-traversal hole.
- Split `pipeline_synthesis` catch-all into dedicated `pipeline_acceptance` + `pipeline_rejection` schemas; accept_synthesis + reject_synthesis now emit honest contracts carrying only fields the event actually has — all 4 CLEAN-09 sentinel patterns (`match_score=0.0`, `base_pipeline=slug`, `"post-accept"`, `"post-reject"`) deleted from `lib/pipeline_synthesizer.py` and the Pitfall 2 `validation_status="invalid"` rejection-proxy hack removed.
- One-liner:
- Catalogue source:

---
