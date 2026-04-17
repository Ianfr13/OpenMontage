# Deferred Items — Phase 01 (Schema + Adapter)

## Pre-existing failures (out of scope for 01-01)

### numpy missing in devcontainer

- **Found during:** Plan 01-01 verification step (`pytest tests/contracts/test_phase0_contracts.py -x -q`)
- **Failure:** `tests/contracts/test_phase0_contracts.py::TestToolRegistry::test_support_envelope` fails with `ModuleNotFoundError: No module named 'numpy'`
- **Root cause:** `tools/video/green_screen_composite.py:19` imports `numpy`; tool discovery in `test_support_envelope` walks `tools/` and triggers the import. `numpy` is not in `requirements.txt`.
- **Reproduces without 01-01 changes:** YES (verified via `git stash` + rerun — same failure).
- **Scope decision:** Pre-existing and orthogonal to Phase 1 schema work. Schema + Checkpoint tests (the scope Phase 1 cares about) are green: `pytest tests/contracts/test_phase0_contracts.py::TestSchemas tests/contracts/test_phase0_contracts.py::TestCheckpoint` → 11/11 passed.
- **Recommended follow-up:** Add `numpy` to `requirements.txt` OR guard the `green_screen_composite` import in a later phase (not schema-adapter territory).

### Devcontainer overlay filesystem full (/tmp unwritable)

- **Found during:** Plan 01-03 verification step (regression run of `tests/contracts/test_phase0_contracts.py`)
- **Failure:** Multiple `TestCheckpoint::*` and `TestToolRegistry::*` tests error with `OSError: [Errno 28] No space left on device: '/tmp/pytest-of-node'` / `'/tmp/pytest-of-unknown'`
- **Root cause:** Devcontainer overlay fs at 100% (`df -h /` = 56G/59G, 0 Avail). Heaviest consumers: `/home/node/.cache/ms-playwright` (615M). `pytest`'s `tmp_path_factory` cannot create its numbered-dir under `/tmp/pytest-of-*`.
- **Reproduces without 01-03 changes:** YES (verified via `git stash` + rerun of `test_write_read_roundtrip` → same failure).
- **Scope decision:** Pre-existing environmental issue (devcontainer disk exhaustion), completely orthogonal to Plan 01-03 (pure-function Python module + unit tests that don't touch `/tmp`). Plan 01-03's own tests and Plan 01-01/01-02 regression tests all pass: `pytest tests/unit/test_schema_adapter.py tests/contracts/test_video_analysis_schema.py tests/contracts/test_pipeline_synthesis_schema.py` → 45/45 passed.
- **Recommended follow-up:** Prune `/home/node/.cache/ms-playwright` (unused for this milestone), rebuild devcontainer with a larger overlay, or mount `/tmp` as tmpfs. Infrastructure concern, not Phase 1 territory.
