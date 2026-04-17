"""Environment variable loader for OpenMontage.

Loads ``.env`` file and provides typed access to environment configuration via
``load_env()``, ``get_env(key, default)``, and ``require_env(key)``.

v2.0 env var catalog (Reference Synthesis milestone)
====================================================

All v2.0 env vars introduced by the video analysis + pipeline synthesis stack.
Consumers MUST use this module (``get_env`` / ``require_env``) rather than
reading ``os.environ`` directly, to centralize defaults and documentation.

+-------------------------+-------------------------------------+---------------------------------+--------------------------------------------------------------+
| Env Var                 | Consumer                            | Default                         | Purpose                                                      |
+=========================+=====================================+=================================+==============================================================+
| ``GEMINI_API_KEY``      | ``tools/analysis/gemini_video_analyzer`` | (unset)                    | Primary Gemini auth; priority over ``GOOGLE_API_KEY``.       |
+-------------------------+-------------------------------------+---------------------------------+--------------------------------------------------------------+
| ``GOOGLE_API_KEY``      | ``tools/analysis/gemini_video_analyzer`` | (unset)                    | Fallback Gemini auth used when ``GEMINI_API_KEY`` unset.     |
+-------------------------+-------------------------------------+---------------------------------+--------------------------------------------------------------+
| ``OPENROUTER_API_KEY``  | ``tools/analysis/openrouter_video_analyzer``, ``lib/llm_fill`` | (unset)        | OpenRouter auth for video analysis and LLM-fill.             |
+-------------------------+-------------------------------------+---------------------------------+--------------------------------------------------------------+
| ``GEMINI_VIDEO_MODEL``  | ``tools/analysis/gemini_video_analyzer`` | ``gemini-3.1-pro-preview`` | Gemini model override. Falls back to ``gemini-2.5-pro`` if   |
|                         |                                     |                                 | preview unavailable.                                         |
+-------------------------+-------------------------------------+---------------------------------+--------------------------------------------------------------+
| ``OPENROUTER_MODEL``    | ``tools/analysis/openrouter_video_analyzer`` | ``google/gemini-3.1-pro-preview`` | OpenRouter model override.                            |
+-------------------------+-------------------------------------+---------------------------------+--------------------------------------------------------------+
| ``VIDEO_ANALYZER_PROVIDER`` | ``tools/analysis/video_analyzer_selector`` | ``auto``                | Force provider routing: ``gemini``, ``openrouter``, or       |
|                         |                                     |                                 | ``auto`` (key-presence heuristic).                           |
+-------------------------+-------------------------------------+---------------------------------+--------------------------------------------------------------+
| ``VIDEO_CHUNK_WORKERS`` | ``lib/chunked_analyzer``            | ``4``                           | ThreadPoolExecutor ``max_workers`` for chunked analysis.     |
|                         |                                     |                                 | Clamped to ``[1, 8]``; invalid value falls back with WARNING.|
+-------------------------+-------------------------------------+---------------------------------+--------------------------------------------------------------+
| ``VIDEO_SYNTH_LLM_FILL``| ``lib/pipeline_synthesizer`` via ``lib/llm_fill`` | ``true``           | Toggle LLM-fill during synthesis: any value other than       |
|                         |                                     |                                 | ``false`` enables it. When enabled but ``OPENROUTER_API_KEY``|
|                         |                                     |                                 | is missing, fill_stage_details falls back to no-op.          |
+-------------------------+-------------------------------------+---------------------------------+--------------------------------------------------------------+

Pre-v2.0 env vars (TTS, image/video gen providers, etc.) are documented per-tool
via ``tool.install_instructions`` in the registry — not in this module.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env(project_root: Optional[Path] = None) -> None:
    """Load .env file from project root."""
    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get an environment variable with optional default."""
    return os.environ.get(key, default)


def require_env(key: str) -> str:
    """Get a required environment variable. Raises if missing."""
    value = os.environ.get(key)
    if value is None:
        raise EnvironmentError(f"Required environment variable {key!r} is not set")
    return value
