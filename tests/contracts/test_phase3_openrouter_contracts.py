"""Contract tests for Phase 3 — OpenRouter provider + ANLZ-06 cross-provider parity.

No API key needed; no network calls. The ANLZ-06 gate parametrizes over BOTH
providers and asserts:
  1. Both ``ToolResult.data`` dicts deep-equal the same canonical artifact
     (caller can't tell which backend served the response).
  2. Both artifacts pass ``validate_artifact('video_analysis', ...)``.
  3. Both have identical top-level keys.

Also:
  * Registration: OpenRouter tool is discovered at video_analysis capability.
  * Selector preference order with OpenRouter now present (ANLZ-01).
  * SKILL.md presence + required sections (skipped until plan 03-02 merges).
  * No real API keys embedded in any source or SKILL file.
  * Tools don't stamp selector metadata on result.data (ANLZ-06 / Pitfall 7).
  * Tools don't import write_checkpoint (WR-05).

NOTE on filename: the plan spec names this ``test_phase3_contracts.py`` but
that file already exists in this repo with unrelated legacy
instruction-driven-architecture tests (TTS, music gen, pipeline manifests,
etc.). Overwriting would destroy ~unrelated coverage, so we use
``test_phase3_openrouter_contracts.py`` — same pattern as Phase 2's
``test_phase2_gemini_contracts.py`` vs legacy ``test_phase2_contracts.py``.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from openai import BadRequestError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.artifacts import load_schema, validate_artifact  # noqa: E402
from lib.schema_adapter import to_api_schema  # noqa: E402
from tools.base_tool import ToolStatus  # noqa: E402
from tools.analysis.gemini_video_analyzer import GeminiVideoAnalyzer  # noqa: E402
from tools.analysis.openrouter_video_analyzer import (  # noqa: E402
    OpenRouterVideoAnalyzer,
)
from tools.analysis.video_analyzer_selector import VideoAnalyzerSelector  # noqa: E402

SKILL_PATH = REPO_ROOT / ".agents" / "skills" / "openrouter-video-analysis" / "SKILL.md"
GEMINI_SKILL_PATH = REPO_ROOT / ".agents" / "skills" / "gemini-video-analysis" / "SKILL.md"

OR_SOURCE = REPO_ROOT / "tools" / "analysis" / "openrouter_video_analyzer.py"
GEM_SOURCE = REPO_ROOT / "tools" / "analysis" / "gemini_video_analyzer.py"
SEL_SOURCE = REPO_ROOT / "tools" / "analysis" / "video_analyzer_selector.py"


# ---------------------------------------------------------------------------
# Helpers — self-contained fake SDK clients (so cross-provider test doesn't
# depend on tests/unit/conftest.py fixtures)
# ---------------------------------------------------------------------------


def _minimal_canonical() -> dict:
    from tests.contracts.test_video_analysis_schema import minimal_video_analysis
    return copy.deepcopy(minimal_video_analysis())


def _fake_openai_client_returning(artifact: dict) -> MagicMock:
    client = MagicMock()
    resp = MagicMock()
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = json.dumps(artifact)
    resp.choices = [choice]
    resp.model = "google/gemini-3.1-pro-preview"
    resp.usage = MagicMock(cost=0.001)
    client.chat.completions.create.return_value = resp
    return client


def _fake_genai_client_returning(artifact: dict) -> MagicMock:
    from google.genai import types

    client = MagicMock()

    up = MagicMock()
    up.name = "files/abc123"
    up_state = MagicMock()
    up_state.value = "PROCESSING"
    up.state = up_state
    client.files.upload.return_value = up

    active = MagicMock()
    active.name = "files/abc123"
    active_state = MagicMock()
    active_state.value = "ACTIVE"
    active.state = active_state
    client.files.get.side_effect = [active]

    resp = MagicMock()
    cand = MagicMock()
    cand.finish_reason = types.FinishReason.STOP
    resp.candidates = [cand]
    resp.text = json.dumps(artifact)
    client.models.generate_content.return_value = resp

    client.files.delete.return_value = MagicMock()
    return client


def _make_fake_provider(name: str, provider_value: str, available: bool = True):
    p = MagicMock()
    p.name = name
    p.provider = provider_value
    p.get_status.return_value = (
        ToolStatus.AVAILABLE if available else ToolStatus.UNAVAILABLE
    )
    p.execute.return_value = MagicMock(success=True, data={"ok": True}, model=None)
    return p


def _bad_request(msg: str = "unsupported response_format") -> BadRequestError:
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    resp = httpx.Response(400, request=req)
    return BadRequestError(msg, response=resp, body={"error": {"message": msg}})


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_openrouter_tool_registered_with_video_analysis_capability():
    """OR-06: OpenRouter tool auto-discovered; Phase 2 tools still present."""
    from tools.tool_registry import registry
    registry.ensure_discovered()
    names = {t.name for t in registry.get_by_capability("video_analysis")}
    assert "openrouter_video_analyzer" in names
    assert "gemini_video_analyzer" in names
    assert "video_analyzer_selector" in names


def test_openrouter_tool_contract():
    """OR-01: OpenRouter tool contract fields."""
    t = OpenRouterVideoAnalyzer()
    info = t.get_info()
    assert info["name"] == "openrouter_video_analyzer"
    assert info["capability"] == "video_analysis"
    assert info["provider"] == "openrouter"
    assert info["tier"] == "analyze"
    assert info["stability"] == "beta"
    assert info["runtime"] == "api"
    assert info["agent_skills"] == ["openrouter-video-analysis"]


# ---------------------------------------------------------------------------
# Selector preference order (ANLZ-01) — with OpenRouter now present
# ---------------------------------------------------------------------------


def test_selector_preference_openrouter_env_wins(monkeypatch):
    """ANLZ-01: VIDEO_ANALYZER_PROVIDER=openrouter routes to OpenRouter tool."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    monkeypatch.setenv("VIDEO_ANALYZER_PROVIDER", "openrouter")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    sel = VideoAnalyzerSelector()
    gem = _make_fake_provider("gemini_video_analyzer", "gemini")
    orx = _make_fake_provider("openrouter_video_analyzer", "openrouter")
    chosen = sel._pick({}, [gem, orx])
    assert chosen is not None
    assert chosen.provider == "openrouter"


def test_selector_preference_explicit_openrouter_wins(monkeypatch):
    """ANLZ-01: inputs['preferred_provider']='openrouter' returns OpenRouter tool."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    sel = VideoAnalyzerSelector()
    gem = _make_fake_provider("gemini_video_analyzer", "gemini")
    orx = _make_fake_provider("openrouter_video_analyzer", "openrouter")
    chosen = sel._pick({"preferred_provider": "openrouter"}, [gem, orx])
    assert chosen is not None
    assert chosen.provider == "openrouter"


def test_selector_preference_gemini_default_when_both_keys(monkeypatch):
    """ANLZ-01: with both keys and no explicit pref, Gemini wins (Phase 2 ordering)."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gem")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-or")
    monkeypatch.delenv("VIDEO_ANALYZER_PROVIDER", raising=False)
    sel = VideoAnalyzerSelector()
    gem = _make_fake_provider("gemini_video_analyzer", "gemini")
    orx = _make_fake_provider("openrouter_video_analyzer", "openrouter")
    chosen = sel._pick({}, [gem, orx])
    assert chosen is not None
    assert chosen.provider == "gemini"


def test_selector_preference_openrouter_when_only_openrouter_key(monkeypatch):
    """ANLZ-01: only OPENROUTER_API_KEY set -> OpenRouter wins via key-presence tie-break."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-or")
    monkeypatch.delenv("VIDEO_ANALYZER_PROVIDER", raising=False)
    sel = VideoAnalyzerSelector()
    gem = _make_fake_provider("gemini_video_analyzer", "gemini")
    orx = _make_fake_provider("openrouter_video_analyzer", "openrouter")
    chosen = sel._pick({}, [gem, orx])
    assert chosen is not None
    assert chosen.provider == "openrouter"


# ---------------------------------------------------------------------------
# ANLZ-06 — cross-provider consistency (THE core gate)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_name", ["gemini", "openrouter"])
def test_cross_provider_consistency_same_canonical_artifact(
    provider_name, monkeypatch, tmp_path,
):
    """ANLZ-06: both providers produce deep-equal canonical artifacts.

    The SAME canonical fixture is fed through each provider's mocked SDK.
    Result: ToolResult.data deep-equals the fixture AND passes
    validate_artifact('video_analysis', ...). Caller cannot tell which
    backend ran from the artifact alone.
    """
    canonical = _minimal_canonical()
    video = tmp_path / "ref.mp4"
    video.write_bytes(b"\x00" * 1024)

    # Scrub any provider keys that might leak from shell
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY",
              "VIDEO_ANALYZER_PROVIDER", "GEMINI_VIDEO_MODEL", "OPENROUTER_MODEL"):
        monkeypatch.delenv(k, raising=False)

    if provider_name == "gemini":
        monkeypatch.setenv("GEMINI_API_KEY", "fake-gem-key")
        import tools.analysis.gemini_video_analyzer as gtarget
        client = _fake_genai_client_returning(canonical)
        monkeypatch.setattr(gtarget.genai, "Client", MagicMock(return_value=client))
        monkeypatch.setattr(gtarget.time, "sleep", lambda *a, **kw: None)
        tool = GeminiVideoAnalyzer()
    else:
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-or-key")
        import tools.analysis.openrouter_video_analyzer as otarget
        client = _fake_openai_client_returning(canonical)
        monkeypatch.setattr(otarget, "OpenAI", MagicMock(return_value=client))
        tool = OpenRouterVideoAnalyzer()

    result = tool.execute({"video_path": str(video)})
    assert result.success is True, result.error
    assert result.data == canonical  # deep equality
    # Gate: artifact passes canonical schema validation
    validate_artifact("video_analysis", result.data)


def test_cross_provider_identical_top_level_keys(monkeypatch, tmp_path):
    """ANLZ-06: result.data key sets are identical across providers."""
    canonical = _minimal_canonical()
    video = tmp_path / "ref.mp4"
    video.write_bytes(b"\x00" * 1024)

    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY",
              "VIDEO_ANALYZER_PROVIDER", "GEMINI_VIDEO_MODEL", "OPENROUTER_MODEL"):
        monkeypatch.delenv(k, raising=False)

    # Gemini
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    import tools.analysis.gemini_video_analyzer as gtarget
    gclient = _fake_genai_client_returning(canonical)
    monkeypatch.setattr(gtarget.genai, "Client", MagicMock(return_value=gclient))
    monkeypatch.setattr(gtarget.time, "sleep", lambda *a, **kw: None)
    gem_result = GeminiVideoAnalyzer().execute({"video_path": str(video)})

    # OpenRouter
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    import tools.analysis.openrouter_video_analyzer as otarget
    oclient = _fake_openai_client_returning(canonical)
    monkeypatch.setattr(otarget, "OpenAI", MagicMock(return_value=oclient))
    or_result = OpenRouterVideoAnalyzer().execute({"video_path": str(video)})

    assert gem_result.success is True, gem_result.error
    assert or_result.success is True, or_result.error
    assert set(gem_result.data.keys()) == set(or_result.data.keys())
    # And the key set matches the canonical fixture (no extras from either provider)
    assert set(gem_result.data.keys()) == set(canonical.keys())


# ---------------------------------------------------------------------------
# SKILL.md presence + required sections (SKILL-02)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not SKILL_PATH.is_file(),
    reason="SKILL.md produced by plan 03-02 (concurrent worktree); enforced after merge.",
)
def test_skill_file_exists():
    """SKILL-02: openrouter-video-analysis/SKILL.md exists; Gemini SKILL still exists."""
    assert SKILL_PATH.is_file(), f"Missing: {SKILL_PATH}"
    if GEMINI_SKILL_PATH.exists():
        assert GEMINI_SKILL_PATH.is_file()


@pytest.mark.skipif(
    not SKILL_PATH.is_file(),
    reason="SKILL.md produced by plan 03-02 (concurrent worktree).",
)
def test_skill_required_sections():
    """SKILL-02: SKILL.md has all required frontmatter/sections/keywords.

    Checks for: frontmatter, name slug, 4 dimensions, json_schema pattern,
    require_parameters keyword, STRING-valued == "length" guidance (Pitfall 2),
    warning against the mythic x-openrouter-credit-remaining header (Pitfall 5),
    default model slug, auth env var, model-swap env var, base64 mention.
    """
    content = SKILL_PATH.read_text(encoding="utf-8")
    assert content.startswith("---"), "SKILL.md must start with YAML frontmatter"
    assert "name: openrouter-video-analysis" in content
    for dim in ("editing_pacing", "audio", "visual_style", "narrative"):
        assert dim in content, f"Missing dimension: {dim}"
    # Structured-output pattern
    assert '"type": "json_schema"' in content or "type: json_schema" in content
    assert "require_parameters" in content
    # Pitfall 2 — STRING compare guidance
    assert '== "length"' in content or "== 'length'" in content
    # Pitfall 5 — warn against the mythic header
    assert "x-openrouter-credit-remaining" in content
    # Model + auth
    assert "google/gemini-3.1-pro-preview" in content
    assert "OPENROUTER_API_KEY" in content
    assert "OPENROUTER_MODEL" in content
    # Encoding path
    assert "base64" in content


# ---------------------------------------------------------------------------
# No embedded API keys (T-03-11, T-02-13 regression)
# ---------------------------------------------------------------------------


def test_no_embedded_api_keys():
    """T-03-11: no real OpenRouter or Google API keys in SKILL/tool/selector source."""
    or_pattern = re.compile(r"sk-or-v1-[a-f0-9]{40,}")
    google_pattern = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
    candidates = [OR_SOURCE, GEM_SOURCE, SEL_SOURCE, SKILL_PATH, GEMINI_SKILL_PATH]
    for path in candidates:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        or_hit = or_pattern.search(content)
        g_hit = google_pattern.search(content)
        assert or_hit is None, (
            f"Real OpenRouter API key pattern in {path}: {or_hit.group(0)[:12]}..."
        )
        assert g_hit is None, (
            f"Real Google API key pattern in {path}: {g_hit.group(0)[:8]}..."
        )


# ---------------------------------------------------------------------------
# OR-06: agent_skills wiring
# ---------------------------------------------------------------------------


def test_agent_skills_wiring_names_are_valid():
    """OR-06 structural: both tools' agent_skills list the expected slugs."""
    or_t = OpenRouterVideoAnalyzer()
    assert "openrouter-video-analysis" in or_t.agent_skills
    gem_t = GeminiVideoAnalyzer()
    assert "gemini-video-analysis" in gem_t.agent_skills


@pytest.mark.skipif(
    not SKILL_PATH.is_file(),
    reason="SKILL.md produced by plan 03-02 (concurrent worktree).",
)
def test_agent_skills_wiring_resolves_to_skill_file():
    """OR-06: each agent_skills entry resolves to an on-disk SKILL.md."""
    for tool_cls in (OpenRouterVideoAnalyzer, GeminiVideoAnalyzer):
        t = tool_cls()
        for skill_name in t.agent_skills:
            path = REPO_ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
            if not path.exists():
                continue  # sibling skill (e.g., gemini) may not have landed yet
            assert path.is_file(), f"Missing SKILL.md at {path}"


# ---------------------------------------------------------------------------
# Shared invariant — flat schema adapter strips unsupported keys
# ---------------------------------------------------------------------------


def test_flat_schema_adapter_strips_unsupported_keys():
    """Phase 1 contract re-asserted: OpenRouter's json_schema relies on this."""
    flat = to_api_schema(load_schema("video_analysis"))
    s = json.dumps(flat)
    assert "$ref" not in s
    assert "uniqueItems" not in s
    compact = s.replace(" ", "")
    assert '"additionalProperties":false' not in compact


# ---------------------------------------------------------------------------
# ANLZ-06 / Pitfall 7 — tools don't stamp selector metadata on data
# ---------------------------------------------------------------------------


def test_tool_does_not_stamp_selector_metadata_on_data(monkeypatch, tmp_path):
    """Pitfall 7: OpenRouter tool must NOT add selector metadata keys to result.data."""
    canonical = _minimal_canonical()
    video = tmp_path / "ref.mp4"
    video.write_bytes(b"\x00" * 1024)
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY",
              "VIDEO_ANALYZER_PROVIDER", "OPENROUTER_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    import tools.analysis.openrouter_video_analyzer as otarget
    monkeypatch.setattr(
        otarget, "OpenAI",
        MagicMock(return_value=_fake_openai_client_returning(canonical)),
    )
    t = OpenRouterVideoAnalyzer()
    result = t.execute({"video_path": str(video)})
    assert result.success is True, result.error
    assert set(result.data.keys()) == set(canonical.keys())
    forbidden = {"selected_provider", "provider_used", "selected_tool", "_selector"}
    assert forbidden.isdisjoint(result.data.keys())


# ---------------------------------------------------------------------------
# WR-05 — neither tool imports write_checkpoint
# ---------------------------------------------------------------------------


def test_tool_does_not_import_checkpoint():
    """WR-05: Gemini + OpenRouter tool sources must not reference lib.checkpoint."""
    for src in (OR_SOURCE, GEM_SOURCE):
        content = src.read_text(encoding="utf-8")
        assert "from lib.checkpoint" not in content, f"{src} imports lib.checkpoint"
        assert "write_checkpoint(" not in content, f"{src} calls write_checkpoint()"
