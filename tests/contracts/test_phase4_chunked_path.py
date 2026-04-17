"""Phase 4 end-to-end contract test — full chunked path.

Exercises ``lib.chunked_analyzer.analyze_chunked`` with:
* split_video mocked (no FFmpeg/ffprobe required — offline-safe)
* StubProvider (no API key, no network — deterministic schema-valid artifact)
* Real ``merge_analyses`` (the actual Phase 4 merger)
* Real ``validate_artifact`` (the canonical schema gate from Phase 1)

Covers CHUNK-03 (orchestrator) + CHUNK-06 (cost tracker) end-to-end.

Integration tests with RUN_INTEGRATION_TESTS=1 + real FFmpeg + real provider
live in Phase 7; these contract tests are the offline gate.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.chunked_analyzer import analyze_chunked  # noqa: E402
from lib.config_model import BudgetMode  # noqa: E402
from lib.video_chunker import Chunk  # noqa: E402
from schemas.artifacts import validate_artifact  # noqa: E402
from tools.base_tool import ToolResult  # noqa: E402
from tools.cost_tracker import CostTracker  # noqa: E402

# Import the Phase 1 canonical fixture (single source of truth)
from tests.contracts.test_video_analysis_schema import (  # noqa: E402
    minimal_video_analysis,
)


class StubProvider:
    """Offline provider: returns schema-valid artifact with cost/model stamped."""

    name = "stub_video_analyzer"
    # chunking_metadata.provider enum in schema is {"gemini","openrouter"};
    # use "gemini" so the merged artifact validates end-to-end.
    provider = "gemini"
    capability = "video_analysis"

    def __init__(self, cost_usd: float = 0.05, model: str = "stub-model-v1"):
        self._cost = cost_usd
        self._model = model
        self.call_count = 0

    def execute(self, inputs):
        self.call_count += 1
        return ToolResult(
            success=True,
            data=copy.deepcopy(minimal_video_analysis()),
            cost_usd=self._cost,
            model=self._model,
        )


def _fake_chunks_multi() -> list[Chunk]:
    """Two chunks totaling 480s (8 min) — forces the multi-chunk merger path."""
    return [
        Chunk(start_global=0.0, end_global=300.0, local_path="/tmp/fake_chunk_000.mp4"),
        Chunk(start_global=300.0, end_global=480.0, local_path="/tmp/fake_chunk_001.mp4"),
    ]


def _fake_chunks_single_bypass(orig_path: str) -> list[Chunk]:
    """Single chunk pointing at the original path — exercises bypass sentinel."""
    return [Chunk(start_global=0.0, end_global=120.0, local_path=orig_path)]


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


class TestPhase4ChunkedPath:
    def test_chunked_path_end_to_end(self, tmp_path):
        """Full split→analyze→merge→validate pipeline with 2 chunks."""
        video = str(tmp_path / "ref.mp4")
        provider = StubProvider()

        with patch(
            "lib.chunked_analyzer.split_video", return_value=_fake_chunks_multi()
        ), patch("lib.chunked_analyzer.cleanup_chunks"):
            merged = analyze_chunked(video, provider)

        # Schema gate — the ultimate contract
        validate_artifact("video_analysis", merged)

        assert merged["version"] == "2.0"
        meta = merged["chunking_metadata"]
        assert meta["chunk_count"] == 2
        # 2 chunks * avg 240s = 480s total
        assert meta["total_duration_s"] == pytest.approx(480.0)
        # Provider propagated from provider_tool.provider
        assert meta["provider"] == "gemini"
        # Per-chunk trace entries with cost + provider
        assert len(meta["per_chunk"]) == 2
        for i, entry in enumerate(meta["per_chunk"]):
            assert entry["index"] == i
            assert entry["cost_usd"] == pytest.approx(0.05)
            assert entry["provider"] == "stub-model-v1"

        # Provider saw two .execute() calls, one per chunk
        assert provider.call_count == 2

        # Core canonical fields present
        assert "editing_pacing" in merged
        assert merged["editing_pacing"]["cuts_per_minute"] >= 0
        assert "audio" in merged
        assert "visual_style" in merged
        assert "narrative" in merged

    def test_chunked_path_cost_tracker_integrated(self, tmp_path):
        """Real CostTracker observes two reconciled entries after the run."""
        video = str(tmp_path / "ref.mp4")
        provider = StubProvider(cost_usd=0.042)
        tracker = CostTracker(
            budget_total_usd=10.0,
            mode=BudgetMode.OBSERVE,  # observe mode bypasses approval gates
        )

        with patch(
            "lib.chunked_analyzer.split_video", return_value=_fake_chunks_multi()
        ), patch("lib.chunked_analyzer.cleanup_chunks"):
            merged = analyze_chunked(video, provider, cost_tracker=tracker)

        # Budget was spent (two chunks @ $0.042 each)
        assert tracker.budget_spent_usd == pytest.approx(0.084, abs=1e-4)

        # Two reconciled entries exist; tool + operation strings set correctly
        reconciled = [
            e for e in tracker.entries if e["status"] == "completed"
        ]
        assert len(reconciled) == 2
        for entry in reconciled:
            assert entry["tool"] == "stub_video_analyzer"
            assert "chunked_analysis" in entry["operation"]
            assert "ref.mp4" in entry["operation"]
            assert entry["actual_usd"] == pytest.approx(0.042)

        # Merged artifact still validates
        validate_artifact("video_analysis", merged)

    def test_chunked_path_cleanup_called(self, tmp_path):
        """cleanup_chunks fires exactly once after the run (try/finally)."""
        video = str(tmp_path / "ref.mp4")

        with patch(
            "lib.chunked_analyzer.split_video", return_value=_fake_chunks_multi()
        ), patch("lib.chunked_analyzer.cleanup_chunks") as cleanup:
            analyze_chunked(video, StubProvider())

        cleanup.assert_called_once()
        # Original path forwarded to cleanup so the sentinel guard works
        args, kwargs = cleanup.call_args
        orig = kwargs.get("original_path") or (args[1] if len(args) > 1 else None)
        assert orig == video

    def test_chunked_path_bypass_single_chunk(self, tmp_path):
        """≤5 min input → single bypass chunk → merger pass-through → valid artifact."""
        video = str(tmp_path / "short.mp4")
        provider = StubProvider()

        with patch(
            "lib.chunked_analyzer.split_video",
            return_value=_fake_chunks_single_bypass(video),
        ), patch("lib.chunked_analyzer.cleanup_chunks"):
            merged = analyze_chunked(video, provider)

        validate_artifact("video_analysis", merged)
        assert merged["chunking_metadata"]["chunk_count"] == 1
        # Pass-through strips internal hint keys
        assert "_cost_usd" not in merged
        assert "_provider_used" not in merged
        # Single provider call (one chunk)
        assert provider.call_count == 1
