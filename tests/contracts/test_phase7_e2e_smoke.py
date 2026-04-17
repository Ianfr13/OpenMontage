"""Phase 7 E2E smoke — TEST-04.

Exercises the full Phase 6 `reference-synthesis.md` meta-skill flow end to
end with ZERO real API calls:

    canonical video_analysis artifact
      -> synthesize_pipeline(mode='template') -> _staging/<slug>.yaml
      -> validate_synthesized_pipeline -> [] (valid)
      -> accept_synthesis(slug) -> pipeline_defs/<slug>.yaml
      -> load_pipeline(slug) -> same manifest, schema-validated

Also locks the reject path and record-shape invariants (diff_against_base,
idempotent slug on re-run).

LLM fill is mocked to identity (deepcopy base). No OPENROUTER_API_KEY is
required. The synthesizer's ``use_llm_fill=True`` path is exercised with
the mock so the helper's "post-merge validation" branch is covered too.

Mirrors the isolated_defs pattern from test_phase5_synthesis.py to avoid
polluting the real pipeline_defs/.
"""
from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml as pyyaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from schemas.artifacts import load_schema  # noqa: E402
from tests.contracts.test_video_analysis_schema import (  # noqa: E402
    minimal_video_analysis,
)


@pytest.fixture
def isolated_defs(tmp_path, monkeypatch):
    """Copy real pipeline_defs/ to tmp; repoint synthesizer + loader constants.

    Same pattern as tests/contracts/test_phase5_synthesis.py -- keeps the
    real repo pipeline_defs/ immutable during tests.
    """
    src = PROJECT_ROOT / "pipeline_defs"
    dst = tmp_path / "pipeline_defs"
    shutil.copytree(src, dst)

    import lib.pipeline_loader as pl
    import lib.pipeline_synthesizer as ps

    monkeypatch.setattr(pl, "PIPELINE_DEFS_DIR", dst)
    monkeypatch.setattr(ps, "PIPELINE_DEFS_DIR", dst)
    monkeypatch.setattr(ps, "STAGING_DIR", dst / "_staging")

    # Mock LLM fill to identity -- deepcopy base, no openai client touched.
    import lib.llm_fill as lf

    monkeypatch.setattr(
        lf,
        "fill_stage_details",
        lambda base, analysis, *, mode: copy.deepcopy(base),
    )
    # Ensure env doesn't force-disable the fill-path branch.
    monkeypatch.setenv("VIDEO_SYNTH_LLM_FILL", "true")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    return dst


def _canonical_analysis() -> dict:
    """Deep copy of the Phase 1 minimal fixture."""
    return copy.deepcopy(minimal_video_analysis())


# ---------------------------------------------------------------------------
# Test 1: full flow -- synthesize -> validate -> accept -> load_pipeline
# ---------------------------------------------------------------------------


def test_e2e_mocked_synthesis_accept_roundtrip(isolated_defs):
    """TEST-04: full flow -- synthesize -> validate -> accept -> load_pipeline."""
    from lib.pipeline_loader import load_pipeline
    from lib.pipeline_synthesizer import (
        accept_synthesis,
        synthesize_pipeline,
        validate_synthesized_pipeline,
    )

    record = synthesize_pipeline(_canonical_analysis(), mode="template")
    assert record["validation_status"] == "valid", (
        f"Synthesis validation failed: {record.get('validation_status')}"
    )
    assert record["staging_path"].startswith("pipeline_defs/_staging/")

    # Record passes the pipeline_synthesis schema.
    jsonschema.validate(
        instance=record, schema=load_schema("pipeline_synthesis")
    )

    # Staged file exists.
    slug = Path(record["staging_path"]).stem
    staged = isolated_defs / "_staging" / f"{slug}.yaml"
    assert staged.exists()
    staged_manifest = pyyaml.safe_load(staged.read_text(encoding="utf-8"))
    assert validate_synthesized_pipeline(staged_manifest) == []

    # Accept -- moves to pipeline_defs/.
    promoted_path, accept_record = accept_synthesis(slug)
    assert promoted_path == isolated_defs / f"{slug}.yaml"
    assert promoted_path.exists()
    assert not staged.exists(), "Staged file must be gone after accept"

    # Round-trip: load_pipeline on promoted file returns the same manifest
    # shape that was staged (ignoring YAML rewrite differences on comments).
    loaded = load_pipeline(slug)
    assert loaded["name"] == staged_manifest["name"]
    assert loaded["stages"] == staged_manifest["stages"]

    # Accept record validates.
    jsonschema.validate(
        instance=accept_record, schema=load_schema("pipeline_synthesis")
    )


# ---------------------------------------------------------------------------
# Test 2: reject path -- staged file deleted, no pipeline_defs/<slug>.yaml
# ---------------------------------------------------------------------------


def test_e2e_mocked_synthesis_reject(isolated_defs):
    """TEST-04: reject path -- staged deleted, no pipeline_defs/<slug>.yaml."""
    from lib.pipeline_synthesizer import reject_synthesis, synthesize_pipeline

    record = synthesize_pipeline(_canonical_analysis(), mode="template")
    slug = Path(record["staging_path"]).stem
    staged = isolated_defs / "_staging" / f"{slug}.yaml"
    assert staged.exists()

    reject_record = reject_synthesis(slug)
    # Phase 5 contract: schema has no "rejected"; user rejection is "invalid".
    assert reject_record["validation_status"] == "invalid"
    assert not staged.exists(), "Reject must delete staging file"
    assert not (isolated_defs / f"{slug}.yaml").exists(), (
        "Reject must NOT promote to pipeline_defs/"
    )


# ---------------------------------------------------------------------------
# Test 3: diff_against_base is either empty or unified-diff-shaped
# ---------------------------------------------------------------------------


def test_e2e_record_has_diff_against_base_shape(isolated_defs):
    """TEST-04: diff_against_base is either empty or unified-diff-shaped.

    Phase 6's reference-synthesis.md meta-skill presents this string to the
    user for approval. Lock the shape invariant here so Phase 6's assumption
    holds.
    """
    from lib.pipeline_synthesizer import synthesize_pipeline

    record = synthesize_pipeline(_canonical_analysis(), mode="template")
    diff = record["diff_against_base"]
    assert isinstance(diff, str)
    if diff:
        # unified-diff headers -- first non-empty line must start with ``---``.
        first_line = diff.splitlines()[0]
        assert first_line.startswith("---"), (
            f"Non-empty diff must start with unified-diff header; got {first_line!r}"
        )


# ---------------------------------------------------------------------------
# Test 4: idempotent slug across runs (SYNTH-06)
# ---------------------------------------------------------------------------


def test_e2e_idempotent_slug(isolated_defs):
    """SYNTH-06: same analysis -> same slug across runs; no silent overwrite."""
    from lib.pipeline_synthesizer import synthesize_pipeline

    analysis = _canonical_analysis()
    r1 = synthesize_pipeline(analysis, mode="template")
    r2 = synthesize_pipeline(analysis, mode="template")

    slug1 = Path(r1["staging_path"]).stem
    # r2 may end in "-v2" if the body drifted (timestamp-aware body compare in
    # _write_staging excludes timestamp lines, so byte-equal runs reuse the
    # same path and the stem stays stable).
    slug2 = Path(r2["staging_path"]).stem
    # Base slug prefix MUST be stable across runs (deterministic from checksum).
    base_stem = slug1
    assert slug2 == base_stem or slug2.startswith(base_stem + "-v"), (
        f"Second run slug {slug2!r} must reuse or -vN-suffix the base {base_stem!r}"
    )

    # Either way, the second staged file exists under _staging/.
    staged2 = isolated_defs / "_staging" / Path(r2["staging_path"]).name
    assert staged2.exists()
