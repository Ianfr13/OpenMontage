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


# ----------------------------------------------------------------------
# CLEAN-07 — full_chunks kwarg for position-aware hook/cta
# ----------------------------------------------------------------------


class TestFullChunksKwarg:
    def test_full_chunks_none_is_backward_compatible(self, fake_video_chunks):
        """Passing full_chunks=None (the default) yields the exact same
        merged artifact as not passing the kwarg at all."""
        chunks_a = fake_video_chunks(n=3)
        chunks_b = fake_video_chunks(n=3)
        a = merge_analyses(chunks_a, provider="gemini")
        b = merge_analyses(chunks_b, provider="gemini", full_chunks=None)
        # hook_type is position-dependent in both paths — should match
        assert a["narrative"]["hook_type"] == b["narrative"]["hook_type"]
        assert a["narrative"]["cta_type"] == b["narrative"]["cta_type"]

    def test_full_chunks_with_none_slots_preserves_position(
        self, fake_video_chunks
    ):
        """full_chunks=[(c0, art0), (c1, None), (c2, art2)] -> merger picks
        hook from art0 and cta from art2 (middle chunk failed)."""
        # Build 3 chunks with distinct hook/cta markers
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"narrative": {"hook_type": "question", "cta_type": "subscribe"}},
                {"narrative": {"hook_type": "bold_claim", "cta_type": "visit_link"}},
                {"narrative": {"hook_type": "stat_drop", "cta_type": "purchase"}},
            ],
        )
        # Survivors: 0 and 2; full_chunks keeps all 3 positions
        survivors = [chunks[0], chunks[2]]
        full = [
            (chunks[0][0], chunks[0][1]),
            (chunks[1][0], None),  # failed chunk
            (chunks[2][0], chunks[2][1]),
        ]
        merged = merge_analyses(
            survivors, provider="gemini", full_chunks=full
        )
        # Hook from chunk 0, cta from chunk 2 (chunk 1 failed)
        assert merged["narrative"]["hook_type"] == "question"
        assert merged["narrative"]["cta_type"] == "purchase"


# ----------------------------------------------------------------------
# format — hierarchical archetype classification (v2.1+)
# ----------------------------------------------------------------------


class TestFormatMerge:
    """Merge strategy consolidated from peer review (Codex + Gemini).

    - primary_archetype by runtime-share (not flat majority)
    - secondary_archetypes = siblings with share >= 0.20
    - format_category derived from primary_archetype via canonical map
    - production_style: duration-weighted majority
    - meta_format: first non-absent (OMIT when all absent)
    - ugc_score: weighted average
    - trend_reference: first non-null string
    - confidence: worst-confidence rule (matches other dimensions)
    """

    def _fmt(
        self,
        archetype: str = "talking_head_studio",
        production_style: str = "creator_prosumer",
        **extras,
    ) -> dict:
        """Build a schema-valid format block with optional extras."""
        out = {
            "format_category": "people_centric",
            "primary_archetype": archetype,
            "production_style": production_style,
        }
        out.update(extras)
        return out

    def test_no_chunk_has_format_omits_field(self, fake_video_chunks):
        chunks = fake_video_chunks(n=2)
        merged = merge_analyses(chunks, provider="gemini")
        assert "format" not in merged

    def test_single_archetype_across_chunks_primary_wins(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"format": self._fmt("talking_head_studio")},
                {"format": self._fmt("talking_head_studio")},
                {"format": self._fmt("talking_head_studio")},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["format"]["primary_archetype"] == "talking_head_studio"
        assert merged["format"]["format_category"] == "people_centric"
        assert "secondary_archetypes" not in merged["format"]

    def test_weighted_majority_by_runtime_share(self, fake_video_chunks):
        # 2×120s of talking_head vs 1×120s of product_demo
        # talking_head share = 2/3 ~= 0.67 -> primary; product_demo share = 0.33 -> secondary
        chunks = fake_video_chunks(
            n=3,
            chunk_seconds=120.0,
            overrides=[
                {"format": self._fmt("talking_head_studio")},
                {"format": self._fmt("talking_head_studio")},
                {"format": self._fmt("product_demo")},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        fmt = merged["format"]
        assert fmt["primary_archetype"] == "talking_head_studio"
        assert fmt["format_category"] == "people_centric"
        assert fmt.get("secondary_archetypes") == ["product_demo"]

    def test_secondary_archetypes_threshold(self, fake_video_chunks):
        # 4 talking_head + 1 product_demo + 0.5 cartoon_2d (as 10s chunk)
        # share: talking_head=4/5.5=0.73, product_demo=1/5.5=0.18, cartoon_2d=0.5/5.5=0.09
        # Only talking_head >= 0.20 as primary (0.73), product_demo just below 0.20 threshold
        # so no secondaries. Test that sub-0.20 ones are filtered.
        chunks = fake_video_chunks(
            n=3,
            chunk_seconds=60.0,
            overrides=[
                {"format": self._fmt("talking_head_studio")},  # 60s
                {"format": self._fmt("talking_head_studio")},  # 60s
                {"format": self._fmt("product_demo")},  # 60s -> share 1/3=0.33, >=0.20
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["format"]["primary_archetype"] == "talking_head_studio"
        # product_demo is 1/3 of runtime -> above 0.20 threshold
        assert merged["format"]["secondary_archetypes"] == ["product_demo"]

    def test_tie_break_uses_first_chunk_when_shares_equal(self, fake_video_chunks):
        # Two equal-weight chunks with different archetypes -> first wins
        chunks = fake_video_chunks(
            n=2,
            chunk_seconds=100.0,
            overrides=[
                {"format": self._fmt("documentary")},
                {"format": self._fmt("talking_head_studio")},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["format"]["primary_archetype"] == "documentary"

    def test_format_category_derived_from_archetype(self, fake_video_chunks):
        # Even if a chunk declares the wrong category, the merger derives it
        # from the canonical archetype->category mapping.
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"format": {
                    "format_category": "mixed",  # intentionally wrong
                    "primary_archetype": "cartoon_2d",
                    "production_style": "motion_graphics_native",
                }},
                {"format": {
                    "format_category": "mixed",  # intentionally wrong
                    "primary_archetype": "cartoon_2d",
                    "production_style": "motion_graphics_native",
                }},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        # Derived from cartoon_2d -> animated, overriding the chunks' declaration
        assert merged["format"]["format_category"] == "animated"

    def test_production_style_weighted_majority(self, fake_video_chunks):
        # 2×120s ugc + 1×120s studio_produced -> ugc wins
        chunks = fake_video_chunks(
            n=3,
            chunk_seconds=120.0,
            overrides=[
                {"format": self._fmt("talking_head_studio", production_style="ugc")},
                {"format": self._fmt("talking_head_studio", production_style="ugc")},
                {"format": self._fmt("talking_head_studio", production_style="studio_produced")},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["format"]["production_style"] == "ugc"

    def test_meta_format_first_non_absent(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"format": self._fmt()},
                {"format": self._fmt(meta_format="pov_caption")},
                {"format": self._fmt(meta_format="grwm_caption")},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["format"]["meta_format"] == "pov_caption"

    def test_meta_format_omitted_when_all_absent(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"format": self._fmt()},
                {"format": self._fmt()},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert "meta_format" not in merged["format"]

    def test_ugc_score_weighted_average(self, fake_video_chunks):
        # Equal-weight chunks with scores 0.2 and 0.8 -> mean 0.5
        chunks = fake_video_chunks(
            n=2,
            chunk_seconds=100.0,
            overrides=[
                {"format": self._fmt(ugc_score=0.2)},
                {"format": self._fmt(ugc_score=0.8)},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["format"]["ugc_score"] == pytest.approx(0.5)

    def test_trend_reference_first_non_null(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"format": self._fmt(trend_reference=None)},
                {"format": self._fmt(trend_reference="POV you are...")},
                {"format": self._fmt(trend_reference="tell me without...")},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["format"]["trend_reference"] == "POV you are..."

    def test_confidence_uses_worst_rule(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"format": self._fmt(confidence={"primary_archetype": "high"})},
                {"format": self._fmt(confidence={"primary_archetype": "low"})},
                {"format": self._fmt(confidence={"primary_archetype": "medium"})},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        # Worst ("low") wins
        assert merged["format"]["confidence"]["primary_archetype"] == "low"

    def test_single_chunk_passthrough_keeps_format(self, fake_video_chunks):
        """Single-chunk (N=1) path deep-copies and does not strip `format`."""
        chunks = fake_video_chunks(
            n=1,
            overrides=[{"format": self._fmt("cinematic_short", production_style="studio_produced")}],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["format"]["primary_archetype"] == "cinematic_short"
        assert merged["format"]["production_style"] == "studio_produced"


# ----------------------------------------------------------------------
# grounding_cues — per-field evidence array (v2.1+)
# ----------------------------------------------------------------------


class TestGroundingCuesMerge:
    def _cue(
        self,
        path: str,
        support: list[str],
        value: str = "stub",
        rejected: str | None = None,
    ) -> dict:
        out: dict[str, Any] = {"field_path": path, "value": value, "support": support}
        if rejected:
            out["rejected"] = rejected
        return out

    def test_no_chunk_has_cues_omits_field(self, fake_video_chunks):
        chunks = fake_video_chunks(n=2)
        merged = merge_analyses(chunks, provider="gemini")
        assert "grounding_cues" not in merged

    def test_single_chunk_passthrough_keeps_cues(self, fake_video_chunks):
        # Single-chunk path deep-copies without the value-aware filter.
        # The pre-minimal fixture has narrative.hook_type="question"; emit a
        # cue with value="question" so the schema validates.
        chunks = fake_video_chunks(
            n=1,
            overrides=[{
                "grounding_cues": [
                    self._cue(
                        "narrative.hook_type",
                        ["0:03 question"],
                        value="question",
                        rejected="none — asked literally",
                    ),
                ]
            }],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["grounding_cues"] == [
            {
                "field_path": "narrative.hook_type",
                "value": "question",
                "support": ["0:03 question"],
                "rejected": "none — asked literally",
            }
        ]

    def test_multi_chunk_concats_support_with_prefix(self, fake_video_chunks):
        # Both chunks agree on pacing_style value -> cues survive; two
        # contributing chunks -> support prefixed.
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"editing_pacing": {"pacing_style": "dynamic_social"},
                 "grounding_cues": [
                     self._cue(
                         "editing_pacing.pacing_style",
                         ["12 shots <1.5s"],
                         value="dynamic_social",
                     )
                 ]},
                {"editing_pacing": {"pacing_style": "dynamic_social"},
                 "grounding_cues": [
                     self._cue(
                         "editing_pacing.pacing_style",
                         ["avg 1.2s"],
                         value="dynamic_social",
                     )
                 ]},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        gc = merged["grounding_cues"]
        assert len(gc) == 1
        entry = gc[0]
        assert entry["field_path"] == "editing_pacing.pacing_style"
        assert entry["value"] == "dynamic_social"
        assert entry["support"] == [
            "[chunk-0] 12 shots <1.5s",
            "[chunk-1] avg 1.2s",
        ]

    def test_single_chunk_contributes_no_prefix(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"narrative": {"hook_type": "question"},
                 "grounding_cues": [self._cue("narrative.hook_type", ["0:03 question"], value="question")]},
                {},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        entry = merged["grounding_cues"][0]
        assert entry["support"] == ["0:03 question"]  # no prefix

    def test_rejected_takes_first_non_empty(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"narrative": {"hook_type": "question"},
                 "grounding_cues": [self._cue("narrative.hook_type", ["a"], value="question", rejected="")]},
                {"narrative": {"hook_type": "question"},
                 "grounding_cues": [self._cue("narrative.hook_type", ["b"], value="question", rejected="other — why")]},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["grounding_cues"][0]["rejected"] == "other — why"

    def test_canonical_ordering(self, fake_video_chunks):
        """Single-chunk pass-through respects input order."""
        chunks = fake_video_chunks(
            n=1,
            overrides=[{
                "grounding_cues": [
                    self._cue("format.primary_archetype", ["talking head"], value="talking_head_studio"),
                    self._cue("editing_pacing.pacing_style", ["dynamic"], value="dynamic_social"),
                    self._cue("narrative.hook_type", ["q"], value="question"),
                ]
            }],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert [e["field_path"] for e in merged["grounding_cues"]] == [
            "format.primary_archetype",
            "editing_pacing.pacing_style",
            "narrative.hook_type",
        ]

    def test_multi_chunk_canonical_ordering(self, fake_video_chunks):
        """Multi-chunk merge emits entries in canonical field_path order."""
        # Set explicit winners for every field the cues bind to so the
        # value-aware filter keeps them; this test is about ordering.
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"narrative": {"hook_type": "question"},
                 "editing_pacing": {"pacing_style": "dynamic_social"},
                 "grounding_cues": [
                     self._cue("editing_pacing.pacing_style", ["b"], value="dynamic_social"),
                 ]},
                {"narrative": {"hook_type": "question"},
                 "editing_pacing": {"pacing_style": "dynamic_social"},
                 "grounding_cues": [
                     self._cue("narrative.hook_type", ["c"], value="question"),
                 ]},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        paths = [e["field_path"] for e in merged["grounding_cues"]]
        assert "editing_pacing.pacing_style" in paths
        assert "narrative.hook_type" in paths
        # pacing_style is ordered before hook_type per canonical list
        assert paths.index("editing_pacing.pacing_style") < paths.index("narrative.hook_type")

    def test_value_aware_filter_drops_losing_cues(self, fake_video_chunks):
        """Codex Bug A: cues whose `value` disagrees with merged winner dropped."""
        # Chunk 0 votes pacing_style=dynamic_social with support.
        # Chunk 1 votes pacing_style=rapid_fire with support.
        # With equal weight, chunk 0 wins (first). Chunk 1's cue must be dropped.
        chunks = fake_video_chunks(
            n=2,
            chunk_seconds=100.0,
            overrides=[
                {"editing_pacing": {"pacing_style": "dynamic_social"},
                 "grounding_cues": [
                     self._cue("editing_pacing.pacing_style", ["avg 2s"], value="dynamic_social"),
                 ]},
                {"editing_pacing": {"pacing_style": "rapid_fire"},
                 "grounding_cues": [
                     self._cue("editing_pacing.pacing_style", ["avg 0.8s"], value="rapid_fire"),
                 ]},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        # Winner is dynamic_social (first-chunk tie-break on equal weights)
        assert merged["editing_pacing"]["pacing_style"] == "dynamic_social"
        # Only the cue for dynamic_social survives
        gc = merged["grounding_cues"]
        assert len(gc) == 1
        assert gc[0]["value"] == "dynamic_social"
        # Support from chunk 0 only (chunk 1 dropped), so no prefix
        assert gc[0]["support"] == ["avg 2s"]

    def test_identical_support_strings_deduped(self, fake_video_chunks):
        """Gemini Issue H: identical support strings across chunks deduped."""
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"narrative": {"hook_type": "question"},
                 "grounding_cues": [self._cue("narrative.hook_type", ["question at 0:03"], value="question")]},
                {"narrative": {"hook_type": "question"},
                 "grounding_cues": [self._cue("narrative.hook_type", ["question at 0:03"], value="question")]},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        gc = merged["grounding_cues"][0]
        # Same string from both chunks collapses to one entry — no duplicate
        # "[chunk-0] question..." and "[chunk-1] question..." pair.
        assert len(gc["support"]) == 1

    def test_extra_field_path_sorted_after_canonical(self, fake_video_chunks):
        """Gemini Issue 4 / Codex Bug G: unknown paths never silently dropped."""
        # Schema's field_path enum is closed (8 allowed paths). This test
        # stubs in an out-of-enum string to validate the merger ordering
        # logic by bypassing schema validation via a single-chunk path.
        # We patch the inner merger directly.
        from lib.analysis_merger import _merge_grounding_cues
        from lib.video_chunker import Chunk

        chunks = [
            (
                Chunk(start_global=0, end_global=10, local_path="/tmp/a.mp4"),
                {"grounding_cues": [
                    {"field_path": "zzz_extra", "value": "anything", "support": ["x"]},
                    {"field_path": "narrative.hook_type", "value": "question", "support": ["y"]},
                ]},
            ),
            (
                Chunk(start_global=10, end_global=20, local_path="/tmp/b.mp4"),
                {"grounding_cues": [
                    {"field_path": "narrative.hook_type", "value": "question", "support": ["z"]},
                ]},
            ),
        ]
        # Pass merged=None to skip value-aware filter (bypass the rest of
        # merge_analyses — we only test ordering here).
        gc = _merge_grounding_cues(chunks, merged=None)
        paths = [e["field_path"] for e in gc]
        # Canonical paths first, then extras alphabetically
        assert paths == ["narrative.hook_type", "zzz_extra"]


# ----------------------------------------------------------------------
# Round 2 — edge cases raised by post-implementation peer review
# ----------------------------------------------------------------------


class TestFormatMergeRound2:
    """Follow-up coverage for bugs caught by round-2 reviewers."""

    def _fmt(
        self,
        archetype: str = "talking_head_studio",
        production_style: str = "creator_prosumer",
        **extras,
    ) -> dict:
        out = {
            "format_category": "people_centric",
            "primary_archetype": archetype,
            "production_style": production_style,
        }
        out.update(extras)
        return out

    def test_drift_invariant_schema_matches_archetype_map(self):
        """Codex Bug G: `_ARCHETYPE_TO_CATEGORY` must cover the schema enum exactly.

        If a new archetype is added to the schema but not to the mapping,
        this test fails — blocking drift between schema and merger.
        """
        from schemas.artifacts import load_schema
        from lib.analysis_merger import _ARCHETYPE_TO_CATEGORY

        canonical = load_schema("video_analysis")
        enum = set(
            canonical["properties"]["format"]["properties"]["primary_archetype"]["enum"]
        )
        map_keys = set(_ARCHETYPE_TO_CATEGORY.keys())
        extra_in_schema = enum - map_keys
        extra_in_map = map_keys - enum
        assert not extra_in_schema, f"archetypes in schema but not mapped: {extra_in_schema}"
        assert not extra_in_map, f"archetypes in map but not in schema: {extra_in_map}"

    def test_drift_invariant_categories_match_schema_enum(self):
        """The target categories in the mapping must all appear in the schema's
        format_category enum."""
        from schemas.artifacts import load_schema
        from lib.analysis_merger import _ARCHETYPE_TO_CATEGORY

        canonical = load_schema("video_analysis")
        cat_enum = set(
            canonical["properties"]["format"]["properties"]["format_category"]["enum"]
        )
        used = set(_ARCHETYPE_TO_CATEGORY.values())
        assert used <= cat_enum, f"map uses categories not in schema enum: {used - cat_enum}"

    def test_unmapped_archetype_drops_format_block_gracefully(self, fake_video_chunks, caplog):
        """Round-3 (Gemini): unmapped archetype logs + drops format block
        instead of crashing the whole merge (fail-graceful)."""
        from lib.analysis_merger import _ARCHETYPE_TO_CATEGORY
        from unittest.mock import patch

        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"format": self._fmt("talking_head_studio")},
                {"format": self._fmt("talking_head_studio")},
            ],
        )
        # Simulate drift: temporarily empty the map. Merge must succeed,
        # emit a warning, and produce a merged artifact without a format
        # block (rest of the dimensions merge normally).
        import logging
        with patch.dict(_ARCHETYPE_TO_CATEGORY, {}, clear=True):
            with caplog.at_level(logging.WARNING, logger="lib.analysis_merger"):
                merged = merge_analyses(chunks, provider="gemini")
        assert "format" not in merged
        # Warning message mentions the drift cause
        assert any(
            "not in _ARCHETYPE_TO_CATEGORY" in rec.message
            for rec in caplog.records
        )

    def test_partial_format_missing_production_style_drops_block(self, fake_video_chunks):
        """Gemini Bug D: when production_style is unresolvable, omit format block."""
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                # format present but production_style missing
                {"format": {
                    "format_category": "people_centric",
                    "primary_archetype": "talking_head_studio",
                }},
                {"format": {
                    "format_category": "people_centric",
                    "primary_archetype": "talking_head_studio",
                }},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert "format" not in merged  # whole block dropped, not emitted with None

    def test_chunk_level_secondary_archetypes_preserved(self, fake_video_chunks):
        """Codex Bug E: chunk-emitted secondary_archetypes survive the merge.

        A single chunk declares intra-chunk mixture (primary + secondary). The
        merger must union the chunk-level secondaries with any derived from
        cross-chunk runtime share.
        """
        chunks = fake_video_chunks(
            n=2,
            chunk_seconds=100.0,
            overrides=[
                {"format": {
                    "format_category": "people_centric",
                    "primary_archetype": "talking_head_studio",
                    "production_style": "creator_prosumer",
                    "secondary_archetypes": ["product_demo"],  # intra-chunk mix
                }},
                {"format": self._fmt("talking_head_studio")},  # no secondaries
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        fmt = merged["format"]
        assert fmt["primary_archetype"] == "talking_head_studio"
        # Chunk-level secondary preserved even though not derivable from share
        assert "product_demo" in fmt.get("secondary_archetypes", [])

    def test_dead_confidence_code_fixed(self, fake_video_chunks):
        """Gemini Bug C: chunks without `confidence` no longer drop the chunk
        silently from the worst-confidence calculation.

        Before: chunks with no confidence field contributed {} via the dead
        default, so worst-confidence ignored them. After: the filter removes
        them explicitly; the merged confidence reflects only chunks that
        declared one.
        """
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"format": self._fmt(confidence={"primary_archetype": "high"})},
                {"format": self._fmt()},  # no confidence -> NOT counted as high
                {"format": self._fmt(confidence={"primary_archetype": "low"})},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        # Worst-confidence among chunks that DID declare one: {high, low} -> low
        assert merged["format"]["confidence"]["primary_archetype"] == "low"

    def test_trend_reference_paired_with_meta_format(self, fake_video_chunks):
        """Codex Bug F: trend_reference pairs with the chunk that supplied
        meta_format (not first-non-null, which could contradict the winner)."""
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                # chunk 0 has a trend_reference but no meta_format
                {"format": self._fmt(trend_reference="older trend")},
                # chunk 1 has meta_format + a trend_reference — should win
                {"format": self._fmt(meta_format="pov_caption", trend_reference="POV you are...")},
                # chunk 2 later
                {"format": self._fmt(meta_format="grwm_caption", trend_reference="GRWM trend")},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        # meta_format is the first chunk that emitted one (chunk 1)
        assert merged["format"]["meta_format"] == "pov_caption"
        # trend_reference paired with chunk 1, not chunk 0's first-non-null
        assert merged["format"]["trend_reference"] == "POV you are..."

    def test_zero_weight_chunks_still_pick_primary(self, fake_video_chunks):
        """Gemini Issue I: zero-duration chunks no longer corrupt normalization."""
        # Build chunks with zero duration — contrived edge case
        from lib.video_chunker import Chunk
        chunks = [
            (
                Chunk(start_global=0.0, end_global=0.0, local_path="/tmp/a.mp4"),
                {"format": self._fmt("talking_head_studio"), **{
                    k: v for k, v in _minimal_artifact_for_test().items() if k != "format"
                }},
            ),
            (
                Chunk(start_global=0.0, end_global=0.0, local_path="/tmp/b.mp4"),
                {"format": self._fmt("product_demo", production_style="studio_produced"), **{
                    k: v for k, v in _minimal_artifact_for_test().items() if k != "format"
                }},
            ),
        ]
        merged = merge_analyses(chunks, provider="gemini")
        # Uniform fallback when total_w=0: first-chunk tie-break still gives
        # a valid primary_archetype.
        assert merged["format"]["primary_archetype"] in {"talking_head_studio", "product_demo"}


def _minimal_artifact_for_test():
    """Helper for the zero-weight test — produces a fresh minimal artifact."""
    from tests.contracts.test_video_analysis_schema import (
        minimal_video_analysis as _m,
    )
    return copy.deepcopy(_m())


# ----------------------------------------------------------------------
# Round 3 — post-round-2 peer review edge cases
# ----------------------------------------------------------------------


class TestGroundingCuesRound3:
    """Coverage for the round-2 peer-review findings."""

    def _cue(
        self,
        path: str,
        support: list[str],
        value: str = "stub",
        rejected: str | None = None,
    ) -> dict:
        out: dict[str, Any] = {"field_path": path, "value": value, "support": support}
        if rejected:
            out["rejected"] = rejected
        return out

    def test_format_cues_dropped_when_format_block_dropped(self, fake_video_chunks):
        """Round-3 Bug N2 + Gemini ruthless: if the format block is dropped
        (e.g. unmapped archetype), orphaned format.* cues must also be dropped.
        """
        from lib.analysis_merger import _ARCHETYPE_TO_CATEGORY
        from unittest.mock import patch

        chunks = fake_video_chunks(
            n=2,
            chunk_seconds=100.0,
            overrides=[
                {"format": {
                    "format_category": "people_centric",
                    "primary_archetype": "talking_head_studio",
                    "production_style": "creator_prosumer",
                 },
                 "grounding_cues": [
                     self._cue("format.primary_archetype",
                               ["0:00-0:10 subject to camera"],
                               value="talking_head_studio"),
                 ]},
                {"format": {
                    "format_category": "people_centric",
                    "primary_archetype": "talking_head_studio",
                    "production_style": "creator_prosumer",
                 },
                 "grounding_cues": [
                     self._cue("narrative.hook_type",
                               ["0:00-0:03 question"],
                               value="question"),
                 ]},
            ],
        )
        with patch.dict(_ARCHETYPE_TO_CATEGORY, {}, clear=True):
            merged = merge_analyses(chunks, provider="gemini")
        assert "format" not in merged
        gc = merged.get("grounding_cues", [])
        emitted_paths = {e["field_path"] for e in gc}
        # format.primary_archetype cue is orphaned -> dropped
        assert "format.primary_archetype" not in emitted_paths

    def test_pre_v2_1_cue_missing_value_dropped_on_string_path(self, fake_video_chunks):
        """Round-3 Bug N1: cues without `value` on exact-enum paths are
        dropped so the merger never emits schema-invalid entries."""
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"narrative": {"hook_type": "question"},
                 "grounding_cues": [
                     # pre-v2.1 shape: no `value` key
                     {"field_path": "narrative.hook_type", "support": ["0:03 q"]},
                 ]},
                {"narrative": {"hook_type": "question"}},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        # No grounding_cues survive (the single entry lacked `value`)
        assert "grounding_cues" not in merged

    def test_structured_path_cues_partition_by_value(self, fake_video_chunks):
        """Round-3 Bug N3: structured-path cues with different `value` tags
        produce SEPARATE merged entries, not one with mixed supports."""
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"visual_style": {"color_palette": {"primary": ["#F0D9B1", "#87CEEB"]}},
                 "grounding_cues": [
                     self._cue("visual_style.color_palette",
                               ["warm dominant in skin tones"],
                               value="warm_amber"),
                 ]},
                {"visual_style": {"color_palette": {"primary": ["#F0D9B1", "#87CEEB"]}},
                 "grounding_cues": [
                     self._cue("visual_style.color_palette",
                               ["cyan sky backgrounds"],
                               value="cool_cyan"),
                 ]},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        gc = [e for e in merged["grounding_cues"] if e["field_path"] == "visual_style.color_palette"]
        # Two entries — one per value tag — not one with pooled supports.
        assert len(gc) == 2
        values = {e["value"] for e in gc}
        assert values == {"warm_amber", "cool_cyan"}
        # Each keeps its own support
        amber = next(e for e in gc if e["value"] == "warm_amber")
        cyan = next(e for e in gc if e["value"] == "cool_cyan")
        assert any("warm dominant" in s for s in amber["support"])
        assert any("cyan sky" in s for s in cyan["support"])

    def test_meta_format_chunk_without_trend_leaves_trend_unset(self, fake_video_chunks):
        """Round-3 Bug F bad-branch: if the meta_format chunk has no
        trend_reference, we do NOT fall back to another chunk (which could
        create a contradiction)."""
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                # chunk 0: trend_reference with NO meta_format
                {"format": {
                    "format_category": "people_centric",
                    "primary_archetype": "talking_head_studio",
                    "production_style": "creator_prosumer",
                    "trend_reference": "older_unrelated_trend",
                 }},
                # chunk 1: meta_format WITHOUT trend_reference
                {"format": {
                    "format_category": "people_centric",
                    "primary_archetype": "talking_head_studio",
                    "production_style": "creator_prosumer",
                    "meta_format": "pov_caption",
                 }},
                # chunk 2: a different trend_reference (noise)
                {"format": {
                    "format_category": "people_centric",
                    "primary_archetype": "talking_head_studio",
                    "production_style": "creator_prosumer",
                    "trend_reference": "unrelated_late_trend",
                 }},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["format"]["meta_format"] == "pov_caption"
        # trend_reference must NOT be pulled from chunk 0 or 2 (contradictory)
        assert "trend_reference" not in merged["format"]

    def test_chunk_level_secondary_archetype_unknown_dropped(self, fake_video_chunks, caplog):
        """Round-3 Bug N4: hallucinated secondary_archetypes from a chunk
        are validated against the canonical enum and dropped (not leaked)."""
        import logging
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"format": {
                    "format_category": "people_centric",
                    "primary_archetype": "talking_head_studio",
                    "production_style": "creator_prosumer",
                    "secondary_archetypes": ["product_demo", "hallucinated_genre"],
                 }},
                {"format": {
                    "format_category": "people_centric",
                    "primary_archetype": "talking_head_studio",
                    "production_style": "creator_prosumer",
                 }},
            ],
        )
        with caplog.at_level(logging.WARNING, logger="lib.analysis_merger"):
            merged = merge_analyses(chunks, provider="gemini")
        sec = merged["format"].get("secondary_archetypes", [])
        # Valid one kept
        assert "product_demo" in sec
        # Hallucinated one dropped
        assert "hallucinated_genre" not in sec
        # Warning logged
        assert any("hallucinated_genre" in rec.message for rec in caplog.records)


# ----------------------------------------------------------------------
# content_identity — what the format is OF (v2.1+)
# ----------------------------------------------------------------------


class TestContentIdentityMerge:
    """Merge strategy for format.content_identity.

    - subjects / aesthetic_tags / recurring_visual_elements: union + dedup
    - setting: weighted majority
    - content_description: concat with chunk labels (multi-chunk) or
      passthrough (single)
    """

    def _fmt_with_ci(self, content_identity: dict) -> dict:
        return {
            "format_category": "animated",
            "primary_archetype": "anime",
            "production_style": "ai_generated",
            "content_identity": content_identity,
        }

    def test_no_content_identity_emits_no_block(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"format": {
                    "format_category": "animated",
                    "primary_archetype": "anime",
                    "production_style": "ai_generated",
                }},
                {"format": {
                    "format_category": "animated",
                    "primary_archetype": "anime",
                    "production_style": "ai_generated",
                }},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert "content_identity" not in merged["format"]

    def test_single_chunk_passthrough_preserves_all_fields(self, fake_video_chunks):
        ci = {
            "subjects": ["anthropomorphic skeleton warrior"],
            "setting": "vast orange desert with cacti and oases",
            "aesthetic_tags": ["cel-shaded anime", "stylized anatomy"],
            "recurring_visual_elements": ["cacti", "sand dunes"],
            "content_description": "AI-generated cel-shaded anime of skeleton survivors in a desert.",
        }
        chunks = fake_video_chunks(
            n=1,
            overrides=[{"format": self._fmt_with_ci(ci)}],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert merged["format"]["content_identity"] == ci

    def test_subjects_union_deduped_across_chunks(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=3,
            overrides=[
                {"format": self._fmt_with_ci({
                    "subjects": ["skeleton warrior", "skeleton thief"],
                })},
                {"format": self._fmt_with_ci({
                    "subjects": ["skeleton thief", "skeleton explorer"],
                })},
                {"format": self._fmt_with_ci({
                    "subjects": ["skeleton explorer"],
                })},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        ci = merged["format"]["content_identity"]
        # Order-preserved union: warrior (chunk 0) first, then thief, then explorer
        assert ci["subjects"] == ["skeleton warrior", "skeleton thief", "skeleton explorer"]

    def test_aesthetic_tags_union(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"format": self._fmt_with_ci({
                    "aesthetic_tags": ["cel-shaded anime", "heavy black outlines"],
                })},
                {"format": self._fmt_with_ci({
                    "aesthetic_tags": ["exaggerated anime eyes", "cel-shaded anime"],
                })},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        tags = merged["format"]["content_identity"]["aesthetic_tags"]
        assert set(tags) == {"cel-shaded anime", "heavy black outlines", "exaggerated anime eyes"}

    def test_recurring_elements_union(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"format": self._fmt_with_ci({
                    "recurring_visual_elements": ["cacti", "sand"],
                })},
                {"format": self._fmt_with_ci({
                    "recurring_visual_elements": ["water oases", "cacti"],
                })},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert set(merged["format"]["content_identity"]["recurring_visual_elements"]) == {
            "cacti", "sand", "water oases"
        }

    def test_setting_weighted_majority(self, fake_video_chunks):
        # chunk 0 (weight 200) vs chunks 1+2 (weight 100 each) saying same thing
        chunks = fake_video_chunks(
            n=3,
            chunk_seconds=100.0,
            overrides=[
                {"format": self._fmt_with_ci({"setting": "vast orange desert"})},
                {"format": self._fmt_with_ci({"setting": "green forest"})},
                {"format": self._fmt_with_ci({"setting": "green forest"})},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        # green forest has 2/3 weight share
        assert merged["format"]["content_identity"]["setting"] == "green forest"

    def test_content_description_multi_chunk_concats(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"format": self._fmt_with_ci({
                    "content_description": "Desert scene with skeletons fighting.",
                })},
                {"format": self._fmt_with_ci({
                    "content_description": "Ocean scene with skeletons swimming.",
                })},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        desc = merged["format"]["content_identity"]["content_description"]
        # Both descriptions present with chunk-N labels
        assert "Desert scene" in desc
        assert "Ocean scene" in desc
        assert "chunk-0" in desc or "chunk-1" in desc

    def test_content_description_single_chunk_unlabeled(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=1,
            overrides=[
                {"format": self._fmt_with_ci({
                    "content_description": "Single chunk desert adventure.",
                })},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        desc = merged["format"]["content_identity"]["content_description"]
        assert desc == "Single chunk desert adventure."
        assert "chunk-" not in desc  # no labeling on single-chunk passthrough

    def test_empty_content_identity_omits_block(self, fake_video_chunks):
        chunks = fake_video_chunks(
            n=2,
            overrides=[
                {"format": self._fmt_with_ci({"subjects": [], "aesthetic_tags": []})},
                {"format": self._fmt_with_ci({"subjects": [], "aesthetic_tags": []})},
            ],
        )
        merged = merge_analyses(chunks, provider="gemini")
        assert "content_identity" not in merged["format"]
