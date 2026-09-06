"""Credential resolution for Pexels API calls.

Mirrors `tools.audio.elevenlabs_auth`: two valid ways to authenticate exist
side by side, and detection between them is automatic.

1. **Self-hosted / direct** — `PEXELS_API_KEY` is set (env var, or a repo
   `.env` picked up by `tools.base_tool`'s loader). The tool sends it
   explicitly as the `Authorization` header.
2. **Claude Code Cloud** — no local key at all. This session's outbound
   HTTPS is routed through the Claude Code agent proxy
   (`CCR_AGENT_PROXY_ENABLED` + `HTTPS_PROXY`), which can inject a securely
   provisioned Pexels credential for `api.pexels.com` without this process
   ever holding the key. The tool sends **no** `Authorization` header at
   all in this mode and lets the proxy fill it in.

Neither path is assumed blindly: `resolve_pexels_auth()` only reports
`"proxy_managed"` when the proxy markers are actually present, and the
caller still gets a real HTTP error from Pexels if that guess was wrong.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

_FALSY_FLAG_VALUES = {"", "0", "false", "no", "off"}


@dataclass(frozen=True)
class PexelsAuth:
    """The resolved authentication mode for one Pexels API call.

    `api_key` is the literal value to send as `Authorization`, or None when
    no header should be sent at all (proxy_managed / none).
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


def resolve_pexels_auth(env: Mapping[str, str] | None = None) -> PexelsAuth:
    """Decide how to authenticate to Pexels for this process.

    Checks `PEXELS_API_KEY` first (self-hosted/direct). Falls back to
    detecting the Claude Code Cloud agent proxy, which can inject a
    credential for `api.pexels.com` on its own. Reports `"none"` when
    neither applies.
    """
    source = os.environ if env is None else env
    api_key = source.get("PEXELS_API_KEY")
    if api_key:
        return PexelsAuth(api_key=api_key, mode="api_key")
    if _agent_proxy_active(source):
        return PexelsAuth(api_key=None, mode="proxy_managed")
    return PexelsAuth(api_key=None, mode="none")
