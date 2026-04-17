# Phase 7 — Deferred Items

Out-of-scope discoveries during execution. Not fixed by current plans.

## Task-unrelated pre-existing environment gap (discovered Plan 07-01)

### 1. `tests/contracts/test_phase2_contracts.py::TestCodeSnippetUnit` requires `fc-list`

- **Failure:** `FileNotFoundError: [Errno 2] No such file or directory: 'fc-list'`
- **Affected tests (3):**
  - `test_render_python`
  - `test_render_with_title`
  - `test_render_different_themes`
- **Root cause:** These tests shell out (directly or via Pillow font discovery) to `fc-list` (fontconfig CLI). The container used for this execution does not have `fontconfig` installed.
- **Pre-existing?** Yes. Reproduces without `env -i`, i.e., not caused by the TEST-01/TEST-03 work.
- **Not in scope for 07-01:** Plan 07-01 adds a backward-compat gate + declares TEST-01 acceptance; it does not modify `test_phase2_contracts.py` or `lib/code_snippet` (or equivalent). Fixing the environment gap is infrastructure work.
- **Resolution options (when triaged):**
  - `apt-get install -y fontconfig` in dev container / CI image (preferred — tests already require a real font renderer).
  - Mark these tests `@pytest.mark.skipif(shutil.which("fc-list") is None, ...)` to let them skip in minimal environments (weakens the contract).
- **Impact on v2.0 milestone:** Not blocking. Phase 7 TEST-01 acceptance is about the API-key-free *logic* (no network, no secrets). The `fc-list` gap is a container-image shortcoming; the 576 tests that *do not* depend on native binaries all pass.
- **Evidence:** `env -i HOME=$HOME PATH=$PATH python3 -m pytest tests/contracts/ tests/unit/ -q` → `3 failed, 576 passed, 6 skipped in 17.95s`.
