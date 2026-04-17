# Phase 4: Chunking - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, tight cadence)

<domain>
## Phase Boundary

Make videos longer than 5 minutes analyzable. `lib/video_chunker.py` splits any video into ≤5min keyframe-aligned chunks using FFmpeg (`-c copy -reset_timestamps 1` — no re-encode). `lib/analysis_merger.py` merges per-chunk `video_analysis` artifacts into a single canonical artifact with normalized global timecodes, narrative hook from chunk 1, CTA from last chunk, audio weighted-averaged by duration, visual fields majority-vote weighted by duration. Chunks analyze with bounded concurrency (max 4 workers default). `chunking_metadata` attached to merged artifact for traceability. Cost estimated + surfaced BEFORE running long analyses so users can abort.

Out of scope: changing provider contracts (Phase 2/3 set those); synthesizer (Phase 5); docs (Phase 6).

</domain>

<decisions>
## Implementation Decisions

### Plan Decomposition (3 plans)
- `04-01-PLAN.md` — `lib/video_chunker.py` (ffmpeg split + duration probe + keyframe alignment) + unit tests. Pure lib module, no BaseTool.
- `04-02-PLAN.md` — `lib/analysis_merger.py` (per-dimension merge rules from REQUIREMENTS CHUNK-04) + unit tests. Pure lib module.
- `04-03-PLAN.md` — Selector + provider integration: the caller (selector or meta skill) uses the chunker+merger when video >5min. Contract tests for end-to-end chunked path. Cost estimation hook. ThreadPoolExecutor bounded concurrency.

### Chunker Shape (CHUNK-01, CHUNK-02, CHUNK-03)
- `split_video(video_path, max_chunk_seconds=300.0) -> list[Chunk]` where `Chunk = namedtuple("Chunk", ["start_global", "end_global", "local_path"])`
- Uses `ffmpeg -i {input} -c copy -reset_timestamps 1 -f segment -segment_time {max} -segment_start_number 0 {output_pattern}`. Stream copy (no re-encode).
- Detect ≤5min videos and return a single chunk equal to the original path (bypass, don't duplicate).
- Probe duration via `ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 {input}`.
- Keyframe alignment: FFmpeg segmenter with `-c copy` automatically aligns to keyframes; no explicit `-force_key_frames` needed (would require re-encode).
- Temp output dir: `tempfile.mkdtemp(prefix="omvid_chunks_")` with `cleanup(chunks)` helper to remove after analysis.

### Merger Shape (CHUNK-04, CHUNK-05)
- `merge_analyses(chunks: list[tuple[Chunk, dict]]) -> dict` — takes list of (chunk_metadata, per_chunk_artifact) pairs; returns merged canonical `video_analysis` artifact.
- Merge rules per REQUIREMENTS CHUNK-04:
  - **editing_pacing**: `cuts_per_minute` = weighted avg by chunk duration; `pacing_style` = majority vote (weighted by duration); `cut_type_distribution` = weighted avg per key; `section_structure` = concatenated with timecodes shifted by `start_global`.
  - **audio**: weighted averages on numerical fields (music_tempo_bpm, vocal_intensity); categorical fields (music_present, voiceover_present) = union/"any"; `mood_arc` concatenated.
  - **visual_style**: `dominant_visual_style` = majority vote; `shot_type_distribution` + `motion_type_distribution` = weighted avg; `dominant_colors_hex` = union (deduplicated, first-N by aggregate prominence).
  - **narrative**: `hook` from chunk 1; `cta` from last chunk; `arc` concatenated/summarized from per-chunk arcs; `target_platform` = first non-null.
- Global timecodes: any timestamp field (e.g., `section_structure[].start_seconds`) shifted by chunk's `start_global`.
- Confidence: aggregated confidence map per dimension — if ANY chunk has low confidence on a field, the merged field's confidence is "low".
- Merged artifact must pass `validate_artifact("video_analysis", ...)` — same schema contract.
- `chunking_metadata = {chunk_count, total_duration_seconds, per_chunk_cost, provider_used_per_chunk, chunker_version}` — attached to top-level.

### Integration (CHUNK-03, CHUNK-06)
- Selector or meta skill logic: if `duration > 300.0`, split → `ThreadPoolExecutor(max_workers=4)` → gather → merge → return merged artifact. Otherwise single-shot analyze.
- Bounded concurrency env override: `VIDEO_CHUNK_WORKERS` (default 4, min 1, max 8).
- Cost estimation: `estimate_chunked_cost(provider, duration, model) -> float` uses a rough heuristic (per-minute token cost per model); surfaced via a ToolResult before the run when duration > 300s. Caller can abort.
- `cost_tracker.py` integration: record each chunk analysis separately (`provider`, `model`, `chunk_index`, `input_tokens`, `output_tokens`, `cost_usd`). Total available after run.
- Partial progress: use `concurrent.futures.as_completed` so callers can observe per-chunk completion via a callback (optional `on_chunk_done=lambda chunk_idx, result: ...`).

### Where Integration Lives
- New module `lib/chunked_analyzer.py` with `analyze_chunked(video_path, provider_tool, on_chunk_done=None) -> dict` — used BY the meta skill (Phase 6 `skills/meta/reference-synthesis.md`). The selector stays single-shot; chunking wraps the selector's output when caller chooses chunked mode.
- Alternative: modify selector directly. REJECTED — keeps selector single-shot and thread-safe; chunking is a higher-level concern.

### Error Handling
- Per-chunk failure: by default `raise` the first exception (fail-fast). Optional `on_chunk_error="continue"` mode skips failed chunks and merges surviving ones (marks `chunking_metadata.failed_chunks`).
- Temp file cleanup: `try/finally` in `analyze_chunked` removes chunk files regardless of exception.

### Claude's Discretion
- Exact weighted-average algorithm for `mood_arc` (free-text field) — planner's call; recommend: string concatenation with chunk-boundary markers
- Partial-progress callback signature — planner decides based on what's ergonomic for Phase 6 meta skill consumer
- Default `max_workers` — recommend 4; planner can tune per research findings

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tools/cost_tracker.py` — already exists; check its record/get API shape during planning
- `tools/analysis/video_analyzer_selector.py` — selector is the default entry point the chunked_analyzer wraps
- Providers (Phase 2/3) — both producing canonical artifacts; chunker just calls them per-chunk
- `schemas/artifacts/__init__.py::validate_artifact` — gate on merged output
- Existing FFmpeg usage in repo — grep `subprocess.*ffmpeg` to find the existing wrapper style
- `tools/analysis/scene_detect.py` — already uses FFmpeg; mirror its subprocess pattern for shell safety

### Established Patterns
- Pure lib modules for non-BaseTool work (lib/checkpoint.py, lib/schema_adapter.py, lib/analysis_errors.py)
- subprocess for FFmpeg with explicit check + shell=False
- Tempfile for scratch outputs
- Error classes extending VideoAnalysisError when appropriate (new: `VideoChunkingError(VideoAnalysisError)` for ffmpeg failures)

</code_context>

<specifics>
## Specific Ideas

- `ffmpeg -c copy -reset_timestamps 1 -f segment -segment_time 300` — stream-copy mode, ~instant for most videos, keyframe-boundary aligned automatically
- Never re-encode chunks (inflates cost, adds latency, loses fidelity)
- Merger handles chunks-of-1 gracefully (if video ≤5min, single-shot analysis goes through chunker as 1-chunk → merger as pass-through)
- Cost estimation heuristic: `tokens_per_minute ≈ 8000` (Gemini video) × model cost per 1k tokens × duration in minutes, with +/-30% uncertainty displayed

</specifics>

<deferred>
## Deferred Ideas

- Adaptive chunk size based on content density (v2.1)
- Re-use chunk cache across runs (same video hash → reuse chunks) (OBS-02, v2.1)
- Parallel ffmpeg splitting for very large files (GB scale) — current bottleneck is analysis cost, not split time

</deferred>
