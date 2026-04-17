---
phase: 5
slug: synthesizer
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-17
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (no pytest.ini / pyproject.toml — default discovery) |
| **Config file** | none |
| **Quick run command** | `pytest tests/unit/test_pipeline_synthesizer.py -x --tb=short -q` |
| **Full suite command** | `pytest tests/unit tests/contracts -x --tb=short -q` |
| **Estimated runtime** | ~5–8 seconds (unit), ~15 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run the task's `<automated>` verify command (each < 5s).
- **After every plan wave:** Run `pytest tests/unit tests/contracts -x -q -k "phase5 or synthesis or llm_fill or accept_reject or pipeline_synthesizer or semantic_validation or pipeline"`
- **Before `/gsd-verify-work`:** `pytest tests/unit tests/contracts --tb=short` fully green, including backward-compat gate (all 12 existing pipelines still load).
- **Max feedback latency:** 5 seconds per task verify.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | SYNTH-05 (staging infra) | T-05-01, T-05-02 | Schema extension additive; _staging gitignored; no write outside staging | contract | `python -c "import ruamel.yaml; json.load(open('schemas/pipelines/pipeline_manifest.schema.json'))['properties']['expected_analysis']" && pytest tests/contracts -x -q -k "pipeline or manifest"` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 1 | SYNTH-01, SYNTH-02, SYNTH-04, SYNTH-05, SYNTH-06 | T-05-01, T-05-02, T-05-04, T-05-06 | Matcher bounded [0,1]; staging-only writes; deterministic slug; no class defs; no LLM | unit | `pytest tests/unit/test_pipeline_synthesizer.py -x -q` | ❌ W0 | ⬜ pending |
| 5-01-03 | 01 | 1 | SYNTH-02 (enabler) | T-05-07 | Annotated pipelines load under extended schema; no backward-compat regression | contract | `pytest tests/contracts -x -q -k "pipeline or manifest" && pytest tests/unit/test_pipeline_synthesizer.py -x -q` | ❌ W0 | ⬜ pending |
| 5-02-01 | 02 | 2 | SYNTH-07, SYNTH-08 | T-05-09, T-05-10, T-05-13 | Semantic validator catches missing skill / unknown tool; loader filter future-proof | unit | `pytest tests/unit/test_semantic_validation.py -x -q` | ❌ W0 | ⬜ pending |
| 5-02-02 | 02 | 2 | SYNTH-08 (record) + SYNTH-09 (honor schema) | T-05-11, T-05-12 | Record validates against pipeline_synthesis schema; enum `valid/invalid/pending` honored; no auto-approval function exists | contract | `pytest tests/contracts/test_phase5_synthesis.py -x -q && pytest tests/unit/test_pipeline_synthesizer.py -x -q` | ❌ W0 | ⬜ pending |
| 5-03-01 | 03 | 3 | SYNTH-03, SYNTH-04 | T-05-14, T-05-15, T-05-17, T-05-18 | LLM fill never raises; bounded 2000 tokens; post-merge validation reverts on injection; no secret logged | unit | `pytest tests/unit/test_llm_fill.py -x -q` | ❌ W0 | ⬜ pending |
| 5-03-02 | 03 | 3 | SYNTH-10, SYNTH-03 (wiring) | T-05-16, T-05-19, T-05-20 | accept/reject are separate functions; records schema-valid; LLM wired with opt-out; order-aware grep guard | contract + unit | `pytest tests/unit/test_accept_reject.py tests/contracts/test_phase5_synthesis.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pip install 'ruamel.yaml>=0.18,<0.20'` — dep missing from venv (Plan 05-01 Task 1)
- [ ] `requirements.txt` — add `ruamel.yaml>=0.18,<0.20` line (Plan 05-01 Task 1)
- [ ] `.gitignore` — add `pipeline_defs/_staging/` entry (Plan 05-01 Task 1)
- [ ] `schemas/pipelines/pipeline_manifest.schema.json` — add optional `expected_analysis` property (Plan 05-01 Task 1)
- [ ] `tests/unit/test_pipeline_synthesizer.py` — NEW file (Plan 05-01 Task 2)
- [ ] `tests/unit/test_semantic_validation.py` — NEW file (Plan 05-02 Task 1)
- [ ] `tests/unit/test_llm_fill.py` — NEW file (Plan 05-03 Task 1)
- [ ] `tests/unit/test_accept_reject.py` — NEW file (Plan 05-03 Task 2)
- [ ] `tests/contracts/test_phase5_synthesis.py` — NEW file (Plan 05-02 Task 2, extended in 05-03 Task 2)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real OpenRouter call with a real `video_analysis` artifact produces a sensible `tools_available` fill | SYNTH-03 | Requires live OPENROUTER_API_KEY + a real analysis artifact; cost ~$0.01 per call; automatable but gated behind `RUN_INTEGRATION_TESTS=1` in Phase 7 | 1. Set `OPENROUTER_API_KEY` in env. 2. Run `python -c "from lib.pipeline_synthesizer import synthesize_pipeline; import json; a=json.load(open('tests/fixtures/video_analysis_sample.json')); r=synthesize_pipeline(a, use_llm_fill=True, mode='replica'); print(r['match_score'], r['staging_path'])"` 3. Open the staging YAML; confirm `tools_available` fields look reasonable for the matched base. 4. This is Phase 7 TEST-02 territory; NOT a Phase 5 blocker. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (each of the 7 tasks has an automated command)
- [x] Wave 0 covers all MISSING references (ruamel install, 5 new test files, schema extension)
- [x] No watch-mode flags
- [x] Feedback latency < 5s per task
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-17
