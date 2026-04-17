# Coding Conventions

**Analysis Date:** 2026-04-17

## Naming Patterns

**Files:**
- Snake_case for module names: `elevenlabs_tts.py`, `video_compose.py`, `frame_sampler.py`, `audio_mixer.py`
- Hyphenated for skill files: `idea-director.md`, `compose-director.md`, `script-director.md`
- Hyphenated for YAML manifests: `framework-smoke.yaml`, `animated-explainer.yaml`, `screen-demo.yaml`
- All caps with underscores for schema/artifact names: `ARTIFACT_NAMES`, `CANONICAL_STAGE_ARTIFACTS`

**Classes:**
- PascalCase without "Tool" suffix. This is mandatory:
  - `ElevenLabsTTS` not `ElevenLabsTTSTool` (file: `tools/audio/elevenlabs_tts.py`)
  - `VideoCompose` not `VideoComposeTool` (file: `tools/video/video_compose.py`)
  - `FrameSampler` not `FrameSamplerTool` (file: `tools/analysis/frame_sampler.py`)
  - `Transcriber` not `TranscriberTool` (file: `tools/analysis/transcriber.py`)
  - `AudioMixer` not `AudioMixerTool` (file: `tools/audio/audio_mixer.py`)

**Functions:**
- snake_case for all functions and methods
- Prefixed with underscore for private/internal methods: `_load_checkpoint_schema()`, `_load_dotenv()`, `_extract_interval()`
- Verb-first for action functions: `load_pipeline()`, `validate_artifact()`, `get_status()`, `check_dependencies()`

**Variables:**
- snake_case for all local and module-level variables
- UPPERCASE_WITH_UNDERSCORES for constants: `PIPELINE_DEFS_DIR`, `SCHEMA_PATH`, `STAGES`

**Enums:**
- PascalCase: `ToolTier`, `ToolStatus`, `ToolRuntime`, `Determinism`, `ExecutionMode`
- Members are UPPERCASE: `ToolStatus.AVAILABLE`, `ToolRuntime.LOCAL`, `Determinism.DETERMINISTIC`

**Dict keys:**
- snake_case for all dictionary keys: `input_schema`, `output_schema`, `artifact_schema`
- YAML manifest keys: kebab-case: `human_approval_default`, `tools_available` (becomes camelCase in YAML)

## Code Style

**Formatting:**
- Black is the expected formatter (no explicit config found but pattern is visible)
- 88-character line length (Black default)
- Type hints required for all function signatures via `from __future__ import annotations`
- Docstrings on all modules, classes, and public functions

**Type Hints:**
- Use `from __future__ import annotations` at the top of every module (mandatory)
- All function parameters and returns must have type hints
- Use generic types: `dict[str, Any]`, `list[str]`, `Optional[Path]`
- Union types: `str | None` (Python 3.10+ syntax)
- Examples from codebase:
  ```python
  def load_pipeline(name: str, defs_dir: Optional[Path] = None) -> dict[str, Any]:
  def get_status(self) -> ToolStatus:
  def execute(self, inputs: dict[str, Any]) -> ToolResult:
  ```

**Imports:**
- Order: Standard library → Third-party → Local imports
- Group imports with blank lines separating groups
- Avoid star imports (`from module import *`)
- Example from `tools/base_tool.py`:
  ```python
  from __future__ import annotations
  
  import hashlib
  import inspect
  import json
  import os
  import platform
  import subprocess
  import shutil
  from abc import ABC, abstractmethod
  from dataclasses import dataclass, field
  from enum import Enum
  from pathlib import Path
  from typing import Any, Callable, Optional
  ```

**Linting:**
- No explicit linting config found (no `.flake8`, `ruff.toml`, or `.pylintrc`)
- Follow PEP 8 conventions
- Avoid bare `except:` clauses; always specify exception type
- Use context managers (`with`) for resource management

## Error Handling

**Patterns:**
- Catch specific exceptions, never bare `except:`
- Define custom exception classes for domain errors
- Example from `tools/base_tool.py`:
  ```python
  class DependencyError(Exception):
      """Raised when a tool's dependency is not satisfied."""
      pass
  ```
- For tools: catch dependencies and return `ToolResult(success=False, error=msg)` rather than raising
- Example from `tools/analysis/frame_sampler.py`:
  ```python
  if not input_path.exists():
      return ToolResult(success=False, error=f"Input not found: {input_path}")
  ```
- For status checking: catch exceptions in `get_status()` and return `ToolStatus.UNAVAILABLE`
  ```python
  def get_status(self) -> ToolStatus:
      try:
          self.check_dependencies()
          return ToolStatus.AVAILABLE
      except DependencyError:
          return ToolStatus.UNAVAILABLE
  ```

**Validation Errors:**
- JSON schema validation via `jsonschema.validate()` (from `schemas/artifacts/__init__.py`)
- Checkpoint validation: raise `CheckpointValidationError` from `lib/checkpoint.py`
- Pipeline validation: raise during `load_pipeline()` via jsonschema

## BaseTool Pattern (Mandatory for All Tools)

All tools must inherit from `BaseTool` in `tools/base_tool.py`. Required fields:

**Identity (class attributes):**
- `name: str` — tool identifier (matches filename, underscore-separated)
- `version: str` — semantic version (e.g., "0.1.0")
- `tier: ToolTier` — one of CORE, VOICE, ENHANCE, GENERATE, SOURCE, ANALYZE, PUBLISH
- `capability: str` — capability family (e.g., "tts", "video_post", "analysis")
- `provider: str` — provider name (e.g., "elevenlabs", "ffmpeg", "openai")
- `stability: ToolStability` — EXPERIMENTAL, BETA, or PRODUCTION
- `execution_mode: ExecutionMode` — SYNC or ASYNC
- `determinism: Determinism` — DETERMINISTIC, SEEDED, or STOCHASTIC

**Dependencies & Installation:**
- `dependencies: list[str]` — list of required dependencies
  - Format: `"cmd:ffmpeg"` for CLI commands, `"env:API_KEY_NAME"` for env vars, `"python:module_name"` for packages
- `install_instructions: str` — human-readable setup guide
- `fallback: Optional[str]` — single fallback tool name
- `fallback_tools: list[str]` — list of all fallback tools

**Capabilities & Schemas:**
- `capabilities: list[str]` — what this tool can do (e.g., `["transcribe", "word_timestamps", "diarization"]`)
- `input_schema: dict` — JSON schema for inputs (required, must have "properties" and "required" keys)
- `output_schema: dict` — JSON schema for outputs
- `artifact_schema: dict` — schema for side-effect artifacts
- `supports: dict[str, Any]` — capability matrix (e.g., `{"voice_cloning": True, "multilingual": True}`)
- `best_for: list[str]` — use cases where this tool excels
- `not_good_for: list[str]` — known limitations

**Agent Skills:**
- `agent_skills: list[str]` — references to `.agents/skills/` directories containing Layer 3 vendor knowledge
- Example: `agent_skills = ["elevenlabs", "text-to-speech"]` means read `.agents/skills/elevenlabs/` and `.agents/skills/text-to-speech/` before using this tool

**Resources & Execution:**
- `resource_profile: ResourceProfile` — CPU/RAM/VRAM/disk requirements
- `retry_policy: RetryPolicy` — max_retries, backoff_seconds, retryable_errors list
- `runtime: ToolRuntime` — LOCAL, LOCAL_GPU, API, or HYBRID

**Methods (must implement):**
- `execute(inputs: dict[str, Any]) -> ToolResult` — main tool logic
  - Return `ToolResult(success=True, data={...}, artifacts=[...])` on success
  - Return `ToolResult(success=False, error="message")` on failure
  - Include `cost_usd`, `duration_seconds`, `seed`, `model` in result
- `dry_run(inputs: dict[str, Any]) -> dict[str, Any]` — override to check inputs without side effects
- `estimate_cost(inputs: dict[str, Any]) -> float` — override for paid tools
- `estimate_runtime(inputs: dict[str, Any]) -> float` — override for long-running tools

**Example from `tools/audio/elevenlabs_tts.py`:**
```python
class ElevenLabsTTS(BaseTool):
    name = "elevenlabs_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "elevenlabs"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API
    
    dependencies = []  # Checked in check_dependencies()
    install_instructions = "Set ELEVENLABS_API_KEY env var..."
    fallback = "openai_tts"
    fallback_tools = ["openai_tts", "piper_tts"]
    agent_skills = ["elevenlabs", "text-to-speech"]
    
    capabilities = ["text_to_speech", "voice_selection", "ssml_support"]
    supports = {"voice_cloning": True, "multilingual": True}
    best_for = ["high-quality narration", "voice-sensitive videos"]
    
    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {...}
    }
    
    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        # Implementation
        ...
```

## ToolResult Return Pattern

All `execute()` methods return `ToolResult` dataclass from `tools/base_tool.py`:

```python
@dataclass
class ToolResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    error: Optional[str] = None
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    seed: Optional[int] = None
    model: Optional[str] = None
```

**Usage:**
- `success=True`: operation completed. Include `data` with output and `artifacts` with file paths.
- `success=False`: operation failed. Always include `error` message.
- `cost_usd`: track spending for budget governance
- `duration_seconds`: track performance
- `seed`: for reproducibility (if operation is seeded)
- `model`: for audit trail (which model version was used)

**Example from `tools/analysis/frame_sampler.py`:**
```python
def execute(self, inputs: dict[str, Any]) -> ToolResult:
    if not input_path.exists():
        return ToolResult(success=False, error=f"Input not found: {input_path}")
    
    # ... do work ...
    
    return ToolResult(
        success=True,
        data={
            "frame_count": len(frames),
            "extraction_strategy": strategy,
            "frames": [str(f) for f in frames],
        },
        artifacts=[str(f) for f in frames],
        duration_seconds=time.time() - start,
    )
```

## Comments & Documentation

**Module docstrings:**
- Every Python file starts with a module docstring explaining what it does
- One-liner followed by detailed description
- Example from `tools/base_tool.py`:
  ```python
  """Base tool class implementing the expanded ToolContract.
  
  Every tool in OpenMontage inherits from BaseTool. This enforces a uniform
  interface for discovery, execution, cost estimation, and health reporting.
  """
  ```

**Class docstrings:**
- Required for all classes
- Describe the purpose and main behavior

**Function docstrings:**
- Required for all public functions
- Use standard format: one-liner + Args + Returns
- Example from `lib/checkpoint.py`:
  ```python
  def get_pipeline_stages(pipeline_type: str | None) -> list[str]:
      """Return the ordered stage list for a specific pipeline.
  
      Falls back to STAGES (deterministic canonical order) when pipeline_type
      is not provided or the manifest cannot be loaded.
      """
  ```

**Inline comments:**
- Only for non-obvious logic
- Avoid comments that restate the code
- Use `# ---` to mark section breaks in long functions

**No type comments:**
- Always use function signature type hints, never `# type:` comments

## YAML Manifest Conventions

**Pipeline manifests** in `pipeline_defs/`:
- File: `pipeline_name.yaml` (kebab-case)
- Keys: snake_case (e.g., `human_approval_default`, `tools_available`, `stage_order`)
- Validated against schema in `schemas/pipelines/pipeline_manifest.schema.json`
- Example from `pipeline_defs/framework-smoke.yaml`:
  ```yaml
  name: framework-smoke
  version: "1.0"
  description: Minimal pipeline manifest...
  stages:
    - name: research
      produces:
        - research_brief
      tools_available: []
      human_approval_default: true
  ```

**JSON Schema Files** in `schemas/`:
- Artifacts: `schemas/artifacts/<artifact_name>.schema.json`
- Pipelines: `schemas/pipelines/pipeline_manifest.schema.json`
- All use JSON Schema Draft 2020-12
- Include `$id`, `title`, `description`, `required` array, `properties` object
- Set `additionalProperties: false` to enforce strict validation
- Example from `schemas/artifacts/script.schema.json`:
  ```json
  {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "openmontage/artifacts/script",
    "type": "object",
    "required": ["version", "title", "total_duration_seconds", "sections"],
    "properties": {...},
    "additionalProperties": false
  }
  ```

## Validation Patterns

**JSON Schema validation:**
- Use `jsonschema.validate(instance=data, schema=schema)` from `schemas/artifacts/__init__.py`
- Load schemas via `load_schema(name)` or `validate_artifact(name, data)`
- Never validate manually; always use the schema system
- Raises `jsonschema.ValidationError` on failure

**Example from `schemas/artifacts/__init__.py`:**
```python
def validate_artifact(name: str, data: dict[str, Any]) -> None:
    """Validate artifact data against its schema. Raises on failure."""
    schema = load_schema(name)
    jsonschema.validate(instance=data, schema=schema)
```

**Pipeline manifest validation:**
- `load_pipeline()` in `lib/pipeline_loader.py` auto-validates against manifest schema
- Never use YAML without schema validation

## Environment Configuration

**Environment variable loading:**
- Use `lib/env_loader.py` with `load_env()` and `require_env(key)`
- `.env` file loaded once at startup
- Example from `lib/env_loader.py`:
  ```python
  def load_env(project_root: Optional[Path] = None) -> None:
      """Load .env file from project root."""
      if project_root is None:
          project_root = Path(__file__).resolve().parent.parent
      env_path = project_root / ".env"
      if env_path.exists():
          load_dotenv(env_path)
  ```
- For required vars: `require_env("API_KEY_NAME")` raises `EnvironmentError` if missing
- For optional: `get_env("VAR_NAME", default_value)`

**Dependency checking in tools:**
- BaseTool automatically loads `.env` via `_load_dotenv()` in `tools/base_tool.py`
- Never hardcode API keys; always read from environment
- Tool must list env dependencies: `dependencies = ["env:ELEVENLABS_API_KEY"]`
- `check_dependencies()` validates all declared dependencies

## Module Organization

**Tools directory structure:**
- `tools/base_tool.py` — abstract base class (never modify except for contract changes)
- `tools/tool_registry.py` — runtime discovery and provider catalog
- `tools/<category>/` — subpackage per capability (audio, video, graphics, analysis, etc.)
- `tools/<category>/<tool_name>.py` — one class per file
- File name matches tool name: `elevenlabs_tts.py` contains `ElevenLabsTTS` class

**Library directory structure:**
- `lib/` — utility modules (pipeline loading, checkpoints, cost tracking, etc.)
- All public functions documented with docstrings
- No circular dependencies between lib modules

**Skill directory structure (Layer 2 & 3):**
- `skills/pipelines/<pipeline_name>/<stage>-director.md` — orchestration guidance per stage
- `.agents/skills/<technology>/` — vendor knowledge (Layer 3)
- Markdown files, never Python

---

*Convention analysis: 2026-04-17*
