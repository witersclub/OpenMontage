"""Regression: `_resolve_subtitle_style` must not crash when
`edit_decisions.subtitles.style` is a plain descriptive string.

The `edit_decisions` schema documents `subtitles.style` as a display-mode
string ("sentence", "word-by-word", "karaoke"), but `_resolve_subtitle_style`
used to call `.items()` on it unconditionally, assuming a font/color style
dict. Any schema-valid edit_decisions with subtitles.style set as a string
crashed the FFmpeg compose path with `AttributeError: 'str' object has no
attribute 'items'`.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.video.video_compose import VideoCompose  # noqa: E402


def test_string_style_does_not_crash_and_is_not_merged():
    edit_decisions = {"subtitles": {"style": "word-by-word"}}
    resolved = VideoCompose._resolve_subtitle_style(None, edit_decisions, None)
    # A plain descriptive string is not a font/color override — it must be
    # ignored, not partially merged character-by-character or raise.
    assert resolved["font"] == "Inter"
    assert resolved["font_size"] == 28


def test_dict_style_still_merges_as_before():
    edit_decisions = {"subtitles": {"style": {"font_size": 36, "font": "Courier"}}}
    resolved = VideoCompose._resolve_subtitle_style(None, edit_decisions, None)
    assert resolved["font_size"] == 36
    assert resolved["font"] == "Courier"


def test_missing_subtitles_key_falls_back_to_defaults():
    resolved = VideoCompose._resolve_subtitle_style(None, {}, None)
    assert resolved["font"] == "Inter"
