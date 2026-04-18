# Phase 8: OpenRouter Provider Hardening - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning
**Mode:** Auto-generated (cleanup phase — specs are literal review findings with file:line references)

<domain>
## Phase Boundary

Harden `tools/analysis/openrouter_video_analyzer.py` against four v2.0 code-review findings: auth/rate errors must fail fast, payload base64 cap must match the chunking contract, MIME detection must be an explicit whitelist, and `OPENROUTER_BASE_URL` must be the single source of truth.

Out of boundary: anything in `gemini_video_analyzer.py` (Phase 9), merger logic (Phase 9), synthesizer (Phase 10), unrelated nits (Phase 11).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion (per REQUIREMENTS.md spec)

The four requirements for this phase (CLEAN-01, CLEAN-02, CLEAN-03, CLEAN-04) already carry exact file paths, line numbers, and fix specifications derived from the Phase 3 REVIEW.md findings. No grey areas worth pausing for — REQUIREMENTS.md is the spec.

Narrow defaults Claude will pick unless research surfaces a constraint:

- **CLEAN-01 (auth/rate surfacing):** narrow the `except APIError` in `_run_once` to a sentinel-bypass pattern. Prefer a dedicated `VideoAnalysisAuthError` / `VideoAnalysisRateLimitError` subclass over `VideoAnalysisError` so `_analyze_with_fallback` can pattern-match and re-raise without compact-retry. Bypass applies to `AuthenticationError` (401), `PermissionDeniedError` (403), `RateLimitError` (429).
- **CLEAN-02 (100MB cap):** set `HARD_MAX_UPLOAD_BYTES = 100 * 1024 * 1024` with a clear `ValueError`/`VideoAnalysisError` telling the caller to use chunking for larger inputs. Keep the constant name; change value only.
- **CLEAN-03 (MIME whitelist):** explicit dict `_EXT_TO_MIME = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".mkv": "video/x-matroska", ".m4v": "video/mp4"}`. Return `None` for unknown — callers already handle `None` as a rejection path.
- **CLEAN-04 (base URL dedup):** replace the hardcoded literal at the call site with the `OPENROUTER_BASE_URL` constant. Update the test that asserts both to assert only the constant + that the client was constructed with it.

### Backward compat

Non-negotiable: `pytest tests/ -q` must stay green (≥588 passing) after each commit. Where a test currently pins the old behavior (e.g. 2GB cap, dual literal), update the test to match the new contract; do NOT loosen coverage.

</decisions>

<code_context>
## Existing Code Insights

### Relevant files
- `tools/analysis/openrouter_video_analyzer.py` — the subject of all four fixes
- `tests/contracts/test_openrouter_analyzer_*.py` (or equivalent) — must be updated for new contracts
- `lib/env_loader.py` — already resolves `OPENROUTER_API_KEY`; no changes expected
- `tools/analysis/video_analyzer_selector.py` — downstream consumer; interface contract for `analyze(file_path, ...)` must not change

### Patterns already in the repo
- Sentinel exception subclasses of `VideoAnalysisError` — this project already uses this pattern (see `lib/checkpoint.py::CheckpointValidationError`). The plan should mirror it.
- Constants block at the top of the analyzer module — the `HARD_MAX_UPLOAD_BYTES` constant exists; only its value and the error message need updating.
- Tests live under `tests/contracts/` (contract-level) and `tests/integration/` (real API, gated by env). Contract tests are mocked and always run.

### Anchor reviews
- v2.0 findings for this file: `.planning/milestones/v2.0-phases/03-openrouter-provider/03-REVIEW.md` — HI-01, MD-01, MD-02, MD-03.

</code_context>

<specifics>
## Specific Ideas

- User's explicit goal for this milestone: narrow atomic fixes, no refactors beyond what findings require, no feature work.
- User's memory note (feedback_validate_api_patterns): validate API patterns BEFORE coding — verify OpenAI SDK exception class hierarchy is what the fix assumes (`openai.AuthenticationError`, `openai.PermissionDeniedError`, `openai.RateLimitError`) before narrowing the except block.

</specifics>

<deferred>
## Deferred Ideas

- Anything about Gemini provider parity on these hardening items — deferred to a potential v2.2 if symmetry becomes important. Phase 8 scope is strictly OpenRouter.
- LOW/NIT items in `03-REVIEW.md` — those absorb into Phase 11 (NITS-01), not Phase 8.

</deferred>
