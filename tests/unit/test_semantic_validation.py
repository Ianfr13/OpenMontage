"""Unit tests for semantic validation + loader hardening (Phase 5 Plan 05-02).

Covers SYNTH-07 (loader underscore-prefix filter) and SYNTH-08 (semantic validator).

9 behaviors:
  1. test_loader_excludes_staging          — `_staging/` YAMLs invisible in list_pipelines
  2. test_loader_underscore_filter_on_recursive — filter catches underscore subdirs even w/ **/*.yaml
  3. test_validate_empty_returns_no_issues — valid cinematic manifest → []
  4. test_validate_missing_skill           — bad skill path → issues list includes skill
  5. test_validate_unknown_tool            — unregistered tool → issues list includes tool
  6. test_validate_discovers_tools         — fresh registry auto-discovers via ensure_discovered
  7. test_synthesis_validation_error_raises — raise_if_invalid raises with .issues populated
  8. test_no_skill_field_is_ok             — stage with only `agent:` does not trigger missing-skill
  9. test_no_tools_available_is_ok         — stage with empty/None tools_available is not an issue
"""

from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_defs(tmp_path, monkeypatch):
    """Copy real pipeline_defs/ to a tmp dir and repoint module constants.

    Tests write only under the tmp tree — never touch the real repo.
    """
    src = _REPO_ROOT / "pipeline_defs"
    dst = tmp_path / "pipeline_defs"
    shutil.copytree(src, dst)

    import lib.pipeline_loader as pl
    import lib.pipeline_synthesizer as ps

    monkeypatch.setattr(pl, "PIPELINE_DEFS_DIR", dst)
    monkeypatch.setattr(ps, "PIPELINE_DEFS_DIR", dst)
    monkeypatch.setattr(ps, "STAGING_DIR", dst / "_staging")
    return dst


@pytest.fixture
def valid_manifest():
    """Load the real cinematic manifest — every skill exists and all tools are registered."""
    from lib.pipeline_loader import load_pipeline

    return copy.deepcopy(load_pipeline("cinematic"))


# ---------------------------------------------------------------------------
# Test 1: SYNTH-07 — loader excludes _staging/ and other underscore subdirs
# ---------------------------------------------------------------------------


def test_loader_excludes_staging(isolated_defs):
    """`list_pipelines()` returns neither `_staging/fake.yaml` nor `_other/also.yaml`.

    Real pipelines (cinematic, animated-explainer, …) still returned.
    """
    # Seed underscore-prefixed subdirs with a YAML each
    (isolated_defs / "_staging").mkdir(parents=True, exist_ok=True)
    (isolated_defs / "_staging" / "fake.yaml").write_text("name: fake\nversion: '1.0'\nstages: []\n")

    (isolated_defs / "_other").mkdir(parents=True, exist_ok=True)
    (isolated_defs / "_other" / "also.yaml").write_text("name: also\nversion: '1.0'\nstages: []\n")

    from lib.pipeline_loader import list_pipelines

    names = set(list_pipelines())
    assert "fake" not in names
    assert "also" not in names
    # Real pipelines still present
    assert "cinematic" in names
    assert "animated-explainer" in names


# ---------------------------------------------------------------------------
# Test 2: SYNTH-07 — filter applies even under a recursive glob (defense-in-depth)
# ---------------------------------------------------------------------------


def test_loader_underscore_filter_on_recursive(isolated_defs, monkeypatch):
    """Simulate a future recursive glob via a Path subclass wrapper.

    Confirms the `startswith("_")` filter STILL hides underscore-prefixed
    parent directories even if a later refactor expands the glob pattern.
    """
    (isolated_defs / "_staging").mkdir(parents=True, exist_ok=True)
    (isolated_defs / "_staging" / "fake.yaml").write_text(
        "name: fake\nversion: '1.0'\nstages: []\n"
    )

    # Wrap Path.glob to force a recursive iteration through the underscore subdir.
    from lib import pipeline_loader as pl

    real_glob = Path.glob

    def recursive_glob(self, pattern):
        if pattern == "*.yaml":
            # Force recursive behavior
            return real_glob(self, "**/*.yaml")
        return real_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", recursive_glob)

    names = set(pl.list_pipelines())
    # Even with recursive glob, underscore subdir must be excluded
    assert "fake" not in names, (
        f"list_pipelines() leaked _staging/fake.yaml under recursive glob — "
        f"SYNTH-07 defense-in-depth filter is missing. names={sorted(names)}"
    )


# ---------------------------------------------------------------------------
# Test 3: SYNTH-08 — valid manifest returns empty issue list
# ---------------------------------------------------------------------------


def test_validate_empty_returns_no_issues(valid_manifest):
    from lib.pipeline_synthesizer import validate_synthesized_pipeline

    issues = validate_synthesized_pipeline(valid_manifest)
    assert issues == [], f"expected no issues for valid cinematic manifest, got: {issues}"


# ---------------------------------------------------------------------------
# Test 4: SYNTH-08 — missing skill file is reported
# ---------------------------------------------------------------------------


def test_validate_missing_skill(valid_manifest):
    from lib.pipeline_synthesizer import validate_synthesized_pipeline

    manifest = copy.deepcopy(valid_manifest)
    # Flip the first stage's skill to a path that definitely doesn't exist
    assert manifest["stages"][0].get("skill"), "fixture precondition: first stage has a skill"
    manifest["stages"][0]["skill"] = "pipelines/cinematic/does-not-exist"

    issues = validate_synthesized_pipeline(manifest)
    # Exactly one issue, and it mentions both the stage name and the path
    assert issues, "expected at least one issue for missing skill file"
    stage_name = manifest["stages"][0]["name"]
    matching = [i for i in issues if stage_name in i and "does-not-exist" in i]
    assert matching, (
        f"expected an issue mentioning stage {stage_name!r} and the bad skill path; "
        f"got: {issues}"
    )


# ---------------------------------------------------------------------------
# Test 5: SYNTH-08 — unregistered tool is reported
# ---------------------------------------------------------------------------


def test_validate_unknown_tool(valid_manifest):
    from lib.pipeline_synthesizer import validate_synthesized_pipeline

    manifest = copy.deepcopy(valid_manifest)
    # Pick the first stage that has a non-empty tools_available list,
    # or seed one if all are empty.
    target_stage = None
    for stage in manifest["stages"]:
        existing = list(stage.get("tools_available") or [])
        if existing:
            stage["tools_available"] = existing + ["not_a_real_tool_12345"]
            target_stage = stage
            break
    if target_stage is None:
        manifest["stages"][0]["tools_available"] = ["not_a_real_tool_12345"]
        target_stage = manifest["stages"][0]

    issues = validate_synthesized_pipeline(manifest)
    matching = [
        i for i in issues
        if "not_a_real_tool_12345" in i and "registry" in i.lower()
    ]
    assert matching, f"expected an issue mentioning the unknown tool and registry; got: {issues}"


# ---------------------------------------------------------------------------
# Test 6: SYNTH-08 — validator calls ensure_discovered() even on a fresh registry
# ---------------------------------------------------------------------------


def test_validate_discovers_tools(valid_manifest):
    """Clear the registry; validate still passes because ensure_discovered runs internally."""
    from tools.tool_registry import registry

    from lib.pipeline_synthesizer import validate_synthesized_pipeline

    registry.clear()
    assert registry.list_all() == [], "precondition: registry cleared"

    issues = validate_synthesized_pipeline(valid_manifest)
    assert issues == [], f"expected empty issues after auto-discovery; got: {issues}"
    # And confirm discovery actually happened (tools now registered)
    assert registry.list_all(), "ensure_discovered() was not invoked by validator"


# ---------------------------------------------------------------------------
# Test 7: SYNTH-08 — raise_if_invalid raises with populated .issues
# ---------------------------------------------------------------------------


def test_synthesis_validation_error_raises(valid_manifest):
    from lib.pipeline_synthesizer import (
        SynthesisValidationError,
        raise_if_invalid,
    )

    manifest = copy.deepcopy(valid_manifest)
    manifest["stages"][0]["skill"] = "pipelines/cinematic/missing-skill-xyz"
    # Also sneak an unknown tool in to get >1 issue
    existing = list(manifest["stages"][0].get("tools_available") or [])
    manifest["stages"][0]["tools_available"] = existing + ["bogus_tool_abc"]

    with pytest.raises(SynthesisValidationError) as exc_info:
        raise_if_invalid(manifest)

    err = exc_info.value
    assert isinstance(err.issues, list)
    assert len(err.issues) >= 2
    # str(exc) joins issues with newlines
    text = str(err)
    for issue in err.issues:
        assert issue in text
    # Happy path does not raise
    raise_if_invalid(valid_manifest)


# ---------------------------------------------------------------------------
# Test 8: SYNTH-08 — agent-only stage (no skill key) is not flagged
# ---------------------------------------------------------------------------


def test_no_skill_field_is_ok(valid_manifest):
    from lib.pipeline_synthesizer import validate_synthesized_pipeline

    manifest = copy.deepcopy(valid_manifest)
    # Convert first stage to agent-only legacy shape
    first = manifest["stages"][0]
    first.pop("skill", None)
    first["agent"] = "LegacyStage"

    issues = validate_synthesized_pipeline(manifest)
    # No "skill file not found" issue — that stage had no skill to check.
    skill_issues = [i for i in issues if "skill file not found" in i and first["name"] in i]
    assert skill_issues == [], (
        f"stage with no `skill` field should not be flagged; got: {skill_issues}"
    )


# ---------------------------------------------------------------------------
# Test 9: SYNTH-08 — missing / empty tools_available is not an issue
# ---------------------------------------------------------------------------


def test_no_tools_available_is_ok(valid_manifest):
    from lib.pipeline_synthesizer import validate_synthesized_pipeline

    manifest = copy.deepcopy(valid_manifest)
    first = manifest["stages"][0]
    first["tools_available"] = []  # explicitly empty
    # And another with the key dropped entirely
    second = manifest["stages"][1]
    second.pop("tools_available", None)

    issues = validate_synthesized_pipeline(manifest)
    # Look for any issue with tools — there should be none on these two stages.
    for stage_name in (first["name"], second["name"]):
        bad = [i for i in issues if stage_name in i and "tool" in i.lower()]
        assert bad == [], f"stage {stage_name!r} should produce no tool issues; got: {bad}"
