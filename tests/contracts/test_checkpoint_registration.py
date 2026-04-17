"""Phase 1 contract tests — checkpoint + artifact-name registration (INT-04).

Verifies that:
  1. The two new artifact names appear in ARTIFACT_NAMES (so
     _validate_artifacts_for_stage does not silently skip them).
  2. The two new stages map to their canonical artifact in
     CANONICAL_STAGE_ARTIFACTS.
  3. validate_artifact(name, fixture) round-trips for both new artifacts
     on fixtures that also validate against the raw schema.
  4. All pre-existing entries in both registries are preserved.

Runs with no API keys or network.
"""
import sys
from pathlib import Path

import jsonschema
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from schemas.artifacts import ARTIFACT_NAMES, validate_artifact  # noqa: E402
from lib.checkpoint import CANONICAL_STAGE_ARTIFACTS, STAGES  # noqa: E402

# Original sets — Phase 1 must preserve these exactly.
ORIGINAL_ARTIFACT_NAMES = {
    "research_brief", "proposal_packet", "brief", "script", "scene_plan",
    "asset_manifest", "edit_decisions", "render_report", "publish_log",
    "review", "cost_log", "decision_log", "source_media_review",
    "final_review", "video_analysis_brief",
}
ORIGINAL_CANONICAL = {
    "research": "research_brief", "proposal": "proposal_packet",
    "idea": "brief", "script": "script", "scene_plan": "scene_plan",
    "assets": "asset_manifest", "edit": "edit_decisions",
    "compose": "render_report", "publish": "publish_log",
}


def _minimal_video_analysis() -> dict:
    # Mirrors Plan 01's minimal fixture. Keep in sync with
    # tests/contracts/test_video_analysis_schema.py::minimal_video_analysis.
    return {
        "version": "2.0",
        "source": {"type": "local_file", "duration_seconds": 45.0, "local_path": "/tmp/ref.mp4"},
        "editing_pacing": {
            "total_shots": 12, "cuts_per_minute": 16.0,
            "avg_shot_duration_seconds": 3.75, "pacing_style": "steady_educational",
            "shot_type_distribution": {"talking_head": 0.4, "b_roll": 0.3, "text_card": 0.2, "animation": 0.1},
            "motion_type_distribution": {"motion_clip": 5, "animated_still": 4, "static_image": 3},
        },
        "audio": {"has_narration": True, "has_music": True,
                  "narration_style": "voice_over", "voice_music_mix": "narration_dominant"},
        "visual_style": {
            "color_palette": {"primary": ["#0A84FF"], "accent": ["#FF375F"], "background": ["#000000"], "text": ["#FFFFFF"]},
            "production_quality": "professional", "aspect_ratio": "16:9",
        },
        "narrative": {
            "hook_type": "question", "narrative_arc": "problem_solution",
            "target_platform": "youtube_long", "target_duration_seconds": 45.0,
            "content_tone": "educational",
        },
    }


def _minimal_synthesis() -> dict:
    return {
        "version": "1.0",
        "base_pipeline": "animated-explainer",
        "match_score": 0.82,
        "mode": "template",
        "staging_path": "pipeline_defs/_staging/ref-abc123.yaml",
        "diff_against_base": "--- base\n+++ synth\n",
        "validation_status": "pending",
        "source_analysis_checksum": "sha256:0123abcd",
        "provider_used": "gemini",
    }


class TestCheckpointRegistration:
    def test_artifact_names_has_video_analysis(self):
        assert "video_analysis" in ARTIFACT_NAMES

    def test_artifact_names_has_pipeline_synthesis(self):
        assert "pipeline_synthesis" in ARTIFACT_NAMES

    def test_canonical_stage_artifacts_video_analysis(self):
        assert CANONICAL_STAGE_ARTIFACTS["video_analysis"] == "video_analysis"

    def test_canonical_stage_artifacts_pipeline_synthesis(self):
        assert CANONICAL_STAGE_ARTIFACTS["pipeline_synthesis"] == "pipeline_synthesis"

    def test_all_original_artifact_names_preserved(self):
        assert ORIGINAL_ARTIFACT_NAMES <= set(ARTIFACT_NAMES)

    def test_all_original_canonical_stage_artifacts_preserved(self):
        for stage, artifact in ORIGINAL_CANONICAL.items():
            assert CANONICAL_STAGE_ARTIFACTS[stage] == artifact

    def test_stages_list_unchanged(self):
        """Phase 1 must NOT add new stages to STAGES (per RESEARCH Finding 8)."""
        assert STAGES == ["research", "proposal", "idea", "script",
                          "scene_plan", "assets", "edit", "compose", "publish"]
        assert "video_analysis" not in STAGES
        assert "pipeline_synthesis" not in STAGES

    def test_validate_artifact_video_analysis_accepts_valid(self):
        # Must not raise.
        validate_artifact("video_analysis", _minimal_video_analysis())

    def test_validate_artifact_video_analysis_rejects_empty(self):
        with pytest.raises(jsonschema.ValidationError):
            validate_artifact("video_analysis", {})

    def test_validate_artifact_pipeline_synthesis_accepts_valid(self):
        validate_artifact("pipeline_synthesis", _minimal_synthesis())

    def test_validate_artifact_pipeline_synthesis_rejects_empty(self):
        with pytest.raises(jsonschema.ValidationError):
            validate_artifact("pipeline_synthesis", {})
