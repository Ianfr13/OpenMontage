---
phase: 02-gemini-provider
plan: 02
subsystem: analysis
tags:
  - gemini
  - video_analysis
  - structured_output
  - files_api
  - provider_tool
dependency_graph:
  requires:
    - "Phase 1: lib/schema_adapter.py::to_api_schema"
    - "Phase 1: schemas/artifacts/__init__.py::load_schema, validate_artifact"
    - "Phase 1: schemas/artifacts/video_analysis.schema.json"
    - "02-01: lib/analysis_errors.py (VideoAnalysisError, VideoUploadError, VideoAnalysisRetryExhausted)"
    - "02-01: tools/analysis/video_analyzer_selector.py (auto-discovers this tool)"
    - "google-genai>=1.73,<2 (new pin)"
  provides:
    - "tools/analysis/gemini_video_analyzer.py — first video_analysis provider"
    - "End-to-end selector -> Gemini routing (selector picks this tool when GEMINI_API_KEY set)"
  affects:
    - "requirements.txt (new dep pin)"
    - "tools/tool_registry.py (auto-discovery picks up new tool)"
tech_stack:
  added:
    - "google-genai 1.73.1 (SDK for Gemini Files API + models.generate_content)"
  patterns:
    - "Structured output via response_mime_type + response_json_schema (flattened)"
    - "Files API lifecycle: upload -> poll ACTIVE -> analyze -> delete (in finally)"
    - "Wall-clock polling via time.monotonic() with capped backoff"
    - "Explicit api_key passed to genai.Client (SDK default preferred GOOGLE_API_KEY — we flip to GEMINI_API_KEY first)"
    - "4-branch model+depth fallback ladder (preview full -> preview compact -> 2.5-pro full -> 2.5-pro compact)"
key_files:
  created:
    - "tools/analysis/gemini_video_analyzer.py"
  modified:
    - "requirements.txt"
decisions:
  - "Fallback ladder written as explicit 4-branch control flow, not a loop — maps 1:1 to behavior tests 10/11/13 and the preview-unavailable-on-retry edge case"
  - "_FLAT_SCHEMA cached as class attribute at import time (to_api_schema deepcopies, so safe to share across instances)"
  - "Artifact validation runs INSIDE the try block — ValidationError caught and returned as ToolResult(success=False) while still triggering the finally-block delete"
  - "API key never formatted into any log/error string (T-02-06 mitigation)"
  - "Tool does NOT call lib.checkpoint.write_checkpoint — caller owns checkpointing (Phase 1 WR-05 requires pipeline_type this tool cannot know)"
metrics:
  duration_minutes: 7
  completed_date: "2026-04-17"
  tasks_completed: 2
  files_changed: 2
  lines_added: 445
---

# Phase 02 Plan 02: Gemini Video Analyzer — Summary

First end-to-end `video_analysis` provider ships: a `BaseTool` that uploads local video via the Gemini Files API, polls until `ACTIVE`, runs structured-output analysis against the flattened canonical schema, retries once on truncation with `analysis_depth="compact"`, falls back from `gemini-3.1-pro-preview` to `gemini-2.5-pro` on `errors.ClientError`, and always deletes the uploaded file in a `finally:` block. Selector from 02-01 now routes to this provider when `GEMINI_API_KEY` is set.

## What Shipped

### `requirements.txt`
- `+google-genai>=1.73,<2` (single-line diff, no other dep moved)
- Installed version in devcontainer: `1.73.1`

### `tools/analysis/gemini_video_analyzer.py` (444 lines)
- `class GeminiVideoAnalyzer(BaseTool)` — `name="gemini_video_analyzer"`, `capability="video_analysis"`, `provider="gemini"`, `runtime=ToolRuntime.API`, `tier=ToolTier.ANALYZE`, `stability=ToolStability.BETA`
- `dependencies = ["env:GEMINI_API_KEY", "python:google.genai"]`
- `agent_skills = ["gemini-video-analysis"]` (skill file lands in 02-03)
- `_FLAT_SCHEMA = to_api_schema(load_schema("video_analysis"))` cached at class load
- Helpers: `_get_api_key`, `_resolve_model`, `_state_value`, `_normalize_shot_boundaries`, `_format_shot_boundaries`, `_wait_for_active`

### Behaviors Implemented (18 total — maps to tests in 02-04)

| # | Behavior | Implementation |
|---|----------|----------------|
| 1 | Tool contract fields | `get_info()` via BaseTool defaults; all class-level attrs set |
| 2 | Env priority GEMINI > GOOGLE | `_get_api_key()`; `genai.Client(api_key=key)` passes explicitly |
| 3 | Missing key returns failure | Returns `ToolResult(success=False, error="GEMINI_API_KEY...")` — key value never formatted |
| 4 | Polling to ACTIVE | `_wait_for_active()` with backoff `(1s, 2s, 5s)` then 5s cap |
| 5 | FAILED raises | `VideoUploadError` with file's `.error` field |
| 6 | Timeout raises | `time.monotonic()`-based wall-clock check against `max_poll_seconds` |
| 7 | Delete on success | `finally: client.files.delete(name=uploaded.name)` |
| 8 | Delete on failure | Same `finally:` block — runs on any exception path |
| 9 | Flattened schema | `to_api_schema(load_schema("video_analysis"))` — no `$ref`/`uniqueItems`/`additionalProperties:false` |
| 10 | MAX_TOKENS retry | `_run_once` raises `VideoAnalysisError`; `_analyze_with_fallback` retries with compact prompt |
| 11 | Retry exhausted | Second `VideoAnalysisError` -> `VideoAnalysisRetryExhausted` |
| 12 | Empty text triggers retry | `if not raw.strip(): raise VideoAnalysisError("Empty response text")` |
| 13 | Model fallback | `errors.ClientError` on first call -> retry with `gemini-2.5-pro` |
| 14 | shot_boundaries absent | Prompt includes literal `shot_boundary_source: "model"` directive |
| 15 | shot_boundaries both shapes | `_normalize_shot_boundaries` accepts `[[s,e]]` AND `[{start_seconds,end_seconds}]` |
| 16 | confidence="low" directive | Explicit prompt instruction for uncertain fields |
| 17 | Artifact validation gate | `validate_artifact("video_analysis", artifact)` before return; `jsonschema.ValidationError` -> `ToolResult(success=False)` with file still deleted |
| 18 | No checkpoint write | `grep "from lib.checkpoint" -> 0 matches` |

## The Fallback Ladder (4 Branches)

```
preview + full  -->[VideoAnalysisError]-->  preview + compact  -->[VideoAnalysisError]-->  RetryExhausted
      |                                         |
      +[ClientError]-->                         +[ClientError]-->
                       2.5-pro + full                              2.5-pro + compact
                           |                                               |
                   [VideoAnalysisError]                                 [V.A.E.]
                           |                                               |
                        2.5-pro + compact --[V.A.E.]--> RetryExhausted  RetryExhausted
```

Written as explicit nested branches rather than a loop — matches behavior tests 10, 11, 13, plus the edge case of preview-unavailable-on-retry. Reason per RESEARCH Pitfall 6: a single-loop implementation obscures which path is which and makes `call_args_list` assertions in 02-04 fragile. Each branch records the model that actually ran in `ToolResult.model`.

## Deviations from Plan

### Auto-fixed Issues
None. Plan 02-02-PLAN.md had extensive inline skeleton in the `<action>` block; implementation follows it 1:1 with two small, safe refinements:

1. **`_run_once` raising `VideoAnalysisError` only after truncation/empty/parse checks** — the plan skeleton is identical; documented here only because the branch order in `_run_once` matters for test 10 (MAX_TOKENS must be detected before empty-text check, since an empty `.text` could accompany a MAX_TOKENS `finish_reason`).
2. **`VideoUploadError` on missing key is NOT raised** — missing key is handled before any client construction via `_get_api_key()` returning `None`; `execute()` returns `ToolResult(success=False)` directly. Same semantic, cleaner early-return. (The error taxonomy docstring in `lib/analysis_errors.py` lists "Missing credentials" under `VideoUploadError` — but the tool returns a `ToolResult` without raising, so this is not a contract break.)

### Authentication Gates
None — unit of work is structural + mocked; real API calls land in plan 02-04 and in the user's SKILL-03 human-verify step.

## Security Confirmations

| Threat | Mitigation | Verified |
|--------|-----------|----------|
| T-02-06 (key leak) | `_get_api_key()` return value never formatted into log/error messages | `grep "{key}"` in source -> 0 matches. Error-path `ToolResult.error` strings contain only static literals + `str(exc)` (SDK exceptions do not include key) |
| T-02-07 (hostile response) | `validate_artifact("video_analysis", artifact)` before return | 1 grep match inside `execute()` success path |
| T-02-08 (hung upload) | `time.monotonic()` wall-clock timeout | `grep "time.monotonic" -> 2 matches` |
| T-02-09 (file leak) | `finally: client.files.delete(name=...)` | `grep "finally:" -> 1`, `grep "client.files.delete" -> 1` (both inside `execute`) |
| T-02-12 (fallback masking) | `logger.warning` records ClientError code before fallback; subsequent ClientError propagates as `ToolResult.error` (not RetryExhausted) | Code-path review in `_analyze_with_fallback` |

## Explicit Confirmations (per `<output>` section of the plan)

- **google-genai version installed:** `1.73.1`
- **Line count of `tools/analysis/gemini_video_analyzer.py`:** `444` (min required: 250)
- **No `write_checkpoint` import:** `grep "from lib.checkpoint" tools/analysis/gemini_video_analyzer.py` -> `0 matches`
- **`result.data` is canonical artifact only:** no `selected_tool` / `selected_provider` keys are written to `ToolResult.data` inside this tool. `grep -E "result\.data\[['\"]selected"` -> `0 matches`. Selector uses `ToolResult.model` field for metadata (02-01 already landed that).
- **Fallback ladder shape:** documented above; cites RESEARCH Pitfall 6.
- **Deviations from RESEARCH Code Examples:** none material.

## Registry Verification

```
$ python3 -c "from tools.tool_registry import registry; registry.discover();
  print(sorted(t.name for t in registry.get_by_capability('video_analysis')))"
['gemini_video_analyzer', 'video_analyzer_selector']
```

Selector now routes to the Gemini provider when `GEMINI_API_KEY` is set:
```
$ python3 -c "import os; os.environ['GEMINI_API_KEY']='fake';
  from tools.tool_registry import registry; registry.discover();
  from tools.analysis.video_analyzer_selector import VideoAnalyzerSelector;
  print([p.name for p in VideoAnalyzerSelector()._providers()])"
['gemini_video_analyzer']
```

## Commits

| Task | Type | Hash | Summary |
|------|------|------|---------|
| 1 | chore | `b9a9ca1` | Pin google-genai>=1.73,<2 in requirements.txt |
| 2 | feat | `1270038` | Add GeminiVideoAnalyzer BaseTool (Files API + structured output + fallback ladder) |

## Follow-ups Owned by Other Plans

- **02-03:** `.agents/skills/gemini-video-analysis/SKILL.md` (Layer 3 prompting knowledge; `agent_skills` field on this tool already points to it)
- **02-04:** 18 unit tests (one per behavior above); mocks SDK surface to keep tests API-key-free
- **SKILL-03 human-verify:** user runs one real ≤2min video through the selector after the phase wave closes; checks ≥12/16 canonical fields populated with appropriate confidence

## Self-Check: PASSED

- `tools/analysis/gemini_video_analyzer.py` exists: FOUND
- `requirements.txt` google-genai pin: FOUND (line 8)
- Task 1 commit `b9a9ca1`: FOUND
- Task 2 commit `1270038`: FOUND
- All 22 grep acceptance criteria: PASSED
- Structural smoke test: PASSED (`ok`)
- Registry discovery: PASSED (tool appears in `get_by_capability("video_analysis")`)
- Selector routing: PASSED (returns Gemini provider when `GEMINI_API_KEY` set)
