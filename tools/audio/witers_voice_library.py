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

# Fallback used only when Brand Wallet has not configured a voice yet.
# JC, Kate and Luján stay registered as preferred voices for future
# selection — they are never picked automatically over an unset Brand
# Wallet voice, only "david" is.
DEFAULT_FALLBACK_KEY = "david"


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


def find_witers_elevenlabs_voice_by_id(
    voice_id: str, registry_path: Path | None = None
) -> dict[str, Any] | None:
    """Look up a preferred voice by its resolved ElevenLabs `voice_id`.

    Used to recover a voice's `preferred_model` once only the `voice_id` is
    in hand (e.g. after Brand Wallet already supplied one that happens to
    match a Witers preferred voice).
    """
    for voice in list_witers_elevenlabs_voices(registry_path):
        if voice.get("voice_id") == voice_id:
            return voice
    return None


def resolve_witers_voice_id(
    brand_wallet_voice_id: str | None, registry_path: Path | None = None
) -> str:
    """Resolve the ElevenLabs voice_id to narrate with.

    Brand Wallet's voice_id always wins when it is set — this function
    never overrides a value the caller already has. Only when
    `brand_wallet_voice_id` is falsy (None or empty) does it fall back to
    Witers' pre-approved default voice (David - British Storyteller).
    """
    if brand_wallet_voice_id:
        return brand_wallet_voice_id

    fallback = find_witers_elevenlabs_voice(DEFAULT_FALLBACK_KEY, registry_path)
    if fallback is None:
        raise LookupError(
            f"Witers fallback voice {DEFAULT_FALLBACK_KEY!r} is missing from "
            f"{registry_path or _REGISTRY_PATH}"
        )
    return fallback["voice_id"]


def resolve_witers_voice_model(
    voice_id: str, registry_path: Path | None = None
) -> str | None:
    """Return the preferred model for `voice_id` if it is a Witers preferred
    voice, or None if it isn't (an unrelated/Brand-Wallet-supplied voice_id
    OpenMontage has no opinion about)."""
    voice = find_witers_elevenlabs_voice_by_id(voice_id, registry_path)
    return voice.get("preferred_model") if voice else None
