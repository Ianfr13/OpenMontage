# Phase 4: Chunking — Research

**Researched:** 2026-04-17
**Domain:** FFmpeg stream-copy segmentation, per-dimension artifact merging, bounded thread concurrency, cost estimation for Gemini video analysis
**Confidence:** HIGH for FFmpeg / ThreadPoolExecutor / merger rules grounded in schema; MEDIUM for cost heuristics (pricing volatile, preview model)

## Summary

Phase 4 makes videos >5 min analyzable by splitting them into ≤5 min keyframe-aligned chunks via FFmpeg stream copy (`-c copy -f segment -segment_time 300 -reset_timestamps 1`), analyzing each chunk concurrently with a bounded ThreadPoolExecutor (max 4 workers), and merging the per-chunk canonical `video_analysis` artifacts back into a single schema-valid artifact with globally shifted timecodes and per-dimension merge rules.

The three sub-plans (`04-01` chunker, `04-02` merger, `04-03` orchestrator) are small because the substrate is already there: the canonical schema is finalized (Phase 1), both providers produce schema-valid artifacts (Phases 2/3), `cost_tracker.py` has `estimate`/`reserve`/`reconcile`/`refund` primitives, and `tests/unit/conftest.py` ships a `minimal_video_analysis()` fixture that keeps test data honest against the real schema.

**Primary recommendation:** Stream-copy FFmpeg with `-reset_timestamps 1` for the split; `concurrent.futures.ThreadPoolExecutor` + `as_completed` with a single `on_chunk_done(idx, ToolResult)` callback for progress; merger uses per-dimension rules derived directly from the `video_analysis` schema (numeric = duration-weighted avg, enum = duration-weighted majority vote, array = concat-with-global-shift for `section_structure` / concat-with-dedup for `transition_types`, boolean = OR, first-chunk-wins for `hook_*` / last-chunk-wins for `cta_*`). Confidence aggregation uses worst-case min (any "low" → "low") per CHUNK-04/CONTEXT.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Plan Decomposition (3 plans)**
- `04-01-PLAN.md` — `lib/video_chunker.py` + unit tests. Pure lib module, no BaseTool.
- `04-02-PLAN.md` — `lib/analysis_merger.py` + unit tests. Pure lib module.
- `04-03-PLAN.md` — `lib/chunked_analyzer.py` + contract tests. ThreadPoolExecutor bounded concurrency, cost estimation hook.

**Chunker Shape (CHUNK-01, CHUNK-02, CHUNK-03)**
- `split_video(video_path, max_chunk_seconds=300.0) -> list[Chunk]` where `Chunk = namedtuple("Chunk", ["start_global", "end_global", "local_path"])`.
- Command: `ffmpeg -i {input} -c copy -reset_timestamps 1 -f segment -segment_time {max} -segment_start_number 0 {output_pattern}`.
- Videos ≤5 min: return a single chunk equal to the original path (bypass, don't duplicate).
- Duration probe: `ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 {input}`.
- Keyframe alignment: segment muxer is automatic; no `-force_key_frames` (would require re-encode).
- Temp dir: `tempfile.mkdtemp(prefix="omvid_chunks_")` + `cleanup(chunks)` helper.

**Merger Shape (CHUNK-04, CHUNK-05)**
- `merge_analyses(chunks: list[tuple[Chunk, dict]]) -> dict` — canonical `video_analysis` artifact.
- Per-dimension rules per REQUIREMENTS CHUNK-04 (see `### Merger Rules` section below for field-level spec).
- Global timecode shift by `chunk.start_global` on any time-valued field.
- Confidence: ANY chunk "low" on a field → merged "low" (min-of-worst).
- Merged artifact MUST pass `validate_artifact("video_analysis", ...)`.
- `chunking_metadata = {chunk_count, total_duration_seconds, per_chunk_cost, provider_used_per_chunk, chunker_version}` attached to top-level (matches schema `chunking_metadata` already defined in `video_analysis.schema.json`).

**Integration (CHUNK-03, CHUNK-06)**
- Selector stays single-shot; `lib/chunked_analyzer.py::analyze_chunked(video_path, provider_tool, on_chunk_done=None) -> dict` is the wrapper. Consumed BY the meta skill (Phase 6 `skills/meta/reference-synthesis.md`).
- `ThreadPoolExecutor(max_workers=4)` + `VIDEO_CHUNK_WORKERS` env override (default 4, min 1, max 8).
- `estimate_chunked_cost(provider, duration, model) -> float` surfaced before long runs; caller can abort.
- `cost_tracker.py` integration: record each chunk analysis separately (estimate → reserve → reconcile).
- Partial progress: `concurrent.futures.as_completed` with optional `on_chunk_done=lambda chunk_idx, tool_result: ...`.

**Error Handling**
- Default fail-fast: first exception raises.
- Optional `on_chunk_error="continue"` mode: skip failed chunks, merge survivors, mark `chunking_metadata.failed_chunks`.
- Temp file cleanup: `try/finally` in `analyze_chunked` (not just chunker) so cleanup runs after analysis, not just after split.

### Claude's Discretion

- Exact weighted-average algorithm for `mood_arc` free-text — planner's call; recommend: concat with `[chunk N/M]` markers (see Pattern 5 below).
- Partial-progress callback signature — recommend `Callable[[int, ToolResult], None]` taking (chunk_idx, tool_result) (see Pattern 3).
- Default `max_workers` — confirmed 4 in CONTEXT; research supports this (see Pitfall 4).

### Deferred Ideas (OUT OF SCOPE)

- Adaptive chunk size based on content density (v2.1).
- Re-use chunk cache across runs (same video hash → reuse chunks) (OBS-02, v2.1).
- Parallel ffmpeg splitting for very large files (GB scale) — split time is not the bottleneck; analysis cost is.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CHUNK-01 | `lib/video_chunker.py` splits video into ≤5 min keyframe-aligned chunks | FFmpeg segment muxer spec (Finding 1), `scene_detect.py:196-202` ffprobe duration pattern |
| CHUNK-02 | ≤5 min videos bypass chunking | Single-chunk branch in `split_video`; merger handles `len(chunks) == 1` as pass-through |
| CHUNK-03 | >5 min → bounded concurrency analysis | `concurrent.futures.ThreadPoolExecutor` + `as_completed` (Pattern 3) |
| CHUNK-04 | Merger with documented per-dimension rules | Canonical schema field enumeration → merge rule spec (§ Merger Rules) |
| CHUNK-05 | `chunking_metadata` on merged artifact | Schema already defines `chunking_metadata` at `video_analysis.schema.json:312-331` |
| CHUNK-06 | Cost tracker records each chunk; estimate surfaced pre-run | `cost_tracker.py:101-165` estimate/reserve/reconcile API + Gemini video token rate (Finding 4) |

## Project Constraints (from CLAUDE.md)

Per `./CLAUDE.md` the canonical operating contract is `AGENT_GUIDE.md`. Phase 4 is *infrastructure for the `video_analysis` capability* — `lib/video_chunker.py` and `lib/analysis_merger.py` are pure lib modules and are NOT BaseTools (CONTEXT locked that explicitly). This sits *below* the "agent is intelligence, Python is tools+persistence" line and does not need Layer 3 skills. The `chunked_analyzer` wrapper is called by the Phase 6 meta skill, not directly by the agent in normal pipeline flow.

Applicable global project rules relevant here:
- Pure lib modules follow `lib/checkpoint.py` / `lib/schema_adapter.py` precedent: no BaseTool ancestry, no `execute()`, no registry visibility.
- subprocess for FFmpeg with `shell=False` and explicit args (see `scene_detect.py:173-180`).
- New error class `VideoChunkingError` extends `VideoAnalysisError` (see § Error Hierarchy).
- Validation: all lib code MUST be covered by pytest unit tests; contract tests live in `tests/contracts/`, unit tests in `tests/unit/`.
- Never call `lib.checkpoint.write_checkpoint` from tool or lib code — that's the meta skill / orchestrator's job (Phase 1 WR-05 contract).

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ffmpeg` (binary) | 4.x+ | Stream-copy segmentation via segment muxer | `[VERIFIED: already a repo dep — `scene_detect.py:36` declares `cmd:ffmpeg`]` — single source of truth for video ops |
| `ffprobe` (binary) | 4.x+ | Duration probe | `[VERIFIED: `scene_detect.py:196-202`]` same invocation pattern already in repo |
| `concurrent.futures.ThreadPoolExecutor` | stdlib | Bounded worker pool for chunk analysis | `[CITED: docs.python.org/3/library/concurrent.futures.html]` idiomatic bounded concurrency |
| `tempfile.mkdtemp` | stdlib | Chunk scratch dir | `[CITED: docs.python.org/3/library/tempfile.html]` CONTEXT locks this over `TemporaryDirectory` because cleanup must be deferred to end-of-analysis, not end-of-split |
| `jsonschema` | ≥4.20 | Merged artifact validation via `validate_artifact("video_analysis", ...)` | `[VERIFIED: `requirements.txt:4`]` already used by Phase 1-3 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `collections.namedtuple` | stdlib | `Chunk(start_global, end_global, local_path)` return shape | Lightweight, no Pydantic overhead for a 3-field record |
| `dataclasses` | stdlib | Alternative to namedtuple if mutable state needed later | Prefer `namedtuple` per CONTEXT (read-only semantics) |
| `pathlib.Path` | stdlib | All path handling | Matches existing codebase convention (`gemini_video_analyzer.py:27`) |
| `logging` | stdlib | Structured module logger | Mirror `gemini_video_analyzer.py:52` pattern: `logger = logging.getLogger(__name__)` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ffmpeg -f segment` | `ffmpeg -ss/-t` per-chunk loop | Loop is N×slower (N seeks vs 1 stream pass); rejected |
| `subprocess.run` | `ffmpeg-python` package | Added dep, no gain — `scene_detect.py` uses `self.run_command` (BaseTool helper); plain `subprocess.run` works for lib-module and avoids BaseTool inheritance |
| `ThreadPoolExecutor` | `asyncio` + `httpx` | Providers are synchronous (`openai>=1.0` sync client; google-genai sync); thread pool is the correct concurrency primitive here |
| `tempfile.TemporaryDirectory` (context mgr) | `tempfile.mkdtemp` + manual cleanup | Context-manager cleanup runs at end-of-`with`, which would fire BEFORE chunk analysis completes. CONTEXT locks `mkdtemp` + `try/finally` in `analyze_chunked` for this reason |
| `dataclasses.dataclass` | `namedtuple` | `namedtuple` is immutable and pickle-safe; fine for a 3-field tuple |

**Installation:** No new deps. Every element is already in `requirements.txt` / `requirements-dev.txt` or is stdlib.

**Version verification:**
```bash
# No new packages — nothing to pin
```

## Architecture Patterns

### Recommended Project Structure

```
lib/
├── video_chunker.py       # split_video + cleanup helpers (CHUNK-01, CHUNK-02)
├── analysis_merger.py     # merge_analyses + per-dimension rules (CHUNK-04, CHUNK-05)
├── chunked_analyzer.py    # analyze_chunked orchestrator — ThreadPoolExecutor wrapper (CHUNK-03, CHUNK-06)
└── analysis_errors.py     # existing — add VideoChunkingError(VideoAnalysisError)

tests/
├── unit/
│   ├── test_video_chunker.py       # ffmpeg subprocess mocked; duration probe fixtures
│   ├── test_analysis_merger.py     # per-dimension rules; schema validation on merged output
│   └── test_chunked_analyzer.py    # ThreadPoolExecutor mocked; cost tracker mocked
└── contracts/
    └── test_phase4_chunked_path.py # end-to-end chunked path with mocked provider
```

### Pattern 1: FFmpeg Stream-Copy Segmentation

**What:** Split a video into fixed-duration segments via FFmpeg's segment muxer without re-encoding. The segment muxer starts each segment at the next keyframe ≥ `-segment_time`; `-reset_timestamps 1` ensures each segment starts at near-zero PTS for independent playback.

**When to use:** Any time the goal is "split for downstream per-chunk processing" and pixel-accurate cuts are not required (they aren't — Gemini analyzes the chunk regardless of sub-keyframe trim offset).

**Example:**
```python
# Source: FFmpeg segment muxer docs + scene_detect.py:196-202 pattern
# [VERIFIED: scene_detect.py line refs — ffprobe invocation]
# [CITED: https://ffmpeg.org/ffmpeg-formats.html#segment]

import subprocess
import tempfile
import shlex
from pathlib import Path

def _probe_duration_seconds(video_path: Path) -> float:
    """ffprobe duration probe — mirror scene_detect.py:196-202."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(video_path),
        ],
        capture_output=True, text=True, check=True, timeout=30,
    )
    return float(result.stdout.strip())

def _split_ffmpeg(video_path: Path, chunk_seconds: float, out_dir: Path) -> list[Path]:
    """Invoke the segment muxer; return sorted list of generated chunk paths."""
    out_pattern = out_dir / "chunk_%03d.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-c", "copy",
        "-map", "0",
        "-reset_timestamps", "1",
        "-f", "segment",
        "-segment_time", str(chunk_seconds),
        "-segment_start_number", "0",
        str(out_pattern),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
    return sorted(out_dir.glob("chunk_*.mp4"))
```

### Pattern 2: Chunker Pass-Through for ≤5 min Videos

**What:** When the probed duration is ≤ `max_chunk_seconds`, return a single `Chunk` pointing at the original path — no ffmpeg invocation, no temp dir.

**When to use:** CHUNK-02 requirement. Avoids per-call overhead and temp-disk I/O for the common short-video case.

**Example:**
```python
# Source: CONTEXT decisions + CHUNK-02 requirement
def split_video(video_path: str, max_chunk_seconds: float = 300.0) -> list[Chunk]:
    video_path = Path(video_path)
    duration = _probe_duration_seconds(video_path)
    if duration <= max_chunk_seconds:
        return [Chunk(start_global=0.0, end_global=duration, local_path=str(video_path))]
    tmpdir = Path(tempfile.mkdtemp(prefix="omvid_chunks_"))
    try:
        paths = _split_ffmpeg(video_path, max_chunk_seconds, tmpdir)
    except Exception:
        # On split failure clean up the empty tmpdir — caller would otherwise leak it
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
    # Last chunk's end_global is total duration; intermediate chunks are exactly max_chunk_seconds
    chunks = []
    for i, p in enumerate(paths):
        start = i * max_chunk_seconds
        end = min(start + max_chunk_seconds, duration)
        chunks.append(Chunk(start_global=start, end_global=end, local_path=str(p)))
    return chunks
```

**Note on the chunk duration math:** FFmpeg may produce a final chunk shorter than `max_chunk_seconds` AND the pre-final chunks may drift slightly if keyframes don't land exactly on 300s boundaries. The `start_global`/`end_global` math above uses *nominal* boundaries; if keyframe drift matters for downstream merge (it shouldn't — see Pitfall 1), probe each generated chunk's own duration via ffprobe and compute `end_global = start_global + probed_duration`.

### Pattern 3: ThreadPoolExecutor with Per-Task Progress Callback

**What:** Use `as_completed` to iterate futures in completion order and invoke a caller-provided callback after each one.

**When to use:** CHUNK-03 requirement for bounded concurrency with partial progress visibility.

**Example:**
```python
# Source: docs.python.org/3/library/concurrent.futures.html + CONTEXT callback spec
# [CITED: https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.as_completed]
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional
from tools.base_tool import ToolResult

ChunkCallback = Optional[Callable[[int, ToolResult], None]]

def _analyze_chunks(
    chunks: list[Chunk],
    provider_tool,
    max_workers: int,
    on_chunk_done: ChunkCallback = None,
    on_chunk_error: str = "fail_fast",  # or "continue"
) -> list[tuple[int, Chunk, ToolResult]]:
    results: list[tuple[int, Chunk, ToolResult]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_idx = {
            pool.submit(provider_tool.execute, {"video_path": chunk.local_path}): (i, chunk)
            for i, chunk in enumerate(chunks)
        }
        for fut in as_completed(future_to_idx):
            idx, chunk = future_to_idx[fut]
            try:
                res = fut.result()
            except Exception as exc:
                if on_chunk_error == "fail_fast":
                    raise
                # "continue" mode — synthesize failed ToolResult and keep going
                res = ToolResult(success=False, error=f"chunk {idx} failed: {exc}")
            results.append((idx, chunk, res))
            if on_chunk_done is not None:
                try:
                    on_chunk_done(idx, res)
                except Exception:  # pragma: no cover — callback errors should not kill the pool
                    logger.exception("on_chunk_done callback raised for chunk %d", idx)
    # Restore submission order for the merger
    results.sort(key=lambda t: t[0])
    return results
```

**Callback signature rationale:** `(chunk_idx: int, result: ToolResult)` — `chunk_idx` lets the consumer correlate with their own chunk list; `ToolResult` gives `.success`, `.data`, `.error`, `.cost_usd`, `.model` in one shot.

### Pattern 4: Merger with Per-Dimension Rules

**What:** Walk the per-chunk artifact list, apply a rule per top-level field, and return a schema-valid merged artifact.

**When to use:** CHUNK-04. The schema is fixed (Phase 1 locked) — merger walks *every* field in `video_analysis.schema.json` and dispatches to one of: weighted-average (numeric), weighted-majority-vote (enum), union-dedup (array of enums), concat-with-shift (array of timecoded objects), OR (boolean), first-wins (`hook_*` fields), last-wins (`cta_*` fields), worst-case (confidence maps).

**Example:**
```python
# Source: CONTEXT + schema field analysis
from collections import Counter

def _weighted_majority(values_and_weights: list[tuple[str, float]]) -> str:
    """Duration-weighted majority vote for enum fields."""
    tally: Counter[str] = Counter()
    for val, w in values_and_weights:
        if val is not None:
            tally[val] += w
    return tally.most_common(1)[0][0]  # caller must handle empty list upstream

def _weighted_avg(values_and_weights: list[tuple[float, float]]) -> float:
    total_w = sum(w for _, w in values_and_weights)
    if total_w == 0:
        return 0.0
    return sum(v * w for v, w in values_and_weights) / total_w
```

### Pattern 5: Free-text `mood_arc` / `paragraph_pattern` concat

**What:** Freeform string fields cannot be meaningfully "averaged". Concat with explicit chunk-boundary markers so downstream (synthesizer, Phase 5) can reason about them.

**Example:**
```python
def _concat_freetext(values: list[str | None], chunk_labels: list[str]) -> str:
    parts = []
    for val, label in zip(values, chunk_labels):
        if val:
            parts.append(f"[{label}] {val}")
    return " | ".join(parts)
# chunk_labels = [f"chunk {i+1}/{N}" for i in range(N)]
```

### Anti-Patterns to Avoid

- **Using `-force_key_frames` with `-c copy`:** `-force_key_frames` is a video filter that requires re-encoding; combining with `-c copy` is a silent no-op. Don't reach for it just because segment output isn't frame-exact.
- **Using `tempfile.TemporaryDirectory()` as a context manager around the split+analyze block:** works functionally, but hides the lifecycle. Explicit `mkdtemp` + `try/finally` in `analyze_chunked` makes the cleanup contract readable at the call site.
- **Calling `validate_artifact` only at merge-end:** do it at merge-end AND smoke-test each per-chunk artifact in the provider path (that's already done in `gemini_video_analyzer.py:432` and `openrouter_video_analyzer.py:562`). Don't re-validate per-chunk in the merger — provider already guarantees it.
- **Blocking the main thread on `future.result()` in submission order:** breaks partial progress. Always use `as_completed`.
- **Aggregating confidence by averaging or mode:** the "low" signal means the model *wasn't sure* — it should not be diluted by another chunk's "high". Worst-case (min-ranked) is the honest aggregation.

## Runtime State Inventory

Phase 4 is greenfield code with no rename or refactor scope — this section does not apply.

## Merger Rules (Field-by-Field Spec from Canonical Schema)

Walking `schemas/artifacts/video_analysis.schema.json` field-by-field:

### `version` (const "2.0")
- Pass-through. Always "2.0".

### `source` (object)
- `type`, `url`, `local_path`, `title`, `resolution` — **first chunk wins** (they all come from the same input).
- `duration_seconds` — **replace with total probed duration** (sum of chunk `end_global - start_global`, which equals the original video's duration).

### `editing_pacing`

| Field | Type | Rule |
|-------|------|------|
| `total_shots` | int | **sum** across chunks |
| `cuts_per_minute` | number | **duration-weighted avg** |
| `avg_shot_duration_seconds` | number | **duration-weighted avg** (or recompute from total_shots & total duration — prefer recompute for consistency) |
| `median_shot_duration_seconds` | number | **duration-weighted avg** (median-of-medians is lossy; this is an approximation and the field is optional) |
| `shortest_shot_seconds` | number | **min** across chunks |
| `longest_shot_seconds` | number | **max** across chunks |
| `pacing_style` | enum | **duration-weighted majority vote** |
| `shot_type_distribution` | object of ratios | **per-key duration-weighted avg**; re-normalize to sum ≈ 1.0 after merge |
| `b_roll_ratio`, `a_roll_ratio` | number (0-1) | **duration-weighted avg** |
| `motion_type_distribution` | object of ratios | **per-key duration-weighted avg** |
| `transition_types` | array of enum | **union-dedup** (order-preserving: first occurrence across chunks wins) |
| `energy_arc` | array of {timestamp_s, energy_level} | **concat with timestamp_s += chunk.start_global** |
| `suggested_remotion_scene_types` | array of string | **union-dedup** |
| `confidence` | map of field→low/med/high | **worst-case min** (any "low" → "low"; else any "medium" → "medium"; else "high") |

### `audio`

| Field | Type | Rule |
|-------|------|------|
| `has_narration` | bool | **OR** (any chunk true → true) |
| `narration_style` | enum | **duration-weighted majority vote** |
| `speaker_count` | int | **max** across chunks (different chunks may feature different speakers; max = upper bound on distinct speakers visible) |
| `voice_gender` | enum | **duration-weighted majority vote** |
| `voice_tone` | enum | **duration-weighted majority vote** |
| `narration_wpm` | number | **duration-weighted avg** (weighted ONLY across chunks where `has_narration=true`) |
| `narration_language` | string | **duration-weighted majority** |
| `has_music` | bool | **OR** |
| `music_genre` | string | **duration-weighted majority** |
| `music_tempo_bpm` | number|null | **duration-weighted avg** of non-null values |
| `music_intensity` | enum | **duration-weighted majority vote** |
| `has_sfx` | bool | **OR** |
| `sfx_style` | string | **duration-weighted majority** |
| `voice_music_mix` | enum | **duration-weighted majority vote** |
| `suggested_tts_voice_profile` | string | **first chunk** (creative hint; consistency > averaging) |
| `suggested_music_prompt` | string | **first chunk** (same reason) |
| `confidence` | map | **worst-case min** |

### `visual_style`

| Field | Type | Rule |
|-------|------|------|
| `color_palette.primary/accent/background/text` | array of string | **union-dedup** (keep first N=5 by frequency — see Pitfall 3) |
| `dominant_colors_hex` | array of string | **union-dedup** (same N=5 cap) |
| `color_temperature` | enum | **duration-weighted majority vote** |
| `color_grading_style` | enum | **duration-weighted majority vote** |
| `background_treatment` | enum | **duration-weighted majority vote** |
| `typography_style` | string | **first chunk** (prose description; concat would be noise) |
| `typography_weight` | enum | **duration-weighted majority vote** |
| `text_card_usage` | enum | **duration-weighted majority vote** |
| `motion_style` | enum | **duration-weighted majority vote** |
| `overlay_style` | enum | **duration-weighted majority vote** |
| `production_quality` | enum | **duration-weighted majority vote** |
| `aspect_ratio` | enum | **first chunk** (physical property; should be identical across chunks — flag if they disagree) |
| `suggested_playbook` | string | **duration-weighted majority** |
| `playbook_overrides` | object | **first chunk** (dict merge is risky; creative hint) |
| `confidence` | map | **worst-case min** |

### `narrative`

| Field | Type | Rule |
|-------|------|------|
| `hook_type` | enum | **first chunk** (per CHUNK-04 spec: hook is always at video start) |
| `hook_duration_seconds` | number | **first chunk** |
| `narrative_arc` | enum | **duration-weighted majority vote** (though the whole-video arc is hard to infer per-chunk; this is approximate — flag low confidence if disagreement) |
| `section_count` | int | **sum** across chunks |
| `section_structure` | array of {label, approx_start_s, approx_end_s, summary} | **concat with `approx_start_s` and `approx_end_s` += chunk.start_global** |
| `cta_type` | enum | **last chunk** (CTA is always at video end) |
| `cta_duration_seconds` | number | **last chunk** |
| `target_platform` | enum | **first non-null** (should be identical across chunks) |
| `target_duration_seconds` | number | **total** (sum of chunk durations) |
| `information_density` | enum | **duration-weighted majority vote** |
| `content_tone` | enum | **duration-weighted majority vote** |
| `paragraph_pattern` | string | **concat with chunk markers** (Pattern 5) |
| `confidence` | map | **worst-case min** |

### `chunking_metadata` (new — required for merged output per CHUNK-05)
```json
{
  "chunk_count": <int>,
  "total_duration_s": <float>,
  "provider": "gemini" | "openrouter",
  "per_chunk": [
    {"index": 0, "start_s": 0.0, "end_s": 300.0, "cost_usd": 0.42, "provider": "gemini"},
    ...
  ]
}
```

### `shot_boundary_source` (enum: scene_detect / model / hybrid)
- **"hybrid"** if chunks disagree OR any chunk is "hybrid"; else **first chunk's value** (they should all agree — same input, same provider).

### Time-valued fields that need `+= chunk.start_global` (exhaustive list)
1. `editing_pacing.energy_arc[].timestamp_s`
2. `narrative.section_structure[].approx_start_s`
3. `narrative.section_structure[].approx_end_s`

**No other time-valued fields exist in the schema.** `hook_duration_seconds` / `cta_duration_seconds` are durations, not timestamps — no shift needed. `shortest/longest/median/avg_shot_duration_seconds` are statistics — no shift.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Video splitting | Custom PTS-tracking seek loop | `ffmpeg -f segment` | Segment muxer handles keyframe alignment, multi-stream mapping, container-specific quirks |
| Duration probe | Parsing `ffmpeg -i` stderr | `ffprobe -show_entries format=duration` | ffprobe returns machine-parseable scalar; already used in `scene_detect.py:196-202` |
| Thread pool | Raw `threading.Thread` + Queue | `concurrent.futures.ThreadPoolExecutor` | Provides `submit`, `as_completed`, future cancellation; stdlib |
| Majority vote | Manual loop with dict | `collections.Counter` | O(n) with `.most_common()`; stdlib |
| Dedup-preserving-order | Manual seen-set loop | `dict.fromkeys(iterable)` (insertion-ordered since 3.7) | Idiomatic 1-liner |
| Tempdir cleanup | Manual `os.walk` + unlink | `shutil.rmtree(path, ignore_errors=True)` | Handles missing files and readonly corner cases |
| Cost estimation | Scraped live pricing pages | Fixed per-model heuristic table with `VERIFIED_AT` date | Pricing is volatile for preview models; stamp a date and let it go stale loudly |

**Key insight:** Every primitive needed for Phase 4 already exists in the repo (ffmpeg/ffprobe wrappers, cost_tracker, error hierarchy, test fixtures). The plans should be thin compositions, not re-implementations.

## Common Pitfalls

### Pitfall 1: Non-uniform chunk durations from keyframe drift

**What goes wrong:** `-segment_time 300` asks for 300s chunks. With `-c copy`, FFmpeg can only cut at keyframes. If the input has keyframes every 10s, you'll get chunks of ~300-310s. If keyframes every 2s, chunks of ~300-302s. If keyframes every 60s (rare but possible — long GOP h264/h265), chunks could be 300-360s.

**Why it happens:** The segment muxer starts a new segment at the next keyframe ≥ the specified segment_time. The `-reset_timestamps 1` flag only resets PTS — it doesn't move keyframes.

**How to avoid:**
- Accept the drift. Downstream (Gemini / OpenRouter) doesn't care whether a chunk is 298s or 312s.
- Use the *actual* probed duration of each chunk file for `end_global` calculation rather than nominal 300s multiples — run ffprobe on each chunk and accumulate. This is O(N chunks) and cheap (ffprobe on a local file is ~50ms).
- DO NOT try to force exact 300s cuts by re-encoding (`-force_key_frames`) — that defeats the entire point of stream copy (speed, fidelity, cost).

**Warning signs:**
- A video's last-chunk duration is dramatically larger than expected (e.g., 420s instead of ~60s) — indicates massive GOP, which is rare but possible with screen recordings.
- Merged artifact's `chunking_metadata.total_duration_s` doesn't match `source.duration_seconds`.

### Pitfall 2: Merger double-validation or skipped validation

**What goes wrong:** Either (a) calling `validate_artifact` per-chunk AND at merge-end and wasting work, OR (b) relying on per-chunk validation alone and shipping a merged artifact that violates the schema (e.g., union-dedup produced an invalid enum, or `section_structure` ended up with overlapping timestamps).

**Why it happens:** Provider tools already validate (`gemini_video_analyzer.py:432`, `openrouter_video_analyzer.py:562`). The merger transforms those validated inputs in ways that can still break the merged output.

**How to avoid:** Validate exactly once — at the *end* of `merge_analyses`. Trust that provider inputs are schema-valid (already enforced upstream).

**Warning signs:** Any unit test of the merger that doesn't call `validate_artifact("video_analysis", merged)` at the assert block.

### Pitfall 3: Array-valued field unbounded growth

**What goes wrong:** A 60-min video split into 12 chunks can produce 12 × 10 transition types = 120 entries in `transition_types` after naive concat, or 60 entries in `dominant_colors_hex` after union. The schema doesn't cap these, but downstream synthesizer (Phase 5) will struggle with a noise-heavy prompt.

**Why it happens:** Array fields have no `maxItems` in the schema; union-without-cap runs unbounded.

**How to avoid:** For array-of-enum fields (`transition_types`, `suggested_remotion_scene_types`), dedup alone is sufficient because the enum space is small (6 transitions, limited scene types). For array-of-hex-color fields (`dominant_colors_hex`, `color_palette.*`), cap at **N=5** by occurrence frequency across chunks — the top-5 most-cited colors are a reasonable palette.

**Warning signs:** Merged artifact has > 8 transition types or > 10 dominant colors. Almost certainly a merger bug, not a legit signal.

### Pitfall 4: ThreadPoolExecutor worker count hurts more than helps

**What goes wrong:** Setting `max_workers=8` on a rate-limited API causes 429s; the chunks run "slower than 4" because of retries.

**Why it happens:** Gemini Files API and OpenRouter both have per-minute rate limits (default tier: Gemini 2 RPM for video + limits on upload rate; OpenRouter varies by model).

**How to avoid:** Start at `max_workers=4` (CONTEXT default). Allow env override `VIDEO_CHUNK_WORKERS` clamped to [1, 8]. Surface 429 errors loudly so the caller can reduce concurrency.

**Warning signs:** Test fixtures or real runs showing chunk failures dominated by 429 / rate-limit errors — reduce `max_workers` not "add retry logic".

### Pitfall 5: Temp file cleanup races with in-flight analysis

**What goes wrong:** `cleanup(chunks)` runs in the chunker's context manager (`with tempfile.TemporaryDirectory()`), tears down the chunk files, and the still-running async analysis calls `FileNotFoundError`.

**Why it happens:** `TemporaryDirectory` cleans on context exit; if the caller `return`s chunks before analysis, those paths are invalid immediately.

**How to avoid:** CONTEXT locks `tempfile.mkdtemp(prefix="omvid_chunks_")` returning a plain path. Cleanup is the *caller's* (`analyze_chunked`) responsibility via `try/finally`. The chunker ONLY splits; it does NOT own the lifecycle of post-split artifacts.

**Warning signs:** `FileNotFoundError` deep in provider code mid-analysis.

### Pitfall 6: Confidence aggregation diluting "low" signals

**What goes wrong:** Merging confidence via mode or average means "low" from one chunk gets outvoted by "high" from three others. Downstream (Phase 5 synthesizer) treats the field as high-confidence and makes a bad call.

**Why it happens:** "Low" is an honest signal from the model that *it couldn't tell*. Averaging it away is a lie.

**How to avoid:** Worst-case min — ANY "low" → "low"; else ANY "medium" → "medium"; else "high". This preserves the pessimism correctly.

**Warning signs:** Merged artifact has `confidence: high` on a field where 3/4 chunks said "low" — obvious merger bug.

### Pitfall 7: Cost tracker entries not correlated across chunks

**What goes wrong:** Calling `cost_tracker.estimate()` per chunk without correlating to the parent `analyze_chunked` operation; budget reports show 12 line items with no way to see "this was one chunked analysis".

**Why it happens:** `cost_tracker.estimate(tool, operation, estimated_usd)` has no parent_id / correlation concept natively (`cost_tracker.py:101-115`).

**How to avoid:** Use a descriptive `operation` string like `f"chunked_analysis[chunk {i}/{N} of {video_name}]"` so log inspection can filter by video. Consider proposing a `group_id` field addition in a follow-up (out of Phase 4 scope — record as an Open Question).

**Warning signs:** Hard-to-diagnose "why did this video cost $5" from cost_log.json.

## Code Examples

### Cost estimation heuristic

```python
# Source: Gemini video token rate [CITED: ai.google.dev/gemini-api/docs/tokens]
# Video input = 263 tokens/second = 15_780 tokens/minute.
# Output: analysis artifact is ~2-4 KB JSON ≈ 800-1600 output tokens per chunk (measured empirically in Phase 2 tests).

# Pricing [VERIFIED: openrouter.ai/google/gemini-3.1-pro-preview, 2026-04-17]
# Gemini 3.1 Pro Preview:
#   input:  $2 / 1M tokens
#   output: $12 / 1M tokens
# Gemini 2.5 Pro (fallback):
#   input:  $1.25 / 1M tokens (<=200k context)
#   output: $10 / 1M tokens

_TOKENS_PER_VIDEO_SECOND = 263  # Gemini's documented rate
_OUTPUT_TOKENS_PER_CHUNK = 1500  # empirical upper bound for compact artifact

_PRICING = {
    # per-million-token rates (USD)
    "gemini-3.1-pro-preview":      {"input": 2.00, "output": 12.00, "verified": "2026-04-17"},
    "gemini-2.5-pro":              {"input": 1.25, "output": 10.00, "verified": "2026-04-17"},
    "google/gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00, "verified": "2026-04-17"},
    "google/gemini-2.5-pro":        {"input": 1.25, "output": 10.00, "verified": "2026-04-17"},
}

def estimate_chunked_cost(
    provider: str,
    duration_seconds: float,
    model: str,
    max_chunk_seconds: float = 300.0,
) -> dict:
    """Rough cost estimate ±30% uncertainty per CONTEXT guidance."""
    pricing = _PRICING.get(model)
    if pricing is None:
        return {
            "total_usd": None,
            "confidence": "unknown",
            "note": f"No pricing table entry for model {model!r}",
        }
    chunk_count = max(1, int(-(-duration_seconds // max_chunk_seconds)))  # ceil div
    input_tokens = duration_seconds * _TOKENS_PER_VIDEO_SECOND
    output_tokens = chunk_count * _OUTPUT_TOKENS_PER_CHUNK
    total = (
        input_tokens * pricing["input"] / 1_000_000
        + output_tokens * pricing["output"] / 1_000_000
    )
    return {
        "total_usd": round(total, 4),
        "low_usd": round(total * 0.7, 4),
        "high_usd": round(total * 1.3, 4),
        "chunk_count": chunk_count,
        "input_tokens_est": int(input_tokens),
        "output_tokens_est": int(output_tokens),
        "pricing_verified_at": pricing["verified"],
    }
```

### Error class

```python
# lib/analysis_errors.py — append VideoChunkingError.
# [VERIFIED: lib/analysis_errors.py:15 — VideoAnalysisError is the base]

class VideoChunkingError(VideoAnalysisError):
    """Raised when FFmpeg split / ffprobe duration probe fails.

    Extends VideoAnalysisError so `except VideoAnalysisError` in callers
    catches both analysis AND chunking failures with the same handler.
    This is deliberate — the caller rarely needs to distinguish "chunking
    failed" from "analysis failed" (both mean "cannot produce a merged
    video_analysis artifact for this input").
    """
```

**Rationale for extending `VideoAnalysisError` (not sibling):** The caller of `analyze_chunked` — the Phase 6 meta skill — wants a single exception hierarchy to catch. Extending keeps that surface flat. It also mirrors the Phase 2 precedent (`VideoUploadError(VideoAnalysisError)` at `lib/analysis_errors.py:19`).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `-ss/-t` per-chunk loop | `-f segment` single pass | FFmpeg 2.8+ (2015) | 10× faster for N chunks; simpler command |
| Gemini 2.5 Pro | Gemini 3.1 Pro Preview | 2026-02 | Higher quality video analysis; preview pricing ($2/$12 vs $1.25/$10) |
| `tempfile.mkdtemp` + manual rmtree | `TemporaryDirectory` context manager | Python 3.2+ | Usually correct; our case needs deferred cleanup → stick with `mkdtemp` |

**Deprecated/outdated:**
- Using `ffmpeg -ss 00:05:00 -t 00:05:00` in a Python loop — slower, doesn't align to keyframes automatically, deprecated in favor of segment muxer since ~2015.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `ffmpeg` (CLI) | `lib/video_chunker.py` split | ✗ | — | MUST be installed on execution host; `scene_detect.py` already declares it required. In this research sandbox it is missing. |
| `ffprobe` (CLI) | `lib/video_chunker.py` duration probe | ✗ | — | Same as ffmpeg — they ship together; sandbox missing. |
| `pytest` | unit + contract tests | ✓ | 9.0.3 | — |
| `python3` | all code | ✓ | 3.11.2 | — |
| `jsonschema` | merger validation gate | ✓ | (≥4.20 per requirements.txt:4) | — |

**Missing dependencies with no fallback:**
- `ffmpeg` / `ffprobe` — Phase 4 code CANNOT run or be integration-tested on this research sandbox. Unit tests mock subprocess so CI without ffmpeg still passes; contract/integration tests gated by `RUN_INTEGRATION_TESTS=1` will need a host with ffmpeg.

**Missing dependencies with fallback:** None.

**Action for planner:** Ensure test plan separates "unit (mock subprocess, CI-safe)" from "integration (requires ffmpeg, gated by env var)". This matches the existing pattern in `tests/unit/test_gemini_video_analyzer.py` (all mocked) vs the TEST-02 requirement (RUN_INTEGRATION_TESTS=1).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest 9.0.3` |
| Config file | none — tests discoverable via default `tests/` layout; `tests/unit/conftest.py` provides shared fixtures |
| Quick run command | `pytest tests/unit/test_video_chunker.py tests/unit/test_analysis_merger.py tests/unit/test_chunked_analyzer.py -x -q` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CHUNK-01 | `split_video` invokes `ffmpeg -c copy -f segment -reset_timestamps 1 -segment_time 300 …` with expected args | unit (subprocess mocked) | `pytest tests/unit/test_video_chunker.py::test_ffmpeg_invocation_args -x` | ❌ Wave 0 |
| CHUNK-01 | `split_video` returns `Chunk` namedtuples with monotonic `start_global` and correct `local_path` list | unit | `pytest tests/unit/test_video_chunker.py::test_chunk_structure -x` | ❌ Wave 0 |
| CHUNK-01 | ffprobe duration probe parses scalar output correctly | unit (subprocess mocked) | `pytest tests/unit/test_video_chunker.py::test_duration_probe -x` | ❌ Wave 0 |
| CHUNK-01 | ffmpeg failure (non-zero exit) raises `VideoChunkingError` | unit | `pytest tests/unit/test_video_chunker.py::test_ffmpeg_failure_raises -x` | ❌ Wave 0 |
| CHUNK-02 | ≤300s video returns single-chunk list pointing at original path, no tempdir | unit | `pytest tests/unit/test_video_chunker.py::test_short_video_bypass -x` | ❌ Wave 0 |
| CHUNK-03 | ThreadPoolExecutor uses `max_workers` from env with clamp [1,8] | unit | `pytest tests/unit/test_chunked_analyzer.py::test_worker_count_clamp -x` | ❌ Wave 0 |
| CHUNK-03 | `on_chunk_done` callback called once per chunk with `(idx, ToolResult)` | unit | `pytest tests/unit/test_chunked_analyzer.py::test_callback_per_chunk -x` | ❌ Wave 0 |
| CHUNK-03 | fail-fast mode raises first exception; continue mode skips and merges survivors | unit | `pytest tests/unit/test_chunked_analyzer.py::test_error_modes -x` | ❌ Wave 0 |
| CHUNK-03 | Temp files cleaned up even when analysis raises | unit | `pytest tests/unit/test_chunked_analyzer.py::test_cleanup_on_exception -x` | ❌ Wave 0 |
| CHUNK-04 | Numeric fields duration-weighted avg (e.g., `cuts_per_minute`) | unit | `pytest tests/unit/test_analysis_merger.py::test_numeric_weighted_avg -x` | ❌ Wave 0 |
| CHUNK-04 | Enum fields duration-weighted majority vote (e.g., `pacing_style`) | unit | `pytest tests/unit/test_analysis_merger.py::test_enum_majority_vote -x` | ❌ Wave 0 |
| CHUNK-04 | `section_structure` concatenated with `approx_start_s += chunk.start_global` | unit | `pytest tests/unit/test_analysis_merger.py::test_section_structure_time_shift -x` | ❌ Wave 0 |
| CHUNK-04 | `energy_arc` concatenated with `timestamp_s += chunk.start_global` | unit | `pytest tests/unit/test_analysis_merger.py::test_energy_arc_time_shift -x` | ❌ Wave 0 |
| CHUNK-04 | Boolean fields OR-aggregated (`has_narration`, `has_music`, `has_sfx`) | unit | `pytest tests/unit/test_analysis_merger.py::test_boolean_or -x` | ❌ Wave 0 |
| CHUNK-04 | `hook_*` from first chunk; `cta_*` from last chunk | unit | `pytest tests/unit/test_analysis_merger.py::test_hook_cta_positioning -x` | ❌ Wave 0 |
| CHUNK-04 | Confidence worst-case min (any "low" → "low") | unit | `pytest tests/unit/test_analysis_merger.py::test_confidence_worst_case -x` | ❌ Wave 0 |
| CHUNK-04 | `transition_types` / `suggested_remotion_scene_types` union-dedup | unit | `pytest tests/unit/test_analysis_merger.py::test_array_union_dedup -x` | ❌ Wave 0 |
| CHUNK-04 | `dominant_colors_hex` capped at 5 by frequency | unit | `pytest tests/unit/test_analysis_merger.py::test_color_cap -x` | ❌ Wave 0 |
| CHUNK-04 | Merged artifact passes `validate_artifact("video_analysis", merged)` | unit | `pytest tests/unit/test_analysis_merger.py::test_merged_artifact_schema_valid -x` | ❌ Wave 0 |
| CHUNK-04 | Merger handles N=1 chunk as pass-through (with chunking_metadata added) | unit | `pytest tests/unit/test_analysis_merger.py::test_single_chunk_passthrough -x` | ❌ Wave 0 |
| CHUNK-05 | `chunking_metadata.chunk_count`, `total_duration_s`, `provider`, `per_chunk[]` populated correctly | unit | `pytest tests/unit/test_analysis_merger.py::test_chunking_metadata_shape -x` | ❌ Wave 0 |
| CHUNK-06 | `cost_tracker.estimate/reserve/reconcile` called per chunk | unit | `pytest tests/unit/test_chunked_analyzer.py::test_cost_tracker_per_chunk -x` | ❌ Wave 0 |
| CHUNK-06 | `estimate_chunked_cost` returns dict with `total_usd`, `low_usd`, `high_usd` | unit | `pytest tests/unit/test_chunked_analyzer.py::test_estimate_chunked_cost -x` | ❌ Wave 0 |
| CHUNK-03 end-to-end | Chunked path with mocked provider produces schema-valid merged artifact | contract | `pytest tests/contracts/test_phase4_chunked_path.py -x` | ❌ Wave 0 |
| — | Ensure selector + chunker integration leaves selector single-shot (no regression) | contract | `pytest tests/contracts/test_phase3_contracts.py -x` | ✅ Exists |

### Sampling Rate

- **Per task commit:** `pytest tests/unit/test_video_chunker.py tests/unit/test_analysis_merger.py tests/unit/test_chunked_analyzer.py -x -q` (fast; mocks subprocess and ThreadPoolExecutor)
- **Per wave merge:** `pytest tests/unit/ tests/contracts/ -x` (full unit + contract; still mocks subprocess)
- **Phase gate:** Full suite green before `/gsd-verify-work`. Integration tests (`RUN_INTEGRATION_TESTS=1`) are Phase 7, NOT Phase 4 gate.

### Wave 0 Gaps

- [ ] `tests/unit/test_video_chunker.py` — covers CHUNK-01, CHUNK-02
- [ ] `tests/unit/test_analysis_merger.py` — covers CHUNK-04, CHUNK-05
- [ ] `tests/unit/test_chunked_analyzer.py` — covers CHUNK-03, CHUNK-06
- [ ] `tests/contracts/test_phase4_chunked_path.py` — end-to-end chunked path with mocked provider (contract-level smoke)
- [ ] Shared fixture in `tests/unit/conftest.py`: `fake_video_chunks(valid_artifact)` — generate N per-chunk artifacts with distinct pacing_style / cuts_per_minute values so merger tests can assert weighted math without hand-crafting each fixture
- [ ] No new framework install needed (pytest 9.0.3 already present)
- [ ] No new dependency add needed

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Gemini 3.1 Pro Preview video cost ≈ $2 input / $12 output per 1M tokens on OpenRouter | Code Examples / cost estimation | Cost estimate off by up to 2×; user sees wrong "before you run" number but actuals reconcile via `cost_tracker.reconcile` from real response.usage.cost. Low risk — labeled ±30%. |
| A2 | Gemini 2.5 Pro pricing ≈ $1.25 input / $10 output per 1M (<200k context) | Code Examples / cost estimation | Same as A1 |
| A3 | Output tokens per chunk ≈ 1500 for canonical artifact | Code Examples | Empirical — may vary by video complexity; estimate is already ±30% |
| A4 | ThreadPoolExecutor `max_workers=4` stays under Gemini/OpenRouter rate limits for typical inputs | Pitfall 4 | 429s on aggressive concurrency; mitigated by env override `VIDEO_CHUNK_WORKERS` and fail-fast default |
| A5 | Chunks need `ffprobe` per-chunk duration probe to compute accurate `end_global` (not nominal multiples) | Pitfall 1 | If skipped, `chunking_metadata.total_duration_s` may disagree with `source.duration_seconds` on videos with long GOP; cosmetic but visible in the artifact |
| A6 | `VideoChunkingError` should extend `VideoAnalysisError` (not sibling) | § Code Examples / Error class | Minor — if callers wanted to handle chunking separately from analysis they could, but the plan keeps them unified. Low risk. |
| A7 | `dominant_colors_hex` cap at N=5 is an acceptable arbitrary | Pitfall 3 | If too low, synthesizer gets fewer palette hints; if too high, prompt noise. 5 is the common "brand palette" count — reasonable default |
| A8 | Free-text field concat marker `[chunk N/M]` is acceptable to downstream synthesizer | Pattern 5 | Synthesizer not built yet (Phase 5); marker format may need adjustment — low risk, trivial change |

## Open Questions

1. **Should `cost_tracker.estimate/reserve/reconcile` gain a `group_id` field for correlating chunk costs?**
   - What we know: Current API is flat; each chunk = separate entry in `cost_log.json`.
   - What's unclear: Whether a future observability requirement (v2.1 OBS-01) needs per-run rollup — if yes, patching `cost_tracker.py` mid-Phase-4 creates scope creep.
   - Recommendation: Do NOT modify `cost_tracker.py` in Phase 4. Use descriptive `operation` strings (`f"chunked_analysis[chunk {i}/{N}]"`) for now; track a v2.1 ticket to add correlation.

2. **When providers disagree on `shot_boundary_source` across chunks, should merged output be "hybrid" or "model"?**
   - What we know: Schema enum is scene_detect / model / hybrid.
   - What's unclear: Whether "hybrid" should mean "this run used both" (cross-chunk) OR only "this chunk used both" (intra-chunk per ANLZ-05).
   - Recommendation: "hybrid" = ANY chunk hybrid OR disagreement across chunks. Document this in merger docstring.

3. **Median-of-medians approximation for `median_shot_duration_seconds`**
   - What we know: Field is optional per schema; duration-weighted avg is lossy.
   - What's unclear: Whether downstream (synthesizer) reads this field at all.
   - Recommendation: Document the approximation in merger docstring; consider omitting the field entirely if Phase 5 doesn't read it. Decision deferred to Phase 5 integration review.

4. **Should the chunker return the *original file path* for ≤5 min videos (bypass), or copy it into a tempdir for lifecycle symmetry?**
   - What we know: CONTEXT locks "bypass — don't duplicate".
   - What's unclear: The `try/finally` cleanup in `analyze_chunked` would need to check `if chunk.local_path != video_path` before unlinking; otherwise it deletes the user's input video.
   - Recommendation: Sentinel check in cleanup. Mandatory test case: "cleanup does not delete original file for single-chunk bypass."

## Sources

### Primary (HIGH confidence)

- **FFmpeg segment muxer docs** — `https://ffmpeg.org/ffmpeg-formats.html#segment` — verified options `-f segment`, `-segment_time`, `-reset_timestamps`, behavior with `-c copy`
- **Gemini API tokens docs** — `https://ai.google.dev/gemini-api/docs/tokens` — verified video tokens = 263 tokens/second
- **Python concurrent.futures docs** — `https://docs.python.org/3/library/concurrent.futures.html` — ThreadPoolExecutor + as_completed contract
- **Python tempfile docs** — `https://docs.python.org/3/library/tempfile.html` — mkdtemp vs TemporaryDirectory tradeoffs
- **Canonical schema** — `/workspace/schemas/artifacts/video_analysis.schema.json` — all merger field rules derive from this
- **Existing repo patterns** — `/workspace/tools/analysis/scene_detect.py:196-202`, `/workspace/lib/analysis_errors.py`, `/workspace/tools/cost_tracker.py:101-165`, `/workspace/tests/unit/conftest.py`

### Secondary (MEDIUM confidence)

- **OpenRouter Gemini 3.1 Pro Preview pricing page** — `https://openrouter.ai/google/gemini-3.1-pro-preview` — $2 input / $12 output per 1M tokens (preview; volatile)
- **FFmpeg segment muxer keyframe alignment — community confirmations** (Mux, Baeldung articles) — stream copy aligns to keyframes automatically; `-force_key_frames` requires re-encode

### Tertiary (LOW confidence)

- Gemini output tokens per chunk (~1500) — empirical estimate, not measured in this research session

## Metadata

**Confidence breakdown:**
- FFmpeg segment behavior: HIGH — official docs + existing repo usage pattern cross-verified
- ThreadPoolExecutor pattern: HIGH — stdlib docs + existing Python idioms
- Merger rules per dimension: HIGH — derived directly from canonical schema; every field enumerated
- Cost estimation: MEDIUM — pricing volatile; rates stamped with verification date so staleness is visible
- Confidence aggregation rule: HIGH — worst-case min is the only honest aggregation; Pitfall 6 explains
- Error hierarchy placement: HIGH — mirrors Phase 2 `VideoUploadError(VideoAnalysisError)` precedent

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 for cost / pricing numbers; 2026-10-17 for FFmpeg / stdlib patterns (stable).
