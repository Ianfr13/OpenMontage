"""Unit tests for accept_synthesis / reject_synthesis (Phase 5 Plan 05-03).

Covers SYNTH-10 (accept/reject API) + LLM fill wiring into synthesize_pipeline.

Tests:
   1 test_accept_moves_file                    — staging → pipeline_defs/ move
   2 test_accept_returns_path_and_record       — returns (Path, record) tuple
   3 test_accept_rejects_existing_target       — FileExistsError, no side effects
   4 test_accept_missing_staging_raises        — FileNotFoundError
   5 test_reject_deletes_staging               — staging unlinked
   6 test_reject_missing_staging_raises        — FileNotFoundError
   7 test_accept_record_schema_valid           — emitted record passes jsonschema (pipeline_acceptance)
   8 test_reject_record_schema_valid           — emitted record passes jsonschema (pipeline_rejection)
   9 test_llm_fill_wired_into_synthesize       — marker propagates through synth
  10 test_llm_fill_env_controlled              — VIDEO_SYNTH_LLM_FILL=false is honored
  11 test_llm_fill_use_llm_fill_false_no_call  — mock assert_not_called
"""

from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock

import jsonschema
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Analysis fixture — matches the contract test shape
# ---------------------------------------------------------------------------


def _minimal_analysis() -> dict:
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
    """Copy real pipeline_defs/ to tmp and repoint module constants.

    Mirrors the contract-test fixture so accept/reject tests match the
    same filesystem layout the synthesizer uses in production.
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


def _stage_file(defs_dir: Path, slug: str) -> Path:
    """Stage a copy of cinematic.yaml under _staging/<slug>.yaml."""
    staging = defs_dir / "_staging"
    staging.mkdir(parents=True, exist_ok=True)
    src = defs_dir / "cinematic.yaml"
    dst = staging / f"{slug}.yaml"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dst


# ---------------------------------------------------------------------------
# Test 1: accept moves file
# ---------------------------------------------------------------------------


def test_accept_moves_file(isolated_defs):
    # Canonical _build_slug shape (base-hex8) — ≥8 chars, lowercase, hyphen-safe
    # (CLEAN-08 slug regex).
    _stage_file(isolated_defs, "foo-abcd1234")
    assert (isolated_defs / "_staging" / "foo-abcd1234.yaml").exists()
    assert not (isolated_defs / "foo-abcd1234.yaml").exists()

    from lib.pipeline_synthesizer import accept_synthesis

    promoted, _record = accept_synthesis("foo-abcd1234")

    assert not (isolated_defs / "_staging" / "foo-abcd1234.yaml").exists(), (
        "staging file should be moved, not copied"
    )
    assert (isolated_defs / "foo-abcd1234.yaml").exists()
    assert promoted == (isolated_defs / "foo-abcd1234.yaml")


# ---------------------------------------------------------------------------
# Test 2: accept returns (Path, record) tuple
# ---------------------------------------------------------------------------


def test_accept_returns_path_and_record(isolated_defs):
    _stage_file(isolated_defs, "foo-abcd1234")

    from lib.pipeline_synthesizer import accept_synthesis

    result = accept_synthesis("foo-abcd1234")
    assert isinstance(result, tuple)
    assert len(result) == 2
    path, record = result
    assert isinstance(path, Path)
    assert isinstance(record, dict)


# ---------------------------------------------------------------------------
# Test 3: accept into existing target → FileExistsError; staging preserved
# ---------------------------------------------------------------------------


def test_accept_rejects_existing_target(isolated_defs):
    _stage_file(isolated_defs, "cinematic")  # collides with pipeline_defs/cinematic.yaml

    from lib.pipeline_synthesizer import accept_synthesis

    with pytest.raises(FileExistsError):
        accept_synthesis("cinematic")

    # staging untouched — no partial state
    assert (isolated_defs / "_staging" / "cinematic.yaml").exists()


# ---------------------------------------------------------------------------
# Test 4: accept on missing staging → FileNotFoundError
# ---------------------------------------------------------------------------


def test_accept_missing_staging_raises(isolated_defs):
    from lib.pipeline_synthesizer import accept_synthesis

    with pytest.raises(FileNotFoundError):
        accept_synthesis("does-not-exist")


# ---------------------------------------------------------------------------
# Test 5: reject deletes staging
# ---------------------------------------------------------------------------


def test_reject_deletes_staging(isolated_defs):
    staged = _stage_file(isolated_defs, "foo-abcd1234")
    assert staged.exists()

    from lib.pipeline_synthesizer import reject_synthesis

    record = reject_synthesis("foo-abcd1234")

    assert not staged.exists()
    # pipeline_defs/foo-abcd1234.yaml was never created
    assert not (isolated_defs / "foo-abcd1234.yaml").exists()
    assert isinstance(record, dict)


# ---------------------------------------------------------------------------
# Test 6: reject on missing staging → FileNotFoundError
# ---------------------------------------------------------------------------


def test_reject_missing_staging_raises(isolated_defs):
    from lib.pipeline_synthesizer import reject_synthesis

    with pytest.raises(FileNotFoundError):
        reject_synthesis("does-not-exist")


# ---------------------------------------------------------------------------
# Test 7: accept record schema-valid
# ---------------------------------------------------------------------------


def test_accept_record_schema_valid(isolated_defs):
    _stage_file(isolated_defs, "foo-abcd1234")

    from lib.pipeline_synthesizer import accept_synthesis
    from schemas.artifacts import load_schema

    _path, record = accept_synthesis("foo-abcd1234")
    # CLEAN-09 / v2.0 Phase 5 REVIEW MR-02: post-accept records validate
    # against pipeline_acceptance, NOT pipeline_synthesis.
    schema = load_schema("pipeline_acceptance")
    # Must not raise.
    jsonschema.validate(instance=record, schema=schema)
    assert record["validation_status"] in ("valid", "invalid")
    assert record["version"] == "1.0"
    assert "promoted_slug" in record and record["promoted_slug"] == "foo-abcd1234"


# ---------------------------------------------------------------------------
# Test 8: reject record validates against pipeline_rejection (CLEAN-09)
# ---------------------------------------------------------------------------


def test_reject_record_schema_valid(isolated_defs):
    _stage_file(isolated_defs, "foo-abcd1234")

    from lib.pipeline_synthesizer import reject_synthesis
    from schemas.artifacts import load_schema

    record = reject_synthesis("foo-abcd1234")
    # CLEAN-09 / v2.0 Phase 5 REVIEW MR-02: rejection has its own schema
    # (pipeline_rejection) — no more reusing pipeline_synthesis with the
    # Pitfall 2 validation_status="invalid" hack.
    schema = load_schema("pipeline_rejection")
    jsonschema.validate(instance=record, schema=schema)
    assert "rejected_slug" in record and record["rejected_slug"] == "foo-abcd1234"
    assert "validation_status" not in record, (
        "Rejection is its own event (CLEAN-09 / v2.0 Phase 5 REVIEW MR-02); "
        "it no longer reuses validation_status as a user-rejection proxy."
    )


# ---------------------------------------------------------------------------
# Test 9: LLM fill marker propagates through synthesize_pipeline
# ---------------------------------------------------------------------------


def test_llm_fill_wired_into_synthesize(isolated_defs, monkeypatch):
    """synthesize_pipeline(use_llm_fill=True) must call fill_stage_details."""
    monkeypatch.setenv("VIDEO_SYNTH_LLM_FILL", "true")

    marker_tool = "MARKER_TOOL_LLM_FILL_WAS_HERE"

    def _fake_fill(base, analysis, *, mode):  # noqa: ARG001
        out = copy.deepcopy(base)
        # Inject the marker into the FIRST stage's tools_available so we can
        # find it in the staged YAML.
        if out.get("stages"):
            out["stages"][0]["tools_available"] = [marker_tool]
        return out

    import lib.llm_fill as lf
    import lib.pipeline_synthesizer as ps

    monkeypatch.setattr(lf, "fill_stage_details", _fake_fill)
    # Also patch the re-import-time reference inside the synthesizer if any.

    record = ps.synthesize_pipeline(
        _minimal_analysis(), mode="template", use_llm_fill=True
    )
    staged = isolated_defs / "_staging" / Path(record["staging_path"]).name
    content = staged.read_text(encoding="utf-8")
    assert marker_tool in content, "LLM-fill marker must appear in staged YAML"


# ---------------------------------------------------------------------------
# Test 10: VIDEO_SYNTH_LLM_FILL=false disables env-controlled path
# ---------------------------------------------------------------------------


def test_llm_fill_env_controlled(isolated_defs, monkeypatch):
    """With env=false, synthesize without use_llm_fill argument skips fill."""
    monkeypatch.setenv("VIDEO_SYNTH_LLM_FILL", "false")

    called = {"n": 0}

    def _fake_fill(*args, **kwargs):  # noqa: ARG001
        called["n"] += 1
        return args[0]

    import lib.llm_fill as lf
    import lib.pipeline_synthesizer as ps

    monkeypatch.setattr(lf, "fill_stage_details", _fake_fill)

    ps.synthesize_pipeline(_minimal_analysis(), mode="template")
    assert called["n"] == 0, "fill_stage_details must not be called when env=false"


# ---------------------------------------------------------------------------
# Test 11: use_llm_fill=False explicit skip (mock assert_not_called)
# ---------------------------------------------------------------------------


def test_llm_fill_use_llm_fill_false_no_call(isolated_defs, monkeypatch):
    monkeypatch.setenv("VIDEO_SYNTH_LLM_FILL", "true")  # env would enable

    import lib.llm_fill as lf
    import lib.pipeline_synthesizer as ps

    spy = MagicMock(side_effect=lambda base, *a, **kw: base)  # noqa: ARG005
    monkeypatch.setattr(lf, "fill_stage_details", spy)

    ps.synthesize_pipeline(
        _minimal_analysis(), mode="template", use_llm_fill=False
    )
    spy.assert_not_called()


# ---------------------------------------------------------------------------
# CLEAN-08 / v2.0 Phase 5 REVIEW MR-01 — slug validation tests
# ---------------------------------------------------------------------------

#: Traversal + malformed payloads covered by _SLUG_RE and the resolved-path
#: guard. Includes empty, too-short (7 chars), uppercase, slash, leading dot,
#: absolute, whitespace, shell-metachar, and backslash cases. See
#: 05-REVIEW.md MR-01 for the full vector set.
_MALFORMED_SLUGS = [
    "",
    "a",
    "abcdef1",             # 7 chars — below {7,127} minimum (needs 8+)
    "Foo-abcdef12",        # uppercase — regex is lowercase-only
    "foo/bar",             # slash
    "../cinematic",        # traversal
    "..",                  # traversal
    "/cinematic",          # absolute
    "foo bar",             # whitespace
    "foo;rm",              # shell metachar
    "foo\\bar",            # backslash
]


@pytest.mark.parametrize("bad_slug", _MALFORMED_SLUGS)
def test_accept_rejects_malformed_slug(isolated_defs, bad_slug):
    """accept_synthesis must raise InvalidPipelineSlug on any malformed /
    traversal payload BEFORE touching the filesystem (CLEAN-08)."""
    from lib.analysis_errors import InvalidPipelineSlug
    from lib.pipeline_synthesizer import accept_synthesis

    with pytest.raises(InvalidPipelineSlug):
        accept_synthesis(bad_slug)


@pytest.mark.parametrize("bad_slug", _MALFORMED_SLUGS)
def test_reject_rejects_malformed_slug(isolated_defs, bad_slug):
    """reject_synthesis applies the identical guard — path-traversal payloads
    never reach src.unlink() (CLEAN-08)."""
    from lib.analysis_errors import InvalidPipelineSlug
    from lib.pipeline_synthesizer import reject_synthesis

    with pytest.raises(InvalidPipelineSlug):
        reject_synthesis(bad_slug)


def test_accept_happy_path_canonical_slug_still_works(isolated_defs):
    """Canonical _build_slug output (``<base>-<hex[:8]>``) passes the regex
    unchanged — locks the validator against future over-tightening."""
    _stage_file(isolated_defs, "cinematic-a1b2c3d4")

    from lib.pipeline_synthesizer import accept_synthesis

    promoted, _record = accept_synthesis("cinematic-a1b2c3d4")
    assert promoted.name == "cinematic-a1b2c3d4.yaml"
    assert promoted.exists()


def test_invalid_pipeline_slug_is_video_analysis_error():
    """Inheritance lock — ``except VideoAnalysisError`` umbrella-handlers
    established in Phase 8 / Phase 9 MUST still catch the new sentinel."""
    from lib.analysis_errors import InvalidPipelineSlug, VideoAnalysisError

    assert issubclass(InvalidPipelineSlug, VideoAnalysisError)
    assert isinstance(InvalidPipelineSlug("x"), VideoAnalysisError)


def test_accept_slug_validation_short_circuits_filesystem(isolated_defs):
    """Malformed slug MUST short-circuit before any shutil/os call — the
    staged file is untouched and no target file is created."""
    from lib.analysis_errors import InvalidPipelineSlug
    from lib.pipeline_synthesizer import accept_synthesis

    staged = _stage_file(isolated_defs, "cinematic-a1b2c3d4")
    assert staged.exists()

    with pytest.raises(InvalidPipelineSlug):
        accept_synthesis("../cinematic-a1b2c3d4")

    # Untouched — validation short-circuited before shutil.move.
    assert staged.exists()
    assert not (isolated_defs / "cinematic-a1b2c3d4.yaml").exists()
