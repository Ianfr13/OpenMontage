# Technology Stack — v2.0 Reference Synthesis

**Project:** OpenMontage  
**Milestone:** v2.0 Reference Synthesis (video_analysis capability + pipeline_synthesizer)  
**Researched:** 2026-04-17  
**Scope:** New additions only. Existing validated stack (Python 3.10+, Node 18+, FFmpeg, Remotion, Pydantic, jsonschema, PyYAML, requests) is NOT re-documented here.

---

## Summary

Three dependency additions are required. No changes to existing deps.

1. **`google-genai`** — the single official Google Gen AI Python SDK (replaces the older `google-generativeai`). Provides the Gemini Files API, multimodal content generation, and structured JSON output mode.
2. **`ruamel.yaml`** — YAML 1.2-compliant writer for safe, comment-preserving pipeline manifest emission. PyYAML (already in `requirements.txt`) is insufficient for safe round-trip writes.
3. **`jsonschema`** — already present at `>=4.20`. No addition needed; `validate()` covers pipeline manifest validation.

---

## New Dependencies

| Package | Version Pin | Purpose | Install |
|---------|-------------|---------|---------|
| `google-genai` | `>=1.73.0` | Gemini Files API + multimodal generation + structured JSON output | `pip install google-genai` |
| `ruamel.yaml` | `>=0.18.0` | YAML 1.2 writer for safe pipeline manifest emission | `pip install ruamel.yaml` |

### What NOT to add

- `google-generativeai` — this is the deprecated 0.x SDK. The new SDK is `google-genai`. Do not add both; they conflict.
- `opencv-python` or `ffmpeg-python` for video pre-processing — FFmpeg CLI is already used via `run_command()`; no new Python video binding needed for the upload path.
- Any async HTTP library (httpx, aiohttp) — `google-genai` 1.x includes async support internally; the synchronous `client.models.generate_content()` path is sufficient for this milestone.
- `instructor` — wraps Gemini for structured output but adds a dependency layer. The native `response_json_schema` parameter in `google-genai` 1.x is sufficient and avoids the extra dep.

---

## Gemini 2.5 Pro API Details

### Model ID

`gemini-2.5-pro` (stable, as of 2026-04-17)

Do NOT use `gemini-3-flash-preview` or other preview strings seen in some SDK docs — those are example placeholders. Confirm the production model ID at https://ai.google.dev/gemini-api/docs/models before first deploy.

### Client Initialization

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
```

Auth follows the existing `lib/env_loader.py` pattern — `require_env("GEMINI_API_KEY")` raises `EnvError` with a useful message if the key is absent. The `gemini_video_analyzer` tool declares `dependencies = ["env:GEMINI_API_KEY"]` so registry status is `UNAVAILABLE` without the key.

### Video Input: Files API vs Inline

| Method | When to use | Size limit |
|--------|-------------|------------|
| **Files API** (`client.files.upload()`) | All videos for Gemini 2.5+; mandatory when total request > 20 MB | 2 GB (free tier) / 20 GB (paid) |
| **Inline base64** (`inline_data`) | Only sub-20 MB files, non-video analysis tasks | < 20 MB total request |

**For this tool: always use Files API.** Gemini 2.5 series models work exclusively with Files API for video (community-confirmed behavior). Inline video is unreliable on 2.5 Pro.

### Files API Upload Pattern

```python
import time
from google import genai

def upload_and_wait(client: genai.Client, video_path: str) -> object:
    """Upload video to Files API and wait for ACTIVE state."""
    video_file = client.files.upload(file=video_path)
    
    while video_file.state.name != "ACTIVE":
        time.sleep(5)
        video_file = client.files.get(name=video_file.name)
    
    return video_file
```

Files are stored for 48 hours then auto-deleted. The tool should call `client.files.delete(name=video_file.name)` after the analysis is complete to avoid quota leakage across project runs.

### Supported Video Formats

MP4, MPEG, MOV (QuickTime), AVI, FLV, MPG, WebM, WMV, 3GPP.

For the `gemini_video_analyzer` tool, the recommended pre-processing decision is:

- **Local files:** Pass directly if format is in the supported list. No transcoding needed.
- **Already-downloaded files from `VideoDownloader`:** Already 720p MP4 — pass directly.
- **Edge case (unsupported format):** Use FFmpeg `run_command()` to re-mux to MP4 before upload. No re-encoding needed (`-c copy`), which is near-instant.

No chunking is required. Gemini 2.5 Pro supports up to 1 hour of video in a single request (3 hours at low media resolution). For this use case (1–10 minute reference videos), chunking is never needed.

### Structured Output (JSON Schema Mode)

Use `response_json_schema` with the Pydantic model's `.model_json_schema()` output, or pass the raw dict schema directly. Both work.

```python
response = client.models.generate_content(
    model="gemini-2.5-pro",
    contents=[video_file, analysis_prompt],
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=VideoAnalysisResult.model_json_schema(),
    ),
)
result = json.loads(response.text)
```

The alternative `response_schema=VideoAnalysisResult` (passing the Pydantic class, not its schema) also works but triggers Gemini-side schema conversion which can drop nested `$defs`. Prefer `.model_json_schema()` for complex nested schemas.

**Note on `response_schema` vs `response_json_schema`:** SDK 1.x introduced `response_json_schema` for passing raw dict schemas. Earlier examples show `response_schema`. Both are supported in 1.73.x; `response_json_schema` is the more explicit form and preferred here.

### Streaming vs Batch

Use **batch (non-streaming)** for `gemini_video_analyzer`. Video analysis is a single-shot structured extraction; streaming adds complexity without benefit since the caller needs the complete JSON before proceeding to `pipeline_synthesizer`. The `generate_content()` call blocks until the response is complete, which is the correct behavior here.

Streaming (`generate_content_stream()`) is only warranted for UX responsiveness in long free-text generation — not applicable here.

### Video Tokenization Rate

| Resolution | Tokens per second | Audio |
|------------|-------------------|-------|
| Default | 263 tokens/sec | +32 tokens/sec |
| Low | ~100 tokens/sec | +32 tokens/sec |

Source: official Gemini token counting docs. A 1-minute video at default resolution = ~(263 + 32) × 60 = **~17,700 input tokens**.

### Context Window

Gemini 2.5 Pro: **1M token context window** (HIGH confidence — verified via multiple sources). The 200k pricing tier boundary is a cost threshold, not a hard limit.

Max output tokens: 8,192 (typical) to 64k (with extended thinking). For structured JSON output of a video analysis schema, output will be 2–5k tokens.

---

## Cost & Quota Notes

### Gemini 2.5 Pro Pricing (April 2026, verified)

| Tier | Input | Output |
|------|-------|--------|
| Prompts ≤ 200k tokens | $1.25 / 1M tokens | $10.00 / 1M tokens |
| Prompts > 200k tokens | $2.50 / 1M tokens | $15.00 / 1M tokens |
| Batch API | $0.625 / 1M tokens (≤ 200k) | $5.00 / 1M tokens |

Source: https://ai.google.dev/gemini-api/docs/pricing

### Typical Analysis Cost (1–3 min video)

| Video Duration | Input Tokens | Input Cost | Output (~3k tokens) | Total |
|----------------|-------------|------------|----------------------|-------|
| 1 min | ~17,700 | ~$0.022 | ~$0.030 | ~**$0.052** |
| 2 min | ~35,400 | ~$0.044 | ~$0.030 | ~**$0.074** |
| 3 min | ~53,100 | ~$0.066 | ~$0.030 | ~**$0.096** |

All cases stay well under the 200k tier boundary — no tier surcharge. Add a short text system prompt (~500 tokens) — negligible.

The `estimate_cost()` method in the tool should implement: `duration_seconds * 295 * 1.25 / 1_000_000 + 3000 * 10.0 / 1_000_000`.

### Free Tier

Gemini 2.5 Pro is paid-only for video input (no free tier). `GEMINI_API_KEY` must be a paid-tier key for video analysis to work. The tool's `install_instructions` should note this.

---

## YAML Writer: Why ruamel.yaml Over PyYAML

PyYAML is already in `requirements.txt` (`pyyaml>=6.0`) and is used for `pipeline_loader.py` (reading). It is NOT sufficient for writing synthesized manifests because:

1. **PyYAML is YAML 1.1** — treats `yes/no/on/off` as booleans, mangles strings in pipeline values.
2. **No comment support** — synthesized manifests should include inline comments explaining decisions. PyYAML strips all comments.
3. **Unsafe dump hazard** — `yaml.dump()` with default Dumper can serialize Python objects unexpectedly. `yaml.safe_dump()` is safe but lossy.

ruamel.yaml is YAML 1.2 compliant, preserves formatting and comments, and provides an explicit `YAML(typ='rt')` (round-trip) or `YAML(typ='safe')` mode.

**For `pipeline_synthesizer`:** use `ruamel.yaml` with `typ='rt'` for emitting the manifest. Use PyYAML for reading existing manifests (already working, no change).

```python
from ruamel.yaml import YAML

yaml = YAML(typ='rt')
yaml.default_flow_style = False
yaml.indent(mapping=2, sequence=4, offset=2)

with open(output_path, "w") as f:
    yaml.dump(manifest_dict, f)
```

---

## JSON Schema Validation: Existing dep is sufficient

`jsonschema>=4.20` is already in `requirements.txt`. The `pipeline_synthesizer` tool validates the synthesized manifest using:

```python
import json
from pathlib import Path
from jsonschema import validate, ValidationError

schema_path = Path("schemas/pipelines/pipeline_manifest.schema.json")
schema = json.loads(schema_path.read_text())
validate(instance=manifest_dict, schema=schema)
```

The schema uses `"$schema": "https://json-schema.org/draft/2020-12/schema"`. The `jsonschema` 4.x library supports Draft 2020-12 natively. No additional validator configuration needed.

**Verification:** `jsonschema` 4.26.0 is current (April 2026). The `>=4.20` pin in `requirements.txt` is already sufficient. Do not bump the pin.

---

## Integration Points with Existing Selector / Registry Pattern

The `gemini_video_analyzer` tool slots into the existing registry pattern with zero changes to `tool_registry.py` or any selector file:

```python
# tools/analysis/gemini_video_analyzer.py

class GeminiVideoAnalyzer(BaseTool):
    name = "gemini_video_analyzer"
    capability = "video_analysis"          # new capability family
    provider = "google"
    tier = ToolTier.ANALYZE
    runtime = ToolRuntime.API
    stability = ToolStability.BETA
    dependencies = [
        "env:GEMINI_API_KEY",
        "python:google.genai",             # maps to google-genai package
    ]
    install_instructions = (
        "Set GEMINI_API_KEY in .env (paid tier required for video analysis).\n"
        "pip install google-genai>=1.73.0"
    )
    agent_skills = ["video-understand"]
```

The `video_analyzer_selector` mirrors `video_selector.py` exactly:
- `capability = "video_analysis"` on the selector
- `registry.get_by_capability("video_analysis")` for provider discovery
- No hardcoded provider list

The `pipeline_synthesizer` tool:
```python
class PipelineSynthesizer(BaseTool):
    name = "pipeline_synthesizer"
    capability = "pipeline_synthesis"      # new capability, no selector needed (single impl)
    provider = "openmontage"
    tier = ToolTier.CORE
    runtime = ToolRuntime.LOCAL
    dependencies = [
        "python:ruamel.yaml",
        "python:jsonschema",
    ]
```

Both tools auto-discovered on `registry.discover()` via `BaseTool` inheritance — no registration code needed.

---

## Updated requirements.txt additions

```
# Additions for v2.0 Reference Synthesis
google-genai>=1.73.0
ruamel.yaml>=0.18.0
```

---

## Verification Log

| Claim | Source | Confidence | Date |
|-------|--------|------------|------|
| Package name is `google-genai` (not `google-generativeai`) | https://github.com/googleapis/python-genai, PyPI | HIGH | 2026-04-17 |
| Latest version is 1.73.1 (released 2026-04-14) | https://pypi.org/project/google-genai/ | HIGH | 2026-04-17 |
| Python >=3.10 required by google-genai | PyPI metadata | HIGH | 2026-04-17 |
| Gemini 2.5 Pro requires Files API for video (2.5+ series) | Community reports + SDK issue tracker | MEDIUM | 2026-04-17 |
| Files API: upload → poll ACTIVE → generate_content pattern | https://ai.google.dev/gemini-api/docs/files + https://ai.google.dev/gemini-api/docs/video-understanding | HIGH | 2026-04-17 |
| Video tokenization: 263 tokens/sec (default) + 32 tokens/sec audio | https://ai.google.dev/gemini-api/docs/tokens | HIGH | 2026-04-17 |
| Files stored 48h, 20GB/project, 2GB/file (paid) | https://ai.google.dev/gemini-api/docs/files | HIGH | 2026-04-17 |
| response_json_schema parameter for structured output | https://googleapis.github.io/python-genai/ | HIGH | 2026-04-17 |
| Gemini 2.5 Pro pricing: $1.25/$10.00 per 1M tokens (≤200k) | https://ai.google.dev/gemini-api/docs/pricing | HIGH | 2026-04-17 |
| ruamel.yaml YAML 1.2 + comment-preservation vs PyYAML YAML 1.1 | PyPI + ruamel.yaml docs | HIGH | 2026-04-17 |
| jsonschema 4.26.0 supports Draft 2020-12 | https://python-jsonschema.readthedocs.io/en/stable/ | HIGH | 2026-04-17 |
| Context window 1M tokens for Gemini 2.5 Pro | Multiple pricing/stats sources | MEDIUM | 2026-04-17 |
| Gemini 2.5 Pro is paid-only (no free video tier) | pricing page, finout.io | MEDIUM | 2026-04-17 |

### Open questions (LOW confidence / unverified)

- Whether `response_schema` (Pydantic class) vs `response_json_schema` (dict) has different behavior for deeply nested schemas on Gemini 2.5 Pro specifically. The GitHub issue #637 mentions structured output was broken on an earlier preview; confirm with a quick smoke test during Phase 1.
- Exact token count when audio track is absent in a video file (muted reference). The 32 tokens/sec audio rate may not apply. Use `client.models.count_tokens()` during integration to measure actual usage.
- Whether `gemini-2.5-pro` (stable) is the correct production model ID as of Phase 1 start, or if a dated variant (e.g., `gemini-2.5-pro-001`) is required. Check https://ai.google.dev/gemini-api/docs/models at phase start.
