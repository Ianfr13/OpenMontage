# Technology Stack

**Analysis Date:** 2026-04-17

## Languages

**Primary:**
- Python 3.11.2 - Core orchestration, tool implementations, pipeline execution, artifact management
- TypeScript 5.3.0 - Remotion composition framework for animated video generation
- YAML - Pipeline manifest specifications, configuration, style playbooks

**Secondary:**
- Bash/Zsh - CLI operations, Docker configuration
- JSON - Artifact schemas, checkpoints, configuration

## Runtime

**Environment:**
- Python 3.11.2 (via system)
- Node.js 22.22.2 (LTS)
- npm 10.9.7 (Node package manager)
- FFmpeg (for local video composition and encoding)

**Package Manager:**
- Python: pip (with `requirements.txt` - `pyyaml>=6.0, pydantic>=2.0, jsonschema>=4.20, python-dotenv>=1.0, Pillow>=10.0, requests>=2.31`)
- Node.js: npm (via `remotion-composer/package.json`)
- Lockfiles: present

## Frameworks

**Core:**
- Remotion 4.0.441 - React-based composition renderer for animated video generation (`remotion-composer/` project)
- Pydantic 2.0+ - Schema validation and data modeling for artifacts and tool inputs
- PyYAML 6.0+ - Pipeline manifest parsing and configuration loading

**Rendering/Composition:**
- FFmpeg - Local video post-processing, encoding, subtitle burning, color grading
- Remotion Captions 4.0.441 - Subtitle rendering in video composition
- Remotion Transitions 4.0.441 - Animated scene transitions
- Remotion Media 4.0.441 - Media handling in compositions
- Remotion Google Fonts 4.0.441 - Font loading for text rendering
- React 18.2.0 - UI framework for Remotion components (inside `remotion-composer/`)

**Development:**
- Remotion CLI 4.0.441 - Build and render tool for compositions
- TypeScript 5.3.0 - Type checking for Remotion projects
- jsonschema 4.20+ - JSON schema validation for artifacts and checkpoints

## Key Dependencies

**Critical:**
- requests 2.31+ - HTTP client for all cloud API calls (ElevenLabs, FAL, HeyGen, Google, OpenAI, Runway, Suno, etc.)
- python-dotenv 1.0+ - Environment variable loading from `.env` file
- Pillow 10.0+ - Image processing (frame sampling, composition, enhancement)

**Infrastructure:**
- PyYAML 6.0+ - Pipeline manifest and configuration parsing
- Pydantic 2.0+ - Tool input/output schema validation, runtime type checking
- jsonschema 4.20+ - JSON schema validation for artifacts, checkpoints, pipelines

**Optional/Conditional:**
- openai (when OPENAI_API_KEY set) - OpenAI TTS and DALL-E image generation
- (No SQLAlchemy, Django ORM, or persistent database client in core stack)

## Configuration

**Environment:**
- Loaded via `python-dotenv` from `.env` file (`.env.example` provided)
- API keys stored as environment variables: `ELEVENLABS_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `FAL_KEY`, `HEYGEN_API_KEY`, `RUNWAY_API_KEY`, `SUNO_API_KEY`, `XAI_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `UNSPLASH_ACCESS_KEY`, `HF_TOKEN`, `MODAL_LTX2_ENDPOINT_URL`
- Local overrides for GPU/model selection: `VIDEO_GEN_LOCAL_ENABLED`, `VIDEO_GEN_LOCAL_MODEL`

**Build:**
- `config.yaml` - Global OpenMontage configuration (LLM provider, budget limits, checkpoint policy, output codec, path resolution)
- `lib/config_model.py` - Pydantic config model with typed validation
- Pipeline manifests: `pipeline_defs/*.yaml` - YAML specifications for each production pipeline (animated-explainer, talking-head, screen-demo, cinematic, avatar-spokesperson, etc.)
- Style playbooks: `styles/*.yaml` - Validated style definitions for visual consistency

## Platform Requirements

**Development:**
- Linux-based environment (devcontainer via `.devcontainer/`)
- Python 3.11+
- Node.js 22+
- FFmpeg installed on system
- Git for version control

**Production/Execution:**
- Python 3.11+ runtime
- Node.js 22+ (for Remotion rendering)
- FFmpeg binary
- Network access to cloud APIs (for providers: fal.ai, ElevenLabs, HeyGen, Google, OpenAI, Runway, Suno, etc.)
- GPU optional (for local video generation models: WAN 2.1, Hunyuan, LTX-2, CogVideo)

---

*Stack analysis: 2026-04-17*
