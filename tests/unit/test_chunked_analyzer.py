"""Unit tests for lib/chunked_analyzer.py (Phase 4 Plan 03).

Covers:
* Worker count resolution (arg > env > default; clamp [1,8]; invalid env → default)
* ThreadPoolExecutor dispatch + as_completed + on_chunk_done callback
* Cleanup via try/finally on success, provider exception, merger exception
* estimate_chunked_cost heuristic + pricing table
* Cost-tracker integration (estimate / reserve / reconcile per chunk)
* on_chunk_error 'fail_fast' (default) + 'continue' modes
* Per-chunk artifact stamping (_cost_usd, _provider_used)
* VideoChunkingError propagation

Tests are offline: FFmpeg/ffprobe never invoked — split_video is monkeypatched
everywhere to return deterministic Chunk lists. Provider is a StubProvider
whose .execute() returns a schema-valid ToolResult (no network).
"""

from __future__ import annotations

import copy
import logging
from unittest.mock import MagicMock

import pytest

from lib.analysis_errors import VideoChunkingError
from lib.video_chunker import Chunk
from tools.base_tool import ToolResult

# Reuse the shared minimal artifact from Phase 1 contracts
from tests.contracts.test_video_analysis_schema import minimal_video_analysis


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class StubProvider:
    """Deterministic provider tool for chunked_analyzer tests.

    Each .execute() call returns a ToolResult whose .data is a deep copy of
    minimal_video_analysis() (schema valid). Can be configured to raise,
    return a custom cost/model, or return a failed ToolResult.
    """

    name = "stub_video_analyzer"
    # Schema constrains chunking_metadata.provider to {"gemini","openrouter"};
    # use "gemini" so merger validation passes end-to-end in tests.
    provider = "gemini"
    capability = "video_analysis"

    def __init__(
        self,
        artifact_factory=None,
        exc=None,
        cost=0.01,
        model="stub-model",
        fail_on_index=None,
        fail_modes=None,
    ):
        self._artifact = artifact_factory or (lambda: copy.deepcopy(minimal_video_analysis()))
        self._exc = exc
        self._cost = cost
        self._model = model
        self._fail_on_index = fail_on_index  # set of ints → raise on those call indices
        self._fail_modes = fail_modes or {}  # {idx: "raise"|"fail_result"}
        self._call_count = 0
        self.calls = []  # list of input dicts

    def execute(self, inputs):
        idx = self._call_count
        self._call_count += 1
        self.calls.append(dict(inputs))
        if self._fail_on_index is not None and idx in self._fail_on_index:
            mode = self._fail_modes.get(idx, "raise")
            if mode == "raise":
                raise RuntimeError(f"stub failure at call {idx}")
            return ToolResult(success=False, error=f"stub failed at {idx}")
        if self._exc:
            raise self._exc
        return ToolResult(
            success=True,
            data=self._artifact(),
            cost_usd=self._cost,
            model=self._model,
        )


def _make_chunks(n: int, chunk_seconds: float = 300.0) -> list[Chunk]:
    """Build N fake chunks with /tmp paths (never touched — split is mocked)."""
    return [
        Chunk(
            start_global=i * chunk_seconds,
            end_global=(i + 1) * chunk_seconds,
            local_path=f"/tmp/omvid_fake/chunk_{i:03d}.mp4",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Task 1 — worker resolution
# ---------------------------------------------------------------------------


class TestWorkerResolution:
    def test_worker_count_default(self, monkeypatch):
        monkeypatch.delenv("VIDEO_CHUNK_WORKERS", raising=False)
        from lib.chunked_analyzer import _resolve_workers

        assert _resolve_workers(None) == 4

    def test_worker_count_arg_wins(self, monkeypatch):
        monkeypatch.setenv("VIDEO_CHUNK_WORKERS", "7")
        from lib.chunked_analyzer import _resolve_workers

        # arg wins over env
        assert _resolve_workers(2) == 2

    def test_worker_count_env(self, monkeypatch):
        monkeypatch.setenv("VIDEO_CHUNK_WORKERS", "6")
        from lib.chunked_analyzer import _resolve_workers

        assert _resolve_workers(None) == 6

    def test_worker_count_clamp_low(self, monkeypatch):
        monkeypatch.delenv("VIDEO_CHUNK_WORKERS", raising=False)
        from lib.chunked_analyzer import _resolve_workers

        assert _resolve_workers(0) == 1
        assert _resolve_workers(-5) == 1

    def test_worker_count_clamp_high(self, monkeypatch):
        monkeypatch.delenv("VIDEO_CHUNK_WORKERS", raising=False)
        from lib.chunked_analyzer import _resolve_workers

        assert _resolve_workers(100) == 8

    def test_worker_count_env_clamped_high(self, monkeypatch):
        monkeypatch.setenv("VIDEO_CHUNK_WORKERS", "50")
        from lib.chunked_analyzer import _resolve_workers

        assert _resolve_workers(None) == 8

    def test_worker_count_env_clamped_low(self, monkeypatch):
        monkeypatch.setenv("VIDEO_CHUNK_WORKERS", "0")
        from lib.chunked_analyzer import _resolve_workers

        assert _resolve_workers(None) == 1

    def test_worker_count_invalid_env(self, monkeypatch, caplog):
        monkeypatch.setenv("VIDEO_CHUNK_WORKERS", "abc")
        from lib.chunked_analyzer import _resolve_workers

        with caplog.at_level(logging.WARNING, logger="lib.chunked_analyzer"):
            n = _resolve_workers(None)

        assert n == 4
        assert any("VIDEO_CHUNK_WORKERS" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Task 1 — ThreadPoolExecutor dispatch
# ---------------------------------------------------------------------------


class TestThreadPoolDispatch:
    def test_executor_submits_per_chunk(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(3)
        cleanup_spy = MagicMock()
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", cleanup_spy)

        provider = StubProvider()
        result = chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"), provider, max_workers=1
        )

        assert provider._call_count == 3
        # Each call got the chunk's local_path
        got_paths = [c["video_path"] for c in provider.calls]
        assert set(got_paths) == {c.local_path for c in chunks}
        assert result["version"] == "2.0"

    def test_callback_per_chunk(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(3)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        seen: list[tuple[int, ToolResult]] = []

        def cb(idx, result):
            seen.append((idx, result))

        chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"),
            StubProvider(),
            on_chunk_done=cb,
            max_workers=1,
        )

        assert len(seen) == 3
        assert {s[0] for s in seen} == {0, 1, 2}
        for idx, res in seen:
            assert isinstance(idx, int)
            assert isinstance(res, ToolResult)
            assert res.success is True

    def test_callback_exception_swallowed(self, monkeypatch, tmp_path, caplog):
        from lib import chunked_analyzer

        chunks = _make_chunks(2)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        def bad_cb(idx, result):
            raise RuntimeError(f"callback kaboom {idx}")

        with caplog.at_level(logging.ERROR, logger="lib.chunked_analyzer"):
            merged = chunked_analyzer.analyze_chunked(
                str(tmp_path / "ref.mp4"),
                StubProvider(),
                on_chunk_done=bad_cb,
                max_workers=1,
            )

        # Didn't propagate — returned a merged artifact
        assert merged["version"] == "2.0"
        assert merged["chunking_metadata"]["chunk_count"] == 2
        # Logged at least once
        assert any("on_chunk_done" in r.message.lower() or "callback" in r.message.lower()
                   for r in caplog.records)

    def test_results_restored_to_submission_order(self, monkeypatch, tmp_path):
        """Even if futures complete out-of-order, merger receives chunks in submission order."""
        from lib import chunked_analyzer

        chunks = _make_chunks(3)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        seen_order: list[Chunk] = []

        def fake_merge(pairs, provider):
            for chunk, art in pairs:
                seen_order.append(chunk)
            # return a minimal schema-valid artifact
            art = copy.deepcopy(minimal_video_analysis())
            art["chunking_metadata"] = {
                "chunk_count": len(pairs),
                "total_duration_s": sum(c.end_global - c.start_global for c, _ in pairs),
                "provider": provider,
                "per_chunk": [],
            }
            return art

        monkeypatch.setattr(chunked_analyzer, "merge_analyses", fake_merge)

        # max_workers=1 forces deterministic order but also means submission order
        # == completion order. To exercise the sort path, use max_workers=3 but
        # the test asserts the merger sees submission-order regardless of
        # completion order (enforced by sort in _analyze_chunks).
        chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"), StubProvider(), max_workers=3
        )

        assert [c.start_global for c in seen_order] == [0.0, 300.0, 600.0]


# ---------------------------------------------------------------------------
# Task 1 — Cleanup (try/finally)
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_cleanup_called_on_success(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(2)
        cleanup_spy = MagicMock()
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", cleanup_spy)

        path = str(tmp_path / "ref.mp4")
        chunked_analyzer.analyze_chunked(path, StubProvider(), max_workers=1)

        cleanup_spy.assert_called_once()
        args, kwargs = cleanup_spy.call_args
        assert args[0] == chunks or args[0] is chunks
        # Accept either positional or kwarg for original_path
        orig = kwargs.get("original_path") or (args[1] if len(args) > 1 else None)
        assert orig == path

    def test_cleanup_called_on_provider_exception(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(2)
        cleanup_spy = MagicMock()
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", cleanup_spy)

        provider = StubProvider(exc=RuntimeError("provider boom"))

        with pytest.raises(RuntimeError, match="provider boom"):
            chunked_analyzer.analyze_chunked(
                str(tmp_path / "ref.mp4"), provider, max_workers=1
            )

        cleanup_spy.assert_called_once()

    def test_cleanup_called_on_merger_exception(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(2)
        cleanup_spy = MagicMock()
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", cleanup_spy)
        monkeypatch.setattr(
            chunked_analyzer,
            "merge_analyses",
            MagicMock(side_effect=ValueError("merger kaboom")),
        )

        with pytest.raises(ValueError, match="merger kaboom"):
            chunked_analyzer.analyze_chunked(
                str(tmp_path / "ref.mp4"), StubProvider(), max_workers=1
            )

        cleanup_spy.assert_called_once()

    def test_single_chunk_bypass_cleanup_spares_original(self, monkeypatch, tmp_path):
        """For a ≤5min video, split_video returns [Chunk(..., local_path=<orig>)].

        analyze_chunked MUST still call cleanup_chunks (letting its sentinel
        guard the original path).
        """
        from lib import chunked_analyzer

        orig = str(tmp_path / "ref.mp4")
        bypass_chunk = Chunk(start_global=0.0, end_global=120.0, local_path=orig)
        cleanup_spy = MagicMock()
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: [bypass_chunk])
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", cleanup_spy)

        merged = chunked_analyzer.analyze_chunked(orig, StubProvider())

        cleanup_spy.assert_called_once()
        args, kwargs = cleanup_spy.call_args
        orig_arg = kwargs.get("original_path") or (args[1] if len(args) > 1 else None)
        assert orig_arg == orig
        assert merged["chunking_metadata"]["chunk_count"] == 1


# ---------------------------------------------------------------------------
# Task 1 — Cost estimation heuristic
# ---------------------------------------------------------------------------


class TestEstimateChunkedCost:
    def test_estimate_chunked_cost_known_model(self):
        from lib.chunked_analyzer import estimate_chunked_cost

        r = estimate_chunked_cost("gemini", 600.0, "gemini-3.1-pro-preview")
        assert r["chunk_count"] == 2
        assert r["total_usd"] > 0
        assert r["low_usd"] == round(r["total_usd"] * 0.7, 4)
        assert r["high_usd"] == round(r["total_usd"] * 1.3, 4)
        assert r["pricing_verified_at"] == "2026-04-17"
        assert r["input_tokens_est"] == int(600.0 * 263)
        assert r["output_tokens_est"] == 2 * 1500

    def test_estimate_chunked_cost_unknown_model(self):
        from lib.chunked_analyzer import estimate_chunked_cost

        r = estimate_chunked_cost("mystery", 600.0, "mystery-model")
        assert r["total_usd"] is None
        assert r["confidence"] == "unknown"
        assert "mystery-model" in r["note"]

    def test_estimate_chunked_cost_math_300s(self):
        """300s @ gemini-3.1-pro-preview:
        input_tokens = 300 * 263 = 78_900
        output_tokens = 1 * 1500 = 1_500
        total = 78_900 * 2 / 1e6 + 1500 * 12 / 1e6 = 0.1578 + 0.018 = 0.1758
        """
        from lib.chunked_analyzer import estimate_chunked_cost

        r = estimate_chunked_cost("gemini", 300.0, "gemini-3.1-pro-preview")
        assert r["chunk_count"] == 1
        assert abs(r["total_usd"] - 0.1758) < 0.0005

    def test_estimate_chunked_cost_one_chunk_min(self):
        """Very short video still counts as 1 chunk."""
        from lib.chunked_analyzer import estimate_chunked_cost

        r = estimate_chunked_cost("gemini", 30.0, "gemini-2.5-pro")
        assert r["chunk_count"] == 1

    def test_estimate_chunked_cost_ceil_division(self):
        """301s → 2 chunks (ceil)."""
        from lib.chunked_analyzer import estimate_chunked_cost

        r = estimate_chunked_cost("gemini", 301.0, "gemini-3.1-pro-preview")
        assert r["chunk_count"] == 2

    def test_estimate_chunked_cost_openrouter_prefix(self):
        from lib.chunked_analyzer import estimate_chunked_cost

        r = estimate_chunked_cost("openrouter", 300.0, "google/gemini-3.1-pro-preview")
        assert r["total_usd"] is not None
        assert r["pricing_verified_at"] == "2026-04-17"


# ---------------------------------------------------------------------------
# Task 2 — Cost tracker integration
# ---------------------------------------------------------------------------


class TestCostTrackerIntegration:
    def test_cost_tracker_per_chunk_estimate_reserve_reconcile(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(3)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        tracker = MagicMock()
        tracker.estimate = MagicMock(side_effect=lambda **kw: f"id-{kw['operation']}")
        tracker.reserve = MagicMock()
        tracker.reconcile = MagicMock()

        provider = StubProvider(cost=0.042)
        chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"),
            provider,
            cost_tracker=tracker,
            max_workers=1,
        )

        assert tracker.estimate.call_count == 3
        assert tracker.reserve.call_count == 3
        assert tracker.reconcile.call_count == 3

        # Descriptive operation strings with 1-indexed chunk num
        ops = [c.kwargs["operation"] for c in tracker.estimate.call_args_list]
        assert any("chunked_analysis[chunk 1/3 of ref.mp4]" in o for o in ops)
        assert any("chunked_analysis[chunk 2/3 of ref.mp4]" in o for o in ops)
        assert any("chunked_analysis[chunk 3/3 of ref.mp4]" in o for o in ops)

        # All reconciles with success=True and actual_usd == stub cost
        for call in tracker.reconcile.call_args_list:
            assert call.kwargs["success"] is True
            assert call.kwargs["actual_usd"] == pytest.approx(0.042)

    def test_cost_tracker_reconcile_on_failure(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(3)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        tracker = MagicMock()
        tracker.estimate = MagicMock(side_effect=lambda **kw: f"id-{kw['operation']}")
        tracker.reserve = MagicMock()
        tracker.reconcile = MagicMock()

        provider = StubProvider(fail_on_index={1}, fail_modes={1: "raise"})
        chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"),
            provider,
            cost_tracker=tracker,
            on_chunk_error="continue",
            max_workers=1,
        )

        assert tracker.reconcile.call_count == 3
        # At least one reconcile was for success=False
        fail_calls = [c for c in tracker.reconcile.call_args_list if c.kwargs["success"] is False]
        assert len(fail_calls) == 1

    def test_cost_tracker_none_skips(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(2)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"), StubProvider(), max_workers=1
        )
        # No assertion failures → tracker was never touched (nothing to assert on)

    def test_cost_tracker_operation_includes_video_name(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(2)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        tracker = MagicMock()
        tracker.estimate = MagicMock(return_value="eid")

        video = tmp_path / "my-reference-video.mp4"
        chunked_analyzer.analyze_chunked(
            str(video), StubProvider(), cost_tracker=tracker, max_workers=1
        )

        ops = [c.kwargs["operation"] for c in tracker.estimate.call_args_list]
        assert all("my-reference-video.mp4" in o for o in ops)
        # Should be basename only — no directory components
        assert not any(str(tmp_path) in o for o in ops)

    def test_cost_tracker_tool_is_provider_name(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(2)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        tracker = MagicMock()
        tracker.estimate = MagicMock(return_value="eid")

        chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"),
            StubProvider(),
            cost_tracker=tracker,
            max_workers=1,
        )

        tools = [c.kwargs["tool"] for c in tracker.estimate.call_args_list]
        assert all(t == "stub_video_analyzer" for t in tools)


# ---------------------------------------------------------------------------
# Task 2 — Error modes
# ---------------------------------------------------------------------------


class TestErrorModes:
    def test_fail_fast_default_first_exc_raises(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(3)
        cleanup_spy = MagicMock()
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", cleanup_spy)

        provider = StubProvider(fail_on_index={0}, fail_modes={0: "raise"})
        with pytest.raises(RuntimeError, match="stub failure"):
            chunked_analyzer.analyze_chunked(
                str(tmp_path / "ref.mp4"), provider, max_workers=1
            )

        cleanup_spy.assert_called_once()

    def test_continue_mode_merges_survivors(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(3)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        provider = StubProvider(fail_on_index={1}, fail_modes={1: "raise"})
        merged = chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"),
            provider,
            on_chunk_error="continue",
            max_workers=1,
        )

        assert merged["chunking_metadata"]["failed_chunks"] == [1]
        # 2 chunks made it to merge
        assert merged["chunking_metadata"]["chunk_count"] == 2

    def test_continue_mode_all_failed_raises(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(3)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        provider = StubProvider(
            fail_on_index={0, 1, 2}, fail_modes={0: "raise", 1: "raise", 2: "raise"}
        )
        with pytest.raises(RuntimeError, match="All chunks failed"):
            chunked_analyzer.analyze_chunked(
                str(tmp_path / "ref.mp4"),
                provider,
                on_chunk_error="continue",
                max_workers=1,
            )

    def test_video_chunking_error_propagates(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        def bad_split(vp):
            raise VideoChunkingError("ffprobe crashed")

        cleanup_spy = MagicMock()
        monkeypatch.setattr(chunked_analyzer, "split_video", bad_split)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", cleanup_spy)

        provider = StubProvider()
        with pytest.raises(VideoChunkingError, match="ffprobe crashed"):
            chunked_analyzer.analyze_chunked(
                str(tmp_path / "ref.mp4"), provider, max_workers=1
            )

        # Provider never called (split_video raised before analyze started)
        assert provider._call_count == 0
        # cleanup_chunks should NOT be called — split_video owns its own cleanup
        cleanup_spy.assert_not_called()


# ---------------------------------------------------------------------------
# Task 2 — Per-chunk artifact stamping
# ---------------------------------------------------------------------------


class TestArtifactStamping:
    def test_cost_and_provider_stamped_on_artifact(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        chunks = _make_chunks(2)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        captured_pairs: list[tuple] = []

        def fake_merge(pairs, provider):
            captured_pairs.extend(pairs)
            art = copy.deepcopy(minimal_video_analysis())
            art["chunking_metadata"] = {
                "chunk_count": len(pairs),
                "total_duration_s": 0.0,
                "provider": provider,
                "per_chunk": [],
            }
            return art

        monkeypatch.setattr(chunked_analyzer, "merge_analyses", fake_merge)

        provider = StubProvider(cost=0.077, model="stub-model-xyz")
        chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"), provider, max_workers=1
        )

        assert len(captured_pairs) == 2
        for chunk, art in captured_pairs:
            assert art["_cost_usd"] == pytest.approx(0.077)
            assert art["_provider_used"] == "stub-model-xyz"

    def test_provider_used_falls_back_to_provider_name_when_model_none(
        self, monkeypatch, tmp_path
    ):
        from lib import chunked_analyzer

        chunks = _make_chunks(1)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        captured = {}

        def fake_merge(pairs, provider):
            captured["pairs"] = pairs
            art = copy.deepcopy(minimal_video_analysis())
            art["chunking_metadata"] = {
                "chunk_count": 1,
                "total_duration_s": 0.0,
                "provider": provider,
                "per_chunk": [],
            }
            return art

        monkeypatch.setattr(chunked_analyzer, "merge_analyses", fake_merge)

        provider = StubProvider(cost=0.01, model=None)
        chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"), provider, max_workers=1
        )

        _, art = captured["pairs"][0]
        assert art["_provider_used"] == "gemini"  # provider.provider attr


# ---------------------------------------------------------------------------
# Task 2 — Single-chunk bypass end-to-end
# ---------------------------------------------------------------------------


class TestSingleChunkBypass:
    def test_single_chunk_bypass_e2e(self, monkeypatch, tmp_path):
        from lib import chunked_analyzer

        orig = str(tmp_path / "short.mp4")
        bypass = Chunk(start_global=0.0, end_global=120.0, local_path=orig)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: [bypass])
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        merged = chunked_analyzer.analyze_chunked(orig, StubProvider())

        # Passes through merger's single-chunk path
        assert merged["chunking_metadata"]["chunk_count"] == 1
        # Underscore-prefixed keys must be stripped by merger
        assert "_cost_usd" not in merged
        assert "_provider_used" not in merged


# ---------------------------------------------------------------------------
# CLEAN-05 — provider validation (v2.0 Phase 4 MR-01)
# ---------------------------------------------------------------------------


class _BadProvider(StubProvider):
    """StubProvider with an invalid schema-enum provider string."""

    provider = "anthropic"  # NOT in {"gemini","openrouter"}


class _NoneProvider(StubProvider):
    """StubProvider whose .provider attribute is None."""

    provider = None


class _OpenRouterProvider(StubProvider):
    """StubProvider with the other valid schema-enum provider."""

    provider = "openrouter"


class TestProviderValidation:
    def test_invalid_provider_name_raises_before_split(self, monkeypatch, tmp_path):
        """CLEAN-05: provider='anthropic' must raise ValueError before
        split_video runs — prevents wasting a full pipeline on a bad config.
        """
        from lib import chunked_analyzer

        split_spy = MagicMock()
        monkeypatch.setattr(chunked_analyzer, "split_video", split_spy)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        provider = _BadProvider()
        with pytest.raises(ValueError, match=r"anthropic.*gemini.*openrouter"):
            chunked_analyzer.analyze_chunked(
                str(tmp_path / "ref.mp4"), provider, max_workers=1
            )
        split_spy.assert_not_called()
        assert provider._call_count == 0

    def test_none_provider_raises_before_split(self, monkeypatch, tmp_path):
        """CLEAN-05: provider=None (attribute missing / None) must raise
        ValueError, not silently default to 'unknown'."""
        from lib import chunked_analyzer

        split_spy = MagicMock()
        monkeypatch.setattr(chunked_analyzer, "split_video", split_spy)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        provider = _NoneProvider()
        with pytest.raises(ValueError, match=r"None.*gemini.*openrouter"):
            chunked_analyzer.analyze_chunked(
                str(tmp_path / "ref.mp4"), provider, max_workers=1
            )
        split_spy.assert_not_called()

    def test_invalid_provider_does_not_touch_cost_tracker(self, monkeypatch, tmp_path):
        """CLEAN-05 corollary: validation happens BEFORE cost_tracker.estimate
        so budget reports don't show phantom reservations for rejected calls."""
        from lib import chunked_analyzer

        monkeypatch.setattr(chunked_analyzer, "split_video", MagicMock())
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        cost_tracker = MagicMock()
        provider = _BadProvider()
        with pytest.raises(ValueError):
            chunked_analyzer.analyze_chunked(
                str(tmp_path / "ref.mp4"),
                provider,
                cost_tracker=cost_tracker,
                max_workers=1,
            )
        cost_tracker.estimate.assert_not_called()
        cost_tracker.reserve.assert_not_called()

    def test_openrouter_provider_accepted(self, monkeypatch, tmp_path):
        """CLEAN-05 negative-space check: the OTHER valid enum value
        ('openrouter') is accepted — proves we didn't over-narrow the set."""
        from lib import chunked_analyzer

        chunks = _make_chunks(2)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        provider = _OpenRouterProvider()
        merged = chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"), provider, max_workers=1
        )
        assert merged["chunking_metadata"]["provider"] == "openrouter"


# ---------------------------------------------------------------------------
# CLEAN-07 — continue mode + positional hook/CTA (v2.0 Phase 4 MR-03)
# ---------------------------------------------------------------------------


class TestContinueModePositionalHookCta:
    """MR-03: when on_chunk_error='continue' drops edge chunks, hook/cta
    must come from the ORIGINAL first/last successful chunk by submission
    index — NOT from the survivor list's first/last."""

    def _chunks_with_distinct_hook_cta(self):
        """Build a fresh artifact factory that stamps chunk-specific hook/cta
        values so we can assert which chunk's value ended up in the merge."""

        def factory_for_index(idx: int):
            def _factory():
                art = copy.deepcopy(minimal_video_analysis())
                # Hook type enums: question | bold_claim | visual_shock | stat_drop | story_open | problem_statement | none
                hooks = ["question", "bold_claim", "visual_shock"]
                # CTA type enums: subscribe | visit_link | purchase | follow | download | none_detected
                ctas = ["subscribe", "visit_link", "purchase"]
                art["narrative"]["hook_type"] = hooks[idx]
                art["narrative"]["cta_type"] = ctas[idx]
                return art
            return _factory

        return factory_for_index

    def test_fail_chunk_0_hook_from_chunk_1(self, monkeypatch, tmp_path):
        """Chunk 0 fails -> hook_type in merged output comes from chunk 1."""
        from lib import chunked_analyzer

        chunks = _make_chunks(3)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        factory_for = self._chunks_with_distinct_hook_cta()

        class PerIndexStub(StubProvider):
            def __init__(self):
                super().__init__(fail_on_index={0}, fail_modes={0: "raise"})

            def execute(self, inputs):
                idx = self._call_count
                # Let the parent handle failure FIRST so _call_count increments
                result = super().execute(inputs)
                if result.success:
                    # Override with per-index artifact
                    result.data = factory_for(idx)()
                return result

        provider = PerIndexStub()
        merged = chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"),
            provider,
            on_chunk_error="continue",
            max_workers=1,
        )
        assert merged["chunking_metadata"]["failed_chunks"] == [0]
        # Hook now comes from chunk 1 (not the survivor-list first, which
        # in current v2.0 code would also be chunk 1 — but the test ANCHORS
        # that contract). Chunk 1's hook_type = "bold_claim".
        assert merged["narrative"]["hook_type"] == "bold_claim"
        # CTA from chunk 2 (last survivor = highest-index survivor).
        assert merged["narrative"]["cta_type"] == "purchase"

    def test_fail_last_chunk_cta_from_second_to_last(self, monkeypatch, tmp_path):
        """Chunk N-1 fails -> cta_type in merged output comes from chunk N-2."""
        from lib import chunked_analyzer

        chunks = _make_chunks(3)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        factory_for = self._chunks_with_distinct_hook_cta()

        class PerIndexStub(StubProvider):
            def __init__(self):
                super().__init__(fail_on_index={2}, fail_modes={2: "raise"})

            def execute(self, inputs):
                idx = self._call_count
                result = super().execute(inputs)
                if result.success:
                    result.data = factory_for(idx)()
                return result

        provider = PerIndexStub()
        merged = chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"),
            provider,
            on_chunk_error="continue",
            max_workers=1,
        )
        assert merged["chunking_metadata"]["failed_chunks"] == [2]
        # Hook from chunk 0 (unchanged — chunk 0 survived)
        assert merged["narrative"]["hook_type"] == "question"
        # CTA from chunk 1 (highest-index survivor)
        assert merged["narrative"]["cta_type"] == "visit_link"

    def test_fail_both_edges_hook_from_1_cta_from_nminus2(self, monkeypatch, tmp_path):
        """Chunks 0 AND N-1 fail -> hook from chunk 1, cta from chunk N-2."""
        from lib import chunked_analyzer

        chunks = _make_chunks(4)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        def factory_for_idx(idx: int):
            def _factory():
                art = copy.deepcopy(minimal_video_analysis())
                hooks = ["question", "bold_claim", "visual_shock", "stat_drop"]
                ctas = ["subscribe", "visit_link", "purchase", "follow"]
                art["narrative"]["hook_type"] = hooks[idx]
                art["narrative"]["cta_type"] = ctas[idx]
                return art
            return _factory

        class PerIndexStub(StubProvider):
            def __init__(self):
                super().__init__(
                    fail_on_index={0, 3}, fail_modes={0: "raise", 3: "raise"}
                )

            def execute(self, inputs):
                idx = self._call_count
                result = super().execute(inputs)
                if result.success:
                    result.data = factory_for_idx(idx)()
                return result

        provider = PerIndexStub()
        merged = chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"),
            provider,
            on_chunk_error="continue",
            max_workers=1,
        )
        assert sorted(merged["chunking_metadata"]["failed_chunks"]) == [0, 3]
        assert merged["narrative"]["hook_type"] == "bold_claim"   # chunk 1
        assert merged["narrative"]["cta_type"] == "purchase"      # chunk 2

    def test_continue_mode_merged_artifact_schema_valid(
        self, monkeypatch, tmp_path
    ):
        """Regression guard: after the continue-mode path runs, the merged
        artifact MUST still validate against the video_analysis schema."""
        from lib import chunked_analyzer
        from schemas.artifacts import validate_artifact

        chunks = _make_chunks(3)
        monkeypatch.setattr(chunked_analyzer, "split_video", lambda vp: chunks)
        monkeypatch.setattr(chunked_analyzer, "cleanup_chunks", MagicMock())

        provider = StubProvider(
            fail_on_index={0}, fail_modes={0: "raise"}
        )
        merged = chunked_analyzer.analyze_chunked(
            str(tmp_path / "ref.mp4"),
            provider,
            on_chunk_error="continue",
            max_workers=1,
        )
        validate_artifact("video_analysis", merged)  # raises on invalid
