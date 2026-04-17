---
name: reference-synthesis
description: Orchestrate the end-to-end flow that turns a local reference video into a reusable pipeline definition. Trigger when the user wants to CAPTURE a video's format as a persistent template (not generate concepts). Two `awaiting_human` checkpoints (analysis review + synthesis diff approval) are architectural safety gates — never auto-approve.
---

# Reference Synthesis — Meta Skill

## When to Use

Trigger this skill when the user wants to capture a reference video's **format**
as a reusable, persistent pipeline definition under `pipeline_defs/`. Output is
a new YAML manifest the agent can invoke on future productions — not a creative
concept for a single video.

This skill is the sister of `skills/meta/video-reference-analyst.md`. They look
superficially similar but produce different artifacts:

| Skill | Produces | Persists |
|-------|----------|----------|
| `video-reference-analyst.md` | Creative **concepts** ("make me one like this") | No — one-shot analysis |
| `reference-synthesis.md` (this) | Pipeline **template** under `pipeline_defs/<slug>.yaml` | Yes — reusable on future videos |

**Trigger phrases (any of these invoke this skill):**
- "synthesize a pipeline from this reference"
- "save this format as reusable"
- "make this video's format into a template"
- "turn this reference into a pipeline"
- "capture this style as a pipeline"
- "save this reference as a template"

**Do NOT trigger — route elsewhere:**
- "make me something like this" / "inspired by this" / "in this style" → `skills/meta/video-reference-analyst.md` (creative variants, no template saved)
- "edit this footage" / "cut this into clips" → `skills/meta/source_media_review.md` (footage-led, not reference-led)
- "just tell me what this video does" → `skills/meta/video-reference-analyst.md` Step 1 only (description without production)

## Scope Limits (v2.0)

- **Local video paths only.** URL fetch (YouTube, Shorts, Vimeo) is deferred to
  v2.1 backlog item **PROV-01**. Ask the user to download locally first.
- **Staging-only writes.** Writes exclusively to `pipeline_defs/_staging/<slug>.yaml`
  until human approves. Only `accept_synthesis` promotes staging → `pipeline_defs/`.
- **Single reference per synthesis.** Multi-reference blending is out of scope.

## Workflow Overview

```
Step 1: receive video (local path)
       |
       v
Step 2: select provider via video_analyzer_selector
       |
       v
Step 3: estimate chunked cost (if >5 min)  -- show user; allow abort
       |
       v
Step 4: analyze  (selector one-shot  OR  analyze_chunked)
       |
       v
Step 5: [awaiting_human #1] REVIEW ANALYSIS ARTIFACT
       |                                            \
       v                                             \-> user says "re-analyze" -> back to Step 4
Step 6: synthesize_pipeline(analysis, mode="template")
       |
       v
Step 7: [awaiting_human #2] REVIEW DIFF + APPROVE/REJECT
       |                                            \
       v                                             \-> user says "revise" -> back to Step 6 (adjust mode/params)
Step 8: accept_synthesis(slug)   OR   reject_synthesis(slug)
```

Eight numbered steps, **two explicit human gates** (Step 5 and Step 7). Neither
gate is optional. A collapsed flow that skips either checkpoint violates
SYNTH-10 and is called out in Anti-Patterns below.

### Step 1: Receive the video

Accept a **local filesystem path** to a video file (mp4, mov, mpeg, avi, webm).

```python
from pathlib import Path

video_path = Path(user_provided_path).expanduser().resolve()
if not video_path.exists() or not video_path.is_file():
    # reject — local files only
    raise FileNotFoundError(f"Not a file: {video_path}")
```

**Reject URLs explicitly.** If the path starts with `http://`, `https://`,
`youtu.be/`, `youtube.com/`, or any other URL scheme, tell the user:

> "This skill accepts local video paths only in v2.0. Please download the video
> locally first, then re-run with the local path. URL fetch is on the v2.1
> backlog as **PROV-01**."

Optionally note the basename for logging (`video_path.name`) — the final slug
comes from the synthesizer's deterministic hash, NOT from the filename.

### Step 2: Select provider via video_analyzer_selector

Always go through the capability-level selector. Never instantiate a raw
provider (`gemini_video_analyzer`, `openrouter_video_analyzer`) directly — the
selector enforces preference order, env overrides, and Layer-3 skill wiring.

```python
from tools.tool_registry import registry
registry.discover()
selector = registry.get_by_capability("video_analysis")[0]
# Selector enforces: provider="selector"; raw providers are never returned first.
assert selector.provider == "selector"
```

**Preference order** (documented in `tools/analysis/video_analyzer_selector.py`):

1. `inputs["preferred_provider"]` if != `"auto"` — caller wins
2. `VIDEO_ANALYZER_PROVIDER` env var if != `"auto"` — workspace config
3. First provider whose API key is present:
   - `GEMINI_API_KEY` or `GOOGLE_API_KEY` → `gemini`
   - `OPENROUTER_API_KEY` → `openrouter`
4. First AVAILABLE provider in discovery order

Never pin a provider inside this skill's code blocks — pass `preferred_provider="auto"`
and let the preference order decide. If you need a specific one, tell the user
to set `VIDEO_ANALYZER_PROVIDER=gemini` (or `openrouter`) in `.env`.

### Step 3: Cost estimation for long-form video

Probe the video's duration with ffprobe (one-liner):

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "<video_path>"
```

**If duration > 300 seconds (5 minutes)**, call `estimate_chunked_cost` and
present the estimate to the user with an explicit abort option:

```python
from lib.chunked_analyzer import estimate_chunked_cost

estimate = estimate_chunked_cost(
    provider="gemini",                    # or "openrouter"
    duration_seconds=probed_duration,
    model="gemini-3.1-pro-preview",       # from VIDEO_ANALYZER env or selector
    max_chunk_seconds=300.0,
)
# estimate keys: total_usd, low_usd, high_usd, chunk_count,
#                input_tokens_est, output_tokens_est, pricing_verified_at
```

Present: video path, duration, chunk count, estimated cost (with low/high
range), pricing verified date. Offer explicit `proceed` / `abort` choice.

**If duration ≤ 300 seconds**, skip the estimate — chunking is not needed.

If the model has no pricing entry, the estimator returns
`{"total_usd": None, "confidence": "unknown"}`. Surface verbatim and ask
whether to proceed blind.

### Step 4: Analyze

Two branches. Short videos take the one-shot path; long videos get chunked.

**Short video (≤5 min) — one-shot selector call:**

```python
result = selector.execute({
    "video_path": str(video_path),
    "analysis_depth": "full",          # enum: "full" | "compact"
    "preferred_provider": "auto",      # respect env + preference order
})
assert result.success, result.error
analysis = result.data                 # canonical video_analysis artifact
selected_provider = result.model       # e.g., "gemini_video_analyzer"
```

**Long video (>5 min) — chunked analysis with bounded concurrency:**

```python
from lib.chunked_analyzer import analyze_chunked

# analyze_chunked takes a provider_tool instance (BaseTool), not a string.
# The selector IS a valid provider_tool — pass it directly.
analysis = analyze_chunked(
    video_path=str(video_path),
    provider_tool=selector,
    max_workers=None,     # None -> env VIDEO_CHUNK_WORKERS -> default 4
    on_chunk_error="fail_fast",   # or "continue" for best-effort merge
)
# analysis is the merged canonical artifact, with chunking_metadata attached
# (chunk_count, total_duration_s, failed_chunks if any).
```

`max_workers` is clamped to `[1, 8]` and resolved as `arg > env
VIDEO_CHUNK_WORKERS > default(4)`. An unparseable env value logs WARNING and
falls back to the default — this is a Pitfall-4 mitigation, do not re-implement
the resolution inline.

### Step 5: [awaiting_human #1] Review analysis artifact

This is the first of two **awaiting_human** checkpoints. Do NOT skip. Do NOT
auto-approve based on validation heuristics — the human must eyeball the
4-dimension summary before we burn synthesis cost.

Checkpoint mechanics (status value, write_checkpoint call, resume behavior) are
defined once in `skills/meta/checkpoint-protocol.md`. Reference that skill;
do not re-document its protocol here.

Present to the user (use this exact shape in your turn):

```
## Analysis Complete — Please Review

**Source:** <video_path>
**Provider used:** <selected_provider>
**Duration:** <sec>s  (chunked: <yes/no>, chunk_count: <N if chunked>)

**4-dimension summary:**
- editing_pacing.pacing_style: <value>   (confidence: <low|medium|high>)
- audio.has_narration: <bool>
- visual_style.color_palette: <N colors>
- narrative.hook_type: <value>

**Full artifact:** <inline JSON OR path to saved artifact>

Please confirm the analysis looks right before I synthesize a pipeline from it.
- Say "looks good, synthesize" to proceed to Step 6.
- Say "re-analyze with <depth|provider>" to re-run Step 4.
- Say "abort" to stop.
```

**Response handling:**

| User says | Action |
|-----------|--------|
| "looks good" / "synthesize" / "approved" | Proceed to Step 6 |
| "re-analyze" / "try again with X" | Return to Step 4 (swap `analysis_depth` or `preferred_provider`) |
| "abort" / "cancel" | Stop; no artifact written |

Status value for this checkpoint: `awaiting_human` (per `checkpoint-protocol.md`
Step 2). The analysis artifact is the checkpoint payload.

### Step 6: Synthesize

One call. Mode default is `"template"` — the generalizable form. `"replica"`
exists for near-reproduction and is the exception, not the rule.

```python
from lib.pipeline_synthesizer import synthesize_pipeline

record = synthesize_pipeline(
    analysis,
    mode="template",           # default; "replica" for near-reproduction
    provider_used=selected_provider,
)
# record keys:
#   version, base_pipeline, match_score, mode, staging_path,
#   diff_against_base, validation_status, source_analysis_checksum,
#   provider_used, created_at
```

Key properties of `synthesize_pipeline`:

- Writes ONLY to `pipeline_defs/_staging/<slug>.yaml` (SYNTH-05 invariant).
- `slug` is a deterministic hash of `(base_pipeline, canonical_sha256(analysis))`
  — same video re-run produces the same slug; same path returns unchanged.
- `diff_against_base` is already a unified-diff string (generated by
  `lib.pipeline_synthesizer._unified_diff`) — do NOT re-compute it.
- `validation_status` is `"valid"` or `"invalid"` based on semantic validation
  (skill paths exist, tools registered). `"pending"` is reserved for future
  async flows — do not rely on it today.
- Optional `use_llm_fill=True|False|None` (None = env-controlled via
  `VIDEO_SYNTH_LLM_FILL`). Default behavior is usually correct; override only
  for deterministic test runs or explicit cost control.

### Step 7: [awaiting_human #2] Review diff + approve or reject

Second **awaiting_human** checkpoint. This one is the harder gate — the human
must read the unified diff and approve, reject, or request revision before the
manifest ever reaches `pipeline_defs/`.

Use `record["diff_against_base"]` verbatim — it is already the unified-diff
output of `lib/pipeline_synthesizer.py::_unified_diff`. Do NOT regenerate it.

Present to the user:

~~~
## Pipeline Synthesized — Please Review Diff

**Base pipeline:** <record["base_pipeline"]>   (match_score: <record["match_score"]:.2f>)
**Mode:** <record["mode"]>
**Validation status:** <record["validation_status"]>
**Staging path:** <record["staging_path"]>
**Slug:** <slug from record["staging_path"] stem>
**Analysis checksum:** <record["source_analysis_checksum"]>

```diff
<record["diff_against_base"]>
```

Options:
- "approve" / "accept"   -> promote to pipeline_defs/<slug>.yaml   (Step 8a)
- "reject"  / "discard"  -> delete from _staging/                   (Step 8b)
- "revise"               -> tell me what to change; I will re-synthesize (back to Step 6)
~~~

**If `validation_status == "invalid"`**: warn loudly before the diff block:

> ⚠ **Semantic validation failed.** The synthesized manifest references a
> skill or tool that is not on disk / not registered. You CAN still accept,
> but explicit confirmation is required. Issues: `<list from validate_synthesized_pipeline>`.

An invalid synthesis does NOT auto-reject — it's a user decision. Some
validation failures are expected (new skills planned but not yet written);
others indicate a bug. The human decides.

Status value for this checkpoint: `awaiting_human`.

### Step 8: Accept or reject

Two terminal branches. The API enforces the separation — there is NO
`synthesize_and_accept` wrapper, and there never will be (SYNTH-10).

**Step 8a — user approved:**

```python
from lib.pipeline_synthesizer import accept_synthesis

# Derive slug from record["staging_path"] — e.g., "pipeline_defs/_staging/animation-a1b2c3d4.yaml"
slug = Path(record["staging_path"]).stem
final_path, updated_record = accept_synthesis(slug)
# final_path: pipeline_defs/<slug>.yaml
# updated_record: schema-validated pipeline_synthesis record with post-promotion
#                 validation_status (re-checked after the move).
```

**Step 8b — user rejected:**

```python
from lib.pipeline_synthesizer import reject_synthesis

slug = Path(record["staging_path"]).stem
rejection_record = reject_synthesis(slug)
# rejection_record.validation_status == "invalid"
# (schema has no "rejected" enum value — user intent is encoded as the
#  invalid sentinel; capture the reason-for-rejection in your turn text.)
```

**Hard rule:** do NOT attempt to collapse Step 8a + Step 8b into one call,
and do NOT add a local wrapper. The separation is the safety gate.

Confirm to the user:

- On accept: "Promoted to `pipeline_defs/<slug>.yaml`. You can now invoke it as
  a pipeline on future productions."
- On reject: "Discarded from staging. No write to `pipeline_defs/`. If you want
  to try a different base, run the skill again with `mode='replica'` or after
  re-analyzing."

## Error Handling

| Failure | Action |
|---------|--------|
| User provided URL (not local path) | Reject: "v2.0 accepts local paths only. Download the video locally first. URL fetch is v2.1 (PROV-01)." |
| No video_analysis providers registered | Surface selector's native error; tell user to set `GEMINI_API_KEY` or `OPENROUTER_API_KEY` in `.env`. |
| `analyze_chunked` partial failure under `on_chunk_error="continue"` | Surface in `analysis.chunking_metadata.failed_chunks`; ask at Step 5 whether to retry, re-run, or accept partial. |
| `validation_status == "invalid"` from synthesizer | Warn loudly at Step 7; require explicit confirmation to accept. Invalid ≠ auto-reject. |
| Staging file disappeared before accept (drift / manual cleanup) | `accept_synthesis` raises `FileNotFoundError`; re-run `synthesize_pipeline` — slug is deterministic so same video re-synthesizes to same path. |
| `accept_synthesis` sees existing `pipeline_defs/<slug>.yaml` | Raises `FileExistsError` — no overwrite, staging preserved. Tell user to change `mode` or re-analyze with different depth to shift the checksum. |
| Staging collision cap hit (>99 `-vN` suffixes) | `synthesize_pipeline` raises `RuntimeError`. Tell user to clean up `_staging/` manually. |

## Anti-Patterns

- **Do NOT** instantiate `gemini_video_analyzer` or `openrouter_video_analyzer`
  directly. Always go through `video_analyzer_selector` so env overrides and
  preference order are respected.
- **Do NOT** skip the Step 5 or Step 7 checkpoints by auto-approving on a
  "looks valid" heuristic. Both `awaiting_human` gates are architectural; a
  passing validation check does not replace human judgment.
- **Do NOT** write to `pipeline_defs/` directly from this skill. Only
  `accept_synthesis` is authorized (SYNTH-10); `_staging/` is the trust
  boundary.
- **Do NOT** invoke `synthesize_pipeline` with `mode="replica"` as the default.
  `"template"` is more generalizable; `"replica"` is the exception for
  near-reproduction.
- **Do NOT** collapse Steps 7 + 8 into one turn, add a local
  `synthesize_and_accept` wrapper, or re-compute `diff_against_base`. SYNTH-10
  forbids the wrapper; the synthesizer already produced the diff — trust it.

## Cross-References

- **`skills/meta/checkpoint-protocol.md`** — canonical definition of checkpoint
  mechanics (status values, `write_checkpoint` usage, resume protocol). Steps 5
  and 7 of this skill reference it rather than re-documenting.
- **`skills/meta/video-reference-analyst.md`** — sister skill for creative
  variants ("make me one like this"). Use when the user wants concepts, NOT a
  reusable pipeline template. Disambiguation block in `## When to Use` above.
- **`CONTEXT.md`** — tools table (`video_analyzer_selector`, provider rows) and
  Libraries section (`lib/pipeline_synthesizer.py`, `lib/chunked_analyzer.py`).
- **`AGENT_GUIDE.md`** Reference Video Entry Point — routing rule that directs
  "synthesize a pipeline" phrases here and "make me something like this" to
  `video-reference-analyst.md`.
