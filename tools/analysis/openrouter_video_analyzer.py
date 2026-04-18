"""Second video_analysis provider — OpenRouter via the openai>=1.0 SDK.

Uses inline base64 encoding (NOT a Files API — OpenRouter + Gemini does not
accept video URLs). Enforces `max_upload_bytes` gate BEFORE encoding to avoid
pointless memory burn. Attempts structured output via response_format=
json_schema with require_parameters=True; falls back to prompt-embedded
schema on BadRequestError. Detects `finish_reason == "length"` (STRING
literal at runtime — NOT an enum; Gemini's MAX_TOKENS pattern does not
apply here). Retries ONCE with analysis_depth="compact" before raising
VideoAnalysisRetryExhausted.

Cost is surfaced from `response.usage.cost` (OpenRouter extra field on the
standard usage body) — NOT from any response header. The header-based
approach referenced in some community code is NOT documented by OpenRouter
(verified RESEARCH Finding 4 / Pitfall 5).

NEVER calls lib.checkpoint.write_checkpoint (Phase 1 WR-05 — checkpoint
requires a pipeline_type this tool cannot know). NEVER stamps selector /
provider metadata on ToolResult.data (ANLZ-06 / Pitfall 7 — caller owns
that). ToolResult.model carries the model that ran; that is the entire
provenance surface the tool exposes.

Implements:
  * OR-01 — BaseTool shape, capability/provider/runtime, explicit api_key
  * OR-02 — openai>=1.0 SDK pointed at OpenRouter base_url
  * OR-03 — inline base64 data URL; max_upload_bytes gate; MIME whitelist
  * OR-04 — response_format=json_schema + extra_body require_parameters;
            prompt-embedded fallback on BadRequestError
  * OR-05 — finish_reason=="length" detection + one compact retry
  * ANLZ-06 — result.data is the canonical artifact only (no selector metadata)
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

import jsonschema
from openai import (
    APIError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from lib.analysis_errors import (
    VideoAnalysisAuthError,
    VideoAnalysisError,
    VideoAnalysisRateLimitError,
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

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-3.1-pro-preview"
FALLBACK_MODEL = "google/gemini-2.5-pro"
DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024           # 20 MB (RESEARCH Assumption A1)
HARD_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024        # 2 GB defensive cap
MIN_MAX_UPLOAD_BYTES = 1
SUPPORTED_MIMES = frozenset({
    "video/mp4",
    "video/quicktime",    # .mov
    "video/webm",
    "video/mpeg",
})


def _get_api_key() -> str | None:
    """Return OPENROUTER_API_KEY (no fallback — explicit per CONTEXT).

    DO NOT rely on OpenAI SDK default: the SDK reads OPENAI_API_KEY, which
    would be the wrong credential for OpenRouter (Pitfall 1).
    """
    return os.environ.get("OPENROUTER_API_KEY")


def _resolve_model() -> str:
    """Return the OpenRouter model slug — env override or default."""
    return os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL


def _clamp_max_upload(raw: Any) -> int:
    """Clamp max_upload_bytes input to [1, HARD_MAX_UPLOAD_BYTES].

    Mirrors Phase 2 MD-04 pattern. Any non-int input returns the default.
    """
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_UPLOAD_BYTES
    return max(MIN_MAX_UPLOAD_BYTES, min(v, HARD_MAX_UPLOAD_BYTES))


def _guess_mime(path: Path) -> str:
    """Best-effort MIME guess from extension; defaults to video/mp4."""
    guessed = mimetypes.guess_type(path.name)[0]
    return guessed or "video/mp4"


def _normalize_shot_boundaries(boundaries: Any) -> list[tuple[float, float]]:
    """Accept list of [start, end] OR list of {'start_seconds','end_seconds'}
    dicts (scene_detect output) and normalize to [(start, end), ...].

    Empty / None / malformed entries are silently dropped — the prompt just
    won't include that boundary. Format errors do NOT raise; they produce
    an empty list, which triggers shot_boundary_source='model' downstream.

    Intentionally duplicated from Phase 2's gemini tool (not shared) per
    CONTEXT discretion note — extract to lib/ only when a third provider
    materializes.
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
    """Render '0.0-3.4s, 3.4-6.8s, ...' for prompt embedding."""
    return ", ".join(f"{s:.1f}-{e:.1f}s" for s, e in pairs)


def _build_data_url(video_path: Path, mime: str) -> str:
    """Full-buffer base64 encode (safe because size gate runs BEFORE this).

    For <= 20 MB defaults this peaks at ~50 MB RAM (raw + b64 string) — well
    within any reasonable host budget. Streaming base64 would add complexity
    for no real benefit at this tier.
    """
    b64 = base64.b64encode(video_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


class OpenRouterVideoAnalyzer(BaseTool):
    """BaseTool exposing video_analysis via OpenRouter's OpenAI-compatible API.

    See module docstring for the full behavior contract. Unit-test coverage
    (22 behaviors) lands in plan 03-03 — this class is shaped so every test
    can be implemented without code changes.
    """

    name = "openrouter_video_analyzer"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "video_analysis"
    provider = "openrouter"
    stability = ToolStability.BETA
    runtime = ToolRuntime.API
    dependencies = ["env:OPENROUTER_API_KEY", "python:openai"]
    install_instructions = (
        "pip install 'openai>=1.0,<3' && "
        "set OPENROUTER_API_KEY in .env (get one at https://openrouter.ai/settings/keys)"
    )
    agent_skills = ["openrouter-video-analysis"]
    best_for = [
        "4-dimension structured video analysis via OpenRouter (inline base64)",
        "videos <=20 MB (default) — chunking comes in Phase 4",
        "model portability: OPENROUTER_MODEL env swaps the underlying provider",
    ]
    retry_policy = RetryPolicy(max_retries=1, backoff_seconds=0.0)
    resource_profile = ResourceProfile(network_required=True)

    # Lazy cache (MD-01 pattern). DO NOT compute at class-body load.
    _FLAT_SCHEMA: dict | None = None

    @classmethod
    def _flat_schema(cls) -> dict:
        if cls._FLAT_SCHEMA is None:
            cls._FLAT_SCHEMA = to_api_schema(load_schema("video_analysis"))
        return cls._FLAT_SCHEMA

    input_schema = {
        "type": "object",
        "required": ["video_path"],
        "properties": {
            "video_path": {
                "type": "string",
                "description": (
                    "Path to a local video file (mp4, mov, webm, mpeg). "
                    "NOT sandboxed — OpenMontage is single-tenant and the "
                    "agent layer is trusted (T-03-12 accepted)."
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
            "max_upload_bytes": {
                "type": "integer",
                "description": (
                    "Max inline-base64 size; clamped to "
                    f"[1,{HARD_MAX_UPLOAD_BYTES}] (2GB)."
                ),
                "default": DEFAULT_MAX_UPLOAD_BYTES,
            },
        },
    }

    # ------------------------------------------------------------------
    # Prompt / message construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        inputs: dict[str, Any],
        depth: str,
        include_schema_in_prompt: bool = False,
    ) -> str:
        """Build the analysis prompt. `depth` is 'full' or 'compact'.

        Encodes:
          * ANLZ-05 shot_boundary_source directive (when no boundaries given)
          * ANLZ-04 confidence='low' directive for uncertain fields
          * analysis_depth tag so tests can assert compact-retry directive
          * Optional schema embed for the prompt-embedded fallback path
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
        depth_directive = (
            "Use terse but complete phrasing; keep descriptive fields under "
            "30 words each."
            if depth == "compact"
            else "Be thorough across all 4 dimensions."
        )
        base = (
            "Analyze the attached video across 4 dimensions: "
            "editing_pacing, audio, visual_style, narrative. "
            "Return a JSON object matching the required schema.\n\n"
            f"{bounds_line}\n\n"
            "For EVERY uncertain or absent field, populate the dimension's "
            "confidence map with the field-name -> \"low\" entry (never omit "
            "a required field, never emit null). Use \"medium\" or \"high\" "
            "only when you are genuinely confident in the value.\n\n"
            f"Depth directive: {depth_directive}\n"
            f"(analysis_depth={depth})"
        )
        if include_schema_in_prompt:
            # Fallback path: the routed model does not accept
            # response_format=json_schema. Embed the flat schema literally
            # so the model still has the shape contract.
            schema_block = json.dumps(self._flat_schema(), indent=2)
            base = (
                base
                + "\n\nYour response MUST validate against this json_schema "
                "(return ONLY the JSON object, no prose, no markdown fences):"
                "\n```json\n"
                + schema_block
                + "\n```"
            )
        return base

    def _build_messages(self, prompt: str, data_url: str) -> list[dict]:
        """Raw-dict messages (Pitfall 3: video_url is NOT in SDK TypedDict).

        At runtime openai SDK serializes dicts to JSON without TypedDict
        validation. A typed construction would add no runtime safety and
        cost a `# type: ignore` at static-check time.
        """
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "video_url", "video_url": {"url": data_url}},
                ],
            }
        ]

    def _response_format(self) -> dict:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "video_analysis",
                "schema": self._flat_schema(),
                "strict": True,
            },
        }

    # ------------------------------------------------------------------
    # Single-attempt + fallback ladder
    # ------------------------------------------------------------------

    def _run_once(
        self,
        client: "OpenAI",
        data_url: str,
        prompt: str,
        model: str,
        structured: bool,
    ) -> tuple[dict, str, float]:
        """One call. Returns (artifact, resp.model, cost_usd).

        Raises BadRequestError upward ONLY when structured=True (so caller
        can fall back to prompt-embedded). Raises VideoAnalysisError on
        truncation / empty / unparseable / other 4xx.
        """
        messages = self._build_messages(prompt, data_url)
        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if structured:
            kwargs["response_format"] = self._response_format()
            # Force providers that actually HONOR response_format (Pitfall 4).
            # Deliberately OMITTED on the fallback path so we don't over-
            # constrain routing when we've already conceded structured output.
            kwargs["extra_body"] = {"provider": {"require_parameters": True}}

        try:
            resp = client.chat.completions.create(**kwargs)
        except BadRequestError:
            if structured:
                raise  # let _analyze_with_fallback handle it
            raise VideoAnalysisError(
                "OpenRouter BadRequestError on prompt-embedded fallback path"
            )
        except AuthenticationError as exc:
            # HI-01 / CLEAN-01: 401 must fast-fail; the compact ladder cannot
            # fix a bad key and would waste a paid API call. Sentinel bypasses
            # _analyze_with_fallback via isinstance guard below.
            raise VideoAnalysisAuthError(
                f"OpenRouter authentication failed: {exc!s}"
            ) from exc
        except PermissionDeniedError as exc:
            # HI-01 / CLEAN-01: 403 = model access / quota denied — same
            # reasoning as 401.
            raise VideoAnalysisAuthError(
                f"OpenRouter permission denied: {exc!s}"
            ) from exc
        except RateLimitError as exc:
            # HI-01 / CLEAN-01: 429 — SDK's own max_retries already handled
            # transient cases; retrying here would only compound the
            # rate-limit.
            raise VideoAnalysisRateLimitError(
                f"OpenRouter rate-limited: {exc!s}"
            ) from exc
        except APIError as exc:
            # AuthenticationError / PermissionDeniedError / RateLimitError
            # already handled above. This branch now catches APITimeoutError
            # and any other APIError subclass not explicitly enumerated — keep
            # wrapping as a retry-eligible VideoAnalysisError (status quo).
            # T-03-06: str(exc) from the SDK does not contain the raw key.
            raise VideoAnalysisError(f"OpenRouter API error: {exc!s}") from exc

        choices = getattr(resp, "choices", None) or []
        if not choices:
            raise VideoAnalysisError("No choices in response")
        finish_reason = getattr(choices[0], "finish_reason", None)
        # STRING equality — finish_reason is a Literal[str] at runtime
        # (Pitfall 2 — NOT an enum; that's Gemini's pattern).
        if finish_reason == "length":
            raise VideoAnalysisError(
                'Response truncated (finish_reason="length")'
            )
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None) or ""
        if not content.strip():
            raise VideoAnalysisError("Empty response content")
        try:
            artifact = json.loads(content)
        except json.JSONDecodeError as exc:
            raise VideoAnalysisError(
                f"Response JSON unparseable: {exc}"
            ) from exc

        resp_model = getattr(resp, "model", None) or model
        usage = getattr(resp, "usage", None)
        cost_usd = 0.0
        if usage is not None:
            # OpenRouter adds `cost` as an extra field; standard
            # CompletionUsage permits extras. getattr for defensive safety
            # across SDK versions and for mocks that omit usage.
            try:
                cost_usd = float(getattr(usage, "cost", 0.0) or 0.0)
            except (TypeError, ValueError):
                cost_usd = 0.0
        return artifact, resp_model, cost_usd

    def _analyze_with_fallback(
        self,
        client: "OpenAI",
        data_url: str,
        inputs: dict[str, Any],
    ) -> tuple[dict, str, float]:
        """Four-branch ladder (maps 1:1 to plan 03-03 tests 9, 11, 13, 15):

            structured + full  -> truncated -> structured + compact
                          |                           |
                          |                           `- truncated ->
                          |                              VideoAnalysisRetryExhausted
                          |
                          `- BadRequest -> prompt-embedded + full ->
                                           truncated ->
                                           prompt-embedded + compact ->
                                           truncated ->
                                           VideoAnalysisRetryExhausted

        A loop here would obscure which path maps to which test. The
        explicit branching matches RESEARCH Pattern 3 + Open Question 1:
        `require_parameters` is set ONLY on the structured branch; the
        prompt-embedded fallback deliberately omits it to avoid over-
        constraining routing when we've already conceded structured output.
        """
        model = _resolve_model()
        prompt_full = self._build_prompt(
            inputs, depth="full", include_schema_in_prompt=False
        )

        # Attempt 1: structured + full
        try:
            return self._run_once(
                client, data_url, prompt_full, model, structured=True
            )
        except BadRequestError as exc:
            # Model / route does not support response_format=json_schema.
            # Log exc.code so operators can see real 4xx patterns rather
            # than silently re-tagging AuthenticationError as "unsupported".
            logger.info(
                "Model %s rejected response_format=json_schema (code=%s); "
                "falling back to prompt-embedded schema path.",
                model, getattr(exc, "code", "?"),
            )
        except VideoAnalysisError as exc:
            if isinstance(exc, (VideoAnalysisAuthError, VideoAnalysisRateLimitError)):
                raise  # HI-01 — fast-fail bypasses compact retry
            # Truncation / empty / parse error -> structured + compact retry
            prompt_compact = self._build_prompt(
                inputs, depth="compact", include_schema_in_prompt=False
            )
            try:
                return self._run_once(
                    client, data_url, prompt_compact, model, structured=True
                )
            except BadRequestError as exc:
                logger.info(
                    "Model %s rejected response_format on compact retry "
                    "(code=%s); falling through to prompt-embedded path.",
                    model, getattr(exc, "code", "?"),
                )
            except VideoAnalysisError as exc:
                if isinstance(exc, (VideoAnalysisAuthError, VideoAnalysisRateLimitError)):
                    raise  # HI-01 — fast-fail bypasses compact retry
                raise VideoAnalysisRetryExhausted(
                    f"Analysis failed after structured+compact retry: {exc}"
                ) from exc

        # Fallback ladder: prompt-embedded schema, NO extra_body (per
        # RESEARCH Open Question 1 — don't over-constrain the fallback).
        prompt_embedded_full = self._build_prompt(
            inputs, depth="full", include_schema_in_prompt=True
        )
        try:
            return self._run_once(
                client, data_url, prompt_embedded_full, model, structured=False
            )
        except VideoAnalysisError as exc:
            if isinstance(exc, (VideoAnalysisAuthError, VideoAnalysisRateLimitError)):
                raise  # HI-01 — fast-fail bypasses compact retry
            prompt_embedded_compact = self._build_prompt(
                inputs, depth="compact", include_schema_in_prompt=True
            )
            try:
                return self._run_once(
                    client,
                    data_url,
                    prompt_embedded_compact,
                    model,
                    structured=False,
                )
            except VideoAnalysisError as exc:
                if isinstance(exc, (VideoAnalysisAuthError, VideoAnalysisRateLimitError)):
                    raise  # HI-01 — fast-fail bypasses compact retry
                raise VideoAnalysisRetryExhausted(
                    "Analysis failed after prompt-embedded+compact retry: "
                    f"{exc}"
                ) from exc

    # ------------------------------------------------------------------
    # execute()
    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        video_path = Path(inputs.get("video_path") or "")
        if not video_path.exists() or not video_path.is_file():
            return ToolResult(
                success=False,
                error=f"Video not found or not a regular file: {video_path}",
            )

        key = _get_api_key()
        if not key:
            # T-03-06: never format the key value into errors or logs.
            return ToolResult(
                success=False,
                error="OPENROUTER_API_KEY not set.",
            )

        # MD-04 pattern: clamp size input.
        max_upload = _clamp_max_upload(inputs.get("max_upload_bytes"))
        try:
            size = video_path.stat().st_size
        except OSError as exc:
            return ToolResult(
                success=False, error=f"Cannot stat video: {exc}"
            )
        if size > max_upload:
            # T-03-08: reject BEFORE encoding; no memory burn, no API call.
            return ToolResult(
                success=False,
                error=(
                    f"video exceeds max_upload_bytes ({size} > {max_upload}); "
                    "chunking lands in Phase 4"
                ),
            )

        mime = _guess_mime(video_path)
        if mime not in SUPPORTED_MIMES:
            return ToolResult(
                success=False,
                error=(
                    f"Unsupported video MIME: {mime} "
                    f"(supported: {sorted(SUPPORTED_MIMES)})"
                ),
            )

        # Size + MIME gates passed -> encode.
        try:
            data_url = _build_data_url(video_path, mime)
        except OSError as exc:
            return ToolResult(
                success=False, error=f"Cannot read video bytes: {exc}"
            )

        # Client init — narrow except on openai.APIError (MD-03 pattern).
        # T-03-06: str(exc) from the SDK does not contain the raw key.
        # Single-line constructor so grep guards match the source literally.
        default_headers = {
            "HTTP-Referer": "https://github.com/openmontage",
            "X-Title": "OpenMontage",
        }
        try:
            client = OpenAI(api_key=key, base_url="https://openrouter.ai/api/v1", default_headers=default_headers)
        except APIError as exc:
            return ToolResult(
                success=False,
                error=f"OpenRouter client init failed: {exc}",
            )

        try:
            artifact, resp_model, cost_usd = self._analyze_with_fallback(
                client, data_url, inputs
            )
            # T-03-07: gate on canonical schema BEFORE returning to caller.
            validate_artifact("video_analysis", artifact)
        except VideoUploadError as exc:
            return ToolResult(success=False, error=str(exc))
        except (VideoAnalysisAuthError, VideoAnalysisRateLimitError) as exc:
            # HI-01 fast-fail: surface verbatim. (_analyze_with_fallback already
            # re-raised via isinstance guard; this branch ensures execute() does
            # not accidentally absorb the sentinel into the generic handler.)
            return ToolResult(success=False, error=str(exc))
        except (VideoAnalysisError, VideoAnalysisRetryExhausted) as exc:
            return ToolResult(success=False, error=str(exc))
        except jsonschema.ValidationError as exc:
            return ToolResult(
                success=False,
                error=(
                    "Returned artifact failed schema validation: "
                    f"{exc.message}"
                ),
            )
        except APIError as exc:
            # Defensive catch — _run_once re-wraps APIError as
            # VideoAnalysisError, but surfacing a bare APIError here
            # (e.g., a future SDK path) still never leaks the key.
            return ToolResult(
                success=False, error=f"OpenRouter API error: {exc}"
            )

        # ANLZ-06 / Pitfall 7: result.data IS the canonical artifact ONLY.
        # Provider metadata lives on ToolResult.model; cost on cost_usd.
        return ToolResult(
            success=True,
            data=artifact,
            model=resp_model,
            cost_usd=cost_usd,
        )
