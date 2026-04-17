---
phase: 2
slug: gemini-provider
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-17
last_updated: 2026-04-17
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ≥ 7 (already in use by Phase 1) |
| **Config file** | None at repo root — `tests/` uses default pytest discovery. `tests/unit/conftest.py` lands in Wave-0 (plan 02-04 Task 1) with shared fixtures |
| **Quick run command** | `pytest tests/unit/test_gemini_video_analyzer.py tests/contracts/test_phase2_contracts.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | <5 seconds (quick) / <30 seconds (full) — all mocked; `time.sleep` patched to no-op |

---

## Sampling Rate

- **After every task commit:** Run the **quick run command** above
- **After every plan wave:** Run the **full suite command** above
- **Before `/gsd-verify-work`:** Full suite must be green AND SKILL-03 manual gate signed off
- **Max feedback latency:** < 2 seconds (quick run is <5s end-to-end)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 1 | ANLZ-01 | T-02-01 | Error messages never contain API key value | smoke | `python3 -c "from lib.analysis_errors import VideoAnalysisError, VideoUploadError, VideoAnalysisRetryExhausted; assert issubclass(VideoUploadError, VideoAnalysisError) and issubclass(VideoAnalysisRetryExhausted, VideoAnalysisError); print('ok')"` | ❌ W0 (plan 02-01) | ⬜ pending |
| 2-01-02 | 01 | 1 | ANLZ-01 | T-02-02 | Selector registers + zero-provider path clean | smoke | `python3 -c "from tools.tool_registry import registry; registry.discover(); assert 'video_analyzer_selector' in [t.name for t in registry.get_by_capability('video_analysis')]"` | ❌ W0 (plan 02-01) | ⬜ pending |
| 2-02-01 | 02 | 2 | GEM-01..05 | — | google-genai pinned and importable | smoke | `grep -E "^google-genai>=1\\.73" requirements.txt && python3 -c "from google import genai; print(genai.__version__)"` | ❌ W0 (plan 02-02) | ⬜ pending |
| 2-02-02 | 02 | 2 | GEM-01..05, ANLZ-04/05 | T-02-06 / T-02-07 / T-02-08 / T-02-09 | Tool imports + structural invariants | smoke + unit | `python3 -c "from tools.analysis.gemini_video_analyzer import GeminiVideoAnalyzer; t=GeminiVideoAnalyzer(); assert t.capability=='video_analysis' and t.provider=='gemini'"` then plan 02-04 unit tests | ❌ W0 (plan 02-02 + 02-04) | ⬜ pending |
| 2-03-01 | 03 | 3 | SKILL-01, GEM-05 | T-02-13 / T-02-14 | SKILL.md exists, no real API key embedded | contract | `pytest tests/contracts/test_phase2_contracts.py::test_gemini_skill_file_exists tests/contracts/test_phase2_contracts.py::test_gemini_skill_has_required_sections tests/contracts/test_phase2_contracts.py::test_no_google_api_keys_embedded -x` | ❌ W0 (plan 02-03 + 02-04) | ⬜ pending |
| 2-03-02 | 03 | 3 | GEM-05 | T-02-14 / T-02-15 | agent_skills wiring resolves to file | contract | `pytest tests/contracts/test_phase2_contracts.py::test_agent_skills_wiring_resolves_to_skill_file -x` | ❌ W0 (plan 02-04) | ⬜ pending |
| 2-04-01 | 04 | 3 | — | T-02-16 | Shared fixtures usable, no test collection errors | smoke | `pytest tests/unit/conftest.py --collect-only -q` | ❌ W0 (plan 02-04) | ⬜ pending |
| 2-04-02 | 04 | 3 | GEM-01 | — | Tool contract (name, capability, provider, runtime, agent_skills) | contract | `pytest tests/unit/test_gemini_video_analyzer.py::test_contract_fields -x` | ❌ W0 | ⬜ pending |
| 2-04-03 | 04 | 3 | GEM-01 | T-02-06 | Auth priority GEMINI_API_KEY > GOOGLE_API_KEY | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_auth_priority_gemini_first tests/unit/test_gemini_video_analyzer.py::test_auth_falls_back_to_google -x` | ❌ W0 | ⬜ pending |
| 2-04-04 | 04 | 3 | GEM-01 | T-02-06 | Missing key error does NOT leak key value | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_execute_no_key_returns_error_without_leaking_value tests/unit/test_gemini_video_analyzer.py::test_api_key_value_not_in_any_error -x` | ❌ W0 | ⬜ pending |
| 2-04-05 | 04 | 3 | GEM-02 | T-02-08 | Polling PROCESSING → ACTIVE succeeds | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_poll_processing_then_active -x` | ❌ W0 | ⬜ pending |
| 2-04-06 | 04 | 3 | GEM-02 | — | FAILED state raises VideoUploadError | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_poll_failed_raises -x` | ❌ W0 | ⬜ pending |
| 2-04-07 | 04 | 3 | GEM-02 | T-02-08 | Wall-clock timeout raises VideoUploadError | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_poll_timeout_raises -x` | ❌ W0 | ⬜ pending |
| 2-04-08 | 04 | 3 | GEM-03 | T-02-09 | `client.files.delete` called on success | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_file_deleted_on_success -x` | ❌ W0 | ⬜ pending |
| 2-04-09 | 04 | 3 | GEM-03 | T-02-09 | `client.files.delete` called on failure (finally) | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_file_deleted_on_failure -x` | ❌ W0 | ⬜ pending |
| 2-04-10 | 04 | 3 | GEM-04 | T-02-07 | Flattened schema passed to generate_content config | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_flat_schema_passed_to_generate_content -x` | ❌ W0 | ⬜ pending |
| 2-04-11 | 04 | 3 | GEM-04 | — | MAX_TOKENS triggers compact retry | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_max_tokens_triggers_compact_retry -x` | ❌ W0 | ⬜ pending |
| 2-04-12 | 04 | 3 | GEM-04 | — | Empty text triggers compact retry | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_empty_text_triggers_retry -x` | ❌ W0 | ⬜ pending |
| 2-04-13 | 04 | 3 | GEM-04 | — | Two consecutive failures raise VideoAnalysisRetryExhausted | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_retry_exhausted_raises -x` | ❌ W0 | ⬜ pending |
| 2-04-14 | 04 | 3 | GEM-04 | T-02-12 | Preview model fallback to gemini-2.5-pro on ClientError | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_model_fallback_on_preview_unavailable -x` | ❌ W0 | ⬜ pending |
| 2-04-15 | 04 | 3 | ANLZ-05 | — | shot_boundaries absent → prompt directs `shot_boundary_source="model"` | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_shot_boundaries_absent_prompt_has_model_directive -x` | ❌ W0 | ⬜ pending |
| 2-04-16 | 04 | 3 | ANLZ-05 | — | shot_boundaries accepts list-of-list AND list-of-dict | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_shot_boundaries_both_shapes_normalize tests/unit/test_gemini_video_analyzer.py::test_shot_boundaries_passed_into_prompt -x` | ❌ W0 | ⬜ pending |
| 2-04-17 | 04 | 3 | ANLZ-04 | — | Prompt instructs confidence="low" rather than null | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_prompt_instructs_confidence_low_not_null -x` | ❌ W0 | ⬜ pending |
| 2-04-18 | 04 | 3 | ANLZ-04 | T-02-17 | Invalid artifact rejected + file deleted | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_invalid_artifact_returns_failure_and_deletes -x` | ❌ W0 | ⬜ pending |
| 2-04-19 | 04 | 3 | — | — | Tool source does NOT import write_checkpoint | contract | `pytest tests/unit/test_gemini_video_analyzer.py::test_tool_source_does_not_import_write_checkpoint -x` | ❌ W0 | ⬜ pending |
| 2-04-20 | 04 | 3 | ANLZ-01 | T-02-02 | Selector registration + providers list excludes self | contract | `pytest tests/contracts/test_phase2_contracts.py::test_selector_registered_with_video_analysis_capability tests/contracts/test_phase2_contracts.py::test_selector_excludes_self_from_providers -x` | ❌ W0 | ⬜ pending |
| 2-04-21 | 04 | 3 | ANLZ-01 | T-02-05 | Preference order: explicit > env > key-presence > first-available | contract | `pytest tests/contracts/test_phase2_contracts.py -k "preference_order or zero_providers" -x` | ❌ W0 | ⬜ pending |
| 2-04-22 | 04 | 3 | GEM-04 | T-02-07 | Flattened schema strips $ref/uniqueItems/additionalProperties:false, preserves enum confidence-map | contract | `pytest tests/contracts/test_phase2_contracts.py::test_flattened_schema_removes_unsupported_keys tests/contracts/test_phase2_contracts.py::test_flattened_schema_preserves_confidence_map tests/contracts/test_phase2_contracts.py::test_schema_adapter_idempotent -x` | ❌ W0 | ⬜ pending |
| 2-04-23 | 04 | 3 | ANLZ-04 | — | Phase 1 minimal artifact fixture still validates | contract | `pytest tests/contracts/test_phase2_contracts.py::test_minimal_artifact_validates -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 in Phase 2 = the first task of each plan that creates the file a later test exercises. Each is owned by a specific plan:

- [ ] `lib/analysis_errors.py` — 3-class hierarchy (plan 02-01 Task 1)
- [ ] `tools/analysis/video_analyzer_selector.py` — capability router (plan 02-01 Task 2)
- [ ] `tests/unit/__init__.py` + `tests/contracts/__init__.py` — pytest package discovery (plan 02-01 Task 2)
- [ ] `tools/analysis/gemini_video_analyzer.py` — provider with Files API lifecycle (plan 02-02 Task 2)
- [ ] `requirements.txt` — `google-genai>=1.73,<2` pin (plan 02-02 Task 1)
- [ ] `.agents/skills/gemini-video-analysis/SKILL.md` — Layer 3 skill (plan 02-03 Task 1)
- [ ] `tests/unit/conftest.py` — shared mock fixtures (plan 02-04 Task 1)
- [ ] `tests/unit/test_gemini_video_analyzer.py` — 18 behaviors (plan 02-04 Task 2)
- [ ] `tests/contracts/test_phase2_contracts.py` — 13+ contract tests (plan 02-04 Task 3)

Framework install: already present (pytest + jsonschema in dev env). Only `pip install 'google-genai>=1.73,<2'` during plan 02-02 Task 1.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Field-level quality on one real video | SKILL-03 | Requires a real `GEMINI_API_KEY` + a real <2 min video; subjective judgment on pacing/color/hook quality | See block below — post-execute, pre-phase-close |

**SKILL-03 — Field-level quality review (human gate):**

```
1. Ensure GEMINI_API_KEY is set in .env.
2. Place a <2 minute video at tests/fixtures/short_sample.mp4 (prefer something with clear
   pacing + visible typography + a hook moment, e.g., a YouTube Short or TikTok).
3. Run:
     python -c "from tools.tool_registry import registry; registry.discover(); \
                sel = registry.get('video_analyzer_selector'); \
                r = sel.execute({'video_path': 'tests/fixtures/short_sample.mp4'}); \
                import json; print(json.dumps(r.data, indent=2))"
4. Inspect the printed artifact. Verify:
   - ≥12 of the 16 canonical required fields are populated with NON-DEFAULT values
     (required = 4 source + 6 editing + 4 audio + 3 visual + 5 narrative = 22 total;
     the ≥12 bar is intentionally lenient for a first-run gate)
   - editing_pacing.pacing_style is one of the enum values and subjectively correct
   - visual_style.color_palette.primary contains 1-3 plausible hex strings
   - narrative.hook_type is non-"none" if the video has a recognizable hook
   - Per-dimension confidence maps contain at least one "low" entry if fields were
     uncertain (i.e., the model actually uses "low" rather than omitting)
5. If the review passes, record the decision in STATE.md and close the phase.
   If the review fails, re-open 02-03-PLAN (prompting) to tighten SKILL.md guidance.
```

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (only SKILL-03 is manual)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (every ❌ W0 row above maps to a plan task that creates the file)
- [x] No watch-mode flags (all pytest commands use `-x -q`, no `--watch`)
- [x] Feedback latency < 2s for quick command (<5s measured in RESEARCH)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned 2026-04-17 — awaiting Wave-0 file creation to flip status to ✅.
