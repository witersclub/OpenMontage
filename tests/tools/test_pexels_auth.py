"""Regression: Pexels stock search must work under the Claude Code Cloud
agent-proxy credential, not just a local PEXELS_API_KEY.

Before this fix, `PexelsSource.is_available()`/`_headers()` only checked
`os.environ["PEXELS_API_KEY"]`, so `direct_clip_search` reported Pexels
unavailable in any environment relying on the proxy-injected credential for
api.pexels.com (mirrors the pre-existing ELEVENLABS_API_KEY / proxy_managed
split already covered for `elevenlabs_auth`).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.video.pexels_auth import resolve_pexels_auth  # noqa: E402
from tools.video.stock_sources.pexels import PexelsSource  # noqa: E402

_PROXY_ENV = {"CCR_AGENT_PROXY_ENABLED": "1", "HTTPS_PROXY": "http://127.0.0.1:33373"}


def test_api_key_wins_when_present():
    auth = resolve_pexels_auth({"PEXELS_API_KEY": "abc123", **_PROXY_ENV})
    assert auth.mode == "api_key"
    assert auth.api_key == "abc123"
    assert auth.available


def test_proxy_managed_when_no_key_but_proxy_active():
    auth = resolve_pexels_auth(_PROXY_ENV)
    assert auth.mode == "proxy_managed"
    assert auth.api_key is None
    assert auth.available


def test_unavailable_when_neither_present():
    auth = resolve_pexels_auth({})
    assert auth.mode == "none"
    assert not auth.available


def test_source_is_available_under_proxy_managed_mode(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.setenv("CCR_AGENT_PROXY_ENABLED", "1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:33373")
    assert PexelsSource().is_available()


def test_source_headers_send_no_authorization_under_proxy_managed_mode(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.setenv("CCR_AGENT_PROXY_ENABLED", "1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:33373")
    assert PexelsSource()._headers() == {}


def test_source_headers_send_authorization_when_key_present(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "abc123")
    assert PexelsSource()._headers() == {"Authorization": "abc123"}
