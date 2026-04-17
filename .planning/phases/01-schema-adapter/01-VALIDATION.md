---
phase: 1
slug: schema-adapter
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-17
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml (or pytest.ini) — confirm during Wave 0 |
| **Quick run command** | `pytest tests/contracts/ -x -q` |
| **Full suite command** | `pytest tests/contracts/ tests/unit/ -q` |
| **Estimated runtime** | ~5 seconds (no API keys, no network) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/contracts/ -x -q`
- **After every plan wave:** Run `pytest tests/contracts/ tests/unit/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | ANLZ-02 | — | N/A (no PII, local schema) | contract | `pytest tests/contracts/test_video_analysis_schema.py -x` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | ANLZ-03 | — | N/A | contract | `pytest tests/contracts/test_video_analysis_schema.py::test_fixture_validates -x` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | SYNTH-09 | — | N/A | contract | `pytest tests/contracts/test_pipeline_synthesis_schema.py -x` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 2 | INT-04 | — | N/A | unit | `pytest tests/unit/test_schema_adapter.py -x` | ❌ W0 | ⬜ pending |
| 1-04-01 | 04 | 3 | INT-04 | — | N/A | integration | `pytest tests/contracts/test_checkpoint_registration.py -x` | ❌ W0 | ⬜ pending |
| 1-04-02 | 04 | 3 | ANLZ-02 | — | N/A (regression) | regression | `pytest tests/contracts/test_brief_schema_regression.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/contracts/test_video_analysis_schema.py` — stubs for ANLZ-02, ANLZ-03
- [ ] `tests/contracts/test_pipeline_synthesis_schema.py` — stubs for SYNTH-09
- [ ] `tests/unit/test_schema_adapter.py` — stubs for INT-04
- [ ] `tests/contracts/test_checkpoint_registration.py` — stubs for INT-04
- [ ] `tests/contracts/test_brief_schema_regression.py` — regression stub for ANLZ-02 (v1.0 brief schema still loads)
- [ ] Inline Python dict fixtures inside each contract-test module (no `tests/fixtures/` directory is created — see RESEARCH.md Finding 5)
- [ ] Confirm pytest is the project test runner; if missing, add to `requirements.txt` / `pyproject.toml`

*Framework install: pytest + jsonschema (4.26.0 already pinned per research); no new deps.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| (none) | — | All Phase 1 behaviors are deterministic schema + adapter work | All automated |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
