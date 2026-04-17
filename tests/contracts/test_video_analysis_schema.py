"""Phase 1 contract tests — video_analysis canonical schema.

Verifies the v2.0 canonical contract (schemas/artifacts/video_analysis.schema.json)
loads as Draft 2020-12 and that a minimal fixture covering all 4 dimensions
validates. Also verifies rejection of malformed fixtures.

Runs without any API key or network access.
"""
import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from schemas.artifacts import load_schema  # noqa: E402

SCHEMA_PATH = PROJECT_ROOT / "schemas" / "artifacts" / "video_analysis.schema.json"


def minimal_video_analysis() -> dict:
    """Return a minimal schema-valid video_analysis artifact covering all 4 dimensions."""
    return {
        "version": "2.0",
        "source": {"type": "local_file", "duration_seconds": 45.0, "local_path": "/tmp/ref.mp4"},
        "editing_pacing": {
            "total_shots": 12,
            "cuts_per_minute": 16.0,
            "avg_shot_duration_seconds": 3.75,
            "pacing_style": "steady_educational",
            "shot_type_distribution": {
                "talking_head": 0.4,
                "b_roll": 0.3,
                "text_card": 0.2,
                "animation": 0.1,
            },
            "motion_type_distribution": {
                "motion_clip": 5,
                "animated_still": 4,
                "static_image": 3,
            },
        },
        "audio": {
            "has_narration": True,
            "has_music": True,
            "narration_style": "voice_over",
            "voice_music_mix": "narration_dominant",
        },
        "visual_style": {
            "color_palette": {
                "primary": ["#0A84FF"],
                "accent": ["#FF375F"],
                "background": ["#000000"],
                "text": ["#FFFFFF"],
            },
            "production_quality": "professional",
            "aspect_ratio": "16:9",
        },
        "narrative": {
            "hook_type": "question",
            "narrative_arc": "problem_solution",
            "target_platform": "youtube_long",
            "target_duration_seconds": 45.0,
            "content_tone": "educational",
        },
    }


class TestVideoAnalysisSchema:
    def test_schema_loads(self):
        assert SCHEMA_PATH.exists()
        schema = json.load(open(SCHEMA_PATH))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["title"] == "video_analysis"
        assert {"editing_pacing", "audio", "visual_style", "narrative"} <= set(schema["required"])

    def test_load_schema_helper_works(self):
        # schemas.artifacts.load_schema uses the bare artifact name
        schema = load_schema("video_analysis")
        assert schema["title"] == "video_analysis"

    def test_fixture_validates(self):
        schema = load_schema("video_analysis")
        fixture = minimal_video_analysis()
        jsonschema.validate(instance=fixture, schema=schema)  # must not raise

    @pytest.mark.parametrize("dimension", ["editing_pacing", "audio", "visual_style", "narrative"])
    def test_rejects_missing_dimension(self, dimension):
        schema = load_schema("video_analysis")
        fixture = minimal_video_analysis()
        del fixture[dimension]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=fixture, schema=schema)

    def test_rejects_invalid_pacing_style(self):
        schema = load_schema("video_analysis")
        fixture = minimal_video_analysis()
        fixture["editing_pacing"]["pacing_style"] = "not_a_real_style"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=fixture, schema=schema)

    def test_rejects_invalid_narration_style(self):
        schema = load_schema("video_analysis")
        fixture = minimal_video_analysis()
        fixture["audio"]["narration_style"] = "invalid"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=fixture, schema=schema)

    def test_chunking_metadata_is_optional(self):
        schema = load_schema("video_analysis")
        fixture = minimal_video_analysis()
        assert "chunking_metadata" not in fixture
        jsonschema.validate(instance=fixture, schema=schema)  # absence is fine

    def test_chunking_metadata_accepts_merger_shape(self):
        schema = load_schema("video_analysis")
        fixture = minimal_video_analysis()
        fixture["chunking_metadata"] = {
            "chunk_count": 3,
            "total_duration_s": 420.0,
            "provider": "gemini",
            "per_chunk": [
                {"index": 0, "start_s": 0, "end_s": 140, "cost_usd": 0.02, "provider": "gemini"},
            ],
        }
        jsonschema.validate(instance=fixture, schema=schema)

    def test_minimal_fixture_not_mutated_by_validate(self):
        # Sanity: jsonschema.validate must not mutate the instance.
        schema = load_schema("video_analysis")
        fixture = minimal_video_analysis()
        snapshot = deepcopy(fixture)
        jsonschema.validate(instance=fixture, schema=schema)
        assert fixture == snapshot
