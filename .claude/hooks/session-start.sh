#!/bin/bash
# OpenMontage SessionStart hook (Claude Code on the web / cloud sessions only).
#
# Installs the runtime dependencies OpenMontage needs (FFmpeg, Python packages,
# Remotion's node_modules) so a fresh cloud container is production-ready
# without an agent having to rediscover and rerun `make setup` by hand every
# session. Reuses OpenMontage's own dependency manifests (requirements*.txt,
# remotion-composer/package.json) rather than a separate hardcoded list, so it
# stays in sync with the project's existing setup mechanism.
#
# Safe to re-run: every step first checks whether its target is already
# satisfied, so a warm/cached container just verifies and exits fast.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

echo "==> OpenMontage session-start: checking runtime dependencies..."

# --- FFmpeg (required by video_post/audio_processing tools and both render engines) ---
if command -v ffmpeg >/dev/null 2>&1; then
  echo "==> ffmpeg already installed ($(ffmpeg -version | head -1))"
else
  echo "==> Installing ffmpeg..."
  SUDO=""
  command -v sudo >/dev/null 2>&1 && SUDO="sudo"

  # This container's outbound network only allows HTTPS CONNECT through the
  # local Claude Code agent proxy; apt's default Ubuntu mirrors use plain
  # http:// URLs, which that proxy rejects outright. When a proxy is
  # configured, switch the main archive/security mirrors to https:// and
  # point apt at the proxy so `apt-get update` can actually reach them.
  PROXY_URL="${HTTPS_PROXY:-${https_proxy:-}}"
  if [ -n "$PROXY_URL" ]; then
    grep -rlE 'http://(archive|security)\.ubuntu\.com' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null \
      | xargs -r $SUDO sed -i -E 's#http://(archive|security)\.ubuntu\.com#https://\1.ubuntu.com#g'
    printf 'Acquire::https::Proxy "%s";\n' "$PROXY_URL" | $SUDO tee /etc/apt/apt.conf.d/99claude-cloud-proxy.conf >/dev/null
  fi

  if [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then
    $SUDO apt-get update -qq \
      -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ubuntu.sources \
      -o Dir::Etc::sourceparts=/dev/null
  else
    $SUDO apt-get update -qq || true
  fi
  $SUDO apt-get install -y -qq ffmpeg \
    || echo "  [skip] ffmpeg install failed — video_post/audio_processing tools will be degraded until it's installed manually"
fi

# --- Python dependencies ---
# Installed straight into the container's system Python (no venv): the agent
# invokes `python`/`python3` directly (see AGENT_GUIDE.md preflight commands),
# and this container is single-purpose and disposable, so there's no
# multi-project isolation concern a venv would be solving here.
echo "==> Installing Python dependencies (requirements.txt + requirements-dev.txt)..."
python3 -m pip install -q -r requirements.txt -r requirements-dev.txt

# --- Remotion composer (Node deps for the Remotion render engine) ---
if [ ! -d "remotion-composer/node_modules" ]; then
  echo "==> Installing Remotion composer dependencies..."
  (cd remotion-composer && npm install --no-fund --no-audit)
else
  echo "==> remotion-composer/node_modules already present"
fi

# --- Piper TTS (free offline narration, best-effort) ---
if ! python3 -c "import piper" >/dev/null 2>&1; then
  echo "==> Installing piper-tts (offline TTS)..."
  python3 -m pip install -q piper-tts || echo "  [skip] piper-tts install failed — TTS will use cloud providers instead"
else
  echo "==> piper-tts already installed"
fi

# --- HyperFrames runtime cache warm (best-effort, avoids first-render cold fetch) ---
echo "==> Warming HyperFrames npx cache..."
npx --yes hyperframes --version >/dev/null 2>&1 && echo "    HyperFrames CLI cached (npx)" || echo "  [skip] HyperFrames cache-warm failed — first render will fetch on demand"

# --- .env scaffold (never overwrites an existing file, never adds secrets) ---
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example (no keys set — add your own to unlock cloud providers)"
fi

echo "==> OpenMontage session-start: done."
