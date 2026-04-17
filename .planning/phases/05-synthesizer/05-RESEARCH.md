# Phase 5: Synthesizer + Staging - Research

**Researched:** 2026-04-17
**Domain:** YAML round-trip authoring, rule-based matching, semantic pipeline validation, OpenRouter LLM fill-in
**Confidence:** HIGH

## Summary

Phase 5 implements `lib/pipeline_synthesizer.py` (pure lib, not BaseTool — mirrors `lib/playbook_generator.py`) that converts a validated `video_analysis` artifact into a pipeline YAML staged at `pipeline_defs/_staging/<slug>.yaml`. The work splits into: (1) a deterministic rule-based matcher over `pacing_style` + `shot_type_distribution` + `motion_type_distribution` against per-pipeline `expected_analysis` annotations; (2) an optional LLM fill-in (OpenRouter → `google/gemini-2.5-flash`, text-only) that only fills stage-level details inside the matched base template; (3) a semantic validator checking every `skill:` path and every `tools_available:` entry against the live registry; and (4) a minimal `accept_synthesis` / `reject_synthesis` API.

The key decisions are already locked in CONTEXT.md. Research confirms the technical anchors: `ruamel.yaml 0.19.1` (not installed yet — must be added to requirements.txt in this phase, not deferred to Phase 6 INT-02), `registry.list_all()` is the existing canonical name query (not `get_all_tool_names`), the current `lib/pipeline_loader.py::list_pipelines()` already excludes `_staging/` by virtue of non-recursive `glob("*.yaml")`, and no existing code computes `source_analysis_checksum` — synthesizer must canonicalize + SHA-256 the artifact itself.

**Primary recommendation:** Structure Plan 05-01 around a minimal skeleton in this order — checksum helper, rule matcher with per-signal contribution table, ruamel.yaml writer with provenance header comment — then Plan 05-02 adds semantic validation + run-record writer, then Plan 05-03 adds the accept/reject API and the LLM fill-in. Add `pipeline_defs/_staging/` to `.gitignore` and add `ruamel.yaml>=0.18,<0.20` to `requirements.txt` as part of 05-01.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Plan Decomposition (3 plans):**
- `05-01-PLAN.md` — `lib/pipeline_synthesizer.py` core: rule-based matching, slug generation (content hash), staging path writer using `ruamel.yaml`. Covers SYNTH-01, SYNTH-02, SYNTH-04, SYNTH-05, SYNTH-06.
- `05-02-PLAN.md` — Semantic validation layer: every `skill:` path exists; every tool in `tools_available` is registered; `pipeline_loader.list_pipelines()` excludes `_staging/`. Covers SYNTH-07, SYNTH-08. Also: pipeline_synthesis run-record writer using Phase 1's schema (SYNTH-09 already shipped schema-only; here we write records that validate).
- `05-03-PLAN.md` — Accept/reject API + LLM fill-in. Covers SYNTH-03, SYNTH-10.

**Matching Algorithm (SYNTH-02) — rule-based, not LLM:**
- `pacing_style` exact enum match → +0.40; adjacent (slow↔medium, medium↔fast, fast↔frenetic) → +0.15
- Dominant `shot_type_distribution.close_up > 0.5` matching `expected.close_up_heavy: true` → +0.25
- `motion_type_distribution.static > 0.5` favoring animated-explainer/screen-demo → +0.20
- `section_structure` length matches target pipeline's stage count → +0.15
- Bounded `[0, 1]`; ties broken alphabetically by pipeline name
- Output: `{base_pipeline, match_score, alternatives: [(name, score), ...]}`

**Slug Generation (SYNTH-06):**
- `slug = f"{base_pipeline_name}-{short_hash(source_analysis_checksum)[:8]}"`
- `source_analysis_checksum` = SHA-256 of canonicalized `video_analysis` artifact
- Collision detection: if `_staging/<slug>.yaml` exists and differs, append `-v2`, `-v3`, ...

**Staging Writer (SYNTH-05):**
- `ruamel.yaml` `YAML(typ='rt')` for round-trip with comments preserved
- Writes ONLY to `pipeline_defs/_staging/<slug>.yaml`; never directly to `pipeline_defs/`
- Header comment: `# synthesized from video_analysis checksum: <hash> at 2026-04-17`
- Create staging dir if missing

**Loader Exclusion (SYNTH-07):**
- Phase 5 audits `lib/pipeline_loader.py::list_pipelines()` and adds `_staging/` exclusion if not present
- Contract test: `_staging/test.yaml` + `real/prod.yaml` → loader returns only real

**Semantic Validation (SYNTH-08):**
- `validate_synthesized_pipeline(yaml_dict) -> list[ValidationError]`
- Per stage: `skill` field → `os.path.exists(f"skills/{path}.md")`
- Per `tools_available` entry: `tool_name in registry.list_all()`
- Empty list → valid; raises `SynthesisValidationError(issues)` on failure
- Called BEFORE approval — rejection short-circuits

**Modes (SYNTH-04):**
- `template` (default): LLM fills `tools_available` hints, `review_focus`, `success_criteria` — stays generalizable
- `replica`: closer reproduction — uses `reference_url_hash`, more specific prompts, tighter `human_approval_default`

**LLM Fill-In (SYNTH-03):**
- **Decision**: minimal `lib/llm_fill.py` helper using `openai` SDK pointed at OpenRouter with `google/gemini-2.5-flash` (fast, cheap)
- Bounded token budget: 2000 max
- Text-only, no video input
- Never invents stage structure; fills within base template only
- LLM output validated: every stage still has required manifest fields

**Accept / Reject API (SYNTH-10):**
- `accept_synthesis(slug: str) -> Path` uses `shutil.move` to promote `_staging/<slug>.yaml` → `pipeline_defs/<slug>.yaml`; returns final path
- `reject_synthesis(slug: str) -> None` uses `os.unlink(staging_path)`
- Both write pipeline_synthesis run record with `validation_status: "accepted"/"rejected"` — wait, schema only allows `"valid"/"invalid"/"pending"` — see clarification in Open Questions
- NO auto-approval path — no function combines synthesize + accept

**Pipeline `expected_analysis` Annotations (SYNTH-02 enabler):**
Each of 12 existing `pipeline_defs/*.yaml` gets a new optional top-level block:
```yaml
expected_analysis:
  pacing_style: fast
  close_up_heavy: true
  static_heavy: false
  expected_stage_count: 5
```
Additive, non-breaking — omitting block = no signal (match_score = 0 for that pipeline). Plan 05-01 adds annotations to all 12.

### Claude's Discretion
- Exact scoring weights — planner may tune; defaults above are reasonable
- Whether to expose `match_score` to user on synthesis completion (recommended **yes**)
- Whether LLM fill-in is opt-out via env var `VIDEO_SYNTH_LLM_FILL=false` (recommended **yes**)

### Deferred Ideas (OUT OF SCOPE)
- LLM-scored confidence beyond rules (SYNTH2-01, v2.1)
- Interactive diff UI (SYNTH2-02, v2.1)
- Auto-regenerate refactor (SYNTH2-03, v2.1)
- Full cost tracking integration for LLM fill (OBS-01, v2.1)
- Auto-execution of synthesized pipeline (explicit REQUIREMENTS "Out of Scope")
- New Remotion scene types
- Streaming
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SYNTH-01 | `lib/pipeline_synthesizer.py` (NOT a `BaseTool`, mirrors `lib/playbook_generator.py`) consumes a `video_analysis` artifact and emits pipeline YAML | `lib/playbook_generator.py` audited — identical shape (module-level functions + `jsonschema.validate`), no class. Use same pattern. |
| SYNTH-02 | Rule-based matching (not LLM) mapping `pacing_style` + `shot_type_distribution` + `motion_type_distribution` to one of 12 pipelines with `match_score` in [0, 1] | `video_analysis.schema.json` defines exact enum values and field shapes — researched below. Per-pipeline `expected_analysis` block enables the match; planner adds it to all 12 pipelines in 05-01. |
| SYNTH-03 | LLM (provider-agnostic) fills stage-level details only, never invents structure | OpenRouter via `openai` SDK pattern verified; `google/gemini-2.5-flash` priced at $0.30/$2.50 per M tokens; 2k token budget fits in <$0.01 per synthesis. Text-only chat completion. |
| SYNTH-04 | `mode="template"` (default) and `mode="replica"` supported | Two-branch prompt strategy in `lib/llm_fill.py`; schema allows only these two values. |
| SYNTH-05 | Output ONLY to `pipeline_defs/_staging/<slug>.yaml` using `ruamel.yaml>=0.18` (YAML 1.2, comment-preserving); never directly to `pipeline_defs/` | ruamel.yaml 0.19.1 is latest stable; API verified (`YAML(typ='rt')`, `yaml.preserve_quotes`, `yaml.indent(mapping, sequence, offset)`). Not installed in repo yet — MUST add to requirements.txt. |
| SYNTH-06 | Slug has short content hash for collision avoidance + idempotency | No prior code computes `source_analysis_checksum` — synthesizer uses `hashlib.sha256(json.dumps(artifact, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()`. Canonical JSON form per CONTEXT.md precedent. |
| SYNTH-07 | `pipeline_loader.list_pipelines()` excludes `pipeline_defs/_staging/` | Verified: current `glob("*.yaml")` is non-recursive → subdirs already ignored. Phase 5 adds an explicit `if not p.parent.name.startswith("_")` filter as a defense-in-depth guard so a future refactor to `**/*.yaml` doesn't silently expose staging. |
| SYNTH-08 | Synthesized YAML validates against `pipeline_manifest.schema.json` AND passes semantic validation (`skill:` path exists; every tool registered) | `registry.list_all()` returns `list[str]` of registered names (verified in source). Skill files live under `skills/<path>.md` — synthesizer checks `os.path.exists`. Manifest schema verified — `stages` is required list, stage requires `name`, uses `skill`/`tools_available` strings. |
| SYNTH-09 | `schemas/artifacts/pipeline_synthesis.schema.json` captures run record | **Already shipped Phase 1**. Phase 5 writes records that validate against it; enum `validation_status` is `valid\|invalid\|pending` — NOT `accepted\|rejected`. See Open Questions. |
| SYNTH-10 | Accept (`move _staging/<slug>.yaml` → `pipeline_defs/<slug>.yaml`) or reject (`unlink _staging/<slug>.yaml`) via explicit API | Pure stdlib (`shutil.move`, `pathlib.Path.unlink`). Run record written on both paths. |
</phase_requirements>

## Project Constraints (from CLAUDE.md / AGENT_GUIDE.md)

These directives apply because Phase 5 extends a production pipeline system that lives by Rule Zero:

- **No orchestration logic in Python.** `lib/pipeline_synthesizer.py` is a pure lib. It does NOT drive stages, does NOT call checkpoint. The meta skill (Phase 6) calls synthesizer functions and drives checkpoint itself.
- **Tools inherit from `BaseTool`.** Synthesizer is a lib, NOT a tool — correct per CONTEXT.md and REQUIREMENTS SYNTH-01.
- **Artifacts must validate against `schemas/`.** Run-record emission must `jsonschema.validate` before write. Written YAML must `jsonschema.validate` against `pipeline_manifest.schema.json` before landing in `_staging/`.
- **No bypass paths.** Per SYNTH-10: "no auto-approval path exists." Synthesize and accept MUST be separate public functions; no convenience wrapper that combines them — even for tests.
- **Tool class naming.** N/A — this is a lib, not a tool.
- **No hand-rolled tool discovery.** Use `registry.list_all()` (the existing API). Don't re-implement `_tools` traversal.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ruamel.yaml` | `>=0.18,<0.20` (latest `0.19.1`, 2025) | YAML 1.2 round-trip writer that preserves comments, key order, quote style, indentation | `PyYAML` (already in repo at `>=6.0`) cannot preserve comments or round-trip without destructive reformat. `ruamel.yaml` is the canonical comment-preserving YAML library for Python; author is the one who shipped YAML 1.2 support for PyYAML before forking. **VERIFIED via PyPI JSON API: 0.19.1, requires-python >=3.9**. |
| `openai` | `>=1.0,<3` (already in requirements.txt) | LLM fill-in client pointed at OpenRouter base URL | Project already uses this SDK for the OpenRouter provider (Phase 3). No new dep. |
| `jsonschema` | `>=4.20` (already present, 4.26 installed) | Validates synthesized YAML against manifest schema + run record against pipeline_synthesis schema | Already the project's validator throughout; reuse. |
| `hashlib` | stdlib | SHA-256 of canonicalized artifact for `source_analysis_checksum` | stdlib, deterministic, reproducible. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `shutil` | stdlib | `shutil.move(src, dst)` for atomic-ish `_staging/` → `pipeline_defs/` promote | accept_synthesis only |
| `pathlib.Path.unlink` | stdlib | Delete staging YAML on reject | reject_synthesis only |
| `difflib` | stdlib | Produce unified `diff_against_base` text for the run record | synthesizer emits after YAML generation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ruamel.yaml` | `PyYAML` | Loses all comments on round-trip. `_staging/` YAMLs need the provenance header comment; `PyYAML` would either strip or require manual string prepend. Rejected. |
| Custom `openai` call | Anthropic / Gemini SDK direct for LLM fill | `openai>=1.0` already in requirements.txt, same client shape as Phase 3's OpenRouter provider. No reason to pull another SDK. |
| Compute checksum at provider tools (Phase 2/3) | Keep all `video_analysis` artifacts as-is, synthesizer computes on consume | Providers don't currently emit checksums; adding one there crosses the phase boundary. Synthesizer is the first consumer that needs idempotency — compute here. |
| `yaml.safe_dump` with string-prefix header | `ruamel.yaml` with `ca` (comment attachment) on the data root | ruamel's comment API is fragile (commented-map internals). Prefer: dump body with ruamel, then file-handle `write()` the header comment line BEFORE the body. Simpler, works, no ruamel internals exposed. |

**Installation — add to `requirements.txt` in Plan 05-01** (do NOT defer to Phase 6):
```
ruamel.yaml>=0.18,<0.20
```

Rationale for not deferring: Phase 6 INT-02 covers the dep as a doc completion task, but Phase 5 code will `import ruamel.yaml` at module top. The test suite in 05-01 will fail to collect if the dep isn't there. Add it now, Phase 6 INT-02 becomes a no-op confirmation.

**Version verification (Context7 + PyPI):**
```bash
curl -s https://pypi.org/pypi/ruamel.yaml/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
# → 0.19.1
```
`[VERIFIED: pypi.org/pypi/ruamel.yaml/json, 2026-04-17]`

## Architecture Patterns

### Recommended Project Structure
```
lib/
├── pipeline_synthesizer.py   # NEW — core module (matcher + slug + writer + validator + accept/reject)
├── llm_fill.py               # NEW — bounded OpenRouter text-only helper
├── pipeline_loader.py         # EDIT — add explicit _staging guard in list_pipelines()
├── playbook_generator.py      # UNCHANGED — reference pattern
└── analysis_errors.py         # EDIT — add SynthesisValidationError (or new file — see Open Questions)

pipeline_defs/
├── _staging/                 # NEW dir — gitignored, created at first staging write
├── animated-explainer.yaml    # EDIT — add expected_analysis block
├── animation.yaml             # EDIT
├── avatar-spokesperson.yaml   # EDIT
├── cinematic.yaml             # EDIT
├── clip-factory.yaml          # EDIT
├── documentary-montage.yaml   # EDIT
├── framework-smoke.yaml       # EDIT
├── hybrid.yaml                # EDIT
├── localization-dub.yaml      # EDIT
├── podcast-repurpose.yaml     # EDIT
├── screen-demo.yaml           # EDIT
└── talking-head.yaml          # EDIT  (12 total — matches AGENT_GUIDE.md list)

tests/
├── contracts/
│   └── test_phase5_synthesis.py          # NEW — end-to-end: artifact → staged YAML → validation
└── unit/
    ├── test_pipeline_synthesizer.py      # NEW — matcher scoring, slug determinism, collisions
    ├── test_semantic_validation.py       # NEW — invalid skill path, unregistered tool
    ├── test_llm_fill.py                  # NEW — mocked openai client, prompt shape
    └── test_accept_reject.py             # NEW — move/unlink + run record writes

schemas/pipelines/
└── pipeline_manifest.schema.json         # UNCHANGED — manifest does not currently include
                                          #   expected_analysis at root; schema has
                                          #   additionalProperties: false. MUST ADD
                                          #   expected_analysis to schema as optional
                                          #   top-level object, OR the 12 annotated YAMLs
                                          #   will fail existing contract tests. See
                                          #   Pitfall 1 below.
```

### Pattern 1: Pure-lib module (mirrors `lib/playbook_generator.py`)
**What:** Module-level functions, no class. Public API surface is deliberate: every function signature is a stage in the synthesizer's responsibility chain.
**When to use:** Always for Phase 5's synthesizer — REQUIREMENTS SYNTH-01 requires it.
**Example (adapted from `lib/playbook_generator.py`):**
```python
# Source: /workspace/lib/playbook_generator.py, adapted for synthesizer
# [CITED: lib/playbook_generator.py:1-50]
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema
from ruamel.yaml import YAML

PIPELINE_DEFS_DIR = Path(__file__).resolve().parent.parent / "pipeline_defs"
STAGING_DIR = PIPELINE_DEFS_DIR / "_staging"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "pipelines" / "pipeline_manifest.schema.json"


def synthesize_pipeline(
    analysis: dict[str, Any],
    *,
    mode: str = "template",
    provider_used: str = "gemini",
    use_llm_fill: bool | None = None,  # None = env-controlled
) -> dict[str, Any]:
    """Produce a run-record dict and stage the YAML.

    Returns a `pipeline_synthesis` artifact (validates against
    schemas/artifacts/pipeline_synthesis.schema.json).
    """
    checksum = _canonical_sha256(analysis)
    match = match_base_pipeline(analysis)              # SYNTH-02
    base_manifest = _load_base(match["base_pipeline"])
    synthesized = _apply_mode(base_manifest, analysis, mode=mode, use_llm_fill=use_llm_fill)
    issues = validate_synthesized_pipeline(synthesized)  # SYNTH-08
    slug = _build_slug(match["base_pipeline"], checksum)
    staging_path = _write_staging(synthesized, slug, checksum)
    diff = _unified_diff(base_manifest, synthesized)
    record = {
        "version": "1.0",
        "base_pipeline": match["base_pipeline"],
        "match_score": match["match_score"],
        "mode": mode,
        "staging_path": str(staging_path.relative_to(PIPELINE_DEFS_DIR.parent)),
        "diff_against_base": diff,
        "validation_status": "valid" if not issues else "invalid",
        "source_analysis_checksum": checksum,
        "provider_used": provider_used,
    }
    jsonschema.validate(instance=record, schema=_load_synthesis_schema())
    return record


def accept_synthesis(slug: str) -> Path:
    """Move _staging/<slug>.yaml → pipeline_defs/<slug>.yaml."""
    import shutil
    src = STAGING_DIR / f"{slug}.yaml"
    dst = PIPELINE_DEFS_DIR / f"{slug}.yaml"
    if dst.exists():
        raise FileExistsError(f"Promoted path already exists: {dst}")
    shutil.move(str(src), str(dst))
    return dst


def reject_synthesis(slug: str) -> None:
    """Delete _staging/<slug>.yaml."""
    (STAGING_DIR / f"{slug}.yaml").unlink()
```

### Pattern 2: ruamel.yaml round-trip with provenance header
**What:** Load base pipeline → mutate → dump to `_staging/` with a `#`-prefixed header that records checksum, base, match_score, mode.
**When to use:** The staging writer path only.
**Example:**
```python
# [CITED: ruamel.yaml docs — yaml.readthedocs.io/en/latest/overview]
from ruamel.yaml import YAML
from io import StringIO
from datetime import datetime, timezone

def _write_staging(manifest: dict, slug: str, checksum: str, *, mode: str, match_score: float, base: str) -> Path:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    path = STAGING_DIR / f"{slug}.yaml"

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 120  # avoid aggressive line-wrap on long strings

    buf = StringIO()
    yaml.dump(manifest, buf)

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    header = (
        f"# synthesized from video_analysis checksum: {checksum}\n"
        f"# base_pipeline: {base}\n"
        f"# match_score: {match_score:.2f}\n"
        f"# mode: {mode}\n"
        f"# at: {timestamp}\n"
    )
    path.write_text(header + buf.getvalue(), encoding="utf-8")
    return path
```
**Why not** attach comments via `manifest.yaml_set_comment_before_after_key(...)`? Reading the ruamel round-trip commented-map API for each key is fragile and couples the synthesizer to ruamel internals. Plain file-handle prefix is equivalent on re-load (YAML ignores `#` lines).

### Pattern 3: Rule-based matching with signal contribution table
**What:** Each signal contributes a bounded score; summing produces `match_score`. Explicit signals, explicit weights, no hidden LLM.
**When to use:** `match_base_pipeline(analysis) -> dict` only.
**Example:**
```python
def match_base_pipeline(analysis: dict) -> dict:
    """Return {base_pipeline, match_score, alternatives}."""
    ep = analysis["editing_pacing"]
    pacing = ep["pacing_style"]
    shot_dist = ep.get("shot_type_distribution", {})
    motion_dist = ep.get("motion_type_distribution", {})
    section_count = len(analysis.get("narrative", {}).get("section_structure", []))

    scores: list[tuple[str, float]] = []
    for name in list_pipelines():  # excludes _staging/
        expected = _load_expected_analysis(name)  # reads root `expected_analysis` block
        score = 0.0
        if expected.get("pacing_style") == pacing:
            score += 0.40
        elif _is_adjacent_pacing(expected.get("pacing_style"), pacing):
            score += 0.15
        # shot_type_distribution: synthesizer normalizes the canonical schema fields
        # (talking_head/b_roll/text_card/animation) to a single boolean heuristic
        # per pipeline. `close_up_heavy` = talking_head > 0.5 dominant.
        if expected.get("close_up_heavy") and shot_dist.get("talking_head", 0) > 0.5:
            score += 0.25
        # motion: schema uses motion_clip/animated_still/static_image
        if expected.get("static_heavy") and motion_dist.get("static_image", 0) > 0.5:
            score += 0.20
        if expected.get("expected_stage_count") == section_count:
            score += 0.15
        scores.append((name, min(score, 1.0)))

    # Sort by (-score, name) → deterministic ties broken alphabetically
    scores.sort(key=lambda x: (-x[1], x[0]))
    return {
        "base_pipeline": scores[0][0],
        "match_score": scores[0][1],
        "alternatives": [{"name": n, "score": s} for n, s in scores[1:]],
    }
```

**IMPORTANT:** The CONTEXT.md's signal "`dominant shot_type_distribution.close_up > 0.5`" references a `close_up` key that does NOT exist in `video_analysis.schema.json`. The canonical schema uses `talking_head` / `b_roll` / `text_card` / `animation` (verified in `/workspace/schemas/artifacts/video_analysis.schema.json:55-60`). The planner MUST either:
1. Reinterpret as `talking_head > 0.5` (treating talking-head shots as the "close-up" semantic proxy), or
2. Extend the video_analysis schema to add a `close_up` field (SCHEMA change → breaks Phase 1 contract).
**Recommendation:** Option 1 — use `talking_head > 0.5` under the `close_up_heavy` pipeline flag name. The pipeline-side annotation name stays `close_up_heavy` because that's what CONTEXT.md decided; internal mapping handles the schema field reality.

### Anti-Patterns to Avoid
- **LLM for base-pipeline selection.** SYNTH-02 explicitly mandates rule-based; LLM is only for stage-detail fill (SYNTH-03). Do NOT let an LLM choose the base pipeline.
- **Writing directly to `pipeline_defs/<slug>.yaml`.** SYNTH-05 is absolute. Synthesizer writes only to `_staging/`; `accept_synthesis` is the ONLY promotion path.
- **Convenience wrapper `synthesize_and_accept`.** Expressly forbidden (SYNTH-10: "no auto-approval path exists"). A reviewer must be able to grep the repo and see that no such function exists.
- **Attaching ruamel comments via internal API.** Use file-handle `write()` of header lines before the dumped body. Simpler, portable.
- **Computing slug from a random suffix.** Breaks idempotency. Slug MUST be deterministic function of `source_analysis_checksum`.
- **Fabricating `close_up` field in analysis.** Not in schema. Map to `talking_head` instead.
- **Letting `SynthesisValidationError` extend generic `Exception` only.** Inherit from a base that's consistent with `lib/analysis_errors.py` conventions (class-per-module-family). See Open Questions.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Preserve comments in round-tripped YAML | Custom line-aware regex | `ruamel.yaml YAML(typ='rt')` | Every edge case (folded strings, anchors, flow-style, unicode keys) already handled. |
| Diff two YAML documents | Side-by-side dict walker | `difflib.unified_diff` on two `yaml.dump` outputs | Produces a standard unified diff format reviewers can read; free. |
| Tool name lookup | `from tools import ...` per tool | `registry.list_all()` | The registry IS the source of truth per CLAUDE.md Rule Zero; skipping it silently desyncs with `support_envelope()`. |
| Content hash | MD5 / custom | `hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',',':'), ensure_ascii=False).encode())` | SHA-256 is the project's existing convention (per CONTEXT.md "established patterns"); canonical JSON args match `tools/cost_tracker` checksum style. |
| OpenRouter HTTP client | `requests.post(...)` | `openai>=1.0` with `base_url="https://openrouter.ai/api/v1"` | Already in requirements.txt, already used by `tools/analysis/openrouter_video_analyzer.py` — consistent error handling, retries, streaming. |
| Checking if `_staging/` path is excluded | Custom `str.startswith("_")` in loader | Rely on current non-recursive `glob("*.yaml")` + add defensive filter | `glob("*.yaml")` already doesn't descend into subdirs. Add the filter as defense-in-depth for a future `**/*.yaml` refactor. |
| Cost tracking for LLM fill | Custom counter | **Skip** — this is explicitly deferred (OBS-01, v2.1) | Phase 5 does not integrate with `cost_tracker.py`. Record the model used in run record, nothing more. |

**Key insight:** Every piece of Phase 5 has a stdlib or already-imported equivalent. New dependencies: ONLY `ruamel.yaml`. No new tools. No new selectors. Lib module + 12 one-line YAML annotations + 3 plans.

## Runtime State Inventory

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — synthesizer is stateless per call; reads analysis artifact, writes staging YAML + run-record dict returned to caller | None |
| Live service config | OpenRouter API (for LLM fill only) — configured via `OPENROUTER_API_KEY` env var (same as Phase 3 provider) | None (env already documented in INT-03) |
| OS-registered state | None — no daemons, task-schedules, or launch entries | None |
| Secrets / env vars | `OPENROUTER_API_KEY` (shared with Phase 3); optional `VIDEO_SYNTH_LLM_FILL=false` to disable LLM | Document new opt-out in Phase 6 INT-03 docs |
| Build artifacts / installed packages | **`ruamel.yaml` is NOT installed** — must add to requirements.txt in 05-01. Plans must run `pip install -r requirements.txt` as first Wave 0 action before any synthesizer tests | Add dep in 05-01; reinstall in dev env |

## Common Pitfalls

### Pitfall 1: Adding `expected_analysis` to pipeline YAMLs breaks the manifest schema
**What goes wrong:** `schemas/pipelines/pipeline_manifest.schema.json` has `"additionalProperties": false` at the root (verified line 160). Any of the 12 YAMLs that gets an `expected_analysis` top-level block will FAIL validation, breaking `lib/pipeline_loader.py::load_pipeline()` and TEST-03 (backward compat).
**Why it happens:** Schema's strict closure prevents undeclared top-level keys.
**How to avoid:** Plan 05-01 MUST include an edit to `schemas/pipelines/pipeline_manifest.schema.json` adding:
```json
"expected_analysis": {
  "type": "object",
  "description": "Signals used by pipeline_synthesizer (Phase 5) for rule-based matching.",
  "properties": {
    "pacing_style": { "type": "string", "enum": ["slow_contemplative","steady_educational","dynamic_social","rapid_fire","variable"] },
    "close_up_heavy": { "type": "boolean" },
    "static_heavy": { "type": "boolean" },
    "expected_stage_count": { "type": "integer", "minimum": 1 }
  },
  "additionalProperties": false
}
```
**Warning signs:** Any existing `test_pipeline_loader` suite failing after annotating a YAML. Verify by running contract tests after adding `expected_analysis` to the FIRST pipeline, before annotating the other 11.

### Pitfall 2: `validation_status` enum mismatch between schema and CONTEXT.md decision
**What goes wrong:** Schema `pipeline_synthesis.schema.json:46-50` constrains `validation_status` to `"valid" | "invalid" | "pending"`. CONTEXT.md says accept/reject API "write a pipeline_synthesis run record with `validation_status: 'accepted'/'rejected'`." Writing those values will fail `jsonschema.validate`.
**Why it happens:** Two independent runs of discuss-phase — the schema was locked in Phase 1, CONTEXT.md proposed accept/reject values without cross-checking.
**How to avoid:** Phase 5 uses `validation_status: "valid"` for accepted records and `"invalid"` for rejected records (since rejection usually follows a validation failure). If the user rejects a semantically-valid synthesis (aesthetic disagreement), emit `validation_status: "valid"` anyway — the field describes the code-verified state, not user sentiment. Record the user action elsewhere (e.g., in `diff_against_base` narrative or a future `user_action` field; do NOT extend schema in Phase 5). See Open Question 1.
**Warning signs:** `jsonschema.ValidationError` at end of `accept_synthesis` / `reject_synthesis`.

### Pitfall 3: `ruamel.yaml` `typ='rt'` loses empty-list `[]` rendering
**What goes wrong:** Base pipelines like `cinematic.yaml` have `tools_available: []` — ruamel in round-trip mode sometimes renders this as a block newline followed by nothing, or flow `[]` — inconsistently per version. If the base has `[]` but LLM fill populates it with a list, the diff looks noisy.
**Why it happens:** ruamel preserves FLOW vs BLOCK style per-node based on source.
**How to avoid:** Set `yaml.default_flow_style = False` for block-style output everywhere except explicitly empty collections. Write a post-dump normalizer that replaces empty BLOCK-style sequences with flow `[]` before writing. Add a contract test: synthesize the `cinematic` pipeline, confirm `tools_available: []` renders identically in base and synthesized when mode=`template` and LLM fill is disabled.
**Warning signs:** `diff_against_base` shows whitespace churn on untouched stages.

### Pitfall 4: OpenRouter `google/gemini-2.5-flash` does not always honor `response_format={"type": "json_schema", ...}`
**What goes wrong:** From Phase 3 research (OR-04): some OpenRouter-routed models silently ignore `response_format` and return prose. For LLM fill, the synthesizer expects a JSON object with `{"tools_available": [...], "review_focus": [...], "success_criteria": [...]}` per stage.
**Why it happens:** OpenRouter `response_format` passthrough varies per upstream provider.
**How to avoid:** (1) Use `response_format={"type": "json_object"}` (broader support) + in-prompt schema; (2) wrap in try/except with ONE retry (Phase 3 pattern); (3) if parse fails twice, fall back to base-pipeline values unchanged — do NOT raise. LLM fill is advisory, not critical.
**Warning signs:** `json.JSONDecodeError` on LLM response; stage details identical to base.

### Pitfall 5: Slug collision on re-run of identical analysis
**What goes wrong:** Same video → same analysis → same checksum → same slug. Second call overwrites the first staging file silently.
**Why it happens:** Idempotency is a feature (same input → same output), but the user might have manually edited the previous staging file.
**How to avoid:** Before writing, if `_staging/<slug>.yaml` exists, byte-compare with what we're about to write. Identical → no-op, return existing path + log `ALREADY_STAGED`. Different → rename to `_staging/<slug>-v2.yaml`, `-v3.yaml`. Never overwrite a human edit without a signal.
**Warning signs:** User reports "I edited the staging file and it got reverted."

### Pitfall 6: `registry.list_all()` returns empty before `registry.discover()` called
**What goes wrong:** Semantic validation's `tool_name in registry.list_all()` silently returns False for every tool because the registry lazy-loads modules.
**Why it happens:** `registry.discover()` must be called once per process; tests don't always do it.
**How to avoid:** Synthesizer calls `registry.ensure_discovered()` at top of `validate_synthesized_pipeline`. Already idempotent per `ToolRegistry.ensure_discovered` (line 86-89 of `tools/tool_registry.py`).
**Warning signs:** All synthesized YAMLs fail semantic validation in fresh test processes.

### Pitfall 7: `shutil.move` is not atomic across filesystems
**What goes wrong:** On some container setups, `pipeline_defs/` and `pipeline_defs/_staging/` could be on different mount points, causing a copy+delete with a window of inconsistency.
**Why it happens:** `shutil.move` falls back to `copy2 + unlink` when `os.rename` EXDEV fails.
**How to avoid:** For Phase 5 the directories are sibling paths under a single mount — `os.rename` succeeds. Enforce by asserting `src.parent.parent == dst.parent` (both under `pipeline_defs/`). If a future refactor makes them cross-mount, `accept_synthesis` should fsync the destination before unlink.
**Warning signs:** Intermittent test flakes under Docker with tmpfs mounts.

## Code Examples

### Semantic validation skeleton
```python
# [CITED: tools/tool_registry.py:95-97, confirms list_all() signature]
from tools.tool_registry import registry
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


class SynthesisValidationError(Exception):
    """Raised when a synthesized pipeline fails semantic validation.

    ``issues`` is a list[str] of human-readable messages. Consumers that
    need per-issue structure should inspect ``issues`` directly rather
    than re-parse ``str(exc)``.
    """
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("\n".join(issues))


def validate_synthesized_pipeline(manifest: dict) -> list[str]:
    """Return issues list. Empty = pass."""
    registry.ensure_discovered()
    known_tools = set(registry.list_all())
    issues: list[str] = []

    for stage in manifest.get("stages", []):
        skill = stage.get("skill")
        if skill:
            expected = SKILLS_DIR / f"{skill}.md"
            if not expected.exists():
                issues.append(f"stage {stage['name']!r}: skill file not found: {expected}")
        for tool in stage.get("tools_available", []):
            if tool not in known_tools:
                issues.append(
                    f"stage {stage['name']!r}: tool {tool!r} not in registry "
                    f"(run `registry.discover()`; known {len(known_tools)} tools)"
                )

    return issues
```

### Content hash (canonical JSON SHA-256)
```python
# [ASSUMED: matches project's "canonical JSON checksum" pattern established in
#  CONTEXT.md "Established Patterns"; no prior implementation exists to cite]
import hashlib
import json

def _canonical_sha256(artifact: dict) -> str:
    canonical = json.dumps(
        artifact,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_slug(base_pipeline: str, checksum: str) -> str:
    return f"{base_pipeline}-{checksum[:8]}"
```

### Minimal `lib/llm_fill.py` (OpenRouter text-only)
```python
# [CITED: tools/analysis/openrouter_video_analyzer.py pattern — openai SDK + base_url]
# [CITED: openrouter.ai pricing — google/gemini-2.5-flash @ $0.30/$2.50 per M tokens]
from __future__ import annotations
import json
import os
from typing import Any

from openai import OpenAI


MODEL = os.environ.get("VIDEO_SYNTH_LLM_MODEL", "google/gemini-2.5-flash")
MAX_TOKENS = 2000  # bounded per CONTEXT.md


def fill_stage_details(
    base_manifest: dict,
    analysis: dict,
    *,
    mode: str = "template",
) -> dict:
    """Return a manifest dict with stage details filled by LLM.

    Falls back to the base manifest unchanged on any LLM failure — this
    path is advisory, never critical. Respects VIDEO_SYNTH_LLM_FILL=false.
    """
    if os.environ.get("VIDEO_SYNTH_LLM_FILL", "true").lower() == "false":
        return base_manifest
    if not os.environ.get("OPENROUTER_API_KEY"):
        return base_manifest

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )

    prompt = _build_prompt(base_manifest, analysis, mode=mode)
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content or ""
        filled = json.loads(text)
    except Exception:
        return base_manifest

    return _merge_stage_details(base_manifest, filled)
```

### Loader exclusion (defense-in-depth)
```python
# [CITED: lib/pipeline_loader.py:53-56]
def list_pipelines(defs_dir: Optional[Path] = None) -> list[str]:
    """List all available pipeline manifest names. Excludes _staging/ and any
    other underscore-prefixed subdirectory, even if a future refactor moves
    to a recursive glob."""
    defs_dir = defs_dir or PIPELINE_DEFS_DIR
    return [
        p.stem
        for p in defs_dir.glob("*.yaml")
        if not p.parent.name.startswith("_")
    ]
```
The filter is redundant today (non-recursive `glob("*.yaml")` can only yield direct children of `defs_dir`) but future-proofs the exclusion.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `PyYAML.safe_dump` for all YAML writes in the repo | `ruamel.yaml` for writes that need comments / round-trip | Phase 5 (this phase) | Comments survive synthesize → review → accept. `PyYAML` stays for read-only `safe_load` paths (loader, contract tests). |
| Claude 3.5 Sonnet for LLM tasks | `google/gemini-2.5-flash` via OpenRouter for low-stakes fill-in | Phase 5 decision per CONTEXT.md | $0.30 / $2.50 per M — ~100x cheaper than Sonnet for 2k budget. Quality sufficient for stage-detail fill. |
| `response_format={"type": "json_schema", ...}` for structured output | `response_format={"type": "json_object"}` + in-prompt schema for OpenRouter passthrough | Phase 3 pitfall carried forward | Broader model support via OpenRouter; one retry + base fallback is the safety net. |

**Deprecated / outdated:**
- Do NOT use `yaml.load(stream, Loader=yaml.FullLoader)` for authoring — that's PyYAML; we're moving to `ruamel.yaml` for writes that need round-trip.
- Do NOT call `openai.ChatCompletion.create` (legacy v0.x API) — Phase 3 already uses `client.chat.completions.create` v1.0+ shape; LLM fill follows suit.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `close_up` in CONTEXT.md matching rules is a semantic proxy for `shot_type_distribution.talking_head > 0.5` | Architecture Pattern 3 / Pitfall on canonical fields | Matcher silently returns 0 for every pipeline because `close_up` key never present; all matches tie at 0 and alphabetical tiebreak picks `animated-explainer` every time. |
| A2 | Canonical JSON form `json.dumps(..., sort_keys=True, separators=(',',':'), ensure_ascii=False)` is the project-standard for checksums | Content hash example | A different canonicalization (e.g., with ensure_ascii=True, or different separator) → different checksum → idempotency broken across re-runs. Mitigation: centralize in one helper used by any future checksum site. |
| A3 | `SynthesisValidationError` belongs in `lib/pipeline_synthesizer.py` (not `lib/analysis_errors.py`) | Error taxonomy | `lib/analysis_errors.py` module docstring explicitly says "Error taxonomy for video-analysis tools" — synthesis is not analysis. Keep them separate. Low risk. |
| A4 | `ruamel.yaml>=0.18,<0.20` is the right constraint (current `0.19.1`) | Standard Stack | A future 0.20 may introduce API breaks; pinning prevents surprise. Low risk — `ruamel.yaml` has stable API since 0.17. |
| A5 | Adding `expected_analysis` to manifest schema is acceptable | Pitfall 1 | If any OTHER consumer of the schema treats it as closed, it breaks. Verified only `lib/pipeline_loader.py` uses the schema — low risk. |
| A6 | `validation_status` must use `valid`/`invalid`/`pending` from schema enum, not `accepted`/`rejected` from CONTEXT.md | Pitfall 2 | CONTEXT.md decision + schema disagree. Resolution requires user clarification OR code rationalization (the latter done here). |
| A7 | OpenRouter `usage.cost` on response is USD (from Phase 3 conftest fixture `_openrouter_resp_ok`) | LLM fill-in | Recording cost in future OBS-01 uses this field. Phase 5 does not track it, so risk is deferred. |

## Open Questions

1. **`validation_status` enum: schema vs CONTEXT.md disagree.**
   - What we know: schema allows `valid\|invalid\|pending`; CONTEXT.md Accept/Reject decision uses `accepted\|rejected`.
   - What's unclear: did the phase owner mean to extend the schema in Phase 5, or to re-use `valid`/`invalid`?
   - Recommendation: Plan 05-02 or 05-03 resolves this explicitly. Prefer NOT extending schema (Phase 1 is closed). Use `validation_status: "valid"` for accepted + `validation_status: "invalid"` for rejected-due-to-validation-failure; for user-initiated reject, `validation_status: "valid"` and surface user action via `diff_against_base` or logs. Ask user at plan-approval time.

2. **`close_up` → `talking_head` mapping is implicit.**
   - What we know: CONTEXT.md rule uses `close_up > 0.5`; schema has `talking_head`.
   - What's unclear: did the user intend `talking_head`, or are they thinking about a future schema extension?
   - Recommendation: Plan 05-01 uses `talking_head` and documents the mapping in the pipeline-annotation README. Flag for user at approval.

3. **Should `_staging/` be gitignored?**
   - What we know: CONTEXT.md specifics say "should be — add `.gitignore` entry in Phase 5 via 05-01". Current `.gitignore` only excludes `pipeline/` (different dir).
   - Recommendation: Plan 05-01 adds `pipeline_defs/_staging/` to `.gitignore`. Confirmed.

4. **Does LLM fill need a JSON schema for its output?**
   - What we know: base pipelines have heterogeneous stage shapes; prompt asks for stage details.
   - What's unclear: strict schema or free-form?
   - Recommendation: Include an inline schema in the prompt for the three filled fields (`tools_available`, `review_focus`, `success_criteria`) only. Validate. On failure, fall back to base unchanged.

5. **Wave 0: do we need to install `ruamel.yaml` before planning?**
   - What we know: dep missing from `requirements.txt` and from the venv.
   - Recommendation: **Yes.** Plan 05-01 task 0 is "add `ruamel.yaml>=0.18,<0.20` to `requirements.txt`; `pip install -r requirements.txt`." Everything downstream depends on it.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all | ✓ | 3.12 (assumed from devcontainer) | — |
| `openai` SDK | LLM fill-in | ✓ | `>=1.0,<3` (in requirements.txt) | — |
| `jsonschema` | record + manifest validation | ✓ | 4.26.0 installed | — |
| `PyYAML` | reading base pipelines (existing pipeline_loader use) | ✓ | `>=6.0` (in requirements.txt) | — |
| `ruamel.yaml` | writing staged YAMLs with comments | ✗ | NOT INSTALLED | No viable fallback (PyYAML can't preserve comments round-trip) |
| `OPENROUTER_API_KEY` env var | LLM fill-in only | ✗ (tests will mock) | — | `VIDEO_SYNTH_LLM_FILL=false` skips the call; base manifest returned unchanged |

**Missing dependencies with no fallback:**
- `ruamel.yaml` — blocking. Must be installed as Wave 0 task in Plan 05-01.

**Missing dependencies with fallback:**
- `OPENROUTER_API_KEY` — LLM fill is advisory; synthesizer returns base manifest unchanged when key absent. No user-visible error.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (imports + fixtures present in `tests/unit/conftest.py`; no `pyproject.toml` or `pytest.ini` found — uses defaults) |
| Config file | none — default pytest discovery finds `tests/contracts/` and `tests/unit/` |
| Quick run command | `pytest tests/unit/test_pipeline_synthesizer.py -x --tb=short` |
| Full suite command | `pytest tests/unit tests/contracts --tb=short` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SYNTH-01 | lib module with module-level functions (not BaseTool) | unit | `pytest tests/unit/test_pipeline_synthesizer.py::test_module_shape -x` | ❌ Wave 0 |
| SYNTH-02 | rule-based matcher returns top pipeline + alternatives with deterministic scoring | unit | `pytest tests/unit/test_pipeline_synthesizer.py::test_matcher -x` | ❌ Wave 0 |
| SYNTH-02 | signal weights produce expected match_score on fixture analysis | unit | `pytest tests/unit/test_pipeline_synthesizer.py::test_scoring_weights -x` | ❌ Wave 0 |
| SYNTH-02 | ties broken alphabetically | unit | `pytest tests/unit/test_pipeline_synthesizer.py::test_deterministic_ties -x` | ❌ Wave 0 |
| SYNTH-03 | LLM fill falls back to base on parse failure / missing key / env opt-out | unit | `pytest tests/unit/test_llm_fill.py -x` | ❌ Wave 0 |
| SYNTH-04 | template vs replica produces different prompts / outputs | unit | `pytest tests/unit/test_llm_fill.py::test_modes -x` | ❌ Wave 0 |
| SYNTH-05 | writer places file under `_staging/`, never outside | unit | `pytest tests/unit/test_pipeline_synthesizer.py::test_staging_only_write -x` | ❌ Wave 0 |
| SYNTH-05 | ruamel round-trip preserves comments of base + adds provenance header | unit | `pytest tests/unit/test_pipeline_synthesizer.py::test_provenance_header -x` | ❌ Wave 0 |
| SYNTH-06 | identical analysis → identical slug (idempotent); collision detection appends -v2 | unit | `pytest tests/unit/test_pipeline_synthesizer.py::test_slug_idempotent -x` | ❌ Wave 0 |
| SYNTH-07 | `list_pipelines()` excludes `_staging/` even after refactor to recursive glob | unit | `pytest tests/unit/test_pipeline_synthesizer.py::test_loader_excludes_staging -x` | ❌ Wave 0 |
| SYNTH-08 | semantic validation catches missing skill path | unit | `pytest tests/unit/test_semantic_validation.py::test_missing_skill -x` | ❌ Wave 0 |
| SYNTH-08 | semantic validation catches unregistered tool | unit | `pytest tests/unit/test_semantic_validation.py::test_unknown_tool -x` | ❌ Wave 0 |
| SYNTH-09 | emitted record validates against `pipeline_synthesis.schema.json` | contract | `pytest tests/contracts/test_phase5_synthesis.py::test_record_validates -x` | ❌ Wave 0 |
| SYNTH-10 | accept moves `_staging/<slug>.yaml` → `pipeline_defs/<slug>.yaml`; reject unlinks | unit | `pytest tests/unit/test_accept_reject.py -x` | ❌ Wave 0 |
| SYNTH-10 | NO function combines synthesize + accept (grep-based assertion) | contract | `pytest tests/contracts/test_phase5_synthesis.py::test_no_auto_approval -x` | ❌ Wave 0 |
| TEST-03 (regression) | all 12 existing pipelines still load after `expected_analysis` annotation + schema update | contract | `pytest tests/contracts -k pipeline` | ✓ existing coverage (must pass) |

### Sampling Rate
- **Per task commit:** `pytest tests/unit/test_pipeline_synthesizer.py -x --tb=short` (<5s target)
- **Per wave merge:** `pytest tests/unit tests/contracts -x --tb=short` (full phase-5 + regression)
- **Phase gate:** `pytest tests/unit tests/contracts` fully green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `pip install 'ruamel.yaml>=0.18,<0.20'` — dep not installed
- [ ] `requirements.txt` — add `ruamel.yaml>=0.18,<0.20` line
- [ ] `.gitignore` — add `pipeline_defs/_staging/`
- [ ] `tests/unit/test_pipeline_synthesizer.py` — new file, covers SYNTH-01, SYNTH-02, SYNTH-05, SYNTH-06, SYNTH-07
- [ ] `tests/unit/test_semantic_validation.py` — new file, covers SYNTH-08
- [ ] `tests/unit/test_llm_fill.py` — new file, covers SYNTH-03, SYNTH-04
- [ ] `tests/unit/test_accept_reject.py` — new file, covers SYNTH-10
- [ ] `tests/contracts/test_phase5_synthesis.py` — new file, covers SYNTH-09 integration + no-auto-approval assertion

## Sources

### Primary (HIGH confidence)
- `/workspace/schemas/artifacts/video_analysis.schema.json` — canonical field shapes for matcher
- `/workspace/schemas/artifacts/pipeline_synthesis.schema.json` — run-record schema (SYNTH-09 shipped)
- `/workspace/schemas/pipelines/pipeline_manifest.schema.json` — manifest schema (must extend for `expected_analysis`)
- `/workspace/lib/pipeline_loader.py` — existing loader, confirms non-recursive glob
- `/workspace/lib/playbook_generator.py` — pure-lib pattern template
- `/workspace/lib/analysis_errors.py` — error taxonomy convention
- `/workspace/tools/tool_registry.py` — `registry.list_all()` + `registry.ensure_discovered()`
- `/workspace/pipeline_defs/cinematic.yaml`, `/workspace/pipeline_defs/animated-explainer.yaml` — base pipeline structure samples
- `/workspace/tests/unit/conftest.py` — test framework + OpenRouter mock patterns
- `/workspace/tests/contracts/test_pipeline_synthesis_schema.py` — Phase 1 fixture for run-record shape
- PyPI JSON API: https://pypi.org/pypi/ruamel.yaml/json — ruamel.yaml 0.19.1 latest
- OpenRouter model card: https://openrouter.ai/google/gemini-2.5-flash — $0.30 / $2.50 per M, 1M context
- OpenRouter docs: https://openrouter.ai/docs/quickstart — `base_url="https://openrouter.ai/api/v1"` + openai SDK pattern

### Secondary (MEDIUM confidence)
- https://yaml.dev/doc/ruamel.yaml/overview/ — round-trip mode behavior and `preserve_quotes` / `indent` API

### Tertiary (LOW confidence)
- None. All claims anchored in code or verified docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — ruamel.yaml 0.19.1 verified on PyPI; openai SDK already in use; all other deps stdlib or already installed.
- Architecture: HIGH — pure-lib pattern is a direct read of `lib/playbook_generator.py`; semantic validator shape is a direct read of `registry.list_all()`.
- Pitfalls: HIGH — pitfalls 1 (schema closure), 2 (enum mismatch), and 6 (lazy discovery) are directly observable in the source. Pitfall 3 (empty list rendering) is a ruamel quirk documented in upstream issue tracker; verified by reading base pipeline YAMLs.
- Matching algorithm: MEDIUM — the weights from CONTEXT.md are the user's stated defaults; the `close_up` → `talking_head` mapping is an interpretation that the planner / user needs to confirm. Flagged as A1 in Assumptions Log.

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (30 days — stable Python/YAML domain, minor risk from OpenRouter model retirement before then)
