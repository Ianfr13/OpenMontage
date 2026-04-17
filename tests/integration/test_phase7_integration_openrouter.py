"""Phase 7 integration tests — OpenRouter provider (real API, TEST-02).

Gated by RUN_INTEGRATION_TESTS=1 + OPENROUTER_API_KEY + fixture video
presence. Skips cleanly (never fails) if any gate is off.
See tests/integration/README.md.

Covers the same 3 fixture tiers as the Gemini file for apples-to-apples
cross-provider comparison. Uses the base64-inline encoding path (Phase 3
contract — OpenRouter does not accept URLs for Gemini-routed models).

Assertions target SHAPE (schema validity, top-level keys, chunking
metadata). Real-model output is non-deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from schemas.artifacts import validate_artifact  # noqa: E402
from tests.integration.conftest import (  # noqa: E402
    require_integration_enabled,
    require_openrouter_key,
)

# Module-level marker — applies to every test function here.
pytestmark = pytest.mark.integration


def _run_openrouter_selector(video_path: Path) -> dict:
    """Shared helper: run the capability selector with preferred_provider='openrouter'.

    Uses the selector (not the raw tool) to exercise Phase 2/3 routing end to
    end. Requires OPENROUTER_API_KEY + the RUN_INTEGRATION_TESTS gate on.
    Returns ToolResult.data (the canonical video_analysis artifact).
    """
    require_integration_enabled()
    require_openrouter_key()

    from tools.analysis.video_analyzer_selector import VideoAnalyzerSelector

    sel = VideoAnalyzerSelector()
    result = sel.execute({
        "video_path": str(video_path),
        "preferred_provider": "openrouter",
        "analysis_depth": "full",
    })
    assert result.success, f"Selector failed: {result.error}"
    assert isinstance(result.data, dict)
    return result.data


@pytest.mark.parametrize("fixture_video", ["short"], indirect=True)
def test_short_video_single_call(fixture_video: Path):
    """TEST-02: short (<2min) via OpenRouter -> valid canonical artifact, no chunking."""
    data = _run_openrouter_selector(fixture_video)
    validate_artifact("video_analysis", data)
    assert "chunking_metadata" not in data, (
        "Short video should use single-call path; got chunking_metadata"
    )
    for key in ("version", "source", "editing_pacing", "audio",
                "visual_style", "narrative"):
        assert key in data, f"Missing canonical key: {key}"


@pytest.mark.parametrize("fixture_video", ["medium"], indirect=True)
def test_medium_video_single_call(fixture_video: Path):
    """TEST-02: medium (3-5min) via OpenRouter -> single-call, no chunking.

    Boundary — 3-5 min sits under the 5-min chunking threshold so the
    single-call path still applies.
    """
    data = _run_openrouter_selector(fixture_video)
    validate_artifact("video_analysis", data)
    assert "chunking_metadata" not in data, (
        "Medium video should stay on single-call path; got chunking_metadata"
    )


@pytest.mark.parametrize("fixture_video", ["long"], indirect=True)
def test_long_video_chunked(fixture_video: Path):
    """TEST-02: long (>5min) via OpenRouter -> chunked merged artifact.

    Each chunk is base64-encoded inline per Phase 3's OR-03 contract. The
    merger (Phase 4) produces the single canonical artifact under test.
    Asserts chunking_metadata present and chunk_count >= 2.
    """
    data = _run_openrouter_selector(fixture_video)
    validate_artifact("video_analysis", data)
    cm = data.get("chunking_metadata")
    assert cm is not None, "Long video must carry chunking_metadata"
    assert isinstance(cm, dict)
    chunk_count = cm.get("chunk_count")
    assert isinstance(chunk_count, int) and chunk_count >= 2, (
        f"Long video must produce >=2 chunks; got chunk_count={chunk_count}"
    )
