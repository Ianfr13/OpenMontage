"""Capability-level selector routing between video_analysis providers.

Auto-discovers any BaseTool with capability="video_analysis" from the registry
and picks one per ANLZ-01 preference order:

    1. inputs["preferred_provider"] (if != "auto")
    2. os.environ["VIDEO_ANALYZER_PROVIDER"] (if set and != "auto")
    3. First provider whose required API key is present — GEMINI_API_KEY|GOOGLE_API_KEY -> gemini, OPENROUTER_API_KEY -> openrouter
    4. First AVAILABLE provider in discovery order

Return shape: the underlying provider's ToolResult.data IS the canonical
video_analysis artifact (validates against schemas/artifacts/video_analysis.schema.json).
Selector-specific metadata (selected_tool, selected_provider) is stamped on
ToolResult fields — NOT on data — to avoid breaking ANLZ-06 (Phase 3 constraint:
caller cannot tell which backend ran from the artifact alone).
"""

from __future__ import annotations

import os
from typing import Any

from tools.base_tool import (
    BaseTool,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class VideoAnalyzerSelector(BaseTool):
    name = "video_analyzer_selector"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "video_analysis"
    provider = "selector"
    stability = ToolStability.BETA
    runtime = ToolRuntime.HYBRID
    agent_skills = ["gemini-video-analysis", "openrouter-video-analysis"]

    best_for = [
        "routing between video_analysis providers",
        "gemini-direct vs openrouter preference by env var",
    ]

    input_schema = {
        "type": "object",
        "required": ["video_path"],
        "properties": {
            "video_path": {
                "type": "string",
                "description": "Path to a local video file (mp4, mov, mpeg, avi, webm, etc.).",
            },
            "shot_boundaries": {
                "type": "array",
                "description": (
                    "Optional shot-boundary hints from scene_detect. "
                    "Each entry may be [start_s, end_s] OR "
                    "{'start_seconds': ..., 'end_seconds': ...}. "
                    "When omitted, provider infers; artifact sets "
                    "shot_boundary_source='model'."
                ),
                "items": {"type": ["array", "object"]},
            },
            "analysis_depth": {
                "type": "string",
                "enum": ["full", "compact"],
                "default": "full",
            },
            "preferred_provider": {
                "type": "string",
                "description": "Provider name (e.g., 'gemini'), 'auto', or a registered provider's name string.",
                "default": "auto",
            },
            "max_poll_seconds": {
                "type": "number",
                "description": "Max wall-clock wait for Files API to reach ACTIVE (passed through to Gemini provider).",
                "default": 300.0,
            },
        },
    }

    def _providers(self) -> list[BaseTool]:
        """Auto-discover video_analysis providers from the registry, excluding self."""
        from tools.tool_registry import registry
        registry.ensure_discovered()
        return [
            t for t in registry.get_by_capability("video_analysis")
            if t.name != self.name
        ]

    def get_status(self) -> ToolStatus:
        if any(t.get_status() == ToolStatus.AVAILABLE for t in self._providers()):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        providers = self._providers()
        if not providers:
            return ToolResult(
                success=False,
                error="No video_analysis provider registered. Install one (e.g., gemini_video_analyzer) and ensure its API key is set.",
            )

        chosen = self._pick(inputs, providers)
        if chosen is None:
            return ToolResult(
                success=False,
                error="No available video_analysis provider. Set GEMINI_API_KEY (or OPENROUTER_API_KEY once Phase 3 lands) in .env.",
            )

        result = chosen.execute(inputs)
        # Stamp selector metadata on ToolResult fields, NOT data (ANLZ-06 / Pitfall 7).
        # data must remain the canonical video_analysis artifact.
        if result.success:
            if result.model is None:
                result.model = chosen.name
        return result

    def _pick(self, inputs: dict[str, Any], providers: list[BaseTool]) -> BaseTool | None:
        available = [t for t in providers if t.get_status() == ToolStatus.AVAILABLE]
        if not available:
            return None
        by_provider: dict[str, BaseTool] = {}
        for t in available:
            by_provider.setdefault(t.provider, t)  # first-seen wins (discovery order)

        # 1. Explicit user choice
        preferred = str(inputs.get("preferred_provider") or "auto").lower()
        if preferred != "auto":
            if preferred in by_provider:
                return by_provider[preferred]
            # Also accept tool-name match (e.g., "gemini_video_analyzer")
            for t in available:
                if t.name == preferred:
                    return t
            # REVIEW MD-05: explicit preference with no match must NOT
            # silently fall through to env-var logic — the caller asked
            # for a specific provider and deserves a deterministic error.
            return None

        # 2. Env override
        env_pref = os.environ.get("VIDEO_ANALYZER_PROVIDER", "auto").lower()
        if env_pref != "auto" and env_pref in by_provider:
            return by_provider[env_pref]

        # 3. API-key presence tie-break (ANLZ-01 strict order)
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            if "gemini" in by_provider:
                return by_provider["gemini"]
        if os.environ.get("OPENROUTER_API_KEY"):
            if "openrouter" in by_provider:
                return by_provider["openrouter"]

        # 4. Fallback: first available in discovery order
        return available[0]
