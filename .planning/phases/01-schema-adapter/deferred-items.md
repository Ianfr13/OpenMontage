# Deferred Items — Phase 01 (Schema + Adapter)

## Pre-existing failures (out of scope for 01-01)

### numpy missing in devcontainer

- **Found during:** Plan 01-01 verification step (`pytest tests/contracts/test_phase0_contracts.py -x -q`)
- **Failure:** `tests/contracts/test_phase0_contracts.py::TestToolRegistry::test_support_envelope` fails with `ModuleNotFoundError: No module named 'numpy'`
- **Root cause:** `tools/video/green_screen_composite.py:19` imports `numpy`; tool discovery in `test_support_envelope` walks `tools/` and triggers the import. `numpy` is not in `requirements.txt`.
- **Reproduces without 01-01 changes:** YES (verified via `git stash` + rerun — same failure).
- **Scope decision:** Pre-existing and orthogonal to Phase 1 schema work. Schema + Checkpoint tests (the scope Phase 1 cares about) are green: `pytest tests/contracts/test_phase0_contracts.py::TestSchemas tests/contracts/test_phase0_contracts.py::TestCheckpoint` → 11/11 passed.
- **Recommended follow-up:** Add `numpy` to `requirements.txt` OR guard the `green_screen_composite` import in a later phase (not schema-adapter territory).
