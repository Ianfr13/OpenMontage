"""Phase 7 backward-compat gate — TEST-03.

All 12 (and any future) pipeline_defs/*.yaml load via lib.pipeline_loader
without raising. Catches any schema-breaking change to
schemas/pipelines/pipeline_manifest.schema.json before it ships.

Runs API-key-free. No network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import jsonschema
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.pipeline_loader import (  # noqa: E402
    PIPELINE_DEFS_DIR,
    list_pipelines,
    load_pipeline,
)

# Enumerate at collection time — each file becomes a test case (fan-out parametrize).
# Glob-at-collection (not hardcoded list) means any future pipeline added under
# pipeline_defs/*.yaml is automatically covered by the gate.
PIPELINE_YAMLS = sorted(PIPELINE_DEFS_DIR.glob("*.yaml"))
PIPELINE_NAMES = [p.stem for p in PIPELINE_YAMLS]


@pytest.mark.parametrize("name", PIPELINE_NAMES)
def test_all_v1_pipelines_load_via_loader(name: str):
    """TEST-03: every pipeline_defs/*.yaml loads + validates against manifest schema."""
    manifest = load_pipeline(name)
    assert isinstance(manifest, dict)
    assert "name" in manifest, f"{name}.yaml missing top-level 'name'"
    assert "stages" in manifest, f"{name}.yaml missing top-level 'stages'"
    assert isinstance(manifest["stages"], list)
    assert len(manifest["stages"]) > 0, f"{name}.yaml has empty stages list"


def test_twelve_pipelines_present():
    """TEST-03 deletion-lock: the 12 known v1 pipelines must be present.

    Uses >= on the total count so future additions do not break this test —
    only deletions of the v1 set are caught. A raw == 12 would be
    surface-brittle to intentional growth.
    """
    names = list_pipelines()
    assert len(names) >= 12, (
        f"Expected >=12 pipelines, found {len(names)}: {sorted(names)}"
    )
    v1_names = {
        "animated-explainer", "animation", "avatar-spokesperson",
        "cinematic", "clip-factory", "documentary-montage",
        "framework-smoke", "hybrid", "localization-dub",
        "podcast-repurpose", "screen-demo", "talking-head",
    }
    missing = v1_names - set(names)
    assert not missing, f"Deleted v1 pipelines (regression): {sorted(missing)}"


def test_staging_exclusion(tmp_path):
    """SYNTH-07 defense-in-depth: list_pipelines() never yields _staging/ files."""
    defs = tmp_path / "pipeline_defs"
    (defs / "_staging").mkdir(parents=True)
    (defs / "visible.yaml").write_text("name: v\nstages: []\n")
    (defs / "_staging" / "ghost.yaml").write_text("name: g\nstages: []\n")
    names = list_pipelines(defs_dir=defs)
    assert "visible" in names
    assert "ghost" not in names


@pytest.mark.parametrize("name", PIPELINE_NAMES)
def test_pipeline_has_expected_analysis(name: str):
    """Phase 5 (Plan 05-01) annotated all 12 with `expected_analysis`.

    This lock test prevents silent drift: if a pipeline loses its
    expected_analysis dict, the matcher (lib/pipeline_synthesizer.py
    match_base_pipeline) would silently score 0 against it.
    """
    manifest = load_pipeline(name)
    exp = manifest.get("expected_analysis")
    assert isinstance(exp, dict), (
        f"{name}.yaml missing or non-dict expected_analysis "
        f"(Plan 05-01 annotation regression)"
    )


def test_manifest_schema_validation(tmp_path):
    """load_pipeline must raise jsonschema.ValidationError on invalid manifest.

    Locks the schema-gate itself — if someone loosens
    schemas/pipelines/pipeline_manifest.schema.json to the point where a
    manifest missing `stages` validates, this test will fail first.
    """
    defs = tmp_path / "pipeline_defs"
    defs.mkdir()
    # Missing required 'stages' field — whatever else the schema requires,
    # 'stages' is a v1 invariant.
    (defs / "broken.yaml").write_text("name: broken\n")
    with pytest.raises((jsonschema.ValidationError, KeyError)):
        load_pipeline("broken", defs_dir=defs)
