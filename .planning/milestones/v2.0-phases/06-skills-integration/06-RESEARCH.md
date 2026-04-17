# Phase 6: Research

**Date:** 2026-04-17
**Confidence:** HIGH (docs work, all code already shipped in Phases 2-5)

## Scope

Phase 6 is documentation + integration. No new libraries, no new SDK surface. All code already shipped. The "research" here is confirming the existing shape of docs and meta skills before editing.

## Existing Artifacts (verified)

### Meta skills directory
- `skills/meta/video-reference-analyst.md` — exists (needs refactor to consume structured artifact)
- `skills/meta/onboarding.md`, `reviewer.md`, `checkpoint-protocol.md`, `creative-intake.md` — templates/patterns to mirror

### Documentation files
- `/workspace/AGENT_GUIDE.md` — Reference Video Entry Point section at lines 17-48 (edit target)
- `/workspace/CONTEXT.md` — exists at repo root (tools table to extend)
- `/workspace/requirements.txt` — already contains all 3 new deps (google-genai, openai, ruamel.yaml) from Phases 2/3/5; Phase 6 audit only

### Libraries (Phase 2-5 shipped)
- `lib/analysis_errors.py`, `lib/schema_adapter.py`, `lib/video_chunker.py`, `lib/analysis_merger.py`, `lib/chunked_analyzer.py`, `lib/pipeline_synthesizer.py`, `lib/llm_fill.py`
- All use module-level functions (pure lib pattern)

### Tools (Phase 2-3 shipped)
- `tools/analysis/video_analyzer_selector.py`
- `tools/analysis/gemini_video_analyzer.py`
- `tools/analysis/openrouter_video_analyzer.py`
- Each has Layer 3 skill in `.agents/skills/gemini-video-analysis/`, `.agents/skills/openrouter-video-analysis/`

### Env Loader
- Check `lib/env_loader.py` — if doesn't exist, create minimal module for INT-03; else add new env var docs inline

## Key Patterns from Existing Meta Skills

- Frontmatter: `name:` + `description:` YAML
- Sections: "When to invoke" / "Workflow overview" / "Step N" / "Checkpoints" / "Examples"
- `awaiting_human` checkpoints referenced via `checkpoint-protocol.md`
- Code examples with specific Python imports and call signatures

## Open Questions (resolved)

1. `lib/env_loader.py` exists? — Will verify in execution; if not, create minimal module (loads .env + documents env vars via module docstring).
2. CONTEXT.md structure — will read during planning/execution.
3. Meta skill trigger phrases — planner can draft; this is not performance-critical (user invokes skill explicitly or via the agent's routing).

## Validation Architecture

### Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest 7.x (docs validation uses pytest as lightweight assertion runner) |
| Quick run command | `pytest tests/contracts/test_phase6_docs.py -q` |
| Full suite command | N/A — Phase 6 is docs; full tests in Phase 7 |
| Estimated runtime | ~2 seconds (file existence + grep patterns) |

### Sampling Rate

- After task commit: existence checks for newly-written docs
- Full run before verify

### Per-Task Verification Map

| Task | Plan | Verification |
|------|------|-------------|
| 06-01 | 01 | `test -f skills/meta/reference-synthesis.md`; grep for `awaiting_human` ≥2 |
| 06-02 | 02 | `test -f skills/meta/video-reference-analyst.md`; grep for "Structured Path" section |
| 06-03 | 03 | `test -f CONTEXT.md`; grep for 3 tool names; `grep -c "video_analyzer_selector" CONTEXT.md ≥1` |

### Wave 0 Requirements

- None new — using existing pytest

### Manual-Only Verifications

None — all doc checks are automated via grep/existence.
