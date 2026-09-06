"""Tests for the pure ElevenLabs character->word alignment helpers.

No network, no filesystem — these exercise
tools/audio/elevenlabs_alignment.py against fixtures covering the cases the
integration proposal called out: plain spaces, punctuation, accents/ñ,
newlines, multiple words, monotonic timestamps, and the exact conversion
CaptionOverlay.tsx expects.
"""

from __future__ import annotations

import re

import pytest

from tools.audio.elevenlabs_alignment import (
    alignment_to_word_timestamps,
    characters_to_word_timestamps,
    word_timestamps_to_word_captions,
)

CHAR_SECONDS = 0.05


def _fixture(text: str, char_seconds: float = CHAR_SECONDS):
    """Build a synthetic ElevenLabs `alignment` fixture for `text`.

    Character i occupies [i*char_seconds, (i+1)*char_seconds) — a simple,
    strictly increasing clock so expected boundaries are easy to reason about.
    """
    characters = list(text)
    start_times = [round(i * char_seconds, 4) for i in range(len(characters))]
    end_times = [round((i + 1) * char_seconds, 4) for i in range(len(characters))]
    return characters, start_times, end_times


def _expected_words(text: str, char_seconds: float = CHAR_SECONDS):
    """Independent oracle: locate non-whitespace runs with a regex, rather
    than reusing the character-scanning loop under test."""
    expected = []
    for match in re.finditer(r"\S+", text):
        start_idx, end_idx_exclusive = match.start(), match.end()
        expected.append(
            {
                "word": match.group(),
                "start": round(start_idx * char_seconds, 4),
                "end": round(end_idx_exclusive * char_seconds, 4),
            }
        )
    return expected


@pytest.mark.parametrize(
    "text",
    [
        "Hola mundo",
        "¡Hola, señor! ¿Cómo estás?",
        "Línea uno\nLínea dos",
        "café  con  leche",
        "Múltiples   espacios\ny saltos\tde línea también",
        "Sin espacios",
        "Ñoño",
        "   espacios al inicio y al final   ",
    ],
)
def test_characters_to_word_timestamps_matches_independent_oracle(text: str) -> None:
    characters, start_times, end_times = _fixture(text)

    result = characters_to_word_timestamps(characters, start_times, end_times)

    assert result == _expected_words(text)


def test_words_include_attached_punctuation_and_accents() -> None:
    text = "¡Hola, señor! ¿Cómo estás?"
    characters, start_times, end_times = _fixture(text)

    result = characters_to_word_timestamps(characters, start_times, end_times)
    words = [w["word"] for w in result]

    assert words == ["¡Hola,", "señor!", "¿Cómo", "estás?"]


def test_newline_separates_words_like_a_space() -> None:
    text = "Línea uno\nLínea dos"
    characters, start_times, end_times = _fixture(text)

    result = characters_to_word_timestamps(characters, start_times, end_times)

    assert [w["word"] for w in result] == ["Línea", "uno", "Línea", "dos"]


def test_multiple_consecutive_spaces_do_not_create_empty_words() -> None:
    text = "café  con  leche"
    characters, start_times, end_times = _fixture(text)

    result = characters_to_word_timestamps(characters, start_times, end_times)

    assert [w["word"] for w in result] == ["café", "con", "leche"]


def test_timestamps_are_monotonic_non_decreasing() -> None:
    text = "¡Hola, señor! ¿Cómo estás, mi amigo?\nBienvenido a España."
    characters, start_times, end_times = _fixture(text)

    words = characters_to_word_timestamps(characters, start_times, end_times)

    assert len(words) > 1
    for word in words:
        assert word["start"] <= word["end"]
    for previous, current in zip(words, words[1:]):
        assert previous["end"] <= current["start"]


def test_empty_text_returns_no_words() -> None:
    assert characters_to_word_timestamps([], [], []) == []


def test_mismatched_lengths_raise_value_error() -> None:
    with pytest.raises(ValueError):
        characters_to_word_timestamps(["a", "b"], [0.0], [0.05, 0.1])


def test_alignment_to_word_timestamps_wraps_raw_response_dict() -> None:
    text = "Hola mundo"
    characters, start_times, end_times = _fixture(text)
    alignment = {
        "characters": characters,
        "character_start_times_seconds": start_times,
        "character_end_times_seconds": end_times,
    }

    result = alignment_to_word_timestamps(alignment)

    assert result == _expected_words(text)


def test_alignment_to_word_timestamps_handles_missing_keys() -> None:
    assert alignment_to_word_timestamps({}) == []


def test_word_timestamps_to_word_captions_matches_compose_director_example() -> None:
    # Same example already documented in
    # skills/pipelines/explainer/compose-director.md Step 5b, to prove the
    # ElevenLabs path produces byte-identical output to the existing
    # Whisper-based conversion for the same seconds input.
    word_timestamps = [
        {"word": "Root", "start": 0.12, "end": 0.34},
        {"word": "canals", "start": 0.34, "end": 0.68},
    ]

    captions = word_timestamps_to_word_captions(word_timestamps)

    assert captions == [
        {"word": "Root", "startMs": 120, "endMs": 340},
        {"word": "canals", "startMs": 340, "endMs": 680},
    ]


def test_word_timestamps_to_word_captions_shape_matches_caption_overlay() -> None:
    word_timestamps = [{"word": "Ñandú", "start": 1.0, "end": 1.5}]

    captions = word_timestamps_to_word_captions(word_timestamps)

    assert captions == [{"word": "Ñandú", "startMs": 1000, "endMs": 1500}]
    # CaptionOverlay.tsx's WordCaption interface is exactly these three keys.
    assert set(captions[0].keys()) == {"word", "startMs", "endMs"}


def test_full_pipeline_alignment_response_to_caption_overlay_format() -> None:
    """End-to-end pure conversion: raw ElevenLabs alignment -> WordCaption[]."""
    text = "Bienvenido a nuestro nuevo producto en español."
    characters, start_times, end_times = _fixture(text)
    alignment = {
        "characters": characters,
        "character_start_times_seconds": start_times,
        "character_end_times_seconds": end_times,
    }

    word_timestamps = alignment_to_word_timestamps(alignment)
    captions = word_timestamps_to_word_captions(word_timestamps)

    assert [c["word"] for c in captions] == [
        "Bienvenido",
        "a",
        "nuestro",
        "nuevo",
        "producto",
        "en",
        "español.",
    ]
    for cue in captions:
        assert isinstance(cue["startMs"], int)
        assert isinstance(cue["endMs"], int)
        assert cue["startMs"] <= cue["endMs"]
    for previous, current in zip(captions, captions[1:]):
        assert previous["endMs"] <= current["startMs"]
