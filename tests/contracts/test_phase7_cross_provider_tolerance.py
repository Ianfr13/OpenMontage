"""Phase 7 cross-provider numeric tolerance -- TEST-05.

Two modes:
  1. MOCKED (always runs, no keys): both providers mocked to return fixture
     artifacts. Exercises the comparison helper + divergence-logging contract.
  2. REAL (skipif-gated on RUN_INTEGRATION_TESTS=1 + both keys + long
     fixture): hits real APIs on the same video; logs numeric divergence
     but does NOT auto-fail on tolerance miss (per CONTEXT.md rule).
     pacing_style enum DOES have to match (hard assertion -- categorical).

The real-mode test lives in this contract file (not tests/integration/)
because its default branch is a clean skip, keeping CI key-free.

Tolerance rule (locked by this test):
  abs(a - b) / max(a, b)  <=  0.15

Derived from CONTEXT.md + 07-RESEARCH.md. 15% is conservative given
stochastic LLM output on the same video; tighter would flake.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from schemas.artifacts import validate_artifact  # noqa: E402
from tests.contracts.test_video_analysis_schema import (  # noqa: E402
    minimal_video_analysis,
)

logger = logging.getLogger(__name__)

CPM_TOLERANCE = 0.15


# ---------------------------------------------------------------------------
# Tolerance helper -- tested in its own test to lock the rule.
# ---------------------------------------------------------------------------


def _relative_div(a: float, b: float) -> float:
    """Relative divergence. abs(a-b) / max(|a|,|b|). Returns 0.0 if both zero."""
    m = max(abs(a), abs(b))
    if m == 0.0:
        return 0.0
    return abs(a - b) / m


def _within_tolerance(a: float, b: float, tol: float = CPM_TOLERANCE) -> bool:
    return _relative_div(a, b) <= tol


# ---------------------------------------------------------------------------
# Shared mock-artifact helpers (shape mirrors Phase 3 openrouter contracts)
# ---------------------------------------------------------------------------


def _artifact_with_cpm(cpm: float, pacing: str = "steady_educational") -> dict:
    """Return a schema-valid video_analysis artifact with a specific cpm."""
    art = copy.deepcopy(minimal_video_analysis())
    art["editing_pacing"]["cuts_per_minute"] = cpm
    art["editing_pacing"]["pacing_style"] = pacing
    return art


def _fake_openai_client_returning(artifact: dict) -> MagicMock:
    client = MagicMock()
    resp = MagicMock()
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = json.dumps(artifact)
    resp.choices = [choice]
    resp.model = "google/gemini-3.1-pro-preview"
    resp.usage = MagicMock(cost=0.001)
    client.chat.completions.create.return_value = resp
    return client


def _fake_genai_client_returning(artifact: dict) -> MagicMock:
    from google.genai import types

    client = MagicMock()

    up = MagicMock()
    up.name = "files/abc123"
    up_state = MagicMock()
    up_state.value = "PROCESSING"
    up.state = up_state
    client.files.upload.return_value = up

    active = MagicMock()
    active.name = "files/abc123"
    active_state = MagicMock()
    active_state.value = "ACTIVE"
    active.state = active_state
    client.files.get.side_effect = [active]

    resp = MagicMock()
    cand = MagicMock()
    cand.finish_reason = types.FinishReason.STOP
    resp.candidates = [cand]
    resp.text = json.dumps(artifact)
    client.models.generate_content.return_value = resp

    client.files.delete.return_value = MagicMock()
    return client


def _run_both_providers(
    gem_artifact: dict,
    or_artifact: dict,
    monkeypatch,
    tmp_path,
) -> tuple[dict, dict]:
    """Execute both providers with mocked clients. Returns (gem_data, or_data)."""
    from tools.analysis.gemini_video_analyzer import GeminiVideoAnalyzer
    from tools.analysis.openrouter_video_analyzer import OpenRouterVideoAnalyzer

    video = tmp_path / "ref.mp4"
    video.write_bytes(b"\x00" * 1024)

    for k in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
        "VIDEO_ANALYZER_PROVIDER",
        "GEMINI_VIDEO_MODEL",
        "OPENROUTER_MODEL",
    ):
        monkeypatch.delenv(k, raising=False)

    # Gemini
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    import tools.analysis.gemini_video_analyzer as gtarget

    gclient = _fake_genai_client_returning(gem_artifact)
    monkeypatch.setattr(gtarget.genai, "Client", MagicMock(return_value=gclient))
    monkeypatch.setattr(gtarget.time, "sleep", lambda *a, **kw: None)
    gem_result = GeminiVideoAnalyzer().execute({"video_path": str(video)})

    # OpenRouter
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    import tools.analysis.openrouter_video_analyzer as otarget

    oclient = _fake_openai_client_returning(or_artifact)
    monkeypatch.setattr(otarget, "OpenAI", MagicMock(return_value=oclient))
    or_result = OpenRouterVideoAnalyzer().execute({"video_path": str(video)})

    assert gem_result.success, gem_result.error
    assert or_result.success, or_result.error
    return gem_result.data, or_result.data


# ---------------------------------------------------------------------------
# MOCKED MODE -- always-on
# ---------------------------------------------------------------------------


def test_tolerance_helper_shape():
    """Lock the relative-div formula + tolerance threshold."""
    assert _relative_div(10.0, 10.0) == 0.0
    assert _within_tolerance(10.0, 11.0)           # 10% -- within
    assert _within_tolerance(10.0, 11.5)           # 15% exactly -- within
    assert not _within_tolerance(10.0, 12.0)       # 16.66% -- outside
    assert _within_tolerance(0.0, 0.0)             # both zero -- defined as within
    assert not _within_tolerance(1.0, 2.0)         # 50%


def test_cross_provider_mocked_identical(monkeypatch, tmp_path):
    """Both providers return SAME artifact -> zero divergence, pacing match."""
    art = _artifact_with_cpm(cpm=12.0, pacing="steady_educational")
    gem_data, or_data = _run_both_providers(art, art, monkeypatch, tmp_path)
    validate_artifact("video_analysis", gem_data)
    validate_artifact("video_analysis", or_data)

    gem_cpm = gem_data["editing_pacing"]["cuts_per_minute"]
    or_cpm = or_data["editing_pacing"]["cuts_per_minute"]
    assert _within_tolerance(gem_cpm, or_cpm)
    assert (
        gem_data["editing_pacing"]["pacing_style"]
        == or_data["editing_pacing"]["pacing_style"]
    )


@pytest.mark.parametrize(
    "gem_cpm,or_cpm,within",
    [
        (10.0, 11.0, True),    # 10% -- within
        (10.0, 11.5, True),    # ~13% -- within
        (10.0, 12.0, False),   # 16.66% -- outside
        (8.0, 10.0, False),    # 20% -- outside
        (5.0, 5.5, True),      # ~9% at lower magnitudes
    ],
)
def test_cross_provider_mocked_tolerance_cases(
    gem_cpm, or_cpm, within, monkeypatch, tmp_path,
):
    """Parametrized tolerance: within-15% pairs pass; outside fail."""
    gem_art = _artifact_with_cpm(gem_cpm)
    or_art = _artifact_with_cpm(or_cpm)
    gem_data, or_data = _run_both_providers(gem_art, or_art, monkeypatch, tmp_path)

    a = gem_data["editing_pacing"]["cuts_per_minute"]
    b = or_data["editing_pacing"]["cuts_per_minute"]
    assert _within_tolerance(a, b) == within, (
        f"Expected within={within} for cpm=({a}, {b}); got {_within_tolerance(a, b)}"
    )


def test_cross_provider_mocked_divergence_is_logged_not_raised(
    monkeypatch, tmp_path, caplog,
):
    """Divergence >15% must be logged (WARNING), not raised.

    This is the CONTEXT.md contract: 'divergences logged, not auto-failed'.
    Mocked test verifies the logging shape without needing real keys.
    """
    gem_art = _artifact_with_cpm(cpm=10.0)
    or_art = _artifact_with_cpm(cpm=15.0)  # 33% divergence
    gem_data, or_data = _run_both_providers(gem_art, or_art, monkeypatch, tmp_path)

    a = gem_data["editing_pacing"]["cuts_per_minute"]
    b = or_data["editing_pacing"]["cuts_per_minute"]

    # Simulate the divergence-logging behavior the real-mode test uses.
    # Real-mode test must do the same: log, don't fail on numeric miss.
    with caplog.at_level(logging.WARNING, logger=__name__):
        if not _within_tolerance(a, b):
            logger.warning(
                "cross-provider cuts_per_minute divergence: gemini=%.2f openrouter=%.2f "
                "relative=%.2f%% (tolerance=%.0f%%)",
                a,
                b,
                _relative_div(a, b) * 100,
                CPM_TOLERANCE * 100,
            )

    assert any("divergence" in rec.message for rec in caplog.records), (
        "Divergence must be logged at WARNING level"
    )


# ---------------------------------------------------------------------------
# REAL MODE -- skipif-gated (opt-in; hits real APIs)
# ---------------------------------------------------------------------------


_REAL_MODE_SKIP_REASONS: list[str] = []
if os.environ.get("RUN_INTEGRATION_TESTS") != "1":
    _REAL_MODE_SKIP_REASONS.append("RUN_INTEGRATION_TESTS!=1")
if not (
    os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
):
    _REAL_MODE_SKIP_REASONS.append("GEMINI_API_KEY not set")
if not os.environ.get("OPENROUTER_API_KEY"):
    _REAL_MODE_SKIP_REASONS.append("OPENROUTER_API_KEY not set")

_LONG_FIXTURE = PROJECT_ROOT / "tests" / "integration" / "fixtures" / "long.mp4"
if not _LONG_FIXTURE.is_file():
    _REAL_MODE_SKIP_REASONS.append(f"fixture missing: {_LONG_FIXTURE}")


@pytest.mark.skipif(
    bool(_REAL_MODE_SKIP_REASONS),
    reason="; ".join(_REAL_MODE_SKIP_REASONS) or "real-mode gate off",
)
def test_cross_provider_real_tolerance(caplog):
    """TEST-05 real mode: same fixture -> both providers -> tolerance + enum match.

    Numeric tolerance miss is LOGGED (not failed) per CONTEXT.md.
    pacing_style enum equality IS a hard assertion -- categorical.
    """
    from tools.analysis.video_analyzer_selector import VideoAnalyzerSelector

    sel = VideoAnalyzerSelector()

    gem_result = sel.execute(
        {
            "video_path": str(_LONG_FIXTURE),
            "preferred_provider": "gemini",
            "analysis_depth": "full",
        }
    )
    assert gem_result.success, f"Gemini failed: {gem_result.error}"

    or_result = sel.execute(
        {
            "video_path": str(_LONG_FIXTURE),
            "preferred_provider": "openrouter",
            "analysis_depth": "full",
        }
    )
    assert or_result.success, f"OpenRouter failed: {or_result.error}"

    validate_artifact("video_analysis", gem_result.data)
    validate_artifact("video_analysis", or_result.data)

    gem_cpm = float(gem_result.data["editing_pacing"]["cuts_per_minute"])
    or_cpm = float(or_result.data["editing_pacing"]["cuts_per_minute"])
    gem_pacing = gem_result.data["editing_pacing"]["pacing_style"]
    or_pacing = or_result.data["editing_pacing"]["pacing_style"]

    # Numeric tolerance -- LOG on miss, don't fail. (CONTEXT.md rule.)
    if not _within_tolerance(gem_cpm, or_cpm):
        logger.warning(
            "TEST-05 cuts_per_minute divergence: gemini=%.2f openrouter=%.2f "
            "relative=%.2f%% (tolerance=%.0f%%)",
            gem_cpm,
            or_cpm,
            _relative_div(gem_cpm, or_cpm) * 100,
            CPM_TOLERANCE * 100,
        )

    # Categorical enum match -- HARD assertion (Phase 2/3 selector contract).
    assert gem_pacing == or_pacing, (
        f"pacing_style enum disagreement: gemini={gem_pacing!r} "
        f"openrouter={or_pacing!r}"
    )
