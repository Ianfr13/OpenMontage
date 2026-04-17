"""Phase 1 contract tests — pipeline_synthesis run-record schema.

Verifies schemas/artifacts/pipeline_synthesis.schema.json enforces the SYNTH-09
field set with correct enums and numeric bounds. Runs without any API key.
"""
import json
import sys
from pathlib import Path

import jsonschema
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from schemas.artifacts import load_schema  # noqa: E402

SCHEMA_PATH = PROJECT_ROOT / "schemas" / "artifacts" / "pipeline_synthesis.schema.json"

SYNTH_09_REQUIRED = {
    "base_pipeline", "match_score", "mode", "staging_path",
    "diff_against_base", "validation_status",
    "source_analysis_checksum", "provider_used",
}


def minimal_synthesis() -> dict:
    return {
        "version": "1.0",
        "base_pipeline": "animated-explainer",
        "match_score": 0.82,
        "mode": "template",
        "staging_path": "pipeline_defs/_staging/ref-abc123.yaml",
        "diff_against_base": "--- a/base\n+++ b/synth\n@@ adjusted target_platform",
        "validation_status": "pending",
        "source_analysis_checksum": "sha256:0123abcd",
        "provider_used": "gemini",
    }


class TestPipelineSynthesisSchema:
    def test_schema_loads(self):
        assert SCHEMA_PATH.exists()
        schema = json.load(open(SCHEMA_PATH))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["title"] == "pipeline_synthesis"
        required = set(schema["required"])
        assert SYNTH_09_REQUIRED <= required
        assert "version" in required

    def test_load_schema_helper_works(self):
        schema = load_schema("pipeline_synthesis")
        assert schema["title"] == "pipeline_synthesis"

    def test_fixture_validates(self):
        schema = load_schema("pipeline_synthesis")
        jsonschema.validate(instance=minimal_synthesis(), schema=schema)  # no raise

    @pytest.mark.parametrize("field", sorted(SYNTH_09_REQUIRED))
    def test_rejects_missing_required(self, field):
        schema = load_schema("pipeline_synthesis")
        fixture = minimal_synthesis()
        del fixture[field]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=fixture, schema=schema)

    def test_rejects_match_score_above_one(self):
        schema = load_schema("pipeline_synthesis")
        fixture = minimal_synthesis()
        fixture["match_score"] = 1.5
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=fixture, schema=schema)

    def test_rejects_match_score_below_zero(self):
        schema = load_schema("pipeline_synthesis")
        fixture = minimal_synthesis()
        fixture["match_score"] = -0.1
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=fixture, schema=schema)

    def test_rejects_invalid_mode(self):
        schema = load_schema("pipeline_synthesis")
        fixture = minimal_synthesis()
        fixture["mode"] = "freeform"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=fixture, schema=schema)

    def test_rejects_invalid_provider(self):
        schema = load_schema("pipeline_synthesis")
        fixture = minimal_synthesis()
        fixture["provider_used"] = "claude"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=fixture, schema=schema)

    def test_rejects_invalid_validation_status(self):
        schema = load_schema("pipeline_synthesis")
        fixture = minimal_synthesis()
        fixture["validation_status"] = "unknown"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=fixture, schema=schema)

    def test_rejects_invalid_version_const(self):
        schema = load_schema("pipeline_synthesis")
        fixture = minimal_synthesis()
        fixture["version"] = "2.0"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=fixture, schema=schema)
