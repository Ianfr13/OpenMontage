# External Integrations

**Analysis Date:** 2026-04-17

## APIs & External Services

**Image Generation:**
- FLUX (via fal.ai) - `tools/graphics/flux_image.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `FAL_KEY` or `FAL_AI_API_KEY` environment variable
  - Endpoint: fal.ai API gateway
  - Models: flux-pro/v1.1, flux/dev, flux-pro

- Google Imagen - `tools/graphics/google_imagen.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `GOOGLE_API_KEY` (dual-use with Google Cloud TTS)
  - Endpoint: aistudio.google.com API

- OpenAI DALL-E - `tools/graphics/openai_image.py`
  - SDK/Client: `openai` Python package
  - Auth: `OPENAI_API_KEY`
  - Endpoint: api.openai.com

- Grok Image/Edit (xAI) - `tools/graphics/grok_image.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `XAI_API_KEY`
  - Endpoint: xAI API

- Recraft - `tools/graphics/recraft_image.py`
  - SDK/Client: HTTP REST API
  - Auth: Environment variable based

**Video Generation:**
- Google Veo (via fal.ai) - `tools/video/veo_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `FAL_KEY` or `FAL_AI_API_KEY`
  - Endpoint: fal.ai video gateway
  - Quality tier: premium

- Kling (via fal.ai) - `tools/video/kling_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `FAL_KEY`
  - Endpoint: fal.ai routing to Kling backend
  - Models: kling-video/v1/standard, kling-video/v1/pro

- MiniMax - `tools/video/minimax_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `FAL_KEY`
  - Endpoint: fal.ai routing

- Hunyuan Video - `tools/video/hunyuan_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `FAL_KEY`
  - Endpoint: fal.ai gateway

- CogVideo - `tools/video/cogvideo_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `FAL_KEY` (via fal.ai routing)

- WAN 2.1 Video - `tools/video/wan_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `FAL_KEY`
  - Models: wan2.1-1.3b, wan2.1-14b (fal.ai routing)

- HeyGen (multi-provider gateway) - `tools/video/heygen_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `HEYGEN_API_KEY`
  - Endpoint: app.heygen.com/api
  - Supports: VEO 3.1, Sora, Runway Gen-4, Kling, Seedance (provider selection via single key)
  - Quality estimation: built-in cost/speed models

- Runway Gen-4 - `tools/video/runway_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `RUNWAY_API_KEY`
  - Endpoint: dev.runwayml.com API
  - Models: gen3a_turbo, gen4_turbo, gen4_aleph
  - Cost: $0.05/sec (turbo), $0.15/sec (aleph)

- Grok Video (xAI) - `tools/video/grok_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `XAI_API_KEY`
  - Endpoint: xAI video API

- Seedance - `tools/video/seedance_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `FAL_KEY`
  - Endpoint: fal.ai routing

- LTX-2 (Modal endpoint) - `tools/video/ltx_video_modal.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `MODAL_LTX2_ENDPOINT_URL` (self-hosted Modal endpoint)
  - Endpoint: custom Modal deployment

- LTX-2 (Local GPU) - `tools/video/ltx_video_local.py`
  - SDK/Client: Local diffusers library
  - Auth: None (local execution)
  - Requires: GPU, model download

**Text-to-Speech:**
- ElevenLabs - `tools/audio/elevenlabs_tts.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `ELEVENLABS_API_KEY` (header: `xi-api-key`)
  - Endpoint: api.elevenlabs.io/v1/text-to-speech/
  - Models: eleven_multilingual_v2 (default), eleven_turbo_v2
  - Voice settings: stability, similarity_boost, style
  - Cost: ~$0.0003 per character

- Google Cloud TTS - `tools/audio/google_tts.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `GOOGLE_API_KEY` (shared with Imagen)
  - Endpoint: Google Cloud TTS API
  - Languages: 50+ languages, 700+ voices

- OpenAI TTS - `tools/audio/openai_tts.py`
  - SDK/Client: `openai` Python package
  - Auth: `OPENAI_API_KEY`
  - Endpoint: api.openai.com
  - Models: tts-1 (fast), tts-1-hd (quality)

- Piper TTS - `tools/audio/piper_tts.py`
  - SDK/Client: Local `piper-tts` binary via subprocess
  - Auth: None (open source, local)
  - Runtime: LOCAL

**Music Generation:**
- Suno AI - `tools/audio/suno_music.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `SUNO_API_KEY`
  - Endpoint: sunoapi.org
  - Execution: ASYNC (polling-based)
  - Capabilities: full songs, instrumentals, vocals, custom lyrics

- Pixabay Music - `tools/audio/pixabay_music.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `PIXABAY_API_KEY`
  - Endpoint: pixabay.com/api/
  - Type: Stock royalty-free music

- Freesound (ElevenLabs) - `tools/audio/freesound_music.py`
  - SDK/Client: HTTP REST API
  - Auth: Environment variable based
  - Type: Stock SFX and music

- MusicGen - `tools/audio/music_gen.py`
  - SDK/Client: Conditional (local or API)
  - Type: Fallback music generation

**Stock Media Sources:**
- Pexels - `tools/video/pexels_video.py`, `tools/video/stock_sources/pexels.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `PEXELS_API_KEY` (free tier available)
  - Endpoint: api.pexels.com
  - Type: Stock footage and images

- Pixabay - `tools/video/pixabay_video.py`, `tools/video/stock_sources/pixabay_video.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `PIXABAY_API_KEY` (free tier)
  - Endpoint: pixabay.com/api/videos
  - Type: Stock footage and images

- Unsplash - `tools/video/stock_sources/unsplash.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `UNSPLASH_ACCESS_KEY` (free developer key)
  - Endpoint: api.unsplash.com
  - Type: Stock images

- NASA Public Archive - `tools/video/stock_sources/nasa.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: None required (public API)
  - Endpoint: images.nasa.gov API
  - Type: NASA imagery and footage

- Archive.org - `tools/video/stock_sources/archive_org.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: None required
  - Type: Public domain media

- Wikimedia Commons - `tools/video/stock_sources/wikimedia.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: None required
  - Type: Public domain media

- ESA (European Space Agency) - `tools/video/stock_sources/esa.py`
  - SDK/Client: HTTP REST API
  - Auth: None required
  - Type: Space and science imagery

- Library of Congress - `tools/video/stock_sources/loc.py`
  - SDK/Client: HTTP REST API
  - Auth: None required
  - Type: Public domain collections

- Coverr.co - `tools/video/stock_sources/coverr.py`
  - SDK/Client: HTTP REST API
  - Auth: Optional (free footage available)
  - Type: Stock video

- Mixkit - `tools/video/stock_sources/mixkit.py`
  - SDK/Client: HTTP REST API
  - Auth: Optional
  - Type: Stock footage and music

- VidEvo - `tools/video/stock_sources/videvo.py`
  - SDK/Client: HTTP REST API
  - Auth: Optional (freemium model)
  - Type: Stock video

- DAREFUL - `tools/video/stock_sources/dareful.py`
  - SDK/Client: HTTP REST API
  - Type: Stock footage

**Avatar & Lip-Sync:**
- HeyGen Avatar - `tools/avatar/talking_head.py`
  - SDK/Client: HTTP REST API via `requests`
  - Auth: `HEYGEN_API_KEY`
  - Endpoint: app.heygen.com API
  - Capabilities: talking head avatars from text or audio

- Wav2Lip (Local) - `tools/avatar/lip_sync.py`
  - SDK/Client: Local model via subprocess/inference
  - Auth: None (open source)
  - Path: `WAV2LIP_PATH` environment variable (optional, repo path)
  - Runtime: LOCAL_GPU
  - Capability: Lip-sync mouth movement matching audio

**Analysis & Understanding:**
- HuggingFace Models - `tools/analysis/transcriber.py`
  - Auth: `HF_TOKEN` (for speaker diarization in transcription)
  - Models: whisper (transcription), speaker diarization models
  - Type: Speech-to-text analysis

- Video Understanding - `tools/analysis/video_understand.py`
  - SDK/Client: Scene detection, frame analysis, visual QA
  - Type: Local analysis (no external API)

- Transcription Analysis - `tools/analysis/transcriber.py`
  - SDK/Client: OpenAI Whisper API (optional) or local models
  - Type: Speech-to-text

## Data Storage

**Databases:**
- None detected - No persistent database client (SQLAlchemy, Django ORM, etc.)
- State stored via: JSON artifacts in checkpoints, YAML manifests, local files

**File Storage:**
- Local filesystem only
  - Project directories: `projects/<project-name>/artifacts/`, `projects/<project-name>/assets/`
  - Clip cache: `~/.openmontage/clips_cache/` (LRU-evicted local cache for downloaded footage)
  - Music library: `music_library/` (user-provided royalty-free tracks)
  - Output: configured via `output_dir` in config.yaml

**Caching:**
- Clip Cache (`tools/video/clip_cache.py`) - In-memory + file-based LRU cache for downloaded stock clips
- No persistent Redis or Memcached integration
- Process-safe manifest lock (`cache_manifest.lock`) for concurrent access

## Authentication & Identity

**Auth Provider:**
- Custom: No unified auth provider
- Each tool manages its own API key from environment variables
- No user identity/account system in core framework

**Key Management:**
- Environment variables via `.env` file (loaded by `python-dotenv`)
- Keys never logged or stored in artifacts
- Support for multiple key formats: `FAL_KEY` / `FAL_AI_API_KEY` (interchangeable)

## Monitoring & Observability

**Error Tracking:**
- None detected - No Sentry, Datadog, or similar integration
- Error handling via `ToolResult` with `.error` and `.success` fields

**Logs:**
- stdout/stderr via Python logging module (in various tools)
- No centralized log aggregation
- Checkpoint system provides audit trail via `decision_log.json`

**Cost Tracking:**
- `tools/cost_tracker.py` - Cost estimation per tool call
- Budget governance: config.yaml `budget` section (total_usd, reserve_pct, single_action_approval_usd)
- Every tool implements `estimate_cost()` method

## CI/CD & Deployment

**Hosting:**
- Not applicable (CLI framework, no deployment service)
- Runs locally or via containerized devcontainer

**CI Pipeline:**
- GitHub Actions config (in `.github/`)
- Tests in `tests/` directory
- No external CI service integration detected

**Environment Configuration:**
- `.env` file (user-provided, not committed)
- `.env.example` - template with all available keys
- `config.yaml` - global OpenMontage configuration

## Webhooks & Callbacks

**Incoming:**
- None detected - OpenMontage is a CLI framework, not a service

**Outgoing:**
- Publisher tools (in `tools/publishers/`) - empty stub directory
- Potential future integration point for publishing to YouTube, social media, etc.

**Async Polling:**
- Suno Music uses async polling for job completion (`tools/audio/suno_music.py`)
- HeyGen video generation supports polling for async job status
- Modal LTX-2 endpoint supports long-running requests with polling

## Environment Configuration

**Required env vars (by capability):**
- **Image Generation:** `FAL_KEY` OR `GOOGLE_API_KEY` OR `OPENAI_API_KEY` OR `XAI_API_KEY`
- **Video Generation:** `FAL_KEY` OR `HEYGEN_API_KEY` OR `RUNWAY_API_KEY` OR (local GPU setup)
- **Text-to-Speech:** `ELEVENLABS_API_KEY` OR `GOOGLE_API_KEY` OR `OPENAI_API_KEY` (or local Piper)
- **Music:** `SUNO_API_KEY` OR free sources (Pixabay, Freesound, local music_library/)
- **Stock Media:** `PEXELS_API_KEY` OR `PIXABAY_API_KEY` OR `UNSPLASH_ACCESS_KEY` (all free tiers available)
- **Analysis:** `HF_TOKEN` (optional, for advanced transcription features)
- **Avatar:** `HEYGEN_API_KEY` (or local Wav2Lip setup)

**Secrets location:**
- `.env` file at project root (git-ignored, user-supplied)
- Never committed to repository
- Loaded by `tools/base_tool.py` at import time via `_load_dotenv()`

**Optional local installations:**
- `WAV2LIP_PATH` - Path to cloned Wav2Lip repo for local lip-sync
- `SADTALKER_PATH` - Path to cloned SadTalker repo for talking head (not yet integrated)
- `VIDEO_GEN_LOCAL_ENABLED` - Set to "true" to enable local video generation
- `VIDEO_GEN_LOCAL_MODEL` - Local model choice: wan2.1-1.3b, wan2.1-14b, hunyuan-1.5, ltx2-local, cogvideo-5b
- `MODAL_LTX2_ENDPOINT_URL` - Optional: Modal self-hosted LTX-2 endpoint for faster inference

## Tool Registry & Provider Selection

**Provider Discovery:**
- `tools/tool_registry.py` - Central registry that auto-discovers all `BaseTool` subclasses
- Selector pattern: `image_selector`, `video_selector`, `tts_selector` route to appropriate provider based on:
  1. User preference
  2. Availability (env var check)
  3. Fallback chain defined in each tool
- Example fallback chain (`tools/audio/elevenlabs_tts.py`):
  - Primary: ElevenLabs
  - Fallback: OpenAI TTS
  - Fallback: Piper (local)

**Support Envelope:**
- `registry.support_envelope()` - Reports all tools and their availability
- `registry.capability_catalog()` - Groups tools by capability (image_generation, video_generation, tts, etc.)
- `registry.provider_catalog()` - Groups tools by provider (elevenlabs, openai, fal, etc.)
- Each tool declares: capability, provider, runtime (LOCAL, API, LOCAL_GPU, HYBRID), status (AVAILABLE, UNAVAILABLE, DEGRADED)

---

*Integration audit: 2026-04-17*
