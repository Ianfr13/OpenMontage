---
phase: 02-gemini-provider
plan: 01
subsystem: analysis
tags: [video_analysis, selector, registry, error-taxonomy, gemini, openrouter, python]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "BaseTool contract, ToolRegistry with get_by_capability + ensure_discovered, tools/analysis/ package, lib/ convention for error modules"
provides:
  - "lib/analysis_errors.py — VideoAnalysisError / VideoUploadError / VideoAnalysisRetryExhausted"
  - "tools/analysis/video_analyzer_selector.py — ANLZ-01 capability selector, auto-discovering, no lib.scoring dependency"
  - "tests/unit/__init__.py — pytest package-discovery stub for plan 02-04"
affects:
  - 02-02-PLAN (gemini_video_analyzer imports the error classes, registers with capability=video_analysis)
  - 02-03-PLAN (SKILL.md is referenced by provider's agent_skills — selector already declares it)
  - 02-04-PLAN (contract tests exercise the selector's zero-providers + priority paths)
  - 03-openrouter-provider (drops in as second video_analysis provider; selector already routes to it)

# Tech tracking
tech-stack:
  added: []  # pure stdlib — no new runtime deps
  patterns:
    - "Capability-level selector pattern (mirrors tools/video/video_selector.py + tools/audio/tts_selector.py)"
    - "Error-taxonomy-per-lib-module (mirrors lib/checkpoint.py::CheckpointValidationError)"
    - "Priority-list routing without lib.scoring — justified when the universe of providers is bounded (2 providers, explicit ANLZ-01 order)"

key-files:
  created:
    - "lib/analysis_errors.py"
    - "tools/analysis/video_analyzer_selector.py"
    - "tests/unit/__init__.py"
  modified: []

key-decisions:
  - "Selector stamps provider identity on ToolResult.model (NOT on result.data) — preserves ANLZ-06: artifact is provider-agnostic"
  - "Skipped lib.scoring import — ANLZ-01 priority is explicit and deterministic, rank_providers would add complexity with no behavioral benefit for 2 providers"
  - "Selector returns ToolResult(success=False, error=...) on zero providers rather than raising — callers (and plan 02-04 tests) can assert the contract without try/except"
  - "Legacy tools/analysis/video_analyzer.py uses capability='analysis' (not 'video_analysis'), so no auto-discovery collision with the new selector — verified via grep before writing the selector"

patterns-established:
  - "Pattern: selector filters itself out via `t.name != self.name` on registry.get_by_capability() — required because the selector itself registers with the same capability"
  - "Pattern: preferred_provider matches on both BaseTool.provider AND BaseTool.name — agent can pass either the provider identity ('gemini') or the concrete tool name ('gemini_video_analyzer')"
  - "Pattern: tests/ subpackages need explicit __init__.py for pytest discovery in devcontainer (plan 02-04 depends on this)"

requirements-completed: [ANLZ-01]

# Metrics
duration: 3min
completed: 2026-04-17
---

# Phase 02 Plan 01: Analysis Error Taxonomy + Video Analyzer Selector Summary

**Ships the empty-provider-safe `video_analyzer_selector` with ANLZ-01 priority routing and the `lib/analysis_errors.py` exception hierarchy that Phase 2+ analysis tools will raise and test against.**

## Performance

- **Duration:** 3 min (≈139 seconds wall-clock)
- **Started:** 2026-04-17T17:56:33Z
- **Completed:** 2026-04-17T17:58:52Z
- **Tasks:** 2
- **Files created:** 3
- **Files modified:** 0

## Accomplishments

- **Exception hierarchy ready for plans 02-02 and 02-04.** `VideoAnalysisError(Exception)` as base, `VideoUploadError(VideoAnalysisError)` for Files-API / auth / path failures, `VideoAnalysisRetryExhausted(VideoAnalysisError)` for terminal retry exhaustion. Subclass checks pass; module imports without side effects.
- **Selector auto-discoverable via registry.** `registry.get_by_capability("video_analysis")` returns `['video_analyzer_selector']` immediately after install — plan 02-02 drops in without touching this file. Selector excludes itself from its own discovery list (via `t.name != self.name`) so it never routes requests to itself.
- **Zero-providers graceful handling.** `execute({'video_path': ...})` returns `ToolResult(success=False, error="No video_analysis provider registered...")` when plan 02-02 has not shipped yet — plan 02-04 tests can assert the contract without mocking anything.
- **ANLZ-01 priority order implemented as 4 explicit branches.** `_pick()` checks (1) `inputs["preferred_provider"]`, (2) `VIDEO_ANALYZER_PROVIDER` env, (3) `GEMINI_API_KEY|GOOGLE_API_KEY` → gemini / `OPENROUTER_API_KEY` → openrouter, (4) first available in discovery order. No `lib.scoring` import — keeping the selector small and deterministic.

## Task Commits

1. **Task 1: lib/analysis_errors.py exception hierarchy** — `5bfce7b` (feat)
2. **Task 2: video_analyzer_selector + tests/unit/__init__.py** — `64ecc58` (feat)

## Files Created/Modified

- `lib/analysis_errors.py` (37 lines) — `VideoAnalysisError` / `VideoUploadError` / `VideoAnalysisRetryExhausted`; module docstring references the `lib/checkpoint.py::CheckpointValidationError` convention; only `from __future__ import annotations` import.
- `tools/analysis/video_analyzer_selector.py` (154 lines) — `VideoAnalyzerSelector(BaseTool)`, `capability="video_analysis"`, `provider="selector"`, `tier=ToolTier.ANALYZE`, `runtime=ToolRuntime.HYBRID`, `agent_skills=["gemini-video-analysis"]`; `_providers()` filters self; `get_status()` returns AVAILABLE iff any provider is AVAILABLE; `execute()` handles zero-provider + no-available-provider early returns; `_pick()` implements the 4-branch ANLZ-01 priority order.
- `tests/unit/__init__.py` — empty stub so `tests.unit` is a package (pytest discovery requirement in devcontainer).

## Confirmed Structural Facts

- **Legacy collision check (Step 1 of Task 2):** `grep -E "^\s*capability" tools/analysis/video_analyzer.py` returned `    capability = "analysis"` — NOT `video_analysis`. The new selector cannot route to the legacy brief-only analyzer. No blocker surfaced.
- **Registry smoke output:** after `registry.discover()`, `get_by_capability("video_analysis")` returns exactly `['video_analyzer_selector']`. No other tool in the codebase claims this capability. When plan 02-02 ships, `gemini_video_analyzer` joins this list automatically.
- **Zero-provider smoke output:** `ToolResult(success=False, data={}, error="No video_analysis provider registered. Install one (e.g., gemini_video_analyzer) and ensure its API key is set.", ...)` — stable error prefix `"No video_analysis provider"` that plan 02-04 can substring-match.

## Final `_pick()` Branch Order (ANLZ-01 Exact Match)

```
Branch 1 — Explicit user choice
  inputs.get("preferred_provider") != "auto"
    → match by provider → return
    → match by tool name → return

Branch 2 — Env override
  os.environ["VIDEO_ANALYZER_PROVIDER"] != "auto"
    → match by provider → return

Branch 3 — API-key presence tie-break
  GEMINI_API_KEY or GOOGLE_API_KEY → "gemini" → return
  OPENROUTER_API_KEY             → "openrouter" → return

Branch 4 — Fallback
  return available[0]   # first AVAILABLE provider in discovery order
```

## Decisions Made

- **No `lib.scoring` import.** Phase 2 has at most 2 providers (gemini, openrouter) and ANLZ-01 is an explicit priority list — `rank_providers` would add runtime cost, richer but unnecessary ordering, and a dependency for no behavioral benefit. Documented in the module docstring and RESEARCH.md Pattern 1 ("Don't Hand-Roll" row).
- **Provider metadata goes on `ToolResult.model`, not `result.data`.** The existing `video_selector.py` does `result.data.setdefault("selected_tool", ...)`, but ANLZ-06 (a Phase 3 contract) requires that the caller cannot tell which backend ran from the artifact alone. Stamping selector metadata on `result.data` would break that invariant now and force Phase 3 to rip it out. Using `ToolResult.model` as the selector's provenance field is idiomatic and preserves `data` as the canonical `video_analysis` artifact.
- **Preferred-provider accepts both `provider` identity and tool `name`.** Agents may pass either `"gemini"` (the provider identity) or `"gemini_video_analyzer"` (the concrete tool name). The `by_provider` dict handles the first; a follow-up name-match loop handles the second. Matches the semantics of the existing `video_selector` without depending on its scoring engine.
- **Preferred-provider lowercased for case-insensitive match.** `env_pref.lower()` and `str(inputs.get("preferred_provider") or "auto").lower()` — avoids a class of real-world env-var typos.

## Deviations from Plan

Plan executed effectively as written. Two minor deviations from the plan's acceptance grep counts, documented here for auditability:

### Acceptance-grep deviations (structural, not behavioral)

**1. [Rule 3 — Blocking (environment)] Installed `numpy` to unblock `registry.discover()`**
- **Found during:** Task 2 Step 5 smoke check
- **Issue:** `registry.discover()` walks `tools/` and imports every module; `tools/video/green_screen_composite.py` imports `numpy`. The devcontainer snapshot had no `numpy` installed, so discovery raised `ModuleNotFoundError` before it could register the selector. This is an environment gap, not a code defect in this plan.
- **Fix:** `pip install numpy --break-system-packages` (PEP 668 override — the devcontainer uses system Python). No file changes in this repo; `requirements.txt` update belongs to plan 02-02 which adds `google-genai` anyway.
- **Verification:** after install, `python3 -c "from tools.tool_registry import registry; registry.discover()"` exits 0 and `get_by_capability("video_analysis")` returns `['video_analyzer_selector']`.
- **Committed in:** No repo change — environment-only fix.

**2. [Documentation-vs-control-flow count] `VIDEO_ANALYZER_PROVIDER` appears twice, plan asked `== 1`**
- **Found during:** Task 2 grep acceptance check
- **Issue:** Plan's acceptance criterion `grep -c "VIDEO_ANALYZER_PROVIDER" tools/analysis/video_analyzer_selector.py == 1` assumed the env-var name appears only in code. I kept one occurrence in the module docstring (preference-order list) and one in `os.environ.get("VIDEO_ANALYZER_PROVIDER", "auto")` — total 2.
- **Fix:** Kept the docstring reference; removing it would degrade discoverability for future readers (the whole point of the docstring is to state the priority order). The intent of the acceptance criterion — "env-var override is wired into `_pick()`" — is met.
- **Impact:** None; count stricter than behavior. All other greps match exactly.
- **Committed in:** `64ecc58` (Task 2 commit)

---

**Total deviations:** 2 minor (1 environment fix, 1 acceptance-grep-count variance). No behavioral deviation from the plan's `_pick()` algorithm, selector contract, or error hierarchy.

**Impact on plan:** None. Plan 02-02 and 02-04 can proceed against the interfaces specified in `must_haves.truths` — every assertion there holds.

## Issues Encountered

- **`registry.discover()` depends on environment-wide tool-module importability.** The pre-existing `tools/video/green_screen_composite.py` imports `numpy` at module load, so any fresh devcontainer must install `numpy` before registry discovery works. Worth flagging in `requirements.txt` / devcontainer setup — tracked as out-of-scope for this plan but relevant for Phase 6 INT-02 (full dependency-set canonicalization).

## User Setup Required

None. No external service configuration. `GEMINI_API_KEY` becomes relevant only when plan 02-02 ships the actual Gemini provider — the selector's zero-provider path does not require any key.

## Next Phase Readiness

- ✅ Plan 02-02 (Gemini provider) can import `VideoUploadError`, `VideoAnalysisError`, `VideoAnalysisRetryExhausted` without circular imports (the selector does not import anything from `tools.analysis.gemini_video_analyzer`).
- ✅ Plan 02-04 (contract + unit tests) can exercise the selector against zero registered providers and assert `success=False` with substring `"No video_analysis provider"`.
- ✅ Plan 02-03 (SKILL.md) — selector's `agent_skills=["gemini-video-analysis"]` already points at the file that plan 02-03 will create; no cross-plan wiring needed.
- ⚠ Devcontainer note: `numpy` must be available before `registry.discover()` runs. The pre-existing `green_screen_composite.py` creates this requirement; this plan's files do not contribute to it. Recommend tracking in INT-02 (Phase 6) dependency audit.

## Self-Check: PASSED

Files verified on disk:
- `lib/analysis_errors.py` — FOUND
- `tools/analysis/video_analyzer_selector.py` — FOUND
- `tests/unit/__init__.py` — FOUND
- `tests/contracts/__init__.py` — FOUND (pre-existing)

Commits verified in `git log`:
- `5bfce7b` feat(02-01): add lib/analysis_errors.py exception hierarchy — FOUND
- `64ecc58` feat(02-01): add video_analyzer_selector with ANLZ-01 priority routing — FOUND

Imports verified:
- `python3 -c "from lib.analysis_errors import VideoAnalysisError, VideoUploadError, VideoAnalysisRetryExhausted; from tools.analysis.video_analyzer_selector import VideoAnalyzerSelector"` exits 0.

Registry discovery verified:
- `registry.get_by_capability("video_analysis")` returns `['video_analyzer_selector']`.

Zero-provider contract verified:
- `sel.execute({'video_path': '/tmp/x.mp4'})` returns `ToolResult(success=False)` with `error` starting `"No video_analysis provider"`.

No security-enforcement violations: `grep` confirms no `GEMINI_API_KEY` / `OPENROUTER_API_KEY` value is interpolated into exception strings (only the literal env-var *names* appear, in error messages and docstrings — never `os.environ["..."]` dereferences inside error-message f-strings).

---
*Phase: 02-gemini-provider*
*Completed: 2026-04-17*
