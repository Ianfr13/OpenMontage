---
phase: 03-openrouter-provider
plan: 01
subsystem: tools/analysis
tags: [openrouter, video_analysis, base-tool, inline-base64, structured-output, provider]
requires:
  - lib/analysis_errors.py (Phase 2)
  - lib/schema_adapter.py (Phase 1)
  - schemas/artifacts/__init__.py (Phase 1)
  - schemas/artifacts/video_analysis.schema.json (Phase 1)
  - tools/base_tool.py (BaseTool, ToolResult, ToolRuntime, ToolTier, ToolStability, ResourceProfile, RetryPolicy)
  - tools/analysis/video_analyzer_selector.py (Phase 2 — auto-discovery loop, zero code changes)
provides:
  - tools/analysis/openrouter_video_analyzer.py (BaseTool, provider="openrouter")
  - requirements.txt pin: openai>=1.0,<3
affects:
  - tools/analysis/video_analyzer_selector.py (now resolves VIDEO_ANALYZER_PROVIDER=openrouter and preferred_provider="openrouter" via auto-discovery — no file change)
tech-stack:
  added:
    - openai>=1.0,<3 (verified 2.32.0 installs cleanly alongside google-genai 1.73.1)
  patterns:
    - Phase 2 MD-01: lazy _FLAT_SCHEMA classmethod cache (None at class body, populated on first _flat_schema() call)
    - Phase 2 MD-03: narrow `except openai.APIError` on client init
    - Phase 2 MD-04: clamp max_upload_bytes to [1, 2 GB]; size gate rejects BEFORE base64 encoding
    - ANLZ-06 / Pitfall 7: result.data IS the canonical artifact — no selector/provider/cost metadata stamped
    - WR-05: tool does NOT import lib.checkpoint (pipeline_type unknown at tool layer)
key-files:
  created:
    - tools/analysis/openrouter_video_analyzer.py
  modified:
    - requirements.txt
decisions:
  - "Inline single-line OpenAI() constructor with literal base_url string — required so the plan's grep guards (`OpenAI(api_key=` and `base_url=\"https://openrouter.ai/api/v1\"`) match the source directly; the OPENROUTER_BASE_URL constant is still defined at module scope for callers that need it"
  - "Duplicate `_normalize_shot_boundaries` helper (not shared with Phase 2) — per CONTEXT discretion note, extract to lib/ only when a third video_analysis provider materializes"
  - "Fallback ladder is explicit 4-branch (structured full -> structured compact -> prompt-embedded full -> prompt-embedded compact); deliberately NOT looped so each branch maps 1:1 to the plan 03-03 behavior tests (9, 11, 13, 15)"
  - "`extra_body={provider: {require_parameters: True}}` set ONLY on the structured path; omitted on the prompt-embedded fallback per RESEARCH Open Question 1 (don't over-constrain routing when structured output is already conceded)"
  - "Cost surfaced via `getattr(resp.usage, 'cost', 0.0)` body field — NOT from any response header; corrects CONTEXT.md's original speculation about `x-openrouter-credit-remaining` (that header is not documented by OpenRouter; RESEARCH Finding 4)"
metrics:
  duration_minutes: 4
  tasks_completed: 2
  files_created: 1
  files_modified: 1
  tool_line_count: 590
  completed_date: 2026-04-17
---

# Phase 3 Plan 01: OpenRouter Video Analyzer Summary

Second interchangeable `video_analysis` provider shipped — a `BaseTool` that encodes local videos as inline base64 and calls OpenRouter's OpenAI-compatible `/chat/completions` via the `openai>=1.0` SDK, with a 4-branch structured-output fallback ladder, string-valued `finish_reason=="length"` truncation retry, and canonical-schema validation gate.

## What Shipped

### Task 1 — `requirements.txt` pin

Added exactly one line: `openai>=1.0,<3` (below `google-genai>=1.73,<2`, no reorders, no other bumps). Verified the SDK surface under `openai==2.32.0`:

- `from openai import OpenAI, APIError, BadRequestError` imports cleanly
- `BadRequestError.__mro__` contains `APIError` (narrow-except safety — MD-03)
- `OpenAI(api_key='dummy', base_url='https://openrouter.ai/api/v1')` constructs without raising
- `Choice.model_fields['finish_reason'].annotation` stringifies to a `typing.Literal[...]` containing both `'length'` and `'stop'` — the Pitfall 2 sentinel (STRING, not enum)
- `google-genai 1.73.1` still imports (no Phase 2 regression)

**Commit:** `341a047`

### Task 2 — `tools/analysis/openrouter_video_analyzer.py` (590 lines)

`class OpenRouterVideoAnalyzer(BaseTool)` with:

- `name = "openrouter_video_analyzer"`, `capability = "video_analysis"`, `provider = "openrouter"`, `runtime = ToolRuntime.API`, `tier = ToolTier.ANALYZE`, `stability = ToolStability.BETA`
- `dependencies = ["env:OPENROUTER_API_KEY", "python:openai"]`
- `agent_skills = ["openrouter-video-analysis"]` → pointed at the SKILL shipped in plan 03-02

**`execute()` sequence:** path-exists → key-present → size-clamp → size-gate → MIME-gate → encode → client-init → analyze-with-fallback → `validate_artifact` → return.

**4-branch fallback ladder** (RESEARCH Pattern 3 + Open Question 1):
1. structured + full (with `extra_body={"provider":{"require_parameters":True}}`)
2. on `VideoAnalysisError`: structured + compact retry (still with `require_parameters`)
3. on `BadRequestError`: prompt-embedded + full (NO `extra_body`; schema literally embedded in prompt)
4. on `VideoAnalysisError`: prompt-embedded + compact retry
5. second failure → `VideoAnalysisRetryExhausted`

**Commit:** `efe9c6c`

## Acceptance-Criteria Confirmations

- `OpenRouterVideoAnalyzer._FLAT_SCHEMA` is `None` at class body (lazy cache — MD-01). Class-body line: `    _FLAT_SCHEMA: dict | None = None` (line 187)
- No `from lib.checkpoint` import anywhere in source (WR-05): `grep -c 'from lib.checkpoint' ...` → 0
- No `response.headers` / `x-openrouter-credit-remaining` read anywhere (Pitfall 5): `grep -cE 'response\.headers|x-openrouter-credit-remaining' ...` → 0. Cost is read exclusively from `getattr(usage, "cost", 0.0)` on the response body (line ~383)
- `result.data` is the canonical artifact only (ANLZ-06 / Pitfall 7): final `ToolResult(success=True, data=artifact, model=resp_model, cost_usd=cost_usd)` — no selector/provider/tool-name keys stamped onto `data`
- `OpenAI(api_key=...)` call passes the key EXPLICITLY (Pitfall 1 mitigation) with `base_url="https://openrouter.ai/api/v1"` as a literal string at line 551; `grep -c 'OpenAI(api_key=' ...` → 2 (module import reference and the actual call)
- `finish_reason == "length"` is a STRING compare (Pitfall 2): `grep -c '== "length"' ...` → 2; `grep -c 'FinishReason' ...` → 0 (zero references to any enum name — the Gemini-style pattern is not imported, not mentioned, not hinted at)
- `response_format={"type":"json_schema","json_schema":{"name":"video_analysis","schema":<flat>,"strict":True}}` on first attempt; `extra_body={"provider":{"require_parameters":True}}` only with structured path (Pitfall 4)
- Registry discovery verified: with `OPENROUTER_API_KEY` set, `registry.get_by_capability("video_analysis")` returns `['gemini_video_analyzer', 'openrouter_video_analyzer', 'video_analyzer_selector']`; selector's `_pick({'preferred_provider':'openrouter'}, ...)` returns the OpenRouter tool (zero selector code changes)

## Deviations from RESEARCH.md Code Examples

**None of substance.** Three cosmetic adjustments for grep-guard conformance, all documented inline in source comments:

1. **`OpenAI()` constructor on a single line** (plan Example 1 shows it multi-line). The plan's acceptance grep `grep -c 'OpenAI(api_key='` and `grep -c 'base_url="https://openrouter.ai/api/v1"'` require the literal on a single line. The `OPENROUTER_BASE_URL` constant is still declared at module scope for any future caller that wants to reuse it; the constructor call uses the literal string directly.
2. **`default_headers` assigned to a local variable** before the constructor call, so the one-line constructor remains readable. Semantically identical to Example 1.
3. **Docstring wording** — removed all mentions of the token "FinishReason" (used in Pitfall-2 explanatory prose in the plan). That token is now absent from the source so `grep -c 'FinishReason' ...` == 0 as required (it was a Gemini-specific enum name that has no runtime presence here; its absence is the entire point of Pitfall 2).

## Self-Check: PASSED

- `tools/analysis/openrouter_video_analyzer.py` exists (590 lines, > 280 required)
- `requirements.txt` contains `openai>=1.0,<3` on line 9
- Commit `341a047` exists on `main` (chore: requirements pin)
- Commit `efe9c6c` exists on `main` (feat: provider tool)
- `python3 -c "from tools.analysis.openrouter_video_analyzer import OpenRouterVideoAnalyzer; t=OpenRouterVideoAnalyzer(); print(t.name, t.provider)"` exits 0 and prints `openrouter_video_analyzer openrouter`
- `registry.discover()` picks up the tool; selector routes `preferred_provider="openrouter"` to it

## Known Stubs

None. Every line of the tool is wired to real behavior; the only "deferred" surface is the SKILL.md referenced via `agent_skills = ["openrouter-video-analysis"]`, which ships in plan 03-02.
