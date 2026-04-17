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
