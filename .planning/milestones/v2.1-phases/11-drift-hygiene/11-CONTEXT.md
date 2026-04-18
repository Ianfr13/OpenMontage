# Phase 11: Drift & Hygiene - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning
**Mode:** Auto-generated (cleanup phase — specs are literal v2.0 deferred items + LOW/NIT catalogue)

<domain>
## Phase Boundary

Close the two remaining cleanup loose ends from v2.0:
1. **DRIFT-01** — `pipeline_defs/cinematic.yaml` references an unregistered `web_search` tool; the semantic validator flags this on every synthesizer run. Either register the tool in the registry (unlikely — no implementation exists) OR remove the reference from the YAML.
2. **NITS-01** — Absorb the 16 LOW + 14 NIT findings deferred from v2.0 Phase 3, 4, 5 reviews. Each fix ships as a narrow atomic commit (git-log grep must show individual fix commits, not one monolithic absorb).

Out of boundary: Providers (Phase 8, done), merger (Phase 9, done), synthesizer records (Phase 10, done), UAT (Phase 12).

</domain>

<decisions>
## Implementation Decisions

### DRIFT-01 — Remove, don't register

The `web_search` reference in `cinematic.yaml` was a placeholder from v1.0 that was never wired. No `web_search` tool exists in the registry and no sibling pipelines use it either. **Decision: remove the reference** (edit YAML), do not register a stub tool. The pipeline keeps working — the reference was advisory, not mechanical.

### NITS-01 — Absorb as narrow atomic commits

Rules for this batch:
- Each fix = one commit. Commit message prefix: `fix(11-nits): <LO|NI>-<phase>-<NN> <short description>`
- If a fix touches the same file as another, they still ship as separate commits unless the change is literally one-token (e.g., renaming a constant referenced in two places).
- 588 tests → current (~687) must stay green after each commit.
- Skip any NIT that would require behavior change or new feature — defer it explicitly.
- If a LOW turns out to already be resolved (e.g. Phase 8 happened to fix it in passing), mark it as "already resolved" in SUMMARY.md with the commit that fixed it.

### Finding catalogue

The full list lives in:
- `.planning/milestones/v2.0-phases/03-openrouter-provider/03-REVIEW.md` (Phase 3 LO + NIT)
- `.planning/milestones/v2.0-phases/04-chunking/04-REVIEW.md` (Phase 4 LO + NIT)
- `.planning/milestones/v2.0-phases/05-synthesizer/05-REVIEW.md` (Phase 5 LO + NIT)

Executor MUST read all three reviews and build a classified checklist before committing. Track progress inline — the SUMMARY.md must enumerate every LO/NI item with status: `fixed` (commit SHA), `already-resolved` (referenced commit), or `deferred` (reason).

### Deferred escape hatch

If a finding turns out to require a real refactor or would break contract, add it to REQUIREMENTS.md `Future Requirements` and explicitly defer. Don't force-fix something that wasn't what the finding claimed.

</decisions>

<code_context>
## Existing Code Insights

### Relevant files
- `pipeline_defs/cinematic.yaml` (DRIFT-01)
- Phase 3, 4, 5 REVIEW.md files (source of truth for NITS-01)
- Many files touched by individual LO/NIT items — not enumerable in advance; executor discovers via grep

### Anchor items (from review findings memory)
- Phase 3: dead constants, redundant env checks, prompt-embedded markdown fences, `_PRICING_VERIFIED_AT` redundancy
- Phase 4: unreachable returns, missing logging on silent failures
- Phase 5: misc code hygiene

### Patterns already in repo
- Phase 8-10 established atomic-commit-per-fix cadence (visible in recent git log)
- `lib/analysis_errors.py` has grown sentinel subclasses — stable pattern for error hygiene

</code_context>

<specifics>
## Specific Ideas

- Do NOT fall into "refactor the file while I'm here" mode. Narrow, atomic, per-finding.
- The 30 finding count is approximate — the catalogue in REVIEW.md files is the authoritative list. If it's 28 or 32, that's fine, just note the exact count in SUMMARY.md.
- Some NITs may have been transparently fixed by Phase 8-10 refactors — those should be marked `already-resolved` with a grep or git blame reference.

</specifics>

<deferred>
## Deferred Ideas

- SYNTH2-* and OBS-* remain in REQUIREMENTS.md Future Requirements. Do NOT pull them into Phase 11.
- Any finding that requires new tests or behavior changes — defer explicitly.

</deferred>
