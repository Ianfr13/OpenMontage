---
phase: 03-openrouter-provider
verified: 2026-04-17T00:00:00Z
status: human_needed
score: 6/6 must-haves verified
overrides_applied: 0
human_verification:
  - test: "SKILL-03 field-level quality review"
    expected: ">=12 of 16 canonical video_analysis fields populated appropriately (not all 'low', not prompt-copy) on one real <2min video routed through video_analyzer_selector with OPENROUTER_API_KEY set and VIDEO_ANALYZER_PROVIDER=openrouter; output shape matches Gemini-analyzed artifact of the same video"
    why_human: "Requires live API call to OpenRouter with a real video; automated tests cover shape/contract but not field-quality semantics. Same manual gate as Phase 2 SKILL-03."
---

# Phase 03: OpenRouter Provider Verification Report

**Phase Goal:** A second interchangeable provider slots into the existing selector; both providers produce artifacts passing the same canonical schema — selector callers cannot tell which backend was used (ANLZ-06).
**Verified:** 2026-04-17
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `openrouter_video_analyzer.py` exists with correct class attrs; registry returns it via `get_by_capability("video_analysis")` | VERIFIED | `registry.get_by_capability("video_analysis")` returns `['gemini_video_analyzer', 'openrouter_video_analyzer', 'video_analyzer_selector']`; `get_info()` → `openrouter_video_analyzer / video_analysis / openrouter / ['openrouter-video-analysis']` (line 165-177) |
| 2 | Selector routes to OpenRouter when `VIDEO_ANALYZER_PROVIDER=openrouter` OR only `OPENROUTER_API_KEY` set OR `preferred_provider="openrouter"` | VERIFIED | Contract tests `test_selector_preference_openrouter_env_wins`, `test_selector_preference_explicit_openrouter_wins`, `test_selector_preference_openrouter_when_only_openrouter_key` all pass (pytest 47 passed) |
| 3 | Tool encodes as `data:<mime>;base64,...` inline; oversize rejected before encoding with error | VERIFIED | `_build_data_url` (line 146-154) uses `f"data:{mime};base64,{b64}"`; `execute()` size gate at line 514 rejects before `_build_data_url` call at line 536; `test_max_upload_bytes_reject` + `test_base64_data_url_prefix` + `test_unsupported_mime_rejected` pass |
| 4 | `finish_reason == "length"` (STRING) triggers ONE compact retry before raising `VideoAnalysisRetryExhausted` | VERIFIED | `"length"` appears 4 times in source (line 367 uses STRING `==`); `FinishReason` enum absent (0 matches); `test_length_finish_reason_triggers_compact_retry`, `test_empty_content_triggers_retry`, `test_retry_exhausted_raises`, `test_finish_reason_string_not_enum_guard` pass |
| 5 | Both providers' artifacts deep-equal and pass same canonical schema; caller cannot tell which backend served (ANLZ-06) | VERIFIED | `test_cross_provider_consistency_same_canonical_artifact` parametrized `["gemini", "openrouter"]` both pass (line 221-222); `test_cross_provider_identical_top_level_keys` passes; tool never stamps provider metadata on `result.data` (`test_tool_does_not_stamp_selector_metadata_on_data` passes) |
| 6 | `SKILL.md` exists at `.agents/skills/openrouter-video-analysis/` and referenced in tool's `agent_skills`; SKILL-03 deferred to HUMAN-UAT | VERIFIED (+ human_needed for SKILL-03) | File exists (341 lines); frontmatter `name: openrouter-video-analysis`; tool line 177 `agent_skills = ["openrouter-video-analysis"]`; `test_skill_file_exists` + `test_skill_required_sections` + `test_agent_skills_wiring_resolves_to_skill_file` pass |

**Score:** 6/6 truths verified (SKILL-03 field-quality review routed to human verification)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tools/analysis/openrouter_video_analyzer.py` | BaseTool subclass, ≥280 lines | VERIFIED | 590 lines; `class OpenRouterVideoAnalyzer(BaseTool)` at line 157; all required class attrs present |
| `.agents/skills/openrouter-video-analysis/SKILL.md` | ≥280 lines, frontmatter, required sections | VERIFIED | 341 lines; valid YAML frontmatter; `name: openrouter-video-analysis` |
| `tests/unit/test_openrouter_video_analyzer.py` | ≥22 tests | VERIFIED | 30 test functions, 589 lines |
| `tests/contracts/test_phase3_openrouter_contracts.py` | ≥13 tests, ANLZ-06 parametrized | VERIFIED | 16 test functions + 1 parametrized over 2 providers = 17 logical cases, 446 lines |
| `tests/unit/conftest.py` | Extended with `mock_openai` fixture | VERIFIED | 281 lines; both `mock_genai` and `mock_openai` fixtures present; Phase 2 fixtures unchanged |
| `requirements.txt` | `openai>=1.0,<3` pin | VERIFIED | Pin added below `google-genai>=1.73,<2` |

### Key Link Verification

| From | To | Via | Status |
|------|------|-----|--------|
| `openrouter_video_analyzer.py` | `lib/schema_adapter.py` | `to_api_schema(load_schema('video_analysis'))` inside `_flat_schema()` (line 192) | WIRED |
| `openrouter_video_analyzer.py` | `schemas/artifacts/__init__.py` | `validate_artifact("video_analysis", artifact)` (line 562) | WIRED |
| `openrouter_video_analyzer.py` | `lib/analysis_errors.py` | `from lib.analysis_errors import VideoAnalysisError, VideoAnalysisRetryExhausted, VideoUploadError` (line 46-50) | WIRED |
| `openrouter_video_analyzer.py` | openai SDK | `OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1", ...)` (line 550) | WIRED |
| `openrouter_video_analyzer.py` | `.agents/skills/openrouter-video-analysis/SKILL.md` | `agent_skills = ["openrouter-video-analysis"]` (line 177) + file exists | WIRED |
| Selector (Phase 2) | OpenRouter tool | Registry auto-discovery via `get_by_capability("video_analysis")` | WIRED (zero selector code changes) |

### Research Callout Grep Results

All mandatory grep invariants pass:

| Grep | Expected | Actual | Pass |
|------|----------|--------|------|
| `OpenAI(api_key=` | ≥1 | 1 | YES |
| `base_url="https://openrouter.ai/api/v1"` | ==1 | 1 | YES |
| `FinishReason` in tool | ==0 | 0 | YES (Pitfall 2) |
| `"length"` in tool | ≥2 | 4 | YES |
| `from lib.checkpoint` in tool | ==0 | 0 | YES (WR-05) |
| base64 inline encoding logic | present | `_build_data_url` at line 146, `f"data:{mime};base64,{b64}"` at line 154 | YES |
| `require_parameters` in tool | ≥1 | 4 | YES (Pitfall 4) |
| `usage.cost` / `usage, "cost"` in tool | ≥1 | 2 | YES (body not header) |
| `x-openrouter-credit-remaining` in tool | ==0 | 0 | YES (Pitfall 5 — fake header absent) |
| `x-openrouter-credit-remaining` in SKILL.md | ≥1 | 3 | YES (explicitly documented as NOT-REAL) |
| real OpenRouter key regex `sk-or-v1-[a-f0-9]{40,}` | ==0 | 0 in both tool and SKILL | YES (T-03-11) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| OR-01 | 03-01, 03-03 | BaseTool, capability=video_analysis, provider=openrouter, OPENROUTER_API_KEY, OPENROUTER_MODEL env | SATISFIED | Tool lines 157-177; `test_contract_fields`, `test_auth_missing_key_no_leak` |
| OR-02 | 03-01, 03-03 | openai>=1.0 SDK with base_url | SATISFIED | Line 550; `requirements.txt` openai>=1.0,<3; `test_openai_client_base_url`, `test_api_key_passed_explicitly` |
| OR-03 | 03-01, 03-03 | Inline base64 + max_upload_bytes gate before encoding | SATISFIED | `_build_data_url` + size gate at execute(); `test_max_upload_bytes_reject` + spy proves `base64.b64encode` not called on oversize |
| OR-04 | 03-01, 03-03 | `response_format=json_schema` structured + prompt-embedded fallback on BadRequestError | SATISFIED | `_response_format()` + `_analyze_with_fallback()` 4-branch ladder; `test_json_schema_response_format_first`, `test_bad_request_falls_back_to_prompt_embedded`, `test_fallback_does_not_set_extra_body` |
| OR-05 | 03-01, 03-03 | `finish_reason == "length"` STRING detection + one compact retry → `VideoAnalysisRetryExhausted` | SATISFIED | Line 367 STRING equality; `test_length_finish_reason_triggers_compact_retry`, `test_retry_exhausted_raises` |
| OR-06 | 03-02, 03-03 | `agent_skills` references `.agents/skills/openrouter-video-analysis/SKILL.md` | SATISFIED | Tool line 177; `test_agent_skills_wiring_resolves_to_skill_file` |
| ANLZ-06 | 03-01, 03-03 | Both providers produce artifacts passing same canonical schema — caller can't distinguish | SATISFIED | `test_cross_provider_consistency_same_canonical_artifact` parametrized over [gemini, openrouter], both pass deep-equality + `validate_artifact`; `test_tool_does_not_stamp_selector_metadata_on_data` confirms no metadata leak |
| SKILL-02 | 03-02, 03-03 | SKILL.md presence, required sections, no embedded keys | SATISFIED | 341-line file with 9+ sections, frontmatter, all required greps pass, 0 real-key regex matches |
| SKILL-03 | (manual) | Real-video field-quality review | NEEDS HUMAN | Deferred to post-execute HUMAN-UAT (same gate as Phase 2) |

No orphaned requirements: ROADMAP maps OR-01..06, ANLZ-06, SKILL-02, SKILL-03 to Phase 3; all are addressed (SKILL-03 via human verification).

### Anti-Patterns Found

None. Scan results:
- `TODO|FIXME|XXX|HACK|PLACEHOLDER` in tool source: 0 material hits
- `from lib.checkpoint` or `write_checkpoint` in tool: 0 (WR-05 preserved)
- `response.headers` or `x-openrouter-credit-remaining` reads in tool: 0 (Pitfall 5 preserved)
- `FinishReason` enum reference in tool: 0 (Pitfall 2 preserved)
- Selector modifications: 0 (Phase 2 contract held; selector still points at `["gemini-video-analysis"]` only; to be updated in Phase 6 INT-01)
- Real OpenRouter API key embedded anywhere: 0

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 3 test suite passes without API keys | `unset GEMINI_API_KEY GOOGLE_API_KEY OPENROUTER_API_KEY VIDEO_ANALYZER_PROVIDER; pytest tests/unit/test_openrouter_video_analyzer.py tests/contracts/test_phase3_openrouter_contracts.py -q` | 47 passed in 3.53s | PASS |
| Tool module imports and registers correctly | `python3 -c "from tools.tool_registry import registry; registry.discover(); print([p.name for p in registry.get_by_capability('video_analysis')])"` | `['gemini_video_analyzer', 'openrouter_video_analyzer', 'video_analyzer_selector']` | PASS |
| Tool get_info exposes all required fields | `OpenRouterVideoAnalyzer().get_info()` | `openrouter_video_analyzer / video_analysis / openrouter / ['openrouter-video-analysis']` | PASS |
| Cross-provider consistency (ANLZ-06) gate | `pytest tests/contracts/test_phase3_openrouter_contracts.py::test_cross_provider_consistency_same_canonical_artifact -q` | 2 passed (gemini + openrouter) | PASS |

### Human Verification Required

#### 1. SKILL-03 — Field-level quality review

**Test:** Run one real <2 min video through `video_analyzer_selector` with `OPENROUTER_API_KEY` set and `VIDEO_ANALYZER_PROVIDER=openrouter`. Then run the same video through the Gemini provider and compare output shapes.

**Expected:**
- ≥12 of 16 canonical `video_analysis` fields populated appropriately (not all `"low"` confidence, not a copy-paste of the input prompt, not empty defaults).
- Output shape (top-level keys, nested structure) matches the Gemini-analyzed artifact of the same video — this is the live ANLZ-06 sanity check.
- Both artifacts pass `validate_artifact("video_analysis", ...)` without modification.

**Why human:** Requires live OpenRouter API call with a real video and qualitative field-quality judgment that automated tests cannot perform. Same manual gate shape as Phase 2 SKILL-03.

### Gaps Summary

No automated gaps found. Every phase requirement (OR-01..06, ANLZ-06, SKILL-02) is covered by at least one passing test. Source-level invariants from RESEARCH.md Findings 2, 4, 5 (finish_reason STRING / cost via body / no fake header) all hold and are additionally guarded by Pitfall tests. SKILL-03 is the single outstanding item and is by design a post-execute human gate (same pattern as Phase 2).

The phase goal is achieved in code: the OpenRouter provider slots into the Phase 2 selector with zero selector changes, both providers pass the same canonical schema, and caller cannot distinguish backends from `result.data`. The remaining human gate (SKILL-03) verifies real-world output quality on a live API call, which must be done manually.

---

*Verified: 2026-04-17*
*Verifier: Claude (gsd-verifier)*
