# OpenMontage

## What This Is

OpenMontage é um sistema de produção de vídeo dirigido por instruções. O agente de IA é a inteligência: lê manifestos YAML (`pipeline_defs/`) e skills MD (`skills/`, `.agents/skills/`) para orquestrar ferramentas Python (`tools/`) que chamam provedores externos (vídeo, imagem, áudio, avatar). Python fornece tools e persistência; toda decisão criativa e de orquestração vive em instruções que o agente lê em tempo de execução.

Para quem: criadores e equipes que precisam produzir vídeo (explainer, trailer, talking-head, screen-demo, clip-factory, etc.) combinando geração de assets por IA com composição programática (FFmpeg + Remotion).

## Core Value

Um agente que lê instruções (pipeline manifest → stage director skill → Layer 3 vendor skill) e entrega um vídeo produzido end-to-end — sem que decisões criativas ou de tooling vazem para código Python.

## Current Milestone: v2.0 Reference Synthesis

**Goal:** Dado um vídeo de referência (URL ou arquivo), extrair sua gramática completa — edição, áudio, estilo visual e narrativa — e sintetizar um novo pipeline persistente em `pipeline_defs/` que reproduz aquele formato.

**Target features:**
- Nova capability `video_analysis` com selector multi-provider; Gemini Pro 3.1 como default (multimodal nativo, contexto longo)
- Extração estruturada contra schema canônico, cobrindo 4 dimensões:
  - **Edição + ritmo** (cortes, shot duration, cuts-per-minute, b-roll vs a-roll, mapeamento para cenas Remotion existentes)
  - **Áudio** (tom/ritmo/idioma da narração, gênero/tempo/intensidade da música, SFX, mix levels, voice/avatar)
  - **Estilo visual** (paleta, tipografia, motion style, text cards/overlays, style playbook sugerido de `styles/`)
  - **Narrativa** (hook, arco, CTA, estrutura de parágrafos, target platform, duração alvo)
- Síntese: analysis → novo `pipeline_defs/<nome>.yaml` persistente e versionado, validado contra `schemas/pipelines/pipeline_manifest.schema.json`
- Pipeline sintetizado reutiliza director skills existentes (aponta para `skills/pipelines/<similar>/*-director.md` conforme a similaridade detectada)
- Refatorar `skills/meta/video-reference-analyst.md` para consumir o novo contrato estruturado em vez de summary freeform
- Entry point ponta-a-ponta: usuário fornece URL/arquivo → agente roda análise → propõe pipeline gerado com diff contra pipelines existentes → aprovação humana → pipeline salvo e disponível no registry

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

- [ ] Capability `video_analysis` com selector e tool `gemini_video_analyzer` (Gemini Pro 3.1)
- [ ] Schema canônico `schemas/artifacts/video_analysis.schema.json` cobrindo edição+ritmo, áudio, estilo visual, narrativa
- [ ] Tool de síntese `pipeline_synthesizer` que consome `video_analysis` e emite `pipeline_defs/<nome>.yaml` validado
- [ ] Matching layer: mapeia estrutura detectada → pipelines base existentes (similarity + feature flags)
- [ ] Refatoração de `skills/meta/video-reference-analyst.md` para contrato estruturado
- [ ] Entry-point end-to-end (URL/arquivo → análise → proposta → aprovação → salvo) documentado no `AGENT_GUIDE.md`
- [ ] Test coverage: contracts (schema), integration (análise real de 2-3 vídeos referência), E2E (reference → pipeline → render)

### Out of Scope

<!-- Boundaries explícitos com razão. -->

- Geração automática de director skills novos — decisão explícita do usuário: reusar directors existentes para limitar escopo e risco de qualidade variável
- Pipeline efêmero por execução — usuário escolheu persistente em `pipeline_defs/`; flag `--ephemeral` não entra nesta milestone
- Multi-provider já na entrega — `video_analysis` é selector-ready, mas só Gemini 3.1 é implementado nesta milestone; outros providers ficam pra próxima
- Fine-tuning ou modelo custom de análise — assumimos Gemini 3.1 multimodal como base; qualquer modelo customizado é fora de escopo
- Auto-execução do pipeline gerado sem aprovação humana — mantém human-in-the-loop no checkpoint de proposta

## Context

- **Baseline técnico:** OpenMontage maduro, 109 tools + 12 pipelines + 138 skills Layer 2 + 58 Layer 3 + remotion-composer. Arquitetura instruction-driven estabelecida.
- **Trabalho anterior relevante:** `skills/meta/video-reference-analyst.md` já existe — faz análise leve de vídeo de referência e produz summary freeform; v2.0 substitui isso por contrato estruturado + síntese de pipeline.
- **Pendências conhecidas (TODO.md):** Python 3.10 no devcontainer, FFmpeg no host, sync de 11 skills GSAP/grok-media pra `.claude/skills/`, `docs/stage-gates/` vazio, README com claim inflado de skills, E2E sem render Remotion real.
- **Ambiente:** devcontainer em `.devcontainer/`. Host tem Python 3.9.6 (insuficiente) e sem FFmpeg — desenvolvimento v2.0 usa devcontainer.
- **Integração com workflow GSD:** `/gsd-map-codebase` rodou em 79bc5d7, gerou `.planning/codebase/`. Esta é a primeira milestone via GSD (v1.0 é baseline retroativo).

## Constraints

- **Tech stack**: Python 3.10+, Node.js 18+, FFmpeg, Remotion — herdado do baseline; novas tools seguem o contrato `BaseTool`
- **Provider**: Gemini Pro 3.1 via API (requer `GEMINI_API_KEY` ou equivalente); usar env var pattern existente (`lib/env_loader.py`)
- **Schemas**: todo artefato canônico novo valida contra JSON Schema; pipeline sintetizado valida contra `schemas/pipelines/pipeline_manifest.schema.json` existente
- **Selectors**: `video_analysis` precisa seguir padrão dos selectors atuais (`tts_selector`, `video_selector`) — discovery via registry, routing por preferência/disponibilidade
- **Human approval**: pipeline gerado nunca executa sem aprovação; checkpoint obrigatório após síntese
- **Backward compat**: pipelines v1.0 continuam funcionando; nada de breaking em `pipeline_defs/` existentes

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Output persistente em `pipeline_defs/` (não efêmero) | Reusabilidade, versionamento, auditoria, alinha com arquitetura atual | — Pending |
| `video_analysis` como capability com selector, Gemini 3.1 como primeiro provider | Mantém padrão de multi-provider do projeto; habilita trocar/adicionar providers sem refactor | — Pending |
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

---
*Last updated: 2026-04-17 after starting milestone v2.0 Reference Synthesis*
