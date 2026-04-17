# Codebase Structure

**Analysis Date:** 2026-04-17

## Directory Layout

```
/workspace
├── .agents/                           # Layer 3: 47 external technology skills
│   └── skills/                        # Vendor & technology knowledge (ffmpeg, elevenlabs, remotion, gsap, threejs, etc.)
│
├── .planning/                         # GSD planning and analysis documents
│   └── codebase/                      # This analysis (ARCHITECTURE.md, STRUCTURE.md, etc.)
│
├── .specs/                            # Feature specifications and research outputs
│   └── current/                       # Active spec files
│
├── .cursor/                           # Cursor IDE configuration
│   └── rules/                         # Custom IDE rules
│
├── docs/                              # Architecture guides and best practices
│   ├── ARCHITECTURE.md                # Comprehensive system design
│   └── stage-gates/                   # Stage-specific governance docs
│
├── lib/                               # Core runtime infrastructure (Python)
│   ├── base_tool.py                   # (in tools/) Abstract base class for all tools
│   ├── checkpoint.py                  # Checkpoint write/read, stage transitions
│   ├── pipeline_loader.py             # YAML manifest loading + validation
│   ├── config_model.py                # Pydantic runtime config (LLM, budget, output, paths)
│   ├── cost_tracker.py                # (in tools/) Budget governance, estimate/reserve/reconcile
│   ├── media_profiles.py              # Platform-specific render profiles (YouTube, TikTok)
│   ├── clip_embedder.py               # Vector embedding for clip search/matching
│   ├── corpus.py                      # Research corpus management
│   ├── source_media_review.py         # User-provided source footage analysis
│   ├── playbook_generator.py          # Style playbook auto-generation
│   ├── scoring.py                     # Quality scoring, variation detection
│   ├── shot_prompt_builder.py         # Shot-level prompt construction for video gen
│   ├── slideshow_risk.py              # Assess Ken Burns fallback risk
│   ├── variation_checker.py           # Detect visual/narrative consistency
│   ├── verify_scene_pacing.py         # Timing validation across scenes
│   ├── env_loader.py                  # .env file parsing
│   ├── delivery_promise.py            # Media delivery guarantees
│   └── providers/                     # (Reserved for future provider abstractions)
│
├── pipeline_defs/                     # 12 YAML pipeline manifests (declaring stages, tools, approval gates)
│   ├── animated-explainer.yaml        # AI-generated explainer (research → script → assets → edit → compose)
│   ├── animation.yaml                 # Animation-first pipeline
│   ├── avatar-spokesperson.yaml       # Avatar presenter/lip-sync
│   ├── cinematic.yaml                 # Trailer/teaser cinematic edit
│   ├── clip-factory.yaml              # Many clips from one source
│   ├── documentary-montage.yaml       # Documentary-style montage
│   ├── hybrid.yaml                    # Source footage + support visuals
│   ├── localization-dub.yaml          # Subtitle/dub/localization
│   ├── podcast-repurpose.yaml         # Podcast highlights
│   ├── screen-demo.yaml               # Screen recording + synthetic terminal
│   ├── talking-head.yaml              # Footage-led speaker video
│   └── framework-smoke.yaml           # Test harness (minimal 2-stage pipeline)
│
├── remotion-composer/                 # Node.js/React Remotion video renderer
│   ├── src/
│   │   ├── index.tsx                  # Main entry, scene router
│   │   ├── CinematicRenderer.tsx       # Cinematic composition wrapper
│   │   └── components/
│   │       ├── TextCard.tsx           # Text + animation
│   │       ├── StatCard.tsx           # Stat display with counter animation
│   │       ├── CalloutBox.tsx         # Highlighted callout
│   │       ├── ComparisonCard.tsx     # Side-by-side comparison
│   │       ├── ProgressBar.tsx        # Progress/timeline display
│   │       ├── HeroTitle.tsx          # Large title scene
│   │       ├── SectionTitle.tsx       # Section header overlay
│   │       ├── TerminalScene.tsx      # Synthetic CLI/terminal demo
│   │       ├── AnimeScene.tsx         # Anime/manga-style animation
│   │       ├── EndTag.tsx             # Outro/branding card
│   │       ├── ProviderChip.tsx       # Provider/badge overlay
│   │       ├── StatReveal.tsx         # Stat reveal animation
│   │       ├── ProductReveal.tsx      # Product showcase animation
│   │       ├── CaptionOverlay.tsx     # Subtitle/caption burn
│   │       ├── ParticleOverlay.tsx    # Particle effects
│   │       ├── charts/                # Chart components (BarChart, LineChart, PieChart, KPIGrid)
│   │       ├── backgrounds/           # Background components (GradientBackground, GridBackground)
│   │       └── animations/            # Animation primitives (SlideIn, FadeIn, etc.)
│   ├── package.json                   # Node.js dependencies (remotion, react, vite)
│   ├── remotion.config.ts             # Remotion render config
│   └── SCENE_TYPES.md                 # Scene type reference + cut schemas
│
├── schemas/                           # JSON Schema definitions for validation
│   ├── artifacts/                     # 11 artifact schemas (validated at checkpoint write)
│   │   ├── brief.schema.json          # Idea stage: topic, hook, duration, tone, platform
│   │   ├── script.schema.json         # Script stage: narration, timing, shot descriptions
│   │   ├── scene_plan.schema.json     # Scene plan: ordered scenes, assets, timings
│   │   ├── asset_manifest.schema.json # Assets stage: image/video/audio paths + metadata
│   │   ├── edit_decisions.schema.json # Edit stage: cuts, overlays, transitions
│   │   ├── render_report.schema.json  # Compose stage: output paths, codec, verification
│   │   ├── proposal_packet.schema.json # Proposal stage: concepts, cost, tool plan
│   │   ├── research_brief.schema.json # Research stage: findings, references
│   │   ├── publish_log.schema.json    # Publish stage: delivery, URLs, metadata
│   │   ├── final_review.schema.json   # Optional final review before delivery
│   │   ├── source_media_review.schema.json # User source footage analysis
│   │   └── video_analysis_brief.schema.json # Reference video grounding
│   ├── checkpoints/
│   │   └── checkpoint.schema.json     # Checkpoint state: stage, status, artifacts, cost
│   ├── pipelines/
│   │   └── pipeline_manifest.schema.json # Pipeline manifest: name, stages, tools, approval
│   ├── styles/
│   │   └── playbook.schema.json       # Style playbook: colors, type, motion, constraints
│   └── tools/
│       └── video_stitch.schema.json   # video_stitch input schema (clips, transitions)
│
├── skills/                            # Layer 2: OpenMontage-specific instructions
│   ├── INDEX.md                       # Skill index + knowledge architecture (read first)
│   ├── core/                          # Core technology skills
│   │   ├── ffmpeg.md                  # FFmpeg encoding, filtering, composition
│   │   ├── remotion.md                # Remotion scene types, animation, composition
│   │   ├── whisperx.md                # WhisperX transcription with word timing
│   │   ├── subtitle-sync.md           # Subtitle alignment and timing
│   │   └── color-grading.md           # FFmpeg color profiles, LUT, accessibility
│   ├── creative/                      # Creative workflow skills
│   │   ├── video-editing.md           # Cut decisions, pacing, rhythm
│   │   ├── enhancement-strategy.md    # Overlay placement, density, timing
│   │   ├── data-visualization.md      # Chart selection, animation, labeling
│   │   ├── video-stitching.md         # Multi-clip assembly, spatial composition
│   │   ├── video-gen-prompting.md     # Universal video generation prompt structure
│   │   ├── storytelling.md            # Narrative structure, hooks, pacing
│   │   └── prompting/                 # Provider-specific video gen prompting
│   │       ├── grok-prompting.md      # Grok image/video prompting
│   │       ├── sora-prompting.md      # Sora 2 structured template
│   │       ├── veo-prompting.md       # VEO 3.1 14-component structure
│   │       ├── ltx-prompting.md       # LTX-2 6-element structure
│   │       └── hunyuan-prompting.md   # HunyuanVideo formula + I2V
│   ├── meta/                          # Cross-cutting meta skills
│   │   ├── reviewer.md                # Self-review protocol, quality gates, re-iteration
│   │   ├── checkpoint-protocol.md     # When to pause, human approval gates
│   │   ├── onboarding.md              # First-time user discovery + capability audit
│   │   ├── video-reference-analyst.md # Reference video analysis workflow
│   │   ├── animation-runtime-selector.md # Route between Remotion, GSAP, Lottie, Manim, D3
│   │   ├── creative-intake.md         # User request classification
│   │   ├── capability-extension.md    # Adding new tools/skills
│   │   └── skill-creator.md           # Creating new skills
│   └── pipelines/                     # Per-pipeline stage directors
│       ├── animated-explainer/        # animated-explainer pipeline skills
│       │   ├── executive-producer.md  # Production orchestration
│       │   ├── research-director.md   # Research stage
│       │   ├── proposal-director.md   # Proposal & cost estimation
│       │   ├── script-director.md     # Script writing
│       │   ├── scene-director.md      # Scene planning
│       │   ├── asset-director.md      # Image, video, audio generation
│       │   ├── edit-director.md       # Editing & composition
│       │   ├── compose-director.md    # Final rendering
│       │   └── publish-director.md    # Delivery & archival
│       ├── animation/ ├── avatar-spokesperson/ ├── cinematic/ ├── clip-factory/
│       ├── documentary-montage/ ├── hybrid/ ├── localization-dub/
│       ├── podcast-repurpose/ ├── screen-demo/ └── talking-head/
│       (each with same 7-9 director skills)
│
├── styles/                            # Style playbooks (YAML) + loader
│   ├── clean-professional.yaml        # Corporate, educational, SaaS aesthetic
│   ├── flat-motion-graphics.yaml      # Social media, TikTok, startup aesthetic
│   ├── minimalist-diagram.yaml        # Technical deep-dives, architecture
│   └── playbook_loader.py             # Load, validate, apply playbook design tokens
│
├── tests/                             # Test suite (contract, QA, eval)
│   ├── contracts/                     # Tool contract tests, artifact validation
│   ├── pipelines/                     # Pipeline execution tests
│   ├── qa/                            # Quality assurance test harness
│   ├── tools/                         # Tool-by-tool output inspection
│   ├── styles/                        # Playbook validation
│   └── eval/                          # Evaluation harness for model outputs
│
├── tools/                             # Layer 1: 78 production tools (Python)
│   ├── base_tool.py                   # Abstract base class (ToolContract)
│   ├── tool_registry.py               # Auto-discovery registry + reporting
│   ├── cost_tracker.py                # Budget governance
│   ├── audio/                         # TTS, music, mixing (15+ tools)
│   │   ├── tts_selector.py            # Routes to ElevenLabs, OpenAI, Google, Piper
│   │   ├── elevenlabs_tts.py          # ElevenLabs TTS
│   │   ├── openai_tts.py              # OpenAI TTS
│   │   ├── google_tts.py              # Google Cloud TTS
│   │   ├── piper_tts.py               # Local Piper TTS
│   │   ├── music_gen.py               # Music generation
│   │   ├── audio_mixer.py             # FFmpeg-based audio mixing
│   │   ├── audio_enhance.py           # Audio normalization, EQ
│   │   └── sound_effects_gen.py       # SFX generation
│   ├── avatar/                        # Talking head, lip-sync (3+ tools)
│   │   ├── heygen_video.py            # HeyGen lip-sync
│   │   ├── talking_head_animator.py   # Local talking head animation
│   │   └── avatar_selector.py         # Routes to best avatar provider
│   ├── analysis/                      # Transcription, scene detection, understanding (6+ tools)
│   │   ├── transcriber.py             # WhisperX + Whisper variants
│   │   ├── scene_detect.py            # Scene boundary detection
│   │   ├── frame_sampler.py           # Extract frames at timestamps
│   │   ├── video_analyzer.py          # Video metadata, resolution, duration
│   │   ├── transcript_fetcher.py      # Fetch transcripts from URLs
│   │   └── video_downloader.py        # Download video from URL
│   ├── capture/                       # Screen recording (3+ tools)
│   │   ├── screen_recorder.py         # OS-level screen capture
│   │   ├── cap_recorder.py            # Alternative capture tool
│   │   └── screen_capture_selector.py # Routes to best recorder
│   ├── enhancement/                   # Upscale, bg removal, face restore (5+ tools)
│   │   ├── upscaler.py                # Image/video upscaling
│   │   ├── bg_remover.py              # Background removal
│   │   ├── face_enhance.py            # Face restoration + beauty
│   │   ├── face_swap.py               # Face replacement
│   │   └── color_grader.py            # Color correction + LUT application
│   ├── graphics/                      # Image generation, diagrams, code snippets (8+ tools)
│   │   ├── image_selector.py          # Routes to FLUX, DALL-E, Recraft, Google, local diffusion
│   │   ├── flux_image.py              # FLUX image generation
│   │   ├── dalle_image.py             # DALL-E 3 image generation
│   │   ├── recraft_image.py           # Recraft.ai image generation
│   │   ├── google_imagen.py           # Google Imagen image generation
│   │   ├── local_diffusion.py         # Local Stable Diffusion (GPU)
│   │   ├── diagram_gen.py             # Mermaid/Graphviz diagrams
│   │   ├── code_snippet_gen.py        # Syntax-highlighted code visualization
│   │   └── math_animator.py           # Manim math animation
│   ├── publishers/                    # Publishing targets (reserved)
│   ├── subtitle/                      # SRT/VTT generation (2+ tools)
│   │   ├── subtitle_gen.py            # Generate SRT from timestamps
│   │   └── subtitle_burner.py         # Burn subtitles into video
│   ├── video/                         # Video generation, composition, post (25+ tools)
│   │   ├── video_selector.py          # Routes to 13 video gen providers
│   │   ├── heygen_video.py            # HeyGen avatar video
│   │   ├── kling_video.py             # Kling video generation (Kuaishou)
│   │   ├── ltx_video_local.py         # LTX-2 local (requires GPU)
│   │   ├── ltx_video_modal.py         # LTX-2 via Modal GPU cloud
│   │   ├── cogvideo_video.py          # CogVideo generation
│   │   ├── veo_video.py               # Google VEO video generation
│   │   ├── wan_video.py               # Wan video generation
│   │   ├── hunyuan_video.py           # HunyuanVideo generation
│   │   ├── minimax_video.py           # MiniMax video
│   │   ├── grok_video.py              # Grok video generation
│   │   ├── pixabay_video.py           # Stock footage from Pixabay
│   │   ├── pexels_video.py            # Stock footage from Pexels
│   │   ├── video_compose.py           # FFmpeg/Remotion composition (final render)
│   │   ├── video_stitch.py            # Multi-clip assembly + spatial composition
│   │   ├── video_trimmer.py           # Clip trimming
│   │   ├── auto_reframe.py            # Aspect ratio adaptation (vertical/horizontal)
│   │   ├── remotion_caption_burn.py   # Remotion subtitle/caption burn
│   │   ├── green_screen_composite.py  # Green screen keying + compositing
│   │   ├── green_screen_processor.py  # Green screen preprocessing
│   │   ├── clip_cache.py              # Clip cache management
│   │   └── clip_search.py             # Semantic clip search
│   └── __init__.py                    # Package exports (empty)
│
├── .gitignore                         # Git ignore rules (projects/, output/, .env)
├── AGENT_GUIDE.md                     # Mandatory agent contract (read first before any user request)
├── AGENTS.md                          # List of supported agent platforms (Claude, Cursor, Copilot)
├── CLAUDE.md                          # Claude-specific agent instructions (points to AGENT_GUIDE.md)
├── CODEX.md                           # Codex agent platform config
├── COPILOT.md                         # GitHub Copilot agent config
├── CURSOR.md                          # Cursor IDE agent config
├── CONTEXT.md                         # User-specific context and memory
├── PROJECT_CONTEXT.md                 # Shared project context (architecture, key files, patterns)
├── PROMPT_GALLERY.md                  # Example production prompts and workflows
├── README.md                          # Project overview and quick-start
├── TODO.md                            # Backlog of features and fixes
├── config.yaml                        # Global runtime config (LLM, budget, checkpoint, output, paths)
├── Makefile                           # Development commands (test, lint, render)
├── render-demo.sh                     # Demo rendering script (shell)
├── render_demo.py                     # Demo rendering (Python)
└── diagram.png                        # Architecture diagram
```

---

## Directory Purposes

**`.agents/skills/`**
- Purpose: Layer 3 external technology skills (vendor APIs, frameworks, libraries)
- Contains: 47 directories of vendor-specific knowledge (ffmpeg, elevenlabs, remotion, gsap-core through gsap-utils, three.js, Manim, D3, etc.)
- Read when: Layer 2 skill references it via `agent_skills[]` field; before calling any generation tool

**`lib/`**
- Purpose: Core Python runtime infrastructure
- Contains: Checkpoint management, config loading, pipeline manifest loading, cost tracking, media profiles, research corpus, playbook generation
- Key files: `checkpoint.py` (persistence), `pipeline_loader.py` (manifest loading), `config_model.py` (Pydantic config), `cost_tracker.py` (budget)

**`pipeline_defs/`**
- Purpose: Declarative pipeline manifests in YAML
- Contains: 12 pipelines defining stages, tools, approval gates, review focus, compatible playbooks
- Structure: Each file is a pipeline; stages list directors, produced artifacts, required/fallback tools
- Example: `animated-explainer.yaml` declares 9 stages (research through publish) with executive-producer orchestration

**`remotion-composer/`**
- Purpose: Node.js/React runtime for Remotion video composition
- Contains: Scene components (TextCard, StatCard, TerminalScene, etc.), chart components, background components, animation primitives
- Entry: `src/index.tsx` routes to scene types via `cut.type` field
- Invoked by: `video_compose` tool when rendering motion-graphics or animated sequences
- Not in `.gitignore`: Committed to repo; part of production runtime

**`schemas/`**
- Purpose: JSON Schema validation for artifacts, checkpoints, pipelines, styles, tools
- Subdir: `artifacts/` (11 schemas for canonical outputs), `checkpoints/` (state), `pipelines/` (manifest), `styles/` (playbook), `tools/` (tool I/O)
- Validation: Enforced at checkpoint write and pipeline load time

**`skills/`**
- Purpose: Layer 2 OpenMontage-specific instructions (how to use tools in pipelines)
- Subdirs: `core/` (FFmpeg, Remotion, WhisperX, color grading), `creative/` (editing, enhancement, visualization, prompting), `meta/` (reviewer, checkpoint-protocol, onboarding), `pipelines/` (per-pipeline stage directors)
- Reading order: Agent reads INDEX.md first, then pipeline manifest, then per-stage director skills, then Layer 3 skills for tool guidance

**`styles/`**
- Purpose: Visual style playbooks and loader
- Contains: clean-professional.yaml, flat-motion-graphics.yaml, minimalist-diagram.yaml (color, type, motion, asset constraints)
- Loader: `playbook_loader.py` validates against `schemas/styles/playbook.schema.json` and applies tokens to asset generation

**`tests/`**
- Purpose: Contract tests, QA validation, evaluation harness
- Subdirs: `contracts/` (tool contract tests), `pipelines/` (pipeline execution tests), `qa/` (quality validation), `tools/` (per-tool output inspection), `styles/` (playbook validation), `eval/` (model eval)

**`tools/`**
- Purpose: Layer 1 production tools (78 Python classes inheriting from BaseTool)
- Subdirs: `audio/` (TTS, music, mixing), `avatar/` (talking head, lip-sync), `analysis/` (transcription, scene detection), `capture/` (screen recording), `enhancement/` (upscale, bg removal), `graphics/` (image gen, diagrams), `video/` (13 video gen providers + composition + post)
- Registry: `tool_registry.py` auto-discovers all subclasses; no manual registration

---

## Key File Locations

**Entry Points:**
- `AGENT_GUIDE.md` — **Mandatory read before ANY user request**; defines contract, protocols, rules
- `PROJECT_CONTEXT.md` — Shared architecture, key files, when building pipelines/tools
- `skills/INDEX.md` — Skill index + knowledge architecture reference

**Configuration:**
- `config.yaml` — Global runtime config (LLM, budget, checkpoint, output, paths)
- `.env` — Environment variables for API keys (not in git; example at `.env.example`)
- `pipeline_defs/<pipeline>.yaml` — Per-pipeline manifest and stage config

**Core Logic:**
- `tools/base_tool.py` — Abstract base class for all tools (contracts, execution interface)
- `tools/tool_registry.py` — Auto-discovery registry; query with `.get_by_capability()`, `.support_envelope()`, etc.
- `lib/checkpoint.py` — Checkpoint persistence and stage transitions
- `lib/pipeline_loader.py` — Pipeline manifest loading + validation

**Testing:**
- `tests/contracts/` — Tool contract tests
- `tests/qa/` — Quality validation test harness

---

## Naming Conventions

**Files:**
- Tools: `snake_case.py` (e.g., `elevenlabs_tts.py`, `flux_image.py`, `video_compose.py`)
- Skills: `kebab-case.md` (e.g., `video-editing.md`, `animation-runtime-selector.md`, `idea-director.md`)
- Pipelines: `kebab-case.yaml` (e.g., `animated-explainer.yaml`, `screen-demo.yaml`)
- Schemas: `snake_case.schema.json` (e.g., `brief.schema.json`, `checkpoint.schema.json`)
- Playbooks: `kebab-case.yaml` (e.g., `clean-professional.yaml`, `flat-motion-graphics.yaml`)

**Directories:**
- Tool families: `snake_case` (e.g., `tools/audio/`, `tools/graphics/`, `tools/video/`)
- Pipeline skill dirs: `kebab-case` matching pipeline name (e.g., `skills/pipelines/animated-explainer/`)
- Layer 3 skill dirs: `kebab-case` or `snake_case` matching technology (e.g., `.agents/skills/ffmpeg/`, `.agents/skills/gsap-core/`)

**Classes (Python):**
- Tools: PascalCase without "Tool" suffix (e.g., `ElevenLabsTTS`, `FluxImage`, `VideoCompose`)
- Use: `from tools.audio.elevenlabs_tts import ElevenLabsTTS` → `tool = ElevenLabsTTS()`
- Enums: PascalCase (e.g., `ToolTier`, `ToolStatus`, `ToolRuntime`)
- Config classes: PascalCase (e.g., `OpenMontageConfig`, `BudgetConfig`, `CheckpointConfig`)

**Artifacts (JSON):**
- Names: `snake_case` matching CANONICAL_STAGE_ARTIFACTS (e.g., `brief.json`, `script.json`, `asset_manifest.json`)
- Path: `pipeline/<project_id>/artifacts/<stage>_<artifact_name>.json` or in checkpoint

---

## Where to Add New Code

**New Video Generation Provider Tool:**
1. Create `tools/video/<provider>_video.py`
2. Import `from tools.base_tool import BaseTool`
3. Declare class `ProviderVideo(BaseTool)` with:
   - `capability = "video_generation"`
   - `provider = "<provider_name>"`
   - `agent_skills = ["ai-video-gen"]` (or provider-specific skill)
   - `execute()` method returning `ToolResult`
4. Register: Automatic via `tool_registry.discover()` — no changes to registry needed
5. Selector: `video_selector` auto-discovers it; no selector code changes needed

**New TTS Provider Tool:**
1. Create `tools/audio/<provider>_tts.py`
2. Declare class `ProviderTTS(BaseTool)` with:
   - `capability = "tts"`
   - `provider = "<provider_name>"`
   - `agent_skills = ["text-to-speech"]` (or provider-specific)
3. Auto-discovered by `tts_selector` — no selector changes

**New Pipeline:**
1. Create `pipeline_defs/<name>.yaml` with stages, tools, approval gates
2. Validate against `schemas/pipelines/pipeline_manifest.schema.json`
3. Create `skills/pipelines/<name>/` with 7-9 director skills:
   - `research-director.md` (if research stage)
   - `proposal-director.md` (if proposal stage)
   - `script-director.md` (if script stage)
   - `scene-director.md` (if scene planning stage)
   - `asset-director.md` (if asset generation stage)
   - `edit-director.md` (if edit stage)
   - `compose-director.md` (if compose stage)
   - `publish-director.md` (if publish stage)
   - `executive-producer.md` (optional orchestration skill)
4. Add to `skills/INDEX.md` pipeline table
5. Reference meta skills: `meta/reviewer.md`, `meta/checkpoint-protocol.md`

**New Stage Artifact:**
1. Define JSON Schema in `schemas/artifacts/<artifact_name>.schema.json`
2. Add entry to `CANONICAL_STAGE_ARTIFACTS` in `lib/checkpoint.py`
3. Agent will validate at checkpoint write time

**New Playbook:**
1. Create `styles/<name>.yaml` declaring design tokens (colors, type, motion, constraints)
2. Validate against `schemas/styles/playbook.schema.json`
3. Add to compatible playbooks in pipeline manifests
4. Loader reads automatically; no code changes to `playbook_loader.py` needed

**New Analysis / Utility Library:**
1. Create `lib/<name>.py` for cross-pipeline utilities
2. Example: `lib/corpus.py` (research management), `lib/source_media_review.py` (user footage analysis), `lib/scoring.py` (quality metrics)
3. Import in skills or tools as needed

**New Agent Skill (Layer 2):**
1. Create `skills/<category>/<name>.md` or `skills/pipelines/<pipeline>/<stage>-director.md`
2. Write Markdown with structured sections: overview, when to use, workflow, quality gates, examples
3. Reference Layer 3 skills in text (e.g., "See `.agents/skills/ffmpeg/` for filtering options")
4. Link in pipeline manifest's `required_skills` if needed

**New Technology Skill (Layer 3):**
1. Created via `.agents/skills/` (external, managed by `skills.sh`)
2. Can be imported and referenced in Layer 2 skills
3. Contains vendor API docs, code patterns, constraints, parameters

---

## Special Directories

**`projects/`** (Created at pipeline init)
- Purpose: Generated assets and artifacts for a production run
- Created by: Agent at pipeline initialization
- Contents: `artifacts/` (JSON artifacts), `assets/` (images, video, audio), `renders/` (final video)
- Committed: NO — gitignored, all outputs are regenerable
- Structure:
  ```
  projects/<project_name>/
  ├── artifacts/
  │   ├── brief.json
  │   ├── script.json
  │   ├── scene_plan.json
  │   ├── asset_manifest.json
  │   ├── edit_decisions.json
  │   └── render_report.json
  ├── assets/
  │   ├── images/
  │   ├── video/
  │   ├── audio/
  │   └── music/
  └── renders/
      └── final.mp4
  ```

**`music_library/`** (Optional, user-provided)
- Purpose: Royalty-free music tracks for asset director
- Created by: User
- Contents: `.mp3` files (track names become options in proposal + asset stage)
- Committed: NO — gitignored
- Used by: Asset director checks before falling back to music generation API

**`.env`** (Secrets, not in git)
- Purpose: API keys and configuration
- Location: Project root (not tracked)
- Example: `.env.example` in repo
- Loaded by: `tools/base_tool.py` and `tools/tool_registry.py` at import time
- Tools check env vars at instantiation; report `UNAVAILABLE` if missing

**`output/`** (Generated videos, not in git)
- Purpose: Final rendered videos and exports
- Created by: Render/publish stages
- Committed: NO — gitignored

---

*Structure analysis: 2026-04-17*
