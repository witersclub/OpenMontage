"""Music generation tool via ElevenLabs Music API.

Generates background music and sound effects for video production.
Reports unavailable when no credential is resolvable — either a local
ELEVENLABS_API_KEY or a Claude Code Cloud agent-proxy-injected credential
for api.elevenlabs.io (see tools.audio.elevenlabs_auth).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tools.audio.elevenlabs_auth import ElevenLabsAuth, resolve_elevenlabs_auth
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


class MusicGen(BaseTool):
    name = "music_gen"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "music_generation"
    provider = "elevenlabs"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []  # checked dynamically via credential resolution
    install_instructions = (
        "Provide an ElevenLabs credential through one of two paths "
        "(checked automatically, no configuration flag to set):\n"
        "  1. Self-hosted / direct: set the ELEVENLABS_API_KEY environment "
        "variable.\n"
        "     export ELEVENLABS_API_KEY=your_key_here\n"
        "     Get a key at https://elevenlabs.io\n"
        "  2. Claude Code Cloud: no env var needed. Ask an administrator to "
        "provision an ElevenLabs credential on this session's agent proxy "
        "for api.elevenlabs.io."
    )

    agent_skills = ["music", "sound-effects", "elevenlabs"]

    capabilities = [
        "generate_background_music",
        "generate_sfx",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Music description (mood, genre, instruments, tempo)",
            },
            "duration_seconds": {
                "type": "number",
                "minimum": 3,
                "maximum": 600,
                "description": (
                    "Target duration in seconds (API supports 3-600s). "
                    "Should match the target video duration from the script/proposal. "
                    "Omitting this defaults to 60s which may not match your video."
                ),
            },
            "output_path": {"type": "string"},
            "force_instrumental": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Whether to generate instrumental-only music (no vocals). "
                    "Defaults to True — the music-gen-usage mandate is to always "
                    "set force_instrumental=true for video background music, since "
                    "vocals collide with narration/dialogue. Set False only for "
                    "explicitly vocal-led pieces."
                ),
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "duration_seconds"]
    side_effects = ["writes audio file to output_path", "calls ElevenLabs API"]
    user_visible_verification = [
        "Listen to generated music for mood and quality",
    ]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if resolve_elevenlabs_auth().available else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # ElevenLabs music generation pricing is per generation
        duration = inputs.get("duration_seconds")
        if duration is None:
            raise ValueError(
                "music_gen.estimate_cost: duration_seconds is required. "
                "Derive it from the approved target runtime in the script/proposal. "
                "Silent defaults are not permitted."
            )
        # Approximate: ~$0.05 per 30 seconds
        return round(duration / 30 * 0.05, 4)

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
        except Exception as e:
            return ToolResult(success=False, error=f"Music generation failed (auth_mode={auth.mode}): {e}")

        result.duration_seconds = round(time.time() - start, 2)
        result.cost_usd = self.estimate_cost(inputs)
        return result

    def _generate(self, inputs: dict[str, Any], auth: ElevenLabsAuth) -> ToolResult:
        import requests

        prompt = inputs["prompt"]
        duration = inputs.get("duration_seconds")
        if duration is None:
            return ToolResult(
                success=False,
                error=(
                    "music_gen: duration_seconds is required. "
                    "Derive it from the approved target runtime in the script/proposal. "
                    "Silent defaults to 60s are not permitted — the generated music "
                    "must match the actual video duration."
                ),
            )

        url = "https://api.elevenlabs.io/v1/music"

        headers = {"Content-Type": "application/json"}
        if auth.api_key:
            headers["xi-api-key"] = auth.api_key
        # else: proxy_managed — no header is sent; the session's agent
        # proxy is expected to inject a credential for api.elevenlabs.io.

        payload = {
            "prompt": prompt,
            "music_length_ms": int(duration * 1000),
            # music-gen-usage mandate: always set force_instrumental=true for
            # video background music (vocals collide with narration). The input
            # schema defaults this to True, so callers get the mandate by
            # default; they may opt out only by passing force_instrumental=False.
            "force_instrumental": bool(inputs.get("force_instrumental", True)),
        }

        response = requests.post(
            url, headers=headers, json=payload, timeout=180
        )
        response.raise_for_status()

        output_path = Path(inputs.get("output_path", "music_output.mp3"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)

        return ToolResult(
            success=True,
            data={
                "provider": "elevenlabs",
                "prompt": prompt,
                "duration_seconds": duration,
                "output": str(output_path),
                "format": "mp3",
                "auth_mode": auth.mode,
            },
            artifacts=[str(output_path)],
        )
