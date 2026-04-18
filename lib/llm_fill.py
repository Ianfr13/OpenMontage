"""Bounded OpenRouter text-only LLM fill-in helper (Phase 5, Plan 05-03).

Public surface:

    fill_stage_details(base_manifest, analysis, *, mode="template") -> dict

Fills three advisory fields (:data:`FILLABLE_FIELDS`) on stages that already
exist in ``base_manifest``. The LLM can NEVER invent stages — extra entries
returned by the model are silently dropped during merge.

The helper's defining contract is its fallback ladder (per 05-03-PLAN.md):

  1. ``VIDEO_SYNTH_LLM_FILL=false``       → return deepcopy of base manifest
  2. ``OPENROUTER_API_KEY`` not set       → return deepcopy of base manifest
  3. ``client.chat.completions.create`` raises → return deepcopy of base manifest
  4. ``json.loads(resp)`` raises          → ONE retry with the same prompt,
                                            then fall back
  5. Merged manifest fails semantic validation → return deepcopy of base manifest
  6. Happy path                           → merged manifest

``fill_stage_details`` MUST NEVER raise — any unexpected exception is caught
and the base manifest is returned unchanged. This is the SYNTH-03 "advisory"
contract: synthesizer determinism takes priority over LLM enrichment.

Threat-model anchors:

  * T-05-14 (spoofing via crafted LLM output) — post-merge semantic validation
    catches bogus tool/skill injection; helper reverts to base on any issue.
  * T-05-15 (tampering via injected stages) — ``_merge_stage_details`` only
    overwrites fields on stages already present in the base; extras dropped.
  * T-05-17 (API-key leak via logs) — exception logging records only the
    exception class name + ``str(exc)``; the openai SDK redacts the key in its
    own error messages (Phase 3 pattern).
  * T-05-18 (response-size DoS) — ``max_tokens=MAX_TOKENS`` (2000); retry cap
    of 2; no amplification path.

Notes on OpenRouter passthrough:
  Some routed models silently ignore ``response_format={"type": "json_schema"}``
  (Pitfall 4 carried from Phase 3 research). Use ``{"type": "json_object"}``
  for broader support and put the schema-shape hint in the prompt itself.
"""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

# --- Tunables -------------------------------------------------------------

#: Default OpenRouter model — cheap, fast, >1M ctx, adequate for stage-detail fill.
MODEL_DEFAULT = "google/gemini-2.5-flash"

#: Hard cap on response tokens (DoS guard; T-05-18).
MAX_TOKENS = 2000

#: Maximum attempts per ``fill_stage_details`` call (first + one retry).
_MAX_ATTEMPTS = 2

#: Fields the LLM is permitted to overwrite on existing stages. Structural
#: keys (name, skill, agent, produces, required_artifacts_in, ...) are NEVER
#: touched — merging them would cross the SYNTH-03 boundary.
FILLABLE_FIELDS: tuple[str, ...] = (
    "tools_available",
    "review_focus",
    "success_criteria",
)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _stage_summary(stages: list[dict[str, Any]]) -> str:
    """Return a compact per-stage summary used as prompt context."""
    lines: list[str] = []
    for stage in stages:
        name = stage.get("name", "<unnamed>")
        tools = stage.get("tools_available", []) or []
        lines.append(f"- {name}: existing tools_available={tools}")
    return "\n".join(lines)


def _analysis_hints(analysis: dict[str, Any]) -> str:
    """Distill pacing + narrative signals into a short hint block."""
    ep = (analysis or {}).get("editing_pacing") or {}
    narrative = (analysis or {}).get("narrative") or {}
    pacing = ep.get("pacing_style", "unknown")
    section_count = len((narrative.get("section_structure") or []))
    tone = narrative.get("content_tone", "unknown")
    return (
        f"pacing_style={pacing}, section_count={section_count}, tone={tone}"
    )


def _build_prompt(
    base_manifest: dict[str, Any],
    analysis: dict[str, Any],
    *,
    mode: str,
) -> str:
    """Build the text-only prompt submitted to the LLM.

    Branches on ``mode``:
      * ``template`` → emphasizes generalizable, reusable values.
      * ``replica``  → emphasizes closer reproduction of the reference.

    The prompt DOES NOT allow the LLM to invent new stages. The merge step
    enforces this separately, but instructing the model up front reduces
    wasted tokens and fallback frequency.
    """
    stages = base_manifest.get("stages", []) or []
    summary = _stage_summary(stages)
    hints = _analysis_hints(analysis)
    base_name = base_manifest.get("name", "<unknown>")

    mode_line = (
        "Keep values generalizable — this is a reusable template."
        if mode == "template"
        else "Aim for closer reproduction of the reference video's specific style."
    )

    # Inline schema example (OpenRouter: prefer response_format=json_object
    # + schema in prompt, see Pitfall 4).
    shape_example = (
        '{"stages": [\n'
        '  {"name": "<stage-name>",\n'
        '   "tools_available": ["..."],\n'
        '   "review_focus": ["..."],\n'
        '   "success_criteria": ["..."]}\n'
        "]}"
    )

    return (
        f"You are filling stage-level advisory details for pipeline "
        f"'{base_name}'.\n\n"
        f"Analysis hints: {hints}\n\n"
        f"Existing stages (do NOT invent new ones; fill only for these "
        f"names):\n{summary}\n\n"
        f"Return a JSON object with ONLY this shape:\n{shape_example}\n\n"
        "Rules:\n"
        "  - Only output stages already listed above.\n"
        "  - tools_available entries must be plausible tool names "
        "(e.g., web_search, transcript_fetcher, video_compose).\n"
        "  - review_focus / success_criteria are short declarative "
        "sentences.\n"
        f"  - {mode_line}\n"
        "Return JSON only. No prose, no markdown fences."
    )


# ---------------------------------------------------------------------------
# Retry-bounded LLM call
# ---------------------------------------------------------------------------


def _call_with_retry(
    client: "OpenAI",
    model: str,
    prompt: str,
) -> dict[str, Any] | None:
    """Invoke the LLM up to ``_MAX_ATTEMPTS`` times; return parsed JSON or None.

    Returns ``None`` on:
      * any openai SDK exception on the last attempt,
      * any JSON parse failure on the last attempt.
    """
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=MAX_TOKENS,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            text = (resp.choices[0].message.content or "").strip()
            return json.loads(text)
        except Exception as exc:
            # T-05-17: str(exc) from the openai SDK does not leak the key.
            logger.warning(
                "llm_fill: attempt %d failed (%s: %s)",
                attempt,
                type(exc).__name__,
                exc,
            )
            if attempt == _MAX_ATTEMPTS:
                return None
    # P5-LR-04: unreachable — the loop either returns on success or
    # returns None on the final attempt's except branch. Kept explicit
    # for type-checker happiness; see 05-REVIEW.md#LR-04.
    return None  # pragma: no cover — defensive / type-check anchor


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def _merge_stage_details(
    base_manifest: dict[str, Any],
    filled: dict[str, Any],
) -> dict[str, Any]:
    """Produce a new manifest by overwriting FILLABLE_FIELDS on matching stages.

    Enforces SYNTH-03 ("never invents stage structure"):
      * Stages in ``filled["stages"]`` that have no corresponding name in
        ``base_manifest`` are DROPPED.
      * Non-fillable keys (name, skill, produces, ...) are never modified.
      * Empty / missing fillable values in ``filled`` leave the base value
        intact — the LLM cannot erase data by returning ``None`` / ``[]``.
    """
    merged = deepcopy(base_manifest)
    filled_by_name = {
        s.get("name"): s
        for s in (filled.get("stages") or [])
        if isinstance(s, dict) and s.get("name")
    }
    for stage in merged.get("stages", []) or []:
        name = stage.get("name")
        if name not in filled_by_name:
            continue
        filled_stage = filled_by_name[name]
        for field in FILLABLE_FIELDS:
            value = filled_stage.get(field)
            if value:  # truthy — non-empty list / non-empty string
                stage[field] = value
    return merged


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fill_stage_details(
    base_manifest: dict[str, Any],
    analysis: dict[str, Any],
    *,
    mode: str = "template",
) -> dict[str, Any]:
    """LLM-assisted fill of advisory stage fields.

    Args:
        base_manifest: Output of :func:`lib.pipeline_loader.load_pipeline`
            (or any schema-valid pipeline manifest dict).
        analysis: The ``video_analysis`` artifact driving the synthesis.
        mode: ``"template"`` (generalizable) or ``"replica"`` (closer
            reproduction).

    Returns:
        A new manifest dict. ``base_manifest`` is never mutated. On any
        failure the returned dict is a deep copy of ``base_manifest``.

    This function NEVER raises — the advisory contract is absolute.
    """
    if os.environ.get("VIDEO_SYNTH_LLM_FILL", "true").lower() == "false":
        logger.info("llm_fill: disabled by VIDEO_SYNTH_LLM_FILL=false")
        return deepcopy(base_manifest)

    if not os.environ.get("OPENROUTER_API_KEY"):
        logger.info(
            "llm_fill: OPENROUTER_API_KEY missing — returning base manifest"
        )
        return deepcopy(base_manifest)

    model = os.environ.get("VIDEO_SYNTH_LLM_MODEL", MODEL_DEFAULT)
    prompt = _build_prompt(base_manifest, analysis, mode=mode)

    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
    except Exception as exc:
        logger.warning(
            "llm_fill: OpenAI client init failed (%s: %s) — returning base",
            type(exc).__name__,
            exc,
        )
        return deepcopy(base_manifest)

    filled = _call_with_retry(client, model, prompt)
    if filled is None:
        return deepcopy(base_manifest)

    try:
        merged = _merge_stage_details(base_manifest, filled)
    except Exception as exc:  # defensive — merge should not raise on well-typed input
        logger.warning(
            "llm_fill: merge raised unexpectedly (%s: %s) — returning base",
            type(exc).__name__,
            exc,
        )
        return deepcopy(base_manifest)

    # Post-merge semantic validation. Local import avoids a module-load
    # cycle (pipeline_synthesizer already imports llm_fill via the wiring
    # from synthesize_pipeline).
    try:
        from lib.pipeline_synthesizer import validate_synthesized_pipeline

        issues = validate_synthesized_pipeline(merged)
    except Exception as exc:
        logger.warning(
            "llm_fill: post-merge validation raised (%s: %s) — returning base",
            type(exc).__name__,
            exc,
        )
        return deepcopy(base_manifest)

    if issues:
        logger.warning(
            "llm_fill: post-merge validation failed (%d issue(s)) — reverting",
            len(issues),
        )
        return deepcopy(base_manifest)

    return merged
