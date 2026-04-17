"""Error taxonomy for video-analysis tools.

Shared by `tools/analysis/gemini_video_analyzer.py`, the selector, and
Phase 3's `openrouter_video_analyzer`. Mirrors the one-module-per-lib-namespace
convention set by `lib/checkpoint.py::CheckpointValidationError`.

- `VideoAnalysisError`          — base; analysis-time failures (truncation, server error, bad response)
- `VideoUploadError`            — upload-time failures (FAILED state, poll timeout, unsupported format, missing API key)
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


class VideoAnalysisRetryExhausted(VideoAnalysisError):
    """Raised after the single retry with `analysis_depth="compact"` also
    fails (null text, `MAX_TOKENS` finish, parse error, or server error).

    Terminal — the tool's `execute()` catches this and returns
    `ToolResult(success=False, error=str(exc))`.
    """
