# Phase 2: Gemini Provider — Research

**Researched:** 2026-04-17
**Domain:** Gemini SDK (google-genai) video understanding — Files API upload + polling + structured output + Layer 3 SKILL.md + capability selector
**Confidence:** HIGH (SDK shape verified against installed google-genai 1.73.1 source; repo patterns verified against actual file reads; one MEDIUM-confidence item flagged in Open Questions)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Plan Decomposition (4 parallel plans, mirroring Phase 1 shape):**
- `02-01-PLAN.md` — selector + error classes (`lib/analysis_errors.py`: `VideoUploadError`, `VideoAnalysisError`; `tools/analysis/video_analyzer_selector.py` auto-discovers via `registry.get_by_capability("video_analysis")`; preference order: explicit → `GEMINI_API_KEY` → `OPENROUTER_API_KEY` → first available)
- `02-02-PLAN.md` — `tools/analysis/gemini_video_analyzer.py` (Files API upload + ACTIVE polling + generate_content + structured output + retry + delete)
- `02-03-PLAN.md` — `.agents/skills/gemini-video-analysis/SKILL.md` + `agent_skills` field wiring on the provider tool
- `02-04-PLAN.md` — Contract tests (selector preference logic, artifact schema validation) + unit tests (mocked Files API, retry paths, error taxonomy) — all API-key-free

**Provider Tool Shape (GEM-01..05, ANLZ-04, ANLZ-05):**
- `BaseTool` subclass, `capability="video_analysis"`, `provider="gemini"`, `runtime=ToolRuntime.API`
- Auth: `GEMINI_API_KEY` primary, `GOOGLE_API_KEY` fallback (both via `os.getenv`) — **see Finding 1 in this doc: this CONTEXT ordering conflicts with the SDK default; the tool MUST pass api_key explicitly to enforce this ordering.**
- Model: `GEMINI_VIDEO_MODEL` env (default `gemini-3.1-pro-preview`, fallback `gemini-2.5-pro` if preview raises model-not-available)
- Files API: `client.files.upload(path)` → poll `get(file.name).state == "ACTIVE"` with exponential backoff (1s → 2s → 5s → 5s cap, 300s max wall; configurable via `max_poll_seconds` param)
- Structured output: `response_mime_type="application/json"` + `response_json_schema=to_api_schema(load_schema("video_analysis"))` (uses Phase 1 adapter)
- On null/truncated (empty string, `MAX_TOKENS` finish reason, or parse failure): one retry with `analysis_depth="compact"` appended to prompt → if still broken, raise `VideoAnalysisError`
- On `FAILED` upload state or 300s timeout: raise `VideoUploadError`
- `finally:` block ensures `client.files.delete(file.name)` runs after analysis (success OR failure) — upload-side isolation per GEM-03
- Optional `shot_boundaries` input (list of `[start, end]` tuples from `scene_detect`); when absent, artifact sets `shot_boundary_source: "model"` (ANLZ-05)
- Missing/uncertain fields: provider writes explicit `{value: ..., confidence: "low"}` on the dimension confidence-map rather than null/absent (ANLZ-04)
- `agent_skills=["gemini-video-analysis"]` (bare skill name, matches existing convention — see Finding 7)

**Selector Shape (ANLZ-01):**
- Mirror `tools/video/video_selector.py` + `tools/audio/tts_selector.py`
- `capability="video_analysis"`, `provider="selector"`, auto-discover via `registry.get_by_capability("video_analysis")` excluding self
- Preference order: `input.preferred_provider` (explicit) > env `VIDEO_ANALYZER_PROVIDER` > first tool with required env var set (Gemini first if both keys present) > first available
- Pass-through inputs: `video_path`, `shot_boundaries?`, `analysis_depth?` (enum `full` | `compact`, default `full`)
- Return shape: identical to underlying provider — caller cannot tell which backend was used (ANLZ-06 preview; final test lands in Phase 3)

**SKILL-03 Quality Gate Strategy:**
- Phase 2 execute completes with code + unit tests + SKILL.md landed; `phase_close_requires_human_verification: true` for SKILL-03
- VERIFICATION.md flags SKILL-03 as `human_needed` with: "Run one real <2min video through the selector; confirm ≥12 of 16 canonical fields are populated with appropriate confidence; confirm pacing_style and dominant_visual_style enums are correct"

**Error Taxonomy:**
- New module `lib/analysis_errors.py`:
  - `class VideoAnalysisError(Exception)` — base
  - `class VideoUploadError(VideoAnalysisError)` — upload failures (FAILED state, timeout, unsupported format)
  - `class VideoAnalysisRetryExhausted(VideoAnalysisError)` — null/truncated response after retry

**Dependencies:**
- Add `google-genai>=1.73` to `requirements.txt` in 02-02 (Phase 6 INT-02 finalizes full dep set including `openai` and `ruamel.yaml`)

### Claude's Discretion
- Exact polling backoff curve (1s→2s→5s→5s is a suggestion; planner may tune)
- Whether to emit structured logging (stdlib `logging`) during polling — planner's call
- Whether to support `analysis_depth="compact"` as user-facing input OR only as internal retry mode — recommend internal-only for v2.0
- Whether to inline the flattened schema at tool init time (cached) or re-flatten each call — recommend cached at class load

### Deferred Ideas (OUT OF SCOPE)
- Cost estimation surface from inside the tool (Phase 4 CHUNK-06)
- Streaming response parsing (out of v2.0 scope)
- Gemini CLI provider (v2.1 PROV-01)
- Claude/Anthropic provider (v2.1 PROV-02)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GEM-01 | `gemini_video_analyzer.py` exists as BaseTool, provider="gemini", GEMINI_API_KEY auth, GEMINI_VIDEO_MODEL env with fallback | Finding 1 (auth priority), Finding 3 (model fallback error) |
| GEM-02 | Files API upload → poll ACTIVE → pass to generate_content; max_poll_wait configurable; VideoUploadError on FAILED/timeout | Finding 2 (state machine + polling loop) |
| GEM-03 | Delete uploaded file after analysis (48h auto-delete insufficient) | Finding 2 (delete signature), Finding 4 (finally pattern) |
| GEM-04 | `response_mime_type="application/json"` + `response_json_schema=<flattened>`; detect null/truncated; retry once with `analysis_depth="compact"` before raising | Finding 3 (GenerateContentConfig shape), Finding 5 (FinishReason enum + detection) |
| GEM-05 | `agent_skills` field references Layer 3 Gemini skill | Finding 7 (existing convention) |
| ANLZ-01 | `video_analyzer_selector.py` with capability="video_analysis"; registry auto-discovery; explicit > GEMINI > OPENROUTER > first-available | Finding 6 (selector template), code_context Selector Shape |
| ANLZ-04 | ToolResult with validated artifact; uncertain fields set `confidence: "low"` | Finding 8 (confidence map shape, schema_adapter behavior) |
| ANLZ-05 | Optional `shot_boundaries` input; when absent `shot_boundary_source: "model"` | Finding 9 (scene_detect output shape) |
| SKILL-01 | `.agents/skills/gemini-video-analysis/SKILL.md` exists with prompting per dimension, Files API quirks, 5-min timecode warning, structured-output block | Finding 10 (skill template pattern) |
| SKILL-03 | Field-level quality review gates phase close | Validation Architecture section — manual-only verification |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

CLAUDE.md routes to `AGENT_GUIDE.md`. Directives that apply to this phase:

1. **Layer 3 skill pattern is mandatory** — every generation/analysis tool must have a Layer 3 skill (`.agents/skills/<name>/SKILL.md`) referenced in its `agent_skills` field. The agent reads the skill before calling the tool. SKILL-01 fulfills this for Gemini.
2. **Tools live in `tools/<domain>/`** — `gemini_video_analyzer.py` and `video_analyzer_selector.py` land in `tools/analysis/`, alongside the existing `video_analyzer.py`, `scene_detect.py`, etc.
3. **Selectors auto-discover from the registry** — never hardcode provider lists. Selectors use `registry.get_by_capability(...)` and filter out themselves.
4. **All tools inherit from `BaseTool`** and expose `execute(inputs) -> ToolResult`. Do NOT add `.run()`.
5. **Tool class naming:** PascalCase without "Tool" suffix. `GeminiVideoAnalyzer` and `VideoAnalyzerSelector` (NOT `GeminiVideoAnalyzerTool`).
6. **`.env` is auto-loaded** by `tools/base_tool.py::_load_dotenv()` at import time (tools/base_tool.py:23-51). Tests that monkeypatch env vars do so AFTER import.
7. **Do not bypass the pipeline / checkpoint flow** — the tool returns a `ToolResult` with a validated artifact. The *caller* (meta skill / orchestrator) writes the checkpoint. The Phase 2 tool MUST NOT call `write_checkpoint` itself (see Finding 8 in this doc).

---

## Summary

Phase 2 delivers the first end-to-end `video_analysis` path by shipping three artifacts alongside tests:

1. **`video_analyzer_selector`** — a thin, registry-driven selector mirroring the shape of `tools/video/video_selector.py` and `tools/audio/tts_selector.py`. Auto-discovers any `BaseTool` with `capability="video_analysis"` and routes per the preference order in ANLZ-01. Since only one provider exists in Phase 2, the selector's routing logic is trivial to test but must be correct now because Phase 3 will slot OpenRouter into the same machinery without changing the selector.
2. **`gemini_video_analyzer`** — the first provider. Uses `google-genai>=1.73` (verified installable; latest is 1.73.1 published ~February 2026). The critical machinery: `client.files.upload(file=path)` returns a `types.File` object whose `.state` moves PROCESSING → ACTIVE (or PROCESSING → FAILED). The SDK provides NO built-in polling helper, so the tool owns the while-loop. Structured output uses `GenerateContentConfig(response_mime_type="application/json", response_json_schema=<flattened schema>)` — the Phase 1 `to_api_schema` adapter produces exactly the right shape. Truncation is detected by `response.candidates[0].finish_reason == FinishReason.MAX_TOKENS` (or empty/unparseable `.text`). Cleanup uses `client.files.delete(name=file.name)` in a `finally:` block.
3. **`.agents/skills/gemini-video-analysis/SKILL.md`** — a Layer 3 skill documenting Gemini-specific prompting per dimension. Templates to mirror: `.agents/skills/elevenlabs/SKILL.md` (has API-call examples + per-setting guidance) and `.agents/skills/ai-video-gen/SKILL.md` (gateway-level routing guidance). SKILL-03 mandates a field-level quality review gate — this is manual-only and fires at phase close.

**Primary recommendation:** Treat this phase as **"three files + mocked tests + one manual gate"**. Every SDK boundary can be mocked cleanly because the SDK exposes six discrete calls (`Client()`, `files.upload`, `files.get`, `files.delete`, `models.generate_content`, response object access). The only real risk is the `GOOGLE_API_KEY` vs `GEMINI_API_KEY` priority inversion (Finding 1) — passing `api_key` explicitly to `Client()` bypasses it entirely.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `google-genai` | `>=1.73,<2` | Official Google SDK for Gemini API + Files API + structured output | [VERIFIED: pypi `pip3 index versions google-genai` → 1.73.1 latest, installed ok in this session]. This is the current SDK (replaces deprecated `google-generativeai`). Every Gemini video example in Google's docs uses it. |
| `jsonschema` | `>=4.20` (already in requirements.txt) | Validate the returned artifact against `schemas/artifacts/video_analysis.schema.json` | [VERIFIED: requirements.txt line 4]. Phase 1 already uses it via `schemas/artifacts/__init__.py::validate_artifact`. |
| `pytest` | `>=7` (already in dev deps per Phase 1) | Test framework for contract + unit tests | [VERIFIED: Phase 1 tests under `/workspace/tests/contracts/` use `pytest`]. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest.monkeypatch` | stdlib of pytest | Monkeypatch env vars + SDK classes in tests | Every unit test touching GEMINI_API_KEY or the SDK client |
| `unittest.mock.MagicMock` + `patch` | stdlib | Mock the genai.Client + files + models surfaces | All SDK mocking |
| `pathlib.Path` | stdlib | File path manipulation for uploads | Upload call |
| `logging` (stdlib) | stdlib | Optional structured logging during the polling loop (Claude's discretion) | See CONTEXT |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `google-genai` SDK | `google-generativeai` (legacy) | Deprecated — do NOT use. Migration complete since 2024. |
| `google-genai` SDK | Raw HTTP + `requests` | Loses File object typing, loses error taxonomy, loses `response.parsed`. Not worth it. |
| `google-genai` Gemini API auth | Vertex AI backend (`Client(vertexai=True, project=..., location=...)`) | Requires GCP setup; out of scope for v2.0 (REQUIREMENTS.md "Out of Scope" — Gemini CLI ruled out, and Vertex is implicitly not in the env matrix). Direct Gemini API via API key is the sole Phase 2 path. |

**Installation:**
```bash
pip install 'google-genai>=1.73,<2'
```

**Version verification:** [VERIFIED in this research session]
- `pip3 index versions google-genai` → latest 1.73.1
- `python3 -c "from google import genai; print(genai.__version__)"` → `1.73.1`
- Installed cleanly alongside stdlib + pydantic 2 + jsonschema 4 (which requirements.txt already pins); no conflicts observed.

---

## Architecture Patterns

### Recommended File Layout

```
tools/analysis/
├── gemini_video_analyzer.py            # NEW — provider (GEM-01..05, ANLZ-04/05)
├── video_analyzer_selector.py          # NEW — capability-level router (ANLZ-01)
├── video_analyzer.py                   # existing legacy brief-only analyzer (untouched)
├── scene_detect.py                     # existing — produces optional shot_boundaries (ANLZ-05)
└── __init__.py                         # existing — no changes needed (tool_registry auto-walks the package)

lib/
└── analysis_errors.py                  # NEW — VideoAnalysisError, VideoUploadError, VideoAnalysisRetryExhausted

.agents/skills/gemini-video-analysis/
└── SKILL.md                            # NEW (SKILL-01)

tests/
├── contracts/
│   └── test_phase2_contracts.py        # NEW — selector preference logic, artifact schema validation
├── unit/
│   └── test_gemini_video_analyzer.py   # NEW — mocked SDK, Files API state machine, retry paths
```

### Pattern 1: Selector (auto-discovering, no hardcoded provider list)

**Source:** `tools/video/video_selector.py` (existing, verified) lines 97-102 + `tools/audio/tts_selector.py` lines 87-92.

```python
# tools/analysis/video_analyzer_selector.py (sketch)
from __future__ import annotations
import os
from typing import Any
from tools.base_tool import BaseTool, ToolResult, ToolRuntime, ToolStability, ToolStatus, ToolTier


class VideoAnalyzerSelector(BaseTool):
    name = "video_analyzer_selector"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "video_analysis"
    provider = "selector"
    stability = ToolStability.BETA
    runtime = ToolRuntime.HYBRID
    agent_skills = ["gemini-video-analysis"]  # grows to include openrouter-video-analysis in Phase 3

    input_schema = {
        "type": "object",
        "required": ["video_path"],
        "properties": {
            "video_path": {"type": "string"},
            "shot_boundaries": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2, "maxItems": 2,
                },
                "description": "Optional [[start_s, end_s], ...] from scene_detect. When omitted, provider infers and sets shot_boundary_source='model'.",
            },
            "analysis_depth": {
                "type": "string", "enum": ["full", "compact"], "default": "full",
            },
            "preferred_provider": {
                "type": "string",
                "description": "Provider name or 'auto'. Discovered at runtime from the registry.",
                "default": "auto",
            },
        },
    }

    def _providers(self) -> list[BaseTool]:
        from tools.tool_registry import registry
        registry.ensure_discovered()
        return [t for t in registry.get_by_capability("video_analysis") if t.name != self.name]

    def get_status(self) -> ToolStatus:
        if any(t.get_status() == ToolStatus.AVAILABLE for t in self._providers()):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        providers = self._providers()
        if not providers:
            return ToolResult(success=False, error="No video_analysis provider registered.")

        # Preference order per ANLZ-01:
        #   1. inputs["preferred_provider"] if not "auto"
        #   2. os.environ["VIDEO_ANALYZER_PROVIDER"] if set and != "auto"
        #   3. GEMINI_API_KEY present → gemini provider
        #   4. OPENROUTER_API_KEY present → openrouter provider (ships in Phase 3)
        #   5. first available provider
        chosen = self._pick(inputs, providers)
        if chosen is None:
            return ToolResult(success=False, error="No available video_analysis provider.")

        result = chosen.execute(inputs)
        if result.success:
            result.data.setdefault("selected_tool", chosen.name)
            result.data["selected_provider"] = chosen.provider
        return result

    def _pick(self, inputs, providers):
        available = [t for t in providers if t.get_status() == ToolStatus.AVAILABLE]
        if not available:
            return None
        by_provider = {t.provider: t for t in available}  # first-seen wins (deterministic from discovery order)

        preferred = inputs.get("preferred_provider", "auto")
        if preferred != "auto" and preferred in by_provider:
            return by_provider[preferred]

        env_pref = os.environ.get("VIDEO_ANALYZER_PROVIDER", "auto")
        if env_pref != "auto" and env_pref in by_provider:
            return by_provider[env_pref]

        # Key-presence tie-break (ANLZ-01 explicit ordering)
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            if "gemini" in by_provider:
                return by_provider["gemini"]
        if os.environ.get("OPENROUTER_API_KEY"):
            if "openrouter" in by_provider:
                return by_provider["openrouter"]

        return available[0]
```

**When to use this pattern:** whenever multiple backends implement the same capability. Both existing selectors (`video_selector`, `tts_selector`) use `lib.scoring.rank_providers` for richer selection — Phase 2 does NOT need that complexity (two providers max, explicit env-var priority order is the requirement). Keep `video_analyzer_selector` simple; do not import `lib.scoring` unless Phase 3 grows to justify it.

### Pattern 2: Files API upload + polling + delete

**Source:** verified directly from `google-genai==1.73.1` installed source (`google/genai/files.py`, `google/genai/types.py`).

```python
# tools/analysis/gemini_video_analyzer.py (sketch of the hot path)
import os, time, json
from pathlib import Path
from google import genai
from google.genai import types, errors

from lib.analysis_errors import VideoUploadError, VideoAnalysisError, VideoAnalysisRetryExhausted
from lib.schema_adapter import to_api_schema
from schemas.artifacts import load_schema, validate_artifact


def _get_api_key() -> str | None:
    # Per CONTEXT.md preference (GEMINI_API_KEY primary, GOOGLE_API_KEY fallback).
    # MUST pass explicitly — SDK default reverses this order (Finding 1).
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _make_client() -> genai.Client:
    key = _get_api_key()
    if not key:
        raise VideoUploadError("GEMINI_API_KEY (or GOOGLE_API_KEY) not set.")
    return genai.Client(api_key=key)


def _wait_for_active(client, file_name: str, max_seconds: float = 300.0) -> types.File:
    """Poll Files API until state == ACTIVE or FAILED, with capped backoff.

    Backoff: 1s, 2s, 5s, 5s, 5s, ... until max_seconds elapsed.
    Raises VideoUploadError on FAILED, on timeout, or on types.File.error being set.
    """
    backoff = [1.0, 2.0]
    start = time.monotonic()
    while True:
        f = client.files.get(name=file_name)
        state = f.state.value if hasattr(f.state, "value") else str(f.state)
        if state == "ACTIVE":
            return f
        if state == "FAILED":
            err = getattr(f, "error", None)
            raise VideoUploadError(f"Files API returned FAILED for {file_name}: {err}")
        if (time.monotonic() - start) >= max_seconds:
            raise VideoUploadError(
                f"Files API did not reach ACTIVE within {max_seconds}s (last state={state})"
            )
        wait = backoff.pop(0) if backoff else 5.0
        time.sleep(wait)


def _analyze_once(client, file_ref: types.File, prompt: str, flat_schema: dict, model: str) -> dict:
    """Single structured-output call. Returns the parsed dict.

    Raises VideoAnalysisError if the response is empty, truncated, or unparseable.
    """
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=flat_schema,
        # Optional: temperature=0.1 for determinism across retries.
    )
    try:
        response = client.models.generate_content(
            model=model,
            contents=[file_ref, prompt],
            config=config,
        )
    except errors.ClientError as exc:
        # 4xx — includes model-not-available for preview models. Let caller decide fallback.
        raise  # re-raise; provider code catches at the model-selection layer
    except errors.ServerError as exc:
        raise VideoAnalysisError(f"Gemini server error: {exc}") from exc

    # Truncation detection — Finding 5
    cands = response.candidates or []
    if not cands:
        raise VideoAnalysisError("No candidates in response")
    finish_reason = getattr(cands[0], "finish_reason", None)
    if finish_reason == types.FinishReason.MAX_TOKENS:
        raise VideoAnalysisError(f"Response truncated (finish_reason=MAX_TOKENS)")
    raw = response.text or ""
    if not raw.strip():
        raise VideoAnalysisError("Empty response text")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VideoAnalysisError(f"Failed to parse response JSON: {exc}") from exc
```

### Pattern 3: finally-block cleanup (GEM-03)

```python
def execute(self, inputs):
    client = _make_client()
    video_path = Path(inputs["video_path"])
    if not video_path.exists():
        return ToolResult(success=False, error=f"Video not found: {video_path}")

    uploaded = None
    try:
        uploaded = client.files.upload(file=str(video_path))
        active = _wait_for_active(client, uploaded.name, max_seconds=inputs.get("max_poll_seconds", 300.0))
        model = self._resolve_model()  # preview → 2.5-pro fallback on ClientError
        artifact = self._analyze_with_retry(client, active, inputs, model)
        validate_artifact("video_analysis", artifact)  # hard gate — raises jsonschema.ValidationError if broken
        return ToolResult(success=True, data=artifact, model=model)
    except (VideoUploadError, VideoAnalysisError) as e:
        return ToolResult(success=False, error=str(e))
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except errors.APIError:
                pass  # best-effort cleanup; Gemini auto-deletes at 48h anyway (see Finding 2)
```

### Pattern 4: Retry on null/truncated (GEM-04)

```python
def _analyze_with_retry(self, client, file_ref, inputs, model):
    base_prompt = self._build_prompt(inputs, depth=inputs.get("analysis_depth", "full"))
    try:
        return _analyze_once(client, file_ref, base_prompt, self._flat_schema, model)
    except VideoAnalysisError:
        # One retry with compact depth — reduces token pressure that caused MAX_TOKENS.
        compact_prompt = self._build_prompt(inputs, depth="compact")
        try:
            return _analyze_once(client, file_ref, compact_prompt, self._flat_schema, model)
        except VideoAnalysisError as exc:
            raise VideoAnalysisRetryExhausted(
                f"Analysis failed after compact retry: {exc}"
            ) from exc
```

### Anti-Patterns to Avoid

- **Calling `write_checkpoint` from inside the tool.** The tool returns a `ToolResult.data = artifact`; the *caller* (meta skill) writes the checkpoint. `write_checkpoint` now (post-Phase 1) REQUIRES a `pipeline_type`, which the tool does not know — trying to checkpoint from inside the tool would force `pipeline_type="unknown"` which `write_checkpoint` explicitly rejects (`lib/checkpoint.py:273-278`).
- **Relying on SDK env-var priority.** The SDK prefers `GOOGLE_API_KEY`; CONTEXT requires `GEMINI_API_KEY` first. Always pass `api_key=_get_api_key()` explicitly to `genai.Client(...)`.
- **Mutating `client.files.upload`'s returned File object.** Treat it as immutable; always re-fetch with `files.get(name=...)` when checking state.
- **Using `response.parsed`.** It looks tempting but behavior with `response_json_schema` (vs `response_schema`) is less predictable — `response.text` + explicit `json.loads` gives deterministic error paths that are easy to test.
- **Hand-flattening the schema inside the tool.** `lib.schema_adapter.to_api_schema` is the single source of truth; cache the result at class init.
- **Leaving `uploaded.name` leaked.** Always `finally: client.files.delete(...)`. 48h auto-delete is for crash recovery, not normal operation.
- **Letting `ClientError` (4xx) for a bad preview model name leak up as a fatal error.** Catch specifically to trigger the 2.5-pro fallback (Finding 3).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP calls to Gemini | Custom `requests`/`httpx` wrapper | `google-genai` SDK | SDK handles auth, retries, proto/JSON marshalling, File object typing, streaming. Rolling your own loses all of it. |
| Polling exponential backoff | Your own retry library | Simple while-loop with `time.sleep` + capped list of wait values | The loop is ~10 lines and fully testable with a monkeypatched `time.sleep`. `tenacity` adds a dep for near-zero gain. |
| Schema flattening for structured output | Re-implementing the stripper | `lib.schema_adapter.to_api_schema` (shipped in Phase 1) | Phase 1's `to_api_schema` handles `$ref` inlining, `additionalProperties` false-vs-schema distinction, `uniqueItems` removal. See `/workspace/lib/schema_adapter.py` + its unit tests in `/workspace/tests/unit/test_schema_adapter.py`. |
| Artifact schema validation | Manual dict walking | `schemas/artifacts/__init__.py::validate_artifact("video_analysis", data)` | Already wraps `jsonschema.validate` against the canonical schema — the function the checkpoint writer calls. Use the same call inside the tool so "valid from the tool" ≡ "valid on write". |
| Error hierarchy for upload vs analysis failures | Ad-hoc strings / generic `Exception` | `lib/analysis_errors.py` with `VideoUploadError` / `VideoAnalysisError` / `VideoAnalysisRetryExhausted` | Matches the existing `lib/checkpoint.py::CheckpointValidationError(ValueError)` convention — one module per lib namespace owns its errors. |
| Selector scoring | `lib.scoring.rank_providers` | A plain priority list per ANLZ-01 | ANLZ-01 spells out a strict ordering; the existing scoring engine is for *video generation* where there are 12+ providers with quality tradeoffs. Two providers with a hard priority order is cleaner as a list. |
| Mocking the genai SDK | Full fake client class | `unittest.mock.MagicMock` + `monkeypatch.setattr` | The SDK surface is narrow: `Client()`, `.files.upload`, `.files.get`, `.files.delete`, `.models.generate_content`. Mock each as needed. See Finding 11 for test snippets. |

**Key insight:** Most of the "complex" work in this phase is actually already done by Phase 1 (`schema_adapter`, `validate_artifact`, canonical schema). The Phase 2 tool is a thin orchestrator over the SDK — the temptation to hand-roll the polling loop, build a mini-retry-framework, or inline-flatten the schema should all be resisted.

---

## Runtime State Inventory

*Not a rename/refactor phase — new files only, no existing state to migrate. No Runtime State Inventory required.*

---

## Common Pitfalls

### Pitfall 1: `GOOGLE_API_KEY` vs `GEMINI_API_KEY` priority inversion

**What goes wrong:** CONTEXT.md says "`GEMINI_API_KEY` primary, `GOOGLE_API_KEY` fallback" but the SDK's `get_env_api_key()` (`google/genai/_api_client.py:102-116`) returns `GOOGLE_API_KEY or GEMINI_API_KEY`, emitting a warning if both are set. If a user has both keys set and you pass `genai.Client()` with no `api_key=`, you'll silently use `GOOGLE_API_KEY` — which violates the CONTEXT-declared ordering.

**Why it happens:** [VERIFIED from installed SDK source] Google's own SDK prefers `GOOGLE_API_KEY` (Vertex-leaning convention); CONTEXT is naming-reversed for clarity (users of OpenMontage have `GEMINI_API_KEY` specifically for this integration).

**How to avoid:** Always pass `api_key=` explicitly:
```python
key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
client = genai.Client(api_key=key)
```

**Warning signs:** Test with both env vars set; assert the tool uses GEMINI_API_KEY (check via mocked `genai.Client.__init__` `api_key` argument).

### Pitfall 2: Polling loop without timeout

**What goes wrong:** Video uploads can hang in `PROCESSING` state indefinitely if the Files API has a backend issue. Without a wall clock cap, the tool blocks forever.

**Why it happens:** The SDK has no built-in polling helper (verified — no `wait_for_active` or similar method exists in `google/genai/files.py`). Developers tend to `while state != "ACTIVE": sleep(1)`.

**How to avoid:** Track `time.monotonic()` start; raise `VideoUploadError` when `elapsed >= max_poll_seconds` (default 300). `time.monotonic()` not `time.time()` — immune to clock jumps.

**Warning signs:** Unit test: mock `files.get` to always return `state=PROCESSING`, assert `VideoUploadError` raised when simulated elapsed time exceeds the cap.

### Pitfall 3: Silent truncation as empty response

**What goes wrong:** Gemini hits `MAX_TOKENS` mid-JSON; the SDK returns a `GenerateContentResponse` with `.text == ""` (or a partial, unparseable string). Code that only checks `if response.text:` proceeds as if analysis succeeded, writes a broken (or default-filled) artifact.

**Why it happens:** `response_json_schema` ensures syntactic JSON on *complete* responses, but says nothing about truncation. The SDK surfaces truncation only via `candidates[0].finish_reason == FinishReason.MAX_TOKENS`.

**How to avoid:** Check `finish_reason` FIRST, then check parseable content. Both paths raise `VideoAnalysisError`, triggering the one retry with `analysis_depth="compact"`.

**Warning signs:** Unit test with mocked response where `finish_reason = FinishReason.MAX_TOKENS`; assert retry fires and compact prompt is used.

### Pitfall 4: `additionalProperties` stripping corrupts confidence maps

**What goes wrong:** The canonical schema uses `additionalProperties: {type: string, enum: [low, medium, high]}` on the per-dimension `confidence` field (see `/workspace/schemas/artifacts/video_analysis.schema.json:98-104,142-148,210-216,302-308`). A naive flattener that strips `additionalProperties` entirely would make confidence-map validation meaningless server-side.

**Why it happens:** Early versions of "Gemini-compatible schema" strippers just deleted `additionalProperties` unconditionally. Gemini DOES support schema-valued `additionalProperties` ([CITED: https://ai.google.dev/gemini-api/docs/structured-output — "Can be a boolean or a schema"]).

**How to avoid:** Use `lib.schema_adapter.to_api_schema` — it only strips `additionalProperties` when the value is literally `False` (`/workspace/lib/schema_adapter.py:70-71`). Confirmed by `test_keeps_additional_properties_object` (`tests/unit/test_schema_adapter.py:42-46`).

**Warning signs:** Contract test: flatten the canonical schema, verify the confidence block preserves its `additionalProperties: {enum: [low, medium, high]}`.

### Pitfall 5: Leaked uploaded files across runs

**What goes wrong:** Without `finally: client.files.delete()`, uploaded videos hang out for 48 hours in the user's Gemini File quota. In a tight dev loop, this accumulates — and uploaded files from failed/crashed runs get reused or just waste quota. Storage costs aren't metered on Files API, but the uploaded-file COUNT has a cap per project.

**Why it happens:** Developers assume the 48h auto-delete is "good enough." It is for crash recovery, not for a tool that's expected to run dozens of times during testing.

**How to avoid:** `finally:` block around the whole upload→analyze block. Catch and swallow `errors.APIError` on delete (best-effort — we do not want a delete failure to mask a success).

**Warning signs:** Manual check during SKILL-03 gate: list files via `client.files.list()` after a test run — should show only in-flight analyses, not historical ones.

### Pitfall 6: Preview model unavailable → fatal error

**What goes wrong:** CONTEXT defaults `GEMINI_VIDEO_MODEL=gemini-3.1-pro-preview`. Preview models come and go; if Google removes this variant, `generate_content(model="gemini-3.1-pro-preview", ...)` raises `errors.ClientError` (HTTP 400 / 404). Without fallback, the tool hard-fails and the user can't analyze anything.

**Why it happens:** CONTEXT requires fallback, but naive implementations just let the error propagate.

**How to avoid:** Catch `errors.ClientError` at the model layer; retry once with `gemini-2.5-pro`. Inspect the error message for model-availability indicators (it surfaces as `code=400` / `code=404`). Record the fallback decision in `ToolResult.model`.

**Warning signs:** Unit test: monkeypatch `generate_content` to raise `errors.ClientError(404, {...})` on first call with preview model; assert second call uses `gemini-2.5-pro`.

### Pitfall 7: Selector return shape leaks provider identity

**What goes wrong:** ANLZ-06 (Phase 3) requires the caller to be unable to tell which backend ran the analysis from the artifact alone. If the selector adds provider-specific keys to `ToolResult.data` (e.g., `gemini_file_name`, `openrouter_credits_used`), the artifact violates this invariant.

**Why it happens:** `video_selector.py` sets `selected_tool`, `selected_provider` on `result.data` (lines 179-183). For the analysis selector, that metadata should live on `ToolResult.model` or a sibling metadata field, NOT inside the canonical artifact dict that validates against the schema.

**How to avoid:** The tool's `data` field IS the canonical artifact (validates against `video_analysis.schema.json`). Selector metadata goes into separate `ToolResult` fields (`.model`, `.seed`, or a separate non-artifact attr). Keep `result.data` clean.

**Warning signs:** Contract test: call selector, `validate_artifact("video_analysis", result.data)` — must pass. If you had to strip `selected_provider` first, the shape is wrong.

---

## Code Examples

### Example 1: Minimal upload → poll → analyze → delete

```python
# Verified against /workspace installed google-genai==1.73.1
from google import genai
from google.genai import types
import time, os, json

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Upload
f = client.files.upload(file="/tmp/ref.mp4")  # returns types.File
# f.name == 'files/abc123xyz', f.state == FileState.PROCESSING (initially)

# Poll
start = time.monotonic()
while f.state.value != "ACTIVE":
    if f.state.value == "FAILED":
        raise RuntimeError(f"Upload failed: {f.error}")
    if time.monotonic() - start > 300:
        raise TimeoutError("Upload did not become ACTIVE in 300s")
    time.sleep(2)
    f = client.files.get(name=f.name)

# Structured-output call
try:
    resp = client.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=[f, "Analyze this video across 4 dimensions..."],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=FLAT_SCHEMA,  # from to_api_schema(...)
        ),
    )
    if resp.candidates[0].finish_reason == types.FinishReason.MAX_TOKENS:
        raise RuntimeError("truncated")
    artifact = json.loads(resp.text)
finally:
    client.files.delete(name=f.name)
```

### Example 2: Pre-flattening the schema once at class load

```python
# tools/analysis/gemini_video_analyzer.py
from lib.schema_adapter import to_api_schema
from schemas.artifacts import load_schema


class GeminiVideoAnalyzer(BaseTool):
    # Cached at class load — called exactly once per process.
    _FLAT_SCHEMA = to_api_schema(load_schema("video_analysis"))

    def execute(self, inputs):
        # ... use self._FLAT_SCHEMA
        ...
```

### Example 3: Mocking the SDK surface in pytest

```python
# tests/unit/test_gemini_video_analyzer.py
from unittest.mock import MagicMock, patch
from google.genai import types


def _fake_file(state="ACTIVE", name="files/abc"):
    f = MagicMock(spec=types.File)
    f.name = name
    f.state = types.FileState(state) if state != "ACTIVE" else types.FileState.ACTIVE
    f.error = None
    return f


def test_polling_returns_active_after_processing(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    # Fake video file
    vid = tmp_path / "ref.mp4"
    vid.write_bytes(b"\x00" * 1024)

    # Mock the Client
    client = MagicMock()
    client.files.upload.return_value = _fake_file(state="PROCESSING")
    # First get() returns PROCESSING, second returns ACTIVE
    client.files.get.side_effect = [
        _fake_file(state="PROCESSING"),
        _fake_file(state="ACTIVE"),
    ]
    # Mock generate_content response
    resp = MagicMock()
    resp.candidates = [MagicMock(finish_reason=types.FinishReason.STOP)]
    resp.text = json.dumps(MINIMAL_VALID_ARTIFACT)
    client.models.generate_content.return_value = resp

    with patch("tools.analysis.gemini_video_analyzer.genai.Client", return_value=client), \
         patch("time.sleep"):  # skip real waits
        tool = GeminiVideoAnalyzer()
        result = tool.execute({"video_path": str(vid)})

    assert result.success
    client.files.delete.assert_called_once_with(name="files/abc")
```

### Example 4: Detecting and retrying on MAX_TOKENS

```python
def test_max_tokens_triggers_compact_retry(monkeypatch, tmp_path):
    # ... setup as Example 3 ...
    resp1 = MagicMock(text="", candidates=[MagicMock(finish_reason=types.FinishReason.MAX_TOKENS)])
    resp2 = MagicMock(text=json.dumps(MINIMAL_VALID_ARTIFACT),
                      candidates=[MagicMock(finish_reason=types.FinishReason.STOP)])
    client.models.generate_content.side_effect = [resp1, resp2]

    # ... invoke tool ...

    calls = client.models.generate_content.call_args_list
    assert len(calls) == 2
    # Second call's prompt includes "compact"
    second_contents = calls[1].kwargs["contents"]
    assert any("compact" in str(c) for c in second_contents)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `google-generativeai` package | `google-genai` package | 2024 | Legacy package deprecated. All new Gemini dev uses `google-genai`. |
| `genai.configure(api_key=...)` + `genai.GenerativeModel(...)` | `genai.Client(api_key=...).models.generate_content(model=..., ...)` | Same migration | Explicit client instance; no module-level global state — much easier to test with mocks. |
| `response_schema` (pydantic-like) | `response_json_schema` (raw JSON Schema dict) | google-genai ≥ ~1.30 | Our canonical schemas are JSON Schema Draft 2020-12, so `response_json_schema` is the direct path. `response_schema` expects pydantic classes. |
| Polling helpers like `wait_for_active()` in other SDKs | App owns the while-loop | N/A — genai SDK has never shipped one | Ten lines of app code; no dep on third-party retry libraries. |
| Inline base64 video | Files API upload | Files API stable since 2024 | Videos >20MB must use Files API (inline has 20MB request limit). Files API is the universally-correct path. |

**Deprecated/outdated:**
- `from google import generativeai` — old package. Do NOT install; do NOT import.
- `response_schema` with pydantic models — works but adds an unnecessary pydantic boundary; `response_json_schema` is more direct given our schemas are already JSON Schema.
- `gemini-1.5-pro` / `gemini-1.5-flash` — superseded by 2.5 series; REQUIREMENTS.md targets 3.1-preview → 2.5-pro fallback.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `gemini-3.1-pro-preview` is a valid Gemini model identifier today | Standard Stack + Pitfall 6 | [ASSUMED — inherited from REQUIREMENTS.md GEM-01 / CONTEXT.md; not verified against `client.models.list()`]. If the exact string is wrong, `execute` will hit `ClientError` on first call and fall back to `gemini-2.5-pro` cleanly. Risk is LOW because the fallback is already designed. |
| A2 | Gemini 3.x model family supports video input via Files API in the same way 2.5-pro does | Architecture Pattern 2 | [ASSUMED — 2.5 is documented; 3.x is in preview with evolving docs]. Risk is LOW because fallback covers it. |
| A3 | `response_json_schema` on Gemini 3.x-preview enforces schema server-side the same way 2.5-pro does | Architecture Pattern 2 + Pitfall 3 | [CITED: https://ai.google.dev/gemini-api/docs/structured-output for 2.5; [ASSUMED] for 3.x-preview]. If preview behaves differently, post-validation via `jsonschema.validate` catches it and triggers the retry path. Risk is LOW. |
| A4 | Files API retains ACTIVE state for at least the duration of one generate_content call | Architecture Pattern 3 | [ASSUMED — 48h auto-delete implies "yes"]. Very high confidence; only flagged for completeness. |
| A5 | `validate_artifact("video_analysis", data)` works on the tool's returned dict with the Phase 1 schema | Pattern 3 (finally block) + Don't Hand-Roll | [VERIFIED: `schemas/artifacts/__init__.py:43-46` calls `jsonschema.validate(instance=data, schema=load_schema(name))` against the Phase 1 canonical schema]. |

**Summary:** 5 assumptions total. A1–A3 are model-capability claims that the fallback path absorbs if wrong. A4 is safe. A5 is verified. **No user-confirmation needed before planning** — all risks are covered by existing design.

---

## Open Questions

1. **Should `.agents/skills/gemini-video-analysis/` live as `SKILL.md` only, or `SKILL.md + reference.md`?**
   - What we know: `.agents/skills/elevenlabs/` has `SKILL.md + reference.md` (long API tables in the reference file). Other skills (e.g., `ai-video-gen`) are `SKILL.md`-only.
   - What's unclear: no hard convention.
   - Recommendation: ship `SKILL.md` only in Phase 2. Add `reference.md` only if SKILL.md exceeds ~400 lines. SKILL-01 wording ("documents Gemini-specific prompting per dimension") fits cleanly in one file.

2. **Does the selector need to handle `task_context` + `rank` operation like `video_selector` does?**
   - What we know: `video_selector.py` supports `operation="rank"` for scored rankings (lines 144-153). `tts_selector.py` has the same pattern.
   - What's unclear: there's no requirement (ANLZ-01 doesn't mention ranking) and only one provider exists in Phase 2.
   - Recommendation: DO NOT add `rank` mode in Phase 2. If Phase 3 adds a real cost/quality tradeoff, reconsider then.

3. **Should `model` in the ToolResult reflect the provider's model (`gemini-3.1-pro-preview`) or the tool name (`gemini_video_analyzer`)?**
   - What we know: `ToolResult.model` is typed as `Optional[str]` (base_tool.py:129); existing tools put provider model strings there.
   - What's unclear: when fallback fires, do we put the requested model or the fallback model?
   - Recommendation: put the MODEL THAT ACTUALLY RAN (fallback model on fallback). Add a sibling `data["model_requested"]` for observability.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | Whole phase | ✓ (devcontainer) | — | Blocker: STATE.md blocker confirms devcontainer Python ≥3.10 required. Host 3.9.6 is known to break — all work must run in devcontainer. |
| `google-genai` >= 1.73 | GeminiVideoAnalyzer | ✓ installable | 1.73.1 latest on PyPI | — |
| `jsonschema` >= 4.20 | validate_artifact | ✓ | pinned in requirements.txt line 4 | — |
| `GEMINI_API_KEY` env var | Runtime only (NOT needed for tests) | — | — | Tool raises `VideoUploadError` with clear message if unset; contract/unit tests monkeypatch env and mock SDK |
| FFmpeg | scene_detect (optional upstream producer of shot_boundaries) | ✓ (devcontainer) | — | Phase 2 does not call scene_detect directly — it accepts pre-computed `shot_boundaries` |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None (all code paths have mocked-test coverage; runtime paths raise clean errors when keys missing).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest ≥ 7 (already in use by Phase 1) |
| Config file | None at repo root — `tests/` uses default pytest discovery; `conftest.py` may be added in Wave 0 if needed for shared fixtures |
| Quick run command | `pytest tests/unit/test_gemini_video_analyzer.py tests/contracts/test_phase2_contracts.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |
| Estimated quick runtime | <5 seconds (all mocked; `time.sleep` patched to no-op) |
| Estimated full runtime | <30 seconds (Phase 1 tests ran in seconds per STATE.md metrics) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ANLZ-01 | `video_analyzer_selector` registers with `capability="video_analysis"` and is discoverable | contract | `pytest tests/contracts/test_phase2_contracts.py::test_selector_registered -x` | ❌ Wave 0 |
| ANLZ-01 | Preference order: explicit `preferred_provider` > `VIDEO_ANALYZER_PROVIDER` env > `GEMINI_API_KEY` presence > `OPENROUTER_API_KEY` presence > first available | unit | `pytest tests/contracts/test_phase2_contracts.py::test_selector_preference_order -x` | ❌ Wave 0 |
| ANLZ-04 | Tool output has `confidence: "low"` on uncertain fields (never `None`) — validated against canonical schema | contract | `pytest tests/contracts/test_phase2_contracts.py::test_artifact_confidence_low_not_null -x` | ❌ Wave 0 |
| ANLZ-05 | When `shot_boundaries` absent, returned artifact has `shot_boundary_source: "model"`; when present, it's `"scene_detect"` | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_shot_boundary_source_model -x` | ❌ Wave 0 |
| ANLZ-05 | `shot_boundaries` is passed into the Gemini prompt content | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_shot_boundaries_included_in_prompt -x` | ❌ Wave 0 |
| GEM-01 | Tool has `name="gemini_video_analyzer"`, `capability="video_analysis"`, `provider="gemini"`, correct schema | contract | `pytest tests/contracts/test_phase2_contracts.py::test_gemini_tool_contract -x` | ❌ Wave 0 |
| GEM-01 | Auth picks `GEMINI_API_KEY` over `GOOGLE_API_KEY` when both set (via explicit `api_key=` to Client) | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_auth_priority_gemini_first -x` | ❌ Wave 0 |
| GEM-01 | When `GEMINI_VIDEO_MODEL` unset, defaults to `gemini-3.1-pro-preview`; falls back to `gemini-2.5-pro` on `ClientError` | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_model_fallback_on_preview_unavailable -x` | ❌ Wave 0 |
| GEM-02 | Polling loop: PROCESSING → ACTIVE returns the file; loop exits | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_poll_processing_then_active -x` | ❌ Wave 0 |
| GEM-02 | On FAILED state, raises `VideoUploadError` with file.error in message | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_poll_failed_raises -x` | ❌ Wave 0 |
| GEM-02 | On wall-clock timeout, raises `VideoUploadError` | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_poll_timeout_raises -x` | ❌ Wave 0 |
| GEM-03 | `client.files.delete(name=...)` is called even when analysis raises | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_file_deleted_on_failure -x` | ❌ Wave 0 |
| GEM-03 | `client.files.delete` is called exactly once on the uploaded file name | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_file_deleted_on_success -x` | ❌ Wave 0 |
| GEM-04 | Truncated response (`finish_reason=MAX_TOKENS`) triggers one retry with `analysis_depth="compact"` in prompt | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_max_tokens_triggers_compact_retry -x` | ❌ Wave 0 |
| GEM-04 | Empty response text triggers the same retry path | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_empty_text_triggers_retry -x` | ❌ Wave 0 |
| GEM-04 | Two consecutive failures raise `VideoAnalysisRetryExhausted` | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_retry_exhausted_raises -x` | ❌ Wave 0 |
| GEM-04 | `response_json_schema` is the flattened schema from `to_api_schema(load_schema("video_analysis"))` | unit | `pytest tests/unit/test_gemini_video_analyzer.py::test_flat_schema_passed_to_generate_content -x` | ❌ Wave 0 |
| GEM-05 | Tool's `agent_skills` includes `"gemini-video-analysis"` | contract | `pytest tests/contracts/test_phase2_contracts.py::test_agent_skills_references_layer3 -x` | ❌ Wave 0 |
| SKILL-01 | `.agents/skills/gemini-video-analysis/SKILL.md` exists and contains per-dimension sections | contract | `pytest tests/contracts/test_phase2_contracts.py::test_skill_file_exists_with_required_sections -x` | ❌ Wave 0 |
| SKILL-03 | Field-level quality review on one real video (≥12 of 16 canonical fields populated with appropriate confidence; `pacing_style` + `dominant_visual_style` enums correct) | **manual-only** | **Human runs:** `python -c "from tools.tool_registry import registry; registry.discover(); sel = registry.get('video_analyzer_selector'); r = sel.execute({'video_path': 'tests/fixtures/short_sample.mp4'}); import json; print(json.dumps(r.data, indent=2))"` — then human inspects output | ❌ fixture video needed |

### Sampling Rate

- **Per task commit:** `pytest tests/unit/test_gemini_video_analyzer.py tests/contracts/test_phase2_contracts.py -x -q` — quick, mocked, no API key needed
- **Per wave merge:** `pytest tests/ -x -q` — includes Phase 1 regression tests + Phase 2 new tests; no API key needed
- **Phase gate:** Full suite green + **SKILL-03 manual verification passed** (human runs one real video through the selector and signs off on field quality). This is the only gate Phase 2 cannot automate.

### Wave 0 Gaps

- [ ] `tests/contracts/test_phase2_contracts.py` — all contract tests listed above. No file exists yet.
- [ ] `tests/unit/test_gemini_video_analyzer.py` — all unit tests listed above. No file exists yet.
- [ ] `tests/fixtures/short_sample.mp4` — a <2min test video for SKILL-03 manual verification. Can be any free-to-use clip (e.g., Big Buck Bunny 30s trim, or a repo-owned asset). Do NOT check in a multi-megabyte file if it can be avoided — prefer a ~1MB 5-second clip.
- [ ] `MINIMAL_VALID_ARTIFACT` test fixture (Python dict) reused from Phase 1's `tests/contracts/test_video_analysis_schema.py::minimal_video_analysis()` — import and reuse, do NOT redefine.
- [ ] Framework install: already present (pytest + jsonschema in dev env). Only need to `pip install google-genai>=1.73` once during 02-02 execution.
- [ ] `tests/unit/conftest.py` (optional) — shared fixtures for fake `types.File` + fake `GenerateContentResponse`. Strongly recommended — otherwise each test rebuilds them.

### Manual-Only Verifications (SKILL-03 gate)

SKILL-03 is a phase-close gate. Phase 2 execute completes with code + SKILL.md shipped + unit tests green; SKILL-03 is flagged `human_needed` in VERIFICATION.md with this precise instruction block:

```
SKILL-03 — Field-level quality review (human gate)

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

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `GEMINI_API_KEY` / `GOOGLE_API_KEY` secret — read from env only; NEVER log; NEVER include in ToolResult fields |
| V3 Session Management | no | Stateless SDK; no sessions |
| V4 Access Control | no | Tool executes with whatever key the process has — no multi-tenant logic |
| V5 Input Validation | yes | `video_path` validated as existing file; `analysis_depth` enum-validated via input_schema; `shot_boundaries` shape validated (array of [start,end] pairs). `jsonschema` enforces input_schema; validate_artifact gates output. |
| V6 Cryptography | no | TLS handled by `google-genai` SDK (uses `httpx` / `requests` with default trust roots). We do NOT hand-roll crypto. |
| V7 Error Handling / Logging | yes | Errors raised as typed exceptions; `ToolResult.error` contains stringified message. **NEVER include `GEMINI_API_KEY` in error messages.** The SDK itself is good about this, but our wrapper around `_get_api_key()` must not format the key into any string. |
| V12 Files & Resources | yes | Uploaded file cleanup in `finally:` (GEM-03). Otherwise uploaded files persist 48h — not a secrecy concern, but an isolation one (see Pitfall 5). |
| V14 Configuration | yes | API key via `os.environ` only (never CLI arg, never file). Model env var (`GEMINI_VIDEO_MODEL`) is not sensitive. |

### Known Threat Patterns for {google-genai + local video file input}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key leakage via logs or `ToolResult.error` | Information Disclosure | Never format `_get_api_key()` into any exception message or log line. Tests assert `"GEMINI_API_KEY"` string appears in no `ToolResult.error`. |
| Malicious video path (path traversal / `/etc/passwd`) | Tampering | Tool already checks `Path(video_path).exists()` — but since the uploader runs as the OpenMontage process, any file it can open is fair game. Document that `video_path` is trusted input in the tool's input_schema. |
| Hostile Gemini response (prompt injection in JSON) | Tampering | `jsonschema.validate` against `video_analysis.schema.json` rejects any artifact that violates the enum/type contract. The schema has no `"raw_html"` or executable field. |
| Uploaded video leaks across project boundary | Information Disclosure | `finally: client.files.delete(...)` — the uploaded file is scoped to the API project anyway; this is defense in depth. |
| Cost exhaustion via very long videos | DoS | CONTEXT defers cost tracking to Phase 4 CHUNK-06; Phase 2 does not cap file size. Planner may document `max_video_duration_seconds` as a future tool param but it's not required for Phase 2. |

---

## Findings Deep-Dive

*(Detailed research notes backing the `## Summary` assertions — useful to the planner for sanity-checking.)*

### Finding 1: `google-genai` env var priority is GOOGLE > GEMINI (opposite of CONTEXT)

**Source:** [VERIFIED] Installed `google-genai==1.73.1`, file `google/genai/_api_client.py:100-116`:

```python
# This method checks for the API key in the environment variables. Google API
# key is precedenced over Gemini API key.
def get_env_api_key() -> Optional[str]:
    env_google_api_key = os.environ.get('GOOGLE_API_KEY', None)
    env_gemini_api_key = os.environ.get('GEMINI_API_KEY', None)
    if env_google_api_key and env_gemini_api_key:
        logger.warning(
            'Both GOOGLE_API_KEY and GEMINI_API_KEY are set. Using GOOGLE_API_KEY.'
        )
    return env_google_api_key or env_gemini_api_key or None
```

**Implication for this phase:** CONTEXT.md specifies `GEMINI_API_KEY` primary, `GOOGLE_API_KEY` fallback. The tool MUST NOT rely on the SDK default. Resolution: build a helper `_get_api_key()` that enforces CONTEXT's order, pass `api_key=` explicitly to `genai.Client(api_key=...)`.

Confidence: **HIGH**.

### Finding 2: Files API state machine — 3 terminal states, no built-in polling

**Source:** [VERIFIED] `google-genai==1.73.1`, `google/genai/types.py`:

```python
class FileState(...):
    STATE_UNSPECIFIED = 'STATE_UNSPECIFIED'
    PROCESSING = 'PROCESSING'
    ACTIVE = 'ACTIVE'
    FAILED = 'FAILED'
```

`types.File` has fields: `name, display_name, mime_type, size_bytes, create_time, expiration_time, update_time, sha256_hash, uri, download_uri, state, source, video_metadata, error`.

**Signatures:**
- `files.upload(*, file: str | PathLike | IOBase, config: UploadFileConfig | None = None) -> types.File`
- `files.get(*, name: str, config: GetFileConfig | None = None) -> types.File`
- `files.delete(*, name: str, config: DeleteFileConfig | None = None) -> DeleteFileResponse`

**No built-in polling helper exists** — confirmed by `grep -i 'wait\|poll\|active' google/genai/files.py` returning only string-literal matches in docstrings. The canonical pattern is an app-owned while-loop against `files.get(name=...).state`.

**Auto-expiration:** 48 hours, confirmed by [CITED: https://ai.google.dev/gemini-api/docs/files — "Files are stored for 48 hours"].

Confidence: **HIGH**.

### Finding 3: `GenerateContentConfig` accepts `response_mime_type` + `response_json_schema`

**Source:** [VERIFIED] `google-genai==1.73.1`, `types.GenerateContentConfig.model_fields` includes both:

```
- response_mime_type
- response_schema          # pydantic-model-based (legacy path)
- response_json_schema     # raw-JSON-Schema path (what we use)
```

**Important:** When using `response_json_schema`, you can pass any dict that Gemini accepts as JSON Schema. Gemini supports: `type`, `properties`, `required`, `items`, `prefixItems`, `minItems`, `maxItems`, `enum`, `format`, `minimum`, `maximum`, `pattern`, `additionalProperties` (boolean OR schema), `title`, `description`. [CITED: https://ai.google.dev/gemini-api/docs/structured-output]

**Implication:** The Phase 1 `to_api_schema` adapter produces EXACTLY the right dict shape:
- Strips `$schema`, `$id`, `uniqueItems`, `additionalProperties: false` — all unsupported
- Preserves `additionalProperties: {type: string, enum: [...]}` — supported (schema-valued)
- Inlines `$ref` — required since Gemini doesn't follow internal refs

**Gemini 3.x-preview availability:** ClientError handling is the fallback mechanism (see Finding 6).

Confidence: **HIGH** for 2.5-pro behavior; **MEDIUM** for 3.x-preview behavior (fallback absorbs any divergence).

### Finding 4: `errors.APIError`, `ClientError`, `ServerError` hierarchy

**Source:** [VERIFIED] `google-genai==1.73.1`, `google/genai/errors.py`:

- `APIError(code: int, response_json: Any, response: Optional[Response])` — base
- `ClientError(APIError)` — 4xx (includes model-not-available as `code=404` or `code=400`)
- `ServerError(APIError)` — 5xx
- `UnknownApiResponseError` — parser failure
- `FunctionInvocationError` — not applicable here

**Pattern:** Catch `errors.ClientError` specifically to trigger the preview→2.5-pro fallback (Pitfall 6). Let `ServerError` become `VideoAnalysisError` to trigger the one retry path.

Confidence: **HIGH**.

### Finding 5: `FinishReason` enum includes 17 members; `MAX_TOKENS` is the truncation signal

**Source:** [VERIFIED] `google-genai==1.73.1`, `types.FinishReason`:

```
STOP, MAX_TOKENS, SAFETY, RECITATION, LANGUAGE, OTHER, BLOCKLIST,
PROHIBITED_CONTENT, SPII, MALFORMED_FUNCTION_CALL, UNEXPECTED_TOOL_CALL,
IMAGE_SAFETY, IMAGE_PROHIBITED_CONTENT, NO_IMAGE, IMAGE_RECITATION,
IMAGE_OTHER, FINISH_REASON_UNSPECIFIED
```

**Detection pattern:**
```python
if response.candidates[0].finish_reason == types.FinishReason.MAX_TOKENS:
    raise VideoAnalysisError("truncated")
```

Empty `response.text` also triggers the retry (belt-and-braces — some truncation cases return whitespace-only strings that pass a `finish_reason == STOP` check).

Confidence: **HIGH**.

### Finding 6: Existing selector template patterns

**Source:** [VERIFIED] `/workspace/tools/video/video_selector.py:97-102` + `/workspace/tools/audio/tts_selector.py:87-92`:

Both selectors follow this exact recipe:
1. `_providers()` — `registry.ensure_discovered()` then filter by capability, exclude self
2. `fallback_tools` + `provider_matrix` as `@property` (rebuilt each call — cheap)
3. `get_status()` — `any(tool.get_status() == AVAILABLE for tool in providers)`
4. `execute()` — pick a provider, pass through inputs, stamp `selected_tool` / `selected_provider` onto result

The `video_analyzer_selector` should mirror this but with a simpler picker (explicit priority list, no `lib.scoring`). See the Pattern 1 code sketch above.

Confidence: **HIGH**.

### Finding 7: `agent_skills` convention uses bare skill names

**Source:** [VERIFIED]
- `tools/video/video_selector.py:23` → `agent_skills = ["ai-video-gen", "create-video", "ltx2"]`
- `tools/audio/tts_selector.py:23` → `agent_skills = ["text-to-speech", "elevenlabs", "openai-docs"]`
- `tools/analysis/video_analyzer.py:52` → `agent_skills = ["video-understand", "ffmpeg"]`

All use bare directory names under `.agents/skills/`. The resolver in `registry.get_info()` (base_tool.py:255) returns the list verbatim; the agent reads `.agents/skills/<name>/SKILL.md`.

**Conclusion:** `agent_skills = ["gemini-video-analysis"]` — bare name, no path prefix, no `.md` suffix.

Confidence: **HIGH**.

### Finding 8: Confidence-map shape is `additionalProperties` with schema value

**Source:** [VERIFIED] `/workspace/schemas/artifacts/video_analysis.schema.json:97-104,142-148,210-216,302-308`:

```json
"confidence": {
  "type": "object",
  "description": "Per-field confidence map: field_name → low|medium|high",
  "additionalProperties": {
    "type": "string",
    "enum": ["low", "medium", "high"]
  }
}
```

**Schema adapter behavior:** `to_api_schema` preserves this block intact — only strips `additionalProperties` when value is literally `False` (`lib/schema_adapter.py:71-72`). Verified by `tests/unit/test_schema_adapter.py:42-46::test_keeps_additional_properties_object`.

**Provider-side behavior (how tool fills it):** The prompt instructs Gemini to include confidence maps per dimension. For any field where Gemini is uncertain or absent, the confidence entry SHOULD be `"low"` rather than omitting the field. Since `additionalProperties` allows any key name matching the enum values, this is trivially valid. The SKILL.md must explicitly teach this pattern in its prompting guidance.

**Checkpoint integration:** Phase 2 tool returns `ToolResult.data = artifact`. The CALLER (meta skill / orchestrator — not Phase 2 code) handles `write_checkpoint(pipeline_type, project_id, "video_analysis", "completed", {"video_analysis": artifact})`. `write_checkpoint` at `lib/checkpoint.py:273-278` REJECTS `pipeline_type=None/""`, so Phase 2 tool cannot checkpoint internally — it lacks that context.

Confidence: **HIGH**.

### Finding 9: `scene_detect` output → `shot_boundaries` shape

**Source:** [VERIFIED] `/workspace/tools/analysis/scene_detect.py:153-164`:

```python
scenes.append({
    "index": i,
    "start_seconds": round(scene_start.get_seconds(), 3),
    "end_seconds": round(scene_end.get_seconds(), 3),
    "duration_seconds": round(
        scene_end.get_seconds() - scene_start.get_seconds(), 3
    ),
})
```

**Gap:** The Phase 2 tool's `shot_boundaries` input is spec'd as `[[start, end], ...]` tuples (per CONTEXT `Optional shot_boundaries input`), but `scene_detect` returns dict objects keyed `start_seconds`/`end_seconds`.

**Resolution:** Document `shot_boundaries` input as BOTH shapes acceptable (either dicts from scene_detect, OR [start, end] lists). In the prompt, format as `"Shot boundaries: 0.0-3.4s, 3.4-5.8s, 5.8-9.2s, ..."` regardless of input shape. This is a ~5-line normalization step inside the tool.

Confidence: **HIGH**.

### Finding 10: Layer 3 skill template — mirror elevenlabs SKILL.md

**Source:** [VERIFIED] `/workspace/.agents/skills/elevenlabs/SKILL.md` — 377 lines, well-structured.

**Sections the Gemini skill should mirror:**
1. **Frontmatter** (`name`, `description`, optional `metadata.openclaw.requires.env_any`) — elevenlabs lines 1-12
2. **Auth section** — env var name, link to console, explicit `GEMINI_API_KEY` (NOT `GOOGLE_API_KEY`, since the tool's helper enforces that order)
3. **Per-dimension prompting** — 4 subsections (editing_pacing, audio, visual_style, narrative) with 2+ good-vs-bad extraction examples each
4. **Files API quirks sidebar** — 48h auto-delete, 20MB inline vs Files API, 2GB video size cap, supported formats (mp4, mov, mpeg, avi, flv, webm, wmv, 3gp)
5. **Structured-output pattern block** — code snippet showing `response_mime_type` + `response_json_schema` + `FinishReason.MAX_TOKENS` detection + retry
6. **5-min timecode hallucination warning** — Gemini tends to invent round-number timecodes (30.0s, 60.0s) past the 5-minute mark when no scene boundaries are supplied; SKILL must instruct: "If video > 5min, always supply `shot_boundaries`."
7. **Models table** — `gemini-3.1-pro-preview` (target, best quality for video), `gemini-2.5-pro` (stable fallback), `gemini-2.5-flash` (faster, smaller context — not recommended for 4-dimension analysis)
8. **Confidence-map pattern** — explicit instruction to emit `"low"` rather than omit fields; example JSON block showing the shape

**Length target:** 300-450 lines — enough to be authoritative without splitting into `reference.md`.

Confidence: **HIGH**.

### Finding 11: Testing strategy — mock the 6-call SDK surface

**Source:** [VERIFIED] My own inspection of `google-genai==1.73.1`.

**Total SDK surface area Phase 2 touches:**
1. `genai.Client(api_key=...)` — construct
2. `client.files.upload(file=path)` — returns `types.File`
3. `client.files.get(name=str)` — returns `types.File`
4. `client.files.delete(name=str)` — returns `DeleteFileResponse`
5. `client.models.generate_content(model=str, contents=[...], config=GenerateContentConfig)` — returns `GenerateContentResponse`
6. `response.text`, `response.candidates[0].finish_reason` — read

**Mock pattern (pytest-clean, no network):**

```python
@pytest.fixture
def mock_genai_client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    # Neutralize dotenv at import time
    client = MagicMock()
    monkeypatch.setattr(
        "tools.analysis.gemini_video_analyzer.genai.Client",
        lambda **kw: client,
    )
    monkeypatch.setattr("time.sleep", lambda *a, **kw: None)
    return client
```

All 11 automated tests listed in the Validation Architecture table can be written against this single fixture + variations of return-value / side-effect stubs.

Confidence: **HIGH**.

---

## Sources

### Primary (HIGH confidence — verified by reading code in this session)

- **Installed `google-genai==1.73.1`** — direct source inspection of `google/genai/_api_client.py`, `google/genai/files.py`, `google/genai/types.py`, `google/genai/errors.py` via `python3 -c "import inspect; ..."` calls
- **`/workspace/tools/base_tool.py`** — BaseTool contract, ToolResult shape, `_load_dotenv()` behavior (lines 23-51, 120-258)
- **`/workspace/tools/video/video_selector.py`** — selector template (lines 97-102, 137-243)
- **`/workspace/tools/audio/tts_selector.py`** — selector template variant (lines 87-188)
- **`/workspace/lib/schema_adapter.py`** — `to_api_schema` behavior, `additionalProperties` handling (lines 70-76)
- **`/workspace/lib/checkpoint.py`** — `write_checkpoint` `pipeline_type` requirement (lines 273-278), `CANONICAL_STAGE_ARTIFACTS` mapping (lines 30-42)
- **`/workspace/schemas/artifacts/video_analysis.schema.json`** — canonical schema with confidence-map shape (lines 97-104, 142-148, 210-216, 302-308)
- **`/workspace/schemas/artifacts/__init__.py`** — `validate_artifact`, `load_schema`, `ARTIFACT_NAMES` (lines 13-51)
- **`/workspace/tools/analysis/scene_detect.py`** — scene output shape (lines 153-164)
- **`/workspace/tests/unit/test_schema_adapter.py`** — test patterns + fixture invariants (lines 27-50)
- **`/workspace/tests/contracts/test_video_analysis_schema.py`** — `minimal_video_analysis()` fixture (lines 25-50)
- **`/workspace/.agents/skills/elevenlabs/SKILL.md`** — Layer 3 skill template (full file)

### Secondary (MEDIUM confidence — WebFetch verified against Google docs)

- [Google AI docs: Structured Output](https://ai.google.dev/gemini-api/docs/structured-output) — JSON Schema support, `additionalProperties` with schema value supported, truncation behavior undefined
- [Google AI docs: Files API](https://ai.google.dev/gemini-api/docs/files) — 48h auto-delete, explicit delete supported
- [Google AI docs: Video Understanding](https://ai.google.dev/gemini-api/docs/video-understanding) — Files API usage; polling pattern not shown (confirms app-owned loop)

### Tertiary (LOW confidence)

- *(None — no LOW-confidence sources were needed; the SDK ships on-disk and the repo patterns ship in-repo.)*

---

## Metadata

**Confidence breakdown:**
- Standard Stack: **HIGH** — `google-genai==1.73.1` verified installable + inspected in session
- Architecture (selector, tool, finally, retry): **HIGH** — four existing tool files read verbatim; patterns mirrored directly
- Pitfalls: **HIGH** — 7 pitfalls are all rooted in verified SDK behavior or verified repo conventions
- SDK signatures / FinishReason / FileState: **HIGH** — inspected from installed source
- Layer 3 SKILL.md template: **HIGH** — elevenlabs SKILL.md read in full as reference
- 3.x-preview-specific behavior: **MEDIUM** — fallback design absorbs any divergence from 2.5-pro

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (one month — `google-genai` is fast-moving; re-verify before Phase 3 ships)
