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


# ----------------------------------------------------------------------
# Multi-chunk: editing_pacing
# ----------------------------------------------------------------------


class TestEditingPacing:
    def test_total_shots_sum(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"editing_pacing": {"total_shots": 5}},
                {"editing_pacing": {"total_shots": 7}},
                {"editing_pacing": {"total_shots": 9}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["editing_pacing"]["total_shots"] == 21
        validate_artifact("video_analysis", merged)

    def test_cuts_per_minute_weighted_avg_equal_weights(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            chunk_seconds=300.0,
            overrides=[
                {"editing_pacing": {"cuts_per_minute": 6.0}},
                {"editing_pacing": {"cuts_per_minute": 3.0}},
                {"editing_pacing": {"cuts_per_minute": 9.0}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        # Equal weights → plain avg = 6.0
        assert merged["editing_pacing"]["cuts_per_minute"] == pytest.approx(6.0)
        validate_artifact("video_analysis", merged)

    def test_cuts_per_minute_unequal_weights(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"editing_pacing": {"cuts_per_minute": 10.0}},
                {"editing_pacing": {"cuts_per_minute": 5.0}},
            ],
        )
        # Manually override chunk durations to 200 / 400
        c0, art0 = chunks[0]
        c1, art1 = chunks[1]
        c0 = c0._replace(start_global=0.0, end_global=200.0)
        c1 = c1._replace(start_global=200.0, end_global=600.0)
        chunks = [(c0, art0), (c1, art1)]
        merged = merge_analyses(chunks, provider="gemini")
        # (10*200 + 5*400) / 600 = 4000/600 = 6.667
        assert merged["editing_pacing"]["cuts_per_minute"] == pytest.approx(6.6667, rel=1e-3)

    def test_pacing_style_weighted_majority(self, fake_video_chunks):
        # chunks 1+2 rapid_fire at 300s each; chunk 3 dynamic_social at 600s
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"editing_pacing": {"pacing_style": "rapid_fire"}},
                {"editing_pacing": {"pacing_style": "rapid_fire"}},
                {"editing_pacing": {"pacing_style": "dynamic_social"}},
            ],
        )
        c2, a2 = chunks[2]
        c2 = c2._replace(start_global=600.0, end_global=1200.0)
        chunks[2] = (c2, a2)
        merged = merge_analyses(chunks, provider="gemini")
        # rapid_fire: 300+300=600, dynamic_social: 600 → tie; rapid_fire inserts first → wins
        # Now double dynamic_social weight by extending:
        c2 = c2._replace(end_global=1500.0)
        chunks[2] = (c2, a2)
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["editing_pacing"]["pacing_style"] == "dynamic_social"

    def test_shortest_shot_min(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"editing_pacing": {"shortest_shot_seconds": 2.0}},
                {"editing_pacing": {"shortest_shot_seconds": 0.5}},
                {"editing_pacing": {"shortest_shot_seconds": 3.0}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["editing_pacing"]["shortest_shot_seconds"] == pytest.approx(0.5)

    def test_longest_shot_max(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"editing_pacing": {"longest_shot_seconds": 10.0}},
                {"editing_pacing": {"longest_shot_seconds": 25.0}},
                {"editing_pacing": {"longest_shot_seconds": 15.0}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["editing_pacing"]["longest_shot_seconds"] == pytest.approx(25.0)

    def test_shot_type_distribution_renormalized(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {
                    "editing_pacing": {
                        "shot_type_distribution": {
                            "talking_head": 0.6,
                            "b_roll": 0.2,
                            "text_card": 0.1,
                            "animation": 0.1,
                        }
                    }
                },
                {
                    "editing_pacing": {
                        "shot_type_distribution": {
                            "talking_head": 0.2,
                            "b_roll": 0.5,
                            "text_card": 0.2,
                            "animation": 0.1,
                        }
                    }
                },
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        dist = merged["editing_pacing"]["shot_type_distribution"]
        assert sum(dist.values()) == pytest.approx(1.0, abs=0.01)
        validate_artifact("video_analysis", merged)

    def test_transition_types_union_dedup(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"editing_pacing": {"transition_types": ["cut", "dissolve"]}},
                {"editing_pacing": {"transition_types": ["cut", "fade_black"]}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["editing_pacing"]["transition_types"] == ["cut", "dissolve", "fade_black"]

    def test_energy_arc_concat_with_shift(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            chunk_seconds=300.0,
            overrides=[
                {
                    "editing_pacing": {
                        "energy_arc": [{"timestamp_s": 10.0, "energy_level": "low"}]
                    }
                },
                {
                    "editing_pacing": {
                        "energy_arc": [{"timestamp_s": 50.0, "energy_level": "peak"}]
                    }
                },
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        arc = merged["editing_pacing"]["energy_arc"]
        assert len(arc) == 2
        assert arc[0]["timestamp_s"] == pytest.approx(10.0)  # chunk 0, start=0
        assert arc[1]["timestamp_s"] == pytest.approx(350.0)  # chunk 1, start=300
        assert arc[0]["energy_level"] == "low"
        assert arc[1]["energy_level"] == "peak"


# ----------------------------------------------------------------------
# Multi-chunk: audio
# ----------------------------------------------------------------------


class TestAudio:
    def test_has_narration_or(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"audio": {"has_narration": False}},
                {"audio": {"has_narration": True}},
                {"audio": {"has_narration": False}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["audio"]["has_narration"] is True
        validate_artifact("video_analysis", merged)

    def test_has_music_or(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"audio": {"has_music": False}},
                {"audio": {"has_music": True}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["audio"]["has_music"] is True

    def test_narration_wpm_only_narrating_chunks(self, fake_video_chunks):
        # chunk1: narration, 150 wpm, 200s; chunk2: no narration, 400s
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"audio": {"has_narration": True, "narration_wpm": 150.0}},
                {"audio": {"has_narration": False, "narration_wpm": 9999.0}},
            ],
        )
        # Override chunk durations
        c0, a0 = chunks[0]
        c1, a1 = chunks[1]
        c0 = c0._replace(end_global=200.0)
        c1 = c1._replace(start_global=200.0, end_global=600.0)
        chunks = [(c0, a0), (c1, a1)]
        merged = merge_analyses(chunks, provider="gemini")
        # Only chunk 0 narrated → wpm = 150
        assert merged["audio"]["narration_wpm"] == pytest.approx(150.0)

    def test_music_tempo_all_null(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"audio": {"music_tempo_bpm": None}},
                {"audio": {"music_tempo_bpm": None}},
                {"audio": {"music_tempo_bpm": None}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["audio"]["music_tempo_bpm"] is None

    def test_music_tempo_mixed_null(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"audio": {"music_tempo_bpm": None}},
                {"audio": {"music_tempo_bpm": 120.0}},
                {"audio": {"music_tempo_bpm": 130.0}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        # Equal weights → avg of (120,130) = 125
        assert merged["audio"]["music_tempo_bpm"] == pytest.approx(125.0)

    def test_voice_music_mix_majority(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"audio": {"voice_music_mix": "narration_dominant"}},
                {"audio": {"voice_music_mix": "music_dominant"}},
                {"audio": {"voice_music_mix": "music_dominant"}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["audio"]["voice_music_mix"] == "music_dominant"

    def test_tts_voice_profile_first_chunk(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"audio": {"suggested_tts_voice_profile": "deep_warm_male"}},
                {"audio": {"suggested_tts_voice_profile": "other_value"}},
                {"audio": {"suggested_tts_voice_profile": "yet_another"}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["audio"]["suggested_tts_voice_profile"] == "deep_warm_male"


# ----------------------------------------------------------------------
# Multi-chunk: visual_style
# ----------------------------------------------------------------------


class TestVisualStyle:
    def test_color_palette_capped_at_5(self, fake_video_chunks):
        # 8 distinct primary colors → merged capped at 5
        palettes = [
            {"visual_style": {"color_palette": {"primary": ["#001", "#002", "#003"]}}},
            {"visual_style": {"color_palette": {"primary": ["#004", "#005", "#006"]}}},
            {"visual_style": {"color_palette": {"primary": ["#007", "#008"]}}},
        ]
        chunks = fake_video_chunks(n=3, overrides=palettes)
        merged = merge_analyses(chunks, provider="gemini")
        assert len(merged["visual_style"]["color_palette"]["primary"]) == 5
        validate_artifact("video_analysis", merged)

    def test_aspect_ratio_first_chunk_wins_and_warns(self, fake_video_chunks, caplog):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"visual_style": {"aspect_ratio": "16:9"}},
                {"visual_style": {"aspect_ratio": "9:16"}},
            ],
        )
        with caplog.at_level(logging.WARNING, logger="lib.analysis_merger"):
            merged = merge_analyses(chunks, provider="gemini")
        assert merged["visual_style"]["aspect_ratio"] == "16:9"
        warning_msgs = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any("aspect_ratio" in m for m in warning_msgs)

    def test_typography_style_first_chunk(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"visual_style": {"typography_style": "sans_modern_bold"}},
                {"visual_style": {"typography_style": "serif_classic"}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["visual_style"]["typography_style"] == "sans_modern_bold"

    def test_production_quality_majority(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"visual_style": {"production_quality": "professional"}},
                {"visual_style": {"production_quality": "prosumer"}},
                {"visual_style": {"production_quality": "professional"}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["visual_style"]["production_quality"] == "professional"

    def test_dominant_colors_hex_top_5(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {
                    "visual_style": {
                        "dominant_colors_hex": ["#A", "#B", "#A", "#C"]
                    }
                },
                {"visual_style": {"dominant_colors_hex": ["#A", "#D", "#E"]}},
                {"visual_style": {"dominant_colors_hex": ["#F", "#G", "#H"]}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        result = merged["visual_style"]["dominant_colors_hex"]
        assert len(result) == 5
        # "#A" appears most frequently → must be first
        assert result[0] == "#A"


# ----------------------------------------------------------------------
# Multi-chunk: narrative
# ----------------------------------------------------------------------


class TestNarrative:
    def test_hook_from_first_chunk(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"narrative": {"hook_type": "question"}},
                {"narrative": {"hook_type": "bold_claim"}},
                {"narrative": {"hook_type": "stat_drop"}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["narrative"]["hook_type"] == "question"

    def test_cta_from_last_chunk(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"narrative": {"cta_type": "none_detected"}},
                {"narrative": {"cta_type": "follow"}},
                {"narrative": {"cta_type": "subscribe"}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["narrative"]["cta_type"] == "subscribe"

    def test_hook_duration_from_first(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"narrative": {"hook_duration_seconds": 3.2}},
                {"narrative": {"hook_duration_seconds": 99.0}},
                {"narrative": {"hook_duration_seconds": 99.0}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["narrative"]["hook_duration_seconds"] == pytest.approx(3.2)

    def test_cta_duration_from_last(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"narrative": {"cta_duration_seconds": 0.0}},
                {"narrative": {"cta_duration_seconds": 0.0}},
                {"narrative": {"cta_duration_seconds": 5.5}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["narrative"]["cta_duration_seconds"] == pytest.approx(5.5)

    def test_section_count_sum(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"narrative": {"section_count": 2}},
                {"narrative": {"section_count": 3}},
                {"narrative": {"section_count": 4}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["narrative"]["section_count"] == 9

    def test_section_structure_concat_and_shift(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            chunk_seconds=300.0,
            overrides=[
                {
                    "narrative": {
                        "section_structure": [
                            {"label": "intro", "approx_start_s": 0.0, "approx_end_s": 30.0}
                        ]
                    }
                },
                {
                    "narrative": {
                        "section_structure": [
                            {"label": "body", "approx_start_s": 10.0, "approx_end_s": 60.0}
                        ]
                    }
                },
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        sections = merged["narrative"]["section_structure"]
        assert len(sections) == 2
        assert sections[0]["approx_start_s"] == pytest.approx(0.0)
        assert sections[0]["approx_end_s"] == pytest.approx(30.0)
        assert sections[1]["approx_start_s"] == pytest.approx(310.0)
        assert sections[1]["approx_end_s"] == pytest.approx(360.0)
        validate_artifact("video_analysis", merged)

    def test_target_duration_seconds_sum(self, fake_video_chunks):
        chunks = fake_video_chunks(n=3, chunk_seconds=300.0)
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["narrative"]["target_duration_seconds"] == pytest.approx(900.0)

    def test_paragraph_pattern_concat_markers(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"narrative": {"paragraph_pattern": "short-punchy"}},
                {"narrative": {"paragraph_pattern": "build-up"}},
                {"narrative": {"paragraph_pattern": "payoff"}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        pp = merged["narrative"]["paragraph_pattern"]
        assert "[chunk 1/3]" in pp
        assert "[chunk 2/3]" in pp
        assert "[chunk 3/3]" in pp


# ----------------------------------------------------------------------
# Confidence aggregation
# ----------------------------------------------------------------------


class TestConfidenceAggregation:
    def test_worst_case_low_wins_per_dimension(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"editing_pacing": {"confidence": {"cuts_per_minute": "high"}}},
                {"editing_pacing": {"confidence": {"cuts_per_minute": "low"}}},
                {"editing_pacing": {"confidence": {"cuts_per_minute": "medium"}}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["editing_pacing"]["confidence"]["cuts_per_minute"] == "low"

    def test_all_high_stays_high(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"audio": {"confidence": {"has_narration": "high"}}},
                {"audio": {"confidence": {"has_narration": "high"}}},
                {"audio": {"confidence": {"has_narration": "high"}}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["audio"]["confidence"]["has_narration"] == "high"

    def test_mixed_no_low(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"narrative": {"confidence": {"hook_type": "high"}}},
                {"narrative": {"confidence": {"hook_type": "medium"}}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["narrative"]["confidence"]["hook_type"] == "medium"


# ----------------------------------------------------------------------
# shot_boundary_source — RESEARCH Open Question 2
# ----------------------------------------------------------------------


class TestShotBoundarySource:
    def test_all_model(self, fake_video_chunks):
        chunks = fake_video_chunks(n=3)
        for _c, art in chunks:
            art["shot_boundary_source"] = "model"
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["shot_boundary_source"] == "model"

    def test_disagreement_becomes_hybrid(self, fake_video_chunks):
        chunks = fake_video_chunks(n=2)
        chunks[0][1]["shot_boundary_source"] = "scene_detect"
        chunks[1][1]["shot_boundary_source"] = "model"
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["shot_boundary_source"] == "hybrid"

    def test_any_hybrid_stays_hybrid(self, fake_video_chunks):
        chunks = fake_video_chunks(n=3)
        chunks[0][1]["shot_boundary_source"] = "model"
        chunks[1][1]["shot_boundary_source"] = "hybrid"
        chunks[2][1]["shot_boundary_source"] = "model"
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["shot_boundary_source"] == "hybrid"

    def test_absent_omits_field(self, fake_video_chunks):
        chunks = fake_video_chunks(n=2)
        # neither chunk sets shot_boundary_source → merged should not have it
        merged = merge_analyses(chunks, provider="gemini")
        assert "shot_boundary_source" not in merged


# ----------------------------------------------------------------------
# chunking_metadata
# ----------------------------------------------------------------------


class TestChunkingMetadata:
    def test_per_chunk_populated(self, fake_video_chunks):
        chunks = fake_video_chunks(n=3, chunk_seconds=300.0)
        for i, (_c, art) in enumerate(chunks):
            art["_cost_usd"] = 0.1 + 0.01 * i
        merged = merge_analyses(chunks, provider="gemini")
        meta = merged["chunking_metadata"]
        assert meta["chunk_count"] == 3
        assert len(meta["per_chunk"]) == 3
        for i, entry in enumerate(meta["per_chunk"]):
            assert entry["index"] == i
            assert entry["start_s"] == pytest.approx(i * 300.0)
            assert entry["end_s"] == pytest.approx((i + 1) * 300.0)
            assert entry["cost_usd"] == pytest.approx(0.1 + 0.01 * i)
            assert entry["provider"] == "gemini"

    def test_total_duration_matches_source(self, fake_video_chunks):
        chunks = fake_video_chunks(n=4, chunk_seconds=250.0)
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["chunking_metadata"]["total_duration_s"] == pytest.approx(1000.0)
        assert merged["source"]["duration_seconds"] == pytest.approx(1000.0)

    def test_provider_used_per_chunk_override(self, fake_video_chunks):
        chunks = fake_video_chunks(n=2)
        chunks[0][1]["_provider_used"] = "gemini"
        chunks[1][1]["_provider_used"] = "openrouter"
        merged = merge_analyses(chunks, provider="gemini")
        per = merged["chunking_metadata"]["per_chunk"]
        assert per[0]["provider"] == "gemini"
        assert per[1]["provider"] == "openrouter"


# ----------------------------------------------------------------------
# Schema validation gate
# ----------------------------------------------------------------------


class TestSchemaValidation:
    def test_merged_artifact_schema_valid_n3(self, fake_video_chunks):
        chunks = fake_video_chunks(n=3)
        merged = merge_analyses(chunks, provider="gemini")
        validate_artifact("video_analysis", merged)

    def test_merged_artifact_schema_valid_n10(self, fake_video_chunks):
        chunks = fake_video_chunks(n=10)
        merged = merge_analyses(chunks, provider="gemini")
        validate_artifact("video_analysis", merged)
        assert merged["chunking_metadata"]["chunk_count"] == 10

    def test_validate_called_once_per_merge(self, fake_video_chunks):
        chunks = fake_video_chunks(n=3)
        with patch(
            "lib.analysis_merger.validate_artifact",
            wraps=validate_artifact,
        ) as spy:
            merge_analyses(chunks, provider="gemini")
            assert spy.call_count == 1

    def test_n1_roundtrip_idempotent(self, fake_video_chunks):
        """Three identical chunks: merged ≈ chunk[0] for 'first chunk' rules."""
        chunks = fake_video_chunks(n=3)
        merged = merge_analyses(chunks, provider="gemini")
        # hook_type from chunks[0]
        assert merged["narrative"]["hook_type"] == chunks[0][1]["narrative"]["hook_type"]
        # aspect_ratio from chunks[0]
        assert (
            merged["visual_style"]["aspect_ratio"]
            == chunks[0][1]["visual_style"]["aspect_ratio"]
        )


# ----------------------------------------------------------------------
# CLEAN-06 / MR-02: MergeConsensusError replaces silent fallback defaults
# ----------------------------------------------------------------------


class TestMergeConsensusError:
    """Each required field that previously fell back to a hardcoded default
    (`vote or dims[0].get(field, DEFAULT)` at lines 295, 394, 400, 538, 551,
    602, 637, 655 in v2.0) now raises MergeConsensusError when every chunk
    is missing / None.

    Happy paths are covered by the existing test classes above — this class
    focuses on the negative path that the old code silently masked.
    """

    def test_pacing_style_missing_raises(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"editing_pacing": {"pacing_style": None}},
                {"editing_pacing": {"pacing_style": None}},
                {"editing_pacing": {"pacing_style": None}},
            ],
        )
        from lib.analysis_errors import MergeConsensusError
        with pytest.raises(MergeConsensusError, match=r"editing_pacing\.pacing_style"):
            merge_analyses(chunks, provider="gemini")

    def test_narration_style_missing_raises(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"audio": {"narration_style": None}},
                {"audio": {"narration_style": None}},
                {"audio": {"narration_style": None}},
            ],
        )
        from lib.analysis_errors import MergeConsensusError
        with pytest.raises(MergeConsensusError, match=r"audio\.narration_style"):
            merge_analyses(chunks, provider="gemini")

    def test_voice_music_mix_missing_raises(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"audio": {"voice_music_mix": None}},
                {"audio": {"voice_music_mix": None}},
                {"audio": {"voice_music_mix": None}},
            ],
        )
        from lib.analysis_errors import MergeConsensusError
        with pytest.raises(MergeConsensusError, match=r"audio\.voice_music_mix"):
            merge_analyses(chunks, provider="gemini")

    def test_production_quality_missing_raises(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"visual_style": {"production_quality": None}},
                {"visual_style": {"production_quality": None}},
                {"visual_style": {"production_quality": None}},
            ],
        )
        from lib.analysis_errors import MergeConsensusError
        with pytest.raises(MergeConsensusError, match=r"visual_style\.production_quality"):
            merge_analyses(chunks, provider="gemini")

    def test_aspect_ratio_missing_raises(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"visual_style": {"aspect_ratio": None}},
                {"visual_style": {"aspect_ratio": None}},
                {"visual_style": {"aspect_ratio": None}},
            ],
        )
        from lib.analysis_errors import MergeConsensusError
        with pytest.raises(MergeConsensusError, match=r"visual_style\.aspect_ratio"):
            merge_analyses(chunks, provider="gemini")

    def test_narrative_arc_missing_raises(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"narrative": {"narrative_arc": None}},
                {"narrative": {"narrative_arc": None}},
                {"narrative": {"narrative_arc": None}},
            ],
        )
        from lib.analysis_errors import MergeConsensusError
        with pytest.raises(MergeConsensusError, match=r"narrative\.narrative_arc"):
            merge_analyses(chunks, provider="gemini")

    def test_target_platform_missing_raises(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"narrative": {"target_platform": None}},
                {"narrative": {"target_platform": None}},
                {"narrative": {"target_platform": None}},
            ],
        )
        from lib.analysis_errors import MergeConsensusError
        with pytest.raises(MergeConsensusError, match=r"narrative\.target_platform"):
            merge_analyses(chunks, provider="gemini")

    def test_content_tone_missing_raises(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"narrative": {"content_tone": None}},
                {"narrative": {"content_tone": None}},
                {"narrative": {"content_tone": None}},
            ],
        )
        from lib.analysis_errors import MergeConsensusError
        with pytest.raises(MergeConsensusError, match=r"narrative\.content_tone"):
            merge_analyses(chunks, provider="gemini")

    def test_inherits_video_analysis_error(self):
        """Backward-compat guard: existing `except VideoAnalysisError` handlers
        still catch MergeConsensusError. Removing the inheritance would break
        callers that broadly catch the base class."""
        from lib.analysis_errors import MergeConsensusError, VideoAnalysisError
        assert issubclass(MergeConsensusError, VideoAnalysisError)
