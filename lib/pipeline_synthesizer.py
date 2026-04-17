"""Pipeline synthesizer — core module (Phase 5, Plan 05-01).

Pure lib module (mirrors ``lib/playbook_generator.py``). **No class definitions.**
All public surface is module-level functions. This plan lands SYNTH-01, SYNTH-02,
SYNTH-04 (mode routing — LLM-fill branches deferred to Plan 05-03), SYNTH-05,
and SYNTH-06.

Responsibility chain for a single ``synthesize_pipeline(analysis)`` call:

    analysis -> _canonical_sha256 -> match_base_pipeline -> load base manifest
              -> (mode routing; LLM fill deferred to Plan 05-03)
              -> _build_slug -> _write_staging -> return run-record dict

Key invariants (enforced by tests):
  - The synthesizer NEVER writes outside ``pipeline_defs/_staging/`` (SYNTH-05).
  - ``_build_slug`` is a deterministic function of ``(base_pipeline, checksum)``,
    so identical analysis artifacts produce identical slugs (SYNTH-06).
  - ``match_base_pipeline`` is 100% rule-based (no LLM). LLM is exclusively used
    inside ``lib/llm_fill.py`` (Plan 05-03) for stage-detail fill — never for
    base selection.
  - No function combines synthesize + accept. That separation is a hard rule
    (SYNTH-10). Plan 05-03 adds ``accept_synthesis`` / ``reject_synthesis`` as
    distinct public functions; no wrapper exists, ever.

Schema field mapping note (research Finding #4):
  The pipeline-side annotation flag ``close_up_heavy`` maps to the canonical
  ``editing_pacing.shot_type_distribution.talking_head > 0.5`` inside the
  matcher. The canonical ``video_analysis`` schema has no ``close_up`` key.

This plan's ``synthesize_pipeline`` does NOT:
  - ``jsonschema.validate`` its return dict against ``pipeline_synthesis.schema.json``
    (Plan 05-02 adds that).
  - Call any LLM client (Plan 05-03).
  - Compute ``diff_against_base`` (Plan 05-02; left as ``""``).
  - Execute semantic validation of skill paths or tool names (Plan 05-02).
"""

from __future__ import annotations

import difflib
import hashlib
import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Literal

import jsonschema
from ruamel.yaml import YAML

from lib.pipeline_loader import PIPELINE_DEFS_DIR, list_pipelines, load_pipeline


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

STAGING_DIR = PIPELINE_DEFS_DIR / "_staging"

#: Root of the ``skills/`` tree — used by ``validate_synthesized_pipeline`` to
#: resolve ``stage["skill"]`` paths. Convention: ``stage["skill"]`` is a path
#: relative to ``skills/`` without the ``.md`` extension.
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

#: Path to the pipeline_synthesis run-record schema (SYNTH-09 shipped Phase 1).
_SYNTHESIS_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "artifacts"
    / "pipeline_synthesis.schema.json"
)

#: Adjacency is defined by neighbor index in this chain. Two styles are
#: "adjacent" iff |idx(a) - idx(b)| == 1.
PACING_CHAIN: list[str] = [
    "slow_contemplative",
    "steady_educational",
    "dynamic_social",
    "rapid_fire",
    "variable",
]

Mode = Literal["template", "replica"]

#: Cap the -vN collision-suffix loop so adversarial filesystems cannot cause
#: unbounded work (T-05-04 DoS mitigation).
_MAX_COLLISION_SUFFIX = 99


# ---------------------------------------------------------------------------
# Semantic validation (SYNTH-08) — Plan 05-02
# ---------------------------------------------------------------------------


class SynthesisValidationError(Exception):
    """Raised when a synthesized pipeline fails semantic validation.

    Attributes:
        issues: ``list[str]`` of human-readable issue descriptions. Consumers
            that need per-issue structure should inspect ``.issues`` directly
            rather than re-parse ``str(exc)``.

    This exception is raised only by ``raise_if_invalid`` (the explicit
    escalation helper). ``validate_synthesized_pipeline`` itself NEVER raises
    — it returns the issues list for callers to surface as they see fit.
    """

    def __init__(self, issues: list[str]):
        self.issues = list(issues)
        super().__init__(
            "\n".join(self.issues) if self.issues else "validation failed"
        )


def validate_synthesized_pipeline(manifest: dict[str, Any]) -> list[str]:
    """Semantic validation of a synthesized pipeline manifest.

    Checks performed per stage:

    * If the stage has a ``skill:`` key, verify that ``skills/<skill>.md``
      exists on disk.
    * Every tool listed in ``tools_available`` must appear in
      ``registry.list_all()`` after ``registry.ensure_discovered()``.

    Stages without a ``skill`` key (legacy ``agent:``-only stages) are not
    flagged. Stages with an absent or empty ``tools_available`` list produce
    no issues.

    Returns:
        list[str]: human-readable issue descriptions. An empty list means
        the manifest passed semantic validation.

    This function NEVER raises. Use :func:`raise_if_invalid` for a raising
    convenience wrapper.
    """
    # Local import avoids a startup-time dependency on the tool registry
    # (and the accompanying importlib walk) for callers that only need the
    # matcher / staging writer from this module.
    from tools.tool_registry import registry

    # Idempotent — safe to call in tests that clear the registry between
    # runs (Pitfall 6 mitigation: registry.list_all() returns empty until
    # ensure_discovered has been called once per process).
    registry.ensure_discovered()
    known_tools = set(registry.list_all())

    issues: list[str] = []
    for stage in manifest.get("stages", []) or []:
        stage_name = stage.get("name", "<unnamed>")

        skill = stage.get("skill")
        if skill:
            skill_path = SKILLS_DIR / f"{skill}.md"
            if not skill_path.exists():
                issues.append(
                    f"stage {stage_name!r}: skill file not found: {skill_path}"
                )

        for tool in stage.get("tools_available", []) or []:
            if tool not in known_tools:
                issues.append(
                    f"stage {stage_name!r}: tool {tool!r} not in registry "
                    f"(known {len(known_tools)} tools after ensure_discovered)"
                )

    return issues


def raise_if_invalid(manifest: dict[str, Any]) -> None:
    """Raise :class:`SynthesisValidationError` iff ``manifest`` has issues.

    Thin wrapper around :func:`validate_synthesized_pipeline` for callers
    that want a single call-site to branch on. No-op on a valid manifest.
    """
    issues = validate_synthesized_pipeline(manifest)
    if issues:
        raise SynthesisValidationError(issues)


# ---------------------------------------------------------------------------
# Run-record helpers (SYNTH-09 emission — Plan 05-02)
# ---------------------------------------------------------------------------


def _load_synthesis_schema() -> dict[str, Any]:
    """Return the parsed ``pipeline_synthesis.schema.json`` dict."""
    with open(_SYNTHESIS_SCHEMA_PATH) as f:
        return json.load(f)


def _unified_diff(
    base_manifest: dict[str, Any],
    synthesized: dict[str, Any],
    *,
    base_name: str,
) -> str:
    """Return a unified-diff between ``base_manifest`` and ``synthesized``.

    Both manifests are dumped through the same ruamel.yaml configuration
    used by the staging writer so the diff reflects actual YAML output —
    not Python dict repr. When both manifests dump to byte-identical YAML,
    the returned string is empty (``""``).
    """
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 120
    yaml.default_flow_style = False

    buf_a, buf_b = StringIO(), StringIO()
    yaml.dump(base_manifest, buf_a)
    yaml.dump(synthesized, buf_b)

    a_text = buf_a.getvalue()
    b_text = buf_b.getvalue()
    if a_text == b_text:
        return ""

    diff_lines = difflib.unified_diff(
        a_text.splitlines(keepends=True),
        b_text.splitlines(keepends=True),
        fromfile=f"base/{base_name}.yaml",
        tofile=f"synthesized/{base_name}.yaml",
        n=3,
    )
    return "".join(diff_lines)


# ---------------------------------------------------------------------------
# Canonical checksum + slug helpers (SYNTH-06)
# ---------------------------------------------------------------------------


def _canonical_sha256(artifact: dict[str, Any]) -> str:
    """Return SHA-256 hex digest over canonical JSON of ``artifact``.

    Canonical form: ``sort_keys=True, separators=(',', ':'), ensure_ascii=False``
    — identical to the project's existing checksum convention.
    """
    canonical = json.dumps(
        artifact,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_slug(base_pipeline: str, checksum: str) -> str:
    """Return slug ``<base_pipeline>-<checksum[:8]>`` (deterministic)."""
    return f"{base_pipeline}-{checksum[:8]}"


# ---------------------------------------------------------------------------
# Matcher (SYNTH-02)
# ---------------------------------------------------------------------------


def _is_adjacent_pacing(a: str | None, b: str | None) -> bool:
    """True iff both styles are in ``PACING_CHAIN`` and sit at neighbor indices."""
    if a is None or b is None:
        return False
    if a not in PACING_CHAIN or b not in PACING_CHAIN:
        return False
    return abs(PACING_CHAIN.index(a) - PACING_CHAIN.index(b)) == 1


def match_base_pipeline(analysis: dict[str, Any]) -> dict[str, Any]:
    """Rule-based base-pipeline matcher.

    Signal weights (bounded ``[0, 1]``):
      * pacing_style exact        = +0.40
      * pacing_style adjacent     = +0.15
      * close_up_heavy signal     = +0.25 (talking_head > 0.5)
      * static_heavy signal       = +0.20 (static_image > 0.5)
      * expected_stage_count match = +0.15

    Ties broken alphabetically by pipeline name (deterministic).

    Returns::

        {
          "base_pipeline": str,
          "match_score": float,
          "alternatives": [{"name": str, "score": float}, ...]
        }
    """
    try:
        ep = analysis["editing_pacing"]
        pacing = ep["pacing_style"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "analysis missing required editing_pacing.pacing_style"
        ) from exc

    shot_dist = ep.get("shot_type_distribution", {}) or {}
    motion_dist = ep.get("motion_type_distribution", {}) or {}
    section_count = len(
        (analysis.get("narrative") or {}).get("section_structure", []) or []
    )

    talking_head_dominant = float(shot_dist.get("talking_head", 0) or 0) > 0.5
    static_image_dominant = float(motion_dist.get("static_image", 0) or 0) > 0.5

    scores: list[tuple[str, float]] = []
    for name in list_pipelines():
        try:
            manifest = load_pipeline(name)
        except Exception:
            # A malformed pipeline file should not crash the matcher.
            scores.append((name, 0.0))
            continue

        expected = manifest.get("expected_analysis") or {}
        score = 0.0

        expected_pacing = expected.get("pacing_style")
        if expected_pacing == pacing:
            score += 0.40
        elif _is_adjacent_pacing(expected_pacing, pacing):
            score += 0.15

        if expected.get("close_up_heavy") and talking_head_dominant:
            score += 0.25

        if expected.get("static_heavy") and static_image_dominant:
            score += 0.20

        expected_stage_count = expected.get("expected_stage_count")
        if (
            isinstance(expected_stage_count, int)
            and expected_stage_count == section_count
        ):
            score += 0.15

        scores.append((name, min(score, 1.0)))

    # Sort by (-score, name) — deterministic tie break by alphabetical name.
    scores.sort(key=lambda x: (-x[1], x[0]))

    if not scores:
        # No pipelines found — caller should never hit this in a healthy repo.
        return {"base_pipeline": "", "match_score": 0.0, "alternatives": []}

    top_name, top_score = scores[0]
    return {
        "base_pipeline": top_name,
        "match_score": top_score,
        "alternatives": [{"name": n, "score": s} for n, s in scores[1:]],
    }


# ---------------------------------------------------------------------------
# Staging writer (SYNTH-05)
# ---------------------------------------------------------------------------


def _build_header(
    *,
    checksum: str,
    base: str,
    match_score: float,
    mode: str,
    timestamp: str | None = None,
) -> str:
    """Return the 5-line provenance header comment block."""
    ts = timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (
        f"# synthesized from video_analysis checksum: {checksum}\n"
        f"# base_pipeline: {base}\n"
        f"# match_score: {match_score:.2f}\n"
        f"# mode: {mode}\n"
        f"# at: {ts}\n"
    )


def _dump_manifest_body(manifest: dict[str, Any]) -> str:
    """Dump ``manifest`` via ruamel YAML round-trip; return string body."""
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 120
    yaml.default_flow_style = False

    buf = StringIO()
    yaml.dump(manifest, buf)
    return buf.getvalue()


def _body_without_timestamp(text: str) -> str:
    """Strip the ``# at: ...`` line so byte-equality compares can ignore timestamps."""
    return "\n".join(
        line for line in text.splitlines() if not line.startswith("# at:")
    )


def _write_staging(
    manifest: dict[str, Any],
    slug: str,
    *,
    checksum: str,
    mode: str,
    match_score: float,
    base: str,
) -> Path:
    """Write ``manifest`` to ``_staging/<slug>.yaml`` with a provenance header.

    Collision handling (SYNTH-06 + Pitfall 5):
      * If the target path exists and its body (timestamp line excluded) is
        byte-equal to what we'd write → no-op; return existing path.
      * Otherwise iterate ``-v2``, ``-v3``, ... up to ``_MAX_COLLISION_SUFFIX``
        before raising ``RuntimeError`` (T-05-04 mitigation).
    """
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    body = _dump_manifest_body(manifest)
    new_header = _build_header(
        checksum=checksum, base=base, match_score=match_score, mode=mode
    )
    new_content = new_header + body

    target = STAGING_DIR / f"{slug}.yaml"

    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if _body_without_timestamp(existing) == _body_without_timestamp(new_content):
            # Byte-equal re-run (ignoring timestamp drift) — reuse existing path.
            return target

        # Find an unused -vN suffix.
        for n in range(2, _MAX_COLLISION_SUFFIX + 1):
            candidate = STAGING_DIR / f"{slug}-v{n}.yaml"
            if not candidate.exists():
                target = candidate
                break
            existing = candidate.read_text(encoding="utf-8")
            if _body_without_timestamp(existing) == _body_without_timestamp(new_content):
                return candidate
        else:
            raise RuntimeError(
                f"Collision cap reached for slug {slug!r} at "
                f"-v{_MAX_COLLISION_SUFFIX}. Clean up _staging/ manually."
            )

    target.write_text(new_content, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Public entry point (SYNTH-01 + SYNTH-04)
# ---------------------------------------------------------------------------


def synthesize_pipeline(
    analysis: dict[str, Any],
    *,
    mode: Mode = "template",
    provider_used: str = "gemini",
    use_llm_fill: bool | None = None,  # accepted; wired in Plan 05-03
) -> dict[str, Any]:
    """Synthesize a pipeline manifest into ``_staging/`` and return a run record.

    **Scope of this plan (05-01):** returns a run-record-shaped dict WITHOUT
    ``jsonschema.validate`` against ``pipeline_synthesis.schema.json``. Plan
    05-02 adds validation + semantic checks + diff computation. Plan 05-03 adds
    LLM fill and the accept/reject API.

    Raises ``ValueError`` if ``mode`` is not ``"template"`` or ``"replica"``.
    """
    if mode not in ("template", "replica"):
        raise ValueError("mode must be 'template' or 'replica'")

    checksum = _canonical_sha256(analysis)
    match = match_base_pipeline(analysis)

    if not match["base_pipeline"]:
        raise RuntimeError(
            "No base pipelines available in pipeline_defs/ — cannot synthesize."
        )

    base_manifest = load_pipeline(match["base_pipeline"])
    # For Plan 05-01 template/replica are identical — both emit the base
    # manifest verbatim. Plan 05-03 diverges them via LLM fill.
    synthesized = base_manifest

    slug = _build_slug(match["base_pipeline"], checksum)
    staging_path = _write_staging(
        synthesized,
        slug,
        checksum=checksum,
        mode=mode,
        match_score=match["match_score"],
        base=match["base_pipeline"],
    )

    # staging_path relative to the repo root (one level above pipeline_defs/).
    repo_root = PIPELINE_DEFS_DIR.parent
    try:
        rel_staging = str(staging_path.relative_to(repo_root))
    except ValueError:
        rel_staging = str(staging_path)

    return {
        "version": "1.0",
        "base_pipeline": match["base_pipeline"],
        "match_score": match["match_score"],
        "mode": mode,
        "staging_path": rel_staging,
        "diff_against_base": "",  # Plan 05-02 fills this
        "validation_status": "pending",  # Plan 05-02 finalizes
        "source_analysis_checksum": checksum,
        "provider_used": provider_used,
    }
