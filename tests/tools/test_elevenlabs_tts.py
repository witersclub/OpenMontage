from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

from tools.audio.elevenlabs_tts import ElevenLabsTTS
from tools.audio.witers_voice_library import find_witers_elevenlabs_voice
from tools.base_tool import ToolStatus
from tools.tool_registry import ToolRegistry

DAVID_VOICE_ID = find_witers_elevenlabs_voice("david")["voice_id"]
JC_VOICE_ID = find_witers_elevenlabs_voice("jc")["voice_id"]


def _response(*, json_data=None, content=b""):
    response = MagicMock()
    response.json.return_value = json_data
    response.content = content
    response.raise_for_status.return_value = None
    return response


def _clear_auth_env(monkeypatch) -> None:
    """Remove every signal both auth paths key off, including the proxy
    markers this very test/sandbox process is genuinely running under —
    without this, "no credential" tests would spuriously see proxy_managed."""
    for var in ("ELEVENLABS_API_KEY", "CCR_AGENT_PROXY_ENABLED", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(var, raising=False)


def test_contract_capability_and_agent_skills(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    tool = ElevenLabsTTS()
    info = tool.get_info()

    assert tool.get_status() == ToolStatus.AVAILABLE
    assert info["capability"] == "tts"
    assert info["provider"] == "elevenlabs"
    # Regression: agent_skills used to include "text-to-speech", which
    # documents HeyGen's Starfish TTS, not ElevenLabs.
    assert info["agent_skills"] == ["elevenlabs"]
    assert "word_timestamps" in info["capabilities"]


def test_get_status_unavailable_with_no_credential_at_all(monkeypatch):
    _clear_auth_env(monkeypatch)
    assert ElevenLabsTTS().get_status() == ToolStatus.UNAVAILABLE


def test_get_status_available_with_explicit_api_key(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    assert ElevenLabsTTS().get_status() == ToolStatus.AVAILABLE


def test_get_status_available_via_agent_proxy_without_any_local_key(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("CCR_AGENT_PROXY_ENABLED", "1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:46769")
    assert ElevenLabsTTS().get_status() == ToolStatus.AVAILABLE


def test_registry_discovers_elevenlabs_tts(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    registry = ToolRegistry()
    registry.discover()

    tool = registry.get("elevenlabs_tts")
    assert tool is not None
    assert tool.get_status() == ToolStatus.AVAILABLE


def test_execute_fails_fast_with_no_credential_and_makes_no_network_call(monkeypatch):
    _clear_auth_env(monkeypatch)
    tool = ElevenLabsTTS()

    with patch("requests.post") as mock_post:
        result = tool.execute({"text": "hola"})

    assert result.success is False
    assert "No ElevenLabs credential available" in result.error
    assert "ELEVENLABS_API_KEY" in result.error
    mock_post.assert_not_called()


def test_execute_with_explicit_api_key_sends_it_as_header(tmp_path, monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "real-looking-test-key")
    output_path = tmp_path / "narration.mp3"
    tool = ElevenLabsTTS()

    response = _response(content=b"fake-mp3-bytes")
    with patch("requests.post", return_value=response) as mock_post:
        result = tool.execute(
            {
                "text": "Hola mundo",
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
                "output_path": str(output_path),
            }
        )

    assert result.success is True
    assert result.data["auth_mode"] == "api_key"
    assert mock_post.call_args.kwargs["headers"]["xi-api-key"] == "real-looking-test-key"


def test_execute_via_agent_proxy_sends_no_api_key_header(tmp_path, monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("CCR_AGENT_PROXY_ENABLED", "1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:46769")
    output_path = tmp_path / "narration.mp3"
    tool = ElevenLabsTTS()

    response = _response(content=b"fake-mp3-bytes")
    with patch("requests.post", return_value=response) as mock_post:
        result = tool.execute(
            {
                "text": "Hola mundo",
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
                "output_path": str(output_path),
            }
        )

    assert result.success is True
    assert result.data["auth_mode"] == "proxy_managed"
    # Never fabricate a placeholder credential — the header must be absent,
    # not empty, so the proxy is free to inject the real one.
    assert "xi-api-key" not in mock_post.call_args.kwargs["headers"]


def test_explicit_api_key_takes_priority_over_agent_proxy(tmp_path, monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "real-looking-test-key")
    monkeypatch.setenv("CCR_AGENT_PROXY_ENABLED", "1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:46769")
    output_path = tmp_path / "narration.mp3"
    tool = ElevenLabsTTS()

    response = _response(content=b"fake-mp3-bytes")
    with patch("requests.post", return_value=response) as mock_post:
        result = tool.execute(
            {"text": "hi", "voice_id": "21m00Tcm4TlvDq8ikWAM", "output_path": str(output_path)}
        )

    assert result.data["auth_mode"] == "api_key"
    assert mock_post.call_args.kwargs["headers"]["xi-api-key"] == "real-looking-test-key"


def test_execute_without_timestamps_hits_plain_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    output_path = tmp_path / "narration.mp3"
    tool = ElevenLabsTTS()

    response = _response(content=b"fake-mp3-bytes")
    with patch("requests.post", return_value=response) as mock_post:
        result = tool.execute(
            {
                "text": "Hola mundo",
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
                "output_path": str(output_path),
            }
        )

    assert result.success is True
    assert output_path.read_bytes() == b"fake-mp3-bytes"
    assert "word_timestamps" not in result.data
    url = mock_post.call_args.args[0]
    assert url.endswith("/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM")
    assert not url.endswith("/with-timestamps")
    assert mock_post.call_args.kwargs["headers"]["Accept"] == "audio/mpeg"
    assert result.artifacts == [str(output_path)]


def test_execute_with_timestamps_hits_with_timestamps_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    output_path = tmp_path / "narration.mp3"
    tool = ElevenLabsTTS()

    text = "¡Hola, señor! ¿Cómo estás?"
    characters = list(text)
    char_seconds = 0.05
    start_times = [round(i * char_seconds, 4) for i in range(len(characters))]
    end_times = [round((i + 1) * char_seconds, 4) for i in range(len(characters))]
    fake_audio = b"totally-real-mp3-bytes"

    response = _response(
        json_data={
            "audio_base64": base64.b64encode(fake_audio).decode("ascii"),
            "alignment": {
                "characters": characters,
                "character_start_times_seconds": start_times,
                "character_end_times_seconds": end_times,
            },
        }
    )

    with patch("requests.post", return_value=response) as mock_post:
        result = tool.execute(
            {
                "text": text,
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
                "model_id": "eleven_multilingual_v2",
                "with_timestamps": True,
                "output_path": str(output_path),
            }
        )

    assert result.success is True

    # Audio bytes were base64-decoded and written, not the raw JSON body.
    assert output_path.read_bytes() == fake_audio

    url = mock_post.call_args.args[0]
    assert url.endswith("/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM/with-timestamps")
    assert mock_post.call_args.kwargs["headers"]["Accept"] == "application/json"

    words = result.data["word_timestamps"]
    assert [w["word"] for w in words] == ["¡Hola,", "señor!", "¿Cómo", "estás?"]
    assert result.data["captions_source"] == "elevenlabs_alignment"

    # Timestamps are monotonic and each word's own span is non-negative.
    for word in words:
        assert word["start"] <= word["end"]
    for previous, current in zip(words, words[1:]):
        assert previous["end"] <= current["start"]

    # Sidecar file was written next to the audio with the same word data.
    sidecar_path = result.data["word_timestamps_path"]
    assert sidecar_path == str(output_path.parent / f"{output_path.stem}.words.json")
    sidecar = json.loads(open(sidecar_path, encoding="utf-8").read())
    assert sidecar["source"] == "elevenlabs_alignment"
    assert sidecar["words"] == words
    assert result.artifacts == [str(output_path), sidecar_path]


def test_voice_id_falls_back_to_witers_david_when_brand_wallet_has_none(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    output_path = tmp_path / "narration.mp3"
    tool = ElevenLabsTTS()

    response = _response(content=b"fake-mp3-bytes")
    with patch("requests.post", return_value=response) as mock_post:
        result = tool.execute({"text": "hi", "output_path": str(output_path)})

    assert result.data["voice_id"] == DAVID_VOICE_ID
    assert mock_post.call_args.args[0].endswith(f"/v1/text-to-speech/{DAVID_VOICE_ID}")
    # No model_id given either, and David is a Witers preferred voice, so
    # the preferred model (eleven_v3) applies automatically.
    assert result.data["model"] == "eleven_v3"


def test_brand_wallet_voice_id_is_never_overridden_by_the_david_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    output_path = tmp_path / "narration.mp3"
    tool = ElevenLabsTTS()
    brand_wallet_voice = "SomeBrandWalletVoiceId123"

    response = _response(content=b"fake-mp3-bytes")
    with patch("requests.post", return_value=response):
        result = tool.execute(
            {"text": "hi", "voice_id": brand_wallet_voice, "output_path": str(output_path)}
        )

    assert result.data["voice_id"] == brand_wallet_voice
    assert result.data["voice_id"] != DAVID_VOICE_ID
    # Unrelated (non-Witers) voice keeps the generic default model.
    assert result.data["model"] == "eleven_multilingual_v2"


def test_model_id_defaults_to_eleven_v3_when_brand_wallet_picks_a_witers_voice(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    output_path = tmp_path / "narration.mp3"
    tool = ElevenLabsTTS()

    response = _response(content=b"fake-mp3-bytes")
    with patch("requests.post", return_value=response):
        result = tool.execute(
            {"text": "hi", "voice_id": JC_VOICE_ID, "output_path": str(output_path)}
        )

    assert result.data["voice_id"] == JC_VOICE_ID
    assert result.data["model"] == "eleven_v3"


def test_explicit_model_id_is_never_overridden_even_for_a_witers_voice(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    output_path = tmp_path / "narration.mp3"
    tool = ElevenLabsTTS()

    response = _response(content=b"fake-mp3-bytes")
    with patch("requests.post", return_value=response):
        result = tool.execute(
            {
                "text": "hi",
                "voice_id": JC_VOICE_ID,
                "model_id": "eleven_multilingual_v2",
                "output_path": str(output_path),
            }
        )

    assert result.data["model"] == "eleven_multilingual_v2"


def test_tts_selector_adapts_generic_timestamps_flag_for_elevenlabs():
    from tools.audio.tts_selector import TTSSelector

    tool = MagicMock()
    tool.name = "elevenlabs_tts"

    adapted = TTSSelector._adapt_inputs(tool, {"text": "hi", "timestamps": True})

    assert adapted["with_timestamps"] is True


def test_tts_selector_does_not_touch_with_timestamps_if_already_set():
    from tools.audio.tts_selector import TTSSelector

    tool = MagicMock()
    tool.name = "elevenlabs_tts"

    adapted = TTSSelector._adapt_inputs(
        tool, {"text": "hi", "timestamps": True, "with_timestamps": False}
    )

    assert adapted["with_timestamps"] is False


def test_tts_selector_leaves_other_providers_unchanged():
    from tools.audio.tts_selector import TTSSelector

    tool = MagicMock()
    tool.name = "fal_elevenlabs_tts"

    inputs = {"text": "hi", "timestamps": True}
    adapted = TTSSelector._adapt_inputs(tool, inputs)

    assert adapted == inputs
