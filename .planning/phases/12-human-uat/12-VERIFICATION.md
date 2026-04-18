---
status: human_needed
phase: 12-human-uat
score: 0/2 manual gates
verified: 2026-04-18
---

# Phase 12: Human UAT — Verification

**Status:** `human_needed` (by design — external resources required)

## Must-Haves

| ID | Must-have | Status |
|----|-----------|--------|
| UAT-01 | Dated Gemini UAT verdict report with fixture metadata + expected/observed diff | Pending (`12-UAT-01-gemini.md`) |
| UAT-02 | Dated OpenRouter UAT verdict report with fixture metadata + expected/observed diff | Pending (`12-UAT-02-openrouter.md`) |

## Why human_needed (not gaps_found)

This phase is a by-design manual quality gate, carried over from v2.0's deferred HUMAN-UAT items. It cannot complete autonomously because it requires:

- **Fixture:** a local `<2 min` video the user provides
- **Gemini key:** `GEMINI_API_KEY` set in environment
- **OpenRouter key:** `OPENROUTER_API_KEY` set in environment

The classification is `human_needed`, NOT `gaps_found` — an autonomous runner correctly reports this status rather than treating it as a failure.

## How to complete

1. Place a test video locally (anywhere readable).
2. Set both API keys in the environment.
3. Run the commands in `12-UAT-01-gemini.md` and `12-UAT-02-openrouter.md`, following the acceptance criteria.
4. Edit the `result:` field in each UAT file from `[pending]` to a verdict (`pass` / `issues-found: <detail>`).
5. Update `Summary` section with pass/issue counts.
6. Commit the updated UAT files.

## Autonomous runner behavior

When the autonomous orchestrator encounters this `human_needed` verification, it SHOULD offer the user:
- **"Validate now"** — run the UAT, record verdicts inline, mark phase passed
- **"Continue without validation"** — defer; the milestone audit will log UAT-01 and UAT-02 as pending tech debt (NOT gaps)

Choosing "continue" is the expected path if fixtures aren't staged.

## Next step

Run `/gsd-verify-work 12` later to complete the UAT when ready, OR accept the deferral at milestone audit and close v2.1 with UAT pending.
