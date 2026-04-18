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


class VideoAnalysisAuthError(VideoAnalysisError):
    """Raised when the analysis call fails with a non-retriable auth/permission
    error (401 AuthenticationError or 403 PermissionDeniedError from the openai
    SDK). Fast-fail — `execute()` surfaces this directly without invoking the
    compact-retry ladder.

    See Phase 8 CLEAN-01 / v2.0 Phase 3 REVIEW HI-01. Splitting this out of
    `VideoAnalysisError` prevents `_analyze_with_fallback` from re-trying
    against a known-bad key.
    """


class VideoAnalysisRateLimitError(VideoAnalysisError):
    """Raised when the analysis call returns a 429 RateLimitError. The openai
    SDK's own `max_retries` already handled transient rate limits; this
    exception only propagates AFTER the SDK gave up, so re-running the compact
    ladder would just compound the rate-limit. Fast-fail in `execute()`.

    See Phase 8 CLEAN-01 / v2.0 Phase 3 REVIEW HI-01.
    """


class MergeConsensusError(VideoAnalysisError):
    """Raised by `lib.analysis_merger` when consensus on a required field
    cannot be derived from any chunk (both the weighted-majority vote AND
    the first-chunk fallback yielded None).

    Replaces the v2.0 silent default-fallback pattern
    (`vote or dims[0].get(field, DEFAULT)`) which injected plausible-looking
    values the source video never actually had — masking upstream provider
    bugs and violating the single-validation-gate guarantee.

    See Phase 9 CLEAN-06 / v2.0 Phase 4 REVIEW MR-02. Subclasses
    `VideoAnalysisError` so existing callers that do `except VideoAnalysisError`
    continue to catch it.
    """


class InvalidPipelineSlug(VideoAnalysisError):
    """Raised by ``lib.pipeline_synthesizer._validate_slug`` when a slug
    passed to ``accept_synthesis`` or ``reject_synthesis`` fails the defensive
    regex (``^[a-z0-9][a-z0-9\\-_]{7,127}$``) or resolves outside the declared
    staging root ``pipeline_defs/_staging/``.

    Replaces the v2.0 "no validation at all" pattern on the public accept/
    reject entry points which let path-traversal payloads
    (``slug="../cinematic"``, absolute paths, shell metachars) reach
    ``shutil.move`` / ``src.unlink()`` directly — a latent hole because the
    only in-tree caller today constructs slugs via ``_build_slug`` (hex + hyphen
    only, deterministic). The guard closes the hole before an upstream refactor
    surfaces user input here without the synthesizer knowing.

    See Phase 10 CLEAN-08 / v2.0 Phase 5 REVIEW MR-01. Subclasses
    ``VideoAnalysisError`` so existing callers that do
    ``except VideoAnalysisError`` (the umbrella-handler pattern established by
    Phase 8 / Phase 9 sentinels) continue to catch it — mirroring
    ``VideoAnalysisAuthError`` and ``MergeConsensusError``.
    """
