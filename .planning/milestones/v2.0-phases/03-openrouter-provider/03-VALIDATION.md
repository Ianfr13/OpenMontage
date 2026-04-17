---
phase: 3
slug: openrouter-provider
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-17
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Mirrors Phase 2's shape. Inherits the autouse `_scrub_provider_keys` fixture from `tests/unit/conftest.py` (scrubs `OPENROUTER_API_KEY` + all other provider keys by default — tests opt in via `mock_openai` or `mock_genai`).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest>=8.0` (already pinned in `requirements-dev.txt`) |
| **Config file** | None in repo root; default directory-based discovery. `tests/unit/__init__.py` + `tests/contracts/__init__.py` already present from Phase 1 |
| **Quick run command** | `pytest tests/unit/test_openrouter_video_analyzer.py -x -q` |
| **Full suite command** | `pytest tests/ -q` (Phase 1 + Phase 2 + Phase 3) |
| **Estimated runtime** | ~10-30 seconds (unit <10s; full suite <30s with all 3 phases) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit/test_openrouter_video_analyzer.py -x -q` (<10s)
- **After every plan wave:** Run `pytest tests/unit/ tests/contracts/ -q` (<30s)
- **Before `/gsd-verify-work`:** Full suite `pytest tests/ -q` must be green with ALL provider keys unset (`unset OPENROUTER_API_KEY GEMINI_API_KEY GOOGLE_API_KEY VIDEO_ANALYZER_PROVIDER`)
- **Max feedback latency:** <30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 1 | OR-02 | — | openai>=1.0 pinned + importable | structural | `grep -E "^openai>=1" requirements.txt && python3 -c "import openai; from openai import OpenAI, APIError, BadRequestError; OpenAI(api_key='x', base_url='https://openrouter.ai/api/v1')"` | ✅ | ⬜ pending |
| 3-01-02 | 01 | 1 | OR-01 | T-03-06 | Contract fields (name/capability/provider/runtime/agent_skills) match; no key leak in missing-key error | unit | `pytest tests/unit/test_openrouter_video_analyzer.py::test_contract_fields tests/unit/test_openrouter_video_analyzer.py::test_auth_missing_key_no_leak -x` | ❌ W0 (Task 3-03-02) | ⬜ pending |
| 3-01-02 | 01 | 1 | OR-02 | — | OpenAI client constructed with `base_url="https://openrouter.ai/api/v1"` AND explicit `api_key=` (not SDK default) | unit | `pytest tests/unit/test_openrouter_video_analyzer.py::test_openai_client_base_url tests/unit/test_openrouter_video_analyzer.py::test_api_key_passed_explicitly -x` | ❌ W0 (Task 3-03-02) | ⬜ pending |
| 3-01-02 | 01 | 1 | OR-03 | T-03-08 | `max_upload_bytes` gate rejects BEFORE encoding; clamp `[1, 2GB]`; data URL prefix `data:video/mp4;base64,`; unsupported MIME rejected | unit | `pytest tests/unit/test_openrouter_video_analyzer.py -k "max_upload or base64_data_url or unsupported_mime or clamp" -x` | ❌ W0 (Task 3-03-02) | ⬜ pending |
| 3-01-02 | 01 | 1 | OR-04 | T-03-07 | Messages use raw dict `{"type":"video_url",...}`; first call sends `response_format=json_schema,strict=True` + `extra_body={"provider":{"require_parameters":True}}`; `BadRequestError` triggers prompt-embedded fallback without `extra_body`; flat schema has no $ref/uniqueItems | unit | `pytest tests/unit/test_openrouter_video_analyzer.py -k "video_url_content_part or json_schema_response_format_first or bad_request_falls_back or fallback_does_not_set_extra_body or flat_schema_no_ref" -x` | ❌ W0 (Task 3-03-02) | ⬜ pending |
| 3-01-02 | 01 | 1 | OR-05 | T-03-09 | `finish_reason=="length"` STRING check triggers compact retry; empty content triggers retry; exhausted → `VideoAnalysisRetryExhausted`; Mock-typed finish_reason does NOT silently bypass | unit | `pytest tests/unit/test_openrouter_video_analyzer.py -k "length_finish_reason or empty_content or retry_exhausted or string_not_enum" -x` | ❌ W0 (Task 3-03-02) | ⬜ pending |
| 3-01-02 | 01 | 1 | ANLZ-06 | T-03-07 | `result.data` equals canonical artifact verbatim — no `selected_provider`/`provider_used`/`selected_tool` keys stamped | unit | `pytest tests/unit/test_openrouter_video_analyzer.py::test_result_data_is_canonical_artifact_only -x` | ❌ W0 (Task 3-03-02) | ⬜ pending |
| 3-01-02 | 01 | 1 | — | T-03-06 | Sentinel API key value never appears in any `ToolResult.error` across all failure paths | unit | `pytest tests/unit/test_openrouter_video_analyzer.py::test_api_key_value_not_in_any_error -x` | ❌ W0 (Task 3-03-02) | ⬜ pending |
| 3-01-02 | 01 | 1 | — | T-03-21 | Cost surfaced from `resp.usage.cost` BODY field; tool source contains NO `response.headers`/`x-openrouter-credit-remaining` references; `result.model` verbatim from `resp.model` | unit | `pytest tests/unit/test_openrouter_video_analyzer.py -k "cost_from_usage_body or tool_result_model" -x && ! grep -qE "response\.headers\|x-openrouter-credit-remaining" tools/analysis/openrouter_video_analyzer.py` | ❌ W0 (Task 3-03-02) | ⬜ pending |
| 3-01-02 | 01 | 1 | — | — | Tool does NOT import `write_checkpoint` (Phase 1 WR-05) | unit | `pytest tests/unit/test_openrouter_video_analyzer.py::test_tool_does_not_import_checkpoint -x` | ❌ W0 (Task 3-03-02) | ⬜ pending |
| 3-01-02 | 01 | 1 | — | — | `_FLAT_SCHEMA` class attribute is None until first call to `_flat_schema()` (MD-01 lazy cache) | unit | `pytest tests/unit/test_openrouter_video_analyzer.py::test_flat_schema_is_lazy -x` | ❌ W0 (Task 3-03-02) | ⬜ pending |
| 3-02-01 | 02 | 2 | SKILL-02 | T-03-13 | SKILL.md exists, ≥280 lines, YAML frontmatter, all 4 dimensions, `json_schema` + `require_parameters` + `== "length"` + `x-openrouter-credit-remaining` warn + OPENROUTER_API_KEY + OPENROUTER_MODEL + base64 + both default models; NO real key embedded | contract | `pytest tests/contracts/test_phase3_contracts.py -k "skill_file_exists or skill_required_sections or no_embedded_api_keys" -x` | ❌ W0 (Task 3-03-03) | ⬜ pending |
| 3-02-02 | 02 | 2 | OR-06 | T-03-14 | Provider tool `agent_skills = ["openrouter-video-analysis"]` resolves to existing `.agents/skills/openrouter-video-analysis/SKILL.md`; Phase 2 wiring intact; selector NOT modified | contract | `pytest tests/contracts/test_phase3_contracts.py::test_agent_skills_wiring_resolves_to_skill_file -x` | ❌ W0 (Task 3-03-03) | ⬜ pending |
| 3-03-01 | 03 | 2 | — | — | `tests/unit/conftest.py` EXTENDED with `mock_openai` + response-factories fixtures; Phase 2 fixtures unchanged | structural | `grep -c "^def mock_openai" tests/unit/conftest.py; grep -c "^def mock_genai" tests/unit/conftest.py` (both must be 1) | ❌ W0 (Task 3-03-01) | ⬜ pending |
| 3-03-02 | 03 | 2 | OR-01..05 | T-03-17, T-03-21 | All 22 behavior unit tests from plan 03-01 green with no API keys | unit | `pytest tests/unit/test_openrouter_video_analyzer.py -x -q` | ❌ W0 (this task creates the file) | ⬜ pending |
| 3-03-03 | 03 | 2 | OR-06, ANLZ-06, SKILL-02 | T-03-18, T-03-20 | Registration, preference order with 4 configs, cross-provider consistency (ANLZ-06 gate parametrized over Gemini + OpenRouter), SKILL presence + sections + no-key-leak, flat-schema adapter invariants, no checkpoint import, no selector metadata stamping | contract | `pytest tests/contracts/test_phase3_contracts.py -x -q` | ❌ W0 (this task creates the file) | ⬜ pending |
| Phase gate | — | — | ALL | ALL | Full Phase 1+2+3 suite green with NO provider keys set | full | `unset OPENROUTER_API_KEY GEMINI_API_KEY GOOGLE_API_KEY VIDEO_ANALYZER_PROVIDER; pytest tests/ -q` | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All test infrastructure required by Phase 3 is created by plan 03-03 itself (Wave 2 alongside plans 03-01 and 03-02 if the file-ownership rule permits — see Wave 0 Gaps in 03-RESEARCH.md). The Wave 0 gap is:

- [ ] `tests/unit/test_openrouter_video_analyzer.py` — covers OR-01..05, security guards, retry logic (22 behaviors). Created by plan 03-03 Task 2.
- [ ] `tests/contracts/test_phase3_contracts.py` — covers OR-06, ANLZ-06, SKILL-02 invariants + cross-provider consistency gate. Created by plan 03-03 Task 3.
- [ ] `tests/unit/conftest.py` EXTENSION — adds `mock_openai` + `openrouter_response_factories` fixtures alongside Phase 2's `mock_genai`. Created by plan 03-03 Task 1.

No new framework install required — `pytest>=8.0` already pinned in `requirements-dev.txt` from Phase 1. Plan 03-01 Task 1 adds `openai>=1.0,<3` to `requirements.txt` (the SDK the tool calls AND the tests mock).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-video field-level quality review | SKILL-03 | Quality assessment of analysis output on a real video requires a human eye — no automated oracle. Gated as a post-execute HUMAN-UAT checkpoint, same as Phase 2's SKILL-03 deferral. | **After `/gsd-execute-phase 3` completes:** (1) Set `OPENROUTER_API_KEY` in `.env` to a real OpenRouter key (get one from https://openrouter.ai/settings/keys). (2) Set `VIDEO_ANALYZER_PROVIDER=openrouter`. (3) Place a short (<2 min) reference video at e.g. `/tmp/reference.mp4`. (4) Run: `python3 -c "from tools.tool_registry import registry; registry.discover(); sel = registry.get('video_analyzer_selector'); import json; r = sel.execute({'video_path': '/tmp/reference.mp4'}); print(json.dumps(r.data, indent=2))"`. (5) Confirm ≥12 of 16 canonical `video_analysis` fields (across the 4 dimensions) are populated with meaningful values — not "low" for every field, not copy-paste of the input prompt, not empty strings. Record the outcome in `03-SKILL-03-UAT.md` as pass/fail with any field-level notes. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test files created in plan 03-03)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-17 (auto-approved by planner; inherits Phase 2 validation discipline)
</content>
