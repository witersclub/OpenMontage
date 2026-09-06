"""Tests for ElevenLabs credential resolution.

Pure function tests — an explicit `env` dict is passed to every call, so
these never touch the real process environment (important: the sandbox this
suite runs in is itself a Claude Code Cloud session with the agent proxy
genuinely enabled, so relying on ambient os.environ here would make these
tests describe the test machine instead of the logic under test).
"""

from __future__ import annotations

from tools.audio.elevenlabs_auth import resolve_elevenlabs_auth


def test_no_signals_at_all_is_unavailable():
    auth = resolve_elevenlabs_auth(env={})

    assert auth.mode == "none"
    assert auth.available is False
    assert auth.api_key is None


def test_explicit_api_key_is_used_directly():
    auth = resolve_elevenlabs_auth(env={"ELEVENLABS_API_KEY": "sk-real-looking-key"})

    assert auth.mode == "api_key"
    assert auth.available is True
    assert auth.api_key == "sk-real-looking-key"


def test_agent_proxy_markers_alone_resolve_to_proxy_managed():
    auth = resolve_elevenlabs_auth(
        env={"CCR_AGENT_PROXY_ENABLED": "1", "HTTPS_PROXY": "http://127.0.0.1:46769"}
    )

    assert auth.mode == "proxy_managed"
    assert auth.available is True
    # No key was ever provided, so none should be reported.
    assert auth.api_key is None


def test_lowercase_https_proxy_variable_also_counts():
    auth = resolve_elevenlabs_auth(
        env={"CCR_AGENT_PROXY_ENABLED": "1", "https_proxy": "http://127.0.0.1:46769"}
    )

    assert auth.mode == "proxy_managed"


def test_proxy_flag_without_an_actual_proxy_configured_is_not_enough():
    # CCR_AGENT_PROXY_ENABLED=1 with no HTTPS_PROXY means nothing would
    # actually route through the proxy, so no credential could be injected.
    auth = resolve_elevenlabs_auth(env={"CCR_AGENT_PROXY_ENABLED": "1"})

    assert auth.mode == "none"


def test_https_proxy_alone_without_the_enabled_flag_is_not_enough():
    auth = resolve_elevenlabs_auth(env={"HTTPS_PROXY": "http://127.0.0.1:46769"})

    assert auth.mode == "none"


def test_explicit_api_key_takes_priority_over_agent_proxy():
    auth = resolve_elevenlabs_auth(
        env={
            "ELEVENLABS_API_KEY": "sk-real-looking-key",
            "CCR_AGENT_PROXY_ENABLED": "1",
            "HTTPS_PROXY": "http://127.0.0.1:46769",
        }
    )

    assert auth.mode == "api_key"
    assert auth.api_key == "sk-real-looking-key"


def test_empty_api_key_string_is_treated_as_unset():
    auth = resolve_elevenlabs_auth(
        env={
            "ELEVENLABS_API_KEY": "",
            "CCR_AGENT_PROXY_ENABLED": "1",
            "HTTPS_PROXY": "http://127.0.0.1:46769",
        }
    )

    assert auth.mode == "proxy_managed"


def test_falsy_flag_values_disable_the_agent_proxy_path():
    for falsy in ("0", "false", "False", "no", "off", ""):
        auth = resolve_elevenlabs_auth(
            env={"CCR_AGENT_PROXY_ENABLED": falsy, "HTTPS_PROXY": "http://127.0.0.1:46769"}
        )
        assert auth.mode == "none", f"{falsy!r} should not enable proxy_managed mode"


def test_no_env_argument_falls_back_to_a_dict_like_real_os_environ():
    # Just confirms the default path doesn't crash and returns *a* result —
    # actual coverage of the real-environment behavior lives in
    # test_elevenlabs_tts.py via monkeypatch, since that's what can control
    # os.environ safely per-test.
    auth = resolve_elevenlabs_auth()
    assert auth.mode in {"api_key", "proxy_managed", "none"}
