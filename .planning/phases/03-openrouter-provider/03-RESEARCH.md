# Phase 3: OpenRouter Provider — Research

**Researched:** 2026-04-17
**Domain:** OpenAI SDK (`openai>=2.32`) pointed at OpenRouter's `/chat/completions` for video analysis — base64 inline + structured output + truncation retry + cross-provider artifact parity
**Confidence:** HIGH on SDK surface (verified against installed `openai==2.32.0`); HIGH on OpenRouter shape (official docs); MEDIUM on a few docs gaps (inline size cap, unsupported-model HTTP code) — flagged in Assumptions

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Plan Decomposition (mirrors Phase 2 shape, 3 parallel plans):**
- `03-01-PLAN.md` — `tools/analysis/openrouter_video_analyzer.py` (BaseTool `provider="openrouter"`, inline base64, `/chat/completions` with `video_url` content type, `response_format={"type":"json_schema","json_schema":{...}}` with prompt-embedded fallback, `finish_reason=="length"` detection, compact retry, `max_upload_bytes` gate). Add `openai>=1.0` to `requirements.txt`.
- `03-02-PLAN.md` — `.agents/skills/openrouter-video-analysis/SKILL.md` (Layer 3: base64-only inline, model swapping via `OPENROUTER_MODEL`, `response_format` compatibility per model, cost surfacing via `usage` body — NOT headers).
- `03-03-PLAN.md` — Contract + unit tests (API-key-free, mocked openai SDK, cross-provider consistency test — ANLZ-06 gate).

**Tool Shape (OR-01..06, ANLZ-06):**
- `BaseTool` subclass, `capability="video_analysis"`, `provider="openrouter"`, `runtime=ToolRuntime.API`.
- Auth: `OPENROUTER_API_KEY` primary (no fallback). Pass explicitly to `openai.OpenAI(api_key=..., base_url="https://openrouter.ai/api/v1")` — SDK reads `OPENAI_API_KEY` by default, which is wrong.
- Model: `OPENROUTER_MODEL` env (default `google/gemini-3.1-pro-preview`). Format: `vendor/model-name`.
- Encoding: `Path(...).read_bytes()` → `base64.b64encode(...).decode()` → prefix `data:video/mp4;base64,...`. Reject with `VideoUploadError` BEFORE encoding if `os.path.getsize(path) > max_upload_bytes` (default 20 MB).
- Message shape: `[{"role":"user","content":[{"type":"text","text":prompt},{"type":"video_url","video_url":{"url":data_url}}]}]`.
- Structured output: try `response_format={"type":"json_schema","json_schema":{"name":"video_analysis","schema":<flattened>,"strict":True}}` first. On 4xx "unsupported" → fall back to prompt-embedded schema + post-hoc `jsonschema.validate` with one retry on parse failure.
- Truncation: `response.choices[0].finish_reason == "length"` (STRING, not enum — differs from Gemini's `FinishReason.MAX_TOKENS`). Also treat empty `response.choices[0].message.content` as truncated.
- Retry: ONE retry with `analysis_depth="compact"` appended. Second failure → `VideoAnalysisRetryExhausted`.
- No file lifecycle (inline → no server-side state). No `client.close()` needed.
- `agent_skills = ["openrouter-video-analysis"]`.

**Selector Integration (ANLZ-06):**
- Zero selector code changes — Phase 2 `VideoAnalyzerSelector._providers()` auto-discovers via `registry.get_by_capability("video_analysis")`.
- Cross-provider consistency test: same canonical fixture through both mocked providers → both artifacts pass `validate_artifact("video_analysis", ...)` → both have identical top-level keys. Selector caller cannot distinguish.

**SKILL-03 Gate:**
- Real-video quality review deferred to HUMAN-UAT (post-execute manual gate), same as Phase 2.
- Instruction: run one real <2 min video through the selector with `OPENROUTER_API_KEY` set and `VIDEO_ANALYZER_PROVIDER=openrouter`; confirm ≥12 of 16 canonical fields populated appropriately.

**Dependencies:** `openai>=1.0` added to `requirements.txt` in plan 03-01 (latest is 2.32.0, published 2026 — Phase 6 INT-02 finalizes full dep set).

### Claude's Discretion
- Base64 streaming strategy — `Path(...).read_bytes()` + single `b64encode` for <20 MB files.
- Record cost observability — **[REVISED from CONTEXT.md]**: use `response.usage.cost` / `usage.cost_details` from response BODY, NOT `x-openrouter-credit-remaining` header (that header is NOT documented by OpenRouter — see Finding 6).
- Probe model support before main call — NO (extra cost); try json_schema first, fall back on error.

### Deferred Ideas (OUT OF SCOPE)
- PROV-01..03 (other providers) — v2.1+.
- Pre-flight cost check via `/api/v1/key` endpoint — body-based surfacing in v2.0, full integration in Phase 4 CHUNK-06 or v2.1 OBS-01.
- Streaming response parsing — out of v2.0.
- Model alias auto-routing — v2.1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OR-01 | `openrouter_video_analyzer.py` as BaseTool, provider="openrouter", OPENROUTER_API_KEY, OPENROUTER_MODEL default `google/gemini-3.1-pro-preview` | Finding 1 (SDK init), Finding 8 (model slug verified) |
| OR-02 | `openai>=1.0` SDK with `base_url="https://openrouter.ai/api/v1"` | Finding 1 (Client(base_url=...) verified) |
| OR-03 | base64 `data:video/mp4;base64,...` inline; `max_upload_bytes` gate rejects before encoding | Finding 2 (content part shape), Finding 5 (size cap gaps) |
| OR-04 | `/chat/completions` with `video_url` content; `response_format={"type":"json_schema",...}` when supported; fallback to prompt-embedded + post-validation | Finding 2 (video_url), Finding 3 (json_schema), Finding 4 (fallback path) |
| OR-05 | `finish_reason == "length"` detection → one compact retry | Finding 7 (Literal str, not enum) |
| OR-06 | `agent_skills` references `openrouter-video-analysis/SKILL.md` | Finding 9 (Phase 2 Layer 3 template) |
| ANLZ-06 | Both providers produce artifacts passing the same canonical schema | Finding 10 (cross-provider test strategy) |
| SKILL-02 | `.agents/skills/openrouter-video-analysis/SKILL.md` with OpenRouter quirks (base64-only inline, model swap, `response_format` per-model, cost via usage body) | Finding 9 + Finding 6 (cost surface) |
| SKILL-03 | Field-level quality review before phase close | Manual-only (HUMAN-UAT gate, same shape as Phase 2) |
</phase_requirements>

## Project Constraints (from CLAUDE.md / AGENT_GUIDE.md)

1. **Layer 3 skill mandatory** — `agent_skills = ["openrouter-video-analysis"]` → must point at `.agents/skills/openrouter-video-analysis/SKILL.md`.
2. **Tools under `tools/<domain>/`** — `tools/analysis/openrouter_video_analyzer.py`.
3. **BaseTool, no `.run()`** — inherit `execute(inputs) -> ToolResult`.
4. **Tool class naming:** `OpenRouterVideoAnalyzer` (no `Tool` suffix).
5. **Tool does NOT call `lib.checkpoint.write_checkpoint`** (Phase 1 WR-05 requires `pipeline_type` the tool doesn't know).
6. **`.env` auto-loaded** at import (`tools/base_tool.py::_load_dotenv()`). Tests monkeypatch env AFTER import.
7. **Do NOT stamp selector metadata on `result.data`** — the selector owns that (ANLZ-06 Pitfall 7). `ToolResult.model` carries the model that ran; `ToolResult.data` is the canonical artifact only.

---

## Summary

Phase 3 is a **parallel provider** — the shape of the work is already established by Phase 2. Phase 3's novel surface area is:

1. **A different SDK (`openai>=1.0`, latest 2.32.0)** pointed at OpenRouter's OpenAI-compatible `/chat/completions`. The SDK is mature and boring — `openai.OpenAI(api_key=..., base_url=...)` + `client.chat.completions.create(...)`. All verified against installed SDK in this session.
2. **Inline base64 video** instead of a Files API. This is REQUIRED — OpenRouter routing to Gemini via Google AI Studio does NOT support video URLs (per OpenRouter docs). So we encode the file bytes and send them in the `video_url.url` as a data URL.
3. **Different truncation sentinel** — `finish_reason == "length"` (Python `Literal` string, verified in SDK types) instead of Gemini's `FinishReason.MAX_TOKENS` enum.
4. **Optional-per-model structured output** — OpenRouter routes through many providers; only some support `response_format={"type":"json_schema", ...}`. The tool tries json_schema first and falls back to prompt-embedded schema on error. `google/gemini-3.1-pro-preview` is known to support structured outputs; confidence HIGH that happy path works, MEDIUM that the fallback branch won't be necessary for the default model, but the branch MUST exist for operational resilience when users swap models.
5. **ANLZ-06 gate** — a cross-provider consistency test lands HERE, because this is the first moment both providers exist. The test is: mock both providers to return the same canonical artifact, run through the selector, assert the caller cannot tell which backend served the response.

**Primary recommendation:** Implement the tool as a **direct parallel of `gemini_video_analyzer.py`**: same error taxonomy (`VideoUploadError`, `VideoAnalysisError`, `VideoAnalysisRetryExhausted`), same artifact validation gate (`validate_artifact("video_analysis", ...)`), same `_FLAT_SCHEMA` lazy cache, same prompt discipline (confidence="low" directive, shot_boundary_source="model" directive, compact-depth retry prompt). The ONLY genuinely new logic is: (a) base64 encoding + size gate, (b) string-valued `finish_reason` check, (c) the json_schema→prompt-embedded fallback ladder, (d) the cost-surfacing decision (body `.usage`, not headers — see Finding 6).

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `openai` | `>=1.0,<3` (latest `2.32.0`) | Official OpenAI Python SDK; used pointed at OpenRouter via `base_url` | [VERIFIED: `pip3 index versions openai` → latest 2.32.0; installed cleanly in this session; `OpenAI(api_key=..., base_url="https://openrouter.ai/api/v1")` accepted] |
| `jsonschema` | `>=4.20` (already pinned) | Post-hoc artifact validation when json_schema fallback path runs | [VERIFIED: in `requirements.txt`] |
| `google-genai` | `>=1.73,<2` (already pinned from Phase 2) | UNRELATED to OpenRouter — but since both tools coexist, Phase 3 does not touch this line | [VERIFIED: `requirements.txt` line 8] |
| `pytest` | `>=8.0` (from `requirements-dev.txt`) | Test framework | [VERIFIED: `requirements-dev.txt` line 4] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `base64` (stdlib) | — | Inline encode video bytes | Upload path; single `b64encode` call |
| `mimetypes` (stdlib) | — | Guess MIME from extension for data URL prefix | Upload path; default `video/mp4` if unknown |
| `unittest.mock.MagicMock` | stdlib | Stub `openai.OpenAI` + `client.chat.completions.create` | Every unit test |
| `pytest.monkeypatch` | stdlib of pytest | Monkeypatch env vars + SDK classes | All API-key-free tests |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `openai>=1.0` SDK (via `base_url`) | Raw HTTP + `requests` | Loses typed response objects (`ChatCompletion`, `Choice`), loses error hierarchy (`APIError`, `BadRequestError`, `RateLimitError`, `APITimeoutError`), loses `with_raw_response`. Not worth it. |
| `openai>=1.0` SDK | OpenRouter's own SDK (`openrouter-py`, community) | Smaller ecosystem, no `extra_body` passthrough for OpenRouter-specific provider routing preferences. OpenAI SDK is the one OpenRouter itself recommends. |
| Inline base64 | Pre-upload to public URL | Requires a signed-URL service; adds infra; moot anyway — OpenRouter→Gemini via AI Studio rejects URLs (docs state "only YouTube links are supported" and Vertex path also rejects URLs). Base64 inline is the only portable path. |

**Installation:**
```bash
pip install 'openai>=1.0'
```

**Version verification:** [VERIFIED this session]
- `pip3 index versions openai` → latest `2.32.0`.
- `python3 -c "import openai; print(openai.__version__)"` → `2.32.0`.
- No conflicts with `google-genai 1.73.1` / `pydantic 2` / `jsonschema 4`.

---

## Architecture Patterns

### Recommended File Layout

```
tools/analysis/
├── gemini_video_analyzer.py        # shipped (Phase 2)
├── openrouter_video_analyzer.py    # NEW — Phase 3 parallel provider
├── video_analyzer_selector.py      # shipped (Phase 2) — zero changes in Phase 3
├── video_analyzer.py               # legacy brief-only (untouched)
└── scene_detect.py                 # optional shot_boundaries producer (ANLZ-05)

lib/
└── analysis_errors.py              # shipped (Phase 2) — REUSE ALL three classes

.agents/skills/openrouter-video-analysis/
└── SKILL.md                        # NEW — Layer 3 (SKILL-02)

tests/
├── contracts/
│   └── test_phase3_contracts.py    # NEW — cross-provider consistency, SKILL presence, registration
├── unit/
│   ├── conftest.py                 # SHIPPED — extend with `mock_openai` fixture (parallel of `mock_genai`)
│   └── test_openrouter_video_analyzer.py  # NEW — 18 behaviors parallel to Phase 2
```

### Pattern 1: OpenRouter client (openai SDK pointed at OpenRouter)

```python
# Verified against openai==2.32.0 (installed this session)
from openai import OpenAI
from openai import APIError, APIStatusError, BadRequestError, RateLimitError, APITimeoutError

client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],    # explicit — SDK default reads OPENAI_API_KEY
    base_url="https://openrouter.ai/api/v1",     # MUST end without trailing /chat/completions
    # Optional — OpenRouter app identification (NOT required but recommended by docs):
    default_headers={
        "HTTP-Referer": "https://github.com/openmontage",      # app url
        "X-Title": "OpenMontage",                              # app name
    },
)
```

### Pattern 2: Inline base64 video message

**Source:** OpenRouter Video Inputs documentation (WebFetch verified — see Sources).

```python
# Canonical OpenRouter multimodal message shape (verified against docs)
import base64, mimetypes
from pathlib import Path

path = Path(video_path)
mime = mimetypes.guess_type(path.name)[0] or "video/mp4"
# Supported: mp4, mov, mpeg, webm (others may be re-encoded by provider).
if mime not in {"video/mp4", "video/mov", "video/quicktime", "video/webm", "video/mpeg"}:
    raise VideoUploadError(f"Unsupported video MIME: {mime}")

size = path.stat().st_size
if size > max_upload_bytes:
    raise VideoUploadError(
        f"video exceeds max_upload_bytes ({size} > {max_upload_bytes}); use chunking (Phase 4)"
    )

b64 = base64.b64encode(path.read_bytes()).decode("ascii")
data_url = f"data:{mime};base64,{b64}"

messages = [
    {
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "video_url", "video_url": {"url": data_url}},
        ],
    }
]
```

**Notes:**
- The `openai>=1.0` SDK's TypedDict union for content parts does NOT include `video_url` at a type level (it includes text, image, audio, file only). **At runtime, `messages` accepts plain dicts** — we pass the video_url shape verbatim. This works because `create()` serializes dicts directly to JSON without runtime TypedDict validation. **No cast / `type: ignore` needed in Python, but expect static type checkers to complain** — if the planner wants strict typing, add a narrow `# type: ignore[list-item]` on the `messages=` arg, OR use a `cast(Any, messages)` pattern.

### Pattern 3: Structured output with json_schema + fallback

**Source:** OpenRouter Structured Outputs docs + `openai==2.32.0` `ResponseFormatJSONSchema` TypedDict.

```python
from openai.types.shared_params.response_format_json_schema import ResponseFormatJSONSchema
# TypedDict shape: {"type": "json_schema", "json_schema": {"name", "description", "schema", "strict"}}

response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "video_analysis",
        "schema": FLAT_SCHEMA,  # from to_api_schema(load_schema("video_analysis"))
        "strict": True,
    },
}

try:
    resp = client.chat.completions.create(
        model=os.environ.get("OPENROUTER_MODEL", "google/gemini-3.1-pro-preview"),
        messages=messages,
        response_format=response_format,
        # Optional — force providers that honor response_format:
        extra_body={"provider": {"require_parameters": True}},
    )
    structured = True
except BadRequestError as exc:
    # OpenRouter returns 4xx when the routed model lacks structured-output support.
    # Fall back to prompt-embedded schema + post-hoc validation.
    structured = False
    resp = client.chat.completions.create(
        model=...,
        messages=messages_with_schema_embedded_in_prompt,
        # no response_format; parse free-form JSON
    )

content = resp.choices[0].message.content or ""
finish = resp.choices[0].finish_reason  # Literal['stop','length','tool_calls','content_filter','function_call']
if finish == "length" or not content.strip():
    raise VideoAnalysisError("Response truncated or empty")

artifact = json.loads(content)
validate_artifact("video_analysis", artifact)  # hard gate (raises on shape violation)
```

**Verified:**
- `finish_reason` type annotation: `typing.Literal['stop', 'length', 'tool_calls', 'content_filter', 'function_call']` — STRING, not enum. [VERIFIED: `inspect` on `openai.types.chat.chat_completion.Choice.model_fields['finish_reason'].annotation`].
- `BadRequestError` is a subclass of `APIStatusError` which is a subclass of `APIError`. Catch `BadRequestError` narrowly for the fallback branch; let other 4xx (`AuthenticationError`, `PermissionDeniedError`) propagate. [VERIFIED: `openai.BadRequestError.__mro__`].
- `extra_body={"provider": {"require_parameters": True}}` — OpenRouter-specific routing preference that forces selection of a provider supporting the requested parameters (e.g., json_schema). [CITED: OpenRouter structured-outputs docs]. The openai SDK passes `extra_body` through to the request payload verbatim.

### Pattern 4: Compact-depth retry on truncation

Mirrors Phase 2 exactly — only the truncation sentinel changes:

```python
def _run_once(self, client, prompt, model, use_structured=True) -> dict:
    messages = self._build_messages(prompt, video_data_url)
    kwargs = dict(model=model, messages=messages)
    if use_structured:
        kwargs["response_format"] = self._response_format()
        kwargs["extra_body"] = {"provider": {"require_parameters": True}}
    try:
        resp = client.chat.completions.create(**kwargs)
    except BadRequestError as exc:
        if use_structured:
            # Re-dispatch without structured — prompt-embedded fallback
            raise _UnsupportedStructured() from exc
        raise VideoAnalysisError(f"OpenRouter BadRequest: {exc}") from exc

    finish = resp.choices[0].finish_reason
    content = resp.choices[0].message.content or ""
    if finish == "length":
        raise VideoAnalysisError("Response truncated (finish_reason=length)")
    if not content.strip():
        raise VideoAnalysisError("Empty response content")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise VideoAnalysisError(f"JSON unparseable: {exc}") from exc
```

### Pattern 5: Cost observability via response body (NOT header)

**[REVISED from CONTEXT.md]:** CONTEXT.md mentioned `x-openrouter-credit-remaining` header. **That header is NOT documented by OpenRouter** (see Finding 6). Cost is surfaced in the response BODY via `response.usage.cost` (total) and `response.usage.cost_details`.

```python
# After a successful create():
usage = getattr(resp, "usage", None)
cost_usd = 0.0
if usage:
    # openai SDK maps additional body fields via __pydantic_extra__ / model_extra
    cost_usd = float(getattr(usage, "cost", 0.0) or 0.0)

return ToolResult(
    success=True,
    data=artifact,
    model=resp.model,        # the actual model OpenRouter used
    cost_usd=cost_usd,
)
```

**Note:** the openai SDK's `CompletionUsage` pydantic model DOES NOT declare a `cost` field natively (it's OpenAI-standard `prompt_tokens`, `completion_tokens`, `total_tokens`). OpenRouter adds `cost` and `cost_details` as extra fields. Pydantic v2 preserves extras on models with `model_config = ConfigDict(extra="allow")`; openai's `CompletionUsage` is declared with extras permitted. Use `getattr(usage, "cost", 0.0)` defensively.

### Anti-Patterns to Avoid

- **Don't use `response.parse()` or `response.parsed`** — the openai SDK exposes `.parse()` on beta endpoints (`client.beta.chat.completions.parse`) with Pydantic model parsing, but that path is OpenAI-specific and doesn't play well with OpenRouter's variable-provider routing. Stick to `.create()` + `json.loads(content)`.
- **Don't retry on every 4xx** — distinguish `BadRequestError` (unsupported parameter → fall back) from `AuthenticationError` (bad key → surface immediately) and `PermissionDeniedError` (quota / model access → surface immediately).
- **Don't assume `video_url` is in the SDK's TypedDict union** — it isn't. Pass dicts at runtime.
- **Don't put `response_format` in `extra_body`** — `response_format` is a first-class `create()` kwarg in `openai>=1.0`. `extra_body` is ONLY for OpenRouter-specific routing (`provider`, `transforms`, etc.).

### Pattern 6: Cross-provider consistency test (ANLZ-06 gate)

```python
# tests/contracts/test_phase3_contracts.py (sketch — full scaffolding in plan 03-03)
import pytest
from unittest.mock import patch, MagicMock
from schemas.artifacts import validate_artifact
from tests.contracts.test_video_analysis_schema import minimal_video_analysis


@pytest.mark.parametrize("provider_name,tool_import_path", [
    ("gemini", "tools.analysis.gemini_video_analyzer"),
    ("openrouter", "tools.analysis.openrouter_video_analyzer"),
])
def test_both_providers_produce_same_canonical_artifact(provider_name, tool_import_path, ...):
    """ANLZ-06: caller cannot tell which backend served the response."""
    canonical = minimal_video_analysis()
    # Patch the provider's underlying SDK surface to return `canonical` as JSON.
    # Call selector.execute(...) with preferred_provider=provider_name.
    # Assert result.data == canonical (deep equality).
    # Assert validate_artifact("video_analysis", result.data) passes.
    # Assert set(result.data.keys()) is identical across both providers.
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OpenAI-compatible chat completions request | Custom `requests.post(...)` with manual header auth | `openai.OpenAI(api_key=..., base_url="https://openrouter.ai/api/v1")` | Typed response objects, error hierarchy, retries/timeouts, `with_raw_response` for header access. |
| Structured output parsing | Custom JSON extractor from free-form text | `response_format={"type":"json_schema","json_schema":{...}}` with prompt-embedded fallback | Two proven paths; fallback only when the routed model doesn't support `json_schema`. |
| Truncation detection | Heuristic (count braces, check for trailing comma) | `resp.choices[0].finish_reason == "length"` + empty-content check | Deterministic; matches what OpenRouter returns verbatim. |
| Base64 data URL construction | Manual string concatenation | `f"data:{mime};base64,{base64.b64encode(...).decode('ascii')}"` | Trivial — but DO use stdlib `mimetypes.guess_type(...)` for MIME; don't hardcode `video/mp4`. |
| Retry backoff | Custom sleep loop | `openai.OpenAI(max_retries=2, timeout=60)` + compact-depth retry on VideoAnalysisError | SDK retries transient 5xx / timeouts automatically; our retry is strictly for truncation+compact-depth semantic retry. |
| Cost extraction | Parse headers with `with_raw_response` | `getattr(resp.usage, "cost", 0.0)` | Cost is in the response BODY (OpenRouter extra field on `usage`), not headers. See Finding 6. |

**Key insight:** the openai SDK is mature (2.32.0 this session). Every SDK surface we need — `Client()`, `chat.completions.create()`, error classes, `extra_body` passthrough — is stable and battle-tested. Hand-rolled HTTP buys nothing.

---

## Runtime State Inventory

**Not applicable — Phase 3 is a greenfield provider, no rename/refactor/migration scope.** Verified by re-reading phase boundary in CONTEXT.md: all artifacts are NEW (tool, skill, tests); no existing files are renamed or migrated. No stored data, live service config, OS-registered state, secrets, or build artifacts change names.

---

## Common Pitfalls

### Pitfall 1: Relying on openai SDK default env for auth
**What goes wrong:** `openai.OpenAI()` (no args) reads `OPENAI_API_KEY`, NOT `OPENROUTER_API_KEY`.
**Why it happens:** SDK is written for OpenAI's own API first; `base_url` override doesn't rewire auth env.
**How to avoid:** Always pass `api_key=os.environ["OPENROUTER_API_KEY"]` explicitly.
**Warning signs:** Tests pass because `OPENAI_API_KEY` happens to be set; in production a different env fails with 401.

### Pitfall 2: Treating `finish_reason` as an enum
**What goes wrong:** Code like `if finish_reason == FinishReason.MAX_TOKENS:` (copy-paste from Gemini pattern) silently always-False because the openai SDK's `finish_reason` is a `Literal[str]`, not an enum.
**Why it happens:** Python typing `Literal` is a TYPE-level construct only; at runtime `finish_reason` is the literal string `"length"`.
**How to avoid:** `if finish_reason == "length":` — string equality. Tests must assert both the string comparison AND that a fake mock returning an enum-like object fails the check.
**Warning signs:** Silent success on truncated output; tests mock with `MagicMock()` whose `.finish_reason` returns a Mock (which equals nothing) and the retry path is never exercised.

### Pitfall 3: `video_url` rejected as invalid content part
**What goes wrong:** Some code paths (e.g., OpenAI's own validation proxy, strict TypedDict checkers) reject `{"type": "video_url", ...}` as an invalid content part.
**Why it happens:** OpenAI's own OpenAPI spec doesn't include `video_url`; OpenRouter extended it. The openai SDK does not validate content-part types at runtime but some middleware might.
**How to avoid:** Use dict literals for messages (not typed TypedDict constructors). Never use `client.beta.*` endpoints — those enforce typing.
**Warning signs:** 400 error from OpenRouter citing "invalid content part type" → double-check the content type string is exactly `"video_url"` (not `"video"`, `"videoUrl"`, etc.).

### Pitfall 4: `response_format` silently downgraded by provider
**What goes wrong:** OpenRouter routes to a provider that accepts `response_format` but doesn't enforce it → you get free-form text instead of strict JSON; schema validation then fails at a confusing layer.
**Why it happens:** Without `extra_body={"provider":{"require_parameters":True}}`, OpenRouter may pick a provider that "accepts" the parameter without enforcing it.
**How to avoid:** Set `extra_body={"provider":{"require_parameters":True}}` whenever using `response_format`. On `BadRequestError`, fall through to prompt-embedded schema path.
**Warning signs:** `json.loads(content)` fails because `content` starts with "I'll analyze this video..." instead of `{`.

### Pitfall 5: Cost misattribution from header (doesn't exist)
**What goes wrong:** Team adds code `resp.response.headers["x-openrouter-credit-remaining"]` → header is not present → crash, or defaults to 0 silently.
**Why it happens:** `x-openrouter-credit-remaining` is NOT documented by OpenRouter. The only documented rate-related headers are `X-RateLimit-Limit/Remaining/Reset`. Cost is in the response body (`usage.cost`).
**How to avoid:** Use `getattr(resp.usage, "cost", 0.0)`. For rate limit, use `with_raw_response` and read `X-RateLimit-*`.
**Warning signs:** Any code that does `response.headers.get("x-openrouter-credit-remaining")`.

### Pitfall 6: Base64 encoding doubles memory
**What goes wrong:** `base64.b64encode(path.read_bytes())` reads the entire file into RAM THEN creates a second copy (1.33x size) as base64 bytes. For 20 MB files → ~50 MB peak RAM for the encoding. Survivable. For 200 MB (which we'd reject anyway) → 500 MB.
**Why it happens:** Naïve full-buffer encode. Stdlib `base64.encode(src, dst)` streams but is awkward.
**How to avoid:** (a) Enforce `max_upload_bytes` BEFORE encoding (default 20 MB — matches OpenAI image inline caps; OpenRouter doesn't document a hard cap — see Assumptions A1). (b) Full-buffer encode is fine for <20 MB.
**Warning signs:** OOM kills on large video inputs in CI; monotonically increasing memory footprint during polling.

### Pitfall 7: Selector metadata stamped on `result.data`
**What goes wrong:** Tool appends `result.data["selected_provider"] = "openrouter"` → cross-provider consistency test fails because Gemini artifact wouldn't have that key (or vice versa); `result.data` is no longer the canonical artifact.
**Why it happens:** Well-intentioned "traceability" addition in the tool instead of at the selector layer.
**How to avoid:** `result.data` is the validated canonical artifact ONLY. Provider metadata lives on `ToolResult.model` and (optional) `ToolResult.cost_usd`. The selector handles any cross-cutting metadata above the tool layer.
**Warning signs:** The ANLZ-06 contract test (plan 03-03) deep-equals fails because the two providers' `result.data` dicts differ by a metadata key.

### Pitfall 8: Assuming json_schema fallback path "won't be needed"
**What goes wrong:** Tool ships without the prompt-embedded fallback because `google/gemini-3.1-pro-preview` supports `response_format`. User swaps `OPENROUTER_MODEL=anthropic/claude-...` → structured output unsupported on that route → runtime BadRequestError with no graceful degradation.
**Why it happens:** Testing happy path with the default model.
**How to avoid:** Write the fallback code AND a unit test that asserts it fires on mocked `BadRequestError`. Treat the fallback as required, not speculative.
**Warning signs:** The fallback branch has no coverage in `tests/unit/test_openrouter_video_analyzer.py`.

---

## Code Examples

Verified patterns from official sources + installed SDK introspection:

### Example 1: Full tool execute() skeleton

```python
# tools/analysis/openrouter_video_analyzer.py (sketch — full class in plan 03-01)
from __future__ import annotations
import base64
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

import jsonschema
from openai import OpenAI, APIError, BadRequestError

from lib.analysis_errors import (
    VideoAnalysisError,
    VideoAnalysisRetryExhausted,
    VideoUploadError,
)
from lib.schema_adapter import to_api_schema
from schemas.artifacts import load_schema, validate_artifact
from tools.base_tool import BaseTool, ResourceProfile, RetryPolicy, ToolResult, ToolRuntime, ToolStability, ToolTier


logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-3.1-pro-preview"
FALLBACK_MODEL = "google/gemini-2.5-pro"
DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB (see Assumption A1)
HARD_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB (OpenRouter unspecified; we cap defensively)
SUPPORTED_MIMES = {"video/mp4", "video/quicktime", "video/mov", "video/webm", "video/mpeg"}


class OpenRouterVideoAnalyzer(BaseTool):
    name = "openrouter_video_analyzer"
    capability = "video_analysis"
    provider = "openrouter"
    runtime = ToolRuntime.API
    agent_skills = ["openrouter-video-analysis"]
    # ... (mirrors GeminiVideoAnalyzer shape)

    _FLAT_SCHEMA: dict | None = None

    @classmethod
    def _flat_schema(cls) -> dict:
        if cls._FLAT_SCHEMA is None:
            cls._FLAT_SCHEMA = to_api_schema(load_schema("video_analysis"))
        return cls._FLAT_SCHEMA

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        video_path = Path(inputs.get("video_path", ""))
        if not video_path.exists() or not video_path.is_file():
            return ToolResult(success=False, error=f"Video not found: {video_path}")

        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            return ToolResult(success=False, error="OPENROUTER_API_KEY not set.")

        # MD-04 pattern: clamp size gate
        raw_cap = inputs.get("max_upload_bytes") or DEFAULT_MAX_UPLOAD_BYTES
        try:
            max_upload = int(raw_cap)
        except (TypeError, ValueError):
            max_upload = DEFAULT_MAX_UPLOAD_BYTES
        max_upload = max(1, min(max_upload, HARD_MAX_UPLOAD_BYTES))

        size = video_path.stat().st_size
        if size > max_upload:
            return ToolResult(
                success=False,
                error=f"video exceeds max_upload_bytes ({size} > {max_upload})",
            )

        mime = mimetypes.guess_type(video_path.name)[0] or "video/mp4"
        if mime not in SUPPORTED_MIMES:
            return ToolResult(success=False, error=f"Unsupported video MIME: {mime}")

        data_url = f"data:{mime};base64,{base64.b64encode(video_path.read_bytes()).decode('ascii')}"

        client = OpenAI(api_key=key, base_url=OPENROUTER_BASE_URL)
        # ... call _analyze_with_fallback(client, data_url, inputs) ...
        # same ladder as Phase 2: structured → structured+compact → prompt-embedded → prompt-embedded+compact
```

### Example 2: json_schema → prompt-embedded fallback ladder

```python
def _analyze_with_fallback(self, client, data_url, inputs) -> tuple[dict, str, float]:
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    prompt = self._build_prompt(inputs, depth="full", include_schema_in_prompt=False)

    # Attempt 1: structured + full
    try:
        return self._run_once(client, data_url, prompt, model, structured=True)
    except BadRequestError as exc:
        logger.info("Model %s rejected response_format=json_schema; falling back to prompt-embedded: %s", model, exc)
        structured = False
    except VideoAnalysisError:
        # Attempt 2: structured + compact
        compact = self._build_prompt(inputs, depth="compact", include_schema_in_prompt=False)
        try:
            return self._run_once(client, data_url, compact, model, structured=True)
        except BadRequestError:
            structured = False
        except VideoAnalysisError as exc:
            raise VideoAnalysisRetryExhausted(f"structured+compact failed: {exc}") from exc

    # Fallback path: prompt-embedded schema + free-form JSON + post-validation
    prompt_with_schema = self._build_prompt(inputs, depth="full", include_schema_in_prompt=True)
    try:
        return self._run_once(client, data_url, prompt_with_schema, model, structured=False)
    except VideoAnalysisError:
        compact_with_schema = self._build_prompt(inputs, depth="compact", include_schema_in_prompt=True)
        try:
            return self._run_once(client, data_url, compact_with_schema, model, structured=False)
        except VideoAnalysisError as exc:
            raise VideoAnalysisRetryExhausted(f"prompt-embedded+compact failed: {exc}") from exc
```

### Example 3: Mocking openai SDK for tests (API-key-free)

```python
# tests/unit/conftest.py — extend existing conftest with this fixture (parallels mock_genai)
@pytest.fixture
def mock_openai(monkeypatch, valid_artifact):
    """Stub the openai SDK for OpenRouter tests.

    By default:
      - chat.completions.create() returns choices[0].finish_reason='stop',
        choices[0].message.content=json.dumps(valid_artifact), usage.cost=0.001
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    resp = MagicMock()
    choice = MagicMock()
    choice.finish_reason = "stop"                                    # STRING, not enum
    choice.message.content = json.dumps(valid_artifact)
    resp.choices = [choice]
    resp.model = "google/gemini-3.1-pro-preview"
    usage = MagicMock()
    usage.cost = 0.001
    resp.usage = usage

    client = MagicMock()
    client.chat.completions.create.return_value = resp

    import tools.analysis.openrouter_video_analyzer as target
    monkeypatch.setattr(target, "OpenAI", MagicMock(return_value=client))
    return client
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `openai<1.0` (legacy module-level `openai.ChatCompletion.create`) | `openai>=1.0` (instance `client.chat.completions.create`) | Nov 2023 | Must use `OpenAI()` instance; module-level API removed. |
| `response_format={"type":"json_object"}` (basic JSON mode) | `response_format={"type":"json_schema","json_schema":{"strict":true,...}}` | Aug 2024 (OpenAI) / rolled out to OpenRouter routes as providers added support | Strict schema enforcement; reduces parse failures. |
| Cost via `with_raw_response` headers | Cost via `response.usage.cost` body field (OpenRouter-specific) | Baseline for OpenRouter | Header approach never worked for OpenRouter — body extra fields are canonical. |

**Deprecated / outdated:**
- `openai.ChatCompletion.create(...)` (module-level): removed in `openai>=1.0`.
- Any `response_format={"type": "json"}` (non-canonical): not supported. Use `json_object` or `json_schema`.

---

## Assumptions Log

Claims I could NOT fully verify this session. Planner + discuss-phase must flag to user for confirmation or accept residual risk:

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Inline base64 cap at 20 MB is the right default (mirrors common OpenAI image cap; OpenRouter does NOT document a hard cap for video) | Pattern 2, Finding 5 | Default too low → small reference videos needlessly rejected. Default too high → HTTP 413 or provider timeout at runtime. Mitigation: make `max_upload_bytes` a tool input (default 20 MB) so callers can override per-call. Clamp hard cap to 2 GB defensively. |
| A2 | `google/gemini-3.1-pro-preview` supports `response_format={"type":"json_schema","strict":true}` on the AI Studio route | Pattern 3 | Structured path always errors → tool degrades to prompt-embedded fallback on every call (slower / less reliable). No correctness impact — fallback is always safe. Flag for SKILL-03 gate to verify empirically. |
| A3 | `extra_body={"provider":{"require_parameters":True}}` is the correct shape for OpenRouter provider routing preferences | Pattern 3 | If docs changed, the flag is silently ignored → same as A2 (correctness unchanged, fallback may fire). |
| A4 | OpenRouter's `BadRequestError` (4xx) body contains a machine-readable "unsupported response_format" signal | Pitfall 4 | Tool catches `BadRequestError` broadly and falls back on ANY 400 — potentially masks malformed request bugs. Mitigation: log `exc.body` / `exc.code` before the fallback path fires, so regressions surface in logs. |
| A5 | `google/gemini-2.5-pro` is a valid model slug for OpenRouter fallback | Example 1 `FALLBACK_MODEL` | If slug is wrong, fallback model also 404s → tool raises `VideoAnalysisRetryExhausted`. Low risk (easy to change); verified `google/gemini-3.1-pro-preview` exists but did not verify `2.5-pro` slug this session. |
| A6 | `openai.types.chat.ChatCompletionMessageParam` at runtime accepts dict content-parts of type `"video_url"` without validation errors | Pattern 2 anti-pattern note | At worst the SDK raises `TypeError` at `create()` time (we'd see immediately in tests). Verified that openai SDK's create() accepts raw dicts for messages — no runtime TypedDict enforcement — but did NOT run a live call with video_url content this session. |

**Nothing in assumptions list is load-bearing for the test suite** — every assumption is either "default value" or "graceful degradation branch." The only truly novel runtime behavior (A2, A6) can be flushed out during SKILL-03 HUMAN-UAT.

---

## Open Questions

1. **Should we set `extra_body={"provider":{"require_parameters":True}}` unconditionally, or only when `response_format` is set?**
   - What we know: `require_parameters` filters providers that support the parameters in the request.
   - What's unclear: whether there's a performance or cost penalty vs the default "best effort" routing.
   - Recommendation: set it only when `response_format` is present (i.e., structured path). Don't over-constrain the prompt-embedded fallback path.

2. **Should the tool record `resp.model` exactly, or normalize to the requested model slug?**
   - What we know: OpenRouter's `resp.model` reflects the provider's actual model ID (e.g., `gemini-2.5-pro-002`), not the OpenRouter slug.
   - What's unclear: whether callers (selector tests, observability) expect the OpenRouter slug or the underlying model ID.
   - Recommendation: store `resp.model` verbatim on `ToolResult.model`. Consistent with Gemini tool's behavior (which stores the model that ran). Document in SKILL-02.

3. **SKILL.md: should we document the `x-openrouter-credit-remaining` header is NOT real, or silently omit?**
   - Recommendation: explicitly document that cost is in `response.usage.cost` body (NOT headers). Agents and future contributors will try the header path if we don't correct the record.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.11 | openai SDK, all tests | ✓ | 3.11 (devcontainer) | — |
| `openai>=1.0` | `OpenRouterVideoAnalyzer` | ✓ (installed this session) | 2.32.0 | Plan 03-01 pins in `requirements.txt` |
| `google-genai` (Phase 2) | Cross-provider ANLZ-06 test | ✓ (pinned from Phase 2) | 1.73.1 | — |
| `jsonschema>=4.20` | Post-hoc artifact validation | ✓ | 4.x already pinned | — |
| `pytest>=8.0` | Test framework | ✓ | In `requirements-dev.txt` | — |
| Network to `api.openrouter.ai` | HUMAN-UAT SKILL-03 gate | not verified this session | — | UAT is manual; run on a workstation with network; not a CI gate |

**Missing dependencies with no fallback:** None — all deps are installable via pip; no external services required for the automated test suite (everything mocked).

**Missing dependencies with fallback:** None blocking Phase 3 execution.

---

## Validation Architecture

**Nyquist validation:** the `.planning/config.json` does NOT explicitly disable `workflow.nyquist_validation` — key is absent → treated as enabled per spec. This section lands.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest>=8.0` (from `requirements-dev.txt`) |
| Config file | None in root; test discovery via default pytest (directory-based). `tests/unit/__init__.py`, `tests/contracts/__init__.py` exist; confirmed by `ls tests/`. |
| Quick run command | `pytest tests/unit/test_openrouter_video_analyzer.py -x -q` (target <10 s) |
| Full suite command | `pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| OR-01 | BaseTool fields (name, capability, provider, runtime, agent_skills) | unit | `pytest tests/unit/test_openrouter_video_analyzer.py::test_contract_fields -x` | Wave 0 |
| OR-01 | Auth: `OPENROUTER_API_KEY` required; missing → success=False; value never leaked in error | unit | `pytest -k test_auth_missing_key_no_leak` | Wave 0 |
| OR-02 | Client constructed with `base_url="https://openrouter.ai/api/v1"` | unit | `pytest -k test_openai_client_base_url` | Wave 0 |
| OR-02 | `api_key` passed explicitly (not env-default) | unit | `pytest -k test_api_key_passed_explicitly` | Wave 0 |
| OR-03 | `max_upload_bytes` gate rejects oversize BEFORE encoding | unit | `pytest -k test_max_upload_bytes_reject` | Wave 0 |
| OR-03 | Base64 data URL prefix `data:video/mp4;base64,` | unit | `pytest -k test_base64_data_url_prefix` | Wave 0 |
| OR-03 | Unsupported MIME rejected | unit | `pytest -k test_unsupported_mime_rejected` | Wave 0 |
| OR-04 | `messages` contains `{"type":"video_url","video_url":{"url":data_url}}` + text part | unit | `pytest -k test_video_url_content_part` | Wave 0 |
| OR-04 | `response_format={"type":"json_schema",...,"strict":True}` used on first attempt | unit | `pytest -k test_json_schema_response_format_first` | Wave 0 |
| OR-04 | On `BadRequestError` → prompt-embedded fallback with schema in prompt | unit | `pytest -k test_bad_request_falls_back_to_prompt_embedded` | Wave 0 |
| OR-05 | `finish_reason=="length"` triggers compact retry | unit | `pytest -k test_length_finish_reason_triggers_compact_retry` | Wave 0 |
| OR-05 | Empty `message.content` triggers retry | unit | `pytest -k test_empty_content_triggers_retry` | Wave 0 |
| OR-05 | Both attempts fail → `VideoAnalysisRetryExhausted` | unit | `pytest -k test_retry_exhausted_raises` | Wave 0 |
| OR-06 | `agent_skills == ["openrouter-video-analysis"]` and SKILL.md file exists | contract | `pytest tests/contracts/test_phase3_contracts.py::test_skill_file_exists -x` | Wave 0 |
| ANLZ-06 | Same canonical fixture through both mocked providers → identical `result.data` keys | contract | `pytest tests/contracts/test_phase3_contracts.py::test_cross_provider_consistency -x` | Wave 0 |
| ANLZ-06 | Artifact passes `validate_artifact("video_analysis", ...)` for both providers | contract | `pytest tests/contracts/test_phase3_contracts.py::test_both_providers_validate` | Wave 0 |
| SKILL-02 | SKILL.md has 8 required sections, names OPENROUTER_API_KEY, mentions base64-only, mentions cost in usage body | contract | `pytest tests/contracts/test_phase3_contracts.py::test_skill_required_sections` | Wave 0 |
| SKILL-02 | No real API key in SKILL.md (regex scan for `sk-or-v1-*`) | contract | `pytest tests/contracts/test_phase3_contracts.py::test_no_embedded_api_keys` | Wave 0 |
| SKILL-03 | Real-video quality review (≥12/16 fields populated correctly) | **manual-only** | HUMAN-UAT, not automated | — |
| Security: artifact schema validation gate | Invalid artifact → success=False; no crash | unit | `pytest -k test_invalid_artifact_rejected` | Wave 0 |
| Security: no `write_checkpoint` import | Source grep | unit | `pytest -k test_tool_does_not_import_checkpoint` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/unit/test_openrouter_video_analyzer.py -x -q` (<10 s) — confirms the tool under active change still passes all 18 behaviors.
- **Per wave merge:** `pytest tests/unit/ tests/contracts/ -q` (<30 s) — full Phase 2 + Phase 3 coverage, including cross-provider consistency.
- **Phase gate:** `pytest tests/ -q` exits 0 with NO API keys set (`unset OPENROUTER_API_KEY GEMINI_API_KEY GOOGLE_API_KEY`) before `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `tests/unit/test_openrouter_video_analyzer.py` — covers OR-01..05, ANLZ-04 retry logic, security invariants (18 behaviors).
- [ ] `tests/contracts/test_phase3_contracts.py` — covers OR-06, ANLZ-06, SKILL-02 invariants.
- [ ] `tests/unit/conftest.py` — EXTEND existing conftest with `mock_openai` fixture + `response_factories` additions for OpenRouter response shapes (truncated/empty/good/BadRequest).
- [ ] `requirements.txt` — add `openai>=1.0` (plan 03-01 Task 1 per the established Phase 2 shape).

---

## Security Domain

Phase 3 inherits `security_enforcement: true` from the Phase 2 precedent (all plan files set it). Applicable ASVS categories:

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | yes | `OPENROUTER_API_KEY` from env; NEVER formatted into logs, errors, or `ToolResult.error`. Mirror Phase 2's T-02-06 mitigation pattern. |
| V3 Session Management | no | Stateless HTTPS per call; no session state. |
| V4 Access Control | no | Single-tenant; agent layer trusted (documented T-02-10 acceptance pattern). |
| V5 Input Validation | yes | Post-response `validate_artifact("video_analysis", ...)` rejects prompt-injection-shaped responses. Strict enums + json_schema enforce schema server-side; jsonschema enforces client-side. |
| V6 Cryptography | yes | TLS via `openai` SDK. API key over `Authorization: Bearer` (openai SDK handles). NEVER hand-roll. |

### Known Threat Patterns for openai + OpenRouter

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key leakage in logs/errors | Information Disclosure | Never format `key` into any `logger.*`, f-string, or `ToolResult.error`. Test asserts a sentinel key value does NOT appear in error output (mirror Phase 2's T-02-06 bonus test). |
| Prompt injection via malicious video content → malformed JSON | Tampering | Hard gate: `validate_artifact("video_analysis", ...)` rejects shapes the schema doesn't allow; strict enums on key fields (pacing_style, dominant_visual_style, hook_type). |
| Cost exhaustion via oversize video | Denial of Service | `max_upload_bytes` gate (default 20 MB) REJECTS before encoding — no network call made for oversize. Clamped to `[1, 2 GB]`. |
| Uncontrolled retries blowing budget | Denial of Service | Exactly ONE compact retry on truncation. Beyond that → `VideoAnalysisRetryExhausted`. SDK's own `max_retries=2` (default) handles transient 5xx only. |
| Model-unavailable masking as `BadRequestError` | Spoofing | Distinguish `BadRequestError` (fallback to prompt-embedded) from `AuthenticationError`/`PermissionDeniedError` (surface immediately). Log the 4xx body before falling back. |
| Real API key in SKILL.md examples | Information Disclosure | SKILL.md must use `os.environ["OPENROUTER_API_KEY"]` or `"YOUR_KEY_HERE"`. Contract test scans for `sk-or-v1-[a-f0-9]{40,}` regex and fails if any match. |

---

## Sources

### Primary (HIGH confidence)
- **Installed `openai==2.32.0`** — inspected this session for: `OpenAI.__init__` signature (has `api_key`, `base_url`, `default_headers`, `max_retries`, `timeout`, etc.); `chat.completions.create` signature (has `messages`, `model`, `response_format`, `extra_body`, `extra_headers`); `Choice.finish_reason` annotation = `Literal['stop','length','tool_calls','content_filter','function_call']` (STRING, not enum); `ChatCompletion.usage` exists; `CompletionUsage` permits extra fields; `BadRequestError.__mro__` = `APIStatusError → APIError → OpenAIError → Exception`; `with_raw_response` and `with_streaming_response` accessors exist.
- **`/workspace/tools/analysis/gemini_video_analyzer.py`** (Phase 2 shipped) — template for BaseTool shape, error handling, prompt building, retry ladder, `_FLAT_SCHEMA` lazy-cache pattern, `validate_artifact` gate.
- **`/workspace/.agents/skills/gemini-video-analysis/SKILL.md`** (Phase 2 shipped, 340 lines) — template for Layer 3 skill shape, 8 sections, code examples, gotchas.
- **`/workspace/.planning/phases/02-gemini-provider/02-RESEARCH.md`** — deep domain context inherited (BaseTool contract, error taxonomy, schema adapter behavior, testing strategy).
- **`/workspace/.planning/phases/02-gemini-provider/02-*-PLAN.md`** — plan decomposition template (02-02 provider, 02-03 SKILL, 02-04 tests).

### Secondary (MEDIUM confidence — official docs, WebFetch-verified)
- **OpenRouter Video Inputs** — https://openrouter.ai/docs/guides/overview/multimodal/videos (verified: `"video_url"` content type; `data:video/mp4;base64,...` prefix; "Google AI Studio only YouTube links supported"; Vertex AI rejects video URLs; base64 recommended for local files; supported MIMEs mp4/mov/webm/mpeg).
- **OpenRouter Structured Outputs** — https://openrouter.ai/docs/guides/features/structured-outputs (verified: `response_format` shape with `type`/`json_schema`/`name`/`strict`/`schema`; `strict: true` recommended; `require_parameters: true` provider preference; models page filter `supported_parameters=structured_outputs`).
- **OpenRouter Gemini 3.1 Pro Preview model page** — https://openrouter.ai/google/gemini-3.1-pro-preview (verified: slug `google/gemini-3.1-pro-preview` is live; 1M context; multimodal text/image/video/audio/code).
- **OpenRouter Gemini 3 Pro Preview model page** — https://openrouter.ai/google/gemini-3-pro-preview (verified: slug exists as additional candidate).

### Tertiary (LOW confidence — WebSearch only, flagged for validation)
- Rate limit headers `X-RateLimit-Limit/Remaining/Reset` — from WebSearch; consistent across community sources but not directly shown in the pages fetched this session. Safe to assume but not load-bearing for Phase 3 (we don't depend on them).
- Exact HTTP code for "model doesn't support response_format" (most likely 400 `BadRequestError`) — WebFetch said "request will fail with an error indicating lack of support" but did NOT publish the status code. We catch `BadRequestError` broadly; planner must accept A4.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — openai SDK verified against installed 2.32.0; versions confirmed.
- Architecture: HIGH — parallels Phase 2 shape 1:1 with documented SDK surface; fallback ladder is an additive branch on an established pattern.
- Pitfalls: HIGH — all 8 pitfalls grounded in either Phase 2 lessons or SDK introspection.
- Assumptions: MEDIUM — 6 assumptions logged (A1..A6); none block the test suite; each has a graceful degradation path.
- Cross-provider consistency (ANLZ-06): HIGH — test strategy is mechanically straightforward (parametrize over provider + mock → deep-equal artifact).

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (30 days; openai SDK is stable, but OpenRouter docs move — re-verify fallback-error shape and cost body field if Phase 3 execution slips past this date).
