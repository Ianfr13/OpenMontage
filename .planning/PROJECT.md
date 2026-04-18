# OpenMontage

## What This Is

OpenMontage é um sistema de produção de vídeo dirigido por instruções. O agente de IA é a inteligência: lê manifestos YAML (`pipeline_defs/`) e skills MD (`skills/`, `.agents/skills/`) para orquestrar ferramentas Python (`tools/`) que chamam provedores externos (vídeo, imagem, áudio, avatar). Python fornece tools e persistência; toda decisão criativa e de orquestração vive em instruções que o agente lê em tempo de execução.

Para quem: criadores e equipes que precisam produzir vídeo (explainer, trailer, talking-head, screen-demo, clip-factory, etc.) combinando geração de assets por IA com composição programática (FFmpeg + Remotion).

## Core Value

Um agente que lê instruções (pipeline manifest → stage director skill → Layer 3 vendor skill) e entrega um vídeo produzido end-to-end — sem que decisões criativas ou de tooling vazem para código Python.

## Current State

**v2.1 Cleanup & Hardening shipped (2026-04-18)** — 5 phases · 8 plans · 689 tests (+68 vs v2.0). All v2.0 HIGH/MEDIUM code-review findings absorbed, `cinematic.yaml` drift cleared, 19 atomic NIT fixes + 2 already-resolved + 9 explicitly deferred, and OpenRouter SKILL-03 real-video UAT passed live (47 canonical fields populated). Gemini UAT deferred on free-tier quota (resource-availability tech debt, not a code defect). See `.planning/milestones/v2.1-ROADMAP.md` for the archive.

**Previously:** v2.0 Reference Synthesis (2026-04-17) — reference-synthesis meta skill (`skills/meta/reference-synthesis.md`) shipped as live entry point. See `.planning/milestones/v2.0-ROADMAP.md`.

## Next Milestone Goals

_TBD — start with `/gsd-new-milestone` to define requirements._

Candidate themes from v2.1 deferred items:
- UAT-01 completion (Gemini real-video SKILL-03 on billing-enabled key) — soft, single-shot retry
- 9 NITS-DEF-* items in Code Hygiene future bucket (key redaction, `_FLAT_SCHEMA` lru_cache, shot-boundary helpers, orphan cost-tracker reservations, pathlib migration, LLM_FILL gate dedup, load_pipeline round-trip validation)
- SYNTH2-* synthesizer quality improvements (still pending from v2.0)
- OBS-* observability (cross-chunk cost tracking, analysis cache by checksum)

---

<details>
<summary>Archived: v2.0 Reference Synthesis milestone definition</summary>

## Shipped Milestone: v2.0 Reference Synthesis

**Goal:** Dado um vídeo de referência (arquivo local), extrair sua gramática completa — edição, áudio, estilo visual e narrativa — e sintetizar um novo pipeline persistente em `pipeline_defs/` que reproduz aquele formato.

**Target features:**
- Nova capability `video_analysis` com selector multi-provider. **Dois providers intercambiáveis atrás do selector**:
  - `gemini_video_analyzer` — SDK direto `google-genai` (Files API, URL ou base64, structured output nativo via `response_json_schema`). Auth: `GEMINI_API_KEY`. Modelo: `GEMINI_VIDEO_MODEL` (default `gemini-3.1-pro-preview`, fallback `gemini-2.5-pro`).
  - `openrouter_video_analyzer` — via `openai>=1.0` SDK apontando pra `https://openrouter.ai/api/v1` (base64 inline obrigatório, modelo trocável). Auth: `OPENROUTER_API_KEY`. Modelo: `OPENROUTER_MODEL` (default `google/gemini-3.1-pro-preview`).
  - Selector roteia por `VIDEO_ANALYZER_PROVIDER` (gemini/openrouter/auto) ou pela env var presente.
- Extração estruturada contra schema canônico, cobrindo 4 dimensões:
  - **Edição + ritmo** (cortes, shot duration, cuts-per-minute, b-roll vs a-roll, mapeamento para cenas Remotion existentes)
  - **Áudio** (tom/ritmo/idioma da narração, gênero/tempo/intensidade da música, SFX, mix levels, voice/avatar)
  - **Estilo visual** (paleta, tipografia, motion style, text cards/overlays, style playbook sugerido de `styles/`)
  - **Narrativa** (hook, arco, CTA, estrutura de parágrafos, target platform, duração alvo)
- **Chunking automático**: vídeos >5min são divididos em chunks ≤5min (FFmpeg), analisados em paralelo, merged em um único artefato canônico com timecodes globais normalizados
- Síntese: analysis → novo `pipeline_defs/_staging/<nome>.yaml` (staging path gated) → aprovação humana → movido para `pipeline_defs/<nome>.yaml` persistente e versionado; validado contra `schemas/pipelines/pipeline_manifest.schema.json`
- Synthesis mode default = `template` (pipeline generalizável, reusável com outros temas); parâmetro `replica` disponível
- Matching rule-based (não LLM puro): pacing_style + shot_distribution + motion_style → pipeline base (animated-explainer, cinematic, hybrid, etc.); LLM só preenche detalhes de stage
- Pipeline sintetizado reutiliza director skills existentes (aponta para `skills/pipelines/<similar>/*-director.md` conforme a similaridade detectada)
- Refatorar `skills/meta/video-reference-analyst.md` para consumir o novo contrato estruturado em vez de summary freeform
- Entry point ponta-a-ponta: usuário fornece URL/arquivo → agente roda análise (chunked se >5min) → synthesizer propõe pipeline em `_staging/` com diff → aprovação humana → pipeline movido para `pipeline_defs/` e disponível no registry

## Requirements

### Validated

<!-- Shipped and confirmed valuable — baseline v1.0 inferido do codebase atual (commit 79bc5d7). -->

- ✓ **Registry-driven tool discovery** — `tools/tool_registry.py` auto-descobre 109 ferramentas via `BaseTool`; nenhuma lista hardcoded — v1.0
- ✓ **Capability selectors multi-provider** — `tts_selector`, `image_selector`, `video_selector` roteiam para providers disponíveis — v1.0
- ✓ **12 pipelines declarativos** — `animated-explainer`, `animation`, `cinematic`, `avatar-spokesperson`, `hybrid`, `screen-demo` (production), `talking-head`, `clip-factory`, `podcast-repurpose`, `localization-dub` (beta), `documentary-montage`, `framework-smoke` — v1.0
- ✓ **Stage director skills + meta skills** — 138 skills Layer 2 (reviewer, checkpoint-protocol, video-reference-analyst, diretores por stage) — v1.0
- ✓ **Layer 3 vendor skills** — 58 skills com prompting específico por provider — v1.0
- ✓ **Checkpoint + cost tracker + pipeline loader** — `lib/checkpoint.py`, `tools/cost_tracker.py`, `lib/pipeline_loader.py` — v1.0
- ✓ **remotion-composer (TypeScript)** — 12 tipos de cena (`text_card`, `stat_card`, `callout`, `comparison`, `hero_title`, `terminal_scene`, `anime_scene`, `bar_chart`, `line_chart`, `pie_chart`, `kpi_grid`, `progress_bar`) + overlays — v1.0
- ✓ **Schemas JSON canônicos** — 19 schemas (artifacts, checkpoints, pipelines, styles, tools) — v1.0
- ✓ **Animation-runtime routing** — Layer 3 GSAP + Remotion primitives (AnimatedText, backgrounds) roteados via `skills/meta/animation-runtime-selector.md` — v1.0

### Active

<!-- Current scope for v2.0 — hipóteses até shippar e validar. -->

- [ ] Capability `video_analysis` com selector `video_analyzer_selector` e **dois providers**: `gemini_video_analyzer` (SDK direto `google-genai`) e `openrouter_video_analyzer` (via `openai` SDK)
- [ ] Schema canônico `schemas/artifacts/video_analysis.schema.json` (novo, não extensão do brief existente) cobrindo edição+ritmo, áudio, estilo visual, narrativa
- [ ] `lib/schema_adapter.py` converte schema canônico → schema flat aceito pelas APIs (remove `$ref`, `additionalProperties: false`, `uniqueItems`)
- [ ] Chunking `lib/video_chunker.py` + merge `lib/analysis_merger.py` para vídeos >5min (FFmpeg split keyframe-aligned + merge com timecode normalization + regras por dimensão)
- [ ] Utilitário de síntese `lib/pipeline_synthesizer.py` (não BaseTool) que consome `video_analysis` e emite YAML para `pipeline_defs/_staging/<nome>.yaml`, com staging path excluído do `pipeline_loader`
- [ ] Matching layer rule-based: estrutura detectada → pipelines base (LLM só preenche detalhes de stage)
- [ ] Synthesis mode `template` (default) + `replica` (param)
- [ ] Layer 3 skills `.agents/skills/gemini-video-analysis/SKILL.md` e `.agents/skills/openrouter-video-analysis/SKILL.md` com prompting específico por provider
- [ ] Meta skill `skills/meta/reference-synthesis.md` orquestra o flow end-to-end com 2 checkpoints (analysis review, synthesis diff approval)
- [ ] Refatoração de `skills/meta/video-reference-analyst.md` para contrato estruturado (com fallback freeform pra backward compat)
- [ ] Entry-point end-to-end (arquivo → análise chunked → proposta staged → aprovação → salvo) documentado no `AGENT_GUIDE.md`
- [ ] Test coverage: contracts (schema, adapter, staging exclusion, selector preference); integration dupla (Gemini + OpenRouter) em 3 vídeos (<2min, 3-5min, >5min chunked); cross-provider consistency dentro de tolerância documentada; backward compat (12 pipelines v1.0 seguem válidos)

### Out of Scope

<!-- Boundaries explícitos com razão. -->

- Geração automática de director skills novos — decisão explícita do usuário: reusar directors existentes para limitar escopo e risco de qualidade variável
- Pipeline efêmero por execução — usuário escolheu persistente em `pipeline_defs/`; flag `--ephemeral` não entra nesta milestone
- Gemini CLI como provider — CLI não suporta schema enforcement ([issue #8022](https://github.com/google-gemini/gemini-cli/issues/8022) aberta desde Set/2025); anexo de vídeo via `@path` indocumentado. SDK direto entrega tudo que CLI faria e mais.
- Providers diretos Anthropic/OpenAI sem vídeo nativo — Claude ainda não aceita video input; OpenAI vision só frames. Fora da milestone.
- Video input via URL **no provider OpenRouter** — Gemini via OpenRouter rejeita URL. Provider Gemini direto (Files API) aceita URL, mas a interface uniforme do selector passa arquivo local pra ambos.
- Fine-tuning ou modelo custom de análise — modelo trocado via `GEMINI_VIDEO_MODEL`/`OPENROUTER_MODEL`; qualquer custom/fine-tune fica fora de escopo
- Auto-execução do pipeline gerado sem aprovação humana — mantém human-in-the-loop no checkpoint de proposta

## Context

- **Baseline técnico:** OpenMontage maduro, 109 tools + 12 pipelines + 138 skills Layer 2 + 58 Layer 3 + remotion-composer. Arquitetura instruction-driven estabelecida.
- **Trabalho anterior relevante:** `skills/meta/video-reference-analyst.md` já existe — faz análise leve de vídeo de referência e produz summary freeform; v2.0 substitui isso por contrato estruturado + síntese de pipeline.
- **Pendências conhecidas (TODO.md):** Python 3.10 no devcontainer, FFmpeg no host, sync de 11 skills GSAP/grok-media pra `.claude/skills/`, `docs/stage-gates/` vazio, README com claim inflado de skills, E2E sem render Remotion real.
- **Ambiente:** devcontainer em `.devcontainer/`. Host tem Python 3.9.6 (insuficiente) e sem FFmpeg — desenvolvimento v2.0 usa devcontainer.
- **Integração com workflow GSD:** `/gsd-map-codebase` rodou em 79bc5d7, gerou `.planning/codebase/`. Esta é a primeira milestone via GSD (v1.0 é baseline retroativo).

## Constraints

- **Tech stack**: Python 3.10+, Node.js 18+, FFmpeg, Remotion — herdado do baseline; novas tools seguem o contrato `BaseTool`
- **Providers (dois, intercambiáveis via selector)**:
  - Gemini direto — SDK `google-genai>=1.73`, auth `GEMINI_API_KEY` (fallback `GOOGLE_API_KEY`), modelo via `GEMINI_VIDEO_MODEL`
  - OpenRouter — SDK `openai>=1.0` com `base_url="https://openrouter.ai/api/v1"`, auth `OPENROUTER_API_KEY`, modelo via `OPENROUTER_MODEL`
  - Preferência via `VIDEO_ANALYZER_PROVIDER` (gemini/openrouter/auto); usar env var pattern existente (`lib/env_loader.py`)
- **Video input**: tool interface uniforme recebe arquivo local. Gemini direto pode usar Files API internamente; OpenRouter encoda base64 inline `data:video/mp4;base64,...` (único formato aceito). `video_downloader` baixa antes quando input é URL.
- **Schemas**: todo artefato canônico novo valida contra JSON Schema; pipeline sintetizado valida contra `schemas/pipelines/pipeline_manifest.schema.json` existente
- **Selectors**: `video_analysis` precisa seguir padrão dos selectors atuais (`tts_selector`, `video_selector`) — discovery via registry, routing por preferência/disponibilidade
- **Human approval**: pipeline gerado nunca executa sem aprovação; checkpoint obrigatório após síntese
- **Backward compat**: pipelines v1.0 continuam funcionando; nada de breaking em `pipeline_defs/` existentes

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Output persistente em `pipeline_defs/` (não efêmero) | Reusabilidade, versionamento, auditoria, alinha com arquitetura atual | — Pending |
| `video_analysis` como capability com selector + **dois providers** (Gemini SDK direto + OpenRouter) intercambiáveis via env | Usuário quer flexibilidade de trocar: Gemini direto pra structured output nativo + Files API; OpenRouter pra trocar modelo sem mudar credenciais. Dois providers cobrem backup caso um falhe. | — Pending |
| Video input = arquivo local; Gemini direto usa Files API, OpenRouter usa base64 inline | Gemini via OpenRouter só aceita base64 (URL rejected). Interface uniforme dos tools recebe file path; cada provider resolve seu transporte. | — Pending |
| Não usar Gemini CLI como provider | CLI não enforça schema (issue #8022 aberta Set/2025); attachment de vídeo via `@path` indocumentado. SDK direto entrega tudo que CLI faria + features. | — Pending |
| Chunking em 5min pra vídeos longos (sem cap de duração) | Usuário escolheu "sem cap" apesar de +2 phases de escopo. Mitiga timecode hallucination do Gemini em vídeos longos e controla custo por chunk. | — Pending |
| Reutilizar director skills existentes (não gerar novos) | Escopo menor, entrega mais rápida, evita qualidade variável de skills auto-geradas | — Pending |
| Extração cobre as 4 dimensões (edição, áudio, estilo visual, narrativa) | Usuário selecionou todas; fragmentar reduziria valor do pipeline sintetizado | — Pending |
| Milestone numerada v2.0 (não v1.1) | Mudança de paradigma: agente passa de "escolhe pipeline" para "sintetiza pipeline" | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

</details>

---
*Last updated: 2026-04-18 after shipping milestone v2.1 Cleanup & Hardening*
