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
import os
import re
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Literal

import jsonschema
from ruamel.yaml import YAML

from lib.analysis_errors import InvalidPipelineSlug
from lib.pipeline_loader import PIPELINE_DEFS_DIR, list_pipelines, load_pipeline
from schemas.artifacts import validate_artifact


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

#: Validation pattern for slugs passed to accept_synthesis / reject_synthesis.
#: Enforces lowercase hex+hyphen+underscore (matches ``_build_slug`` output —
#: ``<base_pipeline>-<checksum[:8]>``); rejects path-traversal payloads
#: (``..``, ``/``, ``\``, ``.``) and absolute paths by construction because
#: those characters are not in the allowed class. Length bound ``{7,127}``
#: covers every realistic slug from a 3-char base + 8-hex suffix up to the
#: 128-char soft cap (NAME_MAX headroom on common filesystems). See Phase 10
#: CLEAN-08 / v2.0 Phase 5 REVIEW MR-01.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{7,127}$")


def _validate_slug(slug: str) -> None:
    """Raise :class:`InvalidPipelineSlug` if ``slug`` is unsafe to join under ``STAGING_DIR``.

    Two gates, applied in order — the regex is fast and rejects the obvious
    payloads; the resolved-path check is defense-in-depth for any hypothetical
    regex bypass (e.g., a symlink under the staging root escaping elsewhere):

      1. Regex ``^[a-z0-9][a-z0-9\\-_]{7,127}$`` — matches the output of
         :func:`_build_slug` (``<base>-<hex[:8]>``) and rejects every
         path-traversal / absolute-path payload by construction (``.``,
         ``/``, ``\\`` are not in the allowed character class).
      2. Resolved-path check — confirm
         ``(STAGING_DIR / f"{slug}.yaml").resolve().parent`` equals
         ``STAGING_DIR.resolve()``; any symlink escape surfaces here.

    Both gates short-circuit before any filesystem mutation (``shutil.move``
    / ``src.unlink()``) in the caller.

    Raises:
        InvalidPipelineSlug: on any failure (never ``ValueError`` — the
            sentinel subclasses ``VideoAnalysisError`` so umbrella handlers
            catch it uniformly alongside ``VideoAnalysisAuthError`` and
            ``MergeConsensusError``).
    """
    if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
        raise InvalidPipelineSlug(
            f"Invalid slug {slug!r} — must match {_SLUG_RE.pattern!r}"
        )
    # Defense-in-depth: resolved path must stay under STAGING_DIR.
    candidate = (STAGING_DIR / f"{slug}.yaml").resolve()
    staging_resolved = STAGING_DIR.resolve()
    if staging_resolved != candidate.parent:
        raise InvalidPipelineSlug(
            f"Slug {slug!r} resolves outside staging root {staging_resolved!s}"
        )


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

    P5-LR-01: wraps ``json.dumps`` in a try/except so a non-JSON type
    (``datetime``, ``Path``, ``bytes``, ``set`` …) smuggled into the
    artifact produces a helpful ``ValueError`` pointing at the root
    cause rather than a bare ``TypeError`` from the encoder. See
    05-REVIEW.md#LR-01.
    """
    try:
        canonical = json.dumps(
            artifact,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except TypeError as exc:
        raise ValueError(
            "analysis is not JSON-serializable; pass the deserialized dict "
            "from a video_analysis artifact"
        ) from exc
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

    **Plan 05-02 additions:**
      * Runs semantic validation (``validate_synthesized_pipeline``) → sets
        ``validation_status`` to ``"valid"`` or ``"invalid"`` (never
        ``"pending"`` — that enum value is reserved for future async flows;
        see Pitfall 2).
      * Computes ``diff_against_base`` as unified-diff text of base YAML vs
        synthesized YAML. Empty string when synthesized equals base byte-for-byte.
      * ``jsonschema.validate``-s the emitted record against
        ``schemas/artifacts/pipeline_synthesis.schema.json`` BEFORE return.

    An invalid synthesis (broken skill path / unknown tool in the base
    manifest) is NOT raised — the record is still returned with
    ``validation_status == "invalid"`` so the caller (Plan 05-03 meta skill)
    can surface the issues to the user. Use :func:`raise_if_invalid` for
    the raising escalation.

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

    # Plan 05-03: optional LLM fill-in. Resolution precedence:
    #   use_llm_fill=True  → always run (even with env=false)
    #   use_llm_fill=False → never run
    #   use_llm_fill=None  → env-controlled (VIDEO_SYNTH_LLM_FILL != "false")
    # The fill helper is advisory — any failure returns the base manifest
    # unchanged, preserving synthesizer determinism.
    if use_llm_fill is None:
        use_llm_fill = (
            os.environ.get("VIDEO_SYNTH_LLM_FILL", "true").lower() != "false"
        )
    if use_llm_fill:
        # Local import keeps the llm_fill module optional at load time —
        # tests that never exercise LLM fill never import openai.
        from lib import llm_fill

        synthesized = llm_fill.fill_stage_details(
            base_manifest, analysis, mode=mode
        )
    else:
        synthesized = deepcopy(base_manifest)

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

    # --- Plan 05-02: semantic validation + diff + record schema check ---
    issues = validate_synthesized_pipeline(synthesized)
    status = "valid" if not issues else "invalid"
    diff = _unified_diff(
        base_manifest, synthesized, base_name=match["base_pipeline"]
    )

    record = {
        "version": "1.0",
        "base_pipeline": match["base_pipeline"],
        "match_score": match["match_score"],
        "mode": mode,
        "staging_path": rel_staging,
        "diff_against_base": diff,
        "validation_status": status,
        "source_analysis_checksum": checksum,
        "provider_used": provider_used,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    # Validate-before-return: ensures any drift in the record shape surfaces
    # at the producer — downstream consumers never see a malformed record
    # (T-05-11 integrity mitigation).
    jsonschema.validate(instance=record, schema=_load_synthesis_schema())
    return record


# ---------------------------------------------------------------------------
# Accept / Reject API (SYNTH-10) — Plan 05-03
# ---------------------------------------------------------------------------


def _relative_staging_path(path: Path) -> str:
    """Return the staging path relative to the repo root.

    Falls back to ``str(path)`` if ``path`` is not under the repo root (e.g.,
    tests that use tmp_path — the whole tmp tree lives outside the repo).
    """
    repo_root = PIPELINE_DEFS_DIR.parent
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def accept_synthesis(slug: str) -> tuple[Path, dict[str, Any]]:
    """Promote a staged pipeline YAML into ``pipeline_defs/``.

    SYNTH-10 contract — this is the ONLY authorized write into
    ``pipeline_defs/``. Moves ``pipeline_defs/_staging/<slug>.yaml`` to
    ``pipeline_defs/<slug>.yaml`` and emits a schema-validated
    ``pipeline_acceptance`` record.

    Post-promotion the promoted YAML is re-validated (``skill:`` paths
    exist, every ``tools_available`` entry is registered). The record's
    ``validation_status`` reflects that check — ``"valid"`` on clean,
    ``"invalid"`` on any residual issue (the move still happens; the
    caller decides whether to revert based on the record).

    Schema note (CLEAN-09 / v2.0 Phase 5 REVIEW MR-02): this record
    validates against ``pipeline_acceptance.schema.json``, NOT
    ``pipeline_synthesis.schema.json``. The legacy pipeline_synthesis
    schema still governs the pre-approval synthesis event emitted by
    :func:`synthesize_pipeline`; post-accept events are their own
    schema, carrying only fields the promotion event actually has
    (``promoted_slug``, ``promoted_path``, ``validation_status``,
    ``created_at``). Audit consumers needing the matcher's
    ``match_score`` / ``base_pipeline`` / ``source_analysis_checksum``
    must correlate by ``promoted_slug`` with the earlier
    pipeline_synthesis record for the same synthesis run.

    Args:
        slug: Filename stem under ``_staging/`` (no ``.yaml`` extension).

    Returns:
        ``(promoted_path, record)`` — ``promoted_path`` is the new path
        under ``pipeline_defs/``; ``record`` validates against
        ``schemas/artifacts/pipeline_acceptance.schema.json``. The
        tuple-return shape is preserved from the v2.0 contract (STATE.md
        decision 05-03); only the record's schema conformance changes.

    Raises:
        InvalidPipelineSlug: ``slug`` fails the defensive regex or resolves
            outside ``STAGING_DIR`` (CLEAN-08 / v2.0 Phase 5 REVIEW MR-01).
            Short-circuits before any filesystem call.
        FileNotFoundError: staging file missing.
        FileExistsError: a file already exists at the promoted path (the
            call would overwrite an existing pipeline).
    """
    _validate_slug(slug)
    src = STAGING_DIR / f"{slug}.yaml"
    dst = PIPELINE_DEFS_DIR / f"{slug}.yaml"

    if not src.exists():
        raise FileNotFoundError(f"Staging file not found: {src}")
    if dst.exists():
        # No partial state — staging file stays in place so the caller can
        # retry with a different slug after inspecting the conflict.
        raise FileExistsError(
            f"Target already exists (will not overwrite): {dst}"
        )

    # Sibling directories under the same mount — os.rename works and
    # shutil.move falls back to copy+unlink only on EXDEV (Pitfall 7).
    shutil.move(str(src), str(dst))

    # Re-validate the promoted manifest; record describes the code-verified
    # state, NOT user sentiment. Rejection is no longer encoded as
    # ``validation_status="invalid"`` — it has its own schema now
    # (pipeline_rejection); see :func:`reject_synthesis`.
    issues: list[str] = []
    try:
        promoted_manifest = load_pipeline(slug)
        issues = validate_synthesized_pipeline(promoted_manifest)
    except Exception:
        # A malformed promoted YAML should not crash the accept path —
        # record as "invalid" so the caller can surface it.
        issues = ["promoted manifest could not be loaded for validation"]

    status = "valid" if not issues else "invalid"

    record: dict[str, Any] = {
        "version": "1.0",
        "promoted_slug": slug,
        "promoted_path": _relative_staging_path(dst),
        "validation_status": status,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if issues:
        record["validation_issues"] = issues
    validate_artifact("pipeline_acceptance", record)
    return dst, record


def reject_synthesis(slug: str) -> dict[str, Any]:
    """Delete a staged pipeline YAML and emit a rejection record.

    Schema note (CLEAN-09 / v2.0 Phase 5 REVIEW MR-02): this record
    validates against ``pipeline_rejection.schema.json``. The v2.0
    pattern of re-emitting a ``pipeline_synthesis`` record with
    ``validation_status="invalid"`` (Pitfall 2 hack — rejection is not a
    validation failure) has been replaced with a dedicated schema that
    carries only fields a rejection event actually has
    (``rejected_slug``, ``staging_path``, ``created_at``; optional
    ``reason``). The meta-skill layer (Phase 6) may forward a
    user-provided reason into the ``reason`` field in a future phase.

    Args:
        slug: Filename stem under ``_staging/``.

    Returns:
        Schema-validated ``pipeline_rejection`` record.

    Raises:
        InvalidPipelineSlug: ``slug`` fails the defensive regex or resolves
            outside ``STAGING_DIR`` (CLEAN-08 / v2.0 Phase 5 REVIEW MR-01).
            Short-circuits before any filesystem call.
        FileNotFoundError: staging file missing.
    """
    _validate_slug(slug)
    src = STAGING_DIR / f"{slug}.yaml"
    if not src.exists():
        raise FileNotFoundError(f"Staging file not found: {src}")

    rel_path = _relative_staging_path(src)
    src.unlink()

    record: dict[str, Any] = {
        "version": "1.0",
        "rejected_slug": slug,
        "staging_path": rel_path,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    validate_artifact("pipeline_rejection", record)
    return record


