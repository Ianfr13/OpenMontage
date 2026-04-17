"""First video_analysis provider — Gemini direct via google-genai SDK.

Uses Files API for all uploads (no inline base64); polls until ACTIVE;
runs structured-output via response_json_schema; retries once on truncation
with analysis_depth="compact"; always deletes the uploaded file in finally;
falls back from preview model to gemini-2.5-pro on ClientError.

NEVER calls lib.checkpoint.write_checkpoint — the caller (meta skill /
orchestrator) owns checkpointing. Post-Phase 1 WR-05, write_checkpoint
REQUIRES a pipeline_type that this tool does not know.

Implements:
  * GEM-01 — BaseTool shape, capability/provider/runtime, explicit api_key
  * GEM-02 — Files API upload + ACTIVE polling with wall-clock timeout
  * GEM-03 — finally-block delete (success OR failure)
  * GEM-04 — structured output, MAX_TOKENS/empty retry, preview->2.5-pro fallback
  * ANLZ-04 — prompt directive: uncertain fields use confidence="low" (never null/absent)
  * ANLZ-05 — optional shot_boundaries input (accepts both [[s,e]] and dict forms)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import jsonschema
from google import genai
from google.genai import errors, types

from lib.analysis_errors import (
    VideoAnalysisError,
    VideoAnalysisRetryExhausted,
    VideoUploadError,
)
from lib.schema_adapter import to_api_schema
from schemas.artifacts import load_schema, validate_artifact
from tools.base_tool import (
    BaseTool,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)


logger = logging.getLogger(__name__)

DEFAULT_PREVIEW_MODEL = "gemini-3.1-pro-preview"
FALLBACK_MODEL = "gemini-2.5-pro"
DEFAULT_MAX_POLL_SECONDS = 300.0
POLL_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 5.0)  # capped at 5s after exhaustion


def _get_api_key() -> str | None:
    """Return API key per CONTEXT priority: GEMINI_API_KEY first, then GOOGLE_API_KEY.

    This is the OPPOSITE of google-genai SDK default (which prefers GOOGLE_API_KEY).
    See RESEARCH Finding 1 / Pitfall 1. Always pass this key EXPLICITLY to
    genai.Client(api_key=...) — do NOT rely on the SDK env-var resolver.
    """
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _resolve_model() -> str:
    """Return the model to try first — env override or the preview default."""
    return os.environ.get("GEMINI_VIDEO_MODEL") or DEFAULT_PREVIEW_MODEL


def _state_value(f: "types.File") -> str:
    """Extract the string value of a Files API state enum, tolerating either
    a native enum with .value or a plain string."""
    state = getattr(f, "state", None)
    if state is None:
        return "STATE_UNSPECIFIED"
    return getattr(state, "value", None) or str(state)


def _normalize_shot_boundaries(boundaries: Any) -> list[tuple[float, float]]:
    """Accept list of [start, end] OR list of {'start_seconds', 'end_seconds'}
    dicts (scene_detect output) and normalize to [(start, end), ...].

    Empty / None / malformed entries are silently dropped — the prompt just
    won't include that boundary. Format errors do NOT raise; they produce
    an empty list, which triggers shot_boundary_source='model' downstream.
    """
    if not boundaries:
        return []
    out: list[tuple[float, float]] = []
    for item in boundaries:
        try:
            if isinstance(item, dict):
                s = float(item["start_seconds"])
                e = float(item["end_seconds"])
            else:
                s = float(item[0])
                e = float(item[1])
            out.append((s, e))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out


def _format_shot_boundaries(pairs: list[tuple[float, float]]) -> str:
    """Render '0.0-3.4s, 3.4-5.8s, ...' for prompt embedding."""
    return ", ".join(f"{s:.1f}-{e:.1f}s" for s, e in pairs)


def _wait_for_active(
    client: "genai.Client",
    file_name: str,
    max_seconds: float,
) -> "types.File":
    """Poll Files API until state == ACTIVE. Raise VideoUploadError on FAILED
    or when elapsed >= max_seconds. Backoff per POLL_BACKOFF_SECONDS then 5s.
    """
    backoff = list(POLL_BACKOFF_SECONDS)
    start = time.monotonic()
    while True:
        f = client.files.get(name=file_name)
        state = _state_value(f)
        if state == "ACTIVE":
            return f
        if state == "FAILED":
            err = getattr(f, "error", None)
            raise VideoUploadError(
                f"Files API returned FAILED for {file_name}: {err!s}"
            )
        elapsed = time.monotonic() - start
        if elapsed >= max_seconds:
            raise VideoUploadError(
                f"Files API did not reach ACTIVE within {max_seconds:.0f}s "
                f"(last state={state})"
            )
        wait = backoff.pop(0) if backoff else 5.0
        time.sleep(wait)


class GeminiVideoAnalyzer(BaseTool):
    """Gemini-direct video_analysis provider.

    See module docstring for full behavior contract. Unit-test coverage
    lands in plan 02-04 (18 behaviors mirroring the PLAN.md <behavior> block).
    """

    name = "gemini_video_analyzer"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "video_analysis"
    provider = "gemini"
    stability = ToolStability.BETA
    runtime = ToolRuntime.API
    dependencies = ["env:GEMINI_API_KEY", "python:google.genai"]
    install_instructions = (
        "pip install 'google-genai>=1.73,<2' && "
        "set GEMINI_API_KEY in .env (get one at https://aistudio.google.com/apikey)"
    )
    agent_skills = ["gemini-video-analysis"]
    best_for = [
        "4-dimension structured video analysis via Gemini Files API",
        "videos <=5 min (single-chunk path; Phase 4 adds chunking for longer)",
    ]
    retry_policy = RetryPolicy(max_retries=1, backoff_seconds=0.0)
    resource_profile = ResourceProfile(network_required=True)

    # Flatten canonical schema exactly once at class-load (RESEARCH Example 2).
    # Cached dict — to_api_schema returns a deepcopy, so this is safe to share.
    _FLAT_SCHEMA: dict = to_api_schema(load_schema("video_analysis"))

    input_schema = {
        "type": "object",
        "required": ["video_path"],
        "properties": {
            "video_path": {
                "type": "string",
                "description": (
                    "Path to a local video file. NOT sandboxed — OpenMontage "
                    "is single-tenant and the agent layer is trusted "
                    "(T-02-10 accepted)."
                ),
            },
            "shot_boundaries": {
                "type": "array",
                "description": (
                    "Optional [[start_s, end_s], ...] or "
                    "[{'start_seconds', 'end_seconds'}, ...] from scene_detect."
                ),
                "items": {"type": ["array", "object"]},
            },
            "analysis_depth": {
                "type": "string",
                "enum": ["full", "compact"],
                "default": "full",
            },
            "max_poll_seconds": {
                "type": "number",
                "default": DEFAULT_MAX_POLL_SECONDS,
            },
        },
    }

    # --- get_status: rely on BaseTool's check_dependencies via env:GEMINI_API_KEY ---
    # Default BaseTool.get_status is sufficient (it calls check_dependencies).

    def _build_prompt(self, inputs: dict[str, Any], depth: str) -> str:
        """Build the analysis prompt. `depth` is 'full' or 'compact'.

        Encodes:
          * ANLZ-05 shot_boundary_source directive (when no boundaries given)
          * ANLZ-04 confidence='low' directive for uncertain fields
          * analysis_depth tag so we can assert compact-retry in tests
        """
        shot_pairs = _normalize_shot_boundaries(inputs.get("shot_boundaries"))
        if shot_pairs:
            bounds_line = (
                "Shot boundaries (from scene_detect): "
                f"{_format_shot_boundaries(shot_pairs)}"
            )
        else:
            bounds_line = (
                "Shot boundaries: NOT PROVIDED — infer from the video and set "
                "shot_boundary_source: \"model\" in the artifact."
            )
        # ANLZ-04 explicit directive + ANLZ-05 shot_boundary_source directive.
        # "compact" variant is for the retry path only (GEM-04).
        depth_directive = (
            "Use terse but complete phrasing; keep descriptive fields under "
            "30 words each."
            if depth == "compact"
            else "Be thorough across all 4 dimensions."
        )
        return (
            "Analyze the attached video across 4 dimensions: "
            "editing_pacing, audio, visual_style, narrative. "
            "Return a JSON object matching the provided response_json_schema.\n\n"
            f"{bounds_line}\n\n"
            "For EVERY uncertain or absent field, populate the dimension's "
            "confidence map with the field-name -> \"low\" entry (never omit "
            "a field and never emit null). Use \"medium\" or \"high\" only "
            "when you are genuinely confident in the value.\n\n"
            f"Depth directive: {depth_directive}\n"
            f"(analysis_depth={depth})"
        )

    def _run_once(
        self,
        client: "genai.Client",
        file_ref: "types.File",
        prompt: str,
        model: str,
    ) -> dict:
        """Single structured-output call. Raises VideoAnalysisError on
        truncation / empty / unparseable. Lets errors.ClientError propagate
        to the caller (which handles the model-fallback branch)."""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=self._FLAT_SCHEMA,
        )
        try:
            response = client.models.generate_content(
                model=model,
                contents=[file_ref, prompt],
                config=config,
            )
        except errors.ClientError:
            raise  # let execute() decide whether to fall back to 2.5-pro
        except errors.ServerError as exc:
            raise VideoAnalysisError(f"Gemini server error: {exc}") from exc

        cands = getattr(response, "candidates", None) or []
        if not cands:
            raise VideoAnalysisError("No candidates in response")
        finish_reason = getattr(cands[0], "finish_reason", None)
        if finish_reason == types.FinishReason.MAX_TOKENS:
            raise VideoAnalysisError(
                "Response truncated (finish_reason=MAX_TOKENS)"
            )
        raw = getattr(response, "text", None) or ""
        if not raw.strip():
            raise VideoAnalysisError("Empty response text")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VideoAnalysisError(
                f"Response JSON unparseable: {exc}"
            ) from exc

    def _analyze_with_fallback(
        self,
        client: "genai.Client",
        file_ref: "types.File",
        inputs: dict[str, Any],
    ) -> tuple[dict, str]:
        """Returns (artifact, model_that_ran). Implements the 4-branch ladder:

          1. preview full   -- first try
          2. preview compact -- on VideoAnalysisError (MAX_TOKENS/empty/parse)
          3. 2.5-pro full    -- on errors.ClientError from preview (model unavailable)
          4. 2.5-pro compact -- on VideoAnalysisError from the 2.5-pro full attempt

        A loop would obscure which path maps to which test. The explicit
        branching matches behavior tests 10, 11, 13, and the edge case of
        preview-unavailable-on-retry. See RESEARCH Pitfall 6.
        """
        requested = _resolve_model()
        depth = inputs.get("analysis_depth", "full") or "full"
        prompt = self._build_prompt(inputs, depth=depth)

        # First attempt at the requested (preview) model, full depth.
        try:
            return self._run_once(client, file_ref, prompt, requested), requested
        except errors.ClientError as exc:
            # Preview model not available (4xx) -> fall back to stable 2.5-pro.
            logger.warning(
                "Gemini model %s unavailable (ClientError code=%s); "
                "falling back to %s",
                requested, getattr(exc, "code", "?"), FALLBACK_MODEL,
            )
            model = FALLBACK_MODEL
        except VideoAnalysisError:
            # Truncation / empty / parse error -> retry once with compact depth.
            compact_prompt = self._build_prompt(inputs, depth="compact")
            try:
                return self._run_once(
                    client, file_ref, compact_prompt, requested
                ), requested
            except errors.ClientError:
                # Preview model unavailable on retry path too -> fall through
                # to the fallback model with compact depth.
                try:
                    return self._run_once(
                        client, file_ref, compact_prompt, FALLBACK_MODEL
                    ), FALLBACK_MODEL
                except VideoAnalysisError as exc2:
                    raise VideoAnalysisRetryExhausted(
                        "Analysis failed after compact retry on fallback "
                        f"model: {exc2}"
                    ) from exc2
            except VideoAnalysisError as exc:
                raise VideoAnalysisRetryExhausted(
                    f"Analysis failed after compact retry: {exc}"
                ) from exc

        # Fallback-model branch: try full depth first, then compact retry.
        try:
            return self._run_once(client, file_ref, prompt, model), model
        except VideoAnalysisError:
            compact_prompt = self._build_prompt(inputs, depth="compact")
            try:
                return self._run_once(
                    client, file_ref, compact_prompt, model
                ), model
            except VideoAnalysisError as exc:
                raise VideoAnalysisRetryExhausted(
                    "Analysis failed on fallback model after compact "
                    f"retry: {exc}"
                ) from exc

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        video_path = Path(inputs.get("video_path", ""))
        if not video_path.exists() or not video_path.is_file():
            return ToolResult(
                success=False,
                error=f"Video not found or not a regular file: {video_path}",
            )

        key = _get_api_key()
        if not key:
            # T-02-06: do NOT format the key value into error messages.
            return ToolResult(
                success=False,
                error="GEMINI_API_KEY (or GOOGLE_API_KEY) not set.",
            )

        try:
            client = genai.Client(api_key=key)
        except Exception as exc:  # SDK init error — auth/config level
            # T-02-06: str(exc) from the SDK does not contain the raw key.
            return ToolResult(
                success=False,
                error=f"Gemini client init failed: {exc}",
            )

        max_poll = float(
            inputs.get("max_poll_seconds") or DEFAULT_MAX_POLL_SECONDS
        )

        uploaded = None
        model_used: str | None = None
        try:
            uploaded = client.files.upload(file=str(video_path))
            active = _wait_for_active(
                client, uploaded.name, max_seconds=max_poll
            )
            artifact, model_used = self._analyze_with_fallback(
                client, active, inputs
            )
            # T-02-07: gate on canonical schema BEFORE returning to caller.
            validate_artifact("video_analysis", artifact)
            # NOTE: ToolResult.data IS the canonical artifact — do NOT stamp
            # selector metadata here (ANLZ-06 / Pitfall 7). Selector uses
            # ToolResult.model for that.
            return ToolResult(
                success=True,
                data=artifact,
                model=model_used,
            )
        except (VideoUploadError, VideoAnalysisError) as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                model=model_used,
            )
        except jsonschema.ValidationError as exc:
            return ToolResult(
                success=False,
                error=(
                    "Returned artifact failed schema validation: "
                    f"{exc.message}"
                ),
                model=model_used,
            )
        except errors.APIError as exc:
            return ToolResult(
                success=False,
                error=f"Gemini API error: {exc}",
                model=model_used,
            )
        finally:
            # T-02-09: always delete the uploaded file — success OR failure.
            # Files API auto-delete (48h) is defense-in-depth only.
            if uploaded is not None:
                try:
                    client.files.delete(name=uploaded.name)
                except errors.APIError as exc:
                    logger.warning(
                        "Failed to delete uploaded file %s: %s",
                        uploaded.name, exc,
                    )
