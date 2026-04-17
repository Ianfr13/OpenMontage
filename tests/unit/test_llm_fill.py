"""Unit tests for lib/llm_fill.py (Phase 5 Plan 05-03).

Covers SYNTH-03 (LLM fill-in) + SYNTH-04 (mode routing).

The 10 behaviors below exercise the fallback contract from 05-03-PLAN.md:

  Test 1  test_env_opt_out                     — VIDEO_SYNTH_LLM_FILL=false → base unchanged
  Test 2  test_missing_key                      — no OPENROUTER_API_KEY → base unchanged
  Test 3  test_happy_path_merge                 — valid LLM JSON → fields merged into matching stage
  Test 4  test_json_parse_failure_retries       — bad JSON then good JSON → 2 calls, merged
  Test 5  test_json_parse_failure_twice_falls_back — bad JSON twice → base unchanged
  Test 6  test_openai_exception_falls_back      — APIConnectionError → base unchanged, no raise
  Test 7  test_post_fill_validation_reverts_on_failure — bogus tool → revert to base
  Test 8  test_modes_differ                     — template vs replica prompts differ
  Test 9  test_token_budget_respected           — max_tokens=2000
  Test 10 test_llm_never_invents_stages         — extra stage dropped in merge
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Repo root on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _base_manifest() -> dict:
    """A minimal manifest shaped like a loaded base pipeline manifest.

    The three stage names mirror a subset of a real cinematic pipeline so
    merges and drops can be verified without loading pipeline_defs/.
    """
    return {
        "name": "fake-base",
        "version": "2.0",
        "description": "fake base for llm_fill tests",
        "category": "cinematic",
        "stability": "production",
        "stages": [
            {
                "name": "research",
                "skill": "pipelines/fake/research-director",
                "produces": ["research_brief"],
                "tools_available": ["web_search"],
                "review_focus": ["existing focus"],
                "success_criteria": ["existing criteria"],
            },
            {
                "name": "script",
                "skill": "pipelines/fake/script-director",
                "produces": ["script"],
                "tools_available": [],
                "review_focus": [],
                "success_criteria": [],
            },
            {
                "name": "compose",
                "skill": "pipelines/fake/compose-director",
                "produces": ["render_report"],
                "tools_available": ["video_compose"],
                "review_focus": [],
                "success_criteria": [],
            },
        ],
    }


def _analysis() -> dict:
    return {
        "version": "2.0",
        "editing_pacing": {
            "pacing_style": "steady_educational",
        },
        "narrative": {
            "section_structure": [],
        },
    }


def _make_resp(content: str) -> MagicMock:
    """Build a MagicMock mimicking an openai chat.completions.create response."""
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    resp.choices = [choice]
    return resp


def _patch_validator_ok(monkeypatch):
    """Patch validate_synthesized_pipeline imported inside llm_fill to return []."""
    import lib.pipeline_synthesizer as ps

    monkeypatch.setattr(ps, "validate_synthesized_pipeline", lambda _m: [])


# ---------------------------------------------------------------------------
# Test 1: env opt-out
# ---------------------------------------------------------------------------


def test_env_opt_out(monkeypatch):
    monkeypatch.setenv("VIDEO_SYNTH_LLM_FILL", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    from lib.llm_fill import fill_stage_details

    base = _base_manifest()
    result = fill_stage_details(base, _analysis(), mode="template")
    assert result == base
    # Returns a copy (not the same object) so callers can mutate safely.
    assert result is not base


# ---------------------------------------------------------------------------
# Test 2: missing OPENROUTER_API_KEY
# ---------------------------------------------------------------------------


def test_missing_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("VIDEO_SYNTH_LLM_FILL", raising=False)

    # Spy on OpenAI constructor to prove it never runs.
    import lib.llm_fill as lf

    spy = MagicMock()
    monkeypatch.setattr(lf, "OpenAI", spy)

    from lib.llm_fill import fill_stage_details

    base = _base_manifest()
    result = fill_stage_details(base, _analysis(), mode="template")
    assert result == base
    spy.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: happy path — fields merged into matching stage ONLY
# ---------------------------------------------------------------------------


def test_happy_path_merge(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("VIDEO_SYNTH_LLM_FILL", raising=False)

    payload = {
        "stages": [
            {
                "name": "research",
                "tools_available": ["web_search", "transcript_fetcher"],
                "review_focus": ["reference match", "source verified"],
                "success_criteria": ["artifact valid"],
            }
        ]
    }

    import lib.llm_fill as lf

    client = MagicMock()
    client.chat.completions.create.return_value = _make_resp(json.dumps(payload))
    monkeypatch.setattr(lf, "OpenAI", MagicMock(return_value=client))

    _patch_validator_ok(monkeypatch)

    from lib.llm_fill import fill_stage_details

    base = _base_manifest()
    result = fill_stage_details(base, _analysis(), mode="template")

    # research stage: overwritten
    research = next(s for s in result["stages"] if s["name"] == "research")
    assert research["tools_available"] == ["web_search", "transcript_fetcher"]
    assert research["review_focus"] == ["reference match", "source verified"]
    assert research["success_criteria"] == ["artifact valid"]

    # script / compose untouched
    script = next(s for s in result["stages"] if s["name"] == "script")
    compose = next(s for s in result["stages"] if s["name"] == "compose")
    assert script["tools_available"] == []
    assert compose["tools_available"] == ["video_compose"]


# ---------------------------------------------------------------------------
# Test 4: JSON parse failure → retry → success
# ---------------------------------------------------------------------------


def test_json_parse_failure_retries(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("VIDEO_SYNTH_LLM_FILL", raising=False)

    payload_ok = {
        "stages": [
            {"name": "research", "tools_available": ["web_search"]}
        ]
    }

    import lib.llm_fill as lf

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _make_resp("not json"),
        _make_resp(json.dumps(payload_ok)),
    ]
    monkeypatch.setattr(lf, "OpenAI", MagicMock(return_value=client))

    _patch_validator_ok(monkeypatch)

    from lib.llm_fill import fill_stage_details

    result = fill_stage_details(_base_manifest(), _analysis())
    assert client.chat.completions.create.call_count == 2
    # Merged — research tools_available came from the LLM payload.
    research = next(s for s in result["stages"] if s["name"] == "research")
    assert research["tools_available"] == ["web_search"]


# ---------------------------------------------------------------------------
# Test 5: JSON parse failure twice → fall back to base
# ---------------------------------------------------------------------------


def test_json_parse_failure_twice_falls_back(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("VIDEO_SYNTH_LLM_FILL", raising=False)

    import lib.llm_fill as lf

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _make_resp("not json"),
        _make_resp("still not json"),
    ]
    monkeypatch.setattr(lf, "OpenAI", MagicMock(return_value=client))

    from lib.llm_fill import fill_stage_details

    base = _base_manifest()
    result = fill_stage_details(base, _analysis())
    assert client.chat.completions.create.call_count == 2
    assert result == base


# ---------------------------------------------------------------------------
# Test 6: openai exception → base unchanged, no raise
# ---------------------------------------------------------------------------


def test_openai_exception_falls_back(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("VIDEO_SYNTH_LLM_FILL", raising=False)

    from openai import APIConnectionError

    import lib.llm_fill as lf

    client = MagicMock()
    # APIConnectionError requires request= kwarg in openai>=1.0.
    client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
    monkeypatch.setattr(lf, "OpenAI", MagicMock(return_value=client))

    from lib.llm_fill import fill_stage_details

    base = _base_manifest()
    # Must NOT raise.
    result = fill_stage_details(base, _analysis())
    assert result == base


# ---------------------------------------------------------------------------
# Test 7: post-fill validation failure → revert to base
# ---------------------------------------------------------------------------


def test_post_fill_validation_reverts_on_failure(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("VIDEO_SYNTH_LLM_FILL", raising=False)

    payload = {
        "stages": [
            {
                "name": "research",
                "tools_available": ["absolutely_fake_tool_9999"],
            }
        ]
    }

    import lib.llm_fill as lf

    client = MagicMock()
    client.chat.completions.create.return_value = _make_resp(json.dumps(payload))
    monkeypatch.setattr(lf, "OpenAI", MagicMock(return_value=client))

    # Patch the validator to report an issue for the fake tool.
    import lib.pipeline_synthesizer as ps

    monkeypatch.setattr(
        ps,
        "validate_synthesized_pipeline",
        lambda _m: ["stage 'research': tool 'absolutely_fake_tool_9999' not in registry"],
    )

    from lib.llm_fill import fill_stage_details

    base = _base_manifest()
    result = fill_stage_details(base, _analysis())
    # Helper returned base unchanged (the broken merge was discarded).
    assert result == base


# ---------------------------------------------------------------------------
# Test 8: template vs replica prompts differ
# ---------------------------------------------------------------------------


def test_modes_differ(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("VIDEO_SYNTH_LLM_FILL", raising=False)

    payload = {"stages": []}

    import lib.llm_fill as lf

    client = MagicMock()
    client.chat.completions.create.return_value = _make_resp(json.dumps(payload))
    monkeypatch.setattr(lf, "OpenAI", MagicMock(return_value=client))

    _patch_validator_ok(monkeypatch)

    from lib.llm_fill import fill_stage_details

    fill_stage_details(_base_manifest(), _analysis(), mode="template")
    fill_stage_details(_base_manifest(), _analysis(), mode="replica")

    assert client.chat.completions.create.call_count == 2
    prompts = [
        call.kwargs["messages"][0]["content"]
        for call in client.chat.completions.create.call_args_list
    ]
    assert prompts[0] != prompts[1]
    # Soft assertion the prompts are meaningfully different — substrings from plan.
    assert "generalizable" in prompts[0].lower()
    assert "closer reproduction" in prompts[1].lower()


# ---------------------------------------------------------------------------
# Test 9: 2000 token budget passed
# ---------------------------------------------------------------------------


def test_token_budget_respected(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("VIDEO_SYNTH_LLM_FILL", raising=False)

    payload = {"stages": []}

    import lib.llm_fill as lf

    client = MagicMock()
    client.chat.completions.create.return_value = _make_resp(json.dumps(payload))
    monkeypatch.setattr(lf, "OpenAI", MagicMock(return_value=client))

    _patch_validator_ok(monkeypatch)

    from lib.llm_fill import fill_stage_details

    fill_stage_details(_base_manifest(), _analysis())
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["max_tokens"] == 2000
    assert kwargs["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# Test 10: LLM cannot invent stages
# ---------------------------------------------------------------------------


def test_llm_never_invents_stages(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("VIDEO_SYNTH_LLM_FILL", raising=False)

    payload = {
        "stages": [
            {"name": "research", "tools_available": ["web_search"]},
            {
                # This stage is NOT in base_manifest — must be dropped.
                "name": "malicious_new_stage",
                "tools_available": ["rm_rf_slash"],
            },
        ]
    }

    import lib.llm_fill as lf

    client = MagicMock()
    client.chat.completions.create.return_value = _make_resp(json.dumps(payload))
    monkeypatch.setattr(lf, "OpenAI", MagicMock(return_value=client))

    _patch_validator_ok(monkeypatch)

    from lib.llm_fill import fill_stage_details

    base = _base_manifest()
    result = fill_stage_details(base, _analysis())

    names = [s["name"] for s in result["stages"]]
    # Malicious stage is NOT in the result.
    assert "malicious_new_stage" not in names
    # Original stage count preserved.
    assert names == [s["name"] for s in base["stages"]]
