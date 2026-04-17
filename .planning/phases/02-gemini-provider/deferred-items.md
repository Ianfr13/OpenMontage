# Deferred Items — Phase 02 Gemini Provider

Out-of-scope issues discovered during plan execution. Per GSD scope boundary
rules, these are logged here rather than fixed inline because they are not
caused by Phase 2 changes.

## Pre-existing test failures in `tests/contracts/test_phase2_contracts.py`

**Discovered during:** plan 02-04 execution (regression check step)

**Failures (3):**
- `TestCodeSnippetUnit::test_render_python`
- `TestCodeSnippetUnit::test_render_with_title`
- `TestCodeSnippetUnit::test_render_different_themes`

**Root cause:** `fc-list` (fontconfig) not installed in the dev container; the
`code_snippet` tool's Pygments/Pillow renderer requires it. Confirmed
pre-existing by running the same tests on a stashed tree (before any 02-04
changes) — 3 identical failures.

**Disposition:** Out-of-scope for Phase 2 Gemini provider work. Owner:
whoever owns the Enhancement Layer (legacy Phase 2 in the pre-GSD naming
scheme). Fix is either `apt-get install fontconfig` in the devcontainer OR
a `pytest.mark.skipif(shutil.which('fc-list') is None, ...)` guard on the
three tests.

---

## Naming collision: `tests/contracts/test_phase2_contracts.py`

**Discovered during:** plan 02-04 execution (file creation step)

**Issue:** Plan 02-04 specified creating `tests/contracts/test_phase2_contracts.py`,
but that path already contains unrelated legacy Enhancement-Layer contract tests
(FaceEnhance, SceneDetect, ColorGrade, AudioEnhance, ImageSelector, CodeSnippet,
DiagramGen) from the pre-GSD project structure.

**Resolution (Rule 3 deviation — blocking issue):** Created
`tests/contracts/test_phase2_gemini_contracts.py` instead. The `_gemini_`
suffix disambiguates this phase's contract file from the legacy test module
without deleting ~100 pre-existing tests. Documented in SUMMARY.md Deviations
section.

**Disposition:** Not fixing. The legacy file can be migrated/renamed in a
future cleanup plan; until then the two files coexist. All Phase 2 acceptance
criteria requiring "a contract test file exists at X" are satisfied by the
renamed file.
