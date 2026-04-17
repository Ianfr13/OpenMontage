"""Error taxonomy for video-analysis tools.

Shared by `tools/analysis/gemini_video_analyzer.py`, the selector, and
Phase 3's `openrouter_video_analyzer`. Mirrors the one-module-per-lib-namespace
convention set by `lib/checkpoint.py::CheckpointValidationError`.

- `VideoAnalysisError`          — base; analysis-time failures (truncation, server error, bad response)
- `VideoUploadError`            — upload-time failures (FAILED state, poll timeout, unsupported format, missing API key)
- `VideoChunkingError`          — FFmpeg split / ffprobe duration probe failures (Phase 4)
- `VideoAnalysisRetryExhausted` — the one retry with `analysis_depth="compact"` also failed
"""

from __future__ import annotations


class VideoAnalysisError(Exception):
    """Base class for all video-analysis failures."""


class VideoUploadError(VideoAnalysisError):
    """Raised when an upstream video-analysis tool fails to upload or
    transition the uploaded file into a ready state.

    Covers:
      * Files API returning `state == FAILED`
      * Wall-clock timeout waiting for `state == ACTIVE`
      * Missing credentials (`GEMINI_API_KEY` / `GOOGLE_API_KEY` unset)
      * Unsupported file format / unreadable local path
    """


class VideoChunkingError(VideoAnalysisError):
    """Raised when FFmpeg split / ffprobe duration probe fails.

    Extends VideoAnalysisError so `except VideoAnalysisError` in callers
    catches both analysis AND chunking failures with the same handler.
    This is deliberate — the caller rarely needs to distinguish "chunking
    failed" from "analysis failed" (both mean "cannot produce a merged
    video_analysis artifact for this input").

    Covers:
      * `ffmpeg -f segment` non-zero exit (stderr captured in message)
      * `ffprobe` non-zero exit or unparseable stdout
      * ffmpeg producing no chunk files despite exit 0
      * Input path missing / not a regular file
      * subprocess timeout on either binary
    """


class VideoAnalysisRetryExhausted(VideoAnalysisError):
    """Raised after the single retry with `analysis_depth="compact"` also
    fails (null text, `MAX_TOKENS` finish, parse error, or server error).

    Terminal — the tool's `execute()` catches this and returns
    `ToolResult(success=False, error=str(exc))`.
    """
