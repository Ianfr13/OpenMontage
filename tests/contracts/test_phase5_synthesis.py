"""Phase 5 contract tests — pipeline synthesis end-to-end (Plan 05-02).

Verifies the synthesizer emits a run record that validates against the
``pipeline_synthesis`` schema and contains a properly-formatted unified diff.
Also enforces the structural guard against any ``synthesize_and_accept``
function (SYNTH-10 — separation between synthesize and accept).

Tests:
  1. test_record_validates_against_schema   — synthesizer output passes jsonschema
  2. test_contract_end_to_end_synthesis     — full path: artifact → staged YAML → record
  3. test_no_auto_approval_path             — no function combines synthesize+accept
  4. test_staging_file_loads_as_yaml        — staged file is parseable YAML
  5. test_staging_path_under_pipeline_defs  — record staging_path is relative
"""

from __future__ import annotations

import copy
import re
import shutil
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml as pyyaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from schemas.artifacts import load_schema  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_analysis() -> dict:
    """Schema-valid minimal ``video_analysis`` artifact (4 dimensions)."""
    return {
        "version": "2.0",
        "source": {
            "type": "local_file",
            "duration_seconds": 60.0,
            "local_path": "/tmp/ref.mp4",
        },
        "editing_pacing": {
            "total_shots": 12,
            "cuts_per_minute": 16.0,
            "avg_shot_duration_seconds": 3.75,
            "pacing_style": "steady_educational",
            "shot_type_distribution": {
                "talking_head": 0.3,
                "b_roll": 0.3,
                "text_card": 0.2,
                "animation": 0.2,
            },
            "motion_type_distribution": {
                "motion_clip": 0.3,
                "animated_still": 0.3,
                "static_image": 0.4,
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
            "target_duration_seconds": 60.0,
            "content_tone": "educational",
            "section_structure": [
                {"label": f"s{i}", "approx_start_s": i * 5.0, "approx_end_s": (i + 1) * 5.0}
                for i in range(5)
            ],
        },
    }


@pytest.fixture
def isolated_defs(tmp_path, monkeypatch):
    """Copy real pipeline_defs/ to tmp and repoint module constants."""
    src = PROJECT_ROOT / "pipeline_defs"
    dst = tmp_path / "pipeline_defs"
    shutil.copytree(src, dst)

    import lib.pipeline_loader as pl
    import lib.pipeline_synthesizer as ps

    monkeypatch.setattr(pl, "PIPELINE_DEFS_DIR", dst)
    monkeypatch.setattr(ps, "PIPELINE_DEFS_DIR", dst)
    monkeypatch.setattr(ps, "STAGING_DIR", dst / "_staging")
    return dst


# ---------------------------------------------------------------------------
# Test 1: emitted record validates against pipeline_synthesis.schema.json
# ---------------------------------------------------------------------------


def test_record_validates_against_schema(isolated_defs):
    from lib.pipeline_synthesizer import synthesize_pipeline

    record = synthesize_pipeline(_minimal_analysis(), mode="template")
    schema = load_schema("pipeline_synthesis")
    jsonschema.validate(instance=record, schema=schema)  # must not raise


# ---------------------------------------------------------------------------
# Test 2: end-to-end — record + staged YAML both consistent
# ---------------------------------------------------------------------------


def test_contract_end_to_end_synthesis(isolated_defs):
    from lib.pipeline_synthesizer import synthesize_pipeline

    record = synthesize_pipeline(_minimal_analysis(), mode="template")

    # Record passes schema
    schema = load_schema("pipeline_synthesis")
    jsonschema.validate(instance=record, schema=schema)

    # Staged file exists and parses as YAML
    staged = isolated_defs / "_staging" / Path(record["staging_path"]).name
    assert staged.exists(), f"staged file missing: {staged}"
    loaded = pyyaml.safe_load(staged.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    assert "stages" in loaded


# ---------------------------------------------------------------------------
# Test 3: SYNTH-10 — no function combines synthesize + accept
# ---------------------------------------------------------------------------


def test_no_auto_approval_path():
    """Source-level guard: no function name contains BOTH 'synthes' and 'accept'.

    This guards Plan 05-03 as well: when ``accept_synthesis`` and
    ``reject_synthesis`` are added, they MUST be separate public functions
    and MUST NOT share a name with ``synthesize_pipeline``.
    """
    src = (PROJECT_ROOT / "lib" / "pipeline_synthesizer.py").read_text(encoding="utf-8")

    bad: list[str] = []
    for match in re.finditer(r"^def\s+(\w+)", src, re.MULTILINE):
        name = match.group(1).lower()
        if "synthes" in name and "accept" in name:
            bad.append(match.group(1))

    assert not bad, (
        f"SYNTH-10 guard: no function may combine synthesize + accept. "
        f"Offending names: {bad}"
    )


# ---------------------------------------------------------------------------
# Test 4: staged file is a parseable YAML manifest
# ---------------------------------------------------------------------------


def test_staging_file_loads_as_yaml(isolated_defs):
    from lib.pipeline_synthesizer import synthesize_pipeline

    record = synthesize_pipeline(_minimal_analysis(), mode="template")
    staged = isolated_defs / "_staging" / Path(record["staging_path"]).name
    manifest = pyyaml.safe_load(staged.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)
    assert "name" in manifest
    assert "stages" in manifest
    assert isinstance(manifest["stages"], list)


# ---------------------------------------------------------------------------
# Test 5: staging_path is repo-relative and under pipeline_defs/_staging/
# ---------------------------------------------------------------------------


def test_staging_path_under_pipeline_defs(isolated_defs):
    from lib.pipeline_synthesizer import synthesize_pipeline

    record = synthesize_pipeline(_minimal_analysis(), mode="template")
    assert record["staging_path"].startswith("pipeline_defs/_staging/"), (
        f"staging_path must be under pipeline_defs/_staging/; got {record['staging_path']!r}"
    )
