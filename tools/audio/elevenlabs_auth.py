"""Credential resolution for ElevenLabs API calls.

Two valid ways to authenticate exist side by side, and detection between
them is automatic:

1. **Self-hosted / direct** — `ELEVENLABS_API_KEY` is set (env var, or a
   repo `.env` picked up by `tools.base_tool`'s loader). The tool sends it
   explicitly as the `xi-api-key` header.
2. **Claude Code Cloud** — no local key at all. This session's outbound
   HTTPS is routed through the Claude Code agent proxy
   (`CCR_AGENT_PROXY_ENABLED` + `HTTPS_PROXY`), which can inject a securely
   provisioned ElevenLabs credential for `api.elevenlabs.io` without this
   process ever holding the key. The tool sends **no** `xi-api-key` header
   at all in this mode and lets the proxy fill it in.

Neither path is assumed blindly: `resolve_elevenlabs_auth()` only reports
`"proxy_managed"` when the proxy markers are actually present, and the
caller still gets a real HTTP error from ElevenLabs if that guess was wrong
(e.g. the proxy has no ElevenLabs credential provisioned for this session).
When neither path applies, callers should fail fast with a clear message
instead of guessing or sending a placeholder credential.

No secret is ever read, logged, returned, or written to disk by this
module — only which authentication mode applies (`api_key` / `proxy_managed`
/ `none`), which is safe to include in tool results, logs, and artifacts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

_FALSY_FLAG_VALUES = {"", "0", "false", "no", "off"}


@dataclass(frozen=True)
class ElevenLabsAuth:
    """The resolved authentication mode for one ElevenLabs API call.

    `api_key` is the literal value to send as `xi-api-key`, or None when no
    header should be sent at all (proxy_managed / none).
    """

    api_key: str | None
    mode: str  # "api_key" | "proxy_managed" | "none"

    @property
    def available(self) -> bool:
        return self.mode != "none"


def _agent_proxy_active(env: Mapping[str, str]) -> bool:
    """True when this session's outbound HTTPS actually routes through the
    Claude Code agent proxy, which is the only thing that could be injecting
    a credential we never see."""
    enabled = env.get("CCR_AGENT_PROXY_ENABLED", "").strip().lower()
    has_https_proxy = bool(env.get("HTTPS_PROXY") or env.get("https_proxy"))
    return enabled not in _FALSY_FLAG_VALUES and has_https_proxy


def resolve_elevenlabs_auth(env: Mapping[str, str] | None = None) -> ElevenLabsAuth:
    """Decide how to authenticate to ElevenLabs for this process.

    Checks `ELEVENLABS_API_KEY` first (self-hosted/direct). Falls back to
    detecting the Claude Code Cloud agent proxy, which can inject a
    credential for `api.elevenlabs.io` on its own. Reports `"none"` when
    neither applies — callers should treat that as unavailable and fail
    with a clear message rather than attempting the call.
    """
    source = os.environ if env is None else env
    api_key = source.get("ELEVENLABS_API_KEY")
    if api_key:
        return ElevenLabsAuth(api_key=api_key, mode="api_key")
    if _agent_proxy_active(source):
        return ElevenLabsAuth(api_key=None, mode="proxy_managed")
    return ElevenLabsAuth(api_key=None, mode="none")
