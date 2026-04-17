"""Contract tests for Phase 2 (Gemini provider) — selector + provider + SKILL.

These tests assert structural invariants that must hold regardless of the
internal mechanics. No API key needed; no network calls. All ``tools/analysis/*``
code is imported and registered via the registry.

Scope (matches ``.planning/phases/02-gemini-provider/02-04-PLAN.md``):

  * Selector registration + self-exclusion
  * Selector preference order (4 branches + zero-providers error)
  * Gemini tool contract fields (GEM-01, GEM-05)
  * Flattened-schema invariants (GEM-04 — no ``$ref``, no ``uniqueItems``,
    no ``additionalProperties: false``, but schema-valued
    ``additionalProperties`` preserved per Pitfall 4)
  * Canonical artifact gate (Phase 1 minimal fixture still validates)
  * Layer 3 skill presence + required sections (SKILL-01 — skipped when
    plan 02-03 has not yet landed the file in this worktree)
  * ``agent_skills`` wiring resolves to an on-disk ``SKILL.md``
  * No real Google API keys embedded in source or SKILL.md
  * Schema adapter idempotency (Pitfall 4 regression defense)

NOTE on filename: the plan spec names this ``test_phase2_contracts.py`` but
``tests/contracts/test_phase2_contracts.py`` already exists in this repo with
unrelated legacy Enhancement-Layer tests (FaceEnhance, SceneDetect, etc.).
Overwriting it would delete ~100 tests and break Phase 1 invariants, so this
file uses ``test_phase2_gemini_contracts.py`` instead. See
``.planning/phases/02-gemini-provider/02-04-SUMMARY.md`` Deviations section.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.schema_adapter import to_api_schema  # noqa: E402
from schemas.artifacts import load_schema, validate_artifact  # noqa: E402
from tools.base_tool import ToolStatus  # noqa: E402
from tools.analysis.gemini_video_analyzer import GeminiVideoAnalyzer  # noqa: E402
from tools.analysis.video_analyzer_selector import VideoAnalyzerSelector  # noqa: E402


SKILL_PATH = REPO_ROOT / ".agents" / "skills" / "gemini-video-analysis" / "SKILL.md"


# ---- Registration ---------------------------------------------------------


def test_selector_registered_with_video_analysis_capability():
    from tools.tool_registry import registry

    registry.ensure_discovered()
    tools = registry.get_by_capability("video_analysis")
    names = [t.name for t in tools]
    assert "video_analyzer_selector" in names
    assert "gemini_video_analyzer" in names


def test_selector_excludes_self_from_providers():
    sel = VideoAnalyzerSelector()
    providers = sel._providers()
    assert all(p.name != "video_analyzer_selector" for p in providers)


# ---- Selector preference order (ANLZ-01) ----------------------------------


def _make_fake_provider(name: str, provider_value: str, available: bool = True):
    p = MagicMock()
    p.name = name
    p.provider = provider_value
    p.get_status.return_value = (
        ToolStatus.AVAILABLE if available else ToolStatus.UNAVAILABLE
    )
    p.execute.return_value = MagicMock(success=True, data={"ok": True}, model=None)
    return p


def test_selector_preference_explicit_wins(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    sel = VideoAnalyzerSelector()
    gem = _make_fake_provider("gemini_video_analyzer", "gemini")
    orx = _make_fake_provider("openrouter_video_analyzer", "openrouter")
    chosen = sel._pick({"preferred_provider": "openrouter"}, [gem, orx])
    assert chosen is not None
    assert chosen.provider == "openrouter"


def test_selector_preference_env_beats_key_presence(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("VIDEO_ANALYZER_PROVIDER", "openrouter")
    sel = VideoAnalyzerSelector()
    gem = _make_fake_provider("gemini_video_analyzer", "gemini")
    orx = _make_fake_provider("openrouter_video_analyzer", "openrouter")
    chosen = sel._pick({}, [gem, orx])
    assert chosen is not None
    assert chosen.provider == "openrouter"


def test_selector_preference_gemini_key_beats_openrouter_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake2")
    monkeypatch.delenv("VIDEO_ANALYZER_PROVIDER", raising=False)
    sel = VideoAnalyzerSelector()
    gem = _make_fake_provider("gemini_video_analyzer", "gemini")
    orx = _make_fake_provider("openrouter_video_analyzer", "openrouter")
    chosen = sel._pick({}, [gem, orx])
    assert chosen is not None
    assert chosen.provider == "gemini"


def test_selector_falls_back_to_first_available(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("VIDEO_ANALYZER_PROVIDER", raising=False)
    sel = VideoAnalyzerSelector()
    gem = _make_fake_provider("gemini_video_analyzer", "gemini")
    chosen = sel._pick({}, [gem])
    assert chosen is not None
    assert chosen.name == "gemini_video_analyzer"


def test_selector_zero_providers_returns_clear_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        VideoAnalyzerSelector, "_providers", lambda self: []
    )
    sel = VideoAnalyzerSelector()
    result = sel.execute({"video_path": str(tmp_path / "x.mp4")})
    assert result.success is False
    assert "No video_analysis provider" in (result.error or "")


# ---- Gemini tool contract (GEM-01, GEM-05) --------------------------------


def test_gemini_tool_contract():
    t = GeminiVideoAnalyzer()
    info = t.get_info()
    assert info["name"] == "gemini_video_analyzer"
    assert info["capability"] == "video_analysis"
    assert info["provider"] == "gemini"
    assert info["tier"] == "analyze"
    assert info["stability"] == "beta"
    assert info["runtime"] == "api"
    assert info["agent_skills"] == ["gemini-video-analysis"]


# ---- Flattened-schema invariants (GEM-04) ---------------------------------


def test_flattened_schema_removes_unsupported_keys():
    flat = to_api_schema(load_schema("video_analysis"))
    s = json.dumps(flat)
    assert "$ref" not in s
    assert "uniqueItems" not in s
    compact = s.replace(" ", "")
    assert '"additionalProperties":false' not in compact


def test_flattened_schema_preserves_confidence_map():
    """Pitfall 4 guard — additionalProperties with enum schema must survive."""
    flat = to_api_schema(load_schema("video_analysis"))
    s = json.dumps(flat)
    assert '"low"' in s
    assert '"medium"' in s
    assert '"high"' in s


def test_schema_adapter_idempotent():
    canonical = load_schema("video_analysis")
    flat1 = to_api_schema(canonical)
    flat2 = to_api_schema(canonical)
    assert json.dumps(flat1, sort_keys=True) == json.dumps(flat2, sort_keys=True)


# ---- Canonical artifact gate (ANLZ-04) ------------------------------------


def test_minimal_artifact_still_validates():
    """Phase 1's minimal fixture must pass Phase 1's validator —
    Phase 2 unit tests (``valid_artifact`` fixture) depend on this invariant.
    """
    from tests.contracts.test_video_analysis_schema import minimal_video_analysis

    validate_artifact("video_analysis", minimal_video_analysis())


# ---- Layer 3 skill presence (SKILL-01, GEM-05) ----------------------------
#
# SKILL.md is shipped by plan 02-03 which runs concurrently. When this
# worktree is merged with 02-03 the skip condition lifts and these tests
# enforce the contract fully. Until then they skip so this worktree's CI
# stays green without duplicating 02-03's work.


@pytest.mark.skipif(
    not SKILL_PATH.is_file(),
    reason="SKILL.md is produced by plan 02-03 (concurrent worktree); "
    "will be enforced once merged.",
)
def test_gemini_skill_file_exists():
    assert SKILL_PATH.is_file(), f"Layer 3 skill missing at {SKILL_PATH}"


@pytest.mark.skipif(
    not SKILL_PATH.is_file(),
    reason="SKILL.md is produced by plan 02-03 (concurrent worktree).",
)
def test_gemini_skill_has_required_sections():
    content = SKILL_PATH.read_text(encoding="utf-8")
    assert content.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    assert "name: gemini-video-analysis" in content
    for dim in ("editing_pacing", "audio", "visual_style", "narrative"):
        assert dim in content, f"SKILL.md missing dimension {dim}"
    # Structured-output pattern
    assert 'response_mime_type="application/json"' in content
    assert "response_json_schema" in content
    assert "FinishReason.MAX_TOKENS" in content
    # Model table
    assert "gemini-3.1-pro-preview" in content
    assert "gemini-2.5-pro" in content
    # Auth
    assert "GEMINI_API_KEY" in content


def test_agent_skills_wiring_consistent():
    """Every tool's ``agent_skills`` list must reference a skill directory
    that either exists today or is slated for creation by a sibling plan
    (``gemini-video-analysis`` is produced by plan 02-03). The wiring is
    asserted unconditionally; the skill-file existence is asserted in the
    paired ``test_gemini_skill_file_exists`` above (skipped until merge).
    """
    for tool_cls in (GeminiVideoAnalyzer, VideoAnalyzerSelector):
        t = tool_cls()
        # Must point at gemini-video-analysis (the Phase 2 skill)
        assert "gemini-video-analysis" in t.agent_skills, (
            f"{tool_cls.__name__}.agent_skills must include "
            f"'gemini-video-analysis'; got {t.agent_skills}"
        )


# ---- Security: no real Google API keys embedded --------------------------


def test_no_google_api_keys_embedded():
    # Google API keys look like ``AIza`` followed by 35 url-safe chars.
    pattern = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
    candidate_paths = [
        REPO_ROOT / "tools" / "analysis" / "gemini_video_analyzer.py",
        REPO_ROOT / "tools" / "analysis" / "video_analyzer_selector.py",
        SKILL_PATH,
    ]
    for path in candidate_paths:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        hit = pattern.search(content)
        assert hit is None, (
            f"Real Google API key pattern found in {path}: {hit.group(0)[:8]}..."
        )
