---
phase: 04-chunking
plan: 01
subsystem: video-chunking
tags: [chunking, ffmpeg, ffprobe, subprocess, tdd]
requires: []
provides:
  - "Chunk namedtuple (start_global, end_global, local_path)"
  - "split_video(video_path, max_chunk_seconds=300.0) -> list[Chunk]"
  - "cleanup_chunks(chunks, original_path) -> None"
  - "VideoChunkingError(VideoAnalysisError)"
affects:
  - lib/video_chunker.py (new)
  - lib/analysis_errors.py (+1 class)
  - tests/unit/test_video_chunker.py (new)
tech-stack:
  added:
    - "FFmpeg segment muxer (-c copy -f segment -reset_timestamps 1)"
    - "ffprobe duration probe (format=duration)"
  patterns:
    - "Pure lib module (no BaseTool ancestry, no execute, no registry)"
    - "tempfile.mkdtemp with caller-owned cleanup lifecycle"
    - "TDD: RED (failing tests + error class) -> GREEN (impl) -> commit per phase"
    - "Subprocess safety: list argv, shell=False, explicit timeouts"
    - "Bypass sentinel guard in cleanup (protects user input file)"
key-files:
  created:
    - lib/video_chunker.py
    - tests/unit/test_video_chunker.py
  modified:
    - lib/analysis_errors.py
decisions:
  - "Implemented Task 1 + Task 2 in a single RED/GREEN cycle — tests for both tasks written together since the Chunk contract is shared and TDD round-trips are cheaper combined."
  - "Added two extra tests beyond the 17 spec'd: test_empty_glob_raises_and_cleans and test_cleanup_chunks_dedups_parents — both cover edge cases called out in RESEARCH Pattern 2 / Pitfall 5 that lacked explicit test coverage in the plan."
  - "Added TimeoutExpired handling (not spec'd but required by T-04-02 threat register)."
metrics:
  duration_minutes: 4
  completed_date: "2026-04-17"
  tasks_completed: 2
  commits: 2
  tests_added: 19
  tests_passing: 19
requirements:
  - CHUNK-01
  - CHUNK-02
---

# Phase 4 Plan 01: Video Chunker Summary

FFmpeg stream-copy video splitter (≤5 min bypass, >5 min segment) with `VideoChunkingError` + bypass-sentinel cleanup guard, fully unit-tested with mocked subprocess.

## Outcome

`lib/video_chunker.py` ships the Phase 4 substrate — a pure lib module (not a BaseTool) exposing `Chunk`, `split_video`, and `cleanup_chunks`. Videos ≤ `max_chunk_seconds` (default 300s) return a single-element list pointing at the user's original path with no ffmpeg call and no tempdir. Videos beyond that boundary flow through `ffmpeg -c copy -f segment -reset_timestamps 1` into a `tempfile.mkdtemp`-owned scratch directory whose lifecycle transfers to the caller. Per-chunk real durations are ffprobed individually so `start_global`/`end_global` reflect actual keyframe-aligned cuts, not nominal 300s multiples (RESEARCH Pitfall 1).

`lib/analysis_errors.py` gains `VideoChunkingError(VideoAnalysisError)` — a single-class append that lets Phase-6 callers use one `except VideoAnalysisError` to catch both analysis and chunking failures.

## Files

| Path | Role | Lines |
|------|------|------:|
| `lib/video_chunker.py` | `Chunk` / `split_video` / `cleanup_chunks` / `_probe_duration_seconds` | 264 |
| `tests/unit/test_video_chunker.py` | Full unit coverage; subprocess mocked via `FakeRun` sequencer | 454 |
| `lib/analysis_errors.py` | +1 class (`VideoChunkingError`) + 1 docstring bullet | +19 |

## Commits

| Hash | Message |
|------|---------|
| `44bf900` | `test(04-01): add failing tests for video_chunker + VideoChunkingError` |
| `82c65d4` | `feat(04-01): implement lib/video_chunker.py (FFmpeg stream-copy splitter)` |

## Tests

19 unit tests, all green. Subprocess mocked throughout so CI without ffmpeg stays green.

| Category | Tests |
|----------|------:|
| `Chunk` namedtuple contract | 1 |
| `VideoChunkingError` hierarchy | 1 |
| ffprobe duration probe (parse + error modes) | 3 |
| Bypass path (≤ max_chunk_seconds, exact boundary) | 2 |
| Multi-chunk ffmpeg invocation argv shape | 1 |
| Per-chunk structure + monotonic starts + sorted paths | 2 |
| ffmpeg failure → rmtree + VideoChunkingError | 1 |
| ffmpeg success → tmpdir preserved | 1 |
| ffprobe called per chunk (N+1 total) | 1 |
| Empty glob → cleanup + raise | 1 |
| Nonexistent input → VideoChunkingError | 1 |
| `cleanup_chunks` — rmtree parents | 1 |
| `cleanup_chunks` — skip bypass sentinel (T-04-04 regression) | 1 |
| `cleanup_chunks` — ignore_errors kwarg | 1 |
| `cleanup_chunks` — dedup parent dirs | 1 |

Run:
```
python3 -m pytest tests/unit/test_video_chunker.py -x -q
# 19 passed in 0.59s
```

## Verification Evidence

- `grep -n 'class VideoChunkingError' lib/analysis_errors.py` → `32:class VideoChunkingError(VideoAnalysisError):`
- `grep -n 'shell=' lib/video_chunker.py` → both real subprocess invocations pass `shell=False` explicitly (T-04-01 mitigation).
- `python3 -c "from lib.video_chunker import split_video, Chunk, cleanup_chunks; from lib.analysis_errors import VideoChunkingError, VideoAnalysisError; assert issubclass(VideoChunkingError, VideoAnalysisError)"` → OK.
- No new dependencies.

## Deviations from Plan

**Consolidated Task 1 + Task 2 into a single RED/GREEN pair.** The plan sequenced them as two separate TDD cycles (scaffold bypass → add multi-chunk path). Because the `Chunk` contract + public API + error class are shared across both tasks and the tests for the multi-chunk path inherently require the bypass path to already work, writing the full test suite up front and implementing the full module in one GREEN pass produced the same shipped artifact with cleaner commit history (one `test(04-01)` commit with all failing tests + error class, one `feat(04-01)` commit with the full implementation). All plan-level `<done>` criteria are covered; test count target (17) is exceeded (19 tests).

**Additional tests beyond plan spec (Rule 2 — correctness):**
- `test_empty_glob_raises_and_cleans` — covers the `ffmpeg exits 0 but emits no files` branch that RESEARCH Pattern 2 calls out but the plan's test list did not name explicitly. Without it, a silent mis-config could ship an empty `chunks == []` list to the merger.
- `test_cleanup_chunks_dedups_parents` — verifies the `set[Path]` dedup so the helper doesn't call `rmtree` multiple times on the same directory when chunks share a parent (the common case).

**Added `subprocess.TimeoutExpired` handling** beyond the plan's `CalledProcessError`-only spec — the `<threat_model>` T-04-02 explicitly calls out unbounded subprocess DoS and lists `subprocess.TimeoutExpired` as the surface mitigation. Both `_probe_duration_seconds` and the ffmpeg split branch now catch timeouts and re-raise as `VideoChunkingError` (Rule 2 — threat register mitigation).

## RESEARCH Open Questions Touched

| # | Question | How Plan-01 Handled It |
|---|----------|------------------------|
| 4 | Should `cleanup_chunks` delete the user's original file on bypass? | **No.** Sentinel guard (`if ch.local_path == str(original_path): continue`) implemented + covered by `test_cleanup_chunks_skips_bypass_sentinel` — direct T-04-04 regression test. |
| 1 | `cost_tracker.group_id` correlation | Not touched (Plan 03 scope). |
| 2 | `shot_boundary_source` disagreement merge rule | Not touched (Plan 02 scope). |
| 3 | `median_shot_duration_seconds` approximation | Not touched (Plan 02 scope). |

## Downstream Dependencies

Both remaining Phase-4 plans consume this file:

- **Plan 02 (`lib/analysis_merger.py`)** imports `Chunk` from `lib.video_chunker` to type its `list[tuple[Chunk, dict]]` argument. It also imports `VideoChunkingError` is NOT needed — the merger raises `VideoAnalysisError` subtypes only when validation fails.
- **Plan 03 (`lib/chunked_analyzer.py`)** imports `Chunk`, `split_video`, `cleanup_chunks`, and `VideoChunkingError`. The `try/finally` around analysis will call `cleanup_chunks(chunks, video_path)` so the bypass sentinel matters for that plan's correctness.

## Self-Check: PASSED

- File `lib/video_chunker.py` exists (264 lines) ✓
- File `tests/unit/test_video_chunker.py` exists (454 lines, 19 test functions) ✓
- Commit `44bf900` in log ✓
- Commit `82c65d4` in log ✓
- `lib.analysis_errors.VideoChunkingError` importable and subclass of `VideoAnalysisError` ✓
- `python3 -m pytest tests/unit/test_video_chunker.py -x -q` → 19 passed ✓
- All 8 plan success-criteria items met ✓
- No new dependencies added to `requirements*.txt` ✓
