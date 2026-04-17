---
name: gemini-video-analysis
description: Analyze a local video file across 4 structured dimensions (editing_pacing, audio, visual_style, narrative) using the Google Gemini Files API with structured JSON output. Use when the agent has a reference video and needs a canonical `video_analysis` artifact for pipeline synthesis. Triggers include "analyze this video", "extract the grammar of this reference", reference-driven pipeline synthesis, and any call-site of `gemini_video_analyzer` or `video_analyzer_selector`.
---

# Gemini Video Analysis

Teaches the agent how to prompt Google Gemini to return a canonical `video_analysis` artifact (see `schemas/artifacts/video_analysis.schema.json`) with tight per-dimension grammar. All examples target the in-repo tool `tools/analysis/gemini_video_analyzer.py`; you should never re-implement the call path — invoke the tool (directly or via `video_analyzer_selector`) and tune the prompt via `analysis_depth` and `shot_boundaries`.

## Auth

**Primary:** `GEMINI_API_KEY` in `.env`. **Fallback:** `GOOGLE_API_KEY`. Our wrapper (`tools/analysis/gemini_video_analyzer.py::_get_api_key`) enforces `GEMINI_API_KEY` first, opposite of the `google-genai` SDK default. NEVER rely on the SDK env resolver — always pass the key explicitly to `genai.Client(api_key=...)`.

Get a key: <https://aistudio.google.com/apikey>

### Models

| Model | Role | When |
|-------|------|------|
| `gemini-3.1-pro-preview` | **Target** — highest quality for video | Default; tool uses this first |
| `gemini-2.5-pro` | Stable fallback | Auto-selected when preview raises `ClientError` (model-not-available) |
| `gemini-2.5-flash` | **NOT recommended** | Smaller context window; inadequate for 4-dimension analysis |

Env override: set `GEMINI_VIDEO_MODEL` to pin a specific model (still falls back to `gemini-2.5-pro` on `ClientError`). The tool returns the model that actually ran on `ToolResult.model` — the caller sees preview or fallback honestly.

## Files API — what to know

- **All videos** go through `client.files.upload(file=path)` regardless of size. The `google-genai` SDK does NOT use inline base64 for video, even below 20MB; everything is Files API.
- **48-hour auto-delete** by Google (defense-in-depth). The tool STILL deletes explicitly in a `finally:` block (`client.files.delete(name=...)`) to keep quota clean and prevent cross-run isolation drift.
- **2 GB per-file cap.** See <https://ai.google.dev/gemini-api/docs/files>.
- **Supported video formats:** `mp4`, `mov`, `mpeg`, `avi`, `flv`, `webm`, `wmv`, `3gp`.
- **State machine:** `PROCESSING → ACTIVE` (success) or `PROCESSING → FAILED` (error). No built-in polling helper — the tool owns the `while True:` loop with a configurable 300s wall-clock cap (`max_poll_seconds` input; backoff curve `1s → 2s → 5s → 5s-capped`).
- **Never pass the file path twice.** Use the `types.File` object returned by `upload()` as a `content[0]` — not the local path again — or Gemini will silently re-encode nothing useful.

## Structured JSON output

The tool uses `response_mime_type="application/json"` plus `response_json_schema` (the Phase 1 adapter's flattened form of `video_analysis.schema.json`). This is the deterministic path — `response.parsed` is NOT used because its behavior under truncation is implementation-defined.

```python
import json
from google import genai
from google.genai import types
from lib.schema_adapter import to_api_schema
from schemas.artifacts import load_schema

FLAT_SCHEMA = to_api_schema(load_schema("video_analysis"))

config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_json_schema=FLAT_SCHEMA,
)

response = client.models.generate_content(
    model="gemini-3.1-pro-preview",
    contents=[file_ref, prompt],
    config=config,
)

# Detect truncation BEFORE parsing — MAX_TOKENS means the JSON is incomplete.
if response.candidates[0].finish_reason == types.FinishReason.MAX_TOKENS:
    # Retry with analysis_depth="compact" — shorter descriptions, same schema.
    raise RuntimeError("retry with compact")

artifact = json.loads(response.text)
```

**Rules:**
- Do NOT use `response.parsed`. Use `json.loads(response.text)` directly — the explicit path is the one the tool tests.
- Always check `FinishReason.MAX_TOKENS` BEFORE parsing. A truncated JSON string is unparseable and its failure mode is noisy — catch it at the finish-reason level.
- Empty `response.text` is a failure too — treat it as a retry signal (the tool does).
- The flattened schema (no `$ref`, no `additionalProperties: false`, no `uniqueItems`) is required — Gemini rejects draft-2020-12 constructs. See `lib/schema_adapter.py::to_api_schema`.

## Per-dimension prompting

The canonical schema has 4 required top-level dimensions: `editing_pacing`, `audio`, `visual_style`, `narrative` (plus `version` const `"2.0"` and a `source` block). Each dimension has its own required keys and a free-form `confidence` map.

You do NOT paste a schema into the prompt — `response_json_schema` already constrains Gemini. Your job is to teach Gemini what each field MEANS so it fills them well.

### editing_pacing

Required keys: `total_shots`, `cuts_per_minute`, `avg_shot_duration_seconds`, `pacing_style` (enum), `shot_type_distribution`, `motion_type_distribution`.

**Shot boundaries:** if the caller supplied `shot_boundaries` (from `tools/analysis/scene_detect.py`), include them in the prompt as `"Shot boundaries (from scene_detect): 0.0-3.4s, 3.4-5.8s, ..."`. If absent, explicitly instruct Gemini to infer and set `shot_boundary_source: "model"` on the artifact (top-level field, per ANLZ-05). The tool's `_build_prompt` already does this — so callers don't need to duplicate the directive.

**Extraction example — BAD:**
```json
"editing_pacing": {
  "total_shots": 10,
  "cuts_per_minute": 12,
  "pacing_style": "fast"   // ← NOT IN ENUM; will fail schema
}
```

**Extraction example — GOOD:**
```json
"editing_pacing": {
  "total_shots": 24,
  "cuts_per_minute": 32.0,
  "avg_shot_duration_seconds": 1.87,
  "median_shot_duration_seconds": 1.5,
  "pacing_style": "rapid_fire",
  "shot_type_distribution": { "talking_head": 0.25, "b_roll": 0.65, "text_card": 0.1, "animation": 0.0 },
  "motion_type_distribution": { "motion_clip": 0.8, "animated_still": 0.2, "static_image": 0.0 },
  "transition_types": ["cut", "zoom_cut"],
  "confidence": { "cuts_per_minute": "high", "median_shot_duration_seconds": "low" }
}
```

**Gotchas:**
- `pacing_style` is a fixed enum: `slow_contemplative | steady_educational | dynamic_social | rapid_fire | variable`. Anything else is a schema violation.
- `cuts_per_minute` is a number (float OK), not an integer.
- `shot_type_distribution` ratios should sum to ~1.0, but this is NOT schema-enforced — the synthesizer normalizes downstream.
- `energy_arc` entries each need `timestamp_s` AND `energy_level` (enum `low|medium|high|peak`). Missing one → dropped entry.

### audio

Required keys: `has_narration`, `has_music`, `narration_style` (enum), `voice_music_mix` (enum).

In Phase 2 (single-chunk path, ≤5-min videos) Gemini analyzes audio holistically — one narration style, one mix rating. Phase 4 chunks longer videos, so prompts may need per-chunk audio aggregation; that aggregation happens AT the synthesis layer, not here.

**Extraction example — BAD:**
```json
"audio": {
  "has_narration": true,
  "has_music": true,
  "narration_style": "voiceover",        // ← not in enum (correct: "voice_over")
  "voice_music_mix": "narration heavy"   // ← not in enum (correct: "narration_dominant")
}
```

**Extraction example — GOOD:**
```json
"audio": {
  "has_narration": true,
  "narration_style": "voice_over",
  "speaker_count": 1,
  "voice_gender": "female",
  "voice_tone": "energetic",
  "narration_wpm": 175,
  "narration_language": "en",
  "has_music": true,
  "music_genre": "indie_electronic",
  "music_tempo_bpm": 128,
  "music_intensity": "moderate",
  "has_sfx": true,
  "sfx_style": "UI clicks + whoosh transitions",
  "voice_music_mix": "narration_dominant",
  "suggested_tts_voice_profile": "energetic female 25-35, conversational US English",
  "confidence": { "music_tempo_bpm": "medium", "narration_wpm": "high" }
}
```

**Gotchas:**
- `narration_style` enum: `voice_over | on_screen_presenter | dialogue_only | none`. Use `"none"` (string) if no narration — NOT absent.
- `voice_music_mix` enum: `narration_dominant | music_dominant | balanced`.
- `music_tempo_bpm` is `number | null`. If Gemini can't hear tempo (e.g., ambient drone), emit `null`. If there's no music at all, omit the field and put `music_tempo_bpm: "low"` in the `confidence` map.
- `narration_wpm` is a number (minimum 0). Gemini estimates; mark confidence `medium` or `low` unless the video is clearly scripted.
- Do NOT put SFX timestamps in the audio block — they're out of v2.0 scope.

### visual_style

Required keys: `color_palette` (object), `production_quality` (enum), `aspect_ratio` (enum).

**Extraction example — BAD:**
```json
"visual_style": {
  "color_palette": { "primary": ["dark blue"] },          // ← NOT HEX
  "dominant_colors_hex": ["navy", "gold"],                // ← NOT HEX
  "typography_style": "Helvetica Neue Bold"               // ← asserting a font family, NOT OK
}
```

**Extraction example — GOOD:**
```json
"visual_style": {
  "color_palette": {
    "primary":    ["#0A1F3D", "#E8B84A"],
    "accent":     ["#FF4D4D"],
    "background": ["#0A1F3D", "#000000"],
    "text":       ["#FFFFFF", "#E8B84A"]
  },
  "dominant_colors_hex": ["#0A1F3D", "#E8B84A", "#FF4D4D"],
  "color_temperature": "warm",
  "color_grading_style": "cinematic_grade",
  "background_treatment": "real_footage",
  "typography_style": "tall geometric sans-serif with ultra-tight tracking; all caps for titles",
  "typography_weight": "bold",
  "text_card_usage": "moderate",
  "motion_style": "spring_physics",
  "overlay_style": "lower_thirds",
  "production_quality": "professional",
  "aspect_ratio": "9:16",
  "confidence": { "color_grading_style": "medium", "motion_style": "low" }
}
```

**Gotchas:**
- **`typography_style` is a PROSE DESCRIPTION, never a font family name.** Gemini cannot reliably identify typefaces from pixels. Phrase it as "chunky geometric sans with rounded terminals", NOT "Gotham Rounded". The schema docstring enforces this convention — respect it.
- All colors MUST be hex strings like `#RRGGBB` or `#RGB`. Named colors ("navy", "gold") are a schema violation downstream.
- `aspect_ratio` enum: `16:9 | 9:16 | 1:1 | 4:3 | other`. Infer from resolution; if uncertain, emit `"other"` and flag confidence `low`.
- `production_quality` is holistic: `amateur | prosumer | professional | broadcast`. Anchor to lighting, audio floor, camera stability — not just color grading.
- `motion_style` enum includes `no_animation`. Use that literal value if static; do NOT emit `"static"` or `"none"`.

### narrative

Required keys: `hook_type` (enum), `narrative_arc` (enum), `target_platform` (enum), `target_duration_seconds`, `content_tone` (enum).

**Extraction example — BAD:**
```json
"narrative": {
  "hook_type": "question_hook",           // ← not in enum (correct: "question")
  "narrative_arc": "problem/solution",    // ← not in enum (correct: "problem_solution")
  "target_platform": "shorts",            // ← not in enum (correct: "youtube_shorts")
  "content_tone": "funny"                 // ← not in enum (correct: "humorous")
}
```

**Extraction example — GOOD:**
```json
"narrative": {
  "hook_type": "bold_claim",
  "hook_duration_seconds": 3.2,
  "narrative_arc": "problem_solution",
  "section_count": 4,
  "section_structure": [
    { "label": "hook",         "approx_start_s": 0.0,  "approx_end_s": 3.2,  "summary": "Bold claim about productivity." },
    { "label": "problem",      "approx_start_s": 3.2,  "approx_end_s": 14.8, "summary": "Reader's current pain, illustrated with b-roll." },
    { "label": "solution",     "approx_start_s": 14.8, "approx_end_s": 42.0, "summary": "Product demo, 3 feature highlights." },
    { "label": "cta",          "approx_start_s": 42.0, "approx_end_s": 48.0, "summary": "Visit link + follow CTA." }
  ],
  "cta_type": "visit_link",
  "cta_duration_seconds": 6.0,
  "target_platform": "youtube_shorts",
  "target_duration_seconds": 48.0,
  "information_density": "dense",
  "content_tone": "energetic",
  "confidence": { "section_structure": "medium", "cta_duration_seconds": "high" }
}
```

Wait — `content_tone` enum is `educational | entertaining | cinematic | corporate | casual | dramatic | inspirational | humorous`. "energetic" is NOT in the enum — use `entertaining` or `inspirational` depending on the video's intent. This is exactly the kind of slip Gemini makes; pin the enum in the prompt.

**Gotchas:**
- `hook_type` enum: `question | bold_claim | visual_shock | stat_drop | story_open | problem_statement | none`. Use `"none"` (string) if there's no identifiable hook — NOT absent.
- Hook is the FIRST 1-8 seconds. Anything past ~10s is not a hook, it's the body. If Gemini says `hook_duration_seconds: 15`, flag `confidence: "low"` and consider the hook to be `"none"`.
- `cta_type` enum: `subscribe | visit_link | purchase | follow | download | none_detected`. Use `none_detected` — NOT `"none"` or `null`.
- `target_platform` is inferred from aspect ratio + pacing + length. `9:16 + <60s` → `youtube_shorts | tiktok | instagram_reels`; pick one and flag `confidence: "medium"` if uncertain.
- `section_structure[].approx_end_s` MUST be ≥ `approx_start_s` (not schema-enforced, but the synthesizer barfs otherwise).

## Confidence maps — always emit "low", never omit

The schema lets each dimension carry a `confidence` map: `field_name → "low" | "medium" | "high"`. Gemini's natural behavior is to OMIT fields it's unsure about. That breaks the downstream synthesizer, which expects completeness with calibrated uncertainty.

**The rule (ANLZ-04):** every uncertain or absent field gets an entry in the dimension's `confidence` map with value `"low"`. NEVER omit a required field. NEVER emit `null` for a required field.

```json
"editing_pacing": {
  "total_shots": 24,
  "cuts_per_minute": 32.0,
  "avg_shot_duration_seconds": 1.87,
  "pacing_style": "rapid_fire",
  "shot_type_distribution": { "talking_head": 0.3, "b_roll": 0.7 },
  "motion_type_distribution": { "motion_clip": 1.0 },
  "confidence": {
    "cuts_per_minute": "high",
    "pacing_style": "medium",
    "shot_length_variance": "low"
  }
}
```

The tool's `_build_prompt` already emits this directive verbatim:

> _"For EVERY uncertain or absent field, populate the dimension's confidence map with the field-name -> \"low\" entry (never omit a field and never emit null). Use \"medium\" or \"high\" only when you are genuinely confident in the value."_

If you are writing a CUSTOM prompt (not via the tool), copy that sentence in. It is load-bearing.

**Read pattern for downstream agents:**
```python
conf = artifact["editing_pacing"].get("confidence", {})
if conf.get("pacing_style") == "low":
    # Don't trust pacing_style for synthesis — degrade gracefully
    ...
```

## Timecode hallucination (>5 min videos)

**Warning:** Gemini occasionally hallucinates round-number timecodes — e.g., `30.0s`, `60.0s`, `90.0s`, `120.0s` — past the 5-minute mark when it cannot actually see scene boundaries. This shows up most in `editing_pacing.energy_arc` and `narrative.section_structure[].approx_start_s`.

**Mitigation (two layers):**
1. **If `source.duration_seconds > 300`: always supply `shot_boundaries`** from `tools/analysis/scene_detect.py`. The tool inlines them in the prompt. Boundaries anchor Gemini to real cut points; without them, it free-associates.
2. **If you can't supply boundaries:** flag the artifact's `editing_pacing.confidence` with `energy_arc: "low"` and `narrative.confidence` with `section_structure: "low"`. Downstream synthesis will weight them accordingly.

Phase 4 introduces chunking for `>5 min` videos: each chunk is ≤5 minutes and analyzed independently, then a chunk-aware aggregator combines results with per-chunk timecodes anchored to chunk start offsets (provider writes `chunking_metadata` on the artifact). In that flow, this warning applies per-chunk — but since chunks are ≤5 min, the hallucination risk is near-zero per call.

**Phase 2 scope reminder:** the gemini-direct tool is single-chunk only. Hand it videos ≤5 min. Longer videos MUST go through the Phase 4 chunking path.

## Security

- **Never log or include the API key** in any prompt, error message, ToolResult field, or debug output. The tool's error strings are constructed to never interpolate `str(exc)` from the SDK constructor without review — `str(exc)` from `google-genai` does not contain the raw key in normal failure modes, but keep prompts key-free.
- **Uploaded videos auto-delete at 48h.** The tool deletes sooner (`finally:` block) to prevent quota/isolation drift. Do not rely on the 48h auto-delete for privacy — delete explicitly.
- **`video_path` is trusted input** from the OpenMontage agent layer. Single-tenant; no sandboxing. Do NOT expose the tool to untrusted external callers without adding a path-traversal guard.
- **Do NOT paste a real API key into SKILL.md examples.** Use `os.environ["GEMINI_API_KEY"]` or `"YOUR_KEY_HERE"`.

## Before you call the tool

- [ ] `GEMINI_API_KEY` set in `.env` (fallback `GOOGLE_API_KEY` OK but discouraged)
- [ ] Video is ≤ 5 min (Phase 2 single-chunk path) OR routed through Phase 4 chunking
- [ ] Video format in `{mp4, mov, mpeg, avi, flv, webm, wmv, 3gp}` and < 2 GB
- [ ] `analysis_depth="full"` unless you explicitly want the compact retry variant (terser field descriptions; same schema)
- [ ] For videos > 5 min inside a chunk-aware wrapper: supply `shot_boundaries` from `scene_detect`
- [ ] Expect `ToolResult.model` to reflect the model that actually ran (`gemini-3.1-pro-preview` on happy path, `gemini-2.5-pro` on fallback)
- [ ] Caller writes the pipeline checkpoint (`lib/checkpoint.py::write_checkpoint`); the tool does NOT

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
    "preferred_provider": "auto",
    "max_poll_seconds": 300.0,
})

if result.success:
    artifact = result.data  # validated against video_analysis.schema.json
    model_used = result.model  # "gemini-3.1-pro-preview" or "gemini-2.5-pro"
else:
    # error is one of: VideoUploadError, VideoAnalysisRetryExhausted,
    # VideoAnalysisError, schema validation failure, Gemini APIError
    raise RuntimeError(result.error)
```

Prefer the selector (`video_analyzer_selector`) to the direct tool (`gemini_video_analyzer`) — it future-proofs against Phase 3 (OpenRouter provider) and keeps ANLZ-06 intact (caller cannot tell which backend ran from the artifact alone).
