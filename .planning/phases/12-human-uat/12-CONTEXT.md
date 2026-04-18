# Phase 12: Human UAT - Context

**Gathered:** 2026-04-18
**Status:** Blocked on external resources (manual gate by design)
**Mode:** Auto-generated (manual UAT phase)

<domain>
## Phase Boundary

Close the two by-design manual quality gates from v2.0 for real-video SKILL-03 review:
- **UAT-01** — Gemini provider: one real `<2 min` video through `video_analyzer_selector` with `GEMINI_API_KEY` set; verify ≥12 of 16 canonical fields, enum sensibility, 4-dimension coverage.
- **UAT-02** — OpenRouter provider: same check with `OPENROUTER_API_KEY` set.

This phase has NO code work. The entire deliverable is two dated verdict reports proving a human ran the analyzer on a real fixture and recorded the outcome.

</domain>

<decisions>
## Implementation Decisions

### This phase is gated on user-supplied resources

Phase 12 cannot complete autonomously. It requires:
- A user-provided fixture video (local mp4, <2 min)
- `GEMINI_API_KEY` set in the environment
- `OPENROUTER_API_KEY` set in the environment

If those resources are not available at milestone-audit time, Phase 12's status is `human_needed` (not `gaps_found`). The milestone audit should account for this — UAT deferral is NOT a milestone-blocking gap, it's a known-and-tracked manual gate.

### Authoritative instructions are in v2.0 archive

The exact UAT procedures for Gemini and OpenRouter are already written in:
- `.planning/milestones/v2.0-phases/02-gemini-provider/02-HUMAN-UAT.md`
- `.planning/milestones/v2.0-phases/03-openrouter-provider/03-HUMAN-UAT.md`

Phase 12's tracking files mirror these with `status: partial` and updated timestamps. When the user runs the UAT, they update the `result:` field from `[pending]` to a verdict (pass / issues-found / blocked).

### Deferred-by-design is the expected outcome for autonomous mode

If the user runs `/gsd-autonomous` without fixtures+keys, Phase 12's verifier will report `human_needed` and the orchestrator should offer "Validate now" vs "Continue without validation". Choosing "continue" moves the milestone to audit, and the audit's `tech_debt` output will note UAT-01 and UAT-02 as still-pending manual gates.

</decisions>

<code_context>
## Existing Code Insights

- No source code changes in this phase.
- The v2.0 HUMAN-UAT.md template format (`status:`, `## Tests`, `## Summary`, `## Gaps`) is reused verbatim; copy with updated phase reference and timestamps.

</code_context>

<specifics>
## Specific Ideas

- The verifier creates 12-VERIFICATION.md with `status: human_needed` automatically — Phase 12 does not need a bespoke "verifier" agent run beyond that.
- If the user executes UAT now and reports issues, those become gap-closure items (e.g., real-world prompt tuning discovery, or a model-default misalignment). Those should be opened as a follow-up v2.2 phase, not force-fit into v2.1.

</specifics>

<deferred>
## Deferred Ideas

- Automating SKILL-03 real-video review with a canned test fixture — blocked on: no license-clear <2 min fixture in the repo, and two paid API providers. Deferred to `INFRA-07` (new, not yet tracked) for a separate milestone.

</deferred>
