"""FFmpeg stream-copy video chunker for long-form video analysis.

Pure lib module — NOT a BaseTool. Exposes three public names:

* ``Chunk`` — immutable 3-field namedtuple ``(start_global, end_global, local_path)``
* ``split_video(video_path, max_chunk_seconds=300.0) -> list[Chunk]``
* ``cleanup_chunks(chunks, original_path) -> None``

Implements Phase 4 requirements:

* **CHUNK-01** — split video into ≤ ``max_chunk_seconds`` keyframe-aligned
  chunks via ``ffmpeg -c copy -f segment -reset_timestamps 1``. No re-encode.
* **CHUNK-02** — videos ≤ ``max_chunk_seconds`` bypass chunking; return a
  single ``Chunk`` whose ``local_path`` points at the user's original file.
  No ffmpeg call, no tempdir.

The stream-copy segment muxer aligns cuts to the next keyframe ≥
``-segment_time``; `-reset_timestamps 1` resets each segment's PTS so
downstream tools see near-zero starts. Because keyframes don't land
exactly on the requested boundary, each produced chunk is probed
individually via ffprobe to derive its real duration — ``start_global``
/ ``end_global`` are accumulated from those real probes, not nominal
multiples (RESEARCH Pitfall 1).

Lifecycle contract (RESEARCH Pitfall 5): ``tempfile.mkdtemp`` returns a
plain path; the *caller* owns cleanup via ``cleanup_chunks`` once
analysis of all chunks is complete. Using ``TemporaryDirectory`` as a
context manager around the split would tear files down before the
async analyzer reads them.

Bypass sentinel (RESEARCH Open Question #4): ``cleanup_chunks`` skips
any chunk whose ``local_path`` equals the original input path so the
user's source file is never deleted.

Security (STRIDE T-04-01): every subprocess invocation uses a list
argv with ``shell=False``; ``video_path`` is stringified but never
interpolated into a shell string.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from collections import namedtuple
from pathlib import Path
from typing import Union

from lib.analysis_errors import VideoChunkingError

logger = logging.getLogger(__name__)

# Immutable, pickle-safe, lightweight.  Matches CONTEXT spec exactly.
Chunk = namedtuple("Chunk", ["start_global", "end_global", "local_path"])

# Subprocess timeouts — long enough for a multi-GB split; short enough to
# surface hung binaries.  ffprobe is a fast metadata read; 30s is generous.
_FFMPEG_TIMEOUT_SECONDS = 1800
_FFPROBE_TIMEOUT_SECONDS = 30

# P4-NI-02: single source of truth for the default chunk boundary.
# Referenced by split_video's default arg AND lib/chunked_analyzer's
# estimate_chunked_cost default. Keep in sync with CHUNK-02 (5 min).
_MAX_CHUNK_SECONDS_DEFAULT: float = 300.0


def _probe_duration_seconds(video_path: Path) -> float:
    """Return the media's duration in seconds via ``ffprobe``.

    Mirrors the shell-safe invocation pattern from
    ``tools/analysis/scene_detect.py:196-202`` — list argv,
    ``shell=False`` (default), explicit timeout.

    Raises ``VideoChunkingError`` on non-zero exit or unparseable stdout.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(video_path),
    ]
    logger.debug("ffprobe duration cmd: %s", cmd)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=_FFPROBE_TIMEOUT_SECONDS,
            shell=False,
        )
    except subprocess.CalledProcessError as e:
        raise VideoChunkingError(
            f"ffprobe failed on {video_path}: {e.stderr}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise VideoChunkingError(
            f"ffprobe timed out after {_FFPROBE_TIMEOUT_SECONDS}s on {video_path}"
        ) from e

    stdout = result.stdout or ""
    try:
        return float(stdout.strip())
    except ValueError as e:
        raise VideoChunkingError(
            f"ffprobe returned unparseable duration for {video_path}: {stdout!r}"
        ) from e


def split_video(
    video_path: Union[str, Path],
    max_chunk_seconds: float = _MAX_CHUNK_SECONDS_DEFAULT,
) -> list[Chunk]:
    """Split ``video_path`` into ≤ ``max_chunk_seconds`` chunks via FFmpeg.

    Returns a list of ``Chunk`` namedtuples with monotonic non-decreasing
    ``start_global`` values. If the probed duration is ≤ ``max_chunk_seconds``
    the input is returned verbatim as a single-element list (no ffmpeg call,
    no tempdir) — that path is called the *bypass sentinel*.

    Parameters
    ----------
    video_path:
        Path to a local video file. Accepts ``str`` or ``Path``.
    max_chunk_seconds:
        Maximum nominal chunk length requested from the segment muxer.
        Actual chunks may be slightly longer or shorter depending on
        keyframe placement (see RESEARCH Pitfall 1).

    Raises
    ------
    VideoChunkingError
        On missing/non-file input, ffprobe failure, ffmpeg non-zero exit,
        ffmpeg exit-zero-but-no-files, or subprocess timeout.
    """
    vp = Path(video_path)
    if not vp.exists() or not vp.is_file():
        raise VideoChunkingError(f"Input not a file: {video_path}")

    duration = _probe_duration_seconds(vp)

    # CHUNK-02 bypass: ≤5 min → return original path as single chunk.
    # Note ≤ (not <) so the exact boundary case also bypasses.
    if duration <= max_chunk_seconds:
        logger.debug(
            "Bypass: duration %.3fs ≤ max_chunk_seconds %.3f — returning single chunk",
            duration,
            max_chunk_seconds,
        )
        return [Chunk(start_global=0.0, end_global=duration, local_path=str(vp))]

    # Multi-chunk path.  tempdir ownership transfers to caller on success.
    tmpdir = Path(tempfile.mkdtemp(prefix="omvid_chunks_"))

    try:
        out_pattern = tmpdir / "chunk_%03d.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(vp),
            "-c",
            "copy",
            "-map",
            "0",
            "-reset_timestamps",
            "1",
            "-f",
            "segment",
            "-segment_time",
            str(float(max_chunk_seconds)),
            "-segment_start_number",
            "0",
            str(out_pattern),
        ]
        logger.debug("ffmpeg split cmd: %s", cmd)
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=_FFMPEG_TIMEOUT_SECONDS,
                shell=False,
            )
        except subprocess.CalledProcessError as e:
            # Clean up the empty/partial tempdir so we don't leak scratch
            # space on every failed split (RESEARCH § Pattern 2).
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise VideoChunkingError(
                f"ffmpeg split failed on {vp}: {e.stderr}"
            ) from e
        except subprocess.TimeoutExpired as e:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise VideoChunkingError(
                f"ffmpeg timed out after {_FFMPEG_TIMEOUT_SECONDS}s on {vp}"
            ) from e

        paths = sorted(tmpdir.glob("chunk_*.mp4"))
        if not paths:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise VideoChunkingError(
                f"ffmpeg produced no chunk files in {tmpdir}"
            )

        chunks: list[Chunk] = []
        running_start = 0.0
        for p in paths:
            # Per-chunk duration probe — real value, not nominal
            # max_chunk_seconds multiple (RESEARCH Pitfall 1).
            probed = _probe_duration_seconds(p)
            chunks.append(
                Chunk(
                    start_global=running_start,
                    end_global=running_start + probed,
                    local_path=str(p),
                )
            )
            running_start += probed

        logger.debug(
            "Split %s into %d chunks (total %.3fs) in %s",
            vp,
            len(chunks),
            running_start,
            tmpdir,
        )
        return chunks

    except VideoChunkingError:
        # _probe_duration_seconds may raise during the per-chunk loop —
        # clean up tmpdir before re-raising so callers don't leak scratch.
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise


def cleanup_chunks(
    chunks: list[Chunk],
    original_path: Union[str, Path],
) -> None:
    """Remove the tempdirs owned by the chunker.

    Deletes the unique *parent directories* of every chunk's ``local_path``
    via ``shutil.rmtree(..., ignore_errors=True)``. SKIPS any chunk whose
    ``local_path`` equals ``str(original_path)`` — that's the bypass
    sentinel (CHUNK-02) and deleting it would delete the user's input
    video (RESEARCH Open Question #4, STRIDE T-04-04).

    Safe to call multiple times. Never raises.
    """
    original_str = str(original_path)
    parents: set[Path] = set()
    for ch in chunks:
        if ch.local_path == original_str:
            # Bypass sentinel — do NOT touch user input.
            logger.debug(
                "cleanup_chunks: skipping bypass sentinel %s", ch.local_path
            )
            continue
        parents.add(Path(ch.local_path).parent)

    for parent in parents:
        logger.debug("cleanup_chunks: rmtree %s", parent)
        shutil.rmtree(parent, ignore_errors=True)
