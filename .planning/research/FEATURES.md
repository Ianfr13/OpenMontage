# Feature Research — v2.0 Reference Synthesis

**Domain:** Reference-to-pipeline synthesis for AI video production
**Researched:** 2026-04-17
**Confidence:** HIGH (schema already exists in codebase; patterns verified against Gemini docs and PySceneDetect docs; UX patterns verified against HITL literature)

---

## Context

This document covers only the NEW capability introduced in v2.0: taking a video URL/file,
extracting its grammar across 4 dimensions, and synthesizing a persistent `pipeline_defs/`
YAML. Features already shipped in v1.0 (pipelines, scene types, selectors, checkpoint,
registry) are baseline — not re-researched here.

The existing `schemas/artifacts/video_analysis_brief.schema.json` (v1.0) covers a
`structure_analysis` and a thin `style_profile`. v2.0 must expand this schema into 4
explicit, structured dimensions so the synthesizer can operate on facts, not prose summaries.

---

## 4-Dimension Field Inventory

### Dimension 1: Editing + Pacing

**Purpose:** Drive scene ordering, cut timing, and Remotion scene-type selection in the
synthesized pipeline.

**Current schema coverage:** `structure_analysis.pacing_profile` has 5 fields.
**Gap:** No b-roll ratio, no motion_type distribution, no Remotion mapping.

**Canonical field list for `video_analysis.editing_pacing`:**

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `total_shots` | integer | Detected shot boundaries (hard cuts + transitions) | PySceneDetect ContentDetector |
| `cuts_per_minute` | number | Total shots / duration in minutes | Derived |
| `avg_shot_duration_seconds` | number | mean shot hold time | Derived |
| `median_shot_duration_seconds` | number | Robust to outliers from title cards | Derived |
| `shortest_shot_seconds` | number | Fastest cut detected | PySceneDetect |
| `longest_shot_seconds` | number | Longest uncut segment | PySceneDetect |
| `pacing_style` | enum | `slow_contemplative` / `steady_educational` / `dynamic_social` / `rapid_fire` / `variable` | Agent rule: CPM < 10 = slow, 10-20 = steady, 20-40 = dynamic, > 40 = rapid_fire |
| `shot_type_distribution` | object | `{talking_head: 0.4, b_roll: 0.3, text_card: 0.2, animation: 0.1}` — ratios must sum to 1.0 | Gemini multimodal per-scene |
| `b_roll_ratio` | number | Fraction of runtime that is b-roll (non-speaker, non-text) | Derived from shot_type_distribution |
| `a_roll_ratio` | number | Fraction of runtime that is talking_head or direct-to-camera | Derived |
| `motion_type_distribution` | object | `{motion_clip: N, animated_still: N, static_image: N}` per scene count | Gemini vision per-scene |
| `transition_types` | array[string] | Detected transitions: `cut`, `dissolve`, `fade_black`, `fade_white`, `wipe`, `zoom_cut` | Gemini multimodal |
| `energy_arc` | array[object] | `[{timestamp_s, energy_level}]` — low/medium/high/peak per scene | Gemini per-scene; used for narrative arc mapping |
| `suggested_remotion_scene_types` | array[string] | Remotion `cut.type` values that reproduce each detected visual type; drawn from `SCENE_TYPES.md` enum | Agent rule mapping visual_type → scene type |

**Detection method:** Use PySceneDetect `ContentDetector` (threshold 27) or `AdaptiveDetector`
for videos with fast camera movement. Pass shot boundaries to Gemini as context, then use
Gemini multimodal for per-shot classification (`visual_type`, `motion_type`, `energy_level`).
PySceneDetect handles the counting accurately; Gemini handles the semantic labeling. Do NOT
rely on Gemini alone for shot boundary count — 1 fps sampling misses fast cuts (<0.5s).

---

### Dimension 2: Audio

**Purpose:** Drive TTS voice selection, music genre/tempo, SFX usage, and mix parameters
in the synthesized pipeline.

**Current schema coverage:** `style_profile.narration_style` has 4 fields; `style_profile.music_style`
is a single freeform string. Inadequate for synthesis.

**Canonical field list for `video_analysis.audio`:**

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `has_narration` | boolean | Voice-over or on-screen speech present | Transcript presence |
| `narration_style` | enum | `voice_over` / `on_screen_presenter` / `dialogue_only` / `none` | Gemini + transcript |
| `speaker_count` | integer | Distinct speaking voices detected | Transcript diarization |
| `voice_gender` | enum | `male` / `female` / `mixed` / `synthetic_detected` / `unknown` | Gemini audio analysis |
| `voice_tone` | enum | `authoritative` / `conversational` / `energetic` / `calm` / `dramatic` | Gemini |
| `narration_wpm` | number | Approximate words-per-minute of delivered narration | word_count / duration |
| `narration_language` | string | BCP-47 language code (e.g., `en-US`) | Whisper transcription |
| `has_music` | boolean | Background music track present | Gemini audio analysis |
| `music_genre` | string | e.g., `ambient_corporate`, `upbeat_electronic`, `cinematic_orchestral` | Gemini |
| `music_tempo_bpm` | number | Estimated BPM if music detected; null if no music | Gemini audio; LOW confidence |
| `music_intensity` | enum | `subtle_background` / `moderate` / `dominant_foreground` | Gemini |
| `has_sfx` | boolean | Sound effects beyond music/narration detected | Gemini |
| `sfx_style` | string | e.g., `whoosh_transitions`, `notification_pings`, `cinematic_impacts` | Gemini |
| `voice_music_mix` | enum | `narration_dominant` / `music_dominant` / `balanced` | Gemini |
| `suggested_tts_voice_profile` | string | Description for `tts_selector` prompt e.g. "professional male, authoritative, moderate pace" | Derived from voice fields |
| `suggested_music_prompt` | string | Prompt for `music_gen` derived from music fields | Derived |

**Hardest field:** `music_tempo_bpm`. Gemini estimates tempo from audio patterns but accuracy
is LOW — acceptable for "around 120 BPM" but not for beat-sync editing. Flag as `estimated`
in the schema. For OpenMontage's use case (choosing music mood), the estimate is sufficient.

---

### Dimension 3: Visual Style

**Purpose:** Select or parameterize a style playbook; drive image_gen prompts, Remotion
theme, color tokens, and typography in the synthesized pipeline.

**Current schema coverage:** `style_profile.color_palette`, `typography_observed` (string),
`closest_playbook`, `playbook_delta`. The color palette and typography are present but shallow.

**Canonical field list for `video_analysis.visual_style`:**

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `color_palette` | object | `{primary: [hex], accent: [hex], background: [hex], text: [hex]}` — extracted from keyframes | Gemini vision on keyframe sample |
| `dominant_colors_hex` | array[string] | Top 5 colors by frequency across all keyframes | Gemini vision |
| `color_temperature` | enum | `warm` / `cool` / `neutral` / `high_contrast` | Derived from palette |
| `color_grading_style` | enum | `flat_clean` / `cinematic_grade` / `desaturated` / `vibrant_saturated` / `dark_moody` | Gemini vision |
| `background_treatment` | enum | `solid_color` / `gradient` / `real_footage` / `abstract_motion` / `transparent_overlay` | Gemini per-scene |
| `typography_style` | string | e.g., "sans-serif bold headings, light body, white on dark" | Gemini vision on text-card frames |
| `typography_weight` | enum | `light` / `regular` / `bold` / `ultra_bold` | Gemini |
| `text_card_usage` | enum | `heavy` (> 30% of scenes) / `moderate` (10-30%) / `minimal` (< 10%) / `none` | Derived from shot_type_distribution |
| `motion_style` | enum | `spring_physics` / `linear_slides` / `ease_in_out` / `snap_cuts` / `no_animation` | Gemini vision on transitions |
| `overlay_style` | enum | `lower_thirds` / `full_frame_cards` / `floating_labels` / `none` | Gemini vision |
| `production_quality` | enum | `amateur` / `prosumer` / `professional` / `broadcast` | Gemini holistic |
| `aspect_ratio` | enum | `16:9` / `9:16` / `1:1` / `4:3` / `other` | Video metadata |
| `suggested_playbook` | string | Best-match from `{clean-professional, flat-motion-graphics, minimalist-diagram, anime-ghibli}` | Rule: map color_grading_style + motion_style + text_card_usage |
| `playbook_overrides` | object | Delta config to apply on top of suggested_playbook (e.g., `{visual_language.color_palette.primary: ["#FF5733"]}`) | Agent synthesis |

**Hardest field in this dimension:** `typography_style`. Gemini can describe what it sees
("bold sans-serif white on dark") but cannot identify the specific font family. This is
acceptable — the synthesized pipeline needs the style description to parameterize Remotion
theme, not the exact font name. Flag as `observed_style` not `font_family`.

**Color palette extraction:** Gemini samples ~5 keyframes and infers dominant colors. For a
structured `[hex]` output, instruct Gemini to return the closest web-safe approximation.
Accuracy is MEDIUM — sufficient for playbook selection, not pixel-perfect.

---

### Dimension 4: Narrative

**Purpose:** Drive script structure, hook pattern, section count, CTA type, target platform,
and duration target in the synthesized pipeline's script stage.

**Current schema coverage:** `content_analysis` has `hook_technique`, `call_to_action`, `tone`.
Missing: arc pattern, section structure, platform detection, structural paragraph map.

**Canonical field list for `video_analysis.narrative`:**

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `hook_type` | enum | `question` / `bold_claim` / `visual_shock` / `stat_drop` / `story_open` / `problem_statement` / `none` | Gemini on first 15% of video |
| `hook_duration_seconds` | number | Length of hook segment before main content | Agent estimate from energy_arc |
| `narrative_arc` | enum | `linear` / `problem_solution` / `listicle` / `story_driven` / `educational_buildup` / `montage_no_arc` | Gemini holistic |
| `section_count` | integer | Number of distinct content sections (excluding hook + CTA) | Gemini structural analysis |
| `section_structure` | array[object] | `[{label, approx_start_s, approx_end_s, summary}]` — section-level outline | Gemini + transcript |
| `cta_type` | enum | `subscribe` / `visit_link` / `purchase` / `follow` / `download` / `none_detected` | Gemini on final 15% |
| `cta_duration_seconds` | number | Length of CTA segment | Agent estimate |
| `target_platform` | enum | `youtube_long` / `youtube_shorts` / `tiktok` / `instagram_reels` / `linkedin` / `twitter` / `unknown` | Heuristic: aspect_ratio + duration + pacing_style |
| `target_duration_seconds` | number | Reference video runtime (used as template duration target) | Video metadata |
| `information_density` | enum | `sparse` (long pauses, slow delivery) / `moderate` / `dense` (fast narration, many facts) | Derived from narration_wpm + cuts_per_minute |
| `content_tone` | enum | `educational` / `entertaining` / `cinematic` / `corporate` / `casual` / `dramatic` / `inspirational` / `humorous` | Gemini holistic |
| `paragraph_pattern` | string | Structural template e.g. "Hook (5s) → Intro (10s) → 3x Point (15s each) → Recap (10s) → CTA (5s)" | Agent synthesis from section_structure |

**Hardest dimension overall:** Narrative. Gemini reliably extracts hook and CTA. The middle
arc (`narrative_arc`, `section_structure`) requires multi-step reasoning: transcript
segmentation + visual scene boundaries + topic clustering. On short videos (< 3 min) this
is reliable. On long-form (> 10 min), `section_count` and `section_structure` should be
flagged with `confidence: medium`. The `paragraph_pattern` field is pure synthesis —
label it explicitly so downstream systems know it's an agent inference, not a measured fact.

---

## Feature Landscape

### Table Stakes (Users Expect These)

These are the minimum behaviors for the reference-synthesis entry point to feel complete.
Missing any one makes the feature feel broken.

| Feature | Why Expected | Complexity (S/M/L) | Dependencies |
|---------|--------------|---------------------|--------------|
| URL/file ingestion — YouTube, Shorts, local file | Any "make something like this" flow starts here | S | `video_downloader`, `transcript_fetcher` (v1.0 tools) |
| Structured analysis output across all 4 dimensions | User expects the system to "understand" the video, not just summarize it | M | `gemini_video_analyzer` (new), PySceneDetect (already in `scene_detect` tool) |
| JSON schema validation of `video_analysis` artifact | Engineering expectation: downstream synthesizer needs typed contract, not freeform text | S | New `schemas/artifacts/video_analysis.schema.json` (extends v1.0 brief) |
| Pipeline suggestion with rationale | User expects "here's which pipeline I'd use and why" | S | matching layer (new); reads existing `pipeline_defs/` |
| Human-readable analysis summary before pipeline proposal | Every comparable system (Runway, Descript, Captions.ai) surfaces an analysis review before acting | S | Agent rendering of `video_analysis` artifact |
| Pipeline diff view — proposed YAML vs closest existing pipeline | User needs to understand what's different from existing pipelines to approve | M | `pipeline_synthesizer` (new); diff logic against `pipeline_defs/` |
| Human approval checkpoint before pipeline is saved | Hard requirement from `PROJECT.md` — never auto-execute | S | `checkpoint.py` (v1.0); new `awaiting_human` status on synthesis result |
| Synthesized pipeline saved to `pipeline_defs/` and validated | User expects it to actually work like other pipelines after approval | M | `pipeline_synthesizer`, `pipeline_manifest.schema.json` (v1.0) |
| Synthesized pipeline immediately available in registry | After save, "run pipeline X" should work without restart | S | `pipeline_loader.py` (v1.0) already supports hot-load |

---

### Differentiators (Competitive Advantage)

Features that go beyond the baseline and make OpenMontage's reference synthesis meaningfully
better than ad-hoc "describe what you see" approaches.

| Feature | Value Proposition | Complexity (S/M/L) | Dependencies |
|---------|-------------------|--------------------|--------------|
| 4-dimension structured schema — not a summary, a contract | Other tools produce prose. OpenMontage produces a typed artifact that drives synthesis deterministically. | M | Gemini structured output (`response_json_schema`); Pydantic model for validation |
| PySceneDetect + Gemini hybrid for shot detection | Gemini at 1 fps misses fast cuts. PySceneDetect catches every hard cut; Gemini labels them semantically. Hybrid gives correct count + rich labels. | M | `scene_detect` tool (v1.0 PySceneDetect wrapper) + `gemini_video_analyzer` |
| Remotion scene-type mapping in analysis output | `suggested_remotion_scene_types` directly names `cut.type` values from `SCENE_TYPES.md`, creating a bridge between analysis and composition. No comparable tool does this. | S | Remotion `SCENE_TYPES.md` vocabulary (v1.0); mapping rule table in synthesizer skill |
| Playbook matching + delta generation | Instead of creating a pipeline from scratch, the system finds the closest existing playbook and outputs only the override keys needed. Reduces token cost and error surface. | M | `styles/` playbooks (v1.0); matching rule table |
| Director-skill reuse selection | Synthesized pipeline points to existing director skills, not generated ones. Explicit constraint from `PROJECT.md`. Prevents quality regression from auto-generated instructions. | S | `skills/pipelines/` catalog (v1.0); matching logic in `pipeline_synthesizer` |
| `paragraph_pattern` field as reusable template | Extracted structural blueprint ("Hook 5s → 3x Point 15s → CTA 5s") becomes a reusable template field in the pipeline manifest for the script stage. | S | `section_structure` extraction; pipeline manifest `metadata` object |
| `video_analysis_selector` following the existing selector pattern | Makes the analysis capability multi-provider from day one, even though only Gemini ships. Trivial to add Claude 3.5 Sonnet, GPT-4o later without refactoring. | S | Selector pattern (`tts_selector` reference implementation) |

---

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Auto-execute synthesized pipeline immediately after approval | "One-click from reference to output" is appealing | Destroys the staged quality system that makes v1.0 work. Users will get bad output and not understand why. | Save pipeline → let user run it normally. The checkpoint system already handles this cleanly. |
| Generate new director skills for the synthesized pipeline | Sounds complete — every pipeline has its own skills | Director skills require human craft to be high quality. Auto-generated MD skills are inconsistent and hard to audit. `PROJECT.md` explicitly disallows this. | Point synthesized pipeline to existing director skills (`skills/pipelines/<closest>/`). |
| Font family identification from video | Seems useful for visual fidelity | Gemini cannot reliably identify specific typefaces. Returns low-confidence guesses. Storing guesses as facts pollutes the schema. | Extract `typography_style` as a prose description. Remotion themes use configurable font families — description is sufficient. |
| Per-frame color extraction (full palette every frame) | "Maximum fidelity" | Massively inflates the artifact size. A 60s video at 1fps = 60 frames × palette = unusable JSON. | Sample 5-8 representative keyframes. Aggregate palette across them. |
| Ephemeral (in-memory only) synthesized pipeline | Faster iteration, no file clutter | Defeats the core value: reusability, versionability, and audit trail. `PROJECT.md` explicitly chose persistent. | Write to `pipeline_defs/`. The user can delete it if not needed. |
| Multi-provider analysis in parallel for consensus | Accuracy improvement | 3x cost, complex conflict resolution, no clear evidence consensus improves output for this use case. | Gemini 3.1 alone is sufficient for this classification task. Add second provider later if accuracy issues emerge. |
| Automatic style playbook creation | References that don't match any existing playbook | High complexity, unclear quality bar. An auto-generated playbook may validate but produce bad visuals. | Use `playbook_overrides` on the closest existing playbook. Document the delta. |

---

## Feature Dependencies

```
[gemini_video_analyzer tool]
    └──requires──> [GEMINI_API_KEY env var]
    └──produces──> [video_analysis artifact]

[video_analysis artifact]
    └──requires──> [video_analysis.schema.json (new)]
    └──requires──> [scene_detect tool (v1.0 PySceneDetect)] — for shot count
    └──requires──> [video_downloader (v1.0)] — for URL ingestion

[pipeline_synthesizer tool]
    └──requires──> [video_analysis artifact]
    └──requires──> [pipeline_defs/ catalog (v1.0)] — for matching
    └──requires──> [skills/pipelines/ catalog (v1.0)] — for director selection
    └──requires──> [styles/ playbooks (v1.0)] — for playbook matching
    └──produces──> [pipeline_defs/<name>.yaml]
    └──validates against──> [pipeline_manifest.schema.json (v1.0)]

[pipeline_defs/<name>.yaml]
    └──requires──> [human approval checkpoint]
    └──then available via──> [pipeline_loader.py (v1.0)]

[skills/meta/video-reference-analyst.md refactor]
    └──requires──> [video_analysis artifact schema finalized]
    └──replaces──> [VideoAnalysisBrief freeform summary]

[video_analysis_selector]
    └──follows pattern of──> [tts_selector, image_selector (v1.0)]
    └──wraps──> [gemini_video_analyzer]
```

### Dependency Notes

- `scene_detect` (v1.0) must be called BEFORE `gemini_video_analyzer` to produce the shot
  timestamp list; the synthesizer passes that list to Gemini for semantic labeling.
- `pipeline_synthesizer` cannot match director skills without the existing `skills/pipelines/`
  catalog. This is a hard read dependency — synthesizer must load the catalog at synthesis time.
- The schema for `video_analysis` must be finalized before the `video-reference-analyst` skill
  can be refactored. Schema is the source of truth for what fields the skill populates.

---

## Recommended UX Flow (Numbered Sequence)

This is the end-to-end entry point for a user who provides a reference video.

1. User provides URL or local file path ("make me something like this").
2. Agent reads `skills/meta/video-reference-analyst.md` (AGENT_GUIDE trigger).
3. Agent runs `video_downloader` (if URL) → local file confirmed.
4. Agent runs `scene_detect` (PySceneDetect) → returns `shot_boundaries[]` with timestamps.
5. Agent runs `gemini_video_analyzer` with `analysis_depth: "structured_4d"` and
   `shot_boundaries` as input context → returns structured `video_analysis` artifact
   across all 4 dimensions.
6. Agent validates `video_analysis` against `schemas/artifacts/video_analysis.schema.json`.
7. Agent presents human-readable summary to user (not raw JSON):
   - "Here's what I found: [content summary]. Pacing: [style]. Visual style: [playbook match].
     Audio: [voice + music description]. Structure: [paragraph_pattern]."
8. Agent asks 2-3 critical questions (narration preference, duration target, topic if different).
   Resolves any gaps before proposing.
9. Agent runs `pipeline_synthesizer` → produces candidate `pipeline_defs/<name>.yaml`
   with `suggested_pipeline` as base, `playbook_overrides` applied.
10. Agent presents pipeline diff: shows proposed YAML alongside the closest existing pipeline
    YAML, highlighting what changed. Includes rationale for each override.
11. **Human approval checkpoint** (mandatory): user approves, requests changes, or aborts.
    - If changes requested: agent patches YAML and returns to step 10.
    - If approved: continue.
12. Agent saves `pipeline_defs/<name>.yaml` to disk.
13. Agent confirms: "Pipeline `<name>` is now available. Run it with: [how to invoke]."
14. Agent offers immediate run or defers to user.

**Critical gates:**
- Step 6: schema validation failure → abort with error, do not proceed.
- Step 11: human approval is non-negotiable; no auto-proceed even if confidence is HIGH.
- Step 12: write only after approval; never speculatively write to `pipeline_defs/`.

---

## Table Stakes vs Differentiators Summary (S/M/L)

| Feature | Category | Size | P-level |
|---------|----------|------|---------|
| URL/file ingestion | Stake | S | P1 |
| 4-dimension structured extraction | Stake | M | P1 |
| Schema validation of analysis artifact | Stake | S | P1 |
| Human-readable analysis summary | Stake | S | P1 |
| Pipeline suggestion with rationale | Stake | S | P1 |
| Pipeline diff view | Stake | M | P1 |
| Human approval checkpoint | Stake | S | P1 |
| Synthesized pipeline saved + validated | Stake | M | P1 |
| Pipeline available in registry post-save | Stake | S | P1 |
| PySceneDetect + Gemini hybrid detection | Differentiator | M | P1 |
| Remotion scene-type mapping in output | Differentiator | S | P1 |
| `paragraph_pattern` template field | Differentiator | S | P2 |
| Playbook matching + delta generation | Differentiator | M | P1 |
| Director-skill reuse selection | Differentiator | S | P1 |
| `video_analysis_selector` pattern | Differentiator | S | P2 |

---

## Which Dimension Is Hardest to Get Right

**Ranked hardest to easiest:**

1. **Narrative** (hardest) — Requires reasoning across the whole video to identify section
   boundaries. Gemini is good at hooks and CTAs (salient, at edges) but struggles with
   mid-video section delineation on videos without strong verbal markers. On videos > 5
   minutes, accuracy of `section_count` and `section_structure` degrades noticeably.
   Mitigation: anchor section detection on the transcript, not just visual analysis;
   validate `section_count` against word-count distribution.

2. **Audio** — `music_tempo_bpm` and `voice_gender` are reliable enough. The tricky field
   is `music_genre`: Gemini produces useful free-text but the enum needs to be constrained
   carefully or you get inconsistent labels (e.g., "upbeat electronic" vs "electronic pop").
   Define the enum vocabulary in the schema before shipping.

3. **Editing + Pacing** — PySceneDetect + Gemini hybrid is highly reliable for `cuts_per_minute`
   and `avg_shot_duration`. The gap: `b_roll_ratio` is estimated from per-scene labels, and
   Gemini occasionally misclassifies talking-head with cutaways as b-roll. Acceptable for
   pipeline selection; document the uncertainty.

4. **Visual Style** (easiest) — Color palette, motion style, and production quality are
   highly reliable from keyframe analysis. Gemini is strong at holistic visual assessment.
   Typography identification is the weak spot (see anti-features), but `typography_style`
   as description is sufficient.

---

## Shot Detection Strategy: PySceneDetect vs Gemini

**Recommendation: Hybrid — PySceneDetect for boundaries, Gemini for labels.**

| Approach | Pros | Cons | Use For |
|----------|------|------|---------|
| PySceneDetect ContentDetector | Deterministic, frame-accurate, catches < 0.5s cuts, free, fast | No semantic labels, no motion_type | Boundary detection, `cuts_per_minute`, `total_shots` |
| PySceneDetect AdaptiveDetector | Fewer false positives on camera-motion-heavy content | Slower (two-pass), may miss some fast cuts | Preferred for cinematic/documentary content |
| Gemini vision alone | Semantic labels, understands context | 1fps default misses fast cuts; hallucination risk on dense edits | Per-scene classification ONLY (after boundaries from PySceneDetect) |
| FFmpeg keyframe extraction | Fast, no extra dependency | Keyframe intervals ≠ shot boundaries; not reliable for detection | Pre-processing step to extract frames for Gemini input |

**Concrete approach:**
1. Run `scene_detect` (wraps PySceneDetect) → `shot_boundaries` list.
2. Extract 1-2 representative frames per shot with `frame_sampler`.
3. Send shot boundaries + sampled frames to `gemini_video_analyzer` as structured input.
4. Gemini classifies each shot: `visual_type`, `motion_type`, `energy_level`, `dominant_colors`,
   `on_screen_text`.
5. Agent derives aggregate metrics (`b_roll_ratio`, `pacing_style`, etc.) from per-shot labels.

`scene_detect` already exists in v1.0. `frame_sampler` already exists in v1.0.
Only `gemini_video_analyzer` is new.

---

## Sources

- Gemini API video understanding docs: https://ai.google.dev/gemini-api/docs/video-understanding
- Gemini structured output docs: https://ai.google.dev/gemini-api/docs/structured-output
- PySceneDetect ContentDetector + AdaptiveDetector docs: https://www.scenedetect.com/docs/latest/api/detectors.html
- PySceneDetect GitHub: https://github.com/Breakthrough/PySceneDetect
- Video-MME (CVPR 2025 benchmark for multimodal LLMs in video): https://github.com/MME-Benchmarks/Video-MME
- LumiVideo agentic color grading (LLM-as-Judge for visual quality): https://arxiv.org/abs/2604.02409
- HITL pipeline patterns (Zapier blog): https://zapier.com/blog/human-in-the-loop/
- Existing codebase: `schemas/artifacts/video_analysis_brief.schema.json` (v1.0 baseline)
- Existing codebase: `pipeline_defs/animated-explainer.yaml`, `cinematic.yaml` (manifest shape)
- Existing codebase: `styles/clean-professional.yaml` (playbook schema reference)
- Existing codebase: `skills/meta/video-reference-analyst.md` (current baseline behavior)

---
*Feature research for: v2.0 Reference Synthesis — OpenMontage*
*Researched: 2026-04-17*
