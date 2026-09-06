"""Witers' preferred ElevenLabs voices for narration.

These are curated, pre-approved voices from Witers' own ElevenLabs account
(`config/voices/witers_elevenlabs_voices.json`), resolved once against
GET /v1/voices rather than left for every pipeline run to search or guess
again. Once a Brand Wallet supplies its own `voice_id` (via `script.voice_id`
/ `asset_manifest.assets[].voice_id`), that value always wins — this registry
only exists so OpenMontage has a sensible, Witers-approved starting point
instead of ElevenLabs' generic default voice when no brand voice is set yet.

This module only reads the local JSON registry. It never calls the
ElevenLabs API and never touches ELEVENLABS_API_KEY.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "voices" / "witers_elevenlabs_voices.json"
)


def load_witers_elevenlabs_voices(registry_path: Path | None = None) -> dict[str, Any]:
    """Load the full registry document (version, provider, brand, voices[])."""
    path = registry_path or _REGISTRY_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_witers_elevenlabs_voices(registry_path: Path | None = None) -> list[dict[str, Any]]:
    """Return the flat list of preferred voice entries."""
    return load_witers_elevenlabs_voices(registry_path).get("voices", [])


def find_witers_elevenlabs_voice(
    name: str, registry_path: Path | None = None
) -> dict[str, Any] | None:
    """Look up a preferred voice by its short `key` (e.g. "jc") or `display_name`.

    Matching is case-insensitive so a Brand Wallet value like
    "JC - Deep & Touching" resolves without needing the short key too.
    Returns None if nothing matches.
    """
    needle = name.strip().lower()
    for voice in list_witers_elevenlabs_voices(registry_path):
        if voice.get("key", "").lower() == needle:
            return voice
        if voice.get("display_name", "").strip().lower() == needle:
            return voice
    return None
