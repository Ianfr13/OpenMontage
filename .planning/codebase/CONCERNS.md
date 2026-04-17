# Codebase Concerns

**Analysis Date:** 2026-04-17

## Critical Issues

### Python Version Mismatch (Development Blocker)

**Issue:** Project requires Python 3.10+ but host environment is 3.9.6.

**Files:** `requirements.txt`, `setup.py`, `Makefile`

**Impact:** Environment setup fails. All local development is blocked until Python is upgraded or devcontainer is used.

**Fix approach:** 
1. Use `.devcontainer/` for isolated Python 3.10+ environment, OR
2. Install Python 3.10+ locally via Homebrew (`brew install python@3.10`) or pyenv

**Current status:** Documented in TODO.md but not yet resolved.

---

### FFmpeg Dependency Missing (Composition Blocker)

**Issue:** FFmpeg is required for video composition (`video_compose`), audio processing (`audio_mixer`), and video analysis (`video_analyzer`), but is not installed on the host.

**Files:** 
- `tools/video/video_compose.py` — depends on FFmpeg binary for compositing, subtitle burn-in, encoding
- `tools/audio/audio_mixer.py` — uses FFmpeg for audio mixing
- `tools/analysis/video_analyzer.py` — uses FFmpeg for frame extraction
- `Makefile` → `setup` target

**Impact:** Cannot generate or compose videos locally without FFmpeg. Pipelines that require composition (`animated-explainer`, `cinematic`, `avatar-spokesperson`, etc.) will fail.

**Fix approach:** Install FFmpeg via system package manager:
- macOS: `brew install ffmpeg`
- Linux: `apt-get install ffmpeg`
- Windows: `winget install ffmpeg` or download from ffmpeg.org

---

## Tech Debt

### Deprecated Image Generation Tool

**Issue:** `tools/graphics/image_gen.py` is marked deprecated and kept only for backward compatibility. It's a monolithic multi-provider tool that has been replaced by the selector pattern.

**Files:** `tools/graphics/image_gen.py`

**Current status:** Functional but old. Should migrate to `image_selector` which routes to per-provider tools (`flux_image`, `openai_image`, `recraft_image`, `local_diffusion`, `pexels_image`, `pixabay_image`).

**Fix approach:** 
1. Audit any direct calls to `image_gen` in pipelines or agent skills
2. Replace with `image_selector` in stage manifests
3. Deprecate `image_gen.py` fully (remove or mark as historical reference)

---

### Skills Synchronization Gap

**Issue:** 11 Layer 3 skills exist in `.agents/skills/` but are missing from `.claude/skills/`, breaking the local skill loading path for agents.

**Files:** 
- Missing from `.claude/skills/`:
  - `grok-media`
  - `gsap` (core + 6 plugins: `gsap-core`, `gsap-frameworks`, `gsap-performance`, `gsap-plugins`, `gsap-react`, `gsap-scrolltrigger`, `gsap-timeline`, `gsap-utils`)
  - `synthetic-screen-recording`

**Impact:** Agents cannot read these skills locally via `.claude/skills/`, forcing fallback to `.agents/skills/` or skill reading failures. This breaks the agent skill-loading flow described in AGENT_GUIDE.md.

**Fix approach:** Synchronize by running:
```bash
cp -r .agents/skills/grok-media .claude/skills/
cp -r .agents/skills/gsap .claude/skills/
cp -r .agents/skills/gsap-core .claude/skills/
cp -r .agents/skills/gsap-frameworks .claude/skills/
cp -r .agents/skills/gsap-performance .claude/skills/
cp -r .agents/skills/gsap-plugins .claude/skills/
cp -r .agents/skills/gsap-react .claude/skills/
cp -r .agents/skills/gsap-scrolltrigger .claude/skills/
cp -r .agents/skills/gsap-timeline .claude/skills/
cp -r .agents/skills/gsap-utils .claude/skills/
cp -r .agents/skills/synthetic-screen-recording .claude/skills/
```

---

### Incorrect Skill Count in README

**Issue:** README.md claims "400+ agent skills" but actual count is ~196 (138 Layer 2 + 58 Layer 3).

**Files:** `README.md:178`

**Impact:** Misleading user expectations about framework scope and capabilities.

**Fix approach:** Update README to reflect actual count: ~196 skills across 2 layers.

---

### Empty Stage Gates Directory

**Issue:** `docs/stage-gates/` is reserved and empty. Quality gate harness per pipeline stage was never implemented.

**Files:** `docs/stage-gates/` (directory)

**Impact:** No formal stage-specific quality gates exist beyond the generic reviewer meta skill. Each stage relies on `review_focus` in pipeline manifests, but there's no structured quality gate infrastructure.

**Fix approach:** Either:
1. Implement stage-gate system with enforcement rules, OR
2. Remove directory and consolidate quality gates into pipeline manifests + reviewer skill

---

### Empty Publishers Directory

**Issue:** `tools/publishers/` is a placeholder with no implementation.

**Files:** `tools/publishers/__init__.py` (empty)

**Impact:** Publishing functionality (to YouTube, social platforms, etc.) is not implemented. Pipelines cannot auto-publish rendered videos.

**Fix approach:** Define scope:
1. If planned: implement publisher tools (YouTube API, TikTok API, etc.)
2. If not planned: mark as future work in docs and remove from tool registry discovery

---

## Performance Bottlenecks

### Corpus Search Uses Linear Scan (No Vector Index)

**Issue:** Corpus search (`lib/corpus.py` → `rank_by_text()`, `knn()`) uses linear scan over all records. For large corpora (>1000 clips), this becomes slow.

**Files:** `lib/corpus.py` lines 247-315

**Current implementation:**
- `rank_by_text()`: Computes all similarities via `self.clip_embeddings @ query_vec` (O(N)), then sorts (O(N log N))
- `knn()`: Similar O(N) scan + sort

**Impact:** Documentary-montage pipeline with large stock-footage corpora will experience retrieval lag. Retrieval time grows linearly with corpus size.

**Scaling limit:** ~5000 clips still works, but >10,000 becomes noticeable.

**Fix approach:** Implement FAISS (Facebook AI Similarity Search) index:
1. Add `faiss` to dependencies in `tools/video/corpus_builder.py`
2. Build index on `clip_embeddings` at corpus save time
3. Use index for fast similarity search (O(log N) or O(1) depending on index type)
4. Keep JSONL for metadata lookup (no change to read path)

**Effort:** Medium. FAISS is well-tested; main work is integrating into existing load/save paths.

---

### Broad Exception Handling in Tool Implementations

**Issue:** 50+ instances of bare `except Exception:` across `tools/` without specific error classification or user-facing messaging.

**Files:** All `tools/` modules

**Examples:**
- `tools/graphics/image_gen.py:138-139` — catches all exceptions from generation, returns generic error message
- `tools/capture/screen_recorder.py:52` — audio device detection fails silently
- `tools/capture/cap_recorder.py:135` — process check fails silently

**Impact:** When tools fail, agents get generic "Generation failed: {e}" messages without distinguishing between auth errors, timeouts, rate limits, or actual bugs. This makes troubleshooting harder and prevents intelligent fallback.

**Fix approach:** Replace bare `except Exception:` with specific exception types:
- `except (AuthenticationError, PermissionError):` → auth issues
- `except (TimeoutError, ConnectionError):` → transient failures (retry)
- `except (ValueError, TypeError):` → input validation (don't retry)
- `except Exception:` → true bugs (log and fail)

---

## Fragile Areas

### Remotion Rendering Without Hardware Validation

**Issue:** `tools/video/video_compose.py` routes to Remotion for still-image composition and animated scenes, but doesn't validate Node.js or Remotion availability until render time.

**Files:** `tools/video/video_compose.py` → `_needs_remotion()`, `render()` operations

**Current behavior:** Preflight checks Remotion availability, but if Node.js or `remotion-composer/` is missing at render time, the entire compose stage fails after asset generation is complete.

**Fragility:** User approves proposal with Remotion-heavy treatment. Assets stage completes. Compose stage launches. Remotion is unavailable. Project is blocked with full cost spent.

**Per AGENT_GUIDE.md § "Critical Rule: Motion-Required Requests":**
> "If Remotion is unavailable, fails to render, or provider clip generation fails in a way that blocks the approved treatment, stop and tell the user before proceeding."

**Fix approach:**
1. Add explicit `validate_remotion_ready()` call in preflight, not just `check_availability()`
2. Test actual Remotion render (dry run) in preflight to catch Node.js or build issues early
3. Fail fast with actionable error: "Remotion not ready. Run: cd remotion-composer && npm install && npm run build"

---

### Checkpoint Resumption and Stage Validation Gaps

**Issue:** `lib/checkpoint.py` validates checkpoint JSON schema and canonical artifact presence, but doesn't validate:
1. Cross-stage artifact continuity (e.g., scene_plan referencing assets from a different project)
2. Timestamp ordering (e.g., edit stage checkpoint created before scene_plan checkpoint)
3. Artifact mutation detection (e.g., scene_plan changed but edit stage not invalidated)

**Files:** `lib/checkpoint.py:95-180` (validation section)

**Impact:** Manual checkpoint edits or corruption can cause silent data inconsistency. Resuming a pipeline with a stale edit stage that references a mutated scene_plan produces incorrect renders.

**Likelihood:** Low (checkpoints are write-once), but high-impact when it occurs.

**Fix approach:**
1. Add `validate_artifact_continuity()` — check that asset_manifest paths exist in the project directory
2. Add `validate_stage_sequence()` — ensure checkpoints exist in correct order with monotonic timestamps
3. Call both in `get_next_stage()` before resuming

---

### Error Handling in Provider Fallback Paths

**Issue:** Selector tools (`tts_selector`, `image_selector`, `video_selector`) route based on availability, but if the selected provider fails partway through (e.g., API key invalid at render time), there's no fallback to next-best provider.

**Files:**
- `tools/tts/tts_selector.py`
- `tools/image/image_selector.py`
- `tools/video/video_selector.py`

**Example scenario:**
1. Preflight: "OPENAI_API_KEY set, ElevenLabs TTS available"
2. Asset stage: Agent selects TTS via `tts_selector`
3. At runtime: OPENAI_API_KEY is valid but ElevenLabs API quota exhausted
4. TTS fails with "Quota exceeded"
5. No fallback to OpenAI (original selection path)

**Fix approach:** 
1. Implement `with_fallback()` wrapper in selectors
2. On provider failure, retry with next-best provider (by availability)
3. Log fallback decision for transparency

---

### Test Coverage for Video Reference Analysis

**Issue:** `skills/meta/video-reference-analyst.md` defines a first-class workflow for analyzing reference videos, but there are no tests covering this path.

**Files:** `tests/` — missing coverage for video-reference-analyst workflow

**Impact:** Breaking changes to reference analysis (e.g., transcript extraction, scene detection) won't be caught by test suite.

**Fix approach:** Add integration test in `tests/qa/` covering:
1. Load sample video reference
2. Run analysis workflow (transcript, frames, scenes)
3. Validate output artifact structure and content

---

## Beta Pipelines (Noted for User Awareness)

Per AGENT_GUIDE.md § "Available Pipelines", these pipelines have **not been fully audited** and should be presented to users with disclaimers:

**Files:**
- `pipeline_defs/talking-head.yaml` — Footage-led speaker videos
- `pipeline_defs/clip-factory.yaml` — Many clips from one long source
- `pipeline_defs/podcast-repurpose.yaml` — Podcast highlights and derivatives
- `pipeline_defs/localization-dub.yaml` — Subtitle, dub, and translated variants
- `pipeline_defs/documentary-montage.yaml` — Stock footage + research-driven montages
- `pipeline_defs/framework-smoke.yaml` — Test: minimal 2-stage smoke test

**Expected issues:** Rough edges, edge cases, potential undefined behavior in specific content types.

**Agent responsibility:** When user selects a beta pipeline, surface message: "This pipeline is still being refined. You might encounter rough edges. Let us know what breaks."

---

## Security Considerations

### Subprocess Calls Use Array Form (Safe)

**Issue:** None found.

**Analysis:** All subprocess calls in capture tools (`screen_recorder.py`, `cap_recorder.py`) use list form:
```python
subprocess.run(["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"])
```

This prevents shell injection attacks. ✓ No risk.

---

### API Key Handling (Secure)

**Issue:** None found.

**Analysis:** All API keys are read from environment variables only, never hardcoded or logged:
- `tools/video/minimax_video.py` — reads `MINIMAX_API_KEY` from os.environ
- `tools/video/kling_video.py` — reads `KLING_API_KEY` from os.environ
- `tools/video/grok_video.py` — reads `XAI_API_KEY` from os.environ

No secrets in version control. ✓ No risk.

---

### Path Handling in Asset Pipeline

**Issue:** None found.

**Analysis:** Asset paths are validated via:
1. `Path.mkdir(parents=True, exist_ok=True)` — safe directory creation
2. All paths rooted in `projects/<project_id>/` — no traversal
3. Artifact schema validates paths are relative (no absolute paths in artifacts)

✓ No path traversal risk.

---

## Missing Test Coverage

### End-to-End Tests Use Only FFmpeg Fixtures

**Issue:** `tests/qa/test_08_end_to_end.py` end-to-end tests use FFmpeg mock fixtures only. No actual Remotion rendering is tested.

**Files:** `tests/qa/test_08_end_to_end.py`

**Impact:** Remotion-specific failures (Node.js version, dependency resolution, build issues) won't be caught by CI.

**Fix approach:** Add E2E test that runs actual Remotion render (no API keys needed for `npx remotion render`):
1. Generate minimal scene_plan with one animated card
2. Call `video_compose` with `remotion_render` operation
3. Verify output.mp4 exists and has valid dimensions

---

## Dependency at Risk

### CLIP Embedder (transformers/torch) Large Download

**Issue:** `tools/video/corpus_builder.py` depends on `transformers` and `torch` for CLIP embedding. First download can be 5GB+ and may fail if network is unstable.

**Files:** `tools/video/corpus_builder.py:85-91` (dependencies)

**Impact:** Large corpus builds are fragile to network interruptions. Mid-build failure leaves partial corpus state.

**Likelihood:** Medium. Common in bandwidth-constrained environments.

**Fix approach:**
1. Add `--cache-dir` to transformers downloads (save to predictable location)
2. Implement checkpointing in `corpus_builder.execute()` — save corpus after every N clips
3. Detect partial corpus on load and resume from checkpoint

---

## Documentation Gaps

### Provider Pricing Not Current

**Issue:** `docs/PROVIDERS.md` exists but pricing information may be outdated (last updated before 2026-04-17).

**Files:** `docs/PROVIDERS.md`

**Risk:** Cost estimates in proposals become inaccurate if provider pricing changed.

**Fix approach:** Quarterly review of pricing for all configured providers (OpenAI, ElevenLabs, Replicate, fal.ai, Pexels, etc.). Update PROVIDERS.md and `cost_tracker.py` estimates.

---

### Screen Capture Tools Not Integrated Visibly

**Issue:** Four screen capture tools exist (`screen_recorder`, `cap_recorder`, `playwright_recording`, `synthetic_screen_recording`) but integration with `screen-demo` pipeline is not obvious.

**Files:**
- `tools/capture/screen_recorder.py`
- `tools/capture/cap_recorder.py`
- `tools/capture/playwright_recording.py`
- `.agents/skills/synthetic-screen-recording/` (Remotion-based)

**Missing documentation:** No clear decision tree in AGENT_GUIDE or skills on which tool to use when.

**Fix approach:** Add routing decision to `skills/pipelines/screen-demo/idea-director.md`:
- Real app UI (unpredictable) → `cap_recorder` (polished) or `screen_recorder` (basic)
- Terminal/CLI demo → `synthetic_screen_recording` (deterministic, faster)
- Browser flow → `playwright_recording` (scriptable)

---

## Summary of Severity

| Severity | Count | Examples |
|----------|-------|----------|
| **Critical (blocks development)** | 2 | Python version mismatch, FFmpeg missing |
| **High (blocks pipelines)** | 2 | Deprecated image_gen, skills sync gap |
| **Medium (production risk)** | 4 | Remotion validation, corpus scaling, broad exceptions, checkpoint gaps |
| **Low (nice-to-have)** | 6 | Publisher stub, test coverage, documentation |

**Recommended action priority:**
1. Resolve Python + FFmpeg (development blocker)
2. Sync skills and deprecate image_gen (code quality)
3. Add Remotion validation and corpus indexing (production stability)
4. Expand test coverage and fix exception handling (long-term)

---

*Concerns audit: 2026-04-17*
