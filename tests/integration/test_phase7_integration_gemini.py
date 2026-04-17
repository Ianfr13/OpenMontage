"""Phase 7 integration tests — Gemini provider (real API, TEST-02).

Gated by RUN_INTEGRATION_TESTS=1 + GEMINI_API_KEY + fixture video presence.
Skips cleanly (never fails) if any gate is off. See tests/integration/README.md.

Covers 3 fixture tiers:
  - short   (< 2 min):  single-call path, no chunking_metadata.
  - medium  (3-5 min):  single-call path at the chunking boundary.
  - long    (> 5 min):  triggers Phase 4 chunked_analyzer merge path.

Assertions target SHAPE (schema validity, top-level keys, chunking metadata
presence). Real-model numeric outputs are non-deterministic across runs, so
no test asserts specific cuts_per_minute / shot_type values.
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
    require_gemini_key,
    require_integration_enabled,
)

# Module-level marker — applies to EVERY test function in this file.
# Filter with `pytest -m integration` / exclude with `pytest -m 'not integration'`.
pytestmark = pytest.mark.integration


def _run_gemini_selector(video_path: Path) -> dict:
    """Shared helper: run the capability selector with preferred_provider='gemini'.

    Requires the Gemini key; uses the selector (not the raw tool) to exercise
    the Phase 2 routing path end-to-end. Returns ToolResult.data (the canonical
    video_analysis artifact).
    """
    require_integration_enabled()
    require_gemini_key()

    from tools.analysis.video_analyzer_selector import VideoAnalyzerSelector

    sel = VideoAnalyzerSelector()
    result = sel.execute({
        "video_path": str(video_path),
        "preferred_provider": "gemini",
        "analysis_depth": "full",
    })
    assert result.success, f"Selector failed: {result.error}"
    assert isinstance(result.data, dict)
    return result.data


@pytest.mark.parametrize("fixture_video", ["short"], indirect=True)
def test_short_video_single_call(fixture_video: Path):
    """TEST-02: short (<2min) fixture -> valid canonical artifact, no chunking."""
    data = _run_gemini_selector(fixture_video)
    validate_artifact("video_analysis", data)
    # Short fixture is below the 5-min threshold — no chunking_metadata expected.
    assert "chunking_metadata" not in data, (
        "Short video should use single-call path; got chunking_metadata"
    )
    # Top-level canonical keys present.
    for key in ("version", "source", "editing_pacing", "audio",
                "visual_style", "narrative"):
        assert key in data, f"Missing canonical key: {key}"


@pytest.mark.parametrize("fixture_video", ["medium"], indirect=True)
def test_medium_video_single_call(fixture_video: Path):
    """TEST-02: medium (3-5min) fixture -> valid artifact, still single-call.

    Boundary test — 3-5 min is under the 5-min (300s) threshold so chunking
    stays off. Useful for catching an accidental tightening of the threshold.
    """
    data = _run_gemini_selector(fixture_video)
    validate_artifact("video_analysis", data)
    assert "chunking_metadata" not in data, (
        "Medium video should stay on single-call path; got chunking_metadata"
    )


@pytest.mark.parametrize("fixture_video", ["long"], indirect=True)
def test_long_video_chunked(fixture_video: Path):
    """TEST-02: long (>5min) fixture -> merged artifact with chunking_metadata.

    Exercises Phase 4's ``analyze_chunked`` + ``analysis_merger`` path through
    the selector. Asserts chunking_metadata exists and records >=2 chunks (a
    >5min video MUST chunk at the default 5-min boundary).
    """
    data = _run_gemini_selector(fixture_video)
    validate_artifact("video_analysis", data)
    cm = data.get("chunking_metadata")
    assert cm is not None, "Long video must carry chunking_metadata"
    assert isinstance(cm, dict)
    chunk_count = cm.get("chunk_count")
    assert isinstance(chunk_count, int) and chunk_count >= 2, (
        f"Long video must produce >=2 chunks; got chunk_count={chunk_count}"
    )
