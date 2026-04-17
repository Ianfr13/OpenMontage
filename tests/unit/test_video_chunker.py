"""Unit tests for `lib/video_chunker.py` (Phase 4, Plan 04-01).

All subprocess invocations are mocked — tests run on hosts without
ffmpeg/ffprobe installed (CI-safe). The stateful `FakeRun` helper
sequences ffprobe + ffmpeg calls so each test documents the exact
shape of subprocess traffic it expects.

Covers CHUNK-01 + CHUNK-02 + the bypass-sentinel cleanup guard
(RESEARCH Open Question #4).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from lib.analysis_errors import VideoAnalysisError, VideoChunkingError
from lib.video_chunker import (
    Chunk,
    cleanup_chunks,
    split_video,
)


# ---------------------------------------------------------------------------
# Stateful subprocess fake
# ---------------------------------------------------------------------------


class FakeRun:
    """Sequenced `subprocess.run` stand-in.

    Drive it with a list of `responses`; each response is either:
      * a CompletedProcess-like MagicMock (stdout/stderr/returncode=0)
      * a `subprocess.CalledProcessError` to raise

    The fake records every invocation into `.calls` for assertion.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, cmd, *args, **kwargs):
        # Always record the argv — tests assert on shape.
        self.calls.append(list(cmd))
        if not self._responses:
            raise AssertionError(
                f"FakeRun ran out of scripted responses — extra call: {cmd}"
            )
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def _ok(stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = 0
    m.stdout = stdout
    m.stderr = stderr
    return m


def _cpe(stderr: str, cmd=("ffprobe",)) -> subprocess.CalledProcessError:
    err = subprocess.CalledProcessError(returncode=1, cmd=list(cmd))
    err.stderr = stderr
    err.stdout = ""
    return err


# ---------------------------------------------------------------------------
# Task 1 — Chunk namedtuple + error class + bypass path
# ---------------------------------------------------------------------------


def test_chunk_namedtuple_fields():
    assert Chunk._fields == ("start_global", "end_global", "local_path")
    c = Chunk(0.0, 1.0, "/tmp/x.mp4")
    assert c.start_global == 0.0
    assert c.end_global == 1.0
    assert c.local_path == "/tmp/x.mp4"


def test_VideoChunkingError_extends_VideoAnalysisError():
    assert issubclass(VideoChunkingError, VideoAnalysisError)
    assert issubclass(VideoChunkingError, Exception)
    # The base stays intact.
    assert issubclass(VideoAnalysisError, Exception)


def test_duration_probe_parses_scalar(monkeypatch, fake_video):
    fake = FakeRun([_ok(stdout="123.456\n")])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    # Block tempfile.mkdtemp — this is the bypass path, nothing should splat.
    monkeypatch.setattr(
        "lib.video_chunker.tempfile.mkdtemp",
        lambda *a, **kw: pytest.fail("mkdtemp called on short-video bypass"),
    )
    # max_chunk_seconds larger than duration → bypass; the single call here
    # IS the probe. 123.456 ≤ 300 → bypass returns a single Chunk.
    chunks = split_video(fake_video)
    assert len(chunks) == 1
    assert chunks[0] == Chunk(0.0, 123.456, str(fake_video))
    assert len(fake.calls) == 1
    # ffprobe invocation shape — first arg is the binary; last is the path.
    probe_cmd = fake.calls[0]
    assert probe_cmd[0] == "ffprobe"
    assert "format=duration" in probe_cmd
    assert probe_cmd[-1] == str(fake_video)


def test_short_video_bypass(monkeypatch, fake_video):
    """120s video, default 300s max → single Chunk == original path; NO ffmpeg, NO mkdtemp."""
    fake = FakeRun([_ok(stdout="120.0")])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    monkeypatch.setattr(
        "lib.video_chunker.tempfile.mkdtemp",
        lambda *a, **kw: pytest.fail("tempdir must NOT be created on bypass"),
    )

    chunks = split_video(fake_video, max_chunk_seconds=300.0)

    assert chunks == [Chunk(0.0, 120.0, str(fake_video))]
    # Exactly ONE subprocess call (the probe). No ffmpeg.
    assert len(fake.calls) == 1
    assert fake.calls[0][0] == "ffprobe"


def test_exact_boundary_bypass(monkeypatch, fake_video):
    """duration == max_chunk_seconds → bypass (≤ semantics, not <)."""
    fake = FakeRun([_ok(stdout="300.0")])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    monkeypatch.setattr(
        "lib.video_chunker.tempfile.mkdtemp",
        lambda *a, **kw: pytest.fail("tempdir must NOT be created at boundary"),
    )
    chunks = split_video(fake_video, max_chunk_seconds=300.0)
    assert len(chunks) == 1
    assert chunks[0].end_global == 300.0
    assert chunks[0].local_path == str(fake_video)


def test_duration_probe_malformed_raises(monkeypatch, fake_video):
    """Empty stdout from ffprobe → VideoChunkingError."""
    fake = FakeRun([_ok(stdout="")])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    with pytest.raises(VideoChunkingError) as exc:
        split_video(fake_video)
    assert "ffprobe returned unparseable duration" in str(exc.value)


def test_ffprobe_nonzero_exit_raises_chunking_error(monkeypatch, fake_video):
    """ffprobe subprocess failure → VideoChunkingError, stderr in message."""
    fake = FakeRun([_cpe(stderr="moov atom not found")])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    with pytest.raises(VideoChunkingError) as exc:
        split_video(fake_video)
    assert "moov atom not found" in str(exc.value)


# ---------------------------------------------------------------------------
# Task 2 — Multi-chunk path + cleanup helper
# ---------------------------------------------------------------------------


def _stage_multi_chunk(tmp_path: Path, chunk_durs: list[float]) -> tuple[FakeRun, Path, list[Path]]:
    """Build a FakeRun driving: source probe → ffmpeg → per-chunk probes.

    Returns (fake, tmpdir, chunk_paths).  Tests wire `mkdtemp` to return tmpdir
    and `glob` to return the chunk_paths so the chunker iterates them.
    """
    tmpdir = tmp_path / "omvid_chunks_fake"
    tmpdir.mkdir()
    chunk_paths: list[Path] = []
    for i in range(len(chunk_durs)):
        p = tmpdir / f"chunk_{i:03d}.mp4"
        p.write_bytes(b"\x00")  # so Path.exists passes if ever checked
        chunk_paths.append(p)

    total = sum(chunk_durs)
    responses: list = [
        _ok(stdout=f"{total}\n"),  # source duration probe
        _ok(stderr="ffmpeg ran fine"),  # ffmpeg split
    ]
    for d in chunk_durs:
        responses.append(_ok(stdout=f"{d}\n"))
    return FakeRun(responses), tmpdir, chunk_paths


def test_ffmpeg_invocation_args(monkeypatch, fake_video, tmp_path):
    """ffmpeg split argv must match the locked command exactly."""
    fake, tmpdir, chunk_paths = _stage_multi_chunk(tmp_path, [298.0, 303.0, 299.0])

    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    monkeypatch.setattr("lib.video_chunker.tempfile.mkdtemp", lambda *a, **kw: str(tmpdir))

    split_video(fake_video, max_chunk_seconds=300.0)

    # calls[0] = source probe, calls[1] = ffmpeg, calls[2..] = per-chunk probes
    ffmpeg_cmd = fake.calls[1]
    assert ffmpeg_cmd == [
        "ffmpeg",
        "-y",
        "-i",
        str(fake_video),
        "-c",
        "copy",
        "-map",
        "0",
        "-reset_timestamps",
        "1",
        "-f",
        "segment",
        "-segment_time",
        "300.0",
        "-segment_start_number",
        "0",
        str(tmpdir / "chunk_%03d.mp4"),
    ]


def test_chunk_structure(monkeypatch, fake_video, tmp_path):
    """900s video, PER-CHUNK probed durations 298/303/299 → monotonic start_global."""
    fake, tmpdir, _ = _stage_multi_chunk(tmp_path, [298.0, 303.0, 299.0])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    monkeypatch.setattr("lib.video_chunker.tempfile.mkdtemp", lambda *a, **kw: str(tmpdir))

    chunks = split_video(fake_video, max_chunk_seconds=300.0)

    assert len(chunks) == 3
    starts = [c.start_global for c in chunks]
    ends = [c.end_global for c in chunks]
    # Monotonic non-decreasing, derived from PER-CHUNK probes (NOT nominal 300).
    assert starts == [0.0, 298.0, 601.0]
    assert ends == [298.0, 601.0, 900.0]
    # First chunk starts at 0 exactly; last end is within tolerance of total.
    assert chunks[0].start_global == 0.0
    assert abs(chunks[-1].end_global - 900.0) < 0.5


def test_chunk_paths_sorted(monkeypatch, fake_video, tmp_path):
    """Even if ffmpeg returns files discovered out-of-order, chunker sorts them."""
    # Write files in a specific order; rely on Path.glob + sorted() for lex order.
    fake, tmpdir, _ = _stage_multi_chunk(tmp_path, [100.0, 100.0, 100.0])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    monkeypatch.setattr("lib.video_chunker.tempfile.mkdtemp", lambda *a, **kw: str(tmpdir))

    chunks = split_video(fake_video, max_chunk_seconds=50.0)

    paths = [c.local_path for c in chunks]
    assert paths == sorted(paths)
    # And each path sits in the fake tmpdir.
    for p in paths:
        assert Path(p).parent == tmpdir


def test_ffmpeg_failure_raises(monkeypatch, fake_video, tmp_path):
    """ffmpeg non-zero → VideoChunkingError, tmpdir rmtree'd (no leak)."""
    tmpdir = tmp_path / "omvid_chunks_fail"
    tmpdir.mkdir()

    fake = FakeRun([
        _ok(stdout="900.0\n"),  # source probe → triggers multi-chunk branch
        _cpe(stderr="invalid data", cmd=("ffmpeg",)),
    ])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    monkeypatch.setattr("lib.video_chunker.tempfile.mkdtemp", lambda *a, **kw: str(tmpdir))

    rmtree_calls: list[tuple[str, dict]] = []

    def spy_rmtree(path, *args, **kwargs):
        rmtree_calls.append((str(path), kwargs))

    monkeypatch.setattr("lib.video_chunker.shutil.rmtree", spy_rmtree)

    with pytest.raises(VideoChunkingError) as exc:
        split_video(fake_video, max_chunk_seconds=300.0)
    assert "invalid data" in str(exc.value)
    # tmpdir cleaned up once on ffmpeg failure.
    assert any(str(tmpdir) == p for p, _ in rmtree_calls), (
        f"expected rmtree({tmpdir}) on ffmpeg failure; got {rmtree_calls}"
    )


def test_ffmpeg_success_tempdir_survives(monkeypatch, fake_video, tmp_path):
    """On successful split, tmpdir is NOT rmtree'd — lifecycle is caller's."""
    fake, tmpdir, _ = _stage_multi_chunk(tmp_path, [300.0, 300.0, 300.0])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    monkeypatch.setattr("lib.video_chunker.tempfile.mkdtemp", lambda *a, **kw: str(tmpdir))

    rmtree_calls: list[str] = []

    def spy_rmtree(path, *args, **kwargs):
        rmtree_calls.append(str(path))

    monkeypatch.setattr("lib.video_chunker.shutil.rmtree", spy_rmtree)

    chunks = split_video(fake_video, max_chunk_seconds=300.0)
    assert len(chunks) == 3
    assert rmtree_calls == []  # tmpdir preserved for caller
    # And tmpdir still exists on disk.
    assert tmpdir.exists()


def test_ffprobe_per_chunk_called(monkeypatch, fake_video, tmp_path):
    """3-chunk path ⇒ ffprobe called 4 times (source + 3 chunks).

    Each per-chunk probe must target the chunk_XXX.mp4 path, not the source.
    """
    fake, tmpdir, chunk_paths = _stage_multi_chunk(tmp_path, [100.0, 100.0, 100.0])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    monkeypatch.setattr("lib.video_chunker.tempfile.mkdtemp", lambda *a, **kw: str(tmpdir))

    split_video(fake_video, max_chunk_seconds=50.0)

    # Count ffprobe vs ffmpeg invocations
    probes = [c for c in fake.calls if c[0] == "ffprobe"]
    ffmpegs = [c for c in fake.calls if c[0] == "ffmpeg"]
    assert len(probes) == 4  # 1 source + 3 per-chunk
    assert len(ffmpegs) == 1
    # First probe targets source; remaining three target chunk files.
    assert probes[0][-1] == str(fake_video)
    per_chunk_targets = sorted(p[-1] for p in probes[1:])
    expected = sorted(str(p) for p in chunk_paths)
    assert per_chunk_targets == expected


def test_nonexistent_input_raises(tmp_path):
    """split_video on a path that doesn't exist → VideoChunkingError."""
    missing = tmp_path / "does" / "not" / "exist.mp4"
    with pytest.raises(VideoChunkingError) as exc:
        split_video(str(missing))
    assert "Input not a file" in str(exc.value)


def test_empty_glob_raises_and_cleans(monkeypatch, fake_video, tmp_path):
    """ffmpeg exits 0 but emits no files → VideoChunkingError + rmtree."""
    tmpdir = tmp_path / "omvid_chunks_empty"
    tmpdir.mkdir()  # exists but no chunk_*.mp4 inside

    fake = FakeRun([
        _ok(stdout="900.0\n"),
        _ok(stderr="ffmpeg fine but empty"),
    ])
    monkeypatch.setattr("lib.video_chunker.subprocess.run", fake)
    monkeypatch.setattr("lib.video_chunker.tempfile.mkdtemp", lambda *a, **kw: str(tmpdir))

    rmtree_calls: list[str] = []
    monkeypatch.setattr(
        "lib.video_chunker.shutil.rmtree",
        lambda p, *a, **kw: rmtree_calls.append(str(p)),
    )

    with pytest.raises(VideoChunkingError) as exc:
        split_video(fake_video, max_chunk_seconds=300.0)
    assert "no chunk files" in str(exc.value).lower()
    assert str(tmpdir) in rmtree_calls


# ---------------------------------------------------------------------------
# cleanup_chunks
# ---------------------------------------------------------------------------


def test_cleanup_chunks_removes_parent_dirs(monkeypatch, tmp_path):
    """All chunks under one parent → rmtree called ONCE with the parent."""
    parent = tmp_path / "omvid_chunks_XXX"
    parent.mkdir()
    chunks = [
        Chunk(0.0, 300.0, str(parent / "chunk_000.mp4")),
        Chunk(300.0, 600.0, str(parent / "chunk_001.mp4")),
        Chunk(600.0, 900.0, str(parent / "chunk_002.mp4")),
    ]
    rmtree_calls: list[tuple[str, dict]] = []

    def spy_rmtree(path, *args, **kwargs):
        rmtree_calls.append((str(path), kwargs))

    monkeypatch.setattr("lib.video_chunker.shutil.rmtree", spy_rmtree)

    cleanup_chunks(chunks, original_path="/some/input.mp4")

    assert len(rmtree_calls) == 1
    assert rmtree_calls[0][0] == str(parent)
    # ignore_errors=True per Pitfall 5
    assert rmtree_calls[0][1].get("ignore_errors") is True


def test_cleanup_chunks_skips_bypass_sentinel(monkeypatch, tmp_path):
    """Bypass case: chunk.local_path == original_path ⇒ rmtree NEVER called."""
    original = tmp_path / "user_input.mp4"
    original.write_bytes(b"\x00")
    chunks = [Chunk(0.0, 120.0, str(original))]

    rmtree_calls: list[str] = []
    monkeypatch.setattr(
        "lib.video_chunker.shutil.rmtree",
        lambda p, *a, **kw: rmtree_calls.append(str(p)),
    )

    cleanup_chunks(chunks, original_path=str(original))

    assert rmtree_calls == []  # user's input file untouched
    # Belt-and-braces — the input file still exists on disk.
    assert original.exists()


def test_cleanup_chunks_ignores_errors(monkeypatch, tmp_path):
    """shutil.rmtree with ignore_errors=True must swallow OSError-like cases.

    We can't verify the suppressed-error path directly (shutil.rmtree itself
    handles it), but we can confirm `cleanup_chunks` doesn't wrap rmtree in
    its own try/except that would re-raise — it simply passes ignore_errors.
    """
    parent = tmp_path / "omvid_chunks_err"
    parent.mkdir()
    chunks = [Chunk(0.0, 300.0, str(parent / "chunk_000.mp4"))]

    captured_kwargs: dict = {}

    def spy_rmtree(path, *args, **kwargs):
        captured_kwargs.update(kwargs)

    monkeypatch.setattr("lib.video_chunker.shutil.rmtree", spy_rmtree)

    # Must not raise
    cleanup_chunks(chunks, original_path="/x.mp4")
    assert captured_kwargs.get("ignore_errors") is True


def test_cleanup_chunks_dedups_parents(monkeypatch, tmp_path):
    """Multiple chunks under the same parent → rmtree called ONCE for that parent."""
    parent1 = tmp_path / "pa"
    parent1.mkdir()
    parent2 = tmp_path / "pb"
    parent2.mkdir()
    chunks = [
        Chunk(0.0, 1.0, str(parent1 / "chunk_000.mp4")),
        Chunk(1.0, 2.0, str(parent1 / "chunk_001.mp4")),
        Chunk(2.0, 3.0, str(parent2 / "chunk_000.mp4")),
    ]
    rmtree_calls: list[str] = []
    monkeypatch.setattr(
        "lib.video_chunker.shutil.rmtree",
        lambda p, *a, **kw: rmtree_calls.append(str(p)),
    )
    cleanup_chunks(chunks, original_path="/x.mp4")
    assert sorted(rmtree_calls) == sorted([str(parent1), str(parent2)])
