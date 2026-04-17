# OpenMontage — Context

Sistema de produção de vídeo dirigido por instruções. O agente de IA é a inteligência — lê manifestos YAML e skills MD para orquestrar ferramentas Python. Sem lógica de orquestração em Python.

**Para instruções de routing:** `AGENT_GUIDE.md`  
**Para arquitetura técnica:** `docs/ARCHITECTURE.md`  
**Para setup de providers:** `docs/PROVIDERS.md`  
**Para leis arquiteturais:** `.specs/constitution.md`

---

## Mapa de Workspaces

### `tools/` — Ferramentas de Produção
109 ferramentas Python em 9 famílias. Toda ferramenta herda de `BaseTool` (`tools/base_tool.py`).

| Família | Ferramentas | Skills Layer 3 |
|---------|-------------|----------------|
| `analysis/` | Transcrição, detecção de cena, frame sampling, face tracking | `speech-to-text`, `video-understand` |
| `audio/` | TTS selector + 4 providers, music gen, mixer | `elevenlabs`, `music`, `sound-effects`, `text-to-speech` |
| `avatar/` | Lip sync, talking head | `avatar-video`, `heygen`, `faceswap` |
| `capture/` | Screen recording | `playwright-recording`, `synthetic-screen-recording` |
| `enhancement/` | Upscale, face restore, remoção de fundo, color grade | `video-edit` |
| `graphics/` | Image gen (Flux, DALL-E, Grok, Recraft), diagramas | `bfl-api`, `flux-best-practices`, `ai-video-gen` |
| `subtitle/` | Geração de legenda | — |
| `video/` | Video gen (15+ providers), compose, stitch, trim | `ai-video-gen`, `ltx2`, `ffmpeg` |

**Registry:** `tools/tool_registry.py` — auto-descoberta via herança. Nunca hardcodar listas.  
**Seletores:** `tts_selector`, `image_selector`, `video_selector` — roteiam para provedores disponíveis automaticamente.

#### tools/analysis/ — Video Analysis Providers (v2.0)

| Tool | Capability | Provider | Auth / Config | Notes |
|------|-----------|----------|---------------|-------|
| `video_analyzer_selector` | `video_analysis` | `selector` | Auto-discovery via registry; routed by `VIDEO_ANALYZER_PROVIDER` env | Never return raw provider directly; preference: explicit > env > first key present > first AVAILABLE |
| `gemini_video_analyzer` | `video_analysis` | `gemini` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY` fallback); model via `GEMINI_VIDEO_MODEL` | google-genai SDK; Files API upload + poll ACTIVE + auto-delete |
| `openrouter_video_analyzer` | `video_analysis` | `openrouter` | `OPENROUTER_API_KEY`; model via `OPENROUTER_MODEL` | openai>=1.0 SDK, base_url=openrouter.ai/api/v1; base64 inline; rejects >max_upload_bytes |

**Layer 3 skills:** `.agents/skills/gemini-video-analysis/`, `.agents/skills/openrouter-video-analysis/`

---

### `pipeline_defs/` — Manifestos de Pipeline
12 YAMLs declarativos. Cada um define estágios, ferramentas, gates de aprovação humana e review focus.

| Pipeline | Melhor para | Estabilidade |
|----------|-------------|-------------|
| `animated-explainer` | Tópico → explainer gerado | production |
| `animation` | Multi-imagem → vídeo com movimento | production |
| `cinematic` | Trailer/teaser mood-driven | production |
| `avatar-spokesperson` | Avatar com script | production |
| `hybrid` | Footage do usuário + visuais gerados | production |
| `screen-demo` | Demos de tela/walkthrough | production |
| `talking-head` | Footage de câmera → edit | beta |
| `clip-factory` | Long video → muitos clips | beta |
| `podcast-repurpose` | Podcast → highlights | beta |
| `localization-dub` | Legenda/dub/tradução | beta |
| `documentary-montage` | Stock footage → montagem | production |
| `framework-smoke` | Smoke test (CI) | test |

---

### `skills/` — Layer 2: Skills do Projeto
138 arquivos MD (~21K linhas). Como o OpenMontage quer que as ferramentas sejam usadas.

```
skills/
├── INDEX.md                  — índice de skills + arquitetura de conhecimento
├── meta/                     — onboarding, reviewer, checkpoint-protocol, video-reference-analyst
├── core/                     — ffmpeg, remotion, whisperx, subtitle-sync, color-grading
├── creative/                 — video-editing, storytelling, data-viz, long-form, prompting/*
└── pipelines/<pipeline>/     — 8 director skills por pipeline (research → publish)
```

**Leitura:** skill de estágio ANTES de qualquer trabalho naquele estágio. Nunca saltar.

---

### `.agents/skills/` — Layer 3: Conhecimento de Vendors
58 diretórios com documentação técnica bruta de tecnologias e provedores.

Lidos ANTES de chamar qualquer ferramenta de geração. Cada ferramenta declara seus Layer 3 no campo `agent_skills`.

**Categorias:**
- Composição: `remotion`, `remotion-best-practices`, `synthetic-screen-recording`
- Animação: `gsap*` (8 skills), `framer-motion`, `lottie-bodymovin`
- Imagem: `bfl-api`, `flux-best-practices`
- Vídeo: `ai-video-gen`, `ltx2`
- Áudio: `elevenlabs`, `music`, `sound-effects`, `text-to-speech`, `acestep`
- Avatar: `avatar-video`, `heygen`, `faceswap`, `create-video`
- Captura: `playwright-recording`
- Visualização: `beautiful-mermaid`, `d3-viz`, `manim-composer`, `manimce-best-practices`
- Edição: `video-edit`, `video-understand`, `video_toolkit`, `visual-style`

**Nota:** `.claude/skills/` é um subset de `.agents/skills/` (47 de 58). Faltam: `gsap*`, `grok-media`, `synthetic-screen-recording`.

---

### `.claude/skills/` — Skills disponíveis no Claude Code
Subset de `.agents/skills/` sincronizado para uso no Claude Code CLI. Ver seção acima.

---

### `lib/` — Infraestrutura Python
23 módulos. Contratos de API documentados em `.specs/constitution.md`.

| Módulo | Propósito |
|--------|-----------|
| `checkpoint.py` | Snapshots resumíveis por estágio. `write_checkpoint()`, `read_checkpoint()`, `get_next_stage()` |
| `pipeline_loader.py` | Carrega e valida manifests YAML. `load_pipeline()`, `get_stage_order()` |
| `cost_tracker.py` | Budget governance: `estimate()` → `reserve()` → `reconcile()` |
| `config_model.py` | Pydantic models para `config.yaml` (BudgetMode, CheckpointPolicy, LLMConfig) |
| `corpus.py` | Índice local de clips com busca vetorial L2 (ClipRecord + Corpus) |
| `delivery_promise.py` | Classifica tipo de entrega: motion_led, source_led, data_explainer, etc. |
| `env_loader.py` | Carrega `.env`, acesso tipado via `get_env()` / `require_env()` |
| `schema_adapter.py` | Canonical JSON Schema to flattened inline schema (strips $ref / additionalProperties / uniqueItems) for provider API structured output |
| `analysis_errors.py` | Shared exception hierarchy: `VideoUploadError`, `VideoAnalysisError`, `SchemaAdapterError` |
| `video_chunker.py` | FFmpeg keyframe-aligned chunking (`-c copy -reset_timestamps 1`); 5-minute bypass; `VideoChunkingError` |
| `analysis_merger.py` | Per-chunk `video_analysis` merge: global timecodes, hook from chunk 1, CTA from last chunk, audio weighted-avg, visual majority vote |
| `chunked_analyzer.py` | ThreadPoolExecutor bounded concurrency; `estimate_chunked_cost()` + `analyze_chunked()`; `VIDEO_CHUNK_WORKERS` env clamped [1,8] |
| `pipeline_synthesizer.py` | Rule-based base matching + staging writer + `synthesize_pipeline()` / `accept_synthesis()` / `reject_synthesis()`; writes ONLY to `pipeline_defs/_staging/` |
| `llm_fill.py` | Advisory LLM fill for stage details (OpenRouter text-only); bounded retries; never-raises fallback; FILLABLE_FIELDS = (tools_available, review_focus, success_criteria) |

---

### `schemas/` — JSON Schemas
19 schemas. Divididos em:
- `artifacts/` (15) — validam artefatos canônicos por estágio
- `checkpoints/` (1) — formato de checkpoint
- `pipelines/` (1) — manifesto de pipeline
- `styles/` (1) — style playbook
- `tools/` (1) — contratos de ferramenta

---

### `remotion-composer/` — Compositor de Vídeo (TypeScript)
29 arquivos TypeScript. Renderiza cenas animadas para os pipelines.

**Entry point:** `src/index.tsx` → composições registradas em `src/Root.tsx`  
**Composições:** `Explainer` (principal), `CinematicRenderer`, `TalkingHead`, `TitledVideo`

**Tipos de cena disponíveis** (`cut.type` no Explainer):

| Tipo | Componente | Input principal |
|------|-----------|----------------|
| `text_card` | TextCard | `text` |
| `stat_card` | StatCard | `stat` |
| `callout` | CalloutBox | `text`, `type` (info/warning/tip/quote) |
| `comparison` | ComparisonCard | `leftLabel`, `leftValue`, `rightLabel`, `rightValue` |
| `hero_title` | HeroTitle | `title` |
| `terminal_scene` | TerminalScene | `steps[]` (cmd/out/pause/pill) |
| `anime_scene` | AnimeScene | `images[]`, `animation` (camera motion) |
| `bar_chart` | BarChart | `data[]` |
| `line_chart` | LineChart | `series[]` |
| `pie_chart` | PieChart | `data[]` |
| `kpi_grid` | KPIGrid | `metrics[]` |
| `progress_bar` | ProgressBar | `progress` |

**Tipos de overlay** (`overlay.type`): `section_title`, `stat_reveal`, `hero_title`, `provider_chip`

**Referência completa de schemas:** `remotion-composer/SCENE_TYPES.md`

**Temas disponíveis:** `clean-professional`, `flat-motion-graphics`, `minimalist-diagram`, `anime-ghibli`

---

### `tests/` — Suite de Testes
14 arquivos, ~55K linhas.

```
tests/
├── contracts/    — Fase 0-3: contratos de tools e pipelines (sem API key)
├── qa/           — Integração: audio mix, video compose, stitch, design system, E2E
├── eval/         — Benchmarks e replay harness
└── tools/        — Testes de adapters específicos
```

**Rodar:** `make test` (todos) ou `make test-contracts` (sem API key).

---

### `styles/` — Style Playbooks
3 YAMLs. Controlam paleta, tipografia, motion style e parâmetros por plataforma.

---

### `docs/` — Documentação de Referência

| Arquivo | Conteúdo |
|---------|---------|
| `ARCHITECTURE.md` | Arquitetura técnica completa (19K bytes) |
| `PROVIDERS.md` | Setup de 35+ providers com custos e instruções (27K bytes) |
| `stage-gates/` | **Vazio** — reservado para harness de quality gates |

---

## Projetos em Execução

Cada run cria `projects/<project-name>/` com `artifacts/`, `assets/`, `renders/`. Gitignored.

---

## Ambiente

| Requisito | Mínimo | Status host |
|-----------|--------|-------------|
| Python | 3.10 | ⚠ 3.9.6 no host (usar devcontainer) |
| FFmpeg | qualquer | ⚠ não instalado no host |
| Node.js | 18+ | ✓ v25.9.0 |
| npx | qualquer | ✓ via npm |

**Para desenvolvimento:** usar o devcontainer em `.devcontainer/`.

---

`Last updated: 2026-04-17`

