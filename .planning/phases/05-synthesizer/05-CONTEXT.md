# Phase 5: Synthesizer + Staging - Context

**Gathered:** 2026-04-17
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, tight cadence)

<domain>
## Phase Boundary

Turn a validated `video_analysis` artifact into a rule-matched, semantically-validated pipeline YAML that lands in `pipeline_defs/_staging/<slug>.yaml` and waits for human approval before touching `pipeline_defs/`. Pure lib module (NOT a BaseTool — mirrors `lib/playbook_generator.py`). Rule-based matching selects one of 12 existing pipelines using `pacing_style` + `shot_type_distribution` + `motion_type_distribution` with a `match_score` 0-1. Optional LLM fill-in ONLY for stage details inside the matched base pipeline template (never invents stage structure). Two modes: `template` (default, generalizable) and `replica` (closer reproduction). Idempotent slug generation (content hash). Semantic validation rejects before approval if any referenced skill path or tool is unknown. Accept/reject API moves or deletes staging file.

Out of scope: auto-execution (explicit per REQUIREMENTS "Out of Scope"); new Remotion scene types; streaming.

</domain>

<decisions>
## Implementation Decisions

### Plan Decomposition (3 plans)
- `05-01-PLAN.md` — `lib/pipeline_synthesizer.py` core: rule-based matching (pacing_style + shot_type + motion_type → base pipeline selection with match_score), slug generation (content hash), staging path writer using `ruamel.yaml` (YAML 1.2 + comment preservation). SYNTH-01, SYNTH-02, SYNTH-04, SYNTH-05, SYNTH-06.
- `05-02-PLAN.md` — Semantic validation layer: every `skill:` path exists on filesystem; every tool in `tools_available` is registered; `pipeline_loader.list_pipelines()` excludes `_staging/`. SYNTH-07, SYNTH-08. Also: pipeline_synthesis run record writer (using Phase 1's schema) with diff_against_base. SYNTH-09 is shipped (schema only); here we write records that validate against it.
- `05-03-PLAN.md` — Accept/reject API (`accept_synthesis(slug)` → move `_staging/` → `pipeline_defs/`; `reject_synthesis(slug)` → delete from `_staging/`) + contract tests for full flow. SYNTH-03 (LLM fill-in), SYNTH-10 (accept/reject API).

### Matching Algorithm (SYNTH-02)
Simple rule-based scorer per base pipeline (no LLM for base selection):
- `pacing_style` enum match → +0.40 (exact), +0.15 (adjacent — slow↔medium, medium↔fast, fast↔frenetic)
- `dominant shot_type_distribution.close_up > 0.5` → pipeline.expected.close_up_heavy = true → +0.25
- `motion_type_distribution.static > 0.5` → animated-explainer/screen-demo preferred → +0.20
- `section_structure` length matches target pipeline's stage count → +0.15
- Base pipelines annotated with an `expected_analysis` yaml block (Phase 5 adds this to each of the 12 existing pipelines — one-line addition per pipeline, non-breaking)
- `match_score` = sum of signal contributions (bounded [0, 1])
- Ties broken deterministically by alphabetical pipeline name
- Output: `{base_pipeline, match_score, alternatives: [(name, score), ...]}`

### Slug Generation (SYNTH-06)
- `slug = f"{base_pipeline_name}-{short_hash(source_analysis_checksum)[:8]}"`
- Uses `source_analysis_checksum` from the `video_analysis` artifact (SHA-256 of canonicalized JSON)
- Idempotent: same checksum → same slug
- Collision detection: before write, check `pipeline_defs/_staging/<slug>.yaml` existence — if exists and differs, append `-v2`, `-v3`, etc.

### Staging Path + YAML Writer (SYNTH-05)
- `ruamel.yaml` YAML(typ='rt') for round-trip (comment-preserving)
- Output path: `pipeline_defs/_staging/<slug>.yaml`
- Never writes directly to `pipeline_defs/` — that's the accept API's job
- YAML header comment: `# synthesized from video_analysis checksum: <hash> at 2026-04-17`
- Staging dir created if missing (`os.makedirs(exist_ok=True)`)

### Loader Exclusion (SYNTH-07)
- `lib/pipeline_loader.py::list_pipelines()` already exists — Phase 5 AUDITS it and ADDS `_staging/` exclusion if not already present
- Audit: read existing implementation; if glob already excludes `_staging/` (unlikely since that path is new), add the filter
- Test: create `_staging/test.yaml` + `real/prod.yaml` → loader returns only real; confirm via contract test

### Semantic Validation (SYNTH-08)
- `validate_synthesized_pipeline(yaml_dict) -> list[ValidationError]` returns issues
- For each stage: `skill` field → check `os.path.exists(f"skills/pipelines/{path}.md")`
- For each `tools_available`: check `tool_name in registry.get_all_tool_names()` (or similar registry query)
- Returns empty list on success; raises `SynthesisValidationError(issues)` on failure
- Called BEFORE approval checkpoint — rejection short-circuits the flow

### Modes (SYNTH-04)
- `template` (default): LLM fills stage `tools_available` hints, `review_focus` items, `success_criteria` — stays generalizable
- `replica`: LLM aims for closer reproduction — uses `reference_url_hash`, more specific prompts, tighter `human_approval_default`

### LLM Fill-In (SYNTH-03)
- Provider-agnostic via existing `video_analyzer_selector` OR a separate text-only selector — recommend NO (use same selector with `operation="llm_fill"` mode? No, selector is for video_analysis)
- **Decision**: add a minimal `lib/llm_fill.py` helper that uses `openai` SDK pointed at OpenRouter with `google/gemini-2.5-flash` (fast, cheap) for stage-detail fill-in. Bounded token budget (2k max). No video input — text-only.
- Do NOT invent stage structure; only fill within the base pipeline template
- LLM output validated: every stage still has required fields per manifest schema

### Accept / Reject API (SYNTH-10)
- `accept_synthesis(slug: str) -> Path` — uses `shutil.move` to promote `_staging/<slug>.yaml` → `pipeline_defs/<slug>.yaml`; returns final path
- `reject_synthesis(slug: str) -> None` — `os.unlink(staging_path)`
- Both write a pipeline_synthesis run record with `validation_status: "accepted"/"rejected"`
- NO auto-approval path anywhere — there MUST NOT be a function that combines synthesize + accept

### Pipeline `expected_analysis` Annotations (SYNTH-02 enabler)
- Each of 12 existing `pipeline_defs/*.yaml` gets a new optional top-level block:
  ```yaml
  expected_analysis:
    pacing_style: fast      # primary match anchor
    close_up_heavy: true    # boolean signals
    static_heavy: false
    expected_stage_count: 5
  ```
- Additive, non-breaking — omitting this block falls back to "no signal" (match_score = 0 for that pipeline)
- Plan 05-01 adds these annotations to all 12 pipelines

### Claude's Discretion
- Exact scoring weights — planner may tune based on research; defaults above are reasonable
- Whether to expose `match_score` to user on synthesis completion (recommended yes; in the synthesis record)
- Whether LLM fill-in is opt-out via env var `VIDEO_SYNTH_LLM_FILL=false` (recommended yes)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lib/pipeline_loader.py` — existing loader; Phase 5 audits + possibly extends
- `lib/playbook_generator.py` — existing lib pattern template (NOT a BaseTool)
- `schemas/pipelines/pipeline_manifest.schema.json` — manifest schema (synthesized YAML must validate)
- `schemas/artifacts/pipeline_synthesis.schema.json` — Phase 1's shipped run-record schema
- `tools/tool_registry.py::registry.get_all_tool_names()` or equivalent — for tools_available validation
- 12 existing `pipeline_defs/*.yaml` — each gets a one-line `expected_analysis` block
- `skills/pipelines/*/` — director skills; synthesizer references these paths in `skill:` fields

### Established Patterns
- Pure lib modules for orchestration logic (not BaseTool)
- YAML manipulation via `ruamel.yaml` (already in requirements per Phase 6 INT-02)
- Error classes per module (`SynthesisValidationError(Exception)` new)
- `json.dumps(canonical_artifact, sort_keys=True, separators=(',',':'))` for deterministic checksums

</code_context>

<specifics>
## Specific Ideas

- Stage the YAML with a header comment showing provenance: `# synthesized_from: <checksum>`, `# base_pipeline: <name>`, `# match_score: 0.85`, `# mode: template`
- `_staging/` directory is gitignored (or should be) — add `.gitignore` entry in Phase 5 via 05-01
- Accept/reject API is NOT exposed to user via CLI — it's called by the meta skill (Phase 6) after user approves at the checkpoint

</specifics>

<deferred>
## Deferred Ideas

- LLM-scored confidence beyond rules (SYNTH2-01, v2.1)
- Interactive diff UI (SYNTH2-02, v2.1)
- Auto-regenerate refactor (SYNTH2-03, v2.1)
- Full cost tracking integration for LLM fill (OBS-01, v2.1)

</deferred>
