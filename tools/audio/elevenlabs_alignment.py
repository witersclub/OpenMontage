"""Pure helpers for turning ElevenLabs' character-level speech alignment into
word-level timing, and for converting that timing into the shape
CaptionOverlay.tsx (remotion-composer/src/components/CaptionOverlay.tsx) expects.

ElevenLabs' `/v1/text-to-speech/{voice_id}/with-timestamps` endpoint (and its
streaming sibling) return only per-character alignment:

    {
      "audio_base64": "...",
      "alignment": {
        "characters": ["H", "o", "l", "a", " ", ...],
        "character_start_times_seconds": [0.0, 0.05, ...],
        "character_end_times_seconds": [0.05, 0.09, ...]
      }
    }

Nothing downstream in OpenMontage (subtitle_gen, remotion_caption_burn,
CaptionOverlay) understands character-level timing — everything works in
word-level `{word, start, end}` seconds (the same shape `Transcriber` already
produces) or `{word, startMs, endMs}` (Remotion's `WordCaption`). These
helpers bridge that gap with no network or file I/O, so they are trivial to
test against fixtures.
"""

from __future__ import annotations

from typing import Any


def characters_to_word_timestamps(
    characters: list[str],
    start_times: list[float],
    end_times: list[float],
) -> list[dict[str, Any]]:
    """Group character-level alignment into word-level {word, start, end} timing.

    A run of whitespace (spaces, newlines, tabs) ends the current word. A
    punctuation mark with no surrounding whitespace (accents, ñ, ¿, ¡, a
    trailing comma or period, ...) has nothing to separate it from its word,
    so it stays attached — matching how the existing Whisper-based caption
    pipeline already treats punctuation.

    Raises ValueError if the three arrays are not the same length: that
    means the response is malformed, and silently zipping mismatched arrays
    would misalign every timestamp after the first gap.
    """
    if not (len(characters) == len(start_times) == len(end_times)):
        raise ValueError(
            "characters, start_times and end_times must be the same length "
            f"(got {len(characters)}, {len(start_times)}, {len(end_times)})"
        )

    words: list[dict[str, Any]] = []
    buffer: list[str] = []
    word_start: float | None = None
    word_end: float | None = None

    for char, start, end in zip(characters, start_times, end_times):
        if char.isspace():
            if buffer:
                words.append({"word": "".join(buffer), "start": word_start, "end": word_end})
                buffer = []
            continue
        if not buffer:
            word_start = start
        buffer.append(char)
        word_end = end

    if buffer:
        words.append({"word": "".join(buffer), "start": word_start, "end": word_end})

    return words


def alignment_to_word_timestamps(alignment: dict[str, Any]) -> list[dict[str, Any]]:
    """Convenience wrapper accepting ElevenLabs' raw `alignment` response object."""
    return characters_to_word_timestamps(
        alignment.get("characters", []),
        alignment.get("character_start_times_seconds", []),
        alignment.get("character_end_times_seconds", []),
    )


def word_timestamps_to_word_captions(word_timestamps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert {word, start, end} seconds timing into Remotion's WordCaption shape.

    Matches the {word, startMs, endMs} millisecond shape that
    CaptionOverlay.tsx / Explainer.tsx's `captions` prop already expect, and
    that the existing Whisper-based path already produces via
    remotion_caption_burn.py::_segments_to_word_captions.
    """
    return [
        {
            "word": w["word"],
            "startMs": int(round(w["start"] * 1000)),
            "endMs": int(round(w["end"] * 1000)),
        }
        for w in word_timestamps
    ]
