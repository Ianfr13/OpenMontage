# Phase 4 — Deferred Items

Pre-existing issues found while running the full contract suite during Plan 04-03 execution. None caused by Phase 4 work; logged here for future phases.

## Pre-existing test failures (not Phase 4 scope)

- `tests/contracts/test_phase2_contracts.py::TestCodeSnippetUnit::test_render_python`
- `tests/contracts/test_phase2_contracts.py::TestCodeSnippetUnit::test_render_with_title`
- `tests/contracts/test_phase2_contracts.py::TestCodeSnippetUnit::test_render_different_themes`

**Root cause:** `FileNotFoundError: 'fc-list'` — font-config CLI binary missing on sandbox. Code-snippet rendering test depends on `fc-list` to enumerate available fonts. Unrelated to Phase 4 (chunking / video_analysis); `test_phase2_contracts.py::TestCodeSnippetUnit` is the pipeline code-snippet render test, not the Phase 2 video-analysis contracts (which live in `test_phase2_gemini_contracts.py`).

**Resolution:** install `fontconfig` on the execution host OR mock `fc-list` at the test level. Deferred — does not block Phase 4 gate.

**Verified pre-existing:** reproduced on `main@a24f6d6` before any Phase 4 Plan 03 work (`git stash` + rerun).
