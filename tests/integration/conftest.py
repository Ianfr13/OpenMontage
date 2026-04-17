"""Shared fixtures for tests/integration/ — TEST-02.

Integration tests are DOUBLE-GATED:
  1. RUN_INTEGRATION_TESTS=1 must be set (opt-in; default CI runs skip).
  2. The specific fixture video file must exist on disk (README.md explains
     how to provision them; they are gitignored because 10-100MB clips).

Both gates use pytest.skip() with readable reason strings. A missing gate
yields a SKIP, never a FAIL — this is the contract that keeps the default
`pytest` run green without fixtures and without API keys.

Unlike tests/unit/conftest.py (which autouse-scrubs provider env vars so
mocks reign), this conftest does NOT scrub env. Real keys are required for
the provider under test; absence is detected by the per-test
skip-if-no-key decorator.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure repo root on sys.path (same pattern as tests/unit/conftest.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# --- Fixture-video paths --------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: 3 tiers required by TEST-02 (short / medium / long-chunked).
FIXTURE_VIDEOS: dict[str, Path] = {
    "short": FIXTURES_DIR / "short.mp4",   # < 2 min — single-call path
    "medium": FIXTURES_DIR / "medium.mp4", # 3-5 min — still single-call
    "long": FIXTURES_DIR / "long.mp4",     # > 5 min — triggers chunking
}


# --- Gate helpers ---------------------------------------------------------

def _integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION_TESTS") == "1"


def require_integration_enabled() -> None:
    """Call from a test body or fixture to skip when the env gate is off."""
    if not _integration_enabled():
        pytest.skip(
            "RUN_INTEGRATION_TESTS!=1 (set to '1' to enable integration tests)"
        )


def require_fixture(tier: str) -> Path:
    """Resolve a fixture video path; skip if missing.

    Args:
        tier: 'short', 'medium', or 'long'.

    Returns:
        Path to the fixture video (exists on disk).
    """
    if tier not in FIXTURE_VIDEOS:
        raise ValueError(f"Unknown fixture tier: {tier!r}")
    path = FIXTURE_VIDEOS[tier]
    if not path.is_file():
        pytest.skip(
            f"Fixture video missing: {path} "
            f"(see tests/integration/README.md to provision)"
        )
    return path


# --- Per-provider key gates -----------------------------------------------

def require_gemini_key() -> None:
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        pytest.skip("GEMINI_API_KEY (or GOOGLE_API_KEY) not set")


def require_openrouter_key() -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")


# --- pytest fixtures ------------------------------------------------------

@pytest.fixture
def fixture_video(request) -> Path:
    """Parametrizable fixture: indirect-param the tier.

    Usage:
        @pytest.mark.parametrize("fixture_video", ["short", "medium", "long"], indirect=True)
        def test_foo(fixture_video):
            # fixture_video is a Path to the existing file
            ...

    Double-gate order:
      1. RUN_INTEGRATION_TESTS=1 (cheap env check) — skip first if off.
      2. Fixture file existence — skip if missing.

    Per-provider API-key gates live in the test bodies (require_gemini_key /
    require_openrouter_key) since the same fixture is shared across providers.
    """
    require_integration_enabled()
    return require_fixture(request.param)
