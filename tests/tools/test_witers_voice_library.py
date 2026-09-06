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
    find_witers_elevenlabs_voice_by_id,
    list_witers_elevenlabs_voices,
    load_witers_elevenlabs_voices,
    resolve_witers_voice_id,
    resolve_witers_voice_model,
)

EXPECTED_KEYS = {"david", "jc", "kate", "lujan"}
DAVID_VOICE_ID = find_witers_elevenlabs_voice("david")["voice_id"]
JC_VOICE_ID = find_witers_elevenlabs_voice("jc")["voice_id"]


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


def test_find_by_id_resolves_registered_voice():
    voice = find_witers_elevenlabs_voice_by_id(JC_VOICE_ID)
    assert voice is not None
    assert voice["key"] == "jc"


def test_find_by_id_returns_none_for_unknown_id():
    assert find_witers_elevenlabs_voice_by_id("not-a-real-voice-id") is None


def test_resolve_falls_back_to_david_when_brand_wallet_has_no_voice():
    assert resolve_witers_voice_id(None) == DAVID_VOICE_ID
    assert resolve_witers_voice_id("") == DAVID_VOICE_ID


def test_resolve_never_overrides_a_brand_wallet_voice_id():
    brand_wallet_voice = "SomeBrandWalletVoiceId123"
    assert resolve_witers_voice_id(brand_wallet_voice) == brand_wallet_voice

    # Even when the Brand Wallet voice happens to be one of Witers' own
    # preferred voices, it passes through unchanged rather than being
    # "re-resolved" to itself through some other path.
    assert resolve_witers_voice_id(JC_VOICE_ID) == JC_VOICE_ID


def test_resolve_model_returns_preferred_model_for_witers_voices():
    assert resolve_witers_voice_model(DAVID_VOICE_ID) == "eleven_v3"
    assert resolve_witers_voice_model(JC_VOICE_ID) == "eleven_v3"


def test_resolve_model_returns_none_for_unrelated_voice():
    assert resolve_witers_voice_model("SomeBrandWalletVoiceId123") is None
