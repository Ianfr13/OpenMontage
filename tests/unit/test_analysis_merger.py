"""Unit tests for ``lib/analysis_merger.py`` — the per-dimension aggregator.

Every test ends by asserting the merged artifact validates against the
canonical ``video_analysis`` schema via ``validate_artifact`` — Pitfall 2.

Fixtures: ``fake_video_chunks`` (conftest.py) generates schema-valid
per-chunk artifacts with targeted overrides so merger math is deterministic.
"""

from __future__ import annotations

import copy
import logging
from unittest.mock import patch

import pytest

from lib.analysis_merger import (
    _concat_freetext,
    _top_n_by_frequency,
    _union_dedup,
    _weighted_avg,
    _weighted_majority,
    _worst_confidence,
    merge_analyses,
)
from lib.video_chunker import Chunk
from schemas.artifacts import validate_artifact


# ----------------------------------------------------------------------
# Primitive helpers
# ----------------------------------------------------------------------


class TestPrimitives:
    def test_weighted_avg_basic(self):
        # (10*1 + 20*3) / (1+3) = 70/4 = 17.5
        assert _weighted_avg([(10.0, 1.0), (20.0, 3.0)]) == pytest.approx(17.5)

    def test_weighted_avg_zero_weights(self):
        """No div-by-zero; returns 0.0 when all weights are zero."""
        assert _weighted_avg([(5.0, 0.0), (10.0, 0.0)]) == 0.0

    def test_weighted_avg_empty(self):
        assert _weighted_avg([]) == 0.0

    def test_weighted_majority_basic(self):
        # "b" has weight 5 vs "a" with weight 3 → "b"
        assert _weighted_majority([("a", 2.0), ("b", 5.0), ("a", 1.0)]) == "b"

    def test_weighted_majority_ignores_none(self):
        """None entries contribute no weight even with huge w values."""
        assert _weighted_majority([(None, 100.0), ("x", 1.0)]) == "x"

    def test_weighted_majority_all_none_returns_none(self):
        assert _weighted_majority([(None, 1.0), (None, 5.0)]) is None

    def test_union_dedup_preserves_order(self):
        assert _union_dedup([["a", "b"], ["b", "c", "a"]]) == ["a", "b", "c"]

    def test_union_dedup_empty(self):
        assert _union_dedup([]) == []

    def test_top_n_by_frequency(self):
        """Most frequent wins; tie broken by first-seen."""
        result = _top_n_by_frequency(
            [["#fff", "#000"], ["#fff", "#111"], ["#000"]],
            n=2,
        )
        assert result == ["#fff", "#000"]

    def test_top_n_by_frequency_cap(self):
        """Cap at N when more distinct values than N."""
        result = _top_n_by_frequency(
            [["#a", "#b", "#c", "#d", "#e", "#f", "#g"]],
            n=5,
        )
        assert len(result) == 5

    def test_worst_confidence_low_wins(self):
        assert _worst_confidence(["high", "low", "medium"]) == "low"

    def test_worst_confidence_all_high(self):
        assert _worst_confidence(["high", "high"]) == "high"

    def test_worst_confidence_mixed_no_low(self):
        assert _worst_confidence(["high", "medium"]) == "medium"

    def test_worst_confidence_empty_returns_high(self):
        """Empty confidence list → default to 'high' (no pessimism signal)."""
        assert _worst_confidence([]) == "high"

    def test_concat_freetext_skips_empties(self):
        result = _concat_freetext(
            ["first", None, "third"],
            ["chunk 1/3", "chunk 2/3", "chunk 3/3"],
        )
        assert "[chunk 1/3] first" in result
        assert "[chunk 3/3] third" in result
        assert "chunk 2/3" not in result


# ----------------------------------------------------------------------
# N=1 single-chunk pass-through
# ----------------------------------------------------------------------


class TestSingleChunkPassThrough:
    def test_single_chunk_passthrough(self, fake_video_chunks):
        chunks = fake_video_chunks(n=1)
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["chunking_metadata"]["chunk_count"] == 1
        # Should pass schema validation
        validate_artifact("video_analysis", merged)

    def test_single_chunk_source_duration_unchanged(self, fake_video_chunks):
        chunks = fake_video_chunks(n=1)
        # Set source.duration_seconds explicitly
        chunks[0][1]["source"]["duration_seconds"] = 120.0
        # Override chunk end_global to match
        new_chunk = chunks[0][0]._replace(start_global=0.0, end_global=120.0)
        chunks = [(new_chunk, chunks[0][1])]
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["source"]["duration_seconds"] == pytest.approx(120.0)

    def test_single_chunk_chunking_metadata_shape(self, fake_video_chunks):
        chunks = fake_video_chunks(n=1, chunk_seconds=180.0)
        # Stamp cost hint
        chunks[0][1]["_cost_usd"] = 0.42
        merged = merge_analyses(chunks, provider="gemini")
        meta = merged["chunking_metadata"]
        assert meta["chunk_count"] == 1
        assert meta["total_duration_s"] == pytest.approx(180.0)
        assert meta["provider"] == "gemini"
        assert len(meta["per_chunk"]) == 1
        entry = meta["per_chunk"][0]
        assert entry["index"] == 0
        assert entry["start_s"] == 0.0
        assert entry["end_s"] == pytest.approx(180.0)
        assert entry["cost_usd"] == pytest.approx(0.42)
        assert entry["provider"] == "gemini"

    def test_single_chunk_deep_copied(self, fake_video_chunks):
        """Merger must not mutate the input artifact."""
        chunks = fake_video_chunks(n=1)
        original_pacing = chunks[0][1]["editing_pacing"]["pacing_style"]
        merged = merge_analyses(chunks, provider="gemini")
        merged["editing_pacing"]["pacing_style"] = "rapid_fire"
        # Input must remain untouched
        assert chunks[0][1]["editing_pacing"]["pacing_style"] == original_pacing


# ----------------------------------------------------------------------
# Fixture sanity
# ----------------------------------------------------------------------


class TestFixture:
    def test_fake_video_chunks_fixture_validates(self, fake_video_chunks):
        """Each per-chunk artifact must pass schema validation on its own."""
        chunks = fake_video_chunks(n=3)
        assert len(chunks) == 3
        for _chunk, art in chunks:
            validate_artifact("video_analysis", art)

    def test_fake_video_chunks_monotonic_timeline(self, fake_video_chunks):
        chunks = fake_video_chunks(n=4, chunk_seconds=150.0)
        prev_end = 0.0
        for c, _ in chunks:
            assert c.start_global == pytest.approx(prev_end)
            assert c.end_global == pytest.approx(c.start_global + 150.0)
            prev_end = c.end_global

    def test_fake_video_chunks_applies_overrides(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"editing_pacing": {"cuts_per_minute": 42.0}},
                {"editing_pacing": {"cuts_per_minute": 7.0}},
            ],
        )
        assert chunks[0][1]["editing_pacing"]["cuts_per_minute"] == 42.0
        assert chunks[1][1]["editing_pacing"]["cuts_per_minute"] == 7.0


# ----------------------------------------------------------------------
# Error paths
# ----------------------------------------------------------------------


class TestErrors:
    def test_empty_chunks_raises(self):
        with pytest.raises(ValueError, match="≥1 chunk"):
            merge_analyses([], provider="gemini")
