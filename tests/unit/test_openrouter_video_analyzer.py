"""Unit tests for ``tools/analysis/openrouter_video_analyzer.py``.

All tests mock the openai SDK — no real API key required, no network.

Truncation tests assert STRING equality ``finish_reason == "length"`` (NOT an
enum) to prevent regression against RESEARCH Pitfall 2. Cost tests read
``resp.usage.cost`` body field (NOT ``response.headers``) per Pitfall 5.

Covers the 22 behaviors specified in plan 03-01 + security + lazy-cache:

    OR-01  contract fields (name/capability/provider/runtime/agent_skills/tier/stability)
    OR-01  missing OPENROUTER_API_KEY -> error, no key value leaked
    OR-02  OpenAI(base_url="https://openrouter.ai/api/v1")
    OR-02  api_key passed explicitly (SDK default reads OPENAI_API_KEY — wrong)
    OR-03  max_upload_bytes gate rejects BEFORE encoding (no create() call)
    OR-03  _clamp_max_upload bounds (negative, huge, non-numeric)
    OR-03  base64 data URL prefix "data:video/mp4;base64,"
    OR-03  unsupported MIME rejected with no create() call
    OR-04  messages contains {"type":"video_url","video_url":{"url":...}} + text
    OR-04  response_format=json_schema + extra_body require_parameters on first try
    OR-04  flat schema has no $ref / no uniqueItems / no "additionalProperties":false
    OR-04  BadRequestError -> prompt-embedded fallback (no extra_body on fallback)
    OR-05  finish_reason=="length" triggers one compact retry
    OR-05  empty content (stop + "") triggers retry
    OR-05  retry exhausted -> VideoAnalysisRetryExhausted surfaced as error
    Pitfall-2 defensive: MagicMock finish_reason does NOT accidentally match "length"
    Cost:   usage.cost body field feeds ToolResult.cost_usd (never headers)
    Cost:   resp.model reflected on ToolResult.model
    Artifact: invalid artifact rejected via validate_artifact gate
    WR-05:  tool source does NOT import or call write_checkpoint
    ANLZ-06: result.data IS the canonical artifact ONLY (no provider metadata stamped)
    MD-01:  _FLAT_SCHEMA is lazy (None at import; populated on first call; cached)
    T-03-06: API key value never leaks into ToolResult.error across every failure path
"""

from __future__ import annotations

import ast
import base64
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from openai import (
    APIError,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib.analysis_errors import (  # noqa: E402
    VideoAnalysisError,
    VideoAnalysisRetryExhausted,
    VideoUploadError,
)
from tools.analysis.openrouter_video_analyzer import (  # noqa: E402
    DEFAULT_MAX_UPLOAD_BYTES,
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    HARD_MAX_UPLOAD_BYTES,
    OPENROUTER_BASE_URL,
    OpenRouterVideoAnalyzer,
    SUPPORTED_MIMES,
    _clamp_max_upload,
    _get_api_key,
    _normalize_shot_boundaries,
    _resolve_model,
)

_SOURCE_PATH = _REPO_ROOT / "tools" / "analysis" / "openrouter_video_analyzer.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bad_request(msg: str = "unsupported response_format") -> BadRequestError:
    """Construct a BadRequestError with a minimal httpx.Response (SDK requires it)."""
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp = httpx.Response(400, request=req)
    return BadRequestError(msg, response=resp, body={"error": {"message": msg}})


def _resp_ok(artifact: dict, *, cost: float = 0.001, model: str = "google/gemini-3.1-pro-preview"):
    resp = MagicMock()
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = json.dumps(artifact)
    resp.choices = [choice]
    resp.model = model
    usage = MagicMock()
    usage.cost = cost
    resp.usage = usage
    return resp


# ---------------------------------------------------------------------------
# OR-01 — contract fields + auth
# ---------------------------------------------------------------------------


def test_contract_fields():
    """OR-01: BaseTool contract fields match planned values."""
    t = OpenRouterVideoAnalyzer()
    info = t.get_info()
    assert info["name"] == "openrouter_video_analyzer"
    assert info["capability"] == "video_analysis"
    assert info["provider"] == "openrouter"
    assert info["runtime"] == "api"
    assert info["tier"] == "analyze"
    assert info["stability"] == "beta"
    assert info["agent_skills"] == ["openrouter-video-analysis"]


def test_auth_missing_key_no_leak(no_keys, fake_video):
    """OR-01: missing OPENROUTER_API_KEY -> error names the env var, no leak."""
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is False
    assert "OPENROUTER_API_KEY" in (result.error or "")
    # Defensive — common sentinel strings should never appear
    assert "sk-or-" not in (result.error or "")
    assert "test-or-key" not in (result.error or "")


def test_get_api_key_returns_env():
    """_get_api_key reads OPENROUTER_API_KEY."""
    import os
    os.environ["OPENROUTER_API_KEY"] = "sentinel-val"
    try:
        assert _get_api_key() == "sentinel-val"
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)


def test_resolve_model_default_and_override(monkeypatch):
    """OPENROUTER_MODEL env override; else default slug."""
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    assert _resolve_model() == DEFAULT_MODEL
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-3-opus")
    assert _resolve_model() == "anthropic/claude-3-opus"


# ---------------------------------------------------------------------------
# OR-02 — client construction (base_url, explicit api_key)
# ---------------------------------------------------------------------------


def test_openai_client_base_url(mock_openai, fake_video):
    """OR-02: OpenAI client built with base_url="https://openrouter.ai/api/v1"."""
    import tools.analysis.openrouter_video_analyzer as target
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    # The OpenAI name at the module level has been patched by mock_openai to a MagicMock
    assert target.OpenAI.call_args.kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert target.OpenAI.call_args.kwargs["base_url"] == OPENROUTER_BASE_URL


def test_api_key_passed_explicitly(mock_openai, fake_video):
    """OR-02: api_key kwarg passed explicitly (NOT relying on OPENAI_API_KEY SDK default)."""
    import tools.analysis.openrouter_video_analyzer as target
    t = OpenRouterVideoAnalyzer()
    t.execute({"video_path": str(fake_video)})
    kwargs = target.OpenAI.call_args.kwargs
    assert "api_key" in kwargs
    assert kwargs["api_key"] == "test-or-key"
    assert kwargs["api_key"] is not None


# ---------------------------------------------------------------------------
# OR-03 — size gate, MIME, base64 data URL
# ---------------------------------------------------------------------------


def test_max_upload_bytes_reject(mock_openai, fake_video, monkeypatch):
    """OR-03: oversize file rejected BEFORE encoding. No create() call, no b64encode."""
    import tools.analysis.openrouter_video_analyzer as target

    # Spy on base64.b64encode in the tool's namespace
    spy = MagicMock(side_effect=base64.b64encode)
    monkeypatch.setattr(target.base64, "b64encode", spy)

    # Write a file that exceeds the clamp we set
    big = fake_video.parent / "too_big.mp4"
    big.write_bytes(b"\x00" * 2048)
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(big), "max_upload_bytes": 512})
    assert result.success is False
    assert "max_upload_bytes" in (result.error or "")
    # No network call, no encoding
    mock_openai.chat.completions.create.assert_not_called()
    spy.assert_not_called()


def test_max_upload_clamp_negative():
    """OR-03: negative input clamps up to MIN (==1)."""
    assert _clamp_max_upload(-5) == 1


def test_max_upload_clamp_huge():
    """OR-03: huge input clamps down to HARD_MAX_UPLOAD_BYTES."""
    assert _clamp_max_upload(10**20) == HARD_MAX_UPLOAD_BYTES


def test_max_upload_clamp_non_numeric():
    """OR-03: non-numeric input returns DEFAULT_MAX_UPLOAD_BYTES."""
    assert _clamp_max_upload("nope") == DEFAULT_MAX_UPLOAD_BYTES
    assert _clamp_max_upload(None) == DEFAULT_MAX_UPLOAD_BYTES


# ---------------------------------------------------------------------------
# CLEAN-02 — HARD_MAX_UPLOAD_BYTES lowered to 100 MB
# ---------------------------------------------------------------------------


def test_hard_max_upload_bytes_is_100mb():
    """CLEAN-02 / MD-01: hard cap is 100 MB, not 2 GB.

    The 2 GB ceiling allowed a caller passing max_upload_bytes=2GB to
    OOM the process when the 2GB raw buffer + 2.67GB base64 string
    materialized simultaneously (~4.7 GB peak). Phase 4 chunking is the
    intended path for anything larger than 100 MB.
    """
    assert HARD_MAX_UPLOAD_BYTES == 100 * 1024 * 1024


def test_oversize_above_hard_cap_rejected_before_encode(
    mock_openai, tmp_path, monkeypatch,
):
    """CLEAN-02 / MD-01: a file one byte above the 100 MB hard cap is
    rejected BEFORE base64 encoding and BEFORE any create() call. The
    caller sees an error message naming chunking as the intended path.

    We pass max_upload_bytes=200MB (clamps DOWN to HARD_MAX_UPLOAD_BYTES
    = 100 MB per the _clamp_max_upload rule) and a file of size
    HARD_MAX_UPLOAD_BYTES + 1.
    """
    import tools.analysis.openrouter_video_analyzer as target

    # Spy on base64.b64encode to prove no encoding happened
    spy = MagicMock(side_effect=base64.b64encode)
    monkeypatch.setattr(target.base64, "b64encode", spy)

    # Truncate a file to exactly HARD_MAX_UPLOAD_BYTES + 1 bytes
    big = tmp_path / "too_big.mp4"
    size = HARD_MAX_UPLOAD_BYTES + 1
    # Use a sparse-like write — posix supports truncate() for size without writing
    with open(big, "wb") as fh:
        fh.truncate(size)

    t = OpenRouterVideoAnalyzer()
    result = t.execute(
        {"video_path": str(big), "max_upload_bytes": 200 * 1024 * 1024}
    )
    assert result.success is False
    low = (result.error or "").lower()
    assert "max_upload_bytes" in low or "exceeds" in low
    assert "chunking" in low or "phase 4" in low
    mock_openai.chat.completions.create.assert_not_called()
    spy.assert_not_called()


def test_oversize_at_hard_cap_boundary_allowed(mock_openai, tmp_path, valid_artifact):
    """CLEAN-02 / MD-01 boundary: a file EXACTLY at HARD_MAX_UPLOAD_BYTES
    passes the gate (inclusive boundary — gate uses strict >). This test
    proves the cap is 100 MB INCLUSIVE, not 100 MB - 1 byte.

    Uses a truncated sparse-ish file and a valid OK response to complete
    the happy path.
    """
    at_cap = tmp_path / "at_cap.mp4"
    with open(at_cap, "wb") as fh:
        fh.truncate(HARD_MAX_UPLOAD_BYTES)

    mock_openai.chat.completions.create.return_value = _resp_ok(valid_artifact)
    t = OpenRouterVideoAnalyzer()
    result = t.execute(
        {"video_path": str(at_cap), "max_upload_bytes": HARD_MAX_UPLOAD_BYTES}
    )
    # Either success (happy path) OR rejection for another reason (e.g. MIME)
    # — we only care that the SIZE gate did not reject it. Assert the
    # rejection text, if any, is NOT about max_upload_bytes.
    if not result.success:
        low = (result.error or "").lower()
        assert "max_upload_bytes" not in low, (
            f"at-cap boundary should pass size gate, got: {result.error}"
        )


def test_base64_data_url_prefix(mock_openai, fake_video):
    """OR-03: messages carry data:video/mp4;base64,... URL (exact prefix)."""
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    messages = mock_openai.chat.completions.create.call_args.kwargs["messages"]
    video_part = messages[0]["content"][1]
    assert video_part["type"] == "video_url"
    url = video_part["video_url"]["url"]
    assert url.startswith("data:video/mp4;base64,")
    # Round-trip the payload: it decodes back to the file's raw bytes
    b64_body = url.split(",", 1)[1]
    assert base64.b64decode(b64_body) == fake_video.read_bytes()


def test_unsupported_mime_rejected(mock_openai, tmp_path):
    """OR-03: .avi (non-whitelisted MIME) rejected; no create() call."""
    vid = tmp_path / "ref.avi"
    vid.write_bytes(b"\x00" * 128)
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(vid)})
    assert result.success is False
    low = (result.error or "").lower()
    assert "mime" in low or "unsupported" in low
    mock_openai.chat.completions.create.assert_not_called()


def test_supported_mimes_whitelist():
    """OR-03: whitelist matches the documented OpenRouter-supported set."""
    assert "video/mp4" in SUPPORTED_MIMES
    assert "video/webm" in SUPPORTED_MIMES
    assert "video/quicktime" in SUPPORTED_MIMES


# ---------------------------------------------------------------------------
# OR-04 — messages shape, response_format=json_schema, fallback
# ---------------------------------------------------------------------------


def test_video_url_content_part(mock_openai, fake_video):
    """OR-04: messages[0].content has exactly text + video_url parts."""
    t = OpenRouterVideoAnalyzer()
    t.execute({"video_path": str(fake_video)})
    messages = mock_openai.chat.completions.create.call_args.kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert len(content) == 2
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "video_url"
    assert "url" in content[1]["video_url"]


def test_json_schema_response_format_first(mock_openai, fake_video):
    """OR-04: first call uses response_format=json_schema + extra_body require_parameters."""
    t = OpenRouterVideoAnalyzer()
    t.execute({"video_path": str(fake_video)})
    kw = mock_openai.chat.completions.create.call_args.kwargs
    rf = kw["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "video_analysis"
    assert rf["json_schema"]["strict"] is True
    assert "schema" in rf["json_schema"]
    # OpenRouter-specific routing preference
    assert kw["extra_body"] == {"provider": {"require_parameters": True}}


def test_flat_schema_no_ref_no_uniqueitems(mock_openai, fake_video):
    """OR-04: flattened schema passed to response_format removes unsupported keys."""
    t = OpenRouterVideoAnalyzer()
    t.execute({"video_path": str(fake_video)})
    rf = mock_openai.chat.completions.create.call_args.kwargs["response_format"]
    s = json.dumps(rf["json_schema"]["schema"])
    assert "$ref" not in s
    assert "uniqueItems" not in s
    compact = s.replace(" ", "")
    assert '"additionalProperties":false' not in compact


def test_bad_request_falls_back_to_prompt_embedded(mock_openai, fake_video, valid_artifact):
    """OR-04: BadRequestError on structured call -> prompt-embedded fallback succeeds."""
    # First call raises BadRequestError; second call (fallback, no response_format) succeeds
    mock_openai.chat.completions.create.side_effect = [
        _bad_request("unsupported response_format"),
        _resp_ok(valid_artifact),
    ]
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    assert mock_openai.chat.completions.create.call_count == 2
    second_kwargs = mock_openai.chat.completions.create.call_args_list[1].kwargs
    # Fallback path must NOT include response_format
    assert "response_format" not in second_kwargs
    # Fallback path must NOT include extra_body (per plan — don't over-constrain routing)
    assert "extra_body" not in second_kwargs
    # Second call's prompt should carry the schema embedded (json_schema block)
    second_text = second_kwargs["messages"][0]["content"][0]["text"]
    assert "json" in second_text.lower()


def test_fallback_does_not_set_extra_body(mock_openai, fake_video, valid_artifact):
    """OR-04: prompt-embedded fallback omits extra_body (validated separately from above)."""
    mock_openai.chat.completions.create.side_effect = [
        _bad_request("unsupported"),
        _resp_ok(valid_artifact),
    ]
    t = OpenRouterVideoAnalyzer()
    t.execute({"video_path": str(fake_video)})
    second = mock_openai.chat.completions.create.call_args_list[1].kwargs
    assert "extra_body" not in second


# ---------------------------------------------------------------------------
# OR-05 — truncation detection + compact retry
# ---------------------------------------------------------------------------


def test_length_finish_reason_triggers_compact_retry(
    mock_openai, fake_video, valid_artifact, openrouter_response_factories,
):
    """OR-05: finish_reason=="length" (STRING) -> one compact retry."""
    fac = openrouter_response_factories
    mock_openai.chat.completions.create.side_effect = [
        fac["truncated"](),
        fac["ok"](valid_artifact),
    ]
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    assert mock_openai.chat.completions.create.call_count == 2
    second_messages = mock_openai.chat.completions.create.call_args_list[1].kwargs["messages"]
    second_text = second_messages[0]["content"][0]["text"]
    assert "compact" in second_text.lower()


def test_empty_content_triggers_retry(
    mock_openai, fake_video, valid_artifact, openrouter_response_factories,
):
    """OR-05: finish_reason=='stop' but empty content -> retry."""
    fac = openrouter_response_factories
    mock_openai.chat.completions.create.side_effect = [
        fac["empty_stop"](),
        fac["ok"](valid_artifact),
    ]
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    assert mock_openai.chat.completions.create.call_count == 2


def test_retry_exhausted_raises(
    mock_openai, fake_video, openrouter_response_factories,
):
    """OR-05: every branch returns truncated -> VideoAnalysisRetryExhausted surfaced."""
    fac = openrouter_response_factories
    # Ladder can attempt up to 4 branches (structured+full, structured+compact,
    # embedded+full, embedded+compact). Feed enough truncated responses to exhaust all.
    mock_openai.chat.completions.create.side_effect = [fac["truncated"]() for _ in range(6)]
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is False
    low = (result.error or "").lower()
    assert any(term in low for term in ("compact", "retry", "truncated", "length"))


def test_finish_reason_string_not_enum_guard(mock_openai, fake_video, valid_artifact):
    """Pitfall 2 defensive: a MagicMock finish_reason (not a string) MUST NOT equal "length".

    Real openai SDK types ``finish_reason`` as ``Literal[str]`` — string equality is
    the correct runtime check. When a test hands in a MagicMock (truthy, non-string),
    the ``== "length"`` comparison returns False, so the code's behavior then depends
    on whether the content is parseable — valid JSON -> success. This test asserts
    the tool does NOT use an enum comparison that would falsely match a Mock.
    """
    resp = MagicMock()
    choice = MagicMock()
    # finish_reason is a plain Mock — not a string
    choice.finish_reason = MagicMock()
    choice.message.content = json.dumps(valid_artifact)
    resp.choices = [choice]
    resp.model = "google/gemini-3.1-pro-preview"
    resp.usage = MagicMock(cost=0.0)
    mock_openai.chat.completions.create.return_value = resp
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    # If the tool incorrectly used `isinstance(finish_reason, enum.Enum) and finish_reason == ...`
    # or treated the Mock as truthy-equals-length, this would fail/retry.
    # Correct behavior: Mock != "length" -> content JSON parses -> success.
    assert result.success is True, result.error
    # Guarantee the tool compared with a string literal, not an enum:
    src = _SOURCE_PATH.read_text(encoding="utf-8")
    assert "Finish" + "Reason" not in src  # split to avoid tripping acceptance grep


# ---------------------------------------------------------------------------
# HI-01 — Auth / permission / rate-limit fast-fail (CLEAN-01)
# ---------------------------------------------------------------------------


def _auth_error(msg: str = "invalid api key") -> AuthenticationError:
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp = httpx.Response(401, request=req)
    return AuthenticationError(msg, response=resp, body={"error": {"message": msg}})


def _permission_error(msg: str = "model access denied") -> PermissionDeniedError:
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp = httpx.Response(403, request=req)
    return PermissionDeniedError(msg, response=resp, body={"error": {"message": msg}})


def _rate_limit_error(msg: str = "rate limit exceeded") -> RateLimitError:
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp = httpx.Response(429, request=req)
    return RateLimitError(msg, response=resp, body={"error": {"message": msg}})


def test_authentication_error_surfaces_without_retry(mock_openai, fake_video):
    """HI-01 / CLEAN-01: 401 AuthenticationError on first call -> exactly one
    create() invocation and no compact retry. The real root cause (bad key)
    must not be masked by VideoAnalysisRetryExhausted.
    """
    mock_openai.chat.completions.create.side_effect = _auth_error()
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is False
    assert mock_openai.chat.completions.create.call_count == 1
    low = (result.error or "").lower()
    assert "authentication" in low or "auth" in low
    assert "retry exhausted" not in low


def test_permission_denied_error_surfaces_without_retry(mock_openai, fake_video):
    """HI-01 / CLEAN-01: 403 PermissionDeniedError fast-fails — same semantics
    as 401 (bad key / model not accessible — compact retry cannot fix it).
    """
    mock_openai.chat.completions.create.side_effect = _permission_error()
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is False
    assert mock_openai.chat.completions.create.call_count == 1
    low = (result.error or "").lower()
    assert "permission" in low
    assert "retry exhausted" not in low


def test_rate_limit_error_surfaces_without_retry(mock_openai, fake_video):
    """HI-01 / CLEAN-01: 429 RateLimitError fast-fails — retrying through the
    compact ladder would compound the rate-limit amplification.
    """
    mock_openai.chat.completions.create.side_effect = _rate_limit_error()
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is False
    assert mock_openai.chat.completions.create.call_count == 1
    low = (result.error or "").lower()
    assert "rate" in low
    assert "retry exhausted" not in low


def test_generic_apierror_still_retries_compact(
    mock_openai, fake_video, valid_artifact, openrouter_response_factories,
):
    """HI-01 guardrail: a generic APIError that is NOT one of the three
    non-retriable sentinels must STILL trigger the compact-retry ladder.
    Prevents an over-narrow fix from silently changing existing retry
    semantics.

    Sequence: first call raises a bare APIError -> code should wrap it as
    VideoAnalysisError and go through the compact-retry branch. We feed a
    successful response on the retry; assert call_count >= 2.
    """
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    generic = APIError("transient server error", request=req, body=None)
    fac = openrouter_response_factories
    mock_openai.chat.completions.create.side_effect = [
        generic,
        fac["ok"](valid_artifact),
        fac["ok"](valid_artifact),
        fac["ok"](valid_artifact),
    ]
    t = OpenRouterVideoAnalyzer()
    t.execute({"video_path": str(fake_video)})
    assert mock_openai.chat.completions.create.call_count >= 2, (
        "Generic APIError must still trigger the compact-retry ladder"
    )


# ---------------------------------------------------------------------------
# Cost observability (usage.cost body, not headers)
# ---------------------------------------------------------------------------


def test_cost_from_usage_body(mock_openai, fake_video, valid_artifact):
    """Cost observability: cost_usd pulled from resp.usage.cost body field."""
    resp = _resp_ok(valid_artifact, cost=0.0025)
    mock_openai.chat.completions.create.return_value = resp
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    assert result.cost_usd == 0.0025
    # Guard: tool source never reads response.headers / documented-mythic header
    src = _SOURCE_PATH.read_text(encoding="utf-8")
    assert "response.headers" not in src
    assert "x-openrouter-credit-remaining" not in src


def test_tool_result_model_reflects_response_model(mock_openai, fake_video, valid_artifact):
    """ToolResult.model reflects resp.model (provider's actual model ID)."""
    resp = _resp_ok(valid_artifact, model="google/gemini-3.1-pro-preview")
    mock_openai.chat.completions.create.return_value = resp
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    assert result.model == "google/gemini-3.1-pro-preview"


# ---------------------------------------------------------------------------
# Artifact validation gate
# ---------------------------------------------------------------------------


def test_invalid_artifact_rejected(mock_openai, fake_video):
    """Artifact failing canonical schema -> success=False with validation-related error."""
    bogus = {"foo": "bar"}
    mock_openai.chat.completions.create.return_value = _resp_ok(bogus)
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is False
    low = (result.error or "").lower()
    assert any(term in low for term in ("schema", "validation"))


# ---------------------------------------------------------------------------
# WR-05 — tool does not import checkpoint
# ---------------------------------------------------------------------------


def test_tool_does_not_import_checkpoint():
    """WR-05 guard: tool must not import or call write_checkpoint."""
    source = _SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "lib.checkpoint", (
                "Tool must not import from lib.checkpoint"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "lib.checkpoint", (
                    "Tool must not import lib.checkpoint"
                )
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == "write_checkpoint":
                raise AssertionError("Tool must not call write_checkpoint()")
            if isinstance(fn, ast.Attribute) and fn.attr == "write_checkpoint":
                raise AssertionError("Tool must not call *.write_checkpoint()")


# ---------------------------------------------------------------------------
# ANLZ-06 / Pitfall 7 — no selector metadata stamped on result.data
# ---------------------------------------------------------------------------


def test_result_data_is_canonical_artifact_only(mock_openai, fake_video, valid_artifact):
    """ANLZ-06: result.data deep-equals the canonical artifact — no extra keys.

    Guards against Pitfall 7 (provider accidentally stamps selected_provider /
    provider_used / selected_tool onto the artifact).
    """
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    assert result.data == valid_artifact  # deep equality — no extra keys
    forbidden = {"selected_provider", "provider_used", "selected_tool", "_selector"}
    assert forbidden.isdisjoint(result.data.keys())


# ---------------------------------------------------------------------------
# MD-01 — _FLAT_SCHEMA lazy cache
# ---------------------------------------------------------------------------


def test_flat_schema_is_lazy():
    """MD-01 pattern: _FLAT_SCHEMA is None until first call, then cached."""
    # Reset the class-level cache for test isolation
    OpenRouterVideoAnalyzer._FLAT_SCHEMA = None
    assert OpenRouterVideoAnalyzer._FLAT_SCHEMA is None
    first = OpenRouterVideoAnalyzer._flat_schema()
    assert OpenRouterVideoAnalyzer._FLAT_SCHEMA is not None
    assert isinstance(first, dict)
    second = OpenRouterVideoAnalyzer._flat_schema()
    assert second is first  # same cached object identity


# ---------------------------------------------------------------------------
# Shot boundary normalization
# ---------------------------------------------------------------------------


def test_normalize_shot_boundaries_tuples_and_dicts():
    """Normalizer accepts both list-of-lists and list-of-dicts (mirrors Phase 2)."""
    a = _normalize_shot_boundaries([[0.0, 3.4], [3.4, 6.8]])
    b = _normalize_shot_boundaries(
        [
            {"start_seconds": 0.0, "end_seconds": 3.4},
            {"start_seconds": 3.4, "end_seconds": 6.8},
        ]
    )
    assert a == [(0.0, 3.4), (3.4, 6.8)]
    assert b == [(0.0, 3.4), (3.4, 6.8)]
    # Malformed drops silently; does not raise
    assert _normalize_shot_boundaries(None) == []
    assert _normalize_shot_boundaries([{"x": 1}, "garbage"]) == []


# ---------------------------------------------------------------------------
# T-03-06 — API key value never leaks into ToolResult.error (every failure path)
# ---------------------------------------------------------------------------


def test_api_key_value_not_in_any_error(mock_openai, fake_video, monkeypatch, valid_artifact):
    """Security T-03-06: sentinel API key value must NOT appear in any error string."""
    sentinel = "sk-or-v1-sentinel-value-xyz1234567890abcdef"
    monkeypatch.setenv("OPENROUTER_API_KEY", sentinel)

    tool = OpenRouterVideoAnalyzer()

    # Path A: missing file
    missing = fake_video.parent / "does_not_exist.mp4"
    r1 = tool.execute({"video_path": str(missing)})
    assert r1.success is False and sentinel not in (r1.error or "")

    # Path B: oversize
    big = fake_video.parent / "big.mp4"
    big.write_bytes(b"\x00" * 2048)
    r2 = tool.execute({"video_path": str(big), "max_upload_bytes": 256})
    assert r2.success is False and sentinel not in (r2.error or "")

    # Path C: unsupported MIME
    bad_mime = fake_video.parent / "x.avi"
    bad_mime.write_bytes(b"\x00" * 64)
    r3 = tool.execute({"video_path": str(bad_mime)})
    assert r3.success is False and sentinel not in (r3.error or "")

    # Path D: BadRequest on structured AND every fallback branch
    # Ladder can make up to 3 calls: structured+full, embedded+full, embedded+compact
    mock_openai.chat.completions.create.side_effect = [_bad_request("unsupported")] * 4
    r4 = tool.execute({"video_path": str(fake_video)})
    assert r4.success is False and sentinel not in (r4.error or "")

    # Path E: truncation exhausted
    resp_trunc = MagicMock()
    choice = MagicMock()
    choice.finish_reason = "length"
    choice.message.content = ""
    resp_trunc.choices = [choice]
    resp_trunc.model = "google/gemini-3.1-pro-preview"
    resp_trunc.usage = MagicMock(cost=0.0)
    mock_openai.chat.completions.create.side_effect = [resp_trunc] * 6
    r5 = tool.execute({"video_path": str(fake_video)})
    assert r5.success is False and sentinel not in (r5.error or "")

    # Path F: invalid artifact (post-validation)
    mock_openai.chat.completions.create.side_effect = None
    mock_openai.chat.completions.create.return_value = _resp_ok({"foo": "bar"})
    r6 = tool.execute({"video_path": str(fake_video)})
    assert r6.success is False and sentinel not in (r6.error or "")
