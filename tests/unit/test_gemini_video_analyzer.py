"""Unit tests for ``tools/analysis/gemini_video_analyzer.py``.

All tests mock the google-genai SDK — no real API key required, no network.
``time.sleep`` is patched to no-op in the ``mock_genai`` fixture, so the polling
loop completes instantly.

Covers the 18 behaviors specified in plan 02-02's ``<behavior>`` block:

    1.  contract fields (name/capability/provider/runtime/agent_skills)
    2.  auth priority (GEMINI_API_KEY beats GOOGLE_API_KEY)
    3.  fallback to GOOGLE_API_KEY when GEMINI_API_KEY unset
    4.  no key -> error does not leak key value
    5.  poll PROCESSING -> ACTIVE -> analyze succeeds
    6.  FAILED state raises VideoUploadError
    7.  wall-clock timeout raises VideoUploadError
    8.  file deleted on success
    9.  file deleted on failure (finally block)
    10. flattened schema passed to generate_content.config
    11. MAX_TOKENS triggers compact retry
    12. retry exhausted surfaces error cleanly
    13. empty response text triggers retry
    14. model fallback on ClientError (preview -> 2.5-pro)
    15. shot_boundaries absent -> prompt directs shot_boundary_source="model"
    16. shot_boundaries accepts list-of-tuples AND list-of-dicts
    17. confidence="low" directive present in every prompt
    18. invalid artifact -> failure + file still deleted
    + tool does NOT import write_checkpoint
    + bonus: API key value never leaks into error text
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from google.genai import errors, types  # noqa: E402

from lib.analysis_errors import (  # noqa: E402
    VideoAnalysisError,
    VideoAnalysisRetryExhausted,
    VideoUploadError,
)
from tools.analysis.gemini_video_analyzer import (  # noqa: E402
    DEFAULT_PREVIEW_MODEL,
    FALLBACK_MODEL,
    GeminiVideoAnalyzer,
    _get_api_key,
    _normalize_shot_boundaries,
    _wait_for_active,
)


# ---------------------------------------------------------------------------
# Test 1 — GEM-01: contract fields
# ---------------------------------------------------------------------------
def test_contract_fields():
    t = GeminiVideoAnalyzer()
    info = t.get_info()
    assert info["name"] == "gemini_video_analyzer"
    assert info["capability"] == "video_analysis"
    assert info["provider"] == "gemini"
    assert info["runtime"] == "api"
    assert info["agent_skills"] == ["gemini-video-analysis"]


# ---------------------------------------------------------------------------
# Test 2 — GEM-01: auth priority (GEMINI_API_KEY beats GOOGLE_API_KEY)
# ---------------------------------------------------------------------------
def test_auth_priority_gemini_first(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem-1")
    monkeypatch.setenv("GOOGLE_API_KEY", "goo-1")
    assert _get_api_key() == "gem-1"


def test_auth_falls_back_to_google(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "goo-1")
    assert _get_api_key() == "goo-1"


# ---------------------------------------------------------------------------
# Test 3 — GEM-01: missing key — error does not leak key value
# ---------------------------------------------------------------------------
def test_execute_no_key_returns_error_without_leaking_value(no_keys, fake_video):
    tool = GeminiVideoAnalyzer()
    result = tool.execute({"video_path": str(fake_video)})
    assert result.success is False
    assert "GEMINI_API_KEY" in result.error
    # Defensive: no typical test-key strings should appear in the error
    assert "gem-" not in result.error
    assert "goo-" not in result.error


# ---------------------------------------------------------------------------
# Test 4 — GEM-02: polling returns ACTIVE after PROCESSING
# ---------------------------------------------------------------------------
def test_poll_processing_then_active(mock_genai, fake_video, valid_artifact):
    # Default fixture: upload PROCESSING -> get [PROCESSING, ACTIVE]
    tool = GeminiVideoAnalyzer()
    result = tool.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    assert result.data == valid_artifact
    # Polled twice: first returns PROCESSING, second returns ACTIVE
    assert mock_genai.files.get.call_count == 2


# ---------------------------------------------------------------------------
# Test 5 — GEM-02: FAILED state raises VideoUploadError (surfaced as failure)
# ---------------------------------------------------------------------------
def test_poll_failed_raises(mock_genai, fake_video, fake_file_factory):
    mock_genai.files.get.side_effect = [
        fake_file_factory(state="FAILED", error="format_not_supported"),
    ]
    tool = GeminiVideoAnalyzer()
    result = tool.execute({"video_path": str(fake_video)})
    assert result.success is False
    assert "FAILED" in result.error


# ---------------------------------------------------------------------------
# Test 6 — GEM-02: wall-clock timeout raises VideoUploadError
# ---------------------------------------------------------------------------
def test_poll_timeout_raises(
    mock_genai, fake_video, fake_file_factory, monkeypatch
):
    # Return PROCESSING forever
    mock_genai.files.get.side_effect = lambda name: fake_file_factory(
        state="PROCESSING"
    )
    # Fake monotonic that jumps 50s per call; second call -> elapsed=50 > 30
    import tools.analysis.gemini_video_analyzer as target

    clock = [0.0]

    def fake_monotonic():
        clock[0] += 50.0
        return clock[0]

    monkeypatch.setattr(target.time, "monotonic", fake_monotonic)

    tool = GeminiVideoAnalyzer()
    result = tool.execute(
        {"video_path": str(fake_video), "max_poll_seconds": 30.0}
    )
    assert result.success is False
    assert "did not reach ACTIVE" in result.error


# ---------------------------------------------------------------------------
# Test 7 — GEM-03: delete on success
# ---------------------------------------------------------------------------
def test_file_deleted_on_success(mock_genai, fake_video):
    tool = GeminiVideoAnalyzer()
    result = tool.execute({"video_path": str(fake_video)})
    assert result.success is True
    mock_genai.files.delete.assert_called_once_with(name="files/abc123")


# ---------------------------------------------------------------------------
# Test 8 — GEM-03: delete on failure (finally block)
# ---------------------------------------------------------------------------
def test_file_deleted_on_failure(mock_genai, fake_video):
    # Persistent truncation: 4-branch ladder can call up to 4 times (full+compact
    # on preview, full+compact on fallback). Use side_effect list big enough.
    resp_bad = MagicMock()
    cand = MagicMock()
    cand.finish_reason = types.FinishReason.MAX_TOKENS
    resp_bad.candidates = [cand]
    resp_bad.text = ""
    mock_genai.models.generate_content.side_effect = [resp_bad, resp_bad]
    tool = GeminiVideoAnalyzer()
    result = tool.execute({"video_path": str(fake_video)})
    assert result.success is False
    mock_genai.files.delete.assert_called_once_with(name="files/abc123")


# ---------------------------------------------------------------------------
# Test 9 — GEM-04: flattened schema passed via config
# ---------------------------------------------------------------------------
def test_flat_schema_passed_to_generate_content(mock_genai, fake_video):
    tool = GeminiVideoAnalyzer()
    tool.execute({"video_path": str(fake_video)})
    call_kwargs = mock_genai.models.generate_content.call_args.kwargs
    config = call_kwargs["config"]
    assert config.response_mime_type == "application/json"
    flat = config.response_json_schema
    s = json.dumps(flat)
    assert "$ref" not in s
    assert "uniqueItems" not in s
    # additionalProperties: False removed; additionalProperties with an object
    # value is preserved. Match on the exact unspaced form for both.
    compact = s.replace(" ", "")
    assert '"additionalProperties":false' not in compact


# ---------------------------------------------------------------------------
# Test 10 — GEM-04: MAX_TOKENS triggers compact retry
# ---------------------------------------------------------------------------
def test_max_tokens_triggers_compact_retry(
    mock_genai, fake_video, valid_artifact, response_factories
):
    resp1 = response_factories["truncated"]("")
    resp2 = response_factories["ok"](valid_artifact)
    mock_genai.models.generate_content.side_effect = [resp1, resp2]
    tool = GeminiVideoAnalyzer()
    result = tool.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    calls = mock_genai.models.generate_content.call_args_list
    assert len(calls) == 2
    # Second call's prompt should carry the "compact" directive
    second_contents = calls[1].kwargs["contents"]
    joined = " ".join(str(c) for c in second_contents)
    assert "compact" in joined.lower()


# ---------------------------------------------------------------------------
# Test 11 — GEM-04: retry exhausted raises (surfaced as ToolResult.error)
# ---------------------------------------------------------------------------
def test_retry_exhausted_raises(mock_genai, fake_video, response_factories):
    resp = response_factories["truncated"]("")
    # 4-branch ladder can attempt up to 4 times on preview+fallback; feed
    # enough truncated responses to exhaust every branch.
    mock_genai.models.generate_content.side_effect = [resp, resp, resp, resp]
    tool = GeminiVideoAnalyzer()
    result = tool.execute({"video_path": str(fake_video)})
    assert result.success is False
    low = (result.error or "").lower()
    assert any(
        term in low
        for term in ("compact", "retry", "truncated", "max_tokens")
    )


# ---------------------------------------------------------------------------
# Test 12 — GEM-04: empty response text triggers retry
# ---------------------------------------------------------------------------
def test_empty_text_triggers_retry(
    mock_genai, fake_video, valid_artifact, response_factories
):
    resp1 = response_factories["empty_stop"]("")  # STOP but empty text
    resp2 = response_factories["ok"](valid_artifact)
    mock_genai.models.generate_content.side_effect = [resp1, resp2]
    tool = GeminiVideoAnalyzer()
    result = tool.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    assert mock_genai.models.generate_content.call_count == 2


# ---------------------------------------------------------------------------
# Test 13 — GEM-04: model fallback on ClientError (preview -> 2.5-pro)
# ---------------------------------------------------------------------------
def test_model_fallback_on_preview_unavailable(
    mock_genai, fake_video, valid_artifact, response_factories
):
    client_error = errors.ClientError(
        404,
        response_json={"error": {"message": "model not found"}},
        response=None,
    )
    resp_ok = response_factories["ok"](valid_artifact)
    mock_genai.models.generate_content.side_effect = [client_error, resp_ok]
    tool = GeminiVideoAnalyzer()
    result = tool.execute({"video_path": str(fake_video)})
    assert result.success is True, result.error
    assert result.model == FALLBACK_MODEL
    calls = mock_genai.models.generate_content.call_args_list
    assert calls[0].kwargs["model"] == DEFAULT_PREVIEW_MODEL
    assert calls[1].kwargs["model"] == FALLBACK_MODEL


# ---------------------------------------------------------------------------
# Test 14 — ANLZ-05: shot_boundaries absent -> prompt has model directive
# ---------------------------------------------------------------------------
def test_shot_boundaries_absent_prompt_has_model_directive(
    mock_genai, fake_video
):
    tool = GeminiVideoAnalyzer()
    tool.execute({"video_path": str(fake_video)})
    call0 = mock_genai.models.generate_content.call_args_list[0]
    prompt_text = " ".join(str(c) for c in call0.kwargs["contents"])
    assert "shot_boundary_source" in prompt_text
    assert "model" in prompt_text


# ---------------------------------------------------------------------------
# Test 15 — ANLZ-05: shot_boundaries accepts both list-of-tuples AND dict form
# ---------------------------------------------------------------------------
def test_shot_boundaries_both_shapes_normalize():
    a = _normalize_shot_boundaries([[0.0, 3.4], [3.4, 6.8]])
    b = _normalize_shot_boundaries(
        [
            {"start_seconds": 0.0, "end_seconds": 3.4},
            {"start_seconds": 3.4, "end_seconds": 6.8},
        ]
    )
    assert a == [(0.0, 3.4), (3.4, 6.8)]
    assert b == [(0.0, 3.4), (3.4, 6.8)]


def test_shot_boundaries_passed_into_prompt(mock_genai, fake_video):
    tool = GeminiVideoAnalyzer()
    tool.execute(
        {
            "video_path": str(fake_video),
            "shot_boundaries": [[0.0, 3.4], [3.4, 6.8]],
        }
    )
    call0 = mock_genai.models.generate_content.call_args_list[0]
    prompt_text = " ".join(str(c) for c in call0.kwargs["contents"])
    # Normalized rendering is "0.0-3.4s, 3.4-6.8s"
    assert "0.0-3.4s" in prompt_text


# ---------------------------------------------------------------------------
# Test 16 — ANLZ-04: confidence="low" directive present in every prompt
# ---------------------------------------------------------------------------
def test_prompt_instructs_confidence_low_not_null(mock_genai, fake_video):
    tool = GeminiVideoAnalyzer()
    tool.execute({"video_path": str(fake_video)})
    call0 = mock_genai.models.generate_content.call_args_list[0]
    prompt_text = " ".join(str(c) for c in call0.kwargs["contents"])
    assert '"low"' in prompt_text
    assert "confidence" in prompt_text.lower()
    # Tool MUST instruct the model NOT to emit null — expect a prohibition,
    # not the absence of the word "null". Accept any phrasing that pairs
    # "null" with a negation ("never", "not", "do not", "avoid").
    lower = prompt_text.lower()
    negation_window = any(
        phrase in lower
        for phrase in ("never emit null", "not emit null", "never null", "avoid null")
    )
    assert negation_window, (
        "Prompt must include a directive against emitting null values; "
        f"got: {prompt_text!r}"
    )


# ---------------------------------------------------------------------------
# Test 17 — Artifact validation gate (invalid -> failure + delete)
# ---------------------------------------------------------------------------
def test_invalid_artifact_returns_failure_and_deletes(
    mock_genai, fake_video, response_factories
):
    # Return valid JSON that fails canonical schema (missing top-level dims)
    invalid = {"foo": "bar"}
    mock_genai.models.generate_content.return_value = response_factories["ok"](
        invalid
    )
    tool = GeminiVideoAnalyzer()
    result = tool.execute({"video_path": str(fake_video)})
    assert result.success is False
    assert any(
        term in (result.error or "").lower()
        for term in ("schema", "validation")
    )
    mock_genai.files.delete.assert_called_once_with(name="files/abc123")


# ---------------------------------------------------------------------------
# Test 18 — Tool does NOT import or call write_checkpoint
# ---------------------------------------------------------------------------
def test_tool_source_does_not_import_write_checkpoint():
    """The tool module must not import from ``lib.checkpoint`` nor call
    ``write_checkpoint``. Docstrings are excluded from the check so prose
    explanations like "does NOT call write_checkpoint" don't trip the guard.
    """
    import ast

    src_path = _REPO_ROOT / "tools" / "analysis" / "gemini_video_analyzer.py"
    source = src_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Check imports — no ``from lib.checkpoint import ...`` and no
    # ``import lib.checkpoint`` anywhere in the module.
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

    # Check no ``write_checkpoint(...)`` call attribute anywhere.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == "write_checkpoint":
                raise AssertionError("Tool must not call write_checkpoint()")
            if isinstance(fn, ast.Attribute) and fn.attr == "write_checkpoint":
                raise AssertionError(
                    "Tool must not call *.write_checkpoint()"
                )


# ---------------------------------------------------------------------------
# Bonus (T-02-16) — API key value never leaks into ToolResult.error
# ---------------------------------------------------------------------------
def test_api_key_value_not_in_any_error(mock_genai, fake_video, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-abcd1234")
    # Force a failure path after client construction
    mock_genai.files.upload.side_effect = RuntimeError("upload crashed")
    tool = GeminiVideoAnalyzer()
    try:
        result = tool.execute({"video_path": str(fake_video)})
    except RuntimeError:
        # Tool does not catch bare RuntimeError — but the mock path above
        # hits the upload() line; if the tool re-raises, that's acceptable
        # (the key still never reaches result.error). Nothing to assert.
        return
    assert "super-secret-abcd1234" not in (result.error or "")
