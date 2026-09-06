"""ElevenLabs text-to-speech provider tool."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from tools.audio.elevenlabs_alignment import alignment_to_word_timestamps
from tools.audio.elevenlabs_auth import ElevenLabsAuth, resolve_elevenlabs_auth
from tools.audio.witers_voice_library import resolve_witers_voice_id, resolve_witers_voice_model
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class ElevenLabsTTS(BaseTool):
    name = "elevenlabs_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "elevenlabs"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = (
        "Provide an ElevenLabs credential through one of two paths "
        "(checked automatically, no configuration flag to set):\n"
        "  1. Self-hosted / direct: set the ELEVENLABS_API_KEY environment "
        "variable.\n"
        "     export ELEVENLABS_API_KEY=your_key_here\n"
        "     Get a key at https://elevenlabs.io\n"
        "  2. Claude Code Cloud: no env var needed. Ask an administrator to "
        "provision an ElevenLabs credential on this session's agent proxy "
        "for api.elevenlabs.io.\n"
        "If fal_elevenlabs_tts is available, use it instead to access ElevenLabs "
        "speech through fal.ai without a separate ElevenLabs key."
    )
    fallback = "openai_tts"
    fallback_tools = ["openai_tts", "piper_tts"]
    agent_skills = ["elevenlabs"]

    capabilities = [
        "text_to_speech",
        "voice_selection",
        "ssml_support",
        "pronunciation_control",
        "word_timestamps",
    ]
    supports = {
        "voice_cloning": True,
        "multilingual": True,
        "offline": False,
        "native_audio": True,
        "word_timestamps": True,
    }
    best_for = [
        "high-quality narration",
        "voice-sensitive spokesperson videos",
        "multilingual spoken delivery",
    ]
    not_good_for = [
        "fully offline production",
        "privacy-constrained local-only workflows",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "description": "Text to convert to speech"},
            "voice_id": {
                "type": "string",
                "description": (
                    "ElevenLabs voice ID. This should come from Brand Wallet "
                    "when a brand has one configured — it always wins. When "
                    "unset, falls back to Witers' pre-approved default voice "
                    "(David - British Storyteller)."
                ),
            },
            "model_id": {
                "type": "string",
                "description": (
                    "TTS model to use. Defaults to eleven_multilingual_v2, "
                    "except when voice_id resolves to one of Witers' "
                    "preferred voices (David, JC, Kate, Luján), which default "
                    "to eleven_v3 instead."
                ),
            },
            "stability": {
                "type": "number",
                "default": 0.5,
                "minimum": 0,
                "maximum": 1,
            },
            "similarity_boost": {
                "type": "number",
                "default": 0.75,
                "minimum": 0,
                "maximum": 1,
            },
            "style": {
                "type": "number",
                "default": 0.0,
                "minimum": 0,
                "maximum": 1,
            },
            "speed": {
                "type": "number",
                "default": 1.0,
                "minimum": 0.7,
                "maximum": 1.2,
            },
            "use_speaker_boost": {
                "type": "boolean",
                "default": True,
            },
            "output_path": {"type": "string"},
            "output_format": {
                "type": "string",
                "default": "mp3_44100_128",
                "enum": ["mp3_44100_128", "mp3_44100_192", "pcm_16000", "pcm_24000"],
            },
            "with_timestamps": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Request word-level timing via ElevenLabs' /with-timestamps "
                    "endpoint instead of the plain synthesis endpoint. Adds "
                    "word_timestamps ({word, start, end} in seconds, the same "
                    "shape Transcriber produces) and word_timestamps_path to the "
                    "result, so captions can skip a separate Whisper pass."
                ),
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = [
        "text",
        "voice_id",
        "model_id",
        "stability",
        "similarity_boost",
        "style",
        "speed",
        "use_speaker_boost",
        "with_timestamps",
    ]
    side_effects = [
        "writes audio file to output_path",
        "when with_timestamps=True, also writes a {word,start,end} timestamps JSON sidecar",
        "calls ElevenLabs API",
    ]
    user_visible_verification = ["Listen to generated audio for natural speech quality"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if resolve_elevenlabs_auth().available else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return round(len(inputs.get("text", "")) * 0.0003, 4)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        auth = resolve_elevenlabs_auth()
        if not auth.available:
            return ToolResult(
                success=False,
                error="No ElevenLabs credential available. " + self.install_instructions,
            )

        start = time.time()
        try:
            result = self._generate(inputs, auth)
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"TTS generation failed (auth_mode={auth.mode}): {exc}",
            )

        result.duration_seconds = round(time.time() - start, 2)
        result.cost_usd = self.estimate_cost(inputs)
        return result

    def _generate(self, inputs: dict[str, Any], auth: ElevenLabsAuth) -> ToolResult:
        import requests

        text = inputs["text"]
        # Brand Wallet's voice_id always wins; only falls back to Witers'
        # pre-approved default (David) when the caller didn't supply one.
        voice_id = resolve_witers_voice_id(inputs.get("voice_id"))
        # Only defaults to eleven_v3 when voice_id resolved to one of
        # Witers' preferred voices; an unrelated voice_id keeps the generic
        # multilingual_v2 default.
        model_id = (
            inputs.get("model_id")
            or resolve_witers_voice_model(voice_id)
            or "eleven_multilingual_v2"
        )
        output_format = inputs.get("output_format", "mp3_44100_128")
        with_timestamps = bool(inputs.get("with_timestamps", False))
        voice_settings = {
            "stability": inputs.get("stability", 0.5),
            "similarity_boost": inputs.get("similarity_boost", 0.75),
            "style": inputs.get("style", 0.0),
            "speed": inputs.get("speed", 1.0),
            "use_speaker_boost": inputs.get("use_speaker_boost", True),
        }

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        if with_timestamps:
            url += "/with-timestamps"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json" if with_timestamps else "audio/mpeg",
        }
        if auth.api_key:
            headers["xi-api-key"] = auth.api_key
        # else: proxy_managed — no header is sent; the session's agent
        # proxy is expected to inject a credential for api.elevenlabs.io.

        response = requests.post(
            url,
            headers=headers,
            json={
                "text": text,
                "model_id": model_id,
                "voice_settings": voice_settings,
            },
            params={"output_format": output_format},
            timeout=120,
        )
        response.raise_for_status()

        ext = "mp3" if "mp3" in output_format else "wav"
        output_path = Path(inputs.get("output_path", f"tts_output.{ext}"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "provider": self.provider,
            "model": model_id,
            "voice_id": voice_id,
            "voice_settings": voice_settings,
            "text_length": len(text),
            "output": str(output_path),
            "format": output_format,
            "auth_mode": auth.mode,
        }
        artifacts = [str(output_path)]

        if with_timestamps:
            payload = response.json()
            output_path.write_bytes(base64.b64decode(payload["audio_base64"]))

            word_timestamps = alignment_to_word_timestamps(payload.get("alignment", {}))
            timestamps_path = output_path.parent / f"{output_path.stem}.words.json"
            timestamps_path.write_text(
                json.dumps(
                    {
                        "version": "1.0",
                        "provider": self.provider,
                        "source": "elevenlabs_alignment",
                        "words": word_timestamps,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            data["word_timestamps"] = word_timestamps
            data["word_timestamps_path"] = str(timestamps_path)
            data["captions_source"] = "elevenlabs_alignment"
            artifacts.append(str(timestamps_path))
        else:
            output_path.write_bytes(response.content)

        return ToolResult(
            success=True,
            data=data,
            artifacts=artifacts,
            model=model_id,
        )
