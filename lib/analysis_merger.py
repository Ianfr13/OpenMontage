"""Per-dimension video_analysis merger for chunked long-form analysis.

Pure lib module — NOT a BaseTool. Exposes one public function:

* ``merge_analyses(chunks, provider) -> dict``

Implements Phase 4 requirements:

* **CHUNK-04** — per-dimension merge rules producing a single canonical
  ``video_analysis`` artifact from a list of ``(Chunk, per_chunk_artifact)``
  pairs.
* **CHUNK-05** — attaches ``chunking_metadata`` with per-chunk cost /
  provider / timestamp traceability.

Every rule is derived directly from
``schemas/artifacts/video_analysis.schema.json`` and enumerated in
``.planning/phases/04-chunking/04-RESEARCH.md § Merger Rules`` — this
module IS that table.

Design invariants
-----------------

* **Single validation gate.** ``validate_artifact("video_analysis", merged)``
  is called *exactly once* at the end of ``merge_analyses`` (RESEARCH
  Pitfall 2). Provider tools already validate their per-chunk outputs;
  re-validating here would double work without catching merger bugs
  (which only show up after transformation).
* **Time-value fields shifted exhaustively.** Only three fields carry
  chunk-local timestamps in the schema (RESEARCH § Time-valued fields):
  ``editing_pacing.energy_arc[].timestamp_s``,
  ``narrative.section_structure[].approx_start_s``,
  ``narrative.section_structure[].approx_end_s``. All three are shifted
  by ``chunk.start_global`` on concat. ``hook_duration_seconds`` /
  ``cta_duration_seconds`` / ``shortest_shot_seconds`` etc. are durations
  or statistics — NOT shifted.
* **Worst-case confidence.** Any chunk "low" on a per-field confidence
  map → merged "low" (RESEARCH Pitfall 6). NEVER averaged, NEVER
  majority-voted — "low" is an honest signal from the model that it
  wasn't sure, and diluting it lies to downstream.
* **Array caps.** Color-like arrays (``color_palette.*``,
  ``dominant_colors_hex``) are capped at N=5 by observation frequency to
  prevent unbounded growth on long videos (RESEARCH Pitfall 3).
* **Position-based fields.** ``hook_*`` always comes from chunks[0]
  (video-start position per CHUNK-04), ``cta_*`` from chunks[-1]
  (video-end position).
* **No side effects.** Merger does NOT call ``cost_tracker`` itself —
  the chunked_analyzer (Plan 03) stamps ``_cost_usd`` on each per-chunk
  artifact before handing them here. Merger also does NOT call
  ``write_checkpoint``; that's the orchestrator's job.
"""

from __future__ import annotations

import copy
import logging
from collections import Counter
from typing import Any

from lib.analysis_errors import MergeConsensusError
from lib.video_chunker import Chunk
from schemas.artifacts import validate_artifact

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Private primitives — pure functions, no side effects.
# ---------------------------------------------------------------------------

_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}
_COLOR_CAP = 5  # RESEARCH Pitfall 3


def _weighted_avg(pairs: list[tuple[float, float]]) -> float:
    """Duration-weighted numeric average.

    Returns 0.0 if ``pairs`` is empty or total weight is zero (no
    division-by-zero panic; callers can substitute None if they prefer
    omit semantics).

    P4-LO-01: ``0.0`` returned on empty-input is indistinguishable from
    a genuine zero-weight average of real data. Callers downstream
    (editing_pacing fields, audio fields, etc.) rely on the fact that
    chunk weights are always positive (``end_global - start_global``),
    so in practice "0.0" means "all zero-weighted" which never occurs
    in a healthy chunk list. If a caller ever passes empty pairs or
    all-None values, "0.0" == "no data" is an acceptable downstream
    signal. See 04-REVIEW.md#LO-01.
    """
    total_w = 0.0
    acc = 0.0
    for v, w in pairs:
        if v is None or w is None:
            continue
        acc += float(v) * float(w)
        total_w += float(w)
    if total_w == 0.0:
        return 0.0
    return acc / total_w


def _weighted_majority(pairs: list[tuple[Any, float]]) -> Any:
    """Duration-weighted majority vote for enum / categorical fields.

    None values contribute no weight. Returns None if every input is
    None or the input list is empty. Ties are resolved by
    ``Counter.most_common`` which preserves insertion order for equal
    counts.
    """
    tally: Counter = Counter()
    for v, w in pairs:
        if v is None:
            continue
        tally[v] += float(w)
    if not tally:
        return None
    return tally.most_common(1)[0][0]


def _union_dedup(arrays: list[list[str]]) -> list[str]:
    """Order-preserving union across arrays (insertion-order via ``dict.fromkeys``)."""
    merged: dict[str, None] = {}
    for arr in arrays:
        if not arr:
            continue
        for item in arr:
            merged[item] = None
    return list(merged.keys())


def _top_n_by_frequency(arrays: list[list[str]], n: int) -> list[str]:
    """Return top-N items by occurrence count across ``arrays``.

    Items seen in many chunks rank higher. Tie-breaker: first-seen order
    (``Counter.most_common`` preserves insertion order for equal counts).
    Empty input → empty list.
    """
    tally: Counter = Counter()
    for arr in arrays:
        if not arr:
            continue
        for item in arr:
            tally[item] += 1
    return [item for item, _ in tally.most_common(n)]


def _worst_confidence(values: list[str]) -> str:
    """Min-of-worst confidence aggregation (RESEARCH Pitfall 6).

    ANY 'low' → 'low'; else ANY 'medium' → 'medium'; else 'high'.
    Empty input defaults to 'high' (no pessimism signal). Unknown
    strings are treated as 'high' (most permissive) so a rogue value
    cannot poison the aggregate.
    """
    if not values:
        return "high"
    worst = 0
    for v in values:
        rank = _CONFIDENCE_RANK.get(v, 0)
        if rank > worst:
            worst = rank
    for label, rank in _CONFIDENCE_RANK.items():
        if rank == worst:
            return label
    return "high"


def _concat_freetext(values: list[str | None], chunk_labels: list[str]) -> str:
    """Concat free-text with ``[chunk N/M]`` markers (RESEARCH Pattern 5).

    None / empty-string values are skipped. Zip is strict-paired with
    labels so the caller controls labelling.
    """
    parts: list[str] = []
    for val, label in zip(values, chunk_labels):
        if val:
            parts.append(f"[{label}] {val}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Dimension merge helpers
# ---------------------------------------------------------------------------


def _renormalize_distribution(d: dict[str, float]) -> dict[str, float]:
    """Re-normalize a dict of non-negative ratios to sum ≈ 1.0.

    If all values are zero (or missing), return the input unchanged.
    """
    total = sum(v for v in d.values() if v is not None)
    if total <= 0.0:
        return d
    return {k: (v / total) for k, v in d.items() if v is not None}


def _collect_field(
    chunks: list[tuple[Chunk, dict]],
    dim: str,
    field: str,
) -> list[Any]:
    """Return ``[artifact[dim].get(field) for _, artifact in chunks]`` verbatim."""
    return [art.get(dim, {}).get(field) for _, art in chunks]


def _pair_with_weights(
    values: list[Any],
    weights: list[float],
    *,
    keep_none: bool = False,
) -> list[tuple[Any, float]]:
    """Zip values with weights; optionally drop None entries."""
    if keep_none:
        return list(zip(values, weights))
    return [(v, w) for v, w in zip(values, weights) if v is not None]


def _merge_confidence_map(confidence_maps: list[dict]) -> dict[str, str]:
    """Per-key worst-case min across chunk confidence dicts.

    Keys seen in only some chunks are included with the worst value
    observed across chunks that DO mention them (missing != low).
    """
    all_keys: set[str] = set()
    for m in confidence_maps:
        if isinstance(m, dict):
            all_keys.update(m.keys())
    merged: dict[str, str] = {}
    for key in all_keys:
        observed: list[str] = []
        for m in confidence_maps:
            if isinstance(m, dict) and key in m:
                observed.append(m[key])
        merged[key] = _worst_confidence(observed)
    return merged


def _chunks_dim(chunks: list[tuple[Chunk, dict]], dim: str) -> list[dict]:
    """Return per-chunk ``artifact[dim]`` dict list, defaulting missing to {}."""
    return [art.get(dim, {}) or {} for _, art in chunks]


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------


def _merge_source(chunks: list[tuple[Chunk, dict]]) -> dict:
    """Source: first-chunk metadata with ``duration_seconds`` = sum-of-chunks."""
    first = copy.deepcopy(chunks[0][1].get("source", {}))
    total = sum(c.end_global - c.start_global for c, _ in chunks)
    first["duration_seconds"] = total
    # Guard: schema requires 'type' and 'duration_seconds'
    if "type" not in first:
        first["type"] = "local_file"
    return first


# ---------------------------------------------------------------------------
# editing_pacing
# ---------------------------------------------------------------------------


def _merge_editing_pacing(
    chunks: list[tuple[Chunk, dict]],
    weights: list[float],
) -> dict:
    dims = _chunks_dim(chunks, "editing_pacing")
    merged: dict[str, Any] = {}

    # Sums
    merged["total_shots"] = int(sum(d.get("total_shots", 0) or 0 for d in dims))

    # Weighted avgs
    merged["cuts_per_minute"] = _weighted_avg(
        _pair_with_weights([d.get("cuts_per_minute") for d in dims], weights)
    )
    merged["avg_shot_duration_seconds"] = _weighted_avg(
        _pair_with_weights(
            [d.get("avg_shot_duration_seconds") for d in dims], weights
        )
    )

    median_pairs = _pair_with_weights(
        [d.get("median_shot_duration_seconds") for d in dims], weights
    )
    if median_pairs:
        merged["median_shot_duration_seconds"] = _weighted_avg(median_pairs)

    shortest_vals = [
        d.get("shortest_shot_seconds") for d in dims if d.get("shortest_shot_seconds") is not None
    ]
    if shortest_vals:
        merged["shortest_shot_seconds"] = float(min(shortest_vals))

    longest_vals = [
        d.get("longest_shot_seconds") for d in dims if d.get("longest_shot_seconds") is not None
    ]
    if longest_vals:
        merged["longest_shot_seconds"] = float(max(longest_vals))

    # Weighted majority (required) — CLEAN-06: no hardcoded default fallback
    pacing = _weighted_majority(
        _pair_with_weights([d.get("pacing_style") for d in dims], weights)
    )
    first_pacing = dims[0].get("pacing_style")
    if pacing is None and first_pacing is None:
        raise MergeConsensusError(
            "editing_pacing.pacing_style: no chunk provided a value "
            "(consensus and first-chunk fallback both None — "
            "single-validation-gate: merger does not fabricate required fields)"
        )
    merged["pacing_style"] = pacing if pacing is not None else first_pacing

    # Distributions: per-key weighted avg + renormalize
    shot_dist_keys: set[str] = set()
    for d in dims:
        if isinstance(d.get("shot_type_distribution"), dict):
            shot_dist_keys.update(d["shot_type_distribution"].keys())
    shot_dist: dict[str, float] = {}
    for k in shot_dist_keys:
        shot_dist[k] = _weighted_avg(
            _pair_with_weights(
                [
                    (d.get("shot_type_distribution") or {}).get(k, 0.0)
                    for d in dims
                ],
                weights,
                keep_none=True,
            )
        )
    merged["shot_type_distribution"] = _renormalize_distribution(shot_dist) if shot_dist else {}

    motion_dist_keys: set[str] = set()
    for d in dims:
        if isinstance(d.get("motion_type_distribution"), dict):
            motion_dist_keys.update(d["motion_type_distribution"].keys())
    motion_dist: dict[str, float] = {}
    for k in motion_dist_keys:
        motion_dist[k] = _weighted_avg(
            _pair_with_weights(
                [
                    (d.get("motion_type_distribution") or {}).get(k, 0.0)
                    for d in dims
                ],
                weights,
                keep_none=True,
            )
        )
    merged["motion_type_distribution"] = motion_dist

    # Optional ratios
    b_roll_pairs = _pair_with_weights([d.get("b_roll_ratio") for d in dims], weights)
    if b_roll_pairs:
        merged["b_roll_ratio"] = _weighted_avg(b_roll_pairs)
    a_roll_pairs = _pair_with_weights([d.get("a_roll_ratio") for d in dims], weights)
    if a_roll_pairs:
        merged["a_roll_ratio"] = _weighted_avg(a_roll_pairs)

    # Array: union-dedup (enum space small)
    transitions = _union_dedup([d.get("transition_types") or [] for d in dims])
    if transitions:
        merged["transition_types"] = transitions
    scenes = _union_dedup([d.get("suggested_remotion_scene_types") or [] for d in dims])
    if scenes:
        merged["suggested_remotion_scene_types"] = scenes

    # energy_arc: concat with timestamp_s += chunk.start_global
    arc: list[dict] = []
    for (chunk, art), _w in zip(chunks, weights):
        per_chunk_arc = (art.get("editing_pacing") or {}).get("energy_arc") or []
        for entry in per_chunk_arc:
            shifted = copy.deepcopy(entry)
            if "timestamp_s" in shifted:
                shifted["timestamp_s"] = float(shifted["timestamp_s"]) + float(
                    chunk.start_global
                )
            arc.append(shifted)
    if arc:
        merged["energy_arc"] = arc

    # Confidence worst-case
    conf_maps = [d.get("confidence") for d in dims]
    merged_conf = _merge_confidence_map([m for m in conf_maps if isinstance(m, dict)])
    if merged_conf:
        merged["confidence"] = merged_conf

    return merged


# ---------------------------------------------------------------------------
# audio
# ---------------------------------------------------------------------------


def _merge_audio(
    chunks: list[tuple[Chunk, dict]],
    weights: list[float],
) -> dict:
    dims = _chunks_dim(chunks, "audio")
    merged: dict[str, Any] = {}

    # Boolean OR
    merged["has_narration"] = any(bool(d.get("has_narration")) for d in dims)
    merged["has_music"] = any(bool(d.get("has_music")) for d in dims)
    merged["has_sfx"] = any(bool(d.get("has_sfx")) for d in dims)

    # narration_style (required) — weighted majority; CLEAN-06 no hardcoded default
    nar_style = _weighted_majority(
        _pair_with_weights([d.get("narration_style") for d in dims], weights)
    )
    first_nar_style = dims[0].get("narration_style")
    if nar_style is None and first_nar_style is None:
        raise MergeConsensusError(
            "audio.narration_style: no chunk provided a value "
            "(consensus and first-chunk fallback both None — "
            "single-validation-gate: merger does not fabricate required fields)"
        )
    merged["narration_style"] = nar_style if nar_style is not None else first_nar_style

    # voice_music_mix (required) — CLEAN-06 no hardcoded default
    vmm = _weighted_majority(
        _pair_with_weights([d.get("voice_music_mix") for d in dims], weights)
    )
    first_vmm = dims[0].get("voice_music_mix")
    if vmm is None and first_vmm is None:
        raise MergeConsensusError(
            "audio.voice_music_mix: no chunk provided a value "
            "(consensus and first-chunk fallback both None — "
            "single-validation-gate: merger does not fabricate required fields)"
        )
    merged["voice_music_mix"] = vmm if vmm is not None else first_vmm

    # speaker_count — max
    sc_vals = [d.get("speaker_count") for d in dims if d.get("speaker_count") is not None]
    if sc_vals:
        merged["speaker_count"] = int(max(sc_vals))

    # voice_gender / voice_tone — weighted majority
    vg = _weighted_majority(
        _pair_with_weights([d.get("voice_gender") for d in dims], weights)
    )
    if vg is not None:
        merged["voice_gender"] = vg
    vt = _weighted_majority(
        _pair_with_weights([d.get("voice_tone") for d in dims], weights)
    )
    if vt is not None:
        merged["voice_tone"] = vt

    # narration_wpm — weighted avg ACROSS CHUNKS where has_narration=True
    narration_pairs: list[tuple[float, float]] = []
    for d, w in zip(dims, weights):
        if d.get("has_narration") and d.get("narration_wpm") is not None:
            narration_pairs.append((d["narration_wpm"], w))
    if narration_pairs:
        merged["narration_wpm"] = _weighted_avg(narration_pairs)

    # narration_language — weighted majority
    lang = _weighted_majority(
        _pair_with_weights([d.get("narration_language") for d in dims], weights)
    )
    if lang is not None:
        merged["narration_language"] = lang

    # music_genre — weighted majority
    mg = _weighted_majority(
        _pair_with_weights([d.get("music_genre") for d in dims], weights)
    )
    if mg is not None:
        merged["music_genre"] = mg

    # music_tempo_bpm — weighted avg of non-null; null if all null
    tempo_pairs: list[tuple[float, float]] = []
    tempo_seen = False
    for d, w in zip(dims, weights):
        if "music_tempo_bpm" in d:
            tempo_seen = True
            if d["music_tempo_bpm"] is not None:
                tempo_pairs.append((d["music_tempo_bpm"], w))
    if tempo_pairs:
        merged["music_tempo_bpm"] = _weighted_avg(tempo_pairs)
    elif tempo_seen:
        merged["music_tempo_bpm"] = None

    # music_intensity — weighted majority
    mi = _weighted_majority(
        _pair_with_weights([d.get("music_intensity") for d in dims], weights)
    )
    if mi is not None:
        merged["music_intensity"] = mi

    # sfx_style — weighted majority
    sfx = _weighted_majority(
        _pair_with_weights([d.get("sfx_style") for d in dims], weights)
    )
    if sfx is not None:
        merged["sfx_style"] = sfx

    # First-chunk creative hints
    tts_profile = dims[0].get("suggested_tts_voice_profile")
    if tts_profile is not None:
        merged["suggested_tts_voice_profile"] = tts_profile
    music_prompt = dims[0].get("suggested_music_prompt")
    if music_prompt is not None:
        merged["suggested_music_prompt"] = music_prompt

    # Confidence
    conf_maps = [d.get("confidence") for d in dims]
    merged_conf = _merge_confidence_map([m for m in conf_maps if isinstance(m, dict)])
    if merged_conf:
        merged["confidence"] = merged_conf

    return merged


# ---------------------------------------------------------------------------
# visual_style
# ---------------------------------------------------------------------------


def _merge_visual_style(
    chunks: list[tuple[Chunk, dict]],
    weights: list[float],
) -> dict:
    dims = _chunks_dim(chunks, "visual_style")
    merged: dict[str, Any] = {}

    # color_palette — cap at 5 by frequency per bucket
    palette: dict[str, list[str]] = {}
    for bucket in ("primary", "accent", "background", "text"):
        bucket_arrays = [
            (d.get("color_palette") or {}).get(bucket) or [] for d in dims
        ]
        if any(bucket_arrays):
            palette[bucket] = _top_n_by_frequency(bucket_arrays, _COLOR_CAP)
    if palette:
        merged["color_palette"] = palette
    else:
        # required field — keep the first chunk's palette verbatim
        merged["color_palette"] = copy.deepcopy(
            dims[0].get("color_palette") or {}
        )

    # dominant_colors_hex — cap at 5 by frequency
    dom_arrays = [d.get("dominant_colors_hex") or [] for d in dims]
    if any(dom_arrays):
        merged["dominant_colors_hex"] = _top_n_by_frequency(dom_arrays, _COLOR_CAP)

    # Weighted-majority enums
    for field in (
        "color_temperature",
        "color_grading_style",
        "background_treatment",
        "typography_weight",
        "text_card_usage",
        "motion_style",
        "overlay_style",
    ):
        vote = _weighted_majority(
            _pair_with_weights([d.get(field) for d in dims], weights)
        )
        if vote is not None:
            merged[field] = vote

    # production_quality (required) — CLEAN-06 no hardcoded default
    pq = _weighted_majority(
        _pair_with_weights([d.get("production_quality") for d in dims], weights)
    )
    first_pq = dims[0].get("production_quality")
    if pq is None and first_pq is None:
        raise MergeConsensusError(
            "visual_style.production_quality: no chunk provided a value "
            "(consensus and first-chunk fallback both None — "
            "single-validation-gate: merger does not fabricate required fields)"
        )
    merged["production_quality"] = pq if pq is not None else first_pq

    # aspect_ratio (required) — first chunk wins; log disagreement
    first_ratio = dims[0].get("aspect_ratio")
    other_ratios = {
        d.get("aspect_ratio") for d in dims[1:] if d.get("aspect_ratio") is not None
    }
    if other_ratios and other_ratios != {first_ratio}:
        logger.warning(
            "aspect_ratio disagreement across chunks — using chunk[0]=%r; also saw %r",
            first_ratio,
            sorted(x for x in other_ratios if x != first_ratio),
        )
    # CLEAN-06 no hardcoded default
    if first_ratio is None:
        raise MergeConsensusError(
            "visual_style.aspect_ratio: chunks[0].aspect_ratio is None "
            "(single-validation-gate: merger does not fabricate required fields)"
        )
    merged["aspect_ratio"] = first_ratio

    # typography_style — first-chunk prose
    ts = dims[0].get("typography_style")
    if ts is not None:
        merged["typography_style"] = ts

    # suggested_playbook — weighted majority
    sp = _weighted_majority(
        _pair_with_weights([d.get("suggested_playbook") for d in dims], weights)
    )
    if sp is not None:
        merged["suggested_playbook"] = sp

    # playbook_overrides — first chunk (dict merge is risky)
    po = dims[0].get("playbook_overrides")
    if po is not None:
        merged["playbook_overrides"] = copy.deepcopy(po)

    # Confidence
    conf_maps = [d.get("confidence") for d in dims]
    merged_conf = _merge_confidence_map([m for m in conf_maps if isinstance(m, dict)])
    if merged_conf:
        merged["confidence"] = merged_conf

    return merged


# ---------------------------------------------------------------------------
# narrative
# ---------------------------------------------------------------------------


def _merge_narrative(
    chunks: list[tuple[Chunk, dict]],
    weights: list[float],
    full_chunks: list[tuple[Chunk, Any]] | None = None,
) -> dict:
    dims = _chunks_dim(chunks, "narrative")
    # CLEAN-07 / MR-03: pick hook/cta by ORIGINAL submission index.
    # When full_chunks is provided, search for the lowest/highest-index
    # entry where art is not None (the position-correct survivor).
    # When None, fall back to survivor-list first/last (v2.0 behavior).
    if full_chunks is not None:
        successful = [art for _c, art in full_chunks if art is not None]
        if successful:
            first = (successful[0].get("narrative") or {})
            last = (successful[-1].get("narrative") or {})
        else:
            # Defensive: should never happen (empty survivors raise upstream),
            # but keep merger robust.
            first = dims[0]
            last = dims[-1]
    else:
        first = dims[0]
        last = dims[-1]
    merged: dict[str, Any] = {}

    # hook_* from first chunk
    merged["hook_type"] = first.get("hook_type", "none")
    if first.get("hook_duration_seconds") is not None:
        merged["hook_duration_seconds"] = float(first["hook_duration_seconds"])

    # narrative_arc — weighted majority vote; CLEAN-06 no hardcoded default
    arc = _weighted_majority(
        _pair_with_weights([d.get("narrative_arc") for d in dims], weights)
    )
    first_arc = first.get("narrative_arc")
    if arc is None and first_arc is None:
        raise MergeConsensusError(
            "narrative.narrative_arc: no chunk provided a value "
            "(consensus and first-chunk fallback both None — "
            "single-validation-gate: merger does not fabricate required fields)"
        )
    merged["narrative_arc"] = arc if arc is not None else first_arc

    # section_count — sum
    merged["section_count"] = int(
        sum(d.get("section_count", 0) or 0 for d in dims)
    )

    # section_structure — concat with approx_start_s / approx_end_s shifted
    sections: list[dict] = []
    for (chunk, art), _w in zip(chunks, weights):
        per = (art.get("narrative") or {}).get("section_structure") or []
        for sect in per:
            shifted = copy.deepcopy(sect)
            if "approx_start_s" in shifted:
                shifted["approx_start_s"] = float(shifted["approx_start_s"]) + float(
                    chunk.start_global
                )
            if "approx_end_s" in shifted:
                shifted["approx_end_s"] = float(shifted["approx_end_s"]) + float(
                    chunk.start_global
                )
            sections.append(shifted)
    if sections:
        merged["section_structure"] = sections

    # cta_* from last chunk
    merged["cta_type"] = last.get("cta_type", "none_detected")
    if last.get("cta_duration_seconds") is not None:
        merged["cta_duration_seconds"] = float(last["cta_duration_seconds"])

    # target_platform (required) — first non-null; CLEAN-06 no hardcoded default
    tp = next(
        (d.get("target_platform") for d in dims if d.get("target_platform") is not None),
        None,
    )
    first_tp = first.get("target_platform")
    if tp is None and first_tp is None:
        raise MergeConsensusError(
            "narrative.target_platform: no chunk provided a value "
            "(consensus and first-chunk fallback both None — "
            "single-validation-gate: merger does not fabricate required fields; "
            "note: the string literal is schema-valid but would be a merger-invented value)"
        )
    merged["target_platform"] = tp if tp is not None else first_tp

    # target_duration_seconds (required) — SUM of chunk durations
    merged["target_duration_seconds"] = float(
        sum(c.end_global - c.start_global for c, _ in chunks)
    )

    # information_density — weighted majority
    info = _weighted_majority(
        _pair_with_weights([d.get("information_density") for d in dims], weights)
    )
    if info is not None:
        merged["information_density"] = info

    # content_tone (required) — weighted majority; CLEAN-06 no hardcoded default
    tone = _weighted_majority(
        _pair_with_weights([d.get("content_tone") for d in dims], weights)
    )
    first_tone = first.get("content_tone")
    if tone is None and first_tone is None:
        raise MergeConsensusError(
            "narrative.content_tone: no chunk provided a value "
            "(consensus and first-chunk fallback both None — "
            "single-validation-gate: merger does not fabricate required fields)"
        )
    merged["content_tone"] = tone if tone is not None else first_tone

    # paragraph_pattern — concat with [chunk N/M] markers
    n = len(chunks)
    labels = [f"chunk {i+1}/{n}" for i in range(n)]
    patterns = [d.get("paragraph_pattern") for d in dims]
    concat = _concat_freetext(patterns, labels)
    if concat:
        merged["paragraph_pattern"] = concat

    # Confidence
    conf_maps = [d.get("confidence") for d in dims]
    merged_conf = _merge_confidence_map([m for m in conf_maps if isinstance(m, dict)])
    if merged_conf:
        merged["confidence"] = merged_conf

    return merged


# ---------------------------------------------------------------------------
# shot_boundary_source — RESEARCH Open Question 2
# ---------------------------------------------------------------------------


def _merge_shot_boundary_source(values: list[Any]) -> str | None:
    """hybrid if any 'hybrid' OR cross-chunk disagreement; else first value.

    All-None → None (don't emit the field).
    """
    non_null = [v for v in values if v is not None]
    if not non_null:
        return None
    if "hybrid" in non_null:
        return "hybrid"
    if len(set(non_null)) > 1:
        return "hybrid"
    return non_null[0]


# ---------------------------------------------------------------------------
# chunking_metadata
# ---------------------------------------------------------------------------


def _build_chunking_metadata(
    chunks: list[tuple[Chunk, dict]],
    provider: str,
) -> dict:
    per_chunk = []
    for i, (c, art) in enumerate(chunks):
        per_chunk.append(
            {
                "index": i,
                "start_s": float(c.start_global),
                "end_s": float(c.end_global),
                "cost_usd": float(art.get("_cost_usd", 0.0) or 0.0),
                "provider": str(art.get("_provider_used", provider)),
            }
        )
    return {
        "chunk_count": len(chunks),
        "total_duration_s": float(
            sum(c.end_global - c.start_global for c, _ in chunks)
        ),
        "provider": provider,
        "per_chunk": per_chunk,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _pass_through_single(
    pair: tuple[Chunk, dict],
    provider: str,
    full_chunks: list[tuple[Chunk, Any]] | None = None,
) -> dict:
    """N=1 path: deep-copy input, strip private ``_*`` keys, attach metadata.

    CLEAN-07: when ``full_chunks`` is provided and the sole survivor was NOT
    at original index 0, log a WARNING — the survivor's local hook_* is not
    the video-wide opening hook, but we still emit it (best-effort).
    """
    chunk, art = pair
    if full_chunks is not None:
        # CLEAN-07 edge: if the sole survivor was NOT at original index 0,
        # its hook_* describes a middle-of-video local hook, not the
        # video-wide hook. Log so callers know the metadata is best-effort.
        sole_chunk = pair[0]
        for i, (c, art_slot) in enumerate(full_chunks):
            if art_slot is not None:
                if c is not sole_chunk and c.start_global != sole_chunk.start_global:
                    continue
                if i != 0:
                    logger.warning(
                        "Single-survivor merge: sole successful chunk was at "
                        "original index %d (not 0) — hook_* reflects that chunk's "
                        "local hook, not the video-wide opening.",
                        i,
                    )
                break
    merged = copy.deepcopy(art)
    # Strip private hints that are NOT part of the canonical schema
    for key in list(merged.keys()):
        if key.startswith("_"):
            merged.pop(key, None)
    merged["chunking_metadata"] = _build_chunking_metadata([pair], provider)
    validate_artifact("video_analysis", merged)
    return merged


def merge_analyses(
    chunks: list[tuple[Chunk, dict]],
    provider: str = "gemini",
    *,
    full_chunks: list[tuple[Chunk, Any]] | None = None,
) -> dict:
    """Merge N per-chunk ``video_analysis`` artifacts into one canonical artifact.

    Parameters
    ----------
    chunks:
        List of ``(Chunk, per_chunk_artifact_dict)`` pairs in submission
        order (i.e. temporal order in the original video). Each
        per-chunk artifact is assumed schema-valid upstream.
    provider:
        The provider name used for the analysis run (recorded in
        ``chunking_metadata.provider``). Individual per-chunk providers
        can be overridden by the ``_provider_used`` key on the per-chunk
        artifact.
    full_chunks:
        Optional list of ``(Chunk, per_chunk_artifact_or_None)`` pairs in
        SUBMISSION ORDER (same length as the total number of original chunks,
        including failures). When supplied, used by ``_merge_narrative`` to
        pick ``hook_*`` from the lowest-index pair where ``art is not None``
        and ``cta_*`` from the highest-index pair where ``art is not None``.

        Used by ``lib.chunked_analyzer.analyze_chunked`` when
        ``on_chunk_error='continue'`` drops edge chunks — without this,
        the merger would pick hook/cta from the survivor list's first/last,
        which silently becomes a middle-of-video chunk when chunk 0 or
        chunk N-1 failed (v2.0 Phase 4 MR-03 / CLEAN-07).

        When ``None`` (default), behavior is unchanged from v2.0.

    Returns
    -------
    dict:
        A canonical ``video_analysis`` artifact with ``chunking_metadata``
        attached, validated against the schema.

    Raises
    ------
    ValueError:
        If ``chunks`` is empty.
    jsonschema.ValidationError:
        If the merged output fails schema validation (indicates a
        merger bug — provider-side validation would have caught
        per-chunk issues upstream).
    """
    if not chunks:
        raise ValueError("merge_analyses requires ≥1 chunk")

    if len(chunks) == 1:
        return _pass_through_single(chunks[0], provider, full_chunks=full_chunks)

    weights = [float(c.end_global - c.start_global) for c, _ in chunks]

    merged: dict[str, Any] = {
        "version": "2.0",
        "source": _merge_source(chunks),
        "editing_pacing": _merge_editing_pacing(chunks, weights),
        "audio": _merge_audio(chunks, weights),
        "visual_style": _merge_visual_style(chunks, weights),
        "narrative": _merge_narrative(chunks, weights, full_chunks=full_chunks),
    }

    sbs = _merge_shot_boundary_source(
        [art.get("shot_boundary_source") for _, art in chunks]
    )
    if sbs is not None:
        merged["shot_boundary_source"] = sbs

    merged["chunking_metadata"] = _build_chunking_metadata(chunks, provider)

    # Single validation gate (RESEARCH Pitfall 2)
    validate_artifact("video_analysis", merged)
    return merged
