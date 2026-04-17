"""ThreadPoolExecutor orchestrator for chunked video analysis.

Pure lib module — NOT a BaseTool. Exposes two public functions:

* ``analyze_chunked(video_path, provider_tool, *, on_chunk_done=None,
  on_chunk_error="fail_fast", cost_tracker=None, max_workers=None) -> dict``
* ``estimate_chunked_cost(provider, duration_seconds, model,
  max_chunk_seconds=300.0) -> dict``

Implements Phase 4 requirements:

* **CHUNK-03** — bounded concurrency (ThreadPoolExecutor + as_completed)
  drives any ``video_analysis`` provider tool across chunks produced by
  ``lib.video_chunker.split_video``. Temp files cleaned up via
  ``try/finally`` — survives provider AND merger exceptions.
* **CHUNK-06** — per-chunk ``cost_tracker`` integration
  (estimate → reserve → reconcile) with descriptive ``operation``
  strings so budget reports can correlate spend by video. Pre-run
  cost surfacing via ``estimate_chunked_cost`` heuristic.

Designed for consumption by the Phase 6 meta skill
``skills/meta/reference-synthesis.md`` — the pipeline-level glue that
calls this orchestrator directly. Never invokes ``lib.checkpoint.
write_checkpoint`` (Phase 1 WR-05 contract: only orchestrators
/ meta skills own checkpointing).

Concurrency (RESEARCH § Pattern 3):

* Worker pool sized ``max_workers`` resolved as ``arg > env
  VIDEO_CHUNK_WORKERS > default(4)``, clamped to ``[1, 8]``. An
  unparseable env value falls back to default with a WARNING log
  (RESEARCH Pitfall 4).
* ``concurrent.futures.as_completed`` iteration surfaces per-chunk
  progress to ``on_chunk_done(idx, ToolResult)`` in completion order.
* Callback exceptions are logged but NEVER propagate (a bad caller
  callback must not kill an otherwise healthy analysis pool).
* After all futures resolve, per-chunk results are sorted back into
  submission order before being passed to the merger.

Error modes:

* ``on_chunk_error="fail_fast"`` (default) — first provider exception
  raises out of ``analyze_chunked``. Cleanup still runs via try/finally.
* ``on_chunk_error="continue"`` — swallow per-chunk exceptions,
  synthesize a failed ``ToolResult`` for the affected chunk, and mark
  ``chunking_metadata.failed_chunks: list[int]`` on the merged artifact.
  If ALL chunks fail, ``RuntimeError`` is raised instead of returning
  an empty merge.

Cost tracker (RESEARCH Pitfall 7):

* When ``cost_tracker`` is provided, each chunk gets
  ``estimate(tool=provider.name, operation=f"chunked_analysis[chunk
  {i+1}/{N} of {video_name}]", estimated_usd=0.0)`` → ``reserve(id)``
  before submit, then ``reconcile(id, actual_usd=result.cost_usd,
  success=result.success)`` after the future resolves.
* The ``operation`` string uses ``Path(video_path).name`` (basename)
  to avoid leaking full filesystem paths into the cost log
  (STRIDE T-04-17).

Cost estimation (RESEARCH § Code Examples):

* ``estimate_chunked_cost`` uses Gemini's documented 263 tokens/sec
  video rate + a per-chunk output-token upper bound, multiplied by
  a module-level ``_PRICING`` table stamped ``verified: '2026-04-17'``.
  Unknown models return ``{total_usd: None, confidence: 'unknown'}``.
"""

from __future__ import annotations

import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Optional

from lib.analysis_merger import merge_analyses
from lib.video_chunker import Chunk, cleanup_chunks, split_video  # noqa: F401
from tools.base_tool import ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Pricing table — stamp every entry with `verified: 'YYYY-MM-DD'` so
# staleness is visible at a glance. Preview-model rates are volatile.
# Sources:
#   - https://ai.google.dev/gemini-api/docs/tokens (263 tokens/sec video rate)
#   - https://openrouter.ai/google/gemini-3.1-pro-preview (preview pricing)
#   - RESEARCH Assumptions A1, A2, A3
_PRICING_VERIFIED_AT = "2026-04-17"

_TOKENS_PER_VIDEO_SECOND = 263  # Gemini documented rate
_OUTPUT_TOKENS_PER_CHUNK = 1500  # empirical upper bound for canonical artifact

_PRICING: dict[str, dict[str, Any]] = {
    # per-million-token rates (USD)
    "gemini-3.1-pro-preview": {
        "input": 2.00,
        "output": 12.00,
        "verified": "2026-04-17",
    },
    "gemini-2.5-pro": {
        "input": 1.25,
        "output": 10.00,
        "verified": "2026-04-17",
    },
    "google/gemini-3.1-pro-preview": {
        "input": 2.00,
        "output": 12.00,
        "verified": "2026-04-17",
    },
    "google/gemini-2.5-pro": {
        "input": 1.25,
        "output": 10.00,
        "verified": "2026-04-17",
    },
}

# Worker count envelope (RESEARCH Pitfall 4 + CONTEXT lock).
_WORKER_MIN = 1
_WORKER_MAX = 8
_WORKER_DEFAULT = 4
_WORKER_ENV_VAR = "VIDEO_CHUNK_WORKERS"


# ---------------------------------------------------------------------------
# Worker resolution
# ---------------------------------------------------------------------------


def _resolve_workers(max_workers: Optional[int]) -> int:
    """Resolve the effective max_workers count.

    Priority: ``arg > env VIDEO_CHUNK_WORKERS > default(4)``. Result is
    clamped to ``[_WORKER_MIN, _WORKER_MAX]``. An unparseable env value
    logs WARNING and falls back to the default (RESEARCH Pitfall 4).
    """
    if max_workers is not None:
        n = int(max_workers)
    else:
        env_val = os.environ.get(_WORKER_ENV_VAR)
        if env_val is None:
            n = _WORKER_DEFAULT
        else:
            try:
                n = int(env_val)
            except ValueError:
                logger.warning(
                    "Invalid %s=%r; using default %d",
                    _WORKER_ENV_VAR,
                    env_val,
                    _WORKER_DEFAULT,
                )
                n = _WORKER_DEFAULT
    return max(_WORKER_MIN, min(_WORKER_MAX, n))


# ---------------------------------------------------------------------------
# Cost estimation (pre-run surfacing hook)
# ---------------------------------------------------------------------------


def estimate_chunked_cost(
    provider: str,
    duration_seconds: float,
    model: str,
    max_chunk_seconds: float = 300.0,
) -> dict:
    """Rough pre-run cost estimate with ±30% uncertainty (RESEARCH § Code Examples).

    Returns a dict with ``total_usd``, ``low_usd``, ``high_usd``,
    ``chunk_count``, ``input_tokens_est``, ``output_tokens_est``,
    and ``pricing_verified_at`` for known models. Unknown models
    return ``{total_usd: None, confidence: 'unknown', note: ...}``.

    Parameters
    ----------
    provider:
        Provider name (currently informational; model is the real key).
    duration_seconds:
        Probed duration of the source video.
    model:
        Model name — must be a key in ``_PRICING`` for a quantitative
        estimate. Try e.g. ``"gemini-3.1-pro-preview"`` or
        ``"google/gemini-3.1-pro-preview"`` (OpenRouter prefix).
    max_chunk_seconds:
        Same value that will be passed to ``split_video``.
    """
    pricing = _PRICING.get(model)
    if pricing is None:
        return {
            "total_usd": None,
            "confidence": "unknown",
            "note": f"No pricing table entry for model {model!r}",
        }

    chunk_count = max(1, math.ceil(duration_seconds / max_chunk_seconds))
    input_tokens = duration_seconds * _TOKENS_PER_VIDEO_SECOND
    output_tokens = chunk_count * _OUTPUT_TOKENS_PER_CHUNK
    total = (
        input_tokens * pricing["input"] / 1_000_000
        + output_tokens * pricing["output"] / 1_000_000
    )
    return {
        "total_usd": round(total, 4),
        "low_usd": round(total * 0.7, 4),
        "high_usd": round(total * 1.3, 4),
        "chunk_count": chunk_count,
        "input_tokens_est": int(input_tokens),
        "output_tokens_est": int(output_tokens),
        "pricing_verified_at": pricing["verified"],
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


ChunkCallback = Optional[Callable[[int, ToolResult], None]]


def _fire_callback(
    on_chunk_done: ChunkCallback,
    idx: int,
    result: ToolResult,
) -> None:
    """Invoke ``on_chunk_done`` defensively — callback exceptions never propagate."""
    if on_chunk_done is None:
        return
    try:
        on_chunk_done(idx, result)
    except Exception:  # pragma: no cover — defensive
        logger.exception(
            "on_chunk_done callback raised for chunk %d — swallowed", idx
        )


def _analyze_chunks(
    chunks: list[Chunk],
    provider_tool: Any,
    max_workers: int,
    on_chunk_done: ChunkCallback,
    on_chunk_error: str,
    cost_tracker: Optional[Any],
    video_name: str,
) -> list[tuple[int, Chunk, ToolResult]]:
    """Submit each chunk to ``provider_tool.execute`` on a thread pool.

    Returns per-chunk ``(idx, chunk, ToolResult)`` triples sorted by
    submission index (original temporal order) so downstream merger
    sees chunks in the order they occurred in the source video.

    Cost tracker (when given) is called per chunk:
      - ``estimate`` with a descriptive operation string
      - ``reserve`` before submit
      - ``reconcile`` after future resolves (actual_usd = result.cost_usd,
        success = result.success)
    """
    total = len(chunks)
    results: list[tuple[int, Chunk, ToolResult]] = []
    tool_name = getattr(provider_tool, "name", None) or "video_analyzer"

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_meta: dict = {}
        for i, chunk in enumerate(chunks):
            entry_id: Optional[str] = None
            if cost_tracker is not None:
                entry_id = cost_tracker.estimate(
                    tool=tool_name,
                    operation=(
                        f"chunked_analysis[chunk {i+1}/{total} of {video_name}]"
                    ),
                    estimated_usd=0.0,
                )
                cost_tracker.reserve(entry_id)
            fut = pool.submit(
                provider_tool.execute, {"video_path": chunk.local_path}
            )
            future_to_meta[fut] = (i, chunk, entry_id)
            logger.info(
                "Submitted chunk %d/%d (path=%s)",
                i + 1,
                total,
                chunk.local_path,
            )

        for fut in as_completed(future_to_meta):
            idx, chunk, entry_id = future_to_meta[fut]
            try:
                res = fut.result()
            except Exception as exc:
                if on_chunk_error == "fail_fast":
                    # Best-effort reconcile before the raise unwinds
                    if cost_tracker is not None and entry_id is not None:
                        try:
                            cost_tracker.reconcile(
                                entry_id, actual_usd=0.0, success=False
                            )
                        except Exception:  # pragma: no cover — defensive
                            logger.exception(
                                "cost_tracker.reconcile failed for chunk %d", idx
                            )
                    raise
                # "continue" mode — synthesize failed ToolResult and keep going
                res = ToolResult(
                    success=False, error=f"chunk {idx} failed: {exc}"
                )
            if cost_tracker is not None and entry_id is not None:
                try:
                    cost_tracker.reconcile(
                        entry_id,
                        actual_usd=float(getattr(res, "cost_usd", 0.0) or 0.0),
                        success=bool(res.success),
                    )
                except Exception:  # pragma: no cover — defensive
                    logger.exception(
                        "cost_tracker.reconcile failed for chunk %d", idx
                    )
            logger.info(
                "Chunk %d/%d completed (success=%s)",
                idx + 1,
                total,
                res.success,
            )
            results.append((idx, chunk, res))
            _fire_callback(on_chunk_done, idx, res)

    # Restore submission order for the merger
    results.sort(key=lambda t: t[0])
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_chunked(
    video_path: str,
    provider_tool: Any,
    *,
    on_chunk_done: ChunkCallback = None,
    on_chunk_error: str = "fail_fast",
    cost_tracker: Optional[Any] = None,
    max_workers: Optional[int] = None,
) -> dict:
    """Split ``video_path`` into chunks, analyze each via ``provider_tool``,
    and return one merged canonical ``video_analysis`` artifact.

    Pipeline:
        1. ``split_video(video_path)`` — may raise ``VideoChunkingError``,
           which propagates without analysis (cleanup is split_video's
           responsibility on its own failure path).
        2. ``_analyze_chunks`` — bounded ThreadPoolExecutor runs each
           chunk through ``provider_tool.execute``; ``on_chunk_done``
           callback fires per completion.
        3. Per-chunk ``ToolResult.data`` artifacts get stamped with
           ``_cost_usd`` + ``_provider_used`` (internal hints consumed
           and stripped by the merger).
        4. ``merge_analyses`` produces the merged artifact.
        5. If any chunks failed in ``on_chunk_error="continue"`` mode,
           ``chunking_metadata.failed_chunks`` is populated.
        6. ``cleanup_chunks`` runs via try/finally — guaranteed even on
           provider or merger exception.

    Parameters
    ----------
    video_path:
        Absolute path to the source video.
    provider_tool:
        Any object with ``.name``, ``.provider``, and
        ``.execute({"video_path": ...}) -> ToolResult`` — works with
        ``video_analyzer_selector`` OR a concrete provider BaseTool.
    on_chunk_done:
        Optional callback ``(int, ToolResult) -> None`` fired after each
        chunk future resolves. Callback exceptions are logged and
        swallowed.
    on_chunk_error:
        ``"fail_fast"`` (default) — first exception raises.
        ``"continue"`` — swallow, mark ``failed_chunks``, merge survivors.
    cost_tracker:
        Optional ``CostTracker``-shaped object supporting
        ``estimate(tool, operation, estimated_usd) -> str`` /
        ``reserve(entry_id)`` / ``reconcile(entry_id, actual_usd,
        success)``. When provided, a trio of calls fires per chunk.
    max_workers:
        Thread pool size. Resolves via ``arg > env VIDEO_CHUNK_WORKERS
        > default(4)``, clamped ``[1, 8]``.

    Returns
    -------
    dict:
        Schema-valid canonical ``video_analysis`` artifact with
        ``chunking_metadata`` attached. When single-chunk bypass
        triggers (video ≤ max_chunk_seconds), the merger's pass-through
        path is exercised and ``chunking_metadata.chunk_count == 1``.

    Raises
    ------
    VideoChunkingError:
        When ``split_video`` fails (ffmpeg/ffprobe error).
    RuntimeError:
        When ``on_chunk_error="continue"`` but all chunks failed, or
        (via ``fail_fast``) the first provider exception.
    ValidationError:
        When the merged artifact doesn't satisfy the canonical schema
        (indicates a merger bug — provider-side validation catches
        per-chunk issues upstream).
    """
    video_path_str = str(video_path)
    video_name = Path(video_path_str).name
    provider_name = getattr(provider_tool, "provider", None) or "unknown"

    t0 = time.monotonic()
    logger.info("analyze_chunked: splitting %s", video_path_str)
    chunks = split_video(video_path_str)  # may raise VideoChunkingError
    logger.info("analyze_chunked: produced %d chunk(s)", len(chunks))

    try:
        n_workers = _resolve_workers(max_workers)
        logger.info(
            "analyze_chunked: analyzing with max_workers=%d", n_workers
        )
        results = _analyze_chunks(
            chunks=chunks,
            provider_tool=provider_tool,
            max_workers=n_workers,
            on_chunk_done=on_chunk_done,
            on_chunk_error=on_chunk_error,
            cost_tracker=cost_tracker,
            video_name=video_name,
        )

        # Stamp per-chunk hints the merger consumes + strip failed chunks
        pairs: list[tuple[Chunk, dict]] = []
        failed_idxs: list[int] = []
        for idx, chunk, tool_result in results:
            if not tool_result.success:
                failed_idxs.append(idx)
                # fail_fast would already have raised inside _analyze_chunks;
                # any non-success we see here must be "continue" mode.
                continue
            artifact = dict(tool_result.data or {})
            artifact["_cost_usd"] = float(tool_result.cost_usd or 0.0)
            artifact["_provider_used"] = str(
                tool_result.model or provider_name
            )
            pairs.append((chunk, artifact))

        if not pairs:
            # All chunks failed under "continue" mode — refuse to emit
            # an empty merge (schema has required fields per dimension).
            raise RuntimeError(
                "All chunks failed; cannot merge empty set "
                f"(failed_chunks={failed_idxs})"
            )

        logger.info(
            "analyze_chunked: merging %d chunk artifact(s) (failed=%d)",
            len(pairs),
            len(failed_idxs),
        )
        merged = merge_analyses(pairs, provider=provider_name)
        if failed_idxs:
            # merge_analyses already attached chunking_metadata; enrich it.
            merged.setdefault("chunking_metadata", {})["failed_chunks"] = (
                sorted(failed_idxs)
            )
        elapsed = time.monotonic() - t0
        logger.info(
            "analyze_chunked: done in %.2fs (chunks=%d, failed=%d)",
            elapsed,
            len(chunks),
            len(failed_idxs),
        )
        return merged
    finally:
        # Guaranteed cleanup — runs even on provider exception AND merger
        # exception. The bypass-sentinel guard inside cleanup_chunks
        # protects the user's original file (RESEARCH Open Question 4).
        try:
            cleanup_chunks(chunks, original_path=video_path_str)
        except Exception:  # pragma: no cover — cleanup_chunks swallows internally
            logger.exception("cleanup_chunks raised unexpectedly")
