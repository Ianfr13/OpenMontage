---
name: openrouter-video-analysis
description: Analyze a local video file across 4 structured dimensions (editing_pacing, audio, visual_style, narrative) using OpenRouter's OpenAI-compatible chat completions API with inline base64 video. Use when the agent wants provider-portable analysis (swap underlying model via OPENROUTER_MODEL env) or when GEMINI_API_KEY is unavailable but OPENROUTER_API_KEY is present. Triggers include reference-driven pipeline synthesis via OpenRouter, any call-site of `openrouter_video_analyzer`, and selector calls with `VIDEO_ANALYZER_PROVIDER=openrouter` or `preferred_provider="openrouter"`.
---

# OpenRouter Video Analysis

Teaches the agent how to prompt OpenRouter (via the `openai>=1.0` SDK pointed at `https://openrouter.ai/api/v1`) to return a canonical `video_analysis` artifact (see `schemas/artifacts/video_analysis.schema.json`) with the same 4-dimension grammar as the Gemini path. All examples target the in-repo tool `tools/analysis/openrouter_video_analyzer.py`; you should never re-implement the call path — invoke the tool (directly or via `video_analyzer_selector`) and tune the prompt via `analysis_depth` and `shot_boundaries`.

OpenRouter differs from Gemini direct in ways that matter for correctness, not just stylistically. Read the `OpenRouter quirks` section below BEFORE copy-pasting any code from the Gemini skill.

## Auth

**Primary (and only):** `OPENROUTER_API_KEY` in `.env`. There is NO fallback env var — unlike Gemini's `GEMINI_API_KEY` / `GOOGLE_API_KEY` pair.

Our wrapper (`tools/analysis/openrouter_video_analyzer.py::_get_api_key`) reads `OPENROUTER_API_KEY` and passes it explicitly:

```python
OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1")
```

**Common mistake to avoid — the SDK's default auth is wrong for us.** The `openai` SDK's zero-arg `OpenAI()` constructor reads `OPENAI_API_KEY`, NOT `OPENROUTER_API_KEY`. If you ever write new code against the SDK for OpenRouter, always pass `api_key=` explicitly. A test that happens to have `OPENAI_API_KEY` set in the environment will PASS silently while production (where only `OPENROUTER_API_KEY` is set) fails with a 401. Do not rely on the SDK env resolver.

Get a key: <https://openrouter.ai/settings/keys>. Real keys match the pattern `sk-or-v1-[a-f0-9]{40,}` — NEVER paste one into this file, a prompt, a log, or an error string. The Phase 3 contract test scans this SKILL for that regex and fails on any match.

### Models

| Model slug | Role | `response_format=json_schema` (strict) |
|------------|------|----------------------------------------|
| `google/gemini-3.1-pro-preview` | **Default** — happiest path, highest quality | Works |
| `google/gemini-2.5-pro` | Alternative | Works |
| `google/gemini-2.5-flash` | NOT recommended | Works but context window too small for 4-dim analysis |
| `anthropic/claude-*` | Alternative | Route-dependent; expect fallback branch to fire (not a bug) |
| Other providers | Variable | Check <https://openrouter.ai/models?supported_parameters=structured_outputs> |

Env override: set `OPENROUTER_MODEL` to pin a specific slug. Format is always `vendor/model-name`. The tool returns the model that actually ran on `ToolResult.model` — **note that OpenRouter rewrites `resp.model` to the underlying provider's model ID** (e.g., you request `google/gemini-3.1-pro-preview` and `resp.model` comes back as `gemini-3.1-pro-preview-20XX-MM-DD` from AI Studio). The tool stores `resp.model` verbatim; callers should NOT normalize it back to the requested slug.

## OpenRouter quirks — what to know

- **Video input is INLINE BASE64 ONLY on the Gemini route.** OpenRouter → Google AI Studio rejects `video_url` values that are HTTP URLs (only YouTube URLs are accepted, which is not a path OpenMontage uses). Vertex AI route rejects URLs too. The tool therefore always encodes `data:<mime>;base64,<payload>`. There is no Files API equivalent, and no cleanup step — the base64 payload lives only in the request body and is not retained server-side by OpenRouter.
- **Default `max_upload_bytes = 20 MB`** (configurable per-call via the tool's `max_upload_bytes` input). Clamped to `[1, 2 GB]` hard cap. Oversize files are rejected BEFORE encoding to avoid pointless memory burn.
- **Supported video MIMEs:** `video/mp4`, `video/quicktime` (.mov), `video/webm`, `video/mpeg`. Other types are rejected before encoding. Extension → MIME guessing uses stdlib `mimetypes.guess_type`; missing types default to `video/mp4`.
- **Base64 memory footprint:** full-buffer encode adds ~1.33× overhead. At the 20 MB default that's ~50 MB peak RAM — trivial. At 200 MB+ (which we'd reject anyway) it's 500 MB+ — OOM territory. Keep videos under the default cap or chunk them (Phase 4).
- **`resp.model` reflects the underlying provider's model ID**, not the OpenRouter slug. Don't normalize it — `ToolResult.model` carries the real model that ran.
- **`client.close()` is NOT needed** (openai SDK manages context internally); no Files API cleanup either.
- **`video_url` content-part type is NOT in the SDK's TypedDict union.** At runtime the SDK accepts raw dicts for `messages=`, so we pass `{"type": "video_url", "video_url": {"url": data_url}}` verbatim. Static type checkers will complain; add `# type: ignore[list-item]` or `cast(Any, messages)` if strict typing matters.
- **Do NOT use `client.beta.chat.completions.parse()`.** That path is OpenAI-specific and does not play well with OpenRouter's multi-provider routing. Stick to `client.chat.completions.create()` + `json.loads(content)`.

## Structured JSON output — the happy path

The tool uses OpenRouter's `response_format={"type": "json_schema", ...}` with `strict: True`, plus the `require_parameters` provider preference to force selection of a route that actually honors the constraint.

```python
import os
import json
from openai import OpenAI
from lib.schema_adapter import to_api_schema
from schemas.artifacts import load_schema

FLAT_SCHEMA = to_api_schema(load_schema("video_analysis"))

client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],   # explicit — SDK default reads OPENAI_API_KEY
    base_url="https://openrouter.ai/api/v1",
    default_headers={
        "HTTP-Referer": "https://github.com/openmontage",
        "X-Title": "OpenMontage",
    },
)

resp = client.chat.completions.create(
    model="google/gemini-3.1-pro-preview",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "video_url", "video_url": {"url": data_url}},   # data:video/mp4;base64,...
            ],
        }
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "video_analysis",
            "schema": FLAT_SCHEMA,
            "strict": True,
        },
    },
    # OpenRouter-specific: force providers that HONOR response_format (Pitfall 4 mitigation)
    extra_body={"provider": {"require_parameters": True}},
)

# Truncation check is STRING equality — NOT an enum
if resp.choices[0].finish_reason == "length":
    # Retry with analysis_depth="compact" — shorter prompts, tighter descriptions
    raise RuntimeError("retry with compact")

content = resp.choices[0].message.content or ""
artifact = json.loads(content)
```

**Rules:**
- `response_format={"type": "json_object"}` is allowed by OpenRouter but is WEAKER than `json_schema` with `strict=True`. Always prefer json_schema when the route supports it.
- `extra_body` is OpenRouter-specific and passed through by the openai SDK verbatim. Do NOT put `response_format` inside `extra_body` — it is a first-class `create()` kwarg in `openai>=1.0`. `extra_body` is ONLY for OpenRouter-specific routing controls (`provider`, `transforms`, etc.).
- The flattened schema (no `$ref`, no `additionalProperties: false`, no `uniqueItems`) is required — some OpenRouter routes reject draft-2020-12 constructs. See `lib/schema_adapter.py::to_api_schema`.
- Always check `finish_reason == "length"` and empty `message.content` BEFORE parsing. A truncated JSON string is unparseable and its failure mode is noisy — catch it at the finish-reason level.

## Fallback — when the model rejects response_format

Some OpenRouter routes (notably some `anthropic/claude-*` variants) return `BadRequestError` when handed `response_format={"type":"json_schema"}`. The tool catches that narrowly and falls back to a prompt-embedded schema + post-hoc `jsonschema.validate`.

```python
import json
from openai import BadRequestError
import jsonschema

try:
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "video_analysis", "schema": FLAT_SCHEMA, "strict": True},
        },
        extra_body={"provider": {"require_parameters": True}},
    )
except BadRequestError:
    # Route doesn't support structured outputs — fall back to schema-in-prompt.
    prompt_with_schema = (
        prompt
        + "\n\nYour response MUST match this schema (return ONLY the JSON "
        "object, no prose, no markdown fences):\n```json\n"
        + json.dumps(FLAT_SCHEMA, indent=2)
        + "\n```"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_with_schema},
                    {"type": "video_url", "video_url": {"url": data_url}},
                ],
            }
        ],
        # NOTE: no response_format, no extra_body on the fallback — don't over-constrain.
    )
    artifact = json.loads(resp.choices[0].message.content)
    # Post-hoc validation is CRITICAL on this path — the model may not honor the embedded schema.
    jsonschema.validate(artifact, FLAT_SCHEMA)
```

**Common mistake:** catching every 4xx as "unsupported structured output." Only `BadRequestError` (400) should trigger the fallback.

- `AuthenticationError` (401) → bad key → surface immediately, do NOT fall back.
- `PermissionDeniedError` (403) → model access / quota → surface immediately.
- `RateLimitError` (429) → surface immediately (SDK retries handle transient cases).
- `APITimeoutError` / 5xx → SDK's own `max_retries` handles these.

A silent fallback on any of these masks real configuration errors. Log `exc.code` before the fallback fires so regressions are visible in logs.

`jsonschema.validate` is essential on the fallback path. Prefer the canonical `validate_artifact("video_analysis", artifact)` (from `schemas/artifacts/__init__.py`) — it is stricter than the flat schema.

## Per-dimension prompting

The canonical schema has 4 required top-level dimensions: `editing_pacing`, `audio`, `visual_style`, `narrative` (plus `version` const `"2.0"` and a `source` block). Each dimension has its own required keys and a free-form `confidence` map.

You do NOT paste a schema into the prompt on the happy path — `response_format=json_schema` already constrains the model. Your job is to teach it what each field MEANS so it fills them well. On the fallback path the schema IS in the prompt (by necessity), but you still teach meaning through the text directives.

### editing_pacing

Required keys: `total_shots`, `cuts_per_minute`, `avg_shot_duration_seconds`, `pacing_style` (enum), `shot_type_distribution`, `motion_type_distribution`.

**Shot boundaries:** if the caller supplied `shot_boundaries` (from `tools/analysis/scene_detect.py`), the tool inlines them in the prompt as `"Shot boundaries (from scene_detect): 0.0-3.4s, 3.4-5.8s, ..."`. If absent, the prompt instructs the model to infer and set `shot_boundary_source: "model"` on the artifact (per ANLZ-05).

**Extraction example — BAD:**
```json
"editing_pacing": {
  "cuts_per_minute": 12,
  "pacing_style": "fast"
}
```
`"fast"` is NOT in the enum; schema validation rejects it. The `json_schema` happy path usually prevents this; the fallback path does not, which is why post-hoc `validate_artifact` is mandatory.

**Extraction example — GOOD:**
```json
"editing_pacing": {
  "total_shots": 24,
  "cuts_per_minute": 32.0,
  "avg_shot_duration_seconds": 1.87,
  "pacing_style": "rapid_fire",
  "shot_type_distribution": { "talking_head": 0.25, "b_roll": 0.65, "text_card": 0.10, "animation": 0.0 },
  "motion_type_distribution": { "motion_clip": 0.8, "animated_still": 0.2, "static_image": 0.0 },
  "confidence": { "cuts_per_minute": "high", "pacing_style": "medium" }
}
```

**Gotcha:** OpenRouter routes may truncate reasoning about many shots on long videos. Pre-computed `shot_boundaries` anchor the model and reduce truncation — prefer them for videos with 20+ cuts.

### audio

Required keys: `has_narration`, `has_music`, `narration_style` (enum), `voice_music_mix` (enum).

Model holistic-audio inference works for ≤20 MB videos (default inline cap). Phase 4 chunking will change the weighting strategy for longer videos — aggregation happens at the synthesis layer, not here.

**Gotchas:**
- `narration_style` enum: `voice_over | on_screen_presenter | dialogue_only | none`. Use `"none"` (string) if no narration — NOT absent.
- `voice_music_mix` enum: `narration_dominant | music_dominant | balanced`.
- `music_tempo_bpm` is `number | null`. If the model can't hear tempo (e.g., ambient drone), emit `null`. If there's no music at all, omit the field.
- `narration_wpm` is a number ≥ 0. The model estimates — mark confidence `medium` or `low` unless the video is clearly scripted.

### visual_style

Required keys: `color_palette` (object), `production_quality` (enum), `aspect_ratio` (enum).

**Gotchas:**
- **`typography_style` is a PROSE DESCRIPTION, never a font family name.** Vision models cannot reliably identify typefaces from pixels. Phrase it as "chunky geometric sans with rounded terminals", NOT "Gotham Rounded".
- All colors MUST be hex strings like `#RRGGBB` or `#RGB`. Named colors ("navy", "gold") are a schema violation downstream.
- `aspect_ratio` enum: `16:9 | 9:16 | 1:1 | 4:3 | other`. Infer from resolution; if uncertain, emit `"other"` and flag confidence `low`.
- `motion_style` enum includes `no_animation`. Use that literal value if static; do NOT emit `"static"` or `"none"`.

### narrative

Required keys: `hook_type` (enum), `narrative_arc` (enum), `target_platform` (enum), `target_duration_seconds`, `content_tone` (enum).

**Gotchas:**
- `hook_type` enum: `question | bold_claim | visual_shock | stat_drop | story_open | problem_statement | none`. Use `"none"` (string) if there's no identifiable hook — NOT absent.
- Hook is the FIRST 1-8 seconds. Anything past ~10s is not a hook, it's the body. If the model says `hook_duration_seconds: 15`, flag `confidence: "low"` and consider the hook to be `"none"`.
- `cta_type` enum: `subscribe | visit_link | purchase | follow | download | none_detected`. Use `none_detected` — NOT `"none"` or `null`.
- `content_tone` enum: `educational | entertaining | cinematic | corporate | casual | dramatic | inspirational | humorous`. "energetic" is NOT in this enum — use `entertaining` or `inspirational` depending on the video's intent. This is exactly the kind of slip the model makes; the json_schema constraint catches it on the happy path, but the fallback path can emit enum-violating values that post-hoc validation must reject.
- `section_structure[].approx_end_s` MUST be ≥ `approx_start_s` (not schema-enforced, but the synthesizer barfs otherwise).

## Truncation, cost, and the "don't trust the enum" trap

> **Gotcha (differs from Gemini):** The openai SDK's `Choice.finish_reason` is typed `Literal['stop', 'length', 'tool_calls', 'content_filter', 'function_call']`. At runtime it is a **plain string**, not an enum. Code like `if finish_reason == FinishReason.MAX_TOKENS:` copy-pasted from the Gemini skill will always be False against OpenRouter responses — retries will never fire and truncated JSON will crash downstream parsing. Use `if finish_reason == "length":` — string equality.

The Gemini tool uses `types.FinishReason.MAX_TOKENS` because `google-genai` returns a real enum. The OpenRouter tool uses `== "length"` because the openai SDK returns a `Literal[str]` (which at runtime is the string `"length"`). `FinishReason.MAX_TOKENS` does NOT exist in the openai SDK; do not import it and do not try to compare against it.

The tool's `_run_once` also treats empty `message.content` as truncation — the model sometimes returns an empty string with `finish_reason="stop"` under resource pressure. Both conditions raise `VideoAnalysisError` which triggers the compact-depth retry at the `_analyze_with_fallback` level.

**Confidence-map discipline (ANLZ-04 — schema-universal, same as Gemini):**

The schema lets each dimension carry a `confidence` map: `field_name → "low" | "medium" | "high"`. The model's natural behavior is to OMIT fields it's unsure about. That breaks the downstream synthesizer, which expects completeness with calibrated uncertainty.

**The rule:** every uncertain or absent field gets an entry in the dimension's `confidence` map with value `"low"`. NEVER omit a required field. NEVER emit `null` for a required field.

```json
"editing_pacing": {
  "cuts_per_minute": 32.0,
  "pacing_style": "rapid_fire",
  "confidence": {
    "cuts_per_minute": "high",
    "pacing_style": "medium",
    "shot_length_variance": "low"
  }
}
```

The tool's `_build_prompt` emits this directive verbatim:

> _"For EVERY uncertain or absent field, populate the dimension's confidence map with the field-name -> \"low\" entry (never omit a field and never emit null). Use \"medium\" or \"high\" only when you are genuinely confident in the value."_

If you are writing a CUSTOM prompt (not via the tool), copy that sentence in. It is load-bearing.

## Cost

Cost surfaces in the response **BODY** via `response.usage.cost`. This is an OpenRouter-specific extra field on the standard `CompletionUsage` pydantic model (which permits extras).

```python
# CORRECT — cost is in the response BODY on the usage object (OpenRouter extra field)
usage = getattr(resp, "usage", None)
cost_usd = float(getattr(usage, "cost", 0.0) or 0.0)

# WRONG — x-openrouter-credit-remaining is NOT a documented header.
# Any code referencing it is stale / copy-pasted from community lore.
# Do NOT do this:
#   resp.response.headers["x-openrouter-credit-remaining"]   # <- this header doesn't exist
```

> **Warning:** `x-openrouter-credit-remaining` is NOT a real OpenRouter response header. It appears in some community code examples but is NOT documented by OpenRouter. The only rate-related headers OpenRouter exposes are the standard `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (and only some routes set them). For per-call cost, use `response.usage.cost` — OpenRouter adds this as an extra field on the standard `CompletionUsage` shape; pydantic preserves it via `model_extra`. Use `getattr(usage, "cost", 0.0)` defensively so mocks without a usage attribute don't crash.

## Timecode hallucination (>5 min videos)

**Warning:** Gemini-backed models (which is what the default `google/gemini-3.1-pro-preview` route is) occasionally hallucinate round-number timecodes — e.g., `30.0s`, `60.0s`, `90.0s`, `120.0s` — past the 5-minute mark when they cannot actually see scene boundaries. This shows up most in `editing_pacing.energy_arc` and `narrative.section_structure[].approx_start_s`. The behavior carries through OpenRouter because OpenRouter is a thin routing layer — the model is the source of the hallucination, not the API path.

**Mitigation (two layers — same as Gemini skill):**
1. **If `source.duration_seconds > 300`: always supply `shot_boundaries`** from `tools/analysis/scene_detect.py`. The tool inlines them in the prompt. Boundaries anchor the model to real cut points; without them, it free-associates.
2. **If you can't supply boundaries:** flag the artifact's `editing_pacing.confidence` with `energy_arc: "low"` and `narrative.confidence` with `section_structure: "low"`. Downstream synthesis will weight them accordingly.

Phase 4 introduces chunking for `>5 min` videos: each chunk is ≤5 minutes and analyzed independently, then a chunk-aware aggregator combines results with per-chunk timecodes anchored to chunk start offsets. In that flow this warning applies per-chunk — and since chunks are ≤5 min, the hallucination risk is near-zero per call.

**Phase 3 scope reminder:** the openrouter-direct tool is single-chunk only. Hand it videos ≤5 min (and ≤20 MB at the default cap). Longer videos MUST go through the Phase 4 chunking path.

## Security

- **Never log or include `OPENROUTER_API_KEY`** in any prompt, error message, `ToolResult` field, or debug output. The tool's error strings are constructed so `str(exc)` from the openai SDK never leaks the raw key in normal failure modes — but keep prompts key-free and never f-string the key anywhere.
- **Real OpenRouter keys match `sk-or-v1-[a-f0-9]{40,}`.** The Phase 3 contract test scans this SKILL for that regex and fails if any match. Use `os.environ["OPENROUTER_API_KEY"]` or the placeholder `"YOUR_KEY_HERE"` in all examples.
- **No server-side file state to clean up** — inline base64 has no equivalent of Gemini's 48h auto-delete. The base64 payload is in the HTTP request body only.
- **Cost-exhaustion DoS is mitigated ONLY by the `max_upload_bytes` gate** (default 20 MB, clamped to `[1, 2 GB]`). Size it appropriately per deployment — too high and a malicious input can rack up credits; too low and legitimate references are rejected. The tool rejects BEFORE encoding, so oversize inputs never hit the network.
- **`video_path` is trusted input** from the OpenMontage agent layer. Single-tenant; no sandboxing. Do NOT expose the tool to untrusted external callers without adding a path-traversal guard. (Same disposition as Phase 2's T-02-10.)
- **Artifact schema validation** runs via `validate_artifact("video_analysis", artifact)` BEFORE the tool returns. Prompt-injection-shaped responses that violate the schema are rejected at this gate.

## Before you call the tool

- [ ] `OPENROUTER_API_KEY` set in `.env` (format `sk-or-v1-...` — and NEVER commit one)
- [ ] Video is ≤ 20 MB (default `max_upload_bytes`) or within your override; supported MIME (`mp4`, `mov`, `webm`, `mpeg`)
- [ ] `analysis_depth="full"` unless you explicitly want the compact retry variant
- [ ] For videos > 5 min: go through Phase 4 chunking — NOT this tool directly
- [ ] Expect `ToolResult.model` to reflect the PROVIDER'S model ID (e.g., `gemini-3.1-pro-preview-20XX-MM-DD`), not the OpenRouter slug
- [ ] Caller writes the pipeline checkpoint (`lib/checkpoint.py::write_checkpoint`); the tool does NOT
- [ ] If swapping `OPENROUTER_MODEL`, confirm structured_outputs support at <https://openrouter.ai/models?supported_parameters=structured_outputs> or expect the fallback branch to fire

## Invocation

```python
from tools.tool_registry import registry

registry.discover()
selector = registry.get("video_analyzer_selector")
result = selector.execute({
    "video_path": "tests/fixtures/short_sample.mp4",
    # Optional:
    "shot_boundaries": [[0.0, 3.4], [3.4, 5.8], [5.8, 9.2]],
    "analysis_depth": "full",
    "preferred_provider": "openrouter",   # or leave "auto" and set VIDEO_ANALYZER_PROVIDER=openrouter
    "max_upload_bytes": 20 * 1024 * 1024,
})

if result.success:
    artifact = result.data       # validated against video_analysis.schema.json
    model_used = result.model    # the provider's actual model ID
    cost_usd = result.cost_usd   # from response.usage.cost body field
else:
    # error is one of: VideoUploadError, VideoAnalysisRetryExhausted,
    # VideoAnalysisError, schema validation failure, OpenRouter APIError
    raise RuntimeError(result.error)
```

Prefer the selector (`video_analyzer_selector`) to the direct tool (`openrouter_video_analyzer`) — it keeps ANLZ-06 intact (the caller cannot tell which backend ran from the artifact alone) and lets `VIDEO_ANALYZER_PROVIDER` / `preferred_provider` swap providers without touching call sites.
