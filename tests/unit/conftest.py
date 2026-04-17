"""Shared pytest fixtures for Phase 2 Gemini provider unit tests.

All fixtures neutralize network: no real ``google-genai`` calls, no real API key
required, ``time.sleep`` patched to no-op. Tests import ``mock_genai`` to stub
the full SDK surface in one line; import ``valid_artifact`` for a schema-valid
canonical ``video_analysis`` artifact to return from mocked ``generate_content``.

This conftest is scoped to ``tests/unit/`` — it does not affect contract tests.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure repo root on sys.path so ``from tools.analysis...`` resolves when pytest
# is invoked from any cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# Import the minimal valid artifact helper from Phase 1's contract tests.
# This is the single source of truth for a canonical video_analysis fixture —
# shared so fake fixtures can never drift from the real schema (T-02-18).
try:
    from tests.contracts.test_video_analysis_schema import (
        minimal_video_analysis as _minimal,
    )
except ImportError:  # pragma: no cover - defensive guard for rename drift
    def _minimal():
        raise RuntimeError(
            "minimal_video_analysis() helper missing from Phase 1 tests — "
            "update tests/unit/conftest.py imports."
        )


@pytest.fixture(autouse=True)
def _scrub_provider_keys(monkeypatch):
    """Strip any provider env vars leaking in from the developer's shell.

    ``mock_genai`` re-injects ``GEMINI_API_KEY='test-key'`` for the happy path;
    tests that assert the unset-key path use the ``no_keys`` fixture (which
    just re-applies this scrub and is a no-op here).
    """
    for key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
        "VIDEO_ANALYZER_PROVIDER",
        "GEMINI_VIDEO_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def valid_artifact() -> dict:
    """A fresh deepcopy of a schema-valid ``video_analysis`` artifact.

    Deepcopied because tests mutate fields per-case.
    """
    return copy.deepcopy(_minimal())


def _deep_merge(dst: dict, src: dict) -> None:
    """In-place recursive dict merge: override ``dst`` with ``src``.

    Nested dicts are merged; all other values (including lists) are replaced.
    Used by ``fake_video_chunks`` so per-chunk overrides target nested fields
    (``editing_pacing.cuts_per_minute``) without clobbering siblings.
    """
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v


@pytest.fixture
def fake_video_chunks():
    """Factory for ``list[(Chunk, artifact_dict)]`` used by merger tests.

    Each call returns a list of ``n`` ``(Chunk, artifact)`` tuples. Every
    artifact starts as a deep copy of the Phase 1 ``minimal_video_analysis``
    fixture (schema-valid) and is patched by ``_deep_merge`` with the
    matching ``overrides[i]`` dict. The ``Chunk.start_global`` /
    ``end_global`` are computed from ``chunk_seconds`` so the merger sees
    the same globally-shifted timeline the real pipeline would.

    Usage:
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"editing_pacing": {"cuts_per_minute": 6.0, "total_shots": 5}},
                {"editing_pacing": {"cuts_per_minute": 3.0, "total_shots": 7}},
                {"editing_pacing": {"cuts_per_minute": 9.0, "total_shots": 9}},
            ],
        )
    """
    from lib.video_chunker import Chunk

    def _build(
        n: int = 3,
        overrides: list[dict] | None = None,
        chunk_seconds: float = 300.0,
    ) -> list:
        ov = overrides or [{} for _ in range(n)]
        out = []
        for i in range(n):
            art = copy.deepcopy(_minimal())
            if i < len(ov) and ov[i]:
                _deep_merge(art, ov[i])
            start = i * chunk_seconds
            end = start + chunk_seconds
            out.append(
                (
                    Chunk(
                        start_global=start,
                        end_global=end,
                        local_path=f"/tmp/chunk_{i:03d}.mp4",
                    ),
                    art,
                )
            )
        return out

    return _build


@pytest.fixture
def fake_video(tmp_path) -> Path:
    """Return a tiny on-disk file that passes ``Path.exists()`` + ``is_file()``."""
    vid = tmp_path / "ref.mp4"
    vid.write_bytes(b"\x00" * 1024)
    return vid


def _fake_file(state: str = "ACTIVE", name: str = "files/abc123", error=None):
    """Build a MagicMock mimicking ``types.File`` with the given state string.

    The tool reads ``.state.value`` via ``_state_value()``; we mirror that
    shape so a plain string (``"ACTIVE"``) is returned from ``.state.value``.
    """
    f = MagicMock()
    f.name = name
    state_mock = MagicMock()
    state_mock.value = state
    f.state = state_mock
    f.error = error
    return f


@pytest.fixture
def fake_file_factory():
    """Expose ``_fake_file`` so tests can build varying states inline."""
    return _fake_file


def _resp_ok(artifact: dict):
    """Build a ``generate_content`` response with ``finish_reason=STOP``."""
    from google.genai import types

    resp = MagicMock()
    cand = MagicMock()
    cand.finish_reason = types.FinishReason.STOP
    resp.candidates = [cand]
    resp.text = json.dumps(artifact)
    return resp


def _resp_truncated(text: str = ""):
    """Build a response with ``finish_reason=MAX_TOKENS`` (truncated)."""
    from google.genai import types

    resp = MagicMock()
    cand = MagicMock()
    cand.finish_reason = types.FinishReason.MAX_TOKENS
    resp.candidates = [cand]
    resp.text = text
    return resp


def _resp_empty_but_stop(text: str = ""):
    """Finish reason STOP but empty text — second retry trigger."""
    from google.genai import types

    resp = MagicMock()
    cand = MagicMock()
    cand.finish_reason = types.FinishReason.STOP
    resp.candidates = [cand]
    resp.text = text
    return resp


@pytest.fixture
def response_factories():
    """Bundle of response builders — keeps per-test setup concise."""
    return {
        "ok": _resp_ok,
        "truncated": _resp_truncated,
        "empty_stop": _resp_empty_but_stop,
    }


@pytest.fixture
def mock_genai(monkeypatch, valid_artifact):
    """Stub the full ``google-genai`` SDK surface used by the Gemini provider.

    Yields the MagicMock client. Tests can override
    ``.files.get.side_effect``/``return_value`` and
    ``.models.generate_content.side_effect``/``.return_value`` per scenario.

    Defaults:
      * ``upload()`` returns a PROCESSING file
      * ``get()`` side_effect = [PROCESSING, ACTIVE] (one poll then ready)
      * ``delete()`` returns MagicMock
      * ``generate_content()`` returns a STOP response with ``valid_artifact``

    ``time.sleep`` inside the tool module is a no-op; ``time.monotonic`` is
    left alone so tests that need it can monkeypatch individually.
    """
    # Provide a valid key so the auth gate passes; value is never asserted.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    client = MagicMock()
    client.files.upload.return_value = _fake_file(state="PROCESSING")
    client.files.get.side_effect = [
        _fake_file(state="PROCESSING"),
        _fake_file(state="ACTIVE"),
    ]
    client.files.delete.return_value = MagicMock()
    client.models.generate_content.return_value = _resp_ok(valid_artifact)

    # Tool does ``from google import genai`` then ``genai.Client(api_key=...)``.
    # Patch the ``genai`` symbol imported into the tool's module namespace.
    import tools.analysis.gemini_video_analyzer as target

    monkeypatch.setattr(target.genai, "Client", MagicMock(return_value=client))
    monkeypatch.setattr(target.time, "sleep", lambda *a, **kw: None)

    return client


@pytest.fixture
def no_keys(monkeypatch):
    """Reassert the auth-absent environment (autouse already scrubbed).

    Explicit fixture so the intent of ``missing key`` tests is readable.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


# ----------------------------------------------------------------------
# Phase 3 additions — OpenRouter provider mocks
# ----------------------------------------------------------------------


def _openrouter_resp_ok(
    artifact: dict,
    model: str = "google/gemini-3.1-pro-preview",
    cost: float = 0.001,
):
    """Build a /chat/completions response with ``finish_reason='stop'``.

    ``finish_reason`` is a STRING (not enum) — Pitfall 2 guard. OpenRouter
    adds ``cost`` as an extra field on the usage body (Pitfall 5).
    """
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


def _openrouter_resp_truncated(model: str = "google/gemini-3.1-pro-preview"):
    """``finish_reason='length'`` + empty content — the truncation sentinel."""
    resp = MagicMock()
    choice = MagicMock()
    choice.finish_reason = "length"
    choice.message.content = ""
    resp.choices = [choice]
    resp.model = model
    resp.usage = MagicMock(cost=0.0)
    return resp


def _openrouter_resp_empty_stop(model: str = "google/gemini-3.1-pro-preview"):
    """``finish_reason='stop'`` but empty content — second retry trigger."""
    resp = MagicMock()
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = ""
    resp.choices = [choice]
    resp.model = model
    resp.usage = MagicMock(cost=0.0)
    return resp


@pytest.fixture
def openrouter_response_factories():
    """Bundle of OpenRouter response builders (parallels ``response_factories``)."""
    return {
        "ok": _openrouter_resp_ok,
        "truncated": _openrouter_resp_truncated,
        "empty_stop": _openrouter_resp_empty_stop,
    }


@pytest.fixture
def mock_openai(monkeypatch, valid_artifact):
    """Stub the ``openai`` SDK surface used by ``OpenRouterVideoAnalyzer``.

    Yields the MagicMock client. Tests override
    ``.chat.completions.create.return_value`` / ``side_effect`` per scenario.

    Defaults:
      * ``chat.completions.create()`` returns ``_openrouter_resp_ok(valid_artifact)``
        with ``finish_reason='stop'`` (STRING) and ``usage.cost=0.001``.

    The autouse ``_scrub_provider_keys`` has already cleared OPENROUTER_API_KEY,
    so we re-inject a test value here. Tests that want the unset-key path
    should use the ``no_keys`` fixture instead.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    client = MagicMock()
    client.chat.completions.create.return_value = _openrouter_resp_ok(valid_artifact)

    # Tool does ``from openai import OpenAI``; patch the name at the tool's module.
    import tools.analysis.openrouter_video_analyzer as target

    monkeypatch.setattr(target, "OpenAI", MagicMock(return_value=client))
    return client
