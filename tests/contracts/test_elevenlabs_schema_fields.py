"""Schema contract tests for the ElevenLabs integration's new fields.

script.schema.json gained a top-level `voice_id` (Brand Wallet voice
selection); asset_manifest.schema.json gained a per-asset `voice_id` and a
`captions` provenance block (source + path to a word-timestamps sidecar).
Both schemas keep `additionalProperties: false`, so these tests double as a
regression guard: a typo'd or removed field name would fail validation.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = REPO_ROOT / "schemas" / "artifacts"


def _load_schema(name: str) -> dict:
    with open(SCHEMAS_DIR / name, encoding="utf-8") as f:
        return json.load(f)


SCRIPT_SCHEMA = _load_schema("script.schema.json")
ASSET_MANIFEST_SCHEMA = _load_schema("asset_manifest.schema.json")


def _minimal_script(**overrides) -> dict:
    doc = {
        "version": "1.0",
        "title": "Demo",
        "total_duration_seconds": 30,
        "sections": [
            {
                "id": "s1",
                "text": "Hola mundo",
                "start_seconds": 0,
                "end_seconds": 30,
            }
        ],
    }
    doc.update(overrides)
    return doc


def _minimal_asset_manifest(asset_overrides: dict | None = None) -> dict:
    asset = {
        "id": "narration-s1",
        "type": "narration",
        "path": "assets/narration/s1.mp3",
        "source_tool": "tts_selector",
        "scene_id": "scene-1",
    }
    asset.update(asset_overrides or {})
    return {"version": "1.0", "assets": [asset]}


def test_script_schema_accepts_voice_id():
    doc = _minimal_script(voice_id="21m00Tcm4TlvDq8ikWAM")
    jsonschema.validate(instance=doc, schema=SCRIPT_SCHEMA)


def test_script_schema_still_valid_without_voice_id():
    jsonschema.validate(instance=_minimal_script(), schema=SCRIPT_SCHEMA)


def test_script_schema_rejects_non_string_voice_id():
    doc = _minimal_script(voice_id=12345)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=doc, schema=SCRIPT_SCHEMA)


def test_asset_manifest_accepts_voice_id_and_captions_block():
    doc = _minimal_asset_manifest(
        {
            "voice_id": "21m00Tcm4TlvDq8ikWAM",
            "captions": {
                "source": "elevenlabs_alignment",
                "path": "assets/narration/s1.words.json",
                "word_count": 24,
            },
        }
    )
    jsonschema.validate(instance=doc, schema=ASSET_MANIFEST_SCHEMA)


def test_asset_manifest_still_valid_without_new_fields():
    jsonschema.validate(instance=_minimal_asset_manifest(), schema=ASSET_MANIFEST_SCHEMA)


def test_asset_manifest_captions_requires_source_and_path():
    doc = _minimal_asset_manifest({"captions": {"word_count": 1}})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=doc, schema=ASSET_MANIFEST_SCHEMA)


def test_asset_manifest_captions_source_is_constrained_enum():
    doc = _minimal_asset_manifest(
        {"captions": {"source": "whisper_transcription", "path": "x.json"}}
    )
    jsonschema.validate(instance=doc, schema=ASSET_MANIFEST_SCHEMA)

    bad = _minimal_asset_manifest(
        {"captions": {"source": "made_up_source", "path": "x.json"}}
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=ASSET_MANIFEST_SCHEMA)


def test_asset_manifest_rejects_unknown_top_level_asset_field():
    # additionalProperties: false regression guard — a typo'd field name
    # (e.g. "voiceId" instead of "voice_id") must fail loudly, not silently
    # be dropped.
    doc = _minimal_asset_manifest({"voiceId": "should-not-be-accepted"})
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=doc, schema=ASSET_MANIFEST_SCHEMA)
