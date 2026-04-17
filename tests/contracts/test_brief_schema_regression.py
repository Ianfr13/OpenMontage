"""Phase 1 regression guard — v1.0 video_analysis_brief.schema.json still works.

Phase 1 adds a NEW canonical video_analysis.schema.json. This test locks the
v1.0 brief schema (co-existing with the v2.0 canonical) against accidental
regressions.

Runs with no API keys or network.
"""
import json
import sys
from pathlib import Path

import jsonschema
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from schemas.artifacts import ARTIFACT_NAMES, load_schema, validate_artifact  # noqa: E402

BRIEF_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "artifacts" / "video_analysis_brief.schema.json"


def _minimal_brief() -> dict:
    """Minimal fixture valid against v1.0 brief schema.

    Required top-level keys per video_analysis_brief.schema.json:
      version, source, content_analysis, structure_analysis
    Nested `structure_analysis` requires: total_scenes, scenes, pacing_profile
    Each scene requires: scene_index, start_time, end_time, description
    """
    return {
        "version": "1.0",
        "source": {
            "type": "local_file",
            "duration_seconds": 60.0,
            "local_path": "/tmp/ref.mp4",
        },
        "content_analysis": {
            "summary": "A two-sentence description of the reference video. It demonstrates a steady-paced educational piece.",
            "topics": ["algorithms", "complexity"],
            "target_audience": "intermediate developers",
        },
        "structure_analysis": {
            "total_scenes": 5,
            "scenes": [
                {"scene_index": 0, "start_time": 0, "end_time": 5, "description": "hook"},
                {"scene_index": 1, "start_time": 5, "end_time": 15, "description": "intro"},
                {"scene_index": 2, "start_time": 15, "end_time": 40, "description": "body"},
                {"scene_index": 3, "start_time": 40, "end_time": 55, "description": "recap"},
                {"scene_index": 4, "start_time": 55, "end_time": 60, "description": "cta"},
            ],
            "pacing_profile": {"cuts_per_minute": 5.0},
        },
    }


class TestV1BriefRegression:
    def test_schema_file_still_exists(self):
        assert BRIEF_SCHEMA_PATH.exists()

    def test_schema_still_loads(self):
        schema = load_schema("video_analysis_brief")
        assert schema["title"] == "video_analysis_brief"
        # v1.0 omits $id per historical convention — assert the shape we remember.
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"

    def test_sample_artifact_still_validates(self):
        schema = load_schema("video_analysis_brief")
        fixture = _minimal_brief()
        jsonschema.validate(instance=fixture, schema=schema)  # must not raise

    def test_validate_artifact_helper_still_works(self):
        # End-to-end: schemas.artifacts.validate_artifact("video_analysis_brief", ...) still works.
        validate_artifact("video_analysis_brief", _minimal_brief())

    def test_video_analysis_brief_still_in_artifact_names(self):
        assert "video_analysis_brief" in ARTIFACT_NAMES

    def test_schema_file_was_not_modified_in_this_phase(self):
        """Guardrail: phase scope explicitly forbids editing the v1.0 file.

        We assert a canonical top-level shape that Phase 1 must not have altered.
        If this fails, re-check that the edit in Plan 04 did not accidentally
        touch video_analysis_brief.schema.json.
        """
        schema = json.load(open(BRIEF_SCHEMA_PATH))
        assert schema["type"] == "object"
        assert set(schema["required"]) == {"version", "source", "content_analysis", "structure_analysis"}
        # version const is "1.0" — must not have drifted to "2.0".
        assert schema["properties"]["version"]["const"] == "1.0"
