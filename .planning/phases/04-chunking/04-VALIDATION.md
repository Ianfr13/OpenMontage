---
phase: 4
slug: chunking
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-17
approved: 2026-04-17
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. All behaviours covered by automated tests; Wave 0 creates the test files inline within each plan (no separate Wave 0 plan).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | none — discoverable via default `tests/` layout; shared fixtures in `tests/unit/conftest.py` |
| **Quick run command** | `python -m pytest tests/unit/test_video_chunker.py tests/unit/test_analysis_merger.py tests/unit/test_chunked_analyzer.py -x -q` |
| **Full suite command** | `python -m pytest tests/unit/ tests/contracts/ -x -q` |
| **Estimated runtime** | ~4 seconds (subprocess + ThreadPoolExecutor + provider all mocked) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command for the relevant test file(s).
- **After every plan wave:** Run the full unit + contract suite (still mocks subprocess + provider).
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 4 seconds.
- **Integration tests (`RUN_INTEGRATION_TESTS=1`) are Phase 7 scope, NOT Phase 4 gate** — Phase 4 ships API-key-free tests only.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 1 | CHUNK-01, CHUNK-02 | T-04-01, T-04-02, T-04-03 | shell=False, timeout=30, stderr captured in error | unit | `python -m pytest tests/unit/test_video_chunker.py -x -q` | ❌ W0 (created by task) | ⬜ pending |
| 4-01-02 | 01 | 1 | CHUNK-01 | T-04-01, T-04-04, T-04-05 | ffmpeg list-args only, bypass sentinel in cleanup, tempdir cleanup on split failure | unit | `python -m pytest tests/unit/test_video_chunker.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-01 | 02 | 2 | CHUNK-04, CHUNK-05 | — | weighted math primitives bounded; single-chunk pass-through schema-valid | unit | `python -m pytest tests/unit/test_analysis_merger.py -x -q` | ❌ W0 | ⬜ pending |
| 4-02-02 | 02 | 2 | CHUNK-04, CHUNK-05 | T-04-07, T-04-08, T-04-09, T-04-10, T-04-11 | worst-case confidence, color cap at 5, time shift exhaustive, schema gate at merge-end | unit | `python -m pytest tests/unit/test_analysis_merger.py -x -q` | ❌ W0 | ⬜ pending |
| 4-03-01 | 03 | 3 | CHUNK-03, CHUNK-06 | T-04-12, T-04-13, T-04-15, T-04-17 | worker clamp [1,8], try/finally cleanup, callback exceptions swallowed, basename-only in ops string | unit | `python -m pytest tests/unit/test_chunked_analyzer.py -x -q` | ❌ W0 | ⬜ pending |
| 4-03-02 | 03 | 3 | CHUNK-03, CHUNK-06 | T-04-13, T-04-14, T-04-16 | cleanup on all exception paths, cost_tracker per-chunk trace, provider name stamped | unit + contract | `python -m pytest tests/unit/test_chunked_analyzer.py tests/contracts/test_phase4_chunked_path.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All test files are created inline by the plans that implement the code they cover (co-located TDD). No separate Wave 0 plan needed.

- [ ] `tests/unit/test_video_chunker.py` — created by Plan 01 Task 1 (scaffold) + extended by Plan 01 Task 2. Covers CHUNK-01, CHUNK-02.
- [ ] `tests/unit/test_analysis_merger.py` — created by Plan 02 Task 1 (primitives + single-chunk) + extended by Plan 02 Task 2 (all field rules). Covers CHUNK-04, CHUNK-05.
- [ ] `tests/unit/test_chunked_analyzer.py` — created by Plan 03 Task 1 (dispatch + cost heuristic) + extended by Plan 03 Task 2 (cost_tracker integration + error modes). Covers CHUNK-03, CHUNK-06.
- [ ] `tests/contracts/test_phase4_chunked_path.py` — created by Plan 03 Task 2. End-to-end contract test with StubProvider + mocked split_video.
- [ ] `tests/unit/conftest.py` — Plan 02 Task 1 adds `fake_video_chunks` fixture for building N distinct per-chunk artifacts.
- [ ] No new framework install (pytest 9.0.3 present).
- [ ] No new dependency add.

---

## Manual-Only Verifications

*None — all phase behaviours have automated verification. Real-FFmpeg and real-provider integration checks live in Phase 7 (`RUN_INTEGRATION_TESTS=1`).*

---

## Cost Heuristic Staleness

The pricing table in `lib/chunked_analyzer.py` is stamped with `verified: "2026-04-17"`. RESEARCH § Metadata declares these rates valid until 2026-05-17. Phase 7 integration tests should re-reconcile via real `response.usage.cost` from OpenRouter; the heuristic is an estimate gate, not a source of truth.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 (test files) are scoped into the implementing plans; no separate plan needed
- [x] No watch-mode flags used
- [x] Feedback latency < 4s (subprocess + ThreadPoolExecutor mocked)
- [x] `nyquist_compliant: true`

**Approval:** approved 2026-04-17
