"""Tests for the Witers preferred-voices registry.

Pure data/loader tests — no network, no ELEVENLABS_API_KEY. The voice_ids in
config/voices/witers_elevenlabs_voices.json were resolved once against the
real ElevenLabs account (see that file's `verification_notes`); these tests
just guard the registry's shape so a future edit can't silently drop a voice
or introduce a duplicate/malformed entry.
"""

from __future__ import annotations

from tools.audio.witers_voice_library import (
    find_witers_elevenlabs_voice,
    list_witers_elevenlabs_voices,
    load_witers_elevenlabs_voices,
)

EXPECTED_KEYS = {"david", "jc", "kate", "lujan"}


def test_registry_loads_and_has_expected_shape():
    doc = load_witers_elevenlabs_voices()
    assert doc["provider"] == "elevenlabs"
    assert doc["brand"] == "witers"
    assert isinstance(doc["voices"], list)


def test_all_four_preferred_voices_are_present():
    voices = list_witers_elevenlabs_voices()
    keys = {v["key"] for v in voices}
    assert keys == EXPECTED_KEYS
    for voice in voices:
        assert voice["voice_id"], f"{voice['key']} is missing a voice_id"
        # Real ElevenLabs voice_ids are ~20 alphanumeric characters.
        assert len(voice["voice_id"]) >= 15
        assert voice["gender"] in {"male", "female"}


def test_no_duplicate_voice_ids():
    ids = [v["voice_id"] for v in list_witers_elevenlabs_voices()]
    assert len(ids) == len(set(ids))


def test_preferred_model_is_eleven_v3_for_every_voice():
    for voice in list_witers_elevenlabs_voices():
        assert voice["preferred_model"] == "eleven_v3"


def test_find_by_key_is_case_insensitive():
    voice = find_witers_elevenlabs_voice("JC")
    assert voice is not None
    assert voice["voice_id"] == "7UB6WMKyZDj19XRGC8Sb"


def test_find_by_display_name():
    voice = find_witers_elevenlabs_voice("David - British Storyteller")
    assert voice is not None
    assert voice["key"] == "david"


def test_find_unknown_voice_returns_none():
    assert find_witers_elevenlabs_voice("not-a-real-voice") is None
