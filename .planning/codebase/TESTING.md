# Testing Patterns

**Analysis Date:** 2026-04-17

## Test Framework

**Runner:**
- pytest 8.0+
- Config: `requirements-dev.txt` declares `pytest>=8.0` and `pytest-asyncio>=0.23`
- Location: `tests/` directory (not co-located with source)

**Assertion Library:**
- pytest built-in assertions (no external assertion library)

**Run Commands:**
```bash
make test                    # Run all tests in tests/
make test-contracts         # Run contract tests in tests/contracts/
python -m pytest tests/ -v  # Verbose pytest run
```

**Async Testing:**
- Uses `pytest-asyncio>=0.23` for async test support
- Mark async tests with `@pytest.mark.asyncio`

## Test File Organization

**Location:**
- Tests are separated from source code in `tests/` directory (not co-located)
- Mirror the structure of `tools/` and `lib/` where applicable

**Test Directory Structure:**
```
tests/
├── __init__.py
├── contracts/              # Phase-based contract testing
│   ├── __init__.py
│   ├── test_phase0_contracts.py
│   ├── test_phase1_contracts.py
│   ├── test_phase1_golden.py
│   ├── test_phase2_contracts.py
│   ├── test_phase2_comparison.py
│   ├── test_phase3_contracts.py
│   └── ...
├── tools/                  # Tool-specific tests
│   ├── __init__.py
│   ├── test_clip_cache.py
│   ├── test_documentary_governance.py
│   ├── test_stock_source_adapters.py
│   └── ...
├── qa/                     # Quality assurance and integration tests
│   ├── __init__.py
│   ├── test_04_audio_mix.py
│   ├── test_05_video_compose.py
│   ├── test_06_video_stitch.py
│   ├── test_07_playbook_intelligence.py
│   └── test_08_end_to_end.py
├── pipelines/              # Pipeline-specific tests
│   ├── __init__.py
│   └── ...
├── styles/                 # Style/playbook tests
│   ├── __init__.py
│   └── ...
├── eval/                   # Evaluation/performance tests
│   ├── __init__.py
│   └── ...
└── output/                 # Generated test artifacts (not committed)
```

**Naming Conventions:**
- Test files: `test_<feature>.py`
- Test classes: `Test<Feature>` or `Test<Feature><Aspect>`
- Test functions: `test_<behavior>_<expected_result>` or `test_<behavior>`
- Example: `TestPhase1ToolContracts`, `test_inherits_base_tool`, `test_has_required_identity`

## Test Structure

**Suite Organization:**
Test files are organized by concern (contract validation, integration, tools, QA). Example from `tests/contracts/test_phase1_contracts.py`:

```python
import pytest
from tools.base_tool import BaseTool, ToolResult

PHASE1_TOOLS = [
    Transcriber,
    VideoTrimmer,
    SubtitleGen,
    FrameSampler,
    AudioMixer,
    VideoCompose,
]

class TestPhase1ToolContracts:
    """Verify all Phase 1 tools satisfy the ToolContract."""
    
    @pytest.mark.parametrize("tool_cls", PHASE1_TOOLS)
    def test_inherits_base_tool(self, tool_cls):
        assert issubclass(tool_cls, BaseTool)
    
    @pytest.mark.parametrize("tool_cls", PHASE1_TOOLS)
    def test_has_required_identity(self, tool_cls):
        tool = tool_cls()
        assert tool.name, f"{tool_cls.__name__} must have a non-empty name"
        assert tool.version, f"{tool_cls.__name__} must have a version"
```

**Parametrize Pattern:**
- Use `@pytest.mark.parametrize()` for testing multiple tools or scenarios
- Reduces test code duplication by running the same test over multiple inputs

**Setup and Teardown:**
- Use pytest fixtures for setup/teardown
- Example from `tests/tools/test_clip_cache.py`:
  ```python
  def test_cache_entry_round_trip_through_dict():
      entry = CacheEntry(
          clip_id="test_001",
          file_name="test_001.mp4",
          size_bytes=42,
          added_at=1000.0,
          last_access_at=2000.0,
          source="test_source",
          source_id="001",
          source_url="https://example.test/001",
          license="CC0",
          creator="rig",
          source_tags="smoke test",
      )
      d = entry.to_dict()
      restored = CacheEntry.from_dict(d)
      assert restored == entry
  ```
- Use `monkeypatch` fixture for environment variable manipulation:
  ```python
  def test_default_cache_dir_uses_env_override(monkeypatch, tmp_path):
      monkeypatch.setenv("OPENMONTAGE_CACHE_DIR", str(tmp_path / "overridden"))
      assert default_cache_dir() == tmp_path / "overridden"
  ```

## Contract Testing (Phase-Based)

OpenMontage uses **phase-based contract testing** to validate tool and framework compliance:

**Phases:**
- **Phase 0:** Framework foundation (checkpoints, manifests, schemas)
- **Phase 1:** Core tools (transcriber, trimmer, audio mixer, video compose)
- **Phase 2:** Selector tools (tts_selector, image_selector, video_selector)
- **Phase 3:** Advanced tools and governance

**Location:**
- `tests/contracts/test_phase0_contracts.py` — framework/checkpoint validation
- `tests/contracts/test_phase1_contracts.py` — core tool contracts
- `tests/contracts/test_phase2_contracts.py` — selector contracts
- `tests/contracts/test_phase3_contracts.py` — advanced contracts

**Contract Assertions:**
Each tool must satisfy:
1. Inherits from `BaseTool`
2. Has required identity fields: `name`, `version`, `tier`, `capability`, `stability`
3. Has `input_schema` and `output_schema` dicts
4. Implements `execute(inputs: dict) -> ToolResult`
5. `get_info()` returns valid dict with expected keys
6. `get_status()` returns one of `AVAILABLE`, `UNAVAILABLE`, `DEGRADED`

**Example from `tests/contracts/test_phase1_contracts.py`:**
```python
class TestPhase1ToolContracts:
    @pytest.mark.parametrize("tool_cls", PHASE1_TOOLS)
    def test_inherits_base_tool(self, tool_cls):
        assert issubclass(tool_cls, BaseTool)

    @pytest.mark.parametrize("tool_cls", PHASE1_TOOLS)
    def test_has_required_identity(self, tool_cls):
        tool = tool_cls()
        assert tool.name, f"{tool_cls.__name__} must have a non-empty name"
        assert tool.version, f"{tool_cls.__name__} must have a version"
        assert tool.tier in ToolTier

    @pytest.mark.parametrize("tool_cls", PHASE1_TOOLS)
    def test_get_info_returns_valid_dict(self, tool_cls):
        tool = tool_cls()
        info = tool.get_info()
        assert isinstance(info, dict)
        assert info["name"] == tool.name
        assert info["tier"] in [t.value for t in ToolTier]
```

## QA Integration Tests

**Location:**
`tests/qa/` contains end-to-end pipeline and stage simulations

**test_08_end_to_end.py:**
- Walks through all 7 stages (research → propose → script → scene_plan → assets → edit → compose)
- Uses synthetic fixtures (generates test MP4s/MP3s with FFmpeg)
- No API keys required
- Validates checkpoints, artifact schemas, cost tracking at each stage
- Main test routine:
  ```python
  def check(name, condition, detail=""):
      """Helper to track pass/fail counts."""
      global PASS, FAIL
      if condition:
          PASS += 1
          print(f"  [PASS] {name}")
      else:
          FAIL += 1
          print(f"  [FAIL] {name}")
  
  # Fixture generation
  def ensure_video(path, duration=5, width=1280, height=720, color="blue"):
      """Create dummy video file for testing."""
      subprocess.run([
          "ffmpeg", "-y", "-f", "lavfi",
          "-i", f"color=c={color}:s={width}x{height}:d={duration}:r=30",
          "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
          path
      ], capture_output=True, check=True)
  ```

**Other QA tests:**
- `test_04_audio_mix.py` — audio mixing tool functionality
- `test_05_video_compose.py` — video composition and rendering
- `test_06_video_stitch.py` — clip stitching and concatenation
- `test_07_playbook_intelligence.py` — style/playbook validation

## Tool Testing Patterns

**Test individual tool contracts (from `tests/tools/`):**

Example from `tests/tools/test_clip_cache.py`:
- Tests cache entry round-trip serialization
- Tests LRU eviction logic
- Tests cache manifest persistence
- Uses `tmp_path` fixture to scope cache directories
- No network access required

**Fixture helpers for tools:**
- Helper functions generate fake test data (e.g., `_fake_clip()`)
- Use test metadata with `_default_metadata()` helper
- Example:
  ```python
  def _fake_clip(path: Path, size_bytes: int) -> Path:
      """Write a fixed-size dummy file and return the path."""
      path.parent.mkdir(parents=True, exist_ok=True)
      with open(path, "wb") as f:
          f.write(b"x" * size_bytes)
      return path
  
  def _default_metadata(clip_id: str = "test_001") -> dict:
      return {
          "source": "test_source",
          "source_id": clip_id.split("_", 1)[-1],
          "source_url": f"https://example.test/{clip_id}",
          "license": "CC0",
          "creator": "test_rig",
          "source_tags": "smoke test metadata",
      }
  ```

## Mocking Patterns

**Framework:**
- pytest built-in `monkeypatch` fixture for mocking environment variables
- No external mocking library required (none imported in visible tests)

**What to Mock:**
- Environment variables: use `monkeypatch.setenv()`
- File paths: use `tmp_path` fixture
- Network/API calls: not tested (smoke tests use local-only tools)

**What NOT to Mock:**
- Tool dependencies check (let actual dependency detection run)
- Artifact schema validation (always validate against real schemas)
- Checkpoint state (persist to real JSON files in test directories)
- FFmpeg/local tools (let them run — they're free and deterministic)

**Example from `tests/tools/test_clip_cache.py`:**
```python
def test_default_cache_dir_uses_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENMONTAGE_CACHE_DIR", str(tmp_path / "overridden"))
    assert default_cache_dir() == tmp_path / "overridden"

def test_default_cache_dir_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("OPENMONTAGE_CACHE_DIR", raising=False)
    result = default_cache_dir()
    assert result == Path.home() / ".openmontage" / "clips_cache"
```

**Environment isolation:**
- Use `monkeypatch.setenv()` and `monkeypatch.delenv()` to isolate tests
- Never modify global `os.environ` directly in tests
- Always restore state after test (pytest handles via fixture)

## Schema Validation in Tests

**Testing artifact validation:**
- Import `validate_artifact()` from `schemas/artifacts/__init__.py`
- Load schemas via `load_schema(name)`
- Example from `tests/qa/test_08_end_to_end.py`:
  ```python
  from schemas.artifacts import validate_artifact, list_schemas
  
  # Validate that artifact matches its schema
  try:
      validate_artifact("script", script_artifact)
      print("[PASS] Script artifact validates")
  except jsonschema.ValidationError as e:
      print(f"[FAIL] Script validation failed: {e}")
  ```

**Testing checkpoint validation:**
- Checkpoints must include canonical artifact for `completed` and `awaiting_human` statuses
- Use `write_checkpoint()` and `read_checkpoint()` from `lib/checkpoint.py`
- Validation happens automatically on read

## Coverage

**Requirements:**
- No explicit coverage threshold enforced in visible config
- Phase-based contract tests provide coverage of critical paths
- QA tests provide integration/smoke test coverage

**Coverage Check:**
- pytest can generate coverage reports with plugin:
  ```bash
  pytest tests/ --cov=tools --cov=lib --cov-report=term-missing
  ```

## Framework-Smoke Pipeline

**Location:** `tests/qa/` or custom test using `pipeline_defs/framework-smoke.yaml`

**Purpose:**
- Minimal pipeline manifest exercising core framework contracts
- No actual tool execution — tests checkpoint/artifact validation only
- Good for testing phase structure without tool dependencies

**Usage:**
```python
from lib.pipeline_loader import load_pipeline

manifest = load_pipeline("framework-smoke")
# Verify manifest structure, stage order, artifact contracts
```

## CI/CD Configuration

**Present:**
- `.github/workflows/` directory exists
- No workflow files visible in this analysis
- Makefile provides test targets

**Local Testing:**
```bash
make test              # Run pytest on tests/
make test-contracts    # Run contract tests only
```

## Test Data & Fixtures

**Locations:**
- Inline fixture generation (FFmpeg-based synthetic media)
- Test output directory: `tests/output/` (not committed, regenerated per run)
- Project directory: `projects/<project-id>/` for pipeline runs (gitignored)

**Synthetic Media Generation:**
All test media is generated via FFmpeg, never committed:
```python
def ensure_video(path, duration=5, width=1280, height=720, color="blue"):
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:d={duration}:r=30",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", path
    ], capture_output=True, check=True)
```

## Module Import Pattern in Tests

**Standard imports:**
```python
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment before imports
from lib.env_loader import load_env
load_env()

# Then import tools/lib
from tools.base_tool import BaseTool, ToolResult
from lib.checkpoint import write_checkpoint, read_checkpoint
```

**Why this pattern:**
- Ensures PROJECT_ROOT is in sys.path before any local imports
- Loads .env early so tools can access API keys/config
- Avoids path-dependent test failures when run from different directories

## Running Tests Locally

**Prerequisites:**
```bash
pip install -r requirements-dev.txt    # pytest + pytest-asyncio
pip install ffmpeg                     # For media generation in QA tests
```

**Execute:**
```bash
cd /workspace
make test                               # All tests
make test-contracts                     # Contract tests only
python -m pytest tests/qa/ -v           # QA tests with verbose output
python -m pytest tests/tools/test_clip_cache.py::test_default_cache_dir_uses_env_override -v
```

**Coverage Report (if pytest-cov installed):**
```bash
pytest tests/ --cov=tools --cov=lib --cov-report=html
# Opens htmlcov/index.html
```

---

*Testing analysis: 2026-04-17*
